"""Read-only G4 exhibit walk: find a trendline-break confirmation bar in real SPY 5m bars,
then (if found) size/exit a hypothetical PUT using the REAL live rules (V15_SAFE_TIERS strike,
strategies.py RIBBON_RIDE exit shape, exit_manager.plan_exit_actions decision core).

NOT a production script. No writes to any automation/state file. No orders. Imports
exit_manager.py READ-ONLY (calls its pure functions; does not modify the file).
"""
import json
import sys
from datetime import time as dtime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import exit_manager as em  # noqa: E402

TOL = 0.10  # trendline_engine.py's own violation tolerance


def find_break_bar(spy_bars_5m: list[dict], line_a_time_idx: int, a_price: float,
                   b_price: float, a_idx: int, b_idx: int, start_check_idx: int) -> dict | None:
    """spy_bars_5m: list of {t, o, h, l, c} ET-labeled. Line defined by two bar indices.
    Returns the first bar (from start_check_idx on) whose CLOSE < projected_line - TOL."""
    slope = (b_price - a_price) / (b_idx - a_idx)
    for j in range(start_check_idx, len(spy_bars_5m)):
        lv = a_price + slope * (j - a_idx)
        c = spy_bars_5m[j]["c"]
        if c < lv - TOL:
            return {"idx": j, "bar": spy_bars_5m[j], "line_value_at_break": round(lv, 2)}
    return None


RIBBON_RIDE_EXIT_SHAPE = {
    "premium_stop_pct": -0.20,
    "tp1_premium_pct": 1.00,
    "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "trailing",
    "runner_target_pct": 99.0,
    "trail_pct": 0.15,
    "stop_mode": "structure",
    "catastrophe_stop_pct": -0.50,
}


def run_exit_walk(entry_premium: float, qty: int, trigger_level: float,
                  option_bars_5m: list[dict], spy_bars_5m: list[dict],
                  entry_bar_idx_spy: int) -> list[dict]:
    """option_bars_5m and spy_bars_5m must be time-aligned (same 5m grid, option bars starting
    at/after entry). Returns a log of ticks (one per option bar) with actions taken."""
    state = em.ExitState.from_entry(
        symbol="HYPOTHETICAL_PUT", side="P", entry_premium=entry_premium, qty=qty,
        exit_shape=RIBBON_RIDE_EXIT_SHAPE, strategy="ribbon_ride_hypothetical",
        trigger_level=trigger_level, structure_stop_enabled=True,
    )
    log = []
    open_qty = qty
    for i, ob in enumerate(option_bars_5m):
        spy_idx = entry_bar_idx_spy + i
        last_closed_5m_close = spy_bars_5m[spy_idx]["c"] if spy_idx < len(spy_bars_5m) else None
        now_et = dtime(*map(int, ob["t_et"].split(":")))
        decision = em.plan_exit_actions(
            state, best_premium=ob["h"], worst_premium=ob["l"], open_qty=open_qty,
            now_et=now_et, ribbon_flip_back=False, last_closed_5m_close=last_closed_5m_close,
        )
        for a in decision.actions:
            log.append({"t_et": ob["t_et"], "kind": a.kind, "qty": a.qty, "reason": a.reason,
                        "stage": a.stage})
            if a.kind == "SELL_PARTIAL":
                open_qty -= a.qty
            elif a.kind == "SELL_ALL":
                open_qty = 0
        state = decision.state
        if open_qty <= 0:
            break
    return log


if __name__ == "__main__":
    print("Module loaded OK. Import and call find_break_bar()/run_exit_walk() from the driver.")
