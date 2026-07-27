"""crypto_twin_signal_backtest.py -- does the crypto twin's ribbon+level signal have ANY
positive expectancy on real BTC/USD history, and which level-set config is least-bad?

J's ask (2026-07-26, "turning organic crypto trading ON tonight, I refuse to hand-pick
parameters"): measure this HONESTLY before flipping the switch. EXPECT A NULL -- this
script's job is to report the truth plainly, not to manufacture a winner.

READ-ONLY / NO-SIDE-EFFECT CONTRACT (fences from the task):
  * Never modifies any existing file. Only writes under analysis/crypto-twin/ (this
    script's own outputs + bar cache) and reads automation/state/crypto-twin/secrets.json
    (never prints its values) + automation/state/params.json (read-only, both already
    gitignored/tracked-but-not-secret respectively).
  * Places NO orders. Does NOT import crypto_twin_broker or anything broker-adjacent --
    credentials are loaded locally (see _load_market_data_creds) by re-reading the same
    secrets.json crypto_twin_broker.load_creds() reads, NOT by importing that module.
  * $0, pure Python + requests + scipy/numpy (already in backtest/.venv) + the repo's own
    crypto.lib / crypto_twin_signal / crypto_twin_levels primitives. No LLM calls.

MECHANISM REUSE (per the task): the SEE->DECIDE stage is NOT reimplemented. It calls the
twin's REAL crypto_twin_levels.build_level_set() and crypto_twin_signal.evaluate() at every
bar, feeding only closed bars up to that point (C6 -- no look-ahead). The one gap: evaluate()
does not expose max_distance_pct as a parameter (it's a hardcoded default inside
crypto_twin_levels.nearest_directional_level, which evaluate() calls without overriding it).
To make that grid axis genuinely testable while still running evaluate()'s real code
verbatim, this script temporarily monkeypatches crypto_twin_levels.nearest_directional_level
in-process (restored immediately after each config) -- see patched_max_distance(). This is
the ONLY way evaluate() and build_level_set() run: unmodified, on disk untouched.

EXIT MODEL (the part that is genuinely NEW code, since exit_manager.py is option-premium-
native and cannot run against a spot BTC price -- see module docstring precedent in
crypto_twin_core.py for why exit_manager's % thresholds don't transfer to spot without a
conversion): automation/state/params.json's production percentages ARE option-premium
percentages (catastrophe cap -50%, TP1 +50%, runner target 2.5x = +150%, profit-lock arms
+5%/trails 12.5%) -- meaningless applied directly to spot BTC's %-moves (a 50% BTC 5-min
move never happens). The LEVERAGE LENS (lens_return = spot_return * M) rescales spot moves
into the same %-space those thresholds were calibrated for, standing in for "how much would
a 0DTE option's premium have moved for this spot move" (an M-delta analogy). Full state
machine: see simulate_lens_trade(). Friction (0.09% round-trip, real measured twin-fill
magnitude) is charged in SPOT space BEFORE the lens multiply -- net_lens = gross_lens -
FRICTION_RT * M -- so it scales with M exactly as real bid-ask/slippage friction scales as a
% of a leveraged/option-premium base when the same spot notional trades through a smaller
premium base. Higher M does not create edge; it rescales wins, losses, AND friction together.

GRID (pre-registered HERE, before any cell is scored -- 181-cells-zero-ships history means
no hand-picking, no post-hoc cherry-picking):
  level_set        in {A: prior-UTC-day H/L/C + intraday H/L (twin's real build_level_set),
                        B: A + round numbers @ $500 increments,
                        C: A + round numbers @ $1000 increments}
  max_distance_pct in {0.25, 0.5, 1.0}
  min_stack_bars   in {2, 3}
  exit variant     in {lens M=20, lens M=40, lens M=80, fixed_spot_control (TP+0.5%/-0.5%)}
  => 3 * 3 * 2 * 4 = 72 cells, ALL reported, none cherry-picked.

HONEST GATES: 70%/30% tuning/held-out split by calendar date (held-out = most recent 30%,
touched once). A cell PASSES only if: positive mean return on tuning AND positive mean
return on held-out AND n_trades (tuning+holdout) >= 30 AND survives Benjamini-Hochberg FDR
at q<=0.10 applied across the WHOLE 72-cell grid at once (p-value = one-sided test of
tuning-set mean return > 0).

DEPLOYABILITY CAVEAT (mechanism fidelity, not an afterthought): Alpaca crypto is cash/
long-only -- crypto_twin_core.py's own docstring states ENTER_BEAR verdicts are "logged-but-
skipped" in production (no short leg exists). This script scores BOTH directions in the
main 72-cell grid for completeness, but the recommended-config section explicitly separates
bull-only performance (the only side deployable tonight without margin/short capability).
"""
from __future__ import annotations

import json
import math
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))                              # crypto.lib.* (namespace package)
sys.path.insert(0, str(REPO / "setup" / "scripts"))         # crypto_twin_signal / crypto_twin_levels

from crypto.lib.bar import Bar, BarSeries                   # noqa: E402
from crypto.lib.bar_reader import closed_bars_only          # noqa: E402
from crypto.lib.levels import Level, round_number_levels    # noqa: E402

import crypto_twin_levels as tl                             # noqa: E402
import crypto_twin_signal as sig                             # noqa: E402

