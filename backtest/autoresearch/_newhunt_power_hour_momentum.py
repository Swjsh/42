"""POWER-HOUR MOMENTUM — real-fills hunt for a 0DTE SPY time-of-day edge.

STRATEGY (sourced, not invented)
================================
Gao, Han, Li & Zhou, "Market Intraday Momentum" (Journal of Financial Economics,
2018; SSRN 2440866). 20 years of SPY (1993-2013): the FIRST half-hour return
(prior-day close -> 10:00 ET) predicts the LAST half-hour return (15:30->16:00 ET).
Their "market-timing strategy": at the START of the last half hour (15:30 ET) go
LONG if the first-half-hour return was positive, SHORT if negative, hold to the
close (16:00 ET). Predictive R^2 = 1.6% (first-half alone), 2.6% combined with the
12th half-hour (15:00-15:30), stronger on high-vol / high-volume / news days.
Sources:
  - SSRN 2440866  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866
  - JFE 2018      https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351
  - QuantConnect replication (exact rule: sign of AM return -> long/short, enter
    30m before close, MOC exit): https://www.quantconnect.com/learning/articles/investment-strategy-library/intraday-etf-momentum
  - QuantifiedStrategies "last hour" momentum framing:
    https://www.quantifiedstrategies.com/last-hour-trading-strategy-in-sp-500/

HONEST PRIOR (disclosed up front, OP-20 anti-theatre): QuantConnect's own
out-of-sample replication of the rule on SPY 2015-2020 produced a NEGATIVE Sharpe
(-0.628) — the published 1993-2013 edge degraded badly in the modern, low-vol,
0DTE-flow-dominated regime. So the base rate going in is unfavorable; this hunt
tests whether the rule survives on OUR 2025-2026 SPY data through REAL 0DTE option
fills (the only WR authority, C1) — not whether the abstract underlying drift is
real.

0DTE ADAPTATION (faithful to the rule, fit to our single-leg engine)
====================================================================
- Signal time: the 15:30 ET bar. first_half = close(10:00 ET) / prior_RTH_close - 1.
  (Optional "combined" mode also requires the 12th-half-hour 15:00->15:30 move to
   agree in sign — the paper's stronger R^2=2.6% predictor.)
- side: "C" (CALL) if first_half > +eps, "P" (PUT) if first_half < -eps, else skip.
- Entry fills on the NEXT bar (~15:35 ET) via simulator_real (no look-ahead).
- Exit: v15 default exits — the 15:50 ET time stop IS the "hold into the close"
  EOD exit for a 0DTE single leg (paper holds 15:30->16:00; our hard flatten is
  15:50). chart-stop / TP1 / ribbon left at v15 defaults.
- rejection_level (chart invalidation, makes the chart-stop meaningful): for a CALL
  the session intraday LOW so far (support below); for a PUT the session HIGH so far
  (resistance above). This is the "the day's trend is invalidated if we lose the
  day's extreme" reading.
- ONE signal per day by construction (single 15:30 evaluation) -> cooldown is moot,
  but we still guard >=30min spacing defensively.

GRID (small, per the brief): strike_offset {-2,-1,0,1,2} x premium_stop_pct
{-0.08,-0.20,-0.50,-0.99}. v15 default exits otherwise.

SELF-VERIFY (deterministic, in-script — NO agents): for the best cell by overall
per-trade expectancy, compute IS(2025)/OOS(2026), positive_quarters/6, top5-day
concentration, and drop-top-5-days per-trade. CANDIDATE BAR (all must hold):
  OOS per-trade > 0  AND  positive_quarters >= 4/6  AND  top5 < 200%  AND
  n >= 20  AND  drop-top-5 per-trade > 0.

Pure Python, $0, no live orders. Writes
analysis/recommendations/newhunt-power-hour-momentum.json.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "newhunt-power-hour-momentum.json"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
QTY = 3

# --- exact strategy times (naive ET — our CSV clock IS ET; see data audit) ----
FIRST_HALF_END = dt.time(10, 0)     # first half-hour return measured to 10:00 ET
TWELFTH_START = dt.time(15, 0)      # 12th half-hour 15:00->15:30 (combined predictor)
SIGNAL_TIME = dt.time(15, 30)       # enter at start of last half hour
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE_LAST = dt.time(15, 55)    # last RTH bar (16:00 bar excluded by <16:00 filter)

EPS = 0.0005   # |first_half| must exceed 5bps to call a direction (avoid coin-flip flat days)
COOLDOWN_MIN = 30

GRID_STRIKE_OFFSET = [-2, -1, 0, 1, 2]
GRID_PREMIUM_STOP = [-0.08, -0.20, -0.50, -0.99]


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self) -> None:
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str) -> None:
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "avg_pnl": round(self.pnl / self.n, 1),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _load_rth() -> pd.DataFrame:
    """RTH 09:30-15:55 ET, naive-ET clock, with per-day helper columns."""
    spy, _vix = ar_runner.load_data(START, END)
    spy["ts"] = pd.to_datetime(spy["timestamp_et"])
    # CSV tz label is inconsistent; the naive wall-clock IS the real ET time
    # (09:30 open / 15:55 close both present; extended-hours bars 04:00-17:55 also
    # present). Strip tz and filter to RTH on the naive clock — exactly what the
    # existing *_real_fills_validate.py scripts do.
    naive = spy["ts"].dt.tz_localize(None) if spy["ts"].dt.tz is not None else spy["ts"]
    spy = spy.copy()
    spy["timestamp_et"] = naive          # simulator_real reads entry_bar['timestamp_et']
    spy["clock"] = naive.dt.time
    spy["date"] = naive.dt.date
    rth = spy[(spy["clock"] >= RTH_OPEN) & (spy["clock"] <= RTH_CLOSE_LAST)].reset_index(drop=True)
    return rth


def _bar_at(day_df: pd.DataFrame, clock: dt.time):
    """First bar AT-OR-AFTER `clock` within a single day's RTH frame; None if absent.

    The 5-min grid lands exactly on :00/:30, but guard for missing bars by taking
    the first bar whose clock >= target.
    """
    sub = day_df[day_df["clock"] >= clock]
    return sub.iloc[0] if len(sub) else None


def build_signals(rth: pd.DataFrame, combined: bool) -> list[dict]:
    """One evaluation per day at 15:30 ET. Returns signal dicts (causal — only bars
    up to and including the 15:30 trigger bar are used)."""
    signals: list[dict] = []
    dates = sorted(rth["date"].unique())
    prior_close: float | None = None
    last_sig_time: dt.datetime | None = None

    # index helper: global row index of each (date) block, so simulate_trade_real
    # (which indexes into the full rth frame) gets the right entry_bar_idx.
    rth = rth.reset_index(drop=True)
    rth["_gidx"] = rth.index
    by_date = {d: g for d, g in rth.groupby("date")}

    for d in dates:
        day_df = by_date[d]
        day_close_bar = day_df.iloc[-1]            # last RTH bar of the day (~15:55)
        this_close = float(day_close_bar["close"])

        if prior_close is None or prior_close <= 0:
            prior_close = this_close
            continue  # need a prior-day close to define the first-half return

        # --- first-half-hour return: prior close -> 10:00 ET ---
        bar_1000 = _bar_at(day_df, FIRST_HALF_END)
        sig_bar = day_df[day_df["clock"] == SIGNAL_TIME]
        if bar_1000 is None or len(sig_bar) == 0:
            prior_close = this_close
            continue
        sig_bar = sig_bar.iloc[0]

        first_half = float(bar_1000["close"]) / prior_close - 1.0

        # --- optional combined predictor: 12th half-hour 15:00 -> 15:30 must agree ---
        if combined:
            bar_1500 = day_df[day_df["clock"] == TWELFTH_START]
            if len(bar_1500) == 0:
                prior_close = this_close
                continue
            twelfth = float(sig_bar["close"]) / float(bar_1500.iloc[0]["close"]) - 1.0
        else:
            twelfth = None

        # --- direction from the sign of the first-half-hour return ---
        if first_half > EPS:
            side = "C"
        elif first_half < -EPS:
            side = "P"
        else:
            prior_close = this_close
            continue  # flat AM -> no directional call (paper: stay out at zero)

        if combined and twelfth is not None:
            tw_dir = "C" if twelfth > 0 else ("P" if twelfth < 0 else None)
            if tw_dir != side:    # require agreement (the stronger R^2=2.6% predictor)
                prior_close = this_close
                continue

        # defensive cooldown (one-per-day makes this a no-op, but keep the guard)
        sig_dt = pd.Timestamp(sig_bar["timestamp_et"]).to_pydatetime()
        if last_sig_time is not None and (sig_dt - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            prior_close = this_close
            continue
        last_sig_time = sig_dt

        # --- chart invalidation level: day extreme so far (up to 15:30) ---
        upto = day_df[day_df["clock"] <= SIGNAL_TIME]
        if side == "C":
            rejection_level = float(upto["low"].min())   # support below — lose the day's low = trend dead
        else:
            rejection_level = float(upto["high"].max())  # resistance above

        signals.append({
            "date": d,
            "gidx": int(sig_bar["_gidx"]),
            "side": side,
            "first_half_ret": round(first_half, 5),
            "twelfth_ret": (round(twelfth, 5) if twelfth is not None else None),
            "entry_spot": float(sig_bar["close"]),
            "rejection_level": round(rejection_level, 2),
            "time": SIGNAL_TIME.strftime("%H:%M"),
        })
        prior_close = this_close

    return signals


def run_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
             premium_stop_pct: float) -> dict:
    """Run the real-fills sim for one grid cell. Returns the accumulators + rows."""
    overall = _Acc()
    by_side = {"C": _Acc(), "P": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0
    rows: list[dict] = []

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["gidx"],
            entry_bar=rth.iloc[s["gidx"]],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["power_hour_momentum", "first_half_hour_sign",
                            f"side_{s['side']}"],
            side=s["side"],
            qty=QTY,
            setup="POWER_HOUR_MOMENTUM",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
        if fill is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_side[s["side"]].add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"],
            "first_half_ret": s["first_half_ret"], "twelfth_ret": s["twelfth_ret"],
            "entry_spot": round(s["entry_spot"], 2),
            "rejection_level": s["rejection_level"],
            "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })

    return {
        "overall": overall, "by_side": by_side, "by_sample": by_sample,
        "by_q": by_q, "no_data": no_data, "rows": rows,
    }


def _drop_top5_per_trade(acc: _Acc) -> float | None:
    """Per-trade expectancy after removing the 5 single best DAYS' P&L.

    Conservative: subtract the 5 best days' total pnl from the numerator but keep
    the full trade count in the denominator (we don't know how many trades made up
    those days; one-per-day here, so it's the 5 best trades — exactly the stress
    test we want)."""
    if acc.n == 0:
        return None
    days_sorted = sorted(acc.by_day.values(), reverse=True)
    top5 = sum(days_sorted[:5])
    n_top = min(5, len(days_sorted))
    remaining_pnl = acc.pnl - top5
    remaining_n = acc.n - n_top   # one trade per day in this strategy
    if remaining_n <= 0:
        return None
    return round(remaining_pnl / remaining_n, 2)


def main() -> dict:
    log.info("Loading %s..%s SPY (RTH)...", START, END)
    rth = _load_rth()
    log.info("RTH bars: %d  trading days: %d", len(rth), rth["date"].nunique())

    results: dict = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "power_hour_momentum",
        "window": f"{START}..{END}",
        "modes": {},
    }

    # Evaluate every cell against the FULL candidate bar (not just overall per-trade,
    # which over-weights the IS-heavy combined mode and is itself a cherry-pick trap).
    # We score each cell on all 5 gates, then SELECT among bar-clearing cells.
    all_cells: list[dict] = []   # flat list across modes, each with full gate eval

    def _gate_eval(cell: dict) -> dict:
        ov: _Acc = cell["overall"]
        rep = ov.report()
        is_r = cell["by_sample"]["IS_2025"].report()
        oos_r = cell["by_sample"]["OOS_2026"].report()
        q_reports = {k: cell["by_q"][k].report() for k in sorted(cell["by_q"])}
        pos_q = sum(1 for r in q_reports.values()
                    if r.get("total_pnl") is not None and r["total_pnl"] > 0)
        n_q = len(q_reports)
        drop5 = _drop_top5_per_trade(ov)
        top5 = rep.get("top5_day_pct")
        oos_pt = oos_r.get("avg_pnl")
        n_best = rep.get("n", 0)
        clears = bool(
            oos_pt is not None and oos_pt > 0
            and pos_q >= 4
            and (top5 is not None and top5 < 200)
            and n_best >= 20
            and drop5 is not None and drop5 > 0
        )
        return {
            "rep": rep, "is_r": is_r, "oos_r": oos_r, "q_reports": q_reports,
            "pos_q": pos_q, "n_q": n_q, "drop5": drop5, "top5": top5,
            "oos_pt": oos_pt, "n_best": n_best, "clears": clears,
        }

    for combined in (False, True):
        mode = "combined_2.6pct" if combined else "first_half_only_1.6pct"
        signals = build_signals(rth, combined=combined)
        n_sig = len(signals)
        n_call = sum(1 for s in signals if s["side"] == "C")
        n_put = n_sig - n_call
        log.info("[%s] signals: %d (C=%d P=%d)", mode, n_sig, n_call, n_put)

        cells: list[dict] = []
        for so in GRID_STRIKE_OFFSET:
            for ps in GRID_PREMIUM_STOP:
                cell = run_cell(rth, signals, so, ps)
                g = _gate_eval(cell)
                cell_summary = {
                    "strike_offset": so,
                    "premium_stop_pct": ps,
                    "overall": g["rep"],
                    "oos_per_trade": g["oos_pt"],
                    "positive_quarters": f"{g['pos_q']}/{g['n_q']}",
                    "top5_day_pct": g["top5"],
                    "drop_top5_per_trade": g["drop5"],
                    "clears_bar": g["clears"],
                    "by_side": {k: v.report() for k, v in cell["by_side"].items()},
                    "n_no_opra_data": cell["no_data"],
                }
                cells.append(cell_summary)
                all_cells.append({
                    "mode": mode, "so": so, "ps": ps,
                    "cell": cell, "signals": signals, "n_sig": n_sig, "g": g,
                })

        results["modes"][mode] = {
            "n_signals": n_sig, "n_call": n_call, "n_put": n_put,
            "grid_cells": cells,
        }

    # ── SELECT the cell to report deeply ────────────────────────────────────────
    # Anti-cherry-pick (2.10): prefer cells that CLEAR ALL 5 gates; among those pick
    # the highest OOS per-trade (the gate that actually matters for go-live). If NONE
    # clear, fall back to the highest overall per-trade so the rejection is shown on
    # the strongest IS cell (most-favorable framing for the REJECT, not the weakest).
    clearing = [c for c in all_cells if c["g"]["clears"]]
    n_clearing = len(clearing)
    if clearing:
        pick = max(clearing, key=lambda c: (c["g"]["oos_pt"], c["g"]["rep"].get("avg_pnl", 0)))
    else:
        pick = max(all_cells, key=lambda c: c["g"]["rep"].get("avg_pnl", -1e9))

    mode, so, ps = pick["mode"], pick["so"], pick["ps"]
    cell, signals, n_sig = pick["cell"], pick["signals"], pick["n_sig"]
    g = pick["g"]
    pt = g["rep"].get("avg_pnl")
    ov: _Acc = cell["overall"]
    is_r, oos_r, q_reports = g["is_r"], g["oos_r"], g["q_reports"]
    pos_q, n_q = g["pos_q"], g["n_q"]
    ov_rep = g["rep"]
    drop5, top5, oos_pt, n_best = g["drop5"], g["top5"], g["oos_pt"], g["n_best"]

    # per-month-normalized walk-forward (IS ~12mo Jan-Dec 2025, OOS ~4.5mo 2026)
    is_pm = (is_r.get("total_pnl", 0) / 12.0) if is_r.get("n") else 0.0
    oos_pm = (oos_r.get("total_pnl", 0) / 4.5) if oos_r.get("n") else 0.0
    wf_ratio = round(oos_pm / is_pm, 2) if is_pm > 0 else None

    clears = g["clears"]

    # ── STOP-ROBUSTNESS diagnostic (the decisive honesty check) ─────────────────
    # If a cell only clears at ONE premium_stop value, the "edge" is the stop's
    # loss-cutting, not the time-of-day signal. Count how many of the 4 stops clear
    # at this cell's (mode, strike_offset).
    sibling_stops = [c for c in all_cells
                     if c["mode"] == mode and c["so"] == so]
    stops_clearing = sorted(c["ps"] for c in sibling_stops if c["g"]["clears"])
    stop_robust = len(stops_clearing) >= 2

    verdict_bits = []
    if oos_pt is None or oos_pt <= 0:
        verdict_bits.append(f"OOS per-trade {oos_pt} <= 0")
    if pos_q < 4:
        verdict_bits.append(f"positive_quarters {pos_q}/{n_q} < 4")
    if top5 is None or top5 >= 200:
        verdict_bits.append(f"top5 concentration {top5}% >= 200 (or pnl<=0)")
    if n_best < 20:
        verdict_bits.append(f"n {n_best} < 20")
    if drop5 is None or drop5 <= 0:
        verdict_bits.append(f"drop-top5 per-trade {drop5} <= 0")

    if not clears:
        verdict = "REJECT — " + "; ".join(verdict_bits)
    elif not stop_robust:
        # Clears the 5 gates but is FRAGILE — survives at only one stop setting.
        verdict = (
            f"WEAK/FRAGILE — clears all 5 gates but ONLY at premium_stop={ps} "
            f"(stops clearing at this strike: {stops_clearing}); the edge is the "
            f"tight -8% stop cutting losers, not the time-of-day signal. Thin "
            f"expectancy (+${pt}/3-lot ~ +${round(pt/QTY,2)}/contract). NOT ship-grade."
        )
    else:
        verdict = (
            f"CANDIDATE — clears all 5 gates AND is stop-robust "
            f"(clears at stops {stops_clearing})"
        )

    best_block = {
        "mode": mode,
        "strike_offset": so,
        "premium_stop_pct": ps,
        "overall": ov_rep,
        "overall_per_trade": pt,
        "by_side": {k: v.report() for k, v in cell["by_side"].items()},
        "IS_2025": is_r,
        "OOS_2026": oos_r,
        "walk_forward_oos_per_month_ratio": wf_ratio,
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{n_q}",
        "top5_day_pct": top5,
        "drop_top5_per_trade": drop5,
        "n_trades": n_best,
        "n_signals": n_sig,
        "n_cells_clearing_bar": n_clearing,
        "stops_clearing_at_this_strike": stops_clearing,
        "stop_robust": stop_robust,
        "clears_bar": clears,
        "verdict": verdict,
        "trades": cell["rows"],
    }
    results["best_cell"] = best_block

    results["DISCLOSURE"] = {
        "authority": "real OPRA fills (C1) — supersedes any SPY-direction proxy",
        "metric": "per-trade EXPECTANCY (avg_pnl) reported, not WR alone (OP-14)",
        "per_trade_overall": pt,
        "per_trade_oos": oos_pt,
        "concentration": f"top5_day_pct={top5}%, drop-top5 per-trade={drop5}",
        "is_oos": f"IS_2025 n={is_r.get('n')} avg={is_r.get('avg_pnl')} | OOS_2026 n={oos_r.get('n')} avg={oos_r.get('avg_pnl')}",
        "positive_quarters": f"{pos_q}/{n_q}",
        "published_prior": ("GHLZ 1993-2013 R^2=1.6%/2.6%; BUT QuantConnect OOS "
                            "replication on SPY 2015-2020 = NEGATIVE Sharpe -0.628. "
                            "Base rate going in is UNFAVORABLE for the modern regime."),
        "n_cells_clearing_bar": n_clearing,
        "stop_robustness": (f"reported cell clears at stops {stops_clearing} "
                            f"(>=2 needed to be called stop-robust; otherwise the "
                            f"edge is the stop, not the signal)"),
        "anti_cherry_pick_2_10": ("ALL 40 cells scored against the full 5-gate bar; "
                                  "the reported cell is the best OOS-per-trade among "
                                  "bar-CLEARING cells (or strongest IS cell if none "
                                  "clear). A cell that clears only at one stop setting "
                                  "is flagged WEAK/FRAGILE, not CANDIDATE."),
        "adaptation_caveat": ("paper holds 15:30->16:00 flat; we route the signal "
                              "through the v15 0DTE single-leg engine (entry ~15:35, "
                              "15:50 hard time-stop = the EOD hold, chart/TP1/ribbon "
                              "exits active). Strike/theta of a 0DTE leg in the last "
                              "25 min is a far harsher test than the paper's index drift."),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    # ── console summary ─────────────────────────────────────────────────────────
    print("\n=== POWER-HOUR MOMENTUM — REAL-FILLS VERDICT ===")
    for m, blk in results["modes"].items():
        print(f"[{m}] signals={blk['n_signals']} (C={blk['n_call']} P={blk['n_put']})")
    print(f"\nCells clearing all 5 gates: {n_clearing}/40")
    print(f"REPORTED CELL: mode={mode} strike_offset={so} premium_stop={ps}")
    print(f"  overall : {ov_rep}")
    print(f"  per_trade(overall)={pt}  per_trade(OOS)={oos_pt}")
    print(f"  IS 2025 : {is_r}")
    print(f"  OOS 2026: {oos_r}  wf_per_month={wf_ratio}")
    print(f"  by_side : C={best_block['by_side']['C']}  P={best_block['by_side']['P']}")
    print(f"  pos_quarters={pos_q}/{n_q}  by_quarter={q_reports}")
    print(f"  top5_day_pct={top5}%  drop_top5_per_trade={drop5}")
    print(f"  stops clearing at this strike: {stops_clearing}  stop_robust={stop_robust}")
    print(f"  VERDICT : {verdict}")
    return results


if __name__ == "__main__":
    main()
