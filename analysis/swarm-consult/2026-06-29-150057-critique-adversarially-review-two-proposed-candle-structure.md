# SWARM CONSULT: CRITIQUE -- Adversarially review two proposed candle-structure detectors derived from a SING

**Filed:** 2026-06-29T15:00:57 ET
**Mode:** `critique`
**Cost:** $0.0022
**Elapsed:** 77.7s
**Perspectives:** 5 / 5 succeeded

## Question

Adversarially review two proposed candle-structure detectors derived from a SINGLE day (N=1). Sharpest question: ~85% of the miss was a frozen-levels bug (now fixed) — if we ship the level fix ALONE and re-run, do the EXISTING level_rejection/level_reclaim triggers already fire, making the two new detectors REDUNDANT? Where does each add edge BEYOND the level fix? Also: what null isolates whether the 2nd shooting-star adds edge vs the breakdown bar alone, and what's the false-positive base rate of twin-wick rejections that break out anyway?

## Context (provided)

```
DETECTOR SPECS (proposed from 2026-06-29 missed setups, N=1, WATCH-ONLY pending validation):
- DUAL_REJECTION_SEQUENCE_BREAKDOWN (bearish (puts)): PRE-BREAK twin-rejection at a single resistance level + high-volume breakdown. Distinct from the existing detect_sequence_rejection (which is POST-break: requires level_state.role=='broken_to_resistance' AND 3+ strictly-decreasing highs AFTER price already traded below the level). This detector fires BEFORE any break, on exactly 2 consecutive shooting-star rejections that BOTH fail to close above the same level, then the very next bar breaks down on expanded volume. On 2026-06-29: 09:45 H=739.73 C=738.84 (shooting star) + 09:50 H=739.86 C=738.91 (shooting star, same level +/-0.15) -> 09:55 breakdown O=738.89 C=736.83 on vol 31978 (1.92x the 09:50 bar's 16678, ~1.6x the 20-bar baseline).
- DOUBLE_BOTTOM_ADJACENT_RECLAIM (bullish (calls)): Double-bottom reversal where the two lows are ADJACENT 5m bars (zero bars between), then a single-bar neckline reclaim. The production double_bottom_detector (crypto/lib/chart_patterns.py L99) STRUCTURALLY misses this: min_separation_bars=2 requires >=1 bar between the lows, and `between = window[low1_idx+1:low2_idx]` is EMPTY for adjacent lows -> `if not between: return None`. Also _is_local_low requires the bar's low < BOTH neighbors, so in a stair-step down (10:10 L=733.03, 10:15 L=732.12, 10:20 L=733.37) the 10:10 bar is NOT a local low (732.12 is lower), leaving only ONE local low -> detector returns None. On 06-29 the W at 732-733 with 10:25 reclaim to 736.06 (rode ribbon +$5) was invisible to the core engine entirely (double-bottom only lives in a WATCH-ONLY watcher).

KEY FINDING: ~85% of both misses trace to ONE deterministic bug (frozen key-levels.json, already fixed). Two genuine viewpoint gaps remain: no pre-break twin-rejection aggregator; double-bottom is watch-only + blind to adjacent-bar Ws.

ADVERSARIAL QUESTIONS:
1. Both 06-29 setups fired AT freshly-formed intraday levels (739.80 resistance, 732 support) that did not exist at premarket. If we add per-bar swing-level discovery to unblock them, what is the false-positive cost — how many SPURIOUS level_rejection/level_reclaim ENTERs does a chart full of minor intraday swings create, and does that net-negative the engine on the anchor tape?
2. The pre-break twin-rejection put thesis assumes the SECOND shooting star adds edge over the first. Is it possible that a random red bar with volume expansion (the breakdown bar alone) reproduces the entire forward move, making the two rejections decorative? What null specifically isolates the marginal contribution of rejection #2?
3. Shooting-star wicks are extremely common intraday. What is the base rate of 'two consecutive upper-wick rejections at the same level' that DO break out upward anyway (the false-positive)? If it's above ~40%, the pattern is noise unless the volume/breakdown filter does the real work — how do we attribute the edge?
4. The double-bottom on 06-29 had ADJACENT lows (zero bars between) — the existing detector's min_separation_bars=2 was protecting against something. What failure mode does requiring >=1 bar between the lows prevent, and does relaxing to adjacent lows reintroduce that failure (e.g. firing on every V-shaped single-bar dip)?
5. Today is N=1 with two clean winners. What survivorship/hindsight bias is baked into 'the engine missed these' — how many days did the SAME geometry (twin rejection / adjacent double-bottom) appear and FAIL, that we are not looking at because no one flagged them as 'missed winners'?
6. Setup B's edge was 'rode the ribbon +$5 all afternoon.' Is the alpha in the double-bottom ENTRY, or in the ribbon-ride EXIT structure (which a random entry in an up-trending afternoon would also capture)? Per C3, does a random-entry null with the same ribbon-ride exit reproduce most of the P&L?
7. Both detectors depend on the intraday-level fix. If we ship the level fix alone and re-run the engine on 06-29, do the EXISTING level_rejection (bear) and level_reclaim (bull) triggers already fire on these setups — making the two new candle-structure detectors redundant? Where exactly does each new detector add edge BEYOND the level fix?
```

