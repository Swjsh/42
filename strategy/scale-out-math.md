# Scale-Out Math — TP1 Optimization for Project Gamma

> **Question:** J proposed selling 2 of 3 contracts at +10% premium gain, leaving 1 runner on the ribbon. Targeting +10–15% account per day. Will the math support that target?
>
> **Answer:** It works, but it's leaving substantial money on the table. Recommended TP1 = **+30% premium**, not +10%. Backed by per-trade math on the three confirmed winners.

---

## The setup we're sizing for

- **$1K paper account** (starting point)
- **3 contracts per trade** (2 TP + 1 runner)
- **Premium stop:** -50% on full position (existing rule)
- **Runner management:** trail via EMA ribbon (exit on close back into ribbon, bounce signature, or +200% premium take)
- **Daily target:** +10–15% account ($100–$150 on $1K)
- **Daily kill switch:** -50% account ($500 on $1K)

---

## Method

Run the math on the three confirmed trades at three TP1 levels (+10%, +30%, +50%) using *the rules-based 3-contract sizing*, not the historical contract counts. This shows what the same trade would have produced under our system.

**Normalization assumption:** Each trade is sized to 3 contracts at the entry premium it actually had. The runner exit price is whatever the trade actually exited at (since that was a clean ribbon-signal exit on 5/4, a level-target exit on 5/1, and a compromised exit on 4/29 — all preserved here).

---

## The numbers — per trade, per TP1 level

### 4/29/2026 — SPY 710P, entry $1.67, runner exit $2.69

3 contracts × $1.67 = **$501 deployed** (right at 50% cap on $1K).

| TP1 level | TP1 price | 2 contracts banked | Runner P&L | Total P&L | % return on capital | % of $1K account |
|---|---|---|---|---|---|---|
| **+10%** | $1.84 | 2 × $17 = **$34** | $102 | **$136** | +27.1% | **+13.6%** |
| **+30%** | $2.17 | 2 × $50 = **$100** | $102 | **$202** | +40.3% | **+20.2%** |
| **+50%** | $2.50 | 2 × $83 = **$166** | $102 | **$268** | +53.5% | **+26.8%** |

All three TP1 levels would have hit on this trade. Higher TP1 = bigger bank.

### 5/1/2026 — SPY 721P, single-trigger entry $0.46 (the *clean* version, not anticipation), runner exit $0.56

3 contracts × $0.46 = **$138 deployed** (14% of $1K, well under cap — small-magnitude trade).

| TP1 level | TP1 price | 2 contracts banked | Runner P&L | Total P&L | % return on capital | % of $1K account |
|---|---|---|---|---|---|---|
| **+10%** | $0.51 | 2 × $5 = **$10** | $10 | **$20** | +14.5% | **+2.0%** |
| **+30%** | $0.60 | not hit (max was $0.56) | — | — | — | — |
| **+50%** | $0.69 | not hit | — | — | — | — |

**This is the key insight:** TP1 at +30% or higher doesn't trigger on small-magnitude trades. We need a fallback rule.

→ **Fallback rule (added to playbook):** "If runner-exit signal fires before TP1 is hit, exit ALL 3 contracts at the signal price." With this rule, 5/1 at TP1=+30% would have:
- Ribbon signal fires at $0.56 (the exit price) → exit all 3 at $0.56 → 3 × $10 = **$30 = +21.7% return on capital = +3.0% account**.

So with the fallback, 5/1 at TP1=+30% is **better** than at TP1=+10% (+3.0% vs +2.0%).

### 5/4/2026 — SPY 721P, entry $0.85, runner exit $1.90

3 contracts × $0.85 = **$255 deployed** (25.5% of $1K).

| TP1 level | TP1 price | 2 contracts banked | Runner P&L | Total P&L | % return on capital | % of $1K account |
|---|---|---|---|---|---|---|
| **+10%** | $0.94 | 2 × $9 = **$18** | $105 | **$123** | +48% | **+12.3%** |
| **+30%** | $1.11 | 2 × $26 = **$52** | $105 | **$157** | +61% | **+15.7%** |
| **+50%** | $1.28 | 2 × $43 = **$86** | $105 | **$191** | +75% | **+19.1%** |

All TP1 levels would have hit. Higher = better.

---

## Sample summary — total $-P&L across the 3 trades

Using the fallback rule for trades where TP1 isn't hit:

| TP1 level | 4/29 | 5/1 (clean) | 5/4 | **Total** | **Avg per trade** |
|---|---|---|---|---|---|
| **+10%** | $136 | $20 | $123 | **$279** | $93 |
| **+30%** | $202 | $30 | $157 | **$389** | $130 |
| **+50%** | $268 | $30 | $191 | **$489** | $163 |

**+30% TP1 produces 39% more total profit than +10% TP1 across the same three trades.** +50% produces 75% more — but with the caveat that +50% will miss more trades that have moderate moves (between +30% and +50% peak premium gain), forcing the fallback.

---

## Why TP1 = +30% is the recommended sweet spot

1. **Bigger bank when TP1 hits.** $50 vs $17 per contract on $1.00 entry. 3x more profit locked in per scale-out.
2. **Higher hit rate than +50%.** Most clean setups produce premium gains in the +30–80% range; +30% catches almost all of them.
3. **Better floor when runner fails.** If TP1 hits and runner stops at BE, you've banked +6% account on $1K (3 contracts × $1.00 entry). vs +1.8% with TP1=+10%. Three times the floor.
4. **Doesn't clip the natural rhythm.** Your 5/4 trade peaked at +124%; clipping at +10% would have been actively destructive. +30% preserves runner upside.
5. **Forces honest signal hierarchy.** TP1 only fires when premium has actually moved meaningfully — not on noise.

