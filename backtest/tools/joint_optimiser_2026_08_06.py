#!/usr/bin/env python
"""joint_optimiser_2026_08_06.py -- KEEP LOSSES SMALL: the JOINT optimisation.

J's ask (2026-08-06, after the close): "we gotta KEEP OUR LOSSES SMALL so that way our wins
can stack." Wednesday 2026-08-05 lost -$1,935.00 (SPY options only) the day after Tuesday
made +$3,624.00. Five lever lanes each measured ONE instrument in isolation. This runner does
the thing none of them could: it computes what happens when they run TOGETHER.

WHY SUMMING IS WRONG, MECHANICALLY
----------------------------------
The fleet day breaker arms off CUMULATIVE REALIZED P&L. An entry-side lever that blocks a
losing trade removes that loss from the breaker's running total, so the breaker trips LATER
or NEVER -- and every trade the breaker WOULD have blocked is then taken. Benefits therefore
do not add; on Wednesday they can even ANTI-add. The only honest way to price a combination
is to re-walk the whole book SEQUENTIALLY with the combination live.

SEMANTICS (live-faithful, "taken-counted")
------------------------------------------
* One global chronological EVENT stream per ET date, BOTH legs on the SAME clock (ET
  datetimes, never entry-UTC vs exit-ET): exits book before entries at equal timestamps,
  because a broker books realized cash at the sell.
* A BLOCKED position contributes $0, never generates an exit event, never increments ANY
  lever's counter, and never feeds the breaker. That is what the live engine would do.
* No exit is re-walked, no fill re-priced, no capital redeployed. Deletion arithmetic on
  real broker fills is the only counterfactual this composition is entitled to.
* Levers are evaluated in a FIXED order; because a block is a block, the order changes only
  the ATTRIBUTION of a block, never the resulting book. Attribution is reported as such.

POPULATION: 208 real-broker-fill positions, 26 ET dates 2026-06-26..2026-08-06, engine
attribution, SPY options only. Base reproduces +$1,782.01 / Tue +$3,624 / Wed -$1,935 /
Thu +$1,465 -- asserted, not assumed.

THIS RUNNER SHIPS NOTHING AND ARMS NOTHING. Analysis only.

Run: backtest/.venv/Scripts/python.exe backtest/tools/joint_optimiser_2026_08_06.py
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lever_entry_count_2026_08_06 as L4  # noqa: E402

TUE, WED, THU = "2026-08-04", "2026-08-05", "2026-08-06"
WEEK = (TUE, WED, THU)
VWAP = "VWAP_CONTINUATION"
OUT_JSON = REPO / "analysis" / "deep-research" / "KEEP-LOSSES-SMALL-2026-08-06.json"

# The J target, stated as a number so no cell can be talked past it.
J_TARGET_WED = -700.0
HARD_GATE_USD = -0.005          # Tuesday AND Thursday must cost EXACTLY $0.00


# ═══════════════════════════════════════════════════════════════════ LEVERS
# Each lever is (key, human_name, kind, allow_fn, close_fn). `st` is a per-date mutable dict.
#   allow_fn(p, st) -> None (ABSTAIN, cannot judge), True (allow), False (BLOCK)
#   close_fn(p, st) -> called ONLY for positions actually taken, at their exit event.

def _mk_breaker(threshold: float):
    def allow(p, st):
        return not st["fleet_latched"]

    def close(p, st):
        st["fleet_realized"] += p["pnl"]
        if st["fleet_realized"] <= threshold:
            st["fleet_latched"] = True
            st.setdefault("latch_at", p["exit_ts_et"])
    return allow, close


def _mk_consec(n: int):
    def allow(p, st):
        return not st["arm_halted"].get(p["arm"], False)

    def close(p, st):
        a = p["arm"]
        if p["pnl"] < 0:
            st["consec"][a] += 1
            if st["consec"][a] >= n:
                st["arm_halted"][a] = True
        else:
            st["consec"][a] = 0
    return allow, close


def _mk_cap(n: int):
    def allow(p, st):
        return st["wave"][(p["arm"], p["symbol"])] < n

    def close(p, st):
        return None
    return allow, close


def _cap_take(p, st):
    st["wave"][(p["arm"], p["symbol"])] += 1


def _samebar_allow(p, st):
    if p.get("setup") is None or p.get("trigger_bar_et") is None:
        return None                                   # ABSTAIN -- never block on a guess
    return (p["arm"], p["setup"], p["trigger_bar_et"]) not in st["claimed_bar"]


def _samebar_take(p, st):
    if p.get("setup") is not None and p.get("trigger_bar_et") is not None:
        st["claimed_bar"].add((p["arm"], p["setup"], p["trigger_bar_et"]))


def _vd1_allow(p, st):
    b = L4.c6_block(p)          # True = the last closed 5m bar DISAGREES with the trade
    return None if b is None else (not b)


def _vwaponce_allow(p, st):
    if p.get("setup") is None:
        return None
    if p["setup"] != VWAP:
        return True
    return st["vwap_taken"].get(p["arm"], 0) < 1


def _vwaponce_take(p, st):
    if p.get("setup") == VWAP:
        st["vwap_taken"][p["arm"]] = st["vwap_taken"].get(p["arm"], 0) + 1


LEVERS = {
    # key            name                                    allow            on_close       on_take
    "BRK600":  ("FLEET realized day breaker -$600 (latching)", *_mk_breaker(-600.0), None),
    "CONSEC4": ("per-arm halt after 4 consecutive losers",     *_mk_consec(4),       None),
    "CAP3":    ("<=3 entries per (arm,date,contract)",         *_mk_cap(3),          _cap_take),
    "SAMEBAR": ("same-bar cooldown (fleet<->core parity)",     _samebar_allow, None, _samebar_take),
    "VD1":     ("V-d1: last CLOSED 5m bar must agree",         _vd1_allow,     None, None),
    "VWAP1":   ("vwap_continuation once-per-day (DEFECT FIX)", _vwaponce_allow, None, _vwaponce_take),
}
ORDER = ["VWAP1", "VD1", "SAMEBAR", "CAP3", "CONSEC4", "BRK600"]


def _fresh_state():
    return {"fleet_realized": 0.0, "fleet_latched": False,
            "consec": defaultdict(int), "arm_halted": {},
            "wave": defaultdict(int), "claimed_bar": set(), "vwap_taken": {}}


def walk(book: list[dict], active: "tuple[str, ...]") -> dict:
    """SEQUENTIAL joint walk. Returns per-date P&L + the blocked set with attribution."""
    by_date: dict = defaultdict(list)
    for p in book:
        by_date[p["date_et"]].append(p)

    day_pnl: dict = {}
    blocked: list[dict] = []
    latch: dict = {}
    for date in sorted(by_date):
        st = _fresh_state()
        rows = by_date[date]
        events = []
        for p in rows:
            events.append((p["entry_dt"], 1, id(p), "entry", p))
        # exits are injected lazily as positions are taken, so build a live queue instead
        events.sort()
        pending_exits: list = []
        total = 0.0
        ei = 0
        while ei < len(events) or pending_exits:
            nxt_entry = events[ei] if ei < len(events) else None
            pending_exits.sort(key=lambda e: (e[0], e[1]))
            nxt_exit = pending_exits[0] if pending_exits else None
            # exits FIRST at equal-or-earlier timestamps (broker books cash at the sell)
            take_exit = nxt_exit is not None and (
                nxt_entry is None or nxt_exit[0] <= nxt_entry[0])
            if take_exit:
                _, _oid, p = pending_exits.pop(0)
                for k in active:
                    _n, _a, close_fn, _t = LEVERS[k]
                    if close_fn is not None:
                        close_fn(p, st)
                continue
            ei += 1
            p = nxt_entry[4]
            hit = None
            for k in ORDER:
                if k not in active:
                    continue
                allow_fn = LEVERS[k][1]
                verdict = allow_fn(p, st)
                if verdict is False:
                    hit = k
                    break
            if hit is not None:
                blocked.append({**{kk: p.get(kk) for kk in
                                   ("arm", "date_et", "symbol", "setup", "pnl",
                                    "wave_ordinal", "entry_ts_et")},
                                "blocked_by": hit})
                continue
            # TAKEN -- register with every active lever, queue its exit
            for k in active:
                take_fn = LEVERS[k][3]
                if take_fn is not None:
                    take_fn(p, st)
            total += p["pnl"]
            pending_exits.append((p["exit_dt"], id(p), p))
        day_pnl[date] = round(total, 2)
        if st.get("latch_at"):
            latch[date] = st["latch_at"]
    return {"day_pnl": day_pnl, "blocked": blocked, "latch": latch}


def score(base: dict, res: dict, label: str) -> dict:
    cf = res["day_pnl"]
    days = sorted(set(base) | set(cf))
    deltas = {d: round(cf.get(d, 0.0) - base.get(d, 0.0), 2) for d in days}
    harmed = {d: v for d, v in deltas.items() if v < -0.005}
    bl = res["blocked"]
    win = round(sum(b["pnl"] for b in bl if b["pnl"] > 0), 2)
    los = round(-sum(b["pnl"] for b in bl if b["pnl"] < 0), 2)
    tot = round(sum(deltas.values()), 2)
    bind_days = sorted({b["date_et"] for b in bl})
    return {
        "cell": label,
        "delta_total": tot,
        "tue": deltas.get(TUE, 0.0), "wed": deltas.get(WED, 0.0), "thu": deltas.get(THU, 0.0),
        "wed_after": cf.get(WED, 0.0),
        "delta_ex_wed": round(sum(v for d, v in deltas.items() if d != WED), 2),
        "delta_ex_week": round(sum(v for d, v in deltas.items() if d not in WEEK), 2),
        "book_after": round(sum(cf.values()), 2),
        "n_blocked": len(bl),
        "blocked_winner_usd": win, "blocked_loser_usd": los,
        "insurance_ratio": (round(win / los, 3) if los > 0 else None),
        "n_days_harmed": len(harmed),
        "harmed_days": dict(sorted(harmed.items(), key=lambda kv: kv[1])[:6]),
        "bind_days": len(bind_days),
        "bind_freq_pct": round(100.0 * len(bind_days) / len(base), 1),
        "share_benefit_wed_pct": (round(100.0 * deltas.get(WED, 0.0) / tot, 1)
                                  if tot > 0 else None),
        "hits_j_target": cf.get(WED, 0.0) > J_TARGET_WED,
        "tue_thu_free": (deltas.get(TUE, 0.0) >= HARD_GATE_USD
                         and deltas.get(THU, 0.0) >= HARD_GATE_USD),
        "attribution": dict(sorted(
            {k: sum(1 for b in bl if b["blocked_by"] == k) for k in ORDER}.items())),
        "latch_dates": res["latch"],
        "week_blocked": [b for b in bl if b["date_et"] in WEEK],
    }


def main() -> int:
    book = L4.load_book()
    m5 = L4.load_5m()
    dates = sorted({p["date_et"] for p in book})
    m1 = L4.fetch_1m(dates)
    L4.annotate_features(book, m5, m1, L4.levels_by_day())

    base_res = walk(book, ())
    base = base_res["day_pnl"]
    book_total = round(sum(base.values()), 2)

    # ── TRUST GATE: the base must reproduce broker truth before any joint cell is believed
    checks = {
        "book_total": (book_total, 1782.01),
        "n_positions": (len(book), 208),
        "n_dates": (len(base), 26),
        "tue": (base[TUE], 3624.00),
        "wed": (base[WED], -1935.00),
        "thu": (base[THU], 1465.00),
    }
    print("=== TRUST GATE: base vs broker truth ===")
    ok = True
    for k, (got, want) in checks.items():
        good = abs(got - want) < 0.02
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {k:14s} got {got} want {want}")
    if not ok:
        print("BASE DOES NOT RECONCILE -- refusing to report joint cells.")
        return 1

    singles = {k: score(base, walk(book, (k,)), f"SOLO {k}") for k in ORDER}
    print("\n=== SOLO CELLS (must reproduce each lane's published number) ===")
    for k in ORDER:
        r = singles[k]
        print(f"  {k:8s} tot {r['delta_total']:>9.2f} | TUE {r['tue']:>9.2f} | "
              f"WED {r['wed']:>8.2f} -> {r['wed_after']:>9.2f} | THU {r['thu']:>8.2f} | "
              f"exWed {r['delta_ex_wed']:>8.2f} | blk {r['n_blocked']:>3d} | "
              f"harmed {r['n_days_harmed']}")

    # ── PAIRWISE INTERACTION MATRIX (Wednesday and total; joint minus sum-of-solos)
    pairs = {}
    for a, b in itertools.combinations(ORDER, 2):
        j = score(base, walk(book, (a, b)), f"{a}+{b}")
        pairs[f"{a}+{b}"] = {
            "joint_wed": j["wed"], "sum_wed": round(singles[a]["wed"] + singles[b]["wed"], 2),
            "interaction_wed": round(j["wed"] - singles[a]["wed"] - singles[b]["wed"], 2),
            "joint_total": j["delta_total"],
            "sum_total": round(singles[a]["delta_total"] + singles[b]["delta_total"], 2),
            "interaction_total": round(j["delta_total"] - singles[a]["delta_total"]
                                       - singles[b]["delta_total"], 2),
            "tue": j["tue"], "thu": j["thu"], "wed_after": j["wed_after"],
            "n_days_harmed": j["n_days_harmed"],
        }
    print("\n=== PAIRWISE INTERACTION (Wednesday $) -- joint vs naive sum ===")
    for k, v in sorted(pairs.items(), key=lambda kv: kv[1]["interaction_wed"]):
        print(f"  {k:18s} joint {v['joint_wed']:>8.2f}  sum {v['sum_wed']:>8.2f}  "
              f"INTERACTION {v['interaction_wed']:>9.2f}  (TUE {v['tue']:>8.2f})")

    # ── EXHAUSTIVE PACKAGE SEARCH over all 2^6 subsets
    allcells = {}
    for r in range(0, len(ORDER) + 1):
        for combo in itertools.combinations(ORDER, r):
            lbl = "+".join(combo) if combo else "CONTROL"
            allcells[lbl] = score(base, walk(book, combo), lbl)

    feasible = [v for v in allcells.values()
                if v["tue_thu_free"] and v["hits_j_target"] and v["n_days_harmed"] == 0]
    tue_thu_free = [v for v in allcells.values() if v["tue_thu_free"]]
    # BEST Wednesday = LEAST negative. Sort descending on wed_after.
    frontier = sorted(tue_thu_free, key=lambda v: -v["wed_after"])[:12]

    print(f"\n=== PACKAGE SEARCH: {len(allcells)} subsets ===")
    print(f"  Tuesday+Thursday-free cells : {len(tue_thu_free)}")
    print(f"  ... of those, Wed > -$700 AND 0 days harmed : {len(feasible)}")
    print("\n=== BEST-WEDNESDAY FRONTIER among Tue/Thu-free cells ===")
    for v in frontier:
        print(f"  {v['cell']:42s} WED {v['wed_after']:>9.2f} | tot {v['delta_total']:>9.2f} "
              f"| exWed {v['delta_ex_wed']:>8.2f} | harmed {v['n_days_harmed']} "
              f"| ratio {v['insurance_ratio']}")

    # minimal feasible = fewest levers, then best book
    minimal = None
    if feasible:
        minimal = sorted(feasible, key=lambda v: (v["cell"].count("+"), -v["delta_total"]))[0]
        print(f"\n=== MINIMAL FEASIBLE PACKAGE: {minimal['cell']} ===")
        print(json.dumps({k: minimal[k] for k in
                          ("delta_total", "tue", "wed", "thu", "wed_after", "delta_ex_wed",
                           "delta_ex_week", "book_after", "n_blocked", "blocked_winner_usd",
                           "blocked_loser_usd", "insurance_ratio", "n_days_harmed",
                           "bind_days", "bind_freq_pct", "share_benefit_wed_pct",
                           "attribution")}, indent=2))
    else:
        print("\n=== NO FEASIBLE PACKAGE -- reporting the achievable frontier instead ===")
        best = frontier[0]
        print(f"  BEST Tue/Thu-free Wednesday = {best['wed_after']} via {best['cell']}")

    # ══════════════════════════════════════════════════════════════════════════════
    # THE JOINT QUESTION NO ISOLATED LANE COULD ASK.
    # Lane 1 proved -$600 is the tightest FLEET breaker that is Tuesday-safe, because
    # Tuesday's own realized path bottoms at -$363. But that floor was measured with every
    # Tuesday loser present. An entry-side lever that blocks a Tuesday LOSER makes Tuesday's
    # drawdown SHALLOWER -- which may unlock a TIGHTER breaker that trips EARLIER on
    # Wednesday. That is a potentially SUPER-additive interaction, and it is invisible to
    # any study that varies one lever at a time.
    thresholds = [-200.0, -250.0, -300.0, -350.0, -400.0, -450.0, -500.0,
                  -550.0, -600.0, -700.0, -800.0]
    entry_pkgs = [(), ("SAMEBAR",), ("CAP3",), ("SAMEBAR", "CAP3"),
                  ("VD1",), ("VD1", "SAMEBAR"), ("VD1", "SAMEBAR", "CAP3"),
                  ("SAMEBAR", "CAP3", "CONSEC4")]
    sweep = []
    for thr in thresholds:
        LEVERS["BRKX"] = (f"FLEET realized day breaker {thr:.0f} (latching)",
                          *_mk_breaker(thr), None)
        if "BRKX" not in ORDER:
            ORDER.append("BRKX")
        for pkg in entry_pkgs:
            lbl = ("+".join(pkg) + "+" if pkg else "") + f"BRK{abs(int(thr))}"
            r = score(base, walk(book, tuple(pkg) + ("BRKX",)), lbl)
            r["threshold"] = thr
            r["entry_pkg"] = "+".join(pkg) or "(none)"
            sweep.append(r)
    ORDER.remove("BRKX")

    print("\n=== BREAKER-THRESHOLD x ENTRY-PACKAGE SWEEP "
          "(does a shallower Tuesday unlock a tighter breaker?) ===")
    print(f"  {'entry package':26s} {'thr':>6s} {'TUE':>9s} {'WED_after':>10s} "
          f"{'THU':>7s} {'total':>9s} {'exWed':>8s} {'harm':>4s}  gate")
    for r in sweep:
        gate = ("TUE/THU-FREE" if r["tue_thu_free"] else "fails")
        if r["tue_thu_free"] and r["n_days_harmed"] == 0:
            gate += " +0harm"
        star = " <<<" if (r["tue_thu_free"] and r["n_days_harmed"] == 0
                          and r["hits_j_target"]) else ""
        print(f"  {r['entry_pkg']:26s} {r['threshold']:>6.0f} {r['tue']:>9.2f} "
              f"{r['wed_after']:>10.2f} {r['thu']:>7.2f} {r['delta_total']:>9.2f} "
              f"{r['delta_ex_wed']:>8.2f} {r['n_days_harmed']:>4d}  {gate}{star}")

    clean = [r for r in sweep if r["tue_thu_free"] and r["n_days_harmed"] == 0]
    winners = [r for r in clean if r["hits_j_target"]]
    print(f"\n  clean cells (Tue+Thu free, 0 days harmed): {len(clean)}")
    print(f"  ... of those clearing J's Wed > -$700 target : {len(winners)}")
    best_clean = sorted(clean, key=lambda r: -r["wed_after"])[:6]
    print("\n=== BEST CLEAN CELLS IN THE SWEEP ===")
    for r in best_clean:
        print(f"  {r['cell']:38s} WED {r['wed_after']:>9.2f} | tot {r['delta_total']:>9.2f} "
              f"| exWed {r['delta_ex_wed']:>8.2f} | exWeek {r['delta_ex_week']:>8.2f} "
              f"| ratio {r['insurance_ratio']} | bind {r['bind_freq_pct']}%")

    # ── LEAVE-ONE-DAY-OUT on the chosen frontier cell: how much is the motivating day?
    lodo = {}
    for r in best_clean[:3]:
        pkg = tuple(x for x in r["cell"].replace(f"BRK{abs(int(r['threshold']))}", "")
                    .strip("+").split("+") if x)
        LEVERS["BRKX"] = ("sweep", *_mk_breaker(r["threshold"]), None)
        ORDER.append("BRKX")
        w = walk(book, pkg + ("BRKX",))
        ORDER.remove("BRKX")
        d = {k: round(w["day_pnl"].get(k, 0.0) - base.get(k, 0.0), 2) for k in base}
        lodo[r["cell"]] = {
            "total": round(sum(d.values()), 2),
            "ex_wed": round(sum(v for k, v in d.items() if k != WED), 2),
            "n_days_moved": sum(1 for v in d.values() if abs(v) > 0.005),
            "pct_from_wed": (round(100.0 * d.get(WED, 0.0) / sum(d.values()), 1)
                             if sum(d.values()) else None),
            "per_day_nonzero": {k: v for k, v in sorted(d.items()) if abs(v) > 0.005},
        }
    print("\n=== LEAVE-ONE-DAY-OUT / concentration on the best clean cells ===")
    print(json.dumps(lodo, indent=2))

    out = {
        "lens": "JOINT OPTIMISATION -- keep losses small (sequential re-walk, not summation)",
        "threshold_x_package_sweep": sweep,
        "clean_cells": clean,
        "best_clean": best_clean,
        "lodo": lodo,
        "clock_verified_et": "2026-08-06 18:03:30 Thursday EDT, market_hours=False",
        "population": {"positions": len(book), "dates": len(base), "book_total": book_total,
                       "tue": base[TUE], "wed": base[WED], "thu": base[THU]},
        "semantics": ("taken-counted sequential event walk; blocked position contributes $0, "
                      "never increments a counter, never feeds the breaker; exits book before "
                      "entries at equal timestamps"),
        "j_target_wed_usd": J_TARGET_WED,
        "solo_cells": singles,
        "pairwise_interaction": pairs,
        "all_subsets": allcells,
        "n_tue_thu_free": len(tue_thu_free),
        "n_feasible": len(feasible),
        "frontier": frontier,
        "minimal_feasible": minimal,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
