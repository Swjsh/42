"""worker_output_verify.py - the anti-fabrication gate for worker (subagent) output.

WHY THIS EXISTS
---------------
2026-08-18: the free-tier `strategist` role wrote
`analysis/manager/2026-08-18-2253-strategist-weekly-options-build.md`, a confident
completion report for the weekly-options build citing artifacts, file paths and
Monte-Carlo numbers that were **never written to disk** - while the real work was
genuinely in flight in another session. The master accepted it. Nothing caught it.

`gamma_manager._looks_like_garbage()` catches token-salad. It cannot catch a
*fluent* report about work that did not happen. That is the failure mode a
master/worker topology is structurally exposed to: the orchestrator only ever
sees the worker's summary, never its trace.

Research backing (analysis/deep-research/AGENT-ORCHESTRATION-2026-08-19.md,
adversarially verified): Anthropic, "Building effective agents" - "The autonomous
nature of agents means higher costs, and the potential for compounding errors";
the recommended mitigation is guardrails, not trust. This module is that
guardrail for the one thing a text summary can be checked against cheaply and
deterministically: the filesystem and the git object store.

WHAT IT CHECKS (deliberately narrow - everything here is decidable, $0, no LLM)
  1. Repo-relative FILE PATHS asserted in the report actually exist on disk.
  2. GIT SHAs asserted in the report actually resolve (`git cat-file -t`).
  3. Whether the report uses COMPLETION language ("wrote", "committed", "shipped").

A missing artifact + completion language == FABRICATED. A missing artifact with
only proposal language ("we should write X") is merely UNVERIFIED - proposing a
path that does not exist yet is legitimate.

WHAT IT DOES NOT CHECK (stated, not silently skipped - OP-33)
  * Numeric claims (P&L, Sharpe, Monte-Carlo results). Not decidable from text.
  * Whether an existing file's CONTENT supports the claim made about it.
  * Semantic correctness of anything.
A VERIFIED verdict means "every artifact this report names exists", NOT "this
report is true".

KNOWN FALSE POSITIVE: a post-mortem that QUOTES fabricated filenames as evidence
trips the gate (analysis/deep-research/AGENT-ORCHESTRATION-2026-08-19.md does).
No opt-out marker is provided on purpose - a worker could emit one to evade the
gate. Scope this to worker output under analysis/manager/, where that trade is
correct, and read human-authored post-mortems with your eyes.

USAGE
  python setup/scripts/worker_output_verify.py <report.md> [--json] [--quiet]
  cat report.md | python setup/scripts/worker_output_verify.py - --json

EXIT CODES  0 = VERIFIED / NO_CLAIMS   2 = UNVERIFIED   3 = FABRICATED
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Extensions worth verifying. A claim about foo.py is checkable; prose is not.
_EXTS = (
    "py", "md", "json", "jsonl", "csv", "ps1", "psm1", "txt", "yml", "yaml",
    "ts", "tsx", "js", "jsx", "bat", "vbs", "sh", "toml", "ini", "html", "css",
)

# A path-ish token: slash-separated, known extension, not glued to other word chars.
_PATH_RE = re.compile(
    r"(?<![\w/\\.-])"
    r"((?:[\w.@+-]+[/\\])+[\w.@+-]+\.(?:" + "|".join(_EXTS) + r"))"
    r"(?![\w])",
    re.IGNORECASE,
)

# A bare filename with a known extension, as it appears in `backticks` or a
# [markdown](link). The 2026-08-18 fabrication used exactly this shape - a table
# of ./expiry_selector.py links - so slash-anchored paths alone are not enough.
_BARE_RE = re.compile(
    r"(?:`([\w.@+-]+\.(?:" + "|".join(_EXTS) + r"))`"
    r"|\]\(\.?/?([\w./@+-]+\.(?:" + "|".join(_EXTS) + r"))\))",
    re.IGNORECASE,
)

# Bare 7-40 char hex that reads like a git object reference. Must contain at
# least one a-f letter: an all-digit run is a date (20260818) or an id, not a sha.
_SHA_RE = re.compile(r"(?<![0-9a-fA-F])(?=[0-9a-f]{7,40}(?![0-9a-fA-F]))(?=[0-9]*[a-f])([0-9a-f]{7,40})")

# Claim-of-completion vocabulary. Deliberately broad.
_DONE_RE = re.compile(
    r"\b(wrote|written|created|added|shipped|committed|commit|saved|generated|"
    r"produced|landed|implemented|delivered|persisted|emitted|appended|"
    r"now exists|lives at|output to)\b",
    re.IGNORECASE,
)

# Proposal vocabulary - downgrades a miss from FABRICATED to UNVERIFIED when no
# completion language is present.
_PROPOSE_RE = re.compile(
    r"\b(should|would|propose|proposed|plan to|next step|recommend|recommended|"
    r"could|todo|to-?do|draft|suggest|suggested|if we|we can)\b",
    re.IGNORECASE,
)


def _repo_roots() -> set:
    """Top-level names that actually exist in the checkout.

    A path claim only counts if its first segment is a real repo root. Without
    this, illustrative paths (src/app/main.py) from a model's training data would
    flood the report with false fabrication findings.
    """
    try:
        return {p.name for p in REPO.iterdir()}
    except OSError:
        return set()


def _sha_exists(sha: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=str(REPO), capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0 and r.stdout.strip() in {"commit", "blob", "tree", "tag"}
    except (OSError, subprocess.SubprocessError):
        return False    # fail LOUD: an unverifiable sha is not a verified sha


def _looks_like_sha_context(text: str, start: int) -> bool:
    """Only treat hex as a git sha when the surrounding words say so.

    Bare hex appears in hashes, ids and colour codes all over this repo's state
    files; verifying all of it would be noise.
    """
    window = text[max(0, start - 60):start].lower()
    return any(w in window for w in ("commit", "sha", "revision", "git ", "revert"))


_BASENAME_INDEX = None

# Third-party / generated trees whose filenames are not this project's artifacts.
_VENDOR_SEGMENTS = {
    "node_modules", ".venv", "venv", ".tts-venv", "site-packages", ".git",
    "worktrees", "__pycache__", ".next", "dist", "build", ".mypy_cache",
    ".pytest_cache", "egg-info",
}


def _basename_index() -> set:
    """Every filename git knows about, tracked or untracked-but-present.

    Used to resolve a BARE filename claim (`expiry_selector.py`) that carries no
    directory. Resolving by basename is deliberately generous - the goal is to
    avoid false FABRICATED verdicts, not to prove the path is the right one.
    """
    global _BASENAME_INDEX
    if _BASENAME_INDEX is not None:
        return _BASENAME_INDEX
    names = set()
    # `--others` WITHOUT --exclude-standard on purpose: gitignored-but-real files
    # (automation/state/fleet/secrets.json, .mcp.json) are legitimate artifacts to
    # cite, and omitting them produced a false FABRICATED on a genuine J brief.
    for args in (["git", "ls-files"], ["git", "ls-files", "--others"]):
        try:
            r = subprocess.run(args, cwd=str(REPO), capture_output=True,
                               text=True, timeout=120, errors="replace")
            if r.returncode != 0:
                continue
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                segs = line.lower().split("/")
                if any(s in _VENDOR_SEGMENTS for s in segs[:-1]):
                    continue              # third-party trees are not our artifacts
                names.add(segs[-1])
        except (OSError, subprocess.SubprocessError):
            pass    # partial index -> conservative; a miss here can only over-flag
    _BASENAME_INDEX = names
    return names


def extract_claims(text: str) -> dict:
    roots = _repo_roots()
    paths, seen = [], set()
    for m in _PATH_RE.finditer(text):
        raw = m.group(1).replace("\\", "/").strip("/")
        if raw.split("/", 1)[0] not in roots:
            continue                      # not a claim about THIS repo
        if raw in seen:
            continue
        seen.add(raw)
        paths.append(raw)

    bare = []
    for m in _BARE_RE.finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace("\\", "/").lstrip("./")
        if not raw or raw in seen:
            continue
        if "/" in raw and raw.split("/", 1)[0] in roots:
            seen.add(raw)
            paths.append(raw)             # it was really a repo path after all
            continue
        name = raw.rsplit("/", 1)[-1]
        if name in seen:
            continue
        seen.add(name)
        bare.append(name)

    shas, seen_s = [], set()
    for m in _SHA_RE.finditer(text):
        sha = m.group(1)
        if sha in seen_s or not _looks_like_sha_context(text, m.start()):
            continue
        seen_s.add(sha)
        shas.append(sha)

    return {"paths": paths, "bare": bare, "shas": shas}


def verify(text: str, report_dir: Path = None) -> dict:
    claims = extract_claims(text)
    says_done = bool(_DONE_RE.search(text))
    says_propose = bool(_PROPOSE_RE.search(text))

    path_results = [{"path": p, "exists": (REPO / p).exists()} for p in claims["paths"]]

    idx = _basename_index() if claims["bare"] else set()
    for name in claims["bare"]:
        beside = bool(report_dir and (report_dir / name).exists())
        path_results.append({
            "path": name,
            "exists": beside or name.lower() in idx,
            "resolved_by": "beside_report" if beside else "basename",
        })

    sha_results = [{"sha": s, "exists": _sha_exists(s)} for s in claims["shas"]]

    missing_paths = [r["path"] for r in path_results if not r["exists"]]
    missing_shas = [r["sha"] for r in sha_results if not r["exists"]]
    n_claims = len(path_results) + len(sha_results)
    n_missing = len(missing_paths) + len(missing_shas)

    if n_claims == 0:
        verdict, code = "NO_CLAIMS", 0
    elif n_missing == 0:
        verdict, code = "VERIFIED", 0
    elif says_done:
        verdict, code = "FABRICATED", 3
    else:
        verdict, code = "UNVERIFIED", 2

    # A missing git sha is never merely "proposed" - you cannot propose a sha.
    if missing_shas and verdict == "UNVERIFIED":
        verdict, code = "FABRICATED", 3

    return {
        "verdict": verdict,
        "exit_code": code,
        "n_claims": n_claims,
        "n_missing": n_missing,
        "missing_paths": missing_paths,
        "missing_shas": missing_shas,
        "paths": path_results,
        "shas": sha_results,
        "says_completion": says_done,
        "says_proposal": says_propose,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a worker report's artifact claims against disk + git.")
    ap.add_argument("report", nargs="+",
                    help="one or more report paths, or '-' for stdin (batch shares one file index)")
    ap.add_argument("--json", action="store_true", help="emit the full result(s) as JSON")
    ap.add_argument("--quiet", action="store_true", help="verdict line only")
    ap.add_argument("--only-bad", action="store_true",
                    help="in batch mode print only UNVERIFIED / FABRICATED rows")
    a = ap.parse_args()

    icon = {"VERIFIED": "OK", "NO_CLAIMS": "--", "UNVERIFIED": "??", "FABRICATED": "!!"}
    results, worst = [], 0

    for target in a.report:
        if target == "-":
            text, label, rdir = sys.stdin.read(), "<stdin>", None
        else:
            p = Path(target)
            if not p.is_absolute():
                p = REPO / p
            if not p.exists():
                print("worker_output_verify: report not found: %s" % p, file=sys.stderr)
                worst = max(worst, 1)
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            rdir = p.parent
            try:
                label = str(p.relative_to(REPO))
            except ValueError:
                label = str(p)

        res = verify(text, report_dir=rdir)
        res["report"] = label
        results.append(res)
        worst = max(worst, res["exit_code"])

        if a.json:
            continue
        if a.only_bad and res["verdict"] in ("VERIFIED", "NO_CLAIMS"):
            continue
        print("[%s] %s  %s  (%d/%d artifacts resolve)" % (
            icon[res["verdict"]], res["verdict"], label,
            res["n_claims"] - res["n_missing"], res["n_claims"]))
        if not a.quiet:
            for m in res["missing_paths"]:
                print("     MISSING FILE: %s" % m)
            for m in res["missing_shas"]:
                print("     MISSING COMMIT: %s" % m)

    if a.json:
        print(json.dumps(results[0] if len(results) == 1 else results, indent=2))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
