"""
D6 SIZING AND CORRELATION -- dissect script.
Read-only against automation/state/fills-ledger.jsonl (options, engine-attributed).
FIFO-matches buy/sell fills per (arm, symbol) -- safe globally since 0DTE symbols encode
the expiry date, so no cross-day collision is possible.
Outputs per-arm per-day realized P&L, correlation matrix, effective-N, and per-trade stats.
"""
import json
import collections
import statistics
import itertools
import math

FILLS = "automation/state/fills-ledger.jsonl"

def load_fills():
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
    """FIFO match buy/sell fills per (arm, symbol); returns list of closed-trade dicts."""
    by_key = collections.defaultdict(list)
    for r in rows:
        by_key[(r["arm"], r["symbol"])].append(r)
    trades = []
    for (arm, symbol), rs in by_key.items():
        rs.sort(key=lambda x: x["ts_utc"])
        buys = collections.deque()
        for r in rs:
            qty = r["qty"]
            price = r["price"]
            ts = r["ts_et"]
            date = r["date_et"]
            if r["side"] == "buy":
                buys.append({"qty": qty, "price": price, "ts": ts, "date": date})
            elif r["side"] == "sell":
                remaining = qty
                while remaining > 1e-9 and buys:
                    lot = buys[0]
                    take = min(remaining, lot["qty"])
                    pnl = (price - lot["price"]) * take * 100
                    trades.append({
                        "arm": arm, "symbol": symbol, "qty": take,
                        "buy_price": lot["price"], "sell_price": price,
                        "buy_ts": lot["ts"], "sell_ts": ts,
                        "buy_date": lot["date"], "sell_date": date,
                        "pnl": pnl,
                        "notional": lot["price"] * take * 100,
                    })
                    lot["qty"] -= take
                    remaining -= take
                    if lot["qty"] <= 1e-9:
                        buys.popleft()
                if remaining > 1e-9:
                    trades.append({
                        "arm": arm, "symbol": symbol, "qty": remaining,
                        "buy_price": None, "sell_price": price,
                        "buy_ts": None, "sell_ts": ts,
                        "buy_date": None, "sell_date": date,
                        "pnl": None, "notional": None,
                        "UNMATCHED_SELL": True,
                    })
    return trades

def main():
    rows = load_fills()
    trades = fifo_match(rows)
    unmatched = [t for t in trades if t.get("UNMATCHED_SELL")]
    matched = [t for t in trades if not t.get("UNMATCHED_SELL")]

    print(f"Total option/engine fill rows: {len(rows)}")
    print(f"Closed round-trip legs (FIFO-matched): {len(matched)}")
    print(f"Unmatched sells (sold w/o a matching buy in this ledger window): {len(unmatched)}")
    if unmatched:
        for u in unmatched:
            print("  UNMATCHED:", u["arm"], u["symbol"], u["sell_date"], u["qty"], u["sell_price"])

    # since 2026-08-06
    since = "2026-08-06"
    m2 = [t for t in matched if t["sell_date"] >= since]
    print(f"\nMatched legs since {since}: {len(m2)}")

    # per (date, arm) pnl
    day_arm_pnl = collections.defaultdict(float)
    day_arm_trades = collections.defaultdict(int)
    for t in m2:
        day_arm_pnl[(t["sell_date"], t["arm"])] += t["pnl"]
        day_arm_trades[(t["sell_date"], t["arm"])] += 1

    dates = sorted(set(d for d, a in day_arm_pnl))
    arms = sorted(set(a for d, a in day_arm_pnl))
    print("\nArms seen:", arms)
    print("Dates seen:", len(dates), dates[0], "..", dates[-1])

    print("\n=== Per-day, per-arm realized P&L (option round trips, FIFO) ===")
    header = "date".ljust(12) + "".join(a.ljust(12) for a in arms) + "book_sum".ljust(12)
    print(header)
    book_by_day = {}
    for d in dates:
        vals = [day_arm_pnl.get((d, a), 0.0) for a in arms]
        book = sum(vals)
        book_by_day[d] = book
        line = d.ljust(12) + "".join(f"{v:+9.2f}  " for v in vals) + f"{book:+9.2f}"
        print(line)

    print("\n=== Correlation of arm P&L (same-day), since", since, "===")
    # build matrix only over days where arm has ANY row (0 if no trade that day but arm active later)
    # use full date range, fill 0 for no-trade days for that arm
    import numpy as np
    mat = np.array([[day_arm_pnl.get((d, a), 0.0) for a in arms] for d in dates])
    print("Matrix shape (days x arms):", mat.shape)
    corr = np.corrcoef(mat.T)
    print("Arms order:", arms)
    for i, a in enumerate(arms):
        print(a.ljust(10), " ".join(f"{corr[i,j]:+.3f}" for j in range(len(arms))))

    # effective number of independent bets via eigenvalues of correlation matrix
    eigvals = np.linalg.eigvalsh(corr)
    eigvals = np.clip(eigvals, 0, None)
    print("\nEigenvalues of corr matrix:", eigvals)
    # effective N (participation ratio): (sum eig)^2 / sum(eig^2)
    if eigvals.sum() > 0:
        eff_n_pr = (eigvals.sum() ** 2) / (eigvals ** 2).sum()
    else:
        eff_n_pr = float('nan')
    print(f"Effective N (participation ratio of eigenvalues): {eff_n_pr:.3f}  (max = {len(arms)})")

    # simple average pairwise correlation -> effective N formula: N / (1 + (N-1)*rho_avg)
    n = len(arms)
    off_diag = [corr[i, j] for i in range(n) for j in range(n) if i != j]
    rho_avg = float(np.mean(off_diag))
    eff_n_formula = n / (1 + (n - 1) * rho_avg)
    print(f"Average pairwise correlation: {rho_avg:+.3f}")
    print(f"Effective N (1/(1+(N-1)rho) formula): {eff_n_formula:.3f}")

    # book vs per-arm loss on LOSING days (book negative)
    print("\n=== Loss days: book total vs per-arm ===")
    for d in dates:
        book = book_by_day[d]
        if book < 0:
            vals = {a: day_arm_pnl.get((d, a), 0.0) for a in arms}
            print(d, f"book={book:+.2f}", {a: round(v,2) for a, v in vals.items() if abs(v) > 0.01})

    with open("scratch_trades.json", "w") as f:
        json.dump(matched, f, indent=1, default=str)
    with open("scratch_day_arm_pnl.json", "w") as f:
        json.dump({f"{d}|{a}": v for (d, a), v in day_arm_pnl.items()}, f, indent=1)

if __name__ == "__main__":
    main()
