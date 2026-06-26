#!/usr/bin/env python3
"""Deterministic post-tick persistence writer for the SPY 0DTE heartbeat.

WHY THIS EXISTS
---------------
The Safe heartbeat (``automation/prompts/heartbeat.md``, fired by
``run-heartbeat.ps1`` via ``claude --print`` on Haiku) sometimes emits its
one-line ``HB#`` summary to the log but exits WITHOUT appending a row to
``automation/state/decisions.jsonl`` -- the state-write phase sits at the very
end of a ~105KB prompt and a heavy-context Haiku run can run out of steam
before it gets there (2026-06-25: decisions.jsonl froze at the 10:23 tick while
the model kept emitting ``HB#`` lines; loop-state.json was observed empty ``{}``).
On top of that, the prompt's own ledger contract intentionally *skips* plain-HOLD
ticks ("these are noise, not decisions"), which leaves audit gaps that look like
a freeze even when the model behaved.

This script makes the decisions-ledger write NON-SKIPPABLE and independent of the
LLM. It runs AFTER ``claude --print`` returns (wired into ``run-heartbeat.ps1``),
reads the ``HB#`` line the model just emitted to the heartbeat log, and -- if the
LLM did not already persist a row for this tick -- synthesises a lean
``decisions.jsonl`` row from that line. Idempotent: it never duplicates a row the
LLM already wrote (dedup is by ``date`` + ``time_et``).

It also self-heals a degraded ``loop-state.json`` (empty ``{}`` / missing
``session_id`` / stale session) -- but ONLY in that degraded case, never
clobbering a healthy file. It deliberately does NOT touch ``current-position.json``
(an order's strike/qty/bracket-ids cannot be reconstructed from a one-liner --
that persistence stays the LLM's job, backstopped by ``atomic_bracket_guard.py``).

MODES
-----
  (default, per-tick)  process the LAST tick in today's log -- the post-tick hook.
  --backfill-day       process EVERY tick in today's log, backfilling all gaps.
                       Doubles as an EOD reconciler and as the test entry point.

Pure stdlib, $0, fail-open: any error is logged to stderr and the script exits 0
so it can never block or alter the heartbeat's own exit code. Anchored to
``__file__`` (L21/C9). PowerShell 5.1-friendly invocation via Invoke-PythonHidden.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - zoneinfo always present on 3.9+
    _ET = None

# Repo root = two levels up from setup/scripts/this_file.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(ROOT, "automation", "state", "logs")

# Actions that represent a HALTED engine (kill-switch / circuit-breaker), not a
# decision. We do NOT write rows for these -- they repeat every 3 min for hours
# and would bloat the ledger (cf. the watcher-observations bloat -> RED incident).
HALTED_ACTIONS = {"PAUSED", "TRIPPED"}

# Canonical action vocabulary (heartbeat.md "Output - ONE LINE ONLY"). Used to
# validate the parsed token; an unknown token still writes (tagged) so we never
# silently drop a tick, but a known token is preferred.
KNOWN_ACTIONS = {
    "HOLD", "HOLD_DEV", "ENTER_BULL", "ENTER_BEAR",
    "EXIT_TP1", "EXIT_RUNNER", "EXIT_STOP", "EXIT_TIME",
    "SKIP_STALE", "SKIP_TV_DATA_STALE", "SKIP_LIQUIDITY", "SKIP_NEWS",
    "SKIP_GATE", "SKIP_FIRST_ENTRY_RULE", "STATE_DRIFT_BLOCKED_ENTRY",
    "PAUSED", "TRIPPED", "ERROR_TV", "ERROR_ALPACA", "ALPACA_RETRY_EXHAUSTED",
    "WATCH_ONLY", "ORB_WOULD_ENTER", "FBW_WOULD_ENTER",
    "SKIP_WATCH_TRIPPED", "SKIP_WATCH_PDT",
}

ACCOUNTS = {
    "safe": {
        "log_task": "heartbeat",
        "decisions": os.path.join(ROOT, "automation", "state", "decisions.jsonl"),
        "loop_state": os.path.join(ROOT, "automation", "state", "loop-state.json"),
        "position": os.path.join(ROOT, "automation", "state", "current-position.json"),
    },
    "bold": {
        "log_task": "heartbeat_aggressive",
        "decisions": os.path.join(ROOT, "automation", "state", "aggressive", "decisions.jsonl"),
        "loop_state": os.path.join(ROOT, "automation", "state", "aggressive", "loop-state.json"),
        "position": os.path.join(ROOT, "automation", "state", "aggressive", "current-position-bold.json"),
    },
}

# --- HB# line parsing -------------------------------------------------------
# Canonical format (heartbeat.md):
#   HB#{n} {hh:mm} {ACTION} | spy={x} ribbon={spread}c({stack}) vix={x}({dir}) bear={n}/10 bull={n}/11 htf={stack} | {reason}
# Real logs are messier: tick label may be `--` or garbage (HB#847), middle
# fields may be empty (spy= ribbon=), scores may be `skip`/`?`, extra `|`
# segments appear (BEACON_STALE). The parser tolerates all of that.
_HB_HEAD = re.compile(r"HB#(?P<label>\S+)\s+(?P<time>\d{1,2}:\d{2})\s+(?P<action>[A-Z][A-Z0-9_]*)")
_FIRE_IDX = re.compile(r"FIRE\b.*?\bidx=(\d+)")
_START = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ET === START tick")


def _f(pattern: str, text: str):
    m = re.search(pattern, text)
    return m.group(1) if m else None


def parse_hb_line(line: str):
    """Parse one ``HB#`` log line into a dict, or return ``None`` if it isn't one."""
    head = _HB_HEAD.search(line)
    if not head:
        return None
    action = head.group("action")
    spy = _f(r"spy=([0-9]+(?:\.[0-9]+)?)", line)
    rib = re.search(r"ribbon=([0-9]+(?:\.[0-9]+)?)c\(([A-Za-z?]+)\)", line)
    vix = re.search(r"vix=([0-9]+(?:\.[0-9]+)?)\(([a-z_?]+)\)", line)
    bear = _f(r"bear=([0-9]+)\s*/\s*10", line)
    bull = _f(r"bull=([0-9]+)\s*/\s*11", line)
    htf = _f(r"htf=([A-Za-z]+)", line)
    # Reason = text after the LAST '|' (the canonical one-clause reason segment).
    reason = line.split("|")[-1].strip() if "|" in line else None
    if reason == "":
        reason = None

    def _num(v, cast):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    stack = None
    spread = None
    if rib:
        spread = _num(rib.group(1), float)
        spread = int(round(spread)) if spread is not None else None
        s = rib.group(2).upper()
        stack = s if s in ("BULL", "BEAR", "MIXED") else None
    htf_stack = None
    if htf and htf.upper() in ("BULL", "BEAR", "MIXED"):
        htf_stack = htf.upper()
    return {
        "hb_label": head.group("label"),
        "time_et": _norm_time(head.group("time")),
        "action": action,
        "spy": _num(spy, float),
        "ribbon_stack": stack,
        "ribbon_spread_cents": spread,
        "vix": _num(vix.group(1), float) if vix else None,
        "vix_dir": vix.group(2) if vix else None,
        "bear_score": _num(bear, int),
        "bull_score": _num(bull, int),
        "htf_15m_stack": htf_stack,
        "reason": reason,
        "raw": line.strip(),
    }


