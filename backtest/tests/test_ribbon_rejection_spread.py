"""Guards for the ribbon-rejection debit-spread battery P&L identities.

These graduate the hand-trace sanity checks (max_loss / max_gain / bounded-pnl)
into code assertions so a future refactor of the spread walker can't silently
break the defined-risk math (C7 / OP-25).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

from autoresearch import ribbon_rejection_spread_battery as sp  # noqa: E402


def _make_master(date: dt.date, spot: float) -> pd.DataFrame:
    """Minimal RTH master with a single entry bar + a few forward bars."""
    rows = []
    base = dt.datetime.combine(date, dt.time(13, 0))
    for k in range(12):
        ts = base + dt.timedelta(minutes=5 * k)
        rows.append({"timestamp_et": pd.Timestamp(ts), "open": spot, "high": spot,
                     "low": spot, "close": spot, "volume": 1000})
    return pd.DataFrame(rows)


class _StubBars:
    """Fake OPRA frame with constant premium so identities are exact."""
    def __init__(self, prem):
        self.prem = prem


def test_qty_and_widths_constants():
    assert sp.QTY == 3
    assert sp.SPREAD_WIDTHS == [2, 3, 5]
    # EOD must be the always-present backstop exit
    assert "EOD" in sp.EXITS
    tp, stop = sp.EXITS["EOD"]
    assert tp is None and stop is None


def test_pnl_identity_max_loss_and_gain(monkeypatch):
    """With a constant long/short premium, verify:
      entry_debit == long-short, max_loss == -debit*100*qty,
      max_gain == (width-debit)*100*qty, and pnl bounded by [max_loss, max_gain].
    """
    date = dt.date(2026, 5, 21)
    spot = 740.0
    spy = _make_master(date, spot)
    width = 3
    long_prem, short_prem = 2.25, 0.63   # debit 1.62 (from the real trace)

    def fake_leg_prem(d, strike, side, ts, cache):
        # long leg (offset 0) is the near-money strike == round(spot)
        return long_prem if strike == round(spot) else short_prem

    def fake_leg_close(d, strike, side, bar_start, cache):
        return long_prem if strike == round(spot) else short_prem

    monkeypatch.setattr(sp, "_leg_premium_at", fake_leg_prem)
    monkeypatch.setattr(sp, "_leg_bar_close", fake_leg_close)

    ev = {"direction": "long", "date": date.isoformat(),
          "ts": spy["timestamp_et"].iloc[0].isoformat(),
          "entry_price": spot, "local_idx": 0}
    r = sp.simulate_spread(ev, spy, width, "EOD", {})
    assert "pnl" in r, r
    debit = r["entry_debit"]
    assert abs(debit - (long_prem - short_prem)) < 1e-6
    assert abs(r["max_loss"] - (-debit * 100 * sp.QTY)) < 0.01
    assert abs(r["max_gain"] - ((width - debit) * 100 * sp.QTY)) < 0.01
    # constant premium => spread value never moves => pnl == 0, bounded
    assert r["max_loss"] - 0.01 <= r["pnl"] <= r["max_gain"] + 0.01


def test_inverted_debit_rejected(monkeypatch):
    """If the far leg fills ABOVE the near leg (bad OPRA cross), debit<=0 and the
    event is flagged opra_miss, never a fabricated fill."""
    date = dt.date(2026, 5, 21)
    spot = 740.0
    spy = _make_master(date, spot)

    def fake_leg_prem(d, strike, side, ts, cache):
        # near-money leg CHEAPER than far leg => inverted => debit <= 0
        return 0.10 if strike == round(spot) else 2.00

    monkeypatch.setattr(sp, "_leg_premium_at", fake_leg_prem)
    ev = {"direction": "long", "date": date.isoformat(),
          "ts": spy["timestamp_et"].iloc[0].isoformat(),
          "entry_price": spot, "local_idx": 0}
    r = sp.simulate_spread(ev, spy, 3, "EOD", {})
    assert r is not None and "opra_miss" in r and r["opra_miss"] == "bad_debit"


def test_missing_leg_flags_opra_miss(monkeypatch):
    date = dt.date(2026, 5, 21)
    spot = 740.0
    spy = _make_master(date, spot)

    def fake_leg_prem(d, strike, side, ts, cache):
        return None  # no OPRA coverage

    monkeypatch.setattr(sp, "_leg_premium_at", fake_leg_prem)
    ev = {"direction": "short", "date": date.isoformat(),
          "ts": spy["timestamp_et"].iloc[0].isoformat(),
          "entry_price": spot, "local_idx": 0}
    r = sp.simulate_spread(ev, spy, 2, "EOD", {})
    assert r is not None and "opra_miss" in r


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
