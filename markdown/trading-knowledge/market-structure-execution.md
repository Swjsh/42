# MARKET-STRUCTURE & EXECUTION — how professionals read price structure

> **Companion to [`GENERATIVE-LENS.md`](GENERATIVE-LENS.md).** This is the "market-structure levers" base the lens tells you to read at session start. When a signal reads weak *standalone*, the fix is almost never "kill it" — it's "layer it into a confluence read" (level + multi-TF + volume + VWAP + regime). This doc is the menu of lenses you layer.
>
> **Why this matters to Gamma specifically:** J's one verified edge is **multi-day horizontal levels + role-flips** (WeBull fresh-eyes 2026-07-01: 59.2% direction when trading *at a PD-level, aligned, midday*). Everything below deepens the mechanism *underneath* that edge — so the engine can grade a level's quality, not just its price. Each section ends with a lever you can turn into an engine input.
>
> **Evidence discipline (per the lens + OP-33):** every section flags where the evidence is **STRONG** (academic / order-book-mechanical), **MODERATE** (widely-practiced, partially studied), or **FOLKLORE** (plausible, popular, unproven). Do not let a folklore lever earn a HIGH-urgency ratification without its own A/B.

---

## 0. The one idea underneath all of it: markets are a two-way auction

Everything in this doc is a corollary of **auction market theory**: a market is a continuous two-way auction where buyers and sellers negotiate value by accepting or rejecting proposed prices. Price *advertises* opportunity; **time** regulates it (the longer price stays at a level, the more "accepted" that price is); **volume** measures how much business actually got done there. This framework was formalized by **J. Peter Steidlmayer at the Chicago Board of Trade in the early 1980s** as *Market Profile*.[^mp-wiki][^topstep]

The single most useful consequence: **price spends most of its time at "fair value" (where lots of business happens) and moves fast through prices the auction rejects (where little business happens).** Support/resistance, volume nodes, VWAP, and the value area are all different instruments measuring the *same* thing — where the auction found agreement vs. where it did not. That is why they cluster and confirm each other. Confluence is not magic; it is several lenses pointed at one underlying fact.

- **Balance** = two-sided auction, price rotates inside a range (mean-reversion regime). 
- **Imbalance** = one-sided auction, price trends / discovers a new level (breakout regime).

> **Lever:** classify each session as *balance* vs *imbalance* first. The correct playbook (fade the edges vs ride the break) is opposite in each. A level-reject setup that's +EV in balance is a *loser* in imbalance — this is the C20/C22 family of lessons (proximity gates anti-correlate with breakout setups).

---

## 1. Support / Resistance & the ROLE-FLIP (the exact thing J trades)

### 1.1 What a level *is* and why it forms

Formal definition (CFA curriculum): **support** is "a low price range in which further decline in price can be averted by some buying activity"; **resistance** is "a price range in which further increase in price can be averted by some selling activity."[^cfa] Note the word **range** — a level is a *zone*, not a single tick. Treating it as an infinitely thin line is the #1 beginner error; professionals draw a band.

A level forms because **resting orders and memory cluster at a price**:
1. **Order clustering** — traders place limit buys, stop-losses, and take-profits at *specific memorable prices*, disproportionately round numbers (prices ending in 0 and 5). This is not folklore; it is measured (see §1.3).
2. **Memory / anchoring** — a price that recently reversed becomes a reference everyone watches. The more times it's tested and the more volume transacted there, the more orders accumulate on the next approach — a self-reinforcing focal point.
3. **Prior value** — old highs/lows, prior-day high/low/close (PDH/PDL/PDC), overnight range, and the open are structural reference prices that institutions benchmark against, so orders pool there.

### 1.2 The ROLE-FLIP (principle of polarity) — the core mechanism

**Once a support level is decisively broken, it tends to act as resistance; once a resistance level is broken, it tends to act as support.**[^cfa][^bajaj][^allstar] The CFA curriculum states it flatly: "once breached, a support level becomes a resistance level. Similarly, resistance levels become support levels upon a breach."[^cfa] This is often called the single most widely-applicable principle in technical analysis — some traders trade essentially nothing else.[^tt]

**The mechanism (this is what makes it *real*, not just a pattern):**
- When **support breaks**, everyone who bought at that level is now underwater. When price rallies back to the old support, those trapped longs sell **to get out at breakeven** — that supply turns former support into new resistance.[^bajaj][^learnapp]
- Symmetrically, when **resistance breaks**, price pulls back to it. Traders who missed the breakout now buy the retest; shorts who sold the old ceiling cover; and the "breakeven" crowd from the other side is gone. That demand turns former resistance into new support.[^bajaj][^allstar]
- **Volume validates the flip.** Higher volume on the break and lower volume on the retest strengthens the role reversal — it means the level was genuinely rejected/accepted, not a random poke.[^bajaj]

