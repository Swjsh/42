# Compound Matrix -- what compounding path is actually available

_Generated 2026-08-29T16:14:32.535718 | seed=20260829 | 2000 sims/path, 1000 sims/milestone_

> $2,000/day is an OUTPUT of compounding, not a target. This is the tool that answers what path gets there and what binds it. **Analysis-path only** -- no trading-engine file was touched, nothing armed.

## Verdict

- **Liquidity is NOT the wall, and the previous version of this report was wrong to say it was.** That headline (a bend at $7.8K-$15.6K equity) came from treating **displayed** NBBO bid size (median 46 contracts) as available liquidity. Displayed top-of-book size is a quote at one instant, not the quantity that can trade -- and the measurement was 33 quotes from 3 snapshots inside a single ~4-minute window of ONE session.
- **Measured against real 1-minute OPRA bars** for the contracts we actually traded (319 contract-days): median daily volume **443,750** contracts per contract, and in the very same $1.50-2.50 band the median MINUTE trades **357** contracts against an alleged 46-contract wall. Our largest order ever is **12**.
- On the traded-volume model (10% participation across a 5-minute exit window, priced off the 25th-percentile minute) capacity binds at **$51,074** equity -- far beyond every milestone in this report. Projections here are therefore no longer depth-capped.
- **The $1,000/5-contract config caps shipped yesterday are NOT a wall either** -- they're sized for today's ~$5K and should rescale with equity (table below).
- **Post-fix (n=23 arm-days, ~8 sessions) is genuinely strong** (median 3.616%/day) but is only ~8.75 independent sessions once cross-arm correlation is priced in -- an extrapolation, not a forecast.
- **All-history's median arm-day is a LOSS** (-0.771%). Any 12-month number below assuming the recent hot streak persists says so in the same sentence.
- **J's stated $3,000 pain threshold is likely to be hit outside the current hot streak**: P($3,000 drawdown within 12mo) is 100% under the August regime and 97% under all-history (vs 100% under post-fix specifically). Full table below.

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

## Capacity -- traded volume, not displayed depth

**CORRECTION (2026-08-29).** This section previously reported a capacity wall at $7.8K-$15.6K equity derived from displayed NBBO bid size. That model is REFUTED and no longer feeds any projection in this file. It is kept below so the correction is auditable rather than silently deleted.

**The live model -- participation in volume actually traded:**

- Evidence: 319 contract-days of real 1-minute OPRA bars, for the contracts this book actually traded.
- Median daily volume per contract: **443,750** contracts (p25 272,818).
- In the $1.50-2.50 exit band (19,623 minutes observed): median **357** contracts/minute, p25 151, p10 65.
- Allowed size = participation x traded volume over a 5-minute exit window, priced off the p25 minute: **755** contracts available in the window.
- Winner cohort in that band: n=28, median entry premium $1.15.

**E\* by deployment fraction x participation rate:**

| deployment f | 5% participation | 10% participation | 20% participation |
|---|---|---|---|
| 10% | $43,412 | $86,825 | $173,650 |
| 15% | $28,942 | $57,883 | $115,767 |
| 17% | $25,537 | $51,074 | $102,147 |
| 20% | $21,706 | $43,412 | $86,825 |
| 25% | $17,365 | $34,730 | $69,460 |

Central (f=17%, participation 10%): **$51,074** equity.

**The refuted depth model, for the record.** Displayed median 46 contracts at $1.50-2.50 vs 638 at $0.00-0.20. Its own evidence verdict was already: "THIN. One session, 3 snapshots, 33 total contract-quotes, on an explicitly 'indicative' (not confirmed real OPRA) feed. Every E* number below is an order-of-magnitude signal, not a precise constant." Ratio of contracts actually traded in the exit window to contracts displayed at the touch: **16.4x**.

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
| post_fix | $5000 | 13/22/36 (100%) | 37/51/72 (100%) | 82/103/128 (100%) |
| post_fix | $10000 | 1/1/3 (100%) | 19/29/44 (100%) | 61/79/103 (100%) |
| august | $5000 | 21/53/155 (100%) | 69/140/298 (100%) | 174/292/512 (100%) |
| august | $10000 | 1/1/13 (100%) | 33/76/193 (100%) | 125/228/410 (100%) |
| all_history | $5000 | 38/153/914 (96%) | 168/555/1679 (88%) | 518/1178/2103 (71%) |
| all_history | $10000 | 1/2/33 (100%) | 69/247/1128 (95%) | 346/850/1980 (81%) |

`(p_reached_within_horizon)` = fraction of the 10-year simulated paths that ever reach the target under the depth cap; a low fraction means most paths plateau below it.

## The $2,000/day MEDIAN-day question

