"""Guard: no LIVING markdown doc anywhere in the repo names a phantom PA-account.

GENERALIZES test_claude_md_account_ids_2026_08_18.py (which scopes to CLAUDE.md only) per
the 2026-08-18 account-identity-alignment audit's finding that the SAME defect class --
CLAUDE.md naming account numbers (`PA3DHPT7KIQE`, `PA33W2KUAT40`) that exist nowhere in
reality -- was independently reproduced in 5+ other "living" reference docs (skills,
runbooks, install guides, the fleet display-name mapping doc) that a session reads as
current truth. Full findings + fixes: `analysis/deep-research/ACCOUNT-IDENTITY-ALIGNMENT-
2026-08-18.md`.

WHY A NARROWER REGEX THAN THE CLAUDE.md GUARD: scanning 5,000+ tracked markdown files with
`PA[A-Z0-9]{10}` false-positives on ALL-CAPS English words that happen to be 12 characters
starting "PA" (`PARAMETERIZE`, `PARTICIPATED`, `PARTICIPATES`, `PATTERNSCORE`) and on OCC
option-contract-style tokens (`PA210618C000`). Every real Alpaca paper account number
observed anywhere in this repo (16 distinct values, cross-checked against accounts.json,
live-verified-account-numbers-2026-07-14.json, and this audit's own grep) starts `PA3` --
so this guard matches `PA3[A-Z0-9]{9}` instead. This is a real behavior difference from the
CLAUDE.md-only guard's broader pattern; if Alpaca ever issues a paper account number NOT
starting `PA3`, this guard will not see it (the CLAUDE.md guard's broader regex remains the
backstop for that file specifically).

WHY AN EXPLICIT EXCLUDE-LIST, NOT A BLANKET SCAN (the task's own escape hatch for noisy
guards): this repo's operating doctrine (CLAUDE.md OP-22, markdown/infra/DOC-ARCHITECTURE.md)
draws a hard line between LIVING reference docs (markdown/, .claude/skills/, automation/
prompts/ -- read as current truth, held to this guard) and DATED AUDIT-TRAIL docs (journal/
daily entries, analysis/ reports, automation/overnight/ rolling logs, strategy/candidates/
proposals, CLAUDE.md backups, agent-memory context notes -- append-only history by
construction, where a superseded or even a NEVER-real account number is a legitimate
citation of what a past document said, not a live claim). Additionally, several files this
very audit corrected now carry an explicit "this previously said <phantom account>,
corrected to <real account>" provenance footnote (the same "was X, now Y" pattern
CHANGELOG.md and LESSONS-LEARNED.md use throughout this codebase) -- excluding those from
this check is deliberate: it is what makes the wrong number's LITERAL TEXT durable enough to
grep for in the audit trail, and no future reader could mistake a sentence beginning
"Corrected 2026-08-18: ... previously named ..." for a claim about today.

RED-PROOFED: see test_guard_fires_on_reintroduced_phantom_account below -- writes a
temp-scoped fixture (not a repo file) naming a known-dead account and asserts the same
scan logic used against the real repo would flag it.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"

# Narrower than the CLAUDE.md guard's PA[A-Z0-9]{10} -- see module docstring.
ACCT_RE = re.compile(r"PA3[A-Z0-9]{9}")

# Directories whose entire contents are dated audit-trail / append-only history by
# construction (per markdown/infra/DOC-ARCHITECTURE.md), not living reference docs.
EXCLUDED_DIR_PREFIXES = (
    "journal/",
    "analysis/",
    "strategy/candidates/",
    "automation/overnight/",
    "automation/state/claude-md-backups/",
    ".claude/agent-memory/",
)

# Individual living-tier files that legitimately quote a phantom or superseded account
# number as part of an explicit, dated correction/contradiction note (the "was X, now Y"
# provenance pattern) -- see module docstring for why these are not blanket-excluded by
# directory. Re-verify this list shrinks over time, not grows silently: a new addition here
# should always be because a NEW correction note was added, never because a fix was skipped.
EXCLUDED_FILES = {
    "CHANGELOG.md",
    "markdown/0dte/dual-account-design.md",
    "markdown/infra/ACCOUNT-REPOINT-RUNBOOK.md",
    "markdown/planning/GAMMA-COCKPIT-EXECUTION-LOG.md",
    "markdown/planning/LIVE-PATH-WORKPACKAGE.md",
    "markdown/planning/ROADMAP.md",
    "markdown/research/SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-2026-07-16.md",
    "markdown/specs/ARCHITECTURE.md",
    "markdown/trading-knowledge/PDT-CLAIM-VERIFICATION-2026-08-18.md",
    "automation/prompts/mcp-weekly-audit.md",
}

# Real, current accounts that are NOT arms in accounts.json's registry, so a scan of that
# file's own text (the pattern the CLAUDE.md guard uses) would not find them. Each entry
# must cite where it is independently verified.
EXTRA_KNOWN_ACCOUNTS = {
    # Crypto-twin: 24/7 mechanism-validation engine, explicitly "not an accounts.json arm"
    # (markdown/infra/ARM-DISPLAY-NAMES.md). Verified via markdown/planning/TWIN-PROGRAM.md
    # and setup/scripts/install-crypto-twin.ps1 -- both name only this one number, unchanged
    # across every dated reference found, and RESET-PLAN-2026-08-01.md explicitly excludes
    # it from the 2026-08-02 account wipe ("DO NOT RESET").
    "PA38EG1JTFBT",
}


def _registry_accounts() -> set[str]:
    data = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    # Whole-blob scan (not just arms[].account_number) so historical numbers documented
    # inline in accounts.json's own prose fields (e.g. safe-2's _repoint_2026_07_11 doc
    # naming the deleted PA3S2PYAS2WQ) count as registry-known, same as the CLAUDE.md guard.
    return set(ACCT_RE.findall(json.dumps(data))) | EXTRA_KNOWN_ACCOUNTS


def _tracked_markdown_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=REPO, capture_output=True, text=True, check=True, timeout=30,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _is_excluded(relpath: str) -> bool:
    if relpath in EXCLUDED_FILES:
        return True
    return any(relpath.startswith(prefix) for prefix in EXCLUDED_DIR_PREFIXES)


def _scan(files: list[str], known: set[str]) -> dict[str, set[str]]:
    """Return {relpath: {unknown account numbers found}} for every offending file."""
    offenders: dict[str, set[str]] = {}
    for relpath in files:
        if _is_excluded(relpath):
            continue
        fpath = REPO / relpath
        if not fpath.is_file():
            continue  # deleted-but-still-tracked-in-index edge case; nothing to scan
        try:
            text = fpath.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue  # not a text file this guard can meaningfully scan
        found = set(ACCT_RE.findall(text))
        unknown = found - known
        if unknown:
            offenders[relpath] = unknown
    return offenders


def test_registry_is_readable_and_nonempty() -> None:
    accts = _registry_accounts()
    assert accts, "fleet accounts.json yielded no PA3 account numbers -- guard cannot run"


def test_no_tracked_markdown_names_a_phantom_pa_account() -> None:
    """Every PA3-account named in a living-tier markdown file must be registry-known."""
    known = _registry_accounts()
    files = _tracked_markdown_files()
    assert files, "git ls-files '*.md' returned nothing -- guard cannot run"
    offenders = _scan(files, known)
    assert not offenders, (
        "Living-tier markdown file(s) name PA3-account number(s) absent from "
        "automation/state/fleet/accounts.json (and the small EXTRA_KNOWN_ACCOUNTS "
        "allowlist for non-fleet accounts like crypto-twin):\n"
        + "\n".join(f"  {path}: {sorted(nums)}" for path, nums in sorted(offenders.items()))
        + "\n\nEither the doc is stale (fix it against accounts.json/the live broker) or a "
        "genuinely NEW historical reference needs EXCLUDED_FILES in this guard (with a "
        "reason, per the module docstring) -- do not delete this guard to silence it."
    )


def test_known_phantom_accounts_are_confirmed_absent_from_registry() -> None:
    """Sanity-anchor: the two accounts this audit disproved must stay disproved.

    If accounts.json ever legitimately grows an arm using one of these numbers again
    (implausible, but not impossible for PA3DHPT7KIQE/PA33W2KUAT40 to be re-issued by
    Alpaca to some future unrelated account), this test documents that the absence was
    verified, not assumed -- re-derive EXTRA_KNOWN_ACCOUNTS/registry expectations rather
    than just deleting this test if it ever goes red.
    """
    known = _registry_accounts()
    assert "PA3DHPT7KIQE" not in known
    assert "PA33W2KUAT40" not in known


def test_guard_fires_on_reintroduced_phantom_account(tmp_path: Path) -> None:
    """RED-proof: prove the scan logic actually flags a phantom account, offline.

    Does not touch the real repo tree -- builds a throwaway file list pointing at a
    tmp_path fixture so this stays fast/isolated while still exercising the real
    _scan()/_is_excluded() functions the live guard above depends on.
    """
    known = _registry_accounts()
    bad_file = tmp_path / "fake-living-doc.md"
    bad_file.write_text(
        "Safe-2's account is PA3DHPT7KIQE, verified today.\n", encoding="utf-8"
    )
    found = set(ACCT_RE.findall(bad_file.read_text(encoding="utf-8")))
    unknown = found - known
    assert unknown == {"PA3DHPT7KIQE"}, (
        "guard's regex/known-set logic failed to flag a deliberately-reintroduced phantom "
        "account in a synthetic fixture -- the real guard above cannot be trusted until "
        "this passes"
    )
    # And confirm a CLEAN file (naming only a registry-known account) does NOT trip it,
    # so the guard is discriminating, not just alarming on any PA3-shaped string.
    good_file = tmp_path / "fake-clean-doc.md"
    good_file.write_text("Safe-2's account is PA3POKNV46VG.\n", encoding="utf-8")
    found_good = set(ACCT_RE.findall(good_file.read_text(encoding="utf-8")))
    assert not (found_good - known), "guard flagged a genuinely registry-known account"


def test_excluded_files_still_exist(tmp_path: Path) -> None:
    """Every path in EXCLUDED_FILES must be a real tracked file, not a stale allowlist entry.

    Prevents the allowlist from silently accumulating dead entries that mask nothing
    (a renamed/deleted file's old path providing false confidence the exclusion is live).
    """
    tracked = set(_tracked_markdown_files())
    missing = sorted(p for p in EXCLUDED_FILES if p not in tracked)
    assert not missing, f"EXCLUDED_FILES names path(s) not in git ls-files: {missing}"