> This is the **break-and-retest** — arguably the highest-probability structural entry in intraday trading, and it *is* J's edge. The retest of a flipped level, in the direction of the break, with an aligned higher timeframe, is the confluence bullseye.

**Worked SPY example (the flip J trades).** Say SPY has rejected **$740.00** three times over two days — a resistance shelf (round number → dense orders → §1.3). Sellers there are defending; buyers who tried and failed are trapped-long fuel.
- **The break:** SPY pushes *through* 740 on a wide, high-volume 15m candle that *closes* above (e.g. 740.60). The shorts who sold 740 are now underwater; the failed-breakout buyers are finally right. Resistance is broken.
- **The flip / retest (the entry):** price pulls back to ~740. Now: shorts cover *at* 740 (they want out at breakeven → buying), pullback-buyers who missed the break add *at* 740 (buying), and the old ceiling-sellers are gone. **Former resistance is now support.** A bullish reclaim/hold of 740 on the retest = the ENTER_BULL / BULLISH_RECLAIM setup. Stop goes *below* the flipped level (if 740 fails to hold as support, the flip is invalidated — clean, mechanical invalidation).
- **Why it's a good option trade specifically:** the flip gives a *tight, defined* stop (just under 740) and an *aligned* directional thesis, which is exactly what a 0DTE/short-dated call needs to overcome theta — small stop distance = small premium risk, directional conviction = the move that pays. A vague "it looks bullish" entry with a 3-point stop bleeds theta; a 740-reclaim with a 0.40 stop does not.

This one example threads every lens in this doc: round-number level (§1.3) → break-and-retest flip (§1.2) → confirmed if 740 is also a higher-TF level (§2) and an HVN/PD-POC (§3) and price is above VWAP (§4), in a trending (imbalance) regime (§0), taken midday not at 09:31 (§5.3). That stack IS the confluence read of §6.

### 1.3 Evidence: **STRONG** for horizontal levels & round numbers

This is the section that separates J's edge from folklore. **Carol Osler (Federal Reserve / Brandeis) got the actual order books** of a large FX dealer (NatWest) and showed *why* support/resistance works, mechanically:[^osler-web]
- Stop-loss and take-profit orders **cluster at round numbers** (rates ending in 0 and 5), consistent with limit-order clustering documented in stock markets.
- **Take-profit orders cluster → price reverses at round numbers** (support/resistance holds). Take-profits are limit orders that *provide* liquidity against the trend, so they absorb momentum and turn price.
- **Stop-loss orders cluster just past round numbers → price moves fast once a level breaks** (the "trends are unusually rapid after crossing a level" prediction). Stops are market orders that *consume* liquidity in the direction of the break, so a broken level cascades.

So the two classic technical claims — *"levels hold"* and *"breaks run"* — both fall out of the **actual distribution of resting orders.** This is about as strong as evidence in technical analysis gets: it's not curve-fit backtest, it's the order book itself. **Horizontal levels and round numbers are the strongest-evidenced structural tool in this document.**

> **Lever for the engine:** a level's *quality* should scale with (a) round-number-ness, (b) touch count with *decreasing* volume per touch (accumulating orders, not chop), (c) volume transacted at the level (§3), and (d) whether it's a flipped level being retested. Grade the level, don't just detect its price. **Caution (C25):** touch_count is double-edged — high touch count drives both "strong level" *and* eventual break (each touch consumes the resting orders). Validate the direction of any touch-count feature per-setup before trusting it.

---

## 2. Multi-timeframe analysis — why higher-TF levels dominate

### 2.1 The rule

**Higher-timeframe levels are "stronger" than lower-timeframe levels**, and traders analyze **top-down**: higher TF for the dominant trend/context, medium TF for the setup, lower TF for precise entry.[^tradeciety][^litefinance-mtf]

Why "stronger" is real and not just a saying:
- A level visible on the **1h/4h/daily** has been agreed on by traders across *all* shorter horizons too — more participants, more accumulated orders, bigger supply/demand imbalance defending it.[^tradefundrr]
- A 5m level is often just intraday noise — an artifact of the last hour's chop that no large participant is watching. It has thin order backing, so it breaks easily.
- Higher-TF structure **contextualizes** the lower TF: a 5m long into a 1h resistance is fighting the bigger auction; the same 5m long *off* a 1h support is aligned with it.

### 2.2 Confluence — the multiplier

**Confluence** = independent signals pointing at the *same price zone*. When a 5m level, a 15m level, and a 1h level stack at the same price, that price is a **confluence zone** — many participants across horizons are all watching it, so orders concentrate there.[^tradefundrr][^xs-confluence]

