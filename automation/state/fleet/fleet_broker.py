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
