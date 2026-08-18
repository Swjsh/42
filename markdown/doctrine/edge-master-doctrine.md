# Edge Master Doctrine — 4/29 + 5/04 Patterns

> Generated 2026-05-10. The two trades the engine BEATS J on. Together: J=$1,072 → engine=$2,790 (260% capture). This file freezes the patterns so future tuning never breaks them.
>
> **Don't tune away from these. Anything that regresses 4/29 or 5/04 is rejected, no exceptions.**

---

## 4/29 — TRENDLINE-then-LEVEL escalation pattern

### J's actual trade
- 0DTE SPY 710P × 6 contracts
- Entry near 10:25 ET (711.4 rejection on a wick + ribbon flip)
- Result: **+$342**

### Engine's BEAT-J replication (+$372 net, 109% of J)

**Trade 1 (TRENDLINE, scratch loss)**
- Time: **12:10 ET**
- Strike: P710, qty=3, entry premium $0.998
- Trigger: `['trendline_rejection']` only
- Quality tier: `TRENDLINE`
- Stop: -8% premium → **stops at $0.918, -$24 loss**
- Hold: 5 minutes
- Why this matters: the SCRATCH stop is by design. It clears the escalation lock so a higher-quality trigger can fire later.

**Trade 2 (LEVEL, the win)**
- Time: **12:25 ET**
- Strike: P710, qty=22, entry premium $1.201
- Trigger: `['level_rejection']` at 710.0
- Quality tier: `LEVEL` (qty=22)
- TP1: $1.561 at 12:30 (5min), filled 50% qty at +30% premium
- Runner exit: BE stop at $1.201 → **+$396**
- Hold: 15 minutes
- Max favorable: $1.690 (+41%)
- Max adverse: $1.093 (-9%)

### The DOCTRINE behind 4/29

| Mechanism | Why | Risk if changed |
|---|---|---|
| TRENDLINE quality_stop = -8% | Forces fast scratch on weak triggers so escalation can fire | Wider stop holds Trade 1 open through Trade 2's window → blocks the win |
| Per-day quality escalation lock | Allows LEVEL > TRENDLINE rank to break the lock | Without lock, the day churns on multiple TRENDLINE entries that net to zero |
| LEVEL qty = 22 | Big size on the high-quality re-entry | Smaller qty makes 4/29 a marginal +$30, not a meaningful BEAT |
| TP1 +30% / runner BE stop | Locks profit; runner trails to BE | Wider TP misses the win (peak was only +41%) |

### Knob ranges that PRESERVE 4/29

- TRENDLINE quality_stop: **-6% to -10%** (anything wider blocks LEVEL re-entry)
- LEVEL qty: **18-25** (lower kills the win magnitude; higher likely fine)
- LEVEL stop: **-8% to -12%** (saw -10% works; tighter would stop on max_adv -9%)
- LEVEL TP1: **+25% to +40%** (max favorable was +41%, so tighter than +40% is required)

### Knob ranges that BREAK 4/29

- TRENDLINE OTM-2 forcing → entry P708 instead of P710 → +$60 instead of +$372 ❌
- TRENDLINE quality_stop -25% or wider → +$60 instead of +$372 ❌
- LEVEL TP1 > +50% → never hits, runs to time stop ❌

---

## 5/04 — CONFLUENCE-CRUSH pattern (the seed10095 doctrine win)

### J's actual trade
- 0DTE SPY 721P × 10 contracts
- Entry around 10:30 ET on premarket level rejection + multi-day descending trendline + EMA ribbon flip = full CONFLUENCE
- Result: **+$730**

### Engine's CRUSH-J replication (+$2,418 net, 331% of J)

**Trade 1 (ELITE, designed scratch)**
- Time: **10:05 ET**
- Strike: P720, qty=10, entry premium $1.267
- Trigger: `['level_rejection', 'confluence']` at 720.67
- Quality tier: `ELITE`
- Stop: -15% premium → **-$190 loss at 10:10**
- Hold: 5 minutes
- Why this matters: just like 4/29, the early ELITE scratch primes the escalation lock so SUPER can supersede.

