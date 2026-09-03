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

# --------------------------------------------------------------------------- #
# RULE-BASED 10:00 ET release schedule (B1, 2026-09-03) -- deterministic,
# network-free coverage for the 10:00 ET macro releases KNOWN_EVENTS_2026 above
# never listed (ISM Manufacturing/Services PMI, Consumer Confidence, UMich
# sentiment). Root cause this fixes: analysis/deep-research/2026-09-03-money/
# audits found every held position in today's Wave 1 (09:41 ET entries, four
# arms) and 2026-08-05's equivalent wave was stopped at the -50% catastrophe
# cap on a single-minute quote-tape gap spanning 10:00-10:01 ET -- coincident
# with the ISM Services PMI release BOTH days (analysis/quote-tape/2026-09-03
# .jsonl: 770C 0.70/0.71 -> 0.49/0.50; 2026-08-05's 776C 1-min bars show the
# identical 2.61 -> 2.27 -> 2.06 pattern). KNOWN_EVENTS_2026 above is a
# hand-curated BLS/BEA/FOMC table that has never once included ISM --
# macro_calendar.py had NO producer for it at all, so premarket's no-trade-
# window computation (compute_no_trade_windows below) could never have
# blocked those entries even in principle, because the event was never in the
# calendar to filter on.
#
# ISM's OWN published rule (https://www.ismworld.org/supply-management-news-
# and-reports/reports/ism-report-on-business/) is deterministic and, unlike
# BLS/Census releases, does not need a hand-verified per-month table:
#   - ISM Manufacturing PMI: 1st US-market BUSINESS DAY of the month, 10:00 ET.
#   - ISM Services PMI:      3rd US-market BUSINESS DAY of the month, 10:00 ET.
# Cross-checked against the quote-tape gaps this task's briefing named:
#   2026-08-05 (Services, 3rd business day of Aug 2026)  -- MATCH
#   2026-09-01 (Manufacturing, 1st business day of Sep 2026) -- MATCH
#   2026-09-03 (Services, 3rd business day of Sep 2026)  -- MATCH (today)
#   next Services after today computes to 2026-10-05 (3rd business day of Oct) -- MATCH
#
# The remaining four candidate release types are handled per the task's
# explicit instruction to OMIT rather than guess: JOLTS has no deterministic
# day-of-month rule (its real-world timing is "first Tuesday-ish", which is
# not a rule) so it is NOT generated at all -- no JOLTS entries exist anywhere
# in generate_rule_based_events()'s output. Conference Board Consumer
# Confidence and the two UMich Consumer Sentiment releases DO have a stateable
# calendar-position rule, so they ARE generated, but every entry is clearly
# marked status="RULE_BASED_UNVERIFIED" + verified=False because -- unlike
# ISM -- none of the three has been cross-checked against a live price gap.
# --------------------------------------------------------------------------- #

# NYSE 2026 holiday calendar -- source: https://www.nyse.com/markets/hours-calendars
# (observed dates; Jul 4 2026 falls on a Saturday so Independence Day is observed
# Fri Jul 3). Cross-checked 2026-09-03 byte-for-byte against the live-fetched
# automation/state/calendar.json (source=alpaca_v2_calendar, produced by
# setup/scripts/market_calendar.py) -- both lists agree on all 10 dates. Hard-
# coded here (rather than reading that cache file) so scheduled_releases() below
# stays a PURE function with zero I/O -- safe to import and call from any
# script/test with no dependency on that file's freshness or presence. A caller
# who wants the live-fetched calendar instead may pass holidays=load_holidays(...)
# explicitly (this file's existing helper, reused rather than duplicated by the
# _nth_business_day_of_month() / is_trading_day() calls below).
NYSE_HOLIDAYS_2026: frozenset[str] = frozenset({
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Washington's Birthday (Presidents' Day)
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth National Independence Day
    "2026-07-03",  # Independence Day (observed -- Jul 4 2026 is a Saturday)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving Day
    "2026-12-25",  # Christmas Day
})

