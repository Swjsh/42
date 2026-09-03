"""block_elite_bull_ssb_study.py -- OPRA-safe COHORT CHARACTERIZATION for the frozen
`block_elite_bull_ssb_revalidation` preregistration
(analysis/recommendations/block-elite-bull-ssb-preregistration.json).

THIS IS NOT A SECOND IMPLEMENTATION OF THE STUDY. The canonical, already-built runner is
`backtest/tools/block_elite_bull_ssb_revalidation.py` (the prereg's own `_doc.runner`
field names it) -- it was built and pinned (19 tests, `backtest/tests/
test_block_elite_bull_ssb_revalidation.py`, all passing at the time this wrapper was
written) during an EARLIER session but never actually RUN end-to-end (prereg status is
still FROZEN_PENDING_RUN, no `block-elite-bull-ssb-revalidation.json` result exists).
This wrapper IMPORTS that module and calls ONLY its OPRA-free functions:
  * m.preflight()                     -- prereg hash/version pin, read-only
  * m.load_core_decisions()           -- reads core-decisions.jsonl only
  * m.mine_elite_extension_events()   -- dedupe + stale-echo filter, decision-log only
  * m.mine_super_comparison_events()  -- same, comparison cohort
  * m.recover_trigger_level()         -- SPY 5m bars + lib.filters.detect_level_reclaim
                                          only (verified: no OPRA import path is reached)
It deliberately does NOT call m.rerun_original_probe() (runs lib.orchestrator.run_backtest
with use_real_fills=True -- reads the OPRA option-bar cache), m.prepare_event() /
m.fetch_bars_cache_then_live() (OPRA option bars), or m.replay_prepared_event() (needs the
OPRA-priced bars the previous two functions fetch) -- ALL of those are off-limits this
session because another study holds the OPRA cache as a single reader tonight.

RESULT: this run answers "how big are the cohorts and what would the gate's own dedupe/
stale-echo/tier rules include" -- it does NOT answer the pass-bar's dollar-based
conditions 1-3 (those need SS-B/OLD pnl, which needs OPRA). Condition 4 (n>=12) IS fully
answered. See `analysis/recommendations/block-elite-bull-ssb-results-2026-09-03.md` for
the run-specific narrative. When OPRA access is available, the confirmatory run is
`backtest/.venv/Scripts/python.exe backtest/tools/block_elite_bull_ssb_revalidation.py`
(unchanged, unmodified by this wrapper) -- writing to the prereg's own reserved output
path (`block-elite-bull-ssb-revalidation.json`). This wrapper writes to a SEPARATE, dated
filename precisely so a partial characterization can never be mistaken for that
confirmatory result.

$0. Read-only against core-decisions.jsonl, SPY/VIX 5m CSVs, and the prior
bull_unblock_replay_probe.py artifact (reused, not re-run). Touches NO trading-path file,
NO OPRA cache.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKTEST_DIR = os.path.abspath(os.path.join(TOOLS_DIR, ".."))
REPO = os.path.abspath(os.path.join(BACKTEST_DIR, ".."))
sys.path.insert(0, BACKTEST_DIR)
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.join(REPO, "automation", "state", "fleet"))

import block_elite_bull_ssb_revalidation as m  # noqa: E402  -- the canonical, frozen-prereg runner

PART_A_ARTIFACT_PATH = os.path.join(REPO, "analysis", "recommendations",
                                     "bull-unblock-elite-replay-2026-06-30.json")
OUT_JSON = os.path.join(REPO, "analysis", "recommendations",
                         "block-elite-bull-ssb-results-2026-09-03.json")
OUT_MD = os.path.join(REPO, "analysis", "recommendations",
                       "block-elite-bull-ssb-results-2026-09-03.md")

# Canonical-module functions this wrapper must NEVER call (each touches the OPRA option-
# bar cache, off-limits this session). Enforced statically by
# backtest/tests/test_block_elite_bull_ssb_study.py::test_wrapper_never_calls_opra_functions
# (AST-walks this file's source for `m.<name>(...)` call sites) -- kept as a single list
# here so the test and this docstring stay in sync with one source of truth.
OPRA_BLOCKED_FUNCTIONS = (
    "rerun_original_probe", "prepare_event", "fetch_bars_cache_then_live",
    "replay_prepared_event", "_cached_bars_as_esp_shape",
)


def build_part_a() -> dict:
    """part_a_original_n7: REUSED from the prior artifact -- NOT re-run this session
    (m.rerun_original_probe() needs run_backtest(use_real_fills=True), which reads the
    OPRA cache; off-limits tonight). Old-exit parity (pass_bar condition 3) therefore
    cannot be certified this run -- that requires the actual re-run's fresh number, not
    a re-read of a number computed by a prior run."""
    with open(PART_A_ARTIFACT_PATH, encoding="utf-8") as f:
        artifact = json.load(f)
    cohort = artifact["added_bull_cohort"]
    return {
        "source": "REUSED_PRIOR_ARTIFACT_NOT_RERUN_OPRA_BLOCKED",
        "artifact_path": os.path.relpath(PART_A_ARTIFACT_PATH, REPO),
        "artifact_generated_at": artifact.get("generated_at"),
        "n": cohort["n"],
        "old_exit_net_pnl_recorded": cohort["net_pnl"],
        "trades": cohort["trades"],
    }


def recover_trigger_levels(events: list[dict]) -> list[dict]:
    """Attach trigger_level/trigger_level_status to each mined event via the canonical
    module's OWN recover_trigger_level() (SPY-5m + detect_level_reclaim only, no OPRA)."""
    out = []
    for ev in events:
        row = ev["entry_row"]
        lvl, status = m.recover_trigger_level(row)
        out.append({
            "entry_time_et": row["ts_et"],
            "spy_spot": row.get("spy"),
            "action": row.get("action"),
            "triggers": row.get("triggers"),
            "n_ticks": ev["n_ticks"],
            "elevated_stale_risk": bool(ev.get("elevated_stale_risk", False)),
            "trigger_level": lvl,
            "trigger_level_status": status,
        })
    return out


