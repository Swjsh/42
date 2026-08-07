"""SIZE-ANATOMY 2026-08-07 — Lane 4: the $629 morning, sizing arithmetic, dollar-risk lens.

Answers (workflow directive, Friday 2026-08-07):
  1. Per-arm qty resolution for the 09:46-09:47 morning trade (28 contracts).
  2. Per-trade dollar-risk normalization {1.5%, 2%, 3% of equity} counterfactual —
     morning AND week (Mon 08-03 .. Fri 08-07 morning), sequential, all arms.
  3. Kill-switch fractions + C31 context.
  4. Battery cells for the stage-as-prereg decision (does NOT ship tonight).

DESIGN (frozen before the run; see JSON `prereg_frame`):
  - Population: every closed SPY-0DTE round-trip position, all 5 arms,
    Mon 2026-08-03 .. Thu 2026-08-06 from journal/trades.csv (T1 broker-truth
    round_trips, grouped by entry_order_id), PLUS Fri 2026-08-07 morning from
    automation/state/trade-today.json broker fills (bridge backfill not yet run).
  - Risk unit per contract = 0.5 * entry_premium * 100 — the v15.3 -50%
    catastrophe cap, the DESIGNED max loss per contract both sides (2026-06-18).
    A full-premium (gap-to-zero) reading of the same cells is f/2 -> same table.
  - qty_cf = floor(f * equity_cf / risk_unit). Three floor variants (all cells reported):
      prod_floor      : max(arm min_contracts (3 safe / 5 bold), qty_cf) — what
                        production risk_gate/min_contracts would actually enforce;
                        NOTE the floor RAISES risk above f on expensive contracts.
      prod_floor_shrink: same, but never sizes ABOVE the actual live qty
                        (pure risk-cap overlay — the direct "$629 too big" lens).
      no_floor        : qty_cf as computed, 0 -> trade skipped (honest cap; violates
                        Rule 6 min-3 — reported as sensitivity, not shippable).
  - pnl_cf = pnl_actual * qty_cf / qty_actual (position-level exact; leg-level
    rounding ignored — LEVER-SIZING-2026-08-06 caveat carried forward).
  - Sequential per (arm): equity_cf starts at the arm's first equity_pre of the
    week and compounds with pnl_cf.
  - Gates reported per cell (WEEK-ORDER battery shape): G1 aggregate, G3 ex-best
    (drop best actual position from both sides), G4 runner cohort (multi-leg
    positions), drop-best-day, sub-window halves. n=5 days — no FDR pretense;
    the POPULATION verdict rides on LEVER-SIZING-2026-08-06 cell (e) (26-day
    book + 141-day replay), quoted in the artifact.

Read-only on all trading-path files. Writes analysis/deep-research/ artifacts only.
"""
from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TRADES_CSV = os.path.join(ROOT, "journal", "trades.csv")
TRADE_TODAY = os.path.join(ROOT, "automation", "state", "trade-today.json")
OUT_JSON = os.path.join(ROOT, "analysis", "deep-research", "SIZE-ANATOMY-2026-08-07.json")

WEEK_CSV_DATES = ("2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06")
FRIDAY = "2026-08-07"

# Per-arm production floors (params.json min_contracts=3 / aggressive params.json=5)
ARM_FLOOR = {"safe-2": 3, "safe-3": 3, "bold-2": 5, "risky-1": 5, "risky-3": 5}
# Rule-5 daily kill fraction of SOD equity
ARM_KILL = {"safe-2": 0.30, "safe-3": 0.30, "bold-2": 0.50, "risky-1": 0.50, "risky-3": 0.50}

F_CELLS = (0.015, 0.02, 0.03)
VARIANTS = ("prod_floor", "prod_floor_shrink", "no_floor")

# Friday-morning SOD equities quoted from the 09:31 flat ledger rows / 09:46 core exec row
FRIDAY_SOD = {"safe-2": 5727.59, "safe-3": 5780.15, "risky-1": 6338.25, "risky-3": 5342.98}


