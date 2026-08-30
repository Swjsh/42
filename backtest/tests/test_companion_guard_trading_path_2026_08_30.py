"""The companion's denylist must actually cover the config-freeze trading path.

FOUND BY AN ADVERSARIAL REVIEW PASS, 2026-08-30, and confirmed by running the real
regexes against real repo paths before fixing anything.

`gamma-companion/lib/guard.js` DENY_WRITE is the ONLY hard technical enforcement of the
project's config freeze. It was missing three of the five files that freeze names:

  * setup/scripts/heartbeat_core.py -- the live deterministic engine. It is a .py file
    OUTSIDE automation/prompts/, so the `automation/prompts/.*heartbeat.*\\.md` pattern
    never reached it.
  * backtest/lib/risk_gate.py -- only its neighbour filters.py was denied.
  * automation/state/fleet/** -- the params pattern is anchored to
    automation/state/params*.json, one directory above the fleet tree.

That mattered because /api/orchestrator-chat runs a REAL Claude Code session on the raw
typed message, with full Write/Edit/Bash and no confirmation step. An ordinary sentence
like "fix the sizing bug in the fleet executor" could have edited the live reward
function during a freeze, and silently: only the already-listed paths produce a visible
"Blocked" refusal, so nothing would have told the operator a frozen file had changed.

These tests parse the two arrays out of guard.js and evaluate them as real regexes, so
they fail if a future edit narrows the list again -- including on Windows-style
backslash paths, which is how they actually arrive from the SDK on this box.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "gamma-companion" / "lib" / "guard.js"


def _js_array(src: str, name: str):
    """Pull one regex array out of guard.js and translate it to Python regexes."""
    m = re.search(r"const " + name + r" = \[(.*?)\n\];", src, re.S)
    assert m, "{} not found in guard.js".format(name)
    out = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("/") or "/i," not in line:
            continue
        body = line[1:line.rindex("/i,")]
        # NO translation. guard.js writes its separators as the character class
        # [\\/] (backslash OR slash), which means the same thing in Python. An
        # earlier version of this helper "helpfully" rewrote \/ to / and thereby
        # collapsed that class to slash-only -- which made all seven Windows-path
        # cases fail and briefly looked like a guard defect rather than a test bug.
        out.append(re.compile(body, re.I))
    return out


@pytest.fixture(scope="module")
def src() -> str:
    return GUARD.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def deny_write(src):
    pats = _js_array(src, "DENY_WRITE")
    assert pats, "DENY_WRITE parsed empty -- the guard would allow everything"
    return pats


@pytest.fixture(scope="module")
def bash_protected(src):
    pats = _js_array(src, "BASH_PROTECTED")
    assert pats, "BASH_PROTECTED parsed empty"
    return pats


def _denied(pats, path: str) -> bool:
    return any(p.search(path) for p in pats)


# Every one of these EXISTS on disk and is named by the config freeze.
FROZEN = [
    "setup/scripts/heartbeat_core.py",
    "backtest/lib/risk_gate.py",
    "backtest/lib/filters.py",
    "automation/state/fleet/fleet_executor.py",
    "automation/state/fleet/accounts.json",
    "automation/state/fleet/exit_manager.py",
    "automation/state/params.json",
    "CLAUDE.md",
]


class TestTheFrozenPathIsDenied:
    @pytest.mark.parametrize("path", FROZEN)
    def test_forward_slash(self, deny_write, path):
        assert _denied(deny_write, path), "{} is WRITABLE by the companion".format(path)

    @pytest.mark.parametrize("path", FROZEN)
    def test_windows_backslash(self, deny_write, path):
        """Paths arrive from the SDK backslashed on this box -- a guard that only
        matches forward slashes is a guard that does not run here."""
        win = path.replace("/", "\\")
        assert _denied(deny_write, win), "{} is WRITABLE by the companion".format(win)

    @pytest.mark.parametrize("path", FROZEN)
    def test_the_file_actually_exists(self, path):
        """A denylist entry for a path that does not exist protects nothing, and a
        frozen file that has moved needs the guard moved with it."""
        assert (ROOT / path).exists(), "{} is not on disk -- guard entry is stale".format(path)


class TestOrdinaryWorkIsStillAllowed:
    """A denylist that blocks the app itself makes the console useless, and a useless
    guard gets switched off."""

    @pytest.mark.parametrize("path", [
        "gamma-companion/public/app/js/glass.js",
        "gamma-companion/public/app/css/app.css",
        "setup/scripts/gamma_glass.py",
        "setup/scripts/gamma_lanes.py",
        "markdown/infra/COCKPIT-DESIGN-SPEC.md",
    ])
    def test_app_surface_is_writable(self, deny_write, path):
        assert not _denied(deny_write, path), "{} should not be frozen".format(path)


class TestBashCannotRouteAroundIt:
    """A denylist that blocks the Write tool but leaves `sed -i` open is not a denylist."""

    @pytest.mark.parametrize("cmd", [
        "sed -i s/x/y/ setup/scripts/heartbeat_core.py",
        "echo x > automation/state/fleet/accounts.json",
        "cp /tmp/f backtest/lib/risk_gate.py",
        "mv new.py automation/state/fleet/exit_manager.py",
    ])
    def test_write_ops_on_frozen_paths_are_matched(self, bash_protected, cmd):
        assert _denied(bash_protected, cmd), "bash could clobber a frozen file: " + cmd

    def test_write_op_and_path_are_BOTH_required(self, src):
        """Reading a frozen file is fine -- only writing is refused. Pinning this so a
        future 'tightening' does not block `cat risk_gate.py` and make the console
        unable to explain the engine it is watching."""
        assert "BASH_WRITE_OP.test(cmd) && BASH_PROTECTED.some" in src, (
            "the bash rule no longer requires a WRITE op alongside a protected path")


class TestOrderToolsStayDenied:
    def test_live_order_tools_are_denied(self, src):
        m = re.search(r"const DENY_TOOL = /(.*?)/i;", src)
        assert m, "DENY_TOOL is gone -- the companion could place live orders"
        pat = re.compile(m.group(1), re.I)
        for tool in ("mcp__alpaca__place_option_order",
                     "mcp__alpaca_aggressive__place_option_order",
                     "mcp__alpaca__cancel_all_orders",
                     "mcp__alpaca__close_position"):
            assert pat.match(tool), "{} is CALLABLE by the companion".format(tool)
