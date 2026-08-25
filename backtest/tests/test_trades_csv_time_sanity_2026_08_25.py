"""Guard for L2 -- trades.csv reconciled fill times were 4h off (UTC->ET conversion
applied in the WRONG DIRECTION), queued/fixed 2026-08-25.

Root cause (one sentence): the EOD-flatten Step 4c fill-reconciliation instruction
(automation/prompts/eod-flatten.md and its aggressive twin) told the LLM to write
`time_exit={fill_time}` straight from Alpaca's raw FILL-activity payload -- which is
UTC -- with ZERO instruction to convert to ET, so on 2026-08-25 the engine's own
ledger recorded entry at ts_et 13:16:03 (17:16 UTC) but the reconciled trades.csv row
reads 09:16:04 / 09:26:03 (the model subtracted instead of adding, or just echoed UTC
wall-clock as if it were ET).

This test does TWO things:
  1. Proves the detection logic actually catches the wrong-direction-conversion defect
     and passes on the corrected value, using an in-memory synthetic row that mirrors
     the real 2026-08-25 numbers (never touches the real trades.csv to plant the bug --
     RED-PROOF is against a synthetic row, per the no-fake-data / don't-touch-history
     rule).
  2. Asserts the REAL journal/trades.csv has ZERO RTH violations among SPY 0DTE option
     rows dated on/after the fix boundary (2026-08-26) -- i.e. it protects all NEW
     writes made after tonight's prompt fix shipped.

KNOWN PRE-EXISTING BACKLOG (measured 2026-08-25, NOT touched, NOT backfilled):
  4 rows violate RTH (09:30-16:00 ET) out of 512 SPY 0DTE option rows scanned:
    - 2026-05-06  row  9 : SPY 2026-05-06 730P   time_exit=18:17:40 (bad exit only)
    - 2026-08-19  row 461: SPY260819C00770000    time_exit=16:23:05 (bad exit only)
    - 2026-08-19  row 462: SPY260819C00771000    time_entry=16:36:07 time_exit=16:41:06
    - 2026-08-25  row 513: SPY 2026-08-25 765C    time_entry=09:16:04 time_exit=09:26:03
                            (THIS is the confirmed-root-cause row this fire is about)
  Date range of backlog: 2026-05-06 .. 2026-08-25.
  These rows predate the fix and are reported here for visibility -- they are
  DELIBERATELY excluded from the RTH assertion (see BOUNDARY_DATE below) rather than
  silently swept in as "clean". Do not backfill them; do not widen the RTH window to
  make them pass.

Rail-4 CLEAR: read-only guard. Reads the real trades.csv for reporting/assertion but
never writes to it. No params/doctrine/orders/heartbeat/filters touched.
"""
import csv
import os
from datetime import time
from typing import Dict, List, Optional

# Anchor to __file__, never cwd (project hard rule).
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRADES_CSV = os.path.join(REPO, "journal", "trades.csv")

RTH_START = time(9, 30, 0)
RTH_END = time(16, 0, 0)

# Rows dated on/after this boundary are held to the RTH guard. Rows before it are the
# measured pre-existing backlog (see docstring) and are reported, not asserted-clean.
# Chosen as the day AFTER tonight's fix ships (2026-08-25 after-hours) so the very row
# that motivated this fire (also dated 2026-08-25) stays correctly classified as
# backlog rather than being retroactively "fixed" by the test.
BOUNDARY_DATE = "2026-08-26"


def _parse_time(s: str) -> Optional[time]:
    s = (s or "").strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) < 2:
        return None
    h, m = int(parts[0]), int(parts[1])
    sec = int(parts[2]) if len(parts) > 2 else 0
    return time(h, m, sec)


def _is_0dte_spy_option(row: Dict[str, str]) -> bool:
    contract = (row.get("contract") or "").strip()
    dte = (row.get("dte") or "").strip()
    return contract.startswith("SPY") and dte == "0"


def _rth_violation_reason(row: Dict[str, str]) -> Optional[str]:
    """Returns a human-readable reason string if this row's entry/exit falls outside
    RTH (09:30-16:00 ET), else None. Pure function -- no I/O -- so it can be exercised
    against synthetic rows for the RED-PROOF as well as against the real file."""
    if not _is_0dte_spy_option(row):
        return None
    te = _parse_time(row.get("time_entry", ""))
    tx = _parse_time(row.get("time_exit", ""))
    bad_entry = te is not None and not (RTH_START <= te <= RTH_END)
    bad_exit = tx is not None and not (RTH_START <= tx <= RTH_END)
    if not bad_entry and not bad_exit:
        return None
    parts = []
    if bad_entry:
        parts.append(f"time_entry={row.get('time_entry')} outside {RTH_START}-{RTH_END}")
    if bad_exit:
        parts.append(f"time_exit={row.get('time_exit')} outside {RTH_START}-{RTH_END}")
    return "; ".join(parts)


