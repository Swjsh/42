# Pipeline audit — 2026-08-11

J: *"It seems like you made a harness and then just wrote tests that would pass and then shipped
it as good."* Correct. This is the teardown. Every number below comes from **broker-realized
P&L or the live decisions ledger** — nothing from a harness I authored.

---

## 1. The harness is disqualified for exit-timing questions

Anchor test: feed each real position the config it *actually traded*, walk it, compare to the
real broker P&L. n=182.

| | |
|---|--:|
| ACTUAL | −$526 |
| REPLAY | +$5,423 |
| **bias** | **+$5,949** |

Decomposed:

| group | n | median Δ hold | total error |
|---|--:|--:|--:|
| harness held LONGER | 87 | **+21 min** | **+$2,118** |
| timing matched (±2 min) | 20 | −1 min | +$1,211 |
| harness exited sooner | 75 | −24 min | −$1,217 |

Two biases: it can't see the structure/ribbon/churn exits that actually end our trades (holds
~21 min too long), and it fills at trigger prices with no slippage (**+$60.5/position** on the
timing-matched cohort). Changing the fill mode from bar-extreme to `mixed` only cuts the bias
from +$5,949 to +$2,112.

**The disqualifier:** the hold-time bias *is* the variable under test. Every exit change is a
hold-longer hypothesis, evaluated by a harness that already holds longer than reality. It will
approve them regardless of merit. That is exactly what happened to the ladder.

---

## 2. What the real money says

**Wide vs tight stops — n=126 real fills, reproduced independently on every arm:**

| config | n | per trade |
|---|--:|--:|
| structure + −50% cap | 49 | **+$33.43** |
| tight % stops (−6%, −20%) | 77 | **−$28.96** |

**Ribbon_ride by config era (VWAP excluded):**

| era | legs | days | total | drop-best | days +ve |
|---|--:|--:|--:|--:|--:|
| **CURRENT** structure/−50% | 93 | 14 | **+$1,638** | **−$124 FAIL** | **6/14 = 43%** |
| LEGACY %-stop/None | 124 | 11 | −$1,320 | −$1,665 FAIL | 2/11 = 18% |

The legacy config is dead and retired — good. **But the current config is carried entirely by one
day: 2026-08-04 is +$1,762 = 108% of the total. Remove it and the book is −$124.**

**VWAP family (frozen prereg TIGHT-STOP-VWAP-2026-08-11): FAILS all gates.**
−$910 total, drop-best −$1,631, 2/4 days positive, only 4 days (G3 needs 8).

---

## 3. The finding that outranks every exit knob

Same setup, same config, two days:

| day | entries | result |
|---|--:|--:|
| 2026-08-04 | 25 | **+$3,624** — every arm positive |
| 2026-08-07 | 12 | **−$2,687** — every arm negative, all calls, 3 re-entry waves |

The engine re-enters aggressively in both cases and cannot tell them apart. **P&L is governed by
whether the day trends in the engine's direction, not by how it exits.** A −$2,687 left tail
larger than the +$1,762 best day, at 43% positive days, is a regime problem. Exit tuning cannot
fix it, and two days of exit work did not.

---

## 4. Status of every claim made this week

| claim | source | status |
|---|---|---|
| Ladder = +$6,454 | broken harness | ❌ **RETRACTED** |
| Ladder corrected effect | multi-leg harness | ⚠️ −$4,891, **p=0.26 → unproven** |
| TP1 / tranche grid | broken harness | ❌ discarded |
| "+$22k best cell" | 1 day = 167% | ❌ killed |
| Wide > tight stops, $62/tr | **broker truth** | ✅ holds |
| 145 die pre-TP1 vs 44 reach it | **live ledger** | ✅ holds |
| Median +75% available | raw OPRA | ✅ holds (upper bound) |
| risky-3 flip | its own prereg needs n≥20 days, **2 elapsed** | ⏸️ blocked, correctly |

---

## 5. What is actually true right now

- Entries: **good** on trend days, **repeatedly wrong** on chop days, with no discriminator.
- Exits: the give-back chain is fixed and held live on 08-11. The ladder is unproven.
- Config: the tight-% stops are the one change real money supports; two live paths still carry
  them (`vwap_continuation` −6%, `vwap_reclaim_failed_break` −8%).
- Simulation: **we do not have a trustworthy exit simulator.** Forward paper is the only clean
  adjudicator, and every remaining exit question has to go through it.
