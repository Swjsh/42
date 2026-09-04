"""CATALYST-DIRECTION STAGE A -- does a news catalyst supply DIRECTION that price-geometry
triggers provably cannot?

Run exactly as frozen in
`analysis/recommendations/prereg-catalyst-direction-2026-09-03.json`. That file is the source
of truth for every threshold below (symbol set, window, min_n, headline horizon, decision
rule) -- it is read at runtime, never hand-copied, so a prereg edit and this harness can never
silently drift apart.

WHY THIS HARNESS EXISTS: two independently-run, well-powered nulls (MULTI-LANE-STAGE-A,
WEEKLY-EXPIRY-EXPERIMENT) already killed price-geometry triggers on non-SPY names -- both
concluded "detects volatility, not direction." News is a mechanically different information
class that has never been tested here. See the prereg's `provenance` block.

NO LOOK-AHEAD, and it is the whole ballgame (same discipline as
backtest/tools/multi_intraday_null_harness.py, this harness's sibling and statistical
template):
  * direction = sign(close[t0+2] - close[t0]) is computed via `compute_direction()`, which is
    handed a 3-bar SLICE [t0, t0+1, t0+2] and physically cannot read anything past t0+2 --
    the no-look-ahead guarantee is structural (the later bars were never passed in), not just
    an assertion.
  * forward returns are computed via `compute_forward_returns()`, handed a slice starting at
    the entry bar (t0+2) -- it never reads backward, and `sign` (the already-fixed direction)
    is passed in as a plain float, not derived from anything in that slice.
  * an extra, non-obvious guard added beyond the prereg's literal text: the RTH-only bar
    filter puts DIFFERENT trading days *adjacent* in each symbol's flat bar array (non-RTH
    bars are dropped, so there is no gap in array INDICES at a session boundary, only a gap
    in wall-clock TIME). Without an explicit same-day check, a late-session headline's
    forward-return window could silently splice into the NEXT day's bars and report a
    fabricated "30-minute reaction" that is actually an overnight gap. Both the direction
    window (t0..t0+2) and the forward window (entry..entry+12) are checked against
    `bars[i]["ts"].date()` before being used; a crossing is skipped and counted, never blended
    in silently.

Reads only. Places no orders. Touches no file in setup/hooks/doctrine.py's FROZEN_TRADING_PATH.
Writes exactly ONE file: analysis/multi-lane/catalyst-direction-stageA.json.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi.lib import creds as mc  # noqa: E402
from multi.lib import scanners as sc  # noqa: E402

import pandas_market_calendars as mcal  # noqa: E402

ET_TZ = ZoneInfo("America/New_York")
DATA_BASE = "https://data.alpaca.markets"

OUT = REPO / "analysis" / "multi-lane" / "catalyst-direction-stageA.json"
PREREG = REPO / "analysis" / "recommendations" / "prereg-catalyst-direction-2026-09-03.json"

HORIZONS = (2, 6, 12)          # 5m bars -> 10 / 30 / 60 minutes, same as the sibling harness
HEADLINE_HORIZON = 6           # frozen: 30 minutes. NOT CLI-sweepable (prereg kill_list).
BAR_MINUTES = 5

# Frozen by the prereg's signal_definition -- verified necessary BEFORE freeze (a real
# 2024-02-20 market-wrap article tagged 25 symbols). NOT a CLI-sweepable knob.
MAX_SYMBOL_TAGS = 3

# Frozen by the prereg's signal_definition. NOT CLI-sweepable.
RTH_START_T = dt_time(9, 35)
RTH_END_T = dt_time(15, 30)

# Sanity floor distinguishing "basically no bar data came back" from a real fetch. This is NOT
# the statistical n>=50 SIGNALS gate (that's min_signals_required, read from the prereg below)
# -- it just refuses to proceed on a symbol whose bar history is implausibly short.
MIN_BARS_PER_SYMBOL = 200


class HarnessError(RuntimeError):
    """Fail loud: an empty, short, or failed fetch/result must never be reported as a result
    computed on nothing."""


# ==========================================================================================
# HTTP resilience -- retry + count, never silently drop a page (the L-scar this prereg names:
# "a prior harness counted errors but didn't print them and returned a plausible 47.10% that
# meant nothing"). `stats` is a mutable {"attempts": int, "errors": int} the caller owns.
# ==========================================================================================

def _resilient_call(fn: Callable[[], dict], stats: dict, max_tries: int = 3,
                     backoff_s: float = 1.0) -> dict:
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_tries + 1):
        stats["attempts"] += 1
        try:
            return fn()
        except sc.ScannerFetchError as e:
            stats["errors"] += 1
            last_exc = e
            if attempt < max_tries:
                time.sleep(backoff_s * attempt)
    raise HarnessError(f"fetch failed after {max_tries} attempts: {last_exc}")


# ==========================================================================================
# News: per-symbol, paginated, full window
# ==========================================================================================

def fetch_all_news_for_symbol(key: str, secret: str, symbol: str, start_iso: str, end_iso: str,
                               stats: dict, limit: int = 50) -> list[dict]:
    """Drains next_page_token for ONE symbol across the whole window, sort=asc. Returns raw
    article dicts, UNFILTERED (event filtering happens in process_symbol_news)."""
    out: list[dict] = []
    token: Optional[str] = None
    while True:
        cur_token = token
        raw = _resilient_call(
            lambda: sc.fetch_news_raw(key, secret, start=start_iso, end=end_iso, limit=limit,
                                       sort="asc", symbols=symbol, page_token=cur_token),
            stats)
        items = raw.get("news") or []
        out.extend(items)
        token = raw.get("next_page_token")
        if not token:
            break
    return out


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def in_rth_window(created_at_et: datetime, trading_days: set) -> bool:
    if created_at_et.date().isoformat() not in trading_days:
        return False
    t = created_at_et.time()
    return RTH_START_T <= t <= RTH_END_T


def process_symbol_news(symbol: str, raw_articles: list[dict], trading_days: set,
                         ) -> tuple[list[dict], dict]:
    """Frozen filter pipeline, applied IN ORDER per the brief:
      1. de-dup by (symbol, headline, created_at truncated to the minute) -- COUNT duplicates.
      2. keep only articles tagging <= MAX_SYMBOL_TAGS symbols.
      3. keep only created_at inside RTH on a US trading day.
    Returns (surviving_events, disclosure_counts). Each surviving event carries a
    `classify_headline()` category for the descriptive news-class split.
    """
    counts: Counter = Counter()
    counts["raw_fetched"] = len(raw_articles)

    seen: set = set()
    deduped: list[dict] = []
    for a in raw_articles:
        headline = a.get("headline") or ""
        created_raw = a.get("created_at") or ""
        dt_utc = _parse_iso(created_raw)
        if dt_utc is None:
            counts["unparseable_created_at"] += 1
            continue
        minute_key = dt_utc.strftime("%Y-%m-%dT%H:%M")
        key = (symbol, headline, minute_key)
        if key in seen:
            counts["duplicate_dropped"] += 1
            continue
        seen.add(key)
        deduped.append({
            "headline": headline, "created_at_raw": created_raw, "created_at_dt": dt_utc,
            "symbols_tagged": tuple(a.get("symbols") or ()),
        })
    counts["after_dedup"] = len(deduped)

    specific = [e for e in deduped if len(e["symbols_tagged"]) <= MAX_SYMBOL_TAGS]
    counts["dropped_too_broad_gt3_symbols"] = len(deduped) - len(specific)
    counts["after_specificity_filter"] = len(specific)

    in_rth: list[dict] = []
    for e in specific:
        et_dt = e["created_at_dt"].astimezone(ET_TZ)
        if in_rth_window(et_dt, trading_days):
            e["created_at_et"] = et_dt
            e["category"] = sc.classify_headline(e["headline"])
            in_rth.append(e)
    counts["dropped_outside_rth_or_non_trading_day"] = len(specific) - len(in_rth)
    counts["after_rth_filter"] = len(in_rth)

    return in_rth, dict(counts)


# ==========================================================================================
# Bars: per-symbol, paginated, feed try-sip-then-iex, own fetcher (NOT multi.core.fetch_bars_batch
# -- that hardcodes feed="iex" and does limit-based recent lookback, wrong for a 12-month pull).
# ==========================================================================================

def _fetch_bars_page(key: str, secret: str, symbol: str, start: str, end: str, timeframe: str,
                      feed: str, page_token: Optional[str], limit: int = 10000) -> dict:
    params = {"symbols": symbol, "timeframe": timeframe, "start": start, "limit": limit,
              "feed": feed, "adjustment": "raw", "sort": "asc"}
    if end:
        params["end"] = end
    if page_token:
        params["page_token"] = page_token
    url = f"{DATA_BASE}/v2/stocks/bars?{urllib.parse.urlencode(params)}"
    return sc._http_get_json(url, key, secret)  # noqa: SLF001 -- deliberate reuse, see module docstring


def fetch_all_bars_for_symbol(key: str, secret: str, symbol: str, start: str, end: str,
                               timeframe: str, stats: dict) -> tuple[list[dict], str]:
    """Try feed=sip first (fully paginated); if it errors out or comes back empty, retry the
    WHOLE pull on feed=iex. Returns (bars_asc, feed_used) where each bar is
    {"ts": aware ET datetime, "o","h","l","c","v"}, sorted oldest-first."""
    for feed in ("sip", "iex"):
        rows: list[dict] = []
        token: Optional[str] = None
        feed_stats = {"attempts": 0, "errors": 0}
        try:
            while True:
                cur_token = token
                data = _resilient_call(
                    lambda: _fetch_bars_page(key, secret, symbol, start, end, timeframe, feed,
                                              cur_token),
                    feed_stats)
                page_rows = (data.get("bars") or {}).get(symbol) or []
                rows.extend(page_rows)
                token = data.get("next_page_token")
                if not token:
                    break
        except HarnessError:
            stats["attempts"] += feed_stats["attempts"]
            stats["errors"] += feed_stats["errors"]
            continue  # try the next feed
        stats["attempts"] += feed_stats["attempts"]
        stats["errors"] += feed_stats["errors"]
        if rows:
            bars = []
            for b in rows:
                ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET_TZ)
                bars.append({"ts": ts, "o": float(b["o"]), "h": float(b["h"]),
                             "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)})
            bars.sort(key=lambda x: x["ts"])
            return bars, feed
        # empty (no error, but nothing returned) -> fall through and try the next feed
    return [], "none"


def filter_rth_bars(bars: list[dict]) -> list[dict]:
    """Keep only bars whose ET local start-time falls in [09:30, 16:00) -- extended-hours bars
    would otherwise contaminate the baseline pool and the signal construction with a different
    volatility regime, and are wider than the news RTH filter (09:35-15:30) deliberately, so a
    boundary headline's t0/entry search always has enough same-day bars either side."""
    return [b for b in bars if dt_time(9, 30) <= b["ts"].time() < dt_time(16, 0)]


