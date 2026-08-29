# PREREG — TIGHT-LADDER FORWARD TEST (frozen 2026-08-28, before the window opens)

> **Status: FROZEN.** Written and committed 2026-08-28 evening ET, before any data in the test
> window exists. The market is closed; the window opens 2026-09-01 09:30 ET. Nothing in this file
> may be edited after the window opens — corrections go in a dated addendum below the signature line.
>
> **This file arms nothing.** It defines a measurement and a decision rule. Arming live money
> remains J's action alone (OP-0 #1).

---

## 1. THE HYPOTHESIS (J's framing, 2026-08-28)

> *"Enough contracts to scale out and ride the ribbon, but keep it tight."*

The engine's money comes from the exit ladder, not from position size. Between 2026-08-18 and
2026-08-19 a set of size/exposure fixes landed (book-exposure ceiling armed `3a032973`, wired to the
fleet path `05ae765b`, cap refresher `1c9aa55a`; later the extra-setup lane disarm `a905ad5f`).

**H1 — the post-fix engine has positive per-contract expectancy that survives its best day and
realistic execution costs.**

Observed but NOT proven (this is what the test is for), measured 2026-08-19..2026-08-28:

| Cut | Pre-fix (34d, n=313) | Post-fix (8d, n=69) |
|---|---:|---:|
| Total | −$2,313 | +$3,455 |
| Win rate | 22% | 43% |
| Max position | $1,880 | **$925** |
| Trades > $1,200 | 10 | **0** |
| Mean position | $365 | $366 |
| **Per contract** | **−$0.20** | **+$13.02** |
| Per contract, ex-best-day | −$3.30 | **+$6.73** |

**The mechanism we believe is operating** (and which the test must be able to falsify): the ladder
was always profitable; what changed is the cost of the losers.

| | ladder exits | everything else |
|---|---:|---:|
| Pre-fix | +$14,521 (44 trades) | −$16,834 (−$63/trade) |
| Post-fix | +$4,634 (13 trades) | −$1,179 (−$21/trade) |

**Explicitly disclosed weakness:** per-contract P&L is size-neutral by construction, so a size cap
alone CANNOT explain a move from −$0.20 to +$13.02. Part of the observed improvement is therefore
other fixes, regime, or noise on 8 days — two of which (08-27 +$1,897, 08-28 +$1,304) are among the
period's best. **This prereg exists because that ambiguity cannot be resolved on the data that
generated the hypothesis.**

---

## 2. THE CONFIGURATION UNDER TEST

Held constant for the whole window. No mid-window tuning (Rule 9).

| Knob | Value | Rationale |
|---|---|---|
| Contracts per entry | **3 minimum, 5 maximum** | 3 = TP1 sells 2, 1 rides (floor for a real runner). 5 = sells 3, 2 ride. Above 5 adds drawdown, not runner quality. |
| Hard dollar cap per position | **$1,000** | Contracts alone do not bound risk — 3 contracts of a $2.50 option is $750. Both caps bind. |
| Exit ladder | **unchanged** — rungs +50%/+75%, TP1 +100% sell 66.7%, trail 15% off HWM, structure stop, −50% cap | The ladder is the profit engine. It is NOT under test. |
| Signal flow | **all qualifying signals** | The per-day figures assume the full signal flow, not one arm's fraction. |
| Setups | current armed set only | The extra-setup lane stays disarmed (`a905ad5f`). |

**Nothing else changes during the window.** No new filters, no re-tuning, no arm reconfiguration.
A clean window is the entire point; changing the system mid-window voids the test.

---

## 3. THE METRIC — fixed now, not chosen later

**Primary:** mean P&L **per contract**, day-clustered, one-sided, net of measured execution cost.

Per-contract because it is size-neutral: it cannot be flattered by sizing up on good days.
Day-clustered because all arms trade one shared signal (pairwise r ≈ 0.62–0.72); the trading day is
the only honest independent unit.

