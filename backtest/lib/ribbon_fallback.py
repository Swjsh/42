"""ribbon_fallback.py — compute the Saty Pivot Ribbon read from generic OHLCV bars.

Layer-1a of the OPEN-BLINDNESS-TV-HANG fix (queue.md, LIVE PROOF 2026-06-24): when a
TradingView chart read fails or HANGS at the open, the heartbeat is blind to price +
ribbon and tree-kills at the 280s timeout — it missed a clean PMH-rejection scalp on
2026-06-24 while Alpaca bars were live the entire time. This module is the source-
AGNOSTIC compute core that lets the engine derive price + the Saty ribbon stack from
ANY 5m OHLCV bars (Alpaca, yfinance, CSV) so it can keep deciding when TV is down.

CRITICAL — same-decision parity (C11 / L180): the fallback MUST make the SAME ribbon
decision the live TV indicator makes, or it silently changes the trade set. This module
guarantees that by reusing the EXACT canonical, fingerprinted spec rather than re-reading
TV (which can drift):
  - periods are LOADED from backtest/lib/ribbon_config.json (fingerprinted 2026-05-07,
    all EMAs within 5c of live TradingView): fast=13, pivot=20, slow=48, sma=50.
  - the EMA is TradingView-style (SMA seed of the first N bars, then EMA), price=close.
  - `test_ribbon_fallback.py` pins a byte-identical PARITY test against the reference
    implementation in automation/scripts/compute_ema_snapshot.py (the scheduled
    Gamma_EmaSnapshot producer) so the two can never silently diverge.

Stack semantics match heartbeat.md exactly:
  BULL  = fast > pivot > slow   (line 546, Fast>Pivot>Slow)
  BEAR  = fast < pivot < slow   (line 448, Fast<Pivot<Slow)
  MIXED = anything else (chop / transition — NOT an invalidation by itself)
  spread_cents = round(abs(fast - slow) * 100, 1)   (ribbon width; flip needs >= 30c)

This module does NOT fetch bars and does NOT touch the live heartbeat — wiring the
Alpaca fetch + fast-fail TV timeout + Safe/Bold stagger into the heartbeat is the
rail-4 (propose-only) step for a later fire. Here we ship only the tested compute core.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_CONFIG_PATH = Path(__file__).resolve().parent / "ribbon_config.json"


def load_periods(config_path: Path | None = None) -> dict[str, int]:
    """Load the canonical fingerprinted ribbon EMA periods from ribbon_config.json.

    Returns a dict with keys fast_ema, pivot_ema, slow_ema, sma_50. Periods are loaded
    (never hardcoded here) so a re-fingerprint of the indicator updates this module too.
    """
    path = config_path or _CONFIG_PATH
    cfg = json.loads(path.read_text(encoding="utf-8"))
    periods = dict(cfg["periods"])
    return {
        "fast_ema": int(periods["fast_ema"]),
        "pivot_ema": int(periods["pivot_ema"]),
        "slow_ema": int(periods["slow_ema"]),
        "sma_50": int(periods.get("sma_50", 50)),
    }


def tv_ema(closes: Sequence[float], period: int) -> float | None:
    """TradingView-style EMA value at the LAST bar: seed with SMA of the first N bars,
    then EMA forward. Returns None if there are fewer than `period` bars (cannot seed).

    Byte-identical to automation/scripts/compute_ema_snapshot.py::ema (pinned by test).
    """
    vals = [float(c) for c in closes]
    n = len(vals)
    if period <= 0 or n < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = sum(vals[:period]) / period  # SMA seed at index period-1
    for i in range(period, n):
        ema_val = vals[i] * k + ema_val * (1 - k)
    return ema_val


def _sma_last(closes: Sequence[float], period: int) -> float | None:
    vals = [float(c) for c in closes]
    if period <= 0 or len(vals) < period:
        return None
    return sum(vals[-period:]) / period


def classify_stack(fast: float | None, pivot: float | None, slow: float | None) -> str:
    """BULL if fast>pivot>slow, BEAR if fast<pivot<slow, else MIXED. UNKNOWN if any None.

    UNKNOWN is the fail-closed signal (uncertainty = abstain): the heartbeat must NOT
    trade a ribbon-stacked setup it cannot read.
    """
    if fast is None or pivot is None or slow is None:
        return "UNKNOWN"
    if fast > pivot > slow:
        return "BULL"
    if fast < pivot < slow:
        return "BEAR"
    return "MIXED"


@dataclass(frozen=True)
class RibbonRead:
    """Immutable ribbon read derived from OHLCV bars. Mirrors heartbeat.md's
    `ribbon` object: {fast, pivot, slow, spread_cents, stack} plus price + sma_50."""

    price: float | None
    ema_fast: float | None
    ema_pivot: float | None
    ema_slow: float | None
    sma_50: float | None
    spread_cents: float | None
    stack: str
    bars_used: int
    source: str

    def is_usable(self) -> bool:
        """True only when the full ribbon resolved (stack is a real direction/chop, not UNKNOWN)."""
        return self.stack != "UNKNOWN"


def compute_ribbon(
    closes: Sequence[float],
    *,
    source: str = "alpaca_fallback",
    config_path: Path | None = None,
) -> RibbonRead:
    """Compute the Saty ribbon read from a sequence of close prices (oldest -> newest).

    Fail-closed by design: if there are too few bars to seed any EMA, that EMA is None
    and the stack degrades to UNKNOWN so the engine abstains rather than trading a
    misread ribbon. Never raises on short input — the live fast-fail path needs that.
    """
    periods = load_periods(config_path)
    vals = [float(c) for c in closes]
    price = vals[-1] if vals else None

    fast = tv_ema(vals, periods["fast_ema"])
    pivot = tv_ema(vals, periods["pivot_ema"])
    slow = tv_ema(vals, periods["slow_ema"])
    sma50 = _sma_last(vals, periods["sma_50"])

    stack = classify_stack(fast, pivot, slow)
    spread = (
        round(abs(fast - slow) * 100, 1)
        if (fast is not None and slow is not None)
        else None
    )

    return RibbonRead(
        price=round(price, 4) if price is not None else None,
        ema_fast=round(fast, 4) if fast is not None else None,
        ema_pivot=round(pivot, 4) if pivot is not None else None,
        ema_slow=round(slow, 4) if slow is not None else None,
        sma_50=round(sma50, 4) if sma50 is not None else None,
        spread_cents=spread,
        stack=stack,
        bars_used=len(vals),
        source=source,
    )


def closes_from_bars(bars: Sequence[dict]) -> list[float]:
    """Extract close prices (oldest -> newest) from a list of Alpaca-style bar dicts.

    Accepts the common key spellings ('c', 'close', 'Close'). Source-agnostic so the
    same compute core serves Alpaca, yfinance, or CSV bars. Raises KeyError loudly if a
    bar has no recognizable close (fail-closed: a malformed feed must not silently pass).
    """
    out: list[float] = []
    for b in bars:
        for key in ("c", "close", "Close"):
            if key in b and b[key] is not None:
                out.append(float(b[key]))
                break
        else:
            raise KeyError(f"bar has no close field (tried c/close/Close): {b!r}")
    return out
