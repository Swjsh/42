"""EMA ribbon signal computer for the Crypto Heartbeat.

Accepts Alpaca bar dicts (oldest-first, in-progress bar already stripped),
returns a signal dict the heartbeat prompt can act on directly.

Usage (standalone test):
  python backtest/crypto/crypto_scalper.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


# ── Math ───────────────────────────────────────────────────────────────────────

def _ema(prices: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out = [prices[0]]
    for p in prices[1:]:
        out.append(p * k + out[-1] * (1 - k))
    return out


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(len(trs), period)


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in diffs[-period:]]
    losses = [max(-d, 0.0) for d in diffs[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1 + avg_gain / avg_loss))


# ── Signal ─────────────────────────────────────────────────────────────────────

@dataclass
class CryptoSignal:
    price:            float
    ema_fast:         float
    ema_pivot:        float
    ema_slow:         float
    ribbon_state:     str          # BULL | BEAR | NEUTRAL
    ribbon_spread_pct: float       # |fast - slow| / slow * 100
    stack_duration:   int          # bars since current stack started
    atr_14:           float
    rsi_14:           float
    signal:           Optional[str]  # LONG | SHORT | None
    stop_distance:    float        # ATR * atr_stop_mult (default 2.0)
    tp1_distance:     float        # ATR * atr_tp1_mult (default 3.0)
    runner_distance:  float        # ATR * atr_runner_mult (default 4.5)
    computed_at:      str
    error:            Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None or k == "signal"}


def compute_signals(
    bars:              list[dict],
    ema_fast_period:   int   = 9,
    ema_pivot_period:  int   = 21,
    ema_slow_period:   int   = 50,
    atr_period:        int   = 14,
    rsi_period:        int   = 14,
    rsi_overbought:    float = 80.0,
    rsi_oversold:      float = 20.0,
    min_stack_bars:    int   = 2,
    atr_stop_mult:     float = 2.0,
    atr_tp1_mult:      float = 3.0,
    atr_runner_mult:   float = 4.5,
) -> CryptoSignal:
    """Compute EMA ribbon signal from closed bars (oldest first, no in-progress bar).

    bars: list of {"t": str, "o": float, "h": float, "l": float, "c": float, "v": float}
    """
    min_bars = max(ema_slow_period + 2, atr_period + 2, rsi_period + 2)
    if len(bars) < min_bars:
        return CryptoSignal(
            price=0, ema_fast=0, ema_pivot=0, ema_slow=0,
            ribbon_state="NEUTRAL", ribbon_spread_pct=0, stack_duration=0,
            atr_14=0, rsi_14=50, signal=None, stop_distance=0,
            tp1_distance=0, runner_distance=0,
            computed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            error=f"Need >= {min_bars} bars, got {len(bars)}",
        )

    closes = [float(b["c"]) for b in bars]
    highs  = [float(b["h"]) for b in bars]
    lows   = [float(b["l"]) for b in bars]

    ema_f_series = _ema(closes, ema_fast_period)
    ema_p_series = _ema(closes, ema_pivot_period)
    ema_s_series = _ema(closes, ema_slow_period)

    f0, p0, s0 = ema_f_series[-1], ema_p_series[-1], ema_s_series[-1]
    c0          = closes[-1]

    bull_now = f0 > p0 > s0
    bear_now = f0 < p0 < s0

    # Stack duration (consecutive bars in current stack)
    stack_duration = 0
    for i in range(len(bars) - 1, -1, -1):
        fi, pi, si = ema_f_series[i], ema_p_series[i], ema_s_series[i]
        if bull_now and fi > pi > si:
            stack_duration += 1
        elif bear_now and fi < pi < si:
            stack_duration += 1
        else:
            break

    ribbon_state = "BULL" if bull_now else ("BEAR" if bear_now else "NEUTRAL")
    ribbon_spread_pct = abs(f0 - s0) / s0 * 100 if s0 else 0.0

    atr14 = _atr(highs, lows, closes, atr_period)
    rsi14 = _rsi(closes, rsi_period)

    # Entry conditions
    signal: Optional[str] = None
    if (bull_now
            and stack_duration >= min_stack_bars
            and c0 > p0
            and rsi14 < rsi_overbought):
        signal = "LONG"
    elif (bear_now
            and stack_duration >= min_stack_bars
            and c0 < p0
            and rsi14 > rsi_oversold):
        signal = "SHORT"

    return CryptoSignal(
        price            = round(c0, 2),
        ema_fast         = round(f0, 2),
        ema_pivot        = round(p0, 2),
        ema_slow         = round(s0, 2),
        ribbon_state     = ribbon_state,
        ribbon_spread_pct= round(ribbon_spread_pct, 4),
        stack_duration   = stack_duration,
        atr_14           = round(atr14, 2),
        rsi_14           = round(rsi14, 1),
        signal           = signal,
        stop_distance    = round(atr14 * atr_stop_mult, 2),
        tp1_distance     = round(atr14 * atr_tp1_mult, 2),
        runner_distance  = round(atr14 * atr_runner_mult, 2),
        computed_at      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def size_position(
    equity:       float,
    entry_price:  float,
    stop_distance: float,
    risk_pct:      float = 0.02,
    max_pct:       float = 0.25,
    min_notional:  float = 50.0,
) -> dict:
    """Compute BTC position size from dollar-risk model.

    Returns {"qty_crypto": float, "qty_usd": float, "risk_dollars": float}
    """
    risk_dollars  = equity * risk_pct
    stop_pct      = stop_distance / entry_price if entry_price else 0.01
    qty_usd       = risk_dollars / stop_pct if stop_pct else 0.0
    qty_usd       = min(qty_usd, equity * max_pct)
    qty_crypto    = qty_usd / entry_price if entry_price else 0.0

    if qty_usd < min_notional:
        return {"qty_crypto": 0.0, "qty_usd": 0.0, "risk_dollars": 0.0,
                "error": f"Notional ${qty_usd:.2f} < min ${min_notional}"}

    return {
        "qty_crypto":   round(qty_crypto, 6),
        "qty_usd":      round(qty_usd, 2),
        "risk_dollars": round(risk_dollars, 2),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random

    # Synthetic BTC bars for smoke test
    random.seed(42)
    price = 103000.0
    bars = []
    for i in range(70):
        o = price
        h = price + random.uniform(50, 800)
        l = price - random.uniform(50, 600)
        c = random.uniform(l, h)
        bars.append({"t": f"2026-06-17T{i:02d}:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": 12.5})
        price = c

    sig = compute_signals(bars)
    print(json.dumps(sig.to_dict(), indent=2))

    if sig.signal:
        sizing = size_position(2000.0, sig.price, sig.stop_distance)
        print(json.dumps(sizing, indent=2))
    else:
        print("No signal on synthetic data (expected — random walk)")
