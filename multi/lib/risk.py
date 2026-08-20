"""multi/lib/risk.py — admission gates for the multi-symbol lane.

FORKED FROM (not imported from — J directive 2026-08-19: copy, don't touch the
original):
  * `backtest/lib/risk_gate.py`'s fail-closed input-hygiene helpers, its
    `Allow`/`Deny`-shaped frozen-dataclass result pattern, its evaluation-order
    discipline ("first failing rule wins"), and — MOST LOAD-BEARING — its
    OP-32 separation: "ORDER control fails CLOSED — on any uncertainty we DENY
    the order. OPERATOR/POSITION control fails OPEN — nothing here can ever
    force-close a position or touch a broker." `_assert_never_force_closes`
    below is the executable statement of that invariant for THIS module,
    mirroring risk_gate's own `_assert_never_locks_human`.
  * `automation/state/fleet/fleet_executor.py`'s per-order gate-then-allow shape
    (finalize()) — extended here with THREE gates that source file has no
    equivalent for, because it only ever manages ONE position at a time on ONE
    symbol: sector concentration, pairwise correlation, and book-wide
    concurrency across many symbols.

WHY THIS FILE EXISTS SEPARATELY FROM sizing.py
------------------------------------------------
sizing.py answers "how many contracts / which strike" for an entry that is
already known to be admissible. risk.py answers "may we enter AT ALL right now"
— kill switch, concentration, correlation, and concurrency. That split mirrors
risk_gate.check_order (admission) vs fleet_executor's tiered qty selection
(sizing) being two separate concerns in the source material; here they are two
separate FILES because both concerns grew enough new symbol-generic logic
(sector/correlation/concurrency) to earn one.

THE REALIZED-ONLY KILL SWITCH (the one rule genuinely different from the SPY
engine's Rule 5)
------------------------------------------------------------------------------
risk_gate.check_order's kill switch compares LIVE broker equity against a
start-of-day floor. That is correct for the SPY engine because a 0DTE position
is opened and closed same-day — by the time equity is read, the number already
reflects only today's realized effect (an early 0DTE position's unrealized
swing IS today's real risk).

This lane holds positions for `exits.days_to_live` days (3 in params.json).
Live account equity on a MULTI-DAY book includes the mark-to-market value of
YESTERDAY's still-open positions — a stock gapping down on macro news swings
that mark without the lane having done anything wrong today, and a raw
equity-vs-floor comparison would trip the kill switch on a paper loss it never
realized and blocks the WHOLE BOOK's new entries over noise. J's directive is
explicit: the kill switch trips on REALIZED loss only (closed-trade P&L
accumulated so far today), unrealized swings on multi-day holds must never trip
it, and tripping ONLY blocks new entries — it never force-closes anything
(mirrors risk_gate's own "ORDER control fails closed, OPERATOR/POSITION control
fails open" split, just applied to per-account position management instead of
per-session human lockout).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


# --- Stable decision codes (public contract) ----------------------------------
CODE_ALLOW = "ALLOW"
CODE_UNREADABLE_INPUT = "UNREADABLE_INPUT"
CODE_UNREADABLE_POSITION = "UNREADABLE_POSITION"
CODE_KILL_SWITCH = "KILL_SWITCH"
CODE_SECTOR_CAP = "SECTOR_CAP"
CODE_CORRELATION = "CORRELATION"
CODE_MAX_CONCURRENT_POSITIONS = "MAX_CONCURRENT_POSITIONS"
CODE_MAX_CONCURRENT_SYMBOLS = "MAX_CONCURRENT_SYMBOLS"


class MalformedPositionError(RuntimeError):
    """Raised loudly when an open position cannot be read confidently enough to
    gate on it. Every gate below that reads `open_positions` fails CLOSED (deny)
    on this — treating an unreadable position as "not there" would understate
    concentration/concurrency, the same over-commit direction sizing.py guards
    against."""


@dataclass(frozen=True)
class RiskDecision:
    """Base result. Use `.allowed` or `bool(result)`."""

    allowed: bool
    code: str
    reason: str

    def __bool__(self) -> bool:
        return self.allowed


@dataclass(frozen=True)
class Allow(RiskDecision):
    def __init__(self, reason: str = "all admission gates passed") -> None:
        object.__setattr__(self, "allowed", True)
        object.__setattr__(self, "code", CODE_ALLOW)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class Deny(RiskDecision):
    def __init__(self, code: str, reason: str) -> None:
        object.__setattr__(self, "allowed", False)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "reason", reason)


# --- input-hygiene helpers (forked verbatim from risk_gate.py's fail-closed core) ---

def _is_bad_number(x: Any) -> bool:
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
    return float(x)


def _risk_block(params: Mapping[str, Any]) -> Mapping[str, Any]:
    risk = params.get("risk")
    return risk if isinstance(risk, Mapping) else params


def _entry_block(params: Mapping[str, Any]) -> Mapping[str, Any]:
    entry = params.get("entry")
    return entry if isinstance(entry, Mapping) else params


def _require_symbols(
    open_positions: Optional[Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Extract `symbol` from every open position. Raises MalformedPositionError
    on the first entry that is not a mapping or has a missing/blank symbol —
    the shared fail-closed primitive every gate below builds on."""
    if not open_positions:
        return []
    out: list[str] = []
    for i, pos in enumerate(open_positions):
        if not isinstance(pos, Mapping):
            raise MalformedPositionError(
                f"open_positions[{i}] is not a mapping ({pos!r})"
            )
        symbol = pos.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise MalformedPositionError(
                f"open_positions[{i}] missing/blank 'symbol' ({symbol!r})"
            )
        out.append(symbol)
    return out


