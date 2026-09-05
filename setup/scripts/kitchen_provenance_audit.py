"""kitchen_provenance_audit.py -- catches Kitchen (free-model) verdicts that cite
artifacts (runner scripts, JSON scorecards, tests) which do not exist on disk.

WHY THIS EXISTS: _lesson-inbox/2026-09-05-kitchen-nemotron-fabricated-analysis-numbers.md --
three independent Sonnet adjudication workers found chef-nemo `_analysis/*.md` verdicts
citing JSONs/tests/runners that were never produced (schema filled in even though the named
runner was never executed -- C7 silent-success at R&D scale). This script is the deterministic,
$0 fix: for every candidate file with a numeric verdict, extract every cited artifact path and
check it against disk. No LLM call, no judgment call -- existence on disk is ground truth.

CLASSIFICATION per file:
  PROVENANCE-OK       -- cites >=1 artifact AND every cited artifact exists on disk.
  PROVENANCE-MISSING  -- cites >=1 artifact AND at least one cited artifact does not exist.
  NO-ARTIFACT-CITED   -- has numeric content (a verdict/scorecard) but cites zero artifacts.
                         Treated as unverified, same trust tier as PROVENANCE-MISSING for
                         promotion purposes, but logged separately since it is a different
                         failure shape (no evidence offered at all, vs. evidence offered that
                         doesn't exist).
  NOT-A-VERDICT       -- no numeric verdict content at all (draft ideas, brainstorm stubs);
                         excluded from totals, not scored.

USAGE:
  python setup/scripts/kitchen_provenance_audit.py            # full scan, writes outputs
  python setup/scripts/kitchen_provenance_audit.py --json-only

OUTPUTS:
  analysis/kitchen-review/provenance-audit.json  -- per-file rows + totals
  analysis/kitchen-review/PROVENANCE-AUDIT.md    -- compact table: totals + 30 worst offenders

GUARDS:
  * Read-only over strategy/candidates/ -- NEVER rewrites the corpus files themselves.
  * Not on FROZEN_TRADING_PATH; never touches heartbeat*/params*/CLAUDE.md.
  * Anchored to __file__; fails open (a crash here must never block the daemon/reviewer).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
CANDIDATES_DIR = REPO / "strategy" / "candidates"
ANALYSIS_DIR = CANDIDATES_DIR / "_analysis"
REVIEW_DIR = REPO / "analysis" / "kitchen-review"
AUDIT_JSON = REVIEW_DIR / "provenance-audit.json"
AUDIT_MD = REVIEW_DIR / "PROVENANCE-AUDIT.md"

# Artifact-path patterns cited in prose. Matches a bare relative path under one of these
# repo roots, plus test_*.py filenames referenced without a full path (common in prose:
# "must pass test_qqq_label_vol_strat.py").
_PATH_RE = re.compile(
    r"(?:^|[\s(`\[\"'])"
    r"((?:analysis|backtest|strategy|automation)/[\w\-./]+\.(?:json|py|md|csv|jsonl)"
    r"|tests/test_[\w\-]+\.py"
    r"|test_[\w\-]+\.py)"
)

# A file "has numeric verdict content" if it contains a confidence score, a percentage,
# a dollar amount, or a PASS/FAIL-style gate result -- i.e. something that reads as evidence
# rather than pure prose brainstorming.
_NUMERIC_VERDICT_RE = re.compile(
    r"\b\d+\s*/\s*10\b"                 # "8 / 10" confidence
    r"|\$-?\d[\d,]*(?:\.\d+)?"          # dollar amounts
    r"|\b\d+(?:\.\d+)?%"                # percentages
    r"|\bSharpe\s*=?\s*-?\d"            # Sharpe=0.68
    r"|\b\d+/\d+\s+(?:PASS|FAIL)\b"     # "67/67 PASS"
    r"|\bexpectancy\D{0,15}[+-]?\$?\d"  # expectancy figures
)


@dataclass
class FileResult:
    path: str
    status: str
    cited: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    mtime: Optional[str] = None


def _extract_cited_paths(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _PATH_RE.finditer(text):
        p = m.group(1).strip().rstrip(").,;:'\"`]")
        if p and p not in seen:
            seen.add(p)
            found.append(p)
    return found


_TEST_FILE_INDEX: Optional[dict[str, Path]] = None
_TEST_INDEX_ROOTS = ("backtest", "crypto", "setup", "multi")


def _test_file_index() -> dict[str, Path]:
    """One-time repo-wide index of test_*.py basename -> first match. Building this once
    is far cheaper than a fresh **-glob per citation (a corpus of 1000+ files easily cites
    hundreds of bare test_*.py names)."""
    global _TEST_FILE_INDEX
    if _TEST_FILE_INDEX is not None:
        return _TEST_FILE_INDEX
    index: dict[str, Path] = {}
    for root_name in _TEST_INDEX_ROOTS:
        root = REPO / root_name
        if not root.exists():
            continue
        for p in root.rglob("test_*.py"):
            index.setdefault(p.name, p)
    _TEST_FILE_INDEX = index
    return index


def _resolve(p: str, repo_root: Path) -> Path:
    """Resolve a cited path relative to repo_root; bare test_*.py files are matched via
    the repo-wide test-file index (built against the REAL repo -- fine even when
    repo_root is a test fixture, since a bare test_*.py citation with no such file
    anywhere real is correctly treated as missing)."""
    candidate = repo_root / p
    if candidate.exists():
        return candidate
    if p.startswith("test_") and p.endswith(".py"):
        hit = _test_file_index().get(p)
        if hit is not None:
            return hit
    return candidate  # non-existent Path -- caller checks .exists()


def classify_file(path: Path, repo_root: Optional[Path] = None) -> FileResult:
    """Classify a single candidate/_analysis markdown file. Never raises -- unreadable
    files come back NOT-A-VERDICT with an empty citation list so a single bad file can't
    abort the batch.

    repo_root defaults to this module's REPO but accepts an override so callers (tests,
    or a caller running against a different checkout/worktree) can classify files that
    live outside the real repo tree without a relative_to() crash.
    """
    repo_root = repo_root if repo_root is not None else REPO
    try:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FileResult(path=rel, status="NOT-A-VERDICT")

    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        mtime = None

    if not _NUMERIC_VERDICT_RE.search(text):
        return FileResult(path=rel, status="NOT-A-VERDICT", mtime=mtime)

    cited = _extract_cited_paths(text)
    if not cited:
        return FileResult(path=rel, status="NO-ARTIFACT-CITED", mtime=mtime)

    missing = [c for c in cited if not _resolve(c, repo_root).exists()]
    status = "PROVENANCE-MISSING" if missing else "PROVENANCE-OK"
    return FileResult(path=rel, status=status, cited=cited, missing=missing, mtime=mtime)


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    if ANALYSIS_DIR.exists():
        files.extend(sorted(ANALYSIS_DIR.glob("*.md")))
    if CANDIDATES_DIR.exists():
        # Top-level candidate files (not the _analysis/_review-log/_LEADERBOARD control files).
        for p in sorted(CANDIDATES_DIR.glob("*.md")):
            if p.name.startswith("_"):
                continue
            files.append(p)
    return files


def run_audit(files: Optional[list[Path]] = None) -> dict:
    """Run the audit over `files` (default: the full corpus) and return the report dict.
    Pure function -- does not write to disk. Callers (main(), the reviewer hook, tests)
    decide what to do with the result."""
    files = files if files is not None else _candidate_files()
    rows = [classify_file(p) for p in files]

    scored = [r for r in rows if r.status != "NOT-A-VERDICT"]
    totals = {
        "PROVENANCE-OK": sum(1 for r in scored if r.status == "PROVENANCE-OK"),
        "PROVENANCE-MISSING": sum(1 for r in scored if r.status == "PROVENANCE-MISSING"),
        "NO-ARTIFACT-CITED": sum(1 for r in scored if r.status == "NO-ARTIFACT-CITED"),
        "NOT-A-VERDICT": sum(1 for r in rows if r.status == "NOT-A-VERDICT"),
    }
    total_scored = len(scored)
    fabricated_rate = (
        round(totals["PROVENANCE-MISSING"] / total_scored, 4) if total_scored else None
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files_scanned": len(rows),
        "files_scored": total_scored,
        "totals": totals,
        "fabricated_artifact_rate": fabricated_rate,
        "rows": [
            {
                "path": r.path,
                "status": r.status,
                "cited": r.cited,
                "missing": r.missing,
                "mtime": r.mtime,
            }
            for r in rows
        ],
    }


def _worst_offenders(report: dict, n: int = 30) -> list[dict]:
    missing_rows = [r for r in report["rows"] if r["status"] == "PROVENANCE-MISSING"]
    # Worst = most missing citations first, then most recent.
    missing_rows.sort(key=lambda r: (-len(r["missing"]), r.get("mtime") or ""), reverse=False)
    missing_rows.sort(key=lambda r: len(r["missing"]), reverse=True)
    return missing_rows[:n]


def _write_md(report: dict) -> None:
    t = report["totals"]
    lines = [
        "<!-- Generated by setup/scripts/kitchen_provenance_audit.py -- DO NOT HAND-EDIT. -->",
        f"<!-- generated_at={report['generated_at']} -->",
        "",
        "# Kitchen Provenance Audit",
        "",
        f"Scanned **{report['files_scanned']}** files "
        f"({report['files_scored']} carry a numeric verdict and were scored).",
        "",
        "| Status | Count |",
        "|---|---|",
        f"| PROVENANCE-OK | {t['PROVENANCE-OK']} |",
        f"| PROVENANCE-MISSING | {t['PROVENANCE-MISSING']} |",
        f"| NO-ARTIFACT-CITED | {t['NO-ARTIFACT-CITED']} |",
        f"| NOT-A-VERDICT (excluded) | {t['NOT-A-VERDICT']} |",
        "",
        f"**fabricated_artifact_rate** = PROVENANCE-MISSING / scored = "
        f"{report['fabricated_artifact_rate']}",
        "",
        "## 30 worst offenders (most missing citations first)",
        "",
        "| file | missing citations |",
        "|---|---|",
    ]
    for row in _worst_offenders(report, 30):
        missing = "; ".join(f"`{m}`" for m in row["missing"])
        lines.append(f"| `{row['path']}` | {missing} |")
    AUDIT_MD.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json-only", action="store_true", help="skip writing the markdown table")
    args = ap.parse_args()

    report = run_audit()
    AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.json_only:
        _write_md(report)

    t = report["totals"]
    print(
        f"[kitchen_provenance_audit] scanned={report['files_scanned']} scored={report['files_scored']} "
        f"OK={t['PROVENANCE-OK']} MISSING={t['PROVENANCE-MISSING']} "
        f"NO-ARTIFACT={t['NO-ARTIFACT-CITED']} NOT-A-VERDICT={t['NOT-A-VERDICT']} "
        f"fabricated_artifact_rate={report['fabricated_artifact_rate']} -> {AUDIT_JSON.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
