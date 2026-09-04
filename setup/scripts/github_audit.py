"""github_audit.py -- secrets & privacy audit before any push to Swjsh/42 (PUBLIC repo).

Scans every git-tracked file for hardcoded API keys, tokens, and credential-like
strings; verifies .gitignore covers all known secret file types; reports a clear
GREEN / RED verdict with exact file:line citations.

Usage:
    python setup/scripts/github_audit.py              # scan working tree
    python setup/scripts/github_audit.py --history    # also scan git commit log (slow ~30-90s)
    python setup/scripts/github_audit.py --json       # machine-readable output to stdout
    python setup/scripts/github_audit.py --staged     # scan only STAGED file content (pre-commit gate)

Allowlist: append  # noqa:secret-ok  to any line that triggers a false positive.
Exit codes: 0 = GREEN, 1 = RED (findings), 2 = tool error.

All reported snippets REDACT any matched secret to its first 4 characters + '...' --
this file's own output is safe to paste into a chat/PR/log even when it finds a hit.

Stdlib only -- zero new dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash on win32 (OP-27 L41)
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


def _detect_project_root() -> Path:
    """Resolve the repo root this audit operates on.

    Prefers `git rev-parse --show-toplevel` from the CURRENT working directory, so
    the CLI operates on whatever repo it's invoked from (e.g. an isolated repo under
    a test's scratch dir, or a scratch clone) -- falling back to this file's own
    on-disk location (parents[2]) if that fails (not inside a git repo, git missing).

    In production the pre-commit hook always invokes this script with cwd at the 42
    repo's top level (git's documented hook cwd), so the two agree byte-for-byte --
    existing CLI behaviour there is unchanged.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return Path(top).resolve()
    except Exception:
        pass
    return Path(__file__).resolve().parents[2]


# LAZY (2026-09-03, GAMMA-DOCTRINE-CREDENTIAL-GUARD): _detect_project_root() shells out
# to `git rev-parse`. Computing it eagerly at import time meant merely IMPORTING this
# module for its SECRET_PATTERNS/scan_text -- e.g. from setup/hooks/doctrine.py, which
# needs them on every PreToolUse Write/Edit/Bash call -- paid a subprocess launch it never
# uses. _project_root() computes once, lazily, on first actual need. There was no prior
# external caller of a bare `PROJECT_ROOT` module attribute (verified by repo-wide grep
# 2026-09-03), so this drops the eager global entirely rather than shadowing it behind a
# module __getattr__ -- every internal call site now calls _project_root() explicitly.
_PROJECT_ROOT_CACHE: Path | None = None


def _project_root() -> Path:
    global _PROJECT_ROOT_CACHE
    if _PROJECT_ROOT_CACHE is None:
        _PROJECT_ROOT_CACHE = _detect_project_root()
    return _PROJECT_ROOT_CACHE

# ── Secret patterns ───────────────────────────────────────────────────────────

