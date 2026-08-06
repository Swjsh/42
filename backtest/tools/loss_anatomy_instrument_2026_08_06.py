#!/usr/bin/env python
"""loss_anatomy_instrument_2026_08_06.py -- LANE 0 / Q1 closer: the anatomy says the loss is
Pareto-concentrated AT THE DAY LEVEL and flat at the trade level. So: WHICH INSTRUMENT?

Prices, on the real-fill book, the only tail instrument the anatomy actually implicates --
a REALIZED-P&L DAY BREAKER that blocks NEW entries once the day is down X -- against the
per-trade alternative (a hard per-trade loss cap), and reports each one's cost on Tuesday
(+$3,624) and Thursday (+$1,465) alongside its Wednesday saving. A lever that fixes Wednesday
and costs Tuesday is not a lever.

CAUSALITY (no look-ahead, C6):
  * A position's P&L is known to the engine only when its LAST exit fill prints. Cumulative
    realized-at-time-t therefore counts ONLY positions fully closed at or before t.
  * A new entry at time t is blocked iff cumulative realized <= -X at t.
  * A position already OPEN when the breaker trips is NOT force-liquidated -- it runs to its
    actual exit. This matches Rule 5's real semantics ("day closed for that account", i.e.
    no new trades) and is the conservative choice.
  * Realized-only is STRICTLY LATER-TRIPPING than the live equity-based kill switch (which
    also sees unrealized mark-to-market). Every saving reported here is therefore a FLOOR on
    what an equity-based breaker at the same threshold would have saved.

The per-trade cap arm is an ORACLE and is LABELLED as such: truncating a realised loss at -$X
requires the exit to have fired at a price we cannot prove was available. It exists in this
file only as the comparator that shows the per-trade axis is the WRONG axis -- never as a
shippable number.

DESCRIPTIVE ONLY. Writes only into analysis/deep-research/LOSS-ANATOMY-2026-08-06.json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "LOSS-ANATOMY-2026-08-06.json"
TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"


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
    for p in pos:
        p["pnl"] = round(p["actual_exit_pnl"], 2)
        p["close_ts"] = max(ef["ts_utc"] for ef in p["exit_fills"])
    pos.sort(key=lambda p: (p["date_et"], p["entry_ts_utc"]))
    return pos


def day_breaker(pos: list[dict], cap: float, *, per_arm: bool) -> dict:
    """Return the counterfactual book under a realized-P&L breaker at -cap."""
    by_day: dict = defaultdict(list)
    for p in pos:
        by_day[p["date_et"]].append(p)
    kept, dropped = [], []
    for _d, day_pos in by_day.items():
        day_pos = sorted(day_pos, key=lambda p: p["entry_ts_utc"])
        closed = sorted(day_pos, key=lambda p: p["close_ts"])
        for p in day_pos:
            scope = (lambda q: q["arm"] == p["arm"]) if per_arm else (lambda q: True)
            realized = sum(q["pnl"] for q in closed
                           if q["close_ts"] <= p["entry_ts_utc"] and scope(q))
            if realized <= -cap:
                dropped.append(p)
            else:
                kept.append(p)
    return {"kept": kept, "dropped": dropped}


def per_trade_cap(pos: list[dict], cap: float) -> list[dict]:
    """ORACLE. Truncate every losing position at -cap."""
    return [{**p, "pnl": max(p["pnl"], -cap)} for p in pos]


def day_totals(rows: list[dict]) -> dict:
    d: dict = defaultdict(float)
    for r in rows:
        d[r["date_et"]] += r["pnl"]
    return {k: round(v, 2) for k, v in d.items()}


def score(base_days: dict, cf_days: dict, label: str, n_dropped: int = 0) -> dict:
    all_days = sorted(set(base_days) | set(cf_days))
    deltas = {d: round(cf_days.get(d, 0.0) - base_days.get(d, 0.0), 2) for d in all_days}
    harmed = {d: v for d, v in deltas.items() if v < -0.005}
    helped = {d: v for d, v in deltas.items() if v > 0.005}
    return {
        "label": label,
        "n_positions_blocked": n_dropped,
        "total_delta": round(sum(deltas.values()), 2),
        "book_after": round(sum(cf_days.values()), 2),
        "wednesday_delta": deltas.get(WED, 0.0),
        "tuesday_delta": deltas.get(TUE, 0.0),
        "thursday_delta": deltas.get(THU, 0.0),
        "wednesday_after": cf_days.get(WED, 0.0),
        "n_days_touched": len(harmed) + len(helped),
        "n_days_harmed": len(harmed),
        "n_days_helped": len(helped),
        "worst_harm": min(harmed.values()) if harmed else 0.0,
        "harmed_days": {k: v for k, v in sorted(harmed.items(), key=lambda kv: kv[1])[:6]},
        "delta_ex_wednesday": round(sum(v for d, v in deltas.items() if d != WED), 2),
    }


def main() -> int:
    pos = load_positions()
    base = day_totals(pos)
    base_total = round(sum(base.values()), 2)
    print(f"[instrument] {len(pos)} positions, {len(base)} days, book {base_total}")

    caps = [250, 400, 500, 600, 750, 1000, 1500]
    fleet_rows, arm_rows, trade_rows = [], [], []
    for c in caps:
        r = day_breaker(pos, c, per_arm=False)
        fleet_rows.append(score(base, day_totals(r["kept"]),
                                f"FLEET realized-day breaker -${c}", len(r["dropped"])))
        r2 = day_breaker(pos, c, per_arm=True)
        arm_rows.append(score(base, day_totals(r2["kept"]),
                              f"PER-ARM realized-day breaker -${c}", len(r2["dropped"])))
    for c in (100, 150, 200, 300, 500):
        trade_rows.append(score(base, day_totals(per_trade_cap(pos, c)),
                                f"ORACLE per-trade loss cap -${c}"))

    # --- the entry-count axis, for contrast: cap N positions per (arm, date)
    count_rows = []
    for n in (2, 3, 4, 6, 8):
        seq: dict = defaultdict(int)
        kept = []
        ndrop = 0
        for p in sorted(pos, key=lambda q: (q["date_et"], q["entry_ts_utc"])):
            k = (p["arm"], p["date_et"])
            seq[k] += 1
            if seq[k] <= n:
                kept.append(p)
            else:
                ndrop += 1
        count_rows.append(score(base, day_totals(kept),
                                f"cap {n} positions per (arm,date)", ndrop))

    # --- and the per-contract wave cap (the CAP-3 lever already on the table)
    wave_rows = []
    for n in (1, 2, 3, 4):
        seq: dict = defaultdict(int)
        kept = []
        ndrop = 0
        for p in sorted(pos, key=lambda q: (q["date_et"], q["entry_ts_utc"])):
            k = (p["arm"], p["symbol"], p["date_et"])
            seq[k] += 1
            if seq[k] <= n:
                kept.append(p)
            else:
                ndrop += 1
        wave_rows.append(score(base, day_totals(kept),
                               f"cap {n} entries per (arm,symbol,date)", ndrop))

    # ---- 391-day REPLAY validation of the same breaker.
    # Population B is ONE arm at qty 3 -- a fifth of the fleet's daily risk budget -- so the
    # SAME dollar cap is a much tighter constraint there. Both the raw cap ladder and a
    # fleet-scaled equivalent (cap/5) are reported; neither is presented as apples-to-apples.
    rep = json.loads((REPO / "analysis" / "recommendations" /
                      "engine-fullhist-replay-2026-07-23.json").read_text(encoding="utf-8"))
    rtr = sorted(rep["trades"], key=lambda t: (t["date"], t["entry_time_et"]))
    for t in rtr:
        t["pnl"] = round(float(t["dollar_pnl"]), 2)
        t["date_et"] = t["date"]
    rep_base = day_totals(rtr)
    rep_rows = []
    for c in (100, 120, 150, 200, 250, 300, 400, 500, 600):
        by_day: dict = defaultdict(list)
        for t in rtr:
            by_day[t["date"]].append(t)
        kept, ndrop = [], 0
        for _d, day_t in by_day.items():
            day_t = sorted(day_t, key=lambda x: x["entry_time_et"])
            run = 0.0
            for t in day_t:
                if run <= -c:
                    ndrop += 1
                    continue
                kept.append(t)
                # replay rows expose no exit timestamp; hold_minutes gives one, but the
                # SEQUENTIAL one-position-at-a-time walk this population was built under
                # means trade k+1 cannot start before trade k is closed. Cumulative-by-entry-
                # order IS therefore cumulative-realized here. Stated, not assumed silently.
                run += t["pnl"]
        rep_rows.append({
            "cap": -c, "n_blocked": ndrop,
            "total_delta": round(sum(day_totals(kept).values()) - sum(rep_base.values()), 2),
            "book_after": round(sum(day_totals(kept).values()), 2),
            "n_days_harmed": sum(1 for d, v in day_totals(kept).items()
                                 if v < rep_base.get(d, 0.0) - 0.005),
            "n_days_helped": sum(1 for d, v in day_totals(kept).items()
                                 if v > rep_base.get(d, 0.0) + 0.005),
        })
    print("\n== 391-day REPLAY: same realized-day breaker (ONE arm, qty 3)")
    print(f"{'cap':>6s} {'nBlk':>5s} {'total':>10s} {'after':>10s} {'harm':>5s} {'help':>5s}")
    for r in rep_rows:
        print(f"{r['cap']:6d} {r['n_blocked']:5d} {r['total_delta']:10.1f} "
              f"{r['book_after']:10.1f} {r['n_days_harmed']:5d} {r['n_days_helped']:5d}")

    out = {
        "_question": "Tail cap or per-trade tuning? Price both on the real-fill book.",
        "replay_day_breaker_391d": rep_rows,
        "replay_baseline_total": round(sum(rep_base.values()), 2),
        "replay_scale_caveat": ("Population B is ONE arm at qty 3. The fleet book runs 5 arms "
                                "at qty 3-8, so a -$600 FLEET cap is roughly a -$120 per-arm "
                                "cap. Compare the replay's -$100/-$120/-$150 rows to the "
                                "book's -$500/-$600 rows, not its -$600 row."),
        "baseline_book_total": base_total,
        "baseline_days": base,
        "causality_note": ("Realized-P&L-at-entry-time only; positions open when the breaker "
                           "trips are NOT force-liquidated. Strictly later-tripping than the "
                           "live equity-based kill switch, so every saving is a FLOOR."),
        "fleet_day_breaker": fleet_rows,
        "per_arm_day_breaker": arm_rows,
        "ORACLE_per_trade_cap": trade_rows,
        "ORACLE_per_trade_cap_LABEL": ("ORACLE -- NOT LIVE-EXECUTABLE. Truncating a realised "
                                       "loss at -$X assumes a fill at a price never proven "
                                       "available. Comparator only; never a shippable number."),
        "positions_per_arm_day_cap": count_rows,
        "entries_per_contract_wave_cap": wave_rows,
    }
    prev = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    prev["q5_which_instrument"] = out
    OUT_JSON.write_text(json.dumps(prev, indent=2), encoding="utf-8")

    def show(rows, title):
        print(f"\n== {title}")
        print(f"{'cell':44s} {'nBlk':>5s} {'total':>9s} {'WED':>9s} {'TUE':>8s} {'THU':>8s} "
              f"{'exWED':>9s} {'harm':>5s}")
        for r in rows:
            print(f"{r['label']:44s} {r['n_positions_blocked']:5d} {r['total_delta']:9.1f} "
                  f"{r['wednesday_delta']:9.1f} {r['tuesday_delta']:8.1f} "
                  f"{r['thursday_delta']:8.1f} {r['delta_ex_wednesday']:9.1f} "
                  f"{r['n_days_harmed']:5d}")
    show(fleet_rows, "FLEET realized-day breaker")
    show(arm_rows, "PER-ARM realized-day breaker")
    show(trade_rows, "ORACLE per-trade cap (comparator only)")
    show(count_rows, "positions per (arm,date)")
    show(wave_rows, "entries per (arm,symbol,date)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
