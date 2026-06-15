"""Fetch SPY 5m price bars, a reconstructed VIX 5m series, and a 0DTE option
strike grid for the *missed offline days* directly from Alpaca, writing CSVs in
the EXACT schema the backtest engine (run.py / orchestrator / option_pricing_real)
expects.

WHY THIS EXISTS
---------------
The machine was offline ~2026-05-23..05-30 (J moved house). yfinance's intraday
feed in this environment lags ~1 week (it returns SPY/VIX only through
2026-05-22), so `tools/fetch_data.py` cannot supply the missed days. Alpaca has
clean SIP data through 05-29 — verified: SPY 5m + 0DTE option 5m bars both return.

VIX INDEX CAVEAT (disclosed per OP-20)
--------------------------------------
Alpaca's equity feed does NOT carry the ^VIX index. It DOES carry VIXY (ProShares
short-term VIX-futures ETF). We reconstruct a VIX *proxy* for the target days by
scaling the VIXY intraday series to the last known real VIX value (from the
existing yfinance vix_5m file, e.g. 16.82 on 2026-05-22). The reconstructed VIX
is used ONLY as a regime gate (bull<17.20 / bear>17.30 rising). It is NOT a
precise 30-day implied-vol figure. Every downstream artifact must label VIX on
the target days as RECONSTRUCTED.

GUARDRAILS
----------
Engine-benefit data infra only (OP-22). Never touches heartbeat*.md / params*.json
and never places orders. Read-mostly: writes only to backtest/data/.

USAGE
-----
    python tools/fetch_missed_days.py \
        --price-start 2026-05-19 --price-end 2026-05-29 \
        --opt-dates 2026-05-26 2026-05-27 2026-05-28 2026-05-29 \
        --strike-lo 735 --strike-hi 765
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Reuse the PROVEN option fetch + cache writer so the option CSV schema is
# byte-for-byte identical to the rest of the cache (avoids L61-style drift).
sys.path.insert(0, str(Path(__file__).parent))
from fetch_option_data import (  # noqa: E402
    fetch_contract_bars,
    write_cache,
    already_cached,
    cache_path,
    ALPACA_KEY,
    ALPACA_SECRET,
)
sys.path.insert(0, str(ROOT))
from lib.option_pricing_real import option_symbol  # noqa: E402

STOCK_URL = "https://data.alpaca.markets/v2/stocks/bars"


def _headers() -> dict:
    return {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}


def fetch_stock_5m(symbol: str, start_date: str, end_date: str) -> list[dict]:
    """All 5m bars from start_date 04:00 ET .. end_date 16:00 ET, ET-stamped.

    Schema rows: timestamp_et, open, high, low, close, volume
    (matches tools/fetch_data.py / the master spy_5m_*.csv files).
    """
    start_utc = f"{start_date}T08:00:00Z"   # 04:00 ET (premarket, for level detection)
    end_utc = f"{end_date}T20:00:00Z"       # 16:00 ET
    rows: list[dict] = []
    page = None
    while True:
        params = {
            "symbols": symbol,
            "timeframe": "5Min",
            "start": start_utc,
            "end": end_utc,
            "feed": "sip",
            "limit": 10000,
        }
        if page:
            params["page_token"] = page
        url = f"{STOCK_URL}?{urlencode(params)}"
        with urlopen(Request(url, headers=_headers()), timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        for b in payload.get("bars", {}).get(symbol, []) or []:
            ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
            ts_et = ts_utc - dt.timedelta(hours=4)  # EDT
            # SPACE separator (not 'T') to match the existing price-CSV convention
            # written by tools/fetch_data.py (yfinance). The orchestrator's
            # _align_vix_to_spy parses with an inferred format; mixing 'T' and space
            # rows in one file makes pandas choke (ValueError at the first odd row).
            rows.append({
                "timestamp_et": ts_et.strftime("%Y-%m-%d %H:%M:%S-04:00"),
                "open": b["o"], "high": b["h"], "low": b["l"],
                "close": b["c"], "volume": int(b["v"]),
            })
        page = payload.get("next_page_token")
        if not page:
            break
    return rows


def write_price_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    df = pd.DataFrame(rows)[cols]
    df.to_csv(path, index=False)


def reconstruct_vix(price_start: str, price_end: str,
                    target_dates: list[str]) -> tuple[list[dict], float]:
    """Real yfinance VIX for pre-gap days + VIXY-scaled proxy for target days.

    Returns (rows, k) where k is the VIX/VIXY scale factor used for disclosure.
    """
    cols = ["timestamp_et", "open", "high", "low", "close", "volume"]
    existing_vix_path = DATA / f"vix_5m_{price_start}_{price_end}.csv"

    # 1. Real VIX rows from yfinance for days BEFORE the gap (<= last real day).
    real_rows: list[dict] = []
    last_real_vix = 16.82  # 2026-05-22 journal fallback
    target_set = set(target_dates)
    if existing_vix_path.exists():
        vdf = pd.read_csv(existing_vix_path)
        vdf["d"] = vdf["timestamp_et"].astype(str).str[:10]
        real = vdf[~vdf["d"].isin(target_set)].copy()
        for _, r in real.iterrows():
            real_rows.append({c: r[c] for c in cols})
        if len(real):
            last_real_vix = float(real.sort_values("timestamp_et").iloc[-1]["close"])

    # 2. VIXY 5m for the whole window (proxy carrier of intraday shape).
    vixy = fetch_stock_5m("VIXY", price_start, price_end)
    vixy_df = pd.DataFrame(vixy)
    vixy_df["d"] = vixy_df["timestamp_et"].astype(str).str[:10]

    # 3. Calibrate k = last_real_vix / VIXY_close_on_last_real_day.
    last_real_day = max((d for d in vixy_df["d"].unique() if d not in target_set),
                        default=None)
    k = 1.0
    if last_real_day is not None:
        ref = vixy_df[vixy_df["d"] == last_real_day]
        vixy_ref_close = float(ref.sort_values("timestamp_et").iloc[-1]["close"])
        if vixy_ref_close > 0:
            k = last_real_vix / vixy_ref_close

    # 4. Build scaled VIX rows for target days from VIXY shape.
    proxy_rows: list[dict] = []
    tgt = vixy_df[vixy_df["d"].isin(target_set)]
    for _, r in tgt.iterrows():
        proxy_rows.append({
            "timestamp_et": r["timestamp_et"],
            "open": round(float(r["open"]) * k, 2),
            "high": round(float(r["high"]) * k, 2),
            "low": round(float(r["low"]) * k, 2),
            "close": round(float(r["close"]) * k, 2),
            "volume": 0,  # synthetic — VIX has no share volume
        })

    all_rows = real_rows + proxy_rows
    all_rows.sort(key=lambda x: x["timestamp_et"])
    return all_rows, k


def fetch_option_grid(dates: list[str], lo: int, hi: int, force: bool) -> tuple[int, int]:
    fetched = skipped = 0
    for date_str in dates:
        td = dt.date.fromisoformat(date_str)
        for strike in range(lo, hi + 1):
            for side in ("C", "P"):
                sym = option_symbol(td, strike, side)
                if already_cached(sym) and not force:
                    skipped += 1
                    continue
                try:
                    rows = fetch_contract_bars(sym, date_str)
                    if rows:
                        write_cache(sym, rows)
                        fetched += 1
                    time.sleep(0.12)
                except Exception as e:  # noqa: BLE001
                    print(f"  FAIL {sym}: {e}")
    return fetched, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-start", required=True)
    ap.add_argument("--price-end", required=True)
    ap.add_argument("--opt-dates", nargs="+", required=True)
    ap.add_argument("--strike-lo", type=int, default=735)
    ap.add_argument("--strike-hi", type=int, default=765)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-options", action="store_true")
    args = ap.parse_args(argv)

    price_cols = ["timestamp_et", "open", "high", "low", "close", "volume"]

    print(f"[1/3] SPY 5m {args.price_start}..{args.price_end} from Alpaca SIP")
    spy_rows = fetch_stock_5m("SPY", args.price_start, args.price_end)
    spy_path = DATA / f"spy_5m_{args.price_start}_{args.price_end}.csv"
    write_price_csv(spy_path, spy_rows, price_cols)
    days = sorted(set(r["timestamp_et"][:10] for r in spy_rows))
    print(f"      wrote {len(spy_rows)} bars -> {spy_path.name}  days={days[0]}..{days[-1]} ({len(days)})")

    print(f"[2/3] VIX reconstruct (real pre-gap + VIXY-scaled targets)")
    vix_rows, k = reconstruct_vix(args.price_start, args.price_end, args.opt_dates)
    vix_path = DATA / f"vix_5m_{args.price_start}_{args.price_end}.csv"
    write_price_csv(vix_path, vix_rows, price_cols)
    print(f"      wrote {len(vix_rows)} bars -> {vix_path.name}  VIX/VIXY scale k={k:.3f}")

    if not args.skip_options:
        print(f"[3/3] Option grid {args.opt_dates} strikes {args.strike_lo}..{args.strike_hi} (C+P)")
        f, s = fetch_option_grid(args.opt_dates, args.strike_lo, args.strike_hi, args.force)
        print(f"      fetched {f} new contracts, {s} already cached/skipped")
    else:
        print("[3/3] skipped options (--skip-options)")

    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
