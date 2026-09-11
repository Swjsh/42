# GOAL: WHY-THIS-WEEK-2026-09-10

> **Opened by J directive, 2026-09-10 ~22:50 ET** (verbatim: *"make sure gamma has this audit
> front and center on its to do list figuring out why this week has been awful and how ti
> improve it i wnt you working all night"*). This is the TOP of the ladder until it closes.
>
> **The trigger — a full audit run this session, broker-verified:**
> - **This week: −$906, 0 wins in 7 trades.** Tue 09-08 −$116 (2 trades, 0W) · Wed 09-09 **$0
>   on 5 ENTER verdicts and 0 fills** · Thu 09-10 −$790 (5 trades, 0W). Mon 09-07 holiday.
> - **Today all five fills were `BEARISH_REJECTION_RIDE_THE_RIBBON`. All five lost.**
> - **safe-2 was the only arm that did not lose** (−$0.07): its structure-veto refused 7 bear
>   entries with *"P entry blocked — price structure is 'uptrend' (wrong-way entry)"*. The
>   three arms that took those bear trades lost $790 between them.
> - **Concentration:** book is +$2,027 over 42 days as-traded but **−$792 ex-best-day**
>   (PF 0.924). At 2-week scale +$2,323 since 08-24 is entirely 08-27 (+$1,897) and 08-28
>   (+$1,304); every other day nets −$878.
> - **safe-2 — the flagship conservative arm — is net NEGATIVE over 32 days:** PF 0.817,
>   −$654 as-traded; ex-best-day PF 0.631, −$1,316. safe-3 (PF 1.514, +$1,233) is carrying
>   the entire book.
> - **Go-live gate RED**, no arm passing; closest is safe-3 at distance 0.657.
> - **47 task-freshness findings** (31 `missing_launch`, 11 `output_stale`) — and the dark
>   producers include `Gamma_TradeAutopsy`, `Gamma_ZeroEnterAutopsy`, `Gamma_RegimeAttribution`,
>   `Gamma_DayTypeLabels`, `Gamma_RightTailCapture`, `Gamma_FleetGateLeakShadow`,
>   `Gamma_StructureClassifierShadow` — i.e. **precisely the instruments that would explain
>   this week.** A week cannot be diagnosed with its diagnostic layer dark.
>
> **The honest framing this goal must hold:** a low-WR right-tail engine is *supposed* to have
> losing weeks. The question is NOT "we lost, what do we change" — that is the revenge-trade
> reflex in research clothing (L168/C31). The question is **"is this week inside the engine's
> known distribution, or is a mechanism broken?"** Those two answers lead to opposite actions
> and the goal is not done until one of them is evidenced.

## DONE-WHEN

**(W1) The diagnostic layer is LIT.** Every dark producer whose output is load-bearing for
W2–W5 is either (a) running and producing fresh output — quote the file + timestamp — or
(b) named with a one-sentence root cause for why it cannot run, filed to STATUS.md. Do not
proceed to a verdict on a week using instruments you have not confirmed are alive (OP-33,
"built ≠ running"). `missing_launch` findings that are merely never-installed launchers are
cheap; fix them. This is an observability fix, **not** a trading-path edit — freeze-safe.

**(W2) The 09-09 hole is root-caused in one sentence.** 5 ENTER verdicts → 0 orders accepted
→ 0 fills, confirmed genuine (equity deltas reconcile to ~$0 on both core accounts, checked
this session — it is NOT an accounting gap). Either name the mechanism that swallowed those
five entries and ship a RED-proofed guard, or prove the enters were correctly refused
downstream and say which gate did it. **If this is a live execution defect it is the single
most expensive finding in the audit** — it eats trades AND eats the sample the go-live gate
is counting. State which.

**(W3) A verdict on `BEARISH_REJECTION` + the structure-veto, with numbers.** Today's tape is
one clean natural experiment: the arm carrying the structure-veto refused the setup; the arms
without it took it and lost. Measure across the whole frozen window, wave-deduped, NOT just
today (n=1 is an anecdote — L140/C24: a one-off exceptional day does not generalize):
per-arm net $ of bear entries the structure-veto would have refused, split by whether price
structure was up/down/chop. Verdict is one of: **EARNING** (veto pays → pre-register
extending it to bold-2/safe-3/risky-1 as a 09-29 kill-type RISK REDUCTION), **COSTING** (veto
refuses net winners → leave it, say so), or **UNDERPOWERED** (say n and stop). A gate may be
found EARNING — that is a real outcome, not a failure.

**(W4) This week placed inside or outside the engine's known distribution.** Using the
bootstrap machinery already in `go_live_gate.py`: what is the probability of a ≥7-trade, 0-win,
−$906 stretch under the engine's own as-traded daily return distribution? If this week is
inside the 90% band → **the week is variance, the correct action is no action**, and the goal
says so in those words. If it is outside → name the regime or mechanism that changed, with the
day-type/VIX-character evidence (C5: VIX *character* > VIX level). **Answer this BEFORE
proposing any change** — W4 gates W5.

**(W5) A ranked improvement set — pre-registered, never shipped tonight.** Every candidate
carries: mechanism in one sentence · the measurement that would kill it · a guard test ·
a revert line · and its checkpoint date (**09-29 for kill-type RISK REDUCTIONS, 10-30 for
anything that expands risk or adds/loosens an entry path**). Ranked by expected $ recovered
with the error bar stated. **If W4 returns "variance", the honest ranked set may legitimately
be empty or reduction-only — do not manufacture changes to look productive** (OP-22: "good
enough" is a valid terminal state; a logged null IS the deliverable).

**(W6) safe-2's 32-day negative gets its own named mechanism.** It is the conservative
flagship and it is net −$654 while safe-3 is +$1,233 on the same signal. The arms differ ONLY
by sizing/gates/stop (they are risk profiles, not strategies). Name which specific
gate/sizing/stop difference accounts for the spread, in dollars. If the answer is "safe-2's
ATM strike tier vs safe-3's tight ladder", quantify it — C29 says exit knobs ratified on one
strike tier do not transfer to another.

## OPERATING RULES

- **⛔ CONFIG FREEZE 2026-08-31 → 2026-10-30 is ABSOLUTE HERE.** This goal exists because the
  book is losing; that is exactly the pressure the freeze was built to resist. **No
  trading-path edit ships from this goal, tonight or any night.** Findings become
  pre-registered checkpoint packages (09-29 reductions / 10-30 expansions), each with prereg,
  guard, RED-proof and revert line. A provably-return-identical edit to a frozen file is
  **still barred** — the freeze protects the SCORE, not just behaviour.
- **Observability work is NOT frozen.** Lighting dark producers, fixing launchers, and writing
  shadow ledgers are freeze-safe and are W1's whole point. Verify each against
  `setup/hooks/doctrine.py` `FROZEN_TRADING_PATH` before staging anyway.
- **No revenge research.** A losing week is not evidence a gate is wrong. Every proposed change
  must survive the question "would I have proposed this last Friday when we were +$2,323?"
  If not, it is drawdown-chasing — kill it and say so.
- Every fire: `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n>
  --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent`/`Workflow` fan-out passes `model:"sonnet"` explicitly. No task chips.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire. Workers never edit STATUS.md
  or commit — the orchestrator does.
- Every timestamp read from `python setup/scripts/et_clock.py` **in the same call**, never typed.
- Every fix ships with a RED-proofed test (fails on pre-fix code) + a one-sentence root cause.
- **Verify, don't claim:** every DONE item quotes the command output that proves it. A result
  that looks great gets `/fable-too-good` before it gets reported.
- ⛔ **Paper-key rotation is CLOSED by J directive (2026-09-10) — it is not an item here or
  anywhere. Do not re-raise it.**

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J

- [x] W1 -- **CLOSED: 10 of 11 producers were ALREADY LIT** (fresh same-day output, 14:00-16:00
      ET timestamps quoted). 1 genuinely broken (Gamma_RefusedSetupLedger) -> fixed + verified.
      2 real residual defects named (below). The '47 findings' headline was largely artifact.
- [x] W2 -- **CLOSED: correct refusal, NOT a defect.** All 5 bold-2 enters hit the validated
      `min_entry_premium` floor (761P priced $0.11-$0.18 vs the $0.30 floor); safe refused the
      same setup 5x on structure-veto. No order was ever submitted. Guard green this session
      (`test_min_entry_premium_floor.py` 11 passed). Not unique, not new, no silent-swallow
      pattern anywhere 08-24 onward. Null fix -- nothing shipped.
- [x] W3 -- **UNDERPOWERED, leaning COSTING. Logged null, no package.** n=7 veto waves, only 2
      with matching real fills. With 09-10: +$102. WITHOUT 09-10: **+$832 COSTING**. Also:
      the veto is NOT wired into the fleet arms at all -- extending it is architecture work.
- [x] W4 -- **VERDICT: VARIANCE, not regime-break.** Done 2026-09-10 23:03:47 Thursday EDT. Numbers below.
- [x] W5 -- **DONE: reduction-only / measurement-only set. See W5 RESULT.** Original text:
      the lever is **PARTICIPATION, not gates**. Do not propose loosening anything to 'win
      more' -- the WR is normal. Investigate why waves/day fell 4.30 (Aug) -> 2.83 (frozen
      window) and whether that decline is (a) market conditions, (b) a gate/config change,
      or (c) silent execution loss (see W2). Only (b)/(c) are actionable, and only as
      pre-registered 09-29/10-30 packages.
- [x] W6 -- **CLOSED (diagnosis phase). Reconciled: the GATE was right, safe-2 IS net negative in engine terms
      (-$675 over 95 engine trips). My +$1,117 ledger figure was inflated by 12 PRE-ENGINE
      April-June legs worth +$1,587. Mechanism = SELECTION, not sizing/strike/exit.**

## PROGRESS LOG

- 2026-09-10 22:5x ET -- OPENED by J directive off this session's full audit. Ladder entry
  inserted at the top of the queued block; active-goal.json repointed here.
  GOAL-FULL-SUITE-RED-TRIAGE-2026-09-10 flipped `[~]` -> `[ ]` with its T4 (final full-suite
  re-run) still genuinely open -- it was NOT closed, and the autopilot will reopen it in order
  once this goal terminates.


---

## W4 RESULT -- variance-vs-mechanism verdict (orchestrator, 2026-09-10 23:03:47 Thursday EDT)

**VERDICT: VARIANCE. This week is inside the engine's known distribution. The correct action
on the P&L itself is NO ACTION.**

### The unit error that made the week look worse than it is
Wave-deduped (10-minute bucket = one market event; multiple arms on the same signal are ONE
event, not N samples), this week was **4 losing waves, not 7 losing trades**:

| date | wave | legs | net |
|---|---|---:|---:|
| 2026-09-08 | 11:0x | 1 | −$95 |
| 2026-09-08 | 13:3x | 1 | −$21 |
| 2026-09-10 | 12:1x | 4 | −$730 |
| 2026-09-10 | 14:3x | 1 | −$60 |

Reporting "0 for 7" counts three arms taking the SAME 12:1x signal as three independent
losses. The honest line is **0 for 4**.

### Placed against the engine's own base rate (600 legs / 60 trading days)
- Engine WR = **33.7%**. `P(0 wins in 4 waves) = 0.663^4 = 19.3%` -- **roughly a 1-in-5 week.**
  (The naive 7-leg framing gives 5.6% and is the wrong unit.)
- Dollars: `P(2 consecutive trading days <= -$906)` = **10.1%** (adjacent-block bootstrap,
  200k draws) / 16.2% (iid). **Actual history: 6 of 59 adjacent 2-day windows (10.2%) were
  this bad or worse** -- the bootstrap and the realised history agree, which is the check
  that matters.
- **The engine loses on 60% of its days (36/60). Median day = −$83.50, mean day = +$47.80,
  sd = $930.** That is the validated right-tail shape, not a malfunction: it is *supposed* to
  bleed most days and pay on few. Worst historical day −$2,687; best +$3,624.

### Recency check (J's standing rule: recency > aggregate) -- NO decay signal
Rolling 60-leg WR: 33.3% → 46.7% → 38.3% → 58.3% → **31.7% (current)**. The current window is
at the LOW end but **inside** the observed band, and a 33.3% window previously produced
−$1,909 without anything being broken. Monthly WR is wildly regime-dependent (Jun 5.3%,
Jul 20.5%, Aug 44.7%, Sep 31.2%), so the 33.7% aggregate is a blend -- but the current window
is not an outlier against it. **The base rate has not decayed; this week does not need a
mechanism to explain it.**

### ~~The REAL finding -- participation, not win rate~~ **STRUCK BY W9 (see below)**
The engine's edge is a right tail. A right tail needs at-bats. **At-bats are down a third:**

| window | waves/day | days |
|---|---:|---:|
| all-time | 3.07 | 60 |
| **August (pre-freeze, best month: +$3,564)** | **4.30** | 20 |
| **frozen window (09-01 →)** | **2.83** | 6 |

**−34% participation vs the month the engine actually made money.** 2026-09-09 made it worse:
**5 ENTER verdicts → 0 fills** (W2). Today's funnel narrowed 772 ticks → 26 signals → 8 ENTER
→ 4 attempted → 3 filled.

⚠️ **PROVISIONAL, n=6 frozen-window days vs 20 August days.** This is a hypothesis with a
real number attached, NOT an established finding -- it must survive W1's lit instruments and
W2's root cause before it drives any package. Do not act on it yet.

### Why this is not drawdown-chasing
The freeze-test: *would I have proposed this last Friday at +$2,323?* **Yes** -- the
participation decline is visible in August's own data and predates this week entirely. It is
not a reaction to the loss. By contrast, any proposal to loosen a gate "because we lost" fails
that test and is killed on sight (L168/C31).

### What this means for the rest of the goal
1. **W2 is promoted to the most important open item.** If enters are being silently eaten,
   we are starving the right tail -- that costs far more than any gate setting.
2. **W3's structure-veto question stands on its own merits** and must NOT be resolved by
   "this week was bad". W4 says the week needs no explaining.
3. **W5 must not propose loosening anything to raise WR.** The WR is normal. The lever is
   at-bats.


---

## W6 PARTIAL -- safe-2 vs safe-3 (orchestrator, 2026-09-10 23:06:27 Thursday EDT)

### What I set out to price
The audit headline said safe-2 is net **−$654** (PF 0.817) over 32 days while safe-3 is
**+$1,233** (PF 1.514) over 28 days on the same signal -- and since the arms differ ONLY by
sizing/gates/stop, some specific mechanical difference should account for it.

### Finding 1 -- on shared signals the two arms are near-identical
The clean test is waves where BOTH arms entered (same 10-min bucket = same market event),
which holds selection constant and isolates sizing/strike/exit. **n = 25 shared waves:**

- safe-2 **+$132** · safe-3 **+$272** · spread **+$140 total across 25 waves**
- The spread is dominated by 3 outliers: 08-07 b72 (−$305 vs safe-2), 09-03 b58 (−$126 vs
  safe-2), 08-27 b58 (+$147 to safe-3). Strip those and the arms are a coin-flip apart.
- Strikes are usually IDENTICAL on shared waves (K763/K769/K772/K777/K778 all match); entry
  premiums differ by pennies. The "safe-2 ATM vs safe-3 tight-ladder" hypothesis does **not**
  show up on common trades at all.

**Verdict on the mechanism question: UNDERPOWERED / mechanics-not-implicated.** Whatever
separates these arms in the gate's numbers, it is **not** how they size, strike or exit the
same signal. The divergence lives in **selection** (safe-2 solo: 70 waves +$985; safe-3 solo:
42 waves +$681) and in the differing measurement windows.

### Finding 2 -- ⚠️ a measurement discrepancy I could NOT reconcile, and it undercuts my own audit headline
Counting the full trade ledger:

| arm | ledger legs | ledger net | gate says |
|---|---:|---:|---|
| safe-2 | 148 | **+$1,117** | **−$654** (94 engine trades, 32 days) |
| safe-3 | 91 | +$953 | +$1,233 (67 engine trades, 28 days) |

**safe-2 is net POSITIVE on the full ledger and net NEGATIVE in the gate's window.** These are
different populations (gate counts engine-attributed trades over its own scoring window; the
ledger includes backfilled/manual/other-window rows) so the two are not contradictory on their
face -- but **I could not reproduce the gate's −$654 from the ledger this fire**, and my
attribution filter returned 0 engine-tagged rows for every arm, meaning the `attribution`
field is not where I assumed it is.

**Consequence -- correcting my own audit:** the statement *"safe-2, the flagship conservative
arm, is net negative over 32 days"* is the **gate's** number for the **gate's** window and
population. It should NOT be repeated as "safe-2 is the losing arm" until the reconciliation
below lands. A too-bad-to-be-true number gets the same artifact hunt as a too-good one.

### Blocking item for the next fire (W6 continuation)
Reconcile ledger↔gate for safe-2: find where `go_live_gate.py` sources `n_engine_trades`,
reproduce the −$654 exactly, and state in one sentence what the ledger's extra 54 legs /
+$1,771 are (window, attribution, or double-count). **Until that reconciles, no per-arm
conclusion and no per-arm package.**

### Bonus, feeding W5 (from W2's exec-status census, 08-24 onward)
`NOT_FLAT` is the single largest consumer of ENTER verdicts -- 09-03: 43 of 81; 08-27: 29 of
40. That is the one-position-at-a-time cap eating at-bats on exactly the high-signal days, and
it is a **structural participation limiter, not a loss mechanism**. This is now the strongest
lead for W5's "why are at-bats down" question. `RISK_DENY_SETTLEMENT` (12 on 09-03) is a
second, smaller one. Both are measurement-only tonight -- freeze holds.

## PROGRESS LOG

- 2026-09-10 23:06:27 Thursday EDT -- W2 CLOSED by Sonnet worker (correct refusal, null fix, guard green).
  W4 CLOSED (VARIANCE). W6 PARTIAL: shared-wave mechanics ruled out (n=25); blocked on a
  ledger-vs-gate reconciliation that also forces a correction to the audit's safe-2 headline.
  W1/W3 workers still running. Nothing shipped to the trading path; freeze intact.


---

## W1 RESULT -- the diagnostic layer was mostly already lit (2026-09-10 23:07:31 Thursday EDT)

### ⚠️ CORRECTION to this goal's own opening premise
The goal header says *"47 task-freshness findings ... precisely the instruments that would
explain this week are dark."* **That was overstated.** Checked directly:

**10 of the 11 load-bearing producers were already producing fresh same-day output**, with
14:00–16:00 ET timestamps today: `trade-autopsy-last.json` (16:20, `net_pnl: -790.0` — matches
Thursday's known loss), `ZERO-ENTER-2026-09-10.json` (14:10, 24KB), `day-type-labels.json`
(15:20, 63KB), `CAPTURE-2026-09-10.json` (14:20), `fleet-gate-leak-summary.json` (15:50, 43KB),
`structure-classifier-shadow-summary.json` (15:55), `conviction-c4-sidecar-summary.json`
(15:40), `entry-location-trend-summary.json` (15:30, 66KB), `self-audit/new-gaps-flagged.md`
(15:32, 203KB).

Two separate artifacts inflated the headline:
1. The `Disabled` state visible on all 11 tonight is the **documented 18:00–23:00 ET quiet-mode
   hold**, which self-resolved on schedule (`Gamma_QuietMode --status` → `quiet_active: false,
   restored_count: 140/140, updated_at: 2026-09-10T23:02:08 ET`). Not breakage.
2. The freshness scan that produced the 47 findings runs at **05:45 ET — before the day's
   producer fires** — so it flags same-day staleness that the day then resolves.

**The diagnostic layer was not the reason this week was hard to explain.** Recorded so the
next session does not re-chase it.

### Real defects found (2) -- both are C7 "silent success is failure"
1. **`Gamma_RefusedSetupLedger` was genuinely dark** — `analysis/refusals/` did not exist. Its
   14:20 ET fire logged `launching:` → `exit=0` in 8 seconds having written nothing, while the
   same command run interactively took much longer (network bar-fetches) and wrote correctly.
   **FIXED by direct run** (never by firing the task — J's standing rule): `refused_setup_ledger.py
   --backfill 1 --fetch --score` → `2026-09-10: 37 episode(s)`, plus `2026-09-09.json` backfilled.
   Exact mechanism of the fast no-op **NOT pinned** (suspected fetch stall / early return under
   the hidden-pythonw launch context, which the code does not log). **Deliberately not
   guess-fixed.** → Watch tomorrow's 14:20 fire; if it silently no-ops again, that is the guard
   to write. UNVERIFIED as permanently fixed.
2. **`Gamma_TradeAutopsy`'s `exit_shape_parity_study` is silently blind** — `HTTP 403 Forbidden`
   on option-bar fetches for dates as old as 09-02 / 09-03 / 09-08, contradicting
   `refused_setup_ledger.py`'s docstring claim that historical bars are not OPRA-gated. **The
   task still exits 0**, so Task Scheduler reads green while the component is dark on multiple
   recent dates. Root cause unconfirmed (vendor key / rate-limit vs a genuine same-day-only
   gate). **This matters to W6**, which needs clean per-trade bar pricing.

### Effect on the rest of the goal
- **W3 fully unblocked** — `structure-classifier-shadow-summary.json` is fresh and populated.
- **W6 has fresh data** (trade-autopsy, entry-location-trend, conviction-c4-sidecar,
  fleet-gate-leak) **but inherits defect #2's pricing blindness** — factor it into the
  ledger-vs-gate reconciliation rather than assuming clean bars.
- **W4 does NOT depend on the UNTAGGED regime attribution.** W1 flags `regime-attribution.json`
  as `"status": "UNTAGGED" ... "2026-09-10 is not in the archetype library"`. W4's verdict was
  derived from the engine's own realised daily P&L distribution and its realised 2-day windows,
  **not** from archetype tags, so the verdict stands as written. The regime *cross-check*
  (is this week's tape a known losing archetype?) remains unavailable until
  `backtest/tools/build_day_archetypes.py` is rebuilt — that is a nice-to-have, not a blocker,
  and it is explicitly NOT a reason to reopen W4.

## PROGRESS LOG

- 2026-09-10 23:07:31 Thursday EDT -- W1 CLOSED. Corrected this goal's own '47 dark instruments' premise:
  10/11 were already lit; 1 fixed (RefusedSetupLedger, mechanism unpinned, flagged for
  tomorrow's fire); 2 real silent-degradation defects named. W3 unblocked. W4 confirmed
  independent of the UNTAGGED regime data. No trading-path edits; freeze intact.


---

## W3 RESULT -- structure-veto x BEARISH_REJECTION: LOGGED NULL (2026-09-10 23:10:28 Thursday EDT)

**VERDICT: UNDERPOWERED, and what signal exists leans COSTING. No 09-29 package proposed.**

### This kills the hypothesis the audit raised
The audit observed *"safe-2's structure-veto refused exactly the trades the other arms lost
$790 on."* Tested properly it does not survive:

- 48 raw `SKIP_STRUCTURE_VETO` ticks -> **7 waves**; only **2** have matching real fills.
  - **2026-09-03** (BULL / downtrend): bold +85, safe-3 +433, risky-1 +314 = **+$832** -- the
    veto would have blocked real **winners**.
  - **2026-09-10** (BEAR / uptrend): -$730 -- veto would have saved losers. **This is the
    anecdote itself, n=1.**
- **With 09-10: +$102. Without 09-10: +$832 -- drop the day that suggested the idea and there
  is no EARNING story left at all.** A wider 5-week lookback sums to -$726 but is dominated by
  two outlier waves; the sign flips across window boundaries = textbook underpowered.

**Artifact hunt clean**: no look-ahead (bars <= trigger bar, code-verified), no wave
double-counting (qty-split rows confirmed single round trips). Revenge-research check: **the
09-03 COSTING wave sat in the same data a week ago and nobody flagged it** -- the gate was only
noticed on the day it happened to pay.

### Architecture finding
- `safe-2`: veto **ON** (`automation/state/params.json:314`, `engine_cli.py:626-646`).
- `bold-2`: veto **explicitly OFF** since 2026-08-12 -- config difference only.
- `safe-3`/`risky-1`/`risky-3`: separate execution path (`fleet_rest` via
  `build_shared_signal.py`) that **never calls `engine_cli.decide_payload`** -- the gate is not
  wired there at all. safe-3 inherits safe-2's refusal only indirectly via shared-signal (and
  on 09-10 it leaked through and lost $280 anyway).
- **So "extend the veto to the other arms" was never a param flip -- it is architecture work.**

---

## W5 RESULT -- the ranked improvement set (2026-09-10 23:10:28 Thursday EDT)

**W4 = VARIANCE, W2 = no-defect, W3 = null. Per this goal's own DONE-WHEN the honest set is
therefore reduction-/measurement-only. Nothing proposes loosening a gate, adding an entry
path, or changing size. Nothing ships tonight.**

### KILLED outright (recorded so they are not re-proposed)
- **Extend structure-veto to the other arms** -- W3 null, leans COSTING, and it is architecture
  not config. Do not revisit without a genuinely new window.
- **Any gate loosening to "win more"** -- W4: the win rate is normal (rolling 31.7%, inside the
  31.7-58.3% band). No WR problem exists to fix. Fails the last-Friday test.
- **Any sizing change in response to this week** -- L168/C31: the killer in J's 667 real trades
  was sizing-UP and adding, not flat count.

### RANK 1 -- measure what NOT_FLAT costs (measurement only; 10-30 at best)
**Mechanism:** the one-position-at-a-time cap refuses ENTER verdicts on the highest-signal days
-- **43 of 81 on 09-03, 29 of 40 on 08-27**. A right-tail engine starved of at-bats cannot
express its edge; at-bats are down ~34% (Aug 4.30 waves/day -> frozen 2.83, **PROVISIONAL n=6**).
**The measurement that would kill it:** for every wave NOT_FLAT blocked, price what that wave
subsequently did under the arm's own strike/exit rules. If blocked waves are net **losers**, the
cap is EARNING and the thread dies -- a real possible outcome, since the cap also prevents
stacking into a bad session.
**Why NOT a 09-29 item:** raising concurrency is a **risk EXPANSION** -> 10-30 regardless of
what the measurement says. Tonight's deliverable is the shadow ledger, not a change.

### RANK 2 -- the two silent-degradation defects (freeze-safe, ship anytime)
Both C7 "silent success is failure", both exit 0 while blind:
1. `Gamma_RefusedSetupLedger` 8-second no-op fire -- **mechanism unpinned**; watch tomorrow's
   14:20 fire, then write the guard. Do not guess-fix.
2. `Gamma_TradeAutopsy` `exit_shape_parity_study` 403-blind on historical bars back to 09-02
   while the task reports green.

### RANK 3 -- reconcile ledger vs gate for safe-2 (blocks all per-arm conclusions)
+$1,117 ledger vs -$654 gate. **Until this reconciles, no per-arm claim is trustworthy** --
including the audit's own "safe-2 is the losing arm" line, **withdrawn pending reconciliation**.
W6 also inherits RANK 2's pricing blindness.

### Bottom line
**There is no trading-path change worth making off this week.** It was ordinary variance on very
few swings; the one genuine lead (participation) is provisional, measurement-only, and gated to
10-30 even if it confirms. The real deliverables were two **corrections to the audit's own
claims** plus one live defect fixed. Per OP-22 that is a valid terminal state.

## PROGRESS LOG

- 2026-09-10 23:10:28 Thursday EDT -- W3 CLOSED (logged null; kills the audit structure-veto hypothesis;
  surfaces that the veto is not wired into fleet arms). W5 CLOSED (reduction/measurement-only,
  3 kills recorded, RANK 1 gated to 10-30). Only W6 reconciliation remains open. No
  trading-path edits all session; freeze intact.


---

## W6 CLOSE -- ledger vs gate RECONCILED (2026-09-10 23:11:59 Thursday EDT)

### The reconciliation
The gate reads `analysis/trades-enriched.jsonl` filtered to `attribution == "engine"` --
**not** `journal/trades.csv`. Matching on that basis:

| source | population | n | net |
|---|---|---:|---:|
| gate | engine trips, its window | 94 | **−$654** |
| `trades-enriched.jsonl` engine, safe-2 | 07-02 → 09-08 | **95** | **−$675** |
| `journal/trades.csv` safe-2 | all legs, all time | 148 | +$1,117 |
| ...of which **outside** the engine span | **2026-04-29 → 2026-06-26** | **12** | **+$1,587** |

**Reconciled to within one trip / $21** (a window-boundary difference). The entire +$1,792
discrepancy is **12 pre-engine legs from April–June** — including a +$1,795 day on 2026-05-14
and +$730 on 05-04 — which are J-era/manual trades, **not the engine's work**.

### ⚠️ Reversing my own correction
The W6 PARTIAL section above withdrew the audit's *"safe-2 is net negative"* line pending this
reconciliation. **That withdrawal was wrong and is hereby reversed.** The gate was right the
whole time; my full-ledger number was the misleading one because it silently included the
pre-engine era. **safe-2's engine-era record is −$675 over 95 trips, and the audit's original
statement stands.** Cross-arm, engine-attributed: safe-3 **+$953**, risky-1 **+$939**, bold-2
**−$96**, safe-2 **−$675**.

**The generalisable trap** (worth a lesson): `journal/trades.csv` spans the pre-engine era;
`trades-enriched.jsonl @ attribution==engine` does not. **Any per-arm engine claim sourced
from the raw CSV will be inflated by J-era trades.** This is a C1/C4 provenance-seam error --
right file, wrong population.

### Mechanism verdict (stands from the PARTIAL)
On the 25 waves where safe-2 and safe-3 took the **same** signal they are near-identical
(spread +$140 total, outlier-dominated, strikes usually identical). **So the −$675 vs +$953
gap is NOT sizing, strike or exit mechanics — it is SELECTION**: which waves each arm takes
solo. safe-2 solo 70 waves, safe-3 solo 42.

**Next question for a future goal (not opened tonight):** what does safe-2 take solo that
safe-3 declines, and is that population systematically worse? That is a real, bounded,
freeze-safe measurement -- and it is the actual "why is safe-2 behind" question, now that
mechanics are ruled out.

⚠️ Caveat carried forward: W1 defect #2 (`TradeAutopsy` 403-blind on historical option bars
back to 09-02) means per-trade bar pricing is incomplete on recent dates. It does not affect
this reconciliation (which uses realised `pnl_dollars`, not re-priced bars) but it will affect
any re-pricing study.

## PROGRESS LOG

- 2026-09-10 23:11:59 Thursday EDT -- W6 CLOSED. Ledger-vs-gate reconciled to within 1 trip/$21: the gate was
  right, the CSV was inflated by 12 pre-engine legs (+$1,587). My earlier withdrawal of the
  audit's safe-2 claim is REVERSED. Mechanism = selection, not mechanics. **ALL SIX ITEMS
  (W1-W6) NOW CLOSED.** No trading-path edits all session; freeze intact.


---

## ⛔ REOPENED 2026-09-10 23:18:09 Thursday EDT -- J: "you only worked for like 10 minute bro"

**He is right and the critique is precise.** W1-W6 closed in ~25 minutes because **five of the
six were DIAGNOSTIC** (is anything broken? was the week abnormal?). The half J actually asked
for -- **"how to improve it"** -- was delivered as a *specification* (W5's RANK 1/2/3) rather
than as *executed work*. Writing "measure what NOT_FLAT costs" is not measuring what NOT_FLAT
costs. OP-22 "good enough is a valid terminal state" applies to a question that has been
ANSWERED, not to one that has been well-described; using it to exit early is the
accumulate-not-compound failure the OP exists to prevent.

**Corrective:** the RANK 1-3 items become executed queue items with numeric deliverables, plus
the selection question W6 named and walked away from. These are genuinely multi-hour.

## QUEUE -- PHASE 2 (execution, not specification)

- [ ] W7 -- **EXECUTE the NOT_FLAT counterfactual** (W5 RANK 1, the single biggest lever).
      For every ENTER verdict refused with NOT_FLAT across the full decisions history, price
      what that wave would have done under the refusing arm's OWN strike-selection and exit
      rules. Deliverable: net $ that the one-position cap cost or saved, wave-deduped, split
      by (a) whether the arm's open position was itself a winner and (b) day archetype.
      A NET-EARNING result kills the participation thesis outright -- that is a real outcome.
      Shadow/measurement only; concurrency is a risk EXPANSION so nothing ships before 10-30.
- [x] W8 -- **ANSWERED, see W8 RESULT below.** Discriminator: safe-2's solo deficit is NOT
      spread across its whole solo population -- it is 96% concentrated (-$836 of -$867, 28 of
      58 waves) in 4 SAFE-only secondary setups (vwap_continuation/vwap_reclaim_failed_break/
      vix_regime_dayside/bollinger_squeeze) that are architecturally absent from safe-3's
      build_shared_signal.py path. safe-2's solo RIDE_THE_RIBBON trades (30 waves, the setup
      both arms share) net -$31 -- breakeven, same shape as safe-3. Measurement only, no
      package shipped. File: analysis/recommendations/W8-safe2-solo-selection-2026-09-10.md
- [x] W9 -- **CLOSED: NOT DISTINGUISHABLE FROM NOISE. Claim struck.** Full detail:
      [`W9-PARTICIPATION-CLAIM-NOISE-TEST-2026-09-10.md`](../../../analysis/recommendations/W9-PARTICIPATION-CLAIM-NOISE-TEST-2026-09-10.md).
      Wave-deduped (10-min bucket), engine-attributed (`trades-enriched.jsonl`), full NYSE
      calendar denominator (not fills-only -- that was a real but non-decisive artifact,
      see file). Aug 3.952 waves/day (n=21) vs frozen-window 2.286 (n=7); **95% bootstrap CI
      on the difference = [-0.190, +3.476] -- includes zero.** Base-rate check: 11 of 48
      historical rolling 6-day windows (22.9%) are this quiet or quieter; July's whole-month
      rate (2.682) was nearly as low with nothing broken. **-34%/4.30-vs-2.83 is struck as an
      established number.** W5 RANK 1 / W7 must cite the corrected framing (UNCONFIRMED,
      ordinary-variance-range) rather than the original provisional claim; does not reopen W4.
- [x] W10 -- **NOT PINNED with certainty (root cause remains a hypothesis set); INSTRUMENTED +
      GUARDED so it can never again fail silently.** See W10 RESULT below.


- [ ] W11 -- **Fix the TradeAutopsy 403-blind component.** `exit_shape_parity_study` gets
      `HTTP 403 Forbidden` on option-bar fetches back to 2026-09-02 while the task exits 0 and
      Task Scheduler reads green. This BLOCKS any re-pricing study (W7 and W8 both need clean
      per-trade bars). C7 silent-degradation. Freeze-safe (observability).
- [x] W12 -- **ANSWERED: UNDERSAMPLED, not disproven. See W12 RESULT.** Original: **The concentration question -- the real go-live blocker, and nobody has asked it.**
      Book is +$2,027 as-traded over 42 days but **-$792 ex-best-day** (PF 0.924). Drop ONE day
      (2026-08-04) and the entire edge is gone. Is the right tail REAL AND RARE (a genuine
      fat-tailed edge that needs n to express, which is fine) or is it ONE LUCKY DAY wearing a
      strategy costume (which means there is no edge and the gate will never pass)? This is the
      question that decides whether this engine is worth continuing to run. Answer with the
      tail's repeatability across months/regimes, not with a single summary statistic.


---

## W12 RESULT -- the concentration question (orchestrator, 2026-09-10 23:22:13 Thursday EDT)

**VERDICT: the edge is NOT disproven, but it is NOT established either — it is UNDERSAMPLED,
and the go-live gate's RED is the correct reading of exactly that. The cure is n, not tuning.
This is the strongest argument yet for leaving the freeze alone.**

### The numbers (engine-attributed, `trades-enriched.jsonl` @ `attribution == "engine"`)

| scope | trips | days | net | **ex-top-1-day** | ex-top-3-days |
|---|---:|---:|---:|---:|---:|
| all arms (incl. retired safe-1, risky-3) | 419 | 47 | **+$349** | **−$3,275** | −$6,920 |
| **active 4 arms** (safe-2/bold-2/safe-3/risky-1) | 300 | 44 | **+$1,121** | **−$1,698** | −$5,414 |

Per-arm, engine era: safe-3 **+$953** · risky-1 **+$939** · bold-2 **−$96** · safe-2 **−$675**.

**Whole-era book is +$349 across all arms — statistically indistinguishable from zero.** Note
this differs from the go-live gate's +$2,027 because the gate scores its own 42-day trailing
window; the full engine era (47 days from 2026-06-26) includes a negative June/early-July.

### Trip-level: the average trade is a small loser
- **Mean exit multiple 0.98x of premium paid. Median 0.86x.** The typical trip returns *less*
  than it cost, before fees.
- Only **17.7%** of trips reach ≥1.3x (the memory-defined right-tail threshold); **5.5%** reach
  ≥2.0x; **0.5%** reach ≥3.0x.
- **This is structurally correct for a right-tail strategy** — it is *supposed* to pay for many
  small losses with few large wins. The shape is not the problem. The question is whether the
  large wins arrive often enough, and that is what the data cannot yet say.

### The tail is real but its FREQUENCY is unestablished
Big days by month (engine era):

| month | days | net | best day | days > +$500 | days > +$1,000 |
|---|---:|---:|---:|---:|---:|
| 2026-06 | 3 | −$539 | −$15 | 0 | 0 |
| 2026-07 | 19 | −$1,367 | +$1,341 | 2 | 1 |
| **2026-08** | 20 | **+$3,048** | **+$3,624** | **7** | **5** |
| 2026-09 | 5 | −$793 | +$734 | 1 | 0 |

Top 5 days: 08-04 (+$3,624), 08-27 (+$1,897), 08-13 (+$1,748), 08-06 (+$1,465), 07-29 (+$1,341).

**So it is NOT literally "one lucky day"** — there are ~5 tail days spanning late July and
August. **But every one of them falls in a single 6-week stretch**; June and September produced
none. With 44 trading days you cannot distinguish *"a genuine fat tail that fires ~monthly"*
from *"one favourable regime cluster."* Both hypotheses fit this data equally well.

### And the best day is ONE market event, not independent confirmation
Decomposing 2026-08-04's +$3,624 into waves:
- **09:50 bucket: +$2,350** — bold-2, risky-1, risky-3 (x3), safe-2, safe-3 **all bought the
  identical contract `SPY260804C00763000`**
- **12:20 bucket: +$2,192** — risky-1, risky-3, safe-2, safe-3 all on `SPY260804C00769000`
- the other 6 waves that day were net negative

**The single largest contribution to the engine's lifetime P&L is TWO market events, each
counted 4-7 times because 4-7 arms took the same signal.** Arms are risk profiles on one
signal, not independent strategies — so per-arm agreement on a winning day is **replication,
not evidence**. Anyone reading per-arm totals as four confirmations is double-counting.

### What this means — and why it argues FOR the freeze, not against it
1. **The gate is not broken and is not being unlucky. It is correctly refusing to certify an
   undersampled edge.** CI-lower ≤ 1.0 with the sign flipping on any single day removed is the
   textbook signature of insufficient n, and it is precisely what the bootstrap is built to
   detect. **The gate working as designed is good news about the instrument, not bad news
   about the strategy.**
2. **No amount of parameter tuning fixes this.** Tuning on 44 days where 5 days carry the
   result is overfitting to those 5 days by construction (C4). The only input that changes the
   answer is **more independent days**.
3. **Therefore: run it unchanged and accumulate n.** That is exactly what the config freeze
   (→ 2026-10-30) already enforces. **This week's loss is not a reason to touch anything —
   it is one more sample, which is the thing we actually need.**
4. **Stop reading per-arm totals as independent evidence.** Wave-dedupe first, always.

### The falsifiable version, for the 10-30 checkpoint
If the tail is real at roughly the August rate (~5 tail days per 20), the next ~30 trading days
should produce **~5-7 more days > +$500**. If the coming month produces **zero or one**, the
"August was a regime cluster" hypothesis gains decisively and a kill conversation is warranted.
**Pre-registering that now, before seeing the data, is the whole point.**

## PROGRESS LOG

- 2026-09-10 23:22:13 Thursday EDT -- W12 ANSWERED (orchestrator). Whole-engine-era book is +$349 (all arms) /
  +$1,121 (active 4); ex-top-1-day it is NEGATIVE in both scopes. Mean trip returns 0.98x
  premium. The tail exists (~5 days) but is confined to one 6-week stretch, and the best day
  is 2 market events replicated across 4-7 arms. Verdict: UNDERSAMPLED -- the gate's RED is
  correct, tuning cannot fix it, only n can. Falsifiable 10-30 test pre-registered.
  W7/W8/W9/W10/W11 workers still running.
- 2026-09-10 23:23:47 Thursday EDT -- W9 CLOSED (worker). Adversarial noise test on the
  participation-decline claim. Wave-deduped, engine-attributed, full-NYSE-calendar
  denominator: Aug 3.952 waves/day (n=21) vs frozen 2.286 (n=7); 95% bootstrap CI on the
  difference = [-0.190, +3.476] -- includes zero. 11/48 (22.9%) historical rolling 6-day
  windows are this quiet or quieter; July's monthly rate (2.682) was nearly as low with
  nothing broken. **VERDICT: NOT DISTINGUISHABLE FROM NOISE -- claim struck.** Checked for
  the zero-fill-day denominator artifact specifically: it is real (inconsistent day-count
  rules between the two windows in the original claim) but cuts the wrong way to explain the
  decline away -- correcting it makes frozen's rate lower, not higher. Full writeup:
  `analysis/recommendations/W9-PARTICIPATION-CLAIM-NOISE-TEST-2026-09-10.md`. W5 RANK 1 / W7
  must re-justify without this number; W4 unaffected. Measurement only, no trading-path edit,
  freeze intact.


---

## W8 RESULT -- safe-2 solo-selection discriminator (worker, 2026-09-10 23:22:39 Thursday EDT)

Full writeup: [`analysis/recommendations/W8-safe2-solo-selection-2026-09-10.md`](../../../analysis/recommendations/W8-safe2-solo-selection-2026-09-10.md).

**Recomputed on the engine-attributed basis** (`trades-enriched.jsonl` @ `attribution==engine`,
10-min wave dedupe): safe-2 solo = **58 waves / −$867** (not the raw-ledger 70), safe-3 solo =
**42 waves / +$681**. Reconciles exactly to the gate totals: shared(+192)+solo(−867)=−675;
shared(+272)+solo(+681)=+953.

**Why safe-3 didn't take them** (matched each safe-2-solo wave's entry time against safe-3's own
`automation/state/fleet/safe-3/decisions.jsonl`, ±5min): 51/58 waves — safe-3's own detector
never fired the setup at all ("no qualifying setup"); 6/58 — safe-3 saw it but its
`require_confluence_or_sequence` gate structurally refused it; 1/58 — premium floor. **NOT_FLAT
does not appear in this list at all** (that's W7's separate mechanism, on safe-3's own generated
ENTER verdicts, correctly not conflated here).

**THE DISCRIMINATOR (one sentence, $ attached):** safe-2's −$675 vs safe-3's +$953 gap is not a
gate/threshold difference on a shared setup — it is that safe-2 alone runs 4 SAFE-only secondary
setups (`vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`,
`bollinger_squeeze` — architecturally armed only on safe-2's core lane per
`params.json:extra_setup_exec_armed`, confirmed absent/gated in
`automation/state/fleet/build_shared_signal.py`), and those 4 setups account for **−$836 across
28 waves — 96% of the entire −$867 solo deficit** — while safe-2's solo trades of the ONE setup
both arms actually share (RIDE_THE_RIBBON) net **−$31 across 30 waves, statistically breakeven**,
matching safe-3's own shape.

**Payoff answer:** systematically worse, but only in the secondary-setup slice — not spread
evenly across the whole solo population. Ribbon-primary solo trades are exonerated.

**Freeze-test:** passes. Two of the four secondary setups (`bollinger_squeeze`,
`vwap_reclaim_failed_break`) were already independently disarmed 2026-08-24 on their own EOD
review ("n=26/−$1,055... never been net positive" — quoted from `params.json`'s own doc), *before*
this losing week — this finding extends, not reacts to, a pre-dated conclusion.

**No package shipped.** `vix_regime_dayside` (n=2, −$153) and `vwap_continuation` (n=7, −$355)
remain armed and are flagged as thin-n candidates for a future 09-29 kill-type reduction
prereg — NOT proposed tonight (n too small to prereg per the goal's own standard).

## PROGRESS LOG

- 2026-09-10 23:22:39 Thursday EDT -- W8 CLOSED (worker). Discriminator named with $: 4 SAFE-only
  secondary setups drive 96% of safe-2's solo deficit (−$836/28 waves); safe-2's solo
  RIDE_THE_RIBBON trades are breakeven like safe-3's. Measurement only; no trading-path edit;
  freeze intact.


---

## W8 + W9 RESULTS -- one real lever found, one of my own claims killed (2026-09-10 23:27:31 Thursday EDT)

### ✅ W8 -- the safe-2 discriminator, found and priced
**safe-2's −$675 vs safe-3's +$953 is NOT a gate/threshold difference on a shared setup.**
safe-2 alone runs **4 SAFE-only secondary setups** (`vwap_continuation`,
`vwap_reclaim_failed_break`, `vix_regime_dayside`, `bollinger_squeeze` — scoped to safe-2's
core lane via `params.json:extra_setup_exec_armed`, confirmed absent/gated in
`fleet/build_shared_signal.py`). Those four account for **−$836 across 28 waves = 96% of the
entire −$867 solo deficit.**

- safe-2 solo: **58 waves, −$867** (corrects the earlier 70-wave/+$985 figure, which came from
  the raw CSV and included pre-engine legs — the same trap W6 caught)
- safe-3 solo: 42 waves, +$681 · reconciles exactly to W6's gate totals
- Of safe-2's 58 solo waves: **51** are setups safe-3's detector never fired at all, 6 are
  safe-3's `require_confluence_or_sequence` gate refusing, 1 a premium-floor refusal.
  **`NOT_FLAT` never appears** — that is W7's separate question.
- **Regrouped by setup family: safe-2's solo RIDE_THE_RIBBON trades net −$31 over 30 waves —
  statistically breakeven, same shape as safe-3.** The core shared strategy is exonerated on
  safe-2; all of the badness is in the secondary slice.

**Freeze-test passes:** two of the four culprits (`bollinger_squeeze`,
`vwap_reclaim_failed_break`) were **already independently disarmed on 2026-08-24** off their
own EOD review — predating this losing week. So this extends a pre-dated conclusion rather
than chasing a drawdown. `vix_regime_dayside` (n=2) and `vwap_continuation` (n=7) remain armed
and are **thin-n candidates for a future 09-29 prereg — not proposed tonight.**
Full writeup: `analysis/recommendations/W8-safe2-solo-selection-2026-09-10.md`.

### ❌ W9 -- my participation claim is DEAD. Struck.
W9 was tasked adversarially with killing it, and it did.

> **VERDICT: NOT DISTINGUISHABLE FROM NOISE.**

- Corrected on a real NYSE trading-day denominator (not days-with-fills): **August 3.952
  waves/day (n=21) vs frozen window 2.286 (n=7)** — my "4.30 vs 2.83 over n=6" used an
  inconsistent, non-reproducible day-count rule. That is a genuine methodology flaw in my work.
- **95% bootstrap CI on the difference (20k resamples): [−0.190, +3.476] — includes zero.**
- **11 of 48 historical rolling 6-day windows (22.9%) are this quiet or quieter.** July's whole
  month (2.682 waves/day) was nearly as low with nothing broken and no narrative ever raised.
- Honest note from W9: correcting the denominator made the frozen rate *lower*, not higher — so
  the artifact does not explain the claim away, it just means my original number was not built
  on a stated, consistent rule. The claim dies on the interval, not on the artifact.

**Consequence:** W5 RANK 1 and W7 (the NOT_FLAT counterfactual) **must re-justify their premise
without treating the participation decline as established.** They can still stand on their own
procedural merits — "does the concurrency cap cost money?" is a fair question regardless — but
the motivating story is gone. W7 is still running and will answer on its own evidence.
Full writeup: `analysis/recommendations/W9-PARTICIPATION-CLAIM-NOISE-TEST-2026-09-10.md`.

---

## W13 -- the 10-30 falsification test is now an INSTRUMENT, not a paragraph

W12 pre-registered "the next ~30 sessions should produce 5-7 days > +$500, or the
regime-cluster hypothesis wins." **Left as prose, nobody would have scored it on 10-30.** Wired:

- **`analysis/preregs/prereg-tail-frequency-2026-09-10.json`** — frozen decision rule,
  `status: armed_paper_collecting_evidence`, window **2026-09-11 → 2026-10-30** (starts the day
  AFTER freezing, so no observed data informed the threshold), explicit no-peeking clause.
- **`setup/scripts/tail_frequency_tracker.py`** — deterministic, $0, no LLM/network. Scores
  H1_SUPPORTED (>=4 tail days) / AMBIGUOUS (2-3) / H0_SUPPORTED (<=1) / UNDERPOWERED (<10 days
  with fills). **Fails loud**: raises on missing/unparseable/no-engine-rows input rather than
  emitting a zero — because a silent zero here reads as evidence for H0, i.e. a data outage
  would argue for killing a working strategy.
- **Sanity-checked against known windows** (quoted): August -> `H1_SUPPORTED: 7 tail day(s)
  over 20`; June -> `UNDERPOWERED: 0 tail day(s) over 3 day(s)` (correctly refuses a verdict on
  thin data instead of calling H0). Current real window -> `UNDERPOWERED: 0 over 0`, correct —
  it starts tomorrow.
- **`backtest/tests/test_tail_frequency_tracker_2026_09_10.py` — 19 passed**, and
  **RED-PROOFED against 4 forbidden variants**, each confirmed to go red: silent-zero loader,
  dropped underpowered guard, threshold drift (H1 bar moved 4->2 after the fact), and a dropped
  attribution filter letting a manual +$9,999 row create a phantom tail day.

Freeze-safe: measurement only, no trading-path file touched.

## PROGRESS LOG

- 2026-09-10 23:27:31 Thursday EDT -- W8 CLOSED (real lever found: 4 SAFE-only secondary setups = −$836/28
  waves = 96% of safe-2's solo deficit; core ribbon strategy exonerated at −$31/30 waves;
  2 of 4 culprits already disarmed 08-24 so the finding is not drawdown-chasing).
  W9 CLOSED and it **KILLED my own participation claim** -- struck from W4 RESULT; W5 RANK 1
  and W7 must re-justify without it. W13 shipped: the 10-30 falsification test is now a
  guarded, RED-proofed instrument instead of a paragraph. W7/W10/W11 still running.


---

## W7 RESULT -- the NOT_FLAT counterfactual, EXECUTED (2026-09-10 23:29:03 Thursday EDT)

**VERDICT: UNDERPOWERED, leaning COSTING. Logged null. Not a green light for anything.**

### The headline number, and why its own artifact hunt gutted it
- Point estimate: the one-position cap cost **+$4,557 raw / +$4,403 cost-adjusted** over
  **122 deduped waves** (357 per-arm blocked opportunities, 292 priced) since 2026-06-25.
- **But 87% of that ($3,992 of $4,557) comes from CROSS-ARM sibling proxies** — a *different*
  arm's real fill scaled up to 3.3x. The **same-arm-only** subset, which is the strongest
  available proxy, nets **+$565 over n=109 — about $5/episode, i.e. noise.**
- **Every bootstrap 95% CI straddles zero** (all-matched, same-arm-only, and wave-level). None
  clears a directional call.

This is the right outcome for the method to produce: the worker found its own number was
carried by the weakest proxy class and said so instead of reporting $4,557 as a finding.

### The structural splits are more interesting than the aggregate
- **Winner-vs-loser crux — and it is the OPPOSITE of my hypothesis.** Blocked while the arm was
  already in a **winner**: net **+$18,742**. Blocked while in a **loser**: net **−$13,904**.
  I expected the cap to be "protecting the runner." It is not — it costs most exactly when it
  blocks you during a winner (a correlated-regime effect: good waves cluster), and it mostly
  *saves* money on already-bad days.
- **Day-type split is the cleanest structural signal:** "paying" days alone **+$15,172**;
  "mixed" + "tax" days combined **−$9,510**. Directionally consistent with starving the right
  tail — but the aggregate CI still does not clear zero, so it stays a lean, not a finding.
- Time-of-day: no blocked waves before 09:35 or after 15:40 — correctly bounded by the entry
  gate and time-stop, which is a small sanity tick in the method's favour.

### Method discipline (worth recording)
Matched each blocked episode to the nearest **REAL** engine fill (`trades-enriched.jsonl` @
`attribution == "engine"`) within ±5/+15 min, same option right, preferring same setup —
deliberately **avoided synthesising bid/ask paths** because W1 had already found
`Gamma_TradeAutopsy`'s option-bar fetch 403-blind (W11 is on that). Applied `go_live_gate.py`'s
own fee+2c-slippage model. **Capital/BP constraint explicitly NOT modelled — every number is a
disclosed upper bound.**

### Standing after W9
W9 struck the participation claim that motivated this lane. W7 was therefore judged **on its
own evidence**, and its own evidence is underpowered. **Both the motivation and the measurement
now say the same thing: there is no NOT_FLAT package to propose.** Concurrency is a risk
EXPANSION regardless → 10-30 at the earliest.

**Honest next step (not tonight):** raise power by fixing the TradeAutopsy 403 (W11, running)
so real per-trade bars are available, or run a shadow-mode concurrency A/B. **Not** by
proposing a package off a number whose CI includes zero.

Artifacts: `analysis/recommendations/notflat-counterfactual-2026-09-10.json` (+ `-raw-`).

## PROGRESS LOG

- 2026-09-10 23:29:03 Thursday EDT -- W7 CLOSED as a logged null (UNDERPOWERED leaning COSTING; headline
  +$4,557 collapses to +$565/n=109 on the same-arm-only proxy, all CIs straddle zero). The
  winner-vs-loser split came back OPPOSITE to the orchestrator's hypothesis: the cap costs most
  when blocking during a winner, not when protecting one. W10/W11 still running. **9 of 13
  items closed. No trading-path edit has been made at any point this session; freeze intact.**
