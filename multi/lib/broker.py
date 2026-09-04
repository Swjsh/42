"""multi/lib/broker.py -- symbol-generic Alpaca REST client for the multi-symbol options lane.

COPIED from `automation/state/fleet/fleet_broker.py` (NOT imported -- J directive 2026-08-19:
"copy the SPY engine, don't touch the original, trade many names, nothing hardcoded for SPY").
Every SPY-specific filter is replaced with the OCC-shape predicate in `multi.lib.positions`,
and credentials are resolved via `multi.lib.creds.resolve()` (which dereferences the
crypto-twin account BY REFERENCE) instead of a fleet-style `secrets.json`.

============================================================================================
THE SINGLE MOST IMPORTANT CONSTRAINT -- READ BEFORE TOUCHING ANYTHING HERE
============================================================================================
Account PA38EG1JTFBT simultaneously runs the crypto twin
(`setup/scripts/crypto_twin_broker.py`), which trades BTC/USD every ~60 seconds and is
ARMED right now. Every position/order read in this module that could enumerate this lane's
holdings goes through `multi.lib.positions.equity_option_positions()` (OCC-shape: 1-6 letter
ROOT + YYMMDD + C|P + 8-digit strike), which makes it STRUCTURALLY impossible -- not a
policy choice, a shape predicate -- for this lane to see, count, or close the twin's BTC
position. There is no SPY-only `startswith()` here (that was fleet_broker's hardcode, and
this lane must not repeat it in either direction: neither SPY-only nor crypto-exclusion-list
based). `close_all_equity_options()` below is proven, in `backtest/tests/test_multi_broker.py`,
to never touch a BTCUSD position placed in the same fixture as real option positions.

Because both programs post fills to the SAME account, ACCOUNT EQUITY IS NOT EVIDENCE for
either program (see multi/lib/creds.py's docstring for the same statement from the
credential side). This lane's evidence is its own ledger; `get_account()`'s `equity` field
must never be read for P&L attribution by anything downstream of this module.

============================================================================================
SHADOW PHASE -- NO ORDER PLACEMENT YET
============================================================================================
`automation/state/multi/params.json` currently has `"shadow_only": true`. Every function that
would place/cancel/replace a live order takes an `armed: bool = False` keyword:

  * `armed=False` (the default): the order is fully CONSTRUCTED (validated, priced, shaped
    exactly as it would be sent) but never reaches the network. Returns
    `{"_shadow": True, "armed": False, "would_submit": <order dict>}` (or `would_close` for
    the flatten primitive) so a caller can log/inspect exactly what WOULD have happened.
  * `armed=True`: re-reads `params.json` (or an injected `params` dict, for tests) at CALL
    TIME -- not cached -- and raises `ShadowModeError` if `shadow_only` is still true. This
    is a second, independent interlock on top of the `armed` flag itself, so "someone
    flipped `armed=True` without noticing the lane is still shadow-only" fails LOUD instead
    of quietly placing an order this phase was built specifically to prevent.
    Only when `armed=True` AND `shadow_only` is false does a submission function actually
    call the network.

Read-only functions (`get_account`, `get_positions`, `equity_option_positions`, `get_orders`,
`get_order`) are always allowed -- they cannot place, cancel, or modify anything, so they
carry no `armed` parameter.

============================================================================================
FAIL LOUD -- NO SILENT "FLAT"
============================================================================================
`fleet_broker.get_positions` collapses ANY read failure to `[]`:

    res = _request(creds, "positions")
    return res if isinstance(res, list) else []

That makes an unreadable broker indistinguishable from a genuinely flat account -- exactly
the failure mode `fleet_broker.open_spy_option_positions_checked`'s docstring documents
costing real money (bold-2, 2026-08-13: a hung `/v2/positions` read `[]`'d and the exit loop
did nothing while a stop sat unmanaged). This module does not have that failure mode at all:
`get_positions` / `get_orders` RAISE `BrokerAPIError` on any read failure instead of ever
returning an empty list for "unknown". A caller only ever sees `[]` when the broker
genuinely, successfully reports zero rows. Order-SUBMISSION calls (POST/DELETE) keep
fleet_broker's `{"_error": ...}` return-dict convention deliberately -- that is an explicit,
inspectable signal (never mistaken for success), and it is what lets `place_bracket` retry
bracket -> oto exactly as fleet_broker's does.

============================================================================================
ALPACA GOTCHAS HONOURED HERE (verified live on this rig; see CLAUDE.md + LESSONS-LEARNED)
============================================================================================
  * Paper keys 401 against `api.alpaca.markets` -- the TRADING api needs
    `paper-api.alpaca.markets`. `multi.lib.creds.resolve()` already refuses to return a
    non-paper `base_url`; this module never overrides or re-derives `base_url` itself.
  * The open-orders LIST can lag a single-order GET by 1-2s. `is_flat_equity_options()`
    below retries ON A TRANSIENT READ FAILURE ONLY (never on a clean "zero positions"
    read) to absorb that lag without ever treating "the read failed every time" as flat.

No SDK dependency (urllib only -- matches fleet_broker.py / crypto_twin_broker.py
convention). No secret is ever printed or logged here; use `multi.lib.creds.masked()` for
diagnostics. This module places nothing on import and has no `__main__` side effects beyond
a read-only self-check.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from multi.lib import creds as creds_mod
from multi.lib import positions as positions_mod

REPO_ROOT = Path(__file__).resolve().parents[2]

OPTIONS_DATA_HOST = "https://data.alpaca.markets"


class BrokerAPIError(RuntimeError):
    """Raised on any Alpaca read failure (HTTP error, network error, malformed payload) for
    the position/order LIST surface. Deliberately distinct from fleet_broker's swallow-to-`[]`
    pattern -- see the module docstring's FAIL LOUD section. A caller catching this must
    treat the read as UNKNOWN, never as "confirmed empty"."""


class ShadowModeError(RuntimeError):
    """Raised when `armed=True` is passed to a submission function while
    `automation/state/multi/params.json` still has `shadow_only: true`. This is the
    shadow-phase interlock: no order reaches the network until `shadow_only` is
    deliberately flipped AND the caller passes `armed=True`."""


# --- low-level REST plumbing (mirrors fleet_broker._request) ------------------------------
def _request(
    creds: creds_mod.MultiCreds, endpoint: str, method: str = "GET",
    data: Optional[dict] = None, timeout: int = 15,
) -> Any:
    url = f"{creds.base_url}/v2/{str(endpoint).lstrip('/')}"
    headers = {
        "APCA-API-KEY-ID": creds.key,
        "APCA-API-SECRET-KEY": creds.secret,
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- fixed https host
            txt = resp.read().decode("utf-8")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": str(e)}
        return {"_error": str(e), "_status": e.code, "_body": err}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"_error": str(e)}


def _raise_if_error(res: Any, what: str) -> None:
    if isinstance(res, dict) and res.get("_error"):
        raise BrokerAPIError(f"{what} failed: {res.get('_error')} (status={res.get('_status')})")


# --- read-only surface (always allowed; no `armed` parameter) -----------------------------
def get_account(creds: creds_mod.MultiCreds) -> dict:
    """GET /v2/account. Raises BrokerAPIError on failure. Read `equity` for NOTHING
    attribution-related -- see the module docstring's shared-account warning."""
    res = _request(creds, "account")
    _raise_if_error(res, "GET /v2/account")
    return res


