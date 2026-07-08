"""Guards for the deterministic futures heartbeat + exit-manager (red-proofed).

Covers the 4 required behaviors:
  (a) DRY_RUN default places NO real order.
  (b) FUTURES_ARMED=1 but broker not-provisioned still does NOT route (fails safe).
  (c) the signal -> order chain fires end-to-end on a known v3-validated signal.
  (d) the exit-manager triggers stop / target / time-stop correctly.

Each behavioral guard has a paired "red-proof" assertion documenting the bug it catches: if the
gating/exit logic regresses, the specific assertion named in the comment flips.

Runs under EITHER interpreter (no tastytrade import) — the broker is a spy double.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.instruments import MNQ  # noqa: E402
from futures.risk import TOPSTEP_50K, PropAccount  # noqa: E402
from futures import futures_exit_manager as fx  # noqa: E402
from futures.futures_exit_manager import (  # noqa: E402
    open_state, decide_exit, FuturesExitState,
    HOLD, FULL_STOP, TP1_PARTIAL, RUNNER_TARGET, RUNNER_BE_STOP, TIME_STOP,
)
import futures.futures_heartbeat_core as hb  # noqa: E402


# ─────────────────────────── broker spy double ───────────────────────────────
class SpyBroker:
    """Records every broker call; NEVER touches a network. `provisioned` controls the futures_bp gate.
    `watch_only=False` so the provisioning probe path is exercised (watch_only short-circuits to unprovisioned)."""
    def __init__(self, *, provisioned: bool, watch_only: bool = False):
        self.watch_only = watch_only
        self._provisioned = provisioned
        self._connected = True
        self.placed = []          # every place_bracket call
        self.closed = []          # every close_position call

    def is_connected(self):
        return self._connected

    def connect(self):
        self._connected = True
        return True

    def get_account_equity(self):
        return 2000.0

    def place_bracket(self, instrument, side, qty, entry, tp1, stop, runner_price=None, tp1_qty=None):
        self.placed.append({"instrument": instrument, "side": side, "qty": qty, "entry": entry,
                            "tp1": tp1, "stop": stop, "runner": runner_price})
        return ["ORD-1", "ORD-2"]

    def close_position(self, instrument, qty, side, price):
        self.closed.append({"instrument": instrument, "qty": qty, "side": side, "price": price})
        return True


# Patch the provisioning probe deterministically (avoid any SDK/balance call in tests).
@pytest.fixture(autouse=True)
def _patch_probe(monkeypatch):
    def fake_probe(broker):
        prov = bool(getattr(broker, "_provisioned", False))
        return prov, {"futures_bp": (1000.0 if prov else 0.0)}
    monkeypatch.setattr(hb, "_broker_provisioned", fake_probe)


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """Redirect state emit + position load to a temp dir so guards never touch real state."""
    monkeypatch.setattr(hb, "STATE_DIR", tmp_path)
    monkeypatch.setattr(hb, "LEDGER", tmp_path / "decisions.jsonl")


def _one_v3_signal():
    """A signal object matching a known v3-validated slice (erl_irl long/high, vix>=16 -> take)."""
    return {"watcher": "erl_irl_watcher", "setup": "ERL_IRL_LONG", "direction": "long",
            "confidence": "high", "entry": 21000.0, "stop": 20980.0, "tp1": 21030.0,
            "runner": 21060.0, "reason": "test"}


# ═══════════════════════ (a) DRY_RUN default = no order ═══════════════════════
class TestDryRunDefault:
    def test_no_futures_armed_env_places_nothing(self, monkeypatch):
        monkeypatch.delenv("FUTURES_ARMED", raising=False)
        broker = SpyBroker(provisioned=True)   # even fully provisioned...
        monkeypatch.setattr(hb, "compute_latest_signals",
                            lambda *a, **k: {"signals": [_one_v3_signal()],
                                             "snapshot": {"instrument": "MNQ", "close": 21000.0,
                                                          "ribbon": "BULL", "vix": 18.0,
                                                          "bar_ts_et": "2026-07-06T11:00:00"}})
        rec = hb.run_tick(MNQ, broker=broker)
        assert rec["dry_run"] is True
        assert rec["action"] == "DRY_RUN_VALIDATED"
        # RED-PROOF: if the arm gate ignored FUTURES_ARMED and routed anyway, placed would be non-empty.
        assert broker.placed == [], "dry-run MUST NOT place a real order"
        # but the order WAS built + validated (proves the chain ran, just didn't route)
        assert rec["order_built"]["routed"] is False
        assert rec["order_built"]["qty"] >= 1


# ═══════════ (b) FUTURES_ARMED=1 but not-provisioned still no route ═══════════
class TestArmedButNotProvisioned:
    def test_armed_unprovisioned_fails_safe(self, monkeypatch):
        monkeypatch.setenv("FUTURES_ARMED", "1")
        broker = SpyBroker(provisioned=False)   # today's exact 5WW73759 state (futures_bp=0)
        monkeypatch.setattr(hb, "compute_latest_signals",
                            lambda *a, **k: {"signals": [_one_v3_signal()],
                                             "snapshot": {"instrument": "MNQ", "close": 21000.0,
                                                          "ribbon": "BULL", "vix": 18.0,
                                                          "bar_ts_et": "2026-07-06T11:00:00"}})
        rec = hb.run_tick(MNQ, broker=broker)
        # RED-PROOF: if dry_run were gated on env ALONE (not env AND provisioned), this would be False
        # and the order would route into an unprovisioned account.
        assert rec["dry_run"] is True
        assert rec["provisioned"] is False
        assert broker.placed == [], "armed-but-unprovisioned MUST fail safe (no route)"

    def test_armed_AND_provisioned_would_route(self, monkeypatch):
        """The positive control: only when BOTH hold does dry_run flip off and a real order route."""
        monkeypatch.setenv("FUTURES_ARMED", "1")
        broker = SpyBroker(provisioned=True)
        monkeypatch.setattr(hb, "compute_latest_signals",
                            lambda *a, **k: {"signals": [_one_v3_signal()],
                                             "snapshot": {"instrument": "MNQ", "close": 21000.0,
                                                          "ribbon": "BULL", "vix": 18.0,
                                                          "bar_ts_et": "2026-07-06T11:00:00"}})
        rec = hb.run_tick(MNQ, broker=broker)
        assert rec["dry_run"] is False
        assert rec["action"] == "PLACED"
        assert len(broker.placed) == 1, "armed AND provisioned MUST route exactly one bracket"
        assert broker.placed[0]["side"] == "BUY"


# ═══════════ (c) signal -> order chain fires on a known v3 signal ═════════════
class TestSignalToOrderChain:
    def test_v3_signal_builds_order_and_exit_plan(self, monkeypatch):
        monkeypatch.delenv("FUTURES_ARMED", raising=False)
        broker = SpyBroker(provisioned=False)
        monkeypatch.setattr(hb, "compute_latest_signals",
                            lambda *a, **k: {"signals": [_one_v3_signal()],
                                             "snapshot": {"instrument": "MNQ", "close": 21000.0,
                                                          "ribbon": "BULL", "vix": 18.0,
                                                          "bar_ts_et": "2026-07-06T11:00:00"}})
        rec = hb.run_tick(MNQ, broker=broker)
        # chain: signal -> decide (v3 take) -> order built -> exit plan attached
        assert rec["n_signals"] == 1
        assert "entry" in rec, "a v3-validated signal MUST produce an entry decision"
        assert rec["entry"]["direction"] == "long"
        assert rec["entry"]["qty"] >= 1
        assert rec["exit_plan_at_fill"]["stop"] == 20980.0
        assert rec["exit_plan_at_fill"]["tp1"] == 21030.0

    def test_non_v3_signal_is_rejected(self, monkeypatch):
        """RED-PROOF for the decide filter: a slice NOT in CURATED_V3_RULES must NOT enter."""
        monkeypatch.delenv("FUTURES_ARMED", raising=False)
        broker = SpyBroker(provisioned=False)
        bad = _one_v3_signal()
        bad["watcher"] = "bullish_watcher"   # bullish long/medium is explicitly EXCLUDED in v3
        bad["confidence"] = "medium"
        monkeypatch.setattr(hb, "compute_latest_signals",
                            lambda *a, **k: {"signals": [bad],
                                             "snapshot": {"instrument": "MNQ", "close": 21000.0,
                                                          "ribbon": "BULL", "vix": 18.0,
                                                          "bar_ts_et": "2026-07-06T11:00:00"}})
        rec = hb.run_tick(MNQ, broker=broker)
        assert rec["action"] == "NO_ENTRY"
        assert "entry" not in rec

    def test_low_vix_gates_out_v3_signal(self, monkeypatch):
        """v3 requires vix>=16 for erl_irl; below floor -> no take (deterministic gate)."""
        monkeypatch.delenv("FUTURES_ARMED", raising=False)
        broker = SpyBroker(provisioned=False)
        monkeypatch.setattr(hb, "compute_latest_signals",
                            lambda *a, **k: {"signals": [_one_v3_signal()],
                                             "snapshot": {"instrument": "MNQ", "close": 21000.0,
                                                          "ribbon": "BULL", "vix": 14.0,
                                                          "bar_ts_et": "2026-07-06T11:00:00"}})
        rec = hb.run_tick(MNQ, broker=broker)
        assert rec["action"] == "NO_ENTRY"


# ═══════════════ (d) exit-manager stop / target / time correctness ════════════
class TestExitManager:
    def _long(self):
        return open_state(instrument="MNQ", direction="long", entry=21000.0, stop=20980.0,
                          tp1=21030.0, runner=21060.0, qty_total=4, tp1_fraction=0.5)

    def _short(self):
        return open_state(instrument="MNQ", direction="short", entry=21000.0, stop=21020.0,
                          tp1=20970.0, runner=20940.0, qty_total=4, tp1_fraction=0.5)

    # --- STOP ---
    def test_long_full_stop_before_tp1(self):
        st = self._long()
        plan = decide_exit(st, price=20970.0, bar_low=20970.0, bar_high=20985.0)
        assert plan.action == FULL_STOP
        assert plan.exit_qty == 4
        assert plan.exit_side == "SELL"
        assert plan.new_state.qty_open == 0

    def test_short_full_stop_before_tp1(self):
        st = self._short()
        plan = decide_exit(st, price=21030.0, bar_high=21030.0, bar_low=21010.0)
        assert plan.action == FULL_STOP
        assert plan.exit_side == "BUY"

    def test_no_stop_when_price_inside_range(self):
        """RED-PROOF: a benign in-trade tick must HOLD, not fire a phantom stop."""
        st = self._long()
        plan = decide_exit(st, price=21005.0, bar_low=20995.0, bar_high=21010.0)
        assert plan.action == HOLD
        assert plan.exit_qty == 0

    # --- TARGET (TP1 partial then runner) ---
    def test_long_tp1_partial_moves_stop_to_be(self):
        st = self._long()
        plan = decide_exit(st, price=21030.0, bar_high=21031.0, bar_low=21010.0)
        assert plan.action == TP1_PARTIAL
        assert plan.exit_qty == 2                      # half of 4
        assert plan.new_state.qty_open == 2
        assert plan.new_state.tp1_filled is True
        # RED-PROOF: TP1 MUST ratchet the stop to break-even (entry). If it didn't, this == 20980.
        assert plan.new_state.stop == 21000.0

    def test_runner_target_after_tp1(self):
        st = self._long()
        after_tp1 = decide_exit(st, price=21030.0, bar_high=21031.0, bar_low=21010.0).new_state
        plan = decide_exit(after_tp1, price=21060.0, bar_high=21061.0, bar_low=21040.0)
        assert plan.action == RUNNER_TARGET
        assert plan.exit_qty == 2
        assert plan.new_state.qty_open == 0

    def test_runner_be_stop_after_tp1(self):
        """After TP1 the runner stop sits at break-even; a pullback to entry exits the runner (small win, not a loss)."""
        st = self._long()
        after_tp1 = decide_exit(st, price=21030.0, bar_high=21031.0, bar_low=21010.0).new_state
        plan = decide_exit(after_tp1, price=21000.0, bar_low=20999.0, bar_high=21010.0)
        assert plan.action == RUNNER_BE_STOP
        assert plan.exit_qty == 2

    # --- TIME STOP ---
    def test_time_stop_flattens_all(self):
        st = self._long()
        late = dt.datetime(2026, 7, 6, 15, 50, 0)
        plan = decide_exit(st, price=21005.0, now_et=late)
        assert plan.action == TIME_STOP
        assert plan.exit_qty == 4
        assert plan.new_state.qty_open == 0

    def test_time_stop_not_yet(self):
        """RED-PROOF: before the time-stop, a benign tick must NOT time-flatten."""
        st = self._long()
        early = dt.datetime(2026, 7, 6, 11, 0, 0)
        plan = decide_exit(st, price=21005.0, bar_low=20995.0, bar_high=21010.0, now_et=early)
        assert plan.action == HOLD

    def test_time_stop_beats_target_on_same_tick(self):
        """Time-stop has top priority: even if the runner target is touched, past the deadline we flatten."""
        st = self._long()
        after_tp1 = decide_exit(st, price=21030.0, bar_high=21031.0, bar_low=21010.0).new_state
        late = dt.datetime(2026, 7, 6, 15, 51, 0)
        plan = decide_exit(after_tp1, price=21060.0, bar_high=21061.0, now_et=late)
        assert plan.action == TIME_STOP

    def test_flat_state_holds(self):
        st = FuturesExitState("MNQ", "long", 21000.0, 20980.0, 21030.0, 21060.0,
                              qty_total=4, qty_open=0, tp1_qty=2, tp1_filled=True)
        plan = decide_exit(st, price=20000.0, now_et=dt.datetime(2026, 7, 6, 15, 55))
        assert plan.action == HOLD
        assert plan.exit_qty == 0


# ═══════ dedup-reset determinism (the real-data leak found 2026-07-07) ════════
class TestDedupResetDeterminism:
    """compute_latest_signals must reset run_all_watchers' GLOBAL dedup state each call, so two
    in-process ticks on the same bar return the SAME signals (a live tick is a fresh cold SEE).
    RED-PROOF: without the reset, the 2nd call sees the prior call's per-day dedup and drops the
    repeat setup -> n_signals differs between identical calls (the bug that made the full-chain
    proof show n_signals=0 for a bar that fires 2 signals cold)."""
    def test_two_ticks_same_bar_same_signals(self):
        import lib.watchers.runner as R
        # poison the global dedup as if a prior tick already emitted everything today
        R._dedup_state = {("2026-06-12", "shotgun_scalper_watcher", "OPEN_REJECTION_short"): "high"}
        R._dedup_date = "2026-06-12"
        a = hb.compute_latest_signals(MNQ, at_idx=28090)
        b = hb.compute_latest_signals(MNQ, at_idx=28090)
        assert a.get("error") is None and b.get("error") is None
        assert len(a["signals"]) == len(b["signals"]) >= 1, "dedup reset must make ticks order-independent"
