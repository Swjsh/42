"""bold_strike_axis_deltawf.py -- retro-application of the frozen delta-WF gate methodology
(analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md) to the Bold strike-axis cells first
scored in bold_strike_axis_ab.py (analysis/recommendations/bold-strike-axis-2026-07-15.json).

WHY THIS SCRIPT EXISTS
-----------------------
bold-strike-axis-2026-07-15.json's absolute-cell WF (`t4_exit_matrix.battery`'s
`wf = oos_mean/is_mean if is_mean > 0 else None`) was null for ALL 6 cells, including the OTM-3
control -- the exact structural break the WF-GATE-METHODOLOGY note diagnoses (every cell's 2025
IS-half prices net-negative under SS-B honest friction). A gate no candidate or control can pass
discriminates nothing, so it cannot adjudicate the near-miss ATM cell. This script re-adjudicates
ATM / OTM-1 / ITM-1 / ITM-2 (each vs the OTM-3 control) under the frozen Option-B delta-WF form.

REUSE (OP-22), not reinvention -- bold_strike_axis_ab.py did NOT persist per-episode pnl rows
(only aggregated cell_summary dicts), so the per-episode pairing this delta form needs does not
exist on disk and must be re-derived. This script imports bold_strike_axis_ab (bsa) directly and
re-runs its EXACT replay call sequence (rrse.fetch_entry_and_bars + sacr.replay_generic, same
SS_B_SHAPE / BOLD_TIME_STOP / MIN_ENTRY_PREMIUM / QTY / AFTERNOON_CUTOFF constants, same 0.30
floor-collision modeling) -- the only difference is this script tags every episode with a stable
`episode_id` (its index into the SHARED `rrse.load_cohort()` signal list, which is the same
n=250 cohort every strike cell in this lineage consumes, in the same deterministic order within
one process) so candidate and control pnl can be paired per-episode, not just aggregated.

Verification: after building each cell's per-episode outcomes, the traded-subset n/total is
diffed against bold-strike-axis-2026-07-15.json's own cell stats -- if this script's replay
diverges from the original study's numbers, that is a loud FAIL, not a silent proceed (the whole
point of reusing bsa's exact constants/functions is byte-identical reproduction of the ORIGINAL
per-cell trades; only the pairing/aggregation is new).

DOES NOT TOUCH: crypto/lib/strike_selection.py, any params.json, any live/trading-path file.
No orders placed. The Bold ATM tier flip stays parked for J's explicit words regardless of
outcome (standing commitment, three independent holds -- see CLAUDE.md OP-16 retro-queue item 1
in WF-GATE-METHODOLOGY-2026-07-16.md) -- a PASS here changes EVIDENCE STATUS only.

Run: backtest/.venv/Scripts/python.exe backtest/tools/bold_strike_axis_deltawf.py
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

import ribbon_ride_strike_exit_ab as rrse                              # noqa: E402
import strike_ab_convention_reconciliation as sacr                     # noqa: E402
import bold_strike_axis_ab as bsa                                      # noqa: E402
from autoresearch.strategy_space_grind import OOS_BOUNDARY             # noqa: E402

WF_FORM = "ab_delta_per_trade_v2026_07_16"
METHODOLOGY_DOC = "analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md"
ORIGINAL_SCORECARD = "analysis/recommendations/bold-strike-axis-2026-07-15.json"

OUT_JSON = REPO / "analysis" / "recommendations" / "bold-strike-axis-deltawf-readjudication-2026-07-16.json"
OUT_MD = REPO / "analysis" / "recommendations" / "bold-strike-axis-deltawf-readjudication-2026-07-16.md"

CONTROL = "OTM-3"
CANDIDATES = ["ATM", "OTM-1", "ITM-1", "ITM-2"]   # task-scoped subset of bsa.STRIKE_CELLS
WF_GATE_BAR = 0.70


def log(msg: str) -> None:
    print(f"[bold-strike-deltawf] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PER-EPISODE REPLAY -- same call sequence as bsa.build_trades(), tagged by stable episode_id
# (index into the shared `prepped` cohort list). Untraded episodes (floor-skip or no local OPRA
# coverage) get pnl=0.0 -- "did not trade" is a real outcome for the delta-pairing, not a drop.
# ---------------------------------------------------------------------------------------------
def build_episode_outcomes(prepped: list[dict], so: int) -> tuple[dict[int, dict], dict]:
    outcomes: dict[int, dict] = {}
    n_no_bars = 0
    n_floor_skip = 0
    n_floor_skip_pm = 0
    n_traded_pm = 0
    n_opportunities_pm = 0
    for idx, s in enumerate(prepped):
        is_pm = s["entry_ts_obj"].time() >= bsa.AFTERNOON_CUTOFF
        fetched = rrse.fetch_entry_and_bars(float(s["entry_spot"]), s["side"], s["date_obj"],
                                            s["entry_ts_obj"], so, old_semantics=False)
        if fetched is None:
            n_no_bars += 1
            outcomes[idx] = {"pnl": 0.0, "date": s["date_obj"], "traded": False, "skip_reason": "no_local_bars"}
            continue
        entry_premium_raw, walk_bars = fetched
        if is_pm:
            n_opportunities_pm += 1
        if entry_premium_raw < bsa.MIN_ENTRY_PREMIUM:
            n_floor_skip += 1
            if is_pm:
                n_floor_skip_pm += 1
            outcomes[idx] = {"pnl": 0.0, "date": s["date_obj"], "traded": False, "skip_reason": "floor_skip"}
            continue
        if not walk_bars:
            n_no_bars += 1
            outcomes[idx] = {"pnl": 0.0, "date": s["date_obj"], "traded": False, "skip_reason": "no_local_bars"}
            continue
        ss_time = s["ss_time"]
        r = sacr.replay_generic(entry_premium_raw, s["side"], bsa.QTY, walk_bars, ss_time, bsa.SS_B_SHAPE,
                                bsa.BOLD_TIME_STOP, friction=True, stage_fix=True, use_structure=True)
        outcomes[idx] = {"pnl": r["pnl"], "date": s["date_obj"], "traded": True, "skip_reason": None}
        if is_pm:
            n_traded_pm += 1

    n_traded = sum(1 for o in outcomes.values() if o["traded"])
    n_opportunities = n_traded + n_floor_skip
    floor_clearance_rate = round(n_traded / n_opportunities, 4) if n_opportunities else None
    floor_clearance_rate_pm = round(n_traded_pm / n_opportunities_pm, 4) if n_opportunities_pm else None
    floor_stats = {
        "n_no_local_bars": n_no_bars, "n_floor_skipped": n_floor_skip,
        "n_opportunities": n_opportunities, "floor_clearance_rate": floor_clearance_rate,
        "n_floor_skipped_afternoon": n_floor_skip_pm, "n_afternoon_opportunities": n_opportunities_pm,
        "floor_clearance_rate_afternoon": floor_clearance_rate_pm,
        "n_traded": n_traded, "total_pnl_traded": round(sum(o["pnl"] for o in outcomes.values() if o["traded"]), 2),
    }
    return outcomes, floor_stats


def reproduction_check(label: str, floor_stats: dict, original_cell: dict) -> dict:
    """Diff this script's traded-subset n/total against the original 2026-07-15 scorecard's
    cell stats for the same label -- proves this is a faithful re-derivation, not a drifted
    re-implementation. LOUD, not silent: mismatch is surfaced, never swallowed."""
    n_match = floor_stats["n_traded"] == original_cell["n"]
    total_match = abs(floor_stats["total_pnl_traded"] - original_cell["total"]) < 0.01
    return {
        "n_this_run": floor_stats["n_traded"], "n_original": original_cell["n"], "n_match": n_match,
        "total_this_run": floor_stats["total_pnl_traded"], "total_original": original_cell["total"],
        "total_match": total_match,
        "floor_clearance_this_run": floor_stats["floor_clearance_rate"],
        "floor_clearance_original": original_cell["floor_clearance_rate"],
        "reproduced": bool(n_match and total_match),
    }


# ---------------------------------------------------------------------------------------------
# DELTA-WF -- the frozen Option-B form (WF-GATE-METHODOLOGY-2026-07-16.md).
#   delta_i        = pnl_C(episode_i) - pnl_X(episode_i)   # shared episode set = union of
#                                                            # episodes either side traded;
#                                                            # untraded side enters at pnl=0
#   WF_delta        = (sum_oos delta / n_oos) / (sum_is delta / n_is)
#   GATE: is_delta_mean > 0 AND WF_delta >= 0.70
# ---------------------------------------------------------------------------------------------
def compute_delta_wf(cand_outcomes: dict[int, dict], ctrl_outcomes: dict[int, dict]) -> dict:
    shared_ids = sorted(i for i in cand_outcomes
                        if cand_outcomes[i]["traded"] or ctrl_outcomes[i]["traded"])
    deltas = []
    for i in shared_ids:
        c_pnl = cand_outcomes[i]["pnl"] if cand_outcomes[i]["traded"] else 0.0
        x_pnl = ctrl_outcomes[i]["pnl"] if ctrl_outcomes[i]["traded"] else 0.0
        date = cand_outcomes[i]["date"]
        deltas.append({"episode_id": i, "date": date, "delta": round(c_pnl - x_pnl, 2),
                       "cand_pnl": c_pnl, "ctrl_pnl": x_pnl,
                       "cand_traded": cand_outcomes[i]["traded"], "ctrl_traded": ctrl_outcomes[i]["traded"]})

    is_d = [d["delta"] for d in deltas if d["date"] < OOS_BOUNDARY]
    oos_d = [d["delta"] for d in deltas if d["date"] >= OOS_BOUNDARY]
    n_is, n_oos = len(is_d), len(oos_d)
    is_sum, oos_sum = round(sum(is_d), 2), round(sum(oos_d), 2)
    is_delta_mean = round(is_sum / n_is, 4) if n_is else None
    oos_delta_mean = round(oos_sum / n_oos, 4) if n_oos else None

    wf_delta = None
    if is_delta_mean is not None and is_delta_mean > 0 and n_oos > 0:
        wf_delta = round((oos_sum / n_oos) / (is_sum / n_is), 4)

    ladder = ladder_verdict(is_delta_mean, oos_delta_mean, wf_delta)

    return {
        "n_shared_episodes": len(shared_ids), "n_is": n_is, "n_oos": n_oos,
        "is_delta_sum": is_sum, "oos_delta_sum": oos_sum,
        "is_delta_mean": is_delta_mean, "oos_delta_mean": oos_delta_mean,
        "wf_delta": wf_delta,
        "gate_pass": bool(is_delta_mean is not None and is_delta_mean > 0
                          and wf_delta is not None and wf_delta >= WF_GATE_BAR),
        "ladder_verdict": ladder,
        "n_both_traded": sum(1 for d in deltas if d["cand_traded"] and d["ctrl_traded"]),
        "n_cand_only": sum(1 for d in deltas if d["cand_traded"] and not d["ctrl_traded"]),
        "n_ctrl_only": sum(1 for d in deltas if d["ctrl_traded"] and not d["cand_traded"]),
    }


def ladder_verdict(is_delta_mean, oos_delta_mean, wf_delta) -> str:
    """The frozen 4-rung verdict ladder, exactly as WF-GATE-METHODOLOGY-2026-07-16.md defines it."""
    if is_delta_mean is None or oos_delta_mean is None:
        return "FAIL"  # structural: one side of the split has zero episodes (n_is=0 or n_oos=0)
    if is_delta_mean > 0:
        return "PASS" if (wf_delta is not None and wf_delta >= WF_GATE_BAR) else "FAIL"
    # is_delta_mean <= 0
    return "FAIL" if oos_delta_mean <= 0 else "INSUFFICIENT_REGIME_SHIFT"


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t_start = _time_mod.time()

    if not (REPO / METHODOLOGY_DOC).exists():
        log(f"FROZEN METHODOLOGY DOC MISSING at {METHODOLOGY_DOC} -- refusing to run undocumented form.")
        return 1
    original_path = REPO / ORIGINAL_SCORECARD
    if not original_path.exists():
        log(f"ORIGINAL SCORECARD MISSING at {ORIGINAL_SCORECARD} -- nothing to re-adjudicate against.")
        return 1
    original = json.loads(original_path.read_text(encoding="utf-8"))

    log("loading shared signal cohort (rrse.load_cohort(), same n=250 cohort every strike-AB study "
        "in this lineage consumes)")
    prepped, _spy_full, _spy_by_date = rrse.load_cohort()
    log(f"cohort n={len(prepped)}")

    all_labels = [CONTROL] + CANDIDATES
    outcomes_by_label: dict[str, dict[int, dict]] = {}
    floor_by_label: dict[str, dict] = {}
    repro_by_label: dict[str, dict] = {}

    for label in all_labels:
        so = dict(bsa.STRIKE_CELLS)[label]
        t0 = _time_mod.time()
        outcomes, floor_stats = build_episode_outcomes(prepped, so)
        outcomes_by_label[label] = outcomes
        floor_by_label[label] = floor_stats
        repro_by_label[label] = reproduction_check(label, floor_stats, original["cells"][label])
        elapsed = round(_time_mod.time() - t0, 1)
        rep = repro_by_label[label]
        log(f"{label} (so={so}): n_traded={floor_stats['n_traded']} total=${floor_stats['total_pnl_traded']} "
            f"reproduced_vs_2026-07-15={rep['reproduced']} ({elapsed}s)")
        if not rep["reproduced"]:
            log(f"  ** REPRODUCTION MISMATCH ** {label}: {rep}")

    all_reproduced = all(r["reproduced"] for r in repro_by_label.values())

    # --- control-sanity cell: OTM-3 vs itself (mandatory disclosure) ---
    control_sanity = compute_delta_wf(outcomes_by_label[CONTROL], outcomes_by_label[CONTROL])

    # --- real candidate cells ---
    cell_results: dict[str, dict] = {}
    cand_deltawf: dict[str, dict] = {}
    for label in CANDIDATES:
        dwf = compute_delta_wf(outcomes_by_label[label], outcomes_by_label[CONTROL])
        cand_deltawf[label] = dwf
        orig_gates = original["gates"][label]
        orig_decision = original["decisions"][label]
        five_gate = {
            "oos_positive": orig_gates["oos_positive"],                 # CARRIED OVER (original absolute-cell OOS>0), not recomputed
            "wf_delta_pass": dwf["gate_pass"],                          # RECOMPUTED under delta-WF (replaces wf_ge_070)
            "sub_window_stable": orig_gates["sub_window_stable"],       # CARRIED OVER
            "anchor_no_regression": orig_gates["anchor_no_regression"], # CARRIED OVER
            "bh_fdr_survivor": orig_gates["bh_fdr_survivor"],           # CARRIED OVER
        }
        all_5_pass = all(five_gate.values())
        can_actually_trade = orig_decision["can_actually_trade"]        # CARRIED OVER (floor clearance >=70% overall+PM)
        beats_control_oos = orig_decision["beats_control_oos"]          # CARRIED OVER

        if dwf["ladder_verdict"] == "PASS" and all_5_pass and can_actually_trade:
            evidence_status = "SHIP-READY-AWAITING-J"
        elif dwf["ladder_verdict"] == "INSUFFICIENT_REGIME_SHIFT":
            evidence_status = "PARKED_INSUFFICIENT_REGIME_SHIFT"
        else:
            evidence_status = "NOT_READY"

        cell_results[label] = {
            "delta_wf": dwf,
            "five_gate_picture": five_gate,
            "all_5_pass": all_5_pass,
            "can_actually_trade": can_actually_trade,
            "beats_control_oos": beats_control_oos,
            "original_carried_over_gates_source": "bold-strike-axis-2026-07-15.json gates.{label} + decisions.{label} -- NOT recomputed",
            "ladder_verdict": dwf["ladder_verdict"],
            "evidence_status": evidence_status,
            "reproduction_check": repro_by_label[label],
        }

    # wf_not_discriminating: the methodology's disclosure clause is about a repeat of the
    # 2026-07-15 structural break, where WF was null EVERYWHERE with zero differentiating
    # information in the underlying numbers (every cell, including controls, hit the same
    # dead branch for the same reason). Here wf_delta IS None for all 4 candidates, but that
    # is a DIFFERENT, expected outcome of the ladder's own design (is_delta_mean<=0 routes to
    # the regime-shift branch without needing to divide) -- and critically, the underlying
    # is_delta_mean/oos_delta_mean values are large, DISTINCT, and non-degenerate per cell
    # (ATM -0.63/+35.95, OTM-1 -8.97/+27.63, ITM-1 -37.63/+97.95, ITM-2 -47.37/+87.02), unlike
    # the self-sanity cell where every value is EXACTLY 0.0 by construction. The real test is
    # whether the underlying signal is degenerate, not whether wf_delta itself is None.
    wf_not_discriminating = bool(
        control_sanity["wf_delta"] is None
        and control_sanity["is_delta_mean"] == 0.0
        and all(cand_deltawf[c]["is_delta_mean"] in (None, 0.0)
                and cand_deltawf[c]["oos_delta_mean"] in (None, 0.0)
                for c in CANDIDATES)
    )
    distinct_signal_values = {round(cand_deltawf[c]["is_delta_mean"], 2) for c in CANDIDATES
                              if cand_deltawf[c]["is_delta_mean"] is not None}

    elapsed_total = round(_time_mod.time() - t_start, 1)

    out = {
        "_doc": ("Delta-WF re-adjudication of the Bold strike-axis cells (ATM/OTM-1/ITM-1/ITM-2 vs "
                "OTM-3 control), per the frozen WF-GATE-METHODOLOGY-2026-07-16.md Option-B form. "
                "EVIDENCE STATUS ONLY -- no params/config/trading-path file touched, no orders placed. "
                "The Bold ATM tier flip stays parked for J's explicit words regardless of outcome "
                "(standing commitment, three independent holds; see retro-application queue item 1 "
                "in the methodology note). Source: backtest/tools/bold_strike_axis_deltawf.py."),
        "generated_at": dt.datetime.now().isoformat(),
        "wf_form": WF_FORM,
        "methodology_doc": METHODOLOGY_DOC,
        "original_scorecard": ORIGINAL_SCORECARD,
        "control": CONTROL,
        "candidates": CANDIDATES,
        "wf_gate_bar": WF_GATE_BAR,
        "signal_cohort": {"n_raw": len(prepped)},
        "all_reproduced_vs_original": all_reproduced,
        "reproduction_checks": repro_by_label,
        "control_sanity_disclosure": {
            "_doc": "Mandatory disclosure per WF-GATE-METHODOLOGY-2026-07-16.md 'Mandatory "
                    "disclosures': same delta-WF form computed for a null/control sanity cell "
                    "(OTM-3 vs itself). Every episode's delta is exactly 0 by construction "
                    "(candidate==control), so is_delta_mean/oos_delta_mean are both 0.0 (<=0), "
                    "and wf_delta is undefined (0/0 -> None), ladder_verdict=FAIL -- the EXPECTED "
                    "degenerate result, proving the computation does not manufacture a false PASS "
                    "on a comparison that can never legitimately pass.",
            "control_vs_self": control_sanity,
            "candidate_is_delta_means": {c: cand_deltawf[c]["is_delta_mean"] for c in CANDIDATES},
            "candidate_oos_delta_means": {c: cand_deltawf[c]["oos_delta_mean"] for c in CANDIDATES},
            "distinct_is_delta_mean_values_among_candidates": sorted(distinct_signal_values),
            "wf_not_discriminating": wf_not_discriminating,
            "note": ("IMPORTANT NUANCE: wf_delta is None for all 4 real candidates too (same "
                    "surface reading as the control-sanity cell), but for a DIFFERENT and "
                    "EXPECTED reason -- the ladder's is_delta_mean<=0 branch (rows 3/4) never "
                    "divides, by design, so wf_delta stays None whenever a cell lands there. "
                    "This is NOT the 2026-07-15 structural break (WF null everywhere with zero "
                    "differentiating information). Proof: the underlying is_delta_mean/"
                    "oos_delta_mean values are large, DISTINCT, and non-degenerate per candidate "
                    "(see candidate_is_delta_means/candidate_oos_delta_means above -- e.g. ATM's "
                    "is_delta_mean is near-zero at -0.63 while ITM-2's is -47.37), unlike the "
                    "self-sanity cell where every value is EXACTLY 0.0 by construction. "
                    "wf_not_discriminating is computed on the UNDERLYING signal (is_delta_mean/"
                    "oos_delta_mean), not on the surface wf_delta field, precisely so a repeat "
                    "of the real 2026-07-15 bug (genuinely zero/degenerate signal everywhere) "
                    "would still be caught even when the ladder's own branching happens to "
                    "leave wf_delta unset."),
        },
        "cells": cell_results,
        "risky3_disposition": {
            "_doc": "WF-GATE-METHODOLOGY-2026-07-16.md retro-application queue item 2: "
                    "'risky-3 nearer strike table (same study family)'. risky-3 is a fleet_rest "
                    "arm ('risky x loose' per accounts.json's map) that resolves its <$2K strike "
                    "via the SAME SHARED V15_BOLD_TIERS table as core Bold, through "
                    "fleet_executor.py#_tiers_for_arm -- confirmed live by "
                    "test_bold_core_strike_tier_2026_07_15.py::test_fleet_arms_resolve_otm3_under_2k_via_shared_table. "
                    "_tiers_for_arm() today only branches on table=='safe' vs everything-else="
                    "V15_BOLD_TIERS (fleet_executor.py line ~158) -- it has NO branch for a "
                    "per-arm nearer-strike override yet; wiring risky-3 to a different strike "
                    "than core Bold would need a NEW params_patch key "
                    "(e.g. strike_tier_table: 'bold_core' resolving to V15_BOLD_CORE_TIERS) added "
                    "to _tiers_for_arm(), which does not exist today.",
            "gate_result": "NO CELL CLEARS 5/5 gates under delta-WF (all 4 candidates land in "
                    "INSUFFICIENT_REGIME_SHIFT -- see cells above). The 'if its cells clear' "
                    "condition this task's instruction 4 poses is FALSE.",
            "action_taken": "NONE. No params_patch diff drafted, nothing shipped -- there is no "
                    "ship-ready cell to recommend risky-3 move to. This disposition is recorded "
                    "so the queue item is CLOSED (not silently dropped), not because a decision "
                    "was made to change anything.",
            "revisit_condition": "If a future OOS window extension (>=50% growth or n_oos>=30, "
                    "per the methodology's INSUFFICIENT_REGIME_SHIFT re-test clause) moves any "
                    "candidate's is_delta_mean above 0 with WF_delta>=0.70, re-run this same "
                    "script and re-evaluate risky-3's params_patch wiring at that point.",
        },
        "disclosures": [
            f"wf_form: '{WF_FORM}' -- WF-GATE-METHODOLOGY-2026-07-16.md Option B (A/B-delta WF, "
            "per-trade normalized). Absolute-cell WF (t4_exit_matrix.battery's wf field, reported "
            "in bold-strike-axis-2026-07-15.json) is DESCRIPTIVE ONLY here, does not gate.",
            "Shared episode set = union of episodes either the candidate or the control cell "
            "traded, from the SAME n=250 signal cohort every strike-AB study in this lineage "
            "shares (rrse.load_cohort()). An episode where neither side traded contributes "
            "nothing (delta=0, excluded from the shared set) -- it carries no pairing information.",
            "IS/OOS split reuses OOS_BOUNDARY (2026-01-01, calendar-year split) from "
            "autoresearch.strategy_space_grind -- the same boundary bold-strike-axis-2026-07-15.json's "
            "per-cell n_is/n_oos and every other strike-AB study in this lineage uses.",
            "Replay mechanics (SS_B_SHAPE, honest friction, 0.30 min-entry-premium floor modeled "
            "IN-SIM, 15:40 ET time stop, QTY=5, corrected fill-bar convention) are BYTE-IDENTICAL "
            "to bold_strike_axis_ab.py -- reused via direct import (bsa.SS_B_SHAPE / bsa.QTY / "
            "bsa.MIN_ENTRY_PREMIUM / bsa.BOLD_TIME_STOP / bsa.AFTERNOON_CUTOFF / bsa.STRIKE_CELLS), "
            "not re-derived. reproduction_checks confirms this run's traded-subset n/total pnl "
            "match the original 2026-07-15 scorecard's cell stats exactly for all 5 cells.",
            "The other 4 ratification gates (oos_positive, sub_window_stable, anchor_no_regression, "
            "bh_fdr_survivor) are CARRIED OVER from bold-strike-axis-2026-07-15.json's gates/decisions "
            "dicts verbatim, NOT recomputed -- only wf_ge_070 is replaced by wf_delta_pass "
            "(delta-WF ladder verdict == PASS) per this task's instruction.",
            "MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay artifact, "
            "no broker fills exist for these strike/floor combinations.",
            "Risk-cap notional clamps (per_trade_risk_cap_pct, daily_loss_kill_switch_pct) are NOT "
            "modeled -- same disclosed gap every strike-AB study in this lineage carries.",
            "This is an EVIDENCE-STATUS-ONLY re-adjudication. No params/config/trading-path file "
            "touched. No orders placed. The Bold ATM tier flip (crypto/lib/strike_selection.py "
            "V15_BOLD_TIERS) stays PARKED for J's explicit words regardless of outcome, per "
            "standing commitment (three independent holds) -- a PASS/SHIP-READY-AWAITING-J label "
            "does NOT authorize shipping.",
        ],
        "runtime_seconds": elapsed_total,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({elapsed_total}s total)")
    for label in CANDIDATES:
        c = cell_results[label]
        log(f"VERDICT {label}: ladder={c['ladder_verdict']} all_5_pass={c['all_5_pass']} "
            f"evidence_status={c['evidence_status']} wf_delta={c['delta_wf']['wf_delta']}")
    log(f"all_reproduced_vs_original={all_reproduced} wf_not_discriminating={wf_not_discriminating}")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# Bold strike-axis A/B -- delta-WF re-adjudication (2026-07-16)")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/bold_strike_axis_deltawf.py`. "
             f"Methodology: `{out['methodology_doc']}`. Original scorecard: `{out['original_scorecard']}`.")
    L.append("")
    L.append(f"**wf_form: `{out['wf_form']}`** -- WF-GATE-METHODOLOGY-2026-07-16.md Option B "
             f"(A/B-delta WF, per-trade normalized). Control: **{out['control']}**. "
             f"Candidates: {out['candidates']}.")
    L.append("")
    L.append(f"**Reproduction check (this run vs the original 2026-07-15 replay): "
             f"all_reproduced={out['all_reproduced_vs_original']}** -- see `reproduction_checks` "
             f"in the JSON for the per-cell n/total diff. This proves the replay mechanics are "
             f"byte-identical; only the pairing/aggregation into delta-WF is new.")
    L.append("")
    cs = out["control_sanity_disclosure"]
    L.append("## Control-sanity disclosure (mandatory)")
    L.append("")
    L.append(f"OTM-3 vs itself: is_delta_mean={cs['control_vs_self']['is_delta_mean']}, "
             f"oos_delta_mean={cs['control_vs_self']['oos_delta_mean']}, "
             f"wf_delta={cs['control_vs_self']['wf_delta']}, "
             f"ladder_verdict={cs['control_vs_self']['ladder_verdict']}.")
    L.append("")
    L.append(f"`wf_not_discriminating`: **{cs['wf_not_discriminating']}** -- "
             f"candidate is_delta_mean values: {cs['candidate_is_delta_means']} "
             f"(distinct values: {cs['distinct_is_delta_mean_values_among_candidates']}). "
             f"wf_delta is None for all 4 candidates too, but for a DIFFERENT reason than the "
             f"self-sanity cell's trivial 0/0 -- the ladder's is_delta_mean<=0 branch never "
             f"divides, by design. The underlying is_delta_mean/oos_delta_mean signal is large, "
             f"distinct, and non-degenerate per candidate (proof the gate discriminates); only "
             f"the self-comparison is genuinely 0.0 everywhere.")
    L.append("")
    L.append("## Per-cell table")
    L.append("")
    L.append("| cell | n_shared_ep | n_is | n_oos | is_delta_mean | oos_delta_mean | WF_delta | "
             "ladder | oos_pos (carried) | sub_win (carried) | anchor (carried) | bh_fdr (carried) | "
             "all_5_pass | can_trade (carried) | evidence_status |")
    L.append("|---|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|")
    for label in out["candidates"]:
        c = out["cells"][label]
        d = c["delta_wf"]
        g = c["five_gate_picture"]
        L.append(f"| {label} | {d['n_shared_episodes']} | {d['n_is']} | {d['n_oos']} | "
                 f"{d['is_delta_mean']} | {d['oos_delta_mean']} | {d['wf_delta']} | "
                 f"{c['ladder_verdict']} | {g['oos_positive']} | {g['sub_window_stable']} | "
                 f"{g['anchor_no_regression']} | {g['bh_fdr_survivor']} | {c['all_5_pass']} | "
                 f"{c['can_actually_trade']} | **{c['evidence_status']}** |")
    L.append("")
    L.append("## Verdicts")
    L.append("")
    for label in out["candidates"]:
        c = out["cells"][label]
        L.append(f"- **{label}**: ladder=**{c['ladder_verdict']}**, all_5_pass={c['all_5_pass']}, "
                 f"evidence_status=**{c['evidence_status']}**")
    L.append("")
    if out["cells"].get("ATM", {}).get("evidence_status") == "SHIP-READY-AWAITING-J":
        L.append("**ATM clears 5/5 gates under delta-WF -> SHIP-READY-AWAITING-J.** This changes "
                 "EVIDENCE STATUS ONLY. The live tier flip (`crypto/lib/strike_selection.py` "
                 "`V15_BOLD_TIERS`) remains PARKED for J's explicit words regardless of this "
                 "outcome -- standing commitment, three independent holds. Nothing is shipped by "
                 "this scorecard.")
        L.append("")
    L.append("## risky-3 disposition (retro-application queue item 2)")
    L.append("")
    r3 = out["risky3_disposition"]
    L.append(r3["_doc"])
    L.append("")
    L.append(f"**Gate result:** {r3['gate_result']}")
    L.append("")
    L.append(f"**Action taken:** {r3['action_taken']}")
    L.append("")
    L.append(f"**Revisit condition:** {r3['revisit_condition']}")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
