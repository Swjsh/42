#!/usr/bin/env python
"""stop_mode_matrix_2026_08_19.py -- FULL STOP-MODE MATRIX over the entire real-fills book.

Dataset: analysis/recommendations/trade-matrix.json (303 closed round trips, 5 arms,
2026-06-26..2026-08-19). The matrix's own `path` field is the HELD window only (entry ->
realized exit), so it CANNOT answer "what would a WIDER stop have done" -- there are no bars
after the realized exit. This module therefore re-reads the full-day 1-minute OPRA cache
(backtest/data/opra_1m_cache/{symbol}_{date}.csv, 09:30..~16:14 ET, all 109 contract-days
present) and walks each position forward to the 15:40 ET hard time stop.

NO LOOK-AHEAD (C6): the entry BAR is excluded from every decision -- a stop cannot fire on a
print that printed before the fill landed. Every stop level is decidable at entry (a fixed %
of entry premium, an ATR computed from PRE-entry bars only, a clock, a trailing rule seeded at
entry, or a SPY level recorded on the decision row that produced the order).

The upside rule is held CONSTANT across every cell so the only moving part is the DOWNSIDE.
Two upside shapes are run: RIBBON (tp1 +100% / 0.667, chandelier arm +5% trail 15% -- the
shape the pre-registered stop-mode clock uses) and SAFE (tp1 +50% / 0.8, trail 12.5% --
automation/state/params.json). A cell that wins under one and loses under the other is fragile
and is reported as such.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import cost_model  # noqa: E402

MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"
OPRA = REPO / "backtest" / "data" / "opra_1m_cache"
SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-19.csv"
OUT = REPO / "analysis" / "deep-research" / "LOSSES-STOP-MODE-MATRIX-2026-08-19.json"

TIME_STOP = dt.time(15, 40)            # automation/state/params.json time_stop_et
EXIT_SLIP_PREMIUM = 0.0103             # COST-REALISM-2026-08-18.md, MEASURED, per contract
_ET = dt.timezone(dt.timedelta(hours=-4))

UPSIDE = {
    "RIBBON": {"tp1_pct": 1.00, "tp1_frac": 0.667, "arm": 0.05, "trail": 0.15},
    "SAFE": {"tp1_pct": 0.50, "tp1_frac": 0.800, "arm": 0.05, "trail": 0.125},
}


# ----------------------------------------------------------------- data
def load_bars(symbol: str, date: str) -> list[dict]:
    p = OPRA / (symbol + "_" + date + ".csv")
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            t = r.get("t")
            if not t:
                continue
            try:
                ts = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            except ValueError:
                continue
            ts = ts.astimezone(_ET).replace(tzinfo=None)
            try:
                o, h, lo, c = float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])
            except (TypeError, ValueError, KeyError):
                continue
            out.append({"ts": ts, "o": o, "h": h, "l": lo, "c": c})
    out.sort(key=lambda b: b["ts"])
    return out


def load_spy5m():
    by_date = defaultdict(list)
    with SPY5M.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            ts = dt.datetime.fromisoformat(r["timestamp_et"]).replace(tzinfo=None)
            by_date[ts.date().isoformat()].append(
                {"ts": ts, "o": float(r["open"]), "h": float(r["high"]),
                 "l": float(r["low"]), "c": float(r["close"])})
    for v in by_date.values():
        v.sort(key=lambda b: b["ts"])
    return dict(by_date)


def atr_from_pre_entry(bars, e0, n=14):
    """Wilder-style ATR on the option's OWN 1-min bars, PRE-ENTRY ONLY. None if too few."""
    pre = [b for b in bars if b["ts"] < e0]
    if len(pre) < n + 1:
        return None
    trs = []
    for i in range(1, len(pre)):
        pc = pre[i - 1]["c"]
        trs.append(max(pre[i]["h"] - pre[i]["l"], abs(pre[i]["h"] - pc), abs(pre[i]["l"] - pc)))
    if len(trs) < n:
        return None
    return sum(trs[-n:]) / n


def _spy_bar_for(day_bars, ts):
    prev = None
    for b in day_bars:
        if b["ts"] <= ts:
            prev = b
        else:
            break
    return prev


