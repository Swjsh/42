#!/usr/bin/env python3
"""Kalshi REST client — public market data unauthenticated, private endpoints RSA-PSS signed.

AUTH (verified against Kalshi docs 2026-08-09):
    headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE
    signed string = f"{timestamp_ms}{METHOD}{path}"   <- path WITHOUT query params
    algorithm    = RSA-PSS, SHA-256 digest + MGF1(SHA-256), salt length = 32, base64

CREDENTIALS never live in this file or any tracked file. They are read from the
GITIGNORED automation/state/fleet/secrets.json under accounts/<arm>/, matching the
shape the Alpaca arms already use:

    "kalshi-1": {
        "key":         "<api key id (a UUID)>",
        "secret_path": "automation/state/fleet/kalshi-1.pem",   # preferred
        "secret":      "-----BEGIN RSA PRIVATE KEY-----\\n...",  # or inline PEM
        "base_url":    "https://api.elections.kalshi.com/trade-api/v2",
        "label":       "KALSHI-1"
    }

Public market data needs NO credentials at all -- shadow mode runs fully without them.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "automation" / "state" / "fleet" / "secrets.json"

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"

# Kalshi auto-generates multi-leg parlay series. They compound spread+fee per leg and
# flood every listing endpoint. Filtered at the data layer, never surfaced upward.
PARLAY_PREFIX = "KXMVE"


class KalshiError(RuntimeError):
    pass


class KalshiAuthMissing(KalshiError):
    """Raised only when a PRIVATE endpoint is called without credentials."""


@dataclass(frozen=True)
class Credentials:
    key_id: str
    private_key: rsa.RSAPrivateKey
    base_url: str
    label: str


def load_credentials(arm: str = "kalshi-1", secrets_path: Path | None = None) -> Credentials | None:
    """Load creds from the gitignored store. Returns None if absent -- callers decide if that's fatal."""
    path = secrets_path or SECRETS
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise KalshiError(f"secrets store unreadable: {e}") from e

    acct = (blob.get("accounts") or {}).get(arm)
    if not acct:
        return None

    key_id = acct.get("key")
    pem: str | None = None
    if acct.get("secret_path"):
        pem_file = Path(acct["secret_path"])
        if not pem_file.is_absolute():
            pem_file = REPO / pem_file
        if not pem_file.exists():
            raise KalshiError(f"secret_path points at a missing file: {pem_file}")
        pem = pem_file.read_text()
    elif acct.get("secret"):
        pem = acct["secret"]

    if not key_id or not pem:
        return None

    try:
        loaded = serialization.load_pem_private_key(pem.encode(), password=None)
    except Exception as e:  # noqa: BLE001 - surface a clean message, never echo key material
        raise KalshiError(f"private key failed to parse (is it a valid RSA PEM?): {type(e).__name__}") from e
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise KalshiError("credential is not an RSA private key -- Kalshi requires RSA")

    return Credentials(
        key_id=key_id,
        private_key=loaded,
        base_url=(acct.get("base_url") or PROD_BASE).rstrip("/"),
        label=acct.get("label") or arm,
    )


