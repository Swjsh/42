"""Integration tests for the GRADUATED fraud-detector gates (C3/L58, L171/L172).

The lesson strategy/candidates/_lesson-inbox/2026-06-20-option-edge-vs-spy-tilt-
discriminator.md demands the two discriminators that caught RSI2 / IBS / ema_adx AFTER
they passed the naive 5-gate verify -- random-entry-null and no-truncation -- graduate
into the real-fills verify harness so EVERY candidate is auto-checked.

This pins the WIRING (autoresearch.fraud_gates + verify_edgehunt_candidates), not just
the shared primitives (those are covered by test_null_baseline.py + test_truncation_guard.py):

  * a known-FAKE (IBS-style truncation flip: +$ at the tight stop, -$ at chart-stop-only)
    is REJECTED, and
  * a known-REAL (vwap_continuation: sign holds at chart-stop-only AND it beats the null
    MAX) PASSES.

Both paths are exercised: the harness's static-JSON read (_extract -> _gate -> _fraud_verdict)
AND the per-trade re-simulation entry point (fraud_gates.verify_candidate) with
simulate_trade_real stubbed (no OPRA data needed, $0).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKTEST = Path(__file__).resolve().parents[1]   # backtest/
ROOT = BACKTEST.parent                            # repo root (42/)
for _p in (str(BACKTEST), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import fraud_gates  # noqa: E402
from autoresearch.fraud_gates import (  # noqa: E402
    CandidateSignal,
    FraudVerdict,
    fraud_gate_from_per_trade,
    verify_candidate,
)
from autoresearch.verify_edgehunt_candidates import _extract, _gate  # noqa: E402

IBS_JSON = ROOT / "analysis" / "recommendations" / "newhunt-ibs-mean-reversion.json"
VWAP_JSON = ROOT / "analysis" / "recommendations" / "edgehunt-vwap_continuation.json"


# ─────────────────────────────────────────────────────────────────────────────
# 1. The pure fraud-gate core: known-fake REJECTED, known-real PASSES
# ─────────────────────────────────────────────────────────────────────────────

def test_fraud_gate_rejects_ibs_truncation_flip():
    """IBS best cell: +$5.3/tr at stop=-8% but -$19.6/tr at chart-stop-only (sign
    inverts) -> truncation artifact -> REJECTED, regardless of the null."""
    null = {"per_trade_mean": 2.0, "per_trade_max": 4.0}  # IBS-like; doesn't matter, trunc fails first
    v = fraud_gate_from_per_trade(
        chosen_per_trade=5.3,
        chart_stop_only_per_trade=-19.6,
        chosen_premium_stop_pct=-0.08,
        drop_top5_per_trade=3.68,
        null=null,
    )
    assert isinstance(v, FraudVerdict)
    assert v.is_truncation_artifact is True
    assert v.no_truncation_pass is False
    assert v.passes is False
    assert "TRUNCATION ARTIFACT" in v.reason


def test_fraud_gate_rejects_rsi2_random_null_match():
    """RSI(2): sign HOLDS at chart-stop-only (no truncation) but +$6.11/tr does NOT beat
    the random-null MAX +$8.10 -> a coin-flip reproduces it -> REJECTED on the null gate."""
    null = {"per_trade_mean": 2.66, "per_trade_max": 8.10}
    v = fraud_gate_from_per_trade(
        chosen_per_trade=6.11,
        chart_stop_only_per_trade=3.0,    # positive -> NOT a truncation artifact
        chosen_premium_stop_pct=-0.08,
        drop_top5_per_trade=2.87,
        null=null,
    )
    assert v.no_truncation_pass is True       # sign holds
    assert v.null_pass is False                # +6.11 < +8.10 null max
    assert v.passes is False                    # killed by the null gate


def test_fraud_gate_passes_a_genuine_edge():
    """Known-real shape: sign holds at chart-stop-only AND beats the null MAX with a
    concentration-robust drop-top5 above the null mean -> PASSES both gates."""
    null = {"per_trade_mean": 5.0, "per_trade_max": 20.0}
    v = fraud_gate_from_per_trade(
        chosen_per_trade=105.62,           # vwap ITM2/-8% OOS per-trade
        chart_stop_only_per_trade=79.79,   # vwap ITM2/chart-stop-only -> sign HOLDS
        chosen_premium_stop_pct=-0.08,
        drop_top5_per_trade=60.0,          # well above null mean
        null=null,
    )
    assert v.no_truncation_pass is True
    assert v.null_pass is True
    assert v.passes is True


def test_fraud_gate_fails_open_when_chart_stop_only_missing():
    """No chart-stop-only reference -> truncation cannot be disproved -> NOT flagged
    (the outer candidate gate still governs; never silently blesses)."""
    null = {"per_trade_mean": 5.0, "per_trade_max": 20.0}
    v = fraud_gate_from_per_trade(
        chosen_per_trade=105.62,
        chart_stop_only_per_trade=None,
        chosen_premium_stop_pct=-0.08,
        drop_top5_per_trade=60.0,
        null=null,
    )
    assert v.no_truncation_pass is True   # fails open
    assert v.null_pass is True
    assert v.passes is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. The harness wiring: a candidate JSON is auto-checked by the fraud gates
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not IBS_JSON.exists(), reason="IBS recommendation JSON not present")
def test_harness_rejects_known_fake_ibs():
    """End-to-end through verify_edgehunt_candidates: the IBS truncation-flip best cell
    is REJECTED with the TRUNCATION_ARTIFACT fail, and the same-strike chart-stop-only
    per-trade is resolved straight from the family grid (-19.6)."""
    ibs = json.loads(IBS_JSON.read_text(encoding="utf-8"))
    best = next(c for c in ibs["grid"]
                if c["strike_offset"] == -1 and c["premium_stop_pct"] == -0.08)
    cand = dict(best)
    cand["self_verify"] = ibs["self_verify"]
    cand["premium_stop_pct"] = -0.08

    ex = _extract("ibs", cand, fam_dict=ibs)
    fails, _caveats = _gate("ibs", ex)

    assert ex["fraud_inputs"]["chart_stop_only_per_trade"] == -19.6
    assert ex["fraud"]["no_truncation_pass"] is False
    assert ex["fraud"]["passes"] is False
    assert any("TRUNCATION_ARTIFACT" in f for f in fails)


@pytest.mark.skipif(not VWAP_JSON.exists(), reason="vwap recommendation JSON not present")
def test_harness_passes_known_real_vwap_fraud_gates():
    """End-to-end: the vwap_continuation ITM2/-8% candidate clears the NO-TRUNCATION gate
    (its chart-stop-only sibling is resolved from base_grid and is positive, so the sign
    holds). The candidate must NOT carry a TRUNCATION_ARTIFACT fail."""
    vwap = json.loads(VWAP_JSON.read_text(encoding="utf-8"))
    cand = next(c for c in vwap["candidate_cells"]
                if c["strike_offset"] == -2 and c["premium_stop_pct"] == -0.08)

    ex = _extract("vwap_continuation", cand, fam_dict=vwap)
    fails, _caveats = _gate("vwap_continuation", ex)

    # chart-stop-only sibling found in base_grid and POSITIVE -> sign holds -> no artifact
    assert ex["fraud_inputs"]["chart_stop_only_per_trade"] is not None
    assert ex["fraud_inputs"]["chart_stop_only_per_trade"] > 0
    assert ex["fraud"]["no_truncation_pass"] is True
    assert not any("TRUNCATION_ARTIFACT" in f for f in fails)
    # and the candidate clears ALL gates (it is the documented sole survivor)
    assert fails == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. The per-trade RE-SIMULATION entry point (simulate_trade_real stubbed)
# ─────────────────────────────────────────────────────────────────────────────

class _StubFill:
    def __init__(self, pnl: float):
        self.dollar_pnl = pnl


def _synthetic_rth(days: int = 10, bars_per_day: int = 78) -> pd.DataFrame:
    """``days`` consecutive 5-min RTH sessions with close/low/high + timestamp_et.

    Multi-day so the drop-top-5-DAYS concentration check in the null gate is meaningful
    (a single-day fixture would drop every trade -> drop_top5=None, which is itself a
    correct rejection but not what these PASS/FAIL fixtures intend to exercise)."""
    rows = []
    for d in range(days):
        base = dt.datetime(2025, 6, 2, 9, 30) + dt.timedelta(days=d)
        for i in range(bars_per_day):
            close = 500.0 + 0.1 * i
            ts = base + dt.timedelta(minutes=5 * i)
            rows.append({"timestamp_et": ts, "close": close,
                         "low": close - 0.5, "high": close + 0.5})
    return pd.DataFrame(rows).reset_index(drop=True)


def _fake_sim_truncation(**kw):
    """A FAKE signal: positive at the tight -8% stop, NEGATIVE at chart-stop-only (-0.99).
    Reproduces the IBS/ema_adx truncation-flip shape under re-simulation."""
    if kw["premium_stop_pct"] <= -0.99 + 1e-9:
        return _StubFill(-20.0)   # chart-stop-only: loss runs -> negative
    return _StubFill(5.0)          # tight stop truncates the loser -> positive


def _real_sim_edge(**kw):
    """A REAL signal: strongly positive at BOTH the tight stop and chart-stop-only, and
    far above any random coin-flip (which the stub also makes mildly positive)."""
    # Signal entries (the candidate's note) earn a big edge; random-null entries earn little.
    if kw.get("setup", "").endswith("_NULL"):
        return _StubFill(2.0)
    return _StubFill(100.0)


def _one_signal_per_day(rth: pd.DataFrame, side: str = "C", bar_in_day: int = 20):
    """One CandidateSignal on the same intraday bar of each session in ``rth`` (so trades
    spread across days and the drop-top-5-DAYS check is non-degenerate)."""
    day_first = {}
    for i, ts in enumerate(rth["timestamp_et"]):
        d = ts.date()
        if d not in day_first:
            day_first[d] = i
    sigs = []
    for first in day_first.values():
        idx = first + bar_in_day
        if idx < len(rth):
            sigs.append(CandidateSignal(bar_idx=idx, side=side,
                                        rejection_level=float(rth.iloc[idx]["low"])))
    return sigs


def test_verify_candidate_resim_rejects_truncation_fake(monkeypatch):
    """Re-simulation path: a signal whose per-trade flips sign at chart-stop-only is
    flagged as a truncation artifact and REJECTED."""
    monkeypatch.setattr(fraud_gates, "simulate_trade_real", _fake_sim_truncation)
    rth = _synthetic_rth(days=10)
    signals = _one_signal_per_day(rth)
    v = verify_candidate(signals, rth, strike_offset=-1, premium_stop_pct=-0.08,
                         sim_fn=_fake_sim_truncation, seeds=3)
    assert v.chosen_per_trade == pytest.approx(5.0)
    assert v.chart_stop_only_per_trade == pytest.approx(-20.0)
    assert v.is_truncation_artifact is True
    assert v.no_truncation_pass is False
    assert v.passes is False


def test_verify_candidate_resim_passes_real_edge(monkeypatch):
    """Re-simulation path: a signal positive at BOTH stops and far above the random null
    PASSES both fraud gates."""
    monkeypatch.setattr(fraud_gates, "simulate_trade_real", _real_sim_edge)
    rth = _synthetic_rth(days=10)
    signals = _one_signal_per_day(rth)
    v = verify_candidate(signals, rth, strike_offset=-2, premium_stop_pct=-0.08,
                         sim_fn=_real_sim_edge, seeds=5)
    assert v.chosen_per_trade == pytest.approx(100.0)
    assert v.chart_stop_only_per_trade == pytest.approx(100.0)   # sign holds
    assert v.no_truncation_pass is True
    assert v.null_pass is True          # 100 beats null max (null entries ~2.0)
    assert v.passes is True


def test_verify_candidate_resim_error_fails_loud(monkeypatch):
    """A re-sim exception fails LOUD into the verdict (error set, passes False) -- never
    silently blesses a candidate (C7)."""
    def _boom(**kw):
        raise RuntimeError("opra read blew up")
    monkeypatch.setattr(fraud_gates, "simulate_trade_real", _boom)
    rth = _synthetic_rth()
    signals = [CandidateSignal(bar_idx=10, side="C", rejection_level=499.0)]
    v = verify_candidate(signals, rth, strike_offset=-2, premium_stop_pct=-0.08,
                         sim_fn=_boom, seeds=2)
    assert v.error is not None
    assert v.passes is False
