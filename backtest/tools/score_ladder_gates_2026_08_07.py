"""score_ladder_gates_2026_08_07.py -- frozen-gate evaluation + canonical battery for
SCORE-LADDER-V2 (prereg c2ec28f3). Consumes SCORE-LADDER-REPLAY-2026-08-07.json.

Battery per prereg _battery_cells: G1 aggregate / G3 ex-best-trade / G4 runner cohort /
sub-window thirds / drop-best-day / archetype slices (day-inventory day_type, trailing
days classified with the inventory's own frozen rule) + bootstrap mean>0 per added-cohort
cell, Benjamini-Hochberg q=0.10 across the population cell family. ALL cells reported.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
IN_JSON = ROOT / "analysis" / "deep-research" / "SCORE-LADDER-REPLAY-2026-08-07.json"
INV_JSON = ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
NEW_SPY = REPO / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
OUT_JSON = ROOT / "analysis" / "deep-research" / "SCORE-LADDER-GATES-2026-08-07.json"

WEEK = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
SHIP = {"risky-3": "7", "risky-1": "8"}


def bootstrap_p(values, n_boot=10000, seed=7):
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    hits = sum(1 for _ in range(n_boot)
               if sum(values[rng.randrange(n)] for _ in range(n)) <= 0)
    return round(hits / n_boot, 5)


def bh(pvals: dict, q=0.10) -> dict:
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda kv: kv[1])
    m = len(items)
    max_i = 0
    for i, (k, p) in enumerate(items, 1):
        if p <= q * i / m:
            max_i = i
    return {k: (i <= max_i) for i, (k, p) in enumerate(items, 1)}


def day_types() -> dict[str, str]:
    inv = json.loads(INV_JSON.read_text(encoding="utf-8"))
    out = {d["date"]: d["day_type"] for d in inv["days"]}
    # trailing days (post-inventory) classified with the inventory's OWN frozen rule:
    # atr20 = mean of prior <=20 covered days' RTH ranges; trend: ratio>=1.0 AND body>=0.5;
    # chop: ratio<0.75; range: otherwise.
    df = pd.read_csv(NEW_SPY)
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    df["t"] = df["ts"].dt.time
    rth = df[(df["t"] >= dt.time(9, 30)) & (df["t"] < dt.time(16, 0))].copy()
    rth["date"] = rth["ts"].dt.date.astype(str)
    g = rth.groupby("date")
    day = pd.DataFrame({
        "high": g["high"].max(), "low": g["low"].min(),
        "open": g["open"].first(), "close": g["close"].last(),
    })
    day["range"] = day["high"] - day["low"]
    ranges = list(day["range"])
    dates = list(day.index)
    for i, d in enumerate(dates):
        if d in out:
            continue
        prior = ranges[max(0, i - 20):i]
        if len(prior) < 5:
            out[d] = "unclassified"
            continue
        atr20 = sum(prior) / len(prior)
        ratio = day["range"].iloc[i] / atr20 if atr20 else None
        rng_i = day["range"].iloc[i]
        body = abs(day["close"].iloc[i] - day["open"].iloc[i]) / rng_i if rng_i else 0.0
        if ratio is None:
            out[d] = "unclassified"
        elif ratio >= 1.0 and body >= 0.5:
            out[d] = "trend"
        elif ratio < 0.75:
            out[d] = "chop"
        else:
            out[d] = "range"
    return out


def per_day(trades):
    if not trades:
        return pd.Series(dtype=float)
    df = pd.DataFrame(trades)
    return df.groupby("date")["dollar_pnl"].sum()


def main() -> int:
    j = json.loads(IN_JSON.read_text(encoding="utf-8"))
    lanes = j["lanes"]
    dtypes = day_types()
    binary = lanes["binary"]
    b_day = per_day(binary["trades"])
    b_total = float(b_day.sum())
    b_worst = float(b_day.min()) if len(b_day) else 0.0
    b_best_day = float(b_day.max()) if len(b_day) else 0.0

    out = {"prereg": j["prereg"], "generated_at": dt.datetime.now().isoformat(),
           "binary": {"total": round(b_total, 2), "worst_day": round(b_worst, 2),
                       "week": {d: round(float(b_day.get(d, 0.0)), 2) for d in WEEK}},
           "rungs": {}, "bootstrap_cells": {}, "bh_q10": {}}

    pcells = {}
    for rung in ("6", "7", "8", "9"):
        L = lanes[rung]
        l_day = per_day(L["trades"])
        l_total = float(l_day.sum())
        extras = [t for t in L["trades"] if t["kind"] == "extra"]
        ex_bull = [t["dollar_pnl"] for t in extras if t["side"] == "C"]
        ex_bear = [t["dollar_pnl"] for t in extras if t["side"] == "P"]
        ex_all = [t["dollar_pnl"] for t in extras]
        # displaced binary trades (in baseline, not in lane)
        lane_keys = {(t["entry_time_et"], t["symbol"]) for t in L["trades"] if t["kind"] == "binary"}
        displaced = [t for t in binary["trades"]
                     if (t["entry_time_et"], t["symbol"]) not in lane_keys]
        disp_pnl = round(sum(t["dollar_pnl"] for t in displaced), 2)

        # gates
        week_lane = {d: round(float(l_day.get(d, 0.0)), 2) for d in WEEK}
        week_bin = {d: round(float(b_day.get(d, 0.0)), 2) for d in WEEK}
        tue_gate = week_lane["2026-08-04"] >= week_bin["2026-08-04"] - max(150.0, 0.10 * abs(week_bin["2026-08-04"]))
        wed_extras = [t for t in extras if t["date"] == "2026-08-05"]
        wed_spiral = {}
        for t in wed_extras:
            k = (t["symbol"], t["side"])
            wed_spiral[k] = wed_spiral.get(k, 0) + 1
        wed_no_spiral = all(v < 3 for v in wed_spiral.values())
        wed_gate = (week_lane["2026-08-05"] >= week_bin["2026-08-05"] - 300.0) and wed_no_spiral
        pop_net_gate = l_total >= b_total - 0.10 * abs(b_total)
        l_worst = float(l_day.min()) if len(l_day) else 0.0
        tail_gate = l_worst >= 1.25 * b_worst

        # battery
        df_l = pd.DataFrame(L["trades"])
        best_trade = float(df_l["dollar_pnl"].max()) if len(df_l) else 0.0
        g3_ex_best = round(l_total - best_trade, 2)
        runner_reasons = {r for r in df_l["exit_reason"].unique()} if len(df_l) else set()
        runner_cohort = [t for t in L["trades"]
                         if any(s in str(t["exit_reason"]).lower()
                                for s in ("runner", "trail", "profit_lock", "chandelier"))]
        # sub-window thirds by date
        all_dates = sorted(set(df_l["date"])) if len(df_l) else []
        thirds = {}
        if all_dates:
            n = len(all_dates)
            cuts = [all_dates[0], all_dates[n // 3], all_dates[(2 * n) // 3], all_dates[-1]]
            for i in range(3):
                lo, hi = cuts[i], cuts[i + 1]
                sel_l = df_l[(df_l["date"] >= lo) & (df_l["date"] <= hi)]["dollar_pnl"].sum() \
                    if i == 2 else df_l[(df_l["date"] >= lo) & (df_l["date"] < hi)]["dollar_pnl"].sum()
                b_df = pd.DataFrame(binary["trades"])
                sel_b = b_df[(b_df["date"] >= lo) & (b_df["date"] <= hi)]["dollar_pnl"].sum() \
                    if i == 2 else b_df[(b_df["date"] >= lo) & (b_df["date"] < hi)]["dollar_pnl"].sum()
                thirds[f"T{i+1}"] = {"lane": round(float(sel_l), 2), "binary": round(float(sel_b), 2),
                                      "delta": round(float(sel_l - sel_b), 2)}
        drop_best_day = round(l_total - b_best_day if False else l_total - (float(l_day.max()) if len(l_day) else 0.0), 2)
        # archetype slice on lane delta
        arch = {}
        delta_days = sorted(set(l_day.index) | set(b_day.index))
        for d in delta_days:
            a = dtypes.get(d, "unclassified")
            arch.setdefault(a, {"lane": 0.0, "binary": 0.0, "n_days": 0})
            arch[a]["lane"] += float(l_day.get(d, 0.0))
            arch[a]["binary"] += float(b_day.get(d, 0.0))
            arch[a]["n_days"] += 1
        for a in arch:
            arch[a] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in arch[a].items()}
            arch[a]["delta"] = round(arch[a]["lane"] - arch[a]["binary"], 2)

        # bootstrap cells
        pcells[f"rung{rung}_extras_all"] = bootstrap_p(ex_all)
        pcells[f"rung{rung}_extras_bull"] = bootstrap_p(ex_bull)
        pcells[f"rung{rung}_extras_bear"] = bootstrap_p(ex_bear)
        delta_series = [float(l_day.get(d, 0.0)) - float(b_day.get(d, 0.0)) for d in delta_days]
        pcells[f"rung{rung}_lane_delta_daily"] = bootstrap_p(delta_series)

        out["rungs"][rung] = {
            "lane_total": round(l_total, 2),
            "extras": {"n": len(extras), "total": round(sum(ex_all), 2),
                        "bull_n": len(ex_bull), "bull_total": round(sum(ex_bull), 2),
                        "bear_n": len(ex_bear), "bear_total": round(sum(ex_bear), 2)},
            "displaced_binary": {"n": len(displaced), "baseline_pnl": disp_pnl},
            "week_lane": week_lane, "week_binary": week_bin,
            "week_lane_total": round(sum(week_lane.values()), 2),
            "week_binary_total": round(sum(week_bin.values()), 2),
            "gates": {
                "G_week_replay_partial": sum(week_lane.values()) > sum(week_bin.values()),
                "G_tuesday": bool(tue_gate),
                "G_wednesday": bool(wed_gate),
                "G_wed_no_spiral": bool(wed_no_spiral),
                "G_population_net": bool(pop_net_gate),
                "G_population_tail": bool(tail_gate),
            },
            "battery": {
                "G1_lane_total": round(l_total, 2),
                "G1_delta_vs_binary": round(l_total - b_total, 2),
                "G3_ex_best_trade": g3_ex_best,
                "G4_runner_cohort": {"n": len(runner_cohort),
                                       "total": round(sum(t["dollar_pnl"] for t in runner_cohort), 2)},
                "exit_reasons_seen": sorted(str(x) for x in runner_reasons),
                "sub_window_thirds": thirds,
                "lane_total_minus_best_day": drop_best_day,
                "worst_day": round(l_worst, 2),
                "archetype": arch,
            },
        }

    out["bootstrap_cells"] = pcells
    out["bh_q10"] = bh(pcells)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out["rungs"].items() if k in ("7", "8")}, indent=1)[:4000])
    print("BH:", out["bh_q10"])
    print("wrote", OUT_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
