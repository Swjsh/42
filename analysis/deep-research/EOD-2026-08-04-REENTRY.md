# EOD 2026-08-04 — LENS 1: ADJUDICATING THE vwap_continuation RE-ENTRY LOOP

**Run:** 2026-08-04 after the close (ET verified 16:07, `market_hours=False`).
**Authority:** real broker fills (`automation/state/fills-ledger.jsonl`, `attribution==engine`)
+ real OPRA 1-min bars fetched live from Alpaca for all 8 traded contracts (3,080 bars).
**Scope:** the 09:46–09:57 `vwap_continuation` cluster flagged mid-session, adjudicated to a verdict.

---

## VERDICT — (c) UNDERPOWERED, and arming any cooldown tonight is NOT justified

A per-setup re-entry cooldown **loses money on every honest cell of today's real fills**, and the
24-day population evidence points the *opposite* way from today. Those two facts cannot both be
explained by one hypothesis at this sample size. That is the definition of underpowered.

**But the sub-verdict is unambiguous: do not arm a cooldown.** Nothing in the evidence supports it,
and the single cell that "wins" is a 2-minute-wide knife edge discovered on one day.

**More importantly: the cooldown is the wrong lever.** The loop is a *symptom*. The mechanism is a
**−6% premium stop running inside a 10.3%-median noise band** (§4). Fix the stop and the loop
disappears on its own; cap the loop and you keep paying the stop.

---

## 1. THE BRIEF'S PREMISE IS WRONG ON FOUR FACTS

I reconstructed every tick before analysing anything. Four load-bearing claims do not survive.

| # | Brief / lesson-item claim | Ledger truth | Impact |
|---|---|---|---|
| 1 | risky-3 "logged ENTER_BULL on SEVEN ticks" → 7 entries | 7 **decision rows**, only **4 PLACED**. 09:48 / 09:49 / 09:53 were `SKIP_DUPLICATE_CLAIM` | The alarm was calibrated on a number **75% too high**. `action=ENTER_BULL` is logged even when placement is refused. |
| 2 | "first four round-tripped for −$289" | The first **three** *placed* round trips lost **−$288.00** | Ordinal wrong; magnitude right. |
| 3 | "The FIFTH (09:57) became the trade of the day" | 09:57 was the **4th placed** entry (7th decision row) | No counting convention makes it 5th. |
| 4 | "risky-1 took the same signal only 3x (**tighter gate**) and made MORE" | risky-1 took it **2x**. Its gate is `gate_override.full_send=true` — the **LOOSEST** gate in the fleet. risky-3 is `min_triggers:1` | **The control is not a control.** The entry-side difference was never a gate difference. |

Claim 4 is the one that matters. It framed the whole question as "risky-3's gate is too loose."
It is not.

---

## 2. WHY risky-1 TOOK FEWER ENTRIES — IT WAS NEVER FLAT

risky-1 did not *decline* the later signals. It was **holding a position** and structurally could
not re-enter. Both arms bought the same 763C within 2 seconds of each other at 09:50.

| | risky-1 | risky-3 |
|---|---|---|
| 09:50 fill | 5 @ **1.39** | 8 @ **1.46** |
| −6% stop sits at | **1.3066** | **1.3724** |
| Outcome | held 95 min → **+$640.00** | stopped 09:52 → **−$40.00** |
| Then | (no re-entry possible: not flat) | re-entered 09:54, 09:57 |

The re-entries exist **only because the exit fired**. The loop is downstream of the exit, not of
the entry gate. Any fix aimed at the entry gate is aimed at the wrong half of the machine.

---

## 3. THE +$640 "CONTROL" WINNER SURVIVED BY 0.34 CENTS

This is the single most important number in the study.

Minimum bid proxy on the 763C during risky-1's hold: **1.3100** (09:57, real OPRA close − 3c
calibrated half-spread). risky-1's stop: **1.3066**.

| Scenario | Entry | Stop | Min bid | Result | Margin |
|---|---|---|---|---|---|
| risky-1 **actual** | 1.39 | 1.3066 | 1.31 | **SURVIVES** | **+$0.0034** |
| filled 3c worse | 1.42 | 1.3348 | 1.31 | STOPPED OUT | −$0.0248 |
| filled at risky-3's price | 1.46 | 1.3724 | 1.31 | STOPPED OUT | −$0.0624 |

**risky-1's entire vwap edge over risky-3 was ~7 cents of entry fill luck, resolved by a third of
one cent.** Had risky-1 filled 3 cents worse it would have churned exactly like risky-3 — and the
"tight gate beats loose gate" story would have been written in reverse. Do not build doctrine on
this comparison.

