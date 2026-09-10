# Intraday key-levels canon — what the books and desks actually use (SPY / ES)

> Living research doc (created 2026-09-09 by a Sonnet web-research crew fired by Fable; APPEND future level research here, never a new dated file — OP-22). Companion: [`TRENDLINE-BREAK-LITERATURE-2026-07-14.md`](TRENDLINE-BREAK-LITERATURE-2026-07-14.md) (trendline breaks + construction). Consumer: [`KEY-LEVELS-CHART-READING-HANDOFF.md` §9](../0dte/KEY-LEVELS-CHART-READING-HANDOFF.md#9-ta-dial-in-work-order-2026-09-09).


Scope note up front: this is web/secondary-source research (search snippets, not full book
re-reads), synthesized for Project Gamma's chart-hygiene problem. Where a claim could not be
pinned to a primary source it is marked UNVERIFIED. Nothing here was checked against the local
repo (out of scope per task).

---

## 1. Which intraday levels professional SPY/ES traders actually use

Ranked roughly by how often each shows up across market-profile literature, price-action authors,
prop-firm curricula, and options-flow desks (SpotGamma-style). No single source ranks all of these
head-to-head — this is a synthesis across sources, not one citation's ranking.

- **Prior-day high / low / close (PDH/PDL/PDC).** Universal reference level across nearly every
  day-trading discipline — market profile, price action, and gamma-flow desks all anchor to it.
  Prior-day *value area* + POC (below) is the market-profile-specific refinement of this same idea.
  (Dalton, *Mind Over Markets*; general prop-firm convention — Topstep/SMB blog material.)
- **Initial Balance (IB) — first 30–60 min range.** Core market-profile concept: "the auction that
  prints in the first hour either gets accepted (rotation day) or rejected (trend day) — entries,
  targets, invalidations flow from that one read." Classic IB = first 60 minutes (two 30-min TPO
  periods); a 30-min IB is a common intraday variant. IB high/low breaks are the trigger; failed
  extensions that fall back inside are faded. (Dalton/Steidlmayer market-profile tradition; summarized
  at satotrades.com "Initial Balance & the First Hour of ES/NQ Trading" and eminimind.com "Ultimate
  Guide to Market Profile.")
- **Developing Value Area + POC (Point of Control).** Value Area = where ~70% (±1 SD equivalent) of
  the day's TPO/volume printed; POC = the single price with the most time/volume — "the fairest
  price." If today's developing POC sits near yesterday's Prior POC, the day tends to be rotational
  (balance); moving away signals directional acceptance. This is the single most theory-dense level
  concept in the professional literature — Dalton devotes most of *Mind Over Markets* to it.
  (Dalton, *Mind Over Markets*, updated ed., Wiley; Steidlmayer's original Market Profile work;
  summarized at atas.net "Analyzing TPO" and marketcalls.in "Understanding POC and PPOC.")
- **VWAP + standard-deviation bands, plus prior-day VWAP.** VWAP is treated as a "gravitational
  line" for intraday price — a primary mean-reversion target/magnet. Bands (commonly ±1/±2/±3 SD)
  mark overbought/oversold zones; "a band of 3 standard deviations usually works well as an
  overbought/oversold region… price reaching the 2SD zone triggers textbook VWAP reversion."
  (trendsandbreakouts.com "VWAP Bands"; thevwap.com; TradingView VWAP script docs.)
- **Opening range (5/15/30 min).** Same family as Initial Balance but the non-market-profile,
  breakout-trading version — used to define an early-session range whose break/hold sets the day's
  bias. (tradeproacademy.com "Intraday Trading Strategy: How to Trade the Opening Range.")
- **Overnight/Globex high-low & premarket high-low.** Treated as a secondary but standard tier —
  used to flag where overnight positioning left resting liquidity/orders, especially relevant
  because 0DTE SPY trades against an overnight futures session. Multiple TradingView "Key Levels"
  scripts default to including these alongside PDH/PDL. (TradingView "Key Levels" script family —
  liquid-trader "Key Levels (Open, Premarket, & Yesterday)"; FlowSleuth "Automated Intraday Key
  Levels.")
- **Gamma/options levels (0DTE-specific): call wall, put wall, zero-gamma/gamma flip, max pain.**
  Specific to options-heavy names like SPY/SPX with large 0DTE flow. Call wall = strike with heaviest
  positive dealer gamma (acts as resistance/pin); put wall = heaviest negative-gamma strike (support);
  gamma flip/zero-gamma = the spot level where aggregate dealer gamma flips sign, changing the market
  from "dealer-dampening" (mean-reverting, low realized vol) to "dealer-amplifying" (trending, high
  realized vol) regime; max pain = the strike that minimizes total option-holder payout at expiry
  (a weaker, more folk-lore-y level — mechanically dubious as a magnet, but widely watched anyway).
  For 0DTE specifically, "when 0DTE gamma is large relative to total GEX, expect amplified intraday
  moves as dealers hedge rapidly decaying positions" — a real structural claim, not folklore.
  (SpotGamma methodology as summarized at zerogex.io "SPX Gamma Levels Today," gexmetrix.com,
  flashalpha.com — these are third-party trackers replicating SpotGamma's public methodology, not
  SpotGamma's own docs; treat the *mechanism* claims as more solid than the specific numeric levels
  quoted, which are live/time-stamped and stale by the time you read them.)
- **Pivot points — floor pivots and Camarilla.** Camarilla was purpose-built for day trading and
  gives tighter levels than classic floor pivots; it derives 8 levels (R1–R4, S1–S4) from prior
  high/low/close. "The most watched levels are R3/S3 (breakout zones) and R4/S4 (extreme reversal
  zones)." Classic floor pivots (P, R1–R3, S1–S3) are the older, wider-spaced cousin — still common
  in futures-trader toolkits (Raschke's *Street Smarts* tradition uses ES-specific pivot variants).
  (dailyemerald.com "Camarilla Pivots Explained"; medium.com "Mastering Trend Trading with Camarilla
  Pivot Points"; Linda Raschke/Laurence Connors, *Street Smarts*, ch. 8 — 2-period ROC and ES-specific
  pivot use, per traderslog.com and macro-ops.com summaries.)
- **Round numbers.** Weakest-theory but empirically real: Osler (2000) found take-profit orders
  cluster strongly AT round numbers (explaining reversals there) and stop-loss orders cluster just
  BEYOND round numbers (explaining accelerated momentum once broken) — a genuine microstructure
  finding, not folklore, based on actual FX dealing-bank order-flow data. SPY analog: round strikes
  ($5 handles) get disproportionate options open interest, which loops back into the gamma-level
  point above. (Carol Osler, "Support for Resistance: Technical Analysis and Intraday Exchange
  Rates," *FRBNY Economic Policy Review*, July 2000, and the companion NY Fed staff report / Journal
  of Finance 2003 piece "Currency Orders and Exchange Rate Dynamics.")
- **Weekly/monthly open.** Shows up in the "True Opens" family of TradingView scripts (an ICT-derived
  concept — "true day/week/month open") but this is a retail-ICT convention, not something Dalton,
  Brooks, or Grimes discuss; treat as lower-consensus / niche. UNVERIFIED as to real edge — no
  academic or prop-firm citation found for it in this pass, only script marketplace pages.

**Academic evidence that S/R "works" at all (not level-specific, but foundational):**
- Osler (2000) — see above; order-flow-based mechanism for why S/R reversal AND breakout-momentum
  predictions both hold.
- Brock, Lakonishok & LeBaron (1992), "Simple Technical Trading Rules and the Stochastic Properties
  of Stock Returns," *Journal of Finance* — moving-average and trading-range-break rules showed
  real predictive power on the DJIA 1897–1986, rejecting random-walk/GARCH null models via
  bootstrap. Caveat found in the same search: later replications (through 2013, across three
  developed markets) show the effect **decayed sharply after 1986** — "markets may have adapted."
  This is a real caveat, not a dismissal — cite it as "worked historically, faded since," not as
  "still works."
- Lo, Mamaysky & Wang (2000), "Foundations of Technical Analysis: A Statistical Approach,"
  *Journal of Finance* 55(4), 1705–1765 — showed technical patterns (head-and-shoulders etc.) have
  statistically detectable predictive content when extracted via automated (kernel-regression)
  pattern recognition rather than eyeballing, and separately argued classic manual pattern ID is
  "in the eyes of the beholder" — an implicit critique of unaided manual S/R drawing, relevant to
  the trader's "unreadable chart" complaint.

---

## 2. Level count & chart hygiene

Direct explicit numeric guidance was hard to pin to a single canonical source — most of what
turned up is TradingView script convention and inferred prop-desk practice, not a stated rule from
a named authority. Flagged where evidence is thin.

- **Fewer, higher-conviction levels is the repeated theme**, not a single hard number. One
  TradingView-script-convention data point: "best practices suggest enabling just the True Day
  Open, True Week Open, and Previous Day H/L only, resulting in just 4 levels on the chart" — this
  is script-vendor guidance (liquid-trader/ICT-style script docs), not an academic or prop-firm rule.
  UNVERIFIED as a general principle beyond that one script's marketing copy, but directionally
  consistent with the price-action-school philosophy below.
- **Zone width: ATR-based or % of price**, not fixed dollar amounts. Practical rule found: "set zone
  width to approximately 0.5%–1.5% of the price... for SPY at $500, zones of roughly $2.50–$7.50
  wide." ATR-based zones "automatically adapt to changing market volatility, widening during high
  turbulence and tightening during quiet periods" — validated by "sanity-checking zone width against
  ATR so the zone stays small relative to the moves being traded." (trendspider.com "Support/
  Resistance Strength," tradingbauhaus "Dynamic ATR Cluster Support Resistance Zones" — both
  vendor/script docs, treat as informed industry convention rather than peer-reviewed rule.)
- **Merging nearby levels into one zone** is standard practice in every S/R-zone script surveyed —
  clustering logic (deduping levels within X ATR or X% of each other into a single band) is
  built into most TradingView "Key Levels" and "S/R Zone" scripts (LuxAlgo's S/R Zone concept
  library; Flux Charts' Key Levels — "can dynamically combine same key levels for a clearer look
  without lines and text colliding").
- **Aging out stale levels**: the closest explicit rule found is behavioral, not calendar-based —
  "on each revisit, traders record whether the zone produced a reaction or was traded through; they
  archive zones that have been cleanly broken, or flip them to the opposite role" (see §3). No
  source gave a fixed "N days and delete" rule; staleness is event-driven (broken + retested = dead
  or flipped), not time-driven, across every source found.
- **Visual encoding of importance**: touch-count and role (support vs resistance vs pivot vs VWAP)
  driving line weight/color is universal in the script ecosystem (Bjorgum Key Levels, Flux Charts)
  but is a UI convention, not a documented "rule" from a named trading authority — treat as
  industry-standard implementation detail, not doctrine.
- **Al Brooks' implicit answer to "how many levels"**: Brooks doesn't prescribe a level count at
  all — his stated position is that indicators/lines are secondary to reading the bar-by-bar
  argument between bulls and bears: "once you start seeing the chart as a running argument between
  bulls and bears, a lot of the clutter disappears... [he] condenses all the necessary tools into
  the price chart itself, relying solely on candlesticks and price action... views indicators as
  lagging and often misleading, obscuring the market's true story." This is the strongest single
  data point for radical minimalism, though it argues for de-emphasizing lines generally rather
  than giving a specific cap. (Al Brooks, *Trading Price Action Trading Ranges*, Wiley; supporting
  material at brookstradingcourse.com.)

---

## 3. Support/resistance as zones: what counts as a test/touch/reclaim/break/flip

- **Zone > line, universally.** Every source in this pass — Brooks, Grimes, and the vendor/script
  literature — treats S/R as a band, not an exact price. Brooks: "support and resistance [are] zones
  — areas where price may slightly exceed these boundaries before reversing, rather than precise
  lines." Grimes: "teaches traders to look beyond obvious horizontal lines and instead focus on
  zones created by clusters of price action, volume, and historical turning points." (Al Brooks,
  price-action corpus; Adam Grimes, *The Art and Science of Technical Analysis*, Wiley.)
- **Break confirmation — close-through, not wick-through, plus follow-through.** A commonly cited
  3-factor breakout-confirmation rule: "(1) volume expansion 50%+ above average, (2) decisive close
  — candle body closes beyond the level, (3) follow-through — momentum continues on the next 1–2
  candles." This is the clearest explicit "what counts as a break" rule surfaced in this research
  pass (vendor/educational source, optimusfutures.com "Support and Resistance Trading: Complete
  Guide for Futures" — treat as informed industry convention, not peer-reviewed).
- **Flip rule (support becomes resistance / vice versa)**: "on each revisit, traders record whether
  the zone produced a reaction or was traded through; they archive zones that have been cleanly
  broken, OR flip them to the opposite role and watch how price treats them from the other side."
  Confirmation of a flip = the level actually rejects price from the new (opposite) side on a
  retest — i.e., the flip isn't assumed at the moment of breaking, it's confirmed by the retest
  reaction. (Same optimusfutures/trendspider-family sourcing as above.)
- **Osler's microstructure evidence backs the flip/break-momentum mechanism directly**: stop-loss
  orders cluster just beyond round numbers/levels, so once a level is crossed those stops fire and
  "intensify trends" — i.e., real resting-order clustering is the mechanism behind "breakout gains
  momentum," not charting mysticism. (Osler 2000, cited above.)

---

## 4. Indicator minimalism for intraday SPY (EMAs/ribbons/SMA 50-200/VWAP)

- The **price-action school's default stance is skeptical of stacked moving-average ribbons on
  intraday charts.** Brooks in particular is explicit that he trades off candlesticks/price action
  alone and regards most indicators, including moving averages, as lagging: "he views indicators as
  lagging and often misleading, obscuring the market's true story" — this is a direct argument
  against exactly the kind of 9-EMA ribbon + SMA 50/200 stack Project Gamma's chart currently runs.
  (Al Brooks corpus, brookstradingcourse.com.)
- Grimes is more moderate — he uses moving averages but for **structure, not signal**: "Simple
  Moving Averages (SMA) are useful for identifying longer-term trends, while Exponential Moving
  Averages (EMA) provide more weight to recent price data" — a single SMA (trend context) plus
  maybe one EMA (recent-price weighting) is the implied minimal set, not a 5-line ribbon. No source
  in this pass found Grimes or Raschke endorsing a multi-EMA "ribbon" specifically. (Adam Grimes,
  *The Art and Science of Technical Analysis*.)
- **VWAP is the one indicator every school agrees earns its place on an intraday SPY chart** — it's
  treated as structural (an actual traded reference the algos/institutions use), not a lagging
  derivative like a moving average. This differentiates VWAP from a generic EMA/SMA stack: "VWAP
  often acts as a gravitational line for intraday price action" and is watched by institutional flow,
  not just retail pattern-readers. (trendsandbreakouts.com, thevwap.com.)
- **Net read for Gamma's chart**: the consensus across price-action authors leans toward VWAP +
  at most one or two moving averages for trend context, NOT a 9-EMA ribbon + SMA 50 + SMA 200 all
  simultaneously visible — that combination is closer to "indicator clutter" than to any named
  school's documented practice. No source explicitly validates a 5-line EMA ribbon as standard;
  this appears to be a Gamma-specific addition, not an industry convention. Flag as UNVERIFIED-as-
  standard / likely non-standard.

---

## 5. Momentum exhaustion as a trigger (brief)

- **Brooks' climax/three-push/wedge framework** is the most directly applicable citation for this
  strategy's "momentum exhaustion" trigger: a climax is "a move that has gone too far too fast and
  has now reversed direction"; a sustainable trend "usually corrects after 3 pushes" — three-push
  patterns with large trend bars often ARE the climax; wedges (converging trend/channel lines around
  a three-push structure) "at the end of a move often flag exhaustion and open the door for a
  reversal or deeper pullback." Exhaustion gaps: "an unusually big bull bar or bars late in a bull
  trend usually attract profit taking and create at least a minor reversal down." (Al Brooks,
  *Trading Price Action Reversals*, Wiley — ch. 5 "Wedges and Other Three-Push Reversal Patterns.")
- **TICK/ADD extremes for SPY/index intraday exhaustion**: extreme NYSE TICK readings above
  roughly +1000/+1200 or below −1000/−1200 mark short-term exhaustion candidates, but **context
  matters** — "a TICK spike to +1100 early in a strong trending day is often a continuation signal,
  while the same spike after two hours of relentless buying tends to mark exhaustion." Best practice
  is to require confirmation from a second internal (ADD/TRIN/VOLD) before fading a TICK extreme —
  "only fade TICK extremes when TRIN and ADD are also stretched." (jumpstarttrading.com "NYSE Tick,"
  usethinkscript.com community threads on ADD/TICK/VOLD divergence — retail/community sourcing,
  reasonable industry convention but not an academic citation.)
- RSI divergence and volume climax are mentioned across multiple generic technical-analysis sources
  as standard exhaustion tells but no single authoritative citation surfaced beyond general
  TA convention in this search pass — treat as well-known but weakly-sourced in this brief.

---

## Consensus ranking of intraday levels for SPY 0DTE

| Level | Consensus rank | Why | Source |
|---|---|---|---|
| Prior-day H/L/C | 1 (near-universal) | Anchor reference every school uses; cheap, stable, high-recognition | Dalton; general prop convention |
| VWAP (+ SD bands) + prior-day VWAP | 1 (near-universal) | The one "indicator" every price-action/quant school agrees belongs on an intraday chart; institutional execution benchmark | trendsandbreakouts.com; thevwap.com |
| Initial Balance (IB) high/low | 2 (market-profile core) | First-hour range structurally determines rotation-vs-trend day; entries/targets flow from it | Dalton/Steidlmayer; satotrades.com, eminimind.com |
| Developing Value Area + POC | 2 (market-profile core) | Defines where "fair" trade is happening now vs. yesterday; balance/imbalance read | Dalton, *Mind Over Markets* |
| Opening range (5/15/30m) | 2 (breakout-school core) | Non-market-profile analog of IB; defines early bias for breakout traders | tradeproacademy.com |
| Gamma levels (call wall/put wall/zero-gamma) | 2–3 (0DTE-specific, high relevance but non-classical) | Structurally real for heavy-0DTE names — changes vol regime at zero-gamma flip | SpotGamma methodology via zerogex.io/gexmetrix.com (3rd-party trackers) |
| Camarilla pivots (R3/S3, R4/S4) | 3 | Purpose-built tighter day-trading levels vs floor pivots; widely used by futures/ES day traders | dailyemerald.com; Raschke *Street Smarts* tradition |
| Overnight/Globex high-low, premarket high-low | 3 | Standard secondary tier, especially relevant pre-open into 0DTE | TradingView Key Levels script family |
| Round numbers | 3 (real but weak-magnitude) | Genuine order-clustering microstructure effect, not folklore, but small-effect | Osler (2000) |
| Floor pivots (classic P/R1-3/S1-3) | 4 | Older/wider-spaced, superseded intraday by Camarilla for many day traders | dailyemerald.com |
| Max pain | 4 (weak/contested) | Widely watched but mechanically the least justified of the gamma-family levels | zerogex.io/general options-flow convention |
| Weekly/monthly open ("true opens") | 5 (niche/ICT) | Retail-ICT convention; no academic or classical prop-firm backing found in this pass | TradingView "True Opens" scripts (UNVERIFIED as edge) |

---

## Chart hygiene rules extracted (max 12)

1. Zone width scales with **ATR or % of price**, not a fixed dollar amount — for SPY, roughly
   0.5–1.5% of price is a cited starting point (widen in high-vol regimes, tighten in low-vol).
2. **Merge/cluster levels within the zone-width tolerance** into one band rather than drawing
   separate lines a few cents/ticks apart — standard in every S/R-zone script surveyed.
3. **Break = close beyond the level (body, not wick) + volume/follow-through**, not a single wick
   touch — the most explicit "what counts as a break" rule found.
4. **A level's role isn't retired at the moment of a break** — it's either archived (cleanly broken,
   dead) or flipped to the opposite role, and the flip is *confirmed* only by how price reacts on
   the retest from the new side.
