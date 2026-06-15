"""v34_ceiling_floor_watcher_gate — CLOSE_CEILING_DISTRIBUTION_FADE + FLOOR_HOLD_DISTRIBUTION_BOUNCE
regression gate for watcher-level logic (time gate, streak gate, breakout/breakdown gate,
key-levels cache gate).

Background:
  2026-05-20: Two new watchers shipped as part of the L59 close-ceiling pattern (CLAUDE.md):
    - backtest/lib/watchers/close_ceiling_fade_watcher.py  (direction="short", bear trap)
    - backtest/lib/watchers/floor_hold_bounce_watcher.py   (direction="long", bull trap)

  v33_close_ceiling_detection.py (PASS 2026-05-20) tests the PRIMITIVE functions:
    detect_close_ceiling() and detect_floor_hold() from crypto.lib.chart_patterns.

  v34 (this file) tests the WATCHER FUNCTIONS which add:
    - Key-levels.json loading and caching (only ★★+ named levels qualify)
    - Time gate: 09:45-14:30 ET (skip gap-open 15 min + avoid late-session theta drain)
    - Cooldown gate: 45 min between signals
    - Breakout gate: bar.close > resistance + 0.05 (CCF) / bar.close < support - 0.05 (FHB)
    - Star filter: only roles in _RESISTANCE_ROLES / _SUPPORT_ROLES qualify

  Gap closed: v33 tested the math primitives; v34 is the watcher-level gate regression gate.
  Pattern: same as v28 (NLWB gate), v29 (DB_BASE_QUIET gate), v30 (DB_MORNING gate),
  v31 (MOMENTUM_ACCEL gate), v32 (DB_BASE_QUIET_ALL_DAY gate).

Offline tests (12 total):

  close_ceiling_fade_watcher (T1-T6):
    T1  streak=3 distribution bars + fake breakout at 10:00 ET
          → WatcherSignal(direction="short", confidence="low")
    T2  time gate: 09:30 ET (before 09:45 start) → None
    T3  time gate: 15:00 ET (after 14:30 end) → None
    T4  streak=2 only (bar 4 resets run, bars 5-6 give max_run=2 < 3) → None
    T5  breakout insufficient: close=750.04 <= level+0.05=750.05 → None
    T6  no ★★+ resistance levels in cache (empty list) → None

  floor_hold_bounce_watcher (T7-T12):
    T7  streak=3 accumulation bars + fake breakdown at 10:00 ET
          → WatcherSignal(direction="long", confidence="low")
    T8  time gate: 09:30 ET (before 09:45 start) → None
    T9  time gate: 15:00 ET (after 14:30 end) → None
    T10 streak=2 only (bar 4 resets run, bars 5-6 give max_run=2 < 3) → None
    T11 breakdown insufficient: close=734.97 >= level-0.05=734.95 → None
    T12 no ★★+ support levels in cache (empty list) → None

Live tests (audit mode):
  Scan watcher-observations.jsonl for any observations where streak_bars < N_MIN_STREAK (3).
  Such rows indicate a gate bypass — the watcher fired without the required distribution streak.
  pass=True always (audit mode — informational only).

Evidence basis:
  L59 (CLAUDE.md 2026-05-20 evening): 6-bar distribution at SPY PM ceiling 740.49 →
  14:40 fake breakout → 14:45 reversal (vol=45,411). N_MIN_STREAK=3 is the minimum
  defensible evidence window (J verbatim: "notice how NONE of the 5m bars closed above
  the key level — that is an indicator we should have noticed to indicate bearish sentiment").
  The 3-bar minimum encodes "persistent distribution / accumulation" as a named constant.

Modes:
  offline  12 deterministic gate tests. All 12 must PASS.
  live     Audit scan for gate-bypass observations. pass=True always (audit mode).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixture bar data (inline — deterministic, no external dependencies)
# ---------------------------------------------------------------------------

# All bars: (open, high, low, close, volume)
#
# close_ceiling_fade — resistance level 750.00
# LEVEL_TOLERANCE=0.05 → distribution bar needs: high >= 749.95, close < 750.00
# BREAKOUT_MIN_CENTS=0.05 → signal bar needs:     close > 750.05
#
# prior_bars layout (8 rows): rows 0-7 passed to BarContext.
#   ctx.bar                       = prior_bars.iloc[-1]  (signal bar, row 7)
#   scan_df = prior_bars.tail(13).iloc[:-1]  = rows 0-6  (7 bars scanned for streak)
#
# Streak verification over scan rows 0-6:
#   Row 0: h=748.50 < 749.95  → NO, run=0
#   Row 1: h=748.80 < 749.95  → NO, run=0
#   Row 2: h=749.20 < 749.95  → NO, run=0
#   Row 3: h=749.50 < 749.95  → NO, run=0
#   Row 4: h=749.98 >= 749.95, c=749.70 < 750.00 → YES, run=1
#   Row 5: h=749.97 >= 749.95, c=749.80 < 750.00 → YES, run=2
#   Row 6: h=749.99 >= 749.95, c=749.85 < 750.00 → YES, run=3  ← max_run=3
#   detected: True (max_run=3 >= N_MIN_STREAK=3)
#   signal bar row 7: close=750.12 > 750.00+0.05=750.05          ← breakout gate passes
_CCF_SIGNAL_BARS = [
    (748.00, 748.50, 747.50, 748.20, 50_000),   # 0: background
    (748.20, 748.80, 747.80, 748.50, 50_000),   # 1: background
    (748.50, 749.20, 748.20, 748.90, 50_000),   # 2: background
    (748.90, 749.50, 748.60, 749.20, 50_000),   # 3: background (h=749.50 < 749.95, no streak)
    (749.20, 749.98, 749.10, 749.70, 80_000),   # 4: distribution bar 1
    (749.70, 749.97, 749.60, 749.80, 85_000),   # 5: distribution bar 2
    (749.80, 749.99, 749.70, 749.85, 90_000),   # 6: distribution bar 3
    (749.85, 750.20, 749.80, 750.12, 120_000),  # 7: SIGNAL BAR — fake breakout (c=750.12 > 750.05)
]

# T4 — streak=2 only: row 4 changed to h=749.30 < 749.95, breaking streak before bars 5-6.
# max_run stays at 2 (rows 5-6 only) < N_MIN_STREAK → None
_CCF_STREAK2_BARS = [
    (748.00, 748.50, 747.50, 748.20, 50_000),   # 0: background
    (748.20, 748.80, 747.80, 748.50, 50_000),   # 1: background
    (748.50, 749.20, 748.20, 748.90, 50_000),   # 2: background
    (748.90, 749.50, 748.60, 749.20, 50_000),   # 3: background
    (749.20, 749.30, 749.10, 749.15, 50_000),   # 4: NON-qualifying (h=749.30 < 749.95) → run=0
    (749.70, 749.97, 749.60, 749.80, 85_000),   # 5: distribution → run=1
    (749.80, 749.99, 749.70, 749.85, 90_000),   # 6: distribution → run=2 (max_run=2 < 3 → None)
    (749.85, 750.20, 749.80, 750.12, 120_000),  # 7: signal bar (would fire if streak >= 3)
]

# T5 — breakout insufficient: close=750.04 <= level+BREAKOUT_MIN_CENTS (750.05)
# Gate expression: `if bar_close <= level + BREAKOUT_MIN_CENTS: continue`
# 750.04 <= 750.05 → True → skips level → None
_CCF_NO_BREAKOUT_BARS = [
    (748.00, 748.50, 747.50, 748.20, 50_000),   # 0: background
    (748.20, 748.80, 747.80, 748.50, 50_000),   # 1: background
    (748.50, 749.20, 748.20, 748.90, 50_000),   # 2: background
    (748.90, 749.50, 748.60, 749.20, 50_000),   # 3: background
    (749.20, 749.98, 749.10, 749.70, 80_000),   # 4: distribution bar 1
    (749.70, 749.97, 749.60, 749.80, 85_000),   # 5: distribution bar 2
    (749.80, 749.99, 749.70, 749.85, 90_000),   # 6: distribution bar 3
    (749.85, 750.10, 749.80, 750.04, 120_000),  # 7: close=750.04 (not > 750.05) → None
]


# floor_hold_bounce — support level 735.00
# LEVEL_TOLERANCE=0.05 → accumulation bar needs: low <= 735.05, close > 735.00
# BREAKDOWN_MIN_CENTS=0.05 → signal bar needs:   close < 734.95
#
# Streak verification over scan rows 0-6:
#   Row 0: l=736.80 > 735.05  → NO, run=0
#   Row 1: l=736.90 > 735.05  → NO, run=0
#   Row 2: l=736.70 > 735.05  → NO, run=0
#   Row 3: l=735.80 > 735.05  → NO, run=0
#   Row 4: l=735.02 <= 735.05, c=735.40 > 735.00 → YES, run=1
#   Row 5: l=734.98 <= 735.05, c=735.60 > 735.00 → YES, run=2
#   Row 6: l=735.00 <= 735.05, c=735.30 > 735.00 → YES, run=3  ← max_run=3
#   detected: True (max_run=3 >= N_MIN_STREAK=3)
#   signal bar row 7: close=734.88 < 735.00-0.05=734.95          ← breakdown gate passes
_FHB_SIGNAL_BARS = [
    (737.00, 737.50, 736.80, 737.10, 50_000),   # 0: background
    (737.10, 737.30, 736.90, 737.00, 50_000),   # 1: background
    (737.00, 737.20, 736.70, 736.90, 50_000),   # 2: background
    (736.90, 737.00, 735.80, 736.50, 50_000),   # 3: background (l=735.80 > 735.05, no streak)
    (736.50, 736.80, 735.02, 735.40, 80_000),   # 4: accumulation bar 1
    (735.40, 736.20, 734.98, 735.60, 85_000),   # 5: accumulation bar 2
    (735.60, 736.30, 735.00, 735.30, 90_000),   # 6: accumulation bar 3
    (735.30, 735.50, 734.70, 734.88, 120_000),  # 7: SIGNAL BAR — fake breakdown (c=734.88 < 734.95)
]

# T10 — streak=2 only: row 4 changed to l=736.00 > 735.05, breaking streak before bars 5-6.
_FHB_STREAK2_BARS = [
    (737.00, 737.50, 736.80, 737.10, 50_000),   # 0: background
    (737.10, 737.30, 736.90, 737.00, 50_000),   # 1: background
    (737.00, 737.20, 736.70, 736.90, 50_000),   # 2: background
    (736.90, 737.00, 735.80, 736.50, 50_000),   # 3: background
    (736.50, 736.80, 736.00, 736.20, 50_000),   # 4: NON-qualifying (l=736.00 > 735.05) → run=0
    (735.40, 736.20, 734.98, 735.60, 85_000),   # 5: accumulation → run=1
    (735.60, 736.30, 735.00, 735.30, 90_000),   # 6: accumulation → run=2 (max_run=2 < 3 → None)
    (735.30, 735.50, 734.70, 734.88, 120_000),  # 7: signal bar (would fire if streak >= 3)
]

# T11 — breakdown insufficient: close=734.97 >= level-BREAKDOWN_MIN_CENTS (734.95)
# Gate expression: `if bar_close >= level - BREAKDOWN_MIN_CENTS: continue`
# 734.97 >= 734.95 → True → skips level → None
_FHB_NO_BREAKDOWN_BARS = [
    (737.00, 737.50, 736.80, 737.10, 50_000),   # 0: background
    (737.10, 737.30, 736.90, 737.00, 50_000),   # 1: background
    (737.00, 737.20, 736.70, 736.90, 50_000),   # 2: background
    (736.90, 737.00, 735.80, 736.50, 50_000),   # 3: background
    (736.50, 736.80, 735.02, 735.40, 80_000),   # 4: accumulation bar 1
    (735.40, 736.20, 734.98, 735.60, 85_000),   # 5: accumulation bar 2
    (735.60, 736.30, 735.00, 735.30, 90_000),   # 6: accumulation bar 3
    (735.30, 735.50, 734.80, 734.97, 120_000),  # 7: close=734.97 (not < 734.95) → None
]


# ---------------------------------------------------------------------------
# BarContext builder
# ---------------------------------------------------------------------------

def _make_prior_bars(bars_data: list[tuple]):
    """Build prior_bars DataFrame from (open, high, low, close, volume) tuples."""
    import pandas as pd
    return pd.DataFrame(bars_data, columns=["open", "high", "low", "close", "volume"])


def _make_ctx(
    bars_data: list[tuple],
    *,
    timestamp_et: Optional[dt.datetime] = None,
    vix_now: float = 17.0,
):
    """Build a minimal BarContext from bar fixture data.

    The last row of bars_data is treated as the current bar (ctx.bar).
    All rows including the last are passed as ctx.prior_bars — same contract
    as watcher_live.py and watcher_replay.py: prior_bars includes current bar
    at index [-1], and watchers internally do .tail(N+1).iloc[:-1] to strip it.
    """
    from backtest.lib.filters import BarContext

    if timestamp_et is None:
        timestamp_et = dt.datetime(2026, 5, 20, 10, 0, 0)

    prior_bars = _make_prior_bars(bars_data)
    trigger_bar = prior_bars.iloc[-1]

    return BarContext(
        bar_idx=len(prior_bars) - 1,
        timestamp_et=timestamp_et,
        bar=trigger_bar,
        prior_bars=prior_bars,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix_now,
        vix_prior=vix_now,
        vol_baseline_20=50_000.0,
        range_baseline_20=0.40,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

_CCF_LEVEL = 750.0
_FHB_LEVEL = 735.0
_TEST_DATE = "2026-05-20"
_RTH_TIME = dt.datetime(2026, 5, 20, 10, 0, 0)   # 10:00 ET — inside 09:45-14:30 window
_BEFORE_GATE = dt.datetime(2026, 5, 20, 9, 30, 0)  # 09:30 ET — before 09:45 start
_AFTER_GATE = dt.datetime(2026, 5, 20, 15, 0, 0)   # 15:00 ET — after 14:30 end


def run_offline() -> dict:
    """Run 12 deterministic gate tests for CCF + FHB watchers.

    Tests T1-T6 cover close_ceiling_fade_watcher.
    Tests T7-T12 cover floor_hold_bounce_watcher.
    All 12 must PASS for overall all_pass=True.

    Injection pattern: directly set watcher module globals _cached_levels,
    _cached_levels_date (bypasses file I/O — no key-levels.json dependency)
    and reset _last_signal_time before each test (prevents cooldown bleed).
    """
    import backtest.lib.watchers.close_ceiling_fade_watcher as _ccf_mod
    import backtest.lib.watchers.floor_hold_bounce_watcher as _fhb_mod
    from backtest.lib.watchers.close_ceiling_fade_watcher import (
        detect_close_ceiling_fade_setup,
        N_MIN_STREAK as CCF_N_MIN_STREAK,
        ENTRY_TIME_START as CCF_START,
        ENTRY_TIME_END as CCF_END,
        BREAKOUT_MIN_CENTS as CCF_BREAKOUT_MIN,
    )
    from backtest.lib.watchers.floor_hold_bounce_watcher import (
        detect_floor_hold_bounce_setup,
        N_MIN_STREAK as FHB_N_MIN_STREAK,
        ENTRY_TIME_START as FHB_START,
        ENTRY_TIME_END as FHB_END,
        BREAKDOWN_MIN_CENTS as FHB_BREAKDOWN_MIN,
    )

    results: list[dict] = []

    # =========================================================================
    # T1: close_ceiling_fade fires — streak=3 + fake breakout at 10:00 ET
    # =========================================================================
    _ccf_mod._last_signal_time = None
    _ccf_mod._cached_levels = [_CCF_LEVEL]
    _ccf_mod._cached_levels_date = _TEST_DATE

    ctx_t1 = _make_ctx(_CCF_SIGNAL_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t1 = detect_close_ceiling_fade_setup(ctx_t1)

    if sig_t1 is not None:
        ok_t1 = (
            sig_t1.direction == "short"
            and sig_t1.setup_name == "CLOSE_CEILING_DISTRIBUTION_FADE"
            and (sig_t1.metadata or {}).get("streak_bars", 0) >= CCF_N_MIN_STREAK
            and sig_t1.watcher_name == "close_ceiling_fade"
        )
        note_t1 = (
            f"direction={sig_t1.direction} setup={sig_t1.setup_name} "
            f"streak_bars={sig_t1.metadata.get('streak_bars','?')} "
            f"confidence={sig_t1.confidence} entry={sig_t1.entry_price:.2f}"
        )
    else:
        ok_t1 = False
        note_t1 = "watcher returned None — pattern did not fire (expected WatcherSignal)"

    results.append({"name": "T1_ccf_fires_streak3", "pass": ok_t1, "note": note_t1})

    # =========================================================================
    # T2: close_ceiling_fade — time gate blocks entry at 09:30 ET (before 09:45)
    # =========================================================================
    _ccf_mod._last_signal_time = None
    _ccf_mod._cached_levels = [_CCF_LEVEL]
    _ccf_mod._cached_levels_date = _TEST_DATE

    ctx_t2 = _make_ctx(_CCF_SIGNAL_BARS, timestamp_et=_BEFORE_GATE, vix_now=17.0)
    sig_t2 = detect_close_ceiling_fade_setup(ctx_t2)

    ok_t2 = sig_t2 is None
    results.append({
        "name": "T2_ccf_time_gate_before_start",
        "pass": ok_t2,
        "note": (
            f"timestamp=09:30 ET < ENTRY_TIME_START={CCF_START} "
            f"watcher_result={'None (PASS)' if sig_t2 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T3: close_ceiling_fade — time gate blocks entry at 15:00 ET (after 14:30)
    # =========================================================================
    _ccf_mod._last_signal_time = None
    _ccf_mod._cached_levels = [_CCF_LEVEL]
    _ccf_mod._cached_levels_date = _TEST_DATE

    ctx_t3 = _make_ctx(_CCF_SIGNAL_BARS, timestamp_et=_AFTER_GATE, vix_now=17.0)
    sig_t3 = detect_close_ceiling_fade_setup(ctx_t3)

    ok_t3 = sig_t3 is None
    results.append({
        "name": "T3_ccf_time_gate_after_end",
        "pass": ok_t3,
        "note": (
            f"timestamp=15:00 ET > ENTRY_TIME_END={CCF_END} "
            f"watcher_result={'None (PASS)' if sig_t3 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T4: close_ceiling_fade — streak=2 insufficient (N_MIN_STREAK=3 not met)
    # Row 4 changed to h=749.30 < 749.95 (non-qualifying), resets run;
    # rows 5-6 give max_run=2 which is < N_MIN_STREAK(3).
    # =========================================================================
    _ccf_mod._last_signal_time = None
    _ccf_mod._cached_levels = [_CCF_LEVEL]
    _ccf_mod._cached_levels_date = _TEST_DATE

    ctx_t4 = _make_ctx(_CCF_STREAK2_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t4 = detect_close_ceiling_fade_setup(ctx_t4)

    ok_t4 = sig_t4 is None
    results.append({
        "name": "T4_ccf_streak2_insufficient",
        "pass": ok_t4,
        "note": (
            f"streak=2 (bar4 resets run, bars5-6 only) < N_MIN_STREAK={CCF_N_MIN_STREAK} "
            f"watcher_result={'None (PASS)' if sig_t4 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T5: close_ceiling_fade — breakout insufficient (close=750.04 not > 750.05)
    # Gate: `if bar_close <= level + BREAKOUT_MIN_CENTS: continue`
    # 750.04 <= 750.05 → True → skips all levels → signal_level remains None → return None
    # =========================================================================
    _ccf_mod._last_signal_time = None
    _ccf_mod._cached_levels = [_CCF_LEVEL]
    _ccf_mod._cached_levels_date = _TEST_DATE

    ctx_t5 = _make_ctx(_CCF_NO_BREAKOUT_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t5 = detect_close_ceiling_fade_setup(ctx_t5)

    ok_t5 = sig_t5 is None
    results.append({
        "name": "T5_ccf_breakout_insufficient",
        "pass": ok_t5,
        "note": (
            f"close=750.04 <= level({_CCF_LEVEL})+BREAKOUT_MIN_CENTS({CCF_BREAKOUT_MIN})={_CCF_LEVEL+CCF_BREAKOUT_MIN} "
            f"gate_expr='bar_close <= level+min_cents' is True → skip → None "
            f"watcher_result={'None (PASS)' if sig_t5 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T6: close_ceiling_fade — no ★★+ resistance levels (empty cache)
    # Gate: `if not resistance_levels: return None`
    # =========================================================================
    _ccf_mod._last_signal_time = None
    _ccf_mod._cached_levels = []          # ← empty → no qualifying levels
    _ccf_mod._cached_levels_date = _TEST_DATE

    ctx_t6 = _make_ctx(_CCF_SIGNAL_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t6 = detect_close_ceiling_fade_setup(ctx_t6)

    ok_t6 = sig_t6 is None
    results.append({
        "name": "T6_ccf_no_resistance_levels",
        "pass": ok_t6,
        "note": (
            "resistance_levels=[] (empty cache — no ★★+ levels loaded) "
            f"watcher_result={'None (PASS)' if sig_t6 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T7: floor_hold_bounce fires — streak=3 + fake breakdown at 10:00 ET
    # =========================================================================
    _fhb_mod._last_signal_time = None
    _fhb_mod._cached_levels = [_FHB_LEVEL]
    _fhb_mod._cached_levels_date = _TEST_DATE

    ctx_t7 = _make_ctx(_FHB_SIGNAL_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t7 = detect_floor_hold_bounce_setup(ctx_t7)

    if sig_t7 is not None:
        ok_t7 = (
            sig_t7.direction == "long"
            and sig_t7.setup_name == "FLOOR_HOLD_DISTRIBUTION_BOUNCE"
            and (sig_t7.metadata or {}).get("streak_bars", 0) >= FHB_N_MIN_STREAK
            and sig_t7.watcher_name == "floor_hold_bounce"
        )
        note_t7 = (
            f"direction={sig_t7.direction} setup={sig_t7.setup_name} "
            f"streak_bars={sig_t7.metadata.get('streak_bars','?')} "
            f"confidence={sig_t7.confidence} entry={sig_t7.entry_price:.2f}"
        )
    else:
        ok_t7 = False
        note_t7 = "watcher returned None — pattern did not fire (expected WatcherSignal)"

    results.append({"name": "T7_fhb_fires_streak3", "pass": ok_t7, "note": note_t7})

    # =========================================================================
    # T8: floor_hold_bounce — time gate blocks entry at 09:30 ET (before 09:45)
    # =========================================================================
    _fhb_mod._last_signal_time = None
    _fhb_mod._cached_levels = [_FHB_LEVEL]
    _fhb_mod._cached_levels_date = _TEST_DATE

    ctx_t8 = _make_ctx(_FHB_SIGNAL_BARS, timestamp_et=_BEFORE_GATE, vix_now=17.0)
    sig_t8 = detect_floor_hold_bounce_setup(ctx_t8)

    ok_t8 = sig_t8 is None
    results.append({
        "name": "T8_fhb_time_gate_before_start",
        "pass": ok_t8,
        "note": (
            f"timestamp=09:30 ET < ENTRY_TIME_START={FHB_START} "
            f"watcher_result={'None (PASS)' if sig_t8 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T9: floor_hold_bounce — time gate blocks entry at 15:00 ET (after 14:30)
    # =========================================================================
    _fhb_mod._last_signal_time = None
    _fhb_mod._cached_levels = [_FHB_LEVEL]
    _fhb_mod._cached_levels_date = _TEST_DATE

    ctx_t9 = _make_ctx(_FHB_SIGNAL_BARS, timestamp_et=_AFTER_GATE, vix_now=17.0)
    sig_t9 = detect_floor_hold_bounce_setup(ctx_t9)

    ok_t9 = sig_t9 is None
    results.append({
        "name": "T9_fhb_time_gate_after_end",
        "pass": ok_t9,
        "note": (
            f"timestamp=15:00 ET > ENTRY_TIME_END={FHB_END} "
            f"watcher_result={'None (PASS)' if sig_t9 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T10: floor_hold_bounce — streak=2 insufficient (N_MIN_STREAK=3 not met)
    # Row 4 changed to l=736.00 > 735.05 (non-qualifying), resets run;
    # rows 5-6 give max_run=2 which is < N_MIN_STREAK(3).
    # =========================================================================
    _fhb_mod._last_signal_time = None
    _fhb_mod._cached_levels = [_FHB_LEVEL]
    _fhb_mod._cached_levels_date = _TEST_DATE

    ctx_t10 = _make_ctx(_FHB_STREAK2_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t10 = detect_floor_hold_bounce_setup(ctx_t10)

    ok_t10 = sig_t10 is None
    results.append({
        "name": "T10_fhb_streak2_insufficient",
        "pass": ok_t10,
        "note": (
            f"streak=2 (bar4 resets run, bars5-6 only) < N_MIN_STREAK={FHB_N_MIN_STREAK} "
            f"watcher_result={'None (PASS)' if sig_t10 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T11: floor_hold_bounce — breakdown insufficient (close=734.97 not < 734.95)
    # Gate: `if bar_close >= level - BREAKDOWN_MIN_CENTS: continue`
    # 734.97 >= 734.95 → True → skips all levels → signal_level remains None → return None
    # =========================================================================
    _fhb_mod._last_signal_time = None
    _fhb_mod._cached_levels = [_FHB_LEVEL]
    _fhb_mod._cached_levels_date = _TEST_DATE

    ctx_t11 = _make_ctx(_FHB_NO_BREAKDOWN_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t11 = detect_floor_hold_bounce_setup(ctx_t11)

    ok_t11 = sig_t11 is None
    results.append({
        "name": "T11_fhb_breakdown_insufficient",
        "pass": ok_t11,
        "note": (
            f"close=734.97 >= level({_FHB_LEVEL})-BREAKDOWN_MIN_CENTS({FHB_BREAKDOWN_MIN})={_FHB_LEVEL-FHB_BREAKDOWN_MIN} "
            f"gate_expr='bar_close >= level-min_cents' is True → skip → None "
            f"watcher_result={'None (PASS)' if sig_t11 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # T12: floor_hold_bounce — no ★★+ support levels (empty cache)
    # Gate: `if not support_levels: return None`
    # =========================================================================
    _fhb_mod._last_signal_time = None
    _fhb_mod._cached_levels = []          # ← empty → no qualifying levels
    _fhb_mod._cached_levels_date = _TEST_DATE

    ctx_t12 = _make_ctx(_FHB_SIGNAL_BARS, timestamp_et=_RTH_TIME, vix_now=17.0)
    sig_t12 = detect_floor_hold_bounce_setup(ctx_t12)

    ok_t12 = sig_t12 is None
    results.append({
        "name": "T12_fhb_no_support_levels",
        "pass": ok_t12,
        "note": (
            "support_levels=[] (empty cache — no ★★+ levels loaded) "
            f"watcher_result={'None (PASS)' if sig_t12 is None else 'Signal (FAIL)'}"
        ),
    })

    # =========================================================================
    # Aggregate
    # =========================================================================
    all_pass = all(r["pass"] for r in results)
    return {
        "mode": "offline",
        "evidence_basis": (
            "L59 (CLAUDE.md 2026-05-20): 6-bar distribution at SPY PM ceiling 740.49 "
            "→ 14:40 fake breakout → 14:45 reversal (vol=45,411). "
            "N_MIN_STREAK=3 is the minimum defensible evidence window. "
            "CCF fixture level=750.00, FHB fixture level=735.00. "
            "Both watchers verified for time gate, streak gate, breakout/breakdown gate, level cache gate."
        ),
        "constants_verified": {
            "CCF_N_MIN_STREAK": CCF_N_MIN_STREAK,
            "CCF_ENTRY_TIME_START": str(CCF_START),
            "CCF_ENTRY_TIME_END": str(CCF_END),
            "CCF_BREAKOUT_MIN_CENTS": CCF_BREAKOUT_MIN,
            "FHB_N_MIN_STREAK": FHB_N_MIN_STREAK,
            "FHB_ENTRY_TIME_START": str(FHB_START),
            "FHB_ENTRY_TIME_END": str(FHB_END),
            "FHB_BREAKDOWN_MIN_CENTS": FHB_BREAKDOWN_MIN,
        },
        "tests": results,
        "passed": sum(1 for r in results if r["pass"]),
        "total": len(results),
        "all_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Scan watcher-observations.jsonl for gate-bypass observations.

    For close_ceiling_fade: any observation where metadata.streak_bars < 3
    indicates the N_MIN_STREAK=3 gate was bypassed (watcher fired on insufficient
    distribution evidence).

    For floor_hold_bounce: same check — streak_bars < 3 is a gate bypass.

    Audit mode: pass=True always (informational — RED verdict surfaces the bypass).
    If no CCF/FHB observations yet (watchers are new as of 2026-05-20), PASS with note.
    """
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {
            "mode": "live",
            "source": str(obs_path),
            "skipped": True,
            "reason": "watcher-observations.jsonl not found",
            "pass": True,
        }

    target_setups = {"CLOSE_CEILING_DISTRIBUTION_FADE", "FLOOR_HOLD_DISTRIBUTION_BOUNCE"}
    ccf_obs: list[dict] = []
    fhb_obs: list[dict] = []
    streak_bypasses: list[dict] = []
    lines_read = 0

    try:
        with open(obs_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obs = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lines_read += 1
                setup = obs.get("setup_name", obs.get("watcher_name", ""))
                if setup not in target_setups:
                    continue

                streak_bars = (obs.get("metadata") or {}).get("streak_bars", None)

                if setup == "CLOSE_CEILING_DISTRIBUTION_FADE":
                    ccf_obs.append(obs)
                    if streak_bars is not None and streak_bars < 3:
                        streak_bypasses.append({
                            "setup": setup,
                            "date": obs.get("date", "?"),
                            "timestamp": obs.get("bar_timestamp_et", obs.get("timestamp_et", "?")),
                            "streak_bars": streak_bars,
                            "issue": f"streak_bars={streak_bars} < N_MIN_STREAK=3 (gate bypass)",
                        })
                elif setup == "FLOOR_HOLD_DISTRIBUTION_BOUNCE":
                    fhb_obs.append(obs)
                    if streak_bars is not None and streak_bars < 3:
                        streak_bypasses.append({
                            "setup": setup,
                            "date": obs.get("date", "?"),
                            "timestamp": obs.get("bar_timestamp_et", obs.get("timestamp_et", "?")),
                            "streak_bars": streak_bars,
                            "issue": f"streak_bars={streak_bars} < N_MIN_STREAK=3 (gate bypass)",
                        })
    except Exception as exc:
        return {
            "mode": "live",
            "skipped": True,
            "reason": f"read error: {exc}",
            "pass": True,
        }

    total_obs = len(ccf_obs) + len(fhb_obs)
    if total_obs == 0:
        return {
            "mode": "live",
            "source": str(obs_path),
            "total_lines_scanned": lines_read,
            "ccf_observations": 0,
            "fhb_observations": 0,
            "streak_gate_bypasses": 0,
            "verdict": "GREEN",
            "note": (
                "No CLOSE_CEILING_DISTRIBUTION_FADE or FLOOR_HOLD_DISTRIBUTION_BOUNCE "
                "observations yet — watchers are new as of 2026-05-20. "
                "PASS: absence of bypass evidence."
            ),
            "pass": True,
        }

    verdict = "GREEN" if not streak_bypasses else "RED"
    return {
        "mode": "live",
        "source": str(obs_path),
        "total_lines_scanned": lines_read,
        "ccf_observations": len(ccf_obs),
        "fhb_observations": len(fhb_obs),
        "streak_gate_bypasses": len(streak_bypasses),
        "bypass_details": streak_bypasses,
        "verdict": verdict,
        "note": (
            "Scanned all CLOSE_CEILING_DISTRIBUTION_FADE + FLOOR_HOLD_DISTRIBUTION_BOUNCE "
            "observations. Any row with metadata.streak_bars < 3 indicates the N_MIN_STREAK "
            "gate was bypassed — the watcher fired without the required distribution streak. "
            "N_MIN_STREAK=3 encodes the minimum evidence window per L59 J identification."
        ),
        "pass": True,  # audit mode — RED is informational; no gate bypass expected in practice
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="v34 CCF+FHB watcher gate regression tests"
    )
    parser.add_argument("--mode", choices=["offline", "live", "both"], default="offline")
    args = parser.parse_args(argv)

    exit_code = 0

    if args.mode in ("offline", "both"):
        result = run_offline()
        print(json.dumps(result, indent=2))
        if not result.get("all_pass", False):
            exit_code = 1

    if args.mode in ("live", "both"):
        result = run_live()
        print(json.dumps(result, indent=2))
        # live is audit-mode, never fails overall

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
