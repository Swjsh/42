"""earnings_calendar.py -- trusted earnings-calendar producer for the weekly-options lane
(arm weekly-1, markdown/planning/WEEKLY-OPTIONS-PROGRAM.md).

WHY THIS EXISTS: the lane's single worst NEW failure mode vs the core 0DTE SPY book is
holding a single-name option through an earnings print -- IV crush routinely loses money
even when direction is right (MIT working paper cited in the program doc's research
synthesis: retail documented losing to crush, not direction). This is the producer half of
the guard; the consumer (another workstream) reads this file's per-symbol record and blocks
entry per the FAIL-CLOSED CONTRACT below. This script NEVER places/cancels/modifies an
order -- it only computes and writes state (PAPER/SHADOW-only lane, house rule).

TWO-SOURCE DESIGN (verified live 2026-08-18, both reachable from this host):
  1. PRIMARY -- yfinance's Ticker.calendar / Ticker.earnings_dates (already installed in
     backtest/.venv, 0.2.66; no new dependency). Live-verified: NVDA next print
     2026-08-26 16:00 ET (AMC), AAPL 2026-10-29 16:00 ET (AMC), JPM 06:00-08:00 ET rows
     (BMO) -- confirms yfinance returns ET-local wall-clock timestamps (tz offset -04:00
     = EDT) directly usable for AMC/BMO classification with no separate ET conversion.
     GLD (ETF) returns calendar={} and earnings_dates=None with NO exception -- this is
     the legitimate "no company earnings" signal the ETF short-circuit relies on.
  2. CROSS-CHECK -- Nasdaq's public earnings-calendar JSON endpoint
     (https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD), live-verified
     2026-08-18: HTTP 200, requires a browser User-Agent (no key), returns
     data.rows[]=[{symbol,time,...}] for that ONE calendar date. Confirmed live: NVDA
     appears in the 2026-08-26 payload with time="time-after-hours" -- agrees with
     yfinance's AMC read for the same date, an independent real-world confirmation of
     both the endpoint's shape and the two-source design.
  FMP and Polygon were investigated per the task brief and are confirmed paid-gated dead
  ends for this use (no free earnings-calendar tier) -- not used, not wired.

  2-SOURCE AGREEMENT RULE (per params.json's shadow-first, fail-closed posture):
    - both sources found the SAME (date, timing) -> confidence="confirmed"
    - both sources found the symbol but DISAGREE (different date and/or conflicting
      definite timing) -> confidence="disputed", and the blackout window is the UNION of
      each source's own window (min start, max end) -- the conservative direction, never
      narrower than either source alone would produce.
    - only yfinance answered (Nasdaq unreachable, or reachable but didn't list the
      symbol near that date) -> confidence="single_source".
    - yfinance itself has no usable answer (exception, or rows but none upcoming) ->
      status="unavailable" (NOT fabricated as a plausible date -- see FAIL-CLOSED below).
      Nasdaq is a CROSS-CHECK, never promoted to primary on yfinance's total failure --
      that would blend "verification" and "fallback primary" roles the design brief
      explicitly keeps separate.

BLACKOUT WINDOW ARITHMETIC -- AMC vs BMO (own design, documented here because
params.json/the program doc specify the WIDTH -- entry.earnings_blackout_sessions TRADING
sessions before the print through the session after it -- but not how AMC/BMO shifts the
anchor; this is that missing piece, pinned exactly by
test_earnings_calendar_producer.py::test_*_blackout_window_exact_dates):
  A print's real overnight-gap danger sits at a specific trading-session BOUNDARY, not
  necessarily on the print's own calendar date:
    - AMC (after the close) on session D: the gap materializes overnight D -> D+1 (the
      report drops after D's 4pm close, market absorbs it at D+1's open). A position must
      already be flat by D's close, so D itself is the "must be flat" session -- the
      anchor is D, unshifted.
    - BMO (before the open) on session D: the gap materializes overnight D-1 -> D (the
      report drops before D opens). A position must already be flat by D-1's close -- the
      anchor is the PRIOR trading session, D-1.
    - unknown timing -> treated as BMO throughout (per task brief: "the more conservative
      assumption, since a BMO print makes the prior evening's hold dangerous" -- an
      un-shifted AMC-style anchor would allow an entry on D-1 that a real BMO print makes
      dangerous).
  Given the anchor session A (= D for AMC, D-1 for BMO/unknown):
    blackout_start_date = A shifted back `entry.earnings_blackout_sessions` TRADING
                           sessions (never calendar days -- weekends/holidays are skipped
                           entirely, not counted)
    blackout_end_date   = A shifted forward 1 TRADING session
  This makes the window's total session-count identical for AMC and BMO (N+2 sessions),
  just anchored one session apart -- AMC's window includes the day AFTER the print
  (overnight gap risk into D+1), BMO's window includes the day OF the print (overnight
  gap risk already realized by D's open, elevated intraday vol) but not the day after.

NO-LOOK-AHEAD CONTRACT: every symbol record carries its own `as_of` timestamp, which is
the FIRST run that observed the CURRENT `next_earnings_date` value -- re-confirming an
unchanged date on a later run does NOT bump as_of (mirrors macro_calendar.py's
merge-not-replace idiom). A backtest filtering to "what was known as of date X" must use
this field, never the file's generated_at_et (which only says when the file was last
touched, not when a given fact became known) -- using an earnings date the market did not
yet know on a given historical day is a classic look-ahead leak.

FAIL-CLOSED CONSUMPTION CONTRACT (also embedded verbatim in the written JSON's
`_fail_closed_contract` field -- see that string for the exact wording another workstream's
consumer must implement): a consumer MUST treat any non-exempt single-name symbol as
BLOCKED when this file is missing/unreadable, when it is older than
params.json#entry.earnings_feed_stale_hours_fail_closed hours, or when that symbol's own
entry has status != "ok" (a lookup failure). ETF entries (exempt=true) are never blocked
by this feed. This script is the PRODUCER only -- wiring the actual entry gate is another
workstream's job (per the task brief).

ETF SHORT-CIRCUIT: KNOWN_ETFS is a small, named fast path (GLD, QQQ -- called out
explicitly in WEEKLY-OPTIONS-PROGRAM.md sec 2/params.json's universe) that skips the
network entirely for symbols already known to have no company earnings. ANY OTHER symbol
that queries yfinance cleanly (no exception) and gets back an empty calendar AND empty
earnings_dates is ALSO exempted -- this is a real API answer confirming absence, not a
silent default on error, so it correctly covers "any symbol with no company earnings"
(per the task brief) without hand-maintaining an exhaustive list. A genuine fetch
exception is never mistaken for this case (see lookup_yfinance_earnings).

SILENT-SUCCESS GUARD: run() raises if it would produce zero symbol records (empty
universe in params.json); main() additionally exits 1 (with each failing symbol named on
stderr) if any NON-EXEMPT symbol totally failed lookup (both sources unusable) -- the
file is still written with an explicit failure entry for that symbol (never fabricated),
but the process signals loudly rather than reporting exit-0 success on a feed that did
not actually do its job for that name (C7 -- silent success is failure).

Usage:
    python earnings_calendar.py                  # normal run: live yfinance + Nasdaq
    python earnings_calendar.py --dry-run         # compute + print, no writes
    python earnings_calendar.py --date 2026-08-18 # override "today"/generated_at (testing/backfill)
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402  (canonical ET clock -- never hand-roll TZ math)

STATE = REPO / "automation" / "state"
WEEKLY_STATE = STATE / "weekly"
PARAMS_PATH = WEEKLY_STATE / "params.json"
OUTPUT_PATH = WEEKLY_STATE / "earnings-blackout.json"
CALENDAR_PATH = STATE / "calendar.json"

# Fast-path exempt symbols named explicitly in WEEKLY-OPTIONS-PROGRAM.md sec 2 / params.json
# universe -- saves the network round-trip for names we already KNOW are ETFs. NOT
# exhaustive: any other symbol that queries cleanly with zero earnings data is ALSO
# exempted at query time (see lookup_yfinance_earnings) -- this list is an optimization,
# not the only path to "exempt".
KNOWN_ETFS: frozenset[str] = frozenset({"GLD", "QQQ"})

NASDAQ_EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"
NASDAQ_TIME_MAP = {"time-after-hours": "amc", "time-pre-market": "bmo"}  # anything else -> "unknown"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# --------------------------------------------------------------------------- #
# Pure helpers (deliberately duplicated, not imported, from macro_calendar.py's proven
# is_trading_day/next_trading_day pattern -- see self_check.py's own module comment above
# check_macro_calendar_freshness for why this codebase prefers small duplicated pure
# helpers over cross-importing sibling producer scripts across ownership boundaries /
# differing runtime environments).
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
    """Write JSON atomically (tmp file + os.replace) so a crash mid-write never corrupts
    the live state file (matches macro_calendar.py's _atomic_write_json exactly)."""
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


def load_holidays(calendar_path: Path) -> "set[str]":
    """US market holidays from automation/state/calendar.json (Alpaca-sourced, an
    already-working producer; reused here rather than duplicated computation)."""
    data = load_json(calendar_path, {})
    return set(data.get("holidays", []))


def is_trading_day(date_str: str, holidays: "set[str]") -> bool:
    d = datetime.fromisoformat(date_str)
    return d.weekday() < 5 and date_str not in holidays


def shift_trading_days(date_str: str, n: int, holidays: "set[str]") -> str:
    """Step exactly `n` TRADING SESSIONS (never calendar days) from `date_str` -- n>0
    forward, n<0 backward, n==0 returns date_str unchanged. Weekends and `holidays` are
    skipped entirely, never counted as a step. This is the ONLY place session-vs-calendar
    day counting happens; every blackout-window date flows through this function."""
    d = datetime.fromisoformat(date_str)
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining > 0:
        d += timedelta(days=step)
        if is_trading_day(d.strftime("%Y-%m-%d"), holidays):
            remaining -= 1
    return d.strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# AMC/BMO classification + blackout-window arithmetic (pure -- see module docstring for
# the full rationale).
# --------------------------------------------------------------------------- #
def classify_timing(hour: int, minute: int) -> str:
    """ET wall-clock hour/minute -> 'bmo' (before 09:30 open) / 'amc' (16:00 close or
    later) / 'unknown' (the rare mid-session announcement, or an unclassifiable time).
    Verified live 2026-08-18 against real yfinance rows: NVDA/AAPL/TSLA report at
    16:00:00-04:00 (amc), JPM at 06:00:00-04:00 / 08:00:00-04:00 (bmo)."""
    minutes = hour * 60 + minute
    if minutes < 9 * 60 + 30:
        return "bmo"
    if minutes >= 16 * 60:
        return "amc"
    return "unknown"


def compute_blackout_window(print_date: str, timing: str, blackout_sessions: int,
                             holidays: "set[str]") -> "tuple[str, str]":
    """(blackout_start_date, blackout_end_date) for one (print_date, timing) pair. See the
    module docstring's BLACKOUT WINDOW ARITHMETIC section for the AMC-vs-BMO anchor-shift
    rationale. `timing` may be 'amc' / 'bmo' / 'unknown' -- anything other than the
    literal 'amc' is treated as BMO for anchor purposes (the conservative default the task
    brief specifies for unknown timing)."""
    anchor = print_date if timing == "amc" else shift_trading_days(print_date, -1, holidays)
    start = shift_trading_days(anchor, -blackout_sessions, holidays)
    end = shift_trading_days(anchor, 1, holidays)
    return start, end


# --------------------------------------------------------------------------- #
# Source 1 (PRIMARY): yfinance
# --------------------------------------------------------------------------- #
def lookup_yfinance_earnings(symbol: str, *, today: str, ticker_factory=None) -> dict:
    """Return {'exempt', 'found', 'date', 'timing', 'error', 'reason'} (unused keys None).

    exempt=True         -- known ETF (no network call) OR yfinance cleanly confirmed no
                            company earnings exist (calendar AND earnings_dates both
                            empty, no exception) -- the "no company earnings" case from
                            the task brief, not a failure.
    found=True           -- a real upcoming (>= today) earnings date was read.
    found=False, error=.. -- a GENUINE failure (exception, or data present but nothing
                            upcoming) -- never silently treated as exempt (house rule: no
                            silent fallback / no plausible-looking default)."""
    if symbol in KNOWN_ETFS:
        return {"exempt": True, "found": False, "date": None, "timing": None, "error": None,
                "reason": "known ETF (KNOWN_ETFS static list) -- no company earnings, not queried"}

    factory = ticker_factory
    if factory is None:
        import yfinance as yf  # noqa: PLC0415 -- lazy import, already in backtest/.venv
        factory = yf.Ticker

    try:
        t = factory(symbol)
        earnings_dates = t.earnings_dates
        calendar = t.calendar
    except Exception as e:  # noqa: BLE001 -- genuine fetch failure, recorded with context, never swallowed
        return {"exempt": False, "found": False, "date": None, "timing": None,
                "error": f"yfinance {type(e).__name__}: {e}", "reason": None}

    ed_empty = earnings_dates is None or getattr(earnings_dates, "empty", True)
    cal_empty = not calendar
    if ed_empty and cal_empty:
        return {"exempt": True, "found": False, "date": None, "timing": None, "error": None,
                "reason": "yfinance returned no calendar/earnings_dates data -- no company earnings"}
    if ed_empty:
        return {"exempt": False, "found": False, "date": None, "timing": None,
                "error": "earnings_dates empty but calendar non-empty -- ambiguous yfinance "
                         "response, not trusted as either a date or an exemption",
                "reason": None}

    rows = [(ts.strftime("%Y-%m-%d"), ts.hour, ts.minute) for ts in earnings_dates.index]
    upcoming = [r for r in rows if r[0] >= today]
    if not upcoming:
        return {"exempt": False, "found": False, "date": None, "timing": None,
                "error": "earnings_dates has rows but none on/after today -- no upcoming print known",
                "reason": None}
    soonest = min(upcoming, key=lambda r: r[0])
    return {"exempt": False, "found": True, "date": soonest[0],
            "timing": classify_timing(soonest[1], soonest[2]), "error": None, "reason": None}


# --------------------------------------------------------------------------- #
# Source 2 (CROSS-CHECK): Nasdaq public earnings-calendar JSON
# --------------------------------------------------------------------------- #
def _default_nasdaq_fetch(date_str: str) -> "list[dict]":
    """REAL network GET against NASDAQ_EARNINGS_URL for one calendar date. Raises on any
    failure -- callers decide fail-open handling (matches macro_calendar.py's
    verify_source contract: this function never silently returns a fabricated empty
    result on error, its caller distinguishes 'probed, empty' from 'unreachable')."""
    import urllib.request  # noqa: PLC0415
    url = f"{NASDAQ_EARNINGS_URL}?date={date_str}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:  # noqa: S310 -- fixed https host
        body = r.read().decode("utf-8")
    payload = json.loads(body)
    return ((payload.get("data") or {}).get("rows")) or []


def lookup_nasdaq_earnings(symbol: str, near_date: str, holidays: "set[str]", *,
                            fetch: "Callable[[str], list[dict]] | None" = None,
                            probe_sessions: int = 1) -> dict:
    """Probe Nasdaq's earnings-calendar JSON for `symbol` on near_date plus the
    `probe_sessions` TRADING sessions immediately before/after it -- so a name reported
    off-by-one-session by either source is still found, rather than mislabeled
    'unreachable'. Returns {'reachable', 'found', 'date', 'timing', 'error'}.

    'reachable' distinguishes 'the endpoint answered but the symbol genuinely isn't
    listed in this window' (Nasdaq DISAGREES) from 'every probed date failed to fetch'
    (Nasdaq is DOWN) -- the caller (cross_check_symbol) must never conflate the two.
    Never raises (fail-open observer, matches macro_calendar.py's verify_source)."""
    fetch = fetch or _default_nasdaq_fetch
    candidates = {near_date}
    d = near_date
    for _ in range(probe_sessions):
        d = shift_trading_days(d, -1, holidays)
        candidates.add(d)
    d = near_date
    for _ in range(probe_sessions):
        d = shift_trading_days(d, 1, holidays)
        candidates.add(d)

    any_reachable = False
    for cand in sorted(candidates):
        try:
            rows = fetch(cand)
        except Exception:  # noqa: BLE001 -- this ONE date probe failed; try the rest
            continue
        any_reachable = True
        for row in rows:
            if str(row.get("symbol", "")).upper() == symbol.upper():
                timing = NASDAQ_TIME_MAP.get(row.get("time"), "unknown")
                return {"reachable": True, "found": True, "date": cand, "timing": timing, "error": None}

    if any_reachable:
        return {"reachable": True, "found": False, "date": None, "timing": None,
                "error": f"{symbol} not listed on Nasdaq's earnings calendar within "
                         f"+/-{probe_sessions} session(s) of {near_date}"}
    return {"reachable": False, "found": False, "date": None, "timing": None,
            "error": "Nasdaq earnings-calendar endpoint unreachable on every probed date"}


# --------------------------------------------------------------------------- #
# Cross-check combiner (pure -- see module docstring's 2-SOURCE AGREEMENT RULE)
# --------------------------------------------------------------------------- #
def cross_check_symbol(symbol: str, yf_result: dict, nasdaq_result: dict,
                        blackout_sessions: int, holidays: "set[str]") -> dict:
    """Combine ONE symbol's yfinance + Nasdaq results into the final record. Pure (no
    I/O) -- every branch is independently unit-testable with plain dict inputs."""
    if yf_result.get("exempt"):
        return {"exempt": True, "reason": yf_result.get("reason")}
    if not yf_result.get("found"):
        return {"exempt": False, "status": "unavailable", "error": f"yfinance: {yf_result.get('error')}"}

    yf_date, yf_timing = yf_result["date"], yf_result["timing"]
    nasdaq_ok = bool(nasdaq_result.get("reachable")) and bool(nasdaq_result.get("found"))

    if nasdaq_ok:
        nd_date, nd_timing = nasdaq_result["date"], nasdaq_result["timing"]
        timing_conflict = (yf_timing != "unknown" and nd_timing != "unknown" and yf_timing != nd_timing)
        if nd_date == yf_date and not timing_conflict:
            final_timing = yf_timing if yf_timing != "unknown" else nd_timing
            start, end = compute_blackout_window(yf_date, final_timing, blackout_sessions, holidays)
            return {"exempt": False, "status": "ok", "confidence": "confirmed", "sources_agreed": True,
                    "next_earnings_date": yf_date, "timing": final_timing,
                    "blackout_start_date": start, "blackout_end_date": end}
        # DISAGREEMENT (date and/or timing) -- UNION-WIDEN: each source's own window,
        # conservative envelope = earliest start, latest end. Never narrower than either
        # source alone would have produced.
        s1, e1 = compute_blackout_window(yf_date, yf_timing, blackout_sessions, holidays)
        s2, e2 = compute_blackout_window(nd_date, nd_timing, blackout_sessions, holidays)
        start, end = min(s1, s2), max(e1, e2)
        return {"exempt": False, "status": "ok", "confidence": "disputed", "sources_agreed": False,
                "next_earnings_date": yf_date, "timing": yf_timing,
                "disputed_detail": {"yfinance": {"date": yf_date, "timing": yf_timing},
                                     "nasdaq": {"date": nd_date, "timing": nd_timing}},
                "blackout_start_date": start, "blackout_end_date": end}

    # Nasdaq did not corroborate (unreachable OR reachable-but-symbol-not-found) -- single source.
    start, end = compute_blackout_window(yf_date, yf_timing, blackout_sessions, holidays)
    return {"exempt": False, "status": "ok", "confidence": "single_source", "sources_agreed": False,
            "next_earnings_date": yf_date, "timing": yf_timing,
            "cross_check_note": nasdaq_result.get("error"),
            "blackout_start_date": start, "blackout_end_date": end}


# --------------------------------------------------------------------------- #
# Per-symbol record (adds no-look-ahead as_of merge on top of the pure cross-check)
# --------------------------------------------------------------------------- #
def build_symbol_record(symbol: str, now_et: datetime, params: dict, holidays: "set[str]",
                         existing: "dict | None", *, yf_lookup=None, nasdaq_lookup=None) -> dict:
    """ONE symbol's full JSON record. See module docstring's NO-LOOK-AHEAD CONTRACT for
    why `as_of` is merged against `existing` rather than always stamped 'now'."""
    now_iso = now_et.strftime("%Y-%m-%dT%H:%M:%S")
    today = now_et.strftime("%Y-%m-%d")
    blackout_sessions = int(params["entry"]["earnings_blackout_sessions"])

    yf_lookup = yf_lookup or lookup_yfinance_earnings
    yf_result = yf_lookup(symbol, today=today)

    if yf_result.get("exempt"):
        return {"exempt": True, "reason": yf_result.get("reason"), "as_of": now_iso}

    if yf_result.get("found"):
        nasdaq_lookup = nasdaq_lookup or lookup_nasdaq_earnings
        nasdaq_result = nasdaq_lookup(symbol, yf_result["date"], holidays)
    else:
        nasdaq_result = {"reachable": False, "found": False, "date": None, "timing": None,
                          "error": "skipped -- no yfinance date to cross-check against"}

    combined = cross_check_symbol(symbol, yf_result, nasdaq_result, blackout_sessions, holidays)
    if combined.get("exempt") or combined.get("status") != "ok":
        combined["as_of"] = now_iso
        return combined

    prior_date = (existing or {}).get("next_earnings_date")
    if prior_date == combined["next_earnings_date"] and (existing or {}).get("as_of"):
        combined["as_of"] = existing["as_of"]  # unchanged value -- preserve first-known timestamp
    else:
        combined["as_of"] = now_iso  # new/changed date -- this run is when we learned it
    return combined


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(repo_root: Path = REPO, now: "datetime | None" = None, dry_run: bool = False,
        yf_lookup=None, nasdaq_lookup=None) -> dict:
    state = repo_root / "automation" / "state"
    weekly_state = state / "weekly"
    params_path = weekly_state / "params.json"
    output_path = weekly_state / "earnings-blackout.json"
    calendar_path = state / "calendar.json"

    now_et = now or et_now()
    # params.json is REQUIRED, already-existing config another workstream owns -- a
    # missing/unreadable file is a real fatal error, never a silent default (house rule).
    params = json.loads(params_path.read_text(encoding="utf-8"))
    holidays = load_holidays(calendar_path)
    existing_symbols = load_json(output_path, {}).get("symbols", {})

    universe = list(dict.fromkeys(
        list(params.get("universe", {}).get("active", []))
        + list(params.get("universe", {}).get("wave_2_pending", []))
    ))
    if not universe:
        raise RuntimeError("earnings_calendar.py: params.json universe.active + "
                            "wave_2_pending is EMPTY -- refusing to write a symbol-less file "
                            "(silent-success guard).")

    symbols = {
        sym: build_symbol_record(sym, now_et, params, holidays, existing_symbols.get(sym),
                                  yf_lookup=yf_lookup, nasdaq_lookup=nasdaq_lookup)
        for sym in universe
    }
    if not symbols:  # defense in depth -- universe non-empty guarantees this today, but
        raise RuntimeError("earnings_calendar.py: computed zero symbol records -- refusing "
                            "to write an empty file (silent-success guard).")

    stale_h = params.get("entry", {}).get("earnings_feed_stale_hours_fail_closed", "?")
    out = {
        "generated_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "producer": "setup/scripts/earnings_calendar.py",
        "_fail_closed_contract": (
            f"Consumers MUST treat this feed as BLOCKED for any non-exempt weekly-1 "
            f"single-name symbol when: (a) this file is missing/unreadable, (b) "
            f"generated_at_et is older than params.json#entry."
            f"earnings_feed_stale_hours_fail_closed ({stale_h}h), or (c) that symbol's "
            f"own entry has status != 'ok' and exempt != true. ETF entries (exempt=true) "
            f"are never blocked by this feed. Fail-CLOSED means 'no entry allowed', "
            f"never a silent pass-through on missing/stale/failed data."
        ),
        "symbols": symbols,
    }
    if not dry_run:
        _atomic_write_json(output_path, out)
    return out


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--dry-run", action="store_true", help="compute and print, but do not write state files")
    ap.add_argument("--date", default=None, help="override 'today'/generated_at as YYYY-MM-DD (testing/backfill)")
    args = ap.parse_args(argv)

    now = datetime.fromisoformat(args.date) if args.date else None

    try:
        result = run(REPO, now=now, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 -- top-level guard: never crash silently (Task
        # Scheduler needs a clean, loud exit code + stderr message, not a raw traceback).
        print(f"FATAL earnings_calendar.py: {exc}", file=sys.stderr)
        return 1

    non_exempt = {s: r for s, r in result["symbols"].items() if not r.get("exempt")}
    failed = {s: r for s, r in non_exempt.items() if r.get("status") != "ok"}
    print(json.dumps(result, indent=2, default=str))
    if failed:
        print(f"earnings_calendar.py: {len(failed)} symbol(s) FAILED lookup entirely "
              f"(both sources unusable) -- {sorted(failed)}. The file was still written "
              f"with an explicit failure entry for each (never fabricated) so a fail-"
              f"closed consumer blocks these symbols; see detail below.", file=sys.stderr)
        for s, r in failed.items():
            print(f"  {s}: {r.get('error')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