def get_clock(creds: creds_mod.MultiCreds) -> dict:
    """GET /v2/clock -> {timestamp, is_open, next_open, next_close}. Raises BrokerAPIError on
    failure -- never coerces a broken read into "closed" (which would silently halt a lane) or
    "open" (which would silently trade a holiday). The CALLER decides what an unreadable clock
    means (execute.py: proceed under the weekday/window invariants, disclosed as
    CLOCK_READ_ERROR)."""
    res = _request(creds, "clock")
    _raise_if_error(res, "GET /v2/clock")
    if not isinstance(res, dict) or "is_open" not in res:
        raise BrokerAPIError(f"GET /v2/clock returned unexpected shape: {res!r}"[:300])
    return res


def get_positions(creds: creds_mod.MultiCreds) -> list[dict]:
    """RAW positions across every asset class held in this account (equities, crypto,
    options -- everything, including the crypto twin's BTC). Almost never what a caller
    wants directly -- see `equity_option_positions()`. Raises BrokerAPIError on ANY read
    failure; never coerces a broken connection into `[]` (see FAIL LOUD in the module
    docstring)."""
    res = _request(creds, "positions")
    _raise_if_error(res, "GET /v2/positions")
    if not isinstance(res, list):
        raise BrokerAPIError(f"GET /v2/positions returned unexpected shape: {type(res).__name__}: {res!r}")
    return res


