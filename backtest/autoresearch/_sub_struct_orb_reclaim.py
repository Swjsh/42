"""STRUCTURAL-MIMIC: struct_orb_reclaim — opening-range RECLAIM continuation.

HYPOTHESIS (J, 2026-06-20): a NEW structural ONE-causal-entry/day detector that
mimics vwap_continuation's WINNING SHAPE (one with-trend entry/day, no confluence
stack) but reads a DIFFERENT structural primitive: the OPENING-RANGE RECLAIM.

    Price builds an opening range (OR) over the first OR_BARS of RTH. Later in the
    morning price BREAKS the OR (closes beyond OR-high or OR-low = a FAILED breakout),
    then RECLAIMS back THROUGH the broken edge in the TREND direction. The reclaim
    bar is the one causal entry. With-trend = the direction of the reclaim (a break
    BELOW that reclaims back ABOVE -> bullish CALL; a break ABOVE that reclaims back
    BELOW -> bearish PUT). This is the classic "ORB failure / reclaim" continuation.

WHY THIS, NOT MORE CONFLUENCE (the campaign's thesis):
  * The selection campaign proved ADDITIVE confluence is DEAD on 0DTE (theta-trap /
    single-regime / over-constraint). The ONE win was SUBTRACTIVE (skip the worst
    VIX tercile of vwap entries -> cleared all 8 gates). So the path is (a) SUBTRACT
    bad conditions and (b) MIMIC vwap's STRUCTURAL SHAPE with a fresh primitive.
  * struct_orb_reclaim is exactly that: ONE causal entry/day, with-trend, no stacked
    confirmations. It is a STRUCTURAL test of whether a *different* one-entry/day
    shape carries a real per-trade option edge on real OPRA fills.

CAUSALITY (C6 — no look-ahead):
  * OR = first OR_BARS RTH bars (e.g. 15-min = 3 bars, 30-min = 6 bars). The OR is
    FROZEN once those bars CLOSE; we only consider entries on bars AFTER the OR.
  * A bar j (OR_BARS <= j, t[j] <= ENTRY_CUTOFF) is a reclaim iff:
      - a PRIOR bar k in [OR_BARS, j-1] CLOSED beyond the OR edge (the break), AND
      - bar j CLOSES back through that edge in the with-trend direction.
  * Everything uses closes[:j+1] / the FROZEN OR (computed from bars[:OR_BARS]) ->
    reading at bar j is causal. Entry fills the NEXT bar open (sim handles it).
  * stop_level = the structural extreme of the break leg (the failed-breakout
    extreme): for a bullish reclaim the LOW since the OR formed; for a bearish
    reclaim the HIGH since the OR formed. Chart-stop = that level via rejection_level.

REAL FILLS (C1): lib.simulator_real.simulate_trade_real — nearest-cached strike snap
(<=4) + OPRA bars + entry_vix + chart-stop via rejection_level. Reuses the EXACT
edgehunt/exploitation sim+metrics path so nothing drifts (C14).

STRIKE: ITM-2 (strike_offset=-2) PRIMARY (survivor structure), AND OTM-2
(strike_offset=+2 = Safe-2's actual $2K tier) reported per C29 (gates don't transfer
across strike tiers). Two OR windows reported (15-min / 30-min) — NO cherry-pick
(anti-pattern 2.10): every (OR x strike) cell is reported with its full gate verdict.

ALL 8 GATES MANDATORY (anti-2.10):
  1. OOS(2026) per-trade > 0
  2. positive_quarters >= 4/6
  3. top5_day_pct < 200
  4. n_trades >= 20
  5. drop-top5 per-trade > 0  (day-concentration robustness)
  6. IS(2025)-half > 0        (split IS in two; first-half per-trade > 0)
  7. beats random-entry-null  (L172 — ~20 seeds; signal > coin-flip on same days/sides)
  8. no-truncation            (L171 — per-trade SIGN holds from -8% stop -> chart-stop-only -0.99)

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed (weekend).
Writes analysis/recommendations/sub-struct-orb-reclaim.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_struct_orb_reclaim.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# REUSE the validated data normalizers + sim path so the real-fills authority is
# byte-for-byte identical to the campaign (no drift — C14).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    ENTRY_CUTOFF,        # 10:30 ET morning cutoff (matches vwap's shape)
    MAX_STRIKE_STEPS,    # nearest-cached snap radius (4)
    QTY,                 # 3 (2 TP + 1 runner)
    OOS_YEAR,            # 2026
)
from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sub-struct-orb-reclaim.json"

# ── Detector params ─────────────────────────────────────────────────────────────
# OR windows: 15-min (3 x 5m bars) and 30-min (6 x 5m bars). RTH bars are 5m.
OR_BAR_CHOICES = {"15min": 3, "30min": 6}
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
# A "break" close must clear the OR edge by at least this fraction (filters touches
# that merely tag the edge). Small, structural — not a tuned knob.
BREAK_TOL = 0.0      # close strictly beyond the edge is the break (>= / <=)

# ── Strike tiers (C29: report both; ITM-2 primary, OTM-2 = Safe-2's $2K tier) ────
STRIKE_OFFSETS = {"ITM2": -2, "OTM2": 2}
PRIMARY_TIER = "ITM2"

# ── Stop (survivor config) + the no-truncation reference cell ───────────────────
SURV_PREMIUM_STOP = -0.08   # -8% premium stop (survivor)
CHART_STOP_ONLY = -0.99     # no-truncation fraud reference (L171)

# ── Fraud-gate params ───────────────────────────────────────────────────────────
N_NULL_SEEDS = 20           # L172 random-entry null seed count

# ── 8-gate bars ─────────────────────────────────────────────────────────────────
BAR_OOS_EXP = 0.0
BAR_POS_Q = 4
BAR_TOP5 = 200.0
BAR_N = 20


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR — opening-range RECLAIM. One causal with-trend entry/day.
# ─────────────────────────────────────────────────────────────────────────────
def detect_orb_reclaim(days: list[DayCtx], *, or_bars: int) -> list[Signal]:
    """One causal ORB-reclaim entry/day.

    OR frozen from the first `or_bars` RTH closes/highs/lows. For each later bar j
    (j >= or_bars, t[j] <= ENTRY_CUTOFF) we look for a FAILED breakout that has now
    RECLAIMED:

      BULLISH (CALL): some prior bar k in [or_bars, j-1] CLOSED below OR-low (failed
        downside break), and bar j CLOSES back ABOVE OR-low. stop = min low since OR.
      BEARISH (PUT): some prior bar k CLOSED above OR-high (failed upside break),
        and bar j CLOSES back BELOW OR-high. stop = max high since OR.

    First reclaim wins (one entry/day, break on first match). With-trend = the
    reclaim direction. Causal: OR is frozen pre-window; bar j reads closes[:j+1].
    """
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < or_bars + 2:
            continue
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()

        or_high = float(np.max(highs[:or_bars]))
        or_low = float(np.min(lows[:or_bars]))
        if or_high <= or_low:
            continue

        broke_down = False   # a prior bar closed below OR-low
        broke_up = False     # a prior bar closed above OR-high
        for j in range(or_bars, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            cj = closes[j]
            # detect a reclaim BEFORE registering this bar's own break, so the same
            # bar can't both break and reclaim (a reclaim needs a PRIOR break bar).
            if broke_down and cj > or_low:
                # bullish reclaim of OR-low — stop = structural low of the break leg
                stop = float(np.min(lows[:j + 1]))
                out.append(Signal(bar_idx=int(idxs[j]), side="C", stop_level=stop,
                                  note=f"orb{or_bars}_reclaim_low"))
                break
            if broke_up and cj < or_high:
                # bearish reclaim of OR-high — stop = structural high of the break leg
                stop = float(np.max(highs[:j + 1]))
                out.append(Signal(bar_idx=int(idxs[j]), side="P", stop_level=stop,
                                  note=f"orb{or_bars}_reclaim_high"))
                break
            # register this bar's break for FUTURE bars to reclaim
            if cj < or_low:
                broke_down = True
            elif cj > or_high:
                broke_up = True
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM — re-run simulate_trade_real per (strike, stop) cell. Validated path.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    trig: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct):
    """Real-fills sim of a signal set at one (strike,stop). v15 default exits."""
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
            qty=QTY, setup="STRUCT_ORB_RECLAIM", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side,
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
# METRICS (OP-20 disclosure — mirrors the exploitation harness)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day_top5_pct(rows: list[TradeRow]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_topN_day_per_trade(rows: list[TradeRow], k: int = 5) -> Optional[float]:
    """Per-trade mean after removing the k highest-P&L *days* entirely (gate 5)."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _is_first_half_per_trade(rows: list[TradeRow]) -> Optional[float]:
    """Gate 6: split the IS (non-OOS) trades chronologically in two; first-half
    per-trade. >0 means the IS edge is not all back-loaded onto the OOS boundary."""
    is_rows = sorted((r for r in rows if int(r.date[:4]) != OOS_YEAR),
                     key=lambda r: r.date)
    if len(is_rows) < 2:
        return None
    half = len(is_rows) // 2
    first = is_rows[:half]
    return round(float(np.mean([r.pnl for r in first])), 2) if first else None


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

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    # max drawdown on the chronological cumulative P&L curve (disclosure)
    chrono = [r.pnl for r in sorted(rows, key=lambda r: r.date)]
    cum = np.cumsum(chrono)
    running_max = np.maximum.accumulate(cum)
    max_dd = round(float(np.min(cum - running_max)), 2) if len(cum) else 0.0

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "max_drawdown": max_dd,
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_exp": _is_first_half_per_trade(rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# FRAUD GATE 7 — random-entry null (L172). Same days+sides, random morning bar.
# Proves the SIGNAL (reclaim timing) beats a coin-flip morning entry on a day we
# already know broke the OR on that side. Hardest fair control.
# ─────────────────────────────────────────────────────────────────────────────
def random_null(signals, spy, ribbon, vix, days, *, or_bars, seeds=N_NULL_SEEDS,
                strike_offset, premium_stop_pct=SURV_PREMIUM_STOP) -> dict:
    """Same-day, same-side random-entry null over the morning window."""
    day_bars: dict[dt.date, list[int]] = {}
    for dc in days:
        rth = dc.rth
        times = rth["t"].values
        idxs = rth.index.tolist()
        elig = [int(idxs[j]) for j in range(or_bars, len(rth)) if times[j] <= ENTRY_CUTOFF]
        if elig:
            day_bars[dc.date] = elig
    sig_specs = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        sig_specs.append((d, sg.side, sg.stop_level))

    per_seed_exp, per_seed_oos_exp, per_seed_total = [], [], []
    for seed in range(seeds):
        rng = np.random.default_rng(2000 + seed)
        rand_sigs = []
        for d, side, stop in sig_specs:
            elig = day_bars.get(d)
            if not elig:
                continue
            bidx = int(rng.choice(elig))
            rand_sigs.append(Signal(bar_idx=bidx, side=side, stop_level=stop, note="rand"))
        rows, _ = simulate_set(rand_sigs, spy, ribbon, vix,
                               strike_offset=strike_offset, premium_stop_pct=premium_stop_pct)
        if rows:
            m = metrics(rows)
            per_seed_exp.append(m["exp_dollar"])
            per_seed_oos_exp.append(m["oos_exp"])
            per_seed_total.append(m["total_dollar"])
    if not per_seed_exp:
        return {"seeds": 0}
    return {
        "seeds": len(per_seed_exp),
        "null_exp_mean": round(float(np.mean(per_seed_exp)), 2),
        "null_exp_min": round(float(np.min(per_seed_exp)), 2),
        "null_exp_max": round(float(np.max(per_seed_exp)), 2),
        "null_exp_std": round(float(np.std(per_seed_exp)), 2),
        "null_oos_exp_mean": round(float(np.mean(per_seed_oos_exp)), 2),
        "null_total_mean": round(float(np.mean(per_seed_total)), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# THE 8-GATE EVALUATION for one (OR x strike) cell.
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_cell(signals, spy, ribbon, vix, days, *, or_bars, strike_offset) -> dict:
    rows, cov = simulate_set(signals, spy, ribbon, vix,
                             strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    m = metrics(rows)
    # no-truncation (gate 8): same signals at chart-stop-only
    cs_rows, _ = simulate_set(signals, spy, ribbon, vix,
                              strike_offset=strike_offset, premium_stop_pct=CHART_STOP_ONLY)
    cs_m = metrics(cs_rows)
    nt_sign_stable = bool(
        m.get("n") and cs_m.get("n")
        and (m["exp_dollar"] > 0) == (cs_m.get("exp_dollar", 0) > 0)
    )
    # random-null (gate 7)
    nullb = random_null(signals, spy, ribbon, vix, days,
                        or_bars=or_bars, strike_offset=strike_offset)
    beats_null = False
    if nullb.get("seeds") and m.get("n"):
        thr = nullb["null_exp_mean"] + nullb.get("null_exp_std", 0.0)
        beats_null = bool(m["exp_dollar"] > thr)

    # ── the 8 gates ──────────────────────────────────────────────────────────
    g = {}
    g["g1_oos_per_trade_gt0"] = bool(m.get("oos_exp", -1) > BAR_OOS_EXP)
    g["g2_posq_ge_4of6"] = bool(m.get("positive_quarters_n", 0) >= BAR_POS_Q)
    t5 = m.get("top5_day_pct")
    g["g3_top5_lt_200"] = bool(t5 is not None and t5 < BAR_TOP5)
    g["g4_n_ge_20"] = bool(m.get("n", 0) >= BAR_N)
    dt5 = m.get("drop_top5_day_per_trade")
    g["g5_drop_top5_gt0"] = bool(dt5 is not None and dt5 > 0)
    h1 = m.get("is_first_half_exp")
    g["g6_is_first_half_gt0"] = bool(h1 is not None and h1 > 0)
    g["g7_beats_random_null"] = beats_null
    g["g8_no_truncation_sign_stable"] = nt_sign_stable
    clears_all = all(g.values())

    return {
        "or_window": f"{or_bars}bar",
        "strike_offset": strike_offset,
        "strike_tier": ("ITM%d" % abs(strike_offset)) if strike_offset < 0
                        else ("ATM" if strike_offset == 0 else "OTM%d" % strike_offset),
        "coverage": cov,
        "metrics": m,
        "no_truncation": {
            "stop8_exp": m.get("exp_dollar"), "chartstop_exp": cs_m.get("exp_dollar"),
            "stop8_oos_exp": m.get("oos_exp"), "chartstop_oos_exp": cs_m.get("oos_exp"),
            "stop8_total": m.get("total_dollar"), "chartstop_total": cs_m.get("total_dollar"),
            "sign_stable": nt_sign_stable,
        },
        "random_null": {**nullb, "beats_null": beats_null},
        "gates": g,
        "n_gates_passed": sum(1 for v in g.values() if v),
        "clears_all_gates": clears_all,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[sub-orb] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sub-orb] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    cells = []
    detector_meta = {}
    for or_name, or_bars in OR_BAR_CHOICES.items():
        signals = detect_orb_reclaim(days, or_bars=or_bars)
        sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
        side_ct = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
        fire_pct = round(100 * sig_days / n_days, 1) if n_days else 0.0
        detector_meta[or_name] = {"or_bars": or_bars, "n_signals": len(signals),
                                  "fire_day_pct": fire_pct, "side_count": side_ct}
        print(f"\n[sub-orb] OR={or_name} ({or_bars}bar): signals={len(signals)} on "
              f"{sig_days} days (fires {fire_pct}% of days) side={side_ct}", flush=True)
        for tier, so in STRIKE_OFFSETS.items():
            cell = evaluate_cell(signals, spy, ribbon, vix, days,
                                 or_bars=or_bars, strike_offset=so)
            cell["or_window"] = or_name
            cell["tier"] = tier
            cells.append(cell)
            m = cell["metrics"]
            print(f"  [{or_name}/{tier} off={so:+d}] n={m.get('n','-')} "
                  f"exp=${m.get('exp_dollar','-')} oos_exp=${m.get('oos_exp','-')} "
                  f"(oos_n={m.get('oos_n','-')}) posQ={m.get('positive_quarters','-')} "
                  f"top5%={m.get('top5_day_pct','-')} droptop5=${m.get('drop_top5_day_per_trade','-')} "
                  f"isH1=${m.get('is_first_half_exp','-')} beats_null={cell['random_null'].get('beats_null')} "
                  f"trunc_stable={cell['no_truncation'].get('sign_stable')} "
                  f"-> {cell['n_gates_passed']}/8 {'CLEARS' if cell['clears_all_gates'] else 'no'}",
                  flush=True)

    # ── Headline = PRIMARY tier (ITM-2). Prefer 30min if it clears, else best by
    #    n_gates_passed then OOS per-trade among primary cells. ────────────────
    primary_cells = [c for c in cells if c["tier"] == PRIMARY_TIER]
    clearing = [c for c in cells if c["clears_all_gates"]]
    primary_clearing = [c for c in primary_cells if c["clears_all_gates"]]

    def _rank_key(c):
        return (c["n_gates_passed"], c["metrics"].get("oos_exp", -9e9))

    headline = None
    if primary_clearing:
        headline = max(primary_clearing, key=_rank_key)
    elif primary_cells:
        headline = max(primary_cells, key=_rank_key)

    summary = {
        "study": "struct_orb_reclaim (structural-mimic of vwap_continuation's one-entry/day shape)",
        "slug": "struct-orb-reclaim",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "hypothesis": ("opening-range RECLAIM continuation: price builds an OR over the first "
                       "OR_BARS RTH bars, BREAKS it (failed breakout), then RECLAIMS back "
                       "through the broken edge in the trend direction -> ONE causal with-trend "
                       "entry/day. Mimics vwap_continuation's WINNING SHAPE (one causal entry/day, "
                       "no confluence stack) on a DIFFERENT structural primitive."),
        "detector": ("clean causal one-entry/day ORB-reclaim (this file's detect_orb_reclaim); "
                     "OR frozen from first OR_BARS RTH bars, reclaim of a PRIOR failed-breakout "
                     "close in the with-trend direction, entry <= 10:30 ET, fill next-bar-open "
                     "(no look-ahead), chart-stop = break-leg structural extreme via rejection_level"),
        "fills_authority": ("real OPRA via lib.simulator_real.simulate_trade_real (C1); "
                            "nearest-cached strike snap <=4 (infinite_ammo path); v15 default exits; "
                            "byte-for-byte same sim+metrics path as the vwap exploitation campaign"),
        "strike_offset_convention": ("simulator_real: puts strike=atm-offset, calls strike=atm+offset "
                                     "=> NEGATIVE=ITM, POSITIVE=OTM for both sides (anti-pattern 2.2 clear)"),
        "strike_tiers": {"primary": "ITM2 (strike_offset=-2, survivor structure)",
                         "secondary": "OTM2 (strike_offset=+2 = Safe-2's $2K tier; C29 — gates "
                                      "don't transfer across strike tiers)"},
        "or_windows": list(OR_BAR_CHOICES.keys()),
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "survivor_config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                            "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)"},
        "eight_gates": {
            "g1": "OOS(2026) per-trade > 0",
            "g2": "positive_quarters >= 4/6",
            "g3": "top5_day_pct < 200",
            "g4": "n_trades >= 20",
            "g5": "drop-top5 per-trade > 0 (day-concentration robust)",
            "g6": "IS(2025) first-half per-trade > 0",
            "g7": "beats random-entry null (L172, 20 seeds, mean+1std)",
            "g8": "no-truncation: per-trade sign holds -8% stop -> chart-stop-only (-0.99) (L171)",
        },
        "detector_meta": detector_meta,
        "cells": cells,
        "n_cells": len(cells),
        "clearing_cells": [{"or_window": c["or_window"], "tier": c["tier"],
                            "strike_offset": c["strike_offset"]} for c in clearing],
        "n_clearing_cells": len(clearing),
        "headline_primary_cell": headline,
        "DISCLOSURE": {
            "per_trade": "expectancy reported (oos_exp), not WR alone (OP-14/C4)",
            "is_oos": "IS=2025 vs OOS=2026 split per cell (OP-20)",
            "concentration": "top5_day_pct + drop_top5_day_per_trade (OP-20 #5 / gate 5)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "no_survivor_pick": ("every (OR x strike) cell reported with all 8 gate booleans + "
                                 "n_gates_passed; nothing cherry-picked (anti-pattern 2.10)"),
            "null_is_hardest_fair": ("random-null uses SAME days/sides (days that broke the OR on "
                                     "the correct side) at random morning bars -> isolates reclaim "
                                     "TIMING from day+side selection + exit bracket (C3/L58)"),
            "fill_caveat": ("nearest-cached strike snap (<=4) may snap deep ITM/OTM inward when "
                            "uncached; coverage.fill_rate discloses this"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sub-orb] wrote {OUT}", flush=True)

    # ── Console verdict ──────────────────────────────────────────────────────
    print("\n=== STRUCT_ORB_RECLAIM VERDICT ===")
    for c in cells:
        m = c["metrics"]
        gates_failed = [k for k, v in c["gates"].items() if not v]
        print(f"  {c['or_window']}/{c['tier']} (off={c['strike_offset']:+d}): "
              f"n={m.get('n','-')} oos_exp=${m.get('oos_exp','-')} "
              f"-> {c['n_gates_passed']}/8 "
              f"{'CLEARS ALL 8' if c['clears_all_gates'] else 'FAILS: ' + ','.join(gates_failed)}")
    if clearing:
        print(f"\nCELLS CLEARING ALL 8 GATES: "
              f"{[(c['or_window'], c['tier']) for c in clearing]}")
    else:
        print("\nNO cell clears all 8 gates.")
    if headline:
        hm = headline["metrics"]
        print(f"\nHEADLINE (primary ITM-2): {headline['or_window']} "
              f"n={hm.get('n')} oos_exp=${hm.get('oos_exp')} "
              f"posQ={hm.get('positive_quarters')} -> {headline['n_gates_passed']}/8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
