# TA Pattern Reference — Detection Geometry for the 0DTE SPY Engine

> Canonical, cited reference for implementing chart-pattern + market-structure detectors that read 5-minute and 15-minute SPY bars. Precision of detection geometry is the priority; prose is kept minimal.
>
> **Statistic discipline.** Every empirical number below is quoted from a named source (URL in the Sources list). Bulkowski's *"break-even failure rate"* = the percentage of patterns that **fail to move more than 5%** past the breakout (his definition). His *performance rank* is "1 = best" out of 39 patterns for up-breakouts / 36 for down-breakouts. Where no source publishes a number, the text says **"no published stat"** — nothing here is invented.
>
> **Intraday caveat that applies to the whole document.** Bulkowski's and StockCharts' statistics were measured on **daily/weekly** data. The *shape detectors* port to 5m/15m bars; the *failure-rate percentages do not* — they would have to be re-measured on our own intraday SPY sample before being trusted. Each pattern carries a specific "INTRADAY/0DTE APPLICABILITY" note.

---

## A. Market Structure

These are the primitives. Everything in sections B and C is ultimately defined in terms of swing points and the trend they imply, so implement A first.

### A.1 Swing High / Swing Low (fractal / pivot detection)

**Definition (Williams fractal, the standard N-bar rule).** A swing point is the center bar of a symmetric window of `2N+1` bars.

- **Swing high (up fractal):** a bar whose HIGH is strictly greater than the highs of the `N` bars immediately before it AND the `N` bars immediately after it. Williams' canonical form uses `N = 2` → a **5-bar pattern**: the middle bar has the highest high, with two lower highs on each side. (MetaTrader/TradingView/LuxAlgo.)
- **Swing low (down fractal):** mirror — a bar whose LOW is strictly less than the lows of the `N` bars on each side. Canonical `N = 2`: lowest low in the middle, two higher lows on each side.

**Precise rule to code (`N` = bars per side):**
```
is_swing_high(i, N) = all( high[i] > high[i-k] for k in 1..N ) and all( high[i] > high[i+k] for k in 1..N )
is_swing_low(i, N)  = all( low[i]  < low[i-k]  for k in 1..N ) and all( low[i]  < low[i+k]  for k in 1..N )
```
Use `>`/`<` (strict). For equal-high ties, pick a deterministic tie-break (e.g. require strictly greater, or treat the later bar as the pivot) and document it.

**Confirmation lag (critical for a live engine).** A fractal can only be confirmed **`N` bars after** the pivot bar, because you need the `N` right-hand bars to exist. With `N=2` the swing is confirmed 2 bars late. This is a *confirmation* tool, not a predictive one — never treat the current (still-forming) bar as a confirmed swing. (MetaTrader, LuxAlgo, QuantifiedStrategies.)

**Common N values for intraday.** Platforms default to the 5-bar (`N=2`) Williams fractal, but that default is not sacred. For intraday use, practitioners widen the lookback to suppress noise: TradingView-community guidance cites a **"Pivot Length" of ~7–14** (shorter for scalping, longer for positional), and one commonly cited setup is a **15-minute chart with pivot lookback ~10–15** for a balance of signal frequency vs. level significance. (LuxAlgo, QuantifiedStrategies, TradingView scripts.) **Implementation recommendation:** expose `N` (bars-per-side) as a config knob per timeframe — e.g. `N=2` on 15m for major pivots, larger on 5m to filter chop — and tune empirically rather than hard-coding 2.

**ICT/SMC note.** Smart-money material often uses the looser **3-bar swing** (`N=1`): a swing high is a candle whose high exceeds the candle on each immediate side; swing low the mirror. (Mind Math Money, DailyPriceAction.) This is the same rule with `N=1`. Be explicit about which `N` a given detector uses, because BOS/CHoCH below are defined relative to *these* swing points.

**INTRADAY/0DTE APPLICABILITY:** Fully applicable and foundational — this is the one section that is *more* useful intraday than the big multi-week patterns. Caveat: small `N` on 5m bars produces many noise pivots; widen `N` or require a minimum price displacement between pivots.

---

### A.2 HH / HL / LH / LL → Trend Definition

Label each confirmed swing relative to the prior swing of the same type:

- **HH (higher high):** swing high above the previous swing high.
- **HL (higher low):** swing low above the previous swing low.
- **LH (lower high):** swing high below the previous swing high.
- **LL (lower low):** swing low below the previous swing low.

**Trend from labels (Dow Theory):**

| Trend | Condition |
|---|---|
| **Uptrend** | sequence of **HH + HL** (each rally peak exceeds the prior peak, each pullback holds above the prior trough) |
| **Downtrend** | sequence of **LH + LL** (each rally fails below the prior peak, each trough undercuts the prior trough) |
| **Range / undefined** | mixed labels (e.g. HH but LL, or alternating) — no clean trend |

An uptrend requires **both** HH and HL; losing either condition signals weakening/possible reversal. Downtrend is the mirror. (Dow Theory — Zerodha Varsity, IncredibleCharts, QuantifiedStrategies.)

