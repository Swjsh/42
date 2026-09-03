"""Guards for setup/scripts/recovery_drill_observer.py -- the RECOVERY DRILL observer
(work order 2c: "TV CDP dead + Alpaca REST 5xx + Windows restart mid-session, each once,
read-only observation of what the healers and DMS do"). This module must NEVER induce a
failure or mutate anything -- it only samples state and detects the first automated reaction
from fixture-style log/jsonl data. Covers:
  1. sampler schema (sample_once returns the documented keys)
  2. first-action detection from fixture logs, one case per scenario
  3. table rendering
  4. AST guard: no mutating call anywhere in the module
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location("recovery_drill_observer_g", SCRIPTS / "recovery_drill_observer.py")
obs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(obs)  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------- #
# 1. sampler schema
# --------------------------------------------------------------------------------------- #
def test_sample_once_returns_documented_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(obs, "LOG_DIR", tmp_path)
    monkeypatch.setattr(obs, "ENGINE_HEALTH_PATH", tmp_path / "engine-health.json")
    cursors = obs._TailCursors.__new__(obs._TailCursors)
    cursors.date_str = "2026-09-05"
    cursors.tv_watchdog_log = tmp_path / "tv-watchdog-2026-09-05.log"
    cursors.engine_heal_log = tmp_path / "engine-heal-2026-09-05.log"
    cursors.dms_jsonl = tmp_path / "dead-mans-switch-2026-09-05.jsonl"
    cursors.tv_off = 0
    cursors.heal_off = 0
    cursors.dms_off = 0

    monkeypatch.setattr(obs, "check_port", lambda h, p, timeout=1.0: False)
    monkeypatch.setattr(obs._dms, "core_liveness_minutes", lambda account, now: 3.0)
    monkeypatch.setattr(obs, "_query_task_state", lambda name: {"State": "Ready"})

    sample = obs.sample_once(cursors, ts_offset_s=12.3, creds_all={})
    expected_keys = {
        "ts_offset_s", "ts_et", "tv_cdp_port_open", "heartbeat_liveness_min",
        "engine_health", "heartbeat_task", "tv_watchdog_new_lines",
        "engine_heal_new_lines", "dms_new_rows", "broker_probe_ok", "broker_probe_status",
    }
    assert expected_keys.issubset(sample.keys())
    assert sample["ts_offset_s"] == 12.3
    assert sample["tv_cdp_port_open"] is False
    assert sample["heartbeat_liveness_min"] == {"safe": 3.0, "bold": 3.0}


# --------------------------------------------------------------------------------------- #
# 2. first-action detection from fixture logs
# --------------------------------------------------------------------------------------- #
def test_detect_tv_cdp_relaunch():
    samples = [
        {"ts_offset_s": 0.0, "tv_watchdog_new_lines": []},
        {"ts_offset_s": 10.0, "tv_watchdog_new_lines": ["2026-09-05 10:00:00 ET RELAUNCH_KILL TV pid=1234 CDP dead"]},
        {"ts_offset_s": 20.0, "tv_watchdog_new_lines": []},
    ]
    action = obs.detect_first_action("tv_cdp_dead", samples)
    assert action is not None
    assert action["action"] == "TV_RELAUNCH"
    assert action["ts_offset_s"] == 10.0


def test_detect_tv_cdp_relaunch_failed_distinguished():
    samples = [
        {"ts_offset_s": 5.0, "tv_watchdog_new_lines": ["RELAUNCH_KILL_FAILED CDP still unreachable"]},
    ]
    action = obs.detect_first_action("tv_cdp_dead", samples)
    assert action["action"] == "TV_RELAUNCH_FAILED"


def test_detect_tv_cdp_no_signal_yet():
    samples = [{"ts_offset_s": 0.0, "tv_watchdog_new_lines": []}]
    assert obs.detect_first_action("tv_cdp_dead", samples) is None


def test_detect_alpaca_5xx_via_dms_read_failed():
    samples = [
        {"ts_offset_s": 0.0, "dms_new_rows": [], "engine_health": None, "broker_probe_ok": True},
        {"ts_offset_s": 30.0, "dms_new_rows": [{"arm": "safe-2", "action": "READ_FAILED"}],
         "engine_health": None, "broker_probe_ok": True},
    ]
    action = obs.detect_first_action("alpaca_5xx", samples)
    assert action["action"] == "DMS_READ_FAILED"
    assert action["ts_offset_s"] == 30.0


def test_detect_alpaca_5xx_via_engine_health_red():
    samples = [
        {"ts_offset_s": 15.0, "dms_new_rows": [], "broker_probe_ok": True,
         "engine_health": {"verdict": "RED", "red_checks": ["alpaca_broker_reachable"]}},
    ]
    action = obs.detect_first_action("alpaca_5xx", samples)
    assert action["action"] == "ENGINE_HEALTH_RED_BROKER"


def test_detect_alpaca_5xx_via_broker_probe_fallback():
    samples = [
        {"ts_offset_s": 8.0, "dms_new_rows": [], "engine_health": None,
         "broker_probe_ok": False, "broker_probe_status": 503},
    ]
    action = obs.detect_first_action("alpaca_5xx", samples)
    assert action["action"] == "BROKER_PROBE_FAILED_OBSERVED"


def test_detect_windows_restart_resumed_ticking():
    samples = [
        {"ts_offset_s": 0.0, "heartbeat_liveness_min": {"safe": None, "bold": None}, "engine_heal_new_lines": []},
        {"ts_offset_s": 10.0, "heartbeat_liveness_min": {"safe": None, "bold": None}, "engine_heal_new_lines": []},
        {"ts_offset_s": 20.0, "heartbeat_liveness_min": {"safe": 1.2, "bold": None}, "engine_heal_new_lines": []},
    ]
    action = obs.detect_first_action("windows_restart", samples)
    assert action["action"] == "ENGINE_RESUMED_TICKING"
    assert action["ts_offset_s"] == 20.0


def test_detect_windows_restart_via_heal_engine_line():
    samples = [
        {"ts_offset_s": 5.0, "heartbeat_liveness_min": {"safe": None, "bold": None},
         "engine_heal_new_lines": ["HEALED 10:05: re-fired Gamma_HeartbeatCore (brain, confirmed dead)"]},
    ]
    action = obs.detect_first_action("windows_restart", samples)
    assert action["action"] == "HEAL_ENGINE_ACTED"


def test_detect_unknown_scenario_returns_none():
    assert obs.detect_first_action("not_a_real_scenario", [{"ts_offset_s": 0.0}]) is None


# --------------------------------------------------------------------------------------- #
# 3. table rendering
# --------------------------------------------------------------------------------------- #
def test_write_scenario_md_renders_first_action(tmp_path):
    samples = [
        {"ts_offset_s": 0.0, "tv_cdp_port_open": False, "heartbeat_liveness_min": {"safe": 1.0, "bold": 1.0},
         "engine_health": {"verdict": "GREEN"}, "tv_watchdog_new_lines": []},
        {"ts_offset_s": 10.0, "tv_cdp_port_open": True, "heartbeat_liveness_min": {"safe": 1.1, "bold": 1.1},
         "engine_health": {"verdict": "GREEN"},
         "tv_watchdog_new_lines": ["RELAUNCH_FRESH no TV process and CDP dead - launching"]},
    ]
    md_path = tmp_path / "out.md"
    obs._write_scenario_md("tv_cdp_dead", samples, md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "TV_RELAUNCH" in text
    assert "+10.0s" in text
    assert "| 0.0 |" in text and "| 10.0 |" in text


def test_write_scenario_md_no_signal_says_so(tmp_path):
    samples = [{"ts_offset_s": 0.0, "tv_cdp_port_open": True, "heartbeat_liveness_min": {},
                "engine_health": None, "tv_watchdog_new_lines": []}]
    md_path = tmp_path / "out.md"
    obs._write_scenario_md("tv_cdp_dead", samples, md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "none observed" in text


# --------------------------------------------------------------------------------------- #
# 4. AST guard: no mutating call anywhere in the module
# --------------------------------------------------------------------------------------- #
MUTATING_VERBS = {
    "place_bracket", "place_option_order", "place_stock_order", "place_crypto_order",
    "market_sell", "close_all_spy_options", "replace_order_by_id", "replace_stop_order",
    "cancel_order", "cancel_all_orders", "Stop-Process", "Start-ScheduledTask",
    "Stop-ScheduledTask", "Disable-ScheduledTask", "Enable-ScheduledTask",
}


def test_no_mutating_call_anywhere_in_module():
    src = (SCRIPTS / "recovery_drill_observer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits = [
        (n.lineno, n.func.attr) for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in MUTATING_VERBS
    ]
    assert hits == [], f"mutating call(s) found in the recovery observer module: {hits}"

    # Also scan for the PowerShell-side verbs as string literals (they're invoked as
    # subprocess.run([...]) argv strings, not python attribute calls).
    ps_mutating_literals = {"Start-ScheduledTask", "Stop-ScheduledTask",
                             "Disable-ScheduledTask", "Enable-ScheduledTask", "Stop-Process"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            for verb in ps_mutating_literals:
                assert verb not in n.value, (
                    f"line {n.lineno}: mutating PowerShell verb '{verb}' found in a string "
                    "literal -- this module must stay read-only"
                )


def test_only_broker_calls_are_reads():
    ALLOWED = {"load_creds", "_request"}
    src = (SCRIPTS / "recovery_drill_observer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "fleet_broker"):
            assert n.func.attr in ALLOWED, (
                f"line {n.lineno}: fleet_broker.{n.func.attr} is not an allowed read-only call"
            )
