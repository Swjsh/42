"""Dealer Gamma Exposure (GEX) regime tag — pure, chain-snapshot in, regime out.

WHAT THIS IS (Game Plan 1, Part B — research evidence, propose-only)
--------------------------------------------------------------------
A LEAN, pure-function regime classifier built from the SPY option chain we already
pull via the Alpaca MCP (``mcp__alpaca__get_option_snapshot`` / ``get_option_chain``).
Given ONE chain snapshot (per-strike open-interest + per-contract gamma + spot) it
computes the three numbers the peer-reviewed dealer-gamma literature says actually
carry a regime signal:

  1. **net dealer GEX sign** — is the dealer book net-LONG or net-SHORT gamma right now;
  2. **zero-gamma flip level** — the spot price where net dealer gamma crosses zero
     (above it dealers are typically long-gamma => pinning/mean-reversion; below it
     short-gamma => trend-amplifying hedging into the close);
  3. **nearest call wall / put wall** — the strikes with the largest call-gamma and
     put-gamma concentration (the "magnets"/barriers practitioners watch).

WHY (the edge link, from the game-plan doc + sources)
-----------------------------------------------------
Barbon & Buraschi "Gamma Fragility" + Baltussen et al. (JFE 2021): when dealers are
net-SHORT gamma, their end-of-day delta hedging *amplifies* the prevailing move
(continuation) — which is exactly Gamma's confirmed BEARISH_REJECTION edge regime.
When dealers are net-LONG gamma, hedging *dampens* moves (pinning / mean-reversion) —
a regime where a directional 0DTE continuation trade should size down or abstain.
CBOE's own data says don't believe the "0DTE gamma squeeze moves the market" hype, but
the *regime sign* is real and complementary to VIX/IV. So this is a BIAS/REGIME tag,
never a trigger (Rule 9: propose-only; no live gating without an A/B + anchor check).

THE FORMULA (dealer convention: long calls, short puts)
-------------------------------------------------------
Per-strike gamma exposure, in $ of dealer delta change per 1% move in spot::

    GEX_strike = gamma * OI * 100 * spot^2 * 0.01 * sign

where ``sign = +1`` for calls and ``-1`` for puts (the standard dealer-positioning
convention used by the open-source gex-tracker referenced in the game plan:
https://github.com/Matteo-Ferrara/gex-tracker). ``100`` is the option multiplier;
``spot^2 * 0.01`` converts the per-share, per-$1 gamma into a per-1%-move dollar
notional. Net GEX is the sum across all strikes. The zero-gamma flip is found by
sweeping a candidate spot grid and locating where the (spot-dependent) net GEX
crosses zero, interpolating between the bracketing grid points.

PURITY / SCOPE (deliberately minimal — one module, one test)
------------------------------------------------------------
* No I/O, no network, no clock. Input is a plain list of contract rows (a tiny
  dataclass) the caller builds from whatever the Alpaca MCP returned; output is a
  frozen :class:`GexRegime`. This keeps it trivially testable and decoupled from
  the exact MCP response shape (which the caller adapts via :func:`from_alpaca_snapshot`).
* It is NOT wired into any live path or any params file. It produces a TAG for a
  premarket/heartbeat note to consult, going forward.

BACKTESTING FEASIBILITY — read this before trying to backtest GEX
-----------------------------------------------------------------
We have per-contract OPRA *price* bars (``backtest/data/options/SPY*.csv``) but we do
**NOT** have a historical full-chain *open-interest + gamma* snapshot archive. OI is a
daily end-of-day figure that is not reconstructable from intraday price bars, and the
gamma in those files is not stored either. Therefore **GEX cannot be backtested on our
current data** without fabricating OI/gamma — which would be a fake backtest (the kind
this project bans). This module is positioned as a **LIVE going-forward regime tag**:
to ever backtest it, we must first stand up a daily chain-snapshot capture (persist the
``get_option_chain`` greeks+OI once per day) and accumulate history. See
``assess_backtest_feasibility`` for the machine-readable version of this caveat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

# Option contract multiplier (shares per contract). SPY options are standard 100x.
CONTRACT_MULTIPLIER = 100.0

# Converts per-share, per-$1 gamma into dollar gamma per 1% spot move: spot^2 * 0.01.
ONE_PCT = 0.01


@dataclass(frozen=True)
class GammaContract:
    """One option contract's GEX-relevant fields (immutable).

    The minimal set needed for a dealer-GEX computation. Build a list of these from
    an Alpaca chain snapshot via :func:`from_alpaca_snapshot`, or directly in tests.

    Attributes
    ----------
    strike:
        Strike price in dollars.
    option_type:
        ``"call"`` or ``"put"`` (case-insensitive; ``"C"``/``"P"`` also accepted).
    gamma:
        Per-share option gamma (d-delta / d-spot), as returned in the contract's
        greeks. Typically a small positive number for both calls and puts.
    open_interest:
        Open interest (number of contracts outstanding) at this strike/type.
    """

    strike: float
    option_type: str
    gamma: float
    open_interest: float

    def is_call(self) -> bool:
        t = self.option_type.strip().lower()
        return t in ("call", "c")

    def is_put(self) -> bool:
        t = self.option_type.strip().lower()
        return t in ("put", "p")


@dataclass(frozen=True)
class Wall:
    """A gamma 'wall' — the strike with the largest gamma-notional concentration."""

    strike: float
    gex_notional: float  # absolute dollar gamma at this strike (per 1% move)


@dataclass(frozen=True)
class GexRegime:
    """Computed dealer-gamma regime tag (immutable, JSON-friendly via :meth:`to_dict`).

    Attributes
    ----------
    net_gex:
        Net dealer dollar gamma at the supplied spot, per 1% move (calls +, puts -).
    net_gex_sign:
        ``"long"`` (net_gex > 0), ``"short"`` (net_gex < 0), or ``"flat"`` (== 0).
    regime:
        Human-facing regime label derived from the sign:
        ``"long_gamma_pin"`` (mean-reversion/pinning; directional continuation should
        size down/abstain) or ``"short_gamma_trend"`` (hedging amplifies the move;
        Gamma's continuation edge regime) or ``"flat"``.
    zero_gamma_flip:
        Spot price where net GEX crosses zero, or ``None`` if no crossing exists on
        the searched grid (e.g. all-positive or all-negative across the range).
    call_wall / put_wall:
        Largest call-gamma and put-gamma strikes (the magnets/barriers), or ``None``
        if there are no calls/puts in the chain.
    spot:
        The spot price the net_gex was evaluated at (echoed for traceability).
    n_contracts:
        Number of contracts included after filtering (OI>0, finite gamma).
    """

    net_gex: float
    net_gex_sign: str
    regime: str
    zero_gamma_flip: Optional[float]
    call_wall: Optional[Wall]
    put_wall: Optional[Wall]
    spot: float
    n_contracts: int

    def to_dict(self) -> dict:
        """Plain-dict form for JSON scorecards / state files."""
        return {
            "net_gex": self.net_gex,
            "net_gex_sign": self.net_gex_sign,
            "regime": self.regime,
            "zero_gamma_flip": self.zero_gamma_flip,
            "call_wall": (None if self.call_wall is None
                          else {"strike": self.call_wall.strike,
                                "gex_notional": self.call_wall.gex_notional}),
            "put_wall": (None if self.put_wall is None
                         else {"strike": self.put_wall.strike,
                               "gex_notional": self.put_wall.gex_notional}),
            "spot": self.spot,
            "n_contracts": self.n_contracts,
        }


def _strike_gex(contract: GammaContract, spot: float) -> float:
    """Signed dollar gamma for one contract at ``spot`` (calls +, puts -), per 1% move.

    GEX = gamma * OI * 100 * spot^2 * 0.01 * sign. Returns 0.0 for a non-call/non-put
    type so an unrecognised row cannot silently corrupt the net sum (it is also
    excluded by :func:`_clean_contracts`, this is belt-and-suspenders).
    """
    if contract.is_call():
        sign = 1.0
    elif contract.is_put():
        sign = -1.0
    else:
        return 0.0
    return (
        contract.gamma
        * contract.open_interest
        * CONTRACT_MULTIPLIER
        * (spot ** 2)
        * ONE_PCT
        * sign
    )


def net_gex_at(contracts: Sequence[GammaContract], spot: float) -> float:
    """Net dealer dollar gamma across the chain, evaluated at ``spot`` (per 1% move)."""
    return float(sum(_strike_gex(c, spot) for c in contracts))


def _clean_contracts(contracts: Iterable[GammaContract]) -> list[GammaContract]:
    """Drop rows that cannot contribute signal: non-call/put, OI<=0, non-finite gamma.

    Validating at this boundary (per the input-validation rule) means the rest of the
    module can assume every row is a usable call or put with positive OI.
    """
    import math

    cleaned: list[GammaContract] = []
    for c in contracts:
        if not (c.is_call() or c.is_put()):
            continue
        try:
            oi = float(c.open_interest)
            g = float(c.gamma)
        except (TypeError, ValueError):
            continue
        if oi <= 0 or not math.isfinite(oi):
            continue
        if not math.isfinite(g):
            continue
        cleaned.append(c)
    return cleaned


def _find_zero_gamma_flip(
    contracts: Sequence[GammaContract],
    lo: float,
    hi: float,
    steps: int = 200,
) -> Optional[float]:
    """Locate the spot where net GEX crosses zero on a [lo, hi] grid, interpolating.

    Sweeps ``steps`` evenly-spaced candidate spots, evaluating net GEX at each (gamma
    is held fixed per contract — a first-order regime proxy, not a full re-greeking).
    Returns the linearly-interpolated zero crossing of the FIRST sign change found, or
    ``None`` if net GEX keeps the same sign across the whole range.

    NOTE on the model: because per-contract gamma is treated as constant across the
    sweep (we don't re-price each option at each candidate spot), the spot^2 factor is
    the only spot dependence. With mixed call/put OI the net curve still crosses zero
    where the call/put dollar-gamma balance flips, which is the quantity of interest.
    This is the documented simplification the open-source gex-tracker also makes.
    """
    if hi <= lo or steps < 2:
        return None
    prev_spot = lo
    prev_val = net_gex_at(contracts, lo)
    width = hi - lo
    for i in range(1, steps + 1):
        s = lo + width * i / steps
        v = net_gex_at(contracts, s)
        if prev_val == 0.0:
            return float(prev_spot)
        if v == 0.0:
            return float(s)
        if (prev_val < 0.0) != (v < 0.0):
            # Sign change between prev_spot and s — linear-interpolate the crossing.
            denom = v - prev_val
            if denom == 0.0:
                return float(prev_spot)
            frac = -prev_val / denom
            return float(prev_spot + frac * (s - prev_spot))
        prev_spot, prev_val = s, v
    return None


def _walls(contracts: Sequence[GammaContract], spot: float) -> tuple[Optional[Wall], Optional[Wall]]:
    """Largest call-gamma strike and largest put-gamma strike (absolute notional)."""
    call_by_strike: dict[float, float] = {}
    put_by_strike: dict[float, float] = {}
    for c in contracts:
        notional = abs(_strike_gex(c, spot))
        if c.is_call():
            call_by_strike[c.strike] = call_by_strike.get(c.strike, 0.0) + notional
        elif c.is_put():
            put_by_strike[c.strike] = put_by_strike.get(c.strike, 0.0) + notional

    def _top(d: dict[float, float]) -> Optional[Wall]:
        if not d:
            return None
        strike = max(d, key=lambda k: d[k])
        return Wall(strike=float(strike), gex_notional=round(float(d[strike]), 2))

    return _top(call_by_strike), _top(put_by_strike)


def compute_gex_regime(
    contracts: Iterable[GammaContract],
    spot: float,
    flip_search_pct: float = 0.05,
) -> GexRegime:
    """Compute the dealer-gamma regime tag from a chain snapshot at ``spot``.

    Parameters
    ----------
    contracts:
        Iterable of :class:`GammaContract` (strike, type, gamma, OI). Rows with
        OI<=0, non-finite gamma, or an unrecognised type are dropped.
    spot:
        Current underlying (SPY) price the net GEX is evaluated at.
    flip_search_pct:
        Half-width (fraction of spot) of the grid searched for the zero-gamma flip.
        Default ±5% — wide enough to bracket the flip on a normal SPY chain without
        wandering into illiquid wings.

    Returns
    -------
    GexRegime

    Raises
    ------
    ValueError:
        If ``spot`` is non-positive/non-finite, or the chain has no usable contracts.
    """
    import math

    if not math.isfinite(spot) or spot <= 0:
        raise ValueError(f"spot must be a positive finite price; got {spot!r}.")

    cleaned = _clean_contracts(contracts)
    if not cleaned:
        raise ValueError(
            "No usable contracts after filtering (need >=1 call/put with OI>0 and "
            "finite gamma)."
        )

    net = net_gex_at(cleaned, spot)
    if net > 0:
        sign, regime = "long", "long_gamma_pin"
    elif net < 0:
        sign, regime = "short", "short_gamma_trend"
    else:
        sign, regime = "flat", "flat"

    lo = spot * (1.0 - flip_search_pct)
    hi = spot * (1.0 + flip_search_pct)
    flip = _find_zero_gamma_flip(cleaned, lo, hi)

    call_wall, put_wall = _walls(cleaned, spot)

    return GexRegime(
        net_gex=round(net, 2),
        net_gex_sign=sign,
        regime=regime,
        zero_gamma_flip=(None if flip is None else round(flip, 2)),
        call_wall=call_wall,
        put_wall=put_wall,
        spot=float(spot),
        n_contracts=len(cleaned),
    )


def from_alpaca_snapshot(snapshot: dict, default_spot: Optional[float] = None) -> list[GammaContract]:
    """Adapt an Alpaca option-snapshot dict into a list of :class:`GammaContract`.

    The Alpaca MCP ``get_option_snapshot`` / ``get_option_chain`` returns a mapping of
    OCC option symbol -> snapshot, where each snapshot carries ``greeks.gamma`` and
    ``open_interest`` (or ``openInterest``). Strike + type are parsed from the OCC
    symbol (e.g. ``SPY260501P00721000`` -> put, strike 721.0) when not provided as
    fields. Rows missing gamma/OI are skipped (caller decides whether the chain is
    usable via the resulting list length).

    This adapter is intentionally forgiving about key casing/nesting because the exact
    MCP response shape can vary; it is the ONLY place that knows the wire format, so
    the rest of the module stays pure. ``default_spot`` is unused here (spot is passed
    separately to :func:`compute_gex_regime`) but accepted for call-site symmetry.
    """
    rows = snapshot.get("snapshots", snapshot) if isinstance(snapshot, dict) else {}
    out: list[GammaContract] = []
    if not isinstance(rows, dict):
        return out
    for sym, snap in rows.items():
        if not isinstance(snap, dict):
            continue
        greeks = snap.get("greeks") or snap.get("latestGreeks") or {}
        gamma = greeks.get("gamma") if isinstance(greeks, dict) else None
        oi = snap.get("open_interest", snap.get("openInterest"))
        strike = snap.get("strike_price", snap.get("strike"))
        otype = snap.get("type") or snap.get("option_type")
        if strike is None or otype is None:
            parsed = _parse_occ_symbol(str(sym))
            if parsed is None:
                continue
            otype, strike = parsed
        if gamma is None or oi is None:
            continue
        try:
            out.append(GammaContract(
                strike=float(strike), option_type=str(otype),
                gamma=float(gamma), open_interest=float(oi)))
        except (TypeError, ValueError):
            continue
    return out


def _parse_occ_symbol(sym: str) -> Optional[tuple[str, float]]:
    """Parse an OCC option symbol tail -> (type, strike). e.g. SPY260501P00721000.

    Format: ROOT + YYMMDD + {C,P} + strike*1000 zero-padded to 8 digits. Returns
    ``None`` if the symbol does not match (so the caller skips it).
    """
    # Find the last C or P that is followed by exactly 8 digits at end of string.
    for i in range(len(sym) - 9, -1, -1):
        ch = sym[i]
        if ch in ("C", "P"):
            tail = sym[i + 1:]
            if len(tail) == 8 and tail.isdigit():
                return ("call" if ch == "C" else "put", int(tail) / 1000.0)
    return None


def assess_backtest_feasibility() -> dict:
    """Machine-readable honest verdict on whether GEX can be backtested on our data.

    Returns a dict the scorecard embeds verbatim. Short answer: NO with current data
    (we have OPRA price bars, not a historical OI+gamma full-chain archive); this is a
    LIVE going-forward tag until a daily chain-snapshot capture accumulates history.
    """
    return {
        "can_backtest_now": False,
        "reason": (
            "GEX needs per-strike OPEN INTEREST and per-contract GAMMA across the FULL "
            "chain, as-of each historical day. We have OPRA per-contract PRICE bars "
            "(backtest/data/options/SPY*.csv) only — those files carry no OI and no "
            "stored gamma, and OI (an end-of-day outstanding-contracts figure) is NOT "
            "reconstructable from intraday price bars. Computing historical GEX would "
            "require fabricating OI/gamma, which is a fake backtest (banned)."
        ),
        "what_we_have": "OPRA per-contract 5m PRICE bars (strike-level, no OI/gamma).",
        "what_is_missing": "Daily full-chain OI + gamma snapshots, as-of each day.",
        "path_to_backtestable": (
            "Stand up a once-per-day capture that persists get_option_chain greeks+OI "
            "(a small JSONL/parquet per day), accumulate >= a few months, THEN a GEX "
            "backtest becomes possible. Until then gex_regime.py is a LIVE "
            "premarket/heartbeat regime TAG, computed from the current chain forward."
        ),
        "position": "LIVE-going-forward regime tag (propose-only; NOT a trigger, NOT gated live).",
    }
