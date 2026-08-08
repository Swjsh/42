# Lesson candidate: armed gates rot silently — the block_elite_bull scar generalized to a standing instrument

> Queued 2026-08-08 (build session: gate-recency doctrine + weekly instrument). lesson-author picks up at next wake fire.

## Symptom

`block_elite_bull` was revalidated 2026-07-10 (SS-B exit shape, KEEP verdict) under a level
feed that was **later found broken**. The gate kept blocking on that stale verdict for 21 days
with nothing noticing — including 111 refusals same-session on 2026-07-31 on a maxed 11/11
bull setup, while fleet arms that structurally never inherited `GATE_ORDER` took the identical
setup and made real money. That scar produced the first instrument
(`Gamma_GateExpiryCheck` / `gate_expiry_check.py`, J directive 2026-07-31).

One-off audit `analysis/recommendations/gate-recency-audit-2026-08-08.{md,json}` then found
the FIRST instrument itself has a scope gap: it only mines `GATE_ORDER` + two named vetoes +
fleet config. The scoring-filter layer (`backtest/lib/filters.py`), the extra-setup lane
(`extra_setup_exec_armed`), and `risk_gate` config modes (`pdt_gate_mode`) sit entirely outside
its reach. Inside that blind spot the audit found: (a) `pdt_gate_mode=margin_pdt` (Bold)
hard-blocking on a self-imposed rule the paper broker doesn't even enforce — one blocked day
alone cost a +$1,465 book day; (b) two GATE_ORDER-scope gates (`structure_veto_enabled` Safe,
`require_bearish_fill_bar` Bold) sitting RED per the FIRST instrument's own P&L check, 43 and
52 days past their revalidation interval, with nobody reading the output on a cadence; (c) a
551-tick/15-day volume-suppressor (`filter_10_min_triggers_bull=2` on Safe, double both Bold's
own setting and bear's own floor) with zero dated evidence for the asymmetry, invisible to the
first instrument entirely.

## Root cause

**Two distinct, compounding failure modes, not one:**
1. A revalidated-but-since-invalidated gate has no re-check clock (the original scar) — fixed
   by `gate_expiry_check.py`.
2. **A checker's own scope is itself a silent staleness surface.** `gate_expiry_check.py`
   correctly re-checks everything it knows about, but "everything it knows about" was fixed at
   build time to `GATE_ORDER` + 2 named vetoes + fleet config — a scope decision baked into
   `check_gate()`'s category dispatch and never revisited as the engine grew a scoring-filter
   layer, an extra-setup lane, and risk_gate config modes. An instrument that faithfully
   re-checks a stale SCOPE is not meaningfully better than no instrument for anything outside
   that scope. This is the general shape: **a monitoring instrument's coverage boundary rots
   exactly like the thing it monitors does, and nothing was watching the watcher's scope.**

## Fix

Built a second, complementary instrument rather than widening the first one's scope in place
(the first instrument's expensive real-OPRA-fills replay path is a poor fit for a cheap weekly
re-run of a broader, lighter check):
- `setup/scripts/gate_recency_report.py` — pure-stdlib, dependency-light, weekly. Reads the
  first instrument's own verdicts (never recomputes them) + does its own 15-trading-day
  block-count pass (raw ticks, no $ simulation) using the exact per-gate attribution rules the
  2026-08-08 audit documented, covering the scope gap directly (`GATE_ROSTER` includes the
  scoring-filter layer, extra-setup lane, and `pdt_gate_mode` explicitly, each labeled
  `expiry_verdict: "NOT_IN_EXPIRY_CHECKER"` rather than a silent/fake GREEN when the first
  instrument's scope doesn't reach them).
- `setup/scripts/install-gate-recency.ps1` — registers `Gamma_GateRecency`, Sundays 18:00 MT.
- `markdown/doctrine/GATE-RECENCY-DOCTRINE.md` — the instrument chain (stage 1 nightly P&L →
  stage 2 weekly recency report → stage 3 standup surfacing → stage 4 revalidation A/B → stage
  5 auto-ratify) + the rule: any gate RED for >7 days without a filed revalidation pre-reg is a
  doctrine violation to flag in standups.

## Encoded in

`markdown/doctrine/GATE-RECENCY-DOCTRINE.md` (full doctrine); `setup/scripts/gate_recency_report.py`
+ `backtest/tests/test_gate_recency_report.py` (the instrument + its guard, 54 tests green);
`setup/scripts/install-gate-recency.ps1` (the standing schedule, not yet installed — orchestrator
runs the install + registers it in `automation/state/SCHEDULED-TASKS.md`).

## L## (optional)

Next available slot per `LESSONS-LEARNED.md` is L283 (max found this session: L282,
2026-08-04). Candidate class: C7 (silent success is failure) + C34 (shared-surface staleness) —
this is a NEW sub-pattern within those classes ("a monitor's own coverage scope rots
independently of the thing it monitors") worth its own entry rather than folding into an
existing one, since the fix pattern (build a second cheap instrument reading the first one's
output, rather than widen the first one in place) is itself reusable.
