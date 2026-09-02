"""Guards for setup/scripts/obsidian_vault_sync.py's '## The gate' HOME.md block (B4, 2026-09-01).

The generator must RENDER go-live-gate.json verbatim, never compute a new statistic, and a
missing key must degrade to the literal string "n/a" rather than a guess or a crash -- this is
a reporting surface (C7: audit outputs, not exit codes) and it must never break the daily
generator run just because the gate's schema grew or shrank a key overnight.

Covers:
1. A full fixture (mirroring tonight's real go-live-gate.json shape) renders every required
   line, in the required order: overall verdict, criterion-5 (prod_shadow), frozen-window BOOK
   PF/CI, per-arm plan-reachability table, null-study line, governing clock.
2. Missing keys inside an otherwise-valid gate JSON render 'n/a', not KeyError/None/a guess.
3. A missing/corrupt gate file degrades to a stated "unavailable" line, never raises
   (fail-open, C7) -- RED-PROOF target below.
4. The null-study line falls back to "not run" when the summary file does not exist, and
   reads the file verbatim when it does.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"


def _load():
    spec = importlib.util.spec_from_file_location("obsidian_vault_sync_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["obsidian_vault_sync_gate"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


FULL_FIXTURE = {
    "generated_et": "2026-09-01T20:50:20",
    "overall_verdict": "RED",
    "criteria": {
        "prod_shadow": {
            "designation": {"arm": "safe-3"},
            "days_scored": 0,
            "days_needed": 20,
            "current_ci_lower_2.5": None,
            "status": "INSUFFICIENT_DAYS",
        }
    },
    "disclosures": {
        "frozen_config_window": {
            "book_wide_correlated_rollup": {
                "ex_best_day": {"pf_point": None, "ci_lower_2.5": None}
            }
        },
        "plan_reachability": {
            "per_arm": {
                "safe-3": {
                    "tight_ladder_clock_end": {
                        "dollars_per_day": 59.42,
                        "already_clears": False,
                    }
                },
                "safe-2": {
                    "tight_ladder_clock_end": {
                        "dollars_per_day": 65.91,
                        "already_clears": False,
                    }
                },
            }
        },
    },
}


def test_full_fixture_renders_all_required_lines_in_order(tmp_path, monkeypatch):
    m = _load()
    gate_path = tmp_path / "go-live-gate.json"
    gate_path.write_text(json.dumps(FULL_FIXTURE), encoding="utf-8")
    monkeypatch.setattr(m, "GATE_JSON", gate_path)
    monkeypatch.setattr(m, "NULL_STUDY_SUMMARY", tmp_path / "does-not-exist.txt")

    block = m.render_gate_block()
    text = "\n".join(block)

    assert text.index("overall verdict") < text.index("criterion 5")
    assert text.index("criterion 5") < text.index("frozen-window BOOK")
    assert text.index("frozen-window BOOK") < text.index("$/day needed")
    assert text.index("$/day needed") < text.index("null study")
    assert text.index("null study") < text.index("governing clock")

    assert "`RED`" in text
    assert "safe-3" in text
    assert "0/20 days scored" in text
    assert "INSUFFICIENT_DAYS" in text
    assert "59.42" in text and "65.91" in text
    assert "2026-10-30" in text
    assert "null study:** not run" in text


def test_missing_keys_render_n_a_not_a_guess(tmp_path, monkeypatch):
    m = _load()
    sparse = {"overall_verdict": "RED"}  # everything else absent
    gate_path = tmp_path / "go-live-gate.json"
    gate_path.write_text(json.dumps(sparse), encoding="utf-8")
    monkeypatch.setattr(m, "GATE_JSON", gate_path)
    monkeypatch.setattr(m, "NULL_STUDY_SUMMARY", tmp_path / "does-not-exist.txt")

    block = m.render_gate_block()
    text = "\n".join(block)

    # criterion-5 fields all absent -> n/a, never None/KeyError text
    assert "n/a" in text
    assert "None" not in text
    assert "null study:** not run" in text


def test_gate_file_missing_degrades_to_stated_unavailable_line(tmp_path, monkeypatch):
    """RED-PROOF target: an unreadable gate file must never raise -- it must render a
    stated warning line so the generator (and the whole daily HOME.md build) keeps running."""
    m = _load()
    monkeypatch.setattr(m, "GATE_JSON", tmp_path / "nope.json")

    block = m.render_gate_block()  # must not raise
    text = "\n".join(block)
    assert "gate file unreadable" in text


def test_null_study_summary_line_read_verbatim_when_present(tmp_path, monkeypatch):
    m = _load()
    gate_path = tmp_path / "go-live-gate.json"
    gate_path.write_text(json.dumps(FULL_FIXTURE), encoding="utf-8")
    monkeypatch.setattr(m, "GATE_JSON", gate_path)
    summary = tmp_path / "summary-line.txt"
    summary.write_text("book PF 1.02 vs null-shuffle p=0.41 -- NOT distinguishable from noise",
                        encoding="utf-8")
    monkeypatch.setattr(m, "NULL_STUDY_SUMMARY", summary)

    text = "\n".join(m.render_gate_block())
    assert "NOT distinguishable from noise" in text
    assert "not run" not in text
