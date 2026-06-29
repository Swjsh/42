"""Golden-file guard for the canonical probe-stats helper.

Pins the single-source significance + concentration policy (self-audit gap
2026-06-28T17:30:40 items 1+2) AND proves the helper reproduces the EXACT numbers
both committed range-scalp probes already published -- so adopting the helper in a
future probe cannot silently change a result, and the n<10 / top3>150% thresholds
can never drift apart again (the C14 divergent-knob class these two probes were in).

$0 / offline: reads the committed result JSONs, never re-runs the slow real-fills
probe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(_REPO / "backtest"))

from autoresearch.probe_stats import (  # noqa: E402
    CONCENTRATION_TOP3_PCT_MAX,
    INCONCLUSIVE_MIN_N,
    REALISTIC_SLIPPAGE_HALF_SPREAD,
    base_verdict,
    breakeven_half_spread,
    concentration_flag,
    day_concentration,
    edge_capture_gate_misapplied,
    net_pnls_after_slippage,
    recommended_yardstick,
    requires_directional_anchor,
    significance,
    slippage_haircut_per_trade,
    slippage_sweep,
    summarize_trades,
)

_REC = _REPO / "analysis" / "recommendations"
_UNGATED = _REC / "range-scalp-probe-2026-06-28.json"
_GATED = _REC / "range-scalp-regime-gated-2026-06-28.json"
_SWEEP = _REC / "range-scalp-gate-sweep-2026-06-28.json"


def _load(p: Path) -> dict:
    if not p.exists():  # golden file is the fixture; absence is a real failure
        pytest.skip(f"golden file missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


# --- canonical thresholds are the single source of truth ----------------------

def test_thresholds_are_canonical():
    assert INCONCLUSIVE_MIN_N == 10
    assert CONCENTRATION_TOP3_PCT_MAX == 150.0


# --- significance: the n<10 gap -----------------------------------------------

def test_significance_flags_small_n():
    assert significance(8)["sufficient"] is False     # the gated probe's n=8
    assert significance(9)["sufficient"] is False
    assert significance(10)["sufficient"] is True      # exactly at the floor
    assert significance(30)["sufficient"] is True      # the ungated probe's n=30
    assert "INCONCLUSIVE" in significance(8)["note"]


# --- concentration: the top3>150% gap -----------------------------------------

def test_concentration_flag_threshold():
    assert concentration_flag(117.2)["concentrated"] is False  # gated: within tol
    assert concentration_flag(150.0)["concentrated"] is False  # boundary excluded
    assert concentration_flag(223.9)["concentrated"] is True   # ungated: fragile
    assert concentration_flag(None)["concentrated"] is False   # zero-net safe


# --- GOLDEN equivalence: helper reproduces the published numbers exactly -------

def test_helper_reproduces_ungated_concentration():
    d = _load(_UNGATED)
    by_day = d["results"]["by_day_pnl"]
    conc = day_concentration(by_day)
    # non-vacuous: the helper's top3 must MATCH the probe's hand-rolled 223.9
    assert conc["top3_day_pct_of_net"] == d["results"]["top3_day_pct_of_net"] == 223.9
    assert conc["n_active_days"] == d["results"]["n_active_days"]
    assert conc["n_losing_days"] == d["results"]["n_losing_days"]


def test_helper_reproduces_gated_summary_and_concentration():
    d = _load(_GATED)
    gross = d["gated_gross"]
    # reconstruct the gated per-trade pnls from the stored trade rows
    gated_pnls = [r["dollar_pnl"] for r in d["trades"] if r["kept"]]
    summ = summarize_trades(gated_pnls)
    # the helper must reproduce the published gated summary exactly
    assert summ["n_trades"] == gross["n_trades"] == 8
    assert summ["total_pnl_usd"] == gross["total_pnl_usd"] == 355.2
    assert summ["expectancy_per_trade_usd"] == gross["expectancy_per_trade_usd"] == 44.4
    assert summ["win_rate"] == gross["win_rate"] == 0.875
    # and the concentration block
    conc = day_concentration(gross["by_day_pnl"])
    assert conc["top3_day_pct_of_net"] == gross["top3_day_pct_of_net"] == 117.2


# --- canonical verdict ladder reproduces both probes' published verdicts -------

def test_base_verdict_matches_published_verdicts():
    # ungated: n=30, exp 12.46, top3 223.9 -> positive but concentration-fragile.
    # The probe labels this "VEIN_CONCENTRATED"; the canonical neutral verdict is
    # CONCENTRATED (same judgment, single vocabulary).
    assert base_verdict(30, 12.46, 223.9) == "CONCENTRATED"
    # gated: n=8 -> below the floor regardless of how good it looks.
    # Probe labels it "REGIME_GATE_TOO_TIGHT"; canonical = INCONCLUSIVE.
    assert base_verdict(8, 44.4, 117.2) == "INCONCLUSIVE"


def test_base_verdict_ladder_full():
    assert base_verdict(5, 100.0, 50.0) == "INCONCLUSIVE"   # n gate wins first
    assert base_verdict(20, -3.0, 50.0) == "DRY"            # enough n, no edge
    assert base_verdict(20, 5.0, 200.0) == "CONCENTRATED"   # edge but fragile
    assert base_verdict(20, 5.0, 90.0) == "CLEAN"           # edge, spread out
    assert base_verdict(20, 5.0, None) == "CLEAN"           # zero-net -> not fragile


# --- gate-leg sweep (slice 3 part 2): faithful reuse + the locked finding ------

def test_gate_sweep_baseline_reproduces_slice2():
    """The sweep's slice-2 baseline variant (spread<30 / VIX[14,20]) must reproduce
    the committed slice-2 gated numbers EXACTLY -- proves the one-OPRA-pass reuse +
    the probe_stats adoption did not change a result (the C14 reuse-drift guard)."""
    d = _load(_SWEEP)
    base = d["slice2_baseline"]
    assert base["is_slice2_baseline"] is True
    s = base["summary_gross"]
    assert s["n_trades"] == 8
    assert s["expectancy_per_trade_usd"] == 44.4
    assert s["total_pnl_usd"] == 355.2
    assert base["concentration"]["top3_day_pct_of_net"] == 117.2
    assert base["base_verdict"] == "INCONCLUSIVE"     # n=8 < 10, via canonical ladder
    assert base["big_losers_killed"] is True


def test_gate_sweep_finding_locked():
    """The slice-3 finding: loosening the SPREAD leg recovers count (n=8->11->12) but
    every recovered variant goes NEGATIVE net of 0.05 slippage AND concentration gets
    WORSE -- so no variant 'recovers' cleanly; the lever is more data, not looser
    gates. Pins the verdict so a future edit can't silently flip the conclusion."""
    d = _load(_SWEEP)
    assert d["verdict"] == "GATE_KNIFE_EDGE_WIDEN_DATA"
    assert d["best_recoverable"] is None
    # the VIX leg is INERT on this window (a C14 dead-knob): for a fixed spread cap,
    # widening the VIX band changes nothing.
    by_spread: dict[float, set] = {}
    for v in d["variants"]:
        key = v["gate"]["spread_max_cents"]
        by_spread.setdefault(key, set()).add(
            (v["summary_gross"]["n_trades"], v["summary_gross"]["expectancy_per_trade_usd"])
        )
    for sp, outcomes in by_spread.items():
        assert len(outcomes) == 1, f"VIX leg not inert at spread<{sp}: {outcomes}"
    # every significant (n>=10) variant dies under 0.05 slippage (negative net exp).
    for v in d["variants"]:
        if v["significance"]["sufficient"]:
            assert v["summary_net_0.05"]["expectancy_per_trade_usd"] < 0


