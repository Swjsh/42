"""Guard: the engine-room / agent / briefing feeds, and the hydration contract.

J asked for four things this pins:
  "ensure accuracy and proper caching and data hydration"
  "ensure I know what agents are doing"
  "I want to see the heartbeat for each of the engines' ticks"
  "command center should be like me talking to an employee"

THE HYDRATION CONTRACT (the defect this file exists to prevent)
  The cockpit is a static file rebuilt every 30 min. The first build BAKED
  relative ages ("0.1h") into the HTML — so a page left open for six hours kept
  insisting its data was six minutes old. That is silent staleness dressed as
  freshness, the exact anti-pattern the whole surface exists to avoid. Feeds must
  therefore emit ABSOLUTE ISO stamps and the page must compute the age at VIEW
  time, on a timer.

THE FRAME CONTRACT
  This box runs Mountain; every ledger stamps ET. A raw mtime is 2h behind the
  ts_et beside it. Mixing them puts two clocks on one screen — the documented TZ
  scar. Offsets are DISCOVERED from et_clock.py at runtime, never hardcoded.

THE BRIEFING CONTRACT
  It is templates over on-disk state, never an LLM. An LLM writing J's first
  paragraph would be the fabrication risk this cockpit was built to close,
  pointed at the most-read text on the page.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_cockpit_data as cd                 # noqa: E402
import gamma_cockpit_js as vjs                  # noqa: E402
import gamma_home as gh                         # noqa: E402


# ----------------------------------------------------------- hydration

def test_feeds_emit_absolute_stamps_not_baked_ages():
    er = cd.engine_room()
    for e in er["engines"]:
        assert "last_write" in e, e["id"]
        if e["last_write"]:
            datetime.fromisoformat(e["last_write"])      # must parse as ISO
        assert "age_h" not in e, "%s baked a relative age" % e["id"]


def test_page_computes_age_at_view_time_on_a_timer():
    assert "function agoOf(" in vjs.JS and "function paintAge(" in vjs.JS
    assert "setInterval" in vjs.JS and ".age" in vjs.JS, "ages never refresh"
    assert "Date.now()" in vjs.JS, "age is not computed against the viewer's clock"


def test_build_stamp_is_machine_parseable():
    """_et_label() is a human string Date.parse cannot read — that rendered the
    briefing badge as 'unknown age'."""
    p = gh.build(quiet=True)
    datetime.fromisoformat(p["built_at_et"])
    assert "D.built_at_et" in vjs.JS, "page still ages against the human label"


# ----------------------------------------------------------- ET frame

def test_mtimes_are_converted_to_et_not_left_local():
    assert cd._et_offset_h() is not None
    assert "_et_offset_h()" in Path(cd.__file__).read_text(encoding="utf-8")
    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert "timedelta(hours=_et_offset_h())" in src, "mtime not shifted into ET"


def test_et_offset_is_discovered_not_hardcoded():
    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert "et_clock.py" in src, "offset must come from the DST-aware clock"
    assert "hours=2" not in src and "+ 2)" not in src, "hardcoded ET offset"


def test_engine_tick_stamps_and_last_write_share_one_frame():
    """A tick at 15:55 ET next to a 'last write' of 13:55 local is two clocks."""
    er = cd.engine_room()
    spy = [e for e in er["engines"] if e["id"] == "spy-core"][0]
    if not spy["ticks"] or not spy["last_write"]:
        return
    newest = max(t["ts"] for t in spy["ticks"] if t.get("ts"))
    lw = datetime.fromisoformat(spy["last_write"])
    gap = abs((lw - datetime.fromisoformat(newest)).total_seconds())
    assert gap < 3600, "last_write and tick stamps are %.1fh apart — frame mismatch" % (gap / 3600)


# ----------------------------------------------------------- engine room

def test_every_engine_reports_from_its_own_ledger():
    er = cd.engine_room()
    ids = {e["id"] for e in er["engines"]}
    assert {"spy-core", "fut-trader", "multi-core", "kalshi"} <= ids, ids
    srcs = [e["source"] for e in er["engines"]]
    assert len(set(srcs)) == len(srcs), "two engines share a ledger — one is a summary of the other"


def test_blockers_are_named_not_bare_indices():
    """'blocked by 6' tells J nothing; filters.py index 6 is the spread gate."""
    assert cd.blocker_name(6).startswith("6 ·") and "spread" in cd.blocker_name(6)
    assert cd.blocker_name(99) == "99", "unknown index must degrade to itself, not invent a name"
    er = cd.engine_room()
    spy = [e for e in er["engines"] if e["id"] == "spy-core"][0]
    for t in spy["ticks"]:
        for b in t.get("blockers", []):
            assert not b.isdigit(), "bare blocker index leaked: %r" % b


def test_engine_ticks_carry_the_reason_not_just_the_verdict():
    er = cd.engine_room()
    spy = [e for e in er["engines"] if e["id"] == "spy-core"][0]
    if spy["ticks"]:
        t = spy["ticks"][0]
        assert "why" in t and "scores" in t and "ctx" in t


# --------------------------------------------------- kalshi lane (KALSHI-COCKPIT-ENGINE-TICK-STALE-LANE)

def test_kalshi_engine_reads_the_live_weather_lane_not_the_retired_tick_lane():
    """The kalshi block used to read shadow-ledger.jsonl / last-tick.json --
    files belonging to the RETIRED kalshi_tick.py SPY-directional lane
    (superseded 2026-08-09, no scheduled task exists for it). The live lane is
    kalshi_auto.py's weather-predictions.jsonl (Gamma_KalshiAuto, 18:10 ET daily)."""
    er = cd.engine_room()
    kalshi = [e for e in er["engines"] if e["id"] == "kalshi"][0]
    assert kalshi["source"] == "automation/state/kalshi/weather-predictions.jsonl", kalshi["source"]
    assert "shadow-ledger" not in kalshi["source"]


