"""SELECTION test: vwap_plus_confluence -- sharpen the ONE survivor.

HYPOTHESIS (J): take the proven vwap_continuation signals (the only mechanical survivor,
+$78/tr ITM-2) but keep ONLY the high-confluence SUBSET -- those that ALSO have, AT ENTRY
TIME (causal), all three independent confirmations:
    (1) a NAMED-LEVEL confluence within $0.30 of the entry spot,
    (2) RIBBON alignment (stack BULL for a call / BEAR for a put), AND
    (3) entry-bar VOLUME >= 1.3x the trailing 20-bar baseline.
Does the high-confluence subset have materially better per-trade / lower drawdown than
vwap-alone? If SELECTION sharpens the proven edge -> shippable. If it just thins N without
lifting per-trade (or breaks a gate), it FAILS -- honest either way.

This is the THESIS the whole research program is now testing: SELECTION/CONFLUENCE is the
edge -- multiple independent confirmations convert a coin-flip into an edge. (~32 mechanical
daily strategies were coin-flips; vwap_continuation is the lone SELECTIVE survivor.)

REUSE (no drift, C14):
  * signals  = _edgehunt_vwap_continuation.detect_signals (BYTE-FOR-BYTE the validated
    j_daily_pattern_ratify / vwap_continuation_watcher detector).
  * fills     = lib.simulator_real.simulate_trade_real (real OPRA bars, the ONLY WR
    authority, C1). SURVIVOR STRUCTURE: strike_offset=-2 (ITM-2), premium_stop_pct=-0.08,
    v15 exits (tp1 0.30 / runner 2.5 / chandelier trail 0.20).
  * strike snap = infinite_ammo _nearest_cached_strike / _strike_from_spot.
  * named levels = the codebase's causal historical proxy set (named_level_bounce_scan
    convention): PDH/PDL/PDC (prior RTH day high/low/close), 5-session hi/lo, $5 round
    numbers. ALL known at entry time -> no look-ahead (C6).
  * ribbon = lib.ribbon.compute_ribbon stack at the ENTRY bar.

ALL GATES MANDATORY (deterministic, in-script; anti-pattern 2.10 = no cherry-picking).
The SELECTED subset must clear EVERY one or it does NOT ship:
  G1  OOS(2026) per-trade > 0
  G2  positive_quarters >= 4/6
  G3  top5-day < 200%
  G4  n_trades >= 20
  G5  drop-top-5-DAYS still > 0 (edge survives removing the 5 best days)
  G6  beats a RANDOM-entry null (same exit/strike/stop, same per-day count & side,
      ~20 seeds): subset per-trade must exceed mean(null)+1sd  (not just the mean)
  G7  no-truncation: sign does NOT invert at chart-stop-only (premium_stop=-0.99)
  G8  IN-SAMPLE (2025) half is ALSO positive (reject the IS-neg / OOS-pos single-regime
      artifact -- the futures trap)

OP-20 disclosure: per-trade EXPECTANCY (not WR alone, OP-14), IS/OOS split, positive
quarters, top5-day concentration, SPY-direction != option edge (real OPRA fills).

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed.
Writes analysis/recommendations/sel-vwap_plus_confluence.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sel_vwap_plus_confluence.py
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
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals,
    _normalize_spy,
    _align_vix,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sel-vwap_plus_confluence.json"
SLUG = "vwap_plus_confluence"

# ── SURVIVOR STRUCTURE (primary, per task spec) ───────────────────────────────
STRIKE_OFFSET = -2          # ITM-2 (the +$78/tr survivor config)
PREMIUM_STOP_PCT = -0.08    # v15 asymmetric (bull -8%); we use -8% as the survivor base
QTY = 3
MAX_STRIKE_STEPS = 4
# v15 exits
TP1 = 0.30
RUNNER = 2.5
TRAIL = 0.20                # chandelier trailing 20% off HWM

# ── SELECTION knobs (the hypothesis) ──────────────────────────────────────────
LEVEL_CONFLUENCE_DOLLARS = 0.30   # entry spot within $0.30 of a named level
VOL_MULT_MIN = 1.30               # entry-bar volume >= 1.3x trailing 20-bar baseline
VOL_BASELINE_BARS = 20
ROUND_STEP = 5.0                  # $5 SPY round numbers (street-watched)
PRIOR_DAY_LOOKBACK = 5            # 5-session hi/lo

# ── OOS split + gate bars ─────────────────────────────────────────────────────
OOS_YEAR = 2026
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0
NULL_SEEDS = 20

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL NAMED-LEVEL SET (known at entry time -> no look-ahead, C6)
# ─────────────────────────────────────────────────────────────────────────────
def build_prior_levels(spy: pd.DataFrame) -> dict[dt.date, list[float]]:
    """Per trading day: PDH, PDL, PDC (prior RTH day) + 5-session RTH hi/lo.

    Strictly causal: the levels for day D use only RTH bars from days < D.
    """
    by_day: dict[dt.date, pd.DataFrame] = {}
    for d, day in spy.groupby("date", sort=True):
        rth = day[(day["t"] >= RTH_OPEN) & (day["t"] < RTH_CLOSE)]
        if len(rth):
            by_day[d] = rth
    ordered = sorted(by_day.keys())
    out: dict[dt.date, list[float]] = {}
    for i, d in enumerate(ordered):
        if i == 0:
            out[d] = []
            continue
        prev = by_day[ordered[i - 1]]
        pdh = float(prev["high"].max())
        pdl = float(prev["low"].min())
        pdc = float(prev["close"].iloc[-1])
        lvls = [pdh, pdl, pdc]
        # 5-session rolling hi/lo over the prior up-to-5 RTH days
        lookback_days = ordered[max(0, i - PRIOR_DAY_LOOKBACK):i]
        hi5 = max(float(by_day[x]["high"].max()) for x in lookback_days)
        lo5 = min(float(by_day[x]["low"].min()) for x in lookback_days)
        lvls.extend([hi5, lo5])
        out[d] = sorted(set(round(x, 2) for x in lvls))
    return out


def nearest_named_level(spot: float, day_levels: list[float]) -> tuple[Optional[float], float]:
    """Nearest named level (prior-day set OR $5 round) and its distance to `spot`."""
    cands = list(day_levels)
    # $5 round numbers bracketing the spot (always available, street-watched)
    lo_round = np.floor(spot / ROUND_STEP) * ROUND_STEP
    cands.extend([lo_round, lo_round + ROUND_STEP])
    best_lvl, best_d = None, float("inf")
    for lv in cands:
        dd = abs(spot - lv)
        if dd < best_d:
            best_lvl, best_d = lv, dd
    return best_lvl, best_d


# ─────────────────────────────────────────────────────────────────────────────
# SELECTION filter (all three confirmations, causal at the entry bar)
# ─────────────────────────────────────────────────────────────────────────────
def passes_selection(sg, spy: pd.DataFrame, ribbon: pd.DataFrame,
                     prior_levels: dict[dt.date, list[float]]) -> tuple[bool, dict]:
    """Three independent confirmations evaluated at the signal (trigger) bar."""
    bar = spy.iloc[sg.bar_idx]
    d = bar["timestamp_et"].date()
    spot = float(bar["close"])

    # (1) named-level confluence within $0.30
    lvl, dist = nearest_named_level(spot, prior_levels.get(d, []))
    level_ok = dist <= LEVEL_CONFLUENCE_DOLLARS

    # (2) ribbon alignment: stack BULL for a call, BEAR for a put
    stack = str(ribbon.iloc[sg.bar_idx]["stack"]) if sg.bar_idx < len(ribbon) else "WARMUP"
    ribbon_ok = (stack == "BULL" and sg.side == "C") or (stack == "BEAR" and sg.side == "P")

    # (3) entry-bar volume >= 1.3x trailing 20-bar baseline (look-ahead-safe: prior bars)
    start = max(0, sg.bar_idx - VOL_BASELINE_BARS)
    base_slice = spy.iloc[start:sg.bar_idx]
    base = float(base_slice["volume"].mean()) if len(base_slice) else 0.0
    vol = float(bar["volume"])
    vol_mult = (vol / base) if base > 0 else 0.0
    vol_ok = base > 0 and vol_mult >= VOL_MULT_MIN

    detail = {
        "spot": round(spot, 2), "nearest_level": lvl,
        "level_dist": round(dist, 3), "level_ok": level_ok,
        "stack": stack, "ribbon_ok": ribbon_ok,
        "vol_mult": round(vol_mult, 2), "vol_ok": vol_ok,
    }
    return (level_ok and ribbon_ok and vol_ok), detail


# ─────────────────────────────────────────────────────────────────────────────
# SIM
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    exit_reason: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct,
                 tp1=TP1, runner=RUNNER, trail=TRAIL) -> tuple[list[TradeRow], dict]:
    use_trailing = trail > 0
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
            qty=QTY, setup="SEL_VWAP_CONFLUENCE", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
            tp1_premium_pct=tp1, runner_target_premium_pct=runner,
            profit_lock_mode=("trailing" if use_trailing else "fixed"),
            profit_lock_trail_pct=(trail if use_trailing else 0.0),
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(date=str(d), side=sg.side, pnl=round(float(fill.dollar_pnl), 2),
                             exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day(rows: list[TradeRow]) -> dict[str, float]:
    bd: dict[str, float] = defaultdict(float)
    for r in rows:
        bd[r.date] += r.pnl
    return bd


def _top5_day_pct(rows: list[TradeRow]) -> Optional[float]:
    bd = _by_day(rows)
    total = sum(bd.values())
    if total <= 0:
        return None
    top5 = sum(sorted(bd.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_top5_days_total(rows: list[TradeRow]) -> Optional[float]:
    """Total P&L with the 5 best DAYS removed (G5)."""
    bd = _by_day(rows)
    if len(bd) <= 5:
        return None
    kept = sorted(bd.values())[:-5]
    return round(float(sum(kept)), 2)


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
        "n": n, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2), "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters, "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
        "drop_top5_days_total": _drop_top5_days_total(rows),
        "by_side": by_side,
        "exit_hist": {k: sum(1 for x in rows if x.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


# ─────────────────────────────────────────────────────────────────────────────
# RANDOM-ENTRY NULL (G6): same per-day COUNT & SIDE, random entry bar in RTH,
# same exit/strike/stop. ~20 seeds. Subset must beat mean(null)+1sd.
# ─────────────────────────────────────────────────────────────────────────────
def random_null(selected_signals, spy, ribbon, vix, day_ctx_by_date, *, seeds=NULL_SEEDS):
    """For each selected signal's (date, side), draw a random RTH entry bar on that day
    (excluding the last 6 bars so an exit can play out), keep side/exit/strike/stop fixed."""
    from autoresearch.infinite_ammo_discovery import Signal as _Sig
    # group selected by (date, side)
    want: list[tuple[dt.date, str, float]] = []
    for sg in selected_signals:
        bar = spy.iloc[sg.bar_idx]
        want.append((bar["timestamp_et"].date(), sg.side, sg.stop_level))

    per_trade = []
    totals = []
    for seed in range(seeds):
        rng = np.random.default_rng(1000 + seed)
        rand_signals = []
        for d, side, stop in want:
            dc = day_ctx_by_date.get(d)
            if dc is None:
                continue
            rth_idx = dc.rth.index.tolist()
            if len(rth_idx) < 8:
                continue
            # exclude last 6 bars so the trade has room to exit
            pick_pool = rth_idx[:-6] if len(rth_idx) > 6 else rth_idx
            bi = int(rng.choice(pick_pool))
            # random null keeps the ORIGINAL chart stop level (structural) so exit
            # mechanics are comparable; side preserved.
            rand_signals.append(_Sig(bar_idx=bi, side=side, stop_level=stop, note="null"))
        rows, _ = simulate_set(rand_signals, spy, ribbon, vix,
                               strike_offset=STRIKE_OFFSET, premium_stop_pct=PREMIUM_STOP_PCT)
        if rows:
            arr = np.array([r.pnl for r in rows], float)
            per_trade.append(float(arr.mean()))
            totals.append(float(arr.sum()))
    if not per_trade:
        return {"seeds": 0}
    pt = np.array(per_trade)
    return {
        "seeds": len(per_trade),
        "null_per_trade_mean": round(float(pt.mean()), 2),
        "null_per_trade_sd": round(float(pt.std(ddof=0)), 2),
        "null_per_trade_threshold_mean_plus_1sd": round(float(pt.mean() + pt.std(ddof=0)), 2),
        "null_total_mean": round(float(np.mean(totals)), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"[sel-{SLUG}] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    day_ctx_by_date = {dc.date: dc for dc in days}
    n_days = len(days)
    print(f"[sel-{SLUG}] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    prior_levels = build_prior_levels(spy)

    # ── 1. Full vwap_continuation signal set (the survivor baseline) ─────────
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[sel-{SLUG}] vwap_continuation signals: {len(signals)} side={side_ct}", flush=True)

    # ── 2. Apply the SELECTION filter ────────────────────────────────────────
    selected = []
    sel_details = []
    n_lvl = n_rib = n_vol = 0
    for sg in signals:
        ok, det = passes_selection(sg, spy, ribbon, prior_levels)
        n_lvl += 1 if det["level_ok"] else 0
        n_rib += 1 if det["ribbon_ok"] else 0
        n_vol += 1 if det["vol_ok"] else 0
        if ok:
            selected.append(sg)
            d = spy.iloc[sg.bar_idx]["timestamp_et"]
            sel_details.append({"date": str(d.date()), "time": d.strftime("%H:%M"),
                                "side": sg.side, **det, "trig": sg.note})
    sel_side_ct = {"C": sum(1 for s in selected if s.side == "C"),
                   "P": sum(1 for s in selected if s.side == "P")}
    print(f"[sel-{SLUG}] confirmation rates over {len(signals)} signals: "
          f"level<=${LEVEL_CONFLUENCE_DOLLARS}={n_lvl} ribbon_aligned={n_rib} "
          f"vol>={VOL_MULT_MIN}x={n_vol}", flush=True)
    print(f"[sel-{SLUG}] SELECTED (all 3): {len(selected)} side={sel_side_ct}", flush=True)

    # ── 3. Real-fills: baseline (full) vs selected, survivor structure ───────
    base_rows, base_cov = simulate_set(signals, spy, ribbon, vix,
                                       strike_offset=STRIKE_OFFSET,
                                       premium_stop_pct=PREMIUM_STOP_PCT)
    base_m = metrics(base_rows)
    sel_rows, sel_cov = simulate_set(selected, spy, ribbon, vix,
                                     strike_offset=STRIKE_OFFSET,
                                     premium_stop_pct=PREMIUM_STOP_PCT)
    sel_m = metrics(sel_rows)

    # ── 4. No-truncation (G7): chart-stop-only on the SELECTED subset ─────────
    sel_chart_rows, _ = simulate_set(selected, spy, ribbon, vix,
                                     strike_offset=STRIKE_OFFSET, premium_stop_pct=-0.99)
    sel_chart_m = metrics(sel_chart_rows)

    # ── 5. Random-entry null (G6) ────────────────────────────────────────────
    null = random_null(selected, spy, ribbon, vix, day_ctx_by_date, seeds=NULL_SEEDS)

    # ── 6. GATES (deterministic) ─────────────────────────────────────────────
    gates = {}
    gates["G1_oos_per_trade_pos"] = bool(sel_m.get("oos_exp", -1) > 0)
    gates["G2_positive_quarters_ge4"] = bool(sel_m.get("positive_quarters_n", 0) >= BAR_POS_Q)
    t5 = sel_m.get("top5_day_pct")
    gates["G3_top5_day_lt200"] = bool(t5 is not None and t5 < BAR_TOP5)
    gates["G4_n_ge20"] = bool(sel_m.get("n", 0) >= BAR_N)
    dt5 = sel_m.get("drop_top5_days_total")
    gates["G5_drop_top5_days_pos"] = bool(dt5 is not None and dt5 > 0)
    sel_pt = sel_m.get("exp_dollar", -1e9)
    thr = null.get("null_per_trade_threshold_mean_plus_1sd")
    gates["G6_beats_random_null"] = bool(thr is not None and sel_pt > thr)
    # G7: sign must NOT invert at chart-stop-only (both same sign as the survivor base)
    sel_chart_pt = sel_chart_m.get("exp_dollar", 0.0)
    gates["G7_no_truncation_sign_stable"] = bool(
        (sel_pt > 0) == (sel_chart_pt > 0) and sel_chart_m.get("n", 0) > 0)
    gates["G8_in_sample_pos"] = bool(sel_m.get("is_exp", -1) > 0)

    clears_all = all(gates.values())

    # comparison vs the proven vwap-alone baseline
    base_pt = base_m.get("exp_dollar", 0.0)
    sel_pt_val = sel_m.get("exp_dollar", 0.0)
    improvement = round(sel_pt_val - base_pt, 2)
    sharpens = bool(sel_pt_val > base_pt and gates["G4_n_ge20"])

    if not gates["G4_n_ge20"]:
        verdict = (f"INCONCLUSIVE -- selection thinned N to {sel_m.get('n', 0)} (<{BAR_N}); "
                   f"the triple-confirmation subset is too rare to validate. "
                   f"per-trade ${sel_pt_val} vs vwap-alone ${base_pt}.")
    elif clears_all and sharpens:
        verdict = (f"SHIPPABLE -- selection SHARPENS the survivor: per-trade ${sel_pt_val} vs "
                   f"vwap-alone ${base_pt} (+${improvement}/tr), n={sel_m['n']}, clears ALL 8 gates.")
    elif clears_all and not sharpens:
        verdict = (f"NEUTRAL -- subset clears all gates but does NOT beat vwap-alone per-trade "
                   f"(${sel_pt_val} vs ${base_pt}); selection adds no edge over the survivor.")
    else:
        failed = [k for k, v in gates.items() if not v]
        verdict = (f"FAILS -- selection does not clear all gates (failed: {', '.join(failed)}). "
                   f"per-trade ${sel_pt_val} vs vwap-alone ${base_pt}.")

    summary = {
        "hypothesis": SLUG,
        "hypothesis_full": ("Take vwap_continuation signals but keep ONLY the high-confluence "
                            "subset (named-level within $0.30 AND ribbon-aligned AND vol>=1.3x). "
                            "Does selection sharpen the proven +$78/tr ITM-2 survivor?"),
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE _edgehunt_vwap_continuation.detect_signals "
                     "(= j_daily_pattern_ratify / vwap_continuation_watcher)"),
        "fills_authority": ("real OPRA bars via lib.simulator_real.simulate_trade_real (C1); "
                            "survivor structure strike_offset=-2 (ITM-2), premium_stop=-0.08, "
                            "v15 exits tp1=0.30/runner=2.5/chandelier_trail=0.20"),
        "selection": {
            "named_level_confluence_dollars": LEVEL_CONFLUENCE_DOLLARS,
            "named_level_set": ("causal proxy (named_level_bounce_scan convention): PDH/PDL/PDC "
                                "(prior RTH day), 5-session hi/lo, $5 round numbers -- all known "
                                "at entry time (no look-ahead, C6)"),
            "ribbon_alignment": "stack BULL for call / BEAR for put at the entry bar",
            "volume_mult_min": VOL_MULT_MIN,
            "volume_baseline_bars": VOL_BASELINE_BARS,
        },
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "n_vwap_signals": len(signals),
        "vwap_signal_side_count": side_ct,
        "confirmation_rates": {
            "level_ok": n_lvl, "ribbon_ok": n_rib, "vol_ok": n_vol, "of_total": len(signals),
        },
        "n_selected": len(selected),
        "selected_side_count": sel_side_ct,
        "baseline_vwap_alone": {"coverage": base_cov, "metrics": base_m},
        "selected_subset": {"coverage": sel_cov, "metrics": sel_m},
        "selected_chart_stop_only_no_truncation": {"metrics": sel_chart_m},
        "random_entry_null": null,
        "gates": gates,
        "clears_all_gates": clears_all,
        "baseline_per_trade": base_pt,
        "selected_per_trade": sel_pt_val,
        "improvement_per_trade": improvement,
        "selection_sharpens": sharpens,
        "verdict": verdict,
        "selected_trades_detail": sel_details,
        "DISCLOSURE": {
            "per_trade": "expectancy (exp_dollar / oos_exp), not WR alone (OP-14)",
            "is_oos": "IS=2025 vs OOS=2026 split (OP-20)",
            "concentration": "top5_day_pct = top-5 winning DAYS as % of total P&L (OP-20 #5)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "no_survivor_pick": ("ALL 8 gates evaluated deterministically; subset reported with "
                                 "clears_all_gates + each gate's pass/fail (anti-pattern 2.10)"),
            "null_caveat": ("random-entry null keeps same per-day count/side/exit/strike/stop; "
                            "subset must beat mean(null)+1sd, not merely the mean (G6)"),
            "level_caveat": ("historical key-levels.json is a single live snapshot, not per-day; "
                             "this uses the codebase's causal PDH/PDL/PDC + round-number proxy"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sel-{SLUG}] wrote {OUT}", flush=True)

    print("\n=== VWAP_PLUS_CONFLUENCE SELECTION VERDICT ===")
    print(f"vwap signals={len(signals)} -> selected={len(selected)} (all 3 confirmations)")
    print(f"BASELINE vwap-alone : n={base_m.get('n')} exp=${base_pt} oos_exp=${base_m.get('oos_exp')} "
          f"posQ={base_m.get('positive_quarters')} top5%={base_m.get('top5_day_pct')}")
    print(f"SELECTED subset     : n={sel_m.get('n')} exp=${sel_pt_val} oos_exp=${sel_m.get('oos_exp')} "
          f"is_exp=${sel_m.get('is_exp')} posQ={sel_m.get('positive_quarters')} top5%={sel_m.get('top5_day_pct')}")
    print(f"  drop-top5-days total=${sel_m.get('drop_top5_days_total')}  "
          f"chart-stop-only exp=${sel_chart_m.get('exp_dollar')} (n={sel_chart_m.get('n')})")
    print(f"  null per-trade mean=${null.get('null_per_trade_mean')} "
          f"thr(+1sd)=${null.get('null_per_trade_threshold_mean_plus_1sd')}")
    print(f"GATES: {gates}")
    print(f"clears_all_gates={clears_all}  sharpens={sharpens}  improvement=${improvement}/tr")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
