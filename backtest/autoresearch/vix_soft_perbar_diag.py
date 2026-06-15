"""Per-bar deep dive for Config B (vix_soft) and Config E (allow_one_blocker).

Shows EXACTLY when the engine enters on each J winner day under each config,
what conditions triggered the entry, and what happened after.

Goal: understand why Config E gives -$427 on 4/29 vs +$1,794 on 5/04.
Differentiating signal: what makes 5/04's early 09:35 entry GOOD but 4/29's BAD?

Output:
  - analysis/recommendations/vix_perbar_deep_dive.md  (human-readable)
  - analysis/recommendations/vix_perbar_deep_dive.json (machine-readable)

Cost: $0 (pure Python)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest

BASE_KWARGS = dict(
    use_real_fills=True,
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.08,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.0,
    strike_offset=0,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_trail_pct=0.20,
    f9_vol_mult=0.7,
)

J_WINNERS = [
    {"date": "2026-04-29", "j_entry": "10:25", "j_pnl": 342,
     "note": "Gap-down. Rejection at 711.4. J enters 10:25."},
    {"date": "2026-05-01", "j_entry": "13:36", "j_pnl": 470,
     "note": "Bull ribbon all day. J enters puts at 13:36 trendline test."},
    {"date": "2026-05-04", "j_entry": "10:27", "j_pnl": 730,
     "note": "Strong gap-down continuation. J enters 10:27."},
]

CONFIGS = {
    "A_baseline": {},
    "B_vix_soft": {"vix_soft_mode": True},
    "E_soft_allow": {"vix_soft_mode": True, "allow_one_blocker": True},
}


def analyze_day(spy_df: pd.DataFrame, vix_df: pd.DataFrame, date_str: str, extra: dict) -> dict:
    d = dt.date.fromisoformat(date_str)
    spy_window = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_window = vix_df[vix_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    kwargs = {**BASE_KWARGS, **extra}

    result = run_backtest(
        spy_df=spy_window,
        vix_df=vix_window,
        start_date=d,
        end_date=d,
        **kwargs,
    )

    total_pnl = round(sum(t.dollar_pnl for t in result.trades), 2) if result.trades else None

    # Pull decisions for this day only — 09:35 to 13:30
    day_decisions = []
    for dec in result.decisions:
        ts = str(dec.get("timestamp_et", ""))
        if not ts.startswith(date_str):
            continue
        bar_time_str = ts[11:16]  # HH:MM
        if bar_time_str < "09:35" or bar_time_str > "13:30":
            continue
        day_decisions.append({
            "time": bar_time_str,
            "spy": round(dec.get("spy_close", 0), 2),
            "vix": round(dec.get("vix", 0), 2),
            "ribbon": dec.get("ribbon_stack", "?"),
            "spread_c": dec.get("ribbon_spread_cents", 0),
            "htf": dec.get("htf_15m_stack", "?"),
            "score": dec.get("bear_score", 0),
            "blockers": dec.get("blockers", []),
            "triggers": dec.get("triggers_fired", []),
            "passed": dec.get("passed", False),
        })

    # Entry / exit info
    entries = []
    for t in result.trades:
        entry_t = str(t.entry_time_et)[:16] if t.entry_time_et else "?"
        exit_t = str(t.runner_exit_time_et)[:16] if (hasattr(t, "runner_exit_time_et") and t.runner_exit_time_et) else "?"
        entries.append({
            "direction": t.direction if hasattr(t, "direction") else "?",
            "entry_time": entry_t,
            "exit_time": exit_t,
            "pnl": round(t.dollar_pnl, 2),
            "exit_reason": t.exit_reason if hasattr(t, "exit_reason") else "?",
        })

    return {
        "total_pnl": total_pnl,
        "trades": entries,
        "n_decisions": len(day_decisions),
        "first_pass_bar": next((d for d in day_decisions if d["passed"]), None),
        "first_10_bars": day_decisions[:10],  # 09:35 - 10:20 window
        "all_bars_0935_1330": day_decisions,
    }


def main() -> int:
    data_dir = REPO / "data"
    spy_path = data_dir / "spy_5m_2025-01-01_2026-05-15.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-05-15.csv"
    if not spy_path.exists():
        spy_path = data_dir / "spy_5m_2025-01-01_2026-05-07.csv"
        vix_path = data_dir / "vix_5m_2025-01-01_2026-05-07.csv"

    print(f"Loading {spy_path.name}...")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows\n")

    results = {}
    for j_day in J_WINNERS:
        date_str = j_day["date"]
        results[date_str] = {"j_entry": j_day["j_entry"], "j_pnl": j_day["j_pnl"], "note": j_day["note"]}
        for cfg_label, extra in CONFIGS.items():
            print(f"  {date_str} / {cfg_label}...")
            results[date_str][cfg_label] = analyze_day(spy_df, vix_df, date_str, extra)

    # Print summary table
    print("\n=== ENTRY TIMING COMPARISON ===")
    for j_day in J_WINNERS:
        date_str = j_day["date"]
        dr = results[date_str]
        print(f"\n--- {date_str} (J: {j_day['j_entry']}, +${j_day['j_pnl']}) ---")
        print(f"  Note: {j_day['note']}")
        for cfg in CONFIGS:
            cr = dr[cfg]
            pnl_str = f"${cr['total_pnl']:.0f}" if cr['total_pnl'] is not None else "no trade"
            first_pass = cr["first_pass_bar"]
            first_pass_str = f"{first_pass['time']} (SPY={first_pass['spy']}, spread={first_pass['spread_c']}c, score={first_pass['score']})" if first_pass else "NEVER"
            trades_str = ", ".join(f"{t['direction']} @{t['entry_time']} [{t['exit_reason']}] {t['pnl']:.0f}" for t in cr["trades"])
            print(f"  {cfg:25s}  pnl={pnl_str:>8}  first_pass={first_pass_str}")
            if cr["trades"]:
                print(f"    trades: {trades_str}")

    # Print first-10-bars detail for 4/29 and 5/04 under E_soft_allow
    for j_day in J_WINNERS:
        date_str = j_day["date"]
        if date_str not in ("2026-04-29", "2026-05-04"):
            continue
        cr = results[date_str]["E_soft_allow"]
        print(f"\n=== {date_str} bar detail (Config E) ===")
        print(f"{'Time':>5}  {'SPY':>7}  {'VIX':>5}  {'Ribbon':>7}  {'Spread':>7}  {'HTF':>6}  {'Score':>5}  {'Pass':>5}  Blockers / Triggers")
        for bar in cr["all_bars_0935_1330"]:
            pass_str = "PASS" if bar["passed"] else "----"
            blk = ",".join(str(b) for b in bar["blockers"]) if bar["blockers"] else "-"
            trg = ",".join(bar["triggers"]) if bar["triggers"] else "-"
            print(f"  {bar['time']:>5}  {bar['spy']:>7.2f}  {bar['vix']:>5.2f}  {bar['ribbon']:>7}  {bar['spread_c']:>6.0f}c  {bar['htf']:>6}  {bar['score']:>5}  {pass_str:>5}  {blk}  {trg}")

    # Save JSON
    out_path = REPO.parent / "analysis" / "recommendations" / "vix_perbar_deep_dive.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
