"""ssr_shadow.py -- own-book, watch-only forward shadow of the SSR-v1 PULSE configs.

WHY THIS EXISTS: backtest/futures/analysis/SSR-battery/DESIGN.md's SSR-v1 ADDENDUM verdict
rules say that when NO cell clears the full BH-FDR ladder but >=1 cell hits the PULSE tier
(OOS n>=10 AND OOS mean>0 AND beats_bh AND drop_top3>0), the sanctioned next step is a
**forward own-book shadow ledger** (Edge3Sim pattern -- watch-only, no broker, no live money),
NOT another historical grind on sanity-tier yfinance data. RESULTS.md's v1 section names the
PULSE cells; this script runs the two frozen configs below forward in time and accumulates
real-clock evidence toward the arming bar (module docstring's ARMING BAR section).

NEVER PLACES AN ORDER. NEVER TOUCHES A BROKER. NO ACCOUNT, NO CREDS, NO ALPACA IMPORT
ANYWHERE IN THIS FILE. This is a synthetic own-book ledger only -- see CLAUDE.md's standing
refusal list; futures has no live-arming path here regardless (Alpaca has zero futures).

FROZEN SHADOW SPEC v1 (SPEC_VERSION="ssr-v1"; SUPERSEDED 2026-08-23 -- see RESPEC v1->v2
below. Kept verbatim as the historical record of what actually ran and produced the round
trips retained as `legacy_evidence`, non-arming, in the progress JSON):

  Config NQ: symbol NQ=F, bars 15m (fetch period 8d), SHORT signals only,
             SSRParams(zone_atr_mult=0.5, sweep_atr_mult=0.1), h4_anchor='2000',
             include_running=True. FULL-SIZE NQ (point_value $20.00/pt) -- ~326x this
             book's own equity at qty=3 (see the 2026-08-13 FUNDABILITY DISCLOSURE that
             flagged this and forced the RESPEC below). NEVER a live CONFIGS key again.
  Config GC: symbol GC=F, bars 1h (fetch period 60d), SHORT signals only, same params/
             anchor/running. FULL-SIZE GC (point_value $100.00/pt) -- same problem. NEVER a
             live CONFIGS key again.
  (Both are the RESULTS.md v1-family PULSE cells J named -- see CONFIGS below for the
  CURRENT (v2) dict this script runs; the v1 dict is preserved above for provenance only.)

RESPEC v1 -> v2 (2026-08-23, SPEC_VERSION="ssr-v2"): the 2026-08-13 fundability disclosure
(`_fundability`, called from `compute_progress`) measured full-size NQ/GC at qty=3 against
this book's own recorded equity (automation/state/futures/account.json) and found a ~326x
notional/equity ratio -- arithmetically correct, operationally impossible (nobody can margin
3 full NQ contracts on this account). CONFIGS below now key on MNQ/MGC (Micro E-mini
Nasdaq-100 / Micro Gold, both VERIFIED exactly 1/10th their full-size sibling's point_value
-- backtest/futures/instruments.py for MNQ ($2.00/pt vs NQ's $20.00), backtest/futures/ssr/
ssr_instruments.py for MGC ($10.00/pt vs GC's $100.00)). NOTHING about the detector,
entry/exit math, ATR, levels, or the arming bar's THREE conditions (n>=20 AND
positive_expectancy AND beats_null) changed -- ONLY the $-per-point multiplier used to price
each fill. beats_null was FALSE under v1 (an unmanaged hold to the same closing bar
out-earned the managed exits) and stays exactly as broken under v2 -- this respec fixes a
SIZING problem, not an EXIT-QUALITY problem; the two are independent and nobody should read
a green fundability disclosure as evidence the exit logic improved.

FRESH FORWARD CLOCK (hard rule, guarded by backtest/tests/test_ssr_shadow_v2_respec.py):
every round trip scored under CONFIGS' pre-respec keys ("NQ"/"GC" literally -- every row
already in the ledger before this commit, which never carried a `spec_version` field at
all, since that field did not exist pre-respec) is retained VERBATIM in the SAME
ssr-shadow-would-be.jsonl ledger and reported by `compute_progress` as `legacy_evidence`:
historical, clearly labeled ssr-v1, EXCLUDED from n_round_trips/total_pnl_usd/
positive_expectancy/beats_null/armable. The arming bar's n resets to 0 for v2 and only
counts round trips whose rows carry `spec_version=="ssr-v2"` (every row `_entry_event`/
`_row` writes from this commit onward stamps that field automatically -- absence of the
field is itself how a legacy row is recognized). One already-OPEN v1 position
(config="NQ") at the moment of this respec is not orphaned: LEGACY_CONFIG_ALIASES lets it
keep being walked forward to its own natural close using ITS OWN (full-size) instrument
spec -- see `_run_once_unlocked` -- while new entries only ever open under the CONFIGS keys
(MNQ/MGC). LEGACY_CONFIG_ALIASES is NEVER a source for opening a NEW position.

  REUSE (imported, never reimplemented -- backtest/futures/ssr/* is READ-ONLY, HARD RULE):
    futures.ssr.levels.build_levels        -- causal session/day/week/4H (+RUN_*) levels
    futures.ssr.detector.SSRDetector/SSRParams -- the sweep->shift->retest state machine;
      its own SSRParams.entry_start_et/entry_end_et defaults ("03:00"/"15:00") ARE the
      frozen 03:00-15:00 ET entry window -- this script never overrides them, so the
      entry-window gate lives entirely inside the shared detector (tested there; this file's
      test suite pins the gate directly via detector._step_shifted, see test file).
    futures.ssr.ssr_instruments.get_ssr    -- GC/MGC local registry, falls back to the
      shared backtest.futures.instruments registry for NQ/MNQ/ES/MES.
    futures.swing_sim.wilder_atr           -- the canonical Wilder ATR14, not reimplemented.
  NOT reused: futures.ssr.data_fetch (its CSV-cache + provenance.jsonl side effects are the
    BATTERY's own shared resource -- a 15-min poll hammering that cache/ledger with a fresh
    yfinance pull every fire would thrash a file the historical battery scripts also read/
    write). `fetch_bars_light` below is the "data_fetch light variant" the task explicitly
    sanctions: plain yfinance download, same column/tz normalization SHAPE as data_fetch.py,
    but NO disk cache and NO provenance line -- entirely self-contained to this script's own
    automation/state/futures/ssr-shadow-* files.
  NOT reused: futures.ssr.backtest_runner (its `run_trades` is a single-pass, whole-history
    walk-forward over ALREADY-COMPLETE bars -- built for the historical battery, not a
    15-min poll that only ever sees bars up to "now" and must persist in-flight position
    state ACROSS separate process invocations). The exit MATH (TP1=1.5R for 2/3 qty, stop
    to breakeven, runner = nearest opposing level beyond TP1 else 3R capped at 5R,
    stop-before-target on same-bar conflict) is reproduced here to be IDENTICAL to
    backtest_runner.py's doctrine (see `_pick_runner`, `decide_bar_events` docstrings for the
    parity notes against backtest_runner._pick_runner / futures.futures_sim.simulate_futures's
    own per-bar loop order), just re-expressed as an incremental, poll-safe walker.

  POLL MODEL (--once per fire, every 15 min via Task Scheduler, Mon-Fri):
    1) fetch fresh bars per config (15m: period=8d; 1h: period=60d) via fetch_bars_light.
    2) DROP the final row (yfinance's last intraday/hourly row for an active fetch can be an
       in-progress bar -- dropped unconditionally per the frozen spec, never inspected for
       "is it really still forming").
    3) rebuild levels (build_levels) + ATR14 (wilder_atr) + run the detector fresh over the
       WHOLE fetched window (the detector is a stateless, deterministic function of
       bars/snapshots/atr -- re-running it from scratch every poll is correct and cheap at
       this bar count; see module's WATERMARK section for how re-detecting the SAME historical
       signal every poll is prevented from re-opening a position).
    4) SHORT-only enforcement: BOTH configs are frozen SHORT-only per the RESULTS.md PULSE
       cells. The detector itself emits both directions (a buy-side sweep of a high-type
       level arms SHORT, a sell-side sweep of a low-type level arms LONG) -- LONG signals are
       filtered out and COUNTED here, never silently dropped (see `skipped_long_signal`).
    5) WATERMARK + LOOKBACK: a signal is eligible to open a NEW position only if BOTH
       (a) its ts_et is strictly newer than this config's persisted watermark (the newest
           bar timestamp this config has ever scanned -- see `_select_new_signals`), AND
       (b) its bar_index falls within the LAST `LOOKBACK_BARS` (3) bars of THIS poll's
           fetched window (a safety cap independent of the watermark -- protects against
           ever opening a position off a signal that is technically "never scanned before"
           but stale, e.g. after a long outage the watermark itself is stale).
       COLD START (a config with no persisted watermark -- first-ever run, or state file
       lost): mirrors setup/scripts/futures_mirror_shadow.py's own cold-start discipline
       VERBATIM -- the watermark jumps straight to this poll's LAST bar timestamp with ZERO
       candidates opened, and the config exits for this poll. Historical backlog is NEVER
       mirrored; only signals whose OWN bar arrives strictly after a config's first-ever
       watched poll are ever shadow-traded. (Verified live in futures_mirror_shadow.py: an
       early unguarded run without this guard opened positions off signals up to 18 days
       stale -- the exact failure this discipline exists to prevent.)
    6) CONCURRENCY: ONE open position per config at a time (matches DESIGN.md sec 3's
       battery-wide concurrency rule, and backtest_runner.py's `position_open_until` gate --
       kept identical here for apples-to-apples forward/backward comparability). A new
       signal arriving while a config already has an open position is skipped and counted
       (`skipped_while_open`), never queued.
    7) ENTRY: synthetic fill at the SIGNAL bar's own close (`SSRSignal.entry_ref_close` --
       literally the bar the sweep->shift->retest sequence concluded on) +/- 1 tick slippage
       (worse for the position: long pays up 1 tick, short sells down 1 tick). stop =
       `SSRSignal.stop_price` (the detector already computes sweep_extreme +/- 0.15*ATR --
       reused verbatim, never recomputed here). R := |entry - stop|; degenerate (R<=0 or
       R < 1 tick) signals are skipped and counted (`skipped_degenerate`), never opened.
    8) EXIT (identical doctrine to backtest_runner.py / DESIGN.md sec 3, re-expressed as an
       incremental per-bar walker -- see `decide_bar_events`): qty=3, TP1 = entry +/- 1.5R
       for 2 of 3 contracts, stop moves to breakeven (entry) on the remaining 1, runner =
       nearest opposing level from the signal bar's own LevelSnapshot strictly beyond TP1 in
       the profit direction (else a fixed 3R fallback, capped at 5R from entry either way --
       `_pick_runner`, byte-for-byte the same selection rule as
       backtest_runner.py::_pick_runner). Same-bar conflicts resolve STOP FIRST (matches
       futures.futures_sim.simulate_futures's own per-bar loop order: the pre-TP1 fixed stop,
       or the post-TP1 breakeven stop, is always checked before that bar's target/runner
       leg). Forced flat 16:55 ET the SAME trading day the signal fired (single-session --
       unlike futures_mirror_shadow's 2-session MES horizon, SSR entries only fire
       03:00-15:00 ET so 16:55 same day is always hours away, never a same-day-impossible
       deadline).
    9) Open positions are walked forward on every poll: for each open position, every bar in
       this poll's fetch window strictly newer than that position's own
       `last_processed_bar_ts_et` is fed through `decide_bar_events` in chronological order
       (bar high/low, stop-priority) until it closes or bars run out; every fill/close is
       appended to ssr-shadow-would-be.jsonl as its own lifecycle row.

  STATE (automation/state/futures/):
    ssr-shadow-state.json     -- {_doc, spec_version, configs: {NQ:{watermark_bar_ts_et,
                                  last_run_et}, GC:{...}}, positions: {signal_ref: {...}},
                                  last_run_et, errors}. Atomic write (temp file + os.replace).
    ssr-shadow-would-be.jsonl -- append-only lifecycle ledger. Event vocabulary:
                                  entry | tp1 | closed (closed carries `reason` in
                                  {stopped_pre_tp1, stopped_be, runner, time_flat}).
    ssr-shadow-progress.json  -- the arming-bar tracker, recomputed every poll (see below).

  ARMING BAR (this script computes it every poll -- unlike futures_mirror_shadow, which
    defers to a separate later-session script; there is no headroom here for a 4th allowed
    file, so `compute_progress` lives in this module and is called from `run_once`'s tail):
    >=20 CLOSED round trips (a signal_ref's own `closed` event, counted per signal_ref) AND
    positive expectancy (sum of pnl_usd across the round trip's own rows > 0) AND beats_null,
    where the null = the SAME entry (price/timestamp/direction/full original qty=3) held
    UNMANAGED (no stop/target) to that SAME round trip's OWN closing bar's close price --
    read directly off the ledger's own recorded `bar_close` field on the closing row (never a
    network refetch: the closing event already recorded the bar's true OHLC close at the
    moment it fired, whether that fire was a stop/tp1/runner touch or a forced 16:55 flatten).
    A trip missing entry/close/direction/config data (should not occur in a well-formed
    ledger) reports null_unavailable for that trip and is excluded from the null aggregate,
    with coverage disclosed (e.g. "18/20") -- mirrors futures_shadow_progress.py's own
    disclosure convention. `armable=true` only once all three conditions hold; this script
    never arms anything itself (arming stays a documented separate J/doctrine step).
    AS OF ssr-v2 (2026-08-23): round trips are filtered to `spec_version==SPEC_VERSION`
    BEFORE any of the above is computed -- see RESPEC v1->v2 above. Legacy (pre-respec)
    trips are reported separately as `legacy_evidence` and never mixed into this count.

  ALL DATETIMES ARE TZ-AWARE ET (task-explicit override of this repo's usual naive-ET
    convention -- see et_clock.py's own docstring for why naive-ET is normally the house
    style; THIS script instead standardizes on tz-aware `pandas.Timestamp` objects in
    "America/New_York" everywhere, including `_et_now()`'s return value, so every timestamp
    this script stores/compares is unambiguously tz-aware -- see
    test_ssr_shadow.py::test_no_naive_datetimes for the pin).

  FAIL-OPEN EVERYWHERE (C7 -- count every fallback, never a silent empty result): every
    per-config step (fetch, detect, open, manage) is try/except-guarded and any exception is
    appended to the run summary's `errors` list AND the state file's `errors` field; `main()`
    ALWAYS returns 0, never raises.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3 -- same guard as futures_mirror_shadow.py) ==
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting can
# allocate a visible WindowsTerminal window on the FIRST stdout/stderr write. Redirect stdio
# to log files BEFORE any other import gets a chance to write.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "ssr-shadow.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "ssr-shadow.stderr.log", "a", buffering=1, encoding="utf-8")
# ==============================================================================================

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures.ssr.detector import SSRDetector, SSRParams, SSRSignal  # noqa: E402
from futures.ssr.levels import build_levels  # noqa: E402
from futures.ssr.ssr_instruments import get_ssr  # noqa: E402
from futures.swing_sim import wilder_atr  # noqa: E402

# ── frozen spec constants ────────────────────────────────────────────────────────────────
SPEC_VERSION = "ssr-v2"
ET_ZONE = "America/New_York"

# CONFIGS keys are the get_ssr() instrument symbol looked up to price every fill -- MUST be
# the MICRO symbols (see RESPEC v1->v2, module docstring). `symbol` (the yfinance fetch
# ticker) is UNCHANGED from v1: MNQ tracks NQ's own index price 1:1 (only the $-multiplier
# differs -- backtest/futures/instruments.py), MGC tracks GC's own price/oz 1:1 (backtest/
# futures/ssr/ssr_instruments.py) -- so "NQ=F"/"GC=F" bars are byte-identical price data for
# either sizing and there is no separate "MNQ=F" feed to fetch.
CONFIGS: dict[str, dict[str, Any]] = {
    "MNQ": {
        "symbol": "NQ=F", "interval": "15m", "period": "8d",
        "zone_atr_mult": 0.5, "sweep_atr_mult": 0.1,
        "h4_anchor": "2000", "include_running": True,
    },
    "MGC": {
        "symbol": "GC=F", "interval": "1h", "period": "60d",
        "zone_atr_mult": 0.5, "sweep_atr_mult": 0.1,
        "h4_anchor": "2000", "include_running": True,
    },
}

# LEGACY_CONFIG_ALIASES: ssr-v1's full-size config keys, kept ONLY so a position still open
# under the v1 spec (config="NQ"/"GC" literally, recorded in the live state file BEFORE this
# respec) keeps being walked forward to its OWN natural close using ITS OWN (full-size)
# instrument spec -- see `_run_once_unlocked`'s legacy-alias walk. NEVER used to open a NEW
# position -- new entries only ever use the CONFIGS keys above (MNQ/MGC).
LEGACY_CONFIG_ALIASES: dict[str, str] = {"MNQ": "NQ", "MGC": "GC"}

ATR_PERIOD = 14
LOOKBACK_BARS = 3          # "within the last 3 completed bars" -- frozen spec
MIN_BARS_REQUIRED = 20     # floor for ATR/detector warmup; below this a config's poll no-ops
QTY = 3
TP1_QTY = 2                # 2/3 of 3, rounds to 2 (matches backtest_runner.TP1_FRACTION=2/3)
RUN_QTY = QTY - TP1_QTY     # 1
TP1_R_MULT = 1.5
RUNNER_FALLBACK_R_MULT = 3.0
RUNNER_CAP_R_MULT = 5.0
FLAT_HOUR_ET, FLAT_MINUTE_ET = 16, 55
POSITION_RETENTION_DAYS = 10   # OP-22 retention cap on CLOSED positions in the live state json
ARMING_MIN_ROUND_TRIPS = 20

EV_ENTRY = "entry"
EV_TP1 = "tp1"
EV_CLOSED = "closed"

REASON_STOPPED_PRE_TP1 = "stopped_pre_tp1"
REASON_STOPPED_BE = "stopped_be"
REASON_RUNNER = "runner"
REASON_TIME_FLAT = "time_flat"

# ── paths ─────────────────────────────────────────────────────────────────────────────────
STATE_DIR = REPO / "automation" / "state" / "futures"
LOG_DIR = REPO / "automation" / "state" / "logs"
STATE_FILE = STATE_DIR / "ssr-shadow-state.json"
LEDGER_FILE = STATE_DIR / "ssr-shadow-would-be.jsonl"
LOCK_FILE = STATE_DIR / "ssr-shadow.lock"
LOCK_STALE_S = 600  # a lock older than this belongs to a crashed run and may be broken
PROGRESS_FILE = STATE_DIR / "ssr-shadow-progress.json"

STATE_DOC = (
    "ssr_shadow.py watermark + open-position state. spec_version pins the FROZEN SPEC "
    "(module docstring, currently ssr-v2 -- see RESPEC section). configs = {MNQ,MGC: "
    "{watermark_bar_ts_et, last_run_et}} -- the newest bar timestamp each config has ever "
    "scanned; a signal at/before this ts can never open a NEW position (never-backfill "
    "guard). positions = {signal_ref: {...}}, keyed "
    "'{config}|{direction}|{level_name}|{signal_minute}' -- config is either a live CONFIGS "
    "key (MNQ/MGC) or, for a position still open at the moment of the ssr-v2 respec, a "
    "LEGACY_CONFIG_ALIASES value (NQ/GC) settled under its OWN full-size spec. See "
    "ssr_shadow.py module docstring for the full frozen spec + arming bar."
)
LEDGER_DOC = (
    "ssr_shadow.py append-only lifecycle ledger. Event vocabulary: entry | tp1 | closed "
    "(closed carries reason in {stopped_pre_tp1, stopped_be, runner, time_flat}). Every row "
    "records bar_close (the completed bar's own OHLC close at that event, used by the arming "
    "bar's buy-and-hold null -- never a network refetch), qty_open_after (0 on the row that "
    "completes a round trip), and spec_version (ssr-v2 for every row written from the "
    "2026-08-23 respec onward; rows written before that respec never carry this field -- its "
    "absence IS the ssr-v1 marker, see module docstring RESPEC section). ARMING BAR: >=20 "
    "CURRENT-spec_version closed round trips (by signal_ref), positive expectancy (sum "
    "pnl_usd), beats_null (same-direction unmanaged hold to the trip's own closing "
    "bar_close) -- retired-spec_version round trips are reported separately as "
    "legacy_evidence and never counted here. See ssr_shadow.py module docstring for the full "
    "spec. NO BROKER. NO ORDERS. Own-book synthetic ledger only."
)
PROGRESS_DOC = (
    "ssr_shadow.py SSR PULSE forward-shadow arming-bar progress (spec_version ssr-v2, "
    "respec'd 2026-08-23 -- see module docstring RESPEC section). Bar: >=20 CURRENT-spec "
    "closed round trips AND positive_expectancy (total_pnl_usd > 0) AND beats_null "
    "(same-horizon same-direction unmanaged hold, computed from the ledger's own recorded "
    "bar_close -- see module docstring ARMING BAR). armable=true only when all three hold. "
    "Retired-spec (ssr-v1) round trips are excluded from all of the above and reported "
    "separately under legacy_evidence, clearly labeled, non-arming. Read/derived from "
    "ssr-shadow-would-be.jsonl; places no order, arms nothing."
)


# ── fail-open IO helpers (pattern matched to futures_mirror_shadow.py) ─────────────────────
def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = _et_now().strftime("%Y-%m-%d")
        ts = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(LOG_DIR / f"ssr-shadow-{day}.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{_os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    _os.replace(tmp, path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(default))


def _ensure_ledger_doc_header() -> None:
    if LEDGER_FILE.exists():
        return
    try:
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"_doc": LEDGER_DOC}) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _acquire_lock(now_et: pd.Timestamp) -> bool:
    """Exclusive-create lock serializing run_once's read-modify-write window. Two OVERLAPPING
    invocations (manual --once during a scheduled fire, etc.) would otherwise both read the
    same pre-write state and double-append entry rows to the append-only ledger (the installed
    task's -MultipleInstances IgnoreNew guards only the scheduled path). A lock older than
    LOCK_STALE_S is treated as a crashed holder and broken; an unreadable lock is treated as
    a writer mid-write and NOT broken (fail-open toward skipping — the next 15-min poll
    recovers)."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in (0, 1):
        try:
            fd = _os.open(str(LOCK_FILE), _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY)
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps({"pid": _os.getpid(), "ts_et": now_et.isoformat()}))
            return True
        except FileExistsError:
            try:
                held = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
                age_s = (now_et - pd.Timestamp(held["ts_et"])).total_seconds()
            except Exception:  # noqa: BLE001
                return False  # unreadable = writer mid-write; skip this poll
            if age_s > LOCK_STALE_S:
                try:
                    LOCK_FILE.unlink(missing_ok=True)
                except OSError:
                    return False
                continue  # stale holder broken -- retry the exclusive create once
            return False
    return False


