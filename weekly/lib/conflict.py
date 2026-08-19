"""weekly/lib/conflict.py -- concurrency + correlation + capital-commitment gates for the
weekly-1 multi-day multi-symbol basket.

THE SCAR THIS GUARDS AGAINST (markdown/planning/WEEKLY-OPTIONS-PROGRAM.md, Context above
this module's build task): the shop measured its own 5 SPY arms at r=0.846 sign agreement
and called them "one bet in five sizes" wearing five account labels -- per-account
discipline (isolated kill switches, isolated risk caps) did nothing to see or bound the
BASKET-level concentration, because nothing summed what the correlated arms could commit
at once. weekly-1 can hold GLD/QQQ/NVDA/TSLA/AAPL simultaneously for DAYS at a time (the
whole point of weeklies over 0DTE). Long NVDA + long AMD + long SMH weeklies is the
identical trap wearing different TICKERS instead of different account aliases -- a basket
that "looks" diversified (multiple names) can be one semiconductor bet with extra steps.
This module is the basket-level, single-account analogue of that fix.

THREE INDEPENDENT GATES, each pure and each returning a STRUCTURED result (never a bare
bool) so a future weekly-lane participation-cascade instrument (mirrors
backtest/tools/participation_cascade.py's C15 "trace the joint funnel" doctrine) can
attribute exactly which gate, if any, killed a candidate entry:

  1. check_concurrency        -- params.risk.max_concurrent_positions, BASKET-WIDE (not
                                  per-symbol -- a $5K account cannot carry more positions
                                  at once without starving the next setup).
  2. check_correlation        -- params.risk.correlation_gate: deny a new entry whose |r|
                                  of DAILY RETURNS vs any OPEN position is >= deny_abs_r_gte
                                  over lookback_days. FAIL-CLOSED on missing/insufficient
                                  data -- see check_correlation's own docstring for why this
                                  is a deliberate, documented departure from this repo's
                                  usual fail-open guard precedent (book_exposure.py).
  3. check_capital_commitment -- can a NEW entry be afforded given capital ALREADY tied up
                                  by open multi-day holds (params.risk.per_trade_risk_cap_pct
                                  + min_contracts). The single-account, carry-aware analogue
                                  of book_exposure.py's book-wide dollar ceiling (which is
                                  multi-ARM and multi-day-BLIND by construction, since 0DTE
                                  arms are always flat by EOD and never carry commitments).

REUSE CHECK (per this module's build task): setup/scripts/book_exposure.py's `evaluate()`
was inspected before writing check_concurrency. It does NOT fit and was NOT reused --
documented in this module's build report, not silently worked around:
  - book_exposure is keyed by ARM (separate Alpaca accounts trading a SHARED signal) and
    judges a DOLLAR-PERCENTAGE ceiling of aggregate book equity across those arms.
  - This gate is keyed by SYMBOL within ONE account (weekly-1) and judges a POSITION-COUNT
    ceiling (params.risk.max_concurrent_positions), which has no equivalent knob in
    book_exposure at all.
  `position_notional()` (qty * premium * 100) IS the same primitive check_capital_commitment
  needs and its arithmetic is duplicated below rather than imported -- book_exposure.py is
  loaded by its test via importlib.util.spec_from_file_location (it is not part of an
  importable package), so importing it from here would mean either replicating that same
  path-load hack in production code or reaching into setup/scripts as a side-effect import.
  Given the primitive is one line (`abs(qty) * abs(premium) * 100`), duplicating it here
  keeps this module independently loadable and avoids a fragile cross-directory import for
  a single multiplication.

Every function is PURE except the yfinance price fetch (fetch_daily_closes), which is
fail-OPEN at the DATA layer (returns None on any problem, matching ssr_shadow.py's
fetch_bars_light convention) -- the GATE that consumes it (check_correlation) is what fails
CLOSED on a None, per params.risk.correlation_gate.fail_mode. This module places, cancels,
and modifies NOTHING -- Stage A is shadow-only; there is no order-placement call anywhere
below (grep-pinned by backtest/tests/test_weekly_conflict_gates.py).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = REPO_ROOT / "setup" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from et_clock import et_today_str  # noqa: E402  -- DST-aware ET, never a hardcoded offset

WEEKLY_PARAMS_PATH = REPO_ROOT / "automation" / "state" / "weekly" / "params.json"

# Documented current-config-at-time-of-writing values (automation/state/weekly/params.json,
# 2026-08-18). NOT runtime fallbacks -- every gate below FAILS CLOSED (returns a deny) when
# its own params key is actually missing rather than silently substituting one of these.
# They exist only so a reader of this file can see what "normal" is without opening the
# params file.
DOCUMENTED_MAX_CONCURRENT_POSITIONS = 2
DOCUMENTED_CORRELATION_DENY_ABS_R = 0.70
DOCUMENTED_CORRELATION_LOOKBACK_DAYS = 60

# Below this many aligned return-samples a Pearson r is noise, not a measurement -- treated
# as "insufficient data" by check_correlation's fail-closed path, same as a fetch failure.
MIN_CORRELATION_SAMPLES = 20

CODE_OK = "OK"
CODE_CONCURRENCY_CAP = "CONCURRENCY_CAP"
CODE_CORRELATION_DENY = "CORRELATION_DENY"
CODE_CORRELATION_DATA_UNAVAILABLE = "CORRELATION_DATA_UNAVAILABLE"
CODE_CAPITAL_COMMITMENT_DENY = "CAPITAL_COMMITMENT_DENY"
CODE_UNREADABLE_PARAMS = "UNREADABLE_PARAMS"


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover -- debug aid only
        return "<MISSING>"


_MISSING = _Missing()


def _nested_get(params: Any, *path: str) -> Any:
    """Walk a dotted key path through nested Mappings. Returns the sentinel `_MISSING`
    (never None -- None can be a legitimate stored value) the instant the path can't be
    followed, including when `params` itself isn't a Mapping."""
    cur = params
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def _is_bad_number(x: Any) -> bool:
    """True when x cannot be trusted as a finite real number. Mirrors
    backtest/lib/risk_gate.py's `_is_bad_number` (rejects None, NaN, inf, and bools --
    a bool sneaking into a numeric params field is a caller bug, not a 0/1)."""
    if x is None or isinstance(x, bool):
        return True
    if isinstance(x, (int, float)):
        return math.isnan(x) or math.isinf(x)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return True
    return math.isnan(v) or math.isinf(v)


