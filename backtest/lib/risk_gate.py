"""Risk Gate — the single source of truth for "may this order be placed?".

Blueprint Phase 0c. Consolidates EVERY pre-order risk rule that used to live as
English prose scattered through the heartbeat prompt (the "human monitoring is
insufficient" anti-pattern that SEC Rule 15c3-5 names) into ONE pure function.
The backtest engine, the live heartbeat, and the pre-order CLI all call the same
`check_order`, so backtest-risk == live-risk-intent by construction.

WHAT THIS IS / IS NOT
---------------------
This module gates *orders only*. It has NO power over sessions, processes, the
scheduler, or J's interactive Claude. That separation is deliberate and
load-bearing (the OP-32 scar — 2026-05-22 a market-hours firewall locked J out of
his own session entirely):

    * ORDER control fails CLOSED — on any uncertainty we DENY the order.
    * OPERATOR control fails OPEN — nothing here can ever stop, block, or kill a
      human session. `check_order` returns a value; it does not touch the OS.

A `Deny` means "this specific order does not get placed." It never means "the
human is locked out." See `_assert_never_locks_human` for the executable
statement of that invariant.

CANONICAL RULES ENCODED (source of every threshold)
---------------------------------------------------
All numeric thresholds are READ FROM `params.json` by the caller and passed in
via the `params` dict — this function performs no I/O so it stays pure and
testable. The rules, with their doctrine source:

  KILL_SWITCH        CLAUDE.md Rule 5 + params `daily_loss_kill_switch_pct`.
                     Per account, ISOLATED (Safe -30% does NOT halt Bold, Bold
                     -50% does NOT halt Safe). Two independent triggers:
                       (a) caller-supplied `kill_switch_tripped` latch, and
                       (b) realised drawdown: equity <= start_of_day_equity *
                           (1 - daily_loss_kill_switch_pct).
  RISK_CAP           CLAUDE.md Rule 6 + params `per_trade_risk_cap_pct`
                     (Safe 30% / Bold 50% of equity). Notional = premium * qty *
                     100 must not exceed equity * cap.
  MAX_PREMIUM_TIER   CLAUDE.md "The strategy" v15 + params
                     `v15_max_premium_pct_of_account` per-equity-tier hard gate.
                     The tighter of (RISK_CAP, this tier %) is the effective cap.
  MIN_CONTRACTS      CLAUDE.md Rule 6 + params `min_contracts` (>=3: 2 TP + 1
                     runner). A proposal below the floor is denied.
  DAILY_PREMIUM_BUDGET
                     NEW 2026-08-28. Caps total premium DEPLOYED by one arm in
                     one session. Set EITHER
                     `daily_premium_budget_pct_of_equity` (preferred -- scales
                     with the account, so the rule does not tighten as equity
                     grows) OR `daily_premium_budget_dollars` (absolute), or
                     both, in which case the TIGHTER wins. Both absent -> OFF.
                     `daily_premium_budget_loss_armed` (default True) makes it
                     bind only once the arm is already red on the day.
                     Scorecard: analysis/recommendations/daily-premium-budget.json
                     NOTE: this is a DIFFERENT, separately-owned mechanism from
                     the three PREREG-TIGHT-LADDER rules below -- do not conflate
                     them; see cap_entry_qty()'s module comment for why.
  MAX_CONTRACTS_PER_ENTRY / MAX_POSITION_DOLLARS
                     NEW 2026-08-29, PREREG-TIGHT-LADDER-2026-08-28.md controls
                     #1/#2. Flat per-entry ceilings on contract count
                     (`max_contracts_per_entry`) and notional dollars
                     (`max_position_dollars`), ADDITIONAL to RISK_CAP/
                     MAX_PREMIUM_TIER above (all bind, tightest wins). Both
                     absent -> OFF. Callers pre-shrink qty via the standalone
                     `cap_entry_qty()` helper (see its own module comment for
                     the CONFLICT/SKIP rule, control #3) so these two check_order
                     rules are a backstop, not the primary enforcement point.
  DAILY_LOSS_DOLLARS
                     NEW 2026-08-29, PREREG-TIGHT-LADDER-2026-08-28.md control
                     #5. A THIRD, independent KILL_SWITCH trigger alongside the
                     two already documented above: `daily_loss_kill_switch_dollars`
                     (absolute $ floor on top of the existing pct floor -- both
                     armed simultaneously, neither replaces the other). Absent
                     key -> OFF.
  PDT / SETTLEMENT   CLAUDE.md Rule 7. Two mutually-exclusive gate modes, selected
                     by params.pdt_gate_mode (per-account, params.json):
                       "margin_pdt" (LEGACY, function-level default when the key
                         is absent -- preserves every pre-2026-07-14 caller byte-
                         for-byte): >=3 day-trades in rolling 5 business days AND
                         equity < $25,000 -> deny. Models FINRA's margin-account
                         PDT rule. VERIFIED 2026-07-14 this rule never applied to
                         either core account: both are CASH accounts (multiplier
                         "1", Alpaca reports pattern_day_trader/daytrade_count as
                         null -- PDT is structurally inapplicable) --
                         markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-
                         2026-07-14.md.
                       "cash_settlement" (NEW, params.json-selected for both live
                         cash accounts as of 2026-07-14): gates on SETTLED cash,
                         not a trade count -- the constraint that actually binds a
                         cash account (Good Faith Violation / freeriding, Reg T).
                         Requires `settled_cash_available` (today's settled-cash
                         pool remaining, see setup/scripts/settlement_ledger.py)
                         to cover this order's notional, and `same_day_entries_
                         used` to stay under params.max_same_day_roundtrips (a
                         generous sanity cap, default 5). Both are REQUIRED
                         (fail-closed) in this mode -- a missing value is
                         uncertainty, not permission.
                       UPDATE (2026-08-18, markdown/trading-knowledge/REGULATORY-
                         BROKER-LANDSCAPE-2026-08-18.md + analysis/deep-research/
                         PDT-CODE-ALIGNMENT-AUDIT-2026-08-18.md): the "margin_pdt"
                         premise above is DOUBLY stale. (1) FINRA eliminated this
                         exact rule for margin accounts (SR-FINRA-2025-017,
                         effective 2026-06-04; 18mo firm grace window to
                         2027-10-20). (2) "both are CASH accounts (multiplier
                         '1')" was already wrong by 2026-08-06 (live read:
                         multiplier=4, margin) and is wrong in principle -- Alpaca
                         sells no cash-account product at all ("all accounts are
                         set up as margin accounts", confirmed 2026-08-18). A
                         2026-08-18 live read of both core accounts found the
                         pattern_day_trader/daytrade_count fields entirely ABSENT
                         from the account payload (replaced by
                         intraday_adjustments) -- these accounts are confirmed on
                         Alpaca's NEW intraday-margin regime, not held under the
                         legacy grace-window clause. Neither core account runs
                         margin_pdt today (both are cash_settlement); this branch
                         is live code only for fleet arms (pinned margin_pdt,
                         fleet_executor.py:1224) where it is structurally inert
                         (day_trades_used_5d fed is always 0). If ever reactivated
                         with a real count, it would enforce a rule neither FINRA
                         nor Alpaca applies to these accounts any more -- treat
                         PDT_EQUITY_THRESHOLD/PDT_DAY_TRADE_LIMIT below as a frozen
                         historical-rule model, not a current regulatory citation.
  FIRST_ENTRY_LOCK   DELETED (J directive 2026-07-02: "Gone. We no longer have
                     it in our codebase."). The 'no second entry on a setup that
                     stopped out today' deny was Claude-invented and never
                     A/B-validated. `prior_stops_today` is still ACCEPTED (API
                     compat + journaling) but never denies.
  NOT_FLAT           CLAUDE.md Rule 4 ("No adding without a NEW confirmed
                     trigger") + the broker-is-source-of-truth flat-before-entry
                     invariant (C11/L47/L76). If a position is already open ->
                     deny a NEW entry.
  UNREADABLE_INPUT   The core safety property. If ANY required input is missing,
                     None, NaN, or unparseable -> deny. Uncertainty == no trade.

DECISION CODES (stable — callers + logs key off these strings)
  KILL_SWITCH, RISK_CAP, MAX_PREMIUM_TIER, MIN_CONTRACTS, PDT, SETTLEMENT,
  NOT_FLAT, UNREADABLE_INPUT, ALLOW
  (FIRST_ENTRY_LOCK retired 2026-07-02 — constant kept for old-log readers.
   SETTLEMENT added 2026-07-14 — fires only under pdt_gate_mode="cash_settlement".
   MAX_CONTRACTS_PER_ENTRY, MAX_POSITION_DOLLARS, DAILY_LOSS_DOLLARS added
   2026-08-29 — PREREG-TIGHT-LADDER-2026-08-28.md controls #1/#2/#5, all OFF
   unless their params key is present.)

EVALUATION ORDER
  Safety/uncertainty first (UNREADABLE_INPUT), then the hard halts that mean "no
  trading at all right now" (KILL_SWITCH, PDT, NOT_FLAT), then
  the per-order sizing gates (MIN_CONTRACTS, RISK_CAP, MAX_PREMIUM_TIER). The
  first failing rule wins; the returned `RiskDecision` is the single reason.

IMMUTABILITY
  `RiskDecision`, `Allow`, and `Deny` are frozen dataclasses. `check_order`
  reads its inputs and returns a NEW decision object; it never mutates `params`,
  the account, or any argument.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union


# --- Stable decision codes (the public contract for callers + logs) ----------
CODE_ALLOW = "ALLOW"
CODE_KILL_SWITCH = "KILL_SWITCH"
CODE_RISK_CAP = "RISK_CAP"
CODE_MAX_PREMIUM_TIER = "MAX_PREMIUM_TIER"
CODE_MIN_CONTRACTS = "MIN_CONTRACTS"
CODE_PDT = "PDT"
CODE_SETTLEMENT = "SETTLEMENT"  # NEW 2026-07-14 -- cash-settlement/GFV-aware Rule 7 gate
CODE_FIRST_ENTRY_LOCK = "FIRST_ENTRY_LOCK"  # RETIRED 2026-07-02 (kept for old-log readers)
CODE_DAILY_PREMIUM_BUDGET = "DAILY_PREMIUM_BUDGET"  # NEW 2026-08-28 -- session deployment budget
CODE_NOT_FLAT = "NOT_FLAT"
CODE_UNREADABLE_INPUT = "UNREADABLE_INPUT"
# PREREG-TIGHT-LADDER-2026-08-28 controls (added 2026-08-29). See cap_entry_qty's
# own module comment for the full mechanism; these three codes are backstops
# inside check_order (defense-in-depth -- callers are expected to pre-shrink via
# cap_entry_qty so these fire only if a caller skips that pre-check).
CODE_MAX_CONTRACTS_PER_ENTRY = "MAX_CONTRACTS_PER_ENTRY"  # control #1: 5 contracts/entry ceiling
CODE_MAX_POSITION_DOLLARS = "MAX_POSITION_DOLLARS"  # control #2: $1,000/position ceiling
CODE_DAILY_LOSS_DOLLARS = "DAILY_LOSS_DOLLARS"  # control #5: -$400/day realized-loss stop

# PDT (margin_pdt mode only) models FINRA's PRE-2026-06-04 margin-account rule
# (CLAUDE.md Rule 7, legacy) -- $25K threshold, 3-day-trades/5-business-days.
# FINRA ELIMINATED this rule for margin accounts effective 2026-06-04
# (SR-FINRA-2025-017, 18mo firm grace window to 2027-10-20) -- see
# markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md and
# analysis/deep-research/PDT-CODE-ALIGNMENT-AUDIT-2026-08-18.md. Both core
# accounts ARE margin accounts (multiplier=4, live-verified 2026-08-06 and
# 2026-08-18 -- the prior "cash account, multiplier=1" claim here was wrong even
# before the rule changed; Alpaca sells no cash-account product at all). Neither
# core account runs this branch today (both are pdt_gate_mode="cash_settlement");
# retained for the legacy revert path and for fleet arms (pinned margin_pdt,
# fleet_executor.py:1224) where it is structurally inert -- the day-trade count
# fed to it is always 0 (Alpaca's daytrade_count field is gone from the account
# payload as of 2026-08-18, replaced by intraday_adjustments).
PDT_EQUITY_THRESHOLD = 25_000.0
PDT_DAY_TRADE_LIMIT = 3

# cash_settlement mode: generous belt-and-suspenders sanity cap on same-day
# entries, used only when params.max_same_day_roundtrips is absent.
DEFAULT_MAX_SAME_DAY_ROUNDTRIPS = 5


@dataclass(frozen=True)
class RiskDecision:
    """Base result. Use `Allow` / `Deny`; check `.allowed` or `isinstance`."""

    allowed: bool
    code: str
    reason: str

    def __bool__(self) -> bool:  # `if decision:` reads as "is this allowed?"
        return self.allowed


@dataclass(frozen=True)
class Allow(RiskDecision):
    """The order passed every risk rule and may be placed."""

    def __init__(self, reason: str = "all risk checks passed") -> None:
        # frozen dataclass: set fields via object.__setattr__ in __init__.
        object.__setattr__(self, "allowed", True)
        object.__setattr__(self, "code", CODE_ALLOW)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class Deny(RiskDecision):
    """The order is rejected. `code` is one of the stable CODE_* strings."""

    def __init__(self, code: str, reason: str) -> None:
        object.__setattr__(self, "allowed", False)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "reason", reason)


# --- input-hygiene helpers (the fail-closed core) ----------------------------

def _is_bad_number(x: Any) -> bool:
    """True when x cannot be trusted as a finite real number.

    Catches the three unreadable-input shapes the spec calls out: None, NaN, and
    unparseable (a string/object that float() chokes on). Booleans are rejected
    too — a bool sneaking in where a price/equity belongs is a caller bug, and
    silently treating True as 1.0 would be a fail-OPEN hole.
    """
    if x is None:
        return True
    if isinstance(x, bool):
        return True
    if isinstance(x, (int, float)):
        return math.isnan(x) or math.isinf(x)
    # Last resort: anything else must parse to a finite float or it's bad.
    try:
        v = float(x)
    except (TypeError, ValueError):
        return True
    return math.isnan(v) or math.isinf(v)


def _as_float(x: Any) -> float:
    """Parse to float. Caller MUST have screened with _is_bad_number first."""
    return float(x)


def _max_premium_pct_for_equity(
    tiers: Any, equity: float
) -> Optional[float]:
    """Pick the v15 per-tier max-premium fraction for this equity.

    `tiers` is params `v15_max_premium_pct_of_account`: a list of
    {equity_min, equity_max, max_pct}. Returns the matching `max_pct`, or None
    when the table is missing/malformed/uncovered (fail-closed: a None result
    makes the caller deny rather than silently skip the gate).
    """
    if not isinstance(tiers, (list, tuple)) or not tiers:
        return None
    for tier in tiers:
        if not isinstance(tier, Mapping):
            return None
        lo = tier.get("equity_min")
        hi = tier.get("equity_max")
        pct = tier.get("max_pct")
        if _is_bad_number(lo) or _is_bad_number(hi) or _is_bad_number(pct):
            return None
        if _as_float(lo) <= equity < _as_float(hi):
            return _as_float(pct)
    return None  # equity not covered by any tier -> uncertainty -> deny upstream


# --- SETTLEMENT (cash_settlement pdt_gate_mode) — extracted (2026-08-18) ------
#
# RULE-ENGINE-ALIGNMENT-2026-08-18.md finding: fleet_executor.py deliberately pins
# pdt_gate_mode="margin_pdt" for all 3 fleet arms (safe-3/risky-1/risky-3) because it
# never computed settled_cash_available/same_day_entries_used — so no fleet order was
# EVER checked against a settled-cash pool, and nothing capped fleet's same-day entry
# COUNT the way core's max_same_day_roundtrips does. Fixing that WITHOUT flipping
# fleet's pdt_gate_mode (a separate, J-owned decision — see fleet_executor.finalize's
# own blast-radius comment) means fleet needs to run this same settlement math
# independent of the mode dispatch below. Rather than hand-rolling a second copy of the
# comparisons (the exact "guard exists on one path only" bug class this fix closes —
# L184 "reuse the ONE implementation, never re-inline" doctrine), this inline block was
# extracted VERBATIM into
# this standalone pure function. check_order's own cash_settlement branch below now
# just calls it — byte-identical behavior (same codes, same messages, same order of
# checks; pinned by test_risk_gate.py's existing cash_settlement suite, unmodified).
# fleet_executor.finalize calls this SAME function directly, independent of
# pdt_gate_mode, for its own new settlement pre-gate (backtest/tests/
# test_fleet_settlement_gate_2026_08_18.py).
def check_settlement(
    account: str,
    *,
    premium: Any,
    proposed_qty: Any,
    settled_cash_available: Any,
    same_day_entries_used: Any,
    params: Mapping[str, Any],
) -> Optional["Deny"]:
    """PURE. The cash-settlement / GFV-aware Rule 7 check. Returns None when the
    order clears settlement; a Deny(CODE_UNREADABLE_INPUT or CODE_SETTLEMENT)
    otherwise. Self-validates `premium`/`proposed_qty` (fail-closed on bad input)
    so it is safe to call STANDALONE — it does not assume a caller already ran
    check_order's own rule-0 validation on these two fields. check_order's call
    site (below) already has them pre-validated by its own rule 0, so this repeats
    a cheap, always-passing check there — never a behavior change on that path."""
    if _is_bad_number(premium) or _as_float(premium) <= 0:
        return Deny(
            CODE_UNREADABLE_INPUT, f"premium must be a readable number > 0 (got {premium!r})"
        )
    if _is_bad_number(proposed_qty):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"proposed_qty is missing/NaN/unparseable ({proposed_qty!r})",
        )
    _qty_f = _as_float(proposed_qty)
    if _qty_f != int(_qty_f) or _qty_f <= 0:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"proposed_qty must be a positive whole number (got {proposed_qty!r})",
        )
    premium_f = _as_float(premium)
    qty_i = int(_qty_f)

    # NEW 2026-07-14: gates on SETTLED cash (GFV/Reg-T aware), not a trade
    # count. Both inputs are REQUIRED in this mode — fail closed, matching
    # every other hard-halt rule in this function; a caller that flips a
    # cash account into this mode without wiring the ledger gets denies,
    # never silent no-op allows.
    if same_day_entries_used is None or _is_bad_number(same_day_entries_used):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"same_day_entries_used is required under pdt_gate_mode=cash_settlement "
            f"and must be a readable number (got {same_day_entries_used!r})",
        )
    if settled_cash_available is None or _is_bad_number(settled_cash_available):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"settled_cash_available is required under pdt_gate_mode=cash_settlement "
            f"and must be a readable number (got {settled_cash_available!r})",
        )
    entries_used_f = _as_float(same_day_entries_used)
    if entries_used_f < 0 or entries_used_f != int(entries_used_f):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"same_day_entries_used must be a non-negative whole number (got "
            f"{same_day_entries_used!r})",
        )
    entries_used_i = int(entries_used_f)
    settled_f = _as_float(settled_cash_available)
    if settled_f < 0:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"settled_cash_available must be >= 0 (got {settled_f})",
        )

    max_rt_raw = params.get("max_same_day_roundtrips", DEFAULT_MAX_SAME_DAY_ROUNDTRIPS)
    if _is_bad_number(max_rt_raw):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "params.max_same_day_roundtrips present but unreadable",
        )
    max_rt = int(_as_float(max_rt_raw))

    # Belt-and-suspenders sanity cap.
    if entries_used_i >= max_rt:
        return Deny(
            CODE_SETTLEMENT,
            f"{account}: {entries_used_i} same-day entries already placed >= sanity cap "
            f"{max_rt} (params.max_same_day_roundtrips)",
        )

    # The real cash-account constraint: this order's notional must be
    # covered by TODAY's still-settled pool, without reaching into today's
    # (still-unsettled, T+1) closing proceeds — the GFV pattern.
    notional_preview = premium_f * qty_i * 100.0
    if notional_preview > settled_f:
        return Deny(
            CODE_SETTLEMENT,
            f"{account}: notional ${notional_preview:,.0f} exceeds settled cash remaining "
            f"${settled_f:,.0f} today — would fund from today's unsettled proceeds "
            f"(Good Faith Violation risk)",
        )
    return None


# --- DAILY PREMIUM BUDGET (2026-08-28) ---------------------------------------
#
# WHY: over 42 days the book deployed $141,641 of premium to net +$1,317. 48% of
# all entries were placed while that arm was ALREADY RED on the day, and those
# re-deployments carry the losses. Battery + full OP-11 scorecard:
# analysis/recommendations/daily-premium-budget.json
# (script: backtest/autoresearch/daily_premium_budget_battery.py).
#
# TWO SHAPES, selected by params.daily_premium_budget_loss_armed:
#   loss_armed=True  (DEFAULT) -- the budget binds only once the arm has booked a
#       net-negative realised P&L this session. A winning trend day is untouched.
#       This is the shape that passes anchor-no-regression (-5.3% vs the flat
#       cap's -32.3%): a flat cap trims size on exactly the trend days where the
#       right-tail edge lives.
#   loss_armed=False -- flat cap from the session's first entry.
#
# EQUITY-AWARE (J 2026-08-28): prefer `daily_premium_budget_pct_of_equity`. A
# fixed $700 is 14% of a $5k account but 7% of a $10k one -- a dollar-only budget
# silently TIGHTENS as the account grows, which is backwards. On the real-fills
# tape the percentage form is also FLATTER across its band (6-16% all land within
# ~$320 of each other) where the dollar form spikes at $700 and decays either
# side; a flat response curve is the less curve-fit parameterisation.
#
# OFF BY DEFAULT. With `daily_premium_budget_dollars` absent from params this
# function returns None on every call and check_order is byte-identical to its
# pre-2026-08-28 behavior. Pinned by
# backtest/tests/test_daily_premium_budget_2026_08_28.py.
#
# FAIL-CLOSED, but only once armed: the two new inputs are REQUIRED (deny on
# unreadable) exactly when the budget param is present -- the same conditional-
# requirement pattern `check_settlement` uses for settled_cash_available. That
# keeps every existing caller working unchanged while refusing to guess at a
# spend total when the rule is live.
#
# Extracted as a standalone pure function (not inlined) so fleet_executor.py can
# call the IDENTICAL math for the fleet arms, which do not route through
# check_order's cash_settlement branch -- L184 "reuse the ONE implementation,
# never re-inline", the same bug class check_settlement was extracted to close.
def check_daily_premium_budget(
    account: str,
    *,
    premium: Any,
    proposed_qty: Any,
    premium_spent_today: Any,
    realized_pnl_today: Any,
    params: Optional[Mapping[str, Any]],
    start_of_day_equity: Any = None,
) -> Optional[RiskDecision]:
    """Deny when this entry would push the arm past its session premium budget.

    Returns None when the rule is OFF or the order passes; a `Deny` otherwise,
    so callers can chain it like `check_settlement`.

    Args:
        account: account alias, for the message only.
        premium: option mid price per contract (dollars).
        proposed_qty: contracts requested.
        premium_spent_today: premium ALREADY deployed by this arm this session
            (dollars, entries only). Required once the rule is on.
        realized_pnl_today: this arm's realised P&L so far this session
            (dollars, net). Required once the rule is on AND loss_armed.
        params: the account's params mapping.
    """
    if params is None or not isinstance(params, Mapping):
        return Deny(CODE_UNREADABLE_INPUT, "params is missing or not a mapping")

    pct_raw = params.get("daily_premium_budget_pct_of_equity")
    dollars_raw = params.get("daily_premium_budget_dollars")
    if pct_raw is None and dollars_raw is None:
        return None  # rule OFF -- no new input requirements, no behavior change

    # PCT is the preferred form: a fixed dollar budget is a different fraction of
    # a $2k account than a $10k one, so a $-only rule silently tightens as the
    # account grows. When BOTH are set the TIGHTER wins -- the same "tighter of
    # the two" convention RISK_CAP and the v15 tier gate already use, so a
    # dollar figure can act as an absolute ceiling on top of the percentage.
    caps: list[tuple[float, str]] = []

    if pct_raw is not None:
        if _is_bad_number(pct_raw):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "params.daily_premium_budget_pct_of_equity present but unreadable "
                f"({pct_raw!r})",
            )
        pct = _as_float(pct_raw)
        if not (0 < pct <= 1):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "params.daily_premium_budget_pct_of_equity must be a fraction in "
                f"(0, 1] -- got {pct}. (0.12 means 12%, not 12.)",
            )
        if start_of_day_equity is None or _is_bad_number(start_of_day_equity):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "start_of_day_equity is required when "
                "params.daily_premium_budget_pct_of_equity is set and must be a "
                f"readable number (got {start_of_day_equity!r})",
            )
        sod = _as_float(start_of_day_equity)
        if sod <= 0:
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"start_of_day_equity must be > 0 (got {sod})",
            )
        caps.append((pct * sod, f"{pct:.0%} of ${sod:,.0f} start-of-day equity"))

    if dollars_raw is not None:
        if _is_bad_number(dollars_raw):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "params.daily_premium_budget_dollars present but unreadable "
                f"({dollars_raw!r})",
            )
        budget_d = _as_float(dollars_raw)
        if budget_d <= 0:
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"params.daily_premium_budget_dollars must be > 0 (got {budget_d})",
            )
        caps.append((budget_d, f"${budget_d:,.0f} absolute"))

    budget, budget_basis = min(caps, key=lambda c: c[0])

    for name, value in (("premium", premium), ("proposed_qty", proposed_qty)):
        if _is_bad_number(value):
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"{name} is missing/NaN/unparseable ({value!r})",
            )
    if premium_spent_today is None or _is_bad_number(premium_spent_today):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "premium_spent_today is required when a daily premium budget is set "
            f"and must be a readable number (got {premium_spent_today!r})",
        )
    spent = _as_float(premium_spent_today)
    if spent < 0:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"premium_spent_today must be >= 0 (got {spent})",
        )

    # loss_armed: the budget only binds once the session is already red.
    loss_armed = params.get("daily_premium_budget_loss_armed", True)
    if not isinstance(loss_armed, bool):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "params.daily_premium_budget_loss_armed must be a bool (got "
            f"{type(loss_armed).__name__})",
        )
    if loss_armed:
        if realized_pnl_today is None or _is_bad_number(realized_pnl_today):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "realized_pnl_today is required when the daily premium budget is "
                "loss-armed and must be a readable number (got "
                f"{realized_pnl_today!r})",
            )
        if _as_float(realized_pnl_today) >= 0:
            return None  # session not red yet -- budget does not bind

    notional = _as_float(premium) * _as_float(proposed_qty) * 100.0
    if spent + notional > budget:
        armed_note = (
            " (armed: arm is already red today)"
            if loss_armed
            else " (flat budget)"
        )
        return Deny(
            CODE_DAILY_PREMIUM_BUDGET,
            f"{account}: ${spent:,.0f} premium already deployed today + this "
            f"order's ${notional:,.0f} exceeds the session budget ${budget:,.0f} "
            f"({budget_basis}){armed_note}",
        )
    return None


def check_order(
    account: str,
    *,
    equity: Any,
    start_of_day_equity: Any,
    proposed_qty: Any,
    premium: Any,
    setup_name: Any,
    current_position_status: Any,
    day_trades_used_5d: Any,
    kill_switch_tripped: Any,
    prior_stops_today: Any,
    params: Optional[Mapping[str, Any]],
    settled_cash_available: Any = None,
    same_day_entries_used: Any = None,
    premium_spent_today: Any = None,
    realized_pnl_today: Any = None,
) -> RiskDecision:
    """Decide whether ONE proposed option order may be placed.

    Pure function: no I/O, no mutation. Returns an `Allow` or a `Deny(code,
    reason)`. The first failing rule (in the order documented at module top)
    determines the result.

    Args:
        account: account alias, used only for messages (e.g. "Gamma-Safe-2").
        equity: current account equity (dollars).
        start_of_day_equity: equity at session open — kill-switch baseline.
        proposed_qty: number of contracts the strategy wants to buy.
        premium: option mid price per contract (dollars; *100 = per-contract $).
        setup_name: the named playbook setup driving this entry.
        current_position_status: open-position state. Treated as FLAT only when
            it is exactly the string "flat"/"none"/"" (case-insensitive) or
            None-equivalent sentinel handled below; ANY other truthy value is a
            live position -> NOT_FLAT. (Defensive: an unrecognised status is
            treated as "position open", the safe direction.)
        day_trades_used_5d: day-trades used in the rolling 5 business days.
            Read ONLY when params.pdt_gate_mode == "margin_pdt" (legacy);
            still validated as a well-formed number regardless of mode, so
            every existing caller keeps passing it unchanged.
        kill_switch_tripped: bool latch — True if the account's daily kill
            switch has already fired today.
        prior_stops_today: collection of setup names that have ALREADY stopped
            out today (list/set/tuple). Membership of `setup_name` -> deny.
        params: the account's params.json mapping (per_trade_risk_cap_pct,
            daily_loss_kill_switch_pct, min_contracts,
            v15_max_premium_pct_of_account, first_entry_after_stop_blocked,
            pdt_gate_mode, max_same_day_roundtrips).
        settled_cash_available: dollars of TODAY's settled-cash pool still
            uncommitted (see setup/scripts/settlement_ledger.py). REQUIRED
            (fail-closed) when params.pdt_gate_mode == "cash_settlement";
            ignored in "margin_pdt" mode.
        same_day_entries_used: count of entries already placed today.
            REQUIRED (fail-closed) when params.pdt_gate_mode ==
            "cash_settlement"; ignored in "margin_pdt" mode.
        premium_spent_today: dollars of option premium this arm has ALREADY
            deployed this session (entries only). REQUIRED (fail-closed) when
            params.daily_premium_budget_dollars is set; ignored when absent.
        realized_pnl_today: this arm's net realised P&L so far this session.
            REQUIRED (fail-closed) when the budget is set AND
            params.daily_premium_budget_loss_armed (its default) is True.

    Returns:
        RiskDecision — Allow on a clean order, else Deny with a stable code.
    """
    # ---------------------------------------------------------------------
    # 0. FAIL CLOSED on unreadable inputs. This is the load-bearing safety
    #    property: deny new orders whenever ANY required value is missing,
    #    None, NaN, or unparseable. Checked FIRST so no downstream rule can
    #    read a bad value. (SEC 15c3-5: reject on uncertainty.)
    # ---------------------------------------------------------------------
    if params is None or not isinstance(params, Mapping):
        return Deny(CODE_UNREADABLE_INPUT, "params is missing or not a mapping")

    # kill_switch_tripped must be an explicit, unambiguous boolean. None/NaN/
    # "maybe" is uncertainty about whether trading is halted -> deny.
    if kill_switch_tripped is None or not isinstance(kill_switch_tripped, bool):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "kill_switch_tripped must be an explicit bool (got "
            f"{type(kill_switch_tripped).__name__})",
        )

    for name, value in (
        ("equity", equity),
        ("start_of_day_equity", start_of_day_equity),
        ("proposed_qty", proposed_qty),
        ("premium", premium),
        ("day_trades_used_5d", day_trades_used_5d),
    ):
        if _is_bad_number(value):
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"{name} is missing/NaN/unparseable ({value!r})",
            )

    equity_f = _as_float(equity)
    sod_equity_f = _as_float(start_of_day_equity)
    qty_i = _as_float(proposed_qty)
    premium_f = _as_float(premium)
    day_trades_f = _as_float(day_trades_used_5d)

    # Domain sanity — a non-positive equity / SoD / premium, or a fractional or
    # non-positive contract count, is nonsensical input, not a tradeable order.
    if equity_f <= 0:
        return Deny(CODE_UNREADABLE_INPUT, f"equity must be > 0 (got {equity_f})")
    if sod_equity_f <= 0:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"start_of_day_equity must be > 0 (got {sod_equity_f})",
        )
    if premium_f <= 0:
        return Deny(CODE_UNREADABLE_INPUT, f"premium must be > 0 (got {premium_f})")
    if qty_i != int(qty_i) or qty_i <= 0:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"proposed_qty must be a positive whole number (got {proposed_qty!r})",
        )
    if day_trades_f < 0 or day_trades_f != int(day_trades_f):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"day_trades_used_5d must be a non-negative whole number (got "
            f"{day_trades_used_5d!r})",
        )
    qty_i = int(qty_i)
    day_trades_i = int(day_trades_f)

    if not isinstance(setup_name, str) or not setup_name.strip():
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"setup_name is missing or blank ({setup_name!r})",
        )

    # Required params must be present AND numerically readable.
    risk_cap_raw = params.get("per_trade_risk_cap_pct")
    kill_pct_raw = params.get("daily_loss_kill_switch_pct")
    min_contracts_raw = params.get("min_contracts")
    if _is_bad_number(risk_cap_raw):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "params.per_trade_risk_cap_pct missing/unreadable",
        )
    if _is_bad_number(kill_pct_raw):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "params.daily_loss_kill_switch_pct missing/unreadable",
        )
    if _is_bad_number(min_contracts_raw):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "params.min_contracts missing/unreadable",
        )
    risk_cap_pct = _as_float(risk_cap_raw)
    kill_pct = _as_float(kill_pct_raw)
    min_contracts = int(_as_float(min_contracts_raw))

    # ---------------------------------------------------------------------
    # 1. DAILY KILL SWITCH (CLAUDE.md Rule 5; isolated per account).
    #    Two independent triggers — either halts THIS account for the day.
    # ---------------------------------------------------------------------
    if kill_switch_tripped:
        return Deny(
            CODE_KILL_SWITCH,
            f"{account}: daily kill switch already tripped — account halted for the day",
        )
    # Realised-drawdown trigger: equity at/under the day's floor.
    kill_floor = sod_equity_f * (1.0 - kill_pct)
    if equity_f <= kill_floor:
        return Deny(
            CODE_KILL_SWITCH,
            f"{account}: equity ${equity_f:,.0f} <= kill floor ${kill_floor:,.0f} "
            f"({kill_pct:.0%} of SoD ${sod_equity_f:,.0f}) — day closed, no revenge trades",
        )
    # THIRD, independent trigger (PREREG-TIGHT-LADDER-2026-08-28 control #5,
    # 2026-08-29): an absolute-dollar floor ALONGSIDE the pct floor above --
    # this does not replace or weaken it, both stay armed. Rationale (from the
    # prereg): daily_loss_kill_switch_pct=0.30 is ~$1,590 on a $5.3K account,
    # far looser than the -$400 control the prereg specifies. Reuses
    # equity_f/sod_equity_f -- already mandatory, already-validated inputs on
    # EVERY existing caller (unlike DAILY_PREMIUM_BUDGET's realized_pnl_today,
    # which NO caller wires with real data today) -- so arming this key cannot
    # newly deny every order the way a fresh REQUIRED kwarg would. Rule 4 (no
    # adding without a new trigger) keeps the book flat before any new entry is
    # evaluated, so in the common case equity_f at this point carries no open-
    # position mark -- i.e. equity_f - sod_equity_f already reads as today's
    # realized P&L without a second, separately-computed realized-only feed.
    # Absent key = OFF, byte-identical to before this ship.
    dollar_stop_raw = params.get("daily_loss_kill_switch_dollars")
    if dollar_stop_raw is not None:
        if _is_bad_number(dollar_stop_raw):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "params.daily_loss_kill_switch_dollars present but unreadable",
            )
        dollar_stop = _as_float(dollar_stop_raw)
        if dollar_stop <= 0:
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"params.daily_loss_kill_switch_dollars must be > 0 (got {dollar_stop})",
            )
        dollar_floor = sod_equity_f - dollar_stop
        if equity_f <= dollar_floor:
            return Deny(
                CODE_DAILY_LOSS_DOLLARS,
                f"{account}: equity ${equity_f:,.0f} <= dollar-loss floor ${dollar_floor:,.0f} "
                f"(${dollar_stop:,.0f} daily loss stop from SoD ${sod_equity_f:,.0f}) — day "
                "closed, no revenge trades",
            )

    # ---------------------------------------------------------------------
    # 2. DAY-TRADE / SETTLEMENT AWARENESS (CLAUDE.md Rule 7). Mode selected by
    #    params.pdt_gate_mode (see module docstring + check_order docstring).
    # ---------------------------------------------------------------------
    pdt_mode = str(params.get("pdt_gate_mode") or "margin_pdt").strip().lower()

    if pdt_mode == "cash_settlement":
        # EXTRACTED 2026-08-18 into check_settlement (module-level, above) so
        # fleet_executor.py's own settlement pre-gate can reuse the IDENTICAL
        # math without a parallel reimplementation (L184 "one implementation").
        # premium_f/qty_i are already validated by rule 0 above — check_settlement
        # re-validates them too (so it's safe to call standalone), which is a
        # no-op here since they're already known-good. Byte-identical to the
        # inline block this replaced: same codes, same messages, same order.
        _denial = check_settlement(
            account,
            premium=premium_f,
            proposed_qty=qty_i,
            settled_cash_available=settled_cash_available,
            same_day_entries_used=same_day_entries_used,
            params=params,
        )
        if _denial is not None:
            return _denial
    else:
        # LEGACY margin_pdt (function-level default when params.pdt_gate_mode
        # is absent — every pre-2026-07-14 caller/test is byte-identical).
        # >=3 day-trades in rolling 5d AND equity < $25K -> deny.
        if day_trades_i >= PDT_DAY_TRADE_LIMIT and equity_f < PDT_EQUITY_THRESHOLD:
            return Deny(
                CODE_PDT,
                f"{account}: {day_trades_i} day-trades in 5d at equity ${equity_f:,.0f} "
                f"< ${PDT_EQUITY_THRESHOLD:,.0f} — PDT rule blocks a 4th day-trade",
            )

    # ---------------------------------------------------------------------
    # 3. FLAT BEFORE ENTRY (CLAUDE.md Rule 4 + broker-source-of-truth C11).
    #    Any non-flat status blocks a NEW entry. Unknown status = treat as
    #    open (safe direction).
    # ---------------------------------------------------------------------
    if not _is_flat(current_position_status):
        return Deny(
            CODE_NOT_FLAT,
            f"{account}: position already open (status={current_position_status!r}) — "
            "flatten before a new entry (Rule 4: no adding without a new trigger)",
        )

    # ---------------------------------------------------------------------
    # 4. FIRST-ENTRY-AFTER-STOP LOCK: DELETED (J directive 2026-07-02 —
    #    "Gone. We no longer have it in our codebase."). prior_stops_today is
    #    accepted but IGNORED (API compat/journaling); a same-setup re-entry
    #    after a stop is ALLOWED. Guard: test_risk_gate.py absence pins.
    # ---------------------------------------------------------------------

    # ---------------------------------------------------------------------
    # 5. MIN CONTRACTS (CLAUDE.md Rule 6: >=3 = 2 TP + 1 runner).
    # ---------------------------------------------------------------------
    if qty_i < min_contracts:
        return Deny(
            CODE_MIN_CONTRACTS,
            f"{account}: proposed_qty {qty_i} < minimum {min_contracts} "
            "(need 2 TP + 1 runner)",
        )

    # ---------------------------------------------------------------------
    # 5b. MAX CONTRACTS PER ENTRY (PREREG-TIGHT-LADDER-2026-08-28 control #1,
    #     2026-08-29). BACKSTOP ONLY -- callers are expected to pre-shrink qty
    #     via cap_entry_qty() (see that function's module comment) so this
    #     should never fire in normal operation; it exists so a caller that
    #     skips the pre-check still cannot place an oversized order. Absent
    #     key = OFF, byte-identical to before this ship.
    # ---------------------------------------------------------------------
    max_contracts_raw = params.get("max_contracts_per_entry")
    if max_contracts_raw is not None:
        if _is_bad_number(max_contracts_raw):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "params.max_contracts_per_entry present but unreadable",
            )
        max_contracts_per_entry = int(_as_float(max_contracts_raw))
        if qty_i > max_contracts_per_entry:
            return Deny(
                CODE_MAX_CONTRACTS_PER_ENTRY,
                f"{account}: proposed_qty {qty_i} > max_contracts_per_entry "
                f"{max_contracts_per_entry}",
            )

    # ---------------------------------------------------------------------
    # 6. PER-TRADE RISK CAP (CLAUDE.md Rule 6) AND v15 per-tier MAX-PREMIUM
    #    hard gate. Notional = premium * qty * 100. The EFFECTIVE cap is the
    #    tighter (smaller) of the two — premium tier may be stricter than the
    #    blanket risk cap. The v15 tier gate is a SEPARATE code so logs show
    #    which constraint actually bound.
    # ---------------------------------------------------------------------
    notional = premium_f * qty_i * 100.0
    risk_cap_dollars = equity_f * risk_cap_pct

    tier_pct = _max_premium_pct_for_equity(
        params.get("v15_max_premium_pct_of_account"), equity_f
    )
    # When the table is present in params it MUST resolve — an unresolvable
    # tier (malformed row or equity outside every band) is uncertainty about a
    # hard gate, so fail closed rather than silently dropping it.
    if "v15_max_premium_pct_of_account" in params and tier_pct is None:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"{account}: v15_max_premium_pct_of_account present but no tier covers "
            f"equity ${equity_f:,.0f} (or a tier row is malformed)",
        )

    # Session deployment budget (2026-08-28). No-op unless
    # params.daily_premium_budget_dollars is set -- see check_daily_premium_budget.
    _denial = check_daily_premium_budget(
        account,
        premium=premium_f,
        proposed_qty=qty_i,
        premium_spent_today=premium_spent_today,
        realized_pnl_today=realized_pnl_today,
        params=params,
        start_of_day_equity=sod_equity_f,
    )
    if _denial is not None:
        return _denial

    # Risk cap first (Rule 6 is the blanket rule)...
    if notional > risk_cap_dollars:
        return Deny(
            CODE_RISK_CAP,
            f"{account}: notional ${notional:,.0f} exceeds per-trade cap "
            f"${risk_cap_dollars:,.0f} ({risk_cap_pct:.0%} of ${equity_f:,.0f})",
        )
    # ...then the (usually tighter) v15 per-tier premium gate, reported distinctly.
    if tier_pct is not None:
        tier_cap_dollars = equity_f * tier_pct
        if notional > tier_cap_dollars:
            return Deny(
                CODE_MAX_PREMIUM_TIER,
                f"{account}: notional ${notional:,.0f} exceeds v15 tier max-premium "
                f"${tier_cap_dollars:,.0f} ({tier_pct:.0%} of ${equity_f:,.0f})",
            )

    # ---------------------------------------------------------------------
    # 6b. MAX POSITION DOLLARS (PREREG-TIGHT-LADDER-2026-08-28 control #2,
    #     2026-08-29). Flat $ ceiling on notional, ADDITIONAL to and typically
    #     tighter than the pct-of-equity RISK_CAP above at current ($5K-ish)
    #     account sizes -- both bind, tighter wins (same AND convention RISK_CAP
    #     and MAX_PREMIUM_TIER already use with each other). BACKSTOP ONLY, see
    #     cap_entry_qty()'s module comment -- callers pre-shrink via that
    #     function so this should never fire in normal operation. Absent key =
    #     OFF, byte-identical to before this ship.
    # ---------------------------------------------------------------------
    max_position_raw = params.get("max_position_dollars")
    if max_position_raw is not None:
        if _is_bad_number(max_position_raw):
            return Deny(
                CODE_UNREADABLE_INPUT,
                "params.max_position_dollars present but unreadable",
            )
        max_position_dollars = _as_float(max_position_raw)
        if notional > max_position_dollars:
            return Deny(
                CODE_MAX_POSITION_DOLLARS,
                f"{account}: notional ${notional:,.0f} exceeds max_position_dollars "
                f"${max_position_dollars:,.0f}",
            )

    return Allow(
        f"{account}: qty {qty_i} @ ${premium_f:.2f} = ${notional:,.0f} within all caps"
    )


# --- WP-10: cap-aware affordability (the single source of truth for "would the
#            LIVE order gate place this?", reused by the real-fills simulator) ----
#
# L180 / C11 / C14: `simulator_real.simulate_trade_real` historically filled the
# caller-supplied `qty` cap-BLIND — so a real-fills sweep could report a glowing
# expectancy on orders that `check_order` denies live (e.g. the WP-8 1DTE-ATM
# "doubler": qty3 notional $748 > Safe $2K cap $600 -> BLOCK[RISK_CAP]; qty2 ->
# BLOCK[MIN_CONTRACTS], no auto-reduce). The lever that lifts per-trade premium
# (DTE / ITM-depth / wider stop) pushes notional THROUGH a FIXED per-trade $-cap.
#
# These two pure helpers expose EXACTLY the per-order sizing math `check_order`
# uses (notional = premium*qty*100 vs the tighter of RISK_CAP and the v15 tier
# gate, plus the min_contracts floor) so a consumer never re-types the cap
# literals (the C14 dead-knob/divergence trap). `test_risk_gate` cross-checks
# `order_affordable` against `check_order` over a grid so the two implementations
# can NEVER silently diverge. Both FAIL CLOSED: any unreadable input or an equity
# outside every premium tier -> "not affordable" (skip), matching check_order's
# deny-on-uncertainty stance.


def _effective_per_trade_cap_dollars(
    equity: float, params: Mapping[str, Any]
) -> Optional[float]:
    """The binding per-trade dollar cap = tighter of RISK_CAP and the v15 tier gate.

    Returns None on any unreadable input or an equity not covered by the premium
    tier table (uncertainty about a hard gate -> caller must treat as unaffordable).
    """
    if params is None or not isinstance(params, Mapping):
        return None
    if _is_bad_number(equity):
        return None
    equity_f = _as_float(equity)
    if equity_f <= 0:
        return None
    risk_cap_raw = params.get("per_trade_risk_cap_pct")
    if _is_bad_number(risk_cap_raw):
        return None
    cap = equity_f * _as_float(risk_cap_raw)
    if "v15_max_premium_pct_of_account" in params:
        tier_pct = _max_premium_pct_for_equity(
            params.get("v15_max_premium_pct_of_account"), equity_f
        )
        if tier_pct is None:  # table present but no tier covers equity -> uncertainty
            return None
        cap = min(cap, equity_f * tier_pct)
    return cap


def order_affordable(
    *, equity: Any, premium: Any, qty: Any, params: Optional[Mapping[str, Any]]
) -> bool:
    """True iff an order of `qty` contracts at `premium` clears the per-order sizing
    gates (MIN_CONTRACTS + RISK_CAP + MAX_PREMIUM_TIER) that check_order enforces live.

    Fail-closed: any unreadable input -> False (treat as not placeable). This is the
    SAME cap math as check_order (L180 single source of truth); the qty is also held
    to the params `min_contracts` floor, so qty below the minimum is unaffordable even
    when the notional would fit (mirrors live BLOCK[MIN_CONTRACTS]).
    """
    if params is None or not isinstance(params, Mapping):
        return False
    if _is_bad_number(premium) or _is_bad_number(qty):
        return False
    premium_f = _as_float(premium)
    qty_f = _as_float(qty)
    if premium_f <= 0 or qty_f <= 0 or qty_f != int(qty_f):
        return False
    qty_i = int(qty_f)
    min_contracts_raw = params.get("min_contracts")
    if _is_bad_number(min_contracts_raw):
        return False
    if qty_i < int(_as_float(min_contracts_raw)):
        return False
    cap = _effective_per_trade_cap_dollars(equity, params)
    if cap is None:
        return False
    notional = premium_f * qty_i * 100.0
    return notional <= cap


def max_affordable_qty(
    *, equity: Any, premium: Any, params: Optional[Mapping[str, Any]]
) -> int:
    """Largest contract qty that `order_affordable` accepts (>= min_contracts), or 0
    when even the min_contracts floor is unaffordable / inputs are unreadable.

    For cap-aware SIZING. Note the live gate does NOT auto-reduce (it denies the
    proposed qty outright), so a consumer that must mirror live should compare the
    PROPOSED qty against this and skip when it exceeds the affordable max.
    """
    if params is None or not isinstance(params, Mapping):
        return 0
    if _is_bad_number(premium):
        return 0
    premium_f = _as_float(premium)
    if premium_f <= 0:
        return 0
    min_contracts_raw = params.get("min_contracts")
    if _is_bad_number(min_contracts_raw):
        return 0
    min_contracts = int(_as_float(min_contracts_raw))
    cap = _effective_per_trade_cap_dollars(equity, params)
    if cap is None:
        return 0
    per_contract = premium_f * 100.0
    max_qty = int(cap // per_contract)
    if max_qty < min_contracts:
        return 0
    return max_qty


# --- TIGHT-LADDER PER-ENTRY CAPS (2026-08-29) --------------------------------
#
# PREREG-TIGHT-LADDER-2026-08-28.md section 2 + Addendum 1 (S1.1-1.3): the
# forward-test window opening 2026-09-01 09:30 ET is written against controls
# this engine did not yet enforce. Two ADDITIONAL, INDEPENDENT ceilings on top
# of the existing per_trade_risk_cap_pct / v15_max_premium_pct_of_account
# (both caps bind -- tighter wins, same "AND" convention those two already use
# with each other):
#   control #1  max_contracts_per_entry -- e.g. 5. A flat contract-count
#               ceiling; the existing caps are all %-of-equity/$-of-account and
#               none of them bound *count* directly (position_sizing_tiers'
#               elite_qty reaches 8/12/15/20 well above 5 at current equity).
#   control #2  max_position_dollars -- e.g. 1000. A flat $ ceiling on
#               premium*qty*100, tighter in practice than the 30%/50%-of-
#               equity risk cap at current ($5K-ish) account sizes.
#   control #3  the CONFLICT rule: if even min_contracts contracts would
#               breach max_position_dollars (premium > max_position_dollars /
#               (min_contracts*100), e.g. > $3.33 at $1,000/3), do not shrink
#               below min_contracts (Rule 6: 2 sold at TP1 + 1 runner needs the
#               floor) -- SKIP the entry instead.
#
# Both keys OFF by default (absent = the function is a pure passthrough, byte-
# identical to before this ship -- neither key exists in any params file until
# this exact commit arms them).
#
# WHY THIS IS A SEPARATE FUNCTION, NOT check_daily_premium_budget or
# max_affordable_qty: check_daily_premium_budget (2026-08-28) caps CUMULATIVE
# premium DEPLOYED across a whole SESSION and is reserved for a different,
# already-pre-registered, currently-shadow-only forward test (loss-armed-
# budget-forward-prereg-2026-08-28.json, forward window opens the SAME date as
# this ship) -- arming its params keys here would silently graduate THAT
# experiment out of shadow mid-window, which is exactly the kind of
# uncoordinated collision OP-33/C15 exist to prevent. max_affordable_qty caps
# against the EXISTING pct-of-equity rule; this function's caps are NEW,
# additive, flat-dollar/flat-count rules with their own floor-conflict
# semantics (SKIP, never a sub-floor entry) that max_affordable_qty does not
# have (it silently returns 0 on a deadlock; callers here need to know WHY, to
# log a distinct, countable reason -- Addendum 1's own point that this must be
# "logged... so it is countable").
#
# CALLERS: setup/scripts/heartbeat_core.py#_execute (core safe-2/bold-2) and
# automation/state/fleet/fleet_executor.py#finalize (fleet safe-3/risky-1) both
# call this BEFORE the existing max_affordable_qty-based shrink and BEFORE
# check_order, so a SKIP short-circuits without ever proposing an order. The
# MAX_CONTRACTS_PER_ENTRY / MAX_POSITION_DOLLARS rules inside check_order below
# are a backstop for any FUTURE caller that forgets this pre-check -- they
# should never fire in normal operation (mirrors how RISK_CAP is both pre-
# shrunk via max_affordable_qty AND independently re-checked inside
# check_order).
#
# INVARIANT (matches max_affordable_qty's own documented contract): the `qty`
# this returns is always EITHER None with skip=True (no legal qty exists), OR
# an int >= params.min_contracts. It can never return a qty in (0,
# min_contracts) -- composing this with the existing affordability shrink
# (which has the identical invariant) can therefore never produce a qty < 3
# entry; the two either agree on a legal qty >= min_contracts or one of them
# refuses the whole order. Cross-checked by
# test_tight_ladder_controls_2026_08_29.py::test_never_produces_a_sub_floor_qty.
def cap_entry_qty(
    *, proposed_qty: Any, premium: Any, params: Optional[Mapping[str, Any]],
) -> dict:
    """Clamp `proposed_qty` DOWN to fit max_contracts_per_entry AND
    max_position_dollars (both params-gated, both OFF when absent). Never
    raises qty. Returns a dict:
        qty: int|None -- the (possibly clamped) qty, or None when skip=True.
        skip: bool -- True means the CONFLICT rule fired: do not place this
            order at ANY qty >= min_contracts under these caps.
        reason: str|None -- human-readable, set whenever skip=True or an input
            was unreadable.
        capped_by_contracts / capped_by_dollars: bool -- which cap(s) actually
            reduced qty below the input value (both False on a pure passthrough).

    proposed_qty is passed through UNCHANGED (skip=False) when:
      * both params keys are absent (rule OFF), or
      * proposed_qty is None (no sizing tier matched -- a pre-existing, unrelated
        condition; check_order's own rule-0 denies UNREADABLE_INPUT on this
        downstream exactly as it did before this function existed -- mirrors
        _shrink_qty_to_affordable's identical None-passthrough contract).

    premium is required (fails to skip=True) ONLY when max_position_dollars is
    armed AND actually needed to evaluate it. When premium is None (fleet's
    finalize() can be called before a live quote resolves -- SAME contract as
    _shrink_qty_to_affordable), the dollar cap is deferred (not evaluated) and
    only the contract-count cap applies; check_order's rule 0 denies a
    genuinely-missing premium downstream regardless, so this never silently
    permits an unpriced order through.
    """
    _off = {"qty": proposed_qty, "skip": False, "reason": None,
            "capped_by_contracts": False, "capped_by_dollars": False}
    if params is None or not isinstance(params, Mapping):
        return _off
    max_contracts_raw = params.get("max_contracts_per_entry")
    max_dollars_raw = params.get("max_position_dollars")
    if max_contracts_raw is None and max_dollars_raw is None:
        return _off  # rule OFF -- byte-identical, no input validation performed
    if proposed_qty is None:
        return _off  # no tier matched -- unrelated to these caps, pass through

    if _is_bad_number(proposed_qty):
        return {"qty": None, "skip": True,
                "reason": f"proposed_qty is missing/NaN/unparseable ({proposed_qty!r})",
                "capped_by_contracts": False, "capped_by_dollars": False}
    qty_f = _as_float(proposed_qty)
    if qty_f != int(qty_f) or qty_f <= 0:
        return {"qty": None, "skip": True,
                "reason": f"proposed_qty must be a positive whole number (got {proposed_qty!r})",
                "capped_by_contracts": False, "capped_by_dollars": False}
    qty = int(qty_f)

    min_contracts_raw = params.get("min_contracts")
    if _is_bad_number(min_contracts_raw):
        return {"qty": None, "skip": True,
                "reason": "params.min_contracts missing/unreadable",
                "capped_by_contracts": False, "capped_by_dollars": False}
    min_contracts = int(_as_float(min_contracts_raw))

    capped_by_contracts = False
    if max_contracts_raw is not None:
        if _is_bad_number(max_contracts_raw):
            return {"qty": None, "skip": True,
                    "reason": "params.max_contracts_per_entry present but unreadable",
                    "capped_by_contracts": False, "capped_by_dollars": False}
        max_contracts = int(_as_float(max_contracts_raw))
        if max_contracts < 1:
            return {"qty": None, "skip": True,
                    "reason": f"params.max_contracts_per_entry must be >= 1 (got {max_contracts})",
                    "capped_by_contracts": False, "capped_by_dollars": False}
        if qty > max_contracts:
            qty = max_contracts
            capped_by_contracts = True

    capped_by_dollars = False
    premium_f = None
    if max_dollars_raw is not None and premium is not None:
        if _is_bad_number(max_dollars_raw):
            return {"qty": None, "skip": True,
                    "reason": "params.max_position_dollars present but unreadable",
                    "capped_by_contracts": capped_by_contracts, "capped_by_dollars": False}
        max_dollars = _as_float(max_dollars_raw)
        if max_dollars <= 0:
            return {"qty": None, "skip": True,
                    "reason": f"params.max_position_dollars must be > 0 (got {max_dollars})",
                    "capped_by_contracts": capped_by_contracts, "capped_by_dollars": False}
        if _is_bad_number(premium):
            return {"qty": None, "skip": True,
                    "reason": f"premium is missing/NaN/unparseable ({premium!r}) -- required "
                              "once max_position_dollars is set",
                    "capped_by_contracts": capped_by_contracts, "capped_by_dollars": False}
        premium_f = _as_float(premium)
        if premium_f <= 0:
            return {"qty": None, "skip": True,
                    "reason": f"premium must be > 0 (got {premium_f})",
                    "capped_by_contracts": capped_by_contracts, "capped_by_dollars": False}
        dollar_max_qty = int(max_dollars // (premium_f * 100.0))
        if dollar_max_qty < qty:
            qty = dollar_max_qty
            capped_by_dollars = True
    # else: dollar cap absent, OR premium not yet resolved -- deferred (see docstring).

    if qty < min_contracts:
        # CONFLICT RULE (control #3): never take fewer than min_contracts --
        # the ladder needs 2 sold at TP1 + 1 riding. SKIP instead of under-sizing.
        binds = []
        if capped_by_contracts:
            binds.append(f"max_contracts_per_entry={int(_as_float(max_contracts_raw))}")
        if capped_by_dollars:
            binds.append(
                f"max_position_dollars=${_as_float(max_dollars_raw):,.0f} at "
                f"premium ${premium_f:.2f} (min_contracts would cost "
                f"${min_contracts * premium_f * 100.0:,.2f})"
            )
        return {"qty": None, "skip": True,
                "reason": (f"conflict: min_contracts={min_contracts} would violate "
                           f"{' and '.join(binds) or 'a configured cap'} -- SKIP rather than "
                           "under-size below the ladder floor"),
                "capped_by_contracts": capped_by_contracts, "capped_by_dollars": capped_by_dollars}

    return {"qty": qty, "skip": False, "reason": None,
            "capped_by_contracts": capped_by_contracts, "capped_by_dollars": capped_by_dollars}


# --- SIZING-DEADLOCK DIAGNOSTIC (2026-07-30) ---------------------------------
#
# WHY THIS EXISTS. `check_order` already returns an arithmetically honest RISK_CAP
# reason ("notional $426 exceeds per-trade cap $348 (30% of $1,160)"), and that
# string is what the 2026-07-30 ledger carries on all 9 Safe denies. But it is
# arithmetic about ONE PROPOSED ORDER, and a reader — human or downstream monitor —
# cannot tell from it which of two VERY different situations they are looking at:
#
#   (1) SIZING MISS  — the proposal was simply too big; a smaller qty still fits.
#                      max_affordable_qty >= min_contracts. Fix = size down.
#   (2) DEADLOCK     — NO legal qty exists at this premium, because the smallest
#                      order Rule 6 permits (min_contracts) already blows the cap:
#                          premium * min_contracts * 100 > effective_cap
#                      max_affordable_qty == 0. Fix is NOT sizing; the arm is
#                      structurally unable to trade ANY contract at this price.
#
# On 2026-07-30 core Safe hit (2) nine times and the ledger could not say so: at
# equity $1,160.42 the cap is $348.13 and min_contracts is 3, so the arm cannot buy
# ANY contract priced above $1.16 — while ATM 0DTE SPY was $1.42–$2.01 all session.
# That is a silent, total participation loss, and it reads in the log exactly like
# an ordinary oversize deny. This function makes the difference explicit.
#
# CONTRACT — this decides NOTHING.
#   * `check_order` does not call it and its behavior is unchanged. This is pure
#     TELEMETRY, attached to a deny row AFTER the decision is already made.
#   * MONITORING => FAILS OPEN. Every unreadable input returns
#     {"available": False, ...} instead of raising, so a caller can attach it to a
#     log row inside a try/except and a diagnostic bug can never block an entry or
#     break a ledger write. (Contrast check_order, which fails CLOSED because it
#     gates capital.) The two fail-directions are deliberate and opposite.
#   * NO RE-TYPED LITERALS (C14 dead-knob trap): every threshold is obtained by
#     calling `_effective_per_trade_cap_dollars` / `max_affordable_qty` — the SAME
#     helpers `check_order` itself uses — never by re-deriving cap math here. If
#     the caps ever change, this diagnostic changes with them automatically.
#     `test_sizing_deadlock_diag.py` cross-checks `deadlock` against a real
#     `check_order` call over a grid so the two can never silently diverge.
#
# NOTE ON `premium_ceiling`: this is the number an operator actually wants — the
# highest premium at which the arm can place its smallest legal order. Above it the
# arm is blind. It is reported as the exact cap quotient; callers that want a
# quote-safe figure should floor it to the cent (the CLI does).


def explain_block(
    *,
    equity: Any,
    premium: Any,
    params: Optional[Mapping[str, Any]],
    proposed_qty: Any = None,
) -> dict:
    """Explain WHY a per-order sizing refusal happened and WHICH constraint binds.

    Pure + fail-OPEN telemetry (see module comment above). Never raises, never
    decides anything, never consulted by `check_order`.

    Returns a dict that always carries `available`. When True it additionally has:
        min_contracts, risk_cap_pct, risk_cap_dollars, tier_pct, tier_cap_dollars,
        effective_cap_dollars, binding_cap ("risk_cap"|"max_premium_tier"|
        "max_contracts_per_entry"|"max_position_dollars" -- the last two added
        2026-08-29, PREREG-TIGHT-LADDER-2026-08-28.md controls #1/#2),
        max_affordable_qty, premium_ceiling, deadlock, headline.

    `deadlock` is True iff max_affordable_qty == 0 — i.e. not even `min_contracts`
    fits under the effective cap, so no legal order exists at this premium.
    `effective_cap_dollars`/`risk_cap_dollars`/`tier_cap_dollars` stay PCT-cap-only
    (unchanged by this ship) for backward compatibility; `max_affordable_qty`,
    `deadlock`, `binding_cap`, and `headline` reflect the FULL picture including
    max_contracts_per_entry/max_position_dollars when either is set.
    """
    try:
        if params is None or not isinstance(params, Mapping):
            return {"available": False, "why": "params missing or not a mapping"}
        if _is_bad_number(equity) or _is_bad_number(premium):
            return {"available": False, "why": "equity/premium unreadable"}
        equity_f = _as_float(equity)
        premium_f = _as_float(premium)
        if equity_f <= 0 or premium_f <= 0:
            return {"available": False, "why": "equity/premium must be > 0"}
        min_contracts_raw = params.get("min_contracts")
        if _is_bad_number(min_contracts_raw):
            return {"available": False, "why": "params.min_contracts unreadable"}
        min_contracts = int(_as_float(min_contracts_raw))

        cap = _effective_per_trade_cap_dollars(equity_f, params)
        if cap is None:
            # Same uncertainty check_order fails closed on; report it, don't guess.
            return {"available": False,
                    "why": "effective cap unresolvable (bad risk-cap pct, or equity "
                           "outside every v15_max_premium_pct_of_account tier)"}

        risk_cap_pct = _as_float(params.get("per_trade_risk_cap_pct"))
        risk_cap_dollars = equity_f * risk_cap_pct
        tier_pct = _max_premium_pct_for_equity(
            params.get("v15_max_premium_pct_of_account"), equity_f
        ) if "v15_max_premium_pct_of_account" in params else None
        tier_cap_dollars = (equity_f * tier_pct) if tier_pct is not None else None
        binding_cap = ("max_premium_tier"
                       if tier_cap_dollars is not None and tier_cap_dollars < risk_cap_dollars
                       else "risk_cap")

        afford = max_affordable_qty(equity=equity_f, premium=premium_f, params=params)
        ceiling_cap_dollars = cap  # used only for premium_ceiling below

        # PREREG-TIGHT-LADDER-2026-08-28 controls #1/#2 (2026-08-29): `afford` and
        # `cap`/`binding_cap` above are DELIBERATELY unaware of max_contracts_per_entry
        # / max_position_dollars -- max_affordable_qty/_effective_per_trade_cap_dollars
        # are ALSO simulator_real.py's own backtest-side affordability math (WP-10 doc,
        # module top; 19 repo-wide callers as of this ship, several backtest/tools/
        # edge_matrix_*.py research scripts among them). Folding a LIVE-only control
        # into those shared functions would silently change historical backtest
        # results for every one of those callers -- a far larger, unreviewed blast
        # radius than this function's own job (explain a LIVE deny to a human/log).
        # So the tight-ladder awareness is applied HERE ONLY, mirroring
        # cap_entry_qty's own min-contracts-floor logic, exactly so `deadlock` /
        # `headline` / `max_affordable_qty` (this function's OWN output, read by
        # heartbeat_core.py's and fleet_executor.py's live deny telemetry) tell the
        # truth about what check_order will actually do live. Cross-checked by
        # test_sizing_deadlock_diag.py's anti-divergence grid (both directions: a
        # tight-ladder cap can turn a non-deadlock into one, and vice versa it must
        # never SILENTLY widen availability beyond what check_order itself allows).
        if afford > 0:
            max_contracts_raw = params.get("max_contracts_per_entry")
            if max_contracts_raw is not None and not _is_bad_number(max_contracts_raw):
                _mce = int(_as_float(max_contracts_raw))
                if _mce < afford:
                    afford = _mce
                    binding_cap = "max_contracts_per_entry"
        if afford > 0:
            max_position_raw = params.get("max_position_dollars")
            if max_position_raw is not None and not _is_bad_number(max_position_raw):
                _mpd = _as_float(max_position_raw)
                if _mpd > 0:
                    ceiling_cap_dollars = min(ceiling_cap_dollars, _mpd)
                    _dollar_qty = int(_mpd // (premium_f * 100.0))
                    if _dollar_qty < afford:
                        afford = _dollar_qty
                        binding_cap = "max_position_dollars"
        if 0 < afford < min_contracts:
            # CONFLICT (control #3): a ladder cap admits SOME qty but not even
            # min_contracts -- Rule 6 forbids taking fewer, so this is a deadlock
            # exactly like affordability hitting 0, not a smaller legal order.
            afford = 0

        deadlock = (afford == 0)
        # The highest premium at which min_contracts still fits under the cap.
        # Only max_position_dollars (a $ cap) can move this; max_contracts_per_entry
        # (a count ceiling) never affects whether min_contracts itself is eligible.
        premium_ceiling = ceiling_cap_dollars / (min_contracts * 100.0)
        # Quote-safe display value: FLOOR to the cent, never round. Rounding up would
        # print a premium the gate actually refuses (bold-2: ceiling 1.1975 renders as
        # "$1.20", but 5 x $1.20 x 100 = $600 > the $598.76 cap -> still a deadlock).
        ceiling_cents = math.floor(premium_ceiling * 100.0) / 100.0

        # Dollar figure shown in the headline: use whichever cap `binding_cap` names
        # (ceiling_cap_dollars already folds in max_position_dollars; `cap` is the
        # unmodified pct-based figure for the two OLD binding_cap values) -- never
        # print `cap` next to a binding_cap it does not actually describe, and
        # max_contracts_per_entry is a COUNT, not a dollar figure, so it gets its
        # own non-dollar phrasing entirely.
        _headline_cap_dollars = ceiling_cap_dollars if binding_cap == "max_position_dollars" else cap
        if deadlock:
            if binding_cap == "max_contracts_per_entry":
                headline = (
                    f"DEADLOCK: min_contracts {min_contracts} > max_contracts_per_entry "
                    f"{int(_as_float(params.get('max_contracts_per_entry')))} -- NO legal qty "
                    f"exists (min_contracts itself exceeds the contract ceiling)."
                )
            else:
                headline = (
                    f"DEADLOCK: min_contracts {min_contracts} x ${premium_f:.2f} x 100 = "
                    f"${premium_f * min_contracts * 100.0:,.0f} > effective cap "
                    f"${_headline_cap_dollars:,.0f} ({binding_cap}) -- NO legal qty exists at "
                    f"this premium. Ceiling at this equity: ${ceiling_cents:.2f}/contract."
                )
        else:
            if binding_cap == "max_contracts_per_entry":
                headline = (
                    f"SIZING: up to {afford} contracts fit (max_contracts_per_entry ceiling) "
                    f"at ${premium_f:.2f}."
                )
            else:
                headline = (
                    f"SIZING: up to {afford} contracts fit under the ${_headline_cap_dollars:,.0f} "
                    f"cap ({binding_cap}) at ${premium_f:.2f}."
                )

        out = {
            "available": True,
            "min_contracts": min_contracts,
            "risk_cap_pct": round(risk_cap_pct, 6),
            "risk_cap_dollars": round(risk_cap_dollars, 2),
            "tier_pct": (round(tier_pct, 6) if tier_pct is not None else None),
            "tier_cap_dollars": (round(tier_cap_dollars, 2)
                                 if tier_cap_dollars is not None else None),
            "effective_cap_dollars": round(cap, 2),
            "binding_cap": binding_cap,
            "max_affordable_qty": afford,
            "premium_ceiling": round(premium_ceiling, 4),
            "premium_ceiling_cents": round(ceiling_cents, 2),
            "deadlock": deadlock,
            "headline": headline,
        }
        if not _is_bad_number(proposed_qty):
            q = _as_float(proposed_qty)
            out["proposed_qty"] = int(q) if q == int(q) else q
            out["proposed_notional"] = round(premium_f * q * 100.0, 2)
        return out
    except Exception as exc:  # noqa: BLE001 - monitoring must never raise into the entry path
        return {"available": False, "why": f"diagnostic error: {type(exc).__name__}: {exc}"}


def min_equity_for_premium(
    *,
    premium: Any,
    params: Optional[Mapping[str, Any]],
    ceiling: float = 100_000.0,
    step: float = 1.0,
) -> Optional[float]:
    """Smallest equity at which `min_contracts` at `premium` clears the caps, or None.

    Deliberately an ASCENDING SCAN over the real `max_affordable_qty`, NOT a binary
    search: the effective cap is NOT monotonic in equity. `v15_max_premium_pct_of_account`
    steps DOWN across bands (0.40 -> 0.30 -> 0.25 -> 0.20), so e.g. cap($9,999) =
    $2,999.70 but cap($10,000) = $2,500 — a bisection would happily land in a
    band where the answer is wrong. Scanning the real function is slower and correct.

    Fail-open (returns None) on unreadable input. CLI-only by design — never call this
    on the per-tick entry path.
    """
    try:
        if _is_bad_number(premium) or params is None or not isinstance(params, Mapping):
            return None
        e = float(step)
        while e <= ceiling:
            if max_affordable_qty(equity=e, premium=premium, params=params) > 0:
                return e
            e += step
        return None
    except Exception:  # noqa: BLE001
        return None


# --- WP-0: per-setup exit-param dispatch (the order-bracket stop resolver) ----
#
# The order path historically applied ONE global premium stop to EVERY entry. Two
# setups have VALIDATED isolated stops living in `filters.py`
# (vwap_reclaim_failed_break_premium_stop_pct, vix_dayside_premium_stop_pct, both
# -0.08) but NOTHING read them at order-build time — a dead-knob (L38/L72, C14).
#
# `select_exit_params` is the SINGLE pure dispatch that closes that gap WITHOUT
# changing today's behavior while the per-setup flags are off:
#
#   * setup is one of the per-setup-stop setups AND its params flag is ON
#       -> return that setup's ISOLATED filters.py accessor value (single source of
#          truth — we call the accessor, we never re-type the -0.08 literal here).
#   * otherwise (flag off, unknown setup, blank, or None params)
#       -> return `global_stop` UNCHANGED — byte-for-byte today's behavior.
#
# The caller passes the exact global it would otherwise have used (e.g. the
# orchestrator's side_premium_stop) as `global_stop`, so the flags-off path is
# provably identical: the resolver returns its own input. This is the load-bearing
# parity property tested in test_engine_order_bracket_parity.py — any drift with
# every flag off is a KILL.
#
# Pure: no I/O, no mutation. The filters import is function-local because filters.py
# is a heavy module and risk_gate.py is otherwise import-light; keeping it local also
# documents that the dependency is one-way (risk_gate -> filters, never back).

# Registry of per-setup stop overrides, keyed by the EXACT setup_name the watchers
# emit (single source of truth: *_watcher.py setup_name= fields). Each entry maps to
# the (enabled-flag accessor, isolated-stop accessor) pair in filters.py — both read
# the same params keys the live heartbeat reads (gamma-sync, no drift).
_PER_SETUP_STOP_OVERRIDES = {
    "VWAP_RECLAIM_FAILED_BREAK": (
        "vwap_reclaim_failed_break_enabled",
        "vwap_reclaim_failed_break_premium_stop_pct",
    ),
    "VIX_REGIME_DAYSIDE": (
        "vix_dayside_enabled",
        "vix_dayside_premium_stop_pct",
    ),
}


def select_exit_params(
    setup_name: Any,
    side: Any,
    params: Optional[Mapping[str, Any]],
    global_stop: float,
) -> float:
    """Resolve the premium stop % for ONE order's bracket.

    Pure dispatch. Returns the setup's ISOLATED stop ONLY when the setup has a
    per-setup stop override AND that setup's params flag is ON; otherwise returns
    `global_stop` unchanged (today's exact behavior).

    Args:
        setup_name: the named playbook setup driving this entry (e.g.
            "VWAP_RECLAIM_FAILED_BREAK"). Unknown / blank / non-str -> global.
        side: "P"/"C" — accepted for signature stability (the current isolated
            stops are side-agnostic; kept so a future side-specific override needs
            no caller change). Unused today.
        params: the account's params.json mapping (or None for an older snapshot).
            None / non-mapping -> global (no flag can be on).
        global_stop: the stop the order path would otherwise apply — returned
            verbatim on every non-overridden path (the byte-identity guarantee).

    Returns:
        The premium stop % (negative float) to use for this bracket.
    """
    del side  # side-agnostic today; accepted for forward-compatible signature.
    if params is None or not isinstance(params, Mapping):
        return global_stop
    if not isinstance(setup_name, str):
        return global_stop
    override = _PER_SETUP_STOP_OVERRIDES.get(setup_name)
    if override is None:
        return global_stop
    enabled_fn_name, stop_fn_name = override
    # Function-local import: one-way dependency (risk_gate -> filters), avoids any
    # module-top circular-import risk and keeps risk_gate import-light.
    from . import filters as _filters
    enabled = getattr(_filters, enabled_fn_name)(params)
    if not enabled:
        return global_stop
    # Single source of truth: the validated isolated accessor (-0.08 lives ONLY in
    # filters.py; we never duplicate the literal here).
    return float(getattr(_filters, stop_fn_name)(params))


# --- WP-5: per-setup STRIKE dispatch (the order-builder strike resolver) -------
#
# The order path historically picked the strike from the GENERIC v15 per-tier ladder
# (`v15_strike_offset_per_tier`) for EVERY setup. The ONE live edge — vwap_continuation
# (`j_vwap_cont_enabled=true`, Safe-2) — fires the generic OTM-2 tier, the WEAKEST of
# four cells, but is VALIDATED at ATM (Safe) / ITM-2 (Bold). Every live OTM-2 fill
# leaks ~$30/tr (Safe) vs its validated ATM cell (WP5-STRIKE-AB-SCORECARD.md).
#
# `select_strike_offset` is the SINGLE pure dispatch that fixes THIS one setup's strike
# WITHOUT changing today's behavior while the per-setup strike-override flag is off —
# the exact mirror of `select_exit_params` above (C29: per-setup ONLY, NOT a blanket
# v15-tier change; the generic ladder stays correct for every OTHER setup):
#
#   * setup is one of the per-setup-strike setups AND its params flag is ON
#       -> return that setup's VALIDATED strike, sourced from the filters.py accessor
#          (single source of truth — the offset lives ONLY in filters.py / params; we
#          never re-type it here), TRANSLATED to the simulator convention (see below).
#   * otherwise (flag off, unknown setup — incl. the orchestrator's RIDE_THE_RIBBON
#     setups today — blank, or None params)
#       -> return `current_strike_offset` UNCHANGED — byte-for-byte today's behavior.
#
# The caller passes the exact generic-tier offset it would otherwise have used (the
# orchestrator's `side_strike_off`, already in the simulator convention) as
# `current_strike_offset`, so the flags-off path is provably identical: the resolver
# returns its own input. This is the load-bearing parity property tested in
# test_engine_strike_parity.py — any drift with the flag off is a KILL.
#
# CONVENTION (load-bearing — sim-accuracy gate, OP-16): TWO INVERSE conventions exist.
#   * simulator_real / `current_strike_offset` here: NEGATIVE=ITM (ATM=0, ITM-2=-2).
#   * filters.py / live params accessor: NEGATIVE=OTM (ATM=0, ITM-2=+2) — the INVERSE.
# So the validated live-params offset from the accessor is NEGATED to the simulator
# convention before returning — EXACTLY as the orchestrator's generic per-tier path
# does (`kwargs["strike_offset"] = -tier.strike_offset`). The literals live ONLY in
# filters.py / params; risk_gate just dispatches + applies the documented sign flip.
#
# Pure: no I/O, no mutation. The filters import is function-local for the same reason
# as select_exit_params (one-way risk_gate -> filters dependency, import-light).

# Registry of per-setup STRIKE overrides, keyed by the EXACT setup_name the watchers
# emit (single source of truth: *_watcher.py setup_name= fields). Each entry maps to
# the (enabled-flag accessor, validated-offset accessor) pair in filters.py — both read
# the same params keys the live heartbeat reads (gamma-sync, no drift).
_PER_SETUP_STRIKE_OVERRIDES = {
    "VWAP_CONTINUATION": (
        "vwap_cont_strike_override_enabled",
        "vwap_cont_strike_offset",
    ),
}


def select_strike_offset(
    setup_name: Any,
    side: Any,
    params: Optional[Mapping[str, Any]],
    current_strike_offset: int,
) -> int:
    """Resolve the strike offset (simulator convention) for ONE order.

    Pure dispatch. Returns the setup's VALIDATED strike ONLY when the setup has a
    per-setup strike override AND that setup's params flag is ON; otherwise returns
    `current_strike_offset` unchanged (today's exact generic v15-tier behavior).

    Args:
        setup_name: the named playbook setup driving this entry (e.g.
            "VWAP_CONTINUATION"). Unknown / blank / non-str -> current offset.
        side: "P"/"C" — accepted for signature stability (the current strike
            override is side-agnostic; kept so a future side-specific override needs
            no caller change). Unused today.
        params: the account's params.json mapping (or None for an older snapshot).
            None / non-mapping -> current (no flag can be on). The per-account
            validated offset is carried IN params (Safe vs Bold key), so the accessor
            is account-aware via the params file itself.
        current_strike_offset: the strike offset the order path would otherwise apply
            (the generic v15 tier, in the simulator convention) — returned verbatim
            on every non-overridden path (the byte-identity guarantee).

    Returns:
        The strike offset (simulator convention: NEGATIVE=ITM) to use for this order.
    """
    del side  # side-agnostic today; accepted for forward-compatible signature.
    if params is None or not isinstance(params, Mapping):
        return current_strike_offset
    if not isinstance(setup_name, str):
        return current_strike_offset
    override = _PER_SETUP_STRIKE_OVERRIDES.get(setup_name)
    if override is None:
        return current_strike_offset
    enabled_fn_name, offset_fn_name = override
    # Function-local import: one-way dependency (risk_gate -> filters), avoids any
    # module-top circular-import risk and keeps risk_gate import-light.
    from . import filters as _filters
    enabled = getattr(_filters, enabled_fn_name)(params)
    if not enabled:
        return current_strike_offset
    # Single source of truth: the validated offset lives ONLY in filters.py / params
    # (live-params convention, NEGATIVE=OTM). NEGATE to the simulator convention
    # (NEGATIVE=ITM) — the same sign flip the generic per-tier path applies.
    live_params_offset = int(getattr(_filters, offset_fn_name)(params))
    return -live_params_offset


# --- small pure helpers ------------------------------------------------------

_FLAT_TOKENS = frozenset({"flat", "none", "no_position", "closed", "", "null"})


def _is_flat(status: Any) -> bool:
    """True only when the position status unambiguously means 'no open position'.

    Fail-safe direction: anything we don't recognise is treated as a LIVE
    position (so NOT_FLAT fires), because placing a second entry on top of an
    unknown state is the dangerous outcome.
    """
    if status is None:
        return True
    if isinstance(status, str):
        return status.strip().lower() in _FLAT_TOKENS
    # A mapping like {"qty": 0} or {"status": "flat"} — treat 0/empty as flat.
    if isinstance(status, Mapping):
        qty = status.get("qty", status.get("quantity"))
        if qty is not None and not _is_bad_number(qty):
            return _as_float(qty) == 0.0
        st = status.get("status")
        if isinstance(st, str):
            return st.strip().lower() in _FLAT_TOKENS
        return False  # unrecognised mapping -> assume open (safe)
    return False  # any other type -> assume open (safe)


def _assert_never_locks_human() -> None:
    """Executable statement of the OP-32 invariant: this module gates ORDERS,
    never SESSIONS. It imports nothing that can stop a process or session and
    exposes no such capability. The body is intentionally empty — the guarantee
    is in what this file does NOT import or call (no os, no subprocess, no
    signal, no scheduler). Kept as a named anchor for the regression test in
    test_risk_gate.py that asserts those modules are absent.
    """
    return None