> **Evidence: MODERATE, and be skeptical of the numbers.** Educator sources claim multi-TF confluence lifts win rates by "20–30%" or "40–50%."[^tradeciety][^tradefundrr] **Treat those figures as marketing, not measured** — they're uncited, and every strategy article claims a similar boost. What *is* well-founded is the *directional* claim (align with the higher TF, don't fight it) and the *mechanism* (more participants = more orders = firmer level). The magnitude is folklore; the direction is sound.

> **Lever for the engine:** score a level by **how many timeframes independently place a level within a tolerance band of it** (TF-confluence count), and weight the higher TFs more. J's edge is *multi-day* levels precisely because the daily/weekly horizon has the deepest order backing. A level confirmed on 1h + daily + a PD-level should outrank a 5m-only level by a wide margin — this is directly encodeable as a level-quality feature. Also: **only enter aligned with the higher-TF trend** (the WeBull "aligned" filter that lifted J's WR).

---

## 3. Volume Profile / volume-by-price — is J's "volume shelf" intuition real?

### 3.1 The instruments (exact definitions)

Volume Profile plots **volume traded at each price** (a horizontal histogram), vs. a normal chart's volume-over-time. TradingView's canonical definitions:[^tv-vp]
- **Point of Control (POC):** "the price level for the time period with the **highest traded volume**." The single most-transacted price = the auction's center of gravity / fair value.[^tv-vp][^alchemy]
- **Value Area (VA):** "the range of price levels in which the specified percentage of all volume was traded" — **default 70%**.[^tv-vp] (This 70% ≈ one standard deviation is the Market-Profile convention.[^topstep])
- **Value Area High (VAH) / Value Area Low (VAL):** the top and bottom of that 70% range.[^tv-vp] Computed by starting at the POC and alternately adding the higher-volume adjacent row until 70% is captured.[^tv-vp]
- **High-Volume Node (HVN):** a *peak* in the profile — a price where lots of business got done. **Consolidation / acceptance / fair-value zone.**[^orderflow][^tv-vp]
- **Low-Volume Node (LVN):** a *valley* — a price the auction passed through quickly with little two-sided trade. **Rejection zone.**[^orderflow][^tv-vp]

### 3.2 Why HVNs act as support/resistance — J's "volume shelf" intuition IS real (mechanistically)

Yes, the intuition holds up. **HVNs act as stronger support/resistance because heavy prior trading = many participants with positions and memory at that price = thick resting-order backing on re-approach.**[^angelone][^orderflow] Concretely:
- At an HVN, huge inventory changed hands. Longs and shorts from that shelf both have unfinished business (add, defend, exit at breakeven) → dense two-sided orders → price *sticks* and reverses there. It takes real effort to break an HVN, so price usually retraces from it.[^angelone]
- **LVNs are the opposite and equally useful:** little business was done, so there's nothing to defend. Price moves *fast* through an LVN — LVNs are where breakouts accelerate, and they make clean **stop-loss placement / breakout-target** zones (put the stop *past* the LVN; expect quick travel *through* it).[^orderflow][^luxalgo]
- **POC as a magnet:** because it's the fairest price, price that leaves the POC has a statistical tendency to **return** to it — the basis of value-area mean-reversion trades.[^alchemy][^quantvps]

Notice this is the **same order-clustering mechanism as §1.3**, just measured by volume instead of by round-number. A round-number level *and* an HVN at the same price is a genuine double confirmation — two independent lenses on "orders are dense here."

**Worked SPY example (reading yesterday's profile before today's open).** Suppose the prior day's SPY volume profile came out:
- **PD-POC = 738.50** (fairest price, most volume) — today, expect price to gravitate toward and stall near 738.50.
- **PD-VAH = 740.20, PD-VAL = 736.10** (the 70% value area) — today's open *relative* to this range sets the day-type: open **above** VAH and hold = acceptance higher, bullish; open **inside** the value area = likely balance/rotation between VAL and VAH; open **below** VAL and reject back in = failed auction, often a fade.
- **LVN at 741.00** (a volume valley just above VAH) — if price breaks 740.20 and tags 741, expect it to travel *fast* through 741 (nothing to defend) — good breakout-continuation zone, bad place to fade, and the natural spot to *place a stop just beyond* (741.20) because price shouldn't linger there.
- **HVN at 738.50 (=POC) and another at 736.50** — these are the day's likely "sticky" reaction shelves; a horizontal level of J's that coincides with one of these gets a quality up-weight.

That single profile read gives you the day's map — magnet (POC), fade-edges (VAH/VAL in balance), fast-lanes and stop-homes (LVNs), and sticky shelves (HVNs) — *before the bell.* It's the volume-based twin of drawing horizontal levels at premarket.

### 3.3 Evidence: **MODERATE-to-STRONG mechanism, WEAK-to-FOLKLORE for precise rules**