# ==========================================================================================
# Signal construction -- structurally no-look-ahead (see module docstring)
# ==========================================================================================

def find_t0_index(bars_ts: list[datetime], created_at: datetime, bar_minutes: int) -> Optional[int]:
    """First index i such that bar i's CLOSE time (bars_ts[i] + bar_minutes) is strictly after
    `created_at`. Binary search: bars_ts is strictly ascending, so the predicate is monotonic."""
    span = timedelta(minutes=bar_minutes)
    lo, hi = 0, len(bars_ts)
    while lo < hi:
        mid = (lo + hi) // 2
        if bars_ts[mid] + span > created_at:
            hi = mid
        else:
            lo = mid + 1
    return lo if lo < len(bars_ts) else None


def compute_direction(bars_slice: list[dict]) -> Optional[float]:
    """`bars_slice` MUST be exactly [bar(t0), bar(t0+1), bar(t0+2)] -- 3 bars, nothing more.
    Structural no-look-ahead: this function cannot see any bar after t0+2 because it was never
    handed one. Returns +1.0/-1.0, or None for a non-positive close or a DISCARDED zero return
    (never assigned a side)."""
    if len(bars_slice) != 3:
        raise HarnessError(f"compute_direction needs exactly 3 bars, got {len(bars_slice)}")
    c_t0, c_entry = bars_slice[0]["c"], bars_slice[-1]["c"]
    if c_t0 <= 0 or c_entry <= 0:
        return None
    diff = c_entry - c_t0
    if diff == 0:
        return None
    return 1.0 if diff > 0 else -1.0


