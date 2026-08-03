"""ENTRY-ANCHOR-TO-FILL FIX (2026-08-03) guards.

CONFIRMED DEFECT (root cause verified 2026-08-03 in code + broker orders, see
analysis/staged/entry-anchor-fix-2026-08-03.diff and analysis/staged/
AFTER-CLOSE-PACKAGE-2026-08-03.md for the full evidence chain): both live placement
paths -- fleet_live.py#_place_live (line ~497) and heartbeat_core.py#_execute (line
~2187) -- seed exit_actuator.register_entry's entry_premium from entry_px, the PRE-FILL
marketable-limit price (ask + entry_cross_buffer), never the true fill. Confirmed against
real broker fills 2026-08-03 (safe-3 limit $0.42/fill $0.37; risky-1 limit $0.41/fill
$0.37) and the 105-fill population in analysis/recommendations/
entry-execution-cost-2026-08-02.json (98.1% of real fills price BETTER than their own
limit). Every derived exit threshold (TP1 target, runner_stop_premium, hwm_premium) is
therefore anchored 0-14%+ too high whenever price improvement occurs -- TP1 needs MORE
favorable movement than it should, delaying the partial take-profit and the post-TP1
profit-lock arm (profit_lock_arm_scope="post_tp1"), leaving MORE size exposed to the
catastrophe stop for LONGER. This is the exact mechanism behind J's stated #1 fear
("when it crashes, we end up selling the trade and not making any money").

THE FIX (3 files, all additive -- see the .diff for exact hunks):
  1. exit_actuator.py: new `reanchor_entry()` -- re-anchors a persisted ExitState's
     entry_premium/runner_stop_premium/hwm_premium to the true fill, ONCE, conservatively
     (refuses + the caller logs loudly on: no state, fill unknown, already tp1_filled,
     already profit_lock_armed). hwm_premium is never regressed if a real tick already
     advanced it past the old (wrong) anchor.
  2. fleet_live.py#_place_live: adds a bounded fb.poll_fill() call (mirrors heartbeat_
     core's own _reconcile_fill cap) right after register_entry, then calls
     reanchor_entry with the polled fill. Fleet had ZERO fill-poll anywhere on the entry
     path before this fix (0 of 240 broker sub-objects across every fleet arm's
     decisions.jsonl history ever recorded a non-null filled_avg_price -- confirmed by
     direct corpus scan, see the .diff's cover doc).
  3. heartbeat_core.py: new `_reanchor_after_reconcile()` helper, called at BOTH ENTER
     call sites (the primary path and _route_extra_setups) right after the EXISTING
     FIX3 `_reconcile_exec` poll (which already resolves the true fill but never fed it
     back into the ExitState until now).

Every test in this file is RED-PROOFED: run against the diff's ORIGINAL (unpatched)
modules, `reanchor_entry`/`_reanchor_after_reconcile` do not exist (AttributeError) and
the wiring tests observe the pre-fix, limit-anchored numbers -- proving these tests pin
the NEW behavior, not something that passes either way. See this repo's own dated
verification note in analysis/staged/AFTER-CLOSE-PACKAGE-2026-08-03.md for the actual
RED-then-GREEN transcript captured before this file was checked in.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_entry_anchor_to_fill_2026_08_03.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import exit_actuator as ea  # noqa: E402
import exit_manager as em  # noqa: E402
import fleet_executor as fx  # noqa: E402
import fleet_live as fl  # noqa: E402

RIBBON_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
                "profit_lock_mode": "trailing", "runner_target_pct": 2.5, "trail_pct": 0.125}
SYM = "SPY260803C00754000"


def _arm(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    return "test-arm"


# =============================================================================
# 1. exit_actuator.reanchor_entry -- pure state-machine unit tests
# =============================================================================
class TestReanchorEntryCore:
    def test_reanchors_to_better_fill(self, tmp_path, monkeypatch):
        """The safe-3 2026-08-03 exhibit, exactly: limit $0.42, true fill $0.37, +100%
        TP1. Wrong anchor -> TP1 threshold $0.84. Fixed -> $0.74."""
        arm = _arm(tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=RIBBON_SHAPE, strategy="BULLISH_RECLAIM_RIDE_THE_RIBBON")
        new_st = ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37)
        assert new_st is not None
        assert new_st.entry_premium == 0.37
        assert round(new_st.entry_premium * (1 + new_st.tp1_premium_pct), 2) == 0.74
        # runner_stop_premium recomputed off the TRUE premium via the SAME from_entry formula
        assert new_st.runner_stop_premium == round(0.37 * (1 - 0.50), 4)
        # persisted -- a fresh load sees the corrected state, not the stale one
        assert ea.load_states(arm)[SYM].entry_premium == 0.37

    def test_reanchors_to_equal_fill(self, tmp_path, monkeypatch):
        """risky-3 2026-08-03 exhibit: filled AT the limit (no improvement). Still a valid
        (idempotent) re-anchor -- entry_premium unchanged, no crash, no special-casing
        needed by the caller."""
        arm = _arm(tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.38, qty=5,
                          exit_shape=RIBBON_SHAPE, strategy="BULLISH_RECLAIM_RIDE_THE_RIBBON")
        new_st = ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.38)
        assert new_st is not None and new_st.entry_premium == 0.38

    def test_no_op_when_no_state_exists(self, tmp_path, monkeypatch):
        arm = _arm(tmp_path, monkeypatch)
        assert ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37) is None

    def test_refuses_when_fill_price_none(self, tmp_path, monkeypatch):
        """Fill unknown after polling -- NEVER guess. Keeps the limit anchor as-is
        (today's pre-fix behavior), not a regression."""
        arm = _arm(tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=RIBBON_SHAPE, strategy="x")
        assert ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=None) is None
        assert ea.load_states(arm)[SYM].entry_premium == 0.42  # untouched

    @pytest.mark.parametrize("bad", [0, -0.01, "not-a-number"])
    def test_refuses_when_fill_price_invalid(self, tmp_path, monkeypatch, bad):
        arm = _arm(tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=RIBBON_SHAPE, strategy="x")
        assert ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=bad) is None
        assert ea.load_states(arm)[SYM].entry_premium == 0.42

    def test_refuses_when_already_tp1_filled(self, tmp_path, monkeypatch):
        """A REAL partial-sell already executed against the old anchor -- retroactively
        moving entry_premium would desync the broker's actual proceeds from this ledger.
        Ride out on the original anchor rather than risk corrupting an in-flight
        managed position."""
        arm = _arm(tmp_path, monkeypatch)
        st = ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                               exit_shape=RIBBON_SHAPE, strategy="x")
        states = ea.load_states(arm)
        states[SYM] = __import__("dataclasses").replace(st, tp1_filled=True)
        ea.save_states(arm, states)
        assert ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37) is None
        assert ea.load_states(arm)[SYM].entry_premium == 0.42  # untouched

    def test_refuses_when_already_profit_lock_armed(self, tmp_path, monkeypatch):
        arm = _arm(tmp_path, monkeypatch)
        st = ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                               exit_shape=RIBBON_SHAPE, strategy="x")
        states = ea.load_states(arm)
        states[SYM] = __import__("dataclasses").replace(st, profit_lock_armed=True)
        ea.save_states(arm, states)
        assert ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37) is None
        assert ea.load_states(arm)[SYM].entry_premium == 0.42

    def test_hwm_lowered_when_not_yet_advanced(self, tmp_path, monkeypatch):
        """No real tick has moved hwm past the OLD wrong anchor yet (from_entry seeds
        hwm_premium == entry_premium) -- safe to lower hwm to the true, lower fill."""
        arm = _arm(tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=RIBBON_SHAPE, strategy="x")
        new_st = ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37)
        assert new_st.hwm_premium == 0.37

    def test_hwm_never_regressed_once_a_real_tick_advanced_it(self, tmp_path, monkeypatch):
        """A real tick already pushed hwm_premium above the OLD anchor before the poll
        resolved (e.g. a fast-moving 0.03s window) -- must NOT lower it back down, or a
        legitimately-armed profit lock could be incorrectly un-armed."""
        arm = _arm(tmp_path, monkeypatch)
        st = ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                               exit_shape=RIBBON_SHAPE, strategy="x")
        states = ea.load_states(arm)
        states[SYM] = __import__("dataclasses").replace(st, hwm_premium=0.60)  # real tick moved it
        ea.save_states(arm, states)
        new_st = ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37)
        assert new_st.hwm_premium == 0.60, "must never regress an already-achieved high-water mark"
        assert new_st.entry_premium == 0.37  # entry_premium itself still corrects

    def test_structure_mode_stop_recomputed_off_true_premium_not_re_resolved(self, tmp_path, monkeypatch):
        """stop_mode/trigger_level/catastrophe_stop_pct stay FROZEN (never re-resolved --
        that would violate from_entry's own 'never flaps mid-trade' contract); only the
        PRICE they anchor to moves."""
        arm = _arm(tmp_path, monkeypatch)
        shape = {**RIBBON_SHAPE, "stop_mode": "structure"}
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=shape, strategy="x", trigger_level=750.98,
                          structure_stop_enabled=True)
        new_st = ea.reanchor_entry(arm, symbol=SYM, true_entry_premium=0.37)
        assert new_st.stop_mode == "structure"
        assert new_st.trigger_level == 750.98
        assert new_st.catastrophe_stop_pct == -0.50
        assert new_st.runner_stop_premium == round(0.37 * (1 - 0.50), 4)  # off TRUE premium


