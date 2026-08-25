"""Guard: J's interactive surfaces (Desktop app + bare `claude` CLI) must NEVER depend
on the claude-code-router (CCR) gateway being alive.

WHY THIS EXISTS (2026-07-14, J's #1 directive that morning): a PC restart left CCR's
static fallback router (`~/.claude-code-router/config.json` `Router.default`) pointed
at local Ollama with ZERO Anthropic provider entry. `~/.claude/settings.json`'s global
`env`/`apiKeyHelper` keys (wired 2026-07-08 for "every claude fire") captured J's
Desktop app and bare terminal `claude` CLI, not just automation -- so when the cold
boot left CCR's port 3456 listening-but-degraded (satisfies a bare TCP probe) J's
interactive session was silently served Ollama instead of Claude for a full workday,
with no error. Fix: the global override is gone (Anthropic direct by default); CCR
stays available only for automation lanes that opt in per-fire in their own launch
chain (doctrine: markdown/planning/BRAIN-SOVEREIGNTY.md sec 4, pattern:
setup/launch_claude_local.ps1). This file guards BOTH halves:
  1. Unit-level RED-proof of the detector/fixer in ccr_keepalive.py against synthetic
     fixtures (deterministic, portable, always runs).
  2. A live acceptance check against THIS box's actual ~/.claude/settings.json (skips
     cleanly if absent -- e.g. fresh clone/CI) plus a repo-wide scan proving the CCR
     port string appears ONLY in allowlisted automation/narrative files, never in
     something that could re-capture the interactive path by accident.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "setup" / "scripts" / "ccr_keepalive.py"


# ══════════════════════════════════════════════════════════════════════════════════════
# 2026-08-25 REPAIR -- READ THIS BEFORE "FIXING" THE TESTS BELOW.
#
# On 2026-08-23 ccr_keepalive.py was deliberately RETIRED: a module-level
# `sys.exit(0)` tombstone was placed ABOVE all of its function definitions, so any
# importer now raises SystemExit at import time. This file used to import it via
# `_load()` to unit-test `_scan_settings_for_router_leak`, `_strip_router_leak`,
# `_check_and_fix_interactive_settings` and `main`. All 13 of those tests have been
# RED since that commit, and the FULL-SUITE RED entry logged on 2026-08-23 recorded
# them only as an anonymous batch of failures.
#
# The consequence nobody caught for two days: `test_real_claude_settings_json_has_no_
# router_leak` -- the ONLY automated check on J's actual ~/.claude/settings.json, the
# guard for the interactive-surface lockout scar that cost a full workday on
# 2026-07-14 -- also went down, because it too went through `_load()`. The scar guard
# was off while the tombstone looked like a tidy retirement.
#
# WHAT CHANGED HERE, AND WHY IT IS NOT "WEAKENING A TEST TO MAKE IT PASS":
#   KEPT   the detector (`_scan_settings_for_router_leak`) -- reimplemented locally,
#          because the module copy is now unreachable dead code beneath the tombstone.
#          This file is now the ONE implementation, so there is nothing to drift from.
#   KEPT   every detector unit test, including the RED-proof and the
#          not-overly-broad test, now run against the local implementation.
#   KEPT   the live acceptance check on ~/.claude/settings.json -- the whole point.
#   KEPT   the repo-wide allowlist scan below, untouched.
#   DROPPED the 7 tests of `_strip_router_leak` / `_check_and_fix_interactive_settings`
#          / `main`. Their SUBJECT was retired on purpose: nothing auto-repairs
#          settings.json any more, by design ("a dead port fails loudly and is fixed in
#          one click; a live port serving the wrong models fails silently"). Testing a
#          deleted auto-fixer is not coverage.
#   ADDED  `test_ccr_keepalive_stays_retired` so the retirement itself is now guarded.
# ══════════════════════════════════════════════════════════════════════════════════════

_CCR_PORT = "3456"


def _scan_settings_for_router_leak(data: dict) -> list[str]:
    """Return one violation string per key that would route an INTERACTIVE Claude
    surface through the CCR gateway. Only the literal CCR port counts -- a legitimate
    Tier-2 provider override (GLM, DeepSeek, a local no-think proxy) is not a leak.

    This is the detector that guards J's #1 scar (2026-07-14). It lives here rather
    than in ccr_keepalive.py because that module is retired; see the block above.
    """
    violations: list[str] = []

    helper = data.get("apiKeyHelper")
    if isinstance(helper, str) and "claude-code-router" in helper:
        violations.append(f"apiKeyHelper -> claude-code-router: {helper[:80]}")

    env = data.get("env")
    if isinstance(env, dict):
        for key, value in env.items():
            if not isinstance(value, str):
                continue
            # ":3456" rather than a bare "3456" -- a port suffix, so this fires on
            # 127.0.0.1, localhost, 0.0.0.0 or any other host spelling, while a stray
            # "3456" inside a token or path is not a false positive. Deliberately erring
            # BROAD: a false positive costs one look, a false negative cost J a workday.
            if ":" + _CCR_PORT in value:
                violations.append(f"env.{key} -> CCR gateway: {value}")
            elif key == "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY" and value not in ("", "0"):
                violations.append(f"env.{key} -> gateway model discovery enabled: {value}")

    return violations


_CLEAN_SETTINGS = {
    "includeCoAuthoredBy": False,
    "model": "opus[1m]",
    "hooks": {"PreToolUse": []},
    "theme": "dark",
}

_DIRTY_SETTINGS = {
    "apiKeyHelper": "\"C:\\\\Users\\\\jackw\\\\AppData\\\\Roaming\\\\claude-code-router\\\\bin\\\\ccr-claude-code-api-key-default-claude-code.cmd\"",
    "env": {
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:3456",
        "ANTHROPIC_API_BASE_URL": "http://127.0.0.1:3456",
        "CLAUDE_AGENT_API_BASE_URL": "http://127.0.0.1:3456",
    },
    "includeCoAuthoredBy": False,
    "model": "opus[1m]",
    "hooks": {"PreToolUse": []},
    "theme": "dark",
}


# ---- the retirement itself is now guarded ---------------------------------------------

def test_ccr_keepalive_stays_retired():
    """ccr_keepalive.py must remain an inert no-op. If someone un-tombstones it, the
    machine-wide gateway starts resurrecting itself every 10 minutes again -- that is
    scar #2 (2026-08-23), and it broke J's Desktop app across every restart."""
    assert _SCRIPT.exists(), f"ccr_keepalive.py vanished entirely: {_SCRIPT}"
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "TOMBSTONE 2026-08-23" in src, "the retirement notice was removed"

    tombstone_at = src.index("_tombstone_sys.exit(0)")
    for name in ("def _check_and_fix_interactive_settings", "def main"):
        idx = src.find(name)
        if idx != -1:
            assert idx > tombstone_at, (
                f"{name} is now reachable ABOVE the tombstone -- the keepalive has been "
                "partially resurrected")

    # And it must actually exit 0 rather than do work.
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True, text=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert proc.returncode == 0, f"retired keepalive exited {proc.returncode}"
    assert "RETIRED" in proc.stdout, f"unexpected keepalive output: {proc.stdout[:200]}"


