"""Guard tests for backtest/tools/structure_shift_replay.py -- THE PHILOSOPHY BUILD
(analysis-only, no orders, no live config touched). Per task spec: the predicate on synthetic
bars (bear confirm / bull confirm / no-confirm-within-K / lower-high-but-no-break edge),
entry-at-confirmation-close + exit-from-entry+1 convention, and a G5 calibration case.
Fast, pure-function-level -- does NOT re-run the full 390-day replay (that is exercised
manually via `python backtest/tools/structure_shift_replay.py`).

RED-PROOF (executed live this session, not narrated -- see
test_bear_boundary_exact_equality_does_not_confirm_strict_inequality below for the fixture):
mutated `cond2 = c_low < threshold` to `cond2 = c_low <= threshold` in
backtest/tools/structure_shift_replay.py, re-ran the boundary fixture (confirmation bar's low
EXACTLY equal to threshold=599.00) -- with `<=` it wrongly confirmed (conf_idx=1); reverted to
`<`, re-ran the SAME fixture -- it correctly does NOT confirm (conf_idx=None). `git diff
--stat` on the module was empty after revert. This proves the strict inequality is
load-bearing, not vacuous.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST_TOOLS = REPO / "backtest" / "tools"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(REPO), str(BACKTEST_TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import structure_shift_replay as ssr  # noqa: E402


def _mk_frame(day: dt.date, spec: list[tuple]) -> pd.DataFrame:
    """spec: list of (time, open, high, low, close) tuples -> a naive-timestamp RTH frame."""
    rows = []
    for t, o, h, lo, c in spec:
        rows.append({"timestamp_et": pd.Timestamp(dt.datetime.combine(day, t)),
                    "open": o, "high": h, "low": lo, "close": c})
    return pd.DataFrame(rows)


DAY = dt.date(2099, 3, 10)


# =============================================================================== 1. bear predicate

def test_bear_confirms_within_k_first_qualifying_bar_wins():
    """Trigger bar high=600.50 low=599.50, level=599.00. Bar+1 fails cond2 (low stays above the
    floor). Bar+2 satisfies BOTH -- first qualifying bar wins, bar+3 (which would also qualify)
    must NEVER be picked."""
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 600.00, 600.50, 599.50, 600.20),   # trigger (idx 0)
        (dt.time(9, 40), 600.10, 600.40, 599.60, 599.80),   # bar+1: high 600.40<600.50 OK, low 599.60 NOT<599.00 -- fails cond2
        (dt.time(9, 45), 599.70, 600.00, 598.50, 598.60),   # bar+2: high 600.00<600.50 OK, low 598.50<599.00 OK -- CONFIRMS
        (dt.time(9, 50), 598.50, 599.00, 597.00, 597.20),   # bar+3: would also confirm -- must NOT be picked
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=599.00, side="P", k=3)
    assert conf_idx == 2, f"expected first-qualifying bar (idx 2), got {conf_idx}"
    assert len(checked) == 2, "scan must STOP at the first confirming bar, never check bar+3"
    assert checked[0]["cond1"] is True and checked[0]["cond2"] is False
    assert checked[1]["cond1"] is True and checked[1]["cond2"] is True


def test_bear_lower_high_alone_without_breaking_floor_never_confirms():
    """Edge case named in the task spec: a bar prints a lower high but does NOT trade below
    min(trigger_low, level) -- cond1 true, cond2 false -- must NOT confirm."""
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 600.00, 600.50, 599.50, 600.20),   # trigger
        (dt.time(9, 40), 600.00, 600.10, 599.60, 599.90),   # lower high (600.10<600.50) but low 599.60 stays above floor 599.00
        (dt.time(9, 45), 599.90, 600.00, 599.55, 599.80),   # same again
        (dt.time(9, 50), 599.80, 599.95, 599.51, 599.70),   # same again -- K exhausted
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=599.00, side="P", k=3)
    assert conf_idx is None
    assert len(checked) == 3
    assert all(c["cond1"] for c in checked)
    assert not any(c["cond2"] for c in checked)


def test_bear_boundary_exact_equality_does_not_confirm_strict_inequality():
    """RED-PROOF fixture (see module docstring): confirmation bar's low is EXACTLY equal to
    the floor (threshold=min(trigger_low, level)=599.00) -- must NOT confirm, since the
    predicate is a strict '<', not '<='. Mutating to '<=' makes this fixture wrongly confirm
    (verified live this session, then reverted -- git diff was empty)."""
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 600.00, 600.50, 599.50, 600.20),   # trigger: low=599.50, level=599.00 -> threshold=599.00
        (dt.time(9, 40), 599.50, 600.00, 599.00, 599.10),   # low EXACTLY 599.00 (the boundary) -- must NOT confirm
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=599.00, side="P", k=1)
    assert conf_idx is None, "exact equality must NOT satisfy the strict '<' floor-break condition"
    assert checked[0]["cond1"] is True and checked[0]["cond2"] is False
    assert checked[0]["low"] == checked[0]["threshold"] == 599.00


def test_bear_uses_min_of_trigger_low_and_level_whichever_is_tighter():
    """When the level is BELOW the trigger bar's own low, the floor is the LEVEL (tighter),
    not the trigger's low -- a bar that breaks the trigger's low but not the (lower) level must
    NOT confirm."""
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 600.00, 600.50, 599.50, 600.20),   # trigger low=599.50, level=598.00 (level is the tighter floor)
        (dt.time(9, 40), 599.40, 599.60, 599.00, 599.10),   # lower high (599.60<600.50), low 599.00 breaks trigger-low (599.50) but NOT the level (598.00)
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=598.00, side="P", k=2)
    assert conf_idx is None, "must use min(trigger_low, level) -- 598.00 is the binding floor here"
    assert checked[0]["threshold"] == 598.00


# =============================================================================== 2. bull predicate (mirror)

def test_bull_confirms_within_k_mirrors_bear():
    """Trigger bar low=599.50 high=600.50, level=600.00. Confirmation: a HIGHER LOW that is
    ALSO above the level (max(trigger_low, level)=600.00), AND a bar that breaks the trigger's
    own high."""
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 599.80, 600.50, 599.50, 600.20),   # trigger (idx 0)
        (dt.time(9, 40), 600.10, 600.40, 599.90, 600.30),   # bar+1: low 599.90 NOT>600.00 -- fails cond1
        (dt.time(9, 45), 600.20, 600.90, 600.10, 600.80),   # bar+2: low 600.10>600.00 OK, high 600.90>600.50 OK -- CONFIRMS
        (dt.time(9, 50), 600.80, 601.50, 600.50, 601.20),   # bar+3: would also confirm -- must NOT be picked
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=600.00, side="C", k=3)
    assert conf_idx == 2
    assert len(checked) == 2
    assert checked[0]["cond1"] is False
    assert checked[1]["cond1"] is True and checked[1]["cond2"] is True


def test_bull_higher_low_without_breaking_trigger_high_never_confirms():
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 599.80, 600.50, 599.50, 600.20),   # trigger
        (dt.time(9, 40), 600.10, 600.40, 600.10, 600.30),   # higher low above level (600.10>600.00) but high 600.40 does NOT break 600.50
        (dt.time(9, 45), 600.20, 600.45, 600.15, 600.35),
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=600.00, side="C", k=2)
    assert conf_idx is None
    assert all(c["cond1"] for c in checked)
    assert not any(c["cond2"] for c in checked)


# =============================================================================== 3. no-confirm-within-K + day boundary

def test_no_confirmation_within_k_expires_never_falls_back():
    spy = _mk_frame(DAY, [
        (dt.time(9, 35), 600.00, 600.50, 599.50, 600.20),
        (dt.time(9, 40), 600.10, 600.60, 599.60, 600.40),   # higher high -- fails cond1 outright
        (dt.time(9, 45), 600.30, 600.70, 599.70, 600.50),
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=599.00, side="P", k=2)
    assert conf_idx is None
    assert len(checked) == 2


def test_scan_never_crosses_into_the_next_calendar_day():
    """K=3 requested, but only 1 bar remains in the trigger's own day -- the scan must stop at
    the day boundary, never pull in next-day bars even if they would satisfy both conditions."""
    day2 = DAY + dt.timedelta(days=1)
    rows = [
        {"timestamp_et": pd.Timestamp(dt.datetime.combine(DAY, dt.time(15, 50))),
         "open": 600.00, "high": 600.50, "low": 599.50, "close": 600.20},          # trigger, last bar of DAY
        {"timestamp_et": pd.Timestamp(dt.datetime.combine(day2, dt.time(9, 30))),
         "open": 598.00, "high": 598.50, "low": 597.00, "close": 597.50},          # next day -- would confirm if allowed
    ]
    spy = pd.DataFrame(rows)
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=599.00, side="P", k=3)
    assert conf_idx is None
    assert checked == [], "must not even inspect the next-day bar"


# =============================================================================== 4. entry-at-confirmation-close + exit-from-entry+1

def _mk_opt_bar(ts: pd.Timestamp, close: float) -> dict:
    return {"timestamp_et": ts, "open": close, "high": close, "low": close, "close": close,
            "volume": 1, "vwap": close, "trade_count": 1}


def test_resolve_confirmation_entry_uses_exact_timestamp_close_not_next_bar():
    """Entry price must be the option bar's CLOSE at the EXACT confirmation timestamp -- never
    the next bar (that would be ladder_fullhist_replay's DIFFERENT 'entry+1 open' convention,
    not this tool's 'confirmation-bar close' convention)."""
    conf_ts = dt.datetime(2099, 3, 10, 9, 45)
    opt_df = pd.DataFrame([
        _mk_opt_bar(pd.Timestamp(dt.datetime(2099, 3, 10, 9, 40)), 9.00),   # decoy: prior bar, must never be picked
        _mk_opt_bar(pd.Timestamp(conf_ts), 2.50),                            # the exact confirmation-bar quote
        _mk_opt_bar(pd.Timestamp(dt.datetime(2099, 3, 10, 9, 50)), 1.00),   # decoy: next bar, must never be picked
    ])
    res = ssr.resolve_confirmation_entry(opt_df, conf_ts, vix_now=15.0, spot=600.0, strike=600, side="P")
    assert res["ok"] is True
    assert res["entry_premium"] == 2.50


def test_resolve_confirmation_entry_red_proof_no_exact_bar_never_falls_back():
    """If the OPRA cache has bars but NONE at the exact confirmation timestamp, the candidate
    must be EXCLUDED (synthetic-priced for disclosure only) -- never silently substitute a
    neighboring bar's quote."""
    conf_ts = dt.datetime(2099, 3, 10, 9, 45)
    opt_df = pd.DataFrame([
        _mk_opt_bar(pd.Timestamp(dt.datetime(2099, 3, 10, 9, 40)), 9.00),
        _mk_opt_bar(pd.Timestamp(dt.datetime(2099, 3, 10, 9, 50)), 1.00),
    ])
    res = ssr.resolve_confirmation_entry(opt_df, conf_ts, vix_now=15.0, spot=600.0, strike=600, side="P")
    assert res["ok"] is False
    assert res["reason"] == "no_exact_bar_at_confirmation_close"
    assert res["synthetic_entry_premium"] is not None, "still disclosed for transparency"


def test_entry_bar_convention_exit_walk_starts_strictly_after_confirmation_bar():
    """ENTRY-BAR-CONVENTION-RULING-2026-07-25: entry_time_et = the confirmation bar's OWN
    timestamp, so walk_exit_manager's first eligible exit-check bar is strictly the NEXT bar,
    never the confirmation bar's own quote. A stop-tripping quote ON the confirmation bar must
    be ignored; the SAME quote one bar later must resolve it (anti-vacuity)."""
    from lib.exit_manager_walk import walk_exit_manager

    entry_ts = dt.datetime(2099, 3, 10, 9, 45)
    exit_shape = {"tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.8, "runner_target_pct": 99.0,
                  "premium_stop_pct": -0.50, "profit_lock_mode": "trailing",
                  "profit_lock_threshold_pct": 0.05, "profit_lock_trail_pct": 0.125,
                  "profit_lock_stop_offset_pct": 0.0}
    # A catastrophic-looking quote ON the entry/confirmation bar itself (same ts as entry) --
    # must be ignored entirely (walk_exit_manager only considers bars strictly AFTER entry_ts).
    opt_df = pd.DataFrame([
        _mk_opt_bar(pd.Timestamp(entry_ts), 0.01),                                  # entry bar's own quote -- never checked
        _mk_opt_bar(pd.Timestamp(entry_ts + dt.timedelta(minutes=5)), 5.00),        # first eligible check: healthy
    ])
    day_spy = pd.DataFrame([
        {"timestamp_et": pd.Timestamp(entry_ts), "open": 600, "high": 600, "low": 600, "close": 600, "volume": 1},
        {"timestamp_et": pd.Timestamp(entry_ts + dt.timedelta(minutes=5)), "open": 600, "high": 600, "low": 600, "close": 600, "volume": 1},
    ])
    walk = walk_exit_manager(
        symbol="SPY990310P00600000", side="P", entry_time_et=entry_ts, entry_premium=2.00, qty=3,
        exit_shape=exit_shape, structure_stop_enabled=False, trigger_level=None,
        strategy="ribbon_ride", time_stop_et=dt.time(15, 40), opt_df=opt_df,
        ribbon_tick_df=None, five_min_spy_df=day_spy,
    )
    assert walk.n_ticks_walked == 1, "must walk exactly 1 bar (strictly after entry), not 2"
    assert walk.dollar_pnl > 0, "the entry-bar's own catastrophic quote must never have been read"


# =============================================================================== 5. G5 calibration

def test_g5_bear_calibration_2026_07_27_0940_predicate_confirms():
    """Calibration case mirroring the pinned live incident (bear_score=9, level_rejection,
    rejection_level=744.9): a textbook rejection-then-breakdown sequence must confirm at K=3
    AND K=2, at the bar that first breaks BOTH the trigger's low and the level."""
    day = dt.date(2026, 7, 27)
    spy = _mk_frame(day, [
        (dt.time(9, 40), 745.50, 746.00, 744.80, 745.20),   # trigger: rejection at ~744.9, high=746.00 low=744.80
        (dt.time(9, 45), 745.10, 745.60, 744.30, 744.50),   # lower high (745.60<746.00) OK, low 744.30<744.80 OK -- CONFIRMS at K bar 1
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=744.90, side="P", k=3)
    assert conf_idx == 1
    conf_idx2, _ = ssr.scan_confirmation(spy, 0, level=744.90, side="P", k=2)
    assert conf_idx2 == 1, "K=2 sensitivity must reproduce the same result when confirmation fires within 1 bar"


def test_g5_bear_calibration_red_proof_a_rally_bar_does_not_confirm():
    """Anti-vacuity: the SAME trigger bar, but the next bar is a RALLY (higher high, holds
    above the floor) -- must NOT confirm. Proves the calibration test is sensitive, not
    hard-coded True."""
    day = dt.date(2026, 7, 27)
    spy = _mk_frame(day, [
        (dt.time(9, 40), 745.50, 746.00, 744.80, 745.20),
        (dt.time(9, 45), 745.30, 746.50, 745.00, 746.20),   # higher high -- fails cond1
    ])
    conf_idx, checked = ssr.scan_confirmation(spy, 0, level=744.90, side="P", k=3)
    assert conf_idx is None
    assert checked[0]["cond1"] is False


# =============================================================================== 6. trigger_class + population

def test_trigger_class_taxonomy():
    assert ssr.trigger_class(["level_rejection"]) == "LEVEL_tied"
    assert ssr.trigger_class(["trendline_rejection"]) == "TL_only"
    assert ssr.trigger_class(["level_rejection", "trendline_rejection"]) == "BOTH"
    assert ssr.trigger_class(["ribbon_flip"]) == "NEITHER"
    assert ssr.trigger_class(["fhh_level_rejection"]) == "LEVEL_tied", (
        "fhh_level_rejection is in-scope per the frozen pre-reg's explicit predicate text")
    assert ssr.trigger_class([]) == "NEITHER"
    assert ssr.trigger_class(None) == "NEITHER"


def test_build_population_includes_regardless_of_passed_both_sides():
    bear_raw = {
        5: {"score": 9, "blockers": [5], "triggers_fired": ["level_rejection"], "level": 744.9,
            "passed": False, "vix": 16.0},
        9: {"score": 10, "blockers": [], "triggers_fired": ["level_rejection"], "level": 700.0,
            "passed": True, "vix": 16.0},
        11: {"score": 3, "blockers": [1, 2, 3], "triggers_fired": ["ribbon_flip"], "level": None,
             "passed": False, "vix": 16.0},   # no level-tied trigger -- must be excluded
    }
    bull_raw = {
        7: {"score": 8, "blockers": [11], "triggers_fired": ["level_reclaim", "ribbon_flip"],
            "level": 738.1, "passed": False, "vix": 16.0},
    }
    pop = ssr.build_population(bear_raw, bull_raw)
    bar_idxs = {c["bar_idx"]: c for c in pop}
    assert set(bar_idxs) == {5, 9, 7}, "must include BOTH passed=True and passed=False, both sides"
    assert bar_idxs[5]["side"] == "P" and bar_idxs[5]["passed"] is False
    assert bar_idxs[9]["passed"] is True, "passed=True candidates must be included too (not ladder's own bear-only, passed=False-only scope)"
    assert bar_idxs[7]["side"] == "C" and bar_idxs[7]["level"] == 738.1
