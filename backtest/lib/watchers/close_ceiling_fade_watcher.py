"""CLOSE_CEILING_DISTRIBUTION_FADE watcher (WATCH-ONLY per OP-21).

Detects fake breakouts at named ★★+ resistance/carry levels — the L59 pattern
identified by J during the live 2026-05-20 session.

Pattern definition (J-identified, 2026-05-20):
  1. N_MIN_STREAK >= 3 consecutive bars where:
       bar.high >= resistance_level - LEVEL_TOLERANCE   (bar "tested" the ceiling)
       AND bar.close < resistance_level                  (but failed to CLOSE above)
     → This is DISTRIBUTION: bulls are absorbed every time they push to the level.
  2. The SIGNAL BAR: bar.close > resistance_level       (a "breakout" bar)
     → But coming after N_MIN_STREAK distribution bars, this is a FAKE BREAKOUT / BULL TRAP.
     → The signal is: "go short — the breakout will reverse."

Real-data evidence (2026-05-20 SPY, ceiling=740.49 PM, from L59 CLAUDE.md entry):
  14:00 H:740.49 C:740.49 — touch (close == level, does not qualify as "above")
  14:05 H:740.49 C:740.03 — ceiling test, close below → run=1
  14:10 H:740.42 C:740.30 — below ceiling
  14:15 H:740.42 C:740.18 — below ceiling
  14:20 H:740.26 C:740.04 — lower
  14:30 H:740.42 C:740.40 — another ceiling touch, close below → run accumulates
  14:40 C:740.72 — fake breakout (first close ABOVE 740.49) → SIGNAL
  14:45 C:739.77, vol=45,411 — reversal on elevated volume

J insight (verbatim from live session):
  "notice how none of the 5m bars closed above the key level 736.13 that is an
   indicator we should have noticed to indicate bearish sentiment"

Why historical backtest is impossible:
  The pattern REQUIRES named ★★+ levels from key-levels.json (which changes daily
  and is not archived historically). Structural proxies (PDH, morning_high, rolling
  window high) produced 0% WR across 5 signals — the fake breakout cannot be
  distinguished from a real one without knowing where traders are watching.
  Source: analysis/recommendations/close_ceiling_fade_scan.json (2026-05-20 scan).

  SOLUTION: live watcher accumulates observations vs today's key-levels.json in real
  time. After N >= 20 live observations, run real-fills simulation for OP-21 gate.

OP-21 promotion gate (NOT YET PASSED):
  - Historical gate: CANNOT PASS (no key-levels.json archive) — bypassed per above
  - Live accumulation gate: needs N >= 20 observations with WR >= 50% → real-fills
  - Live J gate: needs 3 J-confirmed wins before any promotion to heartbeat.md
  - DO NOT wire into production heartbeat.md until live gate passes

IMPORTANT — LIVE vs SIMULATION STOP DISCREPANCY:
  This watcher emits stop_price = resistance_level + $0.30 (_CHART_STOP_ABOVE_LEVEL).
  simulator_real.py adds an additional LEVEL_STOP_BUFFER = $0.50, giving effective
  stop resistance_level + $0.80 in simulation. heartbeat.md must also add the $0.50
  buffer when consuming this signal — otherwise the live chart stop fires $0.50
  tighter than simulated, triggering more false exits on the initial retest bounce
  (per L51/L55 lesson: violent initial bounces on level-break entries invalidate
  all premium stops AND tight chart stops).
  Promotion protocol: before enabling in heartbeat.md, confirm LEVEL_STOP_BUFFER is applied.

Exit logic (L51/L55 lesson encoded):
  - premium_stop_pct = -0.99 (disabled) — ONLY chart stop. Premium stops are
    incompatible with fake-breakout entries: the initial bounce after the fake
    breakout can drop put premium 40-60% before the directional move develops.
  - Chart stop: resistance_level + $0.30 (watcher) + $0.50 (sim buffer) = $0.80 effective
  - TP1: entry - $0.70 (first reversal target — back inside the distribution zone)
  - Runner: entry - $2.50 (if breakdown extends beyond the zone)

MUTUAL EXCLUSIVITY with NLWB:
  NLWB fires when close > support_level (bounce = bullish). This watcher fires
  when close > resistance_level after N distribution bars (fake breakout = bearish).
  They fire on different levels (support vs resistance) and different directions.
  However, on a day where a prior support becomes resistance (broken_to_resistance),
  both could fire at different price levels — that is NOT an exclusion violation.

Confidence tiers:
  high:   streak >= 5 AND VIX >= 20 (elevated vol + persistent distribution)
  medium: streak >= 4 OR (streak >= 3 AND VIX >= 20)
  low:    streak == 3 AND VIX < 20 (base pattern — observe + log)

Research source:
  L59 (CLAUDE.md OP-25 absorbed lessons 2026-05-20 evening)
  backtest/autoresearch/close_ceiling_fade_scan.py (structural proxy scan → 0% WR)
  analysis/recommendations/close_ceiling_fade_scan.json (scan output → FAIL, requires named levels)
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters ─────────────────────────────────────────────────────

# Minimum consecutive distribution bars before a breakout is considered "fake"
N_MIN_STREAK: int = 3

# How far back to scan prior bars for the distribution pattern
LOOKBACK_BARS: int = 12

# A bar.high within LEVEL_TOLERANCE of the resistance level counts as "testing" the ceiling
# 5 cents is tight enough to avoid false positives while matching real wicks
LEVEL_TOLERANCE: float = 0.05

# The signal bar must close > resistance_level + BREAKOUT_MIN_CENTS
# Avoids triggering on a close that's essentially AT the level (noise)
BREAKOUT_MIN_CENTS: float = 0.05

# Time window: skip gap-open 15 min and avoid late-session theta drain (same as BRAL watcher)
ENTRY_TIME_START: dt.time = dt.time(9, 45)
ENTRY_TIME_END: dt.time = dt.time(14, 30)

# Cooldown: only one signal per 45-minute window (prevents hammering the same level twice)
_COOLDOWN_MINUTES: int = 45

# Named-level gate: only fire at levels with strength.stars >= 2
_MIN_STARS: int = 2

# Roles that qualify as resistance from above (bearish defense)
_RESISTANCE_ROLES: frozenset[str] = frozenset({
    "resistance",
    "carry",
    "broken_to_resistance",
})


# ── Exit knobs (conservative OP-21 watch-only defaults) ─────────────────────

DEFAULT_PREMIUM_STOP_PCT: float = -0.99    # chart-stop ONLY — L51/L55: premium stop incompatible
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-price approximations for stop/target
# NOTE: watcher emits level + $0.30; simulator_real.py adds $0.50 buffer → $0.80 effective
_CHART_STOP_ABOVE_LEVEL: float = 0.30
_TP1_SPY_DROP: float = 0.70    # TP1: first reversal back below ceiling
_RUNNER_SPY_DROP: float = 2.50  # runner: extended move below zone


# ── Key-levels.json cache (refreshed per day) ────────────────────────────────

# Path from this file: backtest/lib/watchers/ → up 3 levels → repo root → automation/state
_KEY_LEVELS_PATH: Path = (
    Path(__file__).resolve().parents[3] / "automation" / "state" / "key-levels.json"
)

_cached_levels: list[float] = []
_cached_levels_date: Optional[str] = None


def _load_resistance_levels(today_str: str) -> list[float]:
    """Load ★★+ resistance/carry/broken_to_resistance levels from key-levels.json.

    Results are cached per calendar day (key-levels.json changes daily but is
    stable within a session). If the file is missing or unreadable, returns []
    — watcher returns None gracefully without crashing the live loop.
    """
    global _cached_levels, _cached_levels_date

    if _cached_levels_date == today_str:
        return _cached_levels

    levels: list[float] = []
    try:
        data = json.loads(_KEY_LEVELS_PATH.read_text(encoding="utf-8-sig"))
        for entry in data.get("levels", []):
            price = entry.get("price", 0.0)
            role = entry.get("role", "")
            stars = entry.get("strength", {}).get("stars", 0)
            if price > 0 and role in _RESISTANCE_ROLES and stars >= _MIN_STARS:
                levels.append(float(price))
    except Exception:
        # File missing, corrupt JSON, unexpected schema — silently return empty.
        # Watcher will return None; the next bar will re-attempt the load.
        pass

    _cached_levels = sorted(set(levels))  # deduplicate + sort ascending
    _cached_levels_date = today_str
    return _cached_levels


# ── Pattern detector (pure, no imports) ──────────────────────────────────────

def _detect_close_ceiling(
    highs: list[float],
    closes: list[float],
    ceiling: float,
    n_min: int = 3,
) -> tuple[bool, int]:
    """Return (pattern_detected, max_consecutive_run).

    A qualifying bar: bar.high >= ceiling - LEVEL_TOLERANCE  AND  bar.close < ceiling.
    A non-qualifying bar (close >= ceiling) RESETS the consecutive run counter.

    This is a self-contained copy of the logic validated in
    crypto/validators/v33_close_ceiling_detection.py (T1-T8, all PASS).
    Kept inline to avoid cross-importing from the validators folder.
    """
    if not highs or not closes or len(highs) != len(closes):
        return False, 0

    max_run = 0
    current_run = 0
    for h, c in zip(highs, closes):
        if h >= ceiling - LEVEL_TOLERANCE and c < ceiling:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0

    return max_run >= n_min, max_run


# ── Module-level cooldown state ───────────────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


# ── Public detector ───────────────────────────────────────────────────────────

def detect_close_ceiling_fade_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect CLOSE_CEILING_DISTRIBUTION_FADE fake-breakout bear setup.

    Entry logic:
      1. Time gate: 09:45-14:30 ET
      2. Cooldown: 45 min since last signal
      3. Load ★★+ resistance/carry levels from key-levels.json
      4. For each level: scan last LOOKBACK_BARS prior bars for N_MIN_STREAK
         consecutive distribution bars (high >= level - tolerance, close < level)
      5. Current bar closes > level + BREAKOUT_MIN_CENTS → fake breakout SIGNAL

    Returns WatcherSignal(direction="short") — buy puts — if all gates pass.
    Returns None if any gate fails.

    Confidence tiers:
      "high":   streak >= 5 AND VIX >= 20
      "medium": streak >= 4 OR (streak >= 3 AND VIX >= 20)
      "low":    streak == 3 AND VIX < 20 (base pattern — observe only)
    """
    global _last_signal_time

    # ── Gate 1: Time window (09:45 - 14:30 ET) ──────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START or bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: Cooldown ─────────────────────────────────────────────────────
    if _last_signal_time is not None:
        elapsed_min = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed_min < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: Named ★★+ resistance levels available ───────────────────────
    today_str = ctx.timestamp_et.date().isoformat()
    resistance_levels = _load_resistance_levels(today_str)
    if not resistance_levels:
        return None

    # ── Gate 4: Close-ceiling distribution + fake-breakout ──────────────────
    bar_close = float(ctx.bar.get("close", 0))

    signal_level: Optional[float] = None
    signal_streak: int = 0

    # Get the prior bars (excluding the current signal bar)
    prior_df = ctx.prior_bars
    if len(prior_df) < N_MIN_STREAK + 1:
        return None

    # Last LOOKBACK_BARS bars BEFORE the current bar
    # prior_bars includes the current bar at index [-1] (per watcher_live + watcher_replay context)
    scan_df = prior_df.tail(LOOKBACK_BARS + 1).iloc[:-1]
    if len(scan_df) < N_MIN_STREAK:
        return None

    scan_highs: list[float] = scan_df["high"].tolist()
    scan_closes: list[float] = scan_df["close"].tolist()

    for level in resistance_levels:
        # Current bar must close ABOVE the level by at least BREAKOUT_MIN_CENTS
        if bar_close <= level + BREAKOUT_MIN_CENTS:
            continue

        detected, streak = _detect_close_ceiling(scan_highs, scan_closes, level, N_MIN_STREAK)
        if not detected:
            continue

        # Take the level with the highest streak (strongest distribution signal)
        if streak > signal_streak:
            signal_streak = streak
            signal_level = level

    if signal_level is None:
        return None

    # ── All gates passed — emit signal ───────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    vix_now = getattr(ctx, "vix_now", None) or 17.0
    stop_price = signal_level + _CHART_STOP_ABOVE_LEVEL
    tp1_price = bar_close - _TP1_SPY_DROP
    runner_price = bar_close - _RUNNER_SPY_DROP

    # Confidence tier
    if signal_streak >= 5 and vix_now >= 20.0:
        confidence = "high"
        conf_note = (
            f"streak={signal_streak} bars (strong distribution) at ★★+ level, "
            f"VIX={vix_now:.1f} >= 20 (elevated vol)"
        )
    elif signal_streak >= 4 or (signal_streak >= 3 and vix_now >= 20.0):
        confidence = "medium"
        conf_note = (
            f"streak={signal_streak} bars at ★★+ level, VIX={vix_now:.1f}"
        )
    else:
        confidence = "low"
        conf_note = (
            f"streak={signal_streak} bars (base pattern, VIX={vix_now:.1f} < 20)"
        )

    # VIX bucket for metadata
    if vix_now < 15:
        vix_bucket = "<15"
    elif vix_now < 20:
        vix_bucket = "15-20"
    elif vix_now < 25:
        vix_bucket = "20-25"
    else:
        vix_bucket = ">=25"

    breakout_by = round(bar_close - signal_level, 2)

    return WatcherSignal(
        watcher_name="close_ceiling_fade",
        setup_name="CLOSE_CEILING_DISTRIBUTION_FADE",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"Close-ceiling distribution fade: {signal_streak}-bar sequence at ★★+ "
            f"resistance ${signal_level:.2f} — none closed above, all wicked to ceiling. "
            f"This bar (C:{bar_close:.2f}) breaks out +{breakout_by:.2f} above level = FAKE BREAKOUT. "
            f"Direction: short (buy puts). "
            f"Stop={stop_price:.2f} (level+$0.30; add $0.50 in heartbeat → $0.80 effective). "
            f"TP1={tp1_price:.2f} (-$0.70). Runner={runner_price:.2f} (-$2.50). "
            f"VIX={vix_now:.1f} ({vix_bucket}). {conf_note}. "
            f"L59 evidence: 2026-05-20 SPY 740.49 PM ceiling, 6-bar distribution "
            f"→ 14:40 fake break → 14:45 reversal vol=45,411."
        ),
        triggers_fired=["close_ceiling_streak", "resistance_level_named", "fake_breakout_bar"],
        metadata={
            "resistance_level": signal_level,
            "streak_bars": signal_streak,
            "breakout_above_level_by_dollars": breakout_by,
            "vix_bucket": vix_bucket,
            "vix_now": vix_now,
            "stop_discrepancy_note": (
                "Watcher emits level+$0.30; simulator_real.py and heartbeat.md must "
                "add $0.50 LEVEL_STOP_BUFFER → $0.80 effective. Per L51/L55 lesson: "
                "premium_stop_pct=-0.99 (disabled). Chart stop is the only exit gate."
            ),
            "promotion_gate": (
                "OP-21: historical gate bypassed (no key-levels archive). "
                "Live gate: N>=20 observations WR>=50% → real-fills → 3 live J wins."
            ),
        },
    )
