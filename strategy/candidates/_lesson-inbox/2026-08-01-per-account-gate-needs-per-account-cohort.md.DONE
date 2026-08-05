---
date: 2026-08-01
severity: HIGH
class: C14 (dead/mistranslated knob) + C7 (silent success) + C4 (disclosure)
incident: block_elite_bull bold-2 lift-gate trial armed then reverted within one session
---

# A per-account gate needs a per-account cohort cell — and a sign-only verdict rule will pass on noise

## Symptom

On 2026-08-01 the `block_elite_bull` gate was disarmed on **bold-2** as a lift-gate trial
(commit `b6a9db67`), then re-blocked the same session (`711420f4`) when two independent
checks disconfirmed its basis within the hour.

## Root cause (two compounding defects)

**1. Cross-account misattribution.** The justifying figure — `+$867, n=5, drop-best +$177`
from `analysis/recommendations/elite-bull-requal-2026-07-31.json` — was **Safe's** blocked
cohort. The recommendation never computed a Bold-specific cell, yet the decision it drove
was a Bold-only config flip. `backtest/tools/bold_fullhist_replay.py` re-ran the identical
cohort at Bold's true sizing (`min_contracts=5`, ATM tier) and got **+$7.80, n=5,
drop-best −$535.00**. The number that looked like a mandate was a coin flip on one trade.

The structural reason it went unnoticed: until `efddde66` **every full-history replay tool
in the repo walked the SAFE shape**. Bold cells were either blind or silently Safe-shaped.
There was no way to compute a Bold cohort, so nobody did, and the Safe number stood in for it.

**2. A sign-only verdict rule.** The frozen verdict rule graded branch `'a'` on any positive
total. `$7.80 > 0` mechanically passed. A rule with no magnitude floor, no drop-best gate,
and no per-account scoping cannot distinguish an edge from rounding.

## What actually settled it

`backtest/tools/bull_gate_f5class_requal_2026_08_01.py`, pre-registered and run over the
full 391-day population (ATM strike, ribbon-BULL-stacked subclass): unblocking **adds n=103
trades at WR 18.45%, −$4,550.70 total, −$44.18/tr**; all four pre-registered gates fail;
drop-best worsens to −$5,428.70; the recent-25 window is **also** negative (−$74.45, n=11).

Crucially, backtest levels come from `lib.levels._detect_from_history`, **not** the live
`refresh_levels_intraday.py` / `key-levels.json` pipeline that carried the IEX/SIP bug. So
this cell is *not* broken-feed-contaminated — which is exactly the objection that voided the
gate's original 24-fill evidence. It answers the question the trial was built to answer.

## Fix / rule

- **A gate armed per-account requires a cohort cell computed for THAT account, at THAT
  account's sizing and strike tier.** Citing another account's cell is a disclosure failure
  even when the mechanism is shared.
- **Verdict rules need a magnitude floor and a drop-best gate**, not just a sign test.
  `total > 0` is not a verdict when n=5.
- **Before arming on a small-n cell, ask what the properly-powered version says.** Here the
  n=103 answer existed and was one study away.
- Related standing rule (OP-16): verify the sim's strike/sizing matches production **before**
  ratification. This incident is that rule failing on the sizing axis rather than the strike axis.

## Guard

`backtest/tests/test_bold_fullhist_replay.py` includes an end-to-end RED-proof: replaying a
real bold anchor at the correct `qty=5` passes tolerance; the same anchor at `qty=3` fails it.
That test is what makes a future Safe-shaped Bold number fail loudly instead of silently.

## Cross-refs

- `analysis/recommendations/bold-fullhist-replay-2026-08-01.json`
- `analysis/recommendations/bull-gate-f5class-requal-2026-08-01.json`
- `analysis/deep-research/BOLD-HARNESS-2026-08-01.md`
- `automation/state/gate-registry.json` → `block_elite_bull.trial` (status REVERTED, reason recorded)