# ---------------------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------------------
OUT_DIR = REPO / "analysis" / "crypto-twin"
CACHE_PATH = OUT_DIR / "btc_5m_cache.json"
SECRETS_PATH = REPO / "automation" / "state" / "crypto-twin" / "secrets.json"
PARAMS_PATH = REPO / "automation" / "state" / "params.json"
MD_OUT = OUT_DIR / "SIGNAL-BACKTEST-2026-07-26.md"
JSON_OUT = OUT_DIR / "SIGNAL-BACKTEST-2026-07-26.json"

ALPACA_DATA_HOST = "https://data.alpaca.markets"
SYMBOL = "BTC/USD"
GRANULARITY_SECONDS = 300  # 5m

# ---------------------------------------------------------------------------------------
# Data-fetch window
# ---------------------------------------------------------------------------------------
TARGET_DAYS = 120  # "aim 60-120 days" -- Alpaca crypto history comfortably covers this
                    # (verified live 2026-07-26: BTC/USD 5m bars exist back to at least
                    # 2026-01-15, ~190 days before this run -- see the fetch step's provenance
                    # stamp for exactly what was returned).

# ---------------------------------------------------------------------------------------
# Signal-walk tuning (NOT swept -- performance/warmup knobs, not the pre-registered grid)
# ---------------------------------------------------------------------------------------
START_IDX = 600          # >= 2 UTC days (576 5m bars) of context before the first bar scored
LEVEL_WINDOW = 700        # bars fed to build_level_set() -- bounded lookback; build_level_set
                          # only ever uses [prior_UTC_day_start, today_end), so anything older
                          # is provably inert -- this is a speed optimization, not a semantics
                          # change (see module docstring's "GRID" section preamble).
RIBBON_WINDOW = 2000      # bars fed to evaluate()/compute_ribbon() -- EMA-48's causal decay
                          # ((1-2/49)^500 ~= 1e-9) means a 2000-bar window converges to the
                          # SAME ribbon value a full-history EMA would produce at that index,
                          # to far better precision than BTC's own price noise. Also a speed
                          # optimization, not a semantics change.
MAX_HOLD_BARS = 48        # 4 hours @ 5m -- fixed 0DTE-session-length analog (NOT swept; the
                          # task's grid axes are level_set/max_distance_pct/min_stack_bars/
                          # exit-variant only). Also used as the flat-rescan skip distance
                          # after any trigger (see run_signal_walk) so trades never overlap
                          # regardless of exit variant.

# ---------------------------------------------------------------------------------------
# Exit-shape constants -- sourced VERBATIM from automation/state/params.json (read-only) /
# the task's explicit instructions where params.json and the task text differ (tp1_qty_
# fraction: params.json's LIVE value is 0.8 (Safe) but the task explicitly specifies 0.667,
# the Bold value also live in params.json under the same key name for the aggressive arm --
# used here exactly as instructed, cited so the discrepancy is never silently swallowed).
# ---------------------------------------------------------------------------------------
CATASTROPHE_LENS = -0.50      # params.json: premium_stop_pct = -0.5
TP1_TARGET_LENS = 0.50        # params.json: tp1_premium_pct = 0.5
TP1_QTY_FRACTION = 0.667      # task-specified explicitly (params.json Bold-arm value; Safe-arm
                              # value is 0.8 -- see docstring note above)
RUNNER_TARGET_LENS = 1.50     # params.json: runner_max_premium_pct = 2.5 -> premium reaches
                              # 2.5x entry = +150% return
PROFIT_LOCK_ARM_LENS = 0.05   # params.json: v15_profit_lock_threshold_pct = 0.05
PROFIT_LOCK_TRAIL_LENS = 0.125  # params.json: v15_profit_lock_trail_pct = 0.125
RUNNER_BE_FLOOR_AFTER_TP1 = True  # params.json: runner_be_stop_after_tp1 = true

FIXED_CONTROL_TP_PCT = 0.005   # task example: "TP +0.5% / stop -0.5%" (plain spot, no lens)
FIXED_CONTROL_STOP_PCT = -0.005

FRICTION_ROUND_TRIP = 0.0009  # 0.09% of notional, round-trip -- "measured from real fills"
                              # (crypto_twin_friction_calibration.py's mandate; charged in
                              # SPOT space before the lens multiply, see module docstring).

LEVERAGE_MS = [20, 40, 80]

# ---------------------------------------------------------------------------------------
# Pre-registered grid (frozen BEFORE any cell is scored -- literal constants below, read
# by build_grid() further down; nothing here is derived from a look at the data).
# ---------------------------------------------------------------------------------------
LEVEL_SET_VARIANTS = ["A", "B", "C"]
MAX_DISTANCE_PCTS = [0.25, 0.5, 1.0]
MIN_STACK_BARS_VALUES = [2, 3]

BH_ALPHA = 0.10
MIN_TRADES_GATE = 30


# =========================================================================================
# 1. CREDENTIALS (read-only; never logs/prints key or secret values)
# =========================================================================================
def _load_market_data_creds() -> Optional[dict]:
    """Mirrors crypto_twin_broker.load_creds()'s SHAPE (re-read locally, never imported --
    the task fence forbids importing that module). Read-only market-data use only; this
    script never places an order, so the "don't reuse Safe-2's key for orders" contamination
    concern in crypto_twin_broker's docstring does not apply here (bars/quotes are account-
    agnostic public data -- verified live 2026-07-10 per that module's own docstring)."""
    if not SECRETS_PATH.exists():
        return None
    try:
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    accounts = data.get("accounts", data)
    twin = accounts.get("twin") if isinstance(accounts, dict) else None
    if not isinstance(twin, dict):
        return None
    key = twin.get("key") or twin.get("api_key")
    secret = twin.get("secret") or twin.get("secret_key")
    if key and secret:
        return {"key": key, "secret": secret}
    return None


