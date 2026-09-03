"""
H8 LOSS-SIZE MATH -- scratch analysis script, read-only on all inputs.
Writes analysis/deep-research/2026-09-03-money/loss-size-math.{md,json}

Inputs (all cached, all local, no network):
  analysis/pain-ledger/mae-mfe.json     -- n=394 scored positions, MAE/MFE per position
  automation/state/core-decisions.jsonl -- VIX ticks (account=safe/bold) for regime join
  automation/state/hypotheses-settled.json -- prior settled stop-width hypothesis (cite, don't redo)

No writes to automation/state/** or journal/**. No network calls.
"""
import json
import random
import statistics
from collections import defaultdict, Counter

random.seed(20260903)

REPO = "C:/Users/jackw/Desktop/42"

with open(f"{REPO}/analysis/pain-ledger/mae-mfe.json") as f:
    LEDGER = json.load(f)

TRADES = LEDGER["trades"]
N_ALL = len(TRADES)

# ---------------------------------------------------------------------------
# 1. VIX regime join: date_et -> median VIX that day, from core-decisions.jsonl
#    (account=='safe' ticks; VIX is a market quantity, not account-specific,
#    so this date-level median is applied to ALL arms including fleet arms
#    whose own decisions.jsonl carries vix=None throughout -- verified below).
# ---------------------------------------------------------------------------
vix_by_date = defaultdict(list)
with open(f"{REPO}/automation/state/core-decisions.jsonl") as f:
    for line in f:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("account") != "safe":
            continue
        v = d.get("vix")
        ts = d.get("ts_et")
        if v is None or not ts:
            continue
        date = ts[:10]
        vix_by_date[date].append(v)

vix_median_by_date = {d: statistics.median(vs) for d, vs in vix_by_date.items()}

def regime_of(date):
    v = vix_median_by_date.get(date)
    if v is None:
        return "UNKNOWN_no_vix_row"
    if v < 15:
        return "VIX<15"
    if v <= 17:
        return "VIX15-17"
    return "VIX>17"

n_dates_no_vix = len({t["date"] for t in TRADES} - set(vix_median_by_date.keys()))

# ---------------------------------------------------------------------------
# 2. Per-trade derived fields
# ---------------------------------------------------------------------------
def enrich(t):
    notional = t["entry_price"] * t["qty"] * 100.0
    exit_pct = (t["realized_pnl"] / notional) if notional else 0.0
    cap_pct = t["stop"]["premium_stop_pct"]  # as-configured cap for THIS trade (negative)
    r_unit = notional * abs(cap_pct) if cap_pct else notional * 0.5
    r_multiple = (t["realized_pnl"] / r_unit) if r_unit else 0.0
    t["_notional"] = notional
    t["_exit_pct"] = exit_pct
    t["_r_multiple"] = r_multiple
    t["_regime"] = regime_of(t["date"])
    return t

for t in TRADES:
    enrich(t)

CURRENT_CAP_COHORT = [t for t in TRADES if t["stop"]["premium_stop_pct"] == -0.5]
LEGACY_COHORT = [t for t in TRADES if t["stop"]["premium_stop_pct"] != -0.5]

# ---------------------------------------------------------------------------
# 3. Bootstrap helper
# ---------------------------------------------------------------------------
def bootstrap_ci(values, stat_fn, n_resamples=3000):
    if not values:
        return (float("nan"), float("nan"), float("nan"))
    n = len(values)
    point = stat_fn(values)
    boots = []
    for _ in range(n_resamples):
        sample = [values[random.randrange(n)] for _ in range(n)]
        boots.append(stat_fn(sample))
    boots.sort()
    lo = boots[int(0.025 * n_resamples)]
    hi = boots[int(0.975 * n_resamples) - 1]
    return (point, lo, hi)

def sum_stat(vals):
    return sum(vals)

def mean_stat(vals):
    return statistics.mean(vals) if vals else 0.0

def pf_stat(pnls):
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses == 0:
        return float("inf") if wins > 0 else float("nan")
    return wins / losses

def wr_stat(outcomes_bin):
    # outcomes_bin: list of 0/1 (1=winner)
    return sum(outcomes_bin) / len(outcomes_bin) if outcomes_bin else float("nan")

