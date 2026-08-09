# Lesson candidate: a monitor silently inherited the soundness of whatever engine computed its numbers

> Queued 2026-08-08 (same session that shipped the bug, self-caught). lesson-author picks up at
> next wake fire.

## Symptom

The nightly gate-expiry instrument (`setup/scripts/gate_expiry_check.py` →
`automation/state/gate-registry-status.json`) computes "refused-cohort EV" for every armed gate
using `backtest/lib/simulator_real.py::simulate_trade_real`. That replay engine has TWO
independently-documented, dated defects already on file elsewhere in the repo, neither new:
exit-shape divergence from the live exit manager
(`analysis/recommendations/exit-manager-replay-2026-07-17.json`'s own docstring) and
same-bar/intrabar look-ahead (`BACKTESTING-PLAYBOOK.md` §2.12; the profit-lock
scope-mismatch appendix).

Nobody had connected those two known-defect citations to the fact that
`gate-registry-status.json`'s own headline EV numbers — quoted as fact — are produced by
exactly that engine. Same evening, the same-day one-off audit
(`analysis/recommendations/gate-recency-audit-2026-08-08.md`) cited two of those numbers
(`structure_veto_enabled` +$32.69/tr, `require_bearish_fill_bar` +$22.96/tr) as corroborating
"RED — costing money" evidence. The brand-new weekly instrument built off that audit
(`setup/scripts/gate_recency_report.py`, shipped same day, commit `31d5849f`) then quoted the
same figures verbatim in its own digest ("would have EARNED $22.96/tr … COSTING money"), and
`markdown/doctrine/GATE-RECENCY-DOCTRINE.md`'s worked example enshrined them as the doctrine's
own origin story. **Four separate files, one unverified number, propagating downstream into
what Gamma reports to J in a standup.**

A same-evening J-directed pre-registered revalidation
(`analysis/recommendations/prereg-gate-revalidation-2026-08-08.json` →
`GATE-REVALIDATION-RESULTS-2026-08-08.md`) did what nobody had done first: audited the reused
instrument's soundness BEFORE touching any P&L, found the forward-replay layer unsound (not the
mining/attribution layer, which was fine and reused verbatim), swapped in the sound production
exit core (`backtest/lib/exit_manager_walk.walk_exit_manager`), and got materially different
numbers on both gates — `structure_veto_enabled` +$6.00/tr (OOS half negative, drop-top-3
-$447) and `require_bearish_fill_bar` +$47.37/tr (one trade carries the whole cohort, p=0.468).
**Both still fail the pre-registered G-battery. Verdict: DO_NOT_UNBLOCK, unchanged — the
original "unblock this, it's costing money" read was itself wrong, just for a different reason
than the number being literally false.**

## Root cause

**A monitor silently inherits the soundness of whatever engine computes its numbers — a
monitor's own evidence chain needs a provenance stamp, or it launders unsound figures into
doctrine and into the operator's face.**

This is NOT "the simulator has a bug" (that was already known and documented in two other
files). The actual failure is structural: `gate_expiry_check.py` produces a number and a
verdict (`RED`/`GREEN`/`YELLOW`) with no machine-readable trace of WHICH replay engine produced
it. Every downstream consumer — a one-off audit, a weekly instrument, a doctrine worked
example — has no way to distinguish "this EV came from the sound production exit core" from
"this EV came from a simulator with two documented defects" without re-deriving the whole
lineage by hand each time. Absent that distinction, every consumer defaults to trusting the
number, because the number LOOKS like a verdict (a signed dollar figure, a RED/GREEN label) —
it reads as settled fact, not as an input with its own confidence tier.

This is the general shape, generalizable beyond this one instrument: **any pipeline stage that
emits a number derived from a swappable/replaceable computation engine must carry that engine's
identity forward as data, not just as a comment in the code that computed it** — otherwise every
consumer two or three hops downstream re-inherits whatever soundness (or lack of it) the origin
had, with no way to tell the difference, and no way to know when the origin's own soundness
later degrades (e.g. if a future engine swap makes today's SOUND numbers stale-but-still-marked-
sound, or vice versa).

## Fix

1. `automation/state/gate-registry-status.json`'s own rewrite (concurrent session, this
   evening) is adding a per-gate soundness stamp (`replay_soundness` / `replay_engine`).
2. `setup/scripts/gate_recency_report.py` (this session) now reads that stamp when present and
   defaults to **PROVISIONAL** — never "COSTING money" wording — when it is missing or marked
   unsound. Fail-safe-open: an unstamped number reads as WEAKER evidence, never stronger.
3. Separately, `gate_recency_report.py` now scans
   `analysis/recommendations/gate-revalidation-*.json` for a FILED settled verdict on the exact
   (params_key, account) pair and reports THAT instead of the raw registry EV whenever one
   exists — a settled `DO_NOT_UNBLOCK` gate never keeps screaming "costing money" in a standup
   after its own pre-registered study said otherwise.
4. `markdown/doctrine/GATE-RECENCY-DOCTRINE.md` now carries a permanent **REPLAY SOUNDNESS**
   rule: an EV claim may only drive a RED/"costing money" verdict if produced by the production
   exit core; anything else is provisional and may only motivate opening a revalidation, never
   stand as the verdict itself.
5. `analysis/recommendations/gate-recency-audit-2026-08-08.{md,json}` were corrected same
   evening with dated CORRECTION blocks — original numbers preserved, marked superseded, never
   silently edited over.

## Encoded in

`markdown/doctrine/GATE-RECENCY-DOCTRINE.md` (REPLAY SOUNDNESS rule + incident write-up);
`setup/scripts/gate_recency_report.py` + `backtest/tests/test_gate_recency_report.py`
(provenance-aware digest wording, settled-revalidation suppression, backward compat, fail-open
tests); `analysis/recommendations/gate-recency-audit-2026-08-08.{md,json}` (dated corrections,
originals preserved).

## L## (optional)

Next available slot per `LESSONS-LEARNED.md` is L283 — but
`strategy/candidates/_lesson-inbox/2026-08-08-gate-recency-instrument-graduation.md` (filed
earlier the same day, the instrument's own graduation lesson) already claims L283. lesson-author
should assign the next free number (likely L284) at pickup; this lesson is a direct sequel to
that one (same instrument, same day, the correction to what it shipped a few hours later) and
should probably cross-reference it rather than stand fully independent. Candidate class: C7
(silent success is failure) + C14 (dead/translated-but-unapplied knobs, in the sense that a
soundness distinction existed in the codebase's own dated docs but was never wired forward as
data) — this is a new sub-pattern ("a monitor's numeric output needs its own provenance stamp,
or every downstream consumer re-inherits whatever soundness the origin had, sight unseen").

## Filed by

Repairer B, 2026-08-08 evening, same session that corrected the downstream artifacts.
