"""github_audit.py -- secrets & privacy audit before any push to Swjsh/42 (PUBLIC repo).

Scans every git-tracked file for hardcoded API keys, tokens, and credential-like
strings; verifies .gitignore covers all known secret file types; reports a clear
GREEN / RED verdict with exact file:line citations.

Usage:
    python setup/scripts/github_audit.py              # scan working tree
    python setup/scripts/github_audit.py --history    # also scan git commit log (slow ~30-90s)
    python setup/scripts/github_audit.py --json       # machine-readable output to stdout

Allowlist: append  # noqa:secret-ok  to any line that triggers a false positive.
Exit codes: 0 = GREEN, 1 = RED (findings), 2 = tool error.

Stdlib only -- zero new dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── Secret patterns ───────────────────────────────────────────────────────────

# Each entry: (compiled_regex, label, severity)
SECRET_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # Alpaca paper/live API key -- PK + 24 uppercase alphanumeric chars
    (re.compile(r'\bPK[A-Z0-9]{24}\b'), "Alpaca API key", "HIGH"),
    # Alpaca secret key in a variable assignment (py/js/json)
    (re.compile(
        r'(?:ALPACA_SECRET_KEY|APCA-API-SECRET-KEY)\s*["\']?\s*[:=]\s*["\']([A-Za-z0-9+/=_\-]{30,})["\']',
        re.IGNORECASE,
    ), "Alpaca secret key assignment", "HIGH"),
    # Any long string value (40+ chars) assigned to a variable whose name
    # contains secret / token / password / credential / auth_key
    (re.compile(
        r'(?:secret|token|password|credential|auth.?key)\s*[=:]\s*["\']([A-Za-z0-9+/=_\-]{40,})["\']',
        re.IGNORECASE,
    ), "Long string near secret-named variable", "MEDIUM"),
    # OpenRouter API key
    (re.compile(r'\bsk-or-v1-[a-zA-Z0-9]{40,}\b'), "OpenRouter API key", "HIGH"),
    # Generic long bare string in code files (heuristic, LOW).
    # Requires: 43 chars, NO underscores/hyphens (real secrets like Alpaca keys are
    # pure alphanumeric; JSON key names always contain underscores -- filter them out),
    # AND must have mixed case + at least one digit (entropy check).
    # Only applies to .py / .js / .ts / .ps1 files.
    (re.compile(r'["\'](?=[A-Za-z0-9+/=]{43}["\'])(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[A-Za-z0-9+/=]{43}["\']'),
     "Possible 43-char credential (check manually)", "LOW"),
]

# File extensions for the heuristic long-string scan (avoid scanning docs / data)
CODE_EXTENSIONS = {".py", ".js", ".ts", ".ps1", ".sh", ".json", ".env"}

# Extensions to SKIP entirely (binary, large data, never contain secrets as text)
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".npz", ".npy", ".mat", ".pkl", ".parquet", ".csv",
    ".zip", ".tar", ".gz", ".7z",
    ".ttf", ".woff", ".woff2", ".eot",
    ".exe", ".dll", ".so", ".dylib",
}

# ── Gitignore required patterns ───────────────────────────────────────────────

REQUIRED_GITIGNORE_PATTERNS: list[tuple[str, str]] = [
    (".mcp.json",                             "Project-root MCP config with live Alpaca keys"),
    ("**/.mcp.json",                          "Nested .mcp.json anywhere"),
    ("**/.discord-config.json",               "Discord config with token"),
    ("**/.discord-token",                     "Discord bot token"),
    ("**/.alpaca-keys",                       "Alpaca key file"),
    ("**/.openrouter.key",                    "OpenRouter API key"),
    ("**/.heartbeat-api-key",                 "Heartbeat API key (Safe)"),
    ("**/.heartbeat-api-key-bold",            "Heartbeat API key (Bold)"),
    ("automation/state/fleet/secrets.json",   "Fleet per-account API secrets"),
    ("**/fleet-secrets.json",                 "Fleet secrets (alt name)"),
    (".env.tastytrade",                       "TastyTrade credentials"),
]

# Tracked files that should have been gitignored -- flag as RED if found
BLOCKED_TRACKED_PATTERNS = [
    (re.compile(r'(^|/)\.mcp\.json$'),         ".mcp.json contains live API keys"),
    (re.compile(r'(^|/)fleet.secrets\.json$'), "fleet secrets file"),
    (re.compile(r'secrets\.json$'),            "file named secrets.json"),
    (re.compile(r'\.(pem|p12|pfx)$'),          "certificate/private-key file"),
    (re.compile(r'\.env(\.|$)'),               ".env file"),
    (re.compile(r'\.heartbeat-api-key'),       "heartbeat API key file"),
    (re.compile(r'\.alpaca-keys'),             "alpaca key file"),
    (re.compile(r'\.openrouter\.key'),         "openrouter key file"),
    (re.compile(r'\.discord-token'),           "discord token file"),
]

# ── Finding dataclass ─────────────────────────────────────────────────────────

@dataclass
class Finding:
    category: Literal["SECRET", "GITIGNORE", "TRACKED_FILE", "HISTORY"]
    severity: Literal["HIGH", "MEDIUM", "LOW", "INFO"]
    path: str
    line: int | None
    label: str
    snippet: str = ""
    fix: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 120) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=timeout
    )
    return result.stdout


def _git_tracked_files() -> list[Path]:
    output = _run(["git", "ls-files"])
    paths = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        p = PROJECT_ROOT / line
        if p.exists() and p.is_file():
            paths.append(p)
    return paths


def _read_gitignore() -> str:
    gi = PROJECT_ROOT / ".gitignore"
    return gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""


def _safe_print(text: str) -> None:
    """Print without crashing on Windows cp1252 consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


