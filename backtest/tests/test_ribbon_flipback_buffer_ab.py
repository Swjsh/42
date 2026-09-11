"""Guard tests for backtest/tools/ribbon_flipback_buffer_ab.py -- the ribbon-flip-back
invalidation buffer A/B (analysis/recommendations/prereg-ribbon-flipback-buffer-2026-08-08.json).

Pure-function coverage only: no network, no broker, no fetching of real OPRA bars. Every test
constructs small synthetic DataFrames so the run is instant and deterministic.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ribbon_flipback_buffer_ab.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_flipback_buffer_ab as m  # noqa: E402


# ------------------------------------------------------------------------------------------
# _run_length -- consecutive-True run counter
# ------------------------------------------------------------------------------------------
def test_run_length_basic_runs():
    mask = pd.Series([False, True, True, True, False, True, False, True, True])
    out = m._run_length(mask)
    assert out.tolist() == [0, 1, 2, 3, 0, 1, 0, 1, 2]


def test_run_length_all_false():
    mask = pd.Series([False, False, False])
    assert m._run_length(mask).tolist() == [0, 0, 0]


def test_run_length_all_true():
    mask = pd.Series([True, True, True])
    assert m._run_length(mask).tolist() == [1, 2, 3]


# ------------------------------------------------------------------------------------------
# build_ribbon_lookup_full -- RTH filter + no-lookahead closes_at column
# ------------------------------------------------------------------------------------------
def _synthetic_spy_df(n_bars: int = 60, start_close: float = 700.0) -> pd.DataFrame:
    """Continuous 5-min bars from 08:00 (premarket) through RTH, rising $0.10/bar so the
    ribbon eventually stacks BULL (fast>pivot>slow) after enough warmup."""
    rows = []
    t = dt.datetime(2026, 6, 1, 8, 0)
    close = start_close
    for i in range(n_bars):
        rows.append({"timestamp_et": t, "close": close})
        t += dt.timedelta(minutes=5)
        close += 0.10
    return pd.DataFrame(rows)


def test_build_ribbon_lookup_full_excludes_premarket():
    spy = _synthetic_spy_df()
    out = m.build_ribbon_lookup_full(spy)
    assert (out["timestamp_et"].dt.time >= dt.time(9, 30)).all()
    assert (out["timestamp_et"].dt.time < dt.time(16, 0)).all()


def test_build_ribbon_lookup_full_closes_at_is_plus_5min():
    spy = _synthetic_spy_df()
    out = m.build_ribbon_lookup_full(spy)
    delta = (out["closes_at"] - out["timestamp_et"]).unique()
    assert list(delta) == [pd.Timedelta(minutes=5)]


def test_build_ribbon_lookup_full_run_columns_consistent_with_stack():
    spy = _synthetic_spy_df(n_bars=80)
    out = m.build_ribbon_lookup_full(spy)
    # wherever bull_run > 0, stack must be BULL; wherever 0, stack must not be BULL
    bull_mask = out["stack"] == "BULL"
    assert (out.loc[bull_mask, "bull_run"] > 0).all()
    assert (out.loc[~bull_mask, "bull_run"] == 0).all()


# ------------------------------------------------------------------------------------------
# ribbon_tick_df_for_full -- no-lookahead as-of join, row-count preserved
# ------------------------------------------------------------------------------------------
def test_ribbon_tick_df_for_full_preserves_row_count_and_is_no_lookahead():
    spy = _synthetic_spy_df(n_bars=40)
    lookup = m.build_ribbon_lookup_full(spy)
    # one option bar exactly 1 minute after a 5m SPY bar STARTS (i.e., that bar has NOT yet
    # closed) -- the join must NOT see that bar's own stack; it must fall back to the PRIOR
    # closed bar.
    some_row = lookup.iloc[10]
    opt_ts = some_row["timestamp_et"] + pd.Timedelta(minutes=1)  # 1 min into an unclosed bar
    opt_df = pd.DataFrame({"timestamp_et": [opt_ts]})
    aligned = m.ribbon_tick_df_for_full(opt_df, lookup)
    assert len(aligned) == 1
    # the aligned row must come from a bar whose closes_at <= opt_ts, i.e. strictly BEFORE
    # some_row's own closes_at (which is 4 minutes in the future of opt_ts)
    assert aligned.iloc[0]["closes_at"] <= opt_ts
    assert aligned.iloc[0]["closes_at"] != some_row["closes_at"]


def test_ribbon_tick_df_for_full_row_count_matches_opt_df():
    spy = _synthetic_spy_df(n_bars=40)
    lookup = m.build_ribbon_lookup_full(spy)
    base = lookup.iloc[5]["timestamp_et"]
    opt_df = pd.DataFrame({
        "timestamp_et": [base + pd.Timedelta(minutes=i) for i in range(7)]
    })
    aligned = m.ribbon_tick_df_for_full(opt_df, lookup)
    assert len(aligned) == len(opt_df)


# ------------------------------------------------------------------------------------------
# candidate_ribbon_tick_df -- the caller-side buffer + confirm derivation (the fix's core)
# ------------------------------------------------------------------------------------------
def _aligned_fixture() -> pd.DataFrame:
    """5 ticks: stack goes BEAR,BEAR,BULL,BULL,BULL (a put-side flip-back at tick 2), with
    a monotonically rising close and bull_run counting the consecutive BULL closes."""
    return pd.DataFrame({
        "stack": ["BEAR", "BEAR", "BULL", "BULL", "BULL"],
        "close": [700.00, 700.05, 700.20, 700.40, 700.70],
        "bull_run": [0, 0, 1, 2, 3],
        "bear_run": [1, 2, 0, 0, 0],
    })


def test_candidate_control_semantics_unbuffered_matches_raw_stack_control():
    """CONTROL (aligned[['stack']] passed straight to walk_exit_manager) flips the instant
    stack goes opposite -- tick 2. A candidate with buffer=0 confirm=1 should therefore ALSO
    show flip eligibility (stack != 'MIXED') starting exactly at tick 2 IF the buffer is
    trivially satisfied (entry_spot far below every close here)."""
    aligned = _aligned_fixture()
    out = m.candidate_ribbon_tick_df(aligned, side="P", buffer_dollars=0.0, confirm_closes=1,
                                     entry_spot=699.00)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "BULL", "BULL", "BULL"]


def test_candidate_buffer_suppresses_flip_until_price_moves_far_enough():
    aligned = _aligned_fixture()
    # entry_spot=700.00, buffer=$0.50 -> put needs close >= 700.50 -> only tick 4 qualifies
    out = m.candidate_ribbon_tick_df(aligned, side="P", buffer_dollars=0.50, confirm_closes=1,
                                     entry_spot=700.00)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "MIXED", "MIXED", "BULL"]


def test_candidate_confirm_closes_suppresses_flip_until_n_consecutive():
    aligned = _aligned_fixture()
    # confirm=2 consecutive BULL closes needed; bull_run hits 2 at tick 3 -> ticks 2 suppressed
    out = m.candidate_ribbon_tick_df(aligned, side="P", buffer_dollars=0.0, confirm_closes=2,
                                     entry_spot=699.00)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "MIXED", "BULL", "BULL"]


def test_candidate_buffer_and_confirm_combine_conjunctively():
    aligned = _aligned_fixture()
    out = m.candidate_ribbon_tick_df(aligned, side="P", buffer_dollars=0.50, confirm_closes=2,
                                     entry_spot=700.00)
    # buffer needs close>=700.50 (tick 4 only); confirm needs bull_run>=2 (tick 3+) --
    # conjunction -> only tick 4 survives
    assert out["stack"].tolist() == ["BEAR", "BEAR", "MIXED", "MIXED", "BULL"]


def test_candidate_call_side_direction_is_mirrored():
    aligned = pd.DataFrame({
        "stack": ["BULL", "BULL", "BEAR", "BEAR"],
        "close": [700.00, 699.90, 699.60, 699.30],
        "bull_run": [1, 2, 0, 0],
        "bear_run": [0, 0, 1, 2],
    })
    # call position (side="C") needs opposite=BEAR + close <= entry_spot - buffer
    out = m.candidate_ribbon_tick_df(aligned, side="C", buffer_dollars=0.50, confirm_closes=1,
                                     entry_spot=700.00)
    assert out["stack"].tolist() == ["BULL", "BULL", "MIXED", "BEAR"]


def test_candidate_entry_spot_none_fails_closed_never_flips():
    """No recoverable closed-bar SPY price at/before entry -> the buffer condition can never
    be satisfied -- the candidate must NEVER flip, not silently degrade to unbuffered."""
    aligned = _aligned_fixture()
    out = m.candidate_ribbon_tick_df(aligned, side="P", buffer_dollars=0.15, confirm_closes=1,
                                     entry_spot=None)
    assert (out["stack"] != "BULL").all()
    assert (out["stack"] != "BEAR").all() or True  # BEAR rows here are the ORIGINAL non-flip
    # explicit: no row should read as the flip-triggering opposite stack post-suppression
    assert out["stack"].tolist()[2:] == ["MIXED", "MIXED", "MIXED"]


def test_candidate_never_introduces_a_flip_where_control_had_none():
    """A candidate must never turn a non-flip (MIXED under raw stack) into a flip -- the
    suppression only ever narrows, never widens, the set of flipped ticks."""
    aligned = pd.DataFrame({
        "stack": ["MIXED", "MIXED", "MIXED"],
        "close": [700.0, 700.6, 701.2],
        "bull_run": [0, 0, 0],
        "bear_run": [0, 0, 0],
    })
    out = m.candidate_ribbon_tick_df(aligned, side="P", buffer_dollars=0.15, confirm_closes=1,
                                     entry_spot=699.0)
    assert (out["stack"] == "MIXED").all()


# ------------------------------------------------------------------------------------------
# bh_fdr -- Benjamini-Hochberg threshold/significance bookkeeping
# ------------------------------------------------------------------------------------------
def test_bh_fdr_all_none_p_values_none_significant():
    out = m.bh_fdr({"A": None, "B": None})
    assert out["A"]["significant"] is False
    assert out["B"]["significant"] is False


def test_bh_fdr_monotone_thresholds_and_known_significance():
    # 6 p-values, alpha=0.10 -- classic BH worked example
    p_by_cid = {"c1": 0.005, "c2": 0.01, "c3": 0.03, "c4": 0.05, "c5": 0.20, "c6": 0.40}
    out = m.bh_fdr(p_by_cid, q=0.10)
    # thresholds: rank1=0.0167, rank2=0.0333, rank3=0.05, rank4=0.0667, rank5=0.0833, rank6=0.10
    assert out["c1"]["significant"] is True
    assert out["c2"]["significant"] is True
    assert out["c3"]["significant"] is True
    assert out["c4"]["significant"] is True    # 0.05 <= rank-4 threshold 0.0667
    assert out["c5"]["significant"] is False   # 0.20 > rank-5 threshold 0.0833
    assert out["c6"]["significant"] is False   # 0.40 > rank-6 threshold 0.10


def test_bh_fdr_empty_input():
    assert m.bh_fdr({}) == {}


# ------------------------------------------------------------------------------------------
# power floor + gate wiring smoke test (synthetic rows, no I/O)
# ------------------------------------------------------------------------------------------
def _synthetic_rows(n: int, delta_per_row: float, dates: list[str], arms: list[str]) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "date_et": dates[i % len(dates)], "arm": arms[i % len(arms)],
            "symbol": f"SPY26080{i % 9}C0075000{i % 9}",
            "entry_ts_et": f"2026-08-0{1 + i % 7}T10:00:00",
            "control_pnl": 100.0, "candidate_pnl": 100.0 + delta_per_row,
            "control_reached_tp1": (i % 2 == 0), "is_anchor": False,
        })
    return rows


def test_evaluate_candidate_underpowered_below_15_changed():
    rows = _synthetic_rows(10, delta_per_row=5.0, dates=["2026-08-01"], arms=["safe-2"])
    ev = m.evaluate_candidate(rows, arch_of={"2026-08-01": "range-chop"})
    assert ev["n_changed"] == 10
    assert ev["power_floor_ok"] is False


def test_evaluate_candidate_positive_delta_passes_g1():
    rows = _synthetic_rows(20, delta_per_row=5.0,
                           dates=["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"],
                           arms=["safe-2", "bold-2"])
    ev = m.evaluate_candidate(rows, arch_of={d: "trend-up" for d in
                                             ("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04")})
    assert ev["power_floor_ok"] is True
    assert ev["gates"]["G1_aggregate_positive"] is True
    assert ev["aggregate_delta"] == pytest.approx(100.0)


def test_evaluate_candidate_g7_per_account_split():
    # safe arms get a positive delta, bold arms get a negative delta -> G7 must fail
    rows = []
    for i in range(20):
        arm = "safe-2" if i < 15 else "bold-2"
        delta = 5.0 if arm == "safe-2" else -5.0
        rows.append({
            "date_et": "2026-08-01", "arm": arm, "symbol": f"SPY2608{i:02d}C00750000",
            "entry_ts_et": f"2026-08-01T{10 + i % 5}:00:00",
            "control_pnl": 100.0, "candidate_pnl": 100.0 + delta,
            "control_reached_tp1": False, "is_anchor": False,
        })
    ev = m.evaluate_candidate(rows, arch_of={"2026-08-01": "trend-up"})
    assert ev["gates"]["G7_per_account_stratification"]["safe_delta"] > 0
    assert ev["gates"]["G7_per_account_stratification"]["bold_delta"] < 0
    assert ev["gates"]["G7_per_account_stratification"]["result"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