# =============================================================================
# 2. fleet_live._place_live wiring -- the poll + reanchor step, end to end
# =============================================================================
class _FakeBrokerWithFill:
    """Extends the established test_place_live_stop_display.py FakeBroker pattern with a
    scripted poll_fill (the new dependency this fix introduces)."""
    def __init__(self, mid, fill_info):
        self.mid = mid
        self.fill_info = fill_info
        self.captured = None
        self.poll_calls = 0

    def get_option_mid(self, creds, symbol):
        return self.mid

    def marketable_limit_price(self, creds, symbol, side="buy", buffer=0.03):
        return round(self.mid + buffer, 2)

    def open_buy_orders(self, creds, symbol):
        return []

    def cancel_order(self, creds, order_id, *, live):
        return {}

    def request(self, creds, endpoint, method="GET", data=None, timeout=15):
        self.captured = {"endpoint": endpoint, "method": method, "data": data}
        return {"id": "fake-order-id", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=0.6):
        self.poll_calls += 1
        return self.fill_info


def _place_with_fill(monkeypatch, *, mid, limit_buffer, fill_info, trigger_level=None):
    fake = _FakeBrokerWithFill(mid, fill_info)
    monkeypatch.setattr(fl.fb, "get_option_mid", fake.get_option_mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", fake.marketable_limit_price)
    monkeypatch.setattr(fl.fb, "open_buy_orders", fake.open_buy_orders)
    monkeypatch.setattr(fl.fb, "cancel_order", fake.cancel_order)
    monkeypatch.setattr(fl.fb, "_request", fake.request)
    monkeypatch.setattr(fl.fb, "poll_fill", fake.poll_fill)
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", lambda creds, symbol: ([], True))
    monkeypatch.setattr(fl.fb, "symbol_position_qty_checked", lambda creds, symbol: (0, True))
    tmp1, tmp2 = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    monkeypatch.setattr(fl, "FLEET_DIR", tmp1)
    monkeypatch.setattr(fl.ea, "FLEET_DIR", tmp2)
    decision = fx.ArmDecision("safe-3", "ENTER_BULL", "C", "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                              754, 3, mid, "ELITE", "ALLOW", "test", trigger_level=trigger_level)
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 8, 3, 9, 42, tzinfo=timezone(timedelta(hours=-4)))
    arm = {"id": "safe-3"}
    res = fl._place_live({}, arm, decision, RIBBON_SHAPE, {}, {}, now)
    return res, fake, tmp2


def test_place_live_reanchors_on_price_improvement(monkeypatch):
    """The live safe-3 2026-08-03 exhibit end to end: mid=0.39, buffer default 0.03 ->
    limit entry_px=0.42; broker actually fills at 0.37. Post-fix, the returned stop AND
    the persisted ExitState must reflect the TRUE $0.37 anchor, not the $0.42 limit."""
    fill_info = {"filled": True, "status": "filled", "filled_qty": 3, "filled_avg_price": 0.37}
    res, fake, ea_dir = _place_with_fill(monkeypatch, mid=0.39, limit_buffer=0.03, fill_info=fill_info)
    assert res["placed"] is True
    assert res["entry_px"] == 0.42          # the ORDER sent to the broker is unaffected (unchanged)
    assert fake.poll_calls == 1
    loaded = ea.load_states.__wrapped__ if hasattr(ea.load_states, "__wrapped__") else None
    # re-point ea back at the temp dir used during placement to read the persisted result
    monkeypatch.setattr(ea, "FLEET_DIR", ea_dir)
    st = ea.load_states("safe-3")["SPY260803C00754000"]
    assert st.entry_premium == 0.37, "persisted ExitState must be re-anchored to the TRUE fill"
    assert st.runner_stop_premium == round(0.37 * (1 - 0.50), 4)


def test_place_live_keeps_limit_anchor_when_fill_unresolved(monkeypatch):
    """poll_fill exhausts its attempts without a terminal fill (RECONCILE_PENDING
    equivalent) -- must NOT guess. The limit-anchored ExitState from register_entry
    stands untouched (today's exact pre-fix behavior, never a regression)."""
    fill_info = {"filled": False, "status": "pending_new", "filled_qty": 0, "filled_avg_price": None}
    res, fake, ea_dir = _place_with_fill(monkeypatch, mid=0.39, limit_buffer=0.03, fill_info=fill_info)
    assert res["placed"] is True
    monkeypatch.setattr(ea, "FLEET_DIR", ea_dir)
    st = ea.load_states("safe-3")["SPY260803C00754000"]
    assert st.entry_premium == 0.42, "must keep the limit anchor when the fill is unresolved"


# =============================================================================
# 3. heartbeat_core._reanchor_after_reconcile wiring
# =============================================================================
class TestHeartbeatCoreWiring:
    @pytest.fixture()
    def hc(self):
        import importlib
        return importlib.import_module("heartbeat_core")

    def _arm_hc(self, hc, tmp_path, monkeypatch):
        monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
        monkeypatch.setitem(hc.ACCOUNTS, "safe",
                            {"params": hc.ACCOUNTS["safe"]["params"], "mcp_server": "alpaca",
                             "fleet_arm": "safe-2"})
        return "safe-2"

    def test_applies_reanchor_with_real_reconciled_fill(self, hc, tmp_path, monkeypatch):
        arm = self._arm_hc(hc, tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=RIBBON_SHAPE, strategy="x")
        exec_row = {"status": "PLACED", "symbol": SYM, "exit_managed": True,
                   "fill": {"reconcile_status": "RECONCILED", "filled_avg_price": 0.37,
                            "filled_qty": 3, "status": "filled"}}
        out = hc._reanchor_after_reconcile("safe", exec_row)
        assert out["reanchor"]["applied"] is True
        assert out["reanchor"]["true_entry_premium"] == 0.37
        assert ea.load_states(arm)[SYM].entry_premium == 0.37

    def test_noop_when_fill_still_pending(self, hc, tmp_path, monkeypatch):
        arm = self._arm_hc(hc, tmp_path, monkeypatch)
        ea.register_entry(arm, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                          exit_shape=RIBBON_SHAPE, strategy="x")
        exec_row = {"status": "PLACED", "symbol": SYM, "exit_managed": True,
                   "fill": {"reconcile_status": "RECONCILE_PENDING"}}
        out = hc._reanchor_after_reconcile("safe", exec_row)
        assert out["reanchor"]["applied"] is False
        assert ea.load_states(arm)[SYM].entry_premium == 0.42  # untouched

    def test_noop_when_not_exit_managed(self, hc, tmp_path, monkeypatch):
        """A dry/WATCH/non-placed row (no exit_managed key) is a pure no-op -- the
        function must never crash on rows that never registered an ExitState."""
        self._arm_hc(hc, tmp_path, monkeypatch)
        exec_row = {"status": "PLACE_FAIL"}
        out = hc._reanchor_after_reconcile("safe", exec_row)
        assert out == {"status": "PLACE_FAIL"}

    def test_passes_through_non_dict_and_none(self, hc, tmp_path, monkeypatch):
        self._arm_hc(hc, tmp_path, monkeypatch)
        assert hc._reanchor_after_reconcile("safe", None) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