# ---------------------------------------------------------------------------
# 4. Overall / cohort-level summary stats
# ---------------------------------------------------------------------------
def summarize(trades, label):
    n = len(trades)
    winners = [t for t in trades if t["outcome"] == "winner"]
    losers = [t for t in trades if t["outcome"] == "loser"]
    scratches = [t for t in trades if t["outcome"] == "scratch"]
    pnls = [t["realized_pnl"] for t in trades]
    win_pnls = [t["realized_pnl"] for t in winners]
    loss_pnls = [t["realized_pnl"] for t in losers]

    wr = len(winners) / n if n else float("nan")
    wr_incl_scratch_as_loss = len(winners) / n if n else float("nan")
    avg_win = statistics.mean(win_pnls) if win_pnls else 0.0
    avg_loss = statistics.mean(loss_pnls) if loss_pnls else 0.0  # negative
    avg_win_pct = statistics.mean([t["_exit_pct"] for t in winners]) if winners else 0.0
    avg_loss_pct = statistics.mean([t["_exit_pct"] for t in losers]) if losers else 0.0
    pf = pf_stat(pnls)
    total_pnl = sum(pnls)

    # break-even WR at the OBSERVED average win / average loss (dollar terms)
    if (avg_win - avg_loss) != 0 and avg_win > 0:
        breakeven_wr = abs(avg_loss) / (avg_win + abs(avg_loss))
    else:
        breakeven_wr = float("nan")

    # R-multiple summary (per-trade cap-normalized)
    r_multiples = [t["_r_multiple"] for t in trades]
    r_win = [t["_r_multiple"] for t in winners]
    r_loss = [t["_r_multiple"] for t in losers]

    total_pnl_ci = bootstrap_ci(pnls, sum_stat)
    pf_ci = bootstrap_ci(pnls, pf_stat)
    wr_ci = bootstrap_ci([1 if t["outcome"] == "winner" else 0 for t in trades], wr_stat)

    return {
        "label": label,
        "n": n,
        "n_winners": len(winners),
        "n_losers": len(losers),
        "n_scratch": len(scratches),
        "wr_observed": wr,
        "wr_ci_2.5_97.5": [wr_ci[1], wr_ci[2]],
        "avg_win_dollars": avg_win,
        "avg_loss_dollars": avg_loss,
        "avg_win_pct_of_premium": avg_win_pct,
        "avg_loss_pct_of_premium": avg_loss_pct,
        "breakeven_wr_at_observed_avg_win_loss": breakeven_wr,
        "wr_edge_over_breakeven_pp": (wr - breakeven_wr) * 100 if breakeven_wr == breakeven_wr else float("nan"),
        "profit_factor": pf,
        "pf_ci_2.5_97.5": [pf_ci[1], pf_ci[2]],
        "total_pnl": total_pnl,
        "total_pnl_ci_2.5_97.5": [total_pnl_ci[1], total_pnl_ci[2]],
        "avg_r_multiple_all": statistics.mean(r_multiples) if r_multiples else 0.0,
        "avg_r_multiple_winners": statistics.mean(r_win) if r_win else 0.0,
        "avg_r_multiple_losers": statistics.mean(r_loss) if r_loss else 0.0,
        "median_r_multiple_losers": statistics.median(r_loss) if r_loss else 0.0,
    }

overall_summary = summarize(TRADES, "ALL_394")
current_cap_summary = summarize(CURRENT_CAP_COHORT, "CURRENT_CAP_-50pct_n239")
legacy_summary = summarize(LEGACY_COHORT, "LEGACY_NON-50pct_CAP_n155")

by_arm_summary = {}
for arm in sorted({t["arm"] for t in TRADES}):
    by_arm_summary[arm] = summarize([t for t in TRADES if t["arm"] == arm], arm)

by_regime_summary = {}
for regime in ["VIX<15", "VIX15-17", "VIX>17", "UNKNOWN_no_vix_row"]:
    sub = [t for t in TRADES if t["_regime"] == regime]
    if sub:
        by_regime_summary[regime] = summarize(sub, regime)

