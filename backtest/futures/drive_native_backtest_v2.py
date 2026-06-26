"""Drive native backtest v2 — with ORB futures-range-scale fix + VIX per row.

Replaces drive_native_backtest.py for the third run.
Key: calls run() from run_native_backtest.py which does set_futures_range_scale().

Usage:
    python backtest/futures/drive_native_backtest_v2.py
"""
from __future__ import annotations
import datetime as dt, json, sys, time
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

DATA = REPO / "backtest" / "data" / "futures"
from futures.instruments import MNQ, MES
from futures.run_native_backtest import run


def run_full(inst, start="2025-01-01", end="2026-06-12", budget_per_chunk=1200):
    sym = inst.symbol
    rows_p  = str(DATA / f"{sym}_native_rows.jsonl")
    state_p = DATA / f"{sym}_native_state.json"

    # Clean slate
    for f in [DATA / f"{sym}_native_rows.jsonl", state_p]:
        if f.exists():
            f.unlink()
            print(f"  Cleared {f.name}")

    start_d = dt.date.fromisoformat(start)
    end_d   = dt.date.fromisoformat(end)

    # Count total trading days for progress %
    import csv
    rth_path = DATA / f"{sym}_5m_continuous.csv"
    dates = set()
    with open(rth_path, newline="") as fh:
        for row in csv.DictReader(fh):
            d = row["timestamp_et"][:10]
            if start <= d <= end:
                dates.add(d)
    total_days = len(dates)

    print(f"\n=== {sym} native backtest v2 (ORB+VIX, {start} to {end}) ===")
    print(f"  {total_days} trading days  |  budget {budget_per_chunk}s/chunk")

    t0 = time.time()
    last_done = None
    chunk = 0

    while True:
        r = run(start_d, end_d, inst,
                resume_after=last_done,
                budget_s=budget_per_chunk,
                rows_path=rows_p)

        last_done_str = r.get("last_done") or (str(last_done) if last_done else None)
        last_done = dt.date.fromisoformat(last_done_str) if last_done_str else None

        # Count rows written so far
        n_rows = sum(1 for _ in open(rows_p)) if Path(rows_p).exists() else 0
        elapsed = time.time() - t0

        if last_done:
            done_days = len([d for d in dates if dt.date.fromisoformat(d) <= last_done])
            pct = done_days / total_days * 100 if total_days else 0
            print(f"  {done_days} days ({pct:.0f}%), {elapsed:.0f}s, {n_rows} signals")

        chunk += 1
        if r.get("reached_end"):
            break
        if chunk > 500:
            print("  ERROR: runaway loop — check budget_s")
            break

    rows = [json.loads(l) for l in open(rows_p)] if Path(rows_p).exists() else []
    elapsed = time.time() - t0
    orb_rows = [r for r in rows if r.get("watcher") == "orb_watcher"]
    has_vix = sum(1 for r in rows if "vix" in r)

    print(f"  DONE: {len(rows)} signals, {elapsed:.1f}s")
    print(f"  ORB signals: {len(orb_rows)}  |  rows with vix: {has_vix}")

    return rows


def summarize(rows, label):
    if not rows:
        print(f"\n{label}: No signals found!")
        return
    df = pd.DataFrame(rows)
    total_net = df["net"].sum()
    wr        = (df["net"] > 0).mean() * 100
    per_trade = total_net / len(df)
    print(f"\n=== {label} SUMMARY ===")
    print(f"  Signals: {len(df)}  WR: {wr:.1f}%  Net: ${total_net:,.2f}  $/t: {per_trade:.2f}")
    print(f"\n  By watcher (top 10 by net):")
    g = df.groupby(["watcher","dir","conf"]).agg(
        n=("net","count"), net=("net","sum"),
        wr=("net", lambda x: (x>0).mean()*100)
    ).sort_values("net", ascending=False).head(10)
    print(g.to_string())

    print(f"\n  By quarter:")
    df["q"] = pd.to_datetime(df["date"]).dt.to_period("Q")
    gq = df.groupby("q").agg(n=("net","count"), net=("net","sum"),
                              wr=("net", lambda x: (x>0).mean()*100))
    print(gq.to_string())


if __name__ == "__main__":
    print("=== Futures Edition — v2 backtest (ORB+VIX enabled) ===")
    mnq_rows = run_full(MNQ)
    summarize(mnq_rows, "MNQ")

    mes_rows = run_full(MES)
    summarize(mes_rows, "MES")

    print("\n=== v2 complete. Next: python backtest/futures/run_full_analysis.py ===")
