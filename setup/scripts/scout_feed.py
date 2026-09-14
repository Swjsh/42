"""scout_feed.py -- continuous deterministic feed scan for Scout (GOAL-GAMMA-STATION
2026-09-14 CREW-RIG R1 build).

WHY THIS EXISTS: J's verdict (2026-09-14 16:50 ET), reading the HQ crew panel -- "Scout
is done?? Scout has access to the Internet. Scout should NEVER be done -- Scout is
pretty much infinite, always scouting things." Scout's only producer until now was the
once-daily 05:30 ET deep brief (automation/scout/state/scout_output.json, a Claude +
WebSearch agent fire) -- correct for premarket, but its deliverable's own age climbs to
23+ hours by late afternoon, which is exactly the "done" signal J flagged. This module
is the SECOND, continuous half of Scout: a $0, stdlib-only, deterministic RSS/Atom scan
that fires inside Gamma_Station every ~30 min, 24/7, and keeps a rolling feed of
headlines Scout "is scanning right now" between deep briefs. It never replaces the
05:30 brief (still a real Claude+WebSearch agent fire, still owned by
.claude/agents/scout.md) -- it fills the other ~47 fires/day with real, cheap,
verifiable work.

SECURITY: outbound GET only, to a fixed allowlist read from config.json's
`web_scan_feeds` (this module never decides which URLs are safe -- that is the
operator's config, not code). Feed text is DATA, never instructions -- titles/links/
pubDates are extracted with stdlib xml.etree, never eval'd, rendered, or executed as
markup/script. No credentials, no query params carrying local state, no HTML rendering.

Fail-open throughout: a dead feed, a malformed response, or a write failure degrades
that ONE piece, never raises into station_loop.py's every-fire block (the try/except at
the call site is defense in depth on top of run_scan's own internal guard).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from et_clock import et_offset_hours  # noqa: E402
import station_board  # noqa: E402 -- read_json_or_none / atomic_write_text / read_jsonl (shared, stdlib-only)
import crew_events  # noqa: E402 -- the crew ticker

# ---- Paths this module owns. Prefixed SCOUT_ so every Station test fixture can
# monkeypatch them to tmp_path exactly like SECTORS_PATH/CREW_EVENTS_PATH already are
# (this bit the rig today: a synthetic-clock test wrote real state -- be137985 -- because
# a producer's own paths weren't redirectable). Functions below take these as defaultable
# keyword args rather than reading the module globals directly, so a test can also just
# pass tmp_path straight through without monkeypatching at all. ----
SCOUT_STATE_DIR = REPO / "automation" / "scout" / "state"
SCOUT_FEED_JSONL_PATH = SCOUT_STATE_DIR / "scout-feed.jsonl"
SCOUT_FEED_SUMMARY_PATH = SCOUT_STATE_DIR / "scout-feed-summary.json"

SCOUT_FEED_CAP = 2000
RESCAN_MINUTES = 25          # Gamma_Station fires every ~30 min; skip a refetch if we scanned <25 min ago
FETCH_TIMEOUT_S = 8
FETCH_MAX_BYTES = 1_000_000  # bounded read -- one huge/misbehaving response must never blow the fire budget
USER_AGENT = "GammaStationScout/1.0 (+local research feed reader; no ads, no tracking)"
TOP_N = 5

# Keyword -> tag. Matched against the lowercased title only (titles/links/pubDate is all
# this module ever reads from a feed -- never full article bodies). Deliberately simple
# substring matching, not NLP -- this is a cheap relevance hint for ranking/labeling, not
# a trading signal.
TAG_KEYWORDS: dict = {
    "fed": ("federal reserve", "fomc", "fed ", "rate hike", "rate cut", "powell", "interest rate", "central bank"),
    "cpi": ("cpi", "consumer price index", "inflation", "ppi", "producer price"),
    "jobs": ("payroll", "nonfarm", "jobless", "unemployment", "jobs report"),
    "oil": ("oil", "crude", "brent", "opec", "wti", "energy price"),
    "spy": ("s&p 500", "s&p500", "spy ", " spy", "spx", "stock market", "equities", "wall street", "nasdaq", "dow jones"),
    "vix": ("vix", "volatility index", "implied volatility"),
    "earnings": ("earnings", "quarterly results", "eps beat", "eps miss", "guidance cut", "guidance raise"),
    "geopolitics": ("war", "conflict", "sanction", "military", "missile", "houthi", "strait of", "geopolitic", "invasion"),
}
TAG_DISPLAY = {
    "fed": "Fed", "cpi": "CPI", "jobs": "Jobs", "oil": "Oil", "spy": "SPY",
    "vix": "VIX", "earnings": "Earnings", "geopolitics": "Geopolitics",
}
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _tag_title(title: str) -> list:
    low = (title or "").lower()
    return [tag for tag, needles in TAG_KEYWORDS.items() if any(n in low for n in needles)]


def _dedupe_hash(source: str, title: str) -> str:
    """Dedupe key = (source, title), normalized -- same item re-appearing in the same
    feed across fires (RSS feeds commonly repeat their last N items every poll) must
    never re-count as 'new'."""
    norm = re.sub(r"\s+", " ", (title or "").strip().lower())
    return hashlib.sha256(f"{source}|{norm}".encode("utf-8")).hexdigest()[:16]


def _feed_label(url: str) -> str:
    """Short human label for a feed URL -- host, minus a leading 'www.'/'feeds.'."""
    m = re.match(r"^https?://([^/]+)/?", str(url))
    host = m.group(1) if m else str(url)
    return re.sub(r"^(www\.|feeds\.)", "", host)


def _fetch_bytes(url: str, *, timeout: int = FETCH_TIMEOUT_S) -> Optional[bytes]:
    """One allowlisted GET. None on ANY failure (dead host, timeout, non-2xx, DNS,
    SSL...) -- a single dead feed must never abort the scan. Bounded read
    (FETCH_MAX_BYTES) so one huge or misbehaving response body can never blow this
    fire's time/memory budget. Never sends a query param, header, or body derived from
    fetched content -- this is a one-shot, stateless GET against an operator-chosen URL."""
    try:
        req = urllib.request.Request(str(url), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- allowlisted feeds only, read-only GET
            status = getattr(resp, "status", 200)
            if not (200 <= status < 300):
                return None
            return resp.read(FETCH_MAX_BYTES)
    except Exception:  # noqa: BLE001 -- one dead feed must never abort the scan
        return None


def _parse_feed_items(raw: bytes, source: str) -> list:
    """Parses an RSS 2.0 (or Atom) body into [{title, link, pub_date, source}], in feed
    order. [] on any parse failure -- malformed XML from a feed is DATA, never a reason
    to crash. Titles/links/pubDates only -- no HTML is rendered, no script/content is
    executed; xml.etree only ever reads element text/attributes, never evaluates
    anything it parses."""
    try:
        root = ET.fromstring(raw)  # noqa: S314 -- stdlib parser reads text/attrs only, no entity/DTD execution risk for well-formed RSS/Atom
    except ET.ParseError:
        return []
    items: list = []
    for node in list(root.iter("item")) + list(root.iter(f"{_ATOM_NS}entry")):
        title_el = node.find("title")
        if title_el is None:
            title_el = node.find(f"{_ATOM_NS}title")
        link_el = node.find("link")
        if link_el is None:
            link_el = node.find(f"{_ATOM_NS}link")
        pub_el = node.find("pubDate")
        if pub_el is None:
            pub_el = node.find(f"{_ATOM_NS}updated")
        title = re.sub(r"\s+", " ", (title_el.text or "")).strip() if title_el is not None else ""
        link = ""
        if link_el is not None:
            # RSS <link>text</link> vs Atom <link href="..."/> -- try both shapes.
            link = (link_el.text or "").strip() or (link_el.get("href") or "").strip()
        pub_date = (pub_el.text or "").strip() if pub_el is not None else ""
        if title:
            items.append({"title": title, "link": link, "pub_date": pub_date, "source": source})
    return items


def scan_feeds(feeds: list, *, fetch_fn: Optional[Callable[[str], Optional[bytes]]] = None) -> dict:
    """Fetches every feed in `feeds` (already the operator's chosen allowlist -- this
    function does not itself decide which URLs are safe) and parses items. Returns
    {"feeds_ok": int, "feeds_failed": int, "items": [...]} -- items are NOT yet deduped
    or capped (see run_scan). Each feed is independent: one timeout/403/malformed body
    only costs that one feed's items, never the rest of the scan (matches
    station_facts.gather_web_scan's existing per-feed fail-open contract)."""
    fetch_fn = fetch_fn or _fetch_bytes
    feeds_ok = 0
    feeds_failed = 0
    items: list = []
    for url in feeds or []:
        label = _feed_label(url)
        try:
            raw = fetch_fn(str(url))
        except Exception:  # noqa: BLE001 -- an injected fetch_fn in a test must not be able to break the scan either
            raw = None
        if raw is None:
            feeds_failed += 1
            continue
        parsed = _parse_feed_items(raw, label)
        if not parsed:
            feeds_failed += 1
            continue
        feeds_ok += 1
        items.extend(parsed)
    return {"feeds_ok": feeds_ok, "feeds_failed": feeds_failed, "items": items}


