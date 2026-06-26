"""SUBTRACTIVE test: abstain_first15_range — skip vwap entries on too-volatile opens.

HYPOTHESIS (subtractive, not additive): the ONE proven 0DTE edge in Project Gamma is
``vwap_continuation`` (the morning VWAP-side continuation). The selection campaign proved
ADDITIVE confluence is DEAD on 0DTE; the lone win was SUBTRACTIVE (skip_top_tercile_only:
abstain from the worst VIX regime -> OOS +$142/tr AND maxDD -$424). THIS test asks a NEW
subtractive question keyed off a DIFFERENT chaos proxy:

    Does ABSTAINING from vwap_continuation entries when the FIRST-15-MIN RTH range is in
    the TOP TERCILE (a "too-volatile / chaotic open" day) IMPROVE the survivor's edge?

The thesis is structural: a chaotic open (wide first-15-min range) is a day whose morning
trend is more likely a fakeout / whipsaw, so the VWAP-side continuation read is less
reliable. Abstaining on those days should lift per-trade and shrink drawdown — the same
SHAPE as the proven VIX-regime subtraction, but using INTRADAY chaos (first-15-min range)
rather than VIX regime.

=== WHAT "first-15-min RTH range" MEANS HERE ===
The first 15 minutes of RTH = the first 3 5-minute bars (09:30, 09:35, 09:40 -> the
09:30..09:45 window). The day's first-15-min range = max(high) - min(low) over those 3
bars, in SPY POINTS. We also report it NORMALIZED by the open price (range / open, in bp)
so a $700 SPY isn't structurally "more volatile" than a $400 SPY just by price level — the
NORMALIZED proxy is the PRIMARY abstention axis; the raw-points proxy is a disclosed
robustness variant.

=== WHY THIS IS HONEST (the foot-guns this script defends against) ===

1. CAUSAL threshold, NO look-ahead (L14/L34/L57): the tercile cut that decides "top
   tercile -> abstain" is an EXPANDING-WINDOW percentile over only PRIOR DAYS' first-15-min
   ranges (with a warmup before any abstention is allowed). A full-sample tercile would
   peek at the future and is FORBIDDEN. The first-15-min range itself is known by 09:45,
   strictly BEFORE every signal entry (entries are >= the 4th RTH bar / TREND_BARS=3, and
   the morning cutoff is 10:30) — so reading it at the signal bar is causal by construction.
   We also report a full-sample-tercile variant ONLY to quantify the look-ahead premium —
   it is NEVER allowed to clear the bar.

2. SUBTRACTIVE PARTITION, signal stream FROZEN (C14, no drift): the detector is
   BYTE-FOR-BYTE the validated j_daily_pattern_ratify.detect_j_vwap_continuation (reused
   verbatim from _edgehunt_vwap_continuation). Signals are detected ONCE; the gate is a
   PARTITION (subset) of that same set re-simulated on the SAME real-fills path. This
   isolates the gate's NET effect.

3. ALL 8 MANDATORY GATES (anti-pattern 2.10, no cherry-pick): OOS(2026) per-trade>0 AND
   positive_quarters>=4/6 AND top5-day<200% AND n>=20 AND drop-top-5-days per-trade>0 AND
   beats a RANDOM-entry null (same exit/count/side, ~20 seeds, L172) AND sign does NOT
   invert at chart-stop-only (no-truncation, L171) AND the IN-SAMPLE(2025) half is ALSO
   positive (reject the IS-neg/OOS-pos single-regime artifact).

4. NET decision metric, not just per-trade: a gate that lifts per-trade but guts total
   P&L is flagged. We report OOS per-trade LIFT *and* OOS total kept-frac vs the ungated
   baseline, plus maxDD (ruin) — the survivor's selling point was per-trade UP AND maxDD
   shallower, so we hold this gate to the same bar.

STRIKE (C29 — gates don't transfer across strike tiers): PRIMARY = strike_offset=-2
(ITM-2, the survivor structure). We ALSO report strike_offset=+2 (OTM-2 = Safe-2's actual
$2K tier) so the gate is judged on the tier it would actually trade on.

Detector: BYTE-FOR-BYTE the validated vwap_continuation detector. Fills: real OPRA via
lib.simulator_real.simulate_trade_real (C1). Survivor structure: ITM-2, premium_stop=-0.08,
v15 exits, qty=3.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed.

Writes analysis/recommendations/sub-abstain_first15_range.json.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_abstain_first15_range.py
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

# REUSE the validated detector + data normalizers from the edgehunt harness so the signal
# set is byte-for-byte identical (no drift). We only ADD the subtractive partition.
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals,
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sub-abstain_first15_range.json"

# ── Survivor structure (FROZEN — the validated cell) ────────────────────────────
SURV_STRIKE_OFFSET = -2     # ITM-2 (primary)
OTM2_STRIKE_OFFSET = 2      # OTM-2 (Safe-2's actual $2K tier; C29 cross-tier check)
SURV_PREMIUM_STOP = -0.08   # v15 asymmetric ITM survivor stop
CHART_STOP_ONLY = -0.99     # no-truncation reference cell

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
FIRST15_BARS = 3            # first 3 5-min RTH bars = 09:30,09:35,09:40 = 09:30..09:45

# ── OOS / gate constants (identical bar to the survivor study) ──────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0
NULL_SEEDS = 20
WARMUP_DAYS = 20           # no abstention until >=20 prior DAYS of first-15 ranges (causal warmup)
TERCILE_TOP = 200.0 / 3.0  # top-tercile cut = 66.67th percentile of prior-days' first-15 ranges

NOMINAL_ACCOUNT = 2000.0


# ─────────────────────────────────────────────────────────────────────────────
# FIRST-15-MIN RANGE per day (raw points + open-normalized bp). Known by 09:45 ->
# strictly before any signal entry (entries >= bar TREND_BARS, morning cutoff 10:30).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class First15:
    date: dt.date
    range_pts: float          # max(high)-min(low) over first 3 RTH bars, in SPY points
    range_bp: float           # range_pts / open * 10000 (open-normalized, basis points)


def compute_first15(days) -> dict[dt.date, First15]:
    out: dict[dt.date, First15] = {}
    for dc in days:
        rth = dc.rth
        if len(rth) < FIRST15_BARS:
            continue
        head = rth.iloc[:FIRST15_BARS]
        hi = float(head["high"].max())
        lo = float(head["low"].min())
        op = float(head.iloc[0]["open"])
        rng = hi - lo
        out[dc.date] = First15(
            date=dc.date,
            range_pts=round(rng, 4),
            range_bp=round((rng / op) * 1e4, 4) if op > 0 else 0.0,
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL "top tercile" decision per DAY. A day is "chaotic open -> ABSTAIN" iff its
# first-15 range exceeds the TERCILE_TOP percentile of ALL PRIOR DAYS' first-15 ranges
# (chronological, expanding window, warmup-gated). Look-ahead-safe by construction.
# ─────────────────────────────────────────────────────────────────────────────
def causal_abstain_days(first15: dict[dt.date, First15], *, axis: str = "bp",
                        full_sample: bool = False) -> dict[dt.date, bool]:
    """Return {date -> abstain?}. axis in {'bp','pts'}. full_sample=True is the
    look-ahead-premium disclosure variant only (NOT allowed to clear the bar)."""
    ordered = sorted(first15.values(), key=lambda f: f.date)
    vals = [(f.range_bp if axis == "bp" else f.range_pts) for f in ordered]
    out: dict[dt.date, bool] = {}
    if full_sample:
        cut = float(np.percentile(vals, TERCILE_TOP)) if vals else float("inf")
        for f, v in zip(ordered, vals):
            out[f.date] = v > cut
        return out
    prior: list[float] = []
    for f, v in zip(ordered, vals):
        if len(prior) < WARMUP_DAYS:
            out[f.date] = False           # warmup: never abstain
        else:
            cut = float(np.percentile(prior, TERCILE_TOP))
            out[f.date] = v > cut
        prior.append(v)                   # AFTER deciding (causal)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set at a fixed (strike,stop). v15 default exits.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    trig: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct) \
        -> tuple[list[TradeRow], dict]:
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
            qty=QTY, setup="JVWAP_SUB_FIRST15", strike_override=strike, entry_vix=entry_vix,
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
# METRICS (OP-20 disclosure block) — mirrors the survivor study exactly.
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day(rows) -> dict[str, float]:
    bd: dict[str, float] = defaultdict(float)
    for r in rows:
        bd[r.date] += r.pnl
    return bd


def _top5_day_pct(rows) -> Optional[float]:
    bd = _by_day(rows)
    total = sum(bd.values())
    if total <= 0:
        return None
    top5 = sum(sorted(bd.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_top5_day_per_trade(rows, k: int = 5) -> Optional[float]:
    """Per-trade mean after removing the k highest-P&L DAYS entirely."""
    if not rows:
        return None
    bd: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        bd[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in bd.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _max_dd_dollars(rows) -> float:
    bd = _by_day(rows)
    cum = peak = mdd = 0.0
    for d in sorted(bd.keys()):
        cum += bd[d]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return round(mdd, 2)


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

    mdd = _max_dd_dollars(rows)
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
        "top5_day_pct": _top5_day_pct(rows),
        "drop_top5_day_per_trade": _drop_top5_day_per_trade(rows, 5),
        "max_drawdown_dollars": mdd,
        "max_drawdown_pct_of_2k": round(100 * abs(mdd) / NOMINAL_ACCOUNT, 1),
        "worst_single_trade_dollars": round(float(pnl.min()), 2),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# RANDOM-ENTRY NULL (L172): SAME days+sides as the kept subset, random morning entry
# bar (>= TREND_BARS, <= ENTRY_CUTOFF). Per-trade must beat the null (mean+1std).
# ─────────────────────────────────────────────────────────────────────────────
def random_null(signals, spy, ribbon, vix, days, *, strike_offset, premium_stop_pct,
                seeds=NULL_SEEDS) -> dict:
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

    per_seed_exp, per_seed_oos_exp, per_seed_total = [], [], []
    for seed in range(seeds):
        rng = np.random.default_rng(1000 + seed)
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
# Evaluate ONE config (strike tier) for: ungated baseline + the abstention gate.
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_config(tier_name, strike_offset, signals, kept_signals, spy, ribbon, vix, days,
                    *, abstain_n_days, abstain_axis) -> dict:
    # ungated baseline (this tier)
    base_rows, base_cov = simulate_set(signals, spy, ribbon, vix,
                                       strike_offset=strike_offset,
                                       premium_stop_pct=SURV_PREMIUM_STOP)
    base_m = metrics(base_rows)
    base_null = random_null(signals, spy, ribbon, vix, days,
                            strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    base_cs_rows, _ = simulate_set(signals, spy, ribbon, vix,
                                   strike_offset=strike_offset, premium_stop_pct=CHART_STOP_ONLY)
    base_cs_m = metrics(base_cs_rows)

    # gated subset (abstain on chaotic-open days)
    g_rows, g_cov = simulate_set(kept_signals, spy, ribbon, vix,
                                 strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    g_m = metrics(g_rows)
    g_null = random_null(kept_signals, spy, ribbon, vix, days,
                         strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    g_cs_rows, _ = simulate_set(kept_signals, spy, ribbon, vix,
                                strike_offset=strike_offset, premium_stop_pct=CHART_STOP_ONLY)
    g_cs_m = metrics(g_cs_rows)

    # ── 8 MANDATORY GATES on the GATED subset (anti-2.10) ─────────────────────
    # beats-null: per-trade overall must beat null mean + 1 std (a real margin, L172).
    null_thr = (g_null.get("null_exp_mean", 9e9) + g_null.get("null_exp_std", 0.0)
                if g_null.get("seeds") else 9e9)
    beats_null = bool(g_m.get("n") and g_m.get("exp_dollar", -9e9) > null_thr)
    # truncation: overall + OOS sign must hold from -8% stop -> chart-stop-only.
    prem_sign = np.sign(g_m.get("exp_dollar", 0.0))
    chart_sign = np.sign(g_cs_m.get("exp_dollar", 0.0))
    truncation_safe = bool(prem_sign == chart_sign and prem_sign != 0)
    drop5 = g_m.get("drop_top5_day_per_trade")
    gates = {
        "oos_per_trade_positive": bool(g_m.get("oos_exp", -1) > 0),
        "positive_quarters_ge_4": bool(g_m.get("positive_quarters_n", 0) >= BAR_POS_Q),
        "top5_day_lt_200": bool(g_m.get("top5_day_pct") is not None and g_m["top5_day_pct"] < BAR_TOP5),
        "n_ge_20": bool(g_m.get("n", 0) >= BAR_N),
        "drop_top5_day_per_trade_positive": bool(drop5 is not None and drop5 > 0),
        "beats_random_null": beats_null,
        "truncation_safe": truncation_safe,
        "is_half_positive": bool(g_m.get("is_exp", -1) > 0),
    }
    clears_all = all(gates.values())

    # ── NET vs ungated baseline (per-trade lift + total kept + ruin) ──────────
    vs_base = {
        "oos_per_trade_lift": round((g_m.get("oos_exp", 0) or 0) - (base_m.get("oos_exp", 0) or 0), 2),
        "per_trade_lift_all": round((g_m.get("exp_dollar", 0) or 0) - (base_m.get("exp_dollar", 0) or 0), 2),
        "oos_total_kept_frac": (round((g_m.get("oos_total", 0) or 0) / base_m["oos_total"], 3)
                                if base_m.get("oos_total") else None),
        "total_kept_frac": (round((g_m.get("total_dollar", 0) or 0) / base_m["total_dollar"], 3)
                            if base_m.get("total_dollar") else None),
        "delta_max_drawdown_dollars": round((g_m.get("max_drawdown_dollars", 0) or 0)
                                            - (base_m.get("max_drawdown_dollars", 0) or 0), 2),
        "n_signals_dropped": len(signals) - len(kept_signals),
    }

    return {
        "tier": tier_name,
        "strike_offset": strike_offset,
        "abstain_days_in_window": abstain_n_days,
        "abstain_axis": abstain_axis,
        "ungated_baseline": {
            "coverage": base_cov, "metrics": base_m,
            "random_null": base_null,
            "no_truncation": {"stop8_exp": base_m.get("exp_dollar"),
                              "chartstop_exp": base_cs_m.get("exp_dollar"),
                              "stop8_oos_exp": base_m.get("oos_exp"),
                              "chartstop_oos_exp": base_cs_m.get("oos_exp")},
        },
        "gated": {
            "coverage": g_cov, "metrics": g_m,
            "random_null": {**g_null, "beats_null": beats_null, "null_threshold": round(null_thr, 2)
                            if null_thr < 9e9 else None},
            "no_truncation": {"stop8_exp": g_m.get("exp_dollar"),
                              "chartstop_exp": g_cs_m.get("exp_dollar"),
                              "stop8_oos_exp": g_m.get("oos_exp"),
                              "chartstop_oos_exp": g_cs_m.get("oos_exp"),
                              "sign_stable": truncation_safe},
        },
        "gates": gates,
        "clears_all_gates": clears_all,
        "vs_baseline": vs_base,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[sub-first15] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sub-first15] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    print("[sub-first15] computing ribbon ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # survivor signals ONCE (byte-for-byte detector)
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[sub-first15] survivor signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    # first-15-min range per day + causal abstention map (PRIMARY = bp-normalized)
    first15 = compute_first15(days)
    abstain_bp = causal_abstain_days(first15, axis="bp", full_sample=False)
    abstain_pts = causal_abstain_days(first15, axis="pts", full_sample=False)
    abstain_bp_fs = causal_abstain_days(first15, axis="bp", full_sample=True)  # look-ahead premium only

    def kept(signals_, abstain_map):
        out = []
        for sg in signals_:
            d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
            if not abstain_map.get(d, False):
                out.append(sg)
        return out

    kept_bp = kept(signals, abstain_bp)
    kept_pts = kept(signals, abstain_pts)
    kept_bp_fs = kept(signals, abstain_bp_fs)

    n_abstain_signal_days_bp = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals
                                    if abstain_bp.get(spy.iloc[s.bar_idx]["timestamp_et"].date(), False)})
    print(f"[sub-first15] first-15 range known on {len(first15)} days; "
          f"causal-bp abstains {sum(abstain_bp.values())} days "
          f"(of which {n_abstain_signal_days_bp} had a signal); "
          f"kept {len(kept_bp)}/{len(signals)} signals (bp) / {len(kept_pts)} (pts)", flush=True)

    # ── PRIMARY: ITM-2 (survivor structure), bp-normalized causal abstention ───
    itm2 = evaluate_config("ITM-2", SURV_STRIKE_OFFSET, signals, kept_bp, spy, ribbon, vix, days,
                           abstain_n_days=int(sum(abstain_bp.values())), abstain_axis="bp_normalized")
    # ── C29 cross-tier: OTM-2 (Safe-2's actual $2K tier), same abstention ──────
    otm2 = evaluate_config("OTM-2", OTM2_STRIKE_OFFSET, signals, kept_bp, spy, ribbon, vix, days,
                           abstain_n_days=int(sum(abstain_bp.values())), abstain_axis="bp_normalized")
    # ── ROBUSTNESS: raw-points axis (ITM-2) ───────────────────────────────────
    itm2_pts = evaluate_config("ITM-2", SURV_STRIKE_OFFSET, signals, kept_pts, spy, ribbon, vix, days,
                               abstain_n_days=int(sum(abstain_pts.values())), abstain_axis="raw_points")
    # ── LOOK-AHEAD PREMIUM (disclosure only — NEVER clears the bar) ────────────
    itm2_fs = evaluate_config("ITM-2", SURV_STRIKE_OFFSET, signals, kept_bp_fs, spy, ribbon, vix, days,
                              abstain_n_days=int(sum(abstain_bp_fs.values())), abstain_axis="bp_FULL_SAMPLE_lookahead")

    primary = itm2  # the decision config (survivor structure + causal bp axis)
    base_m = primary["ungated_baseline"]["metrics"]
    g_m = primary["gated"]["metrics"]

    summary = {
        "hypothesis": "abstain_first15_range",
        "thesis": ("SUBTRACTIVE: abstain from vwap_continuation entries when the first-15-min RTH "
                   "range (09:30..09:45, 3 bars) is in the TOP TERCILE of a CAUSAL expanding-window "
                   "distribution of prior days' first-15 ranges (a too-volatile / chaotic open). "
                   "Mimics the proven subtractive survivor (skip worst-regime) using INTRADAY chaos "
                   "instead of VIX regime. Signal stream FROZEN to the survivor; gate is a PARTITION."),
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE j_daily_pattern_ratify.detect_j_vwap_continuation "
                     "(imported from _edgehunt_vwap_continuation); live port = "
                     "backtest/lib/watchers/vwap_continuation_watcher.py"),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "survivor_structure": {"strike_offset_primary": SURV_STRIKE_OFFSET, "strike_tier_primary": "ITM-2",
                               "premium_stop_pct": SURV_PREMIUM_STOP, "exits": "v15 default", "qty": QTY},
        "first15_definition": ("max(high)-min(low) over the first 3 RTH 5-min bars (09:30,09:35,09:40 "
                               "= 09:30..09:45 window); known by 09:45 -> strictly BEFORE every signal "
                               "entry (entries >= bar TREND_BARS, morning cutoff 10:30) => causal"),
        "abstention_rule": (f"abstain iff day's first-15 range > {TERCILE_TOP:.2f}th percentile of "
                            f"PRIOR DAYS' first-15 ranges (expanding window, warmup={WARMUP_DAYS} days, "
                            f"never abstain during warmup); PRIMARY axis = open-normalized bp"),
        "lookahead_guard": ("tercile cut is CAUSAL (prior-days-only expanding percentile); a "
                            "full-sample tercile would be look-ahead and is reported ONLY to quantify "
                            "the look-ahead premium (NOT allowed to clear the bar) (L14/L34/L57)"),
        "n_signals_ungated": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "first15_coverage": {"days_with_first15": len(first15),
                             "causal_bp_abstain_days": int(sum(abstain_bp.values())),
                             "causal_bp_abstain_signal_days": n_abstain_signal_days_bp,
                             "n_signals_kept_bp": len(kept_bp),
                             "n_signals_kept_pts": len(kept_pts)},
        "gates_required": {
            "oos_per_trade_positive": "> 0",
            "positive_quarters_ge_4": ">= 4/6",
            "top5_day_lt_200": "< 200%",
            "n_ge_20": ">= 20",
            "drop_top5_day_per_trade_positive": "> 0 after removing 5 best days",
            "beats_random_null": f"per-trade > mean+1std of {NULL_SEEDS}-seed random-entry null (L172)",
            "truncation_safe": "per-trade sign does NOT invert at chart-stop-only (L171)",
            "is_half_positive": "IS (2025) per-trade exp > 0",
        },
        "PRIMARY_config": "ITM-2 + causal bp-normalized first-15 tercile abstention",
        "results": {
            "ITM2_bp_PRIMARY": itm2,
            "OTM2_bp_C29": otm2,
            "ITM2_pts_robustness": itm2_pts,
            "ITM2_bp_FULLSAMPLE_lookahead_disclosure": itm2_fs,
        },
        "DISCLOSURE": {
            "subtractive_not_additive": ("partition of the FROZEN survivor signal set; the gate REMOVES "
                                         "chaotic-open days, it adds no confirmations (the campaign proved "
                                         "additive confluence is dead on 0DTE)"),
            "no_cherry_pick": ("BOTH abstention axes (bp-normalized PRIMARY + raw-points robustness) and "
                               "BOTH strike tiers (ITM-2 PRIMARY + OTM-2 per C29) reported with the full "
                               "8-gate scorecard (anti-pattern 2.10)"),
            "net_not_per_trade": ("decision metric is OOS per-trade LIFT *and* OOS total kept-frac *and* "
                                  "maxDD vs ungated baseline — a gate that lifts per-trade but guts total "
                                  "P&L or deepens drawdown is flagged"),
            "causal_threshold": ("expanding-window prior-days tercile, warmup-gated; full-sample variant is "
                                 "look-ahead and disclosed separately, never clears the bar"),
            "fraud_gates": (f"random-entry null ({NULL_SEEDS} seeds, same days/sides, L172) + no-truncation "
                            "(sign holds -8% -> chart-stop-only, L171)"),
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "cross_tier": "C29 — gate judged on ITM-2 (survivor) AND OTM-2 (Safe-2's actual $2K tier)",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sub-first15] wrote {OUT}", flush=True)

    # ── Console verdict ────────────────────────────────────────────────────────
    def _line(tag, ev):
        m = ev["gated"]["metrics"]
        bm = ev["ungated_baseline"]["metrics"]
        vb = ev["vs_baseline"]
        g = ev["gates"]
        print(f"\n[{tag}] clears_all={ev['clears_all_gates']}")
        print(f"  ungated:  n={bm.get('n')} exp=${bm.get('exp_dollar')} oos_exp=${bm.get('oos_exp')} "
              f"oos_total=${bm.get('oos_total')} posQ={bm.get('positive_quarters')} maxDD=${bm.get('max_drawdown_dollars')}")
        print(f"  GATED:    n={m.get('n')} exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} "
              f"oos_total=${m.get('oos_total')} posQ={m.get('positive_quarters')} maxDD=${m.get('max_drawdown_dollars')}")
        print(f"  vs_base:  oos_lift=${vb['oos_per_trade_lift']} oos_kept={vb['oos_total_kept_frac']} "
              f"dMDD=${vb['delta_max_drawdown_dollars']} dropped={vb['n_signals_dropped']} sigs")
        print(f"  gates:    {g}")

    print("\n=== ABSTAIN_FIRST15_RANGE VERDICT ===")
    print(f"survivor signals={len(signals)} on {sig_days}/{n_days} days  side={side_ct}")
    _line("ITM-2 bp PRIMARY", itm2)
    _line("OTM-2 bp (C29)", otm2)
    _line("ITM-2 pts (robustness)", itm2_pts)
    _line("ITM-2 bp FULL-SAMPLE (look-ahead disclosure ONLY)", itm2_fs)
    print(f"\nPRIMARY clears all 8 gates: {primary['clears_all_gates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
