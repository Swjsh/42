# Tori Trendline Research — 2026-08-09

> Web-research deep dive on "Tori Trades," per J's ask. ~30 WebSearch/WebFetch calls across
> spelling variants, platforms, methodology sources, and reputation checks. No paid content
> reproduced; no personal/biographical digging beyond what the subject publishes about her own
> trading. Nothing in this file was committed.

---

## VERDICT

- **Identified with high confidence, single candidate:** Victoria Duke, trading as **"Tori
  Trades" / "Tori Tradez"** — a Nashville, TN futures trader and trading educator. Deliberate
  search for alternates (other spellings, an options/SPY-specific "Tori") found no credible
  second candidate — see Phase 1.
- **The method is genuinely mechanical**, not vibes — pivot-anchored trendlines, minimum touch
  count, defined entry/stop/target logic. It is real enough that two different strangers have
  independently tried to code it as TradingView Pine Script indicators. But the **full rule set
  lives behind a $299 course** (plus a ~$4,000 mentorship tier); what's free is a teaser
  playbook/checklist and derivative summaries — see Phase 2.
- **Wrong market for a direct port.** She swing-trades **commodity futures** (Crude Oil, Platinum,
  occasional Gold/Dow) on **4-hour-to-weekly** charts, holding for **weeks**, not SPY 0DTE options
  held minutes-to-hours. Her numeric parameters (6+ candles between touches, 3+ weeks of line
  maturity) do not transfer bar-for-bar to an intraday instrument — see Phase 4.
- **Reputation is genuinely contested**, not clean. A favorable third-party broker-statement
  review exists; so does a serious, specific, unverified allegation (from a **competing**
  educator) of doctored broker statements and a shared account number between her and her uncle's
  promotional material. Apply the same skepticism standard as the earlier prop-firm research —
  see Phase 3.
- **Correction to the task brief's framing of our own engine:** the claim that
  `trendline_rejection` "has never been able to fire" is **outdated**. Per
  `analysis/deep-research/EOD-2026-08-06.md`, the live bear-side detector
  (`detect_trendline_rejection_bearish`, `backtest/lib/filters.py:601`) fired on **all 8**
  `ENTER_BEAR` verdicts on 2026-08-06 and produced **100%** of that day's P&L. What's actually
  shadow-only is (a) the standalone `trendlines.json`/`trendlines-live.json` **files** (zero
  decision consumers, confirmed) and (b) the **bull-side mirror**, `detect_trendline_reclaim_bullish`
  (explicitly shadow-logged in the source). See Phase 4 §1 for the precise, cited breakdown.
- **Recommendation: no blind adoption, but two narrow ideas are worth a frozen prereg** — see
  Phase 4 §4. Nothing here is a "ship it" edge; everything is a hypothesis to test.

---

## Phase 1 — Identity

### Search coverage

Ran variants across: Tori / Tory / Torie spellings; "Tori Trades" / "ToriTrades" / "@toritrades";
combined with day trading, options, SPY, futures, ES, forex, swing trading, YouTube, TikTok,
Instagram, X, Discord, Substack, Skool, Whop, Patreon; plus an explicit negative search
(`"trendline" trader "Tori" OR "Torie" options SPY stocks -futures -Duke`) to try to surface a
*different* Tori who trades options/SPY specifically. Every search converged on the same person.
**No second candidate found.** This is the honest outcome, not a collapsed-multiple-people
situation — there appears to be one dominant public figure using this name for trendline trading.

### The candidate