- **Strong:** the *mechanism* (volume = transacted inventory = order density = stickiness) is sound and shares Osler's order-clustering backbone. HVN-is-sticky / LVN-is-fast is real market microstructure, not astrology.
- **Weak/folklore:** the *specific tradeable rules* ("70% value area," "fade the VAH," "POC always gets retested by X%") are conventions, not laws. The 70% is an arbitrary (if reasonable) cutoff. Value-area-rotation win-rate claims in educator blogs are uncited. And a subtle trap: **for 0DTE SPY intraday, a single-session volume profile has very little data** — the HVN/POC can be noise until midday. Anchor the profile to a *meaningful* period (prior day, prior week, or a specific move), not an arbitrary lookback.

> **Lever for the engine:** compute a **prior-day (and prior-week) volume profile**; treat PD-POC, PD-VAH, PD-VAL as first-class levels alongside J's horizontal levels — and **up-weight any horizontal level that coincides with an HVN** (double confirmation). Use **LVNs to place stops and set breakout travel targets** (expect fast movement across them). This is a concrete, testable upgrade to the level feed. **Validate per direction (C20/C25):** volume-node features may anti-correlate with breakout setups — A/B before trusting.

---

## 4. VWAP & anchored VWAP — the institutional reference line

### 4.1 What VWAP is and why institutions live on it

**VWAP = Volume-Weighted Average Price** — the average price weighted by volume over the session (resets each day). It is *the* institutional execution benchmark: **a buy filled *below* the day's VWAP is a good fill; above it is a bad fill.**[^valoralgo] Institutions can't dump a million shares at once (they'd move the market against themselves — slippage), so **VWAP algorithms slice the parent order into child orders spread across the day**, weighted to the typical intraday volume curve, aiming to average out near VWAP.[^valoralgo][^litefinance-vwap] By one 2020 ITG estimate, ~**$8.7B/day** of US equity volume executes via VWAP algos — the single most influential benchmark in equities.[^valoralgo]

**Why that makes VWAP act as dynamic support/resistance:** because the big players are *systematically* trying to buy under it and sell over it, VWAP becomes a self-fulfilling magnet and pivot. In a trend, VWAP is a **dynamic separator between bullish and bearish** — trend-followers buy pullbacks *to* VWAP; above VWAP = bulls in control, below = bears.[^cmc][^trendspider-vwap] The most-watched intraday timeframe for VWAP is the **5-minute chart**.[^tradervue]

### 4.2 Anchored VWAP (AVWAP) — VWAP from an event, not the session open

**Anchored VWAP** starts the volume-weighting from a *specific bar you choose* rather than the session open — anchor it to a **swing high/low, a breakout bar, earnings, or a major-news candle.**[^trader-dale][^tradingsim-avwap] It answers "what's the average price of everyone who's traded *since that event*?" — i.e., the level at which the participants who came in on that move are collectively breakeven.[^trader-dale] Cross back below the AVWAP-from-the-low and that whole cohort is now underwater (same trapped-trader mechanic as the role-flip in §1.2).

### 4.3 Evidence: **MODERATE**, and honest about it

- **Strong / mechanical:** VWAP-as-benchmark is a *documented institutional fact* — the order flow around it is real, not a chart artifact. That's the firm ground.
- **Moderate / folklore-adjacent:** "price respects VWAP as support/resistance" is *partly self-fulfilling* and *partly narrative.* It works best on **liquid, high-volume, institutionally-traded instruments** — which SPY is (ideal case). It works *worst* on thin names and *late in the day* when the average is anchored to stale morning volume. AVWAP anchor choice is discretionary and easy to cherry-pick after the fact — the classic "I found the anchor that fits" overfit.

> **Lever for the engine:** SPY is the *perfect* VWAP instrument (deep institutional flow). Add **session VWAP and an AVWAP anchored to the day's first significant swing / the prior-day close** as dynamic levels; grade an entry higher when it's a level-reclaim *on the correct side of VWAP* (aligned with the institutional tide) and lower when it fights VWAP. This is cheap to compute and directly complements J's horizontal-level edge with a *dynamic* reference.

---

## 5. Order flow / microstructure — why levels are where orders cluster

This is the ground floor: the actual **limit order book (LOB)** — the live list of resting buy (bid) and sell (ask) limit orders at each price. Everything above is a summary of what the book does.

### 5.1 The primitives[^bookmap][^aori][^equiti-of]

- **Bid / Ask / Spread:** best bid = highest price a buyer will pay; best ask = lowest a seller will accept; **spread** = ask − bid = the immediate cost of demanding liquidity (crossing to trade *now*). Narrow spread = liquid, cheap to trade; wide spread = illiquid, expensive.[^bookmap]
- **Two order types, opposite roles:** **limit orders *supply* liquidity** (rest in the book, wait); **market orders *consume* liquidity** (hit resting orders, execute now). Price moves when market orders eat through the resting limits at a price and reach the next level.[^aori]
- **Depth / liquidity:** how much resting size sits at and near the touch. Thick depth = a price is hard to move (support/resistance); thin depth = price slips through fast (this is the LVN of §3, seen live).
- **Absorption:** when a wall of **limit** orders soaks up aggressive **market** orders *without price moving* — a big passive player is defending a price. Absorption at a level is a strong tell the level will hold; failure of absorption (the wall gets eaten) precedes the break.[^equiti-of]
- **Order-flow imbalance:** more aggressive buying than selling → price ticks up to attract sellers, and vice-versa. Short-horizon imbalance has *documented* predictive power for the next price move.[^equiti-of]

**What you can and can't infer from bars alone (Gamma's actual constraint).** Gamma sees OHLCV bars, not the live book — so absorption and depth must be *inferred*, and the inference is imperfect. The usable bar-proxies:
- **High volume + small range (a "doji"/narrow bar on a volume spike) at a level = probable absorption.** Lots traded, price didn't move → a passive player is soaking it up → the level is likely defended. This is the closest a bar gives you to seeing a wall.
- **Long wick rejecting a level = market orders hit resting liquidity and got pushed back** — a real-time role-of-the-level tell (long lower wick at support = buyers absorbed sellers).
- **Wide-range bar on high volume *through* a price = the opposite of absorption** — the resting liquidity got consumed (this is a level *breaking*, or an LVN traversal).
- **Low volume on a test = weak defense** — few orders there; more likely to break than a high-volume test.

