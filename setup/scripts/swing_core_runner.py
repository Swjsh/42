"""swing_core_runner.py -- thin runner: futures_heartbeat_core's SEE/DECIDE + the fill-sim
broker's own ACT/exit engine, ONE decision pass per fire. Feeds Gamma_SwingCore (daily,
15:35 ET) and Gamma_SwingMonitor (every 15 min, 09:00-16:05 ET) -- see
setup/scripts/install-swing-tasks.ps1 (STAGED, NOT REGISTERED as of this build; DO NOT run
that installer without J's go-ahead per the arming boundary below).

WHY NOT hb.run_tick() UNMODIFIED -- 3 adapter gaps found reading futures_heartbeat_core.py +
its test suite before writing this file:

  1. STATE-DIR COLLISION. run_tick()'s _emit_state()/_load_position() hard-code
     automation/state/futures/{position,decisions,last-tick,loop-state}.json -- the SAME
     paths the REAL (someday-armed) tastytrade intraday tick owns (confirmed: those 4 files
     already exist on disk from the 2026-07-07 dry-run validation). Calling run_tick()
     verbatim would make the fill-sim swing lane clobber the real intraday tick's position
     state, or vice versa, the day both exist. This runner therefore never calls run_tick() --
     it reuses run_tick's PURE SEE/DECIDE pieces (compute_latest_signals, decide_entry --
     both side-effect-free / self-resetting-per-call, safe to call directly) and drives its
     OWN ACT + state via fill_sim_broker's fillsim-*.json (entirely disjoint paths).

  2. THE PROVISIONING GATE IS TASTYTRADE-SDK-SHAPED. run_tick()'s dry_run =
     not (FUTURES_ARMED=="1" and broker "provisioned"); "provisioned"
     (_broker_provisioned/_read_futures_bp) literally introspects broker._account/_session
     (tastytrade SDK objects) via an async SDK call. A fill-sim broker has neither -- it would
     ALWAYS read as unprovisioned, so even a fully-armed run_tick() call would silently never
     route through it. Moot here since this runner doesn't call run_tick() (see #1), but
     documented because it is the textbook reason "same-interface broker" != "drop straight
     into run_tick()".

  3. run_tick()'s BUILT-IN EXIT MANAGEMENT IS A NO-OP BY DEFAULT (price defaults to
     `pos.entry` when the caller omits `force_price`, which never crosses a stop/target) AND
     ITS TIME_STOP is the INTRADAY 15:50 ET wall-clock check baked into
     futures_exit_manager.DEFAULT_TIME_STOP_ET -- reusing either verbatim for a multiday
     swing hold would either never manage the exit, or force-flatten every position on the
     first check past 15:50 ET on ANY day it is held. This runner manages exits itself via
     FillSimBroker.process_quote() (bar-aware, gap-fill-correct, and it never threads now_et
     into decide_exit() so the intraday TIME_STOP branch never fires -- see
     fill_sim_broker.py's process_quote() docstring). A proper max-hold-days / roll-date stop
     (FUTURES-REVIVAL-PLAN sec 2a) is a follow-up, not built here.

GATING (hard-coded, fail-CLOSED for ENTRIES only -- exit/monitor management ALWAYS runs):
  refuses a NEW entry unless automation/state/futures/armed-setups.json exists and lists >=1
  setup whose analysis/recommendations/futures-swing-{seed}.json scorecard reads
  verdict=="PASS" (read live at runtime, never cached). Logs SKIP_NO_VALIDATED_SETUP and
  proceeds to exit management regardless. This script does NOT create armed-setups.json --
  only J / the validated Phase-1 battery does (OP-0 arming boundary).

MODES:
  (default)  decision fire, once/day (Gamma_SwingCore): manage exits/pending-fills for every
             tracked instrument, THEN -- gate permitting -- run SEE+DECIDE for a NEW entry.
  --monitor  lightweight fire, every 15 min (Gamma_SwingMonitor): exits/pending-fills ONLY, no
             SEE/DECIDE/new-entry (mirrors the plan's "verification, not execution" intraday
             monitor -- except here the monitor genuinely IS the fill mechanism, since there
             is no real broker resting GTC orders server-side for a pure fill-sim).

FAIL-OPEN: every instrument is processed in its own try/except inside run_once(); the whole
script is wrapped so main() always returns 0 and every exception is logged to
automation/state/logs/swing-core-YYYY-MM-DD.log (task requirement -- "a poisoned state file
-> exit 0 + logged").

Runs under backtest/.venv (pandas + yfinance + the watcher fleet live there, not system
Python) -- see install-swing-tasks.ps1's pythonw path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

def _et_now():
    """ET wall-clock via the repo's DST-aware clock. Lazily re-imports et_clock on every call
    (mirrors fill_sim_broker.py's _et_now() exactly) so tests that monkeypatch
    `et_clock.et_now` are honored -- a top-level `from et_clock import et_now` would bind a
    stale local name at import time that a later monkeypatch of the et_clock module could
    never reach. A naive local-clock read is never used (this box runs Mountain time, ET =
    local + 2h; CLAUDE.md TZ-systemic scar)."""
    import et_clock  # noqa: PLC0415
    return et_clock.et_now()


STATE_DIR = REPO / "automation" / "state" / "futures"
LOG_DIR = REPO / "automation" / "state" / "logs"
ARMED_SETUPS_FILE = STATE_DIR / "armed-setups.json"
RECS_DIR = REPO / "analysis" / "recommendations"
HEARTBEAT_FILE = STATE_DIR / "swing-heartbeat.json"

YF_SYMBOL = {"MNQ": "NQ=F", "MES": "ES=F"}


def _log(msg: str) -> None:
    """Fail-open logger -- never raises, even if the log dir/file itself is unwritable."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = _et_now().strftime("%Y-%m-%d")
        ts = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
        path = LOG_DIR / f"swing-core-{day}.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


# ── gating ────────────────────────────────────────────────────────────────────
def check_armed_setups(instrument: str, *, armed_file: Path = ARMED_SETUPS_FILE,
                       recs_dir: Path = RECS_DIR) -> tuple[bool, str]:
    """(passes, reason). PASSES only if armed_file exists, parses, and lists >=1 setup for
    `instrument` (or an untagged entry, which applies to all instruments) whose
    analysis/recommendations/futures-swing-{seed}.json scorecard reads verdict=="PASS", read
    LIVE at call time (never cached). Fails CLOSED on any missing/malformed input -- this is
    the ONLY thing standing between a fresh signal and a simulated order."""
    if not armed_file.exists():
        return False, "no_armed_setups_file"
    try:
        doc = json.loads(armed_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, f"armed_setups_unreadable: {type(e).__name__}"
    setups = doc.get("setups", []) if isinstance(doc, dict) else []
    if not setups:
        return False, "armed_setups_empty"

    checked = []
    for entry in setups:
        if not isinstance(entry, dict):
            continue
        tag = entry.get("instrument")
        if tag not in (None, "", instrument):
            continue
        seed = entry.get("seed")
        if not seed:
            continue
        checked.append(seed)
        scorecard = recs_dir / f"futures-swing-{seed}.json"
        if not scorecard.exists():
            continue
        try:
            sc = json.loads(scorecard.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if sc.get("verdict") == "PASS":
            return True, f"armed:{seed}"
    return False, f"no_pass_scorecard (checked {checked or 'none'})"


# ── live quote fetch (yfinance; imitates sight_beacon.py's resilient-fetch SHAPE --
#    try/except/never-raise, primary-then-fallback spirit. sight_beacon.py itself is
#    untouched per the task's read-only instruction; this is a new, analogous fetcher). ──
def fetch_live_bar(instrument: str) -> Optional[dict]:
    """Best-effort most-recent 15m bar for `instrument` via yfinance. Returns
    {price, open, high, low, time_et} or None on ANY failure -- never raises. Futures trade
    near-24h (Globex), so prepost=True (unlike the SPY-only sight_beacon fetch)."""
    sym = YF_SYMBOL.get(instrument)
    if not sym:
        return None
    try:
        import yfinance as yf  # noqa: PLC0415
        df = yf.download(sym, period="5d", interval="15m", auto_adjust=False,
                         progress=False, prepost=True)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        last = df.iloc[-1]
        if last[["Open", "High", "Low", "Close"]].isnull().any():
            return None
        return {
            "price": float(last["Close"]), "open": float(last["Open"]),
            "high": float(last["High"]), "low": float(last["Low"]),
            "time_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except Exception:  # noqa: BLE001
        return None


# ── per-instrument passes ──────────────────────────────────────────────────────
def manage_instrument(broker, inst_symbol: str, bar: Optional[dict]) -> dict:
    """Exit-management + pending-fill check ONLY. Safe to call with bar=None (a quote-fetch
    failure degrades to a logged no-op, never a crash -- fail-open)."""
    if bar is None:
        return {"instrument": inst_symbol, "event": "noop", "reason": "no_quote"}
    try:
        return broker.process_quote(
            inst_symbol, bar["price"], bar_open=bar.get("open"), bar_high=bar.get("high"),
            bar_low=bar.get("low"), quote_time_et=_et_now())
    except Exception as e:  # noqa: BLE001
        _log(f"manage_instrument({inst_symbol}) FAILED: {type(e).__name__}: {e}")
        return {"instrument": inst_symbol, "event": "error", "reason": str(e)}


def _build_account(broker):
    """A PropAccount sized to the REAL fill-sim equity/floor (not the hardcoded $50K
    TOPSTEP_50K test account futures_heartbeat_core.py defaults to) -- so the kill-switch
    (would_violate) reflects the paper account's actual size."""
    from futures.risk import PropAccount  # noqa: PLC0415
    acct_state = broker.get_account_snapshot()
    equity = float(acct_state.get("equity", 2000.0))
    floor = float(acct_state.get("floor", equity * 0.8))
    daily_loss_limit = float(acct_state.get("daily_loss_limit", 200.0))
    return PropAccount(name="FillSim", starting_balance=equity,
                       max_drawdown=max(1.0, equity - floor), drawdown_type="eod_trailing",
                       profit_target=0.0, max_contracts=5, daily_loss_limit=daily_loss_limit)


def attempt_entry(broker, inst, account, *, armed_file: Optional[Path] = None,
                  recs_dir: Optional[Path] = None) -> dict:
    """Gate -> SEE -> DECIDE -> ACT for ONE instrument. Only called when the instrument is
    flat (no pending, no open) and not in --monitor mode. Uses `hb.` module-attribute calls
    (not `from ... import compute_latest_signals`) so tests can monkeypatch
    futures.futures_heartbeat_core.compute_latest_signals / decide_entry, mirroring
    test_futures_heartbeat.py's own SpyBroker monkeypatch style.

    `armed_file`/`recs_dir` are optional overrides threaded straight into
    check_armed_setups() -- production callers omit them (real paths, bound at
    check_armed_setups' definition time); tests inject tmp_path equivalents so a gating test
    never has to create/read the real automation/state/futures/armed-setups.json or
    analysis/recommendations/ (which this script must never create -- OP-0 arming boundary)."""
    from futures import futures_heartbeat_core as hb  # noqa: PLC0415

    gate_kwargs = {}
    if armed_file is not None:
        gate_kwargs["armed_file"] = armed_file
    if recs_dir is not None:
        gate_kwargs["recs_dir"] = recs_dir
    passed, reason = check_armed_setups(inst.symbol, **gate_kwargs)
    if not passed:
        _log(f"{inst.symbol} SKIP_NO_VALIDATED_SETUP ({reason})")
        return {"instrument": inst.symbol, "action": "SKIP_NO_VALIDATED_SETUP", "reason": reason}

    see = hb.compute_latest_signals(inst)
    if see.get("error"):
        _log(f"{inst.symbol} SEE_ERROR {see['error']}")
        return {"instrument": inst.symbol, "action": "SEE_ERROR", "reason": see["error"]}

    vix = float((see.get("snapshot") or {}).get("vix", 17.0))
    entry = hb.decide_entry(see.get("signals", []), vix=vix, account=account, inst=inst)
    if not entry or entry.get("refused"):
        reason = "no_signal" if not entry else entry["refused"]
        return {"instrument": inst.symbol, "action": "NO_ENTRY", "reason": reason}

    sig = entry["signal"]
    qty = int(entry["qty"])
    side = "BUY" if sig["direction"] == "long" else "SELL"
    tp1_qty = max(1, int(round(qty * hb.TP1_FRACTION)))
    ids = broker.place_bracket(inst.symbol, side, qty, sig["entry"], sig["tp1"], sig["stop"],
                               runner_price=sig["runner"], tp1_qty=tp1_qty)
    action = "PLACED_PENDING" if ids else "PLACE_REFUSED"
    _log(f"{inst.symbol} {action} watcher={sig['watcher']} dir={sig['direction']} qty={qty}")
    return {"instrument": inst.symbol, "action": action, "signal": sig, "qty": qty,
           "order_ids": ids}


def run_once(broker, instruments: list, *, monitor_only: bool,
            quote_fetcher=fetch_live_bar, armed_file: Optional[Path] = None,
            recs_dir: Optional[Path] = None) -> list[dict]:
    """One pass over `instruments`. Always exit-manages; only attempts a new entry when NOT
    monitor_only AND the instrument is flat after management. Each instrument is isolated in
    its own try/except -- one instrument's failure never sinks the pass (fail-open).
    `armed_file`/`recs_dir` pass straight through to attempt_entry() -- see its docstring."""
    results = []
    for inst in instruments:
        try:
            bar = quote_fetcher(inst.symbol)
            manage_result = manage_instrument(broker, inst.symbol, bar)
            result = {"instrument": inst.symbol, "manage": manage_result}
            if not monitor_only and broker.is_flat(inst.symbol):
                account = _build_account(broker)
                result["entry"] = attempt_entry(broker, inst, account, armed_file=armed_file,
                                                recs_dir=recs_dir)
            results.append(result)
        except Exception as e:  # noqa: BLE001
            _log(f"run_once({inst.symbol}) FAILED: {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}")
            results.append({"instrument": inst.symbol, "error": f"{type(e).__name__}: {e}"})
    return results


def _write_heartbeat(broker, instruments: list, results: list[dict]) -> None:
    """The OP-33c glanceable surface. Fail-open: swallows its own errors so a heartbeat-write
    problem never turns into a non-zero exit."""
    try:
        positions = broker.get_positions_snapshot()
        positions_open = sum(
            1 for p in positions.values()
            if p and p.get("status") == "open" and int(p.get("qty_open", 0)) > 0)
        last_action = "NONE"
        for r in results:
            entry = r.get("entry")
            if entry and entry.get("action") not in ("NO_ENTRY", "SKIP_NO_VALIDATED_SETUP", None):
                last_action = entry["action"]
            elif r.get("manage", {}).get("event") not in ("noop", None):
                last_action = r["manage"]["event"]
        snap = {
            "ts_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
            "positions_open": positions_open,
            "equity": broker.get_account_equity(),
            "last_action": last_action,
            "instruments": [inst.symbol for inst in instruments],
            "results": results,
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = HEARTBEAT_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, HEARTBEAT_FILE)
    except Exception as e:  # noqa: BLE001
        _log(f"_write_heartbeat FAILED (non-fatal): {type(e).__name__}: {e}")


def main() -> int:
    """CLI entry point. ALWAYS returns 0 (fail-open, task requirement) -- every exception is
    caught + logged, never re-raised."""
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--monitor", action="store_true",
                        help="lightweight pass: exit/pending-fill management only, no new entries")
        ap.add_argument("--mes", action="store_true", help="also tick MES (default: MNQ only)")
        args = ap.parse_args()

        from futures.instruments import MNQ, MES  # noqa: PLC0415
        from futures.fill_sim_broker import FillSimBroker  # noqa: PLC0415

        broker = FillSimBroker()
        broker.connect()
        instruments = [MNQ] + ([MES] if args.mes else [])

        results = run_once(broker, instruments, monitor_only=args.monitor)
        _write_heartbeat(broker, instruments, results)
        _log(f"pass complete monitor={args.monitor} mes={args.mes} "
            f"results={json.dumps(results, default=str)[:2000]}")
        return 0
    except Exception as e:  # noqa: BLE001 -- fail-open is the task's explicit requirement
        try:
            _log(f"main() FAILED (fail-open, exit 0 anyway): {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}")
        except Exception:  # noqa: BLE001 -- even logging must not break the fail-open contract
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