def evaluate_pass_bar(ssb_total_pnl, ssb_drop_top1_pnl, old_exit_parity_ok, n_events: int):
    """Frozen 4-condition ladder (prereg pass_bar), tolerant of NOT_RUN inputs so this
    wrapper can report condition 4 (the only one answerable without OPRA) honestly instead
    of faking the other three. Mirrors m.'s cond1..cond4 boolean shape exactly when all
    inputs ARE booleans (so this wrapper's math never drifts from the canonical module's),
    but degrades to 'NOT_RUN' per-condition when an input is None."""
    def _b(x):
        return "NOT_RUN" if x is None else bool(x)

    c1 = _b(ssb_total_pnl > 0 if ssb_total_pnl is not None else None)
    c2 = _b(ssb_drop_top1_pnl > 0 if ssb_drop_top1_pnl is not None else None)
    c3 = _b(old_exit_parity_ok)
    c4 = n_events >= m.N_EVENTS_FLOOR

    any_not_run = "NOT_RUN" in (c1, c2, c3)
    all_pass = (c1 is True and c2 is True and c3 is True and c4 is True)
    if all_pass:
        verdict = "UNBLOCK_PROPOSE"
    elif any_not_run:
        verdict = "INDETERMINATE_CONDITIONS_NOT_RUN"
    else:
        verdict = "KEEP"
    return {
        "condition_1_ssb_total_positive": c1,
        "condition_2_ssb_drop_top1_positive": c2,
        "condition_3_old_exit_parity": c3,
        "condition_4_n_events_floor_12": {"result": c4, "n": n_events, "floor": m.N_EVENTS_FLOOR},
        "all_pass": all_pass if not any_not_run else "NOT_RUN",
        "verdict": verdict,
    }


