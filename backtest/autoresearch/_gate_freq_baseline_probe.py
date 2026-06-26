"""Probe: establish live-config baseline + tally per-gate SKIP counts (BEAR path).

Read-only diagnostic. Confirms the live engine runs end-to-end on real fills over
the full window, prints {n_trades, total_pnl, WR, exp, monthly rate}, and counts
how many bars each SKIP_* gate action fired (so the leave-one-out audit only
relaxes gates that actually bind on BEAR entries).

NOT a scorecard. Just a sanity probe. $0 cost.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch import runner  # noqa: E402

PARAMS_PATH = REPO / "automation" / "state" / "params.json"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 5, 29)


def _load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))


def _live_config() -> dict:
    p = _load_params()
    p["use_real_fills"] = True
    return p


def main() -> int:
    p = _live_config()
    print("LIVE CONFIG GATE-RELEVANT KNOBS:")
    for k in (
        "min_ribbon_momentum_cents", "max_ribbon_duration_bars", "midday_trendline_gate",
        "vix_bear_hard_cap", "vix_bear_threshold", "entry_no_trade_before_et",
        "entry_no_trade_after_et", "filter_10_min_triggers_bear", "block_level_rejection",
        "entry_bar_body_pct_min", "filter_9_vol_multiplier", "ribbon_min_spread_cents",
        "premium_stop_pct_bear", "tp1_qty_fraction", "per_trade_risk_cap_pct",
    ):
        print(f"   {k}: {p.get(k)}")

    print(f"\nLoading data {FULL_START}..{FULL_END} ...")
    spy, vix = runner.load_data(FULL_START, FULL_END)
    print(f"   spy bars={len(spy)}  vix bars={len(vix)}")

    print("\nRunning live engine (real fills)...")
    result, metrics = runner.run_with_params(p, FULL_START, FULL_END, spy, vix)
    trades = result.trades
    pnls = [float(getattr(t, "dollar_pnl", 0.0)) for t in trades]
    n = len(pnls)
    n_win = sum(1 for x in pnls if x > 0)
    total = sum(pnls)
    # side split
    bear = [t for t in trades if "BULLISH" not in t.setup]
    bull = [t for t in trades if "BULLISH" in t.setup]
    months = (FULL_END.year - FULL_START.year) * 12 + (FULL_END.month - FULL_START.month) + 1

    print("\n=== LIVE BASELINE (full window, real fills) ===")
    print(f"  n_trades        : {n}")
    print(f"  total_pnl       : ${total:+.0f}")
    print(f"  WR              : {100*n_win/n:.1f}%" if n else "  WR: n/a")
    print(f"  per_trade_exp   : ${total/n:+.0f}" if n else "  exp: n/a")
    print(f"  months          : {months}")
    print(f"  trades/month    : {n/months:.2f}")
    print(f"  bear / bull     : {len(bear)} / {len(bull)}")
    print(f"  bear_pnl        : ${sum(t.dollar_pnl for t in bear):+.0f}")
    print(f"  bull_pnl        : ${sum(t.dollar_pnl for t in bull):+.0f}")

    # Gate SKIP histogram across all decisions
    skip_counts = Counter()
    for d in result.decisions:
        a = d.get("action", "")
        if isinstance(a, str) and a.startswith("SKIP_"):
            skip_counts[a] += 1
    print("\n=== SKIP-action histogram (all decisions) ===")
    for a, c in skip_counts.most_common():
        print(f"  {a:<42} {c}")

    # exit reason histogram
    by_exit = Counter()
    for t in trades:
        er = getattr(t, "exit_reason", None)
        key = er.value if hasattr(er, "value") else (str(er) if er else "NONE")
        by_exit[key] += 1
    print("\n=== exit-reason histogram (taken trades) ===")
    for k, c in by_exit.most_common():
        print(f"  {k:<28} {c}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