def _release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


# ── ET clock (tz-aware; see module docstring "ALL DATETIMES ARE TZ-AWARE ET") ─────────────
def _et_now() -> pd.Timestamp:
    """Tz-aware ET `now`, layered on top of the repo's canonical et_clock.et_now() (which
    returns a NAIVE-but-ET value -- see et_clock.py's own docstring). Lazily re-imports
    et_clock on every call (mirrors futures_mirror_shadow._et_now()'s own rationale) so a
    test's `monkeypatch.setattr(et_clock, "et_now", ...)` is honored. tz_localize on an
    already-ET-wall-clock naive value just attaches tzinfo, no conversion -- correct. The
    twice-yearly DST-fold ambiguous hour is handled by NaT-then-forward-shift rather than
    raising, so a poll never crashes on the fold itself (fail-open)."""
    import et_clock  # noqa: PLC0415
    naive = et_clock.et_now()
    try:
        return pd.Timestamp(naive).tz_localize(ET_ZONE)
    except Exception:  # noqa: BLE001 -- DST fold/gap edge case
        return pd.Timestamp(naive).tz_localize(ET_ZONE, ambiguous=True, nonexistent="shift_forward")


# ── data fetch ("data_fetch light variant" -- see module docstring REUSE) ─────────────────
def fetch_bars_light(symbol: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    """Plain yfinance pull -> engine bar schema (timestamp_et tz-aware ET, open, high, low,
    close, volume), ascending, deduped. NO disk cache, NO provenance write (see module
    docstring's REUSE note for why futures.ssr.data_fetch is not used here). Fail-open ->
    None on any failure (empty response, network error, malformed frame), never raises."""
    try:
        import yfinance as yf  # noqa: PLC0415
        raw = yf.download(symbol, interval=interval, period=period, progress=False,
                          auto_adjust=False)
        if raw is None or raw.empty:
            return None
        if hasattr(raw.columns, "nlevels") and raw.columns.nlevels > 1:
            raw = raw.copy()
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.reset_index()
        tcol = next((c for c in raw.columns if c in ("Datetime", "Date")), raw.columns[0])
        ts = pd.to_datetime(raw[tcol], utc=True).dt.tz_convert(ET_ZONE)
        out = pd.DataFrame({
            "timestamp_et": ts,
            "open": pd.to_numeric(raw["Open"], errors="coerce"),
            "high": pd.to_numeric(raw["High"], errors="coerce"),
            "low": pd.to_numeric(raw["Low"], errors="coerce"),
            "close": pd.to_numeric(raw["Close"], errors="coerce"),
            "volume": pd.to_numeric(raw.get("Volume", 0), errors="coerce"),
        }).dropna(subset=["open", "high", "low", "close"])
        out = out.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
        if out.empty:
            return None
        return out[["timestamp_et", "open", "high", "low", "close", "volume"]]
    except Exception:  # noqa: BLE001
        return None


# ── watermark / new-signal selection (pure) ────────────────────────────────────────────────
def _select_new_signals(signals: list[SSRSignal], watermark_ts: Optional[pd.Timestamp],
                        n_bars: int, lookback: int = LOOKBACK_BARS) -> list[SSRSignal]:
    """PURE. A signal is eligible to open a NEW position iff its ts_et is strictly newer than
    `watermark_ts` (never re-fires an already-scanned signal -- the detector is re-run fresh
    every poll and is deterministic, so without this a stationary signal would reappear every
    poll) AND its bar_index falls within the last `lookback` bars of THIS poll's window (a
    safety cap independent of the watermark). `watermark_ts=None` (cold start, handled by the
    caller before this is ever called) returns [] defensively -- this function never opens a
    position off "no watermark yet"."""
    if watermark_ts is None:
        return []
    eligible = [s for s in signals if s.ts_et > watermark_ts and s.bar_index >= n_bars - lookback]
    return sorted(eligible, key=lambda s: s.ts_et)


# ── runner selection (byte-for-byte parity with backtest_runner.py::_pick_runner) ─────────
def _pick_runner(snapshot, entry: float, tp1: float, direction: str,
                 r_points: float) -> tuple[float, str]:
    """PURE. Nearest opposing level from `snapshot.all_levels()` strictly beyond tp1 in the
    profit direction; else a fixed 3R. Either way capped at 5R from entry. Returns
    (runner_price, source) with source in {"level","fallback_3r","capped_5r"} -- same
    selection rule as backtest_runner.py::_pick_runner (re-implemented here, not imported,
    because that module's helper is private/underscore and this script's poll model is
    otherwise decoupled from backtest_runner -- see module docstring REUSE note)."""
    sign = 1.0 if direction == "long" else -1.0
    candidates: list[float] = []
    if snapshot is not None:
        for _name, price in snapshot.all_levels():
            price = float(price)
            if (sign > 0 and price > tp1) or (sign < 0 and price < tp1):
                candidates.append(price)
    cap_price = entry + sign * RUNNER_CAP_R_MULT * r_points
    if candidates:
        nearest = min(candidates) if sign > 0 else max(candidates)
        if (sign > 0 and nearest > cap_price) or (sign < 0 and nearest < cap_price):
            return cap_price, "capped_5r"
        return nearest, "level"
    return entry + sign * RUNNER_FALLBACK_R_MULT * r_points, "fallback_3r"


# ── position open ────────────────────────────────────────────────────────────────────────
def _signal_ref(config_name: str, signal: SSRSignal) -> str:
    return f"{config_name}|{signal.direction}|{signal.level_name}|{signal.ts_et.strftime('%Y-%m-%dT%H:%M')}"


def _spec_version_for_config(config_name: str) -> str:
    """A row's spec_version is DERIVED from its own `config` value, never from a stamped
    field that could be missing/stale on an old in-memory position dict (see module
    docstring RESPEC section). A position whose `config` is a LEGACY_CONFIG_ALIASES value
    (the retired full-size "NQ"/"GC" literals) is always ssr-v1, regardless of what
    SPEC_VERSION this running code currently is -- a legacy position never "graduates" to
    the current spec just because it's still being walked forward under this build."""
    if config_name in LEGACY_CONFIG_ALIASES.values():
        return "ssr-v1"
    return SPEC_VERSION


def open_position(config_name: str, signal: SSRSignal, snapshot, instrument) -> dict:
    """PURE. Builds a brand-new position dict (never mutates `signal`/`snapshot`). Entry =
    signal's own reaction-bar close +/- 1 tick slippage (module docstring step 7). Deadline =
    16:55 ET the SAME calendar day as the signal (single-session -- entries only ever fire
    03:00-15:00 ET, so 16:55 same day is always hours away)."""
    direction = signal.direction
    sign = 1.0 if direction == "long" else -1.0
    tick = float(instrument.tick_size)
    entry = float(signal.entry_ref_close) + sign * tick
    stop = float(signal.stop_price)
    r_points = abs(entry - stop)
    tp1 = entry + sign * TP1_R_MULT * r_points
    runner, runner_source = _pick_runner(snapshot, entry, tp1, direction, r_points)
    entry_ts = signal.ts_et
    deadline_et = entry_ts.normalize().replace(hour=FLAT_HOUR_ET, minute=FLAT_MINUTE_ET,
                                               second=0, microsecond=0)
    return {
        "signal_ref": _signal_ref(config_name, signal), "config": config_name,
        "direction": direction, "level_name": signal.level_name, "status": "open",
        "qty_open": QTY, "entry": round(entry, 6), "stop": round(stop, 6),
        "tp1": round(tp1, 6), "runner": round(runner, 6), "runner_source": runner_source,
        "r_points": round(r_points, 6), "tp1_filled": False,
        "entry_time_et": entry_ts.isoformat(), "signal_ts_et": entry_ts.isoformat(),
        "last_processed_bar_ts_et": entry_ts.isoformat(),
        "deadline_et": deadline_et.isoformat(), "closed_at_et": None,
        "sweep_extreme": float(signal.sweep_extreme),
    }


def _entry_event(position: dict) -> dict:
    return {
        "ts_et": position["entry_time_et"], "config": position["config"],
        "signal_ref": position["signal_ref"], "direction": position["direction"],
        "event": EV_ENTRY, "reason": "signal_fired", "level_name": position["level_name"],
        "entry": position["entry"], "stop": position["stop"], "tp1": position["tp1"],
        "runner": position["runner"], "fill_price": position["entry"],
        "bar_close": position["entry"], "exit_qty": 0,
        "qty_open_after": position["qty_open"], "pnl_pts": 0.0, "pnl_usd": 0.0,
        "spec_version": _spec_version_for_config(position["config"]),
    }


# ── per-bar exit decision (identical doctrine to backtest_runner.py / futures_sim.py) ─────
def decide_bar_events(position: dict, bar: dict, instrument) -> tuple[list[dict], dict]:
    """PURE (never mutates `position` -- returns a NEW dict). Evaluates exactly ONE completed
    bar against `position`'s current stop/tp1/runner. Mirrors
    futures.futures_sim.simulate_futures's own per-bar fill-order EXACTLY (stop-checked-
    before-target on a same-bar conflict; a same-bar runner touch while still pre-TP1
    implicitly credits the TP1 leg first, both legs stamped to this same bar -- see that
    module's per-bar loop for the byte-for-byte precedent this reproduces incrementally):

      pre-TP1:  1) fixed stop hit -> full close, reason=stopped_pre_tp1
                2) runner hit (implies tp1 also crossed this bar) -> tp1 leg (2 qty) THEN
                   close leg (1 qty) at runner, reason=runner, same bar timestamp
                3) tp1 only hit -> partial fill (2 qty), stop -> breakeven (entry), HOLD
                4) none hit -> silent hold, only last_processed_bar_ts_et advances
      post-TP1: 1) breakeven stop hit -> full close, reason=stopped_be
                2) runner hit -> full close, reason=runner
                3) none hit -> silent hold

    DEADLINE OVERRIDE (checked LAST, unconditional): if the position is still open after the
    above and this bar's own timestamp is at/after its `deadline_et` (16:55 ET the signal's
    own trading day), force-close whatever qty remains at this bar's CLOSE, reason=time_flat
    -- this can co-occur with a TP1 partial that just filled earlier in this same function
    call (the runner leg is simply flattened immediately instead of continuing to hold)."""
    if position.get("status") != "open" or position.get("qty_open", 0) <= 0:
        return [], position

    direction = position["direction"]
    long = direction == "long"
    hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
    ts = bar["ts_et"]
    pos = dict(position)
    events: list[dict] = []

    def _leg(fill_price: float, qty: int) -> tuple[float, float]:
        pts = (fill_price - pos["entry"]) if long else (pos["entry"] - fill_price)
        usd = round(pts * instrument.point_value * qty - instrument.round_turn_usd * qty, 2)
        return round(pts, 6), usd

    def _row(event: str, reason: str, fill_price: float, qty: int, qty_open_after: int) -> dict:
        pts, usd = _leg(fill_price, qty)
        return {
            "ts_et": ts.isoformat(), "config": pos["config"], "signal_ref": pos["signal_ref"],
            "direction": direction, "event": event, "reason": reason,
            "level_name": pos["level_name"], "entry": pos["entry"], "stop": pos["stop"],
            "tp1": pos["tp1"], "runner": pos["runner"], "fill_price": round(fill_price, 6),
            "bar_close": round(close, 6), "exit_qty": qty, "qty_open_after": qty_open_after,
            "pnl_pts": pts, "pnl_usd": usd,
            "spec_version": _spec_version_for_config(pos["config"]),
        }

    if not pos["tp1_filled"]:
        stop_hit = (lo <= pos["stop"]) if long else (hi >= pos["stop"])
        if stop_hit:
            qty = pos["qty_open"]
            events.append(_row(EV_CLOSED, REASON_STOPPED_PRE_TP1, pos["stop"], qty, 0))
            pos.update(status="closed", qty_open=0, closed_at_et=ts.isoformat())
        else:
            runner_hit = (hi >= pos["runner"]) if long else (lo <= pos["runner"])
            tp1_hit = (hi >= pos["tp1"]) if long else (lo <= pos["tp1"])
            if runner_hit:
                remaining = pos["qty_open"] - TP1_QTY
                events.append(_row(EV_TP1, "tp1_touch_1_5R", pos["tp1"], TP1_QTY, remaining))
                events.append(_row(EV_CLOSED, REASON_RUNNER, pos["runner"], remaining, 0))
                pos.update(status="closed", qty_open=0, tp1_filled=True, stop=pos["entry"],
                          closed_at_et=ts.isoformat())
            elif tp1_hit:
                remaining = pos["qty_open"] - TP1_QTY
                events.append(_row(EV_TP1, "tp1_touch_1_5R", pos["tp1"], TP1_QTY, remaining))
                pos.update(qty_open=remaining, tp1_filled=True, stop=pos["entry"])
    else:
        be_hit = (lo <= pos["stop"]) if long else (hi >= pos["stop"])
        runner_hit = (hi >= pos["runner"]) if long else (lo <= pos["runner"])
        if be_hit:
            qty = pos["qty_open"]
            events.append(_row(EV_CLOSED, REASON_STOPPED_BE, pos["stop"], qty, 0))
            pos.update(status="closed", qty_open=0, closed_at_et=ts.isoformat())
        elif runner_hit:
            qty = pos["qty_open"]
            events.append(_row(EV_CLOSED, REASON_RUNNER, pos["runner"], qty, 0))
            pos.update(status="closed", qty_open=0, closed_at_et=ts.isoformat())

    if pos["status"] == "open":
        deadline = pd.Timestamp(pos["deadline_et"])
        if ts >= deadline:
            qty = pos["qty_open"]
            events.append(_row(EV_CLOSED, REASON_TIME_FLAT, close, qty, 0))
            pos.update(status="closed", qty_open=0, closed_at_et=ts.isoformat())

    pos["last_processed_bar_ts_et"] = ts.isoformat()
    return events, pos


def walk_open_position(position: dict, bars: pd.DataFrame, instrument) -> tuple[list[dict], dict]:
    """Feeds every bar in `bars` strictly newer than `position["last_processed_bar_ts_et"]`,
    in chronological order, through `decide_bar_events`, stopping early once the position
    closes. PURE given `bars` (never mutates `position`; returns a fresh dict). A poll that
    only sees stale/no-new bars for this position (e.g. between two 15-min ticks with no new
    bar yet) is a correct, cheap no-op -- returns ([], position) unchanged."""
    if position.get("status") != "open":
        return [], position
    last_ts = pd.Timestamp(position["last_processed_bar_ts_et"])
    new_bars = bars.loc[bars["timestamp_et"] > last_ts].sort_values("timestamp_et")
    events: list[dict] = []
    pos = position
    for row in new_bars.itertuples(index=False):
        if pos.get("status") != "open":
            break
        bar = {"ts_et": row.timestamp_et, "high": row.high, "low": row.low, "close": row.close}
        evs, pos = decide_bar_events(pos, bar, instrument)
        events.extend(evs)
    return events, pos


def _prune_closed_positions(positions: dict, now_et: pd.Timestamp,
                            retention_days: int = POSITION_RETENTION_DAYS) -> dict:
    out = {}
    cutoff = now_et - pd.Timedelta(days=retention_days)
    for key, pos in positions.items():
        if pos.get("status") != "closed":
            out[key] = pos
            continue
        try:
            ts = pd.Timestamp(pos.get("closed_at_et")) if pos.get("closed_at_et") else None
        except Exception:  # noqa: BLE001
            ts = None
        if ts is None or ts >= cutoff:
            out[key] = pos
    return out


# ── state load ───────────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    return _load_json(STATE_FILE, {
        "_doc": STATE_DOC, "spec_version": SPEC_VERSION, "configs": {}, "positions": {},
        "last_run_et": None, "errors": [],
    })


