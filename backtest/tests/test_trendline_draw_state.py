"""Guard tests for setup/scripts/trendline_draw_state.py -- the persistence helper for the
trendline-draw visibility bridge (T14, 2026-07-14).

Pure state I/O, no MCP/network -- these tests monkeypatch STATE to a tmp_path file so they never
touch the real automation/state/trendline-draw-state.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SETUP_SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))

import trendline_draw_state as tds  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setattr(tds, "STATE", tmp_path / "trendline-draw-state.json")
    yield


def test_load_missing_file_returns_empty() -> None:
    assert tds.load() == {"drawn": []}


def test_record_then_load_round_trips() -> None:
    tds.record("e1", "support", "wick", "ascending support 748.7 INTACT")
    payload = tds.load()
    assert payload["drawn"] == [
        {"entity_id": "e1", "kind": "support", "family": "wick",
         "label": "ascending support 748.7 INTACT"}
    ]


def test_ids_to_clear_returns_prior_entity_ids_only() -> None:
    tds.record("e1", "support", "wick")
    tds.record("e2", "resistance", "body")
    assert sorted(tds.ids_to_clear()) == ["e1", "e2"]


def test_clear_record_empties_bookkeeping_without_touching_chart() -> None:
    tds.record("e1", "support", "wick")
    tds.clear_record()
    assert tds.load() == {"drawn": []}
    assert tds.ids_to_clear() == []


def test_load_tolerates_corrupt_json(tmp_path) -> None:
    tds.STATE.parent.mkdir(parents=True, exist_ok=True)
    tds.STATE.write_text("{not valid json", encoding="utf-8")
    assert tds.load() == {"drawn": []}


def test_load_tolerates_wrong_shape(tmp_path) -> None:
    tds.STATE.parent.mkdir(parents=True, exist_ok=True)
    tds.STATE.write_text('{"drawn": "not-a-list"}', encoding="utf-8")
    assert tds.load() == {"drawn": []}


def test_record_accumulates_across_calls() -> None:
    tds.record("e1", "support", "wick")
    tds.record("e2", "resistance", "wick")
    tds.record("e3", "support", "body")
    assert len(tds.load()["drawn"]) == 3
