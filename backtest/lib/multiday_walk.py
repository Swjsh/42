"""Multi-day walk driver — backtest a weekly-option position held ACROSS sessions.

Phase 4 of the weekly-lane night run (markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §9b).
This is what the shop has never had: the SPY harness assumes entry and exit inside one
session, so nothing in it can answer "what happens to a position held Monday to Thursday."

DELEGATES ITS EXIT RULES — DOES NOT REIMPLEMENT THEM
-----------------------------------------------------
Every exit decision is made by `weekly_exit_gate.plan_weekly_exit_actions`, the SAME function
the live shadow lane calls. Reimplementing the rules here would guarantee live/backtest drift,
which this shop treats as a first-class bug class. If the exit rules change, this walker
inherits the change for free and its results stay comparable.

THE HONEST LIMITS OF DAILY BARS (read before trusting any number this produces)
-------------------------------------------------------------------------------
1. **The intraday path is unknown.** A session gives O/H/L/C only. If a session's HIGH would
   have hit the profit target AND its LOW would have hit the stop, which came first is
   genuinely unknowable from this data. Assuming the favorable one is precisely how a
   backtest manufactures edge, so this walker RESOLVES EVERY SUCH SESSION ADVERSELY: it first
   evaluates the session as if only the worst price occurred, and takes that exit if one
   fires. Flagged per-session as `adverse_resolution_applied`.
2. **Overnight gaps are jumps, not paths.** Between sessions the chart stop cannot execute --
   this is the structural fact that makes multi-day holds different from 0DTE. A gap through
   the stop fills at the next session's OPEN, never at the stop price. Flagged `gapped_through`.
3. **Weekends do not exist as sessions** but DO cost theta; the walker simply has no bar for
   them, and `risk.weekend_holds=false` means a correctly-configured position never spans one.
4. **Expiry-day bars are pathological** and are never used for a low-based exit. Observed
   live: an ATM contract printed low=0.07 on 381k volume while closing at 3.20. Exits landing
   on expiry day use the session OPEN, which is a price that actually existed for a
   meaningful window.

Every WalkResult carries the disclosure fields so a downstream report cannot quietly present
modeled numbers as measured ones.
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "backtest" / "data" / "weekly-options"

for _p in (REPO_ROOT / "automation" / "state" / "weekly", REPO_ROOT / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_manager as em  # noqa: E402
import weekly_exit_gate as weg  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "backtest" / "lib"))
from weekly_fill_model import DEFAULT_SPREAD_PCT, buy_fill, sell_fill  # noqa: E402

# Daily granularity forces ONE decision per session. We evaluate at the session close for
# ordinary days; the exit gate itself applies the Friday/expiry flatten schedule when the
# calendar calls for it.
SESSION_DECISION_TIME = dt.time(15, 45)
FRIDAY_DECISION_TIME = dt.time(14, 45)
_FRIDAY = 4


class WalkError(RuntimeError):
    """Raised so a malformed walk fails loud rather than returning a plausible P&L."""


@dataclass(frozen=True)
class SessionBar:
    date_et: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_expiry_day: bool


@dataclass(frozen=True)
class MultiDayPosition:
    contract: str
    symbol: str
    side: str               # "C" | "P"
    entry_date: dt.date
    entry_mid: float
    qty: int
    expiry: dt.date
    zone_width: float
    entry_underlying: float


@dataclass
class WalkResult:
    contract: str
    symbol: str
    side: str
    entry_date: dt.date
    entry_fill: float
    exit_date: Optional[dt.date]
    exit_fill: Optional[float]
    exit_reason: str
    sessions_held: int
    pnl_dollars: float
    return_pct: float
    # --- disclosure: these travel with the number, always ---
    spread_pct_assumed: float
    intraday_path_unknown: bool = True
    adverse_resolution_sessions: int = 0
    gapped_through_sessions: int = 0
    exited_on_expiry_day: bool = False
    session_log: list[dict] = field(default_factory=list)

    def as_row(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "session_log"}
        d["entry_date"] = self.entry_date.isoformat()
        d["exit_date"] = self.exit_date.isoformat() if self.exit_date else None
        return d


def load_contract_bars(contract: str, root: str, data_root: Path = DATA_ROOT) -> list[SessionBar]:
    """Load one contract's cached daily bars, ascending. Raises if absent/empty."""
    path = data_root / root / f"{contract}.csv"
    if not path.exists():
        raise WalkError(
            f"no cached bars for {contract} at {path}. Run "
            f"backtest/tools/fetch_weekly_option_data.py for {root} first."
        )
    bars: list[SessionBar] = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                bars.append(SessionBar(
                    date_et=dt.date.fromisoformat(r["bar_date_et"]),
                    open=float(r["open"]), high=float(r["high"]),
                    low=float(r["low"]), close=float(r["close"]),
                    volume=float(r["volume"] or 0),
                    is_expiry_day=r["is_expiry_day"] == "1",
                ))
            except (KeyError, TypeError, ValueError) as e:
                raise WalkError(f"{path}: unreadable row {r!r}: {e}") from e
    if not bars:
        raise WalkError(f"{path} exists but has zero bars — refusing to walk an empty series")
    bars.sort(key=lambda b: b.date_et)
    return bars


