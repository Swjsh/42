"""RESCUE / STRUCTURAL-GENERALIZE edge test: level_reclaim_fb.

THESIS (generalize the winning SHAPE — not additive confluence):
  The hunt found a 2nd real edge, ``struct_vwap_reclaim_failed_break``: trend side
  -> a FAILED counter-trend VWAP break -> a with-trend VWAP RECLAIM (one causal
  entry/day, chart stop). It clears all 8 gates @ ITM-2 (OOS +$72/tr) but FAILS @
  OTM-2 (Safe-2's $2K tier) on the random-null + truncation gates (C29: OTM
  theta/delta eats the alpha).

  The winning STRUCTURE is "a failed counter-trend break that reclaims with-trend".
  VWAP is just ONE reference line. This script GENERALIZES that exact SHAPE to the
  NAMED STRUCTURAL LEVELS J actually trades against — PDH / PDL / premarket high /
  premarket low / prior close — to see whether a *named-level* reclaim-after-
  failed-break (a) produces more signals and (b) clears all 8 gates at a strike
  whose premium fits the $2K 30% Safe-2 cap (OTM-2 / OTM-1 / ATM), not just ITM-2.

  This is STRUCTURAL generalization (same one-entry/day failed-break->reclaim shape,
  swap the reference from VWAP to a named level), NOT additive confluence (we do
  NOT require VWAP *and* a level; we test named levels in their OWN right). The
  campaign proved stacking confirmations is dead on 0DTE (C4/L122/L154/L166); the
  ONE thing that worked was the structural shape, so we re-use the shape.

NAMED LEVELS (the watcher level set — reconstructed CAUSALLY per day):
  The live ``lib.watchers.level_source.load_named_levels`` reads only TODAY's
  J-curated ``automation/state/key-levels.json`` (schema_version 3) — there is NO
  historical archive (every level-keyed watcher docstring says "historical backtest
  impossible (no key-levels archive)"). So for a 16-month backtest we reconstruct
  the SAME structural named-level family the protocol defines, all look-ahead-safe:
    - PDH  = prior trading day's RTH high   (role: resistance)
    - PDL  = prior trading day's RTH low    (role: support)
    - PMH  = today's PREMARKET high (bars < 09:30 ET)   (role: resistance)
    - PML  = today's PREMARKET low  (bars < 09:30 ET)   (role: support)
    - PC   = prior trading day's RTH close  (pivot)
  Every one is known AT or BEFORE the RTH open -> reading it intraday is causal.
  These are exactly the structural levels key-levels-protocol.md §1-§5 names
  (prior-day extremes, premarket extremes, prior close) and that the support/
  resistance/carry-role watchers fire against. Psychological round numbers are
  EXCLUDED (protocol §6 caps them at ★; level_source forces stars=1) — we do not
  include them, mirroring the live exclusion.

THE DETECTOR — named-level failed-break -> reclaim (one causal entry/day):
  For each named level L (all reconstructed levels, sorted by relevance = nearest
  to the RTH-open price), run the IDENTICAL shape as struct_vwap_reclaim, but
  against L instead of the VWAP series:
    1. TREND SIDE: the first TREND_BARS (3) RTH closes are all on the SAME side of
       L -> that is the day's with-trend side (closes>L -> bullish/CALL;
       closes<L -> bearish/PUT). (Same trend definition; reference swapped to L.)
    2. COUNTER-TREND BREAK: after the trend bars, a bar CLOSES on the WRONG side of
       L (against the morning trend) -> the counter-trend move begins.
    3. FAILS + RECLAIMS: a later bar (<= ENTRY_CUTOFF 10:30 ET) CLOSES back across L
       in the ORIGINAL trend direction -> the counter move failed and price
       reclaimed L with-trend. THAT reclaim bar is the entry (side = morning trend
       side). Fill = NEXT bar open (sim handles it).
  Stop = the counter-trend excursion extreme during the failed break (for a CALL:
  the LOW printed while below L; for a PUT: the HIGH) — the structural invalidation.
  ONE entry per day: across all levels we take the EARLIEST reclaim bar of the day
  (first level to complete the shape), so it stays one causal entry/day exactly
  like the VWAP version (no per-level stacking, no multi-entry inflation).

  No look-ahead: trend side, break, reclaim, and excursion extreme each read only
  bars[0..j]; PDH/PDL/PC are prior-session facts; PMH/PML are pre-09:30 facts.

REAL FILLS (C1): lib.simulator_real.simulate_trade_real on real OPRA bars
  (nearest-cached strike snap <=4, causal next-bar-open entry, chart-stop via
  rejection_level). Report the FULL strike ladder so we find the BEST TRADEABLE
  strike: ITM-2, ITM-1, ATM, OTM-1, OTM-2 (per C29 gates do not transfer across
  tiers — each reported independently with ALL 8 gates).

ALL 8 GATES MANDATORY (anti-cherry-pick 2.10; reported for EVERY strike tier):
  G1 OOS(2026) per-trade > 0
  G2 positive_quarters >= 4/6
  G3 top5_day_pct < 200
  G4 n_trades >= 20
  G5 drop-top5-day per-trade > 0          (concentration robustness)
  G6 IS(2025) FIRST-HALF per-trade > 0    (in-sample stability)
  G7 beats random-entry null              (coin-flip null_pass AND same-day/same-side
                                           mean+std, ~20 seeds; L172)
  G8 no-truncation (L171): per-trade SIGN holds -8% stop -> chart-stop-only (-0.99)

A Safe-2-TRADEABLE winner must clear ALL 8 gates at a strike whose premium fits the
$2K 30% cap (OTM-2 / OTM-1 / ATM) — not only ITM-2.

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/rescue-level_reclaim_fb.json.

Run: backtest/.venv/Scripts/python.exe \
       backtest/autoresearch/_rescue_level_reclaim_fb.py
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

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
# Reuse the edgehunt data normalizers so the bar series is byte-for-byte identical
# to the validated vwap_continuation / struct_vwap_reclaim runs (no drift, C14).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
    RTH_OPEN,
    RTH_CLOSE,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "rescue-level_reclaim_fb.json"

# ── Config ──────────────────────────────────────────────────────────────────
# Full strike ladder so we find the BEST TRADEABLE strike (negative=ITM, positive=OTM;
# verified in simulator_real lines 357-364: puts strike=atm-offset, calls strike=atm+offset).
STRIKE_LADDER = [(-2, "ITM2"), (-1, "ITM1"), (0, "ATM"), (1, "OTM1"), (2, "OTM2")]
# Strikes whose premium fits the Safe-2 $2K 30% cap (OTM/ATM tiers).
SAFE2_TRADEABLE_TIERS = frozenset({"ATM", "OTM1", "OTM2"})
SURV_PREMIUM_STOP = -0.08      # -8% premium stop
CHART_STOP_ONLY = -0.99        # for the no-truncation fraud gate (G8)

N_NULL_SEEDS = 20              # L172
MIN_LEVEL_DISTANCE = 0.05      # ignore degenerate "levels" within 5c of each other / price
PREMARKET_OPEN = dt.time(4, 0)  # earliest premarket bar we count (causal premarket window)


# ─────────────────────────────────────────────────────────────────────────────
# NAMED-LEVEL RECONSTRUCTION (causal; mirrors key-levels-protocol structural family)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NamedLevel:
    price: float
    role: str          # "resistance" | "support" | "pivot"
    name: str          # PDH | PDL | PMH | PML | PC


def build_named_levels(spy_df: pd.DataFrame, days: list[DayCtx]) -> dict[dt.date, list[NamedLevel]]:
    """Per-day causal named-level set: PDH, PDL, PMH, PML, PC.

    PDH/PDL/PC = PRIOR trading day's RTH high/low/close (known before today opens).
    PMH/PML    = today's premarket high/low (bars in [04:00, 09:30) ET, all < open).
    Every value is known AT/BEFORE the RTH open -> causal for all intraday reads.
    """
    # prior-day RTH extremes/close, keyed by date, built once in chronological order.
    prior_rth_high = prior_rth_low = prior_rth_close = None
    levels_by_day: dict[dt.date, list[NamedLevel]] = {}
    # group the FULL day (includes premarket) so we can read pre-09:30 bars.
    for d, day in spy_df.groupby("date", sort=True):
        rth = day[(day["t"] >= RTH_OPEN) & (day["t"] < RTH_CLOSE)]
        lvls: list[NamedLevel] = []
        if prior_rth_high is not None:
            lvls.append(NamedLevel(prior_rth_high, "resistance", "PDH"))
        if prior_rth_low is not None:
            lvls.append(NamedLevel(prior_rth_low, "support", "PDL"))
        if prior_rth_close is not None:
            lvls.append(NamedLevel(prior_rth_close, "pivot", "PC"))
        pre = day[(day["t"] >= PREMARKET_OPEN) & (day["t"] < RTH_OPEN)]
        if len(pre):
            lvls.append(NamedLevel(float(pre["high"].max()), "resistance", "PMH"))
            lvls.append(NamedLevel(float(pre["low"].min()), "support", "PML"))
        levels_by_day[d] = [lv for lv in lvls if lv.price and lv.price > 0]
        # roll prior-day facts for the NEXT iteration (this day becomes "prior" tomorrow)
        if len(rth):
            prior_rth_high = float(rth["high"].max())
            prior_rth_low = float(rth["low"].min())
            prior_rth_close = float(rth["close"].iloc[-1])
    return levels_by_day


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL DETECTOR — named-level reclaim-after-failed-break (one entry/day)
# (IDENTICAL shape to struct_vwap_reclaim; reference swapped VWAP -> named level L)
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side_level(closes, level: float, n: int) -> Optional[str]:
    """Day's with-trend side relative to a FIXED named level: first n RTH closes
    all on the same side of L. 'C' if all above, 'P' if all below, else None."""
    head = closes[:n]
    if len(head) < n:
        return None
    if np.all(head > level):
        return "C"
    if np.all(head < level):
        return "P"
    return None


def _detect_for_level(rth: pd.DataFrame, level: float) -> Optional[Signal]:
    """Run the failed-break->reclaim shape against ONE named level L. Returns the
    (earliest) reclaim Signal for this level, or None. All reads causal (bars[0..j])."""
    closes = rth["close"].values
    highs = rth["high"].values
    lows = rth["low"].values
    times = rth["t"].values
    idxs = rth.index.tolist()
    side = _trend_side_level(closes, level, TREND_BARS)
    if side is None:
        return None
    broke = False
    excursion_ext: Optional[float] = None
    for j in range(TREND_BARS, len(rth)):
        if times[j] > ENTRY_CUTOFF:
            break
        c = closes[j]
        if side == "C":
            # counter-trend break = close BELOW L (against bullish trend)
            if not broke:
                if c < level:
                    broke = True
                    excursion_ext = lows[j]
                continue
            excursion_ext = min(excursion_ext, lows[j]) if excursion_ext is not None else lows[j]
            # reclaim = close BACK ABOVE L in trend direction -> entry
            if c > level:
                return Signal(bar_idx=int(idxs[j]), side="C", stop_level=float(excursion_ext),
                              note="level_reclaim_fb")
        else:
            # counter-trend break = close ABOVE L (against bearish trend)
            if not broke:
                if c > level:
                    broke = True
                    excursion_ext = highs[j]
                continue
            excursion_ext = max(excursion_ext, highs[j]) if excursion_ext is not None else highs[j]
            # reclaim = close BACK BELOW L -> entry
            if c < level:
                return Signal(bar_idx=int(idxs[j]), side="P", stop_level=float(excursion_ext),
                              note="level_reclaim_fb")
    return None


def detect_signals(days: list[DayCtx],
                   levels_by_day: dict[dt.date, list[NamedLevel]]) -> list[Signal]:
    """One causal level_reclaim_fb entry/day: across all named levels, take the
    EARLIEST reclaim bar of the day (first level to complete the shape)."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 3:
            continue
        lvls = levels_by_day.get(dc.date, [])
        if not lvls:
            continue
        # de-dupe near-identical level prices (PC ~ PDH on a doji day etc.)
        seen: list[float] = []
        uniq: list[NamedLevel] = []
        for lv in lvls:
            if all(abs(lv.price - s) > MIN_LEVEL_DISTANCE for s in seen):
                seen.append(lv.price)
                uniq.append(lv)
        best: Optional[Signal] = None
        best_name = ""
        for lv in uniq:
            sg = _detect_for_level(rth, lv.price)
            if sg is None:
                continue
            if best is None or sg.bar_idx < best.bar_idx:
                best = sg
                best_name = lv.name
        if best is not None:
            out.append(Signal(bar_idx=best.bar_idx, side=best.side,
                              stop_level=best.stop_level,
                              note=f"level_reclaim_fb:{best_name}"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set on real OPRA fills (v15 default exits)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    level: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct
                 ) -> tuple[list[TradeRow], dict]:
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
            qty=QTY, setup="LEVEL_RECLAIM_FB", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        lvl_name = sg.note.split(":")[-1] if ":" in (sg.note or "") else "?"
        rows.append(TradeRow(
            date=str(d), side=sg.side,
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            level=lvl_name,
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure)
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
    """Per-trade mean after removing the k highest-P&L DAYS entirely."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    is_sorted = sorted(is_rows, key=lambda r: r.date)
    half = len(is_sorted) // 2
    is_first_half = is_sorted[:half] if half else []

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

    by_level = {}
    for lv in sorted({r.level for r in rows}):
        s = [r.pnl for r in rows if r.level == lv]
        if s:
            by_level[lv] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                            "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                            "total": round(sum(s), 2)}

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "max_drawdown_day": _max_dd_by_day(rows),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_n": len(is_first_half), "is_first_half_exp": _exp(is_first_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "by_side": by_side,
        "by_level": by_level,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


def _max_dd_by_day(rows: list[TradeRow]) -> Optional[float]:
    """Max peak-to-trough drawdown of the cumulative daily-P&L equity curve."""
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
        max_dd = min(max_dd, eq - peak)
    return round(float(max_dd), 2)


# ─────────────────────────────────────────────────────────────────────────────
# G7 — same-day/same-side random null (the HARD control: isolates trigger TIMING
# from day+side selection). Same construction as struct_vwap_reclaim.
# ─────────────────────────────────────────────────────────────────────────────
def sameday_null(signals, spy, ribbon, vix, days, *, seeds, strike_offset,
                 premium_stop_pct) -> dict:
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
    per_seed_exp, per_seed_oos_exp = [], []
    for seed in range(seeds):
        rng = np.random.default_rng(7000 + seed)
        rand_sigs = []
        for d, sd, stop in sig_specs:
            elig = day_bars.get(d)
            if not elig:
                continue
            bidx = int(rng.choice(elig))
            rand_sigs.append(Signal(bar_idx=bidx, side=sd, stop_level=stop, note="rand"))
        rows, _ = simulate_set(rand_sigs, spy, ribbon, vix, strike_offset=strike_offset,
                               premium_stop_pct=premium_stop_pct)
        if rows:
            m = metrics(rows)
            per_seed_exp.append(m["exp_dollar"])
            per_seed_oos_exp.append(m["oos_exp"])
    if not per_seed_exp:
        return {"seeds": 0}
    return {
        "seeds": len(per_seed_exp),
        "null_exp_mean": round(float(np.mean(per_seed_exp)), 2),
        "null_exp_min": round(float(np.min(per_seed_exp)), 2),
        "null_exp_max": round(float(np.max(per_seed_exp)), 2),
        "null_exp_std": round(float(np.std(per_seed_exp)), 2),
        "null_oos_exp_mean": round(float(np.mean(per_seed_oos_exp)), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate one strike tier: all 8 gates
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_tier(signals, spy, ribbon, vix, days, *, strike_offset, tier_label) -> dict:
    rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                             premium_stop_pct=SURV_PREMIUM_STOP)
    m = metrics(rows)
    if not m.get("n"):
        return {"tier": tier_label, "strike_offset": strike_offset, "coverage": cov,
                "metrics": m, "gates": {}, "clears_all_gates": False,
                "note": "no filled trades"}

    # G8 no-truncation: same signals at chart-stop-only
    cs_rows, _ = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                              premium_stop_pct=CHART_STOP_ONLY)
    cs_m = metrics(cs_rows)
    trunc_artifact = is_truncation_artifact(
        best_per_trade=m["exp_dollar"],
        chart_stop_only_per_trade=cs_m.get("exp_dollar"),
        best_premium_stop_pct=SURV_PREMIUM_STOP,
    )
    sign_stable_full = bool(cs_m.get("n") and (m["exp_dollar"] > 0) == (cs_m["exp_dollar"] > 0))
    sign_stable_oos = bool(cs_m.get("oos_n") and (m.get("oos_exp", 0) > 0) == (cs_m.get("oos_exp", 0) > 0))
    truncation_safe = bool((not trunc_artifact) and sign_stable_full and sign_stable_oos)

    # G7 nulls — STANDARD coin-flip null (all RTH) + same-day/same-side null (harder)
    rth_all = pd.concat([dc.rth for dc in days]).sort_index().reset_index(drop=True)
    n_call = sum(1 for s in signals if s.side == "C")
    n_put = sum(1 for s in signals if s.side == "P")
    coin = random_entry_null(
        rth_all, n_signals=len(signals), n_call=n_call, n_put=n_put,
        strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP, seeds=N_NULL_SEEDS)
    coin_g = null_gate(m["exp_dollar"], m.get("drop_top5_day_per_trade"), coin)
    sameday = sameday_null(signals, spy, ribbon, vix, days, seeds=N_NULL_SEEDS,
                           strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    beats_sameday = bool(
        sameday.get("seeds") and
        m["exp_dollar"] > sameday["null_exp_mean"] + sameday.get("null_exp_std", 0.0))
    oos_beats_sameday = bool(
        sameday.get("seeds") and (m.get("oos_exp", 0) or 0) > sameday.get("null_oos_exp_mean", 9e9))
    beats_null = bool(coin_g["null_pass"] and beats_sameday)

    gates = {
        "G1_oos_per_trade_positive": {"pass": bool(m.get("oos_exp", -1) > 0),
                                      "value": m.get("oos_exp"), "oos_n": m.get("oos_n")},
        "G2_positive_quarters_ge_4": {"pass": bool(m.get("positive_quarters_n", 0) >= 4),
                                      "value": m.get("positive_quarters")},
        "G3_top5_day_pct_lt_200": {"pass": bool(m.get("top5_day_pct") is not None
                                                and m["top5_day_pct"] < 200.0),
                                   "value": m.get("top5_day_pct")},
        "G4_n_ge_20": {"pass": bool(m.get("n", 0) >= 20), "value": m.get("n")},
        "G5_drop_top5_per_trade_positive": {"pass": bool(m.get("drop_top5_day_per_trade") is not None
                                                         and m["drop_top5_day_per_trade"] > 0),
                                            "value": m.get("drop_top5_day_per_trade")},
        "G6_is_first_half_positive": {"pass": bool(m.get("is_first_half_exp", -1) > 0
                                                   and m.get("is_first_half_n", 0) > 0),
                                      "value": m.get("is_first_half_exp"),
                                      "is_first_half_n": m.get("is_first_half_n")},
        "G7_beats_random_null": {
            "pass": beats_null,
            "coinflip_null": {**coin, **coin_g},
            "sameday_null": {**sameday, "beats_sameday_mean_plus_std": beats_sameday,
                             "oos_beats_sameday_mean": oos_beats_sameday},
        },
        "G8_no_truncation": {
            "pass": truncation_safe,
            "stop8_exp": m["exp_dollar"], "chartstop_exp": cs_m.get("exp_dollar"),
            "stop8_oos_exp": m.get("oos_exp"), "chartstop_oos_exp": cs_m.get("oos_exp"),
            "stop8_total": m["total_dollar"], "chartstop_total": cs_m.get("total_dollar"),
            "is_truncation_artifact": trunc_artifact,
            "sign_stable_full": sign_stable_full, "sign_stable_oos": sign_stable_oos,
        },
    }
    clears_all = all(g["pass"] for g in gates.values())
    caveats = []
    if clears_all and not oos_beats_sameday:
        caveats.append("oos_lift_within_sameday_null_band: OOS per-trade is below the same-day "
                       "random-entry null OOS mean -> the OOS edge is largely day+side selection, "
                       "not trigger precision (the trigger DOES beat the full-sample null and the "
                       "coin-flip null; full-sample clears every gate).")
    tier_name = (f"ITM{abs(strike_offset)}" if strike_offset < 0
                 else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}"))
    return {
        "tier": tier_label,
        "strike_offset": strike_offset,
        "strike_tier_name": tier_name,
        "safe2_tradeable_tier": tier_name in SAFE2_TRADEABLE_TIERS,
        "coverage": cov,
        "metrics": m,
        "gates": gates,
        "clears_all_gates": clears_all,
        "n_gates_passed": sum(1 for g in gates.values() if g["pass"]),
        "caveats": caveats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[rescue-level-reclaim-fb] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[rescue] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    levels_by_day = build_named_levels(spy, days)
    n_lvl_days = sum(1 for d in days if levels_by_day.get(d.date))
    print(f"[rescue] named levels reconstructed for {n_lvl_days}/{n_days} days "
          f"(PDH/PDL/PC/PMH/PML)", flush=True)

    signals = detect_signals(days, levels_by_day)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    level_ct: dict[str, int] = defaultdict(int)
    for s in signals:
        level_ct[s.note.split(":")[-1]] += 1
    print(f"[rescue] level_reclaim_fb signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct} "
          f"by_level={dict(level_ct)}", flush=True)

    tiers = {}
    for off, lbl in STRIKE_LADDER:
        blk = evaluate_tier(signals, spy, ribbon, vix, days,
                            strike_offset=off, tier_label=lbl)
        tiers[lbl] = blk
        m = blk.get("metrics", {})
        print(f"\n[{lbl} off={off:+d}] n={m.get('n')} exp=${m.get('exp_dollar')} "
              f"oos_exp=${m.get('oos_exp')} (oos_n={m.get('oos_n')}) "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"droptop5=${m.get('drop_top5_day_per_trade')} isH1=${m.get('is_first_half_exp')} "
              f"maxDD=${m.get('max_drawdown_day')}", flush=True)
        for gname, g in blk.get("gates", {}).items():
            print(f"    {gname}: {'PASS' if g['pass'] else 'FAIL'} "
                  f"(value={g.get('value', '-')})", flush=True)
        print(f"    => clears_all_gates={blk.get('clears_all_gates')} "
              f"({blk.get('n_gates_passed')}/8)  safe2_tradeable_tier="
              f"{blk.get('safe2_tradeable_tier')}", flush=True)

    # ── Pick BEST TRADEABLE strike: prefer a Safe-2-tradeable tier (ATM/OTM1/OTM2)
    # that clears all 8 gates; else best ITM that clears all gates; else "NONE".
    def _oos(t):
        return tiers[t].get("metrics", {}).get("oos_exp", -9e9) or -9e9
    cleared = [t for t in tiers if tiers[t].get("clears_all_gates")]
    safe2_cleared = [t for t in cleared if tiers[t].get("safe2_tradeable_tier")]
    if safe2_cleared:
        best_tradeable = max(safe2_cleared, key=_oos)
    elif cleared:
        best_tradeable = max(cleared, key=_oos)
    else:
        best_tradeable = "NONE"
    safe2_any = bool(safe2_cleared)

    # primary reporting tier for the schema = the best tradeable (or ITM2 fallback view)
    primary_key = best_tradeable if best_tradeable != "NONE" else "ITM2"
    primary = tiers.get(primary_key, {})
    pm = primary.get("metrics", {})
    pg = primary.get("gates", {})

    coin = pg.get("G7_beats_random_null", {}).get("coinflip_null", {})
    beats_null = bool(pg.get("G7_beats_random_null", {}).get("pass"))
    truncation_safe = bool(pg.get("G8_no_truncation", {}).get("pass"))
    is_half_positive = bool(pg.get("G6_is_first_half_positive", {}).get("pass"))
    clears_all = bool(primary.get("clears_all_gates"))
    primary_caveats = primary.get("caveats", [])

    if best_tradeable == "NONE":
        verdict = ("REJECTED — generalizing the failed-break->reclaim SHAPE to NAMED LEVELS "
                   "(PDH/PDL/PC/PMH/PML) clears all 8 gates at NO strike tier. The structural "
                   "shape's edge does not survive the named-level reference swap on real fills.")
    elif safe2_any:
        verdict = (f"PROMOTABLE + SAFE-2 TRADEABLE — clears all 8 gates at {primary.get('strike_tier_name')} "
                   f"(a tier whose premium fits the $2K 30% cap). Best tradeable strike = "
                   f"{primary.get('strike_tier_name')} (OOS ${pm.get('oos_exp')}/tr, "
                   f"maxDD ${pm.get('max_drawdown_day')}).")
        if primary_caveats:
            verdict += (" CAVEAT: OOS per-trade sits inside the same-day random-entry null band "
                        "-> OOS edge is largely day+side selection, not trigger precision; still "
                        "clears the coin-flip null and every coded gate full-sample.")
    else:
        verdict = (f"PROMOTABLE (ITM-ONLY, NOT Safe-2 tradeable) — clears all 8 gates only at "
                   f"{primary.get('strike_tier_name')} (ITM premium exceeds the $2K 30% cap); "
                   f"NO OTM/ATM tier clears all gates (C29: OTM theta/delta eats the alpha, same "
                   f"failure mode as struct_vwap_reclaim @ OTM-2).")
        if primary_caveats:
            verdict += (" CAVEAT: OOS per-trade sits inside the same-day random-entry null band "
                        "-> OOS edge is largely day+side selection, not trigger precision.")

    summary = {
        "hypothesis": ("level_reclaim_fb: GENERALIZE the winning failed-break->reclaim SHAPE from "
                       "VWAP to NAMED LEVELS (PDH/PDL/premarket H/L/prior close). Price breaks a "
                       "key level counter-trend, fails, reclaims with-trend -> one causal entry/day. "
                       "STRUCTURAL generalization of struct_vwap_reclaim (reference swapped VWAP->level), "
                       "NOT additive confluence."),
        "kind": "structural_one_entry_per_day",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "opra_fill_cutoff": "2026-05-29 (signals after drop as cache_miss; OOS fills = Jan..May 2026)",
        "named_levels": {
            "source": ("reconstructed CAUSALLY per day (no historical key-levels.json archive exists; "
                       "live level_source.load_named_levels reads only TODAY's file). Family mirrors "
                       "key-levels-protocol §1-§5 structural levels."),
            "levels": ["PDH=prior-day RTH high", "PDL=prior-day RTH low", "PC=prior-day RTH close",
                       "PMH=premarket high (bars<09:30)", "PML=premarket low (bars<09:30)"],
            "excluded": "psychological / round-number levels (protocol §6 caps at ★; live level_source forces stars=1)",
            "level_days": n_lvl_days,
        },
        "detector": ("one causal entry/day: for each named level L, trend side (first 3 RTH closes "
                     "same side of L) -> counter-trend break of L (close wrong side) -> with-trend "
                     "reclaim of L (close back across) <=10:30 ET; across all levels take the EARLIEST "
                     "reclaim bar of the day. entry=reclaim bar, fill=next bar open; chart stop = "
                     "failed-break excursion extreme. IDENTICAL shape to struct_vwap_reclaim, reference "
                     "swapped VWAP->named level."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "strike_ladder": [t for _, t in STRIKE_LADDER],
                   "safe2_tradeable_tiers": sorted(SAFE2_TRADEABLE_TIERS)},
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "signal_level_count": dict(level_ct),
        "eight_gates": {
            "G1": "OOS(2026) per-trade > 0",
            "G2": "positive_quarters >= 4/6",
            "G3": "top5_day_pct < 200",
            "G4": "n_trades >= 20",
            "G5": "drop-top5-day per-trade > 0",
            "G6": "IS(2025) first-half per-trade > 0",
            "G7": "beats random-entry null (coin-flip null_pass AND same-day mean+std, ~20 seeds)",
            "G8": "no-truncation: sign holds -8% -> chart-stop-only (-0.99)",
        },
        "tiers": tiers,
        "best_tradeable_strike": (primary.get("strike_tier_name") if best_tradeable != "NONE" else "NONE"),
        "safe2_tradeable": safe2_any,
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 gates reported for EVERY strike tier in the ladder "
                               "(ITM2/ITM1/ATM/OTM1/OTM2); a tier that fails any gate is marked "
                               "clears_all_gates=false (anti-pattern 2.10)."),
            "structural_not_additive": ("ONE causal entry/day with a structural chart stop; named "
                                        "levels tested in their OWN right (no VWAP+level stacking); "
                                        "additive confluence is dead on 0DTE."),
            "level_reconstruction": ("named levels reconstructed causally (prior-day extremes/close + "
                                     "premarket extremes) because no historical key-levels.json archive "
                                     "exists; live engine reads J-curated levels which overlap this set."),
            "strike_tier_caveat": "C29 — gates do not transfer across strike tiers; reported per tier.",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "fraud_gates": ("G7 random-entry null (coin-flip + same-day/same-side, 20 seeds) + "
                            "G8 no-truncation (sign must hold -8% -> chart-stop-only)."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[rescue] wrote {OUT}", flush=True)

    print("\n=== LEVEL_RECLAIM_FB VERDICT ===")
    print(f"n_signals={len(signals)}  fired {summary['signal_fire_day_pct']}% of {n_days} days")
    print(f"best_tradeable_strike={summary['best_tradeable_strike']}  safe2_tradeable={safe2_any}")
    print(f"primary tier ({primary.get('strike_tier_name')}): n={pm.get('n')} exp=${pm.get('exp_dollar')} "
          f"oos_exp=${pm.get('oos_exp')} posQ={pm.get('positive_quarters')} "
          f"top5%={pm.get('top5_day_pct')} maxDD=${pm.get('max_drawdown_day')}")
    print(f"clears_all_gates={clears_all}  beats_null={beats_null}  "
          f"truncation_safe={truncation_safe}  is_half_positive={is_half_positive}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
