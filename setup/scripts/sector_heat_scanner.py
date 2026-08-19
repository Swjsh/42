"""sector_heat_scanner.py -- "what's hot, when" (WEEKLY-OPTIONS-PROGRAM.md Sec 6).

>>> SCOPE CONSTRAINT (read before wiring this anywhere) <<<
This is a SELECTION / REPORTING layer ONLY. It ranks sectors and, for the top-3, their
liquid constituents -- for a HUMAN (and later a v2 basket-rotation mechanism) to read.
It MUST NOT gate, filter, or influence any trade decision in v1. Nothing in the weekly
trade path (weekly_core, the entry/exit gates in automation/state/weekly/params.json's
"signal" block) may import this module as a hard AND-gate. params.json already encodes
this correctly: sector_heat_rs sits under "soft_logged_only", never under the gate list.
The reason: stacking another hard AND-gate onto an already 5-6-gate cascade is the exact
mechanism (LESSONS-LEARNED L199) that produced "6 arms, 700 signals, 0 trades" on the SPY
side. This scanner exists to be READ, not obeyed.

WHAT IT COMPUTES (all from DAILY bars, $0, no paid feeds, no ETF-flow subscriptions):
  Universe: 11 SPDR sector ETFs + SMH/GDX/IWM (thematic/small-cap extras), SPY as the
  benchmark (never ranked). Per ticker: a relative-strength-vs-SPY ratio series and its
  %-change over 5/21/63 trading days; a SIMPLIFIED JdK-style RS-Ratio/RS-Momentum pair
  (see _APPROXIMATION NOTE_ below -- this is explicitly NOT real RRG); a 4-quadrant label;
  an MA-stack score 0-3; and a dollar-volume-change flow PROXY (real fund-flow data is a
  paid feed we don't have -- this is volume*price change, honestly labeled as a proxy,
  never presented as "flow").

  Composite heat score: all components are cross-sectionally z-scored across the universe
  EVERY RUN (so a rank is always relative to that day's peers, never an absolute level).
  Design called for 5 weighted components (40/20/20/10/10: rs_1m, rs_momentum, ma_stack,
  breadth, dollar-volume-change). BREADTH WAS DROPPED: a genuinely free breadth input needs
  the FULL constituent list per sector (hundreds of names); we only have a hardcoded top-5
  per sector (see TOP_HOLDINGS below), and computing "breadth" from 5-of-500 names would be
  a number that only LOOKS like breadth while measuring something else -- exactly what the
  program doc warned against substituting. Per its own instruction ("drop that term and
  REWEIGHT explicitly"), the remaining 4 weights are proportionally rescaled to sum to 1.0
  (COMPOSITE_WEIGHTS below; each = original_weight / 0.90).

  _APPROXIMATION NOTE_: StockCharts' real JdK RS-Ratio/RS-Momentum use proprietary double-
  smoothing and normalization constants that are not published. What this module computes
  is a SIMPLIFIED, DOCUMENTED stand-in: RS-Ratio ~= a 10-day SMA of the raw RS-vs-SPY price
  ratio; RS-Momentum ~= that smoothed ratio's own %-change over 5 days. Both get cross-
  sectionally z-scored before use. This is an approximation of the SHAPE of RRG analysis
  (a quadrant plot of relative level vs relative momentum), not a claim of RRG parity.
  Never describe this module's output as "RRG" without this caveat attached.

  TOP_HOLDINGS is a hardcoded, dated, QUARTERLY-REFRESH constant -- top-5 holdings by
  weight for each of the 14 non-benchmark tickers, sourced 2026-08-18 from stockanalysis.com
  ETF holdings pages (which mirror each fund's own daily-published factsheet feed; per-ETF
  "as_of" dates below range 2026-07-30..2026-08-18 per what that page reported at fetch
  time). Weights drift daily in reality -- re-source before trusting exact weights more than
  roughly one quarter past the as_of date. Used for the SECOND PASS: for the top-3 ranked
  tickers each run, their hardcoded constituents get their own 21-trading-day price momentum
  computed and ranked against each other (a lighter, single-metric view -- not the full
  composite; the composite needs the long lookback the hardcoded 5-name list doesn't need).

DATA FEED (never-blind, mirrors setup/scripts/sight_beacon.py's fallback idiom): Alpaca
market-data REST (direct urllib, IEX feed, free tier, split-adjusted) as PRIMARY, yfinance
(auto_adjust=True, split+dividend adjusted) as FALLBACK per ticker. This account has no
OPRA/premium data agreement -- every number this scanner ever produces comes from a free,
delayed/indicative feed. A ticker that fails BOTH sources is recorded under failed_tickers
with the reason from EACH source (never silently dropped with no trace).

NO LOOK-AHEAD: any daily bar dated "today" (ET) is dropped if the current run is before
16:05 ET -- that bar has not closed yet (repo house rule: bar_close_et <= now_et).

FAILS LOUD: if zero tickers produce a usable heat_score, main() prints a clear message to
stderr and returns a non-zero exit code WITHOUT writing analysis/sector-heat/{date}.json --
an empty/zero-row "successful" file is exactly the silent-failure class LESSONS-LEARNED C7
warns about, and this module refuses to produce one.

Run nightly via the (not-yet-scheduled) Gamma_SectorHeat task:
    backtest/.venv/Scripts/python.exe setup/scripts/sector_heat_scanner.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

REPO = Path(__file__).resolve().parents[1].parent
MCP_JSON = REPO / ".mcp.json"
OUT_DIR = REPO / "analysis" / "sector-heat"

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from et_clock import et_now  # noqa: E402  -- DST-aware ET, never hardcoded -4/-5.

STALE_TODAY_BAR_CUTOFF_HHMM = (16, 5)  # before this ET time, today's daily bar isn't closed.


# --------------------------------------------------------------------------------------
# Universe + hardcoded provenance constants
# --------------------------------------------------------------------------------------

BENCHMARK = "SPY"

SECTOR_ETFS: dict[str, str] = {
    "XLK": "Technology Select Sector SPDR",
    "XLE": "Energy Select Sector SPDR",
    "XLF": "Financial Select Sector SPDR",
    "XLV": "Health Care Select Sector SPDR",
    "XLI": "Industrial Select Sector SPDR",
    "XLY": "Consumer Discretionary Select Sector SPDR",
    "XLP": "Consumer Staples Select Sector SPDR",
    "XLU": "Utilities Select Sector SPDR",
    "XLB": "Materials Select Sector SPDR",
    "XLRE": "Real Estate Select Sector SPDR",
    "XLC": "Communication Services Select Sector SPDR",
}

EXTRA_ETFS: dict[str, str] = {
    "SMH": "VanEck Semiconductor ETF",
    "GDX": "VanEck Gold Miners ETF",
    "IWM": "iShares Russell 2000 ETF",
}

UNIVERSE: dict[str, str] = {**SECTOR_ETFS, **EXTRA_ETFS}  # 14 ranked tickers, SPY excluded

# Hardcoded top-5 holdings per ticker. QUARTERLY-REFRESH CONSTANT -- see module docstring
# for provenance. Re-source (stockanalysis.com/etf/<ticker>/holdings/ or the fund's own
# factsheet) before trusting weights beyond ~1 quarter past "as_of".
TOP_HOLDINGS: dict[str, dict] = {
    "XLK": {"as_of": "2026-08-07", "holdings": [
        {"ticker": "NVDA", "name": "NVIDIA Corporation", "weight_pct": 14.46},
        {"ticker": "AAPL", "name": "Apple Inc.", "weight_pct": 12.26},
        {"ticker": "MSFT", "name": "Microsoft Corporation", "weight_pct": 9.90},
        {"ticker": "AVGO", "name": "Broadcom Inc.", "weight_pct": 5.40},
        {"ticker": "AMD", "name": "Advanced Micro Devices, Inc.", "weight_pct": 4.00},
    ]},
    "XLE": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "XOM", "name": "ExxonMobil Corporation", "weight_pct": 20.54},
        {"ticker": "CVX", "name": "Chevron Corporation", "weight_pct": 14.99},
        {"ticker": "COP", "name": "ConocoPhillips", "weight_pct": 6.14},
        {"ticker": "MPC", "name": "Marathon Petroleum Corporation", "weight_pct": 5.43},
        {"ticker": "PSX", "name": "Phillips 66", "weight_pct": 5.28},
    ]},
    "XLF": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "weight_pct": 11.83},
        {"ticker": "BRK.B", "name": "Berkshire Hathaway Inc.", "weight_pct": 11.24},
        {"ticker": "V", "name": "Visa Inc.", "weight_pct": 7.35},
        {"ticker": "MA", "name": "Mastercard Incorporated", "weight_pct": 5.59},
        {"ticker": "BAC", "name": "Bank of America Corporation", "weight_pct": 5.12},
    ]},
    "XLV": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "LLY", "name": "Eli Lilly and Company", "weight_pct": 15.71},
        {"ticker": "JNJ", "name": "Johnson & Johnson", "weight_pct": 10.38},
        {"ticker": "ABBV", "name": "AbbVie Inc.", "weight_pct": 7.29},
        {"ticker": "UNH", "name": "UnitedHealth Group Incorporated", "weight_pct": 5.96},
        {"ticker": "MRK", "name": "Merck & Co., Inc.", "weight_pct": 5.51},
    ]},
    "XLI": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "CAT", "name": "Caterpillar Inc.", "weight_pct": 6.74},
        {"ticker": "GE", "name": "GE Aerospace", "weight_pct": 6.44},
        {"ticker": "RTX", "name": "RTX Corporation", "weight_pct": 5.07},
        {"ticker": "GEV", "name": "GE Vernova Inc.", "weight_pct": 4.83},
        {"ticker": "BA", "name": "The Boeing Company", "weight_pct": 3.11},
    ]},
    "XLY": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "AMZN", "name": "Amazon.com, Inc.", "weight_pct": 24.30},
        {"ticker": "TSLA", "name": "Tesla, Inc.", "weight_pct": 15.86},
        {"ticker": "HD", "name": "The Home Depot, Inc.", "weight_pct": 5.55},
        {"ticker": "MCD", "name": "McDonald's Corporation", "weight_pct": 4.16},
        {"ticker": "BKNG", "name": "Booking Holdings Inc.", "weight_pct": 4.06},
    ]},
    "XLP": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "WMT", "name": "Walmart Inc.", "weight_pct": 10.64},
        {"ticker": "COST", "name": "Costco Wholesale Corporation", "weight_pct": 8.97},
        {"ticker": "KO", "name": "The Coca-Cola Company", "weight_pct": 7.15},
        {"ticker": "PG", "name": "The Procter & Gamble Company", "weight_pct": 7.08},
        {"ticker": "PM", "name": "Philip Morris International Inc.", "weight_pct": 6.24},
    ]},
    "XLU": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "NEE", "name": "NextEra Energy, Inc.", "weight_pct": 13.02},
        {"ticker": "SO", "name": "The Southern Company", "weight_pct": 7.59},
        {"ticker": "DUK", "name": "Duke Energy Corporation", "weight_pct": 6.98},
        {"ticker": "CEG", "name": "Constellation Energy Corporation", "weight_pct": 6.47},
        {"ticker": "AEP", "name": "American Electric Power Company, Inc.", "weight_pct": 4.95},
    ]},
    "XLB": {"as_of": "2026-08-13", "holdings": [
        {"ticker": "LIN", "name": "Linde plc", "weight_pct": 12.94},
        {"ticker": "NEM", "name": "Newmont Corporation", "weight_pct": 7.13},
        {"ticker": "FCX", "name": "Freeport-McMoRan Inc.", "weight_pct": 5.62},
        {"ticker": "SHW", "name": "The Sherwin-Williams Company", "weight_pct": 5.18},
        {"ticker": "APD", "name": "Air Products and Chemicals, Inc.", "weight_pct": 4.81},
    ]},
    "XLRE": {"as_of": "2026-08-13", "holdings": [
        {"ticker": "WELL", "name": "Welltower Inc.", "weight_pct": 11.08},
        {"ticker": "PLD", "name": "Prologis, Inc.", "weight_pct": 8.96},
        {"ticker": "EQIX", "name": "Equinix, Inc.", "weight_pct": 7.09},
        {"ticker": "AMT", "name": "American Tower Corporation", "weight_pct": 5.43},
        {"ticker": "DLR", "name": "Digital Realty Trust, Inc.", "weight_pct": 5.11},
    ]},
    "XLC": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "META", "name": "Meta Platforms, Inc.", "weight_pct": 17.47},
        {"ticker": "GOOGL", "name": "Alphabet Inc. (Class A)", "weight_pct": 10.53},
        {"ticker": "GOOG", "name": "Alphabet Inc. (Class C)", "weight_pct": 8.43},
        {"ticker": "T", "name": "AT&T Inc.", "weight_pct": 5.00},
        {"ticker": "VZ", "name": "Verizon Communications Inc.", "weight_pct": 4.85},
    ]},
    "SMH": {"as_of": "2026-08-18", "holdings": [
        {"ticker": "NVDA", "name": "NVIDIA Corporation", "weight_pct": 21.70},
        {"ticker": "TSM", "name": "Taiwan Semiconductor Manufacturing Company Limited", "weight_pct": 9.51},
        {"ticker": "AVGO", "name": "Broadcom Inc.", "weight_pct": 6.73},
        {"ticker": "AMD", "name": "Advanced Micro Devices, Inc.", "weight_pct": 5.43},
        {"ticker": "ASML", "name": "ASML Holding N.V.", "weight_pct": 5.12},
    ]},
    "GDX": {"as_of": "2026-07-30", "holdings": [
        {"ticker": "NEM", "name": "Newmont Corporation", "weight_pct": 10.37},
        {"ticker": "AEM", "name": "Agnico Eagle Mines Limited", "weight_pct": 10.12},
        {"ticker": "B", "name": "Barrick Mining Corporation", "weight_pct": 8.01},
        {"ticker": "WPM", "name": "Wheaton Precious Metals Corp.", "weight_pct": 5.56},
        {"ticker": "FNV", "name": "Franco-Nevada Corporation", "weight_pct": 5.12},
    ]},
    "IWM": {"as_of": "2026-08-18", "holdings": [
        # Broad small-cap index -- no dominant names; largest weight is <0.4%. Included
        # honestly rather than omitted so a second-pass on IWM (if it ever ranks top-3)
        # doesn't silently no-op.
        {"ticker": "MOG.A", "name": "Moog Inc.", "weight_pct": 0.38},
        {"ticker": "UMBF", "name": "UMB Financial Corporation", "weight_pct": 0.35},
        {"ticker": "GKOS", "name": "Glaukos Corporation", "weight_pct": 0.34},
        {"ticker": "VSAT", "name": "Viasat, Inc.", "weight_pct": 0.33},
        {"ticker": "FROG", "name": "JFrog Ltd.", "weight_pct": 0.32},
    ]},
}
TOP_HOLDINGS_SOURCE = "stockanalysis.com ETF holdings pages (mirrors fund factsheet feed)"

# Composite weights. Design called for 40/20/20/10(breadth)/10(dollar-vol); breadth was
# DROPPED (see module docstring) and the remaining 4 rescaled to sum to 1.0.
COMPOSITE_WEIGHTS: dict[str, float] = {
    "rs_1m_z": 0.40 / 0.90,
    "rs_momentum_z": 0.20 / 0.90,
    "ma_stack_z": 0.20 / 0.90,
    "dollar_volume_change_z": 0.10 / 0.90,
}
assert abs(sum(COMPOSITE_WEIGHTS.values()) - 1.0) < 1e-9, "COMPOSITE_WEIGHTS must sum to 1.0"

UNIVERSE_LOOKBACK_CALENDAR_DAYS = 420   # ~300 trading days -- enough for SMA200 + 63d RS change
CONSTITUENT_LOOKBACK_CALENDAR_DAYS = 90  # only needs a 21-trading-day pct-change


class SectorHeatEmptyResultError(RuntimeError):
    """Raised when a run would produce zero scoreable rows. Callers must NOT write a file
    when this fires -- an empty-but-successful sector-heat file is the exact silent-failure
    class LESSONS-LEARNED C7 exists to prevent."""


# --------------------------------------------------------------------------------------
# Data fetch layer (never-blind: Alpaca primary, yfinance fallback -- mirrors sight_beacon.py)
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyBars:
    ticker: str
    dates: tuple[str, ...]     # ascending 'YYYY-MM-DD', ET trading-session date
    closes: tuple[float, ...]
    volumes: tuple[float, ...]
    source: str                # "alpaca_rest_iex" | "yfinance"
    fetch_note: str


def _load_alpaca_key(mcp_json: Path = MCP_JSON) -> tuple[str, str]:
    """Market-data-only read; the weekly-1 account doesn't exist yet (params.json _status
    is SHADOW_PENDING_BUILD), so this deliberately reuses the already-wired 'alpaca' (Safe)
    server credential purely for public market-data reads -- same precedent as sight_beacon.py."""
    try:
        m = json.loads(mcp_json.read_text(encoding="utf-8"))
        env = m.get("mcpServers", {}).get("alpaca", {}).get("env", {})
        return env.get("ALPACA_API_KEY", ""), env.get("ALPACA_SECRET_KEY", "")
    except (OSError, json.JSONDecodeError):
        return "", ""


def _fetch_alpaca_daily_bars(symbol: str, lookback_days: int) -> tuple[Optional[DailyBars], str]:
    """Alpaca daily bars (IEX feed, free tier, split-adjusted -- NOT dividend-adjusted).

    Unlike sight_beacon.py's 5m fetch, no desc-then-reverse trick is needed: limit=1000 far
    exceeds the ~300 trading days a UNIVERSE_LOOKBACK_CALENDAR_DAYS window produces, so
    sort=asc cannot truncate the newest bars off the tail here.
    """
    key, sec = _load_alpaca_key()
    if not key or not sec:
        return None, "no_key"
    start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
           f"?timeframe=1Day&start={start}&limit=1000&feed=iex&adjustment=split&sort=asc")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}"
    except Exception as e:  # noqa: BLE001 -- reason is returned, never swallowed
        return None, f"err_{type(e).__name__}"
    bars = data.get("bars") or []
    dates = tuple(b["t"][:10] for b in bars if b.get("c") is not None)
    closes = tuple(float(b["c"]) for b in bars if b.get("c") is not None)
    volumes = tuple(float(b.get("v") or 0.0) for b in bars if b.get("c") is not None)
    if not closes:
        return None, "empty"
    return (DailyBars(symbol, dates, closes, volumes, "alpaca_rest_iex", f"ok_{len(closes)}bars"),
            f"ok_{len(closes)}bars")


def _yf_symbol(ticker: str) -> str:
    """yfinance uses '-' for share classes ('BRK-B'); Alpaca/factsheets use '.' ('BRK.B')."""
    return ticker.replace(".", "-")


def _fetch_yfinance_daily_bars(symbol: str, lookback_days: int) -> tuple[Optional[DailyBars], str]:
    """yfinance fallback -- no auth, split+dividend adjusted (auto_adjust=True)."""
    try:
        import yfinance as yf
    except ImportError:
        return None, "no_yfinance"
    try:
        df = yf.download(_yf_symbol(symbol), period=f"{lookback_days}d", interval="1d",
                          auto_adjust=True, progress=False, prepost=False)
        if df is None or df.empty:
            return None, "empty"
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        dates, closes, volumes = [], [], []
        for idx, row in df.iterrows():
            c = row.get("Close")
            if c != c:  # NaN
                continue
            dates.append(idx.strftime("%Y-%m-%d"))
            closes.append(float(c))
            v = row.get("Volume")
            volumes.append(float(v) if v == v else 0.0)
        if not closes:
            return None, "empty"
        return (DailyBars(symbol, tuple(dates), tuple(closes), tuple(volumes), "yfinance",
                           f"ok_{len(closes)}bars"),
                f"ok_{len(closes)}bars")
    except Exception as e:  # noqa: BLE001
        return None, f"err_{type(e).__name__}"


def _drop_unclosed_today_bar(bars: DailyBars, now_et: datetime) -> DailyBars:
    """No-look-ahead guard: a daily bar dated today isn't closed until ~16:00 ET. Drop it
    if we're running before the settle buffer (repo house rule: bar_close_et <= now_et)."""
    if not bars.dates:
        return bars
    today_et = now_et.strftime("%Y-%m-%d")
    if bars.dates[-1] == today_et and (now_et.hour, now_et.minute) < STALE_TODAY_BAR_CUTOFF_HHMM:
        return replace(bars, dates=bars.dates[:-1], closes=bars.closes[:-1],
                        volumes=bars.volumes[:-1],
                        fetch_note=bars.fetch_note + "|dropped_unclosed_today_bar")
    return bars