def _decision_dt(session: dt.date) -> dt.datetime:
    t = FRIDAY_DECISION_TIME if session.weekday() == _FRIDAY else SESSION_DECISION_TIME
    return dt.datetime.combine(session, t)


def _build_state(pos: MultiDayPosition, entry_fill: float, shape: dict) -> em.ExitState:
    tp1_fraction = float(shape.get("tp1_qty_fraction", 0.5))
    tp1_qty = max(1, int(round(pos.qty * tp1_fraction)))
    tp1_qty = min(tp1_qty, pos.qty - 1) if pos.qty > 1 else tp1_qty
    return em.ExitState(
        symbol=pos.contract,
        side=pos.side,
        entry_premium=entry_fill,
        total_qty=pos.qty,
        tp1_qty=tp1_qty,
        runner_qty=pos.qty - tp1_qty,
        tp1_premium_pct=float(shape["tp1_premium_pct"]) / 100.0,
        premium_stop_pct=float(shape["catastrophe_stop_pct"]) / 100.0,
        profit_lock_mode="trailing",
        runner_target_pct=float(shape["runner_target_mult"]),
        trail_pct=float(shape["trail_pct"]) / 100.0,
        profit_lock_arm_pct=float(shape["profit_lock_arm_pct"]) / 100.0,
        catastrophe_stop_pct=float(shape["catastrophe_stop_pct"]) / 100.0,
        strategy="weekly_level_v1",
    )


def _signed_move(side: str, entry_underlying: float, current_underlying: float) -> float:
    """+ = favorable to this trade's side. The exit gate never re-derives this sign itself."""
    raw = current_underlying - entry_underlying
    return raw if side == "C" else -raw


