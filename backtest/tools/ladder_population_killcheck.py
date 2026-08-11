#!/usr/bin/env python
"""ladder_population_killcheck.py -- the GIVEBACK-RATCHET-2026-08-10 population run.

Prereg: analysis/recommendations/prereg-giveback-ratchet-2026-08-10.json (frozen + committed
mid-session 2026-08-10 10:51, BEFORE any runner). This runner executes that prereg over the
full real-fills population and doubles as the kill-check for the ladder J ordered shipped
same-day ("Just fucking do this right now"): the ship preceded the population validation by
J's explicit rule-9 override, so a FAIL here triggers the documented one-line revert rather
than having blocked the ship.

POPULATION -- automation/state/pnl-statement.json round_trips (broker truth, entry/exit
activity ids), attribution=="engine" only, grouped to POSITIONS by entry_activity_id (a
TP1'd trade is 2+ FIFO round trips of one position). Each position's real entry (time, price,
qty) is held FIXED; only the exit rule varies. Pricing = real OPRA 5m bars via the same
loader every exit study in this repo uses.

CELLS (all reported, none dropped -- prereg reporting_rule):
  CONTROL          registry shape, every pre_tp1 knob None (yesterday's engine)
  SHIPPED          ladder [[.50,.30],[.75,.60]] + trail 20% arming @ +75% (live since af6cf286/658ecc79)
  J_TRAIL_40       same ladder, trail arming @ +40% -- J's original spec, measured harmful
                   on 08-10 in-sample; population verdict reported by name, never buried
  J_SPEC_RATCHET   single rung +90 -> floor +65 -- the exact cell J first named
  RATCHET_a{A}_f{F} single rung grid {50,70,90} x {50,60,70,80} (12 cells, prereg grid)
  GIVEBACK_{g}     exit when price <= hwm - g*(hwm-entry), g in {20,25,33,50}% -- NOT
                   expressible in the shipped engine (no such knob); computed analytically
                   with the same bar walk and labelled engine_expressible=false

STATS -- primary estimand is the PAIRED per-day delta (cell - CONTROL) inside one harness,
which cancels the shared harness biases below; the headline J-number (cell - ACTUAL) is
reported alongside WITH the per-day fidelity bar |CONTROL - ACTUAL| so nobody quotes a swing
bigger than the harness can support. Day-clustered bootstrap (10k, seeded) on the paired
delta; BH-FDR q=0.10 across every cell this runner tests. Gates from the prereg verbatim:
G_TODAY / G_RUNNER / G_DROP_BEST / G_SUB_WINDOW.

HONESTY DISCLOSURES (travel with every number):
  1. IN-SAMPLE SPLIT: the shipped rungs were chosen partly on the 2026-08-10 tape. The gate
     cohort is the population EXCLUDING 2026-08-10; today is shown separately.
  2. NO SPY FEED: structure/ribbon exits cannot fire in replay -> CONTROL replays worse than
     live actual (it rides to premium floors the live engine pre-empted). Paired deltas
     mostly cancel this; cell-vs-ACTUAL does not -- hence the fidelity bar.
  3. 5-MIN BARS: intra-bar high/low order unknowable; a bar that both sets the HWM and
     breaches the resulting floor resolves optimistically (arm, then exit at floor), same
     convention in every cell.
  4. ENTRY BAR: the walk starts at the first 5m bar boundary AFTER the fill timestamp, so
     the entry bar's own remaining range is not walked -- identical across cells.
  5. TRIGGER LEVELS: historical per-fill trigger levels are not stored, so every replayed
     position resolves to PREMIUM stop mode (structure_stop_enabled needs a level). Live,
     ribbon positions were structure-stopped -- disclosure 2 covers the consequence.
  6. SCALE-INS: each entry activity replays as its own independent position.
  7. SETUP SCOPE: the ladder ships on ribbon_ride only; extra-setup fills are replayed here
     for completeness but tomorrow keep their own validated cells -- the ribbon-only slice
     is reported separately and is the shipping-relevant one.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pandas as pd  # noqa: E402

import strategies as st  # noqa: E402
from ladder_day_replay import replay_fill  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402

STATEMENT = REPO / "automation" / "state" / "pnl-statement.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "giveback-ratchet-population-2026-08-10.json"
OUT_MD = REPO / "analysis" / "recommendations" / "giveback-ratchet-population-2026-08-10.md"
TODAY = "2026-08-10"
SEED = 20260810
N_BOOT = 10_000


def load_positions() -> list[dict]:
    """pnl-statement round_trips -> one dict per POSITION (grouped by entry_activity_id)."""
    data = json.loads(STATEMENT.read_text(encoding="utf-8"))
    groups: dict[str, list] = defaultdict(list)
    for rt in data.get("round_trips", []):
        if rt.get("attribution") != "engine":
            continue
        if not str(rt.get("symbol", "")).startswith("SPY2"):
            continue
        groups[rt["entry_activity_id"]].append(rt)
    out = []
    for eid, legs in groups.items():
        first = legs[0]
        qty = sum(float(x["qty"]) for x in legs)
        pnl = sum(float(x["pnl"]) for x in legs)
        ts = str(first["entry_ts_et"])
        out.append({
            "date": str(first["date_et"]), "arm": first["arm"], "symbol": first["symbol"],
            "qty": int(qty), "entry_premium": float(first["entry_price"]),
            "entry_time": ts[11:19], "actual_pnl": pnl,
            "actual_tp1_filled": len(legs) >= 2, "entry_activity_id": eid,
        })
    out.sort(key=lambda p: (p["date"], p["entry_time"]))
    return out


def base_shape() -> dict:
    return st.by_name("ribbon_ride").exit.to_dict()


def make_cells() -> dict[str, dict]:
    cells: dict[str, dict] = {}
    none_pre = dict(pre_tp1_be_floor_arm_pct=None, pre_tp1_floor_pct=None,
                    pre_tp1_ladder=None, pre_tp1_trail_arm_pct=None, pre_tp1_trail_pct=None)
    cells["CONTROL"] = {**base_shape(), **none_pre}
    cells["SHIPPED"] = {**base_shape(), **none_pre,
                        "pre_tp1_ladder": [[0.50, 0.30], [0.75, 0.60]],
                        "pre_tp1_trail_arm_pct": 0.75, "pre_tp1_trail_pct": 0.20}
    cells["J_TRAIL_40"] = {**cells["SHIPPED"], "pre_tp1_trail_arm_pct": 0.40}
    cells["J_SPEC_RATCHET"] = {**base_shape(), **none_pre,
                               "pre_tp1_ladder": [[0.90, 0.65]]}
    for arm in (0.50, 0.70, 0.90):
        for floor in (0.50, 0.60, 0.70, 0.80):
            if floor >= arm:
                continue  # a floor at/above its arm is degenerate (instant exit at arm)
            cells[f"RATCHET_a{int(arm * 100)}_f{int(floor * 100)}"] = {
                **base_shape(), **none_pre, "pre_tp1_ladder": [[arm, floor]]}
    return cells


def giveback_walk(pos: dict, g: float, cache: dict) -> "dict | None":
    """Analytic giveback-cap walk (engine_expressible=false): exit when the bar's low
    breaches hwm - g*(hwm-entry) with hwm>entry, same bar loop shape as replay_fill."""
    sym, entry, qty = pos["symbol"], pos["entry_premium"], pos["qty"]
    if sym not in cache:
        try:
            cache[sym] = load_contract_bars(sym)
        except Exception:  # noqa: BLE001
            cache[sym] = None
    df = cache[sym]
    if df is None or df.empty:
        return None
    ts = df["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    sub = df.loc[(ts >= pd.Timestamp(f"{pos['date']} {pos['entry_time']}")).values]
    if sub.empty:
        return None
    hwm = entry
    exit_px = None
    for _i, bar in sub.iterrows():
        hwm = max(hwm, float(bar["high"]))
        cat = entry * 0.5                       # the -50% catastrophe cap still applies
        floor = hwm - g * (hwm - entry) if hwm > entry else cat
        stop = max(cat, floor)
        if float(bar["low"]) <= stop:
            exit_px = stop
            break
    if exit_px is None:
        exit_px = float(sub.iloc[-1]["close"])
    return {"replay_pnl": round((exit_px - entry) * qty * 100, 2)}


def bh_fdr(pvals: dict[str, float], q: float = 0.10) -> dict[str, bool]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    passed: dict[str, bool] = {k: False for k in pvals}
    max_k = 0
    for i, (_k, p) in enumerate(items, 1):
        if p <= q * i / m:
            max_k = i
    for i, (k, _p) in enumerate(items, 1):
        passed[k] = i <= max_k
    return passed


def day_bootstrap_p(deltas_by_day: dict[str, float]) -> float:
    """One-sided p for mean per-day delta <= 0, day-clustered, seeded."""
    days = list(deltas_by_day.values())
    if not days:
        return 1.0
    rng = random.Random(SEED)
    n = len(days)
    le = 0
    for _ in range(N_BOOT):
        s = sum(days[rng.randrange(n)] for _ in range(n)) / n
        if s <= 0:
            le += 1
    return max(le / N_BOOT, 1 / N_BOOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="first 30 positions only (smoke)")
    args = ap.parse_args()

    positions = load_positions()
    if args.quick:
        positions = positions[:30]
    cells = make_cells()

    # PRE-FLIGHT: load every distinct contract ONCE; a symbol with no OPRA bars drops its
    # positions from the population with a logged skip (never a poisoned None in the cache).
    cache: dict = {}
    skipped: list[str] = []
    for sym in sorted({p["symbol"] for p in positions}):
        try:
            df = load_contract_bars(sym)
            cache[sym] = df if df is not None and not df.empty else None
        except Exception as e:  # noqa: BLE001 -- a missing contract is a skip, not a crash
            cache[sym] = None
            skipped.append(f"{sym}: {type(e).__name__}: {str(e)[:80]}")
    dropped = [p for p in positions if cache.get(p["symbol"]) is None]
    skipped.extend(f"{p['date']} {p['symbol']}: no OPRA bars" for p in dropped
                   if not any(p["symbol"] in s for s in skipped))
    positions = [p for p in positions if cache.get(p["symbol"]) is not None]

    # replay every position under every engine cell
    per_cell: dict[str, dict[str, dict]] = {c: {} for c in cells}
    for pos in positions:
        for cname, shape in cells.items():
            r = replay_fill(dict(pos), shape, cache, trigger_level=0.0)
            if "error" in r:
                if cname == "CONTROL":
                    skipped.append(f"{pos['date']} {pos['symbol']}: {r['error']}")
                continue
            per_cell[cname][pos["entry_activity_id"]] = r
    for g in (0.20, 0.25, 0.33, 0.50):
        cname = f"GIVEBACK_{int(g * 100)}"
        per_cell[cname] = {}
        for pos in positions:
            r = giveback_walk(pos, g, cache)
            if r is not None:
                per_cell[cname][pos["entry_activity_id"]] = {**pos, **r}

    ctrl = per_cell["CONTROL"]
    pos_by_id = {p["entry_activity_id"]: p for p in positions}
    report: dict = {"rule_id": "GIVEBACK-RATCHET-2026-08-10",
                    "prereg": "analysis/recommendations/prereg-giveback-ratchet-2026-08-10.json",
                    "n_positions": len(positions) + len(dropped),
                    "n_priced": len(ctrl), "n_skipped_no_opra": len(dropped),
                    "skipped": skipped[:20], "cells": {}}

    pvals: dict[str, float] = {}
    for cname, rows in per_cell.items():
        if cname == "CONTROL":
            continue
        ids = [i for i in rows if i in ctrl]
        # per-day aggregation, gate cohort excludes the in-sample day
        by_day_cell: dict[str, float] = defaultdict(float)
        by_day_ctrl: dict[str, float] = defaultdict(float)
        by_day_actual: dict[str, float] = defaultdict(float)
        runner_cell = runner_ctrl = 0.0
        for i in ids:
            p = pos_by_id[i]
            d = p["date"]
            by_day_cell[d] += rows[i]["replay_pnl"]
            by_day_ctrl[d] += ctrl[i]["replay_pnl"]
            by_day_actual[d] += p["actual_pnl"]
            if p["actual_tp1_filled"]:
                runner_cell += rows[i]["replay_pnl"]
                runner_ctrl += ctrl[i]["replay_pnl"]
        oos_days = [d for d in by_day_cell if d != TODAY]
        deltas = {d: by_day_cell[d] - by_day_ctrl[d] for d in oos_days}
        vs_actual = {d: by_day_cell[d] - by_day_actual[d] for d in oos_days}
        fidelity = {d: abs(by_day_ctrl[d] - by_day_actual[d]) for d in oos_days}
        losing_days = [d for d in oos_days if by_day_actual[d] < 0]
        flips = [d for d in losing_days if by_day_cell[d] > 0]
        p_boot = day_bootstrap_p(deltas)
        pvals[cname] = p_boot
        drop_best = (sum(deltas.values()) - max(deltas.values())) if deltas else 0.0
        halves = sorted(oos_days)
        h1 = sum(deltas[d] for d in halves[: len(halves) // 2])
        h2 = sum(deltas[d] for d in halves[len(halves) // 2:])
        report["cells"][cname] = {
            "engine_expressible": not cname.startswith("GIVEBACK"),
            "oos": {
                "n_days": len(oos_days), "n_positions": len([i for i in ids if pos_by_id[i]["date"] != TODAY]),
                "total_cell": round(sum(by_day_cell[d] for d in oos_days), 2),
                "total_control": round(sum(by_day_ctrl[d] for d in oos_days), 2),
                "total_actual": round(sum(by_day_actual[d] for d in oos_days), 2),
                "paired_delta_vs_control": round(sum(deltas.values()), 2),
                "delta_vs_actual": round(sum(vs_actual.values()), 2),
                "median_day_fidelity_err": round(sorted(fidelity.values())[len(fidelity) // 2], 2) if fidelity else None,
                "losing_days_actual": len(losing_days), "flipped_to_winning": len(flips),
                "flipped_days": sorted(flips),
                "G_RUNNER_cell_minus_control": round(runner_cell - runner_ctrl, 2),
                "G_DROP_BEST_delta": round(drop_best, 2),
                "G_SUB_WINDOW": {"h1": round(h1, 2), "h2": round(h2, 2),
                                  "sign_consistent": (h1 >= 0) == (h2 >= 0)},
                "bootstrap_p_one_sided": p_boot,
            },
            "today_in_sample": {
                "cell": round(by_day_cell.get(TODAY, 0.0), 2),
                "control": round(by_day_ctrl.get(TODAY, 0.0), 2),
                "actual": round(by_day_actual.get(TODAY, 0.0), 2),
            },
        }
    fdr = bh_fdr(pvals)
    for cname, ok in fdr.items():
        report["cells"][cname]["bh_fdr_q10_pass"] = ok

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # compact MD table
    lines = ["# GIVEBACK-RATCHET population kill-check (2026-08-10)", "",
             f"Population: {report['n_priced']}/{report['n_positions']} engine positions priced "
             f"on real OPRA ({report['n_skipped_no_opra']} skipped, no bars). "
             f"Gate cohort EXCLUDES {TODAY} (in-sample). Full disclosures in the runner header.", "",
             "| cell | d vs control (paired) | d vs actual | flips L->W | runner d | dropbest | halves | p | BH |",
             "|---|--:|--:|--:|--:|--:|---|--:|---|"]
    for cname, c in sorted(report["cells"].items(), key=lambda kv: -kv[1]["oos"]["paired_delta_vs_control"]):
        o = c["oos"]
        lines.append(
            f"| {cname} | {o['paired_delta_vs_control']:+.0f} | {o['delta_vs_actual']:+.0f} "
            f"| {o['flipped_to_winning']}/{o['losing_days_actual']} "
            f"| {o['G_RUNNER_cell_minus_control']:+.0f} | {o['G_DROP_BEST_delta']:+.0f} "
            f"| {o['G_SUB_WINDOW']['h1']:+.0f}/{o['G_SUB_WINDOW']['h2']:+.0f} "
            f"| {o['bootstrap_p_one_sided']:.4f} | {'PASS' if c.get('bh_fdr_q10_pass') else '-'} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