def dedupe_new_items(items: list, seen_hashes: set, *, now_et: str) -> tuple:
    """Returns (new_rows, updated_seen_hashes). new_rows are ledger-shaped:
    {hash, ts_et, source, title, link, pub_date, tags}, in the order `items` arrived.
    An item whose hash is already in `seen_hashes` (this fire's OR a prior fire's) is
    silently dropped -- feeds routinely re-serve their last N items every poll."""
    new_rows = []
    seen = set(seen_hashes)
    for it in items:
        h = _dedupe_hash(it["source"], it["title"])
        if h in seen:
            continue
        seen.add(h)
        new_rows.append({
            "hash": h, "ts_et": now_et, "source": it["source"], "title": it["title"][:300],
            "link": (it.get("link") or "")[:500], "pub_date": it.get("pub_date", ""),
            "tags": _tag_title(it["title"]),
        })
    return new_rows, seen


def _append_capped_jsonl(path: Path, new_rows: list, cap: int) -> list:
    """Appends new_rows to the existing ledger, then caps at `cap` (oldest dropped
    first). Returns the full post-cap ledger (callers use it to compute 'top' over
    everything currently on file, not just this fire's new items). A no-op read+no-write
    when new_rows is empty (the common case: most fires find nothing new)."""
    existing = station_board.read_jsonl(path)
    if not new_rows:
        return existing
    combined = existing + new_rows
    if len(combined) > cap:
        combined = combined[-cap:]
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in combined)
    station_board.atomic_write_text(path, text)
    return combined


