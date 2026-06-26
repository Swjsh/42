"""sight_beacon.py — the NEVER-BLIND guarantee for the engine's eyes.

The heartbeat reads the market via TV MCP (CDP) with an Alpaca-MCP bar fallback.
Both can fail in the heartbeat's `claude --print` process: TV via CDP single-client
contention, Alpaca-MCP via a slow uvx cold-start or a transient 401. When BOTH fail
the engine goes BLIND and (correctly) refuses to trade — but blindness itself is the
failure J will not tolerate ("ENGINE CAN NOT BE BLIND EVER").

This standalone beacon removes the single points of failure. It is a plain Python
process (NO MCP, NO CDP, NO Claude pool) that fetches SPY 5m bars from two independent
sources and writes a fresh ribbon+price snapshot to automation/state/sight-beacon.json:

  Source 1 (PRIMARY): Alpaca market-data REST (direct urllib, IEX feed, free tier).
  Source 2 (FALLBACK): yfinance (no auth at all — the path watcher_live.py already uses).

As long as ONE of those two HTTP endpoints answers (they essentially always do), the
beacon is fresh, and the heartbeat's Layer-1b fallback can read it and SEE the market.
The beacon cannot be starved by the Max pool, blocked by the chart's CDP connection,
or broken by an MCP server that won't start.

Run every ~1 min during RTH via Gamma_SightBeacon. READ-ONLY w.r.t. trading state.
NEVER places orders. Loads the Alpaca key from .mcp.json at runtime (CLAUDE.md secret
rule — never hardcoded).
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "backtest" / "lib"))
from ribbon_fallback import compute_ribbon  # noqa: E402

BEACON = REPO / "automation" / "state" / "sight-beacon.json"
MCP_JSON = REPO / ".mcp.json"
STALE_AFTER_S = 180  # consumers must treat a beacon older than this as untrustworthy


def _et_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=-4)


def _load_alpaca_key() -> tuple[str, str]:
    """Read the Safe Alpaca key from .mcp.json at runtime (never hardcode — CLAUDE.md)."""
    try:
        m = json.loads(MCP_JSON.read_text(encoding="utf-8"))
        env = m.get("mcpServers", {}).get("alpaca", {}).get("env", {})
        return env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
    except (OSError, json.JSONDecodeError):
        return "", ""


def _fetch_alpaca_bars(limit: int = 300) -> tuple[list[float], str | None, str]:
    """Direct Alpaca market-data REST (IEX feed, free tier). Returns (closes, last_bar_iso, note).

    Look back ~5 calendar days so we always have >=60 bars across prior sessions to seed
    the ribbon EMAs + sma_50 (today's RTH alone is too few early in the session).

    CRITICAL — fetch NEWEST-first (sort=desc), then reverse to ascending. The 5-day window
    holds ~390 5m bars but `limit` caps the response at 300. With sort=asc the cap keeps the
    OLDEST 300 and truncates the newest off the tail, so `spy`/`last_bar` froze on a prior
    session (2026-06-26 scar: beacon stuck at 731.86 / last_bar 2026-06-25T17:45Z, ~$2.80
    stale, all morning). sort=desc keeps the NEWEST 300 (next_page_token drops the old tail
    instead); reversing restores oldest->newest so the ribbon EMAs and bars[-1]=newest are
    both correct."""
    key, sec = _load_alpaca_key()
    if not key or not sec:
        return [], None, "no_key"
    start = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars"
           f"?timeframe=5Min&start={start}&limit={limit}&feed=iex&adjustment=raw&sort=desc")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return [], None, f"http_{e.code}"
    except Exception as e:  # noqa: BLE001
        return [], None, f"err_{type(e).__name__}"
    bars = list(reversed(data.get("bars") or []))  # desc -> asc: ribbon needs oldest->newest
    closes = [float(b["c"]) for b in bars if b.get("c") is not None]
    last_iso = bars[-1].get("t") if bars else None  # bars[-1] is now the NEWEST bar
    return closes, last_iso, f"ok_{len(closes)}bars"


def _fetch_yfinance_bars() -> tuple[list[float], str | None, str]:
    """yfinance fallback — no auth. The path watcher_live.py already proves works."""
    try:
        import yfinance as yf
    except ImportError:
        return [], None, "no_yfinance"
    try:
        df = yf.download("SPY", period="5d", interval="5m",
                         auto_adjust=False, progress=False, prepost=False)
        if df is None or df.empty:
            return [], None, "empty"
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        closes = [float(c) for c in df["Close"].tolist() if c == c]  # drop NaN
        last_iso = None
        try:
            last_iso = df.index[-1].to_pydatetime().isoformat()
        except Exception:  # noqa: BLE001
            pass
        return closes, last_iso, f"ok_{len(closes)}bars"
    except Exception as e:  # noqa: BLE001
        return [], None, f"err_{type(e).__name__}"


def build() -> dict:
    et = _et_now()
    closes, last_iso, note = _fetch_alpaca_bars()
    data_source = "alpaca_rest_iex"
    if len(closes) < 25:  # not enough to seed the ribbon EMAs — try yfinance
        yc, yiso, ynote = _fetch_yfinance_bars()
        if len(yc) >= len(closes):
            closes, last_iso, note, data_source = yc, yiso, ynote, "yfinance"

    if len(closes) < 25:
        return {"ok": False, "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ts_et": et.strftime("%Y-%m-%dT%H:%M:%S-04:00"), "reason": "insufficient_bars",
                "alpaca_note": note, "data_source": data_source, "n_bars": len(closes)}

    read = compute_ribbon(closes)
    return {
        "ok": read.stack != "UNKNOWN",
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ts_et": et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
        "time_et": et.strftime("%H:%M"),
        "age_s": 0,
        "spy": read.price,
        "ribbon_stack": read.stack,
        "ema_fast": read.ema_fast,
        "ema_pivot": read.ema_pivot,
        "ema_slow": read.ema_slow,
        "sma_50": read.sma_50,
        "spread_cents": read.spread_cents,
        "bars_used": read.bars_used,
        "n_bars": len(closes),
        "last_bar": last_iso,
        "data_source": data_source,
        "fetch_note": note,
        "_doc": "NEVER-BLIND beacon. Heartbeat Layer-1b fallback reads this when TV MCP "
                "+ Alpaca MCP both fail. Trust only if age_s < %d. Built by sight_beacon.py "
                "(pure REST/yfinance, no MCP/CDP/pool)." % STALE_AFTER_S,
    }


def main() -> int:
    snap = build()
    # Never overwrite a good beacon with an empty one — keep last-known-good fresh-flagged.
    if not snap.get("ok") and BEACON.exists():
        try:
            prior = json.loads(BEACON.read_text(encoding="utf-8"))
            prior["last_failed_fetch_et"] = snap.get("ts_et")
            prior["last_failed_reason"] = snap.get("reason") or snap.get("fetch_note")
            BEACON.write_text(json.dumps(prior, indent=2), encoding="utf-8")
            print(f"FETCH FAILED ({snap.get('reason') or snap.get('fetch_note')}) — "
                  f"kept prior beacon (ts_et={prior.get('ts_et')})")
            return 0
        except (OSError, json.JSONDecodeError):
            pass
    tmp = BEACON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    tmp.replace(BEACON)
    print(json.dumps({k: snap.get(k) for k in
                      ("ok", "time_et", "spy", "ribbon_stack", "spread_cents",
                       "n_bars", "data_source", "fetch_note")}, indent=2))

    # Drive the fleet's shared-signal off this beacon every minute so the 4 fleet accounts
    # are never blind either. build() prefers a FRESH heartbeat decision and only falls back
    # to the beacon when the ledger is stale/blind — so this is safe to call every tick.
    # Best-effort: never let a fleet hiccup break the beacon write above.
    try:
        sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
        import build_shared_signal as _bss  # noqa: PLC0415
        _bss.build()
    except Exception as e:  # noqa: BLE001
        print(f"(fleet shared-signal refresh skipped: {type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