def _spy_closed_bar_for(day_bars, ts):
    """Most recent 5m bar that has CLOSED strictly at or before ts (no look-ahead)."""
    prev = None
    for b in day_bars:
        if b["ts"] + dt.timedelta(minutes=5) <= ts:
            prev = b
        else:
            break
    return prev


# ----------------------------------------------------------------- walker
def simulate(row, bars, spy_day, stop_kind, stop_arg, up):
    """One counterfactual round trip. Returns a dict, or the string 'UNCOMPUTABLE', or None.

    stop_kind defines ONLY the pre-TP1 downside. Post-TP1 the runner carries the production
    breakeven stop plus the chandelier trail, identically in every cell, so the matrix isolates
    the downside lever instead of silently re-tuning the upside alongside it.
    """
    entry = float(row["entry_premium"])
    qty = int(row["qty"])
    if entry <= 0 or qty <= 0:
        return None
    e_ts = dt.datetime.fromisoformat(row["entry_ts_et"])
    e0 = e_ts.replace(second=0, microsecond=0)
    post = [b for b in bars if b["ts"] > e0]           # C6: entry bar excluded
    if not post:
        return None
    t_stop = dt.datetime.combine(e_ts.date(), TIME_STOP)

    fixed_stop = None
    trail_pct = None
    time_limit = None
    spy_stop = None
    struct_level = None
    if stop_kind == "PREMIUM":
        fixed_stop = entry * (1.0 + stop_arg)
    elif stop_kind == "ATR":
        a = atr_from_pre_entry(bars, e0)
        if a is None or a <= 0:
            return "UNCOMPUTABLE"
        fixed_stop = max(entry - stop_arg * a, 0.005)
    elif stop_kind == "TRAIL":
        trail_pct = stop_arg
    elif stop_kind == "TIME":
        time_limit = e0 + dt.timedelta(minutes=stop_arg)
    elif stop_kind == "SPYMOVE":
        s0 = row.get("spy_at_entry")
        if not s0 or not spy_day:
            return "UNCOMPUTABLE"
        spy_stop = (s0 - stop_arg) if row["side"] == "C" else (s0 + stop_arg)
    elif stop_kind == "STRUCTURE":
        lv = row.get("trigger_level")
        if lv is None or not spy_day:
            return "UNCOMPUTABLE"
        struct_level = float(lv)
        fixed_stop = entry * (1.0 + stop_arg)          # catastrophe cap rides along
    elif stop_kind == "NONE":
        pass
    else:
        raise ValueError(stop_kind)

    tp1_lvl = entry * (1.0 + up["tp1_pct"])
    tp1_qty = min(max(int(round(qty * up["tp1_frac"])), 1), qty - 1) if qty >= 2 else 0

    state = {"open": qty, "proceeds": 0.0, "reason": None}
    legs = []
    tp1_done = False
    hwm = entry

    def close_out(px, ts, why, n=None):
        n = state["open"] if n is None else n
        state["proceeds"] += px * n
        legs.append({"ts": ts.isoformat(), "qty": n, "px": round(px, 4), "why": why})
        state["open"] -= n
        state["reason"] = why

    for b in post:
        if state["open"] <= 0:
            break
        if b["ts"] >= t_stop:
            close_out(b["o"], b["ts"], "time_stop_1540")
            break

        if not tp1_done:
            lvl = None
            why = None
            if fixed_stop is not None:
                lvl = fixed_stop
                why = "catastrophe_cap" if stop_kind == "STRUCTURE" else "premium_stop"
            if trail_pct is not None:
                t = hwm * (1.0 - trail_pct)
                if lvl is None or t > lvl:
                    lvl, why = t, "trail_stop"
            if lvl is not None and b["l"] <= lvl:
                # gap-through: if the bar OPENS below the stop, we get the open, not the level
                close_out(min(lvl, b["o"]), b["ts"], why)
                break
            if spy_stop is not None:
                # CLOSED bars only. _spy_bar_for would hand back the bar CURRENTLY FORMING,
                # whose high/low contain prints up to 5 minutes in the FUTURE -- the exact
                # look-ahead defect C6 exists to catch. Cost: the SPY stop lags up to 5 min.
                b5 = _spy_closed_bar_for(spy_day, b["ts"])
                if b5 and ((row["side"] == "C" and b5["l"] <= spy_stop) or
                           (row["side"] == "P" and b5["h"] >= spy_stop)):
                    close_out(b["c"], b["ts"], "spy_move_stop")
                    break
            if struct_level is not None:
                b5 = _spy_closed_bar_for(spy_day, b["ts"])
                if b5 and ((row["side"] == "C" and b5["c"] < struct_level) or
                           (row["side"] == "P" and b5["c"] > struct_level)):
                    close_out(b["c"], b["ts"], "structure_stop")
                    break
            if time_limit is not None and b["ts"] >= time_limit:
                close_out(b["c"], b["ts"], "time_limit")
                break
            if tp1_qty and b["h"] >= tp1_lvl:
                close_out(tp1_lvl, b["ts"], "tp1", n=tp1_qty)
                tp1_done = True
                hwm = max(hwm, b["h"])
                continue
            hwm = max(hwm, b["h"])
        else:
            hwm = max(hwm, b["h"])
            rstop = entry                              # runner_be_stop_after_tp1 = True
            if hwm >= entry * (1.0 + up["arm"]):
                rstop = max(rstop, hwm * (1.0 - up["trail"]))
            if b["l"] <= rstop:
                close_out(min(rstop, b["o"]), b["ts"], "runner_trail_or_be")
                break

    if state["open"] > 0:
        close_out(post[-1]["c"], post[-1]["ts"], "eod_last_bar")

    pnl = (state["proceeds"] - entry * qty) * 100.0
    return {"pnl_gross": round(pnl, 2), "qty": qty, "exit_reason": state["reason"],
            "hold_min": round((dt.datetime.fromisoformat(legs[-1]["ts"]) - e0).total_seconds() / 60.0, 1),
            "exit_ts": legs[-1]["ts"], "tp1_done": tp1_done, "n_legs": len(legs)}


