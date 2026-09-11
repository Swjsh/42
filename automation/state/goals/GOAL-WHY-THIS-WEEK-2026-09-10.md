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
- [ ] W3 -- structure-veto x BEARISH_REJECTION net-$ verdict across the frozen window,
      wave-deduped, split by structure state: EARNING / COSTING / UNDERPOWERED with n.
- [x] W4 -- **VERDICT: VARIANCE, not regime-break.** Done 2026-09-10 23:03:47 Thursday EDT. Numbers below.
- [ ] W5 -- ranked pre-registered improvement set. UNBLOCKED by W4, and W4 REDIRECTS it:
      the lever is **PARTICIPATION, not gates**. Do not propose loosening anything to 'win
      more' -- the WR is normal. Investigate why waves/day fell 4.30 (Aug) -> 2.83 (frozen
      window) and whether that decline is (a) market conditions, (b) a gate/config change,
      or (c) silent execution loss (see W2). Only (b)/(c) are actionable, and only as
      pre-registered 09-29/10-30 packages.
- [~] W6 -- PARTIAL: shared-wave decomposition done (n=25, arms near-identical -> mechanics do
      NOT explain the gap). **BLOCKED on a measurement reconciliation** (ledger +$1,117 vs
      gate -$654 for safe-2) that must be resolved before any 'safe-2 is the losing arm' claim
      is trusted. See W6 RESULT.

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

### The REAL finding -- participation, not win rate
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