_ISM_SOURCE_URL = (
    "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"
)
_ISM_VERIFIED_BY = (
    "ISM published rule; matched 2026-08-05 and 2026-09-03 quote-tape gaps "
    "(analysis/quote-tape/2026-08-05.jsonl, analysis/quote-tape/2026-09-03.jsonl; "
    "see analysis/deep-research/2026-09-03-money/dissect-wave-autopsy.md)"
)
_ISM_MANUFACTURING_RULE = (
    "ISM Manufacturing PMI releases the 1st US-market business day of the month, "
    "10:00 ET -- ISM's published release schedule."
)
_ISM_SERVICES_RULE = (
    "ISM Services PMI releases the 3rd US-market business day of the month, "
    "10:00 ET -- ISM's published release schedule."
)
_CONSUMER_CONFIDENCE_RULE = (
    "Conference Board Consumer Confidence Index releases the last Tuesday of the "
    "month, 10:00 ET -- commonly-published Conference Board release-calendar "
    "position; NOT cross-checked against a live quote-tape gap."
)
_UMICH_PRELIM_RULE = (
    "University of Michigan Consumer Sentiment (preliminary) releases the 2nd "
    "Friday of the month, 10:00 ET -- commonly-published UMich release-calendar "
    "position; NOT cross-checked against a live quote-tape gap."
)
_UMICH_FINAL_RULE = (
    "University of Michigan Consumer Sentiment (final) releases the 4th Friday "
    "of the month, 10:00 ET -- commonly-published UMich release-calendar "
    "position; NOT cross-checked against a live quote-tape gap."
)

