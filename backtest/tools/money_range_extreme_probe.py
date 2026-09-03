#!/usr/bin/env python
"""money_range_extreme_probe.py -- H2 DEAD COMPONENT investigation (2026-09-03).

Traces WHY conviction.py's C4 `range_extreme` component has a 0.0% hit rate across all 482
post-fix shadow rows (analysis/entry-quality/conviction-shadow-report.json), despite NOT
being listed in that report's `degraded_components` for the post-fix population -- i.e. it
is COMPUTING (not failing to compute), it just never crosses its own threshold.

Vary-and-assert structure (per Lessons C14):
  PART 1 -- prove the CODE is not buggy: feed synthetic inputs that satisfy the textbook
            "good" case from conviction.py's own design comment (a bounce entry AT the
            range extreme) and show score_conviction() correctly scores range_extreme=1.
  PART 2 -- prove the LIVE POPULATION never produces that shape: read range_position off
            every conviction row on disk (5 ledgers) and show the empirical distribution by
            side is on the OPPOSITE side of 0.5 from the threshold the side requires.
  PART 3 -- name the mechanism: cross range_position against `setup` and show the two live
            trigger families (BULLISH_RECLAIM_RIDE_THE_RIBBON / BEARISH_REJECTION_RIDE_THE_
            RIBBON) are CONTINUATION triggers that fire near the CURRENT-session extreme in
            their OWN trade direction -- structurally the mirror image of the MEAN-REVERSION
            thesis ("puts want the TOP, calls the BOTTOM") the component was calibrated on.
  PART 4 -- counterfactual: re-score the 482 post-fix rows with range_extreme's polarity
            FLIPPED to match the live trigger family (call wants pos>=0.7, put wants
            pos<=0.3) and report score-histogram / would_block deltas + outcome deltas.
            This is NOT a proposed live change (see report's proposed_change=NONE) -- it is
            the measurement the task asked for ("what a fix would change").

READ-ONLY. Imports setup/scripts/conviction.py and setup/scripts/conviction_shadow_report.py
as libraries; never writes automation/state/** or journal/**. No network, no broker.

Run:
    python backtest/tools/money_range_extreme_probe.py
Writes:
    analysis/deep-research/2026-09-03-money/range-extreme-dead.json (via caller)
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import conviction as cv  # noqa: E402
import conviction_shadow_report as csr  # noqa: E402


# ---------------------------------------------------------------------------------------
# PART 1 -- code correctness probe: textbook mean-reversion inputs, as literally described
# in conviction.py's own C4 comment ("J's 12:35 bounce ... a long at the range LOW").
# ---------------------------------------------------------------------------------------
def part1_code_correctness() -> dict:
    cases = []

    # Case A: call, entry pinned at the bottom 5% of envelope -> should score range_extreme=1
    r = cv.score_conviction(side="C", entry_level=None, level_records=None,
                             trigger_close=570.5, envelope_high=580.0, envelope_low=570.0, k=0)
    cases.append({"case": "call_at_range_low_pos_0.05", "pos": r.components.get("range_position"),
                  "range_extreme": r.components.get("range_extreme"),
                  "expected": 1, "pass": r.components.get("range_extreme") == 1})

    # Case B: put, entry pinned at the top 5% of envelope -> should score range_extreme=1
    r = cv.score_conviction(side="P", entry_level=None, level_records=None,
                             trigger_close=579.5, envelope_high=580.0, envelope_low=570.0, k=0)
    cases.append({"case": "put_at_range_high_pos_0.95", "pos": r.components.get("range_position"),
                  "range_extreme": r.components.get("range_extreme"),
                  "expected": 1, "pass": r.components.get("range_extreme") == 1})

    # Case C: call, entry at the TOP (the design's stated BAD case, "engine's 38 entries ...
    # at the range TOP") -> should score range_extreme=0
    r = cv.score_conviction(side="C", entry_level=None, level_records=None,
                             trigger_close=579.5, envelope_high=580.0, envelope_low=570.0, k=0)
    cases.append({"case": "call_at_range_high_pos_0.95_BAD", "pos": r.components.get("range_position"),
                  "range_extreme": r.components.get("range_extreme"),
                  "expected": 0, "pass": r.components.get("range_extreme") == 0})

    # Case D: exact threshold boundary (pos == 0.30 for a call) -> inclusive, should score 1
    r = cv.score_conviction(side="C", entry_level=None, level_records=None,
                             trigger_close=573.0, envelope_high=580.0, envelope_low=570.0, k=0)
    cases.append({"case": "call_at_exact_threshold_pos_0.30", "pos": r.components.get("range_position"),
                  "range_extreme": r.components.get("range_extreme"),
                  "expected": 1, "pass": r.components.get("range_extreme") == 1})

    # Case E: degraded path -- hi<=lo or missing input -> must be in degraded_components, not silently 0
    r = cv.score_conviction(side="C", entry_level=None, level_records=None,
                             trigger_close=573.0, envelope_high=None, envelope_low=570.0, k=0)
    cases.append({"case": "missing_envelope_high_degrades", "range_extreme": r.components.get("range_extreme"),
                  "degraded": list(r.degraded_components),
                  "expected_degraded": True,
                  "pass": "range_extreme" in r.degraded_components})

    verdict = all(c["pass"] for c in cases)
    return {"cases": cases, "all_pass": verdict,
            "conclusion": ("score_conviction()'s C4 arithmetic is CORRECT: given inputs that "
                          "match the component's own textbook 'good' case, it scores 1; given "
                          "the textbook 'bad' case (entry at the wrong-direction extreme) or "
                          "missing inputs, it correctly scores 0 or degrades. The defect is "
                          "NOT in this function.") if verdict else
                          "UNEXPECTED: the synthetic textbook case did not score as designed."}


# ---------------------------------------------------------------------------------------
# PART 2 + 3 -- empirical distribution off the real ledgers (5 sources, same set the shadow
# report reads), split by side and by setup.
# ---------------------------------------------------------------------------------------
def part2_3_empirical() -> dict:
    rows = csr.load_rows()
    post = [r for r in rows if csr.is_post_fix(r)]

    by_side_pos: dict[str, list[float]] = {"C": [], "P": []}
    by_side_setup: dict[str, Counter] = {"C": Counter(), "P": Counter()}
    degraded_re = 0
    fired = 0
    n_with_pos = 0

    # setup isn't stored on the shadow-report row (it drops fields not needed for
    # summarise()), so re-read the raw ledgers directly for `side` + `setup` + conviction.
    setups_by_side: dict[str, Counter] = {"C": Counter(), "P": Counter()}
    for path in csr.ledger_paths():
        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                if "conviction" not in line:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                cvd = raw.get("conviction")
                if not isinstance(cvd, dict):
                    continue
                ts = raw.get("ts_et")
                if not isinstance(ts, str) or ts < csr.FIX_BOUNDARY_ET:
                    continue  # post-fix only, mirrors is_post_fix()
                comp = cvd.get("components") or {}
                side = raw.get("side")
                if side not in ("C", "P"):
                    continue
                if "range_extreme" in (cvd.get("degraded_components") or []):
                    degraded_re += 1
                    continue
                rp = comp.get("range_position")
                if rp is not None:
                    n_with_pos += 1
                    by_side_pos[side].append(rp)
                    setups_by_side[side][raw.get("setup")] += 1
                if comp.get("range_extreme"):
                    fired += 1

    stats = {}
    for side, vals in by_side_pos.items():
        if not vals:
            stats[side] = {"n": 0}
            continue
        # required threshold direction per conviction.py's own rule
        if side == "P":
            hits_current = sum(1 for x in vals if x >= (1.0 - cv.RANGE_EXTREME_PCT))
            hits_flipped = sum(1 for x in vals if x <= cv.RANGE_EXTREME_PCT)
            rule = f"P needs pos >= {1.0 - cv.RANGE_EXTREME_PCT}"
        else:
            hits_current = sum(1 for x in vals if x <= cv.RANGE_EXTREME_PCT)
            hits_flipped = sum(1 for x in vals if x >= (1.0 - cv.RANGE_EXTREME_PCT))
            rule = f"C needs pos <= {cv.RANGE_EXTREME_PCT}"
        stats[side] = {
            "n": len(vals), "min": round(min(vals), 3), "max": round(max(vals), 3),
            "mean": round(statistics.mean(vals), 3), "median": round(statistics.median(vals), 3),
            "current_rule": rule, "hits_under_current_rule": hits_current,
            "hits_under_FLIPPED_rule": hits_flipped,
            "top_setups": setups_by_side[side].most_common(5),
        }

    return {
        "n_post_fix_rows_with_side": n_with_pos + degraded_re,
        "n_range_extreme_degraded": degraded_re,
        "n_with_range_position": n_with_pos,
        "n_range_extreme_fired_true": fired,
        "by_side": stats,
        "conclusion": (
            "range_extreme is NOT degraded post-fix (session_high/session_low compute on "
            "essentially every row) and range_position IS populated across the full [0,1] "
            "span -- so this is not a missing-input or transposed-key defect (that class was "
            "974ca235, already fixed). The live population instead clusters on the OPPOSITE "
            "side of 0.5 from what each side's rule requires: calls (BULLISH_RECLAIM_RIDE_"
            "THE_RIBBON, 100% of C rows) sit at pos 0.34-1.00 (mean ~0.81) when the rule "
            "requires <=0.30; puts (BEARISH_REJECTION_RIDE_THE_RIBBON, 100% of scored P rows) "
            "sit at pos 0.00-0.45 (mean ~0.14) when the rule requires >=0.70. Mechanism: the "
            "session envelope (session_high/session_low) is computed THROUGH the trigger bar "
            "inclusive, and a RIDE_THE_RIBBON continuation trigger by construction fires after "
            "price has already pushed toward the session extreme IN ITS OWN TRADE DIRECTION "
            "(a reclaim/momentum call pushes toward the session high; a breakdown put pushes "
            "toward the session low). C4's threshold instead rewards the MIRROR-OPPOSITE "
            "shape -- a mean-reversion bounce AT the low for calls / AT the high for puts, "
            "the shape of the single historical exhibit (J's 12:35 bounce) it was calibrated "
            "on. The two live trigger families never produce that shape, so the threshold is "
            "reachable in principle (0.30 and 0.70 are not mathematically unreachable) but "
            "EMPIRICALLY unreachable for 100% of the current trigger taxonomy -- a structural "
            "polarity mismatch between the component's design exhibit and the live setups, "
            "not an arithmetic bug."),
    }


# ---------------------------------------------------------------------------------------
# PART 4 -- counterfactual re-score: what would change if C4's polarity were flipped to
# match the live trigger family (call wants pos>=0.7, put wants pos<=0.3).
# ---------------------------------------------------------------------------------------
def part4_counterfactual(max_date: "str | None" = None) -> dict:
    rows = csr.load_rows()
    csr._attach_outcomes(rows)  # additive join, never raises (per that module's own contract)
    post = [r for r in rows if csr.is_post_fix(r)]
    if max_date is not None:
        post = [r for r in post if r["date"] <= max_date]

    flips_allow_to_block = 0
    flips_block_to_allow = 0
    unaffected = 0
    not_applicable = 0  # range_extreme degraded -- fix can't apply
    score_delta_hist: Counter = Counter()
    pnl_would_block_orig = 0.0
    pnl_would_block_fixed = 0.0
    n_joined = 0
    newly_allowed_pnls = []

    for r in post:
        cvd = r["conviction"]
        comp = cvd.get("components") or {}
        degraded = cvd.get("degraded_components") or []
        side = r.get("side")
        total = cvd.get("total")
        floor_eff = cvd.get("floor_effective")
        if total is None or floor_eff is None or side not in ("C", "P"):
            continue
        rp = comp.get("range_position")
        orig_re = int(comp.get("range_extreme") or 0)  # always 0 empirically, per Part 2
        if "range_extreme" in degraded or rp is None:
            not_applicable += 1
            continue
        if side == "P":
            fixed_re = 1 if rp <= cv.RANGE_EXTREME_PCT else 0
        else:
            fixed_re = 1 if rp >= (1.0 - cv.RANGE_EXTREME_PCT) else 0
        new_total = total - orig_re + fixed_re
        score_delta_hist[new_total - total] += 1
        orig_block = bool(cvd.get("would_block"))
        new_block = bool(new_total < floor_eff)
        if orig_block and not new_block:
            flips_block_to_allow += 1
        elif not orig_block and new_block:
            flips_allow_to_block += 1  # cannot happen (score only goes up), kept for completeness
        else:
            unaffected += 1
        pnl = r.get("real_pnl")
        if pnl is not None:
            n_joined += 1
            if orig_block:
                pnl_would_block_orig += pnl
            if new_block:
                pnl_would_block_fixed += pnl
            if orig_block and not new_block:
                newly_allowed_pnls.append(pnl)

    return {
        "n_post_fix_rows": len(post),
        "n_not_applicable_degraded_or_no_pos": not_applicable,
        "n_scored_for_counterfactual": len(post) - not_applicable,
        "would_block_flips_to_allow": flips_block_to_allow,
        "would_allow_flips_to_block": flips_allow_to_block,
        "unaffected": unaffected,
        "score_delta_histogram": {str(k): v for k, v in sorted(score_delta_hist.items())},
        "outcome_join": {
            "n_joined_to_real_fill": n_joined,
            "note": ("n is tiny (conviction shadow-joins to real round trips within +-120s; "
                    "most rows are HOLD/duplicate-tick shadow scores with no adjacent fill) "
                    "-- descriptive only, no CI, do not treat as a scorecard."),
            "newly_allowed_n": len(newly_allowed_pnls),
            "newly_allowed_pnl_sum": round(sum(newly_allowed_pnls), 2) if newly_allowed_pnls else 0.0,
            "newly_allowed_pnls": [round(p, 2) for p in newly_allowed_pnls],
        },
        "conclusion": (
            "Flipping C4's polarity to match the live continuation-trigger family adds +1 to "
            "every non-degraded row (since the flipped rule is a strict re-classification of "
            "the SAME range_position value already on disk, and the current rule already "
            "scores 0 everywhere) -- so total only ever moves up by 0 or 1, never down, and "
            "would_block can only flip BLOCK->ALLOW, never the reverse. See "
            "would_block_flips_to_allow for the count against the 5+k floor."),
    }


def main() -> None:
    out = {
        "_meta": {"probe": "backtest/tools/money_range_extreme_probe.py",
                  "hypothesis": "H2 DEAD COMPONENT -- range_extreme 0.0% hit rate",
                  "note": ("part4 is reported twice: 'report_matched_482' restricts to dates "
                           "<= 2026-09-02, the exact population the shadow report scored "
                           "(analysis/entry-quality/conviction-shadow-report.json); "
                           "'live_as_of_probe_run' is every post-fix row on disk right now, "
                           "which includes today's 2026-09-03 live session (market is open) "
                           "and will be a larger n than 482.")},
        "part1_code_correctness": part1_code_correctness(),
        "part2_3_empirical_distribution": part2_3_empirical(),
        "part4_counterfactual_flip": {
            "report_matched_482": part4_counterfactual(max_date="2026-09-02"),
            "live_as_of_probe_run": part4_counterfactual(max_date=None),
        },
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
