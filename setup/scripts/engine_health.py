"""Engine Health Beacon -- fuse every liveness signal into ONE verdict.

Phase 0a of the professional restructuring. Turns "fail-green" (components run
green but do nothing, surfacing only at EOD) into "fail-loud mid-day".

Reads EXISTING state only (adds NO new producers). Computes a single
GREEN / YELLOW / RED verdict and writes automation/state/engine-health.json
every fire. On a *transition into RED* (not every tick) appends one SOUL-voice
alert to the existing Discord outbox (automation/state/discord-outbox.jsonl) --
the bridge drains it idempotently. Outside RTH / weekends / holidays a quiet
engine reads GREEN (no crying wolf overnight).

Checks (critical ones gate RED during RTH):
  levels_blind                     -- engine's own rows carried ZERO active levels on a
                                      weekday (CRIT) -- the 2026-07-30 blind-session
                                      signature; NOT market_open-suppressed, on purpose
  levels_file_stale                -- key-levels.json mtime/session-date staleness, ground
                                      truth, asserted through the close (non-crit)
  heartbeat_safe / heartbeat_bold  -- loop-state last_change_at staleness (CRIT)
  watcher_feed                     -- newest observation date == today (CRIT):
                                      distinguishes "producer dark" from "no signal"
  tv_chart                         -- tv-watchdog-status freshness + cdp_up
  killswitch_safe / killswitch_bold-- circuit-breaker .tripped (CRIT if tripped)
  position_safe / position_bold    -- current-position*.json parseable

Idempotent + fail-safe: a missing state file is a YELLOW check, never a crash.
Pure stdlib. $0 cost. Per OP-27: paths anchored to __file__; pythonw stdio
redirect so a scheduled spawn never leaks a console window.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Repo layout anchors (OP-27: anchor to __file__, never bare relative)
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
AGG = STATE / "aggressive"
OUT_FILE = STATE / "engine-health.json"
OUTBOX = STATE / "discord-outbox.jsonl"
SOUL_FILE = REPO / "automation" / "presence" / "SOUL.md"

# Liveness budget during RTH: a heartbeat whose LOG has not produced an activity
# line in this many minutes is RED. Cadence is ~2-3 min; a tick can run up to the
# 280s (~4.7m) timeout, so 8 min covers one full slow tick + cadence + slack.
# NOTE: liveness is read from the LOG, NOT loop-state.last_change_at -- the loop
# legitimately leaves loop-state untouched on quiet/holding ticks (SKIP
# hash_unchanged + write-only-on-material-change), so loop-state mtime goes stale
# while the engine is alive and holding correctly (false-RED bug, 2026-06-22).
# 10m, not 8: worst-case log gap = 280s tick-timeout + ~3min cadence = ~7.67m, so
# 10m leaves ~2.3m slack vs ~20s at 8m (avoids false-RED under scheduler/IO jitter,
# which would re-introduce the very crying-wolf this rewrite removed). A real death
# (no log line) still REDs within 10m = ~3 missed ticks = unambiguously dead.
HEARTBEAT_STALE_MIN = 10
# --- New deterministic-engine liveness budgets (2026-06-26 repoint) -------------
# The LLM heartbeat was replaced by heartbeat_core (pure-Python, 1-min cadence) and
# the TV-CDP eye by sight_beacon (direct REST, 1-min). These checks watch the NEW
# producers -- core-decisions.jsonl (the brain) + sight-beacon.json (the eye) -- not
# the retired loop-state/LLM logs (which read "log missing" forever after the rebuild,
# pinning the monitor permanently YELLOW and blind to the real engine). Cadence is 1m,
# so 8 missed ticks = unambiguously dead while leaving slack for the veto-call latency
# + scheduler/IO jitter (avoids re-introducing false-RED).
CORE_STALE_MIN = 8
BEACON_STALE_MIN = 8
# A session's first bar cannot exist until it closes (~09:31 for 1m, ~09:35 for 5m) and
# the producer needs a beat to write it -- so watcher_feed must NOT cry "producer dark"
# in the first minutes after the open. This killed the recurring 09:30:02 false-RED (the
# canary fired 2s after the bell, before any today-bar could physically exist).
WATCHER_OPEN_GRACE_MIN = 11
# Map each heartbeat check to its log basename stem (date is appended per-day).
HEARTBEAT_LOG_STEM = {
    "heartbeat_safe": "heartbeat",
    "heartbeat_bold": "heartbeat_aggressive",
}
# TV watchdog writes ~every 5 min; flag if its own timestamp is older than this.
TV_STALE_MIN = 20

# Intraday level feed (2026-06-29): the ONLY shippable win of the 06-29 missed-setups
# mission. refresh_levels_intraday.py (Gamma_LevelRefresh, ~every 5 min during RTH) rewrites
# key-levels.json .as_of with live RTH high/low/swings so the engine isn't blind to intraday
# structure (the frozen-levels root cause that cost two J-readable setups). The fix is purely
# PRODUCER-side: _read_levels() rejects NO stale timestamp, so if the refresh task silently
# dies (reaped / un-scheduled / Alpaca error) the engine reads FROZEN levels again, undetected
# -- the exact regression, the C7 silent-rot class. This check surfaces it. NON-CRITICAL: a
# stale level feed degrades level-awareness but the engine still trades on ribbon/structure, so
# it must NEVER trade-halt -- it degrades the verdict to YELLOW and a genuine RTH stall returns
# RED *status* so the transition-only alerter pings J once. Refresh cadence is ~5 min, so 20m
# = 4 missed refreshes of slack (no cry-wolf); WARMUP guards the open (the first refresh needs
# RTH bars + a beat to write, like watcher_feed's open grace).
LEVEL_FEED_STALE_MIN = 20
LEVEL_FEED_WARMUP_MIN = 12

# Extra-setup dispatch health (2026-06-29): the setup_dispatch layer feeds the validated-
# but-mostly-dormant detectors (vwap_continuation edge #1, gap_and_go, ...). It silently
# returned None on EVERY tick for an extended period -- the G16 _build_ctx ImportError --
# and that blindness was INVISIBLE until a manual observe-live caught it 2026-06-27. This
# check graduates that manual ritual into an automated guard: when an extra-setup detector
# flag is ENABLED in an account's params, the live decisions MUST carry extra_signals on
# that account's ticks. Enabled-but-ZERO over a populated RTH is the EXACT G16 silent-
# dispatch-death signature. NON-CRITICAL (research/observability path, never a live-trade
# gate) + fail-open. RED only on the unambiguous zero-with-sufficient-ticks case (no
# partial-ratio YELLOW -> avoids false alarms during open warmup / short sessions).
DISPATCH_FLAGS = (
    "j_vwap_cont_enabled", "gap_and_go_enabled",
    "j_vwap_reclaim_fb_enabled", "j_vix_dayside_enabled",
    "db_base_quiet_enabled",
)
# An RTH must have produced at least this many ticks before "zero extra_signals" is
# unambiguously a silent death (vs a just-opened or holiday-short session). A full RTH is
# ~380 ticks/account; 30 = the first ~30 min, well past dispatch warmup.
DISPATCH_MIN_TICKS = 30
# Bound the tail read so the every-minute beacon never parses an unbounded ledger.
# ~2 full trading days/account at ~380 ticks each x2 accounts = headroom for the latest RTH.
DISPATCH_TAIL_LINES = 2500

# GEX OI archive continuity (2026-06-29): the months-long dealer-positioning accrual
# (Gamma_CboeOiBank, daily 15:55 ET -> journal/gex-archive/) is the 'class'-rung data
# engine. It can die SILENTLY (un-scheduled / reaped / CBOE format change) and only be
# discovered months later as a gap-riddled, backtest-worthless archive (C7 silent-failure).
# assess_archive_continuity already encodes the GREEN/YELLOW/RED ladder + a synthetic-fixture
# guard, but nothing RAN it against the LIVE archive on a schedule -- so this check wires the
# checker into the every-minute health beacon. It is NON-CRITICAL by design: a stalled RESEARCH
# accrual must NEVER trade-halt nor flip the critical engine verdict RED (it can only degrade to
# YELLOW), but a genuine multi-day stall returns RED status so the transition-only alerter pings
# J exactly once (the silent-accrual-death surfaced -- J's #1 gap is visibility).
REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# DST / ET helpers (copied verbatim from session_guard.py convention -- system
# Python on this host lacks tzdata, so we compute the US offset by hand).
# ---------------------------------------------------------------------------

def _et_offset_hours(dt_utc: datetime) -> int:
    """EDT (UTC-4) from 2nd Sun Mar 02:00 local thru 1st Sun Nov 02:00 local;
    EST (UTC-5) otherwise."""
    y = dt_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start <= dt_utc < dst_end) else -5


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _et_now(now_utc: Optional[datetime] = None) -> datetime:
    """Current ET wall clock as a NAIVE datetime (for display + gating)."""
    now_utc = now_utc or _now_utc()
    return (now_utc + timedelta(hours=_et_offset_hours(now_utc))).replace(tzinfo=None)


# pythonw stdio redirect (OP-27 L41 layer 3) -- after _et_now is defined.
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _logs = STATE / "logs"
    _logs.mkdir(parents=True, exist_ok=True)
    _stamp = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_logs / f"engine-health-{_stamp}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_logs / f"engine-health-{_stamp}.stderr.log", "a", buffering=1, encoding="utf-8")


# ---------------------------------------------------------------------------
# Market-hours model
# ---------------------------------------------------------------------------

def _refresh_calendar_from_alpaca(cal_path: Path, year: int) -> bool:
    """Rebuild calendar.json from the real Alpaca /v2/calendar for `year`. Pure
    stdlib (urllib), $0, fail-open -- any error just leaves the stale/absent
    file alone so the caller falls back to its existing (possibly empty) set.

    WHY THIS EXISTS (2026-07-03 incident): calendar.json never had a producer,
    so _load_holidays() silently returned {} forever -- market_is_open() then
    used pure weekday+clock logic and called the 2026-07-03 holiday (July 4th
    observed) a live trading day. The engine correctly stayed flat (all HOLD),
    but engine-health/self-check false-RED'd on watcher_feed staleness and the
    heartbeat ticked all morning scoring a frozen tape for nothing. Self-healed
    here (not via the LLM premarket persona) to stay pure-Python / $0."""
    import urllib.error
    import urllib.request

    secrets_path = REPO / "automation" / "state" / "fleet" / "secrets.json"
    try:
        secrets = json.loads(secrets_path.read_text(encoding="utf-8"))
        accounts = secrets.get("accounts", secrets)
        creds = next(
            (c for c in accounts.values() if isinstance(c, dict) and (c.get("key") or c.get("api_key"))),
            None,
        )
        if not creds:
            return False
        key = creds.get("key") or creds.get("api_key")
        secret = creds.get("secret") or creds.get("secret_key")
        base = (creds.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
        req = urllib.request.Request(
            f"{base}/v2/calendar?start={year}-01-01&end={year}-12-31",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 -- fixed https host
            days = json.loads(resp.read())
        open_dates = {d["date"] for d in days}
        d = datetime(year, 1, 1)
        end = datetime(year, 12, 31)
        holidays = []
        while d <= end:
            if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in open_dates:
                holidays.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
        cal_path.write_text(json.dumps({
            "source": "alpaca_v2_calendar", "fetched_at_et": _et_now().isoformat(),
            "year_range": [f"{year}-01-01", f"{year}-12-31"], "holidays": sorted(holidays),
        }, indent=2), encoding="utf-8")
        return True
    except (OSError, urllib.error.URLError, KeyError, ValueError, StopIteration):
        return False


def _load_holidays() -> set:
    """Read automation/state/calendar.json .holidays[] (ISO yyyy-mm-dd), self-healing
    the cache if it's absent or stale for the current year (see
    _refresh_calendar_from_alpaca). Matches _shared.ps1 Test-HolidayFromAlpaca's
    contract: any remaining failure -> empty set (never blocks the health check)."""
    cal = STATE / "calendar.json"
    year = _et_now().year
    try:
        data = json.loads(cal.read_text(encoding="utf-8"))
        holidays = {str(d) for d in data.get("holidays", [])}
        year_range = data.get("year_range") or ["", ""]
        if not any(str(year) in str(v) for v in year_range):
            raise ValueError("calendar.json stale for current year")
        return holidays
    except Exception:
        if _refresh_calendar_from_alpaca(cal, year):
            try:
                data = json.loads(cal.read_text(encoding="utf-8"))
                return {str(d) for d in data.get("holidays", [])}
            except Exception:
                return set()
        return set()


def market_is_open(et: datetime) -> bool:
    """True during RTH: Mon-Fri, 09:30 <= ET < 15:55, not a known holiday."""
    if et.weekday() >= 5:  # Sat/Sun
        return False
    if et.strftime("%Y-%m-%d") in _load_holidays():
        return False
    hhmm = et.hour * 100 + et.minute
    return 930 <= hhmm < 1555


def _minutes_since_open(et: datetime) -> float:
    """Minutes since today's 09:30 ET open (negative before the bell). et is naive ET."""
    open_dt = et.replace(hour=9, minute=30, second=0, microsecond=0)
    return (et - open_dt).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# State readers (fail-safe: missing/garbled file -> (None, reason))
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> tuple[Optional[dict], Optional[str]]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except Exception as e:  # noqa: BLE001 -- never crash the beacon
        return None, f"unparseable ({type(e).__name__})"