by_regime_current_cap = {}
for regime in ["VIX<15", "VIX15-17", "VIX>17", "UNKNOWN_no_vix_row"]:
    sub = [t for t in CURRENT_CAP_COHORT if t["_regime"] == regime]
    if sub:
        by_regime_current_cap[regime] = summarize(sub, f"{regime}_CURRENT_CAP")

# ---------------------------------------------------------------------------
# 5. Derived exit-stage classification (APPROXIMATE -- no ground-truth exit-
#    reason tag exists in fills-ledger or mae-mfe.json; disclosed method):
#      cap_hit      : loser AND exit_pct <= cap_pct + 0.05 (closed at/near its
#                      configured premium/catastrophe stop)
#      tp_or_target : winner AND exit_pct >= 1.00 (>=100% gain -- ribbon_ride's
#                      hardcoded TP1 threshold per CLAUDE.md TP1 source-of-truth note)
#      small_win    : winner AND exit_pct < 1.00
#      structure_or_time_loss : loser, exit better (less negative) than cap_pct+0.05
#      scratch      : outcome==scratch
# ---------------------------------------------------------------------------
def classify_stage(t):
    if t["outcome"] == "scratch":
        return "scratch"
    cap = t["stop"]["premium_stop_pct"]
    if t["outcome"] == "loser":
        if t["_exit_pct"] <= cap + 0.05:
            return "cap_hit"
        return "structure_or_time_loss"
    if t["outcome"] == "winner":
        if t["_exit_pct"] >= 1.00:
            return "tp_or_target"
        return "small_win"
    return "other"

for t in TRADES:
    t["_stage"] = classify_stage(t)

stage_counts = Counter(t["_stage"] for t in TRADES)
stage_r = defaultdict(list)
stage_pnl = defaultdict(list)
for t in TRADES:
    stage_r[t["_stage"]].append(t["_r_multiple"])
    stage_pnl[t["_stage"]].append(t["realized_pnl"])

stage_summary = {}
for stage, cnt in stage_counts.items():
    rs = stage_r[stage]
    pnls = stage_pnl[stage]
    stage_summary[stage] = {
        "n": cnt,
        "pct_of_book": cnt / N_ALL,
        "avg_r_multiple": statistics.mean(rs) if rs else 0.0,
        "median_r_multiple": statistics.median(rs) if rs else 0.0,
        "total_pnl": sum(pnls),
        "avg_pnl": statistics.mean(pnls) if pnls else 0.0,
    }

stage_by_arm = defaultdict(lambda: defaultdict(int))
for t in TRADES:
    stage_by_arm[t["arm"]][t["_stage"]] += 1
stage_by_arm = {arm: dict(stages) for arm, stages in stage_by_arm.items()}

# ---------------------------------------------------------------------------
# 6. Candidate tighter-cap counterfactual sweep: -30% / -35% / -40% vs current -50%
#    Methodology (hindsight, descriptive, explicitly NOT a live-rule validation):
#      - Restrict to trades where mae_before_first_exit==True (the adverse
#        excursion happened while the full position was still open -- the ONLY
#        case where a stop rule could plausibly have fired on it; the prereg
#        flags the False case as hypothetical/post-partial).
#      - For candidate cap C (as a positive fraction, e.g. 0.30):
#          if mae_pct <= -C: position is assumed stopped at exactly -C (first
#            touch), counterfactual_pnl = notional * (-C)
#          else: unaffected, counterfactual_pnl = actual realized_pnl
#      - delta = counterfactual_pnl - realized_pnl
#          winner + mae breached  -> "winner_killed"  (delta always <= 0, money lost)
#          loser + mae breached, actual worse than -C  -> "loss_saved" (delta > 0)
#          loser + mae breached, actual better than -C -> "false_stop_worsened" (delta < 0)
#          not breached           -> "unaffected" (delta == 0)
#    No slippage/exact intra-bar sequencing modeled beyond the mae bar-low
#    convention already frozen in PREREG-2026-08-01.md. This is a SENSITIVITY
#    STUDY, not a live-rule validation -- explicit hindsight caveat.
# ---------------------------------------------------------------------------
CANDIDATE_CAPS = [0.30, 0.35, 0.40, 0.50]

