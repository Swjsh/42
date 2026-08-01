"""VISIBILITY (2026-07-09, OP-33c): fleet_live._place_live's plan-log "stop" fields must
show the TRUTH a position is actually managed under -- the known cosmetic bug (STATUS.md
2026-07-09 ~16:20 ET STOP-B ship-1 entry: "plan-log 'stop' shows the -20% fallback even in
structure mode"). These tests prove:
  * structure mode resolved -> stop/premium_stop_pct are corrected to the REAL catastrophe
    floor + pct, and stop_display renders 'STRUCTURE@<level> (cat -50%)'.
  * premium mode (flag off, or no trigger_level) -> BYTE-IDENTICAL to before this build
    (test_fix1_selection.py's existing res["stop"]==0.80/0.94/0.50 pins are untouched --
    this file only adds NEW coverage for the structure branch).
  * render-only: the ONE broker POST (the actual order) is unaffected either way.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import fleet_executor as fx
import fleet_live as fl

_STRUCTURE_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
                    "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
                    "stop_mode": "structure", "catastrophe_stop_pct": -0.50}


class _FakeBroker:
    def __init__(self, mid):
        self.mid = mid
        self.captured = None

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
        return {"id": "fake-order", "status": "accepted"}


def _place_with(monkeypatch, exit_shape, *, params, mid=1.00, trigger_level=None):
    fake = _FakeBroker(mid)
    monkeypatch.setattr(fl.fb, "get_option_mid", fake.get_option_mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", fake.marketable_limit_price)
    monkeypatch.setattr(fl.fb, "open_buy_orders", fake.open_buy_orders)
    monkeypatch.setattr(fl.fb, "cancel_order", fake.cancel_order)
    monkeypatch.setattr(fl.fb, "_request", fake.request)
    # ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02): this file is about stop-display rendering,
    # not the guard -- stub its two broker primitives to "confirmed clear" and sandbox the
    # claim file, exactly like ea.FLEET_DIR is sandboxed below (see
    # test_entry_idempotency_guard.py for the guard's own dedicated coverage).
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", lambda creds, symbol: ([], True))
    monkeypatch.setattr(fl.fb, "symbol_position_qty_checked", lambda creds, symbol: (0, True))
    monkeypatch.setattr(fl, "FLEET_DIR", Path(tempfile.mkdtemp()))
    monkeypatch.setattr(fl.ea, "FLEET_DIR", Path(tempfile.mkdtemp()))
    decision = fx.ArmDecision("risky-loose", "ENTER_BEAR", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON",
                              745, 5, mid, "BASE", "ALLOW", "test", trigger_level=trigger_level)
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 7, 9, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    arm = {"id": "risky-loose"}
    res = fl._place_live({}, arm, decision, exit_shape, {}, params, now)
    return res, fake


def test_structure_mode_corrects_stop_and_renders_display(monkeypatch):
    """Flag ON + a trigger_level available -> structure mode resolves; the numeric stop/
    premium_stop_pct are corrected to the catastrophe floor (NOT the -20% fallback text),
    and stop_display carries the human-readable chart-level truth."""
    params = {"structure_stop_enabled": True}
    res, fake = _place_with(monkeypatch, _STRUCTURE_SHAPE, params=params, mid=1.00,
                            trigger_level=745.0)
    assert res["placed"] is True
    assert res["stop_mode"] == "structure"
    assert res["trigger_level"] == 745.0
    assert res["stop_display"] == "STRUCTURE@745.00 (cat -50%)"
    # the numeric stop must be the REAL catastrophe floor (entry_px-based), NOT the -20%
    # premium fallback (mid*(1-0.20)=0.80) -- this is the actual bug fix, not just a new field
    assert res["premium_stop_pct"] == -0.50
    assert res["stop"] != 0.80, "must not still show the -20% flag-OFF fallback in structure mode"
    # RENDER-ONLY: the one broker POST is untouched -- no stop/tp key ever reaches the order
    assert fake.captured["data"]["type"] == "limit"
    assert "stop" not in fake.captured["data"] and "stop_loss" not in fake.captured["data"]


def test_flag_off_stays_premium_mode_byte_identical(monkeypatch):
    """structure_stop_enabled=False (or absent) -> premium mode, byte-identical to every
    pre-visibility-build number (mirrors test_fix1_selection.py's res["stop"]==0.80 pin)."""
    params = {}  # structure_stop_enabled absent -> False
    res, fake = _place_with(monkeypatch, _STRUCTURE_SHAPE, params=params, mid=1.00,
                            trigger_level=745.0)
    assert res["stop_mode"] == "premium"
    assert res["stop"] == 0.80          # 1.00 * (1 - 0.20), UNCHANGED
    assert res["premium_stop_pct"] == -0.20
    # premium mode: stop_display is built from the SAME mid-based number as res["stop"]
    # (never the entry_px-based ExitState.runner_stop_premium) -- internally consistent.
    assert res["stop_display"] == "0.80 (-20%)"


def test_flag_on_but_no_trigger_level_stays_premium_mode(monkeypatch):
    """Flag ON but NO trigger_level available at entry -> from_entry's third condition
    fails -> premium mode (never guess a level)."""
    params = {"structure_stop_enabled": True}
    res, fake = _place_with(monkeypatch, _STRUCTURE_SHAPE, params=params, mid=1.00,
                            trigger_level=None)
    assert res["stop_mode"] == "premium"
    assert res["stop"] == 0.80
    assert res["trigger_level"] is None


def test_non_structure_shape_unaffected(monkeypatch):
    """A shape that never declares stop_mode="structure" (e.g. vwap_continuation) is
    completely untouched by this build, flag on or off."""
    vwap_shape = {"premium_stop_pct": -0.06, "tp1_premium_pct": 0.40,
                 "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
    res, fake = _place_with(monkeypatch, vwap_shape, params={"structure_stop_enabled": True},
                            mid=1.00, trigger_level=745.0)
    assert res["stop_mode"] == "premium"
    assert res["stop"] == 0.94
    assert res["stop_display"] == "0.94 (-6%)"   # SAME mid-based number as res["stop"]


if __name__ == "__main__":
    import sys
    import types

    class _MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo = []

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        mp = _MP()
        try:
            t(mp)
            print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
