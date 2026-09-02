"""Guard for the duplicate-tick monitor (B3-monitors, 2026-09-01).

The audit flagged the fire-and-forget wrapper as CRITICAL: it can start a second
heartbeat_core invocation before the first exits, defeating heartbeat_core's own
overlap guard (heartbeat_core.py is on the FROZEN_TRADING_PATH, frozen until
2026-09-29 -- this monitor is the $0 read-only visibility fix that does NOT touch it).
None seen since 2026-08-15; `check_duplicate_ticks` makes any recurrence visible by
tail-reading core-decisions.jsonl and flagging any (account, minute) with more than one
distinct core_tick_id.

Pins:
  - a clean synthetic ledger (one tick per account per minute) -> GREEN
  - 1-2 duplicate minutes -> YELLOW
  - >=3 duplicate minutes -> RED
  - the check is NON-CRITICAL (critical=False) -- it must never trade-halt
  - scoping is to the LAST TRADING DAY present in the tail, not the whole file
  - RED-PROOF: neutering the >1-distinct-tick comparison to >=1 flips a clean ledger
    RED, proving the assertion is load-bearing (not a vacuous always-GREEN check).
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_EH_PATH = _REPO / "setup" / "scripts" / "engine_health.py"
_spec = importlib.util.spec_from_file_location("engine_health_duptick_under_test", _EH_PATH)
engine_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine_health)


def _row(account: str, minute: str, tick: str, day: str = "2026-09-01") -> dict:
    return {
        "account": account,
        "ts_et": f"{day}T{minute}:00",
        "core_tick_id": tick,
    }


def _write_ledger(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


@pytest.fixture()
def clean_ledger(tmp_path, monkeypatch):
    state_dir = tmp_path
    p = state_dir / "core-decisions.jsonl"
    rows = []
    for i in range(5):
        minute = f"09:{30 + i:02d}"
        rows.append(_row("safe", minute, f"tick-{i}-safe"))
        rows.append(_row("bold", minute, f"tick-{i}-bold"))
    _write_ledger(p, rows)
    monkeypatch.setattr(engine_health, "STATE", p.parent)
    return p


def test_clean_ledger_is_green(clean_ledger):
    result = engine_health.check_duplicate_ticks(datetime(2026, 9, 1, 15, 0, 0))
    assert result["status"] == "GREEN"
    assert result["critical"] is False
    assert result["name"] == "duplicate_ticks"


def test_one_duplicate_minute_is_yellow(tmp_path, monkeypatch):
    p = tmp_path / "core-decisions.jsonl"
    rows = [
        _row("safe", "09:30", "tick-a"),
        _row("safe", "09:30", "tick-b"),  # duplicate minute for safe
        _row("bold", "09:31", "tick-c"),
    ]
    _write_ledger(p, rows)
    monkeypatch.setattr(engine_health, "STATE", p.parent)
    result = engine_health.check_duplicate_ticks(datetime(2026, 9, 1, 15, 0, 0))
    assert result["status"] == "YELLOW"
    assert result["critical"] is False
    assert "safe@2026-09-01T09:30" in result["detail"]


def test_three_duplicate_minutes_is_red(tmp_path, monkeypatch):
    p = tmp_path / "core-decisions.jsonl"
    rows = []
    for i in range(3):
        minute = f"09:{30 + i:02d}"
        rows.append(_row("safe", minute, f"tick-{i}a"))
        rows.append(_row("safe", minute, f"tick-{i}b"))
    _write_ledger(p, rows)
    monkeypatch.setattr(engine_health, "STATE", p.parent)
    result = engine_health.check_duplicate_ticks(datetime(2026, 9, 1, 15, 0, 0))
    assert result["status"] == "RED"


def test_scoped_to_last_trading_day_only(tmp_path, monkeypatch):
    """A duplicate on a PRIOR day sitting in the tail window must not pollute today's
    verdict -- only the newest ts_et date present is scored."""
    p = tmp_path / "core-decisions.jsonl"
    rows = [
        _row("safe", "09:30", "old-a", day="2026-08-29"),
        _row("safe", "09:30", "old-b", day="2026-08-29"),  # dup on an OLD day
        _row("safe", "09:30", "new-a", day="2026-09-01"),  # clean on the last day
    ]
    _write_ledger(p, rows)
    monkeypatch.setattr(engine_health, "STATE", p.parent)
    result = engine_health.check_duplicate_ticks(datetime(2026, 9, 1, 15, 0, 0))
    assert result["status"] == "GREEN"
    assert "2026-09-01" in result["detail"]


def test_missing_ledger_fails_open_yellow(tmp_path, monkeypatch):
    p = tmp_path / "does-not-exist.jsonl"
    monkeypatch.setattr(engine_health, "STATE", p.parent)
    result = engine_health.check_duplicate_ticks(datetime(2026, 9, 1, 15, 0, 0))
    assert result["status"] == "YELLOW"
    assert result["critical"] is False


def test_red_proof_neutered_dup_detection_flips_clean_ledger(clean_ledger):
    """RED-PROOF: break the mechanism (treat ANY tick, not just a DUPLICATE, as
    a violation) and confirm the clean-ledger test would then fail -- proving the
    len(v) > 1 comparison in check_duplicate_ticks is load-bearing."""
    import inspect
    src = inspect.getsource(engine_health.check_duplicate_ticks)
    assert "len(v) > 1" in src, "expected the exact >1-distinct-tick comparison"
    neutered = src.replace("len(v) > 1", "len(v) >= 1")
    assert neutered != src
    ns: dict = {}
    exec(compile(neutered, "<neutered>", "exec"), engine_health.__dict__, ns)
    broken_fn = ns["check_duplicate_ticks"]
    result = broken_fn(datetime(2026, 9, 1, 15, 0, 0))
    # every minute has exactly 1 tick per account, but >=1 always matches -> RED
    assert result["status"] != "GREEN", (
        "neutering len(v)>1 to len(v)>=1 should break the clean-ledger case (RED-PROOF)"
    )
