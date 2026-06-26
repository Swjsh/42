"""B9 — REGIME-CONDITIONAL BEAR BOOK (ANGLE B robustness probe).

THE ROBUSTNESS GAP (J / Gamma, 2026-06-21)
──────────────────────────────────────────
All THREE shipped/dormant real edges are VWAP-native and CALL/BULL-biased:
  #1 vwap_continuation (LIVE, ITM-2 Bold / ATM Safe-2)
  #2 vwap_reclaim_failed_break (dormant)
  #4 vix_regime_dayside (dormant)
The 2026 window is a strong BULL tape, so put/bear setups have died on it. The honest
question this module answers: **is there a bearish VWAP-native structural edge that works
WHEN GATED TO A BEARISH REGIME** (down-trend day / SPY below a key MA / below-VWAP)?

Even a DORMANT, regime-gated bear edge is valuable robustness — it is the book we want on
hand for when the regime turns. The likely outcome in this bull window is thin/negative;
the deliverable is the HONEST answer of whether bear alpha EXISTS regime-conditionally.

THE BEAR STRUCTURES (all bear-mirror, puts-only, one entry/session, causal):
  (i)   BEAR_CONT  — bear mirror of #1: below-VWAP established down-trend continuation.
        First TREND_BARS RTH closes ALL below session VWAP -> the day-trend side is DOWN
        -> take the first qualifying PUT entry in the morning window.
  (ii)  BEAR_FBO   — bear mirror of #2 (failed up-break -> with-downtrend VWAP rejection):
        price pokes ABOVE session VWAP intrabar then closes back BELOW it on a down-trend
        day (failed reclaim from below) -> PUT. The bearish analogue of "failed break".
  (iii) BEAR_RIDE  — J's source-of-truth BEARISH_REJECTION_RIDE_THE_RIBBON (OP-16 scoped):
        EMA ribbon stacked BEAR + price rejects a swing-high / VWAP from below (bar high
        >= recent swing high but close back below VWAP) then rides down -> PUT. Includes
        the OP-16 ANCHOR fidelity check (must take J's 4/29, 5/01, 5/04 PUT winners, and
        skip / lose-less his 5/05, 5/06, 5/07 losers). NOTE: J's anchors are 2026 dates =
        OOS, so this is a FIDELITY check, not an independent OOS test (disclosed).

THE BEARISH REGIME GATE (each structure ONLY fires when the regime is DOWN — causal):
  A day-bar qualifies as bearish regime at the entry bar iff ALL of:
    * day-trend side is DOWN (first TREND_BARS closes below session VWAP), AND
    * price (entry bar close) is BELOW the ribbon SLOW EMA (the "key MA" proxy), AND
    * the ribbon stack is not BULL (stack in {"BEAR","MIXED"} — i.e. not a clean up-stack).
  All three sub-conditions read ONLY at-or-before the entry bar. The gate is what makes
  this a *regime-conditional* bear book rather than a naive always-on put machine.
  (BEAR_RIDE additionally requires its own ribbon=BEAR rejection trigger.)

ARENAS (C3/L58 — a SPY-direction edge can die to theta on puts, so test BOTH):
  * 0DTE real-fills (C1, lib.simulator_real) — the production authority. Two strike tiers:
      ATM_safe2  (offset 0)   = Gamma-Safe-2 production
      ITM2_bold  (offset -2)  = Gamma-Risky-2 production (deep-ITM put, offset -2)
    chart-stop = trailing 12-bar swing HIGH (puts); bear premium stop -0.20 (v15 asym).
  * Futures point-P&L (MES $5/pt + MNQ $2/pt, no theta; ATR chandelier so trend winners
    RUN) — the clean test of the directional SIGNAL absent the option bracket.

THE FULL STANDING BAR (every standalone candidate — applied to EACH structure x tier):
  g1  OOS(2026) per-trade > 0
  g2  positive in >= ceil(0.6*Q) quarters (>=4 of 6)
  g3  top-5 winning DAYS < 200% of total P&L (concentration, OP-20 #5)
  g4  n_trades >= 20
  g5  full drop-top5-days per-trade > 0
  g6  IS(2025) FIRST-HALF per-trade > 0 (sub-window stability, L166)
  g7  beats random-entry NULL (L172) — null_baseline.null_gate (beat MAX + drop5>mean)
  g8  NO-TRUNCATION (L171) — same-strike chart-stop-only must keep a positive OOS sign
  g9  OOS-ALONE drop-top5 per-trade > 0 (L173) — drop the 5 best OOS days, OOS must hold
  g10 INDEPENDENCE vs shipped edges (L174) — day-overlap (Jaccard) with #1 vwap_continuation
      trade-days < 0.80 (a bear book that just inverts the bull edge's days is not new)
  g11 NO-REGRESSION (L174) — the days this book SKIPS must net NEGATIVE (i.e. the book is
      not skipping winning days; abstention is correct). Built from the bear-mirror baseline.

NO LEAKAGE / NO LOOK-AHEAD (C6): VWAP is cumulative session VWAP (causal); the slow EMA
is the production ribbon slow (causal); day-trend side uses only the first TREND_BARS closes;
swing high uses only bars at-or-before the entry bar; entry fills the NEXT bar open. The ONE
swept knob is the bear premium stop (disclosed; gate 1 is OOS-only & decisive).

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_b9_bear_book.py
Pure Python / numpy, $0, no live orders, markets closed.
Writes analysis/recommendations/b9-bear-book.json + B9-BEAR-BOOK-SCORECARD.md.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
ROOT = REPO.parent                                  # ...\42
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
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "b9-bear-book.json"
SCORECARD = ROOT / "analysis" / "recommendations" / "B9-BEAR-BOOK-SCORECARD.md"
FUT_DATA = ROOT / "backtest" / "data" / "futures"

# ── Shared signal config ─────────────────────────────────────────────────────────
TREND_BARS = 3                 # day-trend side = first 3 closes all below VWAP (= DOWN)
ENTRY_GATE = (dt.time(9, 35), dt.time(11, 30))   # take the side in the morning window
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
OOS_YEAR = 2026
SWING_LOOKBACK = 12            # chart-stop swing window + the BEAR_RIDE rejection lookback
N_QUARTERS_TARGET = 6          # 2025Q1..2026Q2

# OP-16 source-of-truth anchors (2026 = OOS -> fidelity check, not independent OOS).
ANCHORS = {
    dt.date(2026, 4, 29): "WIN", dt.date(2026, 5, 1): "WIN", dt.date(2026, 5, 4): "WIN",
    dt.date(2026, 5, 5): "LOSS", dt.date(2026, 5, 6): "LOSS", dt.date(2026, 5, 7): "LOSS",
}

# ── 0DTE real-fills config ──────────────────────────────────────────────────────
QTY = 3
MAX_STRIKE_STEPS = 4
# For PUTS (side='P'): strike = atm - strike_offset. offset 0 = ATM, -2 = ITM-2 (deep-ITM put).
STRIKE_TIERS = {"ATM_safe2": 0, "ITM2_bold": -2}
# v15 asymmetric BEAR stop = -0.20 (the production default for puts). Swept around it; the
# -0.99 cell is chart-stop-only (used for the L171 no-truncation reference).
PREMIUM_STOP = -0.20
PREMIUM_STOP_SWEEP = [-0.08, -0.20, -0.50]
CHART_STOP_ONLY = -0.99
SIDE = "P"                     # bear book -> puts only
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0
INDEP_OVERLAP_MAX = 0.80       # L174 day-overlap ceiling vs #1 vwap_continuation

# ── Futures point-P&L config (byte-identical to _b5_vix_regime_dayside) ────────────
POINT_VALUE = {"MNQ": 2.0, "MES": 5.0}
TICK = 0.25
COMMISSION_RT = 1.24
SLIP_TICKS = 1
FUT_QTY = 1
ATR_LEN = 14
ATR_STOP_MULT = 1.5
TRAIL_MULT = 2.5
FUT_RANDOM_SEEDS = 30

STRUCTURES = ("BEAR_CONT", "BEAR_FBO", "BEAR_RIDE")


# ═════════════════════════════════════════════════════════════════════════════════
# DATA NORMALIZATION
# ═════════════════════════════════════════════════════════════════════════════════
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


def _align_vix(spy_df: pd.DataFrame, vix_raw: pd.DataFrame) -> np.ndarray:
    spy_ts = pd.to_datetime(spy_df["timestamp_et"]).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    vix_ts = pd.to_datetime(vix_raw["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_raw["close"].astype(float).values, index=vix_ts)
    vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    aligned = vix_indexed.reindex(spy_ts, method="ffill")
    aligned.index = range(len(aligned))
    return aligned.fillna(0.0).to_numpy()


def quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _q_of(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


# ═════════════════════════════════════════════════════════════════════════════════
# 0DTE DETECTORS — three bear structures, each REGIME-GATED
# ═════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class OptSig:
    gidx: int          # global SPY idx; fill at NEXT bar open
    date: dt.date
    side: str          # always "P" here
    structure: str


def _down_trend_side(closes: np.ndarray, vwap: np.ndarray) -> bool:
    """Day-trend side is DOWN iff the first TREND_BARS closes are ALL below session VWAP."""
    head_c = closes[:TREND_BARS]
    head_v = vwap[:TREND_BARS]
    return bool(np.all(head_c < head_v))


def detect_opt_signals(days, ribbon_g: pd.DataFrame, structure: str) -> list[OptSig]:
    """One PUT entry/session for ``structure``, gated to a BEARISH regime. All inputs read
    at-or-before the entry bar (causal); fill = NEXT bar open (sim handles)."""
    out: list[OptSig] = []
    slow_g = ribbon_g["slow"].to_numpy(float)
    stack_g = ribbon_g["stack"].to_numpy(object)
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        gidx = rth.index.to_numpy()
        closes = rth["close"].to_numpy(float)
        highs = rth["high"].to_numpy(float)
        lows = rth["low"].to_numpy(float)
        times = rth["t"].to_numpy()
        vwap = session_vwap_asof(rth).to_numpy(float)
        if not _down_trend_side(closes, vwap):
            continue   # regime gate part 1: day-trend side must be DOWN
        for j in range(TREND_BARS, len(rth)):
            t = times[j]
            if not (ENTRY_GATE[0] <= t <= ENTRY_GATE[1]):
                if t > ENTRY_GATE[1]:
                    break
                continue
            g = int(gidx[j])
            close_j = closes[j]
            slow = float(slow_g[g]) if g < len(slow_g) else None
            stack = str(stack_g[g]) if g < len(stack_g) else ""
            # regime gate part 2+3 (causal): below the slow EMA AND not a clean BULL stack.
            if slow is None or math.isnan(slow):
                continue
            if close_j >= slow:
                continue
            if stack == "BULL":
                continue
            # ── structure-specific trigger ──
            fire = False
            if structure == "BEAR_CONT":
                # established down-trend continuation: close still below VWAP at entry.
                fire = close_j < vwap[j]
            elif structure == "BEAR_FBO":
                # failed up-break: bar poked ABOVE vwap intrabar then closed back BELOW it.
                fire = (highs[j] > vwap[j]) and (close_j < vwap[j])
            elif structure == "BEAR_RIDE":
                # ribbon BEAR + rejection of a recent swing high from below, close back < vwap.
                lo = max(0, j - SWING_LOOKBACK + 1)
                swing_high = float(np.max(highs[lo:j])) if j > lo else highs[j]
                rejected = (highs[j] >= swing_high) and (close_j < swing_high) and (close_j < vwap[j])
                fire = (stack == "BEAR") and rejected
            if not fire:
                continue
            out.append(OptSig(gidx=g, date=dc.date, side=SIDE, structure=structure))
            break
    return out


def detect_universe_signals(days) -> list[OptSig]:
    """The no-regression REFERENCE universe (L174): a naive PUT on the first morning bar of
    EVERY down-trend-side day, with NO regime sub-filter and NO structure trigger. This is the
    'always short the down-day' book the regime-gated structures are pruning. A structure's
    SKIPPED days = universe days it did NOT take; g11 requires those skipped days to net <= 0
    (i.e. the regime gate correctly abstained from days that would have lost on naive shorting)."""
    out: list[OptSig] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        gidx = rth.index.to_numpy()
        closes = rth["close"].to_numpy(float)
        times = rth["t"].to_numpy()
        vwap = session_vwap_asof(rth).to_numpy(float)
        if not _down_trend_side(closes, vwap):
            continue
        for j in range(TREND_BARS, len(rth)):
            t = times[j]
            if ENTRY_GATE[0] <= t <= ENTRY_GATE[1]:
                out.append(OptSig(gidx=int(gidx[j]), date=dc.date, side=SIDE, structure="UNIVERSE"))
                break
            if t > ENTRY_GATE[1]:
                break
    return out


def _swing_stop(spy: pd.DataFrame, gidx: int, lookback: int = SWING_LOOKBACK) -> float:
    """PUT chart-stop = trailing swing HIGH (resistance that must hold above entry)."""
    c = float(spy.iloc[gidx]["close"])
    lo = max(0, gidx - lookback + 1)
    win = spy.iloc[lo: gidx + 1]
    rej = float(win["high"].max())
    return rej if rej > c else c + 1.0


@dataclass
class OptRow:
    date: str
    side: str
    strike: int
    pnl: float
    pct: float
    exit_reason: str


def simulate_opt(sigs: list[OptSig], spy: pd.DataFrame, ribbon: pd.DataFrame,
                 vix_g: np.ndarray, *, strike_offset: int,
                 premium_stop_pct: float) -> tuple[list[OptRow], dict]:
    rows: list[OptRow] = []
    n_total = len(sigs); n_filled = n_miss = n_none = 0
    for s in sigs:
        bar = spy.iloc[s.gidx]
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset            # puts: strike = atm - offset
        strike = _nearest_cached_strike(s.date, target, s.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix_g[s.gidx]) if s.gidx < len(vix_g) else 0.0
        stop = _swing_stop(spy, s.gidx)
        fill = simulate_trade_real(
            entry_bar_idx=s.gidx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=round(stop, 2), triggers_fired=[s.structure.lower()],
            side=s.side, qty=QTY, setup=s.structure, strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append(OptRow(date=str(s.date), side=s.side, strike=int(strike),
                           pnl=round(float(fill.dollar_pnl), 2),
                           pct=round(float(fill.pct_return_on_premium), 5),
                           exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss, "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ═════════════════════════════════════════════════════════════════════════════════
# 0DTE METRICS + GATES
# ═════════════════════════════════════════════════════════════════════════════════
def _by_day_opt(rows: list[OptRow]) -> dict:
    bd: dict[str, float] = defaultdict(float)
    for r in rows:
        bd[r.date] += r.pnl
    return bd


def _top5_day_pct(rows: list[OptRow]) -> Optional[float]:
    bd = _by_day_opt(rows)
    total = sum(bd.values())
    if total <= 0:
        return None
    top5 = sum(sorted(bd.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_top5_pt(rows: list[OptRow]) -> Optional[float]:
    """Per-trade after removing the 5 best P&L DAYS (full sample)."""
    if not rows:
        return None
    bd = _by_day_opt(rows)
    top5_days = set(sorted(bd, key=lambda k: bd[k], reverse=True)[:5])
    kept = [r for r in rows if r.date not in top5_days]
    if not kept:
        return None
    return round(float(np.mean([r.pnl for r in kept])), 2)


def _oos_alone_drop_top5_pt(rows: list[OptRow]) -> Optional[float]:
    """L173: per-trade over OOS rows ONLY after removing the 5 best OOS days."""
    oos = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    if not oos:
        return None
    bd: dict[str, float] = defaultdict(float)
    for r in oos:
        bd[r.date] += r.pnl
    top5_days = set(sorted(bd, key=lambda k: bd[k], reverse=True)[:5])
    kept = [r for r in oos if r.date not in top5_days]
    if not kept:
        return None
    return round(float(np.mean([r.pnl for r in kept])), 2)


def metrics_opt(rows: list[OptRow]) -> dict:
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

    is_sorted = sorted(is_rows, key=lambda r: r.date)
    is_half = is_sorted[: len(is_sorted) // 2] if len(is_sorted) >= 2 else is_sorted
    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_q_of(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    return {
        "n": n, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2), "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_half_n": len(is_half), "is_half_exp": _exp(is_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "drop_top5_per_trade": _drop_top5_pt(rows),
        "oos_alone_drop_top5_per_trade": _oos_alone_drop_top5_pt(rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
        "exit_hist": {k: sum(1 for x in rows if x.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


def jaccard_overlap(days_a: set, days_b: set) -> Optional[float]:
    """L174 independence: |A ∩ B| / |A ∪ B| over trade-DAY sets."""
    if not days_a or not days_b:
        return None
    inter = len(days_a & days_b)
    union = len(days_a | days_b)
    return round(inter / union, 3) if union else None


def eleven_gates_opt(m: dict, null: dict, chart_stop_only_oos_pt: Optional[float],
                     overlap_vs_shipped: Optional[float],
                     skipped_days_net: Optional[float]) -> dict:
    ng = null_gate(m.get("oos_exp"), m.get("drop_top5_per_trade"), null)
    g1 = m.get("oos_exp", -1) > 0
    g2 = m.get("positive_quarters_n", 0) >= BAR_POS_Q
    t5 = m.get("top5_day_pct")
    g3 = t5 is not None and t5 < BAR_TOP5
    g4 = m.get("n", 0) >= BAR_N
    g5 = (m.get("drop_top5_per_trade") is not None and m["drop_top5_per_trade"] > 0)
    g6 = m.get("is_half_exp", -1) > 0
    g7 = bool(ng["null_pass"])
    full_oos = m.get("oos_exp")
    artifact = (full_oos is not None and full_oos > 0
                and chart_stop_only_oos_pt is not None and chart_stop_only_oos_pt < 0)
    g8 = not artifact
    oad5 = m.get("oos_alone_drop_top5_per_trade")
    g9 = oad5 is not None and oad5 > 0                                   # L173
    # L174 independence: overlap with shipped #1 must be < ceiling (None = no shipped days
    # to compare -> treat as PASS-with-disclosure, since bear & bull books are disjoint by
    # construction; we still compute and report the number when available).
    g10 = (overlap_vs_shipped is None) or (overlap_vs_shipped < INDEP_OVERLAP_MAX)
    # L174 no-regression: the days this book SKIPS must net NEGATIVE (abstention is correct).
    g11 = (skipped_days_net is not None and skipped_days_net <= 0)
    gates = {
        "g1_oos_per_trade_pos": bool(g1),
        "g2_pos_quarters_ge4of6": bool(g2),
        "g3_top5_lt_200": bool(g3),
        "g4_n_ge_20": bool(g4),
        "g5_drop_top5_pos": bool(g5),
        "g6_is_half_pos": bool(g6),
        "g7_beats_null": bool(g7),
        "g8_no_truncation": bool(g8),
        "g9_oos_alone_drop_top5_pos": bool(g9),
        "g10_independent_vs_shipped": bool(g10),
        "g11_no_regression_skipped_neg": bool(g11),
    }
    gates["clears_all_gates"] = all(gates.values())
    gates["_null_detail"] = ng
    gates["_truncation_artifact"] = bool(artifact)
    gates["_overlap_vs_shipped"] = overlap_vs_shipped
    gates["_skipped_days_net"] = skipped_days_net
    return gates


# ═════════════════════════════════════════════════════════════════════════════════
# OP-16 ANCHOR FIDELITY (for BEAR_RIDE only)
# ═════════════════════════════════════════════════════════════════════════════════
def anchor_capture(rows: list[OptRow]) -> dict:
    """OP-16 edge_capture = sum(pnl on J's WIN-anchor days) - sum(max(0,-pnl) on LOSS-anchor
    days). Positive = takes the winners, doesn't profit/bleed on the losers. The anchors are
    2026 (OOS) so this is a FIDELITY check, not independent OOS."""
    bd = _by_day_opt(rows)
    win_pnl = 0.0; loss_loss = 0.0
    per_anchor = {}
    for d, label in ANCHORS.items():
        pnl = bd.get(d.isoformat(), 0.0)
        took = d.isoformat() in bd
        per_anchor[d.isoformat()] = {"label": label, "took": took, "pnl": round(pnl, 2)}
        if label == "WIN":
            win_pnl += pnl
        else:
            loss_loss += max(0.0, -pnl)
    return {
        "edge_capture": round(win_pnl - loss_loss, 2),
        "win_day_pnl": round(win_pnl, 2),
        "loss_day_loss": round(loss_loss, 2),
        "per_anchor": per_anchor,
        "fidelity_pass": (win_pnl - loss_loss) > 0,
    }


# ═════════════════════════════════════════════════════════════════════════════════
# FUTURES LEG (point-P&L, no theta) — mirrors _b5_vix_regime_dayside
# ═════════════════════════════════════════════════════════════════════════════════
def load_futures(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(FUT_DATA / f"{symbol}_5m_continuous.csv")
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df = df[(df["t"] >= RTH_OPEN) & (df["t"] < RTH_CLOSE)].reset_index(drop=True)
    return df


def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> np.ndarray:
    h = high.to_numpy(float); l = low.to_numpy(float); c = close.to_numpy(float)
    n = len(h)
    tr = np.full(n, np.nan)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(n, np.nan)
    if n < length:
        return out
    out[length - 1] = np.nanmean(tr[:length])
    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def _ema(arr: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(arr).ewm(span=span, adjust=False).mean().to_numpy()


@dataclass(frozen=True)
class FutSig:
    idx: int           # global bar idx; fill at NEXT bar open
    date: dt.date
    side: str          # always "short" (bear)
    chart_stop: float
    structure: str


def detect_fut_signals(fut: pd.DataFrame, structure: str, slow_span: int = 34) -> list[FutSig]:
    """Futures mirror of the 0DTE bear detector: SHORT only, regime-gated (down-trend day +
    below slow EMA + not clean up-trend), one entry/session. No VIX/ribbon stack on futures,
    so the 'not BULL stack' condition is approximated by 'close below the slow EMA' (already
    required) + 'fast EMA below slow EMA' (a stack proxy)."""
    out: list[FutSig] = []
    close_all = fut["close"].to_numpy(float)
    slow_all = _ema(close_all, slow_span)
    fast_all = _ema(close_all, 8)
    for day, g in fut.groupby("date", sort=True):
        g = g.reset_index()  # 'index' = global idx
        if len(g) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(g).to_numpy(float)
        closes = g["close"].to_numpy(float)
        highs = g["high"].to_numpy(float)
        lows = g["low"].to_numpy(float)
        times = g["t"].to_numpy()
        gi_arr = g["index"].to_numpy(int)
        if not _down_trend_side(closes, vwap):
            continue
        for j in range(TREND_BARS, len(g)):
            t = times[j]
            if not (ENTRY_GATE[0] <= t <= ENTRY_GATE[1]):
                if t > ENTRY_GATE[1]:
                    break
                continue
            gi = int(gi_arr[j])
            close_j = closes[j]
            slow = float(slow_all[gi]); fast = float(fast_all[gi])
            if close_j >= slow:          # regime: below slow EMA
                continue
            if fast >= slow:             # stack proxy: not a clean up-trend
                continue
            fire = False
            if structure == "BEAR_CONT":
                fire = close_j < vwap[j]
            elif structure == "BEAR_FBO":
                fire = (highs[j] > vwap[j]) and (close_j < vwap[j])
            elif structure == "BEAR_RIDE":
                lo = max(0, j - SWING_LOOKBACK + 1)
                swing_high = float(np.max(highs[lo:j])) if j > lo else highs[j]
                fire = (highs[j] >= swing_high) and (close_j < swing_high) and (close_j < vwap[j])
            if not fire:
                continue
            stop = float(np.max(highs[:j + 1]))   # short chart-stop = session high so far
            out.append(FutSig(idx=gi, date=day, side="short", chart_stop=stop, structure=structure))
            break
    return out


@dataclass
class FutFill:
    date: dt.date
    side: str
    pnl: float
    bars_held: int
    exit_reason: str


def simulate_fut(df: pd.DataFrame, sig: FutSig, symbol: str, *, atr: np.ndarray,
                 day_end: dict, exit_mode: str = "atr_trail") -> Optional[FutFill]:
    """Fill NEXT bar open; manage to session close. Short-only (bear book)."""
    pv = POINT_VALUE[symbol]
    entry_idx = sig.idx + 1
    if entry_idx >= len(df):
        return None
    if df["date"].iloc[entry_idx] != sig.date:
        return None
    a = atr[sig.idx]
    if np.isnan(a) or a <= 0:
        return None
    slip = SLIP_TICKS * TICK
    raw_entry = float(df["open"].iloc[entry_idx])
    entry = raw_entry - slip                       # short fill worsened by slippage
    atr_stop = entry + ATR_STOP_MULT * a
    chart = max(sig.chart_stop, entry + TICK)
    stop = chart if exit_mode == "chartstop_eod" else min(atr_stop, chart)
    end_idx = day_end[sig.date]
    ll = float(df["low"].iloc[entry_idx])
    exit_price = None; reason = None; bars = 0
    for k in range(entry_idx, end_idx + 1):
        bars += 1
        hi = float(df["high"].iloc[k]); lo = float(df["low"].iloc[k])
        ll = min(ll, lo)
        if exit_mode == "atr_trail":
            stop = min(stop, ll + TRAIL_MULT * a)
        if hi >= stop:
            exit_price = stop + slip; reason = "stop"; break
        if k == end_idx:
            raw = float(df["close"].iloc[k])
            exit_price = raw + slip; reason = "eod"; break
    if exit_price is None:
        raw = float(df["close"].iloc[end_idx])
        exit_price = raw + slip; reason = "eod"
    gross = (entry - exit_price) * pv * FUT_QTY    # short: profit when price falls
    pnl = gross - COMMISSION_RT * FUT_QTY
    return FutFill(date=sig.date, side=sig.side, pnl=pnl, bars_held=bars, exit_reason=reason)


def _by_day_fut(fills: list[FutFill]) -> dict:
    d = defaultdict(float)
    for f in fills:
        d[f.date] += f.pnl
    return dict(d)


def metrics_fut(fills: list[FutFill]) -> dict:
    if not fills:
        return {"n": 0}
    pnls = np.array([f.pnl for f in fills])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    by_day = _by_day_fut(fills)
    day_vals = np.array(sorted(by_day.values(), reverse=True))
    total = float(pnls.sum())
    top5 = float(day_vals[:5].sum()) if len(day_vals) >= 1 else 0.0
    top5_pct = round(100.0 * top5 / total, 1) if total > 0 else None
    drop_days = set(sorted(by_day, key=lambda k: by_day[k], reverse=True)[:5])
    drop_fills = [f for f in fills if f.date not in drop_days]
    drop_pt = round(float(np.mean([f.pnl for f in drop_fills])), 2) if drop_fills else None
    n = len(fills)
    return {
        "n": n, "wr": round(100.0 * len(wins) / n, 1),
        "total_pnl": round(total, 0), "per_trade": round(float(pnls.mean()), 2),
        "top5_day_pct": top5_pct, "drop_top5_per_trade": drop_pt, "n_days": len(by_day),
    }


def by_quarter_fut(fills: list[FutFill]) -> dict:
    q = defaultdict(list)
    for f in fills:
        q[quarter(f.date)].append(f.pnl)
    return {k: {"n": len(v), "total": round(float(sum(v)), 0),
                "per_trade": round(float(np.mean(v)), 2)} for k, v in sorted(q.items())}


def random_null_fut(df: pd.DataFrame, sigs: list[FutSig], symbol: str, *, atr: np.ndarray,
                    day_end: dict, seeds: int = FUT_RANDOM_SEEDS) -> dict:
    """Matched count/day, all-short, random entry bars in the morning window, same exit."""
    per_day = defaultdict(int)
    for s in sigs:
        per_day[s.date] += 1
    if not sigs:
        return {"per_trade": None, "n_replicates": 0}
    eligible = {}
    for d, g in df.groupby("date"):
        idxs = g.index.to_numpy()
        times = g["t"].to_numpy()
        mask = np.array([ENTRY_GATE[0] <= t <= ENTRY_GATE[1] for t in times])
        ok = idxs[mask]
        ok = ok[ok < idxs[-1]]
        eligible[d] = ok
    rng = np.random.default_rng(42)
    means = []
    for _ in range(seeds):
        fills = []
        for d, cnt in per_day.items():
            ok = eligible.get(d)
            if ok is None or len(ok) == 0:
                continue
            chosen = rng.choice(ok, size=min(cnt, len(ok)), replace=False)
            for gi in chosen:
                gi = int(gi)
                cstop = float(df["high"].iloc[max(0, gi - 12):gi + 1].max())
                f = simulate_fut(df, FutSig(idx=gi, date=d, side="short", chart_stop=cstop,
                                            structure="null"), symbol, atr=atr, day_end=day_end)
                if f:
                    fills.append(f)
        if fills:
            means.append(float(np.mean([f.pnl for f in fills])))
    if not means:
        return {"per_trade": None, "n_replicates": 0}
    return {"per_trade": round(float(np.mean(means)), 2),
            "p95": round(float(np.percentile(means, 95)), 2),
            "n_replicates": len(means)}


def eval_fut_cell(df: pd.DataFrame, symbol: str, sigs: list[FutSig], atr: np.ndarray,
                  day_end: dict, is_days: set, oos_days: set, n_q: int) -> dict:
    fills = [f for s in sigs if (f := simulate_fut(df, s, symbol, atr=atr, day_end=day_end)) ]
    oos_fills = [f for f in fills if f.date in oos_days]
    m_all = metrics_fut(fills); m_oos = metrics_fut(oos_fills)
    q = by_quarter_fut(fills)
    pos_q = sum(1 for v in q.values() if v["total"] > 0)
    need_q = math.ceil(0.6 * n_q)
    oos_sigs = [s for s in sigs if s.date in oos_days]
    null_oos = random_null_fut(df, oos_sigs, symbol, atr=atr, day_end=day_end)
    oos_pt = m_oos.get("per_trade"); n_all = m_all.get("n", 0)
    null_pt = null_oos.get("per_trade")
    top5 = m_all.get("top5_day_pct"); drop_pt = m_all.get("drop_top5_per_trade")
    g1 = oos_pt is not None and oos_pt > 0
    g4 = n_all >= 20
    g5 = drop_pt is not None and drop_pt > 0
    g7 = (oos_pt is not None and null_pt is not None and oos_pt > null_pt)
    clears = bool(g1 and g4 and g5 and g7 and pos_q >= need_q and top5 is not None and top5 < 200.0)
    return {
        "symbol": symbol, "structure": sigs[0].structure if sigs else None,
        "n_signals": len(sigs), "n_fills": len(fills),
        "full": m_all, "oos": m_oos, "by_quarter": q,
        "positive_quarters": pos_q, "n_quarters": n_q, "need_quarters": need_q,
        "random_null_oos": null_oos, "clears_core_gates": clears,
    }


# ═════════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════════
def run_opt_structure(structure: str, days, spy, ribbon, ribbon_g, vix_g, rth_full,
                      shipped_bull_days: set, bear_baseline_by_day: dict) -> dict:
    """Run one bear structure across both strike tiers + the full standing bar."""
    sigs = detect_opt_signals(days, ribbon_g, structure)
    sig_days = {str(s.date) for s in sigs}
    # L174 no-regression: 'skipped days' = bear-mirror baseline days this structure did NOT
    # fire on. Net P&L of those skipped days (from the baseline bull/all-day book) must be
    # <= 0 (i.e. abstaining was correct). We use the BEAR_CONT baseline as the reference book.
    skipped_days = set(bear_baseline_by_day) - sig_days
    skipped_net = round(sum(bear_baseline_by_day[d] for d in skipped_days), 2) if skipped_days else None
    tier_results = {}
    for tier_name, so in STRIKE_TIERS.items():
        rows, cov = simulate_opt(sigs, spy, ribbon, vix_g, strike_offset=so,
                                 premium_stop_pct=PREMIUM_STOP)
        m = metrics_opt(rows)
        rows_cs, _ = simulate_opt(sigs, spy, ribbon, vix_g, strike_offset=so,
                                  premium_stop_pct=CHART_STOP_ONLY)
        m_cs = metrics_opt(rows_cs)
        cs_oos = m_cs.get("oos_exp")
        oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
        n_p = len(oos_rows)
        null = random_entry_null(rth_full, n_signals=n_p, n_call=0, n_put=n_p,
                                 strike_offset=so, premium_stop_pct=PREMIUM_STOP,
                                 entry_gate=ENTRY_GATE)
        trade_days = {r.date for r in rows}
        overlap = jaccard_overlap(trade_days, shipped_bull_days)
        gates = eleven_gates_opt(m, null, cs_oos, overlap, skipped_net)
        anchor = anchor_capture(rows) if structure == "BEAR_RIDE" else None
        tier_results[tier_name] = {
            "strike_offset": so, "premium_stop_pct": PREMIUM_STOP, "coverage": cov,
            "metrics": m, "chart_stop_only_oos_exp": cs_oos, "null": null,
            "anchor_fidelity": anchor, "gates": gates,
        }
    return {"structure": structure, "n_signals": len(sigs), "n_sig_days": len(sig_days),
            "skipped_days_net_pnl": skipped_net, "strike_tiers": tier_results}


def main() -> int:
    summary: dict = {
        "kind": "b9_bear_book",
        "slug": "bear-book",
        "angle": "B — regime-conditional bear book (robustness gap: all 3 real edges are bull-biased)",
        "hypothesis": ("Is there a bearish VWAP-native structural edge that works WHEN GATED TO A "
                       "BEARISH REGIME (down-trend day + SPY below the slow EMA + not a clean "
                       "up-stack)? Three bear-mirror structures (BEAR_CONT = mirror of #1, BEAR_FBO "
                       "= mirror of #2, BEAR_RIDE = J's BEARISH_REJECTION_RIDE_THE_RIBBON w/ OP-16 "
                       "anchor check), puts-only, both strike tiers, real-fills + futures, full "
                       "11-gate standing bar incl OOS-ALONE drop-top5 (L173), independence (L174), "
                       "and no-regression (L174)."),
        "run_date": dt.date.today().isoformat(),
        "regime_gate": ("BEARISH regime at entry bar (causal): day-trend side DOWN (first 3 closes "
                        "below VWAP) AND entry close below ribbon slow EMA AND ribbon stack != BULL"),
        "structures": {
            "BEAR_CONT": "bear mirror of #1 — below-VWAP established down-trend continuation",
            "BEAR_FBO": "bear mirror of #2 — failed up-break (poke above VWAP, close back below) on down day",
            "BEAR_RIDE": "J's BEARISH_REJECTION_RIDE_THE_RIBBON — ribbon BEAR + swing-high rejection, ride down (OP-16 anchor check)",
        },
        "standing_bar_gates": {
            "g1": "OOS(2026) per-trade > 0", "g2": "positive in >= 4/6 quarters",
            "g3": "top-5 winning days < 200% of total", "g4": "n_trades >= 20",
            "g5": "full drop-top5 per-trade > 0", "g6": "IS(2025) first-half per-trade > 0",
            "g7": "beats random-entry null (L172)", "g8": "no-truncation (L171)",
            "g9": "OOS-ALONE drop-top5 per-trade > 0 (L173)",
            "g10": f"independence vs #1 vwap_continuation day-overlap < {INDEP_OVERLAP_MAX} (L174)",
            "g11": "no-regression: skipped days net <= 0 (abstention correct, L174)",
        },
    }

    # ── Load SPY + VIX + ribbon ──────────────────────────────────────────────────
    print("[b9] loading SPY+VIX ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix_g = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon_g = compute_ribbon(pd.Series(spy["close"].values))
    ribbon = ribbon_g
    rth_full = spy[(spy["t"] >= RTH_OPEN) & (spy["t"] < RTH_CLOSE)].reset_index(drop=True)
    print(f"[b9] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # ── Shipped #1 (vwap_continuation) day set for the L174 independence check ────
    # #1 is the BULL mirror: first TREND_BARS closes all ABOVE VWAP -> long/CALL, same morning
    # window. We reconstruct its trade-DAY set (signal days) byte-identically to the bear
    # detector so the Jaccard overlap is apples-to-apples.
    shipped_bull_days: set = set()
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        closes = rth["close"].to_numpy(float)
        vwap = session_vwap_asof(rth).to_numpy(float)
        head_c = closes[:TREND_BARS]; head_v = vwap[:TREND_BARS]
        if np.all(head_c > head_v):
            # bull side established; #1 takes the first morning bar -> the day is a #1 trade day.
            times = rth["t"].to_numpy()
            for j in range(TREND_BARS, len(rth)):
                t = times[j]
                if ENTRY_GATE[0] <= t <= ENTRY_GATE[1]:
                    shipped_bull_days.add(str(dc.date)); break
                if t > ENTRY_GATE[1]:
                    break
    print(f"[b9] shipped #1 (vwap_continuation) bull trade-days: {len(shipped_bull_days)}", flush=True)

    # ── No-regression REFERENCE universe by-day P&L (L174) ──
    # The universe = a naive PUT on the first morning bar of EVERY down-trend-side day (no
    # regime sub-filter, no structure trigger) at ATM with the production bear stop. A
    # structure's SKIPPED days are universe-days it did NOT take; g11 requires those to net
    # <= 0 (the regime gate correctly abstained from naive-short-losing days).
    base_sigs = detect_universe_signals(days)
    base_rows, _ = simulate_opt(base_sigs, spy, ribbon, vix_g, strike_offset=0,
                                premium_stop_pct=PREMIUM_STOP)
    bear_baseline_by_day = dict(_by_day_opt(base_rows))
    print(f"[b9] no-regression UNIVERSE (naive-short down-days/ATM) days={len(bear_baseline_by_day)} "
          f"net=${round(sum(bear_baseline_by_day.values()),2)}", flush=True)

    # ── ARENA A: 0DTE real-fills, three structures x two tiers ───────────────────
    struct_results = {}
    for structure in STRUCTURES:
        res = run_opt_structure(structure, days, spy, ribbon, ribbon_g, vix_g, rth_full,
                                shipped_bull_days, bear_baseline_by_day)
        struct_results[structure] = res
        for tier_name in STRIKE_TIERS:
            t = res["strike_tiers"][tier_name]
            m = t["metrics"]; gobj = t["gates"]
            n_pass = sum(1 for k, v in gobj.items() if k.startswith("g") and v is True)
            print(f"[b9-0DTE] {structure:10s} {tier_name:10s} n_sig={res['n_signals']:3d} "
                  f"n={m.get('n','-')} oos_exp=${m.get('oos_exp','-')} (oos_n={m.get('oos_n','-')}) "
                  f"posQ={m.get('positive_quarters','-')} drop5={m.get('drop_top5_per_trade','-')} "
                  f"oosAlone5={m.get('oos_alone_drop_top5_per_trade','-')} "
                  f"overlap={gobj.get('_overlap_vs_shipped')} skipNet={gobj.get('_skipped_days_net')} "
                  f"-> {n_pass}/11 {'ALL PASS' if gobj['clears_all_gates'] else ''}", flush=True)

    summary["arena_0dte"] = {
        "real_fills_authority": ("lib.simulator_real.simulate_trade_real (C1); nearest-cached "
                                 "strike <=4; causal next-bar-open; PUT chart-stop = 12-bar swing high"),
        "strike_tiers": STRIKE_TIERS, "premium_stop": PREMIUM_STOP, "side": SIDE,
        "shipped_bull_trade_days_n": len(shipped_bull_days),
        "bear_baseline_by_day_net": round(sum(bear_baseline_by_day.values()), 2),
        "structures": struct_results,
    }

    # ── ARENA B: futures point-P&L ───────────────────────────────────────────────
    print("\n[b9] loading futures (MES+MNQ) ...", flush=True)
    fut = {sym: load_futures(sym) for sym in ("MES", "MNQ")}
    fatr = {sym: atr_series(fut[sym]["high"], fut[sym]["low"], fut[sym]["close"], ATR_LEN)
            for sym in ("MES", "MNQ")}
    fday_end = {sym: {d: int(g.index[-1]) for d, g in fut[sym].groupby("date")}
                for sym in ("MES", "MNQ")}
    fut_cells = []
    for sym in ("MES", "MNQ"):
        df = fut[sym]
        days_f = sorted(df["date"].unique())
        cut = int(len(days_f) * 0.70)
        is_days = set(days_f[:cut]); oos_days = set(days_f[cut:])
        n_q = len(set(quarter(d) for d in days_f))
        for structure in STRUCTURES:
            sigs = detect_fut_signals(df, structure)
            cell = eval_fut_cell(df, sym, sigs, fatr[sym], fday_end[sym], is_days, oos_days, n_q)
            cell["oos_start"] = str(sorted(oos_days)[0]) if oos_days else None
            fut_cells.append(cell)
            o = cell["oos"]
            print(f"[b9-FUT] {sym} {structure:10s} n={cell['n_signals']:3d} "
                  f"oos_pt={o.get('per_trade')} full_pt={cell['full'].get('per_trade')} "
                  f"posQ={cell['positive_quarters']}/{n_q} drop5={cell['full'].get('drop_top5_per_trade')} "
                  f"-> {'CLEARS-core' if cell['clears_core_gates'] else 'no'}", flush=True)

    summary["arena_futures"] = {
        "point_value": POINT_VALUE, "commission_rt": COMMISSION_RT,
        "slippage_ticks_each_side": SLIP_TICKS, "qty_micros": FUT_QTY,
        "exit": "atr_trail (chart-stop floor + chandelier 2.5x); hard EOD flat; SHORT only",
        "regime_proxy": "no VIX/ribbon-stack on futures -> regime = down-day + close<slow EMA + fast<slow",
        "cells": fut_cells,
    }

    # ── HEADLINE / VERDICT ───────────────────────────────────────────────────────
    opt_clear = []
    for structure in STRUCTURES:
        for tier_name in STRIKE_TIERS:
            g = struct_results[structure]["strike_tiers"][tier_name]["gates"]
            if g["clears_all_gates"]:
                opt_clear.append(f"{structure}/{tier_name}")
    fut_clear = [f"{c['symbol']}/{c['structure']}" for c in fut_cells if c["clears_core_gates"]]

    # best OOS per-trade among n>=20 0DTE cells (for disclosure even if it fails gates)
    best = None
    for structure in STRUCTURES:
        for tier_name in STRIKE_TIERS:
            t = struct_results[structure]["strike_tiers"][tier_name]
            m = t["metrics"]
            if m.get("n", 0) >= BAR_N and m.get("oos_exp") is not None:
                key = m["oos_exp"]
                if best is None or key > best[0]:
                    best = (key, structure, tier_name, m, t["gates"])

    ride_atm = struct_results["BEAR_RIDE"]["strike_tiers"]["ATM_safe2"]
    ride_anchor = ride_atm.get("anchor_fidelity")

    summary["headline"] = {
        "any_0dte_cell_clears_all_11_gates": bool(opt_clear),
        "n_0dte_cells_clearing_all_11": len(opt_clear),
        "cells_clearing_all_11": opt_clear,
        "n_futures_cells_clearing_core_gates": len(fut_clear),
        "futures_cells_clearing_core": fut_clear,
        "best_0dte_oos_per_trade": (
            {"config": f"{best[1]}/{best[2]}", "oos_per_trade": round(best[0], 2),
             "oos_n": best[3].get("oos_n"), "n": best[3].get("n"),
             "clears_all_11": best[4]["clears_all_gates"]} if best else None),
        "bear_ride_anchor_fidelity_ATM": ride_anchor,
        "robustness_note": ("Even a DORMANT regime-gated bear edge is valuable robustness for "
                            "when the regime turns. This bull window is hostile to puts, so a "
                            "FAIL here is the expected/honest outcome — the result of record is "
                            "whether bear alpha EXISTS regime-conditionally."),
    }

    summary["DISCLOSURE"] = {
        "pure_python": "numpy only; $0; no live orders; markets closed",
        "per_trade": "per-trade expectancy reported, not WR alone (OP-14/C4)",
        "is_oos": "IS=2025 / OOS=2026 chronological split; gate 1 decisive",
        "bull_tape": ("2026 is a strong BULL tape (C4/C5) -> puts fight positive drift + faster "
                      "theta on down-moves; a bear book starts at a structural disadvantage. The "
                      "regime gate is the attempt to confine puts to the days they can work."),
        "anchor_caveat": ("OP-16 anchors are 2026 (OOS) dates -> the BEAR_RIDE anchor check is a "
                          "FIDELITY check (does the codified setup take J's PUT winners / skip his "
                          "losers), NOT an independent OOS test."),
        "no_leakage": "VWAP cumulative session (causal); slow EMA causal; day-side from first 3 closes; next-bar fill (C6)",
        "spy_vs_option": "C3/L58 -> tested in BOTH theta-free futures + real 0DTE",
        "null": "0DTE: null_baseline.null_gate (beat MAX + drop5>mean); futures: matched random-bar mean (L172)",
        "truncation": "0DTE: same-strike chart-stop-only sign (L171)",
        "independence": ("L174 day-overlap (Jaccard) vs shipped #1 vwap_continuation; bear & bull "
                         "books are disjoint by construction so overlap is ~0 -> the bear book is "
                         "structurally independent (it does not invert the bull edge's days)."),
        "no_regression": ("L174: reference universe = naive PUT on first morning bar of EVERY "
                          "down-trend-side day (ATM, prod bear stop). skipped-day net = net P&L of "
                          "universe days the regime-gated structure did NOT take; <= 0 means "
                          "abstention was correct (the gate pruned naive-short-losing days)."),
        "no_survivor_pick": "ALL 3 structures x both tiers x both arenas reported with exact pass/fail flags",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[b9] wrote {OUT}", flush=True)

    write_scorecard(summary, struct_results, fut_cells, best, opt_clear, fut_clear, ride_anchor)

    # ── Console verdict ──────────────────────────────────────────────────────────
    print("\n=== B9 REGIME-CONDITIONAL BEAR BOOK — VERDICT ===")
    print(f"0DTE cells clearing ALL 11 gates: {len(opt_clear)} {opt_clear}")
    print(f"FUTURES cells clearing core gates: {len(fut_clear)} {fut_clear}")
    if best:
        print(f"best 0DTE OOS/trade: {best[1]}/{best[2]} = ${round(best[0],2)} "
              f"(oos_n={best[3].get('oos_n')}, clears_all_11={best[4]['clears_all_gates']})")
    if ride_anchor:
        print(f"BEAR_RIDE (ATM) OP-16 anchor fidelity: edge_capture=${ride_anchor['edge_capture']} "
              f"(WIN-day ${ride_anchor['win_day_pnl']}, LOSS-day loss ${ride_anchor['loss_day_loss']}) "
              f"-> {'PASS' if ride_anchor['fidelity_pass'] else 'FAIL'}")
    verdict = "BEAR ALPHA EXISTS regime-conditionally" if opt_clear else \
              "NO standalone bear edge clears the bar in this bull window (expected; keep as robustness watch)"
    print(f"VERDICT: {verdict}")
    return 0


def write_scorecard(summary, struct_results, fut_cells, best, opt_clear, fut_clear, ride_anchor):
    L = []
    L.append("# B9 — REGIME-CONDITIONAL BEAR BOOK (Angle B) — Scorecard")
    L.append("")
    L.append(f"_Generated {summary['run_date']} — pure-Python real-fills (C1), $0, markets closed._")
    L.append("")
    L.append("## The question")
    L.append("")
    L.append("All three real edges (#1 vwap_continuation LIVE, #2 reclaim, #4 vix_regime) are "
             "VWAP-native and **bull-biased**. The robustness gap: **is there a bearish VWAP-native "
             "structural edge that works WHEN GATED TO A BEARISH REGIME** — the book we want on hand "
             "for when the tape flips?")
    L.append("")
    L.append("**Regime gate (causal):** day-trend side DOWN (first 3 closes below VWAP) AND entry "
             "close below the ribbon slow EMA AND ribbon stack != BULL.")
    L.append("")
    L.append("## Standing bar (11 gates)")
    L.append("")
    L.append("g1 OOS/trade>0 · g2 >=4/6 posQ · g3 top5<200% · g4 n>=20 · g5 drop-top5>0 · "
             "g6 IS-half>0 · g7 beats-null (L172) · g8 no-truncation (L171) · "
             "g9 **OOS-ALONE drop-top5>0 (L173)** · g10 **independence vs #1 <0.80 overlap (L174)** · "
             "g11 **no-regression: skipped days net<=0 (L174)**")
    L.append("")
    L.append("## 0DTE real-fills (the production authority)")
    L.append("")
    L.append("| structure | tier | n | OOS n | OOS/trade | posQ | drop5 | OOS-alone5 | overlap#1 | skipNet | gates | verdict |")
    L.append("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|")
    for structure in STRUCTURES:
        for tier_name in STRIKE_TIERS:
            t = struct_results[structure]["strike_tiers"][tier_name]
            m = t["metrics"]; g = t["gates"]
            n_pass = sum(1 for k, v in g.items() if k.startswith("g") and v is True)
            verd = "**CLEARS ALL 11**" if g["clears_all_gates"] else f"{n_pass}/11"
            L.append(f"| {structure} | {tier_name} | {m.get('n','-')} | {m.get('oos_n','-')} | "
                     f"${m.get('oos_exp','-')} | {m.get('positive_quarters','-')} | "
                     f"${m.get('drop_top5_per_trade','-')} | ${m.get('oos_alone_drop_top5_per_trade','-')} | "
                     f"{g.get('_overlap_vs_shipped')} | ${g.get('_skipped_days_net')} | {n_pass}/11 | {verd} |")
    L.append("")
    L.append("## Futures point-P&L (theta-free directional check, SHORT only)")
    L.append("")
    L.append("| symbol | structure | n | OOS/trade | full/trade | posQ | drop5 | core gates |")
    L.append("|---|---|--:|--:|--:|--:|--:|---|")
    for c in fut_cells:
        o = c["oos"]
        L.append(f"| {c['symbol']} | {c['structure']} | {c['n_signals']} | "
                 f"${o.get('per_trade')} | ${c['full'].get('per_trade')} | "
                 f"{c['positive_quarters']}/{c['n_quarters']} | ${c['full'].get('drop_top5_per_trade')} | "
                 f"{'CLEARS' if c['clears_core_gates'] else 'no'} |")
    L.append("")
    L.append("## OP-16 anchor fidelity — BEAR_RIDE (J's BEARISH_REJECTION_RIDE_THE_RIBBON)")
    L.append("")
    if ride_anchor:
        L.append(f"- **edge_capture = ${ride_anchor['edge_capture']}** "
                 f"(WIN-day P&L ${ride_anchor['win_day_pnl']}, LOSS-day loss ${ride_anchor['loss_day_loss']}) "
                 f"-> {'**PASS**' if ride_anchor['fidelity_pass'] else '**FAIL**'}")
        L.append("- Per-anchor:")
        for d, a in ride_anchor["per_anchor"].items():
            L.append(f"  - {d} ({a['label']}): took={a['took']} pnl=${a['pnl']}")
        L.append("- _Caveat: anchors are 2026 (OOS) dates -> this is a FIDELITY check, not independent OOS._")
    else:
        L.append("- (not computed)")
    L.append("")
    L.append("## Verdict")
    L.append("")
    if opt_clear:
        L.append(f"**BEAR ALPHA EXISTS regime-conditionally.** Cells clearing all 11 gates: "
                 f"{', '.join(opt_clear)}. These are dormant-deploy candidates for a bearish regime.")
    else:
        L.append("**NO standalone bear edge clears the 11-gate bar in this 2026 bull window.** This is "
                 "the expected/honest outcome — puts fight positive drift + faster theta. The regime "
                 "gate confines puts to down-days but the bull tape leaves too few clean continuation "
                 "down-days to build a positive-expectancy real-fills book.")
        if best:
            L.append("")
            L.append(f"Least-bad standalone cell: **{best[1]}/{best[2]}** at "
                     f"OOS ${round(best[0],2)}/trade (oos_n={best[3].get('oos_n')}) — still fails the bar.")
        L.append("")
        L.append("**Robustness value:** the harness is now on file. When the regime turns (sustained "
                 "down-trend tape), re-running `_b9_bear_book.py` will re-test these exact structures on "
                 "the new OOS window without rebuild. A regime-gated bear book is the robustness hedge "
                 "the all-bull edge stack is missing.")
    L.append("")
    SCORECARD.write_text("\n".join(L), encoding="utf-8")
    print(f"[b9] wrote {SCORECARD}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
