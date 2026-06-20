"""Journal J's REAL Webull WINNING trades into Project Gamma's canonical schema.

"Data rules": J's real winners are first-class journaled ground truth — the
foundation the automation is built from. This script reads the reconstructed
round-trip ledger (`analysis/webull-j-trades/j_roundtrips.csv`), filters to the
WINNERS in the SPX/SPY family (the universe the SPY 0DTE engine actually trades;
SPX/SPY track ~10:1, so SPY price action *is* the setup even for SPXW fills),
reconstructs the look-ahead-free SETUP CONTEXT at J's entry from SPY 5m bars, and
writes two DEDICATED ground-truth artifacts:

  - journal/j-real-winners.csv  — the canonical ~41-column trades.csv schema, so
        these winners are engine / analyst / backtest-consumable. Tagged clearly
        as historical-ground-truth (account_id="j_webull_hist") so they NEVER
        pollute the live trades.csv (different era / instrument / account).
  - journal/j-real-winners.md   — a per-trade markdown digest + the "signature of
        J's winners" profile (archetype / direction / time-of-day distribution).

PRIORITY (per L168 — J's genuine edge): the 1-2 contract winners are the ground
truth to replicate. 3+ lot winners are journaled too but flagged as
`size_class=3plus_lot` (less representative — J's documented losing zone).

Setup context is reconstructed look-ahead-free at J's entry bar, REUSING the
exact feature logic in `webull_winner_setups.py` (no logic duplication):
  - price vs session VWAP-to-date, intraday trend (prior-30m sign),
  - new-session-extreme (breakout) vs pullback/midrange/reversal,
  - nearest reference level (PDH/PDL/round/PMH/PML) at entry,
  - the trigger (reclaim / rejection / breakout / pullback),
  - the coarse ARCHETYPE (pullback-continuation / reversal-off-extreme /
    momentum-breakout / trend-continuation).

SPY 5m IEX bars are fetched from the Alpaca Data REST API (same feed the
`alpaca` MCP uses) and cached to `analysis/webull-j-trades/winner_bar_cache.json`
so the run is reproducible and re-runs are free. Credentials are read from the
project MCP config (`~/.claude.json` -> alpaca env) or env vars — never hardcoded.
If bars for an old date are unreachable, the trade is STILL journaled with the
fields available and `setup_context="candles_unavailable"` (the trade is never
dropped — honesty over completeness).

Pure stdlib + the existing setup module. py_compile clean. Propose-only — writes
ONLY the two journal artifacts + the bar cache; touches no live engine / params.

Usage:
    python -m autoresearch.webull_winner_journal            # journal (uses/refreshes cache)
    python -m autoresearch.webull_winner_journal --no-fetch # cache-only, mark missing dates unavailable
    python -m autoresearch.webull_winner_journal --limit 5  # smoke: first 5 winner dates
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# Reuse the canonical, audited feature extractor — DO NOT re-implement.
from autoresearch.webull_winner_setups import Bar, extract_features

REPO = Path(__file__).resolve().parent.parent.parent
WEBULL_DIR = REPO / "analysis" / "webull-j-trades"
ROUNDTRIPS = WEBULL_DIR / "j_roundtrips.csv"
BAR_CACHE = WEBULL_DIR / "winner_bar_cache.json"
LEGACY_CACHE = WEBULL_DIR / "winner_candles.json"  # top-9 bars cached by an earlier step

JOURNAL_DIR = REPO / "journal"
OUT_CSV = JOURNAL_DIR / "j-real-winners.csv"
OUT_MD = JOURNAL_DIR / "j-real-winners.md"

ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"

# Canonical trades.csv schema (the ~41-column header). Source of truth: journal/trades.csv.
SCHEMA = [
    "date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
    "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
    "dollar_pnl", "r_multiple", "stop_px", "target_px", "dollar_risk",
    "pct_risk_of_acct", "account_equity_pre", "followed_rules", "setup_quality",
    "fill_quality", "gamma_recommended", "j_override", "hold_minutes",
    "trade_grade", "trade_grade_score", "delta_at_entry", "iv_at_entry",
    "iv_regime", "slippage_cents", "exit_slippage_cents", "tod_bucket",
    "bars_after_trigger", "entry_relative_to_bar", "hold_quality_pct",
    "cf_time_stop_pnl", "cf_high_water_pnl", "archetype_match_json",
    "tape_assistance", "notes_short", "account_id",
]

# Map the setup module's fine archetype labels to the playbook-aligned coarse class.
ARCHETYPE_TO_CLASS = {
    "momentum_breakout_continuation": "momentum-breakout",
    "bullish_pullback_resumption": "pullback-continuation",
    "bearish_pullback_resumption": "pullback-continuation",
    "trend_continuation_midrange": "trend-continuation",
    "bullish_reversal_off_low": "reversal-off-extreme",
    "bearish_reversal_off_high": "reversal-off-extreme",
    "counter_trend_fade": "reversal-off-extreme",
}

# Map archetype -> the in-spirit named playbook setup (for analyst/engine cross-ref).
ARCHETYPE_TO_SETUP = {
    "momentum-breakout": "MOMENTUM_BREAKOUT",
    "pullback-continuation": "RIDE_THE_RIBBON",
    "trend-continuation": "RIDE_THE_RIBBON",
    "reversal-off-extreme": "BEARISH_REJECTION",
}


# --------------------------------------------------------------------------- #
# Credentials (read from project MCP config or env — never hardcoded)
# --------------------------------------------------------------------------- #
def _load_alpaca_creds() -> tuple[Optional[str], Optional[str]]:
    """Return (key, secret) from env vars, else from ~/.claude.json alpaca block."""
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if key and sec:
        return key, sec
    cfg = Path(os.path.expanduser("~/.claude.json"))
    if not cfg.exists():
        return key, sec
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return key, sec

    found: dict[str, str] = {}

    def _walk(node: Any) -> None:
        if found:
            return
        if isinstance(node, dict):
            if node.get("ALPACA_API_KEY") and node.get("ALPACA_SECRET_KEY"):
                found["key"] = node["ALPACA_API_KEY"]
                found["sec"] = node["ALPACA_SECRET_KEY"]
                return
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return (found.get("key") or key), (found.get("sec") or sec)


# --------------------------------------------------------------------------- #
# Bar cache + fetch
# --------------------------------------------------------------------------- #
def _load_bar_cache() -> dict[str, list[dict[str, Any]]]:
    """date -> list of {t,o,h,l,c,v}. Seed from the legacy top-9 candle cache."""
    cache: dict[str, list[dict[str, Any]]] = {}
    if BAR_CACHE.exists():
        try:
            cache = json.loads(BAR_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}
    # Seed any dates we already have from the earlier top-winner candle cache.
    if LEGACY_CACHE.exists():
        try:
            legacy = json.loads(LEGACY_CACHE.read_text(encoding="utf-8"))
            for w in legacy.get("winners", []):
                cache.setdefault(w["date"], w["bars"])
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    return cache


def _save_bar_cache(cache: dict[str, list[dict[str, Any]]]) -> None:
    BAR_CACHE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")


def _fetch_spy_bars(date: str, key: str, sec: str) -> Optional[list[dict[str, Any]]]:
    """Fetch SPY 5m IEX bars for one ET trade date (RTH+context). None on failure."""
    # Pull the full UTC day so RTH (13:30-20:00Z) is covered regardless of DST edge.
    start = f"{date}T08:00:00Z"
    end = f"{date}T23:59:00Z"
    params = (
        f"?timeframe=5Min&feed=iex&adjustment=raw&limit=2000"
        f"&start={start}&end={end}&sort=asc"
    )
    req = urllib.request.Request(
        ALPACA_BARS_URL + params,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted host)
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"    WARN fetch {date}: {exc}")
        return None
    bars = payload.get("bars") or []
    if not bars:
        return None
    out = []
    for b in bars:
        out.append({"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"],
                    "c": b["c"], "v": int(b.get("v", 0))})
    return out


def _utc_to_et(ts_z: str) -> dt.datetime:
    """'2021-07-07T13:30:00Z' (or with offset) -> naive ET datetime.

    Localizes via America/New_York so EST (UTC-5) vs EDT (UTC-4) is handled
    per-date (lesson C6 — never hardcode the offset; early-2022 dates are EST,
    summer dates are EDT).
    """
    s = ts_z.replace("Z", "+00:00")
    base = dt.datetime.fromisoformat(s)
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.timezone.utc)
    return base.astimezone(_ET).replace(tzinfo=None)


def _rth_bars(raw: list[dict[str, Any]]) -> list[Bar]:
    """Raw cache bars -> RTH (09:30-16:00 ET) Bar list, sorted, look-ahead safe."""
    out = []
    for b in raw:
        t_et = _utc_to_et(b["t"])
        if dt.time(9, 30) <= t_et.time() < dt.time(16, 0):
            out.append(Bar(t_et=t_et, o=float(b["o"]), h=float(b["h"]),
                           l=float(b["l"]), c=float(b["c"]), v=int(b["v"])))
    out.sort(key=lambda x: x.t_et)
    return out


# --------------------------------------------------------------------------- #
# Level + trigger reconstruction (look-ahead free, at entry bar)
# --------------------------------------------------------------------------- #
def _nearest_level(bars: list[Bar], entry_idx: int, prior_day_bars: Optional[list[Bar]]) -> dict[str, Any]:
    """Identify the nearest reference level to J's entry close.

    Candidate levels (all derivable look-ahead-free from same-session bars +,
    when available, the prior session's H/L):
      - round number (nearest whole SPY dollar),
      - session open (first RTH bar open),
      - PDH / PDL (prior-day high/low) if prior_day_bars supplied,
      - intraday session-high / session-low established BEFORE entry.
    Returns {level_name, level_px, dist_pct}.
    """
    entry = bars[entry_idx]
    px = entry.c
    pre = bars[:entry_idx] if entry_idx > 0 else bars[:1]
    cands: list[tuple[str, float]] = []
    cands.append(("ROUND", round(px)))
    cands.append(("SESSION_OPEN", bars[0].o))
    cands.append(("IDH", max(b.h for b in pre)))   # intraday high before entry
    cands.append(("IDL", min(b.l for b in pre)))   # intraday low before entry
    if prior_day_bars:
        cands.append(("PDH", max(b.h for b in prior_day_bars)))
        cands.append(("PDL", min(b.l for b in prior_day_bars)))
    name, lvl = min(cands, key=lambda c: abs(px - c[1]))
    dist_pct = (px - lvl) / lvl * 100 if lvl else 0.0
    return {"level_name": name, "level_px": round(lvl, 2), "dist_pct": round(dist_pct, 3)}


def _trigger(bias: str, feats: dict[str, Any]) -> str:
    """Coarse trigger label from look-ahead-free features + archetype."""
    arch = feats.get("archetype", "")
    new_extreme = feats.get("new_session_extreme", False)
    if "reversal" in arch:
        return "rejection" if bias == "bear" else "reclaim"
    if new_extreme:
        return "breakout"
    if "pullback" in arch:
        return "pullback"
    # midrange trend continuation: a reclaim (bull) / rejection (bear) of the mid
    return "reclaim" if bias == "bull" else "rejection"


def _tod_bucket(hhmm: str) -> str:
    """Map entry HH:MM (ET) to the trades.csv tod_bucket vocabulary."""
    h, m = (int(x) for x in hhmm.split(":"))
    minutes = h * 60 + m
    if minutes < 11 * 60:           # < 11:00
        return "MORNING"
    if minutes < 14 * 60:           # 11:00-13:59
        return "MIDDAY"
    return "AFTERNOON"


# --------------------------------------------------------------------------- #
# Row assembly (canonical schema)
# --------------------------------------------------------------------------- #
def _instrument(symbol: str, underlier: str, is_family: bool) -> str:
    """Human contract label for the canonical `contract` column."""
    # SPXW cash-settled vs SPY ETF — keep the real underlier so era/instrument is explicit.
    return underlier


def _hold_minutes(entry_time: str, exit_time: str) -> str:
    try:
        a = dt.datetime.fromisoformat(entry_time)
        b = dt.datetime.fromisoformat(exit_time)
        return str(int(round((b - a).total_seconds() / 60)))
    except (ValueError, TypeError):
        return ""


def build_row(trip: dict[str, str], setup_ctx: Optional[dict[str, Any]],
              level: Optional[dict[str, Any]]) -> dict[str, str]:
    """Map one round-trip + reconstructed context to the canonical trades.csv row."""
    date = trip["date"]
    bias = trip["bias"]
    right = trip["right"]
    qty = int(trip["qty"])
    strike = trip["strike"]
    expiry = trip["expiry"]
    entry_px = float(trip["entry_px"])
    exit_px = float(trip["exit_px"])
    pnl = float(trip["pnl"])
    underlier = trip["underlier"]
    is_family = trip["is_spx_family"] == "True"
    is_0dte = trip["is_0dte"] == "True"

    entry_t = trip["entry_time"]
    exit_t = trip["exit_time"]
    entry_hhmm = entry_t.split(" ")[1][:5] if " " in entry_t else ""
    exit_hhmm = exit_t.split(" ")[1][:5] if " " in exit_t else ""

    size_class = "1-2_lot" if qty <= 2 else "3plus_lot"
    contract = f"{underlier} {expiry} {strike}{right}"
    dte = "0" if is_0dte else _dte(date, expiry)

    # premium dollars (per-contract px * 100 * qty)
    premium_paid = round(entry_px * 100 * qty)
    premium_recv = round(exit_px * 100 * qty)

    # --- setup-context-derived fields ---
    if setup_ctx and "error" not in setup_ctx:
        arch_fine = setup_ctx.get("archetype", "")
        arch_class = ARCHETYPE_TO_CLASS.get(arch_fine, "trend-continuation")
        setup_name = ARCHETYPE_TO_SETUP.get(arch_class, "RIDE_THE_RIBBON")
        vwap_side = setup_ctx.get("vwap_side", "?")
        trend = setup_ctx.get("prior_trend_30m_pct")
        new_ext = setup_ctx.get("new_session_extreme")
        trig = _trigger(bias, setup_ctx)
        lvl_name = level["level_name"] if level else "?"
        lvl_px = level["level_px"] if level else ""
        lvl_dist = level["dist_pct"] if level else ""
        ctx_status = "reconstructed"
        notes = (
            f"HISTORICAL GROUND TRUTH (J real Webull fill, {underlier} {date}). "
            f"{size_class}. Archetype={arch_class} ({arch_fine}); trigger={trig}; "
            f"VWAP {vwap_side}; prior-30m {trend}%; new_extreme={new_ext}; "
            f"nearest level {lvl_name}@{lvl_px} ({lvl_dist}% away). "
            f"SPY-proxy 5m setup (SPX/SPY ~10:1)."
        )
        arch_json = json.dumps({
            "size_class": size_class, "archetype": arch_class,
            "archetype_fine": arch_fine, "trigger": trig,
            "vwap_side": vwap_side, "new_session_extreme": new_ext,
            "prior_trend_30m_pct": trend, "level": level,
            "playbook_setup": setup_name, "context": ctx_status,
        }, separators=(",", ":"))
        delta_proxy = _delta_proxy(right, setup_ctx, strike, underlier)
    else:
        arch_class = ""
        setup_name = "UNKNOWN_CANDLES_UNAVAILABLE"
        trig = ""
        ctx_status = "candles_unavailable"
        notes = (
            f"HISTORICAL GROUND TRUTH (J real Webull fill, {underlier} {date}). "
            f"{size_class}. setup_context=candles_unavailable (SPY 5m bars "
            f"unreachable for this date) — journaled with trade fields only."
        )
        arch_json = json.dumps({
            "size_class": size_class, "context": ctx_status,
        }, separators=(",", ":"))
        delta_proxy = ""

    row = {
        "date": date,
        "time_entry": entry_t.split(" ")[1] if " " in entry_t else "",
        "time_exit": exit_t.split(" ")[1] if " " in exit_t else "",
        "setup": setup_name,
        "contract": contract,
        "dte": dte,
        "strike": strike,
        "c_or_p": right,
        "qty": str(qty),
        "entry_px": f"{entry_px:g}",
        "exit_px": f"{exit_px:g}",
        "premium_paid": str(premium_paid),
        "premium_received": str(premium_recv),
        "dollar_pnl": f"{pnl:g}",
        "r_multiple": "N/A",
        "stop_px": "unknown (real fill, no recorded stop)",
        "target_px": "unknown (real fill, no recorded target)",
        "dollar_risk": str(premium_paid),  # full premium at risk (long option)
        "pct_risk_of_acct": "N/A (pre-Gamma account)",
        "account_equity_pre": "N/A",
        "followed_rules": "N/A",            # pre-Gamma — no rule framework applied
        "setup_quality": "GROUND_TRUTH",
        "fill_quality": "real_fill",
        "gamma_recommended": "N/A",
        "j_override": "N/A",
        "hold_minutes": _hold_minutes(entry_t, exit_t),
        "trade_grade": "WIN",
        "trade_grade_score": "",
        "delta_at_entry": delta_proxy,
        "iv_at_entry": "",
        "iv_regime": "",
        "slippage_cents": "",
        "exit_slippage_cents": "",
        "tod_bucket": _tod_bucket(entry_hhmm) if entry_hhmm else "",
        "bars_after_trigger": "0",
        "entry_relative_to_bar": "at_close",
        "hold_quality_pct": "",
        "cf_time_stop_pnl": "",
        "cf_high_water_pnl": "",
        "archetype_match_json": arch_json,
        "tape_assistance": "",
        "notes_short": notes,
        "account_id": "j_webull_hist",
    }
    return row


def _dte(date: str, expiry: str) -> str:
    try:
        d = dt.date.fromisoformat(date)
        e = dt.date.fromisoformat(expiry)
        return str((e - d).days)
    except (ValueError, TypeError):
        return ""


def _delta_proxy(right: str, ctx: dict[str, Any], strike: str, underlier: str) -> str:
    """Rough moneyness tag (no chain greeks for 2021-23) — directional, advisory.

    Uses entry_close (SPY-scale) vs strike. SPXW/XSP strikes are SPX-scale (~10x
    SPY) so we scale the SPY close up 10x for those; SPY/QQQ strikes are already
    at-scale. Returns an ITM/ATM/OTM moneyness label rather than a fake numeric
    delta (honesty — we do not have the real greek for this era).
    """
    try:
        close = float(ctx.get("entry_close", 0))
        k = float(strike)
    except (TypeError, ValueError):
        return ""
    # SPX cash index symbols are ~10x SPY; ETF/equity symbols are at SPY scale.
    spx_scale = underlier.upper() in {"SPX", "SPXW", "XSP"} or k > 1000
    spot = close * 10 if spx_scale else close
    if right == "C":
        diff = spot - k
    else:
        diff = k - spot
    pts = abs(diff)
    if diff > 1.0:
        tag = "ITM"
    elif pts <= 1.0:
        tag = "ATM"
    else:
        tag = "OTM"
    return f"{tag}(~{diff:+.0f}pt)"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_family_winners() -> list[dict[str, str]]:
    """SPX/SPY-family closed winners (pnl>0), sorted by P&L desc."""
    rows = []
    with ROUNDTRIPS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["is_spx_family"] != "True":
                continue
            if r["status"] not in ("closed", "expired_worthless"):
                continue
            try:
                if float(r["pnl"]) <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            rows.append(r)
    rows.sort(key=lambda x: float(x["pnl"]), reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="Do not hit Alpaca; use cache only, mark missing as unavailable.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Smoke mode: only process the first N distinct winner dates.")
    args = ap.parse_args()

    winners = load_family_winners()
    print(f"SPX/SPY-family winners (pnl>0, closed): {len(winners)}")

    cache = _load_bar_cache()
    key, sec = _load_alpaca_creds()
    can_fetch = bool(key and sec) and not args.no_fetch
    if not can_fetch and not args.no_fetch:
        print("  NOTE: no Alpaca creds found — running cache-only.")

    # Fetch any missing dates (one call per distinct date), polite pacing.
    dates = sorted({w["date"] for w in winners})
    if args.limit:
        dates = dates[: args.limit]
        winners = [w for w in winners if w["date"] in set(dates)]
    missing = [d for d in dates if d not in cache]
    if can_fetch and missing:
        print(f"  fetching SPY 5m IEX bars for {len(missing)} uncached dates ...")
        for i, d in enumerate(missing, 1):
            bars = _fetch_spy_bars(d, key, sec)  # type: ignore[arg-type]
            if bars:
                cache[d] = bars
                if i % 10 == 0 or i == len(missing):
                    print(f"    {i}/{len(missing)} fetched; caching ...")
                    _save_bar_cache(cache)
            time.sleep(0.35)  # ~3 req/s — well under Alpaca limits
        _save_bar_cache(cache)

    # Build a per-date prior-trading-day bar lookup for PDH/PDL (use cached dates).
    cached_dates_sorted = sorted(cache.keys())

    def _prior_day_bars(date: str) -> Optional[list[Bar]]:
        idx = None
        for i, d in enumerate(cached_dates_sorted):
            if d == date:
                idx = i
                break
        if idx is None or idx == 0:
            return None
        prev = cached_dates_sorted[idx - 1]
        # only treat as PDH/PDL if it's a near-adjacent session (<=4 cal days back)
        try:
            gap = (dt.date.fromisoformat(date) - dt.date.fromisoformat(prev)).days
        except ValueError:
            return None
        if gap > 4:
            return None
        return _rth_bars(cache[prev])

    rows: list[dict[str, str]] = []
    n_reconstructed = 0
    n_unavailable = 0
    for trip in winners:
        date = trip["date"]
        bias = trip["bias"]
        entry_hhmm = trip["entry_time"].split(" ")[1][:5] if " " in trip["entry_time"] else "09:30"
        setup_ctx: Optional[dict[str, Any]] = None
        level: Optional[dict[str, Any]] = None
        raw = cache.get(date)
        if raw:
            bars = _rth_bars(raw)
            if bars:
                setup_ctx = extract_features(bars, entry_hhmm, bias)
                if setup_ctx and "error" not in setup_ctx:
                    # locate entry index for level reconstruction (same flooring rule)
                    h, m = (int(x) for x in entry_hhmm.split(":"))
                    floored = m - (m % 5)
                    target = bars[0].t_et.replace(hour=h, minute=floored, second=0)
                    eidx = 0
                    for i, b in enumerate(bars):
                        if b.t_et <= target:
                            eidx = i
                    level = _nearest_level(bars, eidx, _prior_day_bars(date))
        if setup_ctx and "error" not in setup_ctx:
            n_reconstructed += 1
        else:
            n_unavailable += 1
        rows.append(build_row(trip, setup_ctx, level))

    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(rows)
    _write_md(rows, n_reconstructed, n_unavailable)

    n12 = sum(1 for r in rows if int(r["qty"]) <= 2)
    n3 = len(rows) - n12
    print(f"\nJournaled {len(rows)} winners -> {OUT_CSV.relative_to(REPO)}")
    print(f"  1-2 lot (priority edge): {n12}   |   3+ lot (flagged): {n3}")
    print(f"  setup reconstructed: {n_reconstructed}   |   candles_unavailable: {n_unavailable}")
    print(f"  digest -> {OUT_MD.relative_to(REPO)}")
    return 0


def _write_csv(rows: list[dict[str, str]]) -> None:
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _profile(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Compute the 'signature of J's winners' distribution."""
    from collections import Counter
    arch = Counter()
    direction = Counter()
    tod = Counter()
    trig = Counter()
    vwap = Counter()
    size = Counter()
    n_recon = 0
    for r in rows:
        try:
            aj = json.loads(r["archetype_match_json"])
        except (json.JSONDecodeError, TypeError):
            aj = {}
        size["1-2_lot" if int(r["qty"]) <= 2 else "3plus_lot"] += 1
        direction["bull (calls)" if r["c_or_p"] == "C" else "bear (puts)"] += 1
        if r["tod_bucket"]:
            tod[r["tod_bucket"]] += 1
        if aj.get("context") == "reconstructed":
            n_recon += 1
            arch[aj.get("archetype", "?")] += 1
            trig[aj.get("trigger", "?")] += 1
            vwap[aj.get("vwap_side", "?")] += 1
    return {
        "n": len(rows), "n_recon": n_recon, "size": size, "direction": direction,
        "tod": tod, "archetype": arch, "trigger": trig, "vwap": vwap,
    }


def _write_md(rows: list[dict[str, str]], n_recon: int, n_unavail: int) -> None:
    prof = _profile(rows)
    total_pnl = sum(float(r["dollar_pnl"]) for r in rows)
    rows_sorted = sorted(rows, key=lambda r: float(r["dollar_pnl"]), reverse=True)

    def _line_tbl(counter, label):
        out = [f"| {label} | n | share |", "|---|---|---|"]
        tot = sum(counter.values()) or 1
        for k, n in counter.most_common():
            out.append(f"| {k} | {n} | {n / tot * 100:.0f}% |")
        return "\n".join(out)

    lines: list[str] = []
    lines.append("# J's Real Webull WINNERS — Journaled Ground Truth")
    lines.append("")
    lines.append("> **Data rules:** these are J's REAL winning Webull fills (2021-2023), "
                 "journaled in the canonical `trades.csv` schema as first-class "
                 "ground truth — the foundation the automation is built from.")
    lines.append("> Canonical CSV: [`journal/j-real-winners.csv`](j-real-winners.csv) "
                 "(schema-identical to `trades.csv`; `account_id=j_webull_hist` so it "
                 "NEVER pollutes the live journal).")
    lines.append("> Source ledger: `analysis/webull-j-trades/j_roundtrips.csv`. "
                 "Setup context: SPY 5m IEX bars (SPX/SPY ~10:1), reconstructed "
                 "look-ahead-free at J's entry bar via "
                 "`backtest/autoresearch/webull_winner_setups.py`.")
    lines.append(f"> Generated {dt.date.today().isoformat()}. Propose-only — touches no "
                 "live engine / params (Rule 9).")
    lines.append("")
    lines.append("## Scope + honesty")
    lines.append("")
    lines.append(f"- **{prof['n']} SPX/SPY-family winners** journaled "
                 f"(total realized +${total_pnl:,.0f}).")
    lines.append(f"- **{prof['size'].get('1-2_lot', 0)} are 1-2 lot** — J's genuine "
                 "edge (per L168), the ground truth to replicate. "
                 f"**{prof['size'].get('3plus_lot', 0)} are 3+ lot** — flagged "
                 "`size_class=3plus_lot` (less representative; J's documented losing zone).")
    lines.append(f"- Setup context reconstructed for **{n_recon}**; "
                 f"**{n_unavail}** marked `candles_unavailable` (SPY bars unreachable; "
                 "trade still journaled with its fields).")
    lines.append("- **Era caveat:** 2021-23 SPX-scale options, SPY-proxy candles, no "
                 "chain greeks (delta is an ITM/ATM/OTM moneyness tag, not a real "
                 "greek). Validate any derived rule on the full population first "
                 "(lesson C24 — anchor winners can be one-off exceptions).")
    lines.append("")
    lines.append("## The signature of J's winners (profile)")
    lines.append("")
    lines.append("### Size class")
    lines.append("")
    lines.append(_line_tbl(prof["size"], "size"))
    lines.append("")
    lines.append("### Direction")
    lines.append("")
    lines.append(_line_tbl(prof["direction"], "direction"))
    lines.append("")
    lines.append("### Time-of-day (entry)")
    lines.append("")
    lines.append(_line_tbl(prof["tod"], "tod_bucket"))
    lines.append("")
    lines.append(f"### Archetype  (of {prof['n_recon']} reconstructed)")
    lines.append("")
    lines.append(_line_tbl(prof["archetype"], "archetype"))
    lines.append("")
    lines.append("### Trigger")
    lines.append("")
    lines.append(_line_tbl(prof["trigger"], "trigger"))
    lines.append("")
    lines.append("### VWAP alignment at entry")
    lines.append("")
    lines.append(_line_tbl(prof["vwap"], "vwap_side"))
    lines.append("")
    lines.append("## Per-trade digest (sorted by P&L)")
    lines.append("")
    lines.append("| Date | Underlier | Dir | Qty | Entry→Exit ET | Hold | Entry→Exit px | P&L | Archetype | Trigger | VWAP | Nearest lvl | Ctx |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows_sorted:
        try:
            aj = json.loads(r["archetype_match_json"])
        except (json.JSONDecodeError, TypeError):
            aj = {}
        e = r["time_entry"][:5]
        x = r["time_exit"][:5]
        dirn = "bull" if r["c_or_p"] == "C" else "bear"
        lvl = aj.get("level") or {}
        lvl_s = f"{lvl.get('level_name', '')}@{lvl.get('level_px', '')}" if lvl else "-"
        ctx = "OK" if aj.get("context") == "reconstructed" else "n/a"
        und = r["contract"].split(" ")[0]
        lines.append(
            f"| {r['date']} | {und} | {dirn} | {r['qty']} | {e}->{x} | "
            f"{r['hold_minutes']}m | {r['entry_px']}->{r['exit_px']} | "
            f"+${float(r['dollar_pnl']):.0f} | {aj.get('archetype', '-')} | "
            f"{aj.get('trigger', '-')} | {aj.get('vwap_side', '-')} | {lvl_s} | {ctx} |"
        )
    lines.append("")
    lines.append("## What feeds the engine (recommendations, not ratified)")
    lines.append("")
    lines.append("- These journaled winners are the **real-fill ground-truth anchor "
                 "set** for validating the diversified/regime book on J's actual edge "
                 "— richer than the 3 bearish OP-16 source-of-truth trades.")
    lines.append("- The 1-2 lot subset is the canonical replication target; the 3+ lot "
                 "rows are retained for completeness but excluded from any edge-capture "
                 "target (per L168 sizing finding).")
    lines.append("- Cross-reference `markdown/0dte/J-WEBULL-EDGE-2021-2023.md` for the full "
                 "style analytics (time-of-day, sizing, call/put expectancy).")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
