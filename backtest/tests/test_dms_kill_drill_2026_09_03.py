"""Guards for setup/scripts/dms_kill_drill.py -- the DEAD-MAN'S-SWITCH KILL DRILL tooling
(work order 2c / LIVE-FLIP-RUNBOOK.md section 2 item 2). This script is PREPARATION, not the
drill itself -- it must never fire without a same-day confirm token, must never touch a
process outside heartbeat_core.py's own tree, and must never place a broker order (only the
already-armed dead_mans_switch.py does that). These tests cover:
  1. the refusal matrix (no confirm env / wrong date / bold not flat / safe flat / not RTH)
  2. time-to-flat math + PASS/FAIL classification vs the 12-min bar
  3. an AST guard proving no order-placing call exists anywhere in the module
  4. the observation loop correctly reads a DMS jsonl row and a broker flat-read
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location("dms_kill_drill_g", SCRIPTS / "dms_kill_drill.py")
drill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drill)  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------------------- #
def _base_state(*, safe_qty=3, bold_qty=0, market_open=True, weekday=True):
    return {
        "weekday": weekday,
        "market_open": market_open,
        drill.TARGET_ARM: {
            "read_ok": True,
            "open_positions": [{"symbol": "SPY260903C00650000", "qty": str(safe_qty)}] if safe_qty else [],
            "qty_open": safe_qty,
        },
        drill.OTHER_ARM: {
            "read_ok": True,
            "open_positions": [{"symbol": "SPY260903P00640000", "qty": str(bold_qty)}] if bold_qty else [],
            "qty_open": bold_qty,
        },
    }


TODAY = "2026-09-05"


# --------------------------------------------------------------------------------------- #
# 1. refusal matrix
# --------------------------------------------------------------------------------------- #
def test_refuses_with_no_confirm_env():
    ok, reasons = drill.preflight_check(
        confirm_env=None, today_date=TODAY, accept_bold_flatten=False, state=_base_state(),
    )
    assert ok is False
    assert any("not set" in r for r in reasons)


def test_refuses_with_wrong_date_confirm_env():
    ok, reasons = drill.preflight_check(
        confirm_env="2026-09-01", today_date=TODAY, accept_bold_flatten=False, state=_base_state(),
    )
    assert ok is False
    assert any("does not match today" in r for r in reasons)


def test_refuses_when_bold_not_flat_and_not_accepted():
    ok, reasons = drill.preflight_check(
        confirm_env=TODAY, today_date=TODAY, accept_bold_flatten=False,
        state=_base_state(bold_qty=2),
    )
    assert ok is False
    assert any("accept-bold-flatten" in r for r in reasons)


def test_permits_when_bold_not_flat_but_accepted():
    ok, reasons = drill.preflight_check(
        confirm_env=TODAY, today_date=TODAY, accept_bold_flatten=True,
        state=_base_state(bold_qty=2),
    )
    assert ok is True
    assert reasons == []


def test_refuses_when_safe_is_flat():
    ok, reasons = drill.preflight_check(
        confirm_env=TODAY, today_date=TODAY, accept_bold_flatten=False,
        state=_base_state(safe_qty=0),
    )
    assert ok is False
    assert any("nothing to time-to-flat" in r for r in reasons)


def test_refuses_outside_rth_market_closed():
    ok, reasons = drill.preflight_check(
        confirm_env=TODAY, today_date=TODAY, accept_bold_flatten=False,
        state=_base_state(market_open=False),
    )
    assert ok is False
    assert any("market open" in r for r in reasons)


def test_refuses_on_weekend():
    ok, reasons = drill.preflight_check(
        confirm_env=TODAY, today_date=TODAY, accept_bold_flatten=False,
        state=_base_state(weekday=False),
    )
    assert ok is False
    assert any("weekday" in r for r in reasons)


def test_all_clear_permits_the_drill():
    ok, reasons = drill.preflight_check(
        confirm_env=TODAY, today_date=TODAY, accept_bold_flatten=False, state=_base_state(),
    )
    assert ok is True
    assert reasons == []


def test_reasons_accumulate_not_short_circuit():
    """Multiple blockers at once must ALL be reported (not just the first) -- so a --plan
    run shows every problem instead of whack-a-mole one-at-a-time discovery."""
    ok, reasons = drill.preflight_check(
        confirm_env=None, today_date=TODAY, accept_bold_flatten=False,
        state=_base_state(safe_qty=0, market_open=False, weekday=False),
    )
    assert ok is False
    assert len(reasons) >= 4


# --------------------------------------------------------------------------------------- #
# 2. time-to-flat math + classification
# --------------------------------------------------------------------------------------- #
def test_compute_time_to_flat_s_basic():
    assert drill.compute_time_to_flat_s(1000.0, 1500.0) == 500.0


def test_compute_time_to_flat_s_never_flat_returns_none():
    assert drill.compute_time_to_flat_s(1000.0, None) is None


def test_classify_outcome_pass_at_exact_target():
    assert drill.classify_outcome(720.0, target_s=720) == "PASS"


def test_classify_outcome_fail_just_over_target():
    assert drill.classify_outcome(720.1, target_s=720) == "FAIL"


def test_classify_outcome_fail_when_never_flat():
    assert drill.classify_outcome(None) == "FAIL"


def test_classify_outcome_pass_well_under_target():
    assert drill.classify_outcome(300.0) == "PASS"


# --------------------------------------------------------------------------------------- #
# 3. AST guard: no order-placing call anywhere in the module
# --------------------------------------------------------------------------------------- #
ORDER_VERBS = {
    "place_bracket", "place_option_order", "place_stock_order", "place_crypto_order",
    "market_sell", "close_all_spy_options", "replace_order_by_id", "replace_stop_order",
    "cancel_order", "cancel_all_orders",
}


def test_no_order_placing_call_anywhere_in_module():
    src = (SCRIPTS / "dms_kill_drill.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits = [
        (n.lineno, n.func.attr) for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in ORDER_VERBS
    ]
    assert hits == [], f"order-placing call(s) found in a drill/observer module: {hits}"


def test_only_broker_calls_are_reads():
    """Every fleet_broker.* attribute call in the module must be one of the known-safe
    read-only surfaces. A new call to anything else must be reviewed before this passes."""
    ALLOWED = {"load_creds", "open_spy_option_positions_checked", "_request", "get_account",
               "is_flat_spy_options"}
    src = (SCRIPTS / "dms_kill_drill.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id in ("broker", "fleet_broker")):
            assert n.func.attr in ALLOWED, (
                f"line {n.lineno}: {n.func.value.id}.{n.func.attr} is not an allowed read-only call"
            )


# --------------------------------------------------------------------------------------- #
# 4. observation loop
# --------------------------------------------------------------------------------------- #
class _FakeBroker:
    def __init__(self, flat_after_calls=2):
        self.calls = 0
        self.flat_after_calls = flat_after_calls

    def open_spy_option_positions_checked(self, creds):
        self.calls += 1
        if self.calls >= self.flat_after_calls:
            return ([], True)
        return ([{"symbol": "SPY260903C00650000", "qty": "3"}], True)


def test_observe_one_kill_detects_flat_and_dms_row(tmp_path, monkeypatch):
    date_str = "2026-09-05"
    monkeypatch.setattr(drill, "et_now", lambda: __import__("datetime").datetime(2026, 9, 5, 10, 0, 0))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(drill, "DMS_LOG_DIR", log_dir)

    jsonl_path = log_dir / f"dead-mans-switch-{date_str}.jsonl"
    jsonl_path.write_text("", encoding="utf-8")

    # simulate the DMS writing a FLATTENED row for safe-2 partway through the observation.
    fake_clock = {"t": 0.0}

    def fake_time():
        fake_clock["t"] += 1.0
        if fake_clock["t"] == 3.0:
            with jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"arm": "safe-2", "action": "FLATTENED"}) + "\n")
        return fake_clock["t"]

    sleeps = []
    broker = _FakeBroker(flat_after_calls=3)

    row = drill.observe_one_kill(
        creds={"key": "k", "secret": "s", "base_url": "https://x"},
        kill_ts=0.0,
        position_before=[{"symbol": "SPY260903C00650000", "qty": "3"}],
        poll_interval_s=1, max_observe_s=30,
        sleep_fn=sleeps.append, time_fn=fake_time,
        broker=broker,
    )
    assert row["first_dms_action"] == "FLATTENED"
    assert row["outcome"] in ("PASS", "FAIL")
    assert row["time_to_flat_s"] is not None
    assert row["flat_ts_offset_s"] is not None


def test_observe_one_kill_times_out_never_flat(monkeypatch):
    monkeypatch.setattr(drill, "et_now", lambda: __import__("datetime").datetime(2026, 9, 5, 10, 0, 0))
    fake_clock = {"t": 0.0}

    def fake_time():
        fake_clock["t"] += 5.0
        return fake_clock["t"]

    broker = _FakeBroker(flat_after_calls=999)  # never flat
    row = drill.observe_one_kill(
        creds={"key": "k", "secret": "s", "base_url": "https://x"},
        kill_ts=0.0, position_before=[],
        poll_interval_s=1, max_observe_s=20,
        sleep_fn=lambda s: None, time_fn=fake_time,
        broker=broker,
    )
    assert row["outcome"] == "FAIL"
    assert row["time_to_flat_s"] is None


# --------------------------------------------------------------------------------------- #
# 5. run_arm aborts cleanly on a refusal (no kill_fn call)
# --------------------------------------------------------------------------------------- #
def test_run_arm_aborts_without_confirm_env(monkeypatch):
    monkeypatch.delenv(drill.CONFIRM_ENV, raising=False)
    monkeypatch.setattr(drill, "read_state", lambda: _base_state())
    monkeypatch.setattr(drill, "_today_et_date", lambda: TODAY)

    kill_calls = []
    result = drill.run_arm(
        kills=5, min_gap_min=1, accept_bold_flatten=False,
        sleep_fn=lambda s: None, time_fn=lambda: 0.0,
        kill_fn=lambda: kill_calls.append(1),
    )
    assert result["aborted_at_kill"] == 1
    assert kill_calls == []
