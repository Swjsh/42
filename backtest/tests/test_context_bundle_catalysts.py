"""Guard for the CATALYSTS dimension of context_bundle_producer.py (added 2026-09-03).

WHAT THIS PINS, and why each assertion exists:

1. `compute_catalyst_context` is PURE -- dicts in, dict out, no I/O, no wall clock. Same
   contract as compute_events_context / compute_prior_day, so a future correlation study can
   call it per historical timestamp without re-deriving the math (C6).

2. `windows_scout_only` reproduces 2026-09-03 EXACTLY. That session is the whole reason this
   block exists: the book gapped -$779 in one minute at 10:00->10:01 ET on the ISM Services
   print while the bundle's own `events.todays_windows` read `[]`, because
   macro-calendar.json#no_trade_window_rules has 16 keys and zero ISM. Scout had named the
   window at 05:30 ET. The replay below uses Scout's real payload from that morning and asserts
   the disagreement counter reads 2 -- if a future refactor makes this read 0 again, the test
   fails instead of the money.

3. Overlap comparison, not string equality. The two producers pad and format differently
   ("09:55" vs "9:55", 09:55-10:05 vs 09:50-10:10). A window the mechanical calendar DOES
   cover must not be reported as scout-only just because the strings differ.

4. Fail-soft everywhere: missing/malformed inputs degrade to empty-with-reason, never raise
   and never fabricate a window.

5. The block never becomes a gate. `consumption_contract` is asserted present, and a
   companion source-level assertion checks no frozen decision-path file reads the key
   (L199: independently-reasonable filters AND'd together produced 700 signals / 0 trades).

RED-PROOFED: written against the real 2026-09-03 Scout payload; assertion 2 was confirmed to
FAIL when `windows_scout_only` is stubbed to [] and to PASS with the shipped implementation.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "setup" / "scripts" / "context_bundle_producer.py"

_spec = importlib.util.spec_from_file_location("_ctx_bundle_prod", _SRC)
cbp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbp)  # type: ignore[union-attr]

ET = timezone(timedelta(hours=-4))  # EDT; these fixtures are all September dates


def _now(h: int, m: int = 0, day: int = 3) -> datetime:
    return datetime(2026, 9, day, h, m, tzinfo=ET)


# The REAL payload Scout wrote at 2026-09-03T09:30:03Z (05:30 ET), verbatim.
SCOUT_2026_09_03 = {
    "generated_at": "2026-09-03T09:30:03Z",
    "today_no_trade_windows": [
        {"start": "08:25", "end": "08:35", "reason": "Weekly jobless claims print"},
        {"start": "09:55", "end": "10:05", "reason": "ISM Services PMI print"},
    ],
}

# What the bundle's own events block actually read that session: no windows at all.
EVENTS_EMPTY = {"todays_windows": [], "no_trade_window_active": False}


def test_pure_no_io_no_wall_clock():
    """Same result twice for the same inputs, and no filesystem/network reachability needed."""
    a = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(11))
    b = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(11))
    assert a == b


def test_reproduces_the_2026_09_03_disagreement():
    """THE regression. Scout named 2 windows; the mechanical calendar produced 0."""
    out = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(11))
    assert out["windows_scout_only_count"] == 2
    reasons = {w["reason"] for w in out["windows_scout_only"]}
    assert "ISM Services PMI print" in reasons
    assert "Weekly jobless claims print" in reasons


def test_window_active_flag_tracks_the_et_minute_axis():
    """10:00 ET sits inside Scout's 09:55-10:05 ISM window; 11:00 does not."""
    inside = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(10, 0))
    outside = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(11, 0))
    assert inside["scout_window_active"] is True
    assert inside["scout_active_windows"][0]["reason"] == "ISM Services PMI print"
    assert outside["scout_window_active"] is False


def test_overlap_not_string_equality():
    """A mechanical window that OVERLAPS Scout's must suppress the scout-only report even
    though the strings differ -- otherwise every session reports a false disagreement."""
    covered = {"todays_windows": [{"start_et": "09:50", "end_et": "10:10", "event": "ISM"}]}
    out = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, covered, now_et=_now(11))
    reasons = {w["reason"] for w in out["windows_scout_only"]}
    assert "ISM Services PMI print" not in reasons     # overlapped -> not scout-only
    assert "Weekly jobless claims print" in reasons    # 08:25-08:35 still uncovered
    assert out["windows_scout_only_count"] == 1


