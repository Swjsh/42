# Lesson candidate: independence-vs-shipped-edge + no-regression-vs-parent — two gates that catch 9-gate-clean false promotions

> Queued by Gamma (all-night hunt B8) 2026-06-21. lesson-author picks up at next wake fire.

## Symptom
B8 produced two candidates that PASSED the full real-fills fraud bar yet were NOT new/better edges:
- **Anchored-VWAP A3** (prior-swing-anchored VWAP retest, ITM-2): cleared **all 9 fraud gates** (OOS +$59.23/tr, posQ 6/6, OOS-alone drop-top5 +$15.59, beats-null, no-truncation) — but **97.3% of its entry days overlap the already-LIVE #1 vwap_continuation.** It is the shipped edge wearing an anchored-VWAP costume, not independent alpha. Without an overlap check it would have been a false promotion.
- **Cumulative-delta USE1** (flow-proxy standalone): raw-cleared **9/9** — but it is a strict SUBSET of #1, and the 39 #1-days it skips are net-POSITIVE (+$693 Safe/+$695 Bold). The "selection" removes WINNERS → fails no-regression. USE2 (explicit confirm gate on #1) skipped a +$2,879/+$3,929 net-positive set. No novel flow alpha.
- Same family: the B8-C touch-and-go refinement "lifted" edge #2's headline OOS/tr (+$42.60) purely by concentration (OOS-alone drop-top5 −$36.51, dropped 14 net-winning days).

## Root cause
The 9-gate fraud bar verifies a candidate **in isolation** — it does not ask (a) is this signal **independent** of edges we already trade, or (b) does a gate/refinement **remove net-winners** (a relabel) rather than net-losers (real selection). A structural shape can re-detect an existing edge's days (high overlap) and pass every fraud gate; a filter can raise per-trade by cutting signals while throwing away winning days (concentration mirage, the L173 trap's sibling).

## Fix
- Added **independence-vs-shipped-edges (day-overlap < 0.80)** and **no-regression-for-any-gate/refinement (skipped/pruned days must be net-NEGATIVE)** to the canonical candidate gate-list in `markdown/research/STRATEGY-HUNT-BACKLOG.md`.
- `backtest/autoresearch/_b8_anchored_vwap.py` implements the day-overlap-vs-#1 independence gate; `_b8_cumdelta.py` + `_b8_entry_refine_2_4.py` implement the no-regression-vs-parent check.
- TODO (graduate to code assertion): fold both into `backtest/autoresearch/verify_edgehunt_candidates.py` + `backtest/tests/test_graduated_guards.py` so EVERY future candidate / refinement is auto-checked, not just documented.

## Encoded in
STRATEGY-HUNT-BACKLOG.md gate-list (documented); the three `_b8_*.py` harnesses (enforced for B8); pending graduation into `verify_edgehunt_candidates.py` + `test_graduated_guards.py`.

## L## (optional)
Suggested **L174** (confirm via grep for max). Fold into CLAUDE.md Lessons index — independence → theme **C4** (concentration/independence disclosure); no-regression → **C28/C29** (per-shape calibration doesn't transfer; gates that remove winners are relabels). Sibling to **L173** (OOS-alone drop-top5).