def compute_forward_returns(fwd_slice: list[dict], sign: float) -> dict:
    """`fwd_slice[0]` is the entry bar (t0+2); `fwd_slice[h]` is h bars after entry. Never reads
    backward -- `sign` (the already-fixed direction) arrives as a plain float, not derived from
    anything in this slice."""
    max_h = max(HORIZONS)
    assert len(fwd_slice) == max_h + 1, f"expected {max_h + 1} bars, got {len(fwd_slice)}"
    base = fwd_slice[0]["c"]
    out: dict = {}
    for h in HORIZONS:
        raw = 100.0 * (fwd_slice[h]["c"] / base - 1.0)
        out[f"fwd_{h}"] = round(sign * raw, 5)
        out[f"abs_{h}"] = round(abs(raw), 5)
    return out


def build_events_for_symbol(symbol: str, news_events: list[dict], bars: list[dict],
                             bars_ts: list[datetime]) -> tuple[list[dict], dict]:
    max_h = max(HORIZONS)
    skips: Counter = Counter()
    signals: list[dict] = []
    for ev in news_events:
        t0_idx = find_t0_index(bars_ts, ev["created_at_dt"], BAR_MINUTES)
        if t0_idx is None:
            skips["no_bar_closes_after_headline"] += 1
            continue
        entry_idx = t0_idx + 2
        if entry_idx >= len(bars):
            skips["insufficient_bars_for_entry"] += 1
            continue
        if bars[entry_idx]["ts"].date() != bars[t0_idx]["ts"].date():
            # See module docstring: an RTH-only flat array puts sessions adjacent in INDEX
            # space even though they are hours apart in WALL-CLOCK time.
            skips["entry_crosses_session_boundary"] += 1
            continue
        sign = compute_direction(bars[t0_idx:entry_idx + 1])
        if sign is None:
            skips["zero_or_invalid_return_discarded"] += 1
            continue
        if entry_idx + max_h >= len(bars):
            skips["insufficient_forward_bars"] += 1
            continue
        if bars[entry_idx + max_h]["ts"].date() != bars[entry_idx]["ts"].date():
            skips["forward_window_crosses_session_boundary"] += 1
            continue
        fwd = compute_forward_returns(bars[entry_idx:entry_idx + max_h + 1], sign)
        signals.append({
            "symbol": symbol, "headline": ev["headline"], "created_at": ev["created_at_raw"],
            "category": ev["category"], "trading_day": bars[entry_idx]["ts"].date().isoformat(),
            "direction": "UP" if sign > 0 else "DOWN",
            "t0_ts": bars[t0_idx]["ts"].isoformat(), "entry_ts": bars[entry_idx]["ts"].isoformat(),
            **fwd,
        })
    return signals, dict(skips)