def _norm_time(t: str) -> str:
    """``9:48`` -> ``09:48`` so dedup keys are stable."""
    hh, mm = t.split(":")
    return f"{int(hh):02d}:{mm}"


# --- log iteration ----------------------------------------------------------
def iter_ticks(log_text: str):
    """Yield one record per heartbeat tick in the log, in file order.

    A tick = a ``=== START tick`` marker, the nearest preceding ``FIRE ... idx=``
    (the wall-clock tick index), and the FIRST ``HB#`` line emitted after START
    (the model's canonical one-liner). Ticks with a START but no HB# line (the
    model crashed/timed out before output) yield ``hb=None``.
    """
    lines = log_text.splitlines()
    # Index of every START and the running "last seen FIRE idx".
    starts = []  # (line_idx, start_ts, fire_idx)
    last_fire = None
    for i, ln in enumerate(lines):
        fm = _FIRE_IDX.search(ln)
        if fm:
            last_fire = int(fm.group(1))
        sm = _START.search(ln)
        if sm:
            starts.append((i, sm.group("ts"), last_fire))
    for k, (li, ts, fire_idx) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        hb = None
        for ln in lines[li + 1:end]:
            hb = parse_hb_line(ln)
            if hb:
                break
        yield {"start_ts": ts, "fire_idx": fire_idx, "hb": hb}


