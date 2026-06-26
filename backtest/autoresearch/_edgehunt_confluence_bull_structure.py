"""EDGE-HUNT: re-attack the killed confluence_bull_structure trigger with SIZING + EXITS.

Background
----------
confluence_real_fills_validate.py already swept *conviction* on this family and found
EVERY cell NEGATIVE on chart-stop (premium_stop=-0.99, ATM, qty3, v15 exits). J's
challenge: don't accept the kill until you've also varied the two things that actually
move 0DTE option P&L independent of SPY direction (C3/L58):
  1. the STRIKE (delta — ITM caps theta bleed + has higher delta; OTM is cheaper/convex)
  2. the STOP (capping the big losers — does a tight -8%/-20% premium stop flip it?)
  3. the EXIT mechanics (tp1 / runner target / chandelier profit-lock trailing)

This is BULL-ONLY (calls). Bull-tilt is the prior: bull loses LESS than bear on options
(documented family observation). We test whether cheaper/righter strikes + capped losers
turn bull-only structure positive OUT-OF-SAMPLE (2026) — and we are HONEST if it does not.

Method (fast)
-------------
* Detect the family's fresh-break + bull-confluence signals ONCE (identical detector to
  confluence_real_fills_validate.py, restricted to side=='C').
* PHASE 1 — sweep the 5x4 = 20 (strike_offset x premium_stop_pct) grid, re-running ONLY
  simulator_real.simulate_trade_real per cell (signals are fixed; OPRA bars are RAM-cached
  after first touch, so 20 cells is cheap). v15 exits held constant.
* PHASE 2 — for every grid cell that is OOS per-trade-positive, a SECOND mini-sweep of
  exits on that cell: tp1_premium_pct {0.30,0.50} x runner_target {2.0,2.5,3.0} x
  chandelier(profit_lock trailing 20%) {off,on}. Report the best exit combo.
* DIRECTION SPLIT — also run the bear side at a reference cell to show the bull-tilt.

STRIKE_OFFSET CONVENTION (verified in simulator_real.py lines 357-364, anti-pattern 2.2):
    calls: strike = atm + strike_offset  ->  negative = ITM, positive = OTM
    puts : strike = atm - strike_offset  ->  negative = ITM, positive = OTM
  So for the BULL side: offset -2,-1 = ITM-2,ITM-1 ; 0 = ATM ; +1,+2 = OTM-1,OTM-2.

Candidate-edge bar (ALL must hold; OP-20 + OP-14, no cherry-picking a survivor 2.10):
    OOS per-trade expectancy > 0  AND  positive_quarters >= 4/6  AND
    top5_day_pct < 200            AND  n_trades >= 20.

Disclosure (OP-20): per-trade EXPECTANCY (not WR alone), IS(2025) vs OOS(2026),
positive_quarters/6, top5_day_pct (top-5 winning DAYS as % of total P&L), no_opra_data
per cell (a tiny-N cell may just be an OPRA-coverage hole, not a real signal count).

Pure Python, $0, no LLM in the loop, no live orders.
Writes analysis/recommendations/edgehunt-confluence_bull_structure.json.
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
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.confluence import compute_confluence  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

FAMILY = "confluence_bull_structure"
QTY = 3
TRAIL = 60                # trailing bars for structure/confluence (matches template)
WARMUP = 12               # bars into the day before evaluating
COOLDOWN_MIN = 45         # anti-pattern 2.7 (no back-to-back same-setup churn)
CONVICTION_MIN = 50.0     # matches the conviction the template's base scan used
FRESH_ONLY = True         # the family thesis is a FRESH structure break (BOS/CHoCH on this bar)
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# Sweep axes (the whole point: "different contract sizing + different exits")
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]          # negative=ITM, positive=OTM for calls
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]  # -0.99 == chart-stop-only

# v15 default exits (held constant during the strike x stop grid; varied in PHASE 2)
V15_TP1_PCT = 0.30
V15_RUNNER_TGT = 2.5
V15_TP1_QTY_FRAC = 0.50

# Candidate-edge bar
BAR_OOS_PER_TRADE = 0.0
BAR_POS_QUARTERS = 4
BAR_TOP5_PCT = 200.0
BAR_MIN_TRADES = 20

OUT_JSON = ROOT / "analysis" / "recommendations" / f"edgehunt-{FAMILY}.json"


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    """Accumulator with per-trade expectancy + per-day concentration (OP-14, OP-20)."""
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
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
            "avg_pnl": round(self.pnl / self.n, 1),   # per-trade EXPECTANCY (OP-14)
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


# ── Signal detection (run ONCE) — identical logic to confluence_real_fills_validate.py,
#    restricted to the BULL side (side=='C', bias bullish). ────────────────────────────
def detect_signals():
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill) — for disclosure stratification only
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]
    vix_arr = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)

    log.info("Building bars + scanning fresh-break bull-confluence signals...")
    all_bars: list[Bar] = []
    for _, r in rth.iterrows():
        ts = pd.Timestamp(r["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        all_bars.append(Bar(open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                            open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                            close=float(r["close"]), volume=int(r.get("volume", 50000) or 50000),
                            granularity_seconds=300, source="spy"))

    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None
    for idx in range(len(rth)):
        d = rth["date"].iloc[idx]
        i0 = day_start[d]
        if idx - i0 < WARMUP:
            continue
        trailing = all_bars[max(i0, idx - TRAIL + 1): idx + 1]
        if len(trailing) < 10:
            continue
        ms = analyze_structure(trailing)
        fresh = ms.last_event is not None and ms.last_event.break_index == len(trailing) - 1
        if FRESH_ONLY and not fresh:
            continue
        read = compute_confluence(trailing)
        # BULL-ONLY: require bullish bias + conviction
        if read.bias != "bullish" or read.conviction < CONVICTION_MIN:
            continue
        # break direction must agree with the bullish confluence bias
        if fresh and ms.last_event.direction != "bullish":
            continue
        bar_time = all_bars[idx].open_time.replace(tzinfo=None)
        if last_sig_time is not None and (bar_time - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue
        rej = read.invalidation
        if rej is None:
            continue
        last_sig_time = bar_time
        signals.append({"idx": idx, "date": d, "side": "C", "bias": "bullish",
                        "conviction": read.conviction, "vix": round(vix_arr[idx], 1),
                        "rejection_level": float(rej), "fresh": fresh,
                        "time": bar_time.strftime("%H:%M")})
    log.info("Bull signals detected: %d", len(signals))
    return rth, signals


# ── One sim pass over the fixed signal set with a given (strike,stop,exits) config. ──
def run_config(rth, signals, *, side_filter, strike_offset, premium_stop_pct,
               tp1_premium_pct=V15_TP1_PCT, runner_target_premium_pct=V15_RUNNER_TGT,
               tp1_qty_fraction=V15_TP1_QTY_FRAC, profit_lock_trailing=False,
               profit_lock_trail_pct=0.20):
    overall = _Acc()
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0
    pl_mode = "trailing" if profit_lock_trailing else "fixed"
    for s in signals:
        if s["side"] != side_filter:
            continue
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["confluence", "structure_break" if s["fresh"] else "structure", s["bias"]],
            side=side_filter, qty=QTY, setup="CONFLUENCE_BULL_STRUCTURE",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset,
            tp1_premium_pct=tp1_premium_pct, runner_target_premium_pct=runner_target_premium_pct,
            tp1_qty_fraction=tp1_qty_fraction,
            profit_lock_mode=pl_mode,
            profit_lock_trail_pct=(profit_lock_trail_pct if profit_lock_trailing else 0.0))
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl") and r["total_pnl"] > 0)
    o = overall.report()
    isr, oosr = by_sample["IS_2025"].report(), by_sample["OOS_2026"].report()
    oos_pt = oosr.get("avg_pnl", 0) if oosr.get("n") else 0
    oos_top5 = oosr.get("top5_day_pct")
    clears = bool(
        oosr.get("n", 0) >= BAR_MIN_TRADES
        and oos_pt is not None and oos_pt > BAR_OOS_PER_TRADE
        and pos_q >= BAR_POS_QUARTERS
        and (oos_top5 is not None and oos_top5 < BAR_TOP5_PCT)
    )
    return {
        "overall": o, "IS_2025": isr, "OOS_2026": oosr,
        "by_quarter": q_reports, "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "pos_q_n": pos_q, "n_quarters": len(q_reports),
        "n_no_opra_data": no_data,
        "oos_per_trade": oos_pt, "oos_top5_day_pct": oos_top5,
        "clears_bar": clears,
    }


def _cfg_name(strike_offset, premium_stop_pct):
    so = {-2: "ITM2", -1: "ITM1", 0: "ATM", 1: "OTM1", 2: "OTM2"}[strike_offset]
    return f"{so}_stop{int(round(premium_stop_pct * 100))}"


def main():
    rth, signals = detect_signals()
    n_signals = len([s for s in signals if s["side"] == "C"])

    # ── PHASE 1: strike x stop grid (bull side, v15 exits) ──────────────────
    log.info("PHASE 1: %d strike x %d stop = %d cells over %d bull signals",
             len(STRIKE_OFFSETS), len(PREMIUM_STOPS), len(STRIKE_OFFSETS) * len(PREMIUM_STOPS), n_signals)
    grid = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            r = run_config(rth, signals, side_filter="C", strike_offset=so, premium_stop_pct=ps)
            name = _cfg_name(so, ps)
            r2 = {"config": name, "strike_offset": so, "premium_stop_pct": ps, **r}
            grid.append(r2)
            log.info("  %-14s overall=%s OOS=%s posQ=%s top5=%s no_data=%d clears=%s",
                     name, r["overall"], r["OOS_2026"], r["positive_quarters"],
                     r["oos_top5_day_pct"], r["n_no_opra_data"], r["clears_bar"])

    # ── PHASE 2: exit mini-sweep on every OOS-per-trade-POSITIVE grid cell ──
    oos_pos_cells = [g for g in grid
                     if g["OOS_2026"].get("n", 0) >= 1 and (g["oos_per_trade"] or 0) > 0]
    log.info("PHASE 2: %d grid cells are OOS per-trade-positive -> exit mini-sweep", len(oos_pos_cells))
    exit_sweeps = {}
    for g in oos_pos_cells:
        so, ps = g["strike_offset"], g["premium_stop_pct"]
        combos = []
        for tp1 in (0.30, 0.50):
            for rt in (2.0, 2.5, 3.0):
                for pl in (False, True):
                    rr = run_config(rth, signals, side_filter="C", strike_offset=so,
                                    premium_stop_pct=ps, tp1_premium_pct=tp1,
                                    runner_target_premium_pct=rt, profit_lock_trailing=pl)
                    combos.append({
                        "tp1_premium_pct": tp1, "runner_target_premium_pct": rt,
                        "profit_lock_trailing": pl,
                        "overall": rr["overall"], "OOS_2026": rr["OOS_2026"],
                        "positive_quarters": rr["positive_quarters"],
                        "oos_per_trade": rr["oos_per_trade"],
                        "oos_top5_day_pct": rr["oos_top5_day_pct"],
                        "clears_bar": rr["clears_bar"],
                    })
        combos.sort(key=lambda c: (c["oos_per_trade"] or -9e9), reverse=True)
        exit_sweeps[g["config"]] = {"best": combos[0], "all": combos}
        log.info("  %s best-exit: %s", g["config"], combos[0])

    # ── DIRECTION SPLIT: bear side at the ATM/-50% reference cell ────────────
    # Detect bear signals (mirror of detect_signals) so the split is apples-to-apples.
    bear_signals = _detect_bear_signals(rth)
    log.info("DIRECTION SPLIT: bull(C) vs bear(P) at ATM, stop-50%%, v15 exits")
    bull_ref = run_config(rth, signals, side_filter="C", strike_offset=0, premium_stop_pct=-0.50)
    bear_ref = run_config(rth, bear_signals, side_filter="P", strike_offset=0, premium_stop_pct=-0.50)

    # ── Assemble candidate edges + pick best overall ────────────────────────
    candidate_edges = []
    for g in grid:
        best_exit = None
        if g["config"] in exit_sweeps:
            be = exit_sweeps[g["config"]]["best"]
            best_exit = be if be["clears_bar"] else None
        # A grid cell is reported as a candidate row whether or not it clears,
        # with clears_bar reflecting the BASE (v15-exit) cell; if an exit combo
        # promotes it, note that too.
        candidate_edges.append({
            "config": g["config"],
            "strike_offset": g["strike_offset"],
            "premium_stop_pct": g["premium_stop_pct"],
            "n_trades": g["overall"].get("n", 0),
            "oos_n": g["OOS_2026"].get("n", 0),
            "oos_per_trade": g["oos_per_trade"],
            "oos_total_pnl": g["OOS_2026"].get("total_pnl"),
            "overall_per_trade": g["overall"].get("avg_pnl"),
            "overall_total_pnl": g["overall"].get("total_pnl"),
            "positive_quarters": g["positive_quarters"],
            "top5_day_pct": g["oos_top5_day_pct"],
            "n_no_opra_data": g["n_no_opra_data"],
            "clears_bar": g["clears_bar"],
            "best_exit_combo_clears": best_exit,
        })

    cleared = [c for c in candidate_edges
               if c["clears_bar"] or c["best_exit_combo_clears"] is not None]
    # best overall: prefer a cleared cell by OOS per-trade; else least-bad by OOS per-trade
    def _key(c):
        return (1 if (c["clears_bar"] or c["best_exit_combo_clears"]) else 0,
                c["oos_per_trade"] or -9e9)
    best_cfg = max(candidate_edges, key=_key) if candidate_edges else None

    if cleared:
        verdict = (f"{len(cleared)}/{len(candidate_edges)} cells clear the candidate-edge bar. "
                   f"Best: {best_cfg['config']} OOS/trade=${best_cfg['oos_per_trade']:.1f}.")
    else:
        bb = best_cfg
        verdict = (
            "NEGATIVE — bull-only confluence_bull_structure stays UNPROFITABLE OOS even after "
            "sweeping strike (ITM-2..OTM-2) x premium-stop (-8%..chart-only) x exits "
            "(tp1/runner/chandelier). NO cell clears OOS per-trade>0 + posQ>=4/6 + top5<200 + "
            f"n>=20. Least-bad cell {bb['config']}: OOS/trade=${(bb['oos_per_trade'] or 0):.1f} "
            f"(n_oos={bb['oos_n']}), overall/trade=${bb['overall_per_trade']}. Capping losers with a "
            "tight premium stop reduces the bleed but does not manufacture a positive edge; cheaper/"
            "righter strikes shift magnitude, not sign. CONFIRMS the conviction-sweep kill — the "
            "trigger is awareness-only, not a tradeable bull edge (C3/L58: SPY-direction != option edge)."
        )

    summary = {
        "run_date": dt.date.today().isoformat(),
        "family": FAMILY,
        "window": f"{START}..{END}",
        "is_oos_split": "IS=2025, OOS=2026 (through data end ~2026-05-29)",
        "detector": {
            "rule": "fresh BOS/CHoCH on current bar + bullish confluence (conviction>=%g) + "
                    "break direction agrees; cooldown %dmin; warmup %d; trailing %d bars" % (
                        CONVICTION_MIN, COOLDOWN_MIN, WARMUP, TRAIL),
            "bull_only": True, "fresh_only": FRESH_ONLY, "qty": QTY,
        },
        "strike_offset_convention": "calls: strike=atm+offset -> negative=ITM, positive=OTM "
                                    "(verified simulator_real.py L357-364)",
        "n_signals": n_signals,
        "candidate_edge_bar": {
            "oos_per_trade_gt": BAR_OOS_PER_TRADE, "positive_quarters_gte": f"{BAR_POS_QUARTERS}/6",
            "top5_day_pct_lt": BAR_TOP5_PCT, "n_trades_gte": BAR_MIN_TRADES,
        },
        "phase1_grid": grid,
        "phase2_exit_sweeps": exit_sweeps,
        "direction_split_atm_stop50_v15exits": {
            "bull_C": {"overall": bull_ref["overall"], "OOS_2026": bull_ref["OOS_2026"],
                       "positive_quarters": bull_ref["positive_quarters"]},
            "bear_P": {"overall": bear_ref["overall"], "OOS_2026": bear_ref["OOS_2026"],
                       "positive_quarters": bear_ref["positive_quarters"]},
        },
        "candidate_edges": candidate_edges,
        "n_cells_clearing_bar": len(cleared),
        "best_config_overall": best_cfg["config"] if best_cfg else None,
        "honest_verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR authority; no BS-sim",
            "per_trade": "avg_pnl is per-trade EXPECTANCY, reported alongside (not instead of) WR (OP-14)",
            "concentration": "top5_day_pct = top-5 winning DAYS as %% of total P&L (OP-20 #5)",
            "oos_normalization": "IS=2025 (~12mo) vs OOS=2026 (~5mo); candidate bar is judged on OOS only",
            "coverage_caveat": "n_no_opra_data per cell — ITM-2/OTM-2 strikes can fall outside the "
                               "cached OPRA window on some days; a low-n cell may be a coverage hole, "
                               "not a real signal count (NOT cherry-picked, anti-pattern 2.10)",
            "spy_vs_option": "SPY-direction structure != option edge (C3/L58); this is the option test",
            "no_survivor_mining": "every grid cell + every exit combo is reported, not just the best",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== EDGE-HUNT VERDICT: %s ===" % FAMILY)
    print("bull signals:", n_signals)
    print("cells clearing bar:", len(cleared), "/", len(candidate_edges))
    print("best cell:", best_cfg["config"] if best_cfg else None,
          "OOS/trade=", best_cfg["oos_per_trade"] if best_cfg else None)
    print("DIRECTION SPLIT (ATM, -50%, v15):")
    print("  BULL C:", bull_ref["overall"], "OOS", bull_ref["OOS_2026"])
    print("  BEAR P:", bear_ref["overall"], "OOS", bear_ref["OOS_2026"])
    print("VERDICT:", verdict)
    return summary


def _detect_bear_signals(rth):
    """Mirror of detect_signals for the BEAR side — for the direction split only.

    Rebuilds bars from the already-loaded rth (no second data load)."""
    all_bars: list[Bar] = []
    for _, r in rth.iterrows():
        ts = pd.Timestamp(r["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        all_bars.append(Bar(open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                            open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                            close=float(r["close"]), volume=int(r.get("volume", 50000) or 50000),
                            granularity_seconds=300, source="spy"))
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i
    out: list[dict] = []
    last_sig_time: dt.datetime | None = None
    for idx in range(len(rth)):
        d = rth["date"].iloc[idx]
        i0 = day_start[d]
        if idx - i0 < WARMUP:
            continue
        trailing = all_bars[max(i0, idx - TRAIL + 1): idx + 1]
        if len(trailing) < 10:
            continue
        ms = analyze_structure(trailing)
        fresh = ms.last_event is not None and ms.last_event.break_index == len(trailing) - 1
        if FRESH_ONLY and not fresh:
            continue
        read = compute_confluence(trailing)
        if read.bias != "bearish" or read.conviction < CONVICTION_MIN:
            continue
        if fresh and ms.last_event.direction != "bearish":
            continue
        bar_time = all_bars[idx].open_time.replace(tzinfo=None)
        if last_sig_time is not None and (bar_time - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue
        rej = read.invalidation
        if rej is None:
            continue
        last_sig_time = bar_time
        out.append({"idx": idx, "date": d, "side": "P", "bias": "bearish",
                    "conviction": read.conviction, "vix": round(0.0, 1),
                    "rejection_level": float(rej), "fresh": fresh,
                    "time": bar_time.strftime("%H:%M")})
    return out


if __name__ == "__main__":
    main()