def equity_option_positions(
    creds: creds_mod.MultiCreds, *, allowed_roots: Optional[list] = None
) -> list[dict]:
    """THE crypto-safety read. Raw positions filtered through
    `multi.lib.positions.equity_option_positions` (OCC-shape only) -- structurally excludes
    the twin's BTCUSD/BTC-USD crypto position. Raises BrokerAPIError (via get_positions) on
    a broker read failure -- never returns `[]` for "the read failed", only for "the read
    succeeded and there are genuinely zero option positions"."""
    return positions_mod.equity_option_positions(get_positions(creds), allowed_roots=allowed_roots)


def is_flat_equity_options(
    creds: creds_mod.MultiCreds, *, allowed_roots: Optional[list] = None,
    retries: int = 2, retry_sleep: float = 1.5,
) -> bool:
    """Flat-check with retry tolerance for Alpaca's documented list-lag (open positions/
    orders LIST can lag a single-order GET by 1-2s). Retries ONLY when the read itself
    raises `BrokerAPIError` -- a clean read reporting zero option positions returns True
    immediately, no retry performed. If every attempt fails, the LAST `BrokerAPIError` is
    re-raised: this function still never coerces an unreadable broker into "flat"."""
    last_exc: Optional[BrokerAPIError] = None
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        try:
            return len(equity_option_positions(creds, allowed_roots=allowed_roots)) == 0
        except BrokerAPIError as e:
            last_exc = e
            if attempt < attempts - 1:
                time.sleep(max(0.0, float(retry_sleep)))
    assert last_exc is not None  # loop always runs >=1 time and only reaches here via the except branch
    raise last_exc


def get_orders(
    creds: creds_mod.MultiCreds, *, status: str = "open",
    symbol: Optional[str] = None, side: Optional[str] = None,
) -> list[dict]:
    """Orders list, optionally filtered by exact symbol and/or side. Raises BrokerAPIError
    on failure -- never coerces a broken read into an empty ("no open orders") list, the
    same discipline as get_positions."""
    res = _request(creds, f"orders?status={status}&limit=100&nested=false")
    _raise_if_error(res, "GET /v2/orders")
    if not isinstance(res, list):
        raise BrokerAPIError(f"GET /v2/orders returned unexpected shape: {type(res).__name__}: {res!r}")
    out = res
    if symbol is not None:
        out = [o for o in out if str(o.get("symbol")) == symbol]
    if side is not None:
        out = [o for o in out if str(o.get("side")) == side]
    return out


def get_order(creds: creds_mod.MultiCreds, order_id: str) -> dict:
    """Single order by id (status/filled_qty/filled_avg_price). Raises BrokerAPIError on
    failure."""
    res = _request(creds, f"orders/{order_id}")
    _raise_if_error(res, f"GET /v2/orders/{order_id}")
    return res


_FILLED_STATUSES = ("filled", "partially_filled")


def poll_fill(creds: creds_mod.MultiCreds, order_id: str, *, attempts: int = 3, sleep_sec: float = 1.5) -> dict:
    """Poll get_order up to `attempts` times. Returns {filled, status, filled_qty,
    filled_avg_price, order}. `filled` is True iff status in (filled, partially_filled) AND
    filled_qty > 0. Propagates BrokerAPIError from get_order on a read failure -- this is
    the fill-confirmation read, not a flat-check, so a broken connection must not be
    silently reported as "not filled yet"."""
    last: dict = {"filled": False, "status": "unknown", "filled_qty": 0,
                  "filled_avg_price": None, "order": {}}
    for i in range(max(1, int(attempts))):
        o = get_order(creds, order_id)
        status = str(o.get("status", "")).lower()
        try:
            fq = float(o.get("filled_qty") or 0)
        except (TypeError, ValueError):
            fq = 0.0
        try:
            fap = float(o["filled_avg_price"]) if o.get("filled_avg_price") not in (None, "") else None
        except (TypeError, ValueError):
            fap = None
        last = {"filled": status in _FILLED_STATUSES and fq > 0, "status": status,
                "filled_qty": fq, "filled_avg_price": fap, "order": o}
        if last["filled"]:
            return last
        if i < int(attempts) - 1:
            time.sleep(max(0.0, float(sleep_sec)))
    return last