Do not over-read these — a bar-proxy is a blurry photo of the book, not the book. Flag inferred order-flow reads as *inferred* (OP-33).

### 5.2 The synthesis: **levels ARE order clusters**

This closes the loop on the whole document: **a support/resistance level is, physically, a price where resting limit orders are dense.** Round numbers (§1.3), HVNs (§3), VWAP (§4), and prior-day levels are all *proxies* for "the book is thick here." That's *why* they coincide and confirm — they're four different ways of locating the same resting-order clusters. When they stack, the book really is thick there; when only one fires, it might be noise.

> **Closing the access gap is a research program of its own:** [`microstructure-informed-flow.md`](microstructure-informed-flow.md) — how to get trades/MBO data on the futures lane at ~$0 and the ranked hypotheses (H6 first: calibrate *this section's* bar-absorption proxy against real absorption).
>
> **Evidence: STRONG for the microstructure facts** (LOB mechanics, spread-as-cost, imbalance prediction are core market-microstructure, heavily studied[^equiti-of]). **But NOTE the access gap:** Gamma reads *bars* (OHLCV) and TradingView levels, **not** the live SPY/options order book. So the engine can't see absorption or depth directly — it must **infer** order density from the proxies (round numbers, volume nodes, VWAP, prior-day structure, and *volume + range on the bar*). Bar volume and candle wicks are your low-resolution window into the book. Don't claim order-flow reads you can't actually see (OP-33: verify, don't claim).

### 5.3 The opening range

The **opening range** (typically the first 5/15/30 min) is the session's first battle for value — the initial balance. Its high and low become reference levels the rest of the day trades around; a break of the opening range (**ORB**) is a classic momentum trigger.[^tradealgo-orb] Narrow opening ranges are claimed to precede trend days more often than wide ones.[^quantstrat-orb]

> **Evidence: MIXED — and this is the honest one to internalize.** ORB is *real structure* (the open genuinely sets reference levels), but ORB *as a mechanical strategy* has **contradictory backtests** and a **documented decline over time as it got popular** — a recent futures study found ORB variants on MNQ **all failed statistical tests**.[^quantstrat-orb][^arxiv-mnq] Educator win-rate claims (56%, 68% trend days) are uncited and the ORB search space is large enough that **luck alone produces impressive backtests.**[^quantstrat-orb] Use the opening range as a *reference level* in confluence (strong); be *deeply* skeptical of naked ORB as an edge (weak, and directly relevant — this is exactly the "beats-random-but-loses" trap the lens warns about).

> **Lever:** treat opening-range H/L as levels feeding §1's role-flip machinery, **not** as a standalone signal. The 09:35 entry gate already respects that the open is noisy.

---

## 6. How it COMBINES — the multi-lens confluence read (the engine J wants)

The whole point. Each lens above is one measurement of the same underlying thing (**where the auction found agreement = where orders are dense**). A professional doesn't trade one lens — they stack them and trade only where they **agree**. Confluence isn't additive magic; it's **error-cancellation** — each lens has noise, and the price where several independent-ish lenses agree is where the signal survives.

### The confluence scorecard (what to actually compute per candidate level)

