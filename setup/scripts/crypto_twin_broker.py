"""crypto_twin_broker -- minimal stdlib Alpaca REST client for the CRYPTO TWIN.

Sibling of automation/state/fleet/fleet_broker.py, NOT a fork of it: every function
here that IS asset-class-agnostic (account/positions/orders/fills plumbing) is
IMPORTED from fleet_broker directly and re-exported -- see the "REUSED VERBATIM"
section below. Only genuinely crypto-specific pieces are new code:

  * qty is FRACTIONAL (BTC, not whole option contracts) -- fleet_broker.get_position_qty
    does `int(float(qty))`, which truncates a real crypto position (e.g. 0.003 BTC ->
    int(0.003) == 0, i.e. would misreport a real position as flat). Cannot be reused.
  * orders use `notional` (dollar-based market entries) and time_in_force="gtc"
    (crypto has no trading-day boundary -- Alpaca rejects "day" for crypto orders).
  * market data (bars/quotes) comes from /v1beta3/crypto/us/*, not the options feed.
  * creds load from THIS namespace's own automation/state/crypto-twin/secrets.json --
    a DEDICATED account, deliberately never fleet's or core's (see secrets.json.example
    for why: fleet_live.py sources its kill-switch/risk-cap equity straight from
    GET /v2/account, a unified per-account total across every asset class held in that
    account -- adding BTC positions to any of the 6 fleet/core accounts would corrupt
    that arm's SPY-grid attribution. This module refuses to load fleet's or the
    project-root .mcp.json accounts for ORDER/POSITION calls; see get_twin_creds()).

Market-DATA reads (bars/quotes) are the one place this module tolerates an ambient
key: Alpaca's crypto market-data endpoints are account-agnostic (any valid key/secret
pair authenticates the SAME public feed; verified live 2026-07-10 that they even work
completely UNAUTHENTICATED). Reading bars/quotes never touches account equity,
positions, or orders, so borrowing an existing key for THAT ONE read-only call carries
none of the contamination risk described above -- see _best_effort_market_data_creds().

SAFETY (mirrors fleet_broker exactly):
  * Read-only methods (get_account / get_positions / bars / quotes) never require live=True.
  * place_crypto_order() REFUSES unless live=True is passed explicitly.
  * No SDK dependency (urllib only) -- matches fleet_broker.py / heartbeat_core.py convention.

This module PLACES nothing on import and has no __main__ side effects beyond a
read-only self-check (mirrors fleet_broker's `python -m crypto_twin_broker`).
"""
from __future__ import annotations

import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
TWIN_SECRETS_PATH = TWIN_DIR / "secrets.json"
TWIN_SECRETS_EXAMPLE = TWIN_DIR / "secrets.json.example"
MCP_JSON = REPO / ".mcp.json"

CRYPTO_DATA_HOST = "https://data.alpaca.markets"
CRYPTO_SYMBOL_DEFAULT = "BTC/USD"

# --- REUSED VERBATIM from fleet_broker (asset-class-agnostic REST plumbing) --------
# heartbeat_core.py's own sys.path convention: insert automation/state/fleet so the
# loose module resolves, then import it directly (fleet_broker.py has no package
# __init__.py -- it's a standalone module, same as this file).
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import fleet_broker as _fb  # noqa: E402

get_account = _fb.get_account            # GET /v2/account -- generic, works for any account
get_positions = _fb.get_positions        # GET /v2/positions -- generic
get_order = _fb.get_order                # GET /v2/orders/{id} -- generic
poll_fill = _fb.poll_fill                # polls get_order until filled/exhausted -- generic
cancel_order = _fb.cancel_order          # DELETE /v2/orders/{id} -- generic, WATCH-gated


