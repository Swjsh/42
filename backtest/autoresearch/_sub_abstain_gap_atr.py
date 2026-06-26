"""SUBTRACTIVE abstention test: abstain_gap_atr on vwap_continuation real fills.

HYPOTHESIS (J, 2026-06-20): Skip vwap_continuation entries on days whose OPENING
GAP exceeds N x ATR(14) — i.e. abstain on overnight-gap-risk-regime days. Sweep
N in {1, 1.5, 2}. Does abstaining on big-gap days LIFT OOS per-trade AND CUT
drawdown on the surviving entries, NET of the trades it removes?

WHY SUBTRACTIVE — the selection campaign proved ADDITIVE confluence (stack more
confirmations) is DEAD on 0DTE (theta-trap / single-regime / over-constraint). The
ONE win was SUBTRACTIVE: skip_top_tercile_only (abstain from vwap entries in the
worst VIX regime) cleared all 8 gates -> OOS +$142/tr AND maxDD -$424. This test
asks whether a DIFFERENT subtraction — abstain on gap-risk days — also works.

METHOD (no drift — C14):
  * Detector is BYTE-FOR-BYTE the validated vwap_continuation logic (imported from
    _edgehunt_vwap_continuation.detect_signals); signals detected ONCE.
  * Each N is a PARTITION (subset) of that SAME signal set: KEEP a signal iff its
    day's |opening_gap| <= N * ATR(14). Re-simulate the KEPT subset on the SAME
    real-fills path -> isolates the abstention's NET effect.
  * STRIKE: survivor structure strike_offset=-2 (ITM-2) PRIMARY; ALSO report
    strike_offset=+2 (OTM-2 = Safe-2's actual $2K tier) per C29 (gates don't
    transfer across strike tiers).
  * OOS split = calendar-year: IS=2025, OOS=2026 (OP-20 convention). Real OPRA
    fills cached through ~2026-05-29 -> OOS fills = Jan..May 2026 (post-cache
    signals drop as cache_miss, disclosed in coverage).

GAP / ATR — both CAUSAL (look-ahead-safe):
  * opening_gap = today's RTH-open - prior trading day's RTH-close. Known at the
    open, BEFORE any entry (entries are >= bar 3 / <= 10:30 ET). No look-ahead.
  * ATR(14) = Wilder ATR over the prior 14 COMPLETED daily bars (daily TR built
    from each prior RTH session's H/L and the day-before close). The current day
    is EXCLUDED from the ATR -> the gate uses only information available at the
    open. (C6 no-look-ahead.)
  * gap_atr_ratio = |opening_gap| / ATR(14). Days where ATR(14) is undefined
    (first 14 days warmup) are KEPT by default (the gate cannot fire without a
    reference ATR) and disclosed in coverage.

ALL 8 GATES MANDATORY (anti-2.10 cherry-pick guard) — the KEPT subset must clear:
  1. OOS(2026) per-trade > 0
  2. positive_quarters >= 4/6
  3. top5_day_pct < 200
  4. n_trades >= 20
  5. drop-top5 (per-trade after removing the 5 best P&L days) > 0
  6. IS(2025)-half > 0 (first-half-of-IS per-trade positive — temporal stability)
  7. beats random-entry-null (L172; ~20 seeds; same days/sides; standard bar =
     beat null MAX AND drop-top5 beats null MEAN, via null_baseline.null_gate)
  8. no-truncation (L171): per-trade SIGN holds from -8% stop -> chart-stop-only
     (-0.99). Sign inversion = pure stop-truncation of a SPY tilt, not an edge.

Plus the SUBTRACTIVE-thesis decision metrics vs the ungated baseline: OOS
per-trade LIFT and maxDrawdown CUT (the two things skip_top_tercile_only delivered).

Pure Python, $0 (no LLM, no live orders). Markets CLOSED (weekend).
Writes analysis/recommendations/sub-abstain-gap-atr.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_abstain_gap_atr.py
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

# REUSE the validated detector + data normalizers from the edgehunt harness so the
# signal set is byte-for-byte identical (no drift). We ONLY add the abstention partition.
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
    DayCtx,
    RTH_OPEN,
    RTH_CLOSE,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sub-abstain-gap-atr.json"

# ── SURVIVOR config (FIXED) ─────────────────────────────────────────────────────
ITM2_OFFSET = -2            # survivor structure (PRIMARY)
OTM2_OFFSET = +2            # Safe-2's actual $2K tier (C29 cross-tier report)
SURV_PREMIUM_STOP = -0.08   # -8% premium stop
CHART_STOP_ONLY = -0.99     # for the no-truncation fraud gate

# ── Abstention sweep (the whole point — NO cherry-pick) ─────────────────────────
GAP_ATR_NS = [1.0, 1.5, 2.0]
ATR_PERIOD = 14

# random-null
N_NULL_SEEDS = 20

# ── 8-gate thresholds (documented; mirror the campaign bar) ─────────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0


# ─────────────────────────────────────────────────────────────────────────────
# DAILY ATR(14) + OPENING GAP per trading day — both CAUSAL (use only prior days).
# ─────────────────────────────────────────────────────────────────────────────
def _wilder_daily_atr(tr: list[float], period: int) -> list[Optional[float]]:
    """Wilder ATR over a sequence of DAILY true ranges. atr[i] is the ATR computed
    THROUGH day i (inclusive). Returns None for the warmup (first `period` days)."""
    n = len(tr)
    out: list[Optional[float]] = [None] * n
    if n < period:
        return out
    seed = float(np.mean(tr[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def build_gap_atr_by_date(days: list[DayCtx], period: int = ATR_PERIOD) -> dict[dt.date, dict]:
    """Map trading date -> {opening_gap, atr14, gap_atr_ratio}, all look-ahead-safe.

    Daily bar = each day's RTH session. Daily TR(d) = max(H_d - L_d, |H_d - C_{d-1}|,
    |L_d - C_{d-1}|) where C_{d-1} is the PRIOR day's RTH close. ATR14 read for day d
    is the Wilder ATR computed through day d-1 (PRIOR completed days ONLY) so it is
    known at d's open. Opening gap = open_d - close_{d-1}.
    """
    # Build the ordered daily OHLC series from each DayCtx's RTH slice.
    rows = []
    for dc in days:
        rth = dc.rth
        rows.append({
            "date": dc.date,
            "open": float(rth["open"].iloc[0]),
            "high": float(rth["high"].max()),
            "low": float(rth["low"].min()),
            "close": float(rth["close"].iloc[-1]),
        })
    # Daily true range (uses prior close); TR[0] undefined -> use H-L (no prior close).
    tr: list[float] = []
    prior_close: Optional[float] = None
    for r in rows:
        if prior_close is None:
            tr.append(r["high"] - r["low"])
        else:
            tr.append(max(r["high"] - r["low"],
                          abs(r["high"] - prior_close),
                          abs(r["low"] - prior_close)))
        prior_close = r["close"]
    atr_through = _wilder_daily_atr(tr, period)  # atr_through[i] = ATR through day i

    out: dict[dt.date, dict] = {}
    for i, r in enumerate(rows):
        prior_close_i = rows[i - 1]["close"] if i > 0 else None
        gap = (r["open"] - prior_close_i) if prior_close_i is not None else None
        # ATR available at day i's open = ATR computed THROUGH day i-1 (prior days only).
        atr_asof = atr_through[i - 1] if i > 0 else None
        ratio = (abs(gap) / atr_asof) if (gap is not None and atr_asof and atr_asof > 0) else None
        out[r["date"]] = {
            "opening_gap": (round(gap, 4) if gap is not None else None),
            "atr14": (round(atr_asof, 4) if atr_asof is not None else None),
            "gap_atr_ratio": (round(ratio, 4) if ratio is not None else None),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal subset at one (strike, stop). v15 default exits.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    trig: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct) -> tuple[list[TradeRow], dict]:
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
            qty=QTY, setup="JVWAP_ABSTAIN_GAP", strike_override=strike, entry_vix=entry_vix,
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
# METRICS (OP-20 disclosure block) + maxDrawdown (the subtractive-thesis metric)
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
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _max_drawdown_daily(rows: list[TradeRow]) -> Optional[float]:
    """Max peak-to-trough drawdown of the cumulative DAILY-P&L equity curve.

    Trades aggregated per day (chronological), cumulative equity, max(peak - equity).
    Returned as a NEGATIVE dollar number (the trough depth below the running peak),
    matching the campaign's maxDD convention (e.g. skip_top_tercile maxDD -$424)."""
    if not rows:
        return None
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for d in sorted(by_day):
        eq += by_day[d]
        peak = max(peak, eq)
        dd = eq - peak
        max_dd = min(max_dd, dd)
    return round(max_dd, 2)


