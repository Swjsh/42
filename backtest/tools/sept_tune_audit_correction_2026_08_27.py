"""sept_tune_audit_correction_2026_08_27.py -- regenerates the 4 September-tune A/B
scorecards + the overlap matrix on CORRECTED data, per the AUDIT-CORRECTIONS-2026-08-27
adversarial audit.

WHAT WAS WRONG (verified fresh this session, see AUDIT-CORRECTIONS-2026-08-27.md for the
full writeup): commit 12f86c11 built vwap_family_demotion.json, premium_cost_cap_1200.json,
mixed_ribbon_gate.json, lunch_window_gate_1200_1300.json and
SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json on a "merged-bucket" round-trip basis (one row per
(date,arm,symbol), no split for same-day re-entries) that commit 26e69762 (same evening,
LATER) proved wrong and replaced -- 62/268 buckets silently merged multiple real positions
into one phantom row (cost up to $8,816 when the true max single-position cost in the
corrected ledger is $1,880). No generator script for the original 5 files was ever
committed (a C35 violation in its own right, noted in the audit doc) -- this script is the
first COMMITTED, re-runnable generator for this sweep.

BASIS: this script reads analysis/trades-enriched.jsonl, which is "flat_to_flat" (one row
per buy-to-flat-to-buy position) -- the correct basis for these 4 rules, because every rule
here is an ENTRY-time decision ("would we have taken this position at all") and flat_to_flat
is the natural per-position unit for that question (FIFO's finer P&L-accounting split would
force awkward multi-leg blocking of one entry decision). See trades_enriched.py's module
docstring BASIS section for the full 3-way reconciliation (147 refuted-merged / 210
flat_to_flat / 293 FIFO, all Augusts sum to +$1,744).

GUARDS: every cell now carries the audit's 4 required structural fields (bootstrap CI +
P(pnl<=0)/P(PF<=1.0), ex-best-day sign-flip, signal_cluster_n, BH-FDR q=0.10 across the
whole sweep) via setup/scripts/lib/scorecard_guards.py.

ANCHOR COHORT (redefined, disclosed): the original files' anchor_cohort_n=33/winners=11 has
NO recoverable definition (no committed script, no doc). This script defines it explicitly:
engine trades using setup in (BULLISH_RECLAIM_RIDE_THE_RIBBON, BEARISH_REJECTION_RIDE_THE_
RIBBON) with stop_mode=="structure" -- i.e. the CURRENT v15.3 chart-stop-primary production
strategy, the cohort FUTURE-IMPROVEMENTS.md's own SEPT-TUNE intro names as "the edge...
everything else subtracted." A rule that removes one of THIS cohort's winners is regressing
the thing that's actually working. This is a documented redefinition, not a reproduction of
the undocumented original -- the size differs (n=177 vs the original's unrecoverable n=33)
and that difference is disclosed in every regenerated file's `anchor_cohort_definition` key.

Run: backtest/.venv/Scripts/python.exe backtest/tools/sept_tune_audit_correction_2026_08_27.py
     (plain `python` also works -- stdlib only, no pandas/venv deps, matches trades_enriched.py)
"""
from __future__ import annotations

import collections
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECS = REPO / "analysis" / "recommendations"
ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sg = _load("scorecard_guards", REPO / "setup" / "scripts" / "lib" / "scorecard_guards.py")

IS_LO, IS_HI = "2026-07-01", "2026-08-14"
OOS_LO, OOS_HI = "2026-08-17", "2026-08-27"
WINDOW_LO, WINDOW_HI = "2026-07-01", "2026-08-27"
FDR_Q = 0.10
BOOT_N = 2000
BOOT_SEED = 1337
CLUSTER_WINDOW_S = 60.0

