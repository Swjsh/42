"""ORDER-LEVEL IDEMPOTENCY GUARD, CORE lane (2026-08-02).

Ports the fleet lane's fix (commit 71cce7ac, RED-proofed in
automation/state/fleet/test_entry_idempotency_guard.py) to setup/scripts/heartbeat_core.py's
OWN placement path -- the safe-2/bold-2 accounts that trade directly out of _execute() (not
through fleet_live.py). analysis/deep-research/FLEET-RACE-AND-LATENCY-2026-08-01.md section 3
named this file's cancel-replace loop as having the IDENTICAL shape and explicitly left it out
of scope. This matters MORE here: Gamma_HeartbeatCore ticks every 60s in production (PT1M) --
the fleet lane was still at PT3M when ITS version of this gap was closed the same session.

THE GAP (pre-fix): the ONLY guard against a double-entry was fb.is_flat_spy_options(creds) --
a broker POSITIONS query, blind to a still-WORKING order, read ONCE near the top of _execute,
well before the option-quote round-trips that follow it. The cancel-replace loop right before
the broker POST placed a fresh order unconditionally afterward, even when its own cancel raced
a fill at the broker.

Five scenarios, matching the task's own enumeration, plus a NOT_FLAT adoption regression pin
and the two additional post-cancel query-error paths for full status-vocabulary coverage:
  (a) test_pending_order_present_and_survives_cancel_refuses
  (b) test_cancel_races_fill_refuses
  (c) test_two_ticks_one_window_only_first_places (+ test_claim_expires_after_ttl_allows_fresh_entry)
  (d) test_clean_path_places_exactly_once
  (e) test_broker_query_error_refuses_without_crashing (unit) +
      test_broker_query_error_does_not_block_exit_pass (end-to-end via run_account(), also
      proves the guard sits strictly on the entry side -- exits run first, unconditionally)
  NOT_FLAT: test_untracked_position_still_adopted_and_guard_never_reached

RED-PROOF: run this file against `git show HEAD:setup/scripts/heartbeat_core.py` (the
pre-guard content) to see (a)/(b)/(c)/(e)-broker-query-error fail -- see the session report
for the exact before/after transcript; not re-run automatically here since that requires a
temporary file swap outside pytest's scope.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_core_entry_idempotency_guard_2026_08_02.py
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
BOLD_PARAMS_PATH = ROOT / "automation" / "state" / "aggressive" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads(BOLD_PARAMS_PATH.read_text(encoding="utf-8"))

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}
_NOW = dt.datetime(2026, 8, 3, 11, 0)  # naive, matches this suite's established convention
                                       # (hc._et_now is fully mocked -- awareness is irrelevant)

_VERDICT = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "triggers_fired": ["level_rejection"]}
_PAYLOAD = {"bar_ctx": {"timestamp_et": _NOW.strftime("%Y-%m-%d %H:%M:%S"),
                        "bar": {"close": 620.0}, "levels_active": [620.0],
                        # run_account's decision-row builder indexes these directly
                        # (heartbeat_core.py ~1157: bc["ribbon_now"]["stack"] / ["spread_cents"],
                        # bc["vix_now"], bc["htf_15m_stack"]) -- the real _build_payload always
                        # provides them, so end-to-end tests driving run_account() must too.
                        # Their absence made test_broker_query_error_does_not_block_exit_pass
                        # die on KeyError in LOGGING, masking the exit-pass assertion it exists
                        # for (fixed 2026-08-03; the lane that authored this file died mid-work).
                        "ribbon_now": {"stack": "BEARISH", "spread_cents": 45.0},
                        "vix_now": 17.2, "vix_prior": 17.3,
                        "htf_15m_stack": "BEARISH"}}


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts handle deps)."""
    return importlib.import_module("heartbeat_core")


