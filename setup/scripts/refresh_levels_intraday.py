"""refresh_levels_intraday.py — keep the engine's key levels LIVE during RTH.

THE BUG THIS FIXES (2026-06-29, J live-flagged): key-levels.json was frozen at the
08:30 premarket draw. After the open, price ran to a new intraday high (739.90) but the
engine's highest near-price resistance was still the stale PMH (738.10). When price
REJECTED at 739.90 the engine logged rejection_level=None — it was BLIND to the live
structure and missed the bearish setup. The engine reads key-levels.json every tick
(heartbeat_core._read_levels) but nothing refreshed the intraday levels.

WHAT THIS DOES (purely ADDITIVE + idempotent — never deletes premarket/structural levels):
  * Fetch today's SPY 5m bars via the SAME direct Alpaca REST path the engine uses
    (TV-independent — the TV crashes that corrupted the premarket draw don't touch this).
  * Compute the live intraday RTH high/low so far + the most recent swing high/low.
  * Upsert them into key-levels.json as Active resistance/support (role by side vs price),
    labeled INTRADAY_*. Re-running just updates the same labels (no duplication).
  * Refresh EMAs (13/20/48 + 50SMA) from the close series and clear ema_read_failed in
    today-bias (cosmetic — the live engine computes its own ribbon, but premarket/bias use it).

Run intraday (every few min) so the engine's level set tracks the session in real time.
$0, no LLM, no order placement.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
KEY_LEVELS = STATE / "key-levels.json"
TODAY_BIAS = STATE / "today-bias.json"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now  # noqa: E402

ACTIVE_BAND = 12.0   # the engine only considers levels within $12 of spot (heartbeat_core._read_levels)


def _spy_bars() -> pd.DataFrame:
    """SPY 5m, ~7 days, direct Alpaca REST (same un-blockable path as the engine + beacon)."""
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
    start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min&start={start}"
           f"&limit=600&feed=iex&adjustment=raw&sort=asc")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=15) as r:
        bars = json.loads(r.read()).get("bars", [])
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame([{"t": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                        "close": b["c"], "volume": b["v"]} for b in bars])
    df["ts"] = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = df["ts"].dt.strftime("%Y-%m-%d")
    df["hm"] = df["ts"].dt.strftime("%H:%M")
    return df.reset_index(drop=True)


def _swing_levels(rth: pd.DataFrame) -> tuple[float | None, float | None]:
    """Most recent local swing high/low (3-bar pivots) in the RTH session — the freshest
    structure a rejection/bounce would form against."""
    if len(rth) < 5:
        return None, None
    highs, lows = rth["high"].tolist(), rth["low"].tolist()
    sh = sl = None
    for i in range(len(rth) - 2, 1, -1):
        if sh is None and highs[i] >= highs[i - 1] and highs[i] >= highs[i + 1] and highs[i] > highs[i - 2]:
            sh = round(highs[i], 2)
        if sl is None and lows[i] <= lows[i - 1] and lows[i] <= lows[i + 1] and lows[i] < lows[i - 2]:
            sl = round(lows[i], 2)
        if sh and sl:
            break
    return sh, sl


def _level(price: float, spot: float, label: str, source: str, now_iso: str) -> dict:
    role = "resistance" if price >= spot else "support"
    return {
        "price": round(price, 2), "type": role, "role": role, "label": label,
        "tier": "Active", "source": source, "verified_at": now_iso,
        "expires_at": now_iso[:10] + "T16:00:00-04:00",
        "reasoning": f"Live intraday {role} ({source}) refreshed {now_iso[11:16]} ET — "
                     f"engine rejection/bounce zone.",
        "entity_id": None, "draw_needed": False,
    }


def refresh(df: pd.DataFrame | None = None) -> dict:
    now = et_now()
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S-04:00")
    today = now.strftime("%Y-%m-%d")
    # df injectable for tests/replay (G6 seam pattern); default = live REST, byte-identical.
    df = _spy_bars() if df is None else df
    if df.empty:
        return {"ok": False, "error": "no bars"}

    today_df = df[df["date"] == today]
    rth = today_df[(today_df["hm"] >= "09:30") & (today_df["hm"] <= "16:00")]
    pre = today_df[today_df["hm"] < "09:30"]
    spot = float(df["close"].iloc[-1])

    computed = []
    if len(rth):
        computed.append(("INTRADAY_RTH_HIGH", float(rth["high"].max()), "intraday_rth_high"))
        computed.append(("INTRADAY_RTH_LOW", float(rth["low"].min()), "intraday_rth_low"))
    sh, sl = _swing_levels(rth)
    if sh is not None:
        computed.append(("INTRADAY_SWING_HIGH", sh, "intraday_swing_high"))
    if sl is not None:
        computed.append(("INTRADAY_SWING_LOW", sl, "intraday_swing_low"))
    if len(pre):
        # INTRADAY_ prefix so the line-124 dedup catches them (else they piled up 2/run = the
        # 06-30 duplication bug); distinct from the curated PMH_<date> the premarket draws.
        computed.append(("INTRADAY_PMH", float(pre["high"].max()), "premarket_high"))
        computed.append(("INTRADAY_PML", float(pre["low"].min()), "premarket_low"))

    # Load existing levels, drop our own prior INTRADAY_* upserts (idempotent), keep the rest.
    try:
        kl = json.loads(KEY_LEVELS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        kl = {"schema_version": 1, "levels": []}
    levels = [lv for lv in (kl.get("levels") or []) if not str(lv.get("label", "")).startswith("INTRADAY_")]

    added = []
    for label, price, source in computed:
        lvl = _level(price, spot, f"{label}_{today}", source, now_iso)
        levels.append(lvl)
        added.append((lvl["label"], lvl["price"], lvl["role"]))

    kl["levels"] = levels
    kl["as_of"] = now_iso
    kl["spot_at_compute"] = round(spot, 2)
    kl["computed_from"] = "refresh_levels_intraday.py (live Alpaca REST, TV-independent)"
    # the live feed owns the session date so key-levels never sits stale-dated when the
    # premarket LLM silent-fails (06-30: premarket exit-0-no-write left date frozen at 06-29).
    kl["date"] = today
    kl["for_session"] = today

    tmp = KEY_LEVELS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(kl, indent=1), encoding="utf-8")
    tmp.replace(KEY_LEVELS)

    # EMAs (13/20/48 + 50SMA) from the close series; clear ema_read_failed in today-bias.
    ema_patch = {}
    try:
        closes = df["close"].astype(float)
        ef = float(closes.ewm(span=13, adjust=False).mean().iloc[-1])
        ep = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        es = float(closes.ewm(span=48, adjust=False).mean().iloc[-1])
        ema_patch = {"ema_fast": round(ef, 2), "ema_pivot": round(ep, 2),
                     "ema_slow": round(es, 2), "ema_read_failed": False,
                     "ribbon_source": f"refresh_levels_intraday_{now.strftime('%H:%M')}ET"}
        bias = json.loads(TODAY_BIAS.read_text(encoding="utf-8"))
        bkl = bias.get("key_levels", {})
        # active resistances/supports (within band) for the bias display too
        res = sorted({lv["price"] for lv in levels if lv["role"] == "resistance" and abs(lv["price"] - spot) <= ACTIVE_BAND})
        sup = sorted({lv["price"] for lv in levels if lv["role"] == "support" and abs(lv["price"] - spot) <= ACTIVE_BAND}, reverse=True)
        bkl.update(ema_patch, resistance=res, support=sup)
        bias["key_levels"] = bkl
        btmp = TODAY_BIAS.with_suffix(".json.tmp")
        btmp.write_text(json.dumps(bias, indent=1), encoding="utf-8")
        btmp.replace(TODAY_BIAS)
    except Exception as exc:  # noqa: BLE001 — EMA patch is best-effort, never blocks the level write
        ema_patch = {"error": str(exc)}

    active = sorted({lv["price"] for lv in levels if abs(lv["price"] - spot) <= ACTIVE_BAND})
    return {"ok": True, "ts_et": now_iso, "spot": round(spot, 2), "added": added,
            "engine_active_levels": active, "ema": ema_patch}


if __name__ == "__main__":
    out = refresh()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("ok") else 1)
