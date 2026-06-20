"""NAMED_LEVEL_WICK_BOUNCE (NLWB) watcher (WATCH-ONLY per OP-21).

Detects bullish wick rejections at named support levels — a 5m bar that wicks
BELOW the level but closes BACK ABOVE it, signalling a failed breakdown.

This is the exact setup missed on 2026-05-19 12:35 ET:
  - Pre-market low 734.56 = named support (in key-levels.json)
  - 12:35 bar: low 734.48 (wicked 8c below 734.56), close 735.05 (closed 49c above)
  - F11 (15m HTF BEAR) blocked the engine — structurally wrong for a first-strike
    level-bounce entry where the LEVEL HOLDING is the signal, not the trend.
  - SPY ran 735.05 → 738.10 in the next 90 minutes (+$3.05)

Setup definition (from chef scan 2026-05-20 named_level_bounce_scan.py):
  1. Bar LOW wicks >= WICK_BELOW_MIN_CENTS below a named support level in levels_active
  2. Bar CLOSE is ABOVE the level (bounce confirmed)
  3. Volume >= MIN_VOL_MULT × 20-bar average (confirms buying interest on the bounce)
  4. Ribbon stack is MIXED or BULL — NOT BEAR (don't fade confirmed bear trends)
  5. Time: 09:35 - 14:30 ET

Historical edge (from 16-month PDL proxy scan, N=157 signals):
  - PDL relaxed variant: 71.3% WR (60-min SPY +$0.50 proxy)
  - WR near session low: 72.2%
  - Zero fires on J's loser days (5/05, 5/06, 5/07) — structural incompatibility
    (loser days = confirmed bearish breaks, not bounces back above level)
  - Win days: 4/29 (×2 wins), 5/04 (×2 wins + 1 loss)

MUTUALLY EXCLUSIVE with LBFS:
  - LBFS fires when close is BELOW the level (confirmed break = bearish)
  - NLWB fires when close is ABOVE the level (bounce = bullish)
  - Cannot both fire on the same bar

Real-fills full-window (2026-05-20, PDL proxy, ribbon=MIXED/BULL, N=23 completed):
  WR=47.8% (11W/12L), Total P&L=-$1,294, avg=-$56/trade
  By VIX: <17: WR=62.5% N=8 | 17-20: WR=20.0% N=5 (DRAG) | 20-25: WR=60% N=5 | >=25: WR=40% N=5
  By ribbon: MIXED: WR=52.9% N=17 | BULL: WR=33.3% N=6
  Root cause: SPY-price scan proxy (SPY +$0.50 in 60 min = WIN) systematically
  overstates call-option P&L. A $0.50 SPY move produces less than TP1 (+30% premium)
  in low-to-medium VIX because ATM call premium is thin; theta drag erodes the premium
  during consolidation before the move extends. The chart stop (PDL-$0.80) correctly
  rejects false bounces but does NOT prevent slow theta bleed on genuine bounces that
  stall before reaching TP1. VIX 17-20 bucket (N=5, WR=20%) is the primary drag.
  Source: analysis/recommendations/nlwb_full_real_fills.json

  NOTE: The earlier "PASS" in this docstring (v1, 2/3 WR on T1/T2/T3) was based on
  only 3 cherry-picked anchor dates. Full 16-month scan corrects this to FAIL.
  WATCH_FRAGILE: OP-21 real-fills gate FAILED. No viable promotion path found.

VIX-regime rescue investigation (2026-05-20, nlwb_vix_regime_analysis.py):
  Tested 4 VIX-gated sub-scenarios against existing 23-trade real-fills dataset.
  VERDICT: NO_RESCUE. No VIX-gated variant achieves WR>=50% AND positive P&L.
    A. VIX<17 only:           N=8,  WR=62.5%, PnL=-$33  (WR PASS, PnL FAIL)
    B. VIX>=20 only:          N=10, WR=50.0%, PnL=-$921 (borderline WR, PnL FAIL)
    C. VIX<17 OR VIX>=25:    N=13, WR=53.8%, PnL=-$926 (WR PASS, PnL FAIL)
    D. All except VIX 17-20: N=18, WR=55.6%, PnL=-$954 (WR PASS, PnL FAIL)
  Root cause: R:R mismatch. Break-even WR = wins×reward > losses×risk.
    With TP1=+30% and chart-stop=PDL-$0.80:
      reward ≈ $45/trade (3 contracts, $0.50 ATM call, +30%)
      risk   ≈ $105/trade (3 contracts, $0.50 ATM call, -70% at chart stop)
    Break-even WR = 105/(105+45) = 70%. Scan proxy at 67.5% never clears the bar.
    VIX>=25 bucket is worst (-$893 on 5 trades): higher premium = larger absolute
    dollar loss when chart stop fires, while TP1 pct gain stays fixed at +30%.
  Source: analysis/recommendations/nlwb_vix_regime_analysis.json

OP-21 promotion gate:
  - Historical: PASS (PDL relaxed WR=71.3% N=157 > 50%, guard PASS on loser days) ✓
  - Walk-forward OOS: PASS — PDL relaxed STABLE, delta=-7.9pp, all months >=50% ✓
  - Real-fills: FAIL ❌ — full-window WR=47.8% N=23, P&L=-$1,294 (2026-05-20)
    VIX-regime rescue investigated 2026-05-20 — NO_RESCUE. Structural R:R issue.
  - Live: 0/3 ❌

Parameter sweep results (2026-05-20):
  TP1 sweep (TP1=+30% to +200%, nlwb_tp1_sweep.py):
    ALL 6 values NEGATIVE. WR degrades 43.5%→21.7% as TP1 rises.
    Root cause: 9/11 marginal wins exit via ribbon flip (TP1_THEN_RUNNER_RIBBON)
    BEFORE reaching higher targets. Raising TP1 converts them to chart-stop losses.
    rescue_found=False. Source: analysis/recommendations/nlwb_tp1_sweep.json

  Chart-stop sweep (pdl-0.80 to pdl-0.10, nlwb_chart_stop_sweep.py):
    ALL 5 values NEGATIVE. WR CONSTANT at 43.5% — winners exit via TP1/ribbon,
    NOT chart stop. Tightening stop reduces avg_loss ($215→$156 at pdl-0.10)
    but break-even WR at tightest stop = 57% vs actual 43.5%.
    rescue_found=False. Source: analysis/recommendations/nlwb_chart_stop_sweep.json

  ROOT CAUSE OF ALL FAILURES: PDL is the weakest named-level type (ephemeral,
  single-session). PDL scan proxy WR=71% → real-fills WR=44% (-27pp degradation).
  The production watcher fires on ★★★ levels (multi-session tested, cluster-defended).
  Both rescue paths CLOSED. See L58 in markdown/doctrine/LESSONS-LEARNED.md.

  PDL is a proxy — real-fills WR on PDL may understate production WR on ★★★
  levels by up to 20pp. DO NOT attempt further parameter sweeps on PDL-proxy
  backfill. If real-fills WR on PDL < 50%: accumulate live data first.

Promotion path:
  3+ live J observations on production ★★★ named levels → if 3/3 WIN →
  re-run real-fills on named-level-verified subset → re-evaluate.

Spec: strategy/candidates/2026-05-20-named-level-wick-bounce-bull.md
WATCH_FRAGILE: DO NOT promote. Both parameter rescue paths CLOSED (2026-05-20).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection thresholds (from chef scan calibration) ────────────────────────

# Minimum wick below the level: 8c is the floor (J's 5/19 bar had exactly 8c wick)
# Conservative: 10c. Relaxed: 8c (recommended — matches motivating case).
WICK_BELOW_MIN_CENTS: float = 8.0

# Minimum volume multiplier — confirms buying interest at the bounce bar
MIN_VOL_MULT: float = 1.2

# Ribbon gate: MIXED or BULL allowed; BEAR blocks (don't fade confirmed bear trend)
RIBBON_GATE_STACKS: tuple[str, ...] = ("MIXED", "BULL")

# Time window: standard entry window, avoids gap-open noise and EOD theta burn
ENTRY_TIME_START: dt.time = dt.time(9, 35)
ENTRY_TIME_END: dt.time = dt.time(14, 30)


# ── Default exit knobs (OP-21 watch-only conservative defaults) ──────────────

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99    # chart-stop ONLY — premium stop disabled
                                            # L51 analog for calls: brief post-bounce intrabar
                                            # premium dip fires -10% stop before SPY move develops.
                                            # v1 (-0.10) = 40% real-fills WR. v2 (-0.99) = 67%.
                                            # Chart stop via rejection_level=$0.50 below bounce level.
DEFAULT_TP1_PREMIUM_PCT: float = 0.30      # +30% premium fallback TP1
DEFAULT_RUNNER_TARGET_PCT: float = 1.5     # conservative runner per OP-21 watch-only defaults

# SPY-price stop/target levels (used for observation grading in runner.py)
_CHART_STOP_BELOW_LEVEL: float = 0.30   # stop = bounce_level - $0.30 (false bounce guard)
_TP1_SPY_MOVE: float = 0.80             # TP1 ≈ entry + $0.80 (60-min median SPY move)
_RUNNER_SPY_MOVE: float = 2.50          # runner ≈ entry + $2.50 (deep level target)


def detect_nlwb_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect NAMED_LEVEL_WICK_BOUNCE setup on the current bar.

    Returns WatcherSignal with direction="long" if all gates pass.
    Returns None if any gate fails.

    Confidence tiers:
      - "high":   VIX >= 17 (elevated regime — highest historical WR) AND near session low
      - "medium": VIX 15-17 or ribbon BULL (confirmed trend support)
      - "low":    VIX < 15 (low-vol regime — lower edge, observe only)
    """
    # ── Gate 1: Time window (09:35 - 14:30 ET) ──────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START:
        return None
    if bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: Ribbon MIXED or BULL (NOT BEAR) ──────────────────────────────
    if ctx.ribbon_now is None:
        return None
    ribbon_stack = ctx.ribbon_now.stack
    if ribbon_stack not in RIBBON_GATE_STACKS:
        return None

    # ── Gate 3: Volume >= 1.2× 20-bar average ────────────────────────────────
    if ctx.vol_baseline_20 <= 0:
        return None
    bar_vol = float(ctx.bar.get("volume", 0))
    vol_ratio = bar_vol / ctx.vol_baseline_20
    if vol_ratio < MIN_VOL_MULT:
        return None

    # ── Gate 4: Wick below a named support level, close above ────────────────
    # Find the BEST matching level: wick below by >= WICK_BELOW_MIN_CENTS AND close above
    bar_low = float(ctx.bar.get("low", 0))
    bar_close = float(ctx.bar.get("close", 0))

    bounce_level: Optional[float] = None
    best_wick_cents: float = 0.0

    for lvl in ctx.levels_active:
        # Wick check: bar_low must be below level by at least WICK_BELOW_MIN_CENTS
        # Round to 2dp to guard against floating-point subtraction drift
        # e.g. (734.56 - 734.48) * 100 = 7.9999... not 8.0 in IEEE 754
        wick_cents = round((lvl - bar_low) * 100.0, 2)
        if wick_cents < WICK_BELOW_MIN_CENTS:
            continue

        # Bounce check: close must be ABOVE the level
        if bar_close <= lvl:
            continue

        # Take the level with the deepest wick (most definitive test of support)
        if wick_cents > best_wick_cents:
            best_wick_cents = wick_cents
            bounce_level = lvl

    if bounce_level is None:
        return None

    # ── Confidence tier ──────────────────────────────────────────────────────
    vix_now = ctx.vix_now
    spread_cents = ctx.ribbon_now.spread_cents

    # Near-session-low check: is the bounce bar low close to the day's prior low?
    # (scan showed 72.2% WR near session low vs 71.3% overall)
    prior_lows = ctx.prior_bars["low"].values if len(ctx.prior_bars) > 0 else [bar_low]
    session_low_prior = float(min(prior_lows))
    near_session_low = bar_low <= session_low_prior + 0.10  # within $0.10 of session's prior low

    if vix_now >= 17.0 and near_session_low:
        confidence = "high"
        regime_note = f"VIX={vix_now:.2f} elevated+session-low (strongest historical sub-variant, WR=72.2%)"
    elif vix_now >= 17.0 or ribbon_stack == "BULL":
        confidence = "medium"
        if ribbon_stack == "BULL":
            regime_note = f"BULL ribbon confirmation (spread={spread_cents:.1f}c), VIX={vix_now:.2f}"
        else:
            regime_note = f"VIX={vix_now:.2f} elevated regime, not near session low (WR=71.3%)"
    else:
        confidence = "low"
        regime_note = f"VIX={vix_now:.2f} low-vol regime (lower historical WR, observe only)"

    # ── Stop, TP1, runner prices ─────────────────────────────────────────────
    # Chart stop: SPY falls $0.30 below the bounce level = false bounce
    stop_price = bounce_level - _CHART_STOP_BELOW_LEVEL
    tp1_price = bar_close + _TP1_SPY_MOVE
    runner_price = bar_close + _RUNNER_SPY_MOVE

    # ── OP-21 live gate status ───────────────────────────────────────────────
    historical_note = f"Historical: N=157 (PDL), WR=71.3%, guard PASS (0 fires on J loser days)"
    live_note = "Live gate: 0/3 — DO NOT enter production until 3+ live J confirmations"

    reason = (
        f"NLWB bull bounce at level {bounce_level:.2f}: "
        f"wick {best_wick_cents:.0f}c below (bar_low={bar_low:.2f}), "
        f"close {bar_close:.2f} (body={((bar_close - bounce_level) * 100):.0f}c above), "
        f"ribbon={ribbon_stack} spread={spread_cents:.1f}c, "
        f"vol={vol_ratio:.1f}x, {regime_note}. "
        f"{historical_note}. {live_note}."
    )

    return WatcherSignal(
        watcher_name="named_level_wick_bounce_watcher",
        setup_name="NAMED_LEVEL_WICK_BOUNCE",
        direction="long",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=reason,
        triggers_fired=["WICK_BELOW_NAMED_LEVEL", f"VOL_{vol_ratio:.1f}X", f"RIBBON_{ribbon_stack}"],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "historical_gate_pass": True,         # 4/5 wins on J days, 0 loser-day fires
            "live_gate_pass": False,               # 0/3 live confirmations
            "bounce_level": bounce_level,
            "wick_below_cents": round(best_wick_cents, 2),
            "bar_low": bar_low,
            "bar_close": bar_close,
            "close_above_level_cents": round((bar_close - bounce_level) * 100, 2),
            "ribbon_stack": ribbon_stack,
            "ribbon_spread_cents": spread_cents,
            "vol_ratio": round(vol_ratio, 2),
            "vix_now": vix_now,
            "near_session_low": near_session_low,
            "session_low_prior": round(session_low_prior, 2),
            "chart_stop_below_level": _CHART_STOP_BELOW_LEVEL,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "op21_historical_n": 157,
            "op21_historical_wr": 0.713,
            "op21_historical_loser_day_fires": 0,
            "op21_live_observations": 0,
            "op21_live_target": 3,
            "spec_file": "strategy/candidates/2026-05-20-named-level-wick-bounce-bull.md",
            "motivating_case": "2026-05-19 12:35 ET bounce off 734.56 (pre-market low)",
        },
    )