def _load_real_rows() -> List[Dict[str, str]]:
    with open(TRADES_CSV, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _split_by_boundary(rows: List[Dict[str, str]]):
    """Returns (post_boundary_violations, backlog_violations) as lists of
    (row_number_1indexed_incl_header, row) tuples."""
    post, backlog = [], []
    for i, row in enumerate(rows, start=2):  # data starts at file line 2 (1 = header)
        reason = _rth_violation_reason(row)
        if reason is None:
            continue
        date = (row.get("date") or "").strip()
        if date >= BOUNDARY_DATE:
            post.append((i, row, reason))
        else:
            backlog.append((i, row, reason))
    return post, backlog


# ---------------------------------------------------------------------------
# Part 1: prove the detector itself catches the exact defect and clears the fix.
# This is the RED-PROOF surface -- synthetic in-memory rows only, never the real CSV.
# ---------------------------------------------------------------------------

def _synthetic_row(time_entry: str, time_exit: str) -> Dict[str, str]:
    # Mirrors the real 2026-08-25 defect row's shape (contract/dte only fields that
    # matter to the detector).
    return {
        "date": "2026-08-26",  # inside the guarded (post-boundary) window
        "time_entry": time_entry,
        "time_exit": time_exit,
        "contract": "SPY 2026-08-26 765C",
        "dte": "0",
    }


def test_detector_catches_wrong_direction_utc_conversion_defect():
    """RED case: mirrors the actual 2026-08-25 bug -- fill was 17:16 UTC (13:16 ET) but
    the reconciler wrote 09:16 ET (wrong-direction conversion). Detector must flag it."""
    bad_row = _synthetic_row(time_entry="09:16:04", time_exit="09:26:03")
    reason = _rth_violation_reason(bad_row)
    assert reason is not None, (
        "detector failed to catch the wrong-direction-UTC-conversion defect "
        "(09:16/09:26 ET is physically impossible for a 0DTE SPY option fill -- "
        "market opens 09:30 ET)"
    )
    assert "time_entry" in reason and "time_exit" in reason


def test_detector_passes_on_correctly_converted_et_time():
    """GREEN case: same fill, correctly converted (17:16 UTC -> 13:16 ET, per the
    engine's own ts_et-ledger truth for this exact trade). Detector must clear it."""
    good_row = _synthetic_row(time_entry="13:16:03", time_exit="13:26:03")
    reason = _rth_violation_reason(good_row)
    assert reason is None, f"detector false-positived on a valid RTH time: {reason}"


def test_detector_flags_exit_pushed_past_market_close():
    """An exit that drifts past 16:00 ET (e.g. a bad reconcile pushing to 16:23) is
    also physically impossible for a 0DTE contract (expires worthless/settled at
    close) and must be caught -- mirrors the 2026-08-19 backlog rows."""
    row = _synthetic_row(time_entry="15:50:00", time_exit="16:23:05")
    reason = _rth_violation_reason(row)
    assert reason is not None
    assert "time_exit" in reason


# ---------------------------------------------------------------------------
# Part 2: the real backstop -- the actual journal/trades.csv, scoped to protect only
# writes made on/after the fix boundary.
# ---------------------------------------------------------------------------

def test_no_rth_violations_in_real_trades_csv_after_fix_boundary():
    rows = _load_real_rows()
    post, backlog = _split_by_boundary(rows)

    backlog_dates = sorted({r[1].get("date") for r in backlog})
    backlog_summary = (
        f"KNOWN PRE-EXISTING BACKLOG: {len(backlog)} row(s) dated before "
        f"{BOUNDARY_DATE} already violate RTH (dates: {backlog_dates}). "
        f"These are NOT in scope for this guard and must NOT be silently backfilled -- "
        f"see this test file's module docstring for the itemized list."
    )

    if post:
        detail = "\n".join(
            f"  line {ln}: date={row.get('date')} contract={row.get('contract')} "
            f"time_entry={row.get('time_entry')} time_exit={row.get('time_exit')} "
            f"-- {reason}"
            for ln, row, reason in post
        )
        raise AssertionError(
            f"{len(post)} NEW row(s) on/after {BOUNDARY_DATE} violate RTH "
            f"(09:30-16:00 ET) for a SPY 0DTE option -- the timezone-conversion "
            f"defect this guard exists for has RECURRED:\n{detail}\n\n{backlog_summary}"
        )

    # No assertion failure above -- but keep the backlog visible in a passing run's
    # output too (pytest -q won't show this, -s / -v will), per OP-33 visibility rule.
    print(backlog_summary)


def test_known_backlog_count_matches_measured_baseline():
    """Documents the exact backlog size so any GROWTH in it (e.g. someone hand-editing
    an old row, or a future bug backfilling stale dates) is visible instead of quietly
    absorbed. This does NOT assert the backlog is zero -- it asserts it hasn't grown
    past the measured 2026-08-25 baseline of 4 rows."""
    rows = _load_real_rows()
    _, backlog = _split_by_boundary(rows)
    KNOWN_BASELINE = 4
    assert len(backlog) <= KNOWN_BASELINE, (
        f"backlog grew from the measured baseline of {KNOWN_BASELINE} to "
        f"{len(backlog)} rows -- something backfilled or hand-edited a pre-boundary "
        f"row. Investigate before assuming this is fine; do not raise the baseline "
        f"without checking why."
    )