def _is_first_half_per_trade(rows: list[TradeRow]) -> Optional[float]:
    """Gate 6 — IS(2025) first-half per-trade. Splits the 2025 (IS) trades in half by
    DATE order; returns the per-trade mean of the FIRST half (temporal stability inside
    IS — guards against an edge that only shows up late in the in-sample period)."""
    is_rows = sorted([r for r in rows if int(r.date[:4]) != OOS_YEAR], key=lambda r: r.date)
    if len(is_rows) < 2:
        return None
    half = len(is_rows) // 2
    first = [r.pnl for r in is_rows[:half]]
    return round(float(np.mean(first)), 2) if first else None


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

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "is_first_half_per_trade": _is_first_half_per_trade(rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "max_drawdown": _max_drawdown_daily(rows),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# FRAUD GATE — random-entry null via the shared null_baseline (L172). Same days/sides
# as the kept subset (eligible morning bars), same strike+stop+swing invalidation.
# ─────────────────────────────────────────────────────────────────────────────
def run_null(kept_signals, rth, spy, *, strike_offset, premium_stop_pct, seeds=N_NULL_SEEDS) -> dict:
    """Random-entry null on the SAME days/sides as the kept subset, restricted to the
    morning entry window the detector uses (>= TREND_BARS bar, <= ENTRY_CUTOFF)."""
    n_c = sum(1 for s in kept_signals if s.side == "C")
    n_p = sum(1 for s in kept_signals if s.side == "P")
    n_sig = len(kept_signals)
    # Eligible random-entry bars = RTH bars inside the detector's morning window.
    return random_entry_null(
        rth, n_signals=n_sig, n_call=n_c, n_put=n_p,
        strike_offset=strike_offset, premium_stop_pct=premium_stop_pct,
        qty=QTY, entry_gate=(dt.time(9, 30), ENTRY_CUTOFF), seeds=seeds,
        setup="ABSTAIN_GAP_NULL", triggers=["random_null"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate ALL 8 GATES on a kept-subset's metrics block (for one strike tier)
# ─────────────────────────────────────────────────────────────────────────────
def eval_8_gates(m: dict, cs_m: dict, null: dict) -> dict:
    """Return the 8 booleans + a single clears_all_gates. cs_m = chart-stop-only
    metrics on the SAME subset (no-truncation). null = random_entry_null result."""
    n = m.get("n", 0)
    oos_pt = m.get("oos_exp")
    drop5 = m.get("drop_top5_day_per_trade")
    is_half = m.get("is_first_half_per_trade")
    top5 = m.get("top5_day_pct")

    g1_oos = bool(oos_pt is not None and oos_pt > 0)
    g2_posq = bool(m.get("positive_quarters_n", 0) >= BAR_POS_Q)
    g3_top5 = bool(top5 is not None and top5 < BAR_TOP5)
    g4_n = bool(n >= BAR_N)
    g5_drop5 = bool(drop5 is not None and drop5 > 0)
    g6_ishalf = bool(is_half is not None and is_half > 0)

    ng = null_gate(m.get("exp_dollar"), drop5, null)
    g7_null = bool(ng.get("null_pass"))

    # no-truncation: sign must hold from -8% -> chart-stop-only. Use is_truncation_artifact
    # (L171 graduated guard): NOT an artifact => sign stable / gate passes.
    artifact = is_truncation_artifact(
        best_per_trade=m.get("exp_dollar"),
        chart_stop_only_per_trade=cs_m.get("exp_dollar"),
        best_premium_stop_pct=SURV_PREMIUM_STOP,
    )
    # Also require the OVERALL sign to hold across the stop axis (both positive),
    # which is the direct L171 sign-stability statement.
    sign_stable = bool(
        cs_m.get("n") and m.get("exp_dollar") is not None
        and (m["exp_dollar"] > 0) == (cs_m.get("exp_dollar", 0) > 0)
    )
    g8_trunc = bool((not artifact) and sign_stable)

    gates = {
        "g1_oos_per_trade_pos": g1_oos,
        "g2_positive_quarters_ge4": g2_posq,
        "g3_top5_lt200": g3_top5,
        "g4_n_ge20": g4_n,
        "g5_drop_top5_pos": g5_drop5,
        "g6_is_first_half_pos": g6_ishalf,
        "g7_beats_random_null": g7_null,
        "g8_no_truncation": g8_trunc,
    }
    clears = all(gates.values())
    failed = [k for k, v in gates.items() if not v]
    return {
        "gates": gates,
        "clears_all_gates": clears,
        "failed_gates": failed,
        "null_detail": ng,
        "truncation_detail": {"is_artifact": artifact, "sign_stable": sign_stable,
                              "stop8_exp": m.get("exp_dollar"),
                              "chartstop_exp": cs_m.get("exp_dollar")},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Build a full per-tier result for ONE kept-subset (metrics + chart-stop + null + gates)
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_tier(kept_signals, spy, ribbon, vix, rth, base_m, *, strike_offset, run_fraud) -> dict:
    rows, cov = simulate_set(kept_signals, spy, ribbon, vix,
                             strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    m = metrics(rows)
    block = {
        "strike_offset": strike_offset,
        "strike_tier": (f"ITM{abs(strike_offset)}" if strike_offset < 0
                        else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}")),
        "n_signals_kept": len(kept_signals),
        "coverage": cov,
        "metrics": m,
    }
    if base_m and m.get("n"):
        block["vs_baseline"] = {
            "oos_per_trade_lift": round((m.get("oos_exp", 0) or 0) - (base_m.get("oos_exp", 0) or 0), 2),
            "per_trade_lift_all": round((m.get("exp_dollar", 0) or 0) - (base_m.get("exp_dollar", 0) or 0), 2),
            "maxdd_cut": (round((m.get("max_drawdown", 0) or 0) - (base_m.get("max_drawdown", 0) or 0), 2)
                          if (m.get("max_drawdown") is not None and base_m.get("max_drawdown") is not None) else None),
            "oos_total_kept_frac": (round((m.get("oos_total", 0) or 0) / base_m["oos_total"], 3)
                                    if base_m.get("oos_total") else None),
            "total_kept_frac": (round((m.get("total_dollar", 0) or 0) / base_m["total_dollar"], 3)
                                if base_m.get("total_dollar") else None),
        }
    if run_fraud and m.get("n"):
        cs_rows, _ = simulate_set(kept_signals, spy, ribbon, vix,
                                  strike_offset=strike_offset, premium_stop_pct=CHART_STOP_ONLY)
        cs_m = metrics(cs_rows)
        null = run_null(kept_signals, rth, spy, strike_offset=strike_offset,
                        premium_stop_pct=SURV_PREMIUM_STOP)
        block["chartstop_metrics"] = {"n": cs_m.get("n"), "exp_dollar": cs_m.get("exp_dollar"),
                                      "oos_exp": cs_m.get("oos_exp"), "total_dollar": cs_m.get("total_dollar")}
        block["random_null"] = null
        block["gate_eval"] = eval_8_gates(m, cs_m, null)
    return block


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[abstain-gap-atr] loading SPY+VIX via ar_runner.load_data(2025-01-01..2026-05-15) ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[abstain-gap-atr] bars={len(spy)} days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # RTH-only frame for the null (reset index; the null draws random morning bars).
    rth = spy[(spy["t"] >= RTH_OPEN) & (spy["t"] < RTH_CLOSE)].reset_index(drop=True)

    # Detect the vwap_continuation signal set ONCE (byte-for-byte detector, full pattern).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[abstain-gap-atr] signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    # Per-day gap / ATR(14) features (causal).
    gap_atr = build_gap_atr_by_date(days, ATR_PERIOD)
    # Attach each signal's day ratio.
    sig_ratio = {}
    n_ratio_known = 0
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        ratio = gap_atr.get(d, {}).get("gap_atr_ratio")
        sig_ratio[id(sg)] = ratio
        if ratio is not None:
            n_ratio_known += 1
    ratios_only = [r for r in sig_ratio.values() if r is not None]
    print(f"[abstain-gap-atr] gap/ATR known on {n_ratio_known}/{len(signals)} signals "
          f"(NaN during 14d ATR warmup -> KEPT by default); "
          f"ratio median={np.median(ratios_only):.3f} p90={np.percentile(ratios_only,90):.3f} "
          f"max={max(ratios_only):.3f}", flush=True)

    # ── UNGATED BASELINE (both strike tiers) ─────────────────────────────────
    base = {}
    for off, label in ((ITM2_OFFSET, "ITM2"), (OTM2_OFFSET, "OTM2")):
        rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=off,
                                 premium_stop_pct=SURV_PREMIUM_STOP)
        m = metrics(rows)
        cs_rows, _ = simulate_set(signals, spy, ribbon, vix, strike_offset=off,
                                  premium_stop_pct=CHART_STOP_ONLY)
        cs_m = metrics(cs_rows)
        null = run_null(signals, rth, spy, strike_offset=off, premium_stop_pct=SURV_PREMIUM_STOP)
        ge = eval_8_gates(m, cs_m, null)
        base[label] = {"strike_offset": off, "coverage": cov, "metrics": m,
                       "chartstop_metrics": {"exp_dollar": cs_m.get("exp_dollar"),
                                             "oos_exp": cs_m.get("oos_exp")},
                       "random_null": null, "gate_eval": ge}
        print(f"\n[BASELINE ungated {label}] n={m.get('n')} exp=${m.get('exp_dollar')} "
              f"oos_exp=${m.get('oos_exp')} oos_total=${m.get('oos_total')} "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"maxDD=${m.get('max_drawdown')} droptop5=${m.get('drop_top5_day_per_trade')} "
              f"clears8={ge['clears_all_gates']} failed={ge['failed_gates']}", flush=True)

    base_itm_m = base["ITM2"]["metrics"]
    base_otm_m = base["OTM2"]["metrics"]

    # ── ABSTENTION SWEEP: keep signals where |gap| <= N * ATR14 ───────────────
    sweep = []
    for N in GAP_ATR_NS:
        # KEEP rule: ratio is None (warmup, no ATR -> cannot gate) OR ratio <= N.
        kept = [s for s in signals if (sig_ratio[id(s)] is None) or (sig_ratio[id(s)] <= N)]
        skipped = [s for s in signals if (sig_ratio[id(s)] is not None) and (sig_ratio[id(s)] > N)]
        skip_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in skipped})
        print(f"\n--- N={N}: keep |gap|<={N}xATR14 | kept={len(kept)} skipped={len(skipped)} "
              f"(abstains on {skip_days} days) ---", flush=True)
        itm = evaluate_tier(kept, spy, ribbon, vix, rth, base_itm_m,
                            strike_offset=ITM2_OFFSET, run_fraud=True)
        otm = evaluate_tier(kept, spy, ribbon, vix, rth, base_otm_m,
                            strike_offset=OTM2_OFFSET, run_fraud=True)
        for tier, blk, bm in (("ITM2", itm, base_itm_m), ("OTM2", otm, base_otm_m)):
            mm = blk["metrics"]; vb = blk.get("vs_baseline", {}); ge = blk.get("gate_eval", {})
            print(f"  {tier}: kept_n={mm.get('n')} exp=${mm.get('exp_dollar')} "
                  f"oos_exp=${mm.get('oos_exp')} oos_lift=${vb.get('oos_per_trade_lift')} "
                  f"maxDD=${mm.get('max_drawdown')} maxdd_cut=${vb.get('maxdd_cut')} "
                  f"posQ={mm.get('positive_quarters')} top5%={mm.get('top5_day_pct')} "
                  f"clears8={ge.get('clears_all_gates')} failed={ge.get('failed_gates')}", flush=True)
        sweep.append({
            "N": N,
            "keep_rule": f"|opening_gap| <= {N} * ATR(14)",
            "n_signals_kept": len(kept),
            "n_signals_skipped": len(skipped),
            "abstain_days": skip_days,
            "ITM2": itm,
            "OTM2": otm,
        })

    # ── VERDICT: which (N, tier) clears all 8 gates AND beats the subtractive thesis
    #            (OOS lift > 0 AND maxDD cut <= 0 i.e. drawdown reduced)? ───────
    winners = []
    for s in sweep:
        for tier in ("ITM2", "OTM2"):
            blk = s[tier]
            ge = blk.get("gate_eval", {})
            vb = blk.get("vs_baseline", {})
            clears = bool(ge.get("clears_all_gates"))
            oos_lift = vb.get("oos_per_trade_lift")
            maxdd_cut = vb.get("maxdd_cut")  # negative = drawdown got SMALLER (better)
            lift_pos = bool(oos_lift is not None and oos_lift > 0)
            dd_better = bool(maxdd_cut is not None and maxdd_cut >= 0)  # >=0 means dd shallower or equal
            # subtractive thesis = abstention IMPROVES (lift AND dd not worse) on top of clearing gates
            thesis_ok = clears and lift_pos and dd_better
            if thesis_ok:
                winners.append({"N": s["N"], "tier": tier, "oos_lift": oos_lift,
                                "maxdd_cut": maxdd_cut, "oos_exp": blk["metrics"].get("oos_exp")})

    # Headline = best (N, tier) by clears_all_gates then OOS lift (ITM2 primary).
    def _rank_key(s, tier):
        blk = s[tier]; ge = blk.get("gate_eval", {}); vb = blk.get("vs_baseline", {})
        return (1 if ge.get("clears_all_gates") else 0,
                vb.get("oos_per_trade_lift", -9e9) or -9e9)
    ranked = sorted([(s, t) for s in sweep for t in ("ITM2", "OTM2")],
                    key=lambda st: _rank_key(st[0], st[1]), reverse=True)
    best_s, best_t = ranked[0]
    best_blk = best_s[best_t]
    best_ge = best_blk.get("gate_eval", {})

    summary = {
        "study": "abstain_gap_atr (SUBTRACTIVE) — skip vwap_continuation entries on days where "
                 "|opening_gap| > N x ATR(14); does abstaining lift OOS/tr + cut drawdown NET?",
        "kind": "subtractive_abstention",
        "slug": "abstain-gap-atr",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE vwap_continuation (detect_signals imported from "
                     "_edgehunt_vwap_continuation; live port = "
                     "backtest/lib/watchers/vwap_continuation_watcher.py)"),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "survivor_config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                            "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)"},
        "strike_tiers": {"primary": "ITM-2 (strike_offset=-2, survivor structure)",
                         "secondary": "OTM-2 (strike_offset=+2, Safe-2 $2K tier) per C29"},
        "abstention_rule": "KEEP signal iff |opening_gap| <= N*ATR(14); ATR(14) read AS-OF "
                           "the open (prior 14 completed daily bars only — causal, C6).",
        "sweep_N": GAP_ATR_NS,
        "feature_causality": ("opening_gap = RTH_open(d) - RTH_close(d-1) (known at open, before "
                              "the >=bar3/<=10:30 entry); ATR(14) = Wilder daily ATR through day d-1; "
                              "both look-ahead-safe."),
        "8_gates": {
            "g1": "OOS(2026) per-trade > 0",
            "g2": "positive_quarters >= 4/6",
            "g3": "top5_day_pct < 200",
            "g4": "n_trades >= 20",
            "g5": "drop-top5 per-trade > 0",
            "g6": "IS(2025) first-half per-trade > 0",
            "g7": "beats random-entry-null (L172, 20 seeds; null_pass = beat null MAX AND "
                  "drop-top5 beats null MEAN)",
            "g8": "no-truncation (L171): sign holds -8% -> chart-stop-only (-0.99)",
        },
        "subtractive_thesis_metrics": "OOS per-trade LIFT (>0) AND maxDrawdown CUT (dd shallower) "
                                      "vs ungated baseline — the two skip_top_tercile_only delivered.",
        "n_signals": len(signals), "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "feature_coverage": {"gap_atr_known": n_ratio_known, "gap_atr_total": len(signals),
                             "ratio_median": round(float(np.median(ratios_only)), 4),
                             "ratio_p90": round(float(np.percentile(ratios_only, 90)), 4),
                             "ratio_max": round(float(max(ratios_only)), 4)},
        "ungated_baseline": base,
        "abstention_sweep": sweep,
        "winners_clear_8_and_thesis": winners,
        "headline": {
            "N": best_s["N"], "tier": best_t,
            "clears_all_gates": best_ge.get("clears_all_gates"),
            "failed_gates": best_ge.get("failed_gates"),
            "oos_per_trade": best_blk["metrics"].get("oos_exp"),
            "oos_per_trade_lift": best_blk.get("vs_baseline", {}).get("oos_per_trade_lift"),
            "maxdd_cut": best_blk.get("vs_baseline", {}).get("maxdd_cut"),
        },
        "DISCLOSURE": {
            "no_cherry_pick": "every N in {1,1.5,2} reported on BOTH strike tiers with all 8 gate "
                              "booleans + the exact failed gates (anti-pattern 2.10).",
            "net_not_per_trade": "subtractive thesis judged on OOS per-trade LIFT *and* maxDD cut "
                                 "vs ungated baseline AND OOS total P&L kept fraction.",
            "fraud_gates": "random-entry-null (20 seeds, same days/sides, shared null_baseline) + "
                           "no-truncation (sign must hold -8% -> chart-stop-only via L171 guard).",
            "warmup": "first 14 trading days have no ATR(14) -> those signals KEPT by default "
                      "(gate cannot fire); disclosed in feature_coverage.gap_atr_known.",
            "cross_tier": "C29 — ITM-2 (survivor) is PRIMARY; OTM-2 (Safe-2 tier) reported "
                          "independently (gates do not transfer across strike tiers).",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "opra_cutoff": "OPRA cache ends ~2026-05-29; OOS fills = Jan..May 2026; post-cache "
                           "signals drop as cache_miss (coverage.fill_rate).",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[abstain-gap-atr] wrote {OUT}", flush=True)

    print("\n=== ABSTAIN_GAP_ATR VERDICT ===")
    print(f"ungated ITM2: n={base_itm_m.get('n')} oos_exp=${base_itm_m.get('oos_exp')} "
          f"maxDD=${base_itm_m.get('max_drawdown')} clears8={base['ITM2']['gate_eval']['clears_all_gates']}")
    print(f"ungated OTM2: n={base_otm_m.get('n')} oos_exp=${base_otm_m.get('oos_exp')} "
          f"maxDD=${base_otm_m.get('max_drawdown')} clears8={base['OTM2']['gate_eval']['clears_all_gates']}")
    if winners:
        print(f"WINNERS (clear 8 gates AND subtractive thesis): {winners}")
    else:
        print("WINNERS: NONE — no (N,tier) both clears all 8 gates and improves OOS+maxDD; "
              "abstention does not help (leave vwap_continuation ungated on gap-risk days).")
    print(f"headline: N={best_s['N']} {best_t} clears8={best_ge.get('clears_all_gates')} "
          f"failed={best_ge.get('failed_gates')} "
          f"oos_lift=${best_blk.get('vs_baseline', {}).get('oos_per_trade_lift')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