# ---- _scan_settings_for_router_leak ----------------------------------------------------

def test_scan_detects_router_leak_env_vars():
    """RED-proof: plant the exact 2026-07-14 bad shape, confirm the detector fires."""
    violations = _scan_settings_for_router_leak(_DIRTY_SETTINGS)
    assert violations, "detector must flag the CCR-pointing env block"
    assert any("ANTHROPIC_BASE_URL" in v for v in violations)
    assert any("apiKeyHelper" in v for v in violations)


def test_scan_clean_settings_no_violations():
    assert _scan_settings_for_router_leak(_CLEAN_SETTINGS) == []


def test_scan_ignores_non_ccr_base_urls():
    """A legitimate Tier-2 provider override (BRAIN-SOVEREIGNTY.md sec 4/5 -- GLM,
    DeepSeek, or the local no-think proxy) must NOT be flagged. Only the literal CCR
    gateway port is the violation -- this proves the detector isn't overly broad."""
    data = {**_CLEAN_SETTINGS, "env": {"ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"}}
    assert _scan_settings_for_router_leak(data) == []
    data2 = {**_CLEAN_SETTINGS, "env": {"ANTHROPIC_BASE_URL": "http://localhost:11435"}}
    assert _scan_settings_for_router_leak(data2) == []


def test_scan_handles_missing_env_key():
    assert _scan_settings_for_router_leak({"model": "opus"}) == []


def test_scan_catches_every_host_spelling_of_the_gateway():
    """The 2026-07-14 leak was 127.0.0.1, but the gateway is equally reachable as
    localhost / 0.0.0.0 / a LAN IP. A detector that only knew one spelling would pass a
    machine that is still captured."""
    for host in ("127.0.0.1", "localhost", "0.0.0.0", "192.168.1.42"):
        data = {**_CLEAN_SETTINGS, "env": {"ANTHROPIC_BASE_URL": f"http://{host}:3456"}}
        assert _scan_settings_for_router_leak(data), f"missed gateway at {host}"


def test_scan_does_not_fire_on_a_stray_3456_substring():
    """Proves the detector is a port matcher, not a substring matcher."""
    data = {**_CLEAN_SETTINGS, "env": {"SOME_TOKEN": "abc3456def", "PATH_ISH": "C:/x/3456/y"}}
    assert _scan_settings_for_router_leak(data) == []


def test_scan_does_not_mutate_input():
    """Immutability (coding-style.md): scanning must never edit what it inspects."""
    import copy
    before = copy.deepcopy(_DIRTY_SETTINGS)
    _scan_settings_for_router_leak(_DIRTY_SETTINGS)
    assert _DIRTY_SETTINGS == before


# ---- Live acceptance check -- THIS box's actual settings.json ------------------------