def load_ledger_rows(path: Optional[Path] = None) -> list[dict]:
    """Fail-open: missing/corrupt file -> []. Skips the `_doc` header line and any malformed
    JSON line."""
    p = path if path is not None else LEDGER_FILE
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if "_doc" in row:
            continue
        rows.append(row)
    return rows


# ── arming-bar progress (module docstring ARMING BAR) ──────────────────────────────────────
def group_by_signal(rows: list[dict]) -> dict:
    groups: dict = {}
    for r in rows:
        ref = r.get("signal_ref")
        if not ref:
            continue
        groups.setdefault(ref, []).append(r)
    for ref in groups:
        groups[ref].sort(key=lambda r: r.get("ts_et", ""))
    return groups


def compute_round_trips(rows: list[dict]) -> list[dict]:
    """PURE. One entry per signal_ref with a CLOSED row bringing qty_open_after to 0. Sums
    pnl_usd across every row for that signal_ref (captures the tp1 leg + final leg).

    Each trip carries a `spec_version`: preferred from the row's own `spec_version` field
    (every row `_entry_event`/`_row` write from the ssr-v2 respec onward stamps this); rows
    written BEFORE that respec never carried the field at all, so it falls back to deriving
    it from the row's own `config` value via `_spec_version_for_config` (a LEGACY_CONFIG_
    ALIASES value -- the retired "NQ"/"GC" literals -- is always "ssr-v1"). This is the ONLY
    mechanism `compute_progress` uses to tell fresh ssr-v2 evidence apart from retired ssr-v1
    evidence -- see module docstring RESPEC section."""
    trips = []
    for ref, events in group_by_signal(rows).items():
        closing = [e for e in events if e.get("event") == EV_CLOSED and e.get("qty_open_after") == 0]
        if not closing:
            continue
        last_close = closing[-1]
        total_pnl = round(sum(float(e.get("pnl_usd") or 0.0) for e in events), 2)
        entry_row = next((e for e in events if e.get("event") == EV_ENTRY), events[0])
        spec_version = entry_row.get("spec_version") or _spec_version_for_config(entry_row.get("config"))
        trips.append({
            "signal_ref": ref, "config": entry_row.get("config"),
            "direction": entry_row.get("direction"), "entry": entry_row.get("entry"),
            "entry_ts_et": entry_row.get("ts_et"), "total_pnl_usd": total_pnl,
            "closed_at_et": last_close.get("ts_et"), "close_reason": last_close.get("reason"),
            "close_bar_close": last_close.get("bar_close"),
            "level_name": entry_row.get("level_name"),
            "spec_version": spec_version,
        })
    trips.sort(key=lambda t: t.get("closed_at_et") or "")
    return trips


