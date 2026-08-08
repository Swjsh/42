# Gate-Recency Doctrine

> **Principle (J, 2026-07-31, verbatim):** *"the same thing that worked on day 372 ago is not
> gonna work on day 162 ago."* Recency beats aggregate in a dynamic market. **Every armed gate
> carries a revalidation clock.** An unvalidated lock — a gate blocking entries on evidence
> nobody has re-checked — dies (gets flagged, then re-validated or retired), it does not sit
> there forever on the strength of the day it was ratified.

This doc is the permanent home for that principle. It replaces "someone remembers to re-run
the audit" with a chain of instruments that keeps running whether or not anyone remembers.

---

## The instrument chain

| Stage | What | Cadence | Output |
|---|---|---|---|
| 1. Nightly P&L check | `Gamma_GateExpiryCheck` → `backtest/autoresearch/gate_expiry_check.py` | Nightly, 23:00 MT | `automation/state/gate-registry-status.json` — RED/YELLOW/GREEN/STALE_UNVERIFIED per gate, real-OPRA-fills replay of every refused signal |
| 2. Weekly recency report | `Gamma_GateRecency` → `setup/scripts/gate_recency_report.py` | Weekly, Sun 18:00 MT | `automation/state/gate-recency-latest.json` — merges stage 1's verdicts with a fresh 15-trading-day block-count pass, **including the gates stage 1 structurally cannot see** (scoring-filter layer, extra-setup lane, risk_gate config modes) |
| 3. Standup / wants surfacing | Whatever reads `gate-recency-latest.json`'s `digest` (a future standup, `STATUS.md`, a wants-registry entry) | Whenever stage 2 writes | Human-visible, no gate revalidation is silent |
| 4. Revalidation A/B | A pre-registered shadow study on the refused cohort (OP-16's 4-gate bar: OOS_positive AND WF≥0.70 AND sub_window_stable AND anchor_no_regression) | Ad hoc, triggered by a REVALIDATE/RED row | `analysis/recommendations/{gate_id}-revalidation-*.json` |
| 5. Auto-ratify rail | OP-16's standing rule — J is a REVOKE gate, not a ratification gate | Any after-hours evening once stage 4 clears | Gate re-armed/relaxed/retired, evidence date refreshed in `gate-registry.json` |

Stage 1 and stage 2 are deliberately different instruments, not duplicates. Stage 1 does the
expensive part (real-OPRA-fills P&L replay via `lib.simulator_real.simulate_trade_real`) and
needs the backtest venv + pandas + the OPRA cache. Stage 2 is a cheap, dependency-light,
**pure-stdlib** overlay: it reads stage 1's already-computed verdicts rather than re-simulating
them, and adds the one thing stage 1's own scope excludes — raw block-tick counts (not $) for
gates outside `GATE_ORDER` + the two named vetoes + fleet config. Two cheap, independent checks
catch more than one expensive check re-run twice.

---

## Origin story: the 2026-08-08 audit (the worked example)

`analysis/recommendations/gate-recency-audit-2026-08-08.{md,json}` was a manual, one-shot
census run because J noticed the existing nightly instrument (stage 1 above) had a scope gap:
it only mines `backtest/lib/engine/gates.py`'s `GATE_ORDER` + `structure_veto_enabled` +
`free_model_veto` + fleet config — never the scoring-filter layer (`backtest/lib/filters.py`),
the extra-setup lane (`extra_setup_exec_armed`), or `risk_gate` config modes
(`pdt_gate_mode`). Three findings from that one-shot audit motivate stage 2 existing at all:

1. **`pdt_gate_mode=margin_pdt` (Bold) — the clearest dollar-quantified cost found.** A
   self-imposed legacy-PDT rule the paper broker doesn't even enforce, hard-blocking Bold on
   49 signals in 15 days — one blocked day alone was a +$1,465 book day Bold could not join.
   This lives entirely outside `gate-registry.json`'s scope; without stage 2, nobody re-checks
   it on a schedule.
2. **`structure_veto_enabled` (Safe) and `require_bearish_fill_bar` (Bold) — both independently
   RED per the nightly checker itself**, 43 and 52 days past their revalidation interval, on
   evidence that was thin even at inception (n=2 IS-only; Bold-only validation inherited
   globally by the fleet lane). These prove stage 1 can already SEE a problem — the gap was
   nobody was READING stage 1's output on a cadence, which stage 2 + stage 3 fix. **(Same
   evening, the RED verdict ITSELF was found to rest on an unsound replay engine and both gates
   were revalidated to DO_NOT_UNBLOCK — see "REPLAY SOUNDNESS" below. Point 2's structural
   lesson — stage 1 could already see a problem, nobody was reading it — stands unchanged; the
   specific $/tr figures do not.)**