| Field | Value | Confidence |
|---|---|---|
| Real name | Victoria Duke | High — consistent across LinkedIn, TradingView bio, multiple press/podcast pages |
| Brand/handle | "Tori Trades" (social handles), "Tori Tradez" (toritradez.com domain — stylized spelling of the same brand) | High |
| Location | Nashville, TN | High — self-stated across platforms |
| Market traded | Futures — primarily Crude Oil (CL) and Platinum (PL), occasional Gold and Dow (YM); also teaches an options-selling structure on mega-cap stocks (NVDA/MSFT/AAPL/AVGO/GOOGL) | Medium — instrument list from a favorable third-party review ([a1trading.com](https://www.a1trading.com/is-tori-trades-a-legit-trader-find-out-here/)) plus her own site's options-strategy page; not independently verified against real fills |
| Years trading | Stated inconsistently across sources: 9 / 10 / 11 years, age given as both 32 and 33 — low-stakes bio drift, not independently verified (out of scope per the "no biographical digging" constraint) | Low (self-reported, drifting) |
| Trendlines central to method? | Yes — it is the entire branding and product ("Trendline Strategy," "Trendline Playbook," "Trendline Community") | High |
| Confidence this is who J means | High | — |

### Platform footprint (as observed 2026-08-09)

| Platform | Handle | Followers/subs | Source |
|---|---|---|---|
| Instagram | @tori.trades | 712K | [instagram.com/tori.trades](https://www.instagram.com/tori.trades/) |
| TikTok | @tori.trades | 311K followers, 4.8M likes | search aggregation, [tiktok.com/@tori.trades](https://www.tiktok.com/@tori.trades) |
| X/Twitter | @toritrades | 88.1K, joined Feb 2019 | [x.com/toritrades](https://x.com/toritrades?lang=en) |
| YouTube | @ToriTrades | 200K+ subs (bio claims "over half a million" across platforms combined, not YouTube alone), actively growing | [youtube.com/@ToriTrades](https://www.youtube.com/@ToriTrades), [vidIQ stats](https://vidiq.com/youtube-stats/channel/UC0ep2A36j7gTFdqW2Yvngbg/) |
| TradingView | Tori-Trades | 2.7K followers, 3 published ideas, **0 published scripts** | [tradingview.com/u/Tori-Trades](https://www.tradingview.com/u/Tori-Trades/) |
| Website(s) | toritradez.com (main funnel), tori-trades.thinkific.com (course host), community.toritradez.com (Discord/community portal) | — | direct fetch |

Note the important negative finding here: her own TradingView account has published **zero scripts**.
The Pine Script indicators that claim to encode "the Tori Trades strategy" (below, Phase 2) are
**third-party reverse-engineering attempts by other TradingView users**, not her official code.

---

## Phase 2 — The method

### Sourcing caveat (read before trusting the table below)

I could not get clean primary-source text. Her own free PDF checklist
([hosted on her Webflow CDN](https://cdn.prod.website-files.com/668852f921e36c3365b91d03/6851a0c6c14969d9b98520a2_Tori%20Trades%20Trendlines.pdf))
returned as unparsable binary; the Scribd mirrors ([1](https://www.scribd.com/document/920197298/Tori-Trades-Trendlines),
[2](https://es.scribd.com/document/907054649/Tori-Trades-Playbook)) blocked content extraction.
What follows is triangulated from **derivative/SEO summary pages** (TradeZella, ChartFanatics,
FX Replay — all appear to be independently-written but closely-paraphrased summaries of the same
underlying free playbook, so treat this as **one source confirmed three ways**, not three
independent sources) plus one direct fetch of her own site's homepage and one interview-based blog
post. Everything below is restated in my own words, not quoted from paid material.

### The system: two reference lines, two setups

Her stated approach uses no indicators — pure price action. Two lines do all the work:
- **Action Line** — the trendline itself; the entry trigger.
- **Safety Line** — an opposing/supporting trendline; the stop-loss reference.

Two named setups, per [TradeZella's summary](https://www.tradezella.com/strategies/trendline-strategy)
and [FX Replay's summary](https://fxreplay.com/strategies/tori-trades-trendlines-strategy):

| Element | Bounce setup | Break setup |
|---|---|---|
| Entry logic | Enter at the touch itself, once the line is validated | Enter once a candle **closes** past the line (not just a wick-through) |
| Order type | — | Market order on the close |
| Stop | The line itself; a close-through invalidates | Where the safety line would intersect ~4 candles after the break |
| Target | Trail as new valid swing points form | First support/resistance level offering 2R or better |
| Invalidation | Price closes through the line | Price closes back beyond the safety line |

### Trendline validity rules (the mechanically interesting part)

Consistently reported across the derivative sources:
- **Anchoring: wicks, not bodies.** Multiple independent summaries describe validity as "3 or
  more taps (wicks)" — i.e., the line is fit to candle highs/lows, not opens/closes. This is
  notable given J's own hard rule (anchors must be ALL-body or ALL-wick, never mixed) — her stated
  convention, as reported, is consistently wick-only, which is internally consistent with that rule
  even though she doesn't appear to state the body/wick distinction explicitly as a *rule* the way
  J does.
- **Minimum touches: 3.** ("at least two or three clear touchpoints" in one paraphrase, "3 or more
  taps" in others — converges on 3 as the operative minimum.)
- **Spacing: 6+ candles between taps** — meant to filter out a cluster of touches that's really one
  reaction, not three independent tests.
- **Duration: drawn over 3+ weeks** of price history.
- **Slope constraint: under 45 degrees** when viewed zoomed to ~3 months of chart data — filters
  out unsustainably steep lines.
- **Timeframe: 4-hour chart** for drawing and trading, with the **daily/weekly** used top-down
  only to confirm the prevailing trend direction before dropping to the 4H to draw and trigger.
- **One attempt per trendline** — once a line has been traded and stopped out, it's not re-traded.
- Caution flagged around **futures contract rollover periods** specifically (an artifact of her
  instrument, not applicable to SPY options).

### Confluence factors — genuinely unclear, flag as possibly embellished

One derivative source ([TabCut's interview-based writeup](https://www.tabcut.com/blog/post/trading-simple-trend-line-strategy-made-her-100k-a-year))
states plainly that her own words describing the strategy make **no mention of volume, moving
averages, or session timing** — just multi-timeframe trend confirmation (daily/weekly bias, 4H
execution) plus the touch/slope/spacing checklist above. A *different* SEO page claims "volume
confirms your analysis" as part of the system. Given the sourcing problem above (SEO pages
paraphrasing a paywalled document, possibly padding with generic trading-education boilerplate),
I'm not confident the volume claim is actually hers. Treat any confluence beyond the
touch/slope/spacing/timeframe checklist as **unverified.**

### Third-party attempts to code it

Two TradingView community members have published open-source Pine Script indicators explicitly
named after her strategy:
- ["Tori Trades - Trend Line System" by nifin007](https://www.tradingview.com/script/1qkEcoEp-Tori-Trades-Trend-Line-System/) —
  auto-detects trendlines from pivot highs/lows with a configurable lookback, fires long/short
  signals on trendline breaks, uses the opposing line as the safety-line exit.
- "Tori Trendlines" (a second, simpler open-source script plotting lines per the basic rule set).

Both are **outsider reconstructions from her public rule descriptions**, not her own code (she has
published zero scripts on her own account, per Phase 1). Their existence is useful signal for one
thing only: independent parties looked at her stated rules and concluded they were concrete enough
to encode as a pivot-based detector — which is the same conclusion Phase 4 reaches independently
below.

---

## Phase 3 — Reputation: is this real?

The task asked me to apply the same skepticism as the earlier prop-firm research and weight
affiliate-driven "reviews" as marketing, not evidence. Doing that here surfaces a genuine,
unresolved conflict — not a clean answer either direction.

### Case for legitimacy

| Evidence | Detail | Source |
|---|---|---|
| Trustpilot | ~4/5 stars, 458 reviews for toritradez.com | [trustpilot.com/review/toritradez.com](https://www.trustpilot.com/review/toritradez.com) |
| Third-party broker-statement review | A1 Trading ("TraderNick") reviewed actual TradeStation statements and reported a consistent, rising equity curve on Crude Oil/Platinum futures | [a1trading.com](https://www.a1trading.com/is-tori-trades-a-legit-trader-find-out-here/) — **flag: affiliate-driven**, promotes A1's own Discord/products throughout, not a neutral third party |
| Podcast circuit | Repeat guest on independent trading podcasts — Humbled Traders, The Day Trading Show, Words of Rizdom, the Ed Clay Show — described on one show as "the first female guest" and someone who has reportedly "never blown a trading account" | [Spotify/Buzzsprout episode pages](https://open.spotify.com/episode/3Nsf1xa04RbljF0Nq0HMdK) — **self-reported claim inside a friendly interview format, not independently verified** |
| Family trading lineage | Her uncle, Mike Aston ("Trading Template"), runs his own trading-education business with an independently-decent Trustpilot record (~4/5, 178 reviews) | search aggregation of tradingtemplate.com Trustpilot |

### Case for skepticism

| Allegation | Detail | Source |
|---|---|---|
| Doctored broker statements | A critical review states two separate broker-statement images attributed to her were independently flagged as doctored — one "a clumsy forgery riddled with misspellings," the other cleaner but with formatting inconsistencies | [beststockstrategy.com/tori-trades-review](https://beststockstrategy.com/tori-trades-review/) — **flag: written by David Jaffee, who sells a competing paid trading course ("Financed Bull") — direct competitor conflict of interest, same as the affiliate-review problem, just pointed the other direction** |
| Shared account number | The same review claims a specific brokerage account number appeared in promotional material for **both** her and her uncle's trading success — a single account cannot legitimately belong to two separate traders' marketed track records | same source — **single-source, unverified by me, but specific enough to be checkable in principle** |
| Reconstructed ~$250K drawdown | An analyst referenced in the review ("Market Mommy") allegedly reconstructed a ~50%-of-account drawdown over 3-4 weeks that was later marketed as a win rather than disclosed as a risk event | same source — **unverified, single-source** |
| Whistleblower claim | A reported former employee allegedly supplied internal documents suggesting fabricated results | same source — **unverified, single anonymous source, weakest-tier evidence** |
| Failed prop-firm evaluations | Alleged leaked livestreams reportedly show failed Topstep/Apex evaluations — firms she promotes via affiliate links | same source — **unverified** |
| High-risk-content flag | A generic scam-advisory scanner flags her Thinkific course site as offering "high risk financial services or content," standard boilerplate for any paid trading-education site, not a specific finding against her | [scamadviser.com](https://www.scamadviser.com/check-website/tori-trades.thinkific.com) — low-value signal, noted for completeness only |
| Mixed Trustpilot detail | Even within the mostly-positive Trustpilot page, at least one reviewer specifically flagged the free/entry material as recycled-free-content and the paid mentorship as "messy and hardly maintained" | [trustpilot.com/review/toritradez.com](https://www.trustpilot.com/review/toritradez.com) |

**Read on the conflict:** both the strongest positive review and the strongest negative review are
written by people who sell competing trading education — the A1 Trading piece funnels to A1's own
Discord/signals products, the beststockstrategy.com piece funnels to Jaffee's own course. Neither
is a neutral, disinterested source. I found **no regulatory (SEC/CFTC/FINRA) action, no
independent forensic document analysis, and no court record** — the doctored-statement claim is a
serious, specific allegation that I cannot verify or refute from public sources, and it should be
weighted as such: a real credibility question mark, not a confirmed finding, and not dismissible
either given how specific it is (a named account number, a named reconstructed drawdown).

### Funnel structure (is the free material actually free?)

- **Genuinely free:** YouTube/TikTok/IG/X content, the strategy overview on toritradez.com, and the
  "Trendline Playbook" PDF checklist (the one I couldn't parse, but multiple independent summaries
  confirm its content matches the free-tier rule set above).
- **Paid, $299:** the "Learn to Trade" community + course.
- **Paid, ~$4,000:** a mentorship tier.
- **Formerly paid, $1,997, now discontinued:** a 21-day "Accelerator" bootcamp.
- Sources: [Trustpilot review thread](https://www.trustpilot.com/review/toritradez.com) (pricing
  mentioned in reviews), [Whop marketplace listing](https://whop.com/marketplace/toritrades-accelerator/)
  (listing itself returned "removed," consistent with the accelerator being discontinued).

So: **the mechanical skeleton (touch count, wick-anchoring, action/safety line, entry/stop/target
logic) is free and consistent across every source I found.** What's paywalled is depth — live trade
walkthroughs, community feedback, and presumably more nuanced discretionary judgment on what
qualifies as a genuine touch vs. noise. That matches the task brief's hope ("her strategy might be
out there for free") reasonably well — the skeleton is out there for free; it's not a con where
"free" just means a lead-gen teaser with zero content.

---

## Phase 4 — So what for Project Gamma

### 1. Correcting the internal-state framing before using it

The task brief states trendline_rejection "has never been able to fire" and that consumption has
"ALWAYS been shadow-only with zero validated downstream consumers." Checking this against the
project's own most recent audit before building on it (per debugging discipline — verify against
cold reality, not memory):

- **This is half right, half outdated.** Per `analysis/deep-research/EOD-2026-08-06.md` (§VERDICT,
  point 2) and `EOD-2026-08-06-FULL-REVIEW.md`, the claim "trendlines.json 47 days stale → the
  trigger can never fire" was investigated and found **wrong on the causal link**. The live
  bear-side detector, `detect_trendline_rejection_bearish` (`backtest/lib/filters.py:601`), computes
  its trendline **in-process from `prior_bars`** — it has never read `trendlines.json` at all. On
  2026-08-06 it was the **sole trigger on all 8 `ENTER_BEAR` verdicts** and generated **100% of that
  day's P&L**.
- **What actually is shadow, confirmed:** (a) the standalone `trendlines.json` /
  `trendlines-live.json` **state files** — `analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md`
  confirms these have zero live decision consumers (`confluence_producer.py` and doc references
  only); (b) the **bull-side mirror**, `detect_trendline_reclaim_bullish` — its own docstring in
  `backtest/lib/filters.py` (line ~954) states explicitly it is "SHADOW-LOGGED only."
- **Net correction:** the bear-side in-engine trendline detector is live, wired, and has proven
  P&L. The drawn/persisted trendline *files* and the *bull-side* mirror are the genuinely shadow
  pieces. Any new work here should target the bull side and the file-consumption gap, not re-solve
  an already-solved bear-side liveness problem.

### 2. Structural comparison: her rules vs. our existing detector

Our own `detect_trendline_rejection_bearish` and Tori's stated Break setup are strikingly similar
in *shape* — both are pivot-anchored, wick-based, minimum-3-touch, close-confirmation trendline
break detectors. That convergence (arrived at independently) is a mild point in favor of the
general pattern being a sound one, not evidence her specific numeric tuning is right for our
instrument.

| Parameter | Tori (stated, futures swing, 4H) | Our engine (`filters.py:601`, SPY 0DTE, 5m) |
|---|---|---|
| Anchor | Wicks | Wicks (bar high/low; `trendlines.py` docstring confirms "wicks count") |
| Min touches | 3 | 3 (`min_swings=3`) |
| Touch spacing | 6+ candles (4H → ~24h+ apart) | Not explicitly bar-spaced; uses sequential-descending-peak logic over a lookback window |
| Line maturity | 3+ weeks | `lookback_bars=60` on 5m bars (a few hours) |
| Slope cap | <45° over 3 months | Not slope-capped; requires strictly decreasing pivots |
| Entry confirmation | Candle **closes** past the line | Bar **closes** below the line **and** closes red (stricter — needs both) |
| Touch proximity tolerance | Not numerically stated | `proximity_pct=0.0010` (~0.10%) |
| Direction | Both (bounce/break, ascending/descending) | **Bear-only** as coded; bull mirror exists but is shadow-only |
| Stop | Opposing "safety line" intersection ~4 candles post-break | Not part of this detector — stop logic lives in the exit-manager / chart-stop-primary doctrine separately |
| Re-entry | One attempt per line | No equivalent re-entry cap found in this detector |

### 3. Classification — what's actually portable

**(a) Concrete enough to code and pre-register:**
- **Wick-anchored, 3-touch, close-confirmation trendline break** — we already have this
  structurally; it is not a new idea, it is validation that our existing approach matches an
  independently-arrived-at industry pattern. Nothing new to prereg here.
- **Safety-line-as-dynamic-stop** — this is the one genuinely new, mechanically specifiable idea.
  Instead of (or alongside) the current catastrophe-cap/chandelier exit doctrine, define the stop
  as the price-projection of the *opposing* trendline (the parallel/channel line on the other side
  of price) at time of entry, rescaled to intraday. This is directly testable: for every historical
  `trendline_rejection` fire in the 391-day population, compute where an opposing pivot-fit line
  would have projected, and compare that stop distance/hit-rate against the current stop. Fits
  cleanly into the existing "chart-stop-primary" doctrine (2026-06-18) rather than fighting it.
- **"One attempt per line" re-entry cap** — codifiable (track which specific trendline instance
  produced a stopped-out entry, block re-entry on the *same* line for the rest of session/day) but
  per the standing "kill unvalidated re-entry locks" lesson, this must ship as a **measured
  hypothesis** (does re-adding on the same line actually lose money in our population?), not bolted
  on because a YouTuber does it.

**(b) Discretionary judgment, not automatable as stated:**
- "3+ weeks of line maturity" and "6+ candles between taps" are calibrated for a 4H swing
  timeframe. Applied literally to 5m 0DTE bars they'd require a line to mature over months of
  intraday bars — nonsensical for a same-day-expiry instrument. Any adoption requires an explicit,
  pre-registered rescaling assumption (e.g., preserve the *ratio* of touch-spacing to intended hold
  time), not a literal copy of the numbers. That rescaling choice is itself a judgment call this
  research cannot make for you.
- The 45°-slope-over-3-months constraint is calibrated to how a slope "looks" on a specific chart
  zoom — an inherently visual/discretionary calibration, not something with an obvious 5m
  equivalent.
- Multi-timeframe top-down bias confirmation (daily/weekly trend, then 4H execution) doesn't map
  cleanly onto a same-day 0DTE decision cycle where there's no "daily bias, weekly holding period."

**(c) Marketing / no method behind it:**
- The volume-confluence claim — unclear if it's actually hers or SEO-page padding (Phase 2). Do not
  build on it without finding a primary-source confirmation.
- The broader brand promise ("simple," "no indicators," "$100K/year," "$526,454 from one boring
  strategy") is standard trading-influencer marketing language, not a testable claim, and is
  layered on top of the contested track-record question in Phase 3.

### 4. Recommendation

**Not a dead end, but also not a discovery.** The one idea worth a frozen prereg is narrow: test a
trendline-derived (opposing-line-projection) dynamic stop against the current exit doctrine, scoped
to existing `trendline_rejection` fires in the 391-day population, per OP-16's eval-first gate
(`analysis/recommendations/{rule_id}.json` A/B scorecard before any ratification). Everything else
here either (a) confirms our existing bear-side detector already implements the same general
pattern independently, or (b) doesn't survive the swing-futures-to-0DTE-options translation without
a judgment call this document can't make. Do not adopt her specific numeric parameters (6 candles,
3 weeks, 45°) directly — they're tuned for a different timeframe and a different instrument. Given
the unresolved, specific doctored-statement allegation in Phase 3, this is also not a source to
cite as validating evidence for any trendline approach — treat it as method inspiration only, not
as a track record to lean on.

---

## Sources

Identity: [X/@toritrades](https://x.com/toritrades?lang=en) · [Instagram](https://www.instagram.com/tori.trades/) ·
[TikTok](https://www.tiktok.com/@tori.trades) · [YouTube](https://www.youtube.com/@ToriTrades) ·
[TradingView profile](https://www.tradingview.com/u/Tori-Trades/) · [LinkedIn](https://www.linkedin.com/in/toritrades/) ·
[toritradez.com](https://toritradez.com/)

Method: [TradeZella summary](https://www.tradezella.com/strategies/trendline-strategy) ·
[ChartFanatics summary](https://www.chartfanatics.com/strategies/trendline-strategy) ·
[FX Replay summary](https://fxreplay.com/strategies/tori-trades-trendlines-strategy) ·
[TabCut interview writeup](https://www.tabcut.com/blog/post/trading-simple-trend-line-strategy-made-her-100k-a-year) ·
[nifin007 TradingView script](https://www.tradingview.com/script/1qkEcoEp-Tori-Trades-Trend-Line-System/) ·
[free PDF checklist (unparsable, existence/URL only)](https://cdn.prod.website-files.com/668852f921e36c3365b91d03/6851a0c6c14969d9b98520a2_Tori%20Trades%20Trendlines.pdf)

Reputation: [Trustpilot — toritradez.com](https://www.trustpilot.com/review/toritradez.com) ·
[A1 Trading review](https://www.a1trading.com/is-tori-trades-a-legit-trader-find-out-here/) ·
[beststockstrategy.com critical review](https://beststockstrategy.com/tori-trades-review/) ·
[ScamAdviser check](https://www.scamadviser.com/check-website/tori-trades.thinkific.com) ·
[The Day Trading Show ep. 092](https://open.spotify.com/episode/3Nsf1xa04RbljF0Nq0HMdK) ·
[Whop accelerator listing (removed)](https://whop.com/marketplace/toritrades-accelerator/)

Internal (Project Gamma): `analysis/deep-research/EOD-2026-08-06.md` ·
`analysis/deep-research/EOD-2026-08-06-FULL-REVIEW.md` ·
`analysis/deep-research/EOD-2026-08-06-INSTRUMENTS.md` ·
`analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md` ·
`backtest/lib/filters.py` (lines 601, 944-971) · `backtest/lib/trendlines.py`