class _FakeBroker:
    """Configurable fake for the guard's own primitives -- mirrors the fleet lane's own
    _FakeBroker (automation/state/fleet/test_entry_idempotency_guard.py) so both guards read
    the same way. Every guard-relevant call is counted/recorded so each test asserts the
    EXACT sequence, not just the final outcome.

    open_buy_orders_checked's 1st call is the pre-cancel check; every call after that is
    treated as a post-cancel re-verify -- `post_cancel_pending` (default: same as the initial
    pending list, i.e. "cancel had no effect") lets each test control that independently.
    """

    def __init__(self, *, mid=1.00, entry_px=1.08, equity="2000.0",
                pending=(), pending_ok=True,
                post_cancel_pending=None, post_cancel_pending_ok=True,
                post_cancel_qty=0, post_cancel_qty_ok=True):
        self.mid = mid
        self.entry_px = entry_px
        self.equity = equity
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


def _wire(hc, monkeypatch, tmp_path: Path, fake: _FakeBroker, *,
         now: dt.datetime = _NOW, manages_exits: bool = True) -> None:
    """Full _execute harness (mirrors test_min_entry_premium_floor.py's _wire_execute): fake
    broker REST, real risk_gate/strike_selection/params, hc.STATE sandboxed to tmp_path (which
    is also where the guard's entry-claim.json lives -- STATE/fleet/{arm}/entry-claim.json --
    so each test gets an isolated claim namespace for free, zero extra wiring)."""
    import fleet_broker as fb
    monkeypatch.setattr(fb, "_request", fake.request)
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "get_option_mid", fake.get_option_mid)
    monkeypatch.setattr(fb, "marketable_limit_price", fake.marketable_limit_price)
    monkeypatch.setattr(fb, "open_buy_orders_checked", fake.open_buy_orders_checked)
    monkeypatch.setattr(fb, "cancel_order", fake.cancel_order)
    monkeypatch.setattr(fb, "symbol_position_qty_checked", fake.symbol_position_qty_checked)
    monkeypatch.setattr(hc, "STATE", tmp_path)
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", manages_exits)
    monkeypatch.setitem(sys.modules, "exit_actuator",
                        types.SimpleNamespace(register_entry=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    class _Resp:
        def read(self):
            return json.dumps({"equity": fake.equity}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())


# --- (d) clean path -> places exactly once, no regression, measured call count -------------
def test_clean_path_places_exactly_once(hc, monkeypatch, tmp_path):
    """No pending order, no claim, no query errors -- the ordinary case must still place,
    exactly once, and the checked primitive must 1:1-replace the old unchecked call (ZERO
    added broker round-trips on the clean path -- requirement #4)."""
    fake = _FakeBroker(pending=[])
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    assert len(fake.posts) == 1
    assert fake.cancel_calls == [], "nothing to cancel on the clean path"
    assert fake.open_buy_orders_checked_calls == 1, (
        "clean path must make EXACTLY one open_buy_orders_checked call -- a 1:1 replacement "
        "of the old open_buy_orders call, not an addition")
    assert fake.symbol_position_qty_checked_calls == 0, (
        "the post-cancel position re-verify must never run when there was nothing to cancel")


def test_clean_path_places_exactly_once_bold_account(hc, monkeypatch, tmp_path):
    """Same clean-path proof on the OTHER core account (bold-2) -- the task names BOTH
    safe-2 and bold-2 as in scope; both share this same _execute, but arm_id differs."""
    fake = _FakeBroker(pending=[], equity="1650.0")
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("bold", dict(_VERDICT), dict(_PAYLOAD), BOLD_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    assert len(fake.posts) == 1
    # the claim landed under bold-2's OWN arm subdir, not safe-2's
    assert (tmp_path / "fleet" / "bold-2" / "entry-claim.json").exists()
    assert not (tmp_path / "fleet" / "safe-2" / "entry-claim.json").exists()


# --- (a) pending order present, survives the cancel attempt -> refused ---------------------
def test_pending_order_present_and_survives_cancel_refuses(hc, monkeypatch, tmp_path):
    """A BUY order is already resting for this exact symbol. _execute attempts the cancel
    (unchanged #15 behavior -- cancel_order IS called), but the re-verify shows it is STILL
    open (the fake cancel is a no-op, simulating a cancel that didn't actually take at the
    broker) -> refuse, never place a second order on top."""
    fake = _FakeBroker(pending=[{"id": "stale-buy-1"}],
                       post_cancel_pending=[{"id": "stale-buy-1"}])  # still there post-cancel
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan["status"] == "SKIP_ORDER_STILL_OPEN_AFTER_CANCEL", plan
    assert fake.cancel_calls == ["stale-buy-1"], "the stale order must still be cancel-attempted"
    assert not fake.posts, "no order may be placed while a pending BUY order is unresolved"


# --- (b) cancel races a fill -> post-cancel re-verify catches it ---------------------------
def test_cancel_races_fill_refuses(hc, monkeypatch, tmp_path):
    """A BUY order is resting; the cancel attempt appears to succeed (open_buy_orders_checked
    now shows [] post-cancel), but symbol_position_qty_checked shows a REAL fill just landed
    for this symbol -- the classic cancel-vs-fill race. Must refuse, not stack a second order
    on top of the fill that already happened."""
    fake = _FakeBroker(pending=[{"id": "racing-buy-1"}],
                       post_cancel_pending=[],        # order is gone from the open list...
                       post_cancel_qty=5)              # ...because it FILLED, not cancelled
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan["status"] == "SKIP_CANCEL_RACED_FILL", plan
    assert fake.cancel_calls == ["racing-buy-1"]
    assert fake.symbol_position_qty_checked_calls == 1, (
        "the post-cancel fill re-verify must actually run")
    assert not fake.posts, "a cancel-vs-fill race must NEVER result in a second order"


# --- the two remaining SKIP_POST_CANCEL_* paths (full vocabulary coverage) -----------------
def test_post_cancel_open_orders_query_error_refuses(hc, monkeypatch, tmp_path):
    """The pre-cancel check finds a pending order and the cancel is attempted, but the
    RE-VERIFY query itself fails (distinct from the pre-cancel query failing) -> refuse."""
    fake = _FakeBroker(pending=[{"id": "stale-buy-2"}],
                       post_cancel_pending_ok=False)  # re-verify query itself errors
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan["status"] == "SKIP_POST_CANCEL_QUERY_ERROR", plan
    assert not fake.posts


def test_post_cancel_position_query_error_refuses(hc, monkeypatch, tmp_path):
    """Cancel appears clean (re-verify shows no pending order), but the position-qty check
    that rules out a cancel/fill race itself fails to answer -> refuse (cannot confirm flat)."""
    fake = _FakeBroker(pending=[{"id": "stale-buy-3"}],
                       post_cancel_pending=[], post_cancel_qty_ok=False)
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan["status"] == "SKIP_POST_CANCEL_POSITION_QUERY_ERROR", plan
    assert not fake.posts


# --- (c) two ticks inside the same window -> only one places -------------------------------
def test_two_ticks_one_window_only_first_places(hc, monkeypatch, tmp_path):
    """Simulates tick N then tick N+1 (30s later, well inside the claim TTL) both reaching
    _execute for the IDENTICAL (arm, symbol) -- same day, so _occ's date-only OCC format
    produces the same symbol. The first places normally; the second is refused by the LOCAL
    claim file BEFORE it ever reaches the broker's open-orders query."""
    fake = _FakeBroker(pending=[])
    _wire(hc, monkeypatch, tmp_path, fake)

    plan1 = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan1["status"] == "PLACED", plan1
    assert len(fake.posts) == 1
    calls_after_first = fake.open_buy_orders_checked_calls

    tick2_now = _NOW + dt.timedelta(seconds=30)  # well inside ENTRY_CLAIM_TTL_SEC (180s)
    monkeypatch.setattr(hc, "_et_now", lambda: tick2_now)
    plan2 = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan2["status"] == "SKIP_DUPLICATE_CLAIM", plan2
    assert len(fake.posts) == 1, "tick N+1 must NOT place a second order"
    assert fake.open_buy_orders_checked_calls == calls_after_first, (
        "the claim must short-circuit BEFORE any broker call on the second tick")


def test_claim_expires_after_ttl_allows_fresh_entry(hc, monkeypatch, tmp_path):
    """Companion to (c): once the claim TTL has elapsed, a genuinely later entry for the SAME
    symbol is allowed again (the claim is short-lived, not a permanent lock)."""
    fake = _FakeBroker(pending=[])
    _wire(hc, monkeypatch, tmp_path, fake)
    plan1 = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan1["status"] == "PLACED"

    later = _NOW + dt.timedelta(seconds=hc.ENTRY_CLAIM_TTL_SEC + 1)
    monkeypatch.setattr(hc, "_et_now", lambda: later)
    plan2 = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan2["status"] == "PLACED", plan2
    assert len(fake.posts) == 2


# --- (e) broker query error -> refuses, never crashes --------------------------------------
def test_broker_query_error_refuses_without_crashing(hc, monkeypatch, tmp_path):
    """open_buy_orders_checked reports a query failure (ok=False) -- must refuse to place
    (fail CLOSED: uncertain state -> no placement) and must NOT raise."""
    fake = _FakeBroker(pending=[], pending_ok=False)  # ok=False -- the query itself failed
    _wire(hc, monkeypatch, tmp_path, fake)
    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)
    assert plan["status"] == "SKIP_ORDER_QUERY_ERROR", plan
    assert not fake.posts


def test_broker_query_error_does_not_block_exit_pass(hc, monkeypatch, tmp_path):
    """End-to-end through run_account(): the entry guard refuses (broker query error on the
    entry path), but the exit-management pass (_manage_exits) -- which run_account() calls
    BEFORE the verdict ladder ever reaches ENTER_BEAR/_execute, unconditionally, for every
    tick where CORE_MANAGES_EXITS is on -- is completely unaffected. This drives the REAL
    run_account() loop (not an assertion from reading the source), proving the guard sits
    strictly on the entry side: never blocks exits, the kill-switch, EOD flatten, or
    _adopt_untracked_positions (all of which run earlier / are independent of this guard)."""
    fake = _FakeBroker(pending=[], pending_ok=False)  # entry-side query error
    _wire(hc, monkeypatch, tmp_path, fake)
    monkeypatch.setattr(hc, "ARMED", True)  # dry = not ARMED -- must be False to reach the guard
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
    monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: dict(_PAYLOAD))
    monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(_VERDICT))
    monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: _PAYLOAD["bar_ctx"]["bar"]["close"])
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setitem(sys.modules, "setup_dispatch",
                        types.SimpleNamespace(dispatch_extra_setups=lambda *a, **k: []))
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))

    exit_calls = {"n": 0}

    def _fake_manage_exits(*a, **k):
        exit_calls["n"] += 1
        return [{"symbol": "SPY260803P00745000", "action": "HOLD"}]

    monkeypatch.setattr(hc, "_manage_exits", _fake_manage_exits)

    rec = hc.run_account("safe")

    assert exit_calls["n"] == 1, "the exit-management pass must run regardless of the entry guard"
    assert rec.get("action") == "SKIP_ORDER_QUERY_ERROR", rec
    assert rec.get("exec", {}).get("status") == "SKIP_ORDER_QUERY_ERROR"
    assert not fake.posts, "a broker query error on the entry guard must never reach the order POST"
    assert logged and logged[-1] is rec, "the tick must still be logged (never silently dropped)"