def compute_null_pnl(trip: dict, instrument_lookup: Callable[[str], Any]) -> Optional[float]:
    """PURE. Same-direction UNMANAGED hold (full original qty=3, one round-turn commission)
    from `trip["entry"]` to `trip["close_bar_close"]` -- the closing event's own recorded bar
    close, never a network refetch (module docstring ARMING BAR). Returns None (never a
    fabricated number, C7) if entry/close/direction/config is missing or the config's
    instrument can't be resolved."""
    entry = trip.get("entry")
    close_px = trip.get("close_bar_close")
    direction = trip.get("direction")
    config = trip.get("config")
    if entry is None or close_px is None or direction not in ("long", "short") or not config:
        return None
    try:
        instrument = instrument_lookup(config)
    except Exception:  # noqa: BLE001
        return None
    long = direction == "long"
    pts = (close_px - entry) if long else (entry - close_px)
    return round(pts * instrument.point_value * QTY - instrument.round_turn_usd * QTY, 2)


def _null_check_block(trips: list[dict], total_pnl: float,
                      instrument_lookup: Callable[[str], Any]) -> dict:
    """PURE. Same shape/semantics for ANY trip population (current-spec OR legacy) -- shared
    by `compute_progress` for both the v2 arming-bar null_check and the legacy_evidence
    null_check, so the two can never independently drift apart (the defect this function
    fixes: they DID drift, when the legacy block was first written without ever calling this
    logic at all -- see the QUARANTINE-INTEGRITY comment at the `legacy_evidence` call site)."""
    n = len(trips)
    null_pnls: list[float] = []
    unavailable = 0
    for t in trips:
        v = compute_null_pnl(t, instrument_lookup)
        if v is None:
            unavailable += 1
        else:
            null_pnls.append(v)
    if n == 0:
        return {"evaluated": False, "coverage": "0/0", "unavailable": 0}
    if null_pnls:
        null_total = round(sum(null_pnls), 2)
        return {"evaluated": True, "null_total_pnl_usd": null_total,
               "beats_null": bool(total_pnl > null_total),
               "coverage": f"{len(null_pnls)}/{n}", "unavailable": unavailable}
    return {"evaluated": False, "coverage": f"0/{n}", "unavailable": unavailable,
           "reason": f"null unavailable for all {n} round trips"}


