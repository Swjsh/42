"""money_retest_entry_variant_report.py -- builds the final machine-readable JSON companion
to retest-entry-variant.md from the stats pass + the $0.50 sensitivity run. Read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"

stats = json.loads((OUT_DIR / "retest-entry-variant-stats.json").read_text(encoding="utf-8"))

report = {
    "hypothesis": ("H10 RETEST ENTRY: replace breakout-tick entry with a retest-of-trigger-zone "
                   "entry (trigger_level +/- zone_width, <=30min, 1m close-back confirmation) "
                   "for RIDE_THE_RIBBON, on all actual engine entries since 2026-08-06."),
    "stamp_et": "2026-09-03T10:24 ET",
    "generated_et": "2026-09-03T11:00 ET",
    "verdict": "INCONCLUSIVE",
    "verdict_reason": (
        "Sign of the aggregate dollar effect flips between the two zone-width assumptions "
        "tested ($0.30 default: -$2,850.30 net; $0.50 sensitivity: +$954.60 net). Neither "
        "point estimate clears a 95% bootstrap CI. No historical key-levels.json zone-width "
        "archive exists to resolve which value is realistic."
    ),
    "n_comparable": stats["n_comparable"],
    "n_total_candidate_orders": 125,
    "n_matched_engine_fill": 122,
    "n_excluded_today_live": 8,
    "n_excluded_no_trigger_level": 5,
    "n_excluded_data_gap_2026_08_07": stats["n_excluded_data_gap"],
    "primary_zone_width": 0.30,
    "primary": {
        "actual_total_pnl": stats["actual_total_pnl"],
        "retest_total_pnl": stats["retest_total_pnl"],
        "net_effect": round(stats["retest_total_pnl"] - stats["actual_total_pnl"], 2),
        "n_confirmed_retest_taken": stats["n_confirmed_retest_taken"],
        "n_not_taken": stats["n_not_taken"],
        "n_invalidated": stats["n_invalidated"],
        "n_timeout": stats["n_timeout"],
        "actual_wr": stats["actual_wr"],
        "actual_pf": stats["actual_pf"],
        "retest_wr_of_taken": stats["retest_wr_of_taken"],
        "retest_pf_of_taken": stats["retest_pf_of_taken"],
        "bootstrap_mean_diff_per_trade_95ci": stats["bootstrap_mean_diff_per_trade"],
        "n_missed_winners": stats["n_missed_winners"],
        "missed_winners_actual_pnl_sum": stats["missed_winners_actual_pnl_sum"],
        "n_saved_losers": stats["n_saved_losers"],
        "saved_losers_actual_pnl_sum": stats["saved_losers_actual_pnl_sum"],
        "by_arm": stats["by_arm"],
        "by_vix_regime": stats["by_vix_regime"],
        "big_winner_days": stats["big_winner_days"],
        "concentration": stats["concentration"],
    },
    "sensitivity_zone_width_050": {
        "actual_total_pnl": 3619.20,
        "retest_total_pnl": 4573.80,
        "net_effect": 954.60,
        "n_confirmed_retest_taken": 83,
        "wr_of_taken": 0.4578313253012048,
        "pf_of_taken": 1.7286601879878922,
        "bootstrap_mean_diff_per_trade_95ci": [9.267961165048543, -14.54271844660194, 32.355825242718446],
        "n_missed_winners": 6,
        "missed_winners_actual_pnl_sum": 1555.45,
        "n_saved_losers": 14,
        "saved_losers_actual_pnl_sum": -1632.00,
        "day_2026_08_28_delta": 147.00,
        "day_2026_08_27_delta": -783.80,
    },
    "kills_winners": {
        "zone_width_030": (
            "YES, severely -- 08-28 flips +2,662.60 actual to -420.00 retest (only 2/9 signals "
            "confirmed a retest within 30min); 08-27 cut -41% (+3,359.80 -> +1,967.60); "
            "missed-winners sum ($5,951.60) exceeds the entire actual book total."
        ),
        "zone_width_050": (
            "Materially mitigated, not eliminated -- 08-28 delta flips to +147.00 (8/9 "
            "confirmed); 08-27 still -783.80 (8/12 confirmed)."
        ),
    },
    "fidelity_caveat": (
        "walk_exit_manager magnitude-fidelity PASSES only for safe-2 "
        "(WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md, aggregate_ratio 0.96). "
        "bold-2/risky-1/safe-3 dollars are SIGN-ONLY (magnitude FAILs, ratios 1.72-6.44x). "
        "risky-3 untested by that anchor -- SIGN-ONLY, unverified. Only 5/103 rows are on the "
        "magnitude-trusted arm."
    ),
    "look_ahead_risk": (
        "None identified. Retest decision walks 1-min SPY bars strictly after the trigger "
        "tick; ribbon EMAs are causal; structure-stop uses only already-closed 5-min bars per "
        "production code; retest entry price uses only the option bar at/after the "
        "confirmation instant. The zone-width VALUE is a disclosed modeling assumption, not a "
        "temporal leak."
    ),
    "change_class": "KILL_TYPE_REDUCTION",
    "proposed_change": (
        "NONE. Do not ship live or to shadow. Recommend: (1) start persisting historical "
        "key-levels.json zone widths (or stamp the in-force zone width onto each decision row "
        "at trigger time) so this hypothesis can be replayed on real inputs; (2) if a decision "
        "is needed sooner, run a pre-registered zone-width grid (0.20/0.30/0.40/0.50/0.75) "
        "with the decision rule fixed before results are read."
    ),
    "method_summary": (
        "Both the actual breakout entry and the (when confirmed) retest entry are walked "
        "through the SAME production exit code (backtest/lib/exit_manager_walk.walk_exit_manager "
        "-> automation/state/fleet/exit_manager.py plan_exit_actions), same exit shape "
        "(ribbon_ride), same trigger_level/qty/time_stop -- isolating the entry-TIMING change "
        "from the exit model. Simulated-vs-simulated, not simulated-vs-real-fill (22/82 "
        "(arm,symbol) groups have ambiguous same-day re-entry sell-fill attribution)."
    ),
    "data_sources": [
        "automation/state/core-decisions.jsonl",
        "automation/state/fleet/safe-3/decisions.jsonl",
        "automation/state/fleet/risky-1/decisions.jsonl",
        "automation/state/fleet/risky-3/decisions.jsonl",
        "automation/state/fleet/safe-1/decisions.jsonl",
        "automation/state/fills-ledger.jsonl",
        "backtest/data/spy_5m_2026-05-19_2026-09-02.csv",
        "backtest/data/spy_sip_cache/spy_1m_*.json",
        "backtest/data/options/*.csv",
        "backtest/data/highres/*.csv",
        "automation/state/params.json",
        "automation/state/aggressive/params.json",
        "automation/state/fleet/strategies.py",
        "backtest/lib/exit_manager_walk.py",
        "automation/state/fleet/exit_manager.py",
        "analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md",
        "automation/state/key-levels.json (read-only, today only, to characterize plausible zone-width range)",
    ],
    "artifacts": {
        "script_primary": "backtest/tools/money_retest_entry_variant.py",
        "script_stats": "backtest/tools/money_retest_entry_variant_stats.py",
        "raw_entries": "analysis/deep-research/2026-09-03-money/retest-entry-variant-raw-entries.json",
        "walked_primary_030": "analysis/deep-research/2026-09-03-money/retest-entry-variant-walked.json",
        "walked_sensitivity_050": "analysis/deep-research/2026-09-03-money/retest-entry-variant-walked-zw0.50.json",
        "stats_primary_030": "analysis/deep-research/2026-09-03-money/retest-entry-variant-stats.json",
        "report_md": "analysis/deep-research/2026-09-03-money/retest-entry-variant.md",
    },
}

out = OUT_DIR / "retest-entry-variant.json"
out.write_text(json.dumps(report, indent=1), encoding="utf-8")
print("wrote", out)
