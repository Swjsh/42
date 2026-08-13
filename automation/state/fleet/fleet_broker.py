"""fleet_broker -- minimal stdlib Alpaca REST client for the champion/challenger fleet.

One place that knows how to talk to each fleet arm's paper account, using the
per-arm creds in the GITIGNORED secrets.json (never argv, never git). Mirrors the
proven heartbeat order contract EXACTLY (heartbeat.md step 6-7): bracket entry =
limit parent @ mid + take_profit limit + stop_loss stop (NEVER null), with an
`oto` fallback if the API rejects the bracket.

SAFETY:
  * Read-only methods (get_account / get_positions) are always allowed.
  * place_bracket() REFUSES unless live=True is passed explicitly AND a non-null
    stop price is provided -- it can never place a naked long (lesson C2/C11).
  * close_all_spy_options() is the EOD-flatten primitive for the fleet arms.
  * No SDK dependency (urllib only) -- matches atomic_bracket_guard.py.

This module PLACES nothing on import and has no __main__ side effects beyond a
read-only self-check.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FLEET_DIR = Path(__file__).resolve().parent
SECRETS_PATH = FLEET_DIR / "secrets.json"


def load_creds() -> dict[str, dict[str, str]]:
    """Return {arm: {key, secret, base_url}} from the gitignored secrets.json."""
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(f"fleet_broker: {SECRETS_PATH} not found")
    data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    accounts = data.get("accounts", data)
    out: dict[str, dict[str, str]] = {}
    for arm, c in accounts.items():
        if not isinstance(c, dict):
            continue
        key = c.get("key") or c.get("api_key") or c.get("ALPACA_API_KEY")
        secret = c.get("secret") or c.get("secret_key") or c.get("ALPACA_SECRET_KEY")
        base = c.get("base_url") or c.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets"
        if key and secret:
            out[arm] = {"key": key, "secret": secret, "base_url": base.rstrip("/")}
    return out


def _request(arm_creds: dict[str, str], endpoint: str, method: str = "GET",
             data: dict | None = None, timeout: int = 15) -> Any:
    url = f"{arm_creds['base_url']}/v2/{endpoint.lstrip('/')}"
    headers = {
        "APCA-API-KEY-ID": arm_creds["key"],
        "APCA-API-SECRET-KEY": arm_creds["secret"],
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def get_account(creds: dict[str, str]) -> dict:
    return _request(creds, "account")


def get_positions(creds: dict[str, str]) -> list:
    res = _request(creds, "positions")
    return res if isinstance(res, list) else []


def open_spy_option_positions(creds: dict[str, str]) -> list:
    """SPY option positions only (OCC symbol like SPY260622C00745000)."""
    return [p for p in get_positions(creds)
            if str(p.get("symbol", "")).startswith("SPY") and len(str(p.get("symbol", ""))) >= 15
            and str(p.get("asset_class", "")) in ("option", "us_option", "")]


def is_flat_spy_options(creds: dict[str, str]) -> bool:
    return len(open_spy_option_positions(creds)) == 0


def open_spy_option_positions_checked(creds: dict[str, str]) -> "tuple[list, bool]":
    """SPY option positions, with the read's SUCCESS reported separately (2026-08-13).

    THE INCIDENT THIS EXISTS FOR. `get_positions` collapses any failure to `[]`:

        res = _request(creds, "positions")
        return res if isinstance(res, list) else []      # a timeout returns {"_error": ...}

    so an unreadable arm is INDISTINGUISHABLE from a flat one. On 2026-08-13 bold-2's
    /v2/positions hung at 15s for ~15 minutes (while /v2/clock and /v2/orders answered in 0.2s,
    that arm only). The exit loop saw "no positions", did nothing, and logged exit=0 while the
    bid sat through the -50% stop. Measured cost: -$40 of the -$200 realized.

    That was survivable. The UNBOUNDED case is eod_flatten, which read `[]`, logged
    "EOD_FLATTEN_NOOP -- already flat", and returned. On a 0DTE contract a missed flatten is not
    a delayed exit, it is expiry.

    WHY get_positions IS NOT CHANGED. Its fail-open behaviour is deliberate and documented for
    the exit manager's per-tick re-derivation ("simply re-tries every minute regardless" --
    get_position_qty). That reasoning holds for INDEPENDENT failures; today's were CORRELATED
    (one arm's endpoint down for 15 minutes straight), which is exactly when "it'll retry" stops
    being true. Rather than flip a documented default under every caller, this adds the checked
    read that callers who cannot tolerate a false "flat" must use -- the same shape as
    open_buy_orders_checked / symbol_position_qty_checked (2026-08-02).

    Returns (positions, ok). ok=False means the query itself failed and the caller MUST NOT read
    the empty list as "flat". Never raises.
    """
    try:
        res = _request(creds, "positions")
    except Exception:  # noqa: BLE001 -- a guard primitive must never crash the caller's tick
        return [], False
    if not isinstance(res, list):
        return [], False
    return ([p for p in res
             if str(p.get("symbol", "")).startswith("SPY") and len(str(p.get("symbol", ""))) >= 15
             and str(p.get("asset_class", "")) in ("option", "us_option", "")], True)


OPTIONS_DATA_HOST = "https://data.alpaca.markets"


def get_option_mid(creds: dict[str, str], symbol: str) -> float | None:
    """Latest option mid (bid+ask)/2 from the Alpaca options data feed. None on failure.

    Used only by the LIVE placement path to price the marketable-limit parent leg.
    """
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/quotes/latest?symbols={symbol}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            q = json.loads(resp.read().decode("utf-8")).get("quotes", {}).get(symbol)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    if not q:
        return None
    bid, ask = q.get("bp"), q.get("ap")
    if bid and ask and bid > 0 and ask > 0:
        return round((bid + ask) / 2, 2)
    return None


def _parse_option_greeks(payload: dict, symbol: str) -> "dict | None":
    """Pure: pull {delta,gamma,theta,vega,rho,iv} for `symbol` from an Alpaca options
    snapshots payload -- {"snapshots": {SYM: {"greeks": {...}, "impliedVolatility": ...}}}.
    Returns None when the symbol / greeks are absent or malformed (so the caller logs no
    greeks rather than a partial). Broker-free + side-effect-free -> unit-tests w/o a network.
    Shape verified against the existing gex_capture / gex_regime.from_alpaca_snapshot readers."""
    if not isinstance(payload, dict):
        return None
    snap = (payload.get("snapshots") or {}).get(symbol)
    if not isinstance(snap, dict):
        return None
    greeks = snap.get("greeks") or snap.get("latestGreeks")
    if not isinstance(greeks, dict) or not greeks:
        return None
    out = {k: greeks[k] for k in ("delta", "gamma", "theta", "vega", "rho")
           if isinstance(greeks.get(k), (int, float)) and not isinstance(greeks.get(k), bool)}
    iv = snap.get("impliedVolatility")
    if isinstance(iv, (int, float)) and not isinstance(iv, bool):
        out["iv"] = iv
    return out or None


def get_option_greeks(creds: dict[str, str], symbol: str) -> "dict | None":
    """Latest greeks + IV for ONE option contract from the Alpaca options snapshots feed.
    None on ANY failure. LOG-ONLY (G8): the entry path calls this AFTER placement / in dry
    mode purely to accumulate a per-entry greeks corpus -- it must NEVER affect an order.
    Mirrors get_option_mid's fail-open urllib pattern with a short 6s timeout so a slow feed
    cannot stall a tick. NOTE: the live snapshots-endpoint URL form is UNVERIFIED until a
    real entry logs greeks (fail-open makes a wrong URL a no-op, not a breakage) -- G9/first
    fill confirms it; the PARSE is proven against gex fixtures."""
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/snapshots?symbols={symbol}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    return _parse_option_greeks(payload, symbol)


def place_bracket(creds: dict[str, str], *, symbol: str, qty: int,
                  limit_price: float, take_profit_price: float, stop_price: float,
                  live: bool, simple_fallback: bool = False) -> dict:
    """Place a bracket option order. REFUSES without live=True or a null stop.

    Mirrors heartbeat.md step 7: order_class=bracket, parent limit @ mid, TP limit,
    stop_loss stop; falls back to order_class=oto on bracket rejection (logs that the
    stop leg may be heartbeat-owned). Returns the broker response (or a guard dict).

    simple_fallback (2026-06-26 fix): Alpaca rejects BOTH bracket and oto for options
    ("complex orders not supported for options trading", code 42210000) -- the live trade
    engine could never place a single option order through the bracket/oto path. When
    simple_fallback=True the caller asserts it will manage TP/stop itself off-broker (the
    tick-managed exit_manager), so on a complex-order rejection we place a plain limit
    entry instead. It stays False by default: a simple entry has NO broker-side stop, so
    placing one without engine-managed exits would be a stopless naked long (C2 violation).
    """
    if not live:
        return {"_skipped": "live flag is False -- place_bracket refused (WATCH mode)"}
    if stop_price is None or float(stop_price) <= 0:
        return {"_refused": "null/invalid stop -- refusing to place a naked long (C2)"}
    if qty is None or int(qty) < 1:
        return {"_refused": f"invalid qty {qty}"}

    base = {
        "symbol": symbol,
        "qty": str(int(qty)),
        "side": "buy",
        "type": "limit",
        "limit_price": str(round(float(limit_price), 2)),
        "time_in_force": "day",
    }
    bracket = dict(base, order_class="bracket",
                   take_profit={"limit_price": str(round(float(take_profit_price), 2))},
                   stop_loss={"stop_price": str(round(float(stop_price), 2))})
    res = _request(creds, "orders", method="POST", data=bracket)
    if isinstance(res, dict) and res.get("_error"):
        # Bracket rejected -> oto fallback (parent + stop only), flag for downstream.
        oto = dict(base, order_class="oto",
                   stop_loss={"stop_price": str(round(float(stop_price), 2))})
        res2 = _request(creds, "orders", method="POST", data=oto)
        if isinstance(res2, dict) and not res2.get("_error"):
            res2["_oto_fallback"] = True
            res2["_note"] = "bracket rejected; oto placed (no TP leg)"
            return res2
        # Both complex orders rejected. Alpaca does NOT support bracket/oto/oco for options
        # (code 42210000) -- the entry MUST be a simple order with TP/stop managed off-broker.
        # Fall back to a plain limit entry ONLY when the caller manages exits itself (the
        # tick-managed exit_manager); otherwise refuse, since a stopless naked long violates C2.
        if simple_fallback:
            res3 = _request(creds, "orders", method="POST", data=dict(base))
            if isinstance(res3, dict) and not res3.get("_error"):
                res3["_simple_fallback"] = True
                res3["_note"] = ("bracket+oto rejected (options); simple limit entry placed -- "
                                 "TP/stop are engine-managed (exit_manager tick-stop), no broker bracket")
                return res3
            return {"_error": "bracket, oto, and simple all rejected",
                    "bracket_err": res.get("_body"), "oto_err": res2, "simple_err": res3}
        return {"_error": "both bracket and oto rejected",
                "bracket_err": res.get("_body"), "oto_err": res2}
    return res


def get_option_quote_hilo(creds: dict[str, str], symbol: str) -> "tuple[float, float] | None":
    """(best_premium, worst_premium) for this tick = (ask, bid) of the latest option quote.

    The exit manager walks the live premium like the simulator walks bar high/low: best
    (ask) drives TP1 / runner-target reach, worst (bid) drives the stop. None on failure
    (the caller HOLDS — never force-exits on a missing quote)."""
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/quotes/latest?symbols={symbol}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            q = json.loads(resp.read().decode("utf-8")).get("quotes", {}).get(symbol)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    if not q:
        return None
    bid, ask = q.get("bp"), q.get("ap")
    if bid and ask and bid > 0 and ask > 0:
        return round(float(ask), 2), round(float(bid), 2)
    return None


# --- MONEY-PATH FIX (#15, 2026-06-30): real-fill primitives --------------------------------
# The rig placed limit @ mid and called that "placed" -> a mid limit rarely crosses on 0DTE,
# so it filled 0 orders ever while logging them as entries. These add (a) marketable pricing so
# the order actually crosses, and (b) fill-confirm / cancel-replace helpers (used by the poll
# refinement + the #16 reconciler). Additive: nothing here changes existing callers on import.

def marketable_limit_price(creds: dict[str, str], symbol: str, *, side: str = "buy",
                           buffer: float = 0.03) -> "float | None":
    """Marketable ENTRY limit so the order CROSSES and fills. BUY = ask + buffer; a sell uses
    bid - buffer. `buffer` is an absolute premium add ($/contract) so a wide 0DTE spread still
    fills without a blind market order. None when no two-sided quote (caller HOLDS -- never
    blind-prices). buffer is a knob on how aggressively we cross an already-decided entry."""
    hilo = get_option_quote_hilo(creds, symbol)  # (ask, bid)
    if hilo is None:
        return None
    ask, bid = hilo
    if side == "buy":
        return round(ask + max(0.0, float(buffer)), 2)
    return round(max(0.01, bid - max(0.0, float(buffer))), 2)


def get_order(creds: dict[str, str], order_id: str) -> dict:
    """Single order by id (status / filled_qty / filled_avg_price). {} or {_error} on failure."""
    res = _request(creds, f"orders/{order_id}")
    return res if isinstance(res, dict) else {}


_FILLED_STATUSES = ("filled", "partially_filled")


def poll_fill(creds: dict[str, str], order_id: str, *, attempts: int = 3,
              sleep_sec: float = 1.5) -> dict:
    """Poll get_order up to `attempts` times. Returns {filled, status, filled_qty,
    filled_avg_price, order}. filled is True iff status in (filled, partially_filled) AND
    filled_qty > 0. NEVER raises; an _error/absent order yields filled=False. This is what
    turns 'broker accepted' into 'actually filled'."""
    import time
    last: dict = {"filled": False, "status": "unknown", "filled_qty": 0,
                  "filled_avg_price": None, "order": {}}
    for i in range(max(1, int(attempts))):
        o = get_order(creds, order_id)
        if o and not o.get("_error"):
            status = str(o.get("status", "")).lower()
            try:
                fq = float(o.get("filled_qty") or 0)  # float: whole option contracts AND fractional crypto
            except (TypeError, ValueError):
                fq = 0.0
            try:
                fap = (float(o["filled_avg_price"])
                       if o.get("filled_avg_price") not in (None, "") else None)
            except (TypeError, ValueError):
                fap = None
            last = {"filled": status in _FILLED_STATUSES and fq > 0, "status": status,
                    "filled_qty": fq, "filled_avg_price": fap, "order": o}
            if last["filled"]:
                return last
        if i < int(attempts) - 1:
            time.sleep(max(0.0, float(sleep_sec)))
    return last


def cancel_order(creds: dict[str, str], order_id: str, *, live: bool) -> dict:
    """DELETE /orders/{id}. WATCH-gated. Cancel a stale pending entry limit before re-pricing."""
    if not live:
        return {"_skipped": "live flag False -- cancel_order refused (WATCH)"}
    return _request(creds, f"orders/{order_id}", method="DELETE")


def open_buy_orders(creds: dict[str, str], symbol: str) -> list:
    """Open (un-filled) BUY orders for this exact OCC symbol -- the stale pending entries a
    later tick cancel-replaces so a never-crossing limit doesn't sit all day. [] on failure."""
    res = _request(creds, "orders?status=open&limit=100&nested=false")
    if not isinstance(res, list):
        return []
    return [o for o in res
            if str(o.get("symbol")) == symbol and str(o.get("side")) == "buy"]


def open_buy_orders_checked(creds: dict[str, str], symbol: str) -> "tuple[list, bool]":
    """ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02) primitive. Returns (orders, ok):
    ok=False means the query ITSELF failed/returned something unparseable -- the caller
    MUST NOT treat that the same as a confirmed-empty list. Deliberately DISTINCT from
    open_buy_orders (which fails OPEN to [] -- correct for that function's original
    cancel-replace MAINTENANCE use, where 'unknown' was historically treated as 'nothing
    to cancel', a harmless interpretation for a no-op cleanup step). This variant exists
    because fleet_live._place_live's entry guard must fail CLOSED on an unreadable broker
    response (uncertain state -> no placement -- a missed entry is cheap, a double entry
    is not), which open_buy_orders's collapsed-to-[] contract cannot express. Never raises
    -- any exception from the request itself is caught and reported as ok=False, same as a
    malformed response."""
    try:
        res = _request(creds, "orders?status=open&limit=100&nested=false")
    except Exception:  # noqa: BLE001 -- a guard primitive must never crash the caller's tick
        return [], False
    if not isinstance(res, list):
        return [], False
    return [o for o in res
            if str(o.get("symbol")) == symbol and str(o.get("side")) == "buy"], True


def open_sell_orders(creds: dict[str, str], symbol: str) -> list:
    """Open (un-filled/still-resting) SELL orders for this exact OCC symbol.

    F7-EXIT-SELL-ALL-REFIRE guard (2026-07-18): exit_actuator.manage_tick calls this
    BEFORE submitting a new SELL_PARTIAL/SELL_ALL so a prior tick's exit order that is
    still resting broker-side (a slow fill, or a network timeout AFTER Alpaca actually
    accepted the order -- market_sell's urllib call can raise TimeoutError/URLError on
    the RESPONSE even when the POST already landed) never gets a duplicate real sell
    stacked on top of it. [] on failure -- fail-open (same shape as open_buy_orders):
    an empty list is read as "no known duplicate", i.e. today's exact pre-guard
    behavior, so a broker/API hiccup on THIS read can never make the actuator refuse
    to exit a position that genuinely needs to close."""
    res = _request(creds, "orders?status=open&limit=100&nested=false")
    if not isinstance(res, list):
        return []
    return [o for o in res
            if str(o.get("symbol")) == symbol and str(o.get("side")) == "sell"]


def get_position_qty(creds: dict[str, str], symbol: str) -> int:
    """Open contracts the broker shows for this exact option symbol (0 if flat). Broker is
    the source of truth (C11) — the exit manager re-derives runner state from this each tick."""
    for p in get_positions(creds):
        if str(p.get("symbol")) == symbol:
            try:
                return abs(int(float(p.get("qty", 0))))
            except (TypeError, ValueError):
                return 0
    return 0


def symbol_position_qty_checked(creds: dict[str, str], symbol: str) -> "tuple[int, bool]":
    """ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02) primitive, the position-side twin of
    open_buy_orders_checked. Returns (qty, ok): ok=False means the positions query itself
    failed/returned something unparseable -- the caller MUST NOT read that as '0 = flat'.
    Distinct from get_position_qty (which fails OPEN to 0 -- correct for the exit manager's
    per-tick re-derivation, which simply re-tries every minute regardless). Used by
    fleet_live._place_live's post-cancel re-verify, which must fail CLOSED (refuse to
    place) when it cannot confirm the cancel didn't race a fill. Never raises."""
    try:
        res = _request(creds, "positions")
    except Exception:  # noqa: BLE001 -- a guard primitive must never crash the caller's tick
        return 0, False
    if not isinstance(res, list):
        return 0, False
    for p in res:
        if str(p.get("symbol")) == symbol:
            try:
                return abs(int(float(p.get("qty", 0)))), True
            except (TypeError, ValueError):
                return 0, True
    return 0, True


def market_sell(creds: dict[str, str], *, symbol: str, qty: int, live: bool) -> dict:
    """Market-sell `qty` contracts of an open long option (the scale-out / runner exit leg).

    REFUSES without live=True (WATCH) and on an invalid qty. This is how the tick-managed
    exit manager realizes a SELL_PARTIAL (TP1) or SELL_ALL (stop/target/time) action that
    Alpaca's single-leg bracket cannot express natively."""
    if not live:
        return {"_skipped": "live flag is False -- market_sell refused (WATCH mode)"}
    if qty is None or int(qty) < 1:
        return {"_refused": f"invalid qty {qty}"}
    order = {"symbol": symbol, "qty": str(int(qty)), "side": "sell",
             "type": "market", "time_in_force": "day"}
    return _request(creds, "orders", method="POST", data=order)


def replace_stop_order(creds: dict[str, str], *, order_id: str, stop_price: float,
                       live: bool) -> dict:
    """Ratchet an open stop order to a new stop price (runner -> BE, then chandelier trail).

    REFUSES without live=True or an invalid stop. Maps to Alpaca PATCH /orders/{id}. The
    exit manager emits a RATCHET_STOP action; this realizes it. Idempotent-ish: re-issuing
    the same stop is harmless."""
    if not live:
        return {"_skipped": "live flag is False -- replace_stop_order refused (WATCH mode)"}
    if stop_price is None or float(stop_price) <= 0:
        return {"_refused": "null/invalid stop -- refusing to widen to a naked stop (C2)"}
    return _request(creds, f"orders/{order_id}", method="PATCH",
                    data={"stop_price": str(round(float(stop_price), 2))})


def close_all_spy_options(creds: dict[str, str], *, live: bool) -> dict:
    """EOD flatten primitive: market-sell every open SPY option position.

    Read-only (returns the would-close list) unless live=True. Idempotent.
    """
    positions = open_spy_option_positions(creds)
    if not live:
        return {"_skipped": "live flag False", "would_close": [p.get("symbol") for p in positions]}
    closed, errors = [], []
    for p in positions:
        sym = p.get("symbol")
        qty = abs(int(float(p.get("qty", 0))))
        if qty < 1:
            continue
        order = {"symbol": sym, "qty": str(qty), "side": "sell",
                 "type": "market", "time_in_force": "day"}
        res = _request(creds, "orders", method="POST", data=order)
        (errors if isinstance(res, dict) and res.get("_error") else closed).append(sym)
    return {"closed": closed, "errors": errors, "remaining": len(open_spy_option_positions(creds))}


if __name__ == "__main__":
    # Read-only self-check: prove every arm's creds reach the broker (no secrets printed).
    creds_all = load_creds()
    print(f"{'arm':10} {'account#':14} {'status':9} {'equity':>10} {'flat_spy':>9}")
    print("-" * 60)
    for arm, c in creds_all.items():
        acct = get_account(c)
        if acct.get("_error"):
            print(f"{arm:10} ERROR {acct.get('_status','')} {str(acct.get('_error'))[:30]}")
            continue
        print(f"{arm:10} {acct.get('account_number',''):14} {acct.get('status',''):9} "
              f"{acct.get('equity',''):>10} {str(is_flat_spy_options(c)):>9}")
