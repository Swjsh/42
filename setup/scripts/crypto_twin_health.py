"""crypto_twin_health.py -- T3: visibility instruments for the CRYPTO TWIN (OP-33c).

markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md's T3 build order: "funnel/autopsy/
glance wiring + Gamma_CryptoTwin registration + 48h soak". This module is the
"glance wiring" half. It is a THIN WRAPPER AROUND crypto_twin_core.run_tick() --
T1/T2's tested (40/40) surface is imported and called, NEVER edited by this file.

Gamma_CryptoTwin's scheduled task invokes THIS file (not crypto_twin_core.py
directly) every 5 min, 24/7, because:

  1. crypto_twin_broker deliberately fail-louds on a genuine HTTP/network failure
     (see its module docstring: "Raises on a genuine HTTP/network failure"). Under
     the flash-free wscript->run_exe_hidden.vbs->pythonw chain, pythonw.exe has no
     console -- an uncaught exception's traceback goes to a stderr nobody reads.
     That is a SILENT failure mode (OP-33a: "never claim a tick worked without a
     quoted check" cuts both ways -- a crash nobody recorded is functionally
     indistinguishable from "nothing happened" without a wrapper that catches it and
     writes down what happened). run_tick_with_health() is that outermost net: it
     can print/return an error but it must never itself raise.

  2. automation/state/twin-health.json is a TOP-LEVEL glance file -- a deliberate,
     narrow exception to T1/T2's "zero writes outside crypto-twin/" namespace-
     isolation hard rail (see crypto_twin_core.py's module docstring + the static
     AST guard in test_crypto_twin_core.py, which is intentionally NOT extended to
     this file -- see test_crypto_twin_health.py's own path-identity tests instead).
     It sits next to engine-health.json / self-check-last.json / dress-rehearsal.json
     because that is where J already looks (automation/state/*.json), not buried
     inside the twin's own private ledger directory.

  3. automation/state/crypto-twin/soak-log.jsonl accrues ONE summary row per elapsed
     ET hour (watermarked -- a restart or a multi-hour gap never double-counts or
     loops trying to backfill; it just reports the true period it covers), so T4's
     soak report (crypto_twin_soak_report.py) never has to re-derive a full history
     from raw decisions.jsonl by hand.

Every function here reads either T1/T2's own append-only ledgers (decisions.jsonl,
journal.jsonl, breaker.json) or crypto_twin_broker's creds loader -- never a second
source of truth for the same fact (ticks_today and n_orders_lifetime are RE-DERIVED
from the ledgers on every call, not a separately persisted counter that could drift).

B1c ADDITION (2026-07-11, markdown/planning/TWIN-PROGRAM.md): twin-health.json now also
carries {path_coverage, branches_green_today, incidents_today}, RE-DERIVED every call
from crypto_twin_scenarios.py's path-coverage.json (same "never a second source of
truth" discipline as the rest of this file -- no separately persisted green/incident
counter that could drift from the scoreboard itself). B1b ADDITION: the wrapped tick now
calls crypto_twin_scenarios.run_scenario_tick() instead of crypto_twin_core.run_tick()
directly -- the scenario scheduler's own network-free scheduling step degrades to
"run organically" on any internal error (see that module's run_scenario_tick
docstring), so this file's own outermost catch-all is still the true last line of
defense for a genuine crypto_twin_core.run_tick() failure (network/HTTP/broker).

TWIN-B1.5-WIRE (2026-07-16): run_scenario_tick() itself now ALSO ticks the SIM-tier bear
lane (crypto_twin_scenarios.run_sim_bear_tick(), TWIN-B1.5) every call, wrapped in its own
try/except inside that function so a SIM-lane bug can never turn this file's row into a
TICK_ERROR. No edit was needed here -- run_tick_with_health's `row = cts.run_scenario_tick(
...)["row"]` line is unchanged; the sim-bear result rides along in the same dict under
`result["sim_bear"]` for any caller (this file's own CLI does not surface it -- see
crypto_twin_scenarios.py's own `main()` / `--sim-bear` flag for a direct, visible run).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "crypto-twin-health.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "crypto-twin-health.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_broker as broker  # noqa: E402
import crypto_twin_scenarios as cts  # noqa: E402

STATE = REPO / "automation" / "state"
# TOP-LEVEL glance file -- deliberately a sibling of engine-health.json/
# self-check-last.json, NOT under automation/state/crypto-twin/. See module docstring.
HEALTH_PATH = STATE / "twin-health.json"


# --- fail-open JSONL reader (shared by every counter below) ----------------------------
def _read_jsonl(path: Path) -> list[dict]:
    """Missing file -> []. A malformed individual line is skipped, never aborts the
    whole read (this is a READ-side tolerance for glance/reporting code -- state-file
    corruption RECOVERY is _shared.ps1's Repair-StateFiles' job, not this module's)."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# --- the four health facts --------------------------------------------------------------
def count_ticks_today(decisions_path: Path, today_et: str) -> int:
    """Count of decisions.jsonl rows whose ts_et falls on `today_et` (YYYY-MM-DD).
    Every tick (HOLD, ENTER, MANAGED, HOLD_BAD_BARS, or this module's own TICK_ERROR)
    writes exactly one decisions.jsonl row, so this is precisely "how many times the
    scheduled task fired today", re-derived fresh every call -- self-healing across
    restarts, can never drift from a separately maintained counter."""
    rows = _read_jsonl(decisions_path)
    return sum(1 for r in rows if str(r.get("ts_et", "")).startswith(today_et))


def count_orders_lifetime(journal_path: Path) -> int:
    """Count of journal.jsonl 'PLACED' events whose broker order response carries no
    _error/_refused/_skipped marker -- i.e. genuinely ACCEPTED by Alpaca, not merely
    attempted (place_entry always journals PLACED before checking the response).
    Reads 0 while BLOCKED_NO_ACCOUNT, honestly, since place_entry is never reached on
    that path (run_tick short-circuits before calling it)."""
    rows = _read_jsonl(journal_path)
    n = 0
    for r in rows:
        if r.get("event") != "PLACED":
            continue
        order = r.get("order")
        if isinstance(order, dict) and not (order.get("_error") or order.get("_refused") or order.get("_skipped")):
            n += 1
    return n


def account_status() -> str:
    """'LIVE' when a dedicated twin account is configured AND Alpaca has activated crypto
    on it; 'BLOCKED_NO_ACCOUNT' when secrets.json has no 'twin' entry yet (FileNotFoundError
    = not created, KeyError = file exists but missing the entry); 'BLOCKED_CRYPTO_NOT_APPROVED'
    when the account exists/authenticates but crypto_status != 'ACTIVE' (mirrors run_tick's
    own creds try/except exactly, including the crypto-approval check added 2026-07-11 after
    confirming via Alpaca's docs + live account reads that crypto shares an account's existing
    approval state, not a separate account type -- see crypto_twin_broker.CryptoNotApprovedError).
    NOTE: 'LIVE' describes ACCOUNT CONFIGURATION, not order placement -- whether orders
    actually fire additionally depends on the task's own --live flag, which is separate (and
    already on, safely no-op'ing, per the T3 build note)."""
    try:
        broker.get_twin_creds()
        return "LIVE"
    except (FileNotFoundError, KeyError):
        return "BLOCKED_NO_ACCOUNT"
    except broker.CryptoNotApprovedError:
        return "BLOCKED_CRYPTO_NOT_APPROVED"


def _read_breaker_tripped(cfg: ctc.TwinConfig) -> Optional[bool]:
    p = cfg.state_dir / "breaker.json"
    if not p.exists():
        return None
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("tripped", False))
    except (OSError, json.JSONDecodeError):
        return None