**Trade 2 (SUPER, the CRUSH)**
- Time: **11:15 ET**
- Strike: P719, qty=15, entry premium $1.304
- Trigger: `['level_rejection', 'ribbon_flip', 'confluence']` (3 triggers = SUPER)
- Quality tier: `SUPER` (caller doctrine: -20% stop, +75% TP1, runner=2x)
- TP1: $2.282 at 11:50 (35 min in), filled 50% qty at +75%
- Runner exit: TARGET hit at $3.912 (premium 2x×$1.304=$2.608+ above entry, runner ran to target)
- Hold: 50 minutes
- Max favorable: **$4.095 (+214%)**
- Max adverse: $1.277 (-2% only)
- Net: **+$2,608**

### The DOCTRINE behind 5/04

| Mechanism | Why | Risk if changed |
|---|---|---|
| SUPER tier (n_triggers≥3 OR confluence+ribbon_flip) | Identifies highest-conviction setups for max position | Without SUPER, 5/4 wouldn't get qty=15 + doctrine knobs |
| SUPER caller doctrine: stop=-20% | Wide stop survives the inevitable -2-12% intraday wobble before runner | Tight stops scratch this trade for nothing |
| SUPER TP1 +75% | Captures the meat (peak was +214%), leaves runner | Tighter TP1 (+30%) leaves $1,000+ on the table |
| Runner target = 2x premium | Runner rides to systematic target | Removing runner cuts the CRUSH P&L by ~50% |
| Per-day escalation lock with SUPER>ELITE rank | Allows SUPER to supersede the earlier ELITE stop | Without it, 5/4 would only get the -$190 ELITE scratch |
| BS sim respects strike_offset | Strike picker honors the param | Pre-2026-05-09 bug had sim hardcoded ATM, invalidating all research |

### Knob ranges that PRESERVE 5/04

- SUPER stop: **-15% to -25%** (max_adv was -2%, so tight stops survive too — but doctrine -20% is the proven knob)
- SUPER TP1: **+50% to +100%** (peak was +214%, so any TP1 in this range fills well below max)
- runner_target_premium_pct: **1.5x to 3.0x** (runner peaked at +214%; 2x = $2.608 above entry which is what fired)
- SUPER qty: **10-20** (15 proven; need risk-cap math for higher)

### Knob ranges that BREAK 5/04

- SUPER stop tighter than -10% → scratches on the -12% intraday wobble before runner ❌
- TP1 < +30% → fires too early on partial fill, loses runner upside ❌
- Removing escalation lock → ELITE Trade 1 locks day, no SUPER entry ❌

---

## Cross-pattern principles (what 4/29 + 5/04 BOTH teach)

1. **Early scratch is a feature, not a bug.** Both winning days START with a losing trade that fires escalation. The TRENDLINE/ELITE early entry is the cost of admission for the LEVEL/SUPER win.

2. **Quality tier maps directly to qty + stop + TP1.** A unified knob set per tier (not global) is what makes both days work. SUPER knobs would scratch 4/29's TRENDLINE; TRENDLINE knobs would scratch 5/4's SUPER win.

3. **Escalation lock is mandatory.** Without it, the day churns. Naive "first entry per day" tried 2026-05-09 and broke 5/4. The lock must be quality-gated, not time-gated.

4. **Max favorable / max adverse asymmetry is the edge.** 5/04 SUPER: +214% favorable, -2% adverse. That asymmetry is what 0DTE puts deliver when the setup is right. Tuning that suppresses upside (tight TP1, narrow runners) loses the edge.

5. **Wide intraday wobble tolerance on SUPER is non-negotiable.** 5/04 went -12% before reversing. -8% stop kills it. -20% rides it.

---

## What we DO NOT have edge on yet (don't pretend we do)

- **5/01:** engine takes the same 13:35 trendline bar but BS sim + ribbon data divergence prevent profit. Loss bounded to -$22. Real OPRA fill or TV-aligned data feed required to close.
- **5/05/06:** SKIP is correct (J lost on these). Engine never enters. ✓
- **5/07:** engine bear-shorts both J's losing call setups for +$74×2. Bonus, not core edge.

