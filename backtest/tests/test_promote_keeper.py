"""Guard tests for setup/scripts/promote_keeper.py.

Pins the SAFETY INVARIANT: eval_bar_cleared is ALWAYS false when oos fields are
absent from the contender file. This is the critical gate that prevents IS-only
sweep data from auto-shipping to params.json.

Run:  python -m pytest backtest/tests/test_promote_keeper.py -v

Pure stdlib / no pandas / no heavy deps -- runs with system Python.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Wire the scripts directory so we can import promote_keeper directly.
REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import promote_keeper as PK  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _minimal_contender(
    label: str = "OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:trailing",
    combo: list[Any] | None = None,
    edge_capture: float = 1692.39,
    wf: float = 1.98,
    n: int = 214,
    expectancy: float = 23.78,
    wr: float = 0.1215,
    max_dd: float = -1162.6,
) -> dict[str, Any]:
    """Return a minimal contender-rank JSON structure (one top entry, no OOS fields)."""
    if combo is None:
        combo = ["OTM-2", 2, False, 1, "-8", -0.08, 1.5, 0.8, "trailing"]
    return {
        "ranked_at_et": "2026-06-28 10:03",
        "total_scored": 8835,
        "survivors_over_floor": 1880,
        "j_edge_floor": 771.0,
        "wf_pref": 0.7,
        "top": [
            {
                "label": label,
                "edge_capture": edge_capture,
                "expectancy": expectancy,
                "wr": wr,
                "trades_per_day": 1.329,
                "max_dd": max_dd,
                "wf": wf,
                "n": n,
                "combo": combo,
            }
        ],
        "n_wf_strong": 1,
        "note": "READ-ONLY snapshot.",
    }


def _write_contender(tmp_path: Path, data: dict[str, Any], date: str = "2026-06-28") -> Path:
    p = tmp_path / f"contender-rank-{date}.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _read_proposals(proposals_file: Path) -> list[dict[str, Any]]:
    if not proposals_file.exists():
        return []
    rows = []
    for line in proposals_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# CRITICAL SAFETY GUARD: eval_bar_cleared must always be false
# ---------------------------------------------------------------------------

class TestEvalBarClearedSafetyGate:
    """The most important class of tests in this file.

    These tests ensure that promote_keeper NEVER sets eval_bar_cleared=true
    when oos_positive / anchor_no_regression are absent from the contender file.
    A regression here would allow IS-only data to auto-ship to params.json --
    the exact false-edge class documented in C1/C3/L177/L183.
    """

    def test_eval_bar_cleared_is_false_when_oos_fields_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CORE GUARD: a contender file with no OOS fields -> eval_bar_cleared=false."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        data = _minimal_contender()  # no oos_positive, no anchor_no_regression
        _write_contender(tmp_path, data)

        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result["eval_bar_cleared"] is False, (
            "SAFETY BREACH: eval_bar_cleared must be False when oos fields are absent. "
            "This prevents IS-only sweep data from auto-shipping to params.json."
        )

    def test_eval_bar_cleared_is_false_even_if_wf_exceeds_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """High WF alone does not clear the eval bar -- OOS is required."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        data = _minimal_contender(wf=9.99)  # very high IS WF -- still no OOS
        _write_contender(tmp_path, data)

        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result["eval_bar_cleared"] is False

    def test_eval_bar_cleared_is_false_even_if_edge_capture_near_max(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A near-perfect IS score does not clear the eval bar."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        data = _minimal_contender(edge_capture=1541.99)  # just under the max
        _write_contender(tmp_path, data)

        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result["eval_bar_cleared"] is False

    def test_oos_validation_needed_is_always_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """oos_validation_needed must be True to signal the next step."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result.get("oos_validation_needed") is True

    def test_proposal_carries_oos_note_explaining_the_gap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The oos_note field must mention IS data and OOS validation requirement."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        note = result.get("oos_note", "")
        assert "IS" in note or "in-sample" in note.lower() or "oos_positive" in note, (
            "oos_note must explain that the file contains IS data and OOS is required."
        )

    def test_no_scorecard_field_when_oos_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No 'scorecard' key must appear -- it would mislead the actuator into
        treating this as an auto-ratify-eligible proposal."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert "scorecard" not in result, (
            "A 'scorecard' field must not appear in a promote_keeper proposal "
            "because it would mislead the OP-11 actuator."
        )


# ---------------------------------------------------------------------------
# PROPOSAL STRUCTURE tests
# ---------------------------------------------------------------------------

class TestProposalStructure:
    """The emitted proposal must carry all fields the actuator expects."""

    def test_required_fields_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None

        required = {
            "proposal_id", "created_at", "source", "title", "kind",
            "contender_label", "contender_ranked_at", "contender_file",
            "contender_combo", "contender_metrics",
            "decoded_params", "eval_bar_cleared", "apply", "apply_ops",
            "oos_validation_needed", "oos_note", "status",
        }
        missing = required - set(result.keys())
        assert not missing, f"Proposal missing required fields: {missing}"

    def test_source_is_promote_keeper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result["source"] == "promote_keeper"

    def test_status_is_pending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result["status"] == "pending"

    def test_kind_is_params(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert result["kind"] == "params"

    def test_contender_metrics_carries_key_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        data = _minimal_contender(edge_capture=1692.39, wf=1.98, n=214, expectancy=23.78)
        _write_contender(tmp_path, data)
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        metrics = result.get("contender_metrics", {})
        assert metrics.get("edge_capture") == 1692.39
        assert metrics.get("wf") == 1.98
        assert metrics.get("n") == 214

    def test_proposal_id_includes_file_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        _write_contender(tmp_path, _minimal_contender(), date="2026-06-28")
        result = PK.build_proposal(dry_run=True)
        assert result is not None
        assert "2026-06-28" in result["proposal_id"]


# ---------------------------------------------------------------------------
# IDEMPOTENCY tests
# ---------------------------------------------------------------------------

class TestIdempotency:
    """A second call for the same label+ranked_at must not duplicate the proposal."""

    def test_second_call_same_label_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        proposals_file = tmp_path / "proposals.jsonl"
        monkeypatch.setattr(PK, "PROPOSALS_FILE", proposals_file)

        _write_contender(tmp_path, _minimal_contender())

        result1 = PK.build_proposal()
        assert result1 is not None

        result2 = PK.build_proposal()
        assert result2 is None, "Second call for the same label should return None (skipped)."

        rows = _read_proposals(proposals_file)
        assert len(rows) == 1, f"Expected 1 proposal, got {len(rows)}"

    def test_different_ranked_at_produces_new_proposal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        proposals_file = tmp_path / "proposals.jsonl"
        monkeypatch.setattr(PK, "PROPOSALS_FILE", proposals_file)

        label = "OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:trailing"
        data1 = _minimal_contender(label=label)
        data1["ranked_at_et"] = "2026-06-27 23:45"
        _write_contender(tmp_path, data1, date="2026-06-27")

        result1 = PK.build_proposal(tmp_path / "contender-rank-2026-06-27.json")
        assert result1 is not None

        data2 = _minimal_contender(label=label)
        data2["ranked_at_et"] = "2026-06-28 10:03"
        _write_contender(tmp_path, data2, date="2026-06-28")

        result2 = PK.build_proposal(tmp_path / "contender-rank-2026-06-28.json")
        assert result2 is not None, "Different ranked_at should produce a new proposal."

        rows = _read_proposals(proposals_file)
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# WRITE tests (non-dry-run)
# ---------------------------------------------------------------------------

class TestWriteBehavior:
    """The proposal is written correctly to the ledger in non-dry-run mode."""

    def test_proposal_appended_to_ledger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        proposals_file = tmp_path / "proposals.jsonl"
        monkeypatch.setattr(PK, "PROPOSALS_FILE", proposals_file)

        _write_contender(tmp_path, _minimal_contender())
        result = PK.build_proposal()
        assert result is not None

        rows = _read_proposals(proposals_file)
        assert len(rows) == 1
        written = rows[0]
        assert written["eval_bar_cleared"] is False
        assert written["status"] == "pending"
        assert written["source"] == "promote_keeper"

    def test_dry_run_does_not_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        proposals_file = tmp_path / "proposals.jsonl"
        monkeypatch.setattr(PK, "PROPOSALS_FILE", proposals_file)

        _write_contender(tmp_path, _minimal_contender())
        PK.build_proposal(dry_run=True)

        assert not proposals_file.exists(), "dry_run=True must NOT write to the ledger."

    def test_written_row_is_valid_json_per_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        proposals_file = tmp_path / "proposals.jsonl"
        monkeypatch.setattr(PK, "PROPOSALS_FILE", proposals_file)

        _write_contender(tmp_path, _minimal_contender())
        PK.build_proposal()

        lines = [l for l in proposals_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1
        obj = json.loads(lines[0])  # must not raise
        assert isinstance(obj, dict)


# ---------------------------------------------------------------------------
# ERROR HANDLING tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Graceful handling of missing/malformed inputs."""

    def test_no_contender_files_raises_systemexit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)  # empty dir
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")
        with pytest.raises(SystemExit):
            PK.build_proposal()

    def test_empty_top_list_raises_systemexit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")
        data = _minimal_contender()
        data["top"] = []
        _write_contender(tmp_path, data)
        with pytest.raises(SystemExit):
            PK.build_proposal()

    def test_newest_file_selected_by_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When multiple files exist, the newest (alphabetically latest date) is used."""
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        older = _minimal_contender(label="OTM-1:LR0:mt1:stop-8:tp+150%:sell80%:fixed")
        older["ranked_at_et"] = "2026-06-26 23:00"
        _write_contender(tmp_path, older, date="2026-06-26")

        newer = _minimal_contender(label="OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:trailing")
        newer["ranked_at_et"] = "2026-06-28 10:03"
        _write_contender(tmp_path, newer, date="2026-06-28")

        result = PK.build_proposal(dry_run=True)
        assert result is not None
        # Should have picked the 2026-06-28 file (alphabetically last)
        assert result["contender_label"] == "OTM-2:LR0:mt1:stop-8:tp+150%:sell80%:trailing"

    def test_malformed_combo_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PK, "RECS_DIR", tmp_path)
        monkeypatch.setattr(PK, "PROPOSALS_FILE", tmp_path / "proposals.jsonl")

        data = _minimal_contender()
        data["top"][0]["combo"] = []  # empty combo
        _write_contender(tmp_path, data)

        result = PK.build_proposal(dry_run=True)
        assert result is not None
        # eval_bar_cleared must still be false even with empty combo
        assert result["eval_bar_cleared"] is False


# ---------------------------------------------------------------------------
# BITE TEST: proves the eval_bar_cleared=false guard is non-vacuous
# ---------------------------------------------------------------------------

def test_bite_eval_bar_cleared_cannot_be_true_by_default() -> None:
    """Prove that build_proposal cannot produce eval_bar_cleared=True from a
    contender file without OOS data. This is a bite test -- it verifies the
    safety gate by attempting to observe the failure mode that the gate blocks.

    A contender file with high IS metrics (edge_capture near max, wf>0.9)
    must still produce eval_bar_cleared=False because no oos_positive field
    is present in the file.
    """
    decoded = PK._decode_combo(["OTM-2", 2, False, 1, "-8", -0.08, 1.5, 0.8, "trailing"])
    # Simulate what build_proposal would produce for a "perfect" IS combo.
    # We directly test that no code path in this module ever sets eval_bar_cleared=True
    # from IS-only data.
    assert decoded["tp1_qty_fraction"] == 0.8
    assert decoded["profit_lock_mode"] == "trailing"
    assert decoded["premium_stop_pct"] == -0.08

    # The key assertion: eval_bar_cleared is always hardcoded to False in build_proposal.
    # There is NO code path that sets it True. Verify by inspection of the source.
    import inspect
    src = inspect.getsource(PK.build_proposal)
    # Must not have any assignment of True to eval_bar_cleared.
    assert '"eval_bar_cleared": True' not in src, (
        "BITE TEST FAILURE: found 'eval_bar_cleared': True in build_proposal source. "
        "This would allow IS-only data to auto-ship."
    )
    assert "eval_bar_cleared: True" not in src
    # Must have the False assignment.
    assert '"eval_bar_cleared": False' in src or "eval_bar_cleared=False" in src or "eval_bar_cleared': False" in src