# ── Scan: secret patterns in tracked files ───────────────────────────────────

def scan_secrets(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in SKIP_EXTENSIONS:
            continue
        is_code = suffix in CODE_EXTENSIONS
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if "# noqa:secret-ok" in line:
                continue
            for pattern, label, severity in SECRET_PATTERNS:
                # Low-severity long-string heuristic only on code files
                if severity == "LOW" and not is_code:
                    continue
                if pattern.search(line):
                    snippet = line[:120].strip()
                    findings.append(Finding(
                        category="SECRET",
                        severity=severity,
                        path=rel,
                        line=lineno,
                        label=label,
                        snippet=snippet,
                        fix=(
                            "Load from .mcp.json at runtime -- see _load_account_keys() in "
                            "setup/scripts/fast_path_executor.py for the canonical pattern."
                        ) if severity == "HIGH" else "Verify this is not a live credential.",
                    ))
                    break  # one finding per line is enough
    return findings


# ── Scan: gitignore coverage ──────────────────────────────────────────────────

def scan_gitignore() -> list[Finding]:
    findings: list[Finding] = []
    content = _read_gitignore()
    for pattern, description in REQUIRED_GITIGNORE_PATTERNS:
        # Strip glob anchoring for a simple substring check
        needle = pattern.lstrip("**/").lstrip("*").lstrip("/")
        if needle not in content:
            findings.append(Finding(
                category="GITIGNORE",
                severity="HIGH",
                path=".gitignore",
                line=None,
                label=f"Missing gitignore pattern: {pattern}",
                snippet=f"Protects: {description}",
                fix=f'Add  {pattern}  to the "# Secrets" block in .gitignore',
            ))
    return findings


# ── Scan: blocked file types that are currently tracked ──────────────────────

def scan_tracked_file_types(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        for pattern, description in BLOCKED_TRACKED_PATTERNS:
            if pattern.search(rel):
                findings.append(Finding(
                    category="TRACKED_FILE",
                    severity="HIGH",
                    path=rel,
                    line=None,
                    label=f"Blocked file type tracked: {description}",
                    snippet="",
                    fix=(
                        f"Add to .gitignore, then: "
                        f"git rm --cached {rel} && git commit -m 'chore: untrack secret file'"
                    ),
                ))
    return findings


# ── Scan: git history ─────────────────────────────────────────────────────────

def scan_history() -> list[Finding]:
    """Scan full git log -p for secret patterns. SLOW (~30-90s)."""
    findings: list[Finding] = []
    _safe_print("[github-audit] scanning git history (this takes ~30-90s) ...")
    diff_output = _run(["git", "log", "-p", "--all", "--", "."], timeout=300)
    current_file = "<unknown>"
    current_commit = "<unknown>"
    for raw_line in diff_output.splitlines():
        if raw_line.startswith("commit "):
            current_commit = raw_line.split()[1][:12]
        elif raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            line = raw_line[1:]
            if "# noqa:secret-ok" in line:
                continue
            for pattern, label, severity in SECRET_PATTERNS:
                if severity == "LOW":
                    continue
                if pattern.search(line):
                    findings.append(Finding(
                        category="HISTORY",
                        severity=severity,
                        path=f"{current_file} (commit {current_commit})",
                        line=None,
                        label=f"[HISTORY] {label}",
                        snippet=line.strip()[:120],
                        fix=(
                            "Secret is in git history -- ROTATE the key immediately. "
                            "Rewrite history with 'git filter-repo' (or BFG Repo Cleaner), "
                            "then force-push. Do NOT push until history is clean."
                        ),
                    ))
                    break
    # Deduplicate by label+snippet prefix
    seen: set[str] = set()
    deduped = []
    for f in findings:
        key = f"{f.label}|{f.snippet[:40]}"
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


# ── Reporting ─────────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
SEV_ICON = {"HIGH": "[HIGH]", "MEDIUM": "[MED] ", "LOW": "[LOW] ", "INFO": "[INFO]"}
WIDTH = 62


def report_text(findings: list[Finding], file_count: int, elapsed: float) -> int:
    """Print human-readable report. Returns exit code (0=GREEN, 1=RED)."""
    now_et = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _safe_print("=" * WIDTH)
    _safe_print(f"GITHUB SECRETS & PRIVACY AUDIT -- {now_et}")
    _safe_print("Repo: https://github.com/Swjsh/42  (PUBLIC)")
    _safe_print("=" * WIDTH)
    _safe_print(f"\n[SCAN] {file_count} tracked files in {elapsed:.1f}s\n")

    if not findings:
        _safe_print("  OK  No findings.\n")
        _safe_print("=" * WIDTH)
        _safe_print("VERDICT: GREEN -- safe to push")
        _safe_print("=" * WIDTH)
        return 0

    cats: dict[str, list[Finding]] = {}
    for f in sorted(findings, key=lambda x: (x.category, SEVERITY_ORDER[x.severity])):
        cats.setdefault(f.category, []).append(f)

    high_count = sum(1 for f in findings if f.severity == "HIGH")
    medium_count = sum(1 for f in findings if f.severity == "MEDIUM")

    for cat, items in cats.items():
        _safe_print(f"-- {cat} --")
        for f in items:
            loc = f"{f.path}:{f.line}" if f.line else f.path
            _safe_print(f"  {SEV_ICON[f.severity]}  {loc}")
            _safe_print(f"           {f.label}")
            if f.snippet:
                _safe_print(f"           snippet: {f.snippet[:80]}")
            if f.fix:
                _safe_print(f"           fix:     {f.fix[:100]}")
        _safe_print("")

    verdict_colour = "RED" if (high_count or medium_count) else "YELLOW"
    _safe_print("=" * WIDTH)
    _safe_print(
        f"VERDICT: {verdict_colour} -- {len(findings)} finding(s) "
        f"({high_count} HIGH, {medium_count} MEDIUM)"
    )
    _safe_print("Fix all HIGH/MEDIUM findings before git push.")
    _safe_print("=" * WIDTH)
    return 1 if (high_count or medium_count) else 0


def report_json_output(findings: list[Finding], file_count: int, elapsed: float) -> int:
    high = sum(1 for f in findings if f.severity == "HIGH")
    medium = sum(1 for f in findings if f.severity == "MEDIUM")
    verdict = "GREEN" if not findings else ("RED" if (high or medium) else "YELLOW")
    out = {
        "verdict": verdict,
        "files_scanned": file_count,
        "elapsed_s": round(elapsed, 2),
        "findings": [
            {
                "category": f.category,
                "severity": f.severity,
                "path": f.path,
                "line": f.line,
                "label": f.label,
                "snippet": f.snippet,
                "fix": f.fix,
            }
            for f in findings
        ],
    }
    print(json.dumps(out, indent=2))
    return 0 if verdict == "GREEN" else 1


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub secrets & privacy audit")
    parser.add_argument("--history", action="store_true",
                        help="Also scan git commit history (slow, ~30-90s)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON output instead of human-readable text")
    args = parser.parse_args()

    import time
    t0 = time.monotonic()

    try:
        files = _git_tracked_files()
    except Exception as exc:
        print(f"ERROR: cannot list tracked files: {exc}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    findings.extend(scan_gitignore())
    findings.extend(scan_tracked_file_types(files))
    findings.extend(scan_secrets(files))
    if args.history:
        findings.extend(scan_history())

    elapsed = time.monotonic() - t0

    if args.json:
        return report_json_output(findings, len(files), elapsed)
    return report_text(findings, len(files), elapsed)


if __name__ == "__main__":
    sys.exit(main())