ANCHOR_SETUPS = ("BULLISH_RECLAIM_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON")
ANCHOR_STOP_MODE = "structure"
ANCHOR_COHORT_DEFINITION = (
    "engine trades, setup in BULLISH_RECLAIM_RIDE_THE_RIBBON/BEARISH_REJECTION_RIDE_THE_RIBBON, "
    "stop_mode=='structure' (current v15.3 chart-stop-primary production strategy -- the cohort "
    "FUTURE-IMPROVEMENTS.md's SEPT-TUNE intro names as 'the edge... everything else subtracted'). "
    "REDEFINED 2026-08-27: the original scorecards' anchor_cohort_n=33/winners=11 has no "
    "recoverable definition (no committed generator, no doc) -- this is a disclosed new "
    "definition, not a reproduction."
)


# --------------------------------------------------------------------------- #
# Load population
# --------------------------------------------------------------------------- #

def load_population() -> list:
    with ENRICHED.open(encoding="utf-8") as fh:
        rows = [json.loads(ln) for ln in fh if ln.strip()]
    rows = [r for r in rows if not r.get("_meta")]
    pop = [
        r for r in rows
        if r["attribution"] == "engine" and not r["unbalanced"]
        and WINDOW_LO <= r["date"] <= WINDOW_HI
        and r.get("pnl_dollars") is not None
    ]
    return pop


def _hhmm(row) -> str:
    et = row.get("entry_ts_et")
    if not et:
        return None
    try:
        return datetime.fromisoformat(str(et)).strftime("%H:%M")
    except ValueError:
        return None


