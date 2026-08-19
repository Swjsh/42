"""Options-liquidity screen — of what is HOT, what is actually TRADEABLE at $5K?

J's directive (2026-08-18): the six named tickers were "just random tickers... we need to do
more than that depending on what's hot, what's the sector."

The sector-heat scanner answers "what's hot." It is a SELECTION layer and deliberately knows
nothing about options. This screen answers the second, harder half: a leading sector is
worthless to this lane if its options carry a 20% spread or price a 3-lot beyond the account's
per-trade cap. Hot AND tradeable is a much smaller set than hot.

Method: for each symbol, pull spot, find the nearest listed expiry >= min DTE, snapshot the
ATM call, and compute spread as a % of premium plus the 3-contract cost against the risk cap.
Classification thresholds come from params.json's own live liquidity gate -- not invented here.

Reads only. Places no orders. $0 (already-wired paper market-data key).

CAVEAT, PERMANENT: quotes come from Alpaca's free INDICATIVE feed (this account has no OPRA
agreement), and a snapshot taken outside RTH runs wider than the same contract intraday. Treat
the spread column as a RANKING signal, not a quotable number, and re-verify before trading.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402

DATA_HOST = "https://data.alpaca.markets"
PAPER_HOST = "https://paper-api.alpaca.markets"
PARAMS = REPO / "automation" / "state" / "weekly" / "params.json"
OUT = REPO / "analysis" / "weekly-lane" / "universe-liquidity-screen.json"


class ScreenError(RuntimeError):
    """Fail loud rather than emit a screen with silently-missing symbols."""


def _get(url: str, params: dict, key: str, secret: str, timeout: int = 25) -> dict:
    req = Request(f"{url}?{urlencode(params)}",
                  headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                           "accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        raise ScreenError(f"HTTP {e.code} {url}: {e.read().decode(errors='replace')[:200]}") from e
    except (URLError, TimeoutError) as e:
        raise ScreenError(f"network failure {url}: {e}") from e


def spot_for(symbols: list[str], key: str, secret: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i + 50]
        d = _get(f"{DATA_HOST}/v2/stocks/snapshots", {"symbols": ",".join(chunk), "feed": "iex"},
                 key, secret)
        for sym, snap in (d or {}).items():
            bar = (snap or {}).get("dailyBar") or (snap or {}).get("prevDailyBar") or {}
            if bar.get("c"):
                out[sym] = float(bar["c"])
    return out


def nearest_expiry(symbol: str, min_dte: int, key: str, secret: str) -> dt.date | None:
    today = dt.date.today()
    d = _get(f"{PAPER_HOST}/v2/options/contracts", {
        "underlying_symbols": symbol, "status": "active",
        "expiration_date_gte": (today + dt.timedelta(days=min_dte)).isoformat(),
        "expiration_date_lte": (today + dt.timedelta(days=min_dte + 21)).isoformat(),
        "limit": 2000,
    }, key, secret)
    exps = sorted({c["expiration_date"] for c in (d.get("option_contracts") or [])})
    return dt.date.fromisoformat(exps[0]) if exps else None


def screen_symbol(symbol: str, spot: float, min_dte: int, cap_dollars: float,
                  key: str, secret: str) -> dict:
    row: dict = {"symbol": symbol, "spot": round(spot, 2)}
    exp = nearest_expiry(symbol, min_dte, key, secret)
    if exp is None:
        row.update(ok=False, reason="no listed expiry in the min-DTE window")
        return row
    row["expiry"] = exp.isoformat()
    row["dte"] = (exp - dt.date.today()).days
    band = max(spot * 0.03, 1.0)
    chain = _get(f"{DATA_HOST}/v1beta1/options/snapshots/{symbol}", {
        "feed": "indicative", "expiration_date": exp.isoformat(), "type": "call",
        "strike_price_gte": round(spot - band, 2), "strike_price_lte": round(spot + band, 2),
        "limit": 60,
    }, key, secret)
    snaps = chain.get("snapshots") or {}
    if not snaps:
        row.update(ok=False, reason="no ATM-band snapshots returned")
        return row

    best = None
    for occ, s in snaps.items():
        q = (s or {}).get("latestQuote") or {}
        bid, ask = q.get("bp"), q.get("ap")
        if not bid or not ask or ask <= 0 or bid <= 0:
            continue
        try:
            strike = int(occ[-8:]) / 1000.0
        except ValueError:
            continue
        mid = (bid + ask) / 2.0
        cand = {"occ": occ, "strike": strike, "bid": bid, "ask": ask, "mid": mid,
                "spread_pct": 100.0 * (ask - bid) / mid,
                "oi": (s or {}).get("openInterest"),
                "dist": abs(strike - spot)}
        if best is None or cand["dist"] < best["dist"]:
            best = cand
    if best is None:
        row.update(ok=False, reason="no two-sided quotes in the ATM band")
        return row

    cost3 = best["mid"] * 3 * 100.0
    row.update(
        ok=True, atm_strike=best["strike"], bid=best["bid"], ask=best["ask"],
        mid=round(best["mid"], 3), spread_pct=round(best["spread_pct"], 2),
        open_interest=best["oi"], cost_3_contracts=round(cost3, 2),
        fits_risk_cap=cost3 <= cap_dollars,
    )
    return row


def classify(row: dict, max_spread_pct: float) -> str:
    if not row.get("ok"):
        return "UNSCREENABLE"
    if row["spread_pct"] > max_spread_pct * 3:
        return "AVOID"
    if row["spread_pct"] > max_spread_pct:
        return "TIER2_spread_discipline"
    if not row["fits_risk_cap"]:
        return "TIER2_too_expensive_for_3_lots"
    return "TIER1_tradeable"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", required=True, help="comma-separated")
    ap.add_argument("--cap-dollars", type=float, default=1500.0)
    args = ap.parse_args(argv)

    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    min_dte = int(params["entry"]["min_dte_at_entry"])
    max_spread = float(params["entry"]["liquidity_gate"]["max_spread_pct_of_premium"])

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    creds = resolve_alpaca_creds()
    spots = spot_for(symbols, creds.key, creds.secret)

    rows = []
    for sym in symbols:
        if sym not in spots:
            rows.append({"symbol": sym, "ok": False, "reason": "no spot price"})
            continue
        try:
            r = screen_symbol(sym, spots[sym], min_dte, args.cap_dollars,
                              creds.key, creds.secret)
        except ScreenError as e:
            r = {"symbol": sym, "ok": False, "reason": str(e)[:160]}
        r["tier"] = classify(r, max_spread)
        rows.append(r)
        time.sleep(0.15)

    scored = [r for r in rows if r.get("ok")]
    if not scored:
        print("ERROR: no symbol screened successfully — refusing to write an empty screen.",
              file=sys.stderr)
        return 1

    rows.sort(key=lambda r: (r.get("tier") != "TIER1_tradeable", r.get("spread_pct", 999)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "as_of_et": dt.datetime.now().isoformat(timespec="seconds"),
        "risk_cap_dollars": args.cap_dollars,
        "max_spread_pct_of_premium": max_spread,
        "min_dte": min_dte,
        "quote_feed": "indicative (no OPRA agreement) — ranking signal, not a quotable price",
        "n_screened": len(scored), "n_failed": len(rows) - len(scored),
        "rows": rows,
    }, indent=2), encoding="utf-8")

    print(f"{'sym':<6} {'spot':>8} {'strike':>8} {'mid':>7} {'spr%':>7} {'OI':>7} {'3lot$':>9}  tier")
    for r in rows:
        if r.get("ok"):
            print(f"{r['symbol']:<6} {r['spot']:>8.2f} {r['atm_strike']:>8.1f} {r['mid']:>7.2f} "
                  f"{r['spread_pct']:>7.1f} {str(r['open_interest'] or '-'):>7} "
                  f"{r['cost_3_contracts']:>9.0f}  {r['tier']}")
        else:
            print(f"{r['symbol']:<6} {'-':>8} {'-':>8} {'-':>7} {'-':>7} {'-':>7} {'-':>9}  "
                  f"UNSCREENABLE ({r.get('reason','?')[:40]})")
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