def test_real_claude_settings_json_has_no_router_leak():
    """The actual file J's Desktop app + bare `claude` CLI read. Skips cleanly if absent
    (fresh clone / CI box) -- but on any machine where it exists, it must be clean.

    THIS IS THE ONE THAT MATTERS. It was silently down 2026-08-23 -> 2026-08-25."""
    real_path = Path.home() / ".claude" / "settings.json"
    if not real_path.exists():
        pytest.skip("no ~/.claude/settings.json on this machine")
    data = json.loads(real_path.read_text(encoding="utf-8"))
    violations = _scan_settings_for_router_leak(data)
    assert violations == [], f"live interactive settings leak CCR routing: {violations}"


# ---- Repo-wide scan -- the router port string may ONLY appear in allowlisted files ----

# Files that legitimately mention the CCR gateway port: the keepalive + its guards + its
# installer, the narrative doc trail of the 07-08/07-09/07-14 incidents, and the two
# audit/queue/status logs that recorded them. Nothing else in the repo may reference it --
# a new hit here means something is re-wiring a global (or otherwise unscoped) dependency
# on CCR, which is exactly the class of bug this whole file exists to prevent.
_ALLOWLIST = {
    "setup/scripts/ccr_keepalive.py",
    "setup/scripts/install-ccr-keepalive.ps1",
    "setup/launch_claude_local.ps1",
    "setup/scripts/daily_loss_guard.py",
    "setup/scripts/run-premarket.ps1",
    "setup/scripts/engine_health.py",
    "backtest/tests/test_ccr_keepalive.py",
    "backtest/tests/test_ccr_interactive_isolation.py",
    "backtest/tests/test_engine_health_breaker_rearm.py",
    "markdown/planning/BRAIN-SOVEREIGNTY.md",
    "markdown/audits/OPEN-READINESS-2026-07-10.md",
    "automation/overnight/queue.md",
    "automation/state/SCHEDULED-TASKS.md",
    "automation/overnight/STATUS.md",
    "strategy/candidates/_lesson-inbox/2026-07-14-ccr-boot-lockout.md",
    "markdown/doctrine/LESSONS-LEARNED.md",
    "CHANGELOG.md",
    # Added 2026-08-14. Both are pure NARRATIVE of the 2026-07-14 incident -- the category
    # this allowlist's own comment already sanctions -- and both post-date the list, so the
    # scan had been RED (and therefore dead) since they landed. Verified by reading: the
    # audit doc quotes the leaked settings line, and the memory mirror states the rule
    # ("nothing routes through port 3456"). Neither wires anything.
    "markdown/audits/OLLAMA-CCR-AUDIT-2026-07-14.md",
    "memory-mirror/feedback_interactive_surfaces_never_gatewayed_2026_07_14.md",
}

_SCAN_EXCLUDE_DIR_PARTS = {
    ".git", "node_modules", ".venv", "__pycache__", "worktrees",
    ".pytest_cache", "logs",
}
_SCAN_EXTENSIONS = {".ps1", ".py", ".md", ".json", ".txt"}


def _iter_repo_text_files():
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SCAN_EXTENSIONS:
            continue
        parts = set(path.relative_to(REPO).parts)
        if parts & _SCAN_EXCLUDE_DIR_PARTS:
            continue
        yield path


# ARCHIVES OF ALLOWLISTED NARRATIVE FILES ARE ALLOWLISTED TOO (added 2026-08-21).
#
# `automation/overnight/queue.md` and `STATUS.md` are both sanctioned narrative surfaces,
# and both are ROLLED OFF into dated archive siblings by retention
# (queue-archive-YYYY-MM-DD.md, STATUS-archive-YYYY-MM.md). So the ordinary act of
# archiving MOVES sanctioned text out of an allowlisted file and into an unlisted one,
# and the scan goes RED for a reason that is pure housekeeping -- exactly what happened
# with queue-archive-2026-08-19.md.
#
# Listing each archive by name would mean editing this test every time retention runs.
# The rule is derived instead: if <dir>/<stem>.md is allowlisted, its
# <dir>/<stem>-archive-*.md siblings inherit that sanction. Nothing else does -- an archive
# of a file that was never allowlisted still fails, and code files never match this.
_ARCHIVE_RE = re.compile(r"^(?P<base>.+?)-archive-[\d-]+\.md$")


def _is_allowlisted(rel: str) -> bool:
    if rel in _ALLOWLIST:
        return True
    m = _ARCHIVE_RE.match(rel)
    return bool(m) and f"{m.group('base')}.md" in _ALLOWLIST


def test_router_port_only_appears_in_allowlisted_repo_files():
    hits: dict[str, list[str]] = {}
    for path in _iter_repo_text_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "127.0.0.1:3456" in text or "localhost:3456" in text:
            rel = path.relative_to(REPO).as_posix()
            if not _is_allowlisted(rel):
                hits.setdefault(rel, []).append("router-port string found outside allowlist")

    assert not hits, (
        "found the CCR gateway port referenced outside the allowlisted automation/"
        f"narrative files -- audit these for a new unscoped dependency: {hits}"
    )