# Each entry: (compiled_regex, label, severity)
#
# Live-key blind spot fix (2026-09-03, GITHUB-AUDIT-NO-LIVE-KEY-PATTERN): before this
# change, every pattern below matched PAPER-shaped Alpaca credentials only (PK-prefix).
# A live-money Alpaca key (AK-prefix) could have sat in the tree or history and every
# scan would have read GREEN. Verified from THIS repo's own gitignored credential
# homes (structure/lengths only, values never read into this file or printed):
#   - .mcp.json / automation/state/fleet/secrets.json: every live paper key is
#     `PK` + 24 uppercase-alnum (26 total) -- confirms the existing PK pattern's
#     length. The matching Alpaca secret is exactly 44 chars, pure alphanumeric,
#     mixed case + digit (NOT the 43-char generic heuristic below -- one char short).
#   - automation/state/.discord-config.json: bot_token is 3 dot-separated segments,
#     26/6/38 chars, [A-Za-z0-9_-] -- matches Discord's publicly documented bot-token
#     shape.
#   - automation/kalshi/kalshi_client.py docstring: kalshi-1 credentials are an RSA
#     PEM (`secret_path` / inline `secret` starting `----- BEGIN RSA PRIVATE KEY -----`).
#   - setup/scripts/run_minimax.py validates OpenRouter keys by `.startswith("sk-or-")`
#     only (NOT "sk-or-v1-") -- the existing OpenRouter pattern below required the
#     literal "v1-" segment, so a v2+ (or unversioned) key would have slipped past it.
# NO Alpaca LIVE key has ever existed in this repo (verified separately by hand, HIGH
# severity, unarmed) so its exact body length is UNVERIFIED here -- Alpaca live and
# paper key IDs share one key-generation system and the paper body is confirmed 24
# chars; the pattern below uses an 18-26 range centered on that confirmed length
# rather than a single guessed value. Tighten it the moment real evidence (an Alpaca
# support page, or -- better -- never -- a real leaked live key) pins the exact length.
SECRET_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # Alpaca paper/live API key -- PK + 24 uppercase alphanumeric chars
    (re.compile(r'\bPK[A-Z0-9]{24}\b'), "Alpaca API key", "HIGH"),
    # Alpaca LIVE API key -- AK + 18-26 uppercase alphanumeric chars. Length range is
    # UNVERIFIED (see header comment above) -- no live key has ever existed in this
    # repo to confirm against. Centered on the confirmed paper-key body length (24).
    (re.compile(r'\bAK[A-Z0-9]{18,26}\b'),
     "Alpaca LIVE API key (length unverified -- see SECRET_PATTERNS header)", "HIGH"),
    # Alpaca secret key in a variable assignment (py/js/json)
    (re.compile(
        r'(?:ALPACA_SECRET_KEY|APCA-API-SECRET-KEY)\s*["\']?\s*[:=]\s*["\']([A-Za-z0-9+/=_\-]{30,})["\']',
        re.IGNORECASE,
    ), "Alpaca secret key assignment", "HIGH"),
    # Alpaca secret key, BARE shape -- exactly 44 chars, pure alphanumeric, mixed
    # case + digit (confirmed against this repo's own .mcp.json / secrets.json
    # structure, values never read into this scanner). Catches a secret pasted
    # without ALPACA_SECRET_KEY-style variable-name context (e.g. a JSON value
    # under an unrelated key name). One char longer than the generic 43-char LOW
    # heuristic below, which would otherwise miss it entirely.
    # QUOTE-ANCHORED (mirrors the 43-char LOW heuristic's lookahead style) so it
    # matches only a value whose ENTIRE quoted string is exactly 44 chars -- not a
    # 44-char substring of a longer blob. Without this anchor the pattern false-
    # positived on every sha512 package-lock.json integrity hash in this repo (a
    # long base64 blob happens to contain 44-alnum runs between '+'/'/' bytes);
    # verified during this fix by running the full-tree scan before/after.
    (re.compile(r'["\'](?=[A-Za-z0-9]{44}["\'])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{44}["\']'),
     "Possible Alpaca secret key (bare 44-char, unlabeled)", "MEDIUM"),
    # Any long string value (40+ chars) assigned to a variable whose name
    # contains secret / token / password / credential / auth_key / refresh
    (re.compile(
        r'(?:secret|token|password|credential|auth.?key|refresh)\s*[=:]\s*["\']([A-Za-z0-9+/=_\-]{40,})["\']',
        re.IGNORECASE,
    ), "Long string near secret-named variable", "MEDIUM"),
    # OpenRouter API key -- "sk-or-" prefix only (matches the runtime's own
    # validation in setup/scripts/run_minimax.py, which checks .startswith("sk-or-")
    # and does NOT require a "v1-" version segment). The old pattern hardcoded
    # "v1-" and would miss any future/unversioned OpenRouter key shape.
    (re.compile(r'\bsk-or-(?:v\d+-)?[a-zA-Z0-9]{20,}\b'), "OpenRouter API key", "HIGH"),
    # Discord bot token -- 3 dot-separated segments. Range centered on this repo's
    # own automation/state/.discord-config.json bot_token shape (26/6/38 chars,
    # confirmed by length only, value never read into this scanner), padded per
    # Discord's publicly documented token format.
    (re.compile(r'\b[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,40}\b'),
     "Discord bot token", "HIGH"),
    # Private key PEM block (RSA/EC/DSA/OpenSSH/generic PKCS8) -- confirmed live in
    # this repo: automation/kalshi/kalshi_client.py's `secret` field holds an inline
    # "----- BEGIN RSA PRIVATE KEY -----" PEM when secret_path isn't used.
    (re.compile(r'-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|ENCRYPTED)?\s*PRIVATE KEY-----'),
     "Private key PEM block", "HIGH"),
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
        cmd, capture_output=True, text=True, cwd=str(_project_root()), timeout=timeout,
        encoding="utf-8", errors="replace",
        creationflags=_CREATE_NO_WINDOW,
    )
    return result.stdout


