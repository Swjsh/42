"""Guards for firm_brief's "Tomorrow's exits" section (2026-08-10).

The section is the standing answer to J's repeated "is the new stop logic actually live
for tomorrow?" -- it resolves each arm's exit shape through the PRODUCTION path
(fleet_executor._exit_shape_dict over the strategies registry) at render time, so it
cannot disagree with what tomorrow's entry will register.

What must never rot:
  1. Every active trading arm renders a line, and every line carries the ladder.
  2. A resolved shape MISSING the ladder renders the loud 🚨 line (not silence) --
     this is the exact regression the section exists to catch.
  3. The pending-fill guard presence check reads the REAL exit_actuator source.
  4. The section is fail-open: resolution blowing up renders one RED line, never raises.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import firm_brief as fb  # noqa: E402

ACCOUNTS_PATH = REPO / "automation" / "state" / "fleet" / "accounts.json"


def _live_active_spy_arms() -> tuple:
    """Derived from accounts.json, NEVER hardcoded (2026-08-28 fix -- the old hardcoded
    5-tuple silently included risky-3 after its SAME-DAY retirement, since this test's
    fixed list and firm_brief.py's old name-blocklist agreed with each other while both
    were equally stale). Mirrors firm_brief.render_tomorrow_exits_lines()'s own filter."""
    cfg = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    return tuple(
        str(a["id"]) for a in cfg.get("arms", [])
        if a.get("status") == "active" and a.get("instrument") == "SPY_0DTE_OPTION"
    )


ACTIVE_ARMS = _live_active_spy_arms()


def test_every_active_arm_renders_with_ladder():
    lines = fb.render_tomorrow_exits_lines()
    body = "\n".join(lines)
    for arm in ACTIVE_ARMS:
        assert f"- {arm}:" in body, f"{arm} missing from Tomorrow's exits"
    for line in lines:
        if any(line.startswith(f"- {a}:") for a in ACTIVE_ARMS):
            assert "ladder" in line and "🚨" not in line, line
    # today's live truth pinned: rungs +50->+30 and +75->+60, trail 20% arming at +75%
    assert "+50%->floor +30%" in body and "+75%->floor +60%" in body
    assert "arming @ +75%" in body
    # ASCII-only normal path: cp1252 console prints must never crash on this section
    # (the Invoke-PythonHidden UnicodeEncodeError class, 15c1de5e)
    for line in lines:
        if "🚨" not in line and "⚠" not in line:
            line.encode("cp1252")


def test_registration_guard_check_reads_real_source():
    lines = fb.render_tomorrow_exits_lines()
    body = "\n".join(lines)
    assert "pending-fill prune guard PRESENT" in body, (
        "the section must confirm the 2026-08-10 registration guard from the real source")


def test_missing_ladder_renders_loud_not_silent(monkeypatch):
    """Strip the ladder from the resolved shape -> the 🚨 line must appear per arm."""
    import fleet_executor as fx

    real = fx._exit_shape_dict

    def no_ladder(strategy, arm):
        sh = dict(real(strategy, arm))
        sh["pre_tp1_ladder"] = None
        return sh

    monkeypatch.setattr(fx, "_exit_shape_dict", no_ladder)
    body = "\n".join(fb.render_tomorrow_exits_lines())
    assert "🚨" in body and "NOT live" in body


def test_fail_open_on_resolution_error(monkeypatch):
    import fleet_executor as fx

    def boom(strategy, arm):
        raise RuntimeError("synthetic resolution failure")

    monkeypatch.setattr(fx, "_exit_shape_dict", boom)
    lines = fb.render_tomorrow_exits_lines()
    assert lines and "🚨" in lines[0] and "UNVERIFIED" in "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