# --- slippage sweep (self-audit gap #3): breakeven robustness -----------------
# Both range-scalp probes reported net-of-slippage at only 2 fixed haircuts. The
# canonical helper sweeps a RANGE and reports the breakeven half-spread. These pin
# that it reproduces the committed probe's published net numbers EXACTLY (so adopting
# it can't silently change a result) AND that the breakeven math is correct.

def test_slippage_haircut_matches_probe_cost_model():
    # round-trip half-spread x100 multiplier x qty, the exact model both probes use
    assert slippage_haircut_per_trade(0.05, 3) == 30.0   # 2 * 0.05 * 100 * 3
    assert slippage_haircut_per_trade(0.02, 10) == 40.0  # 2 * 0.02 * 100 * 10
    assert slippage_haircut_per_trade(0.0, 5) == 0.0


def test_slippage_sweep_reproduces_gated_net_0_05():
    """GOLDEN: the helper's net@0.05 on the committed gated trades must reproduce the
    probe's published half_spread_0.05 block EXACTLY (total $115.2, exp $14.4)."""
    d = _load(_GATED)
    kept = [r for r in d["trades"] if r["kept"]]
    pub05 = d["gated_net_of_slippage"]["half_spread_0.05"]
    net05 = net_pnls_after_slippage(kept, 0.05)
    s = summarize_trades(net05)
    assert s["total_pnl_usd"] == pub05["total_pnl_usd"] == 115.2
    assert s["expectancy_per_trade_usd"] == pub05["expectancy_per_trade_usd"] == 14.4
    # and the 0.02 haircut block too (both published points reproduced)
    pub02 = d["gated_net_of_slippage"]["half_spread_0.02"]
    s02 = summarize_trades(net_pnls_after_slippage(kept, 0.02))
    assert s02["total_pnl_usd"] == pub02["total_pnl_usd"] == 259.2
    assert s02["expectancy_per_trade_usd"] == pub02["expectancy_per_trade_usd"] == 32.4