def _git_tracked_files() -> list[Path]:
    output = _run(["git", "ls-files"])
    paths = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        p = _project_root() / line
        if p.exists() and p.is_file():
            paths.append(p)
    return paths


def _read_gitignore() -> str:
    gi = _project_root() / ".gitignore"
    return gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""


def _safe_print(text: str) -> None:
    """Print without crashing on Windows cp1252 consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _redact(line: str, matched: str) -> str:
    """Replace the matched secret substring in `line` with its first 4 chars + '...'.

    Security fix (2026-09-03): both the full-tree scan and the staged pre-commit scan
    used to print the raw matched secret in the snippet/fix report. Redact in BOTH.
    """
    if not matched:
        return line
    redacted = matched[:4] + "..."
    return line.replace(matched, redacted)


# ── Scan: secret patterns in one (path, text) pair ────────────────────────────
# Shared by the full tracked-file scan and the fast --staged pre-commit scan so the
# pattern list + matching/redaction logic lives in exactly one place.

_NOQA_RE = re.compile(r"(?:#|//|--|/\*|<!--)\s*noqa:secret-ok")


def _is_allowlisted(line: str) -> bool:
    """True if the line carries the false-positive marker in ANY comment style.

    Was hardcoded to "# noqa:secret-ok", so no JS/TS/SQL/HTML file in this repo
    could EVER be allowlisted -- gamma-companion/lib/push.js tripped the PEM
    pattern on PKCS8 header boilerplate and had no way to say so (2026-09-03).
    A scanner that stays RED on an un-silenceable false positive is a scanner
    people learn to ignore, which is how the earlier leaks survived.
    """
    return bool(_NOQA_RE.search(line))

def scan_text(path: str, text: str, *, is_code: bool = True) -> list[Finding]:
    """Scan `text` (the content of `path`) for secret patterns. `path` is used only
    as the Finding.path label -- caller decides what string to pass (a working-tree
    relative path, or a staged-file path). Snippets are redacted (see _redact)."""
    findings: list[Finding] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if _is_allowlisted(line):
            continue
        for pattern, label, severity in SECRET_PATTERNS:
            # Low-severity long-string heuristic only on code files
            if severity == "LOW" and not is_code:
                continue
            m = pattern.search(line)
            if m:
                matched = m.group(1) if m.groups() else m.group(0)
                snippet = _redact(line[:120].strip(), matched)
                findings.append(Finding(
                    category="SECRET",
                    severity=severity,
                    path=path,
                    line=lineno,
                    label=label,
                    snippet=snippet,
                    fix=_fix_hint_for_label(label, severity),
                ))
                break  # one finding per line is enough
    return findings


def _fix_hint_for_label(label: str, severity: str) -> str:
    """Per-credential-family fix hint pointing at the runtime loader that should
    have read this secret instead of it being hardcoded. Falls back to the
    original generic Alpaca hint for HIGH/MEDIUM, or a verify-manually note for LOW,
    when a label doesn't match a known family (keeps old behaviour for callers /
    tests that don't care about the new families)."""
    if "Alpaca" in label:
        return (
            "Load from .mcp.json at runtime -- see _load_account_keys() in "
            "setup/scripts/fast_path_executor.py for the canonical pattern."
        )
    if "OpenRouter" in label:
        return (
            "Load from automation/state/.openrouter.key or OPENROUTER_API_KEY env var "
            "-- see setup/scripts/run_minimax.py KEY_FILE loader."
        )
    if "Discord" in label:
        return (
            "Load from the gitignored .discord-config.json bot_token field -- see "
            "setup/scripts/discord-bridge.py."
        )
    if "Private key" in label or "PEM" in label:
        return (
            "Load from automation/state/fleet/secrets.json (secret_path -> a "
            "gitignored .pem file, or inline secret) -- see load_credentials() in "
            "automation/kalshi/kalshi_client.py. ROTATE immediately if this was a "
            "real key."
        )
    if severity == "HIGH":
        return (
            "Load from .mcp.json at runtime -- see _load_account_keys() in "
            "setup/scripts/fast_path_executor.py for the canonical pattern."
        )
    if severity == "MEDIUM":
        return "Verify this is not a live credential; move it to a gitignored secrets store if it is."
    return "Verify this is not a live credential."


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
        rel = str(path.relative_to(_project_root())).replace("\\", "/")
        findings.extend(scan_text(rel, text, is_code=is_code))
    return findings


