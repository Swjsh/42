"""Guards for the 2026-07-28 P&L attribution + min_triggers_bear 1->2 gate A/B.

Three layers:
1. Unit: trigger_class partition + cohort_stats math (synthetic fixtures).
2. Unit: evaluate_gates -- the four pre-registered gates must each be able to FAIL
   (a gate that cannot fail is not a gate).
3. Artifact pins: the committed 2026-07-28 analysis JSONs must stay internally
   consistent (delta accounting to the cent, gate-4 = removed-heldout sum). These
   files are dated one-shots; if regenerated with different data they get new names,
   so exact pins are intentional.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest" / "tools"))

from min_triggers_bear2_gate_ab_2026_07_28 import evaluate_gates  # noqa: E402
from pnl_attribution_2026_07_28 import cohort_stats, trigger_class  # noqa: E402

ATTRIB = ROOT / "analysis" / "deep-research" / "PNL-ATTRIBUTION-2026-07-28.json"
AB = ROOT / "analysis" / "deep-research" / "min-triggers-bear2-ab-2026-07-28.json"
REPLAY = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"


# ---------------------------------------------------------------- trigger_class
@pytest.mark.parametrize("triggers,expected", [
    (["trendline_rejection"], "TL_only"),
    (["ribbon_flip", "trendline_rejection"], "TL_only"),
    (["level_reclaim", "ribbon_flip"], "LEVEL_tied"),
    (["confluence", "level_rejection"], "LEVEL_tied"),
    (["confluence", "level_reclaim", "sequence_reclaim"], "LEVEL_tied"),
    (["confluence", "level_rejection", "trendline_rejection"], "BOTH"),
    (["level_rejection", "ribbon_flip", "trendline_rejection"], "BOTH"),
    ([], "NEITHER"),
    (["ribbon_flip"], "NEITHER"),
    (None, "NEITHER"),
])
def test_trigger_class(triggers, expected):
    assert trigger_class(triggers) == expected


def test_trigger_class_partitions_replay_population():
    trades = json.loads(REPLAY.read_text(encoding="utf-8"))["trades"]
    counts = {}
    for t in trades:
        counts[trigger_class(t["triggers"])] = counts.get(trigger_class(t["triggers"]), 0) + 1
    assert counts == {"TL_only": 124, "LEVEL_tied": 57, "BOTH": 9}


# ---------------------------------------------------------------- cohort_stats
def test_cohort_stats_math():
    trades = [
        {"date": "2026-01-01", "dollar_pnl": 100.0},
        {"date": "2026-01-01", "dollar_pnl": -30.0},
        {"date": "2026-01-02", "dollar_pnl": -50.0},
    ]
    s = cohort_stats(trades)
    assert s["n"] == 3
    assert s["total"] == 20.0
    assert s["wr"] == round(1 / 3, 4)
    assert s["drop_best"] == -80.0     # 20 - 100
    assert s["drop_worst"] == 70.0     # 20 - (-50)
    assert s["n_up_days"] == 1 and s["n_down_days"] == 1


def test_cohort_stats_empty():
    s = cohort_stats([])
    assert s["n"] == 0 and s["total"] == 0.0 and s["wr"] is None


# ---------------------------------------------------------------- evaluate_gates
def test_gates_all_pass_case():
    base = {"d1": -100.0, "d2": -50.0, "d3": 10.0, "h1": -40.0}
    var = {"d3": 10.0}  # d1/d2/h1 trades removed (losers), d3 untouched
    g = evaluate_gates(base, var, heldout={"h1"})
    assert g["gate_1_positive_aggregate"]["pass"]           # +190
    assert g["gate_2_day_majority"]["pass"]                 # 3 improved / 0 worsened
    assert g["gate_3_survives_drop_best"]["pass"]           # 190 - 100 = 90 > 0
    assert g["gate_4_heldout_positive"]["pass"]             # +40
    assert g["all_pass"]


def test_gate2_day_majority_can_fail():
    # aggregate positive from ONE huge day, but most changed days worsen
    base = {"d1": -500.0, "d2": 10.0, "d3": 10.0, "d4": 10.0}
    var = {"d2": 5.0, "d3": 5.0, "d4": 5.0}
    g = evaluate_gates(base, var, heldout=set())
    assert g["gate_1_positive_aggregate"]["pass"]
    assert not g["gate_2_day_majority"]["pass"]
    assert not g["all_pass"]


def test_gate3_drop_best_can_fail():
    base = {"d1": -300.0, "d2": 20.0}
    var = {"d2": 10.0}  # delta: d1 +300, d2 -10 -> total +290, minus best (300) = -10
    g = evaluate_gates(base, var, heldout=set())
    assert g["gate_1_positive_aggregate"]["pass"]
    assert not g["gate_3_survives_drop_best"]["pass"]
    assert not g["all_pass"]


def test_gate4_heldout_can_fail():
    base = {"d1": -200.0, "h1": 50.0}
    var = {}  # removing a heldout WINNER costs the heldout window
    g = evaluate_gates(base, var, heldout={"h1"})
    assert g["gate_1_positive_aggregate"]["pass"]
    assert not g["gate_4_heldout_positive"]["pass"]
    assert not g["all_pass"]


# ---------------------------------------------------------------- artifact pins
def test_attribution_trigger_class_sums_to_replay_total():
    d = json.loads(ATTRIB.read_text(encoding="utf-8"))
    tc = d["replay_slices"]["trigger_class"]
    total = sum(v["total"] for v in tc.values())
    assert abs(total - d["replay_total_recomputed"]) < 0.01
    assert abs(d["replay_total_recomputed"] - 5064.75) < 0.01
    assert tc["TL_only"]["n"] == 124 and tc["TL_only"]["total"] == -1830.10


def test_ab_delta_accounting_closes():
    d = json.loads(AB.read_text(encoding="utf-8"))
    h = d["headline"]
    assert d["status"] == "COMPLETE"
    assert abs(h["delta_total"] - (h["variant_total"] - h["baseline_total"])) < 0.01
    # removed + added + verified leg-2 knock-on == delta, to the cent
    leg2 = d["post_verification_too_good_hunt"]["delta_accounting_exact"][
        "leg2_sizing_knock_on_2025_02_20"]
    assert abs((-h["removed_trades_pnl"]) + h["added_trades_pnl"] + leg2 - h["delta_total"]) < 0.01
    # gate 4 == sum of removed heldout trades (no added trades fell in heldout)
    inv = json.loads((ROOT / "analysis" / "edge-matrix" / "day-inventory-extended.json")
                     .read_text(encoding="utf-8"))
    heldout = set(inv["heldout_days"])
    removed_h = sum(r["dollar_pnl"] for r in d["removed_trades"] if r["date"] in heldout)
    assert abs(d["gates"]["gate_4_heldout_positive"]["heldout_delta"] - (-removed_h)) < 0.01
    # removal must be surgical: every removed trade is a 1-trigger bear trendline entry
    for r in d["removed_trades"]:
        assert r["side"] == "P" and r["triggers"] == ["trendline_rejection"]