| Lens | The question it answers | Strong/weak | Engine feature |
|---|---|---|---|
| **Horizontal level** (§1) | Is this a memory/round-number price with dense orders? | **STRONG** | round-number score, touch pattern, PD-levels |
| **Role-flip** (§1.2) | Is this a *broken* level being retested in the break direction? | **STRONG** | flip-flag + break-volume/retest-volume |
| **Multi-TF** (§2) | Do several timeframes independently mark this price? | MODERATE (dir. sound, magnitude folklore) | TF-confluence count, HT-trend alignment |
| **Volume node** (§3) | Did lots of business happen here (HVN) or none (LVN)? | MODERATE-STRONG mechanism | PD-POC/VAH/VAL, HVN-coincidence, LVN-for-stops |
| **VWAP / AVWAP** (§4) | Is entry on the institutional side of fair value? | MODERATE (SPY = ideal) | side-of-VWAP flag, AVWAP-from-swing |
| **Order-flow proxy** (§5) | Is the book thick here (inferred from vol/range)? | STRONG facts, but INFERRED only | bar-volume, wick/absorption proxy |
| **Regime** (§0) | Balance (fade) or imbalance (ride)? | MODERATE | trend/chop, VIX character, time-of-day |

**The read:** a HIGH-conviction entry is one price zone where **a flipped horizontal level (§1.2) + a higher-TF level (§2) + an HVN or PD-POC (§3) + the correct side of VWAP (§4)** all coincide, in the **right regime (§0)**, at a **non-toxic time of day.** That is not four separate edges — it's four confirmations that *the book is thick and the auction agrees here.* This is precisely J's verified kernel (at a PD-level, aligned, midday) expressed as a scoreable stack.

### Worked confluence read — grading two candidate entries at 11:40 ET

Same instrument (SPY), same day, two possible longs. Score each across the scorecard:

**Candidate A — a 740 reclaim (the bullseye):**
| Lens | Reading | Score |
|---|---|---|
| Horizontal level | 740 = round number, 3× tested resistance, now broken | ✓✓ |
| Role-flip | broke 740 on volume, pulling back to retest as support | ✓✓ |
| Multi-TF | 740 also a 1h swing high + prior-day VAH | ✓ |
| Volume node | 740 sits on yesterday's HVN | ✓ |
| VWAP | price above session VWAP, VWAP rising | ✓ |
| Regime | trend day (imbalance), higher-TF up | ✓ |
| Time | 11:40 — midday, past the toxic 09:30–10:00 window | ✓ |
→ **Every lens agrees.** This is the take. Tight stop under 740, aligned direction — the option trade the engine exists to catch.

**Candidate B — a 736 bounce (the trap):**
| Lens | Reading | Score |
|---|---|---|
| Horizontal level | 736 = a 5m level from this morning's chop only | ✗ (thin) |
| Role-flip | never broke anything — just a pullback low | ✗ |
| Multi-TF | invisible on 15m+ | ✗ |
| Volume node | 736 is in an LVN (fast-travel zone) — price *won't* hold here | ✗✗ |
| VWAP | 736 is *below* VWAP — fighting the institutional tide | ✗ |
| Regime | counter to higher-TF trend | ✗ |
| Time | fine (11:40), but everything else fails | – |
→ **Only "time" passes.** This is a single-lens signal in an LVN, below VWAP, counter-trend. Standalone it might read as a "bounce," but the confluence stack says **skip** — exactly the junk the grading is meant to reject.

The difference between A and B is *not* which one "looks bullish on the 5m" — both do. It's that A is where the book is thick and the auction agrees, and B is a low-volume air-pocket against the tide. **That discrimination is the entire product of the multi-lens engine.**

> **Do NOT** average the lenses into one mush and lose which one fired — trace the cascade (C15: gates interact multiplicatively). Log *which* lenses agreed on each entry, so the post-trade review can learn *which confluence combinations* actually paid — the data flywheel (OP-11).

---

## 7. How to use this to GENERATE ideas (the lens in action)

When a signal reads weak or an edge looks "dead," this doc is a lever menu, not a eulogy. Run the taxonomy:

1. **"Signal X has no lift standalone."** → Almost never a kill. **Layer it** (§6): does X + HT-level + VWAP-side + HVN, in-regime, midday, have lift? A raw single lens *should* read as noise (C25/C27) — that's expected, not disqualifying. **The untested axis is confluence.**
2. **"Levels don't work / random."** → Which levels? Grade them (§1.3, §3.2): round-number-ness, HVN-coincidence, TF-confluence, flip-status. An *ungraded* level pool is a mix of strong and junk levels; the edge is in the *grading*, and that axis is usually untested.
3. **"We already trade levels, what's next?"** → The untested levers are the *dynamic* and *volume* lenses: add **AVWAP**, **prior-day volume profile (POC/VAH/VAL)**, **LVN-based stops**, **TF-confluence scoring**. Each is a concrete, cheap, A/B-able upgrade to the existing level feed — not a new strategy, a *better level*.
4. **"Setup loses in a regime."** → Split by balance/imbalance (§0) and time-of-day. J's own data says 09:30–10:00 was his *toxic* window; midday-at-a-level was the edge. Regime-conditioning is a lever, not a kill.
5. **Break-and-retest is the bullseye.** If you're hunting a new *structural* setup, the retest of a **flipped, higher-TF, HVN-backed** level on the correct side of VWAP is the theoretically-strongest and evidence-backed one — and it's J's edge. Deepen *that* before chasing exotic patterns.

