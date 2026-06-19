"""FLOOR_HOLD_DISTRIBUTION_BOUNCE watcher (WATCH-ONLY per OP-21).

Detects fake breakdowns at named ★★+ support/carry levels — the bullish
analog of L59's close-ceiling distribution pattern.

Pattern definition (mirror of L59, bull side):
  1. N_MIN_STREAK >= 3 consecutive bars where:
       bar.low <= support_level + LEVEL_TOLERANCE   (bar "tested" the floor)
       AND bar.close > support_level                 (but defended close above)
     → This is ACCUMULATION: bears are absorbed every time they push to the level.
  2. The SIGNAL BAR: bar.close < support_level - BREAKDOWN_MIN_CENTS  (a "breakdown" bar)
     → But coming after N_MIN_STREAK accumulation bars, this is a FAKE BREAKDOWN / BEAR TRAP.
     → The signal is: "go long — the breakdown will reverse."

Symmetry with CLOSE_CEILING_DISTRIBUTION_FADE (L59):
  close_ceiling_fade: N bars wick to resistance, close below → fake breakout above → SHORT (puts)
  floor_hold_bounce:  N bars wick to support,    close above → fake breakdown below → LONG (calls)

Theoretical basis:
  The "spring" pattern in Wyckoff analysis: after repeated tests of support where
  buyers absorb every probe, a final bar that closes BELOW the level draws in
  fresh shorts — who then get trapped as the real buyers return. The reversal is
  typically fast and sharp (similar explosive dynamics to a fake breakout trap).

  The ★★+ level gate is critical: structural proxies (PDL, rolling-window low)
  cannot distinguish real support from coincidental proximity. Named levels carry
  trader awareness — they define where stops are clustered.

Why historical backtest is impossible:
  The pattern requires named ★★+ levels from key-levels.json (which changes daily
  and is not archived historically). Same constraint as close_ceiling_fade (L59).
  SOLUTION: live watcher accumulates observations vs today's key-levels.json in real
  time. After N >= 20 live observations, run real-fills simulation for OP-21 gate.

OP-21 promotion gate (NOT YET PASSED):
  - Historical gate: CANNOT PASS (no key-levels.json archive) — bypassed per above
  - Live accumulation gate: needs N >= 20 observations with WR >= 50% → real-fills
  - Live J gate: needs 3 J-confirmed wins before any promotion to heartbeat.md
  - DO NOT wire into production heartbeat.md until live gate passes

IMPORTANT — LIVE vs SIMULATION STOP DISCREPANCY:
  This watcher emits stop_price = support_level - $0.30 (_CHART_STOP_BELOW_LEVEL).
  simulator_real.py must add LEVEL_STOP_BUFFER = $0.50 below, giving effective
  stop support_level - $0.80 in simulation. heartbeat.md must also subtract $0.50.
  Otherwise the live chart stop fires $0.50 tighter than simulated, triggering
  more false exits on the initial bounce after the fake breakdown (per L51/L55:
  violent initial moves on level-break entries invalidate all premium stops AND
  tight chart stops).

Exit logic (L51/L55 lesson encoded):
  - premium_stop_pct = -0.99 (disabled) — ONLY chart stop. Premium stops are
    incompatible with fake-breakdown entries: the initial counter-move can drop
    call premium 40-60% before the directional move develops.
  - Chart stop: support_level - $0.30 (watcher) + $0.50 (sim buffer) = $0.80 effective
  - TP1: entry + $0.70 (first reversal target — back inside the accumulation zone)
  - Runner: entry + $2.50 (if bounce extends beyond the zone)

MUTUAL EXCLUSIVITY with CLOSE_CEILING_DISTRIBUTION_FADE:
  FLOOR_HOLD_BOUNCE fires when close < support_level (breakdown = bull trap → long).
  CLOSE_CEILING_DISTRIBUTION_FADE fires when close > resistance_level (breakout = bear trap → short).
  They fire at different levels (support vs resistance) and different directions.
  Carry levels appear in BOTH watchers' level lists — but a CARRY level triggers
  floor_hold only when close drops BELOW it, and close_ceiling only when close rises
  ABOVE it. For any given bar, both conditions cannot simultaneously hold for the
  same level, so there is no logical exclusion violation.

Confidence tiers:
  high:   streak >= 5 AND VIX >= 20 (elevated vol + persistent floor defense)
  medium: streak >= 4 OR (streak >= 3 AND VIX >= 20)
  low:    streak == 3 AND VIX < 20 (base pattern — observe + log)

Research sources:
  L59 (CLAUDE.md OP-25 absorbed lessons 2026-05-20 evening) — original close-ceiling
  crypto/validators/v33_close_ceiling_detection.py — both detect_close_ceiling +
    detect_floor_hold implemented and tested (T1-T8 all PASS)
  backtest/lib/watchers/close_ceiling_fade_watcher.py — structural template
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from .level_source import load_named_levels
from ..filters import BarContext


# ── Detection parameters ─────────────────────────────────────────────────────

# Minimum consecutive accumulation bars before a breakdown is considered "fake"
N_MIN_STREAK: int = 3

# How far back to scan prior bars for the accumulation pattern
LOOKBACK_BARS: int = 12

# A bar.low within LEVEL_TOLERANCE of the support level counts as "testing" the floor.
# 5 cents allows a bar whose low just missed the exact level to qualify.
LEVEL_TOLERANCE: float = 0.05

# The signal bar must close < support_level - BREAKDOWN_MIN_CENTS.
# Avoids triggering on a close that's essentially AT the level (noise).
BREAKDOWN_MIN_CENTS: float = 0.05

# Time window: skip gap-open 15 min and avoid late-session theta drain
ENTRY_TIME_START: dt.time = dt.time(9, 45)
ENTRY_TIME_END: dt.time = dt.time(14, 30)

# Cooldown: only one signal per 45-minute window (prevents hammering same level twice)
_COOLDOWN_MINUTES: int = 45

# Named-level gate: only fire at levels with strength.stars >= 2
_MIN_STARS: int = 2

# Roles that qualify as support from below (bullish defense).
# NOTE: key-levels.json `role` values are structural (e.g. "broken_to_support") or
# null; the tier ("Carry") lives in a separate field. The shared loader matches on
# BOTH role and type, so support-typed levels (type=="support") and broken-to-support
# roles both qualify. "carry"/"support" kept for back-compat with any role= usage.
_SUPPORT_ROLES: frozenset[str] = frozenset({
    "support",
    "carry",
    "broken_to_support",
})

# Level `type` values that qualify as support (the schema-v3 field the live file
# actually populates). The 2026-06-18 PML carries type=="support", role=null.
_SUPPORT_TYPES: frozenset[str] = frozenset({"support"})


# ── Exit knobs (conservative OP-21 watch-only defaults) ─────────────────────

DEFAULT_PREMIUM_STOP_PCT: float = -0.99    # chart-stop ONLY — L51/L55: premium stop incompatible
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-price approximations for stop/target
# NOTE: watcher emits level - $0.30; simulator_real.py subtracts $0.50 buffer → $0.80 effective
_CHART_STOP_BELOW_LEVEL: float = 0.30
_TP1_SPY_RISE: float = 0.70    # TP1: first reversal back above floor
_RUNNER_SPY_RISE: float = 2.50  # runner: extended move above zone


# ── Key-levels.json level loading (shared helper, 2026-06-18 schema fix) ──────
#
# Levels are loaded via backtest.lib.watchers.level_source.load_named_levels, which
# derives ★-strength from the schema-v3 `tier` field (Active=2/Carry=3/Reference=2)
# when the planned `strength.stars` object is absent (it is, in the live file) and
# caps psychological / round-number levels at ★ so they never clear the >=2 gate.
# Before this fix the bespoke loader read `strength.stars` directly → always 0 →
# empty list → this watcher fired on NOTHING live.
#
# Test-injection override: gym validators (v34) set module globals _cached_levels +
# _cached_levels_date to bypass file I/O. When _cached_levels_date matches today_str,
# we honour that injected list verbatim. Otherwise we delegate to the shared loader.
_cached_levels: list[float] = []
_cached_levels_date: Optional[str] = None


def _load_support_levels(today_str: str) -> list[float]:
    """Load support levels (★★+) for today from key-levels.json via the shared loader.

    Honours the v34 test-injection override (_cached_levels / _cached_levels_date).
    Returns sorted unique support/carry prices; [] if the file is missing/corrupt
    (watcher then returns None gracefully).
    """
    if _cached_levels_date == today_str:
        return _cached_levels

    return load_named_levels(
        today_str,
        roles=_SUPPORT_ROLES,
        types=_SUPPORT_TYPES,
        min_stars=_MIN_STARS,
    )


# ── Pattern detector (pure, no imports) ──────────────────────────────────────

def _detect_floor_hold(
    lows: list[float],
    closes: list[float],
    floor: float,
    n_min: int = 3,
) -> tuple[bool, int]:
    """Return (pattern_detected, max_consecutive_run).

    A qualifying bar: bar.low <= floor + LEVEL_TOLERANCE  AND  bar.close > floor.
    A non-qualifying bar (close <= floor) RESETS the consecutive run counter.

    Mirror of _detect_close_ceiling (see close_ceiling_fade_watcher.py).
    This inlined implementation is validated in v33_close_ceiling_detection.py
    T4-T8 (all PASS). Kept inline to avoid cross-importing from the validators
    folder.
    """
    if not lows or not closes or len(lows) != len(closes):
        return False, 0

    max_run = 0
    current_run = 0
    for l, c in zip(lows, closes):
        if l <= floor + LEVEL_TOLERANCE and c > floor:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0

    return max_run >= n_min, max_run


# ── Module-level cooldown state ───────────────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


# ── Public detector ───────────────────────────────────────────────────────────

def detect_floor_hold_bounce_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect FLOOR_HOLD_DISTRIBUTION_BOUNCE fake-breakdown bull setup.

    Entry logic:
      1. Time gate: 09:45-14:30 ET
      2. Cooldown: 45 min since last signal
      3. Load ★★+ support/carry levels from key-levels.json
      4. For each level: scan last LOOKBACK_BARS prior bars for N_MIN_STREAK
         consecutive accumulation bars (low <= level + tolerance, close > level)
      5. Current bar closes < level - BREAKDOWN_MIN_CENTS → fake breakdown SIGNAL

    Returns WatcherSignal(direction="long") — buy calls — if all gates pass.
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

    # ── Gate 3: Named ★★+ support levels available ───────────────────────────
    today_str = ctx.timestamp_et.date().isoformat()
    support_levels = _load_support_levels(today_str)
    if not support_levels:
        return None

    # ── Gate 4: Floor-hold accumulation + fake-breakdown ────────────────────
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

    scan_lows: list[float] = scan_df["low"].tolist()
    scan_closes: list[float] = scan_df["close"].tolist()

    for level in support_levels:
        # Current bar must close BELOW the level by at least BREAKDOWN_MIN_CENTS
        if bar_close >= level - BREAKDOWN_MIN_CENTS:
            continue

        detected, streak = _detect_floor_hold(scan_lows, scan_closes, level, N_MIN_STREAK)
        if not detected:
            continue

        # Take the level with the highest streak (strongest accumulation signal)
        if streak > signal_streak:
            signal_streak = streak
            signal_level = level

    if signal_level is None:
        return None

    # ── All gates passed — emit signal ───────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    vix_now = getattr(ctx, "vix_now", None) or 17.0
    stop_price = signal_level - _CHART_STOP_BELOW_LEVEL
    tp1_price = bar_close + _TP1_SPY_RISE
    runner_price = bar_close + _RUNNER_SPY_RISE

    # Confidence tier
    if signal_streak >= 5 and vix_now >= 20.0:
        confidence = "high"
        conf_note = (
            f"streak={signal_streak} bars (strong accumulation) at ★★+ level, "
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

    breakdown_by = round(signal_level - bar_close, 2)

    return WatcherSignal(
        watcher_name="floor_hold_bounce",
        setup_name="FLOOR_HOLD_DISTRIBUTION_BOUNCE",
        direction="long",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"Floor-hold accumulation bounce: {signal_streak}-bar sequence at ★★+ "
            f"support ${signal_level:.2f} — bulls defended every dip, none closed below. "
            f"This bar (C:{bar_close:.2f}) fakes down -{breakdown_by:.2f} below level = FAKE BREAKDOWN. "
            f"Direction: long (buy calls). "
            f"Stop={stop_price:.2f} (level-$0.30; subtract $0.50 in heartbeat → $0.80 effective below). "
            f"TP1={tp1_price:.2f} (+$0.70). Runner={runner_price:.2f} (+$2.50). "
            f"VIX={vix_now:.1f} ({vix_bucket}). {conf_note}. "
            f"Symmetric pattern with L59 (close-ceiling). "
            f"Bull side: Wyckoff spring — bears trapped as buyers return."
        ),
        triggers_fired=["floor_hold_streak", "support_level_named", "fake_breakdown_bar"],
        metadata={
            "support_level": signal_level,
            "streak_bars": signal_streak,
            "breakdown_below_level_by_dollars": breakdown_by,
            "vix_bucket": vix_bucket,
            "vix_now": vix_now,
            "stop_discrepancy_note": (
                "Watcher emits level-$0.30; simulator_real.py and heartbeat.md must "
                "subtract $0.50 LEVEL_STOP_BUFFER → $0.80 effective below. Per L51/L55 lesson: "
                "premium_stop_pct=-0.99 (disabled). Chart stop is the only exit gate."
            ),
            "promotion_gate": (
                "OP-21: historical gate bypassed (no key-levels archive). "
                "Live gate: N>=20 observations WR>=50% → real-fills → 3 live J wins."
            ),
        },
    )
