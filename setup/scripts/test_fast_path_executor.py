"""Tests for fast_path_executor — pure-Python sub-30s decision engine.

Verifies:
  - Each filter passes/fails as expected (RTH, VIX, setup, lock, kill, sizing)
  - End-to-end happy path produces ENTER decision with correct strike/qty
  - Synthetic latency stays under 5s per evaluation
  - Observer mode never writes orders (read-only Alpaca calls)
  - setups_allowed=["ALL"] sentinel handled
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="module")
def fpe():
    spec = importlib.util.spec_from_file_location(
        "fpe", Path(__file__).parent / "fast_path_executor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fpe"] = mod
    spec.loader.exec_module(mod)
    return mod


def _synthetic_alert(bias: str = "bullish", pattern: str = "failed_breakdown_wick::contra_regime") -> dict:
    return {
        "fire_at_utc": datetime.now(timezone.utc).isoformat(),
        "pattern": pattern,
        "bias": bias,
        "confidence": 0.75,
        "key_price": 735.0,
        "spy_close": 735.40,
        "level_distance_dollars": 0.10,
        "level_name": "PML",
    }


def _stub_account_info(equity: float = 1000.0, last_equity: float = 1000.0,
                       buying_power: float = 4000.0) -> dict:
    return {
        "equity": str(equity),
        "last_equity": str(last_equity),
        "buying_power": str(buying_power),
    }


def test_decision_dataclass_default_state(fpe):
    d = fpe.Decision(decision="HOLD", reason="default", account="safe")
    assert d.elapsed_ms == 0
    assert d.placed is False
    assert d.mode == "observer"


def test_skip_rth_outside_market_hours(fpe):
    """Outside RTH -> SKIP_RTH, no Alpaca calls made."""
    alert = _synthetic_alert()
    # Force outside RTH
    with patch.object(fpe, "_is_rth_now", return_value=False):
        d = fpe.evaluate_alert("safe", alert, vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_RTH"
    assert "outside RTH" in d.reason


def test_skip_outside_entry_window(fpe):
    """RTH=True but outside 09:35-15:00 entry window -> SKIP_RTH."""
    alert = _synthetic_alert()
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=False):
        d = fpe.evaluate_alert("safe", alert, vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_RTH"
    assert "outside entry window" in d.reason


def test_skip_vix_bull_blocked_by_high_vix(fpe):
    """Bullish alert + VIX > bull threshold + not falling -> SKIP_VIX."""
    alert = _synthetic_alert(bias="bullish")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True):
        d = fpe.evaluate_alert("safe", alert, vix_data={"value": 19.0, "direction": "rising"})
    assert d.decision == "SKIP_VIX"
    assert "blocks bull" in d.reason


def test_skip_vix_bear_needs_rising(fpe):
    """Bearish alert + VIX > bear_min but FLAT -> SKIP_VIX."""
    alert = _synthetic_alert(bias="bearish", pattern="rejection_at_level_bearish")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True):
        d = fpe.evaluate_alert("safe", alert, vix_data={"value": 19.0, "direction": "flat"})
    assert d.decision == "SKIP_VIX"
    assert "blocks bear" in d.reason


def test_skip_vix_unavailable_blocks(fpe):
    """If VIX fetch returned None, block conservatively."""
    alert = _synthetic_alert()
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_fetch_vix_quick", return_value=None):
        d = fpe.evaluate_alert("safe", alert)
    assert d.decision == "SKIP_VIX"
    assert "unavailable" in d.reason


def test_bull_passes_vix_when_below_threshold(fpe):
    """VIX 16, falling -> bull passes VIX. Continues to next filter."""
    alert = _synthetic_alert(bias="bullish")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16.0, "direction": "falling"})
    assert d.decision == "ENTER_BULL"
    assert d.filter_results["vix"] == "pass_bull"


def test_skip_setup_pattern_not_allowed(fpe):
    """momentum_acceleration has no archetype mapping -> SKIP_SETUP on Bold."""
    alert = _synthetic_alert(pattern="momentum_acceleration")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True):
        d = fpe.evaluate_alert("bold", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_SETUP"


def test_setups_allowed_all_accepts_mapped_setup(fpe):
    """Bold profile has setups_allowed=['ALL'] -> double_top maps to BEARISH_..., passes."""
    alert = _synthetic_alert(bias="bearish", pattern="double_top")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        d = fpe.evaluate_alert("bold", alert,
                                vix_data={"value": 18.0, "direction": "rising"})
    # Bold profile should accept double_top via ALL sentinel
    assert d.decision == "ENTER_BEAR"
    assert "via_ALL" in d.filter_results.get("setup", "")


def test_first_entry_lock_blocks_after_stop(fpe, tmp_path, monkeypatch):
    """If a prior trade today exited via stop, block re-entry."""
    today = datetime.now(fpe.ET_TZ).date().isoformat()
    loop_state = {
        "first_entry_lock": [{
            "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
            "entered_at_et": f"{today}T09:50",
            "exited_at_et": f"{today}T10:06",
            "exit_reason": "premium_stop",
        }],
    }
    state_path = tmp_path / "loop-state.json"
    state_path.write_text(json.dumps(loop_state))

    def _fake_load_loop():
        return loop_state

    alert = _synthetic_alert(bias="bullish", pattern="failed_breakdown_wick")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_loop_state", _fake_load_loop), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_LOCK"
    assert "first_entry_after_stop" in d.reason


def test_kill_switch_blocks_when_breached(fpe):
    """Account down -35% vs last_equity (safe threshold -30%) -> SKIP_KILL."""
    alert = _synthetic_alert()
    breached_info = {"equity": "650", "last_equity": "1000", "buying_power": "2000"}
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=breached_info):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_KILL"
    assert "kill-switch" in d.reason


def test_happy_path_enter_bull_with_strike_and_qty(fpe):
    """Full filter pipeline passes -> ENTER_BULL with strike + qty + stop + tp1."""
    alert = _synthetic_alert(bias="bullish")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info(equity=1000)):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16.0, "direction": "falling"})
    assert d.decision == "ENTER_BULL"
    assert d.proposed_strike is not None
    assert d.proposed_qty >= 3  # min contracts rule 6
    assert d.proposed_stop_premium is not None
    assert d.proposed_tp1_premium is not None
    # Bull premium_stop_pct=-0.08 from params_safe -> stop = 1.0 * 0.92 = 0.92
    assert d.proposed_stop_premium == 0.92
    # TP1 premium_pct=0.30 -> tp1 = 1.30
    assert d.proposed_tp1_premium == 1.30


def test_elapsed_ms_under_5sec(fpe):
    """Single-decision wall time must be under 5s (mocked deps)."""
    alert = _synthetic_alert()
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        started = time.monotonic()
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
        wall_ms = int((time.monotonic() - started) * 1000)
    assert wall_ms < 5000
    assert d.elapsed_ms < 5000


def test_observer_mode_does_not_place_orders(fpe):
    """Default mode=observer -> placed=False, no Alpaca POST."""
    alert = _synthetic_alert()
    call_log = []

    def _logging_alpaca(endpoint, account, method="GET", data=None, timeout=5):
        call_log.append((endpoint, method))
        return _stub_account_info()

    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", side_effect=_logging_alpaca):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.placed is False
    # Verify no POST (order placement) was attempted
    posts = [c for c in call_log if c[1] == "POST"]
    assert posts == []


def test_live_enabled_sentinel_absent(fpe, tmp_path, monkeypatch):
    """Without sentinel file, _live_enabled() returns False."""
    fake_state = tmp_path / "automation" / "state"
    fake_state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    assert fpe._live_enabled() is False


def test_live_enabled_sentinel_present(fpe, tmp_path, monkeypatch):
    """With sentinel file, _live_enabled() returns True."""
    fake_state = tmp_path / "automation" / "state"
    fake_state.mkdir(parents=True, exist_ok=True)
    (fake_state / "fast-path-live-enabled.flag").write_text("ratified by J 2026-xx-xx")
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    assert fpe._live_enabled() is True


def test_persist_decision_writes_jsonl(fpe, tmp_path, monkeypatch):
    """_persist_decision appends to fast-path-decisions.jsonl."""
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    d = fpe.Decision(decision="ENTER_BULL", reason="test", account="safe",
                     alert_pattern="failed_breakdown_wick", proposed_strike=735,
                     proposed_qty=3, elapsed_ms=42)
    out = fpe._persist_decision(d)
    assert out.exists()
    line = out.read_text().strip()
    rec = json.loads(line)
    assert rec["decision"] == "ENTER_BULL"
    assert rec["proposed_strike"] == 735
    assert rec["elapsed_ms"] == 42


def test_alert_pattern_strip_contra_regime(fpe):
    """`::contra_regime` suffix should not break setup mapping."""
    alert = _synthetic_alert(pattern="failed_breakdown_wick::contra_regime")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "ENTER_BULL"


# =====================================================================
# LIVE-MODE SAFETY GATES (Option A — J's 2026-05-18 evening ratification)
# =====================================================================

def test_resolve_option_symbol_call(fpe):
    """Bullish bias -> C in OPRA symbol."""
    sym = fpe._resolve_option_symbol("safe", 740, "bullish")
    assert sym is not None
    assert "C" in sym
    assert sym.endswith("00740000")


def test_resolve_option_symbol_put(fpe):
    """Bearish bias -> P in OPRA symbol."""
    sym = fpe._resolve_option_symbol("bold", 734, "bearish")
    assert sym is not None
    assert "P" in sym
    assert sym.endswith("00734000")


def test_place_live_bracket_rejects_non_enter(fpe):
    """Decisions that aren't ENTER_* must be refused."""
    d = fpe.Decision(decision="SKIP_VIX", reason="VIX", account="safe")
    success, order_id, err = fpe._place_live_bracket("safe", d)
    assert success is False
    assert order_id is None
    assert "not ENTER" in err


