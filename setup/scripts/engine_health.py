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

def _load_holidays() -> set:
    """Read automation/state/calendar.json .holidays[] (ISO yyyy-mm-dd) if present.
    Matches _shared.ps1 Test-HolidayFromAlpaca: absent file -> no holidays."""
    cal = STATE / "calendar.json"
    try:
        data = json.loads(cal.read_text(encoding="utf-8"))
        return {str(d) for d in data.get("holidays", [])}
    except Exception:
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
        check_engine_core("heartbeat_safe", "safe", mkt, et),
        check_engine_core("heartbeat_bold", "bold", mkt, et),
        check_sight_beacon(mkt, now_utc),
        check_watcher_feed(mkt, et),
        check_killswitch("killswitch_safe", STATE / "circuit-breaker.json"),
        check_killswitch("killswitch_bold", AGG / "circuit-breaker.json"),
        check_position("position_safe", STATE / "current-position.json"),
        check_position("position_bold", STATE / "current-position-bold.json"),
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
