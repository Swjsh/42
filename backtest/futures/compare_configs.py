"""Compare v2b vs v3 configs on MNQ/MES native data.

Shows IS, OOS, quarterly breakdown, WF gate for each config.
Also tests a VIX-gated version using approximate VIX (17 fixed) vs no gate.

Usage:
    python backtest/futures/compare_configs.py --inst MNQ
    python backtest/futures/compare_configs.py --inst MES
    python backtest/futures/compare_configs.py --inst BOTH
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO / "backtest" / "data" / "futures"
OUT_DIR  = REPO / "analysis" / "recommendations"
sys.path.insert(0, str(REPO / "backtest"))

from futures.strategy_config        import should_take as should_take_v2b
from futures.strategy_config_v3     import should_take as should_take_v3
from futures.strategy_config_v3_mes import should_take_v3_mes
from futures.analyze_native         import load_rows, wf_gate, strategy_summary


CONFIGS_MNQ = {
    "v2b (SPY-proxy derived)":  should_take_v2b,
    "v3 (MNQ-native derived)":  should_take_v3,
}

CONFIGS_MES = {
    "v2b (SPY-proxy derived)":  should_take_v2b,
    "v3 (MNQ-native derived)":  should_take_v3,
    "v3_mes (MES-native derived)": should_take_v3_mes,
}


def eval_config(df: pd.DataFrame, fn, label: str, train_end: str = "2025-12-31"):
    train_end_dt = pd.to_datetime(train_end)
    full = df[df.apply(lambda r: fn(r["watcher"], r["dir"], r["conf"], r.get("vix", 17.0)), axis=1)].copy()
    is_df  = full[full["date"] <= train_end_dt]
    oos_df = full[full["date"] >  train_end_dt]

    def stats(d):
        n = len(d)
        net = d["net"].sum()
        wr  = (d["net"] > 0).mean() * 100 if n else 0
        pt  = net / n if n else 0
        return n, net, wr, pt

    fn_n, fn_net, fn_wr, fn_pt = stats(full)
    is_n, is_net, is_wr, is_pt = stats(is_df)
    os_n, os_net, os_wr, os_pt = stats(oos_df)
    _, verdict = wf_gate(is_pt, os_pt, os_net)

    print(f"\n  [{label}]")
    print(f"    Full   : N={fn_n}  WR={fn_wr:.1f}%  Net=${fn_net:,.0f}  $/trade={fn_pt:.2f}")
    print(f"    IS2025 : N={is_n}  WR={is_wr:.1f}%  Net=${is_net:,.0f}  $/trade={is_pt:.2f}")
    print(f"    OOS2026: N={os_n}  WR={os_wr:.1f}%  Net=${os_net:,.0f}  $/trade={os_pt:.2f}")
    print(f"    OOS Gate: {verdict}")

    # quarterly in OOS
    if not oos_df.empty:
        oos_df2 = oos_df.copy()
        oos_df2["q"] = oos_df2["date"].dt.to_period("Q")
        gq = (oos_df2.groupby("q")
               .agg(n=("net","count"), net=("net","sum"), wr=("net", lambda x: (x>0).mean()*100))
               .reset_index())
        print(f"    OOS quarters: {dict(zip(gq['q'].astype(str), gq['net'].round(0).astype(int).values))}")

    return {
        "label": label,
        "full_net": fn_net, "is_net": is_net, "oos_net": os_net,
        "full_n": fn_n, "is_n": is_n, "oos_n": os_n,
        "oos_wr": os_wr, "oos_pt": os_pt, "gate": verdict,
    }


def run_instrument(inst: str):
    print(f"\n{'#'*70}\n#  {inst} — Config comparison\n{'#'*70}")
    try:
        df = load_rows(inst)
    except SystemExit as e:
        print(f"  SKIP: {e}")
        return

    configs = CONFIGS_MES if inst == "MES" else CONFIGS_MNQ
    results = []
    for label, fn in configs.items():
        r = eval_config(df, fn, label)
        results.append(r)

    # Winner: gate-aware (PASS > REGIME-FLIP > FAIL), then OOS $/trade as tiebreaker
    def gate_score(r: dict) -> tuple:
        gate = r["gate"]
        tier = 2 if gate == "PASS" else (1 if "FLIP" in gate else 0)
        return (tier, r["oos_pt"])
    best = max(results, key=gate_score)
    print(f"\n  => Best config (gate-aware): [{best['label']}]  OOS net=${best['oos_net']:,.0f}  Gate={best['gate']}")

    # Save
    out = OUT_DIR / f"futures-{inst.lower()}-config-comparison.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"  Saved to {out.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BOTH", choices=["MNQ", "MES", "BOTH"])
    a = ap.parse_args()
    insts = ["MNQ", "MES"] if a.inst == "BOTH" else [a.inst]
    for inst in insts:
        run_instrument(inst)


if __name__ == "__main__":
    main()
