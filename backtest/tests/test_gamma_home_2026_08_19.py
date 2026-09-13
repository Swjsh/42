"""Guard: the command center must never show J a number it did not read from a file.

`analysis/home/index.html` is the one surface J is meant to open unprompted. The
whole point is that he can trust it without checking. Two failure classes would
destroy that, and both have precedent in this repo:

  1. SILENT FABRICATION (C7). A missing/unreadable source must render a visible
     NO DATA card naming the file it wanted — never a plausible-looking default
     that reads as real. The free-tier workers already fabricated 12 reports;
     the home page must not become a nicer-looking version of that.

  2. MOJIBAKE / MARKDOWN LEAK. gamma_hq.py --json emits UTF-8; on Windows
     `subprocess(text=True)` decodes with the locale codepage (cp1252) and turned
     every em-dash into "â€"" on the first render. Separately, raw markdown
     sources leaked `> **Signal J wakes to (OP-25).**` and dumped falsifiable
     predictions as raw JSON onto the page.

RED-PROOF: drop `encoding="utf-8"` from _hq_json's subprocess call, or revert
_clean/_claim_of, and these fail.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_home as gh                       # noqa: E402


# ------------------------------------------------------- never fabricate

def test_missing_source_reports_no_data_not_a_default(tmp_path, monkeypatch):
    """Point every answer source at nonexistent files: no confident answers survive."""
    monkeypatch.setattr(gh, "STATE", tmp_path / "nope")
    monkeypatch.setattr(gh, "CALENDAR_JSON", tmp_path / "nope" / "calendar-data.json")
    monkeypatch.setattr(gh, "STATUS_MD", tmp_path / "nope" / "STATUS.md")
    monkeypatch.setattr(gh, "SIGNATURE_MD", tmp_path / "nope" / "SIGNATURE.md")

    answers = gh.build_answers()
    assert answers, "build_answers must still return cards when sources are gone"
    for a in answers:
        blob = json.dumps(a).lower()
        assert "no data" in blob or "unreadable" in blob or a["verdict"] in ("RED", "NO DATA"), (
            "a card with no source must say so, not answer confidently: %r" % a
        )
    # And nothing may invent money.
    money_card = [a for a in answers if "money" in a["q"].lower()][0]
    assert money_card["verdict"] == "NO DATA", money_card
    assert not re.search(r"[+-]\$\d", money_card["answer"]), money_card


def test_every_answer_names_its_source():
    """A number with no provenance is exactly what this page exists to avoid."""
    for a in gh.build_answers():
        assert a.get("sources"), "answer %r has no source" % a["q"]
        for s in a["sources"]:
            assert s.get("path"), s
            assert "age_h" in s, s


def test_source_paths_render_posix():
    """Mixed separators (automation\\state vs automation/overnight) read as sloppy."""
    for a in gh.build_answers():
        for s in a["sources"]:
            assert "\\" not in s["path"], s["path"]


# ------------------------------------------------------- text hygiene

def test_markdown_is_stripped_but_snake_case_survives():
    assert gh._clean("> **Signal J wakes to (OP-25).** Weekly check") == "Signal J wakes to (OP-25). Weekly check"
    # The first fix over-reached and turned recency_check.py into recencycheck.py.
    assert "recency_check.py" in gh._clean("reusable backtest/autoresearch/recency_check.py, generalizes")
    assert "**" not in gh._clean("**bold** text")


def test_predictions_render_as_claims_not_raw_json():
    row = {"claim": "SPY reclaims 768.24 with a confirmed 5m close",
           "trigger_window": "09:35-11:00 ET"}
    out = gh._claim_of(row)
    assert out.startswith("SPY reclaims 768.24"), out
    assert "09:35-11:00 ET" in out
    # Check for the JSON *key* form, not the bare word — "reclaims" contains "claim".
    assert "{" not in out and '"claim"' not in out and "'claim'" not in out
    # Same row arriving as a JSON *string* must resolve identically.
    assert gh._claim_of(json.dumps(row)) == out


def test_clip_never_cuts_mid_word():
    long = "alpha bravo charlie delta echo foxtrot golf hotel india juliet " * 6
    out = gh._clip(long, 120)
    assert len(out) <= 130, len(out)
    assert not out.rstrip("…").endswith(("alph", "brav", "charli")), out


def test_money_formatting_signs_and_separators():
    assert gh._money(3613) == "+$3,613"
    assert gh._money(-1941) == "-$1,941"
    assert gh._money(0) == "+$0"
    assert gh._money(None) == "?"


# ------------------------------------------------------- rendered page

def test_rendered_page_is_self_contained_and_clean():
    payload = gh.build(quiet=True)
    html = gh.render(payload)
    assert html.lstrip().startswith("<!doctype html>")
    assert "__DATA_JSON__" not in html, "data placeholder was not substituted"
    # No external FETCHES: the page must work with no server and no network.
    # Scope this to markup/CSS, where a URL would actually be requested. URLs
    # inside the embedded JSON payload are inert data (worker-registry.json cites
    # the Anthropic docs page its fan-out caps came from), and XML namespace URIs
    # are identifiers, never fetched.
    markup = re.sub(r"const D=\{.*?\};", "", html, flags=re.S)
    probe = (markup.replace("http://www.w3.org/", "")
                   .replace("https://www.w3.org/", "")
                   .replace("http://localhost", ""))
    assert "http://" not in probe and "https://" not in probe, "external http reference in markup/CSS"
    assert "<script src" not in html and "<link rel=\"stylesheet\"" not in html
    assert "cdn." not in html.lower() and "@import" not in html
    # Fonts are vendored + base64-inlined (gamma_cockpit_vendor.py) -- @font-face
    # is now expected, but every src: must stay a data: URI, never a network
    # fetch (2026-09-03 amendment, WS-A: strengthens intent, doesn't drop it).
    faces = re.findall(r"@font-face\{[^}]*\}", html)
    assert faces, "expected inlined @font-face rules"
    for face in faces:
        assert "src:url(data:" in face.replace(" ", ""), face[:120]
    # Mojibake canaries from the cp1252 decode bug.
    for bad in ("Â·", "â€", "Ã©"):
        assert bad not in html, "mojibake %r survived - check subprocess encoding" % bad


def test_compact_calendar_preserves_source_values_exactly():
    """The home grid must not re-derive P&L; it only reshapes what the calendar wrote."""
    src = {"views": {"BOOK": {"days": {"2026-08-04": {"pnl_gross": 3624.0, "pnl_net": 3613.0,
                                                      "trade_count": 25, "trades": [1, 2, 3]}},
                              "summary": {"total_pnl_net": -1940.98}}}}
    out = gh.compact_calendar(src)
    day = out["views"]["BOOK"]["days"]["2026-08-04"]
    assert day == {"g": 3624.0, "n": 3613.0, "t": 25}
    assert out["views"]["BOOK"]["summary"]["total_pnl_net"] == -1940.98
    # The heavy per-trade payload stays out of the home page.
    assert "trades" not in day


def test_station_section_renders_from_fixture_data(monkeypatch, tmp_path):
    """GOAL-GAMMA-STATION-2026-09-13 item (5): the cockpit's Station panel must
    carry real ideas-board/brief/planner/ledger content through to the shipped
    page. Point gamma_cockpit_station's module-level paths at a fixture
    automation/state/station/ directory, build the payload, and confirm (a) the
    payload shape is correct and (b) the fixture strings actually reach the
    rendered page's `const D=...` data blob (the JS renderer reads D.station
    client-side; nothing here executes that JS, so the data blob is the
    furthest point this test suite can verify short of a real browser)."""
    import gamma_cockpit_station as gcs

    station_dir = tmp_path / "station"
    station_dir.mkdir()
    ideas_path = station_dir / "ideas-board.json"
    brief_path = station_dir / "station-brief.md"
    config_path = station_dir / "config.json"
    mode_path = station_dir / "mode.json"
    ledger_path = station_dir / "loop-ledger.jsonl"

    fixture_title = "Fixture idea for station panel test"
    ideas_path.write_text(json.dumps([{
        "id": "fixture01", "ts_et": "2026-09-13 12:00:00 ET", "prompted_by": "station-loop",
        "status": "proposed", "model": "gamma-planner-fast", "title": fixture_title,
        "mechanism": "A fixture mechanism sentence.", "evidence": ["fixture evidence line"],
        "proposed_shadow_test": "Run a fixture shadow test.", "cost_line": "$0",
        "confidence": "med",
    }]), encoding="utf-8")
    brief_path.write_text("2026-09-13 12:00:00 ET - model gamma-planner-fast - 1 cards on the board\n\n"
                          "Fixture brief body text.\n", encoding="utf-8")
    config_path.write_text(json.dumps({"model": "gamma-planner-fast"}), encoding="utf-8")
    mode_path.write_text(json.dumps({"mode": "work"}), encoding="utf-8")
    ledger_path.write_text(json.dumps({
        "ts_et": "2026-09-13 12:00:00 ET", "model": "gamma-planner-fast", "status": "ok",
        "reason": "", "duration_s": 12.3, "prompt_tokens": 5000, "gen_tokens": 100,
        "cards_added": 1, "board_size": 1,
    }) + "\n", encoding="utf-8")

    monkeypatch.setattr(gcs, "STATION_DIR", station_dir)
    monkeypatch.setattr(gcs, "IDEAS_BOARD_PATH", ideas_path)
    monkeypatch.setattr(gcs, "BRIEF_PATH", brief_path)
    monkeypatch.setattr(gcs, "CONFIG_PATH", config_path)
    monkeypatch.setattr(gcs, "MODE_PATH", mode_path)
    monkeypatch.setattr(gcs, "LEDGER_PATH", ledger_path)
    monkeypatch.setattr(gcs, "_gpu_util_pct", lambda: None)  # never shell out in a test

    station_payload = gcs.build()
    assert station_payload["ok"] is True
    assert station_payload["ideas"]["ok"] is True
    assert station_payload["ideas"]["cards"][0]["title"] == fixture_title
    assert station_payload["brief"]["ok"] is True
    assert "Fixture brief body text." in station_payload["brief"]["text"]
    assert station_payload["planner"]["ok"] is True
    assert station_payload["planner"]["model"] == "gamma-planner-fast"
    assert station_payload["planner"]["mode"] == "work"
    assert station_payload["ledger"]["ok"] is True
    assert len(station_payload["ledger"]["rows"]) == 1

    payload = gh.build(quiet=True)
    payload["station"] = station_payload  # splice the fixture in without rebuilding the whole page
    html = gh.render(payload)

    assert fixture_title in html, "fixture idea-card title never reached the rendered data blob"
    assert "Fixture brief body text." in html
    assert "gamma-planner-fast" in html
    assert "stationPanel" in html, "the client-side Station renderer never shipped in the page JS"
    assert "gc-station" in html


def test_shipped_page_exists_and_is_fresh_enough():
    """Built != running. The file J opens must actually be on disk."""
    p = REPO / "analysis" / "home" / "index.html"
    if not p.exists():
        pytest.fail("analysis/home/index.html missing - run setup/scripts/gamma_home.py")
    assert p.stat().st_size > 10_000, "page suspiciously small"
    head = p.read_text(encoding="utf-8", errors="replace")[:3000]
    assert "Cockpit" in head, "shipped page is not the cockpit build"
    assert "__DATA_JSON__" not in head and "__JS__" not in head, "template placeholder left unsubstituted"