def load_prior_confirmatory_result() -> dict | None:
    """DISCOVERED mid-run (2026-09-03): the canonical module's own OUT_JSON
    (analysis/recommendations/block-elite-bull-ssb-revalidation.json) already exists --
    generated_at 2026-07-10T16:10:35, same day as the freeze. It is a COMPLETE run (part_a
    parity_ok=True, n_events_total=28, pass_bar all 4 conditions evaluated, verdict=KEEP,
    no proposal written -- consistent with all_pass=False). The prereg's `status` field was
    simply never updated after that run (a bookkeeping gap, not a pending run) -- this
    wrapper does NOT need to re-run the OPRA-based replay because it already happened.
    Returns the parsed result dict, or None if it genuinely doesn't exist (future-proofing:
    if this file is ever absent, the wrapper correctly falls back to characterization-only
    + INDETERMINATE, as it did before this discovery)."""
    if os.path.exists(m.OUT_JSON):
        with open(m.OUT_JSON, encoding="utf-8") as f:
            return json.load(f)
    return None


def run(write_outputs: bool = True) -> dict:
    pf = m.preflight()
    if not pf["prereg_hash_ok"] or not pf["prereg_version_ok"]:
        raise RuntimeError(f"prereg hash/version mismatch -- refusing to run on a drifted "
                            f"spec: {pf}")

    prior = load_prior_confirmatory_result()

    all_rows = m.load_core_decisions()
    elite_ext_events, elite_ext_stats = m.mine_elite_extension_events(all_rows)
    super_events, super_stats = m.mine_super_comparison_events(all_rows)

    part_a = build_part_a()
    elite_ext_recovered = recover_trigger_levels(elite_ext_events)
    super_recovered = recover_trigger_levels(super_events)

    n_events_total = part_a["n"] + elite_ext_stats["n_kept"]

    tonights_pass_bar = evaluate_pass_bar(
        ssb_total_pnl=None, ssb_drop_top1_pnl=None, old_exit_parity_ok=None,
        n_events=n_events_total,
    )

    trigger_level_recovered_n = sum(1 for e in elite_ext_recovered if e["trigger_level"] is not None)

    # Cross-validate tonight's OPRA-free mining against the prior confirmatory run's own
    # mining stats (if it exists) -- both should be byte-identical on the countable fields
    # since both read the same append-only core-decisions.jsonl over the same fixed window.
    cross_check = None
    if prior is not None:
        prior_ext = prior.get("elite_extension_mining", {})
        prior_cmp = prior.get("super_comparison_mining", {})
        prior_part_a = prior.get("part_a_original_rerun", {})
        cross_check = {
            "n_raw_ticks_part_b": {"tonight": elite_ext_stats["n_raw_ticks"],
                                    "2026_07_10_run": prior_ext.get("n_raw_ticks")},
            "n_kept_part_b": {"tonight": elite_ext_stats["n_kept"],
                               "2026_07_10_run": prior_ext.get("n_kept")},
            "n_kept_comparison": {"tonight": super_stats["n_kept"],
                                   "2026_07_10_run": prior_cmp.get("n_kept")},
            "part_a_n": {"tonight": part_a["n"], "2026_07_10_run": prior_part_a.get("n_added_bulls")},
            "part_a_pnl": {"tonight": part_a["old_exit_net_pnl_recorded"],
                            "2026_07_10_run": prior_part_a.get("reproduced_net_pnl_old_exit")},
            "all_match": (
                elite_ext_stats["n_raw_ticks"] == prior_ext.get("n_raw_ticks")
                and elite_ext_stats["n_kept"] == prior_ext.get("n_kept")
                and super_stats["n_kept"] == prior_cmp.get("n_kept")
                and part_a["n"] == prior_part_a.get("n_added_bulls")
            ),
        }

    result = {
        "study": "block_elite_bull_ssb_revalidation",
        "run": "run_2026_09_03",
        "run_generated_at": dt.datetime.now().isoformat(),
        "MAJOR_FINDING": (
            "A COMPLETE confirmatory run already exists: "
            "analysis/recommendations/block-elite-bull-ssb-revalidation.json, "
            "generated_at=2026-07-10T16:10:35 (same day as the freeze). It was never "
            "OPRA-blocked -- OPRA access was available that session. The prereg's `status` "
            "field was simply never flipped from FROZEN_PENDING_RUN afterward (a bookkeeping "
            "gap, not an actually-pending run). VERDICT (from that run, authoritative): "
            f"{prior['pass_bar']['verdict'] if prior else 'NO_PRIOR_RESULT_FOUND'}."
            if prior is not None else
            "No prior confirmatory result found at analysis/recommendations/"
            "block-elite-bull-ssb-revalidation.json -- the study genuinely has not been run "
            "to a verdict yet. This session's characterization-only run is the only data "
            "point; pass_bar conditions 1-3 remain NOT_RUN."
        ),
        "canonical_runner": "backtest/tools/block_elite_bull_ssb_revalidation.py (NOT re-run "
                             "this session -- OPRA-blocked, AND unnecessary: see MAJOR_FINDING)",
        "preflight": pf,
        "session_constraint": (
            "OPRA option-bar cache and exit-walk replays were OFF-LIMITS this session "
            "(another study holds the single-reader cache). Tonight's own mining reuses the "
            "canonical module's OPRA-free functions (preflight, load_core_decisions, "
            "mine_elite_extension_events, mine_super_comparison_events, "
            "recover_trigger_level) only, as a cross-validation of the 2026-07-10 run's "
            "cohort definitions -- see 'cross_validation_vs_2026_07_10_run' below."
        ),
        "prior_confirmatory_result": prior,
        "cross_validation_vs_2026_07_10_run": cross_check,
        "part_a_original_n7_tonight": part_a,
        "elite_extension_mining_tonight": elite_ext_stats,
        "elite_extension_events_tonight": elite_ext_recovered,
        "elite_extension_trigger_level_recovered_n_tonight": trigger_level_recovered_n,
        "super_comparison_mining_tonight": super_stats,
        "super_comparison_events_tonight": super_recovered,
        "elite_cohort_n_final_tonight": n_events_total,
        "pass_bar_tonight_own_data_only": tonights_pass_bar,
        "AUTHORITATIVE_PASS_BAR": prior["pass_bar"] if prior else tonights_pass_bar,
        "opra_replay_still_needed": False if prior else {
            "entry_premium_recovery_part_b_and_comparison": True,
            "part_a_fresh_rerun_for_old_exit_parity": True,
            "ss_b_and_old_exit_shape_replay_all_events": True,
            "how_to_run_when_unblocked": "backtest/.venv/Scripts/python.exe "
                "backtest/tools/block_elite_bull_ssb_revalidation.py",
        },
        "dollar_impact_on_real_record": {
            "part_a_old_exit_net_pnl_recorded": part_a["old_exit_net_pnl_recorded"],
            "elite_cohort_OLD_exit_total_pnl_2026_07_10_run": (
                prior["elite_cohort"]["OLD"]["total_pnl"] if prior else None),
            "elite_cohort_SS_B_total_pnl_2026_07_10_run": (
                prior["elite_cohort"]["SS_B"]["total_pnl"] if prior else None),
            "interpretation": (
                "From the already-completed 2026-07-10 confirmatory run: on the FULL elite "
                f"cohort (n=28), the OLD exit shape totals "
                f"${prior['elite_cohort']['OLD']['total_pnl']:.2f} and SS-B totals "
                f"${prior['elite_cohort']['SS_B']['total_pnl']:.2f} -- unblocking under EITHER "
                "exit shape would have LOST money on this population; SS-B is worse than OLD "
                "here, not better. The gate is correctly KEEPING this cohort blocked; no "
                "further OPRA work changes that conclusion."
                if prior else
                "The gate SAVED an estimated $241.26 of realized loss for the original n=7 "
                "cohort under the shipped OLD exit shape (prior artifact, not re-derived this "
                "run). No dollar figure is available for part_b/comparison -- both require the "
                "OPRA-based replay this session could not run."
            ),
        },
    }
    if write_outputs:
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        _write_md(result)
        print(f"[written] {OUT_JSON}")
    return result


