"""B3 part 3 — the bounded configuration: hard worst-case + realistic growth band."""
import json
import random
import statistics as st
from collections import defaultdict

ACT = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")
rows = [json.loads(l) for l in open("analysis/trades-enriched.jsonl", encoding="utf-8") if l.strip()]
d = [r for r in rows if not r.get("_meta") and r["arm"] in ACT]
aug = [r for r in d if "2026-08-03" <= r["date"] <= "2026-08-27"]

# per-trade RETURN ON PREMIUM (this is what scales when you change ticket size)
def rets(rs):
    out = []
    for r in rs:
        c = float(r.get("cost_dollars") or 0)
        if c > 0:
            out.append(float(r["pnl_dollars"]) / c)
    return out


R_AUG = rets(aug)
R_FULL = rets(d)
R_S2 = rets([r for r in aug if r["arm"] == "safe-2"])
for nm, R in (("AUG all arms", R_AUG), ("FULL all arms", R_FULL), ("AUG safe-2", R_S2)):
    w = [x for x in R if x > 0]
    l = [x for x in R if x <= 0]
    print(f"{nm}: n={len(R)} WR={len(w)/len(R):.3f} mean_ret={st.mean(R):+.4f} "
          f"avg_win={st.mean(w):+.3f} avg_loss={st.mean(l):+.3f} "
          f"worst={min(R):+.3f} best={max(R):+.3f}")
print()

# trades per day, per arm
tpd = defaultdict(lambda: defaultdict(int))
for r in aug:
    tpd[r["arm"]][r["date"]] += 1
for a in ACT:
    v = list(tpd[a].values())
    print(f"  {a}: traded {len(v)}/19 days, trades/active-day mean={st.mean(v):.2f} max={max(v)}")
print()


def sim(equity, ticket, max_entries_day, daily_stop, monthly_stop, R, days=252, trials=20000, seed=7,
        account_stop=None):
    """Bounded-config Monte Carlo. Ticket is a FIXED dollar amount (not %-of-equity)
    until equity grows past 4x, then it steps with equity to keep %-risk constant.
    Fires `max_entries_day` entries on a day with probability matching observed
    participation (~2.3 trades/active day, arms trade ~14/19 days)."""
    rnd = random.Random(seed)
    ends, mdds, ruin, hit3k, hit3k_dep = [], [], 0, 0, 0
    p_trade_day = 0.75  # observed: arms traded 12-18 of 19 days
    for _ in range(trials):
        eq = equity
        peak = eq
        mdd = 0.0
        month_pnl = 0.0
        month_halt = False
        worst_cum = 0.0
        for i in range(days):
            if i % 21 == 0:
                month_pnl, month_halt = 0.0, False
            if account_stop is not None and (equity - eq) >= account_stop:
                break  # account-level circuit breaker: STOP, escalate to J, no more entries
            if month_halt or rnd.random() > p_trade_day:
                continue
            day_pnl = 0.0
            tk = ticket * max(1.0, eq / equity) if eq > 4 * equity else ticket
            for _e in range(max_entries_day):
                if day_pnl <= -daily_stop or month_pnl + day_pnl <= -monthly_stop:
                    break
                if eq < tk:
                    break
                day_pnl += tk * rnd.choice(R)
            eq += day_pnl
            month_pnl += day_pnl
            if month_pnl <= -monthly_stop:
                month_halt = True
            peak = max(peak, eq)
            mdd = max(mdd, peak - eq)
            worst_cum = min(worst_cum, eq - equity)
        ends.append(eq)
        mdds.append(mdd)
        if eq <= 0.5 * equity:
            ruin += 1
        if mdd >= 3000:
            hit3k += 1
        if worst_cum <= -3000:
            hit3k_dep += 1
    ends.sort()
    mdds.sort()
    return {
        "equity_start": equity,
        "ticket": ticket,
        "max_entries_day": max_entries_day,
        "daily_stop": daily_stop,
        "monthly_stop": monthly_stop,
        "hard_worst_session_dollars": ticket * max_entries_day,
        "hard_worst_month_dollars": monthly_stop + ticket,
        "p10_end": round(ends[int(.10 * trials)], 0),
        "p50_end": round(ends[int(.50 * trials)], 0),
        "p90_end": round(ends[int(.90 * trials)], 0),
        "median_12mo_return_pct": round(100 * (ends[int(.50 * trials)] / equity - 1), 1),
        "maxdd_p50": round(mdds[int(.50 * trials)], 0),
        "maxdd_p90": round(mdds[int(.90 * trials)], 0),
        "p_drawdown_from_peak_ge_3000": round(hit3k / trials, 4),
        "p_total_loss_from_deposit_ge_3000": round(hit3k_dep / trials, 4),
        "p_50pct_drawdown": round(ruin / trials, 4),
    }