---

## 4. ROOT CAUSE — A −6% STOP INSIDE A 10.3% NOISE BAND

`vwap_continuation` carries `premium_stop_pct = -0.06` (`strategies.py#VWAP_CONTINUATION`).
Its `exit_patch` declares `stop_mode="structure"`, but `exit_manager.ExitState.from_entry`
resolves structure mode only when **`trigger_level is not None`**:

```python
resolved_structure = (shape_mode == "structure" and bool(structure_stop_enabled)
                      and trigger_level is not None)
```

`vwap_continuation` is a continuation setup — **`trigger_level` is always `None`**. So the
structure stop is a **guaranteed no-op** for this setup on every arm, and every position falls
back to the raw **−6% premium stop**. Both arms. Every trade.

**Noise floor, 763C, 09:45–10:30, real OPRA (n=46 1-min bars):**

| median 1-min range | p75 | p90 | max | bars whose OWN range ≥ 6% |
|---|---|---|---|---|
| **10.3%** | 13.1% | 14.9% | 23.4% | **93%** |

A −6% stop on an instrument where **93% of individual minutes have a wider range than the stop
itself** is not a risk control — it is a random exit generator. All four losing vwap round trips
today were −6% stop-outs. The winner was simply the one that wasn't clipped.

**Provenance gap (C14-class):** the −0.06/+0.40 shape was ratified by
`analysis/recommendations/vwapcont-exit-ab-ship-gate.json` on **n=149 trades over ~340 trading
days ≈ 0.44 trades/day** — i.e. **at most one entry per day, no re-entry structure in the
simulation at all**. It is now running at **up to 5 entries/day**. The shape was never validated
in the regime it is now executing in.

---

## 5. THE COUNTERFACTUAL — EVERY COOLDOWN CELL LOSES

**Method (TIER 1, exact, zero modeling):** a cooldown can only *remove* a real entry; it can never
invent one. Applying it as a filter over real broker round trips is therefore conservative and
uses only real money. Anchoring to last-entry and last-exit give identical results here.

### Today's real fills — all cells

| cooldown | risky-3 | risky-1 | **COMBINED** | vs live |
|---|---|---|---|---|
| **0 (live)** | n=5 **+156.00** | n=2 **+565.00** | **+721.00** | — |
| 5 min | n=3 −328.00 | n=1 −75.00 | −403.00 | **−1,124.00** |
| 10 min | n=3 +340.00 | n=1 −75.00 | +265.00 | **−456.00** |
| 15 min | n=2 −184.00 | n=1 −75.00 | −259.00 | −980.00 |
| 30 min | n=2 −184.00 | n=1 −75.00 | −259.00 | −980.00 |
| once/day | n=1 −104.00 | n=1 −75.00 | −179.00 | −900.00 |

### The explicit trade-off the brief asked for

**Yes — the cooldown that removes the −$288 churn also removes the trade that made the day, and
worse.**

- risky-3's **+$524** winner entered **3.0 min after the prior entry / 1.0 min after the prior
  exit**. Only a cooldown in the **10–11 min** window preserves it (09:57 is 11.05 min after
  09:46). At 12 min it dies. That 2-minute-wide survival window is the *only* reason the 10-min
  cell looks good — a textbook single-day artifact, not an effect.
- risky-1's **+$640** winner entered **4.0 min after its stop-out**. **Every cooldown ≥ 5 min
  destroys it.**

**The arm the brief nominated as the well-behaved control made 100% of its vwap money on a
4-minute re-entry.** The behaviour the alarm targeted is the behaviour that paid.

### Sensitivity (TIER 2, modeled — disclosed, not used for the verdict)

A calibrated OPRA replay (bid = close − 3c; 7/7 sign agreement vs real outcomes) was built to test
whether blocked entries would shift to later eligible ticks. **It is not used for the verdict**: its
baseline diverges from reality because it cannot reproduce the `SKIP_DUPLICATE_CLAIM` guard, and it
over-credits winners (+$1,058 modeled vs +$524 real on the 09:57 trade) by riding to the 2.5×
runner target. Both biases *favour* the cooldown-preserving cells, so Tier 1 is the conservative
read.

---

## 6. GENERALISATION — 24 REAL TRADING DAYS, AND IT POINTS THE OTHER WAY