# --- decisions.jsonl IO -----------------------------------------------------
def existing_time_ets(decisions_path: str, date: str):
    """Set of ``time_et`` values already present for ``date`` (dedup key)."""
    seen = set()
    if not os.path.exists(decisions_path):
        return seen
    try:
        with open(decisions_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if row.get("date") == date and row.get("time_et"):
                    seen.add(_norm_time(str(row["time_et"])))
    except OSError:
        pass
    return seen


def synthesize_row(hb: dict, fire_idx, date: str, account: str, position_status):
    """Build a canonical lean decisions.jsonl row from a parsed HB# line."""
    tick_id = fire_idx if fire_idx is not None else _tick_id_from_time(hb["time_et"])
    return {
        "tick_id": tick_id,
        "date": date,
        "time_et": hb["time_et"],
        "action": hb["action"],
        "position_status": position_status,
        "bull_score": hb["bull_score"] if hb["bull_score"] is not None else 0,
        "bear_score": hb["bear_score"] if hb["bear_score"] is not None else 0,
        "spy": hb["spy"],
        "vix": hb["vix"],
        "vix_dir": hb["vix_dir"],
        "ribbon_stack": hb["ribbon_stack"],
        "ribbon_spread_cents": hb["ribbon_spread_cents"],
        "htf_15m_stack": hb["htf_15m_stack"],
        "setup_name": None,
        "trigger": None,
        "trigger_fired_this_tick": False,
        "reason": hb["reason"],
        "account_id": account,
        "source": "post_tick_writer",
        "writer_note": "synthesized from HB# log line; LLM did not persist a decisions row this tick",
        "decision_grade": None,
        "decision_grade_basis": "no_fwd_bars",
    }


def _tick_id_from_time(time_et: str) -> int:
    """Wall-clock tick index = floor((t - 09:30)/3), matching run-heartbeat.ps1."""
    try:
        hh, mm = (int(x) for x in time_et.split(":"))
        return max(0, (hh * 60 + mm - (9 * 60 + 30)) // 3)
    except Exception:
        return 0


def append_row(decisions_path: str, row: dict):
    os.makedirs(os.path.dirname(decisions_path), exist_ok=True)
    with open(decisions_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


# --- loop-state recovery (degraded case only) -------------------------------
def maybe_recover_loop_state(loop_path: str, date: str, hb: dict, now_iso: str) -> bool:
    """Seed a MINIMAL valid loop-state ONLY if it is empty/missing/stale.

    Never overwrites a healthy file (one carrying today's ``session_id``). This
    targets the exact ``{}``-freeze symptom without risking the throttle/hash
    state a healthy loop-state drives.
    """
    state = None
    if os.path.exists(loop_path):
        try:
            with open(loop_path, "r", encoding="utf-8") as fh:
                state = json.loads(fh.read() or "{}")
        except (OSError, json.JSONDecodeError):
            state = None
    healthy = isinstance(state, dict) and state.get("session_id") == date and len(state) > 1
    if healthy:
        return False
    seed = {
        "schema_version": 3,
        "session_id": date,
        "last_change_at": now_iso,
        "last_change_reason": "post_tick_writer_recovery (loop-state was empty/stale)",
        "current_mode": (state or {}).get("current_mode", "BASE"),
        "writes_today": int((state or {}).get("writes_today", 0)) + 1,
        "ticks_today": (state or {}).get("ticks_today", 0),
        "spy": {"last": hb.get("spy"), "session_high": None, "session_low": None},
        "next_tick_model": "haiku",
        "_note": "minimal seed by heartbeat_persist_writer; full state resumes next LLM tick",
    }
    try:
        os.makedirs(os.path.dirname(loop_path), exist_ok=True)
        with open(loop_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(seed, indent=2))
        return True
    except OSError:
        return False


# --- main -------------------------------------------------------------------
def _now_et(override: str | None):
    if override:
        return datetime.strptime(override, "%Y-%m-%dT%H:%M:%S")
    if _ET is not None:
        return datetime.now(_ET).replace(tzinfo=None)
    return datetime.utcnow()


def read_position_status(position_path: str):
    if not os.path.exists(position_path):
        return None
    try:
        with open(position_path, "r", encoding="utf-8") as fh:
            pos = json.loads(fh.read() or "{}")
        st = pos.get("status")
        return st if st not in (None, "null", "none", "") else None
    except (OSError, json.JSONDecodeError):
        return None


def process(account: str, *, backfill: bool, max_start_age_sec: int,
            now_override: str | None, log_override: str | None,
            dry_run: bool, silent: bool) -> int:
    cfg = ACCOUNTS[account]
    now = _now_et(now_override)
    date = now.strftime("%Y-%m-%d")
    log_path = log_override or os.path.join(LOG_DIR, f"{cfg['log_task']}-{date}.log")
    if not os.path.exists(log_path):
        if not silent:
            print(f"[persist-writer] no log for {account} at {log_path}", file=sys.stderr)
        return 0
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        log_text = fh.read()

    ticks = list(iter_ticks(log_text))
    if not ticks:
        return 0

    if not backfill:
        # Per-tick mode: only the LAST tick, and only if its START is recent
        # (else this invocation didn't actually run claude -- LOCK_BUSY / skip).
        last = ticks[-1]
        try:
            start_dt = datetime.strptime(last["start_ts"], "%Y-%m-%d %H:%M:%S")
            age = (now - start_dt).total_seconds()
        except (ValueError, KeyError):
            age = 0
        if age > max_start_age_sec:
            if not silent:
                print(f"[persist-writer] last tick START is {int(age)}s old "
                      f"(> {max_start_age_sec}s) -- no fresh tick to persist", file=sys.stderr)
            return 0
        ticks = [last]

    seen = existing_time_ets(cfg["decisions"], date)
    position_status = read_position_status(cfg["position"])
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
    written = 0
    recovered_loop = False
    for t in ticks:
        hb = t["hb"]
        if hb is None:
            continue  # tick produced no HB# line (timeout/crash) -- nothing to parse
        if hb["action"] in HALTED_ACTIONS:
            continue  # PAUSED / TRIPPED: halted state, not a decision
        if hb["time_et"] in seen:
            continue  # LLM already persisted this tick -- idempotent no-op
        row = synthesize_row(hb, t["fire_idx"], date, account, position_status)
        if dry_run:
            print(json.dumps(row, separators=(",", ":")))
        else:
            append_row(cfg["decisions"], row)
            if not recovered_loop:
                recovered_loop = maybe_recover_loop_state(
                    cfg["loop_state"], date, hb, now_iso)
        seen.add(hb["time_et"])
        written += 1

    if not silent:
        tag = "DRY-RUN " if dry_run else ""
        extra = " loop_state_recovered" if recovered_loop else ""
        print(f"[persist-writer] {tag}{account}: wrote {written} backfill row(s){extra}",
              file=sys.stderr)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic post-tick decisions.jsonl writer")
    ap.add_argument("--account", choices=("safe", "bold"), default="safe")
    ap.add_argument("--backfill-day", action="store_true",
                    help="process EVERY tick in today's log, not just the last")
    ap.add_argument("--max-start-age-sec", type=int, default=360,
                    help="per-tick mode: skip if the last START is older than this")
    ap.add_argument("--now-et", default=None, help="override 'now' (YYYY-MM-DDTHH:MM:SS), for tests")
    ap.add_argument("--log", default=None, help="override the log path, for tests")
    ap.add_argument("--dry-run", action="store_true", help="print rows instead of appending")
    ap.add_argument("--silent", action="store_true")
    args = ap.parse_args(argv)
    try:
        process(args.account, backfill=args.backfill_day,
                max_start_age_sec=args.max_start_age_sec, now_override=args.now_et,
                log_override=args.log, dry_run=args.dry_run, silent=args.silent)
    except Exception as exc:  # fail-open: never block or fail the heartbeat
        print(f"[persist-writer] non-fatal error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
