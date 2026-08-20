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