def _parse_ts(val: Any) -> Optional[datetime]:
    """Parse an ISO timestamp (with optional Z / offset) to aware UTC, or epoch int."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(val).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_min(dt: Optional[datetime], now_utc: datetime) -> Optional[float]:
    if dt is None:
        return None
    return (now_utc - dt).total_seconds() / 60.0


def _chk(name: str, status: str, detail: str, critical: bool = False) -> dict:
    return {"name": name, "status": status, "detail": detail, "critical": critical}


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

# Line-start activity stamp: "YYYY-MM-DD HH:MM:SS ET <MARKER...>". Every loop
# event (=== START/END tick, FIRE, SKIP, REAPED, POST_RECOVERY, LOCK_BUSY,
# TIMEOUT, BAR) writes one of these, so ANY such line proves the loop was alive
# at that wall-clock minute -- including quiet SKIP-hash-unchanged holds.
_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ET\b")


def _newest_log_activity_et(stem: str, et: datetime) -> tuple[Optional[datetime], Optional[str]]:
    """Return (newest_activity_as_naive_ET, error). Reads automation/state/logs/
    {stem}-{today}.log, tail-scans for the freshest line that starts with the ET
    timestamp pattern. The log timestamps are naive ET wall-clock (no offset)."""
    path = STATE / "logs" / f"{stem}-{et.strftime('%Y-%m-%d')}.log"
    if not path.exists():
        return None, "log missing"
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, 131072)  # tail 128KB -- many lines, cheap
            f.seek(size - block)
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001 -- never crash the beacon
        return None, f"log read error ({type(e).__name__})"
    for raw in reversed(tail):
        m = _LOG_TS_RE.match(raw.lstrip("﻿").strip())
        if m:
            try:
                # Naive ET wall-clock -- compare against _et_now() (also naive ET).
                return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), None
            except ValueError:
                continue
    return None, "no activity line in tail"


def check_heartbeat(name: str, path: Path, market_open: bool, now_utc: datetime) -> dict:
    """Liveness from the LOG (freshest activity line); CONTENT (mode/ticks) from
    loop-state. The two are decoupled because the loop intentionally leaves
    loop-state unchanged on quiet holding ticks -- so loop-state staleness is NOT
    death (2026-06-22 false-RED root cause)."""
    et = _et_now(now_utc)

    # --- CONTENT (mode / ticks) from loop-state; non-fatal if absent ---
    data, err = _read_json(path)
    if data is not None:
        content = f"mode={data.get('current_mode')}; ticks={data.get('ticks_today')}"
    else:
        content = f"loop-state {err}"

    # --- LIVENESS from the heartbeat log ---
    stem = HEARTBEAT_LOG_STEM.get(name, "heartbeat")
    last_act, log_err = _newest_log_activity_et(stem, et)

    if last_act is None:
        # No log evidence. After close this is fine (quiet); during RTH it is a
        # YELLOW (can't prove liveness, but don't trade-halt on a missing log
        # alone -- loop-state content may still be valid). A missing log during
        # RTH with no other signal is worth surfacing but not crit-RED.
        if not market_open:
            return _chk(name, "GREEN", f"{content} ({log_err}; market closed -- quiet OK)", critical=True)
        return _chk(name, "YELLOW", f"liveness unknown ({log_err}) during RTH -- {content}", critical=False)

    age = (et - last_act).total_seconds() / 60.0
    detail = f"log activity {age:.1f}m ago; {content}"
    if not market_open:
        return _chk(name, "GREEN", f"{detail} (market closed -- quiet OK)", critical=True)
    if age > HEARTBEAT_STALE_MIN:
        return _chk(name, "RED", f"NO LOG ACTIVITY {age:.1f}m (>{HEARTBEAT_STALE_MIN}m) during RTH -- {detail}", critical=True)
    return _chk(name, "GREEN", detail, critical=True)


def check_session_ran(et: datetime) -> dict:
    """DID THE ENGINE RUN TODAY? -- the check that was missing on 2026-07-24.

    Every other check in this file takes `market_open`, a RIGHT-NOW boolean, and suppresses
    itself to "GREEN (market closed -- quiet OK)" when it is False. On 2026-07-24 the machine was
    off all day; by the time anything evaluated, the market had closed, so EVERY check suppressed
    and the fused verdict read GREEN 13/13 on a day the engine logged **zero** ticks. A dead
    engine and a closed market were literally indistinguishable.

    This check asks about the DAY, not the moment: on a weekday, did core-decisions.jsonl record
    a real session? It is deliberately NOT market_open-suppressed -- that suppression is the bug.
    Evaluated only after the session is over (>= 16:05 ET) so a mid-morning run doesn't cry wolf.
    """
    name = "session_ran"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from engine_liveness_check import (STATUS_DID_NOT_RUN, STATUS_PARTIAL,
                                           STATUS_UNKNOWN, check_day)
    except Exception as e:  # noqa: BLE001 -- never let this check break the report
        return _chk(name, "YELLOW", f"liveness module unavailable ({e})", critical=False)

    day = et.strftime("%Y-%m-%d")
    if et.weekday() >= 5:
        return _chk(name, "GREEN", f"{day} is a weekend -- no session expected", critical=False)
    if et.hour < 16:
        return _chk(name, "GREEN", f"{day} session not finished yet -- checked after 16:05 ET",
                    critical=False)

    res = check_day(day)
    st = res.get("status")
    if st == STATUS_DID_NOT_RUN:
        return _chk(name, "RED",
                    f"ENGINE DID NOT RUN {day} -- ZERO ticks on a weekday "
                    "(machine off / tasks dead / market holiday)", critical=True)
    if st == STATUS_PARTIAL:
        return _chk(name, "YELLOW",
                    f"{day} only {res.get('ticks')} ticks -- engine down for part of the session",
                    critical=False)
    if st == STATUS_UNKNOWN:
        return _chk(name, "YELLOW", f"{day} liveness unverifiable: {res.get('reason')}",
                    critical=False)
    return _chk(name, "GREEN", f"{day} session ran ({res.get('ticks')} ticks)", critical=True)


def _import_levels_blind():
    """Import setup/scripts/levels_blind_check.py, or None. Fail-open (mirrors
    check_session_ran's engine_liveness_check import)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import levels_blind_check  # noqa: PLC0415 -- optional dep, callers fail open
        return levels_blind_check
    except Exception:  # noqa: BLE001 -- never let a monitor import break the beacon
        return None


def check_levels_blind(et: datetime) -> dict:
    """DID THE ENGINE SEE ANY LEVELS TODAY? -- the check that was missing on 2026-07-30.

    On 2026-07-30 all 772 core decision rows carried `levels_active: []` because
    key-levels.json had not been rewritten since 2026-07-29 and every level in it had
    expired. The engine did not halt or warn -- it silently switched to trendline-only
    entries (its worst cohort) and fired 11 ENTER_BEAR verdicts at the LOW of the day.
    `check_level_feed` below stayed quiet the entire time: it is market_open-suppressed,
    so after 15:55 it read "market closed -- refresh idle, quiet OK".

    Like `check_session_ran`, this check asks about the DAY, not the moment, and is
    DELIBERATELY NOT market_open-suppressed -- that suppression is the bug. It reads the
    CONSUMER side (what the engine's own rows say it saw), so it is true regardless of
    which producer, cache, or expiry rule emptied the set.

    critical=True on a genuine blind day: this is the same severity class as
    `session_ran` (an engine that ran blind is no better than one that did not run), and
    engine-health.json is NOT on the heartbeat's read path -- verified 2026-07-30, the
    only consumers are self_check/gym_session/gamma_status/open_bell_status/crypto_twin_
    health/handoff_paul/daily_brief plus the conductor+healer PowerShell -- so critical
    here drives the fused verdict and the alerter, and can never trade-halt the engine.
    Fail-open: any import/read/assess failure degrades to a benign YELLOW.
    """
    name = "levels_blind"
    mod = _import_levels_blind()
    if mod is None:
        return _chk(name, "YELLOW", "levels_blind_check module unavailable", critical=False)
    day = et.strftime("%Y-%m-%d")
    try:
        res = mod.check_day(day)
    except Exception as e:  # noqa: BLE001 -- a broken checker must never break the report
        return _chk(name, "YELLOW", f"blindness assess failed ({type(e).__name__})", critical=False)
    st = res.get("status")
    if st == mod.STATUS_BLIND:
        return _chk(name, "RED", res.get("reason", "engine traded blind"), critical=True)
    if st == mod.STATUS_NOT_APPLICABLE:
        return _chk(name, "GREEN", f"{day} is a weekend -- no session expected", critical=False)
    if st == mod.STATUS_INSUFFICIENT:
        return _chk(name, "GREEN", res.get("reason", "insufficient rows"), critical=False)
    if st == mod.STATUS_UNKNOWN:
        return _chk(name, "YELLOW", f"{day} level-sight unverifiable: {res.get('reason')}",
                    critical=False)
    return _chk(name, "GREEN", res.get("reason", "levels visible"), critical=True)


def check_levels_file_stale(et: datetime) -> dict:
    """IS key-levels.json ACTUALLY BEING REFRESHED? -- the PRODUCER-side half of the
    2026-07-30 repair, and deliberately distinct from `check_level_feed` below:

      * check_level_feed  -- reads the SELF-REPORTED `as_of` string, RTH-only, and goes
                             "GREEN (market closed -- refresh idle, quiet OK)" outside RTH.
      * this check        -- reads the file's real MTIME (ground truth) plus the `date` /
                             `for_session` fields the refresher itself stamps, and stays
                             ASSERTED from 09:30 ET right through the close on a weekday.
                             At 18:45 ET on 2026-07-30 it REDs; check_level_feed reads GREEN.

    It also runs the levels through the ENGINE'S OWN expiry predicate, so a file that is
    dated today but whose every level expired yesterday (parses fine, engine sees nothing)
    is caught too. NON-CRITICAL: a producer-side stall degrades level-awareness but must
    never trade-halt (same stance as check_level_feed); a genuine stall still returns RED
    *status* so the transition-only alerter pings J once. Fail-open on everything else."""
    name = "levels_file_stale"
    mod = _import_levels_blind()
    if mod is None:
        return _chk(name, "YELLOW", "levels_blind_check module unavailable", critical=False)
    try:
        res = mod.check_levels_file(et)
    except Exception as e:  # noqa: BLE001
        return _chk(name, "YELLOW", f"levels-file assess failed ({type(e).__name__})", critical=False)
    st = res.get("status")
    if st == mod.STATUS_STALE:
        return _chk(name, "RED", res.get("reason", "key-levels.json stale"), critical=False)
    if st == mod.STATUS_UNKNOWN:
        return _chk(name, "YELLOW", f"level file unverifiable: {res.get('reason')}", critical=False)
    return _chk(name, "GREEN", res.get("reason", "level file fresh"), critical=False)


def check_watcher_feed(market_open: bool, et: datetime) -> dict:
    """Producer-dark detector: newest watcher-observations bar date must be today.
    This is the bug that blinded the fleet -- a dark producer looks identical to
    'no signal' unless you check the freshest row's date."""
    path = STATE / "watcher-observations.jsonl"
    if not path.exists():
        return _chk("watcher_feed", "YELLOW", "watcher-observations.jsonl missing", critical=False)
    newest: Optional[str] = None
    try:
        # Read the last non-empty line; tolerate big files via tail-read.
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, 65536)
            f.seek(size - block)
            tail = f.read().decode("utf-8", errors="replace").splitlines()
        for raw in reversed(tail):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            bt = row.get("bar_timestamp_et")
            if bt:
                newest = str(bt)
                break
    except Exception as e:  # noqa: BLE001
        return _chk("watcher_feed", "YELLOW", f"read error ({type(e).__name__})", critical=False)
    if newest is None:
        return _chk("watcher_feed", "YELLOW", "no bar_timestamp_et in tail", critical=False)
    newest_date = newest[:10]
    today = et.strftime("%Y-%m-%d")
    if not market_open:
        return _chk("watcher_feed", "GREEN", f"newest bar {newest_date} (market closed -- quiet OK)", critical=True)
    if newest_date == today:
        return _chk("watcher_feed", "GREEN", f"producing TODAY's rows (newest bar {newest})", critical=True)
    # Post-open grace (2026-06-26): the first session bar cannot physically exist in the
    # first minutes after the bell, so "newest != today" here is warm-up, not a dark
    # producer. This kills the recurring 09:30:02 cry-wolf RED (fired 2s after the open)
    # WITHOUT weakening the canary past the grace window -- the re-arm guard test runs at
    # 11:00 ET (90m in), well clear of WATCHER_OPEN_GRACE_MIN.
    mins_open = _minutes_since_open(et)
    if 0 <= mins_open < WATCHER_OPEN_GRACE_MIN:
        return _chk(
            "watcher_feed", "YELLOW",
            f"warming up {mins_open:.1f}m into open (newest bar {newest_date}) -- first session bar not written yet",
            critical=False,
        )
    # critical=True (RE-ARMED 2026-06-24): the 2026-06-22 downgrade to critical=False
    # was a DELIBERATE TEMPORARY measure to stop cry-wolf overall-REDs every market open
    # while the watcher_live.py producer rebuild was in flight (the morning no-op =
    # naive-local-time gate [rig is MT, not ET] + the yfinance top-up / stale_csv_date
    # stack -- C6/L161). That rebuild is now COMPLETE + CONFIRMED: ET-gate fix (3e8ed79),
    # load_data total-darkness fix (57cef40), end-to-end integration guard (2eceac1).
    # 2026-06-24 RTH produced FULL 09:30-15:55 ET coverage (154 diag + 78 obs rows, every
    # ET hour 09..15, ZERO crash/darkness signals) -- the exact re-arm condition the old
    # comment named. NOTE: engine-health.json is NOT consumed by the heartbeat (verified
    # 2026-06-24: only the conductor STAGE-0 backpressure, the alerter, the healer, and
    # gym_session.py read it), so critical=True does NOT trade-halt the engine -- it only
    # drives the overall verdict RED so a genuine producer-dark gates feature-build
    # backpressure + stays loud, exactly as intended for THE producer-dark canary.
    # See STATUS.md "WATCHER-FEED-REARM-CONFIRM" + L161/C6.
    return _chk(
        "watcher_feed", "RED",
        f"PRODUCER DARK: newest bar {newest_date} != today {today} -- feed not writing during RTH",
        critical=True,
    )