# --- B1c: path-coverage scoreboard summary (fail-open, RE-DERIVED every call) -----------
def _read_path_coverage_doc(cfg: ctc.TwinConfig) -> dict:
    p = cfg.state_dir / "path-coverage.json"
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def summarize_path_coverage(coverage_doc: dict) -> dict:
    """{path_coverage, branches_green_today, incidents_today} from a path-coverage.json
    doc (crypto_twin_scenarios._load_coverage's on-disk shape). Fail-open on a
    missing/malformed doc (empty branches dict, zero counts) -- never raises, mirrors
    every other fact in this file. `path_coverage` carries EACH branch's tier alongside
    its status so a downstream reader (the firm-brief line, B2) can render e.g. "5/6 LIVE
    branches green, bear-sim lane pending" without re-deriving tier from BRANCH_REGISTRY
    itself."""
    branches = coverage_doc.get("branches", {}) if isinstance(coverage_doc, dict) else {}
    rendered: dict = {}
    green = 0
    incidents = 0
    for name, rec in branches.items():
        if not isinstance(rec, dict):
            continue
        status = rec.get("status", "PENDING")
        rendered[name] = {
            "tier": rec.get("tier", "LIVE"),
            "status": status,
            "count_today": rec.get("count_today", 0),
            "last_exercised_utc": rec.get("last_exercised_utc"),
            "last_result": rec.get("last_result"),
        }
        if status == "GREEN":
            green += 1
        elif status == "INCIDENT":
            incidents += 1
    return {"path_coverage": rendered, "branches_green_today": green, "incidents_today": incidents}


