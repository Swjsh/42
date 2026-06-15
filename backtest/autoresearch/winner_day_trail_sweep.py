"""Winner-day trail-pct sweep — T-2026-05-18-02.

Sweeps profit_lock_trail_pct on the 3 J winner days (4/29, 5/01, 5/04) to find
the minimum trail percentage that captures the sustained-trend moves.

Current production: trail=0.20 (20% off HWM). Engine loses on all 3 winner days.
J's P&L: $342 + $470 + $730 = $1,542 max edge.

Usage: python backtest/autoresearch/winner_day_trail_sweep.py
Output: analysis/recommendations/winner_day_trail_sweep.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import os
from pathlib import Path

# repo root
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

OUT_PATH = REPO / "analysis" / "recommendations" / "winner_day_trail_sweep.json"

J_WINNER_PNL = {
    "2026-04-29": 342,
    "2026-05-01": 470,
    "2026-05-04": 730,
}
J_LOSER_PNL = {
    "2026-05-05": -260,
    "2026-05-06": -300,
    "2026-05-07": -165,  # combined two trades
}

WINNER_DAYS = sorted(J_WINNER_PNL.keys())
LOSER_DAYS = sorted(J_LOSER_PNL.keys())
ALL_DAYS = WINNER_DAYS + LOSER_DAYS

# Production v15.1 profit-lock params
LOCK_THRESHOLD = 0.05   # arm at +5% favor
LOCK_OFFSET = 0.10      # floor at +10% when armed

# Trail percentages to sweep
TRAIL_VARIANTS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]

# ATM strike config (best-performing in T-10)
# Safe-$1K: premium_stop_pct_bear=-0.08 (safe), strike_offset=0 (ATM)
SAFE_ATM_KWARGS: dict = dict(
    use_real_fills=True,
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.08,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.0,
    strike_offset=0,            # ATM
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,       # v15.1 — no dead window
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=LOCK_THRESHOLD,
    profit_lock_stop_offset_pct=LOCK_OFFSET,
)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _run_day(
    spy_df,
    vix_df,
    date_str: str,
    trail_pct: float,
    extra_kwargs: dict,
) -> float | None:
    """Run backtest for a single date. Returns dollar P&L or None if no trade."""
    d = _parse_date(date_str)
    result = run_backtest(
        spy_df=spy_df,
        vix_df=vix_df,
        start_date=d,
        end_date=d,
        profit_lock_trail_pct=trail_pct,
        **extra_kwargs,
    )
    if not result.trades:
        return None
    return round(sum(t.dollar_pnl for t in result.trades), 2)


def main() -> None:
    # Load data (covers all 3 winner + 3 loser days: 4/29, 5/01, 5/04, 5/05, 5/06, 5/07)
    data_dir = REPO / "backtest" / "data"
    spy_path = data_dir / "spy_5m_2025-01-01_2026-05-15.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-05-15.csv"
    if not spy_path.exists():
        # fallback to 2026-05-07 master
        spy_path = data_dir / "spy_5m_2025-01-01_2026-05-07.csv"
        vix_path = data_dir / "vix_5m_2025-01-01_2026-05-07.csv"

    print(f"Loading SPY + VIX data from {spy_path.name}...")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    # Filter to the window we need (4/29 through 5/07 2026)
    spy_df = spy_df[
        (spy_df["timestamp_et"] >= "2026-04-29") &
        (spy_df["timestamp_et"] <= "2026-05-07T23:59:59")
    ].reset_index(drop=True)
    vix_df = vix_df[
        (vix_df["timestamp_et"] >= "2026-04-29") &
        (vix_df["timestamp_et"] <= "2026-05-07T23:59:59")
    ].reset_index(drop=True)
    print(f"Loaded {len(spy_df)} SPY bars, {len(vix_df)} VIX bars (window: 4/29-5/07 2026)")

    results: dict = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "purpose": "Sweep profit_lock_trail_pct on 3 J winner days to find optimal trail",
        "production_trail_pct": 0.20,
        "j_winner_pnl": J_WINNER_PNL,
        "j_winner_total": sum(J_WINNER_PNL.values()),
        "j_loser_pnl": J_LOSER_PNL,
        "config": "Safe-ATM (strike_offset=0, premium_stop=-8%, tp1=+30%)",
        "variants": [],
    }

    print(f"\n{'Trail':>7}  {'4/29':>8}  {'5/01':>8}  {'5/04':>8}  {'Winners':>9}  {'5/05':>8}  {'5/06':>8}  {'5/07':>8}  {'EdgeCapture':>12}")
    print("-" * 90)

    for trail_pct in TRAIL_VARIANTS:
        kwargs = {**SAFE_ATM_KWARGS}

        day_pnl: dict[str, float | None] = {}
        for date_str in ALL_DAYS:
            pnl = _run_day(spy_df, vix_df, date_str, trail_pct, kwargs)
            day_pnl[date_str] = pnl

        winner_total = sum(
            (day_pnl.get(d) or 0) for d in WINNER_DAYS
        )
        loser_sum = sum(
            max(0, -(day_pnl.get(d) or 0)) for d in LOSER_DAYS
        )
        edge_capture = winner_total - loser_sum

        variant_rec = {
            "trail_pct": trail_pct,
            "per_day": day_pnl,
            "winner_total": round(winner_total, 2),
            "loser_exposure": round(loser_sum, 2),
            "edge_capture": round(edge_capture, 2),
        }
        results["variants"].append(variant_rec)

        def fmt(v: float | None) -> str:
            if v is None:
                return "    skip"
            return f"{v:>8.0f}"

        print(
            f"{trail_pct:>7.0%}  "
            f"{fmt(day_pnl.get('2026-04-29'))}  "
            f"{fmt(day_pnl.get('2026-05-01'))}  "
            f"{fmt(day_pnl.get('2026-05-04'))}  "
            f"{winner_total:>9.0f}  "
            f"{fmt(day_pnl.get('2026-05-05'))}  "
            f"{fmt(day_pnl.get('2026-05-06'))}  "
            f"{fmt(day_pnl.get('2026-05-07'))}  "
            f"{edge_capture:>12.0f}"
        )

    # Find best (highest edge_capture) and first variant that meets OP-16 floor
    OP16_FLOOR = 771
    best = max(results["variants"], key=lambda v: v["edge_capture"])
    passing = [v for v in results["variants"] if v["edge_capture"] >= OP16_FLOOR]
    results["best_trail_pct"] = best["trail_pct"]
    results["best_edge_capture"] = best["edge_capture"]
    results["op16_floor"] = OP16_FLOOR
    results["op16_passing_variants"] = [v["trail_pct"] for v in passing]
    results["verdict"] = "OP16_MET" if passing else "OP16_MISS_NEED_MORE_CHANGES"
    results["recommendation"] = (
        f"Use trail_pct={passing[0]['trail_pct']:.2f} (first OP-16 pass, edge_capture={passing[0]['edge_capture']:.0f})"
        if passing else
        f"Best trail_pct={best['trail_pct']:.2f} still misses OP-16 (edge_capture={best['edge_capture']:.0f} < {OP16_FLOOR}). "
        "Root cause may require exit redesign beyond chandelier trail widening (e.g., underlying-price-based runner stop)."
    )

    print(f"\n{'='*90}")
    print(f"Best: trail={best['trail_pct']:.0%}  edge_capture=${best['edge_capture']:.0f}")
    print(f"OP-16 floor: ${OP16_FLOOR}  |  Passing variants: {[v['trail_pct'] for v in passing]}")
    print(f"Verdict: {results['verdict']}")
    print(f"Rec: {results['recommendation']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nOutput: {OUT_PATH}")


if __name__ == "__main__":
    main()