3. **`filter_10_min_triggers_bull=2` (Safe, double Bold's own 1 and double bear's own floor) —
   the single largest volume-suppressor found**, 551 sole-blocked ticks in 15 days with zero
   dated evidence for the asymmetry itself. This is a scoring-filter-layer gate; it has no
   `gate-registry.json` row at all, so stage 1's nightly P&L check will never touch it. Stage
   2's `GATE_ROSTER` tracks it directly, with an audit-ported provenance fallback, precisely
   because the registry does not.

Re-running `gate_recency_report.py --dry-run` against live state on 2026-08-08 reproduced
findings 1 and 2 exactly (same two RED gates, same $/tr figures, since it reads stage 1's own
output) and surfaced finding 3 as the top WATCH line in the digest — proof the standing
instrument reproduces the one-off audit's load-bearing findings without a human re-running it.

---

## REPLAY SOUNDNESS — the same-evening correction (2026-08-08, shipped tonight, caught tonight, corrected tonight)

**The incident.** Hours after the passage above shipped, J asked *"why do we still have gates
blocking profitable trades?"* and ordered a pre-registered revalidation of the 3
most-money-costing gates the audit named
(`analysis/recommendations/prereg-gate-revalidation-2026-08-08.json` →
`GATE-REVALIDATION-RESULTS-2026-08-08.md`). That study's own soundness audit — done FIRST, per
the mission order, before any P&L was touched — found that `gate-registry-status.json`'s own
EV figures (the ones stage 2 had been quoting as fact in its digest, and the ones this doc's
worked example above cites) are produced by `backtest/lib/simulator_real.simulate_trade_real`,
which carries **two independently-documented, dated defects**, not a new finding invented for
the study:

1. **Exit-shape divergence** (2026-07-17 FRAME AUDIT) — the simulator reads exit knobs from
   `params.json`'s top-level keys, not the REAL `exit_manager` registration
   (`fleet/strategies.py#RIBBON_RIDE.exit.to_dict()`) both core accounts actually trade under.
   Measured: a live trade that ran to +$241 sim-replayed as a breakeven zero.
2. **Intrabar look-ahead** (2026-07-11, `BACKTESTING-PLAYBOOK.md` §2.12) — the profit-lock
   ratchet arms off the current bar's high, then checks that SAME bar's low against the
   just-armed stop. A documented C6 violation worth $46.32/tr on the cited cell — bigger than
   that cell's own recorded expectancy.

Swapping in the SOUND replay path (`backtest/lib/exit_manager_walk.walk_exit_manager`, which
ticks the actual production `exit_manager.plan_exit_actions` core) produced materially
different numbers on the exact two gates this doc had called RED: `structure_veto_enabled`
+$6.00/tr (not +$32.69/tr) and `require_bearish_fill_bar` +$47.37/tr (not +$22.96/tr) — and
**both still fail the pre-registered G-battery** (concentration risk / no OOS edge / not
significant). **Verdict: all 3 gates in that study stay DO_NOT_UNBLOCK.** Full detail:
`analysis/recommendations/GATE-REVALIDATION-RESULTS-2026-08-08.md`.

