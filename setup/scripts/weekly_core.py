"""weekly_core.py -- SEE/DECIDE skeleton for the weekly-options lane (arm weekly-1).

WHY THIS EXISTS (integrator build task, 2026-08-18, markdown/planning/WEEKLY-OPTIONS-PROGRAM.md
Sec 5/7 step 5): the program doc names `weekly_core` as "thin SEE/DECIDE: per-symbol level
zones (daily/4h/1h) + market_structure + the Sec4 gates -> shadow ledger -> (later) fleet ACT
lane" and is explicit that `heartbeat_core.py` is NOT reused (its SEE/DECIDE is SPY-entangled).
This module is that fresh, symbol-generic pipeline, built entirely on top of six sibling
workstreams' real interfaces (weekly/lib/bars.py, zones.py, trigger.py, conflict.py,
backtest/lib/expiry_selector.py, setup/scripts/earnings_calendar.py's output) -- see each
import below for the exact contract consumed.

STAGE A / SHADOW ONLY: this module computes signals and WRITES them to
automation/state/weekly/shadow-ledger.jsonl. It contains NO order-placement code path --
not disabled, ABSENT (see `_assert_never_places_orders` and the grep-based structural guard
in backtest/tests/test_weekly_core_imports_and_cascade.py). Every network call in this file
is a GET (read-only market/reference data): Alpaca daily+hourly bars (via weekly/lib/bars.py),
the options contracts catalog, and options snapshots. No POST/PUT/DELETE call exists anywhere
below.

PIPELINE PER ACTIVE SYMBOL (params.json#universe.active), each row TERMINAL at exactly one
STAGE (see the STAGE_* constants below -- this exact ordered set IS the funnel pipeline
automation/state/weekly/participation_cascade.py reads back from the shadow ledger; keep the
two files' stage vocabulary in lockstep if either ever changes):

  bars (daily) -> zones -> bars (hourly) -> trigger -> [contracts fetch] ->
  liquidity -> min-DTE -> earnings-blackout -> expiry-availability -> concurrency ->
  correlation -> WOULD_PLACE

THREE JUDGMENT CALLS made building this pipeline (disclosed per house convention -- every
sibling workstream this session documented its own design decisions the same way):

1. MIN-DTE vs EXPIRY-AVAILABILITY are kept as two DISTINCT gates even though, given the
   lane's only configured `entry.expiry_rule` ("this_friday_if_dte_ge_3_else_next_friday",
   mapped onto `backtest.lib.expiry_selector.RULE_SAME_WEEK`), min-DTE can never actually
   trip today: RULE_SAME_WEEK's own internal logic self-heals by advancing to next Friday
   whenever the same-week Friday is under min_dte, rather than denying. `check_min_dte_calendar`
   below is a REAL, pure, zero-network pre-check (not a hardcoded pass) that would catch a
   future `min_dte_at_entry` value large enough to exceed one week's worth of self-heal
   headroom (>7) -- it is deliberately placed BEFORE the live-chain-dependent
   expiry-availability gate so the cheap, network-free check runs first.
2. The LIQUIDITY gate probes the NEAREST LISTED weekly expiry's ATM contract (closest
   strike to spot, call for a bullish signal / put for a bearish one) as a representative
   liquidity read for the underlying -- distinct from whichever expiry expiry-availability
   ultimately resolves (which may differ under a fallback). This is a coarse, documented
   pre-filter ("is this underlying's front-week chain even liquid enough to bother"), not a
   quote of the exact contract that would be bought.
3. Options-chain data is fetched via the SAME two REST endpoints
   `automation/scripts/gex_capture.py` already uses in production (paper-api
   `/v2/options/contracts` for the contracts catalog + data-api
   `/v1beta1/options/snapshots/{symbol}?feed=indicative` for quotes) -- no new/unverified
   Alpaca endpoint shape is introduced. `feed='indicative'` is a PERMANENT disclosure on every
   liquidity-bearing row: this account has no signed OPRA agreement (params.json's own
   `entry.liquidity_gate._feed_note`).

FAIL-LOUD CONTRACT: a genuine DATA problem (bars unavailable/stale, options-contracts fetch
failed, earnings-blackout.json missing/stale/symbol-unreadable per that file's own
`_fail_closed_contract`) writes an explicit row with `decision: "DATA_ERROR"` and makes
`run()`'s exit code 1 -- never a silently skipped symbol, never a plausible default. A normal
GATE denial (liquidity/min-dte/earnings-window/expiry/concurrency/correlation) or a normal
`NO_SIGNAL` (no zone, no trigger) is a legitimate outcome, always exits 0.

Positions/equity/kill-switch: the weekly-1 broker account does not exist yet (program doc
Sec7 Phase 1 is the one blocking human step). `load_open_positions` therefore always returns
`{}` today (no local position-state file exists either, honestly -- this module never
fabricates a position). Concurrency/correlation gates are consequently structurally ready but
currently inert (an empty basket always clears both). Rule 5's daily kill switch
(weekly/lib/kill_switch.py, built by a sibling workstream) is NOT wired into this pipeline --
it needs real realized P&L/start-of-day equity, which do not exist without a real account, and
was not named in this task's own gate list (liquidity, min-DTE, earnings-blackout,
expiry-availability, concurrency, correlation). Flagged in the build report as a real,
tracked gap, not silently dropped.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

# setup/scripts/weekly_core.py -> setup/scripts -> setup -> 42/ (repo root)
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "backtest" / "tools"), str(_REPO_ROOT / "backtest" / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _alpaca_creds import resolve_alpaca_creds  # noqa: E402  -- backtest/tools, read-only market-data creds
import expiry_selector as es  # noqa: E402  -- backtest/lib

from weekly.lib import bars as weekly_bars  # noqa: E402
from weekly.lib import conflict as weekly_conflict  # noqa: E402
from weekly.lib import trigger as weekly_trigger  # noqa: E402
from weekly.lib import zones as weekly_zones  # noqa: E402

WEEKLY_STATE = _REPO_ROOT / "automation" / "state" / "weekly"
PARAMS_PATH = WEEKLY_STATE / "params.json"
EARNINGS_BLACKOUT_PATH = WEEKLY_STATE / "earnings-blackout.json"
SHADOW_LEDGER_PATH = WEEKLY_STATE / "shadow-ledger.jsonl"
# NOT YET WRITTEN BY ANYTHING -- see module docstring "Positions/equity/kill-switch". Reading
# a nonexistent file here is normal today, not an error; load_open_positions returns {}.
POSITIONS_PATH = WEEKLY_STATE / "positions.json"

ARM = "weekly-1"
FEED = "indicative"  # permanent disclosure -- see module docstring judgment call 3.

DATA_HOST = "https://data.alpaca.markets"
TRADING_HOST = "https://paper-api.alpaca.markets"  # options/contracts catalog is a read-only
# GET against the shared contracts CATALOG, not a specific account's holdings -- the Safe-2
# paper key (resolve_alpaca_creds()'s default) is sufficient, exactly matching
# automation/scripts/gex_capture.py's OPTIONS_CONTRACTS_URL precedent (same host, same key).
ET = ZoneInfo("America/New_York")  # matches weekly/lib/bars.py's own convention EXACTLY --
# see that module's docstring for why et_clock.py's ET_TZ is unsafe for anything that flows
# into bars.py's own now_et parameter (its utcoffset(None) recursion-guard branch returns a
# hardcoded EST offset, wrong for most of the trading year). weekly_core's now_et flows
# straight into bars.fetch_daily/fetch_hourly, so it must be the same tzinfo family.

# Enough daily history for EVERY configured zone family, most importantly ema_20_50's 50-EMA
# leg (weekly/lib/bars.py's fetch_daily docstring: "A caller feeding zones.compute_zones's
# ema_20_50 family must pass min_bars>=51 explicitly, or that family's 50-length leg will
# simply be absent"). 65 gives real margin (~3 calendar months) and also comfortably covers
# prior_week_month_hlc's >=2-complete-period requirement.
_DAILY_MIN_BARS = 65
# Enough 1H bars for a stable market_structure read (SWING_WINDOW_1H default 3) -- roughly a
# week and a half of RTH hours at ~6.5 bars/session.
_HOURLY_MIN_BARS = 40

# params.json#entry.expiry_rule string -> backtest.lib.expiry_selector rule constant. See
# module docstring judgment call 1. A configured string with no mapping here raises rather
# than guessing (house no-silent-fallback rule).
_EXPIRY_RULE_MAP = {"this_friday_if_dte_ge_3_else_next_friday": es.RULE_SAME_WEEK}

# --- STAGE vocabulary -- the pipeline order, verbatim, is what
# automation/state/weekly/participation_cascade.py reconstructs its funnel from. ------------
STAGE_NO_DATA = "NO_DATA"
STAGE_NO_ZONE = "NO_ZONE"
STAGE_NO_TRIGGER = "NO_TRIGGER"
STAGE_LIQUIDITY_BLOCK = "LIQUIDITY_BLOCK"
STAGE_MIN_DTE_BLOCK = "MIN_DTE_BLOCK"
STAGE_EARNINGS_BLACKOUT_BLOCK = "EARNINGS_BLACKOUT_BLOCK"
STAGE_EXPIRY_UNAVAILABLE_BLOCK = "EXPIRY_UNAVAILABLE_BLOCK"
STAGE_CONCURRENCY_BLOCK = "CONCURRENCY_BLOCK"
STAGE_CORRELATION_BLOCK = "CORRELATION_BLOCK"
STAGE_WOULD_PLACE = "WOULD_PLACE"

ALL_STAGES = (
    STAGE_NO_DATA, STAGE_NO_ZONE, STAGE_NO_TRIGGER, STAGE_LIQUIDITY_BLOCK, STAGE_MIN_DTE_BLOCK,
    STAGE_EARNINGS_BLACKOUT_BLOCK, STAGE_EXPIRY_UNAVAILABLE_BLOCK, STAGE_CONCURRENCY_BLOCK,
    STAGE_CORRELATION_BLOCK, STAGE_WOULD_PLACE,
)


def _assert_never_places_orders() -> None:
    """Executable statement of the load-bearing invariant, mirroring
    weekly/lib/kill_switch.py's `_assert_never_force_closes_positions` pattern: this module
    can fetch read-only market/reference data and APPEND to the shadow ledger, but never
    places, cancels, or modifies a broker order. The guarantee is in what this file does NOT
    call -- named anchor for the structural (source-scan) guard test in
    backtest/tests/test_weekly_core_imports_and_cascade.py."""
    return None


# =============================================================================================
# pure gate functions
# =============================================================================================

def check_liquidity(quote: Optional[dict], params: Mapping[str, Any]) -> dict:
    """PURE. `quote` is None (no contract could even be identified) or
    {'occ_symbol','bid','ask','open_interest', ...} with any of bid/ask/open_interest
    possibly None. FAILS CLOSED whenever liquidity cannot actually be evidenced -- 'no
    evidence' is treated the same as 'known illiquid', never silently allowed through. This
    account's ENTIRE liquidity signal is the free 'indicative' feed forever (params.json's
    own entry.liquidity_gate._feed_note) -- there is no better source to fall back to."""
    gate_cfg = (params.get("entry") or {}).get("liquidity_gate") or {}
    max_spread_pct = gate_cfg.get("max_spread_pct_of_premium")
    min_oi = gate_cfg.get("min_open_interest")
    if max_spread_pct is None or min_oi is None:
        return {"allowed": False,
                "reason": "params.entry.liquidity_gate missing max_spread_pct_of_premium/"
                          "min_open_interest -- fail closed"}
    if quote is None:
        return {"allowed": False,
                "reason": "no representative option contract could be identified (empty/"
                          "unreachable chain) -- fail closed, no liquidity evidence"}
    occ = quote.get("occ_symbol")
    bid, ask, oi = quote.get("bid"), quote.get("ask"), quote.get("open_interest")
    if bid is None or ask is None:
        return {"allowed": False, "quote": quote,
                "reason": f"{occ}: bid/ask unavailable on the indicative feed -- fail closed"}
    mid = (float(bid) + float(ask)) / 2.0
    if mid <= 0:
        return {"allowed": False, "quote": quote,
                "reason": f"{occ}: non-positive mid price ({mid}) -- fail closed"}
    spread_pct = (float(ask) - float(bid)) / mid * 100.0
    if oi is None:
        return {"allowed": False, "quote": quote, "spread_pct": round(spread_pct, 2),
                "reason": f"{occ}: open_interest unavailable -- fail closed"}
    if spread_pct > float(max_spread_pct):
        return {"allowed": False, "quote": quote, "spread_pct": round(spread_pct, 2),
                "reason": f"{occ}: spread {spread_pct:.1f}% > {max_spread_pct}% floor "
                          f"(feed=indicative)"}
    if float(oi) < float(min_oi):
        return {"allowed": False, "quote": quote, "spread_pct": round(spread_pct, 2),
                "reason": f"{occ}: open_interest {oi:.0f} < {min_oi} floor"}
    return {"allowed": True, "quote": quote, "spread_pct": round(spread_pct, 2),
            "reason": f"{occ}: spread {spread_pct:.1f}% <= {max_spread_pct}%, "
                      f"OI {oi:.0f} >= {min_oi} (feed=indicative)"}


def check_min_dte_calendar(as_of: date, min_dte: int) -> dict:
    """PURE, ZERO NETWORK. See module docstring judgment call 1 -- a cheap pre-check that
    mirrors RULE_SAME_WEEK's own target-Friday + self-heal-if-under-min_dte arithmetic
    WITHOUT touching the live chain or importing expiry_selector's private helpers. Given the
    lane's only configured expiry_rule this always passes today; it exists as a REAL
    assertion (not a hardcoded True) so a future min_dte_at_entry large enough to exceed one
    week of self-heal headroom (>7) is actually caught here, not silently accepted."""
    same_week_friday = as_of + timedelta(days=(4 - as_of.weekday()) % 7)
    same_week_dte = (same_week_friday - as_of).days
    if same_week_dte >= min_dte:
        target, advanced = same_week_friday, False
    else:
        target, advanced = same_week_friday + timedelta(days=7), True
    target_dte = (target - as_of).days
    passed = target_dte >= min_dte
    return {
        "allowed": passed, "target_expiry": target.isoformat(), "target_dte": target_dte,
        "advanced_past_same_week": advanced,
        "reason": (
            f"calendar target {target.isoformat()} is {target_dte} DTE >= min_dte {min_dte}"
            if passed else
            f"calendar target {target.isoformat()} is only {target_dte} DTE < min_dte "
            f"{min_dte} -- min_dte_at_entry exceeds one week's self-heal headroom under "
            f"RULE_SAME_WEEK; this is a real design gap, not just a data problem"
        ),
    }


def check_earnings_blackout(
    symbol: str, blackout_doc: Optional[dict], params: Mapping[str, Any], as_of: date,
    now_et: datetime,
) -> dict:
    """Implements setup/scripts/earnings_calendar.py's own `_fail_closed_contract` literally
    (see that file's output schema, automation/state/weekly/earnings-blackout.json):
    (a) missing/unreadable file, (b) generated_at_et older than
    params.entry.earnings_feed_stale_hours_fail_closed, (c) symbol status != 'ok' and not
    exempt -- all three fail CLOSED with `data_error=True` (the feed itself is unreliable,
    not a real trading decision -- caller maps this to STAGE_NO_DATA / exit non-zero). Only
    once the feed is trustworthy does this check the REAL calendar question: is `as_of`
    inside [blackout_start_date, blackout_end_date] for this symbol (`data_error=False` --
    a normal, expected gate outcome)."""
    stale_h = (params.get("entry") or {}).get("earnings_feed_stale_hours_fail_closed")
    if stale_h is None:
        return {"allowed": False, "data_error": True,
                "reason": "params.entry.earnings_feed_stale_hours_fail_closed missing -- "
                          "fail closed"}
    if blackout_doc is None:
        return {"allowed": False, "data_error": True,
                "reason": f"{EARNINGS_BLACKOUT_PATH} missing/unreadable -- fail-closed per "
                          "earnings_calendar.py's own _fail_closed_contract"}
    gen_raw = blackout_doc.get("generated_at_et")
    try:
        gen_dt = datetime.strptime(str(gen_raw), "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return {"allowed": False, "data_error": True,
                "reason": f"earnings-blackout.json generated_at_et unreadable "
                          f"({gen_raw!r}) -- fail closed"}
    age_h = (now_et.replace(tzinfo=None) - gen_dt).total_seconds() / 3600.0
    if age_h > float(stale_h):
        return {"allowed": False, "data_error": True,
                "reason": f"earnings-blackout.json is {age_h:.1f}h old > {stale_h}h "
                          "staleness floor -- fail closed"}
    entry = (blackout_doc.get("symbols") or {}).get(symbol)
    if entry is None:
        return {"allowed": False, "data_error": True,
                "reason": f"{symbol} absent from earnings-blackout.json's symbols -- "
                          "fail closed"}
    if entry.get("exempt"):
        return {"allowed": True, "data_error": False,
                "reason": f"{symbol} exempt (ETF) -- {entry.get('reason')}"}
    if entry.get("status") != "ok":
        return {"allowed": False, "data_error": True,
                "reason": f"{symbol} status={entry.get('status')!r} (not 'ok') -- fail "
                          "closed per fail-closed contract clause (c)"}
    start_raw, end_raw = entry.get("blackout_start_date"), entry.get("blackout_end_date")
    if not start_raw or not end_raw:
        return {"allowed": False, "data_error": True,
                "reason": f"{symbol} status=ok but missing blackout_start_date/"
                          "blackout_end_date -- fail closed"}
    start_d, end_d = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
    if start_d <= as_of <= end_d:
        return {"allowed": False, "data_error": False,
                "reason": f"{symbol}: as_of {as_of.isoformat()} is inside the earnings "
                          f"blackout window [{start_raw}..{end_raw}] "
                          f"(next print {entry.get('next_earnings_date')})"}
    return {"allowed": True, "data_error": False,
            "reason": f"{symbol}: as_of {as_of.isoformat()} clear of blackout window "
                      f"[{start_raw}..{end_raw}]"}


def resolve_expiry_availability(
    symbol: str, available_expiries: Sequence[date], params: Mapping[str, Any], as_of: date,
    min_dte: int,
) -> tuple[Optional["es.ExpirySelection"], dict]:
    """Calls the REAL live-chain-dependent selector (backtest.lib.expiry_selector.select_expiry)
    using the already-fetched `available_expiries`. Returns (selection_or_None, gate_result)."""
    rule_str = (params.get("entry") or {}).get("expiry_rule")
    if not rule_str:
        return None, {"allowed": False, "reason": "params.entry.expiry_rule missing -- fail closed"}
    mapped_rule = _EXPIRY_RULE_MAP.get(rule_str)
    if mapped_rule is None:
        raise ValueError(
            f"weekly_core: unrecognized params.entry.expiry_rule {rule_str!r} -- no mapping "
            f"to a backtest.lib.expiry_selector rule; known mappings: "
            f"{sorted(_EXPIRY_RULE_MAP)}. Refusing to silently guess a rule."
        )
    if not available_expiries:
        return None, {"allowed": False,
                       "reason": f"{symbol}: zero listed expiries on the live chain -- "
                                 "cannot select an expiry"}
    try:
        selection = es.select_expiry(mapped_rule, as_of, available_expiries, min_dte)
    except ValueError as exc:
        return None, {"allowed": False,
                       "reason": f"{symbol}: expiry_selector could not resolve an expiry: {exc}"}
    fb = f" [FALLBACK: {selection.fallback_reason}]" if selection.fallback else ""
    return selection, {
        "allowed": True,
        "reason": f"{symbol}: selected {selection.chosen_expiry.isoformat()} via "
                  f"{selection.rule} ({selection.dte} DTE){fb}",
    }


# =============================================================================================
# network fetchers -- read-only GET only (see _assert_never_places_orders)
# =============================================================================================

def _get_json(url: str, *, timeout: int) -> dict:
    creds = resolve_alpaca_creds()
    req = Request(url, headers={
        "APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret,
        "accept": "application/json",
    })
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- fixed https host, not user input
        return json.loads(resp.read())


def fetch_option_contracts(
    symbol: str, *, now_et: Optional[datetime] = None, horizon_days: int = 45, timeout: int = 15,
) -> tuple[dict, ...]:
    """Real Alpaca trading-API GET /v2/options/contracts -- mirrors
    automation/scripts/gex_capture.py's `fetch_open_interest` exactly (same host, same
    pagination convention, same 50-page safety cap; see module docstring judgment call 3).
    READ-ONLY (GET). Raises RuntimeError on a transport failure -- never a silently empty
    tuple. An authentically EMPTY chain (fetch succeeded, zero contracts -- e.g. a delisted
    symbol) is NOT an error and returns () so callers can tell 'nothing listed' apart from
    'couldn't ask'."""
    now_et = now_et or datetime.now(timezone.utc).astimezone(ET)
    today = now_et.date()
    lo, hi = today.isoformat(), (today + timedelta(days=horizon_days)).isoformat()
    out: list[dict] = []
    page_token = None
    pages = 0
    while True:
        q = {"underlying_symbols": symbol, "status": "active",
             "expiration_date_gte": lo, "expiration_date_lte": hi, "limit": 1000}
        if page_token:
            q["page_token"] = page_token
        try:
            payload = _get_json(f"{TRADING_HOST}/v2/options/contracts?{urlencode(q)}", timeout=timeout)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise RuntimeError(
                f"{symbol}: options/contracts fetch failed: {type(exc).__name__}: {exc}"
            ) from exc
        contracts = payload.get("option_contracts") or []
        out.extend(c for c in contracts if isinstance(c, dict))
        pages += 1
        page_token = payload.get("next_page_token") or payload.get("page_token")
        if not page_token or pages >= 50:
            break
    return tuple(out)


