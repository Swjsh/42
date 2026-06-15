# Chart Anatomy — Reading the Setup the Way J Reads It

> Synthesized from the three real winning trades (4/29, 5/1, 5/4) and J's chart annotations. Purpose: translate what J sees visually into a model Gamma can encode programmatically. This is the reference for the heartbeat's chart-reading logic.

---

## J's indicator stack — the lens

What's on J's TradingView chart (visible across all three screenshots):

| Layer | What it is (best inference) | What it means in J's framework |
|---|---|---|
| **EMA ribbon** | Stacked exponential moving averages with color-shaded bands (yellow → green → blue when bullish; red → yellow → blue when bearish). Likely 5/8/13/21/34/55-period EMAs or similar. | Trend filter + dynamic trailing stop. The ribbon's color tells you who's in control. |
| **Golden Cross / Death Cross markers** | Indicator labels printing at moving-average crossovers (likely a faster/slower EMA pair, e.g., 9/21). | Lagging confirmation. By the time it prints, the move is usually underway — useful for confidence, not for entry timing. |
| **Buy / sell triangles (cyan / yellow)** | Indicator-printed mechanical signals. Likely from a paid indicator (SuperTrend, LuxAlgo Premium, or similar). Cyan ▲ = buy print, yellow ▼ = sell print. | Mechanical-system layer. J doesn't appear to enter purely on triangles, but they confirm the momentum direction at the visual level. |
| **User-drawn horizontal levels** | Solid blue/light-blue horizontals at premarket high/low, prior day high/low, key intraday levels (e.g., 721.58, 711.40, 709.40). | Where price has memory. The level is where the trade lives or dies. |
| **User-drawn trendlines** | Cyan/light-blue diagonal lines connecting either descending highs or ascending lows. Drawn manually, often spanning multiple sessions. | Directional bias on a higher timeframe. Multi-day trendline + intraday level = confluence trade. |
| **Volume profile** | Standard volume bars at the bottom, color-matched to the candle direction. | Conviction. Big breakdown candle without volume = weak. Big breakdown candle with volume spike = real. |

---

## The visual signature — what J's eye sees

When the setup fires, J's chart visually shifts in a recognizable way. Across all three trades, the signature is:

1. **The ribbon was flat or bullish-stacked, then it transitions.** Yellow / cyan / blue stack (bullish) → red / yellow stack (bearish). The transition itself is the moment.
2. **Price has just touched a horizontal level from below** — and the candle that touched it closes back below.
3. **A yellow ▼ triangle prints** within a candle or two of the rejection. Confirmation.
4. **The next candle breaks down through the ribbon** with volume support.
5. **The Death Cross marker prints** somewhere in the next 15–30 min of the move (lagging — usually after entry is already paying).

It's a stack of signals, not a single one. The setup is the *concurrence*, not any individual print.

---

## Trade-by-trade reconstruction

### 4/29/2026 — SPY 710P 0DTE — +34%

**Chart context (best read of what J was seeing):**

