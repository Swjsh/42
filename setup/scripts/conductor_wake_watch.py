"""conductor_wake_watch.py -- WAKE-ON-EVENT for the Gamma_Conductor family.

J directive 2026-07-18 ("gamma alive, hunting all day for money"): a RED-grade alert
landing in `discord-outbox.jsonl` or `STATUS.md`'s `## Known broken` section should not
have to wait for the NEXT scheduled conductor cadence (up to 1h after-hours / 2h weekend /
30min RTH) -- it should wake the right conductor mode immediately, debounced so a burst of
alerts doesn't hammer the Max-plan pool.

$0, pure Python stdlib, fail-open (never raises into the scheduler -- every code path below
is wrapped so a parse error or missing file degrades to "no event" rather than crashing the
5-min task). Read-only except for its own watermark file.

MECHANISM:
  1. Scan discord-outbox.jsonl lines appended since the last watermark for a RED-grade
     marker (RED / BROKEN / DEGRADED / KILL_SWITCH / CRITICAL / the siren emoji).
  2. Scan STATUS.md's "## Known broken" section for a NEW leading timestamp since the last
     watermark (a fresh entry landed).
  3. If either fired AND at least WAKE_DEBOUNCE_MIN has elapsed since the last wake-fire,
     Start the right conductor task for the current ET time-of-day:
       - weekday RTH (09:30<=ET<15:55)  -> Gamma_ConductorRTH  (bounded verify-and-flag)
       - everything else                -> Gamma_Conductor     (full after-hours loop)
     via `schtasks /Run /TN <task>` (the CLI equivalent of PowerShell Start-ScheduledTask),
     CREATE_NO_WINDOW so no console flashes (OP-27 L42 discipline).
  4. Always persist the watermark (line-count + marker seen) so a quiet fire never re-scans
     old evidence, and print one status line for the Invoke-PythonHidden log.

CLI:
  python conductor_wake_watch.py            # normal fire (used by Gamma_ConductorWake)
  python conductor_wake_watch.py --dry-run  # detect + print, never actually Start- the task
  python conductor_wake_watch.py --force    # bypass the debounce window (manual testing)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUTBOX = STATE / "discord-outbox.jsonl"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
WATERMARK = STATE / "conductor-wake-watermark.json"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now as _et_now
except Exception:  # noqa: BLE001 -- fail-open fallback, mirrors self_check.py's pattern
    def _et_now():
        return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# COST GOVERNOR (2026-07-25): was 30 min. A measured census (07-18..07-23 session transcripts)
# found the conductor family = 93% of ALL automation token burn ($149.57/day), and THIS constant
# was the multiplier: 22 conductor fires on 07-23 vs 12 scheduled. Each event-fire launches the
# full high-effort $10-cap Gamma_Conductor (measured $7.69/fire), so a 30-min debounce against a
# near-continuously-matching pattern (below) meant ~10 unscheduled $7.69 fires per night.
WAKE_DEBOUNCE_MIN = 180  # max 1 event-fire per 3h

# RED_PATTERN was: \b(RED|BROKEN|DEGRADED|KILL_SWITCH|CRITICAL)\b
# DEGRADED and RED are removed DELIBERATELY. self-check has carried a cosmetic
# "TRENDLINE-DRAW never marked today ... Non-load-bearing (visibility only)" DEGRADED flag for
# 4+ consecutive days; because that string reaches discord-outbox.jsonl, a visibility-only flag
# was literally summoning $7.69 conductor fires all night. This watcher must wake the conductor
# for things that STOP OR ENDANGER TRADING, not for anything that merely reads unwell -- a
# routine DEGRADED still surfaces in self-check/engine-health/the daily brief, which is where a
# non-urgent flag belongs (L189: a perpetually-RED signal trains everyone to skim past it).
RED_PATTERN = re.compile(r"\b(BROKEN|KILL_SWITCH|CRITICAL)\b|\U0001F6A8")
KNOWN_BROKEN_HEADER = "## Known broken"
TS_TOKEN = re.compile(r"\[([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9:.+\-Z]{5,25})\]")
# ENTRY_LINE_RE matches a Known-broken bullet's full text ("- [stamp] MARKER: payload"),
# same bullet shape status_known_broken.py's _BULLET_LINE_RE uses, capturing everything
# AFTER the "[stamp] " prefix in group(1).
ENTRY_LINE_RE = re.compile(r"^-?\s*\[[^\]\n]*\][ \t]*(.*)$", re.MULTILINE)

RTH_TASK = "Gamma_ConductorRTH"
AFTERHOURS_TASK = "Gamma_Conductor"


def _load_watermark() -> dict:
    default = {"last_fired_at_utc": None, "outbox_lines_seen": 0, "known_broken_marker": None}
    if not WATERMARK.exists():
        return default
    try:
        data = json.loads(WATERMARK.read_text(encoding="utf-8"))
        for k, v in default.items():
            data.setdefault(k, v)
        return data
    except Exception:  # noqa: BLE001 -- corrupted watermark, restart clean rather than crash
        return default


def _save_watermark(wm: dict) -> None:
    try:
        tmp = WATERMARK.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(wm, indent=2), encoding="utf-8")
        tmp.replace(WATERMARK)
    except Exception:  # noqa: BLE001 -- fail-open: a lost watermark just re-scans next tick
        pass


def scan_outbox_for_red(lines_seen: int) -> tuple[bool, int, str]:
    """Returns (event_found, new_total_line_count, evidence_snippet)."""
    if not OUTBOX.exists():
        return False, 0, ""
    try:
        lines = OUTBOX.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return False, lines_seen, ""
    total = len(lines)
    # File rotated/truncated shorter than our watermark -> treat as reset, scan tail only.
    start = lines_seen if 0 <= lines_seen <= total else max(0, total - 50)
    for raw in lines[start:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        # ONLY the "message" schema (self_check / mcp_audit / engine_health / preopen_readiness /
        # participation_daily / spend_summary -- every genuine infra-health producer). The
        # "content" schema is narrative/proposal/prospector/companion pings that legitimately use
        # emoji for emphasis (ADHD output style, CLAUDE.md SS2) -- live-verified false-positive:
        # a companion "Honest read on v15" narrative post containing a siren emoji for emphasis
        # was NOT an active RED, and scanning "content" would wake the conductor on every one.
        text = str(obj.get("message") or "")
        if text and RED_PATTERN.search(text):
            return True, total, text[:200]
    return False, total, ""


def _content_hash(payload: str) -> str:
    """Stable short hash of a Known-broken entry's payload (marker + text), with its
    [stamp] already stripped by the caller -- so a re-stamp of the SAME finding hashes
    identical and a genuinely NEW finding hashes different, regardless of what the
    producer put in the timestamp."""
    return hashlib.sha256(payload.strip().encode("utf-8")).hexdigest()[:16]


def scan_known_broken(prev_marker: str | None) -> tuple[bool, str | None]:
    """Returns (new_entry_found, latest_marker_token_or_prev).

    H1 FIX (GOAL-RIG-SIGNAL-HYGIENE-2026-09-05): this used to key "new entry" on the
    newest bullet's leading [timestamp] token (TS_TOKEN). status_known_broken.py's
    producers (engine_health.py's RTH-TICK-GAP in particular) re-stamp their line every
    tick even when the underlying finding hasn't changed, so a timestamp-keyed watermark
    read every re-stamp as a fresh event and woke the conductor every
    WAKE_DEBOUNCE_MIN on nothing (live evidence: "EVENT (known-broken) but DEBOUNCED"
    x30 the morning of 2026-09-05, 09:22-12:01 ET). Now keyed on a content hash of the
    newest entry's payload with its [stamp] stripped -- an unchanged finding hashes the
    same across ticks even if H1's OTHER fix (status_known_broken.upsert keeping the old
    stamp) somehow didn't already stop the timestamp from moving. `known_broken_marker`
    keeps its name (schema migration, not a rename) -- a pre-existing watermark holding an
    old raw-timestamp string simply won't equal any hash and costs exactly one harmless
    extra wake-fire on the first tick after this ships, never a crash."""
    if not STATUS_MD.exists():
        return False, prev_marker
    try:
        # Known broken section can be large historically; only the HEAD (newest entries,
        # this file is append-in-place at the point of the header, newest-first per the
        # existing self_check/mcp_audit writers) matters for freshness detection.
        text = STATUS_MD.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return False, prev_marker
    idx = text.find(KNOWN_BROKEN_HEADER)
    if idx == -1:
        return False, prev_marker
    section = text[idx: idx + 4000]  # first ~4KB after the header is plenty for the newest entry
    m = ENTRY_LINE_RE.search(section)
    if not m:
        return False, prev_marker
    latest = _content_hash(m.group(1))
    if latest == prev_marker:
        return False, prev_marker
    return True, latest


def is_rth(now_et: dt.datetime) -> bool:
    if now_et.weekday() >= 5:  # Sat=5, Sun=6
        return False
    start = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    end = now_et.replace(hour=15, minute=55, second=0, microsecond=0)
    return start <= now_et < end


def target_task(now_et: dt.datetime) -> str:
    return RTH_TASK if is_rth(now_et) else AFTERHOURS_TASK


def fire_task(task_name: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["schtasks", "/Run", "/TN", task_name],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        ok = proc.returncode == 0
        detail = (proc.stdout or proc.stderr or "").strip()[:200]
        return ok, detail
    except Exception as e:  # noqa: BLE001 -- fail-open
        return False, str(e)[:200]


def _safe_console() -> None:
    """Force UTF-8 stdout/stderr with a replace-on-error fallback. Without this, a Discord
    message containing an emoji (verified live: the siren marker this script matches on)
    crashes print() under Windows' default cp1252 console/pipe encoding -- the exact
    encoding-class silent-failure this codebase's self_check.py exists to catch elsewhere.
    Python 3.7+ only; guarded so an older interpreter degrades instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    _safe_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="detect + print, never Start- the task")
    ap.add_argument("--force", action="store_true", help="bypass the debounce window")
    args = ap.parse_args(argv)

    try:
        now_utc = dt.datetime.now(dt.timezone.utc)
        now_et = _et_now()
        if now_et.tzinfo is not None:
            now_et = now_et.replace(tzinfo=None)

        wm = _load_watermark()
        red1, total_lines, evidence = scan_outbox_for_red(wm["outbox_lines_seen"])
        red2, new_marker = scan_known_broken(wm["known_broken_marker"])
        event = red1 or red2

        wm["outbox_lines_seen"] = total_lines
        wm["known_broken_marker"] = new_marker

        if not event:
            print(f"[conductor-wake] no new RED evidence (outbox_lines={total_lines})")
            _save_watermark(wm)
            return 0

        last_fired = wm.get("last_fired_at_utc")
        debounced = False
        if last_fired and not args.force:
            try:
                last_dt = dt.datetime.fromisoformat(last_fired)
                elapsed_min = (now_utc - last_dt).total_seconds() / 60.0
                debounced = elapsed_min < WAKE_DEBOUNCE_MIN
            except Exception:  # noqa: BLE001
                debounced = False

        src = "outbox" if red1 else "known-broken"
        if debounced:
            print(f"[conductor-wake] EVENT ({src}) but DEBOUNCED (<{WAKE_DEBOUNCE_MIN}min since last wake) evidence={evidence!r}")
            _save_watermark(wm)
            return 0

        task = target_task(now_et)
        if args.dry_run:
            print(f"[conductor-wake] EVENT ({src}) DRY-RUN would fire {task} evidence={evidence!r}")
            _save_watermark(wm)
            return 0

        ok, detail = fire_task(task)
        wm["last_fired_at_utc"] = now_utc.isoformat()
        _save_watermark(wm)
        status = "FIRED" if ok else "FIRE_FAILED"
        print(f"[conductor-wake] EVENT ({src}) {status} task={task} detail={detail!r} evidence={evidence!r}")
        return 0
    except Exception as e:  # noqa: BLE001 -- absolute fail-open, this is a 5-min scheduled tick
        print(f"[conductor-wake] ERROR (fail-open, no-op): {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
