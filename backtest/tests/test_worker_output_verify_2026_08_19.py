"""Guard: the master must never bank an unverified worker completion claim.

SCAR (two failures, one root cause — the orchestrator only ever sees the worker's
summary, never its trace):

  1. FABRICATION. `analysis/manager/2026-08-18-2253-strategist-weekly-options-build.md`
     reported Phase 0 of the weekly-options build as done, citing artifacts
     (expiry_selector.py, blast_radius_20260818.json, sector_heat_signals.csv)
     that were never written. A sweep of all 690 reports in analysis/manager/
     found 12 with the same shape, spanning 2026-06-25..2026-08-18 — undetected
     for two months. `_looks_like_garbage()` cannot catch a FLUENT lie.

  2. ESCALATION SPAM. `gamma_manager.escalate()` appended to queue.md
     unconditionally on a 20-minute cadence, so ONE unresolved blocker produced
     9 near-identical `- [ ] ESCALATION (manager_flagged)` lines in a day. The
     coordinator re-words each time, so exact-string dedupe does not work.

RED-PROOF: revert setup/scripts/worker_output_verify.py's bare-filename extraction
(or gamma_manager's _match_existing) and these tests fail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import worker_output_verify as wov            # noqa: E402
import gamma_manager as gm                    # noqa: E402


# ---------------------------------------------------------------- fabrication

FABRICATED_REPORT = REPO / "analysis" / "manager" / "2026-08-18-2253-strategist-weekly-options-build.md"


def test_known_fabricated_report_is_caught():
    """The canonical scar report must verdict FABRICATED, naming real missing files."""
    if not FABRICATED_REPORT.exists():
        pytest.skip("scar report archived; synthetic cases below still guard the logic")
    res = wov.verify(FABRICATED_REPORT.read_text(encoding="utf-8", errors="replace"),
                     report_dir=FABRICATED_REPORT.parent)
    assert res["verdict"] == "FABRICATED", res
    assert res["exit_code"] == 3
    missing = " ".join(res["missing_paths"]).lower()
    assert "blast_radius_20260818.json" in missing, res["missing_paths"]


def test_completion_claim_about_missing_file_is_fabricated():
    text = "I wrote the new detector to `totally_invented_detector_xyz.py` and it passes."
    res = wov.verify(text)
    assert res["verdict"] == "FABRICATED", res


def test_proposal_about_missing_file_is_only_unverified():
    """Naming a path that does not exist YET is legitimate planning, not a lie."""
    text = "We should add `totally_invented_detector_xyz.py` as the next step."
    res = wov.verify(text)
    assert res["verdict"] == "UNVERIFIED", res
    assert res["exit_code"] == 2


def test_real_repo_paths_verify_clean():
    text = "Updated `setup/scripts/gamma_manager.py` and wrote CLAUDE.md."
    res = wov.verify(text)
    assert res["verdict"] == "VERIFIED", res
    assert res["exit_code"] == 0


def test_all_digit_token_is_not_treated_as_a_git_sha():
    """20260818 is a date. Flagging it as a missing commit was a false positive."""
    claims = wov.extract_claims("committed on 20260818 as planned")
    assert claims["shas"] == [], claims


def test_gitignored_but_real_file_does_not_false_positive():
    """secrets.json is gitignored and real; excluding ignored files mis-flagged a
    genuine J-facing brief as FABRICATED."""
    idx = wov._basename_index()
    assert "secrets.json" in idx or not idx, "ignored-but-present files must be indexed"


def test_prose_with_no_artifact_claims_is_not_flagged():
    res = wov.verify("The signal failed the random-entry null on every arm. Nothing ships.")
    assert res["verdict"] == "NO_CLAIMS", res
    assert res["exit_code"] == 0


# ----------------------------------------------------------------- escalation

# Verbatim from automation/overnight/queue.md, 2026-08-19 — nine appends, one blocker.
REAL_DUPES = [
    "OP-32 free-model trust gate validation: exposes a critical trust gate vulnerability where free-tier 'strategist' role generated fake artifacts for a live overnight program - must verify system integri",
    "OP-32 free-model trust gate validation: critical trust gate vulnerability exposed where fake artifacts were generated for a live overnight program - must verify system integrity before any further bui",
    "run validation checks on artifact generation paths and compare against actual disk writes: critical trust gate vulnerability exposed where fake artifacts were generated for a live overnight program -",
    "compare generated artifacts against actual disk writes to detect discrepancies: critical trust gate vulnerability exposed where fake artifacts were generated for a live overnight program - must verify",
    "OP-32 free-model trust gate validation: critical trust gate vulnerability exposed where free-tier 'strategist' role generated fake artifacts for a live overnight program - must verify system integrity",
    "OP-32 free-model trust gate validation: Critical trust gate vulnerability exposed by fake artifact generation requires direct validation of disk writes vs claimed outputs",
    "trust_gate_artifact_validation: Critical trust gate vulnerability exposed by fake artifact generation requires immediate validation of disk writes vs claimed outputs to ensure system integrity",
]


@pytest.fixture()
def sandboxed(tmp_path, monkeypatch):
    """Point every escalation side-effect at tmp_path — never touch live surfaces."""
    monkeypatch.setattr(gm, "ESCALATION_LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(gm, "QUEUE_MD", tmp_path / "queue.md")
    monkeypatch.setattr(gm, "OUTBOX", tmp_path / "outbox.jsonl")
    monkeypatch.setattr(gm, "LOG", tmp_path / "log.jsonl")
    return tmp_path


def test_reworded_repeat_escalations_are_deduped(sandboxed):
    """The nine real 2026-08-19 appends must collapse to ONE queue line."""
    surfaced = [gm.escalate("manager_flagged", d) for d in REAL_DUPES]
    assert surfaced[0] is True, "the first escalation must always surface"
    assert sum(surfaced) == 1, (
        "reworded repeats of one blocker must not re-queue: %d of %d surfaced"
        % (sum(surfaced), len(REAL_DUPES))
    )
    queue_lines = [l for l in (sandboxed / "queue.md").read_text(encoding="utf-8").splitlines()
                   if "ESCALATION" in l]
    assert len(queue_lines) == 1, queue_lines


def test_dedupe_counts_occurrences_instead_of_dropping_them(sandboxed):
    for d in REAL_DUPES:
        gm.escalate("manager_flagged", d)
    ledger = json.loads((sandboxed / "ledger.json").read_text(encoding="utf-8"))
    assert len(ledger) == 1, ledger
    assert list(ledger.values())[0]["count"] == len(REAL_DUPES)


def test_a_genuinely_different_blocker_still_surfaces(sandboxed):
    """Dedupe must not become a gag: an unrelated escalation still reaches J."""
    assert gm.escalate("manager_flagged", REAL_DUPES[0]) is True
    assert gm.escalate("manager_flagged", REAL_DUPES[1]) is False
    assert gm.escalate(
        "engine_red",
        "heartbeat_core wrote 0 decisions for the full session; sight_beacon stale 4h",
    ) is True


def test_related_but_distinct_blocker_is_not_gagged(sandboxed):
    """Anti-gag guard. These share vocabulary with the scar blocker (OP-32,
    free-model, trust gate) but are DIFFERENT problems; measured Jaccard 0.18-0.21
    vs 0.37+ for true repeats. Each must still reach J."""
    assert gm.escalate("manager_flagged", REAL_DUPES[0]) is True
    assert gm.escalate(
        "manager_flagged",
        "OP-32 free-model trust gate: the nemotron lane returned garbage token-salad "
        "output on 4 consecutive fires, free-tier quality has degraded",
    ) is True
    assert gm.escalate(
        "manager_flagged",
        "OP-32 free-model lane exhausted: openrouter free tier returned 429 for every "
        "role this fire, fell through to local ollama floor",
    ) is True


def test_fingerprint_does_not_drift_across_rewordings(sandboxed):
    """The stored identity must stay pinned to the FIRST wording. If it drifted to
    the latest wording each fire it would eventually match everything."""
    gm.escalate("manager_flagged", REAL_DUPES[0])
    first = json.loads((sandboxed / "ledger.json").read_text(encoding="utf-8"))
    first_tokens = list(first.values())[0]["tokens"]
    for d in REAL_DUPES[1:]:
        gm.escalate("manager_flagged", d)
    after = json.loads((sandboxed / "ledger.json").read_text(encoding="utf-8"))
    assert list(after.values())[0]["tokens"] == first_tokens


def test_unreadable_ledger_fails_open(sandboxed):
    """A corrupt ledger must never swallow a signal (OP-25 fail-open rail)."""
    (sandboxed / "ledger.json").write_text("{not json", encoding="utf-8")
    assert gm.escalate("manager_flagged", REAL_DUPES[0]) is True