def check_sight_beacon(market_open: bool, now_utc: datetime) -> dict:
    """The EYE: sight-beacon.json must be fresh during RTH. A stale/failed beacon means
    the engine is BLIND -- the #1 forbidden state (J: 'the engine can NOT be blind ever').
    Replaces the retired TV-CDP tv_chart eye: heartbeat_core reads bars via direct REST,
    so the beacon's freshness + ok-flag is the real sight liveness now."""
    name = "sight_beacon"
    data, err = _read_json(STATE / "sight-beacon.json")
    if data is None:
        # Missing during RTH is a genuine blind-spot (critical); quiet when closed.
        return _chk(name, "RED" if market_open else "YELLOW",
                    f"sight-beacon.json {err}", critical=market_open)
    age = _age_min(_parse_ts(data.get("ts_utc")), now_utc)
    spy = data.get("spy", "?")
    rib = data.get("ribbon_stack", "?")
    src = data.get("data_source", "?")
    if age is None:
        return _chk(name, "YELLOW", "no ts_utc in beacon", critical=False)
    detail = f"eye {age:.1f}m old; spy={spy} ribbon={rib} src={src}"
    if not market_open:
        return _chk(name, "GREEN", f"{detail} (market closed -- quiet OK)", critical=True)
    if data.get("ok") is False:
        return _chk(name, "RED", f"BLIND: beacon ok=False (fetch failed) -- {detail}", critical=True)
    if age > BEACON_STALE_MIN:
        return _chk(name, "RED",
                    f"BLIND: eye STALE {age:.1f}m (>{BEACON_STALE_MIN}m) during RTH -- {detail}",
                    critical=True)
    return _chk(name, "GREEN", detail, critical=True)


