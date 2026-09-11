"""Guards for the multi-day DTE comparison (chef 2026-07-07 offline R&D).

Locks the load-bearing claims so a future refactor can't silently break them:
  1. The per-DTE OPRA cache is 0DTE-by-construction in dir `options/` but the
     1dte/2dte dirs hold the SAME contract's earlier entry-day bars — i.e. a
     multi-day price path IS reconstructable from the cache (data-not-blocked).
  2. The anchor twin (585P exp 2025-06-02, J's 745P analog) prices correctly
     through the real sim fill path: entry == real 2DTE open + slippage.
  3. The discipline helpers (WR, drop-topN, oos split) behave.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_multiday_dte_compare.py -q
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

_BT = Path(__file__).resolve().parents[1]
_REPO = _BT.parent
for p in (str(_BT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from autoresearch import _dte_expansion_sim as X
from autoresearch import multiday_dte_compare as C


class _Fill:
    """Minimal DteFill stand-in for the pure-metric helpers."""
    def __init__(self, date, pnl):
        self.date = date
        self.dollar_pnl = pnl
        self.held_overnight = False


def test_cache_is_0dte_in_options_dir_but_multiday_reconstructable():
    """options/ bar date == expiry (0DTE); options_2dte/ holds the entry-2-days
    bars for the SAME contract -> the price path spans days."""
    # (a) options/ is 0DTE-by-construction: bar date == expiry. Assert on a
    #     contract known to be in the 0DTE dir (the 588C 3-tier example).
    df0 = X.load_dte_contract_bars("SPY250116C00588000", 0)
    assert df0 is not None
    assert (df0["timestamp_et"].dt.date == dt.date(2025, 1, 16)).all()

    # (b) the anchor twin's multi-day path is reconstructable from 1dte+2dte
    #     (not every contract is present in the 0DTE dir; the weekly hold only
    #     needs the pre-expiry entry-day bars, which ARE cached).
    sym = "SPY250602P00585000"  # 585P exp 2025-06-02
    df1 = X.load_dte_contract_bars(sym, 1)
    df2 = X.load_dte_contract_bars(sym, 2)
    assert df1 is not None and df2 is not None
    assert (df1["timestamp_et"].dt.date == dt.date(2025, 5, 30)).all()
    assert (df2["timestamp_et"].dt.date == dt.date(2025, 5, 29)).all()
    dates = {df1["timestamp_et"].iloc[0].date(), df2["timestamp_et"].iloc[0].date()}
    assert len(dates) == 2, "expected distinct pre-expiry entry days, got %s" % dates


def test_anchor_745p_twin_prices_correctly():
    """The 585P anchor twin (J's 745P analog: ~1.51 -> 3.84 intraday, 4.13 next day)
    prices through the REAL sim fill path — entry == real 2DTE open + slippage."""
    df2 = X.load_dte_contract_bars("SPY250602P00585000", 2)
    real_open = float(df2["open"].iloc[0])
    assert abs(real_open - 1.51) < 0.01, real_open  # real cached open

    spy, _vix = X._load_spy_vix()
    mask = spy["timestamp_et"].dt.date == dt.date(2025, 5, 29)
    gi = int(spy[mask].index[0])
    sg = X.Signal(bar_idx=gi, side="P", stop_level=999.0, note="anchor")
    doc = X._spy_day_open_close(spy)
    fill = X.simulate_dte_trade(sg, spy, {}, doc, 2, strike=585,
                                expiry=dt.date(2025, 6, 2), side="P", qty=3,
                                premium_stop_pct=-0.08, tp1_premium_pct=0.30)
    assert fill is not None
    # entry = next-bar open + entry slippage (0.02) — priced from real bars.
    assert abs(fill.entry_premium - (real_open + X.DEFAULT_ENTRY_SLIPPAGE)) < 0.06, fill.entry_premium
    # it survived to fire the +30% TP1 (the whole point vs 0DTE decay-to-zero).
    assert fill.exit_reason == "TP1_PREMIUM"
    assert fill.dollar_pnl > 0


def test_wr_and_drop_topn_helpers():
    rows = [_Fill("2025-01-02", 100), _Fill("2025-01-02", -50),
            _Fill("2025-01-03", 500), _Fill("2025-01-04", 20),
            _Fill("2025-01-05", -10), _Fill("2025-01-06", 30)]
    assert C.wr(rows) == pytest.approx(66.7, abs=0.1)  # 4 of 6 positive
    # drop the best 3 DAYS (01-03=500, 01-02=50 net, 01-06=30) -> keep 01-04,01-05
    d3 = C.drop_topN_per_trade(rows, 3)
    assert d3 is not None
    # remaining days: 01-04(+20), 01-05(-10) -> mean 5.0
    assert d3 == pytest.approx(5.0, abs=0.01)


def test_oos_split_by_year():
    rows = [_Fill("2025-06-01", 10), _Fill("2026-06-01", 20), _Fill("2026-07-01", 30)]
    o = C.oos_rows(rows)
    assert len(o) == 2  # both 2026
    assert C.exp_per_trade(o) == pytest.approx(25.0)