# --- NOT_FLAT adoption (2026-07-07, J: "get rid of the lockout") must still work exactly ----
def test_untracked_position_still_adopted_and_guard_never_reached(hc, monkeypatch, tmp_path):
    """Regression pin: an untracked manual position must still be ADOPTED into exit_manager
    (not just refused) when the account is NOT_FLAT -- a deliberate 2026-07-07 J directive
    this guard must not regress. The NOT_FLAT check (fb.is_flat_spy_options) runs BEFORE the
    new idempotency guard in _execute -- proven here by making the guard's own broker
    primitive EXPLODE if called at all, not merely asserting it returned an unused value."""
    import fleet_broker as fb

    manual = {"symbol": "SPY260803P00745000", "qty": "3", "avg_entry_price": "1.20",
             "side": "long"}
    registered: list = []
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "open_spy_option_positions", lambda c: [manual])
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: False)  # NOT_FLAT

    def _boom(*a, **k):
        raise AssertionError(
            "the idempotency guard's broker primitive must NEVER be reached on a NOT_FLAT "
            "tick -- the flat-check is a hard predecessor, not a peer, of the entry guard")

    monkeypatch.setattr(fb, "open_buy_orders_checked", _boom)
    monkeypatch.setattr(fb, "symbol_position_qty_checked", _boom)
    monkeypatch.setattr(fb, "cancel_order", _boom)

    fake_ea = types.SimpleNamespace(
        load_states=lambda arm: {},
        register_entry=lambda arm, **k: registered.append(k) or k,
    )
    monkeypatch.setitem(sys.modules, "exit_actuator", fake_ea)
    monkeypatch.setattr(hc, "STATE", tmp_path)
    monkeypatch.setattr(hc, "_et_now", lambda: _NOW)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)

    class _Resp:
        def read(self):
            return json.dumps({"equity": "2000.0"}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())

    plan = hc._execute("safe", dict(_VERDICT), dict(_PAYLOAD), SAFE_PARAMS, dry=False)

    assert plan["status"] == "NOT_FLAT", plan
    assert len(registered) == 1, f"expected exactly one adoption, got {registered}"
    adopted = registered[0]
    assert adopted["symbol"] == "SPY260803P00745000"
    assert adopted["side"] == "P"
    assert adopted["qty"] == 3
    assert adopted["entry_premium"] == 1.20
    assert plan.get("adopted") and plan["adopted"][0]["adopted"] is True
    # and no claim file was ever written for this refused tick
    assert not (tmp_path / "fleet" / "safe-2" / "entry-claim.json").exists()