**Disclosure of proxy:** the 391-day population **cannot** answer this. `vwap_continuation` was
import-dead until FIX2 and traded live for the **first time today** — ZERO historical live
sequences. The 391-day backtest population is 1-entry-per-day by construction (§4), so it contains
no re-entry structure to slice. **Closest available proxy: every same-arm / same-day / same-setup
repeat-entry sequence in the 24-day real engine-fill history (2026-06-26 → 2026-08-04), n=45
sequences.**

| population | seqs | Nth re-entry rescues | full P&L | first-entry-only | re-entry legs |
|---|---|---|---|---|---|
| ALL 24 days | 45 | 12 (27%) | +2,119.00 | −237.00 | **+2,356.00** |
| **EX-08-04 (23 days)** | 38 | 6 (**16%**) | −1,505.00 | −1,334.00 | **−171.00** |
| 08-04 only | 7 | 6 (86%) | +3,624.00 | +1,097.00 | **+2,527.00** |

**Tight sequences only** (a leg within 15 min of the prior — what a short cooldown actually targets):

| population | seqs | rescues | re-entry legs |
|---|---|---|---|
| tight, ALL 24 days | 14 | 2 (14%) | **+54.00** |
| tight, **EX-08-04** | 12 | 0 (**0%**) | **−846.00** |

**Cooldown swept across all 24 days of real fills:**

| cooldown | ALL 24d | EX-08-04 | 08-04 | delta vs live |
|---|---|---|---|---|
| 0 (live) | +2,119 | −1,505 | +3,624 | — |
| 5 min | +1,185 | −1,315 | +2,500 | −934 |
| 10 min | +2,110 | −1,058 | +3,168 | −9 |
| 15 min | +1,598 | −1,046 | +2,644 | −521 |
| **30 min** | **+2,268** | −755 | +3,023 | **+149** |
| once/day | −237 | −1,334 | +1,097 | −2,356 |

**How to read this honestly:**

- Ex-today, tight re-entries bled **−$846 over 12 sequences with a 0% rescue rate**. That is a real
  bleed signal and it argues *for* a cooldown.
- Today alone, tight re-entries made **+$900**. That argues *against*.
- Net across 24 days: **+$54.** A wash.
- The cooldown sweep is **non-monotonic** (5 bad → 10 neutral → 15 bad → 30 good). A genuine effect
  would not zig-zag. The only positive cell (+$149 over 24 days = **+$6/day**) is inside noise and
  is the classic signature of picking the grid point that happens to miss the right trades.

This is the positive-skew shape: **many small losses, rare large wins, and the wins arrive on the
late entries.** Blocking re-entries removes both. Over 23 ordinary days you save ~$37/day; on the
one trend day you forfeit ~$900. The sample contains exactly **one** trend day, so the expectation
is not estimable.

---

## 7. WHAT WOULD SETTLE IT

Pre-registered, not to be run until the data exists:

1. **n ≥ 10 tight (< 15 min) `vwap_continuation` re-entry sequences on real fills** — today
   contributes 2. At the current rate this needs roughly a month of sessions.
2. **Stratified by day archetype, ≥ 2 trend days AND ≥ 2 chop days.** Today's sample is 1 archetype.
   Aggregating across archetypes here is exactly the C4 error.
3. **The stop-width A/B must run FIRST** (§8). If the −6% stop is widened, the re-entry loop largely
   stops existing and the cooldown question is moot. Testing the cooldown under the current stop
   measures an artifact of the stop.

Bar for arming a cooldown: OOS positive **and** WF ≥ 0.70 **and** sub-window stable **and** monotonic
across the cooldown grid. Today it fails all four.

---

## 8. THE ACTUAL RECOMMENDED WORK — PREREG ONLY, NOTHING ARMED

**PREREG-A (the real lever): `vwap_continuation` stop width.** The setup's only live stop is −6%
against a 10.3% median 1-min noise band, and the shape was validated at ≤1 entry/day. Pre-register
an A/B over stop width {−6% (control), −12%, −20%, −25%, catastrophe-only} on real OPRA, measuring
entries-per-day and re-entry-sequence count as *outcome* variables, not covariates. **Prediction to
be scored:** widening the stop reduces re-entry count materially, because each re-entry today was
preceded by a stop-out.