def fetch_daily_bars(symbol: str, lookback_days: int,
                      now_et: Optional[datetime] = None) -> tuple[Optional[DailyBars], str]:
    """Alpaca primary, yfinance fallback. Returns (bars_or_None, note). note ALWAYS carries
    the real reason -- even on total failure -- so a caller never has to guess why a ticker
    is missing (no silent fallback: the failure is visible in the output artifact)."""
    now_et = now_et or et_now()
    bars, a_note = _fetch_alpaca_daily_bars(symbol, lookback_days)
    if bars is not None and len(bars.closes) >= 30:
        return _drop_unclosed_today_bar(bars, now_et), f"alpaca_rest_iex:{a_note}"
    bars, y_note = _fetch_yfinance_daily_bars(symbol, lookback_days)
    if bars is not None and len(bars.closes) >= 30:
        return (_drop_unclosed_today_bar(bars, now_et),
                f"yfinance:{y_note} (alpaca_failed:{a_note})")
    return None, f"both_sources_failed alpaca={a_note} yfinance={y_note}"


# --------------------------------------------------------------------------------------
# Pure compute layer -- no network, deterministic, unit-testable with synthetic bars
# --------------------------------------------------------------------------------------

def _align_by_date(bars: DailyBars, bench: DailyBars) -> Optional[tuple[list[str], list[float], list[float], list[float]]]:
    """Intersect two DailyBars on date, preserving ascending order. None if <30 common days."""
    bench_close = dict(zip(bench.dates, bench.closes))
    common = [d for d in bars.dates if d in bench_close]
    if len(common) < 30:
        return None
    close_by_date = dict(zip(bars.dates, bars.closes))
    vol_by_date = dict(zip(bars.dates, bars.volumes))
    closes = [close_by_date[d] for d in common]
    volumes = [vol_by_date[d] for d in common]
    bench_closes = [bench_close[d] for d in common]
    return common, closes, volumes, bench_closes