def compute_progress(rows: list[dict], *, instrument_lookup: Optional[Callable] = None,
                     now_et: Optional[pd.Timestamp] = None,
                     latest_close_by_config: Optional[dict[str, float]] = None) -> dict:
    """PURE given `rows`/`instrument_lookup`/`now_et`/`latest_close_by_config`. Never raises.

    RESPEC (ssr-v2, 2026-08-23): the arming bar is a FRESH FORWARD CLOCK for THIS spec
    version only -- round trips scored under a retired spec_version (ssr-v1's full-size
    NQ/GC contracts, ~326x this book's own equity per the pre-respec fundability disclosure)
    NEVER count toward armable=true again, no matter how many close. They are retained
    verbatim in the SAME ledger and reported below as `legacy_evidence`, clearly labeled,
    for transparency only -- see module docstring RESPEC section."""
    if now_et is None:
        now_et = _et_now()
    instrument_lookup = instrument_lookup or get_ssr
    all_trips = compute_round_trips(rows)
    trips = [t for t in all_trips if t.get("spec_version") == SPEC_VERSION]
    legacy_trips = [t for t in all_trips if t.get("spec_version") != SPEC_VERSION]

    n = len(trips)
    total_pnl = round(sum(t["total_pnl_usd"] for t in trips), 2)
    avg_pnl = round(total_pnl / n, 2) if n else None
    positive_expectancy = bool(n > 0 and total_pnl > 0)

    null_check = _null_check_block(trips, total_pnl, instrument_lookup)
    beats_null: Optional[bool] = null_check.get("beats_null") if null_check.get("evaluated") else None

    armable = bool(n >= ARMING_MIN_ROUND_TRIPS and positive_expectancy and beats_null is True)

    legacy_n = len(legacy_trips)
    legacy_total_pnl = round(sum(t["total_pnl_usd"] for t in legacy_trips), 2)
    legacy_versions = sorted({t.get("spec_version") or "ssr-v1" for t in legacy_trips})
    # QUARANTINE-INTEGRITY RULE (2026-08-23, post-mortem on commit 77442e70's own defect): a
    # quarantine that retires HALF of an evidence pair -- keeping the flattering P&L figure
    # while dropping the null comparison it failed -- is WORSE than deleting both. It leaves a
    # citable number with its refutation silently removed, which is exactly what happened here
    # (v1's beats_null=False / null_total_pnl_usd=30828.09 was dropped when this legacy block
    # was first written, un-sourcing a figure already cited in analysis/deep-research/
    # PROFITABILITY-ORDER-2026-08-23.md). The rule for the next respec: preserve the WHOLE
    # legacy evidence record (P&L AND its null comparison) or none of it -- never split them.
    legacy_null_check = _null_check_block(legacy_trips, legacy_total_pnl, instrument_lookup)

    return {
        "_doc": PROGRESS_DOC, "updated_et": now_et.isoformat(), "spec_version": SPEC_VERSION,
        "n_round_trips": n, "total_pnl_usd": total_pnl, "avg_pnl_usd_per_trip": avg_pnl,
        "positive_expectancy": positive_expectancy, "null_check": null_check,
        "arming_bar": {"round_trips_needed": ARMING_MIN_ROUND_TRIPS, "round_trips_have": n,
                       "expectancy_positive": positive_expectancy, "beats_null": beats_null,
                       "armable": armable},
        "legacy_evidence": {
            "spec_versions": legacy_versions,
            "n_round_trips": legacy_n,
            "total_pnl_usd": legacy_total_pnl,
            "status": "HISTORICAL -- NOT counted toward the arming_bar above",
            "null_check": {
                **legacy_null_check,
                "label": "ssr-v1 / HISTORICAL -- NOT counted toward the v2 arming_bar above; "
                         "the arming_bar's beats_null is computed exclusively from THIS spec "
                         "version's own fresh evidence (see arming_bar block).",
            },
            "note": ("scored under a RETIRED spec (full-size NQ/GC contracts -- ~326x this "
                    "book's fundable size at qty=3; see fundability below for the ssr-v2 "
                    "recompute). Retained verbatim in the same ledger for audit "
                    "transparency; excluded from n_round_trips/total_pnl_usd/"
                    "positive_expectancy/beats_null/armable above by spec_version, never "
                    "deleted, never rescored, never silently merged in. Its null_check is "
                    "retained on the SAME terms -- a quarantine keeps the whole evidence pair "
                    "(P&L and the null it was measured against) or none of it, never one "
                    "half.") if legacy_n else
                    "no legacy (pre-respec) round trips in the ledger.",
        },
        "fundability": _fundability(total_pnl, latest_close_by_config or {}),
    }


