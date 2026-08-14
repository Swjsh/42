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
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "setup" / "scripts" / "ccr_keepalive.py"


def _load():
    for p in (REPO / "setup" / "scripts",):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location("ccr_keepalive_iso", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["ccr_keepalive_iso"] = m
    spec.loader.exec_module(m)  # type: ignore
    return m


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


# ---- _scan_settings_for_router_leak -- RED-proof against synthetic fixtures ----------

def test_scan_detects_router_leak_env_vars():
    """RED-proof: plant the exact 2026-07-14 bad shape, confirm the detector fires."""
    m = _load()
    violations = m._scan_settings_for_router_leak(_DIRTY_SETTINGS)
    assert violations, "detector must flag the CCR-pointing env block"
    assert any("ANTHROPIC_BASE_URL" in v for v in violations)
    assert any("apiKeyHelper" in v for v in violations)


def test_scan_clean_settings_no_violations():
    m = _load()
    assert m._scan_settings_for_router_leak(_CLEAN_SETTINGS) == []


def test_scan_ignores_non_ccr_base_urls():
    """A legitimate Tier-2 provider override (BRAIN-SOVEREIGNTY.md sec 4/5 -- GLM,
    DeepSeek, or the local no-think proxy) must NOT be flagged. Only the literal CCR
    gateway port is the violation -- this proves the detector isn't overly broad."""
    m = _load()
    data = {
        **_CLEAN_SETTINGS,
        "env": {"ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"},
    }
    assert m._scan_settings_for_router_leak(data) == []
    data2 = {**_CLEAN_SETTINGS, "env": {"ANTHROPIC_BASE_URL": "http://localhost:11435"}}
    assert m._scan_settings_for_router_leak(data2) == []


def test_scan_handles_missing_env_key():
    m = _load()
    assert m._scan_settings_for_router_leak({"model": "opus"}) == []


# ---- _strip_router_leak -- immutable, surgical -----------------------------------------

def test_strip_router_leak_removes_only_router_keys():
    m = _load()
    cleaned = m._strip_router_leak(_DIRTY_SETTINGS)
    assert "apiKeyHelper" not in cleaned
    assert "env" not in cleaned
    # Every non-router key survives untouched.
    for key in ("includeCoAuthoredBy", "model", "hooks", "theme"):
        assert cleaned[key] == _DIRTY_SETTINGS[key]
    # Immutability: the input dict itself is untouched (coding-style.md).
    assert "apiKeyHelper" in _DIRTY_SETTINGS
    assert "env" in _DIRTY_SETTINGS


# ---- _check_and_fix_interactive_settings -- full integration, tmp-isolated -----------

def test_check_and_fix_cleans_dirty_file_and_backs_up_and_pings(tmp_path, monkeypatch):
    m = _load()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps(_DIRTY_SETTINGS, indent=2), encoding="utf-8")
    outbox = tmp_path / "discord-outbox.jsonl"
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text(json.dumps({"user_id": "1"}), encoding="utf-8")

    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", outbox)
    monkeypatch.setattr(m, "DISCORD_CFG", cfg)

    result = m._check_and_fix_interactive_settings()
    assert result["checked"] is True
    assert result["fixed"] is True
    assert result["violations"], "must report what it fixed"

    # The live file is now clean and still valid JSON with non-router keys intact.
    cleaned = json.loads(settings_file.read_text(encoding="utf-8"))
    assert m._scan_settings_for_router_leak(cleaned) == []
    assert cleaned["theme"] == "dark"
    assert cleaned["model"] == "opus[1m]"

    # A same-day backup captured the ORIGINAL dirty content.
    backups = list(tmp_path.glob("settings.json.router-leak-*.bak"))
    assert len(backups) == 1
    backed_up = json.loads(backups[0].read_text(encoding="utf-8"))
    assert backed_up == _DIRTY_SETTINGS

    # Exactly one Discord ping, mentioning the leak class.
    lines = outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "CCR LEAK" in row["content"]
    assert row["source"] == "ccr_keepalive"


def test_check_and_fix_noop_on_clean_file(tmp_path, monkeypatch):
    m = _load()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps(_CLEAN_SETTINGS, indent=2), encoding="utf-8")
    outbox = tmp_path / "discord-outbox.jsonl"

    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", outbox)

    result = m._check_and_fix_interactive_settings()
    assert result == {"checked": True, "violations": [], "fixed": False}
    assert not outbox.exists(), "a clean file must never trigger a ping"
    assert not list(tmp_path.glob("*.bak")), "a clean file must never trigger a backup"
    # File content byte-for-byte unchanged (no rewrite on the no-op path).
    assert json.loads(settings_file.read_text(encoding="utf-8")) == _CLEAN_SETTINGS


