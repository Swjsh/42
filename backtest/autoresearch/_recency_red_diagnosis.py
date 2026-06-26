"""RECENCY-RED DIAGNOSIS — is edge #1 vwap_continuation's RED 25-window NORMAL VARIANCE,
REGIME SHIFT, or EDGE DECAY?

SAFE research (Sunday, $0, NOT live path). Read-only: no watcher/params/risk_gate/
orchestrator/heartbeat edits, no orders, no commit.

REUSES BYTE-FOR-BYTE (no edits to any of them):
  - recency_check.load_merged_spy_vix / detect_all / simulate_set (= the Sunday driver's
    sim loop = _edgehunt_vwap_continuation detector + lib.simulator_real real OPRA fills)
  - the same recent window resolution (OPRA cache last - 25 trading days)
  => the FULL real-fills per-trade P&L distribution for edge #1 at ATM and ITM-2 is identical
     to what recency_check produced (recent ATM -$22.46/tr n=10; ITM-2 -$75.27/tr n=11;
     full-OOS-2026 ATM +$47.55 / ITM-2 +$73.66).

THREE TESTS:
  1. VARIANCE TEST: from edge #1's full real-fills trade P&L list, bootstrap MANY 25-trade
     windows AND roll all contiguous 25-trade / 25-trading-day windows. What fraction are RED
     (negative sum/mean)? Where does the CURRENT recent window's per-trade fall (percentile +
     z-score of the rolling-window distribution)? If RED windows are common (>20-30%) and the
     current one is within ~2 sigma => NORMAL VARIANCE.
  2. REGIME CHECK: compare recent-window trades vs full-history WINNING trades on regime
     features computed CAUSALLY at entry bar: SPY 20-day (causal) trend strength, realized
     vol-of-day, VIX level + slope, trend-vs-chop (close-vs-open follow-through after entry).
  3. DECAY CHECK: rolling-90-calendar-day expectancy over 2025->2026 — monotonic downtrend
     (decay) vs discrete drawdown in a stationary mean.

DISCLOSURE (C1/C3/C7): real OPRA fills only (WR authority); per-trade EXPECTANCY not WR;
SPY-direction != option edge; recent n is small by design (reported honestly). RESEARCH ONLY.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_recency_red_diagnosis.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reuse the Sunday driver byte-for-byte.
from autoresearch.recency_check import (  # noqa: E402
    load_merged_spy_vix,
    detect_all,
    simulate_set,
    read_cache_last_date,
    RECENCY_LOOKBACK_TRADING_DAYS,
    EDGE_TIERS,
)
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

EDGE = "vwap_continuation"
TIERS = {"ATM": 0, "ITM-2": -2}        # the two live tiers (Safe-2 ATM, Bold ITM-2)
RECENT_LOOKBACK = RECENCY_LOOKBACK_TRADING_DAYS   # 25
OOS_2026_START = dt.date(2026, 1, 1)
N_BOOTSTRAP = 20000
RNG_SEED = 20260621

OUT_JSON = ROOT / "analysis" / "recommendations" / "RECENCY-RED-DIAGNOSIS.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "RECENCY-RED-DIAGNOSIS.md"


# ─────────────────────────────────────────────────────────────────────────────
# Regime features computed CAUSALLY at the entry bar (no look-ahead for the
# entry-time features; the follow-through feature is by-construction post-entry
# and used only to LABEL trend-vs-chop days, not to gate).
# ─────────────────────────────────────────────────────────────────────────────
def _daily_closes(spy: pd.DataFrame) -> "pd.Series":
    """Per-trading-day SPY close (last RTH bar's close), indexed by date — for the
    causal 20-DAY trend strength feature."""
    by_day = spy.groupby("date")["close"].last()
    return by_day


def _causal_20d_trend(daily_close: pd.Series, d: dt.date) -> float | None:
    """SPY 20-trading-day % change ENDING on the PRIOR trading day (causal: known at
    the open of day d). Positive = uptrend, negative = downtrend."""
    dates = list(daily_close.index)
    if d not in dates:
        # snap to last date strictly before d
        prior = [x for x in dates if x < d]
        if len(prior) < 21:
            return None
        last = prior[-1]
        i = dates.index(last)
    else:
        i = dates.index(d)
        if i < 1:
            return None
        i = i - 1  # prior day's close (known at open of d)
    if i < 20:
        return None
    c_now = float(daily_close.iloc[i])
    c_20 = float(daily_close.iloc[i - 20])
    if c_20 == 0:
        return None
    return round(100.0 * (c_now - c_20) / c_20, 3)


def _realized_vol_of_day(spy: pd.DataFrame, d: dt.date) -> float | None:
    """Realized intraday vol of day d's RTH bars (std of 5m log returns, annualized-ish
    as bp). This is the WHOLE-DAY value — used as a day-descriptor for the recent vs winners
    comparison (NOT a causal gate; flagged as descriptive)."""
    day = spy[spy["date"] == d]
    rth = day[(day["t"] >= dt.time(9, 30)) & (day["t"] < dt.time(16, 0))]
    if len(rth) < 5:
        return None
    c = rth["close"].to_numpy(float)
    rets = np.diff(np.log(c))
    if len(rets) < 2:
        return None
    return round(float(np.std(rets) * 1e4), 2)  # bp of 5m return std


def _entry_vix_and_slope(vix: pd.Series, bar_idx: int, look: int = 5) -> tuple[float | None, float | None]:
    """VIX level at entry bar + causal slope over prior `look` bars."""
    arr = vix.to_numpy(float)
    if bar_idx >= len(arr):
        return None, None
    lvl = float(arr[bar_idx])
    slope = float(arr[bar_idx] - arr[bar_idx - look]) if bar_idx >= look else None
    return round(lvl, 2), (round(slope, 3) if slope is not None else None)


def _day_followthrough(spy: pd.DataFrame, d: dt.date) -> tuple[float | None, str | None]:
    """Day character: RTH close-vs-open % move and a trend/chop label by intraday range
    efficiency = |close-open| / (high-low). High efficiency = trend day; low = chop/reversal.
    Descriptive day label (post-hoc), used to characterise the recent losers."""
    day = spy[spy["date"] == d]
    rth = day[(day["t"] >= dt.time(9, 30)) & (day["t"] < dt.time(16, 0))]
    if len(rth) < 5:
        return None, None
    o = float(rth["open"].iloc[0])
    c = float(rth["close"].iloc[-1])
    hi = float(rth["high"].max())
    lo = float(rth["low"].min())
    rng = hi - lo
    if rng <= 0 or o == 0:
        return None, None
    move_pct = round(100.0 * (c - o) / o, 3)
    eff = abs(c - o) / rng    # 0..1 range efficiency
    label = "TREND" if eff >= 0.5 else ("CHOP" if eff < 0.3 else "MIXED")
    return move_pct, label


# ─────────────────────────────────────────────────────────────────────────────
# VARIANCE TEST
# ─────────────────────────────────────────────────────────────────────────────
def rolling_windows_stats(pnl_ordered: list[float], win: int) -> dict:
    """All contiguous rolling windows of `win` trades over the chronologically-ordered
    full P&L list. Returns the per-trade-mean distribution + RED fraction."""
    arr = np.array(pnl_ordered, float)
    if len(arr) < win:
        return {"n_windows": 0}
    means = np.array([arr[i:i + win].mean() for i in range(len(arr) - win + 1)], float)
    return {
        "win": win,
        "n_windows": int(len(means)),
        "frac_red": round(float((means < 0).mean()), 4),
        "frac_red_pct": round(100 * float((means < 0).mean()), 1),
        "mean_of_window_means": round(float(means.mean()), 2),
        "std_of_window_means": round(float(means.std(ddof=1)) if len(means) > 1 else 0.0, 2),
        "p05": round(float(np.percentile(means, 5)), 2),
        "p25": round(float(np.percentile(means, 25)), 2),
        "p50": round(float(np.percentile(means, 50)), 2),
        "p75": round(float(np.percentile(means, 75)), 2),
        "p95": round(float(np.percentile(means, 95)), 2),
        "min": round(float(means.min()), 2),
        "max": round(float(means.max()), 2),
        "_means": means,   # internal, stripped before json
    }


def bootstrap_red(pnl_all: list[float], win: int, n_boot: int, rng) -> dict:
    """IID bootstrap: sample `win` trades WITH replacement from the full P&L list, many times.
    Fraction of resamples with negative mean + distribution of resample means."""
    arr = np.array(pnl_all, float)
    idx = rng.integers(0, len(arr), size=(n_boot, win))
    means = arr[idx].mean(axis=1)
    return {
        "win": win,
        "n_boot": n_boot,
        "frac_red": round(float((means < 0).mean()), 4),
        "frac_red_pct": round(100 * float((means < 0).mean()), 1),
        "mean": round(float(means.mean()), 2),
        "std": round(float(means.std(ddof=1)), 2),
        "p05": round(float(np.percentile(means, 5)), 2),
        "p50": round(float(np.percentile(means, 50)), 2),
        "p95": round(float(np.percentile(means, 95)), 2),
        "_means": means,
    }


def percentile_of(value: float, dist: np.ndarray) -> float:
    """Percentile rank of `value` within distribution `dist` (% of dist <= value)."""
    return round(100.0 * float((dist <= value).mean()), 1)


def zscore_of(value: float, dist: np.ndarray) -> float:
    mu = float(dist.mean())
    sd = float(dist.std(ddof=1)) if len(dist) > 1 else 0.0
    if sd == 0:
        return 0.0
    return round((value - mu) / sd, 2)


# ─────────────────────────────────────────────────────────────────────────────
# DECAY TEST — rolling 90-calendar-day expectancy
# ─────────────────────────────────────────────────────────────────────────────
def rolling_calendar_expectancy(rows: list[dict], window_days: int = 90, step_days: int = 7) -> list[dict]:
    """Rolling per-trade expectancy over a trailing `window_days` calendar window,
    stepped every `step_days`. Each point = mean P&L of trades whose date is in
    (anchor - window, anchor]."""
    if not rows:
        return []
    dated = sorted(((dt.date.fromisoformat(r["date"]), r["pnl"]) for r in rows), key=lambda x: x[0])
    first, last = dated[0][0], dated[-1][0]
    out = []
    anchor = first + dt.timedelta(days=window_days)
    while anchor <= last:
        lo = anchor - dt.timedelta(days=window_days)
        sub = [p for (dd, p) in dated if lo < dd <= anchor]
        if len(sub) >= 5:   # need a minimum to be meaningful
            out.append({"anchor": anchor.isoformat(), "n": len(sub),
                        "exp_per_trade": round(float(np.mean(sub)), 2),
                        "total": round(float(np.sum(sub)), 2)})
        anchor += dt.timedelta(days=step_days)
    return out


def decay_verdict(series: list[dict]) -> dict:
    """Is the rolling expectancy monotonically fading, or a discrete drawdown in a stationary
    mean? Use OLS slope of exp_per_trade vs time-index + sign of recent vs earlier halves."""
    if len(series) < 6:
        return {"verdict": "INSUFFICIENT", "n_points": len(series)}
    y = np.array([s["exp_per_trade"] for s in series], float)
    x = np.arange(len(y), dtype=float)
    # OLS slope
    slope, intercept = np.polyfit(x, y, 1)
    # correlation as monotonicity proxy
    if y.std() > 0:
        r = float(np.corrcoef(x, y)[0, 1])
    else:
        r = 0.0
    half = len(y) // 2
    first_half = float(y[:half].mean())
    second_half = float(y[half:].mean())
    # Spearman rank correlation (monotonic-trend strength, robust)
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    spearman = float(np.corrcoef(rx, ry)[0, 1]) if ry.std() > 0 else 0.0
    # Decay = persistent negative trend: slope clearly < 0 AND second half meaningfully below first
    decaying = (slope < 0) and (spearman < -0.4) and (second_half < first_half - 5)
    # discrete drawdown = trend flat/positive but a recent local dip
    return {
        "n_points": len(series),
        "ols_slope_per_step": round(float(slope), 3),
        "pearson_r_time": round(r, 3),
        "spearman_r_time": round(spearman, 3),
        "first_half_mean_exp": round(first_half, 2),
        "second_half_mean_exp": round(second_half, 2),
        "monotonic_decay": bool(decaying),
        "verdict": ("MONOTONIC_DECAY" if decaying else
                    "DISCRETE_DRAWDOWN_STATIONARY"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def feature_summary(vals: list[float]) -> dict:
    a = np.array([v for v in vals if v is not None], float)
    if len(a) == 0:
        return {"n": 0}
    return {"n": int(len(a)), "mean": round(float(a.mean()), 3),
            "median": round(float(np.median(a)), 3),
            "p25": round(float(np.percentile(a, 25)), 3),
            "p75": round(float(np.percentile(a, 75)), 3),
            "min": round(float(a.min()), 3), "max": round(float(a.max()), 3)}


def main() -> int:
    rng = np.random.default_rng(RNG_SEED)
    print("[diag] loading merged SPY+VIX (master + recent, byte-for-byte recency_check) ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    trading_days = sorted({dc.date for dc in days})
    cache_last = read_cache_last_date()

    # recent window = OPRA cache last - 25 trading days (identical to recency_check default)
    in_range = [d for d in trading_days if d <= cache_last]
    recent_start = in_range[-RECENT_LOOKBACK] if len(in_range) >= RECENT_LOOKBACK else in_range[0]
    recent_end = cache_last
    print(f"[diag] OPRA cache last={cache_last} | recent window {recent_start}..{recent_end} "
          f"({RECENT_LOOKBACK} trading days)", flush=True)

    # Detect the family signals ONCE (same call as the Sunday driver).
    sigs = detect_all(days, spy, vix)
    sigs.pop("_vix_cfg", None)
    sig = sigs[EDGE]
    print(f"[diag] {EDGE}: {len(sig)} signals detected", flush=True)

    daily_close = _daily_closes(spy)

    tiers_out: dict[str, dict] = {}
    for tier, off in TIERS.items():
        rows, cov = simulate_set(sig, spy, ribbon, vix, strike_offset=off, setup=f"{EDGE}_{tier}")
        # attach signal bar_idx so we can compute entry-time regime features
        # rows from simulate_set carry date/side/strike/pnl/exit; re-map to signals by order.
        # simulate_set iterates signals in order and appends a row only on a successful fill,
        # so we re-walk to attach bar_idx and entry features to each filled row deterministically.
        enriched = _enrich_rows(sig, spy, vix, daily_close, off, rows)
        rows_sorted = sorted(enriched, key=lambda r: (r["date"], r.get("bar_idx", 0)))
        pnl_ordered = [r["pnl"] for r in rows_sorted]

        # full + windows
        full = _window_metrics(rows_sorted, trading_days[0], recent_end)
        full_oos = _window_metrics(rows_sorted, OOS_2026_START, recent_end)
        recent = _window_metrics(rows_sorted, recent_start, recent_end)
        print(f"[diag] {tier:6s}(off={off:+d}): full n={full['n']} exp=${full['exp_per_trade']} | "
              f"OOS-2026 n={full_oos['n']} exp=${full_oos['exp_per_trade']} | "
              f"recent n={recent['n']} exp=${recent['exp_per_trade']}", flush=True)

        # ── 1. VARIANCE TEST ──────────────────────────────────────────────
        roll = rolling_windows_stats(pnl_ordered, RECENT_LOOKBACK)
        boot = bootstrap_red(pnl_ordered, recent["n"] if recent["n"] else RECENT_LOOKBACK,
                             N_BOOTSTRAP, rng)
        roll_means = roll.pop("_means", np.array([]))
        boot_means = boot.pop("_means", np.array([]))
        cur_exp = recent["exp_per_trade"]
        variance = {
            "recent_window_n_trades": recent["n"],
            "recent_window_exp_per_trade": cur_exp,
            "rolling_25trade_windows": roll,
            "bootstrap_iid": boot,
            "current_window": {
                "exp_per_trade": cur_exp,
                "percentile_in_rolling": (percentile_of(cur_exp, roll_means)
                                          if len(roll_means) else None),
                "zscore_in_rolling": (zscore_of(cur_exp, roll_means)
                                      if len(roll_means) else None),
                "percentile_in_bootstrap": (percentile_of(cur_exp, boot_means)
                                            if len(boot_means) else None),
                "zscore_in_bootstrap": (zscore_of(cur_exp, boot_means)
                                        if len(boot_means) else None),
            },
        }
        # within-2-sigma + RED-common verdict
        z_roll = variance["current_window"]["zscore_in_rolling"]
        frac_red = roll.get("frac_red_pct", 0.0)
        within_2sig = (z_roll is not None and abs(z_roll) <= 2.0)
        red_common = frac_red >= 20.0
        variance["normal_variance"] = bool(within_2sig and red_common)
        variance["interpretation"] = (
            f"{frac_red}% of all rolling {RECENT_LOOKBACK}-trade windows are RED; current "
            f"window per-trade ${cur_exp} sits at the {variance['current_window']['percentile_in_rolling']}th "
            f"pct (z={z_roll}) of the rolling distribution. "
            + ("WITHIN ~2 sigma AND RED windows are common -> consistent with NORMAL VARIANCE."
               if (within_2sig and red_common) else
               ("BEYOND ~2 sigma -> unusually bad even for this high-variance edge "
                "(lean toward regime/decay)." if (z_roll is not None and abs(z_roll) > 2.0) else
                "RED windows are NOT common for this edge -> a RED window is itself unusual."))
        )

        # ── 2. REGIME CHECK ───────────────────────────────────────────────
        winners_full = [r for r in rows_sorted if r["pnl"] > 0]
        recent_rows = [r for r in rows_sorted if recent_start <= dt.date.fromisoformat(r["date"]) <= recent_end]
        regime = {
            "recent_trades_n": len(recent_rows),
            "full_winners_n": len(winners_full),
            "features": {
                "spy_20d_trend_pct_causal": {
                    "recent": feature_summary([r.get("trend20") for r in recent_rows]),
                    "full_winners": feature_summary([r.get("trend20") for r in winners_full]),
                },
                "realized_vol_of_day_bp": {
                    "recent": feature_summary([r.get("rvol") for r in recent_rows]),
                    "full_winners": feature_summary([r.get("rvol") for r in winners_full]),
                },
                "entry_vix_level": {
                    "recent": feature_summary([r.get("vix_lvl") for r in recent_rows]),
                    "full_winners": feature_summary([r.get("vix_lvl") for r in winners_full]),
                },
                "entry_vix_slope_5bar": {
                    "recent": feature_summary([r.get("vix_slope") for r in recent_rows]),
                    "full_winners": feature_summary([r.get("vix_slope") for r in winners_full]),
                },
                "day_followthrough_pct": {
                    "recent": feature_summary([r.get("ft_pct") for r in recent_rows]),
                    "full_winners": feature_summary([r.get("ft_pct") for r in winners_full]),
                },
            },
            "day_label_mix": {
                "recent": _label_mix([r.get("ft_label") for r in recent_rows]),
                "full_winners": _label_mix([r.get("ft_label") for r in winners_full]),
            },
            "side_mix": {
                "recent": _label_mix([r.get("side") for r in recent_rows]),
                "full_winners": _label_mix([r.get("side") for r in winners_full]),
            },
        }
        regime["signature_notes"] = _regime_notes(regime)

        # ── 3. DECAY CHECK ────────────────────────────────────────────────
        roll90 = rolling_calendar_expectancy(rows_sorted, window_days=90, step_days=7)
        decay = decay_verdict(roll90)
        decay["rolling_90d_series"] = roll90

        tiers_out[tier] = {
            "strike_offset": off, "coverage": cov,
            "full": full, "full_oos_2026": full_oos, "recent": recent,
            "variance_test": variance,
            "regime_check": regime,
            "decay_check": decay,
        }

    # ── Combined verdict (driven by the ATM + ITM-2 agreement) ────────────
    verdict = _combine_verdict(tiers_out)

    summary = {
        "diagnosis": "RECENCY-RED — is edge #1 vwap_continuation's RED 25-window variance / regime / decay?",
        "run_date": dt.date.today().isoformat(),
        "edge": EDGE,
        "tiers": list(TIERS.keys()),
        "opra_cache_last": str(cache_last),
        "recent_window": f"{recent_start}..{recent_end}",
        "recent_lookback_trading_days": RECENT_LOOKBACK,
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1); "
                           "detector + sim REUSED byte-for-byte from recency_check / _edgehunt_vwap_continuation",
        "bootstrap": {"n_iter": N_BOOTSTRAP, "seed": RNG_SEED},
        "per_tier": tiers_out,
        "VERDICT": verdict,
        "DISCLOSURE": {
            "real_fills": "real OPRA fills only — WR authority (C1); SPY-direction != option edge (C3/L58)",
            "per_trade": "per-trade EXPECTANCY, not WR alone (OP-14)",
            "small_n": f"recent window n is small ({RECENT_LOOKBACK} trading days) — reported honestly",
            "causality": "trend20 + entry_vix(+slope) are CAUSAL at entry; rvol + ft_pct/ft_label are "
                         "whole-day DESCRIPTORS (post-hoc day-character labels, not gates)",
            "no_new_ship": "RESEARCH ONLY; no live edit, no orders (money-path guard)",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _write_md(summary)
    print(f"\n[diag] wrote {OUT_JSON}\n[diag] wrote {OUT_MD}", flush=True)

    print("\n=== RECENCY-RED DIAGNOSIS VERDICT ===")
    print(f"VERDICT: {verdict['verdict']}")
    for line in verdict["reasoning"]:
        print(f"  - {line}")
    print("RE-ENTRY GUIDANCE:")
    for line in verdict["reentry_guidance"]:
        print(f"  * {line}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def _enrich_rows(signals, spy, vix, daily_close, off, rows) -> list[dict]:
    """Re-walk signals deterministically (same order simulate_set used) and attach
    bar_idx + causal regime features to each successfully-filled row.

    simulate_set appends rows in signal order, skipping only on cache_miss/sim_none.
    We re-derive the filled subset by matching (date, side, strike) in order — robust to
    any skip — and decorate. We DO NOT re-run the sim (P&L stays byte-identical)."""
    from autoresearch.infinite_ammo_discovery import _strike_from_spot, _nearest_cached_strike
    MAX_STEPS = 4
    # Build the same ordered list of (date, side, strike, bar_idx) the sim would have filled.
    candidates = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - off if sg.side == "P" else atm + off
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STEPS)
        if strike is None:
            continue
        candidates.append({"date": str(d), "side": sg.side, "strike": int(strike),
                           "bar_idx": int(sg.bar_idx)})
    # rows is the actual filled list (cache_miss already dropped; sim_none also dropped).
    # Match each row to a candidate in order (1:1, monotone).
    enriched = []
    ci = 0
    for r in rows:
        # advance candidate pointer to the matching (date,side,strike)
        while ci < len(candidates) and not (
                candidates[ci]["date"] == r["date"] and candidates[ci]["side"] == r["side"]
                and candidates[ci]["strike"] == r["strike"]):
            ci += 1
        bar_idx = candidates[ci]["bar_idx"] if ci < len(candidates) else None
        if ci < len(candidates):
            ci += 1
        nr = dict(r)
        nr["bar_idx"] = bar_idx
        d = dt.date.fromisoformat(r["date"])
        nr["trend20"] = _causal_20d_trend(daily_close, d)
        nr["rvol"] = _realized_vol_of_day(spy, d)
        if bar_idx is not None:
            lvl, slp = _entry_vix_and_slope(vix, bar_idx)
        else:
            lvl, slp = None, None
        nr["vix_lvl"] = lvl
        nr["vix_slope"] = slp
        ft_pct, ft_label = _day_followthrough(spy, d)
        nr["ft_pct"] = ft_pct
        nr["ft_label"] = ft_label
        enriched.append(nr)
    return enriched


def _window_metrics(rows: list[dict], start: dt.date, end: dt.date) -> dict:
    sub = [r for r in rows if start <= dt.date.fromisoformat(r["date"]) <= end]
    if not sub:
        return {"n": 0, "window": f"{start}..{end}"}
    pnl = np.array([r["pnl"] for r in sub], float)
    return {"window": f"{start}..{end}", "n": len(sub),
            "wr_pct": round(100 * float((pnl > 0).mean()), 1),
            "exp_per_trade": round(float(pnl.mean()), 2),
            "total_dollar": round(float(pnl.sum()), 2),
            "std_per_trade": round(float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0, 2)}


def _label_mix(labels: list) -> dict:
    out = defaultdict(int)
    for x in labels:
        out[str(x)] += 1
    return dict(sorted(out.items()))


def _regime_notes(regime: dict) -> list[str]:
    """Flag any feature where recent trades visibly differ from full-history winners."""
    notes = []
    f = regime["features"]
    for name, blk in f.items():
        rc = blk["recent"]
        fw = blk["full_winners"]
        if rc.get("n", 0) == 0 or fw.get("n", 0) == 0:
            continue
        rm = rc.get("median")
        fm = fw.get("median")
        if rm is None or fm is None:
            continue
        # flag if recent median is outside winners' IQR
        if rm < fw.get("p25", -1e9) or rm > fw.get("p75", 1e9):
            notes.append(f"{name}: recent median {rm} is OUTSIDE winners' IQR "
                         f"[{fw.get('p25')}, {fw.get('p75')}] (winners median {fm}) -> possible signature")
        else:
            notes.append(f"{name}: recent median {rm} within winners' IQR "
                         f"[{fw.get('p25')}, {fw.get('p75')}] -> no clear signature")
    return notes


def _combine_verdict(tiers_out: dict) -> dict:
    """Single honest verdict across ATM + ITM-2."""
    # variance agreement
    var_normal = [t["variance_test"]["normal_variance"] for t in tiers_out.values()]
    zs = [t["variance_test"]["current_window"]["zscore_in_rolling"] for t in tiers_out.values()
          if t["variance_test"]["current_window"]["zscore_in_rolling"] is not None]
    fracs = [t["variance_test"]["rolling_25trade_windows"].get("frac_red_pct", 0.0)
             for t in tiers_out.values()]
    pctls = [t["variance_test"]["current_window"]["percentile_in_rolling"] for t in tiers_out.values()
             if t["variance_test"]["current_window"]["percentile_in_rolling"] is not None]
    # decay agreement
    decays = [t["decay_check"]["verdict"] for t in tiers_out.values()]
    any_decay = any(d == "MONOTONIC_DECAY" for d in decays)
    # regime signature presence
    sig_flags = []
    for t in tiers_out.values():
        sig_flags.extend([n for n in t["regime_check"]["signature_notes"] if "possible signature" in n])

    all_within_2sig = all(z is not None and abs(z) <= 2.0 for z in zs) if zs else False
    red_common_all = all(fr >= 20.0 for fr in fracs) if fracs else False

    reasoning = []
    reasoning.append(f"Variance: rolling-25 RED fraction per tier = "
                     + ", ".join(f"{fr}%" for fr in fracs)
                     + f"; current-window percentile = "
                     + ", ".join(f"{p}th" for p in pctls)
                     + f"; z-score = " + ", ".join(f"{z}" for z in zs) + ".")
    reasoning.append(f"Decay: rolling-90d expectancy verdict per tier = {decays}.")
    if sig_flags:
        reasoning.append("Regime: signatures flagged -> " + " | ".join(sig_flags))
    else:
        reasoning.append("Regime: NO recent feature median falls outside the winners' IQR -> "
                         "no clean gateable regime signature.")

    # decision logic
    if any_decay:
        verdict = "DECAY_CONCERN"
        guidance = [
            "Rolling-90d expectancy shows a persistent negative trend, not a discrete dip — "
            "treat alpha as potentially fading.",
            "Do NOT deploy fresh capital on #1 until the rolling-90d expectancy turns back up "
            "AND a fresh 25-trade window prints positive (recency CONFIRM).",
            "Re-run this diagnosis weekly; if the downtrend persists 2+ more windows, retire/rebuild the edge.",
        ]
    elif all_within_2sig and red_common_all:
        verdict = "NORMAL_DRAWDOWN_VARIANCE"
        guidance = [
            "RED 25-windows are common historically and the current one is within ~2 sigma — "
            "this is the expected drawdown of a high-per-trade-variance +EV edge.",
            "The recency gate is doing its job: HOLD capital scaling until a fresh 25-trade window "
            "prints positive (recency flips to CONFIRM). No structural change warranted.",
            "Do NOT regime-gate on the recent losers — prior regime-gating REMOVED winners (C22/C5); "
            "the recent feature distribution does not separate from the winners.",
            "Re-deploy/scale once recency_check.py flips #1 to CONFIRM (recent exp/tr > 0, n >= floor).",
        ]
    else:
        # beyond 2 sigma but no monotonic decay, OR red not common -> ambiguous, lean cautious
        if sig_flags:
            verdict = "REGIME_UNFAVORABLE"
            guidance = [
                "Recent losers cluster on a measurable regime feature (see signatures) AND the window "
                "is worse than ~2 sigma of normal variance — the edge appears to be in an unfavorable regime.",
                "BE SKEPTICAL of gating: prior regime-gating REMOVED winners (C5/C22). Before adding any "
                "gate, A/B it on full history and confirm it does not kill the OOS-2026 winners.",
                "HOLD capital until either the regime feature normalizes OR recency flips to CONFIRM.",
            ]
        else:
            verdict = "NORMAL_DRAWDOWN_VARIANCE"
            guidance = [
                "Current window is at/near the tail but NO regime signature and NO monotonic decay — "
                "most consistent with an unlucky-but-normal drawdown of a high-variance edge.",
                "HOLD capital scaling until a fresh 25-trade window prints positive (recency CONFIRM).",
                "Re-run weekly; escalate to REGIME/DECAY only if a signature or downtrend emerges.",
            ]

    return {"verdict": verdict, "reasoning": reasoning, "reentry_guidance": guidance,
            "per_tier_decay": dict(zip(tiers_out.keys(), decays)),
            "per_tier_variance_normal": dict(zip(tiers_out.keys(), var_normal))}


def _write_md(s: dict) -> None:
    lines = []
    lines.append(f"# RECENCY-RED DIAGNOSIS — edge #1 `{s['edge']}`")
    lines.append("")
    lines.append(f"> **{s['VERDICT']['verdict']}** — run {s['run_date']}, recent window "
                 f"`{s['recent_window']}` ({s['recent_lookback_trading_days']} trading days), "
                 f"OPRA cache last {s['opra_cache_last']}.")
    lines.append("")
    lines.append("SAFE research, $0, NOT live path. Real OPRA fills (C1); detector + sim REUSED "
                 "byte-for-byte from `recency_check.py` / `_edgehunt_vwap_continuation.py`. "
                 "Per-trade EXPECTANCY, not WR (OP-14). RESEARCH ONLY — no live edit, no orders.")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{s['VERDICT']['verdict']}**")
    lines.append("")
    for r in s["VERDICT"]["reasoning"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("### Re-entry guidance")
    lines.append("")
    for g in s["VERDICT"]["reentry_guidance"]:
        lines.append(f"- {g}")
    lines.append("")
    for tier, t in s["per_tier"].items():
        v = t["variance_test"]
        cw = v["current_window"]
        roll = v["rolling_25trade_windows"]
        lines.append(f"## Tier {tier} (strike_offset {t['strike_offset']:+d})")
        lines.append("")
        lines.append(f"- Full real-fills: n={t['full']['n']}, exp/tr ${t['full']['exp_per_trade']}, "
                     f"std/tr ${t['full'].get('std_per_trade')}, total ${t['full']['total_dollar']}")
        lines.append(f"- Full OOS-2026: n={t['full_oos_2026']['n']}, exp/tr "
                     f"${t['full_oos_2026']['exp_per_trade']}")
        lines.append(f"- Recent window: n={t['recent']['n']}, exp/tr ${t['recent']['exp_per_trade']}, "
                     f"WR {t['recent'].get('wr_pct')}%")
        lines.append("")
        lines.append("### 1. Variance test")
        lines.append("")
        lines.append(f"- Rolling-25-trade windows: {roll.get('n_windows')} windows, "
                     f"**{roll.get('frac_red_pct')}% RED**, window-mean distribution "
                     f"p05/p50/p95 = ${roll.get('p05')}/${roll.get('p50')}/${roll.get('p95')}, "
                     f"std ${roll.get('std_of_window_means')}.")
        lines.append(f"- Bootstrap (IID, n={v['bootstrap_iid'].get('n_boot')}): "
                     f"**{v['bootstrap_iid'].get('frac_red_pct')}% RED**.")
        lines.append(f"- **Current window** exp/tr ${cw['exp_per_trade']} -> "
                     f"**{cw['percentile_in_rolling']}th percentile** of rolling dist, "
                     f"**z = {cw['zscore_in_rolling']}** (bootstrap pct "
                     f"{cw['percentile_in_bootstrap']}, z {cw['zscore_in_bootstrap']}).")
        lines.append(f"- {v['interpretation']}")
        lines.append("")
        lines.append("### 2. Regime check (recent trades vs full-history winners)")
        lines.append("")
        for name, blk in t["regime_check"]["features"].items():
            rc, fw = blk["recent"], blk["full_winners"]
            lines.append(f"- **{name}**: recent median {rc.get('median')} "
                         f"(n={rc.get('n')}, IQR [{rc.get('p25')},{rc.get('p75')}]) vs "
                         f"winners median {fw.get('median')} (IQR [{fw.get('p25')},{fw.get('p75')}])")
        lines.append(f"- Day-label mix — recent: {t['regime_check']['day_label_mix']['recent']}; "
                     f"winners: {t['regime_check']['day_label_mix']['full_winners']}")
        lines.append(f"- Side mix — recent: {t['regime_check']['side_mix']['recent']}; "
                     f"winners: {t['regime_check']['side_mix']['full_winners']}")
        for n in t["regime_check"]["signature_notes"]:
            lines.append(f"  - {n}")
        lines.append("")
        lines.append("### 3. Decay check (rolling-90-calendar-day expectancy)")
        lines.append("")
        d = t["decay_check"]
        lines.append(f"- Verdict: **{d['verdict']}** "
                     f"(OLS slope {d.get('ols_slope_per_step')}/step, Spearman r-vs-time "
                     f"{d.get('spearman_r_time')}, first-half exp ${d.get('first_half_mean_exp')} "
                     f"vs second-half ${d.get('second_half_mean_exp')}).")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Files: `analysis/recommendations/RECENCY-RED-DIAGNOSIS.json` (machine), "
                 "`backtest/autoresearch/_recency_red_diagnosis.py` (this script).")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
