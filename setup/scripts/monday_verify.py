"""monday_verify.py -- WEEKEND-TWELVE Next-Twelve #6: ONE scripted, mechanical sweep that
converts five pending "MONDAY-VERIFY" checklist lines (scattered as prose in STATUS.md,
where they would get half-checked or forgotten) into a verified GREEN/YELLOW/RED/
NOT_EXERCISED line each, plus a sixth item (WS1's Monday-preview vs actuals diff).

THE SIX ITEMS (each read from its own MONDAY-VERIFY note in STATUS.md / lane docs before
this was built -- see the module-level constants below for the exact frozen baselines):
  1. WS7 Live Watch      -- setup/scripts/live_watch.py, Gamma_LiveWatch. Did it fire every
                             minute during RTH, and on the first real position did
                             live-watch.json populate every required field?
  2. WS6 Regime stamp    -- Gamma_RegimeStamp 08:22 ET. Did the 08:30 bias file carry
                             regime_context from the first ORGANIC (scheduled, not manual)
                             fire?
  3. WS3 Level hysteresis -- refresh_levels_intraday.py. Quantifies live flicker (per-level
                             appear/disappear transitions across the day's core ticks) vs
                             Friday 2026-07-31's PRE-FIX baseline (743.25: 331/386 ticks,
                             14 flips); reports hysteresis_held counts from the level-refresh
                             log.
  4. WS11 Core recency   -- backtest/autoresearch/core_strategy_recency.py. Re-reads
                             core-strategy-recency.json after the session: is n growing, did
                             the bear/bull verdict move off the frozen 2026-08-01 baseline
                             (bear RED n=10 -$60.90/tr, bull UNDERPOWERED n=1)?
  5. Theta cockpit       -- setup/scripts/theta_clock.py, Gamma_ThetaClock. Did it fire
                             through the open, and on a real fill did
                             theta_per_contract_per_day_source stay the closed-form estimate
                             (29/29 real entries historically -- broker greeks snapshot has
                             always returned {}) or finally flip to 'broker_snapshot'?
  6. WS1 preview diff    -- analysis/deep-research/MONDAY-PREVIEW-2026-08-03.md (+ its JSON
                             sidecar) predicted per-arm Monday behavior on a Friday-like tape.
                             Diffs the prediction against the day's real entries/config state
                             -- "a preview nobody scores is theater."

DESIGN RULES (C7 -- silent success is failure):
  * Every check states EXPECTED vs OBSERVED with REAL numbers, never a bare pass/fail.
  * A check whose PRECONDITION never occurred (no RTH ticks that day, no real fill, the
    preview's own target date hasn't arrived yet) reports NOT_EXERCISED, never GREEN --
    a check that passes because nothing happened is the silent-success failure class this
    repo keeps hitting.
  * NEVER blocks, NEVER kills, NEVER auto-corrects anything. Pure report. Every check is
    wrapped so ONE failing check can never sink the other five (fail-open, always exits 0).
  * Sub-claims within one item combine via "worse wins" severity (RED > YELLOW >
    NOT_EXERCISED > GREEN) -- e.g. WS7 bundles "did it fire on cadence" (always testable on
    an RTH day) with "did fields populate on the first real fill" (only testable when a fill
    happened); a healthy cadence with no fill reports NOT_EXERCISED, not GREEN, because the
    item's headline claim was never exercised.

OUTPUTS: automation/state/monday-verify.json (full machine-readable detail) +
one prepended dated block on automation/overnight/STATUS.md (newest-first convention, see
setup/scripts/status_retention.py's `## [` entry-boundary split) + a loud, transition-only
line under STATUS.md's "## Known broken" for any item newly RED this run (byte-for-byte the
same pattern as setup/guard_runner_slow.py::_flag_status_md /
backtest/autoresearch/gate_expiry_check.py::flag_status_md).

Run on demand:
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\monday_verify.py [--date YYYY-MM-DD]
                                                                          [--dry-run]
Scheduled: Gamma_MondayVerify, daily post-close (16:15 ET / 14:15 MT), Mon-Fri. Registered
via setup/install-monday-verify.ps1 (wscript -> run_exe_hidden.vbs -> backtest venv pythonw,
OP-27 headless stdio redirect below, header copied verbatim from setup/guard_runner_slow.py).

Guard: backtest/tests/test_monday_verify_2026_08_01.py.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, copied verbatim from
# setup/guard_runner_slow.py -- convention for anything a pythonw scheduled chain can
# import/run; this file lives in setup/scripts/ (same depth as live_watch.py/theta_clock.py)
# so it uses their parents[2] index, not guard_runner_slow.py's own parents[1] -- adapted
# intentionally per that file's own documented C9-anchor-to-__file__ discipline.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "monday-verify.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "monday-verify.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from et_clock import et_now, et_offset_hours  # noqa: E402

# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
# CREATE_NO_WINDOW: the backtest-venv python spawned below is console-subsystem, which
# flashes a console on J's desktop without the flag (2026-08-09 popup sweep).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

STATE = REPO / "automation" / "state"
FLEET_DIR = STATE / "fleet"
LOGS_DIR = STATE / "logs"
THETA_DIR = STATE / "theta-clock"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"

OUT_JSON = STATE / "monday-verify.json"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
LIVE_WATCH_JSON = STATE / "live-watch.json"
LIVE_WATCH_LOG = LOGS_DIR / "live-watch.stdout.log"
REGIME_STAMP_JSON = STATE / "regime-stamp.json"
TODAY_BIAS_JSON = STATE / "today-bias.json"
CORE_RECENCY_JSON = STATE / "core-strategy-recency.json"
CORE_RECENCY_SCRIPT = REPO / "backtest" / "autoresearch" / "core_strategy_recency.py"
BACKTEST_VENV_PY = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
THETA_SNAPSHOT_JSON = STATE / "theta-clock.json"
AGGRESSIVE_PARAMS_JSON = STATE / "aggressive" / "params.json"
WS1_PREVIEW_JSON = REPO / "analysis" / "deep-research" / "monday-preview-scrimmage-2026-08-03.json"
WS1_PREVIEW_MD = REPO / "analysis" / "deep-research" / "MONDAY-PREVIEW-2026-08-03.md"

FLEET_ARM_IDS = ("safe-3", "risky-1", "risky-3")
CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
ALL_SPY_ARMS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")

# core-decisions.jsonl accumulates across the WHOLE project lifetime (33MB+ observed
# 2026-08-01) -- tail-bounded read. 4MB comfortably covers several trading days at the
# observed ~1MB/day accrual rate (386 ticks x 2 accounts), never a full-file read.
CORE_TAIL_BYTES = 4 * 1024 * 1024

# --------------------------------------------------------------------------- #
# verdict vocabulary
# --------------------------------------------------------------------------- #
GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"
NOT_EXERCISED = "NOT_EXERCISED"
_SEVERITY = {RED: 3, YELLOW: 2, NOT_EXERCISED: 1, GREEN: 0}


def _combine(*verdicts: str) -> str:
    """'Worse wins'. RED > YELLOW > NOT_EXERCISED > GREEN -- a healthy cadence combined with
    an un-exercised headline claim reports NOT_EXERCISED, never GREEN (C7)."""
    return max(verdicts, key=lambda v: _SEVERITY[v])


# Friday 2026-07-31 PRE-FIX baseline (analysis/deep-research/LEVEL-FLICKER-FIX-2026-08-01.md
# + .json -- the worst-case row in that report's per-level table).
FRIDAY_BASELINE_DATE = "2026-07-31"
FRIDAY_WORST_LEVEL = "743.25"
FRIDAY_WORST_PRESENT = 331
FRIDAY_WORST_TOTAL = 386
FRIDAY_WORST_FLIPS = 14

# WS11 frozen baseline -- verbatim from automation/state/core-strategy-recency.json as
# written 2026-08-01 (WS11 first standing run; matches WEEKEND-TWELVE-2026-08-01.md and the
# STATUS.md "## Known broken" GATE-EXPIRY RED line for core_strategy_bear).
WS11_BASELINE = {
    "run_date": "2026-08-01",
    "window_end": "2026-07-31",
    "bear": {"verdict": "RED", "n": 10, "exp_per_trade": -60.90},
    "bull": {"verdict": "UNDERPOWERED", "n": 1, "exp_per_trade": -295.00},
}

# The REAL field value (verified against setup/scripts/theta_clock.py:284-294) -- the task
# brief's "closed_form_est" is a paraphrase, not the literal string theta_clock.py writes.
THETA_SOURCE_HISTORICAL_EST = "sqrt_time_decay_model_est"

EXPECTED_LIVE_WATCH_FIRES = 405   # 09:25-16:10 ET, ~1/min (install-live-watch.ps1)
EXPECTED_THETA_FIRES = 390        # 09:30-16:00 ET, ~1/min (install-theta-clock.ps1)

WS1_TARGET_DATE = "2026-08-03"


# --------------------------------------------------------------------------- #
# generic IO helpers (fail-open everywhere -- this script must never raise)
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _decode_bytes(data: bytes) -> str:
    """Decode raw file bytes, sniffing a UTF-16 BOM first. DISCOVERED BUILDING THIS SCRIPT:
    automation/state/logs/level-refresh-*.log is written by run-level-refresh.ps1's
    PowerShell `*>> $log` redirect, which on this box (PS 5.1) emits UTF-16LE WITH a BOM --
    unlike every other log/ledger in this repo (plain UTF-8, no BOM). A bare .decode('utf-8')
    on that file raises UnicodeDecodeError at byte 0 (0xFF). Fail-open to utf-8/replace for
    the common case (every other file this script reads)."""
    if data[:2] == b"\xff\xfe":
        return data[2:].decode("utf-16-le", errors="replace")  # strip BOM -- utf-16-le codec
    if data[:2] == b"\xfe\xff":                                 # does NOT auto-strip it (unlike 'utf-16')
        return data[2:].decode("utf-16-be", errors="replace")
    return data.decode("utf-8", errors="replace")


def _read_text(path: Path) -> str:
    try:
        return _decode_bytes(path.read_bytes())
    except OSError:
        return ""


def _read_tail_text(path: Path, max_bytes: int) -> str:
    """Last max_bytes of a file, decoded fail-open. Mirrors live_watch.py's own
    `_tail_lines` idiom (same file, same convention) -- never a full read of a huge ledger.
    UTF-16 BOM sniffed via _decode_bytes; callers of this tail-bounded reader only ever see
    plain-UTF-8 files today (CORE_DECISIONS, the live-watch log) -- the byte-seek's "drop the
    partial first line" is a UTF-8-only precision guarantee, disclosed not silently assumed."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # drop the partial first line
            data = f.read()
        return _decode_bytes(data)
    except OSError:
        return ""


