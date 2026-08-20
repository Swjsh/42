"""PER-SYMBOL LEVELS — the missing input that was vetoing every signal.

WHY THIS EXISTS (found by the participation cascade, 2026-08-20): the forked engine's filter 10
requires a LEVEL-TIED trigger — `level_rejection`, `fhh_level_rejection`, `confluence`,
`sequence_rejection`, or `trendline_rejection`. With no levels supplied, no level-tied trigger
can ever fire, so filter 10 vetoed 100% of symbols on every tick. The lane was structurally
incapable of ever trading, and the tick's own cascade surfaced it as `action_directional = 0`.

The SPY engine gets its levels from `setup/scripts/refresh_levels_intraday.py` writing
`automation/state/key-levels.json` — a SINGLE-SYMBOL file whose schema has no symbol field at
all. That does not generalize, so this lane computes its own, per symbol, from bars.

DELIBERATELY NARROW. This is not a rewrite of the shop's level doctrine — it is the minimum
that lets a level-tied trigger exist, computed the way the shop already thinks about levels
(J's standing philosophy: supply/demand zones, prior-period extremes, round numbers):

  * swing highs/lows  — fractal pivots over a lookback window
  * prior period H/L/C — prior day and prior week (the levels every desk watches)
  * round numbers     — increment derived from the symbol's own price scale, never a constant

EVERY THRESHOLD IS SYMBOL-RELATIVE. A $0.30 tolerance is 0.04% of a $700 ETF and 1.9% of a $16
stock; the SPY engine is full of such constants and that coupling is exactly what this lane
exists to shed. Widths here are ATR-derived and the round-number increment scales with price.

NO LOOK-AHEAD: levels for a decision at bar i are computed from bars STRICTLY BEFORE i. The
caller passes the already-sliced frame; this module never reaches for "today's" extreme while
today is still forming.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Level:
    price: float
    kind: str          # swing_high | swing_low | prior_day_high | ... | round
    lookback_bars: int  # provenance: how far back the evidence came from


class LevelError(ValueError):
    """Fail loud: a caller that gets zero levels must know it, not silently score without them."""


def round_increment(price: float) -> float:
    """Psychological-level spacing, derived from the symbol's own price scale.

    A $16 stock respects $0.50/$1 levels; a $700 ETF respects $5/$10. A fixed increment would
    emit 700 useless levels for the ETF or 2 for the stock.
    """
    if price <= 0:
        raise LevelError(f"price must be > 0 (got {price})")
    if price < 25:
        return 1.0
    if price < 100:
        return 2.5
    if price < 300:
        return 5.0
    if price < 800:
        return 10.0
    return 25.0


def _atr(bars: pd.DataFrame, length: int = 14) -> float:
    if len(bars) < length + 1:
        raise LevelError(f"need >{length} bars for ATR, got {len(bars)}")
    h, l, c = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
    prev = np.roll(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))[1:]
    return float(pd.Series(tr).ewm(alpha=1 / length, adjust=False).mean().iloc[-1])


def swing_levels(bars: pd.DataFrame, window: int = 3, max_each: int = 6) -> list[Level]:
    """Fractal pivots: a bar whose high (low) exceeds `window` bars on BOTH sides.

    Requiring both sides is what makes it a confirmed pivot rather than a running extreme —
    and it is inherently backward-looking, so it cannot peek at unformed structure.
    """
    out: list[Level] = []
    h, l = bars["high"].to_numpy(), bars["low"].to_numpy()
    n = len(bars)
    for i in range(window, n - window):
        seg_h, seg_l = h[i - window:i + window + 1], l[i - window:i + window + 1]
        if h[i] == seg_h.max() and (seg_h == h[i]).sum() == 1:
            out.append(Level(float(h[i]), "swing_high", n - i))
        if l[i] == seg_l.min() and (seg_l == l[i]).sum() == 1:
            out.append(Level(float(l[i]), "swing_low", n - i))
    highs = [x for x in out if x.kind == "swing_high"][-max_each:]
    lows = [x for x in out if x.kind == "swing_low"][-max_each:]
    return highs + lows


def prior_period_levels(bars: pd.DataFrame) -> list[Level]:
    """Prior DAY and prior WEEK high/low/close, from completed periods only."""
    if not isinstance(bars.index, pd.DatetimeIndex):
        return []
    out: list[Level] = []
    by_day = bars.groupby(bars.index.date)
    days = list(by_day.groups)
    if len(days) >= 2:
        prev = by_day.get_group(days[-2])
        out += [Level(float(prev["high"].max()), "prior_day_high", len(bars)),
                Level(float(prev["low"].min()), "prior_day_low", len(bars)),
                Level(float(prev["close"].iloc[-1]), "prior_day_close", len(bars))]
    iso = bars.index.isocalendar()
    wk = pd.Series(iso.year.astype(str) + "-" + iso.week.astype(str), index=bars.index)
    by_week = bars.groupby(wk)
    weeks = list(by_week.groups)
    if len(weeks) >= 2:
        prevw = by_week.get_group(weeks[-2])
        out += [Level(float(prevw["high"].max()), "prior_week_high", len(bars)),
                Level(float(prevw["low"].min()), "prior_week_low", len(bars))]
    return out


def round_levels(spot: float, n_each: int = 3) -> list[Level]:
    inc = round_increment(spot)
    base = round(spot / inc) * inc
    out = []
    for k in range(-n_each, n_each + 1):
        p = base + k * inc
        if p > 0:
            out.append(Level(round(float(p), 4), "round", 0))
    return out


def dedupe(levels: Sequence[Level], tolerance: float) -> list[Level]:
    """Collapse levels within `tolerance` of each other, keeping the first (most specific).

    Two families naming the same price is ONE level, not two — counting it twice is how a
    confluence score ends up measuring its own double-count (a defect this shop already hit).
    """
    kept: list[Level] = []
    for lv in sorted(levels, key=lambda x: x.price):
        if not any(abs(lv.price - k.price) <= tolerance for k in kept):
            kept.append(lv)
    return kept


def compute_levels(
    bars: pd.DataFrame,
    *,
    spot: Optional[float] = None,
    swing_window: int = 3,
    active_band_pct: float = 0.05,
) -> tuple[list[float], list[float]]:
    """Return (active_levels, multi_day_levels) as plain floats for `build_signal`.

    `active_levels` are those within `active_band_pct` of spot — the ones a trigger could
    plausibly interact with this session. `multi_day_levels` is the wider set used for
    confluence. Both are deduped at an ATR-derived tolerance so one price is one level.
    """
    if bars is None or len(bars) < 30:
        raise LevelError(f"need >=30 bars to compute levels, got {0 if bars is None else len(bars)}")
    px = float(spot if spot is not None else bars["close"].iloc[-1])
    atr = _atr(bars)
    tol = max(atr * 0.15, px * 0.0005)

    all_levels = swing_levels(bars, window=swing_window) + prior_period_levels(bars) \
        + round_levels(px)
    all_levels = dedupe(all_levels, tol)
    if not all_levels:
        raise LevelError("computed zero levels — refusing to score a symbol with no levels")

    band = px * active_band_pct
    active = sorted({round(lv.price, 4) for lv in all_levels if abs(lv.price - px) <= band})
    multi = sorted({round(lv.price, 4) for lv in all_levels})
    return active, multi
