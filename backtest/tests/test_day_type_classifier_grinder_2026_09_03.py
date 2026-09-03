"""Guard suite for backtest/autoresearch/day_type_classifier_grinder.py (F5 day-type
classifier Kitchen grinder, DAY-TYPE-CLASSIFIER-GRINDER queue item). See
analysis/recommendations/prereg-day-type-classifier-2026-09-03.md for the frozen label
definition, feature list, model class, LOWO validation protocol, and ship-to-SHADOW
decision rule this module implements.

Covers (per task brief, >= 8 required):
  1. LOWO folds structurally never let a held-out week's rows leak into that fold's train set
  2/3. the frozen decision rule cannot emit SHADOW_CANDIDATE unless EVERY one of the five
       gates is True -- in particular never when a named anchor day is not 'paying'
       (anchor_days_ok False)
  4. the module's only write target is under analysis/recommendations/, nowhere else
  5. kitchen_daemon.py's GRINDER_REGISTRY carries the new entry and the module it points
     at is importable with a callable main()/run()
  6. the balanced-accuracy helper on known cases
  7/8. the missing-value policy ("never auto-stand-down on data we don't have") for both
       the single-split predictor and the tree predictor
  9. _fit_single_split recovers the correct threshold/direction on a cleanly separable
     synthetic feature
  10. _percentile / _iso_week primitive sanity
  11. run() end-to-end on a fully synthetic, monkeypatched label doc: dry_run=True writes
      nothing, dry_run=False writes exactly one well-formed file under a tmp OUT_DIR
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools", REPO / "backtest", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import autoresearch.day_type_classifier_grinder as g  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. LOWO folds never leak the held-out week
# ---------------------------------------------------------------------------------
def _mk_row(date: str, label: str, feat: dict | None = None, book_pnl: float = 0.0,
            n_closed: int = 1) -> dict:
    return {
        "date": date, "label": label, "y": 1 if label == "paying" else 0,
        "book_pnl": book_pnl, "n_closed": n_closed,
        "feat": feat or {f: None for f in g.ALL_FEATURES},
        "week": g._iso_week(date),
    }


def test_lowo_folds_never_leak_held_out_week():
    rows = [
        _mk_row("2026-07-02", "tax"), _mk_row("2026-07-03", "paying"),   # week 27
        _mk_row("2026-07-09", "tax"),                                     # week 28
        _mk_row("2026-07-16", "paying"), _mk_row("2026-07-17", "tax"),   # week 29
    ]
    folds = g._lowo_folds(rows)
    assert set(folds) == {(2026, 27), (2026, 28), (2026, 29)}
    seen_as_test = set()
    for week, split in folds.items():
        train_dates = {r["date"] for r in split["train"]}
        test_dates = {r["date"] for r in split["test"]}
        # structural non-leak: no date in this fold's test set is also in this fold's train set
        assert train_dates.isdisjoint(test_dates)
        # every test row in this fold actually belongs to the held-out week
        assert all(g._iso_week(d) == week for d in test_dates)
        # every train row belongs to some OTHER week
        assert all(g._iso_week(d) != week for d in train_dates)
        seen_as_test |= test_dates
    # every row appears as a test row in exactly one fold (the union covers everything)
    assert seen_as_test == {r["date"] for r in rows}


# ---------------------------------------------------------------------------------
# 2/3. decision rule requires ALL FIVE gates True; anchor_days_ok is non-negotiable
# ---------------------------------------------------------------------------------
_ALL_TRUE_GATES = {
    "anchor_days_ok": True, "wf_ge_0_70": True, "ci_lower_gt_1": True,
    "tax_removal_ge_50pct": True, "sub_window_stable": True,
}


def test_decision_rule_ships_only_when_all_five_gates_true():
    assert g.apply_decision_rule(dict(_ALL_TRUE_GATES)) == "SHADOW_CANDIDATE"


def test_decision_rule_cannot_ship_when_named_anchor_day_not_paying():
    gates = dict(_ALL_TRUE_GATES)
    gates["anchor_days_ok"] = False  # one of the 4 named anchor days was NOT 'paying'
    assert g.apply_decision_rule(gates) == "NOT_SHIPPABLE"


def test_decision_rule_requires_every_individual_gate():
    for key in _ALL_TRUE_GATES:
        gates = dict(_ALL_TRUE_GATES)
        gates[key] = False
        assert g.apply_decision_rule(gates) == "NOT_SHIPPABLE", f"gate {key} alone should block ship"


# ---------------------------------------------------------------------------------
# 4. output path is under analysis/recommendations/ only
# ---------------------------------------------------------------------------------
def test_output_path_lives_under_analysis_recommendations_only():
    path = g._output_path("2026-09-03")
    rel = path.relative_to(REPO).as_posix()
    assert rel == "analysis/recommendations/day-type-classifier-cook-2026-09-03.json"
    assert rel.startswith("analysis/recommendations/")


# ---------------------------------------------------------------------------------
# 5. GRINDER_REGISTRY entry present + module callable
# ---------------------------------------------------------------------------------
def _load_kitchen_daemon():
    """Same stub-loader pattern as test_kitchen_daemon_starvation.py -- chef_nemotron and
    swarm_client are heavy LLM-calling siblings, stubbed so importing kitchen_daemon.py
    performs no network/LLM calls."""
    fakes = {}
    for name in ("chef_nemotron", "swarm_client"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            if name == "chef_nemotron":
                mod.CHEF_SYSTEM_PROMPT = "stub"
                mod.MODEL_LADDER = []
                mod._call_with_ladder = lambda *a, **k: {"ok": False, "error": "stub"}
                mod._write_candidate = lambda *a, **k: Path(".")
                mod._slugify = lambda s: "stub"
                mod._gather_common_inputs = lambda: ""
            else:
                mod.call_role = lambda *a, **k: {"ok": False, "error": "stub"}
            sys.modules[name] = mod
            fakes[name] = mod
    inserted = "kitchen_daemon" not in sys.modules
    try:
        spec = importlib.util.spec_from_file_location(
            "kitchen_daemon", REPO / "setup" / "scripts" / "kitchen_daemon.py")
        kd_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kd_mod)
    finally:
        for name in fakes:
            sys.modules.pop(name, None)
    return kd_mod


def test_registry_entry_present_and_module_callable():
    kd = _load_kitchen_daemon()
    assert "day_type_classifier_grinder" in kd.GRINDER_REGISTRY
    info = kd.GRINDER_REGISTRY["day_type_classifier_grinder"]
    assert info["module"] == "autoresearch.day_type_classifier_grinder"
    assert "state_dir" in info and "description" in info
    # the module the registry points at is the real, importable grinder we just tested
    assert callable(g.main)
    assert callable(g.run)


# ---------------------------------------------------------------------------------
# 6. balanced accuracy helper
# ---------------------------------------------------------------------------------
def test_balanced_accuracy_known_cases():
    assert g._balanced_accuracy([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert g._balanced_accuracy([1, 1, 0, 0], [0, 0, 1, 1]) == 0.0
    # 1 of 2 tax correct (0.5) + 2 of 2 paying correct (1.0) -> mean 0.75
    assert g._balanced_accuracy([1, 1, 0, 0], [1, 1, 0, 1]) == 0.75


# ---------------------------------------------------------------------------------
# 7/8. missing-value policy: never auto-stand-down on data we don't have
# ---------------------------------------------------------------------------------
def test_single_split_predicts_trade_on_missing_feature():
    fit = {"threshold": 5.0, "direction": "low_is_paying", "train_balanced_acc": 0.9, "n_train_used": 10}
    assert g._predict_single_split(None, fit) == "trade"
    assert g._predict_single_split(None, None) == "trade"
    # sanity: a present value that would rule 'standdown' does trigger standdown
    assert g._predict_single_split(9.0, fit) == "standdown"


def test_tree_predicts_trade_on_missing_feature():
    train_rows = [
        _mk_row(f"2026-07-{2+i:02d}", "paying" if i % 2 == 0 else "tax",
                feat={**{f: None for f in g.ALL_FEATURES}, "vix_level_0935": 12.0 + i,
                      "prior_day_range_dollars": 3.0 + i})
        for i in range(8)
    ]
    clf = g._fit_tree(train_rows, ["vix_level_0935", "prior_day_range_dollars"])
    assert clf is not None
    missing_feat = {"vix_level_0935": None, "prior_day_range_dollars": 3.5}
    assert g._predict_tree(clf, missing_feat, ["vix_level_0935", "prior_day_range_dollars"]) == "trade"
    assert g._predict_tree(None, {"vix_level_0935": 12.0, "prior_day_range_dollars": 3.0},
                            ["vix_level_0935", "prior_day_range_dollars"]) == "trade"


# ---------------------------------------------------------------------------------
# 9. single-split fit recovers a cleanly separable rule
# ---------------------------------------------------------------------------------
def test_fit_single_split_recovers_separable_rule():
    # tax days: feature LOW (1..5); paying days: feature HIGH (10..14) -> clean separation
    train_rows = (
        [_mk_row(f"2026-07-{2+i:02d}", "tax", feat={"prior_day_range_dollars": 1.0 + i})
         for i in range(5)]
        + [_mk_row(f"2026-07-{9+i:02d}", "paying", feat={"prior_day_range_dollars": 10.0 + i})
           for i in range(5)]
    )
    fit = g._fit_single_split(train_rows, "prior_day_range_dollars")
    assert fit is not None
    assert fit["train_balanced_acc"] == 1.0
    # 'high_is_paying' with a threshold sitting between the two clusters classifies perfectly
    assert fit["direction"] == "high_is_paying"
    assert 5.0 <= fit["threshold"] <= 10.0
    for r in train_rows:
        pred = g._predict_single_split(r["feat"]["prior_day_range_dollars"], fit)
        expected = "trade" if r["label"] == "paying" else "standdown"
        assert pred == expected


# ---------------------------------------------------------------------------------
# 10. primitive sanity
# ---------------------------------------------------------------------------------
def test_percentile_basic():
    assert g._percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
    assert g._percentile([], 0.5) is None


def test_iso_week_groups_same_calendar_week():
    assert g._iso_week("2026-08-27") == g._iso_week("2026-08-28")  # Thu+Fri, same ISO week
    assert g._iso_week("2026-08-06") != g._iso_week("2026-08-13")  # different weeks


# ---------------------------------------------------------------------------------
# 11. run() end-to-end on a synthetic, fully monkeypatched doc -- no real files touched
# ---------------------------------------------------------------------------------
def _synthetic_doc() -> dict:
    def feat(prior_range):
        return {"features_0935": {**{f: None for f in g.FEATURES_0935},
                                   "prior_day_range_dollars": prior_range},
                "features_0945": {f: None for f in g.FEATURES_0945}}

    sessions = []
    # tax days: wide prior-day range; paying days (incl. all 4 named anchors): narrow range
    tax_dates = ["2026-07-02", "2026-07-09", "2026-08-20", "2026-09-03"]
    paying_dates = ["2026-07-16"] + list(g.NAMED_BIG_DAYS)  # 08-06/08-13/08-27/08-28
    for d in tax_dates:
        sessions.append({"date": d, "label": "tax", "book_pnl": -300.0, "n_closed": 4,
                          **feat(8.5)})
    for d in paying_dates:
        sessions.append({"date": d, "label": "paying", "book_pnl": 500.0, "n_closed": 4,
                          **feat(3.0)})
    return {
        "sessions": sessions,
        "label_summary": {"label_counts": {"tax": len(tax_dates), "paying": len(paying_dates)},
                           "n_sessions": len(sessions)},
    }


def test_run_end_to_end_dry_run_writes_nothing(monkeypatch, tmp_path):
    doc = _synthetic_doc()
    monkeypatch.setattr(g, "_load_labels", lambda today: (doc, False))
    monkeypatch.setattr(g, "OUT_DIR", tmp_path)
    out = g.run(dry_run=True)
    assert out["verdict"] in ("SHADOW_CANDIDATE", "NOT_SHIPPABLE")
    assert len(out["candidates"]) == len(g.ALL_FEATURES) + 1  # 10 single-split + 1 tree
    for c in out["candidates"]:
        assert c["verdict"] in ("SHADOW_CANDIDATE", "NOT_SHIPPABLE")
    assert list(tmp_path.iterdir()) == []  # dry_run must never write


def test_run_end_to_end_real_run_writes_exactly_one_file_under_out_dir(monkeypatch, tmp_path):
    doc = _synthetic_doc()
    monkeypatch.setattr(g, "_load_labels", lambda today: (doc, False))
    monkeypatch.setattr(g, "OUT_DIR", tmp_path)
    out = g.run(dry_run=False)
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].name.startswith("day-type-classifier-cook-")
    reread = json.loads(written[0].read_text(encoding="utf-8"))
    assert reread["verdict"] == out["verdict"]
    assert reread["best_candidate_id"] == out["best_candidate_id"]
    # the four named anchor days are all 'paying' in this synthetic fixture, so the
    # decision-rule test above's invariant must hold here too: if the file's overall
    # verdict is SHADOW_CANDIDATE, the winning candidate's anchor gate must be True
    if reread["verdict"] == "SHADOW_CANDIDATE":
        best = next(c for c in reread["candidates"] if c["candidate_id"] == reread["best_candidate_id"])
        assert best["gates"]["anchor_days_ok"] is True