def test_check_and_fix_missing_file_is_silent_noop(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    result = m._check_and_fix_interactive_settings()
    assert result == {"checked": False, "violations": [], "fixed": False}


def test_check_and_fix_fails_open_on_corrupt_json(tmp_path, monkeypatch):
    """A hand-edited settings.json with a trailing comma or similar must never crash the
    keepalive (OP-33e) -- log and move on, exactly like the rest of this script."""
    m = _load()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{not valid json,,,", encoding="utf-8")
    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    result = m._check_and_fix_interactive_settings()
    assert result == {"checked": False, "violations": [], "fixed": False}


def test_check_and_fix_backs_up_only_once_per_day(tmp_path, monkeypatch):
    """Re-dirtying the file twice in one day must not clobber the first backup -- the
    first snapshot of the day is the one worth keeping for forensics."""
    m = _load()
    settings_file = tmp_path / "settings.json"
    outbox = tmp_path / "discord-outbox.jsonl"
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text(json.dumps({"user_id": "1"}), encoding="utf-8")
    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", outbox)
    monkeypatch.setattr(m, "DISCORD_CFG", cfg)

    dirty_v1 = {**_DIRTY_SETTINGS, "model": "v1-marker"}
    settings_file.write_text(json.dumps(dirty_v1), encoding="utf-8")
    m._check_and_fix_interactive_settings()

    dirty_v2 = {**_DIRTY_SETTINGS, "model": "v2-marker"}
    settings_file.write_text(json.dumps(dirty_v2), encoding="utf-8")
    m._check_and_fix_interactive_settings()

    backups = list(tmp_path.glob("settings.json.router-leak-*.bak"))
    assert len(backups) == 1, "one dated backup per day, not one per fire"
    assert json.loads(backups[0].read_text(encoding="utf-8"))["model"] == "v1-marker"


# ---- main() wiring -- interactive_settings_* lands in the state file -----------------

def test_main_records_interactive_clean_true_in_state(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "STATE_FILE", tmp_path / "ccr-keepalive.json")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(json.dumps(_CLEAN_SETTINGS), encoding="utf-8")
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: True)

    assert m.main() == 0
    state = json.loads((tmp_path / "ccr-keepalive.json").read_text(encoding="utf-8"))
    assert state["interactive_settings_clean"] is True
    assert state["interactive_settings_last_fixed_et"] is None


def test_main_records_interactive_fix_timestamp_in_state(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "STATE_FILE", tmp_path / "ccr-keepalive.json")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(m, "INTERACTIVE_SETTINGS_FILE", tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(json.dumps(_DIRTY_SETTINGS), encoding="utf-8")
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: True)

    assert m.main() == 0
    state = json.loads((tmp_path / "ccr-keepalive.json").read_text(encoding="utf-8"))
    assert state["interactive_settings_clean"] is False
    assert state["interactive_settings_last_fixed_et"], "must stamp when the auto-fix ran"
    # And the file it fixed is provably clean afterward.
    fixed = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert m._scan_settings_for_router_leak(fixed) == []


# ---- Live acceptance check -- THIS box's actual settings.json ------------------------

def test_real_claude_settings_json_has_no_router_leak():
    """The actual file J's Desktop app + bare `claude` CLI read. Skips cleanly if absent
    (fresh clone / CI box) -- but on any machine where it exists, it must be clean."""
    m = _load()
    real_path = Path.home() / ".claude" / "settings.json"
    if not real_path.exists():
        pytest.skip("no ~/.claude/settings.json on this machine")
    data = json.loads(real_path.read_text(encoding="utf-8"))
    violations = m._scan_settings_for_router_leak(data)
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


def test_router_port_only_appears_in_allowlisted_repo_files():
    hits: dict[str, list[str]] = {}
    for path in _iter_repo_text_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "127.0.0.1:3456" in text or "localhost:3456" in text:
            rel = path.relative_to(REPO).as_posix()
            if rel not in _ALLOWLIST:
                hits.setdefault(rel, []).append("router-port string found outside allowlist")

    assert not hits, (
        "found the CCR gateway port referenced outside the allowlisted automation/"
        f"narrative files -- audit these for a new unscoped dependency: {hits}"
    )