def get_position_qty(creds: creds_mod.MultiCreds, symbol: str) -> int:
    """Open contracts the broker shows for this exact OCC option symbol (0 if flat). Raises
    ValueError if `symbol` is not OCC-shaped -- this function only ever answers "how many
    contracts of this OPTION", never anything crypto/equity."""
    if not positions_mod.is_occ_option_symbol(symbol):
        raise ValueError(f"get_position_qty refuses a non-OCC-shaped symbol: {symbol!r}")
    for p in get_positions(creds):
        if str(p.get("symbol")) == symbol:
            try:
                return abs(int(float(p.get("qty", 0))))
            except (TypeError, ValueError):
                return 0
    return 0


# --- market data (options quotes; read-only, no `armed` needed) ---------------------------
def get_option_quote_hilo(creds: creds_mod.MultiCreds, symbol: str) -> Optional[tuple]:
    """(best_ask, worst_bid) for this tick -- the pricing input for a marketable entry and
    for walking TP/stop off the live premium. None on a quote-fetch failure (the caller
    HOLDS -- never force-prices/force-exits on a missing quote; mirrors
    fleet_broker.get_option_quote_hilo exactly, deliberately NOT upgraded to raise, since a
    missing quote is a legitimate "wait" signal, not an unknown-broker-state signal)."""
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/quotes/latest?symbols={symbol}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 -- fixed https host
            q = json.loads(resp.read().decode("utf-8")).get("quotes", {}).get(symbol)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    if not q:
        return None
    bid, ask = q.get("bp"), q.get("ap")
    if bid and ask and bid > 0 and ask > 0:
        return round(float(ask), 2), round(float(bid), 2)
    return None


def marketable_limit_price(
    creds: creds_mod.MultiCreds, symbol: str, *, side: str = "buy", buffer: float = 0.03
) -> Optional[float]:
    """Marketable ENTRY limit so the order CROSSES and fills. BUY = ask + buffer; SELL =
    bid - buffer. None when no two-sided quote (caller HOLDS). Raises ValueError if
    `symbol` is not OCC-shaped."""
    if not positions_mod.is_occ_option_symbol(symbol):
        raise ValueError(f"marketable_limit_price refuses a non-OCC-shaped symbol: {symbol!r}")
    hilo = get_option_quote_hilo(creds, symbol)
    if hilo is None:
        return None
    ask, bid = hilo
    if side == "buy":
        return round(ask + max(0.0, float(buffer)), 2)
    return round(max(0.01, bid - max(0.0, float(buffer))), 2)


# --- params helper: universe roots for the optional allowlist narrowing -------------------
def universe_roots(params: dict) -> set:
    """Flatten `automation/state/multi/params.json`'s `universe` block (index_etf/
    sector_etf/mega_tech/semis_hardware/.../high_beta) into one set of uppercase root
    tickers. Underscore-prefixed keys (`_doc`, `_selection_basis`, `_total_note`, ...) are
    metadata, not ticker lists, and are skipped. This is the "optional symbol-root
    allowlist from params `universe`" the task brief calls for -- an ADDITIONAL narrowing
    layered on top of the OCC-shape safety boundary in `multi.lib.positions`, never a
    substitute for it."""
    universe = params.get("universe") or {}
    roots: set = set()
    for key, val in universe.items():
        if str(key).startswith("_"):
            continue
        if isinstance(val, list):
            roots.update(str(r).upper() for r in val)
    return roots