def run_cap_sweep(trades, label):
    eligible = [t for t in trades if t.get("mae_before_first_exit") is True]
    excluded_n = len(trades) - len(eligible)
    sweep = {}
    for C in CANDIDATE_CAPS:
        rows = []
        for t in eligible:
            notional = t["_notional"]
            breached = t["mae_pct"] <= -C
            if breached:
                cf_pnl = notional * (-C)
            else:
                cf_pnl = t["realized_pnl"]
            delta = cf_pnl - t["realized_pnl"]
            if not breached:
                bucket = "unaffected"
            elif t["outcome"] == "winner":
                bucket = "winner_killed"
            elif delta > 1e-9:
                bucket = "loss_saved"
            elif delta < -1e-9:
                bucket = "false_stop_worsened"
            else:
                bucket = "unaffected_edge"
            rows.append({
                "date": t["date"], "arm": t["arm"], "symbol": t["symbol"],
                "outcome": t["outcome"], "realized_pnl": t["realized_pnl"],
                "mae_pct": t["mae_pct"], "cf_pnl": cf_pnl, "delta": delta,
                "bucket": bucket, "regime": t["_regime"],
            })
        buckets = defaultdict(list)
        for r in rows:
            buckets[r["bucket"]].append(r)

        deltas = [r["delta"] for r in rows]
        net_ci = bootstrap_ci(deltas, sum_stat)

        winner_killed = buckets["winner_killed"]
        loss_saved = buckets["loss_saved"]
        false_stop = buckets["false_stop_worsened"]

        sweep[f"cap_{int(C*100)}pct"] = {
            "candidate_cap_pct": -C,
            "n_eligible": len(eligible),
            "n_winner_killed": len(winner_killed),
            "dollars_winner_killed": sum(r["delta"] for r in winner_killed),  # negative
            "winner_killed_symbols": [f"{r['date']}/{r['arm']}/{r['symbol']}" for r in winner_killed],
            "n_loss_saved": len(loss_saved),
            "dollars_loss_saved": sum(r["delta"] for r in loss_saved),  # positive
            "n_false_stop_worsened": len(false_stop),
            "dollars_false_stop_worsened": sum(r["delta"] for r in false_stop),  # negative
            "n_unaffected": len(buckets["unaffected"]) + len(buckets["unaffected_edge"]),
            "net_dollar_effect": sum(deltas),
            "net_dollar_effect_ci_2.5_97.5": [net_ci[1], net_ci[2]],
            "big_winning_days_hit": sorted({r["date"] for r in winner_killed
                                             if r["date"] in ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")}),
        }
    return {"label": label, "n_total": len(trades), "n_excluded_mae_after_partial_exit": excluded_n, "sweep": sweep}

sweep_all = run_cap_sweep(TRADES, "ALL_394_any_configured_cap")
sweep_current = run_cap_sweep(CURRENT_CAP_COHORT, "CURRENT_CAP_-50pct_cohort_n239")

# per-regime sweep on the ALL population (net effect only, lean)
sweep_by_regime = {}
for regime in ["VIX<15", "VIX15-17", "VIX>17"]:
    sub = [t for t in TRADES if t["_regime"] == regime]
    if len(sub) >= 15:
        r = run_cap_sweep(sub, regime)
        sweep_by_regime[regime] = {k: v["net_dollar_effect"] for k, v in r["sweep"].items()}
        sweep_by_regime[regime]["n"] = len(sub)

# ---------------------------------------------------------------------------
# 7. Big-winning-day check: does ANY candidate cap touch the 4 named winning days?
# ---------------------------------------------------------------------------
BIG_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
big_day_trades = [t for t in TRADES if t["date"] in BIG_DAYS]
big_day_by_date = defaultdict(list)
for t in big_day_trades:
    big_day_by_date[t["date"]].append(t)

big_day_report = {}
for date in BIG_DAYS:
    rows = big_day_by_date.get(date, [])
    total_pnl_day = sum(t["realized_pnl"] for t in rows)
    winners = [t for t in rows if t["outcome"] == "winner"]
    detail = []
    for C in CANDIDATE_CAPS:
        breached_winners = [t for t in winners if t["mae_pct"] <= -C and t.get("mae_before_first_exit") is True]
        detail.append({
            "cap": -C,
            "n_winners_would_be_killed": len(breached_winners),
            "dollars_at_risk": sum(t["realized_pnl"] for t in breached_winners),
        })
    big_day_report[date] = {
        "n_trades_in_ledger": len(rows),
        "total_realized_pnl": total_pnl_day,
        "n_winners": len(winners),
        "cap_sweep_impact": detail,
    }

# ---------------------------------------------------------------------------
# 8. stop_inside_mae sanity check on CURRENT cap cohort (uses pain_ledger's own
#    pre-computed field, i.e. ground truth for "-50%" without our approximation)
# ---------------------------------------------------------------------------
current_cap_losers = [t for t in CURRENT_CAP_COHORT if t["outcome"] == "loser"]
n_losers_stop_inside_mae = sum(1 for t in current_cap_losers if t["stop"]["stop_inside_mae"])
current_cap_winners = [t for t in CURRENT_CAP_COHORT if t["outcome"] == "winner"]
n_winners_stop_inside_mae = sum(1 for t in current_cap_winners if t["stop"]["stop_inside_mae"])

# ---------------------------------------------------------------------------
# 9. Prior settled hypothesis (cite, don't redo)
# ---------------------------------------------------------------------------
with open(f"{REPO}/automation/state/hypotheses-settled.json") as f:
    settled = json.load(f)
prior_stop_hypothesis = next(
    (h for h in settled["settled"] if h.get("mechanism") == "stop_inside_noise_floor"), None
)

# ---------------------------------------------------------------------------
# 10. Assemble output JSON
# ---------------------------------------------------------------------------
OUT = {
    "hypothesis_id": "H8",
    "hypothesis": "LOSS-SIZE MATH: is the -50%-of-premium catastrophe cap the right loss unit, "
                  "or would a tighter cap (-30/-35/-40%) be net positive after accounting for "
                  "winner-kills (MAE breaches on trades that recovered)?",
    "stamp_et": "2026-09-03T10:24",
    "n_scored_positions": N_ALL,
    "data_sources": [
        "analysis/pain-ledger/mae-mfe.json (n=394 scored, PREREG-2026-08-01.md)",
        "automation/state/fills-ledger.jsonl (broker truth, read via mae-mfe.json builder)",
        "automation/state/core-decisions.jsonl (VIX join, account=safe ticks, date-level median)",
        "automation/state/hypotheses-settled.json (prior stop_inside_noise_floor settlement)",
    ],
    "n_dates_missing_vix_join": n_dates_no_vix,
    "prior_settled_hypothesis_cited": prior_stop_hypothesis,
    "overall_summary": overall_summary,
    "current_cap_cohort_summary": current_cap_summary,
    "legacy_cap_cohort_summary": legacy_summary,
    "by_arm_summary": by_arm_summary,
    "by_regime_summary_all_caps": by_regime_summary,
    "by_regime_summary_current_cap_only": by_regime_current_cap,
    "derived_exit_stage_note": "APPROXIMATE -- no ground-truth exit-reason tag exists in "
                                "fills-ledger.jsonl or mae-mfe.json. Classified from exit_pct "
                                "vs configured cap_pct (see script docstring section 5).",
    "stage_summary": stage_summary,
    "stage_by_arm_counts": stage_by_arm,
    "current_cap_stop_inside_mae_groundtruth": {
        "n_losers_current_cap": len(current_cap_losers),
        "n_losers_stop_inside_mae_true": n_losers_stop_inside_mae,
        "pct_losers_that_touched_cap_level": (n_losers_stop_inside_mae / len(current_cap_losers)) if current_cap_losers else None,
        "n_winners_current_cap": len(current_cap_winners),
        "n_winners_stop_inside_mae_true": n_winners_stop_inside_mae,
        "pct_winners_that_ALSO_touched_cap_level_and_recovered": (n_winners_stop_inside_mae / len(current_cap_winners)) if current_cap_winners else None,
        "note": "stop_inside_mae is pain_ledger.py's own field: bar low traded through the AS-CONFIGURED "
                "stop_premium for that trade. For the current-cap cohort this literally is -50%.",
    },
    "cap_sweep_all_population": sweep_all,
    "cap_sweep_current_cap_cohort_only": sweep_current,
    "cap_sweep_net_effect_by_regime": sweep_by_regime,
    "big_winning_days_check": big_day_report,
    "hindsight_caveat": "MANDATORY (C6 / PREREG-2026-08-01.md): MAE is knowledge of a trade's "
                         "eventual worst point, available only after the fact. A live stop cannot "
                         "condition on 'this will recover' -- it can only condition on price crossing "
                         "a level NOW. Every 'winner_killed' and 'loss_saved' figure in this report is "
                         "a hindsight counterfactual over the REALIZED population, not a forward-tested "
                         "rule. The prior settled hypothesis (stop_inside_noise_floor, 2026-08-06) found "
                         "stop-width changes in EITHER direction are regime-conditional and graveyarded "
                         "'any stop-width change in EITHER direction' -- this report's job is to check "
                         "whether that verdict still holds on the CURRENT (-50%) cap era's population, "
                         "not to re-open it on a hope.",
}

out_path = f"{REPO}/analysis/deep-research/2026-09-03-money/loss-size-math.json"
with open(out_path, "w") as f:
    json.dump(OUT, f, indent=2, default=str)

print("WROTE", out_path)
print()
print("=== OVERALL (n=394) ===")
print(f"WR observed: {overall_summary['wr_observed']:.4f}  breakeven WR: {overall_summary['breakeven_wr_at_observed_avg_win_loss']:.4f}  edge(pp): {overall_summary['wr_edge_over_breakeven_pp']:.2f}")
print(f"avg win ${overall_summary['avg_win_dollars']:.2f}  avg loss ${overall_summary['avg_loss_dollars']:.2f}  PF {overall_summary['profit_factor']:.3f}  total ${overall_summary['total_pnl']:.2f}")
print()
print("=== CURRENT CAP -50% cohort (n=239) ===")
print(f"WR observed: {current_cap_summary['wr_observed']:.4f}  breakeven WR: {current_cap_summary['breakeven_wr_at_observed_avg_win_loss']:.4f}")
print(f"PF {current_cap_summary['profit_factor']:.3f} CI {current_cap_summary['pf_ci_2.5_97.5']}  total ${current_cap_summary['total_pnl']:.2f} CI {current_cap_summary['total_pnl_ci_2.5_97.5']}")
print()
print("=== STAGE SUMMARY ===")
for k, v in stage_summary.items():
    print(k, v)
print()
print("=== CAP SWEEP (ALL population, n eligible varies) ===")
for k, v in sweep_all["sweep"].items():
    print(k, "net", round(v["net_dollar_effect"], 2), "CI", [round(x, 2) for x in v["net_dollar_effect_ci_2.5_97.5"]],
          "winner_killed", v["n_winner_killed"], f"(${v['dollars_winner_killed']:.2f})",
          "loss_saved", v["n_loss_saved"], f"(${v['dollars_loss_saved']:.2f})",
          "false_stop_worsened", v["n_false_stop_worsened"], f"(${v['dollars_false_stop_worsened']:.2f})",
          "big_days_hit", v["big_winning_days_hit"])
print()
print("=== CAP SWEEP (CURRENT -50% cohort only) ===")
for k, v in sweep_current["sweep"].items():
    print(k, "net", round(v["net_dollar_effect"], 2), "CI", [round(x, 2) for x in v["net_dollar_effect_ci_2.5_97.5"]],
          "winner_killed", v["n_winner_killed"], f"(${v['dollars_winner_killed']:.2f})",
          "loss_saved", v["n_loss_saved"], f"(${v['dollars_loss_saved']:.2f})",
          "false_stop_worsened", v["n_false_stop_worsened"], f"(${v['dollars_false_stop_worsened']:.2f})")
print()
print("=== BY REGIME net effect (ALL population) ===")
for regime, d in sweep_by_regime.items():
    print(regime, d)
print()
print("=== BIG WINNING DAYS ===")
for date, d in big_day_report.items():
    print(date, "total_pnl", d["total_realized_pnl"], "n_winners", d["n_winners"], d["cap_sweep_impact"])
print()
print("=== BY ARM (current cap cohort membership + WR) ===")
for arm, s in by_arm_summary.items():
    print(arm, "n=", s["n"], "WR", round(s["wr_observed"],3), "PF", round(s["profit_factor"],3), "total", round(s["total_pnl"],2))
