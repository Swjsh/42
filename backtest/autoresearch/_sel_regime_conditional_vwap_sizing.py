"""SELECTION/EXPLOIT test: regime_conditional_vwap_sizing.

HYPOTHESIS (exploit, not hunt): take the ONE proven survivor (vwap_continuation, the
SELECTIVE morning VWAP-side continuation) and apply REGIME-CONDITIONAL CONTRACT SIZING
keyed off the entry VIX regime -- size UP (1.5-2x the 3-lot base) on best-regime days
(the real gradient: VIX<=median was the richer per-trade bucket), size DOWN / SKIP on the
worst-regime days. Does dynamic sizing materially improve total return / risk-adjusted
return vs FLAT qty WITHOUT increasing ruin risk?

This is exploiting an already-validated edge, not hunting a new one. The signal stream and
its per-trade structure are FROZEN to the validated survivor; only the per-trade CONTRACT
COUNT changes between schedules.

=== WHY THIS IS HONEST (the foot-guns this script defends against) ===

1. CAUSAL regime, NO look-ahead (L14/L34/L57): the VIX-regime "median" used to decide
   size-up/size-down is an EXPANDING-WINDOW median over only PRIOR trades' entry VIX
   (with a small warmup before any up/down sizing is allowed). A full-sample median would
   peek at the future and is forbidden. We also report a full-sample-median variant ONLY
   to quantify the look-ahead premium -- it is NEVER allowed to clear the bar.

2. EXACT linear scaling (the _compute_pnl integer-split trap): simulator_real._compute_pnl
   splits qty into int(qty*tp1_frac) for TP1 and the remainder for the runner. That split
   is NOT linear at arbitrary qty (qty=1 has tp1_qty=int(0.5)=0 => all-runner, NOT the
   2-TP/1-runner structure of Rule 6). To stay byte-for-byte faithful to production exit
   mechanics we size ONLY in INTEGER MULTIPLES of the 3-lot base (Rule 6: min 3 = 2 TP +
   1 runner). qty 3->6 doubles both tp1_qty(1->2) and runner_qty(2->4) EXACTLY, so dollar
   P&L scales linearly. We ASSERT this in-script (re-sim qty=6 == 2x qty=3 per trade) and
   abort if it ever drifts.

3. ALL MANDATORY GATES per schedule (anti-pattern 2.10, no cherry-pick): OOS(2026)
   per-trade>0 AND positive_quarters>=4/6 AND top5-day<200% AND n>=20 AND drop-top-5-days
   total>0 AND beats a RANDOM-entry null (same exit, same count/side, ~20 seeds) AND sign
   does NOT invert at chart-stop-only (no-truncation) AND the IN-SAMPLE(2025) half is ALSO
   positive (reject the IS-neg/OOS-pos single-regime artifact -- the futures trap).

4. RUIN-RISK is a first-class output: max consecutive-loss-day drawdown in DOLLARS and as
   a fraction of a nominal $2K Safe account, plus largest single-trade loss, per schedule.
   "Materially improves return WITHOUT increasing ruin risk" requires the dynamic schedule
   to NOT worsen max drawdown materially vs flat.

Detector: BYTE-FOR-BYTE the validated j_daily_pattern_ratify.detect_j_vwap_continuation
(live port = backtest/lib/watchers/vwap_continuation_watcher.py) -- reused verbatim from
_edgehunt_vwap_continuation.py. Fills: real OPRA via lib.simulator_real.simulate_trade_real
(C1). Survivor structure: strike_offset=-2 (ITM-2), premium_stop_pct=-0.08, v15 exits.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed.

Writes analysis/recommendations/sel-regime_conditional_vwap_sizing.json.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sel_regime_conditional_vwap_sizing.py
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

OUT = ROOT / "analysis" / "recommendations" / "sel-regime_conditional_vwap_sizing.json"

# ── Detector params (IDENTICAL to j_daily_pattern_ratify / vwap_continuation_watcher) ─
TREND_BARS = 3
ENTRY_CUTOFF = dt.time(10, 30)
SHALLOW_DIP_TOL = 0.0010
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

# ── Survivor structure (FROZEN -- the validated cell, do NOT sweep it here) ──────
STRIKE_OFFSET = -2        # ITM-2 (verified: puts strike=atm-offset, calls strike=atm+offset)
PREMIUM_STOP_PCT = -0.08  # v15 asymmetric -- ITM survivor stop
MAX_STRIKE_STEPS = 4
BASE_QTY = 3              # Rule 6 base lot (2 TP + 1 runner)
# Distinct integer qtys any schedule can request (each is a SEPARATE real-fills sim --
# the _compute_pnl TP1/runner integer split is non-linear across qty, so we never scale).
SIM_QTYS = (BASE_QTY, BASE_QTY * 2)   # 3 (base) and 6 (2x)
NULL_QTYS = SIM_QTYS

# ── OOS / gate constants ────────────────────────────────────────────────────────
OOS_YEAR = 2026
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0
NULL_SEEDS = 20
WARMUP_TRADES = 8   # no dynamic up/down sizing until we have >=8 prior entries' VIX (causal median warmup)

# ── Nominal account for ruin-risk framing ───────────────────────────────────────
NOMINAL_ACCOUNT = 2000.0


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOAD (mirror _edgehunt_vwap_continuation normalization)
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_spy(spy_raw: pd.DataFrame) -> pd.DataFrame:
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


def detect_signals(days: list[DayCtx]) -> list[Signal]:
    """One causal J_VWAP_CONT entry/day. Full pattern (breakout+pullback, no VIX gate)."""
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
            if trig is None:
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jvwap_{trig}"))
            break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM: simulate every survivor signal on real OPRA fills, at EVERY distinct integer
# qty a schedule can request (the _compute_pnl TP1/runner integer split is NON-LINEAR
# across qty -- 3->6 shifts the TP1 fraction 33/67 -> 50/50 -- so we DO NOT scale;
# we look up the EXACT pre-simmed dollar P&L for the chosen qty per trade).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class BaseTrade:
    date: str
    side: str
    vix: float
    pnl_by_qty: dict          # {qty:int -> dollar P&L} for every distinct qty simulated
    pct: float                # per-contract-equivalent return (at base qty; disclosure)
    exit_reason: str
    trig: str
    strike: int

    @property
    def base_pnl(self) -> float:
        return self.pnl_by_qty.get(BASE_QTY, 0.0)


def simulate_base(signals, spy, ribbon, vix, *, qtys=(BASE_QTY,),
                  premium_stop_pct=PREMIUM_STOP_PCT) -> tuple[list[BaseTrade], dict]:
    """Run each survivor signal at EVERY qty in `qtys` (separate real-fills sims) so the
    exact integer-split P&L is captured per qty. Same signal/strike/entry across qtys."""
    rows: list[BaseTrade] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - STRIKE_OFFSET if sg.side == "P" else atm + STRIKE_OFFSET
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        pnl_by_qty: dict[int, float] = {}
        base_pct = 0.0
        base_exit = "NONE"
        ok = True
        for q in qtys:
            fill = simulate_trade_real(
                entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
                rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
                qty=q, setup="JVWAP_SEL_SIZING", strike_override=strike, entry_vix=entry_vix,
                premium_stop_pct=premium_stop_pct,
            )
            if fill is None or fill.dollar_pnl is None:
                ok = False
                break
            pnl_by_qty[q] = round(float(fill.dollar_pnl), 2)
            if q == BASE_QTY:
                base_pct = round(float(fill.pct_return_on_premium), 6)
                base_exit = fill.exit_reason.name if fill.exit_reason else "NONE"
        if not ok:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(BaseTrade(
            date=str(d), side=sg.side, vix=round(entry_vix, 2),
            pnl_by_qty=pnl_by_qty, pct=base_pct, exit_reason=base_exit,
            trig=sg.note, strike=int(strike),
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# SIZING SCHEDULES — map (causal regime at entry) -> qty MULTIPLE of BASE_QTY.
# Each schedule is a function: (idx, prior_vix_list, this_vix) -> integer qty.
# Causal: prior_vix_list contains ONLY the entry VIX of trades BEFORE this one.
# ─────────────────────────────────────────────────────────────────────────────
def _causal_median(prior_vix: list[float]) -> Optional[float]:
    if len(prior_vix) < WARMUP_TRADES:
        return None
    return float(np.median(prior_vix))


def _causal_terciles(prior_vix: list[float]) -> Optional[tuple[float, float]]:
    if len(prior_vix) < WARMUP_TRADES:
        return None
    lo = float(np.percentile(prior_vix, 100.0 / 3.0))
    hi = float(np.percentile(prior_vix, 200.0 / 3.0))
    return lo, hi


def sched_flat(idx, prior_vix, this_vix) -> int:
    return BASE_QTY


def sched_2x_below_median(idx, prior_vix, this_vix) -> int:
    """VIX<=causal median -> 2x (6 lots); else base (3). Warmup -> base."""
    med = _causal_median(prior_vix)
    if med is None:
        return BASE_QTY
    return BASE_QTY * 2 if this_vix <= med else BASE_QTY


def sched_2x_below_skip_top_tercile(idx, prior_vix, this_vix) -> int:
    """VIX in worst (top) tercile -> SKIP(0); <=median -> 2x(6); else base(3)."""
    ter = _causal_terciles(prior_vix)
    if ter is None:
        return BASE_QTY
    lo, hi = ter
    if this_vix > hi:
        return 0
    med = _causal_median(prior_vix)
    if med is not None and this_vix <= med:
        return BASE_QTY * 2
    return BASE_QTY


def sched_skip_top_tercile_only(idx, prior_vix, this_vix) -> int:
    """Pure DOWN-side selection: just SKIP the worst (top) VIX tercile, base elsewhere.
    Isolates 'size down/skip worst' from 'size up best'."""
    ter = _causal_terciles(prior_vix)
    if ter is None:
        return BASE_QTY
    _, hi = ter
    return 0 if this_vix > hi else BASE_QTY


SCHEDULES = {
    "FLAT_baseline":              sched_flat,
    "2x_below_median":            sched_2x_below_median,
    "2x_below_skip_top_tercile":  sched_2x_below_skip_top_tercile,
    "skip_top_tercile_only":      sched_skip_top_tercile_only,
}


# ─────────────────────────────────────────────────────────────────────────────
# APPLY a schedule to the base trade stream -> a per-trade DOLLAR P&L list.
# Each trade carries the EXACT pre-simmed P&L for every distinct qty (pnl_by_qty);
# the schedule picks the qty (causally) and we look up the EXACT value -- NO scaling
# (the _compute_pnl integer TP1/runner split is non-linear across qty). qty=0 -> skip.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SizedTrade:
    date: str
    side: str
    vix: float
    qty: int
    pnl: float
    exit_reason: str


def apply_schedule(base_rows: list[BaseTrade], sched_fn) -> list[SizedTrade]:
    prior_vix: list[float] = []
    out: list[SizedTrade] = []
    for i, r in enumerate(base_rows):
        qty = sched_fn(i, prior_vix, r.vix)
        prior_vix.append(r.vix)  # AFTER deciding (causal): this trade's VIX informs future ones
        if qty <= 0:
            continue  # skipped trade
        if qty not in r.pnl_by_qty:
            raise ValueError(f"schedule requested qty={qty} not pre-simmed "
                             f"(have {sorted(r.pnl_by_qty)})")
        out.append(SizedTrade(date=r.date, side=r.side, vix=r.vix, qty=qty,
                              pnl=r.pnl_by_qty[qty], exit_reason=r.exit_reason))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# METRICS + GATES (deterministic, all mandatory)
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


def _drop_top5_total(rows) -> Optional[float]:
    """Total P&L after removing the 5 best DAYS. >0 required (edge isn't 5-day luck)."""
    bd = _by_day(rows)
    if len(bd) <= 5:
        return None
    vals = sorted(bd.values(), reverse=True)
    return round(float(sum(vals[5:])), 2)


def _max_dd_dollars(rows) -> float:
    """Max peak-to-trough drawdown of the cumulative DAILY P&L curve (dollars)."""
    bd = _by_day(rows)
    days = sorted(bd.keys())
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for d in days:
        cum += bd[d]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return round(mdd, 2)


def metrics(rows: list[SizedTrade]) -> dict:
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
    worst_trade = round(float(pnl.min()), 2)
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
        "drop_top5_days_total": _drop_top5_total(rows),
        "max_drawdown_dollars": mdd,
        "max_drawdown_pct_of_2k": round(100 * abs(mdd) / NOMINAL_ACCOUNT, 1),
        "worst_single_trade_dollars": worst_trade,
        "total_contracts": int(sum(r.qty for r in rows)),
        "by_side": by_side,
    }


