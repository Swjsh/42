"""GAP_AND_GO watcher (H2b) — WATCH-ONLY per OP-21.

Opening-gap CONTINUATION after a confirming first bar. The data-discovered
survivor from the infinite-ammo first-principles edge search
(``analysis/recommendations/infinite-ammo-discovery.json``), re-validated under the
doctrinally-correct CHART-STOP-ONLY exit (L51/L55/C2):

  Real OPRA fills, 2025-01..2026-06, ATM, premium-stop disabled (chart-stop only):
    n=84, exp +$41.6/trade, WR 72.6%, drop-top5 +$15.62, DSR PASS, both dirs +,
    6/6 quarters positive, expanding-anchor WF_norm +1.87/+2.28/+1.12 (all OOS+).
  Scorecard: analysis/recommendations/gap-and-go-LIVE.json
  (The discovery scorecard's headline +$35.24/42.9% used premium_stop=-0.08, the
   v14 default — that EXIT choked the setup; chart-stop-only is the correct exit
   and lifts WR to 72.6% with WF_PASS. See gap-and-go-exit-wf.json.)

────────────────────────────────────────────────────────────────────────────────
PATTERN (mirror of autoresearch.infinite_ammo_discovery.detect_gap_and_go — the
detector that was validated; this is the LIVE port, byte-for-byte same logic):

  GAP = first_RTH_bar.open / prior_RTH_close - 1
  Gap UP  (gap >= +MIN_GAP) AND first RTH bar closes GREEN (close > open) -> CALLS.
  Gap DOWN(gap <= -MIN_GAP) AND first RTH bar closes RED   (close < open) -> PUTS.
  Skip |gap| > MAX_GAP (news-driven runaway) and |gap| < MIN_GAP (no real gap).
  The first-bar confirmation is what separates 'go' (continuation) from 'fade'.

  Entry  = first RTH bar CLOSE (fill is the NEXT bar open — sim/heartbeat handles).
  Stop   = the first bar's OPPOSITE extreme (gap-up/calls -> first bar LOW;
           gap-down/puts -> first bar HIGH). Chart stop; premium stop DISABLED.
  One signal per day, on/after the first RTH bar.

CAUSALITY (audited — _gap_and_go_causality_audit.py, 96/96 signals PASS):
  prior_close is the PRIOR trading day's last RTH close (look-ahead-safe); the gap
  and the green/red confirmation are read from the FIRST RTH bar only; nothing after
  the trigger bar is consulted; the fill is strictly the next bar open.

LIVE-ABILITY NOTE: gap-and-go is a once-per-day OPEN setup, not a per-tick rubric
match. The heartbeat should call this ONCE, right after the 09:30 ET bar closes
(first entry ~09:35 at the next bar open). The ctx wrapper below fires only when the
trigger bar IS the day's first RTH bar; it needs the prior-day RTH close, which the
heartbeat supplies via `prior_rth_close` (from today-bias.json) or which the wrapper
derives from a multi-day `prior_bars` frame when present.

OP-21 promotion gate:
  Offline (real-fills, this scorecard): PASS — exp+, WR 72.6%, DSR PASS, WF_PASS,
    both dirs +, drop-top5 robust, causal. (Proxy-strike caveat L58 still applies:
    ATM not always cached; nearest-cached strike used in the sim.)
  Live gate: accumulate observations -> 3 live J confirmations -> Rule 9 ratify
    BEFORE any live execution path is wired. This module ONLY observes + logs.

Sources:
  backtest/autoresearch/infinite_ammo_discovery.py#detect_gap_and_go (validated)
  backtest/lib/watchers/named_level_second_test_watcher.py (structural template)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters (IDENTICAL to detect_gap_and_go — no silent drift, C14) ─
MIN_GAP: float = 0.0025          # >= 0.25% overnight gap to count as a gap
MAX_GAP: float = 0.015           # skip > 1.5% gaps (news-driven runaway)

# RTH open (ET). The "first RTH bar" is the bar whose start == 09:30 ET.
RTH_OPEN: dt.time = dt.time(9, 30)

# ── Exit knobs (chart-stop ONLY — L51/L55/C2; matches CHART-STOP-PRIMARY live) ──
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # premium stop disabled; chart stop governs
DEFAULT_STRIKE_OFFSET: int = 0            # ATM (validated tier; ITM-1 also PASS)
DEFAULT_QTY: int = 3
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # v15 fallback when no chart level hit
DEFAULT_TP1_QTY_FRACTION: float = 0.50    # prod (L108)
DEFAULT_RUNNER_TARGET_PCT: float = 2.5    # prod (L109)

# SPY-price target geometry for the WatcherSignal (advisory; the real-fills exit
# stack on the sim/heartbeat side uses chart-stop + ribbon-flip + chandelier + time).
# These translate the premium-% intents into rough SPY moves for the obs schema.
_TP1_SPY_MOVE: float = 0.70
_RUNNER_SPY_MOVE: float = 2.50


@dataclass(frozen=True)
class GapAndGoResult:
    """Pure detector output (no ctx) — directly unit-testable, mirrors the discovery
    Signal plus the OHLC needed to build a WatcherSignal."""
    direction: str          # "long" (calls) | "short" (puts)
    side: str               # "C" | "P"
    gap_pct: float
    first_open: float
    first_high: float
    first_low: float
    first_close: float
    stop_level: float       # first bar opposite extreme (chart stop)


def detect_gap_and_go_core(
    prior_rth_close: float,
    first_open: float,
    first_high: float,
    first_low: float,
    first_close: float,
    *,
    min_gap: float = MIN_GAP,
    max_gap: float = MAX_GAP,
) -> Optional[GapAndGoResult]:
    """Pure gap-and-go decision from the prior RTH close + the first RTH bar OHLC.

    BYTE-FOR-BYTE the same condition as
    ``autoresearch.infinite_ammo_discovery.detect_gap_and_go``:
      gap = first_open/prior_close - 1; gap-up & green -> C; gap-down & red -> P;
      only when min_gap <= |gap| <= max_gap. Stop = first bar opposite extreme.

    Returns None when not a qualifying gap-and-go (no gap, gap too large, or the
    first bar did not confirm the gap direction).
    """
    if prior_rth_close is None or prior_rth_close <= 0 or first_open <= 0:
        return None
    gap = first_open / prior_rth_close - 1.0
    if not (min_gap <= abs(gap) <= max_gap):
        return None
    green = first_close > first_open
    red = first_close < first_open
    if gap > 0 and green:
        return GapAndGoResult(
            direction="long", side="C", gap_pct=gap,
            first_open=first_open, first_high=first_high, first_low=first_low,
            first_close=first_close, stop_level=first_low,
        )
    if gap < 0 and red:
        return GapAndGoResult(
            direction="short", side="P", gap_pct=gap,
            first_open=first_open, first_high=first_high, first_low=first_low,
            first_close=first_close, stop_level=first_high,
        )
    return None


def _prior_rth_close_from_prior_bars(ctx: BarContext) -> Optional[float]:
    """Best-effort prior-day RTH close from a multi-day ``prior_bars`` frame.

    The first RTH bar of TODAY is the trigger bar (ctx.bar). The prior trading day's
    close = the close of the last bar in ``prior_bars`` whose date < today AND whose
    time is within RTH (< 16:00). Returns None when prior_bars holds only today (the
    common single-day replay case) — the caller must then supply prior_rth_close
    explicitly. Look-ahead-safe: only bars strictly before today are read.
    """
    pb = ctx.prior_bars
    if pb is None or len(pb) < 2 or "timestamp_et" not in pb.columns:
        return None
    today = ctx.timestamp_et.date()
    ts = pd.to_datetime(pb["timestamp_et"])
    mask_prior = ts.dt.date < today
    if not bool(mask_prior.any()):
        return None
    prior = pb[mask_prior]
    # Restrict to RTH bars of the prior day(s); fall back to the last prior bar if no
    # explicit RTH bars (data without a clean session boundary).
    t = pd.to_datetime(prior["timestamp_et"]).dt.time
    rth = prior[(t >= RTH_OPEN) & (t < dt.time(16, 0))]
    src = rth if len(rth) else prior
    try:
        return float(src["close"].iloc[-1])
    except (KeyError, IndexError, ValueError):
        return None


def detect_gap_and_go_setup(
    ctx: BarContext,
    *,
    prior_rth_close: Optional[float] = None,
) -> Optional[WatcherSignal]:
    """Detect GAP_AND_GO on the FIRST RTH bar of the day (WATCH-ONLY).

    direction="long" (buy calls) for a gap-UP confirmed GREEN first bar.
    direction="short" (buy puts) for a gap-DOWN confirmed RED first bar.

    Fires ONLY when the trigger bar (ctx.bar) is the day's first RTH bar (start ==
    09:30 ET). ``prior_rth_close`` is the prior trading day's RTH close; if None, the
    wrapper tries to derive it from a multi-day ``ctx.prior_bars`` frame. Returns None
    on any gate miss (not the open bar, no prior close, no qualifying gap-and-go).
    """
    # ── Gate 1: must be the day's FIRST RTH bar (09:30 ET start) ────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time != RTH_OPEN:
        return None

    # ── Gate 2: prior RTH close (explicit, else derive from multi-day frame) ────
    pc = prior_rth_close if prior_rth_close is not None else _prior_rth_close_from_prior_bars(ctx)
    if pc is None or pc <= 0:
        return None

    # ── Current (first RTH) bar OHLC ───────────────────────────────────────────
    o = float(ctx.bar.get("open", 0))
    h = float(ctx.bar.get("high", 0))
    lo = float(ctx.bar.get("low", 0))
    c = float(ctx.bar.get("close", 0))

    res = detect_gap_and_go_core(pc, o, h, lo, c)
    if res is None:
        return None

    # ── Build the WatcherSignal (chart-stop; advisory SPY targets) ─────────────
    entry = c
    if res.direction == "long":
        stop_price = round(res.stop_level, 2)              # first bar low
        tp1_price = round(entry + _TP1_SPY_MOVE, 2)
        runner_price = round(entry + _RUNNER_SPY_MOVE, 2)
        instrument = "calls"
        gap_word = "gap-up"
    else:
        stop_price = round(res.stop_level, 2)              # first bar high
        tp1_price = round(entry - _TP1_SPY_MOVE, 2)
        runner_price = round(entry - _RUNNER_SPY_MOVE, 2)
        instrument = "puts"
        gap_word = "gap-down"

    vix_now = getattr(ctx, "vix_now", None) or 0.0
    reason = (
        f"GAP_AND_GO ({gap_word} continuation): SPY opened {res.gap_pct:+.2%} vs prior "
        f"RTH close {pc:.2f}; first RTH bar confirmed "
        f"({'GREEN' if res.direction == 'long' else 'RED'} C:{c:.2f} vs O:{o:.2f}). "
        f"Direction: {res.direction} (buy {instrument}). Entry={entry:.2f} "
        f"Stop(chart={'first-bar low' if res.direction == 'long' else 'first-bar high'})="
        f"{stop_price:.2f}. Premium stop DISABLED (chart-stop only, L51/L55). "
        f"VIX={vix_now:.1f}. Validated: real-fills exp+$41.6/WR72.6% chart-stop-only, "
        f"DSR PASS, WF_PASS (gap-and-go-LIVE.json)."
    )

    return WatcherSignal(
        watcher_name="gap_and_go_watcher",
        setup_name="GAP_AND_GO",
        direction=res.direction,
        entry_price=entry,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence="medium",   # data-discovered, not yet live-confirmed (OP-21)
        reason=reason,
        triggers_fired=[
            "OPENING_GAP",
            "FIRST_BAR_CONFIRM_GREEN" if res.direction == "long" else "FIRST_BAR_CONFIRM_RED",
            "GAP_CONTINUATION",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "gap_pct": round(res.gap_pct, 5),
            "prior_rth_close": round(pc, 2),
            "first_bar_open": round(o, 2),
            "first_bar_high": round(h, 2),
            "first_bar_low": round(lo, 2),
            "first_bar_close": round(c, 2),
            "chart_stop": stop_price,
            "premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,   # -0.99 = disabled
            "strike_offset": DEFAULT_STRIKE_OFFSET,          # 0 = ATM (validated tier)
            "default_qty": DEFAULT_QTY,
            "tp1_premium_pct": DEFAULT_TP1_PREMIUM_PCT,
            "tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "vix_now": vix_now,
            "validation": "analysis/recommendations/gap-and-go-LIVE.json",
            "promotion_gate": (
                "OP-21: offline real-fills PASS (exp+, WR72.6%, DSR PASS, WF_PASS, "
                "both dirs +, causal). Live gate: 3 live J confirmations + Rule 9."
            ),
        },
    )


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    def _mk_ctx(rows, *, vix=17.0):
        df = pd.DataFrame(rows)
        cur = df.iloc[-1]
        return BarContext(
            bar_idx=len(df) - 1,
            timestamp_et=cur["timestamp_et"],
            bar=cur,
            prior_bars=df,
            ribbon_now=None,
            ribbon_history=[],
            vix_now=vix,
            vix_prior=vix,
            vol_baseline_20=1000.0,
            range_baseline_20=0.5,
            levels_active=[],
            multi_day_levels=[],
            htf_15m_stack=None,
        )

    def _ts(y, mo, d, h, m):
        return dt.datetime(y, mo, d, h, m)

    results: list[tuple[str, bool]] = []

    # ── A — SHOULD FIRE long: gap UP +0.50% confirmed GREEN first bar ──────────
    # prior day close 600.00; today opens 603.00 (+0.50%), first bar closes green.
    rows_a = [
        dict(timestamp_et=_ts(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=_ts(2026, 1, 7, 9, 30), open=603.0, high=604.2, low=602.8, close=604.0, volume=5000),
    ]
    sig_a = detect_gap_and_go_setup(_mk_ctx(rows_a))
    fired_a = sig_a is not None and sig_a.direction == "long" and sig_a.stop_price == 602.8
    results.append(("A: gap-up +0.50% green first bar SHOULD fire long, stop=first-bar low", fired_a))
    if sig_a is not None:
        print(f"[A] FIRED {sig_a.direction} stop={sig_a.stop_price} gap={sig_a.metadata['gap_pct']}")
    else:
        print("[A] no signal")

    # ── B — SHOULD FIRE short: gap DOWN -0.50% confirmed RED first bar ─────────
    rows_b = [
        dict(timestamp_et=_ts(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=_ts(2026, 1, 7, 9, 30), open=597.0, high=597.2, low=595.8, close=596.0, volume=5000),
    ]
    sig_b = detect_gap_and_go_setup(_mk_ctx(rows_b))
    fired_b = sig_b is not None and sig_b.direction == "short" and sig_b.stop_price == 597.2
    results.append(("B: gap-down -0.50% red first bar SHOULD fire short, stop=first-bar high", fired_b))
    print(f"[B] {'FIRED ' + sig_b.direction + f' stop={sig_b.stop_price}' if sig_b else 'no signal'}")

    # ── C — SHOULD NOT FIRE: gap up but first bar RED (fade, not go) ───────────
    rows_c = [
        dict(timestamp_et=_ts(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=_ts(2026, 1, 7, 9, 30), open=603.0, high=603.2, low=601.5, close=602.0, volume=5000),
    ]
    sig_c = detect_gap_and_go_setup(_mk_ctx(rows_c))
    results.append(("C: gap-up but RED first bar should NOT fire (that's a fade)", sig_c is None))
    print(f"[C] {'no signal (correct)' if sig_c is None else 'FIRED (wrong!)'}")

    # ── D — SHOULD NOT FIRE: gap too small (+0.10% < 0.25% min) ────────────────
    rows_d = [
        dict(timestamp_et=_ts(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=_ts(2026, 1, 7, 9, 30), open=600.6, high=601.2, low=600.4, close=601.0, volume=5000),
    ]
    sig_d = detect_gap_and_go_setup(_mk_ctx(rows_d))
    results.append(("D: gap < 0.25% min should NOT fire", sig_d is None))
    print(f"[D] {'no signal (correct)' if sig_d is None else 'FIRED (wrong!)'}")

    # ── E — SHOULD NOT FIRE: gap too large (+2.0% > 1.5% max, runaway) ─────────
    rows_e = [
        dict(timestamp_et=_ts(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=_ts(2026, 1, 7, 9, 30), open=612.0, high=613.0, low=611.5, close=612.8, volume=5000),
    ]
    sig_e = detect_gap_and_go_setup(_mk_ctx(rows_e))
    results.append(("E: gap > 1.5% max (runaway) should NOT fire", sig_e is None))
    print(f"[E] {'no signal (correct)' if sig_e is None else 'FIRED (wrong!)'}")

    # ── F — SHOULD NOT FIRE: not the first RTH bar (09:35, not 09:30) ──────────
    rows_f = [
        dict(timestamp_et=_ts(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=_ts(2026, 1, 7, 9, 35), open=603.0, high=604.2, low=602.8, close=604.0, volume=5000),
    ]
    sig_f = detect_gap_and_go_setup(_mk_ctx(rows_f))
    results.append(("F: non-open bar (09:35) should NOT fire", sig_f is None))
    print(f"[F] {'no signal (correct)' if sig_f is None else 'FIRED (wrong!)'}")

    # ── G — explicit prior_rth_close overrides (single-day frame) ──────────────
    rows_g = [
        dict(timestamp_et=_ts(2026, 1, 7, 9, 30), open=603.0, high=604.2, low=602.8, close=604.0, volume=5000),
    ]
    sig_g = detect_gap_and_go_setup(_mk_ctx(rows_g), prior_rth_close=600.0)
    results.append(("G: explicit prior_rth_close fires on single-day frame", sig_g is not None and sig_g.direction == "long"))
    print(f"[G] {'FIRED ' + sig_g.direction if sig_g else 'no signal'}")

    # ── H — core parity: matches the discovery condition exactly on a known case ─
    core = detect_gap_and_go_core(600.0, 603.0, 604.2, 602.8, 604.0)
    results.append(("H: core long gap-up green, side=C stop=first-low", core is not None and core.side == "C" and core.stop_level == 602.8))
    core2 = detect_gap_and_go_core(600.0, 597.0, 597.2, 595.8, 596.0)
    results.append(("H2: core short gap-down red, side=P stop=first-high", core2 is not None and core2.side == "P" and core2.stop_level == 597.2))
    print(f"[H] core long={core}, core short={core2}")

    print("\n=== GAP_AND_GO self-test ===")
    all_pass = True
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print(f"=== {'ALL PASS' if all_pass else 'SOME FAILED'} ===")
    _sys.exit(0 if all_pass else 1)
