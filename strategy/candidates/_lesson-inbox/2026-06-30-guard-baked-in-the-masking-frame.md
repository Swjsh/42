# Lesson candidate — a guard can bake in the very frame you later need to correct

**Date:** 2026-06-30 (conductor fire)
**Theme:** C7 (silent-success / audit-outputs) + L189 (persistently-RED masks orphans) corollary; frame-correction discipline

## Symptom
`self_check.check_engine_tradeability` flagged "ENGINE CANNOT ENTER" as BROKEN on ANY
trigger-fired-but-blocked SKIP, including `SKIP_ELITE_BULL_LEVEL_RECLAIM`. After the
2026-06-30 bull-unblock audit CLOSED that thread (block_elite_bull proven KEEP −$241 on the
fresh OPRA window; sequence_reclaim structurally coupled off; bull frontier DATA-GATED, not a
bug), that block became proven-correct behavior — yet the live self-check sat perpetually-RED
on it (386 ticks / 0 ENTER / 32x SKIP_ELITE_BULL), which is the exact L189 anti-pattern: a
real future "cannot enter" fault (an unexpected block, or the LIVE bear direction failing to
convert) would hide behind the always-on RED.

## Root cause (the new wrinkle beyond L189)
The **existing graduated guard** `test_self_check_flags_zero_entry_with_blocks` had ENCODED
the pre-correction frame: it fed 40x `SKIP_ELITE_BULL_LEVEL_RECLAIM` and asserted "CANNOT
ENTER" MUST flag. So the guard actively DEFENDED the masking behavior — a naive fix to the
monitor would RED that guard, and a careless engineer might "fix the test to pass" by keeping
the mask. A guard written against a frame that later gets corrected will FIGHT the correction.

## Fix
When you correct a monitor's/detector's FRAME, update its guard in the SAME commit to assert
the corrected behavior — do not treat the pre-existing guard as ground truth. Here: the guard
now proves (a) a NON-data-gated block still flags CANNOT ENTER (fault path intact, non-vacuous
bite), and (b) the all-`SKIP_ELITE_BULL` day is now SILENT (the data-gated fix). Scope the
benign set to a named, audited constant (`_DATA_GATED_BLOCK_VERDICTS`) so the suppression is
explicit and reviewable, and delegate edge-regression detection to the correct layer
(`test_bull_unblock_replay_probe.py`), not the liveness monitor.

## Guard
- `backtest/tests/test_self_check_tradeability.py` (8/8) — full matrix: benign-silent,
  real-block-flags, mixed-day, bear-side-flags, ENTER-clean, weekend-skip.
- `backtest/tests/test_graduated_guards.py::test_self_check_flags_zero_entry_with_blocks`
  frame-corrected to the same-day audit.

## Files
`setup/scripts/self_check.py` (+`_DATA_GATED_BLOCK_VERDICTS`, split real-vs-benign block +
bull-vs-bear high-conviction branches).
