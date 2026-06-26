"""Wide-band 0DTE OPRA fetch for the EVENT-IV-CRUSH de-bias (backlog #6).

WHY: the existing +/-$5 OPRA cache (backtest/data/options/) drops ~63% of days --
the BIG-MOVE days that are the short iron condor's LOSER days. That biases the
event-day edge upward and leaves the real tail unpriced. To de-bias, we must price
the strikes the move actually travelled to. This tool pulls a WIDE band
(~+/-$18/side around each day's ATM) for the 46 scheduled-event days + a matched
random NON-event sample, into a DEDICATED cache dir so the +/-$5 cache is untouched.

Reuses (no duplication):
  - the 46-event-day list from autoresearch/_event_iv_crush_precheck.build_event_days()
  - the SPY master + ATM-spot conventions from autoresearch/_pivot_premium_selling
  - the per-contract CSV schema + Alpaca creds resolver from fetch_option_data.py

Batch + rate-limit-aware (sleep + exponential backoff on HTTP 429). Writes per
contract CSV to backtest/data/options_event_wide/{symbol}.csv. Pure historical
market-data reads; never places orders. $0 incremental (within the data plan).

Usage:
    python tools/fetch_event_wide_band.py                 # full fetch (event + matched non-event)
    python tools/fetch_event_wide_band.py --max-days 12   # partial (balanced FOMC/CPI/NFP)
    python tools/fetch_event_wide_band.py --check         # report what's cached, no fetch
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
_TOOLS = _HERE.parent
for _p in (str(_BT), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _alpaca_creds import resolve_alpaca_creds                       # noqa: E402
from autoresearch._event_iv_crush_precheck import (                 # noqa: E402
    build_event_days,
    WINDOW_START,
    WINDOW_END,
)
from autoresearch._pivot_premium_selling import (                   # noqa: E402
    _load_spy_master,
    _spot_and_decision,
    _option_cache_dates,
)

ALPACA_DATA_URL = "https://data.alpaca.markets/v1beta1/options/bars"
WIDE_CACHE_DIR = _BT / "data" / "options_event_wide"

# Wide band: +/-$18 each side of ATM, $1 strike grid, BOTH calls and puts.
# +/-$18 covers the ~+/-3% intraday range that big-move event days reach (well beyond
# the cached +/-$5) so the short condor's loser strikes are finally priced.
BAND_HALF_DOLLARS = 18
ENTRY_TIME = dt.time(10, 0)        # match the precheck's 10:00 ET decision/ATM read
NONEVENT_MATCH_SEED = 4242         # deterministic matched non-event draw
BATCH_SIZE = 40                    # symbols per Alpaca request (calls+puts in one go)


def _expiry_yymmdd(d: dt.date) -> str:
    return d.strftime("%y%m%d")


def _occ_symbol(d: dt.date, right: str, strike_dollars: int) -> str:
    """OCC 0DTE SPY symbol, e.g. SPY250115P00580000 ($580 strike)."""
    strike_milli = strike_dollars * 1000
    return f"SPY{_expiry_yymmdd(d)}{right}{strike_milli:08d}"


def wide_band_symbols(d: dt.date, atm_spot: float) -> list[str]:
    """All call+put OCC symbols on the +/-$18 band, $1 grid, around ATM (rounded)."""
    atm = int(round(atm_spot))
    lo = atm - BAND_HALF_DOLLARS
    hi = atm + BAND_HALF_DOLLARS
    syms: list[str] = []
    for strike in range(lo, hi + 1):
        if strike <= 0:
            continue
        syms.append(_occ_symbol(d, "C", strike))
        syms.append(_occ_symbol(d, "P", strike))
    return syms


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def fetch_bars_batch(symbols: list[str], trade_date: str, key: str, secret: str,
                     *, max_retries: int = 6) -> dict[str, list[dict]]:
    """Fetch 5-min RTH bars for a batch of contracts on one day.

    Returns {symbol: [row, ...]} for symbols that have bars. Retries with
    exponential backoff on HTTP 429 (rate limit) and transient URLErrors.
    """
    start_utc = f"{trade_date}T13:30:00Z"   # 09:30 ET
    end_utc = f"{trade_date}T21:00:00Z"     # ~17:00 ET (past 0DTE close)
    out: dict[str, list[dict]] = {}
    page_token = None
    while True:
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "5Min",
            "start": start_utc,
            "end": end_utc,
            "limit": 1000,
        }
        if page_token:
            params["page_token"] = page_token
        url = f"{ALPACA_DATA_URL}?{urlencode(params)}"
        req = Request(url, headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        })
        delay = 1.0
        for attempt in range(max_retries):
            try:
                with urlopen(req, timeout=45) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except HTTPError as e:
                if e.code == 429:
                    print(f"    429 rate-limited; backoff {delay:.1f}s "
                          f"(attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                raise
            except URLError as e:
                print(f"    URLError {e}; backoff {delay:.1f}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
        else:
            raise RuntimeError(f"exhausted retries for {trade_date} batch")

        bars = payload.get("bars", {}) or {}
        for sym, blist in bars.items():
            rows = out.setdefault(sym, [])
            for b in blist or []:
                ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
                ts_et = ts_utc - dt.timedelta(hours=4)
                rows.append({
                    "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
                    "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
                    "volume": b["v"], "vwap": b.get("vw", b["c"]),
                    "trade_count": b.get("n", 0),
                })
        page_token = payload.get("next_page_token")
        if not page_token:
            break
    return out


def write_cache(symbol: str, rows: list[dict]) -> None:
    WIDE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = WIDE_CACHE_DIR / f"{symbol}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "timestamp_et", "open", "high", "low", "close",
            "volume", "vwap", "trade_count",
        ])
        w.writeheader()
        w.writerows(rows)


def already_cached(symbol: str) -> bool:
    p = WIDE_CACHE_DIR / f"{symbol}.csv"
    return p.exists() and p.stat().st_size > 60


def _classify(d: dt.date, ev: dict) -> str:
    if d in set(ev["fomc"]):
        return "FOMC"
    if d in set(ev["cpi"]):
        return "CPI"
    if d in set(ev["nfp"]):
        return "NFP"
    return "?"


def _balanced_subset(event_days: list[dt.date], ev: dict, max_days: int) -> list[dt.date]:
    """Pick a balanced FOMC/CPI/NFP subset of size <= max_days (round-robin by class)."""
    buckets = {"FOMC": [], "CPI": [], "NFP": []}
    for d in event_days:
        buckets[_classify(d, ev)].append(d)
    for v in buckets.values():
        v.sort()
    picked: list[dt.date] = []
    i = 0
    order = ["FOMC", "CPI", "NFP"]
    while len(picked) < max_days and any(buckets[o] for o in order):
        b = order[i % 3]
        if buckets[b]:
            picked.append(buckets[b].pop(0))
        i += 1
    return sorted(picked)


def _spot_for_day(spy, d: dt.date):
    spy_day = spy[spy["date"] == d]
    if spy_day.empty:
        return None
    _, spot, _ = _spot_and_decision(spy_day, ENTRY_TIME)
    return spot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report cache only, no fetch")
    ap.add_argument("--max-days", type=int, default=0,
                    help="cap event days fetched (balanced FOMC/CPI/NFP); 0 = all")
    ap.add_argument("--no-nonevent", action="store_true",
                    help="skip the matched non-event sample (event days only)")
    args = ap.parse_args(argv)

    ev = build_event_days()
    spy = _load_spy_master()
    cache_dates = _option_cache_dates()  # days the +/-$5 cache covers (have 0DTE chains)
    spy_dates = set(spy["date"].unique())
    usable = sorted(spy_dates & cache_dates)
    usable = [d for d in usable if WINDOW_START <= d <= WINDOW_END]
    event_set = set(ev["all"])
    event_days = [d for d in usable if d in event_set]
    nonevent_days = [d for d in usable if d not in event_set]

    if args.max_days and args.max_days < len(event_days):
        event_days = _balanced_subset(event_days, ev, args.max_days)

    # Matched random non-event sample: same n as the event days, balanced over months.
    rng = random.Random(NONEVENT_MATCH_SEED)
    n_match = len(event_days)
    matched_nonevent = (
        [] if args.no_nonevent
        else sorted(rng.sample(nonevent_days, min(n_match, len(nonevent_days))))
    )

    print("=" * 72)
    print("WIDE-BAND EVENT-IV-CRUSH FETCH  (+/-${} band, $1 grid, C+P)".format(BAND_HALF_DOLLARS))
    print("=" * 72)
    print(f"  event days (cache-present, in-window): {len(event_days)}")
    print(f"  matched non-event days             : {len(matched_nonevent)}")
    print(f"  dedicated cache dir                : {WIDE_CACHE_DIR}")

    if args.check:
        cached = len(list(WIDE_CACHE_DIR.glob("*.csv"))) if WIDE_CACHE_DIR.exists() else 0
        print(f"  cached contracts: {cached}")
        return 0

    creds = resolve_alpaca_creds()
    print(f"  Alpaca creds: key={creds.key[:6]}... source={creds.source}  AUTH (will verify on first call)")

    plan: list[tuple[dt.date, str]] = (
        [(d, "EVENT") for d in event_days]
        + [(d, "NONEVENT") for d in matched_nonevent]
    )

    fetched_contracts = 0
    fetched_days = {"EVENT": 0, "NONEVENT": 0}
    bigmove_probe = []  # (date, atm, max_strike_with_bars_distance) for tail-capture check
    per_day_report = []

    for d, kind in plan:
        spot = _spot_for_day(spy, d)
        if spot is None or spot <= 0:
            print(f"  [{kind}] {d}  SKIP (no SPY spot at {ENTRY_TIME})")
            continue
        syms = wide_band_symbols(d, spot)
        klass = _classify(d, ev) if kind == "EVENT" else "-"
        got_for_day = 0
        bars_for_day = 0
        max_dist_with_bars = 0
        date_str = d.strftime("%Y-%m-%d")
        for batch in _chunks(syms, BATCH_SIZE):
            to_fetch = [s for s in batch if not already_cached(s)]
            if not to_fetch:
                # count already-cached toward coverage
                for s in batch:
                    got_for_day += 1
                continue
            try:
                res = fetch_bars_batch(to_fetch, date_str, creds.key, creds.secret)
            except Exception as e:
                print(f"    FAIL batch {date_str}: {e}")
                continue
            for s in to_fetch:
                rows = res.get(s) or []
                if rows:
                    write_cache(s, rows)
                    fetched_contracts += 1
                    got_for_day += 1
                    bars_for_day += len(rows)
                    # distance of this strike from ATM (for tail-capture probe)
                    strike = int(s[-8:]) / 1000.0
                    dist = abs(strike - round(spot))
                    if dist > max_dist_with_bars:
                        max_dist_with_bars = dist
            time.sleep(0.3)  # gentle pacing between batches
        fetched_days[kind] += 1
        atm = int(round(spot))
        per_day_report.append({
            "date": date_str, "kind": kind, "class": klass, "atm": atm,
            "contracts_with_bars": got_for_day, "total_bars": bars_for_day,
            "max_strike_dist_with_bars": max_dist_with_bars,
        })
        bigmove_probe.append((date_str, atm, max_dist_with_bars))
        print(f"  [{kind:8s}] {date_str} {klass:4s} ATM={atm}  "
              f"contracts={got_for_day}/{len(syms)}  bars={bars_for_day}  "
              f"max_strike_dist_with_bars=${max_dist_with_bars:.0f}")

    # Coverage / fill-rate report.
    total_attempted = sum(r["contracts_with_bars"] for r in per_day_report)
    total_possible = sum(
        len(wide_band_symbols(dt.date.fromisoformat(r["date"]), r["atm"]))
        for r in per_day_report
    ) if per_day_report else 0
    fill_rate = round(total_attempted / total_possible, 3) if total_possible else 0.0
    # tail capture: days where bars exist beyond the cached +/-$5 band
    beyond5 = [r for r in per_day_report if r["max_strike_dist_with_bars"] > 5]

    print("\n" + "=" * 72)
    print("COVERAGE REPORT")
    print("=" * 72)
    print(f"  event days fetched     : {fetched_days['EVENT']}")
    print(f"  non-event days fetched : {fetched_days['NONEVENT']}")
    print(f"  contracts pulled (new) : {fetched_contracts}")
    print(f"  contracts w/ bars      : {total_attempted} / {total_possible} "
          f"(wide fill-rate {fill_rate})")
    print(f"  days with bars beyond cached +/-$5: {len(beyond5)} / {len(per_day_report)} "
          f"(== big-move tail captured)")
    # Spot-check: print the widest-tail days
    widest = sorted(per_day_report, key=lambda r: -r["max_strike_dist_with_bars"])[:5]
    print("  widest-tail days (strikes the move reached, now priced):")
    for r in widest:
        print(f"    {r['date']} {r['class']:4s} ATM={r['atm']} "
              f"reached +/-${r['max_strike_dist_with_bars']:.0f} (cache had only +/-$5)")

    summary = {
        "band_half_dollars": BAND_HALF_DOLLARS,
        "event_days_fetched": fetched_days["EVENT"],
        "nonevent_days_fetched": fetched_days["NONEVENT"],
        "contracts_pulled_new": fetched_contracts,
        "contracts_with_bars": total_attempted,
        "contracts_possible": total_possible,
        "wide_fill_rate": fill_rate,
        "days_with_tail_beyond_5": len(beyond5),
        "days_total": len(per_day_report),
        "cache_dir": str(WIDE_CACHE_DIR),
        "per_day": per_day_report,
    }
    out_path = _BT / "autoresearch" / "_state" / "event_wide_fetch_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
