"""Forward-looking KEY-LEVEL QUALITY benchmark for Project Gamma.

THE QUESTION THIS ANSWERS:
    "How do we actually KNOW we are drawing good key levels?"

Until now the engine DRAWS levels (backtest/lib/levels.py + premarket) and USES them
as trigger anchors, but it NEVER measures whether a drawn level actually got respected
by price. The `respect_count` / `broken_count` fields in key-levels.json are initialised
to 0 and never incremented. This script is the first objective measurement.

METHOD (no look-ahead, reproducible):
  1. For each trading day D, reconstruct the level set the engine WOULD have drawn at
     the open of D, using ONLY bars strictly before 09:30 ET on D
     (calls the production generator levels._detect_from_history -> same code path as the
     backtest engine; premarket/PDH/PDL/5-day/round/POC/aVWAP/globex/swept).
  2. Walk D's RTH bars forward. For each level, find the FIRST touch, classify the
     outcome over the next K bars as RESPECT / BREAK / CHOP, and measure the reaction
     magnitude (how far price moved away from the level in the rejection direction).
  3. Compare every metric against a RANDOM-LEVELS NULL MODEL (same count per day, same
     price envelope, random positions). The LIFT over random is the real edge signal:
     a 60% respect rate is meaningless if random lines also score 58%.
  4. Stratify by level source (multi_day / intraday / round / swept) and by VIX regime.

Outputs (idempotent overwrite):
  analysis/level-quality/level-quality-benchmark.json   (full machine-readable result)
  analysis/level-quality/level-quality-report.md        (human summary for J)

Pure Python + pandas. $0 cost. No orders, no production-doctrine writes (OP-22 safe).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths + production-code import
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
OUT_DIR = REPO / "analysis" / "level-quality"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Import the PRODUCTION level generator so we benchmark the real algorithm.
_levels_path = REPO / "backtest" / "lib" / "levels.py"
_spec = importlib.util.spec_from_file_location("gamma_levels", _levels_path)
levels_mod = importlib.util.module_from_spec(_spec)
sys.modules["gamma_levels"] = levels_mod  # dataclass introspection needs this registered
_spec.loader.exec_module(levels_mod)  # type: ignore

# ---------------------------------------------------------------------------
# Config (thresholds reported across a small sweep so nothing hides in one knob)
# ---------------------------------------------------------------------------
SPY_FILES = [
    "spy_5m_2025-01-01_2026-06-16.csv",
]
VIX_FILES = [
    "vix_5m_2025-01-01_2026-06-16.csv",
]
START_DAY = dt.date(2025, 8, 1)   # ensures >= 5 prior trading days of history
MIN_PRIOR_TRADING_DAYS = 6
TOUCH_TOL = 0.02                   # a bar "touches" L if low-TOL <= L <= high+TOL
BREAK_CENTS = 0.15                 # close this far beyond L = broken through
REACT_GRID = [0.20, 0.30, 0.50]   # respect = reaction >= REACT (report all)
K_GRID = [3, 6]                    # forward window in 5m bars (15 / 30 min)
HEADLINE_REACT = 0.30
HEADLINE_K = 6
N_NULL_SHUFFLES = 3               # average random null over N seeds for stability
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
# ATR for regime-comparable reaction measurement (Task 1.2)
ATR_BARS = 26                      # ~2.5 hours of 5m bars as the ATR window
# Option-space proxy parameters (Task 1.2, labelled PROXY — real-fills for truth per L74)
# Delta assumptions by moneyness tier used in production: OTM-2 ~ 0.35, ATM ~ 0.50, ITM-1 ~ 0.65
# Theta: 0DTE ATM SPY option ~$2.00 at open decays over 390min → ~$0.026/bar (5m bar)
# For 6-bar hold: theta_total = 0.026 * 6 = $0.156
# Breakeven SPY move for ATM: $0.156 / 0.50 = $0.31 (just above HEADLINE_REACT=$0.30)
# Breakeven for OTM-2 (delta=0.35): $0.156 / 0.35 = $0.45 → many "respects" are losers
OPTION_TIERS = [
    {"label": "OTM-2", "delta": 0.35},
    {"label": "ATM",   "delta": 0.50},
    {"label": "ITM-1", "delta": 0.65},
]
THETA_TOTAL_6BARS = 0.156   # $0.026/bar * 6 bars; 0DTE ATM SPY estimate


# ---------------------------------------------------------------------------
# Data loading (parse the ET wall-clock directly; offsets in the files are noise)
# ---------------------------------------------------------------------------
def _parse_wall_clock(series: pd.Series) -> pd.Series:
    """The first 19 chars 'YYYY-MM-DD HH:MM:SS' are the ET wall clock. The trailing
    offset (-04:00 / -0500) is inconsistent export noise; RTH bars sit at 09:30-16:00
    so the labels are already ET. Parse naive to preserve the displayed clock."""
    return pd.to_datetime(series.astype(str).str.slice(0, 19), format="%Y-%m-%d %H:%M:%S")


def load_spy() -> pd.DataFrame:
    frames = []
    for fn in SPY_FILES:
        p = DATA_DIR / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["timestamp_et"] = _parse_wall_clock(df["timestamp_et"])
        frames.append(df)
    if not frames:
        raise SystemExit("No SPY data files found.")
    spy = pd.concat(frames, ignore_index=True)
    spy = spy.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et")
    spy = spy.reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        spy[c] = pd.to_numeric(spy[c], errors="coerce")
    spy["date"] = spy["timestamp_et"].dt.date
    spy["time"] = spy["timestamp_et"].dt.time
    return spy.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def load_vix_at_open() -> dict[dt.date, float]:
    """Map date -> VIX value as of the RTH open (first bar >= 09:30, else last premarket)."""
    out: dict[dt.date, float] = {}
    for fn in VIX_FILES:
        p = DATA_DIR / fn
        if not p.exists():
            continue
        v = pd.read_csv(p)
        v["timestamp_et"] = _parse_wall_clock(v["timestamp_et"])
        v["close"] = pd.to_numeric(v["close"], errors="coerce")
        v["date"] = v["timestamp_et"].dt.date
        v["time"] = v["timestamp_et"].dt.time
        for d, grp in v.groupby("date"):
            rth = grp[grp["time"] >= RTH_OPEN]
            row = rth.iloc[0] if not rth.empty else grp.iloc[-1]
            val = float(row["close"]) if pd.notna(row["close"]) else None
            if val and 5 <= val <= 100:
                out[d] = val
    return out


def vix_regime(v: float | None) -> str:
    if v is None:
        return "unknown"
    if v < 15:
        return "low"
    if v <= 22:
        return "mid"
    return "high"


# ---------------------------------------------------------------------------
# Level tagging (levels.py returns bare floats; recover a coarse source bucket)
# ---------------------------------------------------------------------------
def tag_source(price: float, multi_day: set[float], swept: set[float]) -> str:
    if any(abs(price - s) < 1e-6 for s in swept):
        return "swept"
    if abs(price - round(price)) < 0.02:
        return "round"
    if any(abs(price - m) < 1e-6 for m in multi_day):
        return "multi_day"
    return "intraday"


# ---------------------------------------------------------------------------
# Outcome classification for a single level on one day
# ---------------------------------------------------------------------------
@dataclass
class Outcome:
    touched: bool
    kind: str           # "RESPECT" | "BREAK" | "CHOP" | "UNTOUCHED"
    reaction: float     # cents moved away from L in rejection direction
    false_break: bool
    source: str
    regime: str


def classify_level(
    L: float,
    rth: pd.DataFrame,
    react_cents: float,
    k: int,
    source: str,
    regime: str,
) -> Outcome:
    highs = rth["high"].to_numpy()
    lows = rth["low"].to_numpy()
    closes = rth["close"].to_numpy()
    opens = rth["open"].to_numpy()
    n = len(rth)

    touch_i = -1
    for i in range(n):
        if (lows[i] - TOUCH_TOL) <= L <= (highs[i] + TOUCH_TOL):
            touch_i = i
            break
    if touch_i < 0:
        return Outcome(False, "UNTOUCHED", 0.0, False, source, regime)

    prev_close = closes[touch_i - 1] if touch_i > 0 else opens[touch_i]
    is_resistance = prev_close < L  # approached from below -> acts as resistance

    end = min(touch_i + k, n - 1)
    w_close = closes[touch_i:end + 1]
    w_low = lows[touch_i:end + 1]
    w_high = highs[touch_i:end + 1]

    if is_resistance:
        broke = bool(np.max(w_close) >= L + BREAK_CENTS)
        reaction = float(L - np.min(w_low))           # downward rejection move
        final_back = bool(w_close[-1] < L)
    else:
        broke = bool(np.min(w_close) <= L - BREAK_CENTS)
        reaction = float(np.max(w_high) - L)          # upward bounce move
        final_back = bool(w_close[-1] > L)

    reaction = max(reaction, 0.0)
    if broke:
        return Outcome(True, "BREAK", reaction, final_back, source, regime)
    if reaction >= react_cents:
        return Outcome(True, "RESPECT", reaction, False, source, regime)
    return Outcome(True, "CHOP", reaction, False, source, regime)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def blank_acc() -> dict:
    return {"n": 0, "touched": 0, "respect": 0, "brk": 0, "chop": 0,
            "false_break": 0, "reactions": [], "tradeable": 0}


def blank_atr_acc() -> dict:
    """Accumulator for ATR-scaled outcomes (Task 1.2)."""
    return {"n_touched": 0, "respect_025atr": 0, "respect_05atr": 0, "atr_reactions": []}


def _compute_day_atr(rth: pd.DataFrame) -> float:
    """Compute a simple average true range over the first ATR_BARS RTH bars."""
    if len(rth) < 2:
        return 1.0  # fallback: 1 dollar
    window = rth.iloc[:ATR_BARS]
    trs = []
    highs = window["high"].to_numpy()
    lows = window["low"].to_numpy()
    closes = window["close"].to_numpy()
    for i in range(1, len(window)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return float(np.mean(trs)) if trs else 1.0


def add(acc: dict, o: Outcome) -> None:
    acc["n"] += 1
    if not o.touched:
        return
    acc["touched"] += 1
    if o.reaction >= HEADLINE_REACT:
        acc["tradeable"] += 1
    if o.kind == "RESPECT":
        acc["respect"] += 1
        acc["reactions"].append(o.reaction)
    elif o.kind == "BREAK":
        acc["brk"] += 1
        if o.false_break:
            acc["false_break"] += 1
    elif o.kind == "CHOP":
        acc["chop"] += 1


def summarize(acc: dict) -> dict:
    n, t = acc["n"], acc["touched"]
    reacts = acc["reactions"]
    return {
        "n_levels": n,
        "touch_rate": round(t / n, 4) if n else None,
        "respect_rate_of_touched": round(acc["respect"] / t, 4) if t else None,
        "break_rate_of_touched": round(acc["brk"] / t, 4) if t else None,
        "chop_rate_of_touched": round(acc["chop"] / t, 4) if t else None,
        "false_break_rate_of_touched": round(acc["false_break"] / t, 4) if t else None,
        "tradeable_rate_of_touched": round(acc["tradeable"] / t, 4) if t else None,
        "median_reaction_respected": round(float(np.median(reacts)), 3) if reacts else None,
        "respect_rate_of_drawn": round(acc["respect"] / n, 4) if n else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    spy = load_spy()
    vix_map = load_vix_at_open()
    print(f"Loaded SPY 5m: {len(spy):,} bars, {spy['date'].min()} -> {spy['date'].max()}")
    print(f"Loaded VIX-at-open for {len(vix_map):,} days")

    all_days = sorted(d for d in spy["date"].unique() if d >= START_DAY)
    ts = spy["timestamp_et"]

    # Headline accumulators (real + null), plus per-source and per-regime (real only)
    real = blank_acc()
    null = blank_acc()
    dm_null = blank_acc()          # distance-matched null (Task 1.1)
    by_source = {k: blank_acc() for k in ("multi_day", "intraday", "round", "swept")}
    by_source_null = {k: blank_acc() for k in ("multi_day", "intraday", "round", "swept")}
    by_source_dm_null = {k: blank_acc() for k in ("multi_day", "intraday", "round", "swept")}
    by_regime = {k: blank_acc() for k in ("low", "mid", "high", "unknown")}
    # Full grid: respect rate at each (react, k) for real vs null
    grid = {f"react{r}_k{k}": {"real": blank_acc(), "null": blank_acc()}
            for r in REACT_GRID for k in K_GRID}
    # ATR-scaled + option-space proxy accumulators (Task 1.2)
    atr_real = blank_atr_acc()
    # Option-space proxy: per-tier {n_respect, profitable_count, net_premiums[]}
    option_proxy_real = {
        t["label"]: {"n_respect": 0, "profitable": 0, "net_premiums": []}
        for t in OPTION_TIERS
    }

    days_used = 0
    levels_per_day = []

    for d in all_days:
        open_mask = (spy["date"] == d) & (spy["time"] >= RTH_OPEN)
        if not open_mask.any():
            continue
        open_idx = int(np.argmax(open_mask.to_numpy()))  # first True
        history = spy.iloc[:open_idx]                     # bars strictly before 09:30 on D
        prior_days = history["date"].nunique()
        if prior_days < MIN_PRIOR_TRADING_DAYS:
            continue

        try:
            ls = levels_mod._detect_from_history(history.copy(), d)
        except Exception as e:  # noqa: BLE001 - benchmark must be resilient per-day
            print(f"  {d}: level gen failed: {e}")
            continue
        active = sorted(set(ls.active))
        if not active:
            continue
        multi = set(ls.multi_day)
        swept = set(getattr(ls, "swept_levels", []) or [])

        rth = spy[(spy["date"] == d) & (spy["time"] >= RTH_OPEN) & (spy["time"] < RTH_CLOSE)]
        if len(rth) < 10:
            continue
        rth = rth.reset_index(drop=True)
        day_open = float(rth["open"].iloc[0])
        regime = vix_regime(vix_map.get(d))

        days_used += 1
        levels_per_day.append(len(active))

        # ATR for this day (Task 1.2)
        day_atr = _compute_day_atr(rth)

        # ---- Real levels: headline + grid + strata + ATR + option-proxy
        real_distances = [abs(L - day_open) for L in active]
        for L in active:
            src = tag_source(L, multi, swept)
            o = classify_level(L, rth, HEADLINE_REACT, HEADLINE_K, src, regime)
            add(real, o)
            add(by_source[src], o)
            add(by_regime[regime], o)
            for r in REACT_GRID:
                for k in K_GRID:
                    add(grid[f"react{r}_k{k}"]["real"],
                        classify_level(L, rth, r, k, src, regime))
            # ATR-scaled outcomes
            if o.touched:
                atr_real["n_touched"] += 1
                atr_react = o.reaction / day_atr if day_atr > 0 else 0.0
                atr_real["atr_reactions"].append(atr_react)
                if atr_react >= 0.25:
                    atr_real["respect_025atr"] += 1
                if atr_react >= 0.50:
                    atr_real["respect_05atr"] += 1
            # Option-space proxy (PROXY — SPY-space only; real-fills authority per L74)
            # Measured over RESPECT outcomes only: does the SPY bounce survive delta+theta?
            if o.touched and o.kind == "RESPECT":
                for tier in OPTION_TIERS:
                    acc = option_proxy_real[tier["label"]]
                    acc["n_respect"] += 1
                    net_premium = (tier["delta"] * o.reaction) - THETA_TOTAL_6BARS
                    acc["net_premiums"].append(net_premium)
                    if net_premium > 0:
                        acc["profitable"] += 1

        # ---- Null model 1: uniform (same count, same envelope, random positions)
        env = max(abs(L - day_open) for L in active)
        if env <= 0:
            continue
        for shuffle in range(N_NULL_SHUFFLES):
            seed = int(d.strftime("%Y%m%d")) * 10 + shuffle
            rng = np.random.default_rng(seed)
            rand_levels = day_open + rng.uniform(-env, env, size=len(active))
            for L in rand_levels:
                L = float(round(L, 2))
                src = "round" if abs(L - round(L)) < 0.02 else "intraday"
                o = classify_level(L, rth, HEADLINE_REACT, HEADLINE_K, src, regime)
                add(null, o)
                add(by_source_null.get(src, blank_acc()), o)
                for r in REACT_GRID:
                    for k in K_GRID:
                        add(grid[f"react{r}_k{k}"]["null"],
                            classify_level(L, rth, r, k, src, regime))

        # ---- Null model 2: distance-matched (Task 1.1)
        # Shuffle the real level distances then apply with random sign.
        # This preserves "how far from open" while randomising "which price".
        # The touch-rate lift should collapse; any remaining respect lift is the real signal.
        for shuffle in range(N_NULL_SHUFFLES):
            seed = int(d.strftime("%Y%m%d")) * 100 + shuffle
            rng = np.random.default_rng(seed)
            shuffled_dists = rng.permutation(real_distances)
            signs = rng.choice([-1, 1], size=len(shuffled_dists))
            dm_levels = [float(round(day_open + s * d_, 2))
                         for s, d_ in zip(signs, shuffled_dists)]
            for L in dm_levels:
                src = "round" if abs(L - round(L)) < 0.02 else "intraday"
                o = classify_level(L, rth, HEADLINE_REACT, HEADLINE_K, src, regime)
                add(dm_null, o)
                add(by_source_dm_null.get(src, blank_acc()), o)

    # ATR-scaled summary
    atr_n = atr_real["n_touched"]
    atr_summary = {
        "n_touched": atr_n,
        "respect_rate_025atr": round(atr_real["respect_025atr"] / atr_n, 4) if atr_n else None,
        "respect_rate_05atr": round(atr_real["respect_05atr"] / atr_n, 4) if atr_n else None,
        "median_reaction_in_atr": round(float(np.median(atr_real["atr_reactions"])), 4)
            if atr_real["atr_reactions"] else None,
    }

    # Option-space proxy summary (per tier)
    spy_respect_rate = result["headline"]["real"]["respect_rate_of_touched"] if "headline" in {} else None
    option_proxy_summary = {
        "label": "PROXY — SPY price-space only (L74). Real-fills required for true option edge.",
        "theta_total_6bars": THETA_TOTAL_6BARS,
        "breakeven_spy_move_by_tier": {
            t["label"]: round(THETA_TOTAL_6BARS / t["delta"], 3) for t in OPTION_TIERS
        },
        "note": "Breakeven move shows the minimum SPY bounce needed to profit at each moneyness after theta.",
        "by_tier": {},
    }
    for tier in OPTION_TIERS:
        acc = option_proxy_real[tier["label"]]
        n = acc["n_respect"]
        profits = acc["net_premiums"]
        option_proxy_summary["by_tier"][tier["label"]] = {
            "delta": tier["delta"],
            "n_respect": n,
            "profitable_rate": round(acc["profitable"] / n, 4) if n else None,
            "median_net_premium": round(float(np.median(profits)), 3) if profits else None,
        }

    # Per-source lift vs both null models (touch rate primary, respect rate secondary)
    # NOTE: random null only generates "round"/"intraday" sources — multi_day/swept have no
    # per-source null equivalent. Fall back to headline null touch rate for those two sources.
    headline_null_tr = summarize(null).get("touch_rate")
    headline_dm_tr = summarize(dm_null).get("touch_rate")
    by_source_dm_lift = {}
    for src in ("multi_day", "intraday", "round", "swept"):
        real_s = summarize(by_source[src])
        dm_s = summarize(by_source_dm_null.get(src, blank_acc()))
        null_s = summarize(by_source_null.get(src, blank_acc()))
        rr_s = real_s.get("respect_rate_of_touched")
        dm_s_rr = dm_s.get("respect_rate_of_touched")
        tr_s = real_s.get("touch_rate")
        # For multi_day/swept: per-source null has n=0 (null only tags round/intraday);
        # compare against headline null touch rate (same price envelope, uniform placement).
        dm_s_tr = dm_s.get("touch_rate") if dm_s.get("n_levels") else headline_dm_tr
        null_s_tr = null_s.get("touch_rate") if null_s.get("n_levels") else headline_null_tr
        by_source_dm_lift[src] = {
            # TOUCH RATE (primary metric — placement edge)
            "real_touch": tr_s,
            "dm_null_touch": dm_s_tr,
            "touch_lift_vs_dm_pp": round((tr_s - dm_s_tr) * 100, 1)
                if (tr_s is not None and dm_s_tr is not None) else None,
            "null_random_touch": null_s_tr,
            "touch_lift_vs_random_pp": round((tr_s - null_s_tr) * 100, 1)
                if (tr_s is not None and null_s_tr is not None) else None,
            "note": "per-source null" if null_s.get("n_levels") else "headline null (no per-source null for this type)",
            # RESPECT RATE (secondary metric — reaction edge)
            "real_respect": rr_s,
            "dm_null_respect": dm_s_rr,
            "lift_pp": round((rr_s - dm_s_rr) * 100, 1)
                if (rr_s is not None and dm_s_rr is not None) else None,
        }

    result = {
        "generated_for": "Project Gamma level-quality baseline",
        "data_window": {"start": str(all_days[0]), "end": str(all_days[-1])},
        "days_benchmarked": days_used,
        "avg_levels_per_day": round(float(np.mean(levels_per_day)), 2) if levels_per_day else None,
        "config": {
            "touch_tol": TOUCH_TOL, "break_cents": BREAK_CENTS,
            "headline_react_cents": HEADLINE_REACT, "headline_k_bars": HEADLINE_K,
            "react_grid": REACT_GRID, "k_grid": K_GRID,
            "n_null_shuffles": N_NULL_SHUFFLES,
            "null_model_uniform": "same count/envelope as real, uniform random positions around day open",
            "null_model_distance_matched": "same count/distances from open as real, random sign (isolates price selection)",
        },
        "headline": {
            "real": summarize(real),
            "null_random": summarize(null),
            "null_distance_matched": summarize(dm_null),
        },
        "by_source_real": {k: summarize(v) for k, v in by_source.items()},
        "by_source_null": {k: summarize(v) for k, v in by_source_null.items()},
        "by_source_dm_null_lift": by_source_dm_lift,
        "by_vix_regime_real": {k: summarize(v) for k, v in by_regime.items()},
        "threshold_grid": {
            key: {"real": summarize(v["real"]), "null": summarize(v["null"])}
            for key, v in grid.items()
        },
        "atr_scaled": atr_summary,
        "option_space_proxy": option_proxy_summary,
    }

    # Derived lift (the money number) vs both nulls
    rr = result["headline"]["real"]["respect_rate_of_touched"]
    nr = result["headline"]["null_random"]["respect_rate_of_touched"]
    dm_rr = result["headline"]["null_distance_matched"]["respect_rate_of_touched"]
    tr = result["headline"]["real"]["touch_rate"]
    ntr = result["headline"]["null_random"]["touch_rate"]
    dm_tr = result["headline"]["null_distance_matched"]["touch_rate"]
    result["headline"]["respect_lift_vs_random_pp"] = (
        round((rr - nr) * 100, 1) if (rr is not None and nr is not None) else None
    )
    result["headline"]["touch_lift_vs_random_pp"] = (
        round((tr - ntr) * 100, 1) if (tr is not None and ntr is not None) else None
    )
    result["headline"]["respect_lift_vs_dm_null_pp"] = (
        round((rr - dm_rr) * 100, 1) if (rr is not None and dm_rr is not None) else None
    )
    result["headline"]["touch_lift_vs_dm_null_pp"] = (
        round((tr - dm_tr) * 100, 1) if (tr is not None and dm_tr is not None) else None
    )

    out_json = OUT_DIR / "level-quality-benchmark.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Markdown report
    md = _render_md(result)
    out_md = OUT_DIR / "level-quality-report.md"
    out_md.write_text(md, encoding="utf-8")

    # Console summary (verify-now)
    print("\n" + "=" * 64)
    print(f"DAYS BENCHMARKED : {days_used}")
    print(f"AVG LEVELS/DAY   : {result['avg_levels_per_day']}")
    print(f"TOUCH RATE       : real {rr_fmt(tr)}  unif-null {rr_fmt(ntr)}  dm-null {rr_fmt(dm_tr)}")
    print(f"  lift vs unif: {result['headline']['touch_lift_vs_random_pp']}pp  "
          f"lift vs dm: {result['headline']['touch_lift_vs_dm_null_pp']}pp")
    print(f"RESPECT RATE     : real {rr_fmt(rr)}  unif-null {rr_fmt(nr)}  dm-null {rr_fmt(dm_rr)}")
    print(f"  lift vs unif: {result['headline']['respect_lift_vs_random_pp']}pp  "
          f"lift vs dm: {result['headline']['respect_lift_vs_dm_null_pp']}pp  <-- KEY NUMBER")
    print(f"  (respect = price moved >= {HEADLINE_REACT:.2f} away from level within {HEADLINE_K} bars, of TOUCHED levels)")
    print(f"MEDIAN REACTION  : {result['headline']['real']['median_reaction_respected']} (respected, real)")
    print(f"\nATR-SCALED RESPECT: @0.25xATR {rr_fmt(atr_summary['respect_rate_025atr'])}  "
          f"@0.5xATR {rr_fmt(atr_summary['respect_rate_05atr'])}  "
          f"median_atr_reaction={atr_summary['median_reaction_in_atr']}")
    op = result["option_space_proxy"]
    print("OPTION PROXY (of RESPECT outcomes — PROXY only, L74):")
    for lbl, t_data in op["by_tier"].items():
        be = op["breakeven_spy_move_by_tier"][lbl]
        print(f"  {lbl:6s} delta={t_data['delta']}  profitable={rr_fmt(t_data['profitable_rate'])}"
              f"  median_net=${t_data['median_net_premium']}  breakeven=${be}")
    print("  ** Real-fills required for true option edge (L74) **")
    print("\nBY SOURCE — TOUCH RATE (primary: placement edge vs random):")
    for k in ("multi_day", "intraday", "round", "swept"):
        n = result["by_source_real"][k]["n_levels"]
        src_lift = result["by_source_dm_null_lift"][k]
        tr_real = src_lift["real_touch"]
        tr_lift_rnd = src_lift["touch_lift_vs_random_pp"]
        tr_lift_dm = src_lift["touch_lift_vs_dm_pp"]
        print(f"  {k:10s} n={n:5d}  touch={rr_fmt(tr_real)}  "
              f"lift_vs_random={'+' if tr_lift_rnd and tr_lift_rnd > 0 else ''}{tr_lift_rnd}pp  "
              f"lift_vs_dm={'+' if tr_lift_dm and tr_lift_dm > 0 else ''}{tr_lift_dm}pp")
    print("\nBY SOURCE — RESPECT RATE (secondary: reaction edge vs dm-null):")
    for k in ("multi_day", "intraday", "round", "swept"):
        rsrc = result["by_source_real"][k]["respect_rate_of_touched"]
        n = result["by_source_real"][k]["n_levels"]
        dm_lift = result["by_source_dm_null_lift"][k]["lift_pp"]
        print(f"  {k:10s} n={n:5d}  respect={rr_fmt(rsrc)}  dm-lift={dm_lift}pp")
    print("\nBY VIX REGIME (respect_rate_of_touched, real):")
    for k in ("low", "mid", "high"):
        print(f"  {k:6s} n={result['by_vix_regime_real'][k]['n_levels']:5d}  respect={rr_fmt(result['by_vix_regime_real'][k]['respect_rate_of_touched'])}")
    print("=" * 64)
    print(f"\nWrote {out_json}")
    print(f"Wrote {out_md}")


def rr_fmt(x: float | None) -> str:
    return f"{x*100:5.1f}%" if isinstance(x, (int, float)) else "  n/a"


def _render_md(r: dict) -> str:
    h = r["headline"]
    real, null = h["real"], h["null_random"]
    lines = []
    lines.append("# Key-Level Quality Benchmark - Baseline\n")
    lines.append(f"_Data window: {r['data_window']['start']} -> {r['data_window']['end']}_  ")
    lines.append(f"_Days benchmarked: **{r['days_benchmarked']}**  |  Avg levels/day: **{r['avg_levels_per_day']}**_\n")
    lines.append("> Measures whether the levels the engine WOULD draw at each day's open "
                 "actually get respected by price. Compared against a random-levels null "
                 "(same count + envelope) - the **lift over random** is the edge signal.\n")
    lines.append("## Headline: TOUCH RATE (Primary — Placement Edge)\n")
    lines.append("> Touch rate = fraction of drawn levels that price actually reached during RTH. "
                 "Lift over random null = placement edge (drawing levels at meaningful prices vs random).\n")
    lines.append("| Metric | Real levels | Random null | Lift |")
    lines.append("|---|---|---|---|")
    lines.append(f"| **Touch rate** (price reached level during RTH) | **{rr_fmt(real['touch_rate'])}** | {rr_fmt(null['touch_rate'])} | **{h['touch_lift_vs_random_pp']}pp** |")
    lines.append(f"| Touch lift vs DM-null | — | {rr_fmt(h['null_distance_matched']['touch_rate'])} | {h['touch_lift_vs_dm_null_pp']}pp |")
    lines.append("")
    lines.append("## By level source: TOUCH RATE lift vs random null\n")
    lines.append("| Source | n | Real touch | Random null touch | **Lift (pp)** |")
    lines.append("|---|---|---|---|---|")
    for k in ("multi_day", "intraday", "round", "swept"):
        s = r["by_source_real"][k]
        sl = r["by_source_dm_null_lift"][k]
        lines.append(f"| {k} | {s['n_levels']} | {rr_fmt(sl['real_touch'])} | "
                     f"{rr_fmt(sl['null_random_touch'])} | **{sl['touch_lift_vs_random_pp']}pp** |")
    lines.append("")
    lines.append("## Headline: RESPECT RATE (Secondary — Reaction Edge)\n")
    lines.append("| Metric | Real levels | Random null | Lift |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Respect rate (of touched) | {rr_fmt(real['respect_rate_of_touched'])} | {rr_fmt(null['respect_rate_of_touched'])} | **{h['respect_lift_vs_random_pp']}pp** |")
    lines.append(f"| Break rate (of touched) | {rr_fmt(real['break_rate_of_touched'])} | {rr_fmt(null['break_rate_of_touched'])} | |")
    lines.append(f"| Chop rate (of touched) | {rr_fmt(real['chop_rate_of_touched'])} | {rr_fmt(null['chop_rate_of_touched'])} | |")
    lines.append(f"| Tradeable rate (reaction >= {r['config']['headline_react_cents']}, of touched) | {rr_fmt(real['tradeable_rate_of_touched'])} | {rr_fmt(null['tradeable_rate_of_touched'])} | |")
    lines.append(f"| Median reaction $ (respected) | {real['median_reaction_respected']} | {null['median_reaction_respected']} | |")
    lines.append("")
    lines.append("## By level source: full detail (real)\n")
    lines.append("| Source | n | Touch rate | Respect rate (touched) | Break rate | Median reaction |")
    lines.append("|---|---|---|---|---|---|")
    for k in ("multi_day", "intraday", "round", "swept"):
        s = r["by_source_real"][k]
        lines.append(f"| {k} | {s['n_levels']} | {rr_fmt(s['touch_rate'])} | {rr_fmt(s['respect_rate_of_touched'])} | {rr_fmt(s['break_rate_of_touched'])} | {s['median_reaction_respected']} |")
    lines.append("")
    lines.append("## By VIX regime (real)\n")
    lines.append("| Regime | n | Touch rate | Respect rate (touched) | Break rate |")
    lines.append("|---|---|---|---|---|")
    for k in ("low", "mid", "high"):
        s = r["by_vix_regime_real"][k]
        lines.append(f"| {k} | {s['n_levels']} | {rr_fmt(s['touch_rate'])} | {rr_fmt(s['respect_rate_of_touched'])} | {rr_fmt(s['break_rate_of_touched'])} |")
    lines.append("")
    lines.append("## Threshold sensitivity (respect_rate_of_touched, real vs null)\n")
    lines.append("| react $ / K bars | Real | Null | Lift |")
    lines.append("|---|---|---|---|")
    for key, v in r["threshold_grid"].items():
        rl = v["real"]["respect_rate_of_touched"]
        nl = v["null"]["respect_rate_of_touched"]
        lift = round((rl - nl) * 100, 1) if (rl is not None and nl is not None) else None
        lines.append(f"| {key} | {rr_fmt(rl)} | {rr_fmt(nl)} | {lift}pp |")
    lines.append("")
    lines.append("---\n")
    lines.append("_Generated by `analysis/level-quality/benchmark_level_quality.py`. "
                 "No look-ahead: levels for day D use only bars before 09:30 ET on D, via "
                 "the production generator `backtest/lib/levels.py`._")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