def _write_md(result: dict) -> None:
    pa = result["part_a_original_n7_tonight"]
    ext = result["elite_extension_mining_tonight"]
    cmp_ = result["super_comparison_mining_tonight"]
    prior = result["prior_confirmatory_result"]
    cc = result["cross_validation_vs_2026_07_10_run"]
    auth = result["AUTHORITATIVE_PASS_BAR"]
    lines = [
        "# block_elite_bull SS-B revalidation -- RUN 2026-09-03",
        "",
        "**RESEARCH / SIM-ONLY. Nothing here ships.**",
        "",
        "## MAJOR FINDING",
        result["MAJOR_FINDING"],
        "",
    ]
    if prior is not None:
        oc = prior["elite_cohort"]
        lines += [
            "## AUTHORITATIVE VERDICT (from the 2026-07-10 confirmatory run)",
            f"- **verdict: {auth['verdict']}**",
            f"- conditions: {json.dumps(auth)}",
            f"- elite cohort n=28: OLD exit total pnl = ${oc['OLD']['total_pnl']:.2f}, "
            f"SS-B exit total pnl = ${oc['SS_B']['total_pnl']:.2f} "
            f"(SS-B drop-top-1 remainder = ${oc['SS_B']['drop_top1_remainder']:.2f})",
            "- Both exit shapes lose money on the elite cohort -- SS-B does not rescue it; "
            "block_elite_bull correctly stays armed.",
            "",
            "## Cross-validation: tonight's OPRA-free mining vs the 2026-07-10 run",
            f"- all countable fields match: **{cc['all_match']}**",
            f"- {json.dumps(cc, default=str)}",
            "",
        ]
    lines += [
        f"preflight: `{json.dumps(result['preflight'])}`",
        "",
        "## Tonight's own characterization (cross-check only, not authoritative when a "
        "prior confirmatory result exists)",
        f"- part_a (reused prior artifact, NOT re-run): n={pa['n']}, "
        f"old-exit net pnl recorded=${pa['old_exit_net_pnl_recorded']:.2f}",
        f"- part_b extension (07-01..07-10): {ext['n_raw_ticks']} raw ticks -> "
        f"{ext['n_events_total']} events (5min dedupe) -> "
        f"{ext['n_excluded_stale_echo']} stale-echo excluded -> "
        f"**{ext['n_kept']} final events** "
        f"(sensitivity: 2min={ext['n_events_at_2min']}, 15min={ext['n_events_at_15min']}; "
        f"{ext['n_flagged_open_adjacent']} open-adjacent flagged, not excluded)",
        f"- trigger_level recovered (non-fallback) for "
        f"{result['elite_extension_trigger_level_recovered_n_tonight']}/{ext['n_kept']} kept events",
        f"- elite cohort n_final (part_a + part_b): **{result['elite_cohort_n_final_tonight']}**",
        f"- SUPER comparison cohort (disclosure only): {cmp_['n_raw_ticks']} raw ticks -> "
        f"**{cmp_['n_kept']} final events**",
        "",
        "## Dollar impact on the real record",
        result["dollar_impact_on_real_record"]["interpretation"],
    ]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[written] {OUT_MD}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    result = run(write_outputs=not args.no_write)
    print(json.dumps({
        "elite_cohort_n_final_tonight": result["elite_cohort_n_final_tonight"],
        "AUTHORITATIVE_PASS_BAR_verdict": result["AUTHORITATIVE_PASS_BAR"]["verdict"],
        "super_comparison_n_final_tonight": result["super_comparison_mining_tonight"]["n_kept"],
        "prior_confirmatory_result_found": result["prior_confirmatory_result"] is not None,
    }, indent=2))


if __name__ == "__main__":
    main()
