"""daily_context.py — multi-week structural context from DAILY SIP bars (WS1 v2, 2026-07-27).

THE BUG THIS FIXES: today's engine premarket-high level was 744.90 from a SINGLE 80-share
IEX print (n=1, v=80). J's real level, 745.40, is confirmed all over the SIP tape (07-08
daily close 745.40) and is part of a 3-week shelf (744.2-745.8: 06-22 c744.39, 07-02 c744.78,
07-08 c745.40, 07-21 l744.18) broken down on 07-23. Today (07-27) gapped up +0.81% from
Friday's 738.93 close straight INTO that shelf (open 744.91, high 745.53) — a textbook
backside retest of a broken support-turned-resistance zone — then faded the entire gap.
The engine had zero multi-day/shelf awareness; this module gives it that context, computed
from DAILY bars only ($0, no LLM, pure Python).

WHAT THIS COMPUTES (all from ~60 days of daily SIP bars):
  (a) gap state    — overnight gap $ / %, direction, intraday fill progress.
  (b) shelf zones  — clusters of daily O/H/L/C within a $1.60 band, >=3 touches over
                      >=10 sessions (a standard max-points-in-fixed-window sliding scan
                      seeded on daily closes, touches counted as close-in-band OR
                      intraday-range-intersects-band).
  (c) shelf break  — was a shelf broken (closed clearly outside it) in the last 5
                      sessions, and is today re-approaching it from the OPPOSITE side
                      of the break (backside_retest) — the exact 07-27 geometry.
  (d) prior-day H/L/C.

Writes automation/state/daily-context.json with a computed_at_et stamp. Pure read of the
same direct Alpaca REST path refresh_levels_intraday.py uses (SIP-entitled key, verified
live 2026-07-27) — TV-independent, $0, no LLM.

Injectable seam for tests: compute_daily_context(bars=..., now=...) never hits the network;
write_daily_context() is the only network-touching entrypoint (mirrors refresh_levels_
intraday.refresh(df=...)).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
DAILY_CONTEXT_PATH = STATE / "daily-context.json"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now  # noqa: E402

LOOKBACK_DAYS = 60           # calendar days requested (~40 trading sessions)
SHELF_BAND_WIDTH = 1.60      # $ width a shelf cluster must fit inside
SHELF_MIN_TOUCHES = 3        # minimum sessions touching the band
SHELF_MIN_SPAN_SESSIONS = 10 # minimum session-index span between first and last touch
BREAK_LOOKBACK_SESSIONS = 5  # "broken in the last N sessions"
BREAK_BUFFER = 0.10          # $ buffer beyond the band edge to count as a clean break


# --- fetch -----------------------------------------------------------------------------

def _fetch_daily_bars(days: int = LOOKBACK_DAYS) -> list[dict]:
    """Daily SIP SPY bars, chronological. Same direct-REST pattern as refresh_levels_
    intraday._spy_bars (TV-independent, un-blockable). Returns [] on any fetch failure
    (fail-open — caller must handle empty)."""
    try:
        m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
        env = m["mcpServers"]["alpaca"]["env"]
        key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
    except (OSError, json.JSONDecodeError, KeyError):
        return []
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day&start={start}"
           f"&limit=100&feed=sip&adjustment=raw&sort=asc")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = json.loads(r.read()).get("bars", [])
    except Exception:  # noqa: BLE001 — network/HTTP errors fail open to []
        return []
    bars = []
    for b in raw:
        bars.append({"date": str(b["t"])[:10], "o": float(b["o"]), "h": float(b["h"]),
                     "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)})
    return bars


# --- (a) gap state -----------------------------------------------------------------------

def _gap_state(bars: list[dict], today_et: str) -> dict:
    """Overnight gap $/%, direction, and intraday fill progress. Uses the LATEST bar as
    'today' only if it is actually dated today (ET) — otherwise the session hasn't printed
    an open yet (pre-open call) and gap fields report unavailable rather than comparing two
    stale historical bars."""
    if len(bars) < 2:
        return {"available": False, "reason": "fewer than 2 daily bars"}
    if bars[-1]["date"] != today_et:
        prior = bars[-1]
        return {"available": False, "reason": "today's daily bar not yet printed (pre-open)",
                "prior_close": round(prior["c"], 2), "prior_session": prior["date"]}
    today, prior = bars[-1], bars[-2]
    prior_close = prior["c"]
    gap_dollars = round(today["o"] - prior_close, 4)
    gap_pct = round((gap_dollars / prior_close) * 100, 4) if prior_close else None
    if gap_dollars > 0.005:
        direction = "up"
    elif gap_dollars < -0.005:
        direction = "down"
    else:
        direction = "flat"
    if direction == "up":
        filled = max(0.0, today["o"] - today["l"])
        fill_pct = round(min(1.0, filled / gap_dollars), 4) if gap_dollars else None
    elif direction == "down":
        filled = max(0.0, today["h"] - today["o"])
        fill_pct = round(min(1.0, filled / abs(gap_dollars)), 4) if gap_dollars else None
    else:
        fill_pct = 1.0
    return {
        "available": True,
        "prior_close": round(prior_close, 2), "prior_session": prior["date"],
        "today_open": round(today["o"], 2), "today_session": today["date"],
        "today_high": round(today["h"], 2), "today_low": round(today["l"], 2),
        "today_last": round(today["c"], 2),
        "gap_dollars": gap_dollars, "gap_pct": gap_pct, "direction": direction,
        "fill_pct": fill_pct, "gap_filled": bool(fill_pct is not None and fill_pct >= 0.999),
    }


# --- (d) prior-day H/L/C ------------------------------------------------------------------

def _prior_day_hlc(bars: list[dict], today_et: str) -> dict:
    """The most recently COMPLETED session strictly before today (ET) — robust whether
    'bars' ends with today's live-updating bar or not."""
    prior_bars = [b for b in bars if b["date"] < today_et]
    if not prior_bars:
        return {}
    prior = prior_bars[-1]
    return {"date": prior["date"], "high": round(prior["h"], 2), "low": round(prior["l"], 2),
            "close": round(prior["c"], 2)}


