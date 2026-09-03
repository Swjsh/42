"""Tastytrade paper-trading connector for the Futures Edition.

Replaces ibkr_paper.py — identical external interface so futures-heartbeat.md
needs no structural changes. Uses `pip install tastytrade` (v12+, async SDK).

Setup (one-time OAuth2 — do this once, tokens never expire):
  1. Create a Tastytrade account at tastytrade.com
  2. Go to: my.tastytrade.com → Settings → API Access → OAuth Applications
     → Create Application → add callback URL http://localhost:8000 → Save
     → Copy the client_secret shown
  3. In that same app page: Manage → Create Grant → copy the refresh_token
  4. For sandbox: go to api.cert.tastyworks.com to create a sandbox account
     (same OAuth app works for both environments)
  5. pip install tastytrade
  6. Set env vars (SDK reads TT_SECRET / TT_REFRESH by default):
       TT_SECRET       — client_secret from step 2
       TT_REFRESH      — refresh_token from step 3
       TT_SANDBOX      — "true" (default) = sandbox/cert; "false" = live
       TT_ACCOUNT      — optional: target a specific account number

WATCH_ONLY mode (default True): logs would-be orders to would-be-trades.jsonl.
No network calls, no SDK import needed. Flip to False + set env vars for live paper.

Sandbox notes:
  - Base URL: api.cert.tastyworks.com (is_test=True handles this automatically)
  - Resets every 24h (trades/positions cleared; accounts persist)
  - Quotes are 15-min delayed
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import datetime as dt
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

REPO      = Path(__file__).resolve().parent.parent.parent
STATE_DIR = REPO / "automation" / "state" / "futures"
STATE_DIR.mkdir(parents=True, exist_ok=True)

POSITION_FILE = STATE_DIR / "position.json"
ACCOUNT_FILE  = STATE_DIR / "account.json"
WOULD_BE_FILE = STATE_DIR / "would-be-trades.jsonl"
BROKER_TRANSPORT_FILE = STATE_DIR / "broker-transport.jsonl"  # 2026-08-29 diagnosability fix --
                                                                # see module docstring / helpers
                                                                # below "Transport diagnosability"

WATCH_ONLY = True  # DEFAULT-SAFE, and every caller may still override per instance.
#
# ORIGINAL RATIONALE (2026-06-21 readiness audit), now PARTLY OBSOLETE -- recorded rather
# than deleted, because two of its three legs were real and one has quietly expired:
#   (a) "the futures engine is an unbuilt stub"        -> NO LONGER TRUE. The deterministic
#       tick exists (futures_trader_core), with dollar risk rails, drills and guards.
#   (b) "all 3 Gamma_Futures* tasks are DISABLED"      -> NO LONGER TRUE. Gamma_FuturesTrader
#       and Gamma_FuturesEod2 are registered and firing.
#   (c) ".env.tastytrade also carries live-PROD OAuth tokens" -> **VERIFIED FALSE 2026-08-09**:
#       the file now holds ONLY TT_SECRET / TT_REFRESH / TT_SANDBOX. No TT_PROD_* key exists.
#       That leg was the actual loaded gun, and it is unloaded. (Re-check before assuming --
#       if a PROD token is ever re-added, this default must go back to hard-locked.)
#
# WHY IT STAYS True AS THE DEFAULT ANYWAY: a module-level constant is the wrong place to
# arm anything. Routing is a per-lane decision made by the caller that owns the lane's
# state and risk rails -- futures_trader_core passes watch_only explicitly, gated on
# FUTURES_ARMED. A caller that forgets to think about it gets the safe behaviour.
#
# SANDBOX ONLY, ALWAYS: TT_SANDBOX=true points at api.cert.tastyworks.com. Live money is
# OP-0 #1 plus a new venue -- double-gated, and not reachable from this file's config.
POINT_VALUE = {"MNQ": 2, "MES": 5, "NQ": 20, "ES": 50}


# ── Async helper ───────────────────────────────────────────────────────────────

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent event loop, creating one if needed."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _run(coro):
    """Run async coroutine from synchronous context, handling running loops."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return _get_loop().run_until_complete(coro)


# ── Transport diagnosability (2026-08-29) ───────────────────────────────────────
#
# WHY THIS EXISTS: the MES mirror lane (armed 2026-08-20) has placed 8 order attempts, 0
# placed. 7 of 8 rows in mirror-broker-orders.jsonl read {"order_ids": [], "placed": false}
# with NO reason field. automation/state/logs/futures-mirror-shadow.stderr.log shows the root
# cause -- the Tastytrade SANDBOX is intermittently unavailable:
#     get_positions failed: TastytradeError: Couldn't parse response: <html>502 Bad
#         Gateway</html> nginx/1.31.0
#     get_account_equity failed: ReadTimeout:
#     Tastytrade connect failed: (x6)
# `log = logging.getLogger(__name__)` (module top) has NO handler configured anywhere in this
# repo -- log.warning/log.error calls (including the 2026-08-21 _leg_failure_detail() fix)
# never reach disk. This section bypasses that dead logger entirely with direct, fail-open
# file writes, and fixes a second bug in the same incident: `str(exc)` is EMPTY for several of
# these exceptions ("ReadTimeout: " with nothing after the colon) -- every check below
# classifies by exception TYPE/repr, never str(exc) alone.

