"""Sweep allow_one_blocker_min_spread_cents to find the right guard threshold.

Root cause from vix_soft_perbar_diag:
  - Config E (vix_soft + allow_one_blocker) passes OP-16 at $1,179 edge_capture
  - BUT 4/29 = -$427 (bad 09:45 entry at 16c spread; bad 11:50 entry at 29c spread)
  - 5/04's big winner comes from 11:10 entry at 29c spread — critically 1c below F6 gate

Fix being tested:
  allow_one_blocker_min_spread_cents (N):
    When F6 is the sole non-structural blocker, only bypass it if spread >= N cents.
    This blocks the 4/29 09:45 entry (16c) while allowing 5/04 11:10 entry (29c).

Test range: N = 0 (current E), 10, 15, 20, 25, 27, 29, 30
  N=0  → original allow_one_blocker behavior
  N=25 → blocks 09:45 4/29 (16c), allows 11:10 5/04 (29c)
  N=29 → minimum that would allow 5/04's 29c entry
  N=30 → same as F6 threshold: allow_one_blocker never fires for F6

Output: analysis/recommendations/allow_one_blocker_minspread_sweep.json
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
    vix_soft_mode=True,
    allow_one_blocker=True,
)

J_WINNER_DAYS = {
    "2026-04-29": 342,
    "2026-05-01": 470,
    "2026-05-04": 730,
}
J_LOSER_DAYS = {
    "2026-05-05": -260,
    "2026-05-06": -300,
    "2026-05-07": -165,
}
ALL_DAYS = list(J_WINNER_DAYS) + list(J_LOSER_DAYS)
OP16_FLOOR = 771
MAX_EDGE = 1542

MIN_SPREAD_THRESHOLDS = [0, 10, 15, 20, 25, 27, 29, 30]


def _run_day(spy_df, vix_df, date_str: str, min_spread: int) -> float | None:
    d = dt.date.fromisoformat(date_str)
    spy_window = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_window = vix_df[vix_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    kwargs = {**BASE_KWARGS, "allow_one_blocker_min_spread_cents": min_spread}
    result = run_backtest(
        spy_df=spy_window,
        vix_df=vix_window,
        start_date=d,
        end_date=d,
        **kwargs,
    )
    if not result.trades:
        return None
    return round(sum(t.dollar_pnl for t in result.trades), 2)


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

    print(f"  (All configs use: vix_soft_mode=True, allow_one_blocker=True)")
    print(f"  Testing allow_one_blocker_min_spread_cents: {MIN_SPREAD_THRESHOLDS}\n")

    print(f"{'MinSprd':>8}  {'4/29':>8}  {'5/01':>8}  {'5/04':>8}  {'WinTot':>8}  "
          f"{'5/05':>8}  {'5/06':>8}  {'5/07':>8}  {'EdgeCap':>9}  {'OP16':>5}")
    print("-" * 100)

    all_results = []

    for min_spread in MIN_SPREAD_THRESHOLDS:
        day_pnl: dict[str, float | None] = {}
        for date_str in ALL_DAYS:
            day_pnl[date_str] = _run_day(spy_df, vix_df, date_str, min_spread)

        winner_total = sum((day_pnl.get(d) or 0) for d in J_WINNER_DAYS)
        loser_exposure = sum(max(0, -(day_pnl.get(d) or 0)) for d in J_LOSER_DAYS)
        edge_capture = winner_total - loser_exposure
        op16 = "PASS" if edge_capture >= OP16_FLOOR else "fail"

        def fmt(v) -> str:
            if v is None:
                return "    skip"
            return f"{v:>8.0f}"

        print(f"{min_spread:>7}c  "
              f"{fmt(day_pnl.get('2026-04-29'))}  "
              f"{fmt(day_pnl.get('2026-05-01'))}  "
              f"{fmt(day_pnl.get('2026-05-04'))}  "
              f"{winner_total:>8.0f}  "
              f"{fmt(day_pnl.get('2026-05-05'))}  "
              f"{fmt(day_pnl.get('2026-05-06'))}  "
              f"{fmt(day_pnl.get('2026-05-07'))}  "
              f"{edge_capture:>9.0f}  "
              f"{op16:>5}")

        all_results.append({
            "allow_one_blocker_min_spread_cents": min_spread,
            "per_day_pnl": day_pnl,
            "winner_total": round(winner_total, 2),
            "loser_exposure": round(loser_exposure, 2),
            "edge_capture": round(edge_capture, 2),
            "edge_capture_pct_of_max": round(edge_capture / MAX_EDGE * 100, 1),
            "op16_pass": edge_capture >= OP16_FLOOR,
        })

    # Find best
    best = max(all_results, key=lambda r: r["edge_capture"])
    op16_passing = [r for r in all_results if r["op16_pass"]]

    print(f"\n{'='*100}")
    print(f"J max possible: ${MAX_EDGE}  |  OP-16 floor: ${OP16_FLOOR}")
    print(f"Best edge_capture: min_spread={best['allow_one_blocker_min_spread_cents']}c "
          f"= ${best['edge_capture']:.0f} ({best['edge_capture_pct_of_max']:.1f}%)")
    if op16_passing:
        spreads = [r['allow_one_blocker_min_spread_cents'] for r in op16_passing]
        print(f"OP-16 passing min_spread thresholds: {spreads}")
    else:
        print("No min_spread threshold meets OP-16 floor.")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Find optimal allow_one_blocker_min_spread_cents to fix 4/29 while keeping 5/04",
        "base_config": "vix_soft_mode=True, allow_one_blocker=True",
        "op16_floor": OP16_FLOOR,
        "j_max_edge": MAX_EDGE,
        "best_min_spread": best["allow_one_blocker_min_spread_cents"],
        "best_edge_capture": best["edge_capture"],
        "op16_passing_min_spreads": [r["allow_one_blocker_min_spread_cents"] for r in op16_passing],
        "results": all_results,
    }
    out_path = REPO.parent / "analysis" / "recommendations" / "allow_one_blocker_minspread_sweep.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
