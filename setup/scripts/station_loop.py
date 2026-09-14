"""station_loop.py -- the Station loop v1 (GOAL-GAMMA-STATION-2026-09-13 item (4)).

THE GAP THIS CLOSES: Gamma's autonomy today is all REACTIVE (heartbeat ticks on price,
conductor fires on a clock) -- nothing brings J an idea he did not ask for. Every fire this
reads real state (ledgers, hypotheses, the goal ladder, the newest EOD-deep note, HOME.md's
learned-today block -- see station_facts.py), makes ONE call to a LOCAL Ollama model
(default `gamma-planner`, $0, no Anthropic tokens), and writes at most 2 new falsifiable
idea-cards to `automation/state/station/ideas-board.json` plus a short first-person brief.

NEVER: orders, broker calls, Discord/outbox writes, or any edit to the trading path
(heartbeat_core / fleet / filters / risk_gate / params / heartbeat*.md are untouched by
this file and everything it imports). No LLM call happens near the live tick.

YIELD RULE (checked before the model call, cheapest signal first): (a) RTH -- weekdays
09:30-15:55 ET via et_clock.is_market_hours (never Bash TZ=); (b) GPU busy -- nvidia-smi
utilization.gpu > config.gpu_util_yield_pct (default 50); (c) a denylisted process
(config.yield_processes) is alive, read via _proc_table.py (the wmic-removed-on-24H2
replacement -- NEVER wmic); (d) Ollama unreachable at /api/version -> status "error",
reason "ollama_down" (a hard prerequisite miss, not a "yield"; logged loud, exit 0 so the
task never spams Task Scheduler with a nonzero-exit alarm). --force (manual runs only)
skips (a)-(c); (d) always runs -- there is no point calling a model that is not there.

OUTPUTS (only ever written here): automation/state/station/{ideas-board.json,
station-brief.md, loop-ledger.jsonl} (config.json is read, not written) and
E:\\Gamma\\logs\\station-loop-<date>.log. Every write is atomic (tmp + os.replace) except
the append-only ledger.

Usage: python setup/scripts/station_loop.py --once [--force]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from et_clock import et_now, et_today_str, et_offset_hours, is_market_hours  # noqa: E402
import _proc_table  # noqa: E402
import station_board  # noqa: E402
import station_facts  # noqa: E402
import hypothesis_scorer  # noqa: E402 -- GOAL-GAMMA-STATION item 12: KNOWN_SPEC_TYPES for schema validation
import conductor_outcome  # noqa: E402 -- item 12: every run_once() path records a fire (source="station")
import sector_rows  # noqa: E402 -- 2026-09-14 company-roster re-point: Coach's sectors.json (C2)
import crew_events  # noqa: E402 -- 2026-09-14 company-roster re-point: the crew ticker (C3)
import audit_scheduled_tasks as _ast  # noqa: E402 -- reused live task-enumeration helper (C2's task_health)

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

STATION_DIR = REPO / "automation" / "state" / "station"
CONFIG_PATH = STATION_DIR / "config.json"
IDEAS_BOARD_PATH = STATION_DIR / "ideas-board.json"
BRIEF_PATH = STATION_DIR / "station-brief.md"
LEDGER_PATH = STATION_DIR / "loop-ledger.jsonl"
# Interactivity amendment (2026-09-13): the dashboard's /api/station/action route
# appends here; drained every fire in run_once() regardless of yield state (see
# station_board.apply_inbox_actions). PENDING_NOTES_PATH accumulates test/ask notes
# until an actual model-calling fire delivers them into a prompt (drained on success
# only -- a failed model call must never lose J's note).
INBOX_PATH = STATION_DIR / "station-inbox.jsonl"
INBOX_PROCESSED_PATH = STATION_DIR / "station-inbox-processed.jsonl"
PENDING_NOTES_PATH = STATION_DIR / "station-pending-notes.json"
STATION_PROMPT_PATH = REPO / "automation" / "prompts" / "station.md"
LOG_DIR = Path("E:/Gamma/logs")
# GAMMA-STATION item 12 (2026-09-13): the closed idea loop's own paths. Module-level (not
# hypothesis_scorer's own defaults) so tests can monkeypatch them exactly like every other
# Station path above -- see hypothesis_scorer.py for the scoring contract itself.
AUTOPSY_DIR = REPO / "analysis" / "autopsies"
VERDICTS_LEDGER_PATH = REPO / "analysis" / "recommendations" / "station-verdicts.jsonl"
SETTLED_HYP_PATH = REPO / "automation" / "state" / "hypotheses-settled.json"
# 2026-09-14 company-roster re-point (C1-C3): Chef's verdict-scoring pass and Coach's
# sectors/rig-health pass already ran every fire -- this file just never wrote down that
# either of them had done anything. SECTORS_PATH/CREW_EVENTS_PATH are the new outputs;
# both written on EVERY fire (yielded or not), never inside the LLM branch below -- see
# _write_sectors_and_crew_events's own docstring.
SECTORS_PATH = STATION_DIR / "sectors.json"
CREW_EVENTS_PATH = STATION_DIR / "crew-events.jsonl"
SECTORS_HEARTBEAT = timedelta(hours=3)  # "every 6th fire" at the 30-min Station cadence

DEFAULT_CONFIG = {
    "model": "gamma-planner",
    "ollama_base_url": "http://localhost:11434",
    "num_ctx": 32768,
    "model_call_timeout_s": 300,
    "gpu_util_yield_pct": 50,
    "yield_processes": [
        # GAMES + GPU encoders only. Launchers (steam.exe, epicgameslauncher.exe, riotclientservices.exe,
        # battle.net.exe, eaconnect_microsoft.exe) were removed 2026-09-13 20:05 ET: Steam idling in the tray
        # kept every unforced fire in yield all evening (denylisted_process:steam.exe) while the TV showed a
        # frozen board. gpu_util_yield_pct catches any real game regardless of its name.
        "obs64.exe",
        "r5apex_dx12.exe", "r5apex.exe",  # Apex Legends -- J's game (2026-09-13: 99% GPU, prefill fell to ~25 tok/s)
    ],
    "web_scan": False,
    "web_scan_feeds": [],
    "max_new_cards_per_fire": 2,
    "board_cap": 50,
    "dedupe_similarity_threshold": 0.8,
    "scorer_min_n": 10,  # GAMMA-STATION item 12: post-registration n before a verdict flips
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "brief": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "mechanism": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "proposed_shadow_test": {"type": "string"},
                    "cost_line": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "med", "high"]},
                    # GAMMA-STATION item 12 (2026-09-13): optional, nullable -- lets a card
                    # self-test on the next fire via hypothesis_scorer.py instead of waiting on
                    # a human to translate proposed_shadow_test prose into code. Deliberately
                    # NOT in this item's "required" list below: an older/leaner model, or a
                    # fire where nothing fits the four spec types, must still be able to
                    # propose a card with test_spec omitted or null (station.md: "if none fits
                    # ... leave test_spec null").
                    "test_spec": {
                        "type": ["object", "null"],
                        "properties": {
                            "type": {"type": "string", "enum": list(hypothesis_scorer.KNOWN_SPEC_TYPES)},
                            "params": {"type": "object"},
                        },
                    },
                },
                "required": ["title", "mechanism", "evidence", "proposed_shadow_test", "cost_line", "confidence"],
            },
        },
        "wants": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["brief", "cards", "wants"],
}

DEFAULT_SYSTEM_PROMPT = (
    "You are Gamma's Station. Cite only the facts you are given. Never invent a number. "
    "Propose at most 2 falsifiable idea cards, each with one proposed shadow test and a "
    "cost line. Never propose live money or a mid-session rule change. Output JSON only."
)


# ---- Logging (plain file, never a console -- pythonw + the wscript hidden chain never
# creates a window to redirect from in the first place) ----

def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = f"[{et_now().strftime('%Y-%m-%d %H:%M:%S ET')}] {msg}\n"
        with (LOG_DIR / f"station-loop-{et_today_str()}.log").open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001 -- logging must never crash the loop
        pass


# ---- Config + ledger ----

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    data = station_board.read_json_or_none(CONFIG_PATH)
    if isinstance(data, dict):
        cfg.update({k: v for k, v in data.items() if not str(k).startswith("_")})
    return cfg


def append_ledger(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---- Yield rule ----

def _gpu_util_pct() -> Optional[float]:
    """Current GPU utilization percent, or None if it cannot be measured (no GPU,
    nvidia-smi missing, etc.) -- fails OPEN (None never yields; this is a courtesy
    gate for a research loop, not a safety gate)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return float(out.stdout.strip().splitlines()[0].strip())
    except Exception:  # noqa: BLE001
        return None


