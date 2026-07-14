# Trendline Break Literature Review — External Research (2026-07-14)

> **G2 — external research crew.** Triggered by J's directive after the live 12:10-12:15 ET ascending-support break: *"this needs a proper review. charting skills and a full research agent on trend lines and their breaks."* Scope: web literature only (academic / exchange / practitioner / blog), every claim cited + quality-tagged. **This crew did NOT edit `trendline_engine.py`, any drawing-bridge script, or the in-flight `TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14.md`** — those files were read-only for grounding "portable to our stack" language below, per hard constraint. No orders, no param flips — this is literature + recommendations only; ratification is a separate step.
>
> **Method:** ~20 WebSearch queries + 10 WebFetch pulls, prioritized post-2015 sources, cross-checked against our OWN internal trendline backtests (`analysis/backtests/trendline_break_retest_findings.md`, `backtest/autoresearch/trendline_age_analysis.py` results, `trendline_tod_breakdown.py`) so external claims are graded against what we've already measured on real SPY 5m data — not accepted blind. Quality tags: `[ACADEMIC]` `[EXCHANGE]` `[PRACTITIONER]` `[BLOG]`.

---

## Bottom line (verdict-first)

**The honest literature does NOT support "trendline breaks are a free, standalone edge."** It supports a narrower, testable claim: *a small number of specific mechanical rules (body-close confirmation, avoiding the 11:30-14:00 ET chop window, requiring multiple genuine respects) measurably improve the odds a break is real — but even with all of them applied, a rigorous 2026 falsification study on a comparable liquid index-futures instrument found NO standard OHLCV breakout/retest signal cleared institutional significance thresholds.** Our own internal trendline-break-retest backtest independently arrived at the same shape of result: positive expectancy, striking win/loss ratio, but a win rate too low to promote alone (23% WR at the "sweet spot" touch-count, 3/5 promotion gates). Treat every recommendation below as "worth the smallest test," not "ship it."

| # | Finding | Evidence quality | Matches our own data? | Verdict |
|---|---|---|---|---|
| 1 | **Body-close confirmation, not wick-through** | Converged practitioner + matches academic BOS logic | **Already how `trendline_engine.py` scores breaks** (`close < lv - TOL`) | Validated, no change needed — cite as external confirmation |
| 2 | **11:30-14:00 ET is the worst window for breakout follow-through** | `[PRACTITIONER]` SPY-specific, 13-yr sample + `[PRACTITIONER]` 14-yr QuantPedia backtest | **We already built `midday_trendline_gate` for a sibling setup** — independently discovered the same effect | **J's 12:10-12:15 break sits inside this exact window** — highest-value, cheapest test below |
| 3 | **Retest entry vs immediate-breakout entry — contested, instrument-dependent** | `[ACADEMIC-preprint]` MNQ falsification study found retest catastrophic; practitioner blogs favor retest for fakeout-filtering | Our own `TRENDLINE_BREAK_RETEST` backtest already uses retest mode | Don't import either number blind — same-instrument test only |
| 4 | **Respect count (touches): more ≠ simply better; age and touch-count are separate axes** | `[PRACTITIONER]` Bulkowski (N=3,172) says monotonic; one blog claims the opposite (touches consume liquidity) | Our `min_touches` sweep sides with Bulkowski's direction; our **age-bucket** analysis is hump-shaped, NOT monotonic | Needs a controlled test that separates touches from age — see §4 |
| 5 | **Volume expansion on the break bar** | `[PRACTITIONER, converged, no rigorous quant number found]` | **Not currently used anywhere in `trendline_engine.py`'s scoring** — bars have `v` field, unused | Cheap, untested addition — see §5 |
| 6 | **The null/skeptic literature** | `[ACADEMIC]` multiple, incl. a 2026 preprint on a near-identical instrument | N/A — sobering context | Must be stated before any ratification, per OP-33 no-oversell |

---

## 1. Confirmation criteria: close-through beats wick-through

**Claim:** a break is only real when the candle **body closes** beyond the line — a wick poking through and reversing is a liquidity sweep, not structure. Waiting for a full 5m close (rather than any intrabar touch) is the single filter practitioners converge on hardest.

