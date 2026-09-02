"""dead_mans_switch.py -- independent watchdog: flatten an open SPY option position if the
engine PROCESS has gone silent, closing go-live gate operational criterion 2's last named gap.

WHY THIS EXISTS (queue.md DEAD-MANS-SWITCH-POSITION-FLATTENER, filed 2026-08-29 Fable full
review; go_live_gate.py's own `operational_criterion()` names the gap verbatim):

    "heal-engine.ps1 restarts dead processes but does not flatten open positions;
     exit_actuator.py's orphan-position adoption only reconciles once the SAME process
     resumes ticking -- it is not an INDEPENDENT watchdog."

Three existing mechanisms and why none of them close this:
  * heal-engine.ps1        -- re-fires a dead heartbeat_core process (heals the BRAIN), but
                               never looks at broker positions. A healed-but-late brain still
                               leaves a position that sat unmanaged for the stale window.
  * exit_actuator.adopt_*  -- reconciles an orphaned position, but only runs INSIDE the next
                               tick of the SAME process. If the process is dead, this code
                               never executes -- it cannot resurrect itself.
  * eod_flatten.py         -- fires ONCE at 15:52 ET on a schedule. A process that dies at
                               10:00 ET leaves an open 0DTE position unmanaged for ~5h50m,
                               not until the scheduled backstop.

THIS SCRIPT is a separate, independent, /2min-scheduled process (setup/scripts/
install-dead-mans-switch.ps1 registers Gamma_DeadMansSwitch) that:
  1. Only runs RTH weekdays 09:32-15:58 ET (et_clock -- never Bash TZ). Outside that window
     there is nothing to protect (positions are flat or the flatten backstop already covers
     15:52-15:55 ET).
  2. For each ACTIVE SPY_0DTE_OPTION arm (accounts.json, reusing eod_flatten._active_arms()
     so the roster never drifts from the flatten backstop's own coverage): computes ENGINE
     LIVENESS as minutes since that arm's newest decision-ledger row. Core arms (safe-2,
     bold-2) read automation/state/core-decisions.jsonl (`account` field 'safe'/'bold', ts_et
     NAIVE ET wall-clock); fleet arms (safe-3, risky-1) read their own
     automation/state/fleet/<arm>/decisions.jsonl (`arm_id` field, ts_et AWARE ET-offset ISO).
  3. STALE_MIN = 10 -- strictly AFTER heal-engine.ps1's CORE_STALE_MIN=8 threshold plus a
     window for a heal attempt to land (heal-engine fires on the SAME 1-min cadence as the
     engine and needs ~60-90s for a re-fired tick to write a fresh row). Acting at minute 8
     would race the healer; acting at minute 10 gives it two full chances first.
  4. If an arm is stale AND the broker position-read for that arm SUCCEEDS AND it holds
     >=1 open SPY option position -> FLATTEN via fleet_broker.close_all_spy_options (the
     same primitive eod_flatten.py and heartbeat_core's exit path already use), verify with
     a second position read, append ONE loud line to automation/overnight/STATUS.md under
     '## Live watch', and write both automation/state/dead-mans-switch.json (latest snapshot)
     and a per-run row to automation/state/logs/dead-mans-switch-YYYY-MM-DD.jsonl.
  5. If an arm is stale but the broker READ ITSELF fails -> never guess. No flatten is
     attempted (fail-CLOSED on the action -- placing an order on unverified position state is
     strictly worse than doing nothing), but the failure is logged loudly (fail-OPEN on the
     process -- OP-25: a broken watchdog must never wedge the engine or crash the fire).
  6. A live (fresh) arm is recorded with no action.

DRY_RUN: set DMS_DRY=1 to force `close_all_spy_options(..., live=False)` -- reports what WOULD
close without placing any order (test/dry-run path, same convention as eod_flatten.py's
GAMMA_EOD_DRY).

NEVER RAISES. Every stage is wrapped; a bug in this watchdog must never take down the fire
that scheduled it, and must never be mistaken for "checked, fine" (OP-25 fail-open + C7 never
render an unmeasured state as a measured one).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---- path setup (mirrors eod_flatten.py pattern) ---------------------------------------
_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parents[1]
for _p in ("setup/scripts", "automation/state/fleet", "backtest/lib"):
    _pp = str(_REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

import fleet_broker  # noqa: E402 (from automation/state/fleet)
from et_clock import et_now  # noqa: E402 (from setup/scripts)

import importlib.util as _ilu  # noqa: E402

# Reuse eod_flatten's roster derivation VERBATIM (import, not re-implement) so this
# watchdog's coverage can never silently drift from the flatten backstop's own coverage --
# the exact class of bug (C14 dead/translated-but-unapplied) this repo has been burned by
# before when two things that must agree were hand-kept in sync instead.
_spec = _ilu.spec_from_file_location("eod_flatten_dms", _SCRIPTS / "eod_flatten.py")
_eod_flatten = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_eod_flatten)  # type: ignore[union-attr]

# ---- config ------------------------------------------------------------------------------
STALE_MIN = 10  # strictly > heal-engine.ps1's CORE_STALE_MIN=8 + a heal-attempt window
RTH_START = (9, 32)
RTH_END = (15, 58)

# Core arms log to the SHARED core-decisions.jsonl under a generic 'safe'/'bold' account
# label (heartbeat_core covers both accounts in one process). Any active arm NOT in this map
# is treated as a fleet arm reading its own per-arm automation/state/fleet/<arm>/decisions.jsonl.
CORE_ARM_ACCOUNT = {"safe-2": "safe", "bold-2": "bold"}

CORE_DECISIONS_PATH = _REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET_DIR = _REPO / "automation" / "state" / "fleet"
STATE_PATH = _REPO / "automation" / "state" / "dead-mans-switch.json"
STATUS_MD = _REPO / "automation" / "overnight" / "STATUS.md"
LOG_DIR = _REPO / "automation" / "state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Dry-run switch (2026-09-01, matches eod_flatten.py's GAMMA_EOD_DRY convention).
DRY = os.environ.get("DMS_DRY", "0") == "1"

TAIL_BYTES = 600_000  # generously covers >200 rows/account at ~2KB/row -- 90MB core-decisions
# .jsonl must NEVER be read in full on a /2min fire.


# ---- small helpers -------------------------------------------------------------------- #

def _et_ts() -> str:
    return et_now().strftime("%Y-%m-%d %H:%M:%S ET")


def _log_paths() -> "tuple[Path, Path]":
    date_str = et_now().strftime("%Y-%m-%d")
    return (
        LOG_DIR / f"dead-mans-switch-{date_str}.log",
        LOG_DIR / f"dead-mans-switch-{date_str}.jsonl",
    )


def _log(log_path: Path, msg: str) -> None:
    line = f"[{_et_ts()}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 -- logging must never crash the watchdog
        pass


def _append_jsonl(jsonl_path: Path, record: dict) -> None:
    try:
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _tail_text(path: Path, n_bytes: int = TAIL_BYTES) -> str:
    """Read only the last n_bytes of a (potentially huge) jsonl file. Never raises --
    returns "" on any read error, which callers treat as 'no data' (stale)."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > n_bytes:
                f.seek(size - n_bytes)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def is_rth(et: datetime) -> bool:
    """Weekday + 09:32-15:58 ET, inclusive. Outside this window there is nothing for the
    watchdog to protect (either the market is closed, or the pre-open/post-flatten window is
    covered by other mechanisms)."""
    if et.weekday() >= 5:
        return False
    start = et.replace(hour=RTH_START[0], minute=RTH_START[1], second=0, microsecond=0)
    end = et.replace(hour=RTH_END[0], minute=RTH_END[1], second=0, microsecond=0)
    return start <= et <= end