- **Pre-market and overnight (06:00–09:30):** SPY was bleeding from ~714 down toward ~710 area, with a sharp red wick down around 06:00 (visible on the chart as a long red candle that punched well below the ribbon, then reabsorbed). This sets the day's bias as **bearish** before the bell even rings.
- **The ribbon at the open:** bearish-stacked. Red and yellow on top, blue underneath. Price living at or below the ribbon.
- **Open through 10:00:** SPY tried to bounce. Got up into the ribbon. The rally was met with a **cyan ▲ buy print** (visible on the chart) — but the rally died right there. Bullish signal that didn't deliver.
- **10:00–10:25 (the entry window):** SPY pushed up to test the **711.40 level** (your drawn horizontal). Reached it, formed a candle that wicked above and **closed back below**. A **yellow ▼ sell triangle printed** at exactly that candle (visible right next to the green arrow you drew). The ribbon, which had been transitioning during the bounce, fully restacked bearish.
- **Your entry, 10:25:51:** "right at the break." Translation: SPY just printed the rejection candle at 711.40, ribbon flipped bearish, sell triangle confirmed. You bought 6 puts at $1.67. The premium math says your entry was tight to the rejection (small stop required, big leverage if move continues).
- **10:30–11:30:** SPY broke down through the ribbon's middle band. Volume picked up on the breakdown candles. Ribbon expanded (red band widened — momentum confirmation). SPY ran from 711 → ~709.40, the lower horizontal. **The 709.40 level was your target.**
- **11:30–12:30 (where you weren't watching):** SPY ranged 709.40–710.50, retested 709.40 multiple times. Premium expanded toward $2.00–2.50 as time decay added bearish gamma to the position.
- **12:27–12:37 (your exits):** You sold 5 at $2.15, then 1 at $2.69. The chart shows SPY put in a small wedge / range during this window. You exited based on availability, not signal — the ribbon was still bearish, no Cyan ▲ had printed yet.
- **Afterward (the "money you left"):** SPY chopped lower into the early afternoon, then rallied back up. The "Golden Cross" marker prints later (yellow vertical line). By 16:00 SPY was back near 712. Your 710P decayed to near zero by the close. You were OUT before the reversal — that's lucky given the management compromise.

**The visual story:** SPY tested a defined resistance from below, got rejected exactly where the level lived, the ribbon flipped at the rejection, the sell triangle confirmed, and the breakdown ran to the next level (your target). Textbook execution on the entry. Imperfect on management because of work distractions.

---

### 5/1/2026 — SPY 721P 0DTE — +72%

**Chart context:**

- **Pre-market into open:** SPY up day setting up. Opened near 720, rallied hard.
- **09:30–10:00:** Strong push to ~724.80 — the day's high. **Bullish ribbon-stacked** (cyan/yellow on top). Multiple buy triangles in this window. Bulls in control.
- **10:00–11:00:** Lower high formed. SPY pulled back to ~722, attempted to push back up to 724, failed. **First lower high.** This is when the descending trendline starts to draw itself.
- **11:00–13:00 (the day's structural break):** Multiple **yellow ▼ sell triangles** printed in this window. Ribbon transitioning — losing the cyan/yellow bullish stack, gaining the red/yellow bearish stack. By 12:30, ribbon is fully bearish-colored. SPY trading in 720–723 range under the descending trendline.
- **13:00–13:09 (your premature entry):** SPY at ~722.20, BELOW the descending trendline (which was around 723.50 at this point). The trendline hadn't been re-tested yet. The setup was *forming*, not *fired*. You bought 10 puts at $0.46 anticipating the test + rejection. **The bias was right; the trigger hadn't fired yet.**
- **13:09–13:36 (the adverse move):** SPY rallied UP toward the descending trendline. The chart was *moving toward the actual setup completion*. From a chart-reading perspective, this period is where the setup is *about to fire* — but from a P&L perspective, you're losing because you were already long puts. Premium drops to $0.19. Painful if you don't trust the chart.
- **13:36 (the actual trigger fire):** SPY kissed the descending trendline at ~723.20. **The candle wicked into it and closed back below.** That's the rejection candle. Ribbon was already bearish-stacked (had been since ~12:00). The sell triangle indicator was printing. The Death Cross marker hadn't yet printed but the ribbon transition was complete. *This is where the entry trigger fires.* You bought 10 more at $0.19.
- **13:36–14:47 (the legitimate leg):** SPY rolled off the trendline. Each candle closed bearish. Ribbon expanded. Volume picked up. SPY moved from 723 → ~722 → testing lower levels.
- **14:47 (your exit):** SPY at ~722, back at the mid-range. Premium back to $0.56 (above your blended cost of $0.325). You sold all 20. Exit at a defined intraday level — disciplined, but conservative.
- **14:47–16:00 (what happened after):** SPY continued lower. Made the day's low around 720 / 719 area near 16:00. The "Death Cross" indicator prints near 16:00 — confirming the trend had broken. Heavy red volume bars on the close. Your puts would have been worth significantly more if held — but you exited per plan.

**The visual story:** A morning rally that died, a descending trendline that drew itself through lower highs, a ribbon that transitioned slowly across two hours, and a final rejection at the trendline that completed the setup. You saw it forming and entered too early. The trigger came at 13:36, exactly where the playbook says it should.

---

### 5/4/2026 — SPY 721P 0DTE — +86% (the cleanest example)

**Chart context (this is the most instructive):**

- **Pre-market (golden-shaded area):** SPY testing the **721.58 level** multiple times. Each test rejected. Pre-market high established and respected. Your drawn horizontal is the artifact of this — you put it there because the level had been tested and held repeatedly.
- **Continuation context (visible in the second screenshot):** The descending trendline from the 5/1 morning high *extends across* into 5/4. Same trendline, two days later, still capping highs. **This is multi-day structure.** When the day-of trendline and the multi-day trendline align at the same level, the rejection is pre-loaded with weight.
- **Open (09:30):** SPY around 720. Ribbon transitioning — was bullish into the close on 5/3, but premarket selling started to flip it.
- **09:30–10:25 (the run-up to entry):** SPY rallied off the open toward 721.58. Ribbon began re-stacking bullish briefly during this push — cyan/yellow appearing at the top. **A 'Golden Cross' marker printed** at the yellow vertical line. *In isolation, that's a bullish signal — but it's a counter-trend bullish signal in a bearish multi-day context, which is exactly the kind that gets faded.*
- **10:27 (your entry — the blue circle):** SPY pushed up to **721.58 area** (also called 721.30–721.70 depending on the candle close). Touched it. **Wicked above slightly, closed back below.** The candle is the textbook rejection. Volume on the rejection candle was elevated. *That same moment*, the ribbon flipped — you can see the color flip from bullish-stacked to bearish-stacked in the candles around the blue circle. You bought 10 puts at $0.85.
- **10:30–11:00:** Brief adverse move. SPY drifted slightly higher within a small range. The ribbon stayed bearish-stacked despite the upward drift. *This is the test of conviction* — bias right, trigger right, but price hasn't moved yet. The chart reading says "hold." You held.
- **11:00 (the breakdown):** SPY broke decisively down through the ribbon's middle band. The break was on volume (red volume bar visible). Ribbon expanded. Yellow ▼ triangles printing. **This is where the leg starts.**
- **11:00–11:18 (the leg):** SPY ran from ~721 → ~717.50 in 18 minutes. Every 3-min candle closed below the ribbon. No closes back into the yellow band. The ribbon "rode" with price — staying bearish-stacked, providing the trail.
- **11:14 (TP1):** You sold 8 of 10 at $1.50. Smart — you scaled most of the size off at +76% gain.
- **11:18 (final exit):** You sold the runner at $1.90. Why? Because the chart was telling you the leg was exhausting: long lower wick on a candle, decelerating momentum, possible bounce signature. Premium peaked there. **You took the runner near the optimal exit.**
- **11:18 onward:** SPY bounced. Cyan ▲ buy triangles started printing (visible in screenshot 2 around the post-low recovery). Ribbon began narrowing — the bearish stack starting to dissolve. By 12:00 SPY had recovered to ~720. **You were OUT before the bounce hurt you.**
- **The "Death Cross" marker printed later in the day** — confirming the trend break, but printing well after your exit. Lagging confirmation, as expected.

**The visual story:** A premarket level repeatedly tested and respected. A multi-day trendline still in play. A push to the level on the open. A textbook rejection candle exactly at the level. A simultaneous ribbon flip. A breakdown leg riding the ribbon down. An exit at the local low based on the bounce signature, not on a fixed price target. **This is the reference example.**

---

## Common anatomy across all three

What all three winning trades share — this is the *signature* the heartbeat looks for:

| Element | 4/29 | 5/1 | 5/4 |
|---|---|---|---|
| Bearish multi-period context (downtrend or fade in progress) | ✅ | ✅ (within-day) | ✅ (multi-day) |
| A defined horizontal level being respected | ✅ 711.40 | ✅ trendline at ~723.20 | ✅ 721.58 (premarket) |
| Rejection candle at the level (touch + close back below) | ✅ | ✅ (on leg #2) | ✅ |
| Yellow ▼ sell triangle within ±2 candles of the rejection | ✅ | ✅ | ✅ |
| EMA ribbon flips bearish at or just before entry | ✅ | ✅ | ✅ (cleanest) |
| Volume picks up on the breakdown candle | ✅ | ✅ | ✅ |
| Breakdown leg lasts 30–90 min | ~60 min | ~70 min | ~50 min |
| First TP at next defined level or +50% premium | (skipped) | ✅ | ✅ |
| Runner exits on bounce signature / ribbon retest | (skipped) | (taken at level) | ✅ |
| Death Cross marker prints during/after the move | ✅ later | ✅ later | ✅ later |

**The unified setup:** bearish context + level rejection + ribbon flip + sell triangle = entry. Breakdown candle + volume = confirmation. Ribbon ride = management. Bounce signature = exit. **This is what Gamma encodes.**

---

## Numerical definitions — the single source of truth (added 2026-05-07)

These terms appear throughout `playbook.md`, `heartbeat.md`, and `risk-rules.md`. Every soft adjective that the heartbeat has to evaluate gets a number here. If a definition changes, change it here first; downstream prompts reference these names.

### `vol_baseline_20bar(tf)`
20-bar simple moving average of `volume` on the same timeframe as the bar being evaluated. Computed from the 20 bars **immediately preceding** the bar under evaluation (does not include the bar itself). Used by all "vol ≥ Nx avg" filters and by the volume-divergence rule.

- 5-min context → 20× 5-min bars = 100 minutes of trading time.
- 15-min context → 20× 15-min bars = 5 hours.
- If <20 bars are available (early session, fresh symbol), use the bars available and tag the comparison `low_confidence` in loop-state — the filter still evaluates but Sonnet escalation is required to act on it.

### `range_baseline_20bar(tf)`
20-bar SMA of `(high - low)` on the same timeframe as the bar being evaluated, same window rules as `vol_baseline_20bar`. Used by the reversal-bar formula.

### `vix_rising` / `vix_falling` / `vix_flat`
Computed from `loop-state.vix_cache.value` and `loop-state.vix_cache.prior_value`:
- `rising`  ⟺ `value > prior_value + 0.05`
- `falling` ⟺ `value < prior_value - 0.05`
- `flat`    ⟺ otherwise
- `cached`  ⟺ this tick reused the cache without refreshing

The deadband (±0.05) is intentional — VIX prints noise within 0.04 from quote to quote during normal hours. Anything inside that is "flat." Filters 8 (bearish needs `rising`, bullish needs `falling`) reject `cached` and `flat` outright; filter 8 only passes on a fresh `rising`/`falling` print from a real refresh.

### `reversal_bar_bullish`
A bar qualifies as a bullish reversal bar (used by bullish filter 10) iff ALL of:
- `close > open` (green body)
- `(high - low) ≥ 1.5 × range_baseline_20bar(tf)` (wide-range bar)
- `close ≥ low + 0.7 × (high - low)` (close in the upper 30% of the range — buyers controlled the close)
- `volume ≥ 1.5 × vol_baseline_20bar(tf)` (already in filter 10; included here for completeness)

### `reversal_bar_bearish`
Mirror of the bullish version (used implicitly in bearish setup confirmation, though bearish filter 10 currently uses the breakdown-bar definition below):
- `close < open`
- `(high - low) ≥ 1.5 × range_baseline_20bar(tf)`
- `close ≤ high - 0.7 × (high - low)` (close in the lower 30% of the range)
- `volume ≥ 1.5 × vol_baseline_20bar(tf)`

### `breakdown_bar_bearish`
The "last bar red" condition in bearish filter 9:
- `close < open`
- `close < Fast EMA`
- `(close - high) > 0.6 × (low - high)` (i.e., body is in the lower 40% of the range — small upper wick, big body)
- `volume ≥ 1.3 × vol_baseline_20bar(tf)`

### `volume_divergence_failed`
Defined for the bar at index `n`. The setup is invalidated when ALL of:
- Bar `n` was a breakdown_bar_bearish (or symmetric reversal for bullish setups)
- Bar `n+1` or `n+2` (the very next bar OR the one after — "within 1–2 bars" is exactly two bars) closes in the opposite direction (UP for bearish, DOWN for bullish)
- That recovery bar's `volume ≥ bar_n.volume`

The recovery bar's volume meeting OR exceeding the trigger bar's volume = failed setup. Filter 7 is exactly the negation: "no `volume_divergence_failed` in the last 2 bars."

### `multi_day_trendline`
A trendline qualifies as multi-day (used by the "confluence" trigger third option) iff:
- ≥2 distinct touches (the line passes within ±$0.05 of a swing high/low for bearish/bullish)
- AND age ≥ 90 minutes of trading time (rules out same-lunch-hour drawing)

The 90-min floor is the threshold for "this line has earned the right to mean something." A 30-min trendline on a 5-min chart is just connect-the-dots.

### Candlestick patterns (NEW 2026-05-07 — boosts trigger conviction)

Per-bar geometric primitives. All math on a single bar's OHLC; no extra data needed.

```
range = high - low
body = abs(close - open)
upper_wick = high - max(open, close)
lower_wick = min(open, close) - low
body_pct = body / range            (0 if range == 0)
upper_wick_pct = upper_wick / range
lower_wick_pct = lower_wick / range
is_red = close < open
is_green = close > open
```

**Single-bar patterns** (require `range > 0`):

| Name | Definition | Use |
|---|---|---|
| `doji` | `body_pct < 0.10` | indecision — pause for confirmation |
| `shooting_star` | `is_red AND upper_wick_pct >= 0.50 AND lower_wick_pct <= 0.20 AND body_pct <= 0.30` | bearish reversal at resistance |
| `hammer` | `is_green AND lower_wick_pct >= 0.50 AND upper_wick_pct <= 0.20 AND body_pct <= 0.30` | bullish reversal at support |
| `bearish_marubozu` | `is_red AND body_pct >= 0.75 AND upper_wick_pct <= 0.10 AND lower_wick_pct <= 0.10` | strong bearish continuation |
| `bullish_marubozu` | `is_green AND body_pct >= 0.75 AND upper_wick_pct <= 0.10 AND lower_wick_pct <= 0.10` | strong bullish continuation |

**Two-bar patterns** (require both bars have `range > 0`):

| Name | Definition | Use |
|---|---|---|
| `bearish_engulfing` | bar1 green AND bar2 red AND bar2.body_pct >= 0.50 AND bar2.open >= bar1.close AND bar2.close <= bar1.open | strong bear reversal at resistance |
| `bullish_engulfing` | mirror: bar1 red, bar2 green covering | strong bull reversal at support |

**Role: AWARENESS LANGUAGE, NOT triggers** (revised 2026-05-07 after backtest).

The v4 backtest tested candlestick patterns as a 5th trigger source. Result: 13 → 17 trades but P&L $309 → $135 (-56%) and expectancy $24 → $8 (-67%). The marubozu detection added too many mid-trend continuation entries that didn't have edge. Patterns are NOT triggers.

**What they ARE used for:**
1. **Live chart description.** When Gamma describes a bar to J in chat, name the pattern: "12:30 bar near-marubozu bearish, body 76% of range" instead of "red bar with above-avg vol."
2. **Journal narrative.** Trade entries reference the pattern that fired: "entry at 11:50 — bearish_engulfing of 11:40 wick + level_rejection of 735.40 + ribbon_flip."
3. **Daily-review forensics.** When grading why a setup worked or failed, candlestick context adds color: "the entry bar was a doji — no conviction either way; trade should have waited for a clear marubozu or engulfing pattern."
4. **Skipped-setups context.** A skipped setup that LATER printed a clean engulfing is documented — feeds R&D for future trigger sources.

**Filter 10 triggers remain at "≥ 2 of 4":** level_reject / ribbon_flip / multi_day_confluence / sequence_rejection. No candlestick contribution.

**Today's reference:**
- The **12:30 5-min bar** (open 735.29, high 735.41, low 734.82, close 734.84) had body_pct=0.76, upper_wick_pct=0.20, lower_wick_pct=0.03, is_red=true → near-marubozu bearish (body just over 0.75 with slightly oversized upper wick, but qualifies as strong bear continuation). With sequence_rejection ALSO firing at the broken 735.40 level, that's 2 of 5 triggers met = entry would have been valid.
- The **11:40 5-min bar** (open 736.08, high 736.12, low 735.70, close 735.84) had body_pct=0.57, upper_wick_pct=0.10, lower_wick_pct=0.33, is_red=true → does NOT qualify as shooting star (upper wick not long enough). Standard red bar with mild rejection.

### Live-chart language doctrine (NEW 2026-05-07)

When describing the chart to J in real-time chat, ALWAYS use candlestick-pattern names when applicable. Examples:
- "12:30 bar printed a near-marubozu bearish — body 76% of range, sellers controlled the close"
- "11:40 wicked above 735.40 then reversed — small rejection wick, not a full shooting star"
- "Bullish engulfing forming at 730 if next bar's body covers the 12:00 red bar"
- "Doji at 733 — indecision, wait for the next bar's direction"

J reads the chart in candlestick language. Gamma matches that language. Don't say "red bar with above-avg volume" when "near-marubozu bearish" is more precise. Don't say "long lower wick + green follow-through" when "hammer" is the word.

### `htf_15m_alignment`
- Bullish 5m entry needs `htf_15m.ribbon.stack != "BEAR"` (mixed or BULL OK)
- Bearish 5m entry needs `htf_15m.ribbon.stack != "BULL"` (mixed or BEAR OK)
- `mixed` = the three EMAs are not strictly ordered (Fast > Pivot > Slow OR Fast < Pivot < Slow)

### `iv_regime` (recorded once per session at premarket)
Bands by VIX-at-open as a stand-in until P2 wires direct ATM IV30:
- `LOW`   ⟺ VIX < 15.00
- `MID`   ⟺ 15.00 ≤ VIX ≤ 22.00
- `HIGH`  ⟺ VIX > 22.00

The regime is stored in `today-bias.iv_regime` and tagged onto every `current-position.json` write. It is **not** itself a filter today; it's an attribute used at EOD/Sunday review for per-regime expectancy.

---

## Volume as a validity filter (learned 2026-05-05)

Volume is a required confirmation layer — not just a nice-to-have. Observed in session:

### Volume divergence = setup invalidated

On 2026-05-05, a breakdown bar (1:05 PM ET, close 723.24, vol 20,519) was immediately followed by a recovery bar (1:15 PM ET, close 723.57, vol 42,072) — more than 2× the breakdown volume. The bounce out-volumed the breakdown. The bearish setup was dead before the ribbon even had a chance to flip.

**Rule:** If the bar immediately following a breakdown bar closes UP and has volume ≥ breakdown bar volume → the breakdown has failed. Do not enter puts. Wait for reset.

**Why:** Volume on the recovery bar reflects buyer conviction. If buyers show up harder than sellers did, the sellers don't control price.

### Volume on the breakdown bar must exceed recent context

For BEARISH_REJECTION_RIDE_THE_RIBBON to be valid:
- Breakdown bar volume should be **≥ 1.3× the 5-bar average** preceding it
- If breakdown volume is below-average or immediately overwhelmed by a higher-volume recovery bar → setup is not confirmed

### Chop recognition via volume

When volume is low and consistent across both up and down bars (no clear surge in either direction), the market is in equilibrium/range. Do not enter directional plays in this environment. Signs of chop:
- Volume staying flat 15K–25K per bar with no outliers
- Price oscillating through the ribbon without commitment
- Ribbon spread < 30 cents (EMAs too compressed to give clean direction)

Wait for a breakout bar — a candle where volume **meaningfully exceeds** the recent average AND closes decisively on one side of the ribbon.

---

## Price wick through ribbon ≠ ribbon flip (learned 2026-05-05)

A single candle wick below (or above) the ribbon does NOT constitute a ribbon flip. The ribbon EMAs are moving averages — a single bar's low only marginally moves the EMA calculation. 

**What actually flips the ribbon:** Sustained price pressure over 2–4 bars below the Fast EMA, causing the Fast EMA to drop toward and then below the Pivot EMA. The reordering of EMA lines is the flip — not price piercing through them on a wick.

**Practical implication:** On the 1:05 PM ET bar (2026-05-05), price wicked to 723.12 (below Slow EMA at 723.15) but the EMAs remained Fast(723.44) > Pivot(723.36) > Slow(723.18) — fully bullish-stacked. The ribbon was never bearish. Entering puts on that wick would have violated the context filter requiring a bearish ribbon.

---

## What's different across the three (and why it matters)

| Variable | 4/29 | 5/1 | 5/4 |
|---|---|---|---|
| Entry timing relative to trigger | Coincident with rejection ✅ | 27 min EARLY (anticipation) ❌ | Coincident with rejection ✅ |
| Management quality | Compromised (working) | Conservative (defined-level exit) | Clean (full ribbon ride) |
| Time of day for entry | 10:25 ET (mid-morning) | 13:09 ET (early afternoon) | 10:27 ET (mid-morning) |
| Days into a trend | ~3+ days down | Day 1 of intraday reversal | Day 4 of multi-day trend |
| Result | +34% | +72% | +86% |

**The pattern:** %-return tracks management quality more than entry quality. All three had legitimate setups. The variance in outcomes traces almost entirely to whether J could ride the ribbon correctly. **Gamma's main job in automation is to remove the management variance.**

---

## How Gamma encodes this (the heartbeat translation)

For the polling-based heartbeat to fire on this setup, it needs to detect — programmatically — what J detects visually. Here's the translation:

### Detect "ribbon bearish-stacked"
- Pull the EMA values for each ribbon constituent (5, 8, 13, 21, 34 — actual values TBD when we inspect the indicator).
- Bearish-stacked = `EMA5 < EMA8 < EMA13 < EMA21 < EMA34` AND price below all of them.
- Bullish-stacked = the inverse.
- Transitioning = neither — values are interleaved.

### Detect "rejection candle at level"
- Define "level" = any horizontal in `today-bias.json.key_levels` within ±0.30 of current price.
- Rejection candle = the last closed 3-min candle has `high > level` AND `close < level`.

### Detect "yellow ▼ sell triangle printed"
- The TradingView MCP either exposes the indicator's plot data directly (preferred) or we read pixel signals (less robust). On install, we figure out which.
- If neither: the heartbeat synthesizes its own version — `last_close < EMA5 AND prior_close > EMA5` — which approximates a ribbon-break signal.

### Detect "Death Cross / Golden Cross"
- Read the underlying MA cross from the indicator's data. Probably 9 EMA crossing 21 EMA.
- Useful for *confirmation* logging; not used as primary trigger (lagging).

### Detect "bearish breakdown candle with volume"
- Last closed candle: `close < open` AND `(high - close) > 0.6 × (high - low)` (= big body, small upper wick) AND `volume > average_volume_last_20_candles × 1.5`.

### Detect "bounce signature (exit signal)"
- Last closed candle: long lower wick (`(low - close) > 0.6 × (close - open)` if green, or significant lower tail).
- AND ribbon starts narrowing (recent EMAs converging).
- AND a Cyan ▲ buy triangle within ±2 candles.

When ≥2 of the entry-side criteria fire on a single tick AND the context filters from `playbook.md` are satisfied → trigger fires → trade enters.

When ≥1 of the exit-side criteria fires on a tick AND a position is open → exit fires.

---

## What this anatomy doc is FOR

- **For J:** an articulation of the chart-reading you've been doing intuitively. When the setup is forming again, you can compare to this and self-check.
- **For Gamma:** the source of truth for what to detect. The heartbeat's `decision-log.md` decision tree references the criteria above; if we tune the encoding, this doc updates.
- **For the playbook:** when we add the bullish mirror setup later, we have a template — write it as the inverse of every signal here.

When we install the TradingView MCP and get our hands on the actual indicator data, this doc gets revised with the *real* indicator names and parameters. Right now it's the model based on visual interpretation of the screenshots.
