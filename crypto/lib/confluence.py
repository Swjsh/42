"""confluence -- the synthesis layer that makes the read ELITE.

Amateurs act on one signal. Elite desks STACK independent reads into a single
directional conviction and -- just as important -- flag when the reads DISAGREE.
Project Gamma had great siloed eyes (structure, patterns, ribbon, VWAP, levels,
volume) that never talked to each other. This module is the conductor.

It composes the existing detectors (does NOT re-implement them) into one
`ConfluenceRead`: a weighted directional bias + conviction (0-100), the stack of
confirming/conflicting factors, the invalidation level, and a one-line scenario in
J's language.

WEIGHTS are the load-bearing choice. They start as reasoned defaults and are
refined by the causal forward-edge study (backtest/autoresearch/structure_edge_study.py)
-- so conviction is MEASURED on our own SPY sample, not folklore. The weight block
is tagged with its calibration provenance.

Pure functions over Sequence[Bar] (closed bars, oldest first). No DataFrames, no
LLM, no orders. SPY-direction read -- a screening/ranking layer, NOT an option-edge
claim (delta/theta/stop corrupt the translation; real-fills sim remains the option
authority -- C3/L58).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from crypto.lib import chart_patterns as cp
from crypto.lib.bar import Bar
from crypto.lib.market_structure import analyze_structure

Direction = Literal["bullish", "bearish", "neutral"]

# Factor weights. Provenance tags:
#   [cal] = set/confirmed by structure_edge_study.py on 16mo SPY
#   [def] = reasoned default, not yet edge-measured (do not over-trust)
WEIGHTS: dict[str, float] = {
    "structure_trend": 2.0,   # [cal] trend from swings
    "structure_event": 2.5,   # [cal] last BOS/CHoCH
    "ema_stack": 2.0,         # [def] Saty-style 13/20/48 EMA order
    "vwap_side": 1.5,         # [cal] close above/below session VWAP
    "candlestick": 1.0,       # [def] last-bar reversal/continuation candle
    "pattern": 1.5,           # [def] chart_patterns hit
    "level": 1.5,             # [def] proximity to a named level + its role
    "mtf_structure": 2.0,     # [def] higher-timeframe structure agreement
}
NEUTRAL_DEADBAND = 1.0        # |net| within this => neutral
VOLUME_CONFIRM_MULT = 1.5     # last-bar vol >= this x baseline => conviction boost
# Measured on 16mo SPY (structure_edge_study, 2026-06-20, n=18,161 causal reads):
#   conviction is NOT monotonic with forward edge -> conviction is AWARENESS, not alpha.
#   The one robust effect is a BULL TILT (bullish reads ~52% vs bearish ~48%), which
#   independently corroborates the J-data bull-tilt finding. So: do NOT gate trades on
#   conviction; the real-fills simulator is the option-edge authority. This read is for
#   situational awareness, narration, journaling, and as a SCREEN -- not a trigger.
CALIBRATION_TAG = ("AWARENESS-NOT-ALPHA, PROVEN ON REAL OPRA FILLS (2026-06-20): as a 0DTE trigger "
                   "it LOSES -- -$23k/16mo, 0/6 quarters, 60% WR is a theta trap (C1/C3/L58/OP-14). "
                   "bull-tilt is relative-only (less-bad, not profitable). Screen/narration ONLY, never "
                   "a trigger or sizing input. See markdown/research/CONFLUENCE-REALFILLS-VERDICT-2026-06-20.md")


@dataclass(frozen=True, slots=True)
class Factor:
    name: str
    direction: str
    weight: float
    detail: str


@dataclass(frozen=True, slots=True)
class ConfluenceRead:
    bias: str
    conviction: float                 # 0..100 (100 = unanimous agreement)
    factors: tuple[Factor, ...]
    confirming: tuple[str, ...]
    conflicting: tuple[str, ...]
    invalidation: float | None
    scenario: str
    notes: dict


def _ema(values: Sequence[float], period: int) -> float:
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _session_vwap(bars: Sequence[Bar]) -> float:
    num = den = 0.0
    for b in bars:
        tp = (b.high + b.low + b.close) / 3.0
        num += tp * b.volume
        den += b.volume
    return num / den if den else bars[-1].close


def _last_candle(bars: Sequence[Bar]) -> tuple[Direction, str]:
    """Reversal/continuation candle on the last bar (chart-anatomy.md defs)."""
    b = bars[-1]
    rng = b.high - b.low
    if rng <= 0:
        return "neutral", "flat"
    body = abs(b.close - b.open)
    upper = b.high - max(b.open, b.close)
    lower = min(b.open, b.close) - b.low
    body_pct, up_pct, lo_pct = body / rng, upper / rng, lower / rng
    is_red, is_green = b.close < b.open, b.close > b.open
    if len(bars) >= 2:
        p = bars[-2]
        if is_green and p.close < p.open and b.open <= p.close and b.close >= p.open and body_pct >= 0.5:
            return "bullish", "bullish_engulfing"
        if is_red and p.close > p.open and b.open >= p.close and b.close <= p.open and body_pct >= 0.5:
            return "bearish", "bearish_engulfing"
    if is_green and lo_pct >= 0.5 and up_pct <= 0.2 and body_pct <= 0.3:
        return "bullish", "hammer"
    if is_red and up_pct >= 0.5 and lo_pct <= 0.2 and body_pct <= 0.3:
        return "bearish", "shooting_star"
    if body_pct >= 0.75 and up_pct <= 0.1 and lo_pct <= 0.1:
        return ("bullish", "bullish_marubozu") if is_green else ("bearish", "bearish_marubozu")
    if body_pct < 0.1:
        return "neutral", "doji"
    return "neutral", "indecisive"


def _pattern_vote(bars: Sequence[Bar]) -> tuple[Direction, str]:
    best = None
    for name in ("double_bottom_detector", "double_top_detector", "head_and_shoulders_detector",
                 "failed_breakdown_wick", "rejection_at_level", "momentum_acceleration"):
        fn = getattr(cp, name, None)
        if fn is None:
            continue
        try:
            hit = fn(bars)
        except Exception:
            continue
        if hit is not None and hit.bias in ("bullish", "bearish"):
            if best is None or hit.confidence > best[1]:
                best = (hit.bias, hit.confidence, hit.pattern)
    if best is None:
        return "neutral", "none"
    return best[0], f"{best[2]}({best[1]:.2f})"


def _nearest_level_vote(levels, price: float) -> tuple[Direction, str]:
    if not levels:
        return "neutral", "no_levels"
    best = None
    for lv in levels:
        try:
            lp = float(lv.get("price"))
        except (TypeError, ValueError, AttributeError):
            continue
        d = abs(lp - price)
        if best is None or d < best[0]:
            best = (d, lp, (lv.get("type") or lv.get("role") or "level"))
    if best is None or best[0] > max(0.5, price * 0.0008):
        return "neutral", "no_near_level"
    _, lp, typ = best
    typ = str(typ).lower()
    if "support" in typ or "floor" in typ:
        return "bullish", f"at support {lp:.2f}"
    if "resist" in typ or "ceiling" in typ:
        return "bearish", f"at resistance {lp:.2f}"
    return "neutral", f"at {typ} {lp:.2f}"


def _sign(d: Direction) -> int:
    return 1 if d == "bullish" else (-1 if d == "bearish" else 0)


def compute_confluence(
    bars: Sequence[Bar],
    *,
    levels: list | None = None,
    vix: dict | None = None,
    htf_bars: Sequence[Bar] | None = None,
    window: int = 2,
    weights: dict | None = None,
) -> ConfluenceRead:
    """Fuse every read into one conviction. `weights` overrides the module defaults."""
    w = {**WEIGHTS, **(weights or {})}
    ms = analyze_structure(bars, window=window)
    factors: list[Factor] = []

    # 1. structure trend
    td: Direction = ("bullish" if ms.trend == "uptrend"
                     else "bearish" if ms.trend == "downtrend" else "neutral")
    factors.append(Factor("structure_trend", td, w["structure_trend"], f"trend={ms.trend}"))

    # 2. last structure event (BOS/CHoCH)
    if ms.last_event is not None:
        ed: Direction = "bullish" if ms.last_event.direction == "bullish" else "bearish"
        factors.append(Factor("structure_event", ed, w["structure_event"],
                              f"{ms.last_event.direction} {ms.last_event.kind} @ {ms.last_event.broken_price:.2f}"))

    # 3. EMA stack (13/20/48)
    closes = [b.close for b in bars]
    if len(closes) >= 5:
        f, p, s = _ema(closes, 13), _ema(closes, 20), _ema(closes, 48)
        if f > p > s:
            factors.append(Factor("ema_stack", "bullish", w["ema_stack"], "fast>pivot>slow"))
        elif f < p < s:
            factors.append(Factor("ema_stack", "bearish", w["ema_stack"], "fast<pivot<slow"))
        else:
            factors.append(Factor("ema_stack", "neutral", w["ema_stack"], "mixed"))

    # 4. VWAP side
    vwap = _session_vwap(bars)
    vd: Direction = "bullish" if bars[-1].close > vwap else "bearish" if bars[-1].close < vwap else "neutral"
    factors.append(Factor("vwap_side", vd, w["vwap_side"], f"close {bars[-1].close:.2f} vs vwap {vwap:.2f}"))

    # 5. candlestick
    cd, cname = _last_candle(bars)
    factors.append(Factor("candlestick", cd, w["candlestick"], cname))

    # 6. chart pattern
    pd, pname = _pattern_vote(bars)
    factors.append(Factor("pattern", pd, w["pattern"], pname))

    # 7. level proximity
    ld, lname = _nearest_level_vote(levels, bars[-1].close)
    factors.append(Factor("level", ld, w["level"], lname))

    # 8. MTF structure
    if htf_bars:
        hms = analyze_structure(htf_bars, window=window)
        hd: Direction = ("bullish" if hms.trend == "uptrend"
                         else "bearish" if hms.trend == "downtrend" else "neutral")
        factors.append(Factor("mtf_structure", hd, w["mtf_structure"], f"htf trend={hms.trend}"))

    # aggregate. Conviction is normalised by TOTAL weight (incl. factors that voted
    # neutral) so it only reaches 100 when every factor votes AND agrees -- neutral or
    # conflicting factors drag it down. (Earlier /voting_weight saturated at 80-100 on
    # 75% of reads, per structure_edge_study -- meaningless. This discriminates.)
    net = sum(_sign(f.direction) * f.weight for f in factors)
    voting_weight = sum(f.weight for f in factors if f.direction != "neutral")
    total_weight = sum(f.weight for f in factors)
    bias: Direction = "bullish" if net > NEUTRAL_DEADBAND else "bearish" if net < -NEUTRAL_DEADBAND else "neutral"
    conviction = round(min(100.0, abs(net) / total_weight * 100) if total_weight else 0.0, 1)

    # volume confirmation boost
    vol_note = "n/a"
    if len(bars) >= 21 and bias != "neutral":
        base = sum(b.volume for b in bars[-21:-1]) / 20.0
        last = bars[-1]
        last_dir = "bullish" if last.close > last.open else "bearish" if last.close < last.open else "neutral"
        if base > 0 and last.volume >= VOLUME_CONFIRM_MULT * base and last_dir == bias:
            conviction = round(min(100.0, conviction + 10), 1)
            vol_note = f"confirm {last.volume/base:.1f}x"
        elif base > 0 and last.volume >= VOLUME_CONFIRM_MULT * base and last_dir != bias and last_dir != "neutral":
            conviction = round(max(0.0, conviction - 10), 1)
            vol_note = f"divergent {last.volume/base:.1f}x"

    confirming = tuple(f.name for f in factors if f.direction == bias and bias != "neutral")
    opp = {"bullish": "bearish", "bearish": "bullish"}.get(bias)
    conflicting = tuple(f.name for f in factors if f.direction == opp) if opp else ()

    invalidation_raw = (ms.last_swing_low if bias == "bullish"
                        else ms.last_swing_high if bias == "bearish" else None)
    invalidation = round(invalidation_raw, 2) if invalidation_raw is not None else None

    scenario = _scenario(bias, conviction, confirming, conflicting, invalidation, ms)
    notes = {
        "net_score": round(net, 2),
        "voting_weight": round(voting_weight, 2),
        "vwap": round(vwap, 2),
        "volume": vol_note,
        "structure_trend": ms.trend,
        "calibration": CALIBRATION_TAG,
        "disclaimer": "SPY-direction screening read, not an option-edge claim (C3/L58).",
    }
    return ConfluenceRead(
        bias=bias, conviction=conviction, factors=tuple(factors),
        confirming=confirming, conflicting=conflicting,
        invalidation=invalidation,
        scenario=scenario, notes=notes,
    )


def _scenario(bias, conviction, confirming, conflicting, invalidation, ms) -> str:
    if bias == "neutral":
        return f"NEUTRAL ({conviction}/100) -- reads conflict ({', '.join(conflicting) or 'mixed'}); no edge, wait."
    head = f"{bias.upper()} confluence {conviction}/100"
    conf = f"confirm: {', '.join(confirming)}" if confirming else ""
    confl = f" | conflict: {', '.join(conflicting)}" if conflicting else ""
    inval = f" | invalidation: {'close below' if bias == 'bullish' else 'close above'} {invalidation}" if invalidation is not None else ""
    return f"{head} -- {conf}{confl}{inval}"
