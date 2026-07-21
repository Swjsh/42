"""Guard: THE DOJO's hard fence -- setup/scripts/dojo/ package.

Three invariants, all load-bearing per DOJO-ARCHITECTURE-DECISION.md /
DOJO-REPLAY-TRAINING-SPEC.md (2026-07-20 J directive, "the dojo NEVER touches live state or
places broker orders"):

  1. Importing dojo.session pulls in ZERO alpaca/broker/place-order modules.
  2. session._assert_under_dojo -- the write-path fence -- rejects any path outside
     automation/state/dojo/ and accepts any path inside it.
  3. No dojo/*.py file performs a git operation (the 2026-07-20 STATE-FILE-REVERSION scar:
     a prior incident where a git operation inside a state-writing module reverted live
     state out from under the running system).

Every check that scans/detects is itself RED-proofed: a companion test proves the
detector actually fires on a synthetic violation, so a broken detector can't silently pass.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_fence.py -v
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
DOJO_DIR = ROOT / "setup" / "scripts" / "dojo"
SCRIPTS_DIR = ROOT / "setup" / "scripts"

BROKER_TOKEN_RE = re.compile(r"alpaca|broker|place_order|place_option_order", re.IGNORECASE)


# =====================================================================================
# 1. Importing dojo.session pulls in no broker/alpaca module
# =====================================================================================

def test_importing_session_pulls_in_no_broker_modules():
    """Spawn a CLEAN interpreter (so unrelated pytest-collected modules already sitting in
    sys.modules can't produce a false pass/fail either way), import dojo.session exactly as
    the runbook's CLI entry point does, and dump every sys.modules key that looks
    alpaca/broker-shaped. Must be empty."""
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import dojo.session\n"
        "hits = sorted(m for m in sys.modules "
        "if 'alpaca' in m.lower() or 'broker' in m.lower())\n"
        "print(json.dumps(hits))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    assert out.returncode == 0, (
        f"import dojo.session failed in a clean interpreter (stderr):\n{out.stderr}"
    )
    stdout_lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    assert stdout_lines, f"no output from the subprocess probe; stderr:\n{out.stderr}"
    hits = json.loads(stdout_lines[-1])
    assert hits == [], (
        f"importing dojo.session pulled in broker/alpaca-looking module(s): {hits} "
        "-- the dojo package must NEVER import a broker path (sim-only fence)."
    )


def test_broker_module_detector_would_catch_a_real_violation():
    """RED-proof for the check above: prove the substring test actually flags realistic
    broker module names, so the previous test isn't vacuously green because the detector
    itself is broken."""
    would_be_flagged = [
        "alpaca_mcp_server",
        "alpaca.trading.client",
        "mcp__alpaca__place_option_order",
        "broker_client",
        "setup.scripts.fast_path_executor.broker_gateway",
    ]
    for name in would_be_flagged:
        assert BROKER_TOKEN_RE.search(name), (
            f"detector regex fails to flag {name!r} -- the live check would miss a real "
            "broker-module regression"
        )
    # And a sanity negative: real dojo-ish names must NOT false-positive.
    for name in ["dojo.session", "dojo.clock", "backtest.lib.exit_manager_walk"]:
        assert not BROKER_TOKEN_RE.search(name), (
            f"detector regex false-positives on {name!r} -- would make the real check "
            "fail even with a clean import graph"
        )


# =====================================================================================
# 2. session._assert_under_dojo write-path fence
# =====================================================================================

def _import_dojo_session():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if "dojo.session" in sys.modules:
        return sys.modules["dojo.session"]
    import dojo.session as s  # noqa: PLC0415 -- intentional lazy import, mirrors the CLI
    return s


@pytest.fixture(scope="module")
def dojo_session_module():
    return _import_dojo_session()


def test_assert_under_dojo_rejects_path_outside_dojo_dir(dojo_session_module):
    s = dojo_session_module
    outside = ROOT / "automation" / "state" / "fleet" / "accounts.json"
    with pytest.raises(PermissionError):
        s._assert_under_dojo(outside)


def test_assert_under_dojo_rejects_sibling_prefix_lookalike(dojo_session_module):
    """The classic string-prefix bug: 'automation/state/dojo-evil/' starts with the same
    characters as the real dojo dir but is NOT a child of it. A naive str.startswith()
    fence would wrongly allow this; the real implementation must use Path.parents, which
    correctly rejects it."""
    s = dojo_session_module
    lookalike = ROOT / "automation" / "state" / "dojo-evil" / "file.json"
    with pytest.raises(PermissionError):
        s._assert_under_dojo(lookalike)


def test_assert_under_dojo_rejects_repo_root(dojo_session_module):
    s = dojo_session_module
    with pytest.raises(PermissionError):
        s._assert_under_dojo(ROOT / "CLAUDE.md")


def test_assert_under_dojo_rejects_relative_traversal_outside(dojo_session_module):
    """A relative path that resolves outside DOJO_DIR via '..' must also be rejected --
    _assert_under_dojo resolves before checking, so this can't be used to escape."""
    s = dojo_session_module
    escaping = s.DOJO_DIR / ".." / ".." / "params.json"
    with pytest.raises(PermissionError):
        s._assert_under_dojo(escaping)


def test_assert_under_dojo_accepts_path_inside_sessions_dir(dojo_session_module):
    s = dojo_session_module
    inside = s.SESSIONS_DIR / "2099-01-01-000000.jsonl"
    result = s._assert_under_dojo(inside)
    assert result == inside


def test_assert_under_dojo_accepts_dojo_dir_itself(dojo_session_module):
    """The dojo state dir root is accepted (the rp == DOJO_DIR.resolve() branch), not just
    strict descendants."""
    s = dojo_session_module
    result = s._assert_under_dojo(s.DOJO_DIR)
    assert result == s.DOJO_DIR


def test_assert_under_dojo_accepts_nested_path_inside(dojo_session_module):
    s = dojo_session_module
    nested = s.DOJO_DIR / "sessions" / "sub" / "deep.json"
    result = s._assert_under_dojo(nested)
    assert result == nested


# =====================================================================================
# 3. No git operations anywhere in dojo/*.py
# =====================================================================================

_GIT_SUBPROCESS_FNS = {"run", "call", "Popen", "check_call", "check_output", "system", "popen"}


def _git_operations_in_source(path: Path) -> list[str]:
    """AST-scan one .py file for (a) `import git` / `from git import ...`, or (b) a
    subprocess-family call whose first argument literally contains the token 'git'.
    Returns a list of human-readable violation strings (empty if clean)."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [f"{path.name}: unparsable ({e})"]

    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "git" or alias.name.startswith("git."):
                    hits.append(f"{path.name}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "git" or node.module.startswith("git.")):
                hits.append(f"{path.name}:{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Call):
            fname = None
            func = node.func
            if isinstance(func, ast.Attribute):
                fname = func.attr
            elif isinstance(func, ast.Name):
                fname = func.id
            if fname not in _GIT_SUBPROCESS_FNS:
                continue
            for arg in node.args:
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and re.search(r"(?<![\w-])git(?![\w-])", arg.value)):
                    hits.append(f"{path.name}:{node.lineno}: {fname}(...) string arg contains 'git'")
                elif isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
                    first = arg.elts[0]
                    if (isinstance(first, ast.Constant) and isinstance(first.value, str)
                            and first.value == "git"):
                        hits.append(f"{path.name}:{node.lineno}: {fname}([\"git\", ...])")
    return hits


def test_dojo_source_files_perform_no_git_operations():
    py_files = sorted(DOJO_DIR.glob("*.py"))
    assert py_files, f"no .py files found under {DOJO_DIR} -- test target is missing"
    violations: dict[str, list[str]] = {}
    for f in py_files:
        hits = _git_operations_in_source(f)
        if hits:
            violations[f.name] = hits
    assert not violations, (
        "dojo source file(s) perform a git operation -- this is the exact 2026-07-20 "
        f"STATE-FILE-REVERSION scar shape:\n{violations}"
    )


def test_git_operation_detector_would_catch_a_real_violation(tmp_path):
    """RED-proof for the check above: run the SAME AST scanner against synthetic files that
    each contain one of the violation shapes it claims to catch. Every one must be flagged,
    proving the previous test isn't vacuously green from a broken/no-op detector."""
    cases = {
        "bad_import_git.py": "import git\n",
        "bad_from_git.py": "from git import Repo\n",
        "bad_subprocess_list.py": "import subprocess\nsubprocess.run(['git', 'checkout', '.'])\n",
        "bad_subprocess_string.py": (
            "import subprocess\nsubprocess.run('git push origin main', shell=True)\n"
        ),
        "bad_check_output.py": "import subprocess\nsubprocess.check_output(['git', 'revert', 'HEAD'])\n",
        "bad_os_system.py": "import os\nos.system('git reset --hard')\n",
    }
    for fname, src in cases.items():
        f = tmp_path / fname
        f.write_text(src, encoding="utf-8")
        hits = _git_operations_in_source(f)
        assert hits, f"detector failed to flag a real git-operation violation in {fname}: {src!r}"

    # Sanity negative: legitimate, non-git code must NOT be flagged.
    clean = tmp_path / "clean.py"
    clean.write_text(
        "import subprocess\n"
        "subprocess.run(['python', '-m', 'pytest'])\n"
        "x = 'a legitimate string mentioning gitignore-adjacent config, not a command'\n",
        encoding="utf-8",
    )
    hits = _git_operations_in_source(clean)
    assert not hits, f"detector false-positived on clean code: {hits}"


def test_dojo_source_files_import_no_alpaca_or_broker_module():
    """Static companion to the runtime import-graph check (#1): AST-scan every dojo/*.py
    for a direct `import`/`from ... import` of anything alpaca/broker-shaped, independent
    of whether that module happens to be installed/importable in this environment."""
    py_files = sorted(DOJO_DIR.glob("*.py"))
    assert py_files, f"no .py files found under {DOJO_DIR} -- test target is missing"
    violations: dict[str, set[str]] = {}
    for f in py_files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        hits = {n for n in names if BROKER_TOKEN_RE.search(n)}
        if hits:
            violations[f.name] = hits
    assert not violations, f"dojo source statically imports broker/alpaca module(s): {violations}"
