# Lesson candidate: two scorecards on the IDENTICAL signal cohort reached OPPOSITE-SIGN verdicts because neither declared its friction/shape/fill-bar/structure-layer conventions in a checkable place

> Queued by Claude (JOB1 convention reconciliation, `backtest/tools/strike_ab_convention_reconciliation.py`) 2026-07-15. lesson-author picks up at next wake fire. Sibling of the pending `2026-07-11-fill-bar-window-convention-divergence.md` item (same family: two engines replaying "the same trade" under undisclosed-divergent conventions) — this is a FRESH, concrete instance with a different, larger dominant cause, not a duplicate.

## Symptom
The 2026-07-14 strike A/B (`ribbon_ride_strike_exit_ab.py`, commit 81b25b4 — the study whose scorecard armed the ATM strike-tier override in CLAUDE.md) reported its ATM/SS-B cell at +$65.82/tr (n=244, QTY=10, zero friction code). The same night's `debit_spread_ab_study.py`, run on the SAME 250-signal ribbon_ride cohort (same n=244 after coverage drops) with an ATM long leg, reported its naked-ATM control at -$5.24/tr — a **sign flip on what was assumed to be the same measurement.** Both scripts' own docstrings describe the population as the shared canonical cohort; neither states in a machine-checkable way which of 5 independent convention axes it uses, so the sign flip read as a real finding rather than a units mismatch until a toggle-by-toggle reconciliation (`analysis/recommendations/strike-ab-convention-reconciliation.json`) was run.

## Root cause
The two scripts differ on 5 axes, only 2 of which were named when the reconciliation was requested (friction, fill-bar convention) — the other 3 were undisclosed: (1) **exit shape** — `ribbon_ride_strike_exit_ab.py` holds `SS_B_SHAPE` fixed; `debit_spread_ab_study.py`'s `_live_shape()` reads `automation/state/params.json` FRESH at run time, which differs from SS-B on every knob except `premium_stop_pct` (tp1_premium_pct 0.50 vs 1.0, tp1_qty_fraction 0.8 vs 0.667, profit_lock_mode fixed vs trailing, trail_pct 0.125 vs 0.15, runner_target_pct 2.5 vs 9.9, time_stop 15:40 vs 15:50) — this ONE axis alone is -$57.81/tr, 81% of the total -$71.06/tr gap; (2) **structure-stop chart layer** — present in `ribbon_ride_strike_exit_ab.py` (SS-B's ss_time branch), absent in `debit_spread_ab_study.py` (premium-only, per its own disclosure) — worth +$32.55/tr in isolation, i.e. it was pulling the OTHER direction and partially offsetting the shape/friction hit, which would have been invisible without decomposing it separately; (3) **friction** — absent vs present, -$47.86/tr, the single factor J's framing correctly flagged; (4) **fill-bar convention** — `debit_spread_ab_study.py`'s own docstring self-identifies as "Fill-bar-INCLUDED... same as t4_exit_matrix._load_bars," which is the OLD, PRE-p5_topcell-fix convention, not "the corrected" one as the task brief characterized it — worth a negligible +$2.06/tr here, direction-noise-level, and mislabeled as a fix when it is a regression; (5) **premium_stop stage-label handling** — the fix debit_spread_ab_study.py applies (use `runner_stop_premium` not the static level) is a verified NO-OP for both scripts under `ARM_SCOPE_POST_TP1` ($0.00/tr) — it only matters for `ARM_SCOPE_FULL` shapes neither script here uses. QTY=10 was actually IDENTICAL in both (confirmed zero contribution) despite being named as a suspect axis. Net: the two named axes (friction + fill-bar) explain roughly two-thirds of the gap; the two UNNAMED axes (shape-config swap + structure-layer presence) explain the rest, and one of the "named fixes" (fill-bar) was mischaracterized in the request itself.

## Fix
`strike_ab_convention_reconciliation.py` re-ran the strike axis with SS-B genuinely held fixed (the literal ask) plus honest friction — under that honest-but-comparable convention the ATM-vs-OTM-2 relative delta SURVIVES ($50.52/tr honest vs $47.96/tr pre-friction) and ATM is the ONLY one of the 4 strike cells that clears positive expectancy overall AND is stable across both chronological halves, so the arming decision stands on relative grounds independent of the debit-spread study's apples-to-oranges number. The reconciliation script's `convention_audit` block and a 2^5 factorial (`job1b_gap_bridge_atm`, forward + reverse path + order-independent main effects, empirically confirmed additive/order-independent to the cent) now exist as the reusable decomposition pattern.

## Generalization / spec for the missing machine-readable header
Every cohort-level scorecard JSON in `analysis/recommendations/` should carry a top-level `"convention_header"` object, checked by a shared assertion (extend `backtest/tests/test_graduated_guards.py`) before two scorecards are compared or a delta is quoted in prose:
```
"convention_header": {
  "signal_cohort_source": "<module.function that produced the signal population, e.g. _signal_cache.load_or_build_signals>",
  "exit_shape_source": "FROZEN:<name>" | "LIVE:params.json@<git_sha_or_mtime>",
  "structure_stop_layer": true | false,
  "friction_model": "none" | "simulator_credit.DEFAULT_*",
  "fill_bar_convention": "corrected_exclude_fill_bar" | "old_include_fill_bar",
  "qty_convention": "flat_relative:<n>" | "production_scaled",
  "time_stop_et": "HH:MM"
}
```
A scorecard that quotes a delta against ANOTHER scorecard, or gets cited in prose as "same cohort, different X," must diff this header first — a mismatched header means the comparison is NOT isolating the variable it claims to, and any headline number built on it (including one that later arms a live override) should be labeled comparison-invalid until reconciled, exactly as this ATM override nearly was.

## Encoded in
`analysis/recommendations/strike-ab-convention-reconciliation.json` + `.md` (the decomposition + the audit language). TODO for lesson-author: add the `convention_header` schema above to a shared validator and wire it into any script under `backtest/tools/*_ab*.py` / `*_study.py` that writes to `analysis/recommendations/`.

## L## (optional)
Max lesson number as of this filing is L200 (`markdown/doctrine/LESSONS-LEARNED.md`) — suggest **L201**. Fold into theme **C6** (no look-ahead / bar-convention discipline) alongside the sibling `2026-07-11-fill-bar-window-convention-divergence.md` item, OR promote to a new sub-theme if a second fill-bar-adjacent lesson in 4 days signals C6 needs a dedicated "cross-scorecard convention parity" bullet distinct from the look-ahead bullets already there.
