"""EDGE-HUNT: vwap_continuation (J_VWAP_CONT) real-fills strike x stop x exit sweep.

Family spec: morning (<=10:30 ET) VWAP-side continuation. The first TREND_BARS (3) RTH
closes are all on the SAME side of the as-of session VWAP -> that is the day's side; the
first morning bar that CONTINUES in-trend (fresh in-trend extreme = breakout, OR a shallow
VWAP-ward dip that closes back with-trend = pullback) is the entry. One causal entry/day,
fill the NEXT bar open (no look-ahead). Detector is BYTE-FOR-BYTE the validated
``j_daily_pattern_ratify.detect_j_vwap_continuation`` (which is what the live
``vwap_continuation_watcher`` ports) -- we REUSE that exact logic + the validated
``infinite_ammo_discovery.simulate_signals`` real-fills path (nearest-cached strike +
``simulate_trade_real`` OPRA fills + entry_vix) so nothing drifts (C14).

THE SWEEP (the whole point -- "different contract sizing + different exits"):
  * strike_offset in {-2,-1,0,1,2}  (NEGATIVE = ITM, POSITIVE = OTM, for BOTH sides --
    VERIFIED in simulator_real.py lines 357-364: puts strike = atm - offset, calls
    strike = atm + offset; so offset<0 => ITM for both. Anti-pattern 2.2 cleared.)
  * premium_stop_pct in {-0.08, -0.20, -0.50, -0.99 (chart-stop-only)}.
  * Detect signals ONCE, then loop the 5x4=20 (strike x stop) grid re-running ONLY the
    sim. Default v15 exits otherwise.
  * For any (strike,stop) cell OOS-positive per-trade -> SECOND mini-sweep of exits:
    tp1_premium_pct {0.30,0.50} x runner_target_premium_pct {2.0,2.5,3.0} x
    profit_lock 'trailing'/chandelier trail 0.20 {on,off}. Report best exit combo.
  * Direction split (bull-tilt is real on options).

DISCLOSURE (OP-20, honest): per-trade EXPECTANCY (not WR alone -- OP-14), IS(2025) vs
OOS(2026) split, positive_quarters/6, top5_day_pct (top-5 winning DAYS as % of total P&L).
NO survivor cherry-pick (anti-pattern 2.10): a positive cell that is tiny-N / high-conc /
OOS-negative is reported with clears_bar=false.

CANDIDATE EDGE bar (ALL must hold): OOS per-trade expectancy > 0 AND positive_quarters
>= 4/6 AND top5_day_pct < 200 AND n_trades >= 20.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed (weekend).
Writes analysis/recommendations/edgehunt-vwap_continuation.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_edgehunt_vwap_continuation.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    session_vwap_asof,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "edgehunt-vwap_continuation.json"

# ── Detector params (IDENTICAL to j_daily_pattern_ratify / vwap_continuation_watcher) ─
TREND_BARS = 3
ENTRY_CUTOFF = dt.time(10, 30)
SHALLOW_DIP_TOL = 0.0010
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

# ── Sweep space ───────────────────────────────────────────────────────────────
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]          # negative=ITM, positive=OTM (verified)
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]  # -0.99 = chart-stop-only
MAX_STRIKE_STEPS = 4                          # nearest-cached snap radius (matches ratify)
QTY = 3

# Exit mini-sweep (only for OOS-positive base cells)
EXIT_TP1 = [0.30, 0.50]
EXIT_RUNNER = [2.0, 2.5, 3.0]
EXIT_TRAIL = [0.0, 0.20]   # 0.0 = no chandelier; 0.20 = trailing chandelier 20% off HWM

# OOS split: 2025 = IS, 2026 = OOS (calendar-year split, the OP-20 convention).
OOS_YEAR = 2026

# Candidate-edge bar
BAR_OOS_EXP = 0.0       # OOS per-trade expectancy must be > 0
BAR_POS_Q = 4           # positive_quarters >= 4/6
BAR_TOP5 = 200.0        # top5_day_pct < 200
BAR_N = 20              # n_trades >= 20


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOAD (task spec: ar_runner.load_data) -> normalize to load_spy() shape
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_spy(spy_raw: pd.DataFrame) -> pd.DataFrame:
    """tz-naive ET + date/t/minute helpers + float cols (mirror infinite_ammo.load_spy)."""
    df = spy_raw.copy()
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    df["minute"] = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


def _align_vix(spy_df: pd.DataFrame, vix_raw: pd.DataFrame) -> pd.Series:
    """ffill VIX close onto SPY bars (mirror infinite_ammo.align_vix). spy_df tz-naive ET."""
    spy_ts = pd.to_datetime(spy_df["timestamp_et"]).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    vix_ts = pd.to_datetime(vix_raw["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_raw["close"].astype(float).values, index=vix_ts)
    vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    aligned = vix_indexed.reindex(spy_ts, method="ffill")
    aligned.index = range(len(aligned))
    return aligned.fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR (byte-for-byte j_daily_pattern_ratify.detect_j_vwap_continuation)
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side(closes, vwap, n) -> Optional[str]:
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def _vix_slope(vix, idx: int, look: int = 5) -> float:
    arr = vix.values if hasattr(vix, "values") else vix
    if idx < look or idx >= len(arr):
        return 0.0
    return float(arr[idx] - arr[idx - look])


def detect_signals(days: list[DayCtx], vix: pd.Series, *, breakout_only=False,
                   put_needs_rising_vix=False) -> list[Signal]:
    """One causal J_VWAP_CONT entry/day. Mirror of the validated detector."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + SHALLOW_DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - SHALLOW_DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if breakout_only:
                trig = "breakout" if breakout else None
            if trig is None:
                continue
            if put_needs_rising_vix and side == "P" and _vix_slope(vix, int(idxs[j])) < 0:
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jvwap_{trig}"))
            break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM — re-run ONLY simulate_trade_real per cell (signals fixed). Validated path:
# nearest-cached strike at the requested offset + entry_vix + chart-stop rejection.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    strike: int
    atm: int
    strike_off: int
    entry_premium: float
    pnl: float
    pct: float
    exit_reason: str
    trig: str


def simulate_cell(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct,
                  tp1_premium_pct=0.30, runner_target_premium_pct=2.5,
                  profit_lock_trail_pct=0.0) -> tuple[list[TradeRow], dict]:
    """Run every signal at one (strike,stop[,exit]) cell on real OPRA fills."""
    use_trailing = profit_lock_trail_pct > 0
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="JVWAP_EDGEHUNT", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
            tp1_premium_pct=tp1_premium_pct,
            runner_target_premium_pct=runner_target_premium_pct,
            profit_lock_mode=("trailing" if use_trailing else "fixed"),
            profit_lock_trail_pct=(profit_lock_trail_pct if use_trailing else 0.0),
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, strike=int(strike), atm=int(atm),
            strike_off=int(strike - atm),
            entry_premium=round(float(fill.entry_premium), 4),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            trig=sg.note,
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day_top5_pct(rows: list[TradeRow]) -> Optional[float]:
    """top-5 winning DAYS as % of total P&L (OP-20 #5). None if total<=0."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())

    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    # per-quarter expectancy
    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    # direction split
    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    top5 = _by_day_top5_pct(rows)
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": top5,
        "by_side": by_side,
        "exit_hist": {k: v for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


def clears_bar(m: dict) -> tuple[bool, list[str]]:
    """Candidate-edge gate. Returns (clears, list_of_failed_reasons)."""
    fails = []
    if m.get("n", 0) < BAR_N:
        fails.append(f"n={m.get('n', 0)}<{BAR_N}")
    if m.get("oos_exp", -1) <= BAR_OOS_EXP:
        fails.append(f"oos_exp={m.get('oos_exp')}<=0")
    if m.get("positive_quarters_n", 0) < BAR_POS_Q:
        fails.append(f"pos_q={m.get('positive_quarters', '?')}<{BAR_POS_Q}/6")
    t5 = m.get("top5_day_pct")
    if t5 is None or t5 >= BAR_TOP5:
        fails.append(f"top5_day_pct={t5}>={BAR_TOP5}")
    return (len(fails) == 0, fails)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"[edgehunt] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    # RTH filter is done per-day inside build_day_contexts; keep full spy for sim walk-forward.
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[edgehunt] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    print(f"[edgehunt] computing ribbon (for ribbon-flip exits) ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # Detect the family signals ONCE (full pattern, no VIX gate = headline cell).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[edgehunt] signals detected: {len(signals)} on {sig_days} days "
          f"(fires {round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    # ── BASE GRID: 5 strikes x 4 stops, re-run only the sim ──────────────────
    grid = []
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            rows, cov = simulate_cell(signals, spy, ribbon, vix,
                                      strike_offset=so, premium_stop_pct=ps)
            m = metrics(rows)
            clears, fails = clears_bar(m)
            cell = {
                "strike_offset": so,
                "strike_tier": (f"ITM{abs(so)}" if so < 0 else ("ATM" if so == 0 else f"OTM{so}")),
                "premium_stop_pct": ps,
                "stop_label": ("chart_stop_only" if ps <= -0.99 else f"{int(ps*100)}pct"),
                "coverage": cov,
                "metrics": m,
                "clears_bar": clears,
                "clears_bar_fails": fails,
            }
            grid.append(cell)
            mm = m if m.get("n") else {}
            print(f"  off={so:+d}({cell['strike_tier']:>4}) stop={ps:>6} | "
                  f"n={mm.get('n','-'):>3} exp=${mm.get('exp_dollar','-'):>7} "
                  f"oos_exp=${mm.get('oos_exp','-'):>7} (oos_n={mm.get('oos_n','-')}) "
                  f"posQ={mm.get('positive_quarters','-')} top5%={mm.get('top5_day_pct','-')} "
                  f"-> {'CLEARS' if clears else 'no ('+';'.join(fails)+')'}", flush=True)

    # ── EXIT MINI-SWEEP for every OOS-positive base cell ─────────────────────
    exit_sweeps = []
    oos_pos_cells = [c for c in grid if c["metrics"].get("oos_exp", -1) > 0
                     and c["metrics"].get("n", 0) >= BAR_N]
    print(f"\n[edgehunt] exit mini-sweep on {len(oos_pos_cells)} OOS-positive base cell(s) "
          f"(n>={BAR_N}) ...", flush=True)
    for c in oos_pos_cells:
        so, ps = c["strike_offset"], c["premium_stop_pct"]
        best = None
        combos = []
        for tp1 in EXIT_TP1:
            for rt in EXIT_RUNNER:
                for tr in EXIT_TRAIL:
                    rows, cov = simulate_cell(
                        signals, spy, ribbon, vix, strike_offset=so, premium_stop_pct=ps,
                        tp1_premium_pct=tp1, runner_target_premium_pct=rt,
                        profit_lock_trail_pct=tr)
                    m = metrics(rows)
                    clears, fails = clears_bar(m)
                    combo = {
                        "tp1_premium_pct": tp1, "runner_target_premium_pct": rt,
                        "profit_lock_trail_pct": tr,
                        "n": m.get("n"), "exp_dollar": m.get("exp_dollar"),
                        "oos_exp": m.get("oos_exp"), "oos_n": m.get("oos_n"),
                        "total_dollar": m.get("total_dollar"),
                        "positive_quarters": m.get("positive_quarters"),
                        "top5_day_pct": m.get("top5_day_pct"),
                        "clears_bar": clears, "clears_bar_fails": fails,
                    }
                    combos.append(combo)
                    # rank by OOS expectancy (the out-of-sample edge), tiebreak overall exp
                    key = (m.get("oos_exp", -9e9), m.get("exp_dollar", -9e9))
                    if best is None or key > (best["oos_exp"], best["exp_dollar"]):
                        best = combo
        exit_sweeps.append({
            "base_cell": {"strike_offset": so, "strike_tier": c["strike_tier"],
                          "premium_stop_pct": ps, "stop_label": c["stop_label"]},
            "best_exit": best,
            "all_combos": combos,
        })
        print(f"  cell off={so:+d} stop={ps}: best exit tp1={best['tp1_premium_pct']} "
              f"runner={best['runner_target_premium_pct']} trail={best['profit_lock_trail_pct']} "
              f"-> oos_exp=${best['oos_exp']} exp=${best['exp_dollar']} "
              f"posQ={best['positive_quarters']} {'CLEARS' if best['clears_bar'] else 'no'}",
              flush=True)

    # ── Direction split on the headline ATM/chart-stop cell + best base cell ──
    atm_chart = next((c for c in grid if c["strike_offset"] == 0
                      and c["premium_stop_pct"] <= -0.99), None)
    # best base cell by OOS expectancy among filled cells
    filled = [c for c in grid if c["metrics"].get("n", 0) > 0]
    best_base = max(filled, key=lambda c: c["metrics"].get("oos_exp", -9e9)) if filled else None

    # candidate edges = base cells that clear the bar (PLUS note their best exit if swept)
    candidate_cells = [c for c in grid if c["clears_bar"]]

    summary = {
        "family": "vwap_continuation",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE j_daily_pattern_ratify.detect_j_vwap_continuation "
                     "(full pattern, breakout+pullback, no VIX gate = headline cell); live port = "
                     "backtest/lib/watchers/vwap_continuation_watcher.py"),
        "fills_authority": ("real OPRA bars via lib.simulator_real.simulate_trade_real "
                            "(C1); nearest-cached strike snap <=4 (infinite_ammo path); causal "
                            "next-bar-open entry, chart-stop = session extreme via rejection_level"),
        "strike_offset_convention": ("VERIFIED simulator_real.py L357-364: puts strike=atm-offset, "
                                     "calls strike=atm+offset => NEGATIVE offset = ITM for BOTH "
                                     "sides, POSITIVE = OTM (anti-pattern 2.2 cleared)"),
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "candidate_edge_bar": {
            "oos_exp_per_trade": "> 0", "positive_quarters": f">= {BAR_POS_Q}/6",
            "top5_day_pct": f"< {BAR_TOP5}", "n_trades": f">= {BAR_N}",
        },
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "sweep_space": {
            "strike_offsets": STRIKE_OFFSETS, "premium_stops": PREMIUM_STOPS,
            "exit_tp1": EXIT_TP1, "exit_runner": EXIT_RUNNER, "exit_trail": EXIT_TRAIL,
        },
        "base_grid": grid,
        "exit_mini_sweeps": exit_sweeps,
        "headline_atm_chartstop": atm_chart,
        "best_base_cell_by_oos_exp": best_base,
        "candidate_cells": candidate_cells,
        "n_candidate_cells": len(candidate_cells),
        "DISCLOSURE": {
            "per_trade": "expectancy (exp_dollar / oos_exp) reported, not WR alone (OP-14)",
            "is_oos": "IS=2025 vs OOS=2026 split per cell (OP-20)",
            "concentration": "top5_day_pct = top-5 winning DAYS as % of total P&L (OP-20 #5)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "no_survivor_pick": ("every cell reported with clears_bar + the exact failing "
                                 "gates; a positive-but-tiny-N / high-conc / OOS-neg cell is "
                                 "marked clears_bar=false (anti-pattern 2.10)"),
            "fill_caveat": ("nearest-cached strike snap (<=4) means deep ITM/OTM offsets may "
                            "snap inward when uncached; coverage.fill_rate + strike_off per "
                            "trade disclose this"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[edgehunt] wrote {OUT}", flush=True)

    # ── Console verdict ──────────────────────────────────────────────────────
    print("\n=== VWAP_CONTINUATION EDGE-HUNT VERDICT ===")
    print(f"signals={len(signals)} fires {summary['signal_fire_day_pct']}% of {n_days} days  "
          f"side={side_ct}")
    if atm_chart and atm_chart["metrics"].get("n"):
        a = atm_chart["metrics"]
        print(f"HEADLINE ATM/chart-stop: n={a['n']} exp=${a['exp_dollar']} "
              f"oos_exp=${a['oos_exp']} posQ={a['positive_quarters']} top5%={a['top5_day_pct']} "
              f"bull={a['by_side'].get('C')} bear={a['by_side'].get('P')}")
    print(f"candidate cells (clear ALL bars): {len(candidate_cells)}")
    for c in candidate_cells:
        m = c["metrics"]
        print(f"  off={c['strike_offset']:+d}({c['strike_tier']}) stop={c['premium_stop_pct']} "
              f"-> n={m['n']} oos_exp=${m['oos_exp']} exp=${m['exp_dollar']} "
              f"posQ={m['positive_quarters']} top5%={m['top5_day_pct']}")
    if not candidate_cells:
        print("  NONE clear the candidate-edge bar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
