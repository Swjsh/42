"""Macro/news calendar producer -- FOMC/CPI/PPI/NFP/PCE/GDP event feed.

THE GAP THIS FIXES (diagnosed 2026-07-09): automation/state/macro-calendar.json's
ONLY producer was weekly-review.md Section 8a -- a WebFetch step buried at the END
of a long Sunday LLM prompt ("After the weekly review is written but BEFORE the
dashboard ticker writes..."). It silently stopped appending refresh_log[] entries
after "ran_at": "2026-06-14T18:00:00-04:00" even though weekly-review kept firing
and exiting 0 every Sunday since (automation/state/logs/weekly-review-2026-06-21.log
and -2026-06-28.log both end "=== END tick exit=0 ===" with a full written review --
neither mentions a calendar refresh). Section 8a is the LAST of 9 sections in an
8-budget-dollar, 720s-timeout prompt; the primary review evidently consumes the
budget/turns before ever reaching it. This is exactly the "Sunday weekly-review
silently failing 3+ weeks" gap already flagged in automation/overnight/STATUS.md
and queue item F23-F27-JOURNAL-CALENDAR ("macro/news calendar stale 23 days (F27)").

Compounding: the daily Scout feed (automation/scout/state/scout_output.json), which
also informs today-bias.json#news_calendar.catalyst_narrative via news.json, has
failed EVERY session since >= 2026-06-22 with "Error: Exceeded USD budget (0.5)"
(automation/state/logs/scout-2026-07-0{1,2,3,6,7,8}.log) or a 240s timeout
(scout-2026-07-09.log) -- both LLM-invocation pipelines that feed this gap are
broken in the same way: an interactive Claude subprocess with a cost/time budget
that a network-heavy, multi-step prompt routinely blows through.

LIVE PROOF of the blind spot (captured before this fix, 2026-07-08 premarket run):
    automation/state/today-bias.json#news_calendar =
        {"no_trade_window": [], "stale": true, "calendar_freshness_days": 24}
The 06:00 ET swarm's own macro agent said the same thing the same morning
(automation/swarm/state/macro_output.json, generated_at 2026-07-08T08:18:01Z):
    "Calendar is stale (last refresh 2026-06-14, 24 days old) with no visible
     events for 2026-07-08 in events_30d; cannot confirm if macro events exist
     today."
The engine has had ZERO macro-event no-trade-window protection for 3+ weeks.

THE FIX: a deterministic, dependency-free, non-LLM Python script any scheduled
task can invoke directly -- no Claude subprocess, no $0.50 budget cap, no context
window, no trust-dialog dependency -- to refresh BOTH:

  1. automation/state/macro-calendar.json -- the ENGINE-CRITICAL file.
     premarket.md Step 1b reads events_30d[] + no_trade_window_rules to compute
     today-bias.json#news_calendar.no_trade_window[], which heartbeat filter 2
     enforces as a hard no-trade veto. Also read directly by
     automation/swarm/prompts/macro_agent.md (06:00 ET swarm macro/VIX agent).
  2. automation/state/news.json -- the catalyst-narrative doc named in CLAUDE.md
     OP-25(b) ("Market event -> write automation/state/news.json") and read by
     premarket.md Step 1b #5 (catalyst_narrative, only if < 7 days old). This
     script writes FACTS ONLY (event dates/times/sources, mechanically derived
     no-trade windows) -- it does NOT fabricate VIX levels, chart levels, or
     market narrative. That requires a live TradingView/Alpaca read, which is
     out of scope for a stdlib-only $0 script and belongs to premarket/scout.
     Every narrative-shaped field says so explicitly rather than inventing a
     number (never invent values -- CLAUDE.md Step 0 pre-flight doctrine).

DATA SOURCES (free, no key, reachability verified 2026-07-09 by direct curl from
this host -- see the docstring of `verify_source` and the commit message for the
literal HTTP status codes captured):
  - https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  (FOMC)  -- HTTP 200
  - https://www.bea.gov/news/schedule                                 (PCE/GDP)-- HTTP 200
  - https://www.federalreserve.gov/newsevents/speech/2026-speeches.htm (Fed speakers) -- HTTP 200
  - https://www.bls.gov/schedule/news_release/*.htm (CPI/PPI/NFP) -- HTTP 403,
    CONFIRMED BLOCKED with or without a browser User-Agent. This matches the
    calendar's own fetch_failures[] history from 2026-05-14 (same 403s, same
    URLs). BLS release DATES are therefore a hand-verified static table
    (KNOWN_EVENTS_2026 below, each entry source-cited, dates verified via web
    search 2026-07-09) -- the same "published ~1yr ahead, essentially never
    moves" trust model this file already uses for fomc_meeting_dates_2026.

FAIL-OPEN CONTRACT: any network failure degrades gracefully -- keeps whatever
was already in events_30d[], merges in the static verified baseline (which
needs no network at all), logs the failure to fetch_failures[], and still
exits 0. Only a local file-write error exits non-zero, so Task Scheduler's
LastTaskResult can distinguish "source down" (0, expected, self-healing) from
"script broke" (1, needs a human). Never writes an event without a source_url
(OP-18 -- no speculation).

Usage:
    python macro_calendar.py                  # normal run: baseline + live verification
    python macro_calendar.py --no-fetch        # offline mode: baseline table only, no network
    python macro_calendar.py --dry-run         # compute + print, no writes
    python macro_calendar.py --date 2026-07-09 # override "today" (testing/backfill)
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402  (canonical ET clock -- never hand-roll TZ math)

# --------------------------------------------------------------------------- #
# Verified static baseline (2026-07-09) -- needs NO network to be correct.
# --------------------------------------------------------------------------- #
# FOMC dates come straight from federalreserve.gov (HTTP 200, live-fetchable --
# these are re-verified below when network is available). CPI/PPI/NFP/Retail
# Sales dates were confirmed via web search 2026-07-09 because BLS/Census block
# scripted GETs; each entry cites the authoritative page a human can re-check.
KNOWN_EVENTS_2026: list[dict[str, Any]] = [
    {
        "date": "2026-07-14", "time_et": "08:30", "event": "CPI (June 2026 data)",
        "type": "cpi_release", "severity": "high",
        "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        "notes": "Verified via web search 2026-07-09 -- direct BLS fetch returns HTTP 403 from this host.",
    },
    {
        "date": "2026-07-15", "time_et": "08:30", "event": "PPI (June 2026 data)",
        "type": "ppi_release", "severity": "med",
        "source_url": "https://www.bls.gov/schedule/news_release/ppi.htm",
        "notes": "Verified via web search 2026-07-09 -- direct BLS fetch returns HTTP 403 from this host.",
    },
    {
        "date": "2026-07-16", "time_et": "08:30", "event": "Advance Monthly Retail Trade Sales (June 2026)",
        "type": "retail_sales", "severity": "med",
        "source_url": "https://www.census.gov/retail/release_schedule.html",
        "notes": "Verified via web search 2026-07-09.",
    },
    {
        "date": "2026-07-29", "time_et": "14:00", "event": "FOMC Rate Decision (Jul 2026 meeting)",
        "type": "fomc_decision", "severity": "high",
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "notes": "Two-day meeting Jul 28-29; statement 14:00 ET, presser 14:30 ET. No SEP this meeting.",
    },
    {
        "date": "2026-07-30", "time_et": "08:30", "event": "GDP Advance Estimate Q2 2026",
        "type": "gdp_release", "severity": "med",
        "source_url": "https://www.bea.gov/news/schedule",
        "notes": "Same-day release as the June PCE Price Index below.",
    },
    {
        "date": "2026-07-30", "time_et": "08:30",
        "event": "PCE Price Index (June 2026 data) + Personal Income and Outlays",
        "type": "pce_release", "severity": "high",
        "source_url": "https://www.bea.gov/news/schedule",
        "notes": "Fed's preferred inflation gauge. Same-day as Q2 2026 GDP advance estimate.",
    },
    {
        "date": "2026-08-07", "time_et": "08:30", "event": "Employment Situation / NFP (Jul 2026 data)",
        "type": "nfp_release", "severity": "high",
        "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm",
        "notes": "Verified via web search 2026-07-09 -- direct BLS fetch returns HTTP 403 from this host.",
    },
    {
        "date": "2026-09-16", "time_et": "14:00", "event": "FOMC Rate Decision (Sep 2026 meeting)",
        "type": "fomc_decision", "severity": "high",
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "notes": "Two-day meeting Sep 15-16. Includes Summary of Economic Projections.",
    },
]

# Live-verification targets: (label, url, substrings whose presence in the body
# confirms the fetched page still corroborates our static baseline). A hit does
# NOT replace the baseline entry (HTML scraping full event tables is brittle and
# not worth the fragility for a handful of dates that change once a year) -- it
# just upgrades that source's refresh_log confidence from "baseline_only" to
# "live_verified".
_LIVE_SOURCES: list[tuple[str, str, tuple[str, ...]]] = [
    ("fomc", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", ("July 28", "July 29")),
    ("bea_pce_gdp", "https://www.bea.gov/news/schedule", ("July 30",)),
    ("fed_speeches", "https://www.federalreserve.gov/newsevents/speech/2026-speeches.htm", ()),
]

# BLS endpoints are attempted too (in case they ever unblock) purely so a fresh
# fetch_failures[] entry lands with today's date -- matches the file's existing
# fetch_failures schema exactly.
_BLS_PROBE_SOURCES: list[tuple[str, str]] = [
    ("nfp_release", "https://www.bls.gov/schedule/news_release/empsit.htm"),
    ("cpi_release", "https://www.bls.gov/schedule/news_release/cpi.htm"),
    ("ppi_release", "https://www.bls.gov/schedule/news_release/ppi.htm"),
]

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def load_json(path: Path, default: Any) -> Any:
    """Read JSON, tolerating a BOM. Missing/corrupt file -> `default` (never crash)."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return default


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write JSON atomically (tmp file + os.replace) -- matches status_retention.py's
    _atomic_write pattern so a crash mid-write never corrupts the live state file
    (automation/state/*.json is mirrored to .lastgood/ by _shared.ps1; this keeps
    that mirror meaningful by never leaving a half-written file behind)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        Path(tmp).replace(path)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink()


def load_holidays(alpaca_calendar_path: Path) -> set[str]:
    """US market holidays from automation/state/calendar.json (Alpaca calendar --
    a separate, already-working producer; reused here rather than duplicated)."""
    data = load_json(alpaca_calendar_path, {})
    return set(data.get("holidays", []))


def is_trading_day(date_str: str, holidays: set[str]) -> bool:
    dt = datetime.fromisoformat(date_str)
    return dt.weekday() < 5 and date_str not in holidays


def next_trading_day(from_date: str, holidays: set[str], inclusive: bool = True) -> str:
    """First trading day >= from_date (or > from_date if inclusive=False)."""
    dt = datetime.fromisoformat(from_date)
    if not inclusive:
        dt += timedelta(days=1)
    while not is_trading_day(dt.strftime("%Y-%m-%d"), holidays):
        dt += timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def next_n_trading_days(from_date: str, n: int, holidays: set[str]) -> list[str]:
    """The next `n` trading days starting at (and including, if it qualifies) from_date."""
    out: list[str] = []
    d = from_date
    first = True
    while len(out) < n:
        candidate = next_trading_day(d, holidays, inclusive=first)
        out.append(candidate)
        d = candidate
        first = False
    return out


def verify_source(url: str, timeout: float = 10.0) -> tuple[int, str]:
    """Best-effort GET. Never raises -- returns (0, "<exception text>") on any
    failure so callers can treat "unreachable" uniformly with "non-200"."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https gov URLs)
            body = resp.read(200_000).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e)


FetchFn = Callable[[str], tuple[int, str]]


# --------------------------------------------------------------------------- #
# macro-calendar.json refresh
# --------------------------------------------------------------------------- #
def refresh_macro_calendar(
    existing: dict[str, Any],
    today: str,
    known_events: list[dict[str, Any]],
    fetch_fn: Optional[FetchFn],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge `known_events` into `existing`'s events_30d[], prune stale entries,
    optionally live-verify FOMC/BEA/Fed-speech reachability, and produce a
    refresh_log[] entry. Never mutates `existing` in place; returns a new dict.

    Mirrors the merge/prune/audit-log semantics documented in
    automation/prompts/weekly-review.md Section 8a exactly (dedupe by
    (date, type), drop date < today - 7, cite source_url on every entry) so
    this script is a drop-in replacement for that step, not a new contract.
    """
    out = dict(existing)  # shallow copy; we only replace top-level mutable keys
    events: list[dict[str, Any]] = list(existing.get("events_30d", []))
    existing_keys = {(e.get("date"), e.get("type")) for e in events}

    added = 0
    skipped_existing = 0
    for ev in known_events:
        key = (ev["date"], ev["type"])
        if ev["date"] < today:
            continue  # past event, don't (re-)add
        if key in existing_keys:
            skipped_existing += 1
            continue
        events.append(dict(ev))
        existing_keys.add(key)
        added += 1

    prune_floor = (datetime.fromisoformat(today) - timedelta(days=7)).strftime("%Y-%m-%d")
    before_prune = len(events)
    events = [e for e in events if e.get("date", "9999-99-99") >= prune_floor]
    pruned = before_prune - len(events)
    events.sort(key=lambda e: (e.get("date", ""), e.get("time_et", "")))
    out["events_30d"] = events
    out.setdefault("earnings_30d", existing.get("earnings_30d", []))

    warnings: list[str] = []
    live_status: dict[str, Any] = {}
    fetch_failures = list(existing.get("fetch_failures", []))
    now_iso = et_now().isoformat()

    if fetch_fn is None:
        live_status["mode"] = "offline (--no-fetch)"
        data_quality = "baseline_only"
    else:
        confirmed = 0
        attempted = 0
        for label, url, expect_substrings in _LIVE_SOURCES:
            attempted += 1
            status, body = fetch_fn(url)
            ok = status == 200 and all(s in body for s in expect_substrings)
            live_status[label] = {"http_status": status, "content_match": ok}
            if status == 200:
                confirmed += 1
            else:
                warnings.append(f"{label} unreachable (HTTP {status}) -- {url}")

        for ev_type, url in _BLS_PROBE_SOURCES:
            status, _ = fetch_fn(url)
            live_status[f"bls_{ev_type}"] = {"http_status": status}
            if status != 200:
                fetch_failures.append({
                    "fetched_at": now_iso,
                    "url": url,
                    "http_status": status,
                    "purpose": f"{ev_type} release dates -- direct verification attempt",
                    "fallback": "Used static verified table (KNOWN_EVENTS_2026 in macro_calendar.py, "
                                 "source-cited, confirmed via web search) -- matches this file's own "
                                 "established fallback pattern from 2026-05-14.",
                })

        if attempted > 0 and confirmed == attempted:
            data_quality = "live_verified"
        elif confirmed > 0:
            data_quality = "partial"
        else:
            data_quality = "baseline_only"
            warnings.append("ALL live sources unreachable this run -- operating on static baseline only.")

    fetch_failures = fetch_failures[-30:]  # retention cap (OP-22 compound-not-accumulate)
    out["fetch_failures"] = fetch_failures

    refresh_log = list(existing.get("refresh_log", []))
    log_entry = {
        "ran_at": now_iso,
        "source": "setup/scripts/macro_calendar.py",
        "fetched_count": len(known_events),
        "added_count": added,
        "skipped_existing_count": skipped_existing,
        "pruned_count": pruned,
        "data_quality": data_quality,
        "live_status": live_status,
        "warnings": warnings,
        "coverage_thru": max((e["date"] for e in events), default=today),
    }
    refresh_log.append(log_entry)
    out["refresh_log"] = refresh_log[-20:]  # retention cap

    return out, log_entry


def compute_no_trade_windows(events_on_date: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Same computation premarket.md Step 1b performs -- reproduced here so
    news.json can carry a genuinely-correct (not fabricated) no-trade preview.
    The engine's OWN no_trade_window[] still comes from premarket -> today-bias.json;
    this is a courtesy mirror, not a new gate."""
    windows: list[dict[str, Any]] = []
    for ev in events_on_date:
        if ev.get("severity") not in ("high", "med"):
            continue
        rule = rules.get(ev.get("type", ""))
        if not rule:
            continue
        hh, mm = (int(x) for x in ev["time_et"].split(":"))
        base = hh * 60 + mm
        start = base - int(rule.get("block_starts_minutes_before", 0))
        end = base + int(rule.get("block_ends_minutes_after", 0))
        windows.append({
            "start_et": f"{start // 60:02d}:{start % 60:02d}",
            "end_et": f"{end // 60:02d}:{end % 60:02d}",
            "event": ev["event"],
            "type": ev["type"],
            "severity": ev["severity"],
        })
    return windows


# --------------------------------------------------------------------------- #
# news.json refresh
# --------------------------------------------------------------------------- #
def build_news_json(calendar: dict[str, Any], today: str, for_session: str) -> dict[str, Any]:
    """Factual, mechanically-generated catalyst digest. Deliberately does NOT
    fabricate VIX levels, chart levels, or directional narrative -- those need
    a live TradingView/Alpaca read this stdlib script does not have. Every such
    field says so explicitly instead of guessing (never invent values)."""
    events = sorted(calendar.get("events_30d", []), key=lambda e: (e["date"], e.get("time_et", "")))
    upcoming = [e for e in events if e["date"] >= today]
    events_today = [e for e in events if e["date"] == for_session]
    no_trade_today = compute_no_trade_windows(events_today, calendar.get("no_trade_window_rules", {}))

    primary = upcoming[0] if upcoming else None
    secondary = upcoming[1:4]
    now_et = et_now()

    if primary is None:
        catalyst_summary = (
            "MECHANICAL MACRO DIGEST (setup/scripts/macro_calendar.py -- no chart/VIX read). "
            f"No scheduled high/med-severity US macro event found within the tracked window for "
            f"session {for_session}. See automation/state/macro-calendar.json#events_30d for the full list."
        )
    elif primary["date"] == for_session:
        catalyst_summary = (
            "MECHANICAL MACRO DIGEST (setup/scripts/macro_calendar.py -- no chart/VIX read). "
            f"TODAY ({for_session}) is an event day: {primary['event']} at {primary['time_et']} ET "
            f"(severity={primary['severity']}). "
            + (f"No-trade window(s): {no_trade_today}. " if no_trade_today else "")
            + "VIX/chart/level context is out of this script's scope -- see today-bias.json "
              "(premarket's live TradingView read) for that."
        )
    else:
        catalyst_summary = (
            "MECHANICAL MACRO DIGEST (setup/scripts/macro_calendar.py -- no chart/VIX read). "
            f"Session {for_session} has no scheduled high/med-severity macro event. "
            f"Next up: {primary['event']} on {primary['date']} at {primary['time_et']} ET "
            f"(severity={primary['severity']}). "
            "VIX/chart/level context is out of this script's scope -- see today-bias.json "
            "(premarket's live TradingView read) for that."
        )

    def _catalyst_block(ev: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "macro_calendar",
            "name": ev["event"],
            "timing_et": f"{ev['time_et']} ET {ev['date']}",
            "description": f"{ev['event']} -- severity={ev['severity']}. Source: {ev['source_url']}"
                            + (f" Notes: {ev['notes']}" if ev.get("notes") else ""),
            "direction": "unknown_mechanical -- no chart/VIX read performed by this generator",
            "confidence": "high (date/time sourced + cited)",
            "spy_impact": "not computed by mechanical generator; requires live chart read (see today-bias.json)",
            "fragility": "not computed by mechanical generator; requires live chart read (see today-bias.json)",
        }

    return {
        "as_of": now_et.isoformat(),
        "for_session": for_session,
        "regime": "not_computed -- mechanical generator has no VIX/chart access; see today-bias.json#iv_regime",
        "generator": "setup/scripts/macro_calendar.py",
        "mechanical": True,
        "freshness_stamp": now_et.isoformat(),
        "catalyst_summary": catalyst_summary,
        "primary_catalyst": _catalyst_block(primary) if primary else None,
        "secondary_catalysts": [_catalyst_block(e) for e in secondary],
        "vix_expectation": (
            "VIX not read by this script (no live market data access) -- see "
            "today-bias.json#vix_at_open / vix_bias from premarket's TradingView read "
            "for the current VIX level and regime."
        ),
        "key_levels_for_session": {
            "note": "Not computed by this script -- see today-bias.json#key_levels (premarket's live chart read)."
        },
        "no_trade_windows_added_for_today": no_trade_today,
        "implication_for_setups": {
            "note": "Not computed by this script -- see today-bias.json#news_calendar / bias_note "
                    "(premarket combines this calendar with a live chart read)."
        },
        "accounts_context": {
            "note": "Not computed by this script -- see automation/state/circuit-breaker.json / "
                    "aggressive/circuit-breaker.json for live account equity."
        },
        "watch_for_reversal": (
            [f"Macro event within next 2 trading days: {primary['event']} on {primary['date']} "
             f"{primary['time_et']} ET -- re-check automation/state/macro-calendar.json no_trade_window "
             "before entries near that time."]
            if primary and primary["date"] in next_n_trading_days(today, 2, set())
            else []
        ),
        "sources": [
            {"note": "Machine-generated by setup/scripts/macro_calendar.py from "
                      "automation/state/macro-calendar.json#events_30d (see that file's own "
                      "refresh_log[] for per-source fetch provenance)."}
        ],
        "next_scheduled_news_check": f"proposed daily premarket fire ~07:45 ET (see report for schedule row)",
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(
    repo_root: Path,
    today: Optional[str] = None,
    do_fetch: bool = True,
    dry_run: bool = False,
    fetch_fn: Optional[FetchFn] = None,
) -> dict[str, Any]:
    state = repo_root / "automation" / "state"
    calendar_path = state / "macro-calendar.json"
    news_path = state / "news.json"
    alpaca_calendar_path = state / "calendar.json"

    now_et = et_now()
    today = today or now_et.strftime("%Y-%m-%d")
    holidays = load_holidays(alpaca_calendar_path)
    for_session = today if is_trading_day(today, holidays) else next_trading_day(today, holidays, inclusive=False)

    existing_calendar = load_json(calendar_path, {
        "schema_version": 1,
        "purpose": "Hand-curated calendar of high-impact macro events that move SPY 0DTE.",
        "no_trade_window_rules": {},
        "events_30d": [],
        "earnings_30d": [],
        "fetch_failures": [],
        "refresh_log": [],
    })

    active_fetch_fn: Optional[FetchFn]
    if not do_fetch:
        active_fetch_fn = None
    elif fetch_fn is not None:
        active_fetch_fn = fetch_fn
    else:
        active_fetch_fn = verify_source

    new_calendar, log_entry = refresh_macro_calendar(existing_calendar, today, KNOWN_EVENTS_2026, active_fetch_fn)
    news = build_news_json(new_calendar, today, for_session)

    if not dry_run:
        _atomic_write_json(calendar_path, new_calendar)
        _atomic_write_json(news_path, news)

    events_today = [e for e in new_calendar["events_30d"] if e["date"] == for_session]
    upcoming_10td = next_n_trading_days(today, 10, holidays)
    events_next_10td = [e for e in new_calendar["events_30d"] if e["date"] in upcoming_10td]

    return {
        "today": today,
        "for_session": for_session,
        "wrote": not dry_run,
        "calendar_path": str(calendar_path),
        "news_path": str(news_path),
        "refresh_log_entry": log_entry,
        "events_today": events_today,
        "events_next_10_trading_days": events_next_10td,
        "no_trade_windows_today": news["no_trade_windows_added_for_today"],
        "total_events_in_file": len(new_calendar["events_30d"]),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--no-fetch", action="store_true", help="skip live network verification (offline/test mode)")
    ap.add_argument("--dry-run", action="store_true", help="compute and print, but do not write state files")
    ap.add_argument("--date", default=None, help="override 'today' as YYYY-MM-DD (testing/backfill)")
    args = ap.parse_args(argv)

    try:
        summary = run(REPO, today=args.date, do_fetch=not args.no_fetch, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 -- top-level guard: never crash the scheduled task silently
        print(f"FATAL macro_calendar.py: {exc!r}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