# =========================================================================================
# 2. DATA FETCH (Alpaca primary, paginated) + CACHE
# =========================================================================================
def _fetch_alpaca_paginated(creds: Optional[dict], start: datetime, end: datetime) -> list[dict]:
    headers = {}
    if creds:
        headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    url = f"{ALPACA_DATA_HOST}/v1beta3/crypto/us/bars"
    params = {"symbols": SYMBOL, "timeframe": "5Min", "sort": "asc", "limit": 10000,
              "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    all_rows: list[dict] = []
    page_token = None
    while True:
        req_params = dict(params)
        if page_token:
            req_params["page_token"] = page_token
        r = requests.get(url, params=req_params, headers=headers, timeout=30)
        r.raise_for_status()
        payload = r.json()
        rows = (payload.get("bars") or {}).get(SYMBOL, [])
        all_rows.extend(rows)
        page_token = payload.get("next_page_token")
        if not page_token:
            break
    return all_rows


def fetch_or_load_bars(*, refresh: bool = False) -> tuple[list[Bar], dict]:
    """Returns (bars, provenance). Uses the on-disk cache unless `refresh` (reruns are
    free per the task -- default behavior never re-hits the network once cached)."""
    if CACHE_PATH.exists() and not refresh:
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            bars = [Bar(open_time=datetime.fromisoformat(r["t"]), open=r["o"], high=r["h"],
                        low=r["l"], close=r["c"], volume=r["v"],
                        granularity_seconds=GRANULARITY_SECONDS, source=cached["source"])
                    for r in cached["bars"]]
            return bars, cached["provenance"]
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass  # fall through to a fresh fetch if the cache is unreadable/malformed

    creds = _load_market_data_creds()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=TARGET_DAYS)
    raw_rows: list[dict] = []
    source = "alpaca"
    fetch_error: Optional[str] = None
    try:
        raw_rows = _fetch_alpaca_paginated(creds, start, now)
        if not raw_rows:
            raise RuntimeError("alpaca returned zero bars")
    except Exception as e:  # noqa: BLE001 -- fall back honestly, never silently empty
        fetch_error = f"{type(e).__name__}: {e}"
        # Fallback per task's option (b): crypto.lib.data_sources (tri-source). Its yfinance/
        # coinbase 5m paths are capped far short of TARGET_DAYS (yfinance hardcodes "5d" for
        # <=300s granularity; coinbase caps at 300 candles/call = ~25h) -- this fallback will
        # cover a much SHORTER window than requested, and that shortfall is stamped into
        # provenance rather than hidden.
        from crypto.lib.data_sources import fetch_bars as ds_fetch_bars
        for alt_source in ("coinbase", "yfinance"):
            try:
                series = ds_fetch_bars(alt_source, "BTC-USD", GRANULARITY_SECONDS, count=300)
                if len(series) > 0:
                    source = alt_source
                    bars_out = list(series.bars)
                    prov = {"source": source, "fetch_error_primary_alpaca": fetch_error,
                            "requested_days": TARGET_DAYS, "actual_bars": len(bars_out),
                            "date_range": [bars_out[0].open_time.isoformat(),
                                          bars_out[-1].open_time.isoformat()],
                            "fetched_at_utc": now.isoformat(),
                            "shortfall_warning": f"fallback source {alt_source} could not "
                                                 f"cover {TARGET_DAYS}d -- see caps in "
                                                 "crypto/lib/data_sources.py"}
                    _write_cache(bars_out, source, prov)
                    return bars_out, prov
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError(f"all data sources failed; primary error: {fetch_error}")

    # dedupe + sort (defensive -- Alpaca returns sorted+unique in practice, but BarSeries's
    # constructor raises on any violation, so make this bulletproof rather than let a rare
    # server-side hiccup crash the whole run)
    by_ts: dict[str, dict] = {}
    for row in raw_rows:
        by_ts[row["t"]] = row  # last-write-wins on duplicate timestamp
    sorted_rows = sorted(by_ts.values(), key=lambda r: r["t"])

    bars = [Bar(open_time=datetime.fromisoformat(r["t"].replace("Z", "+00:00")),
                open=float(r["o"]), high=float(r["h"]), low=float(r["l"]), close=float(r["c"]),
                volume=float(r.get("v", 0.0)), granularity_seconds=GRANULARITY_SECONDS,
                source="alpaca")
           for r in sorted_rows]

    closed = closed_bars_only(
        BarSeries(symbol=SYMBOL, granularity_seconds=GRANULARITY_SECONDS, source="alpaca",
                  bars=tuple(bars)),
        now)
    bars = list(closed.bars)

    gaps = sum(1 for i in range(1, len(bars))
              if (bars[i].open_time - bars[i - 1].open_time).total_seconds() > 2 * GRANULARITY_SECONDS)

    provenance = {
        "source": "alpaca_v1beta3_crypto_us_bars", "symbol": SYMBOL,
        "granularity_seconds": GRANULARITY_SECONDS, "requested_days": TARGET_DAYS,
        "actual_bars": len(bars),
        "date_range": [bars[0].open_time.isoformat(), bars[-1].open_time.isoformat()] if bars else None,
        "fetched_at_utc": now.isoformat(), "gaps_gt_2x_granularity": gaps,
        "auth": "twin_creds" if creds else "unauthenticated_public_tier",
    }
    _write_cache(bars, "alpaca", provenance)
    return bars, provenance


