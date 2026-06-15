"""VIX filter mode sweep — find the F8 relaxation that captures J's winner days.

Root cause (from winner_day_entry_blocker_diag.py):
  - F8 (VIX > 17.30 AND vix_rising) is the #1 blocker across all 3 winner days.
  - 4/29 + 5/04: VIX > 17.30 all day but FLAT (not rising) → F8 hard-blocks for hours
  - 5/01: VIX < 17.30 all day → F8 hard-blocks entirely (bear setup never fires)

Test configs:
  A. baseline  — current (VIX > 17.30 AND rising, hard block)
  B. soft      — vix_soft_mode=True (direction becomes score modifier, not hard block)
  C. level_17  — disable_filters=[8] + VIX > 17.30 check moved to score (no direction)
  D. level_15  — disable_filters=[8] (VIX removed entirely from hard gates)
  E. soft_nof7 — vix_soft + disable F7 (also relax volume divergence gate)

Output: analysis/recommendations/vix_mode_edge_sweep.json
Usage: python backtest/autoresearch/vix_mode_edge_sweep.py
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

# ---------------------------------------------------------------------------
# J's source-of-truth days
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Base config (Safe-ATM)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Sweep configs
# ---------------------------------------------------------------------------
CONFIGS = [
    {
        "label": "A_baseline",
        "desc": "Current production: VIX>17.30 AND rising (hard block)",
        "extra": {},
    },
    {
        "label": "B_vix_soft",
        "desc": "vix_soft_mode=True: direction is score demerit only, not hard block",
        "extra": {"vix_soft_mode": True},
    },
    {
        "label": "C_disable_f8",
        "desc": "disable_filters=[8]: F8 entirely removed (VIX not checked at all)",
        "extra": {"disable_filters": [8]},
    },
    {
        "label": "D_disable_f7_f8",
        "desc": "disable_filters=[7,8]: Remove VIX + volume divergence gates",
        "extra": {"disable_filters": [7, 8]},
    },
    {
        "label": "E_soft_allow_blocker",
        "desc": "vix_soft + allow_one_blocker: allows 1 hard block besides VIX",
        "extra": {"vix_soft_mode": True, "allow_one_blocker": True},
    },
]


def _run_day(spy_df, vix_df, date_str: str, extra_kwargs: dict) -> float | None:
    d = dt.date.fromisoformat(date_str)
    spy_window = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_window = vix_df[vix_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    kwargs = {**BASE_KWARGS, **extra_kwargs}
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
    # Load data
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

    print(f"{'Config':>20}  {'4/29':>8}  {'5/01':>8}  {'5/04':>8}  {'WinTot':>8}  "
          f"{'5/05':>8}  {'5/06':>8}  {'5/07':>8}  {'EdgeCap':>9}  {'OP16':>5}")
    print("-" * 105)

    all_results = []

    for cfg in CONFIGS:
        label = cfg["label"]
        extra = cfg["extra"]

        day_pnl: dict[str, float | None] = {}
        for date_str in ALL_DAYS:
            day_pnl[date_str] = _run_day(spy_df, vix_df, date_str, extra)

        winner_total = sum((day_pnl.get(d) or 0) for d in J_WINNER_DAYS)
        loser_exposure = sum(max(0, -(day_pnl.get(d) or 0)) for d in J_LOSER_DAYS)
        edge_capture = winner_total - loser_exposure
        op16 = "PASS" if edge_capture >= OP16_FLOOR else "fail"

        def fmt(v) -> str:
            if v is None:
                return "    skip"
            return f"{v:>8.0f}"

        print(f"{label:>20}  "
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
            "label": label,
            "desc": cfg["desc"],
            "extra_kwargs": {k: str(v) for k, v in extra.items()},
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

    print(f"\n{'='*105}")
    print(f"J max possible: ${MAX_EDGE}  |  OP-16 floor: ${OP16_FLOOR}")
    print(f"Best edge_capture: {best['label']} = ${best['edge_capture']:.0f} ({best['edge_capture_pct_of_max']:.1f}%)")
    if op16_passing:
        print(f"OP-16 passing: {[r['label'] for r in op16_passing]}")
    else:
        print("No config meets OP-16 floor. VIX relaxation alone insufficient.")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Sweep VIX filter modes to find which relaxation captures J winner days",
        "op16_floor": OP16_FLOOR,
        "j_max_edge": MAX_EDGE,
        "best_label": best["label"],
        "best_edge_capture": best["edge_capture"],
        "op16_passing_configs": [r["label"] for r in op16_passing],
        "configs": all_results,
    }
    out_path = REPO.parent / "analysis" / "recommendations" / "vix_mode_edge_sweep.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
