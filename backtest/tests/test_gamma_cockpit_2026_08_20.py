"""Guard: the cockpit's structure, honesty rails and self-containment.

`analysis/home/index.html` is the surface J opens instead of asking. It replaced
five earlier presence surfaces, all of which died for the same reason: they were
add-on channels nobody kept honest. These tests pin the properties that make this
one different.

WHAT IS PINNED
  * SELF-CONTAINED. No script src, no stylesheet link, no @import, no @font-face,
    no CDN. It must render from a file:// URL with no network, forever — the
    previous home base (localhost:3000/gamma) was found DEAD behind a keepalive.
  * EVERY VIEW EXISTS and is wired into the nav.
  * NO PLACEHOLDER LEAKS — an unsubstituted __DATA_JSON__ / __JS__ ships a broken
    page that still looks like a page.
  * NO AGGREGATE-ONLY SCREEN. Per-desk data must be present; hiding a weak desk
    behind a strong one is the anti-pattern J has called out by name.
  * COLOUR VOCABULARY. Red/green belong to P&L. System health uses traffic-light
    dots. Overloading them is a documented dashboard anti-pattern.
  * REDUCED MOTION is honoured.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_home as gh                         # noqa: E402
import gamma_cockpit_ui as ui                   # noqa: E402
import gamma_cockpit_js as vjs                  # noqa: E402

PAGE = REPO / "analysis" / "home" / "index.html"


@pytest.fixture(scope="module")
def html():
    return gh.render(gh.build(quiet=True))


# ------------------------------------------------------- self-contained

def test_no_external_resource_tags(html):
    for bad in ("<script src", "<link rel=\"stylesheet\"", "@import", "@font-face",
                "cdn.", "unpkg", "jsdelivr", "googleapis"):
        assert bad not in html.lower() if bad.islower() else bad not in html, bad


def test_no_placeholder_survives(html):
    for ph in ("__DATA_JSON__", "__JS__", "__CSS__", "__VIEWS_JS__"):
        assert ph not in html, "unsubstituted placeholder %s" % ph


def test_payload_cannot_break_out_of_its_script_block(html):
    """A source string containing </script> would end the block and inject markup."""
    body = re.sub(r"<script>__?JS.*", "", html, flags=re.S)
    assert "</script" not in body.split("const D=", 1)[-1].split("</script>", 1)[0]


# ------------------------------------------------------- structure

def test_every_view_is_defined_and_navigable():
    for v in ("overview", "desks", "orchestration", "journal", "answers", "activity"):
        assert "id:'%s'" % v in vjs.JS, "view %s missing from VIEWS" % v
    assert "const RENDER={" in vjs.JS
    for fn in ("vOverview", "vDesks", "vOrch", "vJournal", "vAnswers", "vActivity"):
        assert "function %s(" % fn in vjs.JS, "renderer %s missing" % fn


def test_routing_does_not_depend_on_hash_mutation():
    """Some hosts serve this file from a data: URL where assigning location.hash
    is a no-op — that left the nav visibly dead once already."""
    assert "function route(want)" in vjs.JS, "route() must accept an explicit view id"
    assert "a.onclick=e=>{e.preventDefault();route(v.id)" in vjs.JS


def test_drilldowns_exist():
    for fn in ("deskDrawer", "dayDrawer", "answerDrawer", "openDrawer", "closeDrawer"):
        assert "function %s(" % fn in vjs.JS, "%s missing" % fn


def test_command_palette_indexes_every_entity_kind():
    for kind in ("'View'", "'Desk'", "'Agent'", "'Answer'", "'Day'"):
        assert kind in vjs.JS, "palette does not index %s" % kind


# ------------------------------------------------------- honesty rails

def test_payload_carries_per_desk_data_not_just_an_aggregate(html):
    payload = gh.build(quiet=True)
    desks = (payload.get("desks") or {}).get("desks") or []
    assert len(desks) >= 4, "fewer than four desks — per-desk view would be incomplete"
    for d in desks:
        assert d.get("metric"), "desk %s has no headline metric" % d.get("id")
        assert d.get("chip"), "desk %s has no status" % d.get("id")


def test_every_answer_still_ships_its_sources(html):
    payload = gh.build(quiet=True)
    for a in payload["answers"]:
        assert a.get("sources"), a["q"]


def test_source_row_is_rendered_for_provenance():
    assert "function srcRow(" in vjs.JS
    assert "D.stale_hours" in vjs.JS, "staleness threshold not applied to source badges"


def test_calendar_ramp_is_clamped_and_extremes_annotated():
    """One blowout day must not flatten the month's colour ramp."""
    assert "D.calendar_scale" in vjs.JS
    assert "clamp" in vjs.JS and "max_abs" in vjs.JS
    scale = gh.calendar_scale(gh._load_json(gh.CALENDAR_JSON)[0] or {})
    assert scale["clamp"] > 0


def test_health_uses_dots_not_pnl_colours():
    """Red/green are P&L's vocabulary. Health must not borrow them as fills."""
    assert "function health(" in vjs.JS
    assert ".chip.ok .dot{background:var(--pos)}" in ui.CSS
    assert "traffic-light" in ui.CSS or "traffic-light" in ui.__doc__