# --- 1. KILL SWITCH — realized loss only, blocks NEW ENTRIES ONLY -------------

def check_kill_switch(
    *,
    account: Any,
    start_of_day_equity: Any,
    realized_pnl_today: Any,
    kill_switch_tripped: Any,
    params: Optional[Mapping[str, Any]],
) -> RiskDecision:
    """Rule 5 for the multi-symbol lane: trips on REALIZED loss, never on
    unrealized mark-to-market swings from standing multi-day positions.

    Args:
        account: account/arm label, used only for the message.
        start_of_day_equity: equity at session open (kill-switch baseline).
        realized_pnl_today: cumulative REALIZED P&L (dollars) from trades CLOSED
            so far today — positive or negative. NEVER derived from live/mark
            equity; the caller must compute this from closed fills only (see
            module docstring for why: a multi-day book's live equity line
            includes yesterday's still-open positions' unrealized swing, which
            must not be able to trip today's switch).
        kill_switch_tripped: bool latch — True if the switch already fired
            today (sticky for the rest of the session, mirrors risk_gate).
        params: must carry `risk.daily_loss_kill_switch_pct` (0.25 in
            params.json — 25% of start-of-day equity in REALIZED losses halts
            new entries for the account for the day).

    Returns:
        Allow, or Deny(CODE_KILL_SWITCH, ...). This function NEVER recommends
        or performs closing any position — see `_assert_never_force_closes`.
        A Deny here means exactly one thing: no NEW entry for this account
        today. Every position already open stays open and continues to be
        managed by its own exit rules (chart stop / TP / catastrophe cap),
        completely independent of this gate.

    FAIL CLOSED: unreadable inputs (including a non-bool
    `kill_switch_tripped`, matching risk_gate's own stance that "maybe halted"
    is not a safe default) -> Deny(CODE_UNREADABLE_INPUT, ...).
    """
    if params is None or not isinstance(params, Mapping):
        return Deny(CODE_UNREADABLE_INPUT, "params missing or not a mapping")
    if kill_switch_tripped is None or not isinstance(kill_switch_tripped, bool):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"kill_switch_tripped must be an explicit bool (got "
            f"{type(kill_switch_tripped).__name__})",
        )
    if _is_bad_number(start_of_day_equity) or _as_float(start_of_day_equity) <= 0:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"start_of_day_equity must be a readable number > 0 (got {start_of_day_equity!r})",
        )
    if _is_bad_number(realized_pnl_today):
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"realized_pnl_today must be a readable number (got {realized_pnl_today!r})",
        )
    risk = _risk_block(params)
    kill_pct_raw = risk.get("daily_loss_kill_switch_pct")
    if _is_bad_number(kill_pct_raw):
        return Deny(
            CODE_UNREADABLE_INPUT,
            "params.risk.daily_loss_kill_switch_pct missing/unreadable",
        )
    kill_pct = _as_float(kill_pct_raw)
    sod_f = _as_float(start_of_day_equity)
    realized_f = _as_float(realized_pnl_today)

    if kill_switch_tripped:
        return Deny(
            CODE_KILL_SWITCH,
            f"{account}: daily kill switch already tripped — new entries "
            f"halted for the day (existing positions unaffected)",
        )

    realized_loss_floor = -1.0 * sod_f * kill_pct
    if realized_f <= realized_loss_floor:
        return Deny(
            CODE_KILL_SWITCH,
            f"{account}: realized P&L today ${realized_f:,.2f} <= kill floor "
            f"${realized_loss_floor:,.2f} ({kill_pct:.0%} of SoD ${sod_f:,.2f}) "
            f"— new entries halted for the day; open positions are NOT closed",
        )
    return Allow(
        f"{account}: realized P&L ${realized_f:,.2f} within kill floor "
        f"${realized_loss_floor:,.2f}"
    )