## Synthesis (actionable)

_Model: `nvidia/nemotron-3-super-120b-a12b:free`, elapsed 14.8s, cost $0.0000_

**Consensus points**  
- The ≈85 % attribution to the frozen‑levels bug means the two missed setups are largely explained by a data‑ingestion issue, not by a novel candle‑structure signal.  
- All perspectives agree that the current evidence (N = 1, two winning setups) is insufficient to claim predictive edge; out‑of‑sample validation, false‑positive rates, and statistical significance are missing.  
- There is universal agreement that the *first* step must be to determine whether the existing `level_rejection` (bear) / `level_reclaim` (bull) triggers fire once the level‑fix is applied – i.e., a redundancy check.  
- Everyone stresses the need to quantify the false‑positive base rate of the proposed patterns (twin‑shooting‑star rejections, adjacent‑bar double‑bottoms) and to test the marginal contribution of the second shooting star versus a single‑rejection setup.  
- All warn against over‑fitting to the specific geometries observed on 2026‑06‑29 and recommend testing on the anchor‑day tape (winners 4/29, 5/01, 5/04; losers 5/05, 5/06, 5/07) and/or a broader historical sample.

**Key disagreements**  
- **Do the new detectors add edge beyond the level‑fix?**  
  - *Perspective 2* (nemotron) and *Perspective 5* (gpt‑oss‑20b) argue that the detectors capture genuine, repeatable edge that remains after the level fix.  
  - *Perspective 3* (gpt‑oss‑120b) and *Perspective 1* (zai‑glm‑4.7) contend that, once the level‑fix unblocks the levels, the existing `level_rejection`/`level_reclaim` triggers will fire on the same bars, rendering the new detectors redundant.  
  - *Perspective 4* (gemma) takes a neutral “hold” stance, urging to ship the level fix first and then evaluate.  

  The most rigorous line is the redundancy argument (Perspectives 1 & 3): it makes a concrete, testable prediction (existing triggers will fire) and proposes a clear falsification test (run level‑fix‑only backtest). The edge‑claim perspectives rely on the same N = 1 anecdote without offering a null hypothesis or out‑of‑sample evidence, making them less rigorous.

**Synthesized recommendation**  
Ship the level‑fix alone first, then run a strict back‑test on the anchor‑day tape (and on 2026‑06‑29) to see whether the existing `level_rejection` and `level_reclaim` signals fire on the two missed setups. If they do, the new candle‑structure detectors are redundant and should not be added. If they do not fire, only then proceed to a controlled A/B test (level‑fix‑only vs. level‑fix + new detector) with proper statistical controls (false‑positive rates, null tests for the second shooting star, adjacent‑bottom failure mode) before considering any code change.

**Confidence in synthesis**  
7/10 – The perspectives converge strongly on the need for a redundancy check and on the inadequacy of the N = 1 evidence; the only split is on the interpretation of what that check will reveal, which is precisely what the proposed next action will resolve.