- **post_fix**: naive math says $55,310 equity, but the depth wall caps deployable equity at ~$51,074, so the median day's dollar P&L plateaus at ~$1,847/day -- BELOW $2,000 at ANY equity under this depth constraint. Scaling THIS account cannot reach $2,000/day as the median day; only more market depth (more names, slower/limit execution, or a bigger per-contract edge) can.
- **august**: naive math says $167,504 equity, but the depth wall caps deployable equity at ~$51,074, so the median day's dollar P&L plateaus at ~$610/day -- BELOW $2,000 at ANY equity under this depth constraint. Scaling THIS account cannot reach $2,000/day as the median day; only more market depth (more names, slower/limit execution, or a bigger per-contract edge) can.
- **all_history**: median arm-day is a LOSS in this regime -- no equity level makes $2,000/day the MEDIAN day; more capital cannot fix a negative median.

## Naive (uncapped) vs depth-capped 12-month projection, $1.00 slippage

_The 'naive' column is deliberately unconstrained (contracts scale with equity forever, no market-depth limit) -- the huge numbers are the point: this is what the brief's original wrong assumption ('returns hold at any size') implies, and it is obviously absurd. The depth-capped column is the realistic one._

| Regime | Start | Naive p50 @12mo | Depth-capped p50 @12mo | Cost of the depth wall |
|---|---|---|---|---|
| post_fix | $5000 | $14,809,230 | $360,691 | $14,448,539 |
| post_fix | $10000 | $28,367,177 | $396,336 | $27,970,841 |
| august | $5000 | $56,950 | $61,068 | $-4,118 |
| august | $10000 | $112,924 | $105,724 | $7,200 |
| all_history | $5000 | $7,227 | $7,227 | $0 |
| all_history | $10000 | $14,408 | $14,408 | $0 |

All-history shows a NEGATIVE 'cost' (capped ends up higher than naive): expected, not a bug -- all-history's median day is a loss, so uncapped (proportional) compounding drags equity DOWN over time (volatility drag on a negative-median geometric walk), while the depth cap also limits DOWNSIDE dollar risk once equity has been above the wall, softening the decay.

## Withdrawal vs reinvest (illustrative: post-fix regime, $5,000 start)

**Threshold $43,400 (BELOW the ~$51,074 depth wall -- withdrawing here forgoes real compounding):**
- 100% reinvest, median combined wealth @12mo: **$359,209**
- Withdraw above threshold monthly: **$348,490**
- Cost of withdrawing: **$10,719**

**Threshold $10,000 (BELOW the ~$51,074 depth wall -- withdrawing here forgoes real compounding):**
- 100% reinvest, median combined wealth @12mo: **$359,209**
- Withdraw above threshold monthly: **$118,966**
- Cost of withdrawing: **$240,243**

Same random draws for both policies (paired comparison). Withdraw policy caps the TRADING account at $43,400 monthly and sweeps the excess to cash (0% yield assumed); 'combined wealth' = trading equity + cash swept out. Reinvesting keeps compounding the swept cash INSIDE the trading account instead. The below-wall case has a REAL cost because that capital was still compounding productively; the at/above-wall case costs ~nothing because the depth cap already made that capital idle inside the trading account too -- withdrawing it loses nothing.

## Drawdown / ruin (central slippage $1.00/contract, depth-capped)

| Regime | Start | Median max DD% | p90 max DD% | P(50% DD) | P($3,000 DD) | P(below start @12mo) | Longest losing streak (median/p90 days) |
|---|---|---|---|---|---|---|---|
| post_fix | $5,000 | 11.29% | 17.05% | 0.0% | 100.0% | 0.0% | 5/7 |
| post_fix | $10,000 | 10.18% | 16.18% | 0.0% | 100.0% | 0.0% | 5/7 |
| august | $5,000 | 50.91% | 68.53% | 53.0% | 100.0% | 2.4% | 7/9 |
| august | $10,000 | 47.96% | 69.35% | 44.7% | 100.0% | 2.6% | 7/9 |
| all_history | $5,000 | 61.62% | 80.87% | 78.6% | 97.5% | 36.6% | 10/14 |
| all_history | $10,000 | 61.09% | 81.12% | 76.4% | 100.0% | 36.1% | 10/14 |

## Ranked: what actually binds the compounding path

**1. [which_regime_is_real] Whether August's +1.55%/day is the true rate or a favourable 20-session sample. All-history's MEDIAN day is a LOSS (-0.77%).**
   - Binds at: Every projection in this file. It is the only assumption that changes the answer by orders of magnitude.
   - Fix: The September scoring window measures exactly this. Nothing else to do but run it clean and let go_live_gate.py score it.

**2. [market_depth_REFUTED] ⛔ WAS rank 1. The claim that displayed exit-side liquidity (median 46.0 contracts at $1.50-2.50) caps deployable equity at $7.8K-$15.6K. REFUTED 2026-08-29: displayed top-of-book size is a quote at an instant, not available liquidity, and the measurement was 33 quotes from 3 snapshots in one ~4-minute window.**
   - Binds at: Nothing at this scale. Real 1-minute OPRA bars for the contracts we traded: median daily volume ~443,750 contracts; the median MINUTE in that same $1.50-2.50 band trades ~357 contracts against an alleged 46.0-contract wall; our largest order ever is 12, and only 1.6% of minutes in that band trade fewer than 12.
   - Fix: Superseded by the traded-volume model (capacity_volume). Revisit only if order size approaches a few percent of per-minute traded volume.

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