def test_kalshi_weather_tick_shapes_a_real_row_with_no_verdict_field():
    """Weather rows carry no `verdict` key the way other engines' ticks do --
    _generic_tick would degrade every one of these to '—'. A real unscored row
    (observed is null) must shape to PICKED; a real scored losing row (pick_won
    is false) must shape to LOSS."""
    unscored = {
        "ts_utc": "2026-09-02T14:28:51.705760+00:00", "day": "2026-09-03",
        "series": "KXHIGHLAX", "label": "Los Angeles Intl",
        "pick_ticker": "KXHIGHLAX-26SEP03-B76.5", "pick_p": 0.2706, "pick_ask": 0.49,
        "observed": None,
    }
    t = cd._kalshi_weather_tick(unscored)
    assert t["verdict"] == "PICKED", t
    assert t["sym"] == "KXHIGHLAX" and t["ts"] == unscored["ts_utc"]
    assert "KXHIGHLAX-26SEP03-B76.5" in t["why"]

    scored_loss = {
        "ts_utc": "2026-08-09T23:42:07.244983+00:00", "day": "2026-08-10",
        "series": "KXHIGHNY", "label": "NYC Central Park",
        "pick_ticker": "KXHIGHNY-26AUG10-B91.5", "pick_p": 0.2724, "pick_ask": 0.27,
        "observed": 85.0, "abs_err": 6.53, "pick_won": False,
    }
    t2 = cd._kalshi_weather_tick(scored_loss)
    assert t2["verdict"] == "LOSS", t2


# ----------------------------------------------------------- agents

def test_agent_feed_surfaces_the_fabrication_verdict():
    """Which worker outputs were TRUSTED is the whole point of showing agents."""
    a = cd.agent_feed()
    assert "counts" in a and "fabricated" in a["counts"]
    assert "artifact_verdict" in Path(cd.__file__).read_text(encoding="utf-8")


def test_agent_events_are_newest_first_and_stamped():
    a = cd.agent_feed()
    ts = [e["ts"] for e in a["events"]]
    assert ts == sorted(ts, reverse=True), "agent feed is not newest-first"
    assert all(e.get("ts") for e in a["events"])


# ----------------------------------------------------------- briefing

def test_briefing_is_deterministic_templates_not_an_llm():
    src = Path(cd.__file__).read_text(encoding="utf-8")
    body = src.split("def briefing(", 1)[1]
    for banned in ("openai", "anthropic", "swarm_client", "call_role", "requests.", "urllib"):
        assert banned not in body.lower(), "briefing reaches for a model: %s" % banned


def test_briefing_repeats_exactly_on_identical_state():
    p = gh.build(quiet=True)
    a = cd.briefing(p["desks"]["desks"], p["allocation"], p["answers"])
    b = cd.briefing(p["desks"]["desks"], p["allocation"], p["answers"])
    assert a["lines"] == b["lines"], "briefing is not deterministic"


def test_briefing_speaks_first_person_and_names_the_decision():
    p = gh.build(quiet=True)
    br = cd.briefing(p["desks"]["desks"], p["allocation"], p["answers"])
    joined = " ".join(br["lines"]).lower()
    assert re.search(r"\bi (held|called|was|would)\b", joined), br["lines"]
    top = (p["allocation"].get("desks") or [{}])[0]
    if top.get("armable_unarmed"):
        assert any(f["kind"] == "decision" for f in br["flags"]), "a rotting decision was not raised"


def test_briefing_never_invents_a_number_absent_from_state():
    """Every dollar figure in the briefing must appear in the payload it read."""
    p = gh.build(quiet=True)
    br = cd.briefing(p["desks"]["desks"], p["allocation"], p["answers"])
    import json as _j
    hay = _j.dumps(p, default=str)
    for money in re.findall(r"[+-]?\$[\d,]+", " ".join(br["lines"] + [f["text"] for f in br["flags"]])):
        assert money.replace("$", "").replace(",", "").lstrip("+-") in hay.replace(",", ""), money