def _iter_concat_json(text: str) -> list:
    """Parse a stream of CONCATENATED (possibly pretty-printed) JSON documents, e.g.
    automation/state/logs/level-refresh-*.log, which is `print(json.dumps(out, indent=2))`
    appended every ~5 min by run-level-refresh.ps1's `*>> $log`. Resyncs to the next '{' on
    a decode error instead of aborting -- one malformed run must never hide every other run
    that day."""
    dec = json.JSONDecoder()
    idx, n = 0, len(text)
    out = []
    while idx < n:
        while idx < n and text[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = dec.raw_decode(text, idx)
        except json.JSONDecodeError:
            nxt = text.find("{", idx + 1)
            if nxt == -1:
                break
            idx = nxt
            continue
        out.append(obj)
        idx = end
    return out


def _is_weekday(date_str: str) -> bool:
    try:
        return dt.date.fromisoformat(date_str).weekday() < 5
    except ValueError:
        return False


def _now_et_str() -> str:
    try:
        return et_now().strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _file_mtime_et_date(path: Path) -> str | None:
    """The ET calendar date a file was last written, via its OS mtime -- used to decide
    whether live-watch.stdout.log's undated print lines belong to the date being checked
    (the log has no per-line date; see _scan_live_watch_log's docstring)."""
    try:
        m = path.stat().st_mtime
    except OSError:
        return None
    try:
        u = dt.datetime.fromtimestamp(m, tz=dt.timezone.utc)
        off = et_offset_hours(u)
        return (u + dt.timedelta(hours=off)).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _finish(id_: str, name: str, verdict: str, expected: str, observed: str, detail: dict) -> dict:
    return {"id": id_, "name": name, "verdict": verdict, "expected": expected,
            "observed": observed, "detail": detail}


# --------------------------------------------------------------------------- #
# shared domain helpers (ledger reads, reused across checks)
# --------------------------------------------------------------------------- #
def _load_core_rows_for_date(date_str: str, path: Path | None = None,
                              tail_bytes: int | None = None) -> list[dict]:
    """core-decisions.jsonl rows (BOTH safe+bold accounts) dated date_str, oldest-first,
    REAL LIVE TICKS ONLY (armed is True). DISCOVERED BUILDING THIS SCRIPT (this exact dry
    run, Saturday 2026-08-01): off-hours diagnostic/manual heartbeat calls also log to this
    ledger with armed=False (6 such rows found tonight, ts 13:02/14:23/14:28, verdict
    HOLD/SKIP_STRUCTURE_VETO) -- an unfiltered read would have misread a diagnostic ping as
    a real RTH session and produced an artifactual GREEN/RED instead of NOT_EXERCISED. A
    real trading day carries armed=True on EVERY row including plain HOLDs (386/386 verified
    on Friday 2026-07-31's safe ledger) -- the SAME filter gate_expiry_check.load_decision_rows
    already applies for the identical reason ("excludes the off-hours diagnostic/gym-harness
    calls... polluting fire counts").

    path/tail_bytes default to the CURRENT module globals, resolved at CALL time (not
    def-time) -- so callers that never pass an override (e.g. _entries_for_date) still see a
    monkeypatched CORE_DECISIONS in tests, matching every other check's late-bound path read."""
    path = CORE_DECISIONS if path is None else path
    tail_bytes = CORE_TAIL_BYTES if tail_bytes is None else tail_bytes
    text = _read_tail_text(path, tail_bytes)
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or date_str not in line:
            continue
        try:
            r = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if str(r.get("ts_et") or "").startswith(date_str) and r.get("armed") is True:
            rows.append(r)
    rows.sort(key=lambda r: r.get("ts_et", ""))
    return rows


def _load_fleet_rows_for_date(arm_id: str, date_str: str) -> list[dict]:
    """One fleet arm's decisions.jsonl rows dated date_str. These files are small
    (~1.7MB observed) -- full read is fine, no tail-bounding needed."""
    path = FLEET_DIR / arm_id / "decisions.jsonl"
    rows = []
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line or date_str not in line:
            continue
        try:
            r = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if str(r.get("ts_et") or "").startswith(date_str):
            rows.append(r)
    return rows


def _entries_for_date(date_str: str) -> tuple[list[dict], list[dict]]:
    """(entries, core_rows). entries = every REAL placed ENTER across all 5 active SPY arms
    dated date_str (core: verdict in ENTER_*, armed True; fleet: action in ENTER_*,
    placement.placed True) -- the shared "was there a real fill" signal WS7/WS1/Theta all
    need. core_rows = every core row that date (also the "did the market trade" proxy).

    ADDITIVE (2026-08-04, real 2026-08-03T13:21:03 safe/bollinger_squeeze incident): a core
    row's TOP-LEVEL verdict/action is the PRIMARY-setup path only -- heartbeat_core.py's
    _route_extra_setups lane can place a REAL order for a totally different setup on the SAME
    row while that row's own verdict/action records an unrelated primary-path SKIP (here:
    verdict/action=SKIP_ELITE_BULL_LEVEL_RECLAIM while extra_exec placed a real +$67.85
    bollinger_squeeze fill, SPY260803C00757000 side C qty 3). That real entry lives ONLY
    inside extra_exec (a LIST of dicts), so the branch above -- which only ever fires on an
    ENTER_BEAR/ENTER_BULL verdict -- never sees it. The loop below scans extra_exec on EVERY
    row in addition to (never instead of) the existing branch, so a row can contribute to
    BOTH lanes; this row only qualifies for the new one since its own verdict is a SKIP. Same
    reuse pattern as the proven fix in full_send_vs_gated.py::load_core_safe_entry_minutes;
    mirrored fix on the participation_cascade.py side: build_events/_extra_exec_events. Guard:
    test_monday_verify_2026_08_01.py::test_entries_for_date_finds_extra_exec_placed_entry."""
    core_rows = _load_core_rows_for_date(date_str)
    entries = []
    for r in core_rows:
        if r.get("verdict") in ("ENTER_BEAR", "ENTER_BULL") and r.get("armed") is True:
            acct = r.get("account")
            entries.append({
                "lane": "core", "arm": CORE_ACCOUNT_TO_ARM.get(acct, acct), "account": acct,
                "side": r.get("side"), "setup": r.get("setup"), "ts_et": r.get("ts_et"),
            })
        for xe in (r.get("extra_exec") or []):
            if not isinstance(xe, dict) or xe.get("action") != "PLACED":
                continue
            exec_ = xe.get("exec") or {}
            acct = r.get("account")
            entries.append({
                "lane": "core_extra_exec", "arm": CORE_ACCOUNT_TO_ARM.get(acct, acct),
                "account": acct, "side": exec_.get("side"), "setup": xe.get("setup"),
                "ts_et": r.get("ts_et"), "strike": exec_.get("strike"),
                "qty": exec_.get("qty"), "premium": exec_.get("premium"),
            })
    for arm_id in FLEET_ARM_IDS:
        for r in _load_fleet_rows_for_date(arm_id, date_str):
            if r.get("action") in ("ENTER_BEAR", "ENTER_BULL") and (r.get("placement") or {}).get("placed") is True:
                entries.append({
                    "lane": "fleet", "arm": arm_id, "side": r.get("side"),
                    "setup": r.get("setup_name"), "ts_et": r.get("ts_et"),
                    "strike": r.get("strike"), "qty": r.get("qty"),
                    "premium": r.get("premium"), "risk_code": r.get("risk_code"),
                })
    entries.sort(key=lambda e: e.get("ts_et") or "")
    return entries, core_rows


def _level_flip_stats(ticks: list[tuple]) -> dict:
    """ticks: [(ts_et, sorted-list-of-rounded-level-prices), ...] time-ordered. Returns
    {f"{price:.2f}": {"present": n, "flips": n}} -- present/absent transition count per
    level, the exact metric LEVEL-FLICKER-FIX-2026-08-01.md's per-level table reports."""
    all_prices = sorted({p for _, levels in ticks for p in levels})
    stats = {}
    for price in all_prices:
        seq = [price in levels for _, levels in ticks]
        present = sum(seq)
        flips = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
        stats[f"{price:.2f}"] = {"present": present, "flips": flips}
    return stats


_LW_LINE_RE = re.compile(
    r"^\[live_watch\] (\d{2}:\d{2}) ET "
    r"(RTH snapshot written \(in_trade=(\d+), arms=(\d+), errors=(\d+)\)"
    r"|closed; wrote single CLOSED marker"
    r"|closed; snapshot already CLOSED -- no write)$"
)


def _scan_live_watch_log(date_str: str, log_path: Path | None = None,
                          max_bytes: int = 400_000) -> dict:
    """live_watch.py's stdout log carries NO date per line (`[live_watch] HH:MM ET ...`),
    only a clock time, because it is a single ever-appending file (unlike level-refresh's
    per-day logs). Isolate "today's" contiguous run by walking the tail BACKWARD and
    stopping at the first non-monotonic jump (today's minutes strictly decrease going
    backward; the moment we cross into a PRIOR day's tail, HH:MM jumps UP, e.g. 16:05 seen
    after 09:25). Only trusted when the log's own mtime ET-date matches date_str -- this
    heuristic is not meaningful for an arbitrary PAST date, only "the most recent session
    reflected in the log", which is the realistic on-demand/post-close use case.

    log_path defaults to the CURRENT module global LIVE_WATCH_LOG, resolved at CALL time (not
    def-time) so check_ws7_live_watch (which never passes an override) still honors a
    monkeypatched path in tests."""
    log_path = LIVE_WATCH_LOG if log_path is None else log_path
    mtime_date = _file_mtime_et_date(log_path)
    if mtime_date != date_str:
        return {"available": False, "reason": f"log mtime ET-date={mtime_date} != {date_str}",
                "n_rth_fires": 0, "in_trade_ticks": 0, "first_hhmm": None, "last_hhmm": None,
                "n_lines_scanned": 0}
    text = _read_tail_text(log_path, max_bytes)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    same_day: list[tuple] = []
    prev_hhmm = None
    for ln in reversed(lines):
        m = _LW_LINE_RE.match(ln)
        if not m:
            continue
        hhmm = m.group(1)
        if prev_hhmm is not None and hhmm > prev_hhmm:
            break  # crossed into a prior day's tail (backward-in-time jumped UP)
        same_day.append((hhmm, ln))
        prev_hhmm = hhmm
    same_day.reverse()
    n_rth = sum(1 for _, ln in same_day if "RTH snapshot written" in ln)
    in_trade_ticks = 0
    for _, ln in same_day:
        m2 = re.search(r"in_trade=(\d+)", ln)
        if m2 and int(m2.group(1)) > 0:
            in_trade_ticks += 1
    return {"available": True, "reason": None, "n_rth_fires": n_rth,
            "in_trade_ticks": in_trade_ticks,
            "first_hhmm": same_day[0][0] if same_day else None,
            "last_hhmm": same_day[-1][0] if same_day else None,
            "n_lines_scanned": len(same_day)}


def _attempt_core_recency_refresh(timeout_s: int = 90) -> dict:
    """Best-effort fresh re-run of the WS11 instrument (broker-fills-only, --no-replay skips
    the ~2min engine-sim supplement) so the check reads Monday's real fills without waiting
    for the 01:00 ET Gamma_GateExpiryCheck fire. Never load-bearing for the verdict by
    itself -- see decide_ws11 -- a failed/timed-out attempt just means we read whatever is
    already on disk (possibly refreshed by the nightly job already, possibly still the
    frozen baseline, both disclosed)."""
    if not BACKTEST_VENV_PY.exists() or not CORE_RECENCY_SCRIPT.exists():
        return {"attempted": False, "ok": False, "reason": "backtest venv python or script missing"}
    try:
        proc = subprocess.run(
            [str(BACKTEST_VENV_PY), str(CORE_RECENCY_SCRIPT), "--no-replay"],
            cwd=str(REPO), capture_output=True, text=True, timeout=timeout_s,
            creationflags=_CREATE_NO_WINDOW,
        )
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-5:]
        return {"attempted": True, "ok": proc.returncode == 0, "returncode": proc.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"attempted": True, "ok": False, "reason": f"timeout after {timeout_s}s"}
    except Exception as exc:  # noqa: BLE001 -- this refresh attempt must never crash the sweep
        return {"attempted": True, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# pure verdict deciders (no I/O -- unit-tested + RED-proofed directly)
# --------------------------------------------------------------------------- #
def decide_ws7(*, has_session: bool, n_rth_fires: int, expected_fires: int,
               in_trade_ticks: int, n_entries: int) -> str:
    if not has_session:
        return NOT_EXERCISED
    if n_rth_fires == 0:
        return RED  # an RTH session happened; the watcher produced zero evidence of firing
    cadence_ok = expected_fires <= 0 or (n_rth_fires / expected_fires) >= 0.75
    if n_entries == 0:
        # cadence is testable and answered; the FIELD-POPULATION headline claim is not.
        return _combine(GREEN if cadence_ok else YELLOW, NOT_EXERCISED)
    if in_trade_ticks == 0:
        return RED  # a real fill happened but live_watch never once saw it as in_trade
    return GREEN if cadence_ok else YELLOW


def decide_ws6(*, is_weekday: bool, stamp_present: bool, rc_present: bool,
               dates_match: bool, gen_hhmm_in_window: bool | None) -> str:
    if not is_weekday:
        return NOT_EXERCISED
    if not stamp_present or not rc_present:
        return RED
    if not dates_match:
        return RED  # artifacts exist but are stale -- the fire didn't happen TODAY
    if gen_hhmm_in_window is None:
        return YELLOW
    return GREEN if gen_hhmm_in_window else YELLOW


def decide_ws3(*, has_session: bool, n_refresh_runs: int, worst_flips: int | None,
               friday_worst_flips: int = FRIDAY_WORST_FLIPS) -> str:
    if not has_session:
        return NOT_EXERCISED
    if n_refresh_runs == 0:
        return RED  # core ticks exist but the level refresher never logged a single run
    if worst_flips is None:
        return YELLOW  # runs logged but no level presence could be measured (empty ticks?)
    if worst_flips >= friday_worst_flips:
        return RED  # matches or exceeds Friday's PRE-FIX pathological worst case
    if worst_flips > friday_worst_flips / 2:
        return YELLOW
    return GREEN


def decide_ws11(*, window_advanced: bool) -> str:
    return GREEN if window_advanced else NOT_EXERCISED


def decide_theta(*, has_session: bool, snapshot_fresh: bool, accounts_checked: bool,
                  n_rows: int, n_usable_source_rows: int) -> str:
    if not has_session:
        return NOT_EXERCISED
    if not snapshot_fresh or not accounts_checked:
        return RED  # RTH session happened; the cockpit produced no fresh evidence at all
    if n_rows == 0:
        return NOT_EXERCISED  # cadence alive, but no position ever open -> source Q untested
    if n_usable_source_rows == 0:
        return YELLOW  # rows exist but every one is 'unavailable' -- degraded, not dead
    return GREEN


def decide_ws1(*, date_matches_target: bool, has_session: bool, data_ok: bool) -> str:
    if not date_matches_target or not has_session:
        return NOT_EXERCISED
    return GREEN if data_ok else RED


# --------------------------------------------------------------------------- #
# the six checks (IO wrappers around the pure deciders above)
# --------------------------------------------------------------------------- #
def check_ws7_live_watch(date_str: str) -> dict:
    name = "WS7 live watch"
    expected = (
        "Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open "
        "position, live-watch.json (and the log's in_trade count) should reflect it within "
        "~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should "
        "populate non-null."
    )
    entries, core_rows = _entries_for_date(date_str)
    if not core_rows:
        return _finish("ws7_live_watch", name, NOT_EXERCISED, expected,
                        f"no core-decisions.jsonl ticks dated {date_str} -- no RTH session "
                        f"evidence (non-trading day or engine idle).", {"entries": entries})
    log_scan = _scan_live_watch_log(date_str)
    n_entries = len(entries)
    if not log_scan["available"]:
        observed = (f"live-watch.stdout.log's most recent session does not match {date_str} "
                    f"({log_scan['reason']}) -- cadence not verifiable from the log; "
                    f"{n_entries} real fill(s) dated {date_str} per the decisions ledger.")
        return _finish("ws7_live_watch", name, RED, expected, observed,
                        {"log_scan": log_scan, "n_entries": n_entries, "entries": entries})
    verdict = decide_ws7(has_session=True, n_rth_fires=log_scan["n_rth_fires"],
                          expected_fires=EXPECTED_LIVE_WATCH_FIRES,
                          in_trade_ticks=log_scan["in_trade_ticks"], n_entries=n_entries)
    fills_txt = ", ".join(f"{e['arm']}@{str(e['ts_et'])[11:16]}" for e in entries) if entries else "none"
    caveat = (" Field-level population NOT re-verifiable post-close (live-watch.json holds "
              "only the latest snapshot, no historical archive) -- corroborated only via the "
              "log's in_trade count, not a full field dump." if entries else "")
    observed = (
        f"{log_scan['n_rth_fires']} RTH fires logged ({log_scan['first_hhmm']}-"
        f"{log_scan['last_hhmm']} ET, vs ~{EXPECTED_LIVE_WATCH_FIRES} expected), "
        f"{log_scan['in_trade_ticks']} tick(s) showed in_trade>0. {n_entries} real fill(s) "
        f"dated {date_str}: {fills_txt}.{caveat}"
    )
    detail = {"log_scan": log_scan, "n_entries": n_entries, "entries": entries,
              "current_snapshot": _read_json(LIVE_WATCH_JSON)}
    return _finish("ws7_live_watch", name, verdict, expected, observed, detail)


def check_ws6_regime_stamp(date_str: str) -> dict:
    name = "WS6 regime stamp"
    expected = (
        "Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and "
        "Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches "
        "today-bias.json#regime_context, both dated the SAME session day, generated near "
        "08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re-test."
    )
    if not _is_weekday(date_str):
        return _finish("ws6_regime_stamp", name, NOT_EXERCISED, expected,
                        f"{date_str} is not a weekday -- Gamma_Premarket/Gamma_RegimeStamp "
                        f"do not fire on weekends.", {})
    stamp = _read_json(REGIME_STAMP_JSON)
    bias = _read_json(TODAY_BIAS_JSON)
    rc = (bias or {}).get("regime_context")
    stamp_date = (stamp or {}).get("date")
    bias_date = (bias or {}).get("date")
    rc_stamp_date = (rc or {}).get("stamp_date")
    gen_et = (stamp or {}).get("generated_at_et") or ""
    gen_hhmm = gen_et[11:16] if len(gen_et) >= 16 else None
    dates_match = stamp_date == date_str and rc_stamp_date == date_str
    gen_in_window = ("08:15" <= gen_hhmm <= "08:40") if gen_hhmm else None
    verdict = decide_ws6(is_weekday=True, stamp_present=bool(stamp), rc_present=bool(rc),
                          dates_match=dates_match, gen_hhmm_in_window=gen_in_window)
    observed = (
        f"regime-stamp.json date={stamp_date}, generated_at_et={gen_et or '?'} "
        f"(hhmm={gen_hhmm}, in 08:15-08:40 window={gen_in_window}). today-bias.json "
        f"date={bias_date}, regime_context.stamp_date={rc_stamp_date} (present={bool(rc)}, "
        f"dates_match={dates_match}). one_liner="
        f"{str((stamp or {}).get('one_liner', '?'))[:140]!r}"
    )
    detail = {"stamp": stamp, "regime_context": rc, "bias_date": bias_date,
              "dates_match": dates_match, "gen_hhmm": gen_hhmm, "gen_in_window": gen_in_window}
    return _finish("ws6_regime_stamp", name, verdict, expected, observed, detail)


def check_ws3_level_hysteresis(date_str: str) -> dict:
    name = "WS3 level hysteresis"
    expected = (
        f"Friday {FRIDAY_BASELINE_DATE} PRE-FIX worst case: level {FRIDAY_WORST_LEVEL} "
        f"present {FRIDAY_WORST_PRESENT}/{FRIDAY_WORST_TOTAL} core ticks, "
        f"{FRIDAY_WORST_FLIPS} appear/disappear flips (fixed-replay showed "
        f"{FRIDAY_WORST_TOTAL}/{FRIDAY_WORST_TOTAL}, 0 flips). Hysteresis N=5 is live in "
        f"production since 2026-08-01; every level's worst flip count today should sit well "
        f"under {FRIDAY_WORST_FLIPS}, with hysteresis_held firing whenever a level would "
        f"otherwise have vanished-and-returned within 5 refresh windows."
    )
    _entries, core_rows = _entries_for_date(date_str)
    if not core_rows:
        return _finish("ws3_level_hysteresis", name, NOT_EXERCISED, expected,
                        f"no core-decisions.jsonl ticks dated {date_str}.", {})
    safe_rows = [r for r in core_rows if r.get("account") == "safe"
                 and isinstance(r.get("levels_active"), list)]
    ticks = [(r.get("ts_et"),
              sorted({round(float(x), 2) for x in (r.get("levels_active") or [])
                      if isinstance(x, (int, float))}))
             for r in safe_rows]
    stats = _level_flip_stats(ticks)
    worst_level = worst_flips = None
    if stats:
        worst_level, worst_row = max(stats.items(), key=lambda kv: kv[1]["flips"])
        worst_flips = worst_row["flips"]
    log_path = LOGS_DIR / f"level-refresh-{date_str}.log"
    runs = _iter_concat_json(_read_text(log_path)) if log_path.exists() else []
    n_ok_runs = sum(1 for r in runs if isinstance(r, dict) and r.get("ok"))
    held_events = sum(len(r.get("hysteresis_held") or []) for r in runs if isinstance(r, dict))
    held_levels = {(e.get("label"), e.get("price")) for r in runs if isinstance(r, dict)
                   for e in (r.get("hysteresis_held") or [])}
    verdict = decide_ws3(has_session=True, n_refresh_runs=len(runs), worst_flips=worst_flips)
    observed = (
        f"{len(ticks)} safe core ticks, {len(stats)} distinct near-price levels. Worst: "
        f"{worst_level} flipped {worst_flips}x (vs Friday PRE-FIX worst "
        f"{FRIDAY_WORST_LEVEL} @ {FRIDAY_WORST_FLIPS}x, present "
        f"{FRIDAY_WORST_PRESENT}/{FRIDAY_WORST_TOTAL}). {len(runs)} level-refresh run(s) "
        f"logged ({n_ok_runs} ok), hysteresis_held fired {held_events} time(s) across "
        f"{len(held_levels)} distinct level(s)."
    )
    detail = {
        "n_ticks": len(ticks), "per_level": stats, "worst_level": worst_level,
        "worst_flips": worst_flips, "n_refresh_runs": len(runs), "n_ok_runs": n_ok_runs,
        "hysteresis_held_events": held_events, "hysteresis_held_distinct_levels": len(held_levels),
        "friday_baseline": {"date": FRIDAY_BASELINE_DATE, "level": FRIDAY_WORST_LEVEL,
                            "present": FRIDAY_WORST_PRESENT, "total": FRIDAY_WORST_TOTAL,
                            "flips": FRIDAY_WORST_FLIPS},
    }
    return _finish("ws3_level_hysteresis", name, verdict, expected, observed, detail)


def check_ws11_core_recency(date_str: str, attempt_live_refresh: bool = True) -> dict:
    name = "WS11 core recency"
    b = WS11_BASELINE
    expected = (
        f"Baseline frozen {b['run_date']} (25-trading-day rolling window ending "
        f"{b['window_end']}): bear {b['bear']['verdict']} n={b['bear']['n']} "
        f"exp=${b['bear']['exp_per_trade']}/tr; bull {b['bull']['verdict']} n={b['bull']['n']} "
        f"exp=${b['bull']['exp_per_trade']}/tr. Watching whether n grows and/or either "
        f"verdict moves as the rolling window advances past {b['window_end']}."
    )
    refresh = _attempt_core_recency_refresh() if attempt_live_refresh else {"attempted": False}
    cur = _read_json(CORE_RECENCY_JSON)
    if not cur:
        return _finish("ws11_core_recency", name, RED, expected,
                        "automation/state/core-strategy-recency.json is missing entirely -- "
                        "the WS11 instrument has never produced output.", {"refresh": refresh})
    window_end = (cur.get("window") or {}).get("end")
    window_advanced = window_end is not None and window_end != b["window_end"]
    bear = (cur.get("verdicts") or {}).get("bear", {})
    bull = (cur.get("verdicts") or {}).get("bull", {})
    verdict = decide_ws11(window_advanced=window_advanced)
    n_delta = (bear["n"] - b["bear"]["n"]) if isinstance(bear.get("n"), (int, float)) else None
    verdict_moved = bear.get("verdict") != b["bear"]["verdict"]
    n_delta_txt = f"{n_delta:+d}" if isinstance(n_delta, int) else "n/a"
    observed = (
        f"run_date={cur.get('run_date')} window_end={window_end} (baseline "
        f"window_end={b['window_end']}, advanced={window_advanced}). bear now: "
        f"{bear.get('verdict')} n={bear.get('n')} (delta {n_delta_txt} vs baseline n=10) "
        f"exp=${bear.get('exp_per_trade')}/tr, verdict_moved={verdict_moved}. bull now: "
        f"{bull.get('verdict')} n={bull.get('n')} exp=${bull.get('exp_per_trade')}/tr. "
        f"live refresh attempted={refresh.get('attempted')} ok={refresh.get('ok')}."
    )
    detail = {"baseline": b, "current_verdicts": cur.get("verdicts"), "window_end": window_end,
              "window_advanced": window_advanced, "n_delta_bear": n_delta,
              "verdict_moved_bear": verdict_moved, "refresh": refresh,
              "run_date": cur.get("run_date")}
    return _finish("ws11_core_recency", name, verdict, expected, observed, detail)


def check_theta_cockpit(date_str: str) -> dict:
    name = "Theta cockpit"
    expected = (
        "Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically "
        f"theta_per_contract_per_day_source == '{THETA_SOURCE_HISTORICAL_EST}' on 29/29 "
        "real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint "
        "has returned {} every time) -- this run tests whether that streak is STILL true "
        f"on any real fill dated {date_str}, or whether it finally flips to "
        "'broker_snapshot'."
    )
    entries, core_rows = _entries_for_date(date_str)
    if not core_rows:
        return _finish("theta_cockpit", name, NOT_EXERCISED, expected,
                        f"no core-decisions.jsonl ticks dated {date_str} -- non-trading day.",
                        {"entries": entries})
    snapshot = _read_json(THETA_SNAPSHOT_JSON) or {}
    snapshot_fresh = str(snapshot.get("ts_et") or "").startswith(date_str)
    accounts_checked = snapshot.get("accounts_checked") or []
    daily_jsonl = THETA_DIR / f"theta-clock-{date_str}.jsonl"
    rows = []
    for ln in _read_text(daily_jsonl).splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except (json.JSONDecodeError, ValueError):
            continue
    sources_seen = sorted({r.get("theta_per_contract_per_day_source") for r in rows
                           if r.get("theta_per_contract_per_day_source")})
    n_broker = sum(1 for r in rows if r.get("theta_per_contract_per_day_source") == "broker_snapshot")
    n_est = sum(1 for r in rows if r.get("theta_per_contract_per_day_source") == THETA_SOURCE_HISTORICAL_EST)
    n_unavail = sum(1 for r in rows if r.get("theta_per_contract_per_day_source") == "unavailable")
    n_usable = n_broker + n_est
    verdict = decide_theta(has_session=True, snapshot_fresh=snapshot_fresh,
                            accounts_checked=bool(accounts_checked), n_rows=len(rows),
                            n_usable_source_rows=n_usable)
    flipped = n_broker > 0
    if flipped:
        source_note = "FLIPPED to broker_snapshot at least once -- the 29/29-empty streak is broken."
    elif rows:
        source_note = f"still {THETA_SOURCE_HISTORICAL_EST} on every row -- the 29/29-empty streak holds."
    else:
        source_note = f"no real position dated {date_str} -- source question not exercised."
    observed = (
        f"snapshot ts_et={snapshot.get('ts_et')} (fresh_today={snapshot_fresh}) "
        f"accounts_checked={accounts_checked}. {len(rows)} theta-clock row(s) dated "
        f"{date_str} across {len({r.get('symbol') for r in rows})} position(s); sources "
        f"seen={sources_seen}. broker_snapshot={n_broker}, "
        f"{THETA_SOURCE_HISTORICAL_EST}={n_est}, unavailable={n_unavail}. {source_note}"
    )
    detail = {"snapshot": snapshot, "n_rows": len(rows), "sources_seen": sources_seen,
              "n_broker": n_broker, "n_est": n_est, "n_unavailable": n_unavail,
              "flipped_to_broker": flipped, "entries": entries}
    return _finish("theta_cockpit", name, verdict, expected, observed, detail)


def check_ws1_preview_diff(date_str: str) -> dict:
    name = "WS1 preview diff"
    expected = (
        f"MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/"
        f"bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of "
        f"2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable "
        f"episodes / 32 in-window ENTER-plan ticks under the new bold_core ATM tier); "
        f"risky-3 ~2 fills. risky-1 SoD equity ~$1,756.87 (ATM tier applies) UNLESS the "
        f"WS12 $2,500/arm reset ran, which flips every arm's normal lane back to OTM-2."
    )
    if date_str != WS1_TARGET_DATE:
        return _finish("ws1_preview_diff", name, NOT_EXERCISED, expected,
                        f"this preview is date-scoped to Monday {WS1_TARGET_DATE}; checked "
                        f"date is {date_str} -- diff not applicable.",
                        {"target_date": WS1_TARGET_DATE})
    entries, core_rows = _entries_for_date(date_str)
    if not core_rows:
        return _finish("ws1_preview_diff", name, NOT_EXERCISED, expected,
                        f"no core-decisions.jsonl ticks dated {date_str} yet -- Monday "
                        f"hasn't traded (or the engine hasn't fired) -- diff not computable.",
                        {"target_date": WS1_TARGET_DATE})

    agg_params = _read_json(AGGRESSIVE_PARAMS_JSON) or {}
    block_elite_bull_now = agg_params.get("block_elite_bull")

    preview = _read_json(WS1_PREVIEW_JSON) or {}
    friday_equity = preview.get("friday_sod_equity") or {}
    equity_now = {a: (_read_json(FLEET_DIR / a / "circuit-breaker.json") or {}).get("starting_equity_today")
                  for a in FLEET_ARM_IDS}
    known_equities = [equity_now[a] for a in FLEET_ARM_IDS if equity_now.get(a) is not None]
    reset_happened = (all(abs(v - 2500.0) < 50.0 for v in known_equities)
                      if len(known_equities) == len(FLEET_ARM_IDS) else None)

    per_arm_actual = {arm_id: sum(1 for e in entries if e["arm"] == arm_id) for arm_id in ALL_SPY_ARMS}
    predicted_episodes = {}
    for arm_id in FLEET_ARM_IDS:
        eps = ((preview.get("arms") or {}).get(arm_id) or {}).get("episodes") or []
        predicted_episodes[arm_id] = sum(1 for e in eps if e.get("n_ticks", 0) >= 2)

    data_ok = block_elite_bull_now is not None
    verdict = decide_ws1(date_matches_target=True, has_session=True, data_ok=data_ok)

    if reset_happened is True:
        reset_txt = "YES (~$2,500/arm -- normal lanes now price OTM-2, ATM tier inert)"
    elif reset_happened is False:
        reset_txt = "NO (equity still near Friday's levels -- risky-1 ATM tier applies)"
    else:
        reset_txt = "unknown (one or more fleet circuit-breaker.json unreadable)"
    actual_txt = ", ".join(f"{a}={per_arm_actual.get(a, 0)}" for a in ALL_SPY_ARMS)
    predicted_txt = ", ".join(f"{a}={predicted_episodes.get(a)}" for a in FLEET_ARM_IDS)
    observed = (
        f"block_elite_bull now={block_elite_bull_now} (preview predicted UNAPPLIED=true -> "
        f"cores stay at 0 elite-bull entries). Reset: {reset_txt}. Actual entries "
        f"{date_str}: {actual_txt}. Predicted tradeable episodes (Friday-tape replay, "
        f"n_ticks>=2): {predicted_txt}."
    )
    detail = {
        "target_date": WS1_TARGET_DATE, "block_elite_bull_now": block_elite_bull_now,
        "friday_sod_equity": friday_equity, "equity_now": equity_now,
        "reset_happened": reset_happened, "per_arm_actual_entries": per_arm_actual,
        "predicted_tradeable_episodes": predicted_episodes, "entries": entries,
    }
    return _finish("ws1_preview_diff", name, verdict, expected, observed, detail)


# --------------------------------------------------------------------------- #
# top-level orchestration
# --------------------------------------------------------------------------- #
def run_all(date_str: str, attempt_live_refresh: bool = True) -> dict:
    checks = [
        check_ws7_live_watch(date_str),
        check_ws6_regime_stamp(date_str),
        check_ws3_level_hysteresis(date_str),
        check_ws11_core_recency(date_str, attempt_live_refresh=attempt_live_refresh),
        check_theta_cockpit(date_str),
        check_ws1_preview_diff(date_str),
    ]
    overall = _combine(*(c["verdict"] for c in checks))
    return {
        "schema_version": 1,
        "checker": "monday_verify.py (WEEKEND-TWELVE Next-Twelve #6)",
        "generated_at_et": _now_et_str(),
        "check_date": date_str,
        "overall": overall,
        "never_blocks_never_kills": True,
        "checks": checks,
    }


def render_text_report(report: dict) -> str:
    lines = [f"=== monday_verify {report['check_date']} (generated {report['generated_at_et']} ET) ===",
             f"OVERALL: {report['overall']}", ""]
    for c in report["checks"]:
        lines.append(f"[{c['verdict']:14s}] {c['name']}")
        lines.append(f"  expected: {c['expected']}")
        lines.append(f"  observed: {c['observed']}")
        lines.append("")
    return "\n".join(lines)


def _short(s: str, n: int = 300) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"


def _render_status_block(report: dict) -> str:
    ts = report["generated_at_et"]
    overall = report["overall"]
    date_str = report["check_date"]
    counts = {v: sum(1 for c in report["checks"] if c["verdict"] == v)
             for v in (GREEN, YELLOW, RED, NOT_EXERCISED)}
    lines = [
        f"## [{ts} ET] {overall} -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): "
        f"mechanical sweep for {date_str} -- {counts[GREEN]} GREEN / {counts[YELLOW]} YELLOW "
        f"/ {counts[RED]} RED / {counts[NOT_EXERCISED]} NOT_EXERCISED",
        "",
        "**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies "
        "into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED "
        "means the item's precondition never fired this run (C7: a check passing because "
        "nothing happened is not GREEN).",
        "",
        "| Item | Verdict | Expected | Observed |",
        "|---|---|---|---|",
    ]
    for c in report["checks"]:
        exp = _short(c["expected"]).replace("|", "\\|").replace("\n", " ")
        obs = _short(c["observed"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {c['name']} | {c['verdict']} | {exp} | {obs} |")
    lines += [
        "",
        "Full detail: `automation/state/monday-verify.json`. Re-run: "
        "`backtest\\.venv\\Scripts\\python.exe setup\\scripts\\monday_verify.py "
        f"--date {date_str}`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.",
        "",
    ]
    return "\n".join(lines)


def _prepend_status_block(report: dict, status_md: Path = STATUS_MD) -> None:
    """Newest-first prepend, matching every other producer + status_retention.py's `## [`
    entry-boundary split -- this block becomes ONE more dated entry at the top."""
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return
    block = _render_status_block(report)
    try:
        status_md.write_text(block + "\n---\n\n" + text, encoding="utf-8")
    except OSError:
        pass


def _compute_newly_red(report: dict, prior: dict | None) -> list[dict]:
    """Byte-for-byte the same transition-only, no-respam idea as
    gate_expiry_check.compute_newly_red / guard_runner_slow._flag_status_md."""
    prior_by_id = {c["id"]: c for c in (prior or {}).get("checks", [])} if prior else {}
    return [c for c in report["checks"]
            if c["verdict"] == RED and prior_by_id.get(c["id"], {}).get("verdict") != RED]


def _flag_known_broken(newly_red: list[dict], date_str: str, status_md: Path = STATUS_MD) -> None:
    if not newly_red:
        return
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        return
    lines = []
    for c in newly_red:
        lines.append(
            f"- [{_now_et_str()}] MONDAY-VERIFY RED :: {c['id']} :: {_short(c['observed'], 220)} "
            f":: re-check: backtest\\.venv\\Scripts\\python.exe setup\\scripts\\monday_verify.py "
            f"--date {date_str}")
    head, _, tail = text.partition(marker + "\n")
    block = "\n".join(lines)
    try:
        status_md.write_text(f"{head}{marker}\n\n{block}\n{tail.lstrip(chr(10))}", encoding="utf-8")
    except OSError:
        pass


def write_outputs(report: dict, prior: dict | None) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    newly_red = _compute_newly_red(report, prior)
    _flag_known_broken(newly_red, report["check_date"])
    _prepend_status_block(report)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="WEEKEND-TWELVE Next-Twelve #6: mechanical Monday-verify sweep (WS7 "
                    "live-watch, WS6 regime stamp, WS3 level hysteresis, WS11 core recency, "
                    "theta cockpit, WS1 preview-vs-actuals). Fail-open, never blocks/kills; "
                    "NOT_EXERCISED when a precondition never fired.")
    ap.add_argument("--date", type=str, default=None,
                    help="ET date to verify, YYYY-MM-DD (default: today ET)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print only; never writes monday-verify.json or STATUS.md")
    ap.add_argument("--skip-live-refresh", action="store_true",
                    help="skip the WS11 live subprocess re-run; read the on-disk "
                         "core-strategy-recency.json as-is")
    args = ap.parse_args(argv)

    if args.date:
        date_str = args.date
    else:
        try:
            date_str = et_now().date().isoformat()
        except Exception:  # noqa: BLE001
            date_str = dt.date.today().isoformat()

    try:
        prior = _read_json(OUT_JSON)
        report = run_all(date_str, attempt_live_refresh=not args.skip_live_refresh)
    except Exception as exc:  # noqa: BLE001 -- this sweep must NEVER crash/block anything
        print(f"[monday_verify] FAIL-OPEN: unexpected error building the report: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0

    print(render_text_report(report))

    if args.dry_run:
        print("[monday_verify] --dry-run: not writing monday-verify.json or STATUS.md")
        return 0

    try:
        write_outputs(report, prior)
        print(f"[monday_verify] wrote {OUT_JSON}")
    except Exception as exc:  # noqa: BLE001 -- writing the report must never be fatal either
        print(f"[monday_verify] FAIL-OPEN: could not write outputs: {type(exc).__name__}: {exc}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