**PREREG-B: `trigger_level=None` disables the structure stop silently.** Every
`stop_mode="structure"` shape is a **no-op on every trigger-level-free setup**, falling back to a
premium stop the exit A/B never intended. This is a C14 dead-knob: the config *says* structure, the
machine *runs* premium. Needs an explicit assertion + a decision on what continuation setups should
use as chart invalidation (VWAP itself is the obvious candidate — it is in the setup's name).

**NOT recommended:** any re-entry cooldown, at any value, tonight.

---

## 9. AUDIT OF MY OWN JUDGMENT AT 09:57

**Was the alarm defensible on the evidence available at 09:57? NO — on three independent counts.**

1. **The trigger count was wrong and was never checked.** I reported 7 entries. Four were placed.
   The number that drove the alarm's urgency came from counting `action` rows without reading
   `placement.placed` in the same record. One field, same row, not read. Not a judgment error — a
   verification error, and OP-33 exists precisely to catch it.
2. **The decision statistic was structurally biased.** Realized P&L at minute 11 of a cluster is
   censored, and the censoring correlates with outcome sign: losers resolve in <2 min and print;
   winners are still open and contribute nothing. Four fast losses plus one 7-minute-old open
   position is what a *working* trend-continuation setup looks like at minute 11. I read the
   censored sum as the setup's expectancy.
3. **The proposed action did not follow from the diagnosis even if the diagnosis were right.**
   I proposed `RUN_VWAP=False` — disarming the *entry producer* — for a pathology whose mechanism is
   the *exit*. Nothing about entry frequency was defective; the arm re-entered because it kept being
   returned to flat. Killing the signal to fix a stop is a category error.

**Was the retraction defensible? Right call, wrong process.** Retracting was correct — but I
retracted on the same censored 11-minute window that produced the alarm, having acquired no new
evidence. Both the alarm and the retraction were drawn from the same biased sample; the second
happened to land on the right side. **A coin that lands heads is not a decision procedure.** The
retraction also stated no threshold, so it left nothing behind: a future session inherits neither
the rule that would have justified the revert nor the reason it was withdrawn.

**Net:** the alarm was wrong, the retraction was right, and *neither was earned*. The process that
produced both is unchanged and will fire again on the next fast-loss cluster.

**One thing was correct and should be preserved:** I did not act mid-session. Rule 9 held. The gap
is that Rule 9 stopped the *action* but not the *conclusion* — and a stated conclusion is what a
later session acts on.

---

## 10. CORRECTIONS FILED TO THE LESSON-INBOX ITEM

`strategy/candidates/_lesson-inbox/intra-session-defect-call-evidence-threshold-2026-08-04.md`
was written during/after the session and repeats three of the four §1 errors — including
"risky-1 … on a tighter gate" and attributing risky-1's **whole-day** +$1,039.54 to the vwap
signal (its actual vwap P&L was **+$565.00**). Corrected in place this session, with the
placed-vs-logged distinction promoted into the lesson body, since that is the reusable failure.

---

## APPENDIX — vwap_continuation round trips, real fills (2026-08-04)

| arm | entry | K | qty | fill | exit | P&L | gap since prior entry / exit |
|---|---|---|---|---|---|---|---|
| risky-3 | 09:46 | 762 | 8 | 1.750 | 09:47 | **−104.00** | — |
| risky-3 | 09:50 | 763 | 8 | 1.460 | 09:52 | **−40.00** | 4.0 / 3.0 min |
| risky-3 | 09:54 | 763 | 8 | 1.520 | 09:56 | **−144.00** | 4.0 / 2.0 min |
| risky-3 | 09:57 | 763 | 8 | 1.400 | 10:23 | **+524.00** | 3.0 / **1.0** min |
| risky-3 | 10:35 | 765 | 8 | 1.330 | 10:37 | **−80.00** | 38.0 / 12.0 min |
| risky-1 | 09:46 | 762 | 5 | 1.770 | 09:47 | **−75.00** | — |
| risky-1 | 09:50 | 763 | 5 | 1.390 | 11:25 | **+640.00** | 4.0 / **3.0** min |

**vwap_continuation total: +$721.00 (10 legs, 7 round trips, first live session).**

**Reconciliation:** FIFO over real fills gives a day total of **+$3,624.00** vs the brief's
**+$3,617.19** (Δ $6.81). Both are real; the delta is fee/accounting treatment, not a trade
discrepancy. All five arms flat at the close — confirmed.

**PDT — UNVERIFIED, flagged as a missing instrument.** risky-3 closed **8 round trips today** on a
`multiplier=4` margin account. The Alpaca account payload returns **no `daytrade_count` and no
`pattern_day_trader` field**, so PDT headroom could not be verified this session from the broker.
This is the one argument for a re-entry cap that is *not* about P&L, and it currently has no
instrument behind it. Named here, not asserted.
