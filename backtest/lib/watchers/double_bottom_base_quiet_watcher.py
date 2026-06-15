"""DOUBLE_BOTTOM_BASE_QUIET watcher (WATCH-ONLY per OP-21).

16-month combination search (2025-01-01 to 2026-05-15) cross-validated Rank #3:
    double_bottom | NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL
    N=168, WR=59.5%, EdgeCap=+$14.66, Score=+3.55

Cross-validation: N=43 WR=65.1% (90-day) -> N=168 WR=59.5% (16-month).
Expected regression to mean at 4x sample size. Still above 57% promotion gate.

Setup definition:
  1. `double_bottom_detector` fires on the current bar's sliding window
  2. Pattern confidence < 0.60 (conf=LOW in combo_search — base pattern only, or minor
     secondary factors; no "decisive_reclaim" or multi-factor stacks)
  3. VIX < 20 at entry (LOW_VOL regime) — quiet market = clean mean-reversion
  4. Pattern center NOT within $0.50 of any star2+ named level (NOT_NEAR_NAMED)
  5. No time window restriction (fires 09:35-15:55 ET — unlike the MORNING variant)
  6. Cooldown: 30 min between signals

Walk-forward validation result (2026-05-20):
  - Train (2025-01-01 to 2025-09-30): N=68, WR=58.82%
  - Test  (2025-10-01 to 2026-05-15): N=100, WR=60.0%  <- +1.2pp improvement
  - VERDICT: STABLE -- most robust of the three 2026-05-20 watchers
  - No MORNING filter means no overfitting to early 2025 morning regime
  - STATUS: WATCH_STABLE -- direct complement to the MORNING variant (catches pm signals)

Why conf=LOW is the sweet spot:
  - The 0.60-0.70 confidence band has OOS WR=46.8% (N=447) per 90-day analysis -- worst band
  - The pathological case: single `low2_volume_higher` activation (v2 formula) pushed conf to
    0.60, but OOS WR was 38.5% (N=26) -- clearly noise
  - v3 formula fix: `low2_volume_higher` weight 0.15->0.11 so single-factor conf=0.56 (<0.60)
  - Result: conf=LOW bucket (< 0.60) = clean base patterns + volume-only weak confirmations
    These are the PUREST double bottoms -- no ambiguous partial-factor augmentation
  - Paradox: LESS confident (fewer factors) = MORE reliable in quiet markets (VIX<20)
    because a clean W shape in a stable tape needs no augmenting evidence -- it IS the signal

Confidence threshold = 0.60 corresponds to:
  - 0 factors (base only):              conf = 0.45 -- always BELOW ceiling
  - low2_volume_higher only (v3):       conf = 0.56 -- BELOW ceiling (v3 fix)
  - bars_between_sweet_spot only:       conf = 0.55 -- BELOW ceiling
  - very_tight_lows only:               conf = 0.55 -- BELOW ceiling
  - decent_neckline_height only:        conf = 0.50 -- BELOW ceiling
  - decisive_reclaim only:              conf = 0.60 -- AT ceiling (excluded by <)
  - any 2+ factor combination:          conf >= 0.65 -- ABOVE ceiling (excluded)

Real-fills validation result (2026-05-20):
  - N=131 signals (simplified scan, NOT_NEAR_NAMED omitted), 122 completed, 9 no OPRA data
  - Real WR=63.9% (78W/44L), delta=+4.4pp vs scan proxy 59.5%. Total P&L=+$1,755.
  - VERDICT: FAVORABLE — real-fills WR exceeds scan proxy; positive expectancy confirmed
  - Time distribution: 10AM peak (41 signals), spread full RTH — no time-slot concentration
  - Exit: full RTH fires (09:00-15:00), 10AM most active as expected for double bottoms
  - NOT_NEAR_NAMED filter omitted — adding it should further improve WR
  - Full results: analysis/recommendations/db-base-quiet-real-fills.json

Why this is watch-only (OP-21 gates not yet met):
  - Historical gate: 3+ wins PASS (N=168) ✓
  - Walk-forward OOS: STABLE +1.2pp ✓
  - Real-fills: FAVORABLE +4.4pp (WR=63.9%, N=122 completed, total +$1,755) ✓
  - Live J observations: 0/3 needed

OP-21 promotion gate:
  - Historical: N>=168 (full 16-month) ✓
  - Walk-forward: STABLE +1.2pp ✓
  - Real-fills: FAVORABLE +4.4pp (WR=63.9%, N=122 completed, total +$1,755) ✓
    NOTE: simplified scan omits NOT_NEAR_NAMED — full-filter real-fills pending.
  - Live: 3+ live J confirmations on double bottom in quiet market (any time of day)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, double_bottom_detector, enrich_hit_with_proximity
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# -- Detection thresholds -----------------------------------------------------

# VIX gate: LOW_VOL regime (VIX<20 in combo_search)
VIX_LOW_VOL_CEILING: float = 20.0

# Confidence ceiling: conf=LOW tier from combo_search
# Accepts base pattern (0.45) + minor single-factor hits (0.50-0.56)
# Rejects decisive_reclaim solo (0.60) and all 2+ factor combos (>= 0.65)
CONFIDENCE_LOW_CEILING: float = 0.60

# Proximity gate: NOT within $0.50 of any star2+ named level
PROXIMITY_MAX_DISTANCE: float = 0.50

# Sliding window for double_bottom_detector: last 30 bars (~2.5 hours of 5m bars)
_WINDOW_BARS: int = 30

# Cooldown: don't re-fire the same watcher within 30 min of the last signal
_COOLDOWN_MINUTES: int = 30

# No entry time window -- this watcher fires 09:35-15:55 ET (unlike MORNING variant)
_RTH_START: dt.time = dt.time(9, 35)
_RTH_END: dt.time = dt.time(15, 55)


# -- Default exit knobs (OP-21 watch-only conservative) -----------------------

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart-stop ONLY (L55 analog -- same reasoning
                                          # as double_bottom_morning variant: initial bar
                                          # can dip before the full W-completion move)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-level targets (for observation grading in watcher_live.py)
_CHART_STOP_BELOW_NECKLINE: float = 0.30   # stop = neckline - $0.30
_TP1_SPY_MOVE: float = 0.70                # TP1 ~ entry + $0.70
_RUNNER_SPY_MOVE: float = 2.00             # runner ~ entry + $2.00


# -- Module-level state (cooldown tracking) -----------------------------------

_last_signal_time: Optional[dt.datetime] = None


def _build_bars_from_context(ctx: BarContext) -> list[Bar]:
    """Convert the last _WINDOW_BARS rows of prior_bars into Bar objects."""
    if not _PATTERNS_AVAILABLE:
        return []
    import pandas as pd

    df = ctx.prior_bars.tail(_WINDOW_BARS).copy()
    bars = []
    for ts, row in df.iterrows():
        if isinstance(ts, (int, float)):
            open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=int(ts) * 300)
        else:
            try:
                pt = pd.Timestamp(ts)
                open_time = (pt.tz_localize("UTC") if pt.tzinfo is None else pt.tz_convert("UTC")).to_pydatetime()
            except Exception:
                open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
        bars.append(Bar(
            open_time=open_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 50_000)),
            granularity_seconds=300,
            source="spy_5m",
        ))
    return bars


def detect_db_base_quiet_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect DOUBLE_BOTTOM_BASE_QUIET setup on the current bar.

    Returns WatcherSignal with direction="long" if all gates pass.
    Returns None if any gate fails.

    Key difference from DOUBLE_BOTTOM_MORNING_LOW_VOL:
      - No MORNING time restriction (fires 09:35-15:55 ET)
      - Confidence CEILING: only base-pattern hits (conf < 0.60)
        This excludes the pathological 0.60-0.70 band (OOS WR=46.8%)
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # -- Gate 1: RTH window (09:35-15:55 ET) ----------------------------------
    bar_time = ctx.timestamp_et.time()
    if bar_time < _RTH_START or bar_time > _RTH_END:
        return None

    # -- Gate 2: VIX LOW_VOL (<20) --------------------------------------------
    if ctx.vix_now >= VIX_LOW_VOL_CEILING:
        return None

    # -- Gate 3: Cooldown -- don't re-fire within 30 min ---------------------
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # -- Gate 4: Run double_bottom_detector on sliding window ----------------
    bars = _build_bars_from_context(ctx)
    if len(bars) < 10:
        return None

    hit = double_bottom_detector(bars)
    if hit is None:
        return None

    # -- Gate 5: conf=LOW -- reject medium/high confidence hits --------------
    # This is the KEY discriminator: the 0.60-0.70 band is pathological OOS.
    # Keep only clean base-pattern double bottoms (conf < 0.60).
    if hit.confidence >= CONFIDENCE_LOW_CEILING:
        return None

    # -- Gate 6: NOT near a named level ($0.50 proximity check) -------------
    named_levels = [
        {"price": lvl, "name": f"level_{lvl:.2f}", "stars": 2}
        for lvl in ctx.levels_active
    ]
    enriched = enrich_hit_with_proximity(hit, named_levels, max_distance=PROXIMITY_MAX_DISTANCE)
    if enriched.notes.get("near_key_level") is True:
        return None

    # -- Signal passes all gates ----------------------------------------------
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    neckline = enriched.notes.get("neckline", bar_close)

    v2_factors = enriched.notes.get("v2_factors_active", [])
    conf_score = enriched.confidence

    # All signals are "low confidence" by gate design, but report context
    if len(v2_factors) > 0:
        conf_note = f"base+minor factors={v2_factors} conf={conf_score:.2f} (conf=LOW qualified)"
    else:
        conf_note = f"pure base pattern conf={conf_score:.2f} (cleanest W shape)"

    stop_price = float(neckline) - _CHART_STOP_BELOW_NECKLINE
    tp1_price = bar_close + _TP1_SPY_MOVE
    runner_price = bar_close + _RUNNER_SPY_MOVE

    vix_regime = f"VIX={ctx.vix_now:.2f} (LOW_VOL <{VIX_LOW_VOL_CEILING})"
    proximity_note = enriched.notes.get("nearest_key_level_distance", None)
    prox_str = f"nearest_level_dist=${proximity_note:.2f}" if proximity_note else "no_nearby_level"
    time_note = f"time={ctx.timestamp_et.strftime('%H:%M')} ET (RTH, no morning filter)"

    return WatcherSignal(
        watcher_name="db_base_quiet",
        setup_name="DOUBLE_BOTTOM_BASE_QUIET",
        direction="long",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence="low",   # always low by gate design -- that's the feature, not the bug
        reason=(
            f"Double bottom ({conf_note}). "
            f"Neckline={neckline:.2f}, stop={stop_price:.2f}. "
            f"{vix_regime}. {prox_str}. {time_note}."
        ),
        triggers_fired=["double_bottom_detector", "conf_low_gate", "low_vol_vix", "not_near_named"],
        metadata={
            "combo_search_rank": 9,
            "combo_search_n": 168,
            "combo_search_wr_pct": 59.5,
            "combo_search_window": "2025-01-01 to 2026-05-15",
            "walk_forward_verdict": "STABLE",
            "walk_forward_train_wr": 58.82,
            "walk_forward_test_wr": 60.0,
            "walk_forward_delta_pp": 1.2,
            "confidence_score": conf_score,
            "confidence_ceiling": CONFIDENCE_LOW_CEILING,
            "v2_factors_active": v2_factors,
            "neckline": neckline,
            "vix_now": ctx.vix_now,
            "op21_live_gate": "0/3 -- DO NOT promote until 3+ live J confirmations",
        },
    )