# --- creds ---------------------------------------------------------------------------
def load_creds() -> dict[str, dict[str, str]]:
    """{"twin": {key, secret, base_url}} from the gitignored crypto-twin secrets.json.

    Byte-identical shape/loader logic to fleet_broker.load_creds() (deliberately not
    imported -- fleet_broker's version points at FLEET_DIR/secrets.json; re-pointing it
    at this namespace via a kwarg would be the more "DRY" move, but fleet_broker.py is
    production code another crew may be touching tonight, and this 15-line loader is
    cheap enough to keep as a sibling rather than risk a shared-surface edit there.
    """
    if not TWIN_SECRETS_PATH.exists():
        raise FileNotFoundError(
            f"crypto_twin_broker: {TWIN_SECRETS_PATH} not found. Copy "
            f"{TWIN_SECRETS_EXAMPLE.name} to secrets.json in the same directory and fill in "
            "a DEDICATED Alpaca paper account (NOT any of the 6 fleet/core accounts -- "
            "see secrets.json.example for why)."
        )
    data = json.loads(TWIN_SECRETS_PATH.read_text(encoding="utf-8"))
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


class CryptoNotApprovedError(RuntimeError):
    """The configured twin account exists and authenticates, but Alpaca has not activated
    crypto trading on it (crypto_status != "ACTIVE"). Distinct from the missing-account case
    (FileNotFoundError/KeyError) so a caller can't confuse "no creds yet" with "creds exist
    but crypto isn't enabled" -- the fix is different (submit the crypto_agreement via the
    Accounts API; see https://docs.alpaca.markets/us/docs/crypto-trading-1) and a silent
    misclassification would have J hunting the wrong problem after he's already done the
    account-creation step. Never raised for a market-data-only caller (crypto bars/quotes
    are account-agnostic public feeds -- see _best_effort_market_data_creds)."""


def get_twin_creds(*, verify_crypto_status: bool = True) -> dict[str, str]:
    """The twin's own dedicated account creds ({"key","secret","base_url"}).

    Raises the same FileNotFoundError as load_creds() when unconfigured, or KeyError if
    secrets.json exists but has no "twin" entry. Callers that only need MARKET DATA
    (bars/quotes) should prefer _best_effort_market_data_creds() instead, which degrades
    gracefully when no account is configured yet -- this function is for ORDER/POSITION/
    ACCOUNT calls, which have no safe fallback (T2 is genuinely blocked without it).

    verify_crypto_status=True (default) additionally confirms the account's crypto_status
    is "ACTIVE" via GET /v2/account -- raises CryptoNotApprovedError otherwise. Every one of
    this project's existing paper accounts already shows crypto_status=ACTIVE (verified live
    2026-07-10 via the core Safe-2/Bold-2 accounts), so a genuinely fresh account is EXPECTED
    to inherit the same default; this check exists purely so a rarer INACTIVE account fails
    LOUD with the exact remediation instead of silently misbehaving on order placement.
    Pass False only from a context that cannot make a network call (e.g. a pure unit test).
    """
    creds = load_creds()
    if "twin" not in creds:
        raise KeyError(
            f"crypto_twin_broker: {TWIN_SECRETS_PATH} has no 'twin' account entry "
            f"(have {list(creds)}). See {TWIN_SECRETS_EXAMPLE.name}."
        )
    twin_creds = creds["twin"]
    if verify_crypto_status:
        acct = get_account(twin_creds)
        status = (acct or {}).get("crypto_status")
        if status != "ACTIVE":
            raise CryptoNotApprovedError(
                f"crypto_twin_broker: twin account crypto_status={status!r} (need 'ACTIVE'). "
                "Submit the crypto_agreement via Alpaca's Accounts API for this account, then "
                "retry -- see https://docs.alpaca.markets/us/docs/crypto-trading-1"
            )
    return twin_creds


def _best_effort_market_data_creds() -> Optional[dict[str, str]]:
    """Best-effort creds for READ-ONLY market-data calls only (bars/quotes).

    Preference order: (1) the twin's own dedicated account, once configured; (2) the
    project-root .mcp.json "alpaca" (Safe-2) server env -- READ-ONLY market-data use is
    safe to borrow (see module docstring: crypto bars/quotes are account-agnostic public
    feeds, never touching Safe-2's equity/positions/orders); (3) None, in which case
    callers fall back to Alpaca's completely UNAUTHENTICATED crypto data tier (verified
    live 2026-07-10 -- see fetch_crypto_bars). Never raises.
    """
    try:
        return get_twin_creds()
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    try:
        cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
        env = cfg["mcpServers"]["alpaca"]["env"]
        key, secret = env.get("ALPACA_API_KEY"), env.get("ALPACA_SECRET_KEY")
        if key and secret:
            return {"key": key, "secret": secret, "base_url": "https://paper-api.alpaca.markets"}
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        pass
    return None


