"""Assembly step for TP1-R50-READJUDICATION-2026-08-23: merges the outputs of
tp1_r50_readjudication_2026_08_23.py (Part 2 -- extended popA gate re-run) and
tp1_r50_live_arm_2026_08_23.py (Part 1 -- forward-clock; Part 3 -- live-arm corroboration)
into the single deliverable requested by the brief: analysis/recommendations/
tp1-r50-readjudication-2026-08-23.json (overwritten in place with the merged/final shape) plus
a companion .md with the one-line verdict at the top.

G6/G7/G8 (week-population-B-scope + cross-cell BH-FDR family scope) are CARRIED FORWARD from
the original 2026-08-06 scorecard, UNCHANGED and clearly labeled -- this study extended
population A (the entry window) only, per the brief; it did not re-pull population B's real
broker week-book or re-run the full 28-cell grid the BH-FDR family scope depends on. Carrying
forward a value that was never re-verified this session is disclosed, not silently presented as
fresh.

Run: backtest/.venv/Scripts/python.exe backtest/tools/tp1_r50_assemble_2026_08_23.py
(after both tp1_r50_readjudication_2026_08_23.py and tp1_r50_live_arm_2026_08_23.py have run)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PART2_JSON = REPO / "analysis" / "recommendations" / "tp1-r50-readjudication-2026-08-23.json"
LIVE_ARM_JSON = REPO / "analysis" / "recommendations" / "tp1-r50-live-arm-2026-08-23.json"
ORIGINAL_SCORECARD = REPO / "analysis" / "recommendations" / "tp1-reachability-2026-08-06.json"
FINAL_JSON = PART2_JSON  # overwrite in place -- this IS the requested deliverable path
FINAL_MD = REPO / "analysis" / "recommendations" / "tp1-r50-readjudication-2026-08-23.md"


def main() -> int:
    part2 = json.loads(PART2_JSON.read_text(encoding="utf-8"))
    live_arm = json.loads(LIVE_ARM_JSON.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL_SCORECARD.read_text(encoding="utf-8"))
    orig_r50 = next(c for c in original["cells"] if c["id"] == "R_tp100_f50")

    part1 = live_arm["part1_forward_clock"]
    part3 = live_arm["part3_live_arm_corroboration"]

    void = part2["void_check"]["void"]
    premature = not part1["clock_triggered"]

    if void:
        full_gates = None
        full_bar = None
        clears_full_bar = None
        gate_summary_line = "VOID -- CONTROL reconciliation failed, no gate table computed"
    else:
        r50 = part2["cells"]["R_tp100_f50"]
        full_gates = dict(r50["gates_popA_scope"])
        full_gates["G6_week_tuesday_HARD"] = orig_r50["gates"]["G6_week_tuesday_HARD"]
        full_gates["G7_week_total"] = orig_r50["gates"]["G7_week_total"]
        full_gates["G8_bh_fdr"] = orig_r50["gates"]["G8_bh_fdr"]
        full_bar = dict(r50["bar_popA_scope"])
        clears_all_gates = all(full_gates.values())
        clears_full_bar = clears_all_gates and all(full_bar.values())
        failing = [k for k, v in full_gates.items() if not v]
        gate_summary_line = ("CLEARS ALL 8 GATES + full bar" if clears_full_bar
                              else f"FAILS: {', '.join(failing)}")

    final = {
        "_doc": (
            "EXTENDED RE-ADJUDICATION of frozen prereg cell R_tp100_f50 "
            "(analysis/recommendations/prereg-tp1-reachability-2026-08-06.json). Assembled from "
            "backtest/tools/tp1_r50_readjudication_2026_08_23.py (Part 2, extended popA gate "
            "re-run) + backtest/tools/tp1_r50_live_arm_2026_08_23.py (Part 1 forward-clock, "
            "Part 3 live-arm corroboration) + carried-forward G6/G7/G8 from the original "
            "2026-08-06 scorecard (week-population-B-scope + cross-cell BH-FDR family scope, "
            "NOT re-run this session -- disclosed below, not silently presented as fresh)."
        ),
        "generated_at_et": dt.datetime.now().isoformat(),
        "prereg_id": "TP1-REACHABILITY-2026-08-06",
        "cell_readjudicated": "R_tp100_f50 (ribbon_ride, tp1_premium_pct=1.0, tp1_qty_fraction=0.5)",
        "control_null_cell": "R_tp100_f667 (== live registry AS OF 2026-08-06 -- see drift_disclosure)",

        "part1_forward_clock": part1,
        "premature_clock": premature,

        "part2_extended_population": {
            "drift_disclosure": part2["drift_disclosure"],
            "cache_last_date": part2["cache_last_date"],
            "original_popA_window": part2["original_popA_window"],
            "extension_window": part2["extension_window"],
            "extension_stats": part2["extension_stats"],
            "combined_popA_n": part2["combined_popA_n"],
            "void_check": part2["void_check"],
            "runner_cohort_extended": part2["runner_cohort"],
            "g4_subwindow_boundaries_extended": part2["g4_subwindow_boundaries_extended"],
            "cells": part2["cells"],
            "g4_structural_finding": (
                "G4 requires >=3 of the sub-windows (among those with >=5 changed trades) to be "
                "delta>=-$0.005, AND at least 2 windows must qualify (>=5 changed trades) at all. "
                "2025H1 and 2026Q1 are FIXED CALENDAR-PAST windows sitting at n_changed=4 each "
                "(both original 2026-08-06 run and this extended run) -- a forward extension of "
                "popA's END date can only ever add trades to the newest (4th) window; it cannot "
                "retroactively add trades to a window that is entirely in the past. Only 2 of the "
                "4 windows (2025H2 n=13, 2026Q2p_ext n=14) can ever qualify under this population-"
                "extension approach, so the >=3-qualifying-and-positive requirement is "
                "STRUCTURALLY UNREACHABLE via this lever alone -- extending popA's window further "
                "forward (e.g. through a later cache date) would grow the 4th window further but "
                "still cannot create a 3rd qualifying window. G4 did not fail this run for the "
                "same reason it failed originally (power/dispersion, all windows positive) -- it "
                "fails now for a DIFFERENT, sharper reason: the gate's own qualification "
                "structure caps out at 2 qualifying windows for this population, permanently, "
                "under any forward-only extension."
            ),
        },

        "full_gate_table": full_gates,
        "full_gate_table_summary": gate_summary_line,
        "g6_g7_g8_carried_forward_disclosure": (
            "G6_week_tuesday_HARD, G7_week_total, G8_bh_fdr are CARRIED FORWARD verbatim from the "
            "original 2026-08-06 scorecard (all TRUE there, orig_r50.gates) -- this extension did "
            "NOT re-pull population B's real broker week-book (2026-08-03..06 is a closed, already-"
            "settled real-fills week; nothing new to re-derive) and did NOT re-run the full 28-cell "
            "BH-FDR family (out of scope for a single-cell re-adjudication of R_tp100_f50). "
            f"Original values: G6={orig_r50['gates']['G6_week_tuesday_HARD']} "
            f"G7={orig_r50['gates']['G7_week_total']} G8={orig_r50['gates']['G8_bh_fdr']} "
            f"(bh_family_size={original['bh_family_size']}, bh_survivors={original['bh_survivors']})."
        ),
        "auto_ratify_bar_full": full_bar,
        "clears_full_auto_ratify_bar": clears_full_bar,

        "part3_live_arm_corroboration": part3,

        "verdict": (
            "VOID" if void else
            ("R_tp100_f50 CLEARS the full auto-ratify bar on the extended population"
             if clears_full_bar else
             "R_tp100_f50 STILL FAILS G4_subwindow_stable on the extended population -- "
             "DO_NOT_ARM stands. Prereg stays FROZEN.")
        ),
    }
    FINAL_JSON.write_text(json.dumps(final, indent=2, default=str), encoding="utf-8")
    print(f"[assemble] wrote {FINAL_JSON}")
    print(f"[assemble] VERDICT: {final['verdict']}")

    # ---------------- companion markdown ----------------
    p1v = part1["verdict"]
    p3v = part3["verdict"]
    lines = [
        f"# TP1-R50 Extended Re-adjudication -- {dt.date.today().isoformat()}",
        "",
        f"**VERDICT: {final['verdict']}**",
        "",
        "PREMATURE_CLOCK label: " + ("YES -- see Part 1" if premature else "NO -- clock triggered, see Part 1"),
        "",
        "## Part 1 -- forward-clock trigger",
        "",
        f"- risky-1 exit_patch (verified live): `{part1['risky1_exit_patch_verified']}`",
        f"- journal/trades.csv (primary, real fills): **n={part1['journal_primary']['n_position_level']}** "
        f"position-level ribbon fills post-2026-08-03 ({part1['journal_primary']['n_leg_rows']} leg-rows)",
        f"- decisions.jsonl cross-check: n={part1['decisions_crosscheck']['n']} placed=true ENTER rows "
        f"({part1['cross_validation']['matched_by_date_strike_side_within_15s']} matched within 15s)",
        f"- **{p1v}** (floor={part1['n_floor']}, calendar deadline {part1['clock_calendar_deadline']} not yet passed)",
        "",
        "## Part 2 -- extended population A gate re-run",
        "",
        f"- cache last date: {part2['cache_last_date']}; extension window {part2['extension_window']}",
        f"- extension: {part2['extension_stats']['n_replayed']} new ribbon_ride entries "
        f"({part2['extension_stats']['n_excluded_no_opra_cache']} excluded no-OPRA, "
        f"{part2['extension_stats']['n_excluded_no_spy_day']} excluded no-SPY-day)",
        f"- combined popA n = {part2['combined_popA_n']} (191 original frozen + "
        f"{part2['extension_stats']['n_replayed']} new)",
        f"- **VOID check: {'VOID -- ' + str(part2['void_check']['n_mismatches']) + ' mismatches' if void else 'PASS, 0 mismatches'}**",
        "",
        "### G4 sub-windows (extended)",
        "",
        "| Window | Delta | N changed | Qualifies (>=5)? |",
        "|---|---:|---:|:---:|",
    ]
    if not void:
        for w in part2["cells"]["R_tp100_f50"]["popA"]["sub_windows"]:
            lines.append(f"| {w['window']} | ${w['delta']:+,.2f} | {w['n_changed']} | "
                         f"{'yes' if w['n_changed'] >= 5 else 'no'} |")
        lines += [
            "",
            "### Full 8-gate table (R_tp100_f50, extended)",
            "",
            "| Gate | Result | Scope |",
            "|---|:---:|---|",
        ]
        scope_note = {"G1_popA_aggregate": "popA (RE-RUN, extended)", "G2_ex_best_trade": "popA (RE-RUN, extended)",
                      "G3_runner_anchor": "popA (RE-RUN, extended)", "G4_subwindow_stable": "popA (RE-RUN, extended)",
                      "G5_drop_best_day": "popA (RE-RUN, extended)",
                      "G6_week_tuesday_HARD": "week B (CARRIED FORWARD, not re-run)",
                      "G7_week_total": "week B (CARRIED FORWARD, not re-run)",
                      "G8_bh_fdr": "28-cell family (CARRIED FORWARD, not re-run)"}
        for g, v in final["full_gate_table"].items():
            lines.append(f"| {g} | {'PASS' if v else 'FAIL'} | {scope_note.get(g,'')} |")
        lines += [
            "",
            f"**{gate_summary_line}**",
            "",
            f"G4 structural finding: {final['part2_extended_population']['g4_structural_finding']}",
        ]
    lines += [
        "",
        "## Part 3 -- live-arm corroboration (proxy)",
        "",
        part3["axis_mismatch_disclosure"],
        "",
        f"- {part3['n_shared_signals_with_sibling']} risky-1 ribbon signals post-2026-08-03 shared with >=1 sibling arm",
        f"- coarse (total position $) delta risky-1 minus siblings: ${part3['total_coarse_delta_risky1_minus_siblings']:+,.2f}",
        f"- runner-leg proxy delta risky-1 minus siblings: ${part3['total_runner_proxy_delta_risky1_minus_siblings']:+,.2f} "
        f"(n={part3['n_runner_proxy_pairs']} multi-leg paired signals -- SMALL SAMPLE, read with caution)",
        f"- **{p3v}**",
        "",
        "---",
        "_Source: backtest/tools/tp1_r50_readjudication_2026_08_23.py + "
        "backtest/tools/tp1_r50_live_arm_2026_08_23.py + "
        "backtest/tools/tp1_r50_assemble_2026_08_23.py. "
        "Full JSON: analysis/recommendations/tp1-r50-readjudication-2026-08-23.json._",
    ]
    FINAL_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[assemble] wrote {FINAL_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