def _write_cache(bars: list[Bar], source: str, provenance: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source, "provenance": provenance,
        "bars": [{"t": b.open_time.isoformat(), "o": b.open, "h": b.high, "l": b.low,
                  "c": b.close, "v": b.volume} for b in bars],
    }
    CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")


# =========================================================================================
# 3. LEVEL-SET VARIANTS (A = twin's real build_level_set; B/C add round numbers via the
#    reused crypto.lib.levels.round_number_levels primitive -- new EXTENSION code, since
#    crypto_twin_levels.py has no round-number concept; never edits that file)
# =========================================================================================
@dataclass(frozen=True)
class ExtendedLevelSet:
    """Duck-types TwinLevelSet's ONE consumed surface (`.all_levels`) -- evaluate() /
    nearest_directional_level never touch any other TwinLevelSet field, only
    `levels.all_levels`, so this wrapper is a safe, non-invasive extension point."""
    base: tl.TwinLevelSet
    extra: tuple

    @property
    def all_levels(self) -> list[Level]:
        return list(self.base.all_levels) + list(self.extra)

    @property
    def session_date_utc(self) -> str:
        return self.base.session_date_utc


def build_levelset_variant(level_bars: Sequence[Bar], now_utc: datetime, variant: str,
                           spot: float) -> ExtendedLevelSet:
    base = tl.build_level_set(level_bars, now_utc)
    extra: tuple = ()
    if variant == "B":
        extra = tuple(round_number_levels(spot, 500.0, radius=5))
    elif variant == "C":
        extra = tuple(round_number_levels(spot, 1000.0, radius=5))
    return ExtendedLevelSet(base=base, extra=extra)


@contextmanager
def patched_max_distance(max_distance_pct: float):
    """Temporarily overrides crypto_twin_levels.nearest_directional_level's default
    max_distance_pct so evaluate()'s REAL, unmodified call site (which never passes this
    kwarg explicitly) exercises the grid value under test. Restored unconditionally.
    See module docstring's 'MECHANISM REUSE' section for why this is necessary and why it
    still counts as running evaluate()'s genuine code path."""
    original = tl.nearest_directional_level

    def patched(levels, spot, side, max_distance_pct=max_distance_pct):  # noqa: ANN001
        return original(levels, spot, side, max_distance_pct=max_distance_pct)

    tl.nearest_directional_level = patched
    try:
        yield
    finally:
        tl.nearest_directional_level = original


# =========================================================================================
# 4. SIGNAL WALK -- produces trigger events for ONE (level_set, max_distance_pct,
#    min_stack_bars) config. Flat-only scanning: after any trigger, skips MAX_HOLD_BARS+1
#    bars so no two triggers can ever produce overlapping trades under ANY exit variant
#    (documented conservative simplification -- likely UNDERCOUNTS trade frequency for
#    fast-exiting variants, which biases toward the null, never toward manufacturing edge).
# =========================================================================================
@dataclass(frozen=True)
class Trigger:
    idx: int
    ts_utc: str
    entry_date_utc: str
    side: str
    entry_price: float
    setup: str
    ribbon_stack: str
    stack_bars: int


def run_signal_walk(bars: list[Bar], *, level_variant: str, max_distance_pct: float,
                    min_stack_bars: int) -> list[Trigger]:
    triggers: list[Trigger] = []
    n = len(bars)
    i = START_IDX
    with patched_max_distance(max_distance_pct):
        while i < n:
            bar = bars[i]
            now_utc = bar.close_time
            level_window = bars[max(0, i - LEVEL_WINDOW + 1):i + 1]
            ribbon_window = bars[max(0, i - RIBBON_WINDOW + 1):i + 1]
            levelset = build_levelset_variant(level_window, now_utc, level_variant, bar.close)
            verdict = sig.evaluate(ribbon_window, levelset, min_stack_bars=min_stack_bars)
            if verdict.verdict in ("ENTER_BULL", "ENTER_BEAR"):
                triggers.append(Trigger(
                    idx=i, ts_utc=now_utc.isoformat(), entry_date_utc=bar.open_time.strftime("%Y-%m-%d"),
                    side=verdict.side, entry_price=bar.close, setup=verdict.setup or "",
                    ribbon_stack=verdict.ribbon_stack, stack_bars=verdict.stack_bars))
                i += MAX_HOLD_BARS + 1
            else:
                i += 1
    return triggers


# =========================================================================================
# 5. TRADE SIMULATION (the new code -- exit_manager.py is option-premium-native and cannot
#    run against a spot BTC price; see module docstring). Two families: lens (M-scaled,
#    partial TP1 + chandelier runner) and fixed_control (single-lot bracket, no lens).
# =========================================================================================
@dataclass(frozen=True)
class TradeResult:
    entry_idx: int
    entry_date_utc: str
    side: str
    exit_reason: str
    bars_held: int
    tp1_filled: bool
    gross_return_pct: float   # lens-% for lens variants, spot-% for fixed_control
    net_return_pct: float     # gross - friction (friction scaled by M for lens variants)


def _raw_spot(entry_price: float, price: float, side: str) -> float:
    r = (price - entry_price) / entry_price
    return r if side == "bull" else -r


