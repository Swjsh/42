#!/usr/bin/env python
"""lever_daily_cap_mtm_2026_08_06.py -- LEVER 1, the EQUITY-BASED arm.

The frozen grid measures a REALIZED-P&L breaker. That is deliberately a FLOOR: Rule 5's actual
kill switch watches EQUITY, which includes unrealized mark-to-market, so it trips EARLIER than
anything the realized-only walk can show. The realized arm's honest answer to J was "-$710 is
the best a Tuesday-safe daily cap can do to Wednesday." This module asks whether the
instrument J already owns -- an equity-based switch -- can do better, and prices the Tuesday
and Thursday cost of that on exactly the same basis.

METHOD (real data end to end, no synthetic marks):
  * Every closed engine SPY-option position in the 26-date book (same population as the
    realized arm).
  * Real OPRA 1-min bars for all 71 distinct (symbol, date) pairs, via
    exit_shape_parity_study.fetch_option_bars. A date with ANY missing symbol is DROPPED from
    the MTM population and named -- never marked with a guess.
  * Minute-by-minute fleet P&L = realized-from-actual-exit-fills (including PARTIAL exits,
    handled per-leg) + unrealized on the still-open remainder marked at that minute's real
    OPRA bar. Positions are marked from their entry minute forward.
  * Breaker: at each entry, if the fleet's mark-to-market P&L for the day is already <= -X,
    the entry is blocked. PATH-CONSISTENT -- a blocked position contributes neither realized
    nor unrealized to the running mark.
  * Blocks NEW entries only. Open positions are never force-liquidated.

MARK CHOICE: bar CLOSE is primary; bar VWAP is run as a sensitivity and both are reported.
Neither is a claim that the mark was tradeable -- it is a valuation, which is exactly what an
equity-based kill switch reads.

DESCRIPTIVE ONLY. Arms nothing, ships nothing, touches no trading-path file.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402
import lever_daily_cap_2026_08_06 as L  # noqa: E402

OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-DAILY-CAP-2026-08-06.json"
TUE, WED, THU = L.TUE, L.WED, L.THU
MULT = 100.0


def minute_key(ts: str) -> str:
    """UTC ISO timestamp -> 'YYYY-MM-DDTHH:MM' UTC minute bucket."""
    return ts[:16]


def load_marks(book: list[dict]) -> tuple[dict, set]:
    """{(symbol, 'YYYY-MM-DDTHH:MM' UTC): {'c':..,'vw':..}} from REAL OPRA 1-min bars."""
    pairs = sorted({(p["symbol"], p["date_et"]) for p in book})
    marks: dict = {}
    missing: set = set()
    for i, (sym, d) in enumerate(pairs, 1):
        bars = esp.fetch_option_bars(sym, d)
        if not bars:
            missing.add(d)
            print(f"  [{i}/{len(pairs)}] {sym} {d}: NO BARS -> date dropped")
            continue
        for b in bars:
            marks[(sym, minute_key(b["t"]))] = {"c": float(b["c"]),
                                                "vw": float(b.get("vw") or b["c"])}
        if i % 15 == 0:
            print(f"  [{i}/{len(pairs)}] fetched")
    return marks, missing


def mark_at(marks: dict, sym: str, minute: str, field: str,
            fallback: float) -> float:
    """Mark for `sym` at a UTC minute; if that exact minute has no print, walk back up to 30
    minutes, then fall back to the position's entry price (a zero-unrealized assumption, which
    is the CONSERVATIVE direction for a loss breaker -- it cannot manufacture a trip)."""
    base = dt.datetime.strptime(minute, "%Y-%m-%dT%H:%M")
    for back in range(0, 31):
        k = (sym, (base - dt.timedelta(minutes=back)).strftime("%Y-%m-%dT%H:%M"))
        if k in marks:
            return marks[k][field]
    return fallback


def _fleet_mtm(taken: list[dict], now: str, mnt: str, marks: dict, field: str) -> float:
    """Fleet mark-to-market P&L at UTC instant `now` over the positions actually taken."""
    total = 0.0
    for q in taken:
        if q["entry_ts_utc"] > now:
            continue
        realized, out_qty = 0.0, 0.0
        for ef in q["exit_fills"]:
            if ef["ts_utc"] <= now:
                realized += ef["qty"] * (ef["price"] - q["entry_price"]) * MULT
                out_qty += ef["qty"]
        open_qty = q["entry_qty"] - out_qty
        unreal = 0.0
        if open_qty > 1e-9:
            m = mark_at(marks, q["symbol"], mnt, field, q["entry_price"])
            unreal = open_qty * (m - q["entry_price"]) * MULT
        total += realized + unreal
    return total


def mtm_breaker(book: list[dict], marks: dict, cap: float | None, field: str,
                latch: bool = True) -> dict:
    """Fleet-scope equity (mark-to-market) day breaker, path-consistent.

    latch=True is the RULE-5-FAITHFUL semantics ("day closed for that account"). It is the
    DEFAULT here because Rule 5 latches.

    Also measures `armed_window_dates` -- every date whose minute-by-minute fleet mark ever
    went below -cap, WHETHER OR NOT an entry happened to arrive while it was armed. That is
    the honest bind rate: a day where the breaker was armed and simply had no entry to block
    cost $0 by TIMING LUCK, not by safety margin, and must not be counted as evidence of
    harmlessness."""
    by_day: dict = defaultdict(list)
    for p in book:
        by_day[p["date_et"]].append(p)
    kept, blocked = [], []
    armed_dates, trip_minute, armed_window = set(), {}, {}
    for d, day_pos in by_day.items():
        taken: list[dict] = []
        tripped = False
        for p in sorted(day_pos, key=lambda q: (q["entry_ts_utc"], q["arm"], q["symbol"])):
            if cap is None:
                kept.append(p)
                taken.append(p)
                continue
            now = p["entry_ts_utc"]
            total = _fleet_mtm(taken, now, minute_key(now), marks, field)
            if total <= -cap + 1e-9:
                tripped = True
            if tripped if latch else (total <= -cap + 1e-9):
                blocked.append(p)
                armed_dates.add(d)
                trip_minute.setdefault(d, minute_key(now))
            else:
                kept.append(p)
                taken.append(p)

        # --- true armed WINDOW, swept minute by minute over the ACTUAL (unmodified) day
        if cap is not None:
            t0 = min(q["entry_ts_utc"] for q in day_pos)
            t1 = max(max(ef["ts_utc"] for ef in q["exit_fills"]) for q in day_pos)
            a = dt.datetime.strptime(t0[:16], "%Y-%m-%dT%H:%M")
            b = dt.datetime.strptime(t1[:16], "%Y-%m-%dT%H:%M")
            worst, worst_at, first_below = 0.0, None, None
            while a <= b:
                mk = a.strftime("%Y-%m-%dT%H:%M")
                v = _fleet_mtm(day_pos, mk + ":59Z", mk, marks, field)
                if v < worst:
                    worst, worst_at = v, mk
                if v <= -cap + 1e-9 and first_below is None:
                    first_below = mk
                a += dt.timedelta(minutes=1)
            if first_below:
                armed_window[d] = {"first_below_utc": first_below,
                                   "worst_mtm": round(worst, 2),
                                   "worst_at_utc": worst_at,
                                   "actual_day_pnl": round(sum(q["pnl"] for q in day_pos), 2)}
    return {"kept": kept, "blocked": blocked, "armed_dates": armed_dates,
            "trip_minute": trip_minute, "armed_window_dates": armed_window}


def main() -> int:
    book = L.load_book()
    print(f"[mtm] fetching real OPRA 1-min bars for "
          f"{len({(p['symbol'], p['date_et']) for p in book})} (symbol,date) pairs...")
    marks, missing = load_marks(book)
    print(f"[mtm] {len(marks)} real OPRA 1-min marks; dates dropped for missing bars: "
          f"{sorted(missing) or 'none'}")

    pop = [p for p in book if p["date_et"] not in missing]
    base = L.day_totals(pop)
    n_dates = len(base)
    print(f"[mtm] MTM population: {len(pop)}/{len(book)} positions over {n_dates} dates")

    rows = []
    for field, tag in (("c", "bar CLOSE"), ("vw", "bar VWAP")):
        for cap in (300, 400, 500, 600, 750, 900, 1200, 1500):
            res = mtm_breaker(pop, marks, cap, field, latch=True)
            cf = L.day_totals(res["kept"])
            deltas = {d: round(cf.get(d, 0.0) - base.get(d, 0.0), 2)
                      for d in set(base) | set(cf)}
            harmed = {d: v for d, v in deltas.items() if v < -0.005}
            blk = res["blocked"]
            up = round(sum(p["pnl"] for p in blk if p["pnl"] > 0), 2)
            prev = round(sum(-p["pnl"] for p in blk if p["pnl"] < 0), 2)
            rows.append({
                "label": f"EQUITY (mark-to-market, {tag}) FLEET day breaker -${cap}",
                "mark_field": field, "cap_dollars": -cap,
                "n_positions_blocked": len(blk),
                "total_delta": round(sum(deltas.values()), 2),
                "wednesday_delta": deltas.get(WED, 0.0),
                "wednesday_after": round(cf.get(WED, 0.0), 2),
                "tuesday_delta": deltas.get(TUE, 0.0),
                "thursday_delta": deltas.get(THU, 0.0),
                "delta_ex_wednesday": round(sum(v for d, v in deltas.items() if d != WED), 2),
                "n_days_harmed": len(harmed),
                "worst_harm": round(min(harmed.values()), 2) if harmed else 0.0,
                "harmed_days": {k: v for k, v in sorted(harmed.items(),
                                                        key=lambda kv: kv[1])[:6]},
                "upside_surrendered": up, "loss_prevented": prev,
                "insurance_cost_ratio": round(up / prev, 4) if prev > 0 else None,
                "bind_rate_calendar_blocked": round(len(res["armed_dates"]) / n_dates, 4),
                "n_dates_where_something_was_blocked": len(res["armed_dates"]),
                # the HONEST bind rate: every date the breaker was ARMED at any minute,
                # whether or not an entry happened to arrive while it was armed.
                "n_dates_ARMED_at_any_minute": len(res["armed_window_dates"]),
                "bind_rate_calendar_ARMED": round(len(res["armed_window_dates"]) / n_dates, 4),
                "armed_window_detail": res["armed_window_dates"],
                "armed_on_a_PROFITABLE_day": sorted(
                    d for d, v in res["armed_window_dates"].items()
                    if v["actual_day_pnl"] > 0),
                "wednesday_trip_minute_utc": res["trip_minute"].get(WED),
                "REJECTED_TUESDAY": deltas.get(TUE, 0.0) < -0.005,
            })

    out = {
        "_question": ("Rule 5 is EQUITY-based, not realized-based. Does including unrealized "
                      "mark-to-market let a Tuesday-safe fleet day breaker get Wednesday below "
                      "the realized arm's -$710 floor?"),
        "method": ("Real OPRA 1-min bars for every (symbol,date) in the book; minute-by-minute "
                   "fleet P&L = realized from ACTUAL exit fills (partial exits handled per-leg) "
                   "+ unrealized on the open remainder at that minute's real bar. "
                   "Path-consistent; blocks NEW entries only; never force-liquidates."),
        "mark_fallback_note": ("If a symbol has no print in the exact minute, the mark walks "
                               "back up to 30 minutes; if still nothing, it falls back to the "
                               "position's ENTRY price (zero unrealized), which cannot "
                               "manufacture a trip. Conservative by construction."),
        "n_opra_minute_marks": len(marks),
        "dates_dropped_for_missing_bars": sorted(missing),
        "population_n_positions": len(pop), "population_n_dates": n_dates,
        "baseline_days": base,
        "cells": rows,
    }
    prev_json = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    prev_json["equity_mtm_arm"] = out
    OUT_JSON.write_text(json.dumps(prev_json, indent=2), encoding="utf-8")
    print(f"[mtm] wrote {OUT_JSON}")

    print(f"\n{'cell':52s} {'nBlk':>4s} {'total':>9s} {'WEDaft':>9s} "
          f"{'TUE':>9s} {'THU':>7s} {'harm':>4s} {'ratio':>6s} {'ARMED':>6s} {'onWinDay':>9s} G")
    for r in rows:
        ratio = "n/a" if r["insurance_cost_ratio"] is None else f"{r['insurance_cost_ratio']:.2f}"
        gate = "X" if r["REJECTED_TUESDAY"] else "."
        print(f"{r['label']:52.52s} {r['n_positions_blocked']:4d} {r['total_delta']:9.2f} "
              f"{r['wednesday_after']:9.2f} {r['tuesday_delta']:9.2f} {r['thursday_delta']:7.2f} "
              f"{r['n_days_harmed']:4d} {ratio:>6s} "
              f"{r['n_dates_ARMED_at_any_minute']:6d} "
              f"{len(r['armed_on_a_PROFITABLE_day']):9d} {gate}")

    print("\n== THE TIMING-LUCK CHECK: dates where the breaker was ARMED at some minute ==")
    for r in rows:
        if r["mark_field"] != "c":
            continue
        det = r["armed_window_detail"]
        if not det:
            continue
        print(f"  {r['label']}")
        for d, v in sorted(det.items()):
            note = "  <-- ARMED ON A DAY THAT ENDED PROFITABLE" if v["actual_day_pnl"] > 0 else ""
            print(f"      {d}  first below at {v['first_below_utc'][11:]} UTC  "
                  f"worst MTM {v['worst_mtm']:9.2f} at {v['worst_at_utc'][11:]}  "
                  f"day ended {v['actual_day_pnl']:9.2f}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