def _read_process_table() -> dict:
    return _proc_table.parse_process_table(_proc_table.process_table_text())


def _denylisted_process(process_table_fn: Callable[[], dict], yield_processes: list) -> Optional[str]:
    if not yield_processes:
        return None
    try:
        table = process_table_fn()
    except Exception:  # noqa: BLE001 -- fail open: an unreadable process table never yields
        return None
    for cmdline in table.values():
        low = (cmdline or "").lower()
        for name in yield_processes:
            if name and name.lower() in low:
                return name
    return None


def _ollama_reachable(base_url: str) -> bool:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/version")
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 -- localhost only
            return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001
        return False


def _station_mode() -> str:
    """J's switch: automation/state/station/mode.json written by setup/scripts/gamma_mode.ps1
    ("gaming" / "off" -> the loop yields; missing or garbled file -> "work")."""
    try:
        path = REPO / "automation" / "state" / "station" / "mode.json"
        if not path.exists():
            return "work"
        return str(json.loads(path.read_text(encoding="utf-8-sig")).get("mode", "work"))  # utf-8-sig: PS 5.1 writes a BOM
    except Exception:  # noqa: BLE001 -- fail-open: a broken switch file never blocks the loop
        return "work"


def _unload_loaded_models() -> list:
    """J's "or both" (2026-09-13: "an off switch or a gaming mode switch or both so I can use all my
    GPU"): when the loop yields because a game/launcher is alive, free the VRAM now instead of waiting
    for Ollama's keep-alive -- `ollama stop` every loaded model, exactly what gamma_mode.ps1 -Mode gaming
    does. Returns the names unloaded. Fail-open: any error -> []."""
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=30,
                             creationflags=_CREATE_NO_WINDOW)
        names = [ln.split()[0] for ln in out.stdout.splitlines()[1:] if ln.strip()]
        for name in names:
            subprocess.run(["ollama", "stop", name], capture_output=True, text=True, timeout=60,
                           creationflags=_CREATE_NO_WINDOW)
        return names
    except Exception:  # noqa: BLE001 -- a courtesy unload never breaks the fire
        return []


