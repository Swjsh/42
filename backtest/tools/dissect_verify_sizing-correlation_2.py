"""
Independent reproduction / verification of dissect-sizing-correlation.md's claims.
Written from scratch (does not import or reuse the original dissect script) against
automation/state/fills-ledger.jsonl (read-only). FIFO buy/sell matching per (arm, symbol),
is_option==true AND attribution=='engine' only.

Checks:
  1. Today's book-level trough (time-ordered running sum across arms).
  2. Per-arm today trough.
  3. Wave-1 / wave-2 loss breakdown.
  4. Correlation matrix + avg pairwise rho + effective-N, since 2026-08-06, excl today.
  5. Bootstrap CI on avg rho (own resampling, different seed).
  6. Flat-3-contracts counterfactual (entry-level reconstruction).
"""
import json
import collections
import math
import random

FILLS = "automation/state/fills-ledger.jsonl"


def load_rows():
    rows = []
    with open(FILLS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not r.get("is_option"):
                continue
            if r.get("attribution") != "engine":
                continue
            rows.append(r)
    return rows


def fifo_match(rows):
    """FIFO match per (arm, symbol). Returns list of closed round-trip legs."""
    by_key = collections.defaultdict(list)
    for r in rows:
        by_key[(r["arm"], r["symbol"])].append(r)

    legs = []
    unmatched_sells = []
    for (arm, symbol), rs in by_key.items():
        rs2 = sorted(rs, key=lambda x: x["ts_utc"])
        open_lots = collections.deque()
        for r in rs2:
            if r["side"] == "buy":
                open_lots.append({"qty": r["qty"], "price": r["price"],
                                   "ts_et": r["ts_et"], "date_et": r["date_et"]})
            elif r["side"] == "sell":
                remaining = r["qty"]
                while remaining > 1e-9 and open_lots:
                    lot = open_lots[0]
                    take = min(remaining, lot["qty"])
                    pnl = (r["price"] - lot["price"]) * take * 100.0
                    legs.append({
                        "arm": arm, "symbol": symbol, "qty": take,
                        "buy_price": lot["price"], "sell_price": r["price"],
                        "buy_ts_et": lot["ts_et"], "sell_ts_et": r["ts_et"],
                        "buy_date_et": lot["date_et"], "sell_date_et": r["date_et"],
                        "pnl": pnl, "notional": lot["price"] * take * 100.0,
                    })
                    lot["qty"] -= take
                    remaining -= take
                    if lot["qty"] <= 1e-9:
                        open_lots.popleft()
                if remaining > 1e-9:
                    unmatched_sells.append((arm, symbol, r))
            else:
                raise ValueError(f"unexpected side: {r['side']}")
    return legs, unmatched_sells


def pearson(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def corr_matrix(day_arm_pnl, dates, arms):
    mat = {}
    for a in arms:
        mat[a] = [day_arm_pnl.get((d, a), 0.0) for d in dates]
    corr = {}
    for a in arms:
        for b in arms:
            corr[(a, b)] = pearson(mat[a], mat[b])
    return corr


def avg_pairwise(corr, arms):
    vals = [corr[(a, b)] for a in arms for b in arms if a != b]
    return sum(vals) / len(vals)


def eff_n_formula(rho, n):
    return n / (1 + (n - 1) * rho)


def main():
    rows = load_rows()
    print(f"Total option/engine fill rows: {len(rows)}")
    legs, unmatched = fifo_match(rows)
    print(f"Closed round-trip legs (FIFO): {len(legs)}")
    print(f"Unmatched sells: {len(unmatched)}")
    for u in unmatched:
        print("  UNMATCHED:", u)

    # ---- 1/2/3: TODAY ----
    today = "2026-09-03"
    today_legs = sorted([l for l in legs if l["sell_date_et"] == today], key=lambda x: x["sell_ts_et"])
    print(f"\nToday's closed legs (sell_date_et=={today}): {len(today_legs)}")

    running_by_arm = collections.defaultdict(float)
    book_running = 0.0
    book_trough = 0.0
    book_trough_ts = None
    for l in today_legs:
        running_by_arm[l["arm"]] += l["pnl"]
        book_running = sum(running_by_arm.values())
        if book_running < book_trough:
            book_trough = book_running
            book_trough_ts = l["sell_ts_et"]
    print(f"\nBOOK trough today: {book_trough:+.2f} at {book_trough_ts}")
    print(f"BOOK final (closed legs, this read): {book_running:+.2f}")

    print("\nPer-arm today (final closed, trough, trough_ts):")
    by_arm_today = collections.defaultdict(list)
    for l in today_legs:
        by_arm_today[l["arm"]].append(l)
    for arm in sorted(by_arm_today):
        run = 0.0
        tr = 0.0
        tr_ts = None
        for l in by_arm_today[arm]:
            run += l["pnl"]
            if run < tr:
                tr = run
                tr_ts = l["sell_ts_et"]
        print(f"  {arm:10s} final={run:+8.2f}  trough={tr:+8.2f} @ {tr_ts}")

    # wave breakdown: list every losing leg today, grouped by sell_ts minute-cluster
    print("\nAll losing legs today (arm, symbol, sell_ts_et, pnl):")
    losers_today = [l for l in today_legs if l["pnl"] < -0.01]
    for l in sorted(losers_today, key=lambda x: x["sell_ts_et"]):
        print(f"  {l['arm']:10s} {l['symbol']:20s} sell={l['sell_ts_et']} pnl={l['pnl']:+.2f}")
    print(f"Sum of all losing legs today: {sum(l['pnl'] for l in losers_today):+.2f}")
    print(f"Count of losing legs today: {len(losers_today)}")
    print(f"Sum of ALL legs today (== book final): {sum(l['pnl'] for l in today_legs):+.2f}")

    # ---- 4/5: CORRELATION since 2026-08-06, excl today ----
    since = "2026-08-06"
    m2 = [l for l in legs if l["sell_date_et"] >= since]
    day_arm_pnl = collections.defaultdict(float)
    for l in m2:
        day_arm_pnl[(l["sell_date_et"], l["arm"])] += l["pnl"]

    all_dates = sorted(set(d for d, a in day_arm_pnl))
    arms = sorted(set(a for d, a in day_arm_pnl))
    dates_excl_today = [d for d in all_dates if d != today]
    print(f"\nDates since {since} (excl today): n={len(dates_excl_today)}")
    print("Arms:", arms)

    print("\nPer-day per-arm P&L (excl today):")
    for d in dates_excl_today:
        vals = {a: round(day_arm_pnl.get((d, a), 0.0), 2) for a in arms}
        book = sum(vals.values())
        print(f"  {d}  " + "  ".join(f"{a}={vals[a]:+8.2f}" for a in arms) + f"  book={book:+9.2f}")

    corr = corr_matrix(day_arm_pnl, dates_excl_today, arms)
    print("\nCorrelation matrix (excl today):")
    print("           " + " ".join(f"{a:>10s}" for a in arms))
    for a in arms:
        print(f"{a:10s} " + " ".join(f"{corr[(a,b)]:+10.3f}" for b in arms))

    rho = avg_pairwise(corr, arms)
    n = len(arms)
    effn = eff_n_formula(rho, n)
    print(f"\nAvg pairwise rho: {rho:+.4f}")
    print(f"Effective N (formula N/(1+(N-1)rho)): {effn:.4f}")

    # bootstrap CI, own RNG (python random, seed different from original's numpy seed)
    random.seed(99001)
    boot_rhos = []
    boot_effn = []
    B = 3000
    nd = len(dates_excl_today)
    for _ in range(B):
        sample = [dates_excl_today[random.randrange(nd)] for _ in range(nd)]
        c = corr_matrix(day_arm_pnl, sample, arms)
        r = avg_pairwise(c, arms)
        if not math.isnan(r):
            boot_rhos.append(r)
            boot_effn.append(eff_n_formula(r, n))
    boot_rhos.sort()
    boot_effn.sort()

    def pct(sorted_list, p):
        idx = int(round(p / 100.0 * (len(sorted_list) - 1)))
        return sorted_list[idx]

    mean_rho = sum(boot_rhos) / len(boot_rhos)
    mean_effn = sum(boot_effn) / len(boot_effn)
    print(f"\nBootstrap ({B} resamples, own RNG, days w/ replacement, n={nd}):")
    print(f"  avg rho: mean={mean_rho:.4f}  95% CI [{pct(boot_rhos,2.5):.4f}, {pct(boot_rhos,97.5):.4f}]")
    print(f"  effN:    mean={mean_effn:.4f}  95% CI [{pct(boot_effn,2.5):.4f}, {pct(boot_effn,97.5):.4f}]")

    # ---- 6: flat-3-contracts counterfactual ----
    print("\n=== Flat-3-contracts-everywhere counterfactual (entry-level, since", since, ") ===")
    entries = collections.defaultdict(lambda: {"qty": 0.0, "pnl": 0.0})
    for l in m2:
        key = (l["arm"], l["symbol"], l["buy_ts_et"])
        e = entries[key]
        e["qty"] += l["qty"]
        e["pnl"] += l["pnl"]

    per_arm_actual = collections.defaultdict(float)
    per_arm_cf3 = collections.defaultdict(float)
    per_arm_n = collections.defaultdict(int)
    per_arm_n_above3 = collections.defaultdict(int)
    for (arm, symbol, buy_ts), e in entries.items():
        qty = e["qty"]
        pnl = e["pnl"]
        per_contract = pnl / qty if qty else 0.0
        cf_qty = min(qty, 3.0)
        cf_pnl = per_contract * cf_qty
        per_arm_actual[arm] += pnl
        per_arm_cf3[arm] += cf_pnl
        per_arm_n[arm] += 1
        if qty > 3:
            per_arm_n_above3[arm] += 1

    tot_a = tot_c = 0.0
    for arm in sorted(per_arm_actual):
        a = per_arm_actual[arm]
        c = per_arm_cf3[arm]
        tot_a += a
        tot_c += c
        print(f"  {arm:10s} n={per_arm_n[arm]:4d} n>3={per_arm_n_above3[arm]:4d} "
              f"actual={a:+9.2f} flat3={c:+9.2f} delta={c-a:+9.2f}")
    print(f"  {'TOTAL':10s} n={sum(per_arm_n.values()):4d} n>3={sum(per_arm_n_above3.values()):4d} "
          f"actual={tot_a:+9.2f} flat3={tot_c:+9.2f} delta={tot_c-tot_a:+9.2f}")


if __name__ == "__main__":
    main()
