"""fill_sim_broker.py -- the OWN-FILL-SIM broker for the futures swing PAPER lane.

WHY THIS EXISTS (2026-07-09, FUTURES-REVIVAL-PLAN-2026-07-02.md sec 1.3 / 2d / 5#3):
tastytrade's cert (sandbox) account cannot hold a multiday position -- it resets every 24h
and the account itself reports `futures_approved=False` (order placement UNVERIFIED). The
plan's own fallback (sec 1.3, sec 2d, open question #3 "plan default: own fill-sim lane
first -- it's the only one that needs nothing from anyone") is an OWN FILL-SIM lane:
simulate fills against LIVE quotes, persist positions ACROSS DAYS / PROCESS RESTARTS,
journal every would-be trade -- so a swing engine can paper-trade autonomously with zero
dependency on the tastytrade SDK install, cert quirks, or the outstanding token rotation.

INTERFACE CONTRACT -- drop-in for futures_heartbeat_core.py's TastytradeBroker duck-type
(see tastytrade_paper.py): connect / get_positions / is_flat / get_account_equity /
place_bracket / cancel_all / close_position. See setup/scripts/swing_core_runner.py's module
docstring for the THREE places this is NOT a blind drop-in (state-dir collision, the
tastytrade-SDK-shaped provisioning gate, and futures_exit_manager's intraday time-stop) --
swing_core_runner.py works around each; none of the three change this file's public surface.

FILL SEMANTICS (task spec, matches the plan's swing_sim.py gap-fill convention verbatim --
"gaps fill at the open beyond the stop, never at the stop", plan sec 2f):
  - Entry LIMIT: fills the FIRST time a subsequent quote/bar touches the limit price. Fills
    AT the limit (no slippage modeled for entries -- standard backtest-sim convention, matches
    futures_sim.simulate_futures' own touch-fill treatment of targets).
  - TP1 / runner target: same touch-at-level convention as entries.
  - STOP (FULL_STOP / RUNNER_BE_STOP): fills AT the stop price on a normal in-bar touch. On a
    GAP (the checked bar's OPEN is already beyond the stop -- price jumped the level between
    checks with no intervening trade AT the stop) fills AT THE OPEN instead, which is by
    construction WORSE than the stop. Never fills AT the stop price during a genuine gap.
  - "GTC" persistence: fillsim-positions.json IS the resting order. process_quote() is the
    fill engine a real exchange would run server-side; state survives a process restart
    because every write is atomic (temp file + os.replace) and every read is a fresh file
    parse (no in-memory cache to go stale).

Positions are keyed by instrument symbol in ONE file (fillsim-positions.json) so MNQ + MES
can be open simultaneously without collision. would-be-trades.jsonl gets one row per
lifecycle event using this vocabulary: placed (order placed) / filled (entry limit touched)
/ tp1 (partial scale-out) / stop (FULL_STOP or break-even RUNNER_BE_STOP) / closed
(RUNNER_TARGET or a forced close). Every timestamp is ET via et_clock.et_now() -- NEVER a
a naive local-clock read (this rig runs Mountain time; CLAUDE.md TZ-systemic scar).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures.instruments import get as get_instrument  # noqa: E402
from futures.futures_exit_manager import (  # noqa: E402
    FuturesExitState, decide_exit, HOLD, FULL_STOP, TP1_PARTIAL, RUNNER_TARGET, RUNNER_BE_STOP,
    TIME_STOP,
)


def _et_now() -> dt.datetime:
    """ET wall-clock via the repo's DST-aware clock (never a naive local-clock read -- this
    box runs Mountain time, ET = local + 2h; see setup/scripts/et_clock.py + CLAUDE.md)."""
    _scripts = str(REPO / "setup" / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from et_clock import et_now  # noqa: PLC0415
    return et_now()


STATE_DIR = REPO / "automation" / "state" / "futures"
RISK_FILE = STATE_DIR / "risk.json"
DEFAULT_START_EQUITY = 2000.0  # matches automation/state/futures/risk.json daily_start_equity

# Lifecycle event vocabulary (would-be-trades.jsonl "event" field) -- task spec verbatim.
EV_PLACED = "placed"
EV_FILLED = "filled"
EV_TP1 = "tp1"
EV_STOP = "stop"
EV_CLOSED = "closed"

# decide_exit() action code -> would-be-trades.jsonl event name.
_ACTION_TO_EVENT = {
    TP1_PARTIAL: EV_TP1,
    FULL_STOP: EV_STOP,
    RUNNER_BE_STOP: EV_STOP,
    RUNNER_TARGET: EV_CLOSED,
    TIME_STOP: EV_CLOSED,
}


def _atomic_write_json(path: Path, data: dict) -> None:
    """Temp file + os.replace -- atomic on both Windows and POSIX (task requirement)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _order_id(instrument: str, tag: str) -> str:
    return f"FILLSIM-{instrument}-{tag}-{uuid.uuid4().hex[:8]}"


