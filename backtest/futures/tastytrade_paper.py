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

WATCH_ONLY  = True  # SAFETY (2026-06-21 readiness audit): the futures engine is an
# unbuilt stub (broken VIX read, unwired levels, no watcher integration) and all 3
# Gamma_Futures* tasks are DISABLED. Shipping WATCH_ONLY=False with a live place_bracket()
# path was a loaded gun (.env.tastytrade also carries live-PROD OAuth tokens). WATCH_ONLY
# stays True until the engine is real AND J explicitly flips it. Do NOT set False while
# TT_PROD_* tokens exist in .env.tastytrade. (Token rotation is a separate J action.)
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
                session  = tt.Session(client_secret, refresh_token, is_test=self._sandbox)
                accounts = await tt.Account.get(session)   # returns list[Account]
                if not accounts:
                    raise RuntimeError("No accounts found on this Tastytrade login")
                if target_account:
                    match = [a for a in accounts if a.account_number == target_account]
                    acct  = match[0] if match else accounts[0]
                else:
                    acct = accounts[0]
                return session, acct

            self._session, self._account = _run(_conn())
            self._connected = True
            log.info("Tastytrade connected (sandbox=%s) acct=%s",
                     self._sandbox, self._account.account_number)
            return True

        except KeyError as e:
            log.error("Missing env var %s — set TT_SECRET and TT_REFRESH (see file docstring)", e)
            return False
        except Exception as e:
            log.error("Tastytrade connect failed: %s", e)
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

            return [
                {
                    "symbol":   p.symbol,
                    "qty":      p.quantity,
                    "avg_cost": float(p.average_open_price or 0),
                }
                for p in _run(_get())
                if getattr(p.instrument_type, "value", str(p.instrument_type)).upper()
                   in ("FUTURE", "FUTURES")
            ]
        except Exception as e:
            log.error("get_positions failed: %s", e)
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

            bal = _run(_get())
            return float(bal.net_liquidating_value)
        except Exception as e:
            log.error("get_account_equity failed: %s", e)
            return None

    # ── Orders ──────────────────────────────────────────────────────────────────

    def _front_month(self, instrument: str):
        """Return nearest-expiry active Future contract object."""
        from tastytrade.instruments import Future as TTFuture

        async def _get():
            result    = await TTFuture.get(self._session, instrument)
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

            async def _place():
                ids = []

                # 1. Entry LIMIT (DAY) — full qty
                r = await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.DAY,
                        order_type=OrderType.LIMIT,
                        legs=[contract.build_leg(qty, open_act)],
                        price=Decimal(str(entry_price)),
                    ),
                    dry_run=False,
                )
                if r.order:
                    ids.append(r.order.id)

                # 2. TP1 exit LIMIT (GTC) — tp1_q contracts
                r = await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.GTC,
                        order_type=OrderType.LIMIT,
                        legs=[contract.build_leg(tp1_q, close_act)],
                        price=Decimal(str(tp1_price)),
                    ),
                    dry_run=False,
                )
                if r.order:
                    ids.append(r.order.id)

                # 3. Stop STOP (GTC) — full qty; heartbeat trims to runner qty after TP1 fills
                r = await self._account.place_order(
                    self._session,
                    NewOrder(
                        time_in_force=OrderTimeInForce.GTC,
                        order_type=OrderType.STOP,
                        legs=[contract.build_leg(qty, close_act)],
                        stop_trigger=Decimal(str(stop_price)),
                    ),
                    dry_run=False,
                )
                if r.order:
                    ids.append(r.order.id)

                # 4. Runner TP LIMIT (GTC) — optional
                if runner_price and run_q > 0:
                    r = await self._account.place_order(
                        self._session,
                        NewOrder(
                            time_in_force=OrderTimeInForce.GTC,
                            order_type=OrderType.LIMIT,
                            legs=[contract.build_leg(run_q, close_act)],
                            price=Decimal(str(runner_price)),
                        ),
                        dry_run=False,
                    )
                    if r.order:
                        ids.append(r.order.id)

                return ids

            ids = _run(_place())
            log.info("Bracket placed %s %s %d @ %.2f TP=%.2f ST=%.2f IDs=%s",
                     side, instrument, qty, entry_price, tp1_price, stop_price, ids)
            return ids

        except Exception as e:
            log.error("place_bracket failed: %s", e)
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
