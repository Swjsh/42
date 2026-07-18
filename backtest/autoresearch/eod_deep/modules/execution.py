"""Execution module — Phase 2.4 real implementation (was Phase-1 shallow stub).

Answers: "did entries/exits fire as the plan said, and how fast?"

Three real sub-checks per trade, replacing the Phase-1 fill-count/avg-slippage-only stub:

  1. Fill-timing-vs-trigger-bar — how long between the engine's ENTER_BULL/ENTER_BEAR
     decision (decisions.jsonl) and the actual entry fill (trades.csv / Alpaca order)?
     A fast, tight fill means the engine acted on the trigger it saw, not a stale one.
  2. Partial-fill detection — did the entry order fill in more than one clip? If so,
     how spread out in time (a single-tick partial is fine; a multi-minute partial
     means real slippage risk the raw price alone doesn't show).
  3. Slippage (kept from Phase 1) — avg |slippage_cents| across all fills that carry it.

No trades = neutral stub (nothing to score). Missing engine_decisions for a given
trade degrades gracefully (fill-timing sub-score falls back to a lower-confidence
default, not a crash) — J's manual entries or a decisions.jsonl gap should never
throw the whole category.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from ..schema import CategoryScore
from ..ingest import IngestedData

# Decisions that count as "the trigger that led to this trade's entry".
_ENTRY_DECISIONS = ("ENTER_BULL", "ENTER_BEAR", "ENTER", "ENTER_LONG", "ENTER_SHORT")


def _parse_hms(time_et: str) -> Optional[int]:
    """'HH:MM:SS' or 'HH:MM' -> seconds-since-midnight. None if unparseable."""
    if not time_et:
        return None
    parts = time_et.strip().split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + int(float(s))
        if len(parts) == 2:
            h, m = parts
            return int(h) * 3600 + int(m) * 60
    except (ValueError, TypeError):
        return None
    return None


def _fill_timing_for_trade(trade) -> dict:
    """Seconds between the ENTER decision and the first entry fill, or None if
    either side is missing/unparseable."""
    trigger_secs = None
    for d in sorted(trade.engine_decisions or [], key=lambda d: d.time_et or ""):
        if d.decision in _ENTRY_DECISIONS:
            trigger_secs = _parse_hms(d.time_et)
            if trigger_secs is not None:
                break

    entry_fills = [f for f in (trade.fills or []) if f.reason == "entry"]
    entry_fills_sorted = sorted(entry_fills, key=lambda f: f.time_et or "")
    fill_secs = _parse_hms(entry_fills_sorted[0].time_et) if entry_fills_sorted else None

    lag_secs = None
    if trigger_secs is not None and fill_secs is not None and fill_secs >= trigger_secs:
        lag_secs = fill_secs - trigger_secs

    return {
        "lag_secs": lag_secs,
        "has_trigger_decision": trigger_secs is not None,
        "has_entry_fill": fill_secs is not None,
    }


def _partial_fill_for_trade(trade) -> dict:
    """Detect whether the entry filled in more than one clip and how spread out."""
    entry_fills = sorted(
        [f for f in (trade.fills or []) if f.reason == "entry"],
        key=lambda f: f.time_et or "",
    )
    is_partial = len(entry_fills) > 1
    spread_secs = None
    if is_partial:
        secs = [s for s in (_parse_hms(f.time_et) for f in entry_fills) if s is not None]
        if len(secs) >= 2:
            spread_secs = max(secs) - min(secs)
    return {
        "is_partial_fill": is_partial,
        "clip_count": len(entry_fills),
        "spread_secs": spread_secs,
    }


def _slippage_for_trade(trade) -> Optional[float]:
    slips = [f.slippage_cents for f in (trade.fills or []) if f.slippage_cents is not None]
    if not slips:
        return None
    return sum(slips) / len(slips)


def analyze_execution(data: IngestedData, trades) -> CategoryScore:
    if not trades:
        return CategoryScore(
            score=50.0,
            evidence={"phase": "2.4", "trade_count": 0},
            narrative="No trades to analyze.",
            actions=[],
        )

    per_trade = []
    timing_pts_sum = 0.0
    partial_pts_sum = 0.0
    slippage_pts_sum = 0.0

    for t in trades:
        timing = _fill_timing_for_trade(t)
        partial = _partial_fill_for_trade(t)
        avg_slip = _slippage_for_trade(t)

        # 40 pts: fill-timing-vs-trigger-bar responsiveness
        lag = timing["lag_secs"]
        if lag is None:
            timing_pts = 25.0  # unknown -- neutral-low, not a crash, not a free pass
        elif lag <= 60:
            timing_pts = 40.0
        elif lag <= 180:
            timing_pts = 30.0
        elif lag <= 300:
            timing_pts = 20.0
        else:
            timing_pts = 10.0

        # 30 pts: partial-fill quality (no partial = full marks; tight partial ok;
        # spread-out partial = real slippage-risk exposure)
        if not partial["is_partial_fill"]:
            partial_pts = 30.0
        elif partial["spread_secs"] is not None and partial["spread_secs"] <= 60:
            partial_pts = 22.0
        else:
            partial_pts = 12.0

        # 30 pts: slippage (kept from Phase 1, same thresholds)
        if avg_slip is None:
            slippage_pts = 22.0  # no data -- neutral, not penalized for missing field
        elif abs(avg_slip) <= 5:
            slippage_pts = 30.0
        elif abs(avg_slip) <= 10:
            slippage_pts = 25.0
        elif abs(avg_slip) <= 20:
            slippage_pts = 15.0
        else:
            slippage_pts = 5.0

        timing_pts_sum += timing_pts
        partial_pts_sum += partial_pts
        slippage_pts_sum += slippage_pts

        per_trade.append({
            "trade_id": t.id,
            "fill_lag_secs": lag,
            "is_partial_fill": partial["is_partial_fill"],
            "partial_clip_count": partial["clip_count"],
            "partial_spread_secs": partial["spread_secs"],
            "avg_slippage_cents": round(avg_slip, 1) if avg_slip is not None else None,
            "timing_pts": timing_pts,
            "partial_pts": partial_pts,
            "slippage_pts": slippage_pts,
        })

    n = len(trades)
    timing_avg = timing_pts_sum / n
    partial_avg = partial_pts_sum / n
    slippage_avg = slippage_pts_sum / n
    score = round(timing_avg + partial_avg + slippage_avg, 1)

    n_partial = sum(1 for p in per_trade if p["is_partial_fill"])
    known_lags = [p["fill_lag_secs"] for p in per_trade if p["fill_lag_secs"] is not None]
    avg_lag_str = f"{sum(known_lags) / len(known_lags):.0f}s" if known_lags else "unknown"

    narrative = (
        f"{n} trade(s). Avg fill-lag-vs-trigger {avg_lag_str} "
        f"({len(known_lags)}/{n} trades had a resolvable trigger+fill pair). "
        f"{n_partial}/{n} trades had a partial-fill entry. "
        f"Score {score}/100 (timing={timing_avg:.0f}/40, partial={partial_avg:.0f}/30, "
        f"slippage={slippage_avg:.0f}/30)."
    )

    return CategoryScore(
        score=score,
        evidence={
            "phase": "2.4",
            "trade_count": n,
            "per_trade": per_trade,
            "weights": {
                "fill_timing": round(timing_avg, 1),
                "partial_fill": round(partial_avg, 1),
                "slippage": round(slippage_avg, 1),
            },
        },
        narrative=narrative,
        actions=[],
    )
