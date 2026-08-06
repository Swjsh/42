#!/usr/bin/env python
"""lever_daily_cap_headroom_2026_08_06.py -- LEVER 1, robustness half.

The coarse grid (lever_daily_cap_2026_08_06.py) finds a best cell. This module asks the only
question that decides whether that cell is a real instrument or a curve-fit:

  IS THE THRESHOLD ON A PLATEAU, OR ON A CLIFF?

A threshold picked at a cliff found in a 26-date sample is the classic shape that does not
generalise. So:
  1. FINE SWEEP -- every $25 from -$50 to -$2,500, fleet + per-arm, on the book; and every $10
     from -$25 to -$1,000 on the 391-day replay. Plot the total-delta curve and the
     Tuesday-cost curve as text so a reader can SEE plateau vs spike.
  2. HEADROOM -- per date, the minimum fleet (and per-arm) running realized P&L, and the P&L of
     every entry taken AFTER that minimum. That is exactly the money a breaker at any level
     below the minimum would forfeit. It names the day that sets the cliff.
  3. LEAVE-ONE-DAY-OUT -- for the surviving candidate cells, recompute total delta with each
     date removed in turn. Reports the full range, so "100% of the benefit is one day" is
     stated as a measured number, not an impression.
  4. CONSEC-N decomposition -- which dates supply the consecutive-loss lever's ex-Wednesday
     money, since that is the only surviving cell in the frozen grid that has any.

DESCRIPTIVE ONLY. Reads the same real broker fills; writes into the LEVER-DAILY-CAP json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lever_daily_cap_2026_08_06 as L  # noqa: E402

OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-DAILY-CAP-2026-08-06.json"
TUE, WED, THU = L.TUE, L.WED, L.THU


# ------------------------------------------------------------------ headroom
def headroom(book: list[dict], per_arm: bool) -> list[dict]:
    """Per scope: the minimum running realized P&L reached, and the P&L of entries taken after
    it. A breaker set anywhere ABOVE that minimum (i.e. tighter than |min|) would have armed on
    that scope; what it forfeits is `pnl_after_min`."""
    by_scope: dict = defaultdict(list)
    for p in book:
        by_scope[(p["arm"], p["date_et"]) if per_arm else (p["date_et"],)].append(p)
    rows = []
    for scope, grp in sorted(by_scope.items()):
        entries = sorted(grp, key=lambda p: p["entry_ts_utc"])
        closes = sorted(grp, key=lambda p: p["close_ts"])
        run, min_run, min_ts = 0.0, 0.0, None
        for q in closes:
            run += q["pnl"]
            if run < min_run:
                min_run, min_ts = run, q["close_ts"]
        after = [p for p in entries if min_ts and p["entry_ts_utc"] > min_ts]
        rows.append({
            "scope": "|".join(scope),
            "date": scope[-1],
            "n_positions": len(grp),
            "day_pnl": round(sum(p["pnl"] for p in grp), 2),
            "min_running_realized": round(min_run, 2),
            "min_reached_at_utc": min_ts,
            "n_entries_after_min": len(after),
            "pnl_of_entries_after_min": round(sum(p["pnl"] for p in after), 2),
        })
    return sorted(rows, key=lambda r: r["min_running_realized"])


# ------------------------------------------------------------------ fine sweep
def sweep(book: list[dict], base: dict, per_arm: bool, caps: list[float]) -> list[dict]:
    scope_of = ((lambda p: (p["arm"], p["date_et"])) if per_arm
                else (lambda p: (p["date_et"],)))
    out = []
    for c in caps:
        res = L.simulate(book, scope_of, lambda s, g, c=c: L.DollarCap(c))
        cf = L.day_totals(res["kept"])
        deltas = {d: round(cf.get(d, 0.0) - base.get(d, 0.0), 2) for d in set(base) | set(cf)}
        harmed = {d: v for d, v in deltas.items() if v < -0.005}
        blk = res["blocked"]
        up = sum(p["pnl"] for p in blk if p["pnl"] > 0)
        prev = sum(-p["pnl"] for p in blk if p["pnl"] < 0)
        out.append({
            "cap": -c,
            "total_delta": round(sum(deltas.values()), 2),
            "wed": deltas.get(WED, 0.0), "tue": deltas.get(TUE, 0.0), "thu": deltas.get(THU, 0.0),
            "ex_wed": round(sum(v for d, v in deltas.items() if d != WED), 2),
            "n_blocked": len(blk), "n_harmed": len(harmed),
            "worst_harm": round(min(harmed.values()), 2) if harmed else 0.0,
            "insurance_cost_ratio": round(up / prev, 4) if prev > 0 else None,
        })
    return out


def sweep_replay(trades: list[dict], base: dict, caps: list[float]) -> list[dict]:
    out = []
    for c in caps:
        res = L.replay_sim(trades, lambda c=c: L.DollarCap(c))
        cf = L.day_totals(res["kept"])
        deltas = {d: round(cf.get(d, 0.0) - base.get(d, 0.0), 2) for d in set(base) | set(cf)}
        harmed = {d: v for d, v in deltas.items() if v < -0.005}
        out.append({"cap": -c, "total_delta": round(sum(deltas.values()), 2),
                    "n_blocked": len(res["blocked"]), "n_harmed": len(harmed),
                    "n_helped": sum(1 for v in deltas.values() if v > 0.005),
                    "worst_harm": round(min(harmed.values()), 2) if harmed else 0.0,
                    "bind_rate_days": round(len(res["armed_days"]) / len(base), 4)})
    return out


# ------------------------------------------------------------------ leave-one-day-out
def lodo(book: list[dict], make_rule, scope_of) -> dict:
    """Recompute total delta with each ET date removed in turn."""
    dates = sorted({p["date_et"] for p in book})
    full_res = L.simulate(book, scope_of, make_rule)
    full = round(sum(L.day_totals(full_res["kept"]).values())
                 - sum(L.day_totals(book).values()), 2)
    per_date_delta = {}
    for d in dates:
        sub = [p for p in book if p["date_et"] != d]
        r = L.simulate(sub, scope_of, make_rule)
        per_date_delta[d] = round(
            sum(L.day_totals(r["kept"]).values()) - sum(L.day_totals(sub).values()), 2)
    vals = list(per_date_delta.values())
    worst_date = min(per_date_delta, key=lambda k: per_date_delta[k])
    return {
        "full_sample_total_delta": full,
        "lodo_min": round(min(vals), 2), "lodo_max": round(max(vals), 2),
        "lodo_most_load_bearing_date": worst_date,
        "lodo_total_without_that_date": per_date_delta[worst_date],
        "lodo_share_from_that_date": (round(1 - per_date_delta[worst_date] / full, 4)
                                      if full else None),
        "n_dates_where_removal_leaves_positive": sum(1 for v in vals if v > 0),
        "per_date_total_delta_when_removed": per_date_delta,
    }


def main() -> int:
    book = L.load_book()
    base = L.day_totals(book)
    trades, _ = L.load_replay()
    rep_base = L.day_totals(trades)

    out: dict = {}

    # ---------------- 1. FINE SWEEP
    caps = [c for c in range(50, 2501, 25)]
    fleet_sw = sweep(book, base, per_arm=False, caps=caps)
    arm_sw = sweep(book, base, per_arm=True, caps=caps)
    rep_sw = sweep_replay(trades, rep_base, [c for c in range(25, 1001, 25)])
    out["fine_sweep_fleet_book"] = fleet_sw
    out["fine_sweep_per_arm_book"] = arm_sw
    out["fine_sweep_replay_391d"] = rep_sw

    def plateau(rows, key="total_delta", gate=lambda r: r["tue"] >= -0.005 and r["n_harmed"] == 0):
        ok = [r for r in rows if gate(r)]
        if not ok:
            return None
        best = max(ok, key=lambda r: r[key])
        # the contiguous run of caps around `best` that keep >=90% of best and stay gate-clean
        idx = rows.index(best)
        lo = hi = idx
        thr = 0.90 * best[key]
        while lo - 1 >= 0 and gate(rows[lo - 1]) and rows[lo - 1][key] >= thr:
            lo -= 1
        while hi + 1 < len(rows) and gate(rows[hi + 1]) and rows[hi + 1][key] >= thr:
            hi += 1
        return {"best_cap": best["cap"], "best_total_delta": best[key],
                "plateau_lo_cap": rows[lo]["cap"], "plateau_hi_cap": rows[hi]["cap"],
                "plateau_width_dollars": abs(rows[hi]["cap"] - rows[lo]["cap"]),
                "plateau_n_cells": hi - lo + 1,
                "criterion": "contiguous caps holding >=90% of best AND tuesday>=0 AND 0 harmed"}

    out["plateau_fleet_book"] = plateau(fleet_sw)
    out["plateau_per_arm_book"] = plateau(arm_sw)
    out["plateau_replay"] = plateau(
        rep_sw, gate=lambda r: r["n_harmed"] == 0)

    # ---------------- 2. HEADROOM
    out["headroom_fleet_by_date"] = headroom(book, per_arm=False)
    out["headroom_per_arm_worst20"] = headroom(book, per_arm=True)[:20]

    # ---------------- 3. LODO on the surviving candidates
    out["lodo"] = {
        "FLEET_-600": lodo(book, lambda s, g: L.DollarCap(600), lambda p: (p["date_et"],)),
        "PER_ARM_-600": lodo(book, lambda s, g: L.DollarCap(600),
                             lambda p: (p["arm"], p["date_et"])),
        "PER_ARM_CONSEC_4": lodo(book, lambda s, g: L.ConsecLoss(4),
                                 lambda p: (p["arm"], p["date_et"])),
        "PER_ARM_CONSEC_5": lodo(book, lambda s, g: L.ConsecLoss(5),
                                 lambda p: (p["arm"], p["date_et"])),
    }

    # ---------------- 4. CONSEC-N per-date decomposition
    con: dict = {}
    for n in (3, 4, 5):
        res = L.simulate(book, lambda p: (p["arm"], p["date_et"]),
                         lambda s, g, n=n: L.ConsecLoss(n))
        by_date: dict = defaultdict(lambda: {"n_blocked": 0, "pnl_blocked": 0.0, "arms": set()})
        for p in res["blocked"]:
            e = by_date[p["date_et"]]
            e["n_blocked"] += 1
            e["pnl_blocked"] += p["pnl"]
            e["arms"].add(p["arm"])
        con[f"consec_{n}"] = {
            d: {"n_blocked": v["n_blocked"], "delta": round(-v["pnl_blocked"], 2),
                "arms": sorted(v["arms"])}
            for d, v in sorted(by_date.items())}
    out["consec_per_date_decomposition"] = con

    # ---------------- write + print
    prev = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    prev["robustness"] = out
    OUT_JSON.write_text(json.dumps(prev, indent=2), encoding="utf-8")
    print(f"[headroom] wrote {OUT_JSON}")

    print("\n== FLEET fine sweep on the 26-date book (every $25) -- gate-clean rows only")
    print(f"{'cap':>7s} {'total':>9s} {'WED':>9s} {'TUE':>9s} {'exWED':>8s} {'nBlk':>5s} "
          f"{'harm':>5s} {'ratio':>7s}")
    for r in fleet_sw:
        if r["cap"] % 100 == 0 or (-800 <= r["cap"] <= -300):
            flag = "" if (r["tue"] >= -0.005 and r["n_harmed"] == 0) else "  X"
            ratio = "n/a" if r["insurance_cost_ratio"] is None else f"{r['insurance_cost_ratio']:.2f}"
            print(f"{r['cap']:7.0f} {r['total_delta']:9.2f} {r['wed']:9.2f} {r['tue']:9.2f} "
                  f"{r['ex_wed']:8.2f} {r['n_blocked']:5d} {r['n_harmed']:5d} {ratio:>7s}{flag}")
    print("\nPLATEAU fleet:", json.dumps(out["plateau_fleet_book"]))
    print("PLATEAU per-arm:", json.dumps(out["plateau_per_arm_book"]))
    print("PLATEAU replay:", json.dumps(out["plateau_replay"]))

    print("\n== HEADROOM -- fleet running-realized minimum, per date (10 deepest)")
    print(f"{'date':12s} {'nPos':>4s} {'dayPnL':>10s} {'minRealized':>12s} {'nAfterMin':>10s} "
          f"{'pnlAfterMin':>12s}")
    for r in out["headroom_fleet_by_date"][:10]:
        print(f"{r['date']:12s} {r['n_positions']:4d} {r['day_pnl']:10.2f} "
              f"{r['min_running_realized']:12.2f} {r['n_entries_after_min']:10d} "
              f"{r['pnl_of_entries_after_min']:12.2f}")

    print("\n== LODO (leave-one-date-out) on the surviving candidates")
    for k, v in out["lodo"].items():
        print(f"{k:18s} full {v['full_sample_total_delta']:9.2f} | "
              f"most load-bearing date {v['lodo_most_load_bearing_date']} -> "
              f"{v['lodo_total_without_that_date']:9.2f} "
              f"({(v['lodo_share_from_that_date'] or 0)*100:.1f}% of benefit) | "
              f"range [{v['lodo_min']:.2f}, {v['lodo_max']:.2f}]")

    print("\n== CONSEC-N per-date decomposition")
    for n, dd in out["consec_per_date_decomposition"].items():
        tot = round(sum(v["delta"] for v in dd.values()), 2)
        print(f"  {n}: total {tot:+.2f}")
        for d, v in dd.items():
            print(f"      {d}  delta {v['delta']:+9.2f}  blocked {v['n_blocked']:2d}  "
                  f"arms {','.join(v['arms'])}")

    print("\n== REPLAY fine sweep (391-day, one arm) -- every $50")
    print(f"{'cap':>7s} {'total':>9s} {'nBlk':>5s} {'harm':>5s} {'help':>5s} {'bind':>7s}")
    for r in rep_sw:
        if r["cap"] % 50 == 0:
            print(f"{r['cap']:7.0f} {r['total_delta']:9.2f} {r['n_blocked']:5d} "
                  f"{r['n_harmed']:5d} {r['n_helped']:5d} {r['bind_rate_days']*100:6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
