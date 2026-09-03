"""Guard: the Autonomy view -- GOAL-GAMMA-AUTONOMY-2026-09-03 DONE-WHEN (d).

J, verbatim: "we have an entire 'goal' dashboard and nothing is driving it ...
i need to see it happening, on the dashboard." `gamma_home.py` already computed
`payload["autonomy"]` (gamma_autonomy.py: awake/quiet/budget/recent_fires/
next_move) but no view ever rendered it -- `RENDER` in gamma_cockpit_js.py had
no entry, and the word "autonomy" appeared exactly once in the shipped page
(the JSON key). This file pins that the view now exists, is wired into the
router and the primary nav, and that the goal/autopilot/engines/learning data
it depends on degrades to an honest empty shape rather than crashing the page.

RED-PROOF (quoted in this session): temporarily removing the `autonomy:vAutonomy`
entry from gamma_cockpit_js.py's RENDER map made test_view_wired_into_render_and_nav
fail with `assert 'autonomy:vAutonomy' in vjs.JS` -- AssertionError, restored
immediately after. Temporarily deleting active-goal.json in a tmp STATE dir made
test_goal_block_absent_active_goal_file fail on `assert g["active"] is False`
(it returned True from a stale dict) before the guard clause was in place --
also restored.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_autonomy as ga            # noqa: E402
import gamma_cockpit_js as vjs         # noqa: E402
import gamma_home as gh                # noqa: E402


# ------------------------------------------------------- (1) view is wired

def test_view_wired_into_render_and_nav():
    assert "function vAutonomy(" in vjs.JS
    assert "autonomy:vAutonomy" in vjs.JS
    assert "id:'autonomy'" in vjs.JS, "Autonomy missing from VIEWS"
    assert "label:'Autonomy'" in vjs.JS
    assert "'autonomy'" in vjs.JS.split("const PRIMARY=", 1)[1].split("];", 1)[0], (
        "Autonomy must be a PRIMARY tab, not buried behind Cmd-K"
    )


# ------------------------------------------------------- (2) goal parsing

_GOAL_MD = """# GOAL: TEST-GOAL-2026-09-03

> J verbatim: *"this is the test directive."*

## DONE-WHEN
- (a) First falsifiable thing, wrapped onto
  a second physical line that must fold in.
- (b) Second falsifiable thing.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] T1 -- already done
- [~] T2 -- in progress, with a
  continuation line that must fold into T2, not become its own row
- [ ] T3 -- open item, should be next_open_item
- [B] T4 -- blocked
- [B-J] T5 -- blocked on J

## PROGRESS LOG
- 2026-09-03 -- opened
- 2026-09-03 -- first update

