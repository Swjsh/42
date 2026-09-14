"""Guard: setup/scripts/scout_feed.py -- Scout's continuous feed scan (CREW-RIG R1,
GOAL-GAMMA-STATION-2026-09-13, 2026-09-14 build). J's verdict that started this build:
"Scout should NEVER be done -- Scout is pretty much infinite, always scouting things."

Locks in: RSS/Atom item parsing on saved sample bodies (NEVER a real network call --
_fetch_bytes itself is never exercised here, every test injects its own fetch_fn), tag
extraction, the (source,title) dedupe + 2000-row cap (oldest dropped first), the
<25min rescan-skip gate, and that a crew-event is emitted ONLY when new_items > 0.
Every path is passed explicitly per-test via tmp_path -- no test here ever reads or
writes the real repo's automation/scout/state/.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import scout_feed as sfeed  # noqa: E402
import crew_events as ce  # noqa: E402
import station_board as sb  # noqa: E402

SAMPLE_RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<title>Sample Feed</title>
<item>
  <title>Fed hikes rates by 25bp, first since 2023</title>
  <link><![CDATA[https://example.com/fed-hike]]></link>
  <pubDate><![CDATA[Mon, 14 Sep 2026 14:00:00 GMT]]></pubDate>
</item>
<item>
  <title>Oil surges 6% on Red Sea shipping disruption</title>
  <link>https://example.com/oil-surge</link>
  <pubDate>Mon, 14 Sep 2026 09:00:00 GMT</pubDate>
</item>
<item>
  <title>Local weather: sunny skies expected this week</title>
  <link>https://example.com/weather</link>
  <pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate>
</item>
</channel></rss>"""

SAMPLE_ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
  <title>CPI comes in hot at 3.4% YoY</title>
  <link href="https://example.com/cpi" />
  <updated>2026-09-14T12:00:00Z</updated>
