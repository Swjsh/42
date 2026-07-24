"""twin_gauntlet.py -- B2a: THE TWIN GAUNTLET, the "fix -> live-verified in minutes" GATE.

markdown/planning/TWIN-PROGRAM.md value stream #2: "twin_gauntlet --paths <changed>
forces N real lifecycles through a just-changed code path and diffs vs expected.
Conductor hook: trading-path commits without a gauntlet pass get flagged." Doctrine
rails (same doc, banner): the twin validates MECHANISM, never edge; twin findings
may only propose CODE fixes, never SPY parameters. This module never touches SPY
state, never places a SPY order, and never writes to analysis/recommendations/.

WHAT THIS FILE OWNS (B2, this session): the REQUESTER + POLLER + REPORTER. It does
NOT own forcing a real BTC lifecycle down a path live -- that belongs to the twin's
own scenario scheduler (crypto_twin_scenarios.py / crypto_twin_health.py's 5-min
tick), being built concurrently by a parallel crew (B1) THIS SAME SESSION. To keep
the two crews' work independently shippable, this module never imports
crypto_twin_core/crypto_twin_health/crypto_twin_scenarios AT MODULE IMPORT TIME --
the LIVE queue/poll code path (request_paths/poll_results/pending_requests/
record_path_result) needs none of them at all; only --dry mode lazily imports
crypto_twin_core (read-only: it drives place_entry/manage_positions exactly the way
backtest/tests/test_crypto_twin_core.py already does, never edits that file), and
catches an import failure as a clean DRY-unavailable report instead of crashing --
a defensive choice given B1's crypto_twin_scenarios.py does not exist on disk as of
this commit and crypto_twin_core.py is being actively edited in parallel.

THE QUEUE CONTRACT (v1) -- the two files this module and the twin's tick talk
through. Mirrored in markdown/planning/TWIN-PROGRAM.md's "B2 interfaces" section
(the shared doc comment) so whoever wires B1's scheduler to this has ONE current
copy of the contract, not two that can drift.

  1. automation/state/crypto-twin/gauntlet-queue.jsonl -- WE (this module) write,
     the twin's tick READS. APPEND-ONLY, like every other twin ledger
     (decisions.jsonl, journal.jsonl) -- rows are NEVER rewritten in place. A
     consumer's claim/progress/completion state belongs in path-coverage.json,
     never in a mutated queue row (two processes racing to rewrite the same jsonl
     is exactly the shared-mutable-state hazard this repo's debugging doctrine
     warns about -- see ~/.claude/rules/common/debugging.md "breaks only under
     load or concurrency").

     REQUEST ROW SCHEMA (v1, one row per requested path):
       {
         "request_id":       str,   # "gauntlet-<UTC compact ts>-<path>-<6 hex>"
         "path":              str,   # one of PATH_REGISTRY's keys (see below)
         "n":                 int,   # lifecycles requested
         "requested_at_utc":  str,   # ISO-8601 UTC
         "requested_at_et":   str,   # ISO-8601 ET (human glance)
         "timeout_min":       int,   # this run's honest latency budget
         "status":            "REQUESTED",   # literal; queue rows never change after write
         "source":            "twin_gauntlet",
       }

  2. automation/state/crypto-twin/path-coverage.json -- the twin's scenario
     scheduler WRITES (via record_path_result() below, or its own equivalent),
     WE read. PROPOSED schema (v1 -- B1's scenario scheduler does not exist on
     disk yet; this is the target shape, not a reverse-engineered one):
       {
         "date_et": "YYYY-MM-DD",
         "updated_at_utc": iso8601,
         "paths": {
           "<path_id>": {
             "status": "green" | "red" | "unknown",
             "last_request_id": str | null,   # echoes the REQUEST that produced this result
             "last_updated_utc": iso8601,
             "n_green_today": int,
             "n_total_today": int,
             "last_incident": str | null,     # short human-readable failure description
             "evidence": [ ... ],              # journal.jsonl row(s) or stage trail
           }, ...
         },
       }

  THE ONE-LINE HOOK a future wire-up needs (documented here + TWIN-PROGRAM.md;
  NOT yet called by anything):
      import twin_gauntlet as tg
      for req in tg.pending_requests():        # every REQUESTED row not yet serviced
          ... force `req["path"]`'s lifecycle `req["n"]` times via the twin's REAL
              exit_manager/broker path (crypto_twin_core.place_entry / manage_positions) ...
          tg.record_path_result(req["path"], status="green"/"red",
                                request_id=req["request_id"], evidence=[...])

  HONESTY ABOUT LATENCY: real BTC lifecycles take minutes (a structure break, a
  TP1 touch, a trailing stop -- none of these are instant). LIVE polling therefore
  checks TWO independent sources every `--poll-interval-sec` (default 20s) up to
  `--timeout-min` (default 45): path-coverage.json (if the scheduler is wired) AND
  the twin's own journal.jsonl directly (ground truth of what the broker actually
  did -- works even before path-coverage.json exists). A path that resolves via
  neither source before the timeout is reported FAIL with an explicit "honest
  timeout, not a mechanism failure" note -- never silently treated as a pass.

--dry MODE: never touches the queue or path-coverage.json. Runs the SAME 6
lifecycle scenarios in-process against a small mocked broker (same shape/spirit as
backtest/tests/test_crypto_twin_core.py's `_FakeBroker` -- reused in spirit, not
imported, so this production module has zero coupling to the test tree) driving
the REAL crypto_twin_core.place_entry / manage_positions (imported read-only,
never edited). Instant, deterministic, $0 -- CI-grade. Every dry result is
labeled DRY so it can never be mistaken for a live gauntlet pass. Each scenario
takes ONE injectable "make it fail" knob (a quote, a timestamp, a corrupted state
file) so a test can prove the FAIL path is not vacuous -- see test_twin_gauntlet.py.

PATHS covered (6; the 5 exit-lifecycle branches TWIN-PROGRAM.md's coverage
battery names, PLUS "entry" for the signal->risk_gate->place_entry mechanism --
added per this session's B2b conductor-hook mapping, which names entry files as
their own coverage class ("entry files -> ORGANIC_SIGNAL/entry"), so every
trading-path file the conductor hook can flag maps to a REAL, gauntlet-able path):
    tp1_trail | structure_stop | catastrophe_cap | max_hold |
    restart_open_position | entry

Usage:
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\twin_gauntlet.py ^
        --paths tp1_trail,structure_stop --n 2 --timeout-min 45
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\twin_gauntlet.py ^
        --paths tp1_trail,structure_stop,catastrophe_cap,max_hold,restart_open_position,entry --dry

Exit code: 0 iff EVERY requested path PASSed; 1 otherwise (any FAIL/timeout); 2 on
a bad --paths argument (unknown path id).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

TWIN_STATE = REPO / "automation" / "state" / "crypto-twin"
QUEUE_PATH = TWIN_STATE / "gauntlet-queue.jsonl"
COVERAGE_PATH = TWIN_STATE / "path-coverage.json"
JOURNAL_PATH = TWIN_STATE / "journal.jsonl"
LAST_RESULT_PATH = TWIN_STATE / "gauntlet-last.json"

# --- the path registry -------------------------------------------------------------------
# expected_stages: exit_manager.ExitAction.stage values (automation/state/fleet/exit_manager.py)
# that PROVE this branch fired. terminal_reason/terminal_event cover the two twin-native
# closes exit_manager doesn't own (max-hold flatten guard, entry fill).
PATH_REGISTRY: dict[str, dict] = {
    "tp1_trail": {
        "description": "TP1 partial fill -> ratchet to breakeven -> trailing profit-lock",
        "expected_stages": ("tp1", "trail"),
        "terminal_reason": None,
        "terminal_event": "CLOSED",
    },
    "structure_stop": {
        "description": "position closes via a structure-level break (chart-stop-primary)",
        "expected_stages": ("structure_stop",),
        "terminal_reason": None,
        "terminal_event": "CLOSED",
    },
    "catastrophe_cap": {
        "description": "premium/catastrophe stop caps an adverse move (no structure level in range)",
        "expected_stages": ("premium_stop",),
        "terminal_reason": None,
        "terminal_event": "CLOSED",
    },
    "max_hold": {
        "description": "max_hold_hours flatten backstop fires when no exit_manager stage triggers in time",
        "expected_stages": (),
        "terminal_reason": "max_hold_flatten",
        "terminal_event": "CLOSED",
    },
    "restart_open_position": {
        "description": "a fresh process/tick correctly resumes managing a position already open "
                       "in exit-state.json (state-integrity, not an exit_manager stage)",
        "expected_stages": (),
        "terminal_reason": None,
        "terminal_event": None,  # verified structurally -- see _dry_restart_open_position's docstring
    },
    "entry": {
        "description": "signal -> risk_gate -> place_entry (ORGANIC_SIGNAL) mechanism",
        "expected_stages": (),
        "terminal_reason": None,
        "terminal_event": "FILLED",
    },
}


# ============================================================================================
# LIVE mode: the queue contract (producer) + path-coverage.json (reader/writer helper)
# ============================================================================================

def _read_jsonl(path: Path) -> list[dict]:
    """Fail-open jsonl reader: missing file -> []; a malformed line is skipped, never aborts."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _atomic_write_json(path: Path, data: dict) -> None:
    """Temp-file + os.replace so a crash mid-write can never corrupt the scoreboard
    (mirrors setup/scripts/status_retention.py's _atomic_write)."""
    d = str(path.parent)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _new_request_row(path: str, n: int, timeout_min: int, *,
                     now_utc: Optional[datetime] = None, now_et: Optional[datetime] = None) -> dict:
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_et or et_now()
    request_id = f"gauntlet-{now_utc.strftime('%Y%m%dT%H%M%S')}-{path}-{uuid.uuid4().hex[:6]}"
    return {
        "request_id": request_id, "path": path, "n": n,
        "requested_at_utc": now_utc.isoformat(), "requested_at_et": now_et.isoformat(),
        "timeout_min": timeout_min, "status": "REQUESTED", "source": "twin_gauntlet",
    }