def build_baseline_pool(bars: list[dict]) -> list[dict]:
    """Every eligible bar's forward returns -- the population random entries are drawn from.
    News-independent: this is pure price geometry over the same RTH-filtered bar series."""
    max_h = max(HORIZONS)
    pool = []
    for i in range(len(bars) - max_h):
        if bars[i + max_h]["ts"].date() != bars[i]["ts"].date():
            continue  # same session-boundary guard as the signal path
        base = bars[i]["c"]
        if base <= 0:
            continue
        row = {"i": i}
        for h in HORIZONS:
            row[f"raw_{h}"] = 100.0 * (bars[i + h]["c"] / base - 1.0)
        pool.append(row)
    return pool


# ==========================================================================================
# Null: random-entry draws, SAME construction for signed return AND abs move (the correction
# the prereg names explicitly -- the sibling harness only null-tested signed return).
# ==========================================================================================

def random_null(pools: dict, sig_counts: dict, dir_mix: dict, draws: int, seed: int) -> dict:
    rng = random.Random(seed)
    per_h_signed = {h: [] for h in HORIZONS}
    per_h_abs = {h: [] for h in HORIZONS}
    symbols = [s for s in pools if pools[s]]
    if not symbols:
        raise HarnessError("no baseline pool to draw a null from")

    for _ in range(draws):
        acc_signed = {h: [] for h in HORIZONS}
        acc_abs = {h: [] for h in HORIZONS}
        for sym in symbols:
            k = sig_counts.get(sym, 0)
            if k <= 0:
                continue
            picks = [rng.choice(pools[sym]) for _ in range(k)]
            bull_frac = dir_mix.get(sym, 0.5)
            for p in picks:
                sign = 1.0 if rng.random() < bull_frac else -1.0
                for h in HORIZONS:
                    acc_signed[h].append(sign * p[f"raw_{h}"])
                    acc_abs[h].append(abs(p[f"raw_{h}"]))  # sign-invariant: abs(sign*x)=abs(x)
        for h in HORIZONS:
            if acc_signed[h]:
                per_h_signed[h].append(st.mean(acc_signed[h]))
            if acc_abs[h]:
                per_h_abs[h].append(st.mean(acc_abs[h]))

    def summarize(vals: list[float]) -> dict:
        return {
            "draws": len(vals),
            "null_mean_of_means": round(st.mean(vals), 5) if vals else None,
            "null_MAX_of_means": round(max(vals), 5) if vals else None,
            "draw_means": [round(v, 5) for v in vals],
        }

    return {h: {"signed": summarize(per_h_signed[h]), "abs": summarize(per_h_abs[h])}
            for h in HORIZONS}


def empirical_pvalue(real: Optional[float], null_draw_means: list[float]) -> Optional[float]:
    """One-sided empirical p-value: P(null draw mean >= observed), +1/+1 continuity correction
    (standard permutation-test convention -- never exactly 0)."""
    if real is None or not null_draw_means:
        return None
    ge = sum(1 for v in null_draw_means if v >= real)
    return (ge + 1) / (len(null_draw_means) + 1)


