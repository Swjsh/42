"""Sweep multiple filter configurations across the full backtest window.

Tests entry-tuning hypotheses without changing exit logic (which is already
ratified at v8). Each config holds the v8 exits constant and varies entry filters.

Configs benchmarked:
  A — BASELINE: production rules (>=2 triggers, VIX hard, all 10 must pass)
  B — RELAX-TRIGGERS: >=1 of 4 triggers (catches early single-trigger rejections)
  C — VIX-SOFT: filter 8 becomes -1 score modifier, not hard blocker
  D — ONE-SLACK: allow up to 1 non-structural filter blocked (9/10 effective)

Output: side-by-side table showing trade count, WR, P&L, drawdown, expectancy.
Pre-fetches any new option contracts that fire on configs B/C/D so all stats
use real OPRA fills.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.orchestrator import run_backtest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"
CACHE_DIR = DATA_DIR / "options"
ALPACA_KEY = "PK33J2RV4PNIY6TCOLUG3WYGRX"
ALPACA_SECRET = "FxbJshSbhJ8Rn7KPENssS4eWsLpxCyYeyxavxywV9Bbs"
OPT_URL = "https://data.alpaca.markets/v1beta1/options/bars"


CONFIGS = [
    {
        "name": "A_BASELINE",
        "label": "production_rules_v8",
        "min_triggers": 2,
        "vix_soft_mode": False,
        "allow_one_blocker": False,
        "desc": "v8 doctrine — >=2 triggers, VIX hard, all 10 filters must pass",
    },
    {
        "name": "B_RELAX_TRIGGERS",
        "label": "v8_relax_triggers_1",
        "min_triggers": 1,
        "vix_soft_mode": False,
        "allow_one_blocker": False,
        "desc": "Drop filter 10 to >=1 trigger — catches single-rejection setups",
    },
    {
        "name": "C_VIX_SOFT",
        "label": "v8_vix_soft",
        "min_triggers": 2,
        "vix_soft_mode": True,
        "allow_one_blocker": False,
        "desc": "Filter 8 (VIX) becomes -1 score modifier, not hard block",
    },
    {
        "name": "D_ONE_SLACK",
        "label": "v8_one_slack",
        "min_triggers": 2,
        "vix_soft_mode": False,
        "allow_one_blocker": True,
        "desc": "Allow up to 1 non-structural filter blocked (effectively 9/10)",
    },
]


def cache_path(symbol):
    return CACHE_DIR / f"{symbol}.csv"


def fetch_contract(symbol, trade_date):
    """Fetch a single 0DTE contract's 5-min bars and cache."""
    if cache_path(symbol).exists():
        return True
    start_utc = f"{trade_date}T13:30:00Z"
    end_utc = f"{trade_date}T20:30:00Z"
    params = {"symbols": symbol, "timeframe": "5Min",
              "start": start_utc, "end": end_utc, "limit": 200}
    req = Request(f"{OPT_URL}?{urlencode(params)}",
                  headers={"APCA-API-KEY-ID": ALPACA_KEY,
                           "APCA-API-SECRET-KEY": ALPACA_SECRET})
    try:
        data = json.loads(urlopen(req, timeout=30).read())
        bars = data.get("bars", {}).get(symbol, [])
        if not bars:
            return False
        rows = []
        for b in bars:
            ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
            ts_et = ts_utc - dt.timedelta(hours=4)
            rows.append({
                "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
                "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
                "volume": b["v"], "vwap": b.get("vw", b["c"]),
                "trade_count": b.get("n", 0),
            })
        import csv
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path(symbol), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "timestamp_et", "open", "high", "low", "close",
                "volume", "vwap", "trade_count"])
            w.writeheader()
            w.writerows(rows)
        return True
    except Exception:
        return False


def derive_symbol_from_trade(t):
    d = t.entry_time_et.date() if hasattr(t.entry_time_et, "date") else \
        pd.Timestamp(t.entry_time_et).date()
    return f"SPY{d.strftime('%y%m%d')}P{int(t.strike) * 1000:08d}"


def run_one_config(spy, vix, start, end, config):
    """Run backtest with given config + pre-fetch any missing contracts."""
    # First pass: BS pricing (fast) to discover which contracts the config wants
    result_discovery = run_backtest(
        spy, vix, start_date=start, end_date=end,
        use_real_fills=False,
        min_triggers=config["min_triggers"],
        vix_soft_mode=config["vix_soft_mode"],
        allow_one_blocker=config["allow_one_blocker"],
    )

    # Pre-fetch any contracts we don't have yet
    needed = []
    for t in result_discovery.trades:
        sym = derive_symbol_from_trade(t)
        if not cache_path(sym).exists():
            d = t.entry_time_et.date() if hasattr(t.entry_time_et, "date") else \
                pd.Timestamp(t.entry_time_et).date()
            needed.append((sym, d.isoformat()))

    if needed:
        print(f"    fetching {len(needed)} new contract(s)...")
        for sym, d in needed:
            ok = fetch_contract(sym, d)
            print(f"      {'ok  ' if ok else 'FAIL'} {sym}")
            time.sleep(0.2)

    # Second pass: real fills
    result = run_backtest(
        spy, vix, start_date=start, end_date=end,
        use_real_fills=True,
        min_triggers=config["min_triggers"],
        vix_soft_mode=config["vix_soft_mode"],
        allow_one_blocker=config["allow_one_blocker"],
    )
    return result


