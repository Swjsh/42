"""AUDIT-FIX guards (2026-07-07) for heartbeat_core.py — three RED-proofed fixes.

Each test class pins ONE fix and goes RED if the production change is reverted.

  FIX1 — MANUAL/ENGINE COEXISTENCE (J: "get rid of the lockout"): a manual
    'gamma-manual-' position froze the engine at NOT_FLAT all day (0 orders 2026-07-06).
    Now _execute ADOPTS any UNTRACKED open position into the exit_manager (so the engine
    manages its exit) while STILL refusing to stack a 2nd position (Rule-6 risk cap).

  FIX2 — EXPIRED LEVELS: _read_levels filtered levels by distance only, so an expired
    level (expires_at in the past, e.g. PML_2026-06-30 @741.61) still reached the live
    active set + filter-10. Now a level whose expires_at < today ET is dropped; a level
    with a missing/unparseable expires_at is KEPT (fail-open) and never crashes the read.

  FIX3 — FILL RECONCILIATION: _place_simple_entry stored the accepted-but-pending POST
    body and never polled, so a filled order stayed status=pending_new / filled_qty=0
    forever (logged UNKNOWN/ungraded in trades.csv). Now _execute polls the order to a
    terminal state and writes the reconciled fill (status=filled / filled_avg_price) back
    into the broker/decision row; a poll failure leaves RECONCILE_PENDING, never crashes.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_audit_fix_heartbeat.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


# =============================================================================
# FIX1 — MANUAL/ENGINE COEXISTENCE
# =============================================================================
class TestManualCoexistence:
    def _wire(self, hc, monkeypatch, tmp_path, *, open_positions, now=dt.datetime(2026, 7, 7, 11, 0)):
        """_execute harness with an OPEN untracked position on the broker."""
        import fleet_broker as fb
        registered: list = []
        tracked_state: dict = {}

        monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
        monkeypatch.setattr(fb, "open_spy_option_positions", lambda c: open_positions)
        # is_flat is NOT what the coexistence branch consults now (it reads
        # open_spy_option_positions directly) — leave a truthful stub anyway.
        monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: len(open_positions) == 0)

        fake_ea = types.SimpleNamespace(
            load_states=lambda arm: dict(tracked_state),
            register_entry=lambda arm, **k: registered.append(k) or k,
        )
        monkeypatch.setitem(sys.modules, "exit_actuator", fake_ea)
        monkeypatch.setattr(hc, "STATE", tmp_path)  # no circuit-breaker / kill-switch
        monkeypatch.setattr(hc, "_et_now", lambda: now)
        monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)

        # equity fetch (urllib) — must never be the thing that blocks the flat guard
        class _Resp:
            def read(self):
                return json.dumps({"equity": "2000.0"}).encode("utf-8")

        import urllib.request as _ur
        monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
        return registered, tracked_state

    def test_untracked_open_position_is_adopted_and_entry_blocked(self, hc, monkeypatch, tmp_path):
        """(a) the untracked manual position is REGISTERED with exit management AND
        (b) the ENTER is still blocked from opening a stacked 2nd position (NOT_FLAT)."""
        manual = {"symbol": "SPY260707P00620000", "qty": "3", "avg_entry_price": "1.20",
                  "side": "long"}
        registered, _ = self._wire(hc, monkeypatch, tmp_path, open_positions=[manual])
        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-07 10:55:00", "bar": {"close": 620.0}}}
        plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False)

        # (b) no stacking: the engine refuses a 2nd position while one is open
        assert plan["status"] == "NOT_FLAT", plan
        # (a) the manual position got adopted into exit management
        assert len(registered) == 1, f"expected exactly one adoption, got {registered}"
        adopted = registered[0]
        assert adopted["symbol"] == "SPY260707P00620000"
        assert adopted["side"] == "P"           # OCC decode: ...P00620000 -> a PUT
        assert adopted["qty"] == 3
        assert adopted["entry_premium"] == 1.20
        assert "exit_shape" in adopted           # registered WITH an exit shape (managed)
        # and the plan surfaces the adoption record
        assert plan.get("adopted") and plan["adopted"][0]["adopted"] is True

    def test_already_tracked_position_is_not_reregistered(self, hc, monkeypatch, tmp_path):
        """Idempotent: a symbol already in the exit-state ledger keeps its evolving state
        (re-registering would reset tp1_filled/hwm) — so no second register_entry fires."""
        sym = "SPY260707C00622000"
        pos = {"symbol": sym, "qty": "3", "avg_entry_price": "0.90", "side": "long"}
        registered, tracked = self._wire(hc, monkeypatch, tmp_path, open_positions=[pos])
        tracked[sym] = object()  # pretend the exit_manager already carries this symbol
        verdict = {"verdict": "ENTER_BULL", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                   "triggers_fired": ["reclaim"]}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-07 10:55:00", "bar": {"close": 622.0}}}
        plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False)
        assert plan["status"] == "NOT_FLAT"
        assert registered == [], "already-tracked position must not be re-registered"


# =============================================================================
# FIX2 — EXPIRED LEVELS
# =============================================================================
class TestExpiredLevels:
    def _write_levels(self, hc, monkeypatch, tmp_path, levels, now):
        (tmp_path / "key-levels.json").write_text(json.dumps({"levels": levels}), encoding="utf-8")
        monkeypatch.setattr(hc, "STATE", tmp_path)
        monkeypatch.setattr(hc, "_et_now", lambda: now)

    def test_yesterday_level_excluded_no_expiry_kept(self, hc, monkeypatch, tmp_path):
        now = dt.datetime(2026, 7, 7, 11, 0)
        levels = [
            {"price": 620.10, "expires_at": "2026-07-06"},          # yesterday -> DROP
            {"price": 620.20},                                       # no expires_at -> KEEP
            {"price": 620.30, "expires_at": "2026-07-07"},          # today -> KEEP (not < today)
            {"price": 620.40, "expires_at": "2026-07-08"},          # future -> KEEP
        ]
        self._write_levels(hc, monkeypatch, tmp_path, levels, now)
        active, _ = hc._read_levels(620.0)
        assert 620.10 not in active, "an expired (yesterday) level must be excluded"
        assert 620.20 in active, "a level with NO expires_at must be kept (fail-open)"
        assert 620.30 in active and 620.40 in active

    def test_malformed_expiry_fails_open_and_never_crashes(self, hc, monkeypatch, tmp_path):
        now = dt.datetime(2026, 7, 7, 11, 0)
        levels = [
            {"price": 620.50, "expires_at": "garbage"},   # unparseable -> KEEP
            {"price": 620.60, "expires_at": None},         # null -> KEEP
            {"price": 620.70, "expires_at": ""},           # empty -> KEEP
        ]
        self._write_levels(hc, monkeypatch, tmp_path, levels, now)
        active, _ = hc._read_levels(620.0)  # must not raise
        assert 620.50 in active and 620.60 in active and 620.70 in active

    def test_helper_direct(self, hc):
        assert hc._level_expired({"expires_at": "2026-06-30"}, "2026-07-07") is True
        assert hc._level_expired({"expires_at": "2026-07-07"}, "2026-07-07") is False
        assert hc._level_expired({"expires_at": "2099-01-01"}, "2026-07-07") is False
        assert hc._level_expired({}, "2026-07-07") is False        # fail-open
        assert hc._level_expired({"expires_at": "nope"}, "2026-07-07") is False


# =============================================================================
# FIX3 — FILL RECONCILIATION
# =============================================================================
class TestFillReconciliation:
    def test_pending_post_polls_to_terminal_filled(self, hc, monkeypatch):
        """A broker order accepted as pending_new that then FILLS must reconcile to a
        terminal filled status with filled_avg_price set — not stay pending_new."""
        import fleet_broker as fb
        # accepted POST body: pending, no fill yet
        accepted = {"id": "ord-9", "status": "pending_new", "filled_qty": "0"}

        calls = {"n": 0}

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            calls["n"] += 1
            # first GET still pending, second GET filled
            if calls["n"] == 1:
                return {"id": "ord-9", "status": "pending_new", "filled_qty": "0"}
            return {"id": "ord-9", "status": "filled", "filled_qty": "3",
                    "filled_avg_price": "1.11"}

        monkeypatch.setattr(fb, "_request", fake_request)
        recon = hc._reconcile_fill(_CREDS, accepted, max_polls=4, sleep_s=0.0, hard_cap_s=3.0)
        assert recon["reconcile_status"] == "RECONCILED"
        assert str(recon["status"]).lower() == "filled"
        assert recon["filled_avg_price"] == "1.11"
        assert recon["filled_qty"] == "3"

    def test_poll_failure_leaves_pending_marker_never_crashes(self, hc, monkeypatch):
        import fleet_broker as fb

        def boom(*a, **k):
            raise RuntimeError("broker unreachable")

        monkeypatch.setattr(fb, "_request", boom)
        recon = hc._reconcile_fill(_CREDS, {"id": "ord-x"}, max_polls=2, sleep_s=0.0, hard_cap_s=1.0)
        assert recon["reconcile_status"] == "RECONCILE_PENDING"

    def test_no_id_or_error_response_is_noop(self, hc, monkeypatch):
        import fleet_broker as fb
        monkeypatch.setattr(fb, "_request", lambda *a, **k: pytest.fail("must not poll a non-order"))
        assert hc._reconcile_fill(_CREDS, {"_refused": "invalid qty"}) == {}
        assert hc._reconcile_fill(_CREDS, {"_error": "422"}) == {}
        assert hc._reconcile_fill(_CREDS, {}) == {}

    def test_reconcile_exec_strips_marker_and_is_noop_without_placement(self, hc):
        """_reconcile_exec always strips the transient _reconcile handle, and is a pure
        no-op for an exec row that placed nothing (no marker present)."""
        assert hc._reconcile_exec(None) is None
        skip = {"status": "NOT_FLAT"}
        assert hc._reconcile_exec(skip) == {"status": "NOT_FLAT"}
        dry = {"status": "WOULD_PLACE", "_reconcile": {"creds": {}, "order": {}}}
        out = hc._reconcile_exec(dry)
        assert "_reconcile" not in out, "marker must always be stripped"

    def test_execute_writes_reconciled_fill_into_broker_row(self, hc, monkeypatch, tmp_path):
        """End-to-end: a PLACED entry whose order fills must land status=filled +
        filled_avg_price in plan['broker'] (the persisted decision row), not pending_new."""
        import fleet_broker as fb
        seq = {"n": 0}

        def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
            if method == "POST":          # the entry placement
                return {"id": "ord-77", "status": "pending_new", "filled_qty": "0"}
            seq["n"] += 1                 # subsequent GET polls -> fills on 2nd read
            if seq["n"] == 1:
                return {"id": "ord-77", "status": "pending_new", "filled_qty": "0"}
            return {"id": "ord-77", "status": "filled", "filled_qty": "3",
                    "filled_avg_price": "1.09"}

        monkeypatch.setattr(fb, "_request", fake_request)
        monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
        monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
        monkeypatch.setattr(fb, "open_spy_option_positions", lambda c: [])
        monkeypatch.setattr(fb, "get_option_mid", lambda c, s: 1.00)
        monkeypatch.setattr(fb, "marketable_limit_price", lambda c, s, side="buy", buffer=0.03: 1.08)
        monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
        monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
        monkeypatch.setattr(hc, "STATE", tmp_path)
        monkeypatch.setattr(hc, "_et_now", lambda: dt.datetime(2026, 7, 7, 11, 0))
        monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
        # speed the reconcile poll (no real sleeps) — call the REAL reconciler, sleep_s=0
        _real_reconcile = hc._reconcile_fill
        monkeypatch.setattr(hc, "_reconcile_fill",
                            lambda creds, order, **k: _real_reconcile(creds, order, sleep_s=0.0))
        monkeypatch.setitem(sys.modules, "exit_actuator",
                            types.SimpleNamespace(register_entry=lambda *a, **k: None,
                                                  load_states=lambda arm: {}))
        monkeypatch.setitem(sys.modules, "strategies",
                            types.SimpleNamespace(by_name=lambda n: None))

        class _Resp:
            def read(self):
                return json.dumps({"equity": "2000.0"}).encode("utf-8")

        import urllib.request as _ur
        monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())

        verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
                   "triggers_fired": ["level_rejection"]}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-07 10:55:00", "bar": {"close": 620.0}}}
        # production wires reconciliation at the CALLER (run_account / _route_extra_setups),
        # exactly as this does: reconcile the _execute result before the decision row is logged.
        plan = hc._reconcile_exec(hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False))
        assert plan["status"] == "PLACED", plan
        assert "_reconcile" not in plan, "the transient reconcile marker must be stripped"
        broker = plan["broker"]
        assert str(broker.get("status")).lower() == "filled", f"ledger row not reconciled: {broker}"
        assert broker.get("filled_avg_price") == "1.09"
        assert broker.get("filled_qty") == "3"
        assert plan["fill"]["reconcile_status"] == "RECONCILED"


# =============================================================================
# D2 (2026-07-07) — ADOPTED MANUAL POSITIONS ARE CAP-ONLY (engine never imposes its exit)
# =============================================================================
class TestAdoptedShapeCapOnly:
    """The engine ADOPTS a manual position to prevent catastrophe, but must NOT impose its
    own TP1 / chandelier / ribbon-flip on a trade J originated (today J scalped 80% and rode
    runners toward 2.5x; a +30% TP1 would have cut his runner). RED-proofs:
      - revert the adopted shape to tp1_qty_fraction>0 -> TP1 sells J's runner (test 1 RED)
      - drop the -50% cap / 15:50 flatten -> unmanaged (test 2)
      - drop the `strategy != adopted_manual` ribbon-flip guard -> flip sells J out (test 3 RED)
    """

    def _captured_adopted_shape(self, hc, monkeypatch):
        """Run the REAL _adopt_untracked_positions with a fake untracked position; capture the
        exit_shape production hands register_entry -> pins the ACTUAL shape, not a copy."""
        captured: dict = {}
        fake_ea = types.SimpleNamespace(
            load_states=lambda arm: {},
            register_entry=lambda arm, **k: captured.update(k) or k,
        )
        monkeypatch.setitem(sys.modules, "exit_actuator", fake_ea)
        monkeypatch.setattr(hc, "_adoption_ping", lambda *a, **k: None)  # don't touch the real outbox
        recs = hc._adopt_untracked_positions(
            "safe", {}, [{"symbol": "SPY260707P00747000", "avg_entry_price": "1.00", "qty": "5"}])
        assert any(r.get("adopted") for r in recs), recs
        return captured["exit_shape"]

    def test_adopted_shape_never_fires_tp1_or_profit_lock(self, hc, monkeypatch):
        import exit_manager as em
        shape = self._captured_adopted_shape(hc, monkeypatch)
        st = em.ExitState.from_entry(symbol="SPY260707P00747000", side="P",
                                     entry_premium=1.00, qty=5, exit_shape=shape,
                                     strategy="adopted_manual")
        assert st.tp1_qty == 0, f"adopted must carry NO TP1 units; shape={shape}"
        # a +150% favorable move must NOT sell any of J's contracts, and profit-lock must not arm
        dec = em.plan_exit_actions(st, best_premium=2.50, worst_premium=1.40, open_qty=5,
                                   now_et=dt.time(11, 0))
        assert not any(a.kind in ("SELL_PARTIAL", "SELL_ALL") for a in dec.actions), \
            f"cap-only adopted position was sold on a +150% move: {dec.actions}"
        assert not dec.state.profit_lock_armed, "profit-lock must never arm on an adopted position"

    def test_adopted_cap_and_timestop_still_fire(self, hc, monkeypatch):
        import exit_manager as em
        shape = self._captured_adopted_shape(hc, monkeypatch)
        st = em.ExitState.from_entry(symbol="SPY260707P00747000", side="P",
                                     entry_premium=1.00, qty=5, exit_shape=shape,
                                     strategy="adopted_manual")
        cap = em.plan_exit_actions(st, best_premium=0.55, worst_premium=0.50, open_qty=5,
                                   now_et=dt.time(11, 0))
        assert any(a.kind == "SELL_ALL" and a.stage == "premium_stop" for a in cap.actions), \
            f"-50% cap must still fire on an adopted position: {cap.actions}"
        eod = em.plan_exit_actions(st, best_premium=1.20, worst_premium=1.10, open_qty=5,
                                   now_et=dt.time(15, 51))
        assert any(a.kind == "SELL_ALL" and a.stage == "time_stop" for a in eod.actions), \
            f"15:50 time-stop must still flatten an adopted position: {eod.actions}"

    def test_ribbon_flip_excluded_for_adopted_but_kept_for_engine(self, monkeypatch):
        import exit_actuator as ea
        import exit_manager as em
        adopted = em.ExitState.from_entry(
            symbol="SPY260707P00747000", side="P", entry_premium=1.00, qty=5,
            exit_shape={"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30,
                        "tp1_qty_fraction": 0.0, "profit_lock_mode": "none"},
            strategy="adopted_manual")
        engine = em.ExitState.from_entry(
            symbol="SPY260707P00750000", side="P", entry_premium=2.00, qty=3,
            exit_shape={"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30,
                        "tp1_qty_fraction": 0.667, "profit_lock_mode": "fixed"},
            strategy="vwap_continuation")
        monkeypatch.setattr(ea, "load_states",
                            lambda arm: {adopted.symbol: adopted, engine.symbol: engine})
        monkeypatch.setattr(ea, "save_states", lambda *a, **k: None)

        sells: list = []

        class _Broker:  # quotes chosen so ONLY a ribbon-flip could exit either position
            _hilo = {adopted.symbol: (1.10, 0.90), engine.symbol: (2.10, 1.90)}  # (best, worst)

            def get_position_qty(self, creds, symbol):
                return 5 if symbol == adopted.symbol else 3

            def get_option_quote_hilo(self, creds, symbol):
                return self._hilo[symbol]

            def market_sell(self, creds, *, symbol, qty, live):
                sells.append((symbol, qty)); return {"ok": True}

        ea.manage_tick("safe", {}, live=True,
                       ribbon_flip_back_fn=lambda symbol, side: True,  # flip EVERYTHING
                       now_et=dt.datetime(2026, 7, 7, 11, 0), broker=_Broker(), time_stop_et="15:50")
        sold = {s for s, _ in sells}
        assert engine.symbol in sold, "ribbon-flip must STILL exit a normal engine position"
        assert adopted.symbol not in sold, \
            f"ribbon-flip must NOT exit an adopted manual position (J drives the exit): {sells}"