def relative_strength_series(closes: Sequence[float], bench_closes: Sequence[float]) -> list[float]:
    """RS ratio series = closes[i] / bench_closes[i], index-aligned by the caller."""
    if len(closes) != len(bench_closes):
        raise ValueError("relative_strength_series: closes and bench_closes must be same length")
    out = []
    for c, b in zip(closes, bench_closes):
        if b == 0:
            raise ValueError("relative_strength_series: benchmark close is zero")
        out.append(c / b)
    return out


def pct_change_n(values: Sequence[float], n: int) -> Optional[float]:
    """% change over the last n periods. None (never 0.0) if insufficient history."""
    if len(values) < n + 1:
        return None
    prev = values[-(n + 1)]
    if prev == 0:
        return None
    return (values[-1] - prev) / prev * 100.0


def sma(values: Sequence[float], window: int) -> Optional[float]:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def ma_stack_score(closes: Sequence[float]) -> Optional[int]:
    """0-3: close>SMA20 (+1), SMA20>SMA50 (+1), SMA50>SMA200 (+1). None if <200 bars."""
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    if s20 is None or s50 is None or s200 is None:
        return None
    score = 0
    if closes[-1] > s20:
        score += 1
    if s20 > s50:
        score += 1
    if s50 > s200:
        score += 1
    return score


