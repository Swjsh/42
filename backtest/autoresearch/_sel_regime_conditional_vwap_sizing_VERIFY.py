"""ADVERSARIAL INDEPENDENT re-verification of sel-regime_conditional_vwap_sizing.

Separate from the candidate's own _sel_regime_conditional_vwap_sizing.py. We REUSE only the
two trustable primitives (the validated vwap_continuation detector, vendored byte-for-byte;
and lib.simulator_real.simulate_trade_real, the C1 real-OPRA WR authority). EVERYTHING else
-- causal expanding-window VIX median + top-tercile skip, integer-multiple sizing, IS/OOS
split, quarter split, top-5-day concentration, drop-top-5-days, random-entry null, chart-
stop-only no-truncation sign check -- is re-implemented FRESH so the gates are recomputed
from scratch, not trusted.

Causal regime thresholds match the candidate EXACTLY so we test the SAME claim:
  median  = np.median(prior_vix)             (warmup 8 prior fills, else base qty)
  hi_terc = np.percentile(prior_vix, 200/3)
  schedule '2x_below_skip_top_tercile':
    this_vix > hi_terc  -> SKIP (qty 0)
    this_vix <= median  -> qty 6 (2x base, EXACT per-qty sim)
    else                -> qty 3 (base)
  prior_vix is updated with this trade's entry VIX AFTER the decision (no look-ahead).

Confirm ONLY if ALL hold for the headline schedule:
  OOS(2026)/trade>0 AND IS(2025)/trade>0 AND positive_quarters>=4/6 AND top5_day<200%
  AND n>=20 REAL fills AND drop-top-5-days total>0 AND beats 20-seed random-entry null
  AND sign does NOT invert at chart-stop-only.

Writes analysis/recommendations/sel-regime_conditional_vwap_sizing.VERIFY.json
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sel_regime_conditional_vwap_sizing_VERIFY.py
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
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sel-regime_conditional_vwap_sizing.VERIFY.json"

TREND_BARS = 3
ENTRY_CUTOFF = dt.time(10, 30)
SHALLOW_DIP_TOL = 0.0010
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
MAX_STRIKE_STEPS = 4

STRIKE_OFFSET = -2
PREMIUM_STOP_PCT = -0.08
BASE_QTY = 3
UP_QTY = 6
WARMUP = 8
OOS_YEAR = 2026
N_NULL_SEEDS = 20
BAR_N = 20
BAR_TOP5 = 200.0
BAR_POS_Q = 4


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


@dataclass
class Fill:
    date: str
    side: str
    entry_vix: float
    pnl_base: float
    pnl_up: float
    ok: bool


def simulate_all(signals, spy, vix, *, premium_stop_pct, ribbon_df=None) -> list[Fill]:
    fills: list[Fill] = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - STRIKE_OFFSET if sg.side == "P" else atm + STRIKE_OFFSET
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            fills.append(Fill(str(d), sg.side, 0.0, 0.0, 0.0, ok=False))
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0

        def _sim(qty):
            return simulate_trade_real(
                entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon_df,
                rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
                qty=qty, setup="SEL_REGIME_VWAP", strike_override=strike, entry_vix=entry_vix,
                premium_stop_pct=premium_stop_pct)

        f3 = _sim(BASE_QTY)
        f6 = _sim(UP_QTY)
        if (f3 is None or f3.dollar_pnl is None or f6 is None or f6.dollar_pnl is None):
            fills.append(Fill(str(d), sg.side, entry_vix, 0.0, 0.0, ok=False))
            continue
        fills.append(Fill(str(d), sg.side, entry_vix,
                          round(float(f3.dollar_pnl), 2), round(float(f6.dollar_pnl), 2), ok=True))
    return fills


def apply_schedule(fills: list[Fill], schedule: str):
    prior_vix: list[float] = []
    sized = []
    for f in fills:
        if not f.ok:
            continue
        v = f.entry_vix
        med = float(np.median(prior_vix)) if len(prior_vix) >= WARMUP else None
        hi = float(np.percentile(prior_vix, 200.0 / 3.0)) if len(prior_vix) >= WARMUP else None
        if schedule == "flat":
            qty = BASE_QTY
        elif schedule == "2x_below_median":
            qty = UP_QTY if (med is not None and v <= med) else BASE_QTY
        elif schedule == "skip_top_tercile_only":
            qty = 0 if (hi is not None and v > hi) else BASE_QTY
        elif schedule == "2x_below_skip_top_tercile":
            if hi is not None and v > hi:
                qty = 0
            elif med is not None and v <= med:
                qty = UP_QTY
            else:
                qty = BASE_QTY
        else:
            raise ValueError(schedule)
        prior_vix.append(v)  # causal: AFTER decision
        if qty == 0:
            continue
        pnl = f.pnl_base if qty == BASE_QTY else f.pnl_up
        sized.append({"date": f.date, "side": f.side, "pnl": pnl, "qty": qty})
    return sized


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r["pnl"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    by_q = defaultdict(list)
    for r in rows:
        by_q[_quarter(r["date"])].append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    total = sum(by_day.values())
    days_sorted = sorted(by_day.values(), reverse=True)
    top5_total = sum(days_sorted[:5])
    top5_pct = round(100 * top5_total / total, 1) if total > 0 else None
    drop_top5 = round(total - top5_total, 2)
    return {
        "n": n, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2), "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows),
        "is_exp": round(float(np.mean([r["pnl"] for r in is_rows])), 2) if is_rows else 0.0,
        "oos_n": len(oos_rows),
        "oos_exp": round(float(np.mean([r["pnl"] for r in oos_rows])), 2) if oos_rows else 0.0,
        "quarters": quarters, "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "top5_day_pct": top5_pct,
        "drop_top5_days_total": drop_top5,
    }


def random_null(sized, spy, vix, *, premium_stop_pct, seeds):
    rth_mask = (spy["t"] >= dt.time(9, 35)) & (spy["t"] <= ENTRY_CUTOFF)
    pool_idx = spy.index[rth_mask].tolist()
    real_total = sum(r["pnl"] for r in sized)
    null_totals = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        tot = 0.0
        for r in sized:
            side, qty = r["side"], r["qty"]
            for _ in range(8):
                bi = int(rng.choice(pool_idx))
                bar = spy.iloc[bi]
                d = bar["timestamp_et"].date()
                spot = float(bar["close"])
                atm = _strike_from_spot(spot)
                target = atm - STRIKE_OFFSET if side == "P" else atm + STRIKE_OFFSET
                strike = _nearest_cached_strike(d, target, side, MAX_STRIKE_STEPS)
                if strike is None:
                    continue
                evix = float(vix.iloc[bi]) if bi < len(vix) else 0.0
                rej = spot * (0.99 if side == "C" else 1.01)
                f = simulate_trade_real(
                    entry_bar_idx=bi, entry_bar=bar, spy_df=spy, ribbon_df=None,
                    rejection_level=rej, triggers_fired=["null"], side=side, qty=qty,
                    setup="SEL_NULL", strike_override=strike, entry_vix=evix,
                    premium_stop_pct=premium_stop_pct)
                if f is not None and f.dollar_pnl is not None:
                    tot += float(f.dollar_pnl)
                    break
        null_totals.append(tot)
    null_totals = np.array(null_totals, float)
    return {
        "real_total": round(real_total, 2),
        "null_mean_total": round(float(null_totals.mean()), 2),
        "null_std_total": round(float(null_totals.std()), 2),
        "real_minus_null_mean": round(real_total - float(null_totals.mean()), 2),
        "real_pctile_vs_null": round(float((real_total > null_totals).mean()) * 100, 1),
        "beats_null": bool(real_total > float(null_totals.mean())),
        "seeds": seeds,
    }


def main() -> int:
    print("[verify] loading SPY+VIX 2025-01-01..2026-05-15 ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[verify] signals={len(signals)} on {sig_days} days", flush=True)

    ribbon_df = None
    if "--ribbon" in sys.argv:
        from lib.ribbon import compute_ribbon
        ribbon_df = compute_ribbon(pd.Series(spy["close"].values))
        print("[verify] ribbon ENABLED (mirror candidate v15 ribbon-flip exits)", flush=True)
    fills = simulate_all(signals, spy, vix, premium_stop_pct=PREMIUM_STOP_PCT, ribbon_df=ribbon_df)
    n_ok = sum(1 for f in fills if f.ok)
    print(f"[verify] real OPRA fills (both qtys): {n_ok}/{len(fills)}", flush=True)
    fills_cs = simulate_all(signals, spy, vix, premium_stop_pct=-0.99, ribbon_df=ribbon_df)

    schedules = ["flat", "2x_below_median", "skip_top_tercile_only", "2x_below_skip_top_tercile"]
    results = {}
    for sch in schedules:
        sized = apply_schedule(fills, sch)
        m = metrics(sized)
        sized_cs = apply_schedule(fills_cs, sch)
        m_cs = metrics(sized_cs)
        null = None
        if sch == "2x_below_skip_top_tercile":
            null = random_null(sized, spy, vix, premium_stop_pct=PREMIUM_STOP_PCT, seeds=N_NULL_SEEDS)
        gate_oos = m.get("oos_exp", -1) > 0
        gate_is = m.get("is_exp", -1) > 0
        gate_posq = m.get("positive_quarters_n", 0) >= BAR_POS_Q
        t5 = m.get("top5_day_pct")
        gate_top5 = (t5 is not None and t5 < BAR_TOP5)
        gate_n = m.get("n", 0) >= BAR_N
        gate_droptop5 = m.get("drop_top5_days_total", -1) > 0
        gate_null = (null["beats_null"] if null else None)
        rt = m.get("total_dollar", 0.0)
        ct = m_cs.get("total_dollar", 0.0)
        gate_trunc = (rt > 0 and ct > 0) or (rt < 0 and ct < 0)
        gates = {
            "oos_per_trade_positive": bool(gate_oos),
            "is_half_positive": bool(gate_is),
            "positive_quarters_ge_4": bool(gate_posq),
            "top5_day_lt_200": bool(gate_top5),
            "n_ge_20": bool(gate_n),
            "drop_top5_days_positive": bool(gate_droptop5),
            "beats_random_null": (bool(gate_null) if gate_null is not None else "not_run"),
            "truncation_safe": bool(gate_trunc),
        }
        required = [gate_oos, gate_is, gate_posq, gate_top5, gate_n, gate_droptop5, gate_trunc]
        if null is not None:
            required.append(gate_null)
        clears = all(required)
        results[sch] = {
            "metrics": m, "chartstop_total_dollar": m_cs.get("total_dollar"),
            "chartstop_oos_exp": m_cs.get("oos_exp"), "null": null,
            "gates": gates, "clears_all_gates": bool(clears),
        }
        print(f"[verify] {sch}: n={m.get('n')} exp=${m.get('exp_dollar')} "
              f"is_exp=${m.get('is_exp')} oos_exp=${m.get('oos_exp')} (oos_n={m.get('oos_n')}) "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"droptop5=${m.get('drop_top5_days_total')} cs_total=${m_cs.get('total_dollar')} "
              f"clears={clears}", flush=True)

    head = results["2x_below_skip_top_tercile"]
    confirmed = head["clears_all_gates"]
    out = {
        "hypothesis": "regime_conditional_vwap_sizing",
        "config": "2x_below_skip_top_tercile",
        "verification": "INDEPENDENT adversarial re-run (separate script + fresh gate code)",
        "run_date": dt.date.today().isoformat(),
        "window": "2025-01-02..2026-05-15",
        "survivor_structure": {"strike_offset": STRIKE_OFFSET, "premium_stop_pct": PREMIUM_STOP_PCT,
                               "base_qty": BASE_QTY, "up_qty": UP_QTY, "warmup": WARMUP},
        "n_signals": len(signals), "real_fills_both_qtys": n_ok,
        "schedules": results,
        "headline_oos_exp": head["metrics"].get("oos_exp"),
        "headline_oos_n": head["metrics"].get("oos_n"),
        "headline_n": head["metrics"].get("n"),
        "confirmed": bool(confirmed),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[verify] wrote {OUT}", flush=True)
    print(f"[verify] CONFIRMED={confirmed} headline oos_exp=${head['metrics'].get('oos_exp')} "
          f"oos_n={head['metrics'].get('oos_n')} n={head['metrics'].get('n')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