def check_engine_core(name: str, account: str, market_open: bool, et: datetime) -> dict:
    """The BRAIN: heartbeat_core writes one core-decisions.jsonl row per account every
    ~1-min tick (even on HOLD), so a stale newest-row for an account means the
    deterministic engine stopped ticking. Replaces the LLM-era loop-state.json liveness
    (which now reads 'log missing' against the disabled Gamma_Heartbeat logs). ts_et is
    naive ET wall-clock -- compared against et (also naive ET)."""
    path = STATE / "core-decisions.jsonl"
    if not path.exists():
        return _chk(name, "RED" if market_open else "YELLOW",
                    "core-decisions.jsonl missing", critical=market_open)
    newest: Optional[str] = None
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 131072))  # tail 128KB -- many ticks, cheap
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001 -- never crash the beacon
        return _chk(name, "YELLOW", f"read error ({type(e).__name__})", critical=False)
    for raw in reversed(tail):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if row.get("account") == account and row.get("ts_et"):
            newest = str(row["ts_et"])
            break
    if newest is None:
        return _chk(name, "RED" if market_open else "YELLOW",
                    f"no {account} row in tail", critical=market_open)
    try:
        dt = datetime.strptime(newest[:19], "%Y-%m-%dT%H:%M:%S")  # naive ET
    except ValueError:
        return _chk(name, "YELLOW", f"unparseable ts_et {newest!r}", critical=False)
    age = (et - dt).total_seconds() / 60.0
    detail = f"last {account} tick {age:.1f}m ago ({newest[11:19]})"
    if not market_open:
        return _chk(name, "GREEN", f"{detail} (market closed -- quiet OK)", critical=True)
    if age > CORE_STALE_MIN:
        return _chk(name, "RED",
                    f"ENGINE STALE {age:.1f}m (>{CORE_STALE_MIN}m) during RTH -- {detail}",
                    critical=True)
    return _chk(name, "GREEN", detail, critical=True)


