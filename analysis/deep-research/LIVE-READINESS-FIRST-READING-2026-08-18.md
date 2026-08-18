# First reading of the live-readiness gate — and it is not close

> The gate CLAUDE.md has stated since the beginning — *"Live threshold (per account
> independently): ≥ 20 trades, WR ≥ 45%, positive expectancy, ≤ 2 rule breaks"* — had **no
> implementation** until tonight. `setup/scripts/live_readiness.py` now computes it. This is
> its first reading, taken 2026-08-18, and the numbers were cross-verified against a
> from-scratch re-derivation off `fills_fifo.mine_real_arm_fills` (exact match on every arm).
>
> All five arms are **PAPER**. No real money was ever at risk. That is the point of the
> exercise working correctly.

## VERDICT

**No arm is close to the live bar. Every arm fails win rate and fails expectancy.**

| arm | n | win rate (bar ≥45%) | expectancy (bar >0) | total |
|---|---:|---:|---:|---:|
| safe-2 | 69 | 23.2% ❌ | −$10.67 ❌ | −$736 |
| bold-2 | 26 | 26.9% ❌ | −$18.92 ❌ | −$492 |
| safe-3 | 47 | 21.3% ❌ | −$8.00 ❌ | −$376 |
| risky-1 | 68 | 23.5% ❌ | −$4.37 ❌ | −$297 |
| risky-3 | 79 | 21.5% ❌ | −$2.15 ❌ | −$170 |

Rule-break criterion reads **UNKNOWN**, not PASS: `automation/state/rule-breaks.jsonl` carries
no arm/account attribution field, so per-arm counts cannot be computed. That is a real data
gap, reported rather than guessed. It changes nothing — win rate and expectancy already
disqualify every arm on their own.

## The concentration is the real story

Book-wide (a **correlated** rollup — the five arms trade one signal at r=0.846, so this is not
five independent samples): **289 closed round trips across 34 trading days, −$2,071.**

| cut | book P&L |
|---|---:|
| as traded | **−$2,071** |
| excluding the single best day (2026-08-04) | **−$5,695** |
| excluding the best 2 days | −$7,443 |
| excluding the best 3 days | −$8,908 |

- **Profitable days: 11 of 34 (32%). Median day: −$83.**
- Best day 2026-08-04 alone: **+$3,624**. Worst day 2026-08-07: **−$2,687**.
- Per-arm, every single arm's best day exceeds 100% of its own total P&L — i.e. **remove each
  arm's best day and every arm is deeper underwater.**

This is what a right-tail-shaped edge looks like when the tail is not paying for the body. The
payoff ratios are genuinely good (2.2×–3.5×), which is the design working; the win rates
(21–27%) are simply not high enough to make those payoffs profitable. At 25% and 3× the strategy
is exactly breakeven before costs — every arm sits at or under that line.

## The era split does not rescue it

Split at **2026-08-10**, the boundary already pre-registered in commit `fdedd5c5` ("the review's
biggest leak was already fixed on 2026-08-10 — split the era") rather than chosen here:

| era | n | win rate | expectancy | total |
|---|---:|---:|---:|---:|
| pre-2026-08-10 | 196 | 18.9% | −$3.38 | −$663 |
| **post-2026-08-10** | 93 | **31.2%** | **−$15.14** | **−$1,408** |

**Win rate improved substantially (18.9% → 31.2%) while expectancy got 4.5× worse.** The newer
era wins more often and loses more money. risky-1 is the sharpest example: 15.0% WR / **+$476**
before, 35.7% WR / **−$773** after.

That pattern — more winners, worse P&L — is the signature of a shortened right tail: winners
being cut smaller while losers stay the same size. It is a hypothesis, not a conclusion, and it
sits in direct tension with the stop-mode A/B clock's interim reading (premium stops ahead by
+$1,809 over 95 trades / 5 days). **Both cannot be right.** Resolving that contradiction is the
highest-value open question this instrument has surfaced, and it should be settled by the
pre-registered stop-mode clock at its own D20 checkpoint, not by re-reading this table.

## What this does and does not mean

**Does:**
- The paper program has not earned live money, by its own written criterion, by a wide margin.
- Recent good days (+$124 on 08-17, +$162 on 08-18) are real but are ~1% of the hole. Reporting
  them without this denominator overstates the state of the book, and this document exists so
  that stops happening.
- The gate is now measurable. Every future claim about readiness can be checked in one command.

**Does not:**
- Say the strategy is dead. A 2.2–3.5× payoff ratio with a fixable win rate is a different
  problem from no edge at all.
- Say anything about a specific arm's independent merit — at r=0.846 these are five sizes of
  one bet, and the per-arm rows should be read as five looks at the same strategy.
- Justify loosening any gate to trade more. The measured problem is not too few trades.

## Reproduce

```bash
backtest/.venv/Scripts/python.exe setup/scripts/live_readiness.py
```

Machine-readable output: `analysis/recommendations/live-readiness.json`. Guard:
`backtest/tests/test_live_readiness.py` (19 tests, RED-proofed by mutating both the `n_trades`
and `expectancy` comparison operators and confirming exactly the boundary tests fail).
