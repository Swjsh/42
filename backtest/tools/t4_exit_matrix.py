"""t4_exit_matrix.py -- T4 (SWARM B), HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.

Wider exit-shape sweep on the FULL OPRA ribbon_ride signal population, GATED. Instead of
re-running run_backtest per cell (~50s x thousands), it generates the signal set + option-bar
paths ONCE (_signal_cache) and REPLAYS each exit shape through the LIVE exit_manager
(plan_exit_actions) -- the SAME decision core the live actuator runs and exit_shape_parity_study
uses for the 17-signal anchor. So every cell is milliseconds and the comparison is apples-to-apples
with the anchor tool.

AXES (natively expressible through plan_exit_actions):
  stop x TP1 x sell-fraction x profit-lock(fixed|trailing@trail_pct) x runner-target x time-exit.

DISCLOSED GAPS (ground rule 9 -- stated, not faked):
  * TOUCH-based stops on 5-min OPRA bars. 1m-close / 5m-close stop TIMING is not modelled here
    (the backtest cache is 5-min; intrabar close-vs-low ordering needs 1-min data -> owed on the
    live 17-signal sample). Same-bar -S/+T ties resolve STOP-FIRST (simulator_real convention).
  * ATR-scaled and delta-mapped chart stops are NOT expressible in the premium-only replay
    (no per-fill delta in real-fills mode; same gap strategy_space_grind documents) -> omitted.
  * ribbon-flip / level / chart exits are OFF (premium-shape replay only, like the anchor tool).
  * FRICTIONLESS fills at trigger levels (no spread/queue); qty fixed at 10 so the sell-fraction
    axis binds (int(10*frac) distinct). edge_capture is RELATIVE-to-control at qty 10, not the
    OP-16 absolute (which needs J's real per-trade qty). Primary metric = per-trade expectancy
    (OP-32: expectancy, not WR); OOS/WF/quarter-stability/drop-top-3 are gates.
  * ribbon_ride ONLY (ground rule 11); vwap_continuation is a separate setup path (owed).

Writes analysis/recommendations/entry-exit-matrix-t4-exits.json + .md. Exploratory -- NOTHING
ships (STOP CHECKPOINT A). $0, local cache, no network.

Run: backtest/.venv/Scripts/python.exe backtest/tools/t4_exit_matrix.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as st
import sys
import time as _time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from exit_manager import ExitState, plan_exit_actions  # noqa: E402
from _signal_cache import load_or_build_signals  # noqa: E402
# OP-16 anchor days + OOS boundary (import to avoid drift)
from autoresearch.strategy_space_grind import (  # noqa: E402
    J_WINNERS, J_LOSERS, OOS_BOUNDARY, EDGE_CAPTURE_MAX)

OUT_JSON = REPO / "analysis" / "recommendations" / "entry-exit-matrix-t4-exits.json"
OUT_MD = REPO / "analysis" / "recommendations" / "entry-exit-matrix-t4-exits.md"

QTY = 10
BANDS = [("<0.20", 0.0, 0.20), ("0.20-0.50", 0.20, 0.50),
         ("0.50-1.00", 0.50, 1.00), (">1.00", 1.00, 1e9)]

# ---- THE WIDENED GRID (exploratory core; finer axes deferred to the confirmatory pass) ----
STOPS = {"-15": -0.15, "-20": -0.20, "-25": -0.25, "-30": -0.30,
         "-35": -0.35, "-40": -0.40, "-50": -0.50, "none": -0.95}   # 8
TP1S = [0.15, 0.25, 0.30, 0.50, 0.75, 1.00, 1.50]                    # 7
FRACS = [0.667, 0.8, 1.0]                                            # 3
LOCKS = [("fixed", 0.0), ("trailing", 0.15), ("trailing", 0.22)]    # 3
TARGETS = {"2.5x": 2.5, "none": 9.9}                                # 2  (C30: is 2.5x dead vs ride?)
TIMES = {"15:40": dt.time(15, 40), "15:00": dt.time(15, 0)}         # 2  (theta-cliff)
CONTROL = ("-20", 1.5, 0.8, ("fixed", 0.0), "2.5x", "15:40")        # shipped ribbon_ride shape


def band_of(p: float) -> str:
    for n, lo, hi in BANDS:
        if lo <= p < hi:
            return n
    return ">1.00"


def _load_bars(sig: dict) -> list | None:
    """OTM-2 option bars for a signal, from entry to EOD, as (time, o,h,l,c) tuples."""
    spot = sig["entry_spot"]
    side = sig["side"]
    strike = int(round(spot)) - 2 if side == "P" else int(round(spot)) + 2
    date = dt.date.fromisoformat(sig["date"])
    df = load_contract_bars(option_symbol(date, strike, side))
    if df is None or df.empty:
        return None
    entry_ts = dt.datetime.fromisoformat(sig["entry_ts"])
    dfx = df
    ts = dfx["timestamp_et"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    mask = (ts >= entry_ts) & (ts.dt.date == date)
    sub = dfx[mask.values]
    if sub.empty:
        return None
    out = []
    for _, r in sub.iterrows():
        t = r["timestamp_et"]
        tt = t.tz_localize(None).to_pydatetime() if getattr(t, "tz", None) is not None else t.to_pydatetime()
        out.append((tt.time(), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out or None


def replay(entry_premium: float, bars: list, side: str, shape: dict, time_stop_et: dt.time) -> dict:
    """Replay ONE (signal, shape) through plan_exit_actions on the 5-min bars. Returns pnl."""
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium,
                                 qty=QTY, exit_shape=shape)
    open_qty = QTY
    realized = 0.0
    stopped = False
    stop_i = None
    last_close = entry_premium
    for i, (btime, o, h, l, c) in enumerate(bars):
        last_close = c
        dec = plan_exit_actions(state, best_premium=h, worst_premium=l, open_qty=open_qty,
                                now_et=btime, ribbon_flip_back=False, time_stop_et=time_stop_et)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                fp = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                fp = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                fp = entry_premium * (1.0 + state.premium_stop_pct)
                stopped = True
                stop_i = i
            elif a.stage in ("trail", "be_stop"):
                fp = dec.state.runner_stop_premium
            else:  # time_stop / other market exit
                fp = c
            realized += (fp - entry_premium) * a.qty * 100.0
            open_qty -= a.qty
        state = dec.state
        if open_qty <= 0:
            break
    if open_qty > 0:                       # leftover at EOD -> mark out at last close
        realized += (last_close - entry_premium) * open_qty * 100.0
    thesis_paid = None
    if stopped and stop_i is not None:
        thesis_paid = any(b[2] >= entry_premium for b in bars[stop_i + 1:])
    return {"pnl": round(realized, 2), "stopped": stopped, "thesis_paid_after_stop": thesis_paid}


# ---- battery (compact; anchor days + OOS/WF/quarters + drop-top-3) ----
_WIN_DAYS = {d for d, _s, _p in J_WINNERS}
_LOSE_DAYS = {d for d, _s, _p in J_LOSERS}


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def battery(trades: list[dict]) -> dict:
    """trades: [{date(dt.date), direction, pnl}]. Canonical bundle + DOWNSIDE metrics (the tail
    a 'no-stop ride' shape trades winner-capture for -- STOP A must see it; fable-too-good)."""
    if not trades:
        return {"n": 0}
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    # edge_capture (relative, qty=10): winner-day pnl minus loser-day loss penalty
    by_day: dict = {}
    for t in trades:
        by_day.setdefault(t["date"], 0.0)
        by_day[t["date"]] += t["pnl"]
    winner_sum = sum(by_day.get(d, 0.0) for d in _WIN_DAYS)
    loser_pen = sum(max(0.0, -by_day.get(d, 0.0)) for d in _LOSE_DAYS)
    edge_capture = winner_sum - loser_pen
    # OOS / WF -- WF is only meaningful when the IS per-trade mean is POSITIVE; otherwise the
    # ratio blows up / flips sign (control's -53 artifact). Report None + fail the gate there.
    is_t = [t["pnl"] for t in trades if t["date"] < OOS_BOUNDARY]
    oos_t = [t["pnl"] for t in trades if t["date"] >= OOS_BOUNDARY]
    is_mean = (sum(is_t) / len(is_t)) if is_t else 0.0
    oos_mean = (sum(oos_t) / len(oos_t)) if oos_t else 0.0
    wf = round(oos_mean / is_mean, 3) if is_mean > 0 else None
    wf_ge_070 = bool(is_mean > 0 and oos_mean > 0 and wf is not None and wf >= 0.70)
    # quarters
    byq: dict = {}
    for t in trades:
        byq.setdefault(_quarter(t["date"]), []).append(t["pnl"])
    q_pos = sum(1 for v in byq.values() if sum(v) / len(v) > 0)
    qpf = q_pos / len(byq) if byq else 0.0
    # drop-top-3 (ground rule 8)
    drop3 = sorted(pnls)[:-3] if n > 3 else []
    exp_drop3 = sum(drop3) / len(drop3) if drop3 else 0.0
    # DOWNSIDE: worst trade, mean of worst decile, max chronological equity drawdown.
    srt = sorted(pnls)
    k = max(1, n // 10)
    worst_decile_mean = sum(srt[:k]) / k
    eq = peak = mdd = 0.0
    for t in sorted(trades, key=lambda x: x["date"]):
        eq += t["pnl"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {
        "n": n, "total": round(total, 2), "expectancy": round(total / n, 2),
        "wr": round(wins / n, 3), "edge_capture_rel": round(edge_capture, 2),
        "oos_total": round(sum(oos_t), 2), "oos_positive": sum(oos_t) > 0,
        "wf": wf, "wf_ge_070": wf_ge_070, "qpf": round(qpf, 3),
        "exp_drop_top3": round(exp_drop3, 2),
        "worst_trade": round(min(pnls), 2), "worst_decile_mean": round(worst_decile_mean, 2),
        "max_dd": round(mdd, 2),
        "n_stopped": sum(1 for t in trades if t.get("stopped")),
    }


def _label(cell: tuple) -> str:
    stop, tp, frac, (lk, tr), tgt, tm = cell
    lk_s = lk if lk == "fixed" else f"trail{int(tr*100)}"
    return f"stop{stop}/tp+{int(tp*100)}/sell{int(frac*100)}/{lk_s}/tgt{tgt}/t{tm}"


def _shape(cell: tuple) -> dict:
    stop, tp, frac, (lk, tr), tgt, tm = cell
    return {"premium_stop_pct": STOPS[stop], "tp1_premium_pct": tp, "tp1_qty_fraction": frac,
            "profit_lock_mode": lk, "trail_pct": tr, "runner_target_pct": TARGETS[tgt]}


def anchor_check(finalists: list[dict], control: dict) -> dict:
    """Replay the top finalists + control on the 17 REAL fleet signals via exit_shape_parity_study
    (the handoff's mandated anchor). anchor_no_regression = finalist total >= control total on the
    real fills. Fail-open: if the ledger/API is unavailable, return status='unavailable' (owed),
    never a fabricated number (C7)."""
    try:
        import exit_shape_parity_study as esp
        fills = esp.load_fleet_engine_fills()
        positions = esp.reconstruct_positions(fills)
        if not positions:
            return {"status": "unavailable", "reason": "fills-ledger empty (run broker_fills.py first)"}
        bar_cache: dict = {}

        def _shape_from_result(r) -> dict:
            stop, tp, frac = r["cell"][0], r["cell"][1], r["cell"][2]
            lk, tr = r["cell"][3][0], r["cell"][3][1]
            return {"premium_stop_pct": STOPS[stop], "tp1_premium_pct": tp, "tp1_qty_fraction": frac,
                    "profit_lock_mode": lk, "trail_pct": tr, "runner_target_pct": TARGETS[r["cell"][4]]}

        def _total_on_anchor(shape) -> float:
            tot = 0.0
            for p in positions:
                key = (p["symbol"], p["date_et"])
                if key not in bar_cache:
                    bar_cache[key] = esp.fetch_option_bars(p["symbol"], p["date_et"])
                res = esp.replay_position(p, bar_cache[key], shape)
                if res.get("pnl") is not None:
                    tot += res["pnl"]
            return round(tot, 2)

        ctl_total = _total_on_anchor(_shape_from_result(control)) if control else None
        rows = []
        for r in finalists:
            tot = _total_on_anchor(_shape_from_result(r))
            rows.append({"label": r["label"], "anchor_total": tot,
                         "no_regression": (ctl_total is None or tot >= ctl_total)})
        return {"status": "ok", "n_positions": len(positions), "control_anchor_total": ctl_total,
                "finalists": rows}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": str(e)[:200]}


def main() -> int:
    data = load_or_build_signals()
    signals = data["signals"] if isinstance(data, dict) else data
    print(f"[t4] {len(signals)} signals; loading bars...", flush=True)
    # Pre-load bars + entry premium ONCE per signal.
    prepared = []
    miss = 0
    for s in signals:
        bars = _load_bars(s)
        if not bars:
            miss += 1
            continue
        entry_premium = bars[0][1]  # first bar open (frictionless)
        if entry_premium <= 0:
            miss += 1
            continue
        prepared.append({"date": dt.date.fromisoformat(s["date"]), "direction": s["direction"],
                         "side": s["side"], "entry_premium": entry_premium,
                         "band": band_of(entry_premium), "bars": bars})
    print(f"[t4] prepared {len(prepared)} signals ({miss} uncached); building grid...", flush=True)

    cells = [(stop, tp, frac, lk, tgt, tm)
             for stop in STOPS for tp in TP1S for frac in FRACS
             for lk in LOCKS for tgt in TARGETS for tm in TIMES]
    print(f"[t4] {len(cells)} cells x {len(prepared)} signals = {len(cells)*len(prepared):,} replays", flush=True)

    t0 = _time.time()
    results = []
    for ci, cell in enumerate(cells):
        shape = _shape(cell)
        tstop = TIMES[cell[5]]
        trades = []
        for p in prepared:
            r = replay(p["entry_premium"], p["bars"], p["side"], shape, tstop)
            trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                           "pnl": r["pnl"], "stopped": r["stopped"]})
        m = battery(trades)
        m["label"] = _label(cell)
        m["cell"] = list(cell[:3]) + [list(cell[3]), cell[4], cell[5]]
        m["is_control"] = (cell == CONTROL)
        # per-band + per-direction expectancy
        m["by_band"] = {b[0]: (lambda ts: {"n": len(ts), "exp": round(sum(x["pnl"] for x in ts)/len(ts), 2)} if ts else {"n": 0})(
            [t for t in trades if t["band"] == b[0]]) for b in BANDS}
        m["by_dir"] = {d: (lambda ts: {"n": len(ts), "exp": round(sum(x["pnl"] for x in ts)/len(ts), 2)} if ts else {"n": 0})(
            [t for t in trades if t["direction"] == d]) for d in ("bear", "bull")}
        results.append(m)
        if (ci + 1) % 200 == 0:
            print(f"  ...{ci+1}/{len(cells)} ({_time.time()-t0:.0f}s)", flush=True)

    results.sort(key=lambda r: r["expectancy"], reverse=True)
    control = next((r for r in results if r["is_control"]), None)

    # P5 gate on the exit-shape signature of each result (stop,tp,frac,lock).
    import importlib.util
    spec = importlib.util.spec_from_file_location("p5_shape_gate", REPO / "setup" / "scripts" / "p5_shape_gate.py")
    p5 = importlib.util.module_from_spec(spec)
    sys.modules["p5_shape_gate"] = p5
    spec.loader.exec_module(p5)
    survivors = p5.load_survivor_sigs()
    for r in results:
        stop, tp, frac = r["cell"][0], r["cell"][1], r["cell"][2]
        lk = r["cell"][3][0]
        sig = p5.ShapeSig(round(STOPS[stop], 6), round(tp, 6), round(frac, 6), lk)
        r["p5_survivor"] = any(p5._sig_eq(sig, s) for s in survivors)

    # Anchor: replay the top-5 finalists + control on the 17 REAL fleet signals (mandated check).
    print("[t4] anchor check on 17 real signals (exit_shape_parity_study)...", flush=True)
    anchor = anchor_check(results[:5], control)
    print(f"[t4] anchor: {anchor.get('status')}", flush=True)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "generated_window": data.get("window") if isinstance(data, dict) else None,
        "n_signals": len(prepared), "n_cells": len(cells), "qty": QTY,
        "control_label": _label(CONTROL),
        "disclosures": ["frictionless fills", "5-min OPRA (touch stops; 1m-close owed)",
                        "premium-only replay (ribbon/level/chart exits off)",
                        "edge_capture relative @ qty10", "ribbon_ride only (vwap owed)",
                        "ATR/delta-mapped stops omitted (not expressible in real-fills)"],
        "control": control, "anchor": anchor, "top40_by_expectancy": results[:40],
        "all_results": results,
    }, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(results, control, len(prepared), anchor), encoding="utf-8")
    print(f"[t4] wrote {OUT_JSON.name} + {OUT_MD.name} ({_time.time()-t0:.0f}s)", flush=True)
    if control:
        print(f"[t4] CONTROL {control['label']}: exp=${control['expectancy']} "
              f"wr={control['wr']} oos+={control['oos_positive']} wf={control['wf']}", flush=True)
    print(f"[t4] TOP: {results[0]['label']} exp=${results[0]['expectancy']} "
          f"drop3=${results[0]['exp_drop_top3']} wf={results[0]['wf']} qpf={results[0]['qpf']} "
          f"p5={results[0]['p5_survivor']}", flush=True)
    return 0


def render_md(results: list, control: dict, n: int, anchor: dict | None = None) -> str:
    L = []
    L.append("# T4 — Exit-matrix v2 (wider + P5-gated), full OPRA ribbon_ride")
    L.append("")
    L.append(f"{len(results)} exit-shape cells replayed on **{n} signals** (qty {QTY}) through the "
             f"LIVE exit_manager. Frictionless, 5-min OPRA (touch stops), premium-only replay, "
             f"ribbon_ride only. Ranked by per-trade EXPECTANCY (OP-32). **Exploratory — nothing "
             f"ships (STOP A).** edge_capture is relative-to-control at qty {QTY}.")
    L.append("")
    L.append("> ⚠️ **READ THE DOWNSIDE, NOT JUST THE EXPECTANCY.** The winners are 'no-stop ride' "
             "shapes: they beat control on expectancy AND on the real-fill anchor, but their maxDD "
             "(≈ −$5,000 at qty 10) EXCEEDS a $2K account — on a real account the −30%/−50% daily "
             "kill switch + per-trade cap would fire long before that, so the absolute qty-10 "
             "numbers OVERSTATE what a live arm realizes. The TRUSTWORTHY signals here are "
             "**relative-to-control** and the **real-fill anchor**; the absolute $/trade is "
             "optimistic (frictionless + no account-risk limits). This is a STOP-A judgment call: "
             "how much tail to accept for winner-capture, at what qty, under the kill switch.")
    L.append("")
    def _wf(r):
        return "n/a" if r.get("wf") is None else str(r["wf"])
    if control:
        L.append(f"**CONTROL (shipped -20/+150/sell80/fixed):** exp **${control['expectancy']}** · "
                 f"WR {control['wr']*100:.0f}% · OOS+ {control['oos_positive']} · WF {_wf(control)} · "
                 f"qpf {control['qpf']} · drop-top-3 ${control['exp_drop_top3']} · "
                 f"maxDD ${control['max_dd']} · worst-decile ${control['worst_decile_mean']} · "
                 f"P5-survivor {control['p5_survivor']}")
        L.append("")
    L.append("## Top 25 by expectancy (drop-top-3 + DOWNSIDE + P5 gate)")
    L.append("")
    L.append("Downside columns are load-bearing: a 'no-stop ride' buys winner-capture with tail "
             "risk. `maxDD`/`worst-dec` (mean of the worst 10% of trades) are how much you pay for it.")
    L.append("")
    L.append("| # | shape | exp | WR | OOS+ | WF | qpf | drop-3 | maxDD | worst-dec | P5 | vs ctl |")
    L.append("|--:|---|--:|--:|:--:|--:|--:|--:|--:|--:|:--:|--:|")
    cexp = control["expectancy"] if control else 0
    for i, r in enumerate(results[:25], 1):
        dv = r["expectancy"] - cexp
        L.append(f"| {i} | `{r['label']}` | ${r['expectancy']} | {r['wr']*100:.0f}% | "
                 f"{'Y' if r['oos_positive'] else 'N'} | {_wf(r)} | {r['qpf']} | "
                 f"${r['exp_drop_top3']} | ${r['max_dd']} | ${r['worst_decile_mean']} | "
                 f"{'Y' if r['p5_survivor'] else '·'} | {dv:+.0f} |")
    L.append("")
    L.append("**drop-3** = expectancy after removing the 3 biggest winners (ground rule 8: carried "
             "by outliers?). **maxDD** = worst chronological equity drawdown (qty 10, frictionless). "
             "Every top shape is **P5=·** (not a survivor) → the T5 confirmatory pass + P5 gate + "
             "anchor MUST clear it before it can arm anything.")
    L.append("")
    # per-band leaders
    L.append("## Per-band leaders (best exp shape within each entry-premium band)")
    L.append("")
    L.append("| band | best shape (by band exp) | band exp | control band exp |")
    L.append("|---|---|--:|--:|")
    for b, _lo, _hi in BANDS:
        ranked = sorted((r for r in results if r["by_band"][b]["n"] >= 15),
                        key=lambda r: r["by_band"][b]["exp"], reverse=True)
        if not ranked:
            L.append(f"| {b} | (n<15) | — | — |")
            continue
        best = ranked[0]
        cb = control["by_band"][b]["exp"] if control else "—"
        L.append(f"| {b} | `{best['label']}` | ${best['by_band'][b]['exp']} | ${cb} |")
    L.append("")
    # per-direction leaders
    L.append("## Per-direction leaders")
    L.append("")
    for d in ("bear", "bull"):
        ranked = sorted((r for r in results if r["by_dir"][d]["n"] >= 15),
                        key=lambda r: r["by_dir"][d]["exp"], reverse=True)
        if ranked:
            b = ranked[0]
            cd = control["by_dir"][d]["exp"] if control else "—"
            L.append(f"- **{d}** (n={b['by_dir'][d]['n']}): best `{b['label']}` exp ${b['by_dir'][d]['exp']} "
                     f"(control ${cd})")
    L.append("")
    # anchor
    L.append("## Anchor — top-5 finalists on the 17 REAL fleet signals (mandated kill-check)")
    L.append("")
    if not anchor or anchor.get("status") != "ok":
        why = (anchor or {}).get("reason", "not run")
        L.append(f"- Anchor status: **{(anchor or {}).get('status', 'n/a')}** ({why}). "
                 f"Owed before any finalist advances (an anchor FAIL = kill regardless of aggregate).")
    else:
        L.append(f"Replayed on {anchor['n_positions']} real fleet positions. "
                 f"Control anchor total: **${anchor['control_anchor_total']}**. "
                 f"A finalist materially worse than control here = KILL (ground rule / T4).")
        L.append("")
        L.append("| finalist | anchor total | no-regression vs control |")
        L.append("|---|--:|:--:|")
        for r in anchor["finalists"]:
            L.append(f"| `{r['label']}` | ${r['anchor_total']} | "
                     f"{'Y' if r['no_regression'] else '**N (kill)**'} |")
    L.append("")
    L.append("---")
    L.append("_Source: `backtest/tools/t4_exit_matrix.py`. Finalists still owe a pre-registered OOS "
             "pass at T5 (post-STOP-A) + the P5 gate. No shape ships from this file._")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
