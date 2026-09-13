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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from et_clock import et_now, et_today_str, is_market_hours  # noqa: E402
import _proc_table  # noqa: E402
import station_board  # noqa: E402
import station_facts  # noqa: E402

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

DEFAULT_CONFIG = {
    "model": "gamma-planner",
    "ollama_base_url": "http://localhost:11434",
    "num_ctx": 32768,
    "model_call_timeout_s": 300,
    "gpu_util_yield_pct": 50,
    "yield_processes": [
        "steam.exe", "epicgameslauncher.exe", "riotclientservices.exe",
        "battle.net.exe", "obs64.exe", "eaconnect_microsoft.exe",
    ],
    "web_scan": False,
    "web_scan_feeds": [],
    "max_new_cards_per_fire": 2,
    "board_cap": 50,
    "dedupe_similarity_threshold": 0.8,
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

        threshold = config.get("gpu_util_yield_pct", 50)
        gpu = gpu_util_fn()
        if gpu is not None and gpu > threshold:
            return "yielded", f"gpu_util {gpu:.0f}% > {threshold}%"

        deny = _denylisted_process(process_table_fn, config.get("yield_processes", []))
        if deny:
            return "yielded", f"denylisted_process:{deny}"

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


# ---- One fire ----

def _ledger_row(ts_et: str, model: str, status: str, reason: str, t0: float, *,
                prompt_tokens=None, gen_tokens=None, cards_added: int = 0) -> dict:
    return {
        "ts_et": ts_et, "model": model, "status": status, "reason": reason,
        "duration_s": round(time.time() - t0, 2),
        "prompt_tokens": prompt_tokens, "gen_tokens": gen_tokens,
        "cards_added": cards_added, "board_size": _board_size(),
    }


def run_once(*, force: bool = False, now_utc: Optional[datetime] = None) -> dict:
    t0 = time.time()
    now_utc = now_utc or datetime.now(timezone.utc)
    config = load_config()
    model = config.get("model", DEFAULT_CONFIG["model"])
    ts_et = et_now(now_utc=now_utc).strftime("%Y-%m-%d %H:%M:%S ET")

    drain_inbox()  # every fire, yielded or not -- see drain_inbox()'s own docstring

    status, reason = decide_action(now_utc, config, force=force)
    if status != "ok":
        row = _ledger_row(ts_et, model, status, reason, t0)
        append_ledger(LEDGER_PATH, row)
        _log(f"{status}: {reason}")
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
        return row

    existing_board = station_board.load_board(IDEAS_BOARD_PATH)
    new_board, added = station_board.merge_new_cards(
        existing_board, parsed.get("cards", []), ts_et=ts_et, model=model,
        similarity_threshold=config.get("dedupe_similarity_threshold", 0.8),
        max_new=config.get("max_new_cards_per_fire", 2), cap=config.get("board_cap", 50),
    )
    station_board.write_ideas_board(IDEAS_BOARD_PATH, new_board)
    station_board.write_brief(BRIEF_PATH, ts_et, model, parsed.get("brief", ""), len(new_board))

    row = _ledger_row(ts_et, model, "ok", "", t0,
                      prompt_tokens=raw.get("prompt_eval_count"), gen_tokens=raw.get("eval_count"),
                      cards_added=added)
    row["board_size"] = len(new_board)
    append_ledger(LEDGER_PATH, row)
    _log(f"ok: cards_added={added} board_size={len(new_board)}")
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
