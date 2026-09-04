"""scanners.py -- free Alpaca-data candidate scanners for the multi-symbol options lane.

J's ask (2026-08-19): "what kind of free signals can we get from Alpaca, like, scanner wise
... brainstorm, think through this, and then get it built." This module is the brainstorm,
built: five scanners over Alpaca's free market-data REST surfaces, each returning a
structured, ranked, PROVENANCE-CARRYING candidate list.

>>> SCOPE CONSTRAINT -- READ BEFORE WIRING THIS ANYWHERE <<<
These scanners SELECT candidates for a human-or-later-mechanism to look at. They do NOT
decide trades, and they must NEVER be wired as a hard entry gate (AND'd into the live
decision path). This shop has a documented failure for exactly that mistake --
LESSONS-LEARNED L199: independently-reasonable filters stacked together produced a fleet-wide
cascade that left one arm with 700 signals and 0 trades, because each gate looked fine in
isolation but their intersection was nearly empty. A scanner's job here stops at "worth a
look" -- it feeds a WATCHLIST, never a trigger. Downstream code that treats `enabled: true`
in a scanner's params.json block as "therefore required for entry" is repeating L199.

>>> NO PREDICTIVE CLAIM <<<
A scanner that finds a big mover is only useful if the move CONTINUES, and whether gap-ups /
volume spikes / news catalysts continue or fade is an OPEN EMPIRICAL QUESTION being tested
separately (see the paired shadow-clock work in analysis/). Nothing in this module claims,
implies, or should be read as "this candidate will keep moving." Every function here emits
MEASURED FACTS about right now (a percent change, a volume ratio, a headline) and nothing
about the future. Do not add a "predicted continuation" field to this module without that
being its own validated, disclosed piece of work.

WHAT'S HERE (5 scanners, all reading automation/state/multi/params.json's `scanners` and
`universe` blocks -- this module never modifies that file):

  1. movers          -- GET /v1beta1/screener/stocks/movers. Abs %-change above a threshold.
  2. most_actives     -- GET /v1beta1/screener/stocks/most-actives, queried BOTH by=volume and
                          by=trade_count (two distinct rankings of "what's trading a lot").
  3. gap              -- COMPUTED from GET /v2/stocks/snapshots (today's bar + yesterday's
                          close) and GET /v2/stocks/bars (20-day volume history). Two known
                          house bugs this module works around explicitly: (a) the bars
                          endpoint returns ZERO bars with no explicit `start` -- every bars
                          call here passes one; (b) it paginates via `next_page_token` well
                          under a large `limit` -- every bars call here drains the token loop.
                          RELATIVE VOLUME (today's volume / trailing-20-day average) is
                          treated as the highest-signal field of this whole module -- MRNA ran
                          at ~28x normal volume on 2026-08-19, the day this lane was built.
  4. news             -- GET /v1beta1/news, symbol-tagged, with a crude CLASS tag (trial/FDA,
                          M&A, earnings, guidance, analyst, other) from headline keywords.
                          `classify_headline()` is a KEYWORD HEURISTIC, NOT NLP and not an
                          LLM call -- it is cheap substring matching and WILL mislabel
                          headlines that use unlisted phrasing or bury their real subject.
                          Anything matching no keyword list lands in "other" rather than being
                          force-fit into the nearest category (see the ambiguous-headline test
                          in backtest/tests/test_multi_scanners.py).
  5. composite        -- merges all four above per symbol. Every individual scanner's signal
                          stays VISIBLE in the merged row (movers / most_actives / gap / news
                          sub-dicts) alongside a plain `signal_count` tally of how many
                          DISTINCT scanner types fired. There is deliberately no single
                          opaque blended score -- collapsing to one number is exactly what
                          would hide which scanner actually fired, and the whole point of a
                          watchlist candidate is that a human can see why it's on the list.

FAIL LOUD: every `run_*` function returns a `ScannerResult` whose `ok` flag distinguishes a
scanner that ERRORED (network/HTTP failure -- `ok=False`, `error` set, `candidates=()`) from
one that ran fine and found NOTHING (`ok=True`, `error=None`, `candidates=()`). `raw_count`
further distinguishes "the API returned nothing" (raw_count=0) from "the API returned items
but none passed the configured threshold" (raw_count>0, candidates=()). No scanner here ever
silently returns an empty list and calls it success without a `raw_count` to explain why.

$0 -- every endpoint here is the free/indicative Alpaca market-data tier already verified
working this session (movers, most-actives, news, bars, snapshots). No new vendor, no paid
feed. No OPRA agreement on this account: numbers here are from the indicative feed.

Credentials: resolved via multi.lib.creds (this lane's existing, by-reference credential
module) by the CALLER (setup/scripts/multi_scanner_run.py) -- this module takes a bare
key/secret and never reads .mcp.json or any secrets file itself, and never prints one. ET
timestamps use zoneinfo.ZoneInfo("America/New_York") -- this box runs Mountain time, so a
fixed UTC offset would be wrong for at least part of the year.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

ET_TZ = ZoneInfo("America/New_York")
DATA_BASE = "https://data.alpaca.markets"


def et_now() -> datetime:
    """Timezone-aware Eastern Time, via zoneinfo -- never a hardcoded -4/-5 offset."""
    return datetime.now(ET_TZ)


# ==========================================================================================
# Errors
# ==========================================================================================

class ScannerFetchError(RuntimeError):
    """A live HTTP call to an Alpaca data endpoint failed. Every `run_*` wrapper catches this
    and records it as ScannerResult(ok=False, error=str(e)) -- it must never be swallowed into
    a silent empty result."""


# ==========================================================================================
# Result envelope -- makes "errored" distinguishable from "ran fine, found nothing"
# ==========================================================================================

@dataclass(frozen=True)
class ScannerResult:
    name: str
    ok: bool                 # False = errored (network/HTTP). True = ran, even if 0 candidates.
    candidates: tuple        # () is valid when ok=True -- means nothing matched.
    raw_count: int           # items returned by the API before any threshold filter.
    error: Optional[str]     # non-None reason when ok=False, or a partial-failure note.
    fetched_at_et: str


def scanner_result_to_dict(result: ScannerResult) -> dict:
    """JSON-safe view of a ScannerResult -- dataclass candidates become plain dicts; composite
    rows (already plain dicts) pass through unchanged."""
    def _cand(c):
        return asdict(c) if is_dataclass(c) else c
    return {
        "name": result.name,
        "ok": result.ok,
        "raw_count": result.raw_count,
        "candidate_count": len(result.candidates),
        "error": result.error,
        "fetched_at_et": result.fetched_at_et,
        "candidates": [_cand(c) for c in result.candidates],
    }


# ==========================================================================================
# Candidate shapes
# ==========================================================================================

@dataclass(frozen=True)
class MoverCandidate:
    symbol: str
    direction: str              # "gainer" | "loser"
    percent_change: float
    price: Optional[float]
    source: str = "alpaca_screener_movers"


@dataclass(frozen=True)
class MostActiveCandidate:
    symbol: str
    metric: str                 # "volume" | "trades" -- which ranking this row came from
    rank: int                   # 1-based position within ITS metric's ranking
    volume: Optional[float]
    trade_count: Optional[float]
    source: str = "alpaca_screener_most_actives"


@dataclass(frozen=True)
class NewsItem:
    id: Optional[int]
    headline: str
    created_at: str             # raw ISO string from the API, UTC
    source: str                 # publisher (e.g. "Benzinga")
    symbols: tuple               # symbols this article is tagged against
    category: str                # classify_headline() output -- heuristic, see module docstring
    url: Optional[str] = None
    age_hours: Optional[float] = None


@dataclass(frozen=True)
class GapCandidate:
    symbol: str
    prior_close: float
    current_price: float
    gap_pct: float
    today_volume: float
    avg_20d_volume: Optional[float]   # None if <window trading days of history
    relative_volume: Optional[float]  # None (never a fabricated number) if avg is unknown
    as_of_et: str
    source: str = "alpaca_snapshots+bars"


# ==========================================================================================
# HTTP layer (network -- not covered by unit tests; tests feed raw dicts straight into the
# parse/compute layer below, mirroring setup/scripts/sector_heat_scanner.py's split)
# ==========================================================================================

def _http_get_json(url: str, key: str, secret: str, timeout: int = 15) -> dict:
    """Bare urllib GET with Alpaca auth headers. Never puts the key/secret in the URL or in
    any exception message -- only the path (no query string) is echoed back on failure."""
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "accept": "application/json"})
    path_only = url.split("?", 1)[0]
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 -- fixed https host
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 -- best-effort diagnostic only
            pass
        raise ScannerFetchError(f"HTTP {e.code} from {path_only}: {body}") from e
    except urllib.error.URLError as e:
        raise ScannerFetchError(f"network error hitting {path_only}: {e.reason}") from e
    except (TimeoutError, OSError, json.JSONDecodeError) as e:
        raise ScannerFetchError(f"error hitting {path_only}: {type(e).__name__}: {e}") from e


def _chunk_symbols(symbols: Sequence[str], chunk_size: int = 100) -> list[list[str]]:
    syms = list(symbols)
    return [syms[i:i + chunk_size] for i in range(0, len(syms), chunk_size)] or [[]]


def fetch_movers_raw(key: str, secret: str, top: int = 25) -> dict:
    url = f"{DATA_BASE}/v1beta1/screener/stocks/movers?{urllib.parse.urlencode({'top': top})}"
    return _http_get_json(url, key, secret)


def fetch_most_actives_raw(key: str, secret: str, by: str = "volume", top: int = 25) -> dict:
    q = urllib.parse.urlencode({"by": by, "top": top})
    url = f"{DATA_BASE}/v1beta1/screener/stocks/most-actives?{q}"
    return _http_get_json(url, key, secret)


def fetch_news_raw(key: str, secret: str, start: Optional[str] = None,
                    end: Optional[str] = None, limit: int = 50, sort: str = "desc",
                    symbols: Optional[str] = None, page_token: Optional[str] = None) -> dict:
    """`symbols` and `page_token` are optional additions (2026-09-03, for
    backtest/tools/catalyst_direction_null_harness.py) -- both default to None, so every
    existing caller (run_news, below) is unaffected. `symbols` passes through verbatim as
    Alpaca's comma-separated `symbols` query param (news for ANY of the listed symbols, not
    ANDed); `page_token` continues a prior response's `next_page_token` for a caller that needs
    to drain a whole multi-month history rather than one page."""
    params = {"limit": limit, "sort": sort}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    if symbols:
        params["symbols"] = symbols
    if page_token:
        params["page_token"] = page_token
    url = f"{DATA_BASE}/v1beta1/news?{urllib.parse.urlencode(params)}"
    return _http_get_json(url, key, secret)


def fetch_snapshots_raw(key: str, secret: str, symbols: Sequence[str], feed: str = "iex") -> dict:
    merged: dict = {}
    for chunk in _chunk_symbols(symbols):
        if not chunk:
            continue
        q = urllib.parse.urlencode({"symbols": ",".join(chunk), "feed": feed})
        data = _http_get_json(f"{DATA_BASE}/v2/stocks/snapshots?{q}", key, secret)
        merged.update(data)
    return merged


def fetch_daily_bars_raw(key: str, secret: str, symbols: Sequence[str], start: str,
                          end: Optional[str] = None, limit: int = 1000,
                          feed: str = "iex") -> dict[str, list[dict]]:
    """Multi-symbol daily bars. `start` is REQUIRED -- the endpoint silently returns ZERO
    bars for today-only if it's omitted (house bug #1). Drains `next_page_token` per chunk
    until exhausted -- it paginates well below `limit` on multi-symbol requests (house bug
    #2). Both bugs were found and fixed elsewhere this session; this is the fix applied here.
    """
    merged: dict[str, list[dict]] = {sym: [] for sym in symbols}
    for chunk in _chunk_symbols(symbols):
        if not chunk:
            continue
        page_token: Optional[str] = None
        while True:
            params = {"symbols": ",".join(chunk), "timeframe": "1Day", "start": start,
                       "limit": str(limit), "feed": feed, "sort": "asc"}
            if end:
                params["end"] = end
            if page_token:
                params["page_token"] = page_token
            url = f"{DATA_BASE}/v2/stocks/bars?{urllib.parse.urlencode(params)}"
            data = _http_get_json(url, key, secret)
            for sym, bars in (data.get("bars") or {}).items():
                merged.setdefault(sym, []).extend(bars)
            page_token = data.get("next_page_token")
            if not page_token:
                break
    return merged


# ==========================================================================================
# Pure parse / compute layer -- no network, deterministic, unit-testable with fixture dicts
# ==========================================================================================

def _safe_float(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---- movers ------------------------------------------------------------------------------

def parse_movers(raw: dict, min_abs_pct: float) -> tuple[list[MoverCandidate], int]:
    """Parse {gainers:[...], losers:[...]} into MoverCandidates filtered to |%change| >=
    min_abs_pct and sorted by |%change| descending. Returns (candidates, raw_count) where
    raw_count is the total items seen BEFORE filtering, so a caller can tell 'nothing moved
    enough' (raw_count>0, candidates=[]) apart from 'API gave us nothing' (raw_count=0)."""
    gainers = raw.get("gainers") or []
    losers = raw.get("losers") or []
    raw_count = len(gainers) + len(losers)
    out: list[MoverCandidate] = []
    for item in gainers:
        pct = _safe_float(item.get("percent_change"))
        if pct is None:
            continue
        out.append(MoverCandidate(symbol=item.get("symbol", ""), direction="gainer",
                                   percent_change=pct, price=_safe_float(item.get("price"))))
    for item in losers:
        pct = _safe_float(item.get("percent_change"))
        if pct is None:
            continue
        out.append(MoverCandidate(symbol=item.get("symbol", ""), direction="loser",
                                   percent_change=pct, price=_safe_float(item.get("price"))))
    filtered = [c for c in out if abs(c.percent_change) >= min_abs_pct]
    filtered.sort(key=lambda c: abs(c.percent_change), reverse=True)
    return filtered, raw_count


# ---- most_actives ------------------------------------------------------------------------

def parse_most_actives(raw: dict, metric: str) -> tuple[list[MostActiveCandidate], int]:
    """Parse {most_actives:[{symbol,volume,trade_count}]} preserving the API's own ranking
    (Alpaca already sorts by the requested `by` param) into 1-based `rank` per row."""
    items = raw.get("most_actives") or []
    out: list[MostActiveCandidate] = []
    for i, item in enumerate(items, start=1):
        out.append(MostActiveCandidate(
            symbol=item.get("symbol", ""), metric=metric, rank=i,
            volume=_safe_float(item.get("volume")),
            trade_count=_safe_float(item.get("trade_count")),
        ))
    return out, len(items)


# ---- news classification -------------------------------------------------------------------

# Priority-ordered: first keyword match wins. Deliberately conservative -- generic words like
# "partnership" or "announces" are NOT included anywhere, so a routine corporate-update
# headline correctly falls through to "other" instead of being force-fit into a category.
NEWS_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trial_fda", ("fda", "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii",
                   "clinical trial", "clinical study", "pdufa", "biologics license",
                   "drug approval", "fda approval", "fda clearance")),
    ("m_and_a", ("acquire", "acquisition", "acquiring", "to be acquired", "merger",
                 "merges with", "buyout", "takeover", "tender offer",
                 "definitive agreement to")),
    ("earnings", ("earnings", "eps of", "quarterly results", "q1 results", "q2 results",
                  "q3 results", "q4 results", "beats estimates", "misses estimates",
                  "reports revenue", "fiscal year results")),
    ("guidance", ("guidance", "outlook", "forecast", "raises full-year", "cuts full-year",
                  "reaffirms guidance", "narrows guidance")),
    ("analyst", ("upgrade", "downgrade", "price target", "initiates coverage",
                 "overweight rating", "underweight rating", "outperform rating",
                 "buy rating", "sell rating", "neutral rating")),
)


