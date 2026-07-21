"""Guard: setup/scripts/dojo/sim_executor.py + scorecard.py -- HARD FENCE, no broker.

DOJO-ARCHITECTURE-DECISION.md's sim_executor.py contract: "HARD FENCE: never import any
alpaca/broker module; a test asserts this." This is that test, scoped specifically to the
two modules this build produced (sim_executor.py, scorecard.py) -- complements (does not
duplicate) test_dojo_fence.py's package-wide `dojo.session` import-graph + git-operation
checks.

Two independent detectors, mirroring test_dojo_fence.py's own method (a broken detector
must not be able to silently pass either check):

  1. STATIC -- AST-scan each module's source for any `import`/`from ... import` whose
     dotted module name contains alpaca/broker/place_order.
  2. RUNTIME -- import both modules in a CLEAN subprocess interpreter and dump every
     sys.modules key that looks alpaca/broker-shaped afterward. Must be empty.

Both are RED-proofed: a companion test proves each detector actually fires on a synthetic
violation.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_no_broker.py -v
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
DOJO_DIR = ROOT / "setup" / "scripts" / "dojo"
SCRIPTS_DIR = ROOT / "setup" / "scripts"

TARGET_MODULES = ("sim_executor.py", "scorecard.py")
BROKER_TOKEN_RE = re.compile(r"alpaca|broker|place_order|place_option_order", re.IGNORECASE)


# =====================================================================================
# 1. STATIC -- AST scan of import statements
# =====================================================================================
def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_sim_executor_and_scorecard_import_no_broker_module_statically():
    violations: dict[str, set[str]] = {}
    for fname in TARGET_MODULES:
        f = DOJO_DIR / fname
        assert f.exists(), f"test target missing: {f}"
        hits = {n for n in _imported_module_names(f) if BROKER_TOKEN_RE.search(n)}
        if hits:
            violations[fname] = hits
    assert not violations, f"dojo module(s) statically import broker/alpaca module(s): {violations}"


def test_static_broker_detector_would_catch_a_real_violation(tmp_path):
    """RED-proof: a synthetic file with a realistic broker import must be flagged, so the
    check above isn't vacuously green from a detector that never fires."""
    bad = tmp_path / "bad_sim_executor.py"
    bad.write_text(
        "from __future__ import annotations\n"
        "import alpaca.trading.client\n"
        "from setup.scripts import fast_path_executor as broker_gateway\n",
        encoding="utf-8",
    )
    hits = {n for n in _imported_module_names(bad) if BROKER_TOKEN_RE.search(n)}
    assert hits, "static detector failed to flag a synthetic alpaca/broker import"

    clean = tmp_path / "clean_module.py"
    clean.write_text(
        "from __future__ import annotations\nimport json\nimport pandas as pd\n",
        encoding="utf-8",
    )
    assert not {n for n in _imported_module_names(clean) if BROKER_TOKEN_RE.search(n)}, (
        "static detector false-positived on clean stdlib/pandas imports"
    )


# =====================================================================================
# 2. RUNTIME -- clean-interpreter import + sys.modules scan
# =====================================================================================
def test_importing_sim_executor_and_scorecard_pulls_in_no_broker_modules():
    """Spawn a CLEAN interpreter (so unrelated pytest-collected modules already sitting in
    sys.modules from other test files can't produce a false pass/fail either way), import
    both modules exactly as session.py's cmd_directive/cmd_step/cmd_close do (bare names,
    dojo dir on sys.path), and dump every sys.modules key that looks alpaca/broker-shaped."""
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(DOJO_DIR)!r})\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import sim_executor\n"
        "import scorecard\n"
        "hits = sorted(m for m in sys.modules "
        "if 'alpaca' in m.lower() or 'broker' in m.lower())\n"
        "print(json.dumps(hits))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(ROOT), timeout=90,
    )
    assert out.returncode == 0, (
        f"import sim_executor/scorecard failed in a clean interpreter (stderr):\n{out.stderr}"
    )
    stdout_lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    assert stdout_lines, f"no output from the subprocess probe; stderr:\n{out.stderr}"
    hits = json.loads(stdout_lines[-1])
    assert hits == [], (
        f"importing sim_executor/scorecard pulled in broker/alpaca-looking module(s): {hits} "
        "-- the dojo package must NEVER import a broker path (sim-only fence)."
    )


def test_runtime_broker_module_detector_would_catch_a_real_violation():
    """RED-proof for the runtime check: prove the substring test actually flags realistic
    broker module names and does NOT false-positive on legitimate dojo/backtest names."""
    would_be_flagged = [
        "alpaca_mcp_server", "alpaca.trading.client", "mcp__alpaca__place_option_order",
        "broker_client", "setup.scripts.fast_path_executor.broker_gateway",
    ]
    for name in would_be_flagged:
        assert BROKER_TOKEN_RE.search(name), f"detector regex fails to flag {name!r}"
    for name in ["sim_executor", "scorecard", "dojo.sim_executor",
                 "backtest.lib.exit_manager_walk", "fleet_executor", "strategies",
                 "strike_selection"]:
        assert not BROKER_TOKEN_RE.search(name), f"detector regex false-positives on {name!r}"