def request_paths(paths: list[str], n: int, timeout_min: int, *, queue_path: Path = QUEUE_PATH,
                  now_utc: Optional[datetime] = None, now_et: Optional[datetime] = None) -> list[dict]:
    """Appends one REQUEST row per path to gauntlet-queue.jsonl (APPEND-ONLY -- see
    module docstring). Returns the rows written so the caller can poll by request_id."""
    rows = [_new_request_row(p, n, timeout_min, now_utc=now_utc, now_et=now_et) for p in paths]
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return rows


def load_coverage(coverage_path: Path = COVERAGE_PATH) -> dict:
    """Fail-open: missing/corrupt path-coverage.json -> {} (never raises)."""
    if not coverage_path.exists():
        return {}
    try:
        return json.loads(coverage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def pending_requests(queue_path: Path = QUEUE_PATH, coverage_path: Path = COVERAGE_PATH) -> list[dict]:
    """THE ONE-LINE HOOK for B1's scenario scheduler (or the reviewer wiring the two
    crews' work together): every REQUESTED row in gauntlet-queue.jsonl whose
    request_id has not yet appeared as any path's `last_request_id` in
    path-coverage.json. See module docstring's "THE ONE-LINE HOOK a future wire-up
    needs"."""
    seen_ids = set()
    coverage = load_coverage(coverage_path)
    for rec in (coverage.get("paths") or {}).values():
        if isinstance(rec, dict) and rec.get("last_request_id"):
            seen_ids.add(rec["last_request_id"])
    return [r for r in _read_jsonl(queue_path)
           if r.get("status") == "REQUESTED" and r.get("request_id") not in seen_ids]


def record_path_result(path: str, *, status: str, request_id: Optional[str] = None,
                       incident: Optional[str] = None, evidence: Optional[list] = None,
                       coverage_path: Path = COVERAGE_PATH, now_utc: Optional[datetime] = None) -> dict:
    """Read-modify-write ONE path's scoreboard entry in path-coverage.json (atomic
    write; creates the file/section if absent). `status` is "green" or "red" (the
    scenario-scheduler's own vocabulary, per the proposed schema). Ready-made for
    B1's consumer (or the reviewer) to call once a requested lifecycle actually
    runs -- see "THE ONE-LINE HOOK" above. Returns the written record."""
    now_utc = now_utc or datetime.now(timezone.utc)
    data = load_coverage(coverage_path)
    if not data:
        data = {"date_et": et_now().date().isoformat(), "paths": {}}
    data.setdefault("paths", {})
    prior = data["paths"].get(path) or {}
    n_total = int(prior.get("n_total_today", 0)) + 1
    n_green = int(prior.get("n_green_today", 0)) + (1 if status == "green" else 0)
    data["paths"][path] = {
        "status": status, "last_request_id": request_id,
        "last_updated_utc": now_utc.isoformat(),
        "n_green_today": n_green, "n_total_today": n_total,
        "last_incident": incident, "evidence": evidence or [],
    }
    data["updated_at_utc"] = now_utc.isoformat()
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(coverage_path, data)
    return data["paths"][path]


def _check_journal_evidence(path: str, since_utc: datetime,
                            journal_path: Path = JOURNAL_PATH) -> Optional[dict]:
    """Independent evidence source: scans the twin's OWN journal.jsonl (ground
    truth of what the broker actually did) for a row AFTER `since_utc` matching
    PATH_REGISTRY[path]'s expected shape. Authoritative even if path-coverage.json
    is never wired (see module docstring's dual-source design). None = no
    matching row observed."""
    spec = PATH_REGISTRY[path]
    for row in _read_jsonl(journal_path):
        ts = row.get("ts_utc")
        if not ts:
            continue
        try:
            row_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if row_dt <= since_utc:
            continue
        if spec["expected_stages"] and row.get("event") in ("MANAGED", "CLOSED") \
                and row.get("stage") in spec["expected_stages"]:
            return row
        if spec["terminal_reason"] and row.get("event") == "CLOSED" \
                and row.get("reason") == spec["terminal_reason"]:
            return row
        if spec["terminal_event"] == "FILLED" and row.get("event") == "FILLED":
            return row
    return None


def poll_results(requests: list[dict], *, timeout_min: int, poll_interval_sec: float = 20.0,
                 sleep_fn=time.sleep, now_fn=lambda: datetime.now(timezone.utc),
                 coverage_path: Path = COVERAGE_PATH, journal_path: Path = JOURNAL_PATH) -> dict:
    """Poll path-coverage.json + journal.jsonl until every requested path resolves
    (PASS/FAIL) or the honest `timeout_min` budget elapses. `sleep_fn`/`now_fn` are
    injectable (mirrors trade_autopsy.py's fetch_bars_cached `sleep_fn` pattern) so
    tests drive this deterministically without a real 45-minute wait."""
    pending = {r["path"]: r for r in requests}
    results: dict[str, dict] = {}
    deadline = now_fn() + timedelta(minutes=timeout_min)
    while pending:
        coverage = load_coverage(coverage_path)
        cov_paths = coverage.get("paths") or {}
        resolved_now = []
        for path, req in pending.items():
            since = datetime.fromisoformat(req["requested_at_utc"])
            cov_rec = cov_paths.get(path)
            if isinstance(cov_rec, dict) and cov_rec.get("last_request_id") == req["request_id"]:
                status = "PASS" if cov_rec.get("status") == "green" else "FAIL"
                results[path] = {
                    "path": path, "mode": "LIVE", "status": status, "source": "path-coverage.json",
                    "detail": cov_rec.get("last_incident") or "path-coverage.json reports green",
                    "evidence": cov_rec.get("evidence") or [],
                }
                resolved_now.append(path)
                continue
            evidence_row = _check_journal_evidence(path, since, journal_path=journal_path)
            if evidence_row is not None:
                results[path] = {
                    "path": path, "mode": "LIVE", "status": "PASS", "source": "journal.jsonl",
                    "detail": "matching stage/event observed directly in journal.jsonl",
                    "evidence": [evidence_row],
                }
                resolved_now.append(path)
        for path in resolved_now:
            del pending[path]
        if not pending:
            break
        if now_fn() >= deadline:
            for path, req in pending.items():
                results[path] = {
                    "path": path, "mode": "LIVE", "status": "FAIL", "source": "timeout",
                    "detail": (f"no gauntlet result observed within {timeout_min} min (checked "
                              f"path-coverage.json + journal.jsonl) -- real BTC lifecycles take "
                              f"minutes; this is an honest timeout, not a proven mechanism failure"),
                    "evidence": [],
                }
            break
        sleep_fn(poll_interval_sec)
    overall = "PASS" if results and all(r["status"] == "PASS" for r in results.values()) else "FAIL"
    return {"mode": "LIVE", "overall": overall, "results": results}


def run_live(paths: list[str], n: int, timeout_min: int, *, poll_interval_sec: float = 20.0,
            sleep_fn=time.sleep, now_fn=lambda: datetime.now(timezone.utc)) -> dict:
    requests = request_paths(paths, n, timeout_min)
    return poll_results(requests, timeout_min=timeout_min, poll_interval_sec=poll_interval_sec,
                        sleep_fn=sleep_fn, now_fn=now_fn)


# ============================================================================================
# --dry mode: in-process mocked-broker fixture lifecycles (instant, $0, CI-grade)
# ============================================================================================

_DRY_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}
_DRY_ENTRY_TS = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class _GauntletFakeBroker:
    """Minimal in-process broker double for --dry mode -- same call shapes as
    backtest/tests/test_crypto_twin_core.py's `_FakeBroker` (reused in spirit,
    NOT imported: production code must not depend on the test tree). Records
    every call; simulates fills/quotes deterministically; no network."""

    def __init__(self, *, order_error: Optional[str] = None):
        self.orders: list[dict] = []
        self.sells: list[dict] = []
        self.closes: list[dict] = []
        self.position_qty = 0.0
        self.quote: Optional[tuple] = None
        self.order_error = order_error   # injectable "make entry fail" knob (see _dry_entry)

    def place_crypto_order(self, creds, *, symbol, side, notional=None, qty=None,
                           order_type="market", limit_price=None, live):
        self.orders.append({"symbol": symbol, "side": side, "notional": notional, "live": live})
        if self.order_error:
            return {"id": None, "status": "rejected", "_error": self.order_error}
        return {"id": "gauntlet-dry-order", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": self.position_qty,
               "filled_avg_price": 64000.0, "order": {}}

    def get_crypto_position_qty(self, creds, symbol="BTC/USD"):
        return self.position_qty

    def get_crypto_quote_hilo(self, symbol="BTC/USD", creds=None):
        return self.quote

    def market_sell_crypto(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        return {"id": f"gauntlet-dry-sell-{len(self.sells)}", "status": "accepted"}

    def close_all_crypto(self, creds, *, symbol="BTC/USD", live):
        self.closes.append({"symbol": symbol, "live": live})
        return {"id": f"gauntlet-dry-close-{len(self.closes)}", "status": "accepted"}


class _patched_broker:
    """Context manager: swaps crypto_twin_core's imported `broker` functions for a
    `_GauntletFakeBroker`'s methods for the duration of the block, always restoring
    the originals -- the production-code equivalent of pytest's `monkeypatch`
    fixture (not available outside a test session)."""
    _NAMES = ("place_crypto_order", "poll_fill", "get_crypto_position_qty",
             "get_crypto_quote_hilo", "market_sell_crypto", "close_all_crypto")

    def __init__(self, ctc, fb: _GauntletFakeBroker):
        self._ctc = ctc
        self._fb = fb
        self._originals: dict = {}

    def __enter__(self):
        for name in self._NAMES:
            self._originals[name] = getattr(self._ctc.broker, name)
            setattr(self._ctc.broker, name, getattr(self._fb, name))
        return self._fb

    def __exit__(self, exc_type, exc, tb):
        for name, orig in self._originals.items():
            setattr(self._ctc.broker, name, orig)
        return False


def _import_crypto_twin_core():
    """Lazy, --dry-only import of crypto_twin_core -- see module docstring for why
    this is never imported at module top level. Raises on genuine failure; callers
    (run_dry) catch and report cleanly rather than crashing the CLI."""
    for p in (REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    import crypto_twin_core as ctc  # noqa: E402
    return ctc


def _read_journal(cfg) -> list[dict]:
    return _read_jsonl(cfg.state_dir / "journal.jsonl")


def _summarize_dry(path_id: str, results: list[dict]) -> dict:
    n_ok = sum(1 for r in results if r["ok"])
    status = "PASS" if results and n_ok == len(results) else "FAIL"
    detail = (f"{n_ok}/{len(results)} dry lifecycle(s) hit the expected mechanism"
             if status == "PASS" else
             f"only {n_ok}/{len(results)} dry lifecycle(s) hit the expected mechanism")
    return {"path": path_id, "mode": "DRY", "status": status, "n": len(results),
           "detail": detail, "evidence": results}


def _dry_cfg(ctc, tmp_dir: str, **overrides):
    return ctc.TwinConfig(state_dir=Path(tmp_dir) / "automation" / "state" / "crypto-twin",
                          notional_usd=200.0, **overrides)


_TP1_TRAIL_QUOTES = ((65000.0, 64950.0), (65500.0, 65450.0), (65100.0, 64800.0))


def _dry_tp1_trail(ctc, n: int, *, quotes=_TP1_TRAIL_QUOTES) -> dict:
    """PASS: TP1 partial fires, the runner rallies (trail ratchets up), then a
    pullback through the trailing floor closes the remainder at stage='trail' --
    the exact sequence
    test_crypto_twin_core.py::test_manage_positions_trailing_runner_ratchets_then_stops
    proves against the REAL exit_manager. `quotes` (the 3-tick best/worst sequence)
    is the injectable "make it fail" knob -- ALL THREE ticks must be overridden
    together (a flat/low sequence that never reaches TP1) to prove the FAIL path
    fires; overriding only tick 1 is NOT sufficient here (tick 2's default quote
    alone clears the TP1 level) -- exactly the trap this whole-sequence knob
    exists to avoid (see test_twin_gauntlet.py)."""
    results = []
    for _ in range(max(1, n)):
        with tempfile.TemporaryDirectory() as td:
            cfg = _dry_cfg(ctc, td)
            fb = _GauntletFakeBroker()
            fb.position_qty = 200.0 / 64000.0
            entered = _DRY_ENTRY_TS
            with _patched_broker(ctc, fb):
                ctc.place_entry(cfg, creds=_DRY_CREDS, side="bull", price=64000.0,
                                trigger_level=63500.0, live=True, now_utc=entered)
                for i, q in enumerate(quotes, start=1):
                    fb.quote = q
                    ctc.manage_positions(cfg, creds=_DRY_CREDS,
                                         now_utc=entered + timedelta(minutes=10 * i), live=True)
            journal = _read_journal(cfg)
            stages_seen = [r.get("stage") for r in journal if r.get("event") in ("MANAGED", "CLOSED")]
            # B6 (TWIN-B6-SIM-FRICTION-CALIBRATION, 2026-07-23): an additive "EXIT_FILLED"
            # telemetry row now trails every real CLOSED/MANAGED row -- CLOSED is no longer
            # guaranteed journal[-1] (see crypto_twin_core._journal_exit_fill). Find the last
            # CLOSED row specifically, matching the same fix applied to
            # test_crypto_twin_core.py::test_manage_positions_trailing_runner_ratchets_then_stops.
            closed_rows = [r for r in journal if r.get("event") == "CLOSED"]
            closed = closed_rows[-1] if closed_rows else {}
            ok = (closed.get("stage") == "trail" and "tp1" in stages_seen)
            results.append({"ok": ok, "stages_seen": stages_seen, "journal_tail": journal[-3:]})
    return _summarize_dry("tp1_trail", results)


def _dry_structure_stop(ctc, n: int, *, last_closed_close=63400.0) -> dict:
    """PASS: a closed 5m bar breaks the trigger level -> SELL_ALL stage='structure_stop'
    (test_manage_positions_structure_stop_closes_all). `last_closed_close` is the
    "make it fail" knob -- override ABOVE the trigger (never breaks) to prove FAIL fires."""
    results = []
    for _ in range(max(1, n)):
        with tempfile.TemporaryDirectory() as td:
            cfg = _dry_cfg(ctc, td)
            fb = _GauntletFakeBroker()
            fb.position_qty = 200.0 / 64000.0
            entered = _DRY_ENTRY_TS
            with _patched_broker(ctc, fb):
                ctc.place_entry(cfg, creds=_DRY_CREDS, side="bull", price=64000.0,
                                trigger_level=63500.0, live=True, now_utc=entered)
                fb.quote = (64100.0, 64050.0)  # no premium-based exit triggered
                ctc.manage_positions(cfg, creds=_DRY_CREDS, now_utc=entered + timedelta(minutes=10),
                                     live=True, last_closed_close=last_closed_close)
            journal = _read_journal(cfg)
            # B6: see _dry_tp1_trail's comment -- CLOSED no longer guaranteed journal[-1].
            closed_rows = [r for r in journal if r.get("event") == "CLOSED"]
            closed = closed_rows[-1] if closed_rows else {}
            ok = closed.get("stage") == "structure_stop"
            results.append({"ok": ok, "journal_tail": journal[-2:]})
    return _summarize_dry("structure_stop", results)


def _dry_catastrophe_cap(ctc, n: int, *, adverse_quote=(62000.0, 61900.0)) -> dict:
    """PASS: no trigger_level at entry -> from_entry demotes to premium mode (the
    twin's tighter -3% fallback); an adverse move crosses it -> SELL_ALL
    stage='premium_stop' (test_manage_positions_catastrophe_cap_when_no_trigger_level).
    `adverse_quote` is the "make it fail" knob -- a mild quote that stays inside
    the band proves FAIL fires."""
    results = []
    for _ in range(max(1, n)):
        with tempfile.TemporaryDirectory() as td:
            cfg = _dry_cfg(ctc, td)
            fb = _GauntletFakeBroker()
            fb.position_qty = 200.0 / 64000.0
            entered = _DRY_ENTRY_TS
            with _patched_broker(ctc, fb):
                ctc.place_entry(cfg, creds=_DRY_CREDS, side="bull", price=64000.0,
                                trigger_level=None, live=True, now_utc=entered)
                fb.quote = adverse_quote
                ctc.manage_positions(cfg, creds=_DRY_CREDS, now_utc=entered + timedelta(minutes=10), live=True)
            journal = _read_journal(cfg)
            # B6: see _dry_tp1_trail's comment -- CLOSED no longer guaranteed journal[-1].
            closed_rows = [r for r in journal if r.get("event") == "CLOSED"]
            closed = closed_rows[-1] if closed_rows else {}
            ok = closed.get("stage") == "premium_stop"
            results.append({"ok": ok, "journal_tail": journal[-2:]})
    return _summarize_dry("catastrophe_cap", results)


def _dry_max_hold(ctc, n: int, *, elapsed_hours=6.05) -> dict:
    """PASS: elapsed time crosses max_hold_hours (6.0) -> MAX_HOLD_FLATTEN
    (test_manage_positions_max_hold_flattens). `elapsed_hours` is the "make it
    fail" knob -- well under the threshold proves FAIL fires (position never flattens)."""
    results = []
    for _ in range(max(1, n)):
        with tempfile.TemporaryDirectory() as td:
            cfg = _dry_cfg(ctc, td, max_hold_hours=6.0)
            fb = _GauntletFakeBroker()
            fb.position_qty = 200.0 / 64000.0
            entered = _DRY_ENTRY_TS
            with _patched_broker(ctc, fb):
                ctc.place_entry(cfg, creds=_DRY_CREDS, side="bull", price=64000.0,
                                trigger_level=None, live=True, now_utc=entered)
                fb.quote = (64100.0, 64050.0)  # neutral -- must not itself be what closes it
                ctc.manage_positions(cfg, creds=_DRY_CREDS,
                                     now_utc=entered + timedelta(hours=elapsed_hours), live=True)
            journal = _read_journal(cfg)
            closed = journal[-1] if journal else {}
            ok = closed.get("event") == "CLOSED" and closed.get("reason") == "max_hold_flatten"
            results.append({"ok": ok, "journal_tail": journal[-2:]})
    return _summarize_dry("max_hold", results)


def _dry_restart_open_position(ctc, n: int, *, corrupt_state=False) -> dict:
    """PASS: a position opened by one 'process' is still correctly managed by a
    FRESH TwinConfig instance sharing the same state_dir (simulates a scheduled-
    task restart mid-position) -- exit-state.json round-trips, the still-open
    broker qty is found again, nothing is fabricated. `corrupt_state` is the
    "make it fail" knob -- a test sets it True to overwrite exit-state.json with
    invalid JSON between 'processes', proving the FAIL path correctly detects a
    position LOST across a restart (crypto_twin_core._load_positions fails open
    to {} on corrupt JSON -- an honest degrade, but the gauntlet must catch it,
    never shrug)."""
    results = []
    for _ in range(max(1, n)):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "automation" / "state" / "crypto-twin"
            cfg1 = ctc.TwinConfig(state_dir=state_dir, notional_usd=200.0)
            fb = _GauntletFakeBroker()
            fb.position_qty = 200.0 / 64000.0
            entered = _DRY_ENTRY_TS
            with _patched_broker(ctc, fb):
                ctc.place_entry(cfg1, creds=_DRY_CREDS, side="bull", price=64000.0,
                                trigger_level=63500.0, live=True, now_utc=entered)
                if corrupt_state:
                    (state_dir / "exit-state.json").write_text("{not valid json", encoding="utf-8")
                # Simulate a restart: a brand-new TwinConfig, same state_dir, no in-process
                # state carried over -- crypto_twin_core keeps no OTHER in-memory state, so a
                # fresh cfg instance IS the whole story.
                cfg2 = ctc.TwinConfig(state_dir=state_dir, notional_usd=200.0)
                fb.quote = (64200.0, 64150.0)  # benign -- nothing should exit on this tick
                ctc.manage_positions(cfg2, creds=_DRY_CREDS, now_utc=entered + timedelta(minutes=15), live=True)
            positions_after = ctc._load_positions(cfg2)
            ok = "BTC/USD" in positions_after
            results.append({"ok": ok, "positions_after": list(positions_after.keys()),
                            "corrupt_state": corrupt_state})
    return _summarize_dry("restart_open_position", results)


def _dry_entry(ctc, n: int, *, order_error: Optional[str] = None) -> dict:
    """PASS: risk_gate allows a healthy account + place_entry registers real
    exit-state (mirrors test_place_entry_registers_structure_mode_exit_state).
    `order_error` is the "make it fail" knob -- a simulated broker rejection
    proves the FAIL path fires (entry never actually registers)."""
    results = []
    for _ in range(max(1, n)):
        with tempfile.TemporaryDirectory() as td:
            cfg = _dry_cfg(ctc, td)
            fb = _GauntletFakeBroker(order_error=order_error)
            fb.position_qty = 200.0 / 64000.0
            rd = ctc._risk_gate_check(cfg, equity=2000.0, sod_equity=2000.0,
                                      kill_switch_tripped=False, position_status="flat",
                                      setup_name="GAUNTLET_DRY_ENTRY")
            with _patched_broker(ctc, fb):
                result = ctc.place_entry(cfg, creds=_DRY_CREDS, side="bull", price=64000.0,
                                         trigger_level=63500.0, live=True, now_utc=_DRY_ENTRY_TS)
            positions = ctc._load_positions(cfg)
            ok = bool(rd.allowed and result.get("placed") and "BTC/USD" in positions)
            results.append({"ok": ok, "risk_gate_allowed": rd.allowed, "placed": result.get("placed")})
    return _summarize_dry("entry", results)


DRY_SCENARIOS = {
    "tp1_trail": _dry_tp1_trail,
    "structure_stop": _dry_structure_stop,
    "catastrophe_cap": _dry_catastrophe_cap,
    "max_hold": _dry_max_hold,
    "restart_open_position": _dry_restart_open_position,
    "entry": _dry_entry,
}


def run_dry(paths: list[str], n: int = 1, overrides: Optional[dict] = None) -> dict:
    """Run every requested path's in-process mocked-broker scenario. `overrides`
    (test-only) maps path -> kwargs merged into that path's scenario function --
    the CLI never passes non-default overrides."""
    overrides = overrides or {}
    try:
        ctc = _import_crypto_twin_core()
    except Exception as e:  # noqa: BLE001 -- report cleanly; see module docstring
        detail = f"crypto_twin_core import failed: {type(e).__name__}: {e}"
        return {
            "mode": "DRY", "overall": "FAIL", "import_error": detail,
            "results": {p: {"path": p, "mode": "DRY", "status": "FAIL", "n": 0, "detail": detail,
                            "evidence": []} for p in paths},
        }
    results = {}
    for p in paths:
        fn = DRY_SCENARIOS[p]
        results[p] = fn(ctc, n, **overrides.get(p, {}))
    overall = "PASS" if results and all(r["status"] == "PASS" for r in results.values()) else "FAIL"
    return {"mode": "DRY", "overall": overall, "results": results}


# ============================================================================================
# Reporting + CLI
# ============================================================================================

def _write_last_result(report: dict, *, path: Optional[Path] = None) -> None:
    """Small '-last.json' snapshot (mirrors trade-autopsy-last.json / prospector-last.json
    / self-check-last.json's established pattern) -- firm_brief.py reads this fail-open
    for the "gauntlet: PASS 20:41" scoreboard line. Never raises (best-effort).

    `path` defaults to None and is resolved to the CURRENT `LAST_RESULT_PATH` module
    global INSIDE the function body (never as a `= LAST_RESULT_PATH` def-time-bound
    default) -- a default parameter is snapshotted ONCE when this function is
    defined, so `monkeypatch.setattr(tg, "LAST_RESULT_PATH", tmp)` would silently
    NOT redirect main()'s no-argument call to this function otherwise (the exact
    bug class already caught once this session in trade_autopsy.py's
    write_twin_hypotheses/append_twin_queue_md -- see that fix's docstring)."""
    if path is None:
        path = LAST_RESULT_PATH
    try:
        payload = {
            "ts_et": et_now().isoformat(), "mode": report["mode"], "overall": report["overall"],
            "paths": {p: r["status"] for p, r in report["results"].items()},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, payload)
    except Exception:  # noqa: BLE001 -- visibility must never itself crash the gauntlet
        pass


def print_report(report: dict) -> None:
    mode_tag = f"[{report['mode']}]"
    if report.get("import_error"):
        print(f"{mode_tag} {report['import_error']}", file=sys.stderr)
    print(f"{mode_tag} twin_gauntlet overall: {report['overall']}")
    for path, r in report["results"].items():
        print(f"{mode_tag} {path}: {r['status']} -- {r.get('detail', '')}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Twin Gauntlet -- force a just-changed code path through N real (or "
                    "--dry mocked) crypto-twin lifecycles and report PASS/FAIL per path.",
        epilog="Known paths: " + ", ".join(PATH_REGISTRY))
    ap.add_argument("--paths", required=True,
                    help="comma-separated path ids, e.g. tp1_trail,structure_stop")
    ap.add_argument("--n", type=int, default=1, help="lifecycles requested per path (default 1)")
    ap.add_argument("--timeout-min", type=int, default=45,
                    help="LIVE mode only -- honest latency budget in minutes (default 45; "
                         "real BTC lifecycles take minutes)")
    ap.add_argument("--dry", action="store_true",
                    help="run mocked-broker fixture lifecycles in-process -- instant, $0, CI-grade")
    ap.add_argument("--poll-interval-sec", type=float, default=20.0, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    unknown = [p for p in paths if p not in PATH_REGISTRY]
    if unknown:
        print(f"twin_gauntlet: unknown path(s) {unknown} -- known: {list(PATH_REGISTRY)}",
             file=sys.stderr)
        return 2

    if args.dry:
        report = run_dry(paths, args.n)
    else:
        print(f"twin_gauntlet: LIVE mode -- requesting {len(paths)} path(s), n={args.n}, "
             f"timeout {args.timeout_min} min. Real BTC lifecycles take minutes; this will "
             f"NOT return instantly.")
        report = run_live(paths, args.n, args.timeout_min, poll_interval_sec=args.poll_interval_sec)

    print_report(report)
    _write_last_result(report)
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
