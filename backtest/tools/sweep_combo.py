"""Combination sweep: premium stop tightness x strike offset, on top of B (min_triggers=1).

Goal: find the configuration that hits PROFITABLE on the 53-day window.

Pre-fetches missing option contracts for any new strikes that fire (ITM-1, ITM-2 etc).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from itertools import product
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


PREMIUM_STOPS = [-0.50, -0.40, -0.33, -0.25]
STRIKE_OFFSETS = [0, -1, -2, +1]   # 0=ATM, -1=ITM-1 puts (strike above spot), -2=ITM-2, +1=OTM-1


def cache_path(symbol):
    return CACHE_DIR / f"{symbol}.csv"


def fetch_contract(symbol, trade_date):
    if cache_path(symbol).exists():
        return True
    params = {"symbols": symbol, "timeframe": "5Min",
              "start": f"{trade_date}T13:30:00Z", "end": f"{trade_date}T20:30:00Z",
              "limit": 200}
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


def discover_and_prefetch(spy, vix, start, end, strike_offset):
    """First-pass BS run to discover which contracts the strike_offset wants, then fetch."""
    result = run_backtest(
        spy, vix, start_date=start, end_date=end,
        use_real_fills=False, min_triggers=1, strike_offset=strike_offset,
    )
    needed = []
    for t in result.trades:
        # Reverse-derive strike from offset
        d = pd.Timestamp(t.entry_time_et).date()
        atm_spot = t.entry_spot
        atm = round(atm_spot)
        strike = atm - strike_offset   # for puts
        sym = f"SPY{d.strftime('%y%m%d')}P{strike * 1000:08d}"
        if not cache_path(sym).exists():
            needed.append((sym, d.isoformat()))
    if needed:
        for sym, d in needed:
            ok = fetch_contract(sym, d)
            if not ok:
                print(f"      FAIL fetch {sym}")
            time.sleep(0.15)


def summarize(trades):
    if not trades:
        return dict(n=0, wr=0, total=0, exp=0, avg_w=0, avg_l=0, wl=0, max_dd=0)
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
    wl = abs(avg_w / avg_l) if avg_l else 0
    return dict(n=n, wr=wr, total=total, exp=total / n if n else 0,
                avg_w=avg_w, avg_l=avg_l, wl=wl, max_dd=max_dd)


def main():
    spy = pd.read_csv(DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv")
    vix = pd.read_csv(DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv")
    start = dt.date(2026, 3, 15)
    end = dt.date(2026, 5, 7)

    # Pre-fetch all contract permutations needed
    print("\nPre-fetching contracts for all strike offsets...")
    for offset in STRIKE_OFFSETS:
        print(f"  offset {offset:+d}:")
        discover_and_prefetch(spy, vix, start, end, offset)

    print("\nRunning sweeps...")
    print(f"\n{'STOP':<6}{'OFFSET':<8}{'N':<5}{'WR':<6}{'AvgW':<7}{'AvgL':<7}"
          f"{'W/L':<7}{'TOTAL':<10}{'EXP':<8}{'MaxDD':<10}{'PASS'}")
    print("-" * 88)
    grid = {}
    for stop in PREMIUM_STOPS:
        for offset in STRIKE_OFFSETS:
            r = run_backtest(spy, vix, start_date=start, end_date=end,
                             use_real_fills=True, min_triggers=1,
                             premium_stop_pct=stop, strike_offset=offset)
            s = summarize(r.trades)
            grid[(stop, offset)] = s
            stop_label = f"{int(stop*100)}%"
            offset_label = "ATM" if offset == 0 else (f"ITM{abs(offset)}" if offset < 0 else f"OTM{offset}")
            passes = sum([
                s["n"] >= 20,
                s["wr"] >= 0.45,
                s["wl"] >= 1.5,
                s["exp"] > 0,
            ])
            print(f"{stop_label:<6}{offset_label:<8}{s['n']:<5}{s['wr']*100:<5.0f}%"
                  f"  ${s['avg_w']:<5.0f} ${s['avg_l']:<5.0f}"
                  f"{s['wl']:<6.2f} ${s['total']:<8.0f}${s['exp']:<6.0f} ${s['max_dd']:<8.0f}{passes}/4")

    # Best by total P&L
    best = max(grid.items(), key=lambda x: x[1]["total"])
    (best_stop, best_off), best_s = best
    off_label = "ATM" if best_off == 0 else (f"ITM{abs(best_off)}" if best_off < 0 else f"OTM{best_off}")
    print(f"\n  BEST by total P&L: stop={int(best_stop*100)}% strike={off_label}  "
          f"-> ${best_s['total']:.0f} ({best_s['n']} trades, {best_s['wr']*100:.0f}% WR, "
          f"${best_s['exp']:.0f}/trade, max DD ${best_s['max_dd']:.0f})")

    # Best by expectancy
    best_exp = max(grid.items(), key=lambda x: x[1]["exp"])
    (be_stop, be_off), be_s = best_exp
    off_label2 = "ATM" if be_off == 0 else (f"ITM{abs(be_off)}" if be_off < 0 else f"OTM{be_off}")
    print(f"  BEST by expectancy: stop={int(be_stop*100)}% strike={off_label2}  "
          f"-> ${be_s['exp']:.0f}/trade ({be_s['n']} trades, {be_s['wr']*100:.0f}% WR)")


if __name__ == "__main__":
    main()
