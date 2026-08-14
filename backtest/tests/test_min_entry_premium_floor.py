"""Guard: ENTRY-1 premium floor (`min_entry_premium`), 2026-07-09 ship — STOP-B disposition
(analysis/recommendations/entry-exit-matrix-2026-07-09.md scorecard).

Sub-$0.20 fills are a toxic cohort (T2: ~2-tick stops, ~42% spread proxy -- the stop reads
spread noise, not price action). The floor is a PLAN-TIME strategy-admission check, NOT a
risk_gate rule: it refuses a plan whose entry premium is below `params["min_entry_premium"]`
BEFORE any risk_gate.check_order call, in BOTH lanes:
  * core lane   -- setup/scripts/heartbeat_core.py `_execute` (post-NO_PREMIUM, pre-sizing)
  * fleet lane  -- automation/state/fleet/fleet_executor.py `finalize` (pre-check_order),
                   the single choke point shared by fleet_live.py's decide_arm() (live) and
                   run_dry() (dry-run/CLI/replay) -- see this file's module docstring for why
                   finalize() and not plan_all()/fleet_live.py directly.

RED-PROOFED (vary-and-assert, C14): floor 0.30 rejects a $0.25 plan in BOTH lanes' pure logic;
floor 0 / absent from params is BYTE-IDENTICAL to pre-ship behavior (no new SKIP path taken).

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_min_entry_premium_floor.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from _broker_request_stub import broker_list_stub, order_posts  # shared L294 contract

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


@pytest.fixture()
def hc():
    """heartbeat_core (lives in setup/scripts; module-level sys.path inserts handle deps)."""
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def fx():
    return importlib.import_module("fleet_executor")


# =============================================================================
# COMMITTED-STATE PINS: the floor is really on disk in both lanes' params.json.
# =============================================================================
def test_floor_is_shipped_at_030_in_both_lanes():
    assert SAFE_PARAMS["min_entry_premium"] == 0.30
    assert BOLD_PARAMS["min_entry_premium"] == 0.30


# =============================================================================
# FLEET LANE — automation/state/fleet/fleet_executor.py `finalize` (pure logic, no I/O)
# =============================================================================
def _enter_plan(fx, strategy="ribbon_ride", side="P"):
    return fx.EntryPlan("test-arm", "ENTER", side, "BEARISH_REJECTION_RIDE_THE_RIBBON",
                        620, 3, "BASE", "clean entry", strategy=strategy,
                        exit_shape={"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5,
                                    "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"})


_BASE_RISK_PARAMS = {
    "per_trade_risk_cap_pct": 0.30, "daily_loss_kill_switch_pct": 0.30, "min_contracts": 3,
    "v15_max_premium_pct_of_account": [{"equity_min": 0, "equity_max": 1e9, "max_pct": 0.9}],
}


def _finalize(fx, params, premium, equity=2000.0):
    plan = _enter_plan(fx)
    return fx.finalize(plan, equity=equity, start_of_day_equity=equity, premium=premium,
                       current_position_status=None, day_trades_used_5d=0,
                       kill_switch_tripped=False, prior_stops_today=[], params=params,
                       account_label="TEST")


def test_fleet_finalize_floor_rejects_sub_floor_plan(fx):
    """floor 0.30, premium 0.25 -> HOLD, risk_code SKIP_MIN_PREMIUM_FLOOR, BEFORE check_order."""
    params = {**_BASE_RISK_PARAMS, "min_entry_premium": 0.30}
    decision = _finalize(fx, params, premium=0.25)
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"
    assert "0.25" in decision.reason and "0.3" in decision.reason


def test_fleet_finalize_floor_passes_when_premium_above(fx):
    """premium 0.35 clears the 0.30 floor -> reaches check_order (ALLOW on this small clean order)."""
    params = {**_BASE_RISK_PARAMS, "min_entry_premium": 0.30}
    decision = _finalize(fx, params, premium=0.35)
    assert decision.risk_code != "SKIP_MIN_PREMIUM_FLOOR"
    assert decision.action == "ENTER_BEAR"
    assert decision.risk_code == "ALLOW"


def test_fleet_finalize_floor_absent_is_byte_identical(fx):
    """C14 vary-and-assert: key ABSENT -> identical ArmDecision to calling check_order directly
    (the floor branch must not fire, not even change the reason string)."""
    params = dict(_BASE_RISK_PARAMS)
    assert "min_entry_premium" not in params
    decision = _finalize(fx, params, premium=0.05)  # far below where a floor WOULD trigger
    direct = fx.risk_gate.check_order(
        "TEST", equity=2000.0, start_of_day_equity=2000.0, proposed_qty=3, premium=0.05,
        setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", current_position_status=None,
        day_trades_used_5d=0, kill_switch_tripped=False, prior_stops_today=[], params=params)
    assert decision.risk_code == direct.code
    assert (decision.action == "ENTER_BEAR") == direct.allowed


def test_fleet_finalize_floor_zero_is_byte_identical(fx):
    """C14 vary-and-assert: key present but 0 -> same as absent (explicit OFF)."""
    params = {**_BASE_RISK_PARAMS, "min_entry_premium": 0.0}
    decision = _finalize(fx, params, premium=0.05)
    assert decision.risk_code != "SKIP_MIN_PREMIUM_FLOOR"


def test_fleet_finalize_hold_plan_never_touches_floor(fx):
    """A HOLD plan (no strategy fired) short-circuits before the floor check exists at all --
    the floor must never turn a legitimate HOLD into something else."""
    plan = fx._hold("test-arm", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON", "no qualifying setup")
    decision = fx.finalize(plan, equity=2000.0, start_of_day_equity=2000.0, premium=0.05,
                           current_position_status=None, day_trades_used_5d=0,
                           kill_switch_tripped=False, prior_stops_today=[],
                           params={**_BASE_RISK_PARAMS, "min_entry_premium": 0.30},
                           account_label="TEST")
    assert decision.action == "HOLD" and decision.risk_code is None


# =============================================================================
# CORE LANE — setup/scripts/heartbeat_core.py `_execute` (full harness, broker/urllib faked)
# =============================================================================
def _wire_execute(hc, monkeypatch, tmp_path, *, mid=1.00, equity="2000.0",
                  now=dt.datetime(2026, 7, 9, 11, 0)):
    """Mirrors test_money_path_2026_07_01._wire_execute / test_trade_to_learn's harness:
    fake broker REST + urllib account fetch, real risk_gate/strike_selection/params."""
    import fleet_broker as fb
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})

        _lst = broker_list_stub(endpoint, method)

        if _lst is not None:

            return _lst  # collection endpoints must be LIST-shaped
        return {"id": "ord-1", "status": "accepted"}

    monkeypatch.setattr(fb, "_request", fake_request)
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "get_option_mid", lambda c, s: mid)
    monkeypatch.setattr(fb, "marketable_limit_price",
                        lambda c, s, side="buy", buffer=0.03: round(mid + buffer, 2))
    monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
    monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
    monkeypatch.setattr(hc, "STATE", tmp_path)  # no circuit-breaker / kill-switch files
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
    monkeypatch.setitem(sys.modules, "exit_actuator",
                        types.SimpleNamespace(register_entry=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    class _Resp:
        def read(self):
            return json.dumps({"equity": equity}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return posts


_VERDICT = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
           "triggers_fired": ["level_rejection"]}
_PAYLOAD = {"bar_ctx": {"timestamp_et": "2026-07-09 10:55:00", "bar": {"close": 620.0}}}


def test_core_execute_floor_rejects_sub_floor_mid(hc, monkeypatch, tmp_path):
    """floor 0.30 (as shipped), mid 0.25 -> SKIP_MIN_PREMIUM_FLOOR, ZERO broker POSTs."""
    posts = _wire_execute(hc, monkeypatch, tmp_path, mid=0.25)
    plan = hc._execute("safe", _VERDICT, _PAYLOAD, SAFE_PARAMS, dry=False)
    assert plan["status"] == "SKIP_MIN_PREMIUM_FLOOR", plan
    assert plan["premium"] == 0.25 and plan["min_entry_premium"] == 0.30
    assert len(posts) == 0, "a floor rejection must NEVER reach the broker"


def test_core_execute_floor_passes_when_mid_above_floor(hc, monkeypatch, tmp_path):
    """mid 1.00 clears the 0.30 floor -> proceeds to PLACED exactly as pre-ship."""
    posts = _wire_execute(hc, monkeypatch, tmp_path, mid=1.00)
    plan = hc._execute("safe", _VERDICT, _PAYLOAD, SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    assert len(order_posts(posts)) == 1


def test_core_execute_floor_absent_is_byte_identical(hc, monkeypatch, tmp_path):
    """C14 vary-and-assert: key ABSENT from params -> a sub-$0.20 mid is admitted exactly like
    pre-ship behavior (PLACED), never SKIP_MIN_PREMIUM_FLOOR."""
    params_no_floor = dict(SAFE_PARAMS)
    del params_no_floor["min_entry_premium"]
    posts = _wire_execute(hc, monkeypatch, tmp_path, mid=0.05)
    plan = hc._execute("safe", _VERDICT, _PAYLOAD, params_no_floor, dry=False)
    assert plan["status"] == "PLACED", plan
    assert len(order_posts(posts)) == 1


def test_core_execute_floor_zero_is_byte_identical(hc, monkeypatch, tmp_path):
    """C14 vary-and-assert: key present but 0 -> same as absent (explicit OFF)."""
    params_off = dict(SAFE_PARAMS, min_entry_premium=0.0)
    posts = _wire_execute(hc, monkeypatch, tmp_path, mid=0.05)
    plan = hc._execute("safe", _VERDICT, _PAYLOAD, params_off, dry=False)
    assert plan["status"] == "PLACED", plan
    assert len(order_posts(posts)) == 1


def test_core_execute_bold_floor_rejects_sub_floor_mid(hc, monkeypatch, tmp_path):
    """Both lanes means both ACCOUNTS too -- Bold's own params.json carries the same floor."""
    posts = _wire_execute(hc, monkeypatch, tmp_path, mid=0.10, equity="1650.0")
    plan = hc._execute("bold", _VERDICT, _PAYLOAD, BOLD_PARAMS, dry=False)
    assert plan["status"] == "SKIP_MIN_PREMIUM_FLOOR", plan
    assert len(posts) == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