def _iso_week(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _row_summary(r) -> dict:
    return {
        "date": r["date"], "arm": r["arm"], "sym": r["symbol"],
        "setup": r.get("setup"), "pnl": r["pnl_dollars"], "cost": r.get("cost_dollars"),
        "entry_hhmm": _hhmm(r), "ribbon": r.get("ribbon"),
    }


# --------------------------------------------------------------------------- #
# Anchor cohort
# --------------------------------------------------------------------------- #

def anchor_cohort(pop: list) -> list:
    return [r for r in pop if r.get("setup") in ANCHOR_SETUPS and r.get("stop_mode") == ANCHOR_STOP_MODE]


def anchor_check(pop: list, blocked: list) -> dict:
    anchor = anchor_cohort(pop)
    anchor_winners = [r for r in anchor if r["pnl_dollars"] > 0]
    blocked_keys = {(r["date"], r["arm"], r["symbol"]) for r in blocked}
    removed = [r for r in anchor_winners if (r["date"], r["arm"], r["symbol"]) in blocked_keys]
    return {
        "anchor_cohort_definition": ANCHOR_COHORT_DEFINITION,
        "anchor_cohort_n": len(anchor),
        "anchor_winners_n": len(anchor_winners),
        "removed_anchor_winners_n": len(removed),
        "removed_anchor_winners": [_row_summary(r) for r in removed],
        "anchor_no_regression": len(removed) == 0,
    }


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #

def _day_trade_pnls(rows: list, pnl_fn) -> dict:
    out: dict = collections.defaultdict(list)
    for r in rows:
        out[r["date"]].append(pnl_fn(r))
    return dict(out)


def build_guards(pop: list, blocked: list, counterfactual: list) -> dict:
    """Guards (i)+(ii)+(iii) for one cell. (iv) FDR is cross-cell, applied by the caller
    after all cells in the sweep are built (see main())."""
    cf_day_trade_pnls = _day_trade_pnls(counterfactual, lambda r: r["pnl_dollars"])
    bootstrap_counterfactual = sg.day_level_bootstrap(cf_day_trade_pnls, n_boot=BOOT_N, seed=BOOT_SEED)

    blocked_by_day = _day_trade_pnls(blocked, lambda r: r["pnl_dollars"])
    delta_day_trade_pnls = {d: [-p for p in pnls] for d, pnls in blocked_by_day.items()}
    # every population day that had zero blocked trades still contributes a $0 delta that
    # day -- include it so the bootstrap's day denominator matches the full population, not
    # just days the rule happened to fire on (a rule firing on 2 of 40 days should NOT look
    # "day-level significant" off only those 2 days).
    for r in pop:
        delta_day_trade_pnls.setdefault(r["date"], [])
        if not delta_day_trade_pnls[r["date"]]:
            delta_day_trade_pnls[r["date"]] = [0.0]
    delta_bootstrap = sg.day_level_bootstrap(delta_day_trade_pnls, n_boot=BOOT_N, seed=BOOT_SEED)
    delta_day_totals = {d: round(sum(v), 2) for d, v in blocked_by_day.items()}
    delta_day_totals = {d: -v for d, v in delta_day_totals.items()}
    ex_best = sg.ex_best_day(delta_day_totals)

    cluster = sg.signal_cluster_n(
        [{"date": r["date"], "sym": r["symbol"], "entry_ts_et": r.get("entry_ts_et")} for r in blocked],
        window_s=CLUSTER_WINDOW_S,
    )

    return {
        "counterfactual_bootstrap": bootstrap_counterfactual,
        "delta_bootstrap": delta_bootstrap,
        "ex_best_day": ex_best,
        "signal_cluster": cluster,
        "_delta_p_pnl_le_0_for_fdr": delta_bootstrap.get("p_pnl_le_0"),
    }


# --------------------------------------------------------------------------- #
# Generic cell builder
# --------------------------------------------------------------------------- #

def build_cell(rule_id: str, doc: str, pop: list, is_blocked_fn, extra: dict = None,
                anchor_pop: list = None) -> dict:
    blocked = [r for r in pop if is_blocked_fn(r)]
    kept = [r for r in pop if not is_blocked_fn(r)]
    n = len(pop)
    baseline_pnl = round(sum(r["pnl_dollars"] for r in pop), 2)
    baseline_wr = round(100 * sum(1 for r in pop if r["pnl_dollars"] > 0) / n, 1) if n else None
    cf_pnl = round(sum(r["pnl_dollars"] for r in kept), 2)
    cf_n = len(kept)
    cf_wr = round(100 * sum(1 for r in kept if r["pnl_dollars"] > 0) / cf_n, 1) if cf_n else None
    delta = round(cf_pnl - baseline_pnl, 2)

    winners = [r for r in blocked if r["pnl_dollars"] > 0]
    losers = [r for r in blocked if r["pnl_dollars"] <= 0]

    def _split(lo, hi):
        sub = [r for r in pop if lo <= r["date"] <= hi]
        sub_blocked = [r for r in sub if is_blocked_fn(r)]
        d = round(-sum(r["pnl_dollars"] for r in sub_blocked), 2)
        return len(sub), len(sub_blocked), d

    is_n, is_nb, is_delta = _split(IS_LO, IS_HI)
    oos_n, oos_nb, oos_delta = _split(OOS_LO, OOS_HI)

    weekly: dict = {}
    weeks = sorted(set(_iso_week(r["date"]) for r in pop))
    for wk in weeks:
        wk_pop = [r for r in pop if _iso_week(r["date"]) == wk]
        wk_blocked = [r for r in wk_pop if is_blocked_fn(r)]
        weekly[wk] = {
            "n": len(wk_pop), "n_blocked": len(wk_blocked),
            "delta": round(-sum(r["pnl_dollars"] for r in wk_blocked), 2),
        }
    active_weeks = [w for w, v in weekly.items() if v["n_blocked"] > 0]
    helped_weeks = [w for w in active_weeks if weekly[w]["delta"] >= 0]
    sub_window_stable = (len(helped_weeks) / len(active_weeks) >= 0.5) if active_weeks else True

    # anchor cohort is always evaluated against the FULL book (never rule-scoped) -- matches
    # the original scorecards, which reported the identical anchor_cohort_n/winners_n across
    # all 4 files regardless of each rule's own population restriction (e.g. mixed_ribbon_gate
    # is core-arm-only, but its anchor check still covers the whole engine population).
    anchor = anchor_check(anchor_pop if anchor_pop is not None else pop, blocked)

    wf_proxy = round(oos_delta / is_delta, 3) if is_delta not in (0, 0.0) else None
    wf_ge_070 = (wf_proxy is not None and wf_proxy >= 0.70)
    oos_positive = oos_delta > 0
    evidence_n = len(blocked)

    guards = build_guards(pop, blocked, kept)

    auto_ratify = bool(oos_positive and wf_ge_070 and sub_window_stable and anchor["anchor_no_regression"]
                        and not guards["ex_best_day"]["auto_fail_sign_flips_ex_best_day"])
    reasons = []
    if not oos_positive:
        reasons.append("OOS_delta<=0")
    if wf_proxy is None:
        reasons.append("WF-proxy undefined (IS_delta=0)")
    elif not wf_ge_070:
        reasons.append(f"WF-proxy={wf_proxy} <0.70")
    if not sub_window_stable:
        reasons.append("sub_window unstable (<50% active weeks helped)")
    if not anchor["anchor_no_regression"]:
        reasons.append(f"removes {anchor['removed_anchor_winners_n']} anchor-cohort winner(s)")
    if guards["ex_best_day"]["auto_fail_sign_flips_ex_best_day"]:
        reasons.append("ex-best-day sign flip (edge is single-day-dependent)")
    if evidence_n < 15:
        reasons.append(f"evidence_n={evidence_n} <15 (advisory)")
    reason = "PASSES all hard gates" if auto_ratify else "BLOCKED: " + "; ".join(reasons)

    cell = {
        "_doc": doc,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "basis": "flat_to_flat",
        "rule_id": rule_id,
        "population": f"engine-attribution option round trips (flat_to_flat basis), {WINDOW_LO}..{WINDOW_HI} (full window, not August-only)",
        "IS_window": f"{IS_LO}..{IS_HI}",
        "OOS_window": f"{OOS_LO}..{OOS_HI}",
        "baseline": {"n": n, "pnl": baseline_pnl, "wr_pct": baseline_wr},
        "counterfactual": {"n": cf_n, "pnl": cf_pnl, "wr_pct": cf_wr},
        "delta_pnl": delta,
        "n_blocked": len(blocked),
        "blocked_winners_n": len(winners),
        "blocked_winners_pnl": round(sum(r["pnl_dollars"] for r in winners), 2),
        "blocked_losers_n": len(losers),
        "blocked_losers_pnl": round(sum(r["pnl_dollars"] for r in losers), 2),
        "is_oos": {"IS_n": is_n, "IS_n_blocked": is_nb, "IS_delta": is_delta,
                   "OOS_n": oos_n, "OOS_n_blocked": oos_nb, "OOS_delta": oos_delta},
        "sub_window_weekly": weekly,
        "anchor_check": {k: v for k, v in anchor.items()},
        "concentration_warning": (
            f"SMALL SAMPLE: only {len(blocked)} trades blocked "
            f"({guards['signal_cluster']['signal_cluster_n']} independent signal clusters). "
            "Any positive delta here is NOT robust -- do not oversell a single-digit-n result."
        ) if len(blocked) < 15 else None,
        "n_blocked_full_list": [_row_summary(r) for r in blocked],
        "guards": {
            "day_level_bootstrap_counterfactual": guards["counterfactual_bootstrap"],
            "day_level_bootstrap_delta": guards["delta_bootstrap"],
            "ex_best_day": guards["ex_best_day"],
            "signal_cluster": guards["signal_cluster"],
            "doc": (
                "day_level_bootstrap_counterfactual bootstraps the POST-RULE population's day "
                "totals (is the resulting book profitable/PF>1 under day resampling); "
                "day_level_bootstrap_delta bootstraps the RULE'S OWN claimed benefit "
                "(-sum(blocked pnl) per day, zero-filled on days the rule never fired) -- its "
                "p_pnl_le_0 is the p-value fed into this sweep's BH-FDR (see the sibling "
                "SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json fdr_across_sweep block). "
                "ex_best_day is computed on the delta series. signal_cluster is computed on "
                "the BLOCKED trades (n_blocked's fill count vs its true independent-signal "
                "count, 60s same-symbol clustering -- see scorecard_guards.py)."
            ),
        },
        "gates": {
            "OOS_positive": oos_positive,
            "WF_proxy_OOS_over_IS": wf_proxy,
            "WF_proxy_ge_0_70": wf_ge_070,
            "sub_window_stable": sub_window_stable,
            "sub_window_weeks_helped": f"{len(helped_weeks)}/{len(active_weeks)}",
            "anchor_no_regression": anchor["anchor_no_regression"],
            "auto_fail_sign_flips_ex_best_day": guards["ex_best_day"]["auto_fail_sign_flips_ex_best_day"],
            "evidence_n": evidence_n,
            "signal_cluster_n": guards["signal_cluster"]["signal_cluster_n"],
            "evidence_n_ge_15_advisory": evidence_n >= 15,
            "auto_ratify_eligible": auto_ratify,
            "reason": reason,
        },
    }
    if extra:
        cell.update(extra)
    return cell, guards["_delta_p_pnl_le_0_for_fdr"]


# --------------------------------------------------------------------------- #
# The 4 rules
# --------------------------------------------------------------------------- #

def rule_premium_cost_cap(pop, threshold):
    return lambda r: (r.get("cost_dollars") or 0) > threshold


def rule_vwap_family(pop):
    setups = ("VWAP_CONTINUATION", "VWAP_RECLAIM_FAILED_BREAK")
    return lambda r: r.get("setup") in setups


def rule_mixed_ribbon(pop):
    core_arms = ("safe-2", "bold-2")
    return lambda r: r["arm"] in core_arms and r.get("ribbon") == "MIXED"


def rule_lunch_window(pop):
    def fn(r):
        hhmm = _hhmm(r)
        return hhmm is not None and "12:00" <= hhmm < "13:00"
    return fn


def fleet_disclosure(pop, field_present_fn):
    fleet = [r for r in pop if r["arm"] not in ("safe-2", "bold-2")]
    present = [r for r in fleet if field_present_fn(r)]
    return {
        "_doc": "Fleet arm decisions.jsonl rows do not carry this field at entry -- UNKNOWN/"
                "unenforceable for fleet arms as-is, not zero-effect. Fleet population reported "
                "separately, untouched by this rule.",
        "fleet_eng_n": len(fleet),
        "fleet_eng_pnl": round(sum(r["pnl_dollars"] for r in fleet), 2),
        "fleet_field_present_n": len(present),
    }


def main():
    pop = load_population()
    print(f"[audit-correction] population (flat_to_flat, engine, {WINDOW_LO}..{WINDOW_HI}): "
          f"n={len(pop)} pnl=${sum(r['pnl_dollars'] for r in pop):.2f}")
    max_cost = max((r.get("cost_dollars") or 0) for r in pop)
    print(f"[audit-correction] max cost_dollars in population: ${max_cost:.2f} (must be <= $1,880)")
    assert max_cost <= 1880.5, f"FAIL: population contains a phantom cost > $1,880 (${max_cost})"

    fdr_pvalues = {}
    cells = {}

    # --- premium_cost_cap_1200 (+ 800/1600 sweep) ---
    cell_1200, p_1200 = build_cell(
        "premium_cost_cap_1200",
        "Counterfactual A/B scorecard for candidate 'premium_cost_cap_1200' (block any entry "
        "with premium cost > $1200). REGENERATED 2026-08-27 on corrected flat_to_flat basis "
        "(AUDIT-CORRECTIONS-2026-08-27 -- see superseded_by_audit_2026_08_27 for the original, "
        "phantom-position-corrupted values). NO LOOK-AHEAD: conditions ONLY on entry-time info.",
        pop, rule_premium_cost_cap(pop, 1200),
    )
    fdr_pvalues["premium_cost_cap_1200@1200"] = p_1200
    sweep = {}
    for thr in (800, 1200, 1600):
        c, p = build_cell(f"premium_cost_cap_{thr}_variant", "cap sweep variant", pop,
                           rule_premium_cost_cap(pop, thr))
        sweep[str(thr)] = {
            "n_blocked": c["n_blocked"], "delta_pnl": c["delta_pnl"], "gates": c["gates"],
            "IS_delta": c["is_oos"]["IS_delta"], "OOS_delta": c["is_oos"]["OOS_delta"],
            "guards": c["guards"],
        }
        fdr_pvalues[f"premium_cost_cap_1200@{thr}"] = p
    cell_1200["cap_sweep_800_1200_1600"] = sweep
    cells["premium_cost_cap_1200"] = cell_1200

    # --- vwap_family_demotion (+ variant_b cost-cap-600 rescale) ---
    cell_vwap, p_vwap = build_cell(
        "vwap_family_demotion",
        "Counterfactual A/B scorecard for candidate 'vwap_family_demotion' (block "
        "VWAP_CONTINUATION + VWAP_RECLAIM_FAILED_BREAK entirely). REGENERATED 2026-08-27 on "
        "corrected flat_to_flat basis (AUDIT-CORRECTIONS-2026-08-27). NO LOOK-AHEAD.",
        pop, rule_vwap_family(pop),
    )
    fdr_pvalues["vwap_family_demotion"] = p_vwap
    cells["vwap_family_demotion"] = cell_vwap

    # --- mixed_ribbon_gate ---
    # Population restricted to CORE ARMS ONLY (safe-2/bold-2) -- matches the original
    # scorecard's methodology: fleet arms carry no ribbon field at entry, so scoring this
    # rule against the full book would silently average in 225 fleet trades this rule can
    # never even see, let alone block. Fleet is disclosed separately (fleet_disclosure below),
    # never folded into baseline/counterfactual/delta.
    core_pop = [r for r in pop if r["arm"] in ("safe-2", "bold-2")]
    cell_ribbon, p_ribbon = build_cell(
        "mixed_ribbon_gate",
        "Counterfactual A/B scorecard for candidate 'mixed_ribbon_gate' (block entries where "
        "ribbon=='MIXED' at ENTER, core arms only). REGENERATED 2026-08-27 on corrected "
        "flat_to_flat basis (AUDIT-CORRECTIONS-2026-08-27). NO LOOK-AHEAD. Population "
        "restricted to core arms (safe-2/bold-2) -- fleet arms carry no ribbon field at entry.",
        core_pop, rule_mixed_ribbon(core_pop),
        extra={"fleet_disclosure": fleet_disclosure(pop, lambda r: r.get("ribbon") is not None)},
        anchor_pop=pop,
    )
    fdr_pvalues["mixed_ribbon_gate"] = p_ribbon
    cells["mixed_ribbon_gate"] = cell_ribbon

    # --- lunch_window_gate_1200_1300 ---
    cell_lunch, p_lunch = build_cell(
        "lunch_window_gate_1200_1300",
        "Counterfactual A/B scorecard for candidate 'lunch_window_gate_1200_1300' (block "
        "entries with entry time 12:00-12:59 ET). REGENERATED 2026-08-27 on corrected "
        "flat_to_flat basis (AUDIT-CORRECTIONS-2026-08-27). NO LOOK-AHEAD.",
        pop, rule_lunch_window(pop),
    )
    fdr_pvalues["lunch_window_gate_1200_1300"] = p_lunch
    cells["lunch_window_gate_1200_1300"] = cell_lunch

    fdr = sg.benjamini_hochberg(fdr_pvalues, q=FDR_Q)
    print(f"[audit-correction] BH-FDR q={FDR_Q} across m={fdr['m']} cells: rejected={fdr['rejected']}")

    # --- write each scorecard, preserving OLD content under superseded_by_audit_2026_08_27 ---
    for rule_id, cell in cells.items():
        path = RECS / f"{rule_id}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        cell["fdr_across_sweep"] = {
            "q": FDR_Q, "m": fdr["m"],
            "this_cell_p_value": fdr_pvalues.get(rule_id) or fdr_pvalues.get(f"{rule_id}@1200"),
            "significant_after_fdr": rule_id in fdr["rejected"] or f"{rule_id}@1200" in fdr["rejected"],
            "all_cells_tested": sorted(fdr_pvalues.keys()),
            "doc": "See SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json for the full cross-sweep FDR block.",
        }
        if old is not None:
            cell["superseded_by_audit_2026_08_27"] = old
        path.write_text(json.dumps(cell, indent=2) + "\n", encoding="utf-8")
        print(f"[audit-correction] wrote {path.relative_to(REPO)} "
              f"(n_blocked={cell['n_blocked']}, auto_ratify={cell['gates']['auto_ratify_eligible']})")

    # --- overlap matrix ---
    blocked_sets = {
        rid: {(r["date"], r["arm"], r["sym"]) for r in cell["n_blocked_full_list"]}
        for rid, cell in cells.items()
    }
    rule_ids = list(cells.keys())
    pairwise = {}
    for i, a in enumerate(rule_ids):
        for b in rule_ids[i + 1:]:
            shared = blocked_sets[a] & blocked_sets[b]
            pairwise[f"{a} & {b}"] = {
                "n_shared": len(shared), "n_a": len(blocked_sets[a]), "n_b": len(blocked_sets[b]),
            }

    # marginal value of premium_cost_cap_1200 after vwap_family_demotion already applied
    pop_after_vwap = [r for r in pop if not rule_vwap_family(pop)(r)]
    cell_marginal, p_marginal = build_cell(
        "premium_cost_cap_1200_marginal_after_vwap", "marginal", pop_after_vwap,
        rule_premium_cost_cap(pop_after_vwap, 1200),
    )
    rule2_marginal = {
        "n_blocked_marginal": cell_marginal["n_blocked"],
        "n_blocked_standalone": cells["premium_cost_cap_1200"]["n_blocked"],
        "delta_pnl_marginal": cell_marginal["delta_pnl"],
        "delta_pnl_standalone": cells["premium_cost_cap_1200"]["delta_pnl"],
        "gates": cell_marginal["gates"],
    }

    old_matrix_path = RECS / "SEPT-TUNE-OVERLAP-MATRIX-2026-08-27.json"
    old_matrix = json.loads(old_matrix_path.read_text(encoding="utf-8")) if old_matrix_path.exists() else None
    matrix = {
        "_doc": "Pairwise overlap of blocked-trade sets across the 4 candidates, plus the "
                "marginal value of premium_cost_cap_1200 once vwap_family_demotion has already "
                "removed its trades. REGENERATED 2026-08-27 on corrected flat_to_flat basis "
                "(AUDIT-CORRECTIONS-2026-08-27) -- see superseded_by_audit_2026_08_27 for the "
                "original phantom-position-corrupted values.",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "basis": "flat_to_flat",
        "pairwise": pairwise,
        "rule2_marginal_after_rule1": rule2_marginal,
        "fdr_across_sweep": {
            "q": FDR_Q,
            "m_cells_tested": fdr["m"],
            "cells": sorted(fdr_pvalues.keys()),
            "p_values": fdr_pvalues,
            "rejected_significant": fdr["rejected"],
            "results": fdr["results"],
            "excluded_no_pvalue": fdr["excluded_no_pvalue"],
            "doc": (
                "One-sided bootstrap p-value per cell = P(day-resampled delta_pnl<=0) "
                "(scorecard_guards.day_level_bootstrap on the -blocked-pnl-per-day series, "
                "2000 resamples, seed 1337). Benjamini-Hochberg step-up, q=0.10, across all "
                f"{fdr['m']} cells scanned in this sweep (4 rules + 3-point cap sweep = 6 "
                "distinct threshold cells; the base premium_cost_cap_1200 rule and its @1200 "
                "sweep point are the same test, counted once)."
            ),
        },
    }
    if old_matrix is not None:
        matrix["superseded_by_audit_2026_08_27"] = old_matrix
    old_matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    print(f"[audit-correction] wrote {old_matrix_path.relative_to(REPO)}")

    return cells, matrix


if __name__ == "__main__":
    main()