---

## STAGE 3 LEARNINGS (2026-05-10 afternoon discovery — $12k→$19k)

The stage-3 grinder pushed wide_pnl from $12,105 (stage 2 best) to **$19,627** (+62%) with only TWO knob changes from the prior winner:

| Knob | Stage 2 best | Stage 3 best | What this taught us |
|---|---|---|---|
| `level_qty` | 25 | **28** | LEVEL-tier handles +12% size without breaking; per-trade risk cap is the binding constraint, not signal quality |
| `level_stop` | -12% | **-14%** | -12% stop was firing on intraday noise wobbles; -14% lets winning trades survive the wiggle and reach TP1 + BE runner |

### Why this matters for refinement

**The -12% LEVEL stop was a noise filter, not a risk filter.** Many LEVEL trades that ultimately won were getting stopped on a 0.5-bar pullback before the real move developed. Each spurious stop = ~$200-300 loss on qty=22-25. Across 16 months, those add up.

**Implication for stage 3.5 or future grinder:** explore even wider LEVEL stops (-15%, -16%, -17%) to see if the "stop just past noise" range continues. There's likely a global maximum around -14% to -16% before the stop becomes meaningless.

### Hard ceiling analysis

LEVEL qty=28 at typical $1.20 entry premium = $3,360 capital per trade. Real-account constraints:
- $1K paper account (current): per-trade risk cap = $500 → MAX qty=4 contracts (regardless of grinder findings)
- $5K live account: cap=$2,500 → MAX qty=20
- $25K+ account: cap unlimited at qty=28

**Translation:** the grinder is finding the OPTIMAL strategy for a $5-25K+ account. On the current $1K paper account, the engine's actual sizing is limited by the cap, NOT by the grinder. The grinder's wide_pnl is "what we'd capture at scale" — current paper P&L is a fraction of that until equity grows.

### Diminishing returns trajectory

| Iteration | wide_pnl | absolute gain | gain % |
|---|---|---|---|
| Baseline | $3,655 | — | — |
| Stage 1 best | $12,105 | +$8,450 | +231% |
| Stage 2 best | $12,105 | +$0 | +0% |
| **Stage 3 best (so far)** | **$19,627** | **+$7,522** | **+62%** |

Each stage finds smaller absolute gains as we narrow the search. Realistic ceiling estimate: **~$25-30k wide_pnl** before the strategy hits structural limits (signal frequency, market microstructure).

## Sweep targets for overnight grinder

Vary these knobs **only within the preserve ranges above** to find combinations that:
1. Maintain or improve 4/29 + 5/04 capture
2. Improve aggregate P&L over 2024-2026 historical window
3. Don't add losers on 5/05 / 5/06

Known good baseline (locked floor — never regress below this):
- 4/29: +$372
- 5/04: +$2,418
- edge_capture: +$2,769
- losers_added: $0

---

## J-edge source-of-truth trades

> Relocated verbatim from CLAUDE.md OP-16 (2026-07-16 context-leanness fold). This is the full
> immutable trade list behind the `edge_capture` gate; CLAUDE.md keeps only the formula +
> threshold inline and points here for the underlying trades.

**Source-of-truth trades (immutable until J adds more):**
- **Winners (engine MUST take):** 4/29 SPY 710P × 6 → +$342 | 5/01 SPY 721P × 20 → +$470 | 5/04 SPY 721P × 10 → +$730
- **Losers (engine MUST skip or lose less):** 5/05 SPY 722P × 20 → −$260 | 5/06 SPY 730P × 10 → −$300 | 5/07 SPY 734C × 3 → −$45 | 5/07 SPY 737C × 10 → −$120

**J-edge score:** `edge_capture = sum(engine_pnl_on_winning_days) - sum(max(0, engine_loss_on_losing_days))`
Max possible: 1542. Candidates with edge_capture < 771 (50%) are REJECTED regardless of aggregate. `final_score = edge_capture × aggregate_sharpe`. Aggregate Sharpe/P&L are secondary tiebreakers only.

**Sim accuracy gate:** verify sim's strike picker matches production (`strike_offset`) before ratification — BS-sim-ignored-strike-offset incident invalidated a weekend of research.

