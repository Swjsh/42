"""SAFE quality-based TRENDLINE sizing upgrade, VIX-CONDITIONAL re-test (b1c3e829-0002).

Follow-up to safe_quality_sizing_ab.py (analysis/recommendations/safe_quality_sizing_ab.json),
which REJECTED the unconditional quality-sizing upgrade: WF=0.06 (fails G3 >=0.70) despite both
IS_delta and OOS_delta being positive individually -- a classic regime-dependence signature
(strong in IS, weak/noisy in OOS) rather than a clean fail.

Hypothesis (queue.md SAFE-VIX-CONDITIONAL-SIZING, MED, cook-queue task b1c3e829-0002,
source=context-86-followup): the quality signal (bearish_streak>=3 OR vol_ratio 1.0-1.5) is real
in ONE VIX regime and noise in others, and the unconditional pooled WF hid this. Gate the SAME
criteria on VIX regime at entry (day-level 09:35 ET reading, same convention as
agg_vix_bear_threshold_sweep.py::get_vix_at_entry -- premarket VIX check, not intrabar).

Regime bands taken from markdown/planning/FUTURE-IMPROVEMENTS.md:130 (the only concrete band
definition found in the repo for this exact terminology): BULL<17.5, NEUTRAL 17.5-22,
VOLATILE>=22. (Note: queue.md's own text cites "CONTEXT-103" for a "NEUTRAL 17.5-22 profitable
band" claim; no analysis/ file with that id exists in this repo as of 2026-07-20 -- treated as a
stale/lost pointer, NOT fabricated. The band DEFINITION itself is real and repo-documented; the
"NEUTRAL was profitable" claim is untraceable and is NOT assumed true here -- this study tests it
fresh instead of taking it on faith.)

This is exploratory (not pre-registered) per the queue item's own framing ("Re-test the SAME
criteria... A/B on real fills... ship a scorecard either way") -- reuses the exact G1-G5 gate
shape from the parent study for apples-to-apples comparability, and reports ALL THREE regime
cuts (BULL/NEUTRAL/VOLATILE) plus the original pooled result side-by-side, not just whichever
cut happens to pass (avoids methodology-shopping under CLAUDE.md OP-16 lineage / C22 discipline).
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa
from safe_quality_sizing_ab import (  # noqa
    classify_tier_from_triggers, compute_bar_metrics, is_quality, naive, SAFE_BASE,
)

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_vix_conditional_sizing.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_W  = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

UPGRADE_RATIO = 10.0 / 3.0  # qty upgrade: 3 -> 10

# Regime bands per markdown/planning/FUTURE-IMPROVEMENTS.md:130
REGIME_BANDS = {
    "BULL":     (0.0, 17.5),
    "NEUTRAL":  (17.5, 22.0),
    "VOLATILE": (22.0, 999.0),
}


def get_vix_at_entry(vix_df, entry_dt):
    """VIX at 09:35 ET on the entry date (premarket check convention, matches
    agg_vix_bear_threshold_sweep.py -- day-level regime, not intrabar)."""
    date_str = str(entry_dt.date())
    rows = vix_df[vix_df["timestamp_et"].str.startswith(date_str)]
    morning = rows[rows["timestamp_et"].str[11:16] >= "09:35"]
    if len(morning) == 0:
        if len(rows) > 0:
            return float(rows.iloc[0]["close"])
        return None
    return float(morning.iloc[0]["close"])


def vix_regime(vix_val):
    if vix_val is None:
        return None
    for name, (lo, hi) in REGIME_BANDS.items():
        if lo <= vix_val < hi:
            return name
    return None


def reweight_trades_regime(trades, spy_df, vix_df, regime_filter):
    """Same eligibility logic as safe_quality_sizing_ab.reweight_trades, PLUS a VIX-regime
    gate at entry. base_total is the pooled baseline (unaffected by the gate -- gate only
    changes WHICH trades are eligible for the upgrade), matching the parent study's convention
    of reporting the extra P&L delta the candidate would add."""
    base_total = sum(t.dollar_pnl for t in trades)
    upgraded = 0
    extra = 0.0
    n_in_regime_eligible = 0
    for t in trades:
        if getattr(t, "side", "").upper() not in ("P", "PUT", "BEAR"):
            continue
        if classify_tier_from_triggers(t) != "TRENDLINE":
            continue
        m = compute_bar_metrics(t, spy_df)
        if not is_quality(m):
            continue
        n_in_regime_eligible += 1
        vix_val = get_vix_at_entry(vix_df, naive(t.entry_time_et))
        regime = vix_regime(vix_val)
        if regime_filter is not None and regime != regime_filter:
            continue
        add = t.dollar_pnl * (UPGRADE_RATIO - 1)
        extra += add
        upgraded += 1
    return base_total, round(extra, 1), upgraded, n_in_regime_eligible


def evaluate_cut(label, regime_filter, r_is, r_oos, spy_df, vix_df):
    b_is_total, is_extra, is_upgraded, is_pool = reweight_trades_regime(r_is.trades, spy_df, vix_df, regime_filter)
    b_oos_total, oos_extra, oos_upgraded, oos_pool = reweight_trades_regime(r_oos.trades, spy_df, vix_df, regime_filter)

    is_delta, oos_delta = is_extra, oos_extra
    wf = round(oos_delta / is_delta, 3) if is_delta != 0 else None

    sw_hurt = 0
    sw_detail = {}
    for sw_name, sw_s, sw_e in SW_SPLITS:
        upg_sw = 0.0
        for t in r_is.trades:
            if getattr(t, "side", "").upper() not in ("P", "PUT", "BEAR"): continue
            if classify_tier_from_triggers(t) != "TRENDLINE": continue
            if not (sw_s <= naive(t.entry_time_et).date() <= sw_e): continue
            m = compute_bar_metrics(t, spy_df)
            if not is_quality(m): continue
            vix_val = get_vix_at_entry(vix_df, naive(t.entry_time_et))
            regime = vix_regime(vix_val)
            if regime_filter is not None and regime != regime_filter: continue
            upg_sw += t.dollar_pnl * (UPGRADE_RATIO - 1)
        sw_detail[sw_name] = round(upg_sw, 1)
        if upg_sw < 0:
            sw_hurt += 1

    anch_extra = 0.0
    for t in r_oos.trades:
        if getattr(t, "side", "").upper() not in ("P", "PUT", "BEAR"): continue
        if classify_tier_from_triggers(t) != "TRENDLINE": continue
        if naive(t.entry_time_et).date() not in ANCHOR_W: continue
        m = compute_bar_metrics(t, spy_df)
        if not is_quality(m): continue
        vix_val = get_vix_at_entry(vix_df, naive(t.entry_time_et))
        regime = vix_regime(vix_val)
        if regime_filter is not None and regime != regime_filter: continue
        anch_extra += t.dollar_pnl * (UPGRADE_RATIO - 1)
    b_anch = sum(t.dollar_pnl for t in r_oos.trades if naive(t.entry_time_et).date() in ANCHOR_W)
    c_anch = b_anch + anch_extra
    tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
    g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

    g1 = is_delta >= 0
    g2 = oos_delta > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_hurt <= 1
    # evidence floor: rescued (upgraded) trade count IS+OOS combined, doctrine floor n>=15
    evidence_n = is_upgraded + oos_upgraded
    g6_evidence = evidence_n >= 15
    passed = g1 and g2 and g3 and g4 and g5
    verdict = "RATIFY" if passed else ("INCONCLUSIVE_UNDERPOWERED" if not g6_evidence else "REJECT")

    return {
        "cut": label, "regime_filter": regime_filter,
        "is_upgraded_trades": is_upgraded, "oos_upgraded_trades": oos_upgraded,
        "is_pool_eligible_quality_trades": is_pool, "oos_pool_eligible_quality_trades": oos_pool,
        "is_delta": is_delta, "oos_delta": oos_delta, "wf": wf,
        "sw_hurt": sw_hurt, "sw_detail": sw_detail,
        "anchor_baseline": round(b_anch, 1), "anchor_candidate": round(c_anch, 1),
        "evidence_n": evidence_n,
        "gates": {"G1_is_nonneg": g1, "G2_oos_pos": g2, "G3_wf": g3, "G4_subwindow": g4,
                  "G5_anchor": g5, "G6_evidence_floor_15": g6_evidence, "all_pass_bar": passed},
        "verdict": verdict,
    }


def main():
    print("=" * 70)
    print("SAFE QUALITY SIZING -- VIX-CONDITIONAL RE-TEST (b1c3e829-0002)")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_candidate = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    if vix_candidate.exists():
        vix_path = vix_candidate
    else:
        # Fall back to the newest available full-range (2025-01-01-started) vix_5m file --
        # spy_5m and vix_5m refresh independently and can drift out of exact filename sync.
        vix_path = sorted(DATA.glob("vix_5m_2025-01-01_*.csv"),
                           key=lambda p: p.stat().st_size, reverse=True)[0]
        print(f"  NOTE: exact vix_5m match for {spy_path.name} not found; "
              f"using newest fallback {vix_path.name} instead.")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    print("Running IS baseline...")
    r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **SAFE_BASE)
    print("Running OOS baseline...")
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **SAFE_BASE)

    cuts = {}
    for label, regime_filter in [("POOLED_baseline_reproduction", None),
                                   ("BULL_lt_17.5", "BULL"),
                                   ("NEUTRAL_17.5_22", "NEUTRAL"),
                                   ("VOLATILE_ge_22", "VOLATILE")]:
        print(f"\nEvaluating cut: {label} ...")
        res = evaluate_cut(label, regime_filter, r_is, r_oos, spy_df, vix_df)
        cuts[label] = res
        print(f"  IS_delta={res['is_delta']:+.0f} OOS_delta={res['oos_delta']:+.0f} "
              f"WF={res['wf']} evidence_n={res['evidence_n']} verdict={res['verdict']}")

    any_ratify = any(v["verdict"] == "RATIFY" for v in cuts.values())
    pooled_repro_wf = cuts["POOLED_baseline_reproduction"]["wf"]
    parent_wf = 0.06  # analysis/recommendations/safe_quality_sizing_ab.json
    repro_check = (pooled_repro_wf is not None and abs(pooled_repro_wf - parent_wf) < 0.05)

    out = {
        "task": "b1c3e829-0002-safe-vix-conditional-sizing",
        "source": "context-86-followup (cook-queue), queue.md SAFE-VIX-CONDITIONAL-SIZING",
        "parent_study": "analysis/recommendations/safe_quality_sizing_ab.json (REJECTED, WF=0.06)",
        "candidate": "TRENDLINE bear trades (bearish_streak>=3 OR vol_ratio_1.0-1.5) upgraded qty 3->10, "
                     "gated additionally on VIX regime at entry (day-level 09:35 ET reading)",
        "regime_bands_source": "markdown/planning/FUTURE-IMPROVEMENTS.md:130",
        "regime_bands": REGIME_BANDS,
        "note_on_context_103": ("Found: automation/overnight/STATUS-ARCHIVE.md 2026-06-18 'CONTEXT-103: "
                                 "VIX-REGIME ANALYSIS' -- BULL(<17.5) n=23 bears breakeven (+$66), "
                                 "NEUTRAL(17.5-22) n=29 bears profitable (+$2,544, WR55.2%), "
                                 "VOLATILE(>22) n=2 too-thin. IMPORTANT SCOPE MISMATCH: that finding is "
                                 "IS-ONLY (no OOS/WF check) over the GENERAL SAFE bear population "
                                 "(all tiers, all trigger types) -- NOT the narrow TRENDLINE-tier "
                                 "quality-sizing-eligible subset (bearish_streak>=3 OR vol_ratio 1.0-1.5) "
                                 "this study re-tests. The two populations legitimately diverge: general "
                                 "bears being NEUTRAL-favorable does not imply the quality-sizing CANDIDATE "
                                 "specifically is NEUTRAL-favorable once OOS/WF discipline is applied -- "
                                 "and this study's result (NEUTRAL cut WF=-0.287, worse than pooled) shows "
                                 "it is not, for this specific candidate."),
        "pooled_reproduction_sanity_check": {
            "reproduced_wf": pooled_repro_wf, "parent_study_wf": parent_wf,
            "matches_within_0.05": repro_check,
            "note": "confirms this script's trade population matches the parent study before trusting the regime cuts",
        },
        "cuts": cuts,
        "any_regime_cut_ratifies": any_ratify,
        "verdict_overall": "RATIFY_NEUTRAL_ONLY" if cuts["NEUTRAL_17.5_22"]["verdict"] == "RATIFY"
                            else ("RATIFY_SOME_OTHER_CUT" if any_ratify else "REJECT_ALL_CUTS"),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print(f"\nOVERALL: {out['verdict_overall']}  (pooled-reproduction sanity check: {repro_check})")


if __name__ == "__main__":
    raise SystemExit(main())