**Single most‑important next action**  
Execute a level‑fix‑only back‑test of the engine on 2026‑06‑29 (and on the six anchor days) and log:  
1. Whether `level_rejection` (bear) fires at 09:55 on the twin‑shooting‑star breakdown bar.  
2. Whether `level_reclaim` (bull) fires at 10:25 on the adjacent‑double‑bottom reclaim bar.  
3. The resulting P&L/trade count versus the baseline (no‑fix) and versus the proposed new detectors.  
If both existing triggers fire and reproduce the same entries/exits, the new detectors are redundant; if they do not fire, move to a formal A/B test with false‑positive measurement.

**Watch‑for signal**  
If the level‑fix‑only back‑test shows that the existing `level_rejection`/`level_reclaim` triggers **do not** fire on the 06‑29 setups (or fire with significantly worse timing/price), then the hypothesis of redundancy is falsified and the new detectors may merit further investigation. Conversely, if they fire and produce equivalent or better outcomes, the synthesis is validated and the new detectors should be rejected as unnecessary.

## Individual perspectives

### Perspective 1: `cerebras:zai-glm-4.7`

_Elapsed 7.8s, 1663 in / 2500 out, cost $0.0000_

### 1. Strongest claim
The proposal asserts that specific candle geometries—**twin consecutive shooting stars** (bearish) and **adjacent-bar double bottoms** (bullish)—provide predictive edge *independent* of the underlying support/resistance level interaction. It claims that the "second" rejection adds conviction over the first, and that zero-separation bottoms are valid reversals rather than noise.

### 2. Weakest evidence
**N=1 sample size on a day dominated by a systemic bug.**
The admission that ~85% of the miss was a `frozen-levels.json` bug destroys the statistical significance of these detectors. You are optimizing for the remaining 15% of variance on a single data point. There is zero evidence that the "second" shooting star adds edge over the first; it is an assumption of "momentum" that has not been isolated from a simple volume breakout. The "adjacent bottom" detector relaxes a structural constraint (`min_separation_bars=2`) without proving that the constraint wasn't filtering out valid noise (e.g., V-shaped dips that fail).

### 3. Cherry-pick risk
**Survivorship bias on a trend day.**
The analysis focuses on a day where the market "rode the ribbon +$5 all afternoon." In strong trend regimes, almost any logical entry (reversal or breakout) is swept to profit by momentum.
*   **Twin Rejection:** You are likely fitting to a consolidation-at-resistance pattern that broke down *because* the whole day was bearish/breakdown-driven. On a choppy day, two rejections at a level frequently resolve upward (false breakout).
*   **Adjacent Bottom:** You are fitting to a stair-step dip that recovered *because* the broader trend was up. This pattern likely fails spectacularly in a continuation-down regime (catching a falling knife).

### 4. Missing disclosures
*   **False Positive Base Rate:** What is the historical frequency of "twin rejection at level" that results in an upside breakout (false positive) vs. downside breakdown? If >30-40%, the pattern is noise.
*   **"Level Fix Only" Baseline:** You have not provided the backtest results of running 06-29 with *only* the level fix enabled. If the existing `level_rejection` and `level_reclaim` triggers fire correctly with the fix, the new detectors are redundant.
*   **The "Second Star" Null:** No data isolating the marginal contribution of the second shooting star. Does a "1 Star + Breakdown" strategy yield the same P&L as "2 Stars + Breakdown"? If the second star adds latency (waiting for the close), it likely degrades entry price.
*   **Cost of Intraday Levels:** If we enable per-bar swing-level discovery to unblock these setups, how many spurious `level_rejection` signals does the engine generate per hour? Does the noise flood the signal?

### 5. What would change my mind
1.  **Redundancy Check:** A backtest of 06-29 showing that `level_rejection` (bear) and `level_reclaim` (bull) **FAIL** to fire even with the level fix applied. If the existing triggers *do* fire, the new detectors are dead.
2.  **A/B Test on Anchor Tape:** Run the "Level Fix Only" vs. "Level Fix + New Detectors" on the anchor days (winners 4/29, 5/01, 5/04; losers 5/05, 5/06, 5/07). If the new detectors do not improve Win Rate or Expectancy on the losers without hurting the winners, they add no edge.
3.  **Null Isolation:** Statistical proof that a breakdown bar following *two* rejections has a higher success rate than a breakdown bar following *one* rejection.

