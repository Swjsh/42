"""Real OPRA option contract bar lookup — replaces Black-Scholes with actual fills.

Reads cached CSVs from `backtest/data/options/{symbol}.csv` (populated by
`tools/fetch_option_data.py`, which hardcodes `timeframe="5Min"`). Returns OHLCV+VWAP
for any (symbol, time_et).

Fill model (when used by simulator_real.py):
  - Entry: next 5-min bar's VWAP after the trigger bar (proxy for an intra-bar fill)
  - Stop: bar's high (worst adverse for puts → spot up = put down) becomes premium low
  - TP1: bar's high (best favorable for puts) becomes premium high
  - Exit-on-close events (ribbon flip / level stop / time stop): bar.close

Note: for a PUT, premium moves INVERSE to spot. The Alpaca bars give us the option's
own OHLCV — `high` is the put's highest premium during the bar, `low` is the lowest.
We don't need to invert anything; we just use the bar's own high/low.

RESOLUTION DISCLOSURE (added 2026-08-02, OPTION-BAR-RESOLUTION-BIAS-2026-08-02 --
`analysis/deep-research/OPTION-BAR-RESOLUTION-BIAS-2026-08-02.md`): this file's ONLY data
source is the 5-MINUTE OPRA cache described above. A stop that is breached and recovers
INSIDE a 5-minute bar is invisible at this resolution — no stop hit is recorded where a real
1-minute tick (and the live engine) would have taken one. Measured on the canonical
real-fills population (123 positions, all 6 arms): 4 positions' exits flip from non-stop to
stop-ONLY-at-1-minute, 0 the other way (the bias is one-directional — 5-min never invents a
phantom stop, it only misses real ones), aggregate P&L swing $1,821.75, always in the
direction of 5-min FLATTERING P&L (see the artifact + `analysis/recommendations/
option-bar-resolution-bias-2026-08-02.json`). `load_contract_bars` now takes an explicit,
logged `resolution` kwarg (default `"5min"`, unchanged behavior for all ~250 existing
callers) instead of a silent default, per that finding's remediation. Callers that need
honest intra-bar stop/TP fidelity should use live 1-minute REST bars instead — see
`backtest/tools/_option_bars_1min_cache.fetch_1min_cached` (wraps
`exit_shape_parity_study.fetch_option_bars`) — this file does not fetch or cache 1-minute
data itself (scope discipline: touching this file's actual data path for ~250 importers in
one session was judged unsafe; see the artifact's "what shipped vs what was deferred"
section). `assert_intraday_stop_fidelity()` below is an opt-in guard any exit-walk consumer
can call to fail loudly on an unacknowledged 5-min request — see
`backtest/lib/exit_manager_walk.walk_exit_manager`'s `opt_df_resolution`/`allow_5min` kwargs
for the wired example.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Dual-import fallback (added 2026-08-02 alongside the `frame` kwarg below): this module is
# reachable via THREE different import forms across the codebase -- package-qualified
# (`from lib import option_pricing_real`, common) and bare top-level (`import
# option_pricing_real` / `from option_pricing_real import X`, exercised when
# exit_manager_walk.py's own bare-top-level fallback pulls this module in with
# backtest/lib on sys.path -- see e.g. backtest/tests/test_exit_manager_walk_entry_bar_
# convention.py). A plain relative import here would break that bare-top-level form exactly
# the way exit_manager_walk.py's own option_pricing_real import broke earlier this session
# (see that file's docstring) -- so this uses the same try-relative-then-bare-absolute
# fallback, verified against the full regression sweep before being reported done.
try:
    from .et_frame import FRAME_ET_V2, FRAME_WALL_V1, parse_timestamp_et
except ImportError:
    from et_frame import FRAME_ET_V2, FRAME_WALL_V1, parse_timestamp_et

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "options"

# The ONLY resolution this file's disk cache serves. Not a runtime choice — documents what
# "5min" means when passed to load_contract_bars(resolution=...) / assert_intraday_stop_fidelity.
NATIVE_RESOLUTION = "5min"

# Emit the disclosure log line at most once per process (250+ importers can call
# load_contract_bars thousands of times per run -- a per-call log would drown stdout without
# adding information after the first line). Emitted on the first DEFAULT (unstated-resolution)
# call only, matching the "silent default" this exists to surface.
_disclosed_default_resolution = False

# Process-level in-memory cache for loaded contract bars.
# Populated lazily by load_contract_bars(); persists for the lifetime of the
# worker process.  With multiprocessing.Pool(maxtasksperchild=10), a worker
# handles up to 10 combos before recycling, so all contracts touched by combo-0
# are already in RAM when combo-1 runs.  This eliminates repeated CSV reads
# that caused the overnight/v14e grinders to run 19× slower after the real-fills
# upgrade (each combo triggered hundreds of individual CSV reads from the 7K+
# OPRA cache files).
_CONTRACT_BAR_CACHE: dict[str, Optional[pd.DataFrame]] = {}


def assert_intraday_stop_fidelity(resolution: str, *, allow_5min: bool = True) -> None:
    """Opt-in guard for exit-walk consumers: raises ValueError if `resolution` is the 5-min
    native resolution (which under-detects intra-bar stop/TP touches — see module docstring's
    RESOLUTION DISCLOSURE) and the caller has not explicitly set `allow_5min=True`.

    Backward-compatible by construction: nothing calls this unless it opts in (see
    exit_manager_walk.walk_exit_manager's opt_df_resolution kwarg, default None = never
    called). Not wired into load_contract_bars itself — that function's own `resolution`
    kwarg validation (raises on anything but "5min") is the load-bearing guard for ITS
    callers; this one is for callers a step removed, who receive an already-loaded opt_df
    and only know its resolution if they ask for it explicitly.
    """
    if resolution == NATIVE_RESOLUTION and not allow_5min:
        raise ValueError(
            f"resolution={resolution!r} requested without allow_5min=True: 5-minute option "
            "bars under-detect intra-bar stop/TP touches (OPTION-BAR-RESOLUTION-BIAS-2026-08-02, "
            "measured $1,821.75 aggregate swing on the real-fills population, one-directional). "
            "Pass allow_5min=True to proceed anyway (e.g. a study that has already disclosed "
            "this gap), or source 1-minute bars via "
            "backtest/tools/_option_bars_1min_cache.fetch_1min_cached."
        )


@dataclass(frozen=True)
class OptionBar:
    """One option bar. Every CURRENT caller of load_contract_bars() gets 5-minute bars (this
    file's only data source — see module docstring's RESOLUTION DISCLOSURE); the field shape
    itself does not encode resolution."""
    timestamp_et: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    trade_count: int


def option_symbol(trade_date: dt.date, strike: int, side: str, root: str = "SPY") -> str:
    """Build a real-world (broker/vendor) OCC option symbol:
    {ROOT}{YYMMDD}{C|P}{strike*1000:08d}.

    GENERALIZED 2026-08-18 (markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §5 "New" -- the
    weekly-options lane trades GLD/QQQ/NVDA/TSLA/AAPL, not just SPY) from the original
    hardcoded `f"SPY{yymmdd}{s}{strike*1000:08d}"`. `root` is a NEW keyword parameter
    defaulting to "SPY", so every existing 3-positional-arg call site (~250 across this
    codebase) is byte-identical to before -- pinned by
    test_option_symbol_multi_root_2026_08_18.py against the two independently-known-good
    strings already asserted elsewhere in this repo:
    test_bull_gate_f5class_requal_2026_08_01.py's "SPY260731C00746000" and the WINTER_OPRA
    cache filename in test_et_frame_guards.py ("SPY250102C00580000").

    ROOT-PADDING CORRECTNESS NOTE: the formally published OCC "Options Symbology
    Initiative" spec pads the root LEFT-JUSTIFIED to a fixed 6 characters (blank-filled)
    inside a rigid 21-character field. Real brokers/vendors -- Alpaca (this shop's
    broker), OPRA, and WeBull (verified against J's own real historical fills,
    analysis/webull-j-trades/j_roundtrips.json, e.g. "TSLA210611C00620000",
    "NVDA210618C00795000", "AAPL211119C00152500" -- all UNPADDED, variable total length)
    -- never emit that space padding; they concatenate the root at its NATURAL length
    directly against YYMMDD. This function matches the VENDOR convention (what Alpaca
    actually returns, and what this codebase's CSV cache is keyed by), not the padded
    spec -- both because (a) it must match real broker/CSV-cache symbols, and (b) padding
    would break the "SPY output byte-identical to before" backward-compat requirement
    above (padded "SPY   " is a different string than unpadded "SPY"). This is also WHY
    the 4 duplicate SPY-prefix parse sites flagged in WEEKLY-OPTIONS-PROGRAM.md §5
    (e.g. setup/scripts/atomic_bracket_guard.py's hardcoded `symbol[9]` side lookup) are
    wrong for 4-char roots -- the side character sits at a root-length-DEPENDENT index,
    never a fixed one. NOT fixed in this file (outside this workstream's file ownership
    for this build) -- flagged for whichever workstream owns those 4 sites.

    `root` is validated to 1-6 alphanumeric characters (the OSI field's real width cap)
    and upper-cased for consistency with SPY/GLD/QQQ/NVDA/TSLA/AAPL's own convention, via
    an assert -- matching this function's pre-existing `side` validation idiom, not a
    silent clamp or truncation.
    """
    yymmdd = trade_date.strftime("%y%m%d")
    s = side.upper()
    assert s in ("C", "P"), f"side must be C or P, got {side}"
    root_u = root.upper()
    assert root_u.isalnum() and 1 <= len(root_u) <= 6, (
        f"root must be 1-6 alphanumeric characters (OSI root field width), got {root!r}"
    )
    return f"{root_u}{yymmdd}{s}{int(round(strike)) * 1000:08d}"


def load_contract_bars(
    symbol: str, *, resolution: str = NATIVE_RESOLUTION, frame: Optional[str] = None
) -> Optional[pd.DataFrame]:
    """Load cached bars for a contract. Returns None if not cached.

    Results are stored in _CONTRACT_BAR_CACHE for the lifetime of the worker
    process — subsequent calls for the same symbol return the cached DataFrame
    without touching disk.

    `resolution` (added 2026-08-02, backward-compatible): EXPLICIT, LOGGED input instead of a
    silent default — see module docstring's RESOLUTION DISCLOSURE. Every existing call site
    (~250 across this codebase) calls this positionally with just `symbol`, which resolves to
    the SAME default ("5min") and the SAME on-disk data this function has always served — zero
    behavior change. Passing any value other than "5min" raises NotImplementedError: this
    function's cache is 5-minute-only and has never served another resolution; a caller wanting
    genuine 1-minute fidelity must fetch it itself (see
    backtest/tools/_option_bars_1min_cache.fetch_1min_cached) rather than receive a silent,
    wrong answer from here.

    `frame` (added 2026-08-02, DST-FRAME-BLAST-RADIUS-2026-08-02 — THE ROOT FIX deferred by
    that audit and completed here): controls the convention of the returned `timestamp_et`
    column.
      - frame=None (DEFAULT, UNCHANGED): returns the RAW tz-AWARE, fixed-offset column exactly
        as `pd.to_datetime` parses the CSV's embedded "-04:00" strings (the OPRA cache's actual
        on-disk convention — see et_frame.py's module docstring for why that offset label is
        wrong for EST months). Every pre-2026-08-02 SAFE caller (simulator_real.py,
        simulator_real_trailing.py) re-parses this tz-aware column itself via
        `et_frame.parse_timestamp_et(df["timestamp_et"], frame)` to get EITHER frame
        explicitly — frame=None preserves that contract byte-for-byte, zero behavior change,
        the same backward-compat precedent the `resolution` kwarg above already set.
      - frame="wall-v1" / frame="et-v2": returns an ALREADY-NORMALIZED, tz-NAIVE column in the
        stated et_frame convention (via et_frame.parse_timestamp_et), so a caller that wants a
        correct, unambiguous, EXPLICITLY-STATED result — rather than hand-rolling its own tz
        handling — gets one and cannot silently mis-join two frames. This is the actual
        mechanism DST-FRAME-BLAST-RADIUS-2026-08-02 found: a bare `.dt.tz_localize(None)` on
        this function's raw output is byte-identical to frame="wall-v1", but gives the caller
        no signal that it just made a frame CHOICE (silently, with no cross-check against
        whatever frame its OTHER timestamp series — e.g. the SPY entry time — is already in)
        rather than receiving "the" answer. New callers wanting a one-call, no-extra-import
        path to a correct join should pass this explicitly; exit_manager_walk.py /
        simulator_credit.py / simulator_debit.py route through `et_frame.parse_timestamp_et`
        directly instead (their existing call-site convention — see each file's own docstring)
        but both paths resolve through the SAME `et_frame.parse_timestamp_et`, never a second
        ad hoc implementation.

    Cache safety: the process-level _CONTRACT_BAR_CACHE always stores the RAW tz-aware parse
    (the frame=None shape) regardless of what `frame` any given call requests — frame
    normalization happens on a FRESH COPY after every cache hit/miss, never by mutating the
    cached object in place. Two callers requesting different frames for the same symbol in the
    same worker process therefore never see each other's shape (no cache poisoning), and the
    cache key stays `symbol` alone, matching every existing caller's assumption that
    load_contract_bars(symbol) alone determines the cache slot.
    """
    global _disclosed_default_resolution
    if resolution != NATIVE_RESOLUTION:
        raise NotImplementedError(
            f"load_contract_bars only ever serves resolution={NATIVE_RESOLUTION!r} "
            f"(backtest/data/options/*.csv, populated by fetch_option_data.py's hardcoded "
            f"timeframe='5Min') — got resolution={resolution!r}. This function does not fetch "
            f"or convert resolutions; use backtest/tools/_option_bars_1min_cache."
            f"fetch_1min_cached for 1-minute bars."
        )
    if not _disclosed_default_resolution:
        logger.info(
            "load_contract_bars: serving %s OPRA bars (the only resolution this cache holds) — "
            "intra-bar stop/TP touches that breach-and-recover within a bar are NOT resolved "
            "at this resolution (OPTION-BAR-RESOLUTION-BIAS-2026-08-02, measured $1,821.75 "
            "aggregate swing, one-directional, on the real-fills population). "
            "See markdown/infra/DATA-PROVENANCE.md. (Logged once per process.)",
            NATIVE_RESOLUTION,
        )
        _disclosed_default_resolution = True
    if symbol in _CONTRACT_BAR_CACHE:
        df = _CONTRACT_BAR_CACHE[symbol]
    else:
        path = CACHE_DIR / f"{symbol}.csv"
        if not path.exists():
            _CONTRACT_BAR_CACHE[symbol] = None
            df = None
        else:
            df = pd.read_csv(path)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
            _CONTRACT_BAR_CACHE[symbol] = df
    if df is None or frame is None:
        return df
    if frame not in (FRAME_WALL_V1, FRAME_ET_V2):
        raise ValueError(
            f"unknown timestamp frame {frame!r}; expected 'wall-v1' or 'et-v2' (or omit "
            f"frame entirely for the raw tz-aware column — see load_contract_bars' docstring)"
        )
    out = df.copy()
    out["timestamp_et"] = parse_timestamp_et(out["timestamp_et"], frame)
    return out


def bar_at_or_after(df: pd.DataFrame, when_et: dt.datetime) -> Optional[OptionBar]:
    """Return the first bar whose timestamp is >= when_et.

    The trigger bar in spy_df closes at e.g. 10:25:00. Entry would fill in the
    NEXT 5-min bar (10:25-10:30). We use that bar's VWAP as the entry proxy.
    """
    matches = df[df["timestamp_et"] >= when_et]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )


def bar_containing(df: pd.DataFrame, when_et: dt.datetime) -> Optional[OptionBar]:
    """Return the bar whose timestamp <= when_et < timestamp + 5 min."""
    when = pd.Timestamp(when_et)
    if when.tz is None and df["timestamp_et"].dt.tz is not None:
        when = when.tz_localize(df["timestamp_et"].dt.tz)
    cutoff = df[df["timestamp_et"] <= when]
    if cutoff.empty:
        return None
    row = cutoff.iloc[-1]
    if (when - row["timestamp_et"]).total_seconds() > 300:
        return None  # gap — no bar covers this time
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )


def quote_at_index(df: pd.DataFrame, idx: int) -> Optional[OptionBar]:
    """Direct index access for fast iteration in the simulator."""
    if idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )
