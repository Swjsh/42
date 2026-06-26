"""SUBTRACTIVE / STRUCTURAL-MIMIC edge test: struct_vwap_reclaim_failed_break.

THESIS (the selection-campaign lesson encoded — C4/L122/L154/L166):
  ADDITIVE confluence (stack more confirmations) is DEAD on 0DTE (theta-trap /
  single-regime / over-constraint). The ONE win the campaign produced was
  SUBTRACTIVE (skip the worst VIX tercile on vwap entries) and the proven live
  edge (vwap_continuation) is STRUCTURAL: ONE causal with-trend entry/day. So the
  edge improves by SUBTRACTION (skip bad conditions) and by mimicking vwap's
  STRUCTURAL shape, NOT by stacking confirmations.

THE NEW STRUCTURAL DETECTOR — "failed counter-trend move" (one entry/day):
  1. Morning trend side: the first TREND_BARS (3) RTH closes are all on the SAME
     side of the as-of session VWAP -> that is the day's WITH-TREND direction
     (closes>VWAP -> bullish/CALL; closes<VWAP -> bearish/PUT). Identical trend
     definition to the validated vwap_continuation detector (no drift).
  2. COUNTER-TREND BREAK: after the trend bars, price breaks session VWAP AGAINST
     the morning trend (a bar CLOSES on the wrong side of VWAP) — the
     "counter-trend move" begins.
  3. FAILS + RECLAIMS: a later bar (<= ENTRY_CUTOFF) CLOSES back across VWAP in the
     ORIGINAL trend direction -> the counter-trend move failed and price reclaimed
     VWAP with-trend. THAT reclaim bar is the entry (one causal entry/day, side =
     the morning trend side). Fill = NEXT bar open (sim handles it). No look-ahead:
     every read (VWAP as-of, trend side, break, reclaim) uses only bars[0..j].
  Chart stop = the counter-trend excursion extreme (for a CALL: the LOW printed
  during the failed break = the level that must hold; for a PUT: the HIGH). This is
  the structural invalidation of the "failed counter-trend move" thesis: if price
  takes out the failed-break extreme, the read was wrong.

  This is DISTINCT from vwap_continuation: vwap_cont enters the FIRST with-trend
  continuation (breakout/shallow-dip) with NO requirement that price ever crossed
  VWAP against the trend. struct_vwap_reclaim REQUIRES a completed counter-trend
  VWAP break THEN a with-trend reclaim — the "failed counter-trend move" shape.

REAL FILLS (C1): lib.simulator_real.simulate_trade_real on real OPRA bars
  (nearest-cached strike snap <=4, causal next-bar-open entry, chart-stop via
  rejection_level). Survivor structure strike_offset=-2 (ITM-2) PRIMARY; also
  report strike_offset=+2 (OTM-2 = Safe-2's actual $2K tier) per C29 (gates do not
  transfer across strike tiers).

ALL 8 GATES MANDATORY (anti-cherry-pick 2.10; reported for BOTH strike tiers):
  G1 OOS(2026) per-trade > 0
  G2 positive_quarters >= 4/6
  G3 top5_day_pct < 200
  G4 n_trades >= 20
  G5 drop-top5-day per-trade > 0          (concentration robustness)
  G6 IS(2025) FIRST-HALF per-trade > 0    (in-sample stability, not just full IS)
  G7 beats random-entry null (L172: ~20 seeds, same days/sides) -- here we use the
     STANDARD coin-flip null (autoresearch.null_baseline) AND a same-day/same-side
     null (the harder control): the SIGNAL must beat the null, not the bracket.
  G8 no-truncation (L171): per-trade SIGN holds from -8% stop -> chart-stop-only
     (-0.99). Sign inversion = pure stop-truncation of a SPY-price tilt, not a
     per-trade option edge (truncation_guard).

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/sub-struct_vwap_reclaim_failed_break.json.

Run: backtest/.venv/Scripts/python.exe \
       backtest/autoresearch/_sub_struct_vwap_reclaim_failed_break.py
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

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    session_vwap_asof,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
# Reuse the edgehunt data normalizers so the bar series is byte-for-byte identical.
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sub-struct_vwap_reclaim_failed_break.json"

# ── Config ──────────────────────────────────────────────────────────────────
PRIMARY_STRIKE_OFFSET = -2     # ITM-2 (survivor structure)  -- PRIMARY
SAFE2_STRIKE_OFFSET = +2       # OTM-2 (Safe-2's actual $2K tier) -- reported per C29
SURV_PREMIUM_STOP = -0.08      # -8% premium stop
CHART_STOP_ONLY = -0.99        # for the no-truncation fraud gate (G8)

N_NULL_SEEDS = 20              # L172
RTH_OPEN = dt.time(9, 30)


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL DETECTOR — VWAP-reclaim-after-failed-break (one causal entry/day)
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side(closes, vwap, n) -> Optional[str]:
    """Day's with-trend side: first n RTH closes all same side of as-of VWAP.

    Identical to the validated vwap_continuation trend definition (no drift)."""
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def detect_signals(days: list[DayCtx]) -> list[Signal]:
    """One causal struct_vwap_reclaim_failed_break entry/day.

    Sequence (all reads causal, bars[0..j] only):
      trend side (TREND_BARS) -> counter-trend VWAP break (close wrong side)
      -> with-trend VWAP reclaim (close back across) BEFORE ENTRY_CUTOFF -> entry.
    Stop = the failed-break excursion extreme (the structural invalidation).
    """
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 3:
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

        broke = False                 # has the counter-trend VWAP break happened yet?
        excursion_ext: Optional[float] = None  # extreme during the failed break (the stop)
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            c = closes[j]
            if side == "C":
                # Phase 2: counter-trend break = close BELOW VWAP (against bullish trend)
                if not broke:
                    if c < v:
                        broke = True
                        excursion_ext = lows[j]
                    continue
                # During the failed break, track the deepest LOW (the level that must hold)
                excursion_ext = min(excursion_ext, lows[j]) if excursion_ext is not None else lows[j]
                # Phase 3: reclaim = close BACK ABOVE VWAP in the trend direction -> entry
                if c > v:
                    stop = float(excursion_ext)
                    out.append(Signal(bar_idx=int(idxs[j]), side="C", stop_level=stop,
                                      note="struct_vwap_reclaim"))
                    break
            else:
                # Phase 2: counter-trend break = close ABOVE VWAP (against bearish trend)
                if not broke:
                    if c > v:
                        broke = True
                        excursion_ext = highs[j]
                    continue
                excursion_ext = max(excursion_ext, highs[j]) if excursion_ext is not None else highs[j]
                # Phase 3: reclaim = close BACK BELOW VWAP -> entry
                if c < v:
                    stop = float(excursion_ext)
                    out.append(Signal(bar_idx=int(idxs[j]), side="P", stop_level=stop,
                                      note="struct_vwap_reclaim"))
                    break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set on real OPRA fills (v15 default exits)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct
                 ) -> tuple[list[TradeRow], dict]:
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
            qty=QTY, setup="STRUCT_VWAP_RECLAIM", strike_override=strike, entry_vix=entry_vix,
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
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_topN_day_per_trade(rows: list[TradeRow], k: int = 5) -> Optional[float]:
    """Per-trade mean after removing the k highest-P&L DAYS entirely."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _top5_day_total_pct_of_total(rows: list[TradeRow]) -> Optional[float]:
    """Top-5 winning DAYS' P&L as % of total (the published top5_day_pct concept)."""
    return _by_day_top5_pct(rows)


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    # IS FIRST-HALF (G6): split the IS (2025) rows chronologically in half, require
    # the first half to be per-trade positive (a stricter in-sample-stability gate
    # than full-IS-positive — L166 sub-window sign stability).
    is_sorted = sorted(is_rows, key=lambda r: r.date)
    half = len(is_sorted) // 2
    is_first_half = is_sorted[:half] if half else []

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

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_n": len(is_first_half), "is_first_half_exp": _exp(is_first_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_total_pct_of_total(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# G7 — same-day/same-side random null (the HARD control: isolates trigger TIMING
# from day+side selection). Pick a RANDOM eligible morning bar on the same day,
# same side, same stop geometry, and simulate. Reported alongside the STANDARD
# coin-flip null (null_baseline) which randomizes the entry bar across all RTH.
# ─────────────────────────────────────────────────────────────────────────────
def sameday_null(signals, spy, ribbon, vix, days, *, seeds, strike_offset,
                 premium_stop_pct) -> dict:
    day_bars: dict[dt.date, list[int]] = {}
    for dc in days:
        rth = dc.rth
        times = rth["t"].values
        idxs = rth.index.tolist()
        elig = [int(idxs[j]) for j in range(TREND_BARS, len(rth)) if times[j] <= ENTRY_CUTOFF]
        if elig:
            day_bars[dc.date] = elig
    sig_specs = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        sig_specs.append((d, sg.side, sg.stop_level))
    per_seed_exp, per_seed_oos_exp = [], []
    for seed in range(seeds):
        rng = np.random.default_rng(7000 + seed)
        rand_sigs = []
        for d, sd, stop in sig_specs:
            elig = day_bars.get(d)
            if not elig:
                continue
            bidx = int(rng.choice(elig))
            rand_sigs.append(Signal(bar_idx=bidx, side=sd, stop_level=stop, note="rand"))
        rows, _ = simulate_set(rand_sigs, spy, ribbon, vix, strike_offset=strike_offset,
                               premium_stop_pct=premium_stop_pct)
        if rows:
            m = metrics(rows)
            per_seed_exp.append(m["exp_dollar"])
            per_seed_oos_exp.append(m["oos_exp"])
    if not per_seed_exp:
        return {"seeds": 0}
    return {
        "seeds": len(per_seed_exp),
        "null_exp_mean": round(float(np.mean(per_seed_exp)), 2),
        "null_exp_min": round(float(np.min(per_seed_exp)), 2),
        "null_exp_max": round(float(np.max(per_seed_exp)), 2),
        "null_exp_std": round(float(np.std(per_seed_exp)), 2),
        "null_oos_exp_mean": round(float(np.mean(per_seed_oos_exp)), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate one strike tier: all 8 gates
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_tier(signals, spy, ribbon, vix, days, *, strike_offset, tier_label) -> dict:
    rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                             premium_stop_pct=SURV_PREMIUM_STOP)
    m = metrics(rows)
    if not m.get("n"):
        return {"tier": tier_label, "strike_offset": strike_offset, "coverage": cov,
                "metrics": m, "gates": {}, "clears_all_gates": False,
                "note": "no filled trades"}

    # G8 no-truncation: same signals at chart-stop-only
    cs_rows, _ = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                              premium_stop_pct=CHART_STOP_ONLY)
    cs_m = metrics(cs_rows)
    trunc_artifact = is_truncation_artifact(
        best_per_trade=m["exp_dollar"],
        chart_stop_only_per_trade=cs_m.get("exp_dollar"),
        best_premium_stop_pct=SURV_PREMIUM_STOP,
    )
    # sign must HOLD (full + OOS) from -8% -> chart-stop-only
    sign_stable_full = bool(cs_m.get("n") and (m["exp_dollar"] > 0) == (cs_m["exp_dollar"] > 0))
    sign_stable_oos = bool(cs_m.get("oos_n") and (m.get("oos_exp", 0) > 0) == (cs_m.get("oos_exp", 0) > 0))
    truncation_safe = bool((not trunc_artifact) and sign_stable_full and sign_stable_oos)

    # G7 nulls
    # Build a single RTH frame (reset index) for the STANDARD coin-flip null.
    rth_all = pd.concat([dc.rth for dc in days]).sort_index().reset_index(drop=True)
    n_call = sum(1 for s in signals if s.side == "C")
    n_put = sum(1 for s in signals if s.side == "P")
    coin = random_entry_null(
        rth_all, n_signals=len(signals), n_call=n_call, n_put=n_put,
        strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP, seeds=N_NULL_SEEDS)
    coin_g = null_gate(m["exp_dollar"], m.get("drop_top5_day_per_trade"), coin)
    sameday = sameday_null(signals, spy, ribbon, vix, days, seeds=N_NULL_SEEDS,
                           strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    # same-day null: signal must beat null MEAN+1std (a real margin over day+side selection)
    beats_sameday = bool(
        sameday.get("seeds") and
        m["exp_dollar"] > sameday["null_exp_mean"] + sameday.get("null_exp_std", 0.0))
    oos_beats_sameday = bool(
        sameday.get("seeds") and (m.get("oos_exp", 0) or 0) > sameday.get("null_oos_exp_mean", 9e9))
    # G7 verdict: must beat the STANDARD coin-flip null (null_pass) AND the harder
    # same-day/same-side null mean+std. (Reporting both; require both.)
    beats_null = bool(coin_g["null_pass"] and beats_sameday)

    gates = {
        "G1_oos_per_trade_positive": {"pass": bool(m.get("oos_exp", -1) > 0),
                                      "value": m.get("oos_exp"), "oos_n": m.get("oos_n")},
        "G2_positive_quarters_ge_4": {"pass": bool(m.get("positive_quarters_n", 0) >= 4),
                                      "value": m.get("positive_quarters")},
        "G3_top5_day_pct_lt_200": {"pass": bool(m.get("top5_day_pct") is not None
                                                and m["top5_day_pct"] < 200.0),
                                   "value": m.get("top5_day_pct")},
        "G4_n_ge_20": {"pass": bool(m.get("n", 0) >= 20), "value": m.get("n")},
        "G5_drop_top5_per_trade_positive": {"pass": bool(m.get("drop_top5_day_per_trade") is not None
                                                         and m["drop_top5_day_per_trade"] > 0),
                                            "value": m.get("drop_top5_day_per_trade")},
        "G6_is_first_half_positive": {"pass": bool(m.get("is_first_half_exp", -1) > 0
                                                   and m.get("is_first_half_n", 0) > 0),
                                      "value": m.get("is_first_half_exp"),
                                      "is_first_half_n": m.get("is_first_half_n")},
        "G7_beats_random_null": {
            "pass": beats_null,
            "coinflip_null": {**coin, **coin_g},
            "sameday_null": {**sameday, "beats_sameday_mean_plus_std": beats_sameday,
                             "oos_beats_sameday_mean": oos_beats_sameday},
        },
        "G8_no_truncation": {
            "pass": truncation_safe,
            "stop8_exp": m["exp_dollar"], "chartstop_exp": cs_m.get("exp_dollar"),
            "stop8_oos_exp": m.get("oos_exp"), "chartstop_oos_exp": cs_m.get("oos_exp"),
            "stop8_total": m["total_dollar"], "chartstop_total": cs_m.get("total_dollar"),
            "is_truncation_artifact": trunc_artifact,
            "sign_stable_full": sign_stable_full, "sign_stable_oos": sign_stable_oos,
        },
    }
    clears_all = all(g["pass"] for g in gates.values())
    # HONEST caveat (not a hard gate): if the signal beats the same-day null on the
    # FULL sample but NOT on the OOS slice, the OOS lift sits inside the same-day
    # null band -> the OOS edge is mostly DAY+SIDE selection (picking the right
    # trend days/sides), not reclaim-trigger PRECISION. Surfaced, not hidden.
    caveats = []
    if clears_all and not oos_beats_sameday:
        caveats.append("oos_lift_within_sameday_null_band: OOS per-trade is below the same-day "
                       "random-entry null OOS mean -> the OOS edge is largely day+side selection, "
                       "not trigger precision (the trigger DOES beat the full-sample null and the "
                       "coin-flip null; full-sample clears every gate).")
    return {
        "tier": tier_label,
        "strike_offset": strike_offset,
        "strike_tier_name": (f"ITM{abs(strike_offset)}" if strike_offset < 0
                             else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}")),
        "coverage": cov,
        "metrics": m,
        "gates": gates,
        "clears_all_gates": clears_all,
        "n_gates_passed": sum(1 for g in gates.values() if g["pass"]),
        "caveats": caveats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[sub-struct-vwap-reclaim] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sub] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[sub] struct_vwap_reclaim signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    tiers = {}
    for off, lbl in ((PRIMARY_STRIKE_OFFSET, "ITM2_primary"), (SAFE2_STRIKE_OFFSET, "OTM2_safe2")):
        blk = evaluate_tier(signals, spy, ribbon, vix, days,
                            strike_offset=off, tier_label=lbl)
        tiers[lbl] = blk
        m = blk.get("metrics", {})
        print(f"\n[{lbl} off={off:+d} {blk.get('strike_tier_name')}] "
              f"n={m.get('n')} exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} "
              f"(oos_n={m.get('oos_n')}) posQ={m.get('positive_quarters')} "
              f"top5%={m.get('top5_day_pct')} droptop5=${m.get('drop_top5_day_per_trade')} "
              f"isH1=${m.get('is_first_half_exp')}", flush=True)
        for gname, g in blk.get("gates", {}).items():
            print(f"    {gname}: {'PASS' if g['pass'] else 'FAIL'} "
                  f"(value={g.get('value', '-')})", flush=True)
        print(f"    => clears_all_gates={blk.get('clears_all_gates')} "
              f"({blk.get('n_gates_passed')}/8)", flush=True)

    primary = tiers["ITM2_primary"]
    pm = primary.get("metrics", {})
    pg = primary.get("gates", {})

    # Schema-shaped fields for the StructuredOutput return (primary = ITM-2)
    coin = pg.get("G7_beats_random_null", {}).get("coinflip_null", {})
    beats_null = bool(pg.get("G7_beats_random_null", {}).get("pass"))
    truncation_safe = bool(pg.get("G8_no_truncation", {}).get("pass"))
    is_half_positive = bool(pg.get("G6_is_first_half_positive", {}).get("pass"))
    clears_all = bool(primary.get("clears_all_gates"))
    primary_caveats = primary.get("caveats", [])
    if clears_all:
        verdict = "PROMOTABLE — clears all 8 gates on ITM-2 real fills"
        if primary_caveats:
            verdict += (" (CAVEAT: OOS per-trade sits inside the same-day random-entry null band "
                        "-> OOS edge is largely day+side selection, not trigger precision; "
                        "still clears the coin-flip null and every coded gate full-sample)")
    else:
        verdict = "REJECTED — fails one or more of the 8 mandatory gates (see gates block)"

    summary = {
        "hypothesis": ("struct_vwap_reclaim_failed_break: morning-trend VWAP-reclaim after a "
                       "FAILED counter-trend VWAP break -> one causal with-trend entry/day "
                       "(the 'failed counter-trend move' shape). SUBTRACTIVE/STRUCTURAL-mimic "
                       "of vwap_continuation, NOT additive confluence."),
        "kind": "structural_one_entry_per_day",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "opra_fill_cutoff": "2026-05-29 (signals after drop as cache_miss; OOS fills = Jan..May 2026)",
        "detector": ("clean causal one-entry/day: trend side (first 3 RTH closes same side of "
                     "as-of session VWAP) -> counter-trend VWAP break (close wrong side) -> "
                     "with-trend VWAP reclaim (close back across) <=10:30 ET; entry=reclaim bar, "
                     "fill=next bar open; chart stop = failed-break excursion extreme. "
                     "DISTINCT from vwap_continuation (requires a completed+failed counter move)."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "primary_strike_offset": PRIMARY_STRIKE_OFFSET,
                   "secondary_strike_offset": SAFE2_STRIKE_OFFSET},
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "eight_gates": {
            "G1": "OOS(2026) per-trade > 0",
            "G2": "positive_quarters >= 4/6",
            "G3": "top5_day_pct < 200",
            "G4": "n_trades >= 20",
            "G5": "drop-top5-day per-trade > 0",
            "G6": "IS(2025) first-half per-trade > 0",
            "G7": "beats random-entry null (coin-flip null_pass AND same-day mean+std, ~20 seeds)",
            "G8": "no-truncation: sign holds -8% -> chart-stop-only (-0.99)",
        },
        "tiers": tiers,
        "PRIMARY_TIER": "ITM2_primary",
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 gates reported for BOTH strike tiers (ITM-2 primary + "
                               "OTM-2 Safe-2); a tier that fails any gate is marked "
                               "clears_all_gates=false (anti-pattern 2.10)."),
            "structural_not_additive": ("ONE causal entry/day with a structural chart stop; no "
                                        "stacked confirmations (the campaign proved additive "
                                        "confluence is dead on 0DTE)."),
            "strike_tier_caveat": "C29 — gates do not transfer across strike tiers; reported per tier.",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "fraud_gates": ("G7 random-entry null (coin-flip + same-day/same-side, 20 seeds) + "
                            "G8 no-truncation (sign must hold -8% -> chart-stop-only)."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sub] wrote {OUT}", flush=True)

    print("\n=== STRUCT_VWAP_RECLAIM_FAILED_BREAK VERDICT (PRIMARY ITM-2) ===")
    print(f"n_signals={len(signals)}  fired {summary['signal_fire_day_pct']}% of {n_days} days")
    print(f"ITM-2: n={pm.get('n')} exp=${pm.get('exp_dollar')} oos_exp=${pm.get('oos_exp')} "
          f"posQ={pm.get('positive_quarters')} top5%={pm.get('top5_day_pct')}")
    print(f"clears_all_gates={clears_all}  beats_null={beats_null}  "
          f"truncation_safe={truncation_safe}  is_half_positive={is_half_positive}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