_TRANSPORT_STATUS_MARKERS = ("502", "503", "504", "429")
_RETRY_DELAYS_SEC = (1.0, 3.0, 9.0)   # exponential backoff, deterministic (no jitter). The
                                        # default max_attempts=3 (see _with_retry / place_bracket
                                        # below) consumes only delays[0:2] (1s, 3s) -- two sleeps
                                        # between three total tries. The 9s figure is kept in the
                                        # tuple (task spec named all three) so a future caller
                                        # raising max_attempts to 4 picks it up with no code change.


def _et_now_str() -> str:
    """ET wall-clock timestamp for diagnostic logging, DST-aware via the repo's shared clock --
    never a naive local read (this box runs Mountain time, CLAUDE.md TZ scar). Self-contained
    (matches this file's existing zero-sibling-import design -- no other backtest/futures/*.py
    module is imported here) rather than depending on a sibling futures.* module: inserts
    setup/scripts onto sys.path exactly like futures_session.et_now() does, then lazily imports
    et_clock so a test's monkeypatch of et_clock.et_now is honored. Fail-open to naive local
    time on any import/lookup failure -- this is a diagnostic log timestamp, never a trading
    decision input, so best-effort beats blocking the log write."""
    try:
        p = str(REPO / "setup" / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)
        import et_clock  # noqa: PLC0415

        return et_clock.et_now().replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001 -- best-effort timestamp, never blocks the caller
        return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _is_transport_error(exc: BaseException) -> bool:
    """True iff `exc` looks like a TRANSPORT failure (timeout / gateway / connection reset --
    something that never reached the broker's own order-matching/validation logic) rather than
    a genuine broker-side answer. Drives (a) whether connect/get_positions/get_account_equity/a
    leg placement is safe to retry, and (b) the `outcome` field on every broker-transport.jsonl
    row. Must NEVER return True for a clean response that merely carries `errors`/`warnings` --
    that already reached the broker and answered; retrying it would spam a real rejection.

    Classify by TYPE first: str(exc) is EMPTY for some httpx timeouts seen live ("ReadTimeout: "
    with nothing after the colon) -- a message-only check would miss exactly the case this
    fixes."""
    try:
        import httpx  # noqa: PLC0415 -- only reachable once tastytrade (its own dependency) is
        if isinstance(exc, httpx.RequestError):   # covers Timeout*/Connect*/Network*/Protocol*
            return True
    except ImportError:
        pass
    cls_name = type(exc).__name__.lower()
    if any(marker in cls_name for marker in ("timeout", "connecterror", "connectionerror")):
        return True
    text = f"{exc!r} {exc}".lower()
    if "couldn't parse response" in text or "could not parse response" in text:
        # 2026-09-03 fix: tastytrade.utils.validate_response wraps EVERY body it can't map
        # into its typed response object under this SAME generic prefix -- both genuine
        # gateway noise (an HTML 502 page, an empty body) AND a well-formed JSON error the
        # SDK's own schema just doesn't recognize (live evidence: broker-transport.jsonl
        # 2026-09-01/02, "Couldn't parse response: {'error_code': 'invalid_request',
        # 'error_description': 'User is not a TastyTrade customer'}", 5x). The latter IS a
        # broker-side ANSWER, not noise: it deterministically re-fails every retry (wasting
        # ~13s of the 1/3/9s backoff for nothing) and was being logged as transport_error,
        # burying a genuine account/entitlement message inside the "flaky gateway" bucket
        # where nobody would ever read it as what it is. A structured `error_code` in the
        # wrapped text is the signal that the SDK actually reached the broker and got a real
        # (if unparseable-by-schema) answer back -- classify that as NOT transport so it logs
        # `auth_or_permission_error` and fails fast instead of retrying blind.
        if "error_code" not in text:
            return True
    if any(code in text for code in _TRANSPORT_STATUS_MARKERS):
        return True
    return False


def _extract_http_status(exc: BaseException) -> Optional[str]:
    """Best-effort HTTP status extraction from an exception's repr/str -- 502/503/504/429 are
    the ones actually seen live (gateway/rate-limit class). None if nothing matches; never
    raises."""
    text = f"{exc!r} {exc}"
    for code in _TRANSPORT_STATUS_MARKERS:
        if code in text:
            return code
    return None


def _log_broker_transport(call: str, outcome: str, *, exc: Optional[BaseException] = None,
                          detail: Optional[str] = None) -> None:
    """Appends ONE structured row to broker-transport.jsonl for a leg rejection or transport
    exception -- see "Transport diagnosability" above. `call` is one of: place_bracket_entry /
    tp1 / stop / runner / connect / get_positions / get_account_equity / place_bracket (the
    last for a structural failure before any leg was attempted). `outcome` is one of:
    leg_rejected / transport_error / transport_error_not_retried_ambiguous. NEVER raises --
    this is a diagnostic side channel; a logging hiccup must not break the caller's own
    fail-open contract (mirrors WOULD_BE_FILE's append pattern elsewhere in this file)."""
    try:
        row = {
            "ts_et": _et_now_str(),
            "call": call,
            "outcome": outcome,
            "error_class": type(exc).__name__ if exc is not None else None,
            "error_repr": repr(exc)[:500] if exc is not None else None,
            "http_status": _extract_http_status(exc) if exc is not None else None,
            "detail": detail,
        }
        BROKER_TRANSPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BROKER_TRANSPORT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:  # noqa: BLE001 -- logging must never raise
        pass


