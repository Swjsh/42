# External 0DTE Practitioner/Academic Landscape — Mechanism Sweep (2026-07-11)

> **Research Stream 3 of 5** (profitability deep-research, J-requested 2026-07-11). Literature/practitioner sweep — NOT a repo dig. Read-only on the repo except for this file.
>
> **Scope check performed first:** read [`markdown/0dte/playbook.md`](../0dte/playbook.md) + [`markdown/research/BACKTESTING-PLAYBOOK.md`](BACKTESTING-PLAYBOOK.md). What we ALREADY trade (not repeated below): trendline rejections + EMA ribbon flip (BEARISH_REJECTION / BULLISH_RECLAIM), VWAP morning continuation, opening-gap continuation (GAP_AND_GO), ORB retest (watch-only), level-sweep liquidity grabs, named-level second-test, overshoot/undershoot stop-hunt reversal, trendline-break-on-volume, and a VIX-level gate already wired into both ribbon setups (puts want VIX rising/>20, calls want VIX falling/<17.2). All of it is price-action/technical-analysis based. **Nothing below duplicates that.**

**Method:** WebSearch + WebFetch, 25+ queries/fetches, prioritized post-2023 sources. Every claim below is cited with a URL and a quality tag: `[ACADEMIC]` `[EXCHANGE]` `[REGULATOR]` `[VENDOR]` `[PRACTITIONER]` `[CODE]`. Vendor sources (GEX data sellers) are flagged explicitly — their mechanism explanations are used, their unverified performance claims are not.

---

## Ranking (top 3 for the 20-line summary, full detail below)

| # | Mechanism | Evidence quality | Portability cost | Verdict |
|---|---|---|---|---|
| 1 | Expected-move / VIX1D intraday-vol gate | Exchange primary data + straddle math | Free, ~0 new infra (Alpaca chain already gives ATM straddle) | **Test this first** |
| 2 | Time-of-day structure (chop windows, EOD unwind) | Practitioner-converged, thin academic backing | Free, $0 — re-slice `trades.csv` you already have | **Test this first — costs nothing** |
| 3 | Dealer GEX / zero-gamma flip | Real academic mechanism, but rigorous backtest shows it's ~redundant with VIX once controlled | Free but needs SPX chain (Alpaca doesn't have index options yet) + Black-Scholes gamma calc | Worth a bounded test, expect it to mostly restate what your VIX gate already knows |
| 4 | Charm/vanna EOD pin | Real mechanism, narrow use case | Derivative of #3 — don't build standalone | Low priority |
| 5 | Defined-risk debit spreads for small accounts | Real edge in literature, but mostly for CREDIT/range strategies, not your directional trigger style | Technically feasible (Alpaca `mleg` order class, confirmed) but real engineering lift + philosophical clash with "ride the ribbon runner" | Lowest priority, specific kill test below |
| 6 | Honest base rate (buyer vs seller P&L) | Two credible academic camps disagree; report both | N/A — context, not a knob | Reinforces what your doctrine already does |

---

## 1. Expected-move / IV-based entry gate

**Mechanism (one sentence):** The at-the-money straddle price × ~0.85 gives the market's own 1-standard-deviation expected range for the session; when that range is too narrow to clear your premium + spread cost, the day structurally can't pay and should be skipped or downsized.

