"""Fetch OPRA 1-min bars for the ITM-2..OTM+2 strike ladder around every trade.

Batches by DATE (Alpaca /v1beta1/options/bars accepts a comma-separated symbol list),
writes into the SHARED cache backtest/data/opra_1m_cache/<symbol>_<date>.csv using the
pre-existing schema (t,o,h,l,c,v with t in UTC). Never overwrites an existing file.
Fails LOUD -- a symbol with no bars gets an explicit MISS record, never an imputed row.
"""
from __future__ import annotations
import csv, json, os, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path

REPO = Path(r"C:/Users/jackw/Desktop/42")
CACHE = REPO / "backtest" / "data" / "opra_1m_cache"
MCP_JSON = REPO / ".mcp.json"
URL = "https://data.alpaca.markets/v1beta1/options/bars"
MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"
OFFSETS = (-2, -1, 0, 1, 2)   # signed OTM offset n


def creds():
    k = os.environ.get("ALPACA_API_KEY")
    s = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if k and s:
        return k, s
    cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    env = (cfg.get("mcpServers", {}).get("alpaca", {}) or {}).get("env", {}) or {}
    k = env.get("ALPACA_API_KEY")
    s = env.get("ALPACA_SECRET_KEY") or env.get("ALPACA_API_SECRET")
    if not (k and s):
        raise SystemExit("NO ALPACA MARKET-DATA CREDS -- refusing to fabricate bars")
    return k, s


def alt_symbol(real_symbol: str, side: str, spy: float, n: int) -> tuple[str, float]:
    """n = signed OTM offset (positive = further OTM for this side)."""
    atm = round(spy)
    k = atm + (n if side == "C" else -n)
    return real_symbol[:-8] + str(int(round(k * 1000))).zfill(8), float(k)


def main() -> int:
    d = json.loads(MATRIX.read_text(encoding="utf-8"))
    by_date: dict[str, set[str]] = {}
    for r in d["rows"]:
        spy = r.get("spy_at_entry")
        if spy is None:
            print(f"[SKIP] no spy_at_entry: {r['arm']} {r['date']} {r['symbol']}", file=sys.stderr)
            continue
        for n in OFFSETS:
            s, _ = alt_symbol(r["symbol"], r["side"], spy, n)
            by_date.setdefault(r["date"], set()).add(s)

    CACHE.mkdir(parents=True, exist_ok=True)
    key, sec = creds()
    hdrs = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
    fetched = missing = skipped = 0
    misses: list[str] = []

    for date in sorted(by_date):
        want = sorted(s for s in by_date[date] if not (CACHE / f"{s}_{date}.csv").exists())
        skipped += len(by_date[date]) - len(want)
        if not want:
            continue
        # chunk the symbol list so the URL stays sane
        got: dict[str, list] = {}
        for i in range(0, len(want), 25):
            chunk = want[i:i + 25]
            params = {"symbols": ",".join(chunk), "timeframe": "1Min",
                      "start": f"{date}T12:00:00Z", "end": f"{date}T21:00:00Z", "limit": 10000}
            base = f"{URL}?{urllib.parse.urlencode(params)}"
            page = None
            for _ in range(30):
                u = base + (f"&page_token={urllib.parse.quote(page)}" if page else "")
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, headers=hdrs), timeout=40) as resp:
                        payload = json.loads(resp.read().decode("utf-8"))
                except Exception as exc:                      # noqa: BLE001 -- report, never silently zero
                    print(f"[FETCH-FAIL] {date} chunk{i}: {exc}", file=sys.stderr)
                    return 2
                for sym, bars in (payload.get("bars") or {}).items():
                    got.setdefault(sym, []).extend(bars or [])
                page = payload.get("next_page_token")
                if not page:
                    break
        for s in want:
            bars = got.get(s) or []
            if not bars:
                misses.append(f"{s}_{date}")
                missing += 1
            with (CACHE / f"{s}_{date}.csv").open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["t", "o", "h", "l", "c", "v"])
                for b in bars:
                    w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b.get("v", 0)])
            fetched += 1
        print(f"  {date}: fetched {len(want)} symbols", flush=True)

    print(f"\nfetched={fetched} already_cached={skipped} EMPTY(no OPRA prints)={missing}")
    if misses:
        print("EMPTY symbols (recorded, never imputed):")
        for m in misses[:40]:
            print("  ", m)
        if len(misses) > 40:
            print(f"   ... +{len(misses)-40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
