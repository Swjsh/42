#!/usr/bin/env python3
"""Kalshi venue reconnaissance — is there tradeable liquidity, or is it a spread bleed?

Phase 0 of any Kalshi lane. Answers ONE question with real data:
  For each candidate series, what is the round-trip friction AT THE MONEY?

Why this exists: Project Gamma's hardest-won lesson (C3 / edge-hunt 2026-06-20) is
"ITM+tight = edge, OTM+wide = bleed". A Kalshi contract settles at $0 or $1, so a 10c
bid/ask spread is a 10% round-trip cost. No probability model survives that. Liquidity
is therefore the GATING fact, not a detail -- and it is free to measure.

Sampling discipline (C4): we do NOT sample arbitrary strikes. Deep-OTM tails are
always wide and would slander the venue. We measure only the ATM band -- contracts
priced where genuine uncertainty lives -- because that is the only band we would trade.

Public market-data endpoints only. No auth, no account, no orders, $0.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# ATM band: contracts priced here carry real uncertainty. Outside it, the market has
# already decided and the spread is meaningless for our purposes.
ATM_LO, ATM_HI = 0.20, 0.80

# Candidate venues, grouped by the thesis each one serves.
SERIES = [
    # --- Second monetization of the signal Gamma ALREADY produces ---
    ("KXINXU",        "S&P 500 hourly range",   "reuse-spy-signal"),
    ("KXINX",         "S&P 500 daily range",    "reuse-spy-signal"),
    ("KXNASDAQ100U",  "Nasdaq-100 hourly range", "reuse-spy-signal"),
    # --- 24/7 coverage, USD-settled (not crypto spot) ---
    ("KXBTCD",        "BTC daily range",        "24-7"),
    ("KXETHD",        "ETH daily range",        "24-7"),
    # --- New alpha: free public NOAA ensembles vs retail crowd ---
    ("KXHIGHNY",      "NYC daily high temp",    "weather"),
    ("KXHIGHCHI",     "Chicago daily high",     "weather"),
    ("KXHIGHMIA",     "Miami daily high",       "weather"),
    ("KXHIGHAUS",     "Austin daily high",      "weather"),
    # --- Macro, where Gamma's scout/news layer already looks ---
    ("KXCPIYOY",      "CPI year-over-year",     "macro"),
    ("KXFED",         "Fed decision",           "macro"),
    # --- Sports, the thing J asked about ---
    ("KXMLBGAME",     "MLB moneyline",          "sports"),
    ("KXNFLGAME",     "NFL moneyline",          "sports"),
]


def _get(path: str, retries: int = 2) -> dict:
    """GET a public endpoint. Returns {} on any failure -- a dead series is data, not a crash."""
    url = f"{BASE}{path}"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gamma-recon/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            if attempt == retries:
                return {"_error": f"HTTP {e.code}"}
        except Exception as e:  # noqa: BLE001 - reconnaissance: never let one series kill the sweep
            if attempt == retries:
                return {"_error": str(e)[:80]}
        time.sleep(1.5 * (attempt + 1))
    return {}


def _price(market: dict, key: str) -> float | None:
    """Kalshi returns both `X_dollars` (string) and legacy `X` (integer cents). Accept either."""
    raw = market.get(f"{key}_dollars")
    if raw not in (None, ""):
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    cents = market.get(key)
    if isinstance(cents, (int, float)) and cents > 0:
        return float(cents) / 100.0
    return None


@dataclass
class SeriesReport:
    series: str
    label: str
    thesis: str
    open_markets: int
    atm_markets: int
    median_spread_cents: float | None
    tightest_spread_cents: float | None
    median_depth_contracts: float | None
    verdict: str
    note: str = ""


def survey_series(ticker: str, label: str, thesis: str, depth_sample: int = 4) -> SeriesReport:
    data = _get(f"/markets?series_ticker={ticker}&status=open&limit=1000")
    if "_error" in data:
        return SeriesReport(ticker, label, thesis, 0, 0, None, None, None,
                            "ERROR", data["_error"])

    markets = data.get("markets", [])
    if not markets:
        return SeriesReport(ticker, label, thesis, 0, 0, None, None, None,
                            "NO-OPEN-MARKETS", "series inactive right now (seasonal or between events)")

    # ATM band only -- see sampling discipline in the module docstring.
    atm: list[tuple[dict, float]] = []
    for m in markets:
        bid, ask = _price(m, "yes_bid"), _price(m, "yes_ask")
        if bid is None or ask is None:
            continue
        if ask <= bid:            # crossed/stale quote
            continue
        mid = (bid + ask) / 2.0
        if ATM_LO <= mid <= ATM_HI:
            atm.append((m, round((ask - bid) * 100, 2)))

    if not atm:
        return SeriesReport(ticker, label, thesis, len(markets), 0, None, None, None,
                            "NO-ATM-QUOTES",
                            "open markets exist but none quoted two-sided in the 20-80c band")

    spreads = [s for _, s in atm]
    # Depth on the tightest few -- that is where we would actually work an order.
    depths: list[float] = []
    for m, _ in sorted(atm, key=lambda p: p[1])[:depth_sample]:
        ob = _get(f"/markets/{m['ticker']}/orderbook")
        book = (ob or {}).get("orderbook") or {}
        for side in ("yes", "no"):
            levels = book.get(side) or []
            if levels:
                # levels are [price, size] pairs; total resting size is the honest depth number
                try:
                    depths.append(float(sum(lv[1] for lv in levels if len(lv) >= 2)))
                except (TypeError, ValueError, IndexError):
                    pass
        time.sleep(0.25)

    med = round(statistics.median(spreads), 2)
    tight = round(min(spreads), 2)
    med_depth = round(statistics.median(depths), 1) if depths else None

    # Verdict thresholds, stated up front so they are falsifiable:
    #   <=2c  round-trip <=2% of notional -- a real probability edge can clear it
    #   <=5c  workable only with a large, well-measured edge
    #   >5c   bleed; the venue eats any realistic model
    if med <= 2:
        verdict = "TRADEABLE"
    elif med <= 5:
        verdict = "MARGINAL"
    else:
        verdict = "BLEED"

    note = ""
    if med_depth is None:
        note = "depth unavailable (orderbook may need auth)"
    elif med_depth < 50:
        note = f"thin book (~{med_depth:.0f} contracts) -- size-capped"

    return SeriesReport(ticker, label, thesis, len(markets), len(atm),
                        med, tight, med_depth, verdict, note)


def main() -> int:
    print("Kalshi venue reconnaissance -- ATM liquidity survey")
    print(f"ATM band: {ATM_LO:.2f}-{ATM_HI:.2f} | thresholds: <=2c TRADEABLE, <=5c MARGINAL, >5c BLEED")
    print("=" * 108)
    print(f"{'SERIES':<15}{'WHAT':<26}{'THESIS':<19}{'OPEN':>5}{'ATM':>5}"
          f"{'MED-SPR':>9}{'TIGHT':>7}{'DEPTH':>8}  VERDICT")
    print("-" * 108)

    reports: list[SeriesReport] = []
    for tkr, label, thesis in SERIES:
        r = survey_series(tkr, label, thesis)
        reports.append(r)
        fmt = lambda v, s="{:.1f}": s.format(v) if v is not None else "-"  # noqa: E731
        print(f"{r.series:<15}{r.label[:25]:<26}{r.thesis:<19}{r.open_markets:>5}{r.atm_markets:>5}"
              f"{fmt(r.median_spread_cents)+'c':>9}{fmt(r.tightest_spread_cents)+'c':>7}"
              f"{fmt(r.median_depth_contracts, '{:.0f}'):>8}  {r.verdict}"
              + (f"  [{r.note}]" if r.note else ""))

    tradeable = [r for r in reports if r.verdict == "TRADEABLE"]
    marginal = [r for r in reports if r.verdict == "MARGINAL"]
    print("-" * 108)
    print(f"TRADEABLE: {len(tradeable)}  MARGINAL: {len(marginal)}  "
          f"BLEED/dead: {len(reports) - len(tradeable) - len(marginal)}")
    if tradeable:
        print("  -> tradeable: " + ", ".join(f"{r.series}({r.median_spread_cents}c)" for r in tradeable))

    out = Path(__file__).resolve().parent / "liquidity-survey.json"
    out.write_text(json.dumps(
        {"surveyed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "atm_band": [ATM_LO, ATM_HI],
         "note": "Snapshot. Weekend/off-hours books are thinner than RTH -- re-run during "
                 "the target session before drawing any conclusion about a series.",
         "reports": [asdict(r) for r in reports]},
        indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
