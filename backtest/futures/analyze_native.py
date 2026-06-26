"""Step 3+4: Analyze native backtest results + OOS walk-forward.

Reads {MNQ,MES}_native_rows.jsonl, produces:
  - Per-strategy breakdown (watcher x dir x conf)
  - Quarterly breakdown
  - v2b curated config performance
  - OOS walk-forward: train=2025, test=2026

Usage:
    python backtest/futures/analyze_native.py --inst MNQ
    python backtest/futures/analyze_native.py --inst MES
    python backtest/futures/analyze_native.py --inst BOTH
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO / "backtest" / "data" / "futures"
OUT_DIR  = REPO / "analysis" / "recommendations"

sys.path.insert(0, str(REPO / "backtest"))
from futures.strategy_config        import should_take as should_take_v2b
from futures.strategy_config_v3     import should_take as should_take_v3_mnq
from futures.strategy_config_v3_mes import should_take_v3_mes


# ─── helpers ──────────────────────────────────────────────────────────────────

def load_rows(inst: str) -> pd.DataFrame:
    path = DATA_DIR / f"{inst}_native_rows.jsonl"
    if not path.exists():
        sys.exit(f"ERROR: {path} not found. Run drive_native_backtest.py first.")
    rows = [json.loads(l) for l in path.open()]
    if not rows:
        sys.exit(f"ERROR: {path} is empty.")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    # Use real VIX from row if present (added after initial backtest run),
    # fall back to fixed 17.0 for backward compat with old JSONL files.
    if "vix" not in df.columns:
        df["vix"] = 17.0
    return df


def sharpe(series: pd.Series, periods_per_year: int = 252) -> float:
    if series.std() == 0 or len(series) < 5:
        return 0.0
    return float(series.mean() / series.std() * np.sqrt(periods_per_year))


def quarter_label(date: pd.Timestamp) -> str:
    return f"{date.year}Q{((date.month-1)//3)+1}"


def strategy_summary(df: pd.DataFrame, label: str = ""):
    if label:
        print(f"\n{'='*60}\n{label}\n{'='*60}")
    total = df["net"].sum()
    n = len(df)
    wr = (df["net"] > 0).mean() * 100 if n else 0
    per = total / n if n else 0
    print(f"  N={n}  WR={wr:.1f}%  Net=${total:,.0f}  $/trade={per:.2f}")

    g = (df.groupby(["watcher","dir","conf"])
          .agg(n=("net","count"), net=("net","sum"),
               wr=("net", lambda x: (x>0).mean()*100),
               per_trade=("net","mean"))
          .sort_values("net", ascending=False)
          .reset_index())
    print("\n  By strategy (all, top 15 by net):")
    print(g.head(15).to_string(index=False))

    df2 = df.copy()
    df2["q"] = df2["date"].apply(quarter_label)
    gq = (df2.groupby("q")
           .agg(n=("net","count"), net=("net","sum"),
                wr=("net", lambda x: (x>0).mean()*100))
           .reset_index())
    print("\n  By quarter:")
    print(gq.to_string(index=False))
    return g, gq


def wf_gate(is_pt: float, oos_pt: float, oos_net: float) -> tuple[float, str]:
    """WF ratio + gate verdict.

    Standard WF = OOS_pt / IS_pt breaks when IS_pt is negative (sign inversion).
    Gate logic:
      1. OOS expectancy must be positive (oos_pt > 0 AND oos_net > 0)
      2. If IS_pt > 0: standard ratio >= 0.5
      3. If IS_pt <= 0 and OOS_pt > 0: regime-flip PASS (IS lost, OOS wins = improvement)
      4. If both negative: FAIL
    """
    if oos_pt <= 0 or oos_net <= 0:
        return 0.0, "FAIL (OOS negative)"
    if is_pt > 0:
        ratio = oos_pt / is_pt
        return ratio, "PASS" if ratio >= 0.5 else f"FAIL (WF={ratio:.3f}<0.5)"
    # IS negative, OOS positive = regime flip — note but count as PASS with caveat
    return float("inf"), "PASS-REGIME-FLIP (IS<0, OOS>0, watch for recency bias)"


def oos_walk_forward(df: pd.DataFrame, inst: str, train_end: str = "2025-12-31"):
    """Simple IS/OOS split. Train: <= train_end, Test: > train_end."""
    train_end_dt = pd.to_datetime(train_end)
    is_df  = df[df["date"] <= train_end_dt].copy()
    oos_df = df[df["date"] >  train_end_dt].copy()

    print(f"\n{'='*60}\nOOS Walk-Forward ({inst})\n{'='*60}")
    print(f"  IS:  {is_df['date'].min().date()} to {is_df['date'].max().date()}  N={len(is_df)}")
    print(f"  OOS: {oos_df['date'].min().date()} to {oos_df['date'].max().date()}  N={len(oos_df)}")

    # ── raw (all signals) ──
    raw_is_net  = is_df["net"].sum();  raw_is_n  = len(is_df)
    raw_oos_net = oos_df["net"].sum(); raw_oos_n = len(oos_df)
    raw_is_pt   = raw_is_net / raw_is_n if raw_is_n else 0
    raw_oos_pt  = raw_oos_net / raw_oos_n if raw_oos_n else 0
    _, raw_verdict = wf_gate(raw_is_pt, raw_oos_pt, raw_oos_net)
    print(f"\n  RAW (all signals):")
    print(f"    IS  WR={((is_df['net']>0).mean()*100):.1f}%  Net=${raw_is_net:,.0f}  $/trade={raw_is_pt:.2f}")
    print(f"    OOS WR={((oos_df['net']>0).mean()*100):.1f}%  Net=${raw_oos_net:,.0f}  $/trade={raw_oos_pt:.2f}")
    print(f"    Gate: {raw_verdict}")

    vix_src = "per-row actual" if df["vix"].std() > 0.1 else "fixed=17.0 (re-run backtest for real VIX)"
    print(f"  (VIX source: {vix_src})")

    # ── curated configs comparison (v2b, v3_mnq, v3_mes) ──
    configs_to_check = [
        ("V2B",     should_take_v2b),
        ("V3_MNQ",  should_take_v3_mnq),
    ]
    if inst == "MES":
        configs_to_check.append(("V3_MES", should_take_v3_mes))

    # Scoring: prefer PASS gate > REGIME-FLIP > FAIL; within same gate tier, rank by OOS $/trade
    def config_score(gate: str, oos_pt: float) -> tuple:
        tier = 2 if gate.startswith("PASS") and "FLIP" not in gate else (1 if "FLIP" in gate else 0)
        return (tier, oos_pt)

    best_config = None; best_score = (-1, -1e9)
    for cfg_label, cfg_fn in configs_to_check:
        is_c  = is_df[is_df.apply(lambda r: cfg_fn(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
        oos_c = oos_df[oos_df.apply(lambda r: cfg_fn(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
        is_n,  is_net,  is_pt  = len(is_c),  is_c["net"].sum(),  is_c["net"].sum()/len(is_c) if len(is_c) else 0
        oos_n, oos_net, oos_pt = len(oos_c), oos_c["net"].sum(), oos_c["net"].sum()/len(oos_c) if len(oos_c) else 0
        _, verdict = wf_gate(is_pt, oos_pt, oos_net)
        print(f"\n  [{cfg_label}]")
        print(f"    IS  N={is_n}  WR={((is_c['net']>0).mean()*100 if is_n else 0):.1f}%  Net=${is_net:,.0f}  $/t={is_pt:.2f}")
        print(f"    OOS N={oos_n}  WR={((oos_c['net']>0).mean()*100 if oos_n else 0):.1f}%  Net=${oos_net:,.0f}  $/t={oos_pt:.2f}")
        print(f"    Gate: {verdict}")
        score = config_score(verdict, oos_pt)
        if score > best_score:
            best_score = score; best_config = (cfg_label, oos_c, is_n, oos_n, is_net, oos_net, is_pt, oos_pt, verdict)

    is_v2b  = is_df[is_df.apply(lambda r: should_take_v2b(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
    oos_v2b = oos_df[oos_df.apply(lambda r: should_take_v2b(r["watcher"], r["dir"], r["conf"], r["vix"]), axis=1)]
    is_v2b_net  = is_v2b["net"].sum(); is_v2b_n  = len(is_v2b)
    oos_v2b_net = oos_v2b["net"].sum(); oos_v2b_n = len(oos_v2b)
    is_v2b_pt  = is_v2b_net  / is_v2b_n  if is_v2b_n  else 0
    oos_v2b_pt = oos_v2b_net / oos_v2b_n if oos_v2b_n else 0
    _, verdict_v2b = wf_gate(is_v2b_pt, oos_v2b_pt, oos_v2b_net)

    # show per-strategy breakdown for best config
    if best_config:
        bl, b_oos_c, b_oos_net = best_config[0], best_config[1], best_config[5]
        print(f"\n  => Best OOS: [{bl}] ${b_oos_net:,.0f}  |  per-strategy breakdown:")
        g = (b_oos_c.groupby(["watcher","dir","conf"])
              .agg(n=("net","count"), net=("net","sum"),
                   wr=("net", lambda x: (x>0).mean()*100),
                   per_trade=("net","mean"))
              .sort_values("net", ascending=False).reset_index())
        print(g.to_string(index=False))

        # rolling 2-month OOS windows for the best config
        print(f"\n  Rolling 2-month OOS windows ({bl}):")
        b_oos_c2 = b_oos_c.copy()
        if not b_oos_c2.empty:
            b_oos_c2["month"] = b_oos_c2["date"].dt.to_period("M")
            months = sorted(b_oos_c2["month"].unique())
            all_positive = True
            for i in range(len(months) - 1):
                w = months[i:i+2]
                chunk = b_oos_c2[b_oos_c2["month"].isin(w)]
                if len(chunk) >= 3:
                    net = chunk["net"].sum()
                    if net <= 0:
                        all_positive = False
                    print(f"    {w[0]}-{w[1]}: N={len(chunk)}  Net=${net:,.0f}  "
                          f"WR={((chunk['net']>0).mean()*100):.1f}%")
            if all_positive:
                print(f"    => ALL 2-month windows POSITIVE — rolling stability CONFIRMED")
            else:
                print(f"    => WARNING: Not all 2-month windows positive — check regime dependence")

    # ── per-strategy OOS breakdown (v2b reference) ──
    print(f"\n  V2B per-strategy OOS:")
    if oos_v2b_n:
        g = (oos_v2b.groupby(["watcher","dir","conf"])
              .agg(n=("net","count"), net=("net","sum"),
                   wr=("net", lambda x: (x>0).mean()*100),
                   per_trade=("net","mean"))
              .sort_values("net", ascending=False)
              .reset_index())
        print(g.to_string(index=False))

    # ── rolling 3-month OOS windows (v2b reference) ──
    print(f"\n  Rolling 3-month OOS windows (v2b):")
    oos_v2b2 = oos_v2b.copy()
    if not oos_v2b2.empty:
        oos_v2b2["month"] = oos_v2b2["date"].dt.to_period("M")
        months = sorted(oos_v2b2["month"].unique())
        for i in range(len(months) - 2):
            w = months[i:i+3]
            chunk = oos_v2b2[oos_v2b2["month"].isin(w)]
            if len(chunk) >= 5:
                print(f"    {w[0]}-{w[2]}: N={len(chunk)}  Net=${chunk['net'].sum():,.0f}  "
                      f"WR={((chunk['net']>0).mean()*100):.1f}%")

    return {
        "raw": {"is_net": raw_is_net, "oos_net": raw_oos_net, "gate": raw_verdict},
        "v2b": {"is_net": is_v2b_net, "oos_net": oos_v2b_net,
                "is_n": is_v2b_n, "oos_n": oos_v2b_n,
                "is_pt": is_v2b_pt, "oos_pt": oos_v2b_pt,
                "gate": verdict_v2b},
    }


def find_best_slices(df: pd.DataFrame, min_n: int = 15):
    """Find individually profitable slices (watcher x dir x conf) for v3 candidate."""
    g = (df.groupby(["watcher","dir","conf"])
          .agg(n=("net","count"), net=("net","sum"),
               wr=("net", lambda x: (x>0).mean()*100),
               per_trade=("net","mean"))
          .reset_index())
    pos = g[(g["net"] > 0) & (g["n"] >= min_n)].sort_values("net", ascending=False)
    print(f"\n  Profitable slices (n>={min_n}):")
    print(pos.to_string(index=False))
    return pos


def stress_costs(df: pd.DataFrame, extra_ticks: float = 1.0, inst_symbol: str = "MNQ"):
    """Stress test with 2x slippage (2 ticks per side instead of 1)."""
    sys.path.insert(0, str(REPO / "backtest"))
    from futures.instruments import MNQ, MES
    inst = MNQ if inst_symbol == "MNQ" else MES
    # Each trade: slippage = slippage_ticks * tick_size * point_value * qty * 2_sides
    extra_cost_per_trade = extra_ticks * inst.tick_size * inst.point_value * 3 * 2
    stressed = df.copy()
    stressed["net"] = stressed["net"] - extra_cost_per_trade
    stressed_total = stressed["net"].sum()
    orig_total = df["net"].sum()
    print(f"\n  Stress test (+{extra_ticks} tick slippage = ${extra_cost_per_trade:.2f}/trade):")
    print(f"    Original: ${orig_total:,.2f}  Stressed: ${stressed_total:,.2f}  Delta: ${stressed_total-orig_total:,.2f}")
    return stressed


def save_results(inst: str, full_g, oos_result: dict):
    path = OUT_DIR / f"futures-{inst.lower()}-native-results.json"
    top_slices = full_g.head(20).to_dict(orient="records")
    data = {
        "instrument": inst,
        "top_slices": top_slices,
        "oos": oos_result,
    }
    path.write_text(json.dumps(data, indent=2))
    print(f"\n  Results saved to {path.name}")


def run_instrument(inst: str):
    print(f"\n\n{'#'*70}")
    print(f"#  {inst} NATIVE REAL-DATA ANALYSIS")
    print(f"{'#'*70}")
    df = load_rows(inst)
    print(f"\nLoaded {len(df):,} signals from {df['date'].min().date()} to {df['date'].max().date()}")

    # Full period analysis
    g, _ = strategy_summary(df, f"{inst} — All signals, full period")

    # OOS walk-forward
    oos = oos_walk_forward(df, inst)

    # Best slices for v3 candidate
    print(f"\n  Best individual slices for v3 config:")
    best = find_best_slices(df)

    # Stress costs
    stress_costs(df, extra_ticks=1.0, inst_symbol=inst)

    # Save
    save_results(inst, g, oos)

    return df, oos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BOTH", choices=["MNQ", "MES", "BOTH"])
    a = ap.parse_args()

    insts = ["MNQ", "MES"] if a.inst == "BOTH" else [a.inst]
    for inst in insts:
        path = DATA_DIR / f"{inst}_native_rows.jsonl"
        if not path.exists():
            print(f"SKIP {inst}: {path} not found. Run drive_native_backtest.py first.")
            continue
        run_instrument(inst)


if __name__ == "__main__":
    main()
