"""FLEET-SAME-BAR-COOLDOWN guard (2026-08-06, core-parity wiring).

Prereg (committed BEFORE the wiring commit, git-provable):
analysis/recommendations/fleet-same-bar-cooldown-prereg-2026-08-06.json (55880b45).

The fleet placement path (_place_live) now mirrors heartbeat_core._route_extra_setups'
2026-07-20 EXTRA-SIGNAL-CHURN-COOLDOWN contract:
  * CONSULT: before any broker work, refuse the entry when this (arm, setup) already
    attempted an entry on THIS exact closed 5m trigger bar (signal "trigger_bar_et",
    string equality via exit_actuator.same_bar_cooldown_active).
  * STAMP: record (arm, setup) -> trigger_bar_et ONLY on an actual placement
    (placed=True); refusals never stamp.
  * FAIL-OPEN: missing/None trigger_bar_et, unreadable cooldown state, or a consult
    exception must never block an entry.

Vary-and-assert pins (C14): same trigger bar -> second entry BLOCKED; NEW trigger bar ->
allowed. RED-proof target: remove/disable the consult in fleet_live._place_live and
test_same_bar_second_entry_blocked fails.

DISARMED AT SHIP (2026-08-06): the ship-gate replay through the PRODUCTION trigger-bar
identity showed the study's +$202/+$144 does NOT transfer (wall-clock bar mapping vs
engine trigger_bar_et, L251 class) and the wiring would have blocked Tue 08-04's +$524
real-fills winner (risky-3 09:57 763C) -- the prereg's own kill criterion, met on day-0
replay. FLEET_SAME_BAR_COOLDOWN therefore defaults to False (pinned below); mechanism
tests arm it explicitly via monkeypatch. Outcome record:
analysis/recommendations/fleet-same-bar-cooldown-OUTCOME-2026-08-06.json.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import fleet_executor as fx
import fleet_live as fl

ET = timezone(timedelta(hours=-4))
ARM = {"id": "risky-cd", "live": True}
EXIT_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
              "profit_lock_mode": "trailing"}
_NOW = datetime(2026, 8, 6, 11, 0, 0, tzinfo=ET)
BAR_A = "2026-08-06T10:55:00-04:00"
BAR_B = "2026-08-06T11:00:00-04:00"


def _decision(**overrides) -> fx.ArmDecision:
    base = dict(arm_id="risky-cd", action="ENTER_BEAR", side="P",
                setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", strike=745, qty=5,
                premium=1.00, quality="BASE", risk_code="ALLOW", reason="test")
    base.update(overrides)
    return fx.ArmDecision(**base)


class _FakeBroker:
    """Clean-path fake: no pending orders, every quote resolves, every POST accepted."""

    def __init__(self):
        self.posts: list = []

    def get_option_mid(self, creds, symbol):
        return 1.00

    def marketable_limit_price(self, creds, symbol, side="buy", buffer=0.03):
        return 1.08

    def open_buy_orders_checked(self, creds, symbol):
        return [], True

    def cancel_order(self, creds, order_id, *, live):
        return {"id": order_id, "status": "canceled"}

    def symbol_position_qty_checked(self, creds, symbol):
        return 0, True

    def order_posts(self):
        return [r for r in self.posts if r["method"] == "POST" and r["endpoint"] == "orders"]

    def request(self, creds, endpoint, method="GET", data=None, timeout=15):
        self.posts.append({"endpoint": endpoint, "method": method, "data": data})
        return {"id": f"fake-order-{len(self.posts)}", "status": "accepted"}


@pytest.fixture()
def fake(monkeypatch, tmp_path) -> _FakeBroker:
    # Mechanism tests run ARMED (the disarmed default is pinned by its own test below).
    monkeypatch.setattr(fl, "FLEET_SAME_BAR_COOLDOWN", True)
    fb = _FakeBroker()
    monkeypatch.setattr(fl.fb, "get_option_mid", fb.get_option_mid)
    monkeypatch.setattr(fl.fb, "marketable_limit_price", fb.marketable_limit_price)
    monkeypatch.setattr(fl.fb, "open_buy_orders_checked", fb.open_buy_orders_checked)
    monkeypatch.setattr(fl.fb, "cancel_order", fb.cancel_order)
    monkeypatch.setattr(fl.fb, "symbol_position_qty_checked", fb.symbol_position_qty_checked)
    monkeypatch.setattr(fl.fb, "_request", fb.request)
    monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(fl.ea, "FLEET_DIR", tmp_path)
    return fb


def _sig(bar: "str | None") -> dict:
    return {"trigger_bar_et": bar} if bar is not None else {}


# --------------------------------------------------------------------------- #
# Vary-and-assert: same bar blocked, new bar allowed
# --------------------------------------------------------------------------- #
def test_same_bar_second_entry_blocked(fake):
    """Entry 1 places + stamps; a re-entry on the SAME trigger bar (stop-out reopened the
    arm to flat mid-bar) is refused BEFORE any broker call."""
    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(BAR_A), {}, _NOW)
    assert res1["placed"] is True
    assert len(fake.order_posts()) == 1
    # stamped: the cooldown ledger now claims BAR_A for this (arm, setup)
    assert fl.ea.load_last_entry_bars("risky-cd") == {
        "BEARISH_REJECTION_RIDE_THE_RIBBON": BAR_A}

    # simulate flat again on the SAME bar; use a later wall-clock + different strike so
    # neither the entry claim file nor broker state can be what refuses (only the cooldown)
    later = _NOW + timedelta(seconds=fl.ENTRY_CLAIM_TTL_SEC + 1)
    res2 = fl._place_live({}, ARM, _decision(strike=744), EXIT_SHAPE, _sig(BAR_A), {}, later)
    assert res2["placed"] is False
    assert res2["reason"] == "SKIP_COOLDOWN_SAME_BAR"
    assert res2["trigger_bar_et"] == BAR_A
    assert len(fake.order_posts()) == 1, "the same-bar re-entry must NEVER reach the broker"


def test_new_trigger_bar_is_allowed(fake):
    """The whole point of bar-advance (not time) cooldown: a genuinely NEW trigger bar
    for the same (arm, setup) trades normally."""
    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(BAR_A), {}, _NOW)
    assert res1["placed"] is True

    later = _NOW + timedelta(seconds=fl.ENTRY_CLAIM_TTL_SEC + 1)
    res2 = fl._place_live({}, ARM, _decision(strike=744), EXIT_SHAPE, _sig(BAR_B), {}, later)
    assert res2["placed"] is True, "a NEW trigger bar must still trade"
    assert len(fake.order_posts()) == 2
    # ledger advanced to the new bar
    assert fl.ea.load_last_entry_bars("risky-cd") == {
        "BEARISH_REJECTION_RIDE_THE_RIBBON": BAR_B}


def test_different_setup_same_bar_is_allowed(fake):
    """Cooldown keys on (arm, setup): a DIFFERENT setup on the same bar is not blocked."""
    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(BAR_A), {}, _NOW)
    assert res1["placed"] is True
    later = _NOW + timedelta(seconds=fl.ENTRY_CLAIM_TTL_SEC + 1)
    res2 = fl._place_live({}, ARM, _decision(setup_name="vwap_continuation", strike=744),
                          EXIT_SHAPE, _sig(BAR_A), {}, later)
    assert res2["placed"] is True


# --------------------------------------------------------------------------- #
# Fail-open contract
# --------------------------------------------------------------------------- #
def test_missing_trigger_bar_fails_open(fake):
    """No trigger_bar_et on the signal (beacon fallback / old rows) -> never blocks,
    never stamps a bar."""
    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(None), {}, _NOW)
    assert res1["placed"] is True
    assert fl.ea.load_last_entry_bars("risky-cd") == {}, \
        "an empty trigger bar must not be stamped"
    later = _NOW + timedelta(seconds=fl.ENTRY_CLAIM_TTL_SEC + 1)
    res2 = fl._place_live({}, ARM, _decision(strike=744), EXIT_SHAPE, _sig(None), {}, later)
    assert res2["placed"] is True, "missing trigger bar must never block (fail-open)"


def test_consult_exception_fails_open(fake, monkeypatch):
    """A broken cooldown reader must never become a trading halt (mirrors core's
    test_cooldown_check_exception_fails_open)."""
    monkeypatch.setattr(fl.ea, "same_bar_cooldown_active",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk error")))
    res = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(BAR_A), {}, _NOW)
    assert res["placed"] is True, "a consult exception must fail OPEN"


def test_no_stamp_on_refused_placement(fake, monkeypatch):
    """A refusal (broker POST error) must NOT stamp the bar -- only actual placements
    consume the (arm, setup, bar) slot, mirroring core's _TAKEN contract."""
    monkeypatch.setattr(fl.fb, "_request",
                        lambda *a, **k: {"_error": "broker rejected", "_status": 422})
    res = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(BAR_A), {}, _NOW)
    assert res["placed"] is False
    assert fl.ea.load_last_entry_bars("risky-cd") == {}, \
        "a refused placement must not claim the trigger bar"


