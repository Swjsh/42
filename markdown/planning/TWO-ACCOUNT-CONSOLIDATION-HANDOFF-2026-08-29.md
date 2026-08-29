# HANDOFF — THE TWO-ACCOUNT CONSOLIDATION

> Prepared 2026-08-29 (Saturday, market closed) for a fresh session.
> Sources: a 9-agent autopsy/immunize/repurpose/red-team workflow, the compound-growth matrix, and
> direct verification of every load-bearing number by the orchestrating session.
> **This document arms nothing and changes no config.** Live-money arming is J's alone (OP-0 #1).

J's directive: *"remove safe-2 and figure out what exactly it was doing wrong and make sure the
others dont do that... swap that API key over to a NON SPY option trading... same for bold-2 but
keep bold-2 via a shadow lane... or maybe there isnt [anything to learn] and we can just go down to
the 2 accounts risky-1 and safe-3, leave them as is or propose additions... the end result will be
2 main accounts armed with everything we've learned over this entire year."*

---

## ⚠️ 0. READ THIS FIRST — THREE THINGS CHANGED SINCE THE DIRECTIVE WAS GIVEN

**0.1 — safe-2 was NOT a bad arm. Verified, exact reconciliation:**

| safe-2, split by execution path | n | P&L | WR |
|---|---:|---:|---:|
| **Primary path** (tier-scored ribbon_ride) | 50 | **+$462** | **30.0%** |
| **"Extra-setup" watcher lane** | 36 | **−$896** | 16.7% |
| Full arm (the number the cut decision used) | 86 | −$434 | 24.4% |

+462 + (−896) = −434 exactly. For comparison, safe-3 — the arm we called best-in-class — is
n=59, +$841, **WR 30.5%**. safe-2's real trading is the same arm.

The `extra_setup_exec_armed` lane was a **second entry channel that bypassed the tier/gate/confluence
system entirely**, armed only on safe-2's `params.json` from 2026-07-01 to 07-25. bold-2's equivalent
key has **never existed** in git history; safe-3/risky-1 run `fleet_executor.py` and structurally
cannot reach the lane. It is already ~80% disarmed (1 of 5 setups remains and has **placed 0 trades**).

**The transferable lesson — the most valuable output of the whole autopsy:** *never let a secondary
detector layer place live orders outside the same selectivity discipline as the primary path.*

**0.2 — 🚨 risky-1 HAS THE SAME DEFECT, AND IT IS STILL ARMED.**

| risky-1 lane | n | P&L | avg | WR | days | ex-best |
|---|---:|---:|---:|---:|---:|---:|
| `FULL_SEND` (secondary, fires when primary produces no ENTER) | 27 | **−$427** | −$15.81 | 33.3% | 7 | −$992 |
| normal (primary path) | 52 | **+$1,719** | +$33.06 | 25.0% | 23 | +$891 |

Joined placed-decisions → fills, 0 unmatched of 79. **The plan as stated retires the arm whose
secondary-lane defect is already fixed, and keeps the arm whose defect is live**
(`gate_override.full_send: true`). This is the single most actionable finding in the workflow.

**0.3 — 🚨 A QUEUED CONFIG CHANGE HAS THE WRONG SIGN AND IS SCHEDULED TO SHIP BEFORE MONDAY'S OPEN.**

`SAFE-2-EXIT-SHAPE-AB-PREREG` (queue.md, HIGH) applies `exit_patch {tp1_premium_pct: 0.5,
stop_mode: structure}` to safe-2 before 2026-08-31 open. Natural A/B — **37 (date,symbol) signals
both survivors took, identical contract, identical day**, using `ret_pct_of_premium` which is
qty-independent, so the exit shape is isolated:

```
mean diff (risky-1 tp1=0.5  minus  safe-3 tp1=1.0) = -3.48 pct-of-premium
median diff = 0.00   risky-1 better in only 9/37
ON SAFE-3 WINNERS (ret > +30%): n=9, mean diff -19.39 pp, risky-1 better in 2/9
ON EVERYTHING ELSE:             n=28, mean diff +1.63 pp
Cost if applied to safe-3: ~-$454 of its $841 lifetime P&L (54%)
```