def fetch_option_snapshots(symbol: str, *, timeout: int = 15) -> dict:
    """Real Alpaca data-API GET /v1beta1/options/snapshots/{symbol}?feed=indicative --
    mirrors automation/scripts/gex_capture.py's `fetch_option_snapshots` exactly (same
    endpoint, same pagination, same feed=indicative). Returns {occ_symbol: {...}}.
    feed is ALWAYS 'indicative' (module docstring judgment call 3)."""
    merged: dict[str, dict] = {}
    page_token = None
    pages = 0
    while True:
        q = {"feed": "indicative", "limit": 1000}
        if page_token:
            q["page_token"] = page_token
        try:
            payload = _get_json(
                f"{DATA_HOST}/v1beta1/options/snapshots/{symbol}?{urlencode(q)}", timeout=timeout
            )
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise RuntimeError(
                f"{symbol}: options/snapshots fetch failed: {type(exc).__name__}: {exc}"
            ) from exc
        snaps = payload.get("snapshots") or {}
        if isinstance(snaps, dict):
            merged.update(snaps)
        pages += 1
        page_token = payload.get("next_page_token")
        if not page_token or pages >= 50:
            break
    return merged


def available_expiries_from_contracts(contracts: Sequence[dict]) -> tuple[date, ...]:
    """PURE. Dedupe/sort `expiration_date` strings off a contracts payload into date objects."""
    out: set[date] = set()
    for c in contracts:
        raw = c.get("expiration_date")
        if not raw:
            continue
        try:
            out.add(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    return tuple(sorted(out))


def _pick_atm_contract(contracts: Sequence[dict], expiry: date, right: str, spot: float) -> Optional[dict]:
    """PURE. `right` is 'call' or 'put'. Nearest strike to spot among LISTED, tradable
    contracts of that type expiring on `expiry`."""
    expiry_iso = expiry.isoformat()

    def _strike(c: dict) -> float:
        try:
            return float(c.get("strike_price"))
        except (TypeError, ValueError):
            return float("inf")

    cands = [c for c in contracts
             if c.get("expiration_date") == expiry_iso
             and str(c.get("type", "")).lower() == right
             and c.get("tradable", True)]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(_strike(c) - spot))


