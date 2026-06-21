"""Tests for autoresearch.verify_edgehunt_candidates — the GATE_FRAUD wiring guard.

This is the graduate-to-code half of the option-edge-vs-spy-tilt lesson (L171 + L172):
the two fraud gates (no-truncation `truncation_guard.py`/L171 and random-entry-null
`null_baseline.py`/L172) are wired into the real-fills verify harness via
`autoresearch.fraud_gates`, so EVERY edge-hunt candidate is auto-checked. The campaign
proved the naive 5-gate bar (OOS>0, posQ>=4/6, top5<200, n>=20, robust/anchor) lets
SPY-direction tilts through that profit ONLY by stop-truncation or that a coin-flip
reproduces. These tests pin that the harness's `_gate` REJECTS exactly those impostors —
a candidate that clears every naive gate must STILL be rejected if it is a truncation
artifact or fails the random-null, and confirmed only when both fraud gates clear.

No OPRA / simulation needed: the harness consumes already-computed per-trade numbers
(`fraud_gate_from_per_trade` is the pure core), so these fixtures are plain dicts.
"""
from __future__ import annotations

from autoresearch import verify_edgehunt_candidates as veh


def _base_candidate() -> dict:
    """A candidate dict that clears every NAIVE gate (OOS>0, posQ 6/6, top5<200,
    n/oos_n>=20, robust, anchor, true_edge) AND both fraud gates — the clean baseline.

    null: strategy per_trade (overall 90) beats the null MAX (40); drop_top5 (70) beats
    the null MEAN (10) -> null_pass. chart-stop-only stays positive (60) at the tight 8%
    stop -> no truncation. This is the vwap_continuation shape (the only real survivor)."""
    return {
        "config": "clean_cell",
        "oos_per_trade": 105.0,
        "overall_per_trade": 90.0,
        "n_trades": 60,
        "oos_n": 30,
        "top5_day_pct": 21.0,
        "oos_top5_day_pct": 50.0,
        "positive_quarters": "6/6",
        "clears_bar_robust": True,
        "anchor_no_regression": True,
        "true_edge": True,
        "premium_stop_pct": 8.0,
        "same_strike_chart_stop_only_per_trade": 60.0,
        "null": {"per_trade_mean": 10.0, "per_trade_max": 40.0},
        "drop_top5_per_trade": 70.0,
    }


def _gate_of(raw: dict):
    """Run the harness's real extract->gate path; return (fails, caveats)."""
    ex = veh._extract("test_family", raw)
    return veh._gate("test_family", ex)


# ── the clean baseline must pass everything ──────────────────────────────────

def test_clean_candidate_confirmed():
    fails, _caveats = _gate_of(_base_candidate())
    assert fails == [], f"clean vwap-shaped cell should clear all gates, got: {fails}"


# ── GATE_FRAUD #1: no-truncation (L171) ──────────────────────────────────────

def test_truncation_artifact_rejected():
    """Passes every naive gate, but per-trade INVERTS to negative at chart-stop-only with
    a tight 8% stop -> the positive headline is stop-truncation, not edge (the ema_adx
    case). Must be rejected with the L171 reason."""
    c = _base_candidate()
    c["same_strike_chart_stop_only_per_trade"] = -41.6  # sign inverts at the tight stop
    fails, _ = _gate_of(c)
    assert any("TRUNCATION_ARTIFACT" in f for f in fails), fails


def test_inline_truncation_pin_overrides_recompute():
    """A family that recorded a full-per-trade truncation verdict PINS it: even with a
    positive chart-stop-only number, an inline is_truncation_artifact=True rejects."""
    c = _base_candidate()
    c["is_truncation_artifact"] = True  # family's authoritative inline verdict
    fails, _ = _gate_of(c)
    assert any("TRUNCATION_ARTIFACT" in f for f in fails), fails


# ── GATE_FRAUD #2: random-entry null (L172) ──────────────────────────────────

def test_null_failing_candidate_rejected():
    """The RSI(2) case: a coin-flip MAX (+8.10) reproduces the strategy's per-trade
    (+6.11). chart-stop-only positive (no truncation) so ONLY the null gate catches it."""
    c = _base_candidate()
    c["overall_per_trade"] = 6.11
    c["null"] = {"per_trade_mean": 2.66, "per_trade_max": 8.10}
    c["drop_top5_per_trade"] = 2.87
    fails, _ = _gate_of(c)
    assert any("RANDOM_NULL_FAIL" in f for f in fails), fails
    assert not any("TRUNCATION_ARTIFACT" in f for f in fails), \
        "null-fail case should NOT also trip truncation (chart-stop-only is positive)"


def test_null_unverified_is_caveat_not_reject():
    """Fail-open: a candidate with no null block and no inline null_pass cannot be
    DISPROVEN by the null -> it is a CAVEAT, never a hard fail (cannot-disprove != bless)."""
    c = _base_candidate()
    c.pop("null")
    fails, caveats = _gate_of(c)
    assert not any("RANDOM_NULL_FAIL" in f for f in fails), fails
    assert any("null-unverified" in cv for cv in caveats), caveats
    assert fails == [], f"clean-but-null-unverified cell should still confirm: {fails}"


def test_inline_null_pin_overrides():
    """An inline null_pass=False (family ran null_baseline with full data) rejects even
    without a null dict in the candidate."""
    c = _base_candidate()
    c.pop("null")
    c["null_pass"] = False
    fails, _ = _gate_of(c)
    assert any("RANDOM_NULL_FAIL" in f for f in fails), fails


# ── structural wiring guard: the gates must STAY wired ────────────────────────

def test_fraud_gates_wiring_present():
    """Regression guard against silent un-wiring: the verify harness must consume
    fraud_gates, and fraud_gates must delegate to BOTH graduated libraries (L171/L172).
    If a refactor drops either import, the harness would silently stop fraud-checking."""
    import inspect

    from autoresearch import fraud_gates

    veh_src = inspect.getsource(veh)
    assert "fraud_gate_from_per_trade" in veh_src, \
        "verify harness no longer calls the fraud gate"

    fg_src = inspect.getsource(fraud_gates)
    assert "truncation_guard" in fg_src, "fraud_gates dropped the L171 no-truncation gate"
    assert "null_baseline" in fg_src, "fraud_gates dropped the L172 random-null gate"


def test_both_fraud_gates_must_pass_combined():
    """The lesson thesis 'must pass BOTH': a cell failing EITHER fraud gate is rejected.
    Truncation-artifact AND null-fail simultaneously -> rejected (both reasons present)."""
    c = _base_candidate()
    c["overall_per_trade"] = 6.11
    c["same_strike_chart_stop_only_per_trade"] = -20.0
    c["null"] = {"per_trade_mean": 2.66, "per_trade_max": 8.10}
    c["drop_top5_per_trade"] = 2.87
    fails, _ = _gate_of(c)
    assert any("TRUNCATION_ARTIFACT" in f for f in fails), fails
    assert any("RANDOM_NULL_FAIL" in f for f in fails), fails