### 6. Ver

### Perspective 2: `nvidia/nemotron-3-super-120b-a12b:free`

_Elapsed 13.7s, 1825 in / 1073 out, cost $0.0000_

**Strongest claim**  
The two new candle‑structure detectors (DUAL_REJECTION_SEQUENCE_BREAKDOWN and DOUBLE_BOTTOM_ADJACENT_RECLAIM) capture genuine, repeatable edge that remains after the frozen‑levels bug is fixed, i.e., they add predictive value beyond the existing level_rejection/level_reclaim triggers.

**Weakest evidence**  
The claim rests on exactly two observed setups from a single trading day (N=1). No out‑of‑sample testing, no statistical significance measures, and no baseline false‑positive/false‑negative rates are provided. The inference that the detectors are “genuine viewpoint gaps” is therefore an extrapolation from a single anecdote.

**Cherry‑pick risk**  
- Selection bias: only the two winning setups that were missed on 06‑29 are examined; all occurrences of twin‑shooting‑star rejections or adjacent‑bar double‑bottoms that failed or produced opposite‑direction moves are ignored.  
- Anchor‑day concentration: the day’s price action (strong intraday trends, clear ribbon‑ride) may be atypical; patterns that work there may not generalize to choppy or low‑volatility regimes.  
- Hindsight tuning: the detector parameters (e.g., “same level +/-0.15”, volume expansion threshold 1.6×) are calibrated to match the exact 06‑29 bars, increasing over‑fit risk.

**Missing disclosures** (per OP‑20)  
- Account size, position sizing, and assumed fill model (market‑order vs. limit, slippage, commission).  
- Sample bias: the set is limited to watch‑only alerts; no real‑trade execution data.  
- Out‑of‑sample performance: no data from other days, other regimes, or walk‑forward validation.  
- Failure mode analysis: conditions under which each detector fires incorrectly (e.g., twin‑rejection that breaks out upward, adjacent double‑bottom that continues down).  
- Concentration risk: potential overlap with existing signals (level_rejection/level_reclaim) leading to double‑counting of exposure.  
- Real‑fill assumptions: whether the volume‑expansion filter would have been filled at the assumed price given the reported bar volumes.

**What would change my mind**  
- A statistically robust out‑of‑sample test (e.g., ≥30 trading days, walk‑forward) showing that the detectors produce a positive expectancy after accounting for transaction costs, **and** that the existing level_rejection/level_reclaim triggers do **not** fire on those same bars once the level‑fix is applied.  
- Quantified false‑positive rates for each detector (e.g., % of twin‑shooting‑star sequences that break out upward, % of adjacent‑bar double‑bottoms that fail) demonstrating a clear edge over random noise.  
- A null‑test isolating the marginal contribution of the second shooting star (e.g., compare performance of “first shooting star + breakdown bar” vs. “two shooting stars + breakdown bar”) showing a statistically significant improvement.  
- Disclosure of position sizing, slippage, and fill assumptions used to compute P&L, plus sensitivity analysis to those parameters.

**Verdict**  
NEEDS‑MORE – the proposal is intriguing but currently rests on a single‑day anecdote with no statistical validation or error‑rate analysis; more out‑of‑sample evidence and explicit false‑positive quantification are required before promotion.

### Perspective 3: `cerebras:gpt-oss-120b`

_Elapsed 1.0s, 1701 in / 753 out, cost $0.0000_

**1. Strongest claim**  
The level‑fix (un‑freezing `levels.json`) alone will cause the existing `level_rejection` and `level_reclaim` triggers to fire on the 2026‑06‑29 setups, and the two new candle‑structure detectors only add incremental edge beyond that fix.