**Setup scope = BOTH directions (UNLOCKED 2026-06-28)** — relocated verbatim from CLAUDE.md OP-16 (2026-08-16 context-leanness fold). Direction is NOT a scope, *validation* is. BEARISH_REJECTION + BULLISH_RECLAIM_RIDE_THE_RIBBON both ACTIVE, identical placement path (`enable_bullish=True`). Bull evidence corrected 2026-07-11: old +$5,586/56% WR was a real-OPRA SIM, not broker fills; live paper fills bull n=80 WR 1.2% -$1,573 (9-day, VIX pinned, small-n) — stays enabled pending honest re-eval at n≥20 under SS-B + corrected strike tier (detail: PROFITABILITY-DEEP-RESEARCH-2026-07-11.md). Per-direction block-filters stay ON (A/B-validated per losing cohort; winner = NON-ribbon_flip BULLISH_RECLAIM; detail → C22). Guards: `test_enable_bullish_live_true` + `test_enter_bull_in_placement_path`. **Live-money arming of EITHER direction needs J (OP-0 #1); paper/shadow does not.**

---

## The ENGINE's realized edge — 424 fills, 102 waves, 39 sessions (folded 2026-08-18)

> Everything above this line is **J's anchor trades** — a handful of exceptional manual setups the
> engine is scored against. This section is the other half: what the ENGINE'S OWN realized-fills
> population says its edge is. Living surface, regenerated by
> [`setup/scripts/winner_signature.py`](../../setup/scripts/winner_signature.py) →
> [`analysis/winner-autopsies/SIGNATURE.md`](../../analysis/winner-autopsies/SIGNATURE.md) +
> `signature.json`. Guards: `backtest/tests/test_winner_signature.py` (31, RED-proofed).
> Companion instrument: `winner_autopsy.py` answers the EXIT question (how much of what our winners
> offered did we keep); this one answers the ENTRY/REGIME/SHAPE question.

**The honest denominator is 102 waves, not 424 fills.** Up to six arms consume ONE shared signal
and enter the same impulse seconds apart, so per-trade buckets carry ~4× their apparent evidence.
Wave WR is **24%** — three of every four impulses we commit to lose money — against a 30.0% trade WR.

### 1. What the edge IS

**Every dollar we have ever made came from an exit at ≥1.3× entry premium.** Those 96 fills (23% of
the book) carry **$17,067**; every band below 1.3× is net negative, including the one that closed at
a nominal small profit. The 2× club is 35 fills (8%) worth $6,184 — median hold **43 min**, median
entry premium **$0.84**, concentrated on 10 sessions.

> **The edge in one line: a near-the-money contract given room to run through a real impulse.**
> Not a win rate. A right-tail. This is a positive-skew architecture and it must be judged as one.

### 2. What the bleed IS — and what it is NOT

The median LOSING exit is **0.82× entry (≈−18%)**, nowhere near the −50% catastrophe cap. We are not
being killed by disasters; we are being nibbled to death by a high count of small, fast
invalidations — the trigger firing into impulse ATTEMPTS that get absorbed rather than run. Fills
held <10 min are net **−$4,741**. (⚠ hold time is an OUTCOME, not a lever — a stop-out is short
BECAUSE it lost. It describes the bleed; it cannot filter it.)

### 3. The regime finding — and why it cannot become a pre-open gate

Realized day range is the strongest correlate of session P&L in the data (**r = +0.42**):

| realized day range | sessions | total | green |
|---|---:|---:|---:|
| <0.5% | 5 | **−$3,853** | **0/5** |
| 0.8–1.2% | 14 | −$1,914 | 3/14 |
| 1.2%+ | 7 | **+$5,001** | 5/7 |

**And it is pure look-ahead.** Every pre-open proxy for it fails: ATR14-prior r=−0.11 vs day P&L,
VIX-open r=+0.04, |gap| r=−0.15. **The day cannot be pre-selected** — so the lever cannot be a
pre-open gate. It has to be intraday feedback.

### 4. The gap this opened — Rule 5 has never been reachable

Across **105 arm-days** with recorded equity, the P&L distribution is worst **−24.4%**, p10
**−10.1%**, median **−2.1%**. Rule 5 halts Safe at **−30% of start-of-day equity**. *No arm-day has
ever reached it.* The kill switch is calibrated to account destruction, not to the loss distribution
it actually governs — so in practice the engine runs with **no daily throttle at all**, and keeps
re-firing into an absorbing tape until 15:55.

A per-arm intraday realized-loss throttle improves the in-sample book at **every** setting tested
(−1% → −10% of SoD equity; nine of nine beat no-throttle; baseline −$668 → +$291…+$2,116). Surviving
its own knob sweep is what makes it worth a forward window — **but the in-sample delta lives in ~4 of
39 sessions**, so nothing is armed. Frozen as
[`day-throttle-forward-prereg-2026-08-18.json`](../../analysis/recommendations/day-throttle-forward-prereg-2026-08-18.json)
— SHADOW ONLY, 15-session window, F4 (survives dropping the best session) is the gate it would fail today.

### 5. The trap — do not re-discover and ship this

**Ribbon width (`spread_cents`) filtering is survivorship, not edge.** Cutting entries with ribbon
width ≥40¢ turns the entire book positive, which is why it is the most seductive number in the
study. It also removes ~81% of the population and kills **18 of the top-25 winners**. It is a
trend-EXTENSION measure, not a bid-ask spread. Logged here and in the pre-reg's `what_this_is_NOT`
so the next session does not find it again and act on it. (C4/C14 shape: a filter that looks
devastating because it selected the survivors.)

### 6. Entry-side buckets that did NOT survive

Tested at wave level and rejected as levers: VIX band (no monotone edge), side C vs P (24% wave WR
both), setup, trigger set, hour-of-day (11:xx is 7% wave WR / −$2,373 but survives
mostly as a proxy for midday absorption, and a gate there already exists). Entry premium <$0.30 is
0-for-19 waves / −$787 — real but small, already largely extinct after the fleet strike-tier fix,
and it is a strike-selection defect rather than an edge.

### 7. A worked example of why the WAVE denominator is doctrine, not pedantry

`quality` ELITE-vs-BASE, scored both ways on the same population:

| denominator | ELITE | BASE | reads as |
|---|---|---|---|
| per trade | n=209, 27% WR, **−$653** | n=93, 35% WR, −$414 | "ELITE is anti-predictive" |
| per wave | 31 waves, 23% WR, **+$1,180** | 20 waves, 15% WR, **−$1,503** | "ELITE is the better label" |

**The sign flips.** ELITE waves recruit more arms, so the per-trade view over-weights whichever
ELITE waves happened to lose. Any conclusion drawn from the per-trade row here is an artifact of
correlated arms, not a property of the label. This is the whole reason `winner_signature.py` prints
waves as the headline — and it caught a wrong claim in the first draft of this very section.

### 8. How this gets audited (the standing loop, not a one-off)

| organ | fires | asks |
|---|---|---|
| `Gamma_WinnerAutopsy` → `winner-autopsies/all.md` | 16:25 ET | how much of what our winners offered did we KEEP? (exit) |
| `Gamma_WinnerSignature` → `winner-autopsies/SIGNATURE.md` | 16:32 ET | what does our money LOOK LIKE? (entry / regime / shape) |
| `Gamma_DayThrottleShadow` → `day-throttle-shadow-summary.json` | 16:35 ET | is the one live hypothesis surviving its forward window? |

The third one exists because a pre-registration that nothing computes is prose, and prose
never adjudicates itself (C35/L221 shape — a falsification promise sitting unwired). It
recomputes `would_block` per fill AFTER the close from `journal/trades.csv` rather than
instrumenting the 1-minute tick: identical evidence, and a crash in the counter can never
touch a trade. Its `forward` block is the ONLY thing that can clear a gate; `in_sample_reference`
is printed for drift-checking and is barred by construction from clearing anything.

**The window opens the first session after 2026-08-18 and needs 15 sessions.** Until then the
correct reading of every number in §1–§7 is *hypothesis*, and the correct action is none.
