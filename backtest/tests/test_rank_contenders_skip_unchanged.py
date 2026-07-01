"""Guard: rank_contenders must NOT restamp output when its input is frozen (OP-33).

Scar (2026-07-01 consolidation audit): mass-grind-progress.jsonl froze on 06-26
10:23 but Gamma_ContenderRank kept rewriting contender-rank-{date}.json every
30 min, byte-identical except the timestamp — 6 days of fake "fresh research".

REDs on regression: if main() ever writes a rank file (or a Discord flag) on an
unchanged input, these tests fail.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "rank_contenders.py"
_spec = importlib.util.spec_from_file_location("rank_contenders_under_test", _MOD_PATH)
rc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rc
_spec.loader.exec_module(rc)


_ROW = {"label": "grind-x", "edge_capture": 900.0, "expectancy": 1.2,
        "wr": 0.55, "trades_per_day": 1.1, "max_dd": -120.0, "wf": 0.8, "n": 40}


def _setup(tmp_path, monkeypatch) -> Path:
    rec = tmp_path / "analysis" / "recommendations"
    rec.mkdir(parents=True)
    state = tmp_path / "automation" / "state"
    state.mkdir(parents=True)
    monkeypatch.setattr(rc, "REPO", tmp_path)
    monkeypatch.setattr(rc, "GRIND", rec / "mass-grind-progress.jsonl")
    monkeypatch.setattr(rc, "RANK_STATE", rec / ".contender-rank-input-state.json")
    monkeypatch.setattr(rc, "OUTBOX", state / "discord-outbox.jsonl")
    return rec


def _outbox_size() -> int:
    return rc.OUTBOX.stat().st_size if rc.OUTBOX.exists() else 0


def test_second_run_on_frozen_input_writes_nothing(tmp_path, monkeypatch, capsys):
    rec = _setup(tmp_path, monkeypatch)
    rc.GRIND.write_text(json.dumps(_ROW) + "\n", encoding="utf-8")

    assert rc.main() is not None
    ranked = list(rec.glob("contender-rank-*.json"))
    assert len(ranked) == 1
    stamp1 = ranked[0].stat().st_mtime_ns
    body1 = ranked[0].read_bytes()
    outbox1 = _outbox_size()
    capsys.readouterr()

    # Input untouched -> second run must SKIP and write NOTHING.
    assert rc.main() is None
    out = capsys.readouterr().out
    assert "SKIP_UNCHANGED" in out
    assert "input frozen since" in out
    assert ranked[0].stat().st_mtime_ns == stamp1
    assert ranked[0].read_bytes() == body1
    assert _outbox_size() == outbox1  # no fresh Discord flag on a frozen input


def test_changed_input_ranks_again(tmp_path, monkeypatch, capsys):
    rec = _setup(tmp_path, monkeypatch)
    rc.GRIND.write_text(json.dumps(_ROW) + "\n", encoding="utf-8")
    assert rc.main() is not None
    ranked = list(rec.glob("contender-rank-*.json"))
    stamp1 = ranked[0].stat().st_mtime_ns

    row2 = dict(_ROW, label="grind-y", edge_capture=1000.0)
    with open(rc.GRIND, "a", encoding="utf-8") as f:
        f.write(json.dumps(row2) + "\n")

    out = rc.main()
    assert out is not None and out["total_scored"] == 2
    assert "SKIP_UNCHANGED" not in capsys.readouterr().out
    assert ranked[0].stat().st_mtime_ns >= stamp1


def test_missing_input_after_seed_skips(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch)
    # No GRIND file at all: first run writes (seeds state), second skips.
    assert rc.main() is not None
    assert rc.main() is None
    assert "SKIP_UNCHANGED" in capsys.readouterr().out
