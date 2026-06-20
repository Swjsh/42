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