# --- twin-health.json --------------------------------------------------------------------
def write_twin_health(cfg: ctc.TwinConfig, *, row: Optional[dict], error: Optional[str],
                      now_et: datetime, health_path: Path = HEALTH_PATH) -> dict:
    """Builds + writes the twin-health.json snapshot. `health_path` defaults to the
    production HEALTH_PATH but is an explicit override (mirrors run_tick's own
    injectable now_utc/raw_bars pattern) so tests never touch the real file.

    last_error reflects ONLY this tick -- None means THIS tick was clean, even if a
    prior tick errored (history lives in decisions.jsonl's TICK_ERROR rows + the
    soak-log's per-hour n_errors, not here; this file is a "right now" glance)."""
    today_et = now_et.strftime("%Y-%m-%d")
    coverage_summary = summarize_path_coverage(_read_path_coverage_doc(cfg))
    health = {
        "last_tick_et": now_et.isoformat(),
        "ticks_today": count_ticks_today(cfg.state_dir / "decisions.jsonl", today_et),
        "last_action": (row or {}).get("action"),
        "breaker_tripped": _read_breaker_tripped(cfg),
        "account_status": account_status(),
        "n_orders_lifetime": count_orders_lifetime(cfg.state_dir / "journal.jsonl"),
        "last_error": error,
        **coverage_summary,  # B1c: path_coverage, branches_green_today, incidents_today
    }
    health_path.parent.mkdir(parents=True, exist_ok=True)
    health_path.write_text(json.dumps(health, indent=2), encoding="utf-8")
    return health


# --- soak-log.jsonl (hourly rollup, watermarked) ------------------------------------------
def _soak_log_path(cfg: ctc.TwinConfig) -> Path:
    return cfg.state_dir / "soak-log.jsonl"


def _soak_watermark_path(cfg: ctc.TwinConfig) -> Path:
    return cfg.state_dir / "soak-watermark.json"


def _load_watermark(cfg: ctc.TwinConfig) -> Optional[str]:
    p = _soak_watermark_path(cfg)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_period_end_et")
    except (OSError, json.JSONDecodeError):
        return None


def _save_watermark(cfg: ctc.TwinConfig, period_end_et: str) -> None:
    p = _soak_watermark_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_period_end_et": period_end_et}, indent=2), encoding="utf-8")


def _hour_floor(now_et: datetime) -> datetime:
    return now_et.replace(minute=0, second=0, microsecond=0)


def append_soak_row_if_due(cfg: ctc.TwinConfig, *, now_et: datetime) -> Optional[dict]:
    """Appends ONE soak-log.jsonl row per elapsed ET hour. Watermarked via
    soak-watermark.json (persisted on disk -- survives a task restart, so a gap never
    re-rolls-up an hour twice) -- returns None on every call that is NOT the first
    tick to cross an hour boundary (the common case: 11 of every 12 ticks at 5-min
    cadence). A multi-hour gap (e.g. the box was off overnight) does not loop trying
    to backfill one row per skipped hour -- it produces ONE honest row whose
    period_start/period_end span the true gap, which is simpler and cannot spin.

    Summarizes decisions.jsonl rows in [period_start, hour_floor): tick count,
    TICK_ERROR count, and the full action distribution (HOLD/ENTERED/MANAGED/
    TICK_ERROR/... counts) -- everything crypto_twin_soak_report.py needs without
    re-scanning raw decisions.jsonl itself for historical hours.
    """
    hour_floor = _hour_floor(now_et)
    hour_floor_iso = hour_floor.isoformat()
    last = _load_watermark(cfg)
    if last is not None and last >= hour_floor_iso:
        return None  # this hour is already rolled up

    period_start_iso = last or (hour_floor - timedelta(hours=1)).isoformat()
    rows = _read_jsonl(cfg.state_dir / "decisions.jsonl")
    in_window = [r for r in rows if period_start_iso <= str(r.get("ts_et", "")) < hour_floor_iso]

    dist: dict[str, int] = {}
    for r in in_window:
        action = str(r.get("action", "UNKNOWN"))
        dist[action] = dist.get(action, 0) + 1

    soak_row = {
        "period_start_et": period_start_iso,
        "period_end_et": hour_floor_iso,
        "n_ticks": len(in_window),
        "n_errors": dist.get("TICK_ERROR", 0),
        "action_distribution": dist,
        "written_at_et": now_et.isoformat(),
    }
    p = _soak_log_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(soak_row) + "\n")
    _save_watermark(cfg, hour_floor_iso)
    return soak_row