def decide_action(
    now_utc: datetime,
    config: dict,
    *,
    force: bool = False,
    gpu_util_fn: Optional[Callable[[], Optional[float]]] = None,
    process_table_fn: Optional[Callable[[], dict]] = None,
    ollama_reachable_fn: Optional[Callable[[str], bool]] = None,
    station_mode_fn: Optional[Callable[[], str]] = None,
) -> tuple:
    """Returns (status, reason). status in {"ok", "yielded", "error"}; proceed to the
    model call only when status == "ok". Every check is injectable so tests never shell
    out or hit the network -- the clock (`now_utc`) is always injected."""
    gpu_util_fn = gpu_util_fn or _gpu_util_pct
    process_table_fn = process_table_fn or _read_process_table
    ollama_reachable_fn = ollama_reachable_fn or _ollama_reachable

    if not force:
        mode = (station_mode_fn or _station_mode)()
        if mode in ("gaming", "off"):
            return "yielded", f"station_mode:{mode} (J reserved the GPU via gamma_mode.ps1)"

        if is_market_hours(now_utc=now_utc):
            return "yielded", "rth_window (weekday 09:30-15:55 ET)"

        # Process check FIRST (2026-09-13): a named game/launcher is the reason run_once unloads the
        # model, so it must win over the generic gpu_util reason when both apply.
        deny = _denylisted_process(process_table_fn, config.get("yield_processes", []))
        if deny:
            return "yielded", f"denylisted_process:{deny}"

        threshold = config.get("gpu_util_yield_pct", 50)
        gpu = gpu_util_fn()
        if gpu is not None and gpu > threshold:
            return "yielded", f"gpu_util {gpu:.0f}% > {threshold}%"

    if not ollama_reachable_fn(config.get("ollama_base_url", DEFAULT_CONFIG["ollama_base_url"])):
        return "error", "ollama_down"

    return "ok", ""


# ---- The model call ----

def call_ollama_chat(model: str, system_text: str, user_text: str, base_url: str,
                     num_ctx: int, *, timeout: int = 300) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        "think": False,
        "format": RESPONSE_SCHEMA,
        "options": {"num_ctx": num_ctx},
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- localhost only
        return json.loads(resp.read().decode("utf-8"))


def _validate_test_spec(spec) -> None:
    """Raises ValueError on a malformed test_spec. None is always fine (no spec offered this
    fire -- station.md explicitly sanctions this). A present spec must be an object with
    `type` in hypothesis_scorer.KNOWN_SPEC_TYPES and a dict `params`. Ollama's own `format`
    schema constrains a compliant model already; this is the defensive second check so a
    model that ignores/half-follows the schema still gets caught here rather than writing a
    card hypothesis_scorer.py can never score. Folded into parse_model_output's existing
    'bad model response -> logged error ledger row, never a crash' handling in run_once()."""
    if spec is None:
        return
    if not isinstance(spec, dict):
        raise ValueError(f"test_spec must be an object or null, got {type(spec).__name__}")
    if spec.get("type") not in hypothesis_scorer.KNOWN_SPEC_TYPES:
        raise ValueError(f"test_spec.type {spec.get('type')!r} is not one of "
                         f"{sorted(hypothesis_scorer.KNOWN_SPEC_TYPES)}")
    if not isinstance(spec.get("params"), dict):
        raise ValueError("test_spec.params must be an object")


