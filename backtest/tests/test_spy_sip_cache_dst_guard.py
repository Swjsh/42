"""DST regression guard for backtest/data/spy_sip_cache/ (2026-08-19/20 backfill,
tools/backfill_spy_sip_cache_2024.py).

Root cause this guards against (same family as test_et_frame_guards.py, but for
the spy_sip_cache JSON per-day format rather than the spy_5m_*.csv master): a
writer that applies a FIXED UTC offset year-round instead of a real DST-aware
zoneinfo conversion mislabels every EST-month (winter) bar +1h. Concretely: the
first RTH bar of a session is ALWAYS "...T09:30:00" in true ET wall time; a
fixed -04:00-always writer would mislabel winter sessions' true 09:30 ET bar as
"...T10:30:00" (or, depending on which direction the bug points, drop straight
to a missing/duplicate 09:30 slot).

Two layers:
  1. test_backfill_conversion_is_dst_correct -- unit-level, no cache files
     needed: pins the backfill script's own UTC->ET conversion against known
     winter/summer instants (mirrors test_writer_emits_real_dst_offsets).
  2. test_every_cached_day_has_a_true_0930_open_bar /
     test_dst_boundary_days_have_no_hour_drift -- on-disk guard: FAILS if any
     actual cached day (especially the trading days immediately either side of
     a US DST transition) is missing its 09:30:00 wall-clock RTH-open bar.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

_BACKTEST = Path(__file__).resolve().parents[1]
if str(_BACKTEST) not in sys.path:
    sys.path.insert(0, str(_BACKTEST))
_TOOLS = _BACKTEST / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from backfill_spy_sip_cache_2024 import to_et_naive  # noqa: E402

CACHE_DIR = _BACKTEST / "data" / "spy_sip_cache"
RTH_OPEN = "09:30:00"

# US DST transitions covered by the 2024-01-02..present backfill. For each
# transition we pick the LAST cached trading day before it and the FIRST
# cached trading day at/after it -- these are the two days a fixed-offset
# writer would misalign relative to each other.
DST_BOUNDARY_PAIRS = [
    (dt.date(2024, 3, 8), dt.date(2024, 3, 11)),    # 2024 spring-forward (Mar 10)
    (dt.date(2024, 11, 1), dt.date(2024, 11, 4)),   # 2024 fall-back (Nov 3)
    (dt.date(2025, 3, 7), dt.date(2025, 3, 10)),    # 2025 spring-forward (Mar 9)
    (dt.date(2025, 10, 31), dt.date(2025, 11, 3)),  # 2025 fall-back (Nov 2)
    (dt.date(2026, 3, 6), dt.date(2026, 3, 9)),     # 2026 spring-forward (Mar 8)
]

needs_cache = pytest.mark.skipif(
    not CACHE_DIR.exists() or not any(CACHE_DIR.glob("spy_5m_*.json")),
    reason=f"spy_sip_cache missing/empty: {CACHE_DIR}",
)


def test_backfill_conversion_is_dst_correct():
    """EST instant (UTC-05:00) and EDT instant (UTC-04:00) must both resolve
    to naive wall-clock 09:30:00 -- the same instant-to-label proof shown in
    backtest/tools/_verify_dst_frame_2024_backfill.py's report output."""
    winter = to_et_naive("2025-01-02T14:30:00Z")  # true EST offset
    summer = to_et_naive("2025-06-02T13:30:00Z")  # true EDT offset
    assert winter == dt.datetime(2025, 1, 2, 9, 30, 0)
    assert summer == dt.datetime(2025, 6, 2, 9, 30, 0)

    # the WRONG (fixed -04:00 always) conversion would have read the winter
    # instant as 09:30 UTC-4 == 09:30 label only if you SUBTRACT 4h from
    # 14:30Z... i.e. a fixed-offset bug reading a *true* EST 09:30 ET instant
    # (14:30Z) would mislabel it 10:30 wall if it assumed -05:00 in summer, or
    # correctly read 14:30Z-4h=10:30 -- either way NOT 09:30. Pin the negative:
    fixed_offset_bug = dt.datetime.fromisoformat("2025-01-02T14:30:00+00:00") - dt.timedelta(hours=4)
    assert fixed_offset_bug.time() != dt.time(9, 30), (
        "sanity check inverted: a fixed -04:00-always conversion should NOT "
        "land on 09:30 for a true-EST instant"
    )


def _bar_times(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {b["t"].split("T")[1] for b in data.get("bars", [])}


@needs_cache
def test_every_cached_day_has_a_true_0930_open_bar():
    """Systemic guard: every cached trading day (5m AND 1m) must contain a bar
    at wall-clock 09:30:00. A day silently missing it is a DST-drift smell."""
    files = sorted(CACHE_DIR.glob("spy_5m_*.json")) + sorted(CACHE_DIR.glob("spy_1m_*.json"))
    missing = [f.name for f in files if RTH_OPEN not in _bar_times(f)]
    assert not missing, (
        f"{len(missing)} cached day(s) missing the 09:30:00 RTH-open bar "
        f"(DST-drift smell): {missing[:10]}{'...' if len(missing) > 10 else ''}"
    )


@needs_cache
def test_dst_boundary_days_have_no_hour_drift():
    """Focused guard on the exact days either side of every US DST transition
    in the backfilled span: both the pre- and post-transition trading day must
    show their RTH open at 09:30:00, never 08:30:00 or 10:30:00."""
    checked = 0
    failures = []
    for before, after in DST_BOUNDARY_PAIRS:
        for day in (before, after):
            path = CACHE_DIR / f"spy_5m_{day.isoformat()}.json"
            if not path.exists():
                continue  # weekend/holiday landed on the picked date; not a failure
            checked += 1
            times = _bar_times(path)
            if RTH_OPEN not in times:
                failures.append((day.isoformat(), sorted(times)[:5]))
    assert checked > 0, "no DST-boundary days found on disk -- guard did not actually run"
    assert not failures, f"hour-drift at DST boundary: {failures}"
