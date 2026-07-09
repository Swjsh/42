"""Guards for trade_autopsy.py -- the hypothesis organ (J 2026-07-08: 'why doesn't Gamma think
maybe we're stopping out too early'). Pure-logic only: tag classifier, rolling detectors,
dedupe. No network / no ledger. Red-proof style: each detector has a fires case AND a
below-threshold case, so a vacuous always-fires or never-fires regression reds."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "trade_autopsy", REPO / "setup" / "scripts" / "trade_autopsy.py")
ta = importlib.util.module_from_spec(_SPEC)
sys.modules["trade_autopsy"] = ta
_SPEC.loader.exec_module(ta)


# ---------- classify_position ----------

def test_stopped_then_paid_tag():
    c = ta.classify_position(actual_pnl=-58.0, entry_price=0.96, entry_bar_low=0.90,
                             post_exit_high=2.44, cf_pnls={"wide_stop_-50": 231.0})
    assert "stopped_then_paid" in c["tags"]          # the 741P type specimen
    assert "exit_shape_cost" in c["tags"]            # +231 vs -58 > $25
    assert c["best_counterfactual"] == "wide_stop_-50"
    assert abs(c["stop_cost_vs_best"] - 289.0) < 1e-6


def test_winner_not_tagged_stopped_then_paid():
    c = ta.classify_position(actual_pnl=120.0, entry_price=1.0, entry_bar_low=0.95,
                             post_exit_high=2.0, cf_pnls={"no_stop_ride": 110.0})
    assert "stopped_then_paid" not in c["tags"]      # only losses qualify
    assert "exit_shape_cost" not in c["tags"]        # we BEAT the probes


def test_paid_the_spike_threshold():
    hot = ta.classify_position(-10, entry_price=1.10, entry_bar_low=0.95,
                               post_exit_high=None, cf_pnls={})
    cool = ta.classify_position(-10, entry_price=1.00, entry_bar_low=0.98,
                                post_exit_high=None, cf_pnls={})
    assert "paid_the_spike" in hot["tags"] and "paid_the_spike" not in cool["tags"]


def test_exit_beat_theta_honesty_tag():
    """When riding would have lost MORE, the exit was right -- the organ must be able to say
    'our exit won' (no confirmation bias toward wider-is-better)."""
    c = ta.classify_position(actual_pnl=-40.0, entry_price=1.0, entry_bar_low=1.0,
                             post_exit_high=0.9, cf_pnls={"hold_to_time": -95.0})
    assert "exit_beat_theta" in c["tags"]


# ---------- detectors ----------

def _row(pnl, tags=(), spike=None, cost=None):
    return {"actual_pnl": pnl, "tags": list(tags), "entry_spike_pct": spike,
            "stop_cost_vs_best": cost}


def test_stop_noise_hypothesis_fires_and_respects_floor():
    losers = [_row(-50, tags=["stopped_then_paid"]) for _ in range(5)] + [_row(-40)]
    rows = losers + [_row(30)] * 4                          # 6 losers, 5/6 stopped-then-paid
    hyps = ta.detect_hypotheses(rows, "2026-07-09")
    assert any(h["mechanism"] == "stop_inside_noise_floor" for h in hyps)
    # below the MIN_LOSERS floor: silent (n-honesty -- no claims off 3 trades)
    hyps2 = ta.detect_hypotheses([_row(-50, tags=["stopped_then_paid"])] * 3, "2026-07-09")
    assert not any(h["mechanism"] == "stop_inside_noise_floor" for h in hyps2)


def test_stop_noise_below_fraction_is_silent():
    losers = [_row(-50, tags=["stopped_then_paid"]) for _ in range(3)] + [_row(-40)] * 4
    hyps = ta.detect_hypotheses(losers, "2026-07-09")       # 3/7 = 43% < 60%
    assert not any(h["mechanism"] == "stop_inside_noise_floor" for h in hyps)


def test_entry_spike_hypothesis():
    rows = [_row(-10, spike=0.12) for _ in range(9)]        # median 12% >= 8%, n>=8
    hyps = ta.detect_hypotheses(rows, "2026-07-09")
    assert any(h["mechanism"] == "paying_the_signal_spike" for h in hyps)
    rows2 = [_row(-10, spike=0.03) for _ in range(9)]
    assert not any(h["mechanism"] == "paying_the_signal_spike"
                   for h in ta.detect_hypotheses(rows2, "2026-07-09"))


def test_left_on_table_hypothesis():
    rows = [_row(-30, cost=120.0) for _ in range(5)]        # sum cost 600 >= 300 and >= 2*|net -150|
    hyps = ta.detect_hypotheses(rows, "2026-07-09")
    assert any(h["mechanism"] == "exit_shape_dominated" for h in hyps)


def test_dedupe_one_emission_per_week():
    new = [{"id": "H-2026-07-09-stop-noise", "mechanism": "stop_inside_noise_floor"}]
    recent = [{"mechanism": "stop_inside_noise_floor", "date": "2026-07-05"}]
    old = [{"mechanism": "stop_inside_noise_floor", "date": "2026-06-20"}]
    assert ta.dedupe_hypotheses(new, recent, "2026-07-09") == []      # emitted 4 days ago
    assert ta.dedupe_hypotheses(new, old, "2026-07-09") == new        # last emission stale


def test_every_hypothesis_carries_evidence_and_tests():
    """The contract with the downstream consumers (chef/conductor): a hypothesis without
    evidence numbers + concrete proposed_tests is just vibes -- reject at the source."""
    losers = [_row(-50, tags=["stopped_then_paid"]) for _ in range(6)]
    for h in ta.detect_hypotheses(losers + [_row(20)] * 3, "2026-07-09"):
        assert h["evidence"] and h["proposed_tests"] and h["claim"] and h["id"]
