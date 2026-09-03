"""TRACE (not a fix) for FLEET-EXIT-STATE-BATCH-SAVE-RACE (queue item
FLEET-PATH-AUDIT-FINDINGS residual (3), UNVERIFIED/code-derived at filing).

Claim being traced: exit_actuator.manage_tick() calls save_states() ONCE, after the
whole per-symbol loop (exit_actuator.py ~798-799), not per symbol. If the process is
killed between a broker-accepted TP1 market_sell and that single end-of-tick write, the
persisted exit-state.json record still says tp1_filled=False while the broker's real
open qty has already dropped by the TP1 tranche. Realistic trigger named in the item:
the task's own 2-minute ExecutionTimeLimit (or `_shared.ps1`'s >5-min python reaper),
not an OS crash.

Method: drive the REAL exit_actuator.manage_tick() -> exit_manager.plan_exit_actions()
call path against a broker double that tracks its own qty (so a "kill" mid-tick is
modeled by making the real exit_actuator.save_states monkeypatched to raise AFTER the
broker-accepted sell already landed, but the loop result is never persisted -- exactly
the window the item names), then reload state from disk and run the NEXT tick against
the broker's now-genuinely-reduced qty + the stale reloaded state, and PIN whatever the
actuator actually does. No fix is applied here; see the verdict in the module docstring
of the queue item's residual (3) writeup for the recommended kill-type fix (per-symbol
save right after each broker-accepted sell).

VERDICT (pinned by these tests): LIVE BUG, not "guarded" by F7. The F7
resting-sell-order dupe guard (exit_actuator.py ~687-697) only catches a REPEAT tick's
sell against an order still resting on the broker; a TP1 market order fills immediately,
so by the next tick nothing is resting and F7 does not see the stale state at all.

  * test_stale_state_causes_second_mislabeled_tp1_sell -- if price is STILL at/above the
    TP1 level next tick, the actuator re-derives the ORIGINAL (pre-kill) TP1 branch off
    the stale tp1_filled=False record. `sell_n = min(state.tp1_qty, open_qty)` correctly
    BOUNDS the qty to what the broker actually still holds (no oversell / no broker
    rejection), but it re-sells the entire remaining RUNNER tranche, mislabels it
    "tp1"/stage="tp1" in the order-intent log, and skips the runner-target/trailing-stop
    management that tranche was supposed to get. The position is not pruned that tick
    (closes_position only checks for a SELL_ALL action; SELL_PARTIAL+RATCHET_STOP is not
    one), so it sits "tracked" as an open runner for one more tick even though the broker
    is now flat -- the D5 flat-prune path (2 consecutive flat reads) cleans the ledger up
    two ticks later, by which point the runner has already been dumped.

  * test_stale_state_exposes_runner_to_wider_pre_kill_stop -- if price has pulled back
    below the TP1 level by the next tick, the stale record instead re-runs the ORIGINAL
    (wider) premium_stop_pct catastrophe check instead of the BE-ratcheted runner_stop
    the real (lost) tick 1 outcome should have installed -- the runner rides with LESS
    downside protection than the validated exit shape intends until the stale record is
    eventually reconciled.

Neither test observed a broker-side oversell, a crash, or a double-count beyond the
single genuine broker qty -- the F7 min()-bound holds. The bug is a mis-executed /
mislabeled leg and a temporarily wrong (looser) stop, not an unbounded oversell.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_actuator as ea  # noqa: E402
import strategies as st  # noqa: E402
from et_clock import ET_TZ as ET  # noqa: E402

ARM = "pytest-exit-state-batch-save-race"
SYM_A = "SPY260903C00450000"
SYM_B = "SPY260903C00460000"
ENTRY = 1.00
MORNING = datetime(2026, 9, 3, 10, 0, tzinfo=ET)  # well clear of any time_stop_et


class RaceBrokerDouble:
    """Broker double that TRACKS its own per-symbol open qty across successive
    manage_tick() calls, exactly like the real broker would after a genuinely-accepted
    market sell -- this is what lets the SECOND tick in these tests see the REAL
    reduced qty the item's trace calls for, independent of what got persisted to disk."""

    def __init__(self, qtys: dict, hilo: dict):
        self._qty = dict(qtys)
        self._hilo = dict(hilo)
        self.sell_calls: list[tuple[str, int, bool]] = []

    def set_hilo(self, symbol: str, hilo: tuple[float, float]) -> None:
        self._hilo[symbol] = hilo

    def qty_of(self, symbol: str) -> int:
        return self._qty.get(symbol, 0)

    def symbol_position_qty_checked(self, creds, symbol):
        return self._qty.get(symbol, 0), True

    def get_option_quote_hilo(self, creds, symbol):
        return self._hilo.get(symbol)

    def open_sell_orders(self, creds, symbol):
        return []  # nothing resting -- confirms F7's dupe guard cannot see this race

    def market_sell(self, creds, *, symbol, qty, live):
        self.sell_calls.append((symbol, qty, live))
        if live:
            self._qty[symbol] = max(0, self._qty.get(symbol, 0) - qty)
        return {"status": "accepted", "filled_qty": qty}