def test_place_live_bracket_rejects_missing_prices(fpe):
    """Decision missing strike/qty must be refused."""
    d = fpe.Decision(decision="ENTER_BULL", reason="ok", account="safe",
                     proposed_strike=None, proposed_qty=None)
    success, order_id, err = fpe._place_live_bracket("safe", d)
    assert success is False
    assert "missing" in err


def test_place_live_bracket_respects_daily_cap(fpe, tmp_path, monkeypatch):
    """If account has already fired LIVE_DAILY_FIRE_CAP times today, refuse."""
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fpe, "LIVE_FIRE_COUNTER_FILE",
                        tmp_path / "fast-path-live-fires.json")
    today = datetime.now(fpe.ET_TZ).date().isoformat()
    state_path = tmp_path / "fast-path-live-fires.json"
    state_path.write_text(json.dumps({today: {"safe": fpe.LIVE_DAILY_FIRE_CAP}}))

    d = fpe.Decision(decision="ENTER_BULL", reason="ok", account="safe",
                     alert_bias="bullish", proposed_strike=740,
                     proposed_qty=3, proposed_premium=1.0,
                     proposed_stop_premium=0.92, proposed_tp1_premium=1.30)
    success, order_id, err = fpe._place_live_bracket("safe", d)
    assert success is False
    assert "daily fire cap" in err