## HONEST STATE
Nothing shipped yet, still building.
"""


def test_goal_block_parses_done_when_queue_and_progress(tmp_path, monkeypatch):
    gfile = tmp_path / "goals" / "TEST-GOAL-2026-09-03.md"
    gfile.parent.mkdir(parents=True, exist_ok=True)
    gfile.write_text(_GOAL_MD, encoding="utf-8")
    monkeypatch.setattr(ga, "REPO", tmp_path)

    goal_ptr = {
        "active": True, "id": "GOAL-TEST-GOAL-2026-09-03",
        "file": "goals/TEST-GOAL-2026-09-03.md",
        "opened_at_et": "2026-09-03T00:00:00-04:00",
        "expires_at_et": "2026-09-17",
    }
    g = ga._goal_block(dt.datetime(2026, 9, 3), goal_ptr)

    assert g["active"] is True
    assert g["title"] == "Test goal"
    assert g["days_left"] == 14
    assert len(g["done_when"]) == 2
    assert "wrapped onto a second physical line that must fold in" in g["done_when"][0]

    by_id = {q["text"].split(" --")[0].strip(): q for q in g["queue"]}
    assert by_id["T1"]["state"] == "done"
    assert by_id["T2"]["state"] == "wip"
    assert by_id["T3"]["state"] == "todo"
    assert by_id["T4"]["state"] == "blocked"
    assert by_id["T5"]["state"] == "blocked_j"
    # T2's continuation line folded into the SAME item, not a new row
    assert "continuation line that must fold into T2" in by_id["T2"]["text"]
    assert len(g["queue"]) == 5

    assert g["progress_log"] == ["2026-09-03 -- opened", "2026-09-03 -- first update"]
    assert g["honest_state"] == "Nothing shipped yet, still building."
    assert g["verbatim"] == 'J verbatim: "this is the test directive."'
    assert g["next_item"] == "T3 -- open item, should be next_open_item"
    assert g["source"] == "goals/TEST-GOAL-2026-09-03.md"


def test_goal_block_absent_active_goal_file(tmp_path, monkeypatch):
    """No active-goal.json / inactive goal -> honest active:False, never a raise."""
    monkeypatch.setattr(ga, "REPO", tmp_path)
    g = ga._goal_block(dt.datetime.now(), {})
    assert g["active"] is False
    assert g["id"] is None and g["queue"] == [] and g["done_when"] == []
    assert g["next_item"] is None

    # An active pointer whose file does not exist on disk must degrade the same way.
    g2 = ga._goal_block(dt.datetime.now(), {"active": True, "file": "goals/NOPE.md", "id": "GOAL-NOPE"})
    assert g2["active"] is False


def test_humanize_goal_title():
    assert ga._humanize_goal_title("GOAL-GAMMA-AUTONOMY-2026-09-03") == "Gamma autonomy"
    assert ga._humanize_goal_title(None) == ""


def test_build_never_raises_and_carries_goal_autopilot_engines():
    """The live build (against real on-disk state) must always return the new keys."""
    d = ga.build()
    assert "goal" in d and "autopilot" in d and "engines" in d
    assert isinstance(d["goal"], dict) and "active" in d["goal"]
    assert set(d["engines"].keys()) == {"kitchen", "prospector"}
    assert "Gamma_GoalAutopilot" in d["tasks"]
    assert "Gamma_Home" in d["tasks"]


# ------------------------------------------------------- (3) rendered page

def test_rendered_page_has_autonomy_tab_and_no_undefined():
    payload = {
        "generated_et": "2026-09-03 20:00 Wednesday EDT", "built_at_et": "2026-09-03T20:00:00",
        "today": "2026-09-03", "stale_hours": 24.0, "hq": {}, "hq_source": {"path": "x", "age_h": 0},
        "calendar": {"views": {}}, "calendar_full": {"views": {}}, "calendar_scale": {"clamp": 1, "max_abs": 1},
        "calendar_source": {"path": "x", "age_h": 0}, "cost_meter": {}, "cost_meter_source": {"path": "x", "age_h": 0},
        "answers": [], "desks": {"desks": []}, "allocation": {"desks": []}, "org": {},
        "engine_room": {"engines": []}, "agents": {"events": [], "counts": {}, "sources": []},
        "thinking": {}, "positions": None, "briefing": {"lines": [], "flags": []},
        "wants_full": [], "wants_source": {"path": "x", "age_h": 0},
        "activity": {"sections": {}, "total_changes": 0},
        "autonomy": {"awake": True, "quiet": {}, "watcher": {}, "autofire": {"ever_fired": False, "fired_today": 0},
                     "tasks": {}, "recent_fires": [], "budget": {}, "next_move": None,
                     "goal": {"active": False}, "autopilot": None, "engines": {"kitchen": None, "prospector": None}},
        "goal": {"active": False}, "learning": {"error": "NO DATA", "windows": {}, "latest_verdicts": []},
        "army": {"orchestrator": None, "sessions": [], "workers": [], "pulses": [], "session_overflow": 0,
                 "legend": "", "scope_note": "", "source": {}},
        "cards": {"cards": [], "rth_now": False, "quiet_active": False, "legend": "", "source": {}},
        "glass": {}, "lanes": {},
    }
    html = gh.render(payload)
    assert "Autonomy" in html
    assert "[object Object]" not in html
    # Scoped to the embedded JSON payload, not the JS source -- the runtime
    # legitimately spells the keyword `undefined` (e.g. toLocaleString(undefined,...)).
    m = re.search(r"const D=(\{.*?\});", html, flags=re.S)
    assert m, "payload JSON blob not found in rendered page"
    assert "undefined" not in m.group(1)


def test_missing_learning_ledger_reports_no_data(monkeypatch):
    """No learning_ledger module and no cache file on disk -> honest NO DATA, never a crash."""
    import builtins
    real_import = builtins.__import__

    def blocked_import(name, *a, **kw):
        if name == "learning_ledger":
            raise ImportError("simulated: learning_ledger.py not built yet")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.setattr(gh, "STATE", Path("Z:/definitely/not/a/real/path/nope"))
    payload = gh.build(quiet=True)
    assert payload["learning"]["error"] == "NO DATA"