# ── FUNDABILITY DISCLOSURE ─────────────────────────────────────────────────────────────────
# ORIGINAL FINDING (2026-08-13): total_pnl_usd was scored on FULL-SIZE NQ (point_value 20.0)
# and GC (100.0), because CONFIGS was keyed "NQ"/"GC" and get_ssr resolved those to the full
# contracts. One full NQ at ~29,850 is ~$597,000 of notional; at qty=3 that's ~$1.79M against
# a book holding a few thousand dollars -- a ratio of ~300x+: arithmetically correct, and
# operationally impossible. That finding is WHY the RESPEC (module docstring) switched
# CONFIGS to MNQ/MGC as spec_version ssr-v2 (2026-08-23).
#
# _fundability() below no longer hand-types a snapshot number -- it recomputes the SAME
# notional/equity ratio LIVE every poll, using (a) REAL prices observed THIS poll
# (`latest_close_by_config`, sourced from the very bars `_run_once_unlocked` already fetched
# -- never a stale comment, never a second network call) and (b) this book's OWN recorded
# equity (automation/state/futures/account.json -- never a guessed/hand-typed number). The
# point-value figures come straight from get_ssr()'s live registry, so this can never drift
# out of sync with backtest/futures/instruments.py or backtest/futures/ssr/ssr_instruments.py
# the way a bare module-level ratio constant could have.
FUTURES_ACCOUNT_FILE = STATE_DIR / "account.json"


