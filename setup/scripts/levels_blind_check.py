"""levels_blind_check.py -- did the engine trade BLIND (zero key levels) today?

WHY THIS EXISTS (2026-07-30 incident):
Gamma_LevelRefresh last fired 2026-07-29 20:43 ET and its next run was scheduled for
2026-07-30 16:38 ET -- AFTER the close. It never ran during RTH. key-levels.json therefore
sat untouched for ~19.8h, still `date`/`for_session` = 2026-07-29, with EVERY level carrying
`expires_at` 2026-07-29. `heartbeat_core._read_levels` did exactly the right thing -- it
dropped every expired level (`_level_expired`) and returned ([], []) -- so EVERY ONE of the
day's ~770 RTH decision rows carries `levels_active: []`.

The engine did NOT halt, warn, or degrade. It silently fell through to trendline-only
entries -- its statistically WORST cohort (-$1,830 / WR .19 over 124 trades, vs +$6,895/66
for level-tied trades, PNL-ATTRIBUTION-2026-07-28) -- and at 11:31-11:46 ET produced 11
ENTER_BEAR verdicts at SPY 734.885, the LOW OF THE DAY, before SPY rallied 6.7 points into
the close. Only RISK_DENY_RISK_CAP / RISK_DENY_PDT stopped those fills. Luck, not design.

And NOTHING said so: `engine_health.check_level_feed` is market_open-suppressed ("market
closed -- refresh idle, quiet OK") so by the time anyone looked it read GREEN, the exact
suppression bug that let the 2026-07-24 outage read GREEN 13/13. This module is the
missing assertion, and it deliberately asks about the DAY, not the moment.

TWO INDEPENDENT SIGNALS (either alone would have caught 2026-07-30):
  1. CONSUMER side -- `assess_rows` / `check_day`: on a weekday, did the engine's own
     decision rows carry a non-empty `levels_active`? This is ground truth about what the
     engine actually SAW, downstream of every producer, cache, and expiry rule. Scoped to
     RTH rows and judged on a RATIO -- see BLIND_SIGHTED_RATIO for why both matter (a
     whole-day any-row test was masked by 2 post-close ticks while building this).
  2. PRODUCER side -- `assess_levels_file` / `check_levels_file`: is key-levels.json
     dated today and actually being rewritten? Uses the file's real MTIME (ground truth)
     rather than the self-reported `as_of` string, and the date fields the live refresher
     itself stamps (`refresh_levels_intraday.py` sets both `date` and `for_session`).

MONITORING, therefore FAIL-OPEN EVERYWHERE (house rule): this module never raises -- every
failure path degrades to UNKNOWN, and every caller (engine_health's beacon, daily_brief's
EOD lead line, premarket_readiness's gate) treats a thrown exception as worse than useless.
Nothing here can block a trade; being LOUD is its entire job. Making "blind" mean DO NOT
TRADE is the ENTRY side's work, not this checker's.

CLI:
  python setup/scripts/levels_blind_check.py                  # today, both signals
  python setup/scripts/levels_blind_check.py --date 2026-07-30
  python setup/scripts/levels_blind_check.py --json
Exit codes: 0 = SIGHTED / NOT_APPLICABLE, 3 = BLIND, 4 = UNKNOWN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
KEY_LEVELS = STATE / "key-levels.json"

# A day needs at least this many decision rows before "zero levels_active" is unambiguously
# blindness rather than a warm-up / half-session / holiday artifact. A full RTH writes ~772
# rows (386/account x2); 30 covers roughly the first 15 minutes of a normal session.
# Deliberately low: total absence of level-sight should shout, a slow start should not.
MIN_ROWS_FOR_VERDICT = 30

# Below this sighted-fraction of the RTH rows the session counts as blind even though SOME
# row saw a level. Learned during this build: a whole-day "did ANY row see a level?" test
# flipped 2026-07-30 from BLIND to SIGHTED as soon as a concurrent repair re-ran the level
# refresher at 18:57 ET -- 2 post-close ticks masked 776 blind RTH rows. On a healthy day
# levels are present from the premarket draw (~100%); levels landing a few minutes into the
# session still clear 0.5 easily, so this floor shouts at a half-blind session without ever
# crying wolf at a normal warm-up.
BLIND_SIGHTED_RATIO = 0.5

# Gamma_LevelRefresh's documented cadence is every 5 min (SCHEDULED-TASKS.md). 20 min = four
# consecutive missed refreshes -- unambiguous, with slack for scheduler/IO jitter so a healthy
# feed never cries wolf. Mirrors engine_health.LEVEL_FEED_STALE_MIN by design.
LEVELS_REFRESH_CADENCE_MIN = 5
LEVELS_FILE_STALE_MIN = 20
# The first intraday refresh needs RTH bars plus a beat to write; before this many minutes
# past the open, an un-rewritten file is warm-up, not a stall (same precedent as
# engine_health.LEVEL_FEED_WARMUP_MIN / WATCHER_OPEN_GRACE_MIN).
LEVELS_FILE_WARMUP_MIN = 12

# Assertion window for the DATE fields. The session date must be correct from the opening
# bell onward -- and CRUCIALLY it stays asserted after 15:55, because "the market is closed"
# is precisely the excuse that hid this outage. Before the bell the premarket/refresh chain
# may legitimately not have stamped today yet (premarket_readiness owns that window at 09:00).
SESSION_START_HHMM = 930

STATUS_SIGHTED = "SIGHTED"
STATUS_BLIND = "BLIND"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_INSUFFICIENT = "INSUFFICIENT"
STATUS_UNKNOWN = "UNKNOWN"

STATUS_FRESH = "FRESH"
STATUS_STALE = "STALE"

_EXIT = {
    STATUS_SIGHTED: 0, STATUS_NOT_APPLICABLE: 0, STATUS_INSUFFICIENT: 0, STATUS_FRESH: 0,
    STATUS_BLIND: 3, STATUS_STALE: 3, STATUS_UNKNOWN: 4,
}


def _is_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def _et_offset_hours(utc: dt.datetime) -> int:
    """EDT (UTC-4) from 2nd Sun Mar 02:00 local thru 1st Sun Nov 02:00 local; EST (UTC-5)
    otherwise. Copied verbatim from engine_health._et_offset_hours (system Python on this
    host lacks tzdata)."""
    y = utc.year
    march = dt.datetime(y, 3, 1, tzinfo=dt.timezone.utc)
    dst_start = (march + dt.timedelta(days=((6 - march.weekday()) % 7) + 7)).replace(hour=7)
    nov = dt.datetime(y, 11, 1, tzinfo=dt.timezone.utc)
    dst_end = (nov + dt.timedelta(days=(6 - nov.weekday()) % 7)).replace(hour=6)
    return -4 if (dst_start <= utc < dst_end) else -5


def mtime_as_et(path: Path) -> Optional[dt.datetime]:
    """A file's mtime as NAIVE ET wall-clock, or None if it cannot be stat'd.

    NEVER `datetime.fromtimestamp(mtime)` -- that returns naive LOCAL time and this rig runs
    MOUNTAIN (ET = local + 2), so a raw local mtime compared against a naive-ET `now` reports
    every file as 120 minutes FRESHER than it is, silently neutering a staleness check. The
    epoch is converted through aware-UTC and then offset, the same path et_clock takes.
    (Project scar: "TIME = et_clock, NEVER a naive local read".)"""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return None
    utc = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    return (utc + dt.timedelta(hours=_et_offset_hours(utc))).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Engine-parity expiry predicate
# ---------------------------------------------------------------------------

def level_expired(lv: Any, today_et: str) -> bool:
    """EXACT clone of `heartbeat_core._level_expired` -- date-only comparison, fail-open.

    Cloned rather than imported on purpose: importing heartbeat_core drags pandas + the
    whole live-engine sys.path graft into a fail-open monitor. The clone is pinned against
    the original by
    `backtest/tests/test_levels_blind_detection.py::test_expiry_predicate_matches_heartbeat_core`,
    so any drift in the engine's expiry rule REDs a guard instead of silently making this
    checker disagree with the consumer it is supposed to be watching (C14).
    """
    raw = lv.get("expires_at") if isinstance(lv, dict) else None
    if not raw:
        return False
    exp = str(raw)[:10]  # tolerate 'YYYY-MM-DD' or a full 'YYYY-MM-DDTHH:MM:SS'
    try:
        dt.datetime.strptime(exp, "%Y-%m-%d")
    except (TypeError, ValueError):
        return False  # unparseable -> fail open, keep the level
    return exp < today_et


def engine_visible_levels(data: Any, today_et: str) -> list:
    """The levels the LIVE engine would still see on `today_et`, using its own expiry rule.

    Deliberately does NOT apply heartbeat_core's `abs(price - spy) <= 12` proximity filter:
    spot moves all session, so proximity is a moment property, not a day property. Date
    expiry is what emptied the set on 2026-07-30 and it is a pure function of the file.
    """
    if not isinstance(data, dict):
        return []
    levels = data.get("levels") or data.get("key_levels") or []
    if not isinstance(levels, list):
        return []
    out = []
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        if level_expired(lv, today_et):
            continue
        price = lv.get("price") or lv.get("level") or lv.get("value")
        if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
            out.append(lv)
    return out


# ---------------------------------------------------------------------------
# Signal 1 -- CONSUMER side: did the engine's own rows carry levels?
# ---------------------------------------------------------------------------

def _in_rth(ts_et: str) -> bool:
    """True when a naive-ET 'YYYY-MM-DDTHH:MM:SS' stamp falls inside 09:30 <= t < 15:55."""
    try:
        hhmm = int(ts_et[11:13]) * 100 + int(ts_et[14:16])
    except (ValueError, IndexError):
        return False
    return SESSION_START_HHMM <= hhmm < 1555


def assess_rows(rows: list, day: str, min_rows: int = MIN_ROWS_FOR_VERDICT,
                blind_ratio: float = None) -> dict:
    """Pure assessor (no IO, testable). `rows` = decision dicts with ts_et/account/levels_active.

    SCOPED TO RTH (09:30-15:55), and judged on a RATIO -- both properties were learned the
    hard way while building this check. The first draft asked "did ANY row all day carry
    levels?" over the WHOLE day, and on 2026-07-30 it flipped from BLIND to SIGHTED the
    moment a concurrent repair re-ran the level refresher at 18:57 ET: TWO post-close ticks
    masked 776 blind RTH rows. A verdict about the trading session must be computed from the
    trading session, and one late sighted row is not sight.

    Ladder:
      * < min_rows RTH rows            -> INSUFFICIENT (warm-up / half session / holiday)
      * ZERO sighted RTH rows          -> BLIND ("total")   <- the 2026-07-30 signature
      * sighted fraction < blind_ratio -> BLIND ("partial") <- blind for most of the session
      * otherwise                      -> SIGHTED
    The ratio floor is what keeps this cry-wolf-safe: on a normal day levels are present from
    the premarket draw onward (~100% sighted), and levels landing a few minutes into the
    session still clears 0.5 comfortably. Never raises on a malformed row.
    """
    if blind_ratio is None:
        blind_ratio = BLIND_SIGHTED_RATIO
    rth_rows, by_acct = [], {}
    day_total = day_sighted = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        ts = str(r.get("ts_et", ""))
        if not ts.startswith(day):
            continue
        sighted = bool(r.get("levels_active"))
        day_total += 1
        day_sighted += int(sighted)
        if not _in_rth(ts):
            continue  # premarket / post-close ticks never vote on the session's verdict
        rth_rows.append(r)
        stats = by_acct.setdefault(str(r.get("account", "?")), {"n_total": 0, "n_sighted": 0})
        stats["n_total"] += 1
        stats["n_sighted"] += int(sighted)

    n_total = len(rth_rows)
    n_sighted = sum(1 for r in rth_rows if r.get("levels_active"))
    base = {"date": day, "n_total": n_total, "n_sighted": n_sighted, "accounts": by_acct,
            "n_total_all_day": day_total, "n_sighted_all_day": day_sighted}

    if n_total < min_rows:
        return {**base, "status": STATUS_INSUFFICIENT,
                "reason": f"only {n_total} RTH decision row(s) on {day} (< {min_rows}) -- "
                          "not enough evidence to call the day blind"}
    per_acct = "; ".join(f"{a} {s['n_sighted']}/{s['n_total']}" for a, s in sorted(by_acct.items()))
    tail = (" With no levels the engine cannot detect level rejections/reclaims and falls "
            "through to its WORST cohort (trendline-only). Check Gamma_LevelRefresh + "
            "key-levels.json expires_at dates.")
    if n_sighted == 0:
        return {**base, "status": STATUS_BLIND,
                "reason": f"ENGINE TRADED BLIND on {day} -- 0 of {n_total} RTH decision rows "
                          f"carried ANY active key level ({per_acct})." + tail}
    if n_sighted / n_total < blind_ratio:
        pct = 100.0 * n_sighted / n_total
        return {**base, "status": STATUS_BLIND,
                "reason": f"ENGINE MOSTLY BLIND on {day} -- only {n_sighted} of {n_total} RTH "
                          f"decision rows ({pct:.0f}%) carried an active key level "
                          f"({per_acct})." + tail}
    return {**base, "status": STATUS_SIGHTED,
            "reason": f"{n_sighted}/{n_total} RTH decision rows carried active levels on {day}"}


def _tail_rows(path: Path, day: str) -> Optional[list]:
    """Every JSON row of the decisions ledger stamped `day`, prefiltered on the date substring.

    STREAMS line-by-line rather than `readlines()` (which would materialise the whole ~31MB
    ledger 390x/day inside the every-minute beacon), and deliberately scans the FULL file
    rather than a byte-bounded tail so that back-dated queries -- daily_brief --date, an
    incident replay -- stay correct instead of silently reading INSUFFICIENT. Measured 0.06s
    on the live 31MB ledger. Returns None (-> UNKNOWN) only when the file cannot be opened;
    a garbled LINE is skipped, never fatal.
    """
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if day not in line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        return None
    return out


def check_day(day: str, path: Optional[Path] = None,
              min_rows: int = MIN_ROWS_FOR_VERDICT,
              blind_ratio: float = None) -> dict:
    """Blindness verdict for one ET date (YYYY-MM-DD). Never raises."""
    try:
        d = dt.date.fromisoformat(day)
    except (ValueError, TypeError):
        return {"date": day, "status": STATUS_UNKNOWN, "n_total": 0, "n_sighted": 0,
                "accounts": {}, "reason": f"unparseable date {day!r}"}
    if not _is_weekday(d):
        return {"date": day, "status": STATUS_NOT_APPLICABLE, "n_total": 0, "n_sighted": 0,
                "accounts": {}, "reason": "weekend -- no session expected"}
    rows = _tail_rows(path or CORE_DECISIONS, day)
    if rows is None:
        return {"date": day, "status": STATUS_UNKNOWN, "n_total": 0, "n_sighted": 0,
                "accounts": {}, "reason": "decision ledger unreadable"}
    try:
        return assess_rows(rows, day, min_rows, blind_ratio)
    except Exception as e:  # noqa: BLE001 -- fail-open: a broken assessor is never fatal
        return {"date": day, "status": STATUS_UNKNOWN, "n_total": 0, "n_sighted": 0,
                "accounts": {}, "reason": f"assessor failed ({type(e).__name__}: {e})"}


# ---------------------------------------------------------------------------
# Signal 2 -- PRODUCER side: is key-levels.json actually being rewritten?
# ---------------------------------------------------------------------------

def assess_levels_file(data: Any, mtime: Optional[dt.datetime], et: dt.datetime,
                       *, stale_min: float = LEVELS_FILE_STALE_MIN,
                       warmup_min: float = LEVELS_FILE_WARMUP_MIN) -> dict:
    """Pure assessor for key-levels.json freshness. `mtime` is the file's real modification
    time as NAIVE ET wall-clock (ground truth -- unlike the self-reported `as_of` string,
    which a half-failed writer can leave lying). `et` is naive ET now.

    NOT market-closed-suppressed on purpose. From 09:30 ET onward on a weekday the session
    date must be today, and it stays asserted after the close -- "the market is closed" is
    exactly the excuse that made 2026-07-30 invisible for a full day.
    """
    today = et.strftime("%Y-%m-%d")
    base: dict = {"date": today, "n_visible": 0, "file_date": None, "mtime_age_min": None}

    if not isinstance(data, dict):
        return {**base, "status": STATUS_UNKNOWN,
                "reason": "key-levels.json missing/unreadable/not an object"}

    file_date = str(data.get("for_session") or data.get("date") or "")[:10] or None
    other = str(data.get("date") or data.get("for_session") or "")[:10] or None
    age = None if mtime is None else max(0.0, (et - mtime).total_seconds() / 60.0)
    visible = engine_visible_levels(data, today)
    base = {"date": today, "n_visible": len(visible), "file_date": file_date,
            "mtime_age_min": None if age is None else round(age, 1)}

    if et.weekday() >= 5:
        return {**base, "status": STATUS_NOT_APPLICABLE,
                "reason": f"weekend -- level refresh idle (file dated {file_date})"}

    hhmm = et.hour * 100 + et.minute
    if hhmm < SESSION_START_HHMM:
        return {**base, "status": STATUS_FRESH,
                "reason": f"pre-open -- premarket refresh not yet due (file dated {file_date})"}

    # --- date fields: the 2026-07-30 signature, asserted right through the close ---
    if file_date != today:
        return {**base, "status": STATUS_STALE,
                "reason": f"STALE-DATED LEVEL FILE: key-levels.json is dated {file_date} != "
                          f"today {today} (mtime {base['mtime_age_min']}m ago). Every level in "
                          "it expires before today, so the engine's active level set is EMPTY. "
                          "Check Gamma_LevelRefresh's trigger."}
    if other and other != today:
        return {**base, "status": STATUS_STALE,
                "reason": f"INCONSISTENT LEVEL FILE DATES: for_session/date disagree "
                          f"({file_date} vs {other}) -- a half-written refresh"}

    # --- the file claims today: does the engine actually still see anything in it? ---
    if not visible:
        return {**base, "status": STATUS_STALE,
                "reason": f"LEVEL FILE DATED TODAY BUT EMPTY TO THE ENGINE: 0 of "
                          f"{len(data.get('levels') or [])} level(s) survive the engine's own "
                          "expiry rule -- levels_active will be [] every tick"}

    # --- mtime: ground-truth producer liveness during RTH, past the open warmup ---
    open_dt = et.replace(hour=9, minute=30, second=0, microsecond=0)
    mins_open = (et - open_dt).total_seconds() / 60.0
    in_rth = SESSION_START_HHMM <= hhmm < 1555
    if age is not None and in_rth and mins_open >= warmup_min and age > stale_min:
        return {**base, "status": STATUS_STALE,
                "reason": f"LEVEL FILE NOT REWRITTEN {age:.0f}m (> {stale_min:.0f}m, cadence "
                          f"{LEVELS_REFRESH_CADENCE_MIN}m) during RTH -- refresher stalled; "
                          f"{len(visible)} level(s) still visible but frozen"}

    return {**base, "status": STATUS_FRESH,
            "reason": f"dated today, {len(visible)} level(s) visible to the engine, "
                      f"rewritten {base['mtime_age_min']}m ago"}


def check_levels_file(et: dt.datetime, path: Optional[Path] = None, **kw) -> dict:
    """IO wrapper for assess_levels_file. Never raises."""
    p = path or KEY_LEVELS
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 -- missing/garbled/torn read -> UNKNOWN, never fatal
        data = None
    mtime = mtime_as_et(p)  # naive ET -- never a raw local fromtimestamp (see mtime_as_et)
    try:
        return assess_levels_file(data, mtime, et, **kw)
    except Exception as e:  # noqa: BLE001 -- fail-open
        return {"date": et.strftime("%Y-%m-%d"), "status": STATUS_UNKNOWN, "n_visible": 0,
                "file_date": None, "mtime_age_min": None,
                "reason": f"assessor failed ({type(e).__name__}: {e})"}


# ---------------------------------------------------------------------------
# Spoken/printable alarm for the EOD brief
# ---------------------------------------------------------------------------

def alarm_line(result: dict, file_result: Optional[dict] = None) -> Optional[str]:
    """ONE spoken line for the EOD brief, or None when nothing is wrong.

    Mirrors engine_liveness_check.alarm_line: plain speech, no jargon, no sugar-coating --
    J must hear "I was blind today" BEFORE he hears P&L.
    """
    st = (result or {}).get("status")
    if st == STATUS_BLIND:
        n = result.get("n_total", 0)
        why = ""
        if file_result and file_result.get("status") == STATUS_STALE:
            why = f" My levels file was still dated {file_result.get('file_date')}."
        return (f"Alarm. I traded blind on {result.get('date')}. Zero of my {n} decisions had a "
                f"single key level loaded.{why} No levels means no rejections or reclaims, so I "
                "fall back to my worst setup. Discount every entry from that day.")
    if st == STATUS_UNKNOWN:
        return f"I could not verify whether I had key levels loaded on {result.get('date')}."
    if file_result and file_result.get("status") == STATUS_STALE:
        return (f"Heads up. My key levels file is stale -- dated {file_result.get('file_date')}, "
                "last rewritten "
                f"{file_result.get('mtime_age_min')} minutes ago. The feed is not refreshing.")
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _et_today() -> dt.datetime:
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_now  # noqa: PLC0415 -- optional dep, fail-open below
        return et_now().replace(tzinfo=None)
    except Exception:  # noqa: BLE001 -- never let a clock import break the check
        return dt.datetime.now()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Did the engine trade blind (no key levels)?")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

    et = _et_today()
    day = a.date or et.strftime("%Y-%m-%d")
    rows_res = check_day(day)
    file_res = check_levels_file(et)
    if a.json:
        print(json.dumps({"rows": rows_res, "file": file_res}, indent=2))
    else:
        print(f"  levels_blind    {rows_res['status']:<14} "
              f"{rows_res['n_sighted']}/{rows_res['n_total']} rows sighted  {rows_res['reason']}")
        print(f"  levels_file     {file_res['status']:<14} "
              f"dated={file_res['file_date']} visible={file_res['n_visible']}  {file_res['reason']}")
        line = alarm_line(rows_res, file_res)
        if line:
            print(f"\n  ALARM: {line}")
    return max(_EXIT.get(rows_res["status"], 4), _EXIT.get(file_res["status"], 4))


if __name__ == "__main__":
    raise SystemExit(main())
