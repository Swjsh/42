"""refresh_levels_intraday.py — keep the engine's key levels LIVE during RTH.

THE BUG THIS FIXES (2026-06-29, J live-flagged): key-levels.json was frozen at the
08:30 premarket draw. After the open, price ran to a new intraday high (739.90) but the
engine's highest near-price resistance was still the stale PMH (738.10). When price
REJECTED at 739.90 the engine logged rejection_level=None — it was BLIND to the live
structure and missed the bearish setup. The engine reads key-levels.json every tick
(heartbeat_core._read_levels) but nothing refreshed the intraday levels.

WS1 v2 (2026-07-27, J live-flagged): the 07-27 premarket HIGH was 744.90 from a SINGLE
80-share IEX print (n=1, v=80) — a degenerate, unrepresentative tape. J's real level,
745.40, is confirmed all over the SIP tape and is part of a 3-week shelf. Two root causes
fixed here: (1) this script fetched IEX (one exchange's prints) instead of SIP (the full
consolidated tape) — switched below; (2) it wrote whatever price it computed with zero
regard for how much (or little) data backed it — a degeneracy guard now refuses to write
a level sourced from <3 bars, <10k shares total volume, or a zero-range (high==low)
subset, logging a loud provenance note instead of silently writing garbage (C7/L241).
Levels now also carry weight + zone_width (J doctrine 2026-07-17: levels are ZONES) and,
via daily_context.py, multi-week shelf zones with their own break/backside-retest state.
NOTE: heartbeat_core.py's OWN live-tick fetch stays IEX untouched — this file only feeds
the premarket/intraday level FILE, not the engine's hot-path bar read.

WHAT THIS DOES (purely ADDITIVE + idempotent — never deletes premarket/structural levels):
  * Fetch today's SPY 5m bars via the SAME direct Alpaca REST path the engine uses
    (TV-independent — the TV crashes that corrupted the premarket draw don't touch this),
    now on the SIP feed (full consolidated tape; key verified SIP-entitled 2026-07-27).
  * Compute the live intraday RTH high/low so far + the most recent swing high/low +
    premarket high/low, each gated by the degeneracy guard above.
  * Upsert them into key-levels.json as Active resistance/support (role by side vs price),
    labeled INTRADAY_*. Re-running just updates the same labels (no duplication).
  * Union in multi-week shelf zones from daily_context.py (fail-open) and patch
    today-bias's daily_context section (gap state + shelf proximity + backside retest).
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
PARAMS = STATE / "params.json"
MEMORY_MAP = STATE / "key-levels-memory.json"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now  # noqa: E402
try:
    import daily_context  # noqa: E402 — multi-week shelf/gap context (WS1 v2, 2026-07-27)
except Exception:  # noqa: BLE001 — fail-open: a broken import must never break level refresh
    daily_context = None

ACTIVE_BAND = 12.0   # the engine only considers levels within $12 of spot (heartbeat_core._read_levels)
ROLE_EPSILON = 0.10  # active levels within this $ collapse to ONE entry with ONE role
# G11 level-memory merge wire (2026-07-09): union the shadow multi-day memory map's
# high-conviction near-price levels into the live feed. Gated by params.level_memory_live_merge.
MEMORY_MERGE_SPOT_PCT = 0.015   # only memory levels within +/-1.5% of spot (subset of ACTIVE_BAND)
MEMORY_MERGE_MIN_SCORE = 60.0   # memory_score floor
MEMORY_MERGE_CAP = 6            # overall doc cap (kept for reference/back-compat reads)
# DIRECTIONAL BALANCE (2026-07-27, J live-flagged): "6 nearest to spot" regardless of side
# produced an all-resistance set with ZERO supports at today's session high — the engine had
# no floor to reason about. Cap EACH side independently so both are represented whenever
# both exist in the candidate pool (same total-6 budget, split 3/3 instead of nearest-6-blind).
MEMORY_MERGE_CAP_PER_SIDE = 3

# Degeneracy guard (2026-07-27, J live-flagged): the 07-27 incident's PMH=744.90 was a
# SINGLE 80-share IEX print (n=1, v=80) — the engine trusted a level with essentially no
# data behind it. Refuse to WRITE a computed level whose source bars are this thin;
# log a loud provenance note instead of silently shipping garbage (C7/L241).
DEGENERACY_MIN_BARS = 3
DEGENERACY_MIN_VOLUME = 10_000.0  # shares, summed across the source subset

# Weight scale (2026-07-27, J doctrine 2026-07-17 "levels are ZONES"): every level this
# script writes gets a weight (1-5) and a $ zone_width. 5 = multi-week shelf / daily-close
# cluster (daily_context.py); 3 = prior-day H/L/C; 2 = this script's own intraday computed
# levels (PMH/PML/RTH high-low/swing high-low).
LEVEL_WEIGHT_INTRADAY = 2
LEVEL_WEIGHT_PRIOR_DAY_HLC = 3
LEVEL_WEIGHT_SHELF = 5
ZONE_WIDTH_MIN = 0.15        # $ floor
ZONE_WIDTH_PCT = 0.0005      # 0.05% of price — DEFAULT pending pre-registered A/B (J doctrine)
SHELF_UPSERT_BAND = 20.0     # only shelves within $20 of spot feed the engine file (daily_context.py
                              # itself keeps the FULL multi-week universe; this is the compiler's cutoff)

# SEMANTIC role map (2026-06-30 contradictory-role fix). A level's role is a STRUCTURAL property
# of WHERE IT CAME FROM, not of transient price-vs-spot at compute time. A premarket HIGH is a
# ceiling the session formed overhead; it stays resistance whether spot is below OR above it later.
# Driving role off (price >= spot) is the bug: a premarket high flips resistance->support the moment
# price runs through it, and two refresh runs at different spots leave the SAME logical price carrying
# BOTH roles (self_check.check_level_integrity RED). Keyed by `source`; the per-keyword fallback
# (_high/pmh -> ceiling, _low/pml -> floor) covers any source not enumerated here.
SEMANTIC_SOURCE_ROLE = {
    "premarket_high": "resistance",
    "intraday_rth_high": "resistance",
    "intraday_swing_high": "resistance",
    "double_session_low": "resistance",  # double-bottom that, once reclaimed, caps as overhead structure (per audit spec)
    "premarket_low": "support",
    "intraday_rth_low": "support",
    "intraday_swing_low": "support",
}
# prefixes the dedup must strip so PMH_/PML_ (curated, non-INTRADAY) writers collapse with their
# INTRADAY_ twins at the same rounded price (root cause #2: dedup only caught INTRADAY_ before).
_DEDUP_PREFIXES = ("INTRADAY_", "PMH_", "PML_")


def _spy_bars() -> pd.DataFrame:
    """SPY 5m, ~7 days, direct Alpaca REST (same un-blockable path as the engine + beacon).
    SIP feed (2026-07-27, J live-flagged): the key is SIP-entitled (verified live
    2026-07-27) — SIP is the full consolidated tape, IEX is a single exchange's prints.
    The 07-27 incident's degenerate 80-share single-print PMH was an IEX artifact; SIP
    carries the real cross-exchange volume this script's degeneracy guard depends on.
    heartbeat_core.py's OWN live-tick fetch is a SEPARATE code path and stays IEX —
    untouched by this change (this file only feeds the level FILE, not the hot-path bar
    read).

    LIMIT (2026-07-27): SIP is the FULL consolidated tape — every 5m window has a real
    print, so it is far denser than IEX (single-venue, many empty/sparse windows). Verified
    live: 7 days back returns ~957 SIP bars (~192/session) vs ~404 on IEX (~80/session) for
    the identical window. The pre-SIP limit of 600 was tuned for IEX's sparse density and
    silently stopped reaching TODAY once >=4 sessions of SIP data existed in the window —
    exactly the kind of blind spot this whole change exists to remove. 1500 covers a full
    7-calendar-day (~6 trading-day) SIP window with headroom."""
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
    start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min&start={start}"
           f"&limit=1500&feed=sip&adjustment=raw&sort=asc")
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


def _degeneracy_reason(sub: pd.DataFrame) -> str | None:
    """Refuse-to-write gate (2026-07-27, J live-flagged): a computed level is only as good
    as the tape behind it. The 07-27 PMH=744.90 was a SINGLE 80-share IEX print (n=1, v=80)
    — this would have refused it. Returns a loud one-line reason, or None if the source
    subset clears the bar. Fail-open on a malformed subset (missing column etc.) — never
    raises; treated as degenerate (refuse) rather than crashing the whole refresh."""
    try:
        n = len(sub)
        if n < DEGENERACY_MIN_BARS:
            return f"only {n} bar(s) (<{DEGENERACY_MIN_BARS} required)"
        vol = float(sub["volume"].sum())
        if vol < DEGENERACY_MIN_VOLUME:
            return f"total volume {vol:.0f} shares (<{DEGENERACY_MIN_VOLUME:.0f} required)"
        high, low = round(float(sub["high"].max()), 2), round(float(sub["low"].min()), 2)
        if high == low:
            return f"high==low=={high:.2f} across {n} bar(s) (degenerate zero-range tape)"
    except (KeyError, TypeError, ValueError) as exc:
        return f"malformed source subset ({type(exc).__name__}: {exc})"
    return None


def _zone_width(price: float) -> float:
    """J doctrine 2026-07-17: levels are ZONES, not exact prices. This is a DEFAULT band
    pending a pre-registered A/B study (never hand-picked) — every level carries
    zone_width_provenance='default_pre_ab' so a future study knows which levels still run
    on the default vs a validated width."""
    return round(max(ZONE_WIDTH_MIN, price * ZONE_WIDTH_PCT), 4)


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


def _semantic_role(source: str | None, label: str | None, fallback: str | None = None) -> str | None:
    """Structural role from the level's SOURCE (then label), independent of live price. Stable
    across the session, so one logical price = one role no matter where spot wanders. Returns the
    `fallback` (the level's pre-existing role) only when neither source nor label carries any
    high/low semantics — non-directional refs (prior_close, round_number) keep what they had."""
    src = str(source or "").lower()
    if src in SEMANTIC_SOURCE_ROLE:
        return SEMANTIC_SOURCE_ROLE[src]
    blob = f"{src} {str(label or '').lower()}"
    has_high = any(k in blob for k in ("_high", "pmh", "session_high", "rth_high", "swing_high"))
    has_low = any(k in blob for k in ("_low", "pml", "session_low", "rth_low", "swing_low"))
    if has_high and not has_low:
        return "resistance"
    if has_low and not has_high:
        return "support"
    return fallback


def _level(price: float, spot: float, label: str, source: str, now_iso: str, *,
           source_feed: str | None = None, n_bars: int | None = None,
           volume: float | None = None, weight: int | None = None) -> dict:
    # role by SEMANTIC source (stable), never by transient price-vs-spot (the flip-flop bug).
    role = _semantic_role(source, label) or ("resistance" if price >= spot else "support")
    price = round(price, 2)
    lv = {
        "price": price, "type": role, "role": role, "label": label,
        "tier": "Active", "source": source, "verified_at": now_iso,
        "expires_at": now_iso[:10] + "T16:00:00-04:00",
        "reasoning": f"Live intraday {role} ({source}) refreshed {now_iso[11:16]} ET — "
                     f"engine rejection/bounce zone.",
        "entity_id": None, "draw_needed": False,
        # WS1 v2 (2026-07-27): zone (J doctrine 2026-07-17) — every level this script writes
        # gets a $ band, DEFAULT pending a pre-registered A/B (never hand-picked).
        "zone_width": _zone_width(price), "zone_width_provenance": "default_pre_ab",
    }
    # provenance (2026-07-27, J live-flagged): how much tape backs this level, so a
    # single-print degenerate read (the 744.90 incident) is visible in the FILE, not just
    # inferred. Only set when the caller supplies them (computed intraday levels do; a
    # bare _level() call from a test or another producer stays field-absent, not null-spam).
    if source_feed is not None:
        lv["source_feed"] = source_feed
    if n_bars is not None:
        lv["n_bars"] = n_bars
    if volume is not None:
        lv["volume"] = round(float(volume), 0)
    if weight is not None:
        lv["weight"] = weight
    return lv


def _dedup_key(label: str | None) -> str:
    """The label with any writer prefix (INTRADAY_/PMH_/PML_) stripped, so the SAME logical level
    written by different producers (a curated PMH_<date> and its INTRADAY_PMH twin) shares a key
    and collapses. Root cause #2 of the 06-30 pile-up: dedup only matched INTRADAY_ before, so the
    non-prefixed PMH_/PML_ writers accumulated 6-9x."""
    s = str(label or "")
    for pre in _DEDUP_PREFIXES:
        if s.startswith(pre):
            return s[len(pre):]
    return s


def _normalize_levels(levels: list[dict], spot: float) -> list[dict]:
    """Producer-side invariant for the engine's level feed: every ACTIVE price carries ONE
    SEMANTIC role (structural, not price-relative), and near-equal prices collapse to a single
    canonical entry (a curated / non-INTRADAY label wins as the survivor). Kills BOTH
    self_check.check_level_integrity signatures at the source -- contradictory ceiling+floor roles
    AND >2x duplication -- no matter which upstream producer polluted key-levels.json (refresh is
    the freshest every-few-min writer, so the file self-heals each run). Expired levels pass
    through untouched (the engine and the self-check both ignore tier=='expired')."""
    def _is_intraday(lv: dict) -> bool:
        return str(lv.get("label", "")).startswith("INTRADAY_")

    def _price_of(lv: dict):
        try:
            return round(float(lv["price"]), 2)
        except (KeyError, TypeError, ValueError):
            return None

    expired = [lv for lv in levels if str(lv.get("tier", "")).lower() == "expired"]
    active = [lv for lv in levels
              if str(lv.get("tier", "")).lower() != "expired" and _price_of(lv) is not None]
    # structural (non-INTRADAY) sorts first WITHIN a price so it becomes the cluster survivor.
    active.sort(key=lambda lv: (_price_of(lv), _is_intraday(lv)))
    out: list[dict] = []
    seen_keys: set[str] = set()
    for lv in active:
        price = _price_of(lv)
        # role by SEMANTIC source/label (stable) for any directional level; only a NON-directional
        # ref (no high/low semantics in source or label) falls back to price-side. Either way each
        # PRICE maps to exactly ONE role here, so a price can never end up as both ceiling and floor.
        # G11 (2026-07-09): a level_memory level carries its OWN structural role (multi-day
        # sustained role-flip tagging); keep it STABLE instead of the price-relative flip-flop (else
        # a 747.13 resistance re-roles to support the moment spot ticks above it). ADDITIVE: no other
        # source is 'level_memory', so with no memory levels present this is byte-identical.
        # WS1 v2 (2026-07-27): a daily_context_shelf carries the same kind of pre-computed
        # structural role (break-direction-derived, see refresh()'s _shelf_level) — same
        # stability treatment, same reasoning.
        if str(lv.get("source", "")).lower() in ("level_memory", "daily_context_shelf"):
            _stored = str(lv.get("role") or lv.get("type") or "").lower()
            fb = _stored if _stored in ("resistance", "support") else ("resistance" if price >= spot else "support")
        else:
            fb = "resistance" if price >= spot else "support"
        role = _semantic_role(lv.get("source"), lv.get("label"), fallback=fb)
        canon = {**lv, "price": price, "type": role, "role": role}
        key = _dedup_key(lv.get("label"))
        # collapse by EITHER near-equal price (cluster) OR shared prefix-stripped label key, so
        # PMH_<date> and INTRADAY_PMH at the same level become one entry across ALL writers.
        if (out and abs(_price_of(out[-1]) - price) <= ROLE_EPSILON) or (key and key in seen_keys):
            continue  # represented by the canonical (structural-first) survivor of this cluster
        seen_keys.add(key)
        out.append(canon)
    return out + expired


def _memory_merge_enabled() -> bool:
    """G11 feature flag: params.level_memory_live_merge (absent/false = wire OFF, exact
    pre-change behavior). FAIL-OFF: a missing/unreadable params never turns the wire on."""
    try:
        p = json.loads(PARAMS.read_text(encoding="utf-8"))
        return bool(p.get("level_memory_live_merge"))
    except (OSError, json.JSONDecodeError):
        return False


def _merge_memory_levels(levels: list[dict], spot: float, now_iso: str) -> list[dict]:
    """UNION the shadow multi-day memory map (key-levels-memory.json) into the live feed
    (G11 wire, HANDOFF-2026-07-09). PURELY ADDITIVE: strips only prior source=='level_memory'
    entries (idempotent re-inject), NEVER touches premarket/curated/INTRADAY levels. FAIL-OPEN:
    a missing or unparseable memory map returns `levels` UNTOUCHED (no-op) so the wire can never
    empty or corrupt the feed. Selection = tier=='Active' AND memory_score>=MIN_SCORE AND within
    +/-1.5% of spot.

    DIRECTIONAL BALANCE (2026-07-27, J live-flagged): picking the nearest-CAP overall
    (regardless of side) produced an all-resistance set with ZERO supports at today's
    session high — the engine had no floor at all to reason about. Now caps EACH side
    independently at MEMORY_MERGE_CAP_PER_SIDE nearest-to-spot (ties broken by higher
    score), so both resistance and support are represented whenever both exist in the
    candidate pool. Each merged level carries source/role/flipped_at + an EOD expiry so
    heartbeat_core._level_expired keeps it TODAY and drops it tomorrow (fresh levels
    re-derive every session)."""
    try:
        mem = json.loads(MEMORY_MAP.read_text(encoding="utf-8"))
        cand = mem.get("levels") or []
    except (OSError, json.JSONDecodeError):
        return levels  # fail-open no-op — a bad/missing memory map must never wipe the feed
    kept = [lv for lv in levels if str(lv.get("source", "")).lower() != "level_memory"]
    today = now_iso[:10]
    band = spot * MEMORY_MERGE_SPOT_PCT
    picks = []
    for m in cand:
        try:
            price = round(float(m["price"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        if str(m.get("tier", "")).lower() != "active":
            continue
        try:
            score = float(m.get("memory_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score < MEMORY_MERGE_MIN_SCORE or abs(price - spot) > band:
            continue
        picks.append((abs(price - spot), price, score, m))
    # split by side of spot BEFORE ranking, so a side-blind nearest-N can never starve one
    # side even when the other side has denser/closer candidates.
    above = sorted((t for t in picks if t[1] >= spot), key=lambda t: (t[0], -t[2]))
    below = sorted((t for t in picks if t[1] < spot), key=lambda t: (t[0], -t[2]))
    selected = above[:MEMORY_MERGE_CAP_PER_SIDE] + below[:MEMORY_MERGE_CAP_PER_SIDE]
    merged = []
    for _dist, price, _score, m in selected:
        role = str(m.get("role") or m.get("type") or ("resistance" if price >= spot else "support"))
        merged.append({
            "price": price, "type": role, "role": role,
            "label": str(m.get("label") or f"MEMORY_{role.upper()}_{price:.2f}"),
            "tier": "Active", "source": "level_memory",
            "verified_at": now_iso, "expires_at": today + "T16:00:00-04:00",
            "memory_score": m.get("memory_score"), "touches": m.get("touches"),
            "role_flips": m.get("role_flips"), "flipped_at": m.get("flipped_at"),
            "reasoning": (f"Multi-day memory {role} (score {m.get('memory_score')}, flipped_at "
                          f"{m.get('flipped_at')}) merged live via G11 wire (level_memory_live_merge): "
                          f"nearest-{MEMORY_MERGE_CAP_PER_SIDE}-per-side of spot (directional balance, "
                          f"2026-07-27), score>={int(MEMORY_MERGE_MIN_SCORE)}, within +/-1.5%."),
            "entity_id": None, "draw_needed": False,
        })
    return kept + merged


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

    # Each computed level is tied to the SOURCE SUBSET that backs it, so the degeneracy
    # guard checks the right data (RTH high/low + swings all read `rth`; PMH/PML read
    # `pre`) — 2026-07-27, J live-flagged: PMH=744.90 was a single 80-share IEX print.
    computed = []
    refused = []

    def _try_add(label: str, price: float, source: str, sub: pd.DataFrame) -> None:
        reason = _degeneracy_reason(sub)
        if reason:
            refused.append({"ts_et": now_iso, "label": f"{label}_{today}", "reason": reason,
                            "n_bars": len(sub),
                            "volume": float(sub["volume"].sum()) if len(sub) else 0.0})
            return
        computed.append((label, price, source, len(sub), float(sub["volume"].sum())))

    if len(rth):
        _try_add("INTRADAY_RTH_HIGH", float(rth["high"].max()), "intraday_rth_high", rth)
        _try_add("INTRADAY_RTH_LOW", float(rth["low"].min()), "intraday_rth_low", rth)
    sh, sl = _swing_levels(rth)
    if sh is not None:
        _try_add("INTRADAY_SWING_HIGH", sh, "intraday_swing_high", rth)
    if sl is not None:
        _try_add("INTRADAY_SWING_LOW", sl, "intraday_swing_low", rth)
    if len(pre):
        # INTRADAY_PMH/PML collapse with any curated PMH_<date>/PML_<date> via _normalize_levels'
        # prefix-stripped dedup key (root-cause #2 fix) -- one logical premarket level, not 2/run.
        _try_add("INTRADAY_PMH", float(pre["high"].max()), "premarket_high", pre)
        _try_add("INTRADAY_PML", float(pre["low"].min()), "premarket_low", pre)

    # Load existing levels, drop our own prior INTRADAY_* upserts (idempotent), keep the rest.
    try:
        kl = json.loads(KEY_LEVELS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        kl = {"schema_version": 1, "levels": []}
    levels = [lv for lv in (kl.get("levels") or []) if not str(lv.get("label", "")).startswith("INTRADAY_")]

    added = []
    for label, price, source, n_bars, volume in computed:
        lvl = _level(price, spot, f"{label}_{today}", source, now_iso,
                     source_feed="sip", n_bars=n_bars, volume=volume, weight=LEVEL_WEIGHT_INTRADAY)
        levels.append(lvl)
        added.append((lvl["label"], lvl["price"], lvl["role"]))

    # G11 (2026-07-09): union the shadow multi-day memory map's near-price high-conviction
    # levels when the wire flag is on. Fail-open + additive + idempotent; flag OFF (default)
    # leaves this a no-op => byte-identical to pre-change behavior. Prior level_memory entries
    # (e.g. a Layer-1 hand-insert) are re-derived fresh from the map here when the flag is on.
    memory_merged = 0
    if _memory_merge_enabled():
        levels = _merge_memory_levels(levels, spot, now_iso)
        memory_merged = sum(1 for lv in levels if str(lv.get("source", "")).lower() == "level_memory")

    # WS1 v2 (2026-07-27): union multi-week shelf zones from daily_context.py — fail-open
    # (a broken/missing daily_context must never break the level refresh), additive, and
    # idempotent (prior daily_context_shelf entries are stripped and re-derived fresh each
    # run, same pattern as the level_memory merge above).
    dctx = None
    shelf_upserted = 0
    if daily_context is not None:
        try:
            dctx = daily_context.compute_daily_context(now=now)
        except Exception as exc:  # noqa: BLE001 — never let a daily_context bug break level refresh
            dctx = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if dctx.get("ok"):
            levels = [lv for lv in levels if str(lv.get("source", "")).lower() != "daily_context_shelf"]
            for sh_zone in dctx.get("shelf_zones") or []:
                lo, hi = sh_zone["band_low"], sh_zone["band_high"]
                mid = round((lo + hi) / 2, 2)
                if abs(mid - spot) > SHELF_UPSERT_BAND:
                    continue  # daily_context keeps the full universe; only near-price shelves feed the engine
                brk = sh_zone.get("break")
                if brk and brk.get("direction") == "down":
                    role = "resistance"  # broke DOWN through it -> now overhead ceiling
                elif brk and brk.get("direction") == "up":
                    role = "support"     # broke UP through it -> now underfoot floor
                else:
                    role = "resistance" if mid >= spot else "support"
                retest = sh_zone.get("backside_retest") or {}
                lvl = {
                    "price": mid, "type": role, "role": role,
                    "label": f"SHELF_{lo:.2f}_{hi:.2f}_{today}",
                    "tier": "Active", "source": "daily_context_shelf",
                    "verified_at": now_iso, "expires_at": today + "T16:00:00-04:00",
                    "reasoning": (f"Multi-week shelf {lo:.2f}-{hi:.2f} ({sh_zone['touches']} touches over "
                                  f"{sh_zone['span_sessions']} sessions)"
                                  + (f", broken {brk['direction']} {brk['break_date']}" if brk else "")
                                  + (", BACKSIDE RETEST in progress" if retest.get("backside_retest") else "")
                                  + " via daily_context.py."),
                    "entity_id": None, "draw_needed": False,
                    "zone_width": round((hi - lo) / 2, 4), "zone_width_provenance": "shelf_band_observed",
                    "weight": LEVEL_WEIGHT_SHELF,
                    "touches": sh_zone["touches"], "span_sessions": sh_zone["span_sessions"],
                    "shelf_broken": sh_zone["broken"], "shelf_break": brk,
                    "backside_retest": sh_zone.get("backside_retest"),
                }
                levels.append(lvl)
                shelf_upserted += 1

    # Normalize the FULL written set: one polarity role per price + collapse near-equal
    # duplicates, so the engine never reads a price as both resistance and support and the
    # 6-9x curated PMH/PML pile-up self-heals every run (2026-06-30 contradictory-role fix).
    levels = _normalize_levels(levels, spot)

    kl["levels"] = levels
    kl["as_of"] = now_iso
    kl["spot_at_compute"] = round(spot, 2)
    kl["computed_from"] = "refresh_levels_intraday.py (live Alpaca REST, SIP feed, TV-independent)"
    # the live feed owns the session date so key-levels never sits stale-dated when the
    # premarket LLM silent-fails (06-30: premarket exit-0-no-write left date frozen at 06-29).
    kl["date"] = today
    kl["for_session"] = today
    # Degeneracy refusals (2026-07-27): loud, one-line, THIS-RUN-ONLY (recomputed fresh
    # every cycle, same idempotent pattern as INTRADAY_* — never accumulates unbounded).
    # C7/L241: a refusal must be visible in the file, not just silently skipped.
    kl["provenance_notes"] = refused

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
        # WS1 v2 (2026-07-27): daily_context section (gap state + nearest shelf proximity +
        # backside_retest) so the morning brief / premarket compiler can SPEAK the shelf
        # geometry, not just the bare level list. Fail-open with the outer try/except.
        if dctx and dctx.get("ok"):
            shelves = dctx.get("shelf_zones") or []
            nearest = min(shelves, key=lambda s: abs(((s["band_low"] + s["band_high"]) / 2) - spot)) \
                if shelves else None
            bias["daily_context"] = {
                "computed_at_et": dctx.get("computed_at_et"),
                "gap_state": dctx.get("gap_state"),
                "prior_day": dctx.get("prior_day"),
                "nearest_shelf": ({
                    "band": [nearest["band_low"], nearest["band_high"]],
                    "distance_from_spot": round(abs(((nearest["band_low"] + nearest["band_high"]) / 2) - spot), 2),
                    "touches": nearest["touches"], "broken": nearest["broken"],
                    "break": nearest.get("break"), "backside_retest": nearest.get("backside_retest"),
                } if nearest else None),
            }
        btmp = TODAY_BIAS.with_suffix(".json.tmp")
        btmp.write_text(json.dumps(bias, indent=1), encoding="utf-8")
        btmp.replace(TODAY_BIAS)
    except Exception as exc:  # noqa: BLE001 — EMA patch is best-effort, never blocks the level write
        ema_patch = {"error": str(exc)}

    active = sorted({lv["price"] for lv in levels if abs(lv["price"] - spot) <= ACTIVE_BAND})
    return {"ok": True, "ts_et": now_iso, "spot": round(spot, 2), "added": added,
            "refused": refused, "shelf_upserted": shelf_upserted,
            "memory_merged": memory_merged, "engine_active_levels": active, "ema": ema_patch}


if __name__ == "__main__":
    out = refresh()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("ok") else 1)
