"""Guard: quiet_mode never re-enables a task listed in quiet-mode-never-restore.json.

2026-09-05 (Saturday, J: "everything must be silent"): the 15:17 ET quiet-mode restore re-enabled
Gamma_CryptoTwin (replaced by a resident loop an hour earlier) and Gamma_TickersLane (turned off
pending J's decision), because quiet mode restores whatever it snapshotted as Ready, with no way
to say "this one stays off". This pins the exclusion at both the read and the write of the
restore list.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

qm = importlib.import_module("quiet_mode")


def _point(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qm, "RESTORE_FILE", tmp_path / "quiet-mode-restore.json")
    monkeypatch.setattr(qm, "NEVER_RESTORE_FILE", tmp_path / "quiet-mode-never-restore.json")
    monkeypatch.setattr(qm, "_log", lambda *_a, **_k: None)


def test_load_skips_never_restore_names(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    (tmp_path / "quiet-mode-restore.json").write_text(json.dumps({
        "restore_to_ready": ["Gamma_A", "Gamma_CryptoTwin", "Gamma_B"]}), encoding="utf-8")
    (tmp_path / "quiet-mode-never-restore.json").write_text(json.dumps({
        "never_restore": ["Gamma_CryptoTwin"]}), encoding="utf-8")
    assert qm._load_restore_list() == ["Gamma_A", "Gamma_B"]


def test_without_exclusion_file_the_same_list_comes_back_whole(tmp_path, monkeypatch):
    # Discriminating half: the old behaviour (no exclusion) restores everything.
    _point(tmp_path, monkeypatch)
    (tmp_path / "quiet-mode-restore.json").write_text(json.dumps({
        "restore_to_ready": ["Gamma_A", "Gamma_CryptoTwin"]}), encoding="utf-8")
    assert qm._load_restore_list() == ["Gamma_A", "Gamma_CryptoTwin"]


def test_save_never_records_an_excluded_name(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    (tmp_path / "quiet-mode-never-restore.json").write_text(json.dumps({
        "never_restore": ["Gamma_TickersLane"]}), encoding="utf-8")
    qm._save_restore_list(["Gamma_TickersLane", "Gamma_Z"])
    saved = json.loads((tmp_path / "quiet-mode-restore.json").read_text(encoding="utf-8"))
    assert saved["restore_to_ready"] == ["Gamma_Z"]


def test_garbled_exclusion_file_fails_open(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    (tmp_path / "quiet-mode-never-restore.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "quiet-mode-restore.json").write_text(json.dumps({
        "restore_to_ready": ["Gamma_A"]}), encoding="utf-8")
    assert qm._load_restore_list() == ["Gamma_A"]


def test_live_exclusion_file_names_the_two_saturday_tasks():
    live = json.loads((REPO / "automation" / "state" / "quiet-mode-never-restore.json").read_text(encoding="utf-8-sig"))
    assert {"Gamma_CryptoTwin", "Gamma_TickersLane"} <= set(live["never_restore"])