5. **Staleness is event-driven, not calendar-driven** — no source gave a fixed "delete after N days"
   rule; a level dies when it's cleanly broken-and-not-retested, not on a timer.
6. **Fewer, higher-conviction levels over many** is the repeated theme, though only one concrete
   number surfaced ("~4 levels: true day open, true week open, prior day H/L") from script-vendor
   guidance, not a named authority — treat as directional, not a hard cap.
7. **Visual weight should encode importance/touch-count/role** (color/line-weight/label), a
   universal convention in the script ecosystem though not tied to one named source.
8. **VWAP earns a permanent chart slot; stacked EMA ribbons generally don't** — Brooks argues
   indicators (including MAs) are lagging/noise; Grimes treats a single SMA/EMA as structural
   context, not a 5-line ribbon. A 9-EMA ribbon + SMA50 + SMA200 simultaneously is closer to
   clutter than to any named school's documented practice.
9. **Initial Balance / opening range is a first-class level, not a footnote** — it structurally
   determines rotation-day vs. trend-day and should be visually distinct, since entries/targets/
   invalidations for the rest of the session flow from it.
10. **0DTE-specific: gamma flip/call-wall/put-wall change the *regime* (mean-reverting vs
    trending), not just add another S/R line** — worth a visually distinct treatment from ordinary
    price-based S/R, since the "why" is different (dealer hedging flow, not price memory).
11. **Round numbers are a real but small effect** — fine to keep as a light-weight tertiary
    reference, not a primary trigger level, per Osler's clustering-magnitude findings.
12. **Treat S/R fundamentally as zones with defined width, never bare price lines** — this is the
    one point every source (Brooks, Grimes, vendor scripts, Osler's mechanism) agrees on without
    exception, and is the most load-bearing single fix for a chart that's "unreadable."

---

## Sources (consolidated)

- James F. Dalton, *Mind Over Markets: Power Trading with Market Generated Information*, Wiley (updated ed.) — https://www.wiley.com/en-us/Mind+Over+Markets
- Steidlmayer/Market Profile tradition — summarized: atas.net "Analyzing TPO," marketcalls.in "Understanding POC and PPOC," eminimind.com "The Ultimate Guide to Market Profile"
- satotrades.com, "Initial Balance & the First Hour of ES/NQ Trading (2026)" — https://satotrades.com/guides/initial-balance-futures
- tradeproacademy.com, "Intraday Trading Strategy: How to Trade the Opening Range"
- trendsandbreakouts.com, "VWAP Bands"; thevwap.com "The Detailed Guide to VWAP"
- zerogex.io "SPX/QQQ Gamma Levels Today"; gexmetrix.com "Free SPX Gamma Exposure (GEX)"; flashalpha.com — third-party trackers replicating SpotGamma-style methodology (not SpotGamma's own docs)
- dailyemerald.com, "Camarilla Pivots Explained"; medium.com, "Mastering Trend Trading with Camarilla Pivot Points"
- Linda Bradford Raschke / Laurence Connors, *Street Smarts*, ch. 8 — summarized via traderslog.com "Trader Linda Raschke Provides Tips on Day-Trading S&P," macro-ops.com "Lessons From a Trading Great: Linda Bradford Raschke"
- Carol L. Osler, "Support for Resistance: Technical Analysis and Intraday Exchange Rates," FRBNY Economic Policy Review, July 2000 — https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf ; companion: "Currency Orders and Exchange-Rate Dynamics," NY Fed Staff Report 125 — https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf
- William Brock, Josef Lakonishok, Blake LeBaron, "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns," Journal of Finance, 1992 — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x
- Andrew W. Lo, Harry Mamaysky, Jiang Wang, "Foundations of Technical Analysis: A Statistical Approach," NBER Working Paper 7613 / Journal of Finance 55(4), 2000 — https://www.nber.org/papers/w7613
- Al Brooks, *Trading Price Action Trading Ranges*, Wiley; *Trading Price Action Reversals*, Wiley (ch. 5, wedges/three-push) — supporting material at brookstradingcourse.com, trasignal.com "The Complete Al Brooks Price Action Guide"
- Adam H. Grimes, *The Art and Science of Technical Analysis: Market Structure, Price Action, and Trading Strategies*, Wiley — https://www.wiley.com/... (via Goodreads/Amazon listings, tradermarkus.com review)
- trendspider.com "Support/Resistance Strength"; tradingbauhaus "Dynamic ATR Cluster Support Resistance Zones"; optimusfutures.com "Support and Resistance Trading: Complete Guide for Futures" — vendor/educational sourcing on zone width and break confirmation
- LuxAlgo Library, "S/R Zone — Support/Resistance & Levels Concept" — https://www.luxalgo.com/library/concept/s-r-zone/
- TradingView script marketplace: liquid-trader "Key Levels (Open, Premarket, & Yesterday)," FlowSleuth "Automated Intraday Key Levels," Flux Charts "Key Levels," Bjorgum "Key Levels" — script-vendor convention, not authoritative doctrine
- jumpstarttrading.com "NYSE Tick — Instantly Boost Your Day Trading Profits"; usethinkscript.com community thread "$ADD $TICK $VOLD trading strategy — Divergence Indicator" — community/retail sourcing on TICK/ADD exhaustion reads

## What was NOT verified in this pass
- No SMB Capital or Bear Bull Traders primary-source doc gave an explicit numeric "max N levels"
  rule — search returned only blog/marketing pages, not curriculum text.
- The "≈4 levels" TradingView-script guidance is vendor marketing copy, not a cited authority —
  flagged as directional, not doctrine.
- Weekly/monthly "true open" levels have no academic or classical prop-firm backing found; ICT/
  retail-script convention only.
- Max pain's predictive validity is contested even within the options-flow community; treat as
  the weakest level in the gamma family despite being widely watched.
