"""Seed B -- E2 direction contexts (at-PD-level + VWAP-aligned) on MES daily bars.

Per FUTURES-REVIVAL-PLAN section 2c seed 2 / section 0 point 1 (the E2 replay,
`analysis/j-webull/E2-machine-management-replay.md`): J's best cell was
"at-level <=0.1% (PDH/PDL/PDC) & VWAP-aligned & morning 10:00-11:00" (79.3% WR,
n=29, BS-sim ranking-only). This seed re-expresses the two SELF-CONTAINED,
scale-free parts of that context directly on MES bars:

  at_level:     |close - nearest(PDH, PDL, PDC)| / level <= tol
  vwap_aligned: close vs that SESSION's own volume-weighted average price
                (typical price (H+L+C)/3, cumulative through the RTH session,
                evaluated at the close -- the same "VWAP side" read J trades
                against). Direction is DERIVED from this (long if close >
                VWAP, short if close < VWAP) -- E2's "bias x vwap_side"
                alignment collapses to this when bias is generated FROM vwap
                side rather than graded against an independent human pick
                (there is no independent direction call at daily-bar swing
                cadence; disclosed).

NOT PORTABLE -- disclosed and skipped, not faked:
  The "morning 10:00-11:00" time-of-day component has no meaning on a bar
  that spans the entire RTH session (a daily bar close). SKIPPED-NOT-PORTABLE.
  (The 4h-of-RTH resample exists and its FIRST bucket, [09:30,13:30), is the
  closest available proxy, but it still isn't the 10:00-11:00 window and would
  misrepresent the original cell -- this seed runs on DAILY bars only,
  disclosed as a scope choice, not a fabricated approximation.)

Grid: tol in {0.10%, 0.20%} (2 combos). Both directions reported (E2's own
direction read was two-sided; the task's battery discipline mandates it too).
"""
from __future__ import annotations

import pandas as pd

TOL_PCT = (0.001, 0.002)


def compute_session_vwap_by_date(rth_intraday: pd.DataFrame) -> pd.Series:
    """Typical-price VWAP per RTH session (cumulative, evaluated at session
    close). `rth_intraday`: RTH-filtered 1m/5m bars with timestamp_et/high/
    low/close/volume. Returns a Series indexed by `datetime.date`."""
    tp = (rth_intraday["high"] + rth_intraday["low"] + rth_intraday["close"]) / 3.0
    pv = tp * rth_intraday["volume"]
    date = rth_intraday["timestamp_et"].dt.tz_convert("America/New_York").dt.date
    df = pd.DataFrame({"_date": date, "_pv": pv, "_v": rth_intraday["volume"]})
    g = df.groupby("_date")
    vwap = g["_pv"].sum() / g["_v"].sum().replace(0, pd.NA)
    return vwap


def build_grid() -> list[dict]:
    return [{"tol_pct": t} for t in TOL_PCT]


def generate_signals(
    daily_bars: pd.DataFrame, session_vwap_by_date: pd.Series,
    grid: list[dict] | None = None,
) -> pd.DataFrame:
    """daily_bars: `data.resample_daily` schema (timestamp_et, date, OHLCV),
    RangeIndex. Signal fires on bar i using bar i's own close vs bar (i-1)'s
    PD levels (causal: PD levels are fully known before bar i even opens) and
    bar i's own end-of-session VWAP (causal: known at bar i's close, same
    moment the daily bar closes). Entry = bar i+1's open (next-bar convention).
    """
    if grid is None:
        grid = build_grid()
    rows = []
    dates = daily_bars["date"].tolist()
    highs, lows, closes = (daily_bars["high"].tolist(), daily_bars["low"].tolist(),
                            daily_bars["close"].tolist())
    for combo in grid:
        tol = combo["tol_pct"]
        combo_id = f"e2_tol{tol}"
        for i in range(1, len(daily_bars)):
            vwap = session_vwap_by_date.get(dates[i])
            if vwap is None or pd.isna(vwap):
                continue
            pdh, pdl, pdc = highs[i - 1], lows[i - 1], closes[i - 1]
            close = closes[i]
            levels = {"PDH": pdh, "PDL": pdl, "PDC": pdc}
            nearest_name = min(levels, key=lambda k: abs(close - levels[k]) / levels[k])
            nearest_dist_pct = abs(close - levels[nearest_name]) / levels[nearest_name]
            if nearest_dist_pct > tol:
                continue
            vwap = float(vwap)
            if close > vwap:
                direction = "long"
            elif close < vwap:
                direction = "short"
            else:
                continue
            rows.append({
                "combo_id": combo_id, "tol_pct": tol,
                "signal_bar_idx": i, "direction": direction,
                "nearest_level": nearest_name, "nearest_dist_pct": round(nearest_dist_pct, 5),
                "close": close, "vwap": round(vwap, 4),
            })
    return pd.DataFrame(rows, columns=["combo_id", "tol_pct", "signal_bar_idx", "direction",
                                        "nearest_level", "nearest_dist_pct", "close", "vwap"])


__all__ = ["build_grid", "generate_signals", "compute_session_vwap_by_date"]