def _with_retry(fn, *, max_attempts: int = 3, delays: tuple = _RETRY_DELAYS_SEC):
    """Runs `fn()` (a zero-arg callable performing ONE network call) with up to `max_attempts`
    TOTAL tries, retrying ONLY on a transport-classified failure (`_is_transport_error`) -- a
    non-transport exception (e.g. a genuine auth/permissions TastytradeError, or a KeyError) is
    re-raised immediately on its first occurrence, never retried. Deterministic, jitter-free
    backoff: sleeps `delays[i]` before attempt i+2. Re-raises the LAST exception once attempts
    are exhausted -- never invents a return value.

    For NON-ORDER read calls ONLY (connect / get_positions / get_account_equity) -- CLAUDE.md
    2026-08-29: "non-order read calls are safe to retry freely." place_bracket's own leg
    placements deliberately do NOT use this wrapper -- see place_bracket's `_place_leg`, which
    adds the duplicate-order confirm-before-retry safety gate this generic wrapper has no
    concept of (retrying an ORDER write risks placing a genuine duplicate if the first attempt
    actually reached the broker and only the response was lost; a read call carries no such
    risk, so it may retry unconditionally)."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 -- classification decides retry, not a blanket catch
            if not _is_transport_error(e) or attempt >= max_attempts:
                raise
            time.sleep(delays[min(attempt - 1, len(delays) - 1)])


# ── State dataclasses (identical to ibkr_paper.py for compatibility) ───────────

@dataclass
class FuturesPosition:
    instrument:      str
    side:            str        # "long" | "short" | "flat"
    qty:             int
    entry_price:     float
    stop_price:      float
    tp1_price:       float
    runner_price:    Optional[float]
    entry_time:      str
    tp1_filled:      bool = False
    runner_order_id: Optional[str] = None
    stop_order_id:   Optional[str] = None

    @classmethod
    def flat(cls, instrument: str = "") -> "FuturesPosition":
        return cls(instrument, "flat", 0, 0.0, 0.0, 0.0, None, "", False)

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument, "side": self.side, "qty": self.qty,
            "entry_price": self.entry_price, "stop_price": self.stop_price,
            "tp1_price": self.tp1_price, "runner_price": self.runner_price,
            "entry_time": self.entry_time, "tp1_filled": self.tp1_filled,
        }

    @classmethod
    def from_file(cls, instrument: str = "") -> "FuturesPosition":
        if POSITION_FILE.exists():
            try:
                d = json.loads(POSITION_FILE.read_text())
                return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls.flat(instrument)

    def save(self):
        POSITION_FILE.write_text(json.dumps(self.to_dict(), indent=2))


@dataclass
class FuturesAccount:
    equity:           float
    day_start_equity: float
    peak_equity:      float
    daily_pnl:        float = 0.0
    daily_loss_limit: float = 500.0
    max_drawdown:     float = 1000.0

    @property
    def floor(self) -> float:
        return max(self.peak_equity - self.max_drawdown,
                   self.day_start_equity - self.daily_loss_limit)

    @property
    def is_blown(self) -> bool:
        return self.equity <= self.floor

    def to_dict(self) -> dict:
        return {
            "equity": self.equity, "day_start_equity": self.day_start_equity,
            "peak_equity": self.peak_equity, "daily_pnl": self.daily_pnl,
            "daily_loss_limit": self.daily_loss_limit,
            "max_drawdown": self.max_drawdown, "floor": self.floor,
        }

    def save(self):
        ACCOUNT_FILE.write_text(json.dumps(self.to_dict(), indent=2))


# ── Broker ─────────────────────────────────────────────────────────────────────

class TastytradeBroker:
    """Tastytrade futures broker adapter — same interface as the retired IBKRBroker.

    Watch-only mode (default): logs would-be orders to JSONL, no network calls.
    Live mode: connects to Tastytrade sandbox via the tastytrade Python SDK (v12+).

    Auth: OAuth2 via TT_SECRET (client_secret) + TT_REFRESH (refresh_token).
    Tokens never expire — set once, work indefinitely.
    """

    def __init__(self, watch_only: bool = WATCH_ONLY):
        self.watch_only = watch_only
        self._session   = None
        self._account   = None
        self._connected = False
        self._sandbox   = os.getenv("TT_SANDBOX", "false").lower() != "false"
        # 2026-08-29 diagnosability fix: structured detail from the LAST place_bracket call,
        # set on every call (None on full success) -- see "Transport diagnosability" above.
        # Callers (e.g. futures_mirror_shadow._broker_execute_entry) read this when the
        # returned id list is empty/short, instead of getting a reasonless [].
        self.last_failure_detail: Optional[dict] = None
        # 2026-09-03 (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL): labeled leg ids from the LAST
        # place_bracket call -- see that method's own comment for why the plain `ids` list
        # returned to callers is not enough on its own.
        self.last_bracket_legs: Optional[dict] = None

    # ── Connection ──────────────────────────────────────────────────────────────

    def connect(self, timeout: float = 10.0) -> bool:
        if self.watch_only:
            self._connected = True
            return True
        try:
            import tastytrade as tt

            # SDK reads TT_SECRET / TT_REFRESH from env by default.
            # Pass explicitly so missing vars surface a clear error here.
            client_secret  = os.environ["TT_SECRET"]
            refresh_token  = os.environ["TT_REFRESH"]
            target_account = os.getenv("TT_ACCOUNT", "")

            async def _conn():
                # timeout= is forwarded to httpx.AsyncClient (Session.__init__'s own docstring:
                # "additional keyword arguments to pass to the httpx AsyncClient, such as
                # timeout") -- httpx's own default is 5.0s (DEFAULT_TIMEOUT_CONFIG,
                # httpx/_config.py) if unset, which this method's `timeout` PARAMETER never
                # actually reached before this fix (dead parameter -- accepted, never used).
                # 2026-08-29: wired through, raising the effective timeout from httpx's 5.0s
                # default to this method's own existing default of 10.0s against a sandbox
                # that has shown 502s / ReadTimeouts under load.
                session  = tt.Session(client_secret, refresh_token, is_test=self._sandbox,
                                      timeout=timeout)
                accounts = await tt.Account.get(session)   # returns list[Account]
                if not accounts:
                    raise RuntimeError("No accounts found on this Tastytrade login")
                if target_account:
                    match = [a for a in accounts if a.account_number == target_account]
                    acct  = match[0] if match else accounts[0]
                else:
                    acct = accounts[0]
                return session, acct

            self._session, self._account = _with_retry(lambda: _run(_conn()))
            self._connected = True
            self.last_failure_detail = None  # clear any stale failure from a prior connect()
            log.info("Tastytrade connected (sandbox=%s) acct=%s",
                     self._sandbox, self._account.account_number)
            return True

        except KeyError as e:
            # 2026-08-30 diagnosability fix: log.error() alone is a dead end under this
            # lane's real deployment shape -- pythonw has no stdout/stderr and nothing in
            # this call chain ever attaches a logging.Handler, so every connect() failure
            # reason was being computed and then discarded (C7: silent success is failure).
            # Mirror the same durable trail place_bracket already uses: last_failure_detail
            # (read by callers) + one row in broker-transport.jsonl (read by
            # futures_health.py's broker_transport check) -- for BOTH the transport-error
            # and the non-transport (auth/config) case, not just the former.
            log.error("Missing env var %s — set TT_SECRET and TT_REFRESH (see file docstring)", e)
            self.last_failure_detail = {
                "call": "connect", "outcome": "missing_env_var",
                "error_class": type(e).__name__, "error_repr": repr(e),
                "detail": f"missing env var {e}",
            }
            _log_broker_transport("connect", "missing_env_var", exc=e,
                                   detail=f"missing env var {e}")
            return False
        except Exception as e:
            log.error("Tastytrade connect failed: %s: %s", type(e).__name__, e)
            outcome = "transport_error" if _is_transport_error(e) else "auth_or_permission_error"
            self.last_failure_detail = {
                "call": "connect", "outcome": outcome,
                "error_class": type(e).__name__, "error_repr": repr(e)[:500],
                "http_status": _extract_http_status(e),
            }
            _log_broker_transport("connect", outcome, exc=e)
            return False

    def disconnect(self):
        self._session   = None
        self._account   = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ── Positions / account ─────────────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        if self.watch_only or not self._connected or not self._account:
            return []
        try:
            async def _get():
                return await self._account.get_positions(self._session)

            positions = _with_retry(lambda: _run(_get()))
            return [
                {
                    "symbol":   p.symbol,
                    "qty":      p.quantity,
                    "avg_cost": float(p.average_open_price or 0),
                }
                for p in positions
                if getattr(p.instrument_type, "value", str(p.instrument_type)).upper()
                   in ("FUTURE", "FUTURES")
            ]
        except Exception as e:
            # 2026-08-21 DIAGNOSABILITY FIX: some SDK/network exceptions (confirmed live in
            # today's sandbox log) have an EMPTY str(e) -- "get_positions failed: " with
            # nothing after the colon. Always include the exception TYPE so a future failure
            # is at least classifiable, even when the message body is blank.
            log.error("get_positions failed: %s: %s", type(e).__name__, e)
            # 2026-08-29: retried transparently above (_with_retry) on a transport failure --
            # reaching here means either a non-transport exception, or retries exhausted. Only
            # the latter is worth a broker-transport.jsonl row (a non-transport failure here,
            # e.g. a parse error, isn't the sandbox-flakiness class this file exists to catch).
            if _is_transport_error(e):
                _log_broker_transport("get_positions", "transport_error", exc=e)
            return []

    def is_flat(self, instrument: str) -> bool:
        """L76 ghost-prevention: verify flat at broker, not just local state."""
        for p in self.get_positions():
            if instrument in p["symbol"] and abs(p["qty"]) > 0:
                return False
        return True

    def get_account_equity(self) -> Optional[float]:
        if self.watch_only or not self._connected or not self._account:
            return None
        try:
            async def _get():
                return await self._account.get_balances(self._session)

            bal = _with_retry(lambda: _run(_get()))
            return float(bal.net_liquidating_value)
        except Exception as e:
            # Same empty-str(e) diagnosability fix as get_positions above.
            log.error("get_account_equity failed: %s: %s", type(e).__name__, e)
            if _is_transport_error(e):
                _log_broker_transport("get_account_equity", "transport_error", exc=e)
            return None

    def get_recent_fills(self, symbol: str, since_et: Optional[dt.datetime] = None,
                         days_back: int = 3) -> list[dict]:
        """READ-ONLY: filled order legs touching `symbol` since `since_et` (or `days_back`).

        Added 2026-09-03 (FUTURES-BROKER-LANE-NEVER-LOGS-EXITS) so the journal writer can
        reconcile what the broker actually did instead of only reacting to fills the engine
        itself was watching for. Never places, cancels, or replaces an order -- `get_order_
        history` is the SDK's own read endpoint (GET /accounts/{id}/orders). Every element of
        every FILLED leg's `fills` list is returned flattened, one dict per fill:
            {order_id, order_type, action ('BUY'/'SELL'), qty, fill_price, filled_at (aware
             UTC datetime), fill_id}
        `fill_price` is None for a MARKET order leg whose own `price` field the SDK leaves
        unset (fill_id/filled_at are always populated for an actual fill) -- callers must not
        assume a market close carries a price here.
        """
        if self.watch_only or not self._connected or not self._account:
            return []
        try:
            start_date = (since_et or (
                dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back))).date()

            async def _get():
                return await self._account.get_order_history(
                    self._session, start_date=start_date, sort="Asc")

            orders = _with_retry(lambda: _run(_get()))
            out: list[dict] = []
            for o in orders:
                status_val = getattr(o.status, "value", str(o.status))
                if status_val.lower() != "filled":
                    continue
                for leg in (o.legs or []):
                    leg_symbol = getattr(leg, "symbol", "") or ""
                    if symbol not in leg_symbol:
                        continue
                    action_val = getattr(leg.action, "value", str(leg.action)).upper()
                    for f in (getattr(leg, "fills", None) or []):
                        ts = getattr(f, "filled_at", None)
                        if since_et is not None and ts is not None:
                            # since_et may be naive (ET) or aware; compare on aware UTC only.
                            cmp_since = since_et if since_et.tzinfo else since_et.replace(
                                tzinfo=dt.timezone.utc)
                            if ts < cmp_since:
                                continue
                        price = getattr(f, "fill_price", None)
                        out.append({
                            "order_id": o.id,
                            "order_type": status_val,
                            "symbol": leg_symbol,
                            "action": action_val,
                            "qty": float(getattr(f, "quantity", 0) or 0),
                            "fill_price": float(price) if price is not None else None,
                            "filled_at": ts.isoformat() if ts is not None else None,
                            "fill_id": getattr(f, "fill_id", None),
                        })
            out.sort(key=lambda r: r["filled_at"] or "")
            return out
        except Exception as e:  # noqa: BLE001 -- a reconciliation read must never break the tick
            log.error("get_recent_fills failed: %s: %s", type(e).__name__, e)
            if _is_transport_error(e):
                _log_broker_transport("get_recent_fills", "transport_error", exc=e)
            return []

    # ── Orders ──────────────────────────────────────────────────────────────────

    def _front_month(self, instrument: str):
        """Return nearest-expiry active Future contract object."""
        from tastytrade.instruments import Future as TTFuture

        async def _get():
            # NOTE: TTFuture.get(session, symbols=...) expects a FULL contract symbol
            # (e.g. "ESZ9"), not a root/product code -- passing "MNQ" 404s as
            # record_not_found. product_codes=[...] is the correct lookup for a root.
            # Confirmed 2026-07-06 via tastytrade_e2e_test.py (never exercised before).
            result    = await TTFuture.get(self._session, product_codes=[instrument])
            contracts = result if isinstance(result, list) else [result]
            active    = [c for c in contracts if not getattr(c, "is_expired", False)]
            if not active:
                raise RuntimeError(f"No active {instrument} contracts on Tastytrade")
            active.sort(key=lambda c: c.expiration_date)
            return active[0]

        return _run(_get())

    def place_bracket(
        self,
        instrument:   str,
        side:         str,        # "BUY" or "SELL"
        qty:          int,
        entry_price:  float,
        tp1_price:    float,
        stop_price:   float,
        runner_price: Optional[float] = None,
        tp1_qty:      Optional[int]   = None,
    ) -> list:
        """Place a bracket order. Returns list of order IDs, or [] on watch-only/error.

        Watch-only: appends record to WOULD_BE_FILE, no network call.
        Live: places entry LIMIT (DAY) + TP1 LIMIT (GTC) + STOP (GTC) as 3 orders.
              Runner TP added as a 4th GTC LIMIT if runner_price is set.

        Futures use OrderAction.BUY / SELL (not BUY_TO_OPEN / SELL_TO_CLOSE).
        Tastytrade has no native OCA bracket — heartbeat manages TP/stop cancellation.
        """
        now_str = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        record  = {
            "time": now_str, "instrument": instrument, "side": side, "qty": qty,
            "entry": entry_price, "tp1": tp1_price, "stop": stop_price,
            "runner": runner_price, "watch_only": self.watch_only,
            "broker": "tastytrade",
        }

        if self.watch_only:
            log.info("WATCH-ONLY bracket: %s", record)
            with open(WOULD_BE_FILE, "a") as f:
                f.write(json.dumps(record) + "\n")
            return []

        if not self.is_connected():
            log.error("place_bracket: not connected")
            return []

        try:
            from tastytrade.order import (
                NewOrder, OrderType, OrderTimeInForce, OrderAction,
            )

            contract = self._front_month(instrument)
            tp1_q    = tp1_qty or max(1, qty // 2)
            run_q    = qty - tp1_q

            # Futures use BUY / SELL (not BUY_TO_OPEN / SELL_TO_CLOSE)
            open_act  = OrderAction.BUY  if side == "BUY" else OrderAction.SELL
            close_act = OrderAction.SELL if side == "BUY" else OrderAction.BUY

            # Tastytrade order.price convention: negative = debit, positive = credit
            # (NewOrder docstring in the SDK's order.py). BUY-to-open / BUY-to-close
            # is always a debit (you pay) -> negative; SELL is always a credit -> positive.
            # Passing an unsigned price here made every BUY-side leg fail live with
            # "cant_buy_for_credit" — confirmed 2026-07-06 via tastytrade_e2e_test.py,
            # never caught before because no order had ever actually been placed.
            def _signed(action, magnitude) -> Decimal:
                mag = Decimal(str(magnitude))
                return -mag if action == OrderAction.BUY else mag

            def _leg_failure_detail(resp) -> str:
                """2026-08-21 DIAGNOSABILITY FIX: the mirror's first-ever real armed order
                attempt today (2026-08-21T11:10 ET, MIRROR_ARMED=1, Tastytrade sandbox)
                returned placed=False, order_ids=[] with ZERO diagnostic trail -- `if r.order`
                silently skipped appending an id and no leg ever logged WHY. Best-effort
                extraction of the SDK response's own error/warning fields so the NEXT attempt
                is classifiable instead of a second silent empty list. Never raises."""
                for attr in ("errors", "error", "warnings"):
                    val = getattr(resp, attr, None)
                    if val:
                        return f"{attr}={val!r}"
                return repr(resp)

            def _leg_already_working_or_filled() -> Optional[bool]:
                """DUPLICATE-ORDER SAFETY (2026-08-29): before retrying ANY leg placement after
                a transport-class failure, confirm the PRIOR attempt did not actually reach the
                broker. A transport failure means we lost the RESPONSE, not necessarily the
                REQUEST -- the order may already be resting (visible in get_live_orders) or
                already filled into the account's position (visible in get_positions). Retrying
                blind risks placing a genuine duplicate order -- for the entry leg specifically
                this would DOUBLE the position size; for an exit leg (tp1/stop/runner) it risks
                two live orders both authorized to close the same qty. Matches this contract's
                symbol only (same loose-match convention as this class's own is_flat()) --
                broad enough to fail closed on ANY doubt.

                Returns:
                  True  -- confirmed a matching working order OR position already exists ->
                           caller must NOT retry (would duplicate).
                  False -- confirmed absent in both live orders and positions -> safe to retry.
                  None  -- the confirmation query itself failed (broker unreachable again right
                           now, same as the failure being investigated) -> INCONCLUSIVE. Treated
                           by the caller as "do NOT retry" -- a duplicate live order is a
                           strictly worse outcome than abandoning one diagnostic retry, so this
                           check fails CLOSED on any doubt, unlike the rest of this file's
                           fail-OPEN logging/diagnostics (CLAUDE.md C11: broker is source of
                           truth; verify flat before entry)."""
                try:
                    symbol = getattr(contract, "symbol", None)

                    async def _check():
                        orders = await self._account.get_live_orders(self._session)
                        positions = await self._account.get_positions(self._session)
                        return orders, positions

                    orders, positions = _run(_check())
                    for o in orders:
                        for leg in (getattr(o, "legs", None) or []):
                            leg_symbol = getattr(leg, "symbol", "") or ""
                            if symbol and symbol in leg_symbol:
                                return True
                    for p in positions:
                        p_symbol = getattr(p, "symbol", "") or ""
                        p_qty = getattr(p, "quantity", 0) or 0
                        if symbol and symbol in p_symbol and abs(p_qty) > 0:
                            return True
                    return False
                except Exception:  # noqa: BLE001 -- inconclusive, not a crash
                    return None

            def _place_leg(build_coro, *, call_name: str) -> Optional[str]:
                """Places ONE bracket leg with transport-retry + duplicate-order safety.
                Returns the placed order id, or None if the leg was abandoned (a clean
                rejection, a transport failure that exhausted retries, or the ambiguous-
                landed-state guard). EVERY non-success path is journaled to
                broker-transport.jsonl so an empty order_ids=[] is never reasonless again
                (2026-08-29 diagnosability fix -- see module-level "Transport diagnosability").
                Max 3 total attempts (see _RETRY_DELAYS_SEC) -- deliberately NOT using the
                generic _with_retry helper, because an order WRITE needs the confirm-before-
                retry safety check that helper intentionally omits (see its own docstring)."""
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        resp = _run(build_coro())
                    except Exception as e:  # noqa: BLE001
                        if not _is_transport_error(e):
                            # Not a network blip -- e.g. a pydantic validation error building
                            # the request itself. Never reached the broker at all; retrying an
                            # identical malformed request would just fail identically forever.
                            _log_broker_transport(call_name, "leg_rejected", exc=e,
                                                  detail="exception_before_response")
                            log.warning("%s leg raised non-transport exception: %s: %s",
                                       call_name, type(e).__name__, e)
                            return None
                        if attempt >= 3:
                            _log_broker_transport(call_name, "transport_error", exc=e)
                            log.warning("%s leg exhausted %d transport retries: %s: %s",
                                       call_name, attempt, type(e).__name__, e)
                            return None
                        landed = _leg_already_working_or_filled()
                        if landed is not False:   # True (confirmed landed) OR None (ambiguous)
                            _log_broker_transport(
                                call_name, "transport_error_not_retried_ambiguous", exc=e,
                                detail=("confirmed_order_already_landed" if landed is True
                                       else "confirmation_query_itself_failed"))
                            log.warning("%s leg transport failure NOT retried (landed=%s, "
                                       "duplicate-order risk): %s: %s",
                                       call_name, landed, type(e).__name__, e)
                            return None
                        time.sleep(_RETRY_DELAYS_SEC[min(attempt - 1, len(_RETRY_DELAYS_SEC) - 1)])
                        continue
                    if resp.order:
                        return resp.order.id
                    detail = _leg_failure_detail(resp)
                    _log_broker_transport(call_name, "leg_rejected", detail=detail)
                    log.warning("%s leg rejected, no order id: %s", call_name, detail)
                    return None

            ids: list = []
            leg_failures: list = []

            # 1. Entry LIMIT (DAY) — full qty
            async def _entry_coro():
                return await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.DAY,
                        order_type=OrderType.LIMIT,
                        legs=[contract.build_leg(qty, open_act)],
                        price=_signed(open_act, entry_price),
                    ),
                    dry_run=False,
                )
            entry_id = _place_leg(_entry_coro, call_name="place_bracket_entry")
            if entry_id:
                ids.append(entry_id)
            else:
                leg_failures.append("place_bracket_entry")

            # 2. TP1 exit LIMIT (GTC) — tp1_q contracts
            async def _tp1_coro():
                return await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.GTC,
                        order_type=OrderType.LIMIT,
                        legs=[contract.build_leg(tp1_q, close_act)],
                        price=_signed(close_act, tp1_price),
                    ),
                    dry_run=False,
                )
            tp1_id = _place_leg(_tp1_coro, call_name="tp1")
            if tp1_id:
                ids.append(tp1_id)
            else:
                leg_failures.append("tp1")

            # 3. Stop STOP (GTC) — full qty; heartbeat trims to runner qty after TP1 fills
            async def _stop_coro():
                return await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.GTC,
                        order_type=OrderType.STOP,
                        legs=[contract.build_leg(qty, close_act)],
                        stop_trigger=Decimal(str(stop_price)),
                    ),
                    dry_run=False,
                )
            stop_id = _place_leg(_stop_coro, call_name="stop")
            if stop_id:
                ids.append(stop_id)
            else:
                leg_failures.append("stop")

            # 4. Runner TP LIMIT (GTC) — optional
            runner_id = None  # stays None unless the branch below actually places it
            if runner_price and run_q > 0:
                async def _runner_coro():
                    return await self._account.place_order(
                        self._session,
                        NewOrder(
                            time_in_force=OrderTimeInForce.GTC,
                            order_type=OrderType.LIMIT,
                            legs=[contract.build_leg(run_q, close_act)],
                            price=_signed(close_act, runner_price),
                        ),
                        dry_run=False,
                    )
                runner_id = _place_leg(_runner_coro, call_name="runner")
                if runner_id:
                    ids.append(runner_id)
                else:
                    leg_failures.append("runner")

            log.info("Bracket placed %s %s %d @ %.2f TP=%.2f ST=%.2f IDs=%s",
                     side, instrument, qty, entry_price, tp1_price, stop_price, ids)
            # 2026-08-29: structured, instance-level failure detail -- see __init__ and module
            # docstring "Transport diagnosability". None on a fully clean bracket; otherwise a
            # summary a caller (e.g. futures_mirror_shadow._broker_execute_entry) can read
            # without cross-referencing broker-transport.jsonl by hand.
            self.last_failure_detail = (
                {"instrument": instrument, "placed_ids": list(ids), "leg_failures": leg_failures}
                if leg_failures else None)
            # 2026-09-03 (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL): `ids` is a flat, order-of-
            # attempt list that collapses to ambiguous positions the moment any leg fails to
            # place -- a caller cannot reliably tell "this id is the stop leg" from it alone.
            # This labeled map is what the sibling-cancel safety net (no native OCO wired --
            # see this method's own docstring above) reads to find "the OTHER leg" once one
            # fills. None for any leg that was never placed/failed -- never guessed.
            self.last_bracket_legs = {
                "entry": entry_id, "tp1": tp1_id, "stop": stop_id, "runner": runner_id,
            }
            return ids

        except Exception as e:
            log.error("place_bracket failed: %s: %s", type(e).__name__, e)
            self.last_failure_detail = {
                "call": "place_bracket", "error_class": type(e).__name__,
                "error_repr": repr(e)[:500],
            }
            # A failed attempt's leg ids belong to nothing this caller can act on -- never
            # leave a PRIOR successful call's map looking current for this one.
            self.last_bracket_legs = None
            _log_broker_transport(
                "place_bracket", "transport_error" if _is_transport_error(e) else "leg_rejected",
                exc=e, detail="exception_before_any_leg_attempted")
            return []

    def cancel_all(self, instrument: str) -> bool:
        """Cancel all open orders for instrument (EOD flatten step 1)."""
        if self.watch_only:
            log.info("WATCH-ONLY cancel_all %s", instrument)
            return True
        if not self.is_connected():
            return False
        try:
            async def _cancel():
                orders = await self._account.get_live_orders(self._session)
                n = 0
                for order in orders:
                    for leg in (order.legs or []):
                        # leg.symbol is full contract e.g. "MNQU6" — match by product code
                        if instrument in (leg.symbol or ""):
                            await self._account.delete_order(self._session, order.id)
                            n += 1
                            break
                return n

            n = _run(_cancel())
            log.info("cancel_all %s: %d orders cancelled", instrument, n)
            return True
        except Exception as e:
            log.error("cancel_all failed: %s", e)
            return False

    def cancel_order(self, order_id) -> bool:
        """Cancel ONE order by id (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL, 2026-09-03).

        The sibling-cancel safety net: Tastytrade's REST order-write endpoint (`NewOrder` /
        `Account.place_order`) has no native OCA bracket for a futures leg pair -- TP1 and
        stop are two independent GTC orders (see `place_bracket`'s own docstring) -- so the
        moment one fills, the caller (`futures_broker_reconciler.reconcile_broker_exits`)
        cancels the other via this method instead of waiting for it to also fill and reopen
        a stray position (the exact 8-anomaly pattern this fix responds to, 09-01/09-02).

        Kill-type by construction: a cancel can only REDUCE working exposure, never add any.
        True on a clean cancel OR watch-only (nothing to cancel); False on any broker error
        (already-filled/already-cancelled included -- the caller must not assume the order
        is still live either way, only that this call did not confirm a fresh cancel)."""
        if self.watch_only:
            log.info("WATCH-ONLY cancel_order %s", order_id)
            return True
        if not self.is_connected():
            return False
        try:
            async def _cancel():
                await self._account.delete_order(self._session, order_id)

            _run(_cancel())
            log.info("cancel_order %s: cancelled", order_id)
            return True
        except Exception as e:
            log.error("cancel_order %s failed: %s: %s", order_id, type(e).__name__, e)
            if _is_transport_error(e):
                _log_broker_transport("cancel_order", "transport_error", exc=e)
            return False

    def get_working_orders(self, instrument: str) -> list[dict]:
        """READ-ONLY: currently LIVE (open/resting) orders touching `instrument`.

        Added for the flatten-cancel-confirm sweep (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL,
        2026-09-03): `cancel_all()` submits cancel requests but never confirmed they actually
        cleared before the old FLATTEN path went straight to `close_position()` -- a resting
        leg that survived the cancel (or was never cancelled, since cancel_all was never even
        called from that path) could still fill after the flatten. This is the read side of
        that confirmation. Never places, cancels, or replaces anything -- same read-only
        contract as `get_recent_fills`/`get_positions`. [] on watch-only, not-connected, or
        any read failure (fail-open on the READ; the caller's own bounded poll + loud
        anomaly log is what handles an unconfirmable sweep, not this method pretending)."""
        if self.watch_only or not self._connected or not self._account:
            return []
        try:
            async def _get():
                return await self._account.get_live_orders(self._session)

            orders = _with_retry(lambda: _run(_get()))
            out: list[dict] = []
            for o in orders:
                for leg in (o.legs or []):
                    leg_symbol = getattr(leg, "symbol", "") or ""
                    if instrument in leg_symbol:
                        out.append({
                            "order_id": o.id, "symbol": leg_symbol,
                            "status": getattr(o.status, "value", str(o.status)),
                        })
                        break
            return out
        except Exception as e:
            log.error("get_working_orders failed: %s: %s", type(e).__name__, e)
            if _is_transport_error(e):
                _log_broker_transport("get_working_orders", "transport_error", exc=e)
            return []

    def close_position(self, instrument: str, qty: int, side: str, price: float) -> bool:
        """Market-close an open position (EOD flatten step 2)."""
        if self.watch_only:
            log.info("WATCH-ONLY close_position %s qty=%d", instrument, qty)
            return True
        if not self.is_connected():
            return False
        try:
            from tastytrade.order import NewOrder, OrderType, OrderTimeInForce, OrderAction

            # Futures use BUY / SELL (not BUY_TO_CLOSE / SELL_TO_CLOSE)
            close_act = OrderAction.SELL if side == "BUY" else OrderAction.BUY
            contract  = self._front_month(instrument)

            async def _close():
                r = await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.DAY,
                        order_type=OrderType.MARKET,
                        legs=[contract.build_leg(qty, close_act)],
                    ),
                    dry_run=False,
                )
                return r.order is not None

            ok = _run(_close())
            log.info("close_position %s qty=%d: %s", instrument, qty, "OK" if ok else "FAILED")
            return ok
        except Exception as e:
            log.error("close_position failed: %s", e)
            return False
