"""VISIBILITY (2026-07-09, OP-33c/STOP-B first-live-day): the 'EXIT MODE' line on the two
glance surfaces (gamma_status.py + gamma_glance.py) -- "EXIT MODE: structure (SS-B) since
2026-07-09; positions open under structure: N; last structure exit: <ts or none>". Builds a
deterministic fixture (tmp STATE dir) so the count/timestamp-picking logic is pinned, not
just eyeballed against today's live files.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

ACCOUNTS_FIXTURE = {
    "arms": [
        {"id": "safe-2", "instrument": "SPY_0DTE_OPTION"},
        {"id": "safe-1", "instrument": "SPY_0DTE_OPTION"},
        {"id": "mes-linear-sim", "instrument": "MES_FUTURES"},  # must be excluded (not SPY 0DTE)
    ]
}


def _seed(tmp_path: Path, *, structure_open: bool, last_exit_row: dict | None,
         safe_flag: bool = True, bold_flag: bool = True):
    (tmp_path / "fleet" / "safe-2").mkdir(parents=True)
    (tmp_path / "fleet" / "safe-1").mkdir(parents=True)
    (tmp_path / "fleet" / "safe-1" / "exit-state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "aggressive").mkdir(parents=True)
    (tmp_path / "fleet" / "accounts.json").write_text(json.dumps(ACCOUNTS_FIXTURE), encoding="utf-8")
    (tmp_path / "params.json").write_text(json.dumps({"structure_stop_enabled": safe_flag}), encoding="utf-8")
    (tmp_path / "aggressive" / "params.json").write_text(
        json.dumps({"structure_stop_enabled": bold_flag}), encoding="utf-8")
    est = {}
    if structure_open:
        est["SPY260709P00747000"] = {"stop_mode": "structure", "trigger_level": 747.41}
    (tmp_path / "fleet" / "safe-2" / "exit-state.json").write_text(json.dumps(est), encoding="utf-8")
    core_lines = []
    if last_exit_row is not None:
        core_lines.append(json.dumps(last_exit_row))
    (tmp_path / "core-decisions.jsonl").write_text("\n".join(core_lines) + ("\n" if core_lines else ""),
                                                    encoding="utf-8")
    (tmp_path / "fleet" / "safe-1" / "decisions.jsonl").write_text("", encoding="utf-8")


def _structure_exit_row(ts: str, symbol: str, level: float) -> dict:
    return {"ts_et": ts, "account": "safe",
            "exit_pass": [{"symbol": symbol, "trigger_level": level,
                          "actions": [{"kind": "SELL_ALL", "stage": "structure_stop",
                                      "reason": f"structure_stop @ {level}"}]}]}


def test_gamma_status_exit_mode_none_yet(tmp_path, monkeypatch):
    gs = importlib.import_module("gamma_status")
    monkeypatch.setattr(gs, "STATE", tmp_path)
    _seed(tmp_path, structure_open=False, last_exit_row=None)
    fa = gs._j(tmp_path / "fleet" / "accounts.json")
    line = gs._structure_stop_glance(fa)
    assert "EXIT MODE: structure (SS-B) since 2026-07-09" in line
    assert "[safe=ON bold=ON]" in line
    assert "positions open under structure: 0" in line
    assert "last structure exit: none" in line


def test_gamma_status_exit_mode_counts_open_and_last_exit(tmp_path, monkeypatch):
    gs = importlib.import_module("gamma_status")
    monkeypatch.setattr(gs, "STATE", tmp_path)
    row = _structure_exit_row("2026-07-09T11:05:00", "SPY260709P00745000", 745.0)
    _seed(tmp_path, structure_open=True, last_exit_row=row)
    fa = gs._j(tmp_path / "fleet" / "accounts.json")
    line = gs._structure_stop_glance(fa)
    assert "positions open under structure: 1" in line
    assert "last structure exit: 2026-07-09T11:05:00 SPY260709P00745000" in line


def test_gamma_status_exit_mode_flag_off_rendered(tmp_path, monkeypatch):
    gs = importlib.import_module("gamma_status")
    monkeypatch.setattr(gs, "STATE", tmp_path)
    _seed(tmp_path, structure_open=False, last_exit_row=None, safe_flag=False, bold_flag=True)
    fa = gs._j(tmp_path / "fleet" / "accounts.json")
    line = gs._structure_stop_glance(fa)
    assert "[safe=OFF bold=ON]" in line


def test_gamma_glance_exit_mode_block_matches(tmp_path, monkeypatch):
    gg = importlib.import_module("gamma_glance")
    monkeypatch.setattr(gg, "STATE", tmp_path)
    row = _structure_exit_row("2026-07-09T11:05:00", "SPY260709P00745000", 745.0)
    _seed(tmp_path, structure_open=True, last_exit_row=row)
    lines = gg._structure_stop()
    assert len(lines) == 1
    assert "positions open under structure: 1" in lines[0]
    assert "last structure exit: 2026-07-09T11:05:00 SPY260709P00745000" in lines[0]
    lines[0].encode("ascii")  # must stay console-safe (PS 5.1 / cp1252)


def test_gamma_glance_build_includes_exit_mode_section(tmp_path, monkeypatch):
    """End-to-end: the full build() output carries the EXIT MODE header + line, and the
    whole page still round-trips through ASCII (the existing guard's load-bearing check)."""
    gg = importlib.import_module("gamma_glance")
    monkeypatch.setattr(gg, "STATE", tmp_path)
    _seed(tmp_path, structure_open=False, last_exit_row=None)
    # build() also touches several OTHER state files (self-check, core-decisions, etc.) that
    # _seed doesn't create -- every reader in this module is fail-open on a missing file, so
    # an empty/absent source degrades that section's text rather than raising.
    text = gg.build()
    assert "EXIT MODE" in text
    assert "structure (SS-B) since 2026-07-09" in text
    text.encode("ascii")