def walk(
    pos: MultiDayPosition,
    bars: Sequence[SessionBar],
    shape: dict,
    *,
    underlying_by_date: Optional[dict] = None,
    spread_pct: float = DEFAULT_SPREAD_PCT,
    params: Optional[dict] = None,
) -> WalkResult:
    """Walk one position session-by-session from entry to exit.

    `bars` must include the entry session. `underlying_by_date` supplies the underlying close
    per session for the theta-budget thesis-progress test; when absent, the move is treated as
    zero (the conservative reading — no demonstrated progress, so the theta budget can fire).
    """
    entry_bars = [b for b in bars if b.date_et >= pos.entry_date]
    if not entry_bars:
        raise WalkError(f"{pos.contract}: no bars on/after entry {pos.entry_date}")
    if entry_bars[0].date_et != pos.entry_date:
        raise WalkError(
            f"{pos.contract}: no bar for the entry session {pos.entry_date} "
            f"(first available {entry_bars[0].date_et}) — refusing to silently shift the entry"
        )

    entry_fill = buy_fill(pos.entry_mid, spread_pct).price
    state = _build_state(pos, entry_fill, shape)
    ctx_params = params
    open_qty = pos.qty

    result = WalkResult(
        contract=pos.contract, symbol=pos.symbol, side=pos.side,
        entry_date=pos.entry_date, entry_fill=entry_fill,
        exit_date=None, exit_fill=None, exit_reason="still_open",
        sessions_held=0, pnl_dollars=0.0, return_pct=0.0,
        spread_pct_assumed=spread_pct,
    )

    prior_close: Optional[float] = None
    for bar in entry_bars:
        is_entry_session = bar.date_et == pos.entry_date
        result.sessions_held += 1

        gapped = False
        if prior_close is not None:
            stop_premium = entry_fill * (1.0 + float(shape["catastrophe_stop_pct"]) / 100.0)
            if bar.open <= stop_premium < prior_close:
                gapped = True
                result.gapped_through_sessions += 1

        if is_entry_session:
            prior_close = bar.close
            result.session_log.append({
                "date": bar.date_et.isoformat(), "event": "entry", "fill": entry_fill,
            })
            continue

        underlying = (underlying_by_date or {}).get(bar.date_et)
        move = (
            _signed_move(pos.side, pos.entry_underlying, underlying)
            if underlying is not None else 0.0
        )
        ctx = weg.WeeklyExitContext.from_params(
            entry_session_date=pos.entry_date,
            zone_width=pos.zone_width,
            underlying_move_in_direction=move,
            params=ctx_params,
        )
        now_et = _decision_dt(bar.date_et)

        # --- ADVERSE-FIRST RESOLUTION -------------------------------------------------
        # Evaluate the session as if ONLY the worst price occurred. If an exit fires under
        # that view, it is the outcome — we cannot prove the favorable price came first, and
        # assuming it did is exactly how a daily-bar backtest invents edge.
        adverse = weg.plan_weekly_exit_actions(
            state, ctx, best_premium=bar.low, worst_premium=bar.low,
            open_qty=open_qty, now_et=now_et,
        )
        adverse_fires = bool(getattr(adverse, "actions", None))

        decision = adverse
        if not adverse_fires:
            decision = weg.plan_weekly_exit_actions(
                state, ctx, best_premium=bar.high, worst_premium=bar.low,
                open_qty=open_qty, now_et=now_et,
            )
        else:
            result.adverse_resolution_sessions += 1

        actions = list(getattr(decision, "actions", []) or [])
        if not actions:
            prior_close = bar.close
            result.session_log.append({"date": bar.date_et.isoformat(), "event": "hold"})
            continue

        # Exit price: gap-through fills at the OPEN (the stop could not execute overnight);
        # expiry-day exits use the OPEN because that session's low is pathological.
        if gapped or bar.is_expiry_day:
            exit_mid = bar.open
        else:
            act = actions[0]
            stage = str(getattr(act, "stage", "") or "")
            exit_mid = bar.high if "tp" in stage.lower() or "runner" in stage.lower() else bar.low

        exit_fill = sell_fill(exit_mid, spread_pct).price
        result.exit_date = bar.date_et
        result.exit_fill = exit_fill
        result.exit_reason = str(getattr(actions[0], "stage", "") or "exit")
        result.exited_on_expiry_day = bar.is_expiry_day
        result.pnl_dollars = (exit_fill - entry_fill) * open_qty * 100.0
        result.return_pct = (exit_fill / entry_fill - 1.0) * 100.0
        result.session_log.append({
            "date": bar.date_et.isoformat(), "event": "exit", "reason": result.exit_reason,
            "fill": exit_fill, "gapped": gapped, "expiry_day": bar.is_expiry_day,
        })
        return result

    # Never exited within the available bars: mark to the last close, labelled honestly.
    last = entry_bars[-1]
    exit_fill = sell_fill(last.close, spread_pct).price
    result.exit_date = last.date_et
    result.exit_fill = exit_fill
    result.exit_reason = "series_exhausted"
    result.exited_on_expiry_day = last.is_expiry_day
    result.pnl_dollars = (exit_fill - entry_fill) * open_qty * 100.0
    result.return_pct = (exit_fill / entry_fill - 1.0) * 100.0
    return result


def walk_many(
    positions: Iterable[MultiDayPosition], shape: dict, **kw
) -> tuple[list[WalkResult], list[str]]:
    """Walk many positions. Returns (results, failures) — failures are never silently dropped."""
    results, failures = [], []
    for p in positions:
        try:
            bars = load_contract_bars(p.contract, p.symbol)
            results.append(walk(p, bars, shape, **kw))
        except (WalkError, ValueError) as e:
            failures.append(f"{p.contract}: {e}")
    return results, failures
