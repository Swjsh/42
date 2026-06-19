"""Live watcher — polls latest bars + runs watchers in real time during market hours.

Runs every 5 min via Gamma_WatcherLive scheduled task (Mon-Fri 09:30-15:55 ET).

Flow:
  1. Read today's bars from the master SPY CSV (updated by EodSummary daily,
     or the live feed if data/today appender runs intraday)
  2. Get the LATEST bar (most recent 5min close)
  3. Run all watchers on that bar
  4. If any watcher fires + confidence >= medium → log + Discord ping
  5. Save state so we don't double-fire on the same bar

Watcher results land in:
  automation/state/watcher-observations.jsonl

Discord ping format:
  "🟡 ORB watcher: ORB_RETEST_LONG (medium) entry=$732.50 stop=$731.30 tp1=$734.10"
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))  # needed for crypto.lib.chart_patterns (HS/DB/FBW/momentum_accel watchers)

from autoresearch import runner as ar_runner
from lib.filters import BarContext, vol_baseline_20bar, range_baseline_20bar
from lib.ribbon import compute_ribbon, RibbonState
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import run_all_watchers, log_observation, OBS_LOG

import pandas as pd

STATE_DIR = ROOT / "automation" / "state"
LIVE_STATE = STATE_DIR / ".watcher-live-state.json"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"
CFG = STATE_DIR / ".discord-config.json"


def _user_mention() -> str:
    if not CFG.exists():
        return ""
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:
        return ""


def _queue_alert(content: str) -> None:
    row = {
        "queued_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "content": _user_mention() + content,
    }
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _read_last_bar_state() -> dict:
    if not LIVE_STATE.exists():
        return {}
    try:
        return json.loads(LIVE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_last_bar_state(state: dict) -> None:
    LIVE_STATE.write_text(json.dumps(state, default=str), encoding="utf-8")


def _write_skip_diag(reason: str, bar_ts: str = "", now: "dt.datetime | None" = None,
                     extra: "dict | None" = None) -> None:
    """Write a minimal diag entry on every early-return path so watcher fires are visible
    even when no bar is processed. Differentiates 'ran but skipped' from 'never ran'.

    `extra` merges additional context (e.g. exception text) into the row."""
    if now is None:
        now = dt.datetime.now()
    try:
        diag_file = STATE_DIR / "watcher-live-diag.jsonl"
        row = {"fire_at": now.isoformat(), "skip_reason": reason, "bar_ts_at_skip": bar_ts}
        if extra:
            row.update(extra)
        with diag_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        pass


def _load_history_only_fallback() -> "tuple[pd.DataFrame, pd.DataFrame]":
    """Load the MOST RECENT available spy_5m / vix_5m CSV pair regardless of whether
    it covers today's window.

    This is the rescue path for the pre-14:00 ET window: the rolling CSV that
    covers [today-7d, today] is not created until the ~14:00 daily-append job runs,
    so ``ar_runner.load_data(today-7d, today)`` raises FileNotFoundError and the
    watcher historically wrote {"skip_reason":"no_csv_data"} and produced ZERO
    observations all morning — leaving the unified heartbeat watcher layer INERT.

    Returning a history-only frame (which may END days ago) lets the yfinance
    intraday top-up graft today's live bars on top, so the ribbon SMA50 warmup
    still has 60+ trailing bars and the watcher fleet can fire on today's tape.

    Returns ([spy_df, vix_df]); each may be EMPTY if no CSV exists at all (the
    caller then relies entirely on the yfinance top-up).
    """
    empty = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    data_dir = ar_runner.DATA
    try:
        import re
        pattern = re.compile(r"spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")
        cands: list[tuple[dt.date, "Path"]] = []
        for p in data_dir.glob("spy_5m_*.csv"):
            m = pattern.match(p.name)
            if not m:
                continue
            try:
                fe = dt.date.fromisoformat(m.group(2))
            except ValueError:
                continue
            cands.append((fe, p))
        if not cands:
            return empty.copy(), empty.copy()
        # Most-recent end-date first.
        cands.sort(key=lambda x: x[0], reverse=True)
        for _fe, spy_path in cands:
            vix_path = data_dir / spy_path.name.replace("spy_5m_", "vix_5m_")
            if not vix_path.exists():
                vix_path = data_dir / vix_path.name.replace(".csv", "_merged.csv")
            try:
                spy = ar_runner._dedupe_by_timestamp(pd.read_csv(spy_path))
            except Exception:
                continue
            if vix_path.exists():
                try:
                    vix = ar_runner._dedupe_by_timestamp(pd.read_csv(vix_path))
                except Exception:
                    vix = empty.copy()
            else:
                vix = empty.copy()
            sys.stderr.write(
                f"watcher_live: load_data fallback using history-only CSV {spy_path.name} "
                f"(ends {_fe}); relying on yfinance top-up for today\n"
            )
            return spy, vix
    except Exception as e:
        sys.stderr.write(f"watcher_live history-only fallback failed: {e}\n")
    return empty.copy(), empty.copy()


def main() -> int:
    today = dt.date.today()
    now = dt.datetime.now()

    # Skip outside market hours (09:30-15:55 ET)
    t = now.time()
    if t < dt.time(9, 30) or t > dt.time(15, 55):
        return 0

    # Skip weekends
    if now.weekday() >= 5:
        return 0

    # Load latest bars (today + lookback for ribbon warmup)
    lookback_start = today - dt.timedelta(days=7)  # need 60+ bars for SMA50 warmup
    # PRE-14:00 RESCUE (2026-06-18 fix): the rolling CSV covering [today-7d, today]
    # is not written until the ~14:00 ET append job runs, so load_data raises
    # FileNotFoundError every morning. Historically this wrote skip_reason=no_csv_data
    # and produced ZERO observations all morning, leaving the unified heartbeat
    # watcher layer INERT. Instead of returning, fall back to the most-recent
    # history-only CSV and let the yfinance intraday top-up (below) graft today's
    # live bars on top. The top-up block now runs UNCONDITIONALLY when today's
    # bars are missing — it is no longer gated behind load_data success.
    _used_csv_fallback = False
    try:
        spy_full, vix_full = ar_runner.load_data(lookback_start, today)
    except FileNotFoundError:
        spy_full, vix_full = _load_history_only_fallback()
        _used_csv_fallback = True
        _write_skip_diag(
            "load_data_fallback_history_only",
            now=now,
            extra={"history_rows": int(len(spy_full)), "note": "rolling CSV absent; using yfinance top-up for today"},
        )
    # If even the fallback found nothing, keep going with an empty frame — the
    # yfinance top-up may still produce today's bars. Only the post-top-up
    # 'no bars at all' check below is allowed to bail (and it writes a diag).
    if "timestamp_et" not in spy_full.columns:
        spy_full = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"], errors="coerce")
    spy_full = spy_full.dropna(subset=["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    # Normalize vix_full timestamp_et too (load_data returns string-typed col).
    # Pass utc=True to silence "mixed timezones" FutureWarning when CSV mixes
    # tz-aware + naive strings.
    if "timestamp_et" in vix_full.columns:
        vix_full["timestamp_et"] = pd.to_datetime(vix_full["timestamp_et"], utc=True, errors="coerce")

    # Intraday top-up: if today's bars are missing from the CSV (CSV stops at
    # yesterday because the EOD appender hasn't run yet), fetch live 5m bars
    # from yfinance and append in-memory. Critical for watcher live observation
    # during market hours (encoded after 2026-05-13 wake-fire foot-gun where
    # watchers silently no-op'd all day because of `latest_date != today` gate).
    _csv_is_empty = spy_full.empty
    latest_csv_date = spy_full["date"].max() if not _csv_is_empty else None
    # Normalize latest_csv_date to a dt.date for comparison (CSV column may be
    # str, Timestamp, or date depending on pandas read). May be None/NaT when the
    # history-only fallback found nothing.
    if latest_csv_date is None or (isinstance(latest_csv_date, float) and pd.isna(latest_csv_date)) or pd.isna(latest_csv_date):
        latest_csv_date = None
    elif isinstance(latest_csv_date, str):
        latest_csv_date = dt.date.fromisoformat(latest_csv_date)
    elif hasattr(latest_csv_date, "date") and not isinstance(latest_csv_date, dt.date):
        latest_csv_date = latest_csv_date.date()
    # Top-up condition: also top-up when the CSV has today's date but the latest
    # bar is stale (> 10 min behind now). Without this, the watcher silently
    # deduplicates all intraday fires after the first one because the CSV already
    # has "today" in it (from a prior partial-day append) but doesn't have the
    # current 5-min bar. The dedup guard returns 0 every subsequent
    # fire, producing zero diag entries for the rest of the session.
    # Root cause of WATCHER_FLEET 0/100 on 2026-06-15.
    try:
        latest_csv_ts = pd.to_datetime(spy_full["timestamp_et"]).max() if not _csv_is_empty else None
        if latest_csv_ts is not None and not pd.isna(latest_csv_ts):
            if hasattr(latest_csv_ts, "tzinfo") and latest_csv_ts.tzinfo is not None:
                latest_csv_ts = latest_csv_ts.tz_localize(None)
            _stale_threshold = dt.timedelta(minutes=10)
            _csv_is_stale = latest_csv_ts < (dt.datetime.now() - _stale_threshold)
        else:
            _csv_is_stale = True
    except Exception:
        _csv_is_stale = False

    # Force the yfinance top-up whenever the CSV is empty, doesn't reach today, is
    # stale, or we fell back to a history-only file. This is the load-bearing
    # reorder: the top-up must run even when load_data threw FileNotFoundError.
    _need_topup = (
        _csv_is_empty
        or _used_csv_fallback
        or latest_csv_date is None
        or latest_csv_date < today
        or _csv_is_stale
    )
    if _need_topup:
        try:
            import yfinance as yf
            import pytz as _pytz
            ET = _pytz.timezone("America/New_York")

            def _fetch_intraday(sym_yf: str) -> pd.DataFrame:
                df = yf.download(
                    sym_yf,
                    start=today - dt.timedelta(days=2),
                    end=today + dt.timedelta(days=1),
                    interval="5m",
                    auto_adjust=False,
                    progress=False,
                    prepost=False,
                )
                if df.empty:
                    return pd.DataFrame()
                # Flatten MultiIndex columns (yfinance >=0.2.40 returns tuples for single ticker)
                if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                    df.columns = df.columns.get_level_values(0)
                df = df.reset_index()
                ts_col = df.columns[0]
                df = df.rename(columns={
                    ts_col: "timestamp_et",
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume",
                })
                # Match spy_full schema: timestamp_et is tz-aware ET. yfinance
                # returns UTC; convert to ET but keep tz-info.
                ts = df["timestamp_et"]
                if hasattr(ts.iloc[0], "tzinfo") and ts.iloc[0].tzinfo is not None:
                    df["timestamp_et"] = ts.dt.tz_convert(ET)
                else:
                    df["timestamp_et"] = pd.to_datetime(ts).dt.tz_localize("UTC").dt.tz_convert(ET)
                # Filter to today's bars by ET date
                df = df[df["timestamp_et"].dt.date == today]
                if df.empty:
                    return df
                df["date"] = df["timestamp_et"].dt.date
                return df[["timestamp_et", "open", "high", "low", "close", "volume", "date"]]

            spy_today = _fetch_intraday("SPY")
            if not spy_today.empty:
                spy_full = pd.concat([spy_full, spy_today], ignore_index=True)
                # Coerce timestamp_et to a single datetime64 dtype after concat
                # (concat of mixed tz-aware can produce object dtype). Make naive ET.
                ts = pd.to_datetime(spy_full["timestamp_et"], utc=True, errors="coerce")
                spy_full["timestamp_et"] = ts.dt.tz_convert(ET).dt.tz_localize(None)
                spy_full["date"] = spy_full["timestamp_et"].dt.date
                spy_full = spy_full.drop_duplicates(subset=["timestamp_et"], keep="last")
                spy_full = spy_full.sort_values("timestamp_et").reset_index(drop=True)
                sys.stderr.write(f"watcher_live: added {len(spy_today)} SPY intraday bars for {today}\n")

            vix_today = _fetch_intraday("^VIX")
            if not vix_today.empty:
                vix_full = pd.concat([vix_full, vix_today], ignore_index=True)
                ts2 = pd.to_datetime(vix_full["timestamp_et"], utc=True, errors="coerce")
                vix_full["timestamp_et"] = ts2.dt.tz_convert(ET).dt.tz_localize(None)
                vix_full = vix_full.drop_duplicates(subset=["timestamp_et"], keep="last")
                vix_full = vix_full.sort_values("timestamp_et").reset_index(drop=True)
                sys.stderr.write(f"watcher_live: added {len(vix_today)} VIX intraday bars for {today}\n")
        except Exception as e:
            # Live fetch failed (network / yf rate limit) — log and continue with
            # CSV-only data. Watchers will no-op via the existing latest_date check.
            import traceback
            sys.stderr.write(f"watcher_live yfinance top-up failed: {e}\n")
            sys.stderr.write(traceback.format_exc())
            _write_skip_diag(
                f"yfinance_topup_failed:{type(e).__name__}",
                now=now,
                extra={"exc": str(e)[:300]},
            )

    # If the CSV had no usable history AND the top-up produced no bars at all, we
    # have nothing to run on — bail LOUDLY (no silent return). This is distinct
    # from rth_empty below, which can also be hit by the volume filter dropping
    # every bar; this one specifically flags "data acquisition produced zero rows".
    if spy_full.empty:
        _write_skip_diag(
            "no_bars_after_topup",
            now=now,
            extra={"used_csv_fallback": _used_csv_fallback,
                   "note": "history-only CSV empty AND yfinance returned no bars (weekend/after-close or fetch failure)"},
        )
        return 0

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    # T76 (2026-05-14 11:30 ET fix) — INCOMPLETE-BAR FILTER. yfinance's
    # most recent 5m bar (the one currently in progress) returns volume=0
    # and OHLC all equal to the snapshot price. That bar fails every
    # watcher's volume gate (vol_mult > 1.1) → all 5 multi-day watchers
    # silent. Diag-trail captured: 24 fires, 0 signals, latest_bar.volume=0
    # while vol_baseline_20=425K. Fix: drop bars with volume==0 so we
    # use the most recent CLOSED 5m bar. Historical CSV bars all have
    # real volume so this only filters the live in-progress bar.
    # See docs/T48-SNIPER-5-13-MISSFIRE-2026-05-14.md mode 4.
    _pre_filter_rows = len(rth)
    rth = rth[rth["volume"] > 0].reset_index(drop=True)
    if len(rth) < _pre_filter_rows:
        sys.stderr.write(
            f"T76: dropped {_pre_filter_rows - len(rth)} zero-volume incomplete bar(s)\n"
        )

    if rth.empty:
        _write_skip_diag("rth_empty", now=now)
        return 0

    # Find the latest bar
    latest_idx = len(rth) - 1
    latest_bar = rth.iloc[latest_idx]
    latest_ts = latest_bar["timestamp_et"]
    latest_date = latest_ts.date()

    # Skip if we've already processed this bar.
    #
    # STALE-STATE GUARD (2026-06-18 fix): the dup check compares against
    # .watcher-live-state.json, which can FREEZE (the whole reason the feed went
    # dark — ~20 fires after 14:00 on 2026-06-15 wrote neither obs nor diag because
    # a stale state file kept matching). Two hardenings:
    #   (a) Only honour the dup-skip when the latest bar is genuinely from TODAY.
    #       A new today-bar must NEVER be suppressed by yesterday's frozen state.
    #   (b) Only honour it when the stored ts ALSO parses to today — a stale ts
    #       from a prior session can't gate out today's first real bar.
    state = _read_last_bar_state()
    last_processed_ts = state.get("last_bar_ts")
    _stored_is_today = False
    if last_processed_ts:
        try:
            _stored_is_today = pd.to_datetime(last_processed_ts).date() == today
        except Exception:
            _stored_is_today = False
    if (
        last_processed_ts
        and last_processed_ts == str(latest_ts)
        and latest_date == today
        and _stored_is_today
    ):
        # Genuinely already processed THIS today-bar — write a low-noise skip entry
        # every 6th fire (~30 min) so we can confirm the task is running without
        # flooding the diag log.
        try:
            _skip_count = state.get("_dup_skip_count", 0) + 1
            state["_dup_skip_count"] = _skip_count
            _save_last_bar_state(state)
            if _skip_count % 6 == 1:
                _write_skip_diag(f"dup_bar:{latest_ts}", bar_ts=str(latest_ts), now=now)
        except Exception:
            pass
        return 0

    # Skip if latest bar is not from today (data feed hasn't caught up)
    if latest_date != today:
        _write_skip_diag(f"stale_csv_date:{latest_date}!={today}", bar_ts=str(latest_ts), now=now)
        return 0

    # Build context for the latest bar
    if latest_idx < 60:
        _write_skip_diag(f"not_enough_bars:{latest_idx}", bar_ts=str(latest_ts), now=now)
        return 0

    # Ribbon / VIX-alignment / HTF precompute — any of these can throw on a
    # malformed frame. Previously a bare `except: return 0` swallowed the failure
    # SILENTLY (lesson C7). Now every exception path writes a diag with the
    # exception text + stderr traceback so a broken ribbon is never invisible.
    try:
        ribbon_df = compute_ribbon(rth["close"])
        vix_aligned = _align_vix_to_spy(rth, vix_full)
        htf_stacks = _precompute_htf_15m_stacks(rth)
    except Exception as _e_pre:
        import traceback
        sys.stderr.write(f"watcher_live ribbon/vix precompute failed: {_e_pre}\n")
        sys.stderr.write(traceback.format_exc())
        _write_skip_diag("ribbon_exception", bar_ts=str(latest_ts), now=now,
                         extra={"stage": "precompute", "exc": f"{type(_e_pre).__name__}: {_e_pre}"})
        return 0

    try:
        r = ribbon_df.iloc[latest_idx]
        ribbon_state = RibbonState(
            fast=float(r["fast"]),
            pivot=float(r["pivot"]),
            slow=float(r["slow"]),
            stack=str(r["stack"]),
            spread_cents=float(r["spread_cents"]),
        )
    except Exception as _e_ribbon:
        import traceback
        sys.stderr.write(f"watcher_live ribbon_state build failed: {_e_ribbon}\n")
        sys.stderr.write(traceback.format_exc())
        _write_skip_diag("ribbon_exception", bar_ts=str(latest_ts), now=now,
                         extra={"stage": "ribbon_state", "latest_idx": int(latest_idx),
                                "exc": f"{type(_e_ribbon).__name__}: {_e_ribbon}"})
        return 0

    # Build short ribbon history
    ribbon_history = []
    for i in range(max(0, latest_idx - 5), latest_idx + 1):
        try:
            r = ribbon_df.iloc[i]
            ribbon_history.append(RibbonState(
                fast=float(r["fast"]),
                pivot=float(r["pivot"]),
                slow=float(r["slow"]),
                stack=str(r["stack"]),
                spread_cents=float(r["spread_cents"]),
            ))
        except Exception:
            pass

    vol_baseline = vol_baseline_20bar(rth, latest_idx)
    range_baseline = range_baseline_20bar(rth, latest_idx)
    vix_now = float(vix_aligned.iloc[latest_idx]) if latest_idx < len(vix_aligned) else 17.0
    # 2026-05-16 L40 fix (T81): use 3-bar lookback for vix_prior (15-min trend).
    # Single-bar VIX delta is 0.01–0.04 on slow post-news drift days — sub-deadband (0.05),
    # always "flat" → Filter 8 blocks ALL bullish bars even on CPI-relief trending days.
    # 3-bar lookback accumulates 0.06–0.12 delta → exceeds deadband → "falling" fires correctly.
    # Mirrors the fix already applied in eod_deep/modules/detection.py (vix_prior_idx = max(0, idx-3)).
    _vix_prior_idx = max(0, latest_idx - 3)
    vix_prior = float(vix_aligned.iloc[_vix_prior_idx]) if _vix_prior_idx < len(vix_aligned) else vix_now

    full_history = spy_full[spy_full["timestamp_et"] <= latest_ts]
    level_set = _detect_from_history(full_history, latest_date)

    # Per-day level state (rebuilt from today's bars)
    level_states = {}
    today_bars = rth[rth["timestamp_et"].dt.date == latest_date].reset_index(drop=True)
    for i in range(len(today_bars)):
        b = today_bars.iloc[i]
        _update_level_states(level_states, level_set.active, b, i)

    htf_stack = htf_stacks[latest_idx] if latest_idx < len(htf_stacks) else None

    ctx = BarContext(
        bar_idx=latest_idx,
        timestamp_et=latest_ts.to_pydatetime(),
        bar=latest_bar,
        prior_bars=rth,
        ribbon_now=ribbon_state,
        ribbon_history=ribbon_history,
        vix_now=vix_now,
        vix_prior=vix_prior,
        vol_baseline_20=vol_baseline,
        range_baseline_20=range_baseline,
        levels_active=level_set.active,
        multi_day_levels=level_set.multi_day,
        htf_15m_stack=htf_stack,
        level_states=level_states,
    )

    bar_idx_in_day = (today_bars["timestamp_et"] == latest_ts).idxmax() if not today_bars.empty else 0

    # Build ribbon state dict for VWAP watcher (which wants a plain dict, not RibbonState)
    ribbon_state_dict = {
        "fast": ribbon_state.fast,
        "pivot": ribbon_state.pivot,
        "slow": ribbon_state.slow,
        "stack": ribbon_state.stack,
        "spread_cents": ribbon_state.spread_cents,
    }

    # T82 (2026-05-14 evening fix) — STATEFUL DETECTOR WARMUP.
    # ORB (and likely ODF + PFF) use module-level state machines that progress
    # NEUTRAL → BREAKOUT → WAIT_RETEST → ENTRY across bars. Production fires
    # watcher_live as a FRESH PROCESS every 5min via Gamma_WatcherLive — module
    # state is reset on every fire, so the breakout bar registers in process A
    # and the entry signal never fires from process B. Per
    # docs/T80-ORB-BULL-REGRESSION.md (PROD-MIMIC test reproduced 0 fires/day).
    #
    # Fix: walk today's RTH bars sequentially calling stateful detectors directly
    # (no logging, no Discord ping) BEFORE the main run_all_watchers call below.
    # State machine accumulates correctly. Latest bar's call then fires entries.
    # Validated by backtest/autoresearch/t82_orb_warmup_test.py: 78-bar warmup
    # takes 6.5ms (well under 80ms budget). Without warmup → 0 ORB fires/day;
    # with warmup → 1 ORB fire today @ 10:30 ET medium confidence.
    if not today_bars.empty and bar_idx_in_day > 0:
        try:
            from lib.watchers.orb_watcher import detect_orb_break as _orb_warmup
            # T82b extension (2026-05-14 evening): also warmup ODF (module-level
            # _odf_state per-day state machine for HOD/LOD ratchet + stall counter).
            # PFF + VWAP + V14E are stateless — no warmup needed.
            from lib.watchers.opening_drive_fade_watcher import (
                detect_opening_drive_fade_setup as _odf_warmup,
            )
            for _wu_idx in range(int(bar_idx_in_day)):  # exclude latest (run_all_watchers below handles it)
                _wu_bar = today_bars.iloc[_wu_idx]
                # ORB takes (bar, day_bars, day_idx, vol_baseline)
                try:
                    _orb_warmup(_wu_bar, today_bars, _wu_idx, vol_baseline)
                except Exception as _e_orb_wu:
                    sys.stderr.write(f"T82 orb warmup err at bar_idx={_wu_idx}: {type(_e_orb_wu).__name__}: {_e_orb_wu}\n")
                # ODF takes (bar, multi_day_idx, multi_day_rth) — find the bar's
                # index in the full multi_day_rth (rth) frame
                try:
                    _wu_match = rth.index[rth["timestamp_et"] == _wu_bar["timestamp_et"]]
                    if len(_wu_match) > 0:
                        _wu_full_idx = int(_wu_match[-1])
                        _odf_warmup(_wu_bar, _wu_full_idx, rth)
                except Exception as _e_odf_wu:
                    sys.stderr.write(f"T82b odf warmup err at bar_idx={_wu_idx}: {type(_e_odf_wu).__name__}: {_e_odf_wu}\n")
        except Exception as _e_t82:
            sys.stderr.write(f"T82 warmup module-import failed: {type(_e_t82).__name__}: {_e_t82}\n")

    try:
        signals = run_all_watchers(
            latest_bar,
            today_bars,
            bar_idx_in_day,
            vol_baseline,
            ctx,
            vix_now,
            multi_day_rth=rth,
            ribbon_state_dict=ribbon_state_dict,
        )
    except Exception as _e_run:
        # The watcher fleet itself blew up — this is the load-bearing operation,
        # so a crash here must be LOUD (lesson C7), not a stack-trace to nowhere.
        import traceback
        sys.stderr.write(f"watcher_live run_all_watchers failed: {_e_run}\n")
        sys.stderr.write(traceback.format_exc())
        _write_skip_diag("watcher_run_exception", bar_ts=str(latest_ts), now=now,
                         extra={"exc": f"{type(_e_run).__name__}: {_e_run}"})
        return 0

    for s in signals:
        log_observation(s, latest_ts)
        # Discord ping for medium+ confidence
        if s.confidence in ("medium", "high"):
            emoji = "🔴" if s.confidence == "high" else "🟡"
            msg = (
                f"{emoji} **{s.watcher_name}**: {s.setup_name} ({s.confidence})\n"
                f"entry=${s.entry_price:.2f} stop=${s.stop_price:.2f} "
                f"tp1=${s.tp1_price:.2f}" + (f" runner=${s.runner_price:.2f}" if s.runner_price else "") + "\n"
                f"reason: {s.reason}"
            )
            _queue_alert(msg)

    state["last_bar_ts"] = str(latest_ts)
    state["last_run"] = now.isoformat()
    state["signals_this_bar"] = len(signals)
    _save_last_bar_state(state)

    # Diagnostic trail (T48 / OP-25 silent-failure absorption 2026-05-14).
    # Every fire writes a 1-line summary so we can detect silent zero-observation
    # days in real time. JSONL append-only.
    try:
        from lib.sniper_detector import compute_levels as _sniper_compute_levels, SniperParams as _SniperParams
        try:
            _sniper_levels = _sniper_compute_levels(rth, as_of=latest_ts.to_pydatetime(), params=_SniperParams())
            _level_count = len(_sniper_levels)
            _level_5d_high = next((l.price for l in _sniper_levels if l.label == "5d_high"), None)
        except Exception:
            _level_count = -1
            _level_5d_high = None

        # Bar 12:20-style snapshot
        _diag = {
            "fire_at": now.isoformat(),
            "latest_bar_ts": str(latest_ts),
            "latest_bar_o": float(latest_bar.get("open", 0.0)),
            "latest_bar_h": float(latest_bar.get("high", 0.0)),
            "latest_bar_l": float(latest_bar.get("low", 0.0)),
            "latest_bar_c": float(latest_bar.get("close", 0.0)),
            "latest_bar_v": int(latest_bar.get("volume", 0)),
            "multi_day_rth_rows": int(len(rth)),
            "today_rth_rows": int(len(today_bars)),
            "vol_baseline_20": float(vol_baseline) if vol_baseline else 0.0,
            "vix_now": float(vix_now),
            "sniper_levels_count": _level_count,
            "sniper_5d_high": _level_5d_high,
            "signals_emitted": len(signals),
            "signals_by_watcher": {s.watcher_name: s.setup_name for s in signals} if signals else {},
        }
        diag_file = STATE_DIR / "watcher-live-diag.jsonl"
        with diag_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_diag) + "\n")
    except Exception as _diag_e:
        # Never let diagnostic failure break the main fire
        sys.stderr.write(f"watcher_live diag write failed: {_diag_e}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
