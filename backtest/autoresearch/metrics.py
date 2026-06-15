"""Performance metrics computed from a list of TradeFill objects.

The Sharpe ratio is the loss function (Karpathy autoresearch -> Gamma mapping).
We compute it on the daily P&L series rather than per-trade so multi-trade
days contribute correctly.

All metrics are immutable (frozen dataclass) so callers cannot accidentally
mutate the baseline.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

# Import lazily inside functions to avoid forcing a heavy lib.* import at
# module load time when autoresearch is invoked from the CLI.


@dataclass(frozen=True)
class TradeMetrics:
    """Aggregate scorecard for a backtest run."""

    n_trades: int
    n_winners: int
    n_losers: int
    win_rate: float
    total_pnl: float
    expectancy: float            # mean P&L per trade
    avg_winner: float            # mean P&L of winning trades (0 if none)
    avg_loser: float             # mean P&L of losing trades (0 if none, sign-preserving negative)
    wl_ratio: float              # |avg_winner / avg_loser| (math.inf if no losers)
    max_drawdown: float          # negative number, peak-to-trough on cumulative P&L
    sharpe_daily: float          # daily Sharpe annualised (mean/std * sqrt(252))
    n_days_traded: int           # distinct trading days with at least one trade

    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "n_winners": self.n_winners,
            "n_losers": self.n_losers,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": round(self.total_pnl, 2),
            "expectancy": round(self.expectancy, 2),
            "avg_winner": round(self.avg_winner, 2),
            "avg_loser": round(self.avg_loser, 2),
            "wl_ratio": round(self.wl_ratio, 3) if math.isfinite(self.wl_ratio) else None,
            "max_drawdown": round(self.max_drawdown, 2),
            "sharpe_daily": round(self.sharpe_daily, 4),
            "n_days_traded": self.n_days_traded,
        }


def _trade_date(trade) -> dt.date:
    """Extract the trade date in a TZ-naive way (entries can be TZ-aware or not)."""
    ts = trade.entry_time_et
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return ts.date()


def daily_pnl_series(trades: Sequence) -> dict[dt.date, float]:
    """Group trade P&L by date. Days with no trades are NOT in the dict
    (Sharpe is computed on trading days only)."""
    out: dict[dt.date, float] = {}
    for t in trades:
        d = _trade_date(t)
        out[d] = out.get(d, 0.0) + float(t.dollar_pnl)
    return out


def _sharpe(values: Iterable[float], periods_per_year: int = 252) -> float:
    """Annualised Sharpe of a series. Returns 0 when std is degenerate.

    We use the std of the raw daily P&L (in dollars). The unit cancels in
    mean/std, so the Sharpe is unitless.
    """
    vals = list(values)
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    variance = sum((v - mean) ** 2 for v in vals) / (n - 1)
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    return (mean / std) * math.sqrt(periods_per_year)


def compute_metrics(trades: Sequence) -> TradeMetrics:
    """Build a `TradeMetrics` from a list of TradeFill objects."""
    n = len(trades)
    if n == 0:
        return TradeMetrics(
            n_trades=0, n_winners=0, n_losers=0, win_rate=0.0,
            total_pnl=0.0, expectancy=0.0, avg_winner=0.0, avg_loser=0.0,
            wl_ratio=0.0, max_drawdown=0.0, sharpe_daily=0.0, n_days_traded=0,
        )
    pnls = [float(t.dollar_pnl) for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)
    expectancy = total_pnl / n
    avg_winner = (sum(winners) / len(winners)) if winners else 0.0
    avg_loser = (sum(losers) / len(losers)) if losers else 0.0
    wl_ratio = abs(avg_winner / avg_loser) if avg_loser else math.inf

    # Sequential drawdown (sorted by entry time).
    sorted_trades = sorted(trades, key=_trade_date)
    cum = peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        cum += float(t.dollar_pnl)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    daily = daily_pnl_series(trades)
    sharpe = _sharpe(daily.values()) if daily else 0.0

    return TradeMetrics(
        n_trades=n,
        n_winners=len(winners),
        n_losers=len(losers),
        win_rate=len(winners) / n,
        total_pnl=total_pnl,
        expectancy=expectancy,
        avg_winner=avg_winner,
        avg_loser=avg_loser,
        wl_ratio=wl_ratio,
        max_drawdown=max_dd,
        sharpe_daily=sharpe,
        n_days_traded=len(daily),
    )