def _top_items(rows: list, n: int = TOP_N) -> list:
    """5 newest by relevance = tag count first, recency second (list index -- rows are
    appended in chronological/scan order, never reordered, so a larger index is always
    at-least-as-recent)."""
    indexed = list(enumerate(rows))
    indexed.sort(key=lambda pair: (-len(pair[1].get("tags") or []), -pair[0]))
    return [r for _, r in indexed[:n]]


def _format_crew_line(new_rows: list, *, max_len: int = 280) -> str:
    top = _top_items(new_rows, 3)
    parts = []
    for r in top:
        tags = r.get("tags") or []
        label = TAG_DISPLAY.get(tags[0], "news") if tags else "news"
        parts.append(f"{label}: {r['title'][:70]}")
    line = f"Scout: {len(new_rows)} new — " + " · ".join(parts)
    return line[:max_len]


def _last_scan_utc(summary_path: Path) -> Optional[datetime]:
    doc = station_board.read_json_or_none(summary_path)
    if not isinstance(doc, dict):
        return None
    ts = doc.get("ts_et")
    if not ts or not isinstance(ts, str):
        return None
    try:
        naive_et = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S ET")
    except ValueError:
        return None
    offset = et_offset_hours(naive_et.replace(tzinfo=timezone.utc))
    return (naive_et - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def run_scan(ts_et: str, now_utc: datetime, feeds: list, *,
            summary_path: Optional[Path] = None, jsonl_path: Optional[Path] = None,
            crew_events_path: Optional[Path] = None,
            fetch_fn: Optional[Callable[[str], Optional[bytes]]] = None) -> dict:
    """The Station's every-fire entrypoint (station_loop.py calls this in the every-fire
    block, yielded or not -- a feed scan is pure I/O + parsing, no LLM, no trading path).

    Returns the summary dict that was written (or the prior one, unchanged, when this
    fire skipped a refetch because the last scan is <RESCAN_MINUTES old -- station_loop
    fires every ~30 min, so this keeps a manual/extra fire from re-hitting every feed).

    NEVER RAISES: every internal step is wrapped so a dead feed, a malformed response,
    or a write failure degrades gracefully to an {"error": ...} summary rather than
    propagating -- the caller's own try/except in station_loop.py is defense in depth,
    not the only guard.
    """
    summary_path = summary_path or SCOUT_FEED_SUMMARY_PATH
    jsonl_path = jsonl_path or SCOUT_FEED_JSONL_PATH
    try:
        if not feeds:
            return {"ts_et": ts_et, "feeds_ok": 0, "feeds_failed": 0, "new_items": 0, "top": [],
                    "skipped": "no feeds configured (config.json web_scan_feeds is empty)"}

        last_scan = _last_scan_utc(summary_path)
        if last_scan is not None and (now_utc - last_scan) < timedelta(minutes=RESCAN_MINUTES):
            prior = station_board.read_json_or_none(summary_path)
            return prior if isinstance(prior, dict) else {"ts_et": ts_et, "skipped": "rescanned too recently"}

        scan = scan_feeds(feeds, fetch_fn=fetch_fn)
        existing_rows = station_board.read_jsonl(jsonl_path)
        seen = {r.get("hash") for r in existing_rows if r.get("hash")}
        new_rows, _ = dedupe_new_items(scan["items"], seen, now_et=ts_et)
        all_rows = _append_capped_jsonl(jsonl_path, new_rows, SCOUT_FEED_CAP)

        top = _top_items(all_rows, TOP_N)
        summary = {
            "ts_et": ts_et,
            "feeds_ok": scan["feeds_ok"],
            "feeds_failed": scan["feeds_failed"],
            "new_items": len(new_rows),
            "top": [{"ts": r["ts_et"], "source": r["source"], "title": r["title"],
                     "tags": r["tags"], "link": r["link"]} for r in top],
        }
        station_board.atomic_write_text(summary_path, json.dumps(summary, indent=2, ensure_ascii=False))

        if new_rows:
            try:
                crew_events.append(
                    {"ts_et": ts_et, "who": "Scout", "kind": "scan", "to": "Pilot",
                     "line": _format_crew_line(new_rows), "ref": str(summary_path)},
                    path=crew_events_path or crew_events.DEFAULT_PATH,
                )
            except Exception:  # noqa: BLE001 -- a ticker glitch must never break the scan itself
                pass
        return summary
    except Exception as exc:  # noqa: BLE001 -- the Station fire must never die on a feed-scan bug
        return {"ts_et": ts_et, "error": f"{type(exc).__name__}: {exc}"[:300]}
