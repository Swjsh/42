#!/usr/bin/env python
"""winners_exit_target_robustness_2026_08_19.py -- the anti-cherry-pick layer.

Every headline cell in the exit-target matrix wins by a delta whose top DAY carries 68-103%
of it. This module answers, for the top cells + the doctrinally interesting ones:
  1. LODO   -- leave-one-day-out: does the delta survive dropping its best day? its worst?
  2. LOAO   -- leave-one-arm-out: is it one arm's accident?
  3. BOOT   -- cluster bootstrap by DAY (the correlated unit), 2000 resamples, P(delta>0)
  4. RULE5  -- worst single arm-day under the cell, against the -30%/-50% kill switch
  5. SPLIT  -- first-half / second-half of the book (a crude walk-forward)
Reads the raw grid + the scored JSON. Writes the robustness block into the tables file.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "setup" / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

RAW = REPO / "backtest" / "data" / "winners-exit-target-matrix-2026-08-19.raw.json"
SCORED = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.json"
OUT = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.robust.json"
TABLES = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md"
MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"

P = "pnl_market_range"
FEE = "fees_market"
EQUITY = {"safe-2": 5501.0, "bold-2": 1633.0, "safe-3": 2000.0,
          "risky-1": 2000.0, "risky-3": 2000.0}   # accounts.json / CLAUDE.md, approximate
KILL = {"safe-2": 0.30, "safe-3": 0.30, "bold-2": 0.50, "risky-1": 0.50, "risky-3": 0.50}


def net_of(t):
    if t[P] is None or t[FEE] is None:
        return None
    return t[P] - t[FEE]


def deltas(cell_trades, prod_by_key):
    """Per-trade delta rows: (delta, date, arm)."""
    out = []
    for t in cell_trades:
        k = (t["arm"], t["symbol"], t["entry_ts"])
        p = prod_by_key.get(k)
        if p is None:
            continue
        a, b = net_of(t), net_of(p)
        if a is None or b is None:
            continue
        out.append((a - b, t["date"], t["arm"]))
    return out


def by_day(rows):
    d = defaultdict(float)
    for v, date, _ in rows:
        d[date] += v
    return d


def analyse(cell_id, rows, prod_rows):
    d = deltas(rows, prod_rows)
    total = sum(x[0] for x in d)
    bd = by_day(d)
    days = sorted(bd)
    best_day = max(bd.items(), key=lambda kv: kv[1])
    worst_day = min(bd.items(), key=lambda kv: kv[1])
    top_abs_day = max(bd.items(), key=lambda kv: abs(kv[1]))
    top_trade = max(d, key=lambda x: abs(x[0]))

    # LODO: min delta over all single-day removals
    lodo = {dd: total - v for dd, v in bd.items()}
    lodo_min_day = min(lodo.items(), key=lambda kv: kv[1])

    # LOAO
    ba = defaultdict(float)
    for v, _, arm in d:
        ba[arm] += v
    loao = {a: total - v for a, v in ba.items()}
    loao_min = min(loao.items(), key=lambda kv: kv[1]) if loao else (None, None)

    # cluster bootstrap by DAY
    day_vals = [bd[dd] for dd in days]
    rnd = random.Random(20260819)
    boots = []
    n = len(day_vals)
    for _ in range(2000):
        boots.append(sum(day_vals[rnd.randrange(n)] for _ in range(n)))
    boots.sort()
    p_pos = sum(1 for b in boots if b > 0) / len(boots)
    ci = (boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))])

    # split-half walk-forward
    mid = days[len(days) // 2]
    first = sum(v for dd, v in bd.items() if dd < mid)
    second = sum(v for dd, v in bd.items() if dd >= mid)

    # Rule-5 exposure: worst ABSOLUTE arm-day P&L under this cell (not the delta)
    arm_day = defaultdict(float)
    for t in rows:
        v = net_of(t)
        if v is None:
            continue
        arm_day[(t["arm"], t["date"])] += v
    worst = min(arm_day.items(), key=lambda kv: kv[1])
    breaches = sum(1 for (arm, _), v in arm_day.items()
                   if v < -KILL.get(arm, 0.5) * EQUITY.get(arm, 2000.0))

    return {
        "cell_id": cell_id, "total_delta_net": round(total, 2),
        "n_days": len(days),
        "top_day": [top_abs_day[0], round(top_abs_day[1], 2),
                    round(top_abs_day[1] / total, 4) if total else None],
        "best_day": [best_day[0], round(best_day[1], 2)],
        "worst_day": [worst_day[0], round(worst_day[1], 2)],
        "top_trade": [top_trade[1], top_trade[2], round(top_trade[0], 2),
                      round(top_trade[0] / total, 4) if total else None],
        "lodo_min": [lodo_min_day[0], round(lodo_min_day[1], 2)],
        "lodo_all_positive": all(v > 0 for v in lodo.values()),
        "days_positive": sum(1 for v in bd.values() if v > 0),
        "days_negative": sum(1 for v in bd.values() if v < 0),
        "loao_min": [loao_min[0], round(loao_min[1], 2) if loao_min[1] is not None else None],
        "boot_p_positive": round(p_pos, 4),
        "boot_ci95": [round(ci[0], 2), round(ci[1], 2)],
        "split_first_half": round(first, 2), "split_second_half": round(second, 2),
        "split_sign_stable": (first > 0) == (second > 0),
        "worst_arm_day_abs": [worst[0][0], worst[0][1], round(worst[1], 2)],
        "rule5_breach_arm_days": breaches,
    }


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    scored = json.loads(SCORED.read_text(encoding="utf-8"))
    per_trade = raw["per_trade"]

    # rebuild the production reference from the scored run's stored population
    import winners_exit_target_report_2026_08_19 as R
    prod = R.run_production()
    prod_by_key = {(t["arm"], t["symbol"], t["entry_ts"]): t for t in prod}

    ranked = scored["cells"]
    interesting = [r["cell_id"] for r in ranked[:10]]
    for cid in ("f0.0_t0.3_r1.0_x0.1", "f0.667_t1.0_r99.0_x0.15",
                "f0.667_t1.5_r99.0_x0.15", "f0.667_t0.5_r99.0_x0.15",
                "f1.0_t1.0_r1.0_x0.1", "f0.667_t1.0_r99.0_x0.4",
                "f0.667_t1.0_r2.5_x0.15"):
        if cid in per_trade and cid not in interesting:
            interesting.append(cid)

    out = []
    for cid in interesting:
        out.append(analyse(cid, per_trade[cid], prod_by_key))

    # production's own absolute Rule-5 exposure, for reference
    arm_day = defaultdict(float)
    for t in prod:
        v = net_of(t)
        if v is not None:
            arm_day[(t["arm"], t["date"])] += v
    pw = min(arm_day.items(), key=lambda kv: kv[1])
    prod_breaches = sum(1 for (arm, _), v in arm_day.items()
                        if v < -KILL.get(arm, 0.5) * EQUITY.get(arm, 2000.0))

    payload = {"generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
               "primary_model": P, "n_bootstrap": 2000, "cluster_unit": "trading day",
               "production_worst_arm_day": [pw[0][0], pw[0][1], round(pw[1], 2)],
               "production_rule5_breach_arm_days": prod_breaches,
               "cells": out}
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    L = ["", "### F. Robustness — the anti-cherry-pick layer", "",
         "Cluster unit = **trading day** (the 5 arms are one signal; a day is the correlated "
         "block). 2,000 day-bootstrap resamples. `LODO min` = the delta after removing the "
         "single day that hurts it most.", "",
         "| cell | delta | top day | share | LODO min | days +/- | boot P(>0) | boot 95% CI | "
         "1st half | 2nd half | worst arm-day | Rule5 breaches |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out:
        L.append("| `%s` | %+0.0f | %s | %s | %+0.0f | %d/%d | %.0f%% | [%+0.0f, %+0.0f] | "
                 "%+0.0f | %+0.0f | %s %s %+0.0f | %d |"
                 % (r["cell_id"], r["total_delta_net"], r["top_day"][0],
                    ("%.0f%%" % (100 * r["top_day"][2])) if r["top_day"][2] is not None else "-",
                    r["lodo_min"][1], r["days_positive"], r["days_negative"],
                    100 * r["boot_p_positive"], r["boot_ci95"][0], r["boot_ci95"][1],
                    r["split_first_half"], r["split_second_half"],
                    r["worst_arm_day_abs"][0], r["worst_arm_day_abs"][1],
                    r["worst_arm_day_abs"][2], r["rule5_breach_arm_days"]))
    L.append("| **PRODUCTION** | 0 | - | - | - | - | - | - | - | - | %s %s %+0.0f | %d |"
             % (payload["production_worst_arm_day"][0], payload["production_worst_arm_day"][1],
                payload["production_worst_arm_day"][2], prod_breaches))
    L.append("")
    with TABLES.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print("wrote", OUT)
    for r in out:
        print("%-28s delta %+8.0f  topday %s %s  LODOmin %+8.0f  P(>0) %.0f%%  CI [%+0.0f,%+0.0f]  "
              "worstArmDay %s %s %+0.0f  R5breach %d"
              % (r["cell_id"], r["total_delta_net"], r["top_day"][0],
                 ("%.0f%%" % (100 * r["top_day"][2])) if r["top_day"][2] is not None else "-",
                 r["lodo_min"][1], 100 * r["boot_p_positive"], r["boot_ci95"][0],
                 r["boot_ci95"][1], r["worst_arm_day_abs"][0], r["worst_arm_day_abs"][1],
                 r["worst_arm_day_abs"][2], r["rule5_breach_arm_days"]))
    print("PRODUCTION worst arm-day: %s %s %+0.0f | breaches %d"
          % (payload["production_worst_arm_day"][0], payload["production_worst_arm_day"][1],
             payload["production_worst_arm_day"][2], prod_breaches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
