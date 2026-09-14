"""Guards for the Station loop's 'game detected -> free the GPU now' behaviour (J 2026-09-13: "I need an
off switch or a gaming mode switch or both so I can use all my GPU"; 17:0x ET Apex Legends on the RTX
5080 dropped local prefill to ~25 tok/s while the 13 GB planner stayed resident).

Contract pinned here:
  * a denylisted process (game / launcher) is checked BEFORE the GPU-utilization rule, so the yield
    reason names the process and the loop unloads every loaded Ollama model on that fire;
  * a plain gpu_util yield (no denylisted process) does NOT unload -- the busy GPU may be another local
    fire mid-inference;
  * the unload helper fails open (returns []) when `ollama` is unavailable.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import station_loop  # noqa: E402

SUNDAY_EVENING_UTC = datetime(2026, 9, 13, 22, 0, tzinfo=timezone.utc)  # 18:00 ET Sunday, market closed
CONFIG = dict(station_loop.DEFAULT_CONFIG, yield_processes=["steam.exe", "r5apex_dx12.exe"])


@pytest.fixture(autouse=True)
def _no_real_side_effects(monkeypatch, tmp_path):
    """run_once() now scores the board and records an outcome on EVERY path (item 12); keep this suite
    off the real ledgers exactly like test_station_loop.py's autouse fixture does."""
    for name in ("IDEAS_BOARD_PATH", "BRIEF_PATH", "LEDGER_PATH", "INBOX_PATH", "INBOX_PROCESSED_PATH",
                 "PENDING_NOTES_PATH", "VERDICTS_LEDGER_PATH", "SETTLED_HYP_PATH"):
        if hasattr(station_loop, name):
            monkeypatch.setattr(station_loop, name, tmp_path / name.lower())
    if hasattr(station_loop, "AUTOPSY_DIR"):
        monkeypatch.setattr(station_loop, "AUTOPSY_DIR", tmp_path / "autopsies")
    if hasattr(station_loop, "conductor_outcome"):
        monkeypatch.setattr(station_loop.conductor_outcome, "record", lambda *a, **k: None, raising=False)


def _decide(gpu, table):
    return station_loop.decide_action(
        SUNDAY_EVENING_UTC, CONFIG, force=False,
        gpu_util_fn=lambda: gpu,
        process_table_fn=lambda: table,
        ollama_reachable_fn=lambda _url: True,
        station_mode_fn=lambda: "work",
    )


def test_denylisted_process_wins_over_gpu_util_in_the_reason():
    status, reason = _decide(99.0, {"1": r"C:\Program Files (x86)\Steam\steamapps\common\Apex Legends\r5apex_dx12.exe"})
    assert status == "yielded"
    assert reason.startswith("denylisted_process:r5apex_dx12.exe")


def test_gpu_util_alone_still_yields_without_naming_a_process():
    status, reason = _decide(99.0, {"1": r"C:\Windows\explorer.exe"})
    assert status == "yielded"
    assert reason.startswith("gpu_util 99%")


def test_run_once_unloads_models_only_on_a_denylisted_process(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(station_loop, "_unload_loaded_models", lambda: calls.append("unload") or ["gamma-planner-fast"])
    monkeypatch.setattr(station_loop, "load_config", lambda: CONFIG)
    monkeypatch.setattr(station_loop, "drain_inbox", lambda: None)
    monkeypatch.setattr(station_loop, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(station_loop, "_log", lambda *_a, **_k: None)

    monkeypatch.setattr(station_loop, "decide_action",
                        lambda *a, **k: ("yielded", "denylisted_process:r5apex_dx12.exe"))
    row = station_loop.run_once(now_utc=SUNDAY_EVENING_UTC, force=False)
    assert row["status"] == "yielded" and row["unloaded"] == ["gamma-planner-fast"]
    assert calls == ["unload"]

    monkeypatch.setattr(station_loop, "decide_action", lambda *a, **k: ("yielded", "gpu_util 99% > 50%"))
    row = station_loop.run_once(now_utc=SUNDAY_EVENING_UTC, force=False)
    assert row["status"] == "yielded" and "unloaded" not in row
    assert calls == ["unload"]


def test_unload_helper_fails_open_without_ollama(monkeypatch):
    def boom(*_a, **_k):
        raise FileNotFoundError("ollama")
    monkeypatch.setattr(station_loop.subprocess, "run", boom)
    assert station_loop._unload_loaded_models() == []


@pytest.mark.parametrize("name", ["r5apex_dx12.exe", "r5apex.exe"])
def test_default_denylist_names_the_game_j_plays(name):
    assert name in station_loop.DEFAULT_CONFIG["yield_processes"]


@pytest.mark.parametrize("name", ["steam.exe", "epicgameslauncher.exe", "riotclientservices.exe", "battle.net.exe"])
def test_default_denylist_excludes_idle_launchers(name):
    # 2026-09-13 20:05 ET (test premise changed on purpose, not weakened): Steam idling in the
    # tray kept every unforced fire in yield all evening (denylisted_process:steam.exe) while
    # the TV showed a frozen board. A launcher is not a game; gpu_util_yield_pct catches any
    # real game regardless of its name, so the default list names GAME executables only.
    assert name not in station_loop.DEFAULT_CONFIG["yield_processes"]

