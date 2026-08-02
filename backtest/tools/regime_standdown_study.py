"""regime_standdown_study.py -- executes prereg-regime-standdown-2026-08-02.json
(REGIME-STANDDOWN-EARLY-CLASSIFIER-2026-08-02, 2026-08-02).

Created AFTER the prereg was committed (60e1dcc8) -- git-provable freeze order, no
exceptions, per the task brief. Does NOT re-simulate anything: pure post-hoc filtering of
the already-real-fills, already-real-exit-walked engine-fullhist-replay-2026-07-23.json
trade log against the already-committed, already-frozen early classifier's out-of-fold
predictions (early-classifier-2026-08-02.json, commit 76857479). Zero new entry/exit logic,
zero new simulation -- if this script disagrees with THE FINDING's own numbers on the
CONTROL arm, that is a bug in this script, not a second measurement of the engine.

Arms (frozen in the prereg, reproduced here verbatim, not re-derived):
    ARM_2_CONTROL         -- unmodified in-scope trade population
    ARM_1_STANDDOWN_10AM  -- CONTROL minus trades on days classifier[10:00].pred_standdown_direct==True (PRIMARY)
    ARM_1B_STANDDOWN_0945 -- CONTROL minus trades on days classifier[09:45].pred_standdown_direct==True (secondary)

Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_standdown_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scipy import stats  # noqa: E402

from lib.regime_slice import load_library  # noqa: E402

TRADES_JSON = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
CLASSIFIER_JSON = REPO / "analysis" / "regime-library" / "early-classifier-2026-08-02.json"
LIBRARY_JSON = REPO / "analysis" / "regime-library" / "day-archetypes.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "regime-standdown-2026-08-02.json"
OUT_MD = REPO / "analysis" / "recommendations" / "regime-standdown-2026-08-02.md"

RECENT_N = 25
RUNNER_PREFIX = "runner_stop"          # exact-matched to the task brief's cited 35/+$15,774.05
G4_RUNNER_FLOOR_PCT = 0.95
G5_MIN_REMOVED_TRADES = 5
BH_ALPHA = 0.10


def log(msg: str) -> None:
    print(f"[regime-standdown-study] {msg}", flush=True)


def bh_fdr(pvals: list[float], q: float = BH_ALPHA) -> list[bool]:
    """Standard Benjamini-Hochberg; reject-null mask aligned to input order. Independently
    reimplemented (not imported) from backtest/autoresearch/dynamic_stop_ab.py's bh_fdr() --
    same well-known procedure, kept local to avoid dragging that script's unrelated
    module-level state into this runner (per this prereg's own no_new_knobs disclosure)."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    reject = [False] * m
    thresh_k = -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            thresh_k = rank
    for rank, i in enumerate(order, start=1):
        if rank <= thresh_k:
            reject[i] = True
    return reject


def one_sided_mean_below_zero_pvalue(vals: list[float]) -> float | None:
    """One-sample t-test, H0: mean==0, one-sided alternative mean<0 (i.e. 'these removed
    trades were, on net, real losers'). None if n<2 (t-test undefined)."""
    if len(vals) < 2:
        return None
    t_stat, p_two_sided = stats.ttest_1samp(vals, popmean=0.0)
    if t_stat < 0:
        return float(p_two_sided / 2.0)
    return float(1.0 - p_two_sided / 2.0)


def load_inputs():
    trades_doc = json.loads(TRADES_JSON.read_text(encoding="utf-8"))
    trades = trades_doc["trades"]
    classifier_doc = json.loads(CLASSIFIER_JSON.read_text(encoding="utf-8"))
    lib = load_library(LIBRARY_JSON)["days"]
    return trades, classifier_doc, lib


def build_scope(trades: list[dict], oof_09: dict, oof_10: dict) -> tuple[list[dict], list[dict], list[str]]:
    """Split CONTROL trades into (in_scope, excluded_no_oof, excluded_dates). A trade is
    in-scope only if its date has an honest out-of-fold prediction at BOTH cutoffs (keeps
    ARM_1 and ARM_1B's CONTROL population byte-identical, so the two arms are directly
    comparable on the same base)."""
    in_scope, excluded = [], []
    for t in trades:
        if t["date"] in oof_09 and t["date"] in oof_10:
            in_scope.append(t)
        else:
            excluded.append(t)
    excluded_dates = sorted({t["date"] for t in excluded})
    return in_scope, excluded, excluded_dates


def recent_n_dates(all_dates: list[str], n: int = RECENT_N) -> list[str]:
    return sorted(set(all_dates))[-n:] if n else sorted(set(all_dates))


def day_sums(trades: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in trades:
        out[t["date"]] = round(out.get(t["date"], 0.0) + t["dollar_pnl"], 2)
    return out


def runner_cohort(trades: list[dict]) -> tuple[int, float]:
    r = [t for t in trades if str(t.get("exit_reason", "")).startswith(RUNNER_PREFIX)]
    return len(r), round(sum(t["dollar_pnl"] for t in r), 2)


def archetype_of_date(lib: dict, date: str) -> str:
    rec = lib.get(date)
    return rec["archetype"] if rec else "UNTAGGED"


def evaluate_arm(control: list[dict], oof: dict, lib: dict, arm_name: str) -> dict:
    removed = [t for t in control if oof[t["date"]]["pred_standdown_direct"]]
    kept = [t for t in control if not oof[t["date"]]["pred_standdown_direct"]]
    removed_dates = sorted({t["date"] for t in removed})

    control_total = round(sum(t["dollar_pnl"] for t in control), 2)
    kept_total = round(sum(t["dollar_pnl"] for t in kept), 2)
    removed_total = round(sum(t["dollar_pnl"] for t in removed), 2)
    assert round(control_total - removed_total, 2) == kept_total, "arithmetic drift: kept != control-removed"

    # --- recent-25-day window (calendar/session convention, per prereg) ---
    all_dates = sorted({t["date"] for t in control})
    recent = set(recent_n_dates(all_dates, RECENT_N))
    control_recent = [t for t in control if t["date"] in recent]
    removed_recent = [t for t in removed if t["date"] in recent]
    control_recent_total = round(sum(t["dollar_pnl"] for t in control_recent), 2)
    removed_recent_total = round(sum(t["dollar_pnl"] for t in removed_recent), 2)
    kept_recent_total = round(control_recent_total - removed_recent_total, 2)
    delta_recent = round(kept_recent_total - control_recent_total, 2)   # == -removed_recent_total

    # --- G2 day-majority (recent window, days with >=1 removed trade) ---
    control_day_sums_recent = day_sums(control_recent)
    removed_day_sums_recent = day_sums(removed_recent)
    n_improved = sum(1 for d, v in removed_day_sums_recent.items() if v < 0)   # removing a net-loss day helps
    n_worsened = sum(1 for d, v in removed_day_sums_recent.items() if v > 0)   # removing a net-win day hurts
    n_neutral_changed_days = sum(1 for d, v in removed_day_sums_recent.items() if v == 0)

    # --- G3: recent delta minus the single worst-dodged (most negative removed) trade ---
    worst_removed_recent = min((t["dollar_pnl"] for t in removed_recent), default=0.0)
    delta_recent_minus_worst_dodge = round(delta_recent - (-worst_removed_recent), 2)
    # delta_recent = -(removed_recent_total); its "best contribution" is the single most
    # negative removed trade (biggest loser dodged) -- subtract that one trade's dodge-value.

    # --- G4 runner-cohort, full in-scope population, zero tolerance ---
    n_runner_control, total_runner_control = runner_cohort(control)
    n_runner_kept, total_runner_kept = runner_cohort(kept)
    runner_count_pct = (n_runner_kept / n_runner_control) if n_runner_control else 1.0
    runner_total_pct = (total_runner_kept / total_runner_control) if total_runner_control else 1.0
    n_runner_removed = n_runner_control - n_runner_kept
    total_runner_removed = round(total_runner_control - total_runner_kept, 2)

    # --- full-population drop-best-day (mirrors THE FINDING's own convention) ---
    kept_day_sums = day_sums(kept)
    control_day_sums_full = day_sums(control)
    if kept_day_sums:
        best_kept_day, best_kept_val = max(kept_day_sums.items(), key=lambda kv: kv[1])
        drop_best_day_kept_total = round(kept_total - best_kept_val, 2)
    else:
        best_kept_day, best_kept_val, drop_best_day_kept_total = None, 0.0, kept_total

    # --- removed-trade archetype breakdown (the load-bearing descriptive number) ---
    removed_by_archetype: dict[str, dict] = {}
    for t in removed:
        arch = archetype_of_date(lib, t["date"])
        b = removed_by_archetype.setdefault(arch, {"n_trades": 0, "total_pnl": 0.0, "dates": set()})
        b["n_trades"] += 1
        b["total_pnl"] += t["dollar_pnl"]
        b["dates"].add(t["date"])
    for arch, b in removed_by_archetype.items():
        b["total_pnl"] = round(b["total_pnl"], 2)
        b["n_days"] = len(b["dates"])
        del b["dates"]

    gapgo_removed = removed_by_archetype.get("gap-go", {"n_trades": 0, "total_pnl": 0.0, "n_days": 0})
    pin_gapfade_removed_n = (removed_by_archetype.get("pin-day", {}).get("n_trades", 0)
                              + removed_by_archetype.get("gap-fade", {}).get("n_trades", 0))
    pin_gapfade_removed_total = round(removed_by_archetype.get("pin-day", {}).get("total_pnl", 0.0)
                                       + removed_by_archetype.get("gap-fade", {}).get("total_pnl", 0.0), 2)

    p_removed_negative = one_sided_mean_below_zero_pvalue([t["dollar_pnl"] for t in removed])

    gates = {
        "G1_recent_window_positive": {"pass": delta_recent > 0, "value": delta_recent},
        "G2_day_majority_recent": {"pass": n_improved > n_worsened,
                                     "n_improved": n_improved, "n_worsened": n_worsened,
                                     "n_neutral": n_neutral_changed_days},
        "G3_survives_worst_single_dodge_recent": {"pass": delta_recent_minus_worst_dodge > 0,
                                                     "value": delta_recent_minus_worst_dodge,
                                                     "worst_single_removed_trade_recent": round(worst_removed_recent, 2)},
        "G4_runner_anchor_no_regression": {
            "pass": (runner_count_pct >= G4_RUNNER_FLOOR_PCT and runner_total_pct >= G4_RUNNER_FLOOR_PCT),
            "runner_count_control": n_runner_control, "runner_count_kept": n_runner_kept,
            "runner_count_pct_of_control": round(runner_count_pct, 4),
            "runner_total_control": total_runner_control, "runner_total_kept": total_runner_kept,
            "runner_total_pct_of_control": round(runner_total_pct, 4),
            "n_runner_trades_removed": n_runner_removed, "total_runner_pnl_removed": total_runner_removed,
        },
        "G5_meaningful_participation_change": {"pass": len(removed) >= G5_MIN_REMOVED_TRADES,
                                                  "n_removed_trades": len(removed),
                                                  "n_removed_days": len(removed_dates)},
    }
    ships = all(g["pass"] for g in gates.values())

    return {
        "arm": arm_name,
        "n_control_trades": len(control), "n_kept_trades": len(kept), "n_removed_trades": len(removed),
        "n_removed_days": len(removed_dates), "removed_dates": removed_dates,
        "control_total_pnl": control_total, "kept_total_pnl": kept_total, "removed_total_pnl": removed_total,
        "full_population_delta": round(kept_total - control_total, 2),
        "drop_best_day_full_population": {
            "best_kept_day": best_kept_day, "best_kept_day_pnl": best_kept_val,
            "kept_total_minus_best_day": drop_best_day_kept_total,
            "still_positive_after_drop_best": drop_best_day_kept_total > 0 if kept_day_sums else None,
        },
        "recent_window": {
            "window_dates": [min(recent), max(recent)] if recent else None,
            "control_total": control_recent_total, "kept_total": kept_recent_total,
            "removed_total": removed_recent_total, "delta": delta_recent,
        },
        "removed_by_true_archetype": removed_by_archetype,
        "gap_go_removed": gapgo_removed,
        "pin_gapfade_removed": {"n_trades": pin_gapfade_removed_n, "total_pnl": pin_gapfade_removed_total,
                                  "note": "the archetypes this arm was SUPPOSED to catch"},
        "removed_trades_one_sided_pvalue_mean_below_zero": (round(p_removed_negative, 4)
                                                              if p_removed_negative is not None else None),
        "gates": gates,
        "ships": ships,
    }


def main() -> int:
    log("loading trades + classifier oof predictions + regime library")
    trades, classifier_doc, lib = load_inputs()
    oof_09 = classifier_doc["per_cutoff"]["09:45"]["oof_predictions_by_date"]
    oof_10 = classifier_doc["per_cutoff"]["10:00"]["oof_predictions_by_date"]

    in_scope, excluded, excluded_dates = build_scope(trades, oof_09, oof_10)
    log(f"  in-scope trades: {len(in_scope)} of {len(trades)} "
        f"(excluded, no honest OOF pred: {len(excluded)} trades / {len(excluded_dates)} dates)")

    arm_10 = evaluate_arm(in_scope, oof_10, lib, "ARM_1_STANDDOWN_10AM")
    arm_09 = evaluate_arm(in_scope, oof_09, lib, "ARM_1B_STANDDOWN_0945")

    pvals = [a["removed_trades_one_sided_pvalue_mean_below_zero"] for a in (arm_10, arm_09)
             if a["removed_trades_one_sided_pvalue_mean_below_zero"] is not None]
    labels = [a["arm"] for a in (arm_10, arm_09) if a["removed_trades_one_sided_pvalue_mean_below_zero"] is not None]
    rejects = bh_fdr(pvals, BH_ALPHA)
    bh_result = {"alpha": BH_ALPHA, "n_cells": len(pvals),
                 "survivors": [labels[i] for i, r in enumerate(rejects) if r]}

    any_ships = arm_10["ships"] or arm_09["ships"]
    verdict = {
        "any_arm_ships": any_ships,
        "arm_10_ships": arm_10["ships"], "arm_09_ships": arm_09["ships"],
        "conclusion": (
            "SHIPS -- see arming plan" if any_ships else
            "NOT LIVE-EXECUTABLE with the current early-classifier methodology -- "
            "confirms the prereg's stated prior. Filed as a real, dated null result."
        ),
    }

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": "analysis/recommendations/prereg-regime-standdown-2026-08-02.json (commit 60e1dcc8)",
        "sources": {
            "trades": str(TRADES_JSON.relative_to(REPO)),
            "classifier": str(CLASSIFIER_JSON.relative_to(REPO)),
            "regime_library": str(LIBRARY_JSON.relative_to(REPO)),
        },
        "scope": {
            "n_total_trades": len(trades), "n_in_scope_trades": len(in_scope),
            "n_excluded_trades": len(excluded), "n_excluded_dates": len(excluded_dates),
            "excluded_dates": excluded_dates,
            "note": "excluded = trade dates in the classifier's walk-forward SEED window "
                     "(no honest out-of-fold prediction exists) -- dropped from BOTH arms "
                     "identically, per the prereg.",
        },
        "arm_ARM_1_STANDDOWN_10AM_primary": arm_10,
        "arm_ARM_1B_STANDDOWN_0945_secondary": arm_09,
        "bh_fdr_removed_trade_means": bh_result,
        "verdict": verdict,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")

    for arm in (arm_10, arm_09):
        g = arm["gates"]
        log(f"  {arm['arm']}: ships={arm['ships']} | "
            f"G1={g['G1_recent_window_positive']['pass']}({g['G1_recent_window_positive']['value']}) "
            f"G2={g['G2_day_majority_recent']['pass']} "
            f"G3={g['G3_survives_worst_single_dodge_recent']['pass']} "
            f"G4={g['G4_runner_anchor_no_regression']['pass']}"
            f"(runner$ kept={g['G4_runner_anchor_no_regression']['runner_total_pct_of_control']*100:.1f}% of control) "
            f"G5={g['G5_meaningful_participation_change']['pass']}"
            f"(removed n={g['G5_meaningful_participation_change']['n_removed_trades']}) | "
            f"gap-go removed: n={arm['gap_go_removed']['n_trades']} ${arm['gap_go_removed']['total_pnl']:+.2f}")
    log(f"VERDICT: {verdict['conclusion']}")
    return 0


def write_markdown(out: dict) -> None:
    v = out["verdict"]
    L = [
        "# Regime stand-down study -- REGIME-STANDDOWN-EARLY-CLASSIFIER-2026-08-02",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/regime_standdown_study.py`. "
        f"Prereg: `{out['prereg']}`.",
        "",
        f"## VERDICT: {v['conclusion']}",
        "",
        f"- ARM_1 (10:00 cutoff, primary) ships: **{v['arm_10_ships']}**",
        f"- ARM_1B (09:45 cutoff, secondary) ships: **{v['arm_09_ships']}**",
        "",
        "## Scope",
        "",
        f"- {out['scope']['n_total_trades']} total trades in engine-fullhist-replay-2026-07-23.json",
        f"- {out['scope']['n_in_scope_trades']} in-scope (both cutoffs have honest out-of-fold predictions)",
        f"- {out['scope']['n_excluded_trades']} excluded ({out['scope']['n_excluded_dates']} dates, "
        "walk-forward seed window, no honest OOF prediction -- dropped from both arms identically)",
        "",
    ]
    for arm in (out["arm_ARM_1_STANDDOWN_10AM_primary"], out["arm_ARM_1B_STANDDOWN_0945_secondary"]):
        g = arm["gates"]
        L += [
            f"## {arm['arm']}",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Control total P&L (in-scope) | ${arm['control_total_pnl']:+,.2f} ({arm['n_control_trades']} trades) |",
            f"| ARM total P&L (after stand-down) | ${arm['kept_total_pnl']:+,.2f} ({arm['n_kept_trades']} trades) |",
            f"| Removed (skipped) total P&L | ${arm['removed_total_pnl']:+,.2f} ({arm['n_removed_trades']} trades, {arm['n_removed_days']} days) |",
            f"| Full-population delta | ${arm['full_population_delta']:+,.2f} |",
            f"| Drop-best-day (kept book) | ${arm['drop_best_day_full_population']['kept_total_minus_best_day']:+,.2f} (still positive: {arm['drop_best_day_full_population']['still_positive_after_drop_best']}) |",
            f"| Recent-25-day window delta | ${arm['recent_window']['delta']:+,.2f} |",
            f"| Removed-trades one-sided p (mean<0) | {arm['removed_trades_one_sided_pvalue_mean_below_zero']} |",
            "",
            "### Removed trades by TRUE archetype (hindsight label)",
            "",
            "| Archetype | N trades | N days | Total $ removed |",
            "|---|---:|---:|---:|",
        ]
        for arch, b in sorted(arm["removed_by_true_archetype"].items(), key=lambda kv: -abs(kv[1]["total_pnl"])):
            L.append(f"| {arch} | {b['n_trades']} | {b['n_days']} | ${b['total_pnl']:+,.2f} |")
        gg = arm["gap_go_removed"]
        L += [
            "",
            f"**gap-go specifically: {gg['n_trades']} trades / {gg.get('n_days', 0)} days removed, "
            f"${gg['total_pnl']:+,.2f}** -- this is the book's single largest archetype (60.5% of ALL "
            "P&L per THE FINDING); any material removal here is a direct hit on the profit engine, "
            "not a side effect.",
            "",
            "### Gates",
            "",
            "| Gate | Pass | Detail |",
            "|---|:---:|---|",
            f"| G1 recent-window positive (PRIMARY) | {g['G1_recent_window_positive']['pass']} | delta=${g['G1_recent_window_positive']['value']:+,.2f} |",
            f"| G2 day-majority | {g['G2_day_majority_recent']['pass']} | improved={g['G2_day_majority_recent']['n_improved']} worsened={g['G2_day_majority_recent']['n_worsened']} |",
            f"| G3 survives worst-single-dodge | {g['G3_survives_worst_single_dodge_recent']['pass']} | value=${g['G3_survives_worst_single_dodge_recent']['value']:+,.2f} |",
            f"| G4 runner-cohort no-regression (ZERO tolerance) | {g['G4_runner_anchor_no_regression']['pass']} | kept {g['G4_runner_anchor_no_regression']['runner_total_pct_of_control']*100:.1f}% of control $ ({g['G4_runner_anchor_no_regression']['runner_count_kept']}/{g['G4_runner_anchor_no_regression']['runner_count_control']} trades), removed ${g['G4_runner_anchor_no_regression']['total_runner_pnl_removed']:+,.2f} of runner P&L |",
            f"| G5 meaningful participation change | {g['G5_meaningful_participation_change']['pass']} | removed {g['G5_meaningful_participation_change']['n_removed_trades']} trades / {g['G5_meaningful_participation_change']['n_removed_days']} days |",
            f"| **SHIPS (all gates)** | **{arm['ships']}** | |",
            "",
        ]
    bh = out["bh_fdr_removed_trade_means"]
    L += [
        "## BH-FDR (advisory)",
        "",
        f"alpha={bh['alpha']}, n_cells={bh['n_cells']}, survivors={bh['survivors']}",
        "",
        "---",
        f"_Source: `backtest/tools/regime_standdown_study.py`. Raw JSON: "
        f"`analysis/recommendations/regime-standdown-2026-08-02.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