def dollar_volume_change_pct(closes: Sequence[float], volumes: Sequence[float],
                              window: int = 21) -> Optional[float]:
    """Flow PROXY (close*volume), NOT real fund-flow data -- that's a paid feed we don't
    have. Recent `window`-day avg dollar volume vs the PRIOR `window`-day avg. None if
    insufficient history."""
    if len(closes) < 2 * window or len(volumes) < 2 * window:
        return None
    dollar_vol = [c * v for c, v in zip(closes, volumes)]
    recent_avg = sum(dollar_vol[-window:]) / window
    prior_avg = sum(dollar_vol[-2 * window:-window]) / window
    if prior_avg == 0:
        return None
    return (recent_avg - prior_avg) / prior_avg * 100.0


def jdk_style_rs_ratio_momentum(rs_series: Sequence[float], ratio_smooth: int = 10,
                                 momentum_window: int = 5) -> tuple[Optional[float], Optional[float]]:
    """SIMPLIFIED JdK-style RS-Ratio / RS-Momentum APPROXIMATION -- see module docstring
    _APPROXIMATION NOTE_. rs_ratio_raw = SMA(rs_series, ratio_smooth)[-1]; rs_momentum_raw =
    that smoothed ratio's own %-change over momentum_window periods. Both are cross-
    sectionally z-scored by the caller before use -- these raw units are not comparable
    across tickers on their own."""
    if len(rs_series) < ratio_smooth:
        return None, None
    smoothed = [sum(rs_series[max(0, i - ratio_smooth + 1):i + 1]) /
                len(rs_series[max(0, i - ratio_smooth + 1):i + 1])
                for i in range(len(rs_series))]
    if len(smoothed) < momentum_window + 1:
        return smoothed[-1], None
    rs_ratio_raw = smoothed[-1]
    prev = smoothed[-1 - momentum_window]
    rs_momentum_raw = ((smoothed[-1] - prev) / prev * 100.0) if prev != 0 else None
    return rs_ratio_raw, rs_momentum_raw


