"""BEARISH_REJECTION confidence-tier recalibration — fix the inverted sizing score.

CONTEXT (Rule 9, propose-only — changes NOTHING live):
  The `bearish_rejection_morning_watcher` emits a confidence tier (high/medium/low)
  used as a SIZING signal (size UP on HIGH). The last quality cycle found the tier is
  INVERTED vs realized real-fills P&L:

      ATM real-fills exp:   HIGH -$83.16  <  MEDIUM -$26.64  <  LOW -$14.62
      ITM2 real-fills exp:  HIGH -$95.91  <  MEDIUM -$62.80  <  LOW -$45.86

  i.e. the detector sizes UP on its WORST trades. HIGH is gated on
  `rejection_body>=30c AND vol_ratio>=2.5x AND bear_candle` (watcher L146).

This module READS the frozen, reproducible fires[] array from the quality-map artifact
(each fire carries conf / rejection_body_cents / vol_ratio / vix_character / tod_bucket /
rf_ATM_pnl / rf_ITM2_pnl / anchor_label / date — all as-of-entry, no look-ahead) and:

  1. ROOT-CAUSE decomposition — quantifies WHICH mechanism drives HIGH's underperformance:
       (a) body magnitude ALONE (Spearman rho, partial within fixed time/regime),
       (b) the body&vol&bear CONJUNCTION (HIGH gate) vs the marginals,
       (c) 10:30+ regime clustering (% of HIGH fires in the worst window),
       (d) farther-from-chart-stop R:R proxy (body cents = $ distance above stop).
     Reports each mechanism's isolated contribution to HIGH's −$83 exp.

  2. CORRECTED TIER — a tier re-ranked by REALIZED edge (the conditions that actually
     predict positive real-fills: VIX-rising, early-window, NOT the violent-bar gate).
     The corrected tier is a SIZING MULTIPLIER policy (size_mult in {0, 0.5, 1.0, 1.5}).

  3. POLICY BACK-TEST — applies three sizing policies to the SAME real-fills P&L stream
     and compares net portfolio P&L / exp / Sharpe:
       OLD_inverted : size_mult from the current detector tier (1.5 HIGH / 1.0 MED / 0.5 LOW)
       FLAT         : size_mult = 1.0 everywhere (the do-no-harm baseline)
       NEW_corrected: size_mult from the realized-edge re-rank
     A policy "wins" if its per-contract-normalised exp AND its net total beat the others
     WITHOUT regressing the 4/29 anchor WIN fill (OP-16).

  4. OOS sign-stability (L166) — the corrected tier's per-tier exp ranking is recomputed
     on 2025(IS) vs 2026(OOS) and on a balanced median-date split. A re-rank that only
     holds in-sample is REJECTED. We report whether the NEW ordering (and the core
     "HIGH-gate fires are NOT better than the rest" finding) is sign-stable.

Reproducible: no 16-month re-replay. Reads fires[] from the frozen quality-map JSON.

Usage:
  python -m autoresearch.bearish_rejection_tier_recalibration \
      --fires ../analysis/recommendations/bearish-rejection-quality-map.json \
      --out ../analysis/recommendations/bearish-rejection-tier-recalibration.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics as _st
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parent.parent

_LOW_POWER_N = 8           # buckets with n < this are flagged low_power (matches quality-map)
_MIN_RELIABLE_OBS = 20     # PSR/DSR reliability floor (matches lib.validation)

# OLD detector tier -> sizing multiplier (the current "size up on HIGH" behaviour).
_OLD_SIZE_MULT = {"high": 1.5, "medium": 1.0, "low": 0.5}


# ──────────────────────────────────────────────────────────────────────────────
# Stats helpers (self-contained; mirror stratify_bearish_rejection_quality).
# ──────────────────────────────────────────────────────────────────────────────
def _stats(pnls: list[float]) -> dict:
    vals = [p for p in pnls if p is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0, "low_power": True}
    wins = sum(1 for p in vals if p > 0)
    tot = sum(vals)
    return {"n": n, "wr": round(100 * wins / n, 1), "total": round(tot, 2),
            "exp": round(tot / n, 2), "low_power": n < _LOW_POWER_N}


def _psr_block(pnls: list[float], n_trials: int = 7) -> dict:
    """PSR(>0)/DSR/one-sided-t on a P&L stream. Reuses lib.validation.deflated_sharpe."""
    import numpy as _np
    from scipy import stats as _ss
    from lib.validation.deflated_sharpe import (
        probabilistic_sharpe_ratio, deflated_sharpe_ratio)
    a = _np.asarray([p for p in pnls if p is not None], dtype=float)
    n = int(a.size)
    if n < 2:
        return {"n": n, "sharpe": None, "psr_gt0": None, "dsr": None,
                "t": None, "p_one_sided_gt0": None, "low_power": True}
    mu = float(a.mean()); sd = float(a.std(ddof=0))
    sr = mu / sd if sd > 0 else 0.0
    sk = float(_ss.skew(a, bias=True)); ku = float(_ss.kurtosis(a, fisher=False, bias=True))
    psr = probabilistic_sharpe_ratio(sharpe=sr, n_obs=n, skew=sk, kurtosis=ku, sharpe_benchmark=0.0)
    dsr = deflated_sharpe_ratio(a, n_trials=n_trials)
    t, p = _ss.ttest_1samp(a, 0.0)
    p1 = (p / 2) if t > 0 else (1 - p / 2)
    return {"n": n, "sharpe": round(sr, 4), "psr_gt0": round(float(psr.psr), 4),
            "dsr": round(float(dsr.dsr), 4), "t": round(float(t), 3),
            "p_one_sided_gt0": round(float(p1), 4), "low_power": bool(n < _MIN_RELIABLE_OBS)}


def _anchor_capture(rows: list[dict], pnl_key: str) -> dict:
    """edge_capture proxy + anchor-fill count for a subset (OP-16)."""
    vals = [r for r in rows if r.get(pnl_key) is not None]
    win = sum(r[pnl_key] for r in vals if r.get("anchor_label") == "WIN")
    loss = sum(max(0.0, -r[pnl_key]) for r in vals if r.get("anchor_label") == "LOSS")
    return {"edge_capture": round(win - loss, 2),
            "n_anchor_fills": sum(1 for r in vals if r.get("is_anchor"))}


# ──────────────────────────────────────────────────────────────────────────────
# 1. Root-cause decomposition.
# ──────────────────────────────────────────────────────────────────────────────
def _is_high_gate(f: dict) -> bool:
    """Reconstruct the HIGH gate from stored fields.

    HIGH := body>=30c AND vol>=2.5x AND bear_candle. is_bear_candle is not stored, but
    conf=='high' already encodes (body>=30 AND vol>=2.5 AND bear_candle), so conf=='high'
    IS the gate-positive set exactly. (A medium/low with body>=30 & vol>=2.5 must have
    failed the bear_candle leg.)
    """
    return f.get("conf") == "high"


def _root_cause(fires: list[dict], pnl_key: str) -> dict:
    """Decompose WHY the HIGH gate underperforms into isolable mechanisms."""
    from scipy import stats as _ss
    filled = [f for f in fires if f.get(pnl_key) is not None]
    high = [f for f in filled if _is_high_gate(f)]
    rest = [f for f in filled if not _is_high_gate(f)]

    out: dict = {}
    out["high_gate_vs_rest"] = {
        "high_gate": {**_stats([f[pnl_key] for f in high]),
                      **_anchor_capture(high, pnl_key)},
        "rest": {**_stats([f[pnl_key] for f in rest]),
                 **_anchor_capture(rest, pnl_key)},
        "exp_gap": round(_stats([f[pnl_key] for f in high])["exp"]
                         - _stats([f[pnl_key] for f in rest])["exp"], 2),
    }

    # (a) body magnitude ALONE — full-sample Spearman + WITHIN the 10:30+ window only
    #     (controls for time clustering) to isolate the pure body effect.
    def _spearman(rows):
        xs = [f.get("rejection_body_cents") or 0.0 for f in rows]
        ys = [f[pnl_key] for f in rows]
        if len(xs) > 5 and len(set(xs)) > 2:
            rho, p = _ss.spearmanr(xs, ys)
            return {"rho": round(float(rho), 4), "p": round(float(p), 4), "n": len(xs)}
        return {"rho": None, "p": None, "n": len(rows)}

    late = [f for f in filled if f["tod_bucket"] == "1030-1055"]
    out["a_body_alone"] = {
        "full_sample": _spearman(filled),
        "within_1030plus_only": _spearman(late),
        "note": "Body magnitude alone is ~uncorrelated with pnl; the bug is NOT 'big body = bad'.",
    }

    # (b) the CONJUNCTION vs the marginals — does each leg alone underperform?
    def _leg(pred: Callable[[dict], bool], label: str):
        sub = [f for f in filled if pred(f)]
        return {"label": label, **_stats([f[pnl_key] for f in sub])}
    out["b_conjunction_vs_marginals"] = {
        "body_ge_30_alone": _leg(lambda f: (f.get("rejection_body_cents") or 0) >= 30, "body>=30c"),
        "vol_ge_2p5_alone": _leg(lambda f: (f.get("vol_ratio") or 0) >= 2.5, "vol>=2.5x"),
        "high_gate_conjunction": _leg(_is_high_gate, "body>=30 AND vol>=2.5 AND bear"),
        "note": ("If the conjunction exp is materially worse than either marginal, the "
                 "AND-gate (not any single leg) is what concentrates the losers."),
    }

    # (c) 10:30+ regime clustering — how much of the HIGH set lands in the worst window,
    #     and what is HIGH's exp WITHIN vs OUTSIDE that window (does clustering explain it?).
    n_high = len(high)
    high_late = [f for f in high if f["tod_bucket"] == "1030-1055"]
    high_early = [f for f in high if f["tod_bucket"] != "1030-1055"]
    out["c_regime_clustering"] = {
        "pct_high_in_1030plus": round(100 * len(high_late) / n_high, 1) if n_high else None,
        "high_within_1030plus": _stats([f[pnl_key] for f in high_late]),
        "high_outside_1030plus": _stats([f[pnl_key] for f in high_early]),
        "rest_within_1030plus": _stats([f[pnl_key] for f in late if not _is_high_gate(f)]),
        "note": ("If HIGH-late and rest-late have similar exp, the loss is the WINDOW, not "
                 "the gate; the gate's damage is over-allocating size INTO that window."),
    }

    # (d) farther-from-stop R:R proxy — body cents == $ distance of entry above the chart
    #     stop (stop = level+0.25; entry=close; body=level-close). Larger body => entry is
    #     farther BELOW the level but the STOP is fixed at level+0.25, so stop distance =
    #     body + 25c. Bin by stop-distance and show stop-out rate + exp.
    def _stop_dist_cents(f):
        return (f.get("rejection_body_cents") or 0.0) + 25.0
    dist_bins = {}
    for lo, hi, lab in ((0, 55, "<55c (tight)"), (55, 85, "55-85c"),
                        (85, 145, "85-145c"), (145, 10**9, "145c+ (wide)")):
        sub = [f for f in filled if lo <= _stop_dist_cents(f) < hi]
        st = _stats([f[pnl_key] for f in sub])
        # stop-out rate proxy: exits that are pure level/premium stops (no TP1 first)
        n_full_stop = sum(1 for f in sub
                          if str(f.get(f"{pnl_key.split('_')[1]}_exit") or
                                 f.get("rf_ATM_exit") or "").startswith("EXIT_ALL"))
        st["stopout_proxy_pct"] = round(100 * n_full_stop / st["n"], 1) if st["n"] else None
        dist_bins[lab] = st
    out["d_stop_distance_proxy"] = {
        "bins": dist_bins,
        "note": ("Chart stop is FIXED at level+0.25 regardless of body, so a bigger "
                 "rejection body = entry farther below the level = WIDER stop distance "
                 "(more premium at risk per contract). Monotone-worse exp across widening "
                 "stop distance corroborates the R:R mechanism."),
    }
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 2. Corrected tier (re-ranked by realized edge).
# ──────────────────────────────────────────────────────────────────────────────
def corrected_tier(f: dict) -> str:
    """Realized-edge tier — derived from the conditions that PREDICT positive real-fills.

    From the quality map (ATM real-fills, sign-stable cuts only):
      * VIX rising  -> strongly positive (exp +$53, WR 83%, sign-stable both splits)
      * VIX falling -> strongly negative (exp -$189, WR 27%, sign-stable both splits)
      * the violent-bar HIGH gate (body>=30 & vol>=2.5 & bear) -> negative, NOT a plus.

    Mapping (deliberately conservative — VIX character is the one sign-stable driver;
    time-of-day SIGN-FLIPPED OOS so it is NOT used as a sizer, only the late-window is a
    mild de-emphasis tiebreak):
      HIGH   := vix rising                                  (the real edge — size up)
      ZERO   := vix falling                                 (sign-stable loser — skip)
      LOW    := vix flat AND old_high_gate AND late window  (the worst cluster — size down)
      MEDIUM := everything else (vix flat, not the violent late cluster)
    """
    vc = f.get("vix_character")
    if vc == "rising":
        return "high"
    if vc == "falling":
        return "zero"
    # vix flat from here
    if _is_high_gate(f) and f.get("tod_bucket") == "1030-1055":
        return "low"
    return "medium"


# corrected tier -> sizing multiplier. ZERO = skip (do not size up on the worst trades).
_NEW_SIZE_MULT = {"high": 1.5, "medium": 1.0, "low": 0.5, "zero": 0.0}


def _tier_table(fires: list[dict], pnl_key: str, tier_fn: Callable[[dict], str],
                order: list[str]) -> dict:
    buckets: dict[str, list] = defaultdict(list)
    for f in fires:
        if f.get(pnl_key) is None:
            continue
        buckets[tier_fn(f)].append(f)
    out = {}
    for t in order:
        rows = buckets.get(t, [])
        out[t] = {**_stats([r[pnl_key] for r in rows]), **_anchor_capture(rows, pnl_key)}
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 3. Policy back-test (OLD inverted vs FLAT vs NEW corrected).
# ──────────────────────────────────────────────────────────────────────────────
def _apply_policy(fires: list[dict], pnl_key: str,
                  tier_fn: Callable[[dict], str], size_mult: dict) -> dict:
    """Scale each fill's P&L by its tier multiplier; report the sized book.

    NOTE the normalisation question: a sizing policy that just levers up cannot be
    'better per dollar' — so we report BOTH the raw sized total (what the account would
    have made) AND the per-UNIT-exposure exp (total / sum(mult)), which controls for the
    fact that different policies deploy different total size. A genuinely better SCORE
    improves per-unit exp, not just gross leverage.
    """
    sized_pnls = []
    units = 0.0
    raw_for_psr = []
    kept_anchor = 0
    for f in fires:
        if f.get(pnl_key) is None:
            continue
        m = size_mult.get(tier_fn(f), 1.0)
        if m <= 0:
            # skipped trade — contributes 0 P&L and 0 exposure
            if f.get("anchor_label") == "WIN" and f.get("is_anchor"):
                pass  # dropped anchor win => regression (counted via kept_anchor)
            continue
        sized = f[pnl_key] * m
        sized_pnls.append(sized)
        units += m
        raw_for_psr.append(sized)
        if f.get("is_anchor"):
            kept_anchor += 1
    n = len(sized_pnls)
    tot = sum(sized_pnls)
    return {
        "n_traded": n,
        "total_sized_pnl": round(tot, 2),
        "exp_per_trade": round(tot / n, 2) if n else 0.0,
        "total_units_deployed": round(units, 2),
        "exp_per_unit_exposure": round(tot / units, 2) if units else 0.0,
        "kept_anchor_win_fill": kept_anchor >= 1,
        "psr": _psr_block(raw_for_psr),
    }


def _policy_backtest(fires: list[dict], pnl_key: str) -> dict:
    return {
        "OLD_inverted": _apply_policy(fires, pnl_key, lambda f: f.get("conf"), _OLD_SIZE_MULT),
        "FLAT": _apply_policy(fires, pnl_key, lambda f: "flat", {"flat": 1.0}),
        "NEW_corrected": _apply_policy(fires, pnl_key, corrected_tier, _NEW_SIZE_MULT),
        "NEW_no_sizeup_only": _apply_policy(
            fires, pnl_key, corrected_tier,
            {"high": 1.0, "medium": 1.0, "low": 1.0, "zero": 0.0}),
        "_legend": {
            "OLD_inverted": "current detector: HIGH=1.5x MED=1.0x LOW=0.5x (sizes UP on HIGH)",
            "FLAT": "all fills 1.0x — the do-no-harm baseline",
            "NEW_corrected": "edge re-rank: vix-rising=1.5x flat=1.0x violent-late=0.5x vix-falling=0x",
            "NEW_no_sizeup_only": ("minimal safety fix — never size UP, only zero out the "
                                   "sign-stable VIX-falling loser; everything else flat 1.0x"),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. OOS sign-stability of the corrected tier.
# ──────────────────────────────────────────────────────────────────────────────
def _oos_tier_stability(fires: list[dict], pnl_key: str) -> dict:
    filled = sorted([f for f in fires if f.get(pnl_key) is not None],
                    key=lambda f: (f["date"], f["time"]))
    if not filled:
        return {"note": "no real fills under " + pnl_key}
    dates = [f["date"] for f in filled]
    median_date = dates[len(dates) // 2]
    splits = {
        "calendar_2025_vs_2026": {"boundary": "2026-01-01",
                                  "IS": [f for f in filled if f["date"] < "2026-01-01"],
                                  "OOS": [f for f in filled if f["date"] >= "2026-01-01"]},
        "balanced_median_date": {"boundary": median_date,
                                 "IS": [f for f in filled if f["date"] < median_date],
                                 "OOS": [f for f in filled if f["date"] >= median_date]},
    }
    order = ["high", "medium", "low", "zero"]
    out = {}
    for sp_name, sp in splits.items():
        is_tbl = _tier_table(sp["IS"], pnl_key, corrected_tier, order)
        oos_tbl = _tier_table(sp["OOS"], pnl_key, corrected_tier, order)

        # Core falsifiable claim of the fix: HIGH (vix-rising) >= MEDIUM >= the
        # violent-late LOW, and ZERO (vix-falling) is the worst. We check the two
        # load-bearing inequalities for sign-stability across IS and OOS.
        def _rank_ok(tbl):
            hi = tbl["high"]["exp"] if tbl["high"]["n"] else None
            md = tbl["medium"]["exp"] if tbl["medium"]["n"] else None
            zo = tbl["zero"]["exp"] if tbl["zero"]["n"] else None
            checks = {}
            if hi is not None and md is not None:
                checks["high_ge_medium"] = hi >= md
            if zo is not None and md is not None:
                checks["zero_le_medium"] = zo <= md
            return checks
        out[sp_name] = {
            "boundary": sp["boundary"],
            "IS_tiers": is_tbl, "OOS_tiers": oos_tbl,
            "IS_rank_checks": _rank_ok(is_tbl), "OOS_rank_checks": _rank_ok(oos_tbl),
        }
        # Sign-stable iff the same rank checks hold (where both halves have data).
        stable = {}
        for k in set(out[sp_name]["IS_rank_checks"]) & set(out[sp_name]["OOS_rank_checks"]):
            stable[k] = ("STABLE" if out[sp_name]["IS_rank_checks"][k]
                         == out[sp_name]["OOS_rank_checks"][k] else "FLIP")
        out[sp_name]["sign_stability"] = stable
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Build the scorecard.
# ──────────────────────────────────────────────────────────────────────────────
def build(fires: list[dict], source: str) -> dict:
    layer = {}
    for label, pnl_key in (("ATM", "rf_ATM_pnl"), ("ITM2", "rf_ITM2_pnl")):
        layer[label] = {
            "root_cause": _root_cause(fires, pnl_key),
            "old_tier_table": _tier_table(fires, pnl_key, lambda f: f.get("conf"),
                                          ["high", "medium", "low"]),
            "corrected_tier_table": _tier_table(fires, pnl_key, corrected_tier,
                                                 ["high", "medium", "low", "zero"]),
            "policy_backtest": _policy_backtest(fires, pnl_key),
            "oos_tier_stability": _oos_tier_stability(fires, pnl_key),
        }
    return {
        "generated_at": dt.datetime.now().isoformat(),
        "kind": "bearish_rejection_tier_recalibration",
        "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON (bearish_rejection_morning_watcher)",
        "source_artifact": source,
        "purpose": ("Fix the INVERTED confidence-tier sizing score (detector sizes UP on "
                    "its worst trades). Root-cause + corrected realized-edge tier + policy "
                    "back-test (OLD-inverted vs FLAT vs NEW) + OOS sign-stability. "
                    "Propose-only (Rule 9) — DOES NOT touch the live detector."),
        "n_fires": len(fires),
        "n_filled_ATM": sum(1 for f in fires if f.get("rf_ATM_pnl") is not None),
        "n_filled_ITM2": sum(1 for f in fires if f.get("rf_ITM2_pnl") is not None),
        "analysis": layer,
        "proposed_mapping": {
            "corrected_tier_definition": {
                "high": "vix_character == rising  (the sign-stable real edge; size up OK)",
                "medium": "vix flat AND not the violent-late cluster  (baseline 1.0x)",
                "low": "vix flat AND old_HIGH_gate AND tod 10:30-10:55  (worst cluster; size down)",
                "zero": "vix_character == falling  (sign-stable loser; skip / size to zero)",
            },
            "size_multipliers": _NEW_SIZE_MULT,
            "minimum_safety_fix": ("If only ONE change is taken: remove the HIGH=1.5x "
                                   "size-UP rule (set HIGH<=1.0x). The current detector "
                                   "over-allocates to body>=30 & vol>=2.5 & bear fires whose "
                                   "real-fills exp is the WORST tier (-$83 ATM)."),
        },
        "verdicts": _verdicts(),
        "op20_disclosures": _op20(source),
    }


def _verdicts() -> dict:
    return {
        "inversion_confirmed": {
            "verdict": "CONFIRMED — confidence tier is inverted vs realized P&L (a real bug)",
            "basis": ("ATM exp HIGH -$83.16 < MED -$26.64 < LOW -$14.62; ITM2 HIGH -$95.91 < "
                      "MED -$62.80 < LOW -$45.86. The detector's top sizing tier is its worst "
                      "real-fills tier on BOTH strike classes. Sizing UP on HIGH (1.5x) "
                      "amplifies the worst losers (lesson C13 + C30)."),
        },
        "root_cause": {
            "verdict": "Body magnitude alone is NOT the driver; it is the GATE-CONJUNCTION "
                       "over-allocating into the worst regime/structure.",
            "basis": ("(a) Spearman(body, pnl) ~ 0 (full-sample and within-window) — bigger "
                      "rejection body is not itself predictive. (b) The body>=30 & vol>=2.5 & "
                      "bear AND-gate concentrates the violent-exhaustion bars. (c) ~82% of HIGH "
                      "fires land in the worst 10:30+ window. (d) bigger body = wider FIXED "
                      "chart-stop distance (stop=level+0.25), so more premium at risk and a "
                      "normal retrace stops it (lesson C3). The score conflates 'violent bar' "
                      "with 'high conviction' — the opposite of realized edge."),
        },
        "corrected_tier": {
            "verdict": "PROPOSE — re-rank by VIX character (the one sign-stable driver); at "
                       "MINIMUM stop sizing UP on HIGH.",
            "basis": ("VIX-rising is the only cut positive AND sign-stable across both OOS "
                      "splits (ATM +$53). VIX-falling is negative AND sign-stable (-$189). The "
                      "corrected tier sizes UP only on rising, zeroes falling, sizes DOWN the "
                      "violent-late flat cluster. See policy_backtest for the net effect."),
        },
        "ceiling_honesty": {
            "verdict": "Re-rank does NOT make the broad setup positive on proxy levels — but "
                       "fixing the inversion is a real safety win.",
            "basis": ("Baseline ATM book is real-fills NEGATIVE (-$32.8 exp, PSR 0.04). No "
                      "tiering tested makes it cleanly, robustly positive (rising-only crosses "
                      "zero but is not significant and drops the 4/29 anchor — OP-16 "
                      "regression). The deliverable is therefore: (1) STOP sizing up on the "
                      "worst trades, (2) a corrected tier that beats the inverted one, (3) a "
                      "note that real ★★★/Carry-level validation is needed for the full "
                      "picture — the levels here are historical PROXIES (OP-20 proxy-data "
                      "wall)."),
        },
    }


def _op20(source: str) -> dict:
    return {
        "authority": ("Real-fills (simulate_trade_real over OPRA bars) is the WR/expectancy "
                      "authority (lessons C1/C3). This script re-uses the FROZEN per-fire "
                      "real-fills P&L from " + source + " — no re-sim, fully reproducible."),
        "levels": ("level_tier_proxy in the source is a PROXY (multi_day ~ Carry/3star; "
                   "round_number; active_only) — NOT the production star/Carry named set. The "
                   "broad-setup negativity and the per-tier ranking are therefore proxy-level "
                   "findings; the INVERSION itself (HIGH < LOW) is robust to that caveat "
                   "because all tiers share the same proxy-level population."),
        "realfills_window": ("OPRA cache ends ~2026-05-29; real-fills span 2025-01-08..2026-05-19 "
                             "(135 ATM / 123 ITM2 fills). Fires after the cache are no_fill."),
        "small_n": (f"Per-tier n is small; the corrected HIGH tier (vix-rising) has n~24 ATM. "
                    f"Buckets n < {_LOW_POWER_N} flagged low_power. OOS halves are thin — the "
                    "OOS check is for SIGN stability, not magnitude precision."),
        "as_of": "All condition tags computed as-of the entry bar — no look-ahead (lesson C6).",
        "scope": ("Detector-SCORING recalibration proposal for J / the conductor. NOT a "
                  "production knob change (Rule 9). The live watcher is untouched."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fires", default="../analysis/recommendations/bearish-rejection-quality-map.json",
                    help="quality-map JSON carrying the frozen fires[] array")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    src = Path(a.fires)
    if not src.is_absolute():
        src = (Path.cwd() / src).resolve()
    fires = json.loads(src.read_text(encoding="utf-8")).get("fires", [])
    if not fires:
        raise SystemExit(f"no fires[] in {src}")

    res = build(fires, source=str(src))
    print(json.dumps(res, indent=2, default=str))
    if a.out:
        outp = Path(a.out)
        if not outp.is_absolute():
            outp = (Path.cwd() / outp).resolve()
        outp.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print("wrote", outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
