"""Black-Scholes pricing, implied-volatility solve, and delta — stdlib only.

WHY THIS EXISTS: the frozen expiry pre-registration
(analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json) requires strikes to
be DELTA-matched across arms, not strike-matched — the same strike is a different delta at
different DTE, so strike-matching would confound "which expiry" with "how far out of the
money," which is a different question entirely.

The cached weekly option bars carry no greeks, so delta has to be derived: solve implied vol
from the contract's own observed price, then compute delta at that vol. Using a single assumed
vol across arms would defeat the purpose, since term structure is exactly what differs.

No scipy: the normal CDF comes from math.erf, and the IV solve uses BISECTION rather than
Newton-Raphson. Bisection is slower but cannot diverge — Newton fails badly on deep OTM
contracts where vega approaches zero, which is precisely the population where a silent bad
solve would corrupt strike selection.

Rate: a single risk-free rate is passed in by the caller (Fed funds was 3.50-3.75% as of
2026-08-18). Dividend yield matters for GLD (none) vs equity ETFs (QQQ pays ~0.5%); the caller
supplies it rather than this module guessing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Bisection bounds. 1000% vol is far outside anything real; if the solve pins to the ceiling
# the price is not explicable by Black-Scholes and the caller must be told, not handed a number.
_IV_LO = 1e-4
_IV_HI = 10.0
_IV_TOL = 1e-6
_MAX_ITER = 200

# Minimum vega (dPrice/dVol, per 1.0 of vol) for an implied vol to be IDENTIFIABLE at all.
# Where vega approaches zero -- deep ITM or deep OTM, especially at low vol and short DTE --
# a wide range of vols produce the SAME price to within a penny, so "the" implied vol does not
# exist as a well-posed quantity. Returning a number there would be fabrication: the solver
# would hand back whatever the bisection happened to land on, and the delta computed from it
# would select the wrong strike with no downstream statistic able to notice.
# Calibration: a genuinely tradeable ATM weekly runs vega ~30; this floor is far below any
# real candidate and far above the degenerate cases.
_MIN_VEGA_IDENTIFIABLE = 0.05


class OptionMathError(ValueError):
    """Raised on inputs Black-Scholes cannot price, so a bad solve fails loud."""


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    implied_vol: float
    d1: float
    d2: float


def _validate(spot: float, strike: float, t_years: float, right: str) -> str:
    if spot <= 0:
        raise OptionMathError(f"spot must be > 0 (got {spot})")
    if strike <= 0:
        raise OptionMathError(f"strike must be > 0 (got {strike})")
    if t_years <= 0:
        raise OptionMathError(
            f"t_years must be > 0 (got {t_years}); an expired contract has no BS value — "
            f"the caller must handle expiry separately rather than pricing it"
        )
    r = right.upper()[:1]
    if r not in ("C", "P"):
        raise OptionMathError(f"right must be call/put (got {right!r})")
    return r


def bs_price(spot: float, strike: float, t_years: float, vol: float, right: str,
             *, rate: float = 0.036, div_yield: float = 0.0) -> float:
    r = _validate(spot, strike, t_years, right)
    if vol <= 0:
        raise OptionMathError(f"vol must be > 0 (got {vol})")
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    disc_r = math.exp(-rate * t_years)
    disc_q = math.exp(-div_yield * t_years)
    if r == "C":
        return spot * disc_q * _norm_cdf(d1) - strike * disc_r * _norm_cdf(d2)
    return strike * disc_r * _norm_cdf(-d2) - spot * disc_q * _norm_cdf(-d1)


def bs_vega(spot: float, strike: float, t_years: float, vol: float, right: str,
            *, rate: float = 0.036, div_yield: float = 0.0) -> float:
    """dPrice/dVol per 1.0 of vol. Identical for calls and puts (put-call parity)."""
    _validate(spot, strike, t_years, right)
    if vol <= 0:
        raise OptionMathError(f"vol must be > 0 (got {vol})")
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / (vol * sqrt_t)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return spot * math.exp(-div_yield * t_years) * pdf * sqrt_t


def bs_delta(spot: float, strike: float, t_years: float, vol: float, right: str,
             *, rate: float = 0.036, div_yield: float = 0.0) -> float:
    r = _validate(spot, strike, t_years, right)
    if vol <= 0:
        raise OptionMathError(f"vol must be > 0 (got {vol})")
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / (vol * sqrt_t)
    disc_q = math.exp(-div_yield * t_years)
    return disc_q * _norm_cdf(d1) if r == "C" else -disc_q * _norm_cdf(-d1)


def implied_vol(price: float, spot: float, strike: float, t_years: float, right: str,
                *, rate: float = 0.036, div_yield: float = 0.0) -> float:
    """Solve IV by bisection. Raises rather than returning a bound when the price is
    outside what Black-Scholes can produce (arbitrage-violating or stale quote)."""
    r = _validate(spot, strike, t_years, right)
    if price <= 0:
        raise OptionMathError(f"price must be > 0 (got {price})")

    # No-arbitrage bounds. A price outside these is not a vol problem — it is a bad quote,
    # and silently clamping it would hand back a fabricated vol.
    disc_r = math.exp(-rate * t_years)
    disc_q = math.exp(-div_yield * t_years)
    if r == "C":
        lo_bound = max(0.0, spot * disc_q - strike * disc_r)
        hi_bound = spot * disc_q
    else:
        lo_bound = max(0.0, strike * disc_r - spot * disc_q)
        hi_bound = strike * disc_r
    if price < lo_bound - 1e-9 or price > hi_bound + 1e-9:
        raise OptionMathError(
            f"price {price:.4f} is outside the no-arbitrage band "
            f"[{lo_bound:.4f}, {hi_bound:.4f}] for {right} K={strike} S={spot} T={t_years:.4f} — "
            f"refusing to fabricate an implied vol from an impossible quote"
        )

    lo, hi = _IV_LO, _IV_HI
    if bs_price(spot, strike, t_years, hi, r, rate=rate, div_yield=div_yield) < price:
        raise OptionMathError(
            f"price {price:.4f} exceeds the BS value at {_IV_HI:.0%} vol — not solvable"
        )
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        val = bs_price(spot, strike, t_years, mid, r, rate=rate, div_yield=div_yield)
        if abs(val - price) < _IV_TOL or (hi - lo) < _IV_TOL:
            # MUST go through _checked: an early return here would bypass the vega
            # identifiability guard on the convergent path, which is the COMMON path --
            # leaving the guard live only for non-converging solves. (Caught by the
            # round-trip test, 2026-08-18: a vega=0.0026 contract solved "successfully".)
            return _checked(mid, spot, strike, t_years, r, rate, div_yield)
        if val < price:
            lo = mid
        else:
            hi = mid
    return _checked(0.5 * (lo + hi), spot, strike, t_years, r, rate, div_yield)


def _checked(vol: float, spot: float, strike: float, t_years: float, right: str,
             rate: float, div_yield: float) -> float:
    """Reject a solved vol that sits in a vega dead zone — see _MIN_VEGA_IDENTIFIABLE."""
    vega = bs_vega(spot, strike, t_years, vol, right, rate=rate, div_yield=div_yield)
    if vega < _MIN_VEGA_IDENTIFIABLE:
        raise OptionMathError(
            f"implied vol is UNIDENTIFIABLE for {right} K={strike} S={spot} "
            f"T={t_years:.4f}: vega {vega:.2e} < {_MIN_VEGA_IDENTIFIABLE}. A wide range of "
            f"vols reprice this contract identically, so any returned value would be "
            f"fabricated — and a delta derived from it would select the wrong strike."
        )
    return vol


def solve_greeks(price: float, spot: float, strike: float, t_years: float, right: str,
                 *, rate: float = 0.036, div_yield: float = 0.0) -> Greeks:
    """IV from the observed price, then delta at that IV — the delta-matching primitive."""
    vol = implied_vol(price, spot, strike, t_years, right, rate=rate, div_yield=div_yield)
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / (vol * sqrt_t)
    return Greeks(
        price=price,
        delta=bs_delta(spot, strike, t_years, vol, right, rate=rate, div_yield=div_yield),
        implied_vol=vol,
        d1=d1,
        d2=d1 - vol * sqrt_t,
    )


def pick_delta_matched(candidates: list[dict], target_delta: float, *,
                       spot: float, t_years: float, right: str,
                       rate: float = 0.036, div_yield: float = 0.0) -> dict | None:
    """From [{'strike':..., 'price':...}], pick the contract whose |delta| is nearest target.

    Contracts whose price cannot be solved (stale/arbitrage-violating quotes) are SKIPPED and
    counted, never silently priced with a fallback vol — a fabricated delta would land the
    experiment on the wrong strike and no downstream statistic could detect it.
    """
    best, best_err, skipped = None, float("inf"), 0
    for c in candidates:
        try:
            g = solve_greeks(float(c["price"]), spot, float(c["strike"]), t_years, right,
                             rate=rate, div_yield=div_yield)
        except OptionMathError:
            skipped += 1
            continue
        err = abs(abs(g.delta) - abs(target_delta))
        if err < best_err:
            best, best_err = {**c, "delta": g.delta, "implied_vol": g.implied_vol,
                              "delta_err": err}, err
    if best is not None:
        best["candidates_skipped_unsolvable"] = skipped
        best["candidates_considered"] = len(candidates)
    return best
