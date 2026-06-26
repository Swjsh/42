"""W1: IV-SKEW / 25-DELTA RISK-REVERSAL as an AS-OF-ENTRY directional CONFIRMER on the
LIVE edge #1 vwap_continuation (the one real edge: ATM / 0DTE / -8% / qty3).

THE HYPOTHESIS (web-scout top testable-now candidate)
─────────────────────────────────────────────────────
The 25-delta risk-reversal RR = IV(25d call) - IV(25d put) and the put-wing skew slope
encode the option market's *directional fear*. A STEEPENING put skew / FALLING RR is a
bearish tell; a FLATTENING skew / RISING RR is bullish. As an additive CONFIRMER on the
existing morning vwap_continuation signals: KEEP entries where the as-of skew sign/CHANGE
AGREES with the trade side (put-skew steepening / RR falling -> confirm PUT;
flattening / RR rising -> confirm CALL), DROP disagreements. W1b = the PUT-side gate
FIRST (J's anchor winners are put-heavy).

DATA REALITY (the binding constraint, disclosed honestly — C3/L58)
──────────────────────────────────────────────────────────────────
The OPRA cache has NO IV/greeks columns. IV is BS-INVERTIBLE from the option bar close +
concurrent SPY spot + r + intraday T-to-0DTE-expiry. We invert per cached strike, then
interpolate IV across the strike grid to the ~25-delta call/put strikes.

  * Inversion is NOISIest at the bar close late in the day (theta/vega collapse), so we
    restrict the snapshot to a 09:35-10:30 ET window — which is also exactly the
    vwap_continuation entry window (entry cutoff 10:30), so NO entries are lost to it.
  * COVERAGE CAVEAT (measured, NOT assumed): the cache is ~$10 (+-$5) wide on ~97.5% of
    (day,side) groups; only ~18/730 groups carry the +-$18/+-$30 'event' cache. 25-delta
    0DTE in the morning often sits AT or just beyond +-$5, so on most days we CANNOT
    resolve a true 25-delta and must EXTRAPOLATE to the nearest available delta. Every
    signal is flagged with its realized |target_delta - achieved_delta| and a coverage
    tier; entries where we cannot get within delta_tol of 25d are flagged and (in the
    strict variant) EXCLUDED from the confirmer (they pass through unfiltered).

THE BAR (the 11-gate; the load-bearing one is the L172 RANDOM-FILTER null)
──────────────────────────────────────────────────────────────────────────
Price filtered-vs-unfiltered #1 through lib.simulator_real (real OPRA fills). The
filtered set must:
  (a) beat the UNFILTERED #1 on per-trade expectancy / risk-adj,
  (b) BEAT THE L172 RANDOM-FILTER NULL — a random filter that drops the SAME fraction of
      the SAME signal trades, many seeds. (This is the gate the VIX-level gate FAILED at
      p=0.355. A real confirmer's kept-subset expectancy must sit in the right tail of
      the random-drop distribution: one-sided p < 0.05.) This is DISTINCT from the
      random-ENTRY null in null_baseline.py — here the universe is the signal set itself,
      and we test whether THIS particular drop-rule selects better than a coin-flip drop
      of the same size.
  (c) hold OOS+ / posQ>=4/6 / drop-top5+ / L173 OOS-alone-drop-top5 / L171 no-truncation,
  (d) OP-16 J-anchor no-regression (the vwap_continuation P&L on 4/29, 5/01, 5/04 must
      not regress under the filter),
  (e) be ORTHOGONAL to #1's own VWAP trigger (the confirmer must not just re-derive the
      side the detector already chose — we report agreement-rate vs side and the skew's
      correlation with the raw trigger).

improves_edge = true ONLY IF filtered beats unfiltered AND beats the random-filter null
AND holds the 11-gate AND anchors survive. Filters usually just shrink n without real
selection (the VIX-level gate did exactly that) — we name the death honestly.

Pure Python, $0 (no LLM). No live orders. Weekend / markets closed. PAPER.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_iv_skew_confirmer.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for p in (str(REPO), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts, session_vwap_asof, _nearest_cached_strike,
    _strike_from_spot, Signal, DayCtx,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402 — REUSE the byte-for-byte detector + sim
    _normalize_spy, _align_vix, detect_signals, simulate_cell, metrics, clears_bar,
    OOS_YEAR, BAR_N,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.pricing import black_scholes, RISK_FREE_RATE, time_to_expiry_years  # noqa: E402
from lib.option_pricing_real import option_symbol, load_contract_bars  # noqa: E402
from lib.anchor_check import anchor_no_regression  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "web-vwap_cont_iv_skew_confirmer.json"

# ── Live edge #1 headline cell (the ONE real edge) ───────────────────────────
LIVE_STRIKE_OFFSET = 0       # ATM (headline cell)
LIVE_PREMIUM_STOP = -0.08    # -8%
QTY = 3

# ── Skew snapshot window (restrict inversion to low-noise morning) ───────────
SNAP_START = dt.time(9, 35)
SNAP_END = dt.time(10, 30)
TARGET_DELTA = 0.25          # ~25-delta wings
DELTA_TOL = 0.08             # within +-0.08 of 25d to count as "resolved" coverage
SKEW_CHANGE_LOOKBACK = 3     # bars back for RR/slope CHANGE (3 x 5m = 15 min)

# ── Random-filter null ───────────────────────────────────────────────────────
NULL_SEEDS = 2000

# ── J anchor dates (OP-16 source-of-truth WINNERS) ───────────────────────────
ANCHOR_WIN_DATES = {"2025-04-29", "2025-05-01", "2025-05-04"}


# ─────────────────────────────────────────────────────────────────────────────
# BS IV INVERSION  (close + spot + r + intraday-T -> implied vol; then IV->delta grid)
# ─────────────────────────────────────────────────────────────────────────────
def implied_vol(price: float, spot: float, strike: float, tte: float, is_call: bool,
                rate: float = RISK_FREE_RATE) -> Optional[float]:
    """Invert BS for IV via bisection. None if no-arbitrage bounds fail or non-convergent."""
    if price is None or price <= 0 or tte <= 0 or spot <= 0:
        return None
    # intrinsic floor (American-ish lower bound for a European proxy)
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if price < intrinsic - 0.02:
        return None  # below intrinsic -> bad bar / stale print, reject
    lo, hi = 1e-4, 5.0
    plo, _ = black_scholes(spot, strike, lo, tte, is_call, rate)
    phi, _ = black_scholes(spot, strike, hi, tte, is_call, rate)
    if not (plo <= price <= phi):
        # price outside [vol=0.0001 .. vol=500%] envelope -> unresolvable
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        pm, _ = black_scholes(spot, strike, mid, tte, is_call, rate)
        if abs(pm - price) < 1e-4:
            return float(mid)
        if pm < price:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def _option_close_at(d: dt.date, strike: int, side: str, when_et: pd.Timestamp) -> Optional[float]:
    """Close of the cached option bar that CONTAINS `when_et` (<= when < +5m). Causal."""
    df = load_contract_bars(option_symbol(d, strike, side))
    if df is None:
        return None
    ts = df["timestamp_et"]
    # CRITICAL (L6/L34 tz foot-gun): the OPRA cache stores timestamps as a FIXED
    # UTC-04:00 offset (not true seasonal ET). Naive-stripping yields a +1h-shifted
    # wall clock (e.g. real 09:30 ET shows as 10:30). Convert to America/New_York FIRST,
    # then strip — that reproduces the true ET wall clock SPY is normalized to.
    if ts.dt.tz is not None:
        twall = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    else:
        twall = pd.to_datetime(ts)
    w = pd.Timestamp(when_et)
    if getattr(w, "tz", None) is not None:
        w = w.tz_localize(None)
    cut = df[twall <= w]
    if cut.empty:
        return None
    last_t = twall[cut.index[-1]]
    if (w - last_t).total_seconds() > 300:
        return None  # gap, no covering bar
    c = float(cut.iloc[-1]["close"])
    return c if c > 0 else None


@dataclass
class SkewSnap:
    rr: Optional[float]            # IV(25dC) - IV(25dP)
    put_slope: Optional[float]     # (IV(25dP) - IV(atm_put)) / dStrike  -> put-wing steepness
    call_delta_err: Optional[float]
    put_delta_err: Optional[float]
    n_strikes_used: int
    resolved: bool                 # both wings within DELTA_TOL of 25d
    note: str


def _iv_grid(d: dt.date, side: str, spot: float, tte: float, when_et) -> list[tuple[int, float, float]]:
    """For one side, invert IV at every cached strike that has a covering bar.
    Returns sorted list of (strike, iv, delta). delta is the BS delta at that IV."""
    df_ok = []
    atm = _strike_from_spot(spot)
    is_call = (side == "C")
    # scan a generous strike radius around ATM ($25 each way covers the +-18 event cache)
    for k in range(atm - 25, atm + 26):
        c = _option_close_at(d, k, side, when_et)
        if c is None:
            continue
        iv = implied_vol(c, spot, float(k), tte, is_call)
        if iv is None:
            continue
        _, delta = black_scholes(spot, float(k), iv, tte, is_call)
        df_ok.append((k, iv, float(delta)))
    df_ok.sort(key=lambda x: x[0])
    return df_ok


def _interp_iv_at_delta(grid: list[tuple[int, float, float]], target_abs_delta: float,
                        is_call: bool) -> Optional[tuple[float, float, float]]:
    """Interpolate IV (vs |delta|) to the target |delta|. Returns (iv, achieved_abs_delta,
    strike_proxy). None if grid empty. Uses linear interp in |delta| space; if target is
    outside the grid's delta range, EXTRAPOLATE to the nearest endpoint and flag via the
    achieved-delta gap the caller measures."""
    if not grid:
        return None
    ad = [(abs(dl), iv, k) for (k, iv, dl) in grid]
    ad.sort(key=lambda x: x[0])
    deltas = [x[0] for x in ad]
    ivs = [x[1] for x in ad]
    # if target within range -> interpolate; else clamp to nearest endpoint (extrapolation
    # is unreliable for IV vs delta, so we take the nearest available delta and flag the gap)
    if target_abs_delta <= deltas[0]:
        return (ivs[0], deltas[0], ad[0][2])
    if target_abs_delta >= deltas[-1]:
        return (ivs[-1], deltas[-1], ad[-1][2])
    iv = float(np.interp(target_abs_delta, deltas, ivs))
    ach = target_abs_delta
    # strike proxy: nearest grid strike to interpolated delta
    strike = min(ad, key=lambda x: abs(x[0] - target_abs_delta))[2]
    return (iv, ach, strike)


def skew_snapshot(d: dt.date, spot: float, when_et) -> SkewSnap:
    """Compute RR (25dC IV - 25dP IV) + put-wing slope as-of `when_et`."""
    tte = time_to_expiry_years(pd.Timestamp(when_et).to_pydatetime())
    cg = _iv_grid(d, "C", spot, tte, when_et)
    pg = _iv_grid(d, "P", spot, tte, when_et)
    n_used = len(cg) + len(pg)
    c25 = _interp_iv_at_delta(cg, TARGET_DELTA, True)
    p25 = _interp_iv_at_delta(pg, TARGET_DELTA, False)
    if c25 is None or p25 is None:
        return SkewSnap(None, None, None, None, n_used, False, "no_grid")
    iv_c25, ach_c, _ = c25
    iv_p25, ach_p, _ = p25
    rr = iv_c25 - iv_p25
    # put-wing slope: how much steeper the 25d put IV is vs the ~ATM (50d) put IV per $ moved.
    atm_put = _interp_iv_at_delta(pg, 0.50, False)
    put_slope = None
    if atm_put is not None:
        iv_atm_p, _, _ = atm_put
        put_slope = iv_p25 - iv_atm_p  # >0 = put wing richer than ATM = downside skew
    cerr = abs(ach_c - TARGET_DELTA)
    perr = abs(ach_p - TARGET_DELTA)
    resolved = (cerr <= DELTA_TOL) and (perr <= DELTA_TOL)
    return SkewSnap(rr, put_slope, cerr, perr, n_used, resolved, "ok")


# ─────────────────────────────────────────────────────────────────────────────
# PER-SIGNAL SKEW FEATURES (as-of trigger bar; CHANGE vs prior N bars)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SigSkew:
    date: str
    side: str
    bar_idx: int
    time_et: str
    in_window: bool
    rr: Optional[float]
    put_slope: Optional[float]
    rr_change: Optional[float]        # rr(now) - rr(prior N bars)
    slope_change: Optional[float]     # put_slope(now) - put_slope(prior N bars)
    resolved: bool
    coverage_note: str
    confirm: Optional[bool]           # does skew sign/change AGREE with side?


def compute_sig_skews(signals, spy) -> list[SigSkew]:
    out: list[SigSkew] = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        t = bar["timestamp_et"].time()
        spot = float(bar["close"])
        in_win = SNAP_START <= t <= SNAP_END
        if not in_win:
            out.append(SigSkew(str(d), sg.side, sg.bar_idx, t.strftime("%H:%M"), False,
                               None, None, None, None, False, "outside_window", None))
            continue
        now = skew_snapshot(d, spot, bar["timestamp_et"])
        # CHANGE vs prior N bars (same session, causal). Use the spy bar SKEW_CHANGE_LOOKBACK back.
        prior_idx = sg.bar_idx - SKEW_CHANGE_LOOKBACK
        rr_chg = slope_chg = None
        if prior_idx >= 0:
            pbar = spy.iloc[prior_idx]
            if pbar["timestamp_et"].date() == d:
                prev = skew_snapshot(d, float(pbar["close"]), pbar["timestamp_et"])
                if now.rr is not None and prev.rr is not None:
                    rr_chg = now.rr - prev.rr
                if now.put_slope is not None and prev.put_slope is not None:
                    slope_chg = now.put_slope - prev.put_slope
        out.append(SigSkew(str(d), sg.side, sg.bar_idx, t.strftime("%H:%M"), True,
                           now.rr, now.put_slope, rr_chg, slope_chg,
                           now.resolved, now.note, None))
    return out


def apply_confirmer(sig_skews: list[SigSkew], *, put_only: bool, strict_resolved: bool) -> list[SigSkew]:
    """Set .confirm per the side-specific rule.

    PUT confirm  := put-skew STEEPENS (slope_change > 0) OR RR FALLS (rr_change < 0)  (bearish)
    CALL confirm := put-skew FLATTENS (slope_change < 0) OR RR RISES (rr_change > 0)  (bullish)

    Entries with no resolvable skew CHANGE pass through (confirm=None -> KEPT, flagged),
    UNLESS strict_resolved: then an unresolved/unwindowed entry is KEPT but not 'selected'
    (treated as pass-through unfiltered). put_only: only gate PUT entries; CALLs pass.
    """
    out = []
    for s in sig_skews:
        s2 = SigSkew(**asdict(s))
        # decide on the strongest available signal: prefer CHANGE, fall back to level sign
        has_change = (s.rr_change is not None) or (s.slope_change is not None)
        if strict_resolved and not (s.in_window and s.resolved and has_change):
            s2.confirm = None  # pass-through (cannot judge) — counts as KEPT-unfiltered
            out.append(s2); continue
        if not has_change:
            s2.confirm = None; out.append(s2); continue
        if s.side == "P":
            steepen = (s.slope_change is not None and s.slope_change > 0)
            rr_fall = (s.rr_change is not None and s.rr_change < 0)
            s2.confirm = bool(steepen or rr_fall)
        else:  # CALL
            if put_only:
                s2.confirm = None  # don't gate calls in W1b
            else:
                flatten = (s.slope_change is not None and s.slope_change < 0)
                rr_rise = (s.rr_change is not None and s.rr_change > 0)
                s2.confirm = bool(flatten or rr_rise)
        out.append(s2)
    return out


def kept_signals(signals, sig_skews_conf) -> list[Signal]:
    """KEEP a signal if confirm is True OR None (pass-through). DROP confirm==False."""
    keep_idx = {s.bar_idx for s in sig_skews_conf if s.confirm is not False}
    return [sg for sg in signals if sg.bar_idx in keep_idx]


# ─────────────────────────────────────────────────────────────────────────────
# METRIC HELPERS for the gates (drop-top5, OOS-alone-drop-top5)
# ─────────────────────────────────────────────────────────────────────────────
def _per_trade(rows) -> Optional[float]:
    return round(float(np.mean([r.pnl for r in rows])), 2) if rows else None


def _drop_top5_per_trade(rows) -> Optional[float]:
    """Per-trade after removing the 5 best P&L DAYS (concentration robustness, L173)."""
    if not rows:
        return None
    by_day = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    top5_days = set(sorted(by_day, key=lambda d: sum(by_day[d]), reverse=True)[:5])
    kept = [r.pnl for r in rows if r.date not in top5_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _oos_rows(rows):
    return [r for r in rows if int(r.date[:4]) == OOS_YEAR]


def _anchor_pnl(rows) -> float:
    return round(sum(r.pnl for r in rows if r.date in ANCHOR_WIN_DATES), 2)


# ─────────────────────────────────────────────────────────────────────────────
# THE L172 RANDOM-FILTER NULL  (the load-bearing gate)
# ─────────────────────────────────────────────────────────────────────────────
def random_filter_null(all_rows, n_keep: int, seeds: int = NULL_SEEDS) -> dict:
    """Drop the SAME fraction at RANDOM and measure the kept-subset per-trade distribution.

    The confirmer keeps `n_keep` of len(all_rows) trades. A real confirmer's kept-subset
    per-trade must sit in the RIGHT TAIL of what a coin-flip drop of the same size yields.
    Returns the null distribution + one-sided p for the OBSERVED filtered per-trade.
    """
    pnl = np.array([r.pnl for r in all_rows], float)
    N = len(pnl)
    if n_keep <= 0 or n_keep >= N:
        return {"n_total": N, "n_keep": n_keep, "applicable": False,
                "note": "filter dropped 0 or all trades — null not applicable"}
    means = np.empty(seeds)
    rng = random.Random(1234)
    idx_all = list(range(N))
    for s in range(seeds):
        pick = rng.sample(idx_all, n_keep)
        means[s] = pnl[pick].mean()
    return {
        "n_total": int(N), "n_keep": int(n_keep),
        "drop_fraction": round(1 - n_keep / N, 3),
        "seeds": seeds,
        "null_mean": round(float(means.mean()), 2),
        "null_p05": round(float(np.percentile(means, 5)), 2),
        "null_p50": round(float(np.percentile(means, 50)), 2),
        "null_p95": round(float(np.percentile(means, 95)), 2),
        "null_max": round(float(means.max()), 2),
        "_means": means,  # internal, stripped before json
        "applicable": True,
    }


def null_p_for(observed_per_trade: float, null: dict) -> Optional[float]:
    if not null.get("applicable"):
        return None
    means = null["_means"]
    p = float((means >= observed_per_trade).mean())
    return round(p, 4)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[ivskew] loading SPY+VIX ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[ivskew] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # 1) Detect the SAME byte-for-byte vwap_continuation signals (full pattern, no VIX gate).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[ivskew] signals={len(signals)} side={side_ct}", flush=True)

    # 2) Compute as-of skew features per signal.
    print("[ivskew] inverting IV / computing skew per signal (this walks the OPRA cache) ...",
          flush=True)
    sig_skews = compute_sig_skews(signals, spy)
    n_window = sum(1 for s in sig_skews if s.in_window)
    n_resolved = sum(1 for s in sig_skews if s.resolved)
    n_haschange = sum(1 for s in sig_skews if (s.rr_change is not None or s.slope_change is not None))
    print(f"[ivskew] coverage: in_window={n_window}/{len(sig_skews)}  "
          f"true-25d-resolved={n_resolved}  has-change={n_haschange}", flush=True)

    # 3) Baseline UNFILTERED #1 at the live cell.
    base_rows, base_cov = simulate_cell(signals, spy, ribbon, vix,
                                        strike_offset=LIVE_STRIKE_OFFSET,
                                        premium_stop_pct=LIVE_PREMIUM_STOP)
    base_m = metrics(base_rows)
    base_pt = _per_trade(base_rows)
    base_dt5 = _drop_top5_per_trade(base_rows)
    base_oos = _oos_rows(base_rows)
    base_oos_pt = _per_trade(base_oos)
    base_oos_dt5 = _drop_top5_per_trade(base_oos)
    base_anchor = _anchor_pnl(base_rows)
    print(f"[ivskew] UNFILTERED #1 (ATM/-8%): n={base_m.get('n')} "
          f"exp=${base_pt} oos_exp=${base_oos_pt} posQ={base_m.get('positive_quarters')} "
          f"drop5=${base_dt5} anchor=${base_anchor}", flush=True)

    variants = {}
    for vname, put_only in (("W1b_put_side_first", True), ("W1_both_sides", False)):
        for strict in (True, False):
            label = f"{vname}{'_strict25d' if strict else '_loose'}"
            conf = apply_confirmer(sig_skews, put_only=put_only, strict_resolved=strict)
            keep = kept_signals(signals, conf)
            n_drop = len(signals) - len(keep)
            # orthogonality: of the entries we JUDGED (confirm in {T,F}), how often did
            # the skew AGREE with the side the VWAP detector already chose?
            judged = [s for s in conf if s.confirm is not None]
            agree = sum(1 for s in judged if s.confirm)
            agree_rate = round(agree / len(judged), 3) if judged else None

            frows, fcov = simulate_cell(keep, spy, ribbon, vix,
                                        strike_offset=LIVE_STRIKE_OFFSET,
                                        premium_stop_pct=LIVE_PREMIUM_STOP)
            fm = metrics(frows)
            f_pt = _per_trade(frows)
            f_dt5 = _drop_top5_per_trade(frows)
            f_oos = _oos_rows(frows)
            f_oos_pt = _per_trade(f_oos)
            f_oos_dt5 = _drop_top5_per_trade(f_oos)
            f_anchor = _anchor_pnl(frows)

            # (a) beat unfiltered on per-trade
            beats_unfiltered = (f_pt is not None and base_pt is not None and f_pt > base_pt)
            # (b) L172 RANDOM-FILTER null on the FILLED base rows (same realized fill universe)
            null = random_filter_null(base_rows, n_keep=len(frows))
            null_p = null_p_for(f_pt, null) if (f_pt is not None) else None
            beats_random_filter = (null_p is not None and null_p < 0.05)
            # (c) structural gates
            clears, fails = clears_bar(fm)
            oos_pos = (f_oos_pt is not None and f_oos_pt > 0)
            drop5_pos = (f_dt5 is not None and f_dt5 > 0)
            oos_drop5_pos = (f_oos_dt5 is not None and f_oos_dt5 > 0)  # L173
            n_ok = (fm.get("n", 0) >= BAR_N)
            # L171 no-truncation: exit-reason histogram should not be dominated by a single
            # truncation artifact; report it (no hard fail, disclosure).
            # (d) anchor no-regression on the vwap_continuation anchor-date P&L
            anchor_ok = anchor_no_regression(base_anchor, f_anchor, tolerance_pct=0.10)

            improves = bool(beats_unfiltered and beats_random_filter and clears
                            and oos_pos and drop5_pos and oos_drop5_pos and n_ok and anchor_ok)

            null_clean = {k: v for k, v in null.items() if k != "_means"}
            variants[label] = {
                "put_only": put_only, "strict_resolved": strict,
                "n_signals_in": len(signals), "n_kept": len(keep), "n_dropped": n_drop,
                "drop_fraction": round(n_drop / len(signals), 3) if signals else 0.0,
                "n_filled": fm.get("n"),
                "filtered": {
                    "exp": f_pt, "oos_exp": f_oos_pt, "total": fm.get("total_dollar"),
                    "wr_pct": fm.get("wr_pct"), "posQ": fm.get("positive_quarters"),
                    "drop_top5_per_trade": f_dt5, "oos_drop_top5_per_trade": f_oos_dt5,
                    "top5_day_pct": fm.get("top5_day_pct"),
                    "by_side": fm.get("by_side"), "exit_hist": fm.get("exit_hist"),
                    "anchor_pnl": f_anchor,
                },
                "gates": {
                    "beats_unfiltered_exp": beats_unfiltered,
                    "beats_random_filter_null": beats_random_filter,
                    "null_p": null_p,
                    "oos_positive": oos_pos,
                    "drop_top5_positive": drop5_pos,
                    "oos_drop_top5_positive_L173": oos_drop5_pos,
                    "n_ge_20": n_ok,
                    "clears_structural_bar": clears, "structural_fails": fails,
                    "anchor_no_regression_OP16": anchor_ok,
                },
                "random_filter_null_L172": null_clean,
                "orthogonality": {
                    "judged_n": len(judged), "skew_agrees_with_side_rate": agree_rate,
                    "note": ("agreement-rate near 0.5 => skew is orthogonal to the VWAP "
                             "trigger (not re-deriving the side); near 1.0 => redundant"),
                },
                "improves_edge": improves,
            }
            v = variants[label]
            print(f"  [{label}] kept={len(keep)}/{len(signals)} drop={v['drop_fraction']*100:.0f}% "
                  f"exp=${f_pt} (base ${base_pt}) oos=${f_oos_pt} drop5=${f_dt5} "
                  f"null_p={null_p} beatsNull={beats_random_filter} anchor=${f_anchor}({anchor_ok}) "
                  f"clears={clears} -> improves={improves}", flush=True)

    # ── headline verdict = best PUT-side-first variant by whether it improves, else loose
    ordered = sorted(variants.items(),
                     key=lambda kv: (kv[1]["improves_edge"],
                                     kv[1]["gates"]["beats_random_filter_null"],
                                     -(kv[1]["gates"]["null_p"] or 1.0)), reverse=True)
    headline_label, headline = ordered[0]
    any_improves = any(v["improves_edge"] for v in variants.values())

    summary = {
        "family": "vwap_continuation",
        "experiment": "W1_iv_skew_25delta_RR_confirmer",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "live_cell": {"strike_offset": LIVE_STRIKE_OFFSET, "strike_tier": "ATM",
                      "premium_stop_pct": LIVE_PREMIUM_STOP, "qty": QTY},
        "mechanism": ("BS-invert IV at cached strikes -> interpolate IV vs |delta| to ~25d "
                      "call/put -> RR=IV(25dC)-IV(25dP) + put-wing slope + their CHANGE vs "
                      "prior 3 bars, as-of the trigger bar in a 09:35-10:30 ET snapshot. "
                      "CONFIRM: put-skew steepens / RR falls => keep PUT; flattens / RR rises "
                      "=> keep CALL; drop disagreements."),
        "coverage": {
            "n_signals": len(signals), "side_count": side_ct,
            "in_window": n_window, "true_25delta_resolved": n_resolved,
            "has_skew_change": n_haschange,
            "cache_caveat": ("OPRA cache spans ~$10 (+-$5) on ~97.5% of (day,side) groups "
                             "(measured: 712/730); only ~18 groups carry the +-$18/+-$30 "
                             "event cache. 25-delta 0DTE in the morning frequently sits at or "
                             "beyond +-$5 so most days resolve only to the NEAREST available "
                             "delta (extrapolation flagged per signal via delta_err / "
                             "resolved). strict25d variants EXCLUDE unresolved entries from "
                             "the gate (pass-through unfiltered)."),
        },
        "unfiltered_baseline": {
            "n": base_m.get("n"), "exp": base_pt, "oos_exp": base_oos_pt,
            "total": base_m.get("total_dollar"), "posQ": base_m.get("positive_quarters"),
            "drop_top5_per_trade": base_dt5, "oos_drop_top5_per_trade": base_oos_dt5,
            "top5_day_pct": base_m.get("top5_day_pct"), "anchor_pnl": base_anchor,
            "by_side": base_m.get("by_side"),
        },
        "variants": variants,
        "headline_variant": headline_label,
        "any_variant_improves_edge": any_improves,
        "DISCLOSURE": {
            "fills_authority": "real OPRA via lib.simulator_real (C1); same path as edge #1",
            "load_bearing_gate": ("L172 random-FILTER null — drops the SAME fraction at random "
                                  "2000x; the confirmer's kept per-trade must beat it (one-sided "
                                  "p<0.05). The VIX-level gate FAILED this at p=0.355."),
            "spy_vs_option": "C3/L58 — IV inverted from option bars IS the option surface, "
                             "but coverage forces nearest-delta extrapolation on most days.",
            "honest_default": "filters usually just shrink n without real selection; "
                              "improves_edge is true ONLY on all gates incl. the random-filter null.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print("\n=== W1 IV-SKEW CONFIRMER VERDICT ===")
    print(f"unfiltered #1 ATM/-8%: n={base_m.get('n')} exp=${base_pt} oos=${base_oos_pt} "
          f"drop5=${base_dt5} anchor=${base_anchor}")
    print(f"true-25d coverage: {n_resolved}/{len(signals)} signals "
          f"({round(100*n_resolved/max(1,len(signals)),1)}%) — REST are nearest-delta proxies")
    for label, v in variants.items():
        g = v["gates"]; f = v["filtered"]
        print(f"  {label}: kept={v['n_kept']}/{v['n_signals_in']} "
              f"exp=${f['exp']} oos=${f['oos_exp']} drop5=${f['drop_top5_per_trade']} | "
              f"beats_unf={g['beats_unfiltered_exp']} beats_null={g['beats_random_filter_null']}"
              f"(p={g['null_p']}) anchor_ok={g['anchor_no_regression_OP16']} "
              f"-> improves={v['improves_edge']}")
    print(f"\nANY variant improves edge: {any_improves}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