# ----------------------------------------------------------------- aggregation
def costs_for(entry_premium, qty, pnl_gross):
    fb = cost_model.fee_breakdown({"entry_premium": entry_premium, "qty": qty,
                                   "real_pnl": pnl_gross})
    return fb["fee_total_ex_cat"], qty * EXIT_SLIP_PREMIUM * 100.0


def summarize(trades, label, baseline=None):
    if not trades:
        return None
    g = sum(t["pnl_gross"] for t in trades)
    fee = sum(t["fee"] for t in trades)
    slip = sum(t["slip"] for t in trades)
    wins = [t for t in trades if t["pnl_gross"] > 0]
    losses = [t for t in trades if t["pnl_gross"] < 0]
    by_day = defaultdict(float)
    for t in trades:
        by_day[t["date"]] += t["pnl_gross"]
    chrono = sorted(trades, key=lambda t: t["exit_ts"])
    peak = cum = mdd = 0.0
    for t in chrono:
        cum += t["pnl_gross"]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    out = {
        "cell": label, "n": len(trades),
        "gross": round(g, 2),
        "net_fees": round(g - fee, 2),
        "net_fees_slip": round(g - fee - slip, 2),
        "fees": round(fee, 2), "slip": round(slip, 2),
        "win_rate": round(len(wins) / len(trades), 4),
        "winner_dollars": round(sum(t["pnl_gross"] for t in wins), 2),
        "loser_dollars": round(sum(t["pnl_gross"] for t in losses), 2),
        "avg_loss": round(statistics.mean([t["pnl_gross"] for t in losses]), 2) if losses else 0.0,
        "worst_loss": round(min([t["pnl_gross"] for t in losses]), 2) if losses else 0.0,
        "best_trade": round(max([t["pnl_gross"] for t in trades]), 2),
        "max_drawdown": round(mdd, 2),
        "expectancy": round(g / len(trades), 2),
        "n_days": len(by_day),
        "top_day_pnl": round(max(by_day.values(), key=abs), 2),
        "avg_hold_min": round(statistics.mean([t["hold_min"] for t in trades]), 1),
        "pct_tp1_reached": round(sum(1 for t in trades if t.get("tp1_done")) / len(trades), 4),
    }
    if baseline is not None:
        bmap = {t["key"]: t["pnl_gross"] for t in baseline}
        deltas = [(t["key"], t["date"], round(t["pnl_gross"] - bmap[t["key"]], 2))
                  for t in trades if t["key"] in bmap]
        tot = sum(d[2] for d in deltas)
        by_d = defaultdict(float)
        for _, dte, dv in deltas:
            by_d[dte] += dv
        abs_sum = sum(abs(d[2]) for d in deltas)
        top_trade = max((abs(d[2]) for d in deltas), default=0.0)
        top_day = max((abs(v) for v in by_d.values()), default=0.0)
        # winners of the BASELINE that this cell turned into losers, and vice versa
        killed = [(k, round(bmap[k], 2)) for k, _, _ in deltas
                  if bmap[k] > 0 and next(t["pnl_gross"] for t in trades if t["key"] == k) <= 0]
        out["delta_vs_baseline"] = round(tot, 2)
        out["delta_top_day_share"] = round(top_day / abs_sum, 4) if abs_sum else None
        out["delta_top_trade_share"] = round(top_trade / abs_sum, 4) if abs_sum else None
        out["delta_top_day"] = max(by_d.items(), key=lambda kv: abs(kv[1]))[0] if by_d else None
        out["baseline_winners_killed"] = len(killed)
        out["baseline_winner_dollars_killed"] = round(sum(v for _, v in killed), 2)
    return out