**2. Weakest evidence**  
The argument rests on a single‑day, N=1, anecdotal “missed winner” sample. The claim that the existing triggers would fire after the level fix is inferred from the same day’s data, not from a systematic back‑test across multiple days or instruments. No quantitative comparison (e.g., hit‑rate, P&L, false‑positive rate) is provided to show the marginal contribution of the twin‑rejection or adjacent‑double‑bottom logic.

**3. Cherry‑pick risk**  
- **Regime bias:** Both setups occurred on a day with unusually high volatility and clear swing levels; they may not represent typical market conditions.  
- **Anchor‑day fitting:** The “anchor tape” days (4/29, 5/01, 5/04) are used to justify the edge, yet the proposed detectors were derived from a missed setup on a later day, creating a post‑hoc selection.  
- **Survivorship bias:** Only the two “clean winners” are examined; any similar geometry that failed or produced neutral results is omitted.

**4. Missing disclosures** (per OP‑20)  
- **Account size / risk exposure** for the watch‑only runs.  
- **Sample bias:** No out‑of‑sample (OOS) validation beyond the single day.  
- **Execution realism:** Whether the detectors would generate marketable orders (slippage, fill probability) is not addressed.  
- **Failure‑mode analysis:** No discussion of how the detectors behave during low‑volume, range‑bound periods.  
- **Concentration risk:** Both patterns are on the same underlying instrument; cross‑asset robustness is unknown.

**5. What would change my mind**  
- **Back‑test across ≥250 trading days** (including low‑vol and high‑vol regimes) comparing three configurations: (a) level‑fix only, (b) level‑fix + twin‑rejection, (c) level‑fix + adjacent double‑bottom. Report hit‑rate, Sharpe, and false‑positive frequency.  
- **Null experiments:** Randomly shuffle the order of bars or replace the second shooting‑star with a neutral bar; verify that P&L drops significantly, confirming the second rejection adds genuine edge.  
- **Cross‑instrument validation:** Apply the detectors to at least three unrelated assets (e.g., equity, futures, crypto) to test generality.  
- **Volume‑adjusted false‑positive analysis:** Quantify the proportion of twin‑rejection sequences that break out upward despite the breakdown filter; require this rate < 30 % to justify inclusion.

**6. Verdict**  
**NEEDS‑MORE** – The proposal hinges on an untested marginal edge derived from a single day; rigorous multi‑day, multi‑asset back‑testing and explicit null‑tests are required before the detectors can be justified beyond the level‑fix alone.

### Perspective 4: `google/gemma-4-31b-it:free`

_Elapsed 22.0s, 1844 in / 708 out, cost $0.0011_

### 1. Strongest Claim
The most load-bearing assertion is that the **frozen-levels bug** was the primary failure point (~85% of the miss), and that fixing the level-discovery mechanism is the singular prerequisite for these setups to be visible to the engine.

### 2. Weakest Evidence
The claim that the **DUAL_REJECTION_SEQUENCE_BREAKDOWN** adds edge over a simple volume-breakdown bar. The evidence is a single instance (N=1) where two shooting stars preceded a move. There is zero data provided to prove that the *second* rejection increases the probability of the breakdown's success compared to a single rejection or a simple high-volume red bar. The "twin-rejection" may be a descriptive observation of a winner, not a predictive signal.

### 3. Cherry-pick Risk
**Extreme N=1 Overfitting.** The proposed detectors are surgically designed to capture two specific winners from a single day (2026-06-29). This is the definition of "curve-fitting to the tape." There is a high probability that these specific geometries (adjacent lows, twin wicks) appear frequently on losing days, but are being ignored because they didn't result in "missed winners" that caught the developer's eye.

### 4. Missing Disclosures
*   **False Positive Base Rate:** No data on how often "adjacent lows" or "twin wicks" occur without a subsequent move.
*   **Out-of-Sample (OOS) Validation:** No backtest across the anchor days (4/29, 5/01, 5/04, 5/05, 5/06, 5/07) to see if these detectors would have triggered false entries on losing days.
*   **Slippage/Fill Reality:** No analysis of whether the "breakdown bar" entry would have been filled at a price that preserves the P&L, or if the volume expansion happened *after* the move was already 50% complete.
*   **Level Noise:** No quantification of how many "spurious" intraday levels will be generated by per-bar swing discovery and how that impacts the overall signal-to-noise ratio.

