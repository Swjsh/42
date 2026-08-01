"""ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02).

Closes the gap documented in analysis/deep-research/FLEET-RACE-AND-LATENCY-2026-08-01.md
section 3: fleet_live.py::_place_live() had NO order-level idempotency protection --
run()'s `flat` gate is a broker POSITIONS query only (invisible to a still-WORKING order),
_place_live never called fb.poll_fill, and its stale-order cancel loop placed a fresh order
unconditionally even when its own cancel raced a fill at the broker. At today's 3-min fleet
cadence this was unlikely; at a candidate 1-min cadence it is a live double-entry hazard.

This file is the guard's OWN dedicated coverage (other test files that exercise
_place_live for unrelated reasons -- test_place_live_stop_display.py, test_fix1_selection.py,
test_money_path_simple_fallback.py, backtest/tests/test_fill_latency_2026_08_01.py -- stub
the guard's two broker primitives to "confirmed clear" so they keep testing what they were
built to test).

Five scenarios, matching the task's own enumeration:
  (a) a pending unfilled BUY order present, and it survives the cancel attempt -> refused.
  (b) cancel races a fill (order gone from the open list, but a position now exists) ->
      the post-cancel re-verify catches it -> refused.
  (c) two ticks inside the same short signal window -> only the first places (claim file).
  (d) normal clean path -> places exactly once (no regression).
  (e) a broker query error on the guard's own primitive -> refuses to place, does NOT
      raise, and does NOT touch/affect the exit-management pass (exits unaffected).

Runs under pytest OR standalone (mirrors this directory's existing test style).
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fleet_executor as fx
import fleet_live as fl

ET = timezone(timedelta(hours=-4))
ARM = {"id": "risky-idem", "live": True}
EXIT_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
             "profit_lock_mode": "trailing"}
_NOW = datetime(2026, 8, 3, 11, 0, 0, tzinfo=ET)


def _decision(**overrides) -> fx.ArmDecision:
    base = dict(arm_id="risky-idem", action="ENTER_BEAR", side="P",
               setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", strike=745, qty=5,
               premium=1.00, quality="BASE", risk_code="ALLOW", reason="test")
    base.update(overrides)
    return fx.ArmDecision(**base)


class _FakeBroker:
    """Configurable fake for the guard's own primitives. Every guard-relevant call is
    counted/recorded so each test asserts the EXACT sequence, not just the final outcome.

    open_buy_orders_checked's 1st call is the pre-cancel check; every call after that is
    treated as a post-cancel re-verify -- `post_cancel_pending` (default: same as the
    initial pending list, i.e. "cancel had no effect") lets each test control that
    independently of the initial state.
    """

    def __init__(self, *, mid=1.00, entry_px=1.08,
                pending=(), pending_ok=True,
                post_cancel_pending=None, post_cancel_pending_ok=True,
                post_cancel_qty=0, post_cancel_qty_ok=True):
        self.mid = mid
        self.entry_px = entry_px
        self._pending = list(pending)
        self._pending_ok = pending_ok
        self._post_cancel_pending = post_cancel_pending
        self._post_cancel_pending_ok = post_cancel_pending_ok
        self._post_cancel_qty = post_cancel_qty
        self._post_cancel_qty_ok = post_cancel_qty_ok
        self.open_buy_orders_checked_calls = 0
        self.symbol_position_qty_checked_calls = 0
        self.cancel_calls: list = []
        self.posts: list = []

    def get_option_mid(self, creds, symbol):
        return self.mid

    def marketable_limit_price(self, creds, symbol, side="buy", buffer=0.03):
        return self.entry_px

    def open_buy_orders_checked(self, creds, symbol):
        self.open_buy_orders_checked_calls += 1
        if self.open_buy_orders_checked_calls == 1:
            return list(self._pending), self._pending_ok
        post = self._pending if self._post_cancel_pending is None else self._post_cancel_pending
        return list(post), self._post_cancel_pending_ok

    def cancel_order(self, creds, order_id, *, live):
        self.cancel_calls.append(order_id)
        return {"id": order_id, "status": "canceled"}

    def symbol_position_qty_checked(self, creds, symbol):
        self.symbol_position_qty_checked_calls += 1
        return self._post_cancel_qty, self._post_cancel_qty_ok

    def request(self, creds, endpoint, method="GET", data=None, timeout=15):
        rec = {"endpoint": endpoint, "method": method, "data": data}
        self.posts.append(rec)
        return {"id": f"fake-order-{len(self.posts)}", "status": "accepted"}


def _wire(monkeypatch, fake: _FakeBroker, fleet_dir: Path) -> None:
    monkeypatch.setattr(fl.fb, "get_option_mid", fake.get_option_mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", fake.marketable_limit_price)
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", fake.open_buy_orders_checked)
    monkeypatch.setattr(fl.fb, "cancel_order", fake.cancel_order)
    monkeypatch.setattr(fl.fb, "symbol_position_qty_checked", fake.symbol_position_qty_checked)
    monkeypatch.setattr(fl.fb, "_request", fake.request)
    monkeypatch.setattr(fl, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(fl.ea, "FLEET_DIR", fleet_dir)


# --- (a) pending order present, survives the cancel attempt -> refused --------------------
def test_pending_order_present_and_survives_cancel_refuses(monkeypatch, tmp_path):
    """A BUY order is already resting for this exact symbol. _place_live attempts the
    cancel (unchanged #15 behavior -- cancel_order IS called), but the re-verify shows it
    is STILL open (the fake cancel is a no-op, simulating a cancel that didn't actually
    take at the broker) -> refuse, never place a second order on top."""
    fake = _FakeBroker(pending=[{"id": "stale-buy-1"}],
                       post_cancel_pending=[{"id": "stale-buy-1"}])  # still there post-cancel
    _wire(monkeypatch, fake, tmp_path)
    res = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, _NOW)
    assert res["placed"] is False
    assert res["reason"] == "SKIP_ORDER_STILL_OPEN_AFTER_CANCEL"
    assert fake.cancel_calls == ["stale-buy-1"], "the stale order must still be cancel-attempted"
    assert not fake.posts, "no order may be placed while a pending BUY order is unresolved"


# --- (b) cancel races a fill -> post-cancel re-verify catches it ---------------------------
def test_cancel_races_fill_refuses(monkeypatch, tmp_path):
    """A BUY order is resting; the cancel attempt appears to succeed (open_buy_orders_checked
    now shows [] post-cancel), but symbol_position_qty_checked shows a REAL fill just
    landed for this symbol -- the classic cancel-vs-fill race. Must refuse, not stack a
    second order on top of the fill that already happened."""
    fake = _FakeBroker(pending=[{"id": "racing-buy-1"}],
                       post_cancel_pending=[],       # order is gone from the open list...
                       post_cancel_qty=5)             # ...because it FILLED, not cancelled
    _wire(monkeypatch, fake, tmp_path)
    res = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, _NOW)
    assert res["placed"] is False
    assert res["reason"] == "SKIP_CANCEL_RACED_FILL"
    assert fake.cancel_calls == ["racing-buy-1"]
    assert fake.symbol_position_qty_checked_calls == 1, \
        "the post-cancel fill re-verify must actually run"
    assert not fake.posts, "a cancel-vs-fill race must NEVER result in a second order"


# --- (c) two ticks inside the same window -> only one places -------------------------------
def test_two_ticks_same_window_only_first_places(monkeypatch, tmp_path):
    """Simulates tick N then tick N+1 (30s later, well inside the claim TTL) both reaching
    _place_live for the IDENTICAL (arm, symbol). The first places normally; the second is
    refused by the LOCAL claim file BEFORE it ever reaches the broker's open-orders query
    (open_buy_orders_checked_calls must stay at 1 after the second call)."""
    fake = _FakeBroker(pending=[])
    _wire(monkeypatch, fake, tmp_path)

    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, _NOW)
    assert res1["placed"] is True
    assert len(fake.posts) == 1
    calls_after_first = fake.open_buy_orders_checked_calls

    tick2_now = _NOW + timedelta(seconds=30)  # well inside ENTRY_CLAIM_TTL_SEC (180s)
    res2 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, tick2_now)
    assert res2["placed"] is False
    assert res2["reason"] == "SKIP_DUPLICATE_CLAIM"
    assert len(fake.posts) == 1, "tick N+1 must NOT place a second order"
    assert fake.open_buy_orders_checked_calls == calls_after_first, \
        "the claim must short-circuit BEFORE any broker call on the second tick"


def test_claim_expires_after_ttl_and_a_fresh_entry_is_allowed(monkeypatch, tmp_path):
    """Companion to (c): once the claim TTL has elapsed, a genuinely later entry for the
    SAME symbol is allowed again (the claim is short-lived, not a permanent lock)."""
    fake = _FakeBroker(pending=[])
    _wire(monkeypatch, fake, tmp_path)
    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, _NOW)
    assert res1["placed"] is True

    later = _NOW + timedelta(seconds=fl.ENTRY_CLAIM_TTL_SEC + 1)
    res2 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, later)
    assert res2["placed"] is True, "an expired claim must not block a later, distinct tick"
    assert len(fake.posts) == 2


# --- (d) normal clean path -> places exactly once (no regression) --------------------------
def test_clean_path_places_exactly_once(monkeypatch, tmp_path):
    """No pending order, no claim, no query errors -- the ordinary case must still place,
    exactly once, with the SAME order shape as before this guard existed."""
    fake = _FakeBroker(pending=[])
    _wire(monkeypatch, fake, tmp_path)
    res = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, _NOW)
    assert res["placed"] is True
    assert len(fake.posts) == 1
    order = fake.posts[0]
    assert order["endpoint"] == "orders" and order["method"] == "POST"
    assert order["data"]["side"] == "buy" and order["data"]["type"] == "limit"
    assert fake.cancel_calls == [], "nothing to cancel on the clean path"


# --- (e) broker query error -> refuses, never crashes, never touches exits -----------------
def test_broker_query_error_refuses_without_crashing(monkeypatch, tmp_path):
    """open_buy_orders_checked reports a query failure (ok=False) -- must refuse to place
    (fail CLOSED: uncertain state -> no placement) and must NOT raise."""
    fake = _FakeBroker(pending=[], pending_ok=False)  # ok=False -- the query itself failed
    _wire(monkeypatch, fake, tmp_path)
    res = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, {}, {}, _NOW)
    assert res["placed"] is False
    assert res["reason"] == "SKIP_ORDER_QUERY_ERROR"
    assert not fake.posts


def test_broker_query_error_does_not_block_exits(monkeypatch, tmp_path):
    """End-to-end through run(): the entry guard refuses (broker query error on the entry
    path), but the exit-management pass (ea.manage_tick) -- which runs BEFORE decide_arm/
    _place_live are ever reached, unconditionally, for every active arm -- is completely
    unaffected. Proves the guard is structurally entry-only, by driving the real run()
    loop, not by asserting it from reading the source."""
    fleet_dir = tmp_path / "fleet"
    fleet_dir.mkdir()
    accounts = {"arms": [{"id": "risky-idem", "status": "active", "execution": "fleet_rest",
                          "live": True}]}
    (fleet_dir / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
    signal_path = fleet_dir / "shared-signal.json"
    signal_path.write_text(json.dumps({
        "tick_id": "t1", "written_at": _NOW.isoformat(), "spot": 745.0,
        "ribbon_stack": "BEAR",
    }), encoding="utf-8")

    exit_calls = {"n": 0}

    def _fake_manage_tick(*a, **k):
        exit_calls["n"] += 1
        return [{"symbol": "SPY260803P00745000", "action": "HOLD"}]

    fake_decision = fx.ArmDecision(
        arm_id="risky-idem", action="ENTER_BEAR", side="P",
        setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", strike=745, qty=5, premium=1.00,
        quality="BASE", risk_code="ALLOW", reason="forced-for-guard-test")

    monkeypatch.setattr(fl, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(fl, "ACCOUNTS_PATH", fleet_dir / "accounts.json")
    monkeypatch.setattr(fl, "_now_et", lambda: _NOW)  # fix the clock inside the 09:35-15:00 window
    monkeypatch.setattr(fl.ea, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(fl.ea, "manage_tick", _fake_manage_tick)
    monkeypatch.setattr(fl, "decide_arm", lambda *a, **k: (fake_decision, EXIT_SHAPE))
    monkeypatch.setattr(fl.fb, "load_creds", lambda: {"risky-idem": {"key": "k", "secret": "s",
                                                                     "base_url": "https://x"}})
    monkeypatch.setattr(fl.fb, "get_account", lambda c: {"equity": "2000.0", "daytrade_count": 0})
    monkeypatch.setattr(fl.fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fl.fb, "get_option_mid", lambda c, s: 1.00)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", lambda c, s, side="buy", buffer=0.03: 1.08)
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", lambda c, s: ([], False))  # BROKEN
    posts: list = []
    monkeypatch.setattr(fl.fb, "_request",
                        lambda *a, **k: posts.append(a) or {"id": "should-not-place"})

    results = fl.run(signal_path, master_live=True)

    assert exit_calls["n"] == 1, "the exit-management pass must run regardless of the entry guard"
    assert results and results[0]["placement"]["placed"] is False
    assert results[0]["placement"]["reason"] == "SKIP_ORDER_QUERY_ERROR"
    assert not posts, "a broker query error on the entry guard must never reach the order POST"


if __name__ == "__main__":
    import sys

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
        tmp = Path(tempfile.mkdtemp())
        try:
            t(mp, tmp)
            print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