class KalshiClient:
    """Thin, explicit REST client. Public reads work with creds=None."""

    def __init__(self, creds: Credentials | None = None, base_url: str | None = None,
                 timeout: int = 25) -> None:
        self.creds = creds
        self.base_url = (base_url or (creds.base_url if creds else PROD_BASE)).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "gamma-kalshi/1.0", "Accept": "application/json"})

    # ---------------------------------------------------------------- signing
    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        if not self.creds:
            raise KalshiAuthMissing(
                "private endpoint requires credentials -- add accounts.kalshi-1 to "
                f"{SECRETS.relative_to(REPO)} (see module docstring)"
            )
        ts = str(int(time.time() * 1000))          # MILLISECONDS, not seconds
        message = f"{ts}{method.upper()}{path}"    # path must exclude query params
        signature = self.creds.private_key.sign(
            message.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=hashes.SHA256().digest_size),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.creds.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }

    def _request(self, method: str, path: str, *, private: bool = False,
                 params: dict | None = None, body: dict | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}
        if private:
            # Per Kalshi docs (getting_started/api_environments): "Request signing uses the
            # same signed path regardless of which host is used." So the signed string is
            # the URL PATH ONLY -- host excluded, query string excluded.
            signed_path = urlparse(self.base_url).path.rstrip("/") + path.split("?", 1)[0]
            headers = self._auth_headers(method, signed_path)
        try:
            resp = self._session.request(method, url, headers=headers, params=params,
                                         json=body, timeout=self.timeout)
        except requests.RequestException as e:
            raise KalshiError(f"network failure on {method} {path}: {e}") from e

        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise KalshiError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as e:
            raise KalshiError(f"non-JSON response on {method} {path}") from e

    # ----------------------------------------------------------- public reads
    def exchange_status(self) -> dict:
        return self._request("GET", "/exchange/status")

    def markets(self, *, series_ticker: str | None = None, status: str = "open",
                limit: int = 200, drop_parlays: bool = True) -> list[dict]:
        params: dict[str, Any] = {"status": status, "limit": min(limit, 1000)}
        if series_ticker:
            params["series_ticker"] = series_ticker
        out = self._request("GET", "/markets", params=params).get("markets", [])
        if drop_parlays:
            out = [m for m in out
                   if not str(m.get("event_ticker", "")).startswith(PARLAY_PREFIX)
                   and not str(m.get("ticker", "")).startswith(PARLAY_PREFIX)]
        return out

    def market(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}").get("market", {})

    def orderbook(self, ticker: str, depth: int = 10) -> dict[str, list[tuple[float, float]]]:
        """The depth read -- the number that decides whether capacity exists.

        Kalshi returns `orderbook_fp` with `yes_dollars` / `no_dollars` as ascending
        [price_str, size_str] pairs. We normalise to floats sorted BEST FIRST
        (descending price = highest bid first) so callers never re-derive it.

        NOTE both sides are BIDS. A resting `no` bid at 0.58 is equivalently a `yes`
        offer at 1 - 0.58 = 0.42. `best_prices()` below does that conversion.
        """
        raw = self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})
        book = raw.get("orderbook_fp") or raw.get("orderbook") or {}
        out: dict[str, list[tuple[float, float]]] = {"yes": [], "no": []}
        for side in ("yes", "no"):
            levels = book.get(f"{side}_dollars") or book.get(side) or []
            parsed: list[tuple[float, float]] = []
            for lv in levels:
                if not isinstance(lv, (list, tuple)) or len(lv) < 2:
                    continue
                try:
                    parsed.append((float(lv[0]), float(lv[1])))
                except (TypeError, ValueError):
                    continue
            out[side] = sorted(parsed, key=lambda x: -x[0])
        return out

    @staticmethod
    def best_prices(book: dict[str, list[tuple[float, float]]]) -> dict[str, float | None]:
        """Convert a two-sided bid book into yes bid/ask + size at each touch."""
        yes_levels, no_levels = book.get("yes") or [], book.get("no") or []
        yes_bid, yes_bid_sz = (yes_levels[0] if yes_levels else (None, None))
        no_bid, no_bid_sz = (no_levels[0] if no_levels else (None, None))
        yes_ask = round(1.0 - no_bid, 4) if no_bid is not None else None
        spread = round((yes_ask - yes_bid) * 100, 2) if (yes_ask is not None and yes_bid is not None) else None
        return {"yes_bid": yes_bid, "yes_bid_size": yes_bid_sz,
                "yes_ask": yes_ask, "yes_ask_size": no_bid_sz,
                "spread_cents": spread}

    # ---------------------------------------------------------- private reads
    def balance(self) -> dict:
        """Account balance in CENTS under key 'balance'."""
        return self._request("GET", "/portfolio/balance", private=True)

    def positions(self) -> dict:
        return self._request("GET", "/portfolio/positions", private=True)

    def orders(self, status: str | None = None) -> dict:
        params = {"status": status} if status else None
        return self._request("GET", "/portfolio/orders", private=True, params=params)

    # --------------------------------------------------------------- trading
    def place_order(self, *, ticker: str, side: str, action: str, count: int,
                    limit_price_cents: int, client_order_id: str,
                    time_in_force: str = "") -> dict:
        """Place an order. LIMIT ONLY BY DESIGN.

        The economics model showed taking the spread costs 5-6x the maker fee, so this
        client deliberately exposes no market-order path. If you want to cross, post a
        limit at the far touch -- that is an explicit choice, not a default.
        """
        if side not in ("yes", "no"):
            raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
        if action not in ("buy", "sell"):
            raise ValueError(f"action must be 'buy' or 'sell', got {action!r}")
        if not 1 <= limit_price_cents <= 99:
            raise ValueError(f"limit price must be 1-99 cents, got {limit_price_cents}")
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")

        body = {
            "ticker": ticker,
            "client_order_id": client_order_id,
            "side": side,
            "action": action,
            "count": int(count),
            "type": "limit",
            f"{side}_price": int(limit_price_cents),
        }
        if time_in_force:
            body["time_in_force"] = time_in_force
        return self._request("POST", "/portfolio/orders", private=True, body=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/orders/{order_id}", private=True)


# ------------------------------------------------------------------ fee model
def fee_dollars(contracts: int, price_dollars: float, maker: bool = True) -> float:
    """Exact Kalshi fee. ceil applies to the ORDER TOTAL (verified 2026-08-09)."""
    import math
    rate = 0.0175 if maker else 0.07
    return math.ceil(rate * contracts * price_dollars * (1 - price_dollars) * 100) / 100


if __name__ == "__main__":
    c = KalshiClient()
    st = c.exchange_status()
    print(f"exchange_active={st.get('exchange_active')} trading_active={st.get('trading_active')}")
    creds = load_credentials()
    print(f"credentials: {'LOADED (' + creds.label + ')' if creds else 'ABSENT -- shadow mode only'}")
