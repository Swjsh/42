"""exit_grid_n1_20260731_746c.py -- WHAT ELSE COULD THIS EXIT HAVE BEEN.

n=1 DESCRIPTIVE AUTOPSY of ONE winning trade. This is an ANECDOTE, not evidence.
Nothing in this file ratifies, arms, or proposes an exit change. Read the
"HONEST FRAME" block in the emitted JSON before quoting any number from it.

THE POSITION (anchor facts, all fills-verified from automation/state/fills-ledger.jsonl):
    arm            risky-3 (FLEET-LOOSE-R, PA31WIU8X15Q), exit_profile ZONE-RIDE
    symbol         SPY260731C00746000  (SPY 0DTE 746 CALL, 2026-07-31)
    entry          BUY 5 @ $0.33  filled 12:19:03.936 ET
    setup          BULLISH_RECLAIM_RIDE_THE_RIBBON, bull score 11/11, blockers empty
    trigger_level  743.25   stop_mode=structure   (v15.3 chart-stop-primary)
    exits (actual) SELL 3 @ $0.65 12:34:04 ET (tp1 @ +100%)
                   SELL 2 @ $0.48 12:43:03 ET (runner_stop @ 0.55, chandelier trail)
    realized       +$126.00

EXIT SHAPE ACTUALLY IN FORCE (resolved the same way production resolves it:
fleet_executor._exit_shape_dict = strategies.RIBBON_RIDE.exit.to_dict() shallow-merged
under accounts.json arms[risky-3].params_patch.exit_patch):
    tp1_premium_pct 1.0 | tp1_qty_fraction 0.667 | profit_lock_mode trailing
    trail_pct 0.20 (ZONE-RIDE patch; registry ribbon_ride is 0.15) | arm_pct 0.05
    arm_scope post_tp1 | stop_mode structure | catastrophe -0.50 | runner_target +9900%

DATA -- 100% REAL OPRA, no synthetic:
    option   /v1beta1/options/bars 1Min for SPY260731C00746000 (real OPRA trade prints)
    SPY      /v2/stocks/SPY/bars 1Min + 5Min, feed=sip
    Cross-check that proves the option feed is real: SPY 15:59 close 746.82 -> 746C
    intrinsic $0.82; the 16:00 OPRA bar closes 1.23/vwap-consistent with that decay.

CONVENTIONS (inherited, not invented here):
  * entry+1 (strict >) exit eligibility -- markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md
  * point-sample best=worst=bar OPEN at each 1-min tick (exit_manager_walk's documented
    fidelity fix: a live tick reads ONE NBBO snapshot, not a 60s sweep)
  * market-style stages (time_stop / ribbon_flip / structure_stop / level_target) fill at
    that bar's CLOSE - $0.02 slippage; limit-style stages (tp1 / trail / premium stop)
    fill exactly at the triggered level
  * ENTRY-PREMIUM SPLIT, disclosed: live registered the ExitState at entry_premium=$0.34
    (the LIMIT price from the ENTER decision) while the real fill was $0.33. Every DECISION
    THRESHOLD below therefore uses 0.34 (live-faithful) and every DOLLAR uses 0.33 (money
    truth). This 1c registration gap is itself a finding, not an assumption.

EXECUTABILITY RULE: every variant in the main grid is a rule the engine could have
followed with information available at that tick. Anything requiring hindsight is
reported SEPARATELY as an unreachable ORACLE BOUND and never mixed into the grid.

Run (backtest venv):
    backtest/.venv/Scripts/python.exe backtest/tools/exit_grid_n1_20260731_746c.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

from lib.exit_manager_walk import walk_exit_manager, DEFAULT_EXIT_SLIPPAGE  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
import exit_manager as em  # noqa: E402
import strategies as strat_mod  # noqa: E402
import fleet_executor as fx  # noqa: E402

# ------------------------------------------------------------------ anchor facts
DATE_ET = "2026-07-31"
SYMBOL = "SPY260731C00746000"
ARM_ID = "risky-3"
ENTRY_TS_ET = dt.datetime(2026, 7, 31, 12, 19, 3, 936711)
ENTRY_FILL = 0.33          # real fill (fills-ledger) -> ALL dollars
ENTRY_REGISTERED = 0.34    # live ExitState entry_premium -> ALL thresholds
QTY = 5
SIDE = "C"
TRIGGER_LEVEL = 743.25
TIME_STOP_ET = dt.time(15, 40)   # automation/state/params.json time_stop_et
EOD_FLATTEN_ET = dt.time(15, 55)  # Gamma_EodFlatten backstop

ACTUAL_LEGS = [
    {"ts_et": "12:34:04", "qty": 3, "price": 0.65, "stage": "tp1"},
    {"ts_et": "12:43:03", "qty": 2, "price": 0.48, "stage": "trail"},
]

CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:/Users/jackw/AppData/Local/Temp/claude/C--Users-jackw-Desktop-42"
    r"/21375492-0e59-4fe4-99b0-ba94a60caa33/scratchpad")
OUT_JSON = REPO / "analysis" / "recommendations" / "exit-grid-n1-2026-07-31-746c.json"


def _et(t: str) -> dt.datetime:
    return (dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
            - dt.timedelta(hours=4)).replace(tzinfo=None)


def load_bars(fname: str) -> pd.DataFrame:
    raw = json.loads((CACHE / fname).read_text())
    return pd.DataFrame([{
        "timestamp_et": _et(b["t"]), "open": b["o"], "high": b["h"],
        "low": b["l"], "close": b["c"], "volume": b.get("v", 0), "n": b.get("n", 0),
    } for b in raw]).sort_values("timestamp_et").reset_index(drop=True)


def production_shape() -> dict:
    """The EXACT shape this position ran under -- resolved through production code."""
    accounts = json.loads((REPO / "automation" / "state" / "fleet" / "accounts.json")
                          .read_text(encoding="utf-8"))
    arm = [a for a in accounts["arms"] if a["id"] == ARM_ID][0]
    return fx._exit_shape_dict(strat_mod.RIBBON_RIDE, arm)


# ------------------------------------------------------------------ generic level walk
def walk_level_target(opt_df: pd.DataFrame, spy_1m: pd.DataFrame, spy_5m: pd.DataFrame,
                      target: float, mode: str, base_shape: dict,
                      ribbon_tick: pd.DataFrame, tp1_first: bool) -> dict:
    """Walk the position with a SPY-LEVEL take-profit layered on the production exit core.

    mode="touch"  : fire when the live 1-min bar's HIGH >= target (spot touch)
    mode="close5" : fire when the last CLOSED 5-min SPY bar's close >= target

    tp1_first=False -> the level target closes the WHOLE position (level replaces TP1).
    tp1_first=True  -> production TP1 still fires; the level closes the RUNNER.
    All other production exits (structure stop, catastrophe, time stop) stay armed and are
    evaluated by the real exit_manager core, so this is additive, never a re-implementation.
    """
    shape = dict(base_shape)
    if not tp1_first:
        shape["tp1_qty_fraction"] = 0.0
    state = em.ExitState.from_entry(
        symbol=SYMBOL, side=SIDE, entry_premium=ENTRY_REGISTERED, qty=QTY,
        exit_shape=shape, strategy="ribbon_ride", trigger_level=TRIGGER_LEVEL,
        structure_stop_enabled=True)
    spy_1m_idx = spy_1m.set_index("timestamp_et")
    open_qty, legs = QTY, []
    start = opt_df.index[opt_df["timestamp_et"] > ENTRY_TS_ET]
    if len(start) == 0:
        return {"legs": [], "note": "no bars after entry"}
    for idx in range(int(start[0]), len(opt_df)):
        bar = opt_df.iloc[idx]
        ts, best = bar["timestamp_et"], float(bar["open"])
        closed5 = _last_closed_5m(spy_5m, ts)
        # --- production core first (structure / catastrophe / time / tp1) -------------
        dec = em.plan_exit_actions(
            state, best_premium=best, worst_premium=best, open_qty=open_qty,
            now_et=ts.time(), ribbon_flip_back=False, time_stop_et=TIME_STOP_ET,
            last_closed_5m_close=closed5)
        state = dec.state
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            px = (best if a.stage in ("tp1",)
                  else max(0.01, float(bar["close"]) - DEFAULT_EXIT_SLIPPAGE))
            if a.stage == "tp1":
                px = ENTRY_REGISTERED * (1.0 + state.tp1_premium_pct)
            legs.append({"ts_et": ts.strftime("%H:%M:%S"), "qty": a.qty,
                         "price": round(px, 4), "stage": a.stage, "reason": a.reason})
            open_qty -= a.qty
        if dec.closes_position or open_qty <= 0:
            break
        # --- the LEVEL TAKE-PROFIT overlay -------------------------------------------
        hit = False
        if mode == "touch":
            row = spy_1m_idx.loc[ts] if ts in spy_1m_idx.index else None
            hit = row is not None and float(row["high"]) >= target
        elif mode == "close5":
            hit = closed5 is not None and float(closed5) >= target
        if hit:
            px = max(0.01, float(bar["close"]) - DEFAULT_EXIT_SLIPPAGE)  # market-style
            legs.append({"ts_et": ts.strftime("%H:%M:%S"), "qty": open_qty,
                         "price": round(px, 4), "stage": "level_target",
                         "reason": f"level_target {target} ({mode})"})
            open_qty = 0
            break
    if open_qty > 0:
        last = opt_df.iloc[-1]
        legs.append({"ts_et": last["timestamp_et"].strftime("%H:%M:%S"), "qty": open_qty,
                     "price": round(max(0.01, float(last["close"]) - DEFAULT_EXIT_SLIPPAGE), 4),
                     "stage": "force_close", "reason": "data_exhausted"})
    return {"legs": legs}


def _last_closed_5m(spy_5m: pd.DataFrame, as_of) -> float | None:
    closes_at = spy_5m["timestamp_et"] + pd.Timedelta(minutes=5)
    elig = spy_5m.loc[closes_at <= as_of]
    return None if elig.empty else float(elig.iloc[-1]["close"])


def pnl_of(legs: list[dict]) -> float:
    return round(sum((leg["price"] - ENTRY_FILL) * leg["qty"] * 100.0 for leg in legs), 2)


def run_shape(name: str, shape: dict, opt_df, spy_5m, ribbon_tick, *,
              time_stop=TIME_STOP_ET, ribbon_on=False) -> dict:
    r = walk_exit_manager(
        symbol=SYMBOL, side=SIDE, entry_time_et=ENTRY_TS_ET,
        entry_premium=ENTRY_REGISTERED, qty=QTY, exit_shape=shape,
        structure_stop_enabled=True, trigger_level=TRIGGER_LEVEL,
        strategy="ribbon_ride", time_stop_et=time_stop, opt_df=opt_df,
        ribbon_tick_df=(ribbon_tick if ribbon_on else None), five_min_spy_df=spy_5m)
    legs = [{"ts_et": l.ts_et.strftime("%H:%M:%S"), "qty": l.qty, "price": l.fill_price,
             "stage": l.stage, "reason": l.reason} for l in r.legs]
    return {"variant": name, "legs": legs, "pnl": pnl_of(legs),
            "exit_reason": r.exit_reason,
            "exit_ts": r.exit_time_et.strftime("%H:%M:%S") if r.exit_time_et else None}


def main() -> None:
    opt = load_bars("opt746_1min.json")
    spy1 = load_bars("spy_1min.json")
    spy5 = load_bars("spy_5min.json")
    rth = ((spy5["timestamp_et"].dt.time >= dt.time(9, 30))
           & (spy5["timestamp_et"].dt.time < dt.time(16, 0)))
    spy5_rth = spy5.loc[rth].reset_index(drop=True)
    # WARMUP FIX (found building this file): computing the ribbon on the RTH-only slice
    # burns the slow_ema(48) warmup INSIDE the session, so every bar before ~13:25 reads
    # "WARMUP" and no flip can ever be detected -- a pure reconstruction artifact that
    # would have silently made the ribbon-flip variant untestable. Seed the EMAs from the
    # full 04:00-onward frame, then slice to RTH (C6: a warmup frame is not an iteration
    # frame -- re-slice to the caller's own scope, L235).
    rib_full = compute_ribbon(spy5["close"])
    rib_lookup = spy5[["timestamp_et"]].copy()
    rib_lookup["stack"] = rib_full["stack"].values
    rib_lookup = rib_lookup.loc[rth].reset_index(drop=True)
    ribbon_tick = pd.merge_asof(
        opt[["timestamp_et"]].sort_values("timestamp_et"),
        rib_lookup.sort_values("timestamp_et"),
        on="timestamp_et", direction="backward")[["stack"]].reset_index(drop=True)

    base = production_shape()
    rows: list[dict] = []

    # ---- 0. actual live result (real fills) ------------------------------------------
    baseline_pnl = pnl_of(ACTUAL_LEGS)
    rows.append({"variant": "BASELINE_ACTUAL_LIVE", "legs": ACTUAL_LEGS,
                 "pnl": baseline_pnl, "exit_reason": "tp1 + chandelier trail",
                 "exit_ts": "12:43:03", "family": "actual"})

    # ---- 1. harness parity reproduction ----------------------------------------------
    rows.append({**run_shape("HARNESS_REPRO_PRODUCTION_SHAPE", base, opt, spy5_rth,
                             ribbon_tick), "family": "parity"})

    # ---- 2. J's level targets ---------------------------------------------------------
    # LOOK-AHEAD DISCIPLINE: the eligible-level list is read from the 12:00 key-levels
    # SNAPSHOT (automation/state/key-levels-history/2026-07-31/1200.json, as_of 11:58:37
    # ET) -- the file that was actually on disk when the 12:19 entry fired. Today's
    # post-session key-levels.json contains levels derived from price action that had not
    # happened yet at 12:19 (e.g. INTRADAY_RTH_HIGH 748.89) and using it would be a
    # textbook look-ahead leak (C6).
    snap = json.loads((REPO / "automation" / "state" / "key-levels-history" / DATE_ET
                       / "1200.json").read_text(encoding="utf-8"))
    spot_at_entry = 743.3
    eligible = sorted([lv for lv in snap["levels"] if lv["price"] > spot_at_entry],
                      key=lambda lv: lv["price"])
    level_cells = [(f"SNAP_{lv['price']}_{lv['label'][:22]}", lv["price"])
                   for lv in eligible[:6]]
    for lbl, tgt in level_cells:
        for mode in ("touch", "close5"):
            r = walk_level_target(opt, spy1, spy5_rth, tgt, mode, base, ribbon_tick, False)
            rows.append({"variant": f"LEVELTP_{lbl}_{mode}_LEVEL_ONLY", "legs": r["legs"],
                         "pnl": pnl_of(r["legs"]),
                         "exit_reason": r["legs"][-1]["reason"] if r["legs"] else "n/a",
                         "exit_ts": r["legs"][-1]["ts_et"] if r["legs"] else None,
                         "family": "level_target_from_snapshot"})

    for lbl, tgt in [("HOD_SO_FAR_746.30", 746.301), ("OPEN_0930_744.68", 744.68),
                     ("PDH_742.45", 742.45)]:
        for mode in ("touch", "close5"):
            for tp1_first, tag in ((False, "LEVEL_ONLY"), (True, "TP1_THEN_LEVEL")):
                r = walk_level_target(opt, spy1, spy5_rth, tgt, mode, base,
                                      ribbon_tick, tp1_first)
                rows.append({"variant": f"LEVELTP_{lbl}_{mode}_{tag}", "legs": r["legs"],
                             "pnl": pnl_of(r["legs"]),
                             "exit_reason": r["legs"][-1]["reason"] if r["legs"] else "n/a",
                             "exit_ts": r["legs"][-1]["ts_et"] if r["legs"] else None,
                             "family": "level_target"})

    # ---- 3. hold-everything variants ---------------------------------------------------
    no_tp1 = {**base, "tp1_qty_fraction": 0.0}
    rows.append({**run_shape("HOLD_ALL_TO_TIMESTOP_1540", no_tp1, opt, spy5_rth, ribbon_tick),
                 "family": "hold"})
    rows.append({**run_shape("HOLD_ALL_TO_EOD_FLATTEN_1555", no_tp1, opt, spy5_rth,
                             ribbon_tick, time_stop=EOD_FLATTEN_ET), "family": "hold"})
    rows.append({**run_shape("NO_TP1_ALL5_ON_CHANDELIER_scope_post_tp1",
                             {**no_tp1, "profit_lock_arm_scope": "post_tp1"},
                             opt, spy5_rth, ribbon_tick), "family": "hold"})
    rows.append({**run_shape("NO_TP1_ALL5_ON_CHANDELIER_scope_full",
                             {**no_tp1, "profit_lock_arm_scope": "full"},
                             opt, spy5_rth, ribbon_tick), "family": "hold"})
    rows.append({**run_shape("TP1_THEN_RUNNER_TO_EOD_NO_TRAIL",
                             {**base, "profit_lock_mode": "fixed"},
                             opt, spy5_rth, ribbon_tick, time_stop=EOD_FLATTEN_ET),
                 "family": "hold"})

    # ---- 4. trail sweep -----------------------------------------------------------------
    for t in (0.10, 0.125, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50):
        tag = f"TRAIL_{t:.3f}" + ("_LIVE" if abs(t - 0.20) < 1e-9 else "")
        rows.append({**run_shape(tag, {**base, "trail_pct": t}, opt, spy5_rth, ribbon_tick),
                     "family": "trail_sweep"})

    # ---- 5. TP1 level sweep -------------------------------------------------------------
    for t in (0.30, 0.50, 0.75, 1.00, 1.50):
        tag = f"TP1_PCT_{t:.2f}" + ("_LIVE" if abs(t - 1.0) < 1e-9 else "")
        rows.append({**run_shape(tag, {**base, "tp1_premium_pct": t}, opt, spy5_rth,
                                 ribbon_tick), "family": "tp1_sweep"})

    # ---- 6. ribbon flip -----------------------------------------------------------------
    rows.append({**run_shape("RIBBON_FLIP_EXIT_ARMED", base, opt, spy5_rth, ribbon_tick,
                             ribbon_on=True), "family": "ribbon"})
    rows.append({**run_shape("RIBBON_FLIP_ARMED_NO_TP1", no_tp1, opt, spy5_rth, ribbon_tick,
                             ribbon_on=True), "family": "ribbon"})

    harness_pnl = [r for r in rows if r["variant"] == "HARNESS_REPRO_PRODUCTION_SHAPE"][0]["pnl"]
    for r in rows:
        r["delta_vs_actual_live"] = round(r["pnl"] - baseline_pnl, 2)
        r["delta_vs_harness_baseline"] = round(r["pnl"] - harness_pnl, 2)
        # NO-OP DETECTION: a level-target cell whose level was never reached silently
        # degrades to the incumbent's time stop. Its P&L is then a HOLD-TO-TIMESTOP result
        # wearing a level-target label -- the single easiest way to fake a level-target win.
        if r["family"] in ("level_target", "level_target_from_snapshot"):
            r["level_actually_fired"] = any(l.get("stage") == "level_target"
                                            for l in r["legs"])
            if not r["level_actually_fired"]:
                r["_NO_OP_WARNING"] = ("level never reached -- this cell is really "
                                       f"{r['exit_reason']}, NOT a level-target result")
        # MODEL-ERROR BAND: the harness reproduces this position at +$21.80 (+17.3%) vs the
        # real fills, so any |delta| below that is inside its own optimism and means nothing.
        r["inside_model_error_band"] = abs(r["delta_vs_harness_baseline"]) < 21.80

    # ---- 6b. ribbon diagnostic: could the flip exit have fired AT ALL? -------------------
    rib_after = rib_lookup.loc[rib_lookup["timestamp_et"] > ENTRY_TS_ET]
    transitions, prev = [], None
    for _, x in rib_lookup.iterrows():
        if x["stack"] != prev:
            transitions.append({"ts_et": x["timestamp_et"].strftime("%H:%M"),
                                "stack": x["stack"]})
        prev = x["stack"]
    ribbon_diag = {
        "question": "J: 'did we sell it at ~13:45 when we closed in the ribbon?'",
        "answer": "NO. The 5m ribbon never printed a BEAR bar after entry, so the "
                  "ribbon_flip_back exit was structurally incapable of firing on this trade.",
        "rth_transitions": transitions,
        "bear_bars_after_entry": rib_after.loc[rib_after["stack"] == "BEAR",
                                               "timestamp_et"].dt.strftime("%H:%M").tolist(),
        "stack_at_entry_last_closed_5m": str(
            rib_lookup.loc[rib_lookup["timestamp_et"] <= ENTRY_TS_ET, "stack"].iloc[-1]),
    }

    # ---- 6c. LATE-SESSION FRAGILITY: how knife-edge is every 'hold longer' cell? ---------
    frag = []
    for _, b in opt.loc[(opt["timestamp_et"].dt.time >= dt.time(15, 30))
                        & (opt["timestamp_et"].dt.time <= dt.time(16, 0))].iterrows():
        px = max(0.01, float(b["close"]) - DEFAULT_EXIT_SLIPPAGE)
        frag.append({"exit_minute_et": b["timestamp_et"].strftime("%H:%M"),
                     "opt_close": float(b["close"]), "prints_in_minute": int(b["n"]),
                     "contracts_in_minute": int(b["volume"]),
                     "pnl_all5_market_exit": round((px - ENTRY_FILL) * 5 * 100, 2)})

    # ---- 7. ORACLE BOUND (unreachable, reported separately) ------------------------------
    after = opt.loc[opt["timestamp_et"] > ENTRY_TS_ET]
    peak_row = after.loc[after["high"].idxmax()]
    pre_ts = after.loc[after["timestamp_et"].dt.time <= TIME_STOP_ET]
    peak_pre = pre_ts.loc[pre_ts["high"].idxmax()]
    oracle = {
        "_LABEL": "UNREACHABLE ORACLE BOUND -- requires hindsight, NOT a variant",
        "peak_premium_full_session": float(peak_row["high"]),
        "peak_ts_et": peak_row["timestamp_et"].strftime("%H:%M"),
        "oracle_pnl_all5_at_peak": round((float(peak_row["high"]) - ENTRY_FILL) * 5 * 100, 2),
        "peak_premium_before_timestop_1540": float(peak_pre["high"]),
        "peak_ts_before_timestop": peak_pre["timestamp_et"].strftime("%H:%M"),
        "oracle_pnl_all5_before_timestop": round(
            (float(peak_pre["high"]) - ENTRY_FILL) * 5 * 100, 2),
        "baseline_capture_rate_vs_full_session_oracle": round(
            baseline_pnl / ((float(peak_row["high"]) - ENTRY_FILL) * 5 * 100), 4),
    }

    day = {
        "session_open_0930": float(spy1.loc[spy1["timestamp_et"]
                                            == dt.datetime(2026, 7, 31, 9, 30), "open"].iloc[0]),
        "session_high": float(spy1.loc[(spy1["timestamp_et"].dt.time >= dt.time(9, 30))
                                       & (spy1["timestamp_et"].dt.time < dt.time(16, 0)),
                                       "high"].max()),
        "session_low": float(spy1.loc[(spy1["timestamp_et"].dt.time >= dt.time(9, 30))
                                      & (spy1["timestamp_et"].dt.time < dt.time(16, 0)),
                                      "low"].min()),
        "session_close_1559": float(spy1.loc[(spy1["timestamp_et"].dt.time >= dt.time(9, 30))
                                             & (spy1["timestamp_et"].dt.time < dt.time(16, 0)),
                                             "close"].iloc[-1]),
        "hod_so_far_at_entry_1219": 746.301,
        "prior_day_high_0730_rth": 742.45,
        "spot_at_entry_approx": 743.3,
    }

    graveyard = {
        "tp1_sweep": "MATCHES GRAVEYARD: 'take-profit-earlier' x3 iterations. Every "
                     "TP1_PCT cell below 1.00 is a re-run of an already-NULLED family. "
                     "Cell E2 of exit-armscope-tp1-ab-2026-07-28 tested a uniform "
                     "tp1 1.0->0.5 and returned -$2,491 aggregate / -$5,616 runner.",
        "hold": "PARTIAL MATCH: the 'no floor at all / ride to EOD' shape is the inverse "
                "of the trailing-lock family, but the CATASTROPHE-ONLY runner has not "
                "been swept as its own cell. Note NO_TP1_ALL5_ON_CHANDELIER_scope_full "
                "IS the pre-TP1 trailing lock -- graveyard, 4 thresholds, clipped the "
                "runner cohort at every one (-$7,759 -> -$3,898).",
        "level_target": "NO DIRECT MATCH for a level-referenced TAKE-PROFIT. Adjacent "
                        "graveyard entries are 'exit-all-at-touch' and the 'zone-banded "
                        "CLOSE-cross detector' -- both were ENTRY/stop-side detectors, "
                        "not profit targets. This is the one genuinely untested family "
                        "in the grid, which is exactly why it gets a pre-registration "
                        "and not a ship.",
        "trail_sweep": "NOT graveyarded as such, but trail_pct is a live A/B axis already "
                       "(risky-3 runs 0.20 vs the registry 0.15) -- n=1 cannot move it.",
        "ribbon": "Ribbon-flip exit is SHIPPED production behavior (since G14), not a "
                  "proposal. C28 already documents it as a LAGGING exit.",
    }

    payload = {
        "_HONEST_FRAME": [
            "n=1. ONE trade, ONE day, a V-recovery uptrend into a 15:5x melt-up.",
            "This is an ANECDOTE. It is not evidence and it ratifies NOTHING.",
            "Any variant that beats baseline here may be the SAME variant already",
            "NULLED across hundreds of trades -- see graveyard_matches per family.",
            "The winning cells all win for ONE reason: SPY went up and kept going up",
            "after 12:19. On any of the many days it does not, the same cells are the",
            "ones that give back the whole trade. n=1 cannot distinguish those worlds.",
            "Real OPRA only. No synthetic premiums anywhere in this file.",
        ],
        "graveyard_matches": graveyard,
        "ribbon_flip_diagnostic": ribbon_diag,
        "late_session_fragility": {
            "_WHY": "Every 'hold longer' cell resolves inside a 20-minute window where the "
                    "746C ran 1.58 -> 2.83 -> 0.71. The exit MINUTE, not the exit RULE, "
                    "dominates the P&L there. Read this table before believing any "
                    "hold-to-EOD number.",
            "curve": frag,
        },
        "generated_et": dt.datetime.now().isoformat(timespec="seconds"),
        "position": {"symbol": SYMBOL, "arm": ARM_ID, "entry_ts_et": ENTRY_TS_ET.isoformat(),
                     "entry_fill": ENTRY_FILL, "entry_registered_in_exitstate": ENTRY_REGISTERED,
                     "qty": QTY, "trigger_level": TRIGGER_LEVEL, "exit_shape": base},
        "day_frame_ET_SIP": day,
        "level_snapshot_at_entry": {
            "_SOURCE": f"automation/state/key-levels-history/{DATE_ET}/1200.json",
            "as_of": snap.get("as_of"),
            "_FINDING": "The level J is describing as 'the high of day' was ALREADY IN THE "
                        "ENGINE'S OWN FILE at entry time as INTRADAY_RTH_HIGH_2026-07-31 = "
                        "746.30 (zone_width 0.3731). The engine had the number and no "
                        "mechanism to use a level as a take-profit target.",
            "_NAIVE_DETECTOR_WARNING": "A naive 'nearest eligible level above spot' rule "
                                       "picks 744.31, NOT 746.30. Which level qualifies as "
                                       "a TARGET is the entire hypothesis -- it must be "
                                       "pre-registered, never chosen after seeing this day.",
            "eligible_upside_levels": [
                {"price": lv["price"], "tier": lv.get("tier"), "label": lv.get("label"),
                 "zone_width": lv.get("zone_width"), "source": lv.get("source")}
                for lv in eligible],
        },
        "baseline_pnl": baseline_pnl,
        "harness_vs_live_parity": {
            "_WHY_IT_MATTERS": "Every delta in the grid is measured through a harness that "
                               "is demonstrably OPTIMISTIC vs the real fills on this exact "
                               "position. Deltas smaller than this gap are model error, "
                               "not findings.",
            "actual_live_pnl": baseline_pnl,
            "harness_repro_pnl": harness_pnl,
            "gap_dollars": round(harness_pnl - baseline_pnl, 2),
            "gap_pct_of_actual": round((harness_pnl - baseline_pnl) / baseline_pnl, 4),
            "mechanism_1_fill_model": "Harness fills limit-style EXACTLY at the trigger "
                                      "level (tp1 0.68, trail floor 0.544). Live places a "
                                      "market_sell and takes the bid (0.65, 0.48). Live was "
                                      "3c worse on TP1 and 6.4c worse on the runner.",
            "mechanism_2_tick_cadence": "This fleet arm decides every 3 MINUTES (12:19, "
                                        "12:22 ... 12:43), the harness every 1 minute. The "
                                        "12:39 dip to 0.52 that trips the harness's 0.544 "
                                        "floor happened in a minute the live arm never "
                                        "evaluated; live's next look (12:40) saw 0.58, "
                                        "above the floor, and it did not exit until 12:43.",
            "leg_attribution": {"tp1_3ct": 9.00, "runner_2ct": 12.80},
        },
        "grid": rows,
        "oracle_bound": oracle,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    w = max(len(r["variant"]) for r in rows) + 1
    print(f"{'VARIANT':<{w}} {'P&L':>8} {'vsLIVE':>8} {'vsHARN':>8}  EXIT")
    print("-" * (w + 50))
    for r in sorted(rows, key=lambda x: -x["pnl"]):
        print(f"{r['variant']:<{w}} {r['pnl']:>8.2f} {r['delta_vs_actual_live']:>+8.2f}"
              f" {r['delta_vs_harness_baseline']:>+8.2f}  {r['exit_ts']} "
              f"{r['exit_reason'][:44]}")
    print("\nRIBBON:", ribbon_diag["answer"])
    print("transitions:", ribbon_diag["rth_transitions"])
    print("\nLATE-SESSION FRAGILITY (all-5 market exit, by minute):")
    for f in frag:
        print(f"  {f['exit_minute_et']}  close={f['opt_close']:.2f}  "
              f"prints={f['prints_in_minute']:>3}  pnl={f['pnl_all5_market_exit']:>8.2f}")
    print("\nORACLE (unreachable):", json.dumps(oracle, indent=1))
    print("\nwrote", OUT_JSON)


if __name__ == "__main__":
    main()