### The session workflow this implies (top-down, every day)

1. **Premarket — build the map (context, no trades):** mark prior-day H/L/C, overnight range, round numbers near price; pull the **prior-day + prior-week volume profile** (POC / VAH / VAL / HVNs / LVNs); note the higher-TF (daily/1h) trend and nearest daily levels. Where do round numbers, HVNs, PD-levels, and HT-levels *stack*? Those confluence prices are the day's watch-list.
2. **Open — read the day-type (§0, §5.3):** open above/inside/below yesterday's value area? Balance or imbalance? Wide or narrow opening range? This picks the playbook (fade edges vs ride breaks). Do not trade the first 5 min — the open is noise (09:35 gate).
3. **Intraday — wait for price to reach a *graded* level and confirm:** only act at a watch-list confluence zone (not a fresh 5m level in an air-pocket). At the level, want: role-flip retest (§1.2), correct side of VWAP (§4), a bar-proxy tell of absorption/rejection (§5.1), non-toxic time-of-day.
4. **Entry & stop:** enter on the confirmation (reclaim/hold or wick-rejection); stop goes just *past* the level / beyond the nearest LVN — tight and mechanical, which is what makes the option trade survive theta.
5. **Post-trade — feed the flywheel:** log *which lenses agreed*, so the review learns which confluence combinations actually pay (OP-11). A level that failed teaches which grade-feature was wrong.

---

## 8. Honest evidence ledger (strong vs folklore, at a glance)

| Claim | Verdict | Why |
|---|---|---|
| Horizontal levels & **round numbers** hold, breaks run | **STRONG** | Osler got the actual FX order books: take-profit clustering → reversals; stop clustering → fast breaks.[^osler-web] Order-book-mechanical, not curve-fit. |
| **Role-flip / polarity** (S↔R after break) | **STRONG (mechanism)** | Trapped-trader breakeven-selling is a real, documented psychological+order mechanic; in CFA curriculum.[^cfa][^bajaj] Exact hit-rate unquantified. |
| **HVN = sticky, LVN = fast, POC = magnet** | **MODERATE-STRONG (mechanism)** | Same order-density backbone as levels; microstructurally sound.[^angelone][^orderflow] But precise rules (70% VA, fade-the-VAH) are conventions, and single-session 0DTE profiles are data-poor. |
| **VWAP as institutional S/R** | **MODERATE** | VWAP-as-benchmark is a documented institutional fact (~$8.7B/day).[^valoralgo] "Price respects it" is partly self-fulfilling; best on liquid names (SPY ✓), worst late-day. |
| **Higher-TF > lower-TF, confluence works** | **MODERATE** | *Direction* sound (more participants = more orders). *Magnitude* claims ("+40%") are uncited educator marketing.[^tradeciety][^tradefundrr] |
| **Order-book mechanics** (spread=cost, imbalance predicts) | **STRONG (facts)** | Core market microstructure.[^equiti-of] BUT Gamma can't see the live book — must infer from bar proxies. Don't claim reads you can't see. |
| **Opening-range breakout as a strategy** | **MIXED / WEAK** | ORB structure is real; ORB-as-edge has contradictory backtests, decayed over time, MNQ variants failed stat tests.[^quantstrat-orb][^arxiv-mnq] Reference level ✓, standalone edge ✗. |
| Multi-TF win-rate figures, value-area hit-rates, ORB 56%/68% | **FOLKLORE** | Uncited educator/marketing numbers. Use the mechanism; **A/B the magnitude yourself** before any HIGH-urgency ratification. |

**Bottom line for Gamma:** J's edge (multi-day horizontal levels + role-flips) sits on the **strongest-evidenced** ground in all of technical analysis — it's backed by the actual order book, not folklore. The generative move is not to find a *new* edge; it's to **grade J's levels better** (round-number + HVN + TF-confluence + VWAP-side + regime) so the engine takes the *good* ones and skips the junk. Every "lever for the engine" callout above is a concrete, cheap, A/B-able feature toward that.

---

## Sources

