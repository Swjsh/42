"""RESCUE-TO-SAFE2 sweep: struct_vwap_reclaim_failed_break across strike x exit cells.

CONTEXT (the 2nd real edge the hunt found):
  struct_vwap_reclaim_failed_break — trend side -> failed counter-trend VWAP break
  -> with-trend VWAP reclaim (<=10:30 ET, chart stop). ONE causal entry/day. It
  clears ALL 8 gates @ ITM-2 (strike_offset=-2: OOS +$72/tr, posQ 5/6) but FAILS @
  OTM-2 (strike_offset=+2: G7 random-null + G8 no-truncation both fail) — C29: OTM
  theta/delta eats the alpha. Safe-2 is a $2K account whose tier is OTM-2/OTM-1/ATM
  (ITM-2 premiums blow the 30% cap), so the ITM-2 winner is NOT Safe-2-shippable.

HYPOTHESIS (this script):
  RESCUE the edge to a Safe-2-tradeable strike by SWEEPING:
    strike_offset in {ITM-1 (-1), ATM (0), OTM-1 (+1), OTM-2 (+2)}   (the rescue axis)
    x  tp1_premium_pct in {0.20, 0.30}                               (faster TP1)
    x  level_stop_buffer_dollars in {0.25, 0.50}                     (tighter chart stop)
  The DETECTOR is unchanged (reuse the exact validated signal set). A faster TP1
  banks the with-trend pop before OTM theta drags it back; a tighter chart-stop
  buffer cuts the failed-reclaim sooner. If ANY cell whose strike is Safe-2-tradeable
  (ITM-1/ATM/OTM-1/OTM-2, premium fits the $2K 30% cap) clears ALL 8 gates -> the
  edge is Safe-2-shippable (huge).

ALL 8 GATES MANDATORY per cell (anti-cherry-pick 2.10; reported for EVERY cell):
  G1 OOS(2026) per-trade > 0
  G2 positive_quarters >= 4/6
  G3 top5_day_pct < 200
  G4 n_trades >= 20
  G5 drop-top5-day per-trade > 0
  G6 IS(2025) FIRST-HALF per-trade > 0
  G7 beats random-entry null (coin-flip null_pass AND same-day mean+std, 20 seeds)
  G8 no-truncation: per-trade SIGN holds -8% stop -> chart-stop-only (-0.99)

SAFE-2 TRADEABILITY (on top of all-8-gates):
  strike_offset >= -1 (ITM-1/ATM/OTM-1/OTM-2 — NOT ITM-2) AND the median
  entry-premium position (entry_premium * qty * 100) fits the $2K 30% cap ($600).
  A winner that clears all 8 gates but only at ITM-2 is reported but NOT marked
  safe2_tradeable.

Detector + real fills + nulls reuse the VALIDATED sub-struct module byte-for-byte
(same data normalizers, same Signal set, same gate code) -> no detector drift.

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/rescue-otm2.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_rescue_otm2.py
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
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
# Reuse the EXACT validated detector + same-day-null from the sub-struct module so the
# signal set is byte-for-byte identical to the promoted ITM-2 edge (no detector drift).
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals,
    sameday_null,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "rescue-otm2.json"

# ── Sweep config ──────────────────────────────────────────────────────────────
# Rescue axis: strikes a $2K Safe-2 account could actually trade (NOT ITM-2).
# We include ITM-2 (-2) as the ANCHOR (the known winner) for no-regression context,
# but only -1/0/+1/+2 are Safe-2-tradeable candidates.
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]            # ITM2(anchor), ITM1, ATM, OTM1, OTM2
TP1_PCTS = [0.20, 0.30]                        # faster TP1 (0.20) vs v15 default (0.30)
STOP_BUFFERS = [0.25, 0.50]                    # tighter chart-stop buffer (0.25) vs v15 (0.50)

SAFE2_TRADEABLE_OFFSETS = {-1, 0, 1, 2}        # ITM-2 excluded (blows the $2K cap)
SURV_PREMIUM_STOP = -0.08                      # -8% premium stop
CHART_STOP_ONLY = -0.99                        # G8 no-truncation reference
N_NULL_SEEDS = 20                              # L172

# Safe-2 sizing: $2K equity, Rule 6 cap = 30% = $600 max risk; qty=3 (2 TP + 1 runner).
SAFE2_EQUITY = 2000.0
SAFE2_RISK_CAP_PCT = 0.30
SAFE2_MAX_RISK_DOLLARS = SAFE2_EQUITY * SAFE2_RISK_CAP_PCT   # $600


@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    entry_premium: float


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set on real OPRA fills, with sweepable TP1 + chart-stop buffer.
# ─────────────────────────────────────────────────────────────────────────────
def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct,
                 tp1_premium_pct, level_stop_buffer_dollars) -> tuple[list[TradeRow], dict]:
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # strike_offset convention (matches simulator_real + sub-struct):
        #   puts:  target = atm - offset  (offset<0 -> ITM above spot)
        #   calls: target = atm + offset  (offset<0 -> ITM below spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="STRUCT_VWAP_RECLAIM_RESCUE", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct,
            tp1_premium_pct=tp1_premium_pct,
            level_stop_buffer_dollars=level_stop_buffer_dollars,
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
            entry_premium=round(float(fill.entry_premium), 4),
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure) — same shape as the sub-struct module.
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


def _max_drawdown(rows: list[TradeRow]) -> Optional[float]:
    """Peak-to-trough $ drawdown on the chronological cumulative-P&L curve."""
    if not rows:
        return None
    srt = sorted(rows, key=lambda r: r.date)
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for r in srt:
        cum += r.pnl
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return round(float(mdd), 2)


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

    prem = np.array([r.entry_premium for r in rows], float)
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "max_drawdown": _max_drawdown(rows),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_n": len(is_first_half), "is_first_half_exp": _exp(is_first_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "median_entry_premium": round(float(np.median(prem)), 4),
        "max_entry_premium": round(float(np.max(prem)), 4),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate one (strike_offset, tp1_pct, stop_buffer) cell: all 8 gates + tradeability.
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_cell(signals, spy, ribbon, vix, days, *, strike_offset, tp1_premium_pct,
                  level_stop_buffer_dollars) -> dict:
    cell_id = (f"off{strike_offset:+d}_tp1{int(tp1_premium_pct*100)}"
               f"_buf{int(level_stop_buffer_dollars*100)}")
    rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                             premium_stop_pct=SURV_PREMIUM_STOP,
                             tp1_premium_pct=tp1_premium_pct,
                             level_stop_buffer_dollars=level_stop_buffer_dollars)
    m = metrics(rows)
    strike_tier_name = (f"ITM{abs(strike_offset)}" if strike_offset < 0
                        else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}"))
    if not m.get("n"):
        return {"cell_id": cell_id, "strike_offset": strike_offset,
                "strike_tier_name": strike_tier_name, "tp1_premium_pct": tp1_premium_pct,
                "level_stop_buffer_dollars": level_stop_buffer_dollars,
                "coverage": cov, "metrics": m, "gates": {}, "clears_all_gates": False,
                "safe2_tradeable": False, "note": "no filled trades"}

    # G8 no-truncation: SAME cell knobs at chart-stop-only.
    cs_rows, _ = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                              premium_stop_pct=CHART_STOP_ONLY,
                              tp1_premium_pct=tp1_premium_pct,
                              level_stop_buffer_dollars=level_stop_buffer_dollars)
    cs_m = metrics(cs_rows)
    trunc_artifact = is_truncation_artifact(
        best_per_trade=m["exp_dollar"],
        chart_stop_only_per_trade=cs_m.get("exp_dollar"),
        best_premium_stop_pct=SURV_PREMIUM_STOP,
    )
    sign_stable_full = bool(cs_m.get("n") and (m["exp_dollar"] > 0) == (cs_m["exp_dollar"] > 0))
    sign_stable_oos = bool(cs_m.get("oos_n") and (m.get("oos_exp", 0) > 0) == (cs_m.get("oos_exp", 0) > 0))
    truncation_safe = bool((not trunc_artifact) and sign_stable_full and sign_stable_oos)

    # G7 nulls — coin-flip (standard) + same-day/same-side (hard control).
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

    # Safe-2 tradeability: strike is in the Safe-2 tier (NOT ITM-2) AND the typical
    # position (median entry premium * qty * 100) fits the $2K 30% cap ($600).
    med_prem = m.get("median_entry_premium", 9e9)
    position_risk = med_prem * QTY * 100.0
    fits_cap = bool(position_risk <= SAFE2_MAX_RISK_DOLLARS)
    strike_in_tier = strike_offset in SAFE2_TRADEABLE_OFFSETS
    safe2_tradeable = bool(clears_all and strike_in_tier and fits_cap)

    caveats = []
    if clears_all and not oos_beats_sameday:
        caveats.append("oos_lift_within_sameday_null_band: OOS per-trade below the same-day "
                       "random-entry null OOS mean -> OOS edge is largely day+side selection, "
                       "not trigger precision (still clears the coin-flip null + every coded gate).")

    return {
        "cell_id": cell_id,
        "strike_offset": strike_offset,
        "strike_tier_name": strike_tier_name,
        "tp1_premium_pct": tp1_premium_pct,
        "level_stop_buffer_dollars": level_stop_buffer_dollars,
        "coverage": cov,
        "metrics": m,
        "gates": gates,
        "clears_all_gates": clears_all,
        "n_gates_passed": sum(1 for g in gates.values() if g["pass"]),
        "safe2_position_risk_dollars": round(position_risk, 2),
        "safe2_fits_cap": fits_cap,
        "safe2_strike_in_tier": strike_in_tier,
        "safe2_tradeable": safe2_tradeable,
        "caveats": caveats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[rescue-otm2] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[rescue] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # EXACT validated signal set (reused detector — no drift).
    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[rescue] struct_vwap_reclaim signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    cells = []
    total_cells = len(STRIKE_OFFSETS) * len(TP1_PCTS) * len(STOP_BUFFERS)
    i = 0
    for off in STRIKE_OFFSETS:
        for tp1 in TP1_PCTS:
            for buf in STOP_BUFFERS:
                i += 1
                blk = evaluate_cell(signals, spy, ribbon, vix, days,
                                    strike_offset=off, tp1_premium_pct=tp1,
                                    level_stop_buffer_dollars=buf)
                cells.append(blk)
                m = blk.get("metrics", {})
                print(f"[{i}/{total_cells}] {blk['cell_id']} ({blk['strike_tier_name']}) "
                      f"n={m.get('n')} exp=${m.get('exp_dollar')} oos=${m.get('oos_exp')} "
                      f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
                      f"medPrem=${m.get('median_entry_premium')} "
                      f"=> gates {blk.get('n_gates_passed')}/8 "
                      f"clears={blk.get('clears_all_gates')} "
                      f"safe2={blk.get('safe2_tradeable')}", flush=True)

    # Rank: Safe-2-tradeable winners first, then by OOS per-trade.
    safe2_winners = [c for c in cells if c.get("safe2_tradeable")]
    all_winners = [c for c in cells if c.get("clears_all_gates")]

    def _oos(c):
        return c.get("metrics", {}).get("oos_exp", -9e9) or -9e9

    safe2_winners.sort(key=_oos, reverse=True)
    all_winners.sort(key=_oos, reverse=True)

    best_safe2 = safe2_winners[0] if safe2_winners else None
    best_any = all_winners[0] if all_winners else None

    if best_safe2:
        bc = best_safe2
        bm = bc["metrics"]
        verdict = (f"RESCUED — Safe-2-tradeable cell {bc['cell_id']} ({bc['strike_tier_name']}) "
                   f"clears ALL 8 gates: OOS +${bm.get('oos_exp')}/tr, posQ {bm.get('positive_quarters')}, "
                   f"medPrem ${bm.get('median_entry_premium')} (position risk "
                   f"${bc.get('safe2_position_risk_dollars')} <= $600 cap). "
                   f"The struct_vwap_reclaim edge IS Safe-2-shippable.")
        if bc.get("caveats"):
            verdict += " CAVEAT: " + " | ".join(bc["caveats"])
    elif best_any:
        ba = best_any
        am = ba["metrics"]
        verdict = (f"NOT RESCUED — the only all-8-gate cells are NOT Safe-2-tradeable "
                   f"(best: {ba['cell_id']} {ba['strike_tier_name']} OOS +${am.get('oos_exp')}/tr — "
                   f"strike-tier or premium-cap fail). No OTM-2/OTM-1/ATM/ITM-1 cell clears all 8 "
                   f"gates; C29 holds (OTM theta/delta eats the alpha, faster TP1 + tighter stop "
                   f"don't recover it within the $2K cap).")
    else:
        verdict = ("NOT RESCUED — NO cell (any strike/exit) clears all 8 gates in this sweep; the "
                   "rescue exits did not recover the edge anywhere.")

    summary = {
        "hypothesis": ("RESCUE struct_vwap_reclaim_failed_break to a Safe-2-tradeable strike: sweep "
                       "strike_offset {ITM-1,ATM,OTM-1,OTM-2} x faster TP1 {0.20,0.30} x tighter "
                       "chart-stop buffer {0.25,0.50} to find a cell that clears ALL 8 gates "
                       "(esp. beats-null + no-truncation) at a premium that fits the $2K 30% cap."),
        "kind": "strike_x_exit_rescue_sweep",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "opra_fill_cutoff": "signals after OPRA cache end drop as cache_miss; OOS fills = Jan..May 2026",
        "detector": ("REUSED VALIDATED struct_vwap_reclaim_failed_break detector (sub-struct module, "
                     "byte-for-byte): trend side (first 3 RTH closes same side of as-of VWAP) -> "
                     "counter-trend VWAP break -> with-trend VWAP reclaim <=10:30 ET; chart stop = "
                     "failed-break excursion extreme. ONE causal entry/day."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "sweep_axes": {
            "strike_offset": STRIKE_OFFSETS,
            "tp1_premium_pct": TP1_PCTS,
            "level_stop_buffer_dollars": STOP_BUFFERS,
            "premium_stop_pct": SURV_PREMIUM_STOP,
            "qty": QTY,
            "n_cells": total_cells,
        },
        "safe2_sizing": {
            "equity": SAFE2_EQUITY,
            "risk_cap_pct": SAFE2_RISK_CAP_PCT,
            "max_risk_dollars": SAFE2_MAX_RISK_DOLLARS,
            "tradeable_strike_offsets": sorted(SAFE2_TRADEABLE_OFFSETS),
            "note": ("ITM-2 (-2) is the anchor (known winner) but NOT Safe-2-tradeable — its premium "
                     "blows the $2K 30% cap; Safe-2 tier = ITM-1/ATM/OTM-1/OTM-2 with position risk "
                     "(median entry premium * qty * 100) <= $600."),
        },
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "eight_gates": {
            "G1": "OOS(2026) per-trade > 0",
            "G2": "positive_quarters >= 4/6",
            "G3": "top5_day_pct < 200",
            "G4": "n_trades >= 20",
            "G5": "drop-top5-day per-trade > 0",
            "G6": "IS(2025) first-half per-trade > 0",
            "G7": "beats random-entry null (coin-flip null_pass AND same-day mean+std, 20 seeds)",
            "G8": "no-truncation: sign holds -8% -> chart-stop-only (-0.99)",
        },
        "cells": cells,
        "n_cells_clearing_all_gates": len(all_winners),
        "n_safe2_tradeable_winners": len(safe2_winners),
        "best_safe2_tradeable_cell": best_safe2["cell_id"] if best_safe2 else None,
        "best_all_gate_cell": best_any["cell_id"] if best_any else None,
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 gates reported for EVERY swept cell; a cell that fails any "
                               "gate is clears_all_gates=false (anti-pattern 2.10). The ITM-2 anchor "
                               "is included for context but flagged safe2_tradeable=false (cap)."),
            "structural_not_additive": ("ONE causal entry/day with a structural chart stop; the rescue "
                                        "sweeps STRIKE + EXIT mechanics only, never stacks confirmations."),
            "strike_tier_caveat": "C29 — gates do not transfer across strike tiers; the sweep IS the per-tier test.",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "fraud_gates": ("G7 random-entry null (coin-flip + same-day/same-side, 20 seeds) + "
                            "G8 no-truncation (sign must hold -8% -> chart-stop-only)."),
            "detector_no_drift": ("detector + same-day null imported byte-for-byte from the validated "
                                  "sub-struct module; only strike/TP1/stop-buffer vary."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[rescue] wrote {OUT}", flush=True)

    print("\n=== RESCUE-OTM2 (struct_vwap_reclaim_failed_break) VERDICT ===")
    print(f"n_signals={len(signals)}  fired {summary['signal_fire_day_pct']}% of {n_days} days")
    print(f"cells swept={total_cells}  clears_all_gates={len(all_winners)}  "
          f"safe2_tradeable={len(safe2_winners)}")
    if best_safe2:
        bm = best_safe2["metrics"]
        print(f"BEST SAFE-2 CELL: {best_safe2['cell_id']} ({best_safe2['strike_tier_name']}) "
              f"n={bm.get('n')} exp=${bm.get('exp_dollar')} oos=${bm.get('oos_exp')} "
              f"posQ={bm.get('positive_quarters')} medPrem=${bm.get('median_entry_premium')}")
    if best_any:
        am = best_any["metrics"]
        print(f"BEST ANY-STRIKE CELL: {best_any['cell_id']} ({best_any['strike_tier_name']}) "
              f"n={am.get('n')} exp=${am.get('exp_dollar')} oos=${am.get('oos_exp')}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