# --- shadow-phase submission gate ----------------------------------------------------------
def _gate_submission(
    armed: bool, order_preview: dict, *, params: Optional[dict] = None
) -> Optional[dict]:
    """Common gate for every order-submission function. Returns a shadow-preview dict when
    `armed=False` (no network call made, order fully constructed for inspection). When
    `armed=True`, checks `shadow_only` (from the injected `params` dict, or a fresh
    `creds_mod.load_params()` read when not injected -- always re-read, never cached) and
    raises `ShadowModeError` if it is still true. Returns None to mean "gate passed, caller
    may submit"."""
    if not armed:
        return {"_shadow": True, "armed": False, "would_submit": order_preview}
    p = params if params is not None else creds_mod.load_params()
    if bool(p.get("shadow_only", True)):
        raise ShadowModeError(
            "multi lane params.json has shadow_only=true -- refusing to submit even though "
            f"armed=True was passed. SHADOW PHASE: no order placement yet. preview={order_preview!r}"
        )
    return None


# --- order construction + gated submission -------------------------------------------------
def place_bracket(
    creds: creds_mod.MultiCreds, *, symbol: str, qty: int, limit_price: float,
    take_profit_price: float, stop_price: float, armed: bool = False,
    simple_fallback: bool = False, params: Optional[dict] = None,
) -> dict:
    """Construct (and, only when armed, submit) a bracket option entry: limit parent @
    caller-supplied price + take-profit limit + stop-loss stop. Mirrors
    `fleet_broker.place_bracket`'s shape and its bracket -> oto fallback on rejection.

    Raises ValueError (construction-time, always enforced, regardless of `armed`) if:
      * `symbol` is not OCC-shaped -- the crypto-safety guard extends to entries too: this
        lane can never construct an order for a non-option symbol.
      * `stop_price` is null/<=0 -- refuses to construct a naked long (lesson C2).
      * `qty` is not a positive integer.

    See `_gate_submission` for the armed/shadow_only interlock.
    """
    if not positions_mod.is_occ_option_symbol(symbol):
        raise ValueError(f"place_bracket refuses a non-OCC-shaped symbol: {symbol!r} (crypto-safety guard)")
    if stop_price is None or float(stop_price) <= 0:
        raise ValueError("place_bracket: null/invalid stop -- refusing to construct a naked long (C2)")
    if qty is None or int(qty) < 1:
        raise ValueError(f"place_bracket: invalid qty {qty!r}")

    base = {
        "symbol": symbol, "qty": str(int(qty)), "side": "buy", "type": "limit",
        "limit_price": str(round(float(limit_price), 2)), "time_in_force": "day",
    }
    bracket = dict(base, order_class="bracket",
                   take_profit={"limit_price": str(round(float(take_profit_price), 2))},
                   stop_loss={"stop_price": str(round(float(stop_price), 2))})

    preview = _gate_submission(armed, bracket, params=params)
    if preview is not None:
        return preview

    res = _request(creds, "orders", method="POST", data=bracket)
    if isinstance(res, dict) and res.get("_error"):
        oto = dict(base, order_class="oto", stop_loss={"stop_price": str(round(float(stop_price), 2))})
        res2 = _request(creds, "orders", method="POST", data=oto)
        if isinstance(res2, dict) and not res2.get("_error"):
            res2["_oto_fallback"] = True
            res2["_note"] = "bracket rejected; oto placed (no TP leg)"
            return res2
        if simple_fallback:
            res3 = _request(creds, "orders", method="POST", data=dict(base))
            if isinstance(res3, dict) and not res3.get("_error"):
                res3["_simple_fallback"] = True
                res3["_note"] = "bracket+oto rejected; simple limit entry placed (engine-managed exits)"
                return res3
            return {"_error": "bracket, oto, and simple all rejected",
                    "bracket_err": res.get("_body"), "oto_err": res2}
        return {"_error": "both bracket and oto rejected",
                "bracket_err": res.get("_body"), "oto_err": res2}
    return res