**To code:** maintain an ordered list of confirmed swings `[(idx, price, type)]`; compare each new swing high to the last swing high and each new swing low to the last swing low to emit HH/HL/LH/LL; derive trend state from the last two highs **and** last two lows jointly.

**INTRADAY/0DTE APPLICABILITY:** Highly applicable — this is the workhorse for intraday trend context (e.g. "are we in an HH/HL uptrend on the 5m?"). Caveat: intraday trend flips fast; recompute every bar and treat single-swing flips as tentative until a structure break (A.3/A.4) confirms.

---

### A.3 Break of Structure (BOS)

**Definition.** A **continuation** signal: price breaks **beyond the most recent confirmed swing in the direction of the existing trend**.

- **Bullish BOS (in an uptrend):** price **closes above** the most recent confirmed swing **high**. Confirms bulls still in control → trend continues up.
- **Bearish BOS (in a downtrend):** price **closes below** the most recent confirmed swing **low**. Confirms bears in control → trend continues down.

(Mind Math Money, FluxCharts, FXOpen, DailyPriceAction.)

**Close vs. wick (load-bearing for the detector).** A *wick* through the swing level does **not** confirm a BOS — require a candle **close (body)** beyond the level. A wick that pierces and rejects is treated as a **liquidity sweep**, not a structural break. Encode the break as `close[i] > swing_high_price` (bullish) / `close[i] < swing_low_price` (bearish), not `high`/`low`. (Mind Math Money, DailyPriceAction.)

**INTRADAY/0DTE APPLICABILITY:** Very applicable — BOS is one of the cleanest intraday continuation triggers and maps directly onto the engine's "reclaim/break of a named level" logic. Caveat: define the swing-`N` first; a BOS is only as meaningful as the swing it breaks. Use the close-confirmation rule to avoid being faked out by 0DTE-driven wicks.

---

### A.4 Change of Character (CHoCH / CHOCH)

**Definition (ICT / Smart-Money-Concepts terminology).** The **first counter-trend structure break** — the earliest sign that the prevailing trend may be reversing.

- **Bearish CHoCH (was an uptrend):** price **closes below the most recent higher-low (HL)**. The uptrend was making HH/HL; the first time price breaks the last HL, character has changed from bullish to bearish.
- **Bullish CHoCH (was a downtrend):** price **closes above the most recent lower-high (LH)**. The downtrend was making LH/LL; the first break above the last LH flips character to bullish.

(Mind Math Money, FluxCharts, DailyPriceAction, TradeThePool.)

**BOS vs. CHoCH — the single distinguishing axis.** Same mechanic (a swing-level break confirmed by a close); the **direction of the break relative to the existing trend** is the only difference:
- break **with** the trend (beyond the swing extreme in the trend direction) = **BOS** (continuation);
- break **against** the trend (through the most recent counter-trend swing — the last HL in an uptrend / last LH in a downtrend) = **CHoCH** (reversal).

A common state machine: trend continues via BOS after BOS; the first opposing break is the CHoCH, which flips the working trend; subsequent breaks in the new direction are again BOS. The same wick-vs-close rule applies — require a body close beyond the level. (Smart Money ICT, InnerCircleTrader explainers.)

**Caveat on provenance.** BOS/CHoCH are ICT/SMC vocabulary, not Dow-Theory or Bulkowski terms. They are widely used but are pedagogical/discretionary constructs; the cited sources are reputable explainers rather than peer-reviewed statistics. **No published failure-rate stat exists** for BOS or CHoCH.

**INTRADAY/0DTE APPLICABILITY:** Applicable and popular intraday — CHoCH is effectively an early reversal trigger and pairs naturally with the engine's reversal setups. Caveat: it is the *first* break, so it is noisier than a confirmed multi-swing reversal; treat a lone CHoCH as "reversal candidate," confirm with follow-through (a BOS in the new direction) before high-conviction sizing.

---

## B. Reversal Patterns

> **Headline for all of section B:** every pattern here is described by the source literature as a **multi-week to multi-month** structure. The geometry/triggers are codeable from OHLC, but the Bulkowski failure rates were measured on daily/weekly charts and **do not transfer to 5m/15m**. See each pattern's applicability note.

### B.1 Double Top (bearish mirror of double bottom)

