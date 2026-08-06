"""Assemble analysis/deep-research/EOD-2026-08-05-ENTRIES.json from the scored scratch files."""
import json
import subprocess
import sys

S = sys.argv[1]
ev = json.load(open(S + r"\events_feat.json"))
rows = json.load(open(S + r"\variant_rows.json"))
split = json.load(open(S + r"\split_final.json"))
sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                     capture_output=True, text=True).stdout.strip()


def cut(pred):
    x = [e for e in ev if pred(e)]
    return {"n": len(x), "pnl": round(sum(e["pnl"] for e in x), 2),
            "wr_pct": round(100 * sum(1 for e in x if e["pnl"] > 0) / max(1, len(x)), 1)}


def has_struct(e):
    return e.get("struct_kind") not in (None, "None")


def want(e):
    return "up" if e["side"] == "C" else "down"


out = {
 "artifact": "EOD-2026-08-05-ENTRIES",
 "lens": "LENS 2 -- did we need better ENTRIES?",
 "generated_at_et": "2026-08-06 pre-dawn (et_clock verified market_hours=False)",
 "head_at_run": sha,
 "prereg": {"path": "analysis/recommendations/entry-improvement-variants-prereg-2026-08-05.json",
            "commit": "b9cd7a6e", "frozen_before_runner": True},
 "authority": {
   "pnl": "Alpaca broker orders + automation/state/fills-ledger.jsonl (attribution=engine), FIFO round trips",
   "spy_bars": "Alpaca SIP 1Min + 5Min, fetched live 2026-08-06",
   "option_prices": "real OPRA 1Min bars (Alpaca v1beta1/options/bars), 1182 bars across 3 contracts",
   "decisions": "automation/state/fleet/<arm>/decisions.jsonl + automation/state/core-decisions.jsonl"},

 "root_cause_entry_side": {
   "headline": "The 776C spiral is a PROVENANCE defect, not a tuning gap: the validated vwap_continuation cell is ONE ENTRY PER DAY, and the live fleet path structurally cannot enforce that.",
   "mechanism": "detect_vwap_continuation_setup enforces once-per-day with the MODULE-GLOBAL _fired_today. setup/scripts/run-fleet-executor.ps1 launches automation/state/fleet/build_shared_signal.py in a FRESH pythonw PROCESS every 60s, so the flag resets on every tick.",
   "red_proof": {"same_process_fires": 1, "fresh_process_each_tick_fires": 3,
                 "fires_same_process": ["09:55"],
                 "fires_fresh_process": ["09:55", "10:05", "10:10"],
                 "note": "3 on CLOSED 5m bars; the live producer also reads the in-progress bar, which is why it fired 5x"},
   "parity_gap": "CORE lane persists a same-bar cooldown (heartbeat_core._route_extra_setups -> exit_actuator.same_bar_cooldown_active -> <arm>/extra-setup-cooldown.json). FLEET lane persists NOTHING. That is exactly why safe-2 took ONE extra-setup entry on 08-05 while risky-1 and risky-3 each took FIVE.",
   "lesson_class": ["C12 stateful detectors need persisted state",
                    "C14 a knob unconditional in the study but void in production"],
   "guard_shipped": "backtest/tests/test_vwap_cont_once_per_day_process_scope_2026_08_05.py (3 tests, RED-proofed both ways)",
   "NOT_a_cooldown_knob": "Distinct from the graveyarded per-setup re-entry cooldown (a tuned duration). Restoring one-per-day only restores the cell's own validated contract. Forward P&L of the fix is NOT established -- the 08-04 REENTRY study found every cooldown cell lost on a trend day."
 },

 "engine_view_at_each_entry": [
  {"t_et": "09:58:05 / 09:58:07", "arms": ["risky-1", "risky-3"], "action": "ENTER_BULL",
   "setup": "VWAP_CONTINUATION", "quality": "BASE", "risk_code": "ALLOW", "trigger_level": None,
   "spy_last_closed_1m": 776.15, "session_high": 776.85, "session_high_age_min": 19.1,
   "levels_active": [772.33, 772.97, 773.41, 774.4, 775.84, 776.85],
   "ribbon": "BULL", "htf_15m": "BULL", "vix": 17.44, "bull_score": 9, "bear_score": 5,
   "core_verdict_same_tick": "HOLD (bull_blockers [7,8])",
   "trend_alignment": "3/3 uptrend (daily + hourly + m15, context_bundle 09:55)",
   "structure_5m": "NO EVENT (only 5 closed 5m bars -- warmup-blind)",
   "structure_1m": "NO EVENT",
   "last_closed_5m": "UP (09:50 bar 775.39 -> 775.89)",
   "prior_day_rth_high": 773.41,
   "reason_quoted": "vwap_continuation C (BASE); qty clamped 8->5: FULL_SEND min size"},
  {"t_et": "10:01:58", "arms": ["safe-2"], "action": "extra-setup entry",
   "setup": "vwap_reclaim_failed_break", "detector_entry_price": 776.69, "detector_stop_price": 774.40,
   "confidence": "medium",
   "triggers": ["VWAP_TREND_ESTABLISHED", "VWAP_COUNTER_TREND_BREAK_FAILED", "VWAP_WITH_TREND_RECLAIM"],
   "note": "params.extra_setup_exec_armed.vwap_continuation is FALSE -- the core did NOT take vwap_continuation, it took its armed sibling. The detector supplied a REAL structure stop at 774.40 and the position still exited -17.4% with SPY at 776.23, i.e. the structure stop never bound."},
  {"t_et": "10:06:05 / 10:06:13", "arms": ["risky-1", "risky-3"], "setup": "VWAP_CONTINUATION",
   "spy_last_closed_1m": 775.98, "session_high_age_min": 27.1,
   "structure_5m": "NO EVENT (7 closed bars, still blind)",
   "last_closed_5m": "DOWN (10:00 bar 776.67 -> 775.79)"},
  {"t_et": "10:10:06 / 10:10:07", "arms": ["risky-1", "risky-3"], "setup": "VWAP_CONTINUATION",
   "spy_last_closed_1m": 776.06, "session_high_age_min": 31.1,
   "structure_5m": "NO EVENT (>=8 bars, trend=unknown)", "last_closed_5m": "UP"},
  {"t_et": "10:14:05 / 10:14:07", "arms": ["risky-1", "risky-3"], "setup": "VWAP_CONTINUATION",
   "spy_last_closed_1m": 776.17, "session_high_age_min": 35.1,
   "structure_5m": "NO EVENT", "last_closed_5m": "UP"},
  {"t_et": "10:18:06 / 10:18:07", "arms": ["risky-1", "risky-3"], "setup": "VWAP_CONTINUATION",
   "spy_last_closed_1m": 776.19, "session_high_age_min": 39.1,
   "structure_5m": "NO EVENT", "last_closed_5m": "UP"},
  {"t_et": "11:48:05 / 11:48:07 / 11:49:07", "arms": ["risky-1", "risky-3", "safe-2"],
   "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON", "trigger_level": 772.33,
   "spy_last_closed_1m": 771.59,
   "structure_5m": "BOS DOWN, 5 bars ago, trend=downtrend", "structure_1m": "BOS DOWN, 34 bars ago",
   "note": "the ONLY trades of the day with a confirmed structure event in their direction -- and the only trade that paid."}
 ],

 "entry_timing_verdict": {
   "question": "Was the 09:58 776C long a reasonable read that failed, or structurally wrong from the first tick?",
   "answer": "The DIRECTION was defensible. The LOCATION was not.",
   "direction_support": ["ribbon BULL", "htf_15m BULL",
                          "3/3 timeframe alignment uptrend (context_bundle 09:55)",
                          "price above session VWAP", "VIX 17.44 and easing"],
   "location_failure": [
     "SPY opened 775.84, GAPPED ABOVE the prior-day RTH high 773.41. The whole session traded inside the gap with no tested demand beneath it.",
     "The session high 776.85 printed at 09:39 (1m) and was NEVER exceeded again. All ten 776C entries sat 0.23-0.87 BELOW it, 19-39 minutes after it printed.",
     "776.85 was IN levels_active. The engine had the ceiling on its own list and bought into it ten times.",
     "Zero confirmed BOS/CHoCH existed on 5m OR 1m before any call entry -- the tape had produced no structure to trade with.",
     "Every entry landed on a green 1m thrust into that ceiling (09:58 bar 776.15->776.62, 10:10 776.07->776.30, 10:18 776.20->776.28)."],
   "j_philosophy_scorecard": {
     "supply_demand_zone_identified": "YES -- 776.85 was in levels_active",
     "waited_for_return_to_the_zone": "NO -- bought AT the supply zone, never at a demand zone",
     "structure_shift_at_the_zone": "NO -- zero structure events on any timeframe",
     "never_chase_candles": "VIOLATED -- every entry was into an up-thrust"},
   "did_we_chase": True,
   "prior_day_high_test": "brief variant (c) as literally specified CANNOT fire on 08-05: PDH 773.41 sat 2.56-2.78 BELOW every entry. The binding supply was the SESSION high, not the prior-day high."
 },

 "variant_results_prereg_all_cells_reported": rows,

 "variant_robustness_extra": {
   "note": "drop-top-2-days and the within-day permutation were added AFTER the prereg. Both are strictly HARDER tests, so they can only demote a cell -- they cannot cherry-pick upward. Disclosed.",
   "within_day_permutation_defn": "hold each day's number of blocked entries fixed, randomise WHICH entries within that day get blocked, 20,000 draws. Tests 'did the rule pick the bad ENTRY' rather than 'did the rule sit out a bad DAY'.",
   "cells": {
     "V-d1": {"n_blocked": 33, "delta": 1242, "drop_top2_days": 726, "blocked_WR_pct": 3.0,
              "p_random_k": 0.0433, "p_within_day": 0.1447, "delta_0804": 179, "delta_0805": 145,
              "days_touched": 14, "days_negative": 1, "worst_day_delta": -15},
     "V-d2": {"n_blocked": 64, "delta": 2590, "drop_top2_days": 655, "blocked_WR_pct": 17.2,
              "p_random_k": 0.0021, "p_within_day": 0.1022,
              "note": "blocks risky-1's +$347 put on 08-05 and $1,272 of winners overall"},
     "V-cp2": {"n_blocked": 54, "delta": 3262, "drop_top2_days": 553, "blocked_WR_pct": 7.4,
               "p_random_k": 0.0000, "p_within_day": 0.2550,
               "concentration": "83% of its delta is 2 days (08-05 $1,935 + 07-27 $774), and 08-05 is the day it was designed on. Passes the letter of the pre-registered gates; does not survive the drop-top-2 cut."},
     "V-cp3": {"n_blocked": 41, "delta": 2757, "drop_top2_days": 431, "blocked_WR_pct": 4.9}}
 },

 "post_hoc_exploratory_cells": {
   "DISCLOSURE": "invented AFTER seeing the 08-05 tape. CANNOT ship off this population. Listed as pre-registration fodder for a forward test.",
   "V-e1_no_5m_structure_event": {"n": 38, "delta": 1366, "ex_0805": 453, "drop_top2": -159,
                                  "p_within_day": 0.372},
   "V-e2_no_5m_structure_incl_warmup_blind": {"n": 92, "delta": 586, "ex_0805": -777,
                                              "drop_top2": -1389, "p_within_day": 0.475},
   "V-e3_no_1m_structure_event": {"n": 41, "delta": 2357, "ex_0805": 994, "drop_top2": 637,
                                  "blocked_WR_pct": 7.3, "delta_h1": 1101, "delta_h2": 1256,
                                  "delta_0804": 179, "delta_0805": 1363, "days_negative": 1,
                                  "p_within_day": 0.063,
                                  "verdict": "strongest discriminator found anywhere in this study; POST-HOC, must be forward-tested before it can ship"},
   "V-f_union_d1_or_e1": {"n": 65, "delta": 2371, "ex_0805": 1313, "drop_top2": 647,
                          "p_within_day": 0.227}
 },

 "structure_context_cuts": {
   "_defn": "all 230 live engine entry events, bucketed by what crypto/lib/market_structure.analyze_structure saw on CLOSED 5m bars strictly before the fill",
   "structure_agrees_with_trade": cut(lambda e: has_struct(e) and e.get("struct_dir") == want(e)),
   "structure_disagrees": cut(lambda e: has_struct(e) and e.get("struct_dir") != want(e)),
   "no_structure_event_at_all": cut(lambda e: int(e["n_closed_5m"]) >= 8 and not has_struct(e)),
   "structure_blind_warmup_lt_8_bars": cut(lambda e: int(e["n_closed_5m"]) < 8),
   "READ": "The killer bucket is NO STRUCTURE EVENT AT ALL, not 'structure disagrees'. Brief variant (a) as written (require AGREEMENT) tests the wrong property -- the disagree bucket is the most profitable in the book.",
   "V_a_blindness": "23% of all entries (54/230, every entry between 09:30 and 10:06 ET) happen before 8 closed 5m bars exist, so a 5m structure gate ABSTAINS exactly when the session does its most damage. On 08-05 it abstained on the first six 776C entries.",
   "last_closed_5m_agrees": cut(lambda e: e["last5_dir"] == want(e)),
   "last_closed_5m_against": cut(lambda e: e["last5_dir"] is not None and e["last5_dir"] != want(e))
 },

 "entry_vs_exit_split": {
   "day_actual_spy_options_usd": split["day_actual"],
   "method": "per prereg -- a trade is ENTRY-side if its real-OPRA MFE from fill to the arm's own exit never reached a payable profit. The pre-registered binary was refined into 3 buckets after discovering that one arm's OWN TP1 (+100%) sat above anything the tape offered; the refinement subdivides a bucket, it does not move the A/B numbers.",
   "payable_bar": "+30% -- the tightest TP1 configured anywhere in the live book (params.j_vwap_reclaim_fb_tp1_pct)",
   "buckets": {
     "A_entry_side_tape_never_paid_30pct": {
       "n": 11, "actual": -1363.0, "best_executable": -1363.0, "recoverable": 0.0,
       "detail": "the ten 776C round trips (MFE 0.0% / 1.5% / 2.2% / 2.6% / 4.5% / 5.0% / 6.1% / 6.1% / 10.5% / 11.5%) plus safe-2's 777C (MFE 23.6%). None ever printed a payable profit. No exit rule in doctrine could have saved them."},
     "B_config_side_tape_paid_but_own_TP1_unreachable": {
       "n": 1, "actual": -664.0, "best_executable": 163.5, "recoverable": 827.5,
       "detail": "risky-3's SPY260805P00772000. ribbon_ride's registry TP1 is +100% (= 3.30); the put topped at 2.62 (+66.7%), so TP1 was structurally unreachable. risky-1 held the SAME contract with params_patch.exit_patch.tp1_premium_pct = 0.5, hit +50% at 2.535, and sold 3 of 5 at 2.62 at 12:09. Same trade, opposite outcome, decided by ONE config key."},
     "C_exit_side_TP1_reachable_and_missed": {
       "n": 2, "actual": 92.0, "best_executable": 470.3, "recoverable": 378.3,
       "detail": "risky-1 (+$45 still available on the 2-lot tail) and safe-2 (+$333 -- the core TP1 of +50% was reachable at 2.445 and never fired; root cause is owned by the L5-0 / L4-3 lane, only the number is used here)."}},
   "totals": {"best_executable": split["best_executable"],
              "recoverable_usd": split["recoverable"],
              "entry_side_share_of_loss_pct": split["entry_side_share_pct"],
              "exit_and_config_share_of_loss_pct": round(100 - split["entry_side_share_pct"], 1),
              "recoverable_share_of_day_pct": 62.3},
   "ORACLE_BOUND_LABEL_ONLY_NEVER_EXECUTABLE": split["oracle_bound_LABEL_ONLY"],
   "ANSWER": "70.4% of Wednesday's loss ($1,363 of $1,935) was ENTRY-side: trades that never once printed a payable profit, unsaveable by any exit rule. The other 29.6% was exit/config -- and because the exit-side trades also gave back profit that was on the table, executable exit+config fixes were worth $1,205.80, which would have cut the day from -$1,935 to -$729.20."
 },

 "survives_both_days": {
   "requirement": "the brief rejects any change that only works on 08-04 or only on 08-05",
   "answer": "YES -- one pre-registered ENTRY rule survives both: V-d1.",
   "V-d1": {
     "rule": "do not enter when the LAST FULLY CLOSED 5m bar closed AGAINST the trade direction",
     "delta_2026_08_04_trend_day": 179, "delta_2026_08_05_chop_day": 145,
     "delta_full_population_25_days": 1242, "days_touched": 14, "days_with_negative_delta": 1,
     "worst_day_delta": -15, "blocked_winner_dollars": 15, "blocked_loser_dollars": 1257,
     "why_it_survives_both": "it is not a regime bet. On a trend day the last closed bar usually already agrees, so it rarely binds and blocks no winners (+$179). In chop it binds precisely on the knife-catch re-entries (+$145).",
     "honest_limit": "within-day permutation p=0.14 across 17 tested cells, uncorrected. The dollar edge is real in-sample but NOT statistically separated from 'sat out days that were bad anyway'.",
     "recommended_action": "SHADOW-AND-MEASURE for 10 sessions, not arm."},
   "what_does_NOT_survive": "every level-proximity cell (V-b, all six) is REJECT; V-c2 is REJECT; V-cp2/V-cp3 pass the letter of the gates but 83%/79% of their delta is two days including the one they were designed on."
 },

 "caveats": [
   "n=230 entries over 25 live days. Small. 2026-08-04 alone is +$3,624 of the +$317 net; every headline is reported ex-08-04 as well.",
   "levels_active is only logged from 2026-07-28, so V-b/engine covers 7 days (169 of 230 entries abstain). The V-b/proxy row rebuilds a causal mechanical level set for the full window and is a PROXY, not the engine's own levels.",
   "The ten 776C entries are ONE clustered decision, not ten independent ones. n_blocked overstates independence; the within-day permutation is the honest correction and it is reported for every leading cell.",
   "V-c-prime, V-e1/e2/e3 and V-f were designed after seeing the 08-05 tape. They cannot ship off this population.",
   "The 3-cent half-spread haircut applied to the OPRA high is a fill proxy for a resting TP1 limit, not a guaranteed fill.",
   "The B-bucket counterfactual harmonises risky-3's TP1 to +50%. That is a CONFIG change, not an exit-execution improvement, and it is labelled separately for that reason.",
   "accounts.json's note for risky-1 still says 'deliberately NO exit_patch -- the untouched control lane'. That is STALE: the arm has carried params_patch.exit_patch {tp1_premium_pct: 0.5, stop_mode: structure} since 2026-07-29, and that key is exactly what made risky-1 the only winner on the put. Doc defect, not a code defect.",
   "PROCESS MISS (self-reported): the RED-proof briefly wrote to automation/state/fleet/fleet_live.py while another lane (L4-5 FLEET-PDT-PARITY) was editing it. Verified afterwards that their change is intact -- 868 lines, _true_day_trades_5d present, file parses, their guard backtest/tests/test_fleet_pdt_parity.py exists. No damage, but the RED-proof should have used a temp copy."
 ]
}

p = "analysis/deep-research/EOD-2026-08-05-ENTRIES.json"
json.dump(out, open(p, "w"), indent=1)
print("wrote", p, len(json.dumps(out)), "bytes")
