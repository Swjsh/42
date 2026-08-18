"""Guards for the 2026-08-18 'monitor that could never go green' scars.

THREE independent defects, all in the weekly MCP audit path, all live:

1. `mcp_audit_direct.py` and `mcp_audit.py` compared the broker's live `account_number`
   for EQUALITY against the string literals "PA3DHPT7KIQE" / "PA33W2KUAT40". Neither was
   ever a real account number -- a documentation transcription error copied into code --
   so the equality could never be satisfied. The audit returned RED on every run
   regardless of real health, and `mcp_audit_direct.py` fires a Discord alert + a
   STATUS.md write on RED, manufacturing a recurring "engine red" ping with no fault
   behind it. Proven fired: automation/state/mcp-weekly-audit-log.jsonl:21 (2026-08-17).

2. `mcp_audit_direct.check_tv()`'s success branch read
       return True, "CDP ok" if <cond> else False, "no Browser"
   which Python parses as a THREE-tuple, so the two-value unpack at the call site raised
   ValueError and killed the process. It crashed on every run where CDP was reachable and
   only "worked" when TradingView was down. Combined with (1), GREEN was unreachable under
   any condition.

3. `context_audit.py`'s CLAUDE.md integrity invariant asserted those same two phantom
   literals were PRESENT in the soul file -- so once CLAUDE.md was corrected to the true
   account numbers, the integrity check began false-failing the correct file.

A monitor that cannot go green trains the operator to ignore the channel, which is worse
than having no monitor. These tests pin that the expected values come from the fleet
registry (the same source the executors read) and that the tuple contract holds.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "automation" / "state" / "fleet" / "accounts.json"
PHANTOMS = ("PA3DHPT7KIQE", "PA33W2KUAT40")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _registry_core() -> tuple[str | None, str | None]:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {}
    for arm in reg.get("arms", []):
        aid = arm.get("id") or arm.get("arm_id")
        acct = arm.get("account_number")
        if aid and isinstance(acct, str):
            by_id.setdefault(str(aid), acct)
    return by_id.get("safe-2"), by_id.get("bold-2")


@pytest.mark.parametrize("rel", [
    "setup/scripts/mcp_audit.py",
    "setup/scripts/mcp_audit_direct.py",
    "setup/scripts/context_audit.py",
])
def test_no_phantom_account_literal_survives(rel: str) -> None:
    """The phantom strings may appear ONLY inside an explanatory scar comment, never as a
    value that gets compared or asserted."""
    src = (REPO / rel).read_text(encoding="utf-8")
    for line_no, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if not any(p in line for p in PHANTOMS):
            continue
        is_comment = stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'")
        assert is_comment or '"""' in src[:src.index(line)][-2000:], (
            f"{rel}:{line_no} uses a phantom account number in live code: {stripped[:90]!r}"
        )


def test_direct_audit_expected_accounts_match_registry() -> None:
    mod = _load("mcp_audit_direct_g", "setup/scripts/mcp_audit_direct.py")
    assert mod.expected_accounts() == _registry_core()


def test_plain_audit_expected_accounts_match_registry() -> None:
    mod = _load("mcp_audit_g", "setup/scripts/mcp_audit.py")
    assert mod.expected_accounts() == _registry_core()


def test_expected_accounts_are_real_and_not_phantom() -> None:
    safe, bold = _registry_core()
    assert safe and bold, "registry has no safe-2/bold-2 account_number"
    assert safe not in PHANTOMS and bold not in PHANTOMS
    assert safe.startswith("PA") and bold.startswith("PA"), "core arms must be PAPER accounts"


def test_check_tv_always_returns_exactly_two_values() -> None:
    """THE TUPLE SCAR. Both branches must unpack into (ok, note)."""
    mod = _load("mcp_audit_direct_tv", "setup/scripts/mcp_audit_direct.py")
    got = mod.check_tv()          # real call; CDP may be up or down, both are valid
    assert isinstance(got, tuple) and len(got) == 2, f"check_tv returned {len(got)}-tuple: {got!r}"
    ok, note = got                # must not raise
    assert isinstance(ok, bool) and isinstance(note, str)


def test_every_check_tv_return_is_a_two_tuple_by_AST() -> None:
    """Pin the SHAPE, not just today's runtime result -- the precedence trap only manifests
    on the reachable-CDP branch, so one passing live call does not prove the other branch.

    Uses AST, not text matching: this module's own scar docstring quotes the buggy line
    verbatim as documentation, and a grep-based check false-positives on its own note.
    """
    import ast
    tree = ast.parse((REPO / "setup/scripts/mcp_audit_direct.py").read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "check_tv"), None)
    assert fn is not None, "check_tv not found"
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
    assert returns, "check_tv has no return statements"
    for r in returns:
        assert isinstance(r.value, ast.Tuple), (
            f"check_tv line {r.lineno}: return is not a tuple ({type(r.value).__name__})"
        )
        assert len(r.value.elts) == 2, (
            f"check_tv line {r.lineno}: returns a {len(r.value.elts)}-tuple, must be exactly 2. "
            "An unparenthesised `x if c else y` inside a tuple silently widens it -- the 2026-08-18 scar."
        )

def test_context_audit_account_invariant_follows_the_registry() -> None:
    ca = _load("context_audit_g", "setup/scripts/context_audit.py")
    safe, bold = _registry_core()
    assert ca._core_accounts_documented(f"...{safe}... ...{bold}...", REPO) is True
    assert ca._core_accounts_documented("no accounts here", REPO) is False
    # The phantom literals must NOT satisfy it any more.
    assert ca._core_accounts_documented(f"{PHANTOMS[0]} {PHANTOMS[1]}", REPO) is False


def test_context_audit_invariant_fails_open_on_missing_registry(tmp_path: Path) -> None:
    """An integrity check must not red the soul file because an unrelated state file is gone."""
    ca = _load("context_audit_g2", "setup/scripts/context_audit.py")
    assert ca._core_accounts_documented("anything", tmp_path) is True


def test_live_claude_md_satisfies_the_account_invariant() -> None:
    ca = _load("context_audit_g3", "setup/scripts/context_audit.py")
    txt = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert ca._core_accounts_documented(txt, REPO) is True, (
        "CLAUDE.md does not name the registry's current core account numbers"
    )