@pytest.fixture()
def two_symbol_arm(tmp_path, monkeypatch):
    """Two tracked positions, mirroring the item's 'two symbols, the first's TP1 fills'
    scenario. ribbon_ride: premium_stop_pct=-0.20, tp1_premium_pct=1.0 (TP1 @ +100%),
    tp1_qty_fraction=0.667 -> qty=3 splits tp1_qty=2 / runner_qty=1."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(ea, "STATUS_MD", tmp_path / "STATUS.md")
    shape = st.by_name("ribbon_ride").exit.to_dict()
    ea.register_entry(ARM, symbol=SYM_A, side="C", entry_premium=ENTRY, qty=3,
                      exit_shape=shape, strategy="ribbon_ride")
    ea.register_entry(ARM, symbol=SYM_B, side="C", entry_premium=ENTRY, qty=2,
                      exit_shape=shape, strategy="ribbon_ride")
    pre = ea.load_states(ARM)
    assert pre[SYM_A].tp1_qty == 2 and pre[SYM_A].runner_qty == 1, "fixture split changed"
    return tmp_path, shape


def _kill_the_batch_save():
    """Model 'the task's own 2-minute ExecutionTimeLimit / the >5-min reaper' firing
    AFTER manage_tick's per-symbol loop has already called broker.market_sell (broker-
    accepted) but BEFORE the single end-of-loop save_states() write lands -- exactly the
    window exit_actuator.py ~798-799 leaves open.

    Deliberately a manual attribute swap (not monkeypatch.setattr): the `two_symbol_arm`
    fixture and this test share ONE function-scoped monkeypatch instance, and
    monkeypatch.undo() reverts EVERYTHING patched through it (including FLEET_DIR/
    STATUS_MD) -- this needs to restore ONLY save_states mid-test."""
    orig = ea.save_states

    def _boom(arm_id, states):
        raise RuntimeError("simulated kill before the batch save_states() write")

    ea.save_states = _boom
    return orig


def test_kill_loses_the_tp1_write_after_broker_already_sold(two_symbol_arm):
    """Ground truth for the race itself: the broker-accepted sell happens; the write
    that would have recorded it does not."""
    tp1_level = ENTRY * (1.0 + 1.0)  # 2.00
    broker = RaceBrokerDouble(
        qtys={SYM_A: 3, SYM_B: 2},
        hilo={SYM_A: (tp1_level, tp1_level), SYM_B: (1.05, 1.05)},
    )
    orig_save = _kill_the_batch_save()
    try:
        with pytest.raises(RuntimeError):
            ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    finally:
        ea.save_states = orig_save  # restore the real save_states before reading state back

    # the broker-side sell REALLY happened before the simulated kill ...
    assert broker.sell_calls == [(SYM_A, 2, True)]
    assert broker.qty_of(SYM_A) == 1  # only the runner remains, broker-side

    # ... but nothing was persisted: the on-disk record is still pre-TP1.
    stale = ea.load_states(ARM)
    assert stale[SYM_A].tp1_filled is False
    assert stale[SYM_A].runner_stop_premium == round(ENTRY * (1.0 - 0.20), 4)


def test_stale_state_causes_second_mislabeled_tp1_sell(two_symbol_arm):
    """Price is STILL at/above the TP1 level on the next tick: pins that the actuator
    re-fires a SECOND 'tp1' leg against the stale pre-kill state, selling the runner's
    only remaining contract (bounded by min(), not oversold) but mislabeled as TP1 and
    without the runner-target/trailing-stop management it should have received."""
    tp1_level = ENTRY * (1.0 + 1.0)
    broker = RaceBrokerDouble(
        qtys={SYM_A: 3, SYM_B: 2},
        hilo={SYM_A: (tp1_level, tp1_level), SYM_B: (1.05, 1.05)},
    )
    orig_save = _kill_the_batch_save()
    try:
        with pytest.raises(RuntimeError):
            ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    finally:
        ea.save_states = orig_save  # tick 2 persists for real, like the live engine's next fire

    # tick 2: broker genuinely holds only the runner (1); price never moved.
    assert broker.qty_of(SYM_A) == 1
    rows = ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    row_a = next(r for r in rows if r["symbol"] == SYM_A)

    assert row_a["actions"], "expected a mis-fired second TP1 leg -- got none"
    leg = row_a["actions"][0]
    assert leg["kind"] == "SELL_PARTIAL"
    assert leg["stage"] == "tp1"
    assert leg["qty"] == 1, "bounded by min(tp1_qty=2, open_qty=1) -- confirms NO oversell"
    assert leg["placed"] is True
    assert broker.sell_calls[-1] == (SYM_A, 1, True)
    assert broker.qty_of(SYM_A) == 0, "broker is now genuinely flat"

    # the position is NOT pruned this tick: closes_position only looks for a SELL_ALL
    # action, and this tick emitted SELL_PARTIAL + RATCHET_STOP -- so the ledger still
    # thinks a runner is open even though the broker holds zero.
    persisted = ea.load_states(ARM)
    assert SYM_A in persisted
    assert persisted[SYM_A].tp1_filled is True
    assert persisted[SYM_A].runner_stop_premium == round(ENTRY, 4)  # ratcheted to BE

    # it self-heals via the pre-existing D5 flat-prune path -- but only after the
    # mis-sell already happened, and only after 2 more flat reads (~2 ticks).
    r3 = ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    a3 = next(r for r in r3 if r["symbol"] == SYM_A)
    assert a3["action"] == "FLAT_SUSPECT_HOLD"
    r4 = ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    a4 = next(r for r in r4 if r["symbol"] == SYM_A)
    assert a4["action"] == "FLAT_PRUNED"


def test_stale_state_exposes_runner_to_wider_pre_kill_stop(two_symbol_arm):
    """Price pulls BACK below the TP1 level by the next tick: pins that the stale record
    re-checks the ORIGINAL (wider, -20%) premium stop instead of the break-even runner
    stop the real (lost) tick-1 TP1 fill should have ratcheted to -- the runner rides
    with less downside protection than the validated exit shape intends until the stale
    record is reconciled."""
    tp1_level = ENTRY * (1.0 + 1.0)
    broker = RaceBrokerDouble(
        qtys={SYM_A: 3, SYM_B: 2},
        hilo={SYM_A: (tp1_level, tp1_level), SYM_B: (1.05, 1.05)},
    )
    orig_save = _kill_the_batch_save()
    try:
        with pytest.raises(RuntimeError):
            ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    finally:
        ea.save_states = orig_save

    # tick 2: price pulled back -- below TP1 (2.00) but above the ORIGINAL stop (0.80)
    # and above where the (lost) BE ratchet (1.00) would have sat.
    broker.set_hilo(SYM_A, (0.90, 0.85))
    rows = ea.manage_tick(ARM, creds={}, live=True, broker=broker, now_et=MORNING)
    row_a = next(r for r in rows if r["symbol"] == SYM_A)

    # the REAL (lost) outcome would have been tp1_filled=True, runner_stop=BE=1.00, so
    # worst=0.85 <= 1.00 should have force-sold the runner at break-even. The STALE
    # record instead re-checks the wider original stop (0.80): 0.85 > 0.80, so nothing
    # fires this tick and the runner keeps riding uncushioned.
    assert row_a["actions"] == [], (
        "stale state let the runner ride past the BE floor it should already have; "
        f"got actions={row_a['actions']}")
    assert row_a["runner_stop"] == round(ENTRY * (1.0 - 0.20), 4), (
        "runner is still governed by the pre-kill -20% stop, not the lost BE ratchet")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
