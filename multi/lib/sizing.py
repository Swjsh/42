"""multi/lib/sizing.py — contracts + strike sizing for the multi-symbol lane.

FORKED FROM (not imported from — J directive 2026-08-19: copy, don't touch the
original):
  * `backtest/lib/risk_gate.py`'s fail-closed input-hygiene helpers
    (`_is_bad_number`), its `Allow`/`Deny`-shaped frozen-dataclass result pattern,
    and its cap math (`notional = premium * qty * 100`, `min_contracts` floor).
  * `automation/state/fleet/fleet_executor.py`'s shrink-not-deny sizing shape
    (`_shrink_qty_to_affordable` / `max_affordable_qty` — the "pick the largest
    legal qty under the cap" idea), extended here to also net out capital already
    committed by other open positions in this book.
  * `crypto/lib/strike_selection.py`'s tier-offset walk (`pick_strike`,
    `moneyness`) — reused for the OFFSET ARITHMETIC ONLY. Its anchor
    (`atm_strike(spot) -> int(round(spot))`) is NOT reused: that assumes $1-wide
    strikes, true for SPY/QQQ, false for most single names (many strike at $2.50
    or $5 rungs at higher prices, $0.50 at low prices). `select_strike` below
    always walks the LIVE LISTED CHAIN the caller supplies; it can never return a
    strike that isn't actually listed.

WHY THIS FILE IS SYMBOL-GENERIC
--------------------------------
Every function takes `symbol`/`spot`/`available_strikes` explicitly. Nothing here
assumes SPY, a $1 strike grid, or a single open position at a time — this lane
runs up to `risk.max_concurrent_positions` across `entry.max_concurrent_symbols`
(see multi/lib/risk.py for the admission gates that enforce those counts;
sizing.py answers "how many contracts / which strike", never "may we enter at
all" — that split mirrors risk_gate.check_order vs fleet_executor's tiered qty
selection, which are also two separate concerns in the source material).

MULTI-DAY CAPITAL ACCOUNTING (the one thing genuinely new here)
-----------------------------------------------------------------
The SPY engine (and the fleet arms forked from it) size every trade against a
FRESH book: one position at a time, flat before entry (risk_gate's NOT_FLAT
rule). This lane holds MULTIPLE positions across MULTIPLE days
(`exits.days_to_live` = 3 in params.json) — a sizing calc that only looks at
`equity * per_trade_risk_cap_pct` for a NEW entry, ignoring capital already tied
up in standing positions, would let the book overcommit. `size_entry` below nets
out `committed_notional(open_positions)` from equity before applying the
per-trade cap.

FAIL-CLOSED ON MALFORMED POSITIONS (load-bearing — J directive 2026-08-19)
------------------------------------------------------------------------------
`committed_notional` raises `MalformedPositionError` the moment ANY open
position cannot be read confidently (missing/blank symbol, unreadable/
non-positive qty or entry premium). It does NOT skip the bad row and keep
summing the rest — treating an unreadable position as "$0 committed"
UNDERSTATES exposure and OVERSTATES affordability, which is failing OPEN in
the exact direction that lets the book over-commit. `size_entry` catches that
exception and returns a `SizingResult(allowed=False, code=CODE_UNREADABLE_POSITION,
...)` — i.e. "cannot size a new entry right now", never "proceed as if nothing
were committed."
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


# --- Stable decision codes (public contract) ----------------------------------
CODE_ALLOW = "ALLOW"
CODE_UNREADABLE_INPUT = "UNREADABLE_INPUT"
CODE_UNREADABLE_POSITION = "UNREADABLE_POSITION"
CODE_MIN_CONTRACTS = "MIN_CONTRACTS"
CODE_NO_CAPITAL_REMAINING = "NO_CAPITAL_REMAINING"
CODE_SELECTED = "SELECTED"
CODE_NO_LISTED_STRIKE = "NO_LISTED_STRIKE"


class MalformedPositionError(RuntimeError):
    """Raised loudly by `committed_notional` when an open position cannot be read
    confidently. Callers MUST treat this as "cannot size a new entry right now" —
    NEVER as permission to treat the position as $0 committed. See module
    docstring "FAIL-CLOSED ON MALFORMED POSITIONS"."""


@dataclass(frozen=True)
class SizingResult:
    """Result of `size_entry`. Use `.allowed` or `bool(result)`."""

    allowed: bool
    code: str
    reason: str
    contracts: int = 0
    committed_notional: Optional[float] = None
    available_notional: Optional[float] = None
    effective_cap_dollars: Optional[float] = None

    def __bool__(self) -> bool:
        return self.allowed


@dataclass(frozen=True)
class StrikeSelection:
    """Result of `select_strike`. Use `.ok` or `bool(result)`."""

    ok: bool
    code: str
    reason: str
    strike: Optional[float] = None
    anchor_strike: Optional[float] = None
    listed_strikes_count: Optional[int] = None

    def __bool__(self) -> bool:
        return self.ok


# --- input-hygiene helpers (forked verbatim from risk_gate.py's fail-closed core) ---

def _is_bad_number(x: Any) -> bool:
    """True when x cannot be trusted as a finite real number. See
    backtest/lib/risk_gate.py's identical helper for the full rationale (None,
    bool, NaN/inf, and unparseable strings are all "bad")."""
    if x is None:
        return True
    if isinstance(x, bool):
        return True
    if isinstance(x, (int, float)):
        return math.isnan(x) or math.isinf(x)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return True
    return math.isnan(v) or math.isinf(v)


def _as_float(x: Any) -> float:
    """Parse to float. Caller MUST have screened with _is_bad_number first."""
    return float(x)


def _risk_block(params: Mapping[str, Any]) -> Mapping[str, Any]:
    """params.json nests sizing knobs under a `risk` block (see
    automation/state/multi/params.json). Falls back to the top-level mapping so a
    flat params dict (as tests often pass) also works."""
    risk = params.get("risk")
    return risk if isinstance(risk, Mapping) else params


# --- committed-capital accounting (multi-day, multi-symbol book) --------------

def committed_notional(
    open_positions: Optional[Sequence[Mapping[str, Any]]],
) -> float:
    """Sum the capital committed by every OPEN position in the book.

    For long-premium-only options (params.json entry.structure ==
    "long_premium_only"), the debit paid at entry IS the capital committed — a
    long option has no margin call, so max loss/capital-at-risk is exactly
    entry_premium * qty * 100 per position, regardless of current mark. Using the
    ENTRY premium (not a live mark) is deliberate: it answers "how much of the
    account's capital is already spoken for", not "what is the position worth
    right now" (that second question is the kill-switch's job, and it must be
    answered from REALIZED P&L only — see risk.py).

    FAIL CLOSED: raises `MalformedPositionError` on the FIRST position that is
    not a mapping, or is missing/has an unreadable `symbol`, `qty`, or
    `premium_entry`. See module docstring.

    `open_positions=None` or `[]` -> 0.0 (an empty book has nothing committed;
    this is the ONE legitimate way to get a $0 answer — not through a skipped
    bad row).
    """
    if not open_positions:
        return 0.0
    total = 0.0
    for i, pos in enumerate(open_positions):
        if not isinstance(pos, Mapping):
            raise MalformedPositionError(
                f"open_positions[{i}] is not a mapping ({pos!r}) — refusing to "
                f"treat it as $0 committed"
            )
        symbol = pos.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise MalformedPositionError(
                f"open_positions[{i}] missing/blank 'symbol' ({symbol!r})"
            )
        qty = pos.get("qty")
        premium_entry = pos.get("premium_entry")
        if _is_bad_number(qty):
            raise MalformedPositionError(
                f"open_positions[{i}] ({symbol}) has unreadable qty ({qty!r})"
            )
        if _is_bad_number(premium_entry):
            raise MalformedPositionError(
                f"open_positions[{i}] ({symbol}) has unreadable premium_entry "
                f"({premium_entry!r})"
            )
        qty_f = _as_float(qty)
        prem_f = _as_float(premium_entry)
        if qty_f <= 0 or qty_f != int(qty_f):
            raise MalformedPositionError(
                f"open_positions[{i}] ({symbol}) qty must be a positive whole "
                f"number (got {qty!r})"
            )
        if prem_f <= 0:
            raise MalformedPositionError(
                f"open_positions[{i}] ({symbol}) premium_entry must be > 0 "
                f"(got {premium_entry!r})"
            )
        total += prem_f * int(qty_f) * 100.0
    return total


# --- contracts sizing -----------------------------------------------------------

def size_entry(
    *,
    symbol: Any,
    equity: Any,
    premium: Any,
    params: Optional[Mapping[str, Any]],
    open_positions: Optional[Sequence[Mapping[str, Any]]] = None,
) -> SizingResult:
    """Compute contracts for ONE new entry in `symbol`.

    Honors:
      * `risk.per_trade_risk_cap_pct * equity` — the per-trade dollar cap
        (mirrors risk_gate.check_order's RISK_CAP rule, symbol-generic).
      * `risk.min_contracts` — Rule 6 floor (>= 2 TP + 1 runner). A max-affordable
        qty below the floor is a deny, never a silent round-up (matches
        risk_gate/fleet_executor: this module does not invent liquidity).
      * Capital ALREADY COMMITTED by other open positions in this book
        (`committed_notional`) — narrows `available = equity - committed`, and
        the EFFECTIVE cap for this order is `min(per_trade_cap, available)`. A
        fresh-book calc that ignores standing positions is wrong on a multi-day
        book (see module docstring).

    Returns the LARGEST legal qty (shrink-not-deny, per fleet_executor's proven
    pattern) rather than a fixed tier size — a fixed tier can price itself out of
    its own opportunity set exactly as fleet_executor.py's own history documents.

    FAIL CLOSED: unreadable symbol/equity/premium/params, unreadable
    `risk.per_trade_risk_cap_pct` / `risk.min_contracts`, a malformed open
    position (via `committed_notional`), or a book with no capital remaining ->
    `allowed=False`, `contracts=0`.
    """
    if params is None or not isinstance(params, Mapping):
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             "params missing or not a mapping")
    if not isinstance(symbol, str) or not symbol.strip():
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             f"symbol missing/blank ({symbol!r})")
    if _is_bad_number(equity) or _as_float(equity) <= 0:
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             f"equity must be a readable number > 0 (got {equity!r})")
    if _is_bad_number(premium) or _as_float(premium) <= 0:
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             f"premium must be a readable number > 0 (got {premium!r})")
    equity_f = _as_float(equity)
    premium_f = _as_float(premium)

    risk = _risk_block(params)
    cap_pct_raw = risk.get("per_trade_risk_cap_pct")
    min_contracts_raw = risk.get("min_contracts")
    if _is_bad_number(cap_pct_raw):
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             "params.risk.per_trade_risk_cap_pct missing/unreadable")
    if _is_bad_number(min_contracts_raw):
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             "params.risk.min_contracts missing/unreadable")
    cap_pct = _as_float(cap_pct_raw)
    min_contracts = int(_as_float(min_contracts_raw))
    if cap_pct <= 0:
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             f"params.risk.per_trade_risk_cap_pct must be > 0 (got {cap_pct})")
    if min_contracts <= 0:
        return SizingResult(False, CODE_UNREADABLE_INPUT,
                             f"params.risk.min_contracts must be > 0 (got {min_contracts})")

    try:
        committed = committed_notional(open_positions)
    except MalformedPositionError as exc:
        return SizingResult(False, CODE_UNREADABLE_POSITION,
                             f"cannot size a new {symbol} entry: {exc}")

    per_trade_cap = equity_f * cap_pct
    available = equity_f - committed
    if available <= 0:
        return SizingResult(
            False, CODE_NO_CAPITAL_REMAINING,
            f"{symbol}: no capital remaining — equity ${equity_f:,.2f} - "
            f"committed ${committed:,.2f} <= 0",
            committed_notional=committed, available_notional=available,
        )

    effective_cap = min(per_trade_cap, available)
    per_contract = premium_f * 100.0
    max_qty = int(effective_cap // per_contract)
    if max_qty < min_contracts:
        return SizingResult(
            False, CODE_MIN_CONTRACTS,
            f"{symbol}: max affordable {max_qty} contract(s) < min_contracts "
            f"{min_contracts} (effective cap ${effective_cap:,.2f} = min(per-trade "
            f"${per_trade_cap:,.2f}, available ${available:,.2f}) at ${premium_f:.2f}/contract)",
            committed_notional=committed, available_notional=available,
            effective_cap_dollars=effective_cap,
        )

    return SizingResult(
        True, CODE_ALLOW,
        f"{symbol}: {max_qty} contracts @ ${premium_f:.2f} = "
        f"${max_qty * per_contract:,.2f} within effective cap ${effective_cap:,.2f}",
        contracts=max_qty, committed_notional=committed, available_notional=available,
        effective_cap_dollars=effective_cap,
    )


# --- strike selection from the LIVE LISTED CHAIN (the SPY-coupling fix) -------
#
# crypto/lib/strike_selection.atm_strike(spot) = int(round(spot)) silently assumes
# $1-wide strikes. That is TRUE for SPY/QQQ and FALSE for most single names: e.g.
# a $2.50 or $5 rung at higher prices, a $0.50 rung at low prices. Rounding spot
# to the nearest dollar for, say, a $187.30 stock with $2.50-wide strikes
# ($185/$187.50/$190/...) returns 187 — NOT A LISTED STRIKE. Placing an order at
# an unlisted strike is not "slightly wrong pricing", it is an order the chain
# cannot fill. `select_strike` below NEVER computes a strike by dollar rounding —
# it always walks `available_strikes`, the caller's live chain read, so its
# return value is provably a member of that sequence.

def select_strike(
    *,
    symbol: Any,
    spot: Any,
    side: Any,
    available_strikes: Optional[Sequence[Any]],
    tier_offset: int = 0,
) -> StrikeSelection:
    """Pick a LISTED strike near `spot`, walked `tier_offset` rungs through the
    live chain (0 = nearest-to-spot / "ATM"; sign convention matches
    crypto/lib/strike_selection.pick_strike — POSITIVE = ITM, NEGATIVE = OTM;
    BEAR puts walk the index UP, BULL calls walk it DOWN, mirroring that file's
    `atm + offset` / `atm - offset` formula but applied to a SORTED INDEX of
    LISTED strikes rather than dollar arithmetic on price).

    The anchor ("ATM") is the LISTED strike closest to spot — never an unlisted
    round number. Ties (spot exactly equidistant between two listed strikes)
    break toward the LOWER strike, a deterministic and disclosed choice.

    FAIL CLOSED: missing/empty `available_strikes`, an unreadable `spot`, a bad
    `side`, or a `tier_offset` that walks off either end of the listed chain ->
    `ok=False`. This function never guesses a strike that isn't listed.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        return StrikeSelection(False, CODE_UNREADABLE_INPUT,
                                f"symbol missing/blank ({symbol!r})")
    if side not in ("C", "P"):
        return StrikeSelection(False, CODE_UNREADABLE_INPUT,
                                f"side must be 'C' or 'P' (got {side!r})")
    if _is_bad_number(spot) or _as_float(spot) <= 0:
        return StrikeSelection(False, CODE_UNREADABLE_INPUT,
                                f"spot must be a readable number > 0 (got {spot!r})")
    spot_f = _as_float(spot)

    if not available_strikes:
        return StrikeSelection(False, CODE_NO_LISTED_STRIKE,
                                f"{symbol}: no strikes supplied by the live chain read")

    parsed = []
    for raw in available_strikes:
        if _is_bad_number(raw):
            continue
        v = _as_float(raw)
        if v > 0:
            parsed.append(v)
    if not parsed:
        return StrikeSelection(False, CODE_NO_LISTED_STRIKE,
                                f"{symbol}: none of the {len(available_strikes)} supplied "
                                f"strikes were readable positive numbers")

    listed = sorted(set(parsed))
    # Anchor = listed strike closest to spot; ties -> lower strike (deterministic).
    anchor_idx = min(
        range(len(listed)),
        key=lambda i: (abs(listed[i] - spot_f), listed[i]),
    )

    try:
        offset_i = int(tier_offset)
    except (TypeError, ValueError):
        return StrikeSelection(False, CODE_UNREADABLE_INPUT,
                                f"tier_offset must be an integer (got {tier_offset!r})")

    idx = anchor_idx + offset_i if side == "P" else anchor_idx - offset_i
    if idx < 0 or idx >= len(listed):
        return StrikeSelection(
            False, CODE_NO_LISTED_STRIKE,
            f"{symbol}: tier_offset {tier_offset} from anchor {listed[anchor_idx]} "
            f"walks off the listed chain ({len(listed)} strikes, "
            f"{listed[0]}-{listed[-1]})",
            anchor_strike=listed[anchor_idx], listed_strikes_count=len(listed),
        )

    chosen = listed[idx]
    return StrikeSelection(
        True, CODE_SELECTED,
        f"{symbol}: selected strike {chosen} (anchor {listed[anchor_idx]}, "
        f"offset {tier_offset}, side {side})",
        strike=chosen, anchor_strike=listed[anchor_idx],
        listed_strikes_count=len(listed),
    )


def moneyness(*, strike: Any, spot: Any, side: Any) -> str:
    """Classify `strike` as 'ITM' | 'ATM' | 'OTM' relative to `spot`, given side.

    Symbol-generic by construction: compares the two prices directly, no
    dollar-rounding anchor (unlike crypto/lib/strike_selection.moneyness, which
    calls its own $1-rounding atm_strike() first). 'ATM' fires only on an exact
    match, which is rare for a real listed strike vs. a real spot price — that is
    expected and correct; most real strikes are legitimately ITM or OTM by a
    fractional amount.
    """
    if side not in ("C", "P"):
        raise ValueError(f"side must be 'C' or 'P', got {side!r}")
    strike_f = _as_float(strike)
    spot_f = _as_float(spot)
    if strike_f == spot_f:
        return "ATM"
    if side == "C":
        return "ITM" if strike_f < spot_f else "OTM"
    return "ITM" if strike_f > spot_f else "OTM"
