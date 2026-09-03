"""
Part 2: entry-level reconstruction (group legs by buy_ts), per-contract counterfactual
sizing sweep (flat 3 contracts everywhere vs actual tiered qty), and today's running
intraday P&L trough per arm (vs -$400/arm dollar stop and Rule 6/kill-switch % of equity).
"""
import json, collections
import numpy as np

with open("scratch_trades.json", encoding="utf-8") as f:
    trades = json.load(f)

since = "2026-08-06"
m = [t for t in trades if t["sell_date"] >= since]

# group by (arm, symbol, buy_ts) = one original entry order (buy_ts identical across
# all legs of the same buy fill since FIFO consumes lots in order and buy_ts is the lot's
# own fill timestamp)
entries = collections.defaultdict(lambda: {"qty": 0.0, "pnl": 0.0, "date": None, "arm": None, "symbol": None})
for t in m:
    key = (t["arm"], t["symbol"], t["buy_ts"])
    e = entries[key]
    e["qty"] += t["qty"]
    e["pnl"] += t["pnl"]
    e["date"] = t["sell_date"]  # approx, legs of one entry may close on same/adjacent day (0DTE => same day always)
    e["arm"] = t["arm"]
    e["symbol"] = t["symbol"]
    e["buy_price"] = t["buy_price"]

entries = list(entries.values())
print(f"Reconstructed entries (by buy_ts) since {since}: {len(entries)}")

# distribution of entry qty
qty_counts = collections.Counter(round(e["qty"]) for e in entries)
print("Entry qty distribution:", dict(sorted(qty_counts.items())))

per_arm_actual = collections.defaultdict(float)
per_arm_cf3 = collections.defaultdict(float)
per_arm_n = collections.defaultdict(int)
per_arm_n_above3 = collections.defaultdict(int)

for e in entries:
    arm = e["arm"]
    qty = e["qty"]
    pnl = e["pnl"]
    per_contract = pnl / qty if qty else 0.0
    cf_qty = min(qty, 3.0)  # flat-3 cap: never exceed 3, but don't invent qty below what was actually tradeable
    cf_pnl = per_contract * cf_qty
    per_arm_actual[arm] += pnl
    per_arm_cf3[arm] += cf_pnl
    per_arm_n[arm] += 1
    if qty > 3:
        per_arm_n_above3[arm] += 1

print("\n=== Flat-3-contracts-everywhere counterfactual (per-contract linear scaling, APPROXIMATE) ===")
print("arm         n_entries  n_qty>3   actual_$    flat3_$     delta_$")
tot_actual = tot_cf = 0.0
for arm in sorted(per_arm_actual):
    a = per_arm_actual[arm]; c = per_arm_cf3[arm]
    tot_actual += a; tot_cf += c
    print(f"{arm:10s}  {per_arm_n[arm]:8d}  {per_arm_n_above3[arm]:6d}  {a:9.2f}  {c:9.2f}  {c-a:9.2f}")
print(f"{'TOTAL':10s}  {sum(per_arm_n.values()):8d}  {sum(per_arm_n_above3.values()):6d}  {tot_actual:9.2f}  {tot_cf:9.2f}  {tot_cf-tot_actual:9.2f}")

# median winner size (dollar) vs median loser size, per arm, since 08-06 (entry-level)
print("\n=== Winner/loser size distribution (entry-level $, since 08-06) ===")
for arm in sorted(set(e["arm"] for e in entries)):
    ent = [e for e in entries if e["arm"] == arm]
    winners = [e["pnl"] for e in ent if e["pnl"] > 0]
    losers = [e["pnl"] for e in ent if e["pnl"] < 0]
    med_w = np.median(winners) if winners else float('nan')
    med_l = np.median(losers) if losers else float('nan')
    notional = [e["qty"]*e.get("buy_price",0)*100 for e in ent]
    med_notional = np.median(notional) if notional else float('nan')
    print(f"{arm:10s} n={len(ent):3d} med_win=${med_w:7.2f} med_loss=${med_l:8.2f} med_notional=${med_notional:7.2f}")

# ---- TODAY: intraday running trough per arm ----
print("\n=== TODAY (2026-09-03) running realized P&L per arm, trough vs -$400 stop ===")
today_trades = [t for t in trades if t["sell_date"] == "2026-09-03"]
today_trades.sort(key=lambda x: x["sell_ts"])
by_arm = collections.defaultdict(list)
for t in today_trades:
    by_arm[t["arm"]].append(t)

equity = {"safe-2": 5653.81, "bold-2": 5593.52, "safe-3": 5639.10, "risky-1": 6149.12}
kill_pct = {"safe-2": 0.30, "bold-2": 0.50, "safe-3": 0.30, "risky-1": 0.50}

for arm in sorted(by_arm):
    running = 0.0
    trough = 0.0
    trough_ts = None
    for t in by_arm[arm]:
        running += t["pnl"]
        if running < trough:
            trough = running
            trough_ts = t["sell_ts"]
    eq = equity.get(arm)
    pct_of_400 = trough / -400.0 * 100
    pct_of_equity = trough / eq * 100 if eq else None
    kp = kill_pct.get(arm)
    kill_dollar = -kp * eq if (eq and kp) else None
    pct_of_kill = (trough / kill_dollar * 100) if kill_dollar else None
    print(f"{arm:10s} final={running:+8.2f}  trough={trough:+8.2f} @ {trough_ts}  "
          f"({pct_of_400:5.1f}% of -$400 stop; {pct_of_equity:+.2f}% of equity; "
          f"{pct_of_kill:5.1f}% of way to {kp*100:.0f}% kill switch [-${-kill_dollar:.0f}])")

# ---- book-level trough (time-aligned sum across arms) ----
print("\n=== TODAY book-level running trough (time-aligned across all arms) ===")
all_today = sorted(today_trades, key=lambda x: x["sell_ts"])
running_by_arm = collections.defaultdict(float)
book_running = 0.0
book_trough = 0.0
book_trough_ts = None
for t in all_today:
    running_by_arm[t["arm"]] += t["pnl"]
    book_running = sum(running_by_arm.values())
    if book_running < book_trough:
        book_trough = book_running
        book_trough_ts = t["sell_ts"]
print(f"Book trough today: {book_trough:+.2f} at {book_trough_ts}")
print(f"Book final (closed legs only, as of last read): {book_running:+.2f}")