**The propagation problem this section exists to name.** The unsound EV figures had already
been quoted as fact in four places by the time this was caught, same evening: (a)
`gate-registry-status.json` itself, (b) `gate_recency_report.py`'s own digest line ("would have
EARNED $22.96/tr … COSTING money"), (c)
`analysis/recommendations/gate-recency-audit-2026-08-08.{md,json}`, and (d) this doctrine file's
own worked example above. That is an OP-33 (verify, don't claim) failure — a monitor quoting a
number as fact that it never verified the provenance of — and it was corrected the same
session it was caught, not left to rot. The correction blocks are marked in each of the four
files, not silently edited over (see each file's own dated CORRECTION block / commit).

**THE RULE (permanent, going forward):**

> **An EV claim may only drive a RED / "costing money" verdict if it was produced by the
> production exit core** (`exit_manager_walk.walk_exit_manager` / `exit_manager.plan_exit_actions`,
> or any future replacement that is itself broker-fill-faithfulness-tested against the live
> exit path). **An EV claim produced by `simulator_real.simulate_trade_real` — or by anything
> whose replay engine is missing/unstated — is PROVISIONAL.** Provisional EV may motivate
> opening a pre-registered revalidation (stage 4 of the instrument chain above); it may never,
> by itself, stand as the verdict.
>
> Practically, for `gate_recency_report.py`: it reads a per-gate soundness stamp
> (`replay_soundness` / `replay_engine`, wherever `gate_expiry_check.py` writes it) off
> `gate-registry-status.json` when present. A RED gate backed by a stamped-SOUND replay may
> still say "COSTING money." A RED gate that is stamped unsound, or simply carries no stamp at
> all (the schema before tonight, and the fail-open default), reads as **"RED (provisional — EV
> from an unsound/unstamped replay engine, needs a pre-registered revalidation)"** instead —
> weaker evidence, never stronger, fail-safe-open by construction.
>
> Separately: **any gate with a FILED revalidation scorecard**
> (`analysis/recommendations/gate-revalidation-*.json`) reports THAT verdict in the digest, not
> the raw registry EV, regardless of the registry's own (possibly still-stale) RED/GREEN
> reading. A settled `NOT-UNBLOCK-ELIGIBLE` gate does not keep screaming "costing money" in a
> standup after its own pre-registered study said otherwise.

This is a new, generalizable pattern, not just a one-gate fix — filed to the lesson inbox:
`strategy/candidates/_lesson-inbox/2026-08-08-monitor-inherited-an-unsound-engine.md`.

---

## The rule

**Any gate RED on `gate-recency-latest.json` for more than 7 days without a filed revalidation
pre-reg (stage 4 above) is a doctrine violation — flag it in the next standup / status
surface.** `gate_recency_report.py` itself has no memory of its own prior runs beyond what it
overwrites each week; the 7-day clock is enforced by whatever consumes `gate-recency-latest.json`
over time (comparing `reds[]` across two weekly runs, or a future dedicated check), not by the
report itself. The report's job is narrower and non-negotiable: **a RED verdict is never more
than one week stale on the surface that names it.**

A gate that goes RED and gets a pre-reg filed within 7 days is doctrine-compliant even while
the pre-reg runs — the rule punishes *silence*, not *revalidation in progress*.

---

## Design notes (for the next session touching this)

- `gate_recency_report.py`'s `recommendation` field is a **mechanical** default (same inputs →
  same output, every run) — it will sometimes read stricter than a human editorial pass would
  (e.g. it flags `block_level_rejection` REVALIDATE at 52 days stale + 1 block/15d, where the
  2026-08-08 audit's own prose called it "low urgency despite the age"). That divergence is
  intentional: a repeatable instrument should not silently import one-off editorial judgment
  calls as if they were mechanical facts. Read `recommendation` as "the rule says look", not
  "a human already decided this is urgent."
- The gate roster's per-account "which accounts to track" set is a **snapshot**, ported from
  the 2026-08-08 audit, not auto-derived from `params.json`. Live `setting` VALUES are read
  fresh each run (so displayed numbers/booleans self-correct as J re-tunes a gate); the
  tracked-account SET does not self-heal if J arms a currently-untracked account on one of
  these gates. A future generalization could auto-discover the account set from a naming
  convention; out of scope for this build (`gate-registry.json`'s own `accounts_armed` field
  has the identical limitation — it's hand-maintained, not live-derived, and stage 1 has never
  needed to fix that either).
- `min_entry_premium`, the scoring-filter layer, the extra-setup lane, and `pdt_gate_mode` all
  report `expiry_verdict: "NOT_IN_EXPIRY_CHECKER"` — this is not a bug, it is the coverage gap
  finding 1 and 3 above are named for, kept visible on purpose rather than papered over with a
  fake GREEN.