def check_tv_chart(now_utc: datetime) -> dict:
    path = STATE / "tv-watchdog-status.json"
    data, err = _read_json(path)
    if data is None:
        return _chk("tv_chart", "YELLOW", f"tv-watchdog-status {err}", critical=False)
    cdp_up = bool(data.get("cdp_up"))
    action = data.get("tv_action", "?")
    age = _age_min(_parse_ts(data.get("ts")), now_utc)
    age_s = f"{age:.1f}m" if age is not None else "?"
    if not cdp_up:
        return _chk("tv_chart", "YELLOW", f"CDP down; action={action}; status age {age_s}", critical=False)
    if age is not None and age > TV_STALE_MIN:
        return _chk("tv_chart", "YELLOW", f"watchdog status stale {age_s} (>{TV_STALE_MIN}m); action={action}", critical=False)
    return _chk("tv_chart", "GREEN", f"cdp_up; action={action}; status age {age_s}", critical=False)


def check_killswitch(name: str, path: Path) -> dict:
    data, err = _read_json(path)
    if data is None:
        return _chk(name, "YELLOW", f"circuit-breaker {err}", critical=False)
    tripped = bool(data.get("tripped"))
    if tripped:
        reason = data.get("tripped_reason") or data.get("trip_reason") or "unspecified"
        return _chk(name, "RED", f"KILL-SWITCH TRIPPED: {reason}", critical=True)
    return _chk(name, "GREEN", "armed, not tripped", critical=True)


# Per-account breaker date-field (mirrors daily_loss_guard.py ACCOUNTS -- see that file's
# docstring for the C9 symmetry trap: the two breakers use fully divergent field names).
BREAKER_DATE_FIELD = {
    "breaker_rearm_safe": "last_reset",   # ISO datetime, e.g. "2026-07-08T08:31:00-04:00"
    "breaker_rearm_bold": "session_id",   # bare date, e.g. "2026-07-08"
}


def check_breaker_rearm(name: str, path: Path, date_field: str, market_open: bool, et: datetime) -> dict:
    """Re-armed-TODAY canary (2026-07-09 incident). check_killswitch only ever asks
    "tripped?" -- it says nothing about whether today's start-of-day equity baseline is
    even fresh. Root cause 2026-07-09: the premarket LLM run (historically the only writer
    of starting_equity_today/equity_start_of_day) failed both attempts because its
    claude-code-router dependency (~/.claude/settings.json env/apiKeyHelper ->
    127.0.0.1:3456) was down (ConnectionRefused; confirmed dead PID + no listener on
    3456-3459) -- so both breakers kept 2026-07-08's SoD equity while the engine traded
    2026-07-09 against a stale baseline, and killswitch_safe/killswitch_bold read GREEN
    throughout ("armed, not tripped" is silent on staleness). daily_loss_guard.rearm() now
    closes the write-side gap deterministically (LLM/CCR-independent); THIS check is the
    read-side defense-in-depth net in case that rearm doesn't run either (task
    unregistered, Alpaca REST down, reverted, etc.) -- never rely on a single layer.

    NON-CRITICAL by design (mirrors level_feed/gex_archive/dispatch_health): a stale re-arm
    degrades the kill-switch's accuracy but must never itself trade-halt -- only a genuine
    .tripped=True (check_killswitch) does that. A genuine staleness still returns RED
    *status* so the transition-only alerter (maybe_alert) pings J once. Market-closed ->
    GREEN (quiet OK; nothing has re-armed yet outside RTH by design). Fail-open: any
    read/parse error, or a non-dict payload, is a benign YELLOW -- never crashes the beacon
    or flips the overall verdict."""
    try:
        data, err = _read_json(path)
        if data is None:
            return _chk(name, "YELLOW", f"circuit-breaker {err}", critical=False)
        if not isinstance(data, dict):
            return _chk(name, "YELLOW", "circuit-breaker payload is not an object", critical=False)
        raw_date = data.get(date_field)
        bdate = str(raw_date)[:10] if raw_date else None
        today = et.strftime("%Y-%m-%d")
        if not market_open:
            return _chk(name, "GREEN", f"{date_field}={bdate} (market closed -- quiet OK)", critical=False)
        if bdate is None:
            return _chk(name, "RED", f"NOT RE-ARMED: {date_field} missing from breaker", critical=False)
        if bdate != today:
            return _chk(
                name, "RED",
                f"STALE RE-ARM: {date_field}={bdate} != today {today} -- kill-switch anchored "
                f"to a stale start-of-day equity (premarket did not re-arm today; check "
                f"daily_loss_guard.rearm + claude-code-router :3456)",
                critical=False,
            )
        return _chk(name, "GREEN", f"{date_field}={bdate} (re-armed today)", critical=False)
    except Exception as e:  # noqa: BLE001 -- never let this check break the beacon
        return _chk(name, "YELLOW", f"breaker-rearm check failed ({type(e).__name__})", critical=False)


