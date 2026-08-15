"""Guard tests for backtest/tools/ribbon_flipback_buffer_ab_v2.py -- the v2 ribbon-flip-back
DECISIVENESS A/B (spread_cents threshold x confirm-closes),
analysis/recommendations/prereg-ribbon-flipback-buffer-v2-2026-08-08.json.

Pure-function coverage only: no network, no broker, no fetching of real OPRA bars (the ONE
exception -- test_mae_mfe_frozen_population_size -- reads the already-on-disk frozen JSON
ledger, no network). Every other test constructs small synthetic DataFrames/dicts so the run
is instant and deterministic.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ribbon_flipback_ab_v2.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_flipback_buffer_ab_v2 as m  # noqa: E402


# ------------------------------------------------------------------------------------------
# _naive_et -- timestamp normalization
# ------------------------------------------------------------------------------------------
def test_naive_et_strips_z_and_shifts_utc_to_et():
    d = m._naive_et("2026-06-26T18:53:49.640000Z")
    assert d == dt.datetime(2026, 6, 26, 14, 53, 49, 640000)


def test_naive_et_passthrough_naive_string():
    d = m._naive_et("2026-06-26T14:53:49.640000")
    assert d == dt.datetime(2026, 6, 26, 14, 53, 49, 640000)


# ------------------------------------------------------------------------------------------
# _run_length -- consecutive-True run counter (shared with v1, re-verified here)
# ------------------------------------------------------------------------------------------
def test_run_length_basic_runs():
    mask = pd.Series([False, True, True, True, False, True, False, True, True])
    assert m._run_length(mask).tolist() == [0, 1, 2, 3, 0, 1, 0, 1, 2]


def test_run_length_all_false():
    assert m._run_length(pd.Series([False, False, False])).tolist() == [0, 0, 0]


def test_run_length_all_true():
    assert m._run_length(pd.Series([True, True, True])).tolist() == [1, 2, 3]


# ------------------------------------------------------------------------------------------
# build_ribbon_lookup_full -- RTH filter + no-lookahead closes_at column + lookup_idx identity
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
    out = m.build_ribbon_lookup_full(_synthetic_spy_df())
    assert (out["timestamp_et"].dt.time >= dt.time(9, 30)).all()
    assert (out["timestamp_et"].dt.time < dt.time(16, 0)).all()


def test_build_ribbon_lookup_full_closes_at_is_plus_5min():
    out = m.build_ribbon_lookup_full(_synthetic_spy_df())
    delta = (out["closes_at"] - out["timestamp_et"]).unique()
    assert list(delta) == [pd.Timedelta(minutes=5)]


def test_build_ribbon_lookup_full_run_columns_consistent_with_stack():
    out = m.build_ribbon_lookup_full(_synthetic_spy_df(n_bars=80))
    bull_mask = out["stack"] == "BULL"
    assert (out.loc[bull_mask, "bull_run"] > 0).all()
    assert (out.loc[~bull_mask, "bull_run"] == 0).all()


def test_build_ribbon_lookup_full_lookup_idx_monotonic_row_identity():
    out = m.build_ribbon_lookup_full(_synthetic_spy_df(n_bars=30))
    assert out["lookup_idx"].tolist() == list(range(len(out)))


# ------------------------------------------------------------------------------------------
# ribbon_tick_df_for_full -- no-lookahead as-of join, row-count preserved, closed-read-only
# carry-forward (C6: every 1-min row carries the most recent CLOSED 5m read, never forming)
# ------------------------------------------------------------------------------------------
def test_ribbon_tick_df_for_full_row_count_matches_opt_df():
    lookup = m.build_ribbon_lookup_full(_synthetic_spy_df(n_bars=40))
    base = lookup.iloc[5]["timestamp_et"]
    opt_df = pd.DataFrame({"timestamp_et": [base + pd.Timedelta(minutes=i) for i in range(7)]})
    aligned = m.ribbon_tick_df_for_full(opt_df, lookup)
    assert len(aligned) == len(opt_df)


def test_ribbon_tick_df_for_full_carries_forward_only_within_closed_window():
    """The reconstruction-alignment closed-read-only mutation test: ticks that land INSIDE a
    5m bar's own still-forming window must carry the PRIOR closed read, never that bar's own
    (not-yet-closed) stack -- and the tick that lands EXACTLY at that bar's own close must
    finally pick it up."""
    # n_bars=110 / indices 55,56 chosen so BOTH reads are past full EMA warmup (slow period
    # 48) -- spread_cents is non-NaN for both, so the carry-forward assertion below is a real
    # numeric check, not a NaN==NaN vacuous pass.
    lookup = m.build_ribbon_lookup_full(_synthetic_spy_df(n_bars=110))
    r_prev = lookup.iloc[55]
    r = lookup.iloc[56]
    opt_ts = [r["timestamp_et"] + pd.Timedelta(minutes=k) for k in (1, 2, 3, 4, 5)]
    opt_df = pd.DataFrame({"timestamp_et": opt_ts})
    aligned = m.ribbon_tick_df_for_full(opt_df, lookup)
    # +1..+4 min into r's own formation (r has NOT yet closed) -> must carry r_prev, not r
    assert (aligned["stack"].iloc[:4] == r_prev["stack"]).all()
    assert (aligned["spread_cents"].iloc[:4] == r_prev["spread_cents"]).all()
    # +5 min == r's own close -> r itself is now picked up
    assert aligned["stack"].iloc[4] == r["stack"]
    assert aligned["spread_cents"].iloc[4] == r["spread_cents"]
    assert aligned["lookup_idx"].iloc[4] == r["lookup_idx"]


# ------------------------------------------------------------------------------------------
# candidate_ribbon_tick_df -- the v2 decisiveness filter: spread_cents threshold x
# confirm-closes, conjunctive, re-evaluated fresh at every tick (no persisted state)
# ------------------------------------------------------------------------------------------
def _aligned_fixture() -> pd.DataFrame:
    """5 ticks: stack goes BEAR,BEAR,BULL,BULL,BULL (a put-side flip at tick 2). spread_cents
    is DELIBERATELY below the test threshold at tick 3 (20) but above it at tick 4 (80), so
    threshold and confirm-closes tests can be told apart from their conjunction."""
    return pd.DataFrame({
        "stack": ["BEAR", "BEAR", "BULL", "BULL", "BULL"],
        "spread_cents": [40.0, 45.0, 10.0, 20.0, 80.0],
        "bull_run": [0, 0, 1, 2, 3],
        "bear_run": [1, 2, 0, 0, 0],
    })


def test_candidate_control_equivalent_threshold0_confirm1_matches_raw_stack():
    out = m.candidate_ribbon_tick_df(_aligned_fixture(), side="P", min_spread_cents=0.0,
                                     confirm_closes=1)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "BULL", "BULL", "BULL"]


def test_candidate_spread_threshold_alone_suppresses_until_decisive():
    out = m.candidate_ribbon_tick_df(_aligned_fixture(), side="P", min_spread_cents=50.0,
                                     confirm_closes=1)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "MIXED", "MIXED", "BULL"]


def test_candidate_confirm_closes_alone_suppresses_until_n_consecutive():
    out = m.candidate_ribbon_tick_df(_aligned_fixture(), side="P", min_spread_cents=0.0,
                                     confirm_closes=2)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "MIXED", "BULL", "BULL"]


def test_candidate_threshold_and_confirm_combine_conjunctively():
    """confirm_closes=2 is satisfied starting tick 3 (bull_run==2) but spread_cents=20 < 50
    at tick 3 -- the conjunction must still suppress tick 3, only clearing at tick 4 where
    BOTH conditions hold simultaneously."""
    out = m.candidate_ribbon_tick_df(_aligned_fixture(), side="P", min_spread_cents=50.0,
                                     confirm_closes=2)
    assert out["stack"].tolist() == ["BEAR", "BEAR", "MIXED", "MIXED", "BULL"]


def test_candidate_call_side_direction_is_mirrored():
    aligned = pd.DataFrame({
        "stack": ["BULL", "BULL", "BEAR", "BEAR"],
        "spread_cents": [40.0, 45.0, 10.0, 80.0],
        "bull_run": [1, 2, 0, 0],
        "bear_run": [0, 0, 1, 2],
    })
    out = m.candidate_ribbon_tick_df(aligned, side="C", min_spread_cents=50.0, confirm_closes=1)
    assert out["stack"].tolist() == ["BULL", "BULL", "MIXED", "BEAR"]


def test_candidate_nan_spread_fails_closed_never_flips():
    """A WARMUP/NaN spread_cents read can never satisfy the decisiveness gate -- fail CLOSED
    (C7), never a silent pass-through of missing data."""
    aligned = pd.DataFrame({
        "stack": ["BEAR", "BULL", "BULL"],
        "spread_cents": [40.0, float("nan"), float("nan")],
        "bull_run": [0, 1, 2],
        "bear_run": [1, 0, 0],
    })
    out = m.candidate_ribbon_tick_df(aligned, side="P", min_spread_cents=0.0, confirm_closes=1)
    assert out["stack"].tolist() == ["BEAR", "MIXED", "MIXED"]


def test_candidate_never_introduces_a_flip_where_raw_had_none():
    aligned = pd.DataFrame({
        "stack": ["MIXED", "MIXED", "MIXED"],
        "spread_cents": [40.0, 90.0, 120.0],
        "bull_run": [0, 0, 0],
        "bear_run": [0, 0, 0],
    })
    out = m.candidate_ribbon_tick_df(aligned, side="P", min_spread_cents=0.0, confirm_closes=1)
    assert (out["stack"] == "MIXED").all()


# ------------------------------------------------------------------------------------------
# pin_percentiles -- deterministic percentile pinning (pandas linear-interpolation quantile)
# ------------------------------------------------------------------------------------------
def test_pin_percentiles_known_values():
    reads = [{"spread_cents": float(v)} for v in range(10, 101, 10)]  # 10,20,...,100
    out = m.pin_percentiles(reads)
    assert out["n"] == 10
    assert out["p25"] == pytest.approx(32.5)
    assert out["p50"] == pytest.approx(55.0)
    assert out["p75"] == pytest.approx(77.5)
    assert out["min"] == 10.0
    assert out["max"] == 100.0


def test_pin_percentiles_empty_corpus():
    out = m.pin_percentiles([])
    assert out == {"n": 0, "p25": None, "p50": None, "p75": None, "min": None, "max": None}


def test_pin_percentiles_deterministic_across_calls():
    reads = [{"spread_cents": v} for v in [15.5, 92.0, 33.3, 61.1, 47.0]]
    out1 = m.pin_percentiles(reads)
    out2 = m.pin_percentiles(list(reversed(reads)))
    assert out1 == out2


# ------------------------------------------------------------------------------------------
# build_candidate_defs -- {0,p25,p50,p75} x {1,2} minus (0,1)=CONTROL == 7 candidates
# ------------------------------------------------------------------------------------------
def test_build_candidate_defs_full_grid_is_7_candidates_excludes_control():
    pcts = {"n": 100, "p25": 30.0, "p50": 50.0, "p75": 70.0, "min": 5.0, "max": 200.0}
    defs = m.build_candidate_defs(pcts)
    assert len(defs) == 7
    assert "P0-C1" not in defs  # == CONTROL, excluded per the frozen grid
    assert defs["P0-C2"] == {"min_spread_cents": 0.0, "confirm_closes": 2, "threshold_label": "P0"}
    assert defs["P25-C1"]["min_spread_cents"] == 30.0
    assert defs["P75-C2"]["confirm_closes"] == 2


def test_build_candidate_defs_empty_percentiles_degrades_gracefully():
    pcts = {"n": 0, "p25": None, "p50": None, "p75": None, "min": None, "max": None}
    defs = m.build_candidate_defs(pcts)
    assert list(defs.keys()) == ["P0-C2"]


# ------------------------------------------------------------------------------------------
# sample_control_parity_positions -- deterministic stratified round-robin sample
# ------------------------------------------------------------------------------------------
def _pos(date: str, arm: str, symbol: str, outcome: str) -> dict:
    return {"date_et": date, "entry_ts_et": date + "T10:00:00", "arm": arm, "symbol": symbol,
            "mae_mfe_outcome": outcome}


def test_sample_control_parity_positions_deterministic_round_robin():
    positions = [
        _pos("2026-06-26", "bold-2", "A", "loser"),
        _pos("2026-06-27", "bold-2", "B", "loser"),
        _pos("2026-06-28", "safe-2", "C", "loser"),
        _pos("2026-06-29", "safe-2", "D", "winner"),
        _pos("2026-06-30", "bold-2", "E", "winner"),
        _pos("2026-07-01", "safe-2", "F", "scratch"),
    ]
    sample = m.sample_control_parity_positions(positions, n=4)
    # buckets sorted: ('loser','bold')=[A,B] < ('loser','safe')=[C] < ('scratch','safe')=[F]
    # < ('winner','bold')=[E] < ('winner','safe')=[D] -- round-robin picks A,C,F,E then stops
    assert [p["symbol"] for p in sample] == ["A", "C", "F", "E"]


def test_sample_control_parity_positions_reproducible():
    positions = [_pos(f"2026-07-{d:02d}", "safe-2" if d % 2 else "bold-2", f"S{d}",
                      "winner" if d % 3 == 0 else "loser") for d in range(1, 20)]
    s1 = [p["symbol"] for p in m.sample_control_parity_positions(positions, n=8)]
    s2 = [p["symbol"] for p in m.sample_control_parity_positions(positions, n=8)]
    assert s1 == s2
    assert len(s1) == 8


def test_sample_control_parity_positions_never_exceeds_population():
    positions = [_pos("2026-07-01", "safe-2", "ONLY", "loser")]
    sample = m.sample_control_parity_positions(positions, n=8)
    assert len(sample) == 1


# ------------------------------------------------------------------------------------------
# whipsaw_base_rate -- un-flip-within-1-2-reads market statistic
# ------------------------------------------------------------------------------------------
def test_whipsaw_base_rate_immediate_unflip():
    lookup = pd.DataFrame({"stack": ["BULL", "BULL", "BEAR", "BULL", "BEAR", "BEAR"]})
    reads = [{"lookup_idx": 1, "side": "P"}, {"lookup_idx": 3, "side": "P"}]
    out = m.whipsaw_base_rate(reads, lookup)
    assert out["n_flip_reads"] == 2
    assert out["n_unflip_within_1_read"] == 2
    assert out["whipsaw_rate_1_read"] == pytest.approx(1.0)
    assert out["whipsaw_rate_within_2_reads"] == pytest.approx(1.0)


def test_whipsaw_base_rate_persistent_flip_never_unflips():
    lookup = pd.DataFrame({"stack": ["BULL", "BULL", "BULL"]})
    reads = [{"lookup_idx": 0, "side": "P"}]
    out = m.whipsaw_base_rate(reads, lookup)
    assert out["n_unflip_within_1_read"] == 0
    assert out["whipsaw_rate_1_read"] == pytest.approx(0.0)
    assert out["whipsaw_rate_within_2_reads"] == pytest.approx(0.0)


def test_whipsaw_base_rate_unflips_only_on_second_read():
    lookup = pd.DataFrame({"stack": ["BULL", "BULL", "BEAR"]})
    reads = [{"lookup_idx": 0, "side": "P"}]
    out = m.whipsaw_base_rate(reads, lookup)
    assert out["n_unflip_within_1_read"] == 0     # idx+1 still BULL
    assert out["n_unflip_within_2_reads"] == 1     # idx+2 is BEAR
    assert out["whipsaw_rate_1_read"] == pytest.approx(0.0)
    assert out["whipsaw_rate_within_2_reads"] == pytest.approx(1.0)


def test_whipsaw_base_rate_lookup_exhausted_excluded_from_denominator():
    lookup = pd.DataFrame({"stack": ["BULL", "BULL"]})
    reads = [{"lookup_idx": 1, "side": "P"}]  # idx+1 is out of range
    out = m.whipsaw_base_rate(reads, lookup)
    assert out["n_lookup_exhausted"] == 1
    assert out["whipsaw_rate_1_read"] is None  # denom == 0


# ------------------------------------------------------------------------------------------
# bh_fdr -- Benjamini-Hochberg threshold/significance bookkeeping (shared mechanism w/ v1)
# ------------------------------------------------------------------------------------------
def test_bh_fdr_all_none_p_values_none_significant():
    out = m.bh_fdr({"A": None, "B": None})
    assert out["A"]["significant"] is False
    assert out["B"]["significant"] is False


def test_bh_fdr_monotone_thresholds_and_known_significance():
    p_by_cid = {"c1": 0.005, "c2": 0.01, "c3": 0.03, "c4": 0.05, "c5": 0.20, "c6": 0.40}
    out = m.bh_fdr(p_by_cid, q=0.10)
    assert out["c1"]["significant"] is True
    assert out["c4"]["significant"] is True
    assert out["c5"]["significant"] is False
    assert out["c6"]["significant"] is False


def test_bh_fdr_empty_input():
    assert m.bh_fdr({}) == {}


# ------------------------------------------------------------------------------------------
# evaluate_candidate -- gate arithmetic fixtures (power floor, G1, G7)
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


# ------------------------------------------------------------------------------------------
# population parity with mae-mfe.json counts
# ------------------------------------------------------------------------------------------
# The frozen population's own as-of boundary, DERIVED not guessed: mae-mfe.json is append-only
# and had grown 219 -> 303 by 2026-08-15, so this pinned a moving target and had been RED (and
# blind) since the ledger passed 219. Counting by date, trades through **2026-08-07** total
# exactly 219 -- that is the study's real population edge. L292 again: the monitor's coverage
# scope rots exactly like the thing it monitors.
MAE_MFE_ANCHOR_ASOF_ET = "2026-08-07"


def test_mae_mfe_frozen_population_size():
    """The frozen population this study MUST match: 219 scored engine positions, per the
    prereg's population_and_engine clause. Pure JSON read, no network -- catches accidental
    drift in the on-disk ledger the harness pins against.

    Bounded to the population's own as-of date (see above) so that APPENDING new trades -- the
    ledger's normal behaviour, not a defect -- no longer reads as drift, while a change to the
    already-frozen rows still fails loudly. That distinction is the whole point of the tripwire.
    """
    data = json.loads(m.MAE_MFE.read_text(encoding="utf-8"))
    frozen = [t for t in data["trades"] if str(t.get("date", ""))[:10] <= MAE_MFE_ANCHOR_ASOF_ET]
    assert len(frozen) == 219, (
        f"the FROZEN slice (<= {MAE_MFE_ANCHOR_ASOF_ET}) is {len(frozen)}, not 219 -- rows "
        "inside the study's own population changed, which invalidates its results")
    assert len(data["trades"]) >= 219, "mae-mfe.json SHRANK -- the ledger lost history"


def test_load_frozen_population_matches_and_excludes_unmatched(monkeypatch, tmp_path):
    mae_mfe = {
        "_meta": {},
        "trades": [
            {"date": "2026-06-26", "arm": "bold-2", "symbol": "SYM1",
             "entry_ts_utc": "2026-06-26T18:00:00.000000Z", "outcome": "loser",
             "stop": {"stop_mode_source": "unrecoverable"}},
            {"date": "2026-06-27", "arm": "safe-2", "symbol": "SYM2",
             "entry_ts_utc": "2026-06-27T18:00:00.000000Z", "outcome": "winner",
             "stop": {"stop_mode_source": "unrecoverable"}},
        ],
    }
    mae_path = tmp_path / "mae-mfe.json"
    mae_path.write_text(json.dumps(mae_mfe), encoding="utf-8")
    monkeypatch.setattr(m, "MAE_MFE", mae_path)

    fills = [
        # SYM1 -- matches mae_mfe trade #1 exactly (date/arm/symbol/entry_ts_utc)
        {"arm": "bold-2", "symbol": "SYM1", "side": "buy", "qty": 5, "price": 0.2,
         "ts_utc": "2026-06-26T18:00:00.000000Z", "ts_et": "2026-06-26T14:00:00",
         "date_et": "2026-06-26"},
        {"arm": "bold-2", "symbol": "SYM1", "side": "sell", "qty": 5, "price": 0.1,
         "ts_utc": "2026-06-26T18:05:00.000000Z", "ts_et": "2026-06-26T14:05:00",
         "date_et": "2026-06-26"},
        # SYM3 -- a reconstructed position with NO matching mae_mfe target key; must be
        # excluded from the matched population, never silently dropped from the counters
        {"arm": "safe-2", "symbol": "SYM3", "side": "buy", "qty": 3, "price": 0.5,
         "ts_utc": "2026-06-28T18:00:00.000000Z", "ts_et": "2026-06-28T14:00:00",
         "date_et": "2026-06-28"},
        {"arm": "safe-2", "symbol": "SYM3", "side": "sell", "qty": 3, "price": 0.4,
         "ts_utc": "2026-06-28T18:05:00.000000Z", "ts_et": "2026-06-28T14:05:00",
         "date_et": "2026-06-28"},
    ]
    monkeypatch.setattr(m.esp, "load_fleet_engine_fills", lambda arms=None: fills)

    positions, meta = m.load_frozen_population()

    assert meta["n_frozen_target"] == 2
    assert meta["n_reconstructed_total"] == 2
    assert meta["n_matched"] == 1
    assert meta["n_unmatched_target_keys"] == 1
    assert len(positions) == 1
    assert positions[0]["symbol"] == "SYM1"
    assert positions[0]["mae_mfe_outcome"] == "loser"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
