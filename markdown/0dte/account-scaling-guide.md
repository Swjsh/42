# Account Scaling Guide — Project Gamma

> **Status:** TEMPLATE — populated with empirical data after 20+ live trading days per account (target: ~4 weeks post-2026-05-18)
> **Updates:** Every Sunday weekly review appends a new data row to each table below.
> **Source data:** `journal/trades.csv` filtered by `account_id` · `automation/state/equity-curve.json`
> **Doctrine:** [`markdown/0dte/dual-account-design.md`](dual-account-design.md) | [`markdown/0dte/risk-rules.md`](risk-rules.md)

---

## Purpose

This guide answers the questions no backtest can reliably answer:

1. **At $1K: 30% or 50% risk per trade?** Which compounds better after real fills and real emotions?
2. **ATM or ITM-2?** Which strike family produces better expectancy net of slippage at the $1K tier?
3. **+30% or +75% TP1?** Which produces better WR-adjusted P&L over 20+ trades?
4. **When to size up?** What account level, WR, and streak criteria trigger the move from 3→5 contracts?
5. **Live deployment readiness:** Which account earns the 45%+ WR / positive expectancy threshold first?

The answers come from the dual-account experiment running on both Gamma-Safe and Gamma-Bold simultaneously starting 2026-05-18.

---

## Tier Structure

### Current Tiers (as of v15, ratified 2026-05-13)

| Account Equity | Base Contracts | Elite Contracts | Notes |
|---|---|---|---|
| $0 – $2,000 | 3 | 3 | Capital constraint. 2 TP1 + 1 runner. |
| $2,000 – $10,000 | 5 | 8 | 3 TP1 + 1 conservative + 1 aggressive runner |
| $10,000 – $25,000 | 10 | 15 | 6 TP1 + 2 conservative + 2 aggressive runners |
| $25,000+ | 10 | 15 | PDT-eligible. Live deployment threshold. |

**Scale-up rule:** Account must CLOSE above the tier threshold for ≥3 consecutive trading days before upsizing. Prevents whipsaw on a single outsized winner.

**ELITE qualifier:** trigger set includes confluence OR sequence_rejection/reclaim. BASE = otherwise.

### Sizing Math Reference

#### Gamma-Safe (ATM, 30% risk cap)

| Entry Premium | Max Contracts (30% of $1K = $300) | Capital Deployed | Notes |
|---|---|---|---|
| $0.50 | 6 → cap at 5 | $250 | Under cap, capped at tier max |
| $0.75 | 4 | $300 | Fits exactly |
| $1.00 | 3 | $300 | Minimum floor |
| $1.50 | 2 → skip (below min-3) | N/A | Premium too rich; wait or skip |
| $2.00 | 1 → skip | N/A | Way above per-trade cap |

#### Gamma-Bold (ITM-2, 50% risk cap)

| Entry Premium | Max Contracts (50% of $1K = $500) | Capital Deployed | Notes |
|---|---|---|---|
| $0.75 | 6 → cap at 5 | $375 | Under cap, capped at tier max |
| $1.00 | 5 | $500 | Fits exactly |
| $1.50 | 3 | $450 | Minimum floor satisfied |
| $2.50 | 2 | $500 | Under min-3 → skip unless sizing allows |
| $3.30 | 1 → skip | N/A | Too rich for $1K account |

**Key difference:** At ITM-2 premiums typically $1.50–$3.00 on 0DTE SPY, Bold often hits the min-3 floor or skips entirely on rich-premium days. That's a feature: Bold self-limits on expensive entries.

---

## Live Performance Tracking

*Populated weekly by Sunday review. First data: week ending 2026-05-24.*

### Gamma-Safe Weekly Scorecard

| Week | Equity ($) | Trades | WR (%) | Avg Win ($) | Avg Loss ($) | Expectancy ($) | Max DD (%) | Rule Breaks |
|---|---|---|---|---|---|---|---|---|
| 2026-05-18 (baseline) | 1,000 | 0 | — | — | — | — | — | 0 |
| *(data after 5/24)* | | | | | | | | |

### Gamma-Bold Weekly Scorecard

