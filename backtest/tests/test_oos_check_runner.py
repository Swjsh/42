"""Guards for oos_check_runner.py core logic (Gamma_OosCheck nightly).

The runner un-strands promote_keeper proposals (PIPELINE-AUDIT-2026-07-01 break
 #4). Pure-logic functions under guard (the subprocess orchestration is not):

  - select_pending: only pending, un-cleared promote_keeper rows whose
    contender_file is still the NEWEST ranking are validated (superseded rows
    are skipped — contender_oos_check always validates the newest file's top).
  - apply_cleared_scorecard: flips eval_bar_cleared + attaches the scorecard on
    exactly the matching row, atomically, leaving every other row byte-intact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from oos_check_runner import (  # noqa: E402
    apply_cleared_scorecard,
    newest_contender_name,
    select_pending,
)


def _row(pid: str, **kw) -> dict:
    base = {
        "proposal_id": pid,
        "source": "promote_keeper",
        "status": "pending",
        "eval_bar_cleared": False,
        "contender_file": "contender-rank-2026-06-29.json",
    }
    return {**base, **kw}


def test_select_pending_filters_correctly() -> None:
    newest = "contender-rank-2026-06-29.json"
    rows = [
        _row("pk-2026-06-29-001"),                                        # eligible
        _row("pk-2026-06-28-001", contender_file="contender-rank-2026-06-28.json"),  # superseded
        _row("pk-x-cleared", eval_bar_cleared=True),                      # already cleared
        _row("pk-x-approved", status="approved"),                         # not pending
        {"proposal_id": "cd-1", "source": "conductor", "status": "pending"},  # wrong source
        _row("pk-2026-06-29-001"),                                        # duplicate pid
    ]
    picked = select_pending(rows, newest)
    assert [r["proposal_id"] for r in picked] == ["pk-2026-06-29-001"]


def test_select_pending_no_newest_contender_allows_all_pending() -> None:
    rows = [_row("pk-a"), _row("pk-b", contender_file="contender-rank-2026-06-01.json")]
    picked = select_pending(rows, None)
    assert {r["proposal_id"] for r in picked} == {"pk-a", "pk-b"}


def test_newest_contender_name(tmp_path: Path) -> None:
    (tmp_path / "contender-rank-2026-06-01.json").write_text("{}", encoding="utf-8")
    (tmp_path / "contender-rank-2026-06-29.json").write_text("{}", encoding="utf-8")
    assert newest_contender_name(tmp_path) == "contender-rank-2026-06-29.json"
    assert newest_contender_name(tmp_path / "empty") is None


def test_apply_cleared_scorecard_flips_only_matching_row(tmp_path: Path) -> None:
    ledger = tmp_path / "conductor-proposals.jsonl"
    other = {"proposal_id": "cd-1", "source": "conductor", "status": "pending"}
    target = _row("pk-2026-06-29-001")
    bystander = _row("pk-2026-06-28-001")
    ledger.write_text(
        "\n".join(json.dumps(r) for r in (other, target, bystander)) + "\n",
        encoding="utf-8",
    )

    rel = "analysis/recommendations/pk-2026-06-29-001-scorecard.json"
    assert apply_cleared_scorecard(ledger, "pk-2026-06-29-001", rel) is True

    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 3
    by_id = {r["proposal_id"]: r for r in rows}
    flipped = by_id["pk-2026-06-29-001"]
    assert flipped["eval_bar_cleared"] is True
    assert flipped["scorecard"] == rel
    assert flipped["oos_validation_needed"] is False
    assert "oos_cleared_at" in flipped
    # bystanders untouched
    assert by_id["pk-2026-06-28-001"]["eval_bar_cleared"] is False
    assert by_id["cd-1"] == other


def test_apply_cleared_scorecard_no_match_returns_false(tmp_path: Path) -> None:
    ledger = tmp_path / "conductor-proposals.jsonl"
    ledger.write_text(json.dumps(_row("pk-a")) + "\n", encoding="utf-8")
    before = ledger.read_text(encoding="utf-8")
    assert apply_cleared_scorecard(ledger, "pk-MISSING", "x.json") is False
    assert ledger.read_text(encoding="utf-8") == before

    # already-cleared row is not re-flipped
    ledger2 = tmp_path / "l2.jsonl"
    ledger2.write_text(json.dumps(_row("pk-a", eval_bar_cleared=True)) + "\n", encoding="utf-8")
    assert apply_cleared_scorecard(ledger2, "pk-a", "x.json") is False
