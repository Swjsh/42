#!/usr/bin/env python
"""HOLD-TIME MATRIX -- what a pure clock-based exit would have returned on every trade we
have ever taken.

QUESTION (J, 2026-08-19): "one specifically for fine tuning bigger winners ... full matrix on
every single trade we've ever taken."  The lever under test is HOLD TIME: are winners being
cut early, or held too long?

DATASET  analysis/recommendations/trade-matrix.json (303 closed round trips, 5 arms,
         35 trading days, 2026-06-26..2026-08-19) + backtest/data/opra_1m_cache full-day
         OPRA 1-minute bars (09:30 -> ~16:14 ET, 109/109 contract-days cached).

NO LOOK-AHEAD (C6). A clock exit needs only the clock: at entry_ts + T minutes we sell.
Nothing in the pricing consults a future bar.  The one figure that IS backward-looking --
"how long after our actual exit did the day's MFE occur" -- is labelled ORACLE / DIAGNOSTIC
everywhere it appears and never enters a shippable cell.

WHY THIS IS NOT trade_autopsy's `hold_to_time` ARTIFACT. That probe used premium_stop -0.95 /
tp1 999 / runner 999 -- a near-stopless unbounded-upside shape that wins any "best
counterfactual" contest by construction, which is exactly why it was quarantined as an oracle
on 2026-08-06.  This module reports EVERY cell of the grid with its own concentration, never a
max-over-cells, and prices exits with the same measured sell model on both sides.

ACCOUNTING (two layers, both reported, never mixed)
  GROSS   production = the recorded broker P&L (real_pnl_gross).  Counterfactual = bar close
          at the exit minute.  No fees, no spread model.
  NET     BOTH sides repriced with ONE symmetric sell model, then real regulatory fees:
            sell fill = low + SELL_POS_IN_RANGE * (high - low)   [SELL_POS_IN_RANGE = 1/3]
          0.333 is the position a genuine bid-hit implies; our recorded exits sat at 0.462,
          i.e. 0.129 of range too good (analysis/deep-research/COST-REALISM-2026-08-18.md).
          Applying it to production too is what makes the delta apples-to-apples -- crediting
          production its optimistic recorded fill while charging the counterfactual a
          realistic one would manufacture an edge out of the accounting.
          Fees: setup/scripts/cost_model.fee_breakdown (OCC+ORF+TAF+SEC, ex-CAT).

Read-only. Places no orders, edits no params, arms nothing.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from cost_model import fee_breakdown  # noqa: E402

ET = ZoneInfo("America/New_York")
MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"
OPRA = REPO / "backtest" / "data" / "opra_1m_cache"
OUT_JSON = REPO / "analysis" / "deep-research" / "WINNERS-HOLD-TIME-MATRIX-2026-08-19.json"

FLATTEN_HHMM = (15, 50)          # CLAUDE.md hard time-stop
SELL_POS_IN_RANGE = 1.0 / 3.0    # measured realistic bid-hit position (COST-REALISM)
MIN_RANGE_USD = 0.02             # thinner than this cannot locate a fill in the range
HOLD_GRID = [3, 5, 8, 10, 12, 15, 18, 20, 22, 25, 30, 35, 40, 45, 60, 90, 120]
CAT_CAP_PCT = -0.50              # shipped catastrophe cap, for the capped variant
HOUR_BUCKETS = [
    ("09:30-10:00", 0, 30), ("10:00-11:00", 30, 90), ("11:00-12:00", 90, 150),
    ("12:00-13:00", 150, 210), ("13:00-14:00", 210, 270), ("14:00-15:00", 270, 330),
    ("15:00-15:50", 330, 380),
]


# ------------------------------------------------------------------ bars
def load_bars(symbol: str, date: str):
    p = OPRA / f"{symbol}_{date}.csv"
    if not p.exists():
        return None
    out = []
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                ts = dt.datetime.fromisoformat(str(r["t"]).replace("Z", "+00:00"))
                ts = ts.astimezone(ET).replace(tzinfo=None)
                out.append({"ts": ts, "o": float(r["o"]), "h": float(r["h"]),
                            "l": float(r["l"]), "c": float(r["c"])})
            except (KeyError, TypeError, ValueError):
                continue
    out.sort(key=lambda b: b["ts"])
    return out or None


def parse_et(s):
    return dt.datetime.fromisoformat(str(s)) if s else None


def sell_price(bar: dict) -> float:
    """Realistic market-SELL fill inside one traded minute. Thin range -> close (a one-trade
    minute carries no locatable position; never defaulted to the midpoint)."""
    rng = bar["h"] - bar["l"]
    if rng < MIN_RANGE_USD:
        return bar["c"]
    return bar["l"] + SELL_POS_IN_RANGE * rng


def bar_at_or_before(bars, ts, not_before):
    """Last bar with not_before <= bar.ts <= ts. Returns (bar, staleness_minutes) or None."""
    best = None
    for b in bars:
        if b["ts"] > ts:
            break
        if b["ts"] >= not_before:
            best = b
    if best is None:
        return None
    return best, round((ts - best["ts"]).total_seconds() / 60.0, 1)


def fee_of(entry_premium: float, qty: int, gross_pnl: float) -> float:
    return float(fee_breakdown({"entry_premium": entry_premium, "qty": qty,
                                "real_pnl": gross_pnl})["fee_total_ex_cat"])


def clock_exit(t: dict, T, cap):
    """Sell the FULL position T minutes after entry (or at 15:50 when T is None).
    `cap` (e.g. -0.50) additionally exits early the first minute the premium trades at or
    below entry*(1+cap) -- the shipped catastrophe cap, decidable in real time."""
    entry_ts, ep, qty = t["entry_ts"], t["entry_premium"], t["qty"]
    target = t["flatten_ts"] if T is None else min(entry_ts + dt.timedelta(minutes=T),
                                                   t["flatten_ts"])
    entry_min = entry_ts.replace(second=0, microsecond=0)

    stopped_at = None
    if cap is not None:
        cap_price = ep * (1.0 + cap)
        for b in t["bars"]:
            if b["ts"] <= entry_min or b["ts"] > target:
                continue
            if b["l"] <= cap_price:
                # market stop -> fills at the cap or worse; take the more conservative of
                # the cap price and the minute's own realistic sell.
                stopped_at = (b, min(cap_price, sell_price(b)))
                break

    if stopped_at is not None:
        bar, px_real = stopped_at
        px_gross = min(ep * (1.0 + cap), bar["c"])
        stale = 0.0
        reason = "cap50"
    else:
        hit = bar_at_or_before(t["bars"], target, entry_min)
        if hit is None:
            return None                     # UNPRICEABLE -- reported, never zero-filled
        bar, stale = hit
        px_gross, px_real = bar["c"], sell_price(bar)
        reason = "clock"

    gross = round((px_gross - ep) * qty * 100.0, 2)
    gross_real = round((px_real - ep) * qty * 100.0, 2)
    return {"gross": gross,
            "net": round(gross_real - fee_of(ep, qty, gross_real), 2),
            "exit_px_gross": round(px_gross, 4), "exit_px_realistic": round(px_real, 4),
            "exit_ts": bar["ts"].isoformat(), "staleness_min": stale, "reason": reason,
            "held_min": round((bar["ts"] - entry_ts).total_seconds() / 60.0, 1)}


# ------------------------------------------------------------------ per-trade engine
def build_trades():
    doc = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = doc["rows"]
    trades, skipped = [], []
    bar_cache = {}

    for r in rows:
        key = (r["symbol"], r["date"])
        if key not in bar_cache:
            bar_cache[key] = load_bars(*key)
        bars = bar_cache[key]
        entry_ts = parse_et(r["entry_ts_et"])
        exit_ts = parse_et(r["exit_ts_et"])
        qty = int(r["qty"])
        ep = float(r["entry_premium"])
        if bars is None or entry_ts is None or exit_ts is None or qty <= 0 or ep <= 0:
            skipped.append({"arm": r["arm"], "date": r["date"], "symbol": r["symbol"],
                            "reason": "no bars / malformed row",
                            "real_pnl_gross": r["real_pnl_gross"]})
            continue

        d = entry_ts.date()
        flatten_ts = dt.datetime(d.year, d.month, d.day, *FLATTEN_HHMM)
        entry_min = entry_ts.replace(second=0, microsecond=0)
        # entry-bar-EXCLUSIVE forward window: bars strictly after the entry minute, so no
        # pre-entry tick inside the signal bar can contaminate a forward statistic.
        fwd = [b for b in bars if entry_min < b["ts"] <= flatten_ts]

        t = {
            "arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "side": r["side"],
            "qty": qty, "entry_premium": ep, "entry_ts": entry_ts, "exit_ts": exit_ts,
            "flatten_ts": flatten_ts, "bars": bars, "fwd": fwd,
            "minutes_since_open": r["minutes_since_open"],
            "hold_minutes": r["hold_minutes"], "exit_stage": r.get("exit_stage"),
            "moneyness": r.get("moneyness"), "setup": r.get("setup"),
            "prod_gross": float(r["real_pnl_gross"]),
            "prod_fee": float(r["fee_total_ex_cat"]),
            "prod_net_recorded": float(r["real_pnl_net"]),
            "exit_legs": r.get("exit_legs") or [],
            "exit_premium": r.get("exit_premium"),
        }

        # ---------- production, repriced with the symmetric sell model (NET layer baseline)
        legs = t["exit_legs"]
        if not legs and r.get("exit_premium") is not None:
            legs = [{"ts_et": r["exit_ts_et"], "qty": qty, "price": r["exit_premium"]}]
        proceeds, leg_qty, leg_ok = 0.0, 0, True
        for lg in legs:
            lts = parse_et(lg.get("ts_et"))
            lq = int(lg.get("qty") or 0)
            if lts is None or lq <= 0:
                leg_ok = False
                break
            hit = bar_at_or_before(bars, lts, entry_min)
            if hit is None:
                leg_ok = False
                break
            proceeds += sell_price(hit[0]) * lq
            leg_qty += lq
        if leg_ok and leg_qty == qty:
            t["prod_gross_realistic"] = round((proceeds - ep * qty) * 100.0, 2)
            t["prod_reprice_ok"] = True
        else:
            # Never silently substitute: fall back to the recorded fill and flag the row.
            t["prod_gross_realistic"] = t["prod_gross"]
            t["prod_reprice_ok"] = False
        t["prod_net"] = round(t["prod_gross_realistic"]
                              - fee_of(ep, qty, t["prod_gross_realistic"]), 2)

        # ---------- day MFE / MAE, entry-bar-exclusive, entry -> 15:50 (ORACLE diagnostic)
        if fwd:
            hi = max(fwd, key=lambda b: b["h"])
            lo = min(fwd, key=lambda b: b["l"])
            t["day_mfe_premium"] = hi["h"]
            t["day_mfe_minute"] = round((hi["ts"] - entry_ts).total_seconds() / 60.0, 1)
            t["day_mfe_pct"] = round(hi["h"] / ep - 1.0, 4)
            t["day_mae_premium"] = lo["l"]
            t["day_mae_minute"] = round((lo["ts"] - entry_ts).total_seconds() / 60.0, 1)
            t["day_mae_pct"] = round(lo["l"] / ep - 1.0, 4)
            t["mfe_after_exit_minutes"] = round(
                t["day_mfe_minute"] - float(r["hold_minutes"]), 1)
        else:
            for k in ("day_mfe_premium", "day_mfe_minute", "day_mfe_pct", "day_mae_premium",
                      "day_mae_minute", "day_mae_pct", "mfe_after_exit_minutes"):
                t[k] = None

        # ---------- clock-exit cells
        t["cells"] = {}
        for T in HOLD_GRID:
            t["cells"]["T%d" % T] = clock_exit(t, T, cap=None)
            t["cells"]["T%d_cap50" % T] = clock_exit(t, T, cap=CAT_CAP_PCT)
        t["cells"]["EOD"] = clock_exit(t, None, cap=None)
        t["cells"]["EOD_cap50"] = clock_exit(t, None, cap=CAT_CAP_PCT)
        trades.append(t)
    return trades, {"skipped": skipped}


# ------------------------------------------------------------------ aggregation
def max_drawdown_by_day(day_pnl):
    cum, peak, mdd = 0.0, 0.0, 0.0
    for d in sorted(day_pnl):
        cum += day_pnl[d]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return round(mdd, 2)


def share(top, total):
    if not total:
        return None
    return round(top / total, 4)


def summarise(vals, label):
    """vals = [(date, pnl_of_one_trade)]"""
    pnls = [v for _, v in vals]
    n = len(pnls)
    if n == 0:
        return {"cell": label, "n": 0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    day = defaultdict(float)
    for d, p in vals:
        day[d] += p
    total = sum(pnls)
    top_day = max(day.items(), key=lambda kv: abs(kv[1])) if day else ("", 0.0)
    top_trade = max(pnls, key=abs)
    win_dollars = sum(wins)
    top_win = max(wins) if wins else 0.0
    return {
        "cell": label, "n": n, "total": round(total, 2),
        "win_rate": round(len(wins) / n, 4),
        "avg_win": round(statistics.fmean(wins), 2) if wins else None,
        "avg_loss": round(statistics.fmean(losses), 2) if losses else None,
        "median": round(statistics.median(pnls), 2),
        "max_drawdown": max_drawdown_by_day(day),
        "best_day": [top_day[0], round(top_day[1], 2)],
        "top_day_share_of_total": share(top_day[1], total),
        "top_trade": round(top_trade, 2),
        "top_trade_share_of_total": share(top_trade, total),
        "top_win_share_of_winner_dollars": share(top_win, win_dollars),
        "n_days_positive": sum(1 for v in day.values() if v > 0),
        "n_days": len(day),
    }


CLUSTER_GAP_S = 3600   # 60 min -- yields 84 clusters, inside the repo's established 60-90


def clusters_of(trades, gap_s: int = CLUSTER_GAP_S):
    """Signal-level clustering: same date + same side, entries within `gap_s` of the cluster
    seed. The 5 arms fire one shared signal (r=0.846, 95.7% sign agreement), so the ROW count
    is not a sample size -- the cluster count is the decision count. 60 min is the
    conservative choice: it lands at 84, inside the 60-90 the repo already reconciled, and a
    wider cluster means a WIDER bootstrap CI, never a flattering one."""
    idx = sorted(range(len(trades)), key=lambda i: (trades[i]["date"], trades[i]["side"],
                                                    trades[i]["entry_ts"]))
    out, cur, seed = [], [], None
    for i in idx:
        t = trades[i]
        if (seed is not None and t["date"] == trades[seed]["date"]
                and t["side"] == trades[seed]["side"]
                and (t["entry_ts"] - trades[seed]["entry_ts"]).total_seconds() <= gap_s):
            cur.append(i)
        else:
            if cur:
                out.append(cur)
            cur, seed = [i], i
    if cur:
        out.append(cur)
    return out


def bootstrap_delta(trades, cell, layer, cl, iters=4000, seed=42):
    """Resample CLUSTERS (not rows) with replacement -> CI on the delta vs production."""
    import random
    rng = random.Random(seed)
    per_cluster = []
    for c in cl:
        d = 0.0
        for i in c:
            t = trades[i]
            cv = t["cells"].get(cell)
            if cv is None:
                continue
            d += cv[layer] - (t["prod_gross"] if layer == "gross" else t["prod_net"])
        per_cluster.append(d)
    k = len(per_cluster)
    if k == 0:
        return None
    tot = sum(per_cluster)
    draws = []
    for _ in range(iters):
        draws.append(sum(per_cluster[rng.randrange(k)] for _ in range(k)))
    draws.sort()
    return {"observed_delta": round(tot, 2), "clusters": k,
            "ci95": [round(draws[int(0.025 * iters)], 2), round(draws[int(0.975 * iters)], 2)],
            "p_delta_gt_0": round(sum(1 for x in draws if x > 0) / iters, 4)}


def main() -> int:
    trades, meta = build_trades()
    cl = clusters_of(trades)
    cells = (["T%d" % T for T in HOLD_GRID] + ["EOD"]
             + ["T%d_cap50" % T for T in HOLD_GRID] + ["EOD_cap50"])

    report = {
        "_doc": "Hold-time matrix -- pure clock exits on all 303 closed round trips.",
        "generated_at_et": dt.datetime.now(ET).replace(tzinfo=None).isoformat(timespec="seconds"),
        "source": "analysis/recommendations/trade-matrix.json",
        "n_rows": len(trades), "n_clusters": len(cl),
        "n_skipped": len(meta["skipped"]), "skipped": meta["skipped"],
        "sell_model": {"position_in_range": round(SELL_POS_IN_RANGE, 4),
                       "provenance": "COST-REALISM-2026-08-18.md: BUY 0.667 / SELL 0.462; a "
                                     "genuine bid-hit implies ~0.333, so recorded exits are "
                                     "0.129 of range too good. Applied to BOTH sides."},
        "flatten_et": "15:50", "hold_grid_minutes": HOLD_GRID,
        "catastrophe_cap_pct": CAT_CAP_PCT,
    }

    # ---- production baseline
    report["production"] = {
        "gross": summarise([(t["date"], t["prod_gross"]) for t in trades], "PRODUCTION"),
        "net": summarise([(t["date"], t["prod_net"]) for t in trades], "PRODUCTION"),
        "net_as_recorded_total": round(sum(t["prod_net_recorded"] for t in trades), 2),
        "reprice_failures": sum(1 for t in trades if not t["prod_reprice_ok"]),
        "median_hold_minutes": round(statistics.median([t["hold_minutes"] for t in trades]), 2),
    }

    # ---- the matrix
    matrix = {}
    for cell in cells:
        priced = [t for t in trades if t["cells"].get(cell) is not None]
        g = summarise([(t["date"], t["cells"][cell]["gross"]) for t in priced], cell)
        n_ = summarise([(t["date"], t["cells"][cell]["net"]) for t in priced], cell)
        dg = [(t["date"], t["cells"][cell]["gross"] - t["prod_gross"]) for t in priced]
        dn = [(t["date"], t["cells"][cell]["net"] - t["prod_net"]) for t in priced]
        matrix[cell] = {
            "n_priced": len(priced), "n_unpriceable": len(trades) - len(priced),
            "gross": g, "net": n_,
            "delta_gross": summarise(dg, cell + " dgross"),
            "delta_net": summarise(dn, cell + " dnet"),
            "median_staleness_min": round(statistics.median(
                [t["cells"][cell]["staleness_min"] for t in priced]), 2) if priced else None,
            "n_cap_stopped": sum(1 for t in priced if t["cells"][cell]["reason"] == "cap50"),
            "median_effective_hold_min": round(statistics.median(
                [t["cells"][cell]["held_min"] for t in priced]), 1) if priced else None,
        }
    report["matrix"] = matrix

    # ---- time-of-day cross
    tod = {}
    for name, lo, hi in HOUR_BUCKETS:
        sub = [t for t in trades if lo <= (t["minutes_since_open"] or -1) < hi]
        if not sub:
            continue
        row = {"n": len(sub),
               "production_net": round(sum(t["prod_net"] for t in sub), 2),
               "production_gross": round(sum(t["prod_gross"] for t in sub), 2),
               "median_actual_hold_min": round(statistics.median(
                   [t["hold_minutes"] for t in sub]), 1),
               "cells": {}}
        for cell in cells:
            pr = [t for t in sub if t["cells"].get(cell) is not None]
            if not pr:
                continue
            row["cells"][cell] = {
                "n": len(pr),
                "net": round(sum(t["cells"][cell]["net"] for t in pr), 2),
                "gross": round(sum(t["cells"][cell]["gross"] for t in pr), 2),
                "win_rate": round(sum(1 for t in pr if t["cells"][cell]["net"] > 0) / len(pr), 4),
            }
        tod[name] = row
    report["time_of_day"] = tod

    # ---- ORACLE: where did the day's MFE actually sit relative to our exit
    have = [t for t in trades if t["mfe_after_exit_minutes"] is not None]
    after = [t for t in have if t["mfe_after_exit_minutes"] > 0]
    dm = sorted(t["mfe_after_exit_minutes"] for t in have)

    def pct(seq, q):
        return round(seq[min(len(seq) - 1, int(q * len(seq)))], 1) if seq else None

    report["mfe_timing_oracle"] = {
        "_warning": "BACKWARD-LOOKING DIAGNOSTIC. Knowing where the day's high sat is not a "
                    "tradeable rule; it only says whether the tail was still available after "
                    "we left. Never quote as a P&L opportunity.",
        "n": len(have),
        "n_mfe_after_our_exit": len(after),
        "pct_mfe_after_our_exit": round(len(after) / len(have), 4) if have else None,
        "minutes_after_exit_to_day_mfe": {
            "p10": pct(dm, 0.10), "p25": pct(dm, 0.25), "median": pct(dm, 0.50),
            "p75": pct(dm, 0.75), "p90": pct(dm, 0.90),
            "mean": round(statistics.fmean(dm), 1) if dm else None},
        "median_day_mfe_pct": round(statistics.median(
            [t["day_mfe_pct"] for t in have]), 4) if have else None,
        "median_day_mfe_minute": round(statistics.median(
            [t["day_mfe_minute"] for t in have]), 1) if have else None,
        "median_day_mfe_minute_winners": round(statistics.median(
            [t["day_mfe_minute"] for t in have if t["prod_gross"] > 0]), 1)
            if any(t["prod_gross"] > 0 for t in have) else None,
        "median_day_mfe_minute_losers": round(statistics.median(
            [t["day_mfe_minute"] for t in have if t["prod_gross"] <= 0]), 1)
            if any(t["prod_gross"] <= 0 for t in have) else None,
        "pct_day_mfe_within_first_10_min": round(sum(
            1 for t in have if t["day_mfe_minute"] <= 10) / len(have), 4) if have else None,
        "pct_day_mfe_never_above_entry": round(sum(
            1 for t in have if t["day_mfe_pct"] <= 0) / len(have), 4) if have else None,
    }

    # ---- ROBUSTNESS: is the cell an edge, or is it one day wearing a costume?
    #      Leave-one-DAY-out is the right unit here: the 5 arms fire one shared signal, so a
    #      single trend day enters the book five times and a row-level jackknife would hide it.
    all_days = sorted({t["date"] for t in trades})
    robust = {}
    for cell in cells:
        by_day = defaultdict(float)
        for t in trades:
            cv = t["cells"].get(cell)
            if cv is None:
                continue
            by_day[t["date"]] += cv["net"] - t["prod_net"]
        tot = sum(by_day.values())
        if not by_day:
            continue
        best_day = max(by_day.items(), key=lambda kv: kv[1])
        worst_day = min(by_day.items(), key=lambda kv: kv[1])
        lodo = {d: round(tot - by_day.get(d, 0.0), 2) for d in all_days}
        pos_days = sum(1 for v in by_day.values() if v > 0)
        robust[cell] = {
            "delta_net_total": round(tot, 2),
            "best_day": [best_day[0], round(best_day[1], 2)],
            "best_day_share_of_delta": share(best_day[1], tot),
            "worst_day": [worst_day[0], round(worst_day[1], 2)],
            "delta_ex_best_day": round(tot - best_day[1], 2),
            "worst_leave_one_day_out": min(lodo.values()),
            "days_delta_positive": pos_days, "days_total": len(by_day),
            "day_sign_rate": round(pos_days / len(by_day), 4),
            "median_daily_delta": round(statistics.median(by_day.values()), 2),
        }
    report["robustness_lodo"] = robust

    # ---- SURVIVABILITY: Rule 5 kill switches are per-account and per-DAY. A cell whose
    #      worst modelled day exceeds an arm's daily loss budget is not merely worse -- it is
    #      unreachable, because the account halts before the day finishes.
    equity = {}
    for t in trades:
        equity.setdefault(t["arm"], []).append(t["entry_premium"] * t["qty"] * 100.0)
    surv = {}
    for cell in cells:
        per_arm_day = defaultdict(float)
        for t in trades:
            cv = t["cells"].get(cell)
            if cv is None:
                continue
            per_arm_day[(t["arm"], t["date"])] += cv["net"]
        worst = min(per_arm_day.items(), key=lambda kv: kv[1]) if per_arm_day else None
        surv[cell] = {
            "worst_arm_day_net": round(worst[1], 2) if worst else None,
            "worst_arm_day": list(worst[0]) if worst else None,
            "n_arm_days_worse_than_-600": sum(1 for v in per_arm_day.values() if v < -600.0),
            "n_arm_days": len(per_arm_day),
        }
    report["survivability"] = surv

    # ---- n_effective, three ways -- stated, never assumed
    by_date_side = len({(t["date"], t["side"]) for t in trades})
    report["n_effective"] = {
        "rows": len(trades),
        "clusters_signal_60min": len(cl),
        "clusters_date_side_5min": len(clusters_of(trades, 300)),
        "clusters_date_side_30min": len(clusters_of(trades, 1800)),
        "clusters_date_side": by_date_side,
        "trading_days": len(all_days),
        "note": "The 5 arms trade ONE shared signal (r=0.846, 95.7% sign agreement). The "
                "defensible decision count is the date+side cluster count, not the row count.",
    }

    # ---- NOISE BAND: how far does the book move for a 2-3 minute shift of the exit clock?
    #      If neighbouring cells differ by as much as the best cell beats production, the grid
    #      is reading 1-minute premium wiggle, not a hold-time mechanism.
    plain = ["T%d" % T for T in HOLD_GRID]
    adj = []
    for a, b in zip(plain, plain[1:]):
        adj.append({"pair": "%s->%s" % (a, b),
                    "d_minutes": int(b[1:]) - int(a[1:]),
                    "d_net": round(matrix[b]["net"]["total"] - matrix[a]["net"]["total"], 2)})
    mid = [x for x in adj if 5 <= int(x["pair"].split("->")[0][1:]) <= 30]
    report["noise_band"] = {
        "adjacent_cells": adj,
        "mean_abs_adjacent_move_net_5_to_30min": round(
            statistics.fmean([abs(x["d_net"]) for x in mid]), 2) if mid else None,
        "max_abs_adjacent_move_net_5_to_30min": round(
            max(abs(x["d_net"]) for x in mid), 2) if mid else None,
        "reading": "Compare against the best cell's delta vs production. A best-cell delta "
                   "inside this band is not a hold-time effect, it is grid noise.",
    }

    # ---- SPLIT-HALF OUT-OF-SAMPLE: pick the best T on the first half of the calendar, then
    #      spend it on the second half (and the reverse). This is the only question that
    #      matters -- an in-sample argmax is guaranteed to look good.
    half = len(all_days) // 2
    seg = {"first": set(all_days[:half]), "second": set(all_days[half:])}

    def delta_on(cell, days):
        s = 0.0
        for t in trades:
            if t["date"] not in days:
                continue
            cv = t["cells"].get(cell)
            if cv is not None:
                s += cv["net"] - t["prod_net"]
        return round(s, 2)

    wf = {}
    for train, test in (("first", "second"), ("second", "first")):
        scored = sorted(cells, key=lambda c: -delta_on(c, seg[train]))
        pick = scored[0]
        pick_plain = sorted(plain, key=lambda c: -delta_on(c, seg[train]))[0]
        wf["train_%s_test_%s" % (train, test)] = {
            "days_train": len(seg[train]), "days_test": len(seg[test]),
            "best_cell_in_train": pick,
            "delta_in_train": delta_on(pick, seg[train]),
            "delta_in_test": delta_on(pick, seg[test]),
            "best_plain_cell_in_train": pick_plain,
            "plain_delta_in_train": delta_on(pick_plain, seg[train]),
            "plain_delta_in_test": delta_on(pick_plain, seg[test]),
        }
    report["split_half_oos"] = wf

    # ---- ranking + bootstrap on the leaders
    ranked = sorted(cells, key=lambda c: -matrix[c]["net"]["total"])
    report["ranking_by_net"] = [{"cell": c, "net": matrix[c]["net"]["total"],
                                 "gross": matrix[c]["gross"]["total"],
                                 "win_rate": matrix[c]["net"]["win_rate"]} for c in ranked]
    boot_cells = list(dict.fromkeys(ranked[:5] + ["EOD", "T30", "T15", "T10"]))
    report["bootstrap"] = {c: {"gross": bootstrap_delta(trades, c, "gross", cl),
                               "net": bootstrap_delta(trades, c, "net", cl)}
                           for c in boot_cells}

    # ---- per-trade export for the write-up (lean fields only)
    report["trades"] = [{
        "arm": t["arm"], "date": t["date"], "symbol": t["symbol"], "side": t["side"],
        "qty": t["qty"], "entry_premium": t["entry_premium"],
        "entry_ts": t["entry_ts"].isoformat(), "hold_minutes": t["hold_minutes"],
        "minutes_since_open": t["minutes_since_open"], "exit_stage": t["exit_stage"],
        "prod_gross": t["prod_gross"], "prod_net": t["prod_net"],
        "prod_reprice_ok": t["prod_reprice_ok"],
        "day_mfe_pct": t["day_mfe_pct"], "day_mfe_minute": t["day_mfe_minute"],
        "mfe_after_exit_minutes": t["mfe_after_exit_minutes"],
        "cells": {c: (t["cells"][c]["net"] if t["cells"].get(c) else None) for c in cells},
        "cells_gross": {c: (t["cells"][c]["gross"] if t["cells"].get(c) else None)
                        for c in cells},
    } for t in trades]

    OUT_JSON.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("wrote %s" % OUT_JSON)
    print("rows %d  clusters %d  skipped %d" % (len(trades), len(cl), len(meta["skipped"])))
    print("production gross %.2f  net(realistic) %.2f  net(as recorded) %.2f"
          % (report["production"]["gross"]["total"], report["production"]["net"]["total"],
             report["production"]["net_as_recorded_total"]))
    for c in ranked:
        m, rb = matrix[c], report["robustness_lodo"][c]
        print("  %-12s n=%3d gross=%9.2f net=%9.2f wr=%.3f mdd=%9.2f "
              "dnet=%9.2f exBest=%9.2f bestShare=%s dayPos=%d/%d"
              % (c, m["n_priced"], m["gross"]["total"], m["net"]["total"],
                 m["net"]["win_rate"], m["net"]["max_drawdown"],
                 rb["delta_net_total"], rb["delta_ex_best_day"],
                 rb["best_day_share_of_delta"], rb["days_delta_positive"], rb["days_total"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