| Week | Equity ($) | Trades | WR (%) | Avg Win ($) | Avg Loss ($) | Expectancy ($) | Max DD (%) | Rule Breaks |
|---|---|---|---|---|---|---|---|---|
| 2026-05-18 (baseline) | 1,000 | 0 | — | — | — | — | — | 0 |
| *(data after 5/24)* | | | | | | | | |

### Head-to-Head Comparison

| Metric | Safe | Bold | Winner | Notes |
|---|---|---|---|---|
| Cumulative P&L | — | — | — | *After 20+ trades* |
| Win Rate | — | — | — | *Safe targets high WR; Bold targets high $* |
| Avg Winner $ | — | — | — | *Bold should win here if signals are right* |
| Avg Loser $ | — | — | — | *Safe should lose less per stop* |
| Expectancy per trade | — | — | — | *The number that matters* |
| Max Drawdown % | — | — | — | *Bold expected to be worse* |
| Sharpe (annualized) | — | — | — | *Per-trade normalized* |
| Trades to positive expectancy | — | — | — | *Which reaches the threshold faster* |

---

## Decision Framework: When to Change Tiers

### Size-Up Criteria (3 → 5 contracts)

**All of the following must be true:**
- Account equity ≥ $2,000 for ≥3 consecutive closing days
- Win rate over last 10 trades ≥ 45%
- Expectancy per trade over last 10 trades > 0
- No rule breaks in last 5 trading days
- Gamma confirms in next premarket: "Scale-up criteria met. Tier moving to $2K-$10K: 5 base / 8 elite."

**Do NOT size up because:**
- Had one great trade that pushed equity above $2K
- WR just crossed 45% on a single winning trade
- J wants to "press the advantage"

### Size-Down Criteria (3 → 2 → emergency 1)

If account equity drops below 75% of previous tier threshold, size down to previous tier's qty and **require a 5-trade winning streak to re-qualify**.

Example: Account hits $2,400 → moves to 5-contract tier → drops to $1,400 → size back down to 3 contracts + must win 5 of next 7 before upsizing again.

### Live Deployment Readiness

**Both accounts independently track this checklist:**

| Metric | Threshold | Safe | Bold |
|---|---|---|---|
| Paper trades logged | ≥ 20 | — | — |
| Win rate | ≥ 45% | — | — |
| Avg W / Avg L | ≥ 1.5× | — | — |
| Expectancy per trade | > 0 | — | — |
| Max DD in test period | ≤ 30% of equity | — | — |
| Rule compliance | ≤ 2 breaks across sample | — | — |

First account to clear all 6 thresholds earns the live deployment recommendation. J decides whether to deploy that style, the other, or both.

---

## Scaling Principles (Doctrine)

1. **Never size up after a string of losses.** Compounding a losing streak is how accounts blow up at $25K+ on strategies that worked fine at $1K.

2. **The tier structure is a safety feature, not a growth obstacle.** Staying at 3 contracts while the account doubles from $1K → $2K is correct. The tier moves when the account CONSISTENTLY closes above threshold — not when it spikes there once.

3. **Bold's blowup is data, not failure.** If Gamma-Bold blows up the $1K account in week 2, that's the most valuable data point in the guide: "ITM-2 + 50% risk at $1K blows up in [N] days under [these conditions]." Safe that knowledge.

4. **Real money scales from the safer profile first.** When J moves to live money, start with Safe-equivalent params regardless of which account performs better in paper. The psychological difference between paper loss and real loss is enormous — let the safer profile establish real-money process discipline before loosening parameters.

5. **Sizing follows equity, not conviction.** Strong signals don't justify oversizing. The params.json sizing math runs the same for "obvious" setups as for marginal ones. No exceptions.

---

## Open Research Questions (Answered After Data Accumulates)

- Does ATM or ITM-2 produce better fill quality at 0DTE premiums < $1.00?
- Does the -15% bear stop (Bold) actually prevent more stops than -8% (Safe) on real intraday price action?
- Which TP1 level (+30% vs +75%) is more commonly hit before the runner leg gets stopped?
- At what account size does the ITM-2 premium cap become a binding constraint on Bold's trade count?
- Is there a VIX threshold where Safe's tighter gate outperforms (avoids bad vol regimes) vs where it underperforms (misses good setups)?
