"""morning_gate_study.py -- PROFIT-P3-MORNING-GATE, the frozen runner for
analysis/recommendations/prereg-morning-gate-2026-07-11.json.

Runs the pre-registration EXACTLY as frozen: 3 candidate entry-time floors
(V1 block<11:00 / V2 block<10:30 / V3 block<10:35=09:35-open+60min) on the ribbon_ride
BULLISH_RECLAIM/BEARISH_REJECTION population, full 6-stage battery + kill ladder + mandatory
anchor-context disclosure. No re-picks (no_repick_clause) -- this file does not choose
thresholds; it evaluates the ones the registration froze.

REUSE (OP-22): p3p5_baseline.build_baseline() for the gate-OFF population (SS-B exit, OTM-2,
same pipeline PROFIT-P2 used -- verified byte-identical to the shipped ribbon-ride-strike-
exit-ab.json OTM-2/SS-B cell: n=250, exp=$17.86, total=$4465.60, before this study's
hypothesis-window exclusion is even needed since it does not overlap the achieved window).
t4_exit_matrix.battery() for the metrics bundle, autoresearch.null_baseline.random_entry_null
(sim_fn injection through ribbon_ride_strike_exit_ab.make_null_sim_fn -- the SAME SS-B replay
engine, not simulate_trade_real, which cannot express the structure-stop layer),
ribbon_rejection_wick_battery.bh_fdr (alpha=0.10).

Run: backtest/.venv/Scripts/python.exe backtest/tools/morning_gate_study.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_ride_strike_exit_ab as ab   # noqa: E402
import t4_exit_matrix as t4               # noqa: E402
import p3p5_baseline as base              # noqa: E402
from autoresearch.null_baseline import random_entry_null, DEFAULT_SEEDS  # noqa: E402

SMOKE = "--smoke" in sys.argv
OUT_JSON = REPO / "analysis" / "recommendations" / ("morning-gate-result-SMOKE.json" if SMOKE
                                                     else "morning-gate-result.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("morning-gate-result-SMOKE.md" if SMOKE
                                                   else "morning-gate-result.md")

ENTRY_WINDOW_OPEN = dt.time(9, 35)
CANDIDATES = {
    "V1_GATE_BEFORE_11": dt.time(11, 0, 0),
    "V2_GATE_BEFORE_1030": dt.time(10, 30, 0),
    "V3_GATE_FIRST_HOUR": dt.time(10, 35, 0),
}
CANDIDATE_ORDER = ["V1_GATE_BEFORE_11", "V2_GATE_BEFORE_1030", "V3_GATE_FIRST_HOUR"]
MIN_N = 20  # this project's live-graduation floor (CLAUDE.md), reused per the pre-reg

# J's 3 OP-16 source-of-truth winners -- exact entry times pulled from journal/YYYY-MM-DD.md
# (registration's own requirement: "not assumed from the summary table").
ANCHOR_WINNERS = [
    {"date": dt.date(2026, 4, 29), "time": dt.time(10, 25, 51), "label": "4/29 SPY 710P x6 -> +$342",
     "source": "journal/2026-04-29.md line 29 (Entry: 10:25:51 EDT)"},
    {"date": dt.date(2026, 5, 1), "time": dt.time(13, 9, 14), "label": "5/01 SPY 721P x20 -> +$470 (leg#1, PREMATURE/anticipation entry per journal)",
     "source": "journal/2026-05-01.md line 16 (Filled 13:09:14 EDT)"},
    {"date": dt.date(2026, 5, 1), "time": dt.time(13, 36, 11), "label": "5/01 SPY 721P x20 -> +$470 (leg#2, THE REAL TRIGGER per journal)",
     "source": "journal/2026-05-01.md line 21 (Filled 13:36:11 EDT)"},
    {"date": dt.date(2026, 5, 4), "time": dt.time(10, 27, 50), "label": "5/04 SPY 721P x10 -> +$730",
     "source": "journal/2026-05-04.md line 39 (Entry: 10:27:50 EDT)"},
]

EXCLUDED_SETUPS = ("vwap_continuation", "j_vwap_reclaim_fb", "J_VWAP_RECLAIM_FB",
                   "j_vix_dayside", "J_VIX_DAYSIDE")


def log(msg: str) -> None:
    print(f"[morning-gate] {msg}", flush=True)


def scope_check(trades: list[dict]) -> dict:
    """k5_scope_violation guard: the population must be ribbon_ride ONLY. _signal_cache's
    generator only ever emits BULLISH_RECLAIM/BEARISH_REJECTION ribbon_ride signals (BS_FALLBACK
    excluded at generation time), so this is a structural assertion, not a filter."""
    directions = {t["direction"] for t in trades}
    ok = directions <= {"bull", "bear"}
    return {"ok": ok, "directions_seen": sorted(directions),
           "note": ("_signal_cache.build_signals() only emits ribbon_ride BULLISH_RECLAIM/"
                    "BEARISH_REJECTION setups (source: strategy_space_grind run_backtest with "
                    "BS_FALLBACK excluded) -- vwap_continuation/j_vwap_reclaim_fb/j_vix_dayside "
                    "structurally cannot appear in this population.")}


def battery1(kept: list[dict], removed: list[dict], all_trades: list[dict]) -> dict:
    b_kept = t4.battery(kept)
    b_removed = t4.battery(removed)
    b_all = t4.battery(all_trades)
    return {"kept": b_kept, "removed": b_removed, "gate_off": b_all}


def stage2_oos(kept: list[dict], all_trades: list[dict]) -> dict:
    kept_is = [t for t in kept if t["date"] < base.OOS_BOUNDARY]
    kept_oos = [t for t in kept if t["date"] >= base.OOS_BOUNDARY]
    all_is = [t for t in all_trades if t["date"] < base.OOS_BOUNDARY]
    all_oos = [t for t in all_trades if t["date"] >= base.OOS_BOUNDARY]
    b_kept_is, b_kept_oos = t4.battery(kept_is), t4.battery(kept_oos)
    b_all_is, b_all_oos = t4.battery(all_is), t4.battery(all_oos)
    is_pass = (b_kept_is.get("expectancy") is not None and b_all_is.get("expectancy") is not None
              and b_kept_is["expectancy"] > b_all_is["expectancy"])
    oos_pass = (b_kept_oos.get("expectancy") is not None and b_all_oos.get("expectancy") is not None
               and b_kept_oos["expectancy"] > b_all_oos["expectancy"])
    return {"kept_is": b_kept_is, "kept_oos": b_kept_oos, "all_is": b_all_is, "all_oos": b_all_oos,
           "is_pass": bool(is_pass), "oos_pass": bool(oos_pass),
           "pass": bool(is_pass and oos_pass)}


def stage3_random_null(removed: list[dict], spy_full, spy_by_date, cutoff: dt.time) -> dict:
    n_call = sum(1 for t in removed if t["side"] == "C")
    n_put = sum(1 for t in removed if t["side"] == "P")
    if not removed:
        return {"null": {"note": "no removed trades -- candidate blocks nothing, stage moot"},
               "removed_expectancy": None, "pass": True, "note": "n_removed=0, vacuously passes"}
    sim_fn = ab.make_null_sim_fn(base.SO, base.SHAPE, True, spy_by_date)
    null = random_entry_null(
        rth=spy_full, n_signals=len(removed), n_call=n_call, n_put=n_put,
        strike_offset=base.SO, premium_stop_pct=base.SHAPE["premium_stop_pct"],
        qty=base.QTY, entry_gate=(ENTRY_WINDOW_OPEN, cutoff), seeds=DEFAULT_SEEDS,
        setup="MORNING_GATE_NULL", sim_fn=sim_fn,
    )
    removed_exp = t4.battery(removed).get("expectancy")
    p = null.get("per_trade_mean")
    passed = (removed_exp is not None and p is not None and removed_exp <= p)
    return {"null": null, "removed_expectancy": removed_exp,
           "pass": bool(passed),
           "note": "PASS = the blocked cohort's own realized per-trade is <= the random-entry null mean"}


def stage4_opposite_null(kept: list[dict], removed: list[dict], all_trades: list[dict],
                         all_exp: float) -> dict:
    target_n = len(removed)
    if target_n == 0:
        return {"pass": True, "note": "n_removed=0, opposite-null check vacuous"}
    times_desc = sorted((t["entry_ts"].time() for t in all_trades), reverse=True)
    idx = min(target_n, len(times_desc)) - 1
    threshold_time = times_desc[idx]
    mirror_blocked = [t for t in all_trades if t["entry_ts"].time() >= threshold_time]
    mirror_kept = [t for t in all_trades if t["entry_ts"].time() < threshold_time]
    mirror_kept_exp = t4.battery(mirror_kept).get("expectancy")
    kept_exp = t4.battery(kept).get("expectancy")
    candidate_delta = (kept_exp - all_exp) if (kept_exp is not None and all_exp is not None) else None
    mirror_delta = (mirror_kept_exp - all_exp) if (mirror_kept_exp is not None and all_exp is not None) else None
    # "comparable-or-larger" = mirror achieves >=90% of the candidate's own improvement
    # (disclosed threshold -- the registration names the concept, not a numeric bar).
    comparable = (candidate_delta is not None and candidate_delta > 0 and mirror_delta is not None
                 and mirror_delta >= 0.9 * candidate_delta)
    return {
        "threshold_time_et": str(threshold_time), "n_mirror_blocked": len(mirror_blocked),
        "target_n": target_n, "pct_diff_from_target": (round(100 * (len(mirror_blocked) - target_n) / target_n, 1)
                                                        if target_n else None),
        "mirror_kept_expectancy": mirror_kept_exp, "candidate_kept_expectancy": kept_exp,
        "candidate_delta": round(candidate_delta, 2) if candidate_delta is not None else None,
        "mirror_delta": round(mirror_delta, 2) if mirror_delta is not None else None,
        "mirror_comparable_or_larger": bool(comparable),
        "pass": bool(not comparable),
        "note": ("PASS = the late-session mirror gate does NOT match/beat the candidate's own "
                "improvement (threshold: mirror_delta < 90% of candidate_delta)"),
    }


def stage5_concentration(kept: dict, all_battery: dict) -> dict:
    kept_drop3 = kept.get("exp_drop_top3")
    all_drop3 = all_battery.get("exp_drop_top3")
    passed = (kept_drop3 is not None and all_drop3 is not None and kept_drop3 > all_drop3)
    return {"kept_drop_top3": kept_drop3, "gate_off_drop_top3": all_drop3, "pass": bool(passed)}


def anchor_context(cutoff: dt.time) -> dict:
    blocked = [a for a in ANCHOR_WINNERS if a["time"] < cutoff]
    return {"cutoff_et": str(cutoff), "blocked_winners": [a["label"] for a in blocked],
           "any_blocked": len(blocked) > 0,
           "miscalibrated": len(blocked) > 0}


def evaluate_candidate(cand_id: str, cutoff: dt.time, all_trades: list[dict],
                       spy_full, spy_by_date) -> dict:
    t0 = _time_mod.time()
    kept = [t for t in all_trades if t["entry_ts"].time() >= cutoff]
    removed = [t for t in all_trades if t["entry_ts"].time() < cutoff]
    b1 = battery1(kept, removed, all_trades)
    all_exp = b1["gate_off"].get("expectancy")
    s1_pass = (b1["kept"].get("expectancy") is not None and all_exp is not None
              and b1["kept"]["expectancy"] > all_exp)
    s2 = stage2_oos(kept, all_trades)
    s3 = stage3_random_null(removed, spy_full, spy_by_date, cutoff)
    s4 = stage4_opposite_null(kept, removed, all_trades, all_exp)
    s5 = stage5_concentration(b1["kept"], b1["gate_off"])
    anchor = anchor_context(cutoff)

    n_kept, n_removed = len(kept), len(removed)
    insufficient_n = n_kept < MIN_N or n_removed < MIN_N

    k1 = not s1_pass
    k2 = not s2["pass"]
    k3 = bool(s4.get("mirror_comparable_or_larger"))
    # k4 (BH-FDR) filled in by caller after all 3 candidates' p_null are known.
    elapsed = round(_time_mod.time() - t0, 1)
    log(f"{cand_id} (cutoff {cutoff}): n_kept={n_kept} n_removed={n_removed} "
        f"exp_kept=${b1['kept'].get('expectancy')} exp_gate_off=${all_exp} "
        f"stage1={s1_pass} stage2={s2['pass']} stage3={s3['pass']} stage4={s4['pass']} "
        f"stage5={s5['pass']} anchor_miscalibrated={anchor['miscalibrated']} ({elapsed}s)")

    return {
        "candidate_id": cand_id, "cutoff_et": str(cutoff),
        "n_kept": n_kept, "n_removed": n_removed, "insufficient_n": insufficient_n,
        "stage1_expectancy": {"pass": s1_pass, "kept": b1["kept"], "removed": b1["removed"],
                              "gate_off": b1["gate_off"]},
        "stage2_oos": s2,
        "stage3_random_null": s3,
        "stage4_opposite_null": s4,
        "stage5_concentration": s5,
        "kill_flags": {"k1_stage1_fail": k1, "k2_stage2_fail": k2,
                       "k3_opposite_null_comparable": k3},
        "anchor_context_disclosure": anchor,
        "p_null": (1.0 if s3.get("removed_expectancy") is None else
                  round((1 + sum(1 for v in s3["null"].get("per_trade_by_seed", [])
                                if v >= s3["removed_expectancy"])) / (1 + max(1, len(s3["null"].get("per_trade_by_seed", [])))), 4)),
    }


def main() -> int:
    t_start = _time_mod.time()
    log(f"{'SMOKE MODE' if SMOKE else 'FULL RUN'} -- loading shared p3p5 baseline")
    all_trades, spy_full, spy_by_date, base_meta = base.build_baseline()
    if SMOKE:
        all_trades = all_trades[:60]
        log(f"SMOKE: truncated to {len(all_trades)} trades")

    scope = scope_check(all_trades)
    if not scope["ok"]:
        log(f"K5 SCOPE VIOLATION: {scope}")

    results = {}
    for cid in CANDIDATE_ORDER:
        results[cid] = evaluate_candidate(cid, CANDIDATES[cid], all_trades, spy_full, spy_by_date)

    # stage6: BH-FDR across the 3 candidates
    bh_input = [{"p_null": results[cid]["p_null"]} for cid in CANDIDATE_ORDER]
    ab.bh_fdr(bh_input, alpha=ab.FDR_ALPHA)
    for cid, b in zip(CANDIDATE_ORDER, bh_input):
        results[cid]["bh_fdr_survivor"] = b["bh_fdr_survivor"]
        results[cid]["bh_rank"] = b["bh_rank"]
        results[cid]["kill_flags"]["k4_bh_fdr_fail"] = not b["bh_fdr_survivor"]

    verdicts = {}
    for cid in CANDIDATE_ORDER:
        r = results[cid]
        if scope["ok"] is False:
            verdicts[cid] = "KILL_K5_SCOPE_VIOLATION"
        elif r["insufficient_n"]:
            verdicts[cid] = "INSUFFICIENT_N"
        elif any(r["kill_flags"].values()):
            reasons = [k for k, v in r["kill_flags"].items() if v]
            verdicts[cid] = f"KILL ({', '.join(reasons)})"
        else:
            s2p, s3p, s5p = r["stage2_oos"]["pass"], r["stage3_random_null"]["pass"], r["stage5_concentration"]["pass"]
            pass_bar = r["stage1_expectancy"]["pass"] and s2p and s3p and r["stage4_opposite_null"]["pass"] and s5p and r["bh_fdr_survivor"]
            verdicts[cid] = "PASS" if pass_bar else "FAIL"
        results[cid]["verdict"] = verdicts[cid]

    out = {
        "_doc": ("PROFIT-P3-MORNING-GATE result. Runs analysis/recommendations/"
                "prereg-morning-gate-2026-07-11.json EXACTLY as frozen (no_repick_clause honored "
                "-- thresholds/population/battery/kill-bar unchanged from the registration). "
                "MEASURED tier: real OPRA local 5-min option bars replayed through the live "
                "exit_manager decision core (structure_stop_study.replay_structure_aware), NOT "
                "live broker fills."),
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "registration": "analysis/recommendations/prereg-morning-gate-2026-07-11.json",
        "baseline_meta": base_meta,
        "scope_check_k5": scope,
        "population_note": ("Shared p3p5_baseline: ribbon_ride BULLISH_RECLAIM/BEARISH_REJECTION, "
                            "both directions, OTM-2 strike, SS-B exit shape (fixed both arms), "
                            "QTY=10. Window achieved: "
                            f"{base_meta.get('window_achieved')} (registration's stated net window "
                            "2025-01-02..2026-06-25 -- achieved window is the cached signal set's "
                            "own span, ~1wk shorter at the tail, disclosed per the registration's "
                            "own 'no silent substitution' clause; the hypothesis-source window "
                            "2026-06-26..2026-07-09 does not overlap the achieved window either way)."),
        "candidates": results,
        "candidate_order": CANDIDATE_ORDER,
        "min_n_floor": MIN_N,
        "anchor_winners_checked": ANCHOR_WINNERS,
        "disclosures": [
            "Strike fixed at OTM-2, exit shape fixed at SS-B for BOTH gate-ON and gate-OFF arms "
            "(only entry inclusion differs) -- neither knob is named by the registration; this is "
            "a filled gap disclosed in p3p5_baseline.py's own module docstring, not a re-pick.",
            "Stage 4 (opposite/late-session mirror null) 'comparable-or-larger' is operationalized "
            "as mirror_delta >= 90% of candidate_delta -- the registration names the concept "
            "without a numeric bar; this threshold is disclosed here, not silently chosen.",
            "p_null (feeding stage 6 BH-FDR) is the add-one empirical p-value of the REMOVED "
            "cohort's own realized expectancy against the stage-3 random-entry-null's per-seed "
            "means (10 seeds, module default) -- same convention PROFIT-P2 used, distinct from "
            "ribbon_rejection_wick_battery.bootstrap_p's trade-level bootstrap (disclosed, not "
            "conflated).",
            "anchor_context_check is DISCLOSURE-ONLY per the registration (not a pass/fail gate "
            "for P3, unlike P5's k6) -- reported prominently regardless of aggregate verdict.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({round(_time_mod.time()-t_start,1)}s total)")
    for cid in CANDIDATE_ORDER:
        log(f"VERDICT {cid}: {results[cid]['verdict']}")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# PROFIT-P3 MORNING-GATE — result")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Registration: `{out['registration']}`. "
            f"Runner: `backtest/tools/morning_gate_study.py`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE — reduced population, pipeline verification only, NOT decision-grade.**")
    L.append("")
    L.append(f"**Population:** {out['population_note']}")
    L.append("")
    L.append(f"**k5 scope check:** {'PASS' if out['scope_check_k5']['ok'] else 'VIOLATION'} "
            f"(directions seen: {out['scope_check_k5']['directions_seen']})")
    L.append("")
    L.append("## Anchor context (J's 3 OP-16 winners — disclosure, mandatory report before aggregate)")
    L.append("")
    for a in out["anchor_winners_checked"]:
        L.append(f"- {a['label']} — entry {a['time']} ET ({a['source']})")
    L.append("")
    L.append("| candidate | cutoff | n_kept | n_removed | blocks which winners |")
    L.append("|---|---|--:|--:|---|")
    for cid in out["candidate_order"]:
        r = out["candidates"][cid]
        blocked = r["anchor_context_disclosure"]["blocked_winners"]
        L.append(f"| {cid} | {r['cutoff_et']} | {r['n_kept']} | {r['n_removed']} | "
                f"{'; '.join(blocked) if blocked else 'none'} |")
    L.append("")
    L.append("## Battery results")
    L.append("")
    L.append("| candidate | exp kept | exp gate-off | s1 | s2 OOS | s3 null | s4 opposite | "
            "s5 concentration | s6 BH-FDR | verdict |")
    L.append("|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|")
    for cid in out["candidate_order"]:
        r = out["candidates"][cid]
        L.append(f"| {cid} | ${r['stage1_expectancy']['kept'].get('expectancy')} | "
                f"${r['stage1_expectancy']['gate_off'].get('expectancy')} | "
                f"{r['stage1_expectancy']['pass']} | {r['stage2_oos']['pass']} | "
                f"{r['stage3_random_null']['pass']} | {r['stage4_opposite_null']['pass']} | "
                f"{r['stage5_concentration']['pass']} | {r['bh_fdr_survivor']} | "
                f"**{r['verdict']}** |")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