**Execution cost:** the measured value from `analysis/quote-tape/` (recorder shipped 2026-08-28,
first data 2026-09-01). Until ≥100 matched exit quotes exist, report the metric at **$0.00, $1.00
and $2.00 per contract** and treat **$2.00 as the headline** (the repo's own conservative figure).
When the measured number lands, it replaces the sweep — and the measured number is used regardless
of whether it helps or hurts.

**Secondary (reported, not decisive):** ladder-reach rate (fraction of entries reaching +50% of
premium), loser cost per trade, max position size, WR.

---

## 4. THE WINDOW — start AND end registered

- **Opens:** 2026-09-01 09:30 ET
- **Closes:** **2026-10-30 16:00 ET** (or the first day the day-count bar below is met, whichever is later)
- **Day-count bar:** ≥ **40 trading days** with ≥ 1 qualifying entry.

Registering the end date is deliberate. On the existing tape, moving the window end by ONE day
swung the required sample from 54 days to 132 — an unregistered end date is a free parameter for
whoever writes the report.

---

## 5. THE DECISION RULE — written before the data

Evaluated once, at window close. All four must hold to call H1 supported:

1. **Sign:** mean per-contract P&L > 0 at the measured cost level.
2. **Significance:** day-clustered one-sided lower confidence bound > 0 at 95%.
3. **Concentration (primary, not a side condition):** the sign **survives removing the single best
   day**. This is the test this engine has historically failed; it is not a tiebreaker.
4. **No regression:** no rule break, no manual intervention (target 0 — counted by
   `analysis/interventions/summary.json`), and zero ITM-at-expiry violations.

**If supported:** H1 becomes the basis for a *separate* live-arming decision by J. Support here is
necessary, not sufficient — it does not authorize real money by itself.

**If not supported — the kill rule, stated now:** the tight-ladder config is not carried forward as
an assumption. Specifically, if mean per-contract P&L at the measured cost is **≤ 0**, or the sign
fails the ex-best-day test, then the post-fix improvement is declared **regime or noise**, the
November live question is answered NO, and the next question becomes whether the strategy has an
edge at all rather than how to size it.

**Peeking:** interim readings may be produced (the nightly chain will emit them) but MUST NOT
change the configuration, the metric, the window, or this decision rule.

---

## 6. WHAT WOULD MAKE THIS TEST INVALID

Stated up front so it cannot be rationalized later:

- Any change to the exit ladder, setup set, sizing rule, or gate set during the window.
- Any manual trade or override on the tested arms.
- Substituting a different cost assumption than the measured one once it exists.
- Reporting a window other than the registered one.
- Any arm reconfiguration or retirement inside the window (note: risky-3 was retired 2026-08-28,
  BEFORE the window opens — that is fine; a mid-window equivalent would not be).

---

## 7. PROVENANCE

- Hypothesis source: J, 2026-08-28 — *"enough cons to scale out and ride the ribbon but keep it tight."*
- Supporting analysis, this session: per-contract economics, pre/post-fix split at 2026-08-19,
  exit-reason decomposition, ex-best-day concentration checks. All computed from
  `analysis/trades-enriched.jsonl` (canonical basis, FIFO-reconciled).
- Related instruments: `setup/scripts/quote_recorder.py` (cost measurement),
  `analysis/interventions/summary.json` (criterion 4), `setup/scripts/lib/scorecard_guards.py`
  (day-bootstrap + ex-best-day machinery), `setup/scripts/go_live_gate.py` (separate live gate).
- Doctrine: OP-11 eval-first, C4 concentration disclosure, C6 no look-ahead, Rule 9 no mid-window
  rule changes, OP-0 #1 arming is J's alone.

---

*Frozen 2026-08-28 evening ET. Addenda below this line only; the sections above are immutable.*

---

## ADDENDUM 1 — 2026-08-28 evening ET, BEFORE the window opens

**Trigger:** J asked whether the $1,000 cap was per-day, and observed it would permit ten $0.75
contracts. Both points expose genuine ambiguity in §2. Clarified here rather than left to
interpretation. **The window has not opened; no data in the test period exists.** This addendum
resolves an ambiguity and adds a missing control — it does not change the hypothesis, the metric,
the window, or the decision rule.

### 1.1 — The $1,000 cap is PER POSITION, not per day

§2's row read "Hard dollar cap per position: $1,000" but was easy to misread. Restated:

- **Per single entry.** It bounds one position's premium outlay, nothing else.
- **J's example resolved:** ten contracts at $0.75 = $750, which passes the dollar cap — but the
  **5-contract cap binds first**, yielding 5 contracts for $375. The two caps are AND-ed; whichever
  is tighter wins.

**Measured on all 382 engine round trips** (entry premium: min $0.02, p25 $0.36, median $0.70,
p75 $1.13, p90 $1.41, max $2.37):

| Premium band | Which cap binds | Share of trades |
|---|---|---:|
| under $2.00 | contract cap (5) — spend $150–$1,000 | **97.4%** |
| $2.00–$3.33 | dollar cap — 3–4 contracts | 2.6% |
| over $3.33 | conflict: cannot hold 3 contracts under $1,000 → **SKIP** | **0.0%** |

The contract cap is the operative control in ~97% of cases. The dollar cap exists to bound the
tail, and the skip rule to resolve the conflict case — which has never yet occurred.

### 1.2 — Conflict rule (was undefined)

If premium is high enough that 3 contracts would breach the $1,000 position cap (premium > $3.33),
**skip the trade.** Do not breach the dollar cap, and do not take fewer than 3 contracts — below 3
the ladder cannot scale out (TP1 needs to sell 2 and leave 1 riding), so the position would no
longer be the strategy under test.

### 1.3 — Daily controls (MISSING from §2 — added here)

§2 bounded a position and never bounded a day. Observed post-fix behaviour, per arm per day:
median deployed **$810**, p75 $1,320, p90 $1,520, **max $1,955**; median **2** entries, max 5.

Added, chosen to sit just above observed behaviour so they bound the tail without altering normal
operation:

| Control | Value | Rationale |
|---|---|---|
| Max concurrent open positions | **1 per arm** | Already the engine's behaviour (NOT_FLAT blocks). Stated so it cannot drift. |
| Max entries per arm per day | **4** | Observed median 2, max 5. Bounds a churn day like 2026-08-28's risky-3 (5 entries, −$460). |
| Max premium deployed per arm per day | **$2,500** | ~1.3× the observed max. Binds only an abnormal day. |
| **Daily loss stop per arm** | **−$400** | The real control. See below. |

**Why the loss stop is the meaningful one:** deployment is not loss. Post-fix losers exit at mean
**−25%** of premium (median −21%, worst −57%) because stops cut before total loss. So three
maximum-size positions losing simultaneously is ≈ **−$757**, not −$3,000. A **−$400** daily stop
sits below that and above a normal bad day, and it is a hard floor that does not depend on any
stop firing correctly.

**Worst-case arithmetic under these controls, per arm per day:** 4 entries × $1,000 max = $4,000
gross deployed, but the −$400 daily stop binds first, so **the arm cannot lose more than ~$400 in a
day** absent a mechanical failure (process death with an open position — the known unbounded path,
tracked separately and NOT closed by this prereg).

### 1.4 — Effect on the test

None of these controls binds on normal observed behaviour (they sit above median and near the
observed max), so they do not alter the strategy under test. They bound the tail. If any of them
binds more than **twice in the window**, that is itself a finding to report — it would mean live
behaviour left the envelope the test assumed.

*Addendum 1 frozen 2026-08-28 evening ET, before window open.*

---

## ADDENDUM 2 — 2026-08-28 evening ET, BEFORE the window opens

**Trigger:** J's objection — *"I don't want to get into a con and get chopped out then sit out from a
winner for the day; there has to be some sort of decision making, a variable that changes."*
Recording the evidence behind Addendum 1's −$400 daily stop so it is on the record as
evidence-chosen rather than picked, and so the kill rule can be applied to it honestly.

### 2.1 — Loss-COUNT throttles lose money; loss-DOLLAR stops do not

These are different controls and the distinction is the whole answer to J's objection.

| Control | Winners blocked | Losers blocked | Net effect |
|---|---:|---:|---|
| Loss-count "stop after 2 losses" (T-2, measured forward) | **$589** | $283 | **−$306 — costs money** |
| −$200 / arm / day (dollars) | $2,762 | $3,688 | +$926 |
| **−$400 / arm / day (dollars)** | **$347** | $1,948 | **+$1,601** |
| −$600 / arm / day (dollars) | **$0** | $1,048 | +$1,048 |

Mechanism: a loss-count throttle fires on two trivial scratches and then blocks a real winner. A
dollar stop only fires after actual bleeding. **−$400 blocked $347 of winners across the entire
382-trade record.**

### 2.2 — Trading after losses is bad at every quality tier

Trades taken AFTER the day's first loss (all history): **n=311, −$5,115, WR 21%.** After the second
loss: n=271, −$3,104. Split by conviction tier, post-first-loss:

| Tier | n | Total | WR |
|---|---:|---:|---:|
| ELITE | 174 | −$2,714 | 18% |
| BASE | 65 | −$1,073 | 28% |
| TRENDLINE | 36 | −$283 | 31% |
| SUPER | 9 | −$423 | 0% |

**Raising the quality bar after losses does NOT rescue post-loss trading** — ELITE, the tier that
carries the book overall (+$2,540 in August), still loses after the day has turned. This kills the
otherwise-attractive idea of "after N losses, only take ELITE." Getting chopped is information
about the DAY, not about the next setup.

### 2.3 — The big winners arrive early, which is why the stop is cheap

Of 30 trades making ≥ +$300, **18 (60%) entered before 11:00 ET** (by hour: 09h=12, 10h=6, 11h=5,
12h=4, 13h=1, 14h=2). A daily dollar stop typically triggers after the window in which the day's
best trade would already have been taken. This is the direct answer to J's concern: **the stop
mostly fires on days whose winner never existed, not on days whose winner is still ahead.**

### 2.4 — Disclosure and status

- The −$400 stop triggered **9 times in 42 days** — small n. It is retained as a **bound on the
  tail**, not as a tuned parameter, and it is NOT part of hypothesis H1. If it binds more than
  twice in the window, that is reported as a finding (per §1.4).
- The −$600 variant blocked zero winners on this record and is the more conservative choice; −$400
  is retained because it bounds the day nearer the observed loss distribution (post-fix losers exit
  at mean −25% of premium, so three max positions ≈ −$757).
- **Not tested and explicitly out of scope:** a time-varying threshold (looser before 11:00 ET when
  the winner may still be ahead, tighter after). The 60%-early finding suggests it, the sample does
  not support fitting it, and adding it now would make the config a tuned artifact of the same data
  that produced the hypothesis. It is logged here as a candidate for a LATER, separately
  pre-registered test.

*Addendum 2 frozen 2026-08-28 evening ET, before window open.*
