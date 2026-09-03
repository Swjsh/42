"""Guard: STAGED-FILES secret scan (2026-09-03, closes the pre-commit gap).

CONTEXT: a pre-push audit (github_audit.py, run BY HAND) found two real paper API keys
hardcoded in an orphan script that had already passed the curated pre-commit gate
(setup/git-hooks/pre-commit -> run_safety_gate.py, 59 curated tests + commit_scope_gate)
earlier the same day. Nothing was pushed -- the file was deleted before it reached the
remote -- but the gate itself had NO secret scan, so a leak could sit in local history
unnoticed until someone ran the audit manually. That gap is what this file guards.

FIX: setup/scripts/github_audit.py gained a `--staged` mode that scans only the STAGED
content (`git show :path`) of `git diff --cached --name-only --diff-filter=ACM` files,
reusing the SAME SECRET_PATTERNS list + a new shared `scan_text(path, text)` function the
full-tree scan now also calls. setup/git-hooks/pre-commit runs it BEFORE the safety gate.
Both the staged mode AND the full-tree mode now REDACT any matched secret to its first 4
characters + '...' in all output (previously the full-tree mode printed the raw secret).

These tests exercise the CLI end-to-end (subprocess, checking the real exit code) against
a disposable git repo created fresh under the scratchpad dir for each test -- never the
main 42 checkout. `github_audit.py` resolves its own repo root via
`git rev-parse --show-toplevel` from the invoking cwd (see _detect_project_root), so
pointing `cwd=` at the scratch repo is sufficient to isolate it; nothing here touches the
real repo's git state.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "github_audit.py"
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import github_audit  # noqa: E402  (path-inserted import, matches repo test convention)

SCRATCHPAD = Path(
    r"C:\Users\jackw\AppData\Local\Temp\claude\C--Users-jackw-Desktop-42"
    r"\b6eea006-22c7-498b-a0c1-23c79c635f20\scratchpad"
)

# Fixture-only fake credential -- shaped like a real Alpaca paper/live key
# (\bPK[A-Z0-9]{24}\b) but never a real one. Never use a real key in a test, ever.
FAKE_ALPACA_KEY = "PK" + "A" * 24
assert len(FAKE_ALPACA_KEY) == 26

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        timeout=30, creationflags=_CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed in {repo}: {result.stdout}\n{result.stderr}"
    )
    return result


def _run_audit(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(repo), capture_output=True, text=True,
        timeout=30, creationflags=_CREATE_NO_WINDOW,
    )


@pytest.fixture
def scratch_repo():
    """A fresh, disposable git repo under the scratchpad dir with one seed commit."""
    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
    repo_dir = Path(tempfile.mkdtemp(prefix="ga_staged_test_", dir=str(SCRATCHPAD)))
    try:
        _run_git(repo_dir, "init", "-q")
        _run_git(repo_dir, "config", "user.email", "test@example.invalid")
        _run_git(repo_dir, "config", "user.name", "Test Runner")
        (repo_dir / ".gitkeep").write_text("", encoding="utf-8")
        _run_git(repo_dir, "add", ".gitkeep")
        _run_git(repo_dir, "commit", "-q", "-m", "seed")
        yield repo_dir
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


# ── 1. Staged file with a fake Alpaca-shaped key ──────────────────────────────

def test_staged_fake_alpaca_key_blocks_with_exit_1(scratch_repo):
    leak = scratch_repo / "leaky.py"
    leak.write_text(f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"\n', encoding="utf-8")
    _run_git(scratch_repo, "add", "leaky.py")

    result = _run_audit(scratch_repo, "--staged")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "RED" in result.stdout


def test_staged_fake_alpaca_key_output_is_redacted(scratch_repo):
    leak = scratch_repo / "leaky.py"
    leak.write_text(f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"\n', encoding="utf-8")
    _run_git(scratch_repo, "add", "leaky.py")

    result = _run_audit(scratch_repo, "--staged")

    assert FAKE_ALPACA_KEY not in result.stdout, "raw secret leaked into hook output"
    assert FAKE_ALPACA_KEY[:4] + "..." in result.stdout


# ── 2. Clean staged file passes ────────────────────────────────────────────────

def test_clean_staged_file_passes(scratch_repo):
    clean = scratch_repo / "clean.py"
    clean.write_text("print('hello world')\n", encoding="utf-8")
    _run_git(scratch_repo, "add", "clean.py")

    result = _run_audit(scratch_repo, "--staged")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "GREEN" in result.stdout


# ── 3. Unstaged secret in the working tree does not fail the staged scan ──────

def test_unstaged_secret_not_flagged(scratch_repo):
    (scratch_repo / "unstaged_leak.py").write_text(
        f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"\n', encoding="utf-8",
    )
    # deliberately never `git add`-ed

    result = _run_audit(scratch_repo, "--staged")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 staged files" in result.stdout


# ── 4. A deleted file is ignored (diff-filter=ACM excludes D) ─────────────────

def test_deleted_file_is_ignored(scratch_repo):
    tracked = scratch_repo / "tracked.py"
    tracked.write_text("print('ok')\n", encoding="utf-8")
    _run_git(scratch_repo, "add", "tracked.py")
    _run_git(scratch_repo, "commit", "-q", "-m", "add tracked")

    tracked.unlink()
    _run_git(scratch_repo, "add", "-A")  # stages the deletion

    result = _run_audit(scratch_repo, "--staged")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 staged files" in result.stdout


# ── 5. noqa allowlist still respected in staged mode ───────────────────────────

def test_noqa_allowlist_respected_in_staged_mode(scratch_repo):
    allowlisted = scratch_repo / "allowlisted.py"
    allowlisted.write_text(
        f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"  # noqa:secret-ok\n', encoding="utf-8",
    )
    _run_git(scratch_repo, "add", "allowlisted.py")

    result = _run_audit(scratch_repo, "--staged")

    assert result.returncode == 0, result.stdout + result.stderr


# ── 6. The full-scan CLI still works, and is now redacted too ─────────────────

def test_full_scan_still_works_and_is_redacted(scratch_repo):
    committed_leak = scratch_repo / "committed_leak.py"
    committed_leak.write_text(f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"\n', encoding="utf-8")
    _run_git(scratch_repo, "add", "committed_leak.py")
    _run_git(scratch_repo, "commit", "-q", "-m", "oops, a tracked secret")

    result = _run_audit(scratch_repo)  # no --staged = full tracked-file scan

    assert result.returncode == 1, result.stdout + result.stderr
    assert "RED" in result.stdout
    assert FAKE_ALPACA_KEY not in result.stdout, "raw secret leaked into full-scan output"
    assert FAKE_ALPACA_KEY[:4] + "..." in result.stdout


# ── 7. --staged --json is redacted and machine-readable ───────────────────────

def test_staged_json_output_is_redacted_and_valid(scratch_repo):
    leak = scratch_repo / "leaky.js"
    leak.write_text(f'const key = "{FAKE_ALPACA_KEY}";\n', encoding="utf-8")
    _run_git(scratch_repo, "add", "leaky.js")

    result = _run_audit(scratch_repo, "--staged", "--json")

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "RED"
    assert any(f["path"] == "leaky.js" for f in payload["findings"])
    raw = json.dumps(payload)
    assert FAKE_ALPACA_KEY not in raw, "raw secret leaked into --json output"


# ── 8. scan_text() is importable and usable without the full tracked-file scan ─

def test_scan_text_importable_and_finds_pattern_directly():
    findings = github_audit.scan_text(
        "inline.py", f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"\n', is_code=True,
    )

    assert len(findings) == 1
    assert findings[0].severity == "HIGH"
    assert findings[0].path == "inline.py"
    assert FAKE_ALPACA_KEY not in findings[0].snippet
    assert FAKE_ALPACA_KEY[:4] + "..." in findings[0].snippet


def test_scan_text_clean_line_finds_nothing():
    findings = github_audit.scan_text("inline.py", "print('hello')\n", is_code=True)
    assert findings == []


# ── 9. Performance budget: < 3s on a 50-file staged commit ────────────────────

def test_staged_scan_of_50_files_finishes_under_3s(scratch_repo):
    for i in range(49):
        (scratch_repo / f"file_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    (scratch_repo / "file_49_secret.py").write_text(
        f'ALPACA_KEY = "{FAKE_ALPACA_KEY}"\n', encoding="utf-8",
    )
    _run_git(scratch_repo, "add", "-A")

    t0 = time.monotonic()
    result = _run_audit(scratch_repo, "--staged")
    elapsed = time.monotonic() - t0

    assert result.returncode == 1, result.stdout + result.stderr
    assert elapsed < 3.0, f"staged scan of 50 files took {elapsed:.2f}s (budget: 3s)"


# ── 10. --history mode: cp1252-crash fix (2026-09-03) ──────────────────────────
#
# CONTEXT: `python setup/scripts/github_audit.py --history` crashed on this box
# BEFORE the fix in two ways: (a) UnicodeDecodeError -- the git subprocess in
# `_run()` / `_detect_project_root()` / `_git_show_staged()` decoded with the
# Windows cp1252 default instead of utf-8, and any non-cp1252 byte reachable in
# `git log -p --all` (e.g. binary-ish content in an old commit) blew up before
# scanning; (b) AttributeError: 'NoneType' object has no attribute 'splitlines'
# at the top of scan_history() -- a scanner that silently treats a failed git
# call as "no output, report clean" is worse than one that errors loudly.
# FIX: every subprocess.run() git call now passes encoding="utf-8",
# errors="replace" so a bad byte becomes U+FFFD instead of crashing, and
# scan_history() now raises RuntimeError if `git log -p` returns falsy output
# instead of proceeding to scan nothing.

# Built by concatenation (same trick as FAKE_ALPACA_KEY above) so this test file
# never itself carries a key-shaped literal -- the staged-secret hook we ship in
# this very file would otherwise block every commit that touches it. Proven: the
# hook flagged this line on 2026-09-03 before it was split.
FAKE_ALPACA_KEY_2 = "PK" + "ABCDEFGHIJKLMNOPQRSTUVWX"
assert len(FAKE_ALPACA_KEY_2) == 26


def test_history_scan_survives_non_cp1252_byte_and_finds_key(scratch_repo):
    """A commit whose diff contains a non-utf8 byte (0x9d, an orphan cp1252/latin1
    continuation byte that is NOT valid standalone utf-8) must not crash the
    --history scan, and the fake key committed alongside it must still be found
    and redacted in the output."""
    leaky = scratch_repo / "history_leak.py"
    # Byte 0x9d alone is invalid UTF-8 (a lone continuation byte with no lead byte).
    # Written as raw bytes so `git log -p` will emit it verbatim in the diff.
    content = (
        b"# marker byte follows: \x9d end-marker\n"
        + f'ALPACA_KEY = "{FAKE_ALPACA_KEY_2}"\n'.encode("utf-8")
    )
    leaky.write_bytes(content)
    _run_git(scratch_repo, "add", "history_leak.py")
    _run_git(scratch_repo, "commit", "-q", "-m", "oops, key + weird byte in history")

    result = _run_audit(scratch_repo, "--history")

    assert result.returncode == 1, (
        "history scan should not crash on a non-cp1252 byte -- "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "UnicodeDecodeError" not in result.stderr
    assert "AttributeError" not in result.stderr
    assert "RED" in result.stdout
    assert FAKE_ALPACA_KEY_2 not in result.stdout, "raw secret leaked into history output"
    assert FAKE_ALPACA_KEY_2[:4] + "..." in result.stdout


def test_history_scan_none_output_raises_instead_of_reporting_clean(monkeypatch):
    """scan_history() must fail loudly (raise), never silently report a clean
    scan, when the underlying `git log -p` output is None/empty -- e.g. because
    the git subprocess failed. A no-op secret scanner is a false GREEN."""
    monkeypatch.setattr(github_audit, "_run", lambda *a, **k: None)
    with pytest.raises(Exception):
        github_audit.scan_history()

    monkeypatch.setattr(github_audit, "_run", lambda *a, **k: "")
    with pytest.raises(Exception):
        github_audit.scan_history()
