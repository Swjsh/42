"""Black-Scholes for ATM 0DTE option premium estimation.

Real 0DTE option fills depend on bid-ask spread, dealer positioning, gamma effects,
implied volatility skew, and theta acceleration in the last hour. We don't model any
of that. We model the directional + time-decay component, which is enough to answer
"does this setup produce profitable directional plays?"

Approach:
  - Strike = round(SPY, $1) — approximates ATM behavior
  - IV proxy = VIX / 100 — actual ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime
  - Risk-free rate = 4% (current US 3M T-bill range; 0DTE is barely sensitive to this anyway)
  - Time to expiry = (16:00 ET - current bar timestamp) / (365.25 * 24 * 60)
                    minutes-to-close in years for the BS formula

Output: (premium, delta) at any (spot, strike, time-to-expiry, vix).
Both call and put supported but the playbook is puts-only for v1.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


RISK_FREE_RATE = 0.04
MARKET_CLOSE_HOUR = 16  # 16:00 ET expiry for 0DTE
MIN_TIME_TO_EXPIRY = 1.0 / (365.25 * 24 * 60)  # 1 minute floor — avoid div-by-zero


@dataclass(frozen=True)
class OptionQuote:
    """Snapshot of an option at a moment."""
    spot: float
    strike: float
    iv: float           # decimal (0.18 = 18%)
    time_to_expiry_years: float
    is_call: bool
    premium: float
    delta: float


def time_to_expiry_years(now_et: dt.datetime) -> float:
    """Fractional years until 16:00 ET on `now_et.date()`. Floors at 1 minute."""
    expiry = now_et.replace(hour=MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    if now_et >= expiry:
        return MIN_TIME_TO_EXPIRY
    seconds_to_close = (expiry - now_et).total_seconds()
    return max(MIN_TIME_TO_EXPIRY, seconds_to_close / (365.25 * 24 * 60 * 60))


def vix_to_iv(vix: float) -> float:
    """Convert VIX (e.g., 17.30) to decimal IV (0.173). Floors at 5%, caps at 200%."""
    iv = vix / 100.0
    return max(0.05, min(2.0, iv))


def black_scholes(
    spot: float,
    strike: float,
    iv: float,
    time_to_expiry: float,
    is_call: bool,
    rate: float = RISK_FREE_RATE,
) -> tuple[float, float]:
    """Vanilla European Black-Scholes. Returns (price, delta)."""
    if time_to_expiry <= 0 or iv <= 0:
        # At expiry: option = max(S - K, 0) for call, max(K - S, 0) for put
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        delta = (1.0 if spot > strike else 0.0) if is_call else (-1.0 if spot < strike else 0.0)
        return intrinsic, delta

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * time_to_expiry) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t

    if is_call:
        price = spot * norm.cdf(d1) - strike * math.exp(-rate * time_to_expiry) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = strike * math.exp(-rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1.0  # put delta is negative
    return float(price), float(delta)


def price_atm_put(spot: float, vix: float, now_et: dt.datetime) -> OptionQuote:
    """Quote ATM 0DTE put: strike = round(spot, $1), IV from VIX, time = bar→16:00 ET."""
    strike = round(spot)
    iv = vix_to_iv(vix)
    tte = time_to_expiry_years(now_et)
    premium, delta = black_scholes(spot, strike, iv, tte, is_call=False)
    return OptionQuote(
        spot=spot, strike=strike, iv=iv, time_to_expiry_years=tte,
        is_call=False, premium=premium, delta=delta,
    )


def price_atm_call(spot: float, vix: float, now_et: dt.datetime) -> OptionQuote:
    """Quote ATM 0DTE call (symmetric to put)."""
    strike = round(spot)
    iv = vix_to_iv(vix)
    tte = time_to_expiry_years(now_et)
    premium, delta = black_scholes(spot, strike, iv, tte, is_call=True)
    return OptionQuote(
        spot=spot, strike=strike, iv=iv, time_to_expiry_years=tte,
        is_call=True, premium=premium, delta=delta,
    )