def zscore(values: Sequence[Optional[float]]) -> list[Optional[float]]:
    """Cross-sectional z-score. A None input stays None in the output -- a fabricated 0.0
    would silently claim 'exactly average', which is a lie for missing data."""
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        return [None for _ in values]
    mean = sum(valid) / len(valid)
    var = sum((v - mean) ** 2 for v in valid) / len(valid)
    std = var ** 0.5
    if std == 0:
        return [0.0 if v is not None else None for v in values]
    return [((v - mean) / std) if v is not None else None for v in values]


def quadrant_label(rs_ratio_z: Optional[float], rs_momentum_z: Optional[float]) -> str:
    """4-quadrant RRG-style label from the (already cross-sectionally z-scored) RS-Ratio and
    RS-Momentum. Boundary convention: >=0 counts as the 'strong' side of each axis (the
    cross-sectional mean, z=0, is the natural neutral line)."""
    if rs_ratio_z is None or rs_momentum_z is None:
        return "UNKNOWN"
    if rs_ratio_z >= 0 and rs_momentum_z >= 0:
        return "LEADING"
    if rs_ratio_z >= 0 and rs_momentum_z < 0:
        return "WEAKENING"
    if rs_ratio_z < 0 and rs_momentum_z < 0:
        return "LAGGING"
    return "IMPROVING"


