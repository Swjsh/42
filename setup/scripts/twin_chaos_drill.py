"""twin_chaos_drill.py -- B4: the CRYPTO TWIN's weekly CHAOS DRILL (resilience ledger).

markdown/planning/TWIN-PROGRAM.md value stream #4: "Chaos drills (weekly). Injected
failures we'd never dare on SPY: process kill mid-position, corrupt state file, stale
feed, breaker mid-trip. Resilience ledger." This module is that forcing function --
FOUR real (or as-real-as-safely-possible) failure injections against the twin's OWN
state under automation/state/crypto-twin/, run against the REAL twin (Alpaca crypto
PAPER, never SPY/fleet -- crypto/CLAUDE.md's "no live orders" rule scopes the crypto/
folder's validators only, NOT this file, which lives in setup/scripts/ alongside
crypto_twin_core.py and follows ITS doctrine: the twin trades real paper orders by
design, see TWIN-PROGRAM.md).

REUSE, never fork (same hard rail every twin module states): every drill drives the
REAL production functions (crypto_twin_core.run_tick/place_entry/load_breaker/
_risk_gate_check, crypto_twin_broker's REST calls, crypto.lib.kill_switch.tick) --
this module invents ZERO new decision logic. It only (a) injects a failure into real
state or a real subprocess, (b) observes what the REAL mechanism does, (c) restores
clean state, (d) journals the rep to resilience-ledger.jsonl.

FOUR DRILLS:
  1. process_kill_mid_position -- opens a REAL twin position (place_entry, tagged
     CHAOS_DRILL_PROCESS_KILL), launches a REAL managing tick as a subprocess (the
     exact Gamma_CryptoTwin entrypoint, crypto_twin_health.py --live), kills it
     forcefully mid-flight (TerminateProcess, simulating this rig's own reaper/crash
     class -- see root CLAUDE.md "THIS RIG KILLS ITS OWN PROCESSES"), then proves a
     FRESH tick recovers: state file still parses, and the position is either still
     correctly tracked (broker + disk agree) or was cleanly closed -- never silently
     orphaned (broker holds real qty but disk shows flat, the one true FAIL case;
     classify_recovery() below is the decision table, unit-tested offline).
  2. corrupt_state_file -- malforms exit-state.json's bytes on disk, proves
     crypto_twin_core._load_positions fails OPEN (returns {}, never raises) and a
     following real tick does not crash, then restores the exact original bytes.
  3. stale_feed -- points ONE tick at a deliberately stale bar (via run_tick's own
     injectable `raw_bars`, the same mechanism crypto_twin_scenarios.py and every twin
     test already use -- no network flakiness, fully deterministic), proves
     bar_reader's real staleness verdict fires (action=HOLD_BAD_BARS) and NO order is
     attempted. live=False (WATCH) by construction -- nothing to restore.
  4. breaker_mid_trip -- overwrites breaker.json with a TRIPPED doc (equity healthy,
     latch set -- isolates testing the LATCH, not "would trip anyway"), proves the
     REAL load_breaker -> kill_switch.tick -> risk_gate.check_order chain halts new
     entries (code=KILL_SWITCH), restores the exact original bytes, then proves the
     SAME chain re-arms (allows again) off the restored file.

SAFETY: every drill either (a) touches only automation/state/crypto-twin/ files plus a
real BTC/USD paper order (drill 1 -- explicitly authorized: TWIN-PROGRAM.md "this is
exactly its job"), or (b) is fully offline/deterministic (drills 2-4's verification
steps never place an order). Drill 1 is the only one with real financial-shaped
exposure, and it is PAPER money on a dedicated twin-only account
(crypto_twin_broker.get_twin_creds() refuses fleet/core credentials by construction).
Every drill restores original state before returning; drill 1's orchestrator force-
flattens any position still open at the end (force_flatten_position, below) so the
twin is left FLAT and clean regardless of how the drill resolved.

CONCURRENCY NOTE (honest, not solved): Gamma_CryptoTwin fires every 5 min, 24/7,
independent of this script. Each drill's real-I/O window is seconds, not minutes, so
the odds of the standing task's own tick landing inside a drill's injection window are
low but non-zero -- if it does, the standing task simply observes the SAME injected
state a moment earlier than my own verification step would have, which is not a false
result (it is, if anything, an EXTRA real rep of the exact resilience property being
tested). No drill here mutates state in a way that a concurrent read could
misinterpret as a genuine trading signal (drills 2-4 never touch decisions that would
place an order without ALSO going through the same real risk_gate/bar-staleness gates
a concurrent tick would use).

Usage:
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\twin_chaos_drill.py --all
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\twin_chaos_drill.py --drill stale_feed
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
for _p in ("automation/state/fleet", "backtest/lib"):
    _full = REPO / _p
    if str(_full) not in sys.path:
        sys.path.insert(0, str(_full))

from et_clock import et_now  # noqa: E402

import crypto_twin_broker as broker  # noqa: E402
import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_health as cth  # noqa: E402
from crypto.lib.kill_switch import tick as ks_tick  # noqa: E402

TWIN_STATE = REPO / "automation" / "state" / "crypto-twin"
LEDGER_PATH = TWIN_STATE / "resilience-ledger.jsonl"
PYTHON_VENV = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
HEALTH_ENTRYPOINT = SCRIPTS / "crypto_twin_health.py"

DRILL_PROCESS_KILL = "process_kill_mid_position"
DRILL_CORRUPT_STATE = "corrupt_state_file"
DRILL_STALE_FEED = "stale_feed"
DRILL_BREAKER_TRIP = "breaker_mid_trip"
ALL_DRILLS = (DRILL_PROCESS_KILL, DRILL_CORRUPT_STATE, DRILL_STALE_FEED, DRILL_BREAKER_TRIP)


# --- shared, fully offline helpers (unit-tested directly) -------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    """Temp-file + os.replace so a crash mid-restore can never leave a half-written
    file -- mirrors twin_gauntlet.py's _atomic_write_json (same convention, text-level
    so drill 2 can round-trip a deliberately-malformed non-JSON string too)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    d = str(path.parent)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def append_resilience_row(row: dict, *, ledger_path: Path = LEDGER_PATH) -> dict:
    """Append ONE row to resilience-ledger.jsonl (append-only, same convention as every
    other twin ledger -- decisions.jsonl/journal.jsonl/incidents.jsonl). Returns the row
    written (mirrors twin_gauntlet.record_path_result's "return what was written")."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _ledger_row(drill: str, *, injected_at: str, recovered: Optional[bool], recovery_path: str,
                notes: str, evidence: Optional[dict] = None) -> dict:
    return {
        "drill": drill,
        "injected_at": injected_at,
        "observed_at": _now_iso(),
        "recovered": recovered,  # True/False/None (None = drill skipped/inconclusive, not a fail)
        "recovery_path": recovery_path,
        "notes": notes,
        "evidence": evidence or {},
    }


# --- drill 1: process-kill mid-position --------------------------------------------------
def classify_recovery(*, disk_position: Optional[dict], broker_qty: float,
                      state_file_valid: bool) -> tuple[str, str]:
    """Pure decision table for drill 1's post-kill observation (unit-tested with every
    branch below -- see test_twin_chaos_drill.py). Never touches I/O.

    Returns (verdict, recovery_path):
      verdict is "RECOVERED" or "INCIDENT" (mirrors crypto_twin_scenarios._grade's own
      GREEN/INCIDENT vocabulary so a reader scanning both ledgers recognizes the shape).

    DUST FLOOR (2026-09-05, RESILIENCE-LEDGER-DUST-RECONCILIATION): `broker_qty > 0` used
    to be the "has_broker" test, which misclassified the 9e-09 / 1e-09 BTC float noise
    observed in two real 2026-08-16/08-23 reps (a full sell-to-flat rounding artifact,
    ~5-6 orders of magnitude below one traded unit) as an ORPHANED_POSITION_NO_RECORD
    INCIDENT. `ctc.DUST_EPSILON_BTC` is the SAME threshold `_reconcile_untracked_exposure`
    now uses in production, so the drill's verdict and the live mechanism's own definition
    of "a real untracked position" can never silently diverge again.
    """
    if not state_file_valid:
        return "INCIDENT", "STATE_FILE_CORRUPTED_ON_KILL"
    has_disk = disk_position is not None
    has_broker = broker_qty > ctc.DUST_EPSILON_BTC
    if has_disk and has_broker:
        return "RECOVERED", "STATE_CONSISTENT_WITH_BROKER"
    if not has_disk and not has_broker:
        return "RECOVERED", "POSITION_CLOSED_CLEANLY"
    if has_disk and not has_broker:
        # exit-state.json still lists it but the broker is flat -- the very next real
        # manage_positions() tick prunes this via its own FLAT_PRUNED branch (see
        # crypto_twin_core.manage_positions: "if open_qty <= 0: del positions[symbol]").
        # Recoverable by construction, not an orphan.
        return "RECOVERED", "BROKER_FLAT_PENDING_PRUNE"
    # not has_disk and has_broker: the broker holds REAL qty with no local record to
    # manage it -- exactly the orphan class root-caused live 2026-07-15 03:58 UTC
    # (crypto_twin_core.py's own "BUGFIXES" section, the CLOSE_FAILED fix) but for the
    # OPPOSITE failure direction (lost record, not a failed sell). A genuine finding.
    return "INCIDENT", "ORPHANED_POSITION_NO_RECORD"


def force_flatten_position(cfg: ctc.TwinConfig, creds: dict, *,
                           close_fn: Optional[Callable] = None) -> Optional[dict]:
    """RESTORE step for drill 1 (and a safety net for any drill that could plausibly
    leave a real position open): if exit-state.json still lists cfg.symbol, market-sell
    the entire REAL broker qty and remove the local record, journaling a CHAOS_DRILL
    close. `close_fn` is injectable (mirrors every other twin module's broker-call
    injection pattern) so this is unit-testable with a fake broker double, no network.
    Resolved to `broker.close_all_crypto` INSIDE the function body (never as a bound
    default -- a default parameter is snapshotted ONCE when this function is defined,
    so `monkeypatch.setattr(tcd.broker, "close_all_crypto", fake)` would silently NOT
    redirect a no-arg call otherwise; the exact bug class twin_gauntlet.py's own
    `_write_last_result` docstring calls out, caught first in trade_autopsy.py).
    Returns the broker response, or None if nothing needed flattening."""
    if close_fn is None:
        close_fn = broker.close_all_crypto
    positions = ctc._load_positions(cfg)
    if cfg.symbol not in positions:
        return None
    res = close_fn(creds, symbol=cfg.symbol, live=True)
    del positions[cfg.symbol]
    ctc._save_positions(cfg, positions)
    ctc._journal(cfg, "CLOSED", symbol=cfg.symbol, reason="chaos_drill_restore", broker=res)
    return res


def drill_process_kill(cfg: ctc.TwinConfig = ctc.TwinConfig(), *, kill_after_sec: float = 2.5,
                       popen_fn: Callable = subprocess.Popen,
                       ledger_path: Optional[Path] = None) -> dict:
    """LIVE, real-network drill. Opens a real position, kills a real managing tick
    subprocess mid-flight, proves a fresh tick recovers, restores flat. `popen_fn` is
    injectable ONLY so a smoke test can substitute a fast dummy subprocess (still real
    OS process creation -- see test file's process-kill smoke test); the entry/exit
    calls always hit the REAL broker (drill 1 has no offline mode by design -- it is
    THE thing that must be proven against a real broker + a real killed process).
    `ledger_path` defaults to the REAL production ledger INSIDE the function body (never
    a bound default -- same reasoning as force_flatten_position's close_fn) so tests can
    redirect every write to a tmp_path ledger and never pollute resilience-ledger.jsonl."""
    ledger_path = ledger_path or LEDGER_PATH
    injected_at = _now_iso()
    now_utc = datetime.now(timezone.utc)

    if ctc.get_open_position(cfg) is not None:
        return append_resilience_row(_ledger_row(
            DRILL_PROCESS_KILL, injected_at=injected_at, recovered=None,
            recovery_path="SKIPPED_POSITION_ALREADY_OPEN",
            notes="a real (organic or scenario) position was already open -- deferred "
                 "drill 1 to avoid killing a mid-lifecycle rep that isn't this drill's own "
                 "(TWIN-PROGRAM.md judgment call). Re-run once flat."), ledger_path=ledger_path)

    try:
        creds = broker.get_twin_creds()
    except Exception as e:  # noqa: BLE001
        return append_resilience_row(_ledger_row(
            DRILL_PROCESS_KILL, injected_at=injected_at, recovered=None,
            recovery_path="SKIPPED_NO_ACCOUNT", notes=f"twin creds unavailable: {e}"),
            ledger_path=ledger_path)

    bars, bar_meta = ctc.fetch_closed_bars(cfg, now_utc=now_utc)
    if not bars or bar_meta["verdict"] != "ok":
        return append_resilience_row(_ledger_row(
            DRILL_PROCESS_KILL, injected_at=injected_at, recovered=None,
            recovery_path="SKIPPED_BAD_BARS", notes=f"fetch_closed_bars verdict={bar_meta.get('verdict')}"),
            ledger_path=ledger_path)
    price = bars[-1].close

    entry = ctc.place_entry(cfg, creds=creds, side="bull", price=price, trigger_level=None,
                            live=True, now_utc=now_utc, scenario_tag="CHAOS_DRILL_PROCESS_KILL")
    if not entry.get("placed"):
        return append_resilience_row(_ledger_row(
            DRILL_PROCESS_KILL, injected_at=injected_at, recovered=None,
            recovery_path="SKIPPED_ENTRY_FAILED", notes=f"place_entry did not fill: {entry}"),
            ledger_path=ledger_path)

    proc = popen_fn([str(PYTHON_VENV), str(HEALTH_ENTRYPOINT), "--live"], cwd=str(REPO),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=kill_after_sec)
        killed_before_completion = False
    except subprocess.TimeoutExpired:
        proc.kill()  # TerminateProcess -- abrupt, no cleanup: the reaper-kill class this drill exists to prove resilience against
        proc.wait(timeout=15)
        killed_before_completion = True

    state_path = cfg.state_dir / "exit-state.json"
    state_file_valid = True
    try:
        json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state_file_valid = False

    disk_position_post_kill = ctc.get_open_position(cfg)
    broker_qty_post_kill = broker.get_crypto_position_qty(creds, cfg.symbol)

    verdict, recovery_path = classify_recovery(
        disk_position=disk_position_post_kill, broker_qty=broker_qty_post_kill,
        state_file_valid=state_file_valid)

    # Whether recovered or not, run ONE more real tick (fresh process, in-process here)
    # to give the real mechanism its actual recovery chance -- mirrors RESTART_OPEN_
    # POSITION's own "a fresh process still correctly manages an open position" property.
    recovery_tick_error = None
    try:
        cth.run_tick_with_health(cfg, live=True)
    except Exception as e:  # noqa: BLE001 -- the drill must observe a crash, never hide one
        recovery_tick_error = f"{type(e).__name__}: {e}"

    disk_after_recovery_tick = ctc.get_open_position(cfg)
    broker_qty_after_recovery_tick = broker.get_crypto_position_qty(creds, cfg.symbol)

    restored = force_flatten_position(cfg, creds)

    evidence = {
        "killed_before_completion": killed_before_completion,
        "state_file_valid_post_kill": state_file_valid,
        "disk_position_post_kill": disk_position_post_kill is not None,
        "broker_qty_post_kill": broker_qty_post_kill,
        "recovery_tick_error": recovery_tick_error,
        "disk_position_after_recovery_tick": disk_after_recovery_tick is not None,
        "broker_qty_after_recovery_tick": broker_qty_after_recovery_tick,
        "force_flattened_at_restore": restored is not None,
    }
    recovered = (verdict == "RECOVERED") and recovery_tick_error is None
    notes = (f"opened real CHAOS_DRILL_PROCESS_KILL position at ${price:,.2f}, killed the "
            f"managing subprocess {'mid-flight' if killed_before_completion else '(it finished before the timeout -- no true kill occurred, treat as a weaker rep)'}, "
            f"classified {recovery_path}, then ran one more real recovery tick "
            f"({'errored: ' + recovery_tick_error if recovery_tick_error else 'clean'}) and restored flat.")
    return append_resilience_row(_ledger_row(
        DRILL_PROCESS_KILL, injected_at=injected_at, recovered=recovered,
        recovery_path=recovery_path, notes=notes, evidence=evidence), ledger_path=ledger_path)


# --- drill 2: corrupt state file ----------------------------------------------------------
def inject_corrupt_state(state_path: Path, *,
                         payload: str = "{not valid json -- injected by twin_chaos_drill") -> str:
    """Snapshots the ORIGINAL bytes (empty string if the file didn't exist yet -- mirrors
    _load_positions' own missing-file default of {}), overwrites with malformed JSON,
    returns the original text for restore_state(). Pure I/O, unit-tested with tmp_path."""
    original = state_path.read_text(encoding="utf-8") if state_path.exists() else ""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(payload, encoding="utf-8")
    return original


def restore_state(state_path: Path, original_text: str) -> None:
    """Restores EXACTLY the bytes inject_corrupt_state() snapshotted, atomically."""
    _atomic_write_text(state_path, original_text if original_text else "{}")


def check_fail_safe_load(cfg: ctc.TwinConfig) -> bool:
    """True iff crypto_twin_core._load_positions degrades to {} (never raises) against
    whatever is CURRENTLY on disk at cfg.state_dir/exit-state.json."""
    try:
        loaded = ctc._load_positions(cfg)
    except Exception:  # noqa: BLE001 -- a raise here IS the fail-safe test failing
        return False
    return loaded == {}


def drill_corrupt_state(cfg: ctc.TwinConfig = ctc.TwinConfig(), *,
                        ledger_path: Optional[Path] = None) -> dict:
    """LIVE (real state dir), but network-optional: uses live=True on the recovery tick
    so a genuinely-flat twin (tonight's case) proves the whole real pipeline survives,
    while never being ABLE to place an order it wasn't already going to place (the
    corruption only affects position bookkeeping, never bar/signal/risk_gate logic).
    `ledger_path` resolved inside the body -- see drill_process_kill's docstring."""
    ledger_path = ledger_path or LEDGER_PATH
    injected_at = _now_iso()
    state_path = cfg.state_dir / "exit-state.json"

    existing_position_before = ctc.get_open_position(cfg)
    try:
        creds = broker.get_twin_creds()
        broker_qty_before = broker.get_crypto_position_qty(creds, cfg.symbol)
    except Exception as e:  # noqa: BLE001
        creds = None
        broker_qty_before = None
        creds_error = f"{type(e).__name__}: {e}"
    else:
        creds_error = None

    original_text = inject_corrupt_state(state_path)
    fail_safe_ok = check_fail_safe_load(cfg)

    tick_error = None
    try:
        result = cth.run_tick_with_health(cfg, live=creds is not None)
        tick_error = result.get("error")
    except Exception as e:  # noqa: BLE001 -- the drill must observe this, never hide it
        tick_error = f"{type(e).__name__}: {e}"

    broker_qty_after = None
    if creds is not None:
        try:
            broker_qty_after = broker.get_crypto_position_qty(creds, cfg.symbol)
        except Exception:  # noqa: BLE001 -- best-effort observation only
            broker_qty_after = None

    restore_state(state_path, original_text)

    recovered = fail_safe_ok and tick_error is None
    orphan_risk_note = ("" if existing_position_before is None else
                        " WARNING: a real position was open BEFORE this drill -- corrupting "
                        "state while a position is genuinely open can hide it from "
                        "manage_positions until the next organic entry re-populates the file; "
                        "this is a real known gap, not masked by this drill's restore step.")
    notes = (f"malformed exit-state.json, confirmed _load_positions fail-opened to {{}} "
            f"({'OK' if fail_safe_ok else 'FAILED -- raised or returned non-empty'}), ran one "
            f"real tick ({'clean' if tick_error is None else 'errored: ' + tick_error}), "
            f"restored the original {len(original_text)}-byte file.{orphan_risk_note}")
    evidence = {
        "creds_error": creds_error, "existing_position_before": existing_position_before is not None,
        "broker_qty_before": broker_qty_before, "fail_safe_ok": fail_safe_ok, "tick_error": tick_error,
        "broker_qty_after": broker_qty_after, "original_bytes_len": len(original_text),
    }
    return append_resilience_row(_ledger_row(
        DRILL_CORRUPT_STATE, injected_at=injected_at, recovered=recovered,
        recovery_path="FAIL_OPEN_LOAD_THEN_RESTORE_ORIGINAL_BYTES", notes=notes, evidence=evidence),
        ledger_path=ledger_path)


# --- drill 3: stale feed -------------------------------------------------------------------
def _raw_bar(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> dict:
    return {"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}


def detect_stale_feed(cfg: ctc.TwinConfig, *, now_utc: datetime,
                      stale_hours: float = 3.0, price: float = 65000.0) -> tuple[bool, dict]:
    """Pure(ish) core of drill 3: feeds run_tick ONE bar closed `stale_hours` ago (via
    the real injectable `raw_bars` param -- crypto.lib.bar_reader's own staleness
    verdict decides, never reimplemented here) and returns
    (detected: bool, row: dict). live=False (WATCH) always -- see module docstring."""
    stale_ts = now_utc - timedelta(hours=stale_hours)
    raw = [_raw_bar(stale_ts, price, price, price, price)]
    row = ctc.run_tick(cfg, live=False, now_utc=now_utc, raw_bars=raw)
    detected = row.get("action") == "HOLD_BAD_BARS"
    return detected, row


def drill_stale_feed(cfg: ctc.TwinConfig = ctc.TwinConfig(), *,
                     ledger_path: Optional[Path] = None) -> dict:
    ledger_path = ledger_path or LEDGER_PATH
    injected_at = _now_iso()
    now_utc = datetime.now(timezone.utc)

    journal_path = cfg.state_dir / "journal.jsonl"
    placed_before = journal_path.read_text(encoding="utf-8").count('"event": "PLACED"') if journal_path.exists() else 0

    detected, row = detect_stale_feed(cfg, now_utc=now_utc)

    placed_after = journal_path.read_text(encoding="utf-8").count('"event": "PLACED"') if journal_path.exists() else 0
    no_new_orders = placed_after == placed_before

    recovered = detected and no_new_orders
    notes = (f"injected a bar closed 3h stale; run_tick verdict={row.get('reason')!r} "
            f"action={row.get('action')!r} ({'staleness correctly detected' if detected else 'NOT DETECTED -- INCIDENT'}), "
            f"no new PLACED journal rows ({'confirmed' if no_new_orders else 'MISMATCH -- an order attempt occurred'}). "
            "Append-only decisions.jsonl row written by design (visibility); nothing else mutated, nothing to restore.")
    evidence = {"action": row.get("action"), "bar_meta_reason": row.get("reason"),
               "placed_before": placed_before, "placed_after": placed_after}
    return append_resilience_row(_ledger_row(
        DRILL_STALE_FEED, injected_at=injected_at, recovered=recovered,
        recovery_path="N/A_APPEND_ONLY_NO_MUTATION_TO_REVERT", notes=notes, evidence=evidence),
        ledger_path=ledger_path)


# --- drill 4: breaker mid-trip --------------------------------------------------------------
def build_tripped_breaker_doc(original: Optional[dict], cfg: ctc.TwinConfig, now_utc: datetime) -> dict:
    """Pure function: builds a TRIPPED breaker.json doc that isolates testing the LATCH
    (kill_switch.py: 'once tripped, stays tripped even if equity recovers') rather than
    'would trip anyway from a low current_equity' -- current_equity here is set to the
    SAME start_of_day_equity (healthy, no real loss), only `tripped`/`tripped_at_equity`
    are forced True. Unit-tested directly (no I/O)."""
    today = now_utc.strftime("%Y-%m-%d")
    sod = (float(original["start_of_day_equity"]) if original and original.get("utc_date") == today
          else cfg.starting_equity)
    return {"utc_date": today, "account_id": cfg.account_label, "start_of_day_equity": sod,
           "current_equity": sod, "threshold_pct": cfg.daily_loss_kill_switch_pct,
           "tripped": True, "tripped_at_equity": sod * (1.0 - cfg.daily_loss_kill_switch_pct),
           "min_equity_seen": sod * (1.0 - cfg.daily_loss_kill_switch_pct)}


def verify_gate(cfg: ctc.TwinConfig, *, now_utc: datetime) -> tuple[bool, dict]:
    """Drives the REAL chain -- load_breaker() (disk read) -> kill_switch.tick() (the
    latch) -> ctc._risk_gate_check() (the real risk_gate.check_order) -- off WHATEVER is
    currently persisted in cfg.state_dir/breaker.json, and returns
    (blocked: bool, evidence). No network, no bars, no order: fully offline/deterministic,
    exactly targeting the halt/re-arm mechanism (see module docstring for why this is a
    MORE precise test than a full run_tick here)."""
    equity = cfg.starting_equity
    if (cfg.state_dir / "breaker.json").exists():
        try:
            equity = float(json.loads((cfg.state_dir / "breaker.json").read_text(encoding="utf-8"))
                          .get("current_equity", equity))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    loaded = ctc.load_breaker(cfg, now_utc=now_utc, current_equity=equity)
    ticked = ks_tick(loaded, equity)
    ctc.save_breaker(cfg, ticked, now_utc=now_utc, current_equity=equity)
    decision = ctc._risk_gate_check(cfg, equity=equity, sod_equity=ticked.start_of_day_equity,
                                    kill_switch_tripped=ticked.tripped, position_status="flat",
                                    setup_name="CHAOS_DRILL_BREAKER_GATE")
    blocked = (not decision.allowed) and decision.code == "KILL_SWITCH"
    return blocked, {"loaded_tripped": loaded.tripped, "ticked_tripped": ticked.tripped,
                     "risk_gate_allowed": decision.allowed, "risk_gate_code": decision.code,
                     "risk_gate_reason": decision.reason}


def drill_breaker_trip(cfg: ctc.TwinConfig = ctc.TwinConfig(), *,
                       ledger_path: Optional[Path] = None) -> dict:
    ledger_path = ledger_path or LEDGER_PATH
    injected_at = _now_iso()
    now_utc = datetime.now(timezone.utc)
    breaker_path = cfg.state_dir / "breaker.json"

    original_text = breaker_path.read_text(encoding="utf-8") if breaker_path.exists() else ""
    try:
        original_doc = json.loads(original_text) if original_text else None
    except json.JSONDecodeError:
        original_doc = None

    tripped_doc = build_tripped_breaker_doc(original_doc, cfg, now_utc)
    _atomic_write_text(breaker_path, json.dumps(tripped_doc, indent=2))

    halted, halt_evidence = verify_gate(cfg, now_utc=now_utc)

    # save_breaker() inside verify_gate() re-persists the ticked state -- restore the
    # DRILL'S OWN pre-injection snapshot now, not that intermediate write.
    restore_state(breaker_path, original_text)

    # verify_gate's own save_breaker call (below) re-persists whatever the restored
    # file's real tripped/current_equity state ticks to (identical semantics to a
    # genuine next production tick). Expected outcome depends on what the ORIGINAL file
    # actually said: if it was untripped (tonight's case), re-arming must show
    # blocked=False; if the account happened to be genuinely tripped already, staying
    # blocked after restore is the CORRECT behavior, not a re-arm failure.
    expected_blocked_after_restore = bool(original_doc.get("tripped")) if original_doc else False
    rearm_blocked, rearm_evidence = verify_gate(cfg, now_utc=now_utc)
    rearm_ok = rearm_blocked == expected_blocked_after_restore

    # One more restore pass in case verify_gate's second save_breaker call altered
    # anything beyond the original snapshot (belt-and-suspenders -- breaker.json must
    # end this drill byte-identical to how it started).
    restore_state(breaker_path, original_text)

    recovered = halted and rearm_ok
    notes = (f"injected a LATCHED-tripped breaker.json (healthy current_equity, forced "
            f"tripped=True) -- real load_breaker+kill_switch.tick+risk_gate chain "
            f"{'correctly HALTED (code=KILL_SWITCH)' if halted else 'FAILED TO HALT -- INCIDENT'}. "
            f"Restored the original {len(original_text)}-byte file -- real chain "
            f"{'correctly RE-ARMED' if rearm_ok else 'FAILED TO RE-ARM -- INCIDENT'}.")
    evidence = {"original_tripped": bool(original_doc.get("tripped")) if original_doc else False,
               "halt_check": halt_evidence, "rearm_check": rearm_evidence}
    return append_resilience_row(_ledger_row(
        DRILL_BREAKER_TRIP, injected_at=injected_at, recovered=recovered,
        recovery_path="RESTORE_ORIGINAL_BYTES_THEN_REVERIFY_GATE", notes=notes, evidence=evidence),
        ledger_path=ledger_path)


# --- orchestration -------------------------------------------------------------------------
DRILL_FUNCS: dict[str, Callable[..., dict]] = {
    DRILL_PROCESS_KILL: drill_process_kill,
    DRILL_CORRUPT_STATE: drill_corrupt_state,
    DRILL_STALE_FEED: drill_stale_feed,
    DRILL_BREAKER_TRIP: drill_breaker_trip,
}


def run_all(cfg: ctc.TwinConfig = ctc.TwinConfig(), *, drills: tuple = ALL_DRILLS,
           kill_after_sec: float = 2.5, ledger_path: Optional[Path] = None) -> list[dict]:
    """Runs the requested drills IN ORDER (process_kill first while the account is
    guaranteed flat, corrupt_state/stale_feed/breaker_trip after -- each restores clean
    state before the next starts, so order only matters for drill 1's flat-precondition).
    `kill_after_sec` only affects drill_process_kill (see its docstring: a managing tick
    that legitimately finishes before this window elapses is NOT a true kill -- tune
    down if a real rep reports killed_before_completion=False). `ledger_path` threads to
    every drill call (tests pass a tmp_path override; production omits it)."""
    rows = []
    for d in drills:
        if d == DRILL_PROCESS_KILL:
            rows.append(drill_process_kill(cfg, kill_after_sec=kill_after_sec, ledger_path=ledger_path))
        else:
            rows.append(DRILL_FUNCS[d](cfg, ledger_path=ledger_path))
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Twin chaos drill -- weekly failure-injection resilience test (TWIN-PROGRAM.md stream 4)")
    parser.add_argument("--all", action="store_true", help="run all four drills in order")
    parser.add_argument("--drill", choices=sorted(DRILL_FUNCS), default=None,
                        help="run exactly one drill")
    parser.add_argument("--kill-after-sec", type=float, default=2.5,
                        help="drill 1 only: seconds to wait before force-killing the managing "
                             "subprocess (default 2.5; lower if a rep reports "
                             "killed_before_completion=False -- the tick finished too fast to catch)")
    args = parser.parse_args(argv)

    if not args.all and not args.drill:
        parser.error("pass --all or --drill <name>")

    if args.drill == DRILL_PROCESS_KILL:
        rows = [drill_process_kill(ctc.TwinConfig(), kill_after_sec=args.kill_after_sec)]
    else:
        rows = run_all(drills=ALL_DRILLS if args.all else (args.drill,),
                       kill_after_sec=args.kill_after_sec)
    for row in rows:
        print(json.dumps(row, indent=2, default=str))
    any_incident = any(r.get("recovered") is False for r in rows)
    return 1 if any_incident else 0


if __name__ == "__main__":
    raise SystemExit(main())
