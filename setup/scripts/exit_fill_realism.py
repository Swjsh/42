"""Where in the minute did our EXIT actually fill? -- settling the cost model's biggest unknown.

THE QUESTION. The 2026-08-18 cost-realism audit resolved the ENTRY side with high confidence
(entries land near the real ask, matching a known $0.03 cross-buffer -- not at the midpoint)
but left EXITS unverified, because exits go out as market orders and therefore have no
submitted limit price to diff against. That gap is not academic: the audit's two scenarios
differ by 2.3x --

    fee-adjusted book, exits assumed realistic   : -$2,201
    fee-adjusted book, conservative exit slippage: -$5,069

and the arms sit only 0.6-5.1 percentage points below their own breakeven win rates. A cost
difference of that size decides whether this strategy is marginally-under or hopelessly-under.

THE METHOD. `automation/state/fills-ledger.jsonl` records fill price but NO quote. Alpaca's
historical options QUOTES endpoint returns 404 on this key, so NBBO-at-fill is unavailable.
What IS available at $0 is `/v1beta1/options/bars` (the same endpoint the repo's proven
fetch_option_data.py uses). So instead of asking "what was the bid", ask the answerable
question:

    WHERE IN THAT MINUTE'S TRADED RANGE DID OUR SELL LAND?

    position = (fill - low) / (high - low)      0.0 = at the minute's LOW, 1.0 = at its HIGH

For a SELL, the bid side of the book is the low side of the traded range. So:
  * positions clustering near 0.0  -> we sell into the bid. REALISTIC. Paper is not flattering us.
  * positions clustering near 0.5  -> we sell at the midpoint. OPTIMISTIC; real fills would be
                                     worse by roughly half the spread on every exit.

This is a PROXY, and its limits are stated rather than buried:
  * A 1-minute OHLC bar is built from trades, not quotes. The low is the lowest PRINT, which
    is at or above the true bid, so this test is CONSERVATIVE -- it can understate how good
    our fills are, never overstate them.
  * A one-trade minute has high == low and no meaningful position; those are excluded, not
    defaulted to 0.5.
  * Bars are the consolidated tape; our fill is one print within it. We are asking where in
    the distribution we landed, not reconstructing the book.

$0 -- bars are free on the already-wired key. Read-only: places no orders, touches no params,
arms nothing.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FILLS_LEDGER = REPO_ROOT / "automation" / "state" / "fills-ledger.jsonl"
MCP_JSON = REPO_ROOT / ".mcp.json"
BARS_URL = "https://data.alpaca.markets/v1beta1/options/bars"

# A minute whose traded range is thinner than this can't locate a fill meaningfully.
MIN_RANGE_USD = 0.02
# Same-day option bars 403 on this key; leave a margin.
SETTLED_LAG_DAYS = 1


def _headers() -> dict:
    cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    env = (cfg.get("mcpServers", {}).get("alpaca", {}) or {}).get("env", {}) or {}
    key, sec = env.get("ALPACA_API_KEY"), env.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        print("No Alpaca creds in .mcp.json -- refusing to continue.", file=sys.stderr)
        raise SystemExit(2)
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}


def load_option_sell_fills(max_date: str | None = None) -> list[dict]:
    """Engine-attributed option SELL fills, oldest first. Never J's manual fills."""
    out = []
    if not FILLS_LEDGER.exists():
        return out
    for line in FILLS_LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not r.get("is_option"):
            continue
        if str(r.get("attribution")) != "engine":
            continue
        if not str(r.get("side", "")).lower().startswith("sell"):
            continue
        if max_date and str(r.get("date_et", "")) > max_date:
            continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("ts_utc") or ""))
    return out


