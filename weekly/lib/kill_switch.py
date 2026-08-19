"""weekly/lib/kill_switch.py -- CLAUDE.md Rule 5 (per-account daily loss kill switch),
re-derived for a lane that can hold positions across days.

WHY THE 0DTE VERSION DOESN'T TRANSFER. The SPY core/fleet kill switches measure -30%/-50%
of START-OF-DAY EQUITY *intraday* (backtest/lib/risk_gate.py's KILL_SWITCH rule) and that
is correct there BECAUSE every 0DTE position is flat by EOD: for a lane with no overnight
carry, equity drawdown IS realized P&L drawdown -- the two numbers never diverge. weekly-1
breaks that equivalence on purpose (multi-day holds are the entire point of trading
weeklies instead of 0DTE). An OPEN multi-day position's UNREALIZED mark can swing -25% on
one red session and fully recover the next day without the entry thesis ever being wrong.
Reusing the equity-based trip here would fire on ORDINARY volatility the strategy is
DESIGNED to hold through -- likely several times a week -- which would silently defeat the
lane's own premise. So:

  TRIP DECISION = REALIZED P&L TODAY ONLY. Unrealized P&L is computed and RETURNED on every
  call (visibility is the product, OP-33) but NEVER feeds the trip boolean. See
  `evaluate_daily_kill_switch`.

  SEMANTICS = BLOCK NEW ENTRIES ONLY, NEVER FORCE-CLOSE (params.risk.kill_switch_semantics
  == "blocks_new_entries_only", the only semantics this module implements). Force-closing
  open positions on an unrealized swing would LIQUIDATE positions this strategy is
  specifically designed to hold through -- that is a silent, risk-control-SHAPED strategy
  change, not a safety measure, and it is exactly the kind of thing Rule 10 ("if Gamma
  flags a rule violation, the trade does not happen") exists to prevent from happening by
  accident. Rule 5's job is "stop digging a NEW hole today"; it is never "override the
  position-management thesis of every position already open." The only `action` values
  this module can ever return are `ACTION_NONE` and `ACTION_BLOCK_NEW_ENTRIES_ONLY` -- there
  is no close/liquidate/cancel code path anywhere below (see
  `_assert_never_force_closes_positions`, the named anchor the guard test in
  backtest/tests/test_weekly_kill_switch.py pins against, and the grep-based "no
  order-placement call in this file" guard in the same test file).

FAIL-CLOSED ON UNREADABLE REALIZED-P&L INPUT -- same direction as risk_gate.check_order's
rule 0 (uncertainty about an order-relevant number -> deny), applied here to "uncertainty
about today's own loss so far -> block new entries until it's trustworthy again." This
NEVER touches an open position and NEVER touches the operator's session (OP-32): only
Stage A shadow logging observes the result of this module. A `kill_switch_tripped=True`
returned for a DATA problem carries a distinct `code`
(CODE_UNREADABLE_INPUT vs CODE_KILL_TRIPPED) so a downstream reader/instrument can always
tell "we blocked because we don't trust the data" apart from "the account genuinely lost
its daily floor."

ALSO EXPOSES `check_position_catastrophe` -- Rule 8's -50% catastrophe premium cap,
baselined at EACH POSITION'S OWN ENTRY PREMIUM, never start-of-day equity and never any
other position's state. A weekly position opened two sessions ago at $2.00 that now marks
$1.00 has breached its own -50% floor regardless of what today's start-of-day equity did or
what any OTHER basket position is doing. This is a PURE evaluation only -- it does not
close, cancel, or modify anything; real exit mechanics for a breach live in
exit_manager.py (program doc §5, reused as-is, out of scope for this module).
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional

CODE_OK = "OK"
CODE_KILL_TRIPPED = "DAILY_KILL_TRIPPED"
CODE_UNREADABLE_INPUT = "UNREADABLE_INPUT"

ACTION_NONE = "none"
ACTION_BLOCK_NEW_ENTRIES_ONLY = "block_new_entries_only"

# The ONLY kill-switch semantics this module implements. Matches
# automation/state/weekly/params.json's risk.kill_switch_semantics value verbatim.
SUPPORTED_KILL_SWITCH_SEMANTICS = "blocks_new_entries_only"


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover -- debug aid only
        return "<MISSING>"


_MISSING = _Missing()


def _nested_get(params: Any, *path: str) -> Any:
    """Walk a dotted key path through nested Mappings. Local copy of conflict.py's helper
    (deliberately duplicated, not imported, so this module stays independently loadable --
    mirrors risk_gate.py's self-contained style; no cross-import between the gate modules
    in this repo)."""
    cur = params
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def _is_bad_number(x: Any) -> bool:
    """True when x cannot be trusted as a finite real number. Local copy of
    conflict.py's / risk_gate.py's helper -- rejects None, NaN, inf, and bools."""
    if x is None or isinstance(x, bool):
        return True
    if isinstance(x, (int, float)):
        return math.isnan(x) or math.isinf(x)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return True
    return math.isnan(v) or math.isinf(v)


def _fail_closed_block(code: str, reason: str, **context: Any) -> dict:
    """Shared fail-closed shape used whenever the trip decision cannot be trusted. Always
    BLOCKS new entries (the safe direction for uncertainty about your own realized P&L) but
    is tagged with a code distinct from a genuine trip (see module docstring)."""
    return {
        "kill_switch_tripped": True,
        "action": ACTION_BLOCK_NEW_ENTRIES_ONLY,
        "code": code,
        "reason": reason,
        **context,
    }


def evaluate_daily_kill_switch(
    realized_pnl_today: Any,
    start_of_day_equity: Any,
    unrealized_pnl_today: Any,
    params: Mapping[str, Any],
) -> dict:
    """Rule 5 for weekly-1. Trips on REALIZED P&L only; unrealized P&L is reported, never
    used in the trip test. Returns `action` in {ACTION_NONE, ACTION_BLOCK_NEW_ENTRIES_ONLY}
    -- see module docstring for the full reasoning on both design decisions.
    """
    semantics = _nested_get(params, "risk", "kill_switch_semantics")
    if semantics != SUPPORTED_KILL_SWITCH_SEMANTICS:
        # This module implements ONE semantics. A config that asks for anything else is a
        # mismatch we do not silently reinterpret -- we still fail closed (block new
        # entries, the strictly safe direction) but say exactly why, rather than guessing
        # what an unimplemented "force_close" or similar mode should do.
        return _fail_closed_block(
            CODE_UNREADABLE_INPUT,
            f"params.risk.kill_switch_semantics={semantics!r} -- this module only "
            f"implements {SUPPORTED_KILL_SWITCH_SEMANTICS!r}; refusing to silently guess "
            "an unimplemented kill-switch behavior, blocking new entries until this is "
            "corrected",
        )

    pct_raw = _nested_get(params, "risk", "daily_loss_kill_switch_pct")
    if pct_raw is _MISSING or _is_bad_number(pct_raw):
        return _fail_closed_block(
            CODE_UNREADABLE_INPUT,
            f"params.risk.daily_loss_kill_switch_pct missing/unreadable ({pct_raw!r}) -- "
            "fail closed, blocking new entries",
        )
    if _is_bad_number(realized_pnl_today) or _is_bad_number(start_of_day_equity):
        return _fail_closed_block(
            CODE_UNREADABLE_INPUT,
            f"realized_pnl_today/start_of_day_equity unreadable (got "
            f"{realized_pnl_today!r}, {start_of_day_equity!r}) -- fail closed, blocking "
            "new entries until today's realized P&L is trustworthy again",
        )
    realized = float(realized_pnl_today)
    sod_equity = float(start_of_day_equity)
    if sod_equity <= 0:
        return _fail_closed_block(
            CODE_UNREADABLE_INPUT,
            f"start_of_day_equity must be > 0 (got {sod_equity}) -- fail closed",
            start_of_day_equity=sod_equity,
        )

    # Unrealized is REPORTED ONLY -- a read failure on it must never itself block entries
    # (only realized-P&L uncertainty does, checked above). Parsed leniently: unreadable ->
    # reported as None, never treated as "no drawdown" or "huge drawdown".
    unrealized: Optional[float]
    if _is_bad_number(unrealized_pnl_today):
        unrealized = None
    else:
        unrealized = float(unrealized_pnl_today)

    kill_pct = float(pct_raw)
    realized_loss_floor_dollars = -abs(kill_pct) * sod_equity
    tripped = realized <= realized_loss_floor_dollars

    return {
        "kill_switch_tripped": tripped,
        "action": ACTION_BLOCK_NEW_ENTRIES_ONLY if tripped else ACTION_NONE,
        "code": CODE_KILL_TRIPPED if tripped else CODE_OK,
        "realized_pnl_today": round(realized, 2),
        "unrealized_pnl_today_reported_only": (round(unrealized, 2) if unrealized is not None else None),
        "start_of_day_equity": round(sod_equity, 2),
        "daily_loss_kill_switch_pct": kill_pct,
        "realized_loss_floor_dollars": round(realized_loss_floor_dollars, 2),
        "reason": (
            f"realized P&L ${realized:,.0f} <= floor ${realized_loss_floor_dollars:,.0f} "
            f"({kill_pct:.0%} of start-of-day ${sod_equity:,.0f}) -- new entries blocked "
            "for the rest of the day; existing positions are UNTOUCHED (see module docstring)"
            if tripped else
            f"realized P&L ${realized:,.0f} above floor ${realized_loss_floor_dollars:,.0f} "
            f"({kill_pct:.0%} of start-of-day ${sod_equity:,.0f})"
        ),
    }


def check_position_catastrophe(
    symbol: str,
    entry_premium: Any,
    current_premium: Any,
    params: Mapping[str, Any],
) -> dict:
    """Per-POSITION catastrophe check, baselined at THIS position's OWN entry premium --
    never start-of-day equity, never any other position's state (see module docstring for
    why conflating this with `evaluate_daily_kill_switch`'s start-of-day baseline would be
    wrong for a multi-day hold).

    PURE EVALUATION ONLY. Never closes, cancels, or modifies anything. Returns whether the
    breach condition holds so a shadow-ledger row (or a future exit_manager wiring, out of
    scope here) can attribute the decision; it never enacts it.
    """
    catastrophe_pct_raw = _nested_get(params, "exits", "catastrophe_stop_pct")
    if catastrophe_pct_raw is _MISSING or _is_bad_number(catastrophe_pct_raw):
        return {
            "breached": None,
            "code": CODE_UNREADABLE_INPUT,
            "symbol": symbol,
            "reason": f"params.exits.catastrophe_stop_pct missing/unreadable ({catastrophe_pct_raw!r}) "
                      "-- cannot evaluate; this is NOT a breach determination either way",
        }
    if _is_bad_number(entry_premium) or _is_bad_number(current_premium):
        return {
            "breached": None,
            "code": CODE_UNREADABLE_INPUT,
            "symbol": symbol,
            "reason": f"entry_premium/current_premium unreadable (got {entry_premium!r}, "
                      f"{current_premium!r})",
        }
    entry = float(entry_premium)
    current = float(current_premium)
    if entry <= 0:
        return {
            "breached": None,
            "code": CODE_UNREADABLE_INPUT,
            "symbol": symbol,
            "reason": f"entry_premium must be > 0 (got {entry})",
        }

    catastrophe_pct = float(catastrophe_pct_raw)  # e.g. -50.0 meaning -50%
    pct_move = ((current - entry) / entry) * 100.0
    breached = pct_move <= catastrophe_pct
    return {
        "breached": breached,
        "code": CODE_OK,
        "symbol": symbol,
        "entry_premium": round(entry, 4),
        "current_premium": round(current, 4),
        "pct_move_from_own_entry": round(pct_move, 2),
        "catastrophe_stop_pct": catastrophe_pct,
        "reason": (
            f"{symbol}: {pct_move:.1f}% from its OWN entry ${entry:.2f} breaches the "
            f"{catastrophe_pct:.0f}% catastrophe floor"
            if breached else
            f"{symbol}: {pct_move:.1f}% from its OWN entry ${entry:.2f}, within the "
            f"{catastrophe_pct:.0f}% catastrophe floor"
        ),
    }


def _assert_never_force_closes_positions() -> None:
    """Executable statement of the load-bearing invariant: this module can BLOCK new
    entries but can never close, cancel, or modify an existing position. The guarantee is
    in what this file does NOT import or call -- no order-placement/cancel/close call, no
    `close_*`/`liquidate_*`/`cancel_*` function, and no `action` value other than
    ACTION_NONE / ACTION_BLOCK_NEW_ENTRIES_ONLY exists anywhere in this module. Named
    anchor for the regression test in backtest/tests/test_weekly_kill_switch.py that pins
    this shape (mirrors backtest/lib/risk_gate.py's `_assert_never_locks_human` pattern).
    """
    return None
