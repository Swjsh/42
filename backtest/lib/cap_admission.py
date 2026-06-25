"""cap_admission — the order-ADMISSION layer for autoresearch book aggregation.

WHY THIS EXISTS (the graduated guardrail)
-----------------------------------------
`risk_gate.check_order` (the SINGLE live authority) caps an order's NOTIONAL =
premium * qty * 100 at the TIGHTER of `per_trade_risk_cap_pct` and the v15 per-tier
max-premium table, AND enforces a `min_contracts` floor (Safe 3 / Bold 5; qty below
the floor is a hard DENY). The research path — `simulator_real` and the DTE harness
that underlies it — has NO such gate, so a validated expectancy SILENTLY OVERSTATES
the realizable book for any config whose `qty * premium` exceeds the cap: the sim
counts a fill the live engine would BLOCK.

This is a re-violated lesson (the 2026-06-15 Bold-oversize incident -> pre_order_gate;
the 2026-06-21 DTE cap-overlay finding). Per the doctrine "a re-violated lesson is a
missing guardrail -> graduate it to a code assertion," this module turns the cap into
a DEFAULT, tested, reusable book-aggregation step shared by the sweep entry points.

WHAT THIS IS / IS NOT
---------------------
  * This is the order-ADMISSION layer. A trade is ADMITTED iff `check_order` ALLOWS it
    (notional within the tighter of risk-cap / tier AND qty >= min_contracts). A BLOCKED
    trade is EXCLUDED from the realizable book entirely (its realizable P&L is $0) — it
    is NEVER qty-reduced. `min_contracts` DENIES; it does not shrink.
  * The cap is an ORDER GATE, not a fill price. This module never touches per-fill
    economics (entry/exit premium, pct_return, dollar_pnl). `simulator_real` and the DTE
    sim stay BEHAVIOR-UNCHANGED — admission happens AFTER the fills are produced, at the
    book layer. That is what keeps this Sunday-guard-safe by construction.
  * `check_order` is the ONLY authority. We do NOT re-implement the cap arithmetic here;
    we call it with the EXACT params the live heartbeat uses (the same params
    `pre_order_gate._params_for` builds), so cap-aware == live-risk-intent by construction.

The standalone overlays `_capcheck_dte_overlay.py` and `_dte_stop_cap_aware.py` are the
origin of this logic; they now import from here (single source of truth).

Pure module: no I/O, no mutation. Every public function returns NEW objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from lib.risk_gate import check_order, RiskDecision


# --- account sizing config (the params check_order's SIZING path reads) -------
#
# These mirror `automation/scripts/pre_order_gate.py` EXACTLY (Safe params.json +
# the Bold per-tier table Bold's params.json omits). They are CONFIG, not a second
# rule implementation — the rule that consumes them lives once, in check_order. Kept
# here (rather than importing pre_order_gate, which lives under automation/scripts and
# is not importable as a package) so this lib has no path-hacking dependency. A guard
# test asserts these stay byte-identical to pre_order_gate's tables.

SAFE_MAX_PREMIUM_TIERS = [
    {"equity_min": 0,      "equity_max": 2_000,        "max_pct": 0.40},
    {"equity_min": 2_000,  "equity_max": 10_000,       "max_pct": 0.30},
    {"equity_min": 10_000, "equity_max": 25_000,       "max_pct": 0.25},
    {"equity_min": 25_000, "equity_max": 999_999_999,  "max_pct": 0.20},
]
BOLD_MAX_PREMIUM_TIERS = [
    {"equity_min": 0,      "equity_max": 2_000,        "max_pct": 0.50},
    {"equity_min": 2_000,  "equity_max": 10_000,       "max_pct": 0.40},
    {"equity_min": 10_000, "equity_max": 25_000,       "max_pct": 0.35},
    {"equity_min": 25_000, "equity_max": 999_999_999,  "max_pct": 0.25},
]
SAFE_RISK_CAP = 0.30
BOLD_RISK_CAP = 0.50
SAFE_MIN_CONTRACTS = 3
BOLD_MIN_CONTRACTS = 5


def params_for(account: str) -> dict:
    """Build the minimal sizing-params mapping check_order needs, per account.

    Byte-identical to `pre_order_gate._params_for` — the same contract the live
    heartbeat hands the gate. Only the keys the SIZING path reads are populated;
    the non-sizing rules are neutralised by the caller (see `cap_allows`).
    """
    a = account.lower()
    if a in ("safe", "gamma-safe-2"):
        return {
            "per_trade_risk_cap_pct": SAFE_RISK_CAP,
            "daily_loss_kill_switch_pct": 0.30,
            "min_contracts": SAFE_MIN_CONTRACTS,
            "first_entry_after_stop_blocked": True,
            "v15_max_premium_pct_of_account": SAFE_MAX_PREMIUM_TIERS,
        }
    if a in ("bold", "aggressive", "gamma-risky-2"):
        return {
            "per_trade_risk_cap_pct": BOLD_RISK_CAP,
            "daily_loss_kill_switch_pct": 0.50,
            "min_contracts": BOLD_MIN_CONTRACTS,
            "first_entry_after_stop_blocked": True,
            "v15_max_premium_pct_of_account": BOLD_MAX_PREMIUM_TIERS,
        }
    raise ValueError(f"unknown account {account!r} (expected safe/bold)")


def _account_alias(account: str) -> str:
    return "Gamma-Safe-2" if account.lower() in ("safe", "gamma-safe-2") else "Gamma-Risky-2"


def decide(account: str, equity: float, qty: int, premium: float,
           params: Optional[Mapping[str, Any]] = None) -> RiskDecision:
    """The LIVE gate's verdict for ONE (qty, premium) at this equity, SIZING-only.

    Calls `lib.risk_gate.check_order` with the account's sizing params (the same the
    heartbeat uses), neutralising every NON-sizing rule (flat / PDT / kill-switch /
    first-entry) so ONLY the notional cap + min_contracts can bind — exactly as
    `pre_order_gate.check` does. Returns the full RiskDecision (code + reason) so a
    caller can introspect WHICH constraint bound.
    """
    p = dict(params) if params is not None else params_for(account)
    return check_order(
        _account_alias(account),
        equity=equity,
        start_of_day_equity=equity,   # == equity => realised-drawdown branch can't fire
        proposed_qty=qty,
        premium=premium,
        setup_name="CAP_ADMISSION",
        current_position_status=None,  # flat => NOT_FLAT can't fire
        day_trades_used_5d=0,          # PDT neutralised
        kill_switch_tripped=False,     # kill-switch neutralised
        prior_stops_today=(),          # first-entry-lock neutralised
        params=p,
    )


def cap_allows(account: str, equity: float, qty: int, premium: float,
               params: Optional[Mapping[str, Any]] = None) -> bool:
    """True iff the LIVE risk_gate would ADMIT this (qty, premium) at this equity.

    The single admission predicate. A False here is the SAME denial the live engine
    would issue at order-build (notional > cap OR qty < min_contracts)."""
    return bool(decide(account, equity, qty, premium, params).allowed)


@dataclass(frozen=True)
class AdmissionResult:
    """The realizable book after the order-admission gate.

    admitted    : the subset of input fills the cap ALLOWS (realizable book).
    blocked     : the fills the cap EXCLUDES ($0 realizable each).
    n_total     : len(input fills).
    block_rate  : len(blocked) / n_total (0.0 when n_total == 0).
    block_codes : {decision.code: count} over the blocked fills (why each was denied).
    enforce_cap : True (this result came from the cap-enforced path).
    """

    admitted: tuple
    blocked: tuple
    n_total: int
    block_rate: float
    block_codes: dict
    enforce_cap: bool = True


def admit_book(
    fills: Sequence,
    account: str,
    equity: float,
    qty: int,
    *,
    enforce_cap: bool = True,
    premium_getter: Callable[[Any], float] = lambda r: r.entry_premium,
    params: Optional[Mapping[str, Any]] = None,
) -> AdmissionResult:
    """Filter a list of per-trade fills to the realizable (cap-admitted) book.

    This is the DEFAULT book-aggregation step for the autoresearch sweep entry points.

    Each fill is admitted iff `check_order` ALLOWS (qty @ the fill's entry premium @
    `equity`): notional <= the tighter of (per_trade_risk_cap_pct, v15 tier) AND
    qty >= min_contracts. A blocked fill is EXCLUDED from `admitted` (realizable book
    $0 for it) and recorded in `blocked` — never qty-reduced.

    Args:
        fills: per-trade fill objects (e.g. DteFill / TradeFill). Read-only.
        account: "safe" or "bold" (aliases accepted).
        equity: account equity the cap is measured against.
        qty: contracts per order (the book's fixed qty; e.g. Safe 3 / Bold 5).
        enforce_cap: when True (DEFAULT) the cap gate runs and the realizable book is
            returned. When False the book is returned UNCHANGED (every fill admitted,
            block_rate 0.0) — the OLD cap-blind book, for EXPLICIT comparison only.
            With enforce_cap=False the returned `admitted` tuple preserves input order
            and identity, so the book is byte-identical to the pre-cap behaviour.
        premium_getter: how to read a fill's per-contract entry premium (default
            `.entry_premium`, which both DteFill and TradeFill expose).
        params: optional explicit sizing params (defaults to `params_for(account)`).

    Returns:
        AdmissionResult.
    """
    fills = tuple(fills)
    n_total = len(fills)

    if not enforce_cap:
        # Cap-blind path: byte-identical to today's book. NO gate is consulted.
        return AdmissionResult(
            admitted=fills, blocked=(), n_total=n_total,
            block_rate=0.0, block_codes={}, enforce_cap=False,
        )

    p = dict(params) if params is not None else params_for(account)
    admitted = []
    blocked = []
    block_codes: dict = {}
    for r in fills:
        d = decide(account, equity, qty, float(premium_getter(r)), p)
        if d.allowed:
            admitted.append(r)
        else:
            blocked.append(r)
            block_codes[d.code] = block_codes.get(d.code, 0) + 1

    block_rate = round(len(blocked) / n_total, 4) if n_total else 0.0
    return AdmissionResult(
        admitted=tuple(admitted), blocked=tuple(blocked), n_total=n_total,
        block_rate=block_rate, block_codes=block_codes, enforce_cap=True,
    )


def median_notional_exceeds_cap(
    fills: Sequence,
    account: str,
    equity: float,
    qty: int,
    *,
    premium_getter: Callable[[Any], float] = lambda r: r.entry_premium,
    params: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True iff the MEDIAN order's notional (median entry premium * qty * 100) would be
    BLOCKED by the cap at this equity. This is the trip-wire the graduated guard uses:
    a config whose median order exceeds the cap MUST be cap-aware (its cap-blind book
    overstates the realizable edge). Returns False on an empty book (nothing to assert)."""
    fills = tuple(fills)
    if not fills:
        return False
    prems = sorted(float(premium_getter(r)) for r in fills)
    m = len(prems)
    median_prem = prems[m // 2] if m % 2 == 1 else 0.5 * (prems[m // 2 - 1] + prems[m // 2])
    return not cap_allows(account, equity, qty, median_prem, params)