def test_place_live_bracket_happy_path(fpe, tmp_path, monkeypatch):
    """All gates pass + Alpaca returns order_id -> success."""
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fpe, "LIVE_FIRE_COUNTER_FILE",
                        tmp_path / "fast-path-live-fires.json")
    fake_resp = {"id": "abc-order-id-123", "symbol": "test", "status": "new"}
    with patch.object(fpe, "_alpaca", return_value=fake_resp):
        d = fpe.Decision(decision="ENTER_BULL", reason="ok", account="safe",
                         alert_bias="bullish", proposed_strike=740,
                         proposed_qty=3, proposed_premium=1.0,
                         proposed_stop_premium=0.92, proposed_tp1_premium=1.30)
        success, order_id, err = fpe._place_live_bracket("safe", d)
    assert success is True
    assert order_id == "abc-order-id-123"
    assert err is None
    # Counter should have incremented to 1
    assert fpe._live_fires_today("safe") == 1


def test_place_live_bracket_alpaca_rejection(fpe, tmp_path, monkeypatch):
    """If Alpaca returns error, surface it without bumping counter."""
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fpe, "LIVE_FIRE_COUNTER_FILE",
                        tmp_path / "fast-path-live-fires.json")
    err_resp = {"_error": "403", "_status": 403,
                "_body": {"message": "insufficient buying power"}}
    with patch.object(fpe, "_alpaca", return_value=err_resp):
        d = fpe.Decision(decision="ENTER_BULL", reason="ok", account="safe",
                         alert_bias="bullish", proposed_strike=740,
                         proposed_qty=3, proposed_premium=1.0,
                         proposed_stop_premium=0.92, proposed_tp1_premium=1.30)
        success, order_id, err = fpe._place_live_bracket("safe", d)
    assert success is False
    assert "insufficient" in err
    # Counter should NOT have incremented
    assert fpe._live_fires_today("safe") == 0


def test_live_fires_counter_resets_per_day(fpe, tmp_path, monkeypatch):
    """Counter is keyed by ET date — yesterday's count doesn't bleed."""
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fpe, "LIVE_FIRE_COUNTER_FILE",
                        tmp_path / "fast-path-live-fires.json")
    yesterday = (datetime.now(fpe.ET_TZ).date() - timedelta(days=1)).isoformat()
    (tmp_path / "fast-path-live-fires.json").write_text(
        json.dumps({yesterday: {"safe": 99}})
    )
    # Yesterday had 99 fires but today should read 0
    assert fpe._live_fires_today("safe") == 0


# =====================================================================
# CONCURRENT POSITION SAFEGUARD (J 2026-05-18 chat — "one trade at a time")
# =====================================================================

