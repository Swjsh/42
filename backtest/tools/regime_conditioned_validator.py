"""regime_conditioned_validator.py -- regime-CONDITIONED validation procedure.

Implements `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json`
(frozen BEFORE any candidate is scored). Companion to
`analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md` (the calendar A/B-delta WF
this note's method REPLACES the IS/OOS *split axis* for, not the WF formula itself).

THE CORE IDEA: classify every trading day into a regime bucket (VIX band x trend
character, via `regime_classifier.py` -- the SAME primitives the live engine's context
bundle reads). A candidate is validated iff it works consistently WITHIN its target
regime bucket ACROSS THE WHOLE regime-tagged history (both 2025 and 2026 occurrences of
that regime) -- split IS/OOS by CHRONOLOGICAL ORDER OF OCCURRENCE WITHIN THE BUCKET, not
by calendar year. This keeps a real out-of-sample check (chronological, not dropped)
while removing the calendar-year confound the WF-GATE-METHODOLOGY note's absolute-WF form
could not answer.

INPUT CONTRACT: a candidate is a POPULATION of dated (date, pnl) trades -- either a
standalone "take these trades" cohort (control = skip, so delta_i = pnl_i, exactly as
this module treats it) or a block/gate's REMOVED cohort (control = keep; the caller
negates pnl before passing it in, matching `elite_bear_level_reject_gate_ab.py`'s own
`delta = -pnl(removed)` convention -- documented at each call site, never assumed here).

GATE LADDER (mirrors WF-GATE-METHODOLOGY-2026-07-16.md's Option B, computed within-regime):
  is_delta_mean > 0        and WF_delta >= 0.70   -> PASS
  is_delta_mean > 0        and WF_delta <  0.70   -> FAIL
  is_delta_mean <= 0       and oos_delta_mean <= 0 -> FAIL
  is_delta_mean <= 0       and oos_delta_mean >  0 -> INSUFFICIENT_REGIME_SHIFT (still parks
                                                       even WITHIN a regime bucket -- a candidate
                                                       that only works in the newest slice of its
                                                       OWN regime bucket is not proven either)
Plus: sub-window stability (within-regime early/late quarter split), BH-FDR one-sided test
on the regime-OOS cohort, drop-top-3 concentration check, and the TAUTOLOGY DISCLOSURE
(% of the target regime bucket's episodes dated 2026 -- flagged DEGENERATE_REGIME_PROXY at
>=90%, per the frozen prereg).

Run standalone for a smoke check against a synthetic cohort:
    backtest/.venv/Scripts/python.exe backtest/tools/regime_conditioned_validator.py
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for p in (str(ROOT), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backtest.tools.regime_classifier import RegimeCalendar  # noqa: E402

BH_ALPHA = 0.10
DEGENERATE_PROXY_PCT_2026 = 90.0
MIN_BUCKET_N = 6          # need >=6 episodes in the target bucket to even attempt a split
MIN_PER_SIDE_N = 2         # need >=2 on EACH side (regime-IS, regime-OOS) of the split


def _one_sided_p_mean_gt_0(xs: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def _bh_fdr_single(p: float | None, alpha: float = BH_ALPHA) -> dict:
    if p is None:
        return {"p": None, "threshold": alpha, "significant": False, "note": "p undefined (n<2)"}
    return {"p": round(p, 5), "threshold": alpha, "significant": p <= alpha,
            "note": "single-candidate BH-FDR degenerates to a plain one-sided test at alpha"}


def _target_regime_bucket(tagged: list[dict]) -> tuple[str, dict]:
    """Precommitted rule: MODAL regime bucket among the candidate's own episodes.
    The RULE is fixed here before any candidate is scored; WHICH bucket it resolves to
    for a given candidate is discovered by running it, not chosen post-hoc."""
    counts: dict[str, int] = {}
    for t in tagged:
        counts[t["regime"]] = counts.get(t["regime"], 0) + 1
    if not counts:
        return "NONE", {"counts": {}, "concentration_pct": None}
    best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))  # ties -> alphabetically first
    # re-resolve tie deterministically: max by count, then min bucket name
    max_count = max(counts.values())
    tied = sorted([r for r, c in counts.items() if c == max_count])
    bucket = tied[0]
    concentration_pct = round(100.0 * counts[bucket] / len(tagged), 1)
    return bucket, {"counts": counts, "concentration_pct": concentration_pct}


def _quarter(date_str: str) -> str:
    d = dt.date.fromisoformat(date_str)
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def validate_candidate(
    trades: list[dict],
    *,
    candidate_name: str,
    calendar: RegimeCalendar,
    full_window_start: dt.date,
    full_window_end: dt.date,
) -> dict:
    """trades: list of {"date": "YYYY-MM-DD", "pnl": float, ...passthrough}. pnl is ALREADY
    the delta_i (candidate-vs-control) the caller intends -- see module docstring's
    INPUT CONTRACT for the sign convention on block/gate candidates."""
    tagged = []
    for t in trades:
        lab = calendar.label(t["date"])
        tagged.append({**t, "regime": lab["regime"], "vix_band": lab["vix_band"], "trend": lab["trend"]})

    bucket, bucket_meta = _target_regime_bucket(tagged)
    in_bucket = sorted([t for t in tagged if t["regime"] == bucket], key=lambda t: (t["date"],))
    n_bucket = len(in_bucket)

    years_present = sorted({dt.date.fromisoformat(t["date"]).year for t in in_bucket})
    both_years_present = (2025 in years_present) and (2026 in years_present)

    if n_bucket < MIN_BUCKET_N:
        return _insufficient_result(candidate_name, bucket, bucket_meta, tagged, in_bucket,
                                     reason=f"n_bucket={n_bucket} < MIN_BUCKET_N={MIN_BUCKET_N}")

    half = n_bucket // 2
    regime_is = in_bucket[:half]
    regime_oos = in_bucket[half:]
    if len(regime_is) < MIN_PER_SIDE_N or len(regime_oos) < MIN_PER_SIDE_N:
        return _insufficient_result(candidate_name, bucket, bucket_meta, tagged, in_bucket,
                                     reason=f"split too thin (is={len(regime_is)}, oos={len(regime_oos)})")

    is_pnls = [t["pnl"] for t in regime_is]
    oos_pnls = [t["pnl"] for t in regime_oos]
    is_delta_mean = sum(is_pnls) / len(is_pnls)
    oos_delta_mean = sum(oos_pnls) / len(oos_pnls)

    if is_delta_mean == 0:
        wf_delta = None
    else:
        wf_delta = round(oos_delta_mean / is_delta_mean, 3)

    # ---- sub-window stability: split regime_is and regime_oos each in half again ----
    def _half_stable(rows):
        if len(rows) < 4:
            return True, []  # too thin to sub-split meaningfully -- don't penalize
        h = len(rows) // 2
        a, b = rows[:h], rows[h:]
        a_mean = sum(t["pnl"] for t in a) / len(a)
        b_mean = sum(t["pnl"] for t in b) / len(b)
        hurt = [x for x in (("first_half", a_mean), ("second_half", b_mean)) if x[1] < 0]
        return len(hurt) == 0, hurt

    is_stable, is_hurt = _half_stable(regime_is)
    oos_stable, oos_hurt = _half_stable(regime_oos)
    sub_window_stable = is_stable and oos_stable

    # ---- BH-FDR one-sided test: is regime-OOS mean pnl > 0 ----
    p_val = _one_sided_p_mean_gt_0(oos_pnls)
    bh = _bh_fdr_single(p_val)

    # ---- concentration check: drop top-3 by |pnl| in regime-OOS ----
    oos_sorted = sorted(regime_oos, key=lambda t: -abs(t["pnl"]))
    drop_top3 = oos_sorted[3:]
    oos_mean_ex_top3 = (sum(t["pnl"] for t in drop_top3) / len(drop_top3)) if drop_top3 else None

    # ---- tautology disclosure: % of target bucket dated 2026 ----
    n_2026 = sum(1 for t in in_bucket if dt.date.fromisoformat(t["date"]).year == 2026)
    pct_2026 = round(100.0 * n_2026 / n_bucket, 1)
    degenerate_regime_proxy = pct_2026 >= DEGENERATE_PROXY_PCT_2026 or pct_2026 <= (100 - DEGENERATE_PROXY_PCT_2026)

    # ---- gate ladder (mirrors WF-GATE-METHODOLOGY-2026-07-16.md Option B, within-regime) ----
    g1_oos_positive = oos_delta_mean > 0
    g2_wf = wf_delta is not None and wf_delta >= 0.70
    g3_sub_window_stable = sub_window_stable
    g4_bh_survivor = bh["significant"]
    g5_concentration_survives = (oos_mean_ex_top3 is None) or (oos_mean_ex_top3 > 0)

    if is_delta_mean <= 0 and oos_delta_mean <= 0:
        ladder = "FAIL"
    elif is_delta_mean <= 0 and oos_delta_mean > 0:
        ladder = "INSUFFICIENT_REGIME_SHIFT"
    elif g2_wf:
        ladder = "PASS" if (g1_oos_positive and g3_sub_window_stable and g4_bh_survivor and g5_concentration_survives) else "FAIL"
    else:
        ladder = "FAIL"

    all_gates_pass = g1_oos_positive and g2_wf and g3_sub_window_stable and g4_bh_survivor and g5_concentration_survives
    verdict = "PASS" if (ladder == "PASS" and all_gates_pass) else (
        "INSUFFICIENT_REGIME_SHIFT" if ladder == "INSUFFICIENT_REGIME_SHIFT" else "FAIL")

    if degenerate_regime_proxy and verdict == "PASS":
        verdict = "PASS_BUT_DEGENERATE_REGIME_PROXY"

    return {
        "candidate": candidate_name,
        "n_total_tagged": len(tagged),
        "target_regime_bucket": bucket,
        "target_regime_bucket_meta": bucket_meta,
        "both_years_present_in_bucket": both_years_present,
        "years_present_in_bucket": years_present,
        "n_bucket": n_bucket,
        "n_regime_is": len(regime_is),
        "n_regime_oos": len(regime_oos),
        "regime_is_delta_mean": round(is_delta_mean, 2),
        "regime_oos_delta_mean": round(oos_delta_mean, 2),
        "regime_is_delta_total": round(sum(is_pnls), 2),
        "regime_oos_delta_total": round(sum(oos_pnls), 2),
        "wf_delta": wf_delta,
        "sub_window_stability": {"is_stable": is_stable, "is_hurt": is_hurt,
                                  "oos_stable": oos_stable, "oos_hurt": oos_hurt,
                                  "stable": sub_window_stable},
        "bh_fdr": bh,
        "concentration_check": {
            "oos_top3_dropped": [{"date": t["date"], "pnl": t["pnl"]} for t in oos_sorted[:3]],
            "oos_mean_ex_top3": round(oos_mean_ex_top3, 2) if oos_mean_ex_top3 is not None else None,
            "survives_ex_top3": g5_concentration_survives,
        },
        "tautology_disclosure": {
            "pct_bucket_dated_2026": pct_2026,
            "degenerate_regime_proxy_flag": degenerate_regime_proxy,
            "threshold_pct": DEGENERATE_PROXY_PCT_2026,
        },
        "gates": {
            "1_regime_oos_positive": g1_oos_positive,
            "2_wf_delta_ge_070": g2_wf,
            "3_sub_window_stable": g3_sub_window_stable,
            "4_bh_fdr_survivor": g4_bh_survivor,
            "5_concentration_survives_ex_top3": g5_concentration_survives,
        },
        "ladder_verdict": ladder,
        "all_gates_pass": all_gates_pass,
        "verdict": verdict,
        "insufficient_data": False,
    }


def _insufficient_result(candidate_name, bucket, bucket_meta, tagged, in_bucket, *, reason) -> dict:
    return {
        "candidate": candidate_name,
        "n_total_tagged": len(tagged),
        "target_regime_bucket": bucket,
        "target_regime_bucket_meta": bucket_meta,
        "n_bucket": len(in_bucket),
        "verdict": "INSUFFICIENT_N",
        "insufficient_data": True,
        "reason": reason,
    }


if __name__ == "__main__":
    import random

    cal = RegimeCalendar()
    rng = random.Random(1)
    days = cal.all_trading_days(dt.date(2025, 1, 2), dt.date(2026, 7, 8))
    synth = [{"date": d.isoformat(), "pnl": rng.gauss(0, 100)} for d in rng.sample(days, 40)]
    result = validate_candidate(synth, candidate_name="smoke_test_noise",
                                 calendar=cal, full_window_start=dt.date(2025, 1, 2),
                                 full_window_end=dt.date(2026, 7, 8))
    import json
    print(json.dumps(result, indent=2, default=str))