</entry>
</feed>"""

MALFORMED = b"<rss><channel><item><title>unterminated"


def _fetch_map(mapping: dict):
    return lambda url: mapping.get(url)


# ============================================================================
# _parse_feed_items -- RSS (CDATA + plain link) and Atom, malformed XML
# ============================================================================

def test_parse_feed_items_rss_extracts_title_link_pubdate():
    items = sfeed._parse_feed_items(SAMPLE_RSS, "example.com")
    assert len(items) == 3
    assert items[0]["title"] == "Fed hikes rates by 25bp, first since 2023"
    assert items[0]["link"] == "https://example.com/fed-hike"
    assert items[0]["pub_date"] == "Mon, 14 Sep 2026 14:00:00 GMT"
    assert items[0]["source"] == "example.com"
    assert items[1]["link"] == "https://example.com/oil-surge", "plain (non-CDATA) <link> text must parse too"


def test_parse_feed_items_atom_uses_href_attribute():
    items = sfeed._parse_feed_items(SAMPLE_ATOM, "example.com")
    assert len(items) == 1
    assert items[0]["title"] == "CPI comes in hot at 3.4% YoY"
    assert items[0]["link"] == "https://example.com/cpi"


def test_parse_feed_items_malformed_xml_returns_empty_list_not_a_crash():
    assert sfeed._parse_feed_items(MALFORMED, "example.com") == []


def test_parse_feed_items_skips_entries_with_no_title():
    raw = b"<rss><channel><item><link>https://x</link></item></channel></rss>"
    assert sfeed._parse_feed_items(raw, "x") == []


# ============================================================================
# Tagging
# ============================================================================

def test_tag_title_matches_multiple_keyword_buckets():
    tags = sfeed._tag_title("Fed hikes rates as oil surges amid geopolitical conflict")
    assert set(tags) == {"fed", "oil", "geopolitics"}


def test_tag_title_no_match_returns_empty_list():
    assert sfeed._tag_title("Local weather: sunny skies expected") == []


# ============================================================================
# scan_feeds -- per-feed fail-open (one dead/malformed feed never aborts the scan)
# ============================================================================

def test_scan_feeds_one_dead_feed_does_not_abort_the_rest():
    fetch = _fetch_map({"https://ok.example/rss": SAMPLE_RSS})
    result = sfeed.scan_feeds(["https://ok.example/rss", "https://dead.example/rss"], fetch_fn=fetch)
    assert result["feeds_ok"] == 1
    assert result["feeds_failed"] == 1
    assert len(result["items"]) == 3


def test_scan_feeds_malformed_body_counts_as_failed_not_ok():
    fetch = _fetch_map({"https://bad.example/rss": MALFORMED})
    result = sfeed.scan_feeds(["https://bad.example/rss"], fetch_fn=fetch)
    assert result["feeds_ok"] == 0
    assert result["feeds_failed"] == 1


def test_scan_feeds_a_raising_fetch_fn_is_treated_as_a_dead_feed():
    def boom(url):
        raise RuntimeError("network is on fire")
    result = sfeed.scan_feeds(["https://x"], fetch_fn=boom)
    assert result["feeds_ok"] == 0
    assert result["feeds_failed"] == 1
    assert result["items"] == []


# ============================================================================
# dedupe_new_items -- (source, title) hash, case/whitespace-insensitive
# ============================================================================

def test_dedupe_new_items_drops_items_already_seen():
    items = [{"title": "Fed hikes rates", "link": "l", "pub_date": "p", "source": "s"}]
    new_rows, seen = sfeed.dedupe_new_items(items, set(), now_et="t1")
    assert len(new_rows) == 1
    new_rows2, _ = sfeed.dedupe_new_items(items, seen, now_et="t2")
    assert new_rows2 == [], "an item already in seen_hashes must never re-count as new"


def test_dedupe_new_items_is_case_and_whitespace_insensitive():
    a = {"title": "Fed Hikes Rates", "link": "l", "pub_date": "p", "source": "s"}
    b = {"title": "  fed   hikes rates  ", "link": "l2", "pub_date": "p2", "source": "s"}
    _, seen = sfeed.dedupe_new_items([a], set(), now_et="t1")
    new_rows2, _ = sfeed.dedupe_new_items([b], seen, now_et="t2")
    assert new_rows2 == [], "normalized title match across whitespace/case must dedupe"


def test_dedupe_new_items_same_title_different_source_is_not_a_duplicate():
    a = {"title": "Fed hikes rates", "link": "l", "pub_date": "p", "source": "cnbc"}
    b = {"title": "Fed hikes rates", "link": "l2", "pub_date": "p2", "source": "marketwatch"}
    _, seen = sfeed.dedupe_new_items([a], set(), now_et="t1")
    new_rows2, _ = sfeed.dedupe_new_items([b], seen, now_et="t2")
    assert len(new_rows2) == 1, "dedupe key is (source, title) -- a different source is a different item"


def test_dedupe_new_items_tags_each_new_row():
    items = [{"title": "Fed hikes rates on hot CPI", "link": "l", "pub_date": "p", "source": "s"}]
    new_rows, _ = sfeed.dedupe_new_items(items, set(), now_et="t1")
    assert set(new_rows[0]["tags"]) == {"fed", "cpi"}


# ============================================================================
# _append_capped_jsonl -- oldest dropped first
# ============================================================================

def test_append_capped_jsonl_drops_oldest_first(tmp_path):
    path = tmp_path / "feed.jsonl"
    batch = [{"hash": f"h{i}", "title": f"t{i}"} for i in range(5)]
    sfeed._append_capped_jsonl(path, batch, cap=3)
    rows = sb.read_jsonl(path)
    assert [r["hash"] for r in rows] == ["h2", "h3", "h4"], "oldest rows must drop first"


def test_append_capped_jsonl_empty_new_rows_is_a_noop(tmp_path):
    path = tmp_path / "feed.jsonl"
    result = sfeed._append_capped_jsonl(path, [], cap=10)
    assert result == []
    assert not path.exists(), "an empty batch must never create the file"


# ============================================================================
# run_scan -- end to end: writes summary+jsonl, rescan-skip gate, crew-event
# only when new_items > 0, never raises.
# ============================================================================

def test_run_scan_writes_summary_and_jsonl(tmp_path):
    fetch = _fetch_map({"https://ok.example/rss": SAMPLE_RSS})
    summary_path, jsonl_path, crew_path = tmp_path / "summary.json", tmp_path / "feed.jsonl", tmp_path / "crew.jsonl"
    now_utc = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)
    ts_et = "2026-09-14 17:00:00 ET"

    result = sfeed.run_scan(ts_et, now_utc, ["https://ok.example/rss"], fetch_fn=fetch,
                            summary_path=summary_path, jsonl_path=jsonl_path, crew_events_path=crew_path)

    assert result["feeds_ok"] == 1
    assert result["new_items"] == 3
    assert len(result["top"]) == 3
    doc = json.loads(summary_path.read_text(encoding="utf-8"))
    assert doc["ts_et"] == ts_et
    assert len(sb.read_jsonl(jsonl_path)) == 3


def test_run_scan_emits_crew_event_only_when_new_items_found(tmp_path):
    fetch = _fetch_map({"https://ok.example/rss": SAMPLE_RSS})
    summary_path, jsonl_path, crew_path = tmp_path / "summary.json", tmp_path / "feed.jsonl", tmp_path / "crew.jsonl"
    now_utc = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)

    sfeed.run_scan("2026-09-14 17:00:00 ET", now_utc, ["https://ok.example/rss"], fetch_fn=fetch,
                   summary_path=summary_path, jsonl_path=jsonl_path, crew_events_path=crew_path)
    events = ce.read_rows(crew_path)
    assert len(events) == 1
    assert events[0]["who"] == "Scout"
    assert events[0]["kind"] == "scan"
    assert events[0]["to"] == "Pilot"
    assert "3 new" in events[0]["line"]

    # A second fire 26 min later re-fetching the SAME content -> everything dedupes to
    # zero new items -> no second crew-event.
    later = now_utc + timedelta(minutes=26)
    sfeed.run_scan("2026-09-14 17:26:00 ET", later, ["https://ok.example/rss"], fetch_fn=fetch,
                   summary_path=summary_path, jsonl_path=jsonl_path, crew_events_path=crew_path)
    events2 = ce.read_rows(crew_path)
    assert len(events2) == 1, "no new items on the second fire -> no second crew-event"


def test_run_scan_skips_refetch_within_rescan_window(tmp_path):
    calls = {"n": 0}

    def counting_fetch(url):
        calls["n"] += 1
        return SAMPLE_RSS

    summary_path, jsonl_path, crew_path = tmp_path / "summary.json", tmp_path / "feed.jsonl", tmp_path / "crew.jsonl"
    now_utc = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)
    ts_et = "2026-09-14 17:00:00 ET"

    r1 = sfeed.run_scan(ts_et, now_utc, ["https://ok.example/rss"], fetch_fn=counting_fetch,
                        summary_path=summary_path, jsonl_path=jsonl_path, crew_events_path=crew_path)
    assert calls["n"] == 1

    soon = now_utc + timedelta(minutes=10)
    r2 = sfeed.run_scan(ts_et, soon, ["https://ok.example/rss"], fetch_fn=counting_fetch,
                        summary_path=summary_path, jsonl_path=jsonl_path, crew_events_path=crew_path)
    assert calls["n"] == 1, "a fire <25 min after the last real scan must not refetch"
    assert r2 == r1

    later = now_utc + timedelta(minutes=26)
    sfeed.run_scan(ts_et, later, ["https://ok.example/rss"], fetch_fn=counting_fetch,
                   summary_path=summary_path, jsonl_path=jsonl_path, crew_events_path=crew_path)
    assert calls["n"] == 2, "a fire >=25 min after the last real scan must refetch"


def test_run_scan_no_feeds_configured_is_a_clean_noop(tmp_path):
    summary_path = tmp_path / "summary.json"
    result = sfeed.run_scan("t", datetime.now(timezone.utc), [], summary_path=summary_path)
    assert result["new_items"] == 0
    assert not summary_path.exists(), "no feeds configured must never touch disk"


def test_run_scan_never_raises_on_a_totally_broken_fetch_fn(tmp_path):
    def boom(url):
        raise RuntimeError("network is on fire")

    result = sfeed.run_scan("t", datetime.now(timezone.utc), ["https://x"], fetch_fn=boom,
                            summary_path=tmp_path / "s.json", jsonl_path=tmp_path / "j.jsonl",
                            crew_events_path=tmp_path / "crew.jsonl")
    assert result["feeds_failed"] == 1
    assert result["new_items"] == 0