def test_no_concurrent_position_blocks_when_local_state_open(fpe):
    """If current-position-{account}.json shows status=open, BLOCK new entry."""
    alert = _synthetic_alert(bias="bullish")
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_position_state",
                       return_value={"status": "open", "symbol": "SPY260518C00740000", "qty": 3}), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_LOCK"
    assert "concurrent position blocked" in d.reason


def test_no_concurrent_position_blocks_when_local_state_pending_fill(fpe):
    """status=pending_fill (parent placed, awaiting fill) also blocks."""
    alert = _synthetic_alert()
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_position_state",
                       return_value={"status": "pending_fill", "symbol": "SPY260518C00740000"}), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_LOCK"


def test_no_concurrent_position_blocks_when_alpaca_has_position(fpe):
    """Even if local state says flat, Alpaca REST showing a position blocks."""
    alert = _synthetic_alert()
    call_log = []

    def _stub_alpaca(endpoint, account, method="GET", data=None, timeout=5):
        call_log.append(endpoint)
        if endpoint == "account":
            return _stub_account_info()
        if "positions" in endpoint:
            return [{"symbol": "SPY260518C00740000", "qty": "3"}]
        if "orders" in endpoint:
            return []
        return {}

    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_position_state", return_value={"status": None}), \
         patch.object(fpe, "_alpaca", side_effect=_stub_alpaca):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_LOCK"
    assert "alpaca_rest" in d.reason


def test_no_concurrent_position_blocks_when_pending_alpaca_order(fpe):
    """Alpaca pending buy order for SPY option blocks new entry."""
    alert = _synthetic_alert()
    def _stub_alpaca(endpoint, account, method="GET", data=None, timeout=5):
        if endpoint == "account":
            return _stub_account_info()
        if "positions" in endpoint:
            return []
        if "orders" in endpoint:
            return [{"symbol": "SPY260518P00734000", "side": "buy", "status": "new"}]
        return {}

    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_position_state", return_value={"status": None}), \
         patch.object(fpe, "_alpaca", side_effect=_stub_alpaca):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_LOCK"
    assert "alpaca_pending_orders" in d.reason


def test_no_concurrent_position_recent_fire_cooldown(fpe):
    """Recent ENTER placement within 90s blocks new entry (eventual-consistency)."""
    fake_recent = {
        "decided_at_utc": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
        "decided_at_et": "2026-05-19T09:30:30-04:00",
        "account": "safe",
        "decision": "ENTER_BULL",
        "placed": True,
        "bracket_order_id": "abc-123",
    }
    alert = _synthetic_alert()

    def _stub_alpaca(endpoint, account, method="GET", data=None, timeout=5):
        if endpoint == "account":
            return _stub_account_info()
        if "positions" in endpoint:
            return []
        if "orders" in endpoint:
            return []
        return {}

    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_position_state", return_value={"status": None}), \
         patch.object(fpe, "_recent_fast_path_fire", return_value=fake_recent), \
         patch.object(fpe, "_alpaca", side_effect=_stub_alpaca):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    assert d.decision == "SKIP_LOCK"
    assert "recent fast-path fire" in d.reason


def test_no_concurrent_position_passes_when_flat(fpe):
    """Flat account + no pending + no recent fire -> filter passes."""
    alert = _synthetic_alert()
    def _stub_alpaca(endpoint, account, method="GET", data=None, timeout=5):
        if endpoint == "account":
            return _stub_account_info()
        if "positions" in endpoint:
            return []
        if "orders" in endpoint:
            return []
        return {}

    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_load_position_state", return_value={"status": None}), \
         patch.object(fpe, "_alpaca", side_effect=_stub_alpaca):
        d = fpe.evaluate_alert("safe", alert,
                                vix_data={"value": 16, "direction": "falling"})
    # Should reach ENTER_BULL (all filters pass)
    assert d.decision == "ENTER_BULL"
    assert d.filter_results.get("concurrent_position") == "pass"


def test_main_does_not_place_without_sentinel(fpe, tmp_path, monkeypatch):
    """Even with --mode live, no sentinel file = no placement."""
    monkeypatch.setattr(fpe, "PROJECT_ROOT", tmp_path)
    # Create an alert file but no sentinel
    alert_dir = tmp_path / "automation" / "state"
    alert_dir.mkdir(parents=True)
    alert_file = alert_dir / "numeric-alert.jsonl"
    alert_file.write_text(json.dumps(_synthetic_alert()) + "\n")
    monkeypatch.setattr(fpe, "_read_latest_alert", lambda **k: _synthetic_alert())
    # Sentinel deliberately not created
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=_stub_account_info()), \
         patch.object(sys, "argv", ["fpe", "--mode", "live", "--silent"]):
        rc = fpe.main()
    # No placement attempted — sentinel absent
    # Counter file should not exist
    assert not (tmp_path / "fast-path-live-fires.json").exists()