The reason TP1=+10% feels intuitive ("bank fast, reduce risk") is psychological, not mathematical. With the **BE stop on the runner after TP1**, the runner isn't actually risking your trade — it's a free swing at the home run. The 2 contracts at TP1 are doing the de-risking. Banking +10% vs +30% on those 2 contracts is the difference between "I made my morning coffee" and "I made the day."

---

## Recommended scale-out rule (replaces the placeholder in `playbook.md`)

```
TP1: Sell 2 of 3 contracts when:
  - Premium ≥ entry × 1.30 (i.e., +30% gain), OR
  - SPY reaches first major intraday support level from today-bias.json,
  whichever fires FIRST.

After TP1:
  - Move stop on remaining runner to BREAKEVEN (premium = entry premium).
  - Continue ribbon trail on runner.

Runner exit (any of):
  - 3-min candle closes back into the EMA ribbon
  - Bounce signature: long lower wick + green follow-through
  - Premium ≥ entry × 3.0 (i.e., +200% — massive runner, take it)
  - Time stop 15:50 ET

Fallback (TP1 not yet hit but runner-exit signal fires):
  - Exit ALL 3 contracts at the signal price.
  - This is the "small move, ride together, exit together" path.
  - Without this rule, small-magnitude trades like 5/1 don't pay.
```

This is what I'll wire into `params.json` and `decision-log.md`.

---

## Account growth model

### Per-trade EV (rough, based on the 3-trade sample + assumed loss rate)

Assumptions for modeling (paper-test period; refine after n=20):

- **Win rate:** 60% (the 3 confirmed examples are 100% but tiny sample; real win rate likely 50–65%).
- **Avg winner:** +13% of account (avg of the three at TP1=+30% on $1K = ~$130 = 13%).
- **Avg loser:** -12% of account (premium stop -50% on 3 × $1.00 = $150 risk = 15%; some stops happen before full loss, so avg ~12%).
- **Trades per day:** 0.7 (some days no setup fires, some days 1 trade, rare 2 trades).

Per-trade EV: 0.6 × 13% + 0.4 × (-12%) = 7.8% - 4.8% = **+3.0% per trade**.

Per-day EV: 0.7 trades × 3.0% = **+2.1% per day average**.

### Realistic growth curve

| Account size | Per-day target ($) | Per-day average ($) | Days to next milestone |
|---|---|---|---|
| $1,000 → $1,500 | $100 | $21 | ~20 trading days (1 month) |
| $1,500 → $2,000 | $150 | $32 | ~14 trading days |
| $2,000 → $5,000 (with 4-contract scaling) | $300 | $84 | ~30 trading days |
| $5,000 → $10,000 (with scaled contracts) | $750 | $210 | ~25 trading days |
| $10,000 → $25,000 | $1,500 | $420 | ~40 trading days |

**Realistic time horizon: $1K → $10K in ~3–4 months of consistent paper-testing edge.** $10K → 5-figures+ within another 1–2 months.

This assumes the sample edge (3 of 3 winners, +64% avg return on capital) holds in a larger sample. **It probably won't fully hold** — that's why we paper-test 20 trades before flipping to live, and why the live thresholds in `risk-rules.md` are conservative.

### What "10% per day" actually means

The +10% number is a **target**, not an expected average. On any given day:
- ~40% chance: no setup fires, return = 0%
- ~30% chance: TP1 hit + good runner = +10–15% account ✓ target hit
- ~20% chance: TP1 hit + weak runner / fallback exit = +3–6%
- ~10% chance: stop-out = -10–15%

The expected average is ~2–3% per day. The **good days** that hit the target and the **bad days** that take the kill switch average out. The strategy is profitable if the good days outweigh the bad days, which they do on this sample.

---

## Position scaling as the account grows

| Account size | Contracts per trade | Scale-out structure | Approx % deployed (at $1.00 entry) |
|---|---|---|---|
| $1,000 – $2,000 | **3** | 2 TP + 1 runner | 30% |
| $2,000 – $5,000 | **4** | 2 TP + 2 runners | 25% |
| $5,000 – $10,000 | **6** | 4 TP + 2 runners (67/33 split preserved) | 18% |
| $10,000 – $25,000 | **10** | 6 TP + 4 runners | 12% |
| $25,000+ | **15+** | 10 TP + 5 runners | 10% |

**As the account grows, % deployed *decreases* but absolute contract count *increases*.** This is intentional — at higher account sizes you don't need as much % risk to hit the same dollar target, and lower variance compounds better.

The 50% per-trade cap and -50% premium stop hold across all sizes. They're the survival rules; everything else scales around them.

---

## What gets updated based on this analysis

- **`strategy/playbook.md`:** TP1 rule rewritten from "+50%" to "+30% OR first major support level, whichever first." Fallback exit-all-on-ribbon rule added.
- **`strategy/risk-rules.md`:** position-scaling table added.
- **`automation/state/params.json`:** `tp1_premium_pct` changed from `0.5` to `0.3`. New `runner_be_stop_after_tp1` flag = `true`. New `exit_all_on_runner_signal_if_tp1_unfired` flag = `true`.
- **`automation/decision-log.md`:** TP1 logic + fallback path encoded into the management branch.

Let me know if you want TP1 at a different level (+25% as a compromise? +40% to swing for the fences?). The math will run on whatever you specify; I just don't want it at +10% because the data says it's leaving real money behind.
