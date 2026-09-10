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


---

# PART 2 — Trendline CONSTRUCTION canon (external research, 2026-09-09)

> Sonnet web-research crew, fired by Fable 2026-09-09 23:15 ET after J flagged the engine's `[GTL] [WICK] SUPPORT | touch x3` line as not touching 3 times while his own 08:30-ET-anchored line does. Part 1 above covers BREAKS; this part covers how a line is BUILT. Every rule cites a source; UNVERIFIED items are flagged in the last section. Plan that consumes this: [`KEY-LEVELS-CHART-READING-HANDOFF.md` §9](../0dte/KEY-LEVELS-CHART-READING-HANDOFF.md#9-ta-dial-in-work-order-2026-09-09).


Context: engine's auto-fitted "support" line claims 3 touches it doesn't visibly have; trader's
hand-drawn line anchored at 08:30 ET premarket wick low is the "real" lower boundary of a
descending wedge. This report gathers sourced rules to encode a correct auto-fitter.

---

## 1. Trendline construction rules (classic + modern canon)

**Edwards & Magee — *Technical Analysis of Stock Trends* (1948, later eds w/ Bassetti)**
- RULE — Two points are the geometric minimum to draw a line; **a third touch is what confirms
  it as valid** ("It takes two points to draw a trend line, and the third one confirms the
  validity.") — restated across multiple secondary sources summarizing E&M; direct verbatim E&M
  text not retrievable from a scanned/OCR source in this session, so treat the *exact wording* as
  UNVERIFIED even though the *rule* is the standard attribution. Source: [Grokipedia trend line
  page](https://grokipedia.com/page/Trend_line_(technical_analysis)), [CMT Association PDF —
  "The Edwards & Magee Toolkit: Trendlines, Basing Points, Patterns"](https://cmtassociation.org/wp-content/uploads/2024/01/charlesbassetti-011911-1.pdf).
- RULE — The lows (uptrend) or highs (downtrend) used as anchor points should be a "reasonable"
  distance apart — too close and the line is not meaningfully validated; too far and it may not
  reflect the current trend regime. Distance is timeframe- and volatility-dependent, not a fixed
  number. Source: same summary material above (E&M attribution, paraphrased).
- RULE — Steeper trendlines are less reliable / more easily penetrated than shallow ones — "the
  steeper the trendline, the more easily it is penetrated," and chartists are warned against
  drawing "unrealistic trendlines" off a single sharp spike. This phrasing appears directly in
  Murphy (see §1 Murphy below) under a heading "The Relative Steepness of the Trendline," which
  is itself continuing the Edwards & Magee tradition — Murphy's book explicitly builds on E&M.
  Source: [archive.org full text of Murphy, *Technical Analysis of the Financial
  Markets*](https://archive.org/stream/JohnJ.MurphyTechnicalAnalysisOfTheFinancialMarkets/John_J._Murphy_-_Technical_Analysis_Of_The_Financial_Markets_djvu.txt).

**John Murphy — *Technical Analysis of the Financial Markets*, ch. 4 ("Basic Concepts of Trend")**
- RULE — A valid trendline break requires **both** a percentage-penetration filter and a
  time filter: commonly cited as price must **close roughly 3% beyond the line** and **stay
  beyond it for two consecutive days** before the break is treated as confirmed, rather than
  reacting to the first single-bar penetration. **UPDATE 2026-09-09: primary text now reached —
  see "Murphy 3%/2-day rule — provenance check (2026-09-09)" below.** Verdict:
  VERIFIED-PRIMARY on the two numbers (3%, two days) and their existence in Murphy ch. 4
  pp.71-72, but **the "both/AND" framing above is itself a mild misattribution** — Murphy
  presents the percentage filter and the time filter as *alternative* filter types ("An
  alternative to a price filter... is a time filter"), not a joint requirement. Do not carry
  the "requires both" wording forward; see the provenance-check section for the exact quotes
  and the SPY-timeframe scope finding. Original (superseded) secondary source used before
  primary-text access: [finaccfundas.blogspot.com summary of Murphy's
  rules](https://finaccfundas.blogspot.com/2014/09/john-murphy-rules-of-technical-trading.html).
- RULE — Steepness matters: an extremely steep line drawn off an abnormal short-term spike is
  "unrealistic" and should be redrawn once the market provides a second, more representative
  pivot — directly supported by the phrase captured from the text: *"the steeper the trendline,
  the more easily it is penetrated."* Source: [archive.org Murphy full
  text](https://archive.org/stream/JohnJ.MurphyTechnicalAnalysisOfTheFinancialMarkets/John_J._Murphy_-_Technical_Analysis_Of_The_Financial_Markets_djvu.txt) (verbatim phrase confirmed).
- RULE — **Internal trendlines** (ch. 4, p.90 per table of contents) — when the "ideal" line
  drawn to the absolute extreme point cuts through a cluster of intervening prices, Murphy
  teaches drawing the line through the area of *most* prices (an internal trendline) rather than
  forcing it through the single extreme spike, accepting that the extreme point becomes an
  overshoot/wick outlier rather than the anchor. NOTE: page/section existence confirmed via table
  of contents; exact body wording not retrieved verbatim this session — treat as UNVERIFIED
  detail, VERIFIED concept-existence. Source: [archive.org Murphy full
  text](https://archive.org/stream/JohnJ.MurphyTechnicalAnalysisOfTheFinancialMarkets/John_J._Murphy_-_Technical_Analysis_Of_The_Financial_Markets_djvu.txt) TOC.
- RULE — **Channel line** (ch. 4, p.80) — once a basic trendline (support in an uptrend, e.g.)
  is drawn from two points, a parallel "return line" / channel line is projected off the single
  most prominent opposite extreme (the highest high, for an ascending channel) to define the
  channel's far boundary — this is the same construction Bulkowski calls a "3-point channel"
  (see §1 Bulkowski below). Concept-existence confirmed via TOC; body text UNVERIFIED this
  session.

**Thomas Bulkowski — *Encyclopedia of Chart Patterns* / thepatternsite.com**
- RULE — For rectangle-type / two-line patterns, price should touch **each** trendline **at
  least twice** at distinct minor highs (top line) / minor lows (bottom line) before the pattern
  is considered validly bounded. Source: [Bulkowski, "Up-Sloping
  Trendlines"](https://thepatternsite.com/uptrendlines.html) and ["Down-Sloping
  Trendlines"](https://thepatternsite.com/trenddown.html) (thepatternsite.com).
- RULE — Up-sloping trendline: draw along the price *valleys* (lows); price should touch the
  line and rise away from it without piercing it — a touch that pierces meaningfully is not a
  clean touch. Down-sloping: draw along the price *peaks* (highs); same non-piercing
  expectation. Source: [Bulkowski uptrendlines](https://thepatternsite.com/uptrendlines.html),
  [Bulkowski down-trendlines](https://thepatternsite.com/trenddown.html).
- RULE — **3-Point Channel method** — draw line AB through two peaks (or two troughs), extend it
  into the future, then draw a second line *parallel* to AB through the single intervening
  trough (or peak) C between A and B, and extend that parallel line — this is Bulkowski's
  explicit channel-construction technique, directly analogous to Murphy's channel/return line.
  Source: [Bulkowski, "Drawing 3 Point
  Channels"](https://thepatternsite.com/3PointChannels.html).
- RULE (chart-pattern "mirrors" concept) — Bulkowski's touch-counting for broadening/wedge
  patterns explicitly tolerates a touch that falls slightly short of the line if it is "close
  enough" — i.e., touch tolerance is a judgment band, not an exact-price hit. Source: search
  summary of [Bulkowski, "Broadening
  Bottoms"](https://thepatternsite.com/broadb.html) (a touch "falling a bit short of the line,
  but close enough" is explicitly accepted as a valid touch in his pattern-identification
  methodology).
- STATS — Falling wedge (Bulkowski's Encyclopedia stats): breaks **upward 68%** of the time (not
  100%); break-even failure rate for upward breaks is **26%** (i.e., 74% of upward breaks travel
  ≥5% before reversing); **throwback rate 62%** (majority of breakouts retest the broken
  trendline — supporting "wait for retest" over "chase the break"); measured-move target hit
  rate **62%**; overall rank **31st of 39** bullish patterns (weak-to-mediocre, not a strong
  edge). Source: [Bulkowski, "Falling Wedges"](https://thepatternsite.com/fallwedge.html).
- STATS — Descending broadening wedge: overall rank 27/39 (up-breakout) and 29/36
  (down-breakout); break-even failure rate 18% (up) / 35% (down); n=757 perfect trades studied;
  downward breakouts are comparatively rare, most occur in bull markets with upward breaks.
  Source: [Bulkowski, "Descending Broadening
  Wedges"](https://thepatternsite.com/dbw.html).

**Victor Sperandeo — *Trader Vic: Methods of a Wall Street Master* (the 1-2-3 rule)**
- RULE — The **correct trendline in a downtrend** is drawn through exactly two points: (1) the
  high that immediately *precedes* the absolute low of the move, and (2) the *first* high the
  down-move started from — i.e., anchor at the extreme, then to the nearest preceding
  countertrend high, NOT an arbitrary earlier high. Source: [3candlereversal.com summary of
  Sperandeo's method](https://www.3candlereversal.com/post/victor-sperandeo-reversal-patterns/);
  [mkatsanos.com, "Sperandeo's 1-2-3 System"](https://mkatsanos.com/sperandeos-1-2-3-system/).
- RULE — **The line must never cross through intervening price** — if a straight line from
  point 1 to the farthest candidate point 2 would cut through the chart (pass through price
  bars), Sperandeo's method requires moving point 2 inward to the *next closer* high/low until
  the line clears all intervening bars without crossing them. This is the literal answer to "the
  line may not cut through bars" — Sperandeo makes it definitional, not optional. Source:
  [mkatsanos.com](https://mkatsanos.com/sperandeos-1-2-3-system/); [instaforex.com, "Victor
  Sperandeo Trading Method"](https://www.instaforex.com/knowledge_base/566-victor-sperandeo-trading-method).
- RULE — **1-2-3 trend-change confirmation** (validation sequence, not just line-drawing): (1)
  price breaks the trendline; (2) price retests the broken line/old extreme from the other side
  and *fails* to re-cross it; (3) price then breaks the prior minor swing point in the new
  direction. Only after all three does Sperandeo treat the trend as reversed — a single
  trendline break alone is explicitly NOT sufficient confirmation. Source: [Bulkowski, "The 1-2-3
  Trend Change"](https://thepatternsite.com/123tc.html) (Bulkowski's own treatment of Sperandeo's
  rule); [roboforex.com blog on the 1-2-3
  reversal](https://blog.roboforex.com/blog/2020/02/11/trading-like-sperandeo-1-2-3-reversal-and-2b-pattern/).

**Al Brooks — *Trading Price Action Trends* / Brooks Trading Course**
- RULE — A trend (channel) line needs only **two pushes** to draw — connect the first two swing
  points and project the line forward; the **third touch is the trade signal** (watch for
  reversal/reaction as price approaches the line a third time), functionally the same
  2-draw/3-confirm logic as Edwards & Magee but framed as an active trading trigger rather than a
  passive validity rule. Source: [Shortform summary of Brooks, *Trading Price Action
  Trends*](https://www.shortform.com/summary/trading-price-action-trends-summary-al-brooks");
  [Brooks Trading Course, "10 Best Price Action Trading
  Patterns"](https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/).
- RULE — **Wedge = three pushes** (occasionally four or five) in the same direction with each
  push showing diminishing momentum/overlap — Brooks explicitly counts *pushes*, not just two
  trendline touches, as the pattern's defining structure; the standard trade is to fade the third
  push with a stop beyond the wedge's extreme, or wait for the break of the near trendline.
  Source: [Brooks Trading Course "10 best patterns"
  page](https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/);
  [Shortform Brooks summary](https://www.shortform.com/summary/trading-price-action-trends-summary-al-brooks).
- RULE — **Micro channel** — a run of consecutive same-direction candles with minimal overlap,
  usually appearing near the edge of a range; Brooks treats a micro channel as a high-probability
  continuation/breakout signal distinct from an ordinary trend channel, and warns that trying to
  fade a micro channel early is low-probability. Source: [arongroups.co summary of Brooks on
  trading ranges](https://arongroups.co/technical-analyze/al-brooks-trading-ranges/).
- RULE — Brooks generally favors **body/close-based reads for trend structure and signal bars**
  (his "signal bar" and "trend bar" definitions are close-relative-to-open based), while using
  wick extremes mainly for stop placement — i.e., Brooks does NOT use a single consistent
  wick-only or body-only convention for trendlines themselves; his emphasis is on reading bar
  *closes* for momentum/trend-strength judgments. This is a general characterization from summary
  sources, not a verbatim Brooks quote — UNVERIFIED at the sentence level, but consistent across
  multiple independent secondary descriptions of his method.

**Peter Brandt / Wyckoff**
- No sourced material was found in this session specific to Peter Brandt's or Richard Wyckoff's
  explicit trendline-construction rules (touches, tolerance, steepness). Wyckoff's own
  contribution is mainly to trading-range/accumulation-distribution theory rather than a
  distinct trendline-touch methodology, and no primary or secondary source surfaced in searches
  this session with a citable, specific rule attributable to either. **Flag as a gap** — do not
  encode anything under their names without further sourcing.

---

## 2. Wedge / channel definitions

- RULE — **Falling (descending) wedge**: both boundary lines slope downward and converge; lower
  highs AND lower lows, narrowing range. Bulkowski's stats (68% up-break rate, 62% throwback, 26%
  break-even failure) are given above. Source: [Bulkowski, "Falling
  Wedges"](https://thepatternsite.com/fallwedge.html).
- RULE — **Descending broadening wedge** (diverging, not converging) is a separate pattern from
  the falling wedge — lines slope down but *widen* apart rather than converge; distinctly worse
  overall statistical rank (27–29th of 36–39). Source: [Bulkowski, "Descending Broadening
  Wedges"](https://thepatternsite.com/dbw.html).
- RULE — Brooks' wedge = **3 pushes** (see §1); the two boundary lines are chosen by connecting,
  respectively, the sequence of push-highs and the sequence of push-lows — NOT by connecting
  arbitrary highs/lows, but specifically the extremes of each of the 3 (or more) pushes. Source:
  [Brooks Trading Course](https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/).
- RULE — On practitioner handling of "touching the top/bottom of the wedge": the throwback
  statistic (62% for falling wedges, per Bulkowski) is explicitly cited by conservative traders
  as the reason to **wait for the break + retest**, not fade every touch of the boundary — a
  bare touch of the wedge boundary is a *lower-confidence* fade than a confirmed breakout +
  successful retest. Source: [Bulkowski, "Falling
  Wedges"](https://thepatternsite.com/fallwedge.html) (throwback-rate framing).
- RULE — Channel construction (both Murphy's "return line" and Bulkowski's "3-point channel," and
  Brooks' basic channel line) is convergent across sources: **draw the primary trendline off two
  points, then draw the parallel/channel boundary off the single best opposite-extreme point** —
  never independently curve-fit the second line to its own two points. Sources: as cited in §1
  above (Murphy TOC, Bulkowski 3PointChannels, Brooks channel-line described in Shortform
  summary).

---

## 3. Premarket / extended-hours data in intraday trendline/level construction

- RULE — Premarket high/low levels (roughly 06:00–09:30 ET session, or the ES/Globex overnight
  session before that) are treated as legitimate, commonly-watched key levels for SPY/ES day
  trading — multiple independent practitioner sources describe marking the premarket/overnight
  high and low as standard daily prep, on par with prior-day high/low. Source: [justintrading.com,
  "Premarket High and Low in Futures: How to Use
  Them"](https://justintrading.com/premarket-high-low-futures/); [navixa.io, "SPY Futures
  Trading: Navigating Pre-Market Trends"](https://navixa.io/blog/spy-futures-trading-pre-market-trends);
  ["Globex Breakout Strategy" description — marking the overnight session's high/low ahead of the
  08:30 ET data releases and the 09:30 ET open](https://kr.tradingview.com/chart/ES1%21/IZ9gKAA5-Pre-Market-Levels-are-CRITICAL-in-Day-Trading-10X-Gains-For-Me)
  (TradingView community chart-idea, practitioner-level not academic).
- RULE — It is common and explicitly recommended practice for SPY/ES intraday traders to use
  **ES futures' near-24-hour session** for overnight/premarket structure (since SPY itself only
  trades premarket at low liquidity while ES trades continuously), then map those ES-derived
  levels onto the SPY chart. Source: [futurestradingpro.substack.com, "Inside Day on ES/SPX:
  Watch These Key Levels/Setups"](https://futurestradingpro.substack.com/p/inside-day-on-esspx-watch-these-key");
  [navixa.io](https://navixa.io/blog/spy-futures-trading-pre-market-trends).
- IMPLICATION for this engine — the trader's practice of anchoring the trendline at the 08:30 ET
  premarket wick low is squarely inside standard practice (08:30 ET is explicitly called out
  across multiple sources as the highest-volatility premarket moment, tied to scheduled economic
  data releases, and is exactly the kind of "premarket wick extreme" practitioners mark as a key
  level). No source found that argues premarket bars should be *excluded* from trendline/level
  construction on SPY/ES — the debate found in this research is wick-vs-close (see §4), not
  regular-hours-only vs. extended-hours-included.

---

## 4. Wick vs. body/close anchoring

- RULE — Practitioner consensus (non-academic, but consistent across multiple independent
  sources) frames this as a genuine, unresolved stylistic choice, not a settled rule: **wicks**
  capture the true price extreme / every attempt the market made to move further, but are
  vulnerable to being driven by a single emotional/liquidity-driven spike; **bodies/closes**
  filter out that noise and better reflect where the market was willing to *transact* and hold,
  at the cost of ignoring real (if brief) price extremes. Source: [Trade2Win forum discussion,
  "Bodies or Wicks?"](https://www.trade2win.com/threads/bodies-or-wicks.174754/); [RSIwave, "How
  to Draw Trend Lines Perfectly Every Time"](https://rsiwave.com/how-to-draw-trend-lines/);
  [OnEquity, "Professional Guide to Drawing and Trading
  Trendlines"](https://onequity.com/mastering-trendlines-how-to-draw-validate-and-trade-them-like-a-market-professional/).
- RULE — A commonly recommended heuristic (not attributable to one named canonical author, but
  repeated across secondary sources): **start with wicks; if the wick-based line is repeatedly
  violated by closes but never violated by full candle bodies, switch to a body-based line** —
  i.e., let the market tell you which anchoring the current regime respects. Source:
  [OnEquity](https://onequity.com/mastering-trendlines-how-to-draw-validate-and-trade-them-like-a-market-professional/);
  [RSIwave](https://rsiwave.com/how-to-draw-trend-lines/).
- RULE — Al Brooks leans toward reading bar **bodies/closes** for trend-strength and signal-bar
  judgments (his trend-bar/signal-bar vocabulary is close-relative-to-open), while still using
  wick extremes for stop placement — i.e., Brooks does not treat "all-wick" as the default; he
  mixes them by *purpose* (structure = close-based, risk = wick-based), which is a notably
  different design than "never mix" — see §5 for what this implies for the engine's stated rule.
- ON THE ENGINE'S "all-wick OR all-body, never mixed" rule — **no source found explicitly states
  this as a formal rule.** It is a reasonable, internally-consistent engineering simplification
  (pick one basis and stay consistent within a single line so the line's slope isn't
  contaminated by mixing two different price series), and it is *compatible* with the
  wick-then-switch-to-body heuristic above (which also switches the *whole* line's basis at once,
  never point-by-point) — but it should be reported as an ENGINEERING CHOICE consistent with
  practitioner heuristics, not a canon rule with a named source. Bulkowski, Murphy, and E&M all
  discuss "touches" without specifying wick-only or body-only universally; Brooks explicitly uses
  both, by purpose, in the same analysis.

---

## 5. Algorithmic trendline fitting (open literature / community scripts)

- METHOD — **Pivot-based fitting (dominant approach)**: nearly every open-source
  implementation (LuxAlgo "Trendlines with Breaks," the Python libs `trendln`/`pytrendline`,
  academic papers) first reduces the bar series to **pivot highs/lows** (a zigzag/fractal-style
  local-extrema filter over a lookback window), then fits lines only through pivot points — never
  through every bar — because fitting through all bars (plain OLS regression) tends to produce a
  line that doesn't track the actual reaction points traders react to. Source: [LuxAlgo
  "Trendlines with Breaks" description — "calculates upward and downward sloping trendlines based
  on pivot highs and lows over a customizable lookback
  period"](https://www.luxalgo.com/library/indicator/trendlines-with-breaks/); [GregoryMorse/trendln
  GitHub — "calculates support and resistance information including local extrema, average and
  their trend lines"](https://github.com/GregoryMorse/trendln); [ednunezg/pytrendline
  GitHub](https://github.com/ednunezg/pytrendline) — "pivot points are identified as local
  maximum/minimum points... the algorithm speeds up if the search is narrowed to lines with pivot
  points as one of the start/end points."
- METHOD — **Slope-selection method varies** (this is the "how steep" question, made concrete):
  LuxAlgo's default uses **ATR** (average true range) to pick a slope so the line's steepness
  scales with recent volatility (a shallower slope in a quiet market, steeper in a volatile one)
  rather than a fixed angle; alternatives offered are **standard deviation** (Stdev) of price, or
  a **linear-regression** slope fit to the points. This directly operationalizes E&M/Murphy's
  "steeper = less valid" concern into a numeric, volatility-normalized bound. Source: [LuxAlgo
  "Trendlines with Breaks" library
  page](https://www.luxalgo.com/library/indicator/trendlines-with-breaks/) (slope-method
  description recovered via web search summary; direct doc page fetch failed —
  `docs.mt.luxalgo.com` DNS error this session, so treat exact wording as **UNVERIFIED**,
  concept as cross-confirmed by two independent search-result summaries).
- METHOD — **Extremal/geometric fit vs. least-squares regression**: one line of academic/
  engineering work (the "Evolutionary Optimized Stock Support-Resistance Line Detection" paper,
  and the "brute-force on pivot points" approach described for at least one open-source project)
  explicitly rejects plain linear regression across all closes in favor of either (a) an
  **exhaustive/brute-force search over candidate pivot-point pairs** (worst case O(N³) checking
  every point-pair-extension combination), scored by number of touches / total "respect," or (b)
  an **evolutionary/optimization search** over line parameters (slope, intercept) maximizing a
  fitness function that rewards touches and penalizes body/price violations. Regression-on-all-
  closes is explicitly used as a *simpler baseline*, not the preferred production method, in the
  sourced material. Source: [ResearchGate, "Evolutionary Optimized Stock Support-Resistance Line
  Detection for Algorithmic Trading
  Systems"](https://www.researchgate.net/publication/337423371_Evolutionary_Optimized_Stock_Support-Resistance_Line_Detection_for_Algorithmic_Trading_Systems)
  (abstract: "Linear regression is applied to close prices of the last n days to detect the trend
  line" as the baseline being improved upon); [MDPI, "Support Resistance Levels towards
  Profitability in Intelligent Algorithmic Trading
  Models"](https://www.mdpi.com/2227-7390/10/20/3888) (swing-high/swing-low detection via a
  Depth/Deviation/Backstep zigzag-style function, closely mirroring the classic MetaTrader ZigZag
  indicator's parameters).
- METHOD — **Touch tolerance as a price-scaled band, not exact-price hit**: the sourced
  literature and community scripts consistently score a "touch" as *near* the line within some
  tolerance band (an ATR fraction, a percent-of-price band, or a fixed tick tolerance) rather than
  requiring the bar to hit the line's exact computed price — this operationalizes Bulkowski's
  "close enough" touch-tolerance judgment call (§1) into a numeric parameter. Source: general
  characterization across [LuxAlgo](https://www.luxalgo.com/library/indicator/trendlines-with-breaks/),
  [pytrendline](https://github.com/ednunezg/pytrendline) ("tuning parameters" mentioned in repo
  description), and [MDPI paper](https://www.mdpi.com/2227-7390/10/20/3888) (Deviation parameter
  in the zigzag). Exact tolerance formula not retrieved verbatim from any single source this
  session for any one implementation — treat specific numeric defaults as UNVERIFIED without
  reading each project's source code directly.
- METHOD — **"Must not pass through price" as a hard constraint**: this is the single most
  consistent design principle across both the classic canon (Sperandeo's explicit "move point 2
  inward until the line clears the chart" rule, §1) and the algorithmic literature (the brute-
  force/evolutionary search papers explicitly score or reject candidate lines that cut through
  intervening bar bodies/wicks) — this is the strongest, most cross-source-agreed rule in this
  entire research set. Source: Sperandeo rule as attributed above
  ([mkatsanos.com](https://mkatsanos.com/sperandeos-1-2-3-system/)); algorithmic papers cited
  above (candidate-line rejection on intervening-price violation is implicit in "brute-force...
  scored by touches/respect" framing, and explicit in the evolutionary-optimization fitness-
  function framing).
- METHOD — **Breakout/break detection**: LuxAlgo and the general community convention define a
  "break" as **price crossing the projected trendline** in real time (no repaint/backpaint), often
  gated by a confirmation bar or ATR-scaled buffer rather than any single-tick cross — this is
  the algorithmic analogue of Murphy's percent + two-day filter (§1), substituting a volatility-
  scaled buffer + N-bar persistence for Murphy's fixed 3%/2-day numbers. Source: [LuxAlgo
  "Trendlines with Breaks" description — "breakouts occur in real-time and are not subject to
  backpainting"](https://www.luxalgo.com/library/indicator/trendlines-with-breaks/).

---

## Consensus vs. contested

| Question | Consensus | Contested / varies |
|---|---|---|
| Minimum points to draw | 2 points (E&M, Brooks, Sperandeo, Bulkowski all agree) | — |
| Minimum touches to call it "confirmed"/valid | 3rd touch confirms (E&M, Brooks — same number, different framing: E&M = validity, Brooks = trade signal) | Bulkowski's pattern-specific work sometimes only requires 2 touches per boundary for a *pattern* to exist, distinct from "confirmed trendline" |
| Line may not cut through intervening price | Universal — the single most agreed-on rule (Sperandeo explicit; embedded implicitly in every algorithmic touch-scoring method) | — |
| Touch must be exact price hit | No source requires exact-hit; "close enough" tolerance is explicit (Bulkowski) and implicit (all algo tolerance bands) | Exact tolerance *value* (ATR%, price%, ticks) is implementation-specific, no canonical number |
| Steepness limit | Steeper = less valid / more easily broken (E&M/Murphy consensus); algorithmic tools operationalize via ATR/Stdev/linreg-scaled slope | No canonical numeric angle limit anywhere in classic canon — always relative/qualitative |
| Break confirmation needs filter (not first touch) | Consensus that a bare cross shouldn't be acted on instantly — Murphy's 3%/2-day (attribution widely repeated but NOT verified verbatim this session), Sperandeo's full 1-2-3 sequence, LuxAlgo's no-repaint + buffer | Exact numeric filter differs by source/system; no single agreed threshold |
| Wick vs. body/close anchoring | No consensus — genuinely contested; "pick one and be consistent, or switch by regime" is the closest thing to shared practitioner advice | Brooks mixes both by purpose (structure vs. stop) rather than choosing one; academic/algo tools mostly work off bar highs/lows (wick-equivalent) by default |
| Premarket/extended-hours data inclusion for SPY/ES levels | Consensus: include it — premarket/overnight (ES/Globex) highs/lows are standard, widely-marked key levels, 08:30 ET explicitly called a high-volatility premarket moment | No source argues for excluding premarket data on SPY/ES specifically |
| Channel/second line construction | Consensus across Murphy, Bulkowski, Brooks: draw primary line off 2 points, then parallel line off the single opposite extreme — never independently fit line 2 | — |
| "All-wick OR all-body, never mixed" (the engine's stated rule) | Not found as a named canon rule anywhere | Best characterized as a reasonable engineering simplification, partially supported by the "wick-then-switch-to-body-as-regime-shifts" practitioner heuristic, but contradicted by Brooks' by-purpose mixing |

---

## What this implies for an auto-fitter (max 10 bullets)

1. **Never emit a line that passes through any bar's body/wick** (whichever basis is chosen) —
   this is the single most cross-source-agreed constraint; a "3-touch support" that visibly cuts
   through bars is disqualified by every source in this research, not just the trader's eye test.
2. **Require ≥3 touches to label a line "confirmed"**, not just draw-eligible; 2 touches is a
   draft/candidate line, matching E&M/Brooks' 2-draws/3-confirms convention.
3. **Score touches with a tolerance band** (ATR fraction or % of price), not exact-price
   equality — Bulkowski's "close enough" and every algorithmic implementation found here agree a
   touch is a proximity match, not a pixel-perfect hit.
4. **Pick pivots first (zigzag/fractal local extrema over a lookback window), then fit lines
   only through pivots** — never regress across every raw bar; this is the dominant design in
   both community scripts and academic work, and is why the current auto-fitter's line likely
   looks wrong: if it's fitting through arbitrary bars instead of validated pivot lows, a
   "3-touch" claim can be an artifact of loose tolerance + non-pivot points.
5. **Anchor the second (channel/opposite) line as a parallel line off the single most extreme
   opposite point**, not as an independently-fit second regression line — matches Murphy's
   channel line, Bulkowski's 3-point channel, and Brooks' channel construction.
6. **Include premarket/extended-hours bars** in pivot/level detection for SPY 0DTE — this is
   standard, sourced practice for SPY/ES, and the trader's 08:30 ET premarket-wick anchor is
   textbook, not idiosyncratic.
7. **Scale slope/steepness tolerance to recent volatility (ATR)** rather than a fixed angle —
   operationalizes the qualitative "too steep = less valid" rule from E&M/Murphy into a testable
   parameter, matching LuxAlgo's default design.
8. **Gate "line broken" on a buffer + persistence filter**, not the first single-bar cross — the
   spirit of Murphy's percent+2-day rule (numeric specifics unverified verbatim this session) and
   Sperandeo's full 1-2-3 sequence both argue against reacting to first-touch penetration; an ATR-
   scaled buffer + N-bar hold is the algorithmic-literature analogue.
9. **Pick one basis (wick or body) per line and hold it for that line's lifetime**; the "never
   mixed" rule the trader/engine already uses is not a canon citation but IS consistent with the
   closest practitioner heuristic found (start wick, switch whole-line to body if regime
   demands) — keep it, but label it as an engineering convention, not doctrine.
10. **For a wedge specifically, require the two boundary lines to be built from the highs and
    lows of the same sequence of ~3 pushes** (Brooks) with converging slopes (Bulkowski's falling
    wedge definition) — a mislabeled wedge is often just two lines that happen to converge, not
    a shared-push structure, which is a plausible second contributor to the "claims 3 touches but
    doesn't visibly have them" complaint if the auto-fitter is pattern-matching convergence alone.

---

## Verification notes (what to re-check before hard-coding numbers)

- Murphy's 3%/two-day penetration rule: **RESOLVED 2026-09-09 — primary text reached and quoted
  verbatim, ch. 4 pp.71-72.** See "Murphy 3%/2-day rule — provenance check (2026-09-09)" below
  for the full quotes, the misattribution nuance (Murphy presents them as alternatives, not a
  joint AND-rule), and — the part that actually matters for Gamma — why the 3% figure does not
  transfer to SPY 0DTE 5-minute bars (Murphy's own text: daily/weekly closes, longer-term lines
  only, and he states the 3% figure itself doesn't even hold across all *daily* markets). Do
  NOT encode "3%" as a literal SPY intraday constant off this citation.
- Murphy's "internal trendline" and "channel line" sections (p.90, p.80) are confirmed to exist
  by table of contents but body text was not retrieved verbatim this session.
- LuxAlgo's exact ATR/Stdev/Linreg slope formula could not be fetched directly (`docs.mt.luxalgo.com`
  DNS failure this session) — confirmed only via search-result summaries of two independent
  pages; re-fetch `https://www.luxalgo.com/library/indicator/trendlines-with-breaks/` directly (not
  the docs mirror) or open the Pine source on TradingView to get exact parameter names before
  encoding.
- No sourced material found for Peter Brandt or Wyckoff's specific trendline-touch rules — flagged
  as a gap in this research, not encoded above.

---

## Murphy 3%/2-day rule — provenance check (2026-09-09)

> Triggered by `KEY-LEVELS-CHART-READING-HANDOFF.md` §9.5 row F item 4: *"Verify Murphy's 3%/2-day
> rule from primary text before any constant is named after it."* Prior crew (Part 2 above, 07-14
> session) reached only the archive.org table of contents and graded the claim UNVERIFIED. This
> pass downloaded the full OCR text file directly (`archive.org/download/.../..._djvu.txt`, 769KB,
> 25,404 lines) instead of relying on a single WebFetch summarization pass, and grepped it locally
> for `percent|penetrat|violat` — the passage was in the file the whole time, just past what the
> prior single-fetch summarization surfaced.

### Verdict: VERIFIED-PRIMARY (numbers + existence), with a SUPPORTED-SECONDARY-ONLY correction on the "combined AND-rule" framing, and a hard non-transfer finding for SPY 0DTE.

### What the primary text actually says

Source: John J. Murphy, *Technical Analysis of the Financial Markets* (New York Institute of
Finance, copyright 1999, ISBN 0-7352-0066-1), Chapter 4 "Basic Concepts of Trend," section
**"What Constitutes a Valid Breaking of a Trendline?"**, pp. 71-72 of the printed book (page
headers appear verbatim in the OCR at the quoted boundaries below). Full text:
[archive.org — Technical Analysis of the Financial Markets](https://archive.org/details/JohnJ.MurphyTechnicalAnalysisOfTheFinancialMarkets),
direct OCR text: `.../John_J._Murphy_-_Technical_Analysis_Of_The_Financial_Markets_djvu.txt`.

Verbatim (p.71-72):

> "As a general rule, a close beyond the trendline is more significant than just an intraday
> penetration. To go a step further, sometimes even a closing penetration is not enough. Most
> technicians employ a variety of time and price filters in an attempt to isolate valid trendline
> penetrations and eliminate bad signals or whipsaws. One example of a price filter is the 3%
> penetration criteria. This price filter is used mainly for the breaking of longer term
> trendlines, but requires that the trendline be broken, on a closing basis, by at least 3%.
> (The 3% rule doesn't apply to some financial futures, such as the interest rate markets.)
>
> If, for example, gold prices broke a major up trendline at $400, prices would have to close
> below that line by 3% of the price level where the line was broken (in this case, prices would
> have to close $12 below the trendline, or at $388). Obviously, a $12 penetration criteria would
> not be appropriate for shorter term trading. Perhaps a 1% criterion would serve better in such
> cases. The percentage rule represents just one type of price filter. ...
>
> An alternative to a price filter (requiring that a trendline be broken by some predetermined
> price increment or percentage amount) is a time filter. A common time filter is the two day
> rule. In other words, to have a valid breaking of a trendline, prices must close beyond the
> trendline for two successive days. To break an up trendline, therefore, prices must close under
> the trendline two days in a row. A one day violation would not count. The 1-3% rule and the two
> day rule are also applied to the breaking of important support and resistance levels, not just
> to major trendlines. Another filter would require a Friday close beyond a major breakout point
> to ensure a weekly signal."

A second, independent occurrence of the same two filters appears in Chapter 5 (Head and Shoulders
variations, p.122), confirming the wording is not a one-off:

> "Most chartists require a close beyond a previous resistance peak instead of just an intraday
> penetration. Second, a price filter of some type might be used. One such example is a
> percentage penetration criterion (such as 1% or 3%). Third, the two day penetration rule could
> be used as an example of a time filter. In other words, prices would have to close beyond the
> top of the first peak for two consecutive days to signal a valid penetration."

### Four findings from the primary text

1. **Both numbers are real and correctly cited by secondary sources.** 3% (with 1% offered as the
   variant "for shorter term trading") and two consecutive days are both Murphy's own words, with
   a page-locatable example (gold at $400, 3% penetration, $12, close at $388).
2. **They are presented as ALTERNATIVES, not a joint "AND" rule.** Murphy's own sentence: "An
   alternative to a price filter... is a time filter." He lists price-filter, time-filter, and
   "Friday close" as three separate optional filter types a chartist might pick ONE of — not a
   compound "3% AND 2-day" gate. The secondary web literature (see below) collapses this into a
   single joint rule ("these filters work together"). That collapsing is a genuine, if minor,
   attribution drift: the individual numbers are correctly sourced; the "combined rule" framing
   commonly repeated online is not what the primary text states. This document's own Part 2 section
   1 Murphy bullet (above) previously repeated the same "requires both" framing before this check —
   corrected in place, pointing here.
3. **Explicitly scoped to longer-term daily-bar lines, and even there is not universal.** Murphy
   says the 3% filter "is used mainly for the breaking of longer term trendlines" and states
   outright that "the 3% rule doesn't apply to some financial futures, such as the interest rate
   markets" — Murphy himself flags non-universality across markets. Every worked example in both
   quoted passages ("two successive days," "two days in a row," "a Friday close... to ensure a
   weekly signal") is stated in terms of daily closes; nothing in ch. 4 or ch. 5 discusses
   intraday/5-minute bars for these specific figures (the only ch.-4 intraday mentions are about
   NOT using a mere intraday touch/wick as the break signal at all, i.e. requiring a close — a
   different point from the 3%/2-day figures themselves).
4. **Book covers stocks and futures on daily/weekly charts; SPY 0DTE options on 5-minute bars are
   outside the described scope entirely** — a different instrument class (listed equity index
   options, not the underlying), a different expiry regime (0DTE — the "two successive days" time
   filter is close to meaningless when the entire trade lifecycle is a single session), and a
   two-orders-of-magnitude-finer bar resolution (5-minute vs. daily).

### The arithmetic that actually matters for Gamma

Murphy's worked example: gold at $400, 3% penetration required is $12 — and he calls that "not
appropriate for shorter term trading" even for a timeframe still coarser than intraday. Applying
the same 3% figure to SPY:

- SPY at approximately $765 (the level referenced in this work order) times 3% equals
  **$22.95, approximately $23**.
- A $23 penetration filter applied to a 5-minute chart is not a noise filter — it is larger than
  most entire SPY trading days (calm-to-normal RTH ranges commonly run a small single-digit to
  low-teens dollar span; only outsized catalyst days such as CPI/FOMC/NFP push materially past
  it). A "3% Murphy filter" applied literally to SPY 5-min bars would almost never fire, or would
  only fire on the most extreme trend days — functionally useless as an intraday break-confirmation
  gate.
- The two-day time filter is equally non-transferable on its face: 0DTE means the position exists
  for at most one session; "close beyond the line for two successive days" has no meaning inside a
  single day's 5-minute bars.
- **Conclusion: the rule is real, but it is a daily/weekly-bar, longer-term-trendline heuristic
  that does not scale down to SPY 0DTE intraday structure by direct substitution.** Any intraday
  analogue Gamma builds must be derived independently from ATR-scaled buffer plus N-bar
  persistence (already flagged as the correct approach in Part 2 section 8 above, and consistent
  with how the algorithmic/LuxAlgo literature already operationalizes "Murphy's spirit" for
  intraday use) — not by dividing Murphy's 3%/$12/2-day daily-bar numbers down to intraday scale,
  which has no textual basis in Murphy at all (he gives no formula for how the filter should
  change by timeframe beyond "a 1% criterion would serve better" for "shorter term trading," still
  describing a shorter-term daily trendline, not a 5-minute intraday one).

### Secondary-literature comparison (attribution-drift check)

- finaccfundas.blogspot.com and ajjacobson.us both reproduce Murphy's numbers (3%, two-day)
  essentially correctly — ajjacobson.us's page is close to a direct paraphrase/transcription of
  the same ch. 4 passage quoted above — consistent with primary text, not drift.
- A general web-search synthesis pass (this session) characterized the two filters as working
  "together" / being applied jointly — this is the specific compression identified in finding 2
  above. It is a mild drift (numbers unchanged, relationship between them overstated), not a
  fabrication.
- No source found (primary or secondary) that claims Murphy wrote this rule for intraday bars,
  options, or 0DTE instruments specifically — the "SPY 0DTE" framing is entirely Gamma's own
  proposed application, not anything attributed to Murphy by anyone.

### Full citation list

1. John J. Murphy, *Technical Analysis of the Financial Markets*, New York Institute of Finance,
   copyright 1999, ISBN 0-7352-0066-1, Ch. 4 "Basic Concepts of Trend," pp. 71-72 (section "What
   Constitutes a Valid Breaking of a Trendline?") and Ch. 5, p. 122 ("Filters," Head and Shoulders
   variations). Full OCR text fetched and grepped directly this session:
   [archive.org/details/JohnJ.MurphyTechnicalAnalysisOfTheFinancialMarkets](https://archive.org/details/JohnJ.MurphyTechnicalAnalysisOfTheFinancialMarkets).
2. [finaccfundas.blogspot.com — John Murphy's Patterns in a nutshell](https://finaccfundas.blogspot.com/2014/09/john-murphy-rules-of-technical-trading.html)
   — secondary, numbers match primary.
3. [ajjacobson.us — What Constitutes a Valid Breaking of a Trendline](https://www.ajjacobson.us/technical-analysis/what-constitutes-a-valid-breaking-of-a-trendline.html)
   — secondary, near-verbatim reproduction of the same ch. 4 passage; numbers match primary.
4. [stockdisciplines.com — Stock Trendline Penetrations](https://stockdisciplines.com/stock-trends-penetrations/)
   — secondary, describes the two-day rule as "the most commonly applied method" for stocks
   specifically (still daily-bar framing).

### Grade and recommendation

**Grade: VERIFIED-PRIMARY** for the 3% figure, the 1% variant, and the two-day figure (all
confirmed verbatim against the primary text, ch. 4 pp.71-72 and ch. 5 p.122) — **downgraded on
the combined-rule framing to SUPPORTED-SECONDARY-ONLY** (the "3% AND 2-day, applied together"
version repeated in most web summaries, including this project's own prior Part 2 draft, is a
mild compression of Murphy's actual "pick one filter type" framing) — and **the SPY-0DTE-intraday
application is UNSUPPORTED BY THE PRIMARY TEXT AT ANY GRADE** (Murphy never discusses intraday
bar filters for this rule; the numbers are explicitly daily/weekly and explicitly flagged by
Murphy himself as needing to shrink for "shorter term trading," with no floor stated).

**Recommendation: a constant may cite Murphy for the existence and shape of "percentage-filter OR
time-filter, confirmed-close, not first-touch" break confirmation — but it must NOT carry
Murphy's literal 3% or two-day figures, and should not be named e.g. `MURPHY_3PCT` or
`MURPHY_2DAY`. Name it for what it actually is (an ATR-scaled buffer + N-bar persistence filter,
per Part 2 section 8), and if a citation is wanted in a comment, cite it as "Murphy-style filter
concept, re-derived for 5-min/0DTE scale — see TRENDLINE-BREAK-LITERATURE-2026-07-14.md" rather
than naming the constant itself after Murphy.**
