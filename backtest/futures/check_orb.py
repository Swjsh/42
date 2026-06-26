"""Quick ORB analysis on native rows — run after the ORB-enabled backtest.

Checks: does ORB fire? Is it OOS-positive? Should it join v3/v3_mes?

Usage:
    python backtest/futures/check_orb.py --inst MNQ
    python backtest/futures/check_orb.py --inst MES
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO / "backtest" / "data" / "futures"
sys.path.insert(0, str(REPO / "backtest"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="MNQ", choices=["MNQ", "MES"])
    a = ap.parse_args()

    path = DATA_DIR / f"{a.inst}_native_rows.jsonl"
    if not path.exists():
        sys.exit(f"ERROR: {path} not found")

    rows = [json.loads(l) for l in path.open()]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    orb = df[df["watcher"] == "orb_watcher"].copy()
    n_total = len(df)
    n_orb   = len(orb)
    print(f"  Total signals: {n_total}  |  ORB signals: {n_orb} ({n_orb/n_total*100:.1f}% of all)")

    if orb.empty:
        print(f"ORB watcher: ZERO signals on {a.inst}.")
        print("Root cause: SPY-calibrated OR max gate (2.0 SPY-pts x scale) too narrow for futures.")
        print("MNQ typical OR: 100-200pts; gate allows ~60-70pts → >90% of days blocked.")
        print("Decision: ORB is NOT suitable for futures without redesigning range thresholds.")
        print("=> Do NOT add ORB to v3/v3_mes configs.")
        return

    print(f"\n{'='*60}\nORB Watcher — {a.inst} native data\n{'='*60}")
    print(f"  Total signals: {len(orb)}")

    g = (orb.groupby(["dir","conf"])
          .agg(n=("net","count"), net=("net","sum"),
               wr=("net", lambda x: (x>0).mean()*100),
               per_trade=("net","mean"))
          .sort_values("net", ascending=False))
    print("\n  By dir x conf:")
    print(g.to_string())

    # OOS check
    is_df  = orb[orb["date"] <= pd.to_datetime("2025-12-31")]
    oos_df = orb[orb["date"] >  pd.to_datetime("2025-12-31")]
    is_n  = len(is_df);  is_net  = is_df["net"].sum();  is_pt  = is_net/is_n if is_n else 0
    oos_n = len(oos_df); oos_net = oos_df["net"].sum(); oos_pt = oos_net/oos_n if oos_n else 0

    print(f"\n  IS (2025): N={is_n}  WR={(is_df['net']>0).mean()*100:.1f}%  Net=${is_net:,.0f}  $/t={is_pt:.2f}")
    print(f"  OOS (2026): N={oos_n}  WR={(oos_df['net']>0).mean()*100:.1f}%  Net=${oos_net:,.0f}  $/t={oos_pt:.2f}")

    if oos_net > 0 and oos_pt > 0:
        if is_pt > 0:
            wf = oos_pt / is_pt
            verdict = "PASS" if wf >= 0.5 else f"FAIL (WF={wf:.3f}<0.5)"
        else:
            verdict = "PASS-REGIME-FLIP (IS<0, OOS>0)"
        print(f"  OOS Gate: {verdict}")
        if oos_n < 20:
            print(f"  NOTE: OOS N={oos_n} < 20 minimum — not viable regardless of gate")
        if verdict.startswith("PASS") and oos_n >= 20:
            print(f"\n  => ORB PASSES — add to v3 config for {a.inst}")
        else:
            print(f"\n  => ORB does NOT pass — do NOT add to v3 config (gate={verdict}, OOS N={oos_n})")
    else:
        print(f"  OOS Gate: FAIL (OOS negative)")
        print(f"\n  => ORB fails OOS — do NOT add to v3 config")


if __name__ == "__main__":
    main()