def check_gex_archive(et: datetime) -> dict:
    """Continuity of the GEX OI accrual (the 'class'-rung data engine). NON-CRITICAL:
    a stalled research accrual must never trade-halt nor RED the critical verdict -- it
    degrades to YELLOW at most, and a genuine multi-day stall returns RED *status* so the
    transition-only alerter pings J once. Fail-open: any import/read error is a benign
    YELLOW (never crashes the beacon, never pings). as_of = the ET date (rig is MT, so the
    naive ET date, NOT the system-local date, defines 'owed'); expect_today=False so a
    not-yet-captured today is never falsely flagged."""
    name = "gex_archive"
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from backtest.tools.gex_archive_health import assess_archive_continuity
    except Exception as e:  # noqa: BLE001 -- never let a research checker break the beacon
        return _chk(name, "YELLOW", f"continuity checker unavailable ({type(e).__name__})", critical=False)
    try:
        r = assess_archive_continuity(as_of=et.date(), expect_today=False)
    except Exception as e:  # noqa: BLE001
        return _chk(name, "YELLOW", f"continuity assess failed ({type(e).__name__})", critical=False)
    status = r.get("status", "YELLOW")
    if status not in ("GREEN", "YELLOW", "RED"):
        status = "YELLOW"
    days = r.get("days_accrued")
    latest = r.get("latest_session")
    detail = f"{r.get('reason', '?')} ({days} sessions, latest {latest})"
    # NON-CRITICAL always: research-data continuity, never a live-trade gate.
    return _chk(name, status, detail, critical=False)


def check_level_feed(market_open: bool, et: datetime) -> dict:
    """Freshness of the intraday level feed (key-levels.json .as_of). NON-CRITICAL: a stale
    feed degrades the engine's level-awareness (the frozen-levels root cause) but never
    trade-halts -- it can only degrade the verdict to YELLOW, and a genuine RTH stall returns
    RED *status* so the transition-only alerter pings J once. .as_of is naive ET wall-clock
    (refresh writes %Y-%m-%dT%H:%M:%S with a literal -04:00 suffix), so parse as_of[:19] and
    compare to et (also naive ET) -- the et_clock-consistent read, NOT _parse_ts (the -04:00
    literal is wrong on the MT/DST rig and ignored). Fail-open: missing/garbled/unparseable
    -> benign YELLOW, never crashes the beacon. Market-closed or pre-warmup -> GREEN (the
    refresh only runs during RTH; a stale as_of overnight or in the first minutes is expected)."""
    name = "level_feed"
    data, err = _read_json(STATE / "key-levels.json")
    if data is None:
        return _chk(name, "YELLOW", f"key-levels.json {err}", critical=False)
    as_of = data.get("as_of")
    if not isinstance(as_of, str) or len(as_of) < 19:
        return _chk(name, "YELLOW", "no parseable as_of", critical=False)
    try:
        dt = datetime.strptime(as_of[:19], "%Y-%m-%dT%H:%M:%S")  # naive ET wall-clock
    except ValueError:
        return _chk(name, "YELLOW", f"unparseable as_of {as_of!r}", critical=False)
    age = (et - dt).total_seconds() / 60.0
    detail = f"as_of {as_of[11:19]} ({age:.1f}m old)"
    if not market_open:
        return _chk(name, "GREEN", f"{detail} (market closed -- refresh idle, quiet OK)", critical=True)
    if _minutes_since_open(et) < LEVEL_FEED_WARMUP_MIN:
        return _chk(name, "GREEN", f"{detail} (open warmup -- first refresh pending)", critical=True)
    if age > LEVEL_FEED_STALE_MIN:
        return _chk(name, "RED",
                    f"LEVEL FEED STALE {age:.1f}m (>{LEVEL_FEED_STALE_MIN}m) during RTH -- engine "
                    f"reading FROZEN levels; check Gamma_LevelRefresh -- {detail}", critical=False)
    return _chk(name, "GREEN", detail, critical=True)


def assess_dispatch_health(rows: list, enabled_by_account: dict,
                           min_ticks: int = DISPATCH_MIN_TICKS) -> dict:
    """Pure assessor (testable, no IO). Detects the G16 silent-dispatch-death.

    rows               -- list of decision dicts, each with 'account', 'ts_et', and
                          optionally 'extra_signals'.
    enabled_by_account -- {account_name: bool} -- whether ANY extra-setup flag is enabled
                          in that account's params (so dispatch is EXPECTED to emit rows).

    For each ENABLED account, evaluate the MOST RECENT date present in its rows. RED only
    when that date is populated (>= min_ticks rows) AND ZERO of them carry extra_signals --
    the unambiguous G16 signature (dispatch silently emitting nothing despite an enabled
    detector). Healthy / insufficient-data / no-enabled-account -> GREEN. Never raises on a
    malformed row (the caller fail-opens on any exception)."""
    by_acct: dict = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        acct = r.get("account")
        if acct is None:
            continue
        by_acct.setdefault(acct, []).append(r)

    enabled = [a for a, on in enabled_by_account.items() if on]
    if not enabled:
        return {"status": "GREEN", "detail": "no extra-setup flag enabled (dispatch idle)",
                "accounts": {}}

    acct_stats: dict = {}
    blind: list = []
    healthy: list = []
    insufficient: list = []
    for acct in enabled:
        ar = by_acct.get(acct, [])
        # latest date present for this account (ts_et is naive ET 'YYYY-MM-DD...')
        dates = sorted({str(r.get("ts_et", ""))[:10] for r in ar if r.get("ts_et")})
        latest = dates[-1] if dates else None
        day_rows = [r for r in ar if str(r.get("ts_et", ""))[:10] == latest] if latest else []
        n_total = len(day_rows)
        n_extra = sum(1 for r in day_rows if r.get("extra_signals"))
        acct_stats[acct] = {"date": latest, "n_total": n_total, "n_extra": n_extra}
        if n_total < min_ticks:
            insufficient.append(f"{acct}({n_total}t<{min_ticks})")
        elif n_extra == 0:
            blind.append(f"{acct} {latest}: 0/{n_total} ticks emitted extra_signals")
        else:
            healthy.append(f"{acct} {n_extra}/{n_total}")

    if blind:
        detail = ("EXTRA-SETUP DISPATCH BLIND -- " + "; ".join(blind)
                  + " (G16 silent-dispatch-death signature; an enabled detector emitted "
                  "NOTHING all session -- check setup_dispatch._build_ctx)")
        return {"status": "RED", "detail": detail, "accounts": acct_stats}
    parts = healthy + insufficient
    return {"status": "GREEN", "detail": "dispatch live: " + ", ".join(parts) if parts
            else "dispatch idle (no decisions yet)", "accounts": acct_stats}


