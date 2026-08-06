#!/usr/bin/env python
"""lever_correlation_stagger_2026_08_06.py -- LEVER 5, task 3(a): STAGGERED ENTRY TIMING.

"Do arms have to enter on the SAME tick? What if arms 2..k entered on the NEXT confirmation
instead of piling in within seconds of arm 1?"

This is the ONLY modelled cell in Lever 5. Everything else in the lane is arithmetic on
realized broker fills. This one has to price a counterfactual entry, so it is built to the
repo's hardest standard:

  * REAL Alpaca OPRA 1-minute option bars for the delayed entry price (no synthetic, no BS).
  * Exits re-walked through the REAL production decision core --
    backtest/lib/exit_manager_walk.walk_exit_manager -> exit_manager.plan_exit_actions.
    NOT simulator_real.simulate_trade_real (the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar).
  * The exit SHAPE for each position is resolved from that arm's OWN live decision row
    (setup_name -> strategies.REGISTRY -> ExitShape, then overlaid with that arm's
    accounts.json params_patch.exit_patch) -- the same two-step the live executor performs.
    No shape is guessed and none is fitted.
  * L251 PARITY GATE FIRST: every position is re-walked at D=0 (its ACTUAL entry price and
    time) and compared to broker truth. A wave whose D=0 parity fails is EXCLUDED from every
    delayed cell and reported as excluded. A counterfactual is worthless until the harness
    reproduces the known outcome.
  * Sequential, one position at a time. Nothing is recombined.

FRAME: every date in scope (2026-06-26 .. 2026-08-06) is EDT, so the "wall-v1" and "et-v2"
et_frame conventions coincide exactly and the DST misjoin class (L-DST / DST-FRAME-BLAST-
RADIUS-2026-08-02) has ZERO exposure here. Asserted at runtime, not assumed.

DISCLOSED FIDELITY GAPS (both one-directional and both stated in the artifact):
  1. ribbon_tick_df is None -> the ribbon_flip_back exit branch never fires in any cell,
     INCLUDING the D=0 parity baseline. It is therefore a CONSTANT across the comparison,
     not a bias between cells. (On the week's marquee trades the flip exit was verified
     unreachable anyway -- Wednesday's put needed a BULL flip to exit a put.)
  2. The delayed entry price is the real OPRA 1-min bar OPEN at (actual entry minute + D).
     That is a genuine market print and the same point-sample convention walk_exit_manager
     uses for its own tick reads -- it is NOT a claim that price was certainly fillable.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_correlation_stagger_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp            # noqa: E402
import tw8_level_context as lc                   # noqa: E402
import strategies as fleet_strategies            # noqa: E402
from exit_manager_walk import walk_exit_manager  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"
CORE_DEC = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-CORRELATION-STAGGER-2026-08-06.json"

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"
WAVE_WINDOW_S = 120
DELAYS_MIN = (1, 2, 3, 5)
TIME_STOP = dt.time(15, 50)
PARITY_ABS_TOL = 60.0      # $ -- a position must reproduce within this to enter a delayed cell
PARITY_REL_TOL = 0.25      # or within this fraction of |broker P&L|, whichever is looser
CORE_ARM_BY_ACCOUNT = {"safe": "safe-2", "bold": "bold-2"}
_TRIG_FALLBACK: dict = {}


# ------------------------------------------------------------------ population + context
def load_positions() -> list[dict]:
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("attribution") == "engine" and r.get("is_option") and not r.get("is_crypto"):
            fills.append(r)
    pos = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    ts_et_by = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    for p in pos:
        p["entry_ts_et"] = ts_et_by.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["qty"] = int(p["entry_qty"])
    pos.sort(key=lambda z: (z["entry_ts_et"], z["arm"]))
    return pos


def _parse(ts: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(ts)
    return d.replace(tzinfo=None) if d.tzinfo else d


def load_decision_context() -> list[dict]:
    """Every ENTER_* / PLACED decision row across the fleet + core ledgers, normalised to
    {arm, ts, symbol_or_none, side, setup, trigger_level}. Used ONLY to resolve which exit
    SHAPE the live executor registered for a fill -- never to price anything."""
    ctx = []
    for f in glob.glob(str(REPO / "automation" / "state" / "fleet" / "*" / "decisions.jsonl")):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not str(r.get("action", "")).startswith("ENTER"):
                continue
            pl = r.get("placement") or {}
            ctx.append({"arm": r.get("arm_id"), "ts": _parse(r["ts_et"]),
                        "symbol": pl.get("symbol"), "side": r.get("side"),
                        "setup": r.get("setup_name") or pl.get("strategy"),
                        "trigger_level": r.get("trigger_level") or pl.get("trigger_level")})
    if CORE_DEC.exists():
        for line in CORE_DEC.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            hits = []
            if str(r.get("verdict", "")).startswith("ENTER") or r.get("action") == "PLACED":
                hits.append((r.get("account"), r.get("setup"), r.get("side"),
                             r.get("trigger_level_exact")))
            for xe in (r.get("extra_exec") or []):
                if xe.get("action") == "PLACED":
                    hits.append((r.get("account"), xe.get("setup") or xe.get("strategy"),
                                 xe.get("side") or r.get("side"),
                                 xe.get("trigger_level") or r.get("trigger_level_exact")))
            for acct, setup, side, lvl in hits:
                arm = CORE_ARM_BY_ACCOUNT.get(acct)
                if not arm:
                    continue
                ctx.append({"arm": arm, "ts": _parse(r["ts_et"]), "symbol": None,
                            "side": side, "setup": setup, "trigger_level": lvl})
    return ctx


def build_trigger_fallback(ctx: list[dict]) -> dict:
    """(date, symbol) -> trigger_level, from ANY arm's decision row.

    WHY THIS EXISTS -- a harness defect found by the D=0 parity gate this session, not
    assumed: core-lane rows (safe-2 / bold-2) frequently carry trigger_level_exact = null,
    while the FLEET sibling row for the SAME core_tick_id and the SAME contract carries the
    real level (the arms trade one shared signal). Without this fallback, structure_stop
    silently resolves to the -20% PREMIUM fallback and the walk stops a winner out -- exactly
    the failure mode documented in EOD-2026-08-06-SILENT-ARMS ('harness_defect_found_and_
    corrected'). Measured cost of NOT doing this, on this population: safe-2's 2026-08-06
    770P replayed -$76.80 against a broker truth of +$375.00, a $452 error and a sign flip."""
    out: dict = {}
    for c in ctx:
        if c.get("symbol") and c.get("trigger_level") is not None:
            key = (c["ts"].date().isoformat(), c["symbol"])
            out.setdefault(key, float(c["trigger_level"]))
    return out


def resolve_shape(pos: dict, ctx: list[dict], patches: dict) -> tuple[dict, dict]:
    """(exit_shape, provenance). Nearest ENTER row for this arm within 300s BEFORE the fill,
    preferring an exact symbol match. setup_name -> strategies.REGISTRY -> ExitShape, then
    the arm's accounts.json exit_patch overlaid -- the live two-step, in order."""
    t = _parse(pos["entry_ts_et"])
    cands = [c for c in ctx if c["arm"] == pos["arm"]
             and -5 <= (t - c["ts"]).total_seconds() <= 300]
    exact = [c for c in cands if c["symbol"] == pos["symbol"]]
    pool = exact or cands
    best = min(pool, key=lambda c: abs((t - c["ts"]).total_seconds())) if pool else None
    setup = (best or {}).get("setup")
    strat = None
    if setup:
        for s in fleet_strategies.REGISTRY:
            if setup in s.entry_setups or setup == s.name:
                strat = s
                break
    if strat is None:
        strat = fleet_strategies.RIBBON_RIDE          # registry default, disclosed
        prov_src = "DEFAULT_RIBBON_RIDE (no decision row matched)" if not setup \
            else f"DEFAULT_RIBBON_RIDE (setup {setup!r} not in REGISTRY)"
    else:
        prov_src = f"decision row setup={setup!r} -> strategies.{strat.name}"
    shape = dict(strat.exit.to_dict())
    patch = patches.get(pos["arm"], {})
    shape.update(patch)
    lvl = (best or {}).get("trigger_level")
    lvl_src = "own decision row"
    if lvl is None and pos["arm"] in CORE_ARM_BY_ACCOUNT.values():
        # SCOPED TO THE KNOWN DEFECT ONLY. The core ledger's trigger_level_exact is often
        # null while the fleet sibling row for the same contract carries the real level.
        # A FLEET arm with a null level is NOT the same thing -- there it means the live
        # entry genuinely registered without a structure level, and back-filling one would
        # be inventing a stop the engine never had. Applying this fallback fleet-wide was
        # tried this session and MEASURABLY made parity worse (it structure-stopped
        # risky-1's 2026-08-04 763C at 763.10 for -$5 against a broker truth of +$640).
        lvl = _TRIG_FALLBACK.get((pos["date_et"], pos["symbol"]))
        lvl_src = "CORE-arm gap filled from sibling row" if lvl is not None else "NONE"
    return shape, {"setup": setup, "strategy": strat.name, "source": prov_src,
                   "arm_exit_patch": patch,
                   "trigger_level": lvl, "trigger_level_source": lvl_src,
                   "matched_symbol": (best or {}).get("symbol")}


def load_patches() -> dict:
    d = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    return {a["id"]: ((a.get("params_patch") or {}).get("exit_patch") or {})
            for a in d["arms"]}


# ------------------------------------------------------------------ bar plumbing
_BARS: dict = {}


def opt_bars(symbol: str, date_et: str) -> pd.DataFrame | None:
    key = (symbol, date_et)
    if key in _BARS:
        return _BARS[key]
    raw = esp.fetch_option_bars(symbol, date_et)
    if not raw:
        _BARS[key] = None
        return None
    # every date in scope is EDT -- asserted, not assumed (see module docstring)
    assert dt.date(2026, 3, 9) < dt.date.fromisoformat(date_et) < dt.date(2026, 11, 1), \
        f"{date_et} is outside the asserted EDT window; the -4h conversion below is unsafe"
    rows = []
    for b in raw:
        ts = dt.datetime.strptime(b["t"], "%Y-%m-%dT%H:%M:%SZ") - dt.timedelta(hours=4)
        rows.append({"timestamp_et": ts, "open": float(b["o"]), "high": float(b["h"]),
                     "low": float(b["l"]), "close": float(b["c"])})
    df = pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)
    _BARS[key] = df
    return df