@pytest.mark.parametrize("scout", [None, {}, {"today_no_trade_windows": None},
                                   {"today_no_trade_windows": [{"start": "oops", "end": "10:05"}]},
                                   {"today_no_trade_windows": [{"start": "10:05", "end": "09:55"}]}])
def test_malformed_scout_degrades_never_raises(scout):
    """Unparseable or inverted windows are dropped with the block still returning; a bad
    input must never fabricate a window and must never take the producer down."""
    out = cbp.compute_catalyst_context(scout, None, EVENTS_EMPTY, now_et=_now(11))
    assert out["scout_windows"] == []
    assert out["windows_scout_only"] == []
    assert out["scout_window_active"] is False


def test_missing_scout_is_stale_with_a_reason():
    out = cbp.compute_catalyst_context(None, None, EVENTS_EMPTY, now_et=_now(11))
    assert out["scout_stale"] is True
    assert out["scout_stale_reason"]


def test_yesterdays_scout_is_not_stale_before_the_0530_fire():
    """Before Gamma_ScoutPremarket's 05:30 ET fire + slack, yesterday's file is EXPECTED.
    Flagging it stale at 04:00 would cry wolf every single morning."""
    early = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(4, 0, day=4))
    late = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(11, 0, day=4))
    assert early["scout_stale"] is False
    assert late["scout_stale"] is True


def test_earnings_blackout_only_fires_inside_the_window_and_skips_etfs():
    earnings = {
        "generated_at_et": "2026-09-03T08:20:01",
        "symbols": {
            "GLD": {"exempt": True, "reason": "known ETF"},
            "NVDA": {"exempt": False, "blackout_start_date": "2026-09-01",
                     "blackout_end_date": "2026-09-05", "next_earnings_date": "2026-09-05",
                     "timing": "amc", "confidence": "single_source", "as_of": "2026-08-28T07:50:00"},
            "AAPL": {"exempt": False, "blackout_start_date": "2026-10-23",
                     "blackout_end_date": "2026-10-29", "next_earnings_date": "2026-10-29"},
        },
    }
    out = cbp.compute_catalyst_context(SCOUT_2026_09_03, earnings, EVENTS_EMPTY, now_et=_now(11))
    assert out["earnings_blackout_count"] == 1
    assert out["earnings_blackout_today"][0]["symbol"] == "NVDA"
    assert out["earnings_stale"] is False


def test_earnings_file_from_another_day_is_stale():
    earnings = {"generated_at_et": "2026-08-28T08:20:01", "symbols": {}}
    out = cbp.compute_catalyst_context(SCOUT_2026_09_03, earnings, EVENTS_EMPTY, now_et=_now(11))
    assert out["earnings_stale"] is True
    assert "not today" in (out["earnings_stale_reason"] or "")


def test_consumption_contract_is_stated_in_the_payload():
    out = cbp.compute_catalyst_context(SCOUT_2026_09_03, None, EVENTS_EMPTY, now_et=_now(11))
    assert "never AND'd into a hard entry gate" in out["consumption_contract"]


def test_no_frozen_decision_path_file_reads_the_catalyst_keys():
    """L199 / the freeze. The block rides onto the decision row via heartbeat_core's existing
    verbatim tag of the WHOLE bundle dict; nothing on the scoring path may name these keys."""
    frozen = [REPO / "setup" / "scripts" / "heartbeat_core.py",
              REPO / "backtest" / "lib" / "filters.py",
              REPO / "backtest" / "lib" / "risk_gate.py",
              REPO / "automation" / "state" / "fleet" / "build_shared_signal.py"]
    for path in frozen:
        src = path.read_text(encoding="utf-8", errors="replace")
        for key in ("catalysts", "windows_scout_only", "scout_window_active",
                    "earnings_blackout_today"):
            assert key not in src, f"{path.name} references '{key}' -- the catalyst block must stay logged-only"
