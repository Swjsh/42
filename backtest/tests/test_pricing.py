"""Black-Scholes pricing — sanity checks against known properties."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import pytest
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.pricing import (  # noqa: E402
    black_scholes,
    price_atm_call,
    price_atm_put,
    time_to_expiry_years,
    vix_to_iv,
)


ET = pytz.timezone("America/New_York")


def test_vix_to_iv():
    assert vix_to_iv(17.30) == pytest.approx(0.173)
    assert vix_to_iv(0) == pytest.approx(0.05)  # floored
    assert vix_to_iv(300) == pytest.approx(2.0)  # capped


def test_time_to_expiry_at_open():
    """At 09:30 ET, 6.5 hours to 16:00 → ~6.5/(24*365.25) years."""
    bar = ET.localize(dt.datetime(2026, 5, 6, 9, 30))
    tte = time_to_expiry_years(bar)
    expected = 6.5 / (365.25 * 24)
    assert tte == pytest.approx(expected, rel=1e-3)


def test_time_to_expiry_after_close_floored():
    """After 16:00 ET we floor at 1 minute, not zero."""
    bar = ET.localize(dt.datetime(2026, 5, 6, 16, 30))
    assert time_to_expiry_years(bar) == pytest.approx(1.0 / (365.25 * 24 * 60))


def test_atm_put_has_negative_delta():
    """ATM 0DTE put delta should be near -0.5."""
    bar = ET.localize(dt.datetime(2026, 5, 6, 10, 30))
    q = price_atm_put(spot=720.0, vix=17.30, now_et=bar)
    assert q.is_call is False
    assert q.strike == 720
    assert -0.7 < q.delta < -0.3


def test_atm_call_has_positive_delta():
    bar = ET.localize(dt.datetime(2026, 5, 6, 10, 30))
    q = price_atm_call(spot=720.0, vix=17.30, now_et=bar)
    assert q.is_call is True
    assert 0.3 < q.delta < 0.7


def test_premium_decays_with_time():
    """Same spot/IV, less time-to-expiry → cheaper option."""
    early = ET.localize(dt.datetime(2026, 5, 6, 9, 30))
    late = ET.localize(dt.datetime(2026, 5, 6, 15, 30))
    p_early = price_atm_put(720.0, 17.30, early).premium
    p_late = price_atm_put(720.0, 17.30, late).premium
    assert p_early > p_late, f"theta decay broken: 09:30 ${p_early:.2f} vs 15:30 ${p_late:.2f}"


def test_atm_put_premium_in_reasonable_range():
    """At 09:30, VIX 17, $720 SPY ATM put should be roughly $1-2 (range check, not exact)."""
    bar = ET.localize(dt.datetime(2026, 5, 6, 9, 30))
    q = price_atm_put(720.0, 17.30, bar)
    assert 0.5 < q.premium < 5.0, f"ATM 0DTE put premium {q.premium:.2f} out of expected range"


def test_put_in_the_money_when_spot_drops():
    """If spot drops $5 vs strike, put should be worth at least the intrinsic."""
    bar = ET.localize(dt.datetime(2026, 5, 6, 12, 0))
    spot = 720.0
    drop_spot = spot - 5.0  # 715
    q_atm = price_atm_put(spot, 17.30, bar)
    # Re-price the same strike (720) with new spot 715 — should be worth at least $5 intrinsic.
    from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv
    tte = time_to_expiry_years(bar)
    p_dropped, _ = black_scholes(drop_spot, q_atm.strike, vix_to_iv(17.30), tte, is_call=False)
    assert p_dropped >= 5.0, f"Put with spot $5 below strike worth ${p_dropped:.2f}, expected >= $5"


def test_put_call_parity_approx():
    """C - P = S - K * exp(-rT) at the same strike. Approximate check."""
    bar = ET.localize(dt.datetime(2026, 5, 6, 11, 0))
    spot = 720.0
    strike = 720
    iv = 0.173
    tte = time_to_expiry_years(bar)
    c_price, _ = black_scholes(spot, strike, iv, tte, is_call=True)
    p_price, _ = black_scholes(spot, strike, iv, tte, is_call=False)
    import math
    parity_check = spot - strike * math.exp(-0.04 * tte)
    diff = (c_price - p_price) - parity_check
    assert abs(diff) < 0.01, f"put-call parity violated: C-P={c_price-p_price:.4f} vs S-Ke^-rT={parity_check:.4f}"
