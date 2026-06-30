# Lesson candidate: OOS-alone drop-top5 — full-sample drop-top5 is necessary-but-not-sufficient

> Queued by Gamma (all-night hunt) 2026-06-21. lesson-author picks up at next wake fire.

## Symptom
B5 declared a NEW futures edge (MES→MNQ divergence, persistence≥2): "8/8 gates, OOS +$71.46/tr, **drop-top5 +$3.65**." The ship-review then found the gate-5 +$3.65 was computed over the **FULL IS+OOS sample**; on the **OOS-alone window (n=41)** drop-top5 = **−$16.36** and top5-day = **120.1%** — i.e. remove the 5 best OOS days and the OOS edge goes NEGATIVE. B6 then STACKED vol-regime ATR-band + persistence and swept n∈{2,3,4} across 72 cells: **zero** cleared OOS-alone drop-top5>0; every cell was negative OOS-alone (best −$23.01); more persistence made OOS concentration monotonically WORSE (N2 −$23 → N3 −$52 → N4 −$59; top5-day_OOS 136.6% → 228.3%). Edge #3 was a 2026-bull-regime concentration artifact (C22) that the full-sample concentration gate passed.

## Root cause
The standard drop-top5 (gate-5) is computed over the **whole sample**. A signal can de-concentrate the full sample (IS days dilute the metric) while its **OOS profit still lives entirely in a handful of OOS days**. Because OOS is the only honest forward proxy, OOS-alone concentration is the metric that matters — and it can be negative while full-sample is positive. Full-sample drop-top5 is **necessary-but-not-sufficient**. Mechanism is the C22 family (backward-looking / regime-fit edges concentrate in the favorable regime's best days) crossed with C4/L04 (disclose concentration; normalize OOS).

## Fix
- Added **OOS-ALONE-drop-top5>0** to the canonical candidate gate-list in `markdown/research/STRATEGY-HUNT-BACKLOG.md` (every batch now requires it).
- B6 harness `backtest/autoresearch/_b6_div_stack.py` computes drop-top5 on BOTH the full sample AND the OOS-alone window for every cell and gates on the OOS-alone value.
- TODO (graduate to code assertion): add an `oos_drop_top5 > 0` check to the standard verify path (`backtest/autoresearch/verify_edgehunt_candidates.py` gate dict) and the B-campaign `eval_cell` so it is auto-enforced, not just documented — per "a lesson re-violated is a missing guardrail → graduate it" (`backtest/tests/test_graduated_guards.py`).

## Encoded in
STRATEGY-HUNT-BACKLOG.md gate-list (documented); `_b6_div_stack.py` (enforced for the divergence family); pending graduation into `verify_edgehunt_candidates.py` + `test_graduated_guards.py` for ALL candidates.

## L## (optional)
Suggested **L173** (greps for max should confirm — index was through L172 as of 2026-06-20). Fold into CLAUDE.md Lessons index theme **C4** (disclose concentration / normalize OOS) and/or **C22** (regime-fit artifacts).
