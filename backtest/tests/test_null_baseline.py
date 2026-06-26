"""Tests for autoresearch.null_baseline — the shared random-entry NULL + standard gate.

The null gate is the C3/L58 exit-structure-artifact guard (LESSONS-LEARNED L171): a 0DTE
directional candidate whose per-trade a random-entry null reproduces is the asymmetric
exit bracket talking, not signal alpha. These tests pin the gate logic against the real
rejected artifact (analysis/recommendations/newhunt-rsi2-mean-reversion.json), prove the
RNG refactor preserves the legacy (random.seed) draw, and exercise the helper's branches
without needing OPRA data (simulate_trade_real is stubbed).
"""
from __future__ import annotations

import datetime as dt
import random

import pandas as pd
import pytest

from autoresearch import null_baseline
from autoresearch.null_baseline import null_gate, random_entry_null


# ── null_gate: the standard candidate-gate keys ──────────────────────────────

def test_null_gate_rejects_rsi2_artifact_exit_structure_case():
    """The decisive real case: RSI(2) mean-reversion best cell. per_trade +6.11 does NOT
    clear the random-null MAX (+8.10) even though it beats the mean (+2.66) and the
    drop-top5 (+2.87) beats the mean -> NOT a candidate (exit-structure artifact)."""
    null = {"per_trade_mean": 2.66, "per_trade_min": -5.73, "per_trade_max": 8.1}
    gate = null_gate(per_trade=6.11, drop_top5_per_trade=2.87, null=null)

    assert gate["beats_null_mean"] is True       # +6.11 > +2.66
    assert gate["beats_null_max"] is False        # +6.11 < +8.10  <-- the kill
    assert gate["drop_top5_beats_null_mean"] is True   # +2.87 > +2.66
    assert gate["edge_over_null_per_trade"] == 3.45    # 6.11 - 2.66
    # STANDARD bar requires beating the MAX, not just being positive -> fails.
    assert gate["null_pass"] is False


def test_null_gate_passes_when_signal_beats_max_and_drop_beats_mean():
    null = {"per_trade_mean": 2.66, "per_trade_max": 8.1}
    gate = null_gate(per_trade=12.0, drop_top5_per_trade=5.0, null=null)
    assert gate["beats_null_max"] is True
    assert gate["drop_top5_beats_null_mean"] is True
    assert gate["null_pass"] is True


def test_null_gate_fails_when_concentration_robust_drop_does_not_beat_mean():
    """Beats the MAX on headline, but the day-concentration-robust drop-top5 per-trade is
    below the null mean -> surviving edge is concentration, not signal -> still fails."""
    null = {"per_trade_mean": 2.66, "per_trade_max": 8.1}
    gate = null_gate(per_trade=12.0, drop_top5_per_trade=1.0, null=null)
    assert gate["beats_null_max"] is True
    assert gate["drop_top5_beats_null_mean"] is False
    assert gate["null_pass"] is False


def test_null_gate_handles_none_inputs():
    null = {"per_trade_mean": 2.66, "per_trade_max": 8.1}
    gate = null_gate(per_trade=None, drop_top5_per_trade=None, null=null)
    assert gate["beats_null_mean"] is False
    assert gate["beats_null_max"] is False
    assert gate["drop_top5_beats_null_mean"] is False
    assert gate["edge_over_null_per_trade"] is None
    assert gate["null_pass"] is False


def test_null_gate_strictly_greater_not_equal():
    """Tie with the max is NOT a pass (must strictly beat the luckiest coin-flip)."""
    null = {"per_trade_mean": 2.0, "per_trade_max": 8.0}
    gate = null_gate(per_trade=8.0, drop_top5_per_trade=3.0, null=null)
    assert gate["beats_null_max"] is False
    assert gate["null_pass"] is False


# ── reproducibility: the Random(seed) refactor preserves the legacy random.seed draw ──

def test_local_rng_matches_global_random_seed_sequence():
    """random_entry_null switched from module-global random.seed(s) to a private
    random.Random(s). For the same seed + population the Mersenne-Twister draw is
    identical, so the refactor does not move any already-published null number."""
    pop = list(range(500))
    for seed in range(5):
        random.seed(seed)
        legacy_pick = random.sample(pop, 30)
        legacy_sides = ["C"] * 18 + ["P"] * 12
        random.shuffle(legacy_sides)

        rng = random.Random(seed)
        new_pick = rng.sample(pop, 30)
        new_sides = ["C"] * 18 + ["P"] * 12
        rng.shuffle(new_sides)

        assert new_pick == legacy_pick
        assert new_sides == legacy_sides


# ── random_entry_null: branches + determinism (OPRA stubbed out) ──────────────