def market_sell(
    creds: creds_mod.MultiCreds, *, symbol: str, qty: int, armed: bool = False,
    params: Optional[dict] = None,
) -> dict:
    """Market-sell `qty` contracts of an open long option. Raises ValueError if `symbol` is
    not OCC-shaped -- this is the primitive `close_all_equity_options` relies on for its
    second, independent crypto-safety check (the candidate list is already OCC-filtered by
    `equity_option_positions`; this re-validates at the point of construction so the
    invariant holds even if a future caller invokes `market_sell` directly with an
    untrusted symbol)."""
    if not positions_mod.is_occ_option_symbol(symbol):
        raise ValueError(f"market_sell refuses a non-OCC-shaped symbol: {symbol!r} (crypto-safety guard)")
    if qty is None or int(qty) < 1:
        raise ValueError(f"market_sell: invalid qty {qty!r}")
    order = {"symbol": symbol, "qty": str(int(qty)), "side": "sell",
             "type": "market", "time_in_force": "day"}
    preview = _gate_submission(armed, order, params=params)
    if preview is not None:
        return preview
    return _request(creds, "orders", method="POST", data=order)


def cancel_order(
    creds: creds_mod.MultiCreds, order_id: str, *, armed: bool = False, params: Optional[dict] = None
) -> dict:
    """DELETE /v2/orders/{id}, shadow-gated like every other submission call."""
    preview = _gate_submission(armed, {"cancel_order_id": order_id}, params=params)
    if preview is not None:
        return preview
    return _request(creds, f"orders/{order_id}", method="DELETE")


def replace_stop_order(
    creds: creds_mod.MultiCreds, *, order_id: str, stop_price: float, armed: bool = False,
    params: Optional[dict] = None,
) -> dict:
    """Ratchet an open stop order to a new stop price. Raises ValueError on a null/invalid
    stop -- refuses to widen to a naked stop (C2)."""
    if stop_price is None or float(stop_price) <= 0:
        raise ValueError("replace_stop_order: null/invalid stop -- refusing to widen to a naked stop (C2)")
    preview = _gate_submission(armed, {"order_id": order_id, "stop_price": stop_price}, params=params)
    if preview is not None:
        return preview
    return _request(creds, f"orders/{order_id}", method="PATCH",
                    data={"stop_price": str(round(float(stop_price), 2))})


def close_all_equity_options(
    creds: creds_mod.MultiCreds, *, allowed_roots: Optional[list] = None,
    armed: bool = False, params: Optional[dict] = None,
) -> dict:
    """EOD-flatten primitive, symbol-generic equivalent of `fleet_broker.close_all_spy_options`.

    CANNOT touch a non-option position, by TWO independent checks on the same invariant:
      1. The candidate list comes ONLY from `equity_option_positions()` (OCC-shape filtered)
         -- a BTCUSD position is never even a candidate.
      2. Each close goes through `market_sell()`, which independently re-validates OCC shape
         before constructing an order -- so even a corrupted/hand-edited candidate list could
         not reach a submission call for a non-option symbol.

    This is the primitive `backtest/tests/test_multi_broker.py`'s crypto-safety test proves
    against a fixture containing a BTCUSD position alongside real OCC option positions.
    """
    to_close = equity_option_positions(creds, allowed_roots=allowed_roots)
    if not armed:
        return {"_shadow": True, "armed": False,
                "would_close": [p.get("symbol") for p in to_close]}
    closed, errors = [], []
    for p in to_close:
        sym = p.get("symbol")
        qty = abs(int(float(p.get("qty", 0))))
        if qty < 1:
            continue
        res = market_sell(creds, symbol=sym, qty=qty, armed=True, params=params)
        (errors if isinstance(res, dict) and res.get("_error") else closed).append(sym)
    return {"closed": closed, "errors": errors}


if __name__ == "__main__":
    # Read-only self-check (mirrors fleet_broker.py's __main__): proves the resolved
    # credentials reach the broker and that the equity-option filter runs clean against the
    # LIVE shared account. Never prints a secret.
    c = creds_mod.resolve()
    acct_probe = creds_mod.verify_account(c)
    opts = equity_option_positions(c)
    print(f"account={c.account_number} source={c.source} key={creds_mod.masked(c.key)}")
    print(f"status={acct_probe.get('status')} equity={acct_probe.get('equity')} "
          f"(NOT evidence for either program -- shared account)")
    print(f"equity_option_positions={len(opts)}")
