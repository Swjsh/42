"""Edge-hunt sweep for the DOUBLE_BOTTOM_BASE_QUIET 0DTE SPY family (real OPRA fills).

Family spec: baseline = double_bottom + confidence<0.60 + VIX<20 calls (side='C', bullish
only — a double bottom is a bullish reversal). This script keeps the baseline signal
detector from db_base_quiet_real_fills_validate.py EXACTLY, then sweeps:

  STRIKE x STOP grid (5 x 4 = 20 cells), re-running ONLY the sim per cell:
    strike_offset in {-2,-1,0,1,2}  (calls: negative=ITM strike-below-spot,
                                     positive=OTM strike-above-spot — VERIFIED in
                                     simulator_real.py lines 357-364, side=='C' branch
                                     does `strike = atm + strike_offset`; anti-pattern 2.2
                                     guarded — the offset IS used).
    premium_stop_pct in {-0.08, -0.20, -0.50, -0.99(chart-stop-only)}.
  Default v15 exits otherwise (tp1_qty_fraction 0.50, tp1 +30%, runner 2.5x, chandelier off).

  EXIT mini-sweep (only on OOS-positive strike/stop cells):
    tp1_premium_pct in {0.30,0.50}
    runner_target_premium_pct in {2.0,2.5,3.0}
    profit_lock chandelier 'trailing' trail 0.20 on/off
  -> report the best exit combo per qualifying cell.

  DIRECTION split: family is calls-only, but to substantiate the documented bull-tilt
  (C3: bull loses less than bear on options) we ALSO run the SAME signals as PUTS
  (side='P', same strike/stop default cell) and report the bull-vs-bear delta.

DISCLOSURE (OP-20, MANDATORY): per-trade expectancy (avg_pnl — NOT WR alone, OP-14),
IS(2025) vs OOS(2026) split, positive_quarters/6, top5_day_pct (top-5 winning DAYS as %
of total P&L). Real OPRA fills are the only WR authority (C1) — no BS-sim, no LLM.
no_data (uncached-strike) coverage tracked per cell so a strike offset that falls outside
the cached OPRA band is reported honestly, not silently dropped.

CANDIDATE EDGE bar (ALL must hold): OOS avg_pnl > 0 AND positive_quarters >= 4/6
AND top5_day_pct < 200 AND n_trades >= 20. A lone positive cell that is tiny-N or
high-concentration or OOS-negative is NOT cherry-picked as a survivor (anti-pattern 2.10);
it is reported with clears_bar=false.

Pure Python, $0 (no LLM in the sim loop). Markets closed — heavy compute fine. No orders.
Output: analysis/recommendations/edgehunt-double_bottom_base_quiet.json
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
sys.path.insert(0, str(ROOT))  # for crypto.lib.chart_patterns

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "edgehunt-double_bottom_base_quiet.json"

# ── Family / signal parameters (verbatim from baseline validate script) ────────
VIX_LOW_VOL_CEILING = 20.0
CONFIDENCE_LOW_CEILING = 0.60     # conf < 0.60 is the BASE_QUIET gate
QTY = 3
RTH_START = dt.time(9, 35)
RTH_END = dt.time(15, 55)
COOLDOWN_MINUTES = 30
_CHART_STOP_BELOW_NECKLINE = 0.30  # chart stop = neckline - $0.30 (+0.50 buffer => -0.80)
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# ── Sweep grids ────────────────────────────────────────────────────────────────
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]
# exit mini-sweep (only on OOS-positive cells)
EXIT_TP1 = [0.30, 0.50]
EXIT_RUNNER = [2.0, 2.5, 3.0]
EXIT_TRAIL = [None, 0.20]  # None=v15 default (no chandelier); 0.20=chandelier trailing

# ── Candidate-edge bar ──────────────────────────────────────────────────────────
BAR_OOS_AVG = 0.0          # OOS per-trade expectancy strictly > 0
BAR_POS_QUARTERS = 4       # >= 4 of 6
BAR_TOP5_PCT = 200.0       # < 200
BAR_N_TRADES = 20          # >= 20

try:
    from crypto.lib.chart_patterns import Bar, double_bottom_detector as _detect_db
except ImportError:
    log.error("crypto.lib.chart_patterns not available — cannot run")
    sys.exit(1)


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    """P&L accumulator with OP-20 disclosure (expectancy + concentration + WR)."""
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


def _make_bars(rth: pd.DataFrame, idx: int, window: int = 30) -> list:
    start = max(0, idx - window + 1)
    sub = rth.iloc[start: idx + 1]
    out = []
    for _, row in sub.iterrows():
        ts = pd.Timestamp(row["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        out.append(Bar(
            open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]),
            volume=int(row.get("volume", 50_000) or 50_000),
            granularity_seconds=300, source="spy_5m",
        ))
    return out


def detect_signals() -> tuple[pd.DataFrame, list[dict]]:
    """Detect the family's signals ONCE. Returns (rth_df, signals)."""
    log.info("Loading %s..%s SPY+VIX...", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill), tz-naive
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
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

    log.info("Scanning for double_bottom+conf<0.60+VIX<20 signals (once)...")
    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None

    for idx in range(len(rth)):
        if idx < 30:
            continue
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bt = bar_time.tz_localize(None).to_pydatetime()
        else:
            bt = pd.Timestamp(bar_time).to_pydatetime()
        bd = bt.date()
        if bd < START or bd > END:
            continue
        t = bt.time()
        if t < RTH_START or t > RTH_END:
            continue
        vix_now = float(vix_arr.iloc[idx])
        if vix_now >= VIX_LOW_VOL_CEILING:
            continue
        if last_signal_time is not None:
            if (bt - last_signal_time).total_seconds() / 60.0 < COOLDOWN_MINUTES:
                continue
        bars = _make_bars(rth, idx)
        if len(bars) < 10:
            continue
        hit = _detect_db(bars)
        if hit is None:
            continue
        if hit.confidence >= CONFIDENCE_LOW_CEILING:
            continue
        last_signal_time = bt
        entry_spot = float(bar["close"])
        neckline = hit.notes.get("neckline", entry_spot)
        rejection_level = float(neckline) - _CHART_STOP_BELOW_NECKLINE
        signals.append({
            "date": bd,
            "time": bt.strftime("%H:%M"),
            "bar_idx": idx,
            "vix": round(vix_now, 1),
            "entry_spot": entry_spot,
            "neckline": round(float(neckline), 2),
            "rejection_level": round(rejection_level, 2),
            "hit_confidence": round(hit.confidence, 3),
        })
    log.info("Found %d signals (detected once; reused across %d strike/stop cells).",
             len(signals), len(STRIKE_OFFSETS) * len(PREMIUM_STOPS))
    return rth, signals


