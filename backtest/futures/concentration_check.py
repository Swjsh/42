"""Step 5: Concentration check + stress costs for futures backtests.

Flags:
  - Single day > 40% of total P&L (concentration)
  - Single quarter > 50% of total P&L
  - Stress test: 2-tick slippage
  - Roll-date sanity: no fabricated price jumps > 200pts overnight

Usage:
    python backtest/futures/concentration_check.py --inst MNQ
    python backtest/futures/concentration_check.py --inst BOTH
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO / "backtest" / "data" / "futures"
sys.path.insert(0, str(REPO / "backtest"))

from futures.strategy_config_v3     import should_take     as should_take_mnq
from futures.strategy_config_v3_mes import should_take_v3_mes
from futures.instruments import MNQ, MES

# Instrument-specific v3 configs (MNQ and MES have DIFFERENT signal landscapes)
_CONFIG_FN = {"MNQ": should_take_mnq, "MES": should_take_v3_mes}


def load_and_filter_v3(inst: str) -> pd.DataFrame:
    path = DATA_DIR / f"{inst}_native_rows.jsonl"
    if not path.exists():
        sys.exit(f"ERROR: {path} not found")
    rows = [json.loads(l) for l in path.open()]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if "vix" not in df.columns:
        df["vix"] = 17.0  # fallback for pre-v2 rows
    fn = _CONFIG_FN[inst]
    mask = df.apply(lambda r: fn(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)
    return df[mask].copy()


def concentration_check(df: pd.DataFrame, inst: str):
    print(f"\n{'='*60}\nConcentration Check: {inst} v3 config\n{'='*60}")
    total = df["net"].sum()
    n = len(df)
    print(f"  Total: N={n}  Net=${total:,.0f}")

    # ── Daily concentration ──
    daily = df.groupby("date").agg(net=("net","sum")).sort_values("net", ascending=False)
    daily["pct_of_total"] = daily["net"] / total * 100 if total != 0 else 0
    top_days = daily.head(5)
    print(f"\n  Top 5 days by P&L:")
    for d, row in top_days.iterrows():
        flag = " <<< CONCENTRATION FLAG" if abs(row["pct_of_total"]) > 40 else ""
        print(f"    {d.date()}  ${row['net']:,.0f}  ({row['pct_of_total']:.1f}%){flag}")

    # Check if any single day > 40%
    concentrated_days = daily[daily["pct_of_total"].abs() > 40]
    if not concentrated_days.empty:
        print(f"\n  WARNING: {len(concentrated_days)} days contribute >40% of P&L")
        print("  This signals fragility — the edge may be driven by a single outlier event.")
    else:
        print(f"\n  OK: No single day >40% of P&L")

    # ── Quarterly concentration ──
    df2 = df.copy()
    df2["q"] = df2["date"].dt.to_period("Q")
    qly = df2.groupby("q").agg(net=("net","sum"))
    qly["pct"] = qly["net"] / total * 100 if total != 0 else 0
    print(f"\n  Quarterly distribution:")
    print(qly.to_string())
    over_50 = qly[qly["pct"].abs() > 50]
    if not over_50.empty:
        print(f"  WARNING: Quarter(s) {list(over_50.index.astype(str))} contribute >50%")
    else:
        print(f"  OK: No single quarter >50% of P&L")

    return daily, qly


def stress_test(df: pd.DataFrame, inst: str):
    print(f"\n{'='*60}\nStress Test: {inst} v3 config\n{'='*60}")
    inst_obj = MNQ if inst == "MNQ" else MES

    base_net   = df["net"].sum()
    base_wr    = (df["net"] > 0).mean() * 100
    base_pt    = base_net / len(df) if len(df) else 0

    print(f"  Baseline:         N={len(df)}  WR={base_wr:.1f}%  Net=${base_net:,.0f}  $/trade={base_pt:.2f}")

    for extra_ticks in [1.0, 2.0]:
        extra_usd = extra_ticks * inst_obj.tick_size * inst_obj.point_value * 3 * 2
        stressed = df["net"] - extra_usd
        s_net = stressed.sum()
        s_wr  = (stressed > 0).mean() * 100
        s_pt  = s_net / len(stressed) if len(stressed) else 0
        note = "OK" if s_net > 0 else "NEGATIVE - edge consumed by slippage"
        print(f"  +{extra_ticks:.0f} tick slippage: N={len(df)}  WR={s_wr:.1f}%  Net=${s_net:,.0f}  $/trade={s_pt:.2f}  [{note}]")


def roll_date_sanity(inst: str):
    """Check that continuous series has no fabricated large price jumps."""
    print(f"\n{'='*60}\nRoll-date sanity: {inst} 1m bars\n{'='*60}")
    path_1m = DATA_DIR / f"{inst}_1m_continuous.csv"
    if not path_1m.exists():
        print("  SKIP: 1m CSV not found")
        return
    df = pd.read_csv(path_1m)
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.sort_values("ts").reset_index(drop=True)

    # Compute close-to-open gaps (overnight)
    day_close = df.groupby(df["ts"].dt.date)["close"].last()
    day_open  = df.groupby(df["ts"].dt.date)["open"].first()
    dates = sorted(day_close.index)
    gaps = []
    for i in range(1, len(dates)):
        prev_close = day_close[dates[i-1]]
        curr_open  = day_open[dates[i]]
        gap = abs(curr_open - prev_close)
        if gap > 200:  # >200pts overnight gap is suspicious for a back-adjusted series
            gaps.append((dates[i], gap, prev_close, curr_open))

    if gaps:
        print(f"  WARNING: {len(gaps)} overnight gaps > 200pts:")
        for d, gap, pc, co in gaps[:10]:
            print(f"    {d}: prev_close={pc:.2f} open={co:.2f} gap={gap:.2f}pts")
        if len(gaps) > 5:
            print(f"  NOTE: Large gaps in back-adjusted series on roll dates are EXPECTED.")
            print(f"  A roll-adjusted (Panama) continuous series will have gaps at contract rolls.")
            print(f"  The key check: are these gaps clustered near quarterly expiry dates (Mar/Jun/Sep/Dec)?")
    else:
        print(f"  OK: No overnight gaps > 200pts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BOTH", choices=["MNQ", "MES", "BOTH"])
    a = ap.parse_args()
    insts = ["MNQ", "MES"] if a.inst == "BOTH" else [a.inst]

    for inst in insts:
        path = DATA_DIR / f"{inst}_native_rows.jsonl"
        if not path.exists():
            print(f"SKIP {inst}: not yet computed")
            continue
        df = load_and_filter_v3(inst)
        concentration_check(df, f"{inst} ({('MES-specific' if inst == 'MES' else 'MNQ')} v3)")
        stress_test(df, inst)
        roll_date_sanity(inst)


if __name__ == "__main__":
    main()