def parse_model_output(raw_response: dict) -> dict:
    """Raises ValueError/json.JSONDecodeError on any schema violation -- the caller turns
    that into a logged 'error' ledger row rather than a crash or a fabricated board entry."""
    content = (raw_response.get("message") or {}).get("content", "")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    for key in ("brief", "cards", "wants"):
        if key not in data:
            raise ValueError(f"model output missing required key '{key}'")
    if not isinstance(data["cards"], list):
        raise ValueError("'cards' is not a list")
    for card in data["cards"]:
        if isinstance(card, dict) and "test_spec" in card:
            _validate_test_spec(card["test_spec"])
    return data


def _board_size() -> int:
    return len(station_board.load_board(IDEAS_BOARD_PATH))


def drain_inbox() -> int:
    """Applies every pending station-inbox.jsonl row to the board immediately, then
    archives it -- runs on EVERY fire, yielded or not, since it is a pure file edit
    (no model call, no trading-path write) and J's Kill/Test/Ask clicks should never
    sit stuck for hours behind an RTH yield. Returns the number of rows drained (0
    is the common case and is not logged as an event on its own -- the ledger row
    already records cards_added/board_size for the fire as a whole)."""
    inbox_rows = station_board.read_jsonl(INBOX_PATH)
    if not inbox_rows:
        return 0
    board = station_board.load_board(IDEAS_BOARD_PATH)
    new_board, new_notes = station_board.apply_inbox_actions(board, inbox_rows)
    station_board.write_ideas_board(IDEAS_BOARD_PATH, new_board)
    if new_notes:
        existing = station_board.read_json_or_none(PENDING_NOTES_PATH)
        existing = existing if isinstance(existing, list) else []
        station_board.atomic_write_text(PENDING_NOTES_PATH, json.dumps(existing + new_notes, ensure_ascii=False))
    station_board.append_jsonl(INBOX_PROCESSED_PATH, inbox_rows)
    station_board.atomic_write_text(INBOX_PATH, "")
    return len(inbox_rows)


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:  # noqa: BLE001
        return None


# ---- Sectors + crew-events (2026-09-14 company-roster re-point: C1-C3) ------------------
# Coach's sectors.json (a thin wrapper over sector_rows.build_sector_rows(), owned by a
# different builder and additive-only here) and the crew-events ticker (Chef's verdict
# deltas + Coach's sectors/task-health deltas). Every function below is individually
# fail-open -- see _write_sectors_and_crew_events's own docstring for why.

