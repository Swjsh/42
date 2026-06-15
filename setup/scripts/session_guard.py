"""Session guard -- detects interactive Claude Code sessions running during
market hours and surfaces them to STATUS.md.

PER CLAUDE.md L54 + OP-22: long-running interactive Sonnet sessions during
09:30-15:55 ET share rate-limit quota with `claude --print` heartbeat ticks
and EOD scheduled tasks. A burning interactive session can drain quota and
silently kill production trading + EOD digest.

OPERATING MODES:
  --mode soft  (default): log to JSONL telemetry + append WARN row to STATUS.md.
  --mode hard           : same telemetry, AND kill the offending session(s).

DISCRIMINATOR: interactive vs scheduled-task `claude --print`.
  * `claude --print` invocations (scheduled tasks) have "--print" in CommandLine -- EXEMPT.
  * `Claude.exe` Desktop app processes (the GUI host) are EXEMPT.
  * `claude.exe` with --output-format stream-json (interactive Claude Code CLI) -- FLAG.

Per OP-27 L42 + OP-27 subprocess-spawn discipline, this is a pythonw-safe
script (uses CREATE_NO_WINDOW for subprocess calls and stdio is redirected
when launched headless).

Scheduled invocation: Gamma_SessionGuard every 5 min, 09:30-15:50 ET weekdays.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _et_offset_hours(dt_utc: datetime) -> int:
    """US DST rules: EDT (UTC-4) from 2nd Sunday March 02:00 local through
    1st Sunday November 02:00 local; EST (UTC-5) otherwise. Returns -4 or -5.
    Avoids the tzdata dependency that system Python lacks on this host."""
    y = dt_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start_utc = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end_utc = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start_utc <= dt_utc < dst_end_utc) else -5


def _et_now_naive() -> datetime:
    """Current ET wall clock as a NAIVE datetime (no tzinfo).
    Used for market-hours checks + display formatting only."""
    now_utc = datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=_et_offset_hours(now_utc))).replace(tzinfo=None)
REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
LOG_FILE = STATE_DIR / "session-guard.jsonl"
STATUS_FILE = REPO / "automation" / "overnight" / "STATUS.md"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Headless-launch stdout/stderr redirection (per OP-27 L41 layer 3)
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today = _et_now_naive().strftime("%Y-%m-%d")
    sys.stdout = open(_log_dir / f"session-guard-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"session-guard-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


# Market hours (ET): the window where shared rate-limit conflict matters.
MARKET_START = dtime(9, 30)
MARKET_END = dtime(15, 55)

# Min process age in minutes to consider a session "long-running" worth flagging.
# Below this, it's likely a fresh fire and not yet a problem.
MIN_AGE_MIN = 5


@dataclass(frozen=True)
class GuardEvent:
    detected_at_et: str
    weekday: str
    pid: int
    started_at_utc: str
    age_min: int
    cmd_line_short: str
    action: str  # "warn" | "killed" | "skipped"
    mode: str    # "soft" | "hard"


def _now_et() -> datetime:
    return _et_now_naive()


def _in_market_hours(now_et: datetime) -> bool:
    """Weekday + 09:30-15:55 ET."""
    if now_et.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return MARKET_START <= now_et.time() <= MARKET_END


def _shorten(s: str, n: int = 160) -> str:
    if not s:
        return ""
    s = s.replace("\r", " ").replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."


def _list_interactive_claude_sessions() -> list[dict]:
    """Returns a list of dicts: { pid, cmdline, created_utc_iso, parent_pid }.

    Filters:
      * Image name claude.exe (the CLI, not the Desktop app -- which is "Claude.exe").
      * Excludes children where CommandLine contains "--print" (scheduled tasks).
      * Excludes Desktop app forks (--type=gpu-process/renderer/utility/crashpad-handler).
    """
    # Use -EncodedCommand (UTF-16LE base64) to bypass all CLI quoting headaches.
    import base64
    ps_cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'claude.exe'\" | "
        "Select-Object ProcessId, CommandLine, CreationDate, ParentProcessId | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    encoded = base64.b64encode(ps_cmd.encode("utf-16le")).decode("ascii")
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[session-guard] WARN powershell query failed: {exc}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(f"[session-guard] WARN powershell returned {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
        return []
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[session-guard] WARN json parse failed: {exc}", file=sys.stderr)
        return []
    # Single-result Get-CimInstance returns dict; multi-result returns list.
    rows = data if isinstance(data, list) else [data]
    out: list[dict] = []
    for row in rows:
        cmd = (row.get("CommandLine") or "").strip()
        if not cmd:
            continue
        # Exempt scheduled-task fires
        if "--print" in cmd:
            continue
        # Exempt Desktop-app subprocess children
        if any(tok in cmd for tok in ("--type=gpu-process", "--type=renderer", "--type=utility", "--type=crashpad-handler")):
            continue
        # Exempt the Desktop app host itself (lives in WindowsApps)
        if "WindowsApps" in cmd and "Claude_1." in cmd:
            continue
        # CreationDate comes from CIM in /Date(NNN)/ format or ISO. Parse defensively.
        created_raw = row.get("CreationDate")
        created_iso = ""
        if isinstance(created_raw, dict) and "DateTime" in created_raw:
            created_iso = created_raw["DateTime"]
        elif isinstance(created_raw, str):
            created_iso = created_raw
        out.append({
            "pid": int(row.get("ProcessId") or 0),
            "cmdline": cmd,
            "created_iso": created_iso,
            "parent_pid": int(row.get("ParentProcessId") or 0),
        })
    return out


def _parse_creation_to_utc(s: str) -> Optional[datetime]:
    """CIM CreationDate via ConvertTo-Json comes as `/Date(1779243993656)/`
    (.NET DateTime serialized as Unix epoch ms). Also handle ISO 8601 and the
    raw WMI compact format defensively."""
    if not s:
        return None
    s = s.strip()
    # .NET JSON DateTime: /Date(NNN)/ or \/Date(NNN)\/
    import re
    m = re.match(r"^/?Date\((-?\d+)\)/?$", s.replace("\\/", "/"))
    if m:
        try:
            ms = int(m.group(1))
            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    # ISO 8601
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    # WMI compact format: YYYYMMDDhhmmss.ffffff[+-]TZmin
    if len(s) >= 14 and s[:14].isdigit():
        try:
            yy, mm, dd = int(s[0:4]), int(s[4:6]), int(s[6:8])
            hh, mi, ss = int(s[8:10]), int(s[10:12]), int(s[12:14])
            return datetime(yy, mm, dd, hh, mi, ss, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _kill_pid(pid: int) -> bool:
    """Force-kill a PID via taskkill /T /F. Returns True on success."""
    try:
        proc = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _append_jsonl(path: Path, entry: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"[session-guard] WARN telemetry write failed: {exc}", file=sys.stderr)


def _append_status_warn(events: list[GuardEvent]) -> None:
    """Append a single WARN block to STATUS.md summarizing flagged sessions."""
    if not events:
        return
    try:
        if not STATUS_FILE.parent.exists():
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [
            "",
            f"### WARN: session-guard market-hours flag",
            f"- ts: {ts}",
            f"- count: {len(events)}",
            f"- mode: {events[0].mode}",
        ]
        for ev in events[:5]:  # cap at 5 to keep STATUS tidy
            lines.append(f"  - pid={ev.pid} age={ev.age_min}min action={ev.action} cmd=`{ev.cmd_line_short[:80]}`")
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"[session-guard] WARN status_md write failed: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("soft", "hard"), default="soft",
                        help="soft (default) = log + WARN. hard = also kill flagged sessions.")
    parser.add_argument("--min-age-min", type=int, default=MIN_AGE_MIN,
                        help=f"Minimum age (min) to flag a session (default {MIN_AGE_MIN}).")
    parser.add_argument("--ignore-market-hours", action="store_true",
                        help="Bypass market-hours check (smoke test / manual audit).")
    parser.add_argument("--dry-run", action="store_true",
                        help="In hard mode, only PRINT what would be killed; don't actually kill.")
    args = parser.parse_args()

    now_et = _now_et()
    if not args.ignore_market_hours and not _in_market_hours(now_et):
        print(f"[session-guard] not in market hours ({now_et.strftime('%Y-%m-%d %H:%M:%S')} ET, weekday={now_et.weekday()}); exiting")
        return 0

    sessions = _list_interactive_claude_sessions()
    flagged: list[GuardEvent] = []
    now_utc = datetime.now(timezone.utc)

    for s in sessions:
        created_utc = _parse_creation_to_utc(s["created_iso"]) if s["created_iso"] else None
        if created_utc is None:
            age_min = 9999  # treat unknown-age as old (worth flagging)
        else:
            age_min = int((now_utc - created_utc).total_seconds() / 60)
        if age_min < args.min_age_min:
            continue
        action = "warn"
        if args.mode == "hard":
            if args.dry_run:
                action = "would_kill"
            else:
                killed = _kill_pid(s["pid"])
                action = "killed" if killed else "kill_failed"
        ev = GuardEvent(
            detected_at_et=now_et.strftime("%Y-%m-%dT%H:%M:%S"),
            weekday=now_et.strftime("%A"),
            pid=s["pid"],
            started_at_utc=(created_utc.isoformat() if created_utc else "unknown"),
            age_min=age_min,
            cmd_line_short=_shorten(s["cmdline"], 160),
            action=action,
            mode=args.mode,
        )
        flagged.append(ev)
        _append_jsonl(LOG_FILE, ev.__dict__)
        print(f"[session-guard] FLAG pid={ev.pid} age={ev.age_min}min action={ev.action} cmd={ev.cmd_line_short[:100]}")

    if flagged:
        _append_status_warn(flagged)
        # Exit non-zero only in hard mode -- in soft mode, presence of sessions is informational.
        # The scheduled task wrapper logs both. J's morning brief shows STATUS.md flag either way.
        if args.mode == "hard" and any(ev.action == "killed" for ev in flagged):
            return 0  # successful kill = good (soft 0)
        return 0
    else:
        print(f"[session-guard] OK no flagged sessions in market hours ({now_et.strftime('%H:%M')} ET)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