def _data_headers(creds: Optional[dict[str, str]]) -> dict[str, str]:
    if not creds:
        return {}
    return {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}


# --- market data (bars/quotes) --------------------------------------------------------
def fetch_crypto_bars(symbol: str = CRYPTO_SYMBOL_DEFAULT, *, granularity_seconds: int = 300,
                      limit: int = 200, creds: Optional[dict[str, str]] = None) -> list[dict]:
    """Raw Alpaca crypto bars (oldest-first), including any in-progress trailing bar --
    the CALLER filters to closed-only (crypto_twin_core uses crypto.lib.bar_reader, C6).

    `creds=None` uses _best_effort_market_data_creds() (falls all the way through to
    the UNAUTHENTICATED public tier -- confirmed live-working 2026-07-10). Raises on a
    genuine HTTP/network failure (fail-loud: T1 must not silently log a stale/empty tick
    as if it read real bars).
    """
    tf_map = {60: "1Min", 300: "5Min", 900: "15Min", 1800: "30Min", 3600: "1Hour", 86400: "1Day"}
    if granularity_seconds not in tf_map:
        raise ValueError(f"unsupported granularity_seconds: {granularity_seconds}")
    if creds is None:
        creds = _best_effort_market_data_creds()
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) - timedelta(seconds=granularity_seconds * limit * 3))
    url = (f"{CRYPTO_DATA_HOST}/v1beta3/crypto/us/bars?symbols={symbol.replace('/', '%2F')}"
          f"&timeframe={tf_map[granularity_seconds]}&start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
          f"&sort=asc&limit={limit * 3}")
    req = urllib.request.Request(url, headers=_data_headers(creds))
    with urllib.request.urlopen(req, timeout=15) as r:
        payload = json.loads(r.read().decode("utf-8"))
    rows = (payload.get("bars") or {}).get(symbol, [])
    return rows[-limit:] if rows else []


def get_crypto_quote_hilo(symbol: str = CRYPTO_SYMBOL_DEFAULT,
                          creds: Optional[dict[str, str]] = None) -> Optional[tuple[float, float]]:
    """(best_ask, worst_bid) for this tick -- the crypto analog of
    fleet_broker.get_option_quote_hilo. None on failure (caller HOLDS, never force-exits
    on a missing quote -- same discipline as the options path)."""
    if creds is None:
        creds = _best_effort_market_data_creds()
    url = f"{CRYPTO_DATA_HOST}/v1beta3/crypto/us/latest/quotes?symbols={symbol.replace('/', '%2F')}"
    req = urllib.request.Request(url, headers=_data_headers(creds))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            q = json.loads(r.read().decode("utf-8")).get("quotes", {}).get(symbol)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    if not q:
        return None
    bid, ask = q.get("bp"), q.get("ap")
    if bid and ask and bid > 0 and ask > 0:
        return round(float(ask), 2), round(float(bid), 2)
    return None


