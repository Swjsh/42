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

# Staleness budget during RTH: a heartbeat that has not written in this many
# minutes is RED (heartbeat cadence is 3 min, so >10 min means ~3 missed ticks).
HEARTBEAT_STALE_MIN = 10
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

def check_heartbeat(name: str, path: Path, market_open: bool, now_utc: datetime) -> dict:
    data, err = _read_json(path)
    if data is None:
        return _chk(name, "YELLOW", f"loop-state {err}", critical=False)
    age = _age_min(_parse_ts(data.get("last_change_at")), now_utc)
    if age is None:
        return _chk(name, "YELLOW", "no last_change_at", critical=False)
    detail = f"last write {age:.1f}m ago; mode={data.get('current_mode')}; ticks={data.get('ticks_today')}"
    if not market_open:
        return _chk(name, "GREEN", f"{detail} (market closed -- quiet OK)", critical=True)
    if age > HEARTBEAT_STALE_MIN:
        return _chk(name, "RED", f"STALE {age:.1f}m (>{HEARTBEAT_STALE_MIN}m) during RTH -- {detail}", critical=True)
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
    # critical=False (2026-06-22): the watcher fleet is WATCH_ONLY (it NEVER places
    # orders) and BOTH heartbeats score their primary book via TV-direct reads, so a
    # dark producer DEGRADES (loses the supplementary 28-watcher signal layer) but does
    # NOT block trading. Keep RED-status so it stays loud + visible in reds[], but
    # non-critical so it no longer gates the engine to trade-halt RED -- otherwise it
    # cry-wolf-REDs every market open while the producer rebuild is in flight (the
    # watcher_live.py morning no-op = naive-local-time gate [rig is MT, not ET] + the
    # yfinance top-up / stale_csv_date stack -- C6/L161). RE-ARM to critical=True the
    # moment watcher_live.py reliably emits today's rows again.
    # See STATUS.md "Known broken 2026-06-22" + the queued watcher-producer rebuild task.
    return _chk(
        "watcher_feed", "RED",
        f"PRODUCER DARK: newest bar {newest_date} != today {today} -- feed not writing during RTH "
        f"(WATCH_ONLY layer: degraded supplementary signal, NOT trade-blocking)",
        critical=False,
    )


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

    checks = [
        check_heartbeat("heartbeat_safe", STATE / "loop-state.json", mkt, now_utc),
        check_heartbeat("heartbeat_bold", AGG / "loop-state.json", mkt, now_utc),
        check_watcher_feed(mkt, et),
        check_tv_chart(now_utc),
        check_killswitch("killswitch_safe", STATE / "circuit-breaker.json"),
        check_killswitch("killswitch_bold", AGG / "circuit-breaker.json"),
        check_position("position_safe", STATE / "current-position.json"),
        check_position("position_bold", STATE / "current-position-bold.json"),
    ]
    verdict, reds = fuse(checks)
    return {
        "checked_at_et": et.strftime("%Y-%m-%d %H:%M:%S"),
        "checked_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "market_open": mkt,
        "checks": checks,
        "reds": reds,
    }


# ---------------------------------------------------------------------------
# Discord transition-only alert (reuse existing outbox; no new path)
# ---------------------------------------------------------------------------

def _prior_verdict() -> Optional[str]:
    data, _ = _read_json(OUT_FILE)
    return data.get("verdict") if data else None


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


def maybe_alert(report: dict, prior: Optional[str]) -> bool:
    """Append ONE SOUL-voice line to the outbox only on a *transition into RED*."""
    if report["verdict"] != "RED" or prior == "RED":
        return False
    # ACT-before-WATCH (2026-06-22): if the auto-healer just re-fired the stalled heartbeat,
    # hold the ping until the grace window expires -- the tick lands in ~60-90s. J hears
    # about it ONLY if the heal failed (still RED after grace). RED is still written + shown.
    if _heal_grace_active(_now_utc()):
        return False
    reds = report["reds"]
    head = reds[0] if reds else "engine health critical"
    extra = f" (+{len(reds) - 1} more)" if len(reds) > 1 else ""
    # SOUL voice: terse, one safety marker, no hedging.
    content = f"{_mention_prefix()}🔴 Engine RED: {head}{extra}. Fail-loud beacon. Check the fleet."
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
    prior = _prior_verdict()
    report = build_report()
    alerted = maybe_alert(report, prior)
    report["alerted"] = alerted
    _atomic_write(OUT_FILE, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