def gap_aware_stop_fill(direction: str, stop_price: float, price: float,
                        bar_open: Optional[float]) -> float:
    """Gap-aware stop fill (task requirement + FUTURES-REVIVAL-PLAN sec 2f convention: "gaps
    fill at the open beyond the stop, never at the stop"). A normal in-bar touch fills AT the
    stop; a GAP (bar_open already beyond the stop -- price jumped the level with no
    intervening trade AT it) fills AT THE OPEN, which is by construction WORSE than the stop.
    Module-level + pure so it is trivially unit-testable without a broker instance."""
    o = bar_open if bar_open is not None else price
    if direction == "long":
        return o if o < stop_price else stop_price
    return o if o > stop_price else stop_price


class FillSimBroker:
    """Own-fill-sim paper broker -- drop-in for TastytradeBroker's duck-typed interface.

    Every instance is scoped to a `state_dir` (default automation/state/futures/) so tests
    can point it at a tmp_path and never touch real state. `watch_only = False` always: this
    broker's entire purpose is to FILL (simulate) orders, unlike tastytrade_paper.py's
    watch_only mode which only LOGS a would-be order without any fill mechanics.
    """

    watch_only = False

    def __init__(self, *, state_dir: Optional[Path] = None,
                start_equity: Optional[float] = None) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else STATE_DIR
        self.account_file = self.state_dir / "fillsim-account.json"
        self.positions_file = self.state_dir / "fillsim-positions.json"
        self.would_be_file = self.state_dir / "would-be-trades.jsonl"
        self._connected = False
        self._start_equity_override = start_equity
        self._ensure_account()

    # ── connection (no real network -- always ready) ──────────────────────────
    def connect(self, timeout: float = 10.0) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ── account ─────────────────────────────────────────────────────────────
    def _seed_account(self) -> dict:
        start = self._start_equity_override
        floor = None
        daily_loss_limit = None
        if start is None:
            try:
                risk = json.loads(RISK_FILE.read_text(encoding="utf-8"))
                start = float(risk.get("daily_start_equity", DEFAULT_START_EQUITY))
                floor = float(risk.get("floor", start * 0.8))
                daily_loss_limit = float(risk.get("daily_loss_limit", 200.0))
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                start = DEFAULT_START_EQUITY
        start = float(start if start is not None else DEFAULT_START_EQUITY)
        floor = float(floor if floor is not None else start * 0.8)
        daily_loss_limit = float(daily_loss_limit if daily_loss_limit is not None else 200.0)
        now = _et_now()
        return {
            "account_type": "fill_sim_paper",
            "starting_equity": start, "equity": start, "peak_equity": start,
            "day_start_equity": start, "daily_pnl": 0.0, "realized_pnl_total": 0.0,
            "daily_loss_limit": daily_loss_limit, "floor": floor,
            "trade_count": 0,
            "last_reset_date_et": now.strftime("%Y-%m-%d"),
            "last_updated_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _ensure_account(self) -> None:
        if not self.account_file.exists():
            _atomic_write_json(self.account_file, self._seed_account())

    def _load_account(self) -> dict:
        try:
            return json.loads(self.account_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            acct = self._seed_account()
            _atomic_write_json(self.account_file, acct)
            return acct

    def _save_account(self, acct: dict) -> None:
        _atomic_write_json(self.account_file, acct)

    def _roll_day_if_needed(self, acct: dict) -> dict:
        today = _et_now().strftime("%Y-%m-%d")
        if acct.get("last_reset_date_et") != today:
            acct = dict(acct)
            acct["day_start_equity"] = acct["equity"]
            acct["daily_pnl"] = 0.0
            acct["last_reset_date_et"] = today
        return acct

    def _apply_realized_pnl(self, pnl: float) -> dict:
        acct = self._roll_day_if_needed(self._load_account())
        acct = dict(acct)
        acct["equity"] = float(acct["equity"]) + pnl
        acct["daily_pnl"] = float(acct["daily_pnl"]) + pnl
        acct["realized_pnl_total"] = float(acct["realized_pnl_total"]) + pnl
        acct["peak_equity"] = max(float(acct["peak_equity"]), acct["equity"])
        acct["trade_count"] = int(acct["trade_count"]) + 1
        acct["last_updated_et"] = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
        self._save_account(acct)
        return acct

    def get_account_equity(self) -> Optional[float]:
        """Realized equity only -- no mark-to-market. get_account_equity() takes no live-price
        argument (matching TastytradeBroker's exact signature), so unrealized P&L on an open
        position is NOT reflected here; a documented, deliberate simplification."""
        try:
            return float(self._load_account()["equity"])
        except Exception:  # noqa: BLE001
            return None

    def get_account_snapshot(self) -> dict:
        """Public read of the full account ledger (equity, floor, daily_pnl, trade_count,
        etc.) -- for callers that need more than get_account_equity()'s single float."""
        return self._load_account()

    # ── positions ───────────────────────────────────────────────────────────
    def _load_all_positions(self) -> dict:
        try:
            return json.loads(self.positions_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_all_positions(self, data: dict) -> None:
        _atomic_write_json(self.positions_file, data)

    def get_positions_snapshot(self) -> dict:
        """Public read of the RAW positions dict (keyed by instrument; includes both
        pending_entry and open) -- unlike get_positions() which is OPEN-only, in the
        TastytradeBroker return shape."""
        return self._load_all_positions()

    def get_positions(self) -> list[dict]:
        """OPEN (filled) positions only -- a resting pending-entry limit is a working ORDER,
        not a position yet (matches real-broker semantics; see TastytradeBroker.get_positions,
        which only ever sees FILLED broker positions)."""
        out = []
        for sym, p in self._load_all_positions().items():
            if p and p.get("status") == "open" and int(p.get("qty_open", 0)) > 0:
                signed_qty = p["qty_open"] if p["direction"] == "long" else -p["qty_open"]
                out.append({"symbol": sym, "qty": signed_qty, "avg_cost": p["entry"]})
        return out

    def is_flat(self, instrument: str) -> bool:
        """L76-style ghost-prevention: verify flat from PERSISTED state, not caller memory."""
        p = self._load_all_positions().get(instrument)
        return not (p and p.get("status") == "open" and int(p.get("qty_open", 0)) > 0)

    # ── orders: entry ───────────────────────────────────────────────────────
    def place_bracket(self, instrument: str, side: str, qty: int, entry_price: float,
                      tp1_price: float, stop_price: float,
                      runner_price: Optional[float] = None,
                      tp1_qty: Optional[int] = None) -> list:
        """PLACE a pending limit entry -- does NOT fill here (matches the real broker:
        place_bracket only SUBMITS; fills happen later via process_quote(), the sim's own
        "exchange"). Refuses (returns []) if a pending or open position already exists for
        `instrument` (no-stacking, mirrors Rule 6 / futures_heartbeat_core's own
        decide_skip=position_open_no_stack discipline)."""
        all_pos = self._load_all_positions()
        existing = all_pos.get(instrument)
        if existing and existing.get("status") in ("pending_entry", "open"):
            self._log_event(instrument, "placed_refused", {
                "reason": f"existing_{existing.get('status')}", "side": side, "qty": qty})
            return []

        direction = "long" if side == "BUY" else "short"
        tp1_q = int(tp1_qty) if tp1_qty else max(1, qty // 2)
        tp1_q = min(max(1, tp1_q), qty)
        now = _et_now()
        oid = _order_id(instrument, "BRK")
        pending = {
            "status": "pending_entry", "instrument": instrument, "direction": direction,
            "side": side, "qty": int(qty), "entry": float(entry_price),
            "stop": float(stop_price), "tp1": float(tp1_price),
            "runner": (None if runner_price is None else float(runner_price)),
            "tp1_qty": tp1_q, "order_id": oid,
            "placed_time_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        all_pos[instrument] = pending
        self._save_all_positions(all_pos)
        self._log_event(instrument, EV_PLACED, {
            "order_id": oid, "side": side, "qty": qty, "entry": entry_price,
            "tp1": tp1_price, "stop": stop_price, "runner": runner_price})
        # tastytrade's real place_bracket returns up to 4 broker order ids (entry/tp1/stop/
        # runner legs). We return one synthetic id per leg for shape-parity even though our
        # sim manages tp1/stop/runner as fields of ONE position object, not 3 separate
        # resting broker orders (see cancel_all()'s docstring for the same divergence).
        ids = [oid, f"{oid}-TP1", f"{oid}-STOP"]
        if runner_price is not None:
            ids.append(f"{oid}-RUNNER")
        return ids

    def cancel_all(self, instrument: str) -> bool:
        """Cancel a PENDING entry (no fill yet). No-op (True) on an OPEN position or an
        already-flat instrument -- our sim has no separate resting TP/stop/runner broker
        orders to cancel (they are fields of the open-position object, not broker orders);
        see place_bracket()'s docstring for the same divergence."""
        all_pos = self._load_all_positions()
        p = all_pos.get(instrument)
        if p and p.get("status") == "pending_entry":
            all_pos[instrument] = None
            self._save_all_positions(all_pos)
            self._log_event(instrument, "cancelled", {"order_id": p.get("order_id")})
        return True

    def close_position(self, instrument: str, qty: int, side: str, price: float) -> bool:
        """Forced/manual close (e.g. an EOD-flatten-equivalent, or a caller-driven exit) --
        realizes qty contracts at `price` immediately, independent of decide_exit()."""
        all_pos = self._load_all_positions()
        p = all_pos.get(instrument)
        if not p or p.get("status") != "open" or int(p.get("qty_open", 0)) <= 0:
            return False
        exit_qty = min(int(qty), int(p["qty_open"]))
        self._realize_fill(instrument, all_pos, p, action="FORCED_CLOSE",
                           exit_qty=exit_qty, fill_price=float(price), event=EV_CLOSED)
        return True

    # ── the fill engine ─────────────────────────────────────────────────────
    def process_quote(self, instrument: str, price: float, *, bar_open: Optional[float] = None,
                      bar_high: Optional[float] = None, bar_low: Optional[float] = None,
                      quote_time_et: Optional[dt.datetime] = None) -> dict:
        """THE fill engine -- the sim's own "exchange". Checks a PENDING entry for a limit
        touch, or an OPEN position for a stop/target touch, and realizes any fill. Pure given
        its inputs (price/bar_open/bar_high/bar_low/quote_time_et) -- no network calls, and no
        clock read unless the caller omits quote_time_et, so every branch is unit-testable
        without mocking network or wall-clock.

        Deliberately never passes now_et into decide_exit(): futures_exit_manager's TIME_STOP
        is an INTRADAY wall-clock check (15:50 ET default) that would force-flatten a multiday
        swing position on the first poll after 15:50 ET on ANY day it is held. A proper
        max-hold-days / roll-date stop (FUTURES-REVIVAL-PLAN sec 2a) is NOT yet implemented --
        flagged as a follow-up, not silently mismatched."""
        now = quote_time_et if quote_time_et is not None else _et_now()
        all_pos = self._load_all_positions()
        p = all_pos.get(instrument)
        if not p or p.get("status") not in ("pending_entry", "open"):
            return {"event": "noop", "instrument": instrument, "reason": "flat"}

        if p["status"] == "pending_entry":
            return self._check_pending_fill(instrument, all_pos, p, price, bar_high, bar_low, now)
        return self._check_open_exit(instrument, all_pos, p, price, bar_open, bar_high, bar_low)

    def _check_pending_fill(self, instrument, all_pos, p, price, bar_high, bar_low, now) -> dict:
        long = p["direction"] == "long"
        hi = bar_high if bar_high is not None else price
        lo = bar_low if bar_low is not None else price
        touched = (lo <= p["entry"]) if long else (hi >= p["entry"])
        if not touched:
            return {"event": "noop", "instrument": instrument, "reason": "entry_not_touched"}

        fill_price = float(p["entry"])  # limit fills AT the limit -- no entry slippage modeled
        state = FuturesExitState(
            instrument=instrument, direction=p["direction"], entry=fill_price,
            stop=p["stop"], tp1=p["tp1"], runner=p["runner"], qty_total=p["qty"],
            qty_open=p["qty"], tp1_qty=p["tp1_qty"], tp1_filled=False,
            entry_time_et=now.strftime("%Y-%m-%dT%H:%M:%S"))
        all_pos[instrument] = {"status": "open", "order_id": p["order_id"], **state.to_dict()}
        self._save_all_positions(all_pos)
        self._log_event(instrument, EV_FILLED, {
            "order_id": p["order_id"], "fill_price": fill_price, "qty": p["qty"],
            "direction": p["direction"]})
        return {"event": EV_FILLED, "instrument": instrument, "fill_price": fill_price,
                "qty": p["qty"]}

    def _check_open_exit(self, instrument, all_pos, p, price, bar_open, bar_high, bar_low) -> dict:
        state = FuturesExitState.from_dict(p)
        plan = decide_exit(state, price=price, bar_high=bar_high, bar_low=bar_low, now_et=None)
        if plan.action == HOLD:
            return {"event": "noop", "instrument": instrument, "reason": "hold"}

        fill_price = self._fill_price_for_action(
            plan.action, direction=p["direction"], stop_price=p["stop"], tp1_price=p["tp1"],
            runner_price=p.get("runner"), price=price, bar_open=bar_open)
        event = _ACTION_TO_EVENT.get(plan.action, EV_CLOSED)
        return self._realize_fill(instrument, all_pos, p, action=plan.action,
                                  exit_qty=plan.exit_qty, fill_price=fill_price, event=event,
                                  new_state=plan.new_state)

    @staticmethod
    def _fill_price_for_action(action: str, *, direction: str, stop_price: float,
                               tp1_price: float, runner_price: Optional[float],
                               price: float, bar_open: Optional[float]) -> float:
        """Per-action fill price. STOP legs are gap-aware (task requirement, plan sec 2f
        convention). Target legs (TP1/runner) fill AT the level (standard conservative
        backtest-sim touch convention, matches futures_sim.simulate_futures). TIME_STOP is
        unreachable here (process_quote never passes now_et into decide_exit -- see its
        docstring) but is handled defensively anyway (fills at the last quote)."""
        if action in (FULL_STOP, RUNNER_BE_STOP):
            return gap_aware_stop_fill(direction, stop_price, price, bar_open)
        if action == TP1_PARTIAL:
            return float(tp1_price)
        if action == RUNNER_TARGET:
            return float(runner_price) if runner_price is not None else float(price)
        return float(price)  # TIME_STOP / fallback

    def _realize_fill(self, instrument, all_pos, p, *, action, exit_qty, fill_price, event,
                      new_state: Optional[FuturesExitState] = None) -> dict:
        inst_spec = get_instrument(instrument)
        direction = p["direction"]
        entry = float(p["entry"])
        points = (fill_price - entry) if direction == "long" else (entry - fill_price)
        gross = points * inst_spec.point_value * exit_qty
        commission = inst_spec.round_turn_usd * exit_qty
        pnl = gross - commission
        acct = self._apply_realized_pnl(pnl)

        if new_state is not None:
            remaining = new_state.qty_open
            next_state_dict = new_state.to_dict()
        else:
            # Forced/manual close (close_position) -- decide_exit() never ran, so compute the
            # post-close state ourselves: same shape, qty_open reduced by exit_qty.
            remaining = max(0, int(p.get("qty_open", p.get("qty", 0))) - exit_qty)
            next_state_dict = {k: p.get(k) for k in
                               ("instrument", "direction", "entry", "stop", "tp1", "runner",
                                "qty_total", "tp1_qty", "tp1_filled", "entry_time_et")}
            next_state_dict["qty_open"] = remaining

        if remaining > 0:
            all_pos[instrument] = {"status": "open", "order_id": p.get("order_id"),
                                   **next_state_dict}
        else:
            all_pos[instrument] = None
        self._save_all_positions(all_pos)

        self._log_event(instrument, event, {
            "action": action, "exit_qty": exit_qty, "fill_price": fill_price,
            "pnl": round(pnl, 2), "commission": commission, "qty_open_after": remaining,
            "equity_after": acct["equity"]})
        return {"event": event, "instrument": instrument, "action": action,
                "exit_qty": exit_qty, "fill_price": fill_price, "pnl": pnl,
                "qty_open_after": remaining}

    def _log_event(self, instrument: str, event: str, detail: dict) -> None:
        now = _et_now()
        record = {"ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "instrument": instrument,
                  "event": event, **detail}
        _append_jsonl(self.would_be_file, record)