# --- positions / orders (crypto-specific: fractional qty) -----------------------------
def get_crypto_position_qty(creds: dict[str, str], symbol: str = CRYPTO_SYMBOL_DEFAULT) -> float:
    """Open FRACTIONAL qty the broker shows for this crypto symbol (0.0 if flat).

    NOT fleet_broker.get_position_qty -- that truncates via int(float(qty)), which would
    silently misreport a real 0.003 BTC position as flat. Broker is the source of truth
    (C11); this preserves the fraction fleet's version discards.
    """
    for p in get_positions(creds):
        sym = str(p.get("symbol", ""))
        if sym == symbol or sym == symbol.replace("/", ""):
            try:
                return abs(float(p.get("qty", 0)))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def place_crypto_order(creds: dict[str, str], *, symbol: str = CRYPTO_SYMBOL_DEFAULT,
                       side: str, notional: Optional[float] = None, qty: Optional[float] = None,
                       order_type: str = "market", limit_price: Optional[float] = None,
                       live: bool) -> dict:
    """Place ONE crypto order. REFUSES without live=True (WATCH mode -- mirrors
    fleet_broker.place_bracket / market_sell exactly).

    Exactly one of `notional` (dollar-based -- the entry path, HARD RAILS "~$200/entry")
    or `qty` (fractional BTC -- the exit path, selling a fraction of a held position)
    must be given. time_in_force is ALWAYS "gtc": Alpaca crypto orders reject "day"
    (crypto has no trading-day boundary -- confirmed against Alpaca's crypto order docs;
    the options/equity paths elsewhere in this repo use "day" deliberately, this is the
    one place that must differ).
    """
    if not live:
        return {"_skipped": "live flag is False -- place_crypto_order refused (WATCH mode)"}
    if side not in ("buy", "sell"):
        return {"_refused": f"invalid side {side!r}"}
    if (notional is None) == (qty is None):
        return {"_refused": "exactly one of notional/qty must be given"}
    order: dict[str, Any] = {"symbol": symbol, "side": side, "type": order_type,
                             "time_in_force": "gtc"}
    if notional is not None:
        if float(notional) <= 0:
            return {"_refused": f"invalid notional {notional}"}
        order["notional"] = str(round(float(notional), 2))
    else:
        if float(qty) <= 0:
            return {"_refused": f"invalid qty {qty}"}
        q = float(qty)
        if side == "sell":
            # FLOOR, never round(): fee-shaved crypto positions carry sub-8dp balances
            # (e.g. 0.002396399 BTC after a 0.0024 buy) and round-half-up requests 1e-9
            # MORE than the broker holds -> Alpaca 403 "insufficient balance" -> the exit
            # silently fails. Caught LIVE 2026-07-15 03:58 UTC on the twin's first
            # passive-entry time_stop close (TWIN-B3 ROI ledger: mechanism_bugs_caught).
            q = math.floor(q * 1e8) / 1e8
            if q <= 0:
                return {"_refused": f"qty {qty} floors to 0 at 8dp"}
        else:
            q = round(q, 8)
        order["qty"] = f"{q:.8f}".rstrip("0").rstrip(".")  # never scientific notation
    if order_type == "limit":
        if limit_price is None or float(limit_price) <= 0:
            return {"_refused": "limit order requires a positive limit_price"}
        order["limit_price"] = str(round(float(limit_price), 2))
    return _fb._request(creds, "orders", method="POST", data=order)


def market_sell_crypto(creds: dict[str, str], *, symbol: str = CRYPTO_SYMBOL_DEFAULT,
                       qty: float, live: bool) -> dict:
    """Sell `qty` (fractional) of an open crypto long -- the scale-out / runner exit leg.
    Thin alias over place_crypto_order for readability at call sites."""
    return place_crypto_order(creds, symbol=symbol, side="sell", qty=qty, live=live)


def close_all_crypto(creds: dict[str, str], *, symbol: str = CRYPTO_SYMBOL_DEFAULT,
                     live: bool) -> dict:
    """Max-hold / EOD-style flatten primitive: market-sell the entire open position in
    `symbol`. Idempotent (no-op when already flat). Mirrors fleet_broker.close_all_spy_options."""
    qty = get_crypto_position_qty(creds, symbol)
    if qty <= 0:
        return {"_skipped": "already flat", "symbol": symbol}
    if not live:
        return {"_skipped": "live flag False", "would_close": symbol, "qty": qty}
    return place_crypto_order(creds, symbol=symbol, side="sell", qty=qty, live=True)


if __name__ == "__main__":
    # Read-only self-check (mirrors fleet_broker.py's __main__): proves market data is
    # reachable and, if a dedicated account is configured, that it authenticates. Never
    # prints secrets.
    bars = fetch_crypto_bars(limit=3)
    print(f"market-data self-check: {len(bars)} BTC/USD 5m bars fetched "
         f"(last close={bars[-1]['c'] if bars else 'n/a'})")
    try:
        creds = get_twin_creds()
        acct = get_account(creds)
        if acct.get("_error"):
            print(f"twin account: ERROR {acct.get('_status','')} {str(acct.get('_error'))[:60]}")
        else:
            print(f"twin account: {acct.get('account_number','')} status={acct.get('status','')} "
                 f"equity={acct.get('equity','')}")
    except (FileNotFoundError, KeyError) as e:
        print(f"twin account: NOT CONFIGURED ({e})")