def bar_open_at_or_after(df: pd.DataFrame, ts: dt.datetime):
    sub = df[df["timestamp_et"] >= ts]
    if sub.empty:
        return None, None
    return float(sub.iloc[0]["open"]), sub.iloc[0]["timestamp_et"]


# ------------------------------------------------------------------ the walk
def one_walk(pos, shape, prov, entry_px, entry_ts, spy5) -> dict | None:
    df = opt_bars(pos["symbol"], pos["date_et"])
    if df is None:
        return None
    side = pos["symbol"][9]
    lvl = prov.get("trigger_level")
    res = walk_exit_manager(
        symbol=pos["symbol"], side=side, entry_time_et=entry_ts,
        entry_premium=float(entry_px), qty=int(pos["qty"]), exit_shape=shape,
        structure_stop_enabled=bool(lvl is not None),
        trigger_level=float(lvl) if lvl is not None else None,
        strategy=prov["strategy"], time_stop_et=TIME_STOP,
        opt_df=df, ribbon_tick_df=None,
        five_min_spy_df=spy5[spy5["date"] == dt.date.fromisoformat(pos["date_et"])],
        opt_df_resolution="1min", frame="wall-v1")
    return {"pnl": round(float(res.dollar_pnl), 2), "exit_reason": res.exit_reason}


