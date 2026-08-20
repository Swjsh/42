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
    # Fonts must be system stacks — a webfont would be a network dependency.
    assert "@font-face" not in html
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


def test_shipped_page_exists_and_is_fresh_enough():
    """Built != running. The file J opens must actually be on disk."""
    p = REPO / "analysis" / "home" / "index.html"
    if not p.exists():
        pytest.fail("analysis/home/index.html missing - run setup/scripts/gamma_home.py")
    assert p.stat().st_size > 10_000, "page suspiciously small"
    head = p.read_text(encoding="utf-8", errors="replace")[:3000]
    assert "Cockpit" in head, "shipped page is not the cockpit build"
    assert "__DATA_JSON__" not in head and "__JS__" not in head, "template placeholder left unsubstituted"