def simulate_lens_trade(bars: list[Bar], trigger: Trigger, M: int) -> TradeResult:
    entry_idx, entry_price, side = trigger.idx, trigger.entry_price, trigger.side
    n = len(bars)
    end_idx = min(entry_idx + MAX_HOLD_BARS, n - 1)
    tp1_filled = False
    hwm_lens: Optional[float] = None
    gross = None
    reason = "max_hold"
    exit_j = end_idx

    for j in range(entry_idx + 1, end_idx + 1):
        bar = bars[j]
        worst_spot = _raw_spot(entry_price, bar.low if side == "bull" else bar.high, side)
        best_spot = _raw_spot(entry_price, bar.high if side == "bull" else bar.low, side)
        worst_lens, best_lens = worst_spot * M, best_spot * M

        if not tp1_filled:
            if worst_lens <= CATASTROPHE_LENS:
                gross, reason, exit_j = CATASTROPHE_LENS, "catastrophe_cap", j
                break
            if best_lens >= TP1_TARGET_LENS:
                tp1_filled = True
                hwm_lens = TP1_TARGET_LENS
                # runner phase begins evaluating from the NEXT bar (simplification: TP1's
                # own trigger bar doesn't also get scored for runner exit -- avoids a
                # same-bar double-dip on the same OHLC range).
                continue
        else:
            hwm_lens = max(hwm_lens, best_lens)
            if best_lens >= RUNNER_TARGET_LENS:
                gross = TP1_QTY_FRACTION * TP1_TARGET_LENS + (1 - TP1_QTY_FRACTION) * RUNNER_TARGET_LENS
                reason, exit_j = "runner_target", j
                break
            if hwm_lens >= PROFIT_LOCK_ARM_LENS:
                trail_stop = hwm_lens - PROFIT_LOCK_TRAIL_LENS
                effective_stop = max(trail_stop, 0.0) if RUNNER_BE_FLOOR_AFTER_TP1 else trail_stop
                if worst_lens <= effective_stop:
                    gross = TP1_QTY_FRACTION * TP1_TARGET_LENS + (1 - TP1_QTY_FRACTION) * effective_stop
                    reason, exit_j = "profit_lock_trail", j
                    break
            elif RUNNER_BE_FLOOR_AFTER_TP1 and worst_lens <= 0.0:
                gross = TP1_QTY_FRACTION * TP1_TARGET_LENS + (1 - TP1_QTY_FRACTION) * 0.0
                reason, exit_j = "runner_be_stop", j
                break

    if gross is None:
        # max_hold: exit whatever's open (all of it, if TP1 never filled) at final close
        close_lens = _raw_spot(entry_price, bars[end_idx].close, side) * M
        if tp1_filled:
            gross = TP1_QTY_FRACTION * TP1_TARGET_LENS + (1 - TP1_QTY_FRACTION) * close_lens
        else:
            gross = close_lens
        reason, exit_j = "max_hold", end_idx

    net = gross - FRICTION_ROUND_TRIP * M
    return TradeResult(entry_idx=entry_idx, entry_date_utc=trigger.entry_date_utc, side=side,
                       exit_reason=reason, bars_held=exit_j - entry_idx, tp1_filled=tp1_filled,
                       gross_return_pct=round(gross * 100, 6), net_return_pct=round(net * 100, 6))


def simulate_fixed_control_trade(bars: list[Bar], trigger: Trigger) -> TradeResult:
    entry_idx, entry_price, side = trigger.idx, trigger.entry_price, trigger.side
    n = len(bars)
    end_idx = min(entry_idx + MAX_HOLD_BARS, n - 1)
    gross, reason, exit_j = None, "max_hold", end_idx
    for j in range(entry_idx + 1, end_idx + 1):
        bar = bars[j]
        worst_spot = _raw_spot(entry_price, bar.low if side == "bull" else bar.high, side)
        best_spot = _raw_spot(entry_price, bar.high if side == "bull" else bar.low, side)
        if worst_spot <= FIXED_CONTROL_STOP_PCT:
            gross, reason, exit_j = FIXED_CONTROL_STOP_PCT, "control_stop", j
            break
        if best_spot >= FIXED_CONTROL_TP_PCT:
            gross, reason, exit_j = FIXED_CONTROL_TP_PCT, "control_tp", j
            break
    if gross is None:
        gross = _raw_spot(entry_price, bars[end_idx].close, side)
        reason, exit_j = "max_hold", end_idx
    net = gross - FRICTION_ROUND_TRIP
    return TradeResult(entry_idx=entry_idx, entry_date_utc=trigger.entry_date_utc, side=side,
                       exit_reason=reason, bars_held=exit_j - entry_idx, tp1_filled=False,
                       gross_return_pct=round(gross * 100, 6), net_return_pct=round(net * 100, 6))


# =========================================================================================
# 6. STATS -- tuning/held-out split, per-cell aggregates, BH-FDR
# =========================================================================================
def split_dates(bars: list[Bar]) -> tuple[set, set]:
    dates = sorted({b.open_time.strftime("%Y-%m-%d") for b in bars})
    cut = int(round(0.70 * len(dates)))
    return set(dates[:cut]), set(dates[cut:])


def _stats_block(trades: list[TradeResult]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "win_rate": None, "total_return_pct": None,
               "avg_per_trade_pct": None, "max_drawdown_pct": None}
    rets = [t.net_return_pct for t in trades]
    wins = sum(1 for r in rets if r > 0)
    cum, peak, max_dd = 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda t: t.entry_idx):
        cum += t.net_return_pct
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return {"n_trades": n, "win_rate": round(wins / n, 4),
           "total_return_pct": round(sum(rets), 4), "avg_per_trade_pct": round(sum(rets) / n, 4),
           "max_drawdown_pct": round(max_dd, 4)}