# ---- liveness ---------------------------------------------------------------------------- #

def core_liveness_minutes(account: str, et_now_naive: datetime) -> "float | None":
    """Minutes since the newest core-decisions.jsonl row for this account ('safe'/'bold').
    ts_et is NAIVE ET wall-clock (heartbeat_core's own convention, mirrored from
    heal-engine.ps1's Get-CoreStale). Returns None if the file/row is missing or unparseable
    -- callers treat None as maximally stale (worst case: total silence), never as 'fresh'."""
    text = _tail_text(CORE_DECISIONS_PATH)
    if not text:
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for raw in reversed(lines):
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if row.get("account") != account:
            continue
        ts_raw = row.get("ts_et")
        if not ts_raw:
            continue
        try:
            ts = datetime.strptime(str(ts_raw)[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        return (et_now_naive - ts).total_seconds() / 60.0
    return None


def fleet_liveness_minutes(arm: str, now_utc: datetime) -> "float | None":
    """Minutes since the newest automation/state/fleet/<arm>/decisions.jsonl row for this
    arm_id. ts_et here is AWARE (carries its own ET UTC offset), so age is computed in UTC
    -- correct across a DST boundary without needing et_clock's naive-ET convention. Returns
    None on any missing/unparseable data (treated as maximally stale by callers)."""
    path = FLEET_DIR / arm / "decisions.jsonl"
    text = _tail_text(path)
    if not text:
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for raw in reversed(lines):
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if row.get("arm_id") != arm:
            continue
        ts_raw = row.get("ts_et")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except ValueError:
            continue
        if ts.tzinfo is None:
            continue  # unexpected shape for this ledger -- skip rather than guess an offset
        return (now_utc - ts.astimezone(timezone.utc)).total_seconds() / 60.0
    return None


def arm_liveness_minutes(arm: str, et_now_naive: datetime, now_utc: datetime) -> "float | None":
    account = CORE_ARM_ACCOUNT.get(arm)
    if account is not None:
        return core_liveness_minutes(account, et_now_naive)
    return fleet_liveness_minutes(arm, now_utc)


def _utc_now() -> datetime:
    """Separated from `datetime.now(timezone.utc)` at the call site solely so tests can pin
    'now' consistently with a mocked `et_now()` (both must describe the SAME instant, or the
    core-ledger age and the fleet-ledger age would be computed against two different clocks)."""
    return datetime.now(timezone.utc)


# ---- STATUS.md / state surfaces ---------------------------------------------------------- #

def _append_status_line(msg: str) -> None:
    """Append ONE loud line under '## Live watch'. Never raises -- a failure to write the
    human-visible surface must not block the flatten it is reporting on."""
    try:
        line = f"\n- [{et_now().strftime('%Y-%m-%dT%H:%M:%S')} ET] {msg}\n"
        if STATUS_MD.exists():
            text = STATUS_MD.read_text(encoding="utf-8")
            marker = "## Live watch"
            idx = text.find(marker)
            if idx == -1:
                with STATUS_MD.open("a", encoding="utf-8") as f:
                    f.write(f"\n## Live watch\n{line}")
            else:
                insert_at = idx + len(marker)
                new_text = text[:insert_at] + line + text[insert_at:]
                STATUS_MD.write_text(new_text, encoding="utf-8")
        else:
            STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
            STATUS_MD.write_text(f"# STATUS\n\n## Live watch\n{line}", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _write_state_snapshot(report: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ---- per-arm check ------------------------------------------------------------------------ #

def check_arm(arm: str, creds_all: dict, et_now_naive: datetime, now_utc: datetime,
              log_path: Path, jsonl_path: Path) -> dict:
    """Never raises. Returns a result dict recording exactly what was observed and done."""
    result: dict = {"arm": arm, "ts": _et_ts(), "dry": DRY}
    try:
        liveness = arm_liveness_minutes(arm, et_now_naive, now_utc)
        stale = liveness is None or liveness > STALE_MIN
        result["liveness_min"] = liveness
        result["stale"] = stale

        if not stale:
            result["action"] = "LIVE_NO_ACTION"
            _append_jsonl(jsonl_path, result)
            return result

        if arm not in creds_all:
            msg = f"DMS_NO_CREDS arm={arm} -- stale (liveness={liveness}) but no creds to check broker"
            _log(log_path, msg)
            result["action"] = "NO_CREDS"
            _append_jsonl(jsonl_path, result)
            return result

        creds = creds_all[arm]
        positions, read_ok = fleet_broker.open_spy_option_positions_checked(creds)
        if not read_ok:
            msg = (f"DMS_RED arm={arm} liveness={liveness} STALE and broker position read "
                   f"FAILED -- CANNOT confirm open-position state. NOT flattening (fail-closed "
                   f"on the action). Manual check recommended.")
            _log(log_path, msg)
            result["action"] = "READ_FAILED"
            _append_jsonl(jsonl_path, result)
            return result

        qty_total = sum(abs(int(float(p.get("qty", 0)))) for p in positions)
        symbols = [str(p.get("symbol")) for p in positions]
        if qty_total == 0:
            msg = f"DMS_STALE_BUT_FLAT arm={arm} liveness={liveness} -- 0 open SPY option positions, nothing to flatten"
            _log(log_path, msg)
            result["action"] = "STALE_BUT_FLAT"
            _append_jsonl(jsonl_path, result)
            return result

        # ENGINE STALE + BROKER CONFIRMS AN OPEN POSITION -> FLATTEN.
        _log(log_path, (f"DMS_FIRE arm={arm} liveness={liveness}m qty={qty_total} "
                         f"symbols={symbols} dry={DRY}"))
        close_res = fleet_broker.close_all_spy_options(
            creds, live=(not DRY), arm=arm,
            reason=(f"DEAD_MANS_SWITCH: engine stale {liveness:.1f}m (> {STALE_MIN}m budget) "
                    f"-- process appears dead with an open SPY 0DTE position"))
        closed = close_res.get("closed") or close_res.get("would_close") or []
        errors = close_res.get("errors", [])

        # Verify with a SECOND read (never trust the close response alone -- matches
        # eod_flatten.py's retry-until-zero verification discipline).
        remaining_positions, verify_ok = fleet_broker.open_spy_option_positions_checked(creds)
        remaining = (sum(abs(int(float(p.get("qty", 0)))) for p in remaining_positions)
                     if verify_ok else None)

        msg = (f"DEAD-MANS-SWITCH FIRED :: {arm} :: engine stale {liveness:.1f}m :: "
               f"closed {closed}")
        _log(log_path, msg)
        if not DRY:
            _append_status_line(msg)

        result.update({
            "action": "FLATTENED" if not DRY else "DRY_RUN_WOULD_FLATTEN",
            "qty_before": qty_total,
            "closed": closed,
            "errors": errors,
            "remaining_after_verify": remaining,
            "verify_read_ok": verify_ok,
        })
        _append_jsonl(jsonl_path, result)
        return result

    except Exception as exc:  # noqa: BLE001 -- OP-25: this watchdog must never raise
        msg = f"DMS_ERROR arm={arm} exception={type(exc).__name__}: {exc}"
        try:
            _log(log_path, msg)
        except Exception:
            pass
        result["action"] = "ERROR"
        result["error"] = str(exc)
        try:
            _append_jsonl(jsonl_path, result)
        except Exception:
            pass
        return result


# ---- main ----------------------------------------------------------------------------- #

def main() -> int:
    """OP-25: this ENTIRE function must never raise -- a watchdog that crashes the scheduled
    task it runs under is worse than the gap it exists to close. Every internal stage already
    guards itself; this outer try/except is the last line of defense (mirrors the
    `if __name__` guard below, but also covers direct `main()` calls, e.g. from tests)."""
    try:
        return _main_inner()
    except Exception as exc:  # noqa: BLE001 -- absolute last resort
        try:
            print(f"DMS_FATAL {type(exc).__name__}: {exc}")
        except Exception:
            pass
        return 0


def _main_inner() -> int:
    try:
        et = et_now()
    except Exception as exc:  # noqa: BLE001 -- the clock itself must never crash this fire
        try:
            print(f"DMS_ERROR could not read et_now(): {type(exc).__name__}: {exc}")
        except Exception:
            pass
        return 0

    log_path, jsonl_path = _log_paths()

    if not is_rth(et):
        return 0  # nothing to protect outside 09:32-15:58 ET weekdays

    try:
        arms = list(_eod_flatten._active_arms())
    except Exception as exc:  # noqa: BLE001
        _log(log_path, f"DMS_ERROR roster read failed: {type(exc).__name__}: {exc} -- using core fallback")
        arms = ["safe-2", "bold-2"]

    try:
        creds_all = fleet_broker.load_creds()
    except Exception as exc:  # noqa: BLE001
        _log(log_path, f"DMS_CREDS_ERROR: {exc} -- cannot check any arm's broker state this fire")
        creds_all = {}

    now_utc = _utc_now()
    results = []
    for arm in arms:
        results.append(check_arm(arm, creds_all, et, now_utc, log_path, jsonl_path))

    report = {
        "last_run_et": _et_ts(),
        "dry": DRY,
        "stale_min_threshold": STALE_MIN,
        "per_arm": {r["arm"]: r for r in results},
    }
    _write_state_snapshot(report)
    _log(log_path, f"DMS_COMPLETE outcomes={[r.get('action') for r in results]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 -- absolute last resort: never let this
        # watchdog's own crash look like anything other than an exit-0 no-op to Task
        # Scheduler (OP-25 fail-open -- a broken watchdog must never wedge/alarm the box).
        try:
            print(f"DMS_FATAL {type(exc).__name__}: {exc}")
        except Exception:
            pass
        sys.exit(0)
