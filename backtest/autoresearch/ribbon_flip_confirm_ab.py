"""A/B test: ribbon_flip_price_confirm=False (baseline) vs True (proposed fix).

Tests on all 6 J anchor days. Measures edge_capture per OP-16:
  edge_capture = sum(engine_pnl on J winner days) - sum(max(0, engine_loss on J loser days))
  Min bar = 771 (50% of 1542 max).

USAGE (from backtest/):
    python autoresearch/ribbon_flip_confirm_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backtest"))

from lib.orchestrator import run_backtest
from autoresearch import runner
from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES

REPO = ROOT

J_DAYS = {
    "2026-04-29": {"type": "winner", "j_pnl": 342},
    "2026-05-01": {"type": "winner", "j_pnl": 470},
    "2026-05-04": {"type": "winner", "j_pnl": 730},
    "2026-05-05": {"type": "loser",  "j_pnl": -260},
    "2026-05-06": {"type": "loser",  "j_pnl": -300},
    "2026-05-07": {"type": "loser",  "j_pnl": -165},
}


def build_kwargs(params: dict, start: dt.date, end: dt.date, spy_df, vix_df,
                  ribbon_confirm: bool) -> dict:
    """Build run_backtest kwargs from params + ribbon flag."""
    from autoresearch import config as cfg

    kwargs: dict = {
        "spy_df": spy_df,
        "vix_df": vix_df,
        "start_date": start,
        "end_date": end,
        "use_real_fills": params.get("use_real_fills", False),
        "ribbon_flip_price_confirm": ribbon_confirm,
    }
    direct = (
        "f9_vol_mult",
        "min_triggers_bear", "min_triggers_bull",
        "premium_stop_pct_bear", "premium_stop_pct_bull",
        "strike_offset_bear", "strike_offset_bull",
        "tp1_premium_pct", "tp1_qty_fraction",
        "runner_target_premium_pct",
        "level_stop_buffer_dollars",
        "time_stop_minutes_before_close",
        "profit_lock_threshold_pct",
        "profit_lock_stop_offset_pct",
    )
    for k in direct:
        if k in params:
            kwargs[k] = params[k]
    if "no_trade_before" in params:
        kwargs["no_trade_before"] = cfg.parse_time(params["no_trade_before"])
    if "no_trade_windows" in params:
        parsed = []
        for w in params["no_trade_windows"]:
            s = cfg.parse_time(w[0] if isinstance(w, (list, tuple)) else w.get("start"))
            e = cfg.parse_time(w[1] if isinstance(w, (list, tuple)) else w.get("end"))
            if s and e:
                parsed.append((s, e))
        if parsed:
            kwargs["no_trade_window"] = parsed
    return kwargs


def run_ab():
    params_path = REPO / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    min_d = dt.date(2026, 4, 29)
    max_d = dt.date(2026, 5, 7)
    spy_df, vix_df = runner.load_data(min_d, max_d)

    results = {}
    for confirm_flag in (False, True):
        label = "BASELINE (confirm=False)" if not confirm_flag else "PROPOSED (confirm=True)"
        day_pnl = {}
        for date_str, meta in J_DAYS.items():
            d = dt.date.fromisoformat(date_str)
            kwargs = build_kwargs(params, d, d, spy_df, vix_df, confirm_flag)
            with runner._patched_filter_constants(params):
                bt = run_backtest(**kwargs)
            trades = [t for t in bt.trades if t.entry_time_et.date() == d]
            pnl = sum(t.dollar_pnl for t in trades)
            day_pnl[date_str] = {"pnl": pnl, "n": len(trades)}
            reasons = [str(t.exit_reason) for t in trades]
            print(f"  {date_str} ({meta['type']:6s}): engine_pnl={pnl:+.0f}  "
                  f"n={len(trades)}  exits={reasons}")
        results[label] = day_pnl

    print("\n" + "=" * 70)
    print("A/B COMPARISON — ribbon_flip_price_confirm\n")
    header = f"{'Day':<12} {'J_pnl':>8} {'BASELINE':>10} {'PROPOSED':>10} {'DELTA':>8}"
    print(header)
    print("-" * 55)
    for date_str, meta in J_DAYS.items():
        base_pnl = results["BASELINE (confirm=False)"][date_str]["pnl"]
        prop_pnl = results["PROPOSED (confirm=True)"][date_str]["pnl"]
        delta = prop_pnl - base_pnl
        flag = "  <-- 5/01 KEY" if date_str == "2026-05-01" else ""
        print(f"{date_str:<12} {meta['j_pnl']:>8}  {base_pnl:>10.0f}  {prop_pnl:>10.0f}  {delta:>+8.0f}{flag}")

    print("\nEdge Capture (OP-16):")
    for label, day_pnl in results.items():
        winners = ["2026-04-29", "2026-05-01", "2026-05-04"]
        losers  = ["2026-05-05", "2026-05-06", "2026-05-07"]
        # OP-16 formula: sum(engine_pnl on winner days) - sum(max(0, engine_LOSS on loser days))
        # engine_LOSS = max(0, -engine_pnl): only positive when engine lost money.
        # If engine MADE money on a loser day: loss = 0, no penalty.
        ec = (
            sum(day_pnl[d]["pnl"] for d in winners)
            - sum(max(0, -day_pnl[d]["pnl"]) for d in losers)
        )
        print(f"  {label}: edge_capture={ec:+.0f}  (floor=771, max=1542)")
    print()


if __name__ == "__main__":
    run_ab()