def _load_futures_equity() -> tuple[Optional[float], str]:
    """Fail-open equity lookup against the tastytrade-sandbox futures book (account_id
    5WW73759) futures_mirror_shadow.py already trades against (its own docstring names this
    account directly) -- NEVER a hardcoded/guessed number. Returns (equity, source_label);
    (None, 'unavailable') if the file can't be read/parsed -- callers must handle None, never
    fabricate a fallback (C7)."""
    try:
        data = json.loads(FUTURES_ACCOUNT_FILE.read_text(encoding="utf-8"))
        eq = data.get("equity")
        if isinstance(eq, (int, float)) and eq > 0:
            broker = data.get("broker", "?")
            acct = data.get("account_id", "?")
            return float(eq), f"{FUTURES_ACCOUNT_FILE.name}:equity ({broker} {acct})"
    except (OSError, json.JSONDecodeError):
        pass
    return None, "unavailable"


def _fundability(total_pnl_usd: float, latest_close_by_config: dict[str, float]) -> dict:
    """Recomputes notional at qty=3 under the CURRENT CONFIGS (MNQ/MGC) using real prices
    observed THIS poll and this book's own recorded equity. `still_leveraged_by_design`
    matters: futures are ALWAYS a margined/leveraged product, so notional will always exceed
    equity by a large multiple -- that is not itself a red flag. What this disclosure claims
    is narrower and fully grounded in this repo's own numbers: the SAME ratio methodology
    that flagged ssr-v1 as impossible (~300x+) drops by exactly the point-value ratio
    (derived live, not hand-typed) under ssr-v2 -- NOT a claim that any specific broker's
    margin table approves this size (unverified in-repo)."""
    equity, equity_source = _load_futures_equity()
    per_config: dict[str, Any] = {}
    total_notional = 0.0
    any_price_missing = False
    for cfg_name in CONFIGS:
        try:
            micro = get_ssr(cfg_name)
        except Exception as e:  # noqa: BLE001
            per_config[cfg_name] = {"notional_usd": None,
                                    "reason": f"instrument_lookup_failed:{type(e).__name__}"}
            any_price_missing = True
            continue
        full_alias = LEGACY_CONFIG_ALIASES.get(cfg_name)
        full_point_value = None
        if full_alias:
            try:
                full_point_value = get_ssr(full_alias).point_value
            except Exception:  # noqa: BLE001
                full_point_value = None
        price = latest_close_by_config.get(cfg_name)
        if price is None:
            per_config[cfg_name] = {
                "symbol": micro.symbol, "point_value": micro.point_value,
                "notional_usd": None, "reason": "no_price_observed_this_poll",
            }
            any_price_missing = True
            continue
        notional = round(price * micro.point_value * QTY, 2)
        total_notional += notional
        point_ratio = (round(full_point_value / micro.point_value, 2)
                       if full_point_value else None)
        per_config[cfg_name] = {
            "symbol": micro.symbol, "point_value": micro.point_value, "last_price": price,
            "qty": QTY, "notional_usd": notional,
            "point_value_ratio_vs_full_size": point_ratio,
        }

    ratio = round(total_notional / equity, 1) if equity else None
    return {
        "_doc": ("RESPEC'd 2026-08-23 for ssr-v2 -- see setup/scripts/ssr_shadow.py module "
                "docstring RESPEC section."),
        "scored_on": f"micro contracts per live CONFIGS ({', '.join(CONFIGS)})",
        "per_config": per_config,
        "equity_usd": equity, "equity_source": equity_source,
        "combined_worst_case_notional_usd": (None if any_price_missing
                                             else round(total_notional, 2)),
        "combined_notional_to_equity_ratio": ratio,
        "any_price_missing": any_price_missing,
        "still_leveraged_by_design": ("futures are margined/leveraged instruments -- notional "
                                      "exceeding equity is EXPECTED, not itself a red flag; "
                                      "this figure is not a broker-verified margin approval "
                                      "(unverified in-repo), only a like-for-like recompute of "
                                      "the same ratio that flagged ssr-v1 as impossible."),
        "why_it_matters": (f"total_pnl_usd ({total_pnl_usd}) above is scored on contracts this "
                           "book can actually hold at qty=3 -- point_value_ratio_vs_full_size "
                           "above (derived live from the Instrument registry, not hardcoded) "
                           "is the same ~10x reduction vs the pre-respec disclosure archived "
                           "in the module docstring's RESPEC section."),
    }


# ── per-config signal detection (default seam; injectable for tests) ──────────────────────
def default_signal_fn(bars: pd.DataFrame, snapshots: list, atr: pd.Series,
                      params: SSRParams) -> list[SSRSignal]:
    return SSRDetector(params).run(bars, snapshots, atr)


# ── orchestration ────────────────────────────────────────────────────────────────────────
def run_once(*, now_et: Optional[pd.Timestamp] = None,
            bar_fetcher: Optional[Callable[[str, str, str], Optional[pd.DataFrame]]] = None,
            signal_fn: Optional[Callable] = None) -> dict:
    """Lock-guarded wrapper around the poll pass: acquires the in-process/system-wide lock
    for the whole read-modify-write window, so overlapping invocations can never double-read
    stale state (second caller returns skipped_lock_held=True and touches nothing)."""
    if now_et is None:
        now_et = _et_now()
    if not _acquire_lock(now_et):
        return {"skipped_lock_held": True, "new_signals": 0, "opened": 0, "events": 0,
                "skipped_while_open": 0, "skipped_degenerate": 0, "skipped_long_signal": 0,
                "cold_start_configs": [], "positions_open": 0, "errors": []}
    try:
        return _run_once_unlocked(now_et=now_et, bar_fetcher=bar_fetcher, signal_fn=signal_fn)
    finally:
        _release_lock()


