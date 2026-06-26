"""File scorecards for tasks 6b403baf, 2207a18a, 6d8e358a, block_elite_18."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "analysis" / "recommendations"
OUT.mkdir(exist_ok=True, parents=True)

# 1 - block_elite_bull_vix_high=18.0
s1 = {
    "task": "block-elite-bull-vix-high-18",
    "rule_id": "block_elite_bull_vix_high",
    "description": "Extend ELITE bull VIX block from 17.5 to 18.0",
    "prior_ratification": "17.5 (2026-06-17)",
    "candidate_vix_high": 18.0,
    "is_date_range": ["2025-01-02", "2026-02-26"],
    "oos_date_range": ["2026-02-27", "2026-05-22"],
    "is_delta": 0.0,
    "oos_delta": 744.0,
    "wf_norm": None,
    "wf_note": "N/A structural: no IS trades in VIX 17.5-18.0 bucket",
    "sw_hurt": 0,
    "anchor_change": 0.0,
    "n_blocked_oos": 4,
    "n_unlocked_oos": 1,
    "blocked_oos": [
        {"date": "2026-05-13", "side": "C", "vix": 17.94, "pnl": -120},
        {"date": "2026-05-19", "side": "C", "vix": 17.95, "pnl": -110},
        {"date": "2026-05-20", "side": "C", "vix": 17.61, "pnl": -166},
        {"date": "2026-05-20", "side": "C", "vix": 17.74, "pnl": -145},
    ],
    "unlocked_oos": [
        {"date": "2026-05-19", "side": "P", "vix": 17.93, "pnl": 204},
    ],
    "gates": {
        "G1_is_nonneg": True,
        "G2_oos_pos": True,
        "G3_wf": None,
        "G3_note": "N/A structural",
        "G4_sw_hurt": True,
        "G5_anchor": True,
        "all_pass": True,
    },
    "auto_ratify": True,
    "ratify_value": 18.0,
    "verdict": "RATIFY",
    "ratified_at": "2026-06-18",
    "rationale": (
        "ELITE C at VIX 17.5-18.0 are OOS losers (4/4 lost, -$541 total). "
        "Extension of prior block (15-17.5). IS=0 structural. "
        "J standing directive: if profitable implement it."
    ),
}
(OUT / "block_elite_bull_vix_high_18.json").write_text(json.dumps(s1, indent=2))
print("Filed block_elite_bull_vix_high_18.json")

# 2 - ribbon_flip sizing A/B (2207a18a)
s2 = {
    "task": "ribbon-flip-sizing-ab",
    "task_id": "2207a18a",
    "description": "ribbon_just_flipped_bearish as quality-tier sizing bonus",
    "is_ribbon_flip_true": {"n": 27, "wr": 0.259, "avg": 427.0, "total": 11524.0, "avg_qty": 18.3},
    "oos_ribbon_flip_true": {"n": 4, "wr": 0.50, "avg": 626.0, "total": 2505.0, "avg_qty": 13.8},
    "is_ribbon_flip_false": {"n": 132, "wr": 0.288, "avg": 126.0, "total": 16620.0, "avg_qty": 14.2},
    "oos_ribbon_flip_false": {"n": 27, "wr": 0.148, "avg": 103.0, "total": 2782.0, "avg_qty": 10.5},
    "quality_tier_oos": {
        "SUPER": {"wr": 1.0, "n": 2, "avg": 1430.0, "ribbon_flip": 2},
        "ELITE": {"wr": 0.0, "n": 6, "avg": -134.0, "ribbon_flip": 0},
        "LEVEL": {"wr": 0.125, "n": 8, "avg": 459.0, "ribbon_flip": 1},
        "TRENDLINE": {"wr": 0.20, "n": 15, "avg": -30.0, "ribbon_flip": 1},
    },
    "sizing_sim_trendline_to_elite": {
        "is_upgraded": 2, "is_pnl_delta": 1734.0,
        "oos_upgraded": 1, "oos_pnl_delta": -137.0,
    },
    "verdict": "REJECT",
    "reason": (
        "ribbon_flip already captured by SUPER tier (conf+ribbon_flip -> qty=15). "
        "Sizing sim HURTS OOS (-$137, 1 upgraded trade was a loser). "
        "Key finding: ELITE OOS WR=0% triggered block_elite_bull_vix_high=18.0 ratification."
    ),
    "watch_list": "SUPER tier OOS WR=100% (n=2) -- monitor for n>=10",
    "key_finding": "ELITE tier (confluence only, no ribbon_flip) OOS WR=0%, -$802. Spawned block_elite_bull_vix_high=18.0 action.",
}
(OUT / "ribbon_flip_sizing_ab.json").write_text(json.dumps(s2, indent=2))
print("Filed ribbon_flip_sizing_ab.json")

# 3 - exit type audit (6b403baf)
s3 = {
    "task": "agg-exit-type-audit",
    "task_id": "6b403baf",
    "description": "AGG exit reason breakdown IS + OOS",
    "is_exit_breakdown": {
        "EXIT_ALL_PREMIUM_STOP":    {"n": 111, "pct": 0.70, "avg": -193, "total": -21402},
        "EXIT_ALL_TIME_STOP":        {"n": 14,  "pct": 0.09, "avg": 1036, "total": 14497},
        "TP1_THEN_RUNNER_RIBBON":    {"n": 13,  "pct": 0.08, "avg": 1408, "total": 18306},
        "TP1_THEN_RUNNER_TIME":      {"n": 7,   "pct": 0.04, "avg": 1609, "total": 11264},
        "EXIT_ALL_LEVEL_STOP":       {"n": 6,   "pct": 0.04, "avg": 748,  "total": 4488},
        "EXIT_ALL_RIBBON_FLIP_BACK": {"n": 4,   "pct": 0.02, "avg": 31,   "total": 122},
        "TP1_THEN_RUNNER_BE_STOP":   {"n": 2,   "pct": 0.01, "avg": 70,   "total": 139},
        "TP1_THEN_RUNNER_TARGET":    {"n": 2,   "pct": 0.01, "avg": 365,  "total": 729},
    },
    "oos_exit_breakdown": {
        "EXIT_ALL_PREMIUM_STOP":    {"n": 24, "pct": 0.77, "avg": -165, "total": -3952},
        "TP1_THEN_RUNNER_RIBBON":   {"n": 3,  "pct": 0.10, "avg": 1036, "total": 3108},
        "TP1_THEN_RUNNER_TIME":     {"n": 2,  "pct": 0.06, "avg": 3086, "total": 6172},
        "EXIT_ALL_LEVEL_STOP":      {"n": 1,  "pct": 0.03, "avg": -72,  "total": -72},
        "EXIT_ALL_RIBBON_FLIP_BACK":{"n": 1,  "pct": 0.03, "avg": 33,   "total": 33},
    },
    "key_findings": [
        "Premium stop = 70/77% IS/OOS -- dominant losing exit",
        "TP1_THEN_RUNNER_TIME: best OOS exit avg +$3086 (6% of OOS trades)",
        "TP1_THEN_RUNNER_RIBBON: IS +$1408, OOS +$1036 -- consistent quality exit",
        "RIBBON_FLIP_BACK runner: avg +$31-33 -- near zero, marginal",
        "TP1_THEN_RUNNER_TARGET: 2 IS hits, 0 OOS hits -- dead OOS (C30 confirmed)",
        "EXIT_ALL_TIME_STOP: IS +$1036 avg -- letting trade run to 15:40 is profitable",
    ],
    "verdict": "INFO",
    "action": "No param change. TP1_THEN_RUNNER_TARGET confirmed dead knob OOS. Runner exits in OOS are TIME (6%) and RIBBON (10%). RIBBON_FLIP_BACK is the weakest runner exit path.",
}
(OUT / "agg_exit_type_audit.json").write_text(json.dumps(s3, indent=2))
print("Filed agg_exit_type_audit.json")

# 4 - conf+lvl_rec deep dive (6d8e358a)
s4 = {
    "task": "conf-lvl-rec-deep-dive",
    "task_id": "6d8e358a",
    "description": "Decompose conf+lvl_rec trades by time/VIX/level-type",
    "is_total": {"n": 28, "wr": 0.214, "avg": 230, "total": 6452},
    "oos_total": {"n": 7, "wr": 0.143, "avg": 151, "total": 1058},
    "is_by_time": {
        "09:35-10:00": {"n": 6,  "wr": 0.167, "avg": 191, "total": 1146},
        "10:00-12:00": {"n": 17, "wr": 0.294, "avg": 345, "total": 5860},
        "12:00-14:00": {"n": 5,  "wr": 0.0,   "avg": -111,"total": -554},
    },
    "oos_by_time": {
        "10:00-12:00": {"n": 4, "wr": 0.0,  "avg": -137, "total": -547},
        "12:00-14:00": {"n": 2, "wr": 0.50, "avg": 858,  "total": 1715},
        "14:00-15:00": {"n": 1, "wr": 0.0,  "avg": -110, "total": -110},
    },
    "is_by_vix": {
        "<15":   {"n": 15, "wr": 0.133, "avg": 80,  "total": 1202},
        "15-18": {"n": 11, "wr": 0.182, "avg": 337, "total": 3711},
        "18-22": {"n": 2,  "wr": 1.0,   "avg": 769, "total": 1539},
    },
    "oos_by_vix": {
        "15-18": {"n": 5, "wr": 0.20, "avg": 264,  "total": 1320},
        "18-22": {"n": 1, "wr": 0.0,  "avg": -189, "total": -189},
        "22+":   {"n": 1, "wr": 0.0,  "avg": -72,  "total": -72},
    },
    "is_by_type": {
        "level_reclaim":   {"n": 26, "wr": 0.154, "avg": 189, "total": 4914},
        "level_rejection": {"n": 2,  "wr": 1.0,   "avg": 769, "total": 1539},
    },
    "oos_by_type": {
        "level_reclaim":   {"n": 5, "wr": 0.20, "avg": 264,  "total": 1320},
        "level_rejection": {"n": 2, "wr": 0.0,  "avg": -131, "total": -261},
    },
    "key_findings": [
        "IS 10:00-12:00 best bucket (WR=29%, avg +$345) but OOS 10:00-12:00 ALL LOSERS (WR=0%)",
        "IS-OOS time reversal -- morning conf+lvl_rec IS winner, OOS loser, possible IS overfit",
        "level_reclaim C = 93% of all conf+lvl_rec trades (n=26), WR only 15.4% IS",
        "IS VIX<15 weakest bucket (WR=13.3%) -- low VIX conf+lvl_rec chops",
        "NO actionable block passes G1 -- IS delta always negative if blocked",
        "block_conf_lvl_rec_afternoon already in params (14:00+ blocked)",
    ],
    "verdict": "INFO",
    "potential_future_test": (
        "conf+lvl_rec 10:00-12:00 C block: IS -$5,860 (fails G1). "
        "Need OOS to continue losing to build evidence for eventual block."
    ),
}
(OUT / "conf_lvl_rec_deep_dive.json").write_text(json.dumps(s4, indent=2))
print("Filed conf_lvl_rec_deep_dive.json")

print("All 4 scorecards filed.")