def classify_headline(headline: str) -> str:
    """Keyword HEURISTIC classer -- NOT NLP, NOT an LLM call, just lower-cased substring
    matching against NEWS_CATEGORY_KEYWORDS in priority order (first hit wins). This WILL
    mislabel headlines that use unlisted phrasing or bury their real subject (e.g. "Rival
    Comments on Competitor's FDA Setback" would false-hit trial_fda even though the named
    company isn't the trial's subject) -- it is a cheap triage signal for a human-read
    watchlist, never a claim of semantic understanding. Anything matching no keyword list
    returns 'other' rather than being force-fit into the nearest category."""
    h = (headline or "").lower()
    for category, keywords in NEWS_CATEGORY_KEYWORDS:
        if any(kw in h for kw in keywords):
            return category
    return "other"


def _parse_iso_utc(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def parse_news(raw: dict, now_utc: datetime, lookback_hours: float) -> tuple[list[NewsItem], int]:
    """Parse {news:[...]} into NewsItems classed via classify_headline(), dropping anything
    older than lookback_hours (age computed against the caller-supplied now_utc so this stays
    deterministic/testable -- never wall-clock inside the parse layer). raw_count is the total
    items the API returned before the age filter."""
    items = raw.get("news") or []
    kept: list[NewsItem] = []
    for it in items:
        headline = it.get("headline") or ""
        created_raw = it.get("created_at") or ""
        created_dt = _parse_iso_utc(created_raw)
        age_hours = ((now_utc - created_dt).total_seconds() / 3600.0) if created_dt else None
        if age_hours is not None and age_hours > lookback_hours:
            continue
        kept.append(NewsItem(
            id=it.get("id"), headline=headline, created_at=created_raw,
            source=it.get("source") or "", symbols=tuple(it.get("symbols") or ()),
            category=classify_headline(headline), url=it.get("url"), age_hours=age_hours,
        ))
    return kept, len(items)


# ---- gap + relative volume -----------------------------------------------------------------

def avg_daily_volume(volumes: Sequence[float], window: int = 20) -> Optional[float]:
    """Trailing average over the LAST `window` entries of `volumes` (caller must have already
    excluded any unclosed/today bar -- see _drop_today_bar). None (never 0.0) if there isn't
    enough history yet."""
    vals = [v for v in volumes if v is not None]
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / window


def relative_volume(today_volume: Optional[float], avg_volume: Optional[float]) -> Optional[float]:
    """today_volume / avg_volume. None if either input is missing or avg_volume<=0 -- never a
    divide-by-zero, never a fabricated ratio."""
    if today_volume is None or avg_volume is None or avg_volume <= 0:
        return None
    return today_volume / avg_volume


def gap_pct(prior_close: Optional[float], current_price: Optional[float]) -> Optional[float]:
    """(current - prior_close) / prior_close * 100. None if either input is missing or
    prior_close is 0."""
    if prior_close is None or current_price is None or prior_close == 0:
        return None
    return (current_price - prior_close) / prior_close * 100.0


def _drop_today_bar(bars: Sequence[dict], today_date_str: str) -> list[dict]:
    """No-look-ahead guard for the 20-day volume average: a daily bar dated today may still
    be an in-progress/unclosed bar (Alpaca's 'sort=asc' multi-symbol bars can include a
    partial current-session bar). Drop any bar whose 't' starts with today's date so the
    trailing average is built from CLOSED sessions only."""
    return [b for b in bars if not (b.get("t") or "").startswith(today_date_str)]


def parse_snapshot_row(raw_snapshot_for_symbol: dict) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """(prior_close, current_price, today_volume) from one symbol's /v2/stocks/snapshots
    payload. Missing fields come back None -- never fabricated."""
    snap = raw_snapshot_for_symbol or {}
    prev = snap.get("prevDailyBar") or {}
    today = snap.get("dailyBar") or {}
    latest_trade = snap.get("latestTrade") or {}
    prior_close = _safe_float(prev.get("c"))
    current_price = _safe_float(latest_trade.get("p"))
    if current_price is None:
        current_price = _safe_float(today.get("c"))
    today_volume = _safe_float(today.get("v"))
    return prior_close, current_price, today_volume


def compute_gap_candidates(snapshots_raw: dict, bars_by_symbol: dict[str, list[dict]],
                            as_of_et: str, window: int = 20) -> list[GapCandidate]:
    """Pure compute across a whole symbol set. `bars_by_symbol` values must already have
    today's (possibly-unclosed) bar excluded by the caller (see _drop_today_bar) -- this
    function does not re-check dates, it just averages what it's given. Symbols missing a
    prior close, current price, or today's volume are SKIPPED (not fabricated with a zero)."""
    out: list[GapCandidate] = []
    for symbol, snap in snapshots_raw.items():
        prior_close, current_price, today_volume = parse_snapshot_row(snap)
        if prior_close is None or current_price is None or today_volume is None:
            continue
        g_pct = gap_pct(prior_close, current_price)
        if g_pct is None:
            continue
        bars = bars_by_symbol.get(symbol) or []
        volumes = [_safe_float(b.get("v")) for b in bars]
        avg_vol = avg_daily_volume(volumes, window=window)
        rel_vol = relative_volume(today_volume, avg_vol)
        out.append(GapCandidate(
            symbol=symbol, prior_close=prior_close, current_price=current_price,
            gap_pct=g_pct, today_volume=today_volume, avg_20d_volume=avg_vol,
            relative_volume=rel_vol, as_of_et=as_of_et,
        ))
    return out


def select_gap_candidates(candidates: Sequence[GapCandidate], min_gap_pct: float,
                           min_rel_volume: float) -> list[GapCandidate]:
    """Keep a candidate if EITHER its |gap_pct| clears min_gap_pct OR its relative_volume
    clears min_rel_volume (deliberately OR, not AND -- this is a watchlist filter, not a
    stacked trade gate; see module docstring re: L199). Sorted by relative_volume descending
    (the highest-signal field here), unknown relative_volume sorts last, ties broken by
    |gap_pct| descending."""
    kept = [c for c in candidates
            if abs(c.gap_pct) >= min_gap_pct
            or (c.relative_volume is not None and c.relative_volume >= min_rel_volume)]
    kept.sort(key=lambda c: (c.relative_volume is None, -(c.relative_volume or 0.0), -abs(c.gap_pct)))
    return kept


def run_gap(key: str, secret: str, symbols: Sequence[str], min_gap_pct: float,
            min_rel_volume: float, window: int = 20,
            now_et: Optional[datetime] = None) -> ScannerResult:
    now_et = now_et or et_now()
    today_str = now_et.strftime("%Y-%m-%d")
    if not symbols:
        return ScannerResult("gap", False, tuple(), 0, "empty_symbol_universe", now_et.isoformat())
    try:
        snapshots_raw = fetch_snapshots_raw(key, secret, symbols)
    except ScannerFetchError as e:
        return ScannerResult("gap", False, tuple(), 0, f"snapshots fetch failed: {e}", now_et.isoformat())
    lookback_start = (now_et - timedelta(days=max(45, window * 3))).strftime("%Y-%m-%d")
    try:
        bars_raw = fetch_daily_bars_raw(key, secret, symbols, start=lookback_start)
    except ScannerFetchError as e:
        return ScannerResult("gap", False, tuple(), 0, f"bars fetch failed: {e}", now_et.isoformat())
    bars_by_symbol = {sym: _drop_today_bar(bars, today_str) for sym, bars in bars_raw.items()}
    all_candidates = compute_gap_candidates(snapshots_raw, bars_by_symbol, now_et.isoformat(), window)
    selected = select_gap_candidates(all_candidates, min_gap_pct, min_rel_volume)
    return ScannerResult("gap", True, tuple(selected), len(all_candidates), None, now_et.isoformat())


# ==========================================================================================
# run_* wrappers -- fetch (network) + parse (pure) + wrap in ScannerResult
# ==========================================================================================

def run_movers(key: str, secret: str, min_abs_pct: float, top: int = 25,
                now_et: Optional[datetime] = None) -> ScannerResult:
    now_et = now_et or et_now()
    try:
        raw = fetch_movers_raw(key, secret, top=top)
    except ScannerFetchError as e:
        return ScannerResult("movers", False, tuple(), 0, str(e), now_et.isoformat())
    candidates, raw_count = parse_movers(raw, min_abs_pct)
    return ScannerResult("movers", True, tuple(candidates), raw_count, None, now_et.isoformat())


def run_most_actives(key: str, secret: str, top: int = 25,
                      now_et: Optional[datetime] = None) -> ScannerResult:
    now_et = now_et or et_now()
    all_candidates: list[MostActiveCandidate] = []
    raw_count = 0
    errors: list[str] = []
    for metric, by_param in (("volume", "volume"), ("trades", "trades")):
        try:
            raw = fetch_most_actives_raw(key, secret, by=by_param, top=top)
        except ScannerFetchError as e:
            errors.append(f"{metric}: {e}")
            continue
        cands, n = parse_most_actives(raw, metric)
        all_candidates.extend(cands)
        raw_count += n
    if not all_candidates and errors:
        return ScannerResult("most_actives", False, tuple(), 0, "; ".join(errors), now_et.isoformat())
    return ScannerResult("most_actives", True, tuple(all_candidates), raw_count,
                          ("; ".join(errors) if errors else None), now_et.isoformat())


def run_news(key: str, secret: str, lookback_hours: float, limit: int = 50,
             now_et: Optional[datetime] = None) -> ScannerResult:
    now_et = now_et or et_now()
    now_utc = now_et.astimezone(timezone.utc)
    start_utc = now_utc - timedelta(hours=lookback_hours)
    try:
        raw = fetch_news_raw(key, secret,
                              start=start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              end=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=limit)
    except ScannerFetchError as e:
        return ScannerResult("news", False, tuple(), 0, str(e), now_et.isoformat())
    items, raw_count = parse_news(raw, now_utc, lookback_hours)
    return ScannerResult("news", True, tuple(items), raw_count, None, now_et.isoformat())


# ==========================================================================================
# Composite merge -- signals stay visible, no opaque score
# ==========================================================================================

def merge_composite(movers: Sequence[MoverCandidate], most_actives: Sequence[MostActiveCandidate],
                     gaps: Sequence[GapCandidate], news: Sequence[NewsItem]) -> list[dict]:
    """Merge per-symbol. Every scanner's raw signal stays VISIBLE and separate under its own
    key -- 'signal_count' is a transparent tally of how many DISTINCT scanner TYPES fired for
    a symbol, never a weighted/blended figure that would hide which one mattered (see module
    docstring)."""
    by_symbol: dict[str, dict] = {}

    def ensure(sym: str) -> dict:
        return by_symbol.setdefault(sym, {
            "symbol": sym, "movers": None, "most_actives": [], "gap": None, "news": [],
        })

    for m in movers:
        ensure(m.symbol)["movers"] = asdict(m)
    for a in most_actives:
        ensure(a.symbol)["most_actives"].append(asdict(a))
    for g in gaps:
        ensure(g.symbol)["gap"] = asdict(g)
    for n in news:
        for sym in n.symbols:
            ensure(sym)["news"].append(asdict(n))

    out = []
    for sym, row in by_symbol.items():
        fired = sum([
            row["movers"] is not None,
            bool(row["most_actives"]),
            row["gap"] is not None,
            bool(row["news"]),
        ])
        row["signal_count"] = fired
        out.append(row)
    out.sort(key=lambda r: (-r["signal_count"], r["symbol"]))
    return out


def run_composite(movers_result: ScannerResult, most_actives_result: ScannerResult,
                   gap_result: ScannerResult, news_result: ScannerResult,
                   now_et: Optional[datetime] = None) -> ScannerResult:
    now_et = now_et or et_now()
    upstream = (movers_result, most_actives_result, gap_result, news_result)
    if not any(r.ok for r in upstream):
        errs = "; ".join(f"{r.name}:{r.error}" for r in upstream if r.error)
        return ScannerResult("composite", False, tuple(), 0,
                              f"all upstream scanners failed: {errs}", now_et.isoformat())
    movers = movers_result.candidates if movers_result.ok else ()
    most_actives = most_actives_result.candidates if most_actives_result.ok else ()
    gaps = gap_result.candidates if gap_result.ok else ()
    news = news_result.candidates if news_result.ok else ()
    rows = merge_composite(movers, most_actives, gaps, news)
    return ScannerResult("composite", True, tuple(rows), len(rows), None, now_et.isoformat())


# ==========================================================================================
# Universe helper + top-level orchestration
# ==========================================================================================

def flatten_universe(universe_block: dict) -> list[str]:
    """Flatten params.json's universe block (category -> [symbols], plus '_doc'-style prose
    keys) into one deduped symbol list, preserving first-seen order. Keys starting with '_'
    or non-list values are skipped -- they're documentation, not categories."""
    seen: set = set()
    out: list[str] = []
    for key, val in universe_block.items():
        if key.startswith("_") or not isinstance(val, list):
            continue
        for sym in val:
            if sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out


def run_all_scanners(params: dict, key: str, secret: str,
                      now_et: Optional[datetime] = None) -> dict[str, ScannerResult]:
    """Top-level orchestration: reads params['scanners'] + params['universe'] (READ ONLY --
    this module never writes params.json), runs all 5 scanners, returns a name->ScannerResult
    dict. A scanner disabled in params.json comes back ok=False with error='disabled_in_params'
    -- distinguishable from a real failure by that message, not by a different flag, so the
    envelope shape stays uniform for every caller."""
    now_et = now_et or et_now()
    scanners_cfg = params.get("scanners") or {}
    universe = flatten_universe(params.get("universe") or {})

    movers_cfg = scanners_cfg.get("movers") or {}
    most_actives_cfg = scanners_cfg.get("most_actives") or {}
    news_cfg = scanners_cfg.get("news") or {}
    gap_cfg = scanners_cfg.get("gap") or {}

    def _disabled(name: str) -> ScannerResult:
        return ScannerResult(name, False, tuple(), 0, "disabled_in_params", now_et.isoformat())

    results: dict[str, ScannerResult] = {}

    results["movers"] = (
        run_movers(key, secret, min_abs_pct=movers_cfg.get("min_abs_pct", 8.0), top=25, now_et=now_et)
        if movers_cfg.get("enabled", True) else _disabled("movers")
    )
    results["most_actives"] = (
        run_most_actives(key, secret, top=most_actives_cfg.get("top", 25), now_et=now_et)
        if most_actives_cfg.get("enabled", True) else _disabled("most_actives")
    )
    if not gap_cfg.get("enabled", True):
        results["gap"] = _disabled("gap")
    elif not universe:
        results["gap"] = ScannerResult("gap", False, tuple(), 0, "empty_symbol_universe", now_et.isoformat())
    else:
        results["gap"] = run_gap(key, secret, symbols=universe,
                                  min_gap_pct=gap_cfg.get("min_gap_pct", 5.0),
                                  min_rel_volume=gap_cfg.get("min_rel_volume", 3.0), now_et=now_et)
    results["news"] = (
        run_news(key, secret, lookback_hours=news_cfg.get("lookback_hours", 24), now_et=now_et)
        if news_cfg.get("enabled", True) else _disabled("news")
    )
    results["composite"] = run_composite(results["movers"], results["most_actives"],
                                          results["gap"], results["news"], now_et=now_et)
    return results
