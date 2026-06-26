"""IBKR paper-trading connector for the Futures Edition.

Wraps ib_async for MNQ/MES bracket orders. Designed for the futures heartbeat:
- Connect to IB Gateway headless (Docker) on port 4002
- Place bracket orders (entry + TP1 + stop)
- Track fills via event callbacks
- Flat-verification gate (L76: ghost prevention)
- PropAccount kill-switch check before every entry

Setup (one-time, manual):
  1. Create IBKR account at ibkr.com (Lite = free, no min deposit)
  2. Enable paper trading account in portal
  3. docker run -d --name ib-gateway -p 4002:4002 \
       -e TRADING_MODE=paper \
       -e TWS_USERID=<ibkr_username> -e TWS_PASSWORD=<ibkr_password> \
       ghcr.io/gnzsnz/ib-gateway:latest
  4. pip install ib_async

Usage:
  broker = IBKRBroker()
  if broker.connect():
      positions = broker.get_positions()
      order_ids = broker.place_bracket("MNQ", "BUY", 3, 21400, tp1=21450, stop=21370)
      broker.disconnect()

WATCH-ONLY mode: set WATCH_ONLY=True; place_bracket logs but does not submit.
"""
from __future__ import annotations
import datetime as dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── State paths ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent.parent
STATE_DIR = REPO / "automation" / "state" / "futures"
STATE_DIR.mkdir(parents=True, exist_ok=True)

POSITION_FILE = STATE_DIR / "position.json"
ACCOUNT_FILE  = STATE_DIR / "account.json"
WOULD_BE_FILE = STATE_DIR / "would-be-trades.jsonl"

# ── Config ─────────────────────────────────────────────────────────────────────
IBKR_HOST = "127.0.0.1"
IBKR_PORT = 4002          # paper account
IBKR_CLIENT_ID = 10       # futures heartbeat client

# Front-month symbol by instrument (update on roll dates — quarterly H/M/U/Z)
# Roll schedule: H=Mar(~mid-Mar), M=Jun(~mid-Jun), U=Sep(~mid-Sep), Z=Dec(~mid-Dec)
# Current: U2026 (Sep 2026). Update to Z2026 around 2026-09-12 (third Friday of Sep).
FRONT_MONTH = {
    "MNQ": "MNQU2026",   # Sep 2026 — update to Z2026 after 2026-09-12
    "MES": "MESU2026",
    "NQ":  "NQU2026",
    "ES":  "ESU2026",
}

WATCH_ONLY = True  # Set False to enable live paper order submission


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class FuturesPosition:
    instrument: str
    side: str           # "long" | "short" | "flat"
    qty: int
    entry_price: float
    stop_price: float
    tp1_price: float
    runner_price: Optional[float]
    entry_time: str
    tp1_filled: bool = False
    runner_order_id: Optional[str] = None
    stop_order_id: Optional[str] = None

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
    equity: float
    day_start_equity: float
    peak_equity: float
    daily_pnl: float = 0.0
    daily_loss_limit: float = 500.0   # $500 daily hard stop for paper
    max_drawdown: float = 1000.0      # $1K trailing floor for paper

    @property
    def floor(self) -> float:
        return max(self.peak_equity - self.max_drawdown,
                   self.day_start_equity - self.daily_loss_limit)

    @property
    def is_blown(self) -> bool:
        return self.equity <= self.floor

    def to_dict(self) -> dict:
        return {"equity": self.equity, "day_start_equity": self.day_start_equity,
                "peak_equity": self.peak_equity, "daily_pnl": self.daily_pnl,
                "daily_loss_limit": self.daily_loss_limit, "max_drawdown": self.max_drawdown,
                "floor": self.floor}

    def save(self):
        ACCOUNT_FILE.write_text(json.dumps(self.to_dict(), indent=2))


# ── IBKR broker class ──────────────────────────────────────────────────────────