# ----------------------------------------------------------------- driver
def build_cells():
    cells = [("NONE", None, "NO_STOP (15:40 time stop only)")]
    for p in (-0.10, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50, -0.60, -0.75):
        cells.append(("PREMIUM", p, "PREMIUM_%d" % round(abs(p) * 100)))
    for k in (1.0, 1.5, 2.0, 3.0, 4.0):
        cells.append(("ATR", k, "ATR_%sx" % ("%g" % k)))
    for m in (5, 10, 15, 20, 30, 45, 60, 90):
        cells.append(("TIME", m, "TIME_%dm" % m))
    for p in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
        cells.append(("TRAIL", p, "TRAIL_%d" % round(p * 100)))
    for d in (0.40, 0.60, 0.80, 1.00, 1.50, 2.00):
        cells.append(("SPYMOVE", d, "SPYMOVE_$%.2f" % d))
    for cap in (-0.50, -0.75):
        cells.append(("STRUCTURE", cap, "STRUCTURE+cap%d" % round(abs(cap) * 100)))
    return cells


def main():
    m = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = m["rows"]
    spy = load_spy5m()
    barcache = {}
    for r in rows:
        k = (r["symbol"], r["date"])
        if k not in barcache:
            barcache[k] = load_bars(*k)

    cells = build_cells()
    results = {}
    per_trade = {}
    uncomputable = defaultdict(list)
    no_bars = []

    for shape_name, up in UPSIDE.items():
        for kind, arg, label in cells:
            trades = []
            for i, r in enumerate(rows):
                bars = barcache[(r["symbol"], r["date"])]
                if not bars:
                    if shape_name == "RIBBON" and label == "NONE":
                        no_bars.append(r["symbol"] + " " + r["date"])
                    continue
                res = simulate(r, bars, spy.get(r["date"]), kind, arg, up)
                if res is None:
                    if shape_name == "RIBBON":
                        no_bars.append(r["symbol"] + " " + r["date"])
                    continue
                if res == "UNCOMPUTABLE":
                    uncomputable[label].append(i)
                    continue
                fee, slip = costs_for(r["entry_premium"], r["qty"], res["pnl_gross"])
                trades.append({"key": i, "arm": r["arm"], "date": r["date"],
                               "exit_ts": res["exit_ts"], "pnl_gross": res["pnl_gross"],
                               "fee": fee, "slip": slip, "hold_min": res["hold_min"],
                               "tp1_done": res["tp1_done"], "reason": res["exit_reason"],
                               "qty": r["qty"]})
            results[(shape_name, label)] = trades
            per_trade[shape_name + "|" + label] = trades

    return m, rows, results, per_trade, uncomputable, no_bars


if __name__ == "__main__":
    m, rows, results, per_trade, uncomputable, no_bars = main()
    print("cells:", len(results), "no_bars:", len(set(no_bars)))
    for k, v in uncomputable.items():
        print("UNCOMPUTABLE", k, len(v))
    base = results[("RIBBON", "NO_STOP (15:40 time stop only)")]
    print("sanity NONE gross", round(sum(t["pnl_gross"] for t in base), 2), "n", len(base))
