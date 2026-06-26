"""Pure leg builders for multi-leg 0DTE SPY credit structures.

Given (spot, structure_type, short_offset, wing_width) return the list of legs
`[Leg(strike, side, qty_sign)]` where qty_sign = -1 short (sell-to-open) /
+1 long (buy-to-open, the protective wing).

NO IO, NO pricing, NO look-ahead — these are deterministic geometry only. The
caller (simulator_credit) loads each leg's OPRA bars and prices the combination.

*** CACHE BAND CONSTRAINT (baked in) ***
The OPRA cache is a FIXED ~$10-wide band: 11 contiguous $1 strikes/side, +/-$5
around ATM. So short strikes are expressed as a $-OFFSET from ATM (NOT a delta
target — we have no Greeks, and the band cannot reach true 16-delta on wide-range
days). Wings are forced NARROW ($1-$3). Any structure whose required strike falls
outside the cached band must be SKIPPED by the caller (band_check() helps).

Strikes are rounded to whole dollars (the cache grid is $1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StructureType = Literal["IC", "PCS", "CCS", "IB", "BWIC"]
Side = Literal["C", "P"]


@dataclass(frozen=True)
class Leg:
    """One option leg of a multi-leg structure.

    strike:   whole-dollar strike (cache grid is $1).
    side:     'C' call / 'P' put.
    qty_sign: -1 short (sell-to-open, collect premium) / +1 long (buy wing).
    """
    strike: int
    side: Side
    qty_sign: int  # -1 short / +1 long

    def __post_init__(self) -> None:
        assert self.side in ("C", "P"), f"side must be C/P, got {self.side}"
        assert self.qty_sign in (-1, 1), f"qty_sign must be +/-1, got {self.qty_sign}"


def _atm(spot: float) -> int:
    return int(round(spot))


def build_legs(
    spot: float,
    structure_type: StructureType,
    short_offset: int,
    wing_width: int,
    *,
    call_short_offset: int | None = None,
    call_wing_width: int | None = None,
) -> list[Leg]:
    """Return the legs for a credit structure.

    Args:
        spot:            underlying SPY price at entry decision.
        structure_type:  IC | PCS | CCS | IB | BWIC.
        short_offset:    $ distance of the (put-side) short strike OUT-of-the-money
                         from ATM. For PCS/IC put wing: short put = ATM - short_offset.
                         For CCS: short call = ATM + short_offset.
                         For IB (iron fly): short strikes sit AT ATM (offset ignored,
                         must be 0 conventionally) — both shorts at ATM, wings at
                         ATM +/- wing_width.
        wing_width:      $ width of the protective wing (long strike is this far
                         FURTHER OTM than the short). Must be >= 1.
        call_short_offset / call_wing_width: optional asymmetric overrides for the
                         CALL side of an IC / BWIC (broken-wing). Default = mirror
                         the put side (symmetric IC).

    Returns legs ordered: put-spread (short then long) then call-spread (short then
    long), so IC = [shortP, longP, shortC, longC].

    Raises ValueError on a non-credit / nonsensical geometry (caught by tests).
    """
    if wing_width < 1:
        raise ValueError(f"wing_width must be >= 1, got {wing_width}")
    if short_offset < 0:
        raise ValueError(f"short_offset must be >= 0, got {short_offset}")
    atm = _atm(spot)

    cso = call_short_offset if call_short_offset is not None else short_offset
    cww = call_wing_width if call_wing_width is not None else wing_width

    if structure_type == "PCS":
        # Bullish put credit spread: sell OTM put, buy further-OTM put.
        short_p = atm - short_offset
        long_p = short_p - wing_width
        return [Leg(short_p, "P", -1), Leg(long_p, "P", +1)]

    if structure_type == "CCS":
        # Bearish call credit spread: sell OTM call, buy further-OTM call.
        short_c = atm + short_offset
        long_c = short_c + wing_width
        return [Leg(short_c, "C", -1), Leg(long_c, "C", +1)]

    if structure_type == "IC":
        # Neutral iron condor: PCS + CCS.
        short_p = atm - short_offset
        long_p = short_p - wing_width
        short_c = atm + cso
        long_c = short_c + cww
        return [
            Leg(short_p, "P", -1), Leg(long_p, "P", +1),
            Leg(short_c, "C", -1), Leg(long_c, "C", +1),
        ]

    if structure_type == "IB":
        # Iron fly / iron butterfly: short straddle at ATM + OTM strangle wings.
        # short_offset is ignored (shorts at ATM); wing_width sets the wings.
        short_p = atm
        long_p = atm - wing_width
        short_c = atm
        long_c = atm + cww
        return [
            Leg(short_p, "P", -1), Leg(long_p, "P", +1),
            Leg(short_c, "C", -1), Leg(long_c, "C", +1),
        ]

    if structure_type == "BWIC":
        # Broken-wing IC: asymmetric — caller supplies call_short_offset/call_wing_width
        # to skew (e.g. wider/further call side to lean bullish or kill the upside tail).
        short_p = atm - short_offset
        long_p = short_p - wing_width
        short_c = atm + cso
        long_c = short_c + cww
        return [
            Leg(short_p, "P", -1), Leg(long_p, "P", +1),
            Leg(short_c, "C", -1), Leg(long_c, "C", +1),
        ]

    raise ValueError(f"unknown structure_type: {structure_type}")


def band_strikes(spot: float, half_width: int = 5) -> set[int]:
    """The cached strike band: ATM +/- half_width whole-dollar strikes.

    The OPRA cache is verified ~$10-wide: 11 contiguous $1 strikes/side centered on
    round(spot). half_width=5 => ATM-5..ATM+5 inclusive (11 strikes). Use this to
    decide whether a structure is priceable BEFORE attempting to load legs.
    """
    atm = _atm(spot)
    return set(range(atm - half_width, atm + half_width + 1))


def legs_in_band(legs: list[Leg], spot: float, half_width: int = 5) -> bool:
    """True iff every leg strike falls inside the cached band for this spot.

    NOTE: this is a NECESSARY (band) check, not SUFFICIENT — a strike may be in the
    nominal band yet have no cached CSV (illiquid). The simulator still verifies the
    CSV exists and SKIPS+logs if a load returns None. This is the cheap pre-filter.
    """
    band = band_strikes(spot, half_width)
    return all(leg.strike in band for leg in legs)


def max_loss_per_contract(wing_width: int, net_credit_per_share: float) -> float:
    """Defined max loss in DOLLARS per 1-lot of a vertical/condor.

    = (wing_width - net_credit_per_share) * 100. For an IC the worst case is ONE
    side fully breached (both can't blow out same day), so wing_width is the single
    side's wing. Caller passes the binding (widest) wing for asymmetric structures.
    """
    return (wing_width - net_credit_per_share) * 100.0