class IBKRBroker:
    """Thin wrapper around ib_async for the futures heartbeat."""

    def __init__(self, host: str = IBKR_HOST, port: int = IBKR_PORT,
                 client_id: int = IBKR_CLIENT_ID, watch_only: bool = WATCH_ONLY):
        self._host = host
        self._port = port
        self._client_id = client_id
        self.watch_only = watch_only
        self._ib = None
        self._connected = False

    def connect(self, timeout: float = 10.0) -> bool:
        try:
            import ib_async as iba
            self._ib = iba.IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id,
                             timeout=timeout, readonly=False)
            self._connected = True
            log.info("IBKR connected port=%d client=%d", self._port, self._client_id)
            return True
        except Exception as e:
            log.error("IBKR connect failed: %s", e)
            self._connected = False
            return False

    def disconnect(self):
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._ib is not None and self._ib.isConnected()

    def get_positions(self) -> list[dict]:
        """Return live positions from IBKR (flat-verification gate, L76)."""
        if not self.is_connected():
            return []
        try:
            positions = self._ib.positions()
            return [{"symbol": p.contract.symbol,
                     "qty": p.position,
                     "avg_cost": p.avgCost} for p in positions]
        except Exception as e:
            log.error("get_positions failed: %s", e)
            return []

    def is_flat(self, instrument: str) -> bool:
        """Verify we are truly flat in IBKR (not just locally assumed). L76 guard."""
        positions = self.get_positions()
        for p in positions:
            if instrument in p["symbol"] and abs(p["qty"]) > 0:
                return False
        return True

    def get_account_equity(self) -> Optional[float]:
        if not self.is_connected():
            return None
        try:
            vals = self._ib.accountValues()
            for v in vals:
                if v.tag == "NetLiquidation" and v.currency == "USD":
                    return float(v.value)
            return None
        except Exception:
            return None

    def _make_contract(self, instrument: str):
        import ib_async as iba
        symbol = FRONT_MONTH.get(instrument, instrument + "U2026")
        exchange = "CME"
        # Parse expiry from symbol (e.g. MNQU2026 -> 202609)
        roll_map = {"H": "03", "M": "06", "U": "09", "Z": "12"}
        month_code = symbol[-5]  # e.g. 'U'
        year = symbol[-4:]       # e.g. '2026'
        expiry = f"{year}{roll_map.get(month_code, '09')}"
        contract = iba.Future(symbol[:len(symbol)-5], expiry, exchange,
                              multiplier=str({"MNQ": 2, "MES": 5, "NQ": 20, "ES": 50}.get(instrument, 2)))
        return contract

    def place_bracket(
        self,
        instrument: str,
        side: str,          # "BUY" or "SELL"
        qty: int,
        entry_price: float,
        tp1_price: float,
        stop_price: float,
        runner_price: Optional[float] = None,
        tp1_qty: Optional[int] = None,
    ) -> list[int]:
        """Place a bracket order. Returns list of order IDs, or [] on watch-only / error.

        L76 guard: caller must call is_flat() before this.
        """
        now_str = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        record = {
            "time": now_str, "instrument": instrument, "side": side, "qty": qty,
            "entry": entry_price, "tp1": tp1_price, "stop": stop_price,
            "runner": runner_price, "watch_only": self.watch_only,
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
            import ib_async as iba
            contract = self._make_contract(instrument)
            self._ib.qualifyContracts(contract)

            tp1_q  = tp1_qty or max(1, qty // 2)
            run_q  = qty - tp1_q

            orders = []

            # TP1 bracket (tp1_q contracts)
            if tp1_q > 0:
                tp1_bracket = self._ib.bracketOrder(
                    side, tp1_q,
                    limitPrice=entry_price,
                    takeProfitPrice=tp1_price,
                    stopLossPrice=stop_price,
                )
                for o in tp1_bracket:
                    trade = self._ib.placeOrder(contract, o)
                    orders.append(trade.order.orderId)

            # Runner bracket (if any)
            if run_q > 0 and runner_price is not None:
                run_bracket = self._ib.bracketOrder(
                    side, run_q,
                    limitPrice=entry_price,
                    takeProfitPrice=runner_price,
                    stopLossPrice=stop_price,
                )
                for o in run_bracket:
                    trade = self._ib.placeOrder(contract, o)
                    orders.append(trade.order.orderId)

            log.info("Placed bracket %s %s %d @ %s TP=%s ST=%s IDs=%s",
                     side, instrument, qty, entry_price, tp1_price, stop_price, orders)
            return orders

        except Exception as e:
            log.error("place_bracket failed: %s", e)
            return []

    def cancel_all(self, instrument: str) -> bool:
        """Cancel all open orders for instrument (EOD flatten)."""
        if self.watch_only:
            log.info("WATCH-ONLY cancel_all %s", instrument)
            return True
        if not self.is_connected():
            return False
        try:
            orders = self._ib.openOrders()
            for o in orders:
                if hasattr(o, "contract") and instrument in o.contract.symbol:
                    self._ib.cancelOrder(o)
            return True
        except Exception as e:
            log.error("cancel_all failed: %s", e)
            return False

    def close_position(self, instrument: str, qty: int, side: str, price: float) -> bool:
        """Market-close an open position (EOD flatten). Side = existing side to close."""
        if self.watch_only:
            log.info("WATCH-ONLY close %s qty=%d", instrument, qty)
            return True
        if not self.is_connected():
            return False
        try:
            import ib_async as iba
            contract = self._make_contract(instrument)
            self._ib.qualifyContracts(contract)
            close_side = "SELL" if side == "BUY" else "BUY"
            order = iba.MarketOrder(close_side, qty)
            trade = self._ib.placeOrder(contract, order)
            log.info("EOD close %s %s %d: %s", close_side, instrument, qty, trade)
            return True
        except Exception as e:
            log.error("close_position failed: %s", e)
            return False
