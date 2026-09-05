"""futures_health.py -- fuse every futures-lane liveness signal into ONE verdict.

WHY THIS EXISTS (2026-08-29): self_check.py -- the project's ONE health surface, per
MAP.md -- had ZERO futures awareness (grep confirmed 0 matches before this file), and
MAP.md itself had zero futures rows. Two silent multi-week outages proved the cost:

  1. The fillsim book-of-record lane (Gamma_FuturesTrader) could not enter for 15
     sessions (2026-08-14 -> present) because a ghost `pending_entry` order sat stuck
     in fillsim-positions.json; sim equity froze at $1,899.83; 60 ENTER_REFUSED rows
     accrued while the EOD digest said GREEN every day.
  2. The tastytrade broker lane placed 0 of 8 armed orders since 2026-08-20 because the
     sandbox intermittently returns 502/ReadTimeout, and the failure went to a
     handler-less logger -- the ledger rows said placed:false with no reason anyone read.

Both were invisible to every existing surface. This is the instrument that retires the
repeated question "are we wired into anything paper trading yet?" (a repeated question is
a missing instrument, not a query -- CLAUDE.md OP-25/rule 7).

Reads EXISTING state only (adds NO new producers, places NO orders, mutates NO scheduled
task). Computes ONE GREEN/YELLOW/RED verdict + a list of human-readable reasons, and writes
automation/state/futures/health.json every fire. $0, pure-Python (+ one PowerShell round
trip for task liveness), fail-open throughout.

FOUR-VALUE SUB-VERDICTS (deliberately different from engine_health.py's 3-value GREEN/
YELLOW/RED-only convention): each of the 6 named checks below reports GREEN / YELLOW / RED
/ UNKNOWN. UNKNOWN is reserved strictly for "a required input is missing/unreadable/
unparseable -- we cannot tell" (fail-open, never a crash). YELLOW is reserved for "we have
real evidence of a non-critical degradation". This distinction matters here specifically
because two of the five inputs (broker-transport.jsonl, and the scheduled-task PowerShell
query) may legitimately be absent/unavailable while the lane is otherwise healthy, and
that must never look identical to "confirmed degraded". The TOP-LEVEL verdict, however, is
ALWAYS exactly one of GREEN/YELLOW/RED (never "UNKNOWN") -- an UNKNOWN sub-check degrades
the fused verdict to at most YELLOW, never invents a RED and never claims a false GREEN.

Checks:
  can_enter        -- fillsim-positions.json: any pending_entry row stuck >30m is the exact
                       ghost-order deadlock signature of outage #1, regardless of whether
                       the underlying bug is still live when this runs.
  fills_recency     -- decisions.jsonl: ENTER_REFUSED across >=2 of the last few sessions is
                       RED (signals fired, entries got refused/blocked repeatedly). A quiet
                       market with zero signals is explicitly NOT a failure (doctrine:
                       "sitting out is a valid day") -- this check never REDs on mere time-
                       since-last-fill alone, only on repeated REFUSAL evidence.
  broker_transport  -- broker-probe.jsonl (+ broker-transport.jsonl if a parallel worker has
                       landed it by the time this runs) classified by the probe's own
                       dry_run_ok flag, NOT by its verdict string alone: futures_broker_probe.py
                       (setup/scripts/futures_broker_probe.py) overloads the verdict label
                       "H1_PERMISSIONS" for BOTH a confirmed broker-side permission rejection
                       (dry_run_ok=True, resp.errors) AND for ANY other caught exception that
                       is not itself an explicit "session not active" message -- including a
                       raw ReadTimeout, which is exactly outage #2's signature (verified live
                       2026-08-29: the 2026-08-27 row reads dry_run_ok=false,
                       error="ReadTimeout: ", verdict="H1_PERMISSIONS"). Trusting the verdict
                       string alone would have missed this. A verdict starting with
                       "SESSION_NOT_ACTIVE" is excluded from the error-rate denominator
                       entirely (CME closed is healthy, not a failure) -- and CME-hours is
                       independently cross-checked via backtest/futures/futures_session.py's
                       is_session_open (imported, never reimplemented; itself sourced from
                       et_clock.py, NEVER zoneinfo/bash TZ -- this box runs Mountain time).
  data_freshness    -- folds in the EXISTING data-freshness.json verdict verbatim (never
                       reimplemented).
  no_stray_exposure -- RED on a recent unattributed closing fill / incomplete flatten-cancel
                       sweep / post-exit not-flat row in trader-broker/anomalies.jsonl
                       (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL, 2026-09-03) -- evidence a
                       no-OCO bracket leg or an unconfirmed flatten left exposure alive past
                       when this lane believed it was done.
  task_liveness     -- State/LastRunTime/LastTaskResult for the 7 live futures tasks via
                       Get-ScheduledTask/Get-ScheduledTaskInfo. CRITICAL distinction: a task
                       Disabled AND present in quiet-mode-restore.json's restore_to_ready list
                       is QUIESCED-BY-DESIGN (quiet_mode.py deliberately holds ~114 non-
                       essential tasks down evenings/weekends, restoring at 23:00 ET) --
                       reporting that as an outage would cry wolf every weekend and train
                       everyone to ignore this instrument, which is exactly how the two
                       outages above survived undetected. Disabled and NOT in that list IS an
                       outage.

Run: backtest/.venv/Scripts/python.exe setup/scripts/futures_health.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT_FILE = STATE / "futures" / "health.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402
from et_clock import et_offset_hours  # noqa: E402

for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)
try:
    from futures.futures_session import is_session_open as _is_cme_session_open  # noqa: E402
    from futures.futures_session import session_phase as _cme_session_phase  # noqa: E402
except Exception:  # noqa: BLE001 -- fail open: never let an import failure silently soften a RED
    def _is_cme_session_open(when_et=None) -> bool:  # type: ignore[misc]
        return True

    def _cme_session_phase(when_et=None) -> str:  # type: ignore[misc]
        return "UNKNOWN"

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ---------------------------------------------------------------------------
# pythonw stdio redirect (OP-27 L41 layer 3, C8) -- only fires under a headless
# pythonw.exe interpreter; a no-op under regular python.exe/pytest.
# ---------------------------------------------------------------------------
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _logs = STATE / "logs"
    _logs.mkdir(parents=True, exist_ok=True)
    _stamp = et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_logs / f"futures-health-{_stamp}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_logs / f"futures-health-{_stamp}.stderr.log", "a", buffering=1, encoding="utf-8")

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
PENDING_ENTRY_STALE_MIN = 30.0  # the exact deadlock signature named by the task
RECENT_SESSIONS_WINDOW = 5      # trading-session window for ENTER_REFUSED aggregation
REFUSED_SESSIONS_RED_THRESHOLD = 2  # >=N distinct sessions with refusals in the window -> RED
DECISIONS_TAIL_BYTES = 500_000  # bounded tail read -- comfortably >5 sessions of 5m-cadence rows
PROBE_RECENT_N = 10
PROBE_ERROR_RATE_RED = 0.5

TASK_NAMES = (
    "Gamma_FuturesTrader",
    "Gamma_FuturesBrokerLane",
    "Gamma_FuturesMirror",
    "Gamma_FuturesEdge3Sim",
    "Gamma_SsrShadow",
    "Gamma_FuturesBrokerProbe",
    "Gamma_FuturesEod2",
)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------
def _chk(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _tail_jsonl(path: Path, max_bytes: int) -> list:
    """Bounded tail-read of a JSONL ledger -> list of parsed dict rows. Skips any line
    that fails to parse (including a truncated first partial line from the seek) rather
    than raising. Missing file / read error -> [] (fail-open)."""
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    rows: list = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _age_min_from_et_str(ts: Any, now_et: datetime) -> Optional[float]:
    """Age in minutes of a naive-ET 'YYYY-MM-DDTHH:MM:SS...' string vs now_et. None if
    unparseable (caller treats that as a fail-open signal, never a crash)."""
    if not isinstance(ts, str) or len(ts) < 19:
        return None
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return (now_et - dt).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# a. can_enter -- the ghost pending_entry deadlock signature (outage #1)
# ---------------------------------------------------------------------------
def check_can_enter(now_et: datetime, positions_path: Optional[Path] = None) -> dict:
    name = "can_enter"
    path = positions_path if positions_path is not None else (
        STATE / "futures" / "trader" / "fillsim-positions.json")
    if not path.exists():
        return _chk(name, "UNKNOWN",
                    "fillsim-positions.json missing -- book lane has not written a position "
                    "file yet")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        return _chk(name, "UNKNOWN", f"fillsim-positions.json unreadable ({type(e).__name__})")
    if not isinstance(data, dict):
        return _chk(name, "UNKNOWN", "fillsim-positions.json is not a JSON object")
    if not data:
        return _chk(name, "GREEN", "flat -- no open/pending instrument rows")

    stuck = []
    rows = []
    for instrument, pos in data.items():
        if not isinstance(pos, dict):
            continue
        status = pos.get("status")
        rows.append(f"{instrument}={status}")
        if status != "pending_entry":
            continue
        ts = pos.get("placed_time_et")
        age = _age_min_from_et_str(ts, now_et)
        if age is None:
            stuck.append(f"{instrument} pending_entry with an unparseable placed_time_et "
                         f"({ts!r}) -- treating as suspect, cannot confirm freshness")
            continue
        if age > PENDING_ENTRY_STALE_MIN:
            stuck.append(
                f"{instrument} pending_entry STUCK {age:.1f}m (>{PENDING_ENTRY_STALE_MIN:.0f}m) "
                f"since {ts} -- GHOST-ORDER DEADLOCK signature (outage #1, 2026-08-14): the "
                f"lane cannot open a new position while this row exists")

    if stuck:
        return _chk(name, "RED", "; ".join(stuck))
    return _chk(name, "GREEN", f"no stuck pending_entry -- rows: {rows}")


# ---------------------------------------------------------------------------
# b. fills_recency -- signals-seen-but-refused, never mere absence of signals
# ---------------------------------------------------------------------------
def check_fills_recency(now_et: datetime, decisions_path: Optional[Path] = None) -> dict:
    name = "fills_recency"
    path = decisions_path if decisions_path is not None else (
        STATE / "futures" / "trader" / "decisions.jsonl")
    if not path.exists():
        return _chk(name, "UNKNOWN",
                    "decisions.jsonl missing -- book lane has not produced any decision "
                    "rows yet")
    rows = _tail_jsonl(path, DECISIONS_TAIL_BYTES)
    dated = [r for r in rows if r.get("ts_et") and r.get("action")]
    if not dated:
        return _chk(name, "UNKNOWN",
                    "decisions.jsonl present but no parseable dated/actioned rows in the "
                    "read window")

    by_date: dict = {}
    for r in dated:
        d = str(r["ts_et"])[:10]
        by_date.setdefault(d, []).append(r)
    session_dates = sorted(by_date)
    recent_dates = session_dates[-RECENT_SESSIONS_WINDOW:]

    refused_sessions = [d for d in recent_dates
                        if any(r.get("action") == "ENTER_REFUSED" for r in by_date[d])]
    n_refused_rows = sum(1 for d in recent_dates for r in by_date[d]
                         if r.get("action") == "ENTER_REFUSED")

    enter_dates = sorted(d for d in session_dates
                         if any(r.get("action") == "ENTER" for r in by_date[d]))
    last_fill = enter_dates[-1] if enter_dates else None
    sessions_since_fill = (
        len([d for d in session_dates if d > last_fill]) if last_fill else len(session_dates))

    detail_core = (
        f"last ENTER {last_fill or 'none in window'} ({sessions_since_fill} session(s) since "
        f"in the read window); {n_refused_rows} ENTER_REFUSED row(s) across "
        f"{len(refused_sessions)}/{len(recent_dates)} recent session(s) {recent_dates}")

    if len(refused_sessions) >= REFUSED_SESSIONS_RED_THRESHOLD:
        return _chk(name, "RED",
                    f"SIGNALS SEEN BUT ENTRY REFUSED repeatedly -- {detail_core} (the engine "
                    f"is seeing setups and failing to fill them -- not the same thing as a "
                    f"quiet no-signal day, which is never a failure)")
    if n_refused_rows:
        return _chk(name, "YELLOW", f"isolated ENTER_REFUSED, not yet a pattern -- {detail_core}")
    return _chk(name, "GREEN",
                f"no ENTER_REFUSED in the recent window -- {detail_core} (zero signals is a "
                f"valid quiet day, not a failure -- doctrine: sitting out is a valid day)")


# ---------------------------------------------------------------------------
# c. broker_transport -- probe dry_run_ok is ground truth, not the verdict label
# ---------------------------------------------------------------------------
def _probe_row_class(row: dict) -> str:
    """'session_closed' | 'error' | 'healthy' | 'unknown'. See module docstring for why this
    reads dry_run_ok rather than trusting the verdict string alone."""
    verdict = str(row.get("verdict", ""))
    if verdict.startswith("SESSION_NOT_ACTIVE"):
        return "session_closed"
    if verdict == "PROBE_FAILED":
        return "error"
    dro = row.get("dry_run_ok")
    if dro is False:
        return "error"
    if dro is True:
        return "healthy"
    return "unknown"


def _summarize_transport_log(path: Path) -> str:
    """Summary of broker-transport.jsonl, written by tastytrade_paper.py's
    `_log_broker_transport` (landed 2026-08-29 alongside this file).

    REAL SCHEMA, confirmed by reading the producer's own output rather than guessed:
      {ts_et, call, outcome, error_class, error_repr, http_status, detail}
    `outcome` is the load-bearing field, and its two values mean OPPOSITE things:
      * "transport_error*" -- we never got an answer (502 / ReadTimeout / connection).
        This is infrastructure, it is retryable, and a run of these is what silently
        killed 8 armed orders 2026-08-20..08-28.
      * "leg_rejected"     -- the broker DID answer and said no. That is a real verdict,
        not an outage, and must never be reported as transport ill-health.
    Unknown shapes still degrade to a row-count note rather than inventing semantics."""
    rows = _tail_jsonl(path, 200_000)
    if not rows:
        return "broker-transport.jsonl present but unreadable/empty"

    outcomes = [str(r.get("outcome") or "") for r in rows if isinstance(r, dict)]
    if not any(outcomes):
        return (f"broker-transport.jsonl present, {len(rows)} row(s), schema not "
                f"recognized (no `outcome` field)")

    transport = sum(1 for o in outcomes if o.startswith("transport_error"))
    rejected = sum(1 for o in outcomes if o == "leg_rejected")
    ambiguous = sum(1 for o in outcomes if o.endswith("ambiguous"))
    newest = rows[-1] if isinstance(rows[-1], dict) else {}
    newest_desc = (f"newest {newest.get('ts_et', '?')} {newest.get('call', '?')}"
                   f"/{newest.get('outcome', '?')}")
    parts = [f"broker-transport.jsonl: {len(rows)} row(s)",
             f"{transport} transport-error", f"{rejected} broker-rejected"]
    if ambiguous:
        parts.append(f"{ambiguous} NOT-RETRIED-AMBIGUOUS (possible unconfirmed order)")
    return ", ".join(parts) + f"; {newest_desc}"


def check_broker_transport(now_et: datetime, transport_path: Optional[Path] = None,
                           probe_path: Optional[Path] = None) -> dict:
    name = "broker_transport"
    t_path = transport_path if transport_path is not None else (
        STATE / "futures" / "broker-transport.jsonl")
    p_path = probe_path if probe_path is not None else (
        STATE / "futures" / "broker-probe.jsonl")

    transport_note = ("broker-transport.jsonl not present yet (its producer had not landed "
                      "as of this build)")
    if t_path.exists():
        transport_note = _summarize_transport_log(t_path)

    try:
        cme_open = bool(_is_cme_session_open(now_et))
        phase = _cme_session_phase(now_et)
    except Exception:  # noqa: BLE001 -- never let the session-hours helper break this check
        cme_open, phase = True, "UNKNOWN"

    if not p_path.exists():
        if not t_path.exists():
            return _chk(name, "UNKNOWN",
                        "neither broker-transport.jsonl nor broker-probe.jsonl exist yet")
        return _chk(name, "UNKNOWN", f"broker-probe.jsonl missing; {transport_note}")

    p_rows = _tail_jsonl(p_path, 200_000)[-PROBE_RECENT_N:]
    if not p_rows:
        return _chk(name, "UNKNOWN",
                    f"broker-probe.jsonl unreadable/empty; {transport_note}")

    classified = [(_probe_row_class(r), r) for r in p_rows]
    errors = sum(1 for c, _ in classified if c == "error")
    healthy = sum(1 for c, _ in classified if c == "healthy")
    closed = sum(1 for c, _ in classified if c == "session_closed")
    newest = p_rows[-1]
    newest_desc = f"{newest.get('at_et', '?')} -> {newest.get('verdict', '?')}"
    cme_desc = f"CME session_phase={phase} (open={cme_open}, per futures_session/et_clock)"
    denom = errors + healthy

    if denom == 0:
        return _chk(name, "GREEN",
                    f"no active-session probes in last {len(p_rows)} row(s) (all excluded as "
                    f"session-closed) -- newest {newest_desc}; {cme_desc}; {transport_note}")

    rate = errors / denom
    detail = (f"{errors}/{denom} recent probe(s) show transport errors (rate {rate:.0%}), "
             f"{closed} excluded as session-closed -- newest {newest_desc}; {cme_desc}; "
             f"{transport_note}")
    if rate > PROBE_ERROR_RATE_RED and denom >= 2:
        if cme_open:
            return _chk(name, "RED", detail)
        return _chk(name, "YELLOW",
                    detail + " -- CME currently CLOSED per et_clock, capped at YELLOW "
                    "(cannot confirm the transport is broken right now vs. simply idle)")
    if errors:
        return _chk(name, "YELLOW", detail)
    return _chk(name, "GREEN", detail)


# ---------------------------------------------------------------------------
# d. data_freshness -- fold in the existing verdict verbatim
# ---------------------------------------------------------------------------
def check_data_freshness(freshness_path: Optional[Path] = None) -> dict:
    name = "data_freshness"
    path = freshness_path if freshness_path is not None else (
        STATE / "futures" / "data-freshness.json")
    if not path.exists():
        return _chk(name, "UNKNOWN", "data-freshness.json missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        return _chk(name, "UNKNOWN", f"data-freshness.json unreadable ({type(e).__name__})")
    if not isinstance(data, dict):
        return _chk(name, "UNKNOWN", "data-freshness.json is not a JSON object")
    verdict = data.get("verdict")
    if verdict not in ("GREEN", "YELLOW", "RED"):
        return _chk(name, "UNKNOWN",
                    f"data-freshness.json has no recognizable verdict ({verdict!r})")
    feeds = data.get("feeds") or {}
    feed_desc = (", ".join(f"{k}={v.get('verdict', '?')}({v.get('age_minutes', '?')}m)"
                           for k, v in feeds.items())
                if isinstance(feeds, dict) else "?")
    return _chk(name, verdict,
                f"folded from data-freshness.json (never reimplemented) verdict={verdict} "
                f"written_at_et={data.get('written_at_et', '?')} feeds: {feed_desc or 'none'}")


# ---------------------------------------------------------------------------
# e. broker_exit_pairing -- FUTURES-BROKER-LANE-NEVER-LOGS-EXITS (filed 2026-09-03)
# ---------------------------------------------------------------------------
OPEN_ENTRY_STALE_HOURS = 20.0  # a tracked entry surviving past its own session's close


def check_broker_exit_pairing(now_et: datetime, decisions_path: Optional[Path] = None,
                              trades_csv_path: Optional[Path] = None,
                              open_entry_path: Optional[Path] = None) -> dict:
    """RED when a real broker ENTER never got a matching journaled EXIT.

    Named the count, not just a boolean -- an ENTER whose order id never appears as an
    `entry:` id in any BROKER-fills trades.csv row's `notes`, AND is not the currently-
    tracked `open-entry.json` (a position that is still genuinely open is not a defect),
    is orphaned: either the writer failed to journal it (the exact bug this check exists
    to catch a regression of) or the position is stuck open past its own session.
    """
    name = "broker_exit_pairing"
    dpath = decisions_path if decisions_path is not None else (
        STATE / "futures" / "trader-broker" / "decisions.jsonl")
    tpath = trades_csv_path if trades_csv_path is not None else (
        REPO / "journal" / "futures" / "trades.csv")
    opath = open_entry_path if open_entry_path is not None else (
        STATE / "futures" / "trader-broker" / "open-entry.json")

    if not dpath.exists():
        return _chk(name, "UNKNOWN",
                    "trader-broker/decisions.jsonl missing -- broker lane has not produced "
                    "any decision rows yet")

    enters = []
    for row in _tail_jsonl(dpath, DECISIONS_TAIL_BYTES):
        if row.get("action") == "ENTER" and row.get("order_ids"):
            enters.append(row)
    if not enters:
        return _chk(name, "GREEN", "no real ENTER rows in the read window -- nothing to pair")

    # Every order id that trades.csv's BROKER rows claim as an "entry:" id, from the
    # free-text `notes` column this writer stamps -- see futures_broker_reconciler.py.
    journaled_entry_ids: set = set()
    if tpath.exists():
        try:
            import csv as _csv

            with tpath.open(newline="", encoding="utf-8") as fh:
                for r in _csv.DictReader(fh):
                    if r.get("fills") != "BROKER":
                        continue
                    notes = r.get("notes", "")
                    m = notes.split("entry:", 1)
                    if len(m) < 2:
                        continue
                    ids_str = m[1].split("],", 1)[0].lstrip("[")
                    for tok in ids_str.split(","):
                        tok = tok.strip()
                        if tok.isdigit():
                            journaled_entry_ids.add(int(tok))
        except (OSError, ValueError):
            return _chk(name, "UNKNOWN", "trades.csv present but unreadable")

    open_entry = None
    if opath.exists():
        try:
            open_entry = json.loads(opath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            open_entry = None
    tracked_ids = set(open_entry.get("order_ids") or []) if open_entry else set()

    orphaned = []
    for row in enters:
        ids = set(row.get("order_ids") or [])
        if ids & journaled_entry_ids:
            continue
        if ids & tracked_ids:
            continue  # genuinely still open and tracked -- not a defect
        orphaned.append(row)

    detail_core = (f"{len(enters)} real ENTER row(s) in window, "
                   f"{len(journaled_entry_ids)} journaled BROKER entry id(s), "
                   f"open-entry.json {'present' if open_entry else 'absent'}")

    if orphaned:
        rows_desc = "; ".join(f"{r['ts_et']} order_ids={r['order_ids']}" for r in orphaned)
        return _chk(name, "RED",
                    f"{len(orphaned)} ENTER(s) with NO matching journaled EXIT and not the "
                    f"currently-tracked open position -- {rows_desc} ({detail_core})")

    if open_entry:
        try:
            entry_time = datetime.fromisoformat(open_entry.get("entry_time_et", ""))
            age_hr = (now_et.replace(tzinfo=None) - entry_time).total_seconds() / 3600.0
        except (TypeError, ValueError):
            age_hr = None
        if age_hr is not None and age_hr > OPEN_ENTRY_STALE_HOURS:
            return _chk(name, "RED",
                        f"open-entry.json has tracked entry {open_entry.get('entry_time_et')} "
                        f"unclosed for {age_hr:.1f}h (> {OPEN_ENTRY_STALE_HOURS:.0f}h) -- "
                        f"stuck past its own session, the reconciler never closed it out "
                        f"({detail_core})")

    return _chk(name, "GREEN", f"every ENTER paired to a journaled exit -- {detail_core}")


# ---------------------------------------------------------------------------
# f. no_stray_exposure -- FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL (filed 2026-09-03)
# ---------------------------------------------------------------------------
ANOMALY_TAIL_BYTES = 200_000
# The two events that mean a resting leg (or an unconfirmed flatten sweep) actually let
# exposure survive an exit -- NOT `sibling_leg_cancelled`, which is the safety net WORKING
# as designed and is informational, never a failure.
STRAY_EXPOSURE_RED_EVENTS = {"unattributed_closing_fill", "flatten_cancel_incomplete",
                             "post_exit_not_flat"}
ANOMALY_LOOKBACK_SESSIONS = RECENT_SESSIONS_WINDOW  # reuse fills_recency's own window


def _anomaly_event_date_et(row: dict) -> Optional[str]:
    """The ET calendar date the underlying broker EVENT actually happened on --
    NOT the date the reconciler script happened to be running when it journaled the
    row. `at_et` is the append-time timestamp; a backfill/catch-up run (e.g. the
    reconciler's `get_recent_fills(days_back=3)` sweep) can journal several real
    sessions' worth of stale fills in one run, all sharing the SAME `at_et` minute --
    that would otherwise undercount `no_stray_exposure`'s own "N session(s)" figure
    (filed 2026-09-05 differential: 8 rows from 2026-09-01 AND 2026-09-02 fills were
    all stamped at_et=2026-09-03T00:43, reporting as "1 session" when 2 real sessions
    were actually affected). Prefer the row's own `fill.filled_at` (UTC, from the
    broker) when present; fall back to `at_et` for anomaly kinds with no fill payload
    (flatten_cancel_incomplete, post_exit_not_flat, sibling_leg_cancelled)."""
    filled_at = ((row.get("fill") or {}).get("filled_at")
                 if isinstance(row.get("fill"), dict) else None)
    if filled_at:
        try:
            dt_utc = datetime.fromisoformat(str(filled_at))
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            offset = et_offset_hours(dt_utc.astimezone(timezone.utc))
            dt_et = dt_utc.astimezone(timezone.utc) + timedelta(hours=offset)
            return dt_et.date().isoformat()
        except (TypeError, ValueError):
            pass
    at_et = row.get("at_et")
    return str(at_et)[:10] if at_et else None


def check_no_stray_exposure(now_et: datetime, anomalies_path: Optional[Path] = None) -> dict:
    """RED on any recent unattributed closing fill, incomplete flatten-cancel sweep, or
    post-exit not-flat assertion -- all three are evidence a bracket leg (no native OCO --
    see futures_broker_reconciler.py) or a flatten left the account exposed after this lane
    believed it was done. Read-only against anomalies.jsonl (written by
    futures_broker_reconciler.py / futures_trader_core.py); this check adds no producer of
    its own."""
    name = "no_stray_exposure"
    path = anomalies_path if anomalies_path is not None else (
        STATE / "futures" / "trader-broker" / "anomalies.jsonl")
    if not path.exists():
        return _chk(name, "GREEN", "anomalies.jsonl absent -- nothing logged yet")
    rows = _tail_jsonl(path, ANOMALY_TAIL_BYTES)
    if not rows:
        return _chk(name, "UNKNOWN", "anomalies.jsonl present but unreadable/empty")

    dated = [r for r in rows if r.get("at_et")]
    if not dated:
        return _chk(name, "UNKNOWN",
                    "anomalies.jsonl present but no parseable dated rows")
    by_date: dict = {}
    for r in dated:
        d = _anomaly_event_date_et(r) or str(r["at_et"])[:10]
        by_date.setdefault(d, []).append(r)
    recent_dates = sorted(by_date)[-ANOMALY_LOOKBACK_SESSIONS:]

    hits = [r for d in recent_dates for r in by_date[d]
           if r.get("event") in STRAY_EXPOSURE_RED_EVENTS]
    if hits:
        desc = "; ".join(f"{r.get('at_et')} {r.get('event')} {r.get('symbol', '')}"
                         for r in hits[-8:])
        return _chk(name, "RED",
                    f"{len(hits)} stray-exposure anomaly row(s) in the last "
                    f"{len(recent_dates)} session(s) with anomaly rows -- {desc}")
    return _chk(name, "GREEN",
                f"no unattributed closing fills / incomplete flatten sweeps / post-exit "
                f"not-flat rows in the last {len(recent_dates)} session(s) with anomaly "
                f"rows ({len(dated)} total row(s) read)")


# ---------------------------------------------------------------------------
# g. task_liveness -- Disabled-by-quiet-mode must never read as an outage
# ---------------------------------------------------------------------------
def _default_query_tasks(names: "tuple") -> "list | None":
    """Real Get-ScheduledTask + Get-ScheduledTaskInfo query, one PowerShell round trip for
    the whole roster. Returns None on TOTAL failure (PowerShell unreachable / non-zero exit /
    unparseable output) -- caller reports UNKNOWN. A single task's own lookup failure (not
    registered yet) still returns a row with Error set so one missing task never takes down
    the whole batch (fail-open)."""
    quoted = ",".join("'" + n.replace("'", "''") + "'" for n in names)
    # NOTE: `foreach (...) {...} | ConvertTo-Json` is INVALID PowerShell 5.1 syntax --
    # `foreach` is a statement, not a pipeline expression, and piping its output directly
    # raises "An empty pipe element is not allowed" (verified live 2026-08-29 debugging this
    # exact line: rc=1, that literal parser error, nothing captured). The fix is the standard
    # PS idiom: capture the loop's output into a variable, THEN pipe the variable.
    script = (
        "$names = @(" + quoted + "); "
        "$result = foreach ($n in $names) { "
        "  try { "
        "    $t = Get-ScheduledTask -TaskName $n -ErrorAction Stop; "
        "    $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop; "
        "    [PSCustomObject]@{ TaskName=$n; State=$t.State.ToString(); "
        "      LastRunTime=$i.LastRunTime.ToString('o'); LastTaskResult=$i.LastTaskResult; "
        "      Error=$null } "
        "  } catch { "
        "    [PSCustomObject]@{ TaskName=$n; State=$null; LastRunTime=$null; "
        "      LastTaskResult=$null; Error=$_.Exception.Message } "
        "  } "
        "}; $result | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001 -- subprocess itself failing to launch -> unavailable
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None
    return data


def check_task_liveness(task_names: "tuple" = TASK_NAMES,
                        quiet_restore_path: Optional[Path] = None,
                        query: Optional[Callable] = None) -> dict:
    name = "task_liveness"
    q = query or _default_query_tasks
    try:
        rows = q(task_names)
    except Exception as e:  # noqa: BLE001 -- the query itself must never crash the producer
        return _chk(name, "UNKNOWN", f"scheduled-task query raised ({type(e).__name__})")
    if rows is None:
        return _chk(name, "UNKNOWN",
                    "scheduled-task query unavailable (PowerShell unreachable, non-zero "
                    "exit, or unparseable output)")

    r_path = quiet_restore_path if quiet_restore_path is not None else (
        STATE / "quiet-mode-restore.json")
    quiesced: set = set()
    try:
        if r_path.exists():
            qd = json.loads(r_path.read_text(encoding="utf-8"))
            quiesced = set(qd.get("restore_to_ready") or [])
    except Exception:  # noqa: BLE001 -- unreadable restore list -> "nothing known-quiesced"
        pass

    by_name = {str(r.get("TaskName")): r for r in rows if isinstance(r, dict) and r.get("TaskName")}
    lines = []
    outages = []
    for tname in task_names:
        row = by_name.get(tname)
        if row is None or row.get("Error"):
            err = row.get("Error") if row else "no row returned"
            lines.append(f"{tname}: not found/unqueryable ({err})")
            continue
        state = row.get("State")
        last_run = row.get("LastRunTime")
        last_result = row.get("LastTaskResult")
        if state == "Disabled":
            if tname in quiesced:
                lines.append(f"{tname}: Disabled -- QUIESCED-BY-DESIGN (quiet_mode "
                             f"restore list; not an outage)")
            else:
                outages.append(tname)
                lines.append(f"{tname}: Disabled and NOT in quiet-mode-restore.json -- "
                             f"OUTAGE (last_run={last_run} last_result={last_result})")
        else:
            lines.append(f"{tname}: {state} last_run={last_run} last_result={last_result}")

    detail = "; ".join(lines)
    if outages:
        return _chk(name, "RED",
                    f"{len(outages)} task(s) disabled with no quiesce record: {outages} -- "
                    f"{detail}")
    return _chk(name, "GREEN", detail)


# ---------------------------------------------------------------------------
# Fusion + report
# ---------------------------------------------------------------------------
_SEVERITY = {"GREEN": 0, "UNKNOWN": 1, "YELLOW": 1, "RED": 2}
_VERDICT_FOR_SEVERITY = {0: "GREEN", 1: "YELLOW", 2: "RED"}


def build_report(now_et: Optional[datetime] = None) -> dict:
    now_utc = datetime.now(timezone.utc)
    et = now_et if now_et is not None else et_now()

    checks = [
        check_can_enter(et),
        check_fills_recency(et),
        check_broker_transport(et),
        check_data_freshness(),
        check_broker_exit_pairing(et),
        check_no_stray_exposure(et),
        check_task_liveness(),
    ]
    worst = max((_SEVERITY.get(c["status"], 1) for c in checks), default=0)
    verdict = _VERDICT_FOR_SEVERITY[worst]
    reasons = [f"[{c['status']}] {c['name']}: {c['detail']}" for c in checks
              if c["status"] != "GREEN"]

    return {
        "checked_at_et": et.strftime("%Y-%m-%d %H:%M:%S"),
        "checked_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "checks": checks,
        "reasons": reasons,
    }


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _print_summary(report: dict) -> None:
    print(f"[futures_health] verdict={report['verdict']} at {report['checked_at_et']} ET")
    for c in report["checks"]:
        print(f"  [{c['status']}] {c['name']}: {c['detail']}")


def main() -> int:
    try:
        report = build_report()
        _atomic_write(OUT_FILE, report)
    except Exception as e:  # noqa: BLE001 -- fail-open producer, never raise into the scheduler
        print(f"[futures_health] ERROR (fail-open, nothing written): {type(e).__name__}: {e}",
              file=sys.stderr)
        return 0
    _print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