def _enabled_dispatch_flags(params_path: Path) -> Optional[bool]:
    """True if ANY extra-setup flag is enabled in params_path; None if unreadable."""
    data, _err = _read_json(params_path)
    if data is None:
        return None
    return any(data.get(f) is True for f in DISPATCH_FLAGS)


def _tail_decisions(path: Path, n: int) -> list:
    """Read the last n JSON lines of the decisions ledger. Fail-open: returns [] on any
    read/parse error (the check then reports GREEN-quiet, never crashes the beacon)."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    out = []
    for ln in lines[-n:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except (ValueError, TypeError):
            continue
    return out


def check_dispatch_health(et: datetime) -> dict:
    """Extra-setup dispatch liveness (the G16 silent-death guard). Reads each account's
    enabled dispatch flags + the recent decisions ledger and asserts that an ENABLED
    detector actually emits extra_signals on the latest RTH. NON-CRITICAL always (research/
    observability path -- never trade-halts, never REDs the critical verdict) + fail-open
    (any read/parse error -> benign YELLOW). A genuine BLIND-dispatch returns RED *status*
    so the transition-only alerter pings J once."""
    name = "dispatch_health"
    try:
        enabled = {
            "safe": _enabled_dispatch_flags(STATE / "params.json"),
            "bold": _enabled_dispatch_flags(AGG / "params.json"),
        }
        if all(v is None for v in enabled.values()):
            return _chk(name, "YELLOW", "no params readable", critical=False)
        # Drop unreadable accounts (None) -> never expect dispatch from a params we can't read.
        enabled_clean = {a: bool(v) for a, v in enabled.items() if v is not None}
        rows = _tail_decisions(STATE / "core-decisions.jsonl", DISPATCH_TAIL_LINES)
        r = assess_dispatch_health(rows, enabled_clean)
    except Exception as e:  # noqa: BLE001 -- never let the dispatch checker break the beacon
        return _chk(name, "YELLOW", f"dispatch assess failed ({type(e).__name__})", critical=False)
    status = r.get("status", "YELLOW")
    if status not in ("GREEN", "YELLOW", "RED"):
        status = "YELLOW"
    return _chk(name, status, r.get("detail", "?"), critical=False)


def check_state_freshness(et: datetime) -> dict:
    """CROSS-PRODUCER state freshness -- the 2026-07-30 SIBLING AUDIT check.

    The `levels_blind` / `levels_file_stale` pair above watches ONE file
    (key-levels.json). This watches every OTHER state file the live decision path
    reads, against a declarative manifest
    (automation/state/state-freshness-manifest.json) of
    path / max_age_min / date_field / criticality. It exists because 2026-07-30 was
    not a single-file outage: the same silent-producer-death shape was ALSO running
    on key-levels-memory.json, prior-rth-close.json, context-bundle.json,
    trendlines-live.json, confluence-zones.json, ema-snapshot.json,
    trade-today.json, pnl-statement.json and premarket-readiness.json -- nine more
    files, all frozen at 2026-07-29, none of which any check would have named.

    Checks the CONSEQUENCE (a stale file), not any single cause, so it also catches
    a producer that still fires but writes nothing / writes yesterday's payload --
    failure modes no task-liveness check can see (and `audit_scheduled_tasks.py`
    structurally cannot: its SILENT_TASK loop opens with
    ``if state == "Disabled": continue``).

    OVERLAP IS INTENTIONAL: key-levels.json is in the manifest too. It is the
    canonical example and the manifest must stay a complete registry; a second RED
    on the same root cause is defence in depth, not noise.

    NON-CRITICAL always (monitoring fails OPEN -- never trade-halts, never REDs the
    critical verdict). A genuine stall returns RED *status* so the transition-only
    alerter pings J once. UNKNOWN (unreadable manifest / import failure) maps to a
    benign YELLOW: an audit that cannot run must never look like an audit that passed.
    Guard: backtest/tests/test_state_freshness_audit.py."""
    name = "state_freshness"
    try:
        import state_freshness_audit as sfa  # noqa: PLC0415 -- optional dep, fail open
    except Exception as e:  # noqa: BLE001
        return _chk(name, "YELLOW", f"state_freshness_audit unavailable ({type(e).__name__})",
                    critical=False)
    try:
        rep = sfa.audit(now_et=et)
    except Exception as e:  # noqa: BLE001 -- belt-and-braces; audit() already fails open
        return _chk(name, "YELLOW", f"audit raised ({type(e).__name__})", critical=False)

    verdict = rep.get("verdict", "UNKNOWN")
    stale = [r for r in rep.get("entries", []) if r.get("status") in ("RED", "YELLOW")]
    if verdict == "UNKNOWN":
        return _chk(name, "YELLOW", f"audit UNKNOWN ({rep.get('reason') or 'unreadable manifest'})",
                    critical=False)
    if verdict == "GREEN":
        return _chk(name, "GREEN", f"{rep.get('n_entries', 0)} live-path state files fresh",
                    critical=False)
    named = ", ".join(Path(r["path"]).name for r in stale[:6])
    more = f" (+{len(stale) - 6} more)" if len(stale) > 6 else ""
    return _chk(name, verdict,
                f"{len(stale)}/{rep.get('n_entries', 0)} live-path state files STALE -- "
                f"{named}{more}. Their producers stopped writing; consumers did not notice.",
                critical=False)


def check_position(name: str, path: Path) -> dict:
    data, err = _read_json(path)
    if data is None:
        return _chk(name, "YELLOW", f"position file {err}", critical=False)
    if "status" not in data:
        return _chk(name, "YELLOW", "no 'status' key", critical=False)
    status = data.get("status")
    return _chk(name, "GREEN", "flat" if status is None else f"status={status}", critical=False)


# ---------------------------------------------------------------------------
# Verdict fusion
# ---------------------------------------------------------------------------

def fuse(checks: list[dict]) -> tuple[str, list[str]]:
    """RED if any CRITICAL check is RED; else YELLOW if any check is RED/YELLOW;
    else GREEN. reds[] lists the human-readable triggers."""
    reds: list[str] = []
    crit_red = False
    degraded = False
    for c in checks:
        if c["status"] == "RED":
            reds.append(f"{c['name']}: {c['detail']}")
            if c["critical"]:
                crit_red = True
            else:
                degraded = True
        elif c["status"] == "YELLOW":
            degraded = True
    if crit_red:
        return "RED", reds
    if degraded or reds:
        return "YELLOW", reds
    return "GREEN", reds


def build_report() -> dict:
    now_utc = _now_utc()
    et = _et_now(now_utc)
    mkt = market_is_open(et)

    # ROSTER REPOINT (2026-06-26): watch the NEW deterministic engine, not the retired
    # LLM producers. heartbeat_safe/bold now read core-decisions.jsonl (the brain's
    # per-account per-tick output) instead of the disabled-LLM loop-state.json; sight_beacon
    # is the eye (direct-REST liveness) replacing the retired tv_chart (TV/CDP is no longer
    # on the trade hot path -- Gamma_TvWatchdog owns premarket TV liveness separately). The
    # check NAMES are preserved so the transition-alert idempotency keys stay stable.
    checks = [
        check_session_ran(et),
        # 2026-07-30 blindness pair. NEITHER is market_open-suppressed -- that suppression
        # is what let a full day of zero-level trading read GREEN. levels_blind watches the
        # CONSUMER (the engine's own rows); levels_file_stale watches the PRODUCER (file
        # mtime + session date, asserted through the close). Either alone catches 07-30.
        check_levels_blind(et),
        check_levels_file_stale(et),
        check_engine_core("heartbeat_safe", "safe", mkt, et),
        check_engine_core("heartbeat_bold", "bold", mkt, et),
        check_sight_beacon(mkt, now_utc),
        check_watcher_feed(mkt, et),
        check_killswitch("killswitch_safe", STATE / "circuit-breaker.json"),
        check_killswitch("killswitch_bold", AGG / "circuit-breaker.json"),
        # NON-CRITICAL breaker re-arm freshness (2026-07-09 incident): killswitch_* above
        # only proves "not tripped", not "armed on TODAY's equity" -- surfaces a silent
        # premarket/CCR-gateway death that leaves the daily-loss anchor stale. Never
        # trade-halts; RED status pings J once on a genuine staleness transition.
        check_breaker_rearm("breaker_rearm_safe", STATE / "circuit-breaker.json",
                             BREAKER_DATE_FIELD["breaker_rearm_safe"], mkt, et),
        check_breaker_rearm("breaker_rearm_bold", AGG / "circuit-breaker.json",
                             BREAKER_DATE_FIELD["breaker_rearm_bold"], mkt, et),
        check_position("position_safe", STATE / "current-position.json"),
        check_position("position_bold", STATE / "current-position-bold.json"),
        # NON-CRITICAL research-data continuity watcher (2026-06-29): surfaces a silent
        # GEX-accrual death without ever trade-halting or RED-ing the critical verdict.
        check_gex_archive(et),
        # NON-CRITICAL intraday-level-feed freshness (2026-06-29): surfaces a silent
        # Gamma_LevelRefresh death (engine reading FROZEN levels again) -- the regression
        # guard for the only shippable win of the 06-29 missed-setups mission. Never
        # trade-halts; degrades to YELLOW and pings J once on a genuine RTH stall.
        check_level_feed(mkt, et),
        # NON-CRITICAL extra-setup dispatch liveness (2026-06-29): graduates the G16
        # observe-live ritual into a guard -- surfaces a silent setup_dispatch death
        # (an enabled detector emitting ZERO extra_signals all session, the exact bug
        # that was invisible for weeks). Never trade-halts; RED status pings J once.
        check_dispatch_health(et),
        # NON-CRITICAL cross-producer state freshness (2026-07-30 SIBLING AUDIT). The pair
        # above watches key-levels.json specifically; THIS watches every OTHER live-path
        # state file for the same shape (producer stopped writing, consumers carried on).
        # It found 9 further files already stale on 2026-07-30. Additive by construction:
        # one check name, manifest-driven, never trade-halts, fails open to UNKNOWN.
        check_state_freshness(et),
    ]
    verdict, reds = fuse(checks)
    red_checks = sorted(c["name"] for c in checks if c["status"] == "RED")
    return {
        "checked_at_et": et.strftime("%Y-%m-%d %H:%M:%S"),
        "checked_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "market_open": mkt,
        "checks": checks,
        "reds": reds,
        # Idempotency key for the alerter: the SET of RED check-names. We alert
        # when a NEW red check appears (transition), not on every run while it
        # persists -- so a 3-day producer-dark pings once, not 800 times.
        "red_checks": red_checks,
    }


# ---------------------------------------------------------------------------
# Discord transition-only alert (reuse existing outbox; no new path)
# ---------------------------------------------------------------------------

def _prior_state() -> tuple[Optional[str], set]:
    """Prior (verdict, set-of-red-check-names) from the last written report.
    Used to detect a *transition* (new red appearing) for idempotent alerting."""
    data, _ = _read_json(OUT_FILE)
    if not data:
        return None, set()
    return data.get("verdict"), set(data.get("red_checks") or [])


def _heal_grace_active(now_utc: datetime) -> bool:
    """True if heal-engine.ps1 just attempted an auto-heal (grace window still open).
    Suppresses the J-ping until the re-fired heartbeat tick has had time to land -- the
    ACT-before-WATCH contract (2026-06-22): J is pinged only if the heal FAILS."""
    data, _ = _read_json(STATE / "engine-heal-state.json")
    if not data:
        return False
    gu = _parse_ts(data.get("grace_until"))
    return gu is not None and now_utc < gu


def _mention_prefix() -> str:
    """Match the existing outbox convention: prefix with the user mention so the
    ping pushes to J's device, mirroring discord_watchdog.py's alert format."""
    return "<@207983230618435584> "


def maybe_alert(report: dict, prior_verdict: Optional[str], prior_reds: set) -> bool:
    """Append ONE SOUL-voice line to the outbox on a *transition* -- i.e. when a
    RED check that was NOT red on the previous run appears now. This fires for:
      - a CRITICAL red (verdict=RED, e.g. dead heartbeat / tripped kill-switch), and
      - a sustained NON-critical red (verdict=YELLOW, e.g. watcher producer-dark)
        that previously went un-alerted for 3 days (2026-06-22 root cause).
    Idempotent: keyed on the SET of red check-names, so it pings once on the
    transition, never re-spams while the same red persists."""
    now_reds = set(report.get("red_checks") or [])
    if not now_reds:
        return False
    # Only the NEWLY-red checks are an alertable transition. If the same red set
    # carried over from the prior run, stay silent (already pinged).
    new_reds = now_reds - prior_reds
    if not new_reds:
        return False
    # ACT-before-WATCH (2026-06-22): if the auto-healer just re-fired the stalled heartbeat,
    # hold the ping until the grace window expires -- the tick lands in ~60-90s. J hears
    # about it ONLY if the heal failed (still RED after grace). RED is still written + shown.
    # (Only suppress for heartbeat liveness reds -- the heal-loop only re-fires the
    # heartbeat, so a watcher/kill-switch red must still ping during grace.)
    if new_reds <= {"heartbeat_safe", "heartbeat_bold"} and _heal_grace_active(_now_utc()):
        return False
    # Build the alert from the reds that triggered this transition.
    reds = report["reds"]
    triggered = [r for r in reds if r.split(":", 1)[0] in new_reds] or reds
    head = triggered[0] if triggered else "engine health critical"
    extra = f" (+{len(triggered) - 1} more)" if len(triggered) > 1 else ""
    # Marker reflects severity: critical-red -> verdict RED; non-critical -> degraded.
    marker = "🔴 Engine RED" if report["verdict"] == "RED" else "🟠 Engine DEGRADED (red check)"
    # SOUL voice: terse, one safety marker, no hedging.
    content = f"{_mention_prefix()}{marker}: {head}{extra}. Fail-loud beacon. Check the fleet."
    if len(content) > 1900:
        content = content[:1880] + "...[truncated]"
    row = {"queued_at": report["checked_at_utc"], "content": content}
    try:
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as e:  # noqa: BLE001 -- never let alerting crash the beacon
        print(f"[engine_health] outbox append failed: {e}", file=sys.stderr)
        return False


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    prior_verdict, prior_reds = _prior_state()
    report = build_report()
    alerted = maybe_alert(report, prior_verdict, prior_reds)
    report["alerted"] = alerted
    _atomic_write(OUT_FILE, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
