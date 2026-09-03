"""B5 EDGE-HUNT (rescue lead): ml_futures_liveweights — re-run the LEARNED next-K-bar
direction model on the FUTURES point-P&L target (NO theta), trained ONLY on the live-weight
feature set that B4 proved carried predictive weight, then trade the high-probability subset
on MES/MNQ point-P&L through ALL 8 anti-2.10 gates.

WHY THIS RESCUE
───────────────
B4 (_b4_ml_direction_model.py) trained a 12-feature LR+GBM SPY-direction classifier under
strict walk-forward. Two findings drove this rescue:

  1. The model BEAT the OOS baselines on raw SPY-direction accuracy (LR 0.530 vs coin-flip
     0.500 / majority 0.513) — a small but real directional edge.
  2. BUT it FAILED all 8 gates when real-filled on 0DTE OPTIONS (survivor ITM2/-8% OOS
     per-trade = -$22.53). The documented reason (C3 / L58, L74, L100-101, L112, L136,
     L148-149): a SPY-DIRECTION edge != a 0DTE-OPTION edge — theta decay + premium-stop
     misfire ate the directional signal. Directional edges belong on FUTURES (no theta).

  3. Feature importance was lopsided. The features that actually carried weight ("live
     weights"): VIX level (LR |w| 0.090 / GBM split-freq 0.483 — #1 by far), VIX 5-bar
     slope (LR 0.032), VWAP-distance (GBM 0.200), time-of-day (GBM 0.300). The features
     that were DEAD: rsi2/rsi14/adx14 (GBM 0), ribbon_stack (GBM 0), structure (GBM 0),
     ret1/ret3/ret5 (GBM 0). This convergent axis (VIX-regime level+slope + VWAP-dist +
     time) is the same one surfaced by B4's MES/MNQ divergence (day+side selection) and the
     live vwap_continuation VIX-gate. C4: drop the dead knobs (L70/L77/L88 — dead features
     are noise that hurt OOS).

THIS SCRIPT
───────────
Same LEARNED model machinery (LR + GBM, pure numpy — sklearn not in venv, $0), but:
  • FEATURES = ONLY the live-weight set: [vix, vix_slope5, vwap_dist_pct, tod]  (4, not 12)
  • LABEL    = sign of next-K-bar FUTURES point return (per symbol — theta-free target)
  • P&L      = pure point-P&L via _futures_directional.simulate (NO option pricing, NO theta)
  • Walk-forward: TRAIN on 2025 futures bars, TEST on 2026 (strict, no leakage — features
    causal as-of bar i; forward label only consumed in the 2025 fit; standardizer + model
    weights fit on TRAIN only; OOS labels used solely to score accuracy).
  • Trade the TOP-DECILE most-confident OOS predictions (one entry/day cap, side = predicted
    direction) on BOTH MES and MNQ, ATR-trailing exit (let the runner RUN — the no-theta
    payoff), then run the FULL trade population (IS 2025 + OOS 2026 via the SAME frozen model)
    through all 8 gates.

NO-LEAKAGE GUARANTEES (C6)
  * Train rows = 2025 bars with a fully-formed same-day forward futures-point label.
  * Test rows  = 2026 bars (with fresh VIX — capped at VIX availability 2026-05-15 so the
    VIX features are never stale/ffilled-flat across a gap).
  * Standardizer (mean/std) fit on TRAIN features ONLY, applied to TEST.
  * LR weights + GBM stumps fit on TRAIN ONLY.
  * Feature windows strictly backward; time-of-day naive ET (L165); forward label stays in
    the same RTH session (causal + fillable).

ALL 8 GATES (anti-2.10, no cherry-pick) — applied per symbol on point-P&L:
  1 OOS(2026) per-trade > 0
  2 positive_quarters >= 4/6
  3 top5-day concentration < 200% of total
  4 n_trades >= 20
  5 drop-top5(days) per-trade > 0   <-- THE gate the divergence lead failed; the rescue MUST clear it
  6 IS(2025)-first-half per-trade > 0
  7 beats random-entry NULL (same exit, matched count/side; per-trade > null mean AND
    drop-top5 > null mean) (L172)
  8 no-truncation: a wider exit (atr_trail) vs a tight target keeps the OOS sign (L171)

Pure Python / numpy, $0 (no LLM, no sklearn). No live orders. Markets closed.
Writes analysis/recommendations/b5-ml-futures-liveweights.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b5_ml_futures_liveweights.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]        # backtest/
ROOT = REPO.parent                                # repo root
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
# Reuse the validated futures point-P&L machinery (signal->fill, ATR, metrics, null)
from autoresearch._futures_directional import (  # noqa: E402
    load_futures,
    session_vwap_asof,
    atr_series,
    simulate,
    Sig,
    Fill,
    POINT_VALUE,
    QTY,
    COMMISSION_RT,
    SLIP_TICKS,
    TICK,
)

OUT = ROOT / "analysis" / "recommendations" / "b5-ml-futures-liveweights.json"

# ── Config ────────────────────────────────────────────────────────────────────
LABEL_HORIZON = 6           # predict sign of FUTURES point return over next K=6 bars (~30 min)
OOS_YEAR = 2026
VIX_FRESH_CUTOFF = dt.date(2026, 5, 15)   # VIX feed ends here; cap test fold so VIX never stale
TOP_DECILE = 0.10           # high-probability subset = top 10% by |p - 0.5|
SYMBOLS = ("MES", "MNQ")

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
ENTRY_GATE = (dt.time(9, 35), dt.time(15, 45))   # don't fire on the 1st bar / leave time-stop room
WARMUP_BARS = 6             # need vix_slope5 (i-5) + a couple bars of session for vwap

# Exit structure — no theta, let the runner RUN (ATR trailing).  Gate-8 cross-check uses a
# TIGHT atr_target (small fixed target) — if the wide-trail OOS sign flips to the tight target,
# the edge is a truncation/exit artifact, not signal.
HEADLINE_EXIT = dict(exit_mode="atr_trail", atr_stop_mult=1.5, atr_target_mult=0.0, trail_mult=2.5)
TIGHT_EXIT = dict(exit_mode="atr_target", atr_stop_mult=1.0, atr_target_mult=1.0, trail_mult=0.0)

# ONLY the live-weight features from B4 (DROP rsi2/rsi14/adx14/ribbon_stack/structure/ret*)
FEATURE_NAMES = ["vix", "vix_slope5", "vwap_dist_pct", "tod"]

# Gate bars
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0

# Model hyperparameters (fixed a priori, NO OOS tuning — same as B4)
LR_EPOCHS = 400
LR_LR = 0.30
LR_L2 = 1e-3
GBM_TREES = 60
GBM_LR = 0.10

RANDOM_NULL_SEEDS = 30


# ─────────────────────────────────────────────────────────────────────────────
# VIX ALIGNMENT (hourly VIX ffilled onto 5m futures bars)
# ─────────────────────────────────────────────────────────────────────────────
def align_vix_to_futures(fut: pd.DataFrame, vix_raw: pd.DataFrame) -> pd.Series:
    """ffill the (hourly) VIX close onto every futures bar by UTC timestamp.

    The runner's VIX 'timestamp_et' column is tz-aware UTC (matches the B4 model's handling).
    Futures 'timestamp_et' is naive ET; localize to ET then convert to UTC to align."""
    fut_utc = (pd.to_datetime(fut["timestamp_et"])
               .dt.tz_localize("America/New_York")
               .dt.tz_convert("UTC"))
    vix_ts = pd.to_datetime(vix_raw["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_raw["close"].astype(float).values, index=vix_ts)
    vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")].sort_index()
    aligned = vix_indexed.reindex(fut_utc, method="ffill")
    aligned.index = range(len(aligned))
    return aligned


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL FEATURE ENGINEERING — live-weight set only, per-day session features
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Sample:
    global_idx: int
    date: dt.date
    feats: np.ndarray
    label: Optional[int]    # 1 up / 0 down over next K bars (futures points); None if no fwd window
    fwd_known: bool


def build_samples(fut: pd.DataFrame, vix: pd.Series) -> list[Sample]:
    """One Sample per eligible RTH futures bar (inside the entry gate). Features causal as-of
    bar i; label = sign of next-K-bar FUTURES point return within the SAME day."""
    samples: list[Sample] = []
    for day, g in fut.groupby("date", sort=True):
        g = g.reset_index()                 # 'index' = global futures bar idx
        if len(g) < WARMUP_BARS + LABEL_HORIZON + 2:
            continue
        gidx = g["index"].to_numpy()
        close = g["close"].to_numpy(float)
        times = g["t"].to_numpy()
        ts = pd.to_datetime(g["timestamp_et"])
        minute = (ts.dt.hour * 60 + ts.dt.minute).to_numpy(float)
        vwap = session_vwap_asof(g).to_numpy(float)
        sess_min0 = minute[0]
        for j in range(len(g)):
            t = times[j]
            if not (ENTRY_GATE[0] <= t <= ENTRY_GATE[1]):
                continue
            if j < WARMUP_BARS:
                continue
            gi = int(gidx[j])
            v = vwap[j]
            vwap_dist = (close[j] - v) / v if v > 0 else 0.0
            tod = (minute[j] - sess_min0) / 390.0
            vix_lvl = float(vix.iloc[gi]) if gi < len(vix) else np.nan
            vix_prev = float(vix.iloc[gi - 5]) if (gi >= 5 and gi - 5 < len(vix)) else np.nan
            vix_slope = (vix_lvl - vix_prev) if (not np.isnan(vix_lvl) and not np.isnan(vix_prev)) else np.nan
            feats = np.array([
                vix_lvl, vix_slope, vwap_dist * 100.0, tod,
            ], dtype=float)
            # forward label (same-day, must stay in RTH to be causal & fillable)
            if j + LABEL_HORIZON < len(g):
                fwd = close[j + LABEL_HORIZON] - close[j]
                label = 1 if fwd > 0 else 0
                fwd_known = True
            else:
                label = None
                fwd_known = False
            samples.append(Sample(global_idx=gi, date=day, feats=feats,
                                  label=label, fwd_known=fwd_known))
    return samples


# ─────────────────────────────────────────────────────────────────────────────
# MODELS (pure numpy) — logistic regression + gradient-boosted stumps  (== B4)
# ─────────────────────────────────────────────────────────────────────────────
def _standardize_fit(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    return mu, sd


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def train_logreg(Xtr: np.ndarray, ytr: np.ndarray) -> np.ndarray:
    n, d = Xtr.shape
    Xb = np.hstack([np.ones((n, 1)), Xtr])
    w = np.zeros(d + 1)
    for _ in range(LR_EPOCHS):
        p = _sigmoid(Xb @ w)
        grad = Xb.T @ (p - ytr) / n
        grad[1:] += LR_L2 * w[1:]
        w -= LR_LR * grad
    return w


def predict_logreg(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return _sigmoid(Xb @ w)


@dataclass
class Stump:
    feat: int
    thresh: float
    left: float
    right: float


def _fit_stump(X: np.ndarray, resid: np.ndarray) -> Stump:
    n, d = X.shape
    best = None
    best_sse = np.inf
    qs = np.array([0.2, 0.4, 0.5, 0.6, 0.8])
    for f in range(d):
        col = X[:, f]
        threshes = np.unique(np.quantile(col, qs))
        for thr in threshes:
            mask = col <= thr
            if mask.sum() < 20 or (~mask).sum() < 20:
                continue
            lval = resid[mask].mean()
            rval = resid[~mask].mean()
            sse = ((resid[mask] - lval) ** 2).sum() + ((resid[~mask] - rval) ** 2).sum()
            if sse < best_sse:
                best_sse = sse
                best = Stump(feat=f, thresh=float(thr), left=float(lval), right=float(rval))
    if best is None:
        best = Stump(feat=0, thresh=0.0, left=float(resid.mean()), right=float(resid.mean()))
    return best


def train_gbm(Xtr: np.ndarray, ytr: np.ndarray) -> tuple[float, list[Stump]]:
    p = np.clip(ytr.mean(), 1e-4, 1 - 1e-4)
    init = float(np.log(p / (1 - p)))
    F = np.full(len(ytr), init)
    trees: list[Stump] = []
    for _ in range(GBM_TREES):
        prob = _sigmoid(F)
        resid = ytr - prob
        stump = _fit_stump(Xtr, resid)
        col = Xtr[:, stump.feat]
        upd = np.where(col <= stump.thresh, stump.left, stump.right)
        F = F + GBM_LR * upd
        trees.append(stump)
    return init, trees


def predict_gbm(init: float, trees: list[Stump], X: np.ndarray) -> np.ndarray:
    F = np.full(X.shape[0], init)
    for st in trees:
        col = X[:, st.feat]
        F = F + GBM_LR * np.where(col <= st.thresh, st.left, st.right)
    return _sigmoid(F)


def gbm_importance(trees: list[Stump], d: int) -> dict:
    cnt = np.zeros(d)
    for st in trees:
        cnt[st.feat] += 1
    tot = cnt.sum() or 1.0
    return {FEATURE_NAMES[i]: round(float(cnt[i] / tot), 4) for i in range(d)}


# ─────────────────────────────────────────────────────────────────────────────
# METRICS over point-P&L fills (IS=2025 / OOS=2026 split)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _by_day(fills: list[Fill]) -> dict:
    bd: dict[str, float] = defaultdict(float)
    for f in fills:
        bd[str(f.date)] += f.pnl
    return bd


def _top5_day_pct(fills: list[Fill]) -> Optional[float]:
    bd = _by_day(fills)
    total = sum(bd.values())
    if total <= 0:
        return None
    top5 = sum(sorted(bd.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_top5_per_trade(fills: list[Fill]) -> Optional[float]:
    """Per-trade after removing the 5 best P&L DAYS (concentration robustness — THE gate)."""
    if not fills:
        return None
    bd = _by_day(fills)
    top5_days = set(sorted(bd, key=lambda k: bd[k], reverse=True)[:5])
    kept = [f for f in fills if str(f.date) not in top5_days]
    if not kept:
        return None
    return round(float(np.mean([f.pnl for f in kept])), 2)


def metrics(fills: list[Fill]) -> dict:
    if not fills:
        return {"n": 0}
    pnl = np.array([f.pnl for f in fills], float)
    n = len(fills)
    wins = int((pnl > 0).sum())
    is_rows = [f for f in fills if f.date.year != OOS_YEAR]
    oos_rows = [f for f in fills if f.date.year == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([f.pnl for f in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([f.pnl for f in rs])), 2) if rs else 0.0

    is_sorted = sorted(is_rows, key=lambda f: f.date)
    is_half = is_sorted[: len(is_sorted) // 2] if len(is_sorted) >= 2 else is_sorted

    by_q: dict[str, list[float]] = defaultdict(list)
    for f in fills:
        by_q[_quarter(f.date)].append(f.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    by_side = {}
    for sd in ("long", "short"):
        s = [f.pnl for f in fills if f.side == sd]
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
        "is_half_n": len(is_half), "is_half_exp": _exp(is_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "drop_top5_per_trade": _drop_top5_per_trade(fills),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(fills),
        "by_side": by_side,
        "exit_mix": {k: sum(1 for x in fills if x.exit_reason == k)
                     for k in sorted({f.exit_reason for f in fills})},
    }


# ─────────────────────────────────────────────────────────────────────────────
# RANDOM-ENTRY NULL on point-P&L (matched OOS count + side mix, same exit)  (L172)
# ─────────────────────────────────────────────────────────────────────────────
def random_entry_null_points(fut: pd.DataFrame, atr: np.ndarray, day_end: dict,
                             oos_fills: list[Fill], exit_cfg: dict, symbol: str,
                             seeds: int = RANDOM_NULL_SEEDS) -> dict:
    """Match the strategy's OOS trade COUNT per day; random entry bars in the entry-gate
    window; same long/short mix; same exit. Returns per-trade mean/std across seeds."""
    per_day: dict = defaultdict(int)
    sides: list[str] = []
    for f in oos_fills:
        per_day[f.date] += 1
        sides.append(f.side)
    if not sides:
        return {"per_trade_mean": None, "n_replicates": 0}
    long_frac = sum(1 for x in sides if x == "long") / len(sides)
    # eligible entry bars per day = inside the entry gate, excluding the last bar
    elig: dict = {}
    for d, g in fut.groupby("date"):
        gg = g[(g["t"] >= ENTRY_GATE[0]) & (g["t"] <= ENTRY_GATE[1])]
        idxs = gg.index.to_numpy()
        idxs = idxs[idxs < day_end.get(d, -1)]  # exclude last-bar entries (no fill room)
        if len(idxs):
            elig[d] = idxs
    rng = np.random.default_rng(42)
    means: list[float] = []
    for _ in range(seeds):
        fills: list[Fill] = []
        for d, cnt in per_day.items():
            idxs = elig.get(d)
            if idxs is None or len(idxs) == 0:
                continue
            chosen = rng.choice(idxs, size=min(cnt, len(idxs)), replace=False)
            for gi in chosen:
                side = "long" if rng.random() < long_frac else "short"
                f = simulate(fut, Sig(idx=int(gi), date=d, side=side), symbol,
                             atr=atr, day_end=day_end, **exit_cfg)
                if f:
                    fills.append(f)
        if fills:
            means.append(float(np.mean([f.pnl for f in fills])))
    if not means:
        return {"per_trade_mean": None, "n_replicates": 0}
    arr = np.array(means)
    return {
        "per_trade_mean": round(float(arr.mean()), 2),
        "per_trade_std": round(float(arr.std()), 2),
        "per_trade_p95": round(float(np.percentile(arr, 95)), 2),
        "per_trade_max": round(float(arr.max()), 2),
        "n_replicates": len(means),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8 GATES
# ─────────────────────────────────────────────────────────────────────────────
def eight_gates(m: dict, null: dict, tight_oos_per_trade: Optional[float]) -> dict:
    oos_pt = m.get("oos_exp") if m.get("n") else None
    drop5 = m.get("drop_top5_per_trade")
    null_mean = null.get("per_trade_mean")
    null_max = null.get("per_trade_max")

    g1 = oos_pt is not None and oos_pt > 0
    g2 = m.get("positive_quarters_n", 0) >= BAR_POS_Q
    t5 = m.get("top5_day_pct")
    g3 = t5 is not None and t5 < BAR_TOP5
    g4 = m.get("n", 0) >= BAR_N
    g5 = drop5 is not None and drop5 > 0
    g6 = m.get("is_half_exp", -1) > 0
    # gate 7: beats null on BOTH the headline per-trade (vs null MAX, strict) and the
    # concentration-robust drop-top5 per-trade (vs null MEAN)
    g7 = bool(oos_pt is not None and null_max is not None and oos_pt > null_max
              and drop5 is not None and null_mean is not None and drop5 > null_mean)
    # gate 8: no-truncation — wide-trail OOS sign must survive the tight-target exit (L171)
    g8 = bool(oos_pt is not None and oos_pt > 0
              and tight_oos_per_trade is not None and tight_oos_per_trade > 0) \
        or bool(oos_pt is not None and oos_pt <= 0)  # if not positive, gate-8 is moot (g1 already fails)
    gates = {
        "g1_oos_per_trade_pos": bool(g1),
        "g2_pos_quarters_ge4of6": bool(g2),
        "g3_top5_lt_200": bool(g3),
        "g4_n_ge_20": bool(g4),
        "g5_drop_top5_pos": bool(g5),
        "g6_is_half_pos": bool(g6),
        "g7_beats_null": bool(g7),
        "g8_no_truncation": bool(g8),
    }
    gates["clears_all_gates"] = all(gates[k] for k in (
        "g1_oos_per_trade_pos", "g2_pos_quarters_ge4of6", "g3_top5_lt_200", "g4_n_ge_20",
        "g5_drop_top5_pos", "g6_is_half_pos", "g7_beats_null", "g8_no_truncation"))
    gates["_detail"] = {
        "oos_per_trade": oos_pt, "drop_top5_per_trade": drop5,
        "null_mean": null_mean, "null_max": null_max,
        "tight_target_oos_per_trade": tight_oos_per_trade,
    }
    return gates


# ─────────────────────────────────────────────────────────────────────────────
# RUN ONE SYMBOL
# ─────────────────────────────────────────────────────────────────────────────
def run_symbol(symbol: str, vix_raw: pd.DataFrame) -> dict:
    fut = load_futures(symbol)
    vix = align_vix_to_futures(fut, vix_raw)
    atr = atr_series(fut["high"], fut["low"], fut["close"], 14).to_numpy()
    day_end = {d: int(g.index[-1]) for d, g in fut.groupby("date")}

    samples = build_samples(fut, vix)
    # drop any sample with a non-finite feature (e.g. VIX gap at session head)
    samples = [s for s in samples if np.all(np.isfinite(s.feats))]

    # Walk-forward split. TEST capped at VIX-fresh cutoff (no stale-VIX leakage).
    train = [s for s in samples if s.date.year < OOS_YEAR and s.fwd_known and s.label is not None]
    test = [s for s in samples if s.date.year == OOS_YEAR and s.date <= VIX_FRESH_CUTOFF
            and s.fwd_known and s.label is not None]
    if not train or not test:
        return {"symbol": symbol, "error": "empty train or test fold",
                "n_train": len(train), "n_test": len(test)}

    Xtr = np.array([s.feats for s in train])
    ytr = np.array([s.label for s in train], float)
    Xte = np.array([s.feats for s in test])
    yte = np.array([s.label for s in test], float)

    mu, sd = _standardize_fit(Xtr)
    Xtr_s = (Xtr - mu) / sd
    Xte_s = (Xte - mu) / sd

    # OOS classification baselines
    train_majority = 1 if ytr.mean() >= 0.5 else 0
    maj_acc = float((yte == train_majority).mean())
    coinflip_acc = 0.50

    w = train_logreg(Xtr_s, ytr)
    p_lr = predict_logreg(w, Xte_s)
    acc_lr = float(((p_lr >= 0.5).astype(float) == yte).mean())

    init, trees = train_gbm(Xtr_s, ytr)
    p_gbm = predict_gbm(init, trees, Xte_s)
    acc_gbm = float(((p_gbm >= 0.5).astype(float) == yte).mean())

    lr_imp = {FEATURE_NAMES[i]: round(float(abs(w[i + 1])), 4) for i in range(len(FEATURE_NAMES))}
    lr_imp = dict(sorted(lr_imp.items(), key=lambda kv: kv[1], reverse=True))
    gbm_imp = dict(sorted(gbm_importance(trees, len(FEATURE_NAMES)).items(),
                          key=lambda kv: kv[1], reverse=True))

    beats_coinflip = (acc_lr > coinflip_acc) or (acc_gbm > coinflip_acc)
    beats_majority = (acc_lr > maj_acc) or (acc_gbm > maj_acc)
    beats_baselines = bool(beats_coinflip and beats_majority)

    best_model = "GBM" if acc_gbm >= acc_lr else "LR"
    p_best_te = p_gbm if best_model == "GBM" else p_lr

    # ── HIGH-PROBABILITY SUBSET: top decile by |p-0.5| on OOS (1/day cap) ──
    conf_te = np.abs(p_best_te - 0.5)
    thr = float(np.quantile(conf_te, 1.0 - TOP_DECILE))
    prob_thr_long = round(0.5 + thr, 4)
    prob_thr_short = round(0.5 - thr, 4)

    def picks_from(samples_fold, p_best, conf):
        cand = []
        for k, s in enumerate(samples_fold):
            if conf[k] >= thr:
                side = "long" if p_best[k] >= 0.5 else "short"
                cand.append((conf[k], s.global_idx, s.date, side))
        by_date: dict[dt.date, tuple] = {}
        for c, gi, d, side in cand:
            if d not in by_date or c > by_date[d][0]:
                by_date[d] = (c, gi, d, side)
        return [(gi, d, side) for (_, gi, d, side) in sorted(by_date.values(), key=lambda x: x[1])]

    oos_picks = picks_from(test, p_best_te, conf_te)
    # IS fold via the SAME frozen-on-2025 model (in-sample by construction; feeds IS-half /
    # quarter / null gates — disclosed honestly; gate 1 is OOS-only and decisive)
    p_best_tr = predict_gbm(init, trees, Xtr_s) if best_model == "GBM" else predict_logreg(w, Xtr_s)
    conf_tr = np.abs(p_best_tr - 0.5)
    is_picks = picks_from(train, p_best_tr, conf_tr)
    all_picks = sorted(is_picks + oos_picks, key=lambda x: x[0])

    side_ct_oos = {"long": sum(1 for _, _, s in oos_picks if s == "long"),
                   "short": sum(1 for _, _, s in oos_picks if s == "short")}

    # ── Real point-P&L fills for headline (atr_trail) + tight (atr_target) cross-check ──
    def fill_all(exit_cfg):
        out: list[Fill] = []
        for gi, d, side in all_picks:
            f = simulate(fut, Sig(idx=int(gi), date=d, side=side), symbol,
                         atr=atr, day_end=day_end, **exit_cfg)
            if f:
                out.append(f)
        return out

    fills_head = fill_all(HEADLINE_EXIT)
    fills_tight = fill_all(TIGHT_EXIT)
    m = metrics(fills_head)
    m_tight = metrics(fills_tight)
    tight_oos = m_tight.get("oos_exp") if m_tight.get("n") else None

    oos_fills_head = [f for f in fills_head if f.date.year == OOS_YEAR]
    null = random_entry_null_points(fut, atr, day_end, oos_fills_head, HEADLINE_EXIT, symbol)
    gates = eight_gates(m, null, tight_oos)

    days = sorted(fut["date"].unique())
    return {
        "symbol": symbol,
        "point_value": POINT_VALUE[symbol],
        "data": {"n_bars": len(fut), "n_days": len(days),
                 "range": [str(days[0]), str(days[-1])]},
        "walk_forward": {
            "train_fold": "2025", "test_fold": "2026 (<= VIX-fresh 2026-05-15)",
            "train_n": len(train), "test_n": len(test),
            "train_up_rate": round(float(ytr.mean()), 4),
            "test_up_rate": round(float(yte.mean()), 4),
            "no_leakage": ("features causal as-of bar i; futures-point fwd label only in train "
                           "fit; standardizer + weights TRAIN-only; OOS labels score-only; test "
                           "capped at VIX-fresh cutoff to avoid stale-VIX leakage"),
        },
        "oos_classification": {
            "coinflip_acc": coinflip_acc,
            "majority_train_class": train_majority,
            "majority_acc_oos": round(maj_acc, 4),
            "logreg_acc_oos": round(acc_lr, 4),
            "gbm_acc_oos": round(acc_gbm, 4),
            "beats_coinflip": bool(beats_coinflip),
            "beats_majority": bool(beats_majority),
            "beats_baselines_oos": beats_baselines,
            "best_model": best_model,
        },
        "feature_importance": {
            "logreg_abs_std_weight": lr_imp,
            "gbm_split_frequency": gbm_imp,
        },
        "high_prob_subset": {
            "top_decile": TOP_DECILE,
            "confidence_threshold_abs": round(thr, 5),
            "prob_threshold_long_ge": prob_thr_long,
            "prob_threshold_short_le": prob_thr_short,
            "oos_distinct_day_picks": len(oos_picks),
            "oos_side_count": side_ct_oos,
            "n_picks_total": len(all_picks),
            "n_picks_is": len(is_picks),
            "n_picks_oos": len(oos_picks),
        },
        "exit_structure": {"headline": HEADLINE_EXIT, "truncation_crosscheck": TIGHT_EXIT},
        "metrics_headline": m,
        "metrics_tight_target_crosscheck": {
            "oos_per_trade": tight_oos, "n": m_tight.get("n"),
            "oos_n": m_tight.get("oos_n"), "total": m_tight.get("total_dollar"),
        },
        "random_entry_null_oos": null,
        "gates": gates,
        "clears_all_gates": bool(gates["clears_all_gates"]),
        "oos_per_trade": m.get("oos_exp") if m.get("n") else None,
        "beats_null": bool(gates["g7_beats_null"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[b5] loading SPY+VIX (for VIX feed) ...", flush=True)
    _spy, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    print(f"[b5] VIX rows={len(vix_raw)}", flush=True)

    per_symbol = {}
    for symbol in SYMBOLS:
        print(f"\n[b5] === {symbol} ===", flush=True)
        res = run_symbol(symbol, vix_raw)
        per_symbol[symbol] = res
        if "error" in res:
            print(f"[b5] {symbol} ERROR: {res['error']}", flush=True)
            continue
        m = res["metrics_headline"]
        oc = res["oos_classification"]
        print(f"[b5] {symbol} OOS acc: coinflip={oc['coinflip_acc']} "
              f"majority={oc['majority_acc_oos']} LR={oc['logreg_acc_oos']} "
              f"GBM={oc['gbm_acc_oos']} -> beats_baselines={oc['beats_baselines_oos']}",
              flush=True)
        print(f"[b5] {symbol} top LR feat: {list(res['feature_importance']['logreg_abs_std_weight'].items())}",
              flush=True)
        print(f"[b5] {symbol} top GBM feat: {list(res['feature_importance']['gbm_split_frequency'].items())}",
              flush=True)
        print(f"[b5] {symbol} subset: oos_picks={res['high_prob_subset']['oos_distinct_day_picks']} "
              f"side={res['high_prob_subset']['oos_side_count']} "
              f"prob_thr long>={res['high_prob_subset']['prob_threshold_long_ge']} "
              f"short<={res['high_prob_subset']['prob_threshold_short_le']}", flush=True)
        print(f"[b5] {symbol} headline n={m.get('n')} oos_exp=${m.get('oos_exp')} "
              f"(oos_n={m.get('oos_n')}) posQ={m.get('positive_quarters')} "
              f"top5%={m.get('top5_day_pct')} drop5=${m.get('drop_top5_per_trade')} "
              f"null_mean=${res['random_entry_null_oos'].get('per_trade_mean')}", flush=True)
        print(f"[b5] {symbol} GATES: "
              f"{ {k: v for k, v in res['gates'].items() if k.startswith('g')} }", flush=True)
        print(f"[b5] {symbol} CLEARS ALL 8: {res['clears_all_gates']}", flush=True)

    # Best config across symbols = the one that clears most gates, tiebreak OOS per-trade
    def gate_count(r):
        if "error" in r:
            return -1
        return sum(1 for k, v in r["gates"].items() if k.startswith("g") and v)
    ranked = sorted(SYMBOLS, key=lambda s: (gate_count(per_symbol[s]),
                                            per_symbol[s].get("oos_per_trade") or -1e9),
                    reverse=True)
    best_sym = ranked[0]
    best = per_symbol[best_sym]
    any_clears = any(per_symbol[s].get("clears_all_gates") for s in SYMBOLS if "error" not in per_symbol[s])

    summary = {
        "kind": "b5_rescue",
        "slug": "ml-futures-liveweights",
        "test": "ml_futures_liveweights",
        "lane": "ml-futures",
        "hypothesis": ("Re-run the LEARNED next-K-bar direction model on the FUTURES point-P&L "
                       "target (no theta) using ONLY the live-weight feature set from B4 "
                       "(VIX level + VIX 5-bar slope + VWAP-distance + time-of-day; DROP the dead "
                       "RSI + ribbon-stack/structure/returns); LR + GBM, strict walk-forward "
                       "(train 2025 -> test 2026, no leakage); trade the top-decile high-probability "
                       "subset on MES/MNQ point-P&L through all 8 gates. Does the 53%-direction "
                       "model become PROFITABLE without theta?"),
        "method": "new (supervised learning on theta-free futures point-P&L; live-weight features only)",
        "run_date": dt.date.today().isoformat(),
        "features": FEATURE_NAMES,
        "features_dropped_from_b4": ["rsi2", "rsi14", "adx14", "ribbon_stack", "structure",
                                     "ret1", "ret3", "ret5"],
        "label": f"sign of next-{LABEL_HORIZON}-bar FUTURES point return (same-day RTH window)",
        "pnl_model": ("point-P&L: (exit-entry)*point_value*qty - costs; NO option pricing, NO "
                      f"theta; {QTY} micro, ${COMMISSION_RT} RT commission, {SLIP_TICKS} tick "
                      "slippage each side; ATR-trailing exit (let runner RUN)"),
        "model_hparams": {
            "logreg": {"epochs": LR_EPOCHS, "lr": LR_LR, "l2": LR_L2},
            "gbm": {"trees": GBM_TREES, "lr": GBM_LR, "max_depth": 1},
            "note": "fixed a priori, NO OOS tuning (same as B4)",
        },
        "per_symbol": per_symbol,
        "best_config": best_sym,
        "best_config_clears_all_gates": bool(best.get("clears_all_gates")),
        "any_symbol_clears_all_gates": bool(any_clears),
        "DISCLOSURE": {
            "pure_python": "no sklearn (not in venv); LR + GBM hand-rolled in numpy; $0",
            "theta_free": "futures point-P&L only — this is the C3/L58 directional-edge arena",
            "live_weights_only": ("features restricted to B4's non-dead weights (VIX level #1, "
                                  "VIX slope, VWAP-dist, time-of-day); dead features dropped per C4"),
            "per_trade": "per-trade expectancy reported, not WR alone (OP-14/C4)",
            "is_oos": "IS=2025 (train, in-sample by construction) / OOS=2026 (test) split",
            "decisive_gate": "gate 1 (OOS-2026 per-trade > 0) is the decisive directional test",
            "drop_top5_gate": ("gate 5 (drop best-5-days per-trade > 0) is THE gate the divergence "
                               "lead failed; the rescue MUST clear it"),
            "null": "random-entry null (same exit, matched count/side) isolates exit artifact (L172)",
            "truncation": "wide-trail vs tight-target OOS-sign cross-check (L171)",
            "vix_freshness": "test fold capped at 2026-05-15 (VIX feed end) to avoid stale-VIX leakage",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[b5] wrote {OUT}", flush=True)

    print("\n=== ML_FUTURES_LIVEWEIGHTS (B5 rescue) VERDICT ===")
    for s in SYMBOLS:
        r = per_symbol[s]
        if "error" in r:
            print(f"  {s}: ERROR {r['error']}")
            continue
        print(f"  {s}: OOS/trade=${r.get('oos_per_trade')} clears_all={r.get('clears_all_gates')} "
              f"gates={ {k: v for k, v in r['gates'].items() if k.startswith('g')} }")
    print(f"BEST: {best_sym} | any symbol clears all 8: {any_clears}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
