"""EDGE HUNT — hs_bear 0DTE SPY family: real-fills strike x stop x exit sweep.

Family spec: HEAD_AND_SHOULDERS_BEAR, puts (side="P"), morning window 09:40-12:00 ET.
This is the "different contract sizing + different exits" sweep on top of the
hs_bear_real_fills_validate.py baseline.

PIPELINE (per task + OP-20 + the confluence_real_fills template shape):
  1. Detect H&S-top signals ONCE over the 16-mo window (no proximity filter, the
     hs_watcher default — fires on ALL H&S tops), 09:40-12:00 ET, 45-min cooldown.
  2. Loop the 5x4 = 20 (strike_offset x premium_stop_pct) grid, re-running ONLY
     simulator_real.simulate_trade_real per signal (default v15 exits otherwise).
  3. For ANY (strike,stop) cell that is OOS per-trade positive, run a SECOND mini
     exit-sweep on that cell: tp1_premium_pct {0.30,0.50} x runner_target {2.0,2.5,3.0}
     x chandelier (profit_lock trailing 0.20) on/off. Report best exit combo.
  4. Direction split: re-run the SAME signal bars as CALLS (side="C") to surface the
     bull-tilt (bull loses less than bear on options — C3/L58 family lore).

STRIKE CONVENTION (verified in simulator_real.py FIRST — anti-pattern 2.2):
  side="P": strike = atm - strike_offset  => offset<0 = ITM (strike ABOVE spot),
                                             offset>0 = OTM (strike BELOW spot).
  side="C": strike = atm + strike_offset  => offset<0 = ITM, offset>0 = OTM.
  So {-2,-1,0,1,2} = {ITM-2, ITM-1, ATM, OTM-1, OTM-2} for BOTH sides. Consistent.

DISCLOSURE (OP-20, OP-14): per-trade EXPECTANCY (not WR alone), IS(2025)/OOS(2026)
split, positive_quarters/6, top5_day_pct (top-5 winning DAYS as % of total P&L).
CANDIDATE EDGE bar (ALL must hold): OOS per-trade expectancy > 0 AND
positive_quarters >= 4/6 AND top5_day_pct < 200 AND n_trades >= 20.
NO survivor cherry-picking (anti-pattern 2.10): tiny-N / high-concentration /
OOS-negative cells are reported with clears_bar=false and a stated reason.

Pure Python, $0 (NO LLM in the sim loop). No live orders. Markets closed (weekend).

Output: analysis/recommendations/edgehunt-hs_bear.json
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
sys.path.insert(0, str(ROOT))  # crypto.lib.chart_patterns

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "edgehunt-hs_bear.json"

# ── Family / signal-detection params (mirror hs_bear_real_fills_validate.py) ──
QTY = 3
ENTRY_TIME_START = dt.time(9, 40)
ENTRY_TIME_END = dt.time(12, 0)           # morning-only (family spec)
COOLDOWN_MINUTES = 45
_CHART_STOP_ABOVE_NECKLINE = 0.30         # rejection_level = neckline + 0.30
_WINDOW_BARS = 35
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# ── The sweep grids ──────────────────────────────────────────────────────────
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]                 # ITM-2..OTM-2
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]       # -0.99 == chart-stop-only
# Exit mini-sweep (only run on OOS-positive (strike,stop) cells):
EXIT_TP1S = [0.30, 0.50]
EXIT_RUNNERS = [2.0, 2.5, 3.0]
EXIT_CHANDELIER = [False, True]                    # profit_lock trailing 0.20 on/off

# ── Candidate-edge bar (ALL must hold) ───────────────────────────────────────
BAR_MIN_N = 20
BAR_MIN_POS_QUARTERS = 4
BAR_MAX_TOP5_PCT = 200.0
# (OOS per-trade expectancy > 0 also required)

try:
    from crypto.lib.chart_patterns import Bar, head_and_shoulders_detector as _detect_hs
except ImportError:
    log.error("crypto.lib.chart_patterns not available — cannot run")
    sys.exit(1)


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _offset_label(side: str, off: int) -> str:
    # Both sides: negative=ITM, positive=OTM, 0=ATM (verified in simulator_real.py)
    if off == 0:
        return "ATM"
    return (f"ITM-{abs(off)}" if off < 0 else f"OTM-{off}")


class _Acc:
    """Per-trade accumulator with OP-20 disclosure fields."""
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
            return {"n": 0, "wr": None, "total_pnl": 0.0, "avg_pnl": None, "top5_day_pct": None}
        # top5 winning DAYS as % of total P&L (only positive days count toward the
        # numerator — concentration measures how much of the edge is a few big days).
        pos_days = sorted((v for v in self.by_day.values() if v > 0), reverse=True)
        top5 = sum(pos_days[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "avg_pnl": round(self.pnl / self.n, 1),         # per-trade EXPECTANCY (OP-14)
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _make_bars(rth: pd.DataFrame, idx: int, window: int = 35) -> list:
    start = max(0, idx - window + 1)
    sub = rth.iloc[start: idx + 1]
    out = []
    for _, row in sub.iterrows():
        ts = pd.Timestamp(row["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        open_time = ts.to_pydatetime().replace(tzinfo=dt.timezone.utc)
        out.append(Bar(
            open_time=open_time,
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]),
            volume=int(row.get("volume", 50_000) or 50_000),
            granularity_seconds=300, source="spy_5m",
        ))
    return out


def detect_signals(rth: pd.DataFrame, vix_arr: pd.Series) -> list[dict]:
    """H&S-top signals ONCE — identical gating to hs_bear_real_fills_validate.py."""
    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None
    for idx in range(len(rth)):
        if idx < 30:
            continue
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bar_time_naive = bar_time.tz_localize(None).to_pydatetime()
        else:
            bar_time_naive = pd.Timestamp(bar_time).to_pydatetime()
        bar_date = bar_time_naive.date()
        if bar_date < START or bar_date > END:
            continue
        t = bar_time_naive.time()
        if t < ENTRY_TIME_START or t > ENTRY_TIME_END:
            continue
        if last_signal_time is not None:
            if (bar_time_naive - last_signal_time).total_seconds() / 60.0 < COOLDOWN_MINUTES:
                continue
        bars = _make_bars(rth, idx, window=_WINDOW_BARS)
        if len(bars) < 30:
            continue
        hit = _detect_hs(bars, lookback=30)
        if hit is None:
            continue
        last_signal_time = bar_time_naive
        bar_close = float(bar["close"])
        neckline = float(hit.notes.get("neckline", bar_close))
        rejection_level = neckline + _CHART_STOP_ABOVE_NECKLINE
        signals.append({
            "date": bar_date,
            "time": bar_time_naive.strftime("%H:%M"),
            "bar_idx": idx,
            "entry_spot": bar_close,
            "neckline": round(neckline, 2),
            "rejection_level": round(rejection_level, 2),
            "vix": round(float(vix_arr.iloc[idx]), 1),
            "conf": round(float(hit.confidence), 3),
        })
    return signals


def run_cell(signals: list[dict], rth: pd.DataFrame, side: str, strike_offset: int,
             premium_stop_pct: float, *, tp1_premium_pct: float = 0.30,
             runner_target_premium_pct: float = 2.5, chandelier: bool = False) -> dict:
    """Re-run the sim across all signals for one config. Returns OP-20 cut dict."""
    overall = _Acc()
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0

    pl_kwargs = {}
    if chandelier:
        # v15 chandelier: arm at +5% favorable, trail 20% off HWM (premium basis).
        pl_kwargs = dict(
            profit_lock_threshold_pct=0.05,
            profit_lock_stop_offset_pct=0.0,
            profit_lock_mode="trailing",
            profit_lock_trail_pct=0.20,
        )

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["bar_idx"],
            entry_bar=rth.iloc[s["bar_idx"]],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["hs_top_detector", "time_window", "no_proximity_filter"],
            side=side,
            qty=QTY,
            setup="HEAD_AND_SHOULDERS_BEAR",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
            tp1_premium_pct=tp1_premium_pct,
            runner_target_premium_pct=runner_target_premium_pct,
            **pl_kwargs,
        )
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    n_q = len(q_reports)
    pos_q = sum(1 for r in q_reports.values() if (r.get("total_pnl") or 0) > 0)
    ov = overall.report()
    oos = by_sample["OOS_2026"].report()
    is_r = by_sample["IS_2025"].report()

    # Candidate-edge bar: judged on the OVERALL cut for n/quarters/top5, OOS for sign.
    oos_pos = (oos.get("avg_pnl") is not None and oos["avg_pnl"] > 0)
    clears, reasons = _judge(ov, oos, pos_q, n_q, oos_pos)

    return {
        "side": side,
        "strike_offset": strike_offset,
        "strike_label": _offset_label(side, strike_offset),
        "premium_stop_pct": premium_stop_pct,
        "tp1_premium_pct": tp1_premium_pct,
        "runner_target_premium_pct": runner_target_premium_pct,
        "chandelier": chandelier,
        "n_no_opra_data": no_data,
        "overall": ov,
        "IS_2025": is_r,
        "OOS_2026": oos,
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{n_q}",
        "oos_per_trade_positive": oos_pos,
        "clears_bar": clears,
        "fail_reasons": reasons,
    }


def _judge(ov: dict, oos: dict, pos_q: int, n_q: int, oos_pos: bool) -> tuple[bool, list[str]]:
    reasons = []
    n = ov.get("n", 0) or 0
    if n < BAR_MIN_N:
        reasons.append(f"n_trades {n} < {BAR_MIN_N}")
    if not oos_pos:
        oos_avg = oos.get("avg_pnl")
        reasons.append(f"OOS per-trade {oos_avg} <= 0 (or no OOS trades)")
    if pos_q < BAR_MIN_POS_QUARTERS:
        reasons.append(f"positive_quarters {pos_q}/{n_q} < {BAR_MIN_POS_QUARTERS}")
    t5 = ov.get("top5_day_pct")
    if t5 is None:
        reasons.append("top5_day_pct undefined (total P&L <= 0)")
    elif t5 >= BAR_MAX_TOP5_PCT:
        reasons.append(f"top5_day_pct {t5} >= {BAR_MAX_TOP5_PCT}")
    return (len(reasons) == 0, reasons)


def main() -> dict:
    log.info("Loading 16-month SPY+VIX data (%s to %s)...", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill) — same recipe as the templates
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index
    )
    vix_ser = (vix_full.set_index("timestamp_et")["close"]
               if "close" in vix_full.columns else vix_full.iloc[:, 0])
    rth_naive = (rth["timestamp_et"].dt.tz_localize(None)
                 if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"])
    vix_vals: list[float] = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_vals.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_vals.append(17.0)
    vix_arr = pd.Series(vix_vals, index=rth.index)

    log.info("Detecting H&S signals ONCE (09:40-12:00 ET, no proximity filter)...")
    signals = detect_signals(rth, vix_arr)
    log.info("Signals: %d", len(signals))

    # ── BASELINE (the family default: side P, ATM, premium_stop -0.08, v15 exits) ──
    # The hs template ran chart-stop-only (-0.99). The task asks for the v15 default
    # baseline (premium_stop_pct default = -0.08 ATM). Report BOTH defaults clearly.
    log.info("Baseline (P, ATM, stop -0.08, v15 exits)...")
    baseline_v15 = run_cell(signals, rth, "P", 0, -0.08)
    baseline_chartstop = run_cell(signals, rth, "P", 0, -0.99)

    # ── STRIKE x STOP grid (puts) — 5 x 4 = 20 cells ────────────────────────────
    log.info("Running 5x4 strike x stop grid (puts)...")
    grid: list[dict] = []
    for off in STRIKE_OFFSETS:
        for stop in PREMIUM_STOPS:
            cell = run_cell(signals, rth, "P", off, stop)
            grid.append(cell)
            log.info("  P off=%+d(%s) stop=%.2f -> n=%d oos_avg=%s pos_q=%s clears=%s",
                     off, cell["strike_label"], stop, cell["overall"].get("n"),
                     cell["OOS_2026"].get("avg_pnl"), cell["positive_quarters"],
                     cell["clears_bar"])

    # ── EXIT mini-sweep on OOS-positive cells ───────────────────────────────────
    oos_pos_cells = [c for c in grid if c["oos_per_trade_positive"]]
    log.info("OOS-positive (strike,stop) cells: %d -> exit mini-sweep each",
             len(oos_pos_cells))
    exit_sweeps: list[dict] = []
    for c in oos_pos_cells:
        off, stop = c["strike_offset"], c["premium_stop_pct"]
        best = None
        combos = []
        for tp1 in EXIT_TP1S:
            for runner in EXIT_RUNNERS:
                for chand in EXIT_CHANDELIER:
                    ec = run_cell(signals, rth, "P", off, stop,
                                  tp1_premium_pct=tp1, runner_target_premium_pct=runner,
                                  chandelier=chand)
                    rec = {
                        "tp1_premium_pct": tp1,
                        "runner_target_premium_pct": runner,
                        "chandelier": chand,
                        "overall": ec["overall"],
                        "OOS_2026": ec["OOS_2026"],
                        "positive_quarters": ec["positive_quarters"],
                        "clears_bar": ec["clears_bar"],
                        "fail_reasons": ec["fail_reasons"],
                    }
                    combos.append(rec)
                    # rank by OOS per-trade expectancy then overall total P&L
                    key = (ec["OOS_2026"].get("avg_pnl") or -1e9,
                           ec["overall"].get("total_pnl") or -1e9)
                    if best is None or key > best[0]:
                        best = (key, rec)
        exit_sweeps.append({
            "cell": {"strike_offset": off, "strike_label": c["strike_label"],
                     "premium_stop_pct": stop},
            "best_exit": best[1] if best else None,
            "all_combos": combos,
        })
        if best:
            b = best[1]
            log.info("  best exit @ off=%+d stop=%.2f: tp1=%.2f runner=%.1f chand=%s "
                     "-> oos_avg=%s overall_pnl=%s clears=%s",
                     off, stop, b["tp1_premium_pct"], b["runner_target_premium_pct"],
                     b["chandelier"], b["OOS_2026"].get("avg_pnl"),
                     b["overall"].get("total_pnl"), b["clears_bar"])

    # ── DIRECTION SPLIT: same signal bars as CALLS (bull-tilt check) ─────────────
    # Note: H&S-top is structurally bearish; firing CALLS on those bars is the
    # counterfactual that exposes the bull-tilt (C3/L58 — bull loses less on options).
    log.info("Direction split: same bars as CALLS (ATM) across the stop grid...")
    dir_split = {"put_ATM_baseline_v15": baseline_v15["overall"],
                 "by_stop": []}
    for stop in PREMIUM_STOPS:
        p_cell = run_cell(signals, rth, "P", 0, stop)
        c_cell = run_cell(signals, rth, "C", 0, stop)
        dir_split["by_stop"].append({
            "premium_stop_pct": stop,
            "PUT_ATM": p_cell["overall"],
            "CALL_ATM": c_cell["overall"],
            "PUT_OOS": p_cell["OOS_2026"],
            "CALL_OOS": c_cell["OOS_2026"],
        })

    # ── Collate candidate edges (cells from the grid that clear the bar) ─────────
    candidates = [c for c in grid if c["clears_bar"]]
    # Also fold in any exit-swept combo that clears the bar (with its parent cell).
    exit_candidates = []
    for sw in exit_sweeps:
        for combo in sw["all_combos"]:
            if combo["clears_bar"]:
                exit_candidates.append({"cell": sw["cell"], **combo})

    # Best config overall = highest OOS per-trade expectancy among clearing configs,
    # else the least-bad by OOS expectancy across the whole grid (honest fallback).
    def _oos_avg(c):
        return (c.get("OOS_2026", {}) or {}).get("avg_pnl")

    clearing_pool = candidates + [
        {**ec, "OOS_2026": ec["OOS_2026"],
         "strike_label": ec["cell"]["strike_label"],
         "premium_stop_pct": ec["cell"]["premium_stop_pct"],
         "tp1_premium_pct": ec["tp1_premium_pct"],
         "runner_target_premium_pct": ec["runner_target_premium_pct"],
         "chandelier": ec["chandelier"]}
        for ec in exit_candidates
    ]
    if clearing_pool:
        best_overall = max(clearing_pool, key=lambda c: (_oos_avg(c) or -1e9))
    else:
        best_overall = max(grid, key=lambda c: (_oos_avg(c) if _oos_avg(c) is not None else -1e9))

    summary = {
        "run_date": dt.date.today().isoformat(),
        "family": "hs_bear",
        "setup": "HEAD_AND_SHOULDERS_BEAR",
        "window": f"{START}..{END}",
        "entry_window_et": f"{ENTRY_TIME_START}-{ENTRY_TIME_END}",
        "n_signals": len(signals),
        "authority": "real OPRA fills via simulator_real.simulate_trade_real (C1)",
        "strike_convention_verified": (
            "side=P: strike=atm-offset (offset<0=ITM strike-above-spot, >0=OTM); "
            "side=C: strike=atm+offset (offset<0=ITM, >0=OTM). Verified in "
            "simulator_real.py lines 357-364 BEFORE the sweep (anti-pattern 2.2)."
        ),
        "candidate_edge_bar": {
            "oos_per_trade_expectancy": "> 0",
            "positive_quarters": f">= {BAR_MIN_POS_QUARTERS}/6",
            "top5_day_pct": f"< {BAR_MAX_TOP5_PCT}",
            "n_trades": f">= {BAR_MIN_N}",
            "all_must_hold": True,
        },
        "baselines": {
            "P_ATM_stop_-0.08_v15exits": baseline_v15,
            "P_ATM_chartstop_-0.99": baseline_chartstop,
        },
        "grid_strike_x_stop_puts": grid,
        "exit_minisweep_on_oos_positive_cells": exit_sweeps,
        "direction_split": dir_split,
        "candidate_edges_clearing_bar": candidates,
        "exit_combos_clearing_bar": exit_candidates,
        "best_config_overall": {
            "strike_label": best_overall.get("strike_label"),
            "premium_stop_pct": best_overall.get("premium_stop_pct"),
            "tp1_premium_pct": best_overall.get("tp1_premium_pct", 0.30),
            "runner_target_premium_pct": best_overall.get("runner_target_premium_pct", 2.5),
            "chandelier": best_overall.get("chandelier", False),
            "overall": best_overall.get("overall"),
            "OOS_2026": best_overall.get("OOS_2026"),
            "positive_quarters": best_overall.get("positive_quarters"),
            "clears_bar": best_overall.get("clears_bar", False),
        },
        "DISCLOSURE": {
            "per_trade": "avg_pnl IS the per-trade expectancy (OP-14) — reported on every cut, not WR alone.",
            "is_oos": "IS=2025 (~12mo), OOS=2026 (~4.5mo to 05-15). Sign-stability is the gate, not raw total.",
            "concentration": "top5_day_pct = top-5 WINNING days as % of total P&L (OP-20 #5).",
            "spy_vs_option": "Signal scan WR != option edge (C3/L58). This is the option-edge sweep.",
            "no_survivor": "Cells failing n/quarters/top5/OOS-sign are kept with clears_bar=false + fail_reasons (anti-pattern 2.10).",
            "direction_note": "CALLS on H&S-top bars is a counterfactual to expose the bull-tilt; H&S-top is structurally a PUT setup.",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    # Console verdict
    print("\n=== EDGE HUNT: hs_bear ===")
    print(f"signals={len(signals)}")
    print(f"BASELINE P/ATM/-0.08/v15 : overall={baseline_v15['overall']} "
          f"OOS={baseline_v15['OOS_2026']} pos_q={baseline_v15['positive_quarters']}")
    print(f"BASELINE P/ATM/chartstop : overall={baseline_chartstop['overall']} "
          f"OOS={baseline_chartstop['OOS_2026']} pos_q={baseline_chartstop['positive_quarters']}")
    print(f"\nCANDIDATE EDGES clearing the bar (grid): {len(candidates)}")
    for c in candidates:
        print(f"  P {c['strike_label']} stop={c['premium_stop_pct']}: "
              f"overall={c['overall']} OOS={c['OOS_2026']} pos_q={c['positive_quarters']}")
    print(f"EXIT combos clearing the bar: {len(exit_candidates)}")
    for ec in exit_candidates:
        print(f"  {ec['cell']['strike_label']} stop={ec['cell']['premium_stop_pct']} "
              f"tp1={ec['tp1_premium_pct']} runner={ec['runner_target_premium_pct']} "
              f"chand={ec['chandelier']}: OOS={ec['OOS_2026']} overall={ec['overall']}")
    print(f"\nBEST config overall: {summary['best_config_overall']}")
    print("\nDIRECTION SPLIT (PUT vs CALL, ATM, by stop):")
    for row in dir_split["by_stop"]:
        print(f"  stop={row['premium_stop_pct']}: "
              f"PUT overall={row['PUT_ATM']} | CALL overall={row['CALL_ATM']}")
    return summary


if __name__ == "__main__":
    main()