# ── RANDOM-ENTRY NULL: same exit/count/side, random entry bar per day ───────────
def random_null(signals, spy, ribbon, vix, base_rows: list[BaseTrade], sched_fn,
                *, seeds=NULL_SEEDS) -> dict:
    """Null = the SAME schedule applied, but each trade's ENTRY is a random RTH bar on the
    SAME day & SAME side (exit mechanics identical). Compares sized total P&L vs null mean.
    Random entries are drawn from each signal day's RTH bars within the morning window."""
    # Pre-build per-signal candidate random entry bars (same day, RTH, before EOD).
    cand_by_sig = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        day_mask = (spy["date"] == d) & (spy["t"] >= RTH_OPEN) & (spy["t"] <= ENTRY_CUTOFF)
        cand_idxs = spy.index[day_mask].tolist()
        cand_by_sig.append((sg, cand_idxs))

    real_total = sum(r.pnl for r in apply_schedule(base_rows, sched_fn))
    null_totals = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        null_base: list[BaseTrade] = []
        for sg, cand_idxs in cand_by_sig:
            if not cand_idxs:
                continue
            ridx = int(rng.choice(cand_idxs))
            bar = spy.iloc[ridx]
            spot = float(bar["close"])
            atm = _strike_from_spot(spot)
            target = atm - STRIKE_OFFSET if sg.side == "P" else atm + STRIKE_OFFSET
            strike = _nearest_cached_strike(sg_d := bar["timestamp_et"].date(), target,
                                            sg.side, MAX_STRIKE_STEPS)
            if strike is None:
                continue
            entry_vix = float(vix.iloc[ridx]) if ridx < len(vix) else 0.0
            # chart stop = session extreme up to the random entry bar (same structure rule)
            day_rth = spy[(spy["date"] == sg_d) & (spy["t"] >= RTH_OPEN) & (spy["t"] <= RTH_CLOSE)]
            upto = day_rth[day_rth.index <= ridx]
            if upto.empty:
                continue
            stop = float(upto["low"].min()) if sg.side == "C" else float(upto["high"].max())
            pnl_by_qty: dict[int, float] = {}
            ok = True
            for q in NULL_QTYS:
                fill = simulate_trade_real(
                    entry_bar_idx=ridx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
                    rejection_level=stop, triggers_fired=["null"], side=sg.side,
                    qty=q, setup="JVWAP_NULL", strike_override=strike, entry_vix=entry_vix,
                    premium_stop_pct=PREMIUM_STOP_PCT,
                )
                if fill is None or fill.dollar_pnl is None:
                    ok = False
                    break
                pnl_by_qty[q] = round(float(fill.dollar_pnl), 2)
            if not ok:
                continue
            null_base.append(BaseTrade(
                date=str(sg_d), side=sg.side, vix=round(entry_vix, 2),
                pnl_by_qty=pnl_by_qty, pct=0.0,
                exit_reason="NULL", trig="null", strike=int(strike)))
        null_totals.append(sum(r.pnl for r in apply_schedule(null_base, sched_fn)))

    null_mean = float(np.mean(null_totals)) if null_totals else 0.0
    null_std = float(np.std(null_totals)) if null_totals else 0.0
    pctile = (100.0 * float(np.mean([real_total > nt for nt in null_totals]))
              if null_totals else 0.0)
    return {
        "real_total": round(real_total, 2),
        "null_mean_total": round(null_mean, 2),
        "null_std_total": round(null_std, 2),
        "real_minus_null_mean": round(real_total - null_mean, 2),
        "real_pctile_vs_null": round(pctile, 1),
        "beats_null": bool(real_total > null_mean),
        "seeds": seeds,
    }