def _run_once_unlocked(*, now_et: pd.Timestamp,
            bar_fetcher: Optional[Callable[[str, str, str], Optional[pd.DataFrame]]] = None,
            signal_fn: Optional[Callable] = None) -> dict:
    """ONE poll pass across both configs. Never raises internally (every per-config step is
    try/except-guarded; failures land in the returned summary's `errors` list and the state
    file's `errors` field -- callers needing a hard signal inspect `summary["errors"]`).

    `bar_fetcher(symbol, interval, period) -> Optional[DataFrame]` and
    `signal_fn(bars, snapshots, atr, params) -> list[SSRSignal]` are injectable seams (both
    default to the real fetch/detector) -- tests use `signal_fn` to hand back canned
    SSRSignal objects without needing to hand-craft real sweep/shift/retest price geometry
    (the detector's OWN correctness is covered by backtest/tests/test_ssr_detector.py and
    siblings; this script's test suite covers ITS OWN logic -- dedupe, concurrency, exit math,
    fail-open -- against that seam)."""
    bar_fetcher = bar_fetcher or fetch_bars_light
    signal_fn = signal_fn or default_signal_fn

    errors: list[str] = []
    state = load_state()
    configs_state = dict(state.get("configs", {}))
    positions = dict(state.get("positions", {}))

    summary = {
        "new_signals": 0, "opened": 0, "events": 0, "skipped_while_open": 0,
        "skipped_degenerate": 0, "skipped_long_signal": 0, "cold_start_configs": [],
        "positions_open": 0, "errors": errors,
    }
    latest_close_by_config: dict[str, float] = {}  # fed to _fundability -- see that fn's doc

    _ensure_ledger_doc_header()

    for cfg_name, cfg in CONFIGS.items():
        try:
            bars = bar_fetcher(cfg["symbol"], cfg["interval"], cfg["period"])
        except Exception as e:  # noqa: BLE001
            errors.append(f"fetch_failed:{cfg_name}:{type(e).__name__}:{e}")
            continue
        if bars is None or len(bars) < MIN_BARS_REQUIRED:
            errors.append(f"insufficient_bars:{cfg_name}")
            continue

        bars = bars.iloc[:-1].reset_index(drop=True)  # drop the final in-progress bar
        if len(bars) < MIN_BARS_REQUIRED:
            errors.append(f"insufficient_bars_after_drop:{cfg_name}")
            continue

        try:
            atr = wilder_atr(bars, period=ATR_PERIOD)
            snapshots = build_levels(bars, h4_anchor=cfg["h4_anchor"],
                                    include_running=cfg["include_running"])
            params = SSRParams(zone_atr_mult=cfg["zone_atr_mult"],
                              sweep_atr_mult=cfg["sweep_atr_mult"])
            all_signals = signal_fn(bars, snapshots, atr, params)
        except Exception as e:  # noqa: BLE001
            errors.append(f"detector_failed:{cfg_name}:{type(e).__name__}:{e}")
            continue

        long_signals = [s for s in all_signals if s.direction != "short"]
        summary["skipped_long_signal"] += len(long_signals)
        short_signals = [s for s in all_signals if s.direction == "short"]

        n_bars = len(bars)
        last_bar_ts = bars["timestamp_et"].iloc[-1]
        latest_close_by_config[cfg_name] = float(bars["close"].iloc[-1])

        # ── legacy-alias open-position walk (RESPEC, ssr-v2, 2026-08-23) ──────────────────
        # Runs UNCONDITIONALLY (even through this config's own cold start below) so a
        # position still open under the RETIRED ssr-v1 full-size config (its `config` field
        # is literally "NQ"/"GC") at the moment this respec ships is never orphaned or
        # stalled waiting on MNQ/MGC's own fresh watermark. The bars fetched under cfg_name's
        # OWN `cfg["symbol"]` are byte-identical to what the legacy position needs (MNQ
        # tracks NQ's index price 1:1, only the $-multiplier differs -- module docstring
        # RESPEC section). Each position settles under ITS OWN recorded `config` value's
        # instrument spec (get_ssr(pos["config"])) -- a legacy NQ position keeps being priced
        # in full-size $ terms to its natural close; only NEW entries (below) ever use the
        # MNQ/MGC micro spec. LEGACY_CONFIG_ALIASES is never a source for opening a NEW
        # position.
        legacy_alias = LEGACY_CONFIG_ALIASES.get(cfg_name)
        walk_keys = [k for k, p in positions.items() if p.get("status") == "open"
                    and p.get("config") in (cfg_name, legacy_alias)]
        for key in walk_keys:
            pos_cfg = positions[key].get("config")
            try:
                pos_instrument = get_ssr(pos_cfg)
                events, new_pos = walk_open_position(positions[key], bars, pos_instrument)
                positions[key] = new_pos
                for ev in events:
                    _append_jsonl(LEDGER_FILE, ev)
                summary["events"] += len(events)
            except Exception as e:  # noqa: BLE001
                errors.append(f"manage_failed:{pos_cfg}:{key}:{type(e).__name__}:{e}")

        cfg_state = configs_state.get(cfg_name)
        watermark_ts = None
        if cfg_state and cfg_state.get("watermark_bar_ts_et"):
            try:
                watermark_ts = pd.Timestamp(cfg_state["watermark_bar_ts_et"])
            except Exception:  # noqa: BLE001
                watermark_ts = None

        if watermark_ts is None:
            # cold start (module docstring step 5): never backfill -- seed the watermark and
            # open nothing this poll, mirroring futures_mirror_shadow.py's own discipline.
            # (The legacy-alias walk above already ran regardless of this cold start.)
            configs_state[cfg_name] = {"watermark_bar_ts_et": last_bar_ts.isoformat(),
                                       "last_run_et": now_et.isoformat()}
            summary["cold_start_configs"].append(cfg_name)
            continue

        new_signals = _select_new_signals(short_signals, watermark_ts, n_bars)
        summary["new_signals"] += len(new_signals)

        open_key = next((k for k, p in positions.items()
                         if p.get("config") in (cfg_name, legacy_alias)
                         and p.get("status") == "open"), None)

        try:
            instrument = get_ssr(cfg_name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"instrument_lookup_failed:{cfg_name}:{type(e).__name__}:{e}")
            configs_state[cfg_name] = {"watermark_bar_ts_et": last_bar_ts.isoformat(),
                                       "last_run_et": now_et.isoformat()}
            continue

        for sig in new_signals:
            if open_key is not None:
                summary["skipped_while_open"] += 1
                continue
            tick = float(instrument.tick_size)
            sign = 1.0 if sig.direction == "long" else -1.0
            entry_px = float(sig.entry_ref_close) + sign * tick
            r_points = abs(entry_px - float(sig.stop_price))
            if r_points <= 0 or r_points < tick:
                summary["skipped_degenerate"] += 1
                continue
            snapshot = snapshots[sig.bar_index] if 0 <= sig.bar_index < len(snapshots) else None
            pos = open_position(cfg_name, sig, snapshot, instrument)
            positions[pos["signal_ref"]] = pos
            try:
                _append_jsonl(LEDGER_FILE, _entry_event(pos))
            except Exception as e:  # noqa: BLE001
                errors.append(f"ledger_write_failed:{cfg_name}:{type(e).__name__}:{e}")
            summary["opened"] += 1
            open_key = pos["signal_ref"]

        configs_state[cfg_name] = {"watermark_bar_ts_et": last_bar_ts.isoformat(),
                                   "last_run_et": now_et.isoformat()}

    positions = _prune_closed_positions(positions, now_et)
    summary["positions_open"] = sum(1 for p in positions.values() if p.get("status") == "open")

    try:
        _atomic_write_json(STATE_FILE, {
            "_doc": STATE_DOC, "spec_version": SPEC_VERSION, "configs": configs_state,
            "positions": positions, "last_run_et": now_et.isoformat(), "errors": errors,
        })
    except Exception as e:  # noqa: BLE001
        errors.append(f"state_write_failed:{type(e).__name__}:{e}")

    try:
        progress = compute_progress(load_ledger_rows(), now_et=now_et,
                                    latest_close_by_config=latest_close_by_config)
        _atomic_write_json(PROGRESS_FILE, progress)
    except Exception as e:  # noqa: BLE001
        errors.append(f"progress_failed:{type(e).__name__}:{e}")

    if errors:
        # Spec: errors land in the state file's errors list AND a line in the ledger meta.
        try:
            _append_jsonl(LEDGER_FILE, {"event": "error", "ts_et": now_et.isoformat(),
                                        "errors": list(errors)})
        except Exception:  # noqa: BLE001
            pass  # state file still carries the list; never let observability kill the pass

    return summary


def main() -> int:
    """CLI entry point. ALWAYS returns 0 (fail-open) -- every exception is caught + logged,
    never re-raised."""
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--once", action="store_true",
                        help="run exactly one poll pass (the only mode this script has)")
        ap.parse_args()
        summary = run_once()
        _log(f"pass complete: {json.dumps(summary, default=str)[:2000]}")
        print(json.dumps(summary, default=str))
        return 0
    except Exception as e:  # noqa: BLE001
        try:
            _log(f"main() FAILED (fail-open, exit 0 anyway): {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}")
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
