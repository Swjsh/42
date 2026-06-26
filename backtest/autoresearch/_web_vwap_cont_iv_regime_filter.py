"""WEB-LEARN: vwap_cont_morning_iv_regime_filter — additive intraday-vol gate.

HYPOTHESIS (web-sourced intraday-vol seasonality, the "volatility smile of the day"):
  Within the morning window, vwap_continuation entries taken while the intraday vol
  regime is ELEVATED (open-hour high-IV / wide realized 5m ranges) capture LARGER
  favorable moves for a long option buyer than entries taken once intraday vol has
  already compressed toward the silent/lunch hour. The well-documented U-shaped
  intraday volatility curve (high at the open, troughing ~12:00-13:00 ET, rising into
  the close — Wood/McInish/Ord 1985; Harris 1986; Andersen-Bollerslev 1997 "DM-DEM"
  intraday seasonality; CBOE/Nasdaq "first/last hour" liquidity notes) says realized
  variance is front-loaded. For a LONG 0DTE buyer (long gamma), bar-to-bar realized
  range = the raw material of a favorable excursion; theta is paid regardless. So an
  AS-OF-trigger-time intraday-realized-vol gate SHOULD bias toward the part of the
  morning where the move-per-theta is best.

  TEST AS AN ADDITIVE GATE on the existing #1 vwap_continuation signals, NOT a
  replacement, and NOT a replacement for #4 vix_regime_dayside.

DATA WE HAVE (the binding constraint):
  * SPY 5m bars -> as-of trailing-6-bar realized range proxy (strictly <= trigger-bar
    close, L161/L166 no-look-ahead).
  * VIX 5m level -> as-of entry-bar VIX (we HAVE this).
  Both are computable causally. real OPRA fills via lib.simulator_real, HARD-WINDOW
  <= 2026-05-29 (asserted).

WHAT WE DO NOT HAVE (so we DON'T claim it): real intraday IV / VIX1D / IV-surface.
  The "IV regime" is PROXIED by (a) SPY trailing realized 5m range and (b) VIX 5m
  level. This is disclosed as a proxy (C3/L58: SPY-price vol != option IV).

METHOD:
  1. Detect the SAME morning vwap_continuation signals ONCE (reuse the byte-for-byte
     detector from _edgehunt_vwap_continuation). HARD-WINDOW signals to <= 2026-05-29.
  2. For each signal compute TWO as-of regime proxies at the trigger bar:
       rvol6  = trailing 6-bar (incl. trigger bar) sum/mean of (high-low)/close, %.
                Uses bars STRICTLY up to & including the trigger bar (causal).
       vixlvl = VIX 5m level ffilled onto the trigger bar.
     Also time-of-day (minute-of-RTH) as a cross-check (the curve is a clock effect).
  3. Bucket signals HIGH vs LOW regime by MEDIAN split (disclosed: median is computed
     over the SAME signal population = mild in-sample leakage in the threshold; we
     ALSO report a fixed-clock split 09:35-10:00 vs 10:00-10:30 which has ZERO
     parameter leakage, as the honest robustness check).
  4. Run lib.simulator_real on each bucket at the LIVE headline cells:
       ATM / chart-stop-only  and  ATM / -8% stop  and  ITM-2 / -8% stop.
  5. Measure expectancy DELTA (HIGH - LOW). Gate is additive => we compare GATED
     (HIGH-vol only) vs UNGATED (all morning signals) at the SAME cell.
  6. INDEPENDENCE vs #1's existing gates (L174): #1 already carries a VIX put-slope
     gate. We report the rvol6 gate's effect SEPARATELY from VIX so we can see if it
     is orthogonal or just re-discovering the VIX/clock effect.
  7. NULL (L172): random-entry-time null within the morning window, same N, 200 draws,
     to confirm any HIGH-vol lift beats a same-day random-bar baseline.

This is an ENTRY-candidate-shaping gate (it changes WHICH morning entries we take), so
it must clear the 11-gate bar to be a real edge. Most morning-vol gates DIE on the C3
wall (SPY range != option payoff once theta/delta/stop-misfire are in the real fill).
Name the death honestly.

Pure Python, $0. No live orders. Weekend.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_web_vwap_cont_iv_regime_filter.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals,
    simulate_cell,
    metrics,
    clears_bar,
)
from lib.ribbon import compute_ribbon  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "web-vwap_cont_iv_regime_filter.json"

HARD_WINDOW_END = dt.date(2026, 5, 29)  # OPRA cache cap — HARD assert
RVOL_LOOKBACK = 6                        # trailing 6 bars incl. trigger (causal)
RTH_OPEN_MIN = 9 * 60 + 30
NULL_DRAWS = 200
NULL_SEED = 42

# Headline cells we test the gate on (the LIVE-relevant tiers for edge #1).
CELLS = [
    {"strike_offset": 0, "premium_stop_pct": -0.99, "label": "ATM/chart-stop"},
    {"strike_offset": 0, "premium_stop_pct": -0.08, "label": "ATM/-8%"},
    {"strike_offset": -2, "premium_stop_pct": -0.08, "label": "ITM2/-8%"},
]


def _asof_rvol6(spy: pd.DataFrame, bar_idx: int, day) -> float | None:
    """Trailing RVOL_LOOKBACK-bar mean of (high-low)/close, % — STRICTLY causal.

    Uses only bars at index <= bar_idx that belong to the SAME trading day (no
    cross-day leakage). Returns None if < RVOL_LOOKBACK same-day bars available.
    """
    lo = max(0, bar_idx - 200)
    win = spy.iloc[lo:bar_idx + 1]
    win = win[win["date"] == day]
    if len(win) < RVOL_LOOKBACK:
        return None
    tail = win.iloc[-RVOL_LOOKBACK:]
    rng = (tail["high"].values - tail["low"].values) / tail["close"].values
    return float(np.mean(rng) * 100.0)


def _minute_of_rth(bar) -> int:
    t = bar["timestamp_et"]
    return int(t.hour * 60 + t.minute) - RTH_OPEN_MIN


def _bucket_metrics(signals, spy, ribbon, vix, cell) -> dict:
    rows, cov = simulate_cell(
        signals, spy, ribbon, vix,
        strike_offset=cell["strike_offset"], premium_stop_pct=cell["premium_stop_pct"],
    )
    m = metrics(rows)
    m["_coverage"] = cov
    clears, fails = clears_bar(m)
    m["_clears_bar"] = clears
    m["_clears_bar_fails"] = fails
    return m


def _exp(m: dict) -> float:
    return float(m.get("exp_dollar", 0.0)) if m.get("n") else 0.0


def main() -> int:
    print("[web-iv] loading SPY+VIX ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[web-iv] SPY bars={len(spy)} days={n_days} "
          f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # 1) Detect the SAME morning vwap_continuation signals ONCE (full pattern).
    all_sigs = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)

    # 2) HARD-WINDOW to OPRA cache (assert no signal beyond the cache cap is scored).
    sigs = []
    for s in all_sigs:
        d = spy.iloc[s.bar_idx]["timestamp_et"].date()
        if d <= HARD_WINDOW_END:
            sigs.append(s)
    dropped = len(all_sigs) - len(sigs)
    last_d = max(spy.iloc[s.bar_idx]["timestamp_et"].date() for s in sigs)
    assert last_d <= HARD_WINDOW_END, f"HARD-WINDOW breach: {last_d}"
    print(f"[web-iv] signals={len(all_sigs)} -> {len(sigs)} after HARD-WINDOW "
          f"<= {HARD_WINDOW_END} (dropped {dropped}); last={last_d}", flush=True)

    # 3) Attach as-of regime proxies to each signal.
    enriched = []
    for s in sigs:
        bar = spy.iloc[s.bar_idx]
        d = bar["timestamp_et"].date()
        rv = _asof_rvol6(spy, s.bar_idx, d)
        vl = float(vix.iloc[s.bar_idx]) if s.bar_idx < len(vix) else 0.0
        mr = _minute_of_rth(bar)
        if rv is None:
            continue
        enriched.append((s, rv, vl, mr, d))
    print(f"[web-iv] enriched {len(enriched)} signals with as-of rvol6/vix/minute",
          flush=True)

    rvols = np.array([e[1] for e in enriched])
    vixls = np.array([e[2] for e in enriched])
    rvol_med = float(np.median(rvols))
    vix_med = float(np.median(vixls))
    print(f"[web-iv] rvol6 median={rvol_med:.4f}%  vix median={vix_med:.2f}", flush=True)

    # 4) Define buckets.
    def hi_rvol(e):  # ELEVATED realized range (the hypothesis: better for long buyer)
        return e[1] >= rvol_med

    def hi_vix(e):
        return e[2] >= vix_med

    def early_clock(e):  # 09:35-10:00 = first 25 min of RTH window (the U-curve peak)
        return 0 < e[3] <= 30

    def late_clock(e):   # 10:00-10:30
        return e[3] > 30

    buckets = {
        "all_morning": enriched,
        "rvol_HIGH": [e for e in enriched if hi_rvol(e)],
        "rvol_LOW": [e for e in enriched if not hi_rvol(e)],
        "vix_HIGH": [e for e in enriched if hi_vix(e)],
        "vix_LOW": [e for e in enriched if not hi_vix(e)],
        "clock_EARLY_0935_1000": [e for e in enriched if early_clock(e)],
        "clock_LATE_1000_1030": [e for e in enriched if late_clock(e)],
        # independence cross: HIGH rvol AND LOW vix (orthogonal slice — is rvol adding
        # anything once vix is held low, i.e. NOT just re-discovering VIX?)
        "rvolHIGH_x_vixLOW": [e for e in enriched if hi_rvol(e) and not hi_vix(e)],
        "rvolLOW_x_vixLOW": [e for e in enriched if not hi_rvol(e) and not hi_vix(e)],
    }

    # 5) Run the sim per bucket per cell.
    results = {}
    for cell in CELLS:
        cl = cell["label"]
        results[cl] = {}
        for bname, blist in buckets.items():
            sub = [e[0] for e in blist]
            m = _bucket_metrics(sub, spy, ribbon, vix, cell) if sub else {"n": 0}
            results[cl][bname] = m
            print(f"  [{cl:>14}] {bname:>22}: n={m.get('n','-'):>3} "
                  f"exp=${_exp(m):>7.2f} oos_exp=${m.get('oos_exp','-')} "
                  f"oos_n={m.get('oos_n','-')} posQ={m.get('positive_quarters','-')} "
                  f"top5%={m.get('top5_day_pct','-')} "
                  f"{'CLEARS' if m.get('_clears_bar') else ''}", flush=True)

    # 6) Gate effect: GATED (rvol_HIGH only) vs UNGATED (all_morning) per cell.
    gate_effect = {}
    for cell in CELLS:
        cl = cell["label"]
        ung = results[cl]["all_morning"]
        gat = results[cl]["rvol_HIGH"]
        lo = results[cl]["rvol_LOW"]
        gate_effect[cl] = {
            "ungated_n": ung.get("n", 0), "ungated_exp": _exp(ung),
            "ungated_oos_exp": ung.get("oos_exp"),
            "gated_rvolHIGH_n": gat.get("n", 0), "gated_rvolHIGH_exp": _exp(gat),
            "gated_rvolHIGH_oos_exp": gat.get("oos_exp"),
            "rvolLOW_n": lo.get("n", 0), "rvolLOW_exp": _exp(lo),
            "rvolLOW_oos_exp": lo.get("oos_exp"),
            "exp_delta_HIGH_minus_LOW": round(_exp(gat) - _exp(lo), 2),
            "exp_delta_GATED_minus_UNGATED": round(_exp(gat) - _exp(ung), 2),
            "oos_delta_HIGH_minus_LOW": (
                round((gat.get("oos_exp") or 0) - (lo.get("oos_exp") or 0), 2)
            ),
        }

    # 7) Independence vs #1's VIX gate: is rvol_HIGH's lift present when VIX is LOW?
    independence = {}
    for cell in CELLS:
        cl = cell["label"]
        hxl = results[cl]["rvolHIGH_x_vixLOW"]
        lxl = results[cl]["rvolLOW_x_vixLOW"]
        independence[cl] = {
            "rvolHIGH_x_vixLOW_n": hxl.get("n", 0), "rvolHIGH_x_vixLOW_exp": _exp(hxl),
            "rvolLOW_x_vixLOW_n": lxl.get("n", 0), "rvolLOW_x_vixLOW_exp": _exp(lxl),
            "orthogonal_exp_delta": round(_exp(hxl) - _exp(lxl), 2),
            "verdict": (
                "rvol adds within low-VIX (orthogonal)"
                if _exp(hxl) - _exp(lxl) > 0 and hxl.get("n", 0) >= 15
                else "rvol does NOT add orthogonally (collinear w/ VIX or too few)"
            ),
        }

    # 8) Random-entry-time NULL (L172): for each signal-day, draw a random morning bar
    #    (09:35-10:30) instead of the actual trigger bar; same N days; 200 draws; the
    #    distribution of the rvol_HIGH-equivalent gate's expectancy. We test whether the
    #    rvol_HIGH GATED expectancy beats the null of "high-vol morning bar, any entry".
    #    Use the headline ATM/-8% cell.
    null_cell = CELLS[1]  # ATM/-8%
    rng = np.random.default_rng(NULL_SEED)
    # candidate morning bars per day (09:35-10:30), with as-of rvol attached
    day_bars: dict = defaultdict(list)
    for i in range(len(spy)):
        bar = spy.iloc[i]
        d = bar["date"]
        if d > HARD_WINDOW_END:
            continue
        mr = int(bar["timestamp_et"].hour * 60 + bar["timestamp_et"].minute) - RTH_OPEN_MIN
        if 0 < mr <= 60:  # 09:35..10:30
            day_bars[d].append(i)
    # actual gated (rvol_HIGH) expectancy on ATM/-8%
    actual_gated_exp = _exp(results[null_cell["label"]]["rvol_HIGH"])
    actual_gated_n = results[null_cell["label"]]["rvol_HIGH"].get("n", 0)
    gated_days = sorted({e[4] for e in buckets["rvol_HIGH"]})

    from autoresearch.infinite_ammo_discovery import Signal as _Sig
    null_exps = []
    for _ in range(NULL_DRAWS):
        nsig = []
        for d in gated_days:
            cands = day_bars.get(d, [])
            if not cands:
                continue
            bi = int(rng.choice(cands))
            # reconstruct a plausible chart stop (session extreme to entry) so the sim
            # has a rejection_level; use same-day RTH low (call) — but we don't know the
            # side at a random bar, so mirror the actual signal's side for that day.
            day_sig = next((e[0] for e in buckets["rvol_HIGH"] if e[4] == d), None)
            if day_sig is None:
                continue
            side = day_sig.side
            lo_idx = max(0, bi - 80)
            seg = spy.iloc[lo_idx:bi + 1]
            seg = seg[seg["date"] == d]
            if seg.empty:
                continue
            stop = float(seg["low"].min()) if side == "C" else float(seg["high"].max())
            nsig.append(_Sig(bar_idx=bi, side=side, stop_level=stop, note="null"))
        rows, _ = simulate_cell(nsig, spy, ribbon, vix,
                                strike_offset=null_cell["strike_offset"],
                                premium_stop_pct=null_cell["premium_stop_pct"])
        m = metrics(rows)
        null_exps.append(_exp(m))
    null_exps = np.array(null_exps)
    null_mean = float(np.mean(null_exps))
    null_p95 = float(np.percentile(null_exps, 95))
    # one-sided p: fraction of null draws >= actual gated expectancy
    null_p = float(np.mean(null_exps >= actual_gated_exp))
    print(f"\n[web-iv] NULL (ATM/-8%, rvol_HIGH days, {NULL_DRAWS} draws): "
          f"actual_gated_exp=${actual_gated_exp:.2f} (n={actual_gated_n}) "
          f"null_mean=${null_mean:.2f} null_p95=${null_p95:.2f} "
          f"beats-null p={null_p:.3f}", flush=True)

    # Verdict.
    best_cell = None
    for cell in CELLS:
        cl = cell["label"]
        gat = results[cl]["rvol_HIGH"]
        ge = gate_effect[cl]
        # a real edge would need: gated clears bar AND gated > ungated AND HIGH > LOW
        passes = (
            gat.get("_clears_bar", False)
            and ge["exp_delta_GATED_minus_UNGATED"] > 0
            and ge["exp_delta_HIGH_minus_LOW"] > 0
        )
        if passes:
            best_cell = cl

    verdict = "DEAD"
    if best_cell:
        # additionally require independence + beats null
        indep_ok = independence[best_cell]["orthogonal_exp_delta"] > 0
        null_ok = null_p < 0.05
        if indep_ok and null_ok:
            verdict = "LEAD"  # additive gate shows promise; needs full 11-gate ratify
        else:
            verdict = "DEAD"

    summary = {
        "slug": "vwap_cont_morning_iv_regime_filter",
        "kind": "entry_candidate_shaping_gate (additive to #1 vwap_continuation)",
        "run_date": dt.date.today().isoformat(),
        "hypothesis": ("morning vwap_continuation entries in an ELEVATED intraday-vol "
                       "regime (high trailing SPY 5m realized range / higher VIX level, "
                       "both as-of trigger time) capture larger favorable moves for a "
                       "long 0DTE buyer than entries once intraday vol has compressed"),
        "web_basis": ("U-shaped intraday volatility curve: Wood/McInish/Ord (1985) "
                      "JF; Harris (1986) JFE; Andersen-Bollerslev (1997) intraday "
                      "seasonality; CBOE/Nasdaq first/last-hour liquidity notes. "
                      "Realized variance is front-loaded; long gamma wants range."),
        "data_window": (f"{spy['timestamp_et'].iloc[0].date()}.."
                        f"{spy['timestamp_et'].iloc[-1].date()} SPY/VIX; real OPRA "
                        f"fills HARD-WINDOW <= {HARD_WINDOW_END} (asserted)"),
        "proxy_disclosure": ("'IV regime' is PROXIED by SPY trailing-6-bar realized 5m "
                             "range (%) + VIX 5m level — we do NOT have intraday IV / "
                             "VIX1D / IV-surface history. SPY-price vol != option IV "
                             "(C3/L58); a SPY-range gate may not survive on real fills."),
        "causality": ("rvol6 uses bars STRICTLY <= trigger bar, same trading day only "
                      "(L161/L166); VIX ffilled as-of entry bar; entry next-bar-open"),
        "n_signals_raw": len(all_sigs),
        "n_signals_in_window": len(sigs),
        "n_enriched": len(enriched),
        "rvol6_median_pct": round(rvol_med, 4),
        "vix_median": round(vix_med, 2),
        "cells_tested": CELLS,
        "bucket_results": results,
        "gate_effect_gated_vs_ungated": gate_effect,
        "independence_vs_vix_gate_L174": independence,
        "random_entry_null_L172": {
            "cell": null_cell["label"], "draws": NULL_DRAWS, "seed": NULL_SEED,
            "actual_gated_exp": round(actual_gated_exp, 2),
            "actual_gated_n": actual_gated_n,
            "null_mean_exp": round(null_mean, 2),
            "null_p95_exp": round(null_p95, 2),
            "beats_null_p_value": round(null_p, 3),
            "beats_null": null_p < 0.05,
            "interpretation": ("p = fraction of random-morning-entry draws whose "
                               "expectancy >= the actual rvol_HIGH gated expectancy; "
                               "p<0.05 = the gate's selection beats picking a random "
                               "high-vol-day morning bar"),
        },
        "verdict": verdict,
        "verdict_rule": ("LEAD requires: gated cell clears 11-gate candidate bar AND "
                         "gated_exp>ungated_exp AND HIGH>LOW AND orthogonal-to-VIX "
                         "(rvolHIGH_x_vixLOW > rvolLOW_x_vixLOW) AND beats random null "
                         "(p<0.05). Anything less = DEAD (gate adds no real-fill edge)."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[web-iv] wrote {OUT}", flush=True)
    print(f"[web-iv] VERDICT = {verdict}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