# --- (b) shelf detection -------------------------------------------------------------------

def _touches_band(bar: dict, lo: float, hi: float) -> bool:
    """A session 'touches' [lo, hi] if its close, high, or low actually LANDS inside the
    band — price found/tested that level. Deliberately NOT 'range spans the band' (a big
    trend-day candle that simply blows through a level on its way elsewhere is not a touch
    of that level; in a persistently-trending series that looser test turns nearly every
    band along the path into a spurious 'shelf')."""
    return (lo <= bar["c"] <= hi) or (lo <= bar["h"] <= hi) or (lo <= bar["l"] <= hi)


def _find_shelf_candidates(bars: list[dict], band_width: float = SHELF_BAND_WIDTH,
                            min_touches: int = SHELF_MIN_TOUCHES,
                            min_span: int = SHELF_MIN_SPAN_SESSIONS) -> list[dict]:
    """Classic 'max points in a fixed-width window' scan: anchor a candidate band at every
    unique daily CLOSE (sufficient — the optimal window can always be slid left until its
    left edge sits on the leftmost point still inside it, without losing coverage), then
    score EVERY session (close-in-band OR wick-intersects) as a touch. Returns overlapping
    candidates; caller (_merge_shelf_candidates) dedupes to the strongest per region."""
    if len(bars) < min_touches:
        return []
    # seed candidate LEFT edges from every close/high/low (not closes alone) — a touch can
    # be a wick (H or L landing in-band), so the truly optimal window may need to anchor on
    # a wick price, not just a close, to capture every point that should co-cluster.
    seeds = sorted({round(v, 2) for b in bars for v in (b["c"], b["h"], b["l"])})
    out = []
    for lo in seeds:
        hi = round(lo + band_width, 2)
        touch_idx = [i for i, b in enumerate(bars) if _touches_band(b, lo, hi)]
        if len(touch_idx) < min_touches:
            continue
        span = touch_idx[-1] - touch_idx[0]
        if span < min_span:
            continue
        out.append({
            "band_low": lo, "band_high": hi,
            "touch_idx": touch_idx, "touches": len(touch_idx), "span_sessions": span,
        })
    return out


def _merge_shelf_candidates(candidates: list[dict]) -> list[dict]:
    """Greedy strongest-first non-overlap merge: rank by touch count (ties -> lower band),
    keep a candidate only if it doesn't overlap an already-kept (stronger) shelf."""
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda c: (-c["touches"], c["band_low"]))
    kept: list[dict] = []
    for c in ranked:
        if any(not (c["band_high"] < k["band_low"] or c["band_low"] > k["band_high"]) for k in kept):
            continue
        kept.append(c)
    return sorted(kept, key=lambda c: c["band_low"])


# --- (c) shelf break + backside retest ------------------------------------------------------

