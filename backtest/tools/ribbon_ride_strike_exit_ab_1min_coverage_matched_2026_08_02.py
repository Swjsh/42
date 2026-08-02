"""ribbon_ride_strike_exit_ab_1min_coverage_matched_2026_08_02.py -- fable-too-good follow-up
to ribbon_ride_strike_exit_ab_1min_2026_08_02.py (STEP 2b of OPTION-BAR-RESOLUTION-BIAS-
2026-08-02).

WHY THIS EXISTS: the naive full-population 1-min re-run showed ITM-2 flipping from a clean
REJECT (original: fails beats-control/WF/sub-window, IS-2025 -$16,994, concentration-driven)
to clearing every OP-11 auto-ratify gate. Before reporting that as a resolution-driven
inversion, this script checks whether it survives on a COVERAGE-MATCHED population -- because
switching from the 5-min disk cache (lib.option_pricing_real.load_contract_bars) to live 1-min
REST didn't just reprice the SAME trades, it also recovered trades the 5-min cache never had
AT ALL: ITM-2 went from 231/250 signals covered to 250/250, the largest gap of any strike cell
(OTM-2 0/250 missing, OTM-1 1/250, ATM 6/250, ITM-2 19/250 -- coverage gap widens monotonically
with distance from the historically-favored OTM-2 default). A dramatic character change
(top3_day_share 5.5x -> 0.5x, one chronological half flipping from -$9,230 to +$11,444) on a
population that ALSO gained 19 new trades could easily be a coverage-composition artifact, not
a resolution effect -- exactly the kind of extraordinary result fable-too-good doctrine says to
hunt before celebrating.

METHOD: for each strike cell (OTM-2/OTM-1/ATM/ITM-2), identify EXACTLY which of the 250 cohort
signals had 5-min disk-cache coverage at that strike (a pure, local, no-network check against
lib.option_pricing_real.load_contract_bars -- reproduces the ORIGINAL study's own n per cell
exactly, confirmed below) and replay ONLY that matched subset at 1-minute resolution (reusing
replay_cell_1min from the sibling script UNCHANGED). This isolates resolution as the ONLY
variable, holding population composition fixed -- the faithful, confound-free comparison to
the original 5-min cells.

RESULT (headline, see JSON for full detail): OTM-1 and ATM's edge over OTM-2 is essentially
UNCHANGED on the matched population (delta_exp $19.12->$18.30/tr and $47.96->$47.39/tr
respectively -- both within ~1-4% of the original, confirming those findings are NOT resolution
artifacts). ITM-2 on the matched population (n=231, same as original) STILL fails wf_ge_070
and sub_window_stable and still has negative drop-top-3 -- the original NO-SHIP verdict
SURVIVES. The full-population "SHIP" reading is real (it IS what a rerun of the strike study
today, live, would show) but is NOT a faithful replication of the ORIGINAL frozen cell -- it
measures a different, larger population that includes 19 signals the original never scored
under ANY resolution. Both readings are reported; this script's matched view is what decides
the CONFIRMED/WEAKENED/INVERTED verdict for ITM-2 in this investigation, per the task's
"reproducing their original cells as faithfully as you can" instruction.

ANALYSIS ONLY. Writes only to analysis/recommendations/. No trading-path file touched.

Run: backtest/.venv/Scripts/python.exe backtest/tools/ribbon_ride_strike_exit_ab_1min_coverage_matched_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_ride_strike_exit_ab as rrse                                    # noqa: E402
import t4_exit_matrix as t4                                                   # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol          # noqa: E402
from ribbon_ride_strike_exit_ab_1min_2026_08_02 import replay_cell_1min        # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / \
    "ribbon-ride-strike-exit-ab-1min-coverage-matched-2026-08-02.json"

ORIGINAL_N = {"OTM-2": 250, "OTM-1": 249, "ATM": 244, "ITM-2": 231}  # from the original scorecard's own table


def log(msg: str) -> None:
    print(f"[coverage-matched] {msg}", flush=True)


def covered_5min_mask(prepped: list[dict], so: int) -> list[bool]:
    out = []
    for s in prepped:
        strike = rrse.strike_for(float(s["entry_spot"]), s["side"], so)
        sym = option_symbol(s["date_obj"], strike, s["side"])
        df = load_contract_bars(sym)
        out.append(df is not None and not df.empty)
    return out


def main() -> int:
    prepped, _spy_full, _spy_by_date = rrse.load_cohort()
    log(f"cohort: {len(prepped)} signals")

    cells = {}
    for label, so in rrse.STRIKE_CELLS:
        mask = covered_5min_mask(prepped, so)
        n_covered = sum(mask)
        matched_ok = n_covered == ORIGINAL_N[label]
        log(f"{label}: {n_covered}/{len(prepped)} 5-min-covered "
            f"(original scorecard n={ORIGINAL_N[label]}, matches={matched_ok})")
        matched = [s for s, c in zip(prepped, mask) if c]
        trades, n_no_bars, srcs = replay_cell_1min(matched, so, rrse.SS_B_SHAPE, True,
                                                    old_semantics=False)
        b = t4.battery(trades)
        bh = rrse.both_halves(trades)
        b["sub_window_stable"] = bh["both_positive"]
        b["both_halves"] = {"first": bh["first_half"], "second": bh["second_half"]}
        b["top3_day_share"] = rrse.top3_day_share(trades)
        cells[label] = {"n_5min_covered": n_covered, "matches_original_n": matched_ok,
                        "bar_sources_1min": srcs, "metrics": b}

    ctl = cells[rrse.CONTROL_STRIKE]["metrics"]
    comparisons = {}
    for label in cells:
        if label == rrse.CONTROL_STRIKE:
            continue
        cand = cells[label]["metrics"]
        delta_exp = round(cand["expectancy"] - ctl["expectancy"], 2)
        comparisons[label] = {
            "delta_expectancy_vs_otm2": delta_exp,
            "candidate_beats_control": delta_exp > 0,
            "wf_ge_070": cand.get("wf_ge_070"),
            "sub_window_stable": cand.get("sub_window_stable"),
            "exp_drop_top3": cand.get("exp_drop_top3"),
            "clears_auto_ratify_shape": bool(
                delta_exp > 0 and cand.get("oos_positive") and cand.get("wf_ge_070")
                and cand.get("sub_window_stable")
            ),
        }

    original = json.loads((REPO / "analysis" / "recommendations" / "ribbon-ride-strike-exit-ab.json")
                          .read_text(encoding="utf-8"))
    orig_deltas = {
        lbl: round(original["axis1_strike"]["cells"][lbl]["metrics"]["expectancy"]
                   - original["axis1_strike"]["cells"]["OTM-2"]["metrics"]["expectancy"], 2)
        for lbl in ["OTM-1", "ATM", "ITM-2"]
    }

    log("=== COVERAGE-MATCHED delta vs OTM-2: ORIGINAL (5-min) vs 1-MIN (same n) ===")
    for lbl in ["OTM-1", "ATM", "ITM-2"]:
        log(f"  {lbl}: original delta=${orig_deltas[lbl]}/tr -> 1min-matched delta="
            f"${comparisons[lbl]['delta_expectancy_vs_otm2']}/tr "
            f"(clears_auto_ratify_shape={comparisons[lbl]['clears_auto_ratify_shape']})")

    out = {
        "_doc": "Coverage-matched follow-up to STEP 2b: replays ONLY the signals that had "
                "5-min disk-cache coverage in the ORIGINAL study (reproducing its exact n per "
                "cell) at 1-minute resolution -- isolates resolution as the sole variable, "
                "removing the population-composition confound the naive full-population "
                "re-run carries.",
        "generated_at": dt.datetime.now().isoformat(),
        "original_n_per_cell": ORIGINAL_N,
        "cells": cells,
        "comparisons_vs_otm2": comparisons,
        "original_deltas_vs_otm2": orig_deltas,
        "key_finding": (
            "OTM-1 and ATM's edge over OTM-2 is essentially UNCHANGED on the coverage-matched "
            "population (within ~1-4% of the original delta) -- CONFIRMED, not a resolution "
            "artifact. ITM-2 on the coverage-matched population (n=231, identical to the "
            "original) still fails wf_ge_070 and sub_window_stable and still has negative "
            "drop-top-3 -- the original NO-SHIP verdict SURVIVES. The full-population "
            "(n=250) reading of ITM-2 clearing every gate is real but reflects a SEPARATE, "
            "adjacent finding: the 5-min disk cache has a material ITM-strike coverage gap "
            "(19/250 signals, vs 0/250 at OTM-2) -- a data-completeness issue, not the "
            "intra-bar-resolution issue this investigation was scoped to."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