def composite_heat_score(rs_1m_z: Optional[float], rs_momentum_z: Optional[float],
                          ma_stack_z: Optional[float],
                          dollar_volume_change_z: Optional[float]) -> Optional[float]:
    """Weighted sum per COMPOSITE_WEIGHTS. None (never a partial number) if ANY component is
    missing -- a score computed from 3-of-4 components would silently misrepresent itself as
    comparable to a peer's 4-of-4 score."""
    parts = {
        "rs_1m_z": rs_1m_z,
        "rs_momentum_z": rs_momentum_z,
        "ma_stack_z": ma_stack_z,
        "dollar_volume_change_z": dollar_volume_change_z,
    }
    if any(v is None for v in parts.values()):
        return None
    return sum(COMPOSITE_WEIGHTS[k] * v for k, v in parts.items())


def compute_ticker_metrics(ticker: str, name: str, bars: Optional[DailyBars],
                            bench_bars: Optional[DailyBars], fetch_note: str) -> dict:
    """Raw (pre-cross-section) metrics for one ticker. Pure -- no network, no ranking."""
    if bars is None or bench_bars is None:
        return {"ticker": ticker, "name": name, "ok": False,
                "reason": fetch_note or "no_bars", "data_source": None}
    aligned = _align_by_date(bars, bench_bars)
    if aligned is None:
        return {"ticker": ticker, "name": name, "ok": False,
                "reason": "insufficient_aligned_bars", "data_source": bars.source}
    dates, closes, volumes, bench_closes = aligned
    rs_series = relative_strength_series(closes, bench_closes)
    rs_ratio_raw, rs_momentum_raw = jdk_style_rs_ratio_momentum(rs_series)
    return {
        "ticker": ticker,
        "name": name,
        "ok": True,
        "as_of": dates[-1],
        "data_source": bars.source,
        "fetch_note": fetch_note,
        "n_aligned_bars": len(dates),
        "rs_1w_pct": pct_change_n(rs_series, 5),
        "rs_1m_pct": pct_change_n(rs_series, 21),
        "rs_3m_pct": pct_change_n(rs_series, 63),
        "rs_ratio_raw": rs_ratio_raw,
        "rs_momentum_raw": rs_momentum_raw,
        "ma_stack_score": ma_stack_score(closes),
        "dollar_volume_change_pct": dollar_volume_change_pct(closes, volumes),
    }