def fetch_minute_bar(symbol: str, ts_utc: str, headers: dict, timeout: float = 20.0) -> dict | None:
    """The 1-minute bar containing ts_utc, or None. Fail-soft: never raises."""
    try:
        import datetime as dt
        t0 = dt.datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    minute_start = t0.replace(second=0, microsecond=0)
    import datetime as dt
    q = urllib.parse.urlencode({
        "symbols": symbol, "timeframe": "1Min",
        "start": minute_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": (minute_start + dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 5,
    })
    try:
        req = urllib.request.Request(f"{BARS_URL}?{q}", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as rsp:
            data = json.loads(rsp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    bars = (data.get("bars") or {}).get(symbol) or []
    want = minute_start.strftime("%Y-%m-%dT%H:%M:00Z")
    for b in bars:
        if str(b.get("t", "")).startswith(want[:16]):
            return b
    return bars[0] if bars else None


def position_in_range(fill: float, low: float, high: float) -> float | None:
    """0.0 = filled at the minute's LOW (bid side for a sell), 1.0 = at its HIGH.

    Returns None when the range is too thin to locate a fill -- a one-trade minute is not
    evidence of a midpoint fill and must never be defaulted to 0.5.
    """
    try:
        fill, low, high = float(fill), float(low), float(high)
    except (TypeError, ValueError):
        return None
    rng = high - low
    if rng < MIN_RANGE_USD:
        return None
    return max(0.0, min(1.0, (fill - low) / rng))


def analyse(limit: int = 120, max_date: str | None = None, sleep_s: float = 0.08) -> dict:
    headers = _headers()
    fills = load_option_sell_fills(max_date=max_date)
    sampled = fills[-limit:] if limit else fills
    positions: list[float] = []
    at_or_below_low = 0
    skipped_thin = 0
    skipped_nobar = 0
    for r in sampled:
        bar = fetch_minute_bar(str(r.get("symbol")), str(r.get("ts_utc")), headers)
        if not bar:
            skipped_nobar += 1
            continue
        pos = position_in_range(r.get("price"), bar.get("l"), bar.get("h"))
        if pos is None:
            skipped_thin += 1
            continue
        positions.append(pos)
        try:
            if float(r["price"]) <= float(bar["l"]):
                at_or_below_low += 1
        except (TypeError, ValueError, KeyError):
            pass
        if sleep_s:
            time.sleep(sleep_s)
    n = len(positions)
    if not n:
        return {"n": 0, "verdict": "INSUFFICIENT DATA",
                "skipped_thin_range": skipped_thin, "skipped_no_bar": skipped_nobar}
    mean_pos = statistics.fmean(positions)
    median_pos = statistics.median(positions)
    # Interpretation thresholds are stated, not hidden in a comparison.
    if median_pos <= 0.35:
        verdict = "REALISTIC -- exits land on the bid side of the traded range"
    elif median_pos >= 0.45:
        verdict = "OPTIMISTIC -- exits land at/above midpoint; real fills would be worse"
    else:
        verdict = "AMBIGUOUS -- between bid-side and midpoint"
    return {
        "n": n,
        "mean_position_in_range": round(mean_pos, 4),
        "median_position_in_range": round(median_pos, 4),
        "pct_at_or_below_bar_low": round(100.0 * at_or_below_low / n, 1),
        "verdict": verdict,
        "skipped_thin_range": skipped_thin,
        "skipped_no_bar": skipped_nobar,
        "note": ("Bar low is the lowest PRINT, which sits at or above the true bid, so this "
                 "test is CONSERVATIVE -- it can understate fill quality, never overstate it."),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--max-date", default=None, help="exclude fills after this ET date")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = analyse(limit=a.limit, max_date=a.max_date)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    print("EXIT FILL REALISM -- where in the minute's traded range did our SELL land?")
    print(f"  sampled sell fills scored : {res.get('n')}")
    if res.get("n"):
        print(f"  median position in range  : {res['median_position_in_range']:.3f}"
              f"   (0.0 = at the LOW/bid side, 0.5 = midpoint)")
        print(f"  mean position in range    : {res['mean_position_in_range']:.3f}")
        print(f"  filled at or below bar low: {res['pct_at_or_below_bar_low']}%")
        print(f"  skipped (thin range/no bar): {res['skipped_thin_range']}/{res['skipped_no_bar']}")
        print()
        print(f"  VERDICT: {res['verdict']}")
        print(f"  {res['note']}")
    else:
        print(f"  VERDICT: {res.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