- `[BLOG]` EdgeFlo — "At swing and internal structure levels, only a body close counts... False BOS traps almost always come from counting wick breaks as valid." No confirmation-bar count beyond "wait for the candle to print its final close" and no volume rule stated. [edgeflo.com/blog/break-of-structure-trading](https://www.edgeflo.com/blog/break-of-structure-trading)
- `[BLOG]` general breakout-trading synthesis: "Three conditions signal a genuine breakout: a candle close beyond the trendline (not just a wick), above-average volume on the break candle, and price that fails to reclaim the trendline on a subsequent retest." Also: "If price reverses back through the broken trendline within 3 bars, the break is likely false." [xs.com/en/blog/break-retest-trading](https://www.xs.com/en/blog/break-retest-trading/), [stockgro.club/blogs/trading/trendline-breakout](https://www.stockgro.club/blogs/trading/trendline-breakout/)
- `[PRACTITIONER]` A separate but structurally identical instrument-specific finding, N=115 trades over 6 months on ES 5m ORB: entries gated on a confirmed break rather than a touch produced 72.2% win rate / profit factor 1.62 — the authors note the gate itself (not the breakout definition per se) drove most of the edge. Small sample, no walk-forward, explicit "past performance" disclaimer. [edgeful.com — 5-min ORB on ES](https://www.edgeful.com/blog/posts/5-minute-opening-range-breakout-es-strategy)

**Portable to our stack:** `trendline_engine.py`'s `Trendline.status` logic (line 320-322 in the current file) already implements this exactly: `BROKEN` requires `close < cur - TOL` (a full 5m body close beyond the line), not a wick touch (`bars[last]["l"]`/`["h"]` only sets `TESTING`). **No code change indicated — this is external literature confirming a design choice already made.** Worth stating explicitly in the audit crew's writeup so it isn't accidentally "fixed" into a wick-trigger by a future edit that doesn't know this was deliberate.

**Smallest test:** none needed — already the live behavior. If the in-flight audit finds `TESTING` status is being mis-surfaced as `BROKEN` anywhere downstream (dashboard, journal, drawing bridge), that's a consumer bug, not a detector bug — grep consumers of `trendlines-live.json`'s `status` field.

**Kill criterion:** N/A (nothing to kill — validates existing behavior).

---

## 2. Time-of-day: 11:30-14:00 ET is the single most dangerous window for a break — and J's break sat inside it

**Claim:** breakout/level-reclaim reliability collapses in the midday session as volume and directional persistence both drop, independent of what triggered the break.

- `[PRACTITIONER]` ToS Indicators research blog, minute-level SPY data 2008-2021 (methodology stated, per-stat sample sizes not fully itemized — treat numbers as directionally solid, not exact): **5-min ATR** 09:30-10:30 = $0.42, **11:30-13:30 = $0.18** (57% lower), 15:00-16:00 = $0.35. **Trending-bar %**: 62% (open hour) vs **38% (lunch)** vs 57% (close hour). Volume: lunch window is only 9-13% of daily volume vs 20-29% for the open hour, a **40% drop**. Most direct number: **"When SPY approaches support or resistance during lunch, there is a 45% to 55% chance the breakout fails. Compare that to 25% to 30% during the morning."** [tosindicators.com — should you trade during lunch](https://tosindicators.com/research/should-you-trade-during-the-lunch-time-hour)
- `[PRACTITIONER]` QuantPedia, 14-year SPY hourly backtest (2010-2024, Yahoo/Finram data, own empirical work — explicitly **not** grounded in a peer-reviewed paper): SPY shows negative/flat performance 11:00-12:00 ET followed by a positive shift 12:00-14:00 ET — a documented reversal-of-character right at the hour of J's break. [quantpedia.com — lunch effect](https://quantpedia.com/lunch-effect-in-the-u-s-stock-market-indices/)
- `[PRACTITIONER]` Independent convergence: "if no breakout occurs by 12:00 PM ET, it's best to skip the trade, as institutional momentum tends to wane by midday." [quantifiedstrategies.com — ORB backtest](https://www.quantifiedstrategies.com/opening-range-breakout-strategy/)

**This is not new information to this repo.** `backtest/autoresearch/trendline_tod_breakdown.py`'s own docstring states the engine **already** has a `midday_trendline_gate` that blocks trendline-only signals 11:30-14:00 ET for a sibling setup (TRENDLINE_BREAK_RETEST family, not the new `trendline_engine.py` multi-day detector under audit) — the internal team independently discovered the same effect the external literature documents, well before this literature review. That's strong convergent validation of the mechanism, and it means **the fix pattern already exists in the codebase; it just isn't wired to this specific new detector yet** (which is exactly what "shadow-only, A/B NEEDS-REVIEW" means).

**Applied directly to today:** J's break was 12:10-12:15 ET — dead center in the 11:30-14:00 window every source above flags as the worst-odds window for a break to hold. This doesn't mean the break was fake (a genuine dump-through-support did happen, chart-confirmed), but it means **a break in this window carries a documented lower prior for clean follow-through than a break at 10:15 or 14:30 would**, and any confidence score the trendline system eventually feeds an entry-wire should discount midday breaks rather than treat all break-times identically.

**Portable to our stack:** `trendline-log.jsonl` and `trendlines-live.json` already log `ts_et`/`current_et`/`break_level` per entry. This needs **zero new data collection** — it's a re-slice.

**Smallest test:** bucket every logged `BROKEN`-status transition in `analysis/trendlines/trendline-log.jsonl` (and, once the audit crew's fixes land, the multi-day version) by ET hour, and check whether `respect_count` at time of break or subsequent price behavior differs materially for the 11:30-14:00 bucket vs the rest of the day — this is the same shape of analysis `trendline_tod_breakdown.py` already runs for the sibling setup, just needs to be re-pointed at this detector's own log once it has enough rows (currently the log only goes back to 2026-06-26 for the single-day version / 2026-07-08 for multi-day).

**Kill criterion:** if the trendline-log sample shows no meaningful midday degradation once this detector's own `respect_count`/`violations` scoring is accounted for (i.e., the detector's existing quality filter already screens out weak midday lines), a dedicated time gate is redundant — same "already priced in" caveat the 2026-07-11 0DTE mechanism sweep flagged for time-of-day generally.

---

## 3. Retest entry vs. immediate-breakout entry: genuinely contested, do not import either number

**Claim (practitioner consensus):** waiting for price to break, then pull back and hold the broken line before entering, filters most single-candle fakeouts that an immediate-breakout entry eats.

- `[BLOG]` "Waiting for the retest before entering filters most fakeouts automatically... this single rule filters out most false breakout traps." [xs.com/en/blog/break-retest-trading](https://www.xs.com/en/blog/break-retest-trading/)
- **Direct counter-evidence, same asset class, more rigorous methodology:** `[ACADEMIC-preprint]` Mesfin, M. (2026), *"Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study,"* arXiv:2605.04004 [q-fin.TR] (preprint, **not** peer-reviewed, but methodologically rigorous — 947 trading days of 5m MNQ data 2021-2025, walk-forward validation, min T-stat 2.0, min 30 trades, positive net return after a fixed 2-point round-trip cost, includes two known-positive control signals to validate the framework catches real edges when present). Tested 14 signal families including opening-range breakouts and pullback/retest entries. **The pullback/retest variant (retrace to within 5 points of the breakout level before entering) produced an 80.7% stop-out rate at a 20-point stop (net -4.44, T = -1.27) — the retest filter made things WORSE, not better, in that instrument.** Overall verdict: **no signal family cleared all institutional criteria simultaneously**; gross edge for any next-bar-open execution was 0.07-1.50 points/trade, below realistic transaction costs. [arxiv.org/abs/2605.04004](https://arxiv.org/abs/2605.04004), [SSRN mirror](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6709401)
- `[PRACTITIONER]` A separate quant note observed "algorithmically identified levels show statistically significant bounce behaviour, and the number of prior touches matters" for retest-hold entries specifically (as opposed to blind pullback entries) — a narrower claim than "retest always helps." [Retest quality discussion](https://sudoall.com/chart-patterns-breakouts-and-false-breakouts/)

**Why this one is genuinely unresolved, not a simple "retest wins":** MNQ is a different instrument (index futures, continuous overnight session, different liquidity profile) than SPY 0DTE options during RTH, so the 80.7% stop-out number does not transfer directly — but it is a same-asset-class (index-tracking, high-liquidity, algo-dominated) counter-example that should stop anyone from assuming "wait for the retest" is a costless upgrade. **Our own internal backtest already runs the retest variant** (`analysis/backtests/trendline_break_retest_findings.md`, `TRENDLINE_BREAK_RETEST` setup family) and independently found: positive expectancy, exceptional W/L ratio (7.43× at `min_touches=4`), but win rate too low (23%) to pass the 45% promotion gate, and the whole positive P&L was carried by 2 of 20 trades on one strong trend day. That is closer to the MNQ paper's shape of result (edge exists in principle, structurally fragile / concentrated) than to the confident practitioner-blog framing.

**Portable to our stack:** the retest-vs-immediate question is **already an open backtest lever**, not a build item — `backtest/tools/sweep_trendline_break_retest.py` exists and the findings doc's own R-TL-04 recommendation ("Add a SCALP exit variant... exit on first counter-bar that bounces > $0.30") is effectively an immediate-entry variant nobody has run head-to-head against the retest baseline yet.

**Smallest test:** re-run `sweep_trendline_break_retest.py` with an immediate-entry variant (no retest wait) as a direct A/B against the existing retest baseline, same date range (2026-03-15 → 2026-05-08 IS, plus OOS if available), same touch-count sweet spot (`min_touches=4`). Compare WR/expectancy/concentration (is P&L still carried by 1-2 trades) directly — this is the cheapest way to find out whether SPY 0DTE looks more like the MNQ falsification result or the optimistic blog claim.

**Kill criterion:** if immediate entry ALSO concentrates P&L in 1-2 trend days and fails the same 45% WR gate, that's evidence the underlying signal (not the entry-timing choice) is the bottleneck — stop iterating on entry mechanics and revisit whether `trendline_engine.py`'s 2-of-4-family detection is finding genuinely tradeable structure vs. curve-fit lines (see §4).

---

## 4. Respect count and line age: NOT a simple "more is always better," and age ≠ touch-count

**Claim A (touches):** Thomas Bulkowski's *Encyclopedia of Chart Patterns* statistics — the closest thing to a large-sample, transparent-methodology practitioner study on trendlines specifically (not just chart patterns generally) — found touch count matters monotonically, at least up to the sample sizes he had:

- `[PRACTITIONER]` N=3,172 up-sloping-trendline trades total: "Trendlines with 3 touches lost 2.1%. Trendlines with 4 touches made 2%," rising to **7.5% average gain at 7 touches (N=23, small-sample caveat explicit)**. [thepatternsite.com/uptrendlines.html](https://thepatternsite.com/uptrendlines.html)
- Same source, **length**: "Long trendlines made 2.9% and short ones lost 1.4%. The median between short and long was 44 days." Touch **spacing**: "Trendlines with touches spaced wider than 12 days saw gains averaging 2%. Trades in trendlines shorter than 12 days lost 1%."
- Same source, **slope** (counter-intuitive, worth flagging explicitly): "Shallow trendlines made more money than steep ones... trendlines steeper than 0.05 lost 0.7% but those more shallow made 2%." A naive "steeper slope = stronger trend = more significant break" heuristic is **not** what this dataset shows.
- **Direct contradiction from a different practitioner source** (unverified methodology, no sample size given — flag as weaker evidence): `[BLOG]` "multiple touches make zones weaker, not stronger... each test consumes the liquidity that created the level, and when a level finally breaks, it triggers cascading stops." [forexmentoronline.com](https://forexmentoronline.com/support-resistance-levels-dont-become-stronger-with-multiple-touches/) — this is asserted, not shown with data, and reads as a horizontal-level (not trendline) claim; weight it below Bulkowski's transparent large-N result, but don't dismiss the underlying liquidity-consumption mechanism outright.

**Claim B (age) — where our OWN data adds real information the literature doesn't have:** `backtest/autoresearch/results/trendline_age_analysis.txt` (real SPY 5m + VIX bars, IS n=130 trades / OOS n=21) found line age at time of trigger is **hump-shaped, not monotonic**: 0-10 bars old = worst (20.4% WR, +$28 avg P&L), **10-20 bars = best (42.9% WR, +$388 avg P&L)**, 20-30 bars = mediocre (37.5% WR, +$15 avg), 30-40 bars = negative (0% WR, -$80 avg). This is a genuinely different axis than Bulkowski's "long trendlines (44+ days) made money" — his is calendar-duration-of-the-line-itself; ours is bars-since-most-recent-respect-at-time-of-entry. **Neither literature source nor our own data supports "the oldest/most-touched line is automatically the best line" — both show a sweet spot, and the two studies aren't even measuring the same thing**, which is itself the finding: age and touch-count need to be tracked and tested as separate variables, not conflated into one "quality" score.

**Directly relevant to J's stated rule:** *"quality metric = RESPECT COUNT beyond the 2 anchors — extremes are not automatically anchors; 2-point lines through extremes that nothing else touches are garbage."* This is well-supported by every source above — a 2-anchor-only line has, by definition, zero measured respect count, which both Bulkowski's data (3-touch lines already underperform 4+) and our own `min_touches` sweep (2-touch = no improvement over baseline, per the findings doc) independently confirm is the weakest category, not a null case to special-case away. `_fit()`'s `if respect >= 1` floor in `trendline_engine.py` is a **minimum**, not evidence the line is good — it's one respect above the two defining anchors, which the literature says is barely above the "garbage" threshold J flagged.

**Portable to our stack:** `trendline_engine.py`'s current score formula is `respect - 5*violations + (i2-i1)*0.1` — a linear reward for span (a proxy for both age and touch-opportunity conflated together) and a flat penalty per violation. No slope term at all despite Bulkowski's slope finding, and no separate age-vs-touch-count decomposition despite our own age-bucket data showing they diverge.

**Smallest test:** extend `trendline_age_analysis.py`'s existing bucket logic (it already exists and already produces exactly this shape of table) to the new `trendline_engine.py`/`trendline-log.jsonl` schema once it has enough rows, and add a `respect_count`-holding-`age`-fixed cross-tab (currently the internal analysis varies age; it doesn't yet isolate touch-count independent of age). Also worth a one-line addition: bucket by `slope_per_bar` magnitude against outcome, testing whether our own data replicates or contradicts Bulkowski's "shallow beats steep" finding.

**Kill criterion:** if the cross-tab shows respect-count and age are highly collinear in our sample (i.e., older lines always have proportionally more respects, so they can't be separated), stop trying to build two separate score terms — one composite "maturity" term is sufficient and the literature's disagreement (Bulkowski monotonic vs. our hump-shape) would then be explained by different underlying populations (his: multi-week swing trades; ours: same-day 5m intraday), not a real methodological conflict.

---

## 5. Volume expansion on the break bar — converged but unquantified for our exact case

**Claim:** genuine breaks/breakdowns happen on above-average volume; low-volume breaks are more likely to be liquidity sweeps or noise, especially relevant given §2's finding that the most dangerous break window (11:30-14:00 ET) is also the lowest-volume window (40% below the open-hour, per ToS Indicators above) — **volume and time-of-day are not independent signals, they're measuring overlapping structural reality.**

- `[BLOG]` "Moves accompanied by higher trading volume tend to have a better chance of success... high trading volume signals genuine interest." No quantified backtest found in this pass beyond generic vendor marketing claims (a "90% win rate" figure attributed to one unnamed "algorithmic breakout detection system" was found but is unsourced/unverifiable — **explicitly excluded** from this review's evidence base per doctrine; flagging that it was seen and rejected, not silently omitted). [luxalgo.com — volume confirms breakouts](https://www.luxalgo.com/blog/how-volume-confirms-breakouts-in-trading/)
- No `[ACADEMIC]` or `[EXCHANGE]` source found in this pass that isolates volume-on-break specifically for intraday index-ETF trendline breaks (as opposed to daily-bar chart patterns or generic breakout folklore). This is the weakest-evidenced item in this review — flagged honestly rather than papered over with a confident-sounding blog citation.

**Portable to our stack:** Alpaca's 5m bar payload already includes a `v` (volume) field per bar (same endpoint `trendline_engine.py.fetch_spy_5m` already calls) — this is a genuinely free, zero-new-infra test, but the evidence base for it is the thinnest of anything in this review.

**Smallest test:** add a volume-ratio field (break-bar volume ÷ trailing 20-bar average volume) to the existing `trendline-log.jsonl` rows going forward (a log-only addition, no scoring change — the auditing crew or a follow-up session should make this call, not this literature review), then once ~20+ real breaks have accumulated, check whether high-volume breaks correlate with `status` staying `BROKEN` (vs. quickly flipping back to `TESTING`/`INTACT`) more often than low-volume breaks.

**Kill criterion:** given how thin the evidence base is here, this is the first item to drop if the eventual sample shows no discriminating power — don't sink further build effort into it without at least a directional signal from our own log first.

---

## 6. Trendline break vs. horizontal-level break: thin, mixed, low priority given existing infra

**Claim:** horizontal support/resistance breaks are "cleaner" with more immediate follow-through; trendline breaks capture trend-angle information earlier but are noisier and harder to define precisely (where exactly does a diagonal line "break"?).

- `[BLOG]` "Generally, horizontal S/R breaks tend to be cleaner and show more immediate follow through... Trendline Breakouts follow diagonal resistance or support lines, often capturing breakouts earlier in trend changes, while Horizontal Breakouts break fixed price levels, making them easier to spot but often slower to form." [tradeciety.com](https://tradeciety.com/trading-horizontal-versus-diagonal-boundary-breakouts), [quantum-algo.com](https://www.quantum-algo.com/blog/guides/trendline-trading-complete-guide/)
- **Best available academic grounding for horizontal levels specifically (not a trendline paper, but the closest rigorous analogue):** `[ACADEMIC]` Osler, C. (2000), *"Support for Resistance: Technical Analysis and Intraday Exchange Rates,"* FRBNY Economic Policy Review 6(2), pp.53-68 — analyzed real interbank stop-loss/take-profit order clustering data and found strong evidence that dealer-published support/resistance levels **do** predict intraday trend interruptions, AND that trends tend to be **unusually rapid after price crosses such levels** (i.e., a genuine level break is followed by accelerated, not decelerated, movement — a real mechanism, not folklore, though this is horizontal-level literature, not trendline literature specifically). [FRBNY PDF via ResearchGate](https://www.researchgate.net/profile/Carol-Osler/publication/5050393_Support_for_Resistance_Technical_Analysis_and_Intraday_Exchange_Rates/), [Osler (2003) follow-up, Journal of Finance 58(5)](https://onlinelibrary.wiley.com/doi/abs/10.1111/1540-6261.00588)
- `[ACADEMIC]` Zapranis, A. & Tsinaslanidis, P. (2012), *"Identifying and evaluating horizontal support and resistance levels: an empirical study on US stock markets,"* Applied Financial Economics 22(19):1571-1585 — a rule-based algorithmic HSAR detector evaluated for trend-reversal prediction and abnormal-return generation on US equities; methodologically the closest external analogue to what `key-levels.json`'s level detector already does. [ideas.repec.org](https://ideas.repec.org/a/taf/apfiec/v22y2012i19p1571-1585.html)

**Portable to our stack:** we already run BOTH a horizontal-level detector (`key-levels.json`, `today-bias.json`) and this diagonal trendline detector as **separate** systems — the literature doesn't give a strong reason to merge them, but Osler's "acceleration after a genuine break" finding is a testable, falsifiable claim independent of which line-type triggered it.

**Smallest test:** low priority relative to §2-4 — if pursued, the cheapest version is checking whether the `respect_count`/`violations`-scored trendline breaks in the log show faster post-break displacement than horizontal `key-levels.json` breaks in the same window, using data already logged by both systems.

**Kill criterion:** this item is speculative-priority already; drop it without regret if §2-5 absorb the available research/build budget.

---

## 7. The honest null literature — read this before ratifying anything above

Per OP-33 (verify, don't claim) and the standing no-oversell rule, this section is not optional framing — it's load-bearing for how much confidence to put in everything above.

- `[ACADEMIC]` Sullivan, R., Timmermann, A. & White, H. (1999), *"Data-Snooping, Technical Trading Rule Performance, and the Bootstrap,"* Journal of Finance 54(5):1647-1691. Re-ran Brock/Lakonishok/LeBaron's (1992) universe of technical rules on 100 years of Dow data using White's Reality Check bootstrap to correct for data-snooping bias across the full universe of rules tested (not just the best one in hindsight) — found the earlier strong in-sample result **did not survive** a clean 10-year out-of-sample window once snooping bias was accounted for. [onlinelibrary.wiley.com](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00163)
- `[ACADEMIC]` Malkiel, B., *A Random Walk Down Wall Street* — the canonical academic-adjacent skeptic position: technical analysis "does not give investors a dependable way to beat the market," and his classroom coin-flip experiment (a chartist recommended buying a stock whose entire history was generated by literal coin flips) is the standard illustration of pattern-recognition-on-noise. [en.wikipedia.org/wiki/A_Random_Walk_Down_Wall_Street](https://en.wikipedia.org/wiki/A_Random_Walk_Down_Wall_Street)
- `[ACADEMIC-preprint]` Mesfin (2026) — already cited in §3 — is the single most directly relevant null result in this entire review: a 2026-dated, methodologically rigorous falsification study on a highly liquid, algo-dominated, retail-accessible index-futures instrument (MNQ) that is structurally the closest external analogue to SPY 0DTE intraday trading available. **No breakout, retest, gap, volume, or momentum signal family — 14 tested — cleared institutional significance thresholds** after realistic transaction costs. The paper's own framing (walk-forward, T≥2.0, N≥30, positive-after-costs, multi-year stable, validated against known-positive controls) is close to the bar this repo's own promotion-gate doctrine (OP-11's eval-first gate, OP-25's real-fills-only rule) already tries to hold itself to.
- **Countervailing evidence that keeps the door open (this is not a total-null field):** `[ACADEMIC]` Lo, Mamaysky & Wang (2000), *"Foundations of Technical Analysis,"* Journal of Finance / NBER WP 7613 — kernel-regression pattern recognition across US stocks 1962-1996 found several technical indicators "do provide incremental information and may have some practical value," and a follow-up `[ACADEMIC]` Savin, Weller & Zvingelis study building on that method found head-and-shoulders-conditioned strategies produced 5-7%/year risk-adjusted excess returns. `[ACADEMIC]` Chang & Osler (1999), *"Methodical Madness,"* found H&S patterns profitable for some FX pairs (mark, yen) but not others (CAD, CHF, FRF), and even where profitable, **dominated by simpler filter rules** — i.e. the pattern-recognition complexity wasn't earning its keep. [NBER PDF](https://www.nber.org/system/files/working_papers/w7613/w7613.pdf), [Savin et al.](https://academic.oup.com/jfec/article-abstract/5/2/243/785044), [Chang & Osler](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=51421)

**Synthesis:** the field's honest position, ~25 years of accumulated evidence, is: *some* technical patterns carry *some* real information in *some* markets/regimes, the effect sizes are modest (single-digit % annualized in the strongest cross-sectional daily-bar studies), they are NOT robust to naive data-snooping, and the most recent rigorous intraday-futures falsification study (closest analogue to what we're doing) found nothing survives realistic costs. **This matches, almost exactly, the shape of our own internal trendline-break-retest result** (positive raw expectancy, striking W/L ratio, fails the win-rate promotion gate, P&L concentrated in 2 of 20 trades on one trend day) — that is a *good* sign for the honesty of our own backtest discipline, not a bad sign for the strategy. It means keep testing the specific, falsifiable sub-claims in §1-6 rather than ratifying "trendline breaks = tradeable signal" as a blanket proposition.

---

## Recommended next steps (ranked, none of these are orders/param-flips — they're research/backtest work items)

1. **Cheapest + highest-signal-for-J's-specific-question:** re-slice `trendline-log.jsonl` by ET hour and confirm/deny that today's 12:10-12:15 break sits in a historically low-follow-through bucket, using the same method `trendline_tod_breakdown.py` already applies to the sibling setup (§2).
2. **Second cheapest:** run `sweep_trendline_break_retest.py` with an immediate-entry variant against the existing retest baseline, same IS/OOS window, to find out whether SPY 0DTE looks more like the optimistic blog claim or the MNQ falsification result (§3).
3. **Needs the audit crew's schema to stabilize first:** extend `trendline_age_analysis.py`'s bucket logic to `trendline_engine.py`'s new log once row count is sufficient, and add the respect-count-holding-age-fixed cross-tab plus a slope-magnitude bucket (§4).
4. **Log-only, zero scoring risk:** add a volume-ratio field to `trendline-log.jsonl` rows going forward for future evaluation — do not wire it into scoring yet, evidence is too thin (§5).
5. **Lowest priority:** trendline-vs-horizontal-break differential test, only if 1-4 leave budget (§6).

None of these require touching `trendline_engine.py`'s core detection logic — they're either pure re-slices of data already logged, or additive log fields, or A/B runs of existing harness scripts. That keeps this work fully outside the in-flight audit crew's lane per the hard constraint.

---

## Full citation list (quality-tagged)

**ACADEMIC / peer-reviewed or Fed-quality:**
- Lo, Mamaysky & Wang (2000), "Foundations of Technical Analysis," J. Finance / NBER WP7613 — [nber.org/system/files/working_papers/w7613/w7613.pdf](https://www.nber.org/system/files/working_papers/w7613/w7613.pdf)
- Savin, Weller & Zvingelis, "The Predictive Power of Head-and-Shoulders Price Patterns," J. Financial Econometrics 5(2) — [academic.oup.com/jfec/article-abstract/5/2/243/785044](https://academic.oup.com/jfec/article-abstract/5/2/243/785044)
- Chang & Osler (1999), "Methodical Madness," Economic Journal — [papers.ssrn.com/sol3/papers.cfm?abstract_id=51421](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=51421)
- Brock, Lakonishok & LeBaron (1992), "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns," J. Finance 47(5) — [onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x)
- Sullivan, Timmermann & White (1999), "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap," J. Finance 54(5) — [onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00163](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00163)
- Osler (2000), "Support for Resistance: Technical Analysis and Intraday Exchange Rates," FRBNY Economic Policy Review 6(2) — [researchgate.net/profile/Carol-Osler](https://www.researchgate.net/profile/Carol-Osler/publication/5050393_Support_for_Resistance_Technical_Analysis_and_Intraday_Exchange_Rates/)
- Osler (2003), "Currency Orders and Exchange-Rate Dynamics," J. Finance 58(5) — [onlinelibrary.wiley.com/doi/abs/10.1111/1540-6261.00588](https://onlinelibrary.wiley.com/doi/abs/10.1111/1540-6261.00588)
- Zapranis & Tsinaslanidis (2012), "Identifying and evaluating horizontal support and resistance levels," Applied Financial Economics 22(19) — [ideas.repec.org/a/taf/apfiec/v22y2012i19p1571-1585.html](https://ideas.repec.org/a/taf/apfiec/v22y2012i19p1571-1585.html)
- Malkiel, *A Random Walk Down Wall Street* — [en.wikipedia.org/wiki/A_Random_Walk_Down_Wall_Street](https://en.wikipedia.org/wiki/A_Random_Walk_Down_Wall_Street)
- Mesfin, M. (2026), "Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study," arXiv:2605.04004 [q-fin.TR] (preprint) — [arxiv.org/abs/2605.04004](https://arxiv.org/abs/2605.04004)

**EXCHANGE:**
- CBOE, "0DTE Index Options and Market Volatility: How Large is Their Impact?" (PDF binary — extracted via secondary summary, flagged) — [cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf)
- CBOE Insights, "Evaluating the Market Impact of SPX 0DTE Options" — [cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options](https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options/)

**PRACTITIONER (transparent methodology / real sample sizes):**
- Bulkowski, "Up-Sloping Trendlines," ThePatternSite.com (N=3,172 trades) — [thepatternsite.com/uptrendlines.html](https://thepatternsite.com/uptrendlines.html)
- ToS Indicators, "Should You Trade During the Lunch Time Hour?" (SPY 2008-2021) — [tosindicators.com/research/should-you-trade-during-the-lunch-time-hour](https://tosindicators.com/research/should-you-trade-during-the-lunch-time-hour)
- QuantPedia, "Lunch Effect in the U.S. Stock Market Indices" (SPY 2010-2024) — [quantpedia.com/lunch-effect-in-the-u-s-stock-market-indices](https://quantpedia.com/lunch-effect-in-the-u-s-stock-market-indices/)
- Edgeful, "5-Minute Opening Range Breakout on ES" (N=115, 6mo) — [edgeful.com/blog/posts/5-minute-opening-range-breakout-es-strategy](https://www.edgeful.com/blog/posts/5-minute-opening-range-breakout-es-strategy)

**BLOG (directional / mechanism-descriptive only, no rigorous sample cited):**
- EdgeFlo, "Break of Structure: Body Close vs Wick Rules" — [edgeflo.com/blog/break-of-structure-trading](https://www.edgeflo.com/blog/break-of-structure-trading)
- Forex Mentor Online, "Support/Resistance Don't Get Stronger with Multiple Touches" — [forexmentoronline.com/support-resistance-levels-dont-become-stronger-with-multiple-touches](https://forexmentoronline.com/support-resistance-levels-dont-become-stronger-with-multiple-touches/)
- XS.com, "Break and Retest Trading Explained" — [xs.com/en/blog/break-retest-trading](https://www.xs.com/en/blog/break-retest-trading/)
- Tradeciety, "Trading Horizontal Versus Diagonal Boundary Breakouts" — [tradeciety.com/trading-horizontal-versus-diagonal-boundary-breakouts](https://tradeciety.com/trading-horizontal-versus-diagonal-boundary-breakouts)
- Quantum Algo, "Trendline Trading: Complete Guide" — [quantum-algo.com/blog/guides/trendline-trading-complete-guide](https://www.quantum-algo.com/blog/guides/trendline-trading-complete-guide/)

**Internal (this repo — cross-referenced, not external, cited for convergence/divergence checks):**
- `analysis/backtests/trendline_break_retest_findings.md` — first-pass backtest, 2026-05-08
- `backtest/autoresearch/results/trendline_age_analysis.txt` — age-bucket IS/OOS results
- `backtest/autoresearch/trendline_tod_breakdown.py` — docstring confirms `midday_trendline_gate` already exists for a sibling setup
