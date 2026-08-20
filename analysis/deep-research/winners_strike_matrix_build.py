"""WINNERS-STRIKE-MATRIX v2 -- adds a FAITHFUL multi-leg exit replay.

v1 sold one block at the final exit timestamp.  Production scaled out (TP1 at one minute,
runner at another), so v1 overstated the as-traded replay by $1,937 across the 77 multi-leg
rows, and that error landed hardest on the ITM cells (bigger dollar moves).  v2 replays
production's ACTUAL exit schedule -- each leg's minute and each leg's share of the position
-- on every alternate strike.  Exit minutes are an input identical across all cells, so no
cell can see anything the others cannot.

Conventions otherwise unchanged from v1 (see that docstring): bar-OPEN pricing at the acting
minute, matched row set across all six cells, cost_model fees + $0.02/contract exit slippage.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

REPO = Path(r"C:/Users/jackw/Desktop/42")
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from trade_matrix_build import load_cached_bars, _parse_et          # noqa: E402
import cost_model                                                    # noqa: E402

OFFSETS = (-2, -1, 0, 1, 2)
LABEL = {-2: "ITM-2", -1: "ITM-1", 0: "ATM", 1: "OTM+1", 2: "OTM+2"}
STOP_PCT, TP_PCT = -0.50, 1.00
SLIP = cost_model.EXIT_SLIPPAGE_CONSERVATIVE_PER_CONTRACT


def alt_symbol(sym, side, spy, n):
    k = round(spy) + (n if side == "C" else -n)
    return sym[:-8] + str(int(round(k * 1000))).zfill(8)


def bar_open_at(bymin, minute, win):
    """OPEN of that exact minute; else the latest bar at or before it (never after)."""
    b = bymin.get(minute)
    if b:
        return b["o"], False
    prior = [x for x in win if x["ts"] <= minute]
    return (prior[-1]["o"], True) if prior else (None, True)


def split_qty(total, fracs):
    """Integer leg quantities honouring production's scale-out fractions; remainder to last."""
    q = [int(math.floor(total * f)) for f in fracs]
    q[-1] += total - sum(q)
    return q


def costed(entry_px, proceeds_premium, qty):
    """proceeds_premium = sum(leg_price * leg_qty) in premium space."""
    gross = (proceeds_premium - entry_px * qty) * 100.0
    fb = cost_model.fee_breakdown({"qty": qty, "entry_premium": entry_px, "real_pnl": gross})
    return gross, gross - fb["fee_total_ex_cat"], gross - fb["fee_total_ex_cat"] - SLIP * 100.0 * qty