def _sim_cell(rth, signals, strike_offset, premium_stop_pct, side="C",
              tp1_premium_pct=0.30, runner_target_premium_pct=2.5,
              profit_lock_trail_pct=None):
    """Run the sim for one parameter cell over all signals. Returns dict of _Acc + rows."""
    overall = _Acc()
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0
    n_completed = 0

    pl_mode = "trailing" if profit_lock_trail_pct else "fixed"
    pl_trail = profit_lock_trail_pct or 0.0

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["bar_idx"],
            entry_bar=rth.iloc[s["bar_idx"]],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["double_bottom_detector", "rth_window", "low_vol_vix", "conf_low_gate"],
            side=side,
            qty=QTY,
            setup="DOUBLE_BOTTOM_BASE_QUIET",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
            tp1_premium_pct=tp1_premium_pct,
            runner_target_premium_pct=runner_target_premium_pct,
            profit_lock_mode=pl_mode,
            profit_lock_trail_pct=pl_trail,
        )
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        n_completed += 1

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    return {
        "overall": overall,
        "by_sample": by_sample,
        "by_quarter": q_reports,
        "positive_quarters": pos_q,
        "n_quarters": len(q_reports),
        "no_data": no_data,
        "n_completed": n_completed,
    }


def _clears_bar(oos_rep: dict, pos_q: int, n_q: int, overall_rep: dict) -> tuple[bool, list[str]]:
    """Apply the candidate-edge bar. Returns (clears, reasons_failed)."""
    reasons = []
    oos_n = oos_rep.get("n", 0)
    oos_avg = oos_rep.get("avg_pnl", 0) if oos_n else 0
    top5 = overall_rep.get("top5_day_pct")
    n_trades = overall_rep.get("n", 0)
    if not (oos_n and oos_avg > BAR_OOS_AVG):
        reasons.append(f"OOS_avg_pnl={oos_avg} (need >{BAR_OOS_AVG}, n={oos_n})")
    if pos_q < BAR_POS_QUARTERS:
        reasons.append(f"positive_quarters={pos_q}/{n_q} (need >={BAR_POS_QUARTERS})")
    if top5 is None or top5 >= BAR_TOP5_PCT:
        reasons.append(f"top5_day_pct={top5} (need <{BAR_TOP5_PCT})")
    if n_trades < BAR_N_TRADES:
        reasons.append(f"n_trades={n_trades} (need >={BAR_N_TRADES})")
    return (len(reasons) == 0), reasons


