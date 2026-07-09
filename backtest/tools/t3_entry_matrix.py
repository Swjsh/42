"""t3_entry_matrix.py -- T3 (SWARM A), HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.

J's central hypothesis, priced HONESTLY: does entering at a LIMIT below the signal premium
(passive-wick entry) beat paying up at market -- NET of the winners a passive limit MISSES?
"Entry offset IS stop headroom" (the 741P exhibit: market@0.96 -> limit@0.77 turned -$57 into
+$231). A limit fill at signal*(1-delta) automatically pushes the SAME stop delta% further from
the signal, for free -- but only when the bar dips to fill it; otherwise you miss (and forgo the
move). The metric that adjudicates: per-signal expectancy INCLUDING misses (miss = $0), reported
alongside the forgone P&L (the winners skipped). A passive entry only wins if it beats market NET.

Reuses the signal cache + the replay engine (t4_exit_matrix) so entries and exits are consistent.

DISCLOSURES (ground rule 9): FRICTIONLESS -- market/mid/ask collapse to the signal bar OPEN (no
spread modelled), so the ONLY entry differentiator tested is the LIMIT-BELOW offset (delta) + its
fill/miss accounting; a real spread would tax market MORE than limit, so this is CONSERVATIVE for
the passive hypothesis. Limit fills = a bar low <= L-$0.01 within `patience` 5-min bars (touch !=
fill). 5-min bars (1m intrabar fill timing not resolved). Premium floor = signal-admission on the
MARKET reference premium (same eligible set for market vs limit, fair comparison). qty 10, ribbon_ride
only (vwap owed). Exits held FIXED at 3 shapes (control + a T4 ride leader + a mid scalp).

Writes analysis/recommendations/entry-exit-matrix-t3-entries.json + .md. Exploratory -- NOTHING
ships (STOP A). $0, local cache, no network.

Run: backtest/.venv/Scripts/python.exe backtest/tools/t3_entry_matrix.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

from _signal_cache import load_or_build_signals  # noqa: E402
import t4_exit_matrix as t4  # noqa: E402  (reuse replay, band_of, battery, _load_bars)

OUT_JSON = REPO / "analysis" / "recommendations" / "entry-exit-matrix-t3-entries.json"
OUT_MD = REPO / "analysis" / "recommendations" / "entry-exit-matrix-t3-entries.md"

QTY = t4.QTY

# Fixed exit shapes (control + T4 leader "ride" + a mid "scalp"). time_stop 15:40.
EXITS = {
    "control(-20/+150/sell80/fixed)": {
        "premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "fixed", "trail_pct": 0.0, "runner_target_pct": 2.5},
    "ride(none/+150/sell66/trail15)": {
        "premium_stop_pct": -0.95, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9},
    "scalp(-35/+50/sell80/trail15)": {
        "premium_stop_pct": -0.35, "tp1_premium_pct": 0.5, "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 2.5},
}
TIME_STOP = dt.time(15, 40)

DELTAS = [0.05, 0.10, 0.15, 0.20, 0.25]     # limit at signal*(1-delta)
PATIENCE = [1, 3, 5, 10]                     # 5-min bars to wait for the limit
MISS = ["cancel", "convert"]                 # unfilled: miss ($0) vs convert-to-market at window end
FLOORS = [0.0, 0.20, 0.30, 0.50]             # min entry premium (signal-admission)


def entry_fill(bars, signal_premium: float, policy: dict) -> dict | None:
    """Resolve the entry for one policy. Returns {entry, fill_idx, converted} or None (missed)."""
    if policy["type"] == "market":
        return {"entry": signal_premium, "fill_idx": 0, "converted": False}
    L = signal_premium * (1.0 - policy["delta"])
    pat = min(policy["patience"], len(bars))
    for i in range(pat):
        if bars[i][3] <= L - 0.01:            # bars[i] = (time,o,h,l,c); [3]=low
            return {"entry": round(L, 4), "fill_idx": i, "converted": False}
    if policy["miss"] == "convert":
        j = min(pat, len(bars) - 1)
        return {"entry": bars[j][1], "fill_idx": j, "converted": True}  # market at window end (open)
    return None                               # cancel -> miss


def eval_policy(prepared: list, policy: dict, exit_shape: dict, floor: float) -> dict:
    """One (policy, exit, floor) cell over all signals. Eligible = market signal premium >= floor
    (same denominator for market vs limit). Returns fill/miss accounting + battery."""
    filled_trades, forgone = [], []
    eligible = 0
    for p in prepared:
        if p["entry_premium"] < floor:         # floor = signal admission on the MARKET reference
            continue
        eligible += 1
        f = entry_fill(p["bars"], p["entry_premium"], policy)
        if f is None:                          # missed (limit cancel)
            # forgone = what market entry would have made under this exit (the winner you skipped)
            mr = t4.replay(p["entry_premium"], p["bars"], p["side"], exit_shape, TIME_STOP)
            forgone.append({"date": p["date"], "pnl": mr["pnl"]})
            filled_trades.append({"date": p["date"], "direction": p["direction"],
                                  "band": p["band"], "pnl": 0.0, "missed": True})
            continue
        sub = p["bars"][f["fill_idx"]:]
        r = t4.replay(f["entry"], sub, p["side"], exit_shape, TIME_STOP)
        filled_trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                              "pnl": r["pnl"], "missed": False, "converted": f["converted"]})
    n_miss = sum(1 for t in filled_trades if t.get("missed"))
    n_fill = eligible - n_miss
    b = t4.battery(filled_trades)              # expectancy INCLUDING misses ($0)
    filled_only = [t for t in filled_trades if not t.get("missed")]
    fb = t4.battery(filled_only) if filled_only else {"expectancy": 0, "wr": 0}
    return {
        "eligible_n": eligible, "n_filled": n_fill, "n_missed": n_miss,
        "fill_rate": round(n_fill / eligible, 3) if eligible else 0.0,
        "exp_incl_misses": b.get("expectancy", 0), "wr_incl_misses": b.get("wr", 0),
        "exp_filled_only": fb.get("expectancy", 0), "wr_filled_only": fb.get("wr", 0),
        "exp_drop_top3": b.get("exp_drop_top3", 0),
        "forgone_total": round(sum(x["pnl"] for x in forgone), 2),
        "forgone_mean_per_miss": round(sum(x["pnl"] for x in forgone) / n_miss, 2) if n_miss else 0.0,
        "by_band": {bd[0]: (lambda ts: {"n": len(ts), "exp": round(sum(x["pnl"] for x in ts)/len(ts), 2)} if ts else {"n": 0})(
            [t for t in filled_trades if t["band"] == bd[0]]) for bd in t4.BANDS},
        "total_incl_misses": b.get("total", 0),
    }


def _policies() -> list[dict]:
    pol = [{"type": "market", "label": "market(pay-up ctl)"}]
    for d in DELTAS:
        for pat in PATIENCE:
            for m in MISS:
                pol.append({"type": "limit", "delta": d, "patience": pat, "miss": m,
                            "label": f"limit-{int(d*100)}%/pat{pat}/{m}"})
    return pol


def main() -> int:
    data = load_or_build_signals()
    signals = data["signals"] if isinstance(data, dict) else data
    prepared = []
    for s in signals:
        bars = t4._load_bars(s)
        if not bars:
            continue
        ep = bars[0][1]
        if ep <= 0:
            continue
        prepared.append({"date": dt.date.fromisoformat(s["date"]), "direction": s["direction"],
                         "side": s["side"], "entry_premium": ep, "band": t4.band_of(ep), "bars": bars})
    print(f"[t3] {len(prepared)} prepared signals", flush=True)

    policies = _policies()
    out = {"n_signals": len(prepared), "qty": QTY, "time_stop": "15:40",
           "disclosures": ["frictionless (market/mid/ask = signal bar open; only limit-below tested)",
                           "limit fills = bar low <= L-0.01 within patience; 5-min bars",
                           "floor = signal-admission on market ref (fair market-vs-limit denom)",
                           "qty 10, ribbon_ride only (vwap owed)", "exits FIXED at 3 shapes"],
           "exits": {}}
    for exit_name, exit_shape in EXITS.items():
        floor_blocks = {}
        for floor in FLOORS:
            cells = []
            for pol in policies:
                r = eval_policy(prepared, pol, exit_shape, floor)
                r["policy"] = pol["label"]
                cells.append(r)
            market = next(c for c in cells if c["policy"] == "market(pay-up ctl)")
            for c in cells:
                c["net_vs_market"] = round(c["exp_incl_misses"] - market["exp_incl_misses"], 2)
            cells.sort(key=lambda c: c["exp_incl_misses"], reverse=True)
            floor_blocks[f"floor_{floor}"] = {"market": market, "cells": cells}
        out["exits"][exit_name] = floor_blocks
        best = max((c for fb in floor_blocks.values() for c in fb["cells"]),
                   key=lambda c: c["exp_incl_misses"])
        m0 = floor_blocks["floor_0.0"]["market"]
        print(f"[t3] {exit_name}: market(no floor) exp=${m0['exp_incl_misses']} | "
              f"best={best['policy']} exp=${best['exp_incl_misses']} "
              f"(fill {best['fill_rate']}, forgone/miss ${best['forgone_mean_per_miss']})", flush=True)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    print(f"[t3] wrote {OUT_JSON.name} + {OUT_MD.name}", flush=True)
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# T3 — Entry-matrix (SWARM A): passive limit-below vs pay-up, priced honestly")
    L.append("")
    L.append(f"{out['n_signals']} ribbon_ride signals, qty {out['qty']}. **Does entering at a LIMIT "
             f"below the signal premium beat paying up NET of the winners it misses?** Frictionless "
             f"(market = signal bar open; only the limit-below offset is tested — a real spread would "
             f"tax market MORE, so this is conservative-for-passive). Limit fills = bar low ≤ L−$0.01 "
             f"within patience (5-min bars). **Exploratory — nothing ships (STOP A).**")
    L.append("")
    L.append("`exp incl misses` is the adjudicator (miss = $0). `forgone/miss` = mean P&L of the "
             "winners a limit skipped. A passive entry wins ONLY if `net vs market` > 0.")
    L.append("")
    # HEADLINE verdict per exit: does the honest CANCEL limit (real misses) ever beat market?
    L.append("## HEADLINE — passive entry is CONDITIONAL (entry offset = stop headroom)")
    L.append("")
    L.append("| exit | best honest (cancel) limit net vs market | verdict |")
    L.append("|---|--:|---|")
    for exit_name, floor_blocks in out["exits"].items():
        best_net, best_desc = -1e9, ""
        for fk, blk in floor_blocks.items():
            for c in blk["cells"]:
                if "cancel" in c["policy"] and c["fill_rate"] >= 0.6 and c["net_vs_market"] > best_net:
                    best_net, best_desc = c["net_vs_market"], f"{c['policy']} @ {fk.split('_')[1]}"
        verdict = ("✅ passive WINS" if best_net > 0 else "❌ pay-up better") + f" (best {best_desc})"
        L.append(f"| `{exit_name}` | {best_net:+.0f} | {verdict} |")
    L.append("")
    L.append("The pattern: a limit-below fills CHEAPER → the SAME stop sits offset% further from the "
             "signal (free headroom) → but you MISS the winners the bar never dipped to. That trade "
             "pays off ONLY with a stop to protect AND a reachable target: the **scalp (−35/+50)** "
             "wins big, the **control (−20/+150)** wins only with a premium floor, the **no-stop ride** "
             "LOSES (no stop = headroom protects nothing). A premium floor amplifies passive everywhere. "
             "'convert' policies add a second edge — entering one bar later dodges the signal-bar "
             "premium spike (defect #2) — but that is DELAY, not the limit; the **cancel** rows are the "
             "clean passive-fill test. Joint entry×exit optimum needs the combined grid (T6).")
    L.append("")
    for exit_name, floor_blocks in out["exits"].items():
        L.append(f"## Exit held fixed: `{exit_name}`")
        L.append("")
        for floor_key, blk in floor_blocks.items():
            floor = floor_key.split("_")[1]
            mkt = blk["market"]
            L.append(f"### premium floor ${floor}  (eligible n={mkt['eligible_n']}, "
                     f"market exp ${mkt['exp_incl_misses']})")
            L.append("")
            L.append("| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |")
            L.append("|---|--:|--:|--:|--:|--:|")
            # market row first, then top 6 limit policies
            rows = [blk["market"]] + [c for c in blk["cells"] if c["policy"] != "market(pay-up ctl)"][:6]
            for c in rows:
                star = " ✅" if c["net_vs_market"] > 0 and c["policy"] != "market(pay-up ctl)" else ""
                L.append(f"| `{c['policy']}`{star} | {c['fill_rate']*100:.0f}% | "
                         f"${c['exp_incl_misses']} | {c['net_vs_market']:+.0f} | "
                         f"${c['exp_filled_only']} | ${c['forgone_mean_per_miss']} |")
            L.append("")
    L.append("---")
    L.append("**READ:** if `filled-only exp` >> market but `exp incl misses` ≤ market, the limit "
             "gets BETTER fills but misses too many winners (defect: the passive entry's miss cost "
             "eats its headroom edge). If `net vs market` > 0 at a reachable fill%, J's hypothesis "
             "holds for that exit×floor. Finalists → T5 confirmatory OOS + anchor (post-STOP-A).")
    L.append("")
    L.append("_Source: `backtest/tools/t3_entry_matrix.py`. No entry-path change ships from this file._")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