class _StubFill:
    def __init__(self, pnl: float):
        self.dollar_pnl = pnl


def _stub_sim(**kw):
    """Deterministic stand-in for simulate_trade_real: pnl = bar index * side sign, so
    different random draws produce a genuine spread across seeds."""
    return _StubFill(float(kw["entry_bar_idx"]) * (1.0 if kw["side"] == "C" else -1.0))


def _synthetic_rth(n: int = 78) -> pd.DataFrame:
    """One 5-min RTH day, 09:30 -> 09:30+5*(n-1) min, with close/low/high columns."""
    base = dt.datetime(2025, 6, 2, 9, 30)
    ts = [base + dt.timedelta(minutes=5 * i) for i in range(n)]
    close = [500.0 + 0.1 * i for i in range(n)]
    return pd.DataFrame({
        "timestamp_et": ts,
        "close": close,
        "low": [c - 0.5 for c in close],
        "high": [c + 0.5 for c in close],
    })


def test_random_entry_null_eligible_count_and_gate(monkeypatch):
    monkeypatch.setattr(null_baseline, "simulate_trade_real", _stub_sim)
    rth = _synthetic_rth()  # 09:30..15:55, 78 bars
    out = random_entry_null(rth, n_signals=20, n_call=12, n_put=8,
                            strike_offset=-1, premium_stop_pct=-0.08, seeds=5)
    # gate (09:35..15:45) excludes 09:30 (i=0) and 15:50/15:55 -> 75 in-window bars
    assert out["n_eligible"] == 75
    assert out["n_drawn"] == 20
    assert out["seeds"] == 5
    assert len(out["per_trade_by_seed"]) == 5
    assert out["per_trade_min"] <= out["per_trade_mean"] <= out["per_trade_max"]


def test_random_entry_null_is_deterministic(monkeypatch):
    monkeypatch.setattr(null_baseline, "simulate_trade_real", _stub_sim)
    rth = _synthetic_rth()
    a = random_entry_null(rth, n_signals=15, n_call=8, n_put=7,
                          strike_offset=0, premium_stop_pct=-0.2, seeds=7)
    b = random_entry_null(rth, n_signals=15, n_call=8, n_put=7,
                          strike_offset=0, premium_stop_pct=-0.2, seeds=7)
    assert a == b


def test_random_entry_null_pads_mismatched_side_mix(monkeypatch):
    """n_call + n_put < n_signals must not IndexError (majority-side padding)."""
    monkeypatch.setattr(null_baseline, "simulate_trade_real", _stub_sim)
    rth = _synthetic_rth()
    out = random_entry_null(rth, n_signals=10, n_call=3, n_put=2,
                            strike_offset=0, premium_stop_pct=-0.08, seeds=3)
    assert out["n_drawn"] == 10  # drew the full requested count without error


def test_random_entry_null_empty_gate_returns_zero(monkeypatch):
    monkeypatch.setattr(null_baseline, "simulate_trade_real", _stub_sim)
    rth = _synthetic_rth()
    out = random_entry_null(rth, n_signals=10, n_call=5, n_put=5,
                            strike_offset=0, premium_stop_pct=-0.08,
                            entry_gate=(dt.time(3, 0), dt.time(4, 0)), seeds=3)
    assert out["n_eligible"] == 0
    assert out["per_trade_mean"] == 0.0
    assert out["note"]


def test_random_entry_null_eligible_idx_override(monkeypatch):
    """Explicit eligible_idx overrides the time-gate entirely."""
    monkeypatch.setattr(null_baseline, "simulate_trade_real", _stub_sim)
    rth = _synthetic_rth()
    out = random_entry_null(rth, n_signals=3, n_call=3, n_put=0,
                            strike_offset=0, premium_stop_pct=-0.08,
                            eligible_idx=[0, 1, 2], seeds=2)
    assert out["n_eligible"] == 3
    assert out["n_drawn"] == 3


def test_random_entry_null_feeds_null_gate(monkeypatch):
    """End-to-end: the null dict plugs straight into null_gate."""
    monkeypatch.setattr(null_baseline, "simulate_trade_real", _stub_sim)
    rth = _synthetic_rth()
    null = random_entry_null(rth, n_signals=20, n_call=20, n_put=0,
                             strike_offset=0, premium_stop_pct=-0.08, seeds=5)
    gate = null_gate(per_trade=null["per_trade_max"] + 1.0,
                     drop_top5_per_trade=null["per_trade_mean"] + 1.0, null=null)
    assert gate["null_pass"] is True
    assert set(gate) == {"beats_null_mean", "beats_null_max",
                         "drop_top5_beats_null_mean", "edge_over_null_per_trade",
                         "null_pass"}
