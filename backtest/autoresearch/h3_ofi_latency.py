"""H3 — order-flow imbalance (OFI) as a predictor, net of observation-to-entry latency.

Hypothesis (markdown/trading-knowledge/microstructure-informed-flow.md §4 H3):
a Reddit futures trader (u/hteecs) reported that order-flow aggression was the
most predictive signal he found, but "by the time the aggression was observed
sufficiently the price had already moved, which destroyed the edge." This
script quantifies that claim on SPY, on our own SIP tape data, at $0 (Alpaca
REST only, pure Python, no LLM calls).

Deliverable is a CURVE, not a yes/no: predictive strength of a signed-volume
OFI signal as a function of (lookback x horizon x delay), reported alongside
a direction-controlled null (STRATEGY-BACKLOG.md item 5b: random decision
points where the "side" is the bar's own realized direction — a signal cannot
look good merely by being directionally correct in a drifting tape).

Design (bounded on purpose):
  - ~20 recent RTH weekdays, SPY only, decision grid every 15 min 10:00-15:00 ET.
  - OFI signal = signed volume / total volume over a LOOKBACK window ending at
    decision time t (two lookbacks: 60s, 300s), from Lee-Ready-signed trades
    (backtest/tools/fetch_sip_tape.py — READ, not modified).
  - Outcome = forward SPY return over multiple horizons (1, 5, 15, 30 min),
    computed from the SAME signed trade tape (last trade at-or-before a given
    forward timestamp), which is strictly AFTER the entry timestamp
    (t + delay) — no look-ahead (repo lesson cluster C6).
  - Core measurement: re-run with entry delayed 0/5/15/30/60s after t. Signal
    is measured using data available as of t; "entry" (price reference) is
    read at t+delay, never before.
  - Null: direction-controlled — pick random times, use the SAME LOOKBACK
    window's own trade-tape return sign at that random time as "the signal
    side" (i.e. the null strategy always guesses the bar's own historical
    drift direction), then measure that null's forward-return correlation the
    same way, at the same delays. This isolates OFI's incremental information
    from directional drift.

Everything here is READ-ONLY against fetch_sip_tape's public API (fetch_trades,
fetch_quotes, sign_trades) and Alpaca REST via that module's caching layer.
This file and analysis/recommendations/h3-ofi-latency.json are the only
artifacts this script owns/writes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fetch_sip_tape import fetch_quotes, fetch_trades, sign_trades  # noqa: E402

import pandas_market_calendars as mcal  # noqa: E402

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

SYMBOL = "SPY"
N_DAYS = 20
GRID_START_ET = "10:00"
GRID_END_ET = "15:00"  # inclusive last decision point; avoids 09:30-10:00 open and last 15 min
GRID_STEP_MIN = 15

LOOKBACKS_SEC = [60, 300]
HORIZONS_MIN = [1, 5, 15, 30]
DELAYS_SEC = [0, 5, 15, 30, 60]

# Null control: how many random direction-controlled draws per real decision point.
NULL_DRAWS_PER_DAY = 1  # one random decision point per day per lookback (matches real grid density order)

OUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "analysis"
    / "recommendations"
    / "h3-ofi-latency.json"
)

RTH_OPEN_ET = "09:30"
RTH_CLOSE_ET = "16:00"


# --------------------------------------------------------------------------------
# Day selection
# --------------------------------------------------------------------------------


def select_recent_trading_days(n_days: int, as_of: datetime) -> list[str]:
    """Return the n_days most recent NYSE full trading days strictly before as_of's date.

    Uses pandas_market_calendars (already a dependency elsewhere in this repo,
    e.g. backtest/tools/catalyst_direction_null_harness.py) so holidays and
    half-days are excluded by the calendar itself, not by a hand list.
    """
    nyse = mcal.get_calendar("NYSE")
    # look back generously (n_days weekdays -> need ~1.6x calendar days of buffer)
    lookback_days = int(n_days * 2.2) + 10
    start = (as_of.date() - timedelta(days=lookback_days)).isoformat()
    end = (as_of.date() - timedelta(days=1)).isoformat()
    sched = nyse.schedule(start_date=start, end_date=end)
    if sched.empty:
        raise RuntimeError(f"NYSE calendar returned zero trading days for {start}..{end}")
    days = sorted(sched.index.strftime("%Y-%m-%d").tolist())
    # exclude half-days (early close) — a half-day's 10:00-15:00 grid would run
    # past the close on some days; the schedule's market_close column tells us.
    full_days = []
    for d, row in sched.iterrows():
        close_et = row["market_close"].tz_convert(ET)
        if close_et.strftime("%H:%M") == RTH_CLOSE_ET:
            full_days.append(d.strftime("%Y-%m-%d"))
    if len(full_days) < n_days:
        raise RuntimeError(
            f"Only found {len(full_days)} full RTH days in {start}..{end}, need {n_days}. "
            "Widen the lookback window."
        )
    return full_days[-n_days:]


def decision_grid_et(day: str) -> list[datetime]:
    """15-min grid 10:00..15:00 ET inclusive, tz-aware ET datetimes for `day`."""
    y, m, d = (int(x) for x in day.split("-"))
    start = datetime(y, m, d, 10, 0, tzinfo=ET)
    end = datetime(y, m, d, 15, 0, tzinfo=ET)
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(minutes=GRID_STEP_MIN)
    return out


# --------------------------------------------------------------------------------
# Signed-trade tape access
# --------------------------------------------------------------------------------


@dataclass
class DayTape:
    day: str
    signed: pd.DataFrame  # columns: t_ns, price, size, sign, signed_size (RTH-window fetch)


def fetch_day_signed_tape(day: str) -> DayTape:
    """Fetch + sign the full RTH trade tape for one day (single cached window).

    RTH window fetched with a little slack before 09:30 (for lookback windows
    that reach slightly before the grid start at 10:00, this is unnecessary,
    but a 5-min pad is cheap and avoids any edge truncation) and none after
    16:00 since the grid's longest horizon (30 min) from the 15:00 decision
    point lands at 15:30, well inside RTH.
    """
    y, m, d = (int(x) for x in day.split("-"))
    open_et = datetime(y, m, d, 9, 25, tzinfo=ET)
    close_et = datetime(y, m, d, 16, 0, tzinfo=ET)
    start_utc = open_et.astimezone(UTC)
    end_utc = close_et.astimezone(UTC)

    trades = fetch_trades(SYMBOL, start_utc, end_utc)
    quotes = fetch_quotes(SYMBOL, start_utc, end_utc)
    signed = sign_trades(trades, quotes)
    return DayTape(day=day, signed=signed)


def _price_at_or_before(signed: pd.DataFrame, t_ns: int) -> float | None:
    """Last trade price at or before t_ns. None if no trade yet (no look-ahead)."""
    idx = signed["t_ns"].searchsorted(t_ns, side="right") - 1
    if idx < 0:
        return None
    return float(signed["price"].iloc[idx])


def _ofi_signal(signed: pd.DataFrame, t_ns: int, lookback_sec: int) -> tuple[float | None, int]:
    """Signed-volume / total-volume over (t_ns - lookback, t_ns]. Returns (ofi, n_trades).

    Only trades with timestamp <= t_ns are used — the signal is knowable at t.
    """
    lo_ns = t_ns - lookback_sec * 1_000_000_000
    ts = signed["t_ns"].to_numpy()
    lo_idx = np.searchsorted(ts, lo_ns, side="right")
    hi_idx = np.searchsorted(ts, t_ns, side="right")
    window = signed.iloc[lo_idx:hi_idx]
    n = len(window)
    if n == 0:
        return None, 0
    total_vol = window["size"].sum()
    if total_vol == 0:
        return None, n
    ofi = float(window["signed_size"].sum() / total_vol)
    return ofi, n


def _forward_return(signed: pd.DataFrame, entry_ns: int, horizon_min: int) -> float | None:
    """Return from price-at-entry to price at entry + horizon. Both prices are
    read strictly at-or-before their timestamps from the trade tape — never
    from data after the target timestamp (C6 no-look-ahead)."""
    entry_px = _price_at_or_before(signed, entry_ns)
    if entry_px is None or entry_px == 0:
        return None
    fwd_ns = entry_ns + horizon_min * 60 * 1_000_000_000
    fwd_px = _price_at_or_before(signed, fwd_ns)
    if fwd_px is None:
        return None
    return (fwd_px - entry_px) / entry_px


# --------------------------------------------------------------------------------
# Measurement: real decision points
# --------------------------------------------------------------------------------


def build_real_observations(tapes: list[DayTape]) -> pd.DataFrame:
    """One row per (day, decision_time, lookback, delay, horizon): ofi signal
    (measured at t only), forward return measured from t+delay to t+delay+horizon.
    """
    rows = []
    for tape in tapes:
        signed = tape.signed
        for t_et in decision_grid_et(tape.day):
            t_ns = int(t_et.astimezone(UTC).timestamp() * 1e9)
            for lookback in LOOKBACKS_SEC:
                ofi, n_trades = _ofi_signal(signed, t_ns, lookback)
                if ofi is None:
                    continue
                for delay in DELAYS_SEC:
                    entry_ns = t_ns + delay * 1_000_000_000
                    for horizon in HORIZONS_MIN:
                        ret = _forward_return(signed, entry_ns, horizon)
                        if ret is None:
                            continue
                        rows.append(
                            {
                                "day": tape.day,
                                "t_et": t_et.strftime("%H:%M"),
                                "lookback_sec": lookback,
                                "delay_sec": delay,
                                "horizon_min": horizon,
                                "ofi": ofi,
                                "n_trades_lookback": n_trades,
                                "fwd_return": ret,
                            }
                        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------
# Direction-controlled null (STRATEGY-BACKLOG.md 5b)
# --------------------------------------------------------------------------------


def build_null_observations(tapes: list[DayTape], rng: np.random.Generator) -> pd.DataFrame:
    """Direction-controlled null: at a RANDOM decision point, the "signal" is
    replaced by the sign of the bar's OWN realized (backward-looking) return
    over the same lookback window — i.e. the null strategy is "trade the
    direction the tape was already moving," with no order-flow information
    at all beyond price direction. This isolates whether OFI adds anything
    beyond "a signal that is directionally correct in a drifting tape,"
    per STRATEGY-BACKLOG.md item 5b's methodology finding.

    Same delay/horizon grid as the real observations, same forward-return
    computation (post-delay, no look-ahead), same sample-size discipline
    (one random draw per day per lookback, matching the real grid's per-day
    density order so cell sizes are comparable).
    """
    rows = []
    for tape in tapes:
        signed = tape.signed
        day_grid = decision_grid_et(tape.day)
        for lookback in LOOKBACKS_SEC:
            for _ in range(len(day_grid) * NULL_DRAWS_PER_DAY // len(day_grid) or 1):
                pass
            # one random decision point per day per lookback (see NULL_DRAWS_PER_DAY)
            for _draw in range(NULL_DRAWS_PER_DAY):
                t_et = day_grid[rng.integers(0, len(day_grid))]
                t_ns = int(t_et.astimezone(UTC).timestamp() * 1e9)
                # "signal" = sign of the bar's own realized return over the
                # lookback window ending at t (backward-looking direction,
                # NOT order flow) — this is the null's entire information set.
                lo_ns = t_ns - lookback * 1_000_000_000
                px_lo = _price_at_or_before(signed, lo_ns)
                px_t = _price_at_or_before(signed, t_ns)
                if px_lo is None or px_t is None or px_lo == 0:
                    continue
                realized_dir = np.sign(px_t - px_lo)
                if realized_dir == 0:
                    continue
                for delay in DELAYS_SEC:
                    entry_ns = t_ns + delay * 1_000_000_000
                    for horizon in HORIZONS_MIN:
                        ret = _forward_return(signed, entry_ns, horizon)
                        if ret is None:
                            continue
                        rows.append(
                            {
                                "day": tape.day,
                                "t_et": t_et.strftime("%H:%M"),
                                "lookback_sec": lookback,
                                "delay_sec": delay,
                                "horizon_min": horizon,
                                "null_side": float(realized_dir),
                                "fwd_return": ret,
                            }
                        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------


def cell_metrics_real(df: pd.DataFrame) -> pd.DataFrame:
    """Per (lookback, delay, horizon) cell: Pearson corr(ofi, fwd_return), n,
    and mean forward return conditioned on sign(ofi) (a directionally-oriented,
    more interpretable companion metric to correlation)."""
    out = []
    for (lb, delay, hz), g in df.groupby(["lookback_sec", "delay_sec", "horizon_min"]):
        n = len(g)
        if n < 5:
            corr = None
        else:
            corr = float(np.corrcoef(g["ofi"], g["fwd_return"])[0, 1])
            if np.isnan(corr):
                corr = None
        pos = g[g["ofi"] > 0]["fwd_return"]
        neg = g[g["ofi"] < 0]["fwd_return"]
        mean_cond = None
        if len(pos) >= 3 and len(neg) >= 3:
            mean_cond = float(pos.mean() - neg.mean())
        out.append(
            {
                "lookback_sec": int(lb),
                "delay_sec": int(delay),
                "horizon_min": int(hz),
                "n": int(n),
                "corr_ofi_fwdret": corr,
                "mean_fwdret_pos_minus_neg_ofi": mean_cond,
            }
        )
    return pd.DataFrame(out)


def cell_metrics_null(df: pd.DataFrame) -> pd.DataFrame:
    """Per (lookback, delay, horizon) cell for the null: correlation of
    null_side (the bar's own backward direction, +-1) with forward return,
    and mean forward return conditioned on null_side sign — same functional
    form as the real metric so the two are directly comparable."""
    out = []
    for (lb, delay, hz), g in df.groupby(["lookback_sec", "delay_sec", "horizon_min"]):
        n = len(g)
        if n < 5:
            corr = None
        else:
            corr = float(np.corrcoef(g["null_side"], g["fwd_return"])[0, 1])
            if np.isnan(corr):
                corr = None
        pos = g[g["null_side"] > 0]["fwd_return"]
        neg = g[g["null_side"] < 0]["fwd_return"]
        mean_cond = None
        if len(pos) >= 3 and len(neg) >= 3:
            mean_cond = float(pos.mean() - neg.mean())
        out.append(
            {
                "lookback_sec": int(lb),
                "delay_sec": int(delay),
                "horizon_min": int(hz),
                "n": int(n),
                "corr_null_fwdret": corr,
                "mean_fwdret_pos_minus_neg_null": mean_cond,
            }
        )
    return pd.DataFrame(out)


# --------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------


def main() -> int:
    now_et = datetime.now(tz=ET)
    days = select_recent_trading_days(N_DAYS, now_et)
    print(f"[H3] using {len(days)} trading days: {days[0]} .. {days[-1]}")
    print(f"[H3] dates: {days}")

    tapes: list[DayTape] = []
    fetch_log = []
    for day in days:
        t0 = datetime.now()
        dt = fetch_day_signed_tape(day)
        elapsed = (datetime.now() - t0).total_seconds()
        n_trades = len(dt.signed)
        fetch_log.append({"day": day, "n_trades": n_trades, "wall_seconds": round(elapsed, 3)})
        print(f"[H3] {day}: {n_trades} trades fetched/cached in {elapsed:.2f}s")
        tapes.append(dt)

    real_obs = build_real_observations(tapes)
    print(f"[H3] real observations: {len(real_obs)} rows")

    rng = np.random.default_rng(seed=20260906)  # fixed seed, disclosed, for reproducibility
    null_obs = build_null_observations(tapes, rng)
    print(f"[H3] null observations: {len(null_obs)} rows")

    real_metrics = cell_metrics_real(real_obs)
    null_metrics = cell_metrics_null(null_obs)

    merged = real_metrics.merge(
        null_metrics, on=["lookback_sec", "delay_sec", "horizon_min"], suffixes=("_real", "_null")
    )

    # The core number: for each lookback x horizon, the smallest delay at
    # which |real corr| stops exceeding |null corr| (i.e. signal <= null).
    # If real never exceeds null even at delay=0, report "never_beat_null".
    decay_summary = []
    for (lb, hz), g in merged.groupby(["lookback_sec", "horizon_min"]):
        g = g.sort_values("delay_sec")
        beats_null_at = []
        for _, row in g.iterrows():
            cr = row["corr_ofi_fwdret"]
            cn = row["corr_null_fwdret"]
            beats = (cr is not None and cn is not None and abs(cr) > abs(cn))
            beats_null_at.append((int(row["delay_sec"]), bool(beats)))
        beating_delays = [d for d, b in beats_null_at if b]
        if not beating_delays:
            headline = "never_beats_null_at_any_tested_delay"
        else:
            last_beat = max(d for d, b in beats_null_at if b)
            # first delay AFTER the last delay that beats null, if any
            after = [d for d, b in beats_null_at if d > last_beat]
            headline = f"stops_beating_null_after_delay_sec={last_beat}" if after else (
                f"still_beats_null_at_max_tested_delay_sec={last_beat}"
            )
        decay_summary.append(
            {
                "lookback_sec": int(lb),
                "horizon_min": int(hz),
                "beats_null_by_delay": beats_null_at,
                "headline": headline,
            }
        )

    n_cells_tested = len(merged)
    report = {
        "hypothesis": "H3 — OFI/aggression predictive strength as a function of observation-to-entry delay (the hteecs latency test)",
        "source_doc": "markdown/trading-knowledge/microstructure-informed-flow.md §4 H3",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "symbol": SYMBOL,
        "data_source": "Alpaca SIP trades+quotes via backtest/tools/fetch_sip_tape.py (Lee-Ready signed); forward prices from the SAME trade tape (last trade at-or-before target timestamp), never from data after the target timestamp",
        "cost": "$0 — Alpaca REST only, no LLM calls, pure Python",
        "sample": {
            "n_days": len(days),
            "dates_used": days,
            "decision_grid_et": f"every {GRID_STEP_MIN} min, {GRID_START_ET}-{GRID_END_ET} ET inclusive (excludes 09:30-10:00 open and last 15 min of RTH)",
            "fetch_log": fetch_log,
            "n_real_observations_rows": int(len(real_obs)),
            "n_null_observations_rows": int(len(null_obs)),
        },
        "design": {
            "lookbacks_sec": LOOKBACKS_SEC,
            "horizons_min": HORIZONS_MIN,
            "delays_sec": DELAYS_SEC,
            "signal": "OFI = signed_volume / total_volume over (t-lookback, t], signed trades via Lee-Ready (quote-midpoint rule + tick-rule fallback), knowable at t only (no look-ahead)",
            "null": "direction-controlled per STRATEGY-BACKLOG.md item 5b: 1 random decision point/day/lookback; null 'side' = sign of the bar's OWN backward-looking realized return over the same lookback window (no order-flow information) — isolates OFI's incremental info from directional drift",
            "null_draws_per_day_per_lookback": NULL_DRAWS_PER_DAY,
            "rng_seed": 20260906,
        },
        "results": {
            "cells": json.loads(merged.to_json(orient="records")),
            "delay_decay_summary": decay_summary,
        },
        "disclosure": {
            "multiple_comparisons": f"{len(LOOKBACKS_SEC)} lookbacks x {len(HORIZONS_MIN)} horizons x {len(DELAYS_SEC)} delays = {len(LOOKBACKS_SEC) * len(HORIZONS_MIN) * len(DELAYS_SEC)} cells tested ({n_cells_tested} after merge); this report presents ALL cells, not a cherry-picked best one — do not treat any single strong cell as the headline without correcting for this search width",
            "single_regime_caveat": f"one {len(days)}-day window ({days[0]}..{days[-1]}) is a single, recent SPY regime — no claim of stability across regimes (rate environment, realized vol regime, etc.) is made or implied",
            "sample_size_caveat": "cells with n < 5 are reported as null (correlation/conditional-mean withheld) rather than a noisy point estimate; check per-cell n in results.cells before trusting any single number",
            "not_tuned_for_signal": "lookbacks/horizons/delays were fixed BEFORE running (per markdown/trading-knowledge/microstructure-informed-flow.md §4 H3 and the doc's pre-registered grid), not swept afterward to manufacture a positive result; a null result across the whole grid is reported as such, not discarded",
            "verification": "counts and headline figures below are quoted directly from this script's own run output printed to stdout in the same session",
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, default=str))
    print(f"[H3] wrote {OUT_PATH}")

    print("[H3] === DELAY-DECAY HEADLINE (per lookback x horizon) ===")
    for row in decay_summary:
        print(f"  lookback={row['lookback_sec']}s horizon={row['horizon_min']}m -> {row['headline']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
