"""trendline_conviction_override_study.py -- FROZEN pre-registration runner.

Runs analysis/recommendations/trendline-structure-conviction-preregistration.json EXACTLY as
registered (no re-picks). Decisive test of whether intact wick/body ascending-support structure
(trendline_engine.py) should carve a CONVICTION OVERRIDE out of block_elite_bull's ratified VIX
[15,17.5) block band (analysis/recommendations/elite-bull-block-vix-01.json).

POPULATION: every BASE-run trade where tier=='ELITE', 'level_reclaim' in triggers_fired,
side=='C', and 15.0 <= entry_vix < 17.5 -- this IS exactly the population block_elite_bull
would block (same predicate the live gate itself uses, backtest/lib/orchestrator.py ~line 1386).
Filtering BASE (unblocked) trades directly by this predicate reproduces the blocked population
without a second diff run: the BASE run never blocks these signals, so their triggers/side/vix/
entry_spot/dollar_pnl are exactly what block_elite_bull would have prevented from ever getting a
real fill (P&L is COUNTERFACTUAL by construction -- see pre-registration's counterfactual_caveat).

PNL OUTCOME: reused directly from the BASE run's TradeFill.dollar_pnl -- BASE already runs with
use_real_fills=True (cached OTM-2/ATM OPRA per V15_SAFE_TIERS' historical convention, the SAME
mechanism elite-bull-block-vix-01.json's own IS avg=-$100/n=73 number was built from). This is
layer (a) fresh-slice-signal replay per the pre-registration's data_plan.pnl_outcome_source --
no new OPRA fetching needed, since the population's outcomes ARE the BASE run's trades.

STRUCTURE STATE: trendline_engine.detect() on a trailing N_DAYS=5 trading-day window of the SAME
cached spy_5m_2025-01-01_2026-06-16.csv, truncated to bars with timestamp_et <= signal_ts_et (C6,
no_look_ahead_guard) -- deterministic, CPU-only, no network calls. Guard test:
backtest/tests/test_trendline_conviction_override_no_lookahead.py (condition_4).

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches strategies.py,
params.json, gates.py, or any trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/trendline_conviction_override_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))

import pandas as pd  # noqa: E402

from backtest.lib.orchestrator import run_backtest  # noqa: E402
import elite_bull_vix_range_ab as eb  # noqa: E402  (BASE dict, IS/OOS windows -- reused, not duplicated)
import trendline_engine as te  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "trendline-structure-conviction-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "trendline-conviction-override-result.json"
OUT_MD = REPO / "analysis" / "recommendations" / "trendline-conviction-override-result.md"
BASELINE_FILE = REPO / "analysis" / "recommendations" / "elite-bull-block-vix-01.json"
GUARD_TEST = REPO / "backtest" / "tests" / "test_trendline_conviction_override_no_lookahead.py"

EXPECTED_PREREG_VERSION = 1

# --- gate_under_test predicate (mirrors backtest/lib/orchestrator.py ~line 1386-1388 exactly) ---
VIX_LOW, VIX_HIGH = 15.0, 17.5
N_DAYS = 5  # trailing trading-day lookback, matches trendline_engine.N_DAYS

# --- candidate thresholds (frozen in the pre-registration -- NO re-picks) ---
CANDIDATES = {
    "TL-A": {"families": ("wick",), "min_respect_count": 10, "max_distance_dollars": 1.00},
    "TL-B": {"families": ("wick",), "min_respect_count": 20, "max_distance_dollars": 1.00},
    "TL-C": {"families": ("wick", "body"), "min_respect_count": 10, "max_distance_dollars": 1.00},
}
CANDIDATE_IDS = ("TL-A", "TL-B", "TL-C")
EVIDENCE_FLOOR = 15


# ---------------------------------------------------------------------------------------------
# QUALITY TIER -- corrected reimplementation of orchestrator.py's inline classifier
# (backtest/lib/orchestrator.py ~lines 1173-1219). NOTE: elite_bull_vix_range_ab.py's own
# get_quality() helper only checks "sequence_rejection" (bear vocabulary) regardless of side --
# for a BULL (side=='C') trade the live gate/orchestrator checks "sequence_reclaim" instead.
# Re-implemented here parameterised by side to match the ACTUAL live predicate exactly (matters
# for this study: an under-classified ELITE bull trade would silently drop out of the population).
# ---------------------------------------------------------------------------------------------
def get_quality_tier(t) -> str:
    tf = set(t.triggers_fired or [])
    side = t.side
    level_trig = "level_reclaim" if side == "C" else "level_rejection"
    seq_trig = "sequence_reclaim" if side == "C" else "sequence_rejection"
    has_level = level_trig in tf
    has_confluence = "confluence" in tf
    has_sequence = seq_trig in tf
    has_ribbon_flip = "ribbon_flip" in tf
    has_trendline = "trendline_rejection" in tf
    n = len(tf)
    if (has_confluence and has_ribbon_flip) or n >= 3:
        return "SUPER"
    if has_confluence or has_sequence:
        return "ELITE"
    if has_level:
        return "LEVEL"
    if has_trendline:
        return "TRENDLINE"
    return "BASE"


def in_population(t) -> bool:
    tf = set(t.triggers_fired or [])
    return (t.side == "C" and get_quality_tier(t) == "ELITE" and "level_reclaim" in tf
            and VIX_LOW <= float(t.entry_vix) < VIX_HIGH)


# ---------------------------------------------------------------------------------------------
# PREFLIGHT
# ---------------------------------------------------------------------------------------------
def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")
    return {
        "preregistration_version": ver,
        "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION,
        "preregistration_status_at_run": preg.get("status"),
    }


# ---------------------------------------------------------------------------------------------
# POPULATION RECONSTRUCTION -- reuses elite_bull_vix_range_ab.py's BASE dict + IS/OOS windows
# verbatim (no new signal detection; "this IS the study's population").
# ---------------------------------------------------------------------------------------------
def reconstruct_population() -> tuple[list[dict], dict]:
    spy = pd.read_csv(eb.SPY_FILE)
    vix = pd.read_csv(eb.VIX_FILE)

    is_b = run_backtest(spy, vix, start_date=eb.IS_START, end_date=eb.IS_END, **eb.BASE)
    oos_b = run_backtest(spy, vix, start_date=eb.OOS_START, end_date=eb.OOS_END, **eb.BASE)

    pop = []
    for is_is, res in ((True, is_b), (False, oos_b)):
        for t in res.trades:
            if in_population(t):
                pop.append({"trade": t, "is_is": is_is})
    counts = {"n_is": sum(1 for p in pop if p["is_is"]),
              "n_oos": sum(1 for p in pop if not p["is_is"]),
              "n_total": len(pop),
              "n_is_base_trades": len(is_b.trades), "n_oos_base_trades": len(oos_b.trades)}
    return pop, counts


# ---------------------------------------------------------------------------------------------
# STRUCTURE STATE -- trailing N_DAYS window from the SAME cached SPY 5m CSV, truncated to
# timestamp_et <= signal_ts_et (C6). Deterministic, CPU-only.
# ---------------------------------------------------------------------------------------------
def load_spy_full_for_structure() -> pd.DataFrame:
    spy = pd.read_csv(eb.SPY_FILE)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])  # wall-v1 frame (matches orchestrator's own parse)
    # TradeFill.entry_time_et comes out of orchestrator.py as a tz-NAIVE python datetime
    # (verified empirically: entry_bar["timestamp_et"] loses its tz on the pandas->Python scalar
    # round-trip inside simulate_trade/simulate_trade_real). Strip tz here too so comparisons
    # below are apples-to-apples wall-clock (both sides already share the same wall-v1 frame --
    # this is a naive-vs-naive comparison of the SAME clock, not a silent offset change).
    if spy["timestamp_et"].dt.tz is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    spy = spy.sort_values("timestamp_et").reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    return spy


def _row_to_bar(row) -> dict:
    return {"t": row.timestamp_et.isoformat(), "o": float(row.open), "h": float(row.high),
            "l": float(row.low), "c": float(row.close)}


def structure_state_at(spy_full: pd.DataFrame, dates_sorted: list, entry_time_et) -> list:
    """Trailing N_DAYS trading-day window ending at entry_time_et's date, truncated to
    bars with timestamp_et <= entry_time_et (no look-ahead). Returns detected lines
    (families=('wick','body') so both TL-A/B [wick] and TL-C [wick_or_body] can be evaluated
    from ONE detect() call per signal)."""
    signal_date = entry_time_et.date()
    try:
        idx = dates_sorted.index(signal_date)
    except ValueError:
        # signal date not in the SPY calendar (shouldn't happen -- defensive)
        prior = [d for d in dates_sorted if d <= signal_date]
        if not prior:
            return []
        idx = dates_sorted.index(prior[-1])
    window_dates = dates_sorted[max(0, idx - N_DAYS + 1): idx + 1]
    lo, hi = window_dates[0], window_dates[-1]
    window = spy_full[(spy_full["date"] >= lo) & (spy_full["date"] <= hi)]
    window = window[window["timestamp_et"] <= entry_time_et]
    if len(window) < 5:
        return []
    bars = [_row_to_bar(r) for r in window.itertuples()]
    return te.detect(bars, families=("wick", "body"))


def _support_line(lines: list, family: str):
    return next((ln for ln in lines if ln.kind == "support" and ln.anchor_family == family), None)


def _qualifies(line, min_respect: float, max_dist: float, spot: float) -> bool:
    if line is None:
        return False
    return (line.respect_count >= min_respect and line.status == "INTACT"
            and abs(line.current_value - spot) <= max_dist)


def evaluate_candidates(lines: list, spot: float) -> dict:
    wick = _support_line(lines, "wick")
    body = _support_line(lines, "body")
    out = {}
    for cid, spec in CANDIDATES.items():
        min_r, max_d = spec["min_respect_count"], spec["max_distance_dollars"]
        if spec["families"] == ("wick",):
            out[cid] = _qualifies(wick, min_r, max_d, spot)
        else:  # wick_or_body
            out[cid] = _qualifies(wick, min_r, max_d, spot) or _qualifies(body, min_r, max_d, spot)
    detail = {
        "wick_support": (None if wick is None else {
            "respect_count": wick.respect_count, "status": wick.status,
            "current_value": wick.current_value, "distance_from_spot": round(abs(wick.current_value - spot), 3)}),
        "body_support": (None if body is None else {
            "respect_count": body.respect_count, "status": body.status,
            "current_value": body.current_value, "distance_from_spot": round(abs(body.current_value - spot), 3)}),
    }
    return {"qualifies": out, "detail": detail}


# ---------------------------------------------------------------------------------------------
# GUARD TEST (condition_4) -- run the standing pytest guard for real, don't just assume PASS.
# ---------------------------------------------------------------------------------------------
def run_no_lookahead_guard() -> dict:
    venv_python = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run(
        [str(venv_python), "-m", "pytest", str(GUARD_TEST.relative_to(REPO / "backtest")), "-v"],
        cwd=str(REPO / "backtest"), capture_output=True, text=True, timeout=120,
    )
    passed = proc.returncode == 0
    return {"passed": passed, "returncode": proc.returncode,
            "tail": "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])}


# ---------------------------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------------------------
def _mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 2) if xs else None


def _stderr(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    return round(statistics.stdev(xs) / (len(xs) ** 0.5), 2)


def baseline_avg_and_n() -> tuple[float, int]:
    base = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    bucket = base["vix_is_breakdown"]["vix_15_17"]
    return float(bucket["avg"]), int(bucket["n"])


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[tcos] preflight: {pf}", flush=True)
    if not pf["preregistration_version_ok"]:
        print("[tcos] PREFLIGHT FAILED -- version mismatch, aborting (no re-picks on a stale spec)",
              file=sys.stderr)
        return 1

    print("[tcos] running guard test (condition_4, no-look-ahead)...", flush=True)
    guard = run_no_lookahead_guard()
    print(f"[tcos] guard: passed={guard['passed']}", flush=True)

    print("[tcos] reconstructing population (BASE run, IS+OOS, elite_bull_vix_range_ab.py's own "
          "BASE dict + windows)...", flush=True)
    pop, counts = reconstruct_population()
    print(f"[tcos] population: {counts}", flush=True)

    print("[tcos] loading SPY 5m cache for structure-state reconstruction...", flush=True)
    spy_full = load_spy_full_for_structure()
    dates_sorted = sorted(spy_full["date"].unique())

    print(f"[tcos] evaluating structure state for {len(pop)} population signals...", flush=True)
    rows = []
    for p in pop:
        t = p["trade"]
        lines = structure_state_at(spy_full, dates_sorted, t.entry_time_et)
        ev = evaluate_candidates(lines, float(t.entry_spot))
        rows.append({
            "is_is": p["is_is"], "date": str(t.entry_time_et.date()),
            "entry_time_et": str(t.entry_time_et), "entry_spot": round(float(t.entry_spot), 2),
            "entry_vix": round(float(t.entry_vix), 2), "triggers_fired": list(t.triggers_fired or []),
            "dollar_pnl": round(float(t.dollar_pnl), 2),
            "qualifies": ev["qualifies"], "structure_detail": ev["detail"],
        })

    baseline_avg, baseline_n = baseline_avg_and_n()

    verdicts = {}
    per_candidate = {}
    for cid in CANDIDATE_IDS:
        rescued = [r for r in rows if r["qualifies"][cid]]
        remainder = [r for r in rows if not r["qualifies"][cid]]
        rescued_pnl = [r["dollar_pnl"] for r in rescued]
        remainder_pnl = [r["dollar_pnl"] for r in remainder]

        rescued_mean = _mean(rescued_pnl)
        rescued_n = len(rescued)
        remainder_mean = _mean(remainder_pnl)
        remainder_se = _stderr(remainder_pnl)

        cond1 = bool(rescued_n > 0 and rescued_mean is not None and rescued_mean > 0.0)

        if remainder_n := len(remainder_pnl):
            if remainder_n >= 2:
                threshold = baseline_avg + (remainder_se or 0.0)
                cond2 = bool(remainder_mean <= threshold)
                cond2_note = (f"remainder mean ${remainder_mean}/tr (n={remainder_n}) vs baseline "
                              f"${baseline_avg}/tr (n={baseline_n}) + 1 SE (${remainder_se}) = "
                              f"threshold ${round(threshold, 2)} -> "
                              f"{'no suggestive improvement' if cond2 else 'suggestive improvement -- FAIL'}")
            else:
                cond2 = bool(remainder_mean is not None and remainder_mean <= baseline_avg)
                cond2_note = (f"remainder n={remainder_n} (<2, no SE computable): mean ${remainder_mean}/tr "
                              f"vs baseline ${baseline_avg}/tr, compared directly (no margin) -> "
                              f"{'PASS' if cond2 else 'FAIL'}")
        else:
            cond2 = True
            cond2_note = "remainder is empty (candidate rescues 100% of population) -- no regression population to check"

        cond3_evidence_floor = rescued_n >= EVIDENCE_FLOOR
        cond4 = bool(guard["passed"])

        hard_fail = not (cond1 and cond2 and cond4)
        if hard_fail:
            overall = "FAIL"
        elif not cond3_evidence_floor:
            overall = "INCONCLUSIVE"
        else:
            overall = "PASS"

        verdicts[cid] = {
            "condition_1_rescued_subset_positive": cond1,
            "condition_2_no_regression_on_remainder": cond2,
            "condition_2_detail": cond2_note,
            "condition_3_evidence_floor": cond3_evidence_floor,
            "condition_4_no_lookahead": cond4,
            "overall": overall,
            "reason": (f"rescued n={rescued_n} mean=${rescued_mean} "
                      f"({'PASS' if cond1 else 'FAIL'} cond1); {cond2_note} "
                      f"({'PASS' if cond2 else 'FAIL'} cond2); "
                      f"evidence floor n>={EVIDENCE_FLOOR}: rescued n={rescued_n} "
                      f"({'met' if cond3_evidence_floor else 'UNDERPOWERED'}); "
                      f"no-lookahead guard: {'PASS' if cond4 else 'FAIL'}"),
        }
        # --- robustness diagnostic (NOT a pass_bar condition -- disclosure only, per OP-33/
        # fable-too-good discipline: a single dominant trade can mechanically flip condition_1
        # without the population being a robust edge. Computed on the ALREADY-frozen rescued
        # set -- no candidate, threshold, or population is touched or re-picked.) ---
        n_is_rescued = sum(1 for r in rescued if r["is_is"])
        n_oos_rescued = sum(1 for r in rescued if not r["is_is"])
        if rescued_pnl:
            max_pnl = max(rescued_pnl)
            # Remove exactly ONE instance of the max (leave-one-out), not all ties.
            loo = list(rescued_pnl)
            loo.remove(max_pnl)
            loo_mean = _mean(loo) if loo else None
            # "Share of net P&L" is only a meaningful number when the rescued total is itself
            # positive (the scenario condition_1's PASS depends on) -- when the net is
            # near-zero/negative the ratio blows up/inverts and is not interpretable, so report
            # None (rendered "n/a") rather than a misleading percentage.
            rescued_total = sum(rescued_pnl)
            outlier_share = round(max_pnl / rescued_total, 3) if rescued_total > 0 else None
            outlier_flips_cond1 = bool(cond1 and (loo_mean is None or loo_mean <= 0.0))
        else:
            max_pnl = loo_mean = outlier_share = None
            outlier_flips_cond1 = False

        per_candidate[cid] = {
            "spec": CANDIDATES[cid],
            "rescued_n": rescued_n, "rescued_mean_pnl": rescued_mean,
            "rescued_wr": (round(sum(1 for x in rescued_pnl if x > 0) / rescued_n, 3) if rescued_n else None),
            "rescued_n_is": n_is_rescued, "rescued_n_oos": n_oos_rescued,
            "remainder_n": len(remainder_pnl), "remainder_mean_pnl": remainder_mean,
            "remainder_stderr": remainder_se,
            "robustness_leave_largest_winner_out": {
                "largest_single_trade_pnl": max_pnl,
                "largest_trade_share_of_rescued_total": outlier_share,
                "mean_excluding_largest_winner": loo_mean,
                "condition_1_depends_on_this_single_trade": outlier_flips_cond1,
            },
            "rescued_rows": [r for r in rows if r["qualifies"][cid]],
        }

    key_findings = [
        f"Population: n={counts['n_total']} (IS n={counts['n_is']}, OOS n={counts['n_oos']}) ELITE bull "
        f"level_reclaim signals in VIX [{VIX_LOW},{VIX_HIGH}) reconstructed from the BASE (unblocked) run "
        f"-- for comparison, elite-bull-block-vix-01.json's own ratification reported n_is_blocked=79, "
        f"n_oos_blocked=4 (79+4=83) for the SAME predicate; this study finds n={counts['n_total']}.",
        f"Baseline (what the override is measured against): elite-bull-block-vix-01.json IS VIX-15-17 "
        f"bucket avg=${baseline_avg}/tr, n={baseline_n}.",
    ]
    for cid in CANDIDATE_IDS:
        pc = per_candidate[cid]
        robust = pc["robustness_leave_largest_winner_out"]
        key_findings.append(
            f"{cid}: rescued n={pc['rescued_n']} (IS={pc['rescued_n_is']}/OOS={pc['rescued_n_oos']}) "
            f"mean=${pc['rescued_mean_pnl']} WR={pc['rescued_wr']}, remainder n={pc['remainder_n']} "
            f"mean=${pc['remainder_mean_pnl']} -> {verdicts[cid]['overall']}."
        )
        if robust["condition_1_depends_on_this_single_trade"]:
            key_findings.append(
                f"  ROBUSTNESS FLAG on {cid}: condition_1 (rescued subset positive) is NOT robust -- "
                f"the single largest rescued trade (${robust['largest_single_trade_pnl']}, "
                f"{round(robust['largest_trade_share_of_rescued_total'] * 100, 1)}% of the rescued "
                f"population's total P&L) is doing all the work. Excluding it alone, mean drops to "
                f"${robust['mean_excluding_largest_winner']}/tr (would FAIL condition_1). This is a "
                f"disclosure-only diagnostic (no candidate/threshold/population was touched or "
                f"re-picked) -- {cid}'s mechanical PASS above should be read as OUTLIER-DEPENDENT, "
                f"not a robust edge, until it accrues more evidence."
            )

    disclosures = [
        "COUNTERFACTUAL BY CONSTRUCTION: nearly the entire population never received a real fill (that "
        "is what block_elite_bull prevents) -- every dollar_pnl in this study is a BS/cached-OPRA "
        "SIMULATED replay via orchestrator.run_backtest(use_real_fills=True), NOT a broker-verified fill. "
        "Per OP-16/C1, this can inform a SHIP/HOLD decision on the override but any resulting override "
        "must accrue its own real-fills track record (evidence_n>=15) before being trusted the way "
        "block_elite_bull itself now is.",
        "PNL engine convention: reused BYTE-IDENTICAL to elite_bull_vix_range_ab.py's own BASE dict "
        "(same strike_offset/account_equity defaults that produced elite-bull-block-vix-01.json's "
        "ratified avg=-$100/n=73 number) -- NOT necessarily the current live V15_SAFE_TIERS ATM "
        "strike convention (see CLAUDE.md C29 + analysis/deep-research/2026-07-11-strike-tier-"
        "reconciliation.md). This is a pre-existing, disclosed gap in the gate's OWN evidence base, "
        "not something this study introduces -- reusing it keeps the override measured on an "
        "apples-to-apples footing against the gate it modifies.",
        "Structure-state reconstruction is CPU-only and deterministic: trendline_engine.detect() on a "
        "trailing N_DAYS=5 trading-day window of the SAME cached spy_5m_2025-01-01_2026-06-16.csv used "
        "for signal reconstruction, truncated to timestamp_et <= signal's entry_time_et (C6). No OPRA "
        "or live network calls in this layer.",
        "Timestamp frame: wall-v1 (default et_frame.py convention, matches orchestrator.py's own "
        "pd.to_datetime(timestamp_et) parse with no utc=True normalization) -- consistent with the "
        "population reconstruction's own frame, not independently re-derived.",
        "Early-dataset signals (near 2025-01-02) may see a SHORTER-than-5-day lookback window (cold "
        "start, clamped to whatever trading days exist before them) -- matches production behavior "
        "for a real cold start, not a bug.",
        "The 2026-07-14 11:06 ET exhibit signal plays NO role in any pass/fail verdict above (excluded "
        "by the pre-registration's own ground rule) -- see hypothesis_provenance.today_exhibit in the "
        "pre-registration file for the narrative context that motivated this study.",
    ]

    # --- overall study verdict -- per the pre-registration's OWN mechanical pass_bar, PLUS the
    # disclosed robustness diagnostic (OP-33/fable-too-good: a mechanical PASS that depends on a
    # single trade is not the same claim as a robust edge; the mission standard is "ship nothing
    # that fails the evidence bar," and outlier-dependence IS a failure of that bar even when the
    # literal >$0 threshold is technically cleared). No candidate/threshold/population was
    # touched to reach this -- it is a reading of the SAME frozen numbers above.
    any_mechanical_pass = any(v["overall"] == "PASS" for v in verdicts.values())
    any_robust_pass = any(
        v["overall"] == "PASS"
        and not per_candidate[cid]["robustness_leave_largest_winner_out"]["condition_1_depends_on_this_single_trade"]
        for cid, v in verdicts.items()
    )
    if any_robust_pass:
        overall_study_verdict = "SHIP_CANDIDATE"
        overall_study_reason = ("At least one candidate PASSES the frozen pass_bar AND survives the "
                                "leave-largest-winner-out robustness check.")
    elif any_mechanical_pass:
        mech_cid = next(cid for cid, v in verdicts.items() if v["overall"] == "PASS")
        mech_pc = per_candidate[mech_cid]
        mech_r = mech_pc["robustness_leave_largest_winner_out"]
        fail_cids = [cid for cid, v in verdicts.items() if v["overall"] == "FAIL"]
        fail_summary = "; ".join(
            f"{cid} breakeven at ${per_candidate[cid]['rescued_mean_pnl']}/tr (n={per_candidate[cid]['rescued_n']})"
            for cid in fail_cids
        )
        overall_study_verdict = "KILL"
        overall_study_reason = (
            f"{mech_cid} mechanically clears the frozen pass_bar's condition_1 threshold "
            f"(${mech_pc['rescued_mean_pnl']}/tr > $0) but the robustness diagnostic shows this is a "
            f"single-trade artifact (one ${mech_r['largest_single_trade_pnl']} signal is "
            f"{round(mech_r['largest_trade_share_of_rescued_total'] * 100, 1)}% of the rescued "
            f"population's net P&L; excluding it alone flips the mean to "
            f"${mech_r['mean_excluding_largest_winner']}/tr). "
            + (f"{fail_summary} cleanly FAIL condition_1. " if fail_summary else "")
            + "No candidate clears the evidence bar the mission requires ('ship nothing that fails "
              "the evidence bar no matter the pressure') -- block_elite_bull's VIX[15,17.5) band "
              "stands as correctly calibrated for ELITE bull level_reclaim signals; the "
              "trendline-as-veto/entry-wire remains correctly shadow-only/NEEDS-REVIEW. Today's "
              "(2026-07-14) VIX-deadzone block was NOT a mistake this study can overturn."
        )
    else:
        overall_study_verdict = "KILL"
        overall_study_reason = "All three candidates FAIL the frozen pass_bar outright -- no rescue evident."

    out = {
        "_doc": "TRENDLINE-STRUCTURE CONVICTION-OVERRIDE study -- pre-registered, frozen before any "
                "candidate replay. ANALYSIS ONLY: no trading-path file touched.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "no_lookahead_guard": guard,
        "population_counts": counts,
        "baseline": {"source": str(BASELINE_FILE.relative_to(REPO)).replace("\\", "/"),
                    "avg_per_trade": baseline_avg, "n": baseline_n},
        "candidates": per_candidate,
        "verdicts": verdicts,
        "overall_study_verdict": overall_study_verdict,
        "overall_study_reason": overall_study_reason,
        "key_findings": key_findings,
        "disclosures": disclosures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[tcos] wrote {OUT_JSON}", flush=True)

    for cid, v in verdicts.items():
        print(f"[tcos] {cid}: {v['overall']} -- {v['reason']}", flush=True)
    print(f"[tcos] OVERALL STUDY VERDICT: {overall_study_verdict} -- {overall_study_reason}", flush=True)

    write_markdown(out)
    print(f"[tcos] wrote {OUT_MD}", flush=True)

    return 0


def write_markdown(out: dict) -> None:
    v = out["verdicts"]
    pc = out["candidates"]
    lines = [
        "# Trendline-Structure Conviction-Override -- Result",
        "",
        f"**Generated:** {out['generated_at']}  ",
        f"**Pre-registration:** `{out['preregistration_file']}` (version "
        f"{out['preflight']['preregistration_version']}, frozen status "
        f"`{out['preflight']['preregistration_status_at_run']}`)",
        "",
        f"## Overall verdict: {out['overall_study_verdict']}",
        "",
        out["overall_study_reason"],
        "",
        "## Population",
        "",
        f"n={out['population_counts']['n_total']} (IS n={out['population_counts']['n_is']}, "
        f"OOS n={out['population_counts']['n_oos']}) ELITE bull level_reclaim signals in VIX "
        f"[{VIX_LOW},{VIX_HIGH}) reconstructed from the BASE (unblocked) run -- the exact "
        "population block_elite_bull would block. Reference: elite-bull-block-vix-01.json "
        f"reported n_is_blocked=79, n_oos_blocked=4 (83 total) for the same predicate.",
        "",
        f"Baseline (what a rescue is measured against): elite-bull-block-vix-01.json IS VIX-15-17 "
        f"bucket avg=${out['baseline']['avg_per_trade']}/tr, n={out['baseline']['n']}.",
        "",
        "## Candidate scorecard",
        "",
        "| Candidate | Rescued n (IS/OOS) | Rescued mean $/tr | Rescued WR | Remainder n | "
        "Remainder mean $/tr | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for cid in CANDIDATE_IDS:
        c = pc[cid]
        lines.append(
            f"| {cid} | {c['rescued_n']} ({c['rescued_n_is']}/{c['rescued_n_oos']}) | "
            f"${c['rescued_mean_pnl']} | {c['rescued_wr']} | {c['remainder_n']} | "
            f"${c['remainder_mean_pnl']} | **{v[cid]['overall']}** |"
        )
    lines += [
        "",
        "## Pass-bar conditions (per candidate)",
        "",
        "| Candidate | 1. rescued>0 | 2. no regression on remainder | 3. evidence floor n>=15 | "
        "4. no-lookahead | Overall |",
        "|---|---|---|---|---|---|",
    ]
    for cid in CANDIDATE_IDS:
        d = v[cid]
        lines.append(
            f"| {cid} | {'PASS' if d['condition_1_rescued_subset_positive'] else 'FAIL'} | "
            f"{'PASS' if d['condition_2_no_regression_on_remainder'] else 'FAIL'} | "
            f"{'met' if d['condition_3_evidence_floor'] else 'UNDERPOWERED'} | "
            f"{'PASS' if d['condition_4_no_lookahead'] else 'FAIL'} | **{d['overall']}** |"
        )
    lines += [
        "",
        "## Robustness diagnostic (disclosure only -- not a pass_bar condition)",
        "",
        "Leave-largest-winner-out sensitivity on the rescued subset's condition_1 mean:",
        "",
        "| Candidate | Largest single trade | Share of rescued net P&L | Mean excl. largest winner | "
        "Condition_1 outlier-dependent? |",
        "|---|---|---|---|---|",
    ]
    for cid in CANDIDATE_IDS:
        r = pc[cid]["robustness_leave_largest_winner_out"]
        share = f"{round(r['largest_trade_share_of_rescued_total'] * 100, 1)}%" if r["largest_trade_share_of_rescued_total"] is not None else "n/a"
        lines.append(
            f"| {cid} | ${r['largest_single_trade_pnl']} | {share} | "
            f"${r['mean_excluding_largest_winner']} | "
            f"{'**YES**' if r['condition_1_depends_on_this_single_trade'] else 'no'} |"
        )
    lines += ["", "## Key findings", ""]
    lines += [f"- {k}" for k in out["key_findings"]]
    lines += ["", "## Disclosures", ""]
    lines += [f"- {d}" for d in out["disclosures"]]
    lines += [
        "",
        "## No-repick clause",
        "",
        "Per the frozen pre-registration: no candidate rule, threshold, distance band, or data-layer "
        "convention was edited in light of results. The robustness diagnostic above is an ADDITIONAL "
        "disclosure computed on the already-frozen rescued sets -- it does not alter, threshold-shop, "
        "or re-run any candidate.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
