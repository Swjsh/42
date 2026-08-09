"""futures_drills.py -- force-fire the futures trading lifecycle before trusting it live.

WHY (FUTURES-FIRST-PLAN WS-F3: "force-fire scenario drills first, then organic"). An
engine that has never taken a trade has never proven it CAN. Waiting for an organic
signal to discover that the entry path, the fill engine, the exit ladder or the journal
is broken is the expensive way to find out -- and the crypto twin's own history says
the gap between "the loop runs" and "the loop trades correctly" is where the bugs live.

TWO KINDS OF DRILL, both writing to a throwaway state dir so live state is untouched:

  SCENARIO drills (`run_scenarios`) -- synthetic bars constructed so each exit path is
    GUARANTEED to fire: entry fill, TP1 partial, full stop, and forced flatten. These
    answer "does each branch work at all", and they fail loudly if a branch is dead.

  REPLAY drill (`run_replay`) -- real recent RTH bars walked forward one at a time
    through the real tick. This answers "what would this engine actually have done".
    Strict no-look-ahead: the frame handed to each tick is sliced to bars at or before
    the current bar, so a watcher cannot see a future it would not have had (C6).

WHAT A DRILL IS NOT: evidence of edge. Fills are simulated and the replay is in-sample
against a strategy filter that was fitted elsewhere. A drill answers "is the machinery
correct", full stop. Edge claims need the canonical battery on a frozen prereg.

CLI:
    python -m futures.futures_drills --scenarios
    python -m futures.futures_drills --replay --days 5 --instrument MES
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import pandas as pd  # noqa: E402

from futures.instruments import get as get_instrument  # noqa: E402
from futures.fill_sim_broker import FillSimBroker  # noqa: E402
from futures.futures_risk_rails import FuturesRiskRails  # noqa: E402
from futures import futures_trader_core as core  # noqa: E402
from futures import futures_journal as fj  # noqa: E402

ET = "America/New_York"


def _mk_bars(rows: list[tuple]) -> pd.DataFrame:
    """rows: (ts_naive_et, open, high, low, close, volume)."""
    df = pd.DataFrame(rows, columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(ET)
    return df


# ── scenario drills ───────────────────────────────────────────────────────────

def run_scenarios(instrument: str = "MES") -> dict:
    """Drive each exit branch deterministically through the real FillSimBroker.

    The broker is exercised directly here (not through `run_tick`) on purpose: these
    drills pin the FILL ENGINE's branches, and routing them through signal generation
    would make a dead branch look like "no signal fired today" instead of a failure.
    """
    inst = get_instrument(instrument)
    tmp = Path(tempfile.mkdtemp(prefix="futdrill-"))
    results: dict = {"instrument": inst.symbol, "state_dir": str(tmp), "scenarios": {}}

    try:
        # --- 1. entry fill: a resting long limit that price trades down through -------
        b = FillSimBroker(state_dir=tmp / "s1", start_equity=2_000.0)
        b.connect()
        ids = b.place_bracket(inst.symbol, "BUY", 1, entry_price=7_800.0,
                              tp1_price=7_820.0, stop_price=7_790.0, runner_price=7_840.0)
        assert ids, "place_bracket returned no order ids"
        b.process_quote(inst.symbol, 7_799.0, bar_open=7_805.0, bar_high=7_806.0,
                        bar_low=7_798.0)
        results["scenarios"]["entry_fill"] = {
            "passed": not b.is_flat(inst.symbol),
            "positions": b.get_positions(),
        }

        # --- 2. TP1 partial: price reaches the first target ---------------------------
        b2 = FillSimBroker(state_dir=tmp / "s2", start_equity=2_000.0)
        b2.connect()
        b2.place_bracket(inst.symbol, "BUY", 2, entry_price=7_800.0, tp1_price=7_820.0,
                         stop_price=7_790.0, runner_price=7_840.0, tp1_qty=1)
        b2.process_quote(inst.symbol, 7_800.0, bar_open=7_802.0, bar_high=7_803.0,
                         bar_low=7_799.0)
        ev = b2.process_quote(inst.symbol, 7_821.0, bar_open=7_805.0, bar_high=7_822.0,
                              bar_low=7_804.0)
        snap = b2.get_account_snapshot()
        results["scenarios"]["tp1_partial"] = {
            # TP1 must realize a partial AND leave the runner open.
            "passed": (ev.get("action") == "TP1_PARTIAL"
                       and ev.get("qty_open_after") == 1
                       and snap["equity"] > 2_000.0),
            "event": ev, "equity": snap["equity"],
        }

        # --- 3. full stop: price trades through the stop ------------------------------
        b3 = FillSimBroker(state_dir=tmp / "s3", start_equity=2_000.0)
        b3.connect()
        b3.place_bracket(inst.symbol, "BUY", 1, entry_price=7_800.0, tp1_price=7_820.0,
                         stop_price=7_790.0)
        b3.process_quote(inst.symbol, 7_800.0, bar_open=7_802.0, bar_high=7_803.0,
                         bar_low=7_799.0)
        ev3 = b3.process_quote(inst.symbol, 7_789.0, bar_open=7_798.0, bar_high=7_799.0,
                               bar_low=7_788.0)
        snap3 = b3.get_account_snapshot()
        results["scenarios"]["full_stop"] = {
            "passed": (ev3.get("action") == "FULL_STOP" and b3.is_flat(inst.symbol)
                       and snap3["equity"] < 2_000.0),
            "event": ev3, "equity": snap3["equity"],
            "loss": round(snap3["equity"] - 2_000.0, 2),
        }

        # --- 4. gap-through-stop fills WORSE than the stop, never at it ---------------
        b4 = FillSimBroker(state_dir=tmp / "s4", start_equity=2_000.0)
        b4.connect()
        b4.place_bracket(inst.symbol, "BUY", 1, entry_price=7_800.0, tp1_price=7_820.0,
                         stop_price=7_790.0)
        b4.process_quote(inst.symbol, 7_800.0, bar_open=7_802.0, bar_high=7_803.0,
                         bar_low=7_799.0)
        ev4 = b4.process_quote(inst.symbol, 7_770.0, bar_open=7_775.0, bar_high=7_776.0,
                               bar_low=7_769.0)
        fill_px = ev4.get("fill_price")
        results["scenarios"]["gap_through_stop"] = {
            # A gap must NOT be rewarded with the stop price: the bar OPENED at 7,775,
            # already through the 7,790 stop, so the honest fill is the open, not the
            # stop. Filling at the stop would fabricate $75 of P&L per contract that
            # no real exchange would have given us.
            "passed": (ev4.get("action") == "FULL_STOP" and fill_px is not None
                       and float(fill_px) == 7_775.0),
            "fill_price": fill_px, "stop_was": 7_790.0, "bar_open_was": 7_775.0,
        }

        # --- 5. forced flatten near the settlement stop -------------------------------
        b5 = FillSimBroker(state_dir=tmp / "s5", start_equity=2_000.0)
        b5.connect()
        b5.place_bracket(inst.symbol, "BUY", 1, entry_price=7_800.0, tp1_price=7_820.0,
                         stop_price=7_790.0)
        b5.process_quote(inst.symbol, 7_800.0, bar_open=7_802.0, bar_high=7_803.0,
                         bar_low=7_799.0)
        rails = FuturesRiskRails(rth_only=False)
        must = rails.must_flatten(dt.datetime(2026, 8, 12, 16, 55))
        closed = b5.close_position(inst.symbol, 1, "SELL", 7_805.0) if must.allow else False
        results["scenarios"]["forced_flatten"] = {
            "passed": bool(must.allow and closed and b5.is_flat(inst.symbol)),
            "rail": must.rail, "reason": must.reason,
        }

        # --- 6. no-stacking: a second bracket must be refused -------------------------
        b6 = FillSimBroker(state_dir=tmp / "s6", start_equity=2_000.0)
        b6.connect()
        b6.place_bracket(inst.symbol, "BUY", 1, entry_price=7_800.0, tp1_price=7_820.0,
                         stop_price=7_790.0)
        second = b6.place_bracket(inst.symbol, "BUY", 1, entry_price=7_795.0,
                                  tp1_price=7_815.0, stop_price=7_785.0)
        results["scenarios"]["no_stacking"] = {"passed": second == [], "second_ids": second}

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    results["all_passed"] = all(s.get("passed") for s in results["scenarios"].values())
    results["n_passed"] = sum(1 for s in results["scenarios"].values() if s.get("passed"))
    results["n_total"] = len(results["scenarios"])
    return results


# ── replay drill ──────────────────────────────────────────────────────────────

def run_replay(instrument: str = "MES", days: int = 5,
               rails: Optional[FuturesRiskRails] = None) -> dict:
    """Walk real RTH bars through the REAL tick, one bar at a time, no look-ahead."""
    from futures import futures_live_data as fld  # noqa: PLC0415

    inst = get_instrument(instrument)
    rails = rails or FuturesRiskRails()
    bars = fld.load_series(inst.symbol, "5m", mode="live")
    if bars.empty:
        return {"error": "no live bars cached -- run futures_live_data --append first"}

    rth = bars[(bars["timestamp_et"].dt.time >= dt.time(9, 30)) &
               (bars["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    session_days = sorted(rth["timestamp_et"].dt.date.unique())[-days:]
    if not session_days:
        return {"error": "no RTH sessions in the cached range"}

    tmp = Path(tempfile.mkdtemp(prefix="futreplay-"))
    broker = FillSimBroker(state_dir=tmp, start_equity=rails.start_equity)
    broker.connect()

    # Point the module's ledger at the throwaway dir so a drill never pollutes the
    # live decisions ledger or the live heartbeat file.
    saved = (core.STATE_DIR, core.LEDGER, core.LAST_TICK, core.LOOP_STATE, core.HEARTBEAT)
    core.STATE_DIR = tmp
    core.LEDGER, core.LAST_TICK = tmp / "decisions.jsonl", tmp / "last-tick.json"
    core.LOOP_STATE, core.HEARTBEAT = tmp / "loop-state.json", tmp / "heartbeat.json"

    # ...and the JOURNAL too. run_tick writes a trades.csv row on every closed round
    # trip, so without this a drill would silently file simulated drill trades into the
    # REAL trade ledger -- indistinguishable from live lane activity once written, and
    # the exact way a scorecard ends up quoting numbers nobody meant to produce.
    saved_j = (fj.JOURNAL_DIR, fj.TRADES_CSV, fj.MISTAKES_MD)
    fj.JOURNAL_DIR = tmp / "journal"
    fj.TRADES_CSV = fj.JOURNAL_DIR / "trades.csv"
    fj.MISTAKES_MD = fj.JOURNAL_DIR / "mistakes.md"

    out = {
        "instrument": inst.symbol, "days": [str(d) for d in session_days],
        "n_ticks": 0, "n_signals_seen": 0, "n_entries": 0,
        "actions": {}, "rejections": {}, "entries": [], "errors": [],
        "evidence_class": "SIMULATED fills, in-sample replay -- mechanism only, NOT edge",
    }
    try:
        for day in session_days:
            day_idx = rth.index[rth["timestamp_et"].dt.date == day].tolist()
            for i in day_idx:
                bar_ts = rth.loc[i, "timestamp_et"]
                now_et = bar_ts.tz_localize(None).to_pydatetime()
                # NO LOOK-AHEAD: only bars at or before this one.
                frame = bars[bars["timestamp_et"] <= bar_ts].reset_index(drop=True)
                rec = core.run_tick(
                    inst.symbol, broker=broker, rails=rails, now_et=now_et,
                    bars=frame, refresh=False, freshness_override="GREEN")
                out["n_ticks"] += 1
                out["actions"][rec["action"]] = out["actions"].get(rec["action"], 0) + 1
                out["n_signals_seen"] += int(rec.get("n_signals", 0) or 0)
                for r in rec.get("rejected", []) or []:
                    key = r.get("rail", "?")
                    out["rejections"][key] = out["rejections"].get(key, 0) + 1
                if rec.get("see_error"):
                    out["errors"].append(rec["see_error"])
                if rec["action"] == "ENTER":
                    out["n_entries"] += 1
                    out["entries"].append({"ts": rec["ts_et"], **rec["entry"]})
        snap = broker.get_account_snapshot()
        out["account"] = {
            "start_equity": snap.get("starting_equity"),
            "end_equity": snap.get("equity"),
            "realized_pnl_total": snap.get("realized_pnl_total"),
            "trade_count": snap.get("trade_count"),
        }
        out["would_be_events"] = _count_events(tmp / "would-be-trades.jsonl")
    finally:
        core.STATE_DIR, core.LEDGER, core.LAST_TICK, core.LOOP_STATE, core.HEARTBEAT = saved
        fj.JOURNAL_DIR, fj.TRADES_CSV, fj.MISTAKES_MD = saved_j
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def _count_events(path: Path) -> dict:
    counts: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ev = json.loads(line).get("event", "?")
            counts[ev] = counts.get(ev, 0) + 1
    except Exception:  # noqa: BLE001
        pass
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futures lifecycle drills")
    ap.add_argument("--scenarios", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--instrument", default="MES")
    ap.add_argument("--days", type=int, default=5)
    args = ap.parse_args(argv)

    rc = 0
    if args.scenarios:
        res = run_scenarios(args.instrument)
        print(json.dumps(res, indent=2, default=str))
        rc |= 0 if res["all_passed"] else 1
    if args.replay:
        res = run_replay(args.instrument, args.days)
        print(json.dumps(res, indent=2, default=str))
        rc |= 1 if res.get("error") else 0
    if not (args.scenarios or args.replay):
        ap.print_help()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