# --- the G4 extra-setup route shares the SAME guard (both entry lanes funnel into _execute) -
def test_extra_setup_route_shares_the_same_guard(hc, monkeypatch, tmp_path):
    """_route_extra_setups funnels a fired+armed extra setup through the SAME _execute --
    proves the guard protects BOTH callers (primary ribbon ENTER_* and the G4 route), not
    just the one exercised by the other tests in this file."""
    fake = _FakeBroker(pending=[{"id": "stale-buy-9"}],
                       post_cancel_pending=[{"id": "stale-buy-9"}])
    _wire(hc, monkeypatch, tmp_path, fake)
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    # dry = not ARMED, and _execute returns BEFORE the cancel-replace/guard section in dry
    # mode (by design -- dry places nothing, so idempotency is moot). Without this the test
    # exercised the dry path, got WOULD_PLACE, and never reached the guard it exists to
    # prove (fixed 2026-08-03; the authoring lane died mid-work).
    monkeypatch.setattr(hc, "ARMED", True)
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})

    extra = [{"setup_name": "vwap_reclaim_failed_break", "fired": True, "direction": "short",
             "triggers": ["level_rejection"], "rejection_level": 620.5}]
    out = hc._route_extra_setups("safe", extra, dict(_PAYLOAD), SAFE_PARAMS)
    assert out and out[0]["action"] == "SKIP_ORDER_STILL_OPEN_AFTER_CANCEL", out
    assert not fake.posts


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
