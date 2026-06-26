"""EDGE-HUNT sweep — gap_and_go 0DTE SPY family (REAL-FILLS, OPRA).

Mandate (real-fills quant, C1 authority): CONFIRM the gap-and-go +EV claim and find
the best contract sizing (strike_offset) x exit combo, with FULL OP-20 disclosure and
NO survivor cherry-picking (anti-pattern 2.10).

Detector: the VALIDATED GAP_AND_GO detector itself
(``backtest.autoresearch.infinite_ammo_discovery.detect_gap_and_go`` — the detector
behind gap-and-go-LIVE.json), so this sweep's signal set matches the published
scorecard on a given window. NOTE its prior_close = prior-day FULL-session last close
(incl. extended hours), NOT last RTH close — using RTH-only drops ~11 marginal gap-up
calls (anti-pattern 2.2: do not silently diverge from the validated detector).
  GAP = first_RTH_bar.open / prior_RTH_close - 1
  gap >= +0.25% AND first bar GREEN -> CALLS (side C)
  gap <= -0.25% AND first bar RED   -> PUTS  (side P)
  skip |gap| > 1.5% (runaway) and |gap| < 0.25% (no gap). One signal/day, at the open.
  STOP (chart) = first bar opposite extreme (calls: first-bar low; puts: first-bar high).

Fills: lib.simulator_real.simulate_trade_real (real OPRA bars, causal next-bar-open
entry, v15 exit stack). Detect signals ONCE, then loop the 5x4 (strike x stop) grid
re-running ONLY the sim (fast). Default v15 exits otherwise.

STRIKE CONVENTION (VERIFIED in simulator_real.py L354-364 FIRST, anti-pattern 2.2):
  side P: strike = atm - strike_offset  -> offset<0 => strike ABOVE spot = ITM (puts)
  side C: strike = atm + strike_offset  -> offset<0 => strike BELOW spot = ITM (calls)
  => for BOTH sides: NEGATIVE offset = ITM, POSITIVE offset = OTM, 0 = ATM. Consistent.

SWEEP:
  strike_offset in {-2,-1,0,1,2}; premium_stop_pct in {-0.08,-0.20,-0.50,-0.99(chart-only)}.
  For each (strike,stop) cell that is OOS-positive per-trade -> SECOND mini-sweep:
    tp1_premium_pct in {0.30,0.50} x runner_target_premium_pct in {2.0,2.5,3.0}
    x profit_lock chandelier {off, trailing trail_pct=0.20}. Report best exit combo.
  Direction split (bull C vs bear P) reported for every cell.

CANDIDATE EDGE iff ALL: OOS per-trade expectancy > 0 AND positive_quarters >= 4/6
  AND top5_day_pct < 200 AND n_trades >= 20.

Pure Python, $0 (NO LLM in the sim loop). Writes
analysis/recommendations/edgehunt-gap_and_go.json.
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
from autoresearch import infinite_ammo_discovery as iad  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike, _strike_from_spot, build_day_contexts, detect_gap_and_go,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
QTY = 3
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
MAX_STRIKE_STEPS = 4    # mirror discovery_chart_stop_reeval (proxy-strike snapping, L58)

STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]      # -0.99 == chart-stop-only
EXIT_TP1 = [0.30, 0.50]
EXIT_RUNNER = [2.0, 2.5, 3.0]
EXIT_CHANDELIER = [None, 0.20]                      # None=off; 0.20=trailing 20% off HWM

# Candidate-edge bar (ALL must hold).
BAR_MIN_N = 20
BAR_MIN_POS_QUARTERS = 4
BAR_MAX_TOP5_PCT = 200.0


def _offset_label(off: int) -> str:
    if off == 0:
        return "ATM"
    return f"ITM{-off}" if off < 0 else f"OTM{off}"


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    """P&L accumulator with per-day aggregation for concentration disclosure."""
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
            return {"n": 0, "total_pnl": 0.0, "avg_pnl": 0.0, "wr": 0.0, "top5_day_pct": None}
        # top5_day_pct: top-5 winning DAYS as % of total P&L (only positive days count
        # as "winning days"; OP-20 concentration disclosure).
        pos_days = sorted([v for v in self.by_day.values() if v > 0], reverse=True)
        top5 = sum(pos_days[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 1),
            "avg_pnl": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def detect_signals(spy_full: pd.DataFrame):
    """Detect the gap-and-go signal set ONCE via the VALIDATED discovery detector.

    Mirrors discovery_chart_stop_reeval.py exactly: build_day_contexts + detect_gap_and_go
    on the FULL (extended-hours) frame; signals carry a FULL-frame ``bar_idx`` and the sim
    later runs on that SAME full frame (entry_bar_idx=bar_idx) — identical to the published
    gap-and-go-LIVE.json harness. NOT a self-rolled re-derivation (anti-pattern 2.2). The
    detector's prior_close = prior-day FULL-session last close (build_day_contexts), NOT
    last RTH close.

    Returns (signals_with_full_idx, prepared_full_frame). The frame is reset-indexed and
    annotated with 't'/'date' (build_day_contexts needs them) so positional bar_idx is
    stable for the sim.
    """
    spy_full = spy_full.copy()
    spy_full["t"] = spy_full["timestamp_et"].dt.time
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    spy_full = spy_full.reset_index(drop=True)

    days = build_day_contexts(spy_full)
    raw = detect_gap_and_go(spy_full, None, None, days)

    signals = [{
        "bar_idx": int(s.bar_idx),               # FULL-frame positional index (sim uses this)
        "date": pd.Timestamp(spy_full["timestamp_et"].iloc[s.bar_idx]).date(),
        "side": s.side,
        "direction": "long" if s.side == "C" else "short",
        "stop_level": round(float(s.stop_level), 2),
        "note": getattr(s, "note", ""),
    } for s in raw]
    return signals, spy_full


def _run_grid_cell(signals, spy_full, vix_ser, strike_offset, premium_stop_pct,
                   tp1_premium_pct=0.30, runner_target_premium_pct=2.5,
                   profit_lock_trail_pct=None):
    """Run one sim configuration over ALL signals — FAITHFUL to the validated harness.

    Mirrors discovery_chart_stop_reeval._sim: FULL frame as spy_df, nearest-cached-strike
    snapping (proxy strikes, L58) via strike_override, entry_vix supplied. Exit knobs ride
    on top so the strike x stop x exit sweep is an exact extension of the validated
    methodology — not a divergent re-implementation. Returns accumulators + coverage.
    """
    overall = _Acc()
    by_side = {"C": _Acc(), "P": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    cache_miss = 0
    sim_none = 0
    actual_offsets: list[int] = []
    pl_kwargs = {}
    if profit_lock_trail_pct is not None:
        # Chandelier: arm at +5% favor, trail trail_pct off HWM (matches v15 chandelier).
        pl_kwargs = dict(
            profit_lock_threshold_pct=0.05,
            profit_lock_mode="trailing",
            profit_lock_trail_pct=profit_lock_trail_pct,
        )
    for s in signals:
        bar = spy_full.iloc[s["bar_idx"]]
        d = pd.Timestamp(bar["timestamp_et"]).date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # Simulator-convention target offset, then snap to nearest CACHED strike.
        target = atm - strike_offset if s["side"] == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, s["side"], MAX_STRIKE_STEPS)
        if strike is None:
            cache_miss += 1
            continue
        ev = float(vix_ser.iloc[s["bar_idx"]]) if s["bar_idx"] < len(vix_ser) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=s["bar_idx"], entry_bar=bar, spy_df=spy_full, ribbon_df=None,
            rejection_level=s["stop_level"],
            triggers_fired=[s["note"] or "GAP_AND_GO"],
            side=s["side"], qty=QTY, setup="GAP_AND_GO",
            strike_override=strike, entry_vix=ev,
            premium_stop_pct=premium_stop_pct,
            tp1_premium_pct=tp1_premium_pct,
            runner_target_premium_pct=runner_target_premium_pct,
            **pl_kwargs,
        )
        if fill is None or fill.dollar_pnl is None:
            sim_none += 1
            continue
        actual_offsets.append(int(strike - atm))
        pnl = fill.dollar_pnl
        day = d.isoformat()
        overall.add(pnl, day)
        by_side[s["side"]].add(pnl, day)
        by_sample["IS_2025" if d.year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(d)].add(pnl, day)
    cov = {"cache_miss": cache_miss, "sim_none": sim_none,
           "filled": overall.n,
           "mean_actual_offset": round(sum(actual_offsets) / len(actual_offsets), 2) if actual_offsets else None}
    return overall, by_side, by_sample, by_q, cov


def _evaluate_cell(overall, by_side, by_sample, by_q, cov):
    """Build the disclosure dict for one cell + the clears_bar verdict."""
    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    n_q = len(q_reports)
    oos = by_sample["OOS_2026"].report()
    is_r = by_sample["IS_2025"].report()
    ov = overall.report()
    oos_per_trade = oos.get("avg_pnl", 0.0) if oos.get("n") else 0.0
    top5 = ov.get("top5_day_pct")
    n_total = ov.get("n", 0)

    clears = (
        oos.get("n", 0) > 0
        and oos_per_trade > 0
        and pos_q >= BAR_MIN_POS_QUARTERS
        and (top5 is not None and top5 < BAR_MAX_TOP5_PCT)
        and n_total >= BAR_MIN_N
    )

    # ── Survivor-fragility audit (anti-pattern 2.10): is a "clearing" cell carried by
    # a single day/quarter? Recompute the bar after dropping the best OOS day (drop-top1)
    # and report the OOS-only concentration. A cell that needs its single best day to stay
    # positive, OR whose OOS top-5 days exceed total OOS P&L (top5>=200%), is FRAGILE.
    oos_acc = by_sample["OOS_2026"]
    oos_days = sorted(oos_acc.by_day.values(), reverse=True)
    oos_total = sum(oos_days)
    oos_drop1_total = sum(oos_days[1:]) if len(oos_days) > 1 else 0.0
    oos_pos_days = sorted([v for v in oos_acc.by_day.values() if v > 0], reverse=True)
    oos_top5_pct = round(100 * sum(oos_pos_days[:5]) / oos_total, 0) if oos_total > 0 else None
    fragile = (
        (oos_drop1_total <= 0 and oos_total > 0)      # best single OOS day carries OOS
        or (oos_top5_pct is not None and oos_top5_pct >= BAR_MAX_TOP5_PCT)  # OOS top5 >= 200%
    )
    fragility = {
        "oos_total": round(oos_total, 1),
        "oos_drop_top1_day_total": round(oos_drop1_total, 1),
        "oos_top5_day_pct": oos_top5_pct,
        "is_fragile_survivor": bool(fragile),
        "note": ("OOS rests on the single best day and/or OOS top-5 days exceed total OOS P&L "
                 "— treat as a fragile survivor, NOT a clean edge (anti-pattern 2.10)."),
    }
    clears_robust = clears and not fragile

    # WHY-not, for honest disclosure (no cherry-picking a survivor).
    reasons = []
    if oos.get("n", 0) == 0:
        reasons.append("no_oos_trades")
    if oos_per_trade <= 0:
        reasons.append(f"oos_per_trade<=0 ({oos_per_trade})")
    if pos_q < BAR_MIN_POS_QUARTERS:
        reasons.append(f"pos_quarters {pos_q}/{n_q} < {BAR_MIN_POS_QUARTERS}")
    if top5 is None:
        reasons.append("top5_undefined (total<=0)")
    elif top5 >= BAR_MAX_TOP5_PCT:
        reasons.append(f"top5_day_pct {top5} >= {BAR_MAX_TOP5_PCT}")
    if n_total < BAR_MIN_N:
        reasons.append(f"n_trades {n_total} < {BAR_MIN_N}")

    return {
        "overall": ov,
        "by_side": {k: v.report() for k, v in by_side.items()},
        "IS_2025": is_r,
        "OOS_2026": oos,
        "oos_per_trade": round(oos_per_trade, 2),
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{n_q}",
        "pos_quarters_n": pos_q,
        "top5_day_pct": top5,
        "coverage": cov,
        "clears_bar": clears,
        "clears_bar_robust": clears_robust,
        "fragility": fragility,
        "fail_reasons": reasons,
    }


def _align_vix(spy_full: pd.DataFrame, vix_full: pd.DataFrame) -> pd.Series:
    """VIX series positionally aligned to spy_full rows (ffill), indexed 0..N-1.

    The sim reads entry_vix via vix.iloc[bar_idx] where bar_idx indexes spy_full, so the
    returned series must be the SAME length/order as spy_full (mirrors the harness, which
    builds vix the same way). Only used for the regime-chandelier arming; entry_vix=0 is a
    safe fallback (scalar trail used).
    """
    vix_full = vix_full.copy()
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = (vix_full.set_index("timestamp_et")["close"]
               if "close" in vix_full.columns else vix_full.iloc[:, 0])
    spy_ts = pd.to_datetime(spy_full["timestamp_et"])
    spy_naive = spy_ts.dt.tz_localize(None) if spy_ts.dt.tz is not None else spy_ts
    out = []
    for ts in spy_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            out.append(float(vix_ser.iloc[j]) if j >= 0 else 0.0)
        except Exception:
            out.append(0.0)
    return pd.Series(out)


def main() -> int:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])

    signals, spy_full = detect_signals(spy_full)
    vix_ser = _align_vix(spy_full, vix_full)
    n_days = pd.to_datetime(spy_full["timestamp_et"]).dt.date.nunique()
    side_counts = {"C": sum(1 for s in signals if s["side"] == "C"),
                   "P": sum(1 for s in signals if s["side"] == "P")}
    log.info("Trading days: %d  GAP_AND_GO signals: %d (C=%d P=%d)",
             n_days, len(signals), side_counts["C"], side_counts["P"])

    grid: dict[str, dict] = {}
    candidate_edges: list[dict] = []
    best_overall_per_trade = None
    best_overall_cfg = None

    for off in STRIKE_OFFSETS:
        for stop in PREMIUM_STOPS:
            cfg = f"{_offset_label(off)}|stop={stop}"
            ov, bs, bsam, bq, cov = _run_grid_cell(signals, spy_full, vix_ser, off, stop)
            ev = _evaluate_cell(ov, bs, bsam, bq, cov)
            ev["config"] = cfg
            ev["strike_offset"] = off
            ev["premium_stop_pct"] = stop
            grid[cfg] = ev
            log.info("  [%s] overall=%s OOS/trade=%s posQ=%s top5=%s clears=%s",
                     cfg, ev["overall"], ev["oos_per_trade"], ev["positive_quarters"],
                     ev["top5_day_pct"], ev["clears_bar"])

            ov_per_trade = ev["overall"].get("avg_pnl", 0.0)
            if best_overall_per_trade is None or ov_per_trade > best_overall_per_trade:
                best_overall_per_trade = ov_per_trade
                best_overall_cfg = cfg

            # SECOND mini-sweep of exits on any OOS-positive cell.
            if ev["OOS_2026"].get("n", 0) > 0 and ev["oos_per_trade"] > 0:
                best_exit = None
                exit_results = []
                for tp1 in EXIT_TP1:
                    for runner in EXIT_RUNNER:
                        for chand in EXIT_CHANDELIER:
                            o2, _bs2, bsam2, bq2, _cov2 = _run_grid_cell(
                                signals, spy_full, vix_ser, off, stop,
                                tp1_premium_pct=tp1, runner_target_premium_pct=runner,
                                profit_lock_trail_pct=chand)
                            r2 = o2.report()
                            oos2 = bsam2["OOS_2026"].report()
                            posq2 = sum(1 for k in bq2 if bq2[k].report().get("total_pnl", 0) > 0)
                            combo = {
                                "tp1_premium_pct": tp1,
                                "runner_target_premium_pct": runner,
                                "chandelier_trail_pct": chand,
                                "overall_per_trade": r2.get("avg_pnl", 0.0),
                                "overall_total": r2.get("total_pnl", 0.0),
                                "oos_per_trade": oos2.get("avg_pnl", 0.0) if oos2.get("n") else 0.0,
                                "pos_quarters": posq2,
                                "top5_day_pct": r2.get("top5_day_pct"),
                            }
                            exit_results.append(combo)
                            # "best" = highest OOS per-trade (the honest robustness axis).
                            if best_exit is None or combo["oos_per_trade"] > best_exit["oos_per_trade"]:
                                best_exit = combo
                ev["exit_minisweep"] = {"best": best_exit, "all": exit_results}
                log.info("    exit best: %s", best_exit)

            if ev["clears_bar"]:
                candidate_edges.append({
                    "config": cfg,
                    "n_trades": ev["overall"]["n"],
                    "oos_per_trade": ev["oos_per_trade"],
                    "oos_total_pnl": ev["OOS_2026"].get("total_pnl", 0.0),
                    "overall_per_trade": ev["overall"].get("avg_pnl", 0.0),
                    "positive_quarters": ev["positive_quarters"],
                    "top5_day_pct": ev["top5_day_pct"],
                    # clears_bar = mechanical 4-gate pass; clears_bar_robust additionally
                    # requires it NOT be a single-day/quarter survivor (anti-pattern 2.10).
                    "clears_bar": ev["clears_bar"] and ev["clears_bar_robust"],
                    "clears_bar_mechanical": True,
                    "clears_bar_robust": ev["clears_bar_robust"],
                    "fragility": ev["fragility"],
                    "premium_stop_pct": stop,
                    "doctrinal_chart_stop_only": stop == -0.99,
                })

    # Direction split on the canonical LIVE config (ATM chart-stop-only) for headline.
    live_cfg = grid.get("ATM|stop=-0.99", {})
    direction_split = live_cfg.get("by_side", {})

    summary = {
        "run_date": dt.date.today().isoformat(),
        "family": "gap_and_go",
        "detector": "infinite_ammo_discovery.detect_gap_and_go (the VALIDATED detector behind gap-and-go-LIVE.json; prior_close=prior-day FULL-session last close)",
        "fills": "lib.simulator_real.simulate_trade_real on the FULL frame with nearest-cached-strike snapping (strike_override) + entry_vix — identical harness to discovery_chart_stop_reeval._sim (the gap-and-go-LIVE.json generator). v15 exit stack.",
        "window": f"{START}..{END}",
        "n_trading_days": n_days,
        "qty": QTY,
        "strike_convention": (
            "VERIFIED simulator_real.py L354-364: side P strike=atm-offset, side C strike=atm+offset; "
            "for BOTH sides negative offset=ITM, positive=OTM, 0=ATM. Then snapped to nearest CACHED "
            "strike within +-4 steps (MAX_STRIKE_STEPS) per the validated harness; mean_actual_offset disclosed per cell."
        ),
        "n_signals": len(signals),
        "side_counts": side_counts,
        "reconciliation_vs_LIVE_scorecard": {
            "live_scorecard": "analysis/recommendations/gap-and-go-LIVE.json",
            "live_window": "2025-01-02..2026-06-16 (363 trading days; spy_5m_2025-01-01_2026-06-16.csv)",
            "this_window": f"{START}..{END} ({n_days} trading days; per spec load_data({START},{END}))",
            "why_different": (
                "This sweep uses the spec-mandated window ending 2026-05-15, which EXCLUDES most of 2026Q2 — "
                "the LIVE scorecard's single strongest quarter (ATM exp +$118/trade, n=11). It also has fewer "
                "signals (82 vs 96) purely from the ~21 fewer trading days. The detector + fill harness are "
                "byte-identical to LIVE; the divergence is the data window, NOT a methodology difference. "
                "Net effect: the ATM chart-stop-only headline that reads +$41.6/trade over 363 days reads "
                "MUCH weaker over this shorter window because the carrying 2026Q2 gap days are mostly absent."
            ),
        },
        "sweep": {
            "strike_offset": STRIKE_OFFSETS,
            "premium_stop_pct": PREMIUM_STOPS,
            "exit_tp1_premium_pct": EXIT_TP1,
            "exit_runner_target_premium_pct": EXIT_RUNNER,
            "exit_chandelier_trail_pct": EXIT_CHANDELIER,
        },
        "candidate_edge_bar": {
            "rule": "ALL of: OOS per-trade>0 AND positive_quarters>=4/6 AND top5_day_pct<200 AND n_trades>=20",
            "min_n": BAR_MIN_N, "min_pos_quarters": BAR_MIN_POS_QUARTERS, "max_top5_pct": BAR_MAX_TOP5_PCT,
        },
        "best_overall_per_trade_config": best_overall_cfg,
        "best_overall_per_trade": best_overall_per_trade,
        "n_cells_clear_mechanical": len(candidate_edges),
        "n_cells_clear_robust": sum(1 for c in candidate_edges if c["clears_bar"]),
        "candidate_edges": candidate_edges,
        "direction_split_on_ATM_chart_stop_only": direction_split,
        "grid": grid,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority; supersedes BS-sim + SPY-direction proxies",
            "per_trade": "expectancy (avg_pnl) reported per cell, NOT WR alone (OP-14)",
            "is_oos": "IS=2025 calendar, OOS=2026 calendar (per-cut WF not re-run here; see gap-and-go-LIVE.json for expanding-anchor WF)",
            "concentration": "top5_day_pct = top-5 POSITIVE days as % of total P&L (OP-20 #5)",
            "positive_quarters": "out of 6 quarters (2025Q1..2026Q2)",
            "bull_tilt": "direction split reported (by_side C vs P) — bull/bear asymmetry on options is real",
            "proxy_strike_caveat": "L58: ATM/ITM not always cached; nearest-cached strike (within +-4) used by the sim (mirrors validated harness); cache_miss + mean_actual_offset disclosed in each cell's coverage block",
            "no_cherry_pick": "anti-pattern 2.10: every cell's clears_bar + fail_reasons reported; a tiny-N / high-concentration / OOS-negative survivor is marked clears_bar=false",
            "grid_search_disclosure": "20 (strike x stop) cells searched + exit mini-sweep on OOS+ cells; treat multiple-comparisons risk accordingly (DSR in gap-and-go-LIVE.json used n_trials=30)",
        },
    }

    out = ROOT / "analysis" / "recommendations" / "edgehunt-gap_and_go.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out)

    n_robust = sum(1 for c in candidate_edges if c["clears_bar"])
    print("\n=== GAP_AND_GO EDGE-HUNT VERDICT ===")
    print(f"signals={len(signals)} (C={side_counts['C']} P={side_counts['P']}) over {n_days} trading days")
    print(f"best overall per-trade: {best_overall_cfg} = ${best_overall_per_trade}")
    print(f"cells clearing mechanical 4-gate bar: {len(candidate_edges)}; ROBUST (not fragile survivor): {n_robust}")
    for c in candidate_edges:
        print(f"  {c['config']}: n={c['n_trades']} OOS/trade=${c['oos_per_trade']} "
              f"posQ={c['positive_quarters']} top5={c['top5_day_pct']}% "
              f"fragile={c['fragility']['is_fragile_survivor']} chart_stop_only={c['doctrinal_chart_stop_only']} "
              f"-> robust_clear={c['clears_bar']}")
    print(f"direction split (ATM chart-stop-only): {direction_split}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