def _deny(code: str, reason: str, **extra: Any) -> dict:
    return {"allowed": False, "code": code, "reason": reason, **extra}


def _allow(reason: str = "clear", **extra: Any) -> dict:
    return {"allowed": True, "code": CODE_OK, "reason": reason, **extra}


def load_weekly_params(path: Path = WEEKLY_PARAMS_PATH) -> dict:
    """Convenience loader for automation/state/weekly/params.json. Raises on a
    missing/malformed file -- a caller about to make a risk decision must never silently
    proceed on absent config (no silent fallbacks). Every gate function below still takes
    `params` as an explicit argument (risk_gate.py's pure-function convention) so tests
    never need to touch disk."""
    return json.loads(path.read_text(encoding="utf-8"))


# --- 1. CONCURRENCY -----------------------------------------------------------------------

def check_concurrency(open_positions: Mapping[str, Any], params: Mapping[str, Any]) -> dict:
    """Basket-wide concurrency cap -- params.risk.max_concurrent_positions (documented
    default 2). Deliberately BASKET-WIDE, not per-symbol: multi-day holds tie up capital
    for days, and a $5K weekly-1 account cannot carry more positions at once without
    starving the next setup (params.json's own `_max_concurrent_note`).

    `open_positions` is keyed by symbol: {symbol: {...position fields...}}. This counts
    DISTINCT OPEN SYMBOLS. Adding to an already-open symbol is Rule 4 / NOT_FLAT's concern
    (risk_gate.py), not this gate's -- this gate only bounds how many DIFFERENT positions
    the basket carries at once.
    """
    if not isinstance(open_positions, Mapping):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            f"open_positions must be a mapping keyed by symbol (got {type(open_positions).__name__})",
        )
    max_raw = _nested_get(params, "risk", "max_concurrent_positions")
    if max_raw is _MISSING or _is_bad_number(max_raw):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            f"params.risk.max_concurrent_positions missing/unreadable ({max_raw!r}) -- "
            "fail closed, no new entry",
        )
    max_concurrent = int(max_raw)
    current = len(open_positions)
    if current >= max_concurrent:
        return _deny(
            CODE_CONCURRENCY_CAP,
            f"{current} position(s) already open >= basket-wide cap {max_concurrent} "
            f"(params.risk.max_concurrent_positions) -- open symbols: {sorted(open_positions)}",
            current_count=current,
            max_concurrent=max_concurrent,
        )
    return _allow(
        f"{current} of {max_concurrent} concurrent slots used",
        current_count=current,
        max_concurrent=max_concurrent,
    )


