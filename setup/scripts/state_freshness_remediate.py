"""state_freshness_remediate -- direct-invocation remediator for STALE-BY-SESSION entries.

WHY THIS EXISTS (queue item STATE-FRESHNESS-AUTO-REMEDIATOR, filed 2026-08-10 conductor
AFTERHOURS from `strategy/candidates/_lesson-inbox/state-freshness-detector-no-remediator-
2026-08-10.md`)
--------------------------------------------------------------------------------------------
``state_freshness_audit.py`` (2026-07-30) DETECTS a stalled producer but only REPORTS it --
5 producers sat stale for 3-4 weeks (07-14/07-15 through 08-10) despite the audit firing
correctly every time, because nothing ever re-invoked the flagged producer. This module
closes that loop for the narrowest, safest slice of the problem: a file whose ONLY defect is
``STALE BY SESSION`` (the producer script itself is fine, it just has not run for today's
session yet) gets its producer re-invoked DIRECTLY, right here, in-process.

WHY *DIRECT* INVOCATION, NOT A TASK RESTART (see sibling module state_freshness_selfheal.py)
--------------------------------------------------------------------------------------------
A sibling module, ``state_freshness_selfheal.py`` (2026-07-31, currently UNWIRED -- no
scheduled task references it, confirmed 2026-09-02 via grep of SCHEDULED-TASKS.md), takes a
DIFFERENT approach: force-start the mapped Windows scheduled task via ``Start-ScheduledTask``.
That is the wrong mechanism for THIS lesson's root cause: the very incident that produced the
lesson-inbox item for this module found that the scheduled fires were completing with
``LastTaskResult=0`` and STILL not writing fresh content ("silently no-op'd"), while manually
re-running the exact same producer SCRIPT (bypassing the wscript -> vbs -> system-pythonw
relay chain entirely) fixed it INSTANTLY. Restarting the same scheduled task early does not
route around a fault that lives in the scheduled-task relay chain itself. This module invokes
the producer's ``.py`` file directly with ``sys.executable`` from THIS process -- the same
class of invocation that is proven to work in the lesson.

SCOPE -- ONLY "STALE BY SESSION", NEVER MISSING/UNKNOWN/malformed
-------------------------------------------------------------------
A MISSING file, an UNKNOWN (malformed/unreadable) payload, or a STALE-BY-AGE entry can mean
the manifest itself is wrong, the producer's output schema changed, or something more serious
than "hasn't run yet today" -- those need a human, not a silent auto-write. Only entries whose
entire reason list is the single string ``STALE BY SESSION ...`` are ever acted on
(`_is_stale_by_session_only`).

SAFETY RAILS
------------
1. Market-hours refusal: refuses to remediate anything (does not even run the audit) while
   ``now_et`` falls in the RTH trading band (09:30-15:55 ET, weekdays) -- the simplest safe
   option, per this module's own design brief, rather than per-writer RTH classification.
2. Explicit per-writer ALLOWLIST (`WRITER_ALLOWLIST`) of producers verified $0, idempotent,
   and free of any order-placement call (grepped for `place_option_order` /
   `place_stock_order` / `place_crypto_order` / `submit_order` -- none found in any allowlisted
   script, 2026-09-02). A writer field NOT in the allowlist is reported, never run -- this
   default-deny covers `heartbeat_core.py` (the live engine itself), the futures live-trading
   scripts, `build_shared_signal.py` (feeds the 1-min RTH fleet entry decision), and every
   multi-writer/LLM-prompt-primary field (`daily_loss_guard.py`'s kill-switch anchor,
   `premarket_deterministic_fallback.py`'s bias file) where re-running the WRONG half or
   resetting a kill-switch anchor outside premarket would itself be a rule violation.
3. Cooldown: at most one invocation attempt per WRITER per hour, persisted in
   ``automation/state/state-freshness-remediate.json`` -- a broken producer cannot be hammered.
4. Fail-open: a producer subprocess that raises or times out is caught, logged with a
   traceback tail, and the entry is simply left stale for the next pass -- never propagates.
5. Verify-after: remediation success is decided by re-running `state_freshness_audit.audit()`
   after the invocation and checking whether THAT entry is GREEN now -- never from the
   producer's own exit code (C7: silent success is failure, audit outputs not exit codes).

USAGE
-----
    python setup/scripts/state_freshness_remediate.py            # human summary
    python setup/scripts/state_freshness_remediate.py --json      # machine payload
    python setup/scripts/state_freshness_remediate.py --dry-run   # print what WOULD run, act on nothing

Guard: backtest/tests/test_state_freshness_remediate_2026_09_03.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import state_freshness_audit as sfa  # noqa: E402

STATE_PATH = REPO / "automation" / "state" / "state-freshness-remediate.json"
LOG_PATH = REPO / "automation" / "state" / "state-freshness-remediate-log.jsonl"
DEFAULT_COOLDOWN_MIN = 60
DEFAULT_TIMEOUT_SEC = 180

# ---------------------------------------------------------------------------
# Per-writer allowlist: EXACT `writer` string from state-freshness-manifest.json
# -> repo-relative script to invoke bare (`sys.executable <script>`). A writer
# string not present here is reported ("not_on_allowlist"), NEVER run.
#
# Every mapped script was checked 2026-09-02 for (a) a bare, arg-free `main()`
# entrypoint (no required CLI flags, no continuous-loop default) and (b) an
# absence of any order-placement call. See the module docstring's rail #2 for
# what is deliberately excluded and why.
# ---------------------------------------------------------------------------
WRITER_ALLOWLIST: dict[str, str] = {
    "setup/scripts/refresh_levels_intraday.py (+ premarket)":
        "setup/scripts/refresh_levels_intraday.py",
    "setup/scripts/level_memory_producer.py":
        "setup/scripts/level_memory_producer.py",
    "setup/scripts/context_bundle_producer.py":
        "setup/scripts/context_bundle_producer.py",
    "backtest/autoresearch/trendline_engine.py":
        "backtest/autoresearch/trendline_engine.py",
    "setup/scripts/confluence_producer.py":
        "setup/scripts/confluence_producer.py",
    "setup/scripts/sight_beacon.py":
        "setup/scripts/sight_beacon.py",
    "setup/scripts/trade_today_watcher.py":
        "setup/scripts/trade_today_watcher.py",
    "setup/scripts/broker_fills.py":
        "setup/scripts/broker_fills.py",
    "setup/scripts/premarket_readiness.py":
        "setup/scripts/premarket_readiness.py",
    "automation/scripts/compute_ema_snapshot.py":
        "automation/scripts/compute_ema_snapshot.py",
    "setup/scripts/macro_calendar.py / scout":
        "setup/scripts/macro_calendar.py",  # deterministic half only; "scout" is an LLM persona
}

# Deliberately NOT in the allowlist (manifest writer strings, verbatim, left here so the
# next reader can see the decision without re-deriving it from the manifest):
#   "automation/prompts/premarket.md + setup/scripts/premarket_deterministic_fallback.py"
#       -- multi-writer, primary half is an LLM prompt, not script-invokable
#   "automation/state/fleet/build_shared_signal.py"
#       -- feeds the 1-min RTH fleet entry decision directly; too tightly coupled to the
#          live tick to re-run out-of-band
#   "automation/prompts/premarket.md + setup/scripts/daily_loss_guard.py"
#       -- multi-writer AND resets the Rule-5 kill-switch equity anchor; re-running outside
#          premarket would itself be a rule violation
#   "setup/scripts/heartbeat_core.py"
#       -- the live trading engine itself; also a banned-for-edit trading-path file
#   "setup/scripts/futures_trader_runner.py -> futures_trader_core._write_heartbeat"
#       -- the armed futures intraday lane; can place real fillsim/broker orders
#   "backtest/futures/futures_live_data.write_freshness_snapshot"
#       -- a module.function, not a standalone script; also futures-lane adjacent
#   "backtest/futures/futures_eod.py"
#       -- futures-lane adjacent; excluded conservatively (blast radius not verified)
#   "setup/scripts/futures_trader_runner.py --backend tastytrade"
#       -- the real-broker (tastytrade) parity lane; can place real orders


# ---------------------------------------------------------------------------
# Clock (ET only; a clock failure REFUSES rather than guessing -- see run())
# ---------------------------------------------------------------------------

def _et_now() -> datetime:
    from et_clock import et_now  # noqa: PLC0415
    return et_now().replace(tzinfo=None)


def _in_trading_band(now_et: datetime) -> bool:
    """09:30-15:55 ET, weekdays -- the RTH heartbeat window (CLAUDE.md). Deliberately does
    NOT consult the holiday calendar: refusing on a holiday inside this window too is a
    harmless over-refusal, never a missed remediation window that mattered."""
    if now_et.weekday() >= 5:
        return False
    hhmm = now_et.strftime("%H:%M")
    return "09:30" <= hhmm <= "15:55"


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------

def _is_stale_by_session_only(entry: dict) -> bool:
    """True iff this entry's ENTIRE problem is a session-date staleness -- never MISSING,
    never UNKNOWN/malformed, never STALE BY AGE. Mirrors state_freshness_audit's own
    reason-string contract (evaluate_entry's axis-2 branch)."""
    if entry.get("status") not in ("RED", "YELLOW"):
        return False
    reasons = entry.get("reasons") or []
    if len(reasons) != 1:
        return False
    r = reasons[0]
    return "STALE BY SESSION" in r and "MISSING" not in r and "STALE BY AGE" not in r


# ---------------------------------------------------------------------------
# Cooldown state (per-writer, persisted)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt state = no cooldown, fail open
        return {}


def _save_state(d: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
        import os
        os.replace(tmp, STATE_PATH)
    except Exception:  # noqa: BLE001 -- best-effort persistence, never fatal
        pass


def _on_cooldown(writer: str, state: dict, now_et: datetime, cooldown_min: int) -> bool:
    last = state.get(writer, {}).get("last_attempt") if isinstance(state.get(writer), dict) else None
    if not last:
        return False
    try:
        last_dt = datetime.strptime(str(last)[:19], "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return False
    return (now_et - last_dt) < timedelta(minutes=cooldown_min)


# ---------------------------------------------------------------------------
# Producer invocation
# ---------------------------------------------------------------------------

def _default_starter(script_rel: str, dry_run: bool = False,
                      timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    """Invoke `<script_rel>` directly with `sys.executable`, bypassing the scheduled-task
    relay chain entirely (see module docstring for why that matters). Fails open: a raised
    exception (timeout, missing interpreter, permission error, or the producer's own crash
    surfacing as a nonzero return) is caught here and reported, never propagated."""
    script_path = REPO / script_rel
    cmd = [sys.executable, str(script_path)]
    if dry_run:
        return {"invoked": False, "dry_run": True, "cmd": cmd}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {
            "invoked": True,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-500:],
            "stderr_tail": (proc.stderr or "")[-500:],
        }
    except Exception as e:  # noqa: BLE001 -- a broken producer must never take this down
        return {
            "invoked": True,
            "error": f"{type(e).__name__}: {e}",
            "traceback_tail": traceback.format_exc()[-1500:],
        }


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, cooldown_min: int = DEFAULT_COOLDOWN_MIN,
        now_et: Optional[datetime] = None, starter: Callable = _default_starter,
        audit_fn: Optional[Callable[[], dict]] = None) -> dict:
    """Audit + direct-invoke remediation in one pass. NEVER raises -- any failure degrades
    to a reported UNKNOWN/refused result, matching state_freshness_audit's fail-open
    contract (rail #4)."""
    audit_fn = audit_fn or sfa.audit

    if now_et is None:
        try:
            now_et = _et_now()
        except Exception as e:  # noqa: BLE001 -- can't verify the clock => refuse, don't guess
            return {"verdict": "UNKNOWN", "refused": True,
                     "reason": f"clock unavailable, refusing to remediate: {type(e).__name__}: {e}",
                     "checked_at_et": None, "actions": []}

    if _in_trading_band(now_et):
        return {"verdict": None, "refused": True,
                 "reason": f"trading band ({now_et.strftime('%H:%M')} ET, weekday) -- "
                           f"refusing to remediate live-path state during RTH",
                 "checked_at_et": now_et.strftime("%Y-%m-%d %H:%M:%S"), "actions": []}

    try:
        pre = audit_fn()
    except Exception as e:  # noqa: BLE001
        return {"verdict": "UNKNOWN", "refused": False,
                 "reason": f"audit failed: {type(e).__name__}: {e}",
                 "checked_at_et": now_et.strftime("%Y-%m-%d %H:%M:%S"), "actions": []}

    candidates = [e for e in pre.get("entries", []) if _is_stale_by_session_only(e)]
    state = _load_state()
    actions: list[dict] = []
    invoked_writers: set[str] = set()

    for e in candidates:
        writer = e.get("writer")
        path = e.get("path")
        entry_out = {"path": path, "writer": writer,
                     "reason": (e.get("reasons") or [None])[0]}

        script_rel = WRITER_ALLOWLIST.get(writer)
        if script_rel is None:
            entry_out["outcome"] = "not_on_allowlist"
            actions.append(entry_out)
            continue

        entry_out["resolved_script"] = script_rel

        if _on_cooldown(writer, state, now_et, cooldown_min):
            entry_out["outcome"] = "skipped_cooldown"
            actions.append(entry_out)
            continue

        result = starter(script_rel, dry_run=dry_run)
        entry_out.update(result)
        entry_out["outcome"] = "dry_run" if dry_run else "invoked"
        actions.append(entry_out)
        if not dry_run:
            invoked_writers.add(writer)

    if invoked_writers and not dry_run:
        now_str = now_et.strftime("%Y-%m-%dT%H:%M:%S")
        for w in invoked_writers:
            state.setdefault(w, {})
            state[w]["last_attempt"] = now_str
        _save_state(state)

        # verify-after (rail #5): re-audit and decide `remediated` from THAT, never from
        # the subprocess's own exit code.
        try:
            post = audit_fn()
            post_by_path = {r.get("path"): r for r in post.get("entries", [])}
        except Exception:  # noqa: BLE001 -- verify-after failing must not hide the attempt
            post_by_path = {}
        for a in actions:
            if a["outcome"] != "invoked":
                continue
            post_entry = post_by_path.get(a["path"])
            a["remediated"] = bool(post_entry) and post_entry.get("status") == "GREEN"

    out = {
        "verdict": pre.get("verdict"),
        "refused": False,
        "checked_at_et": now_et.strftime("%Y-%m-%d %H:%M:%S"),
        "n_candidates": len(candidates),
        "actions": actions,
    }

    if actions and not dry_run:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now_et.strftime("%Y-%m-%dT%H:%M:%S"), **out}) + "\n")
        except Exception:  # noqa: BLE001 -- logging must never break the remediation
            pass

    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Directly re-invoke producers for state-freshness entries whose ONLY "
                     "problem is STALE BY SESSION.")
    ap.add_argument("--json", action="store_true", help="emit the machine payload")
    ap.add_argument("--dry-run", action="store_true",
                     help="print what WOULD be invoked; never actually runs a producer or "
                          "consumes a cooldown slot")
    ap.add_argument("--cooldown-min", type=int, default=DEFAULT_COOLDOWN_MIN)
    args = ap.parse_args(argv)

    out = run(dry_run=args.dry_run, cooldown_min=args.cooldown_min)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if out.get("refused"):
            print(f"REFUSED: {out.get('reason')}")
        else:
            print(f"verdict={out.get('verdict')} n_candidates={out.get('n_candidates', 0)} "
                  f"actions={len(out.get('actions', []))}")
            for a in out.get("actions", []):
                extra = ""
                if "remediated" in a:
                    extra = f" remediated={a['remediated']}"
                elif "returncode" in a:
                    extra = f" rc={a['returncode']}"
                elif "error" in a:
                    extra = f" error={a['error']}"
                print(f"  {a.get('path')}: {a.get('outcome')} -> {a.get('resolved_script') or a.get('writer')}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
