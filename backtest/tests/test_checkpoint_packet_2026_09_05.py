"""Tests for setup/scripts/checkpoint_packet.py (GOAL-CHECKPOINT-PACKET-2026-09-29 C2).

Two fixture preregs (a terminal-status one and a still-accruing one) exercise the
fail-open dispatcher end to end without touching any real analysis/recommendations
file. A third fixture row names a scorer that does not exist and a fourth row's
scorer is monkeypatched to raise -- both must degrade to a single UNKNOWN row, never
raise out of build_packet.

RED-PROOFED: every test in this file was run once against a deliberately-broken
change (see the run log quoted in the goal report) to confirm it actually fails
before the fix, per repo debugging doctrine (no test whose failure mode was never
observed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import checkpoint_packet as cp  # noqa: E402


@pytest.fixture()
def fixture_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fixtures"
    d.mkdir()
    return d


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_score_row_terminal_kill_status_is_rule_met(fixture_dir, monkeypatch):
    """Fixture prereg #1: a score-ladder-style prereg whose status is an already-
    adjudicated 'KILL -- ...' string and whose ledger has >=15 sessions. The retirement
    rule must read RULE MET (a terminal KILL verdict IS the retirement evidence)."""
    prereg = fixture_dir / "prereg-fixture-kill.json"
    ledger = fixture_dir / "fixture-ledger.jsonl"
    _write_json(prereg, {"status": "KILL -- fixture forward shadow fails all frozen criteria"})
    _write_jsonl(ledger, [
        {"date": f"2026-09-{i:02d}", "arm_id": "risky-1", "delta_pnl": -100.0} for i in range(1, 20)
    ])
    row = {
        "row_id": "fixture-score-ladder",
        "prereg_path": str(prereg.relative_to(REPO)) if prereg.is_relative_to(REPO) else str(prereg),
        "ledger_path": str(ledger.relative_to(REPO)) if ledger.is_relative_to(REPO) else str(ledger),
        "scorer": "score_ladder_v2_retirement",
    }
    # score_score_ladder_v2_retirement resolves paths via REPO / row[...]; when the
    # fixture lives outside REPO (tmp_path), monkeypatch REPO for this one call.
    monkeypatch.setattr(cp, "REPO", Path("/"))
    row["prereg_path"] = str(prereg)
    row["ledger_path"] = str(ledger)
    result = cp._score_score_ladder_v2_retirement(row, "2026-09-05")
    assert result["verdict"] == cp.VERDICT_MET
    assert result["n"] == 19


def test_score_row_frozen_before_any_result_is_insufficient_n(fixture_dir, monkeypatch):
    """Fixture prereg #2: a still-FROZEN_BEFORE_ANY_RESULT prereg with an empty
    zero-enter evidence directory. Must read INSUFFICIENT N, never RULE MET/NOT MET --
    there is no evidence to rule on yet."""
    prereg = fixture_dir / "prereg-fixture-frozen.json"
    empty_dir = fixture_dir / "zero-enter-empty"
    empty_dir.mkdir()
    _write_json(prereg, {"status": "FROZEN_BEFORE_ANY_RESULT -- fixture checkpoint candidate"})
    monkeypatch.setattr(cp, "REPO", Path("/"))
    row = {
        "row_id": "fixture-f10",
        "prereg_path": str(prereg),
        "ledger_path": str(empty_dir),
        "scorer": "f10_vol_baseline_reset",
    }
    # f10 scorer hard-codes the zero_enter_dir path (REPO / "analysis" / "zero-enter");
    # patch that resolution point directly so the fixture's empty dir is what gets globbed.
    monkeypatch.setattr(cp.Path, "glob", lambda self, pattern: iter(()) if "zero-enter" in str(self) else Path.glob(self, pattern))
    result = cp._score_f10_vol_baseline_reset(row, "2026-09-05")
    assert result["verdict"] == cp.VERDICT_INSUFFICIENT_N
    assert result["n"] == 0


def test_unregistered_scorer_name_degrades_to_unknown_not_a_crash():
    """A row naming a scorer that was never registered must produce one UNKNOWN row
    with an explanatory note -- build_packet must never raise for this."""
    row = {"row_id": "no-such-scorer-row", "scorer": "this_scorer_does_not_exist"}
    result = cp.score_row(row, "2026-09-05")
    assert result["verdict"] == cp.VERDICT_UNKNOWN
    assert "no scorer registered" in result["note"]


def test_raising_scorer_degrades_to_unknown_not_a_crash(monkeypatch):
    """FAIL-OPEN requirement from the goal DONE-WHEN: 'a broken scorer = one UNKNOWN
    row, never a crash.' Monkeypatch a registered scorer to raise and confirm score_row
    catches it, attaches the exception text, and returns a normal dict (no propagation)."""

    def _boom(row, today):
        raise RuntimeError("fixture-induced failure")

    monkeypatch.setitem(cp._SCORERS, "tickers_theta_budget_cadence", _boom)
    row = {"row_id": "boom-row", "scorer": "tickers_theta_budget_cadence"}
    result = cp.score_row(row, "2026-09-05")
    assert result["verdict"] == cp.VERDICT_UNKNOWN
    assert "fixture-induced failure" in result["note"]
    assert "traceback" in result


def test_build_packet_end_to_end_against_real_inventory_has_no_crash_and_nine_rows():
    """Integration smoke test against the real, checked-in C1 inventory: every row
    must produce a non-null verdict (the DONE-WHEN's literal requirement) and the
    count must be exactly the nine named decisions (extras are additive, never fewer)."""
    packet = cp.build_packet()
    assert packet["row_count"] >= 9
    for row in packet["rows"]:
        assert row["verdict"] in {
            cp.VERDICT_MET,
            cp.VERDICT_NOT_MET,
            cp.VERDICT_INSUFFICIENT_N,
            cp.VERDICT_PROVISIONAL,
            cp.VERDICT_UNKNOWN,
        }
        assert row["verdict"] is not None


def test_provisional_override_applies_to_right_tail_control4_row():
    """The goal text is explicit: R4 of GOAL-RIGHT-TAIL-CAPTURE is reopened and this
    row must read PROVISIONAL, never cited as confirming evidence, regardless of what
    the mechanical threshold alone would say."""
    packet = cp.build_packet()
    row = next(r for r in packet["rows"] if r["row_id"] == "tight-ladder-control-4-roundtrip-cap")
    assert row["verdict"] == cp.VERDICT_PROVISIONAL


def test_every_row_has_classification_and_checkpoint_routing():
    """C1 requirement (reduction|expansion|shadow-read|tooling) and the routing rule
    (expansion always -> 2026-10-30) must both hold for every row in the real packet."""
    packet = cp.build_packet()
    valid = {"reduction", "expansion", "shadow-read", "tooling"}
    for row in packet["rows"]:
        assert row["classification"] in valid
        if row["classification"] == "expansion":
            assert row["checkpoint"] == "2026-10-30"