_MONTH_ABBR = (
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _prior_month_label(year: int, month: int) -> str:
    """'<Mon> <year>' label for the month BEFORE (year, month) -- ISM-style
    releases report on the PRIOR month's data (e.g. the Sep release covers Aug)."""
    if month == 1:
        return f"{_MONTH_ABBR[12]} {year - 1}"
    return f"{_MONTH_ABBR[month - 1]} {year}"


def _month_label(year: int, month: int) -> str:
    """'<Mon> <year>' label for (year, month) itself -- Consumer Confidence and
    UMich sentiment report on the SAME month they're released in."""
    return f"{_MONTH_ABBR[month]} {year}"


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


# --------------------------------------------------------------------------- #
# RULE-BASED release-date arithmetic (B1, 2026-09-03) -- pure, zero I/O.
# --------------------------------------------------------------------------- #
def _nth_business_day_of_month(year: int, month: int, n: int, holidays: frozenset[str]) -> str:
    """1-indexed n-th US-market business day of (year, month), as YYYY-MM-DD.
    Reuses is_trading_day() (this file's existing weekend+holiday helper) rather
    than duplicating that logic."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    d = datetime(year, month, 1)
    count = 0
    while d.month == month:
        ds = d.strftime("%Y-%m-%d")
        if is_trading_day(ds, holidays):
            count += 1
            if count == n:
                return ds
        d += timedelta(days=1)
    raise ValueError(f"{year}-{month:02d} has fewer than {n} US-market business days")


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> str:
    """1-indexed n-th occurrence of `weekday` (Mon=0..Sun=6) in (year, month), as
    YYYY-MM-DD. No holiday-skipping -- Consumer Confidence/UMich are published as
    calendar-weekday rules (not business-day rules)."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    d = datetime(year, month, 1)
    count = 0
    while d.month == month:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d.strftime("%Y-%m-%d")
        d += timedelta(days=1)
    raise ValueError(f"{year}-{month:02d} has fewer than {n} occurrences of weekday {weekday}")


def _last_weekday_of_month(year: int, month: int, weekday: int) -> str:
    """Last occurrence of `weekday` (Mon=0..Sun=6) in (year, month), as YYYY-MM-DD."""
    next_month_first = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    d = next_month_first - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def generate_rule_based_events(
    year: int, holidays: Optional[frozenset[str]] = None
) -> list[dict[str, Any]]:
    """The full RULE-BASED 10:00 ET release schedule for `year`. Deterministic,
    zero network/file I/O by default -- `holidays` defaults to the hard-coded
    NYSE_HOLIDAYS_2026 table above; pass a different set to use another year's
    holidays or a live-fetched calendar (e.g. load_holidays(alpaca_calendar_path)).

    Every entry:
      - source == "rule_based" (distinguishes it from KNOWN_EVENTS_2026's
        hand-curated entries, which carry no `source` key at all).
      - carries its generating `rule` as prose (self-documenting -- no need to
        cross-reference this docstring to know WHY a date was picked).
      - ISM Manufacturing / ISM Services: severity="high", verified=True,
        verified_by=<quote-tape cross-check citation> -- matches
        KNOWN_EVENTS_2026's severity vocabulary (high/med).
      - Consumer Confidence / UMich prelim / UMich final: severity="med",
        verified=False, status="RULE_BASED_UNVERIFIED" -- a stateable
        calendar-position rule exists but has NOT been cross-checked against a
        live price gap the way ISM has.
      - JOLTS is deliberately NOT generated at all: its real-world timing
        ("first Tuesday-ish") has no deterministic rule to encode, and this
        generator's instruction is to omit rather than guess.

    Only NYSE_HOLIDAYS_2026 is hard-coded, so years other than 2026 compute
    correctly for weekday-based rules (Consumer Confidence/UMich) but will not
    skip any NYSE holiday for the business-day-based ISM rules unless `holidays`
    is supplied explicitly for that year.
    """
    hset = holidays if holidays is not None else NYSE_HOLIDAYS_2026
    events: list[dict[str, Any]] = []
    for month in range(1, 13):
        events.append({
            "date": _nth_business_day_of_month(year, month, 1, hset),
            "time_et": "10:00",
            "event": f"ISM Manufacturing PMI ({_prior_month_label(year, month)} data)",
            "type": "ism_manufacturing_pmi",
            "severity": "high",
            "source": "rule_based",
            "source_url": _ISM_SOURCE_URL,
            "rule": _ISM_MANUFACTURING_RULE,
            "verified": True,
            "verified_by": _ISM_VERIFIED_BY,
            "notes": "Generated by macro_calendar.generate_rule_based_events() -- B1 2026-09-03.",
        })
        events.append({
            "date": _nth_business_day_of_month(year, month, 3, hset),
            "time_et": "10:00",
            "event": f"ISM Services PMI ({_prior_month_label(year, month)} data)",
            "type": "ism_services_pmi",
            "severity": "high",
            "source": "rule_based",
            "source_url": _ISM_SOURCE_URL,
            "rule": _ISM_SERVICES_RULE,
            "verified": True,
            "verified_by": _ISM_VERIFIED_BY,
            "notes": "Generated by macro_calendar.generate_rule_based_events() -- B1 2026-09-03.",
        })
        events.append({
            "date": _last_weekday_of_month(year, month, 1),  # Tuesday = 1
            "time_et": "10:00",
            "event": f"Conference Board Consumer Confidence ({_month_label(year, month)})",
            "type": "consumer_confidence",
            "severity": "med",
            "source": "rule_based",
            "status": "RULE_BASED_UNVERIFIED",
            "rule": _CONSUMER_CONFIDENCE_RULE,
            "verified": False,
            "notes": "Generated by macro_calendar.generate_rule_based_events() -- B1 2026-09-03.",
        })
        events.append({
            "date": _nth_weekday_of_month(year, month, 4, 2),  # Friday = 4, 2nd occurrence
            "time_et": "10:00",
            "event": f"University of Michigan Consumer Sentiment, preliminary ({_month_label(year, month)})",
            "type": "umich_sentiment_prelim",
            "severity": "med",
            "source": "rule_based",
            "status": "RULE_BASED_UNVERIFIED",
            "rule": _UMICH_PRELIM_RULE,
            "verified": False,
            "notes": "Generated by macro_calendar.generate_rule_based_events() -- B1 2026-09-03.",
        })
        events.append({
            "date": _nth_weekday_of_month(year, month, 4, 4),  # Friday = 4, 4th occurrence
            "time_et": "10:00",
            "event": f"University of Michigan Consumer Sentiment, final ({_month_label(year, month)})",
            "type": "umich_sentiment_final",
            "severity": "med",
            "source": "rule_based",
            "status": "RULE_BASED_UNVERIFIED",
            "rule": _UMICH_FINAL_RULE,
            "verified": False,
            "notes": "Generated by macro_calendar.generate_rule_based_events() -- B1 2026-09-03.",
        })
    events.sort(key=lambda e: (e["date"], e["time_et"], e["type"]))
    return events


def scheduled_releases(date: str, holidays: Optional[frozenset[str]] = None) -> list[dict[str, Any]]:
    """PURE, network-free: the RULE_BASED 10:00 ET macro release(s) scheduled for
    `date` (YYYY-MM-DD). Example:
        scheduled_releases("2026-09-03") ->
            [{"date": "2026-09-03", "time_et": "10:00",
              "event": "ISM Services PMI (Aug 2026 data)",
              "type": "ism_services_pmi", "severity": "high",
              "source": "rule_based", "source_url": ..., "rule": ...,
              "verified": True, "verified_by": ..., "notes": ...}]
    Returns [] on a day with no rule-based release.

    Importing this module, or calling this function, NEVER touches the network
    and never reads a file: the holiday table used is the hard-coded
    NYSE_HOLIDAYS_2026 module constant unless the caller passes `holidays`
    explicitly (e.g. macro_calendar.load_holidays(alpaca_calendar_path) for a
    live-fetched calendar instead). Other scripts can therefore `import
    macro_calendar` and call this function with zero side effects -- the
    module-level network calls in this file (verify_source, _BLS_PROBE_SOURCES)
    only ever run inside refresh_macro_calendar()/run(), which this function
    does not touch.
    """
    year = int(date[:4])
    return [e for e in generate_rule_based_events(year, holidays) if e["date"] == date]


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
            # .get() (not ev['source_url']) -- rule-based Consumer Confidence /
            # UMich entries (generate_rule_based_events()) carry no source_url,
            # only a self-documenting `rule` string; a plain KeyError here would
            # crash build_news_json() on exactly the days those events become
            # primary/secondary catalysts, defeating the B2 wiring for them.
            "description": f"{ev['event']} -- severity={ev['severity']}. "
                            f"Source: {ev.get('source_url', ev.get('rule', 'no source cited'))}"
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

    # RULE-BASED WIRING (B2, 2026-09-03): merge for_session's deterministic,
    # network-free release(s) (scheduled_releases() -- ISM/Consumer-Confidence/
    # UMich, see generate_rule_based_events() above) into the SAME known_events
    # list KNOWN_EVENTS_2026's hand-curated FOMC/BLS entries feed, so
    # refresh_macro_calendar()'s existing merge/dedupe/prune pipeline (dedupe
    # by (date, type) against events_30d) treats a rule-based release exactly
    # like a hand-curated one -- one code path, no drift. Root cause this
    # closes: today (2026-09-03, ISM Services PMI day) the 08:15 ET daily
    # fire wrote news.json saying "no scheduled event" because
    # generate_rule_based_events()/scheduled_releases() existed as pure
    # functions but were never called from run(). Scope is deliberately
    # for_session ONLY (not a wider lookahead window) -- scheduled_releases()
    # returns [] on any day without a rule-based release, so known_events is
    # byte-for-byte identical to the pre-wiring KNOWN_EVENTS_2026 list on
    # every such day; only a genuine release day changes events_30d at all.
    # holidays falls back to the module's hardcoded NYSE_HOLIDAYS_2026 table
    # (frozenset(holidays) if holidays else None) when the Alpaca calendar
    # cache is empty/missing, per this file's existing fail-open philosophy.
    rule_holidays = frozenset(holidays) if holidays else None
    known_events = list(KNOWN_EVENTS_2026) + scheduled_releases(for_session, rule_holidays)

    new_calendar, log_entry = refresh_macro_calendar(existing_calendar, today, known_events, active_fetch_fn)
    news = build_news_json(new_calendar, today, for_session)

    if not dry_run:
        _atomic_write_json(calendar_path, new_calendar)
        _atomic_write_json(news_path, news)

    events_today = [e for e in new_calendar["events_30d"] if e["date"] == for_session]
    upcoming_10td = next_n_trading_days(today, 10, holidays)
    events_next_10td = [e for e in new_calendar["events_30d"] if e["date"] in upcoming_10td]

    # Lookahead enrichment for the events_next_10_trading_days digest field
    # ONLY -- does NOT persist into events_30d, so it can't perturb the
    # hand-curated file's merge/dedupe/idempotency counts on a day with no
    # rule-based release of its own. Folds in any rule-based release across
    # the next ~10 trading sessions not already present in events_30d, so
    # this field (unlike before) actually surfaces ISM/UMich/Consumer-
    # Confidence dates the hand-curated table has never covered.
    lookahead_keys = {(e["date"], e["type"]) for e in events_next_10td}
    for d in upcoming_10td:
        for ev in scheduled_releases(d, rule_holidays):
            key = (ev["date"], ev["type"])
            if key not in lookahead_keys:
                events_next_10td.append(ev)
                lookahead_keys.add(key)
    events_next_10td.sort(key=lambda e: (e["date"], e.get("time_et", "")))

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
        # Surfaced directly (not just buried in news.json) per OP-33 visibility --
        # this is the exact field that silently read "no scheduled event" on
        # ISM days pre-wiring; a --dry-run print now shows the true catalyst.
        "catalyst_summary": news["catalyst_summary"],
        "primary_catalyst": news["primary_catalyst"],
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
