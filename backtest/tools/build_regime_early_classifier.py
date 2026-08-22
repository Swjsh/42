"""build_regime_early_classifier.py -- FEASIBILITY GATE for a live-executable regime
stand-down (REGIME-EARLY-CLASSIFIER-2026-08-02).

THE QUESTION: analysis/regime-library/day-archetypes.json labels every day's archetype from
the FULL session's OHLC -- hindsight, by its own README's admission. To gate live
participation ("skip entries on days that look like pin-day/gap-fade") the archetype must be
guessable EARLY, from data available by ~09:45-10:00 ET. This script builds that early
classifier, evaluates it HONESTLY (walk-forward, never trained on a day it is then scored
against), and reports a confusion matrix against the ground-truth labels -- brutally, per the
task brief: "if gap-go cannot be identified early with useful precision, SAY SO."

TWO CLASSIFIERS, deliberately not conflated:
  1. EIGHT-WAY  -- the full archetype taxonomy, DecisionTreeClassifier(class_weight=
     "balanced"). This is the literal ask ("how accurately can you predict the full-day
     archetype... report a confusion matrix"), and it is expected to be HARD: several
     archetypes (trend-up/down, V-reversal, inverted-V) are DEFINED by where the close lands
     relative to the FULL day's eventual range -- a quantity that is definitionally not
     knowable at 09:45. Reported in full regardless of how it lands (C7 -- no silent papering).
  2. STANDDOWN-DIRECT -- a separate binary tree trained specifically on
     y = archetype in {pin-day, gap-fade} (the task's named reliably-losing set). This is the
     operationally-relevant question for ARM_1 and is expected to be an easier, better-posed
     problem than the full 8-way split (it doesn't need to distinguish trend-up from
     V-reversal, only "reliably-losing" from "not"). Both are reported; ARM_1 (if the study
     proceeds) uses classifier #2's out-of-fold prediction, disclosed explicitly.

HONESTY DISCIPLINE (this is the part that makes the accuracy number trustworthy, not just
optimistic): every reported metric comes from OUT-OF-FOLD predictions under an EXPANDING-
WINDOW walk-forward split (sklearn.model_selection.TimeSeriesSplit over the chronologically-
sorted population, never shuffled) -- a day's own outcome NEVER appears in the training fold
used to predict it. This catches two distinct leakage risks: (a) SAME-DAY lookahead (bars
after the cutoff -- guarded structurally, see lib/regime_early_features.py + its test file),
and (b) ACROSS-DAY lookahead (fitting one set of thresholds on the WHOLE population, including
the very days being scored -- a real form of hindsight bias this task's brief does not name
explicitly but which the C6 "no lookahead" discipline covers in spirit: a threshold chosen by
peeking at a day's own outcome is exactly as invalid as a threshold chosen by peeking at that
day's own afternoon bars). The unavoidable cost: the first ~1/6 of the population (the
walk-forward "seed" window) is used only for training, never scored -- a smaller, honestly
disclosed test population, not a padded one.

NO NEW sklearn DEPENDENCY RISK: pip-installed into backtest/.venv this session (free, local,
OSS, same category as the already-installed pandas/scipy/numpy -- not a new paid vendor/API).
Chosen over a hand-rolled tree to minimize implementation-bug surface on a decision that
carries real money if it ships; DecisionTreeClassifier's split logic is well-tested elsewhere,
this file's own job is the FEATURE ENGINEERING (lookahead-safety) and the EVALUATION PROTOCOL
(walk-forward honesty), not reinventing CART.

Run: backtest/.venv/Scripts/python.exe backtest/tools/build_regime_early_classifier.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score, balanced_accuracy_score, confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import TimeSeriesSplit  # noqa: E402
from sklearn.tree import DecisionTreeClassifier, export_text  # noqa: E402

import build_day_archetypes as bda  # noqa: E402
from lib.regime_slice import ARCHETYPES, DATA_INCOMPLETE, load_library  # noqa: E402
from lib.regime_early_features import CUTOFFS, bars_through_cutoff, early_features  # noqa: E402

OUT_JSON = REPO / "analysis" / "regime-library" / "early-classifier-2026-08-02.json"

EVIDENCE_FLOOR_N = 15                    # matches engine_fullhist_replay.py's OP-11 convention
N_WF_SPLITS = 5
VIX_MA_SHORT = 5
VIX_MA_LONG = 20
STANDDOWN_ARCHETYPES = ("pin-day", "gap-fade")   # task's named reliably-losing set
LEANIN_ARCHETYPE = "gap-go"
RANDOM_STATE = 42
TREE_KW = dict(max_depth=4, min_samples_leaf=10, class_weight="balanced",
               random_state=RANDOM_STATE)


def log(msg: str) -> None:
    print(f"[early-classifier] {msg}", flush=True)


# ---------------------------------------------------------------------------
# dataset construction (pure-ish: file I/O in load_sessions/load_library, no clock)
# ---------------------------------------------------------------------------

def _context_row(library_days: dict, dates_iso: list[str], i: int) -> dict | None:
    """Prior-day + known-at-open context for population index i. Every field is either a
    calendar fact (dow), already a PRIOR-days-only rolling stat inside day-archetypes.json
    itself (atr14_prior_pct explicitly excludes today -- see build_day_archetypes.build_days),
    or today's own vix_open (an early-session read, same timing class as the SPY early bars;
    vix_CLOSE is never referenced anywhere in this module). Returns None for population index
    0 (no prior day to read) -- the caller drops that row."""
    if i == 0:
        return None
    d = dates_iso[i]
    rec = library_days[d]
    prior_rec = library_days[dates_iso[i - 1]]
    return {
        "date": d, "dow": rec["dow"], "atr14_prior_pct": rec.get("atr14_prior_pct"),
        "vix_open": rec.get("vix_open"), "prior_archetype": prior_rec["archetype"],
        "prior_close": rec.get("prior_close"),
    }


def _vix_rolling_ma(library_days: dict, dates_iso: list[str]) -> dict[str, dict]:
    """{date: {vix_5d_ma_prior, vix_20d_ma_prior, vix_declining_prior}} -- rolling means of
    vix_open over the N days STRICTLY BEFORE date (.shift(1) excludes today from its own
    average). min_periods=1 so the earliest days get a shorter-window value instead of being
    dropped (those days are deep in the walk-forward seed region regardless -- never scored)."""
    s = pd.Series({d: library_days[d].get("vix_open") for d in dates_iso}, dtype=float)
    ma5 = s.shift(1).rolling(VIX_MA_SHORT, min_periods=1).mean()
    ma20 = s.shift(1).rolling(VIX_MA_LONG, min_periods=1).mean()
    out = {}
    for d in dates_iso:
        v5, v20 = ma5.get(d), ma20.get(d)
        out[d] = {
            "vix_5d_ma_prior": None if pd.isna(v5) else round(float(v5), 4),
            "vix_20d_ma_prior": None if pd.isna(v20) else round(float(v20), 4),
            "vix_declining_prior": (bool(v5 < v20) if pd.notna(v5) and pd.notna(v20) else None),
        }
    return out


def build_dataset(cutoff_name: str = "09:45"):
    """Returns (X: pd.DataFrame [one-hot encoded, float], y: np.ndarray[str] archetype labels,
    dates: list[str] chronological, parallel to X/y -- NEVER shuffled, the walk-forward split
    depends on this order -- meta: dict of scoping counts). Population: every day-
    archetypes.json day with session != data-incomplete, early bars sufficient by the cutoff,
    AND a prior day available."""
    spy_days, _vix_days, _inputs = bda.load_sessions()
    lib = load_library()["days"]

    # INTERSECT the two sources (fixed 2026-08-21). `spy_days` comes from the bar feed and
    # `lib` from the regime library, and they refresh on DIFFERENT schedules -- bars land
    # ~14:16 MT, the library later. Between those two moments the newest session exists in
    # one source and not the other, and `_vix_rolling_ma`'s `library_days[d]` died with a
    # bare KeyError on that date every single day in that window.
    #
    # A day needs BOTH a session and a library record to be scoreable, which is already this
    # builder's stated population rule ("every day-archetypes.json day with session !=
    # data-incomplete ... AND a prior day available"). Dropping the unscoreable tail is
    # therefore the rule, not a workaround -- but it is DISCLOSED in meta rather than done
    # in silence, so a library that stops refreshing shows up as a growing number instead of
    # looking like a quiet success.
    _all_sorted = sorted(spy_days.keys())
    dates_sorted = [d for d in _all_sorted if d.isoformat() in lib]
    n_no_library = len(_all_sorted) - len(dates_sorted)
    if not dates_sorted:
        raise RuntimeError(
            "no session date has a regime-library record -- the library is empty or its "
            "date keys changed shape; refusing to build a classifier on nothing")
    dates_iso = [d.isoformat() for d in dates_sorted]
    vix_ctx = _vix_rolling_ma(lib, dates_iso)

    cutoff = CUTOFFS[cutoff_name]
    rows, labels, used_dates = [], [], []
    n_incomplete = n_insufficient = 0
    for i, d in enumerate(dates_sorted):
        diso = dates_iso[i]
        rec = lib.get(diso)
        if rec is None or rec["archetype"] == DATA_INCOMPLETE:
            n_incomplete += 1
            continue
        ctx = _context_row(lib, dates_iso, i)
        if ctx is None:
            continue
        early_bars = bars_through_cutoff(spy_days[d], cutoff)
        feats = early_features(early_bars, rec.get("prior_close"))
        if feats.get("insufficient"):
            n_insufficient += 1
            continue
        vx = vix_ctx[diso]
        rows.append({
            "gap_pct": feats["gap_pct"] if feats["gap_pct"] is not None else 0.0,
            "gap_dir": feats["gap_dir"],
            "gap_filled_by_cutoff": int(bool(feats["gap_filled_by_cutoff"])),
            "early_range_pct": feats["early_range_pct"],
            "early_body_pct": feats["early_body_pct"],
            "early_close_loc": feats["early_close_loc"],
            "early_open_loc": feats["early_open_loc"],
            "atr14_prior_pct": ctx["atr14_prior_pct"] if ctx["atr14_prior_pct"] is not None else 0.0,
            "vix_open": ctx["vix_open"] if ctx["vix_open"] is not None else 0.0,
            "vix_5d_ma_prior": vx["vix_5d_ma_prior"] or 0.0,
            "vix_20d_ma_prior": vx["vix_20d_ma_prior"] or 0.0,
            "vix_declining_prior": int(bool(vx["vix_declining_prior"])),
            "dow": ctx["dow"],
            "prior_archetype": ctx["prior_archetype"],
        })
        labels.append(rec["archetype"])
        used_dates.append(diso)

    df = pd.DataFrame(rows)
    df = pd.get_dummies(df, columns=["dow", "prior_archetype"],
                         prefix=["dow", "prior_arch"]).astype(float)
    y = np.array(labels)
    meta = {
        "cutoff": cutoff_name, "n_total_days_seen": len(dates_sorted),
        "n_data_incomplete_excluded": n_incomplete,
        "n_insufficient_early_bars_excluded": n_insufficient,
        "n_no_prior_day_excluded": 1, "n_usable": len(df),
        # Sessions the bar feed has but the regime library does not (see the intersect
        # above). Normally 0 or 1 -- 1 is the ordinary same-day gap between the ~14:16 MT
        # bar drop and the later library refresh. A number that keeps climbing means the
        # library producer has stalled, which would otherwise be invisible here.
        "n_no_library_record_excluded": n_no_library,
        "date_range": [used_dates[0], used_dates[-1]] if used_dates else None,
        "feature_columns": list(df.columns),
    }
    return df, y, used_dates, meta


def walk_forward_splits(n_samples: int, n_splits: int = N_WF_SPLITS):
    """Expanding-window (train=everything chronologically before, test=next block) splits.
    build_dataset() output is never shuffled, so TimeSeriesSplit over a plain index range IS
    a chronological walk-forward split. Yields (train_idx, test_idx) positional-index arrays."""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    for train_idx, test_idx in tscv.split(np.arange(n_samples)):
        yield train_idx, test_idx


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def _baseline_majority(y_train: np.ndarray, n_test: int) -> np.ndarray:
    vals, counts = np.unique(y_train, return_counts=True)
    majority = vals[np.argmax(counts)]
    return np.full(n_test, majority)


def evaluate_cutoff(cutoff_name: str) -> dict:
    t0 = time.time()
    X, y, dates, meta = build_dataset(cutoff_name)
    n = len(X)
    prior_arch_col_vals = None
    # recover the raw prior_archetype string per row (needed for the persistence baseline;
    # get_dummies already one-hot'd it, so re-derive from the dummy columns).
    prior_cols = [c for c in X.columns if c.startswith("prior_arch_")]
    prior_arch_series = X[prior_cols].idxmax(axis=1).str.replace("prior_arch_", "", regex=False)

    folds = list(walk_forward_splits(n, N_WF_SPLITS))
    fold_sizes = [{"train_n": len(tr), "test_n": len(te),
                    "test_date_range": [dates[te[0]], dates[te[-1]]]} for tr, te in folds]
    tested_idx = sorted({i for _, te in folds for i in te})
    log(f"  [{cutoff_name}] n_usable={n} n_folds={len(folds)} "
        f"n_tested={len(tested_idx)} (seed-only, never scored: {n - len(tested_idx)})")

    oof_8way = {}
    oof_bin_direct = {}
    oof_majority = {}
    last_clf8, last_clf_bin = None, None
    for train_idx, test_idx in folds:
        Xtr, Xte = X.iloc[train_idx], X.iloc[test_idx]
        ytr = y[train_idx]

        clf8 = DecisionTreeClassifier(**TREE_KW)
        clf8.fit(Xtr, ytr)
        pred8 = clf8.predict(Xte)
        last_clf8 = clf8

        y_bin_tr = np.isin(ytr, STANDDOWN_ARCHETYPES)
        clf_bin = DecisionTreeClassifier(**TREE_KW)
        clf_bin.fit(Xtr, y_bin_tr)
        pred_bin = clf_bin.predict(Xte)
        last_clf_bin = clf_bin

        maj = _baseline_majority(ytr, len(test_idx))

        for j, idx in enumerate(test_idx):
            oof_8way[idx] = pred8[j]
            oof_bin_direct[idx] = bool(pred_bin[j])
            oof_majority[idx] = maj[j]

    tested_idx = sorted(oof_8way.keys())
    y_true = y[tested_idx]
    dates_tested = [dates[i] for i in tested_idx]
    pred8 = np.array([oof_8way[i] for i in tested_idx])
    pred_maj = np.array([oof_majority[i] for i in tested_idx])
    pred_persist = prior_arch_series.iloc[tested_idx].to_numpy()
    pred_bin_direct = np.array([oof_bin_direct[i] for i in tested_idx])
    pred_bin_derived8 = np.isin(pred8, STANDDOWN_ARCHETYPES)
    y_bin_true = np.isin(y_true, STANDDOWN_ARCHETYPES)
    pred_leanin_derived8 = pred8 == LEANIN_ARCHETYPE
    y_leanin_true = y_true == LEANIN_ARCHETYPE
    pred_bin_persist = np.isin(pred_persist, STANDDOWN_ARCHETYPES)
    pred_bin_majority = np.isin(pred_maj, STANDDOWN_ARCHETYPES)

    labels_present = sorted(set(y_true) | set(pred8))
    cm = confusion_matrix(y_true, pred8, labels=labels_present)
    support = {lab: int((y_true == lab).sum()) for lab in labels_present}

    def _bin_metrics(y_t, y_p, base_rate_of=None):
        p, r, f1, sup = precision_recall_fscore_support(
            y_t, y_p, average="binary", zero_division=0)
        base_rate = float(np.mean(y_t)) if base_rate_of is None else base_rate_of
        return {"precision": round(float(p), 4), "recall": round(float(r), 4),
                "f1": round(float(f1), 4), "n_predicted_positive": int(y_p.sum()),
                "n_true_positive_in_test_set": int(y_t.sum()), "n_test": int(len(y_t)),
                "base_rate": round(base_rate, 4)}

    out = {
        "cutoff": cutoff_name,
        "meta": meta,
        "walk_forward": {"n_splits": N_WF_SPLITS, "folds": fold_sizes,
                           "n_tested_total": len(tested_idx),
                           "tested_date_range": [dates_tested[0], dates_tested[-1]]},
        "eightway": {
            "labels": labels_present,
            "confusion_matrix": cm.tolist(),
            "support_per_class_in_test": support,
            "underpowered_classes_n_lt_15": [lab for lab, n in support.items()
                                              if n < EVIDENCE_FLOOR_N],
            "accuracy": round(float(accuracy_score(y_true, pred8)), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y_true, pred8)), 4),
            "baseline_majority_accuracy": round(float(accuracy_score(y_true, pred_maj)), 4),
            "baseline_persistence_accuracy": round(float(accuracy_score(y_true, pred_persist)), 4),
            "feature_importances": {c: round(float(w), 4) for c, w in
                                     sorted(zip(X.columns, last_clf8.feature_importances_),
                                            key=lambda kv: -kv[1]) if w > 0},
        },
        "binary_standdown_pin_gapfade": {
            "direct_classifier": _bin_metrics(y_bin_true, pred_bin_direct),
            "derived_from_eightway": _bin_metrics(y_bin_true, pred_bin_derived8),
            "baseline_persistence": _bin_metrics(y_bin_true, pred_bin_persist),
            "baseline_majority": _bin_metrics(y_bin_true, pred_bin_majority),
            "feature_importances_direct": {c: round(float(w), 4) for c, w in
                                            sorted(zip(X.columns, last_clf_bin.feature_importances_),
                                                   key=lambda kv: -kv[1]) if w > 0},
            "tree_rules_direct_text": export_text(last_clf_bin, feature_names=list(X.columns),
                                                    max_depth=4),
        },
        "binary_leanin_gap_go_DESCRIPTIVE_ONLY": {
            "derived_from_eightway": _bin_metrics(y_leanin_true, pred_leanin_derived8),
            "note": "NOT a ship gate this session (sizing/lean-in changes are out of scope "
                     "per the task brief's ARM_3 note) -- reported for completeness only.",
        },
        # per-day out-of-fold predictions, needed downstream by the ARM study to build ARM_1's
        # skip-set WITHOUT re-fitting anything (avoids re-deriving a second, possibly-drifted
        # walk-forward run for the P&L study).
        "oof_predictions_by_date": {
            dates_tested[j]: {
                "true_archetype": y_true[j], "pred_8way": pred8[j],
                "pred_standdown_direct": bool(pred_bin_direct[j]),
                "pred_standdown_derived8": bool(pred_bin_derived8[j]),
                "pred_leanin_gapgo_derived8": bool(pred_leanin_derived8[j]),
            } for j in range(len(tested_idx))
        },
        "runtime_seconds": round(time.time() - t0, 2),
    }
    return out


def main() -> int:
    log("building + evaluating early classifiers at both cutoffs (walk-forward, honest OOF)")
    per_cutoff = {}
    for cutoff_name in CUTOFFS:
        per_cutoff[cutoff_name] = evaluate_cutoff(cutoff_name)
        e = per_cutoff[cutoff_name]["eightway"]
        b = per_cutoff[cutoff_name]["binary_standdown_pin_gapfade"]["direct_classifier"]
        log(f"  [{cutoff_name}] 8way acc={e['accuracy']} bal_acc={e['balanced_accuracy']} "
            f"(majority_baseline={e['baseline_majority_accuracy']} "
            f"persistence_baseline={e['baseline_persistence_accuracy']}) | "
            f"standdown-direct P={b['precision']} R={b['recall']} F1={b['f1']} "
            f"base_rate={b['base_rate']}")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "standdown_archetypes": list(STANDDOWN_ARCHETYPES),
        "leanin_archetype": LEANIN_ARCHETYPE,
        "evidence_floor_n": EVIDENCE_FLOOR_N,
        "tree_params": TREE_KW,
        "per_cutoff": per_cutoff,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