def _assert_never_force_closes() -> None:
    """Executable statement of the load-bearing invariant: this module gates
    NEW ENTRIES only. It has no broker import, no order/close capability, and
    exposes no function that returns a "close"/"liquidate" action — a kill-
    switch trip is communicated purely as `Deny(CODE_KILL_SWITCH, ...)`, a
    refusal to admit a NEW trade, never an instruction to exit an existing one.
    Body intentionally empty; the guarantee is in what this file does not
    import or call (no broker/order-placement module). Named anchor for the
    regression test in backtest/tests/test_multi_sizing_risk.py."""
    return None


# --- 2. SECTOR CONCENTRATION CAP -----------------------------------------------

def sector_for_symbol(symbol: Any, params: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Look up which `universe` bucket in params.json a symbol belongs to (the
    bucket name — e.g. "mega_tech", "financials" — IS the sector taxonomy this
    lane uses; params.json's own doc says these are "Liquid US optionable names
    across sectors"). Returns None when the symbol is not found in any bucket —
    callers MUST treat None as "sector unknown" and fail closed (see
    `check_sector_cap`), never as "no sector, no conflict"."""
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    if params is None or not isinstance(params, Mapping):
        return None
    universe = params.get("universe")
    if not isinstance(universe, Mapping):
        return None
    sym = symbol.strip().upper()
    for bucket_name, members in universe.items():
        if bucket_name.startswith("_"):  # doc/comment keys (_doc, _selection_basis, ...)
            continue
        if isinstance(members, (list, tuple)) and sym in {
            str(m).strip().upper() for m in members
        }:
            return bucket_name
    return None


def check_sector_cap(
    *,
    symbol: Any,
    open_positions: Optional[Sequence[Mapping[str, Any]]],
    params: Optional[Mapping[str, Any]],
) -> RiskDecision:
    """Deny a new entry in `symbol` if the book already holds
    `risk.max_positions_per_sector` (or more) open positions in the SAME sector.

    Sector is resolved via `sector_for_symbol` against params.json's `universe`
    buckets. FAIL CLOSED: if `symbol`'s sector cannot be resolved (not present
    in any universe bucket), OR any open position's sector cannot be resolved,
    OR any open position is malformed -> Deny. An unknown sector is uncertainty
    about concentration, not permission to ignore it.
    """
    if params is None or not isinstance(params, Mapping):
        return Deny(CODE_UNREADABLE_INPUT, "params missing or not a mapping")
    if not isinstance(symbol, str) or not symbol.strip():
        return Deny(CODE_UNREADABLE_INPUT, f"symbol missing/blank ({symbol!r})")

    risk = _risk_block(params)
    cap_raw = risk.get("max_positions_per_sector")
    if _is_bad_number(cap_raw):
        return Deny(CODE_UNREADABLE_INPUT,
                    "params.risk.max_positions_per_sector missing/unreadable")
    cap = int(_as_float(cap_raw))
    if cap <= 0:
        return Deny(CODE_UNREADABLE_INPUT,
                    f"params.risk.max_positions_per_sector must be > 0 (got {cap})")

    candidate_sector = sector_for_symbol(symbol, params)
    if candidate_sector is None:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"{symbol}: not found in any params.universe sector bucket — "
            f"cannot evaluate the sector cap, refusing to guess",
        )

    try:
        open_symbols = _require_symbols(open_positions)
    except MalformedPositionError as exc:
        return Deny(CODE_UNREADABLE_POSITION,
                    f"cannot evaluate sector cap for {symbol}: {exc}")

    same_sector_count = 0
    for sym in open_symbols:
        sec = sector_for_symbol(sym, params)
        if sec is None:
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"open position {sym} not found in any params.universe sector "
                f"bucket — cannot evaluate the sector cap, refusing to guess",
            )
        if sec == candidate_sector:
            same_sector_count += 1

    if same_sector_count >= cap:
        return Deny(
            CODE_SECTOR_CAP,
            f"{symbol}: sector '{candidate_sector}' already has {same_sector_count} "
            f"open position(s) >= max_positions_per_sector {cap}",
        )
    return Allow(
        f"{symbol}: sector '{candidate_sector}' has {same_sector_count} open "
        f"position(s), under cap {cap}"
    )


# --- 3. CORRELATION GATE --------------------------------------------------------

def _lookup_correlation(
    a: str, b: str, correlations: Mapping[str, Mapping[str, float]]
) -> Optional[float]:
    """Symmetric lookup: try correlations[a][b] then correlations[b][a]."""
    row_a = correlations.get(a)
    if isinstance(row_a, Mapping) and b in row_a and not _is_bad_number(row_a[b]):
        return _as_float(row_a[b])
    row_b = correlations.get(b)
    if isinstance(row_b, Mapping) and a in row_b and not _is_bad_number(row_b[a]):
        return _as_float(row_b[a])
    return None


def check_correlation_gate(
    *,
    symbol: Any,
    open_positions: Optional[Sequence[Mapping[str, Any]]],
    correlations: Optional[Mapping[str, Mapping[str, float]]],
    params: Optional[Mapping[str, Any]],
) -> RiskDecision:
    """Deny a new entry in `symbol` if |r| >= `risk.correlation_gate.deny_abs_r_gte`
    against ANY currently open position's underlying.

    `correlations` is a symmetric nested mapping, e.g.
    `{"AAPL": {"MSFT": 0.82}, ...}` (lookup tries both orderings). This is
    intentionally the caller's data — this module has no data-fetching
    capability by design (pure gate, no I/O), so whatever produces the
    correlation matrix (a scanner/state file) is wired in by the caller.

    FAIL CLOSED on missing data (`risk.correlation_gate.fail_mode` in
    params.json is documented as "closed" and this function does not read that
    key as a toggle — fail-closed is not optional here): if `correlations` is
    None/empty while the book has open positions, OR any open-position pair's
    correlation reading is absent, the entry is DENIED — uncertainty about
    correlation is not permission to concentrate risk. An EMPTY book (no open
    positions) trivially allows regardless of `correlations`, since there is
    nothing to correlate against.
    """
    if params is None or not isinstance(params, Mapping):
        return Deny(CODE_UNREADABLE_INPUT, "params missing or not a mapping")
    if not isinstance(symbol, str) or not symbol.strip():
        return Deny(CODE_UNREADABLE_INPUT, f"symbol missing/blank ({symbol!r})")

    risk = _risk_block(params)
    gate_cfg = risk.get("correlation_gate")
    if not isinstance(gate_cfg, Mapping):
        return Deny(CODE_UNREADABLE_INPUT,
                    "params.risk.correlation_gate missing or not a mapping")
    threshold_raw = gate_cfg.get("deny_abs_r_gte")
    if _is_bad_number(threshold_raw):
        return Deny(CODE_UNREADABLE_INPUT,
                    "params.risk.correlation_gate.deny_abs_r_gte missing/unreadable")
    threshold = _as_float(threshold_raw)

    try:
        open_symbols = _require_symbols(open_positions)
    except MalformedPositionError as exc:
        return Deny(CODE_UNREADABLE_POSITION,
                    f"cannot evaluate correlation gate for {symbol}: {exc}")

    if not open_symbols:
        return Allow(f"{symbol}: no open positions to correlate against")

    if not isinstance(correlations, Mapping) or not correlations:
        return Deny(
            CODE_UNREADABLE_INPUT,
            f"{symbol}: correlation data missing/empty while {len(open_symbols)} "
            f"position(s) are open — fail-closed (params.risk.correlation_gate."
            f"fail_mode=closed)",
        )

    for open_sym in open_symbols:
        if open_sym == symbol:
            continue
        r = _lookup_correlation(symbol, open_sym, correlations)
        if r is None:
            return Deny(
                CODE_UNREADABLE_INPUT,
                f"{symbol}: no correlation reading vs open position {open_sym} — "
                f"fail-closed (params.risk.correlation_gate.fail_mode=closed)",
            )
        if abs(r) >= threshold:
            return Deny(
                CODE_CORRELATION,
                f"{symbol}: |r|={abs(r):.2f} vs open position {open_sym} >= "
                f"threshold {threshold:.2f} (deny_abs_r_gte)",
            )
    return Allow(f"{symbol}: correlation vs all {len(open_symbols)} open position(s) "
                 f"below threshold {threshold:.2f}")


# --- 4. BOOK-WIDE CONCURRENCY (one-position-at-a-time is a SPY-only assumption) ---

def check_concurrency_admission(
    *,
    symbol: Any,
    open_positions: Optional[Sequence[Mapping[str, Any]]],
    params: Optional[Mapping[str, Any]],
) -> RiskDecision:
    """Deny a new entry when the book is already at capacity on EITHER axis:

      * `risk.max_concurrent_positions` — total open positions, book-wide.
      * `entry.max_concurrent_symbols` — distinct underlyings currently held,
        UNLESS `symbol` is already one of them (adding to an existing name's
        position doesn't grow the distinct-symbol count).

    The SPY engine (and every fleet arm forked from it) hard-assumes ONE
    position at a time; this lane explicitly does not, so both counts must be
    checked independently — a book could be under the position cap but at the
    symbol cap (many 1-lot names) or vice versa (few names, several adds each).

    FAIL CLOSED: unreadable params or a malformed open position -> Deny.
    """
    if params is None or not isinstance(params, Mapping):
        return Deny(CODE_UNREADABLE_INPUT, "params missing or not a mapping")
    if not isinstance(symbol, str) or not symbol.strip():
        return Deny(CODE_UNREADABLE_INPUT, f"symbol missing/blank ({symbol!r})")

    risk = _risk_block(params)
    entry = _entry_block(params)
    max_pos_raw = risk.get("max_concurrent_positions")
    max_sym_raw = entry.get("max_concurrent_symbols")
    if _is_bad_number(max_pos_raw):
        return Deny(CODE_UNREADABLE_INPUT,
                    "params.risk.max_concurrent_positions missing/unreadable")
    if _is_bad_number(max_sym_raw):
        return Deny(CODE_UNREADABLE_INPUT,
                    "params.entry.max_concurrent_symbols missing/unreadable")
    max_positions = int(_as_float(max_pos_raw))
    max_symbols = int(_as_float(max_sym_raw))

    try:
        open_symbols = _require_symbols(open_positions)
    except MalformedPositionError as exc:
        return Deny(CODE_UNREADABLE_POSITION,
                    f"cannot evaluate concurrency admission for {symbol}: {exc}")

    if len(open_symbols) >= max_positions:
        return Deny(
            CODE_MAX_CONCURRENT_POSITIONS,
            f"{symbol}: book already holds {len(open_symbols)} open position(s) "
            f">= max_concurrent_positions {max_positions}",
        )

    distinct = set(open_symbols)
    if symbol not in distinct and len(distinct) >= max_symbols:
        return Deny(
            CODE_MAX_CONCURRENT_SYMBOLS,
            f"{symbol}: book already holds {len(distinct)} distinct symbol(s) "
            f"{sorted(distinct)} >= max_concurrent_symbols {max_symbols}",
        )
    return Allow(
        f"{symbol}: {len(open_symbols)}/{max_positions} positions, "
        f"{len(distinct)}/{max_symbols} symbols — room to enter"
    )


# --- orchestrator: evaluation order mirrors risk_gate.check_order -------------
#
# EVALUATION ORDER: kill switch first (a hard "no trading this account today"
# halt outranks any per-symbol question), then the three per-symbol admission
# gates. First failing gate wins; this is a pure sequencing convenience — every
# gate above is independently callable and independently testable.

def evaluate_admission(
    *,
    account: Any,
    symbol: Any,
    start_of_day_equity: Any,
    realized_pnl_today: Any,
    kill_switch_tripped: Any,
    open_positions: Optional[Sequence[Mapping[str, Any]]],
    correlations: Optional[Mapping[str, Mapping[str, float]]],
    params: Optional[Mapping[str, Any]],
) -> RiskDecision:
    """Run every admission gate for ONE proposed new entry in `symbol`, in
    order: KILL_SWITCH -> concurrency -> sector cap -> correlation. Returns the
    first Deny, or Allow if every gate clears. Pure; no I/O, no mutation, never
    force-closes anything (see `_assert_never_force_closes`)."""
    decision = check_kill_switch(
        account=account, start_of_day_equity=start_of_day_equity,
        realized_pnl_today=realized_pnl_today,
        kill_switch_tripped=kill_switch_tripped, params=params,
    )
    if not decision:
        return decision

    decision = check_concurrency_admission(
        symbol=symbol, open_positions=open_positions, params=params,
    )
    if not decision:
        return decision

    decision = check_sector_cap(
        symbol=symbol, open_positions=open_positions, params=params,
    )
    if not decision:
        return decision

    decision = check_correlation_gate(
        symbol=symbol, open_positions=open_positions, correlations=correlations,
        params=params,
    )
    if not decision:
        return decision

    return Allow(f"{account}/{symbol}: all admission gates passed")
