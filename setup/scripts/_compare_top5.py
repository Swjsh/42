"""Compare top 5 robust candidates side-by-side vs v14."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SEARCH_DIR = REPO / "backtest" / "autoresearch" / "_state" / "random_search"

top_seeds = [(6, "A"), (23, "C"), (15, "B"), (9, "A"), (7, "A")]
records: dict[int, dict] = {}
for sid, batch in top_seeds:
    path = SEARCH_DIR / f"batch_{batch}.jsonl"
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("seed") == sid:
                records[sid] = r
                break

v14 = {
    "f9_vol_mult": 0.7, "ribbon_spread_min_cents": 30, "ribbon_flip_lookback_bars": 3,
    "level_proximity_dollars": 0.50, "confluence_tolerance_dollars": 0.30,
    "no_trade_before": "10:00", "no_trade_window_start": "14:00", "no_trade_window_end": "15:00",
    "min_triggers_bear": 1, "min_triggers_bull": 2,
    "premium_stop_pct_bear": -0.08, "premium_stop_pct_bull": -0.10,
    "tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.667, "runner_target_premium_pct": 3.00,
    "level_stop_buffer_dollars": 0.0, "time_stop_minutes_before_close": 10,
    "strike_offset_bear": -2, "strike_offset_bull": -2,
}

knobs = [
    "f9_vol_mult", "ribbon_spread_min_cents", "ribbon_flip_lookback_bars",
    "level_proximity_dollars", "confluence_tolerance_dollars",
    "no_trade_before", "no_trade_window_start", "no_trade_window_end",
    "min_triggers_bear", "min_triggers_bull",
    "premium_stop_pct_bear", "premium_stop_pct_bull",
    "tp1_premium_pct", "tp1_qty_fraction", "runner_target_premium_pct",
    "level_stop_buffer_dollars", "time_stop_minutes_before_close",
    "strike_offset_bear", "strike_offset_bull",
]

# Header
hdr = f"{'KNOB':<32} {'v14':>10} {'SEED 6':>10} {'SEED 23':>10} {'SEED 15':>10} {'SEED 9':>10} {'SEED 7':>10}"
print(hdr)
print("-" * len(hdr))
for k in knobs:
    row = f"{k:<32} {str(v14[k]):>10}"
    for sid, _ in top_seeds:
        v = records[sid]["params"].get(k, "?")
        row += f" {str(v):>10}"
    print(row)

print()
print("=== METRICS ===")
v14_m = {
    "train": {"n_trades": 171, "win_rate": 0.152, "total_pnl": -320.68,
              "sharpe_daily": -0.4136, "wl_ratio": 5.179, "max_drawdown": -1773.84,
              "expectancy": -1.88},
    "val": {"n_trades": 59, "win_rate": 0.2373, "total_pnl": -56.71,
            "sharpe_daily": -0.2427, "wl_ratio": 3.097, "max_drawdown": -575.81,
            "expectancy": -0.96},
}

metric_rows = [
    ("Train trades", "train", "n_trades"),
    ("Train WR%", "train", "win_rate"),
    ("Train PnL$", "train", "total_pnl"),
    ("Train Sharpe", "train", "sharpe_daily"),
    ("Train W/L ratio", "train", "wl_ratio"),
    ("Train Expectancy$", "train", "expectancy"),
    ("Train MaxDD$", "train", "max_drawdown"),
    ("---", "", ""),
    ("Val trades", "val", "n_trades"),
    ("Val WR%", "val", "win_rate"),
    ("Val PnL$", "val", "total_pnl"),
    ("Val Sharpe", "val", "sharpe_daily"),
    ("Val W/L ratio", "val", "wl_ratio"),
    ("Val Expectancy$", "val", "expectancy"),
    ("Val MaxDD$", "val", "max_drawdown"),
]

print(f"{'METRIC':<22} {'v14':>10} {'SEED 6':>10} {'SEED 23':>10} {'SEED 15':>10} {'SEED 9':>10} {'SEED 7':>10}")
print("-" * 92)
for label, scope, key in metric_rows:
    if not scope:
        print("-" * 92)
        continue
    v = v14_m[scope].get(key, 0)
    if "rate" in key:
        v_str = f"{v*100:.1f}%"
    elif key in ("sharpe_daily", "wl_ratio", "expectancy"):
        v_str = f"{v:+.2f}"
    elif key == "n_trades":
        v_str = f"{v}"
    else:
        v_str = f"{v:+.0f}"
    row = f"{label:<22} {v_str:>10}"
    for sid, _ in top_seeds:
        scope_key = "train_metrics" if scope == "train" else "validate_metrics"
        v = records[sid][scope_key].get(key, 0)
        if "rate" in key:
            v_str = f"{v*100:.1f}%"
        elif key in ("sharpe_daily", "wl_ratio", "expectancy"):
            v_str = f"{v:+.2f}"
        elif key == "n_trades":
            v_str = f"{v}"
        else:
            v_str = f"{v:+.0f}"
        row += f" {v_str:>10}"
    print(row)