def main() -> int:
    d = json.loads((REPO / "analysis/recommendations/trade-matrix.json").read_text())
    cache: dict = {}

    def bars(sym, date):
        k = (sym, date)
        if k not in cache:
            cache[k] = load_cached_bars(sym, date) or []
        return cache[k]

    priced, drops, sched_bad = [], [], 0
    for r in d["rows"]:
        spy, ep, q = r.get("spy_at_entry"), r.get("entry_premium"), r.get("qty")
        if spy is None or not ep or not q:
            drops.append((r["arm"], r["date"], r["symbol"], "missing spy/premium/qty"))
            continue
        e_min = _parse_et(r["entry_ts_et"]).replace(second=0, microsecond=0)
        x_min = _parse_et(r["exit_ts_et"]).replace(second=0, microsecond=0)

        # --- production's real exit schedule -> (minute, fraction of position)
        legs = [l for l in (r.get("exit_legs") or []) if l.get("qty")]
        lq = sum(int(l["qty"]) for l in legs)
        if legs and lq == int(q):
            sched = [(_parse_et(l["ts_et"]).replace(second=0, microsecond=0), int(l["qty"]) / q)
                     for l in legs]
        else:
            if legs:
                sched_bad += 1                      # leg qty disagrees with round-trip qty
            sched = [(x_min, 1.0)]
        sched.sort(key=lambda t: t[0])
        last_min = max(x_min, sched[-1][0])

        plan = [("AS_TRADED", r["symbol"])]
        plan += [(LABEL[n], alt_symbol(r["symbol"], r["side"], spy, n)) for n in OFFSETS]
        cells, bad = {}, None
        for key, sym in plan:
            bb = bars(sym, r["date"])
            win = [b for b in bb if e_min <= b["ts"] <= last_min]
            if not win or win[0]["ts"] != e_min:
                bad = key + ":" + sym + " no bar at entry minute"
                break
            cells[key] = {"symbol": sym, "entry_px": win[0]["o"], "win": win,
                          "bymin": {b["ts"]: b for b in win}}
        if bad:
            drops.append((r["arm"], r["date"], r["symbol"], bad))
            continue

        budget = ep * 100.0 * q
        for key, c in cells.items():
            e, win, bymin = c["entry_px"], c["win"], c["bymin"]
            q1, q2 = int(q), max(1, int(math.floor(budget / (e * 100.0))))
            fracs = [f for _, f in sched]
            stale = False
            out = {}
            for si, qty in (("s1", q1), ("s2", q2)):
                lq_ = split_qty(qty, fracs)
                proceeds = 0.0
                for (mn, _f), lqty in zip(sched, lq_):
                    px, st_ = bar_open_at(bymin, mn, win)
                    stale = stale or st_
                    proceeds += px * lqty
                g, n_, nc = costed(e, proceeds, qty)
                out[si + "_e1_gross"], out[si + "_e1_net"], out[si + "_e1_netcost"] = g, n_, nc
                if si == "s1":
                    out["exit_vwap_e1"] = proceeds / qty
            # E2: policy replay, single block (a policy counterfactual, not a prod replay)
            stop, targ = e * (1 + STOP_PCT), e * (1 + TP_PCT)
            x2, why = None, "clock"
            for b in win[1:]:
                if b["l"] <= stop:
                    x2, why = stop, "stop"
                    break
                if b["h"] >= targ:
                    x2, why = targ, "target"
                    break
            if x2 is None:
                x2, _ = bar_open_at(bymin, last_min, win)
            for si, qty in (("s1", q1), ("s2", q2)):
                g, n_, nc = costed(e, x2 * qty, qty)
                out[si + "_e2_gross"], out[si + "_e2_net"], out[si + "_e2_netcost"] = g, n_, nc
            out.update(symbol=c["symbol"], entry_px=e, qty_s1=q1, qty_s2=q2,
                       stale_exit_bar=stale, e2_reason=why, exit_e2=x2,
                       pct_e1=(out["exit_vwap_e1"] - e) / e, pct_e2=(x2 - e) / e,
                       dollars_per_ctr_e1=(out["exit_vwap_e1"] - e) * 100.0,
                       dollars_per_ctr_e2=(x2 - e) * 100.0)
            cells[key] = out
        priced.append({"r": r, "cells": cells, "n_sched_legs": len(sched)})

    keep = ["arm", "date", "symbol", "side", "moneyness_n", "qty", "entry_premium",
            "real_pnl_gross", "real_pnl_net", "is_winner_gross", "n_exit_legs",
            "hold_minutes", "exit_stage", "setup", "entry_ts_et", "exit_ts_et",
            "minutes_since_open", "vix", "quality_tier"]
    out = {"rows_in": len(d["rows"]), "rows_priced": len(priced), "rows_dropped": len(drops),
           "leg_schedule_mismatches": sched_bad, "conventions": __doc__,
           "drops": [{"arm": a, "date": t, "symbol": s, "why": w} for a, t, s, w in drops],
           "priced": [dict({k: p["r"].get(k) for k in keep}, cells=p["cells"],
                           n_sched_legs=p["n_sched_legs"]) for p in priced]}
    o = REPO / "analysis/deep-research/WINNERS-STRIKE-MATRIX-2026-08-19-cells.json"
    o.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("priced " + str(len(priced)) + "/" + str(len(d["rows"])) + " dropped " + str(len(drops)))
    print("leg-schedule mismatches (fell back to single block): " + str(sched_bad))
    print("stale-minute substitutions: " +
          str(sum(1 for p in priced for c in p["cells"].values() if c["stale_exit_bar"])) +
          " of " + str(len(priced) * 6) + " cells")
    real = sum(p["r"]["real_pnl_gross"] for p in priced)
    sim = sum(p["cells"]["AS_TRADED"]["s1_e1_gross"] for p in priced)
    print(f"SIM GATE  as-traded replay ${sim:,.0f}  vs real ${real:,.0f}  err ${sim-real:+,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