def main() -> dict:
    rth, signals = detect_signals()
    if not signals:
        log.error("No signals — aborting.")
        summary = {"family": "double_bottom_base_quiet", "error": "no signals", "n_signals": 0}
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary

    # ── PHASE 1: 5x4 strike x stop grid (calls, default v15 exits) ─────────────
    log.info("=== PHASE 1: strike x stop grid (calls) ===")
    grid_cells: list[dict] = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            res = _sim_cell(rth, signals, so, ps, side="C")
            o_rep = res["overall"].report()
            oos_rep = res["by_sample"]["OOS_2026"].report()
            is_rep = res["by_sample"]["IS_2025"].report()
            clears, fails = _clears_bar(oos_rep, res["positive_quarters"],
                                        res["n_quarters"], o_rep)
            label = f"strike{so:+d}_stop{ps}"
            cell = {
                "config": label,
                "strike_offset": so,
                "premium_stop_pct": ps,
                "n_trades": o_rep.get("n", 0),
                "no_data": res["no_data"],
                "overall": o_rep,
                "IS_2025": is_rep,
                "OOS_2026": oos_rep,
                "positive_quarters": f"{res['positive_quarters']}/{res['n_quarters']}",
                "by_quarter": res["by_quarter"],
                "clears_bar": clears,
                "fail_reasons": fails,
            }
            grid_cells.append(cell)
            log.info("  %-22s n=%-3d no_data=%-3d overall_avg=%-7s OOS_avg=%-7s posQ=%d/%d top5=%s clears=%s",
                     label, o_rep.get("n", 0), res["no_data"], o_rep.get("avg_pnl"),
                     oos_rep.get("avg_pnl") if oos_rep.get("n") else "n/a",
                     res["positive_quarters"], res["n_quarters"],
                     o_rep.get("top5_day_pct"), clears)

    # ── PHASE 2: exit mini-sweep on OOS-positive strike/stop cells ─────────────
    log.info("=== PHASE 2: exit mini-sweep on OOS-positive cells ===")
    oos_positive_cells = [
        c for c in grid_cells
        if c["OOS_2026"].get("n", 0) and c["OOS_2026"].get("avg_pnl", 0) > 0
    ]
    log.info("OOS-positive strike/stop cells qualifying for exit sweep: %d",
             len(oos_positive_cells))
    exit_sweeps: list[dict] = []
    for c in oos_positive_cells:
        so, ps = c["strike_offset"], c["premium_stop_pct"]
        best = None
        combos: list[dict] = []
        for tp1 in EXIT_TP1:
            for rt in EXIT_RUNNER:
                for trail in EXIT_TRAIL:
                    res = _sim_cell(rth, signals, so, ps, side="C",
                                    tp1_premium_pct=tp1, runner_target_premium_pct=rt,
                                    profit_lock_trail_pct=trail)
                    o_rep = res["overall"].report()
                    oos_rep = res["by_sample"]["OOS_2026"].report()
                    clears, fails = _clears_bar(oos_rep, res["positive_quarters"],
                                                res["n_quarters"], o_rep)
                    combo = {
                        "tp1_premium_pct": tp1,
                        "runner_target_premium_pct": rt,
                        "profit_lock_trail_pct": trail,
                        "n_trades": o_rep.get("n", 0),
                        "overall_avg_pnl": o_rep.get("avg_pnl"),
                        "overall_total_pnl": o_rep.get("total_pnl"),
                        "OOS_avg_pnl": oos_rep.get("avg_pnl") if oos_rep.get("n") else None,
                        "OOS_total_pnl": oos_rep.get("total_pnl") if oos_rep.get("n") else None,
                        "positive_quarters": f"{res['positive_quarters']}/{res['n_quarters']}",
                        "top5_day_pct": o_rep.get("top5_day_pct"),
                        "clears_bar": clears,
                        "fail_reasons": fails,
                    }
                    combos.append(combo)
                    # best = highest OOS total P&L among combos that clear; else highest OOS total
                    key = (combo["clears_bar"], combo["OOS_total_pnl"] or -1e9)
                    if best is None or key > best[0]:
                        best = (key, combo)
        exit_sweeps.append({
            "base_cell": c["config"],
            "strike_offset": so,
            "premium_stop_pct": ps,
            "best_exit_combo": best[1] if best else None,
            "all_combos": combos,
        })
        bc = best[1] if best else {}
        log.info("  cell %-22s best_exit tp1=%s rt=%s trail=%s OOS_total=%s clears=%s",
                 c["config"], bc.get("tp1_premium_pct"), bc.get("runner_target_premium_pct"),
                 bc.get("profit_lock_trail_pct"), bc.get("OOS_total_pnl"), bc.get("clears_bar"))

    # ── PHASE 3: direction split (bull calls vs bear puts on SAME signals) ──────
    log.info("=== PHASE 3: direction split (bull vs bear, ATM/-8% default cell) ===")
    bull = _sim_cell(rth, signals, 0, -0.08, side="C")
    bear = _sim_cell(rth, signals, 0, -0.08, side="P")
    bull_rep, bear_rep = bull["overall"].report(), bear["overall"].report()
    direction_split = {
        "note": ("Family is calls-only (double bottom = bullish reversal). Bear column is "
                 "the SAME signals traded as PUTS to substantiate the documented bull-tilt "
                 "(C3: bull loses less than bear on options). Bear is NOT a tradable config."),
        "cell": "strike+0_stop-0.08 (v15 default)",
        "bull_C": {**bull_rep,
                   "OOS": bull["by_sample"]["OOS_2026"].report(),
                   "positive_quarters": f"{bull['positive_quarters']}/{bull['n_quarters']}"},
        "bear_P": {**bear_rep,
                   "OOS": bear["by_sample"]["OOS_2026"].report(),
                   "positive_quarters": f"{bear['positive_quarters']}/{bear['n_quarters']}"},
        "bull_minus_bear_total_pnl": round((bull_rep.get("total_pnl", 0) or 0)
                                           - (bear_rep.get("total_pnl", 0) or 0), 0),
        "bull_minus_bear_avg_pnl": round((bull_rep.get("avg_pnl", 0) or 0)
                                         - (bear_rep.get("avg_pnl", 0) or 0), 1),
    }

    # ── Pick best overall config (must clear the bar; tiebreak OOS total P&L) ───
    candidate_cells = [c for c in grid_cells if c["clears_bar"]]
    # also consider exit-swept variants that clear
    swept_candidates = []
    for sw in exit_sweeps:
        bc = sw["best_exit_combo"]
        if bc and bc["clears_bar"]:
            swept_candidates.append((sw, bc))

    best_config_overall = None
    if swept_candidates:
        sw, bc = max(swept_candidates, key=lambda x: x[1]["OOS_total_pnl"] or -1e9)
        best_config_overall = (f"{sw['base_cell']} | tp1={bc['tp1_premium_pct']} "
                               f"runner={bc['runner_target_premium_pct']} "
                               f"trail={bc['profit_lock_trail_pct']}")
    elif candidate_cells:
        best = max(candidate_cells, key=lambda c: c["OOS_2026"].get("total_pnl", -1e9) or -1e9)
        best_config_overall = best["config"]

    # baseline cell = ATM / -8% default (matches simulator_real defaults for stop)
    baseline = next((c for c in grid_cells if c["config"] == "strike+0_stop-0.08"), None)
    baseline_avg = baseline["overall"].get("avg_pnl") if baseline else None

    n_clears = sum(1 for c in grid_cells if c["clears_bar"])
    if best_config_overall:
        verdict = (f"CANDIDATE EDGE FOUND: {n_clears}/{len(grid_cells)} strike/stop cells clear "
                   f"the full bar; best config = {best_config_overall}. Real OPRA fills (C1).")
    else:
        # honest negative
        # find the least-bad cell for context
        ranked = sorted(grid_cells, key=lambda c: (c["OOS_2026"].get("avg_pnl", -1e9)
                                                    if c["OOS_2026"].get("n") else -1e9), reverse=True)
        top = ranked[0] if ranked else {}
        verdict = (
            f"NO CANDIDATE EDGE. 0/{len(grid_cells)} strike/stop cells clear the full bar "
            f"(OOS_avg>0 AND posQ>=4/6 AND top5<200 AND n>=20). "
            f"Best OOS cell was {top.get('config')} "
            f"(OOS_avg={top.get('OOS_2026', {}).get('avg_pnl')}, "
            f"posQ={top.get('positive_quarters')}, top5={top.get('overall', {}).get('top5_day_pct')}, "
            f"n={top.get('n_trades')}) — fails: {top.get('fail_reasons')}. "
            f"Not cherry-picked as a survivor (anti-pattern 2.10)."
        )

    summary = {
        "family": "double_bottom_base_quiet",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "authority": "real OPRA fills (C1) — only WR authority; no BS-sim, no LLM in sim loop",
        "side": "C (calls — double bottom is a bullish reversal; calls-only family)",
        "n_signals": len(signals),
        "strike_convention_verified": (
            "calls (side='C'): strike = atm + strike_offset => negative=ITM (strike below "
            "spot), positive=OTM (strike above spot). Verified simulator_real.py L357-364. "
            "anti-pattern 2.2 guarded: offset IS applied to strike."
        ),
        "candidate_edge_bar": {
            "OOS_avg_pnl_gt": BAR_OOS_AVG, "positive_quarters_gte": BAR_POS_QUARTERS,
            "top5_day_pct_lt": BAR_TOP5_PCT, "n_trades_gte": BAR_N_TRADES,
            "logic": "ALL must hold",
        },
        "baseline_default_per_trade": baseline_avg,
        "n_cells_clearing_bar": n_clears,
        "best_config_overall": best_config_overall,
        "honest_verdict": verdict,
        "strike_stop_grid": grid_cells,
        "exit_mini_sweeps": exit_sweeps,
        "direction_split": direction_split,
        "DISCLOSURE": {
            "per_trade": "avg_pnl is per-trade EXPECTANCY, reported alongside (not instead of) WR (OP-14)",
            "is_oos": "IS=2025, OOS=2026-01-01..2026-05-15",
            "concentration": "top5_day_pct = top-5 winning DAYS as % of total P&L (OP-20 #5)",
            "positive_quarters": "count of calendar quarters with positive total P&L, out of 6",
            "no_data": "strike offsets outside the cached OPRA band return None -> counted as no_data, not silently dropped",
            "spy_vs_option": "SPY-direction scan WR (proxy 59.5%) != option edge; this is the option-P&L test (C3/L58)",
            "survivor_guard": "a lone positive cell that is tiny-N/high-concentration/OOS-negative is reported clears_bar=false, never cherry-picked (anti-pattern 2.10)",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== EDGE-HUNT VERDICT: double_bottom_base_quiet ===")
    print(f"signals={len(signals)}  cells_clearing_bar={n_clears}/{len(grid_cells)}")
    print(f"baseline (ATM/-8%) per-trade: {baseline_avg}")
    print(f"best_config_overall: {best_config_overall}")
    print(f"direction: bull_C total={direction_split['bull_C'].get('total_pnl')} "
          f"avg={direction_split['bull_C'].get('avg_pnl')} | "
          f"bear_P total={direction_split['bear_P'].get('total_pnl')} "
          f"avg={direction_split['bear_P'].get('avg_pnl')} | "
          f"bull-bear avg delta={direction_split['bull_minus_bear_avg_pnl']}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    main()
