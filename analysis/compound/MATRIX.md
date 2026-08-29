# Compound Matrix -- what compounding path is actually available

_Generated 2026-08-29T14:28:00.130591 | seed=20260829 | 2000 sims/path, 1000 sims/milestone_

> $2,000/day is an OUTPUT of compounding, not a target. This is the tool that answers what path gets there and what binds it. **Analysis-path only** -- no trading-engine file was touched, nothing armed.

## Verdict

- **The real wall is market depth, not account size.** Central estimate: returns hold their measured shape up to roughly **$7,779-$15,559** equity (1.5x-3x today's ~$5.3-5.8K), then bend from exponential toward linear because the exit-side book (median 46 displayed contracts at the $1.50-2.50 premium where winners actually exit) can't absorb more size at a good price.
- **That number is uncertain** -- the depth measurement is 1 session / 3 snapshots / 33 quotes on an indicative (not confirmed OPRA) feed. Treat it as an order of magnitude.
- **The $1,000/5-contract config caps shipped yesterday are NOT the wall** -- they're sized for today's ~$5K and should rescale with equity (table below), capped at the depth ceiling once that binds.
- **Post-fix (n=23 arm-days, ~8 sessions) is genuinely strong** (median 3.616%/day) but is only ~8.75 independent sessions once cross-arm correlation is priced in -- an extrapolation, not a forecast.
- **All-history's median arm-day is a LOSS** (-0.771%). Any 12-month number below assuming the recent hot streak persists says so in the same sentence.
- **J's stated $3,000 pain threshold is likely to be hit outside the current hot streak**: P($3,000 drawdown within 12mo) is 93% under the August regime and 94% under all-history (vs 0% under post-fix specifically). Full table below.

## Regimes re-derived from analysis/trades-enriched.jsonl (this script's own numbers)

| Regime | n arm-days | sessions | mean%/day | median%/day | sd% | %green | J stated |
|---|---|---|---|---|---|---|---|
| Post-fix (>=08-19) | 23 | 8 | 3.604 | 3.616 | 6.207 | 60.9% | mean 2.99, median 3.21, 61% green |
| August (>=08-01) | 60 | 20 | 1.554 | 1.194 | 7.926 | 53.3% | mean 1.12, median ?, 53% green |
| All-history | 104 | 40 | 0.59 | -0.771 | 6.526 | 38.5% | mean 0.34, median NEGATIVE, 38% green |

4-arm roster used throughout (safe-2, bold-2, safe-3, risky-1): risky-3 retired 2026-08-28, see `risky3_exclusion` in the JSON. Reproduces J's n/sessions/green% exactly; mean/median/sd differ by ~0.3-1.1pp, most likely an equity-denominator convention difference -- disclosed, not resolved.

## Effective-n on the post-fix regime (the anti-self-deception check)

- Raw: 23 arm-days across 8 sessions, cluster sizes [1, 1, 2, 3, 4, 4, 4, 4]
- Measured pairwise correlation across arms: [0.876, 0.894, 0.921, 0.932, 0.951, 0.985]
- Effective n (Kish design effect, rho swept 0.62-0.72): **8.75**
- 23 arm-days across 8 sessions is really ~9 independent observations once cross-arm correlation is priced in -- ANY 12-month projection off this regime is an EXTRAPOLATION from a single-digit number of independent trading sessions, not a forecast.

## The capacity bend (market depth, not config)

- Displayed bid depth: median **638.0** contracts at $0.00-0.20 premium (where losers exit -- deep, no wall) vs median **46.0** at $1.50-2.50 (where winners exit -- thin).
- Winner cohort landing in that thin bucket: n=28, median entry $1.15, median exit $1.795 (Re-derived median exit premium for this cohort is 1.795 -- close to, not identical to, the $1.72 cited in the brief; both land in the same thin $1.50-2.50 depth bucket, which is what matters for this analysis.)
- Evidence quality: THIN. One session, 3 snapshots, 33 total contract-quotes, on an explicitly 'indicative' (not confirmed real OPRA) feed. Every E* number below is an order-of-magnitude signal, not a precise constant.
- Recommended follow-up study: Extend setup/scripts/quote_recorder.py (already polls NBBO) into a dedicated multi-session depth study: sample full-chain bid/ask size at open/mid/close across >=15 sessions, stratified by VIX regime, cross-referenced against this book's own real fill sizes vs displayed size to measure realized slippage-vs-depth directly instead of inferring it from static snapshots.

**E\* sensitivity grid** (equity where contracts-per-entry first hits the threshold fraction of displayed depth), stress case = one entry claims the whole day's deployment:

| deployment f | thresh 10% | thresh 25% | thresh 50% |
|---|---|---|---|
| 10% | $5,290 | $13,225 | $26,450 |
| 15% | $3,527 | $8,817 | $17,633 |
| 17% | $3,112 | $7,779 | $15,559 |
| 20% | $2,645 | $6,612 | $13,225 |
| 25% | $2,116 | $5,290 | $10,580 |

Central (f=17%, thresh=25%): **$7,779** (stress) to **$15,559** (observed ~2 entries/day). Central estimate: the market-depth wall likely starts binding somewhere between roughly $7.8K (conservative: one entry claims the whole day's deployment) and $15.6K (using the observed ~2 entries/day to split it) -- i.e. 1.5x-3x current equity, not $50K-$200K. Thin evidence (see above); treat as 'probably closer than it looks', not as a precise number.

## Config caps that RESCALE with equity (not walls)

| Equity | naive $/entry (17%) | naive max contracts | depth-capped max contracts | recommended max_position_dollars |
|---|---|---|---|---|
| $10,000 | $1,700 | 24.1 | 12 | $846 |
| $25,000 | $4,250 | 60.3 | 12 | $846 |
| $50,000 | $8,500 | 120.6 | 12 | $846 |
| $100,000 | $17,000 | 241.1 | 12 | $846 |

- **min_contracts is a small-account floor, not a large-account wall.** At the 17% target deployment fraction, an account below roughly $1,244 (safe, min_contracts=3) / $2,074 (bold, min_contracts=5) is FORCED to deploy MORE than the target fraction per entry -- the floor over-leverages a small account. Both live accounts (~$5.3-5.8K) sit comfortably above this today, but it binds for anyone starting smaller.
- params.json/aggressive/params.json ALREADY carry a min_contracts_equity_scaled knob designed for exactly this (safe=False, bold=False) -- it exists and is OFF, not missing.

## Milestone table (central slippage $1.00/contract, depth-capped, 4-arm roster)

| Regime | Start | days to $10K (p10/p50/p90) | days to $25K | days to $100K |
|---|---|---|---|---|
| post_fix | $5000 | 14/22/35 (100%) | 60/79/101 (100%) | 324/364/411 (100%) |
| post_fix | $10000 | 1/1/4 (100%) | 41/57/76 (100%) | 304/340/385 (100%) |
| august | $5000 | 21/55/154 (100%) | 120/199/356 (100%) | 745/951/1237 (100%) |
| august | $10000 | 1/1/12 (100%) | 77/139/247 (100%) | 674/882/1148 (100%) |
| all_history | $5000 | 40/160/957 (96%) | 310/721/1714 (90%) | 1814/2218/2493 (13%) |
| all_history | $10000 | 1/2/20 (100%) | 190/442/1133 (96%) | 1673/2184/2456 (21%) |

`(p_reached_within_horizon)` = fraction of the 10-year simulated paths that ever reach the target under the depth cap; a low fraction means most paths plateau below it.

## The $2,000/day MEDIAN-day question

- **post_fix**: naive math says $55,310 equity, but the depth wall caps deployable equity at ~$7,779, so the median day's dollar P&L plateaus at ~$281/day -- BELOW $2,000 at ANY equity under this depth constraint. Scaling THIS account cannot reach $2,000/day as the median day; only more market depth (more names, slower/limit execution, or a bigger per-contract edge) can.
- **august**: naive math says $167,504 equity, but the depth wall caps deployable equity at ~$7,779, so the median day's dollar P&L plateaus at ~$93/day -- BELOW $2,000 at ANY equity under this depth constraint. Scaling THIS account cannot reach $2,000/day as the median day; only more market depth (more names, slower/limit execution, or a bigger per-contract edge) can.
- **all_history**: median arm-day is a LOSS in this regime -- no equity level makes $2,000/day the MEDIAN day; more capital cannot fix a negative median.

## Naive (uncapped) vs depth-capped 12-month projection, $1.00 slippage

_The 'naive' column is deliberately unconstrained (contracts scale with equity forever, no market-depth limit) -- the huge numbers are the point: this is what the brief's original wrong assumption ('returns hold at any size') implies, and it is obviously absurd. The depth-capped column is the realistic one._

| Regime | Start | Naive p50 @12mo | Depth-capped p50 @12mo | Cost of the depth wall |
|---|---|---|---|---|
| post_fix | $5000 | $14,809,230 | $70,629 | $14,738,602 |
| post_fix | $10000 | $28,367,177 | $76,209 | $28,290,968 |
| august | $5000 | $56,950 | $28,039 | $28,911 |
| august | $10000 | $112,924 | $34,856 | $78,068 |
| all_history | $5000 | $7,227 | $8,580 | $-1,353 |
| all_history | $10000 | $14,408 | $16,654 | $-2,246 |

All-history shows a NEGATIVE 'cost' (capped ends up higher than naive): expected, not a bug -- all-history's median day is a loss, so uncapped (proportional) compounding drags equity DOWN over time (volatility drag on a negative-median geometric walk), while the depth cap also limits DOWNSIDE dollar risk once equity has been above the wall, softening the decay.

## Withdrawal vs reinvest (illustrative: post-fix regime, $5,000 start)

**Threshold $6,600 (BELOW the ~$7,779 depth wall -- withdrawing here forgoes real compounding):**
- 100% reinvest, median combined wealth @12mo: **$70,333**
- Withdraw above threshold monthly: **$68,101**
- Cost of withdrawing: **$2,232**

**Threshold $10,000 (AT/ABOVE the ~$7,779 depth wall -- capital past the wall is already capped/idle inside the trading account, so withdrawing it costs ~nothing):**
- 100% reinvest, median combined wealth @12mo: **$70,333**
- Withdraw above threshold monthly: **$70,333**
- Cost of withdrawing: **$0**

Same random draws for both policies (paired comparison). Withdraw policy caps the TRADING account at $6,600 monthly and sweeps the excess to cash (0% yield assumed); 'combined wealth' = trading equity + cash swept out. Reinvesting keeps compounding the swept cash INSIDE the trading account instead. The below-wall case has a REAL cost because that capital was still compounding productively; the at/above-wall case costs ~nothing because the depth cap already made that capital idle inside the trading account too -- withdrawing it loses nothing.

## Drawdown / ruin (central slippage $1.00/contract, depth-capped)

| Regime | Start | Median max DD% | p90 max DD% | P(50% DD) | P($3,000 DD) | P(below start @12mo) | Longest losing streak (median/p90 days) |
|---|---|---|---|---|---|---|---|
| post_fix | $5,000 | 7.74% | 13.12% | 0.0% | 0.1% | 0.0% | 5/7 |
| post_fix | $10,000 | 5.29% | 9.2% | 0.0% | 0.0% | 0.0% | 5/7 |
| august | $5,000 | 37.3% | 62.61% | 24.7% | 93.5% | 1.9% | 7/9 |
| august | $10,000 | 26.31% | 51.39% | 10.8% | 96.5% | 1.0% | 7/9 |
| all_history | $5,000 | 56.88% | 79.66% | 62.6% | 93.8% | 34.4% | 10/14 |
| all_history | $10,000 | 41.46% | 74.48% | 36.8% | 98.4% | 22.5% | 10/14 |

## Ranked: what actually binds the compounding path

**1. [market_depth] Displayed exit-side liquidity at the $1.50-2.50 premium band (median 46.0 contracts) where right-tail winners actually exit.**
   - Binds at: ~$7,779-$15,559 equity (1.5x-3x current), central assumption -- NOT a config number.
   - Fix: Not fixable by more capital. Needs more market depth: trade across more names (the multi-symbol lane already ships this), execute with limit patience instead of market orders at size, or find a bigger per-contract edge so fewer contracts are needed for the same dollars.

**2. [evidence_quality] The depth measurement itself: 1 session, 3 snapshots, 33 quotes, an 'indicative' (not confirmed OPRA) feed.**
   - Binds at: Confidence in constraint #1's exact dollar value, not the path itself.
   - Fix: Run the multi-session depth study named in capacity_bend.evidence_quality before treating any specific E* number as more than an order of magnitude.

**3. [config_rescale] max_contracts_per_entry=5 / max_position_dollars=$1,000 (shipped 2026-08-29 for a ~$5K account) and position_sizing_tiers' flat top bracket above $10K.**
   - Binds at: Immediately above current equity if left un-rescaled -- but this is a KNOB, not a wall.
   - Fix: Rescale with equity per config_rescale_table -- but only up to the depth ceiling (~12 contracts at the central 25%-of-depth assumption); do not extrapolate max_contracts_per_entry past that even though the dollar cap formula would suggest it.

**4. [config_rescale] min_contracts (3 safe / 5 bold) as a FLOOR -- over-leverages SMALL accounts, not large ones.**
   - Binds at: Below ~$1,244 (safe) / ~$2,074 (bold); both live accounts are already above this.
   - Fix: min_contracts_equity_scaled already exists in both params files and is OFF -- turning it on is the built-in fix, not a new build.

**5. [evidence_quality] The all-history regime's MEDIAN arm-day is a loss (this script: -0.771%); post-fix is n=23 arm-days / ~8-10 effective independent sessions.**
   - Binds at: Confidence in ANY forward projection, at any equity.
   - Fix: No fix -- disclose it. Every post-fix-anchored number in this report is an extrapolation from a single-digit number of independent sessions, and the long-run all-history shape says the median day is a loss. Time, not capital, is what would fix this.

## Full data

Every regime x slippage-level (0.00/0.50/1.00/2.00 per contract) x all-days/drop-best-day x $5,000/$10,000 start percentile path and drawdown stat lives in `analysis/compound/matrix.json` -- this file shows the central slippage assumption ($1.00/contract) for readability.