def build_liquidity_quote(
    symbol: str, spot: float, direction: str, contracts: Sequence[dict],
    *, snapshots_fetcher=fetch_option_snapshots,
) -> Optional[dict]:
    """Module docstring judgment call 2: probes the NEAREST LISTED weekly expiry's ATM
    contract. `direction`: 'bullish' -> call, 'bearish' -> put. Returns None if no
    representative contract could be identified at all (empty chain / no contract of that
    type at the nearest expiry) -- check_liquidity treats None as fail-closed."""
    available = available_expiries_from_contracts(contracts)
    if not available:
        return None
    nearest_expiry = available[0]
    right = "call" if direction == "bullish" else "put"
    contract = _pick_atm_contract(contracts, nearest_expiry, right, spot)
    if contract is None:
        return None
    occ = contract.get("symbol")
    oi_raw = contract.get("open_interest")
    try:
        oi = float(oi_raw) if oi_raw is not None else None
    except (TypeError, ValueError):
        oi = None
    snaps = snapshots_fetcher(symbol)
    snap = snaps.get(occ) if isinstance(snaps, dict) else None
    bid = ask = None
    if isinstance(snap, dict):
        lq = snap.get("latestQuote") or {}
        bid_raw, ask_raw = lq.get("bp"), lq.get("ap")
        try:
            bid = float(bid_raw) if bid_raw is not None else None
        except (TypeError, ValueError):
            bid = None
        try:
            ask = float(ask_raw) if ask_raw is not None else None
        except (TypeError, ValueError):
            ask = None
        if oi is None:
            snap_oi = snap.get("open_interest", snap.get("openInterest"))
            try:
                oi = float(snap_oi) if snap_oi is not None else None
            except (TypeError, ValueError):
                pass
    return {"occ_symbol": occ, "bid": bid, "ask": ask, "open_interest": oi,
            "expiry": nearest_expiry.isoformat(), "right": right}