# ── Scan: secret patterns in STAGED file content (pre-commit gate) ───────────

def _git_staged_files() -> list[str]:
    """Staged paths (git-style forward slashes) for Added/Copied/Modified changes.
    Deleted/renamed-away paths are excluded on purpose -- there is no staged blob
    left to scan for a delete, and `git show :path` would just fail for one."""
    output = _run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _git_show_staged(path: str) -> str | None:
    """Read the STAGED content of `path` (the index blob, NOT the working-tree file)
    via `git show :path`. Returns None if the path has no staged blob (e.g. raced
    with an unstage between listing and reading)."""
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(_project_root()),
        timeout=30, creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def scan_staged(staged_files: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for rel in staged_files:
        suffix = Path(rel).suffix.lower()
        if suffix in SKIP_EXTENSIONS:
            continue
        is_code = suffix in CODE_EXTENSIONS
        text = _git_show_staged(rel)
        if text is None:
            continue
        findings.extend(scan_text(rel, text, is_code=is_code))
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
        rel = str(path.relative_to(_project_root())).replace("\\", "/")
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
    if not diff_output:
        raise RuntimeError(
            "scan_history: `git log -p --all` returned empty/None output -- "
            "refusing to report a silent-clean history scan. This usually means the "
            "git subprocess failed (non-utf8 decode, git error, or empty repo). "
            "A security scanner that no-ops on empty output is worse than one that "
            "errors -- fix the underlying git/decode failure, don't suppress this."
        )
    current_file = "<unknown>"
    current_commit = "<unknown>"
    for raw_line in diff_output.splitlines():
        if raw_line.startswith("commit "):
            current_commit = raw_line.split()[1][:12]
        elif raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            line = raw_line[1:]
            if _is_allowlisted(line):
                continue
            for pattern, label, severity in SECRET_PATTERNS:
                if severity == "LOW":
                    continue
                m = pattern.search(line)
                if m:
                    matched = m.group(1) if m.groups() else m.group(0)
                    findings.append(Finding(
                        category="HISTORY",
                        severity=severity,
                        path=f"{current_file} (commit {current_commit})",
                        line=None,
                        label=f"[HISTORY] {label}",
                        snippet=_redact(line.strip()[:120], matched),
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


def report_text(
    findings: list[Finding], file_count: int, elapsed: float,
    scanned_label: str = "tracked files",
) -> int:
    """Print human-readable report. Returns exit code (0=GREEN, 1=RED)."""
    now_et = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _safe_print("=" * WIDTH)
    _safe_print(f"GITHUB SECRETS & PRIVACY AUDIT -- {now_et}")
    _safe_print("Repo: https://github.com/Swjsh/42  (PUBLIC)")
    _safe_print("=" * WIDTH)
    _safe_print(f"\n[SCAN] {file_count} {scanned_label} in {elapsed:.1f}s\n")

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
    parser.add_argument("--staged", action="store_true",
                        help=(
                            "Fast pre-commit mode: scan only the STAGED content of "
                            "`git diff --cached --name-only --diff-filter=ACM` files "
                            "(via `git show :path`) for secret patterns. Ignores "
                            "--history, gitignore checks, and blocked-file-type checks -- "
                            "those are full-tree concerns, not a per-commit gate's job."
                        ))
    args = parser.parse_args()

    import time
    t0 = time.monotonic()

    if args.staged:
        try:
            staged_files = _git_staged_files()
            findings = scan_staged(staged_files)
        except Exception as exc:
            print(f"ERROR: staged scan failed: {exc}", file=sys.stderr)
            return 2
        elapsed = time.monotonic() - t0
        if args.json:
            return report_json_output(findings, len(staged_files), elapsed)
        return report_text(findings, len(staged_files), elapsed, scanned_label="staged files")

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
        try:
            findings.extend(scan_history())
        except Exception as exc:
            print(f"ERROR: history scan failed: {exc}", file=sys.stderr)
            return 2

    elapsed = time.monotonic() - t0

    if args.json:
        return report_json_output(findings, len(files), elapsed)
    return report_text(findings, len(files), elapsed)


if __name__ == "__main__":
    sys.exit(main())
