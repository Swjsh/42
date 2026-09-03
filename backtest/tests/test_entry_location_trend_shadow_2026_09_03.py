"""Guard suite for setup/scripts/entry_location_trend_shadow.py -- the F2 ENTRY-LOCATION x
TREND-QUALITY shadow ledger (descends from analysis/deep-research/2026-09-03-money/
entry-location.md's own INSTRUMENT_ONLY next step).

The guards below pin the mechanics that would matter if broken:

  1. NO LOOK-AHEAD. A tick recorded AFTER a trade's entry must never change that trade's row
     -- range_position, minutes_since_ribbon_flip, minutes_since_htf15m_match, opening-range
     extension, and vix_dir are all computed from a subset filtered to ts <= entry_et before
     any helper ever sees it. This is the single most load-bearing guard in this file.
  2. THE CO-SIGNAL MECHANICS. Ribbon/htf_15m "minutes since flip" must correctly distinguish
     "flip observed within session" from "left-censored" (streak covers the whole visible
     prefix) from "not currently matching the trade direction at all" (None).
  3. OPENING-RANGE EXTENSION direction convention (calls measure above or_high, puts measure
     below or_low) and the partial-window honesty flag for entries before 09:45.
  4. CHASE CLASSIFICATION is reused unmodified from money_entry_location_stats.classify_chase.
  5. IDEMPOTENT + BACKFILL-CORRECT. Re-running against the same fixtures must never duplicate
     a ledger row, and in_sample must split correctly on the frozen 2026-09-02 cutoff.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import entry_location_trend_shadow as elts  # noqa: E402


# ---------------------------------------------------------------------------------
# helpers to build synthetic core-decisions-shaped ticks
# ---------------------------------------------------------------------------------
def _tick(ts_et: str, spy: float, vix: float | None = 15.0,
          ribbon: str | None = "BULL", htf: str | None = "BULL") -> tuple:
    return (dt.datetime.fromisoformat(ts_et), spy, vix, ribbon, htf)


def _trade(arm="test-arm", symbol="SPY260903C00700000", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
           date="2026-09-03", entry_ts_utc="2026-09-03T14:40:00.000000Z", realized_pnl=100.0,
           qty=5.0, hold_minutes=10, outcome="winner") -> dict:
    return {"arm": arm, "symbol": symbol, "setup": setup, "date": date,
            "entry_ts_utc": entry_ts_utc, "realized_pnl": realized_pnl, "qty": qty,
            "hold_minutes": hold_minutes, "outcome": outcome}


# ---------------------------------------------------------------------------------
# 1. NO LOOK-AHEAD -- the load-bearing guard
# ---------------------------------------------------------------------------------
def test_no_lookahead_a_later_tick_never_changes_an_earlier_row():
    """A synthetic decision-ledger with ticks both before AND after a trade's entry. Adding
    ticks AFTER entry (a ribbon flip back, a VIX spike, a new session high) must not move a
    single field on the already-computed row."""
    date = "2026-09-03"
    entry_et_str = "2026-09-03T10:40:00"   # entry at 10:40 ET
    trade = _trade(date=date, entry_ts_utc="2026-09-03T14:40:00.000000Z")

    prefix_only_ticks = {
        date: [
            _tick("2026-09-03T09:30:00", 700.00, 14.0, "BEAR", "BEAR"),
            _tick("2026-09-03T09:40:00", 700.50, 14.1, "BEAR", "BEAR"),
            _tick("2026-09-03T09:50:00", 701.20, 14.0, "BULL", "BULL"),   # ribbon flips here
            _tick("2026-09-03T10:20:00", 702.00, 13.8, "BULL", "BULL"),
            _tick("2026-09-03T10:40:00", 703.00, 13.5, "BULL", "BULL"),   # entry tick itself
        ]
    }
    row_prefix_only = elts.compute_row(trade, prefix_only_ticks)

    with_future_ticks = {
        date: prefix_only_ticks[date] + [
            _tick("2026-09-03T10:41:00", 750.00, 25.0, "BEAR", "BEAR"),   # dramatic future tick
            _tick("2026-09-03T11:00:00", 690.00, 30.0, "BEAR", "BEAR"),
        ]
    }
    row_with_future = elts.compute_row(trade, with_future_ticks)

    assert row_prefix_only == row_with_future, "a tick after entry changed the computed row"
    assert row_prefix_only["range_position"] is not None
    assert row_prefix_only["spy_at_entry"] == 703.00
    assert row_prefix_only["session_hi"] == 703.00   # NOT 750.00 from the future tick


# ---------------------------------------------------------------------------------
# 2. range_position -- H1's own formula, reproduced
# ---------------------------------------------------------------------------------
def test_range_position_matches_hand_computation():
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.00),
        _tick("2026-09-03T09:35:00", 705.00),   # session high so far
        _tick("2026-09-03T09:40:00", 701.00),   # entry tick: (701-700)/(705-700) = 0.2
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T13:40:00.000000Z", symbol="SPY260903C00700000")
    row = elts.compute_row(trade, ticks)
    assert row["range_position"] == pytest.approx(0.2)
    assert row["chase_extreme_0.75_0.25"] is False   # calls at 0.2 are NOT a chase


# ---------------------------------------------------------------------------------
# 3. minutes_since_ribbon_flip -- the three named states
# ---------------------------------------------------------------------------------
def test_ribbon_flip_observed_within_session():
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.0, ribbon="BEAR", htf="BEAR"),
        _tick("2026-09-03T09:50:00", 701.0, ribbon="BULL", htf="BULL"),   # flip at 09:50
        _tick("2026-09-03T10:05:00", 702.0, ribbon="BULL", htf="BULL"),   # entry, 15 min later
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T14:05:00.000000Z")
    row = elts.compute_row(trade, ticks)
    assert row["minutes_since_ribbon_flip"] == pytest.approx(15.0)
    assert row["ribbon_flip_left_censored"] is False


def test_ribbon_flip_none_when_not_matching_trade_direction():
    """Trade is a CALL (target BULL) but ribbon at entry reads BEAR -- must be None, not a
    stale/fabricated number."""
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.0, ribbon="BULL", htf="BULL"),
        _tick("2026-09-03T09:50:00", 699.0, ribbon="BEAR", htf="BEAR"),
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T13:55:00.000000Z")
    row = elts.compute_row(trade, ticks)
    assert row["minutes_since_ribbon_flip"] is None
    assert "!= " in row["ribbon_flip_note"]


def test_ribbon_flip_left_censored_when_streak_covers_whole_prefix():
    """Ribbon is BULL at the very first visible tick of the date -- the true flip is unknown
    (could be pre-session). Must be flagged left_censored, never treated as flip-at-open."""
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.0, ribbon="BULL", htf="BULL"),
        _tick("2026-09-03T09:45:00", 701.0, ribbon="BULL", htf="BULL"),
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T13:45:00.000000Z")
    row = elts.compute_row(trade, ticks)
    assert row["ribbon_flip_left_censored"] is True
    assert row["minutes_since_ribbon_flip"] is not None   # still reports the observable streak


# ---------------------------------------------------------------------------------
# 4. opening-range extension -- direction convention + partial-window honesty
# ---------------------------------------------------------------------------------
def test_or_extension_calls_measure_above_or_high():
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.0),
        _tick("2026-09-03T09:40:00", 702.0),   # or_high candidate
        _tick("2026-09-03T09:44:00", 699.0),   # or_low candidate
        _tick("2026-09-03T09:45:00", 700.5),   # window boundary tick
        _tick("2026-09-03T10:30:00", 705.0),   # entry: 3.0 above or_high, range width 3.0
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T14:30:00.000000Z")
    row = elts.compute_row(trade, ticks)
    assert row["or_high"] == pytest.approx(702.0)
    assert row["or_low"] == pytest.approx(699.0)
    assert row["or_window_complete"] is True
    assert row["or_extension_dollars"] == pytest.approx(3.0)
    assert row["or_extension_multiples"] == pytest.approx(1.0)


def test_or_window_incomplete_before_0945():
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.0),
        _tick("2026-09-03T09:36:00", 701.0),   # entry here, before 09:45
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T13:36:00.000000Z")
    row = elts.compute_row(trade, ticks)
    assert row["or_window_complete"] is False
    assert row["or_high"] == pytest.approx(701.0)   # partial window, honestly reported


# ---------------------------------------------------------------------------------
# 5. vix_dir
# ---------------------------------------------------------------------------------
def test_vix_dir_up_down_flat():
    date = "2026-09-03"
    ticks = {date: [
        _tick("2026-09-03T09:30:00", 700.0, vix=14.00),
        _tick("2026-09-03T09:45:00", 701.0, vix=15.00),   # +1.00 over 15 min -> "up"
    ]}
    trade = _trade(date=date, entry_ts_utc="2026-09-03T13:45:00.000000Z")
    row = elts.compute_row(trade, ticks)
    assert row["vix_dir"] == "up"
    assert row["vix_dir_delta"] == pytest.approx(1.00)

    ticks_flat = {date: [
        _tick("2026-09-03T09:30:00", 700.0, vix=14.00),
        _tick("2026-09-03T09:45:00", 701.0, vix=14.02),   # +0.02 -> "flat" (< 0.05 eps)
    ]}
    row_flat = elts.compute_row(trade, ticks_flat)
    assert row_flat["vix_dir"] == "flat"


# ---------------------------------------------------------------------------------
# 6. no OCC match -> None, never fabricated
# ---------------------------------------------------------------------------------
def test_unparseable_symbol_returns_none():
    trade = _trade(symbol="NOT_AN_OCC_SYMBOL")
    assert elts.compute_row(trade, {}) is None


# ---------------------------------------------------------------------------------
# 7. in_sample split on the frozen backfill cutoff
# ---------------------------------------------------------------------------------
def test_in_sample_flag_splits_on_backfill_cutoff():
    ticks = {"2026-09-02": [_tick("2026-09-02T10:00:00", 700.0)],
             "2026-09-03": [_tick("2026-09-03T10:00:00", 700.0)]}
    old_trade = _trade(date="2026-09-02", entry_ts_utc="2026-09-02T14:00:00.000000Z")
    new_trade = _trade(date="2026-09-03", entry_ts_utc="2026-09-03T14:00:00.000000Z")
    assert elts.compute_row(old_trade, ticks)["in_sample"] is True
    assert elts.compute_row(new_trade, ticks)["in_sample"] is False


# ---------------------------------------------------------------------------------
# 8. run() -- end-to-end idempotent append against fixture artifacts
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    mae_mfe = tmp_path / "mae-mfe.json"
    core_decisions = tmp_path / "core-decisions.jsonl"
    out_dir = tmp_path / "out"
    ledger = out_dir / "entry-location-trend-ledger.jsonl"
    summary = out_dir / "entry-location-trend-summary.json"

    trades = [
        {"date": "2026-09-01", "arm": "safe-2", "symbol": "SPY260901C00700000",
         "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "outcome": "winner", "realized_pnl": 150.0,
         "qty": 5.0, "hold_minutes": 12, "entry_ts_utc": "2026-09-01T14:40:00.000000Z"},
        {"date": "2026-09-01", "arm": "bold-2", "symbol": "SPY260901P00695000",
         "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON", "outcome": "loser", "realized_pnl": -80.0,
         "qty": 3.0, "hold_minutes": 5, "entry_ts_utc": "2026-09-01T15:10:00.000000Z"},
    ]
    mae_mfe.write_text(json.dumps({"trades": trades}), encoding="utf-8")

    rows = []
    for ts, spy, vix, ribbon, htf in [
        ("2026-09-01T09:30:03", 700.0, 14.0, "BEAR", "BEAR"),
        ("2026-09-01T09:50:00", 701.0, 14.0, "BULL", "BULL"),
        ("2026-09-01T10:40:00", 703.0, 13.8, "BULL", "BULL"),   # covers first trade's entry
        ("2026-09-01T11:10:00", 694.0, 13.9, "BEAR", "BEAR"),   # covers second trade's entry
    ]:
        rows.append(json.dumps({"ts_et": ts, "account": "safe", "spy": spy, "vix": vix,
                                 "ribbon": ribbon, "htf_15m": htf}) + "\n")
    core_decisions.write_text("".join(rows), encoding="utf-8")

    monkeypatch.setattr(elts, "MAE_MFE", mae_mfe)
    monkeypatch.setattr(elts, "CORE_DECISIONS", core_decisions)
    monkeypatch.setattr(elts, "OUT_DIR", out_dir)
    monkeypatch.setattr(elts, "LEDGER", ledger)
    monkeypatch.setattr(elts, "SUMMARY", summary)
    return {"ledger": ledger, "summary": summary}


def test_run_writes_one_row_per_trade(_wired_fixtures):
    out = elts.run()
    assert "error" not in out, out
    assert out["new_this_run"] == 2
    rows = elts._read_ledger()
    assert len(rows) == 2
    assert {r["symbol"] for r in rows} == {"SPY260901C00700000", "SPY260901P00695000"}


def test_run_is_idempotent_on_a_second_fire(_wired_fixtures):
    elts.run()
    out2 = elts.run()
    assert out2["new_this_run"] == 0
    rows = elts._read_ledger()
    assert len(rows) == 2, "re-running must never duplicate a ledger row"


def test_run_summary_has_expected_shape(_wired_fixtures):
    out = elts.run()
    summary = json.loads(elts.SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "ARMED"
    assert summary["prereg"] == elts.PREREG_REL
    for key in ("overall", "by_setup", "prereg_readiness", "prereg_cut_diagnostic", "meta"):
        assert key in summary, key
    assert "BULLISH_RECLAIM_RIDE_THE_RIBBON" in summary["by_setup"]
    bull_setup = summary["by_setup"]["BULLISH_RECLAIM_RIDE_THE_RIBBON"]
    assert "by_cosignal" in bull_setup
    for cosig in ("minutes_since_ribbon_flip", "minutes_since_htf15m_match",
                  "or_extension_multiples", "vix_at_entry", "vix_dir"):
        assert cosig in bull_setup["by_cosignal"], cosig
    assert out["prereg_readiness"]["n_chase_required"] == 150
    diag = summary["prereg_cut_diagnostic"]
    for key in ("n_chase_total", "fresh_leq_15min", "gray_15_45min_excluded_from_primary_comparison",
                "stale_gt_45min", "mean_diff_fresh_minus_stale_ci95"):
        assert key in diag, key


# ---------------------------------------------------------------------------------
# 9. chase classification reused unmodified from money_entry_location_stats
# ---------------------------------------------------------------------------------
def test_chase_classification_reuses_h1s_own_function():
    import money_entry_location_stats as mels
    assert elts.mels.classify_chase is mels.classify_chase