**Geometry (OHLC-detectable):**
- Two distinct peaks at **similar price** — peak-to-peak variation **usually < 3%** (Bulkowski's tolerance; use as the similarity threshold).
- For the cleanest "Adam & Adam" variant, both peaks are **narrow, inverted-V spikes** (1–few bars). The intervening **valley should drop ≥ ~10%** below the peaks (allow exceptions).
- Peaks "usually several weeks apart."

**Neckline / confirmation trigger:**
- Neckline = the **lowest low of the valley between the two peaks** (horizontal support across the trough).
- **Confirmation = a CLOSE below that valley low.** A wick below the neckline does *not* confirm. Until the confirming close, twin peaks are not a valid double top (most twin-peak shapes never confirm). Code: `close[i] < min(valley_lows)`.

**Volume signature:** typically higher on the **left** peak than the right; volume trends down across the pattern; breakdown often on rising volume.

**Bulkowski stat (Adam & Adam, bull market, 1,114 perfect trades):** **break-even failure rate 25%**; average decline 15%; performance rank 19/36; pullback rate 64%. (The lower-failure **Eve & Eve** variant ≈ **20%** break-even failure.) Source: thepatternsite.com/aadt.html.

**INTRADAY/0DTE APPLICABILITY:** Marginal. A "double top" can appear intraday (two tests of a 5m resistance with a close back below the intervening low), and that *is* a usable short trigger — but it is really an A.4 CHoCH/level-rejection in disguise; do not attach Bulkowski's 25% figure to it. The textbook double top with weeks between peaks does not complete intraday.

---

### B.2 Inverse Head & Shoulders (Head-and-Shoulders Bottom)

**Geometry (OHLC-detectable):**
- **Three consecutive troughs; the middle (head) is the lowest.** Both shoulder lows are higher than the head and should bottom **near the same price**, be **roughly equidistant** from the head, and look similar (both wide or both narrow) — i.e. not lopsided.
- Must be preceded by a prior **downtrend** (it is a reversal).

**Neckline / confirmation trigger:**
- Neckline = line connecting the **two reaction highs** (the "armpits": high after the left shoulder, high after the head). May slope up, down, or be flat.
- **Confirmation = price closes above the neckline** (for an up-sloping neckline, above the right armpit). StockCharts requires the breakout to come with a **volume expansion** — for a *bottom*, volume confirmation is mandatory ("without the proper expansion of volume, the validity of any breakout becomes suspect"). Throwback to the neckline-as-support occurs ~65% of the time.

**Volume signature:** highest on left shoulder or head, lighter on right shoulder; **volume expansion on the breakout is required** (stronger requirement than the topping variant).

**Bulkowski stat (bull market, 3,197 perfect trades):** **break-even failure rate 11%**; average rise 45%; performance rank 13/39; throwback 65%; meets price target 71%. Source: thepatternsite.com/hsb.html. (Note: an "3–4%" figure seen in search snippets is *not* on the page — the page says **11%**.)

**INTRADAY/0DTE APPLICABILITY:** Marginal-to-occasional. A three-trough base with a neckline reclaim can form within a session and is a legitimate reversal read, but the published 11% is daily/weekly. If implemented intraday, require the same close-above-neckline **with volume expansion** rule and treat the stat as unknown until re-measured.

---

### B.3 Rounding Bottom (Saucer)

**Geometry (OHLC-detectable):**
- A long, gradual **U-shaped "bowl"**: left lip → lowest valley → right lip. The low should be rounded, **not a sharp V**. The right-side advance should take roughly the **same time** as the left-side decline (time symmetry).
- Watch for a deceptive mid-pattern "bump" (false midway breakout).

**Confirmation / buy trigger:** **close above the left lip / left reaction high** (the price where the decline began). A handle variant draws a trendline from left lip to right lip and buys on a close above it.

**Volume signature:** **U-shaped volume** tracking price — high at the start of the decline, **lowest at the bottom**, rising into the advance. (Volume description from StockCharts; Bulkowski's page states no explicit volume rule.)

**Bulkowski stat (990 perfect trades):** **break-even failure rate 4%**; average rise 48%; performance rank 7/39; throwback 64%; meets target 65%. Source: thepatternsite.com/roundb.html.

**Stated duration:** explicitly **long-term** — "many months," "best suited for weekly charts"; worked examples span ~12–18 months.

**INTRADAY/0DTE APPLICABILITY:** Essentially none. This is a weekly-scale base by definition. Do not implement as a 0DTE entry pattern; if anything, a faint intraday "rounding" is just a slow VWAP/MA reclaim and should be handled by trend logic (A.2), not as a rounding bottom.

---

### B.4 Cup and Handle

**Geometry (OHLC-detectable):**
- **U-shaped cup** (rounded, not a sharp V), preceded by a prior advance.
- **Cup depth:** ideally retraces **≤ 1/3** of the prior advance (1/3–1/2 in volatile markets; ~2/3 max in extremes).
- **Handle:** a smaller pullback on the **right side**, forming in the **upper half of the cup**, retracing **up to ~1/3** of the cup's rally — often a small down-sloping flag/pennant. The two cup rims should sit **near the same price** (resistance = the cup highs).

**Confirmation / buy trigger:** **close above the right cup rim** (horizontal resistance at the cup highs); early entry = close above the down-trendline along the handle highs. StockCharts requires a **volume surge** on the breakout.

**Volume signature:** light through the cup base, **surge on the breakout** above handle resistance. (Bulkowski's page states no explicit volume rule; volume detail from StockCharts.)

**Bulkowski stat (913 perfect bull-market trades):** **break-even failure rate 5%**; average rise 54%; performance rank **3/39** (one of his best bullish patterns); throwback 62%; meets target 61%. Source: thepatternsite.com/cup.html.

**Stated duration:** **cup 7–65 weeks** (StockCharts: 1–6 months, sometimes longer); **handle 1 week minimum, ideally 1–4 weeks**. The slowest-forming pattern in section B.

**INTRADAY/0DTE APPLICABILITY:** None for 0DTE. Cup-and-handle is categorically a multi-week-to-multi-month base. Do not implement intraday.

---

### Section B summary (Bulkowski break-even failure rates)

| Pattern | BE failure | Avg move | Rank | Sample | Confirmation | Source duration |
|---|---|---|---|---|---|---|
| Double Top (Adam&Adam) | **25%** (Eve&Eve ~20%) | −15% | 19/36 | 1,114 | close below valley low | peaks weeks apart |
| Inverse H&S | **11%** | +45% | 13/39 | 3,197 | close above neckline (+vol) | weeks–months |
| Rounding Bottom | **4%** | +48% | 7/39 | 990 | close above left lip | many months (weekly) |
| Cup & Handle | **5%** | +54% | 3/39 | 913 | close above right rim (+vol) | cup 7–65 wk, handle 1–4 wk |

---

## C. Continuation Patterns

> Common volume signature across this whole section (per Bulkowski): volume **contracts through the formation** (~72–86% of the time, pattern-dependent) and **expands on the breakout**. The only exception is the price channel, for which Bulkowski publishes no volume stat.

### C.1 Bull Flag / Bear Flag

**Geometry (OHLC-detectable):**
- **Flagpole:** a sharp, near-vertical prior impulse leg (up for bull, down for bear).
- **Flag:** price moves between **two parallel (or near-parallel) trendlines** — a small rectangle/channel **tilted against the trend**: a **bull flag drifts DOWN**, a **bear flag drifts UP**.
- Detection: fit two lines of **roughly equal slope** (constant-width band) whose slope sign is **opposite** the preceding impulse leg.

**Breakout trigger:** close **beyond the consolidation boundary in the pole's direction** — bull flag breaks **above** the upper line; bear flag breaks **below** the lower line.

**Volume signature:** heavy on the pole, **contracts during the flag** (Bulkowski: downtrend in volume 74% up / 77% down breakouts), **expands on the breakout**.

**Bulkowski stat (thepatternsite.com/flags.html):** **break-even failure rate 44% (up) / 45% (down)**; average move 9% / 8%; **"not ranked"** (flag performance is measured on the short swing, not breakout-to-ultimate-move). *Distinct from the "high and tight flag" (htf.html, 0% failure) — do not conflate.*

**INTRADAY/0DTE APPLICABILITY:** Strong. The flag is one of the most reliable *intraday* continuation reads — a sharp 5m/15m impulse followed by a shallow counter-sloping drift, entered on the break in the trend direction. This is a primary candidate for an intraday detector. Caveat: the 44/45% daily figure is not an intraday stat; re-measure on SPY.

---

### C.2 Pennant

**Geometry (OHLC-detectable):**
- **Flagpole:** same steep impulse leg as a flag.
- **Pennant:** a **small SYMMETRICAL TRIANGLE** — two **converging** lines (upper sloping down, lower sloping up → lower highs AND higher lows), beginning wide and narrowing to an apex.
- **Duration disambiguation:** a pennant is **short (≤ ~3 weeks)**; beyond ~3 weeks it is a true symmetrical triangle/wedge, not a pennant.

**Breakout trigger:** close beyond the consolidation boundary in the **pole's direction**.

**Volume signature:** heavy on pole, **contracts** in the pennant (Bulkowski: downtrend 86%), **expands** on breakout.

**Bulkowski stat (thepatternsite.com/pennants.html, >1,600 perfect trades):** **break-even failure rate 54% (up) / 54% (down)**; average move 7% / 6%; not ranked (same short-swing reason as flags). *Bulkowski keeps flags and pennants on separate pages with separate numbers — there is no single merged "flags and pennants" statistic.*

**INTRADAY/0DTE APPLICABILITY:** Moderate. Like the flag, a pennant can form intraday after a sharp move and is a usable continuation trigger — but its published failure rate (54%) is materially worse than the flag's, so weight it lower. The flag-vs-pennant distinction for the detector is purely **parallel channel (flag) vs. converging triangle (pennant)**.

---

### C.3 Ascending Triangle

**Geometry (OHLC-detectable):**
- **Top line FLAT/horizontal** (resistance); **bottom line rising** (higher lows). Hard constraint (StockCharts): if a newer reaction low is ≤ the previous reaction low, the ascending triangle is **invalid**.
- **Touches:** price should touch one line ≥ 3 times and the other ≥ 2 times (distinct peaks/valleys); lines converge to an apex.

**Breakout trigger:** usually **up** — **close above the horizontal resistance** (which then becomes support). Bulkowski: breaks upward 63% of the time.

**Volume signature:** contracts through the pattern (Bulkowski: downtrend ≥ 78%), expands to confirm the breakout.

**Bulkowski stat (thepatternsite.com/at.html):** **break-even failure rate 17% (up) / 38% (down)**; average move 43% / 13%; rank 16/39 (up), 30/36 (down). The **17% up-breakout is the best in section C**.

**INTRADAY/0DTE APPLICABILITY:** Good. A flat intraday resistance with rising lows (coiling under a level) is a clean, common 0DTE setup and maps onto the engine's "break of a named level" logic. Caveat: need enough bars to register ≥3/≥2 touches; on 5m that is achievable within a session.

---

### C.4 Descending Triangle

**Geometry (OHLC-detectable):**
- **Bottom line FLAT/horizontal** (support); **top line falling** (lower highs).
- **Touches:** one line ≥ 3 times, the other ≥ 2 times; price should traverse the pattern side-to-side ("nearly filling the space," not white space); lines converge.

**Breakout trigger:** usually **down** — **close below the horizontal support**.

**Volume signature:** recedes ~78% of the time, very low just before breakout.

**Bulkowski stat (thepatternsite.com/dt.html):** **break-even failure rate 22% (up) / 23% (down)**; average move 38% / 15%; rank 33/39 (up), 15/36 (down).

**INTRADAY/0DTE APPLICABILITY:** Good (bearish). Flat intraday support with descending highs is a recognizable distribution structure and a usable put trigger on the support break. Same touch-count caveat as C.3.

---

### C.5 Symmetrical Triangle

**Geometry (OHLC-detectable):**
- **Both lines converge:** top slopes **down**, bottom slopes **up** → **lower highs AND higher lows** simultaneously.
- **Touches:** one line ≥ 3, the other ≥ 2 (StockCharts: ≥ 4 points min, ideally 6); price must fill the triangle, not leave white space.

**Breakout trigger:** **either direction** — a **closing** break of a trendline (optional filters: 3% break, or hold for 3 days). Ideal break occurs **½–¾ of the way to the apex**; Bulkowski: upward 60% of the time, 74% of the way to the apex.

**Volume signature:** diminishes through the pattern (Bulkowski: 84–86% downtrend) — "the quiet before the storm" — then expands on the breakout.

**Bulkowski stat (thepatternsite.com/st.html):** **break-even failure rate 25% (up) / 37% (down)**; average move 34% / 12%; rank 36/39 (up), 34/36 (down).

**INTRADAY/0DTE APPLICABILITY:** Moderate. Coils/triangles form constantly intraday; the symmetrical (no flat side) is the least directional, so it is best used as a "compression → expansion" heads-up and traded on the *confirmed close* break rather than anticipated. The apex-timing rule (break ½–¾ to apex) is a useful intraday filter.

---

### C.6 Rising Wedge

**Geometry (OHLC-detectable):**
- **Both trendlines slope UP and converge** (higher highs and higher lows, but the lower line rises faster so the channel narrows). **Bearish bias** despite the upward slope.
- **Touches:** ≥ 5 total (≥ 3 on one line, ≥ 2 on the other).

**Breakout trigger:** any direction but **downward 60%** of the time; the bearish resolution is a break **below the rising lower line**.

**Volume signature:** trends down ~79% until the breakout.

**Bulkowski stat (thepatternsite.com/risewedge.html):** **break-even failure rate 19% (up) / 51% (down)**; average move 38% / 9%; rank 32/39 (up), **36/36 — dead last (down)**. Bulkowski flags the down-breakout as having "unacceptably high failure rates and small post-breakout declines."

**INTRADAY/0DTE APPLICABILITY:** Use with caution. A rising wedge into intraday resistance is a recognizable exhaustion read, but the **51% down-breakout failure** (worst-ranked pattern Bulkowski tracks) is a strong warning even on daily data — do not over-weight a wedge break intraday; require corroboration (CHoCH, volume, level).

---

### C.7 Falling Wedge

**Geometry (OHLC-detectable):**
- **Both trendlines slope DOWN and converge** (lower highs and lower lows, upper line falling faster). **Bullish bias** despite the downward slope.
- **Touches:** ≥ 5 total (≥ 3 / ≥ 2).
- **Min duration disambiguation:** Bulkowski sets **3 weeks minimum**, otherwise it is a *pennant*.

**Breakout trigger:** any direction but **upward 68%** of the time; bullish resolution = break **above the falling upper line**.

**Volume signature:** trends down ~72–75% until the breakout.

**Bulkowski stat (thepatternsite.com/fallwedge.html, >800 perfect trades):** **break-even failure rate 26% (up) / 29% (down)**; average move 38% / 14%; rank 31/39 (up), 27/36 (down).

**INTRADAY/0DTE APPLICABILITY:** Moderate (bullish). A converging down-channel that resolves up is a usable intraday reversal/continuation read. Note Bulkowski's own 3-week-minimum rule means an intraday "falling wedge" is, by his taxonomy, really a **pennant** — so for detection purposes a short converging down-channel after an impulse should be classified as a pennant (C.2), and only a longer structure as a true falling wedge.

---

### C.8 Channel (Price Channel)

**Geometry (OHLC-detectable):**
- **Two PARALLEL trendlines, both tilting the same direction** (equal slope, constant-width band). **Up channel** = both slope up (bullish); **down channel** = both slope down (bearish). A **flat/horizontal channel is treated as a rectangle**, not a channel.
- Detection: fit two equal-slope lines; the slope sign sets the channel type.

**Trading the bounce vs. the breakout:**
- **Bounce (with-trend):** in an up channel, buy rebounds off the **lower** line; in a down channel, short turns down off the **upper** line.
- **Breakout:** trade a **close outside** a boundary (either direction).

**Volume signature:** not specified by Bulkowski.

**Bulkowski stat (thepatternsite.com/channels.html):** **no published stat** — Bulkowski states explicitly he "haven't studied channels for performance (statistics)." No break-even failure rate, average move, or rank exists.

**INTRADAY/0DTE APPLICABILITY:** Strong (as context). Intraday price spends much of its time in channels; the bounce-off-the-band and break-of-the-band logic both apply directly and pair well with VWAP/EMA-ribbon context. Caveat: no published edge stat at all — treat channel signals as discretionary structure, validated only by our own data.

---

### Section C summary (Bulkowski break-even failure rates, up / down)

| Pattern | BE failure up/down | Avg move | Rank up/down | Source |
|---|---|---|---|---|
| Flag (ordinary) | 44% / 45% | 9% / 8% | not ranked | flags.html |
| Pennant | 54% / 54% | 7% / 6% | not ranked | pennants.html |
| Ascending triangle | **17%** / 38% | 43% / 13% | 16/39, 30/36 | at.html |
| Descending triangle | 22% / 23% | 38% / 15% | 33/39, 15/36 | dt.html |
| Symmetrical triangle | 25% / 37% | 34% / 12% | 36/39, 34/36 | st.html |
| Rising wedge | 19% / **51%** | 38% / 9% | 32/39, 36/36 | risewedge.html |
| Falling wedge | 26% / 29% | 38% / 14% | 31/39, 27/36 | fallwedge.html |
| Price channel | no published stat | — | — | channels.html |

**Trendline-fit cheat sheet (for the detector):**
- flat top + rising bottom (converging) → **ascending triangle**
- flat bottom + falling top (converging) → **descending triangle**
- falling top + rising bottom (converging) → **symmetrical triangle** (or **pennant** if short + after a steep pole)
- both up, converging → **rising wedge** (bearish)
- both down, converging → **falling wedge** (bullish; if short → pennant)
- both parallel, same slope → **channel** (flat → rectangle); **flag** = a short parallel channel sloping *against* a prior steep pole

---

## D. Candlestick Patterns (multi-bar, beyond standard single/two-bar)

> Body/gap terms below are in OHLC. "Body" = `|close − open|`; "upper shadow" = `high − max(open,close)`; "lower shadow" = `min(open,close) − low`. On 24/5 index/ETF intraday data, literal price **gaps** between consecutive 5m/15m bars are rare except at the regular-session open — see each applicability note.

### D.1 Morning Star (bullish, 3-bar)

**OHLC definition (StockCharts + Bulkowski):**
- **Candle 1:** a **tall black/bearish** candle, extending an existing **downtrend**.
- **Candle 2 (the "star"):** a **small-bodied** candle of **any color** that **gaps DOWN** below candle 1's body (Bulkowski: gaps below the bodies; ignore shadows).
- **Candle 3:** a **tall white/bullish** candle that **gaps up** from candle 2 and **closes above the midpoint of candle 1's body** (Bulkowski: "closes at least midway into the body of the first day").

**Code sketch:**
```
c1_bear = close[1] < open[1] and body[1] large
c2_small = body[2] small and max(open[2],close[2]) < min(open[1],close[1])   # star gaps below c1 body
c3_bull = close[3] > open[3] and close[3] > (open[1]+close[1])/2             # closes past c1 midpoint
```

**Bulkowski stat:** acts as a **bullish reversal 78% of the time**; performance rank **12/103** candle patterns. Source: thepatternsite.com/MorningStar.html.

**INTRADAY/0DTE APPLICABILITY:** Usable with a caveat. The 3-bar bullish-reversal shape (big down bar → small indecision bar → big up bar reclaiming half the down bar) is meaningful on 5m/15m at a support level. **But the literal gap requirements rarely hold intraday** (continuous tape), so relax candle-2's "gap down" to "small body near/below candle-1's low" and keep the hard rule = **candle 3 closes above candle 1's midpoint**. Treat the 78% as daily-derived, not intraday.

---

### D.2 Evening Star (bearish, 3-bar)

**OHLC definition (StockCharts + Bulkowski):**
- **Candle 1:** a **tall white/bullish** candle in an **uptrend**.
- **Candle 2 (the "star"):** a **small-bodied** candle of **any color** that **gaps UP** above candle 1's body (ignore shadows).
- **Candle 3:** a **tall black/bearish** candle that opens below the star and **closes at least midway down candle 1's body** (i.e. below candle 1's midpoint).

**Code sketch:**
```
c1_bull = close[1] > open[1] and body[1] large
c2_small = body[2] small and min(open[2],close[2]) > max(open[1],close[1])   # star gaps above c1 body
c3_bear = close[3] < open[3] and close[3] < (open[1]+close[1])/2             # closes below c1 midpoint
```

**Bulkowski stat:** acts as a **bearish reversal 72% of the time**; performance rank **4/103** candle patterns. Source: thepatternsite.com/EveningStar.html.

**INTRADAY/0DTE APPLICABILITY:** Usable, same caveat as morning star. Strong 3-bar topping read at intraday resistance; relax candle-2's "gap up" to "small body near/above candle-1's high," keep the hard rule = **candle 3 closes below candle 1's midpoint**. 72% is daily-derived.

---

### D.3 Harami (bullish & bearish, 2-bar)

**OHLC definition (StockCharts):** a **small body completely contained within the range of the previous (large) body, and of the opposite color**. (Japanese "harami" = pregnant; large candle = mother, small candle = the contained child.)
- **Bullish harami:** large **black/bearish** candle, then a **small white/bullish** body contained inside it (appears in a downtrend → potential bullish reversal).
- **Bearish harami:** large **white/bullish** candle, then a **small black/bearish** body contained inside it (appears in an uptrend → potential bearish reversal).

**Containment rule to code (body-inside-body):**
```
prev_body_hi = max(open[1], close[1]); prev_body_lo = min(open[1], close[1])
this_body_hi = max(open[0], close[0]); this_body_lo = min(open[0], close[0])
contained = this_body_hi <= prev_body_hi and this_body_lo >= prev_body_lo
small_vs_large = body[0] < body[1]            # child clearly smaller than mother
opposite_color = sign(close[0]-open[0]) != sign(close[1]-open[1])
```
(Classic harami compares **bodies**, not full ranges. A stricter variant requires the entire range contained; document which you use. **No published Bulkowski failure-rate quoted here — "no published stat"** in the material gathered; treat as a context/indecision signal.)

**INTRADAY/0DTE APPLICABILITY:** Usable as a momentum-stall flag. Harami needs **no gap**, so it ports cleanly to 5m/15m — a large impulse bar followed by a small opposite-color inside bar signals momentum pausing (an inside-bar variant). Weak as a standalone trigger intraday; best as a confirmation that a swing/level is holding (combine with A.1/A.3).

---

### D.4 Pin Bar (Pinocchio bar, 1-bar)

**OHLC definition (price-action literature):** a single candle with **one long wick, a small body, and little/no opposite wick** — a rejection candle.
- **Bullish pin bar:** **long LOWER wick**, small body in the **upper** portion of the range, close near the high — sellers pushed down and were rejected.
- **Bearish pin bar:** **long UPPER wick**, small body in the **lower** portion, close near the low — buyers pushed up and were rejected.
- **Proportion rule (commonly cited):** the long wick must be **≥ ~2–3× the body**, and the wick should be **≥ ~2/3 of the candle's total range**.

**Code sketch:**
```
rng = high - low; body = abs(close-open)
upper_w = high - max(open,close); lower_w = min(open,close) - low
bullish_pin = lower_w >= 2*body and lower_w >= (2/3)*rng and upper_w small
bearish_pin = upper_w >= 2*body and upper_w >= (2/3)*rng and lower_w small
```
(**No published Bulkowski failure-rate** under the name "pin bar"; it overlaps Bulkowski's hammer/shooting-star single-bar patterns. "No published stat" for the pin-bar label specifically.)

**INTRADAY/0DTE APPLICABILITY:** Strong. The pin bar is one of the most useful *single-bar* intraday rejection signals — needs no gap, fires on one closed 5m/15m bar, and maps directly onto the engine's "wick rejection at a named level / VWAP" logic. Caveat: 0DTE chop produces many low-quality pins; require the pin to occur **at a level/swing** (A.1) and confirm with the next bar or a close-based filter, exactly as with the BOS wick-vs-close discipline.

---

## E. MACD Divergence

**MACD construction (StockCharts; standard 12/26/9):**
- **MACD line = 12-period EMA − 26-period EMA** (of close).
- **Signal line = 9-period EMA of the MACD line.**
- **Histogram = MACD line − signal line.**
- Parameters (12, 26, 9) are the defaults and may be adjusted; closing prices are used.

Divergence compares the **slope of price swings** to the **slope of the corresponding MACD swings** (use MACD-line peaks/troughs, aligned to the price swing points from A.1).

### E.1 Regular Divergence (reversal signal)

- **Regular bullish divergence:** price makes a **lower low**, but MACD makes a **higher low**. The lower low confirms the current downtrend, but the higher MACD low shows **less downside momentum** → potential bullish reversal. (StockCharts.)
- **Regular bearish divergence:** price makes a **higher high**, but MACD makes a **lower high**. The higher high is normal for the uptrend, but the lower MACD high shows **waning upside momentum** → potential bearish reversal. (StockCharts.)

### E.2 Hidden Divergence (continuation signal)

Hidden divergence is the inverse construction and signals **trend continuation** (it appears on the pullback within a trend). The mapping (standard TA definition; same MACD-vs-price swing comparison):
- **Hidden bullish divergence:** price makes a **higher low**, but MACD makes a **lower low** → momentum supports the **ongoing uptrend** (continuation up). Appears on a pullback in an uptrend.
- **Hidden bearish divergence:** price makes a **lower high**, but MACD makes a **higher high** → supports the **ongoing downtrend** (continuation down). Appears on a bounce in a downtrend.

**Mnemonic for the detector:** *regular* divergence reads the **extreme** that the indicator fails to confirm (reversal); *hidden* divergence reads the **counter-trend pullback** that the indicator over-extends on (continuation). For both, price-extreme direction and MACD-extreme direction **disagree** — what differs is whether you are comparing the trend's new extreme (regular) or the pullback's interim extreme (hidden).

**Detection sketch:**
```
# align MACD swing to each confirmed price swing (A.1)
regular_bullish  = price_LL and macd_HL     # lower low in price, higher low in MACD
regular_bearish  = price_HH and macd_LH     # higher high in price, lower high in MACD
hidden_bullish   = price_HL and macd_LL     # higher low in price, lower low in MACD
hidden_bearish   = price_LH and macd_HH     # lower high in price, higher high in MACD
```

**Caveat (StockCharts):** divergences **frequently occur inside strong trends without producing a reversal** — MACD can "diverge" repeatedly while a trend persists. Do not trade divergence in isolation; require a structure confirmation (a CHoCH/BOS from section A, or a level/candle trigger). **No published failure-rate stat** for MACD divergence.

**INTRADAY/0DTE APPLICABILITY:** Applicable but secondary. MACD divergence on 5m/15m is a legitimate momentum-exhaustion read and complements the engine's reversal setups, but MACD on fast intraday bars is noisy and lagging (it is built from EMAs). Use it as a **confirming filter** on an A-section structure signal, not a standalone 0DTE trigger; the "divergence persists in strong trends" warning is especially acute intraday.

---

## Sources

**Bulkowski — ThePatternSite (Encyclopedia of Chart Patterns, online companion):**
- Adam & Adam Double Top — https://thepatternsite.com/aadt.html
- Head-and-Shoulders Bottom (inverse H&S) — https://thepatternsite.com/hsb.html
- Rounding Bottom — https://thepatternsite.com/roundb.html
- Cup with Handle — https://thepatternsite.com/cup.html
- Flags — https://thepatternsite.com/flags.html
- High and Tight Flag (disambiguation) — https://thepatternsite.com/htf.html
- Pennants — https://thepatternsite.com/pennants.html
- Ascending Triangle — https://thepatternsite.com/at.html
- Descending Triangle — https://thepatternsite.com/dt.html
- Symmetrical Triangle — https://thepatternsite.com/st.html
- Rising Wedge — https://thepatternsite.com/risewedge.html
- Falling Wedge — https://thepatternsite.com/fallwedge.html
- Price Channel (no published stat) — https://thepatternsite.com/channels.html
- Failure Rate study (break-even-failure-rate definition) — https://thepatternsite.com/FailureRates.html
- Morning Star — https://thepatternsite.com/MorningStar.html
- Evening Star — https://thepatternsite.com/EveningStar.html

**StockCharts ChartSchool:**
- Head-and-Shoulders Bottom — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/head-and-shoulders-bottom
- Cup with Handle — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/cup-with-handle
- Rounding Bottom — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/rounding-bottom
- Flag / Pennant — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/flag-pennant
- Ascending Triangle — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/ascending-triangle
- Symmetrical Triangle — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/symmetrical-triangle
- Price Channel — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/price-channel
- Rectangle (horizontal-channel cross-reference) — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/rectangle
- Candlestick Pattern Dictionary (morning/evening star, harami, star) — https://chartschool.stockcharts.com/table-of-contents/chart-analysis/candlestick-charts/candlestick-pattern-dictionary
- MACD oscillator (construction + divergence) — https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/macd-moving-average-convergence-divergence-oscillator

**Market structure — swing/fractal, BOS, CHoCH:**
- Williams Fractal — TradingView — https://www.tradingview.com/support/solutions/43000591663-williams-fractal/
- Fractals — MetaTrader 5 Help — https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/fractals
- Williams Fractal: Spotting Reversal in Trends — LuxAlgo — https://www.luxalgo.com/blog/williams-fractal-spotting-reversal-in-trends/
- Fractal Indicator Trading Strategy / Backtest — QuantifiedStrategies — https://www.quantifiedstrategies.com/fractal-indicator-trading-strategy/
- BOS vs CHoCH — Mind Math Money — https://www.mindmathmoney.com/articles/break-of-structure-bos-and-change-of-character-choch-trading-strategy
- SMC Market Structure: BoS and CHoCH — DailyPriceAction — https://dailypriceaction.com/blog/smc-market-structure/
- Break of Structure (BOS) Explained — FluxCharts — https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/Break-of-Structures
- Market Structure Shift (ICT) — TradeThePool — https://tradethepool.com/technical-skill/ict-market-structure-shift/
- Break of Structure vs Change of Character — Smart Money ICT — https://smartmoneyict.com/break-of-structure-vs-change-of-character-in-ict/

**Trend definition (Dow Theory) — HH/HL/LH/LL:**
- Dow Theory (Part 1): trends — Zerodha Varsity — https://zerodha.com/varsity/chapter/dow-theory-part-1/
- Dow Theory — Trends — IncredibleCharts — https://www.incrediblecharts.com/technical/dow_theory_trends.php
- Dow Theory — QuantifiedStrategies — https://www.quantifiedstrategies.com/dow-theory/

**Pin bar (price-action literature):**
- What is the Pinbar Candlestick and How to Trade It — Tradeciety — https://tradeciety.com/what-is-the-pinbar-candlestick-and-how-to-trade-it
- Pin Bar Candlestick Pattern — Strike.money — https://www.strike.money/technical-analysis/pin-bar