def _detect_break(bars: list[dict], shelf: dict, today_idx: "int | None",
                   lookback_sessions: int = BREAK_LOOKBACK_SESSIONS,
                   buffer: float = BREAK_BUFFER) -> "dict | None":
    """Is price CURRENTLY sitting clearly outside this shelf (as of the last completed
    session before today), and did it get there via a genuine break (the band was touched
    at some point before the outside run started)? Anchored on the most recent session
    rather than 'first close outside the band after the last touch' — a single-session pop
    just past the edge (e.g. a $1.63 poke above a $1.60 band that reverses the very next
    day) is noise, not a break; the session that matters is whichever side price is
    actually sitting on right now, walked backward to where that run began."""
    end = today_idx if today_idx is not None else len(bars)
    if end <= 0:
        return None
    last_idx = end - 1  # last COMPLETED session strictly before today (or series end)
    band_lo, band_hi = shelf["band_low"], shelf["band_high"]
    c = bars[last_idx]["c"]
    if c < band_lo - buffer:
        direction = "down"
    elif c > band_hi + buffer:
        direction = "up"
    else:
        return None  # currently inside/near the band -> not broken right now
    i = last_idx
    while i - 1 >= 0:
        prev_c = bars[i - 1]["c"]
        still_outside_same_side = (prev_c < band_lo - buffer) if direction == "down" \
            else (prev_c > band_hi + buffer)
        if not still_outside_same_side:
            break
        i -= 1
    break_idx = i
    if not any(t < break_idx for t in shelf["touch_idx"]):
        return None  # never actually touched this band before the outside run -> not a break
    sessions_since = end - break_idx
    return {
        "break_idx": break_idx, "break_date": bars[break_idx]["date"], "direction": direction,
        "sessions_since_break": sessions_since,
        "recent": sessions_since <= lookback_sessions,
    }


def _backside_retest(bars: list[dict], shelf: dict, break_info: "dict | None",
                      today_idx: "int | None") -> "dict | None":
    """Is TODAY re-approaching a recently-broken shelf from the opposite side of the
    break? down-break -> retest if today's high reaches back up into/at the band;
    up-break -> retest if today's low reaches back down into/at the band."""
    if break_info is None or not break_info["recent"] or today_idx is None:
        return None
    today = bars[today_idx]
    band_lo, band_hi = shelf["band_low"], shelf["band_high"]
    if break_info["direction"] == "down":
        hit = today["h"] >= band_lo
    else:
        hit = today["l"] <= band_hi
    return {"backside_retest": bool(hit), "from_side": "below" if break_info["direction"] == "down" else "above",
            "broke_direction": break_info["direction"], "sessions_since_break": break_info["sessions_since_break"],
            "shelf_band": [band_lo, band_hi]}


def _shelf_zones(bars: list[dict], today_et: str) -> list[dict]:
    """Full shelf pipeline: detect -> merge -> per-shelf break + backside-retest state.
    Each returned zone carries band_low/band_high/touches/span_sessions/touch_sessions +
    break/backside_retest (None if not broken recently)."""
    today_idx = None
    for i, b in enumerate(bars):
        if b["date"] == today_et:
            today_idx = i
            break
    candidates = _find_shelf_candidates(bars)
    shelves = _merge_shelf_candidates(candidates)
    out = []
    for sh in shelves:
        brk = _detect_break(bars, sh, today_idx)
        retest = _backside_retest(bars, sh, brk, today_idx)
        out.append({
            "band_low": sh["band_low"], "band_high": sh["band_high"],
            "touches": sh["touches"], "span_sessions": sh["span_sessions"],
            "touch_sessions": [bars[i]["date"] for i in sh["touch_idx"]],
            "broken": brk is not None,
            "break": brk,
            "backside_retest": retest,
        })
    return out


# --- top-level -------------------------------------------------------------------------

def compute_daily_context(bars: "list[dict] | None" = None, now=None) -> dict:
    """Pure computation (no I/O besides the optional fetch), injectable for tests."""
    now = now or et_now()
    today_et = now.strftime("%Y-%m-%d")
    bars = _fetch_daily_bars() if bars is None else bars
    if not bars:
        return {"ok": False, "error": "no daily bars", "computed_at_et": now.strftime("%Y-%m-%dT%H:%M:%S-04:00")}

    shelves = _shelf_zones(bars, today_et)
    return {
        "ok": True,
        "computed_at_et": now.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
        "for_session": today_et,
        "n_bars": len(bars),
        "gap_state": _gap_state(bars, today_et),
        "prior_day": _prior_day_hlc(bars, today_et),
        "shelf_zones": shelves,
    }


def write_daily_context() -> dict:
    """Fetch + compute + atomic write to automation/state/daily-context.json. The only
    entrypoint that touches the network; safe to call every refresh cycle (idempotent —
    full recompute + overwrite each time, same pattern as refresh_levels_intraday)."""
    out = compute_daily_context()
    tmp = DAILY_CONTEXT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tmp.replace(DAILY_CONTEXT_PATH)
    return out


if __name__ == "__main__":
    result = write_daily_context()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)