def one_sided_p_mean_gt_0(xs: list[float]) -> Optional[float]:
    """Same convention as backtest/tools/directional_gate_battery.py#one_sided_p_mean_gt_0
    (reimplemented here, not imported -- that module owns its own prereg-hash-locked battery
    format and this tool is intentionally standalone). Normal-approximation one-sample
    t-test, H0: mean <= 0."""
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def bh_fdr(tests: list[dict], alpha: float = BH_ALPHA) -> list[dict]:
    """Benjamini-Hochberg step-up across the WHOLE grid at once (per the task -- not
    per-family). Same algorithm/convention as directional_gate_battery.py#bh_fdr."""
    testable = [t for t in tests if t["p"] is not None]
    testable.sort(key=lambda d: d["p"])
    m = len(testable)
    sig_cut = 0
    for i, d in enumerate(testable, 1):
        thresh = alpha * i / m if m else 0.0
        if d["p"] <= thresh:
            sig_cut = i
    for i, d in enumerate(testable, 1):
        d["bh_threshold"] = round(alpha * i / m, 6) if m else 0.0
        d["bh_significant"] = i <= sig_cut
    for t in tests:
        if t["p"] is None:
            t["bh_threshold"] = None
            t["bh_significant"] = False
    return tests


# =========================================================================================
# 7. GRID RUNNER
# =========================================================================================
def build_grid() -> list[dict]:
    cells = []
    for lv in LEVEL_SET_VARIANTS:
        for md in MAX_DISTANCE_PCTS:
            for ms in MIN_STACK_BARS_VALUES:
                for exit_kind in (*[f"lens_M{m}" for m in LEVERAGE_MS], "fixed_control"):
                    cells.append({"level_set": lv, "max_distance_pct": md, "min_stack_bars": ms,
                                 "exit_variant": exit_kind})
    return cells


def run_grid(bars: list[Bar]) -> dict:
    tuning_dates, holdout_dates = split_dates(bars)
    signal_configs = [(lv, md, ms) for lv in LEVEL_SET_VARIANTS for md in MAX_DISTANCE_PCTS
                      for ms in MIN_STACK_BARS_VALUES]

    trigger_cache: dict[tuple, list[Trigger]] = {}
    for lv, md, ms in signal_configs:
        trigger_cache[(lv, md, ms)] = run_signal_walk(
            bars, level_variant=lv, max_distance_pct=md, min_stack_bars=ms)

    cell_results = []
    p_tests = []
    for lv, md, ms in signal_configs:
        triggers = trigger_cache[(lv, md, ms)]
        n_bull = sum(1 for t in triggers if t.side == "bull")
        n_bear = sum(1 for t in triggers if t.side == "bear")
        for exit_kind in (*[f"lens_M{m}" for m in LEVERAGE_MS], "fixed_control"):
            trades: list[TradeResult] = []
            for trig in triggers:
                if exit_kind == "fixed_control":
                    trades.append(simulate_fixed_control_trade(bars, trig))
                else:
                    M = int(exit_kind.split("M")[1])
                    trades.append(simulate_lens_trade(bars, trig, M))

            tuning_trades = [t for t in trades if t.entry_date_utc in tuning_dates]
            holdout_trades = [t for t in trades if t.entry_date_utc in holdout_dates]
            bull_trades = [t for t in trades if t.side == "bull"]

            tuning_stats = _stats_block(tuning_trades)
            holdout_stats = _stats_block(holdout_trades)
            bull_only_stats = _stats_block(bull_trades)

            p_val = one_sided_p_mean_gt_0([t.net_return_pct for t in tuning_trades])
            n_total = len(trades)

            positive_tuning = (tuning_stats["avg_per_trade_pct"] or 0) > 0 and tuning_stats["n_trades"] > 0
            positive_holdout = (holdout_stats["avg_per_trade_pct"] or 0) > 0 and holdout_stats["n_trades"] > 0

            cell = {
                "level_set": lv, "max_distance_pct": md, "min_stack_bars": ms,
                "exit_variant": exit_kind, "n_triggers_total": len(triggers),
                "n_bull_triggers": n_bull, "n_bear_triggers": n_bear,
                "n_trades_total": n_total,
                "tuning": tuning_stats, "holdout": holdout_stats, "bull_only": bull_only_stats,
                "p_value_tuning": round(p_val, 6) if p_val is not None else None,
                "positive_on_tuning": bool(positive_tuning), "positive_on_holdout": bool(positive_holdout),
                "meets_n_gate": n_total >= MIN_TRADES_GATE,
            }
            cell_results.append(cell)
            p_tests.append({"cell_key": (lv, md, ms, exit_kind), "p": p_val})

    p_by_key = {t["cell_key"]: t for t in bh_fdr(p_tests)}
    for cell in cell_results:
        key = (cell["level_set"], cell["max_distance_pct"], cell["min_stack_bars"], cell["exit_variant"])
        bh = p_by_key[key]
        cell["bh_threshold"] = bh["bh_threshold"]
        cell["bh_significant"] = bh["bh_significant"]
        cell["passes_all_gates"] = bool(
            cell["positive_on_tuning"] and cell["positive_on_holdout"]
            and cell["meets_n_gate"] and cell["bh_significant"])

    return {"cells": cell_results, "tuning_dates": sorted(tuning_dates),
           "holdout_dates": sorted(holdout_dates)}


# =========================================================================================
# 8. REPORT
# =========================================================================================
def breakeven_summary() -> dict:
    return {
        "spot_breakeven_move_pct_per_trade": round(FRICTION_ROUND_TRIP * 100, 4),
        "note": "Friction is charged in SPOT space before the leverage lens multiply, so "
               "the breakeven hurdle in the underlying BTC move is 0.09% round-trip "
               "REGARDLESS of M -- M only rescales wins/losses/friction together in "
               "lens-% space, it never creates edge that wasn't in the spot move itself.",
        "lens_return_hurdle_by_M": {str(m): round(FRICTION_ROUND_TRIP * m * 100, 4)
                                    for m in LEVERAGE_MS},
    }