print("=== BOUNDED CONFIGS, 12 months (252d), resampling AUGUST per-trade returns on premium ===")
cfgs = [
    (5000, 300, 2, 300, 750),
    (5000, 300, 3, 450, 1000),
    (5000, 150, 3, 300, 750),
    (10000, 400, 3, 600, 1500),
    (10000, 600, 3, 900, 2000),
    (25000, 750, 3, 1200, 2500),
]
res = []
for eq, tk, ne, ds, ms in cfgs:
    r = sim(eq, tk, ne, ds, ms, R_AUG)
    res.append(r)
    print(f"  E=${eq:>6,} ticket=${tk:>4} n/day={ne} dstop=${ds:>5,} mstop=${ms:>5,} "
          f"| HARD worst day=${r['hard_worst_session_dollars']:>5,} worst month=${r['hard_worst_month_dollars']:>6,} "
          f"| 12mo p10=${r['p10_end']:>8,.0f} p50=${r['p50_end']:>8,.0f} p90=${r['p90_end']:>9,.0f} "
          f"({r['median_12mo_return_pct']:+.0f}%) | maxDD p50=${r['maxdd_p50']:>6,.0f} p90=${r['maxdd_p90']:>7,.0f} "
          f"| P(lose $3K of deposit)={r['p_total_loss_from_deposit_ge_3000']:.3f} P(DD>=$3K)={r['p_drawdown_from_peak_ge_3000']:.3f} P(-50%)={r['p_50pct_drawdown']:.3f}")

print()
print("=== SAME CONFIGS but resampling FULL-HISTORY returns (the honest, less flattering sample) ===")
res_full = []
for eq, tk, ne, ds, ms in cfgs:
    r = sim(eq, tk, ne, ds, ms, R_FULL)
    res_full.append(r)
    print(f"  E=${eq:>6,} ticket=${tk:>4} n/day={ne} | 12mo p10=${r['p10_end']:>8,.0f} "
          f"p50=${r['p50_end']:>8,.0f} p90=${r['p90_end']:>9,.0f} ({r['median_12mo_return_pct']:+.0f}%) "
          f"| maxDD p90=${r['maxdd_p90']:>7,.0f} | P(lose $3K of deposit)={r['p_total_loss_from_deposit_ge_3000']:.3f} P(DD>=$3K)={r['p_drawdown_from_peak_ge_3000']:.3f}")

print()
print("=== CURRENT CONFIG for comparison: $5K, ticket = observed August median $390, 5 entries/day, "
      "daily stop = 30% kill switch, NO monthly stop ===")
r = sim(5000, 390, 5, 1500, 10**9, R_AUG)
print(f"  HARD worst day=${r['hard_worst_session_dollars']:,} | 12mo p10=${r['p10_end']:,.0f} "
      f"p50=${r['p50_end']:,.0f} p90=${r['p90_end']:,.0f} | maxDD p50=${r['maxdd_p50']:,.0f} "
      f"p90=${r['maxdd_p90']:,.0f} | P(lose $3K of deposit)={r['p_total_loss_from_deposit_ge_3000']:.3f} P(DD>=$3K)={r['p_drawdown_from_peak_ge_3000']:.3f} P(-50%)={r['p_50pct_drawdown']:.3f}")
r = sim(5000, 390, 5, 1500, 10**9, R_FULL)
print(f"  [full-history returns] 12mo p50=${r['p50_end']:,.0f} maxDD p90=${r['maxdd_p90']:,.0f} "
      f"P(lose $3K of deposit)={r['p_total_loss_from_deposit_ge_3000']:.3f} P(DD>=$3K)={r['p_drawdown_from_peak_ge_3000']:.3f} P(-50%)={r['p_50pct_drawdown']:.3f}")

print()
print("=== WITH AN ACCOUNT-LEVEL CIRCUIT BREAKER (the knob that actually bounds a YEAR) ===")
acct = []
for eq, tk, ne, ds, ms, ast in [
    (5000, 300, 2, 300, 750, 1500),
    (5000, 300, 3, 450, 1000, 1500),
    (5000, 150, 3, 300, 750, 1250),
    (10000, 400, 3, 600, 1500, 2500),
    (25000, 750, 3, 1200, 2500, 2500),
]:
    for tag, R in (("AUG", R_AUG), ("FULL", R_FULL)):
        r = sim(eq, tk, ne, ds, ms, R, account_stop=ast)
        r["account_stop"] = ast
        r["sample"] = tag
        r["hard_max_total_loss_dollars"] = ast + tk
        acct.append(r)
        print(f"  [{tag:4}] E=${eq:>6,} ticket=${tk:>4} n/day={ne} acct_stop=${ast:>5,} "
              f"| HARD max total loss=${ast+tk:>5,} | 12mo p10=${r['p10_end']:>8,.0f} "
              f"p50=${r['p50_end']:>8,.0f} p90=${r['p90_end']:>9,.0f} ({r['median_12mo_return_pct']:+.0f}%) "
              f"| P(lose $3K of deposit)={r['p_total_loss_from_deposit_ge_3000']:.4f} P(DD>=$3K)={r['p_drawdown_from_peak_ge_3000']:.4f}")

json.dump({"august_configs": res, "full_history_configs": res_full, "account_stop_configs": acct,
           "_method": "20k Monte Carlo resampling observed per-trade RETURN-ON-PREMIUM; fixed dollar "
                      "ticket (steps with equity past 4x); 75% day-participation; daily + monthly "
                      "circuit breakers enforced. iid-trade assumption, n=210 (Aug) / 353 (full) "
                      "source trades -- small, disclosed per C4."},
          open("analysis/recommendations/B3-bounded-config-2026-08-28.json", "w", encoding="utf-8"), indent=1)
print("\nWROTE analysis/recommendations/B3-bounded-config-2026-08-28.json")
