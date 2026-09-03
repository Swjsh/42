#!/usr/bin/env python
"""day_type_classifier_grinder.py -- Kitchen grinder that FITS + VALIDATES the F5
day-type classifier (paying / tax) exactly as frozen in
analysis/recommendations/prereg-day-type-classifier-2026-09-03.md. Read that prereg for
the label definition, the frozen feature list, the frozen model class, the frozen
leave-one-week-out (LOWO) validation protocol, and the frozen ship-to-SHADOW decision
rule -- this module implements sections 3-5 of that document VERBATIM; it does not
re-derive or soften any of them.

WHAT THIS MODULE DOES (and does NOT do):
  - Loads analysis/recommendations/day-type-labels.json (regenerating it via
    backtest/tools/day_type_labels.py ONLY if today's ET session date does not match the
    file's own `_meta.today_session_et` stamp -- i.e. only when it is stale for the
    CURRENT trading day, never unconditionally).
  - Fits 11 candidates: one single-threshold split rule per frozen feature (10 features,
    prereg section 2) PLUS one depth-2 sklearn.tree.DecisionTreeClassifier over all 10
    features (prereg section 3) -- both classes are fit PER LOWO FOLD on that fold's
    training weeks only, never on the held-out week.
  - Scores every candidate against the frozen decision rule (prereg section 5): keeps
    all 4 named anchor days 'paying' in every fold, removes >=50% of tax-day entries OOS,
    WF>=0.70, and go_live_gate.bootstrap_pf_ci ci_lower_2.5>1.0 on the pooled
    trade-predicted sessions' daily book_pnl. A fifth gate (sub_window_stable, prereg
    section 4 point 6) is ALSO enforced even though section 5's own bullet list does not
    restate it -- this mirrors CLAUDE.md OP-11's project-wide auto-ratify formula
    ("OOS_positive AND WF>=0.70 AND sub_window_stable AND anchor_no_regression"), a
    disclosed judgment call, not a silent addition (see DECISION_RULE for the exact text).
  - Writes ONE file: analysis/recommendations/day-type-classifier-cook-<date>.json
    (date computed in-script from et_clock, never hardcoded). NEVER writes anywhere else
    -- no strategy/candidates/ doc, no progress.json/keepers.jsonl grinder-state files
    (this module has nothing meaningful to report through that channel; when invoked
    through kitchen_daemon.py's shared _run_grinder_task harness, the daemon's OWN
    existing, unmodified code still writes its usual DRAFT strategy/candidates/*.md
    summary pointer regardless of which grinder ran -- that is pre-existing shared-harness
    behaviour this module has no way to opt out of and does not itself perform).
  - Never fits, ships, or arms anything live. The most this module can ever emit is the
    string "SHADOW_CANDIDATE" (permission to build a forward shadow clock per prereg
    section 6, itself a FUTURE build) or "NOT_SHIPPABLE". Nothing here touches the
    trading path, journal/**, or automation/state/** other than READING
    automation/state/{fills-ledger,core-decisions}.jsonl indirectly via
    day_type_labels.run() when a regenerate is actually triggered.

MODEL CLASS (prereg section 3, reused not re-derived):
  1. single_split  -- one threshold on ONE frozen feature, direction searched over
     {high_is_paying, low_is_paying}, threshold candidates = that feature's own DECILE
     grid computed FROM THE TRAINING FOLD ONLY (never the pooled/global population --
     that would leak the held-out week's distribution into the fit).
  2. tree_depth2   -- sklearn.tree.DecisionTreeClassifier(max_depth=2,
     class_weight="balanced"), same library + same class of problem already installed
     and used in backtest/tools/build_regime_early_classifier.py (checked installed in
     backtest/.venv THIS build -- sklearn 1.9.0 -- no new dependency risk, nothing
     installed by this module). SKLEARN-OPTIONALITY-2026-09-03: sklearn is a venv-only dep
     (the system interpreter lacks it; the nightly suite puts backtest/.venv's site-packages
     on PYTHONPATH) -- the import is lazy/optional (SKLEARN_AVAILABLE flag) so this module
     and its 10 single_split candidates always run; when sklearn is missing, tree_depth2
     alone is never fit and reports verdict "SKIPPED_NO_SKLEARN" (disclosed skip, distinct
     from a real NOT_SHIPPABLE where gates were evaluated and failed).

MISSING-VALUE POLICY (disclosed, not silent): a session missing the value a candidate
needs at PREDICT time is always predicted "trade" (never auto-stand-down on missing
data) -- the conservative direction, since standing a session down on data the classifier
never actually saw would be exactly the kind of silent-fallback failure CLAUDE.md's
judgment guards forbid.

VALIDATION (prereg section 4): leave-one-ISO-calendar-week-out. `_lowo_folds` builds every
fold's train/test split so that NO row in a held-out week's test set can ever appear in
that same fold's train set -- structural by construction (a dict comprehension over
`week != held_out_week`), not a runtime filter, mirroring the "receives only the
already-sliced slice" no-look-ahead pattern day_type_labels.py itself uses for ticks.

$0. Pure Python + sklearn (already installed in backtest/.venv; optional at import time --
see SKLEARN-OPTIONALITY-2026-09-03 above). Read-only on automation/state/** (only via
day_type_labels.run(), and only when stale for today). Never places an order, never
touches params*.json/heartbeat_core.py/strategies.py/accounts.json/CLAUDE.md.

CLI contract (kitchen_daemon.py GRINDER_REGISTRY / _run_grinder_task, followed exactly):
    <python> -m autoresearch.day_type_classifier_grinder --hours H --workers W
  --hours/--workers are accepted for harness compatibility (this module ignores their
  values -- there is no parameter sweep to time-box and no multi-worker pool; a single
  LOWO-CV fit over 11 candidates on ~32 labeled sessions is a low-single-digit-second
  computation, verified this build). --dry-run computes everything but skips the write
  (used for testing only). Direct manual run (this module is always cached-data-only /
  offline -- there is no separate "online" mode to distinguish, no network call exists
  anywhere in this file):
    backtest/.venv/Scripts/python.exe -m autoresearch.day_type_classifier_grinder
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(REPO), str(BACKTEST / "tools"), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import day_type_labels as dtl  # noqa: E402 -- backtest/tools/day_type_labels.py
import go_live_gate  # noqa: E402 -- setup/scripts/go_live_gate.py (bootstrap_pf_ci only)

try:
    from sklearn.tree import DecisionTreeClassifier  # noqa: E402
    SKLEARN_AVAILABLE = True
except ImportError:  # sklearn is a venv-only optional dep (nightly suite puts backtest/.venv's
    # site-packages on PYTHONPATH; the system interpreter does not have it) -- lazy/optional per
    # SKLEARN-OPTIONALITY-2026-09-03: the module and its single_split candidates must still run
    # under the system interpreter. The tree_depth2 candidate alone degrades to
    # verdict SKIPPED_NO_SKLEARN (disclosed, never silently substituted) instead of crashing --
    # see _evaluate_candidate's short-circuit and _fit_tree's guard below.
    DecisionTreeClassifier = None  # type: ignore[assignment,misc]
    SKLEARN_AVAILABLE = False

OUT_DIR = REPO / "analysis" / "recommendations"
PREREG_REL = "analysis/recommendations/prereg-day-type-classifier-2026-09-03.md"

NAMED_BIG_DAYS = dtl.NAMED_BIG_DAYS  # ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")

FEATURES_0935 = [
    "overnight_gap_dollars", "overnight_gap_pct", "prior_day_range_dollars",
    "vix_level_0935", "vix_overnight_change", "vix_5d_slope", "vix_20d_slope",
]
FEATURES_0945 = [
    "opening_range_width_dollars", "opening_range_position_vs_prior_range",
    "first_15min_ribbon_flips_count",
]
ALL_FEATURES = FEATURES_0935 + FEATURES_0945

FEATURES_EXCLUDED = {
    "day_of_week": "categorical -- no natural decile threshold for a single-split rule",
    "event_calendar_flag": "boolean with heavy missingness (context_bundle v1.1 only from "
                            "2026-07-15) -- not a continuous decile-splittable feature",
    "es_spy_premarket_trend": "always null in this repo -- no cached ES/premarket-futures "
                               "bar series exists anywhere (day_type_labels.py verified this)",
}

DECISION_RULE = {
    "source": PREREG_REL + " section 5 (+ section 4 point 6 for the fifth gate)",
    "gates_required_all_true_for_shadow_candidate": [
        "anchor_days_ok -- none of the 4 named anchor days is ever predicted stand-down "
        "in the LOWO fold where its own week is held out",
        "tax_removal_ge_50pct -- at least half of all tax-labeled sessions' closed-activity "
        "entries, pooled across OOS folds, occurred on a session predicted stand-down "
        "(weighted by entries-per-session per the prereg's own equivalence)",
        "wf_ge_0_70 -- fraction of LOWO folds whose fold_success is True (prereg section 4 "
        "point 3) is >= 0.70",
        "ci_lower_gt_1 -- go_live_gate.bootstrap_pf_ci ci_lower_2.5 > 1.0 on the pooled "
        "trade-predicted sessions' daily book_pnl (n_boot=20000, the go-live gate's own "
        "criterion, not a softer one invented here)",
        "sub_window_stable -- no single held-out week accounts for more than 50% of the "
        "pooled trade-predicted P&L. Section 5's own bullet list does not restate this "
        "explicitly, but section 4 point 6 freezes it as part of the SAME validation "
        "protocol section 5 draws from, and CLAUDE.md OP-11's project-wide auto-ratify "
        "formula requires it alongside WF and OOS-positive for every instrument of this "
        "shape -- included here as a disclosed judgment call, not a silent addition.",
    ],
    "verdict_enum": ["SHADOW_CANDIDATE", "NOT_SHIPPABLE"],
    "reaching_the_bar_means": "permission to build the SHADOW forward clock (prereg section "
                               "6, a distinct FUTURE build) -- never permission to ship live.",
}


# ------------------------------------------------------------------------------------------
# generic helpers
# ------------------------------------------------------------------------------------------
def _today_et() -> str:
    from et_clock import et_now  # noqa: PLC0415 -- CLAUDE.md: ET via et_clock, never Bash TZ
    return et_now().date().isoformat()


def _iso_week(date_str: str) -> tuple[int, int]:
    iso = dt.date.fromisoformat(date_str).isocalendar()
    return (iso[0], iso[1])


def _percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolation percentile (numpy-free, matches day_type_labels._slope's
    numpy-free convention). p in [0, 1]."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def _output_path(today: str) -> Path:
    """Single write target -- analysis/recommendations/ ONLY, never anywhere else."""
    return OUT_DIR / f"day-type-classifier-cook-{today}.json"


def apply_decision_rule(gates: dict) -> str:
    """Pure function over a gates dict -> 'SHADOW_CANDIDATE' | 'NOT_SHIPPABLE'. Standalone
    and independently testable: CANNOT return SHADOW_CANDIDATE unless gates['anchor_days_ok']
    is True, no matter what the other four gates say (prereg section 5's first bullet)."""
    required = ("anchor_days_ok", "wf_ge_0_70", "ci_lower_gt_1",
                "tax_removal_ge_50pct", "sub_window_stable")
    if all(gates.get(k) is True for k in required):
        return "SHADOW_CANDIDATE"
    return "NOT_SHIPPABLE"


# ------------------------------------------------------------------------------------------
# 1. load labels (regenerate if stale for TODAY only)
# ------------------------------------------------------------------------------------------
def _load_labels(today: str) -> tuple[dict, bool]:
    """Returns (doc, regenerated). Regenerates ONLY when the on-disk file is missing,
    corrupt, or stamped for a different ET session date than today -- never
    unconditionally (day_type_labels.py is cheap but there is no reason to re-derive an
    already-fresh table)."""
    if dtl.OUT_JSON.exists():
        try:
            existing = json.loads(dtl.OUT_JSON.read_text(encoding="utf-8"))
            if existing.get("_meta", {}).get("today_session_et") == today:
                return existing, False
        except (json.JSONDecodeError, OSError):
            pass
    return dtl.run(), True


def _row_from_session(s: dict) -> dict:
    f0935 = s.get("features_0935") or {}
    f0945 = s.get("features_0945") or {}
    feat = {name: f0935.get(name) for name in FEATURES_0935}
    feat.update({name: f0945.get(name) for name in FEATURES_0945})
    return {
        "date": s["date"], "label": s["label"], "y": 1 if s["label"] == "paying" else 0,
        "book_pnl": s["book_pnl"], "n_closed": s["n_closed"], "feat": feat,
        "week": _iso_week(s["date"]),
    }


def _lowo_folds(labeled_rows: list[dict]) -> dict[tuple, dict]:
    """week -> {'train': [...], 'test': [...]}. Structural no-leak: test rows for week W
    are EVERY row whose week == W; train rows are EVERY row whose week != W. A row can
    never be in both for the same fold by construction."""
    weeks = sorted({r["week"] for r in labeled_rows})
    return {
        w: {
            "train": [r for r in labeled_rows if r["week"] != w],
            "test": [r for r in labeled_rows if r["week"] == w],
        }
        for w in weeks
    }


# ------------------------------------------------------------------------------------------
# 2. single-split candidate: fit (train fold only) + predict
# ------------------------------------------------------------------------------------------
def _balanced_accuracy(y_true: list[int], y_pred: list[int]) -> float:
    tax_idx = [i for i, y in enumerate(y_true) if y == 0]
    pay_idx = [i for i, y in enumerate(y_true) if y == 1]
    parts = []
    if tax_idx:
        parts.append(sum(1 for i in tax_idx if y_pred[i] == 0) / len(tax_idx))
    if pay_idx:
        parts.append(sum(1 for i in pay_idx if y_pred[i] == 1) / len(pay_idx))
    return sum(parts) / len(parts) if parts else 0.0


_DECILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
_DIRECTIONS = ("high_is_paying", "low_is_paying")


def _fit_single_split(train_rows: list[dict], feature: str) -> dict | None:
    """Threshold grid = the feature's OWN deciles computed from train_rows only. Ties in
    balanced accuracy are broken deterministically: ascending threshold, then
    'high_is_paying' before 'low_is_paying' (fixed iteration order, first-strictly-better
    wins)."""
    vals = [(r["feat"].get(feature), r["y"]) for r in train_rows if r["feat"].get(feature) is not None]
    if len(vals) < 4:
        return None
    xs = [v for v, _ in vals]
    thresholds = sorted({t for t in (_percentile(xs, p) for p in _DECILES) if t is not None})
    if not thresholds:
        return None
    y_true = [y for _, y in vals]
    best = None
    for t in thresholds:
        for direction in _DIRECTIONS:
            y_pred = []
            for x, _ in vals:
                pred_paying = (x > t) if direction == "high_is_paying" else (x <= t)
                y_pred.append(1 if pred_paying else 0)
            ba = _balanced_accuracy(y_true, y_pred)
            if best is None or ba > best["train_balanced_acc"]:
                best = {"threshold": t, "direction": direction, "train_balanced_acc": ba,
                        "n_train_used": len(vals)}
    return best


def _predict_single_split(feat_value, fit: dict | None) -> str:
    if fit is None or feat_value is None:
        return "trade"  # missing-value policy: never auto-stand-down on data we don't have
    pred_paying = ((feat_value > fit["threshold"]) if fit["direction"] == "high_is_paying"
                   else (feat_value <= fit["threshold"]))
    return "trade" if pred_paying else "standdown"


# ------------------------------------------------------------------------------------------
# 3. depth-2 tree candidate: fit (train fold only) + predict
# ------------------------------------------------------------------------------------------
def _fit_tree(train_rows: list[dict], features: list[str]) -> DecisionTreeClassifier | None:
    if not SKLEARN_AVAILABLE:
        # loud, not silent: a caller that reaches here directly (bypassing
        # _evaluate_candidate's SKIPPED_NO_SKLEARN short-circuit) gets a clear error rather
        # than a NoneType-not-callable on DecisionTreeClassifier(...) below.
        raise RuntimeError(
            "_fit_tree called but sklearn is not importable -- callers must check "
            "SKLEARN_AVAILABLE (see _evaluate_candidate's short-circuit) before calling this"
        )
    X, y = [], []
    for r in train_rows:
        vals = [r["feat"].get(f) for f in features]
        if any(v is None for v in vals):
            continue  # tree needs a complete row -- rows with any missing feature dropped
        X.append(vals)
        y.append(r["y"])
    if len(X) < 4 or len(set(y)) < 2:
        return None
    clf = DecisionTreeClassifier(max_depth=2, class_weight="balanced", random_state=42)
    clf.fit(X, y)
    return clf


def _predict_tree(clf: DecisionTreeClassifier | None, feat: dict, features: list[str]) -> str:
    vals = [feat.get(f) for f in features]
    if clf is None or any(v is None for v in vals):
        return "trade"  # same missing-value policy as the single-split predictor
    pred = clf.predict([vals])[0]
    return "trade" if int(pred) == 1 else "standdown"


# ------------------------------------------------------------------------------------------
# 4. per-candidate LOWO evaluation -> WF, pooled OOS PF, tax-removal, sub-window, gates
# ------------------------------------------------------------------------------------------
def _evaluate_candidate(kind: str, spec, labeled_rows: list[dict], folds: dict) -> dict:
    if kind != "single_split" and not SKLEARN_AVAILABLE:
        # sklearn unavailable (system interpreter, no venv site-packages on PYTHONPATH) --
        # disclosed skip, never a silent fallback: the tree candidate is never fit/predicted
        # on any fold, so every downstream number here is None/0/False rather than fabricated.
        # apply_decision_rule() is deliberately NOT called -- SKIPPED_NO_SKLEARN must never be
        # confusable with a real NOT_SHIPPABLE (gates evaluated and failed).
        return {
            "WF": 0.0,
            "n_folds": 0,
            "fold_details": [],
            "anchor_day_predictions": {d: "NOT_PREDICTED" for d in NAMED_BIG_DAYS},
            "oos": {
                "n_trade_predicted_sessions": 0, "bootstrap_pf_ci": None, "ci_lower_2.5": None,
                "tax_removal_rate": None, "total_tax_entries": 0, "removed_tax_entries": 0,
                "max_week_pnl_share": None, "sub_window_stable": False,
            },
            "gates": {
                "anchor_days_ok": False, "wf_ge_0_70": False, "ci_lower_gt_1": False,
                "tax_removal_ge_50pct": False, "sub_window_stable": False,
            },
            "verdict": "SKIPPED_NO_SKLEARN",
        }

    predictions: dict[str, str] = {}
    fold_details = []

    for week, split in sorted(folds.items()):
        train_rows, test_rows = split["train"], split["test"]
        if kind == "single_split":
            fit = _fit_single_split(train_rows, spec)
        else:
            fit = _fit_tree(train_rows, spec)

        for r in test_rows:
            pred = (_predict_single_split(r["feat"].get(spec), fit) if kind == "single_split"
                    else _predict_tree(fit, r["feat"], spec))
            predictions[r["date"]] = pred

        anchor_here = [r["date"] for r in test_rows if r["date"] in NAMED_BIG_DAYS]
        anchor_ok = all(predictions[d] == "trade" for d in anchor_here) if anchor_here else True

        n_tax = sum(1 for r in test_rows if r["label"] == "tax")
        n_tax_blocked = sum(1 for r in test_rows if r["label"] == "tax" and predictions[r["date"]] == "standdown")
        n_paying = sum(1 for r in test_rows if r["label"] == "paying")
        n_paying_blocked = sum(1 for r in test_rows if r["label"] == "paying" and predictions[r["date"]] == "standdown")
        share_tax_blocked = (n_tax_blocked / n_tax) if n_tax else None
        share_paying_blocked = (n_paying_blocked / n_paying) if n_paying else 0.0
        direction_ok = True if n_tax == 0 else (share_tax_blocked > share_paying_blocked)
        fold_success = bool(anchor_ok and direction_ok)

        fold_details.append({
            "week": f"{week[0]}-W{week[1]:02d}", "n_train": len(train_rows), "n_test": len(test_rows),
            "anchor_days_in_fold": anchor_here, "anchor_ok": anchor_ok,
            "n_tax": n_tax, "n_tax_blocked": n_tax_blocked,
            "n_paying": n_paying, "n_paying_blocked": n_paying_blocked,
            "share_tax_blocked": share_tax_blocked, "share_paying_blocked": share_paying_blocked,
            "direction_ok": direction_ok, "fold_success": fold_success,
            "fit_used": (None if fit is None else
                         {"threshold": fit["threshold"], "direction": fit["direction"],
                          "train_balanced_acc": round(fit["train_balanced_acc"], 4)}
                         if kind == "single_split" else "tree_fit_ok"),
        })

    WF = round(sum(1 for f in fold_details if f["fold_success"]) / len(fold_details), 4) if fold_details else 0.0

    trade_days = [(r["date"], r["book_pnl"], r["week"]) for r in labeled_rows
                  if predictions.get(r["date"]) == "trade"]
    day_values = [v for _, v, _ in trade_days]
    ci = go_live_gate.bootstrap_pf_ci(day_values) if len(day_values) >= 2 else None

    total_tax_entries = sum(r["n_closed"] for r in labeled_rows if r["label"] == "tax")
    removed_tax_entries = sum(r["n_closed"] for r in labeled_rows
                               if r["label"] == "tax" and predictions.get(r["date"]) == "standdown")
    tax_removal_rate = (removed_tax_entries / total_tax_entries) if total_tax_entries else None

    per_week_sum: dict[tuple, float] = {}
    for _, v, wk in trade_days:
        per_week_sum[wk] = per_week_sum.get(wk, 0.0) + v
    total_pnl = sum(per_week_sum.values())
    if per_week_sum and total_pnl != 0:
        max_week_share = max(abs(s) for s in per_week_sum.values()) / abs(total_pnl)
        sub_window_stable = max_week_share <= 0.5
    else:
        max_week_share = None
        sub_window_stable = False

    anchor_present = all(d in predictions for d in NAMED_BIG_DAYS)
    anchor_all_trade = all(predictions.get(d) == "trade" for d in NAMED_BIG_DAYS)

    gates = {
        "anchor_days_ok": bool(anchor_present and anchor_all_trade),
        "wf_ge_0_70": WF >= 0.70,
        "ci_lower_gt_1": bool(ci is not None and ci["ci_lower_2.5"] > 1.0),
        "tax_removal_ge_50pct": bool(tax_removal_rate is not None and tax_removal_rate >= 0.5),
        "sub_window_stable": bool(sub_window_stable),
    }
    verdict = apply_decision_rule(gates)

    return {
        "WF": WF,
        "n_folds": len(fold_details),
        "fold_details": fold_details,
        "anchor_day_predictions": {d: predictions.get(d, "NOT_PREDICTED") for d in NAMED_BIG_DAYS},
        "oos": {
            "n_trade_predicted_sessions": len(trade_days),
            "bootstrap_pf_ci": ci,
            "ci_lower_2.5": (ci["ci_lower_2.5"] if ci else None),
            "tax_removal_rate": (round(tax_removal_rate, 4) if tax_removal_rate is not None else None),
            "total_tax_entries": total_tax_entries,
            "removed_tax_entries": removed_tax_entries,
            "max_week_pnl_share": (round(max_week_share, 4) if max_week_share is not None else None),
            "sub_window_stable": sub_window_stable,
        },
        "gates": gates,
        "verdict": verdict,
    }


# ------------------------------------------------------------------------------------------
# 5. run() / main()
# ------------------------------------------------------------------------------------------
def run(*, dry_run: bool = False) -> dict:
    t0 = time.time()
    today = _today_et()
    doc, regenerated = _load_labels(today)
    sessions = doc["sessions"]
    labeled = [_row_from_session(s) for s in sessions if s["label"] in ("paying", "tax")]
    folds = _lowo_folds(labeled)

    candidates = []
    for feat in ALL_FEATURES:
        c = _evaluate_candidate("single_split", feat, labeled, folds)
        c.update({"candidate_id": f"single_split__{feat}", "type": "single_split", "feature": feat})
        candidates.append(c)

    c_tree = _evaluate_candidate("tree", ALL_FEATURES, labeled, folds)
    c_tree.update({"candidate_id": "tree_depth2__all_features", "type": "decision_tree_depth2",
                    "features": ALL_FEATURES})
    candidates.append(c_tree)

    shippable = [c for c in candidates if c["verdict"] == "SHADOW_CANDIDATE"]
    if shippable:
        best = max(shippable, key=lambda c: (c["oos"]["ci_lower_2.5"] if c["oos"]["ci_lower_2.5"] is not None else -1e9))
        overall_verdict, best_id = "SHADOW_CANDIDATE", best["candidate_id"]
    else:
        ranked = sorted(
            candidates,
            key=lambda c: (c["WF"], c["oos"]["ci_lower_2.5"] if c["oos"]["ci_lower_2.5"] is not None else -1e9),
            reverse=True,
        )
        overall_verdict = "NOT_SHIPPABLE"
        best_id = ranked[0]["candidate_id"] if ranked else None

    out = {
        "_meta": {
            "prereg": PREREG_REL,
            "generated_at_et": None,  # filled below (needs et_now, avoid double-import cost)
            "today_session_et": today,
            "labels_source": "analysis/recommendations/day-type-labels.json",
            "labels_regenerated_this_run": regenerated,
            "n_sessions_total": len(sessions),
            "n_labeled_paying_tax": len(labeled),
            "label_summary": doc["label_summary"],
            "n_weeks": len(folds),
            "features_considered": ALL_FEATURES,
            "features_excluded": FEATURES_EXCLUDED,
            "missing_feature_policy": "a session missing the candidate's required feature "
                                       "value at predict time is always predicted 'trade' "
                                       "(never auto-stand-down on data the classifier never "
                                       "saw)",
            "n_boot": go_live_gate.N_BOOT,
            "build_wall_seconds": None,  # filled below
        },
        "candidates": candidates,
        "decision_rule_applied": DECISION_RULE,
        "best_candidate_id": best_id,
        "verdict": overall_verdict,
        "caveat": (
            f"n={len(sessions)} total sessions / n={len(labeled)} labeled paying+tax across "
            f"{len(folds)} ISO-week LOWO folds (average {round(len(labeled)/max(len(folds),1), 1)} "
            "labeled sessions per fold) is a THIN sample for any classifier claim. Every "
            "number in this file is exploratory (Kitchen free-swarm output), not "
            "confirmatory -- per prereg section 6, clearing the ship gate is permission to "
            "build a forward SHADOW clock (a distinct future build), never permission to "
            "ship live, and the forward clock itself needs >=20 forward sessions before any "
            "ship-consideration read."
        ),
    }
    from et_clock import et_now  # noqa: PLC0415
    out["_meta"]["generated_at_et"] = et_now().isoformat()
    out["_meta"]["build_wall_seconds"] = round(time.time() - t0, 3)

    if not dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        _output_path(today).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hours", type=float, default=0.1,
                    help="accepted for kitchen_daemon GRINDER_REGISTRY/_run_grinder_task "
                         "compatibility -- unused (no parameter sweep to time-box)")
    p.add_argument("--workers", type=int, default=1,
                    help="accepted for harness compatibility -- unused (single-threaded fit)")
    p.add_argument("--dry-run", action="store_true",
                    help="compute everything but skip the write (testing only)")
    args = p.parse_args(argv)

    out = run(dry_run=args.dry_run)
    m = out["_meta"]
    print(f"day_type_classifier_grinder: verdict={out['verdict']} best={out['best_candidate_id']} "
          f"n_candidates={len(out['candidates'])} n_labeled={m['n_labeled_paying_tax']} "
          f"n_weeks={m['n_weeks']} labels_regenerated={m['labels_regenerated_this_run']} "
          f"wall_seconds={m['build_wall_seconds']}")
    for c in out["candidates"]:
        print(f"  {c['candidate_id']:42s} WF={c['WF']:.2f} "
              f"ci_lower={c['oos']['ci_lower_2.5']!s:>8} "
              f"tax_removal={c['oos']['tax_removal_rate']!s:>6} verdict={c['verdict']}")
    if not args.dry_run:
        print(f"wrote {_output_path(m['today_session_et']).relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