**Evidence:**
- CBOE's **VIX1D** (launched April 2023, purpose-built for 0DTE) measures expected volatility for the *current* trading day only, using the SPXW strip expiring today/tomorrow, with the weighting shifting from today's expiry to tomorrow's as the 405-minute session progresses. `[EXCHANGE]` [Cboe VIX1D Dashboard](https://www.cboe.com/us/indices/dashboard/vix1d/), [methodology PDF](https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Cboe_1-Day_Volatility_Index.pdf), [Cboe explainer](https://www.cboe.com/insights/posts/what-the-vix-and-vix-1-d-indices-attempt-to-measure-and-how-they-differ/)
- VIX1D has a documented **overnight bias** — it tends to be structurally elevated at the open and decay through the day, independent of realized moves; a peer-reviewed finance journal piece analyzes causes and proposed corrections. `[ACADEMIC]` [ScienceDirect — "The daily rise and fall of the VIX1D"](https://www.sciencedirect.com/science/article/pii/S1544612324002162)
- Standard practitioner expected-move formula: `Expected Move ≈ ATM straddle price × 0.85` (the 0.85 multiplier corrects for the straddle overstating true expected absolute move). `[PRACTITIONER]` [MenthorQ — straddle to expected move](https://menthorq.com/guide/from-straddle-price-to-expected-move/), [Skavinski](https://www.skavinski.com/expected-move/)
- Intraday IV has a documented **U-shape**: spikes at the open, compresses through midday, re-expands into the close; theta decay accelerates through the compressed midday window while realized vol simultaneously drops. `[PRACTITIONER, converged across sources]` [Volatility Box — 0DTE volatility guide](https://volatilitybox.com/research/0dte-options-volatility-day-trading-guide/)

**Portability to our stack:** This is the cheapest mechanism in the whole sweep. Two implementation paths, both free:
- **Path A (zero new data):** compute the expected move directly every morning from Alpaca's own ATM SPY 0DTE call+put quotes (`get_option_chain` / `get_option_latest_quote`) — no new data source at all, just a formula on data already flowing through the account.
- **Path B (VIX1D):** pull `^VIX1D` from any free quote source (it's a standard exchange-published index; Yahoo Finance and others carry it) as a cross-check / regime label alongside the straddle number.

**Smallest testable step:** backtest a filter that skips or downsizes entries when `(ATM straddle × 0.85) / SPY price` sits below some trailing percentile, cross-checked against the 3 real-money anchor winners (4/29, 5/01, 5/04) and 4 anchor losers already defined in CLAUDE.md OP-16 — the gate must not have blocked any anchor winner, or it's miscalibrated for a trigger-based (not premium-selling) style.

**What would kill it:** if the anchor winners cluster on LOW expected-move days (i.e., some of J's best real trades happened on compressed-range days because the trigger quality mattered more than the day's total range), a blanket expected-move gate would be actively anti-edge — same failure mode as the retired `STAIRSTEP_CONTINUATION` setup (anti-correlated with J's real winners). Check this before wiring anything.

---

## 2. Time-of-day / regime structure

**Mechanism (one sentence):** 0DTE intraday structure has a repeatable shape — open-drive volatility, an 11:00 ET auction that sets the day's range, a low-activity chop window into early afternoon, a gamma-driven trend/pinning window from ~14:00, and a final-30-minute unwind as dealer hedging collapses toward zero at expiry.

**Evidence (practitioner-converged, be honest this is thinner than academic):**
- 60-minute opening range (9:30–10:30 ET) is reported by one practitioner as a stronger signal than 15/30-min windows for 0DTE entries. `[PRACTITIONER]` [Option Alpha — ORB explainer](https://optionalpha.com/blog/opening-range-breakout-0dte-options-trading-strategy-explained)
- Documented backtest: 60-min ORB → 0DTE **credit spreads**, May 2022–Aug 2025, n=661 trades, 87.0% WR, profit factor 1.3, on QuantConnect/LEAN with a caveat that "some QuantConnect stats don't account for multi-leg options positions properly." `[PRACTITIONER, self-reported backtest, not independently audited]` [Quantish — SPX opening range breakouts](https://blog.quantish.io/2025/09/09/0dte-spx-opening-range-breakouts/) — **flag:** this is a short-premium credit-spread strategy (sell the range, hold to close for theta). The high win rate / small-win-many / rare-big-loss shape is typical of short premium and does **not** transfer to your long-premium directional style — don't import the 87% number as if it applies to buying options.
- "Once the 11:00 ET auction sets the day's range, 0DTE positioning typically pulls spot back toward the middle until 14:00, then expands again as gamma hedging unwinds." Midday = lowest-activity window, OTM 0DTE options lose value fastest here. `[PRACTITIONER, converged across multiple vendor sources — treat as directional, not precise]` [FlashAlpha — SPXW 0DTE guide](https://flashalpha.com/articles/spxw-0dte-guide-same-day-sp500-options-gamma-pin-risk), [MenthorQ 0DTE gamma guide](https://menthorq.com/guide/understanding-0dte-gamma-exposure/)
- Academic partial support: liquidity providers' hedging needs and their volatility-attenuating effect are shown to vary through the session, though the paper's focus is aggregate volatility, not retail entry timing. `[ACADEMIC, working paper]` [Adams, Fontaine, Ornthanalai (2024) — SSRN 4881008](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4881008)

**Portability to our stack:** This is the **second-cheapest mechanism here — arguably cheaper than #1.** You already have `journal/trades.csv` and `decisions.jsonl` with entry timestamps in ET for every real and paper fill. No new data, no new infra.

**Smallest testable step:** bucket existing trades by ET hour-of-entry and compare win rate / expectancy per bucket. This is a pure re-slice of data you already have — the cheapest test in this entire document. If a specific hour bucket (candidate: 11:00–13:30 ET) is a clear expectancy drag across your real+paper sample, that's a evidence-backed soft gate (e.g., require higher confluence score in that window) rather than a hard block.

**What would kill it:** your setups already require a fired trigger (ribbon flip, level break, volume confirmation) — those conditions structurally don't fire often during low-activity chop, so a lot of the "avoid midday chop" benefit may already be implicit in your trigger design. If the hour-bucket re-slice shows no real difference, the mechanism is already priced in and a new gate would just be a redundant filter that costs you rare-but-real midday setups (see the NAMED_LEVEL_SECOND_TEST case study, which fired at 11:45 ET and worked).

---

## 3. Dealer gamma exposure (GEX) / zero-gamma flip level

**Mechanism (one sentence):** dealers who are net short customer options must hedge by trading the underlying in the direction that amplifies moves (short gamma, below the "flip" level) or dampens them (long gamma, above it); large open-interest strikes act as intraday magnets because that's where the heaviest hedging flow concentrates.

**Evidence — the mechanism itself is real:**
- Formula (standard, several independent sources agree): `GEX = Γ × OI × 100 × Spot² × 0.01` per contract, summed across strikes with call gamma treated as dealer-long (positive) and put gamma as dealer-short (negative) under the standard "dealers are long calls / short puts" convention — explicitly flagged by the source itself as "a crude approximation" that's better for indices than single names. `[PRACTITIONER, methodologically detailed and reproducible]` [Perfiliev — how to calculate GEX and zero gamma](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/)
- Zero-gamma/flip level = the spot price where cumulative GEX crosses zero; found by recomputing Black-Scholes gamma at multiple hypothetical spot levels and interpolating. Same source.
- CBOE's own research: 0DTE volume is now 40–50% of daily SPX options volume; dealer hedging flows can be a dominant driver of intraday price action on heavy-0DTE-OI days. `[EXCHANGE, but this specific claim traced to secondary summaries of a CBOE PDF I could not machine-extract]` [Cboe — 0DTE index options and market volatility PDF](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf) (binary PDF, could not extract full text — treat the summary as indicative, not verbatim)
- **Important tempering data point, straight from the exchange:** in CBOE's own 2026 breakdown, over 95% of all 0DTE trades are done in a limited-risk format (only ~4% naked shorts), and **dealer hedging represents just 0.2% of SPX daily liquidity** — customer flow is "extremely balanced." `[EXCHANGE, primary]` [Cboe Insights — "0DTEs Decoded"](https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact/) — this cuts directly against the more dramatic "dealer gamma controls the tape" framing sold by GEX-data vendors.
- **The single most important finding for calibrating expectations:** a vendor's own pre-registered 8-year backtest (1,972 SPY trading days, 2018–2026) found raw GEX has a real relationship with next-day realized volatility (rank correlation −0.36), but that relationship **collapses to statistical noise (−0.03, p=0.18) once VIX and ATM IV are added as controls.** Their conclusion: "most of what you see is vol-regime, not unique GEX information." `[VENDOR — but this is a company that SELLS GEX data admitting a null result against their own product once properly controlled, which makes it more credible, not less]` [FlashAlpha — 8-year GEX/DEX/VEX/CHEX backtest](https://flashalpha.com/articles/gex-dex-vex-chex-8-year-backtest-spy-vix-control)

**Why this matters specifically for us:** BEARISH_REJECTION and BULLISH_RECLAIM already gate on VIX level and direction (puts want VIX rising/>20, calls want VIX falling/<17.2). If GEX's information content is mostly redundant with VIX once you control for it — which is exactly what the FlashAlpha backtest found — then building a GEX layer risks re-deriving a gate you already have, dressed up as a new signal. **Test it as "does GEX explain variance beyond our existing VIX gate," not as a standalone correlation.**

**Portability — the free-data question you specifically asked about:**
- **Yes, computable for free**, confirmed two ways: (1) CBOE's own free delayed options-chain download (`cboe.com/delayedquote/quote-table-download`, no signup for delayed data) + `py_vollib`/`scipy` for Black-Scholes gamma — this is literally the data source the Perfiliev methodology above uses. (2) Open-source reference implementations exist: `[CODE]` [jensolson/SPX-Gamma-Exposure](https://github.com/jensolson/SPX-Gamma-Exposure) (uses free CBOE download; appears unmaintained — 27 commits, no recent activity, useful as a methodology reference not production code) and `[CODE]` [FlashAlpha-lab/gex-explained](https://github.com/FlashAlpha-lab/gex-explained) (ships a sample chain CSV + from-scratch `compute_gex.py`, explicitly "runnable with publicly available data," numpy/scipy/matplotlib only).
- **Critical instrument caveat specific to our stack:** SPX options are cash-settled, European-style, ~10x SPY's notional per contract, and have "sticky" open interest because there's no early-exercise ambiguity — this is why GEX-vendor sites treat SPX gamma as "the primary driver for index movement," dwarfing SPY. SPY options are American-style, physically settled, more retail-dominated, and the OI is less sticky — a **weaker, noisier GEX proxy** than SPX. `[VENDOR, but the mechanism logic is sound and uncontested across sources]` [GEXMetrix — SPX vs SPY vs XSP](https://www.gexmetrix.com/blog/spx-vs-spy-options)
- **We trade SPY, and our cached OPRA history is SPY-specific.** Alpaca's options API currently covers US-listed equity/ETF options only — SPX/index options are listed as "coming soon," not yet available. `[VENDOR primary — Alpaca's own docs]` [Alpaca — multi-leg options docs](https://docs.alpaca.markets/docs/options-level-3-trading) (verify current entitlement status yourself; this changes over time). **Practical implication:** if we want an SPX-quality GEX signal (the one that actually matters for index-level dealer flow), it has to come from CBOE's free delayed SPX chain download as a *separate* data pull from the Alpaca SPY execution pipeline — not from Alpaca's own chain data, which only covers SPY notional (smaller, noisier, per the point above).

**Smallest testable step:** pull one week of free CBOE delayed SPX chain snapshots at premarket (matches the existing 08:30 ET `Gamma_Premarket` level-audit cadence), compute the zero-gamma level, and overlay it against the existing `key-levels.json` + `today-bias.json` levels already drawn for that day — check purely by eye whether the flip level coincides with any levels J already trades off of, or adds a genuinely new one. Only build the full pipeline if that spot-check finds something the chart-based levels are missing.

**What would kill it:** per the FlashAlpha finding above — if a same-sample regression shows GEX/flip-level distance adds nothing once your existing VIX gate is in the model, don't ship it. That test should run BEFORE any backtest integration work, not after.

---

## 4. Charm / vanna — end-of-day pin risk

**Mechanism (one sentence):** charm (delta's sensitivity to time) and vanna (delta's sensitivity to IV) force dealers to continuously rebalance hedges even when price hasn't moved, and in low-VIX sessions this combines into a slow afternoon drift toward the strike with the largest open interest, magnetizing price into the close ("EOD pin").

**Evidence:** mechanism is well-explained and consistent across every vendor source checked (no contradicting technical claims found), but I found **no independent academic quantification** of pin magnitude or hit-rate — this concept lives entirely in practitioner/vendor content. `[PRACTITIONER/VENDOR, mechanism-consistent but no rigorous backtest found]` [SpotGamma — Vanna and Charm Explained](https://spotgamma.com/vanna-and-charm-explained/), [VannaCharmAlgo blog](https://vcalgo.com/blog/vanna-charm-gamma-exposure-gex/)

**Portability:** derivative of #3 — you need GEX-by-strike data already computed to identify the high-OI "magnet" strike. Not worth building standalone.

**Smallest testable step:** only after #3 is built, tag any trade entered in the final 45 minutes and check whether proximity to the day's peak-OI strike (once you're computing it anyway) correlates with reduced move magnitude — this is basically free once the GEX infra exists, but has zero value before then.

**What would kill it:** you already have a hard 15:50 ET time stop and no-new-entry-near-close discipline is implicit in most setups' time gates — so the addressable surface for a pin-awareness feature is narrow (mainly: "should I take this trigger at 15:20 given known pin risk" — a fairly rare decision point).

---

## 5. Defined-risk structures for small accounts (debit spreads / broken-wing butterflies)

**Mechanism (one sentence):** buying a vertical debit spread (long near strike, short further OTM strike, same expiry) or broken-wing butterfly caps both max loss and net premium paid versus a naked long, at the cost of a capped upside.

**Evidence:**
- Multi-leg structures reduce cost and cap risk versus naked options; naked short premium is explicitly called "best reserved for seasoned traders." `[PRACTITIONER]` [TradingBlock — 0DTE strategies](https://www.tradingblock.com/blog/0dte-options-strategies)
- Most of the 0DTE small-account defined-risk content that exists is about **CREDIT** structures (iron butterfly, broken-wing butterfly sold for credit) — range/mean-reversion bets that profit from settling near a center strike, sized at roughly "1 contract per $6,000 of account," with VIX-tiered width selection (10-wide under VIX 17, up to 25+-wide above VIX 32) and a hard stop at 2x credit collected. `[PRACTITIONER]` [Theta Profits — broken wing butterfly](https://www.thetaprofits.com/broken-wing-butterfly-a-high-probability-options-strategy/), [Options Cafe — 0DTE iron butterfly, "431% returns and a brutal 2025"](https://options.cafe/blog/zero-dte-spx-iron-butterfly-strategy/) (note the "brutal 2025" in their own headline — even the promotional content admits a bad regime year).
- **This is a structurally different bet than our directional trigger-following style.** A butterfly/condor profits from *staying near a strike*; our whole playbook profits from *riding a directional move* (explicit in the "ride the ribbon" runner logic — 5/04's +86% ceiling came from letting a winner run past TP1, which a capped structure would have clipped). Importing the butterfly/condor family wholesale would mean adding a genuinely new, philosophically opposite strategy — not a structural tweak to the existing setups.
- The closer analog to our style is a **debit vertical** wrapped around an existing directional trigger (buy ATM/1-OTM, sell further OTM, same direction as the trigger) — this reduces net premium and caps the −50% catastrophe-stop dollar loss further, without changing the trigger logic itself.
- **Execution cost reality check:** SPX ATM 0DTE options trade near-penny-wide, but OTM legs — exactly where a debit spread's short leg lives — can carry bid/ask spreads of 30–50% of mid-price; "execution slippage often dominates strategy P&L" on those legs. `[PRACTITIONER, converged]` [FlyOnTheWall — SPX vs SPY 0DTE](https://flyonthewall.ai/spx-vs-spy-options/) — and our smallest account tier (OTM-3 at $1K, per the existing per-tier strike table) trades exactly the cheap, far-OTM contracts where this bites hardest.

**Portability — the execution-machinery question you specifically asked about:**
- **Confirmed technically feasible, contrary to the "no bracket support" assumption alone implying multi-leg is off the table.** Alpaca's Trading API supports a dedicated `order_class: "mleg"` for spreads/straddles/condors/butterflies, submitted as ONE atomic order (a `legs` array, up to 4 legs, each with `symbol`/`side`/`ratio_qty`/`position_intent`) — **this removes entry-leg risk entirely**, distinct from the bracket/OTO rejection you've already hit on single-leg options. `[VENDOR primary — Alpaca's own API docs, verified via two independent doc pages]` [Alpaca — Options Level 3 Trading docs](https://docs.alpaca.markets/docs/options-level-3-trading), [Alpaca support — multi-leg orders](https://alpaca.markets/support/does-alpaca-support-multi-leg-option-orders-such-as-spreads)
- **However:** bracket/stop-loss attachment to an `mleg` order is not documented as supported — consistent with the project's existing finding that Alpaca rejects brackets on single-leg options (see `project_alpaca_options_no_brackets` memory). **Exit management would need the same `exit_manager`-owns-TP/stop pattern already built for single-leg positions, extended to submit a closing `mleg` order (both legs, `*_to_close`) when the trigger fires** — this is bounded, known-shape engineering work, not a research gap. Equity/ETF options only (SPY qualifies); index options (SPX) not yet supported per the same docs.

**Smallest testable step:** replay the project's own best-documented anchor trade (5/04 SPY 721P, +86% ceiling) as a debit vertical instead of naked long, using real OPRA bid/ask on BOTH legs for an honest net debit and capped payout, and check whether the capped structure would have clipped the realized gain.

**What would kill it:** it almost certainly will clip it — that's the point of the test. An 86% ceiling is far beyond where any reasonable short-leg strike sits. If the defined-risk structure would have converted your own source-of-truth anchor win into a much smaller win, that's a direct, doctrine-relevant reason to keep it OFF the core ribbon-ride setups and, if used at all, scope it narrowly to a specific new low-conviction/high-IV setup where capping the tail is actually the point (e.g., as a stop-loss-dollar-reducer on the lowest-quality trigger tier only).

---

## 6. The honest base rate: 0DTE buyer vs seller P&L

**Reported plainly, per the request — the literature does not fully agree, and both camps are cited here rather than picking the scarier number:**

**Camp A — large, documented retail losses:**
- Beckmeyer, Branger, Gayda, **"Retail Traders Love 0DTE Options... But Should They?"** `[ACADEMIC, working paper, Lancaster Univ finance conference]` [PDF](https://wp.lancs.ac.uk/fofi2024/files/2024/04/FoFI-2024-146-Leander-Gayda.pdf), [SSRN abstract](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4404704) — retail investors lost an average **$241,000/day** over their Feb 2021–Sep 2023 sample, growing to **~$350,000/day** after CBOE launched daily SPX expirations in May 2022. Per-contract: debit trades lose **−$8.05**, credit trades make **+$4.55**. Total sample: >$70M gross losses, >$50M of that from transaction costs/spread alone. Their stated bottom line: **"0DTE options are not a lucrative investment vehicle for retail traders"** — and critically, they report **no profitable exception subgroup** (not by time of day, moneyness, or size).

**Camp B — more sanguine, losses "may be exaggerated":**
- Bogousslavsky & Muravyev, **"An Anatomy of Retail Option Trading"** `[ACADEMIC, working paper, $15B trader-level retail dataset]` [SSRN abstract](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4682388), [PDF mirror](https://www.lsu.edu/business/files/event-files/2025-finance-mardi-gras/retail_option_trading_v2.pdf) — a typical retail trade is a one-day S&P 500 index call held about an hour; losses are **"modest... compared to wide bid-ask spreads"**; they find **no evidence of positive skew** (i.e., not lottery-ticket-seeking behavior), and describe the retail base as "relatively sophisticated on average" despite heterogeneity. Their framing: concerns about retail 0DTE losses "may be exaggerated."

**Exchange's own framing (self-interested but verifiable-ish):**
- CBOE reports retail is **~50–60%** of SPX 0DTE volume, **>95%** of trades are in limited-risk format (only ~4% naked shorts), and retail participation *drops* during volatility spikes (57%→47% in one cited episode) rather than chasing them. `[EXCHANGE]` [Cboe Insights — 0DTEs Decoded](https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact/)
- A regulator's own working paper on retail's use of non-marketable limit orders in the 0DTE market found customers' costs from using limit orders (vs. marketable orders) are **low**, and retail-sized (1-2 contract) non-marketable limit orders are heavily used — a data point that cuts against the "retail always crosses the wide spread and gets fleeced" narrative. `[REGULATOR, primary — SEC DERA]` [SEC.gov paper page](https://www.sec.gov/about/divisions-offices/division-economic-risk-analysis/staff-papers-analyses/hope-reasonable-price_customer-use-limit-orders-0dte-market) (full PDF blocked by SEC's server for automated fetch — verify by downloading directly if needed)

**Why this matters for us, plainly:** every camp agrees on the mechanism that actually kills retail 0DTE buyers — spread/transaction-cost drag on undisciplined, high-frequency, low-conviction long-premium trades. **None of it describes what this project does.** We: trade off a named, evidenced trigger (not "buy calls because bullish"); use chart-stop-primary with a catastrophe premium cap (not hold-to-expiry-and-hope); validate against real J trades and real OPRA fills before shipping anything (OP-16); and measure edge_capture against anchor trades rather than aggregate win rate (OP-16, explicitly designed to avoid the exact overfitting trap this literature describes). The base rate is a reason to keep leaning on the validation discipline already in place — not a reason to add a new gate, and not something either camp's data can be read as "vindicating" us, since neither paper isolates a trigger-following cohort. Treat it as a floor to stay above, not a target to beat.

---

## Sources not otherwise cited above but checked for corroboration

- [Cheddar Flow — What Is Gamma Exposure](https://www.cheddarflow.com/blog/what-is-gamma-exposure-an-in-depth-analysis-for-traders/) `[VENDOR]`
- [InsiderFinance — Ultimate Guide to GEX](https://www.insiderfinance.io/resources/the-ultimate-guide-to-gamma-exposure-gex) `[VENDOR]`
- [GEXBoard — Gamma Flip explainer](https://gexboard.com/learn/zero-gamma-gamma-flip) `[VENDOR]`
- [Coriva — 0DTE mechanics, Greeks, P&L distribution](https://coriva.eu.org/en/0dte-options-guide/) `[PRACTITIONER]`
- Brogaard, Han, Won (2023/2024) — "Does 0DTE Options Trading Increase Volatility?" `[ACADEMIC]` [SSRN 4426358](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4426358) — found the OPPOSITE conclusion from Adams/Fontaine/Ornthanalai (0DTE volume ratio correlates with HIGHER realized vol, vs. the latter's finding of net-negative vol impact once liquidity provision is modeled). Flagged in mechanism #3 discussion as an unresolved academic disagreement — don't treat either side as settled.

---

## Bottom line for whoever reads this next

Test **#1 (expected-move gate)** and **#2 (time-of-day re-slice)** first — both are free, both use data or a formula you already have flowing through Alpaca, and #2 specifically costs nothing but a `pandas.groupby` on `trades.csv`. Treat **#3 (GEX)** as a "prove it's not just VIX again" exercise before investing build time — the best available backtest on this exact question found it mostly isn't. Deprioritize **#4** (derivative of #3) and **#5** (real mechanism, real engineering cost, and structurally in tension with the ride-the-ribbon runner thesis that produced your best anchor trade) unless a specific low-conviction setup emerges that wants capped tails on purpose. **#6** is context: the literature disagrees on magnitude but agrees on mechanism, and nothing in it describes what this project already does.
