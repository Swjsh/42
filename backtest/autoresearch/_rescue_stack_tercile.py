"""COMPOUND/RESCUE test: stack_tercile.

HYPOTHESIS
──────────
COMPOUND the two confirmed ITM-2 winners the selection campaign produced:

  EDGE A (the SHAPE):  struct_vwap_reclaim_failed_break  -- one causal with-trend
      entry/day after a FAILED counter-trend VWAP break that RECLAIMS with-trend
      (chart stop = the failed-break excursion extreme). 8/8 gates @ ITM-2 (OOS
      +$72/tr, maxDD -$574); FAILS @ OTM-2 (C29: OTM theta/delta eats the alpha).
      Detector reused BYTE-FOR-BYTE from _sub_struct_vwap_reclaim_failed_break.

  EDGE B (the SUBTRACTION):  skip_top_tercile -- abstain when the entry VIX is in
      the worst (top, causal expanding-window) VIX tercile, base-size everywhere
      else. The lone SUBTRACTIVE winner of the campaign (additive confluence is
      DEAD on 0DTE). Schedule logic reused BYTE-FOR-BYTE from
      _sel_regime_conditional_vwap_sizing.sched_skip_top_tercile_only.

THE COMPOUND: apply EDGE B's causal top-tercile VIX abstention to EDGE A's signal
stream. ONE causal entry/day, pure SUBTRACTION (no size-up leg -> stays inside the
$2K 30% cap, Safe-2-compatible at OTM-2), chart stop unchanged. The question:

  Does stacking raise OOS per-trade above the standalone +$72/tr AND cut the
  standalone -$574 maxDD -- AND clear ALL 8 gates -- at a strike whose premium
  fits the $2K tier (OTM-2), not just ITM-2?

NO-DRIFT (C14):
  * detector            <- _sub_struct_vwap_reclaim_failed_break.detect_signals (verbatim)
  * data normalizers    <- _edgehunt_vwap_continuation._normalize_spy / _align_vix (verbatim)
  * tercile abstention  <- _sel_regime_conditional_vwap_sizing.sched_skip_top_tercile_only
                           (the SAME causal expanding-window top-tercile boundary +
                           WARMUP_TRADES warmup; reused verbatim, applied to EDGE A's stream)
  * real fills          <- lib.simulator_real.simulate_trade_real (C1)
  * coin-flip null      <- autoresearch.null_baseline.random_entry_null / null_gate (L172)
  * no-truncation       <- lib.truncation_guard.is_truncation_artifact (L171)
This script's ONLY new logic is: (1) the causal abstention OVERLAY over EDGE A's
signals (ordered by entry bar), and (2) the maxDD daily-curve comparison vs the
standalone EDGE-A baseline.

ALL 8 MANDATORY GATES (anti-cherry-pick 2.10; reported for BOTH strike tiers):
  G1 OOS(2026) per-trade > 0
  G2 positive_quarters >= 4/6
  G3 top5_day_pct < 200
  G4 n_trades >= 20
  G5 drop-top5-day per-trade > 0          (concentration robustness)
  G6 IS(2025) FIRST-HALF per-trade > 0    (sub-window in-sample stability)
  G7 beats random-entry null (coin-flip null_pass AND same-day mean+std, ~20 seeds)
  G8 no-truncation (L171): per-trade SIGN holds -8% -> chart-stop-only (-0.99)
A Safe-2-TRADEABLE winner must clear ALL 8 at OTM-2 (the $2K 30%-cap tier), not just ITM-2.

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/rescue-stack_tercile.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_rescue_stack_tercile.py
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
)
# EDGE A — the struct_vwap_reclaim_failed_break detector + data normalizers, verbatim.
from autoresearch._sub_struct_vwap_reclaim_failed_break import detect_signals  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
# EDGE B — the causal top-tercile abstention schedule + warmup, verbatim.
from autoresearch._sel_regime_conditional_vwap_sizing import (  # noqa: E402
    sched_skip_top_tercile_only,
    _causal_terciles,
    WARMUP_TRADES,
    BASE_QTY,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "rescue-stack_tercile.json"

# ── Config (FROZEN to EDGE A's survivor structure) ───────────────────────────
PRIMARY_STRIKE_OFFSET = -2     # ITM-2 (EDGE A survivor strike) -- PRIMARY
SAFE2_STRIKE_OFFSET = +2       # OTM-2 (Safe-2's actual $2K tier) -- the SHIP decision (C29)
SURV_PREMIUM_STOP = -0.08      # -8% premium stop (EDGE A)
CHART_STOP_ONLY = -0.99        # for the no-truncation fraud gate (G8)
N_NULL_SEEDS = 20              # L172

# Standalone EDGE-A baseline (from sub-struct_vwap_reclaim_failed_break.json, ITM-2):
#   OOS per-trade +$72.11 ; maxDD reported by the hunt context = -$574.
# We RE-COMPUTE the standalone (no-abstention) maxDD here on the identical daily-curve
# method so the "cut the -$574 maxDD" comparison is internally consistent.
BASELINE_OOS_PER_TRADE = 72.11
BASELINE_MAXDD_CONTEXT = -574.0


# ─────────────────────────────────────────────────────────────────────────────
# REAL-FILLS sim of one signal stream (v15 default exits), carrying entry VIX so the
# causal tercile abstention can be applied AFTER the fills are computed (the skip is a
# pure post-filter; whether we sim then skip, or skip then sim, the kept-trade fills are
# bit-identical because the per-trade fill does not depend on which OTHER trades fired).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    bar_idx: int
    date: str
    side: str
    vix: float
    pnl: float
    pct: float
    exit_reason: str


def simulate_stream(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct
                    ) -> tuple[list[TradeRow], dict]:
    """Sim EVERY EDGE-A signal at one strike/stop, capturing entry VIX. (No abstention
    here -- this is the full standalone stream; the overlay filters it afterwards.)"""
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
            qty=QTY, setup="STACK_TERCILE", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            bar_idx=int(sg.bar_idx), date=str(d), side=sg.side, vix=round(entry_vix, 2),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# THE COMPOUND OVERLAY — EDGE B's causal top-tercile VIX abstention applied to EDGE A's
# stream. Ordered by entry bar (chronological causality). Uses the SAME schedule fn +
# warmup as the campaign winner (qty==0 -> abstain; qty==BASE_QTY -> keep at base size).
# The abstention boundary is the causal expanding-window top tercile of PRIOR kept-stream
# entry VIX -- EXACTLY sched_skip_top_tercile_only's semantics (which itself ignores the
# size-up branch, so a pure skip). prior_vix is built from ALL prior signals' entry VIX
# (the stream the schedule sees), matching how apply_schedule feeds it in the campaign.
# ─────────────────────────────────────────────────────────────────────────────
def apply_tercile_abstention(rows: list[TradeRow]) -> tuple[list[TradeRow], list[dict]]:
    """Return (kept_rows, abstained_audit). Causal: prior_vix grows with EACH visited
    signal (kept OR skipped) -- identical to campaign apply_schedule (prior_vix.append
    happens for every trade, AFTER the size decision). No look-ahead (L14/L34/L57)."""
    ordered = sorted(rows, key=lambda r: r.bar_idx)
    kept: list[TradeRow] = []
    abstained: list[dict] = []
    prior_vix: list[float] = []
    for i, r in enumerate(ordered):
        qty = sched_skip_top_tercile_only(i, prior_vix, r.vix)
        prior_vix.append(r.vix)  # AFTER the decision (causal) -- mirrors apply_schedule
        if qty <= 0:
            ter = _causal_terciles(prior_vix[:-1])  # boundary the decision actually used
            abstained.append({"date": r.date, "side": r.side, "vix": r.vix,
                              "top_tercile_boundary": (round(ter[1], 2) if ter else None),
                              "would_have_pnl": r.pnl})
            continue
        kept.append(r)
    return kept, abstained


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure) + maxDD (campaign daily-curve method, verbatim concept)
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


def _max_dd_dollars(rows: list[TradeRow]) -> float:
    """Max peak-to-trough drawdown of the cumulative DAILY P&L curve (dollars).
    IDENTICAL method to _sel_regime_conditional_vwap_sizing._max_dd_dollars (concept)."""
    bd = _by_day(rows)
    cum = peak = mdd = 0.0
    for d in sorted(bd.keys()):
        cum += bd[d]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return round(mdd, 2)


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

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_n": len(is_first_half), "is_first_half_exp": _exp(is_first_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "max_drawdown_dollars": _max_dd_dollars(rows),
        "worst_single_trade_dollars": round(float(pnl.min()), 2),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# G7 same-day/same-side random null (the HARD control): pick a RANDOM eligible morning
# bar on each KEPT signal's day, same side, same stop geometry. Mirrors the struct
# harness's sameday_null but operates on the KEPT (post-abstention) signal set.
# ─────────────────────────────────────────────────────────────────────────────
def sameday_null(kept_signals, spy, ribbon, vix, days, *, seeds, strike_offset,
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
    for sg in kept_signals:
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
            rand_sigs.append(Signal(bar_idx=int(rng.choice(elig)), side=sd,
                                    stop_level=stop, note="rand"))
        rrows, _ = simulate_stream(rand_sigs, spy, ribbon, vix, strike_offset=strike_offset,
                                   premium_stop_pct=premium_stop_pct)
        if rrows:
            m = metrics(rrows)
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
# Evaluate one strike tier: full standalone stream -> abstention overlay -> all 8 gates
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_tier(signals, spy, ribbon, vix, days, *, strike_offset, tier_label) -> dict:
    # 1) Full standalone EDGE-A stream at this strike (the baseline to beat).
    base_rows, cov = simulate_stream(signals, spy, ribbon, vix,
                                     strike_offset=strike_offset,
                                     premium_stop_pct=SURV_PREMIUM_STOP)
    base_m = metrics(base_rows)

    # 2) Apply the causal top-tercile VIX abstention OVERLAY (the compound).
    kept_rows, abstained = apply_tercile_abstention(base_rows)
    m = metrics(kept_rows)
    if not m.get("n"):
        return {"tier": tier_label, "strike_offset": strike_offset, "coverage": cov,
                "standalone_metrics": base_m, "metrics": m, "gates": {},
                "clears_all_gates": False, "note": "no kept trades after abstention"}

    # 3) G8 no-truncation: SAME abstention overlay on a chart-stop-only base stream.
    cs_base, _ = simulate_stream(signals, spy, ribbon, vix, strike_offset=strike_offset,
                                 premium_stop_pct=CHART_STOP_ONLY)
    cs_kept, _ = apply_tercile_abstention(cs_base)
    cs_m = metrics(cs_kept)
    trunc_artifact = is_truncation_artifact(
        best_per_trade=m["exp_dollar"],
        chart_stop_only_per_trade=cs_m.get("exp_dollar"),
        best_premium_stop_pct=SURV_PREMIUM_STOP,
    )
    sign_stable_full = bool(cs_m.get("n") and (m["exp_dollar"] > 0) == (cs_m["exp_dollar"] > 0))
    sign_stable_oos = bool(cs_m.get("oos_n") and (m.get("oos_exp", 0) > 0) == (cs_m.get("oos_exp", 0) > 0))
    truncation_safe = bool((not trunc_artifact) and sign_stable_full and sign_stable_oos)

    # 4) G7 nulls -- on the KEPT signal set (the abstained-down stream IS the strategy).
    kept_idx = {r.bar_idx for r in kept_rows}
    kept_signals = [s for s in signals if int(s.bar_idx) in kept_idx]
    rth_all = pd.concat([dc.rth for dc in days]).sort_index().reset_index(drop=True)
    n_call = sum(1 for s in kept_signals if s.side == "C")
    n_put = sum(1 for s in kept_signals if s.side == "P")
    coin = random_entry_null(
        rth_all, n_signals=len(kept_signals), n_call=n_call, n_put=n_put,
        strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP, seeds=N_NULL_SEEDS)
    coin_g = null_gate(m["exp_dollar"], m.get("drop_top5_day_per_trade"), coin)
    sameday = sameday_null(kept_signals, spy, ribbon, vix, days, seeds=N_NULL_SEEDS,
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

    # ── The COMPOUND question, answered explicitly vs the standalone EDGE-A baseline ──
    base_oos = base_m.get("oos_exp", 0.0) or 0.0
    base_mdd = base_m.get("max_drawdown_dollars", 0.0) or 0.0
    comp_oos = m.get("oos_exp", 0.0) or 0.0
    comp_mdd = m.get("max_drawdown_dollars", 0.0) or 0.0
    vs_standalone = {
        "standalone_oos_per_trade": base_oos,
        "compound_oos_per_trade": comp_oos,
        "raises_oos_per_trade": bool(comp_oos > base_oos),
        "beats_published_72": bool(comp_oos > BASELINE_OOS_PER_TRADE),
        "standalone_maxdd_dollars": base_mdd,
        "compound_maxdd_dollars": comp_mdd,
        # maxDD is <= 0; "cuts" = shallower = closer to zero = larger (less negative) value.
        "cuts_maxdd": bool(comp_mdd > base_mdd),
        "cuts_published_574_maxdd": bool(comp_mdd > BASELINE_MAXDD_CONTEXT),
        "delta_oos_per_trade": round(comp_oos - base_oos, 2),
        "delta_maxdd_dollars": round(comp_mdd - base_mdd, 2),
        "n_abstained": len(abstained),
        "n_standalone": base_m.get("n"),
        "n_compound": m.get("n"),
    }

    caveats = []
    if clears_all and not oos_beats_sameday:
        caveats.append("oos_lift_within_sameday_null_band: OOS per-trade is below the same-day "
                       "random-entry null OOS mean -> the OOS edge is largely day+side selection, "
                       "not trigger precision (still clears the coin-flip null and every coded gate).")
    if clears_all and not (vs_standalone["raises_oos_per_trade"] and vs_standalone["cuts_maxdd"]):
        caveats.append("compound_does_not_dominate_standalone: the stack clears all 8 gates but does "
                       "NOT both raise OOS/tr AND cut maxDD vs the standalone EDGE-A -> the abstention "
                       "is not additive here (additive confluence is dead on 0DTE; SUBTRACTION must "
                       "EARN its keep, see vs_standalone).")

    return {
        "tier": tier_label,
        "strike_offset": strike_offset,
        "strike_tier_name": (f"ITM{abs(strike_offset)}" if strike_offset < 0
                             else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}")),
        "coverage": cov,
        "standalone_metrics": base_m,
        "metrics": m,
        "abstained_audit": abstained,
        "vs_standalone": vs_standalone,
        "gates": gates,
        "clears_all_gates": clears_all,
        "n_gates_passed": sum(1 for g in gates.values() if g["pass"]),
        "caveats": caveats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[rescue-stack_tercile] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[rescue] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # EDGE A signal stream (struct_vwap_reclaim_failed_break), verbatim detector.
    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[rescue] EDGE-A struct signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    tiers = {}
    for off, lbl in ((PRIMARY_STRIKE_OFFSET, "ITM2_primary"), (SAFE2_STRIKE_OFFSET, "OTM2_safe2")):
        blk = evaluate_tier(signals, spy, ribbon, vix, days,
                            strike_offset=off, tier_label=lbl)
        tiers[lbl] = blk
        m = blk.get("metrics", {})
        vs = blk.get("vs_standalone", {})
        print(f"\n[{lbl} off={off:+d} {blk.get('strike_tier_name')}] COMPOUND "
              f"n={m.get('n')} (standalone {vs.get('n_standalone')}, abstained {vs.get('n_abstained')}) "
              f"exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} (oos_n={m.get('oos_n')}) "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"droptop5=${m.get('drop_top5_day_per_trade')} isH1=${m.get('is_first_half_exp')} "
              f"maxDD=${m.get('max_drawdown_dollars')}", flush=True)
        print(f"    vs standalone: oos {vs.get('standalone_oos_per_trade')}->{vs.get('compound_oos_per_trade')} "
              f"(raises={vs.get('raises_oos_per_trade')}, beats72={vs.get('beats_published_72')}) | "
              f"maxDD {vs.get('standalone_maxdd_dollars')}->{vs.get('compound_maxdd_dollars')} "
              f"(cuts={vs.get('cuts_maxdd')}, cuts574={vs.get('cuts_published_574_maxdd')})", flush=True)
        for gname, g in blk.get("gates", {}).items():
            print(f"    {gname}: {'PASS' if g['pass'] else 'FAIL'} (value={g.get('value', '-')})",
                  flush=True)
        print(f"    => clears_all_gates={blk.get('clears_all_gates')} "
              f"({blk.get('n_gates_passed')}/8)", flush=True)

    primary = tiers["ITM2_primary"]
    pm = primary.get("metrics", {})
    pg = primary.get("gates", {})
    pvs = primary.get("vs_standalone", {})
    safe2 = tiers["OTM2_safe2"]

    beats_null = bool(pg.get("G7_beats_random_null", {}).get("pass"))
    truncation_safe = bool(pg.get("G8_no_truncation", {}).get("pass"))
    is_half_positive = bool(pg.get("G6_is_first_half_positive", {}).get("pass"))
    clears_all = bool(primary.get("clears_all_gates"))
    safe2_tradeable = bool(safe2.get("clears_all_gates"))
    primary_caveats = primary.get("caveats", [])

    # Verdict: the compound is a WIN only if it BOTH raises OOS/tr AND cuts maxDD AND
    # clears all 8 gates @ ITM-2; Safe-2-tradeable additionally requires all 8 @ OTM-2.
    dominates = bool(pvs.get("raises_oos_per_trade") and pvs.get("cuts_maxdd"))
    if clears_all and dominates and safe2_tradeable:
        verdict = ("PROMOTABLE + SAFE-2-TRADEABLE — compound clears all 8 gates @ ITM-2 AND @ OTM-2, "
                   "raises OOS/tr AND cuts maxDD vs standalone")
    elif clears_all and dominates:
        verdict = ("PROMOTABLE @ ITM-2 ONLY — compound clears all 8 gates @ ITM-2, raises OOS/tr AND "
                   "cuts maxDD, but FAILS @ OTM-2 (C29 — not Safe-2-tradeable)")
    elif clears_all:
        verdict = ("CLEARS-8-BUT-NO-DOMINANCE @ ITM-2 — compound clears all 8 gates but does NOT both "
                   "raise OOS/tr AND cut maxDD vs standalone (subtraction did not earn its keep)")
    else:
        verdict = "REJECTED — compound fails one or more of the 8 mandatory gates @ ITM-2 (see gates block)"
    if clears_all and primary_caveats:
        verdict += " [CAVEAT: " + "; ".join(primary_caveats) + "]"

    summary = {
        "hypothesis": ("stack_tercile: COMPOUND struct_vwap_reclaim_failed_break (EDGE A, the SHAPE) "
                       "with skip_top_tercile VIX abstention (EDGE B, the SUBTRACTION) — apply EDGE B's "
                       "causal expanding-window top-VIX-tercile skip to EDGE A's one-entry/day struct "
                       "stream. Does stacking raise OOS/tr above +$72 AND cut the -$574 maxDD, clearing "
                       "all 8 gates at a $2K-tradeable strike (OTM-2), not just ITM-2?"),
        "kind": "compound_two_confirmed_edges",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "opra_fill_cutoff": "2026-05-29 (signals after drop as cache_miss; OOS fills = Jan..May 2026)",
        "edge_A": ("struct_vwap_reclaim_failed_break — detector imported BYTE-FOR-BYTE from "
                   "_sub_struct_vwap_reclaim_failed_break.detect_signals (one causal with-trend entry/day "
                   "after a failed counter-trend VWAP break that reclaims; chart stop = failed-break "
                   "excursion extreme). Standalone: 8/8 @ ITM-2 (OOS +$72/tr), FAILS @ OTM-2."),
        "edge_B": ("skip_top_tercile — abstention schedule imported BYTE-FOR-BYTE from "
                   "_sel_regime_conditional_vwap_sizing.sched_skip_top_tercile_only (causal "
                   f"expanding-window top-VIX-tercile skip; warmup={WARMUP_TRADES} entries). Pure "
                   "SUBTRACTION (no size-up leg -> base qty everywhere it does not skip -> stays inside "
                   "the $2K 30% cap)."),
        "compound_method": ("apply EDGE B's causal top-tercile abstention OVERLAY to EDGE A's signal "
                            "stream, ordered by entry bar; prior_vix grows with EACH visited signal "
                            "(kept or skipped) AFTER the decision (mirrors campaign apply_schedule — no "
                            "look-ahead L14/L34/L57). Kept-trade fills are bit-identical to the standalone "
                            "stream (the skip is a pure post-filter; a per-trade fill does not depend on "
                            "which OTHER trades fired)."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY, "base_qty": BASE_QTY,
                   "warmup_trades": WARMUP_TRADES,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "primary_strike_offset": PRIMARY_STRIKE_OFFSET,
                   "secondary_strike_offset": SAFE2_STRIKE_OFFSET},
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "baseline_for_compound_question": {
            "standalone_published_oos_per_trade": BASELINE_OOS_PER_TRADE,
            "standalone_published_maxdd_context": BASELINE_MAXDD_CONTEXT,
            "note": ("standalone maxDD is ALSO recomputed per tier in vs_standalone.standalone_maxdd_"
                     "dollars on the identical daily-curve method so the comparison is internally "
                     "consistent (the published -$574 is the hunt-context figure)."),
        },
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
        "PRIMARY_TIER": "ITM2_primary",
        "SAFE2_TIER": "OTM2_safe2",
        "compound_dominates_standalone_itm2": dominates,
        "safe2_tradeable": safe2_tradeable,
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 gates reported for BOTH strike tiers (ITM-2 primary + OTM-2 "
                               "Safe-2); a tier that fails any gate is marked clears_all_gates=false "
                               "(anti-pattern 2.10)."),
            "compound_not_additive_confluence": ("EDGE B is a pure SUBTRACTION (skip) over EDGE A's ONE "
                                                 "causal entry/day, NOT a stacked confirmation; the "
                                                 "campaign proved additive confluence is dead on 0DTE."),
            "must_earn_keep": ("the compound is only a WIN if it BOTH raises OOS/tr AND cuts maxDD vs "
                               "the standalone EDGE-A (vs_standalone); clearing 8 gates without "
                               "dominance is flagged, not sold as a win."),
            "strike_tier_caveat": ("C29 — gates do NOT transfer across strike tiers; OTM-2 is the binding "
                                   "Safe-2 ($2K 30%-cap) decision, reported independently."),
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "fraud_gates": ("G7 random-entry null (coin-flip + same-day/same-side, 20 seeds) + G8 "
                            "no-truncation (sign must hold -8% -> chart-stop-only)."),
            "causal_abstention": (f"top-VIX-tercile boundary is a causal expanding-window over PRIOR "
                                  f"entries only; warmup={WARMUP_TRADES} (no abstention until then); "
                                  "no look-ahead (L14/L34/L57)."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[rescue] wrote {OUT}", flush=True)

    print("\n=== STACK_TERCILE COMPOUND VERDICT (PRIMARY ITM-2) ===")
    print(f"n_signals={len(signals)}  fired {summary['signal_fire_day_pct']}% of {n_days} days")
    print(f"ITM-2 compound: n={pm.get('n')} exp=${pm.get('exp_dollar')} oos_exp=${pm.get('oos_exp')} "
          f"posQ={pm.get('positive_quarters')} top5%={pm.get('top5_day_pct')} "
          f"maxDD=${pm.get('max_drawdown_dollars')}")
    print(f"vs standalone: raises_oos={pvs.get('raises_oos_per_trade')} (delta "
          f"${pvs.get('delta_oos_per_trade')}) cuts_maxDD={pvs.get('cuts_maxdd')} (delta "
          f"${pvs.get('delta_maxdd_dollars')})")
    print(f"clears_all_gates={clears_all}  beats_null={beats_null}  truncation_safe={truncation_safe}  "
          f"is_half_positive={is_half_positive}  safe2_tradeable={safe2_tradeable}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