# =============================================================================================
# orchestration
# =============================================================================================

def _row(base: dict, stage: str, *, gate: Optional[str] = None, reason: str = "", **extra: Any) -> dict:
    if stage == STAGE_WOULD_PLACE:
        decision = "WOULD_PLACE"
    elif stage == STAGE_NO_DATA:
        decision = "DATA_ERROR"
    elif stage in (STAGE_NO_ZONE, STAGE_NO_TRIGGER):
        decision = "NO_SIGNAL"
    else:
        decision = "BLOCKED"
    row = {**base, "stage": stage, "decision": decision, "gate": gate, "reason": reason}
    row.update(extra)
    return row


def evaluate_symbol(
    symbol: str,
    *,
    params: Mapping[str, Any],
    now_et: datetime,
    earnings_blackout_doc: Optional[dict],
    open_positions: Mapping[str, Any],
    daily_bars_fetcher=weekly_bars.fetch_daily,
    hourly_bars_fetcher=weekly_bars.fetch_hourly,
    contracts_fetcher=fetch_option_contracts,
    snapshots_fetcher=fetch_option_snapshots,
    correlation_price_fetcher=weekly_conflict.fetch_daily_closes,
) -> dict:
    """One full SEE->DECIDE pass for one symbol. Returns a shadow-ledger row dict (the
    caller appends it -- this function has NO I/O side effects itself besides the injected
    fetchers). See module docstring for the exact stage pipeline and the three judgment
    calls behind its ordering."""
    as_of = now_et.date()
    base = {"ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "arm": ARM, "symbol": symbol, "feed": FEED}

    # -- SEE: daily bars -> zones ------------------------------------------------------------
    try:
        daily_df = daily_bars_fetcher(symbol, min_bars=_DAILY_MIN_BARS, now_et=now_et)
    except weekly_bars.BarFetchError as exc:
        return _row(base, STAGE_NO_DATA, gate="bars_daily", reason=str(exc))
    daily_bars = weekly_bars.dataframe_to_bars(daily_df, "1Day", source="alpaca_weekly_daily")

    try:
        zones = weekly_zones.compute_zones(daily_bars, params=params)
    except (RuntimeError, ValueError, weekly_zones.ZoneConsistencyError) as exc:
        return _row(base, STAGE_NO_DATA, gate="zones", reason=str(exc))
    if not zones:
        return _row(base, STAGE_NO_ZONE, reason=f"{symbol}: compute_zones returned zero zones")

    # -- SEE: hourly bars -> trigger ----------------------------------------------------------
    try:
        hourly_df = hourly_bars_fetcher(symbol, min_bars=_HOURLY_MIN_BARS, now_et=now_et)
    except weekly_bars.BarFetchError as exc:
        return _row(base, STAGE_NO_DATA, gate="bars_hourly", reason=str(exc))
    hourly_bars = weekly_bars.dataframe_to_bars(hourly_df, "1Hour", source="alpaca_weekly_hourly")

    signal = weekly_trigger.detect_trigger(symbol, zones, hourly_bars, params=params)
    if signal is None:
        return _row(base, STAGE_NO_TRIGGER,
                    reason=f"{symbol}: no confirmed structure shift at a zone on the "
                           "latest closed 1H bar")

    spot = float(daily_bars[-1].close)
    signal_fields = {
        "direction": signal.direction, "zone_family": signal.zone.family,
        "zone_price": signal.zone.price, "zone_role": signal.zone.role,
        "confluence_count": signal.confluence_count,
    }

    # -- DECIDE: gate chain -- liquidity, min-dte, earnings-blackout, expiry-availability,
    # concurrency, correlation (task-specified order; see module docstring for why min-dte
    # runs network-free before the live-chain fetch it eventually shares with expiry-
    # availability) ----------------------------------------------------------------------
    try:
        contracts = contracts_fetcher(symbol, now_et=now_et)
    except RuntimeError as exc:
        return _row(base, STAGE_NO_DATA, gate="contracts", reason=str(exc), **signal_fields)

    quote = build_liquidity_quote(symbol, spot, signal.direction, contracts,
                                   snapshots_fetcher=snapshots_fetcher)
    liq = check_liquidity(quote, params)
    if not liq["allowed"]:
        return _row(base, STAGE_LIQUIDITY_BLOCK, gate="liquidity", reason=liq["reason"],
                    liquidity=quote, **signal_fields)

    min_dte = es.load_min_dte_at_entry()  # NEVER hardcoded -- fresh read of params.json
    dte_chk = check_min_dte_calendar(as_of, min_dte)
    if not dte_chk["allowed"]:
        return _row(base, STAGE_MIN_DTE_BLOCK, gate="min_dte", reason=dte_chk["reason"],
                    liquidity=quote, **signal_fields)

    eb = check_earnings_blackout(symbol, earnings_blackout_doc, params, as_of, now_et)
    if not eb["allowed"]:
        stage = STAGE_NO_DATA if eb.get("data_error") else STAGE_EARNINGS_BLACKOUT_BLOCK
        return _row(base, stage, gate="earnings_blackout", reason=eb["reason"],
                    liquidity=quote, **signal_fields)

    available_expiries = available_expiries_from_contracts(contracts)
    selection, exp_res = resolve_expiry_availability(symbol, available_expiries, params, as_of, min_dte)
    if not exp_res["allowed"]:
        return _row(base, STAGE_EXPIRY_UNAVAILABLE_BLOCK, gate="expiry_availability",
                    reason=exp_res["reason"], liquidity=quote, **signal_fields)
    expiry_fields = {
        "expiry_rule": selection.rule, "chosen_expiry": selection.chosen_expiry.isoformat(),
        "expiry_dte": selection.dte, "expiry_fallback": selection.fallback,
        "expiry_fallback_reason": selection.fallback_reason,
    }

    conc = weekly_conflict.check_concurrency(open_positions, params)
    if not conc["allowed"]:
        return _row(base, STAGE_CONCURRENCY_BLOCK, gate="concurrency", reason=conc["reason"],
                    liquidity=quote, **signal_fields, **expiry_fields)

    corr = weekly_conflict.check_correlation(
        symbol, list(open_positions.keys()), params, price_fetcher=correlation_price_fetcher
    )
    if not corr["allowed"]:
        return _row(base, STAGE_CORRELATION_BLOCK, gate="correlation", reason=corr["reason"],
                    liquidity=quote, **signal_fields, **expiry_fields)

    return _row(
        base, STAGE_WOULD_PLACE,
        reason=f"{symbol}: cleared liquidity/min-dte/earnings-blackout/expiry-availability/"
               f"concurrency/correlation -- would place {signal.direction} "
               f"{expiry_fields['chosen_expiry']}",
        liquidity=quote, **signal_fields, **expiry_fields,
    )


def load_params(path: Path = PARAMS_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"weekly params not found at {path} -- cannot run weekly_core")
    return json.loads(path.read_text(encoding="utf-8"))


def load_earnings_blackout(path: Path = EARNINGS_BLACKOUT_PATH) -> Optional[dict]:
    """None on ANY read problem -- check_earnings_blackout treats None as 'file missing/
    unreadable', its own fail-closed branch. Never a silent empty-dict default (that would
    read as 'zero symbols known', a materially different and unsafe signal)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_open_positions(path: Path = POSITIONS_PATH) -> dict:
    """See module docstring 'Positions/equity/kill-switch' -- honestly returns {} when the
    file doesn't exist (true today: no orders are ever placed by this module, and the
    weekly-1 broker account itself doesn't exist yet)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def append_shadow_row(row: dict, *, path: Path = SHADOW_LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def run(
    *, params_path: Path = PARAMS_PATH, now_et: Optional[datetime] = None,
    ledger_path: Path = SHADOW_LEDGER_PATH, earnings_blackout_path: Path = EARNINGS_BLACKOUT_PATH,
    positions_path: Path = POSITIONS_PATH, write: bool = True,
) -> dict:
    """One full weekly-1 tick: SEE+DECIDE every active symbol, append each row to the shadow
    ledger. Returns {'rows': [...], 'exit_code': int}. exit_code is 1 iff ANY row is a
    DATA_ERROR decision (bars/contracts/earnings-feed unreadable -- house fail-loud rule); a
    normal gate BLOCKED or NO_SIGNAL row is a legitimate outcome and never fails the run."""
    now_et = now_et or datetime.now(timezone.utc).astimezone(ET)
    params = load_params(params_path)
    blackout_doc = load_earnings_blackout(earnings_blackout_path)
    open_positions = load_open_positions(positions_path)
    universe = tuple((params.get("universe") or {}).get("active") or ())
    if not universe:
        raise RuntimeError(
            "weekly_core.run: params.json universe.active is EMPTY -- refusing a "
            "symbol-less tick (silent-success guard)"
        )
    rows = []
    for symbol in universe:
        row = evaluate_symbol(symbol, params=params, now_et=now_et,
                               earnings_blackout_doc=blackout_doc, open_positions=open_positions)
        rows.append(row)
        if write:
            append_shadow_row(row, path=ledger_path)
    exit_code = 1 if any(r["decision"] == "DATA_ERROR" for r in rows) else 0
    return {"rows": rows, "exit_code": exit_code}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="weekly-1 SEE/DECIDE tick -- shadow only, never places an order"
    )
    ap.add_argument("--self-check", action="store_true",
                     help="import/resolve check only, no network, no writes, exit 0")
    ap.add_argument("--no-write", action="store_true",
                     help="compute and print but do not append the shadow ledger")
    args = ap.parse_args(argv)

    if args.self_check:
        # Zero network, zero state writes -- proves this file's own sys.path bootstrap +
        # every sibling import resolves under whatever interpreter actually ran it. See
        # backtest/tests/test_weekly_core_imports_and_cascade.py's real-subprocess guard.
        print("weekly_core: self-check OK (imports resolved; no order-placement path in this module)")
        return 0

    result = run(write=not args.no_write)
    for row in result["rows"]:
        print(f"[weekly_core] {row['symbol']}: {row['stage']} -- {row['reason']}")
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