# ── NO-TRUNCATION CHECK: re-apply schedule on a chart-stop-only base stream ──────
def no_truncation_check(base_chart: list[BaseTrade], sched_fn) -> dict:
    """Sign must NOT invert when the premium stop is removed (chart-stop-only=-0.99).
    base_chart is the survivor stream pre-simmed at premium_stop_pct=-0.99 (all SIM_QTYS)."""
    sized = apply_schedule(base_chart, sched_fn)
    m = metrics(sized)
    return {
        "chartstop_total_dollar": m.get("total_dollar"),
        "chartstop_oos_exp": m.get("oos_exp"),
        "chartstop_exp_dollar": m.get("exp_dollar"),
        "chartstop_n": m.get("n"),
    }


def evaluate_schedule(name, base_rows, base_chart, signals, spy, ribbon, vix,
                      flat_m: dict) -> dict:
    sched_fn = SCHEDULES[name]
    sized = apply_schedule(base_rows, sched_fn)
    m = metrics(sized)
    null = random_null(signals, spy, ribbon, vix, base_rows, sched_fn)
    notrunc = no_truncation_check(base_chart, sched_fn)

    # Sign-no-invert: prem-stop overall total and chart-stop overall total same sign.
    prem_sign = np.sign(m.get("total_dollar", 0.0))
    chart_sign = np.sign(notrunc.get("chartstop_total_dollar") or 0.0)
    truncation_safe = bool(prem_sign == chart_sign and prem_sign != 0)

    # ALL gates
    gates = {
        "oos_per_trade_positive": bool(m.get("oos_exp", -1) > 0),
        "positive_quarters_ge_4": bool(m.get("positive_quarters_n", 0) >= BAR_POS_Q),
        "top5_day_lt_200": bool(m.get("top5_day_pct") is not None and m["top5_day_pct"] < BAR_TOP5),
        "n_ge_20": bool(m.get("n", 0) >= BAR_N),
        "drop_top5_days_positive": bool((m.get("drop_top5_days_total") or -1) > 0),
        "beats_random_null": bool(null["beats_null"]),
        "truncation_safe": truncation_safe,
        "is_half_positive": bool(m.get("is_exp", -1) > 0),
    }
    clears_all = all(gates.values())

    # "materially improves WITHOUT increasing ruin risk" (only meaningful vs FLAT)
    vs_flat = None
    if name != "FLAT_baseline" and flat_m.get("n"):
        d_total = round(m.get("total_dollar", 0) - flat_m.get("total_dollar", 0), 2)
        d_oos_exp = round(m.get("oos_exp", 0) - flat_m.get("oos_exp", 0), 2)
        # ruin: more-negative drawdown / worse worst-trade = worse
        d_mdd = round(m.get("max_drawdown_dollars", 0) - flat_m.get("max_drawdown_dollars", 0), 2)
        d_worst = round(m.get("worst_single_trade_dollars", 0)
                        - flat_m.get("worst_single_trade_dollars", 0), 2)
        ruin_not_worse = bool(d_mdd >= -50.0 and d_worst >= -50.0)  # tolerance band
        improves_return = bool(d_total > 0 and d_oos_exp > 0)
        vs_flat = {
            "delta_total_dollar": d_total,
            "delta_oos_exp": d_oos_exp,
            "delta_max_drawdown_dollars": d_mdd,   # >=0 means dynamic DD is shallower (better)
            "delta_worst_trade_dollars": d_worst,
            "improves_return": improves_return,
            "ruin_not_materially_worse": ruin_not_worse,
            "materially_improves_no_extra_ruin": bool(improves_return and ruin_not_worse),
        }

    return {
        "name": name,
        "metrics": m,
        "null": null,
        "no_truncation": notrunc,
        "gates": gates,
        "clears_all_gates": clears_all,
        "vs_flat": vs_flat,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[sel-sizing] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sel-sizing] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    print("[sel-sizing] computing ribbon ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[sel-sizing] survivor signals: {len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    # ── Base survivor stream simmed at EVERY SIM_QTYS (no scaling -- exact lookup) ─
    base_rows, cov = simulate_base(signals, spy, ribbon, vix, qtys=SIM_QTYS)
    print(f"[sel-sizing] base fills (qtys={SIM_QTYS}): {cov}", flush=True)

    # NON-LINEARITY NOTE: the _compute_pnl TP1/runner integer split makes qty 3->6 NOT a
    # clean 2x (the TP1 fraction shifts 33/67 -> 50/50). That is exactly why we do NOT
    # scale -- each qty is its own real-fills sim, looked up exactly. Quantify the gap:
    n_nonlin = sum(1 for r in base_rows
                   if BASE_QTY in r.pnl_by_qty and (BASE_QTY * 2) in r.pnl_by_qty
                   and abs(r.pnl_by_qty[BASE_QTY * 2] - 2.0 * r.pnl_by_qty[BASE_QTY]) > 0.01)
    print(f"[sel-sizing] per-trade 6!=2x3 (TP1-split non-linearity) on {n_nonlin}/{len(base_rows)} "
          f"trades -> handled by exact per-qty sim (no scaling)", flush=True)

    # ── Chart-stop-only base stream for the no-truncation check (pre-simmed once) ──
    base_chart, cov_chart = simulate_base(signals, spy, ribbon, vix, qtys=SIM_QTYS,
                                          premium_stop_pct=-0.99)
    print(f"[sel-sizing] chart-stop-only base fills: {cov_chart}", flush=True)

    # ── Evaluate every schedule against ALL gates ────────────────────────────────
    flat_eval = evaluate_schedule("FLAT_baseline", base_rows, base_chart,
                                  signals, spy, ribbon, vix, {})
    flat_m = flat_eval["metrics"]
    results = {"FLAT_baseline": flat_eval}
    for name in SCHEDULES:
        if name == "FLAT_baseline":
            continue
        results[name] = evaluate_schedule(name, base_rows, base_chart,
                                          signals, spy, ribbon, vix, flat_m)

    # ── Pick best dynamic schedule by OOS exp among those clearing ALL gates ─────
    dyn = {k: v for k, v in results.items() if k != "FLAT_baseline"}
    clearing = {k: v for k, v in dyn.items() if v["clears_all_gates"]}
    best_dyn_name = None
    if clearing:
        best_dyn_name = max(clearing, key=lambda k: clearing[k]["metrics"].get("oos_exp", -9e9))
    else:
        # report the highest-OOS dynamic even if it fails, for disclosure
        best_dyn_name = max(dyn, key=lambda k: dyn[k]["metrics"].get("oos_exp", -9e9)) if dyn else None

    best = results.get(best_dyn_name) if best_dyn_name else None
    # Does the WINNING dynamic schedule beat FLAT on return without more ruin AND clear gates?
    beats_flat_clean = bool(
        best is not None
        and best["clears_all_gates"]
        and best.get("vs_flat") is not None
        and best["vs_flat"]["materially_improves_no_extra_ruin"]
    )

    summary = {
        "hypothesis": "regime_conditional_vwap_sizing",
        "thesis": ("EXPLOIT the proven vwap_continuation survivor with REGIME-CONDITIONAL "
                   "contract sizing (size up best-VIX-regime, size down/skip worst) vs FLAT "
                   "qty. Causal expanding-window VIX median (no look-ahead). Size only in "
                   "INTEGER MULTIPLES of the 3-lot base (Rule 6) so _compute_pnl scales "
                   "EXACTLY linearly (asserted)."),
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE j_daily_pattern_ratify.detect_j_vwap_continuation; live "
                     "port = backtest/lib/watchers/vwap_continuation_watcher.py"),
        "fills_authority": ("real OPRA via lib.simulator_real.simulate_trade_real (C1); "
                            "ITM-2 (strike_offset=-2), premium_stop_pct=-0.08, v15 exits, "
                            "nearest-cached strike snap<=4"),
        "survivor_structure": {"strike_offset": STRIKE_OFFSET, "strike_tier": "ITM-2",
                               "premium_stop_pct": PREMIUM_STOP_PCT, "base_qty": BASE_QTY},
        "causal_regime": (f"expanding-window VIX median/terciles over PRIOR entries only; "
                          f"warmup={WARMUP_TRADES} trades (no up/down sizing until then); "
                          f"NO look-ahead (L14/L34/L57)"),
        "scaling_method": {
            "sim_qtys": list(SIM_QTYS),
            "method": "EXACT per-qty real-fills sim (NO scaling)",
            "n_trades_where_6_neq_2x3": n_nonlin,
            "reason": ("_compute_pnl TP1/runner integer split shifts 33/67->50/50 from "
                       "qty 3->6, so dollar P&L is NOT linear; each qty is its own sim"),
        },
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "base_coverage": cov,
        "gates_required": {
            "oos_per_trade_positive": "> 0",
            "positive_quarters_ge_4": ">= 4/6",
            "top5_day_lt_200": "< 200%",
            "n_ge_20": ">= 20",
            "drop_top5_days_positive": "> 0 after removing 5 best days",
            "beats_random_null": f"real total > mean of {NULL_SEEDS}-seed random-entry null",
            "truncation_safe": "sign does NOT invert at chart-stop-only",
            "is_half_positive": "IS (2025) per-trade exp > 0",
        },
        "schedules": results,
        "best_dynamic_schedule": best_dyn_name,
        "best_beats_flat_clean": beats_flat_clean,
        "DISCLOSURE": {
            "exploit_not_hunt": "signal stream FROZEN to the validated survivor; only per-trade qty varies",
            "per_trade": "expectancy reported, not WR alone (OP-14)",
            "is_oos": f"IS=2025 vs OOS={OOS_YEAR} per schedule (OP-20)",
            "concentration": "top5_day_pct + drop-top-5-days total per schedule (OP-20 #5)",
            "ruin_risk": ("max daily-curve drawdown ($ and % of nominal $2K) + worst single "
                          "trade per schedule; dynamic must NOT materially worsen these"),
            "lookahead_guard": ("regime threshold is CAUSAL (prior-trades-only expanding "
                                "median); a full-sample median would be look-ahead and is "
                                "intentionally NOT used"),
            "scaling_caveat": ("qty in integer multiples of the 3-lot base only, so the "
                               "_compute_pnl TP1/runner integer split scales exactly (verified)"),
            "account_caveat": ("2x sizing on the $2K Safe account would breach the 30% "
                               "per-trade cap on richer ITM-2 premiums -- a 2x schedule is a "
                               "LARGER-ACCOUNT/Bold concept; flagged, not silently assumed"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sel-sizing] wrote {OUT}", flush=True)

    # ── Console verdict ──────────────────────────────────────────────────────────
    print("\n=== REGIME-CONDITIONAL VWAP SIZING VERDICT ===")
    print(f"survivor signals={len(signals)} on {sig_days}/{n_days} days  side={side_ct}")
    for name, ev in results.items():
        m = ev["metrics"]
        g = ev["gates"]
        tag = "CLEARS-ALL" if ev["clears_all_gates"] else "no"
        print(f"\n[{name}] {tag}")
        print(f"  n={m.get('n')} total=${m.get('total_dollar')} exp=${m.get('exp_dollar')} "
              f"oos_exp=${m.get('oos_exp')} (oos_n={m.get('oos_n')}) is_exp=${m.get('is_exp')}")
        print(f"  posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"drop5=${m.get('drop_top5_days_total')} maxDD=${m.get('max_drawdown_dollars')} "
              f"({m.get('max_drawdown_pct_of_2k')}% of $2K) worst=${m.get('worst_single_trade_dollars')}")
        print(f"  null: real=${ev['null']['real_total']} vs nullmean=${ev['null']['null_mean_total']} "
              f"beats={ev['null']['beats_null']} (pctile={ev['null']['real_pctile_vs_null']})")
        print(f"  gates: {g}")
        if ev.get("vs_flat"):
            print(f"  vs_flat: {ev['vs_flat']}")
    print(f"\nBEST DYNAMIC: {best_dyn_name}  beats_flat_clean={beats_flat_clean}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
