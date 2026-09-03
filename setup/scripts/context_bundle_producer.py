"""context_bundle_producer.py -- multi-timeframe TREND-ALIGNMENT context bundle (Phase 0).

WHY THIS EXISTS (J, 2026-07-14: "how are we properly reviewing previous day levels and
correlating them into our 'eyes' of the day and trends... do we cross-correlate any
information before acting on signals? maybe it should be calculated beforehand and tagged
onto the signal"). The audit (markdown plan, 2026-07-14) proved the live engine
cross-correlates prior-day LEVELS (key-levels.json, via heartbeat_core._read_levels) but
NEVER factors the multi-timeframe trend into whether/how strongly it acts -- the intraday
structure_veto only looks at TODAY's 5m bars (engine_cli._classify_sameday_5m). This
producer closes the "does daily/hourly/15m agree with the signal" gap J named, pre-computed
OFF the hot path (heavy multi-day correlation has no business running inline on a 1-min
heartbeat tick) and written to disk for heartbeat_core to read + TAG onto the decision row.

v1 SCOPE (J's explicit call, 2026-07-14): TREND ALIGNMENT ONLY. Macro/event proximity,
confluence-zone strength, and hard context-gating are pre-approved fast-follows, NOT this
phase -- start lean, prove the mechanism first (Phase 1 correlation study), before adding
more dimensions to the bundle.

PHASE 0 IS LOGGED-ONLY / ZERO-BEHAVIOR-CHANGE: heartbeat_core.py tags this bundle onto
bar_ctx + the decision row for VISIBILITY only. Nothing on the decision path (score_bar,
evaluate_gates, _derive_tier) reads it this phase. See heartbeat_core._read_context_bundle
+ the "context_bundle" keys in _build_payload / run_account, and the RED-proof guard test
backtest/tests/test_context_bundle_tag_no_behavior_change.py.

STRUCTURE PRIMITIVE: reuses crypto/lib/market_structure.py::analyze_structure -- the SAME
swing-sequence structure read the LIVE structure_veto gate already runs on today's 5m bars
via engine_cli._classify_sameday_5m (backtest/lib/engine/engine_cli.py:173-205). This module
mirrors that exact bars-list-of-dicts -> crypto.lib.bar.Bar -> analyze_structure conversion,
just across 3 higher timeframes instead of one intraday one.

PHASE 1 REUSE (amendment, 2026-07-14): `compute_trend_alignment` is AS-OF-BOUNDED and pure
by construction -- it has no notion of "now", only of whatever rows the caller's DataFrames
contain. Phase 1's walk-forward correlation study will fetch daily/hourly/15m history ONCE
and call this SAME function per historical decision timestamp T on bars sliced to <=T, with
zero look-ahead (C6) and zero re-derivation of the math. See compute_trend_alignment's own
docstring for the full contract + the guard test that proves it.

EXTENSION (2026-07-15, J's direct ask: "review the new labels... that involve current real
world events and prior day technical analysis"): the two pre-approved fast-follow dimensions
from the v1 scope note above -- macro/event proximity and prior-day/levels context -- ship
here, same discipline exactly, still LOGGED ONLY, still zero new heartbeat_core.py reads (it
already tags the WHOLE bundle dict verbatim -- any key added here rides along for free):

  `events`         -- from automation/state/macro-calendar.json (events_30d + no_trade_window_
                       rules) + news.json (freshness only). Pure date/time arithmetic against
                       `now_et` -- next/last event, minutes-to/-since, whether today's mechanical
                       no-trade window is active right now, and whether news.json is stale
                       relative to Gamma_MacroCalendar's daily 07:45 ET weekday fire (honest-
                       degraded with a reason string, never guessed). Reuses
                       `macro_calendar.compute_no_trade_windows` verbatim -- the SAME no-trade-
                       window math premarket's daily digest already uses -- rather than
                       re-deriving it a second time.
  `prior_day`      -- prior COMPLETE trading day's OHLC, read off the SAME daily_df already
                       fetched for trend_alignment (no new daily fetch).
  `today_context`  -- gap_pct_at_open, position_in_prior_range, the 60-min (09:30-10:30 ET)
                       opening range, and rvol_session_so_far (today's RTH cumulative volume
                       vs the median of the same elapsed-time-of-day cumulative volume across
                       the last 20 trading days). Needs finer/longer intraday history than the
                       existing hourly/m15 fetches carry, so this extension adds ONE new fetch
                       (`5Min`, ~35 calendar days back) -- the daily/hourly/m15 fetches that
                       feed trend_alignment are completely untouched (same days_back/limit as
                       Phase 0, so that dimension's read is byte-for-byte unaffected).
  `levels_context` -- nearest active (non-expired) key-levels.json level above/below the latest
                       available price, plus a count within 1%. Local expiry-date compare
                       mirrors heartbeat_core._level_expired's convention but is NOT shared code
                       (kept self-contained in this file per "one producer, one file").

Every new field is null-with-reason when its inputs are missing/stale/not-yet-available (e.g.
`or_high`/`or_low` are null before 10:30 ET by design, not by failure) -- see each compute_*
function's own docstring for its exact reasons. A bug in any ONE new dimension is isolated
(try/except per dimension in main()) so it degrades that dimension only, never blanks out
Phase 0's trend_alignment or crashes the whole producer.

GRADING PATH (spec only, not built here -- pins the eval-first path per CLAUDE.md OP-11):
same pattern that graded (and KILLed) Phase 1's trend-alignment dimension applies to `events`
and `prior_day`/`today_context`/`levels_context` once enough decision rows have this bundle
attached: a correlation-scorer script (backtest/tools/context_dimension_correlation_study.py,
not yet built) would replay core-decisions.jsonl rows that carry a non-null value for the
dimension under test, bucket by that value (e.g. no_trade_window_active True/False, or
position_in_prior_range deciles, or rvol_session_so_far bands), and score realized trade
P&L/expectancy per bucket against the OP-16 battery (OOS+, WF>=0.70, sub-window-stable,
anchor-no-regression) -- EXACTLY the bar trend_alignment's Phase 1 study will need to clear
before ANY dimension here is allowed to move from LOGGED to CONSUMED on the decision path.
No dimension added in this file may be wired into score/gates/_derive_tier without that
scorecard filed first, per the same eval-first gate OP-11 already requires.

MODES:
  `python context_bundle_producer.py`         -- write automation/state/context-bundle.json,
                                                   print a one-line summary (scheduled-task
                                                   cadence: Gamma_ContextBundle, every 5 min RTH).
  `python context_bundle_producer.py --once`  -- same write, PLUS the full bundle JSON printed
                                                   to stdout (manual verification / --once fires).

FAIL-OPEN: any timeframe fetch failure degrades that timeframe to unavailable (never crashes,
never fabricates a trend) and sets the bundle's top-level `degraded: true` + `degraded_reason`.
$0, pure Python + pandas, no LLM, no TradingView MCP -- direct Alpaca REST (same un-blockable
path as heartbeat_core._fetch_spy_5m / sight_beacon.py).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "context-bundle-producer.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "context-bundle-producer.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import statistics
import sys
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
# so `crypto.lib.*` (PEP-420 namespace package, no crypto/__init__.py) resolves,
# and `et_clock` (bare module in this same directory) resolves whether this file is
# run directly or loaded by path via importlib (heartbeat_core.py's own convention).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from et_clock import et_now as _et_now  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import DEFAULT_WINDOW, analyze_structure  # noqa: E402
from macro_calendar import compute_no_trade_windows  # noqa: E402 -- reused verbatim, not re-derived

STATE = REPO / "automation" / "state"
OUT_F = STATE / "context-bundle.json"

MIN_BARS = 10   # below this, a timeframe's structure read is noise, not signal -- unavailable
VOTE = {"uptrend": 1, "downtrend": -1, "range": 0, "unknown": 0}

# ----- EXTENSION (2026-07-15): events + prior-day/today-context + levels_context knobs -----
ET_ZONE = "America/New_York"
RTH_OPEN = dt_time(9, 30)
RTH_CLOSE = dt_time(16, 0)
OR_WINDOW_END = dt_time(10, 30)            # 60-min opening range: 09:30-10:30 ET (J's spec)
RVOL_LOOKBACK_TRADING_DAYS = 20            # median cumulative-volume-so-far lookback
RVOL_MIN_HISTORY_DAYS = 5                  # below this the median is too thin to trust -- null
LEVEL_PROXIMITY_PCT = 0.01                 # "within 1%" band for levels_context.n_levels_within_1pct
MACRO_CALENDAR_FIRE_ET = dt_time(7, 45)    # Gamma_MacroCalendar's daily weekday cadence
CALENDAR_STALE_SLACK_MIN = 30              # grace past the expected fire before flagging stale


# ----- pure math: the single source of truth Phase 1's scorer will import -----------------
def _df_to_bars(df: "pd.DataFrame | None", granularity_seconds: int, source: str) -> list[Bar]:
    """DataFrame(timestamp, open, high, low, close, volume) -> list[Bar], oldest first.

    PURE (no I/O). Skips any row that fails to convert (NaN OHLC, bad timestamp, high<low)
    rather than raising -- callers treat a short/empty result as 'insufficient data'."""
    out: list[Bar] = []
    if df is None or len(df) == 0:
        return out
    for _, row in df.iterrows():
        try:
            ts = row["timestamp"]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            v = float(row["volume"]) if row.get("volume") == row.get("volume") else 0.0
            if any(x != x for x in (o, h, l, c)):  # NaN check (x != x is True only for NaN)
                continue
            out.append(Bar(open_time=ts, open=o, high=h, low=l, close=c, volume=v,
                            granularity_seconds=granularity_seconds, source=source))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda b: b.open_time)
    return out


def _tf_state(df: "pd.DataFrame | None", *, source: str, granularity_seconds: int,
              window: int, min_bars: int) -> dict:
    """PURE: one timeframe's df -> a JSON-serializable trend-state dict. Never raises --
    any conversion/structure-read failure degrades to trend='unknown', available=False."""
    bars = _df_to_bars(df, granularity_seconds, source)
    if len(bars) < min_bars:
        return {"trend": "unknown", "confidence": 0.0, "trend_basis": "insufficient",
                "available": False, "n_bars": len(bars), "reason": "insufficient_bars"}
    try:
        read = analyze_structure(bars, window=window)
    except Exception as e:  # noqa: BLE001 -- a structure-read bug must degrade, never crash the bundle
        return {"trend": "unknown", "confidence": 0.0, "trend_basis": "insufficient",
                "available": False, "n_bars": len(bars),
                "reason": f"analyze_structure_error: {type(e).__name__}"}
    return {"trend": read.trend, "confidence": round(float(read.confidence), 4),
            "trend_basis": read.trend_basis, "available": True, "n_bars": len(bars), "reason": None}


def compute_trend_alignment(daily_df: "pd.DataFrame | None", hourly_df: "pd.DataFrame | None",
                             m15_df: "pd.DataFrame | None", *, window: int = DEFAULT_WINDOW,
                             min_bars: int = MIN_BARS) -> dict:
    """PURE, side-effect-free, single source of truth for the trend-alignment math -- Phase 1's
    correlation scorer imports this SAME function so the walk-forward replay and the live
    producer can never drift apart. Does NO I/O; every input is a plain OHLCV DataFrame
    (columns: timestamp, open, high, low, close, volume) the caller already fetched.

    Runs crypto.lib.market_structure.analyze_structure on each of the 3 timeframes -- the
    SAME structure primitive the live structure_veto gate already runs on today's 5m bars
    (engine_cli._classify_sameday_5m) -- to get an up/down/range/unknown trend + a heuristic
    confidence per timeframe.

    SCORING CONVENTION (documented here because it's the one thing every consumer must agree
    on): each timeframe casts a vote -- +1 if its trend is 'uptrend', -1 if 'downtrend', 0 if
    'range'/'unknown'/unavailable (no data, insufficient bars, or a fetch that never arrived).
    `alignment_score` = sum of the 3 votes, an integer in [-3, +3].
      SIGN      = net directional lean: positive = net-bullish stack, negative = net-bearish
                  stack, zero = no net lean (either all-range/unknown, or the up/down votes
                  cancel).
      MAGNITUDE = strength of STACKED agreement: +/-3 means all 3 available timeframes agree
                  in the same direction (full alignment); +/-1 is ambiguous by construction --
                  it can mean "only 1 TF has a directional read" OR "2-vs-1 mixed" (e.g. daily
                  up + hourly down + 15m up nets to +1, which is NOT full alignment). Use
                  `trend_alignment` below for the strict per-direction read, not the score alone.

    `trend_alignment.bull.aligned` is True iff EVERY available timeframe read 'uptrend' (and
    at least one timeframe was available) -- the literal answer to J's question "do
    daily/hourly/15m agree with a bull signal?" `trend_alignment.bear` mirrors it for
    'downtrend'. A timeframe that's unavailable (no data) is excluded from the agree/disagree
    count on EITHER side -- it never manufactures false alignment.

    Returns a dict: {per_tf: {daily, hourly, m15}, alignment_score, trend_alignment,
    degraded, degraded_reasons}. `degraded` here means >=1 timeframe was unavailable to THIS
    function (insufficient/malformed data it was handed) -- distinct from main()'s top-level
    `degraded`, which also folds in upstream FETCH failures (network/auth) the pure function
    never sees.

    AS-OF-BOUNDED / NO-LOOK-AHEAD CONTRACT (load-bearing for Phase 1, added 2026-07-14): this
    function has NO notion of "now" or "latest" anywhere in its body or call chain (_tf_state,
    _df_to_bars, crypto.lib.market_structure.analyze_structure, classify_trend,
    find_swing_points are all pure over whatever rows the caller hands them). The result for a
    given set of input DataFrames depends ONLY on the rows those DataFrames contain -- it is
    a pure function of its arguments, full stop. Concretely: if the caller truncates
    daily_df/hourly_df/m15_df to rows with timestamp <= T before calling this function, the
    returned alignment is EXACTLY what would have been computed live at T -- appending more
    rows (bars from AFTER T) to any of the 3 DataFrames and re-calling with the truncated
    (<=T) slice again reproduces the identical result, byte for byte. This is what makes the
    function directly reusable, unmodified, for Phase 1's walk-forward historical replay
    (`backtest/tools/trend_alignment_correlation_study.py`, not yet built): fetch daily/
    hourly/15m history ONCE, then for each historical decision timestamp T, slice each
    DataFrame to `df[df.timestamp <= T]` and call this same function -- never re-derive the
    math, never let a live-only shortcut creep in. `main()` below is the ONLY place that
    reaches for "now" (via `_et_now()`/`datetime.now()`, purely for the fetch window and the
    `computed_at_et` timestamp) -- that code never executes inside this function. Guard:
    test_context_bundle_producer.py::test_compute_trend_alignment_is_as_of_bounded_no_lookahead.
    """
    per_tf = {
        "daily": _tf_state(daily_df, source="spy_daily", granularity_seconds=86400,
                            window=window, min_bars=min_bars),
        "hourly": _tf_state(hourly_df, source="spy_hourly", granularity_seconds=3600,
                             window=window, min_bars=min_bars),
        "m15": _tf_state(m15_df, source="spy_15m", granularity_seconds=900,
                          window=window, min_bars=min_bars),
    }
    votes = {tf: (VOTE.get(st["trend"], 0) if st["available"] else 0) for tf, st in per_tf.items()}
    alignment_score = int(sum(votes.values()))

    available_tfs = [tf for tf, st in per_tf.items() if st["available"]]
    bull_agree = [tf for tf in available_tfs if per_tf[tf]["trend"] == "uptrend"]
    bear_agree = [tf for tf in available_tfs if per_tf[tf]["trend"] == "downtrend"]
    trend_alignment = {
        "bull": {"agreeing_timeframes": bull_agree, "agree_count": len(bull_agree),
                 "available_count": len(available_tfs),
                 "aligned": bool(available_tfs) and len(bull_agree) == len(available_tfs)},
        "bear": {"agreeing_timeframes": bear_agree, "agree_count": len(bear_agree),
                 "available_count": len(available_tfs),
                 "aligned": bool(available_tfs) and len(bear_agree) == len(available_tfs)},
    }
    degraded_reasons = [f"{tf}: {st['reason']}" for tf, st in per_tf.items() if not st["available"]]
    return {
        "per_tf": per_tf,
        "alignment_score": alignment_score,
        "trend_alignment": trend_alignment,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }


# ============================================================================================
# EXTENSION (2026-07-15): events + prior-day/today-context + levels_context -- all PURE,
# same discipline as compute_trend_alignment above (no I/O, never raises, null-with-reason).
# ============================================================================================
def _add_et_columns(df: "pd.DataFrame | None") -> "pd.DataFrame":
    """Non-mutating: df (UTC-aware `timestamp` col) -> copy with `et_date` (str 'YYYY-MM-DD')
    + `et_time` (datetime.time) columns. Empty/None -> empty df, never raises."""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    out = df.copy()
    et_ts = out["timestamp"].dt.tz_convert(ET_ZONE)
    out["et_date"] = et_ts.dt.strftime("%Y-%m-%d")
    out["et_time"] = et_ts.dt.time
    return out


def _latest_close(*dfs: "pd.DataFrame | None") -> "float | None":
    """Most-recent close across any provided non-empty DataFrames -- the finest-available
    'current price' proxy this producer has (no live-quote fetch; a 5-min-cadence producer
    off the hot path has no need for tick-level precision). None if every df is empty."""
    best_ts, best_close = None, None
    for df in dfs:
        if df is None or len(df) == 0:
            continue
        row = df.sort_values("timestamp").iloc[-1]
        ts = row["timestamp"]
        if best_ts is None or ts > best_ts:
            best_ts, best_close = ts, float(row["close"])
    return best_close


# ----- events (macro-calendar.json + news.json) --------------------------------------------
def _event_dt(ev: dict) -> "datetime | None":
    """event's (date, time_et) -> naive ET datetime, matching et_now()'s naive-ET convention.
    None on any malformed event row -- never raises."""
    try:
        hh, mm = (int(x) for x in str(ev["time_et"]).split(":"))
        return datetime.strptime(ev["date"], "%Y-%m-%d").replace(hour=hh, minute=mm)
    except (KeyError, TypeError, ValueError):
        return None


def _calendar_staleness(news: "dict | None", *, now_et: datetime) -> tuple[bool, "str | None"]:
    """True/reason iff news.json's freshness_stamp is older than the most recent expected
    Gamma_MacroCalendar fire (weekdays 07:45 ET) minus a slack window. Honest-degraded: a
    missing/malformed news.json is ALWAYS stale (never silently treated as fresh); a fresh
    file dated before today's 07:45-ET fire simply hasn't happened yet is NOT flagged stale --
    the most recent expected fire is the correct anchor, not "today" unconditionally."""
    if news is None:
        return True, "news.json missing or malformed"
    stamp = news.get("freshness_stamp") or news.get("as_of")
    if not stamp:
        return True, "news.json has no freshness_stamp/as_of field"
    try:
        stamp_dt = datetime.fromisoformat(str(stamp))
    except ValueError:
        return True, f"unparseable freshness_stamp: {stamp!r}"
    if stamp_dt.tzinfo is not None:
        stamp_dt = stamp_dt.replace(tzinfo=None)  # news.json stamps are naive-ET (et_now().isoformat())

    today_fire = now_et.replace(hour=7, minute=45, second=0, microsecond=0)
    if now_et.weekday() >= 5:  # "now" itself falls on a weekend -- anchor to last Friday's fire
        expected = today_fire - timedelta(days=now_et.weekday() - 4)
    elif now_et < today_fire:
        # before today's fire -- anchor to the LAST prior weekday's fire (Monday -> Friday)
        expected = today_fire - timedelta(days=3 if now_et.weekday() == 0 else 1)
    else:
        expected = today_fire
    threshold = expected - timedelta(minutes=CALENDAR_STALE_SLACK_MIN)
    if stamp_dt < threshold:
        age_h = (now_et - stamp_dt).total_seconds() / 3600.0
        return True, (f"freshness_stamp {stamp_dt.isoformat()} predates the expected "
                       f"{expected.isoformat()} ET fire (~{age_h:.1f}h old)")
    return False, None


def compute_events_context(calendar: "dict | None", news: "dict | None", *,
                            now_et: datetime) -> dict:
    """PURE (no I/O -- calendar/news are already-loaded dicts). Next/last macro event pointers,
    today's mechanical no-trade-window state, and news.json staleness -- all derived from
    macro-calendar.json#events_30d + #no_trade_window_rules via `_event_dt` + the imported
    `compute_no_trade_windows` (verbatim reuse of macro_calendar.py's own math, never
    re-derived). Every field null-with-reason when calendar/news is missing or has no usable
    events -- never fabricates a date."""
    if not calendar or not isinstance(calendar.get("events_30d"), list):
        stale, stale_reason = _calendar_staleness(news, now_et=now_et)
        return {
            "next_event_name": None, "next_event_et": None, "minutes_to_next_event": None,
            "next_event_severity": None, "last_event_name": None, "minutes_since_last_event": None,
            "no_trade_window_active": False, "active_windows": [], "todays_windows": [],
            "calendar_stale": stale, "calendar_stale_reason": stale_reason or "macro-calendar.json missing/malformed",
        }

    dated = sorted(((_event_dt(ev), ev) for ev in calendar["events_30d"]),
                    key=lambda pair: pair[0] or datetime.max)
    dated = [(d, ev) for d, ev in dated if d is not None]
    future = [(d, ev) for d, ev in dated if d >= now_et]
    past = [(d, ev) for d, ev in dated if d < now_et]
    next_ev = future[0] if future else None
    last_ev = past[-1] if past else None

    today_str = now_et.strftime("%Y-%m-%d")
    events_today = [ev for d, ev in dated if ev.get("date") == today_str]
    rules = calendar.get("no_trade_window_rules") or {}
    todays_windows = compute_no_trade_windows(events_today, rules)
    now_hm = now_et.hour * 60 + now_et.minute
    active_windows = []
    for w in todays_windows:
        try:
            sh, sm = (int(x) for x in w["start_et"].split(":"))
            eh, em = (int(x) for x in w["end_et"].split(":"))
        except (KeyError, ValueError):
            continue
        if sh * 60 + sm <= now_hm <= eh * 60 + em:
            active_windows.append(w)

    calendar_stale, stale_reason = _calendar_staleness(news, now_et=now_et)
    return {
        "next_event_name": next_ev[1].get("event") if next_ev else None,
        "next_event_et": f"{next_ev[1].get('time_et')} ET {next_ev[1].get('date')}" if next_ev else None,
        "minutes_to_next_event": round((next_ev[0] - now_et).total_seconds() / 60.0, 1) if next_ev else None,
        "next_event_severity": next_ev[1].get("severity") if next_ev else None,
        "last_event_name": last_ev[1].get("event") if last_ev else None,
        "minutes_since_last_event": round((now_et - last_ev[0]).total_seconds() / 60.0, 1) if last_ev else None,
        "no_trade_window_active": bool(active_windows),
        "active_windows": active_windows,
        "todays_windows": todays_windows,
        "calendar_stale": calendar_stale,
        "calendar_stale_reason": stale_reason,
    }


# ----- prior_day (reuses the SAME daily_df trend_alignment already fetches) ----------------
def compute_prior_day(daily_df: "pd.DataFrame | None", *, today_et_date: str) -> dict:
    """PURE. The most recent daily bar strictly BEFORE today_et_date -- the prior COMPLETE
    trading day's OHLC (excludes today's own possibly-still-forming daily bar). Reuses the
    SAME daily_df Phase 0 already fetches (~190 days back) -- no new fetch. Null-with-reason
    if daily_df is empty/unavailable or genuinely has no row before today (e.g. day 1)."""
    d = _add_et_columns(daily_df)
    if len(d) == 0:
        return {"prior_close": None, "prior_high": None, "prior_low": None,
                "prior_range": None, "prior_date": None, "reason": "no_daily_data"}
    prior_rows = d[d["et_date"] < today_et_date].sort_values("et_date")
    if len(prior_rows) == 0:
        return {"prior_close": None, "prior_high": None, "prior_low": None,
                "prior_range": None, "prior_date": None, "reason": "no_prior_trading_day_in_window"}
    row = prior_rows.iloc[-1]
    high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
    return {"prior_close": round(close, 2), "prior_high": round(high, 2), "prior_low": round(low, 2),
            "prior_range": round(high - low, 2), "prior_date": row["et_date"], "reason": None}


# ----- today_context: gap/position/opening-range/rvol (needs the NEW 5-min fetch) ----------
def compute_rvol_session_so_far(five_min_df: "pd.DataFrame | None", *, now_et: datetime,
                                 lookback_days: int = RVOL_LOOKBACK_TRADING_DAYS,
                                 min_history_days: int = RVOL_MIN_HISTORY_DAYS
                                 ) -> tuple["float | None", "str | None"]:
    """PURE. today's RTH cumulative volume from 09:30 ET through now's time-of-day, divided
    by the MEDIAN of the same elapsed-time-of-day cumulative volume across the last
    `lookback_days` trading days present in five_min_df. Causal by construction (only ever
    sums bars with et_time <= now's time-of-day, on each day independently -- never reads a
    later bar on any day, including today). Null-with-reason when there isn't enough same-
    day-so-far data yet (premarket) or too few historical days to trust a median."""
    d = _add_et_columns(five_min_df)
    if len(d) == 0:
        return None, "no_intraday_data"
    rth = d[(d["et_time"] >= RTH_OPEN) & (d["et_time"] < RTH_CLOSE)]
    if len(rth) == 0:
        return None, "no_rth_bars_in_fetch_window"

    today_str = now_et.strftime("%Y-%m-%d")
    cutoff = now_et.time()
    today_rows = rth[(rth["et_date"] == today_str) & (rth["et_time"] <= cutoff)]
    if len(today_rows) == 0:
        return None, "no_rth_bars_for_today_yet"
    today_cum_vol = float(today_rows["volume"].sum())

    hist_days = sorted(dd for dd in rth["et_date"].unique() if dd < today_str)[-lookback_days:]
    cum_vols = []
    for dd in hist_days:
        day_rows = rth[(rth["et_date"] == dd) & (rth["et_time"] <= cutoff)]
        if len(day_rows) > 0:
            cum_vols.append(float(day_rows["volume"].sum()))
    if len(cum_vols) < min_history_days:
        return None, f"insufficient_history_only_{len(cum_vols)}_of_{min_history_days}_min_days"

    median_vol = statistics.median(cum_vols)
    if median_vol <= 0:
        return None, "median_historical_volume_is_zero"
    return round(today_cum_vol / median_vol, 3), None


def compute_today_context(five_min_df: "pd.DataFrame | None", prior_day: dict, *,
                           now_et: datetime) -> dict:
    """PURE. gap_pct_at_open (today's RTH open vs prior_day close), position_in_prior_range
    (latest price's percentile of yesterday's H/L), the 60-min opening range (09:30-10:30 ET,
    null before 10:30 by DESIGN, not failure), and rvol_session_so_far. `prior_day` is the
    dict compute_prior_day() already returned -- never re-fetched, never re-derived."""
    d = _add_et_columns(five_min_df)
    today_str = now_et.strftime("%Y-%m-%d")
    today_rows = d[d["et_date"] == today_str] if len(d) else d
    rth_today = today_rows[today_rows["et_time"] >= RTH_OPEN] if len(today_rows) else today_rows

    if len(rth_today) == 0:
        today_open, gap_pct, gap_reason = None, None, "no_rth_bars_for_today_yet"
    else:
        today_open = float(rth_today.sort_values("timestamp").iloc[0]["open"])
        prior_close = prior_day.get("prior_close")
        if prior_close:
            gap_pct, gap_reason = round((today_open - prior_close) / prior_close * 100.0, 3), None
        else:
            gap_pct, gap_reason = None, "no_prior_close_available"

    # GAP-REASON-SESSION-OPEN-FALLBACK (queue.md, filed 2026-07-20, closed 2026-09-03):
    # at the very session open (or on any fetch-lag tick before today's first bar has
    # landed), `five_min_df`'s newest row can still be YESTERDAY's last bar -- so
    # `_latest_close` silently returns yesterday's close as "latest_price" with no
    # reason recorded, unlike `gap_reason`/`rvol_reason` above which both already flag
    # this exact same "no today bars yet" condition explicitly. Confirmed live
    # 2026-07-20 ~09:34 ET: a decision row carried spy=743.28 == prior-session-close
    # under gap_reason="no_rth_bars_for_today_yet", while position_in_prior_range was
    # silently computed against that same stale carryover price with reason=None.
    # Surface the fallback explicitly instead of a silent default: when the newest row
    # in the whole (not just today-filtered) frame isn't from today, latest_price is a
    # stale prior-session carryover, not a real "latest" read.
    latest_is_stale_prior_session = False
    if len(d):
        newest_et_date = d.sort_values("timestamp").iloc[-1]["et_date"]
        latest_is_stale_prior_session = newest_et_date != today_str

    latest_price = _latest_close(five_min_df)
    prior_high, prior_low = prior_day.get("prior_high"), prior_day.get("prior_low")
    if latest_price is not None and latest_is_stale_prior_session:
        position, position_reason = None, "latest_price_is_stale_prior_session_no_today_bars_yet"
    elif latest_price is not None and prior_high is not None and prior_low is not None:
        rng = prior_high - prior_low
        if rng > 0:
            position, position_reason = round((latest_price - prior_low) / rng, 4), None
        else:
            position, position_reason = None, "prior_range_zero_width"
    else:
        position, position_reason = None, "missing_latest_price_or_prior_range"

    if now_et.time() < OR_WINDOW_END:
        or_high, or_low, or_reason = None, None, "before_10:30_et_opening_range_not_yet_formed"
    elif len(rth_today) == 0:
        or_high, or_low, or_reason = None, None, "no_rth_bars_for_today"
    else:
        or_rows = rth_today[rth_today["et_time"] < OR_WINDOW_END]
        if len(or_rows) == 0:
            or_high, or_low, or_reason = None, None, "no_bars_in_opening_range_window"
        else:
            or_high = round(float(or_rows["high"].max()), 2)
            or_low = round(float(or_rows["low"].min()), 2)
            or_reason = None

    rvol, rvol_reason = compute_rvol_session_so_far(five_min_df, now_et=now_et)
    return {
        "today_open": round(today_open, 2) if today_open is not None else None,
        "gap_pct_at_open": gap_pct, "gap_reason": gap_reason,
        "position_in_prior_range": position, "position_reason": position_reason,
        "or_high": or_high, "or_low": or_low, "or_reason": or_reason,
        "rvol_session_so_far": rvol, "rvol_reason": rvol_reason,
    }


# ----- levels_context (key-levels.json) -----------------------------------------------------
def compute_levels_context(key_levels: "dict | None", *, latest_price: "float | None",
                            today_et_date: str) -> dict:
    """PURE. Nearest active (non-expired) key-levels.json level above/below latest_price, plus
    a count within LEVEL_PROXIMITY_PCT. Expiry compare mirrors heartbeat_core._level_expired's
    convention (date-string compare against today_et_date) but is intentionally NOT shared
    code -- kept self-contained in this file per "one producer, one file"."""
    if not key_levels or not isinstance(key_levels.get("levels"), list):
        return {"nearest_level_above": None, "nearest_level_below": None,
                "n_levels_within_1pct": None, "reason": "key-levels.json missing/malformed"}
    if latest_price is None:
        return {"nearest_level_above": None, "nearest_level_below": None,
                "n_levels_within_1pct": None, "reason": "no_current_price_available"}

    active = []
    for lv in key_levels["levels"]:
        price = lv.get("price")
        if not isinstance(price, (int, float)):
            continue
        exp = lv.get("expires_at")
        if isinstance(exp, str) and len(exp) >= 10 and exp[:10] < today_et_date:
            continue  # expired on a prior ET day -- fail-open on bad/absent date (keep the level)
        active.append({"price": float(price), "label": lv.get("label"),
                        "source": lv.get("source") or lv.get("role") or lv.get("type")})

    above = sorted((lv for lv in active if lv["price"] > latest_price), key=lambda lv: lv["price"])
    below = sorted((lv for lv in active if lv["price"] < latest_price), key=lambda lv: -lv["price"])
    nearest_above = ({"price": above[0]["price"], "distance": round(above[0]["price"] - latest_price, 2),
                       "source": above[0]["source"]} if above else None)
    nearest_below = ({"price": below[0]["price"], "distance": round(latest_price - below[0]["price"], 2),
                       "source": below[0]["source"]} if below else None)
    band = latest_price * LEVEL_PROXIMITY_PCT
    n_within = sum(1 for lv in active if abs(lv["price"] - latest_price) <= band)
    return {"nearest_level_above": nearest_above, "nearest_level_below": nearest_below,
            "n_levels_within_1pct": n_within, "reason": None}


# ----- I/O: fetch + write (kept OUT of the pure function above) ---------------------------
def _load_alpaca_creds() -> tuple[str, str]:
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def _fetch_bars(timeframe: str, *, days_back: int, limit: int) -> tuple[pd.DataFrame, "str | None"]:
    """SPY OHLCV via direct Alpaca REST -- same un-blockable path as heartbeat_core's
    _fetch_spy_5m / sight_beacon.py (never TradingView MCP; off the hot path here, but the
    credential + request shape is identical so a stale key fails the same way everywhere).
    Returns (df, error). df is empty and error is a short string on ANY failure -- NEVER
    raises, so a single bad timeframe degrades that timeframe only (see main())."""
    try:
        import urllib.request
        key, sec = _load_alpaca_creds()
        start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe={timeframe}&start={start}"
               f"&limit={limit}&feed=iex&adjustment=raw&sort=asc")
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=15) as r:
            bars = json.loads(r.read()).get("bars", [])
        if not bars:
            return pd.DataFrame(), f"{timeframe}: empty bars response"
        df = pd.DataFrame([{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                           "close": b["c"], "volume": b["v"]} for b in bars])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.reset_index(drop=True), None
    except Exception as e:  # noqa: BLE001 -- fetch failure must degrade, never crash the producer
        return pd.DataFrame(), f"{timeframe}: {type(e).__name__}: {e}"


def _load_json_or_none(path: Path) -> "dict | None":
    """Fail-open JSON read -- missing/unreadable/malformed -> None (never raises). Mirrors
    heartbeat_core._read_context_bundle's own try/except shape."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    """Fetch daily(~6mo)/hourly(~3wk)/15m(~5d)/5min(~35d) SPY bars + macro-calendar.json /
    news.json / key-levels.json, compute the trend-alignment bundle PLUS the events /
    prior_day / today_context / levels_context dimensions (2026-07-15 extension), write
    automation/state/context-bundle.json. Always returns 0 (fail-open) -- a failed fetch/read
    degrades only the dimension(s) it feeds (each wrapped in its own try/except below) plus
    the bundle's top-level `degraded`; it never aborts the write -- heartbeat_core must always
    find a bundle (possibly degraded) to read."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                     help="single run (the only mode this script has); also prints the full "
                          "bundle JSON to stdout for manual verification")
    args = ap.parse_args()

    now_et = _et_now()

    try:
        daily_df, daily_err = _fetch_bars("1Day", days_back=190, limit=200)
        hourly_df, hourly_err = _fetch_bars("1Hour", days_back=25, limit=500)
        m15_df, m15_err = _fetch_bars("15Min", days_back=7, limit=500)
        # NEW (2026-07-15): a separate, longer/finer intraday fetch for today_context (opening
        # range + rvol need >=20 trading days of RTH 5-min bars) -- deliberately NOT reused for
        # trend_alignment's m15 read above, so that dimension's fetch params (and therefore its
        # output) stay byte-for-byte untouched by this extension.
        five_min_df, five_min_err = _fetch_bars("5Min", days_back=35, limit=4000)

        result = compute_trend_alignment(daily_df, hourly_df, m15_df)
        fetch_errors = [e for e in (daily_err, hourly_err, m15_err) if e]
        reasons = fetch_errors + result["degraded_reasons"]

        # ---- 2026-07-15 extension dimensions: each isolated in its own try/except so a bug
        # in ONE never blanks out trend_alignment or crashes the whole producer. ----
        today_str = now_et.strftime("%Y-%m-%d")

        try:
            calendar = _load_json_or_none(STATE / "macro-calendar.json")
            news = _load_json_or_none(STATE / "news.json")
            events = compute_events_context(calendar, news, now_et=now_et)
        except Exception as e:  # noqa: BLE001
            events = {"next_event_name": None, "next_event_et": None, "minutes_to_next_event": None,
                      "next_event_severity": None, "last_event_name": None, "minutes_since_last_event": None,
                      "no_trade_window_active": False, "active_windows": [], "todays_windows": [],
                      "calendar_stale": True, "calendar_stale_reason": f"events_context_error: {type(e).__name__}: {e}"}
            reasons.append(f"events: {type(e).__name__}: {e}")

        try:
            prior_day = compute_prior_day(daily_df, today_et_date=today_str)
        except Exception as e:  # noqa: BLE001
            prior_day = {"prior_close": None, "prior_high": None, "prior_low": None,
                         "prior_range": None, "prior_date": None,
                         "reason": f"prior_day_error: {type(e).__name__}: {e}"}
            reasons.append(f"prior_day: {type(e).__name__}: {e}")
        if prior_day.get("reason"):
            reasons.append(f"prior_day: {prior_day['reason']}")

        try:
            today_context = compute_today_context(five_min_df, prior_day, now_et=now_et)
        except Exception as e:  # noqa: BLE001
            today_context = {"today_open": None, "gap_pct_at_open": None,
                             "gap_reason": f"today_context_error: {type(e).__name__}: {e}",
                             "position_in_prior_range": None, "position_reason": None,
                             "or_high": None, "or_low": None, "or_reason": None,
                             "rvol_session_so_far": None, "rvol_reason": None}
            reasons.append(f"today_context: {type(e).__name__}: {e}")
        if five_min_err:
            reasons.append(five_min_err)

        try:
            key_levels = _load_json_or_none(STATE / "key-levels.json")
            latest_price = _latest_close(five_min_df, m15_df, hourly_df, daily_df)
            levels_context = compute_levels_context(key_levels, latest_price=latest_price,
                                                      today_et_date=today_str)
        except Exception as e:  # noqa: BLE001
            levels_context = {"nearest_level_above": None, "nearest_level_below": None,
                              "n_levels_within_1pct": None,
                              "reason": f"levels_context_error: {type(e).__name__}: {e}"}
            reasons.append(f"levels_context: {type(e).__name__}: {e}")

        degraded = bool(reasons)

        bundle = {
            "schema_version": 2,
            "computed_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
            "per_tf": result["per_tf"],
            "trend_alignment": result["trend_alignment"],
            "alignment_score": result["alignment_score"],
            "events": events,
            "prior_day": prior_day,
            "today_context": today_context,
            "levels_context": levels_context,
            "degraded": degraded,
            "degraded_reason": "; ".join(reasons) if reasons else None,
            "note": "TREND ALIGNMENT (v1, J 2026-07-14) + EVENTS/PRIOR-DAY/TODAY-CONTEXT/"
                    "LEVELS-CONTEXT (v1.1, J 2026-07-15). LOGGED ONLY: not consumed by "
                    "score/gates/_derive_tier this phase -- see heartbeat_core."
                    "_read_context_bundle + rec['context_bundle']. Grading path (spec only, "
                    "not built): see this module's docstring 'GRADING PATH' section.",
        }
    except Exception as e:  # noqa: BLE001 -- a scheduled fire must never break the chain
        bundle = {
            "schema_version": 2,
            "computed_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
            "per_tf": {}, "trend_alignment": {}, "alignment_score": 0,
            "events": None, "prior_day": None, "today_context": None, "levels_context": None,
            "degraded": True, "degraded_reason": f"producer crash: {type(e).__name__}: {e}",
            "note": "context_bundle_producer main() failed -- see degraded_reason. Fail-open: "
                    "this bundle is intentionally written so heartbeat_core's stale/absent "
                    "check has something concrete to age out.",
        }

    OUT_F.parent.mkdir(parents=True, exist_ok=True)
    OUT_F.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    if args.once:
        print(json.dumps(bundle, indent=2))
    else:
        pt = bundle.get("per_tf", {})
        ev = bundle.get("events") or {}
        tc = bundle.get("today_context") or {}
        print(f"[context_bundle_producer] alignment_score={bundle.get('alignment_score')} "
              f"degraded={bundle.get('degraded')} "
              f"daily={pt.get('daily', {}).get('trend')} "
              f"hourly={pt.get('hourly', {}).get('trend')} "
              f"m15={pt.get('m15', {}).get('trend')} "
              f"next_event={ev.get('next_event_name')} no_trade_window={ev.get('no_trade_window_active')} "
              f"gap_pct={tc.get('gap_pct_at_open')} rvol={tc.get('rvol_session_so_far')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
