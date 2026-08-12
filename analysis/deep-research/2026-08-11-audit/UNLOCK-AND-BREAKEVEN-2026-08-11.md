# Coverage unlock + the breakeven line (2026-08-11 night)

> Goal fire: "unlock more trades from historic data, make the engine better."
> Every number here is **broker-realized P&L** or a **calibration-v5 replay-vs-replay A/B**.
> Nothing here compares a replay against broker truth — that mistake is what produced the
> retracted +$6,454 ladder claim.

---

## 1. The unlock — the harness was blind to two of six accounts

**Defect.** `harness_fidelity_anchor.placement_configs()` globbed only
`automation/state/fleet/*/decisions.jsonl`. **safe-2 and bold-2 are not fleet arms** — they are
the `heartbeat_core` path and log to `automation/state/core-decisions.jsonl` under a different
schema (no `placement` block; `exec` carries ABSOLUTE tp/stop prices, strategy at top-level
`setup`). Every exit study silently excluded them, and the exclusion was misread as "no OPRA
data" rather than "the harness cannot see these accounts" (C7).

| | before | after |
|---|---:|---:|
| positions with a recoverable config | 193 | **240** of 274 |
| replayable days | 22 | **27** |
| accounts visible | 4 of 6 | **6 of 6** |

Also closed: the OPRA bar gap is now **zero** (5 contracts fetched, incl. all of today's —
same-day OPRA fetch works, contradicting the earlier "can't replay today" claim).
The 34 rows still dark lack a `PLACED` row in any ledger.

**Fidelity, checked before admitting anything** (the anchor's own bar is "error must not be
systematically one-directional"):

| source | n | bias/pos | median abs err | sign agree |
|---|---:|---:|---:|---:|
| fleet (recorded placement block) | 193 | −$7.4 | $17.6 | 80% |
| core (reconstructed) | 47 | −$13.2 | $99.0 | 74% |

Core rows are **noisier but not biased differently** — same sign, same conservative direction.
Diagnosis: not a reconstruction defect. `core:explicit` and `core:derived` rows have an
*identical* 41% relative error, and all 36 core rows carry `exit_managed: true`, so
`exit_manager` genuinely ran. The noise is **scale**: core trades ATM (~$0.90/contract) vs
fleet's OTM (~$0.32), and `fill_mode="extreme"` punishes high-gamma contracts harder.
**Admissible for A/B; per-position core claims need wider error bars.**

Guards: `backtest/tests/test_core_placement_recovery_2026_08_11.py` (7, RED-proofed — re-blinding
the harness fails 4). Blast radius on the live trading path: **zero** (research tool only).

---

## 2. Three hypotheses tested tonight. All three died. That is the result.

| # | hypothesis | verdict | evidence |
|---|---|---|---|
| A | Ladder should be un-scoped to all strategies (J challenge) | 🔴 **NO-SHIP** | VWAP cohort n=25: **−$411**, 0 days helped, 100% of damage on the 08-04 trend day. All 4 prereg gates fail. On chop it never arms (positions die below the +50% rung). |
| B | The ladder helps bulls and hurts bears (post-hoc, from the newly-visible data) | ⚪ **NOISE** | Day-clustered bootstrap 10k: BULL +$1,545 95% CI **[−985, +4260]** p=0.12; BEAR −$794 CI [−3662, +2123] p=0.70. Both straddle zero. **Shipped nothing.** |
| C | The marginal (Nth) trade of a day is negative-expectancy | ⚪ **NO EFFECT** | Broker P&L, n=274: 1st trade mean −$8 / WR 20%; every subsequent −$5 / WR 19%. Flat. Trade sequencing is not a lever. |

Ladder on the full 240-position population: **+$340 over 27 days, helped 9 / hurt 8** — still a
wash, unchanged by 24% more data. It stays armed on ribbon (no evidence to remove it), stays
off VWAP (evidence to keep it off).

### The PDT question, answered
68 `RISK_DENY_PDT` refusals over 9 days (18 unique intents) — the largest block of trades the
engine wanted and never took. Priced at logged qty/premium on real OPRA through `exit_manager`:

**Net −$62. 13 of 18 were losers. 2 green days vs 7 red. All 4 gates FAIL.**

🔒 **PDT stays exactly as-is.** The self-imposed paper constraint was mildly *protective*, not
costly. Filed as a closed question rather than a standing "what if".

---

## 3. What actually changed: the engine crossed breakeven in August

Broker-realized, per era — the number that matters:

| era | n | net | green days | WR | avg win | avg loss |
|---|---:|---:|---:|---:|---:|---:|
| Jun 26 – Jul 17 | 147 | −$1,289 | 2/13 | 10.9% | +$119 | −$24 |
| Jul 20 – Jul 31 | 36 | −$617 | 2/9 | 27.8% | +$158 | −$84 |
| **Aug 03 – Aug 11** | **91** | **+$286** | **4/7** | **29.7%** | **+$312** | **−$127** |

**The breakeven line:** avg win $312 / avg loss $127 = **2.45× ratio → breakeven WR = 29.0%.
Actual = 29.7%.**

📌 We are **0.7 percentage points above breakeven.** That is the honest position: the engine is
no longer losing (WR nearly tripled from 10.9%), but the margin is *razor thin* — a single bad
day flips the sign, and drop-best on August is still −$3,338. This is not "profitable"; it is
"first era that isn't negative, with no cushion."

Per-arm, August:

| arm | n | net | green | WR | avg loss |
|---|---:|---:|---:|---:|---:|
| safe-2 | 17 | +$316 | 4/7 | 35.3% | −$98 |
| bold-2 | 7 | +$216 | 2/3 | 28.6% | −$139 |
| risky-1 | 26 | +$130 | 3/7 | 26.9% | −$119 |
| risky-3 | 28 | +$46 | 5/7 | 28.6% | −$139 |
| **safe-3** | 13 | **−$422** | 2/4 | 30.8% | **−$147** |

**safe-3 is the only negative arm — and not because of win rate** (30.8% is above the book).
Its average loss is the worst on the book at −$147. That is a loss-size problem, not a
selection problem, and it is a specific, falsifiable next question.

---

## 4. What this means for the work map

Every exit-shape knob tested to date is a wash or worse; the constraint is a **0.7pp margin**
above breakeven. Two levers move a razor-thin margin, in priority order:

1. **Cut average loss** (currently −$127 book-wide, −$147 on safe-3). Each $10 off the average
   loss moves breakeven WR down ~0.6pp. This is where safe-3's investigation goes.
2. **Regime selection** — still the #1 lever (P1/ER30, forward clock 0/25). Chop days are where
   the losses cluster and where every fixed exit shape fails.

Explicitly NOT levers, now measured: exit-ladder tuning, ladder scope, PDT, trade sequencing.
