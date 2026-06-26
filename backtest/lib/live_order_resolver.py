"""Live-order parameter resolver — the A5 deterministic callable the heartbeat invokes.

A5 KEYSTONE / KILL-clause: the watcher-fleet edges (the live #1, vwap_continuation)
trade via the HEARTBEAT (`automation/prompts/heartbeat.md`, the LLM tick). The A5
KILL-clause forbids leaving load-bearing order math in ambiguous prose. This module is
the SINGLE deterministic callable the tick invokes to resolve #1's order params
(strike_offset, expiry_dte, stop, qty) — graduating prose → code at the order-build
boundary so the live order is computed identically every time, by code, not by prose.

WHAT THIS IS / IS NOT
---------------------
Pure function. No I/O, no mutation, no MCP, no order placement. It READS the account's
`params` mapping and RETURNS an immutable `LiveOrderParams`. It has NO power to place,
size-up, or scale anything; it does not touch the broker. The heartbeat takes the
returned values and builds the bracket through the SAME pre-execution gate + execution
steps as any normal entry (risk_gate.check_order remains the order-placement authority).

It REUSES the already-built, already-parity-tested dispatchers — it never re-types a
strike, stop, or threshold literal:
  * strike  -> risk_gate.select_strike_offset (WP-5; flag j_vwap_cont_strike_override_enabled)
  * %-stop  -> risk_gate.select_exit_params    (WP-0; the per-setup/global premium stop)
  * $-stop  -> filters.vwap_cont_dollar_stop   (WP-8; flag j_vwap_cont_dollar_stop_enabled)
  * expiry  -> filters.vwap_cont_1dte_enabled  (WP-8; flag j_vwap_cont_1dte_enabled)
  * qty     -> the WP-3 cap-respecting base size (3 contracts; v15 nominal 5/8 BREACH the
               30%/50% per-trade cap at $2K — base size only, recency governs SCALING not
               initial deploy).

THE PARITY PROPERTY (the KILL criterion — tested in
test_engine_live_order_resolver_parity.py): with ALL the vwap_continuation override flags
OFF (the on-disk production default), `live_order_params(...)` returns TODAY'S EXACT
config for #1:
    strike_offset = the generic v15 tier the caller passes in (OTM-2 on live Safe-2),
    expiry_dte    = 0 (0DTE),
    stop          = the -8% percent stop the caller passes in (via select_exit_params),
    qty           = the WP-3 cap-respecting base (the caller's current qty).
Any drift with every flag off is a KILL → revert that flag.

CONVENTIONS (load-bearing)
  * strike_offset is in the SIMULATOR convention (NEGATIVE=ITM, ATM=0) — the same value
    select_strike_offset returns and the same value the order path already uses. The
    caller passes the generic-tier offset it would otherwise have used.
  * stop is expressed as EXACTLY ONE of `stop_pct` (a negative fraction, e.g. -0.08) OR
    `stop_dollars` (a positive per-contract premium-loss magnitude). The OTHER is None.
    Flags-off => stop_pct set (today's behavior). $-stop flag on => stop_dollars set.
  * expiry_dte is 0 (0DTE, today) or 1 (1DTE, the WP-8 doubling) — calendar days to add
    to the trade date for the contract expiry. The heartbeat/executor maps it to a real
    expiry; this resolver only states the offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from . import filters as _filters
from . import risk_gate as _risk_gate


# The ONE watcher-fleet edge that is live and that this resolver re-strikes/-stops/-dates.
# Single source of truth: the watcher's setup_name= field (vwap_continuation_watcher.py).
VWAP_CONTINUATION = "VWAP_CONTINUATION"

# WP-3 cap-respecting base size. v15's nominal 5/8 BREACH the 30%/50% per-trade cap at
# $2K; 3 = the floor (2 TP + 1 runner, Rule 6) and the cap-respecting base. Recency
# governs SCALING above this, NOT the initial deploy.
WP3_BASE_QTY = 3


@dataclass(frozen=True)
class LiveOrderParams:
    """The resolved order parameters for ONE live entry. Immutable.

    Exactly one of (stop_pct, stop_dollars) is non-None — see module docstring.
    """

    strike_offset: int          # simulator convention (NEGATIVE=ITM, ATM=0)
    expiry_dte: int             # 0 = 0DTE (today), 1 = 1DTE (T+1)
    stop_pct: Optional[float]   # negative fraction (e.g. -0.08), or None if $-anchored
    stop_dollars: Optional[float]  # positive per-contract premium-loss $, or None if %
    qty: int                    # WP-3 cap-respecting base size

    def __post_init__(self) -> None:
        # Executable invariant: a stop is stated exactly one way. A both/neither result
        # is a resolver bug — fail loud rather than hand the executor an ambiguous bracket.
        has_pct = self.stop_pct is not None
        has_dollars = self.stop_dollars is not None
        if has_pct == has_dollars:
            raise ValueError(
                "LiveOrderParams must state the stop exactly one way "
                f"(stop_pct={self.stop_pct!r}, stop_dollars={self.stop_dollars!r})"
            )


def live_order_params(
    setup_name: Any,
    account: str,
    params: Optional[Mapping[str, Any]],
    *,
    current_strike_offset: int,
    current_stop_pct: float,
    current_qty: int = WP3_BASE_QTY,
    side: str = "P",
) -> LiveOrderParams:
    """Resolve the deterministic order params for ONE live entry.

    For vwap_continuation this returns the VALIDATED config when (and only when) the
    matching override flag is ON, else today's exact config (the parity property). For any
    OTHER setup it returns today's exact config verbatim (the dispatchers are per-setup;
    C29 — overrides never transfer).

    Args:
        setup_name: the named playbook setup driving this entry (e.g. "VWAP_CONTINUATION").
        account: account alias ("Gamma-Safe-2" / "Gamma-Risky-2") — for messages only;
            account-awareness lives IN the per-account `params` file (Safe vs Bold keys).
        params: the account's params.json mapping (or None for an older snapshot).
        current_strike_offset: the generic v15-tier strike offset the order path would
            otherwise use (SIMULATOR convention) — returned verbatim when the strike flag
            is off (the byte-identity guarantee).
        current_stop_pct: the global/per-setup premium stop % the order path would
            otherwise use (negative fraction) — returned verbatim when the $-stop flag is
            off (the byte-identity guarantee).
        current_qty: the current cap-respecting base size (default WP-3 = 3). Returned
            verbatim — this resolver never scales (recency governs scaling, not deploy).
        side: "P"/"C" — passed through to the per-setup dispatchers (side-agnostic today).

    Returns:
        LiveOrderParams — the resolved (strike_offset, expiry_dte, stop, qty).
    """
    # STRIKE: WP-5 dispatch. Flag off (or non-vwap_cont setup) -> current_strike_offset.
    strike_offset = _risk_gate.select_strike_offset(
        setup_name, side, params, current_strike_offset
    )

    # EXPIRY: WP-8 1DTE flag — ONLY for vwap_continuation. Flag off -> 0DTE (today).
    expiry_dte = 0
    is_vwap_cont = isinstance(setup_name, str) and setup_name == VWAP_CONTINUATION
    if is_vwap_cont and _filters.vwap_cont_1dte_enabled(params):
        expiry_dte = 1

    # STOP: WP-8 dollar-stop flag — ONLY for vwap_continuation. When ON, the stop is the
    # validated per-account dollar-anchored magnitude (filters single source of truth) and
    # stop_pct is None. Otherwise the stop is the percent stop resolved through the WP-0
    # dispatch (which itself returns the global -8% unchanged when no per-setup %-flag is
    # on) — today's exact behavior.
    stop_pct: Optional[float]
    stop_dollars: Optional[float]
    if is_vwap_cont and _filters.vwap_cont_dollar_stop_enabled(params):
        stop_dollars = float(_filters.vwap_cont_dollar_stop(params))
        stop_pct = None
    else:
        stop_pct = float(
            _risk_gate.select_exit_params(setup_name, side, params, current_stop_pct)
        )
        stop_dollars = None

    # QTY: WP-3 cap-respecting base size, verbatim. The resolver NEVER scales; the
    # ultimate sizing authority remains risk_gate.check_order at order-placement time.
    return LiveOrderParams(
        strike_offset=int(strike_offset),
        expiry_dte=int(expiry_dte),
        stop_pct=stop_pct,
        stop_dollars=stop_dollars,
        qty=int(current_qty),
    )
