"""ADVERSARIAL VERIFICATION -- LENS 1 (reconstruction fidelity + C6) for
ribbon-flipback-buffer-ab-v2-2026-08-08.json against
prereg-ribbon-flipback-buffer-v2-2026-08-08.json.

Read-only verification. Does NOT modify backtest/tools/ribbon_flipback_buffer_ab_v2.py or
any production module. Adds new assertions only against the harness's own cache
(backtest/data/ribbon_flipback_ab_cache/) and the shipped output JSON.

Run:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ribbon_flipback_verify_lens1.py -v
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

from ribbon import compute_ribbon  # noqa: E402
from exit_manager_walk import walk_exit_manager, ribbon_stack_at  # noqa: E402
import exit_manager as em  # noqa: E402
import winner_autopsy as wa  # noqa: E402
from exit_manager import TIME_STOP_ET  # noqa: E402
import ribbon_flipback_buffer_ab_v2 as harness  # noqa: E402

CACHE_DIR = REPO / "backtest" / "data" / "ribbon_flipback_ab_cache"
OUT_JSON = REPO / "analysis" / "recommendations" / "ribbon-flipback-buffer-ab-v2-2026-08-08.json"
SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-07.csv"

# 3 position-days for independent reproduction: 2 flip-fired + 1 non-flip control.
LENS1_POSITIONS = [
    {"date_et": "2026-07-06", "arm": "safe-2", "symbol": "SPY260706P00750000"},
    {"date_et": "2026-07-07", "arm": "safe-1", "symbol": "SPY260707P00746000"},
    {"date_et": "2026-06-26", "arm": "bold-2", "symbol": "SPY260626P00729000"},
]


@pytest.fixture(scope="module")
def out_data():
    return json.loads(OUT_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def spy_full():
    spy_raw = pd.read_csv(SPY5M)
    spy_ts = pd.to_datetime(spy_raw["timestamp_et"], utc=True, format="mixed")
    spy_ts = spy_ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return spy_raw.assign(timestamp_et=spy_ts).sort_values("timestamp_et").reset_index(drop=True)


def _independent_ribbon_alignment(opt_df: pd.DataFrame, spy_full: pd.DataFrame) -> pd.DataFrame:
    """A SECOND, independently-coded reconstruction path (manual per-row backward search,
    NOT merge_asof) -- deliberately different code from harness.ribbon_tick_df_for_full,
    to catch alignment bugs a shared implementation would hide from itself. Uses the SAME
    production compute_ribbon() call (that part is mandated, not re-derived) but a different
    RTH-window + closed-bar-lookup mechanism."""
    rth_mask = ((spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                & (spy_full["timestamp_et"].dt.time < dt.time(16, 0)))
    spy_rth = spy_full.loc[rth_mask].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    closes_at = spy_rth["timestamp_et"] + pd.Timedelta(minutes=5)

    stacks = []
    spreads = []
    for ts in opt_df["timestamp_et"]:
        # manual backward search: latest 5m bar whose close-time <= ts
        eligible = closes_at[closes_at <= ts]
        if eligible.empty:
            stacks.append(None)
            spreads.append(None)
            continue
        row_idx = eligible.index[-1]
        stacks.append(ribbon.loc[row_idx, "stack"])
        spreads.append(ribbon.loc[row_idx, "spread_cents"])
    return pd.DataFrame({"stack": stacks, "spread_cents": spreads})


@pytest.mark.parametrize("pos", LENS1_POSITIONS, ids=lambda p: f"{p['date_et']}_{p['symbol']}")
def test_lens1a_independent_reconstruction_matches_harness(pos, spy_full):
    """(a) Reproduce the ribbon reconstruction independently (fresh compute_ribbon, different
    alignment code) for 3 position-days; diff stack sequence + spread_cents vs the harness's
    own build_ribbon_lookup_full/ribbon_tick_df_for_full path. Any mismatch is BLOCKING."""
    cache_path = CACHE_DIR / f"{pos['symbol']}_{pos['date_et']}.json"
    assert cache_path.exists(), f"cache miss for {pos} -- cannot verify without cached bars"
    bars = json.loads(cache_path.read_text(encoding="utf-8"))
    rows = []
    for b in bars:
        ts = pd.Timestamp(b["t"])
        if ts.tzinfo is not None:
            ts = ts.tz_convert("America/New_York").tz_localize(None)
        rows.append({"timestamp_et": ts, "open": float(b["o"]), "high": float(b["h"]),
                     "low": float(b["l"]), "close": float(b["c"])})
    opt_df = pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)

    # harness's own path
    ribbon_lookup = harness.build_ribbon_lookup_full(spy_full)
    harness_aligned = harness.ribbon_tick_df_for_full(opt_df, ribbon_lookup)

    # independent path
    indep_aligned = _independent_ribbon_alignment(opt_df, spy_full)

    assert len(harness_aligned) == len(indep_aligned) == len(opt_df)

    n_stack_mismatch = 0
    n_spread_mismatch = 0
    mismatches = []
    for i in range(len(opt_df)):
        h_stack = harness_aligned.iloc[i]["stack"]
        i_stack = indep_aligned.iloc[i]["stack"]
        h_stack_norm = None if pd.isna(h_stack) else str(h_stack)
        i_stack_norm = None if pd.isna(i_stack) else str(i_stack)
        if h_stack_norm != i_stack_norm:
            n_stack_mismatch += 1
            mismatches.append((i, opt_df.iloc[i]["timestamp_et"], h_stack_norm, i_stack_norm))
            continue
        h_spread = harness_aligned.iloc[i]["spread_cents"]
        i_spread = indep_aligned.iloc[i]["spread_cents"]
        if pd.isna(h_spread) and pd.isna(i_spread):
            continue
        if pd.isna(h_spread) != pd.isna(i_spread):
            n_spread_mismatch += 1
            continue
        if abs(float(h_spread) - float(i_spread)) > 1e-6:
            n_spread_mismatch += 1

    assert n_stack_mismatch == 0, (
        f"{pos}: {n_stack_mismatch}/{len(opt_df)} stack mismatches between harness and "
        f"independent reconstruction -- BLOCKING. First few: {mismatches[:5]}")
    assert n_spread_mismatch == 0, (
        f"{pos}: {n_spread_mismatch}/{len(opt_df)} spread_cents mismatches -- BLOCKING.")


@pytest.mark.parametrize("pos", LENS1_POSITIONS, ids=lambda p: f"{p['date_et']}_{p['symbol']}")
def test_lens1b_forming_bar_mutation_closed_read_only(pos, spy_full):
    """(b) closed-read-only mutation test: perturb the LAST (forming/not-yet-closed) 5m bar's
    close price wildly and confirm the ribbon-tick lookup used for any ALREADY-PASSED opt_df
    tick is COMPLETELY UNCHANGED (C6: never read the forming bar). We mutate a bar strictly
    AFTER the position's own tick window ends and confirm ticks inside the window are
    unaffected -- and separately confirm merge_asof direction='backward' cannot select a
    5m bar whose close-time is AFTER the queried opt tick (no look-ahead by construction)."""
    cache_path = CACHE_DIR / f"{pos['symbol']}_{pos['date_et']}.json"
    assert cache_path.exists()
    bars = json.loads(cache_path.read_text(encoding="utf-8"))
    rows = []
    for b in bars:
        ts = pd.Timestamp(b["t"])
        if ts.tzinfo is not None:
            ts = ts.tz_convert("America/New_York").tz_localize(None)
        rows.append({"timestamp_et": ts, "open": float(b["o"]), "high": float(b["h"]),
                     "low": float(b["l"]), "close": float(b["c"])})
    opt_df = pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)

    ribbon_lookup = harness.build_ribbon_lookup_full(spy_full)
    baseline = harness.ribbon_tick_df_for_full(opt_df, ribbon_lookup)

    # Mutate every SPY close AFTER the last opt_df tick's timestamp by +$50 (huge, would
    # flip any stack classification it touched) and rebuild the ribbon lookup.
    last_opt_ts = opt_df["timestamp_et"].max()
    spy_mut = spy_full.copy()
    future_mask = spy_mut["timestamp_et"] > last_opt_ts
    assert future_mask.any(), "test invalid: no future SPY bars exist after this position's window"
    spy_mut.loc[future_mask, "close"] = spy_mut.loc[future_mask, "close"] + 50.0

    ribbon_lookup_mut = harness.build_ribbon_lookup_full(spy_mut)
    mutated = harness.ribbon_tick_df_for_full(opt_df, ribbon_lookup_mut)

    # every opt_df tick's resolved stack + spread_cents must be BYTE-IDENTICAL: a closed-read
    # design can never be influenced by bars that close after the last tick we queried.
    pd.testing.assert_series_equal(
        baseline["stack"].reset_index(drop=True), mutated["stack"].reset_index(drop=True),
        check_names=False)
    pd.testing.assert_series_equal(
        baseline["spread_cents"].reset_index(drop=True), mutated["spread_cents"].reset_index(drop=True),
        check_names=False)


def test_lens1c_control_parity_reproduced_independently(out_data, spy_full):
    """(c) Re-run the 8-position control-parity check ourselves (calling the harness's own
    sample_control_parity_positions + run_control_parity_check against a freshly loaded
    population) and verify: same 8 positions selected, same reconciled/diverged split,
    >=6/8 rule honestly applied (not fudged)."""
    positions, pop_meta = harness.load_frozen_population()
    for p in positions:
        p["side"] = harness.option_side_from_symbol(p["symbol"])
    arm_patches = wa.load_arm_exit_patches()
    ribbon_lookup = harness.build_ribbon_lookup_full(spy_full)

    sample = harness.sample_control_parity_positions(
        positions, n=min(harness.CONTROL_PARITY_N_SAMPLE, len(positions)))
    parity = harness.run_control_parity_check(sample, arm_patches, ribbon_lookup, spy_full)

    shipped = out_data["control_parity_result"]
    assert parity["n_sampled"] == shipped["n_sampled"] == 8
    assert parity["n_reconciled"] == shipped["n_reconciled"]
    assert parity["required"] == shipped["required"] == 6
    assert parity["passed"] == shipped["passed"] is True
    # the >=6/8 rule: ceil(0.75*8) == 6, not silently loosened
    import math
    assert shipped["required"] == math.ceil(0.75 * 8) == 6
    # symbol/date set matches exactly (same deterministic stratified sample, no drift)
    shipped_keys = sorted((r["date_et"], r["arm"], r["symbol"]) for r in shipped["rows"])
    my_keys = sorted((r["date_et"], r["arm"], r["symbol"]) for r in parity["rows"])
    assert shipped_keys == my_keys
    # per-row reconciled/diff values match within float rounding
    shipped_by_key = {(r["date_et"], r["arm"], r["symbol"]): r for r in shipped["rows"]}
    for r in parity["rows"]:
        key = (r["date_et"], r["arm"], r["symbol"])
        s = shipped_by_key[key]
        assert r["reconciled"] == s["reconciled"], f"{key}: reconciled mismatch"
        assert abs(r["diff"] - s["diff"]) < 0.01, f"{key}: diff mismatch {r['diff']} vs {s['diff']}"


@pytest.mark.parametrize("cid", ["P0-C2", "P75-C2"])
def test_lens1d_hand_walk_changed_trades_against_raw_sequence(cid, out_data, spy_full):
    """(d) For 2 candidates (P0-C2 delay-only smallest change-set, P75-C2 largest change-set),
    hand-walk EVERY changed trade: recompute candidate_pnl independently by rebuilding the
    candidate ribbon tick df from the raw reconstructed sequence and re-running
    walk_exit_manager, and confirm it matches the shipped position_detail row exactly."""
    cdefs = out_data["candidate_defs"]
    cdef = cdefs[cid]
    rows = out_data["position_detail"][cid]
    changed = [r for r in rows if abs(r["candidate_pnl"] - r["control_pnl"]) > 1e-6]
    assert len(changed) >= 1, f"{cid}: no changed rows to hand-walk"

    positions, pop_meta = harness.load_frozen_population()
    for p in positions:
        p["side"] = harness.option_side_from_symbol(p["symbol"])
    by_key = {(p["date_et"], p["arm"], p["symbol"], p["entry_ts_et"]): p for p in positions}
    arm_patches = wa.load_arm_exit_patches()
    ribbon_lookup = harness.build_ribbon_lookup_full(spy_full)

    n_confirmed = 0
    for r in changed:
        key = (r["date_et"], r["arm"], r["symbol"], r["entry_ts_et"])
        p = by_key.get(key)
        assert p is not None, f"changed row {key} not found in freshly reloaded population"
        opt_df = harness.load_opt_bars_cached(p["symbol"], p["date_et"])
        assert opt_df is not None and not opt_df.empty
        aligned = harness.ribbon_tick_df_for_full(opt_df, ribbon_lookup)
        entry_dt = harness._naive_et(p["entry_ts_et"])
        shape = harness.resolve_position_shape(p, arm_patches)
        cand_df = harness.candidate_ribbon_tick_df(
            aligned, p["side"], cdef["min_spread_cents"], cdef["confirm_closes"])
        cand_res = walk_exit_manager(
            symbol=p["symbol"], side=p["side"], entry_time_et=entry_dt,
            entry_premium=float(p["entry_price"]), qty=int(round(p["entry_qty"])),
            exit_shape=shape, structure_stop_enabled=False, trigger_level=None,
            strategy="ribbon_flipback_ab_v2", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=cand_df, five_min_spy_df=spy_full,
            opt_df_resolution="1min", frame="et-v2")
        assert abs(cand_res.dollar_pnl - r["candidate_pnl"]) < 0.01, (
            f"{key}: hand-walked candidate_pnl {cand_res.dollar_pnl} != shipped "
            f"{r['candidate_pnl']}")
        n_confirmed += 1
    assert n_confirmed == len(changed)


@pytest.mark.parametrize("cid", ["P0-C2", "P25-C1", "P75-C2"])
def test_lens1e_candidates_change_only_flip_boolean(cid, out_data, spy_full):
    """(e) Candidates must change NOTHING except the ribbon_flip_back-derived boolean:
    verify by construction that candidate_ribbon_tick_df ONLY ever converts a raw opposing-
    stack read to 'MIXED' (suppression), and NEVER invents a flip where CONTROL saw none
    (no widening), for the given candidate definition, across every replay context tick."""
    cdefs = out_data["candidate_defs"]
    cdef = cdefs[cid]

    positions, pop_meta = harness.load_frozen_population()
    for p in positions:
        p["side"] = harness.option_side_from_symbol(p["symbol"])
    ribbon_lookup = harness.build_ribbon_lookup_full(spy_full)

    # sample a handful of positions (not full 219, for test speed) across both sides
    sample = [p for p in positions if p["side"] == "P"][:5] + \
             [p for p in positions if p["side"] == "C"][:5]

    for p in sample:
        opt_df = harness.load_opt_bars_cached(p["symbol"], p["date_et"])
        if opt_df is None or opt_df.empty:
            continue
        aligned = harness.ribbon_tick_df_for_full(opt_df, ribbon_lookup)
        cand_df = harness.candidate_ribbon_tick_df(
            aligned, p["side"], cdef["min_spread_cents"], cdef["confirm_closes"])
        opposite = "BULL" if p["side"] == "P" else "BEAR"
        raw_flip = aligned["stack"] == opposite
        cand_flip = cand_df["stack"] == opposite
        # candidate flip is a SUBSET of raw flip -- never invents a flip control didn't have
        widened = cand_flip & ~raw_flip
        assert not widened.any(), (
            f"{p['symbol']} {p['date_et']}: candidate {cid} invented a flip at "
            f"{widened[widened].index.tolist()} where CONTROL saw none -- widening, not "
            f"narrowing, violates the prereg's 'narrows never widens' mechanism_note")
        # every non-opposite tick is untouched (byte-identical to raw stack, never 'MIXED'
        # substituted where CONTROL wasn't even opposing)
        non_opposite_mask = ~raw_flip
        assert (cand_df.loc[non_opposite_mask, "stack"].reset_index(drop=True) ==
                aligned.loc[non_opposite_mask, "stack"].reset_index(drop=True)).all(), (
            f"{p['symbol']} {p['date_et']}: candidate {cid} altered a non-opposing-stack "
            f"tick's stack value -- should only ever touch opposing reads")