def load_week_positions():
    """Mon-Thu from trades.csv T1 rows, grouped to positions by (date, arm, entry_order_id)."""
    pos = {}
    with open(TRADES_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["date"] not in WEEK_CSV_DATES:
                continue
            try:
                meta = json.loads(row["archetype_match_json"])
            except (ValueError, TypeError):
                meta = {}
            arm = meta.get("arm") or row.get("account_id")
            key = (row["date"], arm, meta.get("entry_order_id", "?"))
            p = pos.setdefault(key, {
                "date": row["date"], "arm": arm, "qty": 0, "pnl": 0.0, "legs": 0,
                "entry_px": float(row["entry_px"]), "equity_pre": float(row["account_equity_pre"]),
                "time": row["time_entry"], "contract": row["contract"],
            })
            p["qty"] += int(row["qty"])
            p["pnl"] += float(row["dollar_pnl"])
            p["legs"] += 1
    return sorted(pos.values(), key=lambda p: (p["date"], p["time"], p["arm"]))


def friday_morning_positions():
    """Fri morning round trips reconstructed from broker fills in trade-today.json.

    Only the 09:46-09:47 entries + 10:01-10:02 exits (the closed morning round trip);
    the 12:06-12:07 second-wave entries are OPEN at run time and excluded."""
    with open(TRADE_TODAY, encoding="utf-8") as f:
        tt = json.load(f)
    fills = [x for x in tt["fills"] if x["status"] == "filled"]
    out = []
    for arm in ("safe-2", "safe-3", "risky-1", "risky-3"):
        arm_fills = [x for x in fills if x["arm"] == arm]
        buys = [x for x in arm_fills if x["side"] == "buy" and x["filled_at"] < "2026-08-07T14:00"]
        sells = [x for x in arm_fills if x["side"] == "sell" and x["filled_at"] < "2026-08-07T15:00"]
        assert len(buys) == 1 and len(sells) == 1, (arm, len(buys), len(sells))
        b, s = buys[0], sells[0]
        assert b["symbol"] == s["symbol"] and b["qty"] == s["qty"], arm
        qty = int(b["qty"])
        pnl = (s["price"] - b["price"]) * qty * 100.0
        out.append({
            "date": FRIDAY, "arm": arm, "qty": qty, "pnl": round(pnl, 2), "legs": 1,
            "entry_px": b["price"], "equity_pre": FRIDAY_SOD[arm],
            "time": "09:46", "contract": b["symbol"],
        })
    return out


def qty_cf_for(f, equity_cf, entry_px, arm, actual_qty, variant):
    risk_unit = 0.5 * entry_px * 100.0
    q = math.floor((f * equity_cf) / risk_unit)
    if variant == "no_floor":
        return q  # 0 => skip
    q = max(ARM_FLOOR[arm], q)
    if variant == "prod_floor_shrink":
        q = min(q, actual_qty)
    return q


def run_cell(book, f, variant):
    eq_cf = {}
    recs = []
    for p in book:
        arm = p["arm"]
        eq_cf.setdefault(arm, p["equity_pre"])  # arm's first appearance seeds its equity
        q = qty_cf_for(f, eq_cf[arm], p["entry_px"], arm, p["qty"], variant)
        pnl_cf = p["pnl"] * (q / p["qty"]) if q > 0 else 0.0
        eq_cf[arm] += pnl_cf
        recs.append({**p, "qty_cf": q, "pnl_cf": round(pnl_cf, 2),
                     "floored": (variant != "no_floor" and q == ARM_FLOOR[arm]
                                 and math.floor(f * (eq_cf[arm] - pnl_cf) / (0.5 * p["entry_px"] * 100)) < ARM_FLOOR[arm]),
                     "skipped": q == 0})
    days = defaultdict(lambda: [0.0, 0.0])
    for r in recs:
        days[r["date"]][0] += r["pnl"]
        days[r["date"]][1] += r["pnl_cf"]
    day_rows = {d: {"actual": round(v[0], 2), "cf": round(v[1], 2), "delta": round(v[1] - v[0], 2)}
                for d, v in sorted(days.items())}
    tot_a = sum(r["pnl"] for r in recs)
    tot_c = sum(r["pnl_cf"] for r in recs)
    best = max(recs, key=lambda r: r["pnl"])  # G3: drop best actual position both sides
    g3_a = tot_a - best["pnl"]
    g3_c = tot_c - best["pnl_cf"]
    runner = [r for r in recs if r["legs"] >= 2]  # G4 runner cohort (multi-leg positions)
    g4_a = sum(r["pnl"] for r in runner)
    g4_c = sum(r["pnl_cf"] for r in runner)
    best_day = max(day_rows, key=lambda d: day_rows[d]["actual"])
    dbd_a = tot_a - day_rows[best_day]["actual"]
    dbd_c = tot_c - day_rows[best_day]["cf"]
    return {
        "f": f, "variant": variant,
        "week_actual": round(tot_a, 2), "week_cf": round(tot_c, 2), "week_delta": round(tot_c - tot_a, 2),
        "days": day_rows,
        "friday_morning_cf": day_rows[FRIDAY]["cf"], "friday_morning_delta": day_rows[FRIDAY]["delta"],
        "wed_cf": day_rows["2026-08-05"]["cf"],
        "g1_aggregate_improves": tot_c > tot_a,
        "g3_ex_best": {"actual": round(g3_a, 2), "cf": round(g3_c, 2), "delta": round(g3_c - g3_a, 2)},
        "g4_runner_cohort": {"n": len(runner), "actual": round(g4_a, 2), "cf": round(g4_c, 2),
                             "delta": round(g4_c - g4_a, 2)},
        "drop_best_day": {"dropped": best_day, "actual": round(dbd_a, 2), "cf": round(dbd_c, 2),
                          "delta": round(dbd_c - dbd_a, 2)},
        "n_floored": sum(1 for r in recs if r.get("floored")),
        "n_skipped": sum(1 for r in recs if r.get("skipped")),
        "n_upsized": sum(1 for r in recs if r["qty_cf"] > r["qty"]),
        "n_downsized": sum(1 for r in recs if 0 < r["qty_cf"] < r["qty"]),
        "positions": [{k: r[k] for k in ("date", "arm", "time", "contract", "qty", "qty_cf",
                                          "entry_px", "pnl", "pnl_cf")} for r in recs],
    }


def main():
    week = load_week_positions()
    fri = friday_morning_positions()
    book = week + fri

    # ---- reconciliation assertions (fail loud, never publish unreconciled numbers) ----
    day_tot = defaultdict(float)
    for p in book:
        day_tot[p["date"]] += p["pnl"]
    expect = {"2026-08-03": 534.0, "2026-08-04": 3624.0, "2026-08-05": -1935.0, "2026-08-06": 1465.0}
    for d, v in expect.items():
        assert abs(day_tot[d] - v) < 1.0, (d, day_tot[d], v)
    # Friday morning: fills-gross -628; book -629.46 incl. fees. Assert the gross.
    assert abs(day_tot[FRIDAY] - (-628.0)) < 1.0, day_tot[FRIDAY]
    fri_qty = {p["arm"]: p["qty"] for p in fri}
    assert fri_qty == {"safe-2": 3, "safe-3": 8, "risky-1": 5, "risky-3": 12}, fri_qty
    assert sum(fri_qty.values()) == 28

    cells = [run_cell(book, f, v) for f in F_CELLS for v in VARIANTS]

    # ---- morning anatomy + kill-switch context ----
    morning = []
    for p in fri:
        arm = p["arm"]
        budget = ARM_KILL[arm] * p["equity_pre"]
        morning.append({
            "arm": arm, "qty": p["qty"], "entry_fill": p["entry_px"], "pnl": p["pnl"],
            "pnl_per_contract": round(p["pnl"] / p["qty"], 2),
            "entry_notional": round(p["entry_px"] * p["qty"] * 100, 2),
            "notional_pct_equity": round(100 * p["entry_px"] * p["qty"] * 100 / p["equity_pre"], 1),
            "cat_cap_dollar_risk": round(0.5 * p["entry_px"] * p["qty"] * 100, 2),
            "cat_cap_risk_pct_equity": round(100 * 0.5 * p["entry_px"] * p["qty"] * 100 / p["equity_pre"], 2),
            "sod_equity": p["equity_pre"],
            "rule5_kill_budget": round(budget, 2),
            "loss_pct_of_kill_budget": round(100 * -p["pnl"] / budget, 1),
        })
    combined_budget = sum(m["rule5_kill_budget"] for m in morning)

    out = {
        "run_at_et": "2026-08-07 ~12:1x ET (market hours; analysis-only, no trading-path writes)",
        "prereg_frame": {
            "risk_unit": "0.5 * entry_premium * 100 (v15.3 -50% catastrophe cap; full-premium reading = same table at f/2)",
            "cells": {"f": list(F_CELLS), "variants": list(VARIANTS)},
            "pnl_model": "pnl_cf = pnl * qty_cf/qty, position-level (LEVER-SIZING leg-rounding caveat carried)",
            "sequential": "per-arm equity compounding from first equity_pre of the week",
            "population_verdict_source": "LEVER-SIZING-2026-08-06 cell (e) — constant-dollar REFUTED on 26-day book (-$2,981 at budget-neutral) + hump-shaped return-on-notional; this week run is the directive's narrower question, not a re-litigation",
        },
        "book_n_positions": len(book),
        "friday_morning_anatomy": morning,
        "friday_book_loss_fills_gross": round(day_tot[FRIDAY], 2),
        "friday_book_loss_official": -629.46,
        "combined_kill_budget": round(combined_budget, 2),
        "book_loss_pct_of_combined_kill_budget": round(100 * 629.46 / combined_budget, 1),
        "cells": cells,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    # ---- console summary ----
    print(f"book positions: {len(book)}  (Mon-Thu {len(week)} + Fri morning {len(fri)})")
    print("day totals reconciled: " + ", ".join(f"{d} {day_tot[d]:+.0f}" for d in sorted(day_tot)))
    print("\nFRIDAY MORNING ANATOMY")
    for m in morning:
        print(f"  {m['arm']:8s} qty {m['qty']:2d} @ {m['entry_fill']:.2f}  pnl {m['pnl']:+8.2f} "
              f"({m['pnl_per_contract']:+6.2f}/ct)  notional {m['entry_notional']:7.0f} "
              f"({m['notional_pct_equity']:4.1f}% eq)  cat-cap risk {m['cat_cap_dollar_risk']:6.0f} "
              f"({m['cat_cap_risk_pct_equity']:5.2f}% eq)  loss = {m['loss_pct_of_kill_budget']:4.1f}% of kill budget")
    print(f"  book -629.46 = {out['book_loss_pct_of_combined_kill_budget']}% of combined kill budgets (${combined_budget:,.0f})")
    print("\nCELLS (week delta / Fri-morning cf / Wed cf / G3 delta / G4 delta / drop-best-day delta / floored / skipped / upsized)")
    for c in cells:
        print(f"  f={c['f']:<5} {c['variant']:17s} weekD {c['week_delta']:+9.2f}  "
              f"FriAM {c['friday_morning_cf']:+8.2f}  Wed {c['wed_cf']:+9.2f}  "
              f"G3D {c['g3_ex_best']['delta']:+9.2f}  G4D {c['g4_runner_cohort']['delta']:+9.2f}  "
              f"DBD {c['drop_best_day']['delta']:+9.2f}  fl {c['n_floored']:2d}  sk {c['n_skipped']:2d}  up {c['n_upsized']:2d}")
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
