# Lesson candidate: a ROLLING state file silently turns every old study that reads it into an n=0 "verdict"

> Queued by the SLIPPAGE-REBASELINE study, 2026-08-12.
> Prereg: `analysis/recommendations/prereg-slippage-rebaseline-2026-08-12.json`.

## Symptom

Re-running published studies to re-baseline them produced clean exit-0 runs with **empty
populations and a real-looking verdict**:

| script | published | re-run today |
|---|--:|--:|
| `backtest/autoresearch/orb_real_fills_validate.py` | n=10, `verdict: FAIL` | **n=0**, `verdict: FAIL` |
| `backtest/autoresearch/v14e_chart_stop_research.py` | n_stopped_obs=100 | **n_stopped_obs=0** |

The ORB script logged `Test cases: 0 total` and then wrote `verdict: FAIL` with
`total_pnl: 0`. Nothing errored. Exit code 0. **The re-run "confirmed" the published KILL
while measuring nothing at all** — and would have been reported as a confirmation if the study
had not carried a mandatory reproduction gate.

## Root cause

`automation/state/watcher-observations.jsonl` is the trade population for a family of studies,
and it is a **rolling file**. `setup/scripts/heal-engine.ps1` (line ~119) rotates it into
`automation/state/archive/` once it exceeds 1MB, keeping only a tail. Today it holds **102 rows,
all dated 2026-08-12** — one day. The May/June studies that consumed thousands of rows cannot
see their own inputs any more, and the watchers they filtered on (`v14_enhanced_watcher`,
`orb_watcher`) are no longer in the live lineup, so the filter matches zero rows.

This is the same class as L234 (a "real fills" arm-scope filter going synthetic-by-omission when
the live lineup moves on), but the trigger here is **file rotation**, not lineup drift, and the
failure is silent because "no rows matched the filter" is indistinguishable from "the filter
correctly excluded everything".

## What recovery looks like (and its limit)

Per the standing rule from commit e8e7913d — *check whether the PRODUCER can re-run, not just
whether the OUTPUT was stored* — the archives were checked and history **is** recoverable:
`archive/watcher-observations-rotated-2026-06-22.jsonl` alone holds 4,914 rows back to
2025-01-02, including `v14_enhanced_watcher` (563) and `orb_watcher` (402). A read-only union of
6 archives + the live file yields **7,681 rows over 376 dates**.

**But a reconstruction is not a reproduction.** It is a *superset*: observations kept accruing
after each study published, so `v14e_chart_stop_research` re-runs at n=132 against a published
100. Nothing ever snapshotted the population a study actually consumed, so the original numbers
are unrecoverable for most cells. (One did reproduce exactly — `orb_real_fills_validate` returned
its published 2.7 / 272.8 / 18.0 — which is what validated the reconstruction method itself.)

## Fix

1. **Any study whose population comes from a rolling/rotating state file must snapshot its
   inputs** into its own output artifact (or write an input hash + row count) at publish time.
   Without that, the verdict is unauditable the moment the file rotates.
2. **A verdict artifact must record `n`**, and any consumer comparing verdicts must treat
   `n == 0` as `NO_RESULT`, never as a verdict. The ORB script's `verdict: FAIL` at n=0 is the
   bug in miniature.
3. When re-running any historical study, **gate on reproduction of the published headline
   numbers before believing any delta** — this is what caught it here.

## Detection / guard

Add an assertion to studies reading `watcher-observations.jsonl` (and any rolling state file):
`assert len(population) > 0, "empty population — source file may have rotated"`. Fail loudly
rather than emitting a verdict. Pairs with the existing C7 family (silent success is failure —
audit outputs, not exit codes).