def rank_universe(raw_rows: list[dict]) -> list[dict]:
    """Cross-sectionally z-score the ok rows, attach quadrant + heat_score + rank (1=hottest).
    Rows with a component missing get heat_score=None and rank=None (excluded from ranking,
    still reported). Failed (ok=False) rows pass through unchanged, appended last."""
    ok_rows = [dict(r) for r in raw_rows if r.get("ok")]
    failed_rows = [dict(r) for r in raw_rows if not r.get("ok")]

    rs_1m_z = zscore([r.get("rs_1m_pct") for r in ok_rows])
    rs_mom_z = zscore([r.get("rs_momentum_raw") for r in ok_rows])
    rs_ratio_z = zscore([r.get("rs_ratio_raw") for r in ok_rows])
    ma_z = zscore([r.get("ma_stack_score") for r in ok_rows])
    dv_z = zscore([r.get("dollar_volume_change_pct") for r in ok_rows])

    for i, r in enumerate(ok_rows):
        r["rs_1m_z"] = rs_1m_z[i]
        r["rs_momentum_z"] = rs_mom_z[i]
        r["rs_ratio_z"] = rs_ratio_z[i]
        r["ma_stack_z"] = ma_z[i]
        r["dollar_volume_change_z"] = dv_z[i]
        r["quadrant"] = quadrant_label(rs_ratio_z[i], rs_mom_z[i])
        r["heat_score"] = composite_heat_score(rs_1m_z[i], rs_mom_z[i], ma_z[i], dv_z[i])

    scored = sorted((r for r in ok_rows if r["heat_score"] is not None),
                     key=lambda r: r["heat_score"], reverse=True)
    unscored = [r for r in ok_rows if r["heat_score"] is None]
    for rank, r in enumerate(scored, start=1):
        r["rank"] = rank
    for r in unscored:
        r["rank"] = None
    return scored + unscored + failed_rows


def build_constituent_rows(constituent_holdings: list[dict],
                            bars_by_ticker: dict[str, tuple[Optional[DailyBars], str]]) -> list[dict]:
    """Second pass for one top-3 sector: rank its hardcoded constituents by their OWN
    21-trading-day price momentum (a lighter single-metric view, not the full composite --
    the composite needs the 200-bar lookback a small holdings list doesn't need)."""
    rows = []
    for h in constituent_holdings:
        sym = h["ticker"]
        bars, note = bars_by_ticker.get(sym, (None, "not_fetched"))
        if bars is None or len(bars.closes) < 22:
            rows.append({"ticker": sym, "name": h["name"], "weight_pct": h["weight_pct"],
                         "ok": False, "reason": note})
            continue
        rows.append({
            "ticker": sym, "name": h["name"], "weight_pct": h["weight_pct"], "ok": True,
            "pct_change_21d": pct_change_n(list(bars.closes), 21),
            "as_of": bars.dates[-1], "data_source": bars.source,
        })
    scored = sorted((r for r in rows if r.get("ok") and r.get("pct_change_21d") is not None),
                     key=lambda r: r["pct_change_21d"], reverse=True)
    unscored = [r for r in rows if r not in scored]
    for rank, r in enumerate(scored, start=1):
        r["rank_in_sector"] = rank
    return scored + unscored


