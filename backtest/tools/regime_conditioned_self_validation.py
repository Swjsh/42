"""regime_conditioned_self_validation.py -- THE GATE (methodology is on trial).

Runs `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json`'s
self-validation: known-BAD cohorts must be KILLED, known-GOOD cohorts must SURVIVE, before
regime-conditioned validation (backtest/tools/regime_conditioned_validator.py) earns the
right to re-adjudicate any of the 5 parked candidates named in
analysis/recommendations/REGIME-REFERENCE-CLASS-ADJUDICATION-2026-07-17.md.

Preflight fails loud on any prereg drift (content_sha256_16 mismatch) -- no post-hoc
re-picking of the regime definition or gate thresholds after seeing results.

Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_conditioned_self_validation.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]     # backtest/
ROOT = REPO.parent                              # repo root
for p in (str(ROOT), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402

from backtest.tools.regime_classifier import RegimeCalendar, tautology_stats  # noqa: E402
from backtest.tools.regime_conditioned_validator import validate_candidate  # noqa: E402
from autoresearch.j_edge_tracker import J_WINNERS, J_LOSERS  # noqa: E402
from autoresearch import _edgehunt_vwap_continuation as ehvc  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

PREREG = ROOT / "analysis" / "recommendations" / "prereg-regime-conditioned-validation-2026-07-17.json"
EXPECTED_SHA16 = "1b927e10e84e7fa3"
EXPECTED_VERSION = 1

OUT_JSON = ROOT / "analysis" / "recommendations" / "regime-conditioned-validation-2026-07-17.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "regime-conditioned-validation-2026-07-17.md"

FULL_WINDOW_START = dt.date(2025, 1, 2)
FULL_WINDOW_END = dt.date(2026, 7, 8)

NLWB_FILE = ROOT / "analysis" / "recommendations" / "nlwb_full_real_fills.json"
CONFLUENCE_FILE = ROOT / "analysis" / "recommendations" / "confluence-real-fills-fresh95.json"
DOUBLE_TOP_FILE = ROOT / "analysis" / "recommendations" / "double-top-real-fills.json"

SPY_FILE = REPO / "data" / "spy_5m_2025-01-01_2026-07-08.csv"
VIX_FILE = REPO / "data" / "vix_5m_2025-01-01_2026-07-08.csv"

PLACEBO_SEED = 20260717
PLACEBO_N = 40
PLACEBO_SD = 150.0


def log(msg: str) -> None:
    print(f"[regime-self-val] {msg}", flush=True)


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    payload = json.dumps(preg_no_hash, sort_keys=True, default=str)
    recomputed = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    ok = (recomputed == EXPECTED_SHA16 == stored and preg.get("version") == EXPECTED_VERSION)
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
            "expected_sha16": EXPECTED_SHA16, "version": preg.get("version"),
            "status": preg.get("status")}


# ---------------------------------------------------------------------------------------------
# COHORT LOADERS
# ---------------------------------------------------------------------------------------------
def load_dated_pnl_cohort(path: Path, results_key: str = "results") -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in d[results_key]:
        date = r.get("date")
        pnl = r.get("pnl") if "pnl" in r else r.get("dollar_pnl")
        if date is None or pnl is None:
            continue
        out.append({"date": date, "pnl": float(pnl)})
    return out


def build_placebo_cohort(calendar: RegimeCalendar) -> list[dict]:
    days = calendar.all_trading_days(FULL_WINDOW_START, FULL_WINDOW_END)
    rng = random.Random(PLACEBO_SEED)
    sample = rng.sample(days, PLACEBO_N)
    out = []
    for d in sample:
        pnl = round(rng.gauss(0.0, PLACEBO_SD), 2)
        out.append({"date": d.isoformat(), "pnl": pnl})
    return out


def build_vwap_continuation_itm2_cohort() -> list[dict]:
    """Reuses _edgehunt_vwap_continuation.py's OWN validated detector + sim path,
    ONE cell (strike_offset=-2 [ITM-2], premium_stop_pct=-0.08) -- the STRATEGY-SPACE-
    REGISTRY.jsonl 'vwap_continuation_itm2_tight' row (verdict=PROMOTE, status=LIVE)."""
    log("loading SPY+VIX for vwap_continuation cohort...")
    spy_raw = pd.read_csv(SPY_FILE)
    vix_raw = pd.read_csv(VIX_FILE)
    spy = ehvc._normalize_spy(spy_raw)
    vix = ehvc._align_vix(spy, vix_raw)
    days = ehvc.build_day_contexts(spy)
    log(f"trading_days={len(days)} window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}")
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals = ehvc.detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    log(f"signals detected: {len(signals)}")
    rows, cov = ehvc.simulate_cell(signals, spy, ribbon, vix, strike_offset=-2, premium_stop_pct=-0.08)
    log(f"vwap_continuation ITM-2/-8% cell: n={len(rows)} coverage={cov}")
    return [{"date": r.date, "pnl": r.pnl, "side": r.side, "exit": r.exit_reason} for r in rows], cov


# ---------------------------------------------------------------------------------------------
# OP-16 ANCHOR QUALITATIVE CHECK (n=7, too thin for the full ladder -- coverage + non-regression)
# ---------------------------------------------------------------------------------------------
def op16_anchor_qualitative_check(calendar: RegimeCalendar) -> dict:
    rows = []
    for t in J_WINNERS:
        lab = calendar.label(t["date"])
        rows.append({"date": t["date"], "kind": "WINNER", "j_pnl": t["j_pnl"], "regime": lab["regime"],
                     "vix_band": lab["vix_band"], "trend": lab["trend"]})
    for t in J_LOSERS:
        lab = calendar.label(t["date"])
        rows.append({"date": t["date"], "kind": "LOSER", "j_pnl": t["j_pnl"], "regime": lab["regime"],
                     "vix_band": lab["vix_band"], "trend": lab["trend"]})
    all_available = all(r["regime"] != "UNKNOWN_unknown" and "unknown" not in r["regime"].lower()
                         for r in rows)
    n_coherent = sum(1 for r in rows if "unknown" not in r["regime"].lower())
    regimes_touched = sorted({r["regime"] for r in rows})
    return {
        "rows": rows,
        "n_total": len(rows),
        "n_coherent_label": n_coherent,
        "all_dates_labelable": all_available,
        "regimes_touched": regimes_touched,
        "note": "n=7, all 2026 -- too thin for the full regime-conditioned WF ladder "
                "(needs >=6 in-bucket AND >=2/side AND both years present). Reported as a "
                "coverage check only: does the classifier produce a coherent, available label "
                "for every one of J's hand-verified anchor dates.",
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    log(f"preflight: {pf}")
    if not pf["ok"]:
        log("PREREG HASH MISMATCH -- ABORTING. Do not proceed on a drifted prereg.")
        out = {"generated_at": dt.datetime.now().isoformat(), "preflight": pf,
               "aborted": True, "reason": "prereg_hash_mismatch"}
        OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        return 1

    calendar = RegimeCalendar()
    global_tautology = tautology_stats(calendar, FULL_WINDOW_START, FULL_WINDOW_END)
    log(f"global tautology check: cramers_v={global_tautology['cramers_v']} n_days={global_tautology['n_days']}")

    # ---- KNOWN-BAD cohorts ----
    log("loading known-bad cohorts...")
    nlwb = load_dated_pnl_cohort(NLWB_FILE)
    confluence = load_dated_pnl_cohort(CONFLUENCE_FILE)
    double_top = load_dated_pnl_cohort(DOUBLE_TOP_FILE)
    placebo = build_placebo_cohort(calendar)
    log(f"nlwb n={len(nlwb)} confluence n={len(confluence)} double_top n={len(double_top)} placebo n={len(placebo)}")

    known_bad_results = {}
    for name, cohort in (("nlwb_full_real_fills", nlwb),
                          ("confluence_real_fills_fresh95", confluence),
                          ("double_top_real_fills", double_top),
                          ("pure_noise_random_entry_placebo", placebo)):
        res = validate_candidate(cohort, candidate_name=name, calendar=calendar,
                                  full_window_start=FULL_WINDOW_START, full_window_end=FULL_WINDOW_END)
        known_bad_results[name] = res
        log(f"KNOWN-BAD {name}: verdict={res['verdict']} bucket={res.get('target_regime_bucket')} "
            f"n_bucket={res.get('n_bucket')}")

    # ---- KNOWN-GOOD cohorts ----
    log("computing known-good vwap_continuation ITM-2/-8% cohort (real OPRA sim, one cell)...")
    vwap_cohort, vwap_cov = build_vwap_continuation_itm2_cohort()
    vwap_result = validate_candidate(vwap_cohort, candidate_name="vwap_continuation_itm2_tight8pct",
                                      calendar=calendar, full_window_start=FULL_WINDOW_START,
                                      full_window_end=FULL_WINDOW_END)
    log(f"KNOWN-GOOD vwap_continuation_itm2_tight8pct: verdict={vwap_result['verdict']} "
        f"bucket={vwap_result.get('target_regime_bucket')} n_bucket={vwap_result.get('n_bucket')}")

    anchor_check = op16_anchor_qualitative_check(calendar)
    log(f"OP-16 anchor qualitative check: all_dates_labelable={anchor_check['all_dates_labelable']}")

    # ---- SELF-VALIDATION VERDICT (precommitted criteria from the prereg) ----
    known_bad_pass_leak = [name for name, r in known_bad_results.items()
                            if r["verdict"] in ("PASS", "PASS_BUT_DEGENERATE_REGIME_PROXY")]
    known_good_killed = vwap_result["verdict"] in ("FAIL", "INSUFFICIENT_REGIME_SHIFT", "INSUFFICIENT_N")
    anchor_problem = not anchor_check["all_dates_labelable"]

    self_val_fails = bool(known_bad_pass_leak) or known_good_killed or anchor_problem
    self_validation_verdict = "FAILS_SELF_VALIDATION" if self_val_fails else "EARNS_RIGHTS"

    fail_reasons = []
    if known_bad_pass_leak:
        fail_reasons.append(f"known-bad cohort(s) PASSED: {known_bad_pass_leak} -- methodology-shopping.")
    if known_good_killed:
        fail_reasons.append(f"known-good vwap_continuation cohort was KILLED (verdict={vwap_result['verdict']}) -- over-strict, not better.")
    if anchor_problem:
        fail_reasons.append("OP-16 anchor dates could not be coherently labelled by the classifier.")

    log(f"SELF-VALIDATION VERDICT: {self_validation_verdict}")
    if fail_reasons:
        for r in fail_reasons:
            log(f"  - {r}")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(ROOT)),
        "preflight": pf,
        "global_tautology_check": global_tautology,
        "known_bad_results": known_bad_results,
        "known_good_vwap_continuation_result": vwap_result,
        "known_good_vwap_continuation_coverage": vwap_cov,
        "op16_anchor_qualitative_check": anchor_check,
        "self_validation_verdict": self_validation_verdict,
        "self_validation_fail_reasons": fail_reasons,
        "cohort_sizes": {"nlwb": len(nlwb), "confluence": len(confluence),
                          "double_top": len(double_top), "placebo": len(placebo),
                          "vwap_continuation_itm2": len(vwap_cohort)},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
