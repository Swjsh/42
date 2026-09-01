"""futures_trader_core.py -- THE autonomous futures tick (broker-agnostic).

WHY THIS EXISTS (2026-08-09, FUTURES-FIRST-PLAN WS-F1/F3). Three futures execution
paths already existed and none of them could actually trade autonomously today:

  * `futures_heartbeat_core.run_tick()` -- deterministic and well-built, but hard-wired
    to the tastytrade SDK (its provisioning probe introspects `broker._account`, so a
    non-SDK broker reads as unprovisioned and it silently never routes), and its exit
    management is a no-op unless the caller passes `force_price`.
  * `swing_core_runner.py` -- solved those gaps, but only for the MULTIDAY swing lane,
    and it is gated on an `armed-setups.json` that does not exist.
  * `fill_sim_broker.FillSimBroker` -- a complete, gap-fill-correct paper exchange that
    nothing intraday was wired to.

This module is the intraday lane, and it makes the BROKER a parameter instead of an
assumption. That is the whole design: the venue question (which is genuinely unresolved
-- see FUTURES-BROKER-RESEARCH-2026-08-09.md) stops blocking the engine. The engine runs
today on the local fill simulator and the same tick routes to a real broker the moment
one clears, with no change to SEE, DECIDE, the rails, or the journal.

WHAT IT REUSES (deliberately -- compound, don't accumulate):
  SEE      futures_heartbeat_core.compute_latest_signals (the VALIDATED watcher fleet;
           bars injected from the live spine instead of the two-month-stale master)
  DECIDE   strategy_config_v3.should_take_v3 (the validated filter)
  RAILS    futures_risk_rails.FuturesRiskRails (dollar-denominated, WS-F7)
  ACT      any object with the FillSimBroker/TastytradeBroker duck-typed surface
  EXITS    fill_sim_broker's own bar-aware fill engine / futures_exit_manager

EVIDENCE STATUS -- read this before quoting any number this module produces. Fills from
the `fillsim` backend are SIMULATED. They are mechanism evidence (does the loop see,
decide, size, place, manage and journal correctly) and they are NOT edge evidence, under
exactly the same standing rule that governs the crypto twin. `should_take_v3` was
validated on the roll-adjusted continuous master; this lane feeds it a different (live,
raw front-month, delayed-quote) frame, which is a disclosed data-source change. Any edge
claim needs the canonical battery on its own frozen prereg -- not this ledger.

SAFETY POSTURE. `fillsim` is the default backend and touches no external account. The
`tastytrade` backend refuses to route unless BOTH `FUTURES_ARMED=1` AND the broker
reports futures buying power > 0, so an armed-but-unprovisioned account still routes
nothing. Live money is out of scope entirely: that is OP-0 #1 plus a new venue.

STATE lives under automation/state/futures/trader/ -- disjoint from the paths
futures_heartbeat_core and the swing lane own, so no lane can clobber another's position.

CLI:
    python -m futures.futures_trader_core --tick                 # one pass, MES, fillsim
    python -m futures.futures_trader_core --tick --instrument MNQ
    python -m futures.futures_trader_core --status               # read-only snapshot
    python -m futures.futures_trader_core --drill entry          # forced scenario drill
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import pandas as pd  # noqa: E402

from futures.instruments import MES, MNQ, get as get_instrument  # noqa: E402
from futures.futures_session import (  # noqa: E402
    et_now, is_session_open, session_phase,
)
from futures.futures_risk_rails import FuturesRiskRails  # noqa: E402
from futures import futures_live_data as fld  # noqa: E402

STATE_DIR = REPO / "automation" / "state" / "futures" / "trader"
LEDGER = STATE_DIR / "decisions.jsonl"
LAST_TICK = STATE_DIR / "last-tick.json"
LOOP_STATE = STATE_DIR / "loop-state.json"
HEARTBEAT = STATE_DIR / "heartbeat.json"

# The real-broker lane's state root, RELATIVE to whatever STATE_DIR currently is.
BROKER_LANE_DIRNAME = "trader-broker"


def lane_paths(state_dir=None, backend=None) -> dict:
    """Resolve this lane's state files. Explicit state_dir wins; else by backend.

    Two lanes run the SAME decisions -- one on the local fill simulator (the persistent
    book of record) and one on the real broker (the fill-parity lane) -- so they must
    never share position/ledger files or each would read the other's fills as its own.
    `trader/` stays the fillsim default, so no existing path or monitor entry moves.

    RESOLVED AT CALL TIME, deliberately, off the CURRENT module globals. A frozen
    import-time mapping silently defeated `monkeypatch.setattr(core, "STATE_DIR", tmp)`,
    which is exactly how drills and tests isolate themselves -- and the replay drill
    writing into real state is a bug this file has already had once tonight. Reading the
    globals live keeps that isolation working.
    """
    if state_dir is None and backend and backend.lower() == "tastytrade":
        state_dir = STATE_DIR.parent / BROKER_LANE_DIRNAME
    if state_dir is None:
        return {"dir": STATE_DIR, "ledger": LEDGER, "last_tick": LAST_TICK,
                "loop_state": LOOP_STATE, "heartbeat": HEARTBEAT}
    d = Path(state_dir)
    return {"dir": d, "ledger": d / "decisions.jsonl", "last_tick": d / "last-tick.json",
            "loop_state": d / "loop-state.json", "heartbeat": d / "heartbeat.json"}

DEFAULT_INSTRUMENT = "MES"
DEFAULT_BACKEND = os.environ.get("FUTURES_BROKER", "fillsim")

# Refresh the bar cache at most this often (Yahoo is delayed anyway; hammering it
# buys nothing and risks the documented futures-symbol flakiness).
DATA_REFRESH_MIN_SECONDS = 60


# ── broker factory ────────────────────────────────────────────────────────────

def make_broker(backend: Optional[str] = None, *, state_dir: Optional[Path] = None,
                start_equity: Optional[float] = None):
    """Return an execution backend by name. The one seam the whole venue question sits behind.

    "fillsim"     local gap-fill-correct paper exchange. No network, no account. DEFAULT.
    "tastytrade"  the real sandbox adapter. Routes only when armed AND provisioned.
    """
    backend = (backend or DEFAULT_BACKEND).lower()
    if backend == "fillsim":
        from futures.fill_sim_broker import FillSimBroker  # noqa: PLC0415

        return FillSimBroker(state_dir=state_dir or STATE_DIR, start_equity=start_equity)
    if backend == "tastytrade":
        from futures.tastytrade_paper import TastytradeBroker  # noqa: PLC0415

        _load_broker_env()
        return TastytradeBroker(watch_only=os.environ.get("FUTURES_ARMED") != "1")
    raise ValueError(f"unknown broker backend {backend!r} (want 'fillsim' or 'tastytrade')")


ENV_FILE = REPO / ".env.tastytrade"


def _load_broker_env() -> bool:
    """Load sandbox credentials from the gitignored store into the process env.

    The adapter reads TT_SECRET/TT_REFRESH from os.environ, which works from a shell
    that exported them and silently does NOT from a scheduled task, where there is no
    shell at all. Running by hand therefore proved nothing about the scheduled path --
    the same lesson the probe's ModuleNotFoundError taught an hour earlier, in a
    different disguise.

    Values are never printed, never logged, never echoed into a ledger row.
    `setdefault` so a genuinely pre-set env always wins.
    """
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        return True
    except OSError:
        return False


def backend_name(broker) -> str:
    return type(broker).__name__


def is_simulated(broker) -> bool:
    """True when fills are ours, not an exchange's. Stamped on every ledger row so a
    downstream reader can never mistake sim P&L for broker P&L (the crypto-twin rule)."""
    return type(broker).__name__ == "FillSimBroker"


# ── io helpers ────────────────────────────────────────────────────────────────

def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _append_ledger(record: dict, paths: Optional[dict] = None) -> None:
    paths = paths or lane_paths()
    try:
        paths["dir"].mkdir(parents=True, exist_ok=True)
        with paths["ledger"].open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception:  # noqa: BLE001 -- journaling never breaks the tick
        pass


def _write_heartbeat(now_et: dt.datetime, verdict: str, detail: dict,
                     paths: Optional[dict] = None) -> None:
    """Liveness beacon, written on EVERY tick including no-ops.

    Shipped with the first commit on purpose: the crypto twin once went dark for four
    days because nothing recorded that it had stopped ticking. A monitor can only
    notice silence if something was supposed to be making noise.
    """
    _atomic_write_json((paths or lane_paths())["heartbeat"], {
        "last_tick_et": now_et.isoformat(timespec="seconds"),
        "verdict": verdict,
        "session_phase": session_phase(now_et),
        "detail": detail,
    })


# ── data ──────────────────────────────────────────────────────────────────────

def refresh_data(root: str, interval: str = "5m", *, force: bool = False) -> dict:
    """Extend the live bar cache, rate-limited. Returns the freshness verdict either way.

    Persists `fld.FRESHNESS_FILE` on every call (2026-08-10 fix). Before this fix the
    file was only ever written by `futures_live_data.py`'s own `--append`/`--check` CLI
    path -- never by the live tick loop that actually calls this function -- so the
    persisted snapshot silently froze at whatever a manual CLI run last wrote (caught
    2026-08-10: `state_freshness_audit.py` flagged it a full session behind while the
    live bar cache itself was refreshing correctly, i.e. the watchdog needed its own
    watchdog wired to the real call site). This is exactly the C7 class this module's
    own docstring warns about.
    """
    should = force
    if not should:
        try:
            snap = json.loads(fld.FRESHNESS_FILE.read_text(encoding="utf-8"))
            last = dt.datetime.fromisoformat(snap["written_at_et"])
            should = (et_now() - last).total_seconds() >= DATA_REFRESH_MIN_SECONDS
        except Exception:  # noqa: BLE001 -- no snapshot yet -> refresh
            should = True
    if should:
        try:
            fld.append_live(root, interval)
        except Exception as e:  # noqa: BLE001 -- a failed fetch must surface as STALE,
            # never as a silent success (L241). The freshness check below is what
            # actually decides, and it reads the file, not this call's return value.
            _append_ledger({"event": "data_refresh_failed", "root": root,
                            "error": f"{type(e).__name__}: {e}",
                            "at_et": et_now().isoformat(timespec="seconds")})
    verdict = fld.freshness(root, interval)
    try:
        fld.write_freshness_snapshot((root,), interval)
    except Exception:  # noqa: BLE001 -- snapshot write never breaks the tick
        pass
    return verdict


def _snap_signal_to_tick(sig: dict, inst) -> dict:
    """Return a COPY of `sig` with every price on a valid tick for `inst`.

    Fixes the 2026-08-31 scar: Tastytrade rejects any leg whose price is not a
    multiple of the contract tick (`invalid_price_increment`), and a rejected
    stop leg aborts the entire bracket -- so every entry became ENTER_REFUSED
    while the tick-agnostic fill simulator traded on regardless.

    Protective legs (stop) snap TOWARD entry so the realised risk can only be
    <= the risk the rails sized for. Entry/tp1/runner snap to nearest tick.
    Immutable by construction: the caller's signal dict is never touched.
    """
    from .instruments import snap, snap_protective  # noqa: PLC0415

    tick = float(getattr(inst, "tick_size", 0) or 0)
    if tick <= 0:
        return sig

    out = dict(sig)
    entry = snap(float(sig["entry"]), tick)
    out["entry"] = entry
    out["stop"] = snap_protective(float(sig["stop"]), tick, entry=entry)
    for key in ("tp1", "runner"):
        if sig.get(key) is not None:
            out[key] = snap(float(sig[key]), tick)

    # A stop that collapses onto the entry is not a stop. Push it one tick out --
    # this is the ONE case where widening is correct, and one tick of extra risk
    # is immaterial next to placing a zero-distance protective order.
    if out["stop"] == entry:
        out["stop"] = round(entry + (tick if float(sig["stop"]) >= entry else -tick), 10)
    return out


# ── the tick ──────────────────────────────────────────────────────────────────

def run_tick(instrument: str = DEFAULT_INSTRUMENT, *, broker=None,
             rails: Optional[FuturesRiskRails] = None,
             backend: Optional[str] = None,
             now_et: Optional[dt.datetime] = None,
             bars: Optional[pd.DataFrame] = None,
             force_refresh: bool = False,
             refresh: bool = True,
             freshness_override: Optional[str] = None,
             state_dir=None) -> dict:
    """One deterministic see -> decide -> act pass. Never raises; always journals.

    Order matters and is not arbitrary: EXITS are managed before ENTRIES are even
    considered, and forced-flatten is checked before both. A tick that dies partway
    must never have left a position unmanaged while it was off looking for a new one.
    """
    now_et = now_et or et_now()
    inst = get_instrument(instrument)
    rails = rails or FuturesRiskRails()
    broker = broker or make_broker(backend)
    connected = bool(broker.connect())
    # Two lanes run the same decisions against different execution backends; they must
    # never share position/ledger files or each would read the other's fills as its own.
    paths = lane_paths(state_dir, backend or (
        "fillsim" if is_simulated(broker) else "tastytrade"))

    record: dict = {
        "ts_et": now_et.isoformat(timespec="seconds"),
        "instrument": inst.symbol,
        "backend": backend_name(broker),
        "simulated_fills": is_simulated(broker),
        "session_phase": session_phase(now_et),
        "action": "HOLD",
        "reason": "",
        "connected": connected,
    }

    # A lane that cannot reach its broker must not go on describing itself as a broker
    # lane. Without this the tick happily reported simulated_fills=false while the
    # adapter had silently failed to authenticate -- which is how phantom "BROKER" rows
    # end up in a ledger whose entire interpretability rests on that column being true.
    # Refuse the tick outright rather than degrade quietly into a half-lane (C7).
    if not connected and not is_simulated(broker):
        # 2026-08-30 diagnosability fix: carry the adapter's OWN failure detail (exception
        # class/repr/http_status, set by TastytradeBroker.connect()'s except blocks) into
        # this ledger row. Before this, "why" lived only in a log.error() call that
        # pythonw's no-console deployment discards outright -- 76% of 2026-08-28's ticks
        # refused with zero recoverable reason. connect_failure is None for a broker that
        # has no such attribute (e.g. a future backend) -- never assumed present.
        connect_failure = getattr(broker, "last_failure_detail", None)
        record.update(action="HOLD", reason="broker_not_connected",
                      detail="adapter did not authenticate -- refusing to act or journal "
                             "as a BROKER lane. Check .env.tastytrade is readable.",
                      connect_failure=connect_failure)
        _write_heartbeat(now_et, "ERROR_NOT_CONNECTED", {"backend": backend_name(broker)}, paths)
        _append_ledger(record, paths)
        _atomic_write_json(paths["last_tick"], record)
        return record

    # 1. Session gate. Outside the session there is nothing to manage and nothing to do.
    if not is_session_open(now_et):
        record.update(action="HOLD", reason=f"session {session_phase(now_et)}")
        _write_heartbeat(now_et, "HOLD_SESSION_CLOSED", {"phase": session_phase(now_et)}, paths)
        _append_ledger(record, paths)
        _atomic_write_json(paths["last_tick"], record)
        return record

    # 2. Data. Freshness is computed even when the refresh throws -- a dead feed must
    #    read as stale, not as "no news".
    #
    #    `refresh`/`freshness_override` exist for REPLAY DRILLS, which feed historical
    #    bars at a historical `now_et`: the live feed is irrelevant there and its real
    #    verdict (CLOSED/RED against a wall clock that is days ahead of the bar) would
    #    block every entry and make the drill prove nothing. They are keyword-only and
    #    default to live behaviour, so a production tick cannot reach them by accident.
    if refresh and freshness_override is None:
        fresh = refresh_data(inst.symbol, force=force_refresh)
    else:
        fresh = fld.freshness(inst.symbol, "5m")
    if freshness_override is not None:
        fresh = dict(fresh, verdict=freshness_override, overridden=True)
        record["freshness_overridden"] = True
    record["freshness"] = fresh["verdict"]
    record["newest_bar_et"] = fresh.get("newest_bar_et")

    if bars is None:
        bars = fld.load_series(inst.symbol, "5m", mode="live")
    last_price = float(bars["close"].iloc[-1]) if len(bars) else None
    last_bar = bars.iloc[-1] if len(bars) else None
    record["last_price"] = last_price

    # 3. EXITS FIRST -- always, regardless of every gate above except the session itself.
    #    process_quote returns ONE flat event dict ({"event": ..., "action": ...}), not a
    #    list under an "events" key. Reading the wrong shape here would have silently
    #    recorded zero exits forever while the fill engine worked perfectly -- caught by
    #    the scenario drills, which is what they are for.
    exit_events = []
    if last_price is not None and hasattr(broker, "process_quote"):
        # Snapshot the position BEFORE the fill engine runs: once a round trip closes,
        # the position object is gone, and with it the entry price, stop, setup and
        # entry time the trade ledger needs. Capturing after would silently write rows
        # with empty entry context.
        pre = _position_snapshot(broker, inst.symbol)
        try:
            ev = broker.process_quote(
                inst.symbol, last_price,
                bar_open=float(last_bar["open"]), bar_high=float(last_bar["high"]),
                bar_low=float(last_bar["low"]), quote_time_et=now_et)
            if ev and ev.get("event") and ev["event"] != "noop":
                exit_events = [ev]
                try:
                    from futures.futures_journal import journal_exit  # noqa: PLC0415

                    journal_exit(instrument=inst.symbol, event=ev,
                                 backend=backend_name(broker), simulated=is_simulated(broker))
                    # A round trip is CLOSED when nothing is left open. That is the only
                    # moment a trades.csv row is meaningful -- a TP1 partial is not a
                    # completed trade, and writing one per fill would double-count.
                    if ev.get("qty_open_after") == 0:
                        _record_round_trip(broker, inst, pre, ev, now_et, record)
                except Exception:  # noqa: BLE001 -- journaling never breaks execution
                    pass
        except Exception as e:  # noqa: BLE001
            record["exit_error"] = f"{type(e).__name__}: {e}"
    record["exit_events"] = exit_events

    # 4. Forced flatten (settlement stop / end of RTH). Demands an action, never blocks one.
    flat_call = rails.must_flatten(now_et)
    if flat_call.allow and not broker.is_flat(inst.symbol):
        positions = {p["symbol"]: p for p in broker.get_positions()}
        pos = next((p for s, p in positions.items() if inst.symbol in s), None)
        if pos and last_price is not None:
            side = "SELL" if float(pos.get("qty", 0)) > 0 else "BUY"
            broker.close_position(inst.symbol, abs(int(float(pos["qty"]))), side, last_price)
            record.update(action="FLATTEN", reason=flat_call.reason)
            _write_heartbeat(now_et, "FLATTEN", {"rail": flat_call.rail}, paths)
            _append_ledger(record, paths)
            _atomic_write_json(paths["last_tick"], record)
            return record

    # 4b. Sandbox-reset reconciliation (the real-broker lane only).
    #     The Tastytrade cert environment WIPES positions and orders every 24 hours. Our
    #     local record of an open position therefore outlives the position itself, and a
    #     naive reading of that gap is "we lost a fill" -- which would either strand the
    #     lane in a permanent no-stack HOLD or make it journal a phantom exit. The broker
    #     is the source of truth (C11): if it says flat and we think we are not, the
    #     position is GONE, and on this venue the overwhelmingly likely cause is the daily
    #     reset rather than a missed fill. Log it explicitly -- never silently -- and clear.
    reset = _reconcile_broker_reset(broker, inst.symbol, paths, now_et)
    if reset:
        record["broker_reset"] = reset

    # 5. No stacking. One position per instrument (Rule 4 analogue: adding needs a new
    #    confirmed trigger and a new leg, which this lane does not yet implement).
    if not broker.is_flat(inst.symbol):
        record.update(action="HOLD", reason="position_open_no_stack")
        _write_heartbeat(now_et, "HOLD_POSITION_OPEN", {"exit_events": exit_events}, paths)
        _append_ledger(record, paths)
        _atomic_write_json(paths["last_tick"], record)
        return record

    # 6. SEE -- the validated watcher fleet, fed the LIVE frame.
    from futures.futures_heartbeat_core import compute_latest_signals  # noqa: PLC0415

    seen = compute_latest_signals(inst, bars=bars)
    record["n_signals"] = len(seen.get("signals", []))
    if seen.get("error"):
        record["see_error"] = seen["error"]
    if seen.get("snapshot"):
        record["snapshot"] = seen["snapshot"]

    # 7. DECIDE -- validated filter first, then the dollar rails.
    from futures.strategy_config_v3 import should_take_v3  # noqa: PLC0415

    vix = float(seen.get("snapshot", {}).get("vix", 17.0))
    equity = broker.get_account_equity() or rails.start_equity
    session_pnl = _session_realized_pnl(broker, now_et)
    record["equity"] = equity
    record["session_realized_pnl"] = session_pnl

    chosen = None
    for sig in seen.get("signals", []):
        if not should_take_v3(sig["watcher"], sig["direction"], sig["confidence"], vix):
            continue
        # TICK ALIGNMENT (scar 2026-08-31 -- see instruments.py "Tick alignment").
        # Snap BEFORE sizing: stop_points below feeds rails.max_qty_for, so a stop
        # widened after sizing would exceed the approved risk. Protective legs round
        # toward entry (never wider); entry/targets round to nearest tick. New dict --
        # the incoming signal is never mutated.
        sig = _snap_signal_to_tick(sig, inst)
        stop_points = abs(float(sig["entry"]) - float(sig["stop"]))
        qty = rails.max_qty_for(equity=equity, stop_points=stop_points, instrument=inst)
        if qty < 1:
            record.setdefault("rejected", []).append(
                {"setup": sig["setup"], "rail": "sizing", "stop_points": stop_points})
            continue
        verdict = rails.check_entry(
            now_et=now_et, equity=equity, session_realized_pnl=session_pnl,
            stop_points=stop_points, qty=qty, instrument=inst,
            freshness_verdict=fresh["verdict"])
        if not verdict.allow:
            record.setdefault("rejected", []).append(
                {"setup": sig["setup"], "rail": verdict.rail, "reason": verdict.reason})
            continue
        chosen = {"signal": sig, "qty": qty, "stop_points": stop_points,
                  "risk_usd": stop_points * inst.point_value * qty}
        break

    if chosen is None:
        record.update(action="HOLD",
                      reason="no_qualifying_signal" if record["n_signals"] else "no_signal")
        _write_heartbeat(now_et, "HOLD", {"n_signals": record["n_signals"],
                                          "rejected": record.get("rejected", [])}, paths)
        _append_ledger(record, paths)
        _atomic_write_json(paths["last_tick"], record)
        return record

    # 8. ACT.
    sig = chosen["signal"]
    side = "BUY" if sig["direction"] == "long" else "SELL"
    tp1_qty = max(1, int(chosen["qty"] * 0.5)) if chosen["qty"] > 1 else chosen["qty"]
    ids = broker.place_bracket(
        inst.symbol, side, chosen["qty"], float(sig["entry"]), float(sig["tp1"]),
        float(sig["stop"]), runner_price=sig.get("runner"), tp1_qty=tp1_qty)

    record.update(
        action="ENTER" if ids else "ENTER_REFUSED",
        reason=sig["setup"],
        entry={"side": side, "qty": chosen["qty"], "entry": sig["entry"],
               "stop": sig["stop"], "tp1": sig["tp1"], "runner": sig.get("runner"),
               "stop_points": chosen["stop_points"], "risk_usd": chosen["risk_usd"],
               "setup": sig["setup"], "watcher": sig["watcher"],
               "confidence": sig["confidence"], "direction": sig["direction"]},
        order_ids=ids,
    )
    _write_heartbeat(now_et, record["action"], {"setup": sig["setup"], "qty": chosen["qty"]}, paths)
    _append_ledger(record, paths)
    _atomic_write_json(paths["last_tick"], record)

    try:
        from futures.futures_journal import journal_entry  # noqa: PLC0415

        journal_entry(record)
    except Exception:  # noqa: BLE001 -- journaling never breaks execution
        pass
    return record


def _reconcile_broker_reset(broker, symbol: str, paths: dict,
                            now_et: dt.datetime) -> Optional[dict]:
    """Detect and record the Tastytrade cert environment's 24-hour wipe.

    Returns a description of the reconciliation, or None when nothing needed doing.

    Only meaningful for a broker whose positions live remotely. The fill simulator's
    positions are ours and persist by design, so it is skipped -- treating a fillsim
    disagreement as a "reset" would paper over a genuine state bug in our own engine.
    """
    if is_simulated(broker):
        return None
    local = paths["dir"] / "open-position.json"
    try:
        remembered = json.loads(local.read_text(encoding="utf-8")) if local.exists() else None
    except (OSError, json.JSONDecodeError):
        remembered = None

    try:
        flat_at_broker = broker.is_flat(symbol)
    except Exception:  # noqa: BLE001 -- an unreadable broker is not a reset; do nothing
        return None

    if remembered and flat_at_broker:
        note = {
            "at_et": now_et.isoformat(timespec="seconds"),
            "event": "broker_position_vanished",
            "symbol": symbol,
            "remembered": remembered,
            "interpretation": ("cert sandbox resets every 24h -- position wiped remotely, "
                               "not a missed fill. Local record cleared so the lane can "
                               "trade again instead of stranding in no-stack HOLD."),
        }
        _append_ledger(note, paths)
        try:
            local.unlink()
        except OSError:
            pass
        return note

    if not flat_at_broker and not remembered:
        # Remember what the broker is holding so the NEXT wipe is detectable.
        try:
            pos = broker.get_positions()
            if pos:
                _atomic_write_json(local, {"recorded_at_et": now_et.isoformat(timespec="seconds"),
                                           "positions": pos})
        except Exception:  # noqa: BLE001
            pass
    return None


def _position_snapshot(broker, symbol: str) -> dict:
    """The raw open/pending position dict, or {} -- the entry context a closed round
    trip needs. Read-only; returns {} for any broker without a positions snapshot."""
    try:
        if hasattr(broker, "get_positions_snapshot"):
            return dict(broker.get_positions_snapshot().get(symbol) or {})
    except Exception:  # noqa: BLE001
        pass
    return {}


def _record_round_trip(broker, inst, pre: dict, ev: dict, now_et: dt.datetime,
                       record: dict) -> None:
    """Append one CLOSED round trip to journal/futures/trades.csv."""
    from futures.futures_journal import record_trade  # noqa: PLC0415

    entry_px = pre.get("entry")
    exit_px = ev.get("fill_price")
    stop_px = pre.get("stop")
    direction = pre.get("direction", "")
    stop_points = (abs(float(entry_px) - float(stop_px))
                   if entry_px is not None and stop_px is not None else None)
    risk_usd = stop_points * inst.point_value * (pre.get("qty_total") or 1) if stop_points else None
    pnl = ev.get("pnl")

    hold_min = None
    entry_time = pre.get("entry_time_et")
    if entry_time:
        try:
            hold_min = round(
                (now_et - dt.datetime.fromisoformat(str(entry_time))).total_seconds() / 60.0, 1)
        except (TypeError, ValueError):
            hold_min = None

    record_trade({
        "date": now_et.strftime("%Y-%m-%d"),
        "session_phase": session_phase(now_et),
        "instrument": inst.symbol,
        "contract_month": pre.get("contract_month", ""),
        "time_entry_et": entry_time or "",
        "time_exit_et": now_et.isoformat(timespec="seconds"),
        "hold_minutes": hold_min if hold_min is not None else "",
        "setup": pre.get("setup", record.get("reason", "")),
        "watcher": pre.get("watcher", ""),
        "confidence": pre.get("confidence", ""),
        "direction": direction,
        "side": "BUY" if direction == "long" else "SELL",
        "qty": pre.get("qty_total", ""),
        "entry_px": entry_px if entry_px is not None else "",
        "exit_px": exit_px if exit_px is not None else "",
        "stop_px": stop_px if stop_px is not None else "",
        "tp1_px": pre.get("tp1", ""),
        "runner_px": pre.get("runner", "") if pre.get("runner") is not None else "",
        "stop_points": round(stop_points, 2) if stop_points else "",
        "point_value": inst.point_value,
        "risk_usd": round(risk_usd, 2) if risk_usd else "",
        "dollar_pnl": round(float(pnl), 2) if pnl is not None else "",
        "r_multiple": (round(float(pnl) / risk_usd, 3)
                       if pnl is not None and risk_usd else ""),
        "exit_reason": ev.get("action", ev.get("event", "")),
        "equity_pre": record.get("equity", ""),
        "equity_post": broker.get_account_equity() or "",
        # The disclosure that makes every downstream number interpretable.
        "fills": "SIMULATED" if is_simulated(broker) else "BROKER",
        "backend": backend_name(broker),
        "followed_rules": "Y",
        "rails_checked": "entry gated by FuturesRiskRails.check_entry",
        "notes": "",
    })


# The fillsim account ledger's field names. Named here rather than inlined because a
# rename on the broker side would otherwise degrade this to a silent 0.0 and quietly
# disable the session-loss rail -- the C14 dead-knob shape. `test_session_pnl_reads_
# the_real_ledger_fields` fails loudly if these drift.
_PNL_FIELD = "daily_pnl"
_PNL_DATE_FIELD = "last_reset_date_et"


def _session_realized_pnl(broker, now_et: dt.datetime) -> float:
    """Realized P&L for the CURRENT session date. 0.0 when genuinely unknowable.

    A stale date returns 0.0 on purpose: yesterday's losses must not consume today's
    session budget. Note the failure direction -- an unreadable ledger makes the
    session-loss rail MORE permissive, so this value is never the only thing between
    the arm and a blown day. The account floor, which reads live equity, is absolute.
    """
    try:
        snap = broker.get_account_snapshot()
    except Exception:  # noqa: BLE001 -- broker without a snapshot surface
        return 0.0
    if not isinstance(snap, dict):
        return 0.0
    if snap.get(_PNL_DATE_FIELD) != now_et.strftime("%Y-%m-%d"):
        return 0.0
    try:
        return float(snap.get(_PNL_FIELD, 0.0))
    except (TypeError, ValueError):
        return 0.0


# ── status / drills ───────────────────────────────────────────────────────────

def status(instrument: str = DEFAULT_INSTRUMENT, backend: Optional[str] = None) -> dict:
    """Read-only snapshot. Never places, cancels or mutates anything."""
    broker = make_broker(backend)
    broker.connect()
    now = et_now()
    out = {
        "checked_at_et": now.isoformat(timespec="seconds"),
        "session_phase": session_phase(now),
        "session_open": is_session_open(now),
        "backend": backend_name(broker),
        "simulated_fills": is_simulated(broker),
        "equity": broker.get_account_equity(),
        "flat": broker.is_flat(instrument),
        "positions": broker.get_positions(),
        "data": fld.freshness(instrument, "5m"),
    }
    for path, key in ((LAST_TICK, "last_tick"), (HEARTBEAT, "heartbeat")):
        try:
            out[key] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            out[key] = None
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Autonomous futures tick (broker-agnostic)")
    ap.add_argument("--tick", action="store_true", help="run one see->decide->act pass")
    ap.add_argument("--status", action="store_true", help="read-only snapshot")
    ap.add_argument("--instrument", default=DEFAULT_INSTRUMENT)
    ap.add_argument("--backend", default=None, help="fillsim (default) | tastytrade")
    ap.add_argument("--force-refresh", action="store_true")
    args = ap.parse_args(argv)

    if args.status:
        print(json.dumps(status(args.instrument, args.backend), indent=2, default=str))
        return 0
    if args.tick:
        rec = run_tick(args.instrument, backend=args.backend,
                       force_refresh=args.force_refresh)
        print(json.dumps(rec, indent=2, default=str))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