# --- the wrapped tick (the scheduled-task entrypoint) -------------------------------------
def _tick_error_row(cfg: ctc.TwinConfig, *, now_et: datetime, now_utc: datetime,
                    live: bool, error_str: str) -> dict:
    return {
        "ts_et": now_et.isoformat(), "ts_utc": now_utc.isoformat(),
        "account": cfg.account_label, "twin": True, "symbol": cfg.symbol,
        "armed": live, "verdict": "HOLD", "side": None, "setup": None,
        "triggers": [], "reason": error_str, "trigger_level_exact": None,
        "exit_pass": [], "action": "TICK_ERROR", "position_status": "unknown",
    }


def run_tick_with_health(cfg: ctc.TwinConfig = ctc.TwinConfig(), *, live: bool = False,
                         now_utc: Optional[datetime] = None, now_et: Optional[datetime] = None,
                         raw_bars: Optional[list[dict]] = None,
                         health_path: Path = HEALTH_PATH) -> dict:
    """The T3 scheduled-task entrypoint: crypto_twin_scenarios.run_scenario_tick()
    (B1b: the scenario-scheduler-wrapped tick -- itself a thin layer over
    crypto_twin_core.run_tick(), see that module's docstring) wrapped in a catch-all so a
    genuine exception is captured (never silently lost under pythonw's discarded
    stderr), logged as a TICK_ERROR decision row, and reflected in twin-health.json's
    last_error -- then ALWAYS writes the health snapshot and the hourly soak rollup,
    whether the tick succeeded or not. This function itself never raises; the only way
    to know it is unhealthy is to read what it wrote down.

    `now_utc`/`now_et`/`raw_bars` are all injectable (default to real network/wall-
    clock) -- mirrors run_tick's own injectable-clock pattern, so this wrapper is
    fully testable without the network or real time.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_et or et_now()

    error_str: Optional[str] = None
    row: Optional[dict] = None
    try:
        row = cts.run_scenario_tick(cfg, live=live, now_utc=now_utc, raw_bars=raw_bars)["row"]
    except Exception as e:  # noqa: BLE001 -- deliberate outermost catch-all; see module docstring.
        error_str = f"{type(e).__name__}: {e}"
        row = _tick_error_row(cfg, now_et=now_et, now_utc=now_utc, live=live, error_str=error_str)
        try:
            ctc.log_decision(cfg, row)
        except Exception:  # noqa: BLE001 -- best-effort; the health snapshot below still tries.
            pass

    try:
        health = write_twin_health(cfg, row=row, error=error_str, now_et=now_et, health_path=health_path)
    except Exception as e:  # noqa: BLE001 -- visibility must not itself become a crash.
        health = {"write_failed": f"{type(e).__name__}: {e}"}

    try:
        soak_row = append_soak_row_if_due(cfg, now_et=now_et)
    except Exception:  # noqa: BLE001
        soak_row = None

    return {"row": row, "health": health, "soak_row": soak_row, "error": error_str}


# --- CLI ------------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Crypto Twin health-wrapped tick -- the Gamma_CryptoTwin scheduled-task entrypoint")
    parser.add_argument("--live", action="store_true", help="place real paper orders (default WATCH)")
    args = parser.parse_args(argv)

    result = run_tick_with_health(live=args.live)
    print(json.dumps({
        "action": (result["row"] or {}).get("action"),
        "error": result["error"],
        "health": result["health"],
        "soak_row_written": result["soak_row"] is not None,
    }, indent=2))
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