def test_reduced_motion_is_honoured():
    assert "prefers-reduced-motion" in ui.CSS
    assert "const RM=matchMedia('(prefers-reduced-motion:reduce)').matches" in vjs.JS
    assert "if(RM" in vjs.JS, "count-up must no-op under reduced motion"


def test_numbers_use_tabular_figures():
    """Jittering digits are the tell of an amateur financial UI."""
    assert "tabular-nums" in ui.CSS


# ------------------------------------------------------- shipped artifact

def test_shipped_page_is_current_and_substantial():
    if not PAGE.exists():
        pytest.fail("run setup/scripts/gamma_home.py")
    txt = PAGE.read_text(encoding="utf-8", errors="replace")
    assert len(txt) > 200_000, "cockpit suspiciously small — did the payload build?"
    assert "Cockpit" in txt[:3000]
    for ph in ("__DATA_JSON__", "__JS__", "__CSS__"):
        assert ph not in txt
    for bad in ("Â·", "â€"):
        assert bad not in txt, "mojibake in the shipped page"


# ── Worker honesty (2026-08-30) ────────────────────────────────────────────────
# J, third ask: "i still dont know what im looking at like subagent wise on the
# screen." Investigating it surfaced something worse than illegibility: session
# 42-c9 rendered "8 workers +43" beside five solid dots while EVERY ONE of its 51
# subagents had finished 9.3 hours earlier. The `8` was never a quantity — it is
# MAX_WORKERS_PER_SESSION, the display cap — so the label read cap+overflow and
# implied a standing army that did not exist. A cockpit that looks authoritative
# while overstating live capacity is the exact failure this file exists to prevent.
def test_payload_separates_workers_ever_spawned_from_workers_running_now():
    """worker_count is HISTORY; only worker_active may back a present-tense claim."""
    from gamma_cockpit_army import build_army

    army = build_army()
    workers = army.get("workers") or []
    for s in army.get("sessions") or []:
        assert "worker_active" in s, f"{s.get('name')} cannot state live capacity honestly"
        assert isinstance(s["worker_active"], int)
        assert 0 <= s["worker_active"] <= s["worker_count"], (
            f"{s.get('name')}: {s['worker_active']} running exceeds {s['worker_count']} spawned"
        )
        # The count must agree with the workers actually shipped for that session,
        # so the number and the dots beside it can never tell different stories.
        shipped_live = sum(
            1 for w in workers if w.get("session_id") == s["session_id"] and w.get("active")
        )
        assert s["worker_active"] >= shipped_live, (
            f"{s.get('name')}: payload ships {shipped_live} live workers but claims "
            f"{s['worker_active']}"
        )


def test_every_worker_carries_a_human_purpose():
    """The card says what each agent is FOR, so it must always have something to say.

    Before this, the Army view rendered subagents as five identical grey circles: the
    agent_type, model, task text and live/done state were all in the payload and none
    reached the screen. `purpose` is the field the row is built on, so an empty one
    puts a blank line where the answer to J's question belongs.
    """
    from gamma_cockpit_army import build_army

    for w in build_army().get("workers") or []:
        assert w.get("purpose"), f"worker {w['agent_id']} has no purpose to show"
        assert not w["purpose"].lstrip().startswith(("[", "{")), (
            f"worker {w['agent_id']} purpose opens with a data blob, not an instruction: "
            f"{w['purpose'][:60]!r}"
        )
        # Internal scratch fields must never reach the page.
        assert "_task_full" not in w and "_distinct" not in w


def test_purpose_prefers_the_spawners_own_description():
    """The Agent tool's `description` is a human label written for exactly this job.

    It was being ignored while the page rendered 180 chars of shared prompt preamble.
    """
    from gamma_cockpit_army import _derive_purposes

    rows = [{"session_id": "s", "workflow_id": "", "description": "Mine design skills",
             "task": "You are a researcher. Go read a hundred repos and report back.",
             "_task_full": "You are a researcher. Go read a hundred repos and report back."}]
    _derive_purposes(rows)
    assert rows[0]["purpose"] == "Mine design skills"


def test_siblings_sharing_boilerplate_get_distinguishing_purposes():
    """Workflow fan-outs share a long context header; the row must show what DIFFERS.

    Rendering the common prefix gave every sibling the same label -- the anonymous
    grey circle problem in text form.
    """
    from gamma_cockpit_army import _derive_purposes

    shared = "CONTEXT: " + ("the same long shared preamble every sibling receives. " * 3)
    rows = [
        {"session_id": "s", "workflow_id": "wf_1", "description": "",
         "task": shared, "_task_full": shared + "Audit the login flow for races."},
        {"session_id": "s", "workflow_id": "wf_1", "description": "",
         "task": shared, "_task_full": shared + "Benchmark the cache eviction policy."},
    ]
    _derive_purposes(rows)
    purposes = [r["purpose"] for r in rows]
    assert purposes[0] != purposes[1], "siblings still share one label"
    assert "Audit the login flow" in purposes[0]
    assert "Benchmark the cache" in purposes[1]
    assert "shared preamble" not in purposes[0]
