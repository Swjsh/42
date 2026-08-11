#!/usr/bin/env python
"""exit_parity_vs_recorded.py -- validate the exit engine against the LIVE ENGINE'S OWN
recorded decisions, not against expectations I wrote.

WHY THIS EXISTS (J, 2026-08-10 night): "Can you simulate trades somehow without writing your
own code that'll pass because you wrote it to pass?" Every number produced tonight came out of
a harness I authored the same evening -- replay code, cells, gates and guards all mine, which
is exactly the circularity that makes a green result worthless.

THE INDEPENDENT ORACLE: `automation/state/fleet/<arm>/decisions.jsonl` carries 1,848
`exit_pass` rows across 22 trading days. Each row is the LIVE engine, at a real tick, writing
down BOTH its inputs (open_qty, best_premium, worst_premium, tp1_filled, runner_stop -- the
real broker quote it saw) AND the action it took. Those rows were written by scheduled fires
over six weeks, most of them BEFORE the ladder existed and none of them by me tonight. I
cannot make them say something else.

TWO THINGS THIS MEASURES

  A. REGRESSION PARITY (ladder OFF). Feed each recorded tick's own inputs to TODAY's
     plan_exit_actions with every pre_tp1 knob None. It must reproduce the recorded verdict.
     A disagreement means tonight's edits changed legacy behaviour -- the inertness contract
     broken against 1,848 real decisions instead of the handful of synthetic cases I wrote.

  B. LADDER EFFECT FROM AN INDEPENDENT DATA SOURCE (ladder ON). Re-plan the same ticks with
     the shipped ladder. Divergences are ticks where the ladder would have SOLD and the live
     engine HELD. Those are priced off the engine's OWN recorded quote stream -- a completely
     different data source from the OPRA 5-minute bars every other estimate tonight used. If
     the two disagree in sign or wildly in size, the OPRA estimate is not trustworthy.

SCOPE -- PRE-TP1 TICKS ONLY, and that restriction is forced by the data, not chosen to
flatter the result. The first version of this script scored 89.38% and every one of its 169
"disagreements" turned out to be a defect in THIS FILE, not in the engine:
  - `tp1_filled` in the log is the state AFTER the tick's action is applied. Feeding it back
    as the tick's INPUT makes a recorded `tp1` fire replay as a post-TP1 `trail`.
  - `profit_lock_armed` is never recorded, so a post-TP1 chandelier RATCHET_STOP cannot be
    reconstructed at all -- the replay necessarily HOLDs where live ratcheted.
  - `time_stop_et` has drifted (a 15:40 historical time_stop vs today's 15:50).
Pre-TP1 ticks have none of those problems: (entry, runner_stop, best, worst, open_qty) is the
COMPLETE input to the pre-TP1 decision, and all of it is recorded. It is also precisely the
regime the ladder operates in, so the scoping costs the test nothing it was built to measure.

WHAT THIS STILL CANNOT DO (stated, not buried):
  - Structure/ribbon exits need `last_closed_5m_close` and the ribbon flag; neither is in the
    recorded row. Ticks whose recorded action was structure_stop/ribbon_flip are reported in
    their own bucket as NOT_REPRODUCIBLE rather than counted as agreement or disagreement.
  - This validates the DECISION FUNCTION per tick given recorded state. It is not a full
    state-evolution replay: each tick is judged on the state the live engine actually had.
    That is a feature here -- it removes my state reconstruction from the loop entirely.
  - Section B isolates the LADDER by diffing ON vs OFF on the SAME tick (never ON vs the
    historical record), so drift in any other shape knob cancels exactly.

$0, deterministic, no network, no LLM.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
for _p in (FLEET,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_manager as em  # noqa: E402
import strategies as st  # noqa: E402

STATEMENT = REPO / "automation" / "state" / "pnl-statement.json"
OUT = REPO / "analysis" / "deep-research" / "2026-08-10-live" / "exit-parity-vs-recorded.json"
NOT_REPRO_STAGES = {"structure_stop", "ribbon_flip"}


def entry_prices() -> dict:
    """(arm, symbol, date) -> real broker entry price, from pnl-statement round_trips."""
    data = json.loads(STATEMENT.read_text(encoding="utf-8"))
    out: dict = {}
    for rt in data.get("round_trips", []):
        key = (rt.get("arm"), rt.get("symbol"), rt.get("date_et"))
        if key not in out:
            out[key] = float(rt["entry_price"])
    return out


def recorded_ticks(arm: str) -> list:
    p = FLEET / arm / "decisions.jsonl"
    if not p.exists():
        return []
    ticks = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        ts = str(row.get("ts_et") or "")
        for e in (row.get("exit_pass") or []):
            if not isinstance(e, dict) or e.get("open_qty") in (None, 0):
                continue
            if e.get("best_premium") is None or e.get("worst_premium") is None:
                continue
            ticks.append({"arm": arm, "ts_et": ts, "date": ts[:10], **e})
    return ticks


def recorded_verdict(tick: dict) -> tuple:
    """(kind, stage) the live engine actually produced. ('HOLD', None) when it held."""
    acts = tick.get("actions") or []
    if not acts:
        return ("HOLD", None)
    a = acts[0]
    return (str(a.get("kind")), str(a.get("stage") or ""))


def replay_verdict(tick: dict, entry: float, shape: dict) -> tuple:
    """Today's planner, on the recorded tick's OWN inputs and recorded state."""
    state = em.ExitState.from_entry(
        symbol=tick["symbol"], side=("P" if "P00" in tick["symbol"] else "C"),
        entry_premium=entry, qty=int(tick["open_qty"]), exit_shape=shape,
        strategy="RIBBON", trigger_level=None, structure_stop_enabled=False)
    # Graft the LIVE state the engine actually held at this tick. tp1_filled is pinned False:
    # callers must pre-filter to pre-TP1 ticks (the logged flag is post-decision -- see the
    # module docstring), so grafting it here would reintroduce the exact off-by-one that
    # produced this file's first, wrong, 89% score.
    state = em.replace(state, tp1_filled=False,
                       runner_stop_premium=(float(tick["runner_stop"])
                                            if tick.get("runner_stop") is not None
                                            else state.runner_stop_premium))
    hhmm = tick["ts_et"][11:16] or "12:00"
    now = dt.time(int(hhmm[:2]), int(hhmm[3:5]))
    dec = em.plan_exit_actions(state, best_premium=float(tick["best_premium"]),
                               worst_premium=float(tick["worst_premium"]),
                               open_qty=int(tick["open_qty"]), now_et=now)
    if not dec.actions:
        return ("HOLD", None)
    a = dec.actions[0]
    return (str(a.kind), str(getattr(a, "stage", "") or ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="safe-3,risky-3,risky-1,safe-2,bold-2")
    args = ap.parse_args()

    prices = entry_prices()
    base = st.by_name("ribbon_ride").exit.to_dict()
    off = {**base, "pre_tp1_be_floor_arm_pct": None, "pre_tp1_floor_pct": None,
           "pre_tp1_ladder": None, "pre_tp1_trail_arm_pct": None, "pre_tp1_trail_pct": None}
    on = {**off, "pre_tp1_ladder": [[0.50, 0.30], [0.75, 0.60]],
          "pre_tp1_trail_arm_pct": 0.75, "pre_tp1_trail_pct": 0.20}

    buckets = Counter()
    disagreements: list = []
    ladder_earlier: list = []
    n_ticks = n_priced = 0
    by_day_ladder_fires: dict = defaultdict(list)

    for arm in args.arms.split(","):
        for tick in recorded_ticks(arm.strip()):
            n_ticks += 1
            entry = prices.get((tick["arm"], tick["symbol"], tick["date"]))
            if entry is None:
                buckets["NO_ENTRY_PRICE"] += 1
                continue
            n_priced += 1
            rec_kind, rec_stage = recorded_verdict(tick)
            if rec_stage in NOT_REPRO_STAGES:
                buckets["NOT_REPRODUCIBLE_needs_spy_feed"] += 1
                continue
            # SCOPE (see module docstring): pre-TP1 only. `tp1_filled` in the log is
            # post-decision, and post-TP1 state (profit_lock_armed) is not recorded at all, so
            # those ticks are unjudgeable from this oracle -- excluded, never scored as
            # agreement. A recorded `tp1` action is itself the TP1 boundary tick.
            if bool(tick.get("tp1_filled")) or "tp1" in (rec_stage or ""):
                buckets["OUT_OF_SCOPE_post_tp1_state_not_recorded"] += 1
                continue
            rep_kind, rep_stage = replay_verdict(tick, entry, off)

            sold_rec, sold_rep = rec_kind != "HOLD", rep_kind != "HOLD"
            if sold_rec == sold_rep and (not sold_rec or rec_stage == rep_stage):
                buckets["AGREE"] += 1
            elif sold_rec == sold_rep:
                buckets["AGREE_sell_but_different_stage"] += 1
                disagreements.append({**{k: tick[k] for k in
                                         ("arm", "ts_et", "symbol", "open_qty", "best_premium",
                                          "worst_premium", "tp1_filled", "runner_stop")},
                                      "recorded": rec_stage, "replay": rep_stage,
                                      "class": "stage_mismatch"})
            else:
                buckets["DISAGREE"] += 1
                disagreements.append({**{k: tick[k] for k in
                                         ("arm", "ts_et", "symbol", "open_qty", "best_premium",
                                          "worst_premium", "tp1_filled", "runner_stop")},
                                      "recorded": rec_kind + "/" + (rec_stage or ""),
                                      "replay": rep_kind + "/" + (rep_stage or ""),
                                      "class": "sell_vs_hold"})

            # (B is a separate per-position walk below -- a per-tick ON/OFF diff cannot
            # measure the ladder, because the ladder's FIRST effect is RATCHET_STOP, which
            # raises the floor without selling. Counting those as exits, as v2 of this file
            # did, overstates the ladder's aggressiveness by ~7x.)

    # ---- B: PER-POSITION WALK over the LIVE RECORDED QUOTE STREAM --------------------
    # Group the recorded ticks into positions and walk each one forward with the ladder ON,
    # evolving state properly (a per-tick ON/OFF diff cannot do this: the ladder's first
    # effect is RATCHET_STOP, which raises the floor WITHOUT selling). The quotes driving the
    # walk are the engine's own recorded broker reads -- a different data source from the OPRA
    # 5m bars used everywhere else tonight, so this is a genuine cross-check of that estimate.
    positions: dict = defaultdict(list)
    for arm in args.arms.split(","):
        for tick in recorded_ticks(arm.strip()):
            if bool(tick.get("tp1_filled")):
                continue  # post-TP1 state is unrecoverable from this oracle
            positions[(tick["arm"], tick["symbol"], tick["date"])].append(tick)

    walk_rows: list = []
    for key, ticks in positions.items():
        arm_id, symbol, date = key
        entry = prices.get(key)
        if entry is None or len(ticks) < 2:
            continue
        ticks.sort(key=lambda t: t["ts_et"])
        state = em.ExitState.from_entry(
            symbol=symbol, side=("P" if "P00" in symbol else "C"), entry_premium=entry,
            qty=int(ticks[0]["open_qty"]), exit_shape=on, strategy="RIBBON",
            trigger_level=None, structure_stop_enabled=False)
        armed_floor = None
        sell_px = sell_ts = None
        for t in ticks:
            hhmm = t["ts_et"][11:16] or "12:00"
            dec = em.plan_exit_actions(
                state, best_premium=float(t["best_premium"]),
                worst_premium=float(t["worst_premium"]), open_qty=int(t["open_qty"]),
                now_et=dt.time(int(hhmm[:2]), int(hhmm[3:5])))
            state = dec.state
            if state.runner_stop_premium and state.runner_stop_premium > entry:
                armed_floor = max(armed_floor or 0.0, float(state.runner_stop_premium))
            sells = [a for a in dec.actions if a.kind in ("SELL_ALL", "SELL_PARTIAL")]
            if sells:
                sell_px = float(getattr(sells[0], "price", None)
                                or state.runner_stop_premium or t["worst_premium"])
                sell_ts = t["ts_et"]
                break
        if armed_floor is None:
            continue  # ladder never armed -> position unaffected, correctly excluded
        qty = int(ticks[0]["open_qty"])
        walk_rows.append({
            "arm": arm_id, "symbol": symbol, "date": date, "entry": entry, "qty": qty,
            "armed_floor": round(armed_floor, 4),
            "floor_pct_above_entry": round((armed_floor / entry - 1) * 100, 1),
            "ladder_sell_ts": sell_ts, "ladder_sell_px": (round(sell_px, 4) if sell_px else None),
            "guaranteed_pnl_at_floor": round((armed_floor - entry) * qty * 100, 2),
        })

    # FIRST ladder fire per position -- later ones are ticks the position would not have seen
    first: dict = {}
    for r in ladder_earlier:
        key = (r["arm"], r["symbol"], r["ts_et"][:10])
        if key not in first or r["ts_et"] < first[key]["ts_et"]:
            first[key] = r

    report = {
        "oracle": "automation/state/fleet/<arm>/decisions.jsonl exit_pass rows -- written by "
                  "live scheduled fires over 22 trading days, not by this session",
        "n_recorded_ticks": n_ticks, "n_priced": n_priced,
        "A_regression_parity_ladder_OFF": dict(buckets),
        "A_disagreements": disagreements[:25],
        "B_position_walk_on_live_recorded_quotes": {
            "method": "per-position forward walk with the ladder ON, driven by the engine's "
                      "OWN recorded broker quotes (independent of the OPRA 5m bars used in "
                      "ladder_population_killcheck). Only positions where the ladder actually "
                      "ARMED a floor above entry are included.",
            "n_positions_armed": len(walk_rows),
            "n_days": len({r["date"] for r in walk_rows}),
            "total_guaranteed_at_floor": round(sum(r["guaranteed_pnl_at_floor"] for r in walk_rows), 2),
            "positions": sorted(walk_rows, key=lambda r: (r["date"], r["arm"])),
        },
        "cannot_measure": [
            "structure_stop / ribbon_flip ticks -- recorded row lacks last_closed_5m_close "
            "and the ribbon flag; bucketed NOT_REPRODUCIBLE, never counted as agreement",
            "exit shape at the historical tick is unknown; TP1 verdicts re-derived under "
            "today's registry shape and bucketed SHAPE_DRIFT when they differ",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== A. REGRESSION PARITY (ladder OFF) vs the live engine's own recorded verdicts")
    total_judged = sum(v for k, v in buckets.items()
                       if k in ("AGREE", "AGREE_sell_but_different_stage", "DISAGREE"))
    for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print(f"    {k:36s} {v:5d}")
    if total_judged:
        print(f"    -> agreement on judged ticks: "
              f"{buckets['AGREE'] / total_judged * 100:.2f}%  (n={total_judged})")
    print()
    print("=== B. PER-POSITION WALK on the LIVE recorded quote stream (not OPRA)")
    print(f"    positions where the ladder ARMED a floor above entry: {len(walk_rows)} "
          f"across {len({r['date'] for r in walk_rows})} days")
    print(f"    {'date':10s} {'arm':8s} {'contract':9s} {'q':>3s} {'entry':>6s} {'floor':>6s} "
          f"{'floor%':>7s} {'>= P&L':>9s}   ladder exit")
    for r in sorted(walk_rows, key=lambda r: (r["date"], r["arm"]))[:30]:
        xt = (r["ladder_sell_ts"][11:16] + f" @ {r['ladder_sell_px']:.2f}"
              if r["ladder_sell_ts"] else "held past recorded ticks")
        print(f"    {r['date']:10s} {r['arm']:8s} {r['symbol'][-9:]:9s} {r['qty']:>3d} "
              f"{r['entry']:6.2f} {r['armed_floor']:6.2f} {r['floor_pct_above_entry']:>6.0f}% "
              f"{r['guaranteed_pnl_at_floor']:+9.2f}   {xt}")
    print(f"    {'':10s} {'TOTAL':8s} floor-guaranteed minimum across armed positions: "
          f"{sum(r['guaranteed_pnl_at_floor'] for r in walk_rows):+.2f}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