# --- 2. CORRELATION ------------------------------------------------------------------------

def _pearson_r(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Pure Pearson correlation coefficient over the trailing min(len(a), len(b)) points.
    Returns None on <2 aligned points or a zero-variance series (undefined correlation --
    e.g. a perfectly flat return series), which check_correlation treats as insufficient
    data (fail-closed), never as r=0."""
    n = min(len(a), len(b))
    if n < 2:
        return None
    a2 = list(a)[-n:]
    b2 = list(b)[-n:]
    mean_a = sum(a2) / n
    mean_b = sum(b2) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a2, b2))
    var_a = sum((x - mean_a) ** 2 for x in a2)
    var_b = sum((y - mean_b) ** 2 for y in b2)
    if var_a <= 0 or var_b <= 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def _daily_returns(closes: Sequence[float]) -> List[float]:
    """Simple daily pct returns from a close series. Correlate RETURNS, not raw price
    levels: two names on unrelated walks can show spuriously high LEVEL correlation just
    from both trending in one direction over the window; return correlation is the actual
    co-movement measure the r=0.846 scar was about (sign-agreement on moves)."""
    out: List[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev == 0:
            continue
        out.append((cur - prev) / prev)
    return out


def fetch_daily_closes(
    symbol: str, lookback_days: int, now_et: Optional[str] = None
) -> Optional[List[float]]:
    """Free daily closes via yfinance, CLOSED sessions only.

    NO LOOK-AHEAD: today's ET session is excluded even if this runs after the close, so the
    output never depends on WHAT TIME today it is called -- deterministic by construction,
    never a peek at an in-progress bar. `now_et` is injectable for deterministic tests
    (defaults to the live et_clock reading).

    Fail-OPEN at the DATA layer only (returns None on any fetch/parse problem -- network
    error, empty response, malformed frame -- matching setup/scripts/ssr_shadow.py's
    `fetch_bars_light` convention: a data-fetch helper never raises into a caller). The
    CALLER (check_correlation) is what fails CLOSED on a None; that split is deliberate --
    see check_correlation's docstring.
    """
    try:
        import yfinance as yf  # noqa: PLC0415

        today = now_et or et_today_str()
        raw = yf.download(
            symbol, period=f"{lookback_days + 15}d", interval="1d",
            progress=False, auto_adjust=False,
        )
        if raw is None or raw.empty:
            return None
        if hasattr(raw.columns, "nlevels") and raw.columns.nlevels > 1:
            raw = raw.copy()
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.reset_index()
        tcol = next((c for c in raw.columns if c in ("Date", "Datetime")), raw.columns[0])
        dates = raw[tcol].astype(str).str.slice(0, 10)
        closes = raw["Close"]
        rows = [
            (d, float(c)) for d, c in zip(dates, closes)
            if d < today and c == c  # c == c is False for NaN -- drops bad closes
        ]
        rows.sort(key=lambda r: r[0])
        if not rows:
            return None
        return [c for _, c in rows[-lookback_days:]]
    except Exception:  # noqa: BLE001 -- a data-fetch helper must never raise into a risk gate
        return None


def check_correlation(
    candidate_symbol: str,
    open_symbols: Sequence[str],
    params: Mapping[str, Any],
    price_fetcher=fetch_daily_closes,
) -> dict:
    """Pairwise correlation gate -- deny a new entry whose |r| of DAILY RETURNS vs ANY
    already-open symbol is >= params.risk.correlation_gate.deny_abs_r_gte (documented 0.70)
    over params.risk.correlation_gate.lookback_days (documented 60). See this module's
    top docstring for the r=0.846 scar this closes.

    FAIL-CLOSED ON MISSING/INSUFFICIENT DATA -- a DELIBERATE, DOCUMENTED departure from
    this repo's usual fail-OPEN guard precedent (book_exposure.py: "never lock J out of
    his own system", OP-32 scar). That precedent is safe there because book_exposure has an
    INDEPENDENT BACKSTOP -- five isolated per-account kill switches and per-account risk
    caps still bind even on a tick where book-level exposure goes unmeasured. THIS gate has
    NO independent backstop: nothing else in Stage A checks basket correlation, so "can't
    measure it -> allow it" would silently readmit the exact concentration trap this gate
    exists to close. Failing closed here is also the SAFE direction to fail into, unlike an
    OP-32-style session lockout: the worst case is one missed candidate entry, logged with
    a reason, on an account that starts every session flat of that new position -- it can
    NEVER trap the operator and NEVER touches an already-open position (compare
    kill_switch.py's sibling invariant: entries fail closed, operators and open positions
    never do).

    `price_fetcher(symbol, lookback_days) -> Optional[Sequence[float]]` is injectable
    (defaults to `fetch_daily_closes`) so this stays testable without network access.
    """
    if not isinstance(open_symbols, (list, tuple, set)):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            f"open_symbols must be a list/tuple/set of symbols (got {type(open_symbols).__name__})",
        )

    lookback_raw = _nested_get(params, "risk", "correlation_gate", "lookback_days")
    threshold_raw = _nested_get(params, "risk", "correlation_gate", "deny_abs_r_gte")
    fail_mode = _nested_get(params, "risk", "correlation_gate", "fail_mode")
    if lookback_raw is _MISSING or _is_bad_number(lookback_raw) \
            or threshold_raw is _MISSING or _is_bad_number(threshold_raw):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            "params.risk.correlation_gate.lookback_days/deny_abs_r_gte missing/unreadable "
            "-- fail closed, no new entry",
        )
    # This module implements fail_mode="closed" ONLY (see docstring). A config asking for
    # anything else is a MISMATCH we do not silently honor -- we still fail closed below
    # (the strictly safer direction regardless of what the key says) and surface the
    # mismatch on every returned row rather than pretending the requested mode ran.
    config_note = None
    if fail_mode != "closed":
        config_note = (
            f"params.risk.correlation_gate.fail_mode={fail_mode!r} requested but NOT "
            "honored -- conflict.check_correlation implements fail-closed ONLY; every "
            "result below fails closed on missing/insufficient data regardless of this key"
        )
    lookback_days = int(lookback_raw)
    threshold = float(threshold_raw)

    def _finish(result: dict) -> dict:
        if config_note is not None:
            result["config_note"] = config_note
        return result

    if not open_symbols:
        return _finish(_allow("no open positions -- nothing to correlate against", checked_against=[]))

    candidate_closes = price_fetcher(candidate_symbol, lookback_days)
    if candidate_closes is None or len(candidate_closes) < MIN_CORRELATION_SAMPLES:
        got = 0 if candidate_closes is None else len(candidate_closes)
        return _finish(_deny(
            CODE_CORRELATION_DATA_UNAVAILABLE,
            f"{candidate_symbol}: insufficient daily closes ({got} < {MIN_CORRELATION_SAMPLES} "
            "minimum) to measure correlation -- fail-closed per this gate's no-independent-"
            "backstop reasoning, denying rather than trading blind on an unmeasured basket risk",
        ))
    candidate_returns = _daily_returns(candidate_closes)

    checked: dict = {}
    for sym in open_symbols:
        if sym == candidate_symbol:
            continue
        closes = price_fetcher(sym, lookback_days)
        if closes is None or len(closes) < MIN_CORRELATION_SAMPLES:
            got = 0 if closes is None else len(closes)
            return _finish(_deny(
                CODE_CORRELATION_DATA_UNAVAILABLE,
                f"{sym}: insufficient daily closes ({got} < {MIN_CORRELATION_SAMPLES} minimum) "
                f"for the open-position correlation check -- fail-closed, denying the "
                f"{candidate_symbol} entry rather than trading blind on an unmeasured basket risk",
                blocked_by_missing_data_for=sym,
            ))
        r = _pearson_r(candidate_returns, _daily_returns(closes))
        if r is None:
            return _finish(_deny(
                CODE_CORRELATION_DATA_UNAVAILABLE,
                f"{sym}: correlation undefined (zero-variance return series over the window) "
                f"-- fail-closed, denying the {candidate_symbol} entry rather than trading "
                "blind on an unmeasured basket risk",
                blocked_by_missing_data_for=sym,
            ))
        checked[sym] = round(r, 4)
        if abs(r) >= threshold:
            return _finish(_deny(
                CODE_CORRELATION_DENY,
                f"{candidate_symbol} vs open position {sym}: |r|={abs(r):.2f} >= "
                f"{threshold:.2f} deny threshold over {lookback_days}d of daily returns -- "
                "same bet, different ticker (the r=0.846 5-SPY-arm 'one bet in five sizes' scar)",
                correlations=checked,
            ))

    return _finish(_allow(
        f"{candidate_symbol} clears the correlation gate vs all {len(open_symbols)} open symbol(s)",
        correlations=checked,
    ))


# --- 3. CAPITAL COMMITMENT ------------------------------------------------------------------

def check_capital_commitment(
    candidate_symbol: str,
    candidate_premium: Any,
    equity: Any,
    open_positions: Mapping[str, Any],
    params: Mapping[str, Any],
) -> dict:
    """Can a NEW entry be afforded given capital ALREADY committed by open multi-day holds?

    backtest/lib/risk_gate.py's `order_affordable` already answers "does THIS order fit
    under the per-trade cap in isolation" -- correct for 0DTE, where every entry starts
    from a flat book (positions never carry across the check). It is NOT sufficient here:
    weekly-1 can be sitting on 1-2 OPEN multi-day positions whose premium is capital
    already tied up and unavailable to fund a new entry, and a check that only looks at
    the new order never sees that. This is the single-account, position-count-aware
    analogue of book_exposure.py's book-wide dollar ceiling (which is multi-ARM and
    multi-day-BLIND by construction, since 0DTE arms are always flat by EOD and never
    needed to track carried commitments).

    Affordable-notional = min(equity * per_trade_risk_cap_pct, equity - already_committed).
    The candidate must clear `min_contracts` (2 TP + 1 runner, Rule 6) at its own premium
    within that affordable amount, or it is denied.
    """
    if not isinstance(open_positions, Mapping):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            f"open_positions must be a mapping keyed by symbol (got {type(open_positions).__name__})",
        )
    cap_pct_raw = _nested_get(params, "risk", "per_trade_risk_cap_pct")
    min_contracts_raw = _nested_get(params, "risk", "min_contracts")
    if cap_pct_raw is _MISSING or _is_bad_number(cap_pct_raw) \
            or min_contracts_raw is _MISSING or _is_bad_number(min_contracts_raw):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            "params.risk.per_trade_risk_cap_pct/min_contracts missing/unreadable -- fail closed",
        )
    if _is_bad_number(equity) or _is_bad_number(candidate_premium):
        return _deny(
            CODE_UNREADABLE_PARAMS,
            f"equity/candidate_premium unreadable (equity={equity!r}, premium={candidate_premium!r})",
        )
    cap_pct = float(cap_pct_raw)
    min_contracts = int(min_contracts_raw)
    equity_f = float(equity)
    premium_f = float(candidate_premium)
    if equity_f <= 0 or premium_f <= 0:
        return _deny(
            CODE_UNREADABLE_PARAMS,
            f"equity ({equity_f}) and candidate_premium ({premium_f}) must both be > 0",
        )

    # FAIL CLOSED on any unreadable open position (code review, 2026-08-18).
    # Skipping a malformed entry would let it contribute $0 to `committed`, which
    # UNDERSTATES capital already tied up and therefore OVERSTATES what a new entry can
    # afford -- i.e. it fails open in the one direction that can over-commit the account.
    # An unreadable position is exactly when we know least about our exposure, so it must
    # deny, never wave through. Same posture as check_correlation's missing-data deny.
    committed = 0.0
    for symbol, pos in open_positions.items():
        if not isinstance(pos, Mapping):
            return _deny(
                CODE_UNREADABLE_PARAMS,
                f"open position {symbol!r} is not a mapping (got {type(pos).__name__}) -- "
                f"cannot compute committed capital, failing closed",
            )
        # Default to _MISSING, never 0: a position dict lacking qty/premium is malformed,
        # and defaulting it to zero size is the same silent fallback in another costume --
        # it would report an unknown-size position as costing nothing.
        qty = pos.get("qty", _MISSING)
        premium = pos.get("premium", _MISSING)
        if qty is _MISSING or premium is _MISSING or _is_bad_number(qty) or _is_bad_number(premium):
            return _deny(
                CODE_UNREADABLE_PARAMS,
                f"open position {symbol!r} has unreadable qty/premium "
                f"(qty={qty!r}, premium={premium!r}) -- cannot compute committed capital, "
                f"failing closed",
            )
        committed += abs(float(qty)) * abs(float(premium)) * 100.0

    per_trade_cap_dollars = equity_f * cap_pct
    available_capital = equity_f - committed
    max_new_notional = max(0.0, min(per_trade_cap_dollars, available_capital))
    min_required_notional = min_contracts * premium_f * 100.0

    context = {
        "committed_notional": round(committed, 2),
        "available_capital": round(available_capital, 2),
        "max_new_notional": round(max_new_notional, 2),
        "min_required_notional": round(min_required_notional, 2),
    }
    if min_required_notional > max_new_notional:
        return _deny(
            CODE_CAPITAL_COMMITMENT_DENY,
            f"{candidate_symbol}: min_contracts {min_contracts} @ ${premium_f:.2f} = "
            f"${min_required_notional:,.0f} exceeds affordable ${max_new_notional:,.0f} "
            f"(equity ${equity_f:,.0f} - committed ${committed:,.0f} = available "
            f"${available_capital:,.0f}, capped at {cap_pct:.0%} per-trade = "
            f"${per_trade_cap_dollars:,.0f})",
            **context,
        )
    return _allow(
        f"{candidate_symbol}: min_contracts {min_contracts} @ ${premium_f:.2f} fits under "
        f"${max_new_notional:,.0f} affordable",
        **context,
    )


# --- orchestrator ----------------------------------------------------------------------------

def evaluate(
    candidate_symbol: str,
    candidate_premium: Any,
    equity: Any,
    open_positions: Mapping[str, Any],
    params: Mapping[str, Any],
    price_fetcher=fetch_daily_closes,
) -> dict:
    """Run all three conflict gates; the FIRST denial wins (mirrors risk_gate.check_order's
    documented evaluation-order convention). Every result -- allow or deny -- carries a
    structured `code`/`reason` (never a bare bool)."""
    concurrency = check_concurrency(open_positions, params)
    if not concurrency["allowed"]:
        return concurrency
    correlation = check_correlation(
        candidate_symbol, list(open_positions.keys()), params, price_fetcher=price_fetcher
    )
    if not correlation["allowed"]:
        return correlation
    capital = check_capital_commitment(candidate_symbol, candidate_premium, equity, open_positions, params)
    if not capital["allowed"]:
        return capital
    return _allow(
        f"{candidate_symbol}: clears concurrency, correlation, and capital-commitment gates",
        concurrency=concurrency,
        correlation=correlation,
        capital=capital,
    )