def render_markdown(grid: dict, provenance: dict, ranked: list[dict]) -> str:
    passing = [c for c in grid["cells"] if c["passes_all_gates"]]
    lines = []
    lines.append("# Crypto Twin Signal Backtest -- 2026-07-26")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if passing:
        lines.append(f"**{len(passing)} of 72 cells PASS all four honesty gates** "
                     "(positive tuning + positive held-out + n>=30 + BH-FDR q<=0.10).")
    else:
        lines.append("**NULL RESULT: 0 of 72 cells pass all four honesty gates.** "
                     "No config here shows measured, statistically-survivable positive "
                     "expectancy on real BTC history under this exit model + friction. "
                     "This is the expected, useful answer -- reported plainly, not softened.")
    lines.append("")
    lines.append("Section below ranks all cells by held-out avg-per-trade return (net of "
                "friction) regardless of pass/fail, so the least-bad config is identifiable "
                "even though nothing measured an edge.")
    lines.append("")
    lines.append("## Top-5 cells (ranked by held-out avg-per-trade % net of friction)")
    lines.append("")
    lines.append("| Rank | level_set | max_dist% | min_stack | exit | n(tune/hold) | "
                 "tune avg%/trade | hold avg%/trade | hold WR | hold max_dd% | BH sig | PASS |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(ranked[:5], 1):
        t, h = c["tuning"], c["holdout"]
        lines.append(
            f"| {i} | {c['level_set']} | {c['max_distance_pct']} | {c['min_stack_bars']} | "
            f"{c['exit_variant']} | {t['n_trades']}/{h['n_trades']} | "
            f"{t['avg_per_trade_pct']} | {h['avg_per_trade_pct']} | {h['win_rate']} | "
            f"{h['max_drawdown_pct']} | {c['bh_significant']} | {c['passes_all_gates']} |")
    lines.append("")

    top = ranked[0]
    lines.append("## Recommended config for tonight")
    lines.append("")
    label = "PASSED all honesty gates" if top["passes_all_gates"] else "NO MEASURED EDGE (least-bad only)"
    lines.append(f"**Label: {label}**")
    lines.append("")
    lines.append(f"- level_set = `{top['level_set']}`, max_distance_pct = `{top['max_distance_pct']}`, "
                "min_stack_bars = `" + str(top['min_stack_bars']) + "`, exit_variant = `" +
                top['exit_variant'] + "`")
    lines.append(f"- Held-out: n={top['holdout']['n_trades']}, "
                f"avg/trade={top['holdout']['avg_per_trade_pct']}%, "
                f"WR={top['holdout']['win_rate']}, "
                f"total_return={top['holdout']['total_return_pct']}%, "
                f"max_dd={top['holdout']['max_drawdown_pct']}%")
    lines.append(f"- Tuning: n={top['tuning']['n_trades']}, "
                f"avg/trade={top['tuning']['avg_per_trade_pct']}%, "
                f"WR={top['tuning']['win_rate']}")
    lines.append(f"- BH-FDR: p={top['p_value_tuning']}, threshold={top['bh_threshold']}, "
                f"significant={top['bh_significant']}")
    lines.append(f"- Bull-only (the ONLY side deployable tonight -- Alpaca crypto is "
                f"cash/long-only, ENTER_BEAR is logged-but-skipped in production per "
                f"crypto_twin_core.py): n={top['bull_only']['n_trades']}, "
                f"avg/trade={top['bull_only']['avg_per_trade_pct']}%, "
                f"WR={top['bull_only']['win_rate']}")
    lines.append("")
    be = breakeven_summary()
    lines.append("## Friction-adjusted breakeven")
    lines.append("")
    lines.append(f"- Spot breakeven move needed per trade (round-trip friction, independent of M): "
                f"**{be['spot_breakeven_move_pct_per_trade']}%**")
    lines.append(f"- Lens-return hurdle by M: " +
                ", ".join(f"M={m}: {be['lens_return_hurdle_by_M'][str(m)]}%" for m in LEVERAGE_MS))
    lines.append(f"- {be['note']}")
    lines.append("")

    lines.append("## Data provenance")
    lines.append("")
    for k, v in provenance.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## Methodology / pre-registration (frozen before any cell was scored)")
    lines.append("")
    lines.append(f"- Grid: level_set in {LEVEL_SET_VARIANTS}, max_distance_pct in "
                f"{MAX_DISTANCE_PCTS}, min_stack_bars in {MIN_STACK_BARS_VALUES}, "
                f"exit_variant in lens_M{LEVERAGE_MS} + fixed_control = "
                f"{len(LEVEL_SET_VARIANTS)*len(MAX_DISTANCE_PCTS)*len(MIN_STACK_BARS_VALUES)*(len(LEVERAGE_MS)+1)} cells.")
    lines.append(f"- Split: 70%/30% tuning/held-out by calendar UTC date (held-out = most "
                f"recent {len(grid['holdout_dates'])} days: {grid['holdout_dates'][0]} to "
                f"{grid['holdout_dates'][-1]}), touched once.")
    lines.append(f"- Pass gate: positive mean tuning return AND positive mean held-out return "
                f"AND n_trades>={MIN_TRADES_GATE} AND BH-FDR significant at q<={BH_ALPHA} "
                "across all 72 p-values at once.")
    lines.append("- Exit shape sourced from automation/state/params.json (read-only): "
                f"catastrophe={CATASTROPHE_LENS}, tp1_target={TP1_TARGET_LENS}, "
                f"tp1_qty_fraction={TP1_QTY_FRACTION} (task-specified), "
                f"runner_target={RUNNER_TARGET_LENS}, profit_lock_arm={PROFIT_LOCK_ARM_LENS}, "
                f"profit_lock_trail={PROFIT_LOCK_TRAIL_LENS}, "
                f"runner_be_floor_after_tp1={RUNNER_BE_FLOOR_AFTER_TP1}.")
    lines.append(f"- Fixed control: TP={FIXED_CONTROL_TP_PCT*100}% / stop={FIXED_CONTROL_STOP_PCT*100}% "
                "of spot, single-lot, no lens.")
    lines.append(f"- Friction: {FRICTION_ROUND_TRIP*100}% round-trip, charged in spot space "
                "before the M multiply.")
    lines.append(f"- max_hold_bars = {MAX_HOLD_BARS} (4h @ 5m, fixed, not swept).")
    lines.append("- DEPLOYABILITY: Alpaca crypto is cash/long-only. ENTER_BEAR triggers are "
                "scored in this grid for completeness but are NOT executable on the twin's "
                "account without margin/short capability -- see crypto_twin_core.py's "
                "own docstring (\"BUY-only... ENTER_BEAR is logged-but-skipped\").")
    lines.append("- max_distance_pct is not a parameter crypto_twin_signal.evaluate() exposes "
                "directly -- it's the default baked into crypto_twin_levels."
                "nearest_directional_level(). This tool temporarily monkeypatches that "
                "function's default in-process (restored immediately after) to make the "
                "grid axis testable while still running evaluate()'s real code verbatim. "
                "See patched_max_distance() in this script.")
    lines.append("")

    lines.append("## Full 72-cell grid")
    lines.append("")
    lines.append("| level_set | max_dist% | min_stack | exit | n_tune | tune avg% | n_hold | "
                 "hold avg% | hold WR | p(tune) | BH sig | PASS |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(grid["cells"], key=lambda c: (c["level_set"], c["max_distance_pct"],
                                                  c["min_stack_bars"], c["exit_variant"])):
        t, h = c["tuning"], c["holdout"]
        lines.append(f"| {c['level_set']} | {c['max_distance_pct']} | {c['min_stack_bars']} | "
                     f"{c['exit_variant']} | {t['n_trades']} | {t['avg_per_trade_pct']} | "
                     f"{h['n_trades']} | {h['avg_per_trade_pct']} | {h['win_rate']} | "
                     f"{c['p_value_tuning']} | {c['bh_significant']} | {c['passes_all_gates']} |")
    lines.append("")
    return "\n".join(lines)