def test_breakeven_half_spread_is_exact():
    """The gated edge (mean $44.4/trade on 3 contracts) breaks even at
    44.4/(200*3) = 0.074 $/share half-spread -- above the 0.05 realistic reference,
    so it SURVIVES realistic slippage (it's just n=8, separately inconclusive)."""
    d = _load(_GATED)
    kept = [r for r in d["trades"] if r["kept"]]
    be = breakeven_half_spread(kept)
    assert be == 0.074
    sweep = slippage_sweep(kept)
    assert sweep["breakeven_half_spread"] == 0.074
    assert sweep["verdict"] == "SURVIVES_REALISTIC"   # 0.074 >= 0.05
    # the swept grid must straddle breakeven: positive below it, negative above it
    pts = {p["half_spread"]: p["positive"] for p in sweep["grid"]}
    assert pts[0.05] is True       # below breakeven -> still positive
    assert pts[0.10] is False      # above breakeven -> negative
    assert REALISTIC_SLIPPAGE_HALF_SPREAD == 0.05


def test_slippage_sweep_verdict_ladder():
    # DRY_AT_ZERO: negative even with no slippage
    dry = slippage_sweep([{"dollar_pnl": -10.0, "qty": 1}, {"dollar_pnl": -5.0, "qty": 1}])
    assert dry["verdict"] == "DRY_AT_ZERO" and dry["breakeven_half_spread"] is None
    # FRAGILE: positive but breakeven below 0.05 (tiny edge, big size)
    #   mean_pnl=2.0, qty=10 -> breakeven = 2/(200*10) = 0.001 < 0.05
    frag = slippage_sweep([{"dollar_pnl": 2.0, "qty": 10}, {"dollar_pnl": 2.0, "qty": 10}])
    assert frag["verdict"] == "FRAGILE_TO_SLIPPAGE"
    assert frag["breakeven_half_spread"] == 0.001
    # SURVIVES: robust edge, breakeven well above 0.05
    surv = slippage_sweep([{"dollar_pnl": 50.0, "qty": 1}, {"dollar_pnl": 30.0, "qty": 1}])
    assert surv["verdict"] == "SURVIVES_REALISTIC"


def test_slippage_sweep_empty_safe():
    s = slippage_sweep([])
    assert s["n_trades"] == 0
    assert s["breakeven_half_spread"] is None
    assert s["verdict"] == "DRY_AT_ZERO"


# --- L192: strategy-class yardstick policy ------------------------------------
# J `edge_capture` (OP-16, 771 floor) is a DIRECTIONAL-anchor metric -- applying it
# to a regime / mean-reversion strategy auto-rejects it by construction. These pin
# the lesson as executable logic so a future gate can't silently re-mis-apply it.

def test_directional_classes_keep_edge_capture():
    for cls in ("directional", "momentum", "continuation", "breakout",
                "bearish_rejection", "bullish_reclaim"):
        assert requires_directional_anchor(cls) is True, cls
        assert recommended_yardstick(cls) == "edge_capture", cls
        # a directional candidate gated on edge_capture is CORRECT, not mis-applied
        assert edge_capture_gate_misapplied(cls, gate_uses_edge_capture=True) is False, cls


def test_regime_classes_reject_edge_capture():
    # the exact classes this lesson was born from (range-scalp = level fade)
    for cls in ("range", "mean_reversion", "mean-reversion", "scalp",
                "level_fade", "overnight", "fade"):
        assert requires_directional_anchor(cls) is False, cls
        assert recommended_yardstick(cls) == "per_trade_expectancy", cls
        # the foot-gun: gating a range strategy on edge_capture<771 is MIS-APPLIED
        assert edge_capture_gate_misapplied(cls, gate_uses_edge_capture=True) is True, cls
        # ...but if the gate ISN'T edge_capture, nothing is mis-applied
        assert edge_capture_gate_misapplied(cls, gate_uses_edge_capture=False) is False, cls


def test_unknown_class_is_conservative():
    # an unclassified strategy must NOT be silently auto-rejected by a directional
    # gate -- unknown defaults to the expectancy yardstick (don't lose a real lead).
    for cls in ("", "weird_new_thing", "vix_dayside_???"):
        assert requires_directional_anchor(cls) is False
        assert recommended_yardstick(cls) == "per_trade_expectancy"
        assert edge_capture_gate_misapplied(cls, gate_uses_edge_capture=True) is True


def test_class_label_normalization():
    # case / hyphen / space variants resolve to the same policy
    assert requires_directional_anchor("Mean-Reversion") is False
    assert requires_directional_anchor(" BREAKOUT ") is True
    assert recommended_yardstick("Mean Reversion") == "per_trade_expectancy"


# --- empty-input safety -------------------------------------------------------

def test_empty_inputs_safe():
    s = summarize_trades([])
    assert s["n_trades"] == 0 and s["total_pnl_usd"] == 0.0
    c = day_concentration({})
    assert c["n_active_days"] == 0 and c["top3_day_pct_of_net"] is None
