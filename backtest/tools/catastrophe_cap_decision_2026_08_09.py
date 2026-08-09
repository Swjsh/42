"""Decision study for prereg CATASTROPHE-CAP-DECISION-2026-08-09.

The CATASTROPHE-CAP-WIDEN-WATCH accrual reached its own pre-registered bar tonight
(n_fires=13 >= decision_n=10). The 2026-07-23 shakeout study that opened the watch forbade
deciding on its n=4 sample and demanded exactly this. Prereg frozen BEFORE this file existed.

Four arms over the 13 REAL catastrophe-cap fires:
  CONTROL             the shipped -50% cap  (each fire's recorded actual_realized_pnl)
  CAP_60 / CAP_70     wider caps, priced by walking real OPRA 1-min bars from entry
  NO_CAP_HOLD_TO_EOD  cap removed           (each fire's recorded held_to_eod_counterfactual)

Pricing note that matters: a widened cap fills AT the cap level, never at the bar low. Using
the low would flatter every wider arm by the size of the wick that triggered it -- the exact
kind of accounting illusion this program has been burned by before.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "backtest" / "tools"),
           str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LEDGER = REPO / "analysis" / "recommendations" / "catastrophe-cap-shadow-ledger.jsonl"
PREREG = REPO / "analysis" / "recommendations" / "prereg-catastrophe-cap-decision-2026-08-09.json"
OUT = REPO / "analysis" / "recommendations" / "catastrophe-cap-decision-2026-08-09.json"

CAPS = {"CAP_60": -0.60, "CAP_70": -0.70}
MULT = 100.0


def _rows() -> list[dict]:
    return [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]


def _price_wider(row: dict, cap: float) -> dict:
    """Walk real OPRA 1-min bars from the fire's entry; the wider cap fires at the FIRST bar
    whose low breaches entry*(1+cap), filled AT the cap price. Never breached -> ride to the
    last RTH bar (same terminal treatment as the hold-to-EOD arm)."""
    from exit_shape_parity_study import fetch_option_bars
    bars = fetch_option_bars(row["symbol"], row["date_et"])
    if not bars:
        return {"ok": False, "reason": "no_opra_bars"}
    entry = float(row["entry_price"])
    qty = float(row["qty"])
    cap_px = round(entry * (1.0 + cap), 4)
    entry_ts = dt.datetime.fromisoformat(row["entry_ts_utc"].replace("Z", "+00:00"))
    after = []
    for b in bars:
        ts = b.get("t") or b.get("timestamp")
        if isinstance(ts, str):
            ts = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts is not None and ts >= entry_ts:
            after.append((ts, b))
    if not after:
        return {"ok": False, "reason": "no_bars_after_entry"}
    for ts, b in after:
        low = float(b.get("l", b.get("low")))
        if low <= cap_px:
            return {"ok": True, "exit_price": cap_px, "exit_ts": ts.isoformat(),
                    "fired": True, "pnl": round((cap_px - entry) * qty * MULT, 2)}
    last = float(after[-1][1].get("c", after[-1][1].get("close")))
    return {"ok": True, "exit_price": last, "exit_ts": after[-1][0].isoformat(),
            "fired": False, "pnl": round((last - entry) * qty * MULT, 2)}


def main() -> int:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    rows = _rows()
    print(f"[cap-decision] prereg {prereg['prereg_id']}, {len(rows)} real fires", flush=True)

    per_fire, excluded = [], []
    for r in rows:
        rec = {"date_et": r["date_et"], "arm": r["arm"], "symbol": r["symbol"],
               "qty": r["qty"], "entry_price": r["entry_price"],
               "CONTROL": float(r["actual_realized_pnl"]),
               "NO_CAP_HOLD_TO_EOD": float(r["held_to_eod_counterfactual_pnl"])}
        for name, cap in CAPS.items():
            got = _price_wider(r, cap)
            if not got.get("ok"):
                rec[name] = None
                excluded.append({"symbol": r["symbol"], "arm": name, "reason": got.get("reason")})
            else:
                rec[name] = got["pnl"]
                rec[f"_{name}_fired"] = got["fired"]
        per_fire.append(rec)
        print(f"  {r['date_et']} {r['arm']:8s} ctl={rec['CONTROL']:>9.2f} "
              f"c60={rec.get('CAP_60')} c70={rec.get('CAP_70')} "
              f"eod={rec['NO_CAP_HOLD_TO_EOD']:>9.2f}", flush=True)

    arms = ["CONTROL", "CAP_60", "CAP_70", "NO_CAP_HOLD_TO_EOD"]
    scored = {}
    ctl_by_key = {(f["date_et"], f["symbol"], f["arm"]): f["CONTROL"] for f in per_fire}
    for a in arms:
        vals = [(f, f.get(a)) for f in per_fire if f.get(a) is not None]
        n = len(vals)
        total = round(sum(v for _f, v in vals), 2)
        beats = [f for f, v in vals if v > ctl_by_key[(f["date_et"], f["symbol"], f["arm"])]]
        gains = [(v - ctl_by_key[(f["date_et"], f["symbol"], f["arm"])]) for f, v in vals]
        best_i = gains.index(max(gains)) if gains else None
        drop_best_total = round(total - vals[best_i][1], 2) if best_i is not None else None
        ctl_drop_best = round(
            sum(ctl_by_key[(f["date_et"], f["symbol"], f["arm"])] for f, _v in vals)
            - ctl_by_key[(vals[best_i][0]["date_et"], vals[best_i][0]["symbol"],
                          vals[best_i][0]["arm"])], 2) if best_i is not None else None
        scored[a] = {
            "n": n, "total": total,
            "n_beats_control": len(beats),
            "majority_of_fires": len(beats) > n / 2,
            "worst_single_fire": round(min((v for _f, v in vals), default=0.0), 2),
            "drop_best_total": drop_best_total,
            "drop_best_still_beats_control": (
                None if drop_best_total is None else drop_best_total > ctl_drop_best),
        }

    ctl = scored["CONTROL"]
    verdict = {"control_total": ctl["total"], "control_worst_fire": ctl["worst_single_fire"],
               "arms": {}}
    for a in arms:
        if a == "CONTROL":
            continue
        s = scored[a]
        g_agg = s["total"] > ctl["total"]
        g_maj = s["majority_of_fires"]
        g_drop = bool(s["drop_best_still_beats_control"])
        g_tail = s["worst_single_fire"] >= ctl["worst_single_fire"]
        verdict["arms"][a] = {
            "G_AGGREGATE": g_agg, "G_MAJORITY": g_maj,
            "G_DROP_BEST": g_drop, "G_TAIL": g_tail,
            "all_gates": bool(g_agg and g_maj and g_drop and g_tail),
            "delta_vs_control": round(s["total"] - ctl["total"], 2),
        }
    survivors = [a for a, v in verdict["arms"].items() if v["all_gates"]]
    verdict["survivors"] = survivors
    verdict["headline"] = (
        "CAP VALIDATED BY FORWARD FIRES -- no width beats the shipped -50% on all four "
        "pre-registered gates." if not survivors else
        f"{survivors} clear all four gates -- propose a pre-registered FORWARD trial on ONE "
        f"arm; this does not itself flip the cap (n=13, rare-tail).")
    verdict["ships_tonight"] = False

    OUT.write_text(json.dumps({"prereg_id": prereg["prereg_id"], "per_fire": per_fire,
                               "scored": scored, "verdict": verdict, "excluded": excluded},
                              indent=1, default=str), encoding="utf-8")
    print("\n" + json.dumps({"scored": scored, "verdict": verdict}, indent=1)[:2200])
    print(f"[cap-decision] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