[^mp-wiki]: Market profile — Wikipedia. https://en.wikipedia.org/wiki/Market_profile
[^topstep]: Intro to auction market theory and market profile — Topstep. https://www.topstep.com/blog/intro-to-auction-market-theory-and-market-profile
[^cfa]: Trend, Support & Resistance Lines, Change in Polarity — AnalystPrep (CFA Level 1). https://analystprep.com/cfa-level-1-exam/portfolio-management/trend-support-resistance-lines-change-polarity/
[^bajaj]: Principle of Polarity in Technical Analysis — Bajaj Finserv. https://www.bajajfinserv.in/principle-of-polarity
[^allstar]: The Principle of Polarity: Supply & Demand 101 — All Star Charts. https://allstarcharts.com/principle-polarity-supply-demand-101/
[^learnapp]: What Is Change In Polarity In Technical Analysis? — LearnApp. https://blog.learnapp.com/trading/change-in-polarity-in-technical-analysis/
[^tt]: Change in Polarity Principle in Technical Analysis — Trading Tuitions. https://tradingtuitions.com/change-in-polarity-principle-in-technical-analysis/
[^osler-web]: Carol Osler, "Currency Orders and Exchange-Rate Dynamics: Explaining the Success of Technical Analysis" (SSRN 923370; Fed NY Staff Report) — findings on stop-loss/take-profit clustering at round numbers explaining support/resistance and post-break momentum. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=923370
[^tradeciety]: How To Perform A Multiple Time Frame Analysis — Tradeciety. https://tradeciety.com/how-to-perform-a-multiple-time-frame-analysis
[^tradefundrr]: Multiple Timeframe Confluence Trading — TradeFundrr. https://tradefundrr.com/multiple-timeframe-confluence-trading/
[^litefinance-mtf]: Technical Analysis Using Multiple Timeframes — LiteFinance. https://www.litefinance.org/blog/for-beginners/technical-analysis/multiple-time-frame-analysis/
[^xs-confluence]: Confluence in Trading: How to Combine Indicators — XS. https://www.xs.com/en/blog/confluence-in-trading/
[^tv-vp]: Volume profile indicators: basic concepts — TradingView. https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/
[^alchemy]: Volume Profile Effective Trading Guide — Alchemy Markets. https://alchemymarkets.com/education/indicators/volume-profile/
[^orderflow]: Volume Profile: A Trader's Guide to HVNs, LVNs, and Value — Orderflow Labs. https://orderflowlabs.com/blogs/theblog/volume-profile-guide
[^angelone]: What are High Volume Nodes (HVNs) in Trading? — Angel One. https://www.angelone.in/knowledge-center/online-share-trading/high-volume-nodes-hvn
[^luxalgo]: Stop-Loss Placement Using Volume Profile — LuxAlgo. https://www.luxalgo.com/blog/stop-loss-placement-using-volume-profile/
[^quantvps]: The Ultimate Guide to Value Area Trading Strategy — QuantVPS. https://www.quantvps.com/blog/value-area-trading-strategy-guide
[^valoralgo]: How Institutions Use VWAP: The Execution Benchmark Guide — ValorAlgo (cites ITG ~$8.7B/day VWAP-algo volume). https://www.valoralgo.com/blog/vwap-trading-doctrine-institutional-guide
[^litefinance-vwap]: What Is the VWAP Indicator and How to Use It — LiteFinance. https://www.litefinance.org/blog/for-beginners/best-technical-indicators/vwap-indicator-what-is-vwap-in-trading-and-how-to-use-it/
[^cmc]: What is VWAP in Trading? — CMC Markets. https://www.cmcmarkets.com/en/technical-analysis/what-is-vwap-in-trading
[^trendspider-vwap]: VWAP Indicator: A Comprehensive Guide — TrendSpider. https://trendspider.com/learning-center/vwap-indicator-a-comprehensive-guide-for-traders/
[^tradervue]: VWAP Indicator Guide — Tradervue. https://www.tradervue.com/blog/vwap-indicator
[^trader-dale]: Master Anchored VWAP: 3 Simple Strategies — Trader Dale. https://www.trader-dale.com/master-anchored-vwap-3-simple-strategies-for-smarter-trading/
[^tradingsim-avwap]: Anchored VWAP Strategy for Day Trading — TradingSim. https://www.tradingsim.com/blog/anchored-vwap-strategies
[^bookmap]: Inside The Market: Order Books — Bookmap. https://bookmap.com/blog/inside-the-market-order-books-and-what-youre-missing-out-on
[^aori]: The Microstructure of Markets: How Order Books Actually Work — Aori. https://www.aori.io/research/posts/how-orderbooks-work
[^equiti-of]: Market Microstructure And Order Flow — Equiti. https://www.equiti.com/sc-en/education/market-analysis/order-flow-and-market-microstructure/
[^tradealgo-orb]: Opening Range Breakout Strategy — TradeAlgo. https://www.tradealgo.com/trading-guides/day-trading/opening-range-breakout-strategy-how-to-trade-the-first-30-minutes
[^quantstrat-orb]: Opening Range Breakout Strategy (ORB): Backtest — QuantifiedStrategies. https://www.quantifiedstrategies.com/opening-range-breakout-strategy/
[^arxiv-mnq]: Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study — arXiv 2605.04004. https://arxiv.org/pdf/2605.04004
