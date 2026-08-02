"""Guard for backtest/tools/bold_fullhist_replay.py (Bold full-history production-parity
replay, analysis/deep-research/BOLD-HARNESS-2026-08-01.md, WEEKEND-TWELVE Next-Twelve #8).

Load-bearing invariants this guard pins -- each one is a knob the translation audit found
that a naive "copy Safe's tool, swap the params file" port would have gotten WRONG:

  1. SIZING RED-PROOF (task requirement: "a deliberately mistranslated knob must fail the
     parity anchor test"): resolve_bold_qty must return Bold's REAL min_contracts (5), not
     Safe's (3) or run_backtest's internal DEFAULT_QTY (3, dead per the tool's own
     docstring finding #1). A concrete end-to-end proof: replaying one real anchor fill at
     the CORRECT qty=5 passes tolerance; replaying the SAME anchor at the WRONG qty=3
     (Safe's min_contracts -- a plausible copy-paste mistranslation) FAILS tolerance. This
     is not a synthetic assertion -- it runs the real walk_exit_manager both ways.
  2. STRIKE SIGN-CONVENTION RED-PROOF: crypto/lib/strike_selection.py's live-params
     convention (positive=ITM) must be NEGATED before reaching orchestrator.run_backtest's
     simulator-convention kwargs (negative=ITM). A non-negated (mistranslated) offset would
     silently invert ITM/OTM for any Bold equity tier above $2,000.
  3. EXIT-SHAPE-PARITY: bold_fullhist_replay.py must derive P&L from the REAL
     strategies.py#RIBBON_RIDE.exit.to_dict() shape (profit_lock_mode="trailing",
     stop_mode="structure") -- the SAME shape Safe's tool uses, never aggressive/
     params.json's own top-level keys (which are vestigial for the core ribbon_ride path,
     see the tool's docstring finding #3).
  4. GATE_KEYS TRANSLATION PINS: every value in bold_base_live() that differs from Safe's
     SAFE_BASE_LIVE is pinned here against automation/state/aggressive/params.json's
     on-disk values, so a future params edit that isn't mirrored into this tool's
     translation table fails loudly instead of silently drifting.
  5. GATE STATE IS AN INPUT: block_elite_bull must be threaded through as a parameter, not
     hardcoded -- bold_base_live(True) and bold_base_live(False) must differ ONLY in that
     one key.
  6. ANCHOR REPRODUCTION: >=5 real bold-2 ENGINE-attributed fills (task requirement) must
     reproduce within the documented tolerance.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bold_fullhist_replay.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
CRYPTO_LIB = REPO / "crypto" / "lib"
for _p in (REPO, BACKTEST, BACKTEST / "tools", FLEET_DIR, CRYPTO_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import bold_fullhist_replay as bfr  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.et_frame import FRAME_ET_V2  # noqa: E402

AGGRESSIVE_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
SAFE_PARAMS = REPO / "automation" / "state" / "params.json"
DATA_AVAILABLE = bfr.SPY_FILE.exists() and bfr.VIX_FILE.exists()


# ---------------------------------------------------------------------------------------- #
# 1. SIZING RED-PROOF
# ---------------------------------------------------------------------------------------- #
def test_resolve_bold_qty_uses_bold_min_contracts_not_safe():
    """The load-bearing sizing formula: qty = min_contracts, not run_backtest's internal
    (dead, always-3) scaling. Bold's real min_contracts is 5; Safe's is 3 -- they must NOT
    silently coincide for a normal, affordable premium."""
    assert bfr.resolve_bold_qty(1.00, equity=10_000, min_contracts=5) == 5
    assert bfr.resolve_bold_qty(1.00, equity=10_000, min_contracts=3) == 3
    # never resizes DOWN from the floor -- either the floor fits or the trade is excluded
    assert bfr.resolve_bold_qty(1.00, equity=10_000, min_contracts=5) != 3


def test_resolve_bold_qty_excludes_never_downsizes():
    """Live risk_gate.check_order denies an order it can't afford at min_contracts -- it
    NEVER auto-shrinks below the floor (module docstring finding #1). At tiny equity with
    an expensive premium, resolve_bold_qty must return None (excluded), not some qty < 5."""
    # equity=$100, cap 50% = $50; premium=$5 x 5 contracts x 100 = $2,500 notional -- unaffordable
    out = bfr.resolve_bold_qty(5.00, equity=100.0, per_trade_risk_cap_pct=0.50, min_contracts=5)
    assert out is None, "unaffordable-at-floor must exclude the trade, never downsize it"


def test_bold_min_contracts_constant_matches_aggressive_params_json():
    """Pins the translation-table's headline number against the live source file. If Bold's
    min_contracts ever changes in aggressive/params.json without this constant being
    updated, this must fail loudly (not silently keep grading trades at a stale qty)."""
    params = json.loads(AGGRESSIVE_PARAMS.read_text(encoding="utf-8"))
    assert params["min_contracts"] == bfr.BOLD_MIN_CONTRACTS == 5
    safe_params = json.loads(SAFE_PARAMS.read_text(encoding="utf-8"))
    assert safe_params["min_contracts"] == 3
    assert bfr.BOLD_MIN_CONTRACTS != safe_params["min_contracts"], (
        "Bold and Safe min_contracts must NOT coincide -- a harness that grades Bold trades "
        "at Safe's floor is exactly the C14 dead-knob trap this tool exists to avoid")


@pytest.mark.skipif(not DATA_AVAILABLE, reason="requires merged SPY/VIX data")
def test_mistranslated_qty_fails_the_anchor_where_correct_qty_passes():
    """END-TO-END RED-PROOF (task requirement, not a unit-test stand-in): replay a REAL
    bold-2 anchor fill (2026-07-27 P737, real_pnl=-$355.00) through the actual
    walk_exit_manager at the CORRECT qty=5 (passes tolerance) and again at the WRONG qty=3
    (a plausible Safe-min_contracts mistranslation) and prove the wrong qty fails."""
    anchor = next(a for a in bfr.ANCHOR_FILLS if a["symbol"] == "SPY260727P00737000")
    opt_df = load_contract_bars(anchor["symbol"])
    if opt_df is None:
        pytest.skip("SPY260727P00737000 OPRA cache not present in this environment")
    spy5_path = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
    spy_df = pd.read_csv(spy5_path)
    ts = pd.to_datetime(spy_df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    spy_df = spy_df.assign(timestamp_et=ts.dt.tz_localize(None))
    day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == dt.date(2026, 7, 27)].reset_index(drop=True)
    shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    entry_time_et = dt.datetime.fromisoformat(anchor["entry_ts_et"])
    trigger_levels = bfr._load_trigger_levels_from_decisions()
    trigger_level = trigger_levels.get((anchor["symbol"], anchor["entry_ts_et"]))

    def replay_at(qty: int) -> float:
        # frame="et-v2" (2026-08-02, DST-FRAME-BLAST-RADIUS-2026-08-02): spy_df above is
        # et-v2-parsed and entry_time_et is a real fill ISO timestamp (true-ET) -- matches
        # bold_fullhist_replay.py's own run_anchor_validation() fix. 2026-07-27 is summer
        # (EDT), so this is byte-identical to the prior default either way; kept
        # frame-consistent with production so this test never models the pre-fix mismatch.
        res = walk_exit_manager(
            symbol=anchor["symbol"], side=anchor["side"], entry_time_et=entry_time_et,
            entry_premium=anchor["entry_premium"], qty=qty, exit_shape=shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=bfr.TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=None,
            five_min_spy_df=day_spy, frame=FRAME_ET_V2,
        )
        return res.dollar_pnl

    real_pnl = anchor["real_pnl"]
    tol = max(bfr.ANCHOR_TOLERANCE_DOLLARS, abs(real_pnl) * bfr.ANCHOR_TOLERANCE_PCT)

    correct_pnl = replay_at(5)
    assert abs(correct_pnl - real_pnl) <= tol, (
        f"correct qty=5 replay (${correct_pnl:.2f}) should pass tolerance vs real "
        f"${real_pnl:.2f} (tol=${tol:.2f}) -- if this fails, the baseline anchor itself broke")

    wrong_pnl = replay_at(3)  # Safe's min_contracts -- the mistranslation this test guards against
    assert abs(wrong_pnl - real_pnl) > tol, (
        f"MISTRANSLATED qty=3 replay (${wrong_pnl:.2f}) should FAIL tolerance vs real "
        f"${real_pnl:.2f} (tol=${tol:.2f}) -- if this assertion fails, the anchor test is "
        f"insensitive to the sizing knob and would silently accept a wrong translation")


# ---------------------------------------------------------------------------------------- #
# 2. STRIKE SIGN-CONVENTION RED-PROOF
# ---------------------------------------------------------------------------------------- #
def test_live_to_sim_strike_offset_negates():
    assert bfr._live_to_sim_strike_offset(0) == 0
    assert bfr._live_to_sim_strike_offset(-2) == 2    # live OTM-2 -> sim +2
    assert bfr._live_to_sim_strike_offset(2) == -2     # live ITM-2 -> sim -2


def test_resolve_bold_strike_offset_matches_v15_bold_core_tiers_negated():
    import strike_selection as ss
    offset, label = bfr.resolve_bold_strike_offset(equity=1_197.52)
    assert label == "ATM"
    assert offset == 0   # ATM is sign-invariant -- the trap doesn't bite at THIS equity
    # at a higher tier the negation is load-bearing: live OTM-2 (-2) must arrive at the
    # simulator as +2, NOT -2 (a non-negated / mistranslated offset).
    offset_2to10k, label_2to10k = bfr.resolve_bold_strike_offset(equity=5_000.0)
    assert label_2to10k == "OTM-2"
    live_tier = ss.pick_tier(5_000.0, ss.V15_BOLD_CORE_TIERS)
    assert live_tier.strike_offset == -2                 # live convention: OTM-2 = -2
    assert offset_2to10k == 2                             # sim convention (negated): +2
    assert offset_2to10k != live_tier.strike_offset, (
        "a mistranslated (non-negated) strike offset would silently pass the live table's "
        "-2 straight into run_backtest's inverted-sign kwarg, flipping OTM-2 into ITM-2")


# ---------------------------------------------------------------------------------------- #
# 3. EXIT-SHAPE-PARITY (same invariant Safe's own guard pins, re-pinned here for Bold)
# ---------------------------------------------------------------------------------------- #
def test_bold_tool_uses_the_real_shared_ribbon_ride_exit_shape():
    shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    assert shape["profit_lock_mode"] == "trailing"
    assert shape["stop_mode"] == "structure"
    assert shape["profit_lock_mode"] != "fixed"
    # aggressive/params.json's OWN top-level exit keys must NOT be what the tool grades
    # trades against -- they are vestigial (finding #3). Prove they actually differ from
    # the real shape, so "the tool happens to use the vestigial numbers anyway" can't hide.
    agg = json.loads(AGGRESSIVE_PARAMS.read_text(encoding="utf-8"))
    assert agg["tp1_premium_pct"] != shape["tp1_premium_pct"], (
        "aggressive/params.json's top-level tp1_premium_pct coincides with the real "
        "ribbon_ride shape -- the vestigial-exit-keys finding may be stale, re-verify")


def test_run_backtest_receives_shared_shape_regardless_of_gate_state():
    """block_elite_bull must be the ONLY thing that differs between the two gate-state
    configs -- exit-shape kwargs (tp1/runner/profit_lock, all disclosure-only per the
    module docstring) must be identical."""
    pre = bfr.bold_base_live(block_elite_bull=True)
    post = bfr.bold_base_live(block_elite_bull=False)
    diff_keys = {k for k in pre if pre[k] != post.get(k)}
    assert diff_keys == {"block_elite_bull"}, (
        f"bold_base_live(True) vs bold_base_live(False) differ in more than the gate "
        f"itself: {diff_keys}")
    assert pre["block_elite_bull"] is True
    assert post["block_elite_bull"] is False


# ---------------------------------------------------------------------------------------- #
# 4. GATE_KEYS TRANSLATION PINS (against the on-disk source of truth)
# ---------------------------------------------------------------------------------------- #
def test_translation_table_pins_against_live_aggressive_params_json():
    """Every non-exit-shape gate value bold_base_live() hardcodes must match
    automation/state/aggressive/params.json's CURRENT on-disk value. A future params edit
    that drifts from this tool's translation silently produces a stale replay -- this test
    is the tripwire."""
    agg = json.loads(AGGRESSIVE_PARAMS.read_text(encoding="utf-8"))
    base = bfr.bold_base_live(block_elite_bull=True)

    assert agg["filter_10_min_triggers_bear"] == 1
    assert agg["filter_10_min_triggers_bull"] == 1
    assert base["min_triggers_bear"] == 1 and base["min_triggers_bull"] == 1

    assert agg["block_level_rejection"] is False
    assert base["block_level_rejection"] is False

    assert agg["block_elite_bull_vix_low"] == 15.0
    assert agg["block_elite_bull_vix_high"] == 18.0
    assert base["block_elite_bull_vix_low"] == 15.0
    assert base["block_elite_bull_vix_high"] == 18.0

    assert "entry_bar_body_pct_min" not in agg   # absent -> engine default 0.0
    assert base["entry_bar_body_pct_min"] == 0.0

    assert "block_bull_1100_1200" not in agg     # absent -> engine default False for Bold
    assert base["block_bull_1100_1200"] is False

    assert "vix_bear_hard_cap" not in agg        # absent -> gate off entirely for Bold
    assert base["vix_bear_hard_cap"] is None

    assert agg["require_bearish_fill_bar"] is True
    assert base["require_bearish_fill_bar"] is True

    assert agg["per_trade_risk_cap_pct"] == 0.50
    assert base["per_trade_risk_cap_pct"] == 0.50

    assert "structure_veto_enabled" not in agg   # disclosed gap: no run_backtest kwarg exists


def test_translation_table_differs_from_safe_where_documented():
    """Cross-check against Safe's own SAFE_BASE_LIVE (engine_fullhist_replay.py) so the
    DIFFERENCES this tool's docstring claims are real, not accidental coincidences."""
    import engine_fullhist_replay as efr
    bold = bfr.bold_base_live(block_elite_bull=True)
    safe = efr.SAFE_BASE_LIVE

    assert bold["min_triggers_bull"] == 1 and safe["min_triggers_bull"] == 2
    assert bold["block_level_rejection"] is False and safe["block_level_rejection"] is True
    assert bold["block_elite_bull_vix_low"] == 15.0 and safe["block_elite_bull_vix_low"] == 0.0
    assert bold["block_elite_bull_vix_high"] == 18.0 and safe["block_elite_bull_vix_high"] == 25.0
    assert bold["entry_bar_body_pct_min"] == 0.0 and safe["entry_bar_body_pct_min"] == 0.2
    assert bold["block_bull_1100_1200"] is False and safe["block_bull_1100_1200"] is True
    assert bold["vix_bear_hard_cap"] is None and safe["vix_bear_hard_cap"] == 23.0
    assert bold["require_bearish_fill_bar"] is True
    assert safe.get("require_bearish_fill_bar", False) is False
    assert bold["per_trade_risk_cap_pct"] == 0.50 and safe["per_trade_risk_cap_pct"] == 0.30


# ---------------------------------------------------------------------------------------- #
# 5. GATE STATE AS INPUT
# ---------------------------------------------------------------------------------------- #
def test_block_elite_bull_is_a_parameter_not_a_constant():
    import inspect
    sig = inspect.signature(bfr.bold_base_live)
    assert "block_elite_bull" in sig.parameters
    assert sig.parameters["block_elite_bull"].default is inspect.Parameter.empty, (
        "block_elite_bull must be REQUIRED (no silent default) so a caller can never "
        "accidentally model the wrong gate state")


# ---------------------------------------------------------------------------------------- #
# 6. ANCHOR REPRODUCTION (task step 3: N>=5 real fills)
# ---------------------------------------------------------------------------------------- #
def test_anchor_set_has_at_least_5_engine_attributed_real_fills():
    assert len(bfr.ANCHOR_FILLS) >= 5
    # every anchor must be qty=5 -- if a future edit adds a manual-attribution or
    # wrongly-sized fill, this catches it immediately (the whole anchor set's evidentiary
    # value rests on being ENGINE fills, not J's manual trades).
    assert all(a["qty"] == 5 for a in bfr.ANCHOR_FILLS)


@pytest.mark.slow
@pytest.mark.skipif(not DATA_AVAILABLE, reason="requires merged SPY/VIX data")
def test_anchor_validation_passes_majority_within_tolerance():
    result = bfr.run_anchor_validation()
    assert result["n_anchors"] >= 5
    ok_rows = [r for r in result["rows"] if r.get("replay_status") == "OK"]
    assert len(ok_rows) >= 5, "at least 5 anchors must be OPRA-evaluable, not cache-missing"
    assert result["n_pass"] >= 5, (
        f"expected >=5/{result['n_anchors']} anchors to pass, got {result['n_pass']} -- "
        f"rows: {json.dumps(result['rows'], indent=2, default=str)}")
    # every evaluated anchor must at least agree on WIN/LOSS direction -- a sign mismatch
    # would mean the harness is modeling the wrong side or a broken exit shape entirely.
    for r in ok_rows:
        assert r["same_sign"], f"anchor {r['symbol']} replayed the WRONG direction: {r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