def _parse_et_stamp(ts: Optional[str]) -> Optional[datetime]:
    """Parses this module's own 'YYYY-MM-DD HH:MM:SS ET' ts_et convention back into a
    UTC-aware datetime for an age/heartbeat comparison against now_utc. None on any
    parse failure -- never a guess. Same DST-safe trick company_audit.py's
    _gt_manager_loop_ledger_cites_number uses (et_offset_hours at the naive instant)."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        naive_et = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S ET")
    except ValueError:
        return None
    offset = et_offset_hours(naive_et.replace(tzinfo=timezone.utc))
    return (naive_et - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def _sectors_summary_line(rows: list) -> str:
    """'<N> lanes -- <g> GREEN * <r> RED (<lane>: <reason>) * <f> frozen' -- the one-line
    headline both sectors.json and the Coach crew-events row carry. The parenthetical
    names the FIRST red lane only (a full list would blow past a ticker-line length; the
    full picture is always in sectors.json's own `rows`)."""
    n = len(rows)
    green = sum(1 for r in rows if r.get("health") == "green")
    red_rows = [r for r in rows if r.get("health") == "red"]
    frozen = sum(1 for r in rows if r.get("health") == "frozen")
    red_part = f" ({red_rows[0].get('lane')}: {str(red_rows[0].get('evidence'))[:80]})" if red_rows else ""
    return f"{n} lanes — {green} GREEN · {len(red_rows)} RED{red_part} · {frozen} frozen"


def _task_health_snapshot(now_utc: datetime, *,
                          registered_tasks_fn: Optional[Callable[[], list]] = None) -> dict:
    """{ts_et, disabled: [Gamma_* task names currently State=Disabled], failed_last_run:
    [], total, source}. Reuses audit_scheduled_tasks._registered_tasks() -- the SAME
    fixed-argv, CREATE_NO_WINDOW PowerShell helper company_audit.py already calls every
    run -- rather than a second ad hoc subprocess call (DRY + already-trusted).

    failed_last_run is deliberately always [] here: LastTaskResult reads 0 on this rig
    even for a real failure (every Gamma_* task launches through a hidden wscript/VBS
    chain that masks the true exit code -- see CLAUDE.md's debugging-discipline note and
    company_audit.py's own AUTONOMOUS-axis comment on the same fact) and per-task log
    parsing across ~190 registered tasks is out of scope for a 30-min ticker fire; the
    honest empty list + a stated reason in `source` beats a fabricated one.

    Fail-open: any enumeration failure (PowerShell/Task Scheduler unavailable, helper
    error) degrades to an empty snapshot with the reason in `source`, never an
    exception."""
    ts_et = et_now(now_utc=now_utc).strftime("%Y-%m-%d %H:%M:%S ET")
    registered_tasks_fn = registered_tasks_fn or _ast._registered_tasks
    try:
        tasks = registered_tasks_fn()
        gamma_tasks = [t for t in tasks if isinstance(t, dict) and str(t.get("name", "")).startswith("Gamma_")]
        disabled = sorted(t["name"] for t in gamma_tasks if t.get("state") == "Disabled")
        return {
            "ts_et": ts_et,
            "disabled": disabled,
            "failed_last_run": [],
            "total": len(gamma_tasks),
            "source": ("audit_scheduled_tasks._registered_tasks() (Get-ScheduledTask via the "
                      "CREATE_NO_WINDOW _list-gamma-tasks-json.ps1 helper); failed_last_run left "
                      "empty -- LastTaskResult reads 0 on this rig even for real failures (hidden "
                      f"VBS launch chain), and per-task log parsing across {len(gamma_tasks)} tasks "
                      "is out of scope for a 30-min ticker fire"),
        }
    except Exception as exc:  # noqa: BLE001 -- fail-open: task_health must never break the Station fire
        return {
            "ts_et": ts_et, "disabled": [], "failed_last_run": [], "total": 0,
            "source": f"unavailable: {type(exc).__name__}: {exc}",
        }


def _format_spec_label(spec: dict) -> str:
    spec_type = spec.get("type", "?")
    params = spec.get("params") or {}
    if spec_type == "size_cap":
        return f"size_cap({params.get('cap', '?')})"
    if spec_type == "exit_shape":
        return f"exit_shape({params.get('shape', '?')})"
    if spec_type == "metric_correlation":
        return f"metric_correlation({params.get('x', '?')}~{params.get('y', 'actual_pnl')})"
    if spec_type == "time_stop_minutes":
        return f"time_stop_minutes({params.get('minutes', '?')})"
    return str(spec_type)


def _format_effect(v, spec_type: str) -> str:
    if v is None:
        return "n/a"
    if spec_type == "metric_correlation":
        return f"r={v:+.3f}"
    return f"{'+' if v >= 0 else ''}${v:,.0f}"


def _format_chef_verdict_line(card: dict, spec: dict, result: dict, status: str, min_n: int) -> str:
    """'Chef: size_cap(3) on BULLISH_RECLAIM_RIDE_THE_RIBBON -- pre +$1,237 (n 148) *
    post n 0/10 -> testing' -- one ticker line summarizing what a scored card's verdict
    now says, for the crew-events row's `line` field."""
    params = spec.get("params") or {}
    spec_type = spec.get("type", "?")
    label = _format_spec_label(spec)
    target = params.get("strategy") or params.get("arm")
    head = f"{label} on {target}" if target else f"{label} — {card.get('title') or card.get('id', '?')}"
    pre = f"pre {_format_effect(result.get('effect_pre'), spec_type)} (n {result.get('n_pre', 0)})"
    post = f"post n {result.get('n_post', 0)}/{min_n}"
    return f"Chef: {head} — {pre} · {post} → {status}"


def _emit_chef_verdict_events(before_board: list, ts_et: str, min_n: int, n_new_rows: int) -> None:
    """Chef's crew-events row(s): one per card actually scored THIS fire, but only when
    something changed since the previous row for that card (new n_post, a status flip,
    or a first verdict) -- hypothesis_scorer.rescore_board() re-scores (and re-appends a
    verdicts-ledger row for) EVERY 'testing' card on EVERY fire even when the underlying
    autopsy data hasn't moved (verified live 2026-09-14: card f5deabe978 got three
    byte-identical n_post=0 verdict rows at 10:21/10:51/11:21 ET), so mirroring the
    ledger 1:1 into the ticker would spam 'nothing happened' every 30 minutes. Diffs the
    board snapshot taken BEFORE score_testing_cards() ran against the verdicts-ledger
    rows it just appended (the last `n_new_rows` lines -- exactly what this fire wrote,
    per score_testing_cards()'s own `ledger_rows_written` count) and the board AFTER.
    Fail-open: a formatting/diff bug here must never break the scorer pass itself."""
    if n_new_rows <= 0:
        return
    try:
        before_by_id = {c.get("id"): c for c in before_board if isinstance(c, dict) and c.get("id")}
        all_verdict_rows = station_board.read_jsonl(VERDICTS_LEDGER_PATH)
        new_rows = all_verdict_rows[-n_new_rows:] if all_verdict_rows else []
        after_board = station_board.load_board(IDEAS_BOARD_PATH)
        after_by_id = {c.get("id"): c for c in after_board if isinstance(c, dict) and c.get("id")}
        for row in new_rows:
            card_id = row.get("card_id")
            if not card_id:
                continue
            before = before_by_id.get(card_id) or {}
            after = after_by_id.get(card_id) or {}
            result = row.get("result") or {}
            is_first = "verdict" not in before
            changed = (is_first or before.get("verdict_n_post") != result.get("n_post")
                      or before.get("status") != after.get("status"))
            if not changed:
                continue
            status = after.get("status") or result.get("verdict", "?")
            line = _format_chef_verdict_line(after or before, row.get("spec") or {}, result, status, min_n)
            crew_events.append({"ts_et": ts_et, "who": "Chef", "kind": "verdict", "to": "Gamma",
                                "line": line, "ref": card_id}, path=CREW_EVENTS_PATH)
    except Exception as exc:  # noqa: BLE001 -- a ticker glitch must never break the scorer pass
        _log(f"crew_events chef verdict row failed (non-fatal): {exc!r}")


def _write_sectors_and_crew_events(ts_et: str, now_utc: datetime, config: dict) -> None:
    """Coach's sectors.json + the crew-events ticker rows it and Chef's scorer feed --
    written on EVERY fire (yielded or not), right next to drain_inbox()/
    score_testing_cards() in run_once(), NEVER inside the LLM branch below it. Fully
    fail-open at every sub-step (hard rule from the build brief: the Station fire must
    never die because sectors/crew-events failed) -- one bad lane, a Task Scheduler
    enumeration failure, or a broken ticker write can each only blank ITS OWN piece,
    never take the others or the fire down with it.

    SYNTHETIC-CLOCK GUARD (2026-09-14, added after a real leak): a caller whose `now_utc`
    is far from actual wall-clock time (the unmistakable signature of a test injecting a
    fixed historical/future clock -- e.g. test_station_yield_unload.py's SUNDAY_EVENING_UTC)
    combined with SECTORS_PATH/CREW_EVENTS_PATH still pointing at the REAL repo path (i.e.
    some caller forgot to monkeypatch them) must never write real state. This is defense
    in depth on top of proper test isolation, not a substitute for it -- see the C34-class
    lesson (a synthetic clock touching real state) this guard closes. A test that DOES
    redirect these paths under tmp_path is unaffected: tmp_path never equals the real
    REPO-derived path, so the guard simply never fires for a properly isolated test."""
    try:
        real_sectors_path = REPO / "automation" / "state" / "station" / "sectors.json"
        real_crew_events_path = REPO / "automation" / "state" / "station" / "crew-events.jsonl"
        clock_drift_s = abs((datetime.now(timezone.utc) - now_utc).total_seconds())
        if clock_drift_s > 900 and (SECTORS_PATH == real_sectors_path or CREW_EVENTS_PATH == real_crew_events_path):
            _log(f"_write_sectors_and_crew_events: synthetic clock + real path -> skipped "
                f"(now_utc={now_utc.isoformat()}, drift={clock_drift_s / 60:.0f}m)")
            return
    except Exception:  # noqa: BLE001 -- the guard itself must never break a real fire
        pass

    try:
        rows = sector_rows.build_sector_rows()
    except Exception as exc:  # noqa: BLE001
        _log(f"sector_rows.build_sector_rows failed (non-fatal): {exc!r}")
        rows = []
    summary_line = _sectors_summary_line(rows)
    task_health = _task_health_snapshot(now_utc)

    old_doc = station_board.read_json_or_none(SECTORS_PATH)
    old_doc = old_doc if isinstance(old_doc, dict) else {}

    doc = {"ts_et": ts_et, "rows": rows, "summary_line": summary_line, "task_health": task_health}
    try:
        station_board.atomic_write_text(SECTORS_PATH, json.dumps(doc, indent=2, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        _log(f"sectors.json write failed (non-fatal): {exc!r}")

    # Coach: sectors ticker row -- only on a real change, or a ~3h heartbeat (SECTORS_HEARTBEAT
    # approximates "every 6th fire" at the 30-min Station cadence without a separate counter).
    try:
        prev = crew_events.last_row(kind="sectors", who="Coach", path=CREW_EVENTS_PATH)
        heartbeat_due = True
        if prev is not None:
            prev_dt = _parse_et_stamp(prev.get("ts_et"))
            heartbeat_due = prev_dt is None or (now_utc - prev_dt) >= SECTORS_HEARTBEAT
        if prev is None or prev.get("line") != summary_line or heartbeat_due:
            crew_events.append({"ts_et": ts_et, "who": "Coach", "kind": "sectors", "to": "Gamma",
                                "line": summary_line, "ref": "automation/state/station/sectors.json"},
                               path=CREW_EVENTS_PATH)
    except Exception as exc:  # noqa: BLE001
        _log(f"crew_events sectors row failed (non-fatal): {exc!r}")

    # Coach: task_health delta row(s) -- only when a Gamma_* task's Disabled-ness flipped
    # since the LAST sectors.json (old_doc, read above before this fire overwrote it).
    try:
        old_disabled = set((old_doc.get("task_health") or {}).get("disabled") or [])
        new_disabled = set(task_health.get("disabled") or [])
        for name in sorted(new_disabled - old_disabled):
            crew_events.append({"ts_et": ts_et, "who": "Coach", "kind": "task_health", "to": "Gamma",
                                "line": f"Coach: {name} went Disabled", "ref": name}, path=CREW_EVENTS_PATH)
        for name in sorted(old_disabled - new_disabled):
            crew_events.append({"ts_et": ts_et, "who": "Coach", "kind": "task_health", "to": "Gamma",
                                "line": f"Coach: {name} came back Ready", "ref": name}, path=CREW_EVENTS_PATH)
    except Exception as exc:  # noqa: BLE001
        _log(f"crew_events task_health row failed (non-fatal): {exc!r}")


# ---- One fire ----

def _ledger_row(ts_et: str, model: str, status: str, reason: str, t0: float, *,
                prompt_tokens=None, gen_tokens=None, cards_added: int = 0) -> dict:
    return {
        "ts_et": ts_et, "model": model, "status": status, "reason": reason,
        "duration_s": round(time.time() - t0, 2),
        "prompt_tokens": prompt_tokens, "gen_tokens": gen_tokens,
        "cards_added": cards_added, "board_size": _board_size(),
    }


def _record_conductor_outcome(*, items_added: int, items_drained: int) -> None:
    """conductor_outcome.record(source='station', ...) at the end of EVERY run_once() path
    (GOAL-GAMMA-STATION item 12) -- so Station fires count in the same autonomy metric every
    other autonomous loop feeds, whether the fire yielded, errored, or produced cards.
    conductor_outcome.record() already never raises on its own (it swallows internally and
    returns None on failure) -- this wrapper only guards against the import/call itself being
    unavailable in some unusual environment, so a broken outcome-metric module can never take
    the Station loop down with it."""
    try:
        conductor_outcome.record(task_id="Gamma_Station", items_added=items_added,
                                 items_drained=items_drained, source="station")
    except Exception as exc:  # noqa: BLE001 -- must never break the Station loop
        _log(f"conductor_outcome.record failed (non-fatal): {exc!r}")


def run_once(*, force: bool = False, now_utc: Optional[datetime] = None) -> dict:
    t0 = time.time()
    now_utc = now_utc or datetime.now(timezone.utc)
    config = load_config()
    model = config.get("model", DEFAULT_CONFIG["model"])
    ts_et = et_now(now_utc=now_utc).strftime("%Y-%m-%d %H:%M:%S ET")

    inbox_rows_drained = drain_inbox()  # every fire, yielded or not -- see drain_inbox()'s own docstring

    # GAMMA-STATION item 12 (2026-09-13): scoring is pure deterministic Python over rows that
    # already exist -- no LLM -- so it runs on EVERY fire (yielded, error, or ok) right after
    # the inbox drain, exactly like drain_inbox() itself ("scoring needs no model", approved
    # plan). score_testing_cards() is a cheap no-op (one read, zero writes) whenever the board
    # has no 'testing' cards -- the common case -- so this never becomes a real cost on a
    # yielded fire.
    min_n = config.get("scorer_min_n", DEFAULT_CONFIG["scorer_min_n"])
    before_board = station_board.load_board(IDEAS_BOARD_PATH)  # snapshot for _emit_chef_verdict_events' diff
    score_summary = station_board.score_testing_cards(
        IDEAS_BOARD_PATH, autopsy_dir=AUTOPSY_DIR, verdicts_path=VERDICTS_LEDGER_PATH,
        settled_path=SETTLED_HYP_PATH, min_n=min_n,
        now_et=et_now(now_utc=now_utc),
    )
    if score_summary.get("testing_cards"):
        _log(f"score_testing_cards: {score_summary}")
    _emit_chef_verdict_events(before_board, ts_et, min_n, score_summary.get("ledger_rows_written", 0))

    # 2026-09-14 company-roster re-point (C1-C3): Coach's sectors.json + the crew-events
    # ticker, right next to the drain/score calls above -- NEVER inside the LLM branch
    # below, so this keeps writing on a yielded/error fire too (the common case: RTH
    # yields 09:30-15:55 ET, but J's "quiet since 09:05" complaint must not recur even
    # then). Wrapped here too, belt-and-suspenders on top of the function's own internal
    # fail-open guards (hard rule: sectors/crew-events must never crash a Station fire).
    try:
        _write_sectors_and_crew_events(ts_et, now_utc, config)
    except Exception as exc:  # noqa: BLE001
        _log(f"_write_sectors_and_crew_events failed (non-fatal): {exc!r}")

    status, reason = decide_action(now_utc, config, force=force)
    if status != "ok":
        row = _ledger_row(ts_et, model, status, reason, t0)
        if reason.startswith("denylisted_process:"):
            row["unloaded"] = _unload_loaded_models()  # J is gaming: give the VRAM back right now
        append_ledger(LEDGER_PATH, row)
        _log(f"{status}: {reason}" + (f" unloaded={row['unloaded']}" if "unloaded" in row else ""))
        _record_conductor_outcome(items_added=0, items_drained=inbox_rows_drained)
        return row

    facts = station_facts.gather_all_facts(config, now_utc=now_utc)
    facts_text = station_facts.render_facts_text(facts)
    pending_notes = station_board.read_json_or_none(PENDING_NOTES_PATH)
    pending_notes = pending_notes if isinstance(pending_notes, list) else []
    notes_text = station_board.render_pending_notes_text(pending_notes)
    if notes_text:
        facts_text = facts_text + "\n\n" + notes_text
    # GAMMA-STATION Slice 1 (2026-09-13): identity capsule first (who Gamma is, what J wants, conduct
    # rules), then this loop's format contract. The chat face loads the same capsule + a prose contract.
    identity_text = _read_text(STATION_PROMPT_PATH.with_name("station-identity.md")) or ""
    station_text = _read_text(STATION_PROMPT_PATH) or DEFAULT_SYSTEM_PROMPT
    system_text = (identity_text + "\n\n" + station_text) if identity_text else station_text

    try:
        raw = call_ollama_chat(model, system_text, facts_text, config["ollama_base_url"],
                               config["num_ctx"], timeout=config.get("model_call_timeout_s", 300))
        parsed = parse_model_output(raw)
    except Exception as exc:  # noqa: BLE001 -- a bad model response is a logged error, not a crash
        row = _ledger_row(ts_et, model, "error", f"model_call_failed: {exc!r}"[:300], t0)
        append_ledger(LEDGER_PATH, row)
        _log(f"error: {row['reason']}")
        _record_conductor_outcome(items_added=0, items_drained=inbox_rows_drained)
        return row

    existing_board = station_board.load_board(IDEAS_BOARD_PATH)
    new_board, added = station_board.merge_new_cards(
        existing_board, parsed.get("cards", []), ts_et=ts_et, model=model,
        similarity_threshold=config.get("dedupe_similarity_threshold", 0.8),
        max_new=config.get("max_new_cards_per_fire", 2), cap=config.get("board_cap", 50),
    )
    station_board.write_ideas_board(IDEAS_BOARD_PATH, new_board)
    station_board.write_brief(BRIEF_PATH, ts_et, model, parsed.get("brief", ""), len(new_board))
    # C3: one crew-events row per brief written -- first line only (the ticker is a
    # headline surface, not the brief's full text, which stays in BRIEF_PATH itself).
    try:
        brief_first_line = next((ln.strip() for ln in (parsed.get("brief", "") or "").splitlines()
                                 if ln.strip()), "(empty brief)")
        crew_events.append({"ts_et": ts_et, "who": "Gamma", "kind": "brief",
                            "line": brief_first_line, "ref": str(BRIEF_PATH)}, path=CREW_EVENTS_PATH)
    except Exception as exc:  # noqa: BLE001 -- a ticker glitch must never break a successful fire
        _log(f"crew_events brief row failed (non-fatal): {exc!r}")
    # Pending-notes bug fix (found by builder #2 reading this file, 2026-09-13): notes_text
    # was folded into every prompt but PENDING_NOTES_PATH was never cleared on success, so
    # J's Test/Ask notes would be re-sent forever. Cleared ONLY here, on the fire that
    # actually delivered them to the model -- a failed/yielded fire (any return above this
    # line) must never lose a note, since it never got read.
    if pending_notes:
        station_board.atomic_write_text(PENDING_NOTES_PATH, json.dumps([], ensure_ascii=False))

    row = _ledger_row(ts_et, model, "ok", "", t0,
                      prompt_tokens=raw.get("prompt_eval_count"), gen_tokens=raw.get("eval_count"),
                      cards_added=added)
    row["board_size"] = len(new_board)
    append_ledger(LEDGER_PATH, row)
    _log(f"ok: cards_added={added} board_size={len(new_board)}")
    _record_conductor_outcome(items_added=added, items_drained=inbox_rows_drained)
    return row


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description="Gamma's Station loop -- local-model idea generator.")
    ap.add_argument("--once", action="store_true", help="run a single fire (the only mode; Task Scheduler owns the cadence)")
    ap.add_argument("--force", action="store_true", help="bypass the RTH/GPU/denylist yield checks for a manual run")
    args = ap.parse_args(argv)
    row = run_once(force=args.force)
    print(json.dumps(row, ensure_ascii=False))
    return 0  # always 0 -- a yield/error is a logged ledger row, never a scheduler alarm


if __name__ == "__main__":
    raise SystemExit(main())