def summarize(result):
    """Compute key stats."""
    trades = result.trades
    if not trades:
        return {
            "n_trades": 0, "wr": 0, "n_wins": 0, "n_losses": 0,
            "avg_winner": 0, "avg_loser": 0, "wl_ratio": 0,
            "total_pnl": 0, "expectancy": 0, "max_dd": 0,
        }
    n = len(trades)
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    avg_w = sum(t.dollar_pnl for t in wins) / max(1, len(wins))
    avg_l = sum(t.dollar_pnl for t in losses) / max(1, len(losses))
    total = sum(t.dollar_pnl for t in trades)

    def _naive(ts):
        if hasattr(ts, "tz_localize") and ts.tz is not None:
            return ts.tz_localize(None)
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts
    cum, peak, max_dd = 0, 0, 0
    for t in sorted(trades, key=lambda t: _naive(t.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    wr = len(wins) / n if n else 0
    wl = abs(avg_w / avg_l) if avg_l else float("inf")
    expectancy = total / n if n else 0
    return {
        "n_trades": n, "wr": wr, "n_wins": len(wins), "n_losses": len(losses),
        "avg_winner": avg_w, "avg_loser": avg_l, "wl_ratio": wl,
        "total_pnl": total, "expectancy": expectancy, "max_dd": max_dd,
    }


def main():
    spy_path = DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv"
    vix_path = DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv"
    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)

    start = dt.date.fromisoformat("2026-03-15")
    end = dt.date.fromisoformat("2026-05-07")
    n_days = (end - start).days

    print(f"\nWindow: {start} to {end} ({n_days} calendar days, ~{n_days * 5 // 7} trading days)\n")

    results = {}
    for cfg in CONFIGS:
        print(f"  {cfg['name']}: {cfg['desc']}")
        r = run_one_config(spy, vix, start, end, cfg)
        s = summarize(r)
        results[cfg["name"]] = s
        print(f"    -> {s['n_trades']} trades, "
              f"{s['n_wins']}W/{s['n_losses']}L = {s['wr']*100:.0f}% WR, "
              f"${s['total_pnl']:.0f} P&L, ${s['expectancy']:.0f}/trade")

    # Side-by-side table
    print("\n" + "=" * 95)
    print("FILTER CONFIG SWEEP — side-by-side")
    print("=" * 95)
    metrics = [
        ("Trades fired", "n_trades", "{:d}"),
        ("Win rate", "wr", "{:.0%}"),
        ("Avg winner", "avg_winner", "${:.0f}"),
        ("Avg loser", "avg_loser", "${:.0f}"),
        ("W/L ratio", "wl_ratio", "{:.2f}x"),
        ("Total P&L", "total_pnl", "${:.0f}"),
        ("Expectancy/trade", "expectancy", "${:.0f}"),
        ("Max drawdown", "max_dd", "${:.0f}"),
    ]
    print(f"  {'Metric':<20}  {'A_BASELINE':<15}  {'B_RELAX_TRIG':<15}  "
          f"{'C_VIX_SOFT':<15}  {'D_ONE_SLACK':<15}")
    print("  " + "-" * 89)
    for label, key, fmt in metrics:
        row = [fmt.format(results[c["name"]][key]) for c in CONFIGS]
        print(f"  {label:<20}  {row[0]:<15}  {row[1]:<15}  {row[2]:<15}  {row[3]:<15}")

    # Live deployment threshold check per config
    print("\n  LIVE DEPLOYMENT SCORECARD (4 thresholds):")
    print(f"  {'Config':<15}  {'Trades>=20':<10} {'WR>=45%':<8} {'WL>=1.5x':<8} {'Exp>0':<6} {'PASS':<5}")
    for cfg in CONFIGS:
        s = results[cfg["name"]]
        c1 = s["n_trades"] >= 20
        c2 = s["wr"] >= 0.45
        c3 = s["wl_ratio"] >= 1.5
        c4 = s["expectancy"] > 0
        passes = sum([c1, c2, c3, c4])
        print(
            f"  {cfg['name']:<15}  "
            f"{('PASS' if c1 else 'fail'):<10}"
            f"{('PASS' if c2 else 'fail'):<8}"
            f"{('PASS' if c3 else 'fail'):<8}"
            f"{('PASS' if c4 else 'fail'):<6}"
            f"{passes}/4"
        )

    return results


if __name__ == "__main__":
    main()