def holm_correction(pvals: dict, alpha: float = 0.05) -> dict:
    """Holm-Bonferroni step-down across the given {label: p} family."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out: dict = {}
    still_rejecting = True
    for rank, (label, p) in enumerate(items, start=1):
        alpha_adj = alpha / (m - rank + 1)
        reject = still_rejecting and (p <= alpha_adj)
        if not reject:
            still_rejecting = False
        out[label] = {"p": round(p, 6), "rank": rank, "alpha_adjusted": round(alpha_adj, 6),
                      "reject_h0": reject}
    return out


# ==========================================================================================
# Block bootstrap: resample whole (symbol, trading_day) blocks, not individual bars/events.
# ==========================================================================================

def block_bootstrap_ci(events: list[dict], value_key: str, *, n_boot: int = 2000,
                        seed: int = 0) -> dict:
    blocks: dict = defaultdict(list)
    for e in events:
        blocks[(e["symbol"], e["trading_day"])].append(e[value_key])
    block_list = list(blocks.values())
    n_blocks = len(block_list)
    if n_blocks == 0:
        return {"n_blocks": 0, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sampled = [block_list[rng.randrange(n_blocks)] for _ in range(n_blocks)]
        flat = [v for blk in sampled for v in blk]
        if flat:
            means.append(st.mean(flat))
    if not means:
        return {"n_blocks": n_blocks, "n_boot": 0, "ci_low": None, "ci_high": None}
    means.sort()
    lo_idx = int(0.025 * len(means))
    hi_idx = min(len(means) - 1, int(0.975 * len(means)))
    return {"n_blocks": n_blocks, "n_boot": len(means),
            "ci_low": round(means[lo_idx], 5), "ci_high": round(means[hi_idx], 5)}


# ==========================================================================================
# Concentration ("carried by a single symbol/class") -- leave-one-out on the LARGEST group.
# ==========================================================================================

def leave_one_out_check(flat_events: list[dict], key_fn: Callable[[dict], str],
                         null_max: Optional[float], horizon: int = HEADLINE_HORIZON) -> Optional[dict]:
    groups: Counter = Counter(key_fn(e) for e in flat_events)
    if not groups:
        return None
    largest_key, largest_n = max(groups.items(), key=lambda kv: kv[1])
    remaining = [e[f"fwd_{horizon}"] for e in flat_events if key_fn(e) != largest_key]
    if not remaining:
        return {"largest_key": largest_key, "largest_n": largest_n, "share_pct": 100.0,
                "excl_mean_signed_headline_pct": None, "still_beats_null_MAX": False}
    excl_mean = st.mean(remaining)
    return {"largest_key": largest_key, "largest_n": largest_n,
            "share_pct": round(100.0 * largest_n / len(flat_events), 2),
            "excl_mean_signed_headline_pct": round(excl_mean, 5),
            "still_beats_null_MAX": (null_max is not None and excl_mean > null_max)}


# ==========================================================================================
# Orchestration
# ==========================================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", default=None,
                     help="comma-separated override of the prereg's test_symbols.set")
    ap.add_argument("--start", default=None, help="override window.requested_start (YYYY-MM-DD)")
    ap.add_argument("--end", default=None, help="override window.requested_end (YYYY-MM-DD)")
    ap.add_argument("--draws", type=int, default=200, help="null-draw count, prereg needs >=40")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--dry-run", action="store_true",
                     help="fetch ONE symbol over a short recent window to smoke-test wiring "
                          "before the full 12-month / 9-symbol pull. Still writes OUT, tagged "
                          "dry_run=true so it can never be mistaken for a real result.")
    ap.add_argument("--json", action="store_true",
                     help="also print the full report JSON to stdout")
    args = ap.parse_args(argv)

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    syms = ([s.strip().upper() for s in args.symbols.split(",")] if args.symbols
            else list(prereg["test_symbols"]["set"]))
    symbols_requested_n = len(syms)
    start = args.start or prereg["window"]["requested_start"]
    end = args.end or prereg["window"]["requested_end"]
    min_n = int(prereg["statistics"]["min_signals_required"])

    if args.dry_run:
        syms = syms[:1]
        end_d = date.fromisoformat(end)
        start = (end_d - timedelta(days=10)).isoformat()
        print(f"[DRY RUN] symbol={syms[0]} window={start}..{end}", file=sys.stderr)

    params = mc.load_params()
    creds = mc.resolve(params)

    nyse = mcal.get_calendar("NYSE")
    sched = nyse.schedule(start_date=start, end_date=end)
    trading_days = set(sched.index.strftime("%Y-%m-%d"))
    if not trading_days:
        raise HarnessError(f"NYSE calendar returned ZERO trading days for {start}..{end}")

    news_start_iso = f"{start}T00:00:00Z"
    news_end_iso = f"{end}T23:59:59Z"

    all_signals: dict[str, list] = {}
    pools: dict[str, list] = {}
    counts: dict[str, int] = {}
    mix: dict[str, float] = {}
    achieved: dict[str, dict] = {}
    fetch_stats_out: dict[str, dict] = {}
    failed_symbols: dict[str, str] = {}
    filter_disclosures: dict[str, dict] = {}
    skip_disclosures: dict[str, dict] = {}

    for sym in syms:
        print(f"  [{sym}] fetching...", file=sys.stderr)
        try:
            bar_stats = {"attempts": 0, "errors": 0}
            raw_bars, feed_used = fetch_all_bars_for_symbol(
                creds.key, creds.secret, sym, start, end, "5Min", bar_stats)
            raw_bars = filter_rth_bars(raw_bars)
            if len(raw_bars) < MIN_BARS_PER_SYMBOL:
                raise HarnessError(
                    f"[{sym}] only {len(raw_bars)} RTH bars returned (feed={feed_used}) -- "
                    f"refusing to build signals on this little data")
            bars_ts = [b["ts"] for b in raw_bars]

            news_stats = {"attempts": 0, "errors": 0}
            raw_news = fetch_all_news_for_symbol(
                creds.key, creds.secret, sym, news_start_iso, news_end_iso, news_stats)

            events, filt_counts = process_symbol_news(sym, raw_news, trading_days)
            signals, skip_counts = build_events_for_symbol(sym, events, raw_bars, bars_ts)
            pool = build_baseline_pool(raw_bars)

            combined_attempts = bar_stats["attempts"] + news_stats["attempts"]
            combined_errors = bar_stats["errors"] + news_stats["errors"]
            error_rate = (100.0 * combined_errors / combined_attempts) if combined_attempts else 0.0
            untrustworthy = error_rate > 1.0

            all_signals[sym] = signals
            pools[sym] = pool
            counts[sym] = len(signals)
            bulls = sum(1 for s in signals if s["direction"] == "UP")
            mix[sym] = (bulls / len(signals)) if signals else 0.5

            achieved[sym] = {
                "feed_used": feed_used,
                "bars_first_ts": raw_bars[0]["ts"].isoformat() if raw_bars else None,
                "bars_last_ts": raw_bars[-1]["ts"].isoformat() if raw_bars else None,
                "bars_count_rth": len(raw_bars),
                "news_raw_fetched": len(raw_news),
                "news_first_created_at": raw_news[0].get("created_at") if raw_news else None,
                "news_last_created_at": raw_news[-1].get("created_at") if raw_news else None,
            }
            fetch_stats_out[sym] = {
                "page_attempts": combined_attempts, "page_errors": combined_errors,
                "error_rate_pct": round(error_rate, 3), "untrustworthy": untrustworthy,
            }
            filter_disclosures[sym] = filt_counts
            skip_disclosures[sym] = skip_counts

            flag = " *** SYMBOL UNTRUSTWORTHY ***" if untrustworthy else ""
            print(f"  [{sym}] {len(signals)} signals / {len(raw_news)} raw news / "
                  f"{len(raw_bars)} RTH bars (feed={feed_used}) | fetch errors "
                  f"{combined_errors}/{combined_attempts} ({error_rate:.2f}%){flag}",
                  file=sys.stderr)
        except HarnessError as e:
            failed_symbols[sym] = str(e)
            print(f"  [{sym}] FAILED: {e}", file=sys.stderr)
            continue

    flat = [s for v in all_signals.values() for s in v]
    total = len(flat)
    if total == 0:
        raise HarnessError(
            "ZERO signals survived the full pipeline across ALL symbols -- refusing to report "
            "a result computed on nothing. failed_symbols=" + json.dumps(failed_symbols))

    per_h_signed, per_h_abs = {}, {}
    for h in HORIZONS:
        vals = [s[f"fwd_{h}"] for s in flat]
        abs_vals = [s[f"abs_{h}"] for s in flat]
        per_h_signed[h] = {
            "n": len(vals),
            "mean_signed_return_pct": round(st.mean(vals), 5),
            "median_signed_return_pct": round(st.median(vals), 5),
            "hit_rate_pct": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 2),
        }
        per_h_abs[h] = {
            "n": len(abs_vals),
            "mean_abs_move_pct": round(st.mean(abs_vals), 5),
            "median_abs_move_pct": round(st.median(abs_vals), 5),
        }

    null = random_null(pools, counts, mix, args.draws, args.seed)

    gate_signed, gate_abs, pvals_signed = {}, {}, {}
    for h in HORIZONS:
        real_s = per_h_signed[h]["mean_signed_return_pct"]
        real_a = per_h_abs[h]["mean_abs_move_pct"]
        nmax_s = null[h]["signed"]["null_MAX_of_means"]
        nmax_a = null[h]["abs"]["null_MAX_of_means"]
        gate_signed[h] = {"real": real_s, "null_MAX": nmax_s,
                           "beats_null_MAX": bool(real_s is not None and nmax_s is not None
                                                   and real_s > nmax_s)}
        gate_abs[h] = {"real": real_a, "null_MAX": nmax_a,
                        "beats_null_MAX": bool(real_a is not None and nmax_a is not None
                                                and real_a > nmax_a)}
        pvals_signed[h] = empirical_pvalue(real_s, null[h]["signed"]["draw_means"])

    holm_signed = holm_correction({h: p for h, p in pvals_signed.items() if p is not None})

    ci_signed = {h: block_bootstrap_ci(flat, f"fwd_{h}", seed=args.seed) for h in HORIZONS}
    ci_abs = {h: block_bootstrap_ci(flat, f"abs_{h}", seed=args.seed) for h in HORIZONS}

    # ---- per-symbol sign majority (decision-rule input -- uses EVERY symbol with >=1 signal,
    # not gated by the n>=50 descriptive-cell threshold; mirrors the sibling harness exactly) --
    per_symbol_gate = {}
    for sym, sigs in all_signals.items():
        if not sigs:
            continue
        v = [s[f"fwd_{HEADLINE_HORIZON}"] for s in sigs]
        per_symbol_gate[sym] = {"n": len(v), "mean_signed_return_pct": round(st.mean(v), 5)}

    pooled_headline_mean = per_h_signed[HEADLINE_HORIZON]["mean_signed_return_pct"]
    pooled_sign_positive = pooled_headline_mean is not None and pooled_headline_mean > 0
    matching = sum(1 for r in per_symbol_gate.values()
                   if (r["mean_signed_return_pct"] > 0) == pooled_sign_positive)
    half_ok = matching >= max(1, (len(per_symbol_gate) + 1) // 2)

    # ---- descriptive splits, n<min_n labelled INSUFFICIENT_EVIDENCE, per prereg ----
    per_symbol_display = {}
    for sym, sigs in all_signals.items():
        n = len(sigs)
        if n < min_n:
            per_symbol_display[sym] = {"n": n, "status": "INSUFFICIENT_EVIDENCE"}
            continue
        v = [s[f"fwd_{HEADLINE_HORIZON}"] for s in sigs]
        per_symbol_display[sym] = {
            "n": n, "mean_signed_return_pct": round(st.mean(v), 5),
            "hit_rate_pct": round(100.0 * sum(1 for x in v if x > 0) / n, 2),
        }

    per_class_vals: dict = defaultdict(list)
    for s in flat:
        per_class_vals[s["category"]].append(s[f"fwd_{HEADLINE_HORIZON}"])
    per_class_display = {}
    for cat, vals in per_class_vals.items():
        n = len(vals)
        if n < min_n:
            per_class_display[cat] = {"n": n, "status": "INSUFFICIENT_EVIDENCE"}
            continue
        per_class_display[cat] = {
            "n": n, "mean_signed_return_pct": round(st.mean(vals), 5),
            "hit_rate_pct": round(100.0 * sum(1 for v in vals if v > 0) / n, 2),
        }

    # ---- concentration ("carried by a single symbol/class") ----
    loo_symbol = leave_one_out_check(flat, lambda e: e["symbol"], gate_signed[HEADLINE_HORIZON]["null_MAX"])
    loo_class = leave_one_out_check(flat, lambda e: e["category"], gate_signed[HEADLINE_HORIZON]["null_MAX"])
    concentration_kill = bool(
        gate_signed[HEADLINE_HORIZON]["beats_null_MAX"] and (
            (loo_symbol is not None and loo_symbol.get("still_beats_null_MAX") is False) or
            (loo_class is not None and loo_class.get("still_beats_null_MAX") is False)
        )
    )

    # ---- volatility-not-direction finding (never a pass, per prereg) ----
    volatility_not_direction = bool(
        (not gate_signed[HEADLINE_HORIZON]["beats_null_MAX"])
        and gate_abs[HEADLINE_HORIZON]["beats_null_MAX"]
    )

    # ---- verdict, mechanically from the frozen decision_rule ----
    enough = total >= min_n
    core_pass = gate_signed[HEADLINE_HORIZON]["beats_null_MAX"] and half_ok
    if not enough:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif not core_pass:
        verdict = "FAIL_stop_the_line"
    elif concentration_kill:
        verdict = "CONCENTRATION_KILL"
    else:
        verdict = "PASS_to_shadow"

    report = {
        "stage": "A_catalyst_direction",
        "prereg": PREREG.name,
        "dry_run": bool(args.dry_run),
        "run_args": {"symbols": syms, "start": start, "end": end, "draws": args.draws,
                     "seed": args.seed},
        "verdict": verdict,
        "_verdict_rule": prereg["decision_rule"],
        "signals_total": total, "min_required": min_n,
        "symbols_requested": symbols_requested_n,
        "symbols_fetched_ok": len(all_signals), "symbols_failed": failed_symbols,
        "headline_horizon_bars": HEADLINE_HORIZON,
        "per_horizon_signed": {str(k): v for k, v in per_h_signed.items()},
        "per_horizon_abs": {str(k): v for k, v in per_h_abs.items()},
        "random_entry_null": {str(k): v for k, v in null.items()},
        "null_gate_signed": {str(k): v for k, v in gate_signed.items()},
        "null_gate_abs": {str(k): v for k, v in gate_abs.items()},
        "holm_correction_signed_family": {str(k): v for k, v in holm_signed.items()},
        "block_bootstrap_ci_signed_95pct": {str(k): v for k, v in ci_signed.items()},
        "block_bootstrap_ci_abs_95pct": {str(k): v for k, v in ci_abs.items()},
        "per_symbol_headline": per_symbol_display,
        "per_news_class_headline": per_class_display,
        "_gate_internal_per_symbol_sign": per_symbol_gate,
        "symbols_with_matching_sign": matching, "symbols_in_gate": len(per_symbol_gate),
        "concentration_check": {
            "leave_one_out_symbol": loo_symbol, "leave_one_out_class": loo_class,
            "concentration_kill": concentration_kill,
        },
        "volatility_not_direction": volatility_not_direction,
        "achieved_window": achieved,
        "fetch_stats": fetch_stats_out,
        "filter_pipeline": filter_disclosures,
        "signal_construction_skips": skip_disclosures,
        "_disclosures": [
            "Stage A measures the SIGNAL on the UNDERLYING -- no option pricing, no spread, "
            "no theta. A pass here is necessary, not sufficient.",
            "No look-ahead: direction uses only bars[t0..t0+2] via a physically-sliced "
            "argument; forward returns start at t0+2 and never feed the direction decision.",
            "created_at is Benzinga's publication stamp, not the moment information became "
            "public; the true lag is unmeasured and biases AGAINST finding an effect.",
            "Feed actually used (sip vs iex) is recorded per symbol in achieved_window.",
            "Per-symbol and per-news-class results are DESCRIPTIVE and excluded from the "
            "Holm-corrected family (which covers the 3 horizons of the signed-return family "
            "only).",
            "Cells with n < min_required are INSUFFICIENT_EVIDENCE, not a weak positive.",
        ],
        "_harness_notes": [
            "Judgment call: news filtering uses a purpose-built pipeline (dedup -> "
            "specificity -> RTH), not scanners.parse_news() verbatim -- parse_news() filters "
            "by lookback_hours from wall-clock now, which does not fit a 12-month historical "
            "pull; classify_headline() IS reused for the news-class split.",
            "Judgment call: bars are fetched per-symbol (not batched) so feed try/fallback and "
            "'which feed each symbol actually used' can be recorded truthfully per symbol "
            "rather than assumed uniform across a batch call.",
            "Judgment call: bars are fetched for exactly [start, end] as given -- not padded "
            "past `end` -- so a signal needing bars beyond the frozen window is honestly "
            "skipped (insufficient_forward_bars) rather than silently reaching past the "
            "prereg's window.",
            "Correctness fix beyond the prereg's literal text: RTH-only bars make different "
            "trading days adjacent in ARRAY INDEX (not wall-clock time). Both the direction "
            "window and the forward-return window are checked for same-day-ness and skipped "
            "(entry_crosses_session_boundary / forward_window_crosses_session_boundary) if "
            "they would otherwise splice an overnight gap into a 10/30/60-minute reaction.",
            "Judgment call: per-symbol/per-page fetch retries (up to 3, with backoff) are "
            "counted into a page_attempts/page_errors tally; error_rate_pct > 1% marks that "
            "symbol untrustworthy IN THE OUTPUT (printed to stderr too) rather than silently "
            "excluding it from the pooled statistics -- so a human reviewer can decide.",
            "Judgment call: CONCENTRATION_KILL is computed via leave-one-out on the SINGLE "
            "LARGEST symbol and the SINGLE LARGEST news-class at the headline horizon -- if "
            "removing either one drops the pooled result below the null MAX, the pass is "
            "concentration-carried and downgraded from PASS_to_shadow to CONCENTRATION_KILL.",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n=== CATALYST-DIRECTION STAGE A VERDICT: {verdict} ===", file=sys.stderr)
    print(f"  signals {total} (need {min_n}) | symbols_ok {len(all_signals)}/{len(syms)} | "
          f"sign-matching {matching}/{len(per_symbol_gate)}", file=sys.stderr)
    for h in HORIZONS:
        gs, gA = gate_signed[h], gate_abs[h]
        ps = per_h_signed[h]
        print(f"  +{h:>2} bars: signed {ps['mean_signed_return_pct']}% hit "
              f"{ps['hit_rate_pct']}% | nullMAX_signed {gs['null_MAX']} -> "
              f"{'BEATS' if gs['beats_null_MAX'] else 'FAILS'} | "
              f"abs {per_h_abs[h]['mean_abs_move_pct']}% nullMAX_abs {gA['null_MAX']} -> "
              f"{'BEATS' if gA['beats_null_MAX'] else 'FAILS'}", file=sys.stderr)
    print(f"  concentration_kill={concentration_kill} volatility_not_direction="
          f"{volatility_not_direction}", file=sys.stderr)
    if failed_symbols:
        print(f"  FAILED symbols: {list(failed_symbols)}", file=sys.stderr)
    untrust = [s for s, v in fetch_stats_out.items() if v["untrustworthy"]]
    if untrust:
        print(f"  *** UNTRUSTWORTHY symbols (fetch error rate > 1%): {untrust} ***",
              file=sys.stderr)
    print(f"\nwrote {OUT}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))

    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