**The patch does one thing: it clips the right tail** — and the right tail is where this engine
makes 100% of its money (39 of 210 August trades produced +$12,530 while the other 171 lost
−$10,786). The median diff of 0.00 confirms it is a tail effect, not a broad one.

⚠️ **Honest caveats:** n=9 winners is small; sign-flip p≈0.13; and safe-3/risky-1 differ in
`profit_lock_mode` too, so attribute to the exit-shape **bundle**, not the single knob (lesson C29).
The queue item's own supporting evidence is self-labelled *"proxy only, never single-variable."*
**Two analyses disagree on the sign. Neither is conclusive. That is sufficient reason not to ship a
trading-path change into a scoring window.**

**Recommended:** do not ship it. safe-2 is being retired, which makes it moot for safe-2, and
folding this shape onto a survivor would clip the tail on the best arm we have.

---

## 1. THE RED TEAM'S VERDICT ON THE CUT LIST

**Cut safe-2 — ✅ SURVIVES every attack.** Worst arm in **39/39** leave-one-day-out jackknifes; best
arm in only **3.4%** of day-bootstraps; and it has a named, git-dated, already-disarmed mechanism
(§0.1). The only leg supported by both statistics *and* mechanism.

**Cut bold-2 — 🚨 DOES NOT SURVIVE.** bold-2 is the book's **best arm in 26.9% of day-bootstraps**
(8× safe-2's rate), and **no mechanism finding was made against it**. This leg is a coin flip
presented as a conclusion. *The plan treats two very different confidence levels as one decision.*

**Is the keep/cut split statistically real at all?** Within-day label permutation (N=50,000,
preserving the day-level common shock, which is the correct null at r≈0.82):

```
keep-vs-cut gap on return-on-capital: +4.747pp,  p = 0.0986
min(keep) - max(cut):                 +2.266pp,  p = 0.0304
P(a random split gives this clean a 2v2 ordering) = 0.069
```

Day-block bootstrap — **not one arm has expectancy distinguishable from zero**:

```
safe-2   -$5.05/trade  95% CI [-35.13, +27.74]  P(mean<=0) = 0.634
bold-2   +$5.51/trade  95% CI [-62.39, +65.05]  P(mean<=0) = 0.423
safe-3  +$14.25/trade  95% CI [-42.58, +67.34]  P(mean<=0) = 0.295
risky-1 +$16.35/trade  95% CI [-29.75, +73.83]  P(mean<=0) = 0.249
```

Pairwise day-level paired tests under BH-FDR: **at q=0.05, ZERO survive.** And the most
decision-relevant comparison — safe-3 (keep) vs safe-2 (cut), same risk profile, most days in
common — is the **weakest of all four at p = 0.16**.

**Concentration:** the survivor pair's entire case is three days. `ex-top1 = +$455`,
`ex-top2 = −$961`, `ex-top3 = −$2,174`. The cut pair's *winning-day rate* (35%) is
indistinguishable from the survivor pair's (34%) — the difference is the size of a few days, not
how often the arms are right.

---

## 2. THE PAIR CHOICE IS A REAL TRADE-OFF, NOT AN OVERSIGHT

Effective sample size, ESS = k / (1 + (k−1)·r̄), on daily P&L:

| Pair | r̄ | ESS | fills | days | signals |
|---|---:|---:|---:|---:|---:|
| safe-2 + bold-2 | 0.691 | **1.183** | 125 | 31 | 77 |
| safe-2 + safe-3 | 0.816 | 1.101 | 145 | 37 | 90 |
| bold-2 + risky-1 | 0.821 | 1.098 | 118 | 32 | 67 |
| bold-2 + safe-3 | 0.825 | 1.096 | 98 | 32 | 65 |
| safe-2 + risky-1 | 0.839 | 1.088 | 165 | 35 | 89 |
| **safe-3 + risky-1 (the plan)** | **0.920** | **1.042** | 138 | 29 | **54** |

**The chosen pair is the worst of all six for independent evidence** — highest correlation, lowest
ESS, and it covers only **54 of 105** distinct signals. Going 4 arms → 2 costs **~10% of effective
independence (1.158 → 1.042), not 50%** — day count is unchanged because both survivors trade the
same days. The "halves the learning rate" worry is **not supported**; the real loss is **49% of
distinct-signal coverage**, which is where new mechanisms get discovered.

**The counterweight — and it is decisive for a 2-account design:** paired A/B power.

| Pair | SD(daily diff) | MDE @20d | days to detect $50/day |
|---|---:|---:|---:|
| **safe-3 + risky-1** | **$157.3** | **$98.5** | **78** |
| bold-2 + safe-3 | $190.4 | $119.2 | 114 |
| safe-2 + risky-1 | $235.4 | $147.4 | 174 |
| bold-2 + risky-1 | $277.4 | $173.7 | 241 |

**safe-3 + risky-1 is the BEST paired instrument in the book.** High correlation is bad for
independent sampling and *good* for controlled A/B. Both are true simultaneously — so the pair
choice is defensible **if and only if the second account's declared purpose is A/B, not
diversification.** State that explicitly in the design.

**Sobering scale note:** a single arm with no control needs **452 days** (risky-1) to detect
$50/day. Any question of the form *"did this change help?"* asked about one arm, inside a 20-day
window, is unanswerable. Only paired survivor-vs-survivor questions have power.

---

## 3. WHAT IS ACTUALLY LOST BY CUTTING — a veto, not an edge

**No hidden entry edge.** safe-2's 32 unique signals: 34 fills in the extra lane (−$830) and 18 on
the primary path (−$412, of which 14 are puts). **There is nothing to rescue in safe-2's unique
entries.** Say it plainly.

**But there IS a hidden day-level VETO.** The `SUPER` tier label — computable only on the arms being
cut — marks the survivors' six worst days:

```
survivors ON SUPER-flag dates:  n=48, days=6,  -$2,394, WR 22.9%
survivors on all other dates:   n=90, days=23, +$4,527, WR 32.2%
day-label permutation (choose 6 of 29, N=200,000): p(total) = 0.0215
NEGATIVE CONTROL (TRENDLINE-flagged days, k=11):   p = 0.4917  <- clean null
```

Six of 29 days turn the survivor pair's +$4,527 into +$2,133, and the only instrument that flags
those days lives on the arms being retired. **The negative control is clean, so this is not "any
label separates days."**

⚠️ **And a correction the red team made to its own workflow:** the claim that SUPER is *"structurally
absent from the survivors"* is **false**. All 12 SUPER rows carry `confluence`, so the fleet path
labels them **ELITE and admits them** — verified empirically on 2026-08-07 and 2026-08-12 where
safe-3 and risky-1 took the *same contract*. **Retiring the arms does not remove that 0-for-12
population from the book; it removes the only place it is visible.** That is the textbook shape of
"cutting the only arm that sees a thing."

**Both losses are recoverable in code without keeping the arms.** The fleet already has
`triggers_fired` in hand at `build_shared_signal.py:389`; computing the SUPER label there is
approximately one line. **Do that BEFORE the retirement, not after.**

**One more structural exposure:** 69% of the book's entire bear-side sample dies with the cut
(cut pair 53.6% bear; safe-3 alone is 91.5% bull with just 5 bear trades lifetime). Bear is a losing
population book-wide (n=97, −$1,334) so this is defensible on P&L — but after consolidation the
book has essentially **one live bear instrument**. If September turns bearish, we have almost no
validated bear machinery and no way to measure it. Disclose as a regime exposure, not a solved problem.

---

## 4. THE COMPOUND MATRIX — and the correction to its headline

Built this session: `setup/scripts/compound_matrix.py` → `analysis/compound/{matrix.json,MATRIX.md}`,
25/25 guard tests including byte-for-byte reproducibility.

**Its headline finding — a market-depth wall at $7.8K–$15.6K equity — is WRONG and must not be
carried forward.** It treated **46 contracts displayed at the NBBO** as capacity. Displayed
top-of-book size is what is quoted at the touch at that instant, not available liquidity. Verified
against the real 1-minute OPRA bars we already hold, for the contracts we actually traded:

```
median daily volume per contract: 491,846 contracts (p25 319,902 / p75 640,400)
our largest order ever:           12 contracts
a 100-contract order:             0.02% of that day's volume
```

**Liquidity is not a constraint anywhere near this plan.** The matrix's depth-capped projections
(12 contracts at any equity; $70K at 12 months) are therefore too pessimistic and should be
regenerated. Its "naive" projections are too optimistic for a different reason — they assume a rate
measured over 8 sessions holds for a year.

**What the matrix does establish — the compounding question reduces to one unknown: which regime:**

| Regime | n | mean %/day | median | $5K → 12mo | days to $10K | days to $25K |
|---|---:|---:|---:|---:|---:|---:|
| Post-fix | 23 arm-days / 8 sessions | +3.60% | +3.62% | *$14.8M — absurd* | 22 | 79 |
| **August** | 60 / 20 sessions | **+1.55%** | +1.19% | **~$57K** | 55 | 199 |
| All-history | 104 / 40 sessions | +0.59% | **−0.77%** | plateaus | 160 | 721 |

**J's model is sound and this is the number to plan against: at August's rate, $5K compounds to
roughly $57K in a year, and $2,000/day arrives on its own at ~$200K equity.** It is an *output*, not
a target — exactly as he framed it. The binding constraint is not capital and not liquidity; it is
**whether the August rate is the real one**. That is precisely what the September window measures.

---

## 5. STRUCTURAL PREREQUISITES — retirement will not work without these

Both verified in source by the workflow; both are prerequisites, not options.

1. **`setup/scripts/heartbeat_core.py:143-147` hardcodes `ACCOUNTS`**, iterated at ~line 3241.
   **Flipping safe-2's `accounts.json` status to retired does NOTHING — the engine keeps placing
   SPY 0DTE orders on `PA3POKNV46VG` every minute.** This must be closed before any MCP repoint.
2. **`eod_flatten._active_arms()` (lines 80-101) has no instrument filter**, so a non-SPY arm flipped
   active gets swept and logs a **false** `already flat`.
3. **The risky-3 precedent:** its 2026-08-28 retirement left `test_eod_flatten_coverage_2026_08_18.py`
   plus 6 fleet routing/display-name tests stale. **Take a full-suite baseline before and after any
   retirement, and fix fixtures as part of the change — never by weakening an assertion.**

---

## 6. THE WORK — ordered

### Before Monday 2026-08-31 open (the freeze begins)
1. **Do not ship `SAFE-2-EXIT-SHAPE-AB-PREREG`** (§0.3). Record the conflicting natural-A/B result
   in the queue item so the decision is auditable, and re-open it as a properly single-variable
   study later.
2. **Nothing else touches the trading path.** The freeze exists to give the gate 20 clean days.

### Inside the window (analysis and shadow only — both are unaffected by the freeze)
3. **Compute the SUPER label in the fleet path** (`build_shared_signal.py:389`, ~one line) and log
   it as a **day-level warning**, not an entry filter. This preserves the p=0.02 veto signal before
   the arms that carry it are retired. Highest-value item in the whole handoff.
4. **Investigate risky-1's `full_send` lane** (§0.2) — n=27, −$427, still armed. Determine whether
   it is the same class of defect as safe-2's extra-setup lane. If yes, disarming it is a
   **pre-registered kill-type risk reduction**, which the freeze explicitly permits.
5. **Persist signal context at fleet placement time** so the fleet path stops losing
   vix/ribbon/score attribution. ⚠️ The workflow's evidence for this was partly wrong: it cited a
   6-row DRY_RUN demo file. The real log is `automation/state/fleet/risky-1/decisions.jsonl`
   (**11,146 rows**, carrying `trigger_level`, `quality`, `reason`, `binding`, `core_tick_id`).
   The gap is real; "the fleet record has no attribution" is not.
6. **Regenerate the compound matrix without the false depth cap** (§4) and re-derive milestones.
7. **Mine the slippage columns we already have** before building anything to measure slippage —
   `analysis/trades-enriched.jsonl` already carries `exit_slippage_vs_mid_before_dollars`,
   `exit_quote_bid/ask/mid_before/after`, and `exit_quote_lag_before_s` on real fills. If those
   answer the execution-quality question, a dedicated lane is redundant.

### At window close (~2026-09-29)
8. **Retire safe-2** — the one cut supported by both statistics and mechanism. Close the
   `heartbeat_core.ACCOUNTS` gap first (§5.1), take the full-suite baseline, fix fixtures.
9. **Do NOT retire bold-2 on current evidence** (§1). Either keep it as the highest-ESS control, or
   pre-register a specific bar that would justify cutting it and wait for that bar. Cutting it now
   is a coin flip.
10. **The bold-2 shadow lane: do NOT build a P&L-replay version.** Its signals overlap risky-1's at
    r≈0.82 with 80% sign agreement — an echo, not information. If bold-2 is retained per §9, the
    question is moot; if it is eventually cut, the replacement instrument should be the SUPER-label
    veto (§6.3), which is the thing that actually dies with it.
11. **Non-SPY repurposing of safe-2's key: NOT a third directional lane.** Two independent
    pre-registered nulls already failed (weekly v1 on GLD/QQQ; the SPY-fork across 9 symbols /
    7,489 signals). A third would be a third kill. Revisit only after §6.7 establishes whether an
    execution-quality lane is even needed.

---

## 7. THE ANSWER TO "TWO ACCOUNTS ARMED WITH EVERYTHING WE LEARNED"

**The inheritance, stated as design rules:**

1. **One entry path, one discipline.** Every failure this year traces to a secondary lane placing
   orders outside the primary path's selectivity: safe-2's `extra_setup_exec_armed` (−$896) and
   risky-1's `full_send` (−$427). **No detector places a live order unless it passes the same gates.**
2. **The ladder is the edge — protect the right tail.** 39 of 210 August trades made +$12,530 while
   171 lost −$10,786. Any change that sells more, earlier, is suspect by default (§0.3).
3. **Size was the killer, never the signal.** Per contract, even the full record is positive; the
   dollar losses came from oversized positions. Caps stay.
4. **Losers cost, not loser count.** A loss-count throttle measured −$306 forward; a −$400 daily
   dollar stop blocked $347 of winners against $1,948 of losses.
5. **Concentration is the primary test, not a footnote.** Every claim reports ex-best-day. Nine of
   thirteen claims in a prior review died to this test alone.
6. **The second account is an A/B channel, not diversification.** At r̄ = 0.92 it diversifies almost
   nothing but is the most powerful paired instrument in the book (78 days to detect $50/day).
7. **Never re-run the dead:** multi-symbol lane, weekly v1 signal, NLWB, ribbon-rejection scalp, the
   four September tune candidates, loss-count throttles, VWAP family re-arming.

---

## 8. STARTING POINTS

`analysis/trades-enriched.jsonl` (canonical ledger) · `analysis/compound/MATRIX.md` ·
`analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md` (prereg format) ·
`markdown/planning/ARM-FUNNEL-HANDOFF-2026-08-29.md` (the earlier, now-superseded audit) ·
`analysis/deep-research/FABLE-FULL-REVIEW-2026-08-29.md` (parallel session, sets the freeze) ·
`setup/scripts/go_live_gate.py` (RED) · `setup/scripts/lib/scorecard_guards.py` (required guard
fields) · `automation/overnight/queue.md` · `MAP.md` (route here before any repo-wide search).