# =========================================================================================
# MAIN
# =========================================================================================
def main() -> int:
    print("[crypto-twin-backtest] fetching/loading BTC/USD 5m bars...", flush=True)
    bars, provenance = fetch_or_load_bars()
    print(f"[crypto-twin-backtest] {len(bars)} bars, {provenance.get('date_range')}", flush=True)

    print("[crypto-twin-backtest] running pre-registered 72-cell grid...", flush=True)
    grid = run_grid(bars)

    ranked = sorted(grid["cells"],
                    key=lambda c: (c["holdout"]["avg_per_trade_pct"] is None,
                                   -(c["holdout"]["avg_per_trade_pct"] or -999),
                                   -(c["holdout"]["n_trades"] or 0)))

    n_pass = sum(1 for c in grid["cells"] if c["passes_all_gates"])
    print(f"[crypto-twin-backtest] {n_pass}/72 cells pass all gates", flush=True)

    md = render_markdown(grid, provenance, ranked)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text(md, encoding="utf-8")

    json_payload = {
        "generated_by": "backtest/tools/crypto_twin_signal_backtest.py",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
        "pre_registration": {
            "level_set_variants": LEVEL_SET_VARIANTS, "max_distance_pcts": MAX_DISTANCE_PCTS,
            "min_stack_bars_values": MIN_STACK_BARS_VALUES, "leverage_ms": LEVERAGE_MS,
            "bh_alpha": BH_ALPHA, "min_trades_gate": MIN_TRADES_GATE,
            "max_hold_bars": MAX_HOLD_BARS,
        },
        "exit_shape_constants": {
            "catastrophe_lens": CATASTROPHE_LENS, "tp1_target_lens": TP1_TARGET_LENS,
            "tp1_qty_fraction": TP1_QTY_FRACTION, "runner_target_lens": RUNNER_TARGET_LENS,
            "profit_lock_arm_lens": PROFIT_LOCK_ARM_LENS,
            "profit_lock_trail_lens": PROFIT_LOCK_TRAIL_LENS,
            "runner_be_floor_after_tp1": RUNNER_BE_FLOOR_AFTER_TP1,
            "friction_round_trip": FRICTION_ROUND_TRIP,
            "fixed_control_tp_pct": FIXED_CONTROL_TP_PCT, "fixed_control_stop_pct": FIXED_CONTROL_STOP_PCT,
        },
        "tuning_dates": grid["tuning_dates"], "holdout_dates": grid["holdout_dates"],
        "n_cells_passing": n_pass, "cells": grid["cells"],
        "ranked_top5": ranked[:5],
        "breakeven_summary": breakeven_summary(),
    }
    JSON_OUT.write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")

    print(f"[crypto-twin-backtest] wrote {MD_OUT}", flush=True)
    print(f"[crypto-twin-backtest] wrote {JSON_OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