def main() -> int:
    positions = load_positions()
    ctx = load_decision_context()
    patches = load_patches()
    _TRIG_FALLBACK.update(build_trigger_fallback(ctx))
    dmin = min(p["date_et"] for p in positions)
    dmax = max(p["date_et"] for p in positions)
    spy5 = lc.load_spy_full(dt.date.fromisoformat(dmin) - dt.timedelta(days=5),
                            dt.date.fromisoformat(dmax))

    # ---- waves: same date, same contract, >=2 distinct arms, entries within WAVE_WINDOW_S
    clusters = defaultdict(list)
    for p in positions:
        clusters[(p["date_et"], p["symbol"])].append(p)
    waves = []
    for (d, sym), plist in clusters.items():
        plist = sorted(plist, key=lambda z: z["entry_ts_et"])
        cur = [plist[0]]
        for p in plist[1:]:
            if (_parse(p["entry_ts_et"]) - _parse(cur[0]["entry_ts_et"])).total_seconds() \
                    <= WAVE_WINDOW_S:
                cur.append(p)
            else:
                waves.append(cur); cur = [p]
        waves.append(cur)
    waves = [w for w in waves if len({p["arm"] for p in w}) > 1]

    # ---- L251 PARITY GATE at D=0
    parity, prepared = [], []
    for w in waves:
        legs = []
        for p in w:
            shape, prov = resolve_shape(p, ctx, patches)
            r = one_walk(p, shape, prov, p["entry_price"], _parse(p["entry_ts_et"]), spy5)
            if r is None:
                legs.append(None); continue
            err = r["pnl"] - p["pnl"]
            ok = abs(err) <= max(PARITY_ABS_TOL, PARITY_REL_TOL * abs(p["pnl"]))
            parity.append({"date": p["date_et"], "symbol": p["symbol"], "arm": p["arm"],
                           "qty": p["qty"], "entry_px": p["entry_price"],
                           "broker_pnl": p["pnl"], "replay_pnl": r["pnl"],
                           "abs_error": round(abs(err), 2), "pass": bool(ok),
                           "exit_reason": r["exit_reason"], "shape_source": prov["source"],
                           "trigger_level": prov.get("trigger_level")})
            legs.append({"pos": p, "shape": shape, "prov": prov, "d0": r, "parity_ok": ok})
        prepared.append(legs)

    n_par = len(parity)
    n_ok = sum(1 for x in parity if x["pass"])
    errs = sorted(x["abs_error"] for x in parity)
    parity_summary = {
        "n_legs": n_par, "n_pass": n_ok,
        "pass_rate": round(n_ok / n_par, 4) if n_par else None,
        "median_abs_error_usd": round(stats.median(errs), 2) if errs else None,
        "mean_abs_error_usd": round(stats.mean(errs), 2) if errs else None,
        "total_broker_pnl": round(sum(x["broker_pnl"] for x in parity), 2),
        "total_replay_pnl": round(sum(x["replay_pnl"] for x in parity), 2),
        "tolerance": f"abs<=${PARITY_ABS_TOL} OR rel<={PARITY_REL_TOL:.0%} of |broker P&L|",
        "_gate": "a WAVE is used in the delayed cells only if EVERY one of its legs passes"}

    # ---- delayed cells.
    #  MODE "stagger"  : leg 0 unchanged, legs 1..k delayed  <- the task's 3(a) proposal
    #  MODE "all"      : EVERY leg delayed                   <- PLACEBO
    #  MODE "leg0_only": ONLY leg 0 delayed, 1..k unchanged  <- ANTI-PLACEBO
    #
    #  The placebos are the whole point. If delaying the FIRST arm (which cannot possibly be
    #  a de-concentration effect) produces a similar dollar swing, then any "benefit" in the
    #  stagger cell is NOT about staggering -- it is about re-rolling the entry price into an
    #  unbounded runner (runner_target_pct = 99.0), which is the same structural artifact the
    #  hold_to_time counterfactual is already graveyarded for.
    cells = {}
    for D in DELAYS_MIN:
      for mode in ("stagger", "all", "leg0_only"):
        rows, skipped = [], 0
        for legs in prepared:
            if any(l is None or not l["parity_ok"] for l in legs):
                skipped += 1
                continue
            for i, l in enumerate(legs):
                p = l["pos"]
                delay_this = (mode == "all") or (mode == "stagger" and i > 0) \
                    or (mode == "leg0_only" and i == 0)
                if not delay_this:
                    rows.append({"date": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                                 "leg": i, "base_pnl": l["d0"]["pnl"],
                                 "staggered_pnl": l["d0"]["pnl"], "delta": 0.0,
                                 "entry_px": p["entry_price"], "new_entry_px": p["entry_price"]})
                    continue
                df = opt_bars(p["symbol"], p["date_et"])
                t_new = _parse(p["entry_ts_et"]).replace(second=0, microsecond=0) \
                    + dt.timedelta(minutes=D)
                px, ts = bar_open_at_or_after(df, t_new) if df is not None else (None, None)
                if px is None:
                    rows.append({"date": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                                 "leg": i, "base_pnl": l["d0"]["pnl"], "staggered_pnl": 0.0,
                                 "delta": round(-l["d0"]["pnl"], 2),
                                 "entry_px": p["entry_price"], "new_entry_px": None,
                                 "note": "no bar at delayed instant -- entry forgone"})
                    continue
                r = one_walk(p, l["shape"], l["prov"], px, ts, spy5)
                sp = r["pnl"] if r else 0.0
                rows.append({"date": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                             "leg": i, "base_pnl": l["d0"]["pnl"], "staggered_pnl": sp,
                             "delta": round(sp - l["d0"]["pnl"], 2),
                             "entry_px": p["entry_price"], "new_entry_px": round(px, 4),
                             "exit_reason": (r or {}).get("exit_reason")})
        by_day = defaultdict(float)
        for r in rows:
            by_day[r["date"]] += r["delta"]
        cheaper = [r for r in rows if r.get("new_entry_px") is not None
                   and r["new_entry_px"] < r["entry_px"] and r["delta"] != 0]
        dearer = [r for r in rows if r.get("new_entry_px") is not None
                  and r["new_entry_px"] > r["entry_px"] and r["delta"] != 0]
        top = sorted((r for r in rows if r["delta"] != 0),
                     key=lambda r: -abs(r["delta"]))[:3]
        tot = sum(r["delta"] for r in rows)
        cells[f"{mode}_{D}min"] = {
            "mode": mode,
            "_mode_meaning": {"stagger": "TASK 3(a): leg 0 keeps its real entry, legs 1..k "
                                         "delayed D minutes",
                              "all": "PLACEBO: every leg delayed D minutes -- no "
                                     "de-concentration whatsoever",
                              "leg0_only": "ANTI-PLACEBO: only the FIRST arm is delayed; the "
                                           "pile-on is left fully intact"}[mode],
            "delay_minutes": D, "n_waves_used": len(prepared) - skipped,
            "n_waves_skipped_parity": skipped, "n_legs": len(rows),
            "n_legs_delayed": sum(1 for r in rows if r["leg"] > 0),
            "total_delta": round(sum(r["delta"] for r in rows), 2),
            "tuesday_delta_2026_08_04": round(by_day.get(TUE, 0.0), 2),
            "wednesday_delta_2026_08_05": round(by_day.get(WED, 0.0), 2),
            "thursday_delta_2026_08_06": round(by_day.get(THU, 0.0), 2),
            "TUESDAY_NO_HARM_GATE": "PASS" if by_day.get(TUE, 0.0) >= -0.005 else "FAIL",
            "n_days_harmed": sum(1 for v in by_day.values() if v < -0.005),
            "n_days_helped": sum(1 for v in by_day.values() if v > 0.005),
            "day_deltas": {k: round(v, 2) for k, v in sorted(by_day.items())
                           if abs(v) > 0.005},
            "week_legs": [r for r in rows if r["date"] in (TUE, WED, THU) and r["delta"] != 0],
            "_artifact_hunt": {
                "delta_from_legs_that_got_a_CHEAPER_entry": round(
                    sum(r["delta"] for r in cheaper), 2),
                "n_cheaper": len(cheaper),
                "delta_from_legs_that_got_a_DEARER_entry": round(
                    sum(r["delta"] for r in dearer), 2),
                "n_dearer": len(dearer),
                "top3_legs_share_of_total_delta": round(
                    sum(r["delta"] for r in top) / tot, 4) if tot else None,
                "top3_legs": top,
                "tuesday_share_of_total_delta": round(
                    by_day.get(TUE, 0.0) / tot, 4) if tot else None}}

    out = {
        "_lane": "LEVER 5, task 3(a) -- staggered ENTRY timing across arms",
        "_generated_by": "backtest/tools/lever_correlation_stagger_2026_08_06.py",
        "_exit_engine": "backtest/lib/exit_manager_walk.walk_exit_manager -> "
                        "automation/state/fleet/exit_manager.plan_exit_actions (PRODUCTION)",
        "_entry_price_source": "REAL Alpaca OPRA 1-min bar OPEN at (entry minute + D)",
        "_frame": "wall-v1; every date in scope is EDT so wall-v1 == et-v2 (asserted at "
                  "runtime in opt_bars())",
        "_disclosed_fidelity_gaps": [
            "ribbon_tick_df=None -> ribbon_flip_back never fires, in the D=0 baseline AND "
            "every delayed cell. Constant across the comparison, not a between-cell bias.",
            "Delayed entry price is a real OPRA 1-min bar OPEN -- a genuine print and the "
            "same point-sample convention walk_exit_manager uses, NOT a fillability claim.",
            "The delayed arm is assumed to still WANT the trade D minutes later. Live, the "
            "signal might have decayed -- that would make the cell MORE conservative, not "
            "less, on losing waves and LESS favourable on winning ones."],
        "n_multi_arm_waves": len(waves),
        "parity_gate_D0": parity_summary,
        "parity_detail": parity,
        "cells": cells,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"waves={len(waves)}  parity {n_ok}/{n_par} "
          f"(median abs err ${parity_summary['median_abs_error_usd']})")
    for k, v in sorted(cells.items()):
        print(f"  {k:20s} total {v['total_delta']:+9.2f}  TUE {v['tuesday_delta_2026_08_04']:+9.2f}"
              f"  WED {v['wednesday_delta_2026_08_05']:+9.2f}"
              f"  THU {v['thursday_delta_2026_08_06']:+9.2f}  gate={v['TUESDAY_NO_HARM_GATE']}"
              f"  waves={v['n_waves_used']}/{v['n_waves_used']+v['n_waves_skipped_parity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