# --------------------------------------------------------------------------------------
# Output assembly + write
# --------------------------------------------------------------------------------------

def build_snapshot(ranked_rows: list[dict], top3_constituents: dict[str, list[dict]],
                    as_of: str, generated_at_et: str) -> dict:
    """Assemble the final JSON dict. Raises SectorHeatEmptyResultError if zero rows produced
    a usable heat_score -- callers must not write a file in that case."""
    scored = [r for r in ranked_rows if r.get("heat_score") is not None]
    if not scored:
        raise SectorHeatEmptyResultError(
            "sector_heat_scanner: zero tickers produced a usable heat_score this run -- "
            "refusing to write an empty/zero-row file.")
    source_counts: dict[str, int] = {}
    for r in ranked_rows:
        src = r.get("data_source") or "failed"
        source_counts[src] = source_counts.get(src, 0) + 1
    return {
        "_doc": "Advisory sector-heat scanner. SELECTION/REPORTING LAYER ONLY -- never a "
                "trade gate (see module docstring in setup/scripts/sector_heat_scanner.py). "
                "RS-Ratio/RS-Momentum are a SIMPLIFIED APPROXIMATION of RRG, not real RRG.",
        "as_of": as_of,
        "generated_at_et": generated_at_et,
        "benchmark": BENCHMARK,
        "composite_weights": COMPOSITE_WEIGHTS,
        "_weights_note": "breadth-or-proxy component DROPPED (no genuinely free breadth "
                          "input existed) and the remaining 4 weights proportionally "
                          "rescaled to sum to 1.0 -- see module docstring.",
        "data_provenance": source_counts,
        "rows": ranked_rows,
        "top3_constituents": top3_constituents,
        "top_holdings_source": TOP_HOLDINGS_SOURCE,
    }


def write_snapshot(snapshot: dict, out_dir: Path = OUT_DIR) -> Path:
    """Atomic write (tmp + replace, mirrors sight_beacon.py). Refuses (belt-and-suspenders,
    build_snapshot already guards this) to write a file with zero scored rows."""
    if not any(r.get("heat_score") is not None for r in snapshot.get("rows", [])):
        raise SectorHeatEmptyResultError(
            "write_snapshot: snapshot has zero scored rows -- refusing to write.")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{snapshot['as_of']}.json"
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    return out_path


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def main() -> int:
    now_et = et_now()
    bench_bars, bench_note = fetch_daily_bars(BENCHMARK, UNIVERSE_LOOKBACK_CALENDAR_DAYS, now_et)
    if bench_bars is None:
        print(f"sector_heat_scanner: FAILED -- benchmark {BENCHMARK} unfetchable "
              f"({bench_note}). Cannot compute relative strength for anything. Aborting.",
              file=sys.stderr)
        return 1

    raw_rows = []
    for ticker, name in UNIVERSE.items():
        bars, note = fetch_daily_bars(ticker, UNIVERSE_LOOKBACK_CALENDAR_DAYS, now_et)
        raw_rows.append(compute_ticker_metrics(ticker, name, bars, bench_bars, note))

    ranked_rows = rank_universe(raw_rows)

    top3 = [r for r in ranked_rows if r.get("rank") in (1, 2, 3)]
    top3_constituents: dict[str, list[dict]] = {}
    for r in top3:
        tkr = r["ticker"]
        holdings = TOP_HOLDINGS.get(tkr, {}).get("holdings", [])
        if not holdings:
            top3_constituents[tkr] = []
            continue
        bars_by_ticker = {h["ticker"]: fetch_daily_bars(h["ticker"], CONSTITUENT_LOOKBACK_CALENDAR_DAYS, now_et)
                           for h in holdings}
        top3_constituents[tkr] = build_constituent_rows(holdings, bars_by_ticker)

    try:
        snapshot = build_snapshot(
            ranked_rows, top3_constituents,
            as_of=bench_bars.dates[-1] if bench_bars.dates else now_et.strftime("%Y-%m-%d"),
            generated_at_et=now_et.strftime("%Y-%m-%dT%H:%M:%S"))
    except SectorHeatEmptyResultError as e:
        print(f"sector_heat_scanner: {e}", file=sys.stderr)
        return 1

    out_path = write_snapshot(snapshot)
    n_scored = sum(1 for r in ranked_rows if r.get("heat_score") is not None)
    n_failed = sum(1 for r in ranked_rows if not r.get("ok"))
    print(f"sector_heat_scanner: wrote {out_path} ({n_scored}/{len(UNIVERSE)} scored, "
          f"{n_failed} failed)")
    if top3:
        leaders = ", ".join(f"{r['ticker']}({r['heat_score']:.2f})" for r in top3)
        print(f"top-3: {leaders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
