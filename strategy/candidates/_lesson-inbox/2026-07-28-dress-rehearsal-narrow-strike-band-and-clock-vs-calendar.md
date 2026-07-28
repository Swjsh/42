# Lesson candidate — narrow static search windows false-negative on sparse chains; derive dates from the broker's own clock, never a separate calendar guess

**Filed:** 2026-07-28, conductor (AFTERHOURS) fire, commit `96cf82b4`.

## Symptom
`self_check.py` reported BROKEN off the real 2026-07-27T20:45:01 nightly `dress_rehearsal.py`
artifact: `check1_options_{safe,bold}` both RED with "no candidate <= $0.05 among 3 contracts
(closest close_price='0.08')" — the deep-OTM probe never reached order placement on either
account.

## Root cause #1 — a fixed-width search window silently starves on a sparse/lumpy chain
`_pick_deep_otm_put` queried strikes in a fixed `target-10` to `target` window. SPY's far-OTM
chain is not `$1`-spaced everywhere — at spot 738.85 the 5%-OTM window held only 3 strikes
(695/700/701), and that night all three happened to price a few cents above the $0.05 ceiling.
The query had no escalation path: one narrow miss = permanent RED, even though a slightly wider
net (strike 690 @ $0.05, just 12 points further) would have qualified instantly.

**General form:** any fixed-width filter/window over a real market chain (strikes, timestamps,
volume buckets) can legitimately have zero qualifying rows on a given night for reasons that
have nothing to do with the thing being tested — chain sparsity, temporary richness, etc. If the
FIRST failure mode is "give up and RED", every such night reads as a broken engine instead of a
narrow window. Fix pattern: escalate through widening bands before concluding "no candidate
exists", and log which band the eventual pick came from (traceable, not just green).

## Root cause #2 — a second, independently-computed "what day is it" drifted from the broker's own answer
`_next_trading_day` computed the next trading day via `calendar?start=today+1&end=...` — correct
ONLY when called after today's market close. Any off-schedule invocation before today's own open
(a manual verification run at 01:xx ET, or a scheduler retry landing at an unusual hour) skips
today entirely, and disagrees with `check3_sanity`'s own separate `/v2/clock` read of the SAME
underlying fact. Two code paths independently re-deriving "what date is relevant" from different
sources of truth is a drift bug waiting to happen — and it happened to bite while I was still
mid-fire verifying the FIRST fix.

**This is C11 (broker is source of truth) in a new shape:** not "verify flat before entry" but
"don't recompute a fact the broker already hands you authoritatively via a DIFFERENT endpoint
than the one you're about to cross-check it against." The fix: derive `next_day` from
`clock.next_open` directly (the same fact `check3_sanity` already reads), with the old
calendar-endpoint guess demoted to a fallback for when the clock call itself fails.

## Why this graduates
C11's existing lessons (L47,76,180,200,215,220,237) are all about broker-vs-cache or
broker-vs-broker READ disagreement at entry/flatten time. This is the same shape at a different
site — a nightly rehearsal script, not the live trading path — which is exactly the kind of
"prose that describes an invariant nobody encoded as code yet, until it recurs somewhere new"
OP-25 asks lesson-author to catch. Suggest folding into C11's index line as a new L# once
lesson-author assigns the number, rather than opening a new cluster — same mechanism class.

## Evidence
- `automation/state/dress-rehearsal.json` before/after (RED -> GREEN, both timestamps in the file
  history / STATUS.md 2026-07-28 ~01:16-01:30 ET entry).
- `backtest/tests/test_dress_rehearsal.py::TestDeepOtmBandWidening` +
  `::TestNextTradingDayUsesClock` (6 new guard tests, RED-proofed via scoped `git stash`).
- Commit `96cf82b4`.
