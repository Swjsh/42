"""run_trendline_swing_battery.py -- the trendline swing MES battery orchestrator.

The ONE untested cell in the futures-swing kill pile (2 prior batteries, 0/96 cells,
neither tested a trendline setup -- see `analysis/recommendations/
futures-swing-phase1-summary.md`). Full grammar/grid/gate: `analysis/deep-research/
TRENDLINE-SWING-MES-PREREG-2026-08-09.md` (frozen and committed before this file existed).

Pipeline: load the SAME cached Databento MES 1m file the prior two batteries used ->
resample daily + 4h-of-RTH (native window only, through 2026-06-12 -- no yfinance
extension, matching the prior battery's own 4h-scope disclosure) -> fetch daily VIX ->
run the official (bias-filter ON) 72-cell battery through `trendline_swing_seed.
score_trendline_seed` -> run the bias-filter-OFF robustness variant (informational only,
NOT part of the PASS/KILL verdict) -> write one scorecard JSON + append a data-versions.jsonl
provenance row.

Run: backtest/.venv/Scripts/python.exe backtest/futures/run_trendline_swing_battery.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "futures"))

warnings.filterwarnings("ignore", category=FutureWarning)  # mixed-DST-offset parse warning, already handled/tested

from futures.data import load_continuous_csv, resample_daily, resample_4h_rth, fetch_vix_daily  # noqa: E402
from futures.instruments import MES  # noqa: E402
from futures.seeds import trendline_swing_seed as tls  # noqa: E402

MES_CSV = REPO / "backtest" / "data" / "futures" / "MES_1m_continuous.csv"
REC_DIR = REPO / "analysis" / "recommendations"
DATA_VERSIONS = REPO / "analysis" / "backtests" / "data-versions.jsonl"

OOS_CUT = dt.date(2026, 1, 1)
H4_HORIZONS = [(2, "1d"), (6, "3d"), (10, "5d")]   # 2 4h-of-RTH bars/day -- same mapping structure_bos_choch used


def log(msg: str) -> None:
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def append_data_version(row: dict) -> None:
    DATA_VERSIONS.parent.mkdir(parents=True, exist_ok=True)
    with DATA_VERSIONS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def load_and_prepare() -> dict:
    t0 = time.time()
    log(f"loading {MES_CSV.name} ...")
    raw = load_continuous_csv(str(MES_CSV))
    span = (str(raw["timestamp_et"].min()), str(raw["timestamp_et"].max()))
    log(f"loaded {len(raw)} 1m bars, span {span}, in {time.time()-t0:.1f}s")

    daily = resample_daily(raw)
    h4 = resample_4h_rth(raw)
    log(f"resampled: daily={len(daily)} bars, 4h-of-RTH={len(h4)} bars "
        f"(IS={ (h4['date']<OOS_CUT).sum() } / OOS={ (h4['date']>=OOS_CUT).sum() } 4h bars)")

    today = dt.date.today()
    log("fetching daily VIX (regime split, yfinance ^VIX) ...")
    vix_df = fetch_vix_daily("2025-01-01", str(today + dt.timedelta(days=1)))
    vix_by_date = dict(zip(vix_df["date"], vix_df["vix_close"]))
    log(f"VIX daily rows: {len(vix_df)}")

    md5 = md5_of(MES_CSV)
    append_data_version({
        "ran_at": dt.datetime.now().isoformat(), "symbol": "mes_futures",
        "as_of": str(today), "status": "ok", "action": "trendline_swing_battery",
        "source": str(MES_CSV), "md5": md5, "rows_1m": len(raw), "span_et": list(span),
        "note": ("Trendline swing seed (2026-08-09) -- the one untested cell in the "
                 "futures-swing kill pile. Same cached Databento MES file as both prior "
                 "Phase-1 batteries (2026-07-02 DOES_NOT_TRANSFER, 2026-07-09 KILL all 3 "
                 "seeds). Native window only (through 2026-06-12), no yfinance extension "
                 "-- matches the prior battery's own 4h-scope disclosure. Prereg: "
                 "analysis/deep-research/TRENDLINE-SWING-MES-PREREG-2026-08-09.md."),
        "vix_rows": len(vix_df),
    })
    log(f"data-versions.jsonl row appended (md5={md5[:12]}...)")
    return {"daily": daily, "h4": h4, "vix_by_date": vix_by_date}


def compute_researcher_diagnostics(official: dict, robustness: dict) -> dict:
    """Beyond-the-mechanical-gate scrutiny -- the SAME depth of check this project's own
    prior batteries apply before trusting a raw PASS (VIX-regime concentration, IS/OOS
    sign stability, how many of the "clearing cells" are actually independent trade
    populations vs the same entries re-graded under a different horizon/stop, and
    sensitivity to the one disclosed robustness toggle). Computed from the already-scored
    cells, not a second data pass."""
    official_clearing = [c for c in official["cells"] if c["clears"]]
    robustness_clearing = [c for c in robustness["cells"] if c["clears"]]

    def population_key(c: dict) -> tuple:
        combo = c["combo"]
        return (combo["window"], combo["entry_trigger"], c["direction"])

    official_populations = sorted(set(population_key(c) for c in official_clearing))
    robustness_populations = sorted(set(population_key(c) for c in robustness_clearing))
    overlap = set(official_populations) & set(robustness_populations)

    regime_rows = []
    for c in official_clearing:
        lo_n = c["regime_split"]["vix_lt_17.5"]["n"] or 0
        hi_n = c["regime_split"]["vix_gte_17.5"]["n"] or 0
        total = lo_n + hi_n
        regime_rows.append({
            "combo_id": c["combo_id"], "direction": c["direction"], "horizon": c["horizon_label"],
            "oos_n": c["oos"]["n"], "vix_lt_17.5_n": lo_n, "vix_gte_17.5_n": hi_n,
            "pct_high_vix": (round(100.0 * hi_n / total, 1) if total else None),
            "is_mean": c["is"]["mean"], "oos_mean": c["oos"]["mean"],
            "is_oos_sign_agrees": (
                None if c["is"]["mean"] is None or c["oos"]["mean"] is None
                else bool((c["is"]["mean"] > 0) == (c["oos"]["mean"] > 0))
            ),
            "is_n": c["is"]["n"],
        })

    return {
        "pseudo_replication_bug": {
            "found_and_fixed_this_session": True,
            "description": ("Multiple geometrically-valid-but-overlapping trendlines fired "
                             "identical (direction, signal_bar_idx) events; one bar was "
                             "counted 9x within a single combo before the fix. Regression "
                             "test: backtest/tests/test_trendline_swing_seed.py::"
                             "TestNoDoubleCounting."),
            "official_signals_before_fix": 820, "official_signals_after_fix": 458,
            "official_clearing_cells_before_fix": 7, "official_clearing_cells_after_fix":
                official["n_clearing_cells"],
        },
        "independent_populations_behind_the_clearing_cells": {
            "n_clearing_cells": len(official_clearing),
            "n_distinct_populations_by_window_trigger_direction": len(official_populations),
            "populations": [{"window": w, "entry_trigger": t, "direction": d} for w, t, d in official_populations],
            "note": ("Cells sharing (window, entry_trigger, direction) share the SAME "
                     "underlying entries and differ only in stop_shape/horizon grading -- "
                     "NOT independent confirmations. BH-FDR corrects for the number of "
                     "CELLS tested, not for this within-family correlation."),
        },
        "vix_regime_concentration_per_clearing_cell": regime_rows,
        "bias_filter_robustness_toggle": {
            "official_populations": [{"window": w, "entry_trigger": t, "direction": d} for w, t, d in official_populations],
            "bias_off_populations": [{"window": w, "entry_trigger": t, "direction": d} for w, t, d in robustness_populations],
            "overlap_count": len(overlap),
            "note": ("Toggling the (disclosed, pre-registered-as-informational-only) daily "
                     "bias filter OFF changes BOTH which combos clear AND which horizon "
                     "clears, with ZERO population overlap with the official set -- a "
                     "single reasonable methodological choice fully changes the answer."),
        },
    }


def write_scorecard(seed_slug: str, official: dict, robustness_bias_off: dict, extra_meta: dict) -> Path:
    REC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REC_DIR / f"futures-swing-{seed_slug}.json"
    diagnostics = compute_researcher_diagnostics(official, robustness_bias_off)
    # NOT auto-computed from a threshold: an early version of this script tried
    # `n_distinct_populations <= 2` as a proxy and got it WRONG (window=2 and window=3
    # bounce-short are DIFFERENT (window, entry_trigger, direction) keys but were verified
    # by hand -- see the results doc -- to share 6 of 8 distinct OOS calendar dates, i.e.
    # they are NOT independent even though the coarse key says n=3 "populations"). The
    # researcher_diagnostics block below reports the raw, correct facts (population KEYS,
    # VIX concentration, bias-toggle sensitivity); this label is the researcher's holistic
    # judgment after ALSO checking actual signal-date overlap by hand (not reproduced here
    # -- see analysis/deep-research/TRENDLINE-SWING-MES-2026-08-09.md), not a formula.
    practical_verdict = "PASS_BUT_NOT_TRUSTED"
    payload = {
        "rule_id": f"futures-swing-{seed_slug}", "phase": "1c",
        "generated_at": dt.datetime.now().isoformat(),
        "spec_origin": "analysis/deep-research/TRENDLINE-SWING-MES-PREREG-2026-08-09.md",
        "prior_art": {
            "note": ("The 2026-07-02 (DOES_NOT_TRANSFER, 0/12) and 2026-07-09 (KILL all 3 "
                     "seeds, 0/96) Phase-1 batteries tested rrw_short/e2_context/"
                     "structure_bos_choch -- NONE was a trendline setup. This scorecard is "
                     "that missing cell, using an externally-specified validity grammar "
                     "(Victoria Duke / 'Tori Trades') pre-registered BEFORE this run."),
            "path": "analysis/recommendations/futures-swing-phase1-summary.md",
            "verdict": "KILL (all 3 prior seeds; this is a 4th, independent seed family)",
        },
        **extra_meta,
        "mechanical_gate_verdict": official["verdict"],
        "practical_verdict": practical_verdict,
        "practical_verdict_note": ("The pre-registered mechanical gate (oos_mean>0 AND "
            "bh_fdr_survivor AND beats_buy_and_hold) is reported UNCHANGED below and was "
            "NOT redefined post-hoc. 'PASS_BUT_NOT_TRUSTED' is the researcher's separate, "
            "explicitly-labeled judgment call after applying the SAME beyond-the-gate "
            "scrutiny this project's own prior batteries use (regime concentration, IS/OOS "
            "stability, population independence, robustness-toggle sensitivity) -- see "
            "researcher_diagnostics and the results doc for the full reasoning. Full detail: "
            "analysis/deep-research/TRENDLINE-SWING-MES-2026-08-09.md."),
        "researcher_diagnostics": diagnostics,
        "official": official,
        "robustness_bias_filter_off": robustness_bias_off,
    }
    out_path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return out_path


def main() -> None:
    t_start = time.time()
    ctx = load_and_prepare()

    log("running OFFICIAL battery (bias filter ON, 72 cells) ...")
    t0 = time.time()
    official = tls.score_trendline_seed(ctx["h4"], ctx["daily"], MES, H4_HORIZONS, OOS_CUT,
                                         ctx["vix_by_date"], apply_bias_filter=True,
                                         informational_only=False)
    log(f"  official verdict: {official['verdict']} "
        f"({official['n_clearing_cells']}/{official['n_cells_tested']} cells clear, "
        f"{official['n_signals_total']} total signals) in {time.time()-t0:.1f}s")

    log("running ROBUSTNESS battery (bias filter OFF, informational only, 72 cells) ...")
    t0 = time.time()
    robustness = tls.score_trendline_seed(ctx["h4"], ctx["daily"], MES, H4_HORIZONS, OOS_CUT,
                                           ctx["vix_by_date"], apply_bias_filter=False,
                                           informational_only=True)
    log(f"  robustness (bias OFF) would-clear count: {robustness['n_clearing_cells']}/"
        f"{robustness['n_cells_tested']} cells, {robustness['n_signals_total']} total signals "
        f"in {time.time()-t0:.1f}s (NOT part of the official verdict, see prereg)")

    meta = {
        "bar_timeframe": "4h_of_rth", "instrument": "MES", "oos_cut": str(OOS_CUT),
        "horizons": H4_HORIZONS,
        "atr_stop_mult": tls.ATR_STOP_MULT, "atr_target_mult": tls.ATR_TARGET_MULT,
        "safety_stop_mult": tls.SAFETY_STOP_MULT, "safety_target_mult": tls.SAFETY_TARGET_MULT,
        "cost_per_side_usd": 2.50,
        "note": "Native Databento window only (through 2026-06-12); no yfinance extension at 4h.",
    }
    path = write_scorecard("trendline", official, robustness, meta)
    saved = json.loads(path.read_text(encoding="utf-8"))
    log(f"scorecard written: {path}")
    log(f"TOTAL runtime: {time.time()-t_start:.1f}s")
    log(f"MECHANICAL GATE VERDICT -- trendline_swing = {saved['mechanical_gate_verdict']}")
    log(f"PRACTICAL VERDICT (researcher judgment, see scorecard) = {saved['practical_verdict']}")


if __name__ == "__main__":
    main()
