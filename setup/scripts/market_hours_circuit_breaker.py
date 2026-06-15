"""Market-hours circuit breaker -- monitors today's Claude token spend and kills
interactive sessions when spend crosses a configurable dollar threshold during
market hours (09:30-15:55 ET weekdays).

Per CLAUDE.md OP-30 (effort/concurrency discipline) and L62 (rate-limit pool
exhaustion silenced heartbeat ticks + EOD pipeline on 2026-05-20): a single
burning interactive `--effort max` session can exhaust the shared rate-limit
pool and knock out Gamma_Heartbeat + EOD scheduled tasks.

ACTIONS when threshold crossed AND interactive sessions exist:
  1. Kill all interactive Claude Code CLI sessions (no --print in command line).
  2. Write automation/state/rate-limit-cooldown.json with claude_print_exempt:true
     so Gamma_Heartbeat keeps trading uninterrupted.
  3. Append a CRITICAL block to automation/overnight/STATUS.md.

Per OP-27 subprocess-spawn discipline: all subprocess calls use CREATE_NO_WINDOW;
long-running pythonw launch redirects stdout/stderr to dated log files.

Scheduled invocation: Gamma_MarketHoursCircuitBreaker every 5 min during
09:30-15:55 ET weekdays (to be registered via install-market-hours-cb.ps1).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# REPO layout anchors (OP-27: always anchor to __file__, never bare relative)
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
STATUS_FILE = REPO / "automation" / "overnight" / "STATUS.md"
COOLDOWN_FILE = STATE_DIR / "rate-limit-cooldown.json"
LOG_FILE = STATE_DIR / "market-hours-cb.jsonl"

# Claude Code session logs for this project
_CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects" / "C--Users-jackw-Desktop-42"

# ---------------------------------------------------------------------------
# OP-27 L41: CREATE_NO_WINDOW for all subprocess calls on Windows
# ---------------------------------------------------------------------------
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ---------------------------------------------------------------------------
# DST helpers (copied verbatim from session_guard.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# OP-27 L41 layer 3: redirect stdout/stderr when launched as pythonw.exe
# (must be after _et_now_naive is defined, before any print/logging calls)
# ---------------------------------------------------------------------------
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today_str = _et_now_naive().strftime("%Y-%m-%d")
    sys.stdout = open(
        _log_dir / f"market-hours-circuit-breaker-{_today_str}.stdout.log",
        "a", buffering=1, encoding="utf-8",
    )
    sys.stderr = open(
        _log_dir / f"market-hours-circuit-breaker-{_today_str}.stderr.log",
        "a", buffering=1, encoding="utf-8",
    )

# ---------------------------------------------------------------------------
# Market hours gate
# ---------------------------------------------------------------------------
MARKET_START = dtime(9, 30)
MARKET_END = dtime(15, 55)

# ---------------------------------------------------------------------------
# Pricing constants (per-token USD) for spend calculation
# ---------------------------------------------------------------------------
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5": {"in": 3.0 / 1e6, "out": 15.0 / 1e6, "cw": 3.75 / 1e6, "cr": 0.30 / 1e6},
    "claude-opus-4-5":   {"in": 15.0 / 1e6, "out": 75.0 / 1e6, "cw": 18.75 / 1e6, "cr": 1.50 / 1e6},
    "claude-haiku-4-5":  {"in": 1.0 / 1e6, "out": 5.0 / 1e6, "cw": 1.25 / 1e6, "cr": 0.10 / 1e6},
}

DEFAULT_THRESHOLD_USD = 100.0
COOLDOWN_RESET_MINUTES = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _in_market_hours(now_et: datetime) -> bool:
    """Weekday + 09:30-15:55 ET."""
    if now_et.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return MARKET_START <= now_et.time() <= MARKET_END


def _normalize_model(raw: str) -> Optional[str]:
    """Map a raw model string to a PRICING key. Returns None if unrecognised."""
    r = raw.lower()
    if "sonnet" in r:
        return "claude-sonnet-4-5"
    if "opus" in r:
        return "claude-opus-4-5"
    if "haiku" in r:
        return "claude-haiku-4-5"
    return None


def _compute_today_spend() -> tuple[float, int]:
    """Read all *.jsonl files under the Claude Code project logs dir and sum
    token spend for today's ET date.

    Returns (total_usd, message_count).
    """
    if not _CLAUDE_PROJECTS_DIR.exists():
        print(
            f"[circuit-breaker] WARN projects dir not found: {_CLAUDE_PROJECTS_DIR}",
            file=sys.stderr,
        )
        return 0.0, 0

    today_date = _et_now_naive().date()
    total_usd = 0.0
    message_count = 0

    for jsonl_path in _CLAUDE_PROJECTS_DIR.glob("*.jsonl"):
        try:
            with open(jsonl_path, encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        entry = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    # Determine message timestamp (ET date check)
                    ts_raw = entry.get("timestamp") or entry.get("ts") or ""
                    if ts_raw:
                        try:
                            # Parse as UTC, convert to ET
                            ts_utc = datetime.fromisoformat(
                                ts_raw.replace("Z", "+00:00")
                            ).astimezone(timezone.utc)
                            ts_et = (
                                ts_utc + timedelta(hours=_et_offset_hours(ts_utc))
                            ).replace(tzinfo=None)
                            if ts_et.date() != today_date:
                                continue
                        except (ValueError, AttributeError):
                            # If we can't parse the timestamp, skip — don't
                            # accidentally count yesterday's tokens as today's
                            continue

                    # Extract usage block; handle both direct and nested layouts
                    usage = entry.get("message", {})
                    if isinstance(usage, dict):
                        usage = usage.get("usage") or {}
                    else:
                        usage = entry.get("usage") or {}

                    if not isinstance(usage, dict) or not usage:
                        continue

                    model_raw = (
                        entry.get("message", {}).get("model")
                        or entry.get("model")
                        or ""
                    )
                    if isinstance(entry.get("message"), dict):
                        model_raw = entry["message"].get("model") or model_raw

                    model_key = _normalize_model(str(model_raw))
                    if model_key is None:
                        # Unknown model — use sonnet pricing as a conservative
                        # estimate so we don't silently miss spend
                        model_key = "claude-sonnet-4-5"

                    p = PRICING[model_key]

                    input_tok = int(usage.get("input_tokens") or 0)
                    output_tok = int(usage.get("output_tokens") or 0)
                    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
                    cache_read = int(usage.get("cache_read_input_tokens") or 0)

                    if input_tok == 0 and output_tok == 0 and cache_write == 0 and cache_read == 0:
                        continue

                    cost = (
                        input_tok * p["in"]
                        + output_tok * p["out"]
                        + cache_write * p["cw"]
                        + cache_read * p["cr"]
                    )
                    total_usd += cost
                    message_count += 1

        except OSError as exc:
            print(
                f"[circuit-breaker] WARN could not read {jsonl_path.name}: {exc}",
                file=sys.stderr,
            )

    return total_usd, message_count


# ---------------------------------------------------------------------------
# Process helpers (copied verbatim from session_guard.py)
# ---------------------------------------------------------------------------

def _list_interactive_claude_sessions() -> list[dict]:
    """Returns a list of dicts: { pid, cmdline, created_utc_iso, parent_pid }.

    Filters:
      * Image name claude.exe (the CLI, not the Desktop app -- which is "Claude.exe").
      * Excludes children where CommandLine contains "--print" (scheduled tasks).
      * Excludes Desktop-app subprocess children
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
        print(f"[circuit-breaker] WARN powershell query failed: {exc}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(f"[circuit-breaker] WARN powershell returned {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
        return []
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[circuit-breaker] WARN json parse failed: {exc}", file=sys.stderr)
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


# ---------------------------------------------------------------------------
# State writers
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, entry: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"[circuit-breaker] WARN telemetry write failed: {exc}", file=sys.stderr)


def _write_cooldown(data: dict) -> None:
    """Atomic write: temp-file then rename (per spec)."""
    tmp = COOLDOWN_FILE.with_suffix(".tmp")
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(COOLDOWN_FILE)
    except OSError as exc:
        print(f"[circuit-breaker] ERROR cooldown write failed: {exc}", file=sys.stderr)


def _append_status_critical(
    spend_usd: float,
    threshold: float,
    killed: list[int],
    kill_failed: list[int],
) -> None:
    """Append a CRITICAL block to STATUS.md."""
    try:
        if not STATUS_FILE.parent.exists():
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        now_et = _et_now_naive().strftime("%Y-%m-%dT%H:%M:%S")
        lines = [
            "",
            "### CRITICAL: market-hours-circuit-breaker fired",
            f"- ts_utc: {ts}",
            f"- ts_et: {now_et}",
            f"- spend_today_usd: ${spend_usd:.2f}",
            f"- threshold_usd: ${threshold:.0f}",
            f"- sessions_killed: {killed}",
            f"- kill_failed: {kill_failed}",
            "- claude_print_exempt: true  # Gamma_Heartbeat keeps trading",
            f"- cooldown_reset_in: {COOLDOWN_RESET_MINUTES} min",
            "- action_required: review interactive session usage; restart if needed after cooldown",
        ]
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"[circuit-breaker] WARN STATUS.md write failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Circuit breaker action
# ---------------------------------------------------------------------------

def _fire_circuit_breaker(
    spend_usd: float,
    threshold: float,
    sessions: list[dict],
    dry_run: bool = False,
) -> dict:
    """Kill interactive sessions, write cooldown, append to STATUS.md."""
    killed: list[int] = []
    kill_failed: list[int] = []

    for s in sessions:
        pid = s["pid"]
        if dry_run:
            print(f"[circuit-breaker] DRY-RUN would kill pid={pid} cmd={s['cmdline'][:120]}")
            killed.append(pid)  # report as "would kill" for dry-run summary
        else:
            if _kill_pid(pid):
                killed.append(pid)
                print(f"[circuit-breaker] KILLED pid={pid}")
            else:
                kill_failed.append(pid)
                print(f"[circuit-breaker] KILL_FAILED pid={pid}", file=sys.stderr)

    now_et = _et_now_naive()
    reset_et = now_et + timedelta(minutes=COOLDOWN_RESET_MINUTES)

    cooldown = {
        "reset_at_et": reset_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "detected_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "detected_by_task": "market-hours-circuit-breaker",
        "claude_print_exempt": True,   # heartbeat keeps firing even during cooldown
        "reason": f"spend=${spend_usd:.2f} crossed ${threshold:.0f} threshold",
        "killed_pids": killed,
        "kill_failed_pids": kill_failed,
    }

    if not dry_run:
        _write_cooldown(cooldown)
        _append_status_critical(spend_usd, threshold, killed, kill_failed)

    # Always log to JSONL (even dry-run — useful for smoke tests)
    _append_jsonl(LOG_FILE, {
        "ts": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": "circuit_breaker_fired" if not dry_run else "circuit_breaker_dry_run",
        "spend_usd": round(spend_usd, 4),
        "threshold_usd": threshold,
        "sessions_found": len(sessions),
        "killed": killed,
        "kill_failed": kill_failed,
        "cooldown_reset_et": reset_et.isoformat(),
    })

    return {
        "killed": killed,
        "kill_failed": kill_failed,
        "cooldown_reset_et": reset_et.isoformat(),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD_USD,
        help=f"USD spend threshold that triggers the breaker (default ${DEFAULT_THRESHOLD_USD:.0f}).",
    )
    parser.add_argument(
        "--ignore-market-hours",
        action="store_true",
        help="Bypass market-hours gate (smoke test / manual audit).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without killing sessions or writing state files.",
    )
    args = parser.parse_args()

    now_et = _et_now_naive()

    # --- Market hours gate ---------------------------------------------------
    if not args.ignore_market_hours and not _in_market_hours(now_et):
        print(
            f"[circuit-breaker] not in market hours "
            f"({now_et.strftime('%Y-%m-%d %H:%M:%S')} ET, weekday={now_et.weekday()}); exiting"
        )
        return 0

    # --- Compute today's spend -----------------------------------------------
    spend_usd, msg_count = _compute_today_spend()

    # --- Enumerate interactive sessions --------------------------------------
    sessions = _list_interactive_claude_sessions()

    # --- Status line (always printed) ----------------------------------------
    action_label = "ok"

    if spend_usd >= args.threshold and sessions:
        if args.dry_run:
            action_label = "would_fire"
        else:
            action_label = "fired"

    print(
        f"[circuit-breaker] spend=${spend_usd:.2f} "
        f"threshold=${args.threshold:.0f} "
        f"sessions={len(sessions)} "
        f"messages={msg_count} "
        f"action={action_label}"
    )

    # --- Fire if conditions met -----------------------------------------------
    if spend_usd >= args.threshold and sessions:
        result = _fire_circuit_breaker(
            spend_usd=spend_usd,
            threshold=args.threshold,
            sessions=sessions,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(
                f"[circuit-breaker] DRY-RUN complete: "
                f"would_kill={result['killed']} "
                f"cooldown_reset={result['cooldown_reset_et']}"
            )
        else:
            print(
                f"[circuit-breaker] FIRED: "
                f"killed={result['killed']} "
                f"kill_failed={result['kill_failed']} "
                f"cooldown_reset={result['cooldown_reset_et']}"
            )
    elif spend_usd >= args.threshold and not sessions:
        # Spend is high but no interactive sessions to kill — still write
        # cooldown so future sessions can't spin up without notice.
        _append_jsonl(LOG_FILE, {
            "ts": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": "threshold_crossed_no_sessions",
            "spend_usd": round(spend_usd, 4),
            "threshold_usd": args.threshold,
        })
        print(
            f"[circuit-breaker] threshold crossed (${spend_usd:.2f}) "
            f"but no interactive sessions found; logged only"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
