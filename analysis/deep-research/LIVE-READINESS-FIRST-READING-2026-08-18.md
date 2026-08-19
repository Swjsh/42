# First reading of the live-readiness gate — and it is not close

> The gate CLAUDE.md has stated since the beginning — *"Live threshold (per account
> independently): ≥ 20 trades, WR ≥ 45%, positive expectancy, ≤ 2 rule breaks"* — had **no
> implementation** until tonight. `setup/scripts/live_readiness.py` now computes it. This is
> its first reading, taken 2026-08-18, and the numbers were cross-verified against a
> from-scratch re-derivation off `fills_fifo.mine_real_arm_fills` (exact match on every arm).
>
> All five arms are **PAPER**. No real money was ever at risk. That is the point of the
> exercise working correctly.

> ## ⚠️ CORRECTION APPENDED 2026-08-18, SAME EVENING
>
> J pushed back on this document's framing: *"the win rate doesn't necessarily reflect being
> profitable, so we need to rethink that part of the readiness gate."* He was right, and
> testing it changed the conclusion. Two things this document got wrong:
>
> 1. **The 45% win-rate bar is miscalibrated for this strategy.** Profitability is decided by
>    whether the win rate clears *this* strategy's breakeven, which is `1/(1+payoff_ratio)`.
>    The arms run 2.25×–3.52× payoffs, so their breakevens are **22%–31%**, not 45%. Measured
>    against their own lines, every arm is **0.6–5.1 percentage points short** — near-misses,
>    not failures. A flat 45% bar demands roughly double what the strategy needs.
>
> 2. **Not one arm's expectancy is statistically distinguishable from zero.** |t| runs
>    0.1–0.7 against a threshold of 2. The point estimates are negative; the *conclusion*
>    "no arm is close" was not supported by them. The honest verdict is **UNKNOWN**, not FAIL.
>
> The gate now reports breakeven win rate, margin in percentage points, and a t-statistic.
> The tables below are left unedited as the original reading.

## VERDICT (as originally written — see correction above)

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

## Corrected verdict

| arm | win rate | its own breakeven | margin | expectancy | t |
|---|---:|---:|---:|---:|---:|
| risky-3 | 21.5% | 22.1% | **−0.6pp** | −$2.15 | −0.1 |
| risky-1 | 23.5% | 25.0% | −1.5pp | −$4.37 | −0.2 |
| safe-3 | 21.3% | 24.4% | −3.2pp | −$8.00 | −0.4 |
| bold-2 | 26.9% | 30.8% | −3.9pp | −$18.92 | −0.4 |
| safe-2 | 23.2% | 28.3% | −5.1pp | −$10.67 | −0.7 |

**Every arm is a near-miss on its own terms, and no arm has enough data to say so with
confidence.** That is a materially different situation from "not close," and it points at a
different question: the gap is 0.6–5.1pp of win rate, which is small enough that costs
(fees + spread, being quantified separately) could plausibly account for the whole of it —
or make it worse. That is now the load-bearing unknown.

## Cost-realistic final picture (added after the exit-fill question was settled)

The corrected verdict above uses GROSS P&L. Real trading pays two costs paper does not charge
us: regulatory fees (Alpaca paper debits them for real, but `broker_fills.py` reads
`/activities/FILL` only, so `real_pnl` never counted them) and exit slippage (measured: our
sells are credited **0.129 of the traded range** better than a real market sell would get —
`exit_fill_realism.py`). Applying both **per trade**, not by extrapolation:

| arm | n | gross expectancy | **net expectancy** | win rate | breakeven | **margin** |
|---|---:|---:|---:|---:|---:|---:|
| risky-3 | 79 | −$2.15 | **−$10.21** | 20.3% | 23.0% | **−2.8pp** |
| risky-1 | 68 | −$4.37 | **−$10.20** | 20.6% | 23.7% | −3.1pp |
| safe-3 | 47 | −$8.00 | **−$11.94** | 21.3% | 26.0% | −4.7pp |
| bold-2 | 26 | −$18.92 | **−$24.74** | 26.9% | 32.0% | −5.1pp |
| safe-2 | 69 | −$10.67 | **−$14.09** | 23.2% | 29.9% | −6.7pp |

| book | figure |
|---|---:|
| as traded | −$2,071 |
| after real fees | −$2,201 |
| **after fees + measured exit slippage** | **−$3,677** |

**Realistic costs roughly DOUBLE the gap for the best arms** — risky-3 goes from a 0.6pp
near-miss on gross numbers to **2.8pp** once it pays what a real account pays. Costs are worth
roughly **2 percentage points of win rate**, which is the single most useful number in this
document for anyone deciding what "close" means.

Note the win rates move too (risky-1 23.5% → 20.6%, risky-3 21.5% → 20.3%): costs flip
marginal winners into losers. That is a real effect of trading a thin edge on sub-$1.00
premiums, not a rounding artifact.

> ⚠️ **Correction to an earlier figure in this session.** A first pass estimated the
> cost-realistic book at −$3,096 by extrapolating from median traded range and median exit
> qty. Computing it per-trade instead gives **−$3,677**. The per-trade number is the correct
> one; the median-extrapolation understated the cost by ~16% because larger exits carry
> proportionally more slippage and medians discard that.

**The conclusion does not change: still near-misses, still not statistically distinguishable
from zero, still not ready.** But "how near" is now honestly ~3–7pp rather than ~1–5pp.

## Reproduce

```bash
backtest/.venv/Scripts/python.exe setup/scripts/live_readiness.py
```

Machine-readable output: `analysis/recommendations/live-readiness.json`. Guard:
`backtest/tests/test_live_readiness.py` (19 tests, RED-proofed by mutating both the `n_trades`
and `expectancy` comparison operators and confirming exactly the boundary tests fail).
