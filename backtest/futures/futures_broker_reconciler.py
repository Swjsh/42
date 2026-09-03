"""futures_broker_reconciler.py -- closes the exit-journaling gap on the real-broker lane.

FUTURES-BROKER-LANE-NEVER-LOGS-EXITS (filed 2026-09-03, `automation/overnight/queue.md`).

ROOT CAUSE, verified cold (see the queue item's DONE note for the full evidence trail):
  1. `futures_trader_core.run_tick`'s exit-detection block (step 3) is gated on
     `hasattr(broker, "process_quote")` -- only `FillSimBroker` implements that method.
     `TastytradeBroker` has none, so for the real-broker lane NOTHING ever notices a
     broker-side TP1/stop fill. `exit_events` stays `[]` forever regardless of what the
     exchange actually did.
  2. The FLATTEN branch (step 4) calls `broker.close_position()` directly and returns --
     it never calls `journal_exit`/`record_trade`, so even the one exit the engine itself
     triggers was never journaled.
  3. `_record_round_trip`'s `pre` snapshot comes from `broker.get_positions_snapshot()`
     (step 3), which `TastytradeBroker` also does not implement -- even if (1) were fixed,
     the entry context (price/stop/tp1/setup) would still write empty.
  Net effect: `journal/futures/trades.csv` has carried zero BROKER rows since the lane
  started routing real orders 2026-08-31, against 3 confirmed real ENTER fills and their
  real closes (verified read-only against the sandbox's own `get_order_history`).

THIS MODULE FIXES ONLY THE WRITER. It never places, cancels, replaces, or times an
order -- it reads `broker.get_recent_fills()` (a new READ-ONLY method) and journals rows
for closing-side fills that have not been journaled yet, attributed to the entry this
lane itself placed (persisted in `open-entry.json` at ENTER time, because (3) above means
the broker cannot answer "what was the entry" itself). No change to when or whether the
lane enters or exits.

FOLLOW-UP FIXED 2026-09-03 (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL, filed from this module's
own docstring above): `place_bracket` still places TP1 and STOP as two INDEPENDENT GTC
orders (the SDK's `ComplexOrderType.OCO/OTOCO` + `Account.place_complex_order` exist, but
switching the routing path to them needs a supervised daytime dry-run against the cert
sandbox to confirm futures-leg support -- not done tonight, every broker call was read-only
by instruction). The mitigation instead: `reconcile_broker_exits` below now cancels the
OTHER leg the instant the first closing fill is seen (`broker.cancel_order`, via the
`leg_ids` map `record_open_entry` now persists), and the FLATTEN path in
`futures_trader_core.run_tick` now calls `cancel_all()` + polls `get_working_orders()` for
confirmation before `close_position()`. Neither eliminates the race inside a single tick
interval; both make the STRAY-FILL window one tick wide instead of unbounded. A stray
closing-side fill this reconciler still cannot attribute to the tracked entry is logged to
`anomalies.jsonl` and EXCLUDED from that entry's P&L rather than silently dropped or
guessed into a fabricated round trip.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo

    _ET = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 -- best effort; falls back to naive comparison
    _ET = None


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def open_entry_path(paths: dict) -> Path:
    return paths["dir"] / "open-entry.json"


def journaled_fills_path(paths: dict) -> Path:
    return paths["dir"] / "journaled-fills.json"


def anomalies_path(paths: dict) -> Path:
    return paths["dir"] / "anomalies.jsonl"


def record_open_entry(paths: dict, *, symbol: str, entry: dict, order_ids: list,
                      now_et: dt.datetime, leg_ids: Optional[dict] = None) -> None:
    """Persist the just-placed bracket's entry context (Rule 8 shape: this is a system
    record of what WAS placed, not a new thesis) so a later tick can attribute closing
    fills back to it -- the broker itself cannot answer "what was the entry" (see module
    docstring point 3).

    `leg_ids` (added 2026-09-03, FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL) is the optional
    `{"entry": id, "tp1": id, "stop": id, "runner": id}` map from
    `TastytradeBroker.last_bracket_legs` -- the sibling-cancel safety net in
    `reconcile_broker_exits` below reads it to find "the OTHER leg" the instant one fills.
    Omitted or None (e.g. a broker with no such map) simply disables that safety net; never
    guessed."""
    data = {
        "symbol": symbol,
        "entry": entry,
        "order_ids": list(order_ids or []),
        "entry_time_et": now_et.isoformat(timespec="seconds"),
        "closed_qty": 0.0,
        "leg_ids": dict(leg_ids) if leg_ids else {},
        "sibling_cancelled": False,
    }
    _atomic_write_json(open_entry_path(paths), data)


def clear_open_entry(paths: dict) -> None:
    p = open_entry_path(paths)
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def _already_journaled(paths: dict, fill_id) -> bool:
    return fill_id in _read_json(journaled_fills_path(paths), [])


def _mark_journaled(paths: dict, fill_id) -> None:
    seen = _read_json(journaled_fills_path(paths), [])
    if fill_id not in seen:
        seen.append(fill_id)
        # Bounded -- this is an idempotency cache, not the ledger; trades.csv is the ledger.
        _atomic_write_json(journaled_fills_path(paths), seen[-500:])


def _append_anomaly(paths: dict, record: dict) -> None:
    try:
        p = anomalies_path(paths)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


def append_anomaly(paths: dict, record: dict) -> None:
    """Public: append one row to this lane's anomalies.jsonl (FUTURES-BROKER-OCO-AND-
    FLATTEN-CANCEL, 2026-09-03). Callers outside this module -- e.g.
    `futures_trader_core`'s flatten-cancel-confirm sweep -- use this same loud, never-silent
    anomaly channel rather than duplicating the append logic or reaching into `_append_anomaly`."""
    _append_anomaly(paths, record)


def _entry_time_utc(entry_time_et_naive: dt.datetime) -> dt.datetime:
    if _ET is not None:
        return entry_time_et_naive.replace(tzinfo=_ET).astimezone(dt.timezone.utc)
    # Fallback: assume ET is UTC-4 (EDT) -- close enough not to mis-order same-day fills;
    # never used unless zoneinfo itself is unavailable.
    return (entry_time_et_naive + dt.timedelta(hours=4)).replace(tzinfo=dt.timezone.utc)


def reconcile_broker_exits(broker, inst, paths: dict, now_et: dt.datetime,
                           point_value: float, backend_name: str,
                           label: str = "reconciled_2026_09_03",
                           until_et: Optional[dt.datetime] = None) -> list[dict]:
    """Journal any closing-side broker fills for the tracked open entry not yet journaled.

    `until_et` (naive ET, optional) caps how far forward the fill search looks -- pass the
    NEXT entry's own timestamp when reconciling historical entries out of order (a backfill
    walking multiple past ENTER rows), otherwise a fill that actually closed a LATER entry
    gets swept into an EARLIER entry's search window (both are on the same symbol, so a
    same-side closing fill is a real ambiguity, not a hypothetical one -- caught by this
    module's own regression test). The live per-tick path always leaves this None: there is
    no "next" entry yet, since the no-stacking gate (step 5 of run_tick) refuses a new ENTER
    while `open-entry.json` still shows this one unclosed.

    Returns the list of newly-journaled exit contributions (possibly empty). Never raises
    -- a reconciliation failure must never break a trading tick (same contract as every
    other journaling call in this lane).
    """
    if not hasattr(broker, "get_recent_fills"):
        return []
    open_entry = _read_json(open_entry_path(paths), None)
    if not open_entry:
        return []

    try:
        from futures.futures_journal import record_trade  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []

    entry = open_entry.get("entry") or {}
    entry_side = str(entry.get("side", "")).upper()  # 'BUY' or 'SELL'
    close_side = "SELL" if entry_side == "BUY" else "BUY"
    entry_qty = float(entry.get("qty") or 0)
    entry_order_ids = sorted(set(open_entry.get("order_ids") or []))

    try:
        entry_time_et = dt.datetime.fromisoformat(open_entry.get("entry_time_et", ""))
    except (TypeError, ValueError):
        entry_time_et = now_et - dt.timedelta(hours=12)
    entry_time_utc = _entry_time_utc(entry_time_et)
    until_utc = _entry_time_utc(until_et) if until_et is not None else None

    try:
        fills = broker.get_recent_fills(inst.symbol, since_et=None, days_back=3)
    except Exception:  # noqa: BLE001
        return []

    # The recorded `entry.entry` is what the SIGNAL asked for (a limit price), not
    # necessarily what actually filled -- a marketable limit can fill through it. Prefer
    # the REAL entry-leg fill (matched by this bracket's own order id) for every P&L
    # calc below; fall back to the recorded signal price only if the broker fill can't be
    # found (never fabricate one, but a signal target is a documented, disclosed fallback).
    entry_px = entry.get("entry")
    entry_fill = next(
        (f for f in fills if f["action"] == entry_side and f["order_id"] in entry_order_ids),
        None)
    if entry_fill is not None and entry_fill["fill_price"] is not None:
        entry_px = entry_fill["fill_price"]

    closing = []
    for f in fills:
        if f["action"] != close_side or not f["filled_at"]:
            continue
        try:
            fill_dt = dt.datetime.fromisoformat(f["filled_at"])
        except ValueError:
            continue
        if until_utc is not None and fill_dt >= until_utc:
            continue
        if fill_dt < entry_time_utc:
            continue
        if _already_journaled(paths, f["fill_id"]):
            continue
        closing.append((fill_dt, f))
    closing.sort(key=lambda pair: pair[0])
    if not closing:
        return []

    # Sibling-cancel (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL, 2026-09-03): the SDK-level
    # ComplexOrderType.OCO/OTOCO exists (tastytrade.order.NewComplexOrder /
    # Account.place_complex_order), but was NOT wired here -- placing a live/dry-run complex
    # order to confirm it actually behaves correctly for a FUTURES leg on the cert sandbox
    # needs a supervised daytime session (every broker call tonight is read-only by
    # instruction), so flipping the routing path on an unverified assumption would be the
    # opposite of a kill-type risk reduction. This is the fallback the queue item asked for:
    # the instant the FIRST new closing fill is SEEN for the tracked entry, cancel the
    # OTHER bracket leg immediately so it cannot also fill (the exact 8-anomaly pattern this
    # fix responds to). Fires at most once per entry (idempotent via `sibling_cancelled`) --
    # never re-cancels an already-cancelled/filled sibling on a later tick.
    leg_ids = open_entry.get("leg_ids") or {}
    if not open_entry.get("sibling_cancelled") and hasattr(broker, "cancel_order") and leg_ids:
        first_fill_id = closing[0][1]["order_id"]
        filled_leg = next((role for role, oid in leg_ids.items()
                           if oid is not None and oid == first_fill_id), None)
        sibling_role = {"tp1": "stop", "stop": "tp1"}.get(filled_leg)
        sibling_id = leg_ids.get(sibling_role) if sibling_role else None
        if sibling_id is not None and sibling_id != first_fill_id:
            try:
                cancelled = broker.cancel_order(sibling_id)
            except Exception:  # noqa: BLE001 -- a failed cancel must never break journaling
                cancelled = None
            _append_anomaly(paths, {
                "at_et": now_et.isoformat(timespec="seconds"),
                "event": "sibling_leg_cancelled",
                "symbol": inst.symbol,
                "filled_leg": filled_leg, "filled_order_id": first_fill_id,
                "cancelled_leg": sibling_role, "cancelled_order_id": sibling_id,
                "cancel_call_ok": cancelled,
                "interpretation": (f"{filled_leg} leg filled -- cancelled the resting "
                                   f"{sibling_role} leg immediately (no native OCO wired "
                                   "yet; see this function's own comment) to prevent it "
                                   "from also filling and reopening a stray position."),
            })
        # Mark fired regardless of whether a sibling id was found -- a bracket with no
        # resolvable leg_ids (e.g. an entry recorded before this fix shipped) must not
        # retry every tick forever; that state is logged once via the anomaly above (or
        # simply has nothing to cancel) and is not retried.
        open_entry["sibling_cancelled"] = True

    already_closed = float(open_entry.get("closed_qty") or 0)
    stop_px = entry.get("stop")
    tp1_px = entry.get("tp1")
    stop_points = (abs(float(entry_px) - float(stop_px))
                   if entry_px is not None and stop_px is not None else None)

    journaled: list[dict] = []
    for fill_dt, f in closing:
        remaining = entry_qty - already_closed
        if remaining <= 1e-9:
            # This entry is already fully accounted for -- a further closing-side fill on
            # this symbol is a STRAY (a resting TP1/stop leg the bracket never cancelled --
            # see module docstring -- or possibly another lane on this shared sandbox
            # account). Flag it; never fabricate an entry side for it, never drop it.
            _append_anomaly(paths, {
                "at_et": now_et.isoformat(timespec="seconds"),
                "event": "unattributed_closing_fill",
                "symbol": inst.symbol,
                "fill": f,
                "tracked_entry_order_ids": entry_order_ids,
                "interpretation": ("closing-side fill after the tracked entry was already "
                                   "fully closed -- not counted in this entry's P&L. Likely "
                                   "an uncancelled resting bracket leg (no OCO between TP1 "
                                   "and stop) or a fill from a different lane on this shared "
                                   "sandbox account."),
            })
            _mark_journaled(paths, f["fill_id"])
            continue

        qty_this = min(remaining, f["qty"])
        exit_px = f["fill_price"]
        pnl = None
        if entry_px is not None and exit_px is not None:
            diff = (float(entry_px) - float(exit_px)) if entry_side == "SELL" else \
                   (float(exit_px) - float(entry_px))
            pnl = diff * qty_this * point_value
        risk_usd = stop_points * point_value * qty_this if stop_points else None

        hold_min = round((fill_dt - entry_time_utc).total_seconds() / 60.0, 1)

        exit_reason = "BROKER_CLOSE"
        if exit_px is not None:
            if stop_px is not None and abs(float(exit_px) - float(stop_px)) < 1e-6:
                exit_reason = "FULL_STOP"
            elif tp1_px is not None and abs(float(exit_px) - float(tp1_px)) < 1e-6:
                exit_reason = "TP1_PARTIAL" if qty_this < entry_qty else "TP1_FULL"

        # The trade DATE is the exit fill's own ET session date, never the `now_et` this
        # was reconciled at -- those differ by construction during a backfill, and even on
        # the live path a fill near midnight UTC could otherwise misdate by a day.
        fill_et = fill_dt.astimezone(_ET) if _ET is not None else fill_dt
        record_trade({
            "date": fill_et.strftime("%Y-%m-%d"),
            "session_phase": "",
            "instrument": inst.symbol,
            "contract_month": "",
            "time_entry_et": open_entry.get("entry_time_et", ""),
            "time_exit_et": f["filled_at"],
            "hold_minutes": hold_min,
            "setup": entry.get("setup", ""),
            "watcher": entry.get("watcher", ""),
            "confidence": entry.get("confidence", ""),
            "direction": entry.get("direction", ""),
            "side": entry_side,
            "qty": qty_this,
            "entry_px": entry_px if entry_px is not None else "",
            "exit_px": exit_px if exit_px is not None else "",
            "stop_px": stop_px if stop_px is not None else "",
            "tp1_px": tp1_px if tp1_px is not None else "",
            "runner_px": entry.get("runner", "") if entry.get("runner") is not None else "",
            "stop_points": round(stop_points, 2) if stop_points else "",
            "point_value": point_value,
            "risk_usd": round(risk_usd, 2) if risk_usd else "",
            "dollar_pnl": round(pnl, 2) if pnl is not None else "",
            "r_multiple": (round(pnl / risk_usd, 3) if pnl is not None and risk_usd else ""),
            "exit_reason": exit_reason,
            "equity_pre": "",
            "equity_post": "",
            "fills": "BROKER",
            "backend": backend_name,
            "followed_rules": "Y",
            "rails_checked": "entry gated by FuturesRiskRails.check_entry",
            "notes": (f"broker_order_ids=entry:{entry_order_ids},exit:{f['order_id']} "
                     f"fill_id={f['fill_id']}"
                     + (f" signal_entry_px={entry.get('entry')}"
                        if entry_fill is not None and entry.get("entry") not in (None, entry_px)
                        else "")
                     + f" {label}"),
        })
        _mark_journaled(paths, f["fill_id"])
        already_closed += qty_this
        journaled.append({"fill": f, "qty": qty_this, "pnl": pnl})

    open_entry["closed_qty"] = already_closed
    if already_closed >= entry_qty - 1e-9:
        clear_open_entry(paths)
        # Post-exit assertion (FUTURES-BROKER-OCO-AND-FLATTEN-CANCEL, 2026-09-03): a round
        # trip journaled as fully closed must actually BE closed at the broker -- flat, with
        # no working orders left resting for the symbol. Read-only; a broken assertion here
        # logs LOUDLY (never raises -- the exit that already correctly journaled above must
        # not be undone by a check running after it).
        try:
            broker_not_flat = not broker.is_flat(inst.symbol)
        except Exception:  # noqa: BLE001
            broker_not_flat = None
        working = None
        if hasattr(broker, "get_working_orders"):
            try:
                working = broker.get_working_orders(inst.symbol)
            except Exception:  # noqa: BLE001
                working = None
        if broker_not_flat or working:
            _append_anomaly(paths, {
                "at_et": now_et.isoformat(timespec="seconds"),
                "event": "post_exit_not_flat",
                "symbol": inst.symbol,
                "broker_not_flat": bool(broker_not_flat),
                "working_orders": working,
                "interpretation": ("journaled this entry as fully closed but the broker "
                                   "still shows an open position and/or working orders for "
                                   "the symbol -- a resting sibling leg likely survived. "
                                   "Investigate before the next entry."),
            })
    else:
        _atomic_write_json(open_entry_path(paths), open_entry)

    return journaled