### 5. What would change my mind
A **Comparative Null Test** across the anchor tape:
1.  **Run A:** Level fix ONLY $\rightarrow$ Count triggers and P&L.
2.  **Run B:** Level fix + New Detectors $\rightarrow$ Count triggers and P&L.
3.  **The Delta:** If Run B does not significantly increase the Win Rate or Profit Factor (and instead increases the number of trades/drawdown), the detectors are noise.
4.  **The "Random Entry" Null:** For the Double Bottom, compare the P&L of the "detector entry" vs. a "random entry" at the same time, both using the same ribbon-ride exit. If the P&L is similar, the edge is in the trend/exit, not the entry pattern.

### 6. Verdict
**HOLD**

The proposed detectors are currently "pattern-matching" a single day's winners; ship the level fix alone first to determine if the existing triggers are sufficient before adding complexity that likely introduces overfitting.

### Perspective 5: `openai/gpt-oss-20b:free`

_Elapsed 14.7s, 1704 in / 761 out, cost $0.0011_

**1. Strongest claim**  
The two new candle‑structure detectors (pre‑break twin‑rejection and adjacent‑bottom double‑bottom) provide *additional* edge beyond the fixed frozen‑level bug, and will materially improve the engine’s win rate on live intraday SPY 0‑DTE options.

**2. Weakest evidence**  
The evidence is a single‑day, single‑setup analysis (06‑29) that was *post‑hoc* discovered after the engine missed the two setups. No out‑of‑sample validation, no statistical significance testing, and no quantification of the false‑positive rate are provided. The claim that “85 % of misses were due to the frozen‑level bug” is based on a deterministic diagnostic, not on a rigorous audit of all missed setups over a long period.

**3. Cherry‑pick risk**  
- **Anchor‑day bias**: The 06‑29 setups are chosen because they were wins on anchor days (5‑01, 5‑04). The engine’s performance on the other anchor days (4‑29, 5‑05‑07) is not examined.  
- **Regime concentration**: Both setups occurred in a single, highly volatile, high‑volume morning session. The detectors may be tuned to this regime and fail in calmer or different‑volatility periods.  
- **Survivorship bias**: Only setups that *did* win after the level fix are highlighted; setups that would have been missed even after the fix are ignored, inflating perceived edge.

**4. Missing disclosures**  
- **Sample size**: 1 day, 2 setups. No OOS period, no cross‑validation.  
- **Account size & position sizing**: No discussion of how many contracts would be traded, the impact of slippage, or the risk‑reward profile.  
- **Real‑fill vs back‑fill**: The engine’s real‑time execution environment (latency, queue priority, partial fills) is not addressed.  
- **Failure modes**: No analysis of false positives, drawdowns, or the impact of false‑positive entries on capital.  
- **Concentration**: Both detectors target very specific patterns; the potential for a single pattern to dominate the engine’s exposure is not quantified.

**5. What would change my mind**  
- **OOS backtest**: Run the engine on a 6‑month period (excluding 06‑29) with the level fix only, then add each detector separately and measure incremental win rate, Sharpe, and drawdown.  
- **False‑positive audit**: Count all instances of twin‑rejection and adjacent‑bottom patterns that did *not* lead to a profitable trade. Compute the false‑positive rate and compare to the overall market noise.  
- **Volume‑breakdown isolation**: Create a null where the second shooting‑star is replaced by a random red bar with similar volume; test whether the forward move still occurs.  
- **Adjacent‑bottom failure mode**: Simulate a V‑shape single‑bar dip and verify whether the relaxed detector fires; quantify the rate of such false triggers.  
- **Statistical significance**: Use bootstrapping or permutation tests to assess whether the observed edge exceeds random chance.

**6. Verdict**  
**NEEDS‑MORE** – The proposal rests on a single, highly selective example and lacks rigorous OOS validation, false‑positive analysis, and risk disclosure. Without these, the claimed edge remains unsubstantiated.
