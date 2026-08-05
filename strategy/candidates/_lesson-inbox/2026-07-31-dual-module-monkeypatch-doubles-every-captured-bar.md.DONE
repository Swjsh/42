# Lesson inbox — 2026-07-31: a capture monkeypatch on TWO module bindings recorded every bar twice, and only the BAR counts were wrong

**Source fire:** filter-5 (ribbon MA-stack) fate lane, 2026-07-31 evening — correction pass.
**Artifacts:** `analysis/recommendations/filter5-ribbon-2026-07-31.json` / `.md` ·
runner `backtest/tools/filter5_ribbon_fate_2026_07_31.py#Blockers5Capture` ·
guard `backtest/tests/test_filter5_capture_no_double_count.py`.

## Symptom

The scorecard reported cohort A — the setups filter 5 blocked ALONE — as **346 bull bars / 152
bear bars** full-history and **56 / 48** over the recent 25 days. The true counts are **173 / 76**
and **28 / 24**. Every number was exactly **2x**.

These figures were quoted to J in the STATUS.md signal block.

## Root cause

`run_arm` patches the evaluator on **both** `lib.orchestrator` and `lib.engine.score`. That dual
patch is CORRECT and deliberate: each module did `from .filters import evaluate_*` and so holds
an independent by-name binding, and `orchestrator.py`'s per-bar parity cross-check
(`_ENGINE_SCORE_ASSERT`) deliberately drives every bar through both so the two scoring paths are
proven to agree under the treatment. Patching only one side makes that assert fire on bar 48.

The defect was in the CAPTURE, not the patch: the closure did a plain `list.append`, so one bar
observed by two bindings became two rows.

## Why it survived review

**Day counts were never wrong.** `len({row['date'] for row in rows})` absorbs the duplicate, so
`n_days_full = 77` and `n_days_recent25 = 12` were correct the whole time and looked consistent
with everything else. Only the BAR counts inflated — and the bar counts were the ones in the
headline. A reviewer sanity-checking "77 days, sounds right" gets no signal at all.

**No gate, delta, P&L or verdict depended on cohort A.** It is descriptive. The arm's realized
cohort is `added_stats`, computed from walked trades on a different code path. So every
cross-check that would normally catch an n error (does the delta reconcile? does the P&L add up?)
passed cleanly. A wrong number with no downstream consumer has nothing to contradict it.

## The generalizable rule

**When you monkeypatch the same callable into N module bindings, any side-effect in that closure
fires N times. Dedupe the side-effect on a natural key; do not "divide by N" after the fact.**

Corollary, and the sharper half: **a descriptive statistic with no downstream consumer is the
LEAST-verified number in any artifact, and therefore the most likely to be wrong.** Reconciliation
only protects numbers that feed something. Anything that is merely *reported* — cohort sizes, bar
counts, coverage tallies — needs its own explicit assertion, because nothing else will ever
disagree with it.

## Fix + guard

- `Blockers5Capture` keys rows on `(side, timestamp)`, so re-introducing the dual patch — or
  adding a THIRD patched module — cannot re-inflate the counts. Structural, not corrected-once.
- `duplicate_hits` is kept and asserted **non-zero** (`assert_dual_patch_observed`): if it ever
  reads 0, the parity cross-check has stopped running and the capture has gone half-blind. The
  dedupe counter doubles as a liveness probe for the mechanism it defends against (C7).
- Guard is two-layer, both RED-proofed:
  1. **mechanism** — replaying the dual-binding call pattern; fails against restored
     `list.append` semantics.
  2. **shipped artifact** — asserts the committed scorecard's cohort-A samples carry no duplicate
     timestamps. This layer FAILED against the pre-correction JSON (all 16 sampled rows were
     exact adjacent duplicates). Without it a correct re-run could still be paired with a stale
     surface, which is the C7 shape that produced this entry in the first place.

## Index

Fits **C14** (dead/translated-but-unapplied knobs and n-accounting defects) with a strong **C7**
component (audit the OUTPUT, never the exit code — and audit the SHIPPED SURFACE, not just the
code that generates it).