def test_flag_off_reverts_to_pre_wiring_behavior(fake, monkeypatch):
    """One-line revert: FLEET_SAME_BAR_COOLDOWN=False disables consult AND stamp."""
    monkeypatch.setattr(fl, "FLEET_SAME_BAR_COOLDOWN", False)
    res1 = fl._place_live({}, ARM, _decision(), EXIT_SHAPE, _sig(BAR_A), {}, _NOW)
    assert res1["placed"] is True
    assert fl.ea.load_last_entry_bars("risky-cd") == {}, "flag off -> no stamp"
    later = _NOW + timedelta(seconds=fl.ENTRY_CLAIM_TTL_SEC + 1)
    res2 = fl._place_live({}, ARM, _decision(strike=744), EXIT_SHAPE, _sig(BAR_A), {}, later)
    assert res2["placed"] is True, "flag off -> same-bar re-entry allowed (pre-wiring behavior)"


def test_default_is_disarmed_do_not_arm_verdict():
    """DO-NOT-ARM pin (2026-08-06): the day-0 production-faithful replay met the prereg's
    own kill criterion (would have blocked Tue 08-04's +$524 real-fills winner, risky-3
    09:57 763C, while blocking NOTHING on Wed 08-05 -- the measured +$202/+$144 was an
    artifact of the study's wall-clock bar mapping). The flag must stay False until an
    honest forward re-measure keyed to trigger_bar_et clears the prereg gates. Flipping
    this default IS an arming decision -- it requires that re-measure, not just a green
    suite."""
    assert fl.FLEET_SAME_BAR_COOLDOWN is False, (
        "FLEET_SAME_BAR_COOLDOWN armed without clearing the DO-NOT-ARM verdict -- see "
        "analysis/recommendations/fleet-same-bar-cooldown-OUTCOME-2026-08-06.json"
    )
