# MICROSTRUCTURE & INFORMED FLOW — research program (order matching, absorption, forced flow, game theory)

> **Provenance:** distilled 2026-09-06 from a r/LucidProp thread ("They said I would never make it...", u/New_Variation_2548, ~190 comments, captured in full via Reddit RSS) plus a fact-check pass against Databento's pricing page the same day. The OP's *results* (one green August on a Lucid $50k flex account, calendar screenshots) are **UNVERIFIED and unverifiable** — screenshots, one month, a prop-firm sub with heavy survivorship. What is worth keeping is the **mechanism stack** the OP describes and the **reading list**, both of which are checkable against literature and data. Treat every claim below as a hypothesis with a kill criterion, per OP-33 and `GENERATIVE-LENS.md`.
>
> **Companion to [`market-structure-execution.md`](market-structure-execution.md)** (§5 order-flow proxies, §0 auction theory). That doc covers what Gamma can infer from *bars*; this doc covers what becomes testable with *trade-and-quote* data — which, as of 2026-09-06, we discovered we already have on SPY for **$0** (§2).
>
> **Why Gamma cares:** J's verified edge is levels + role-flips. The engine currently grades a level by round-number-ness, touch count, and a bar-volume absorption *proxy* (§5 there). Everything in this doc is about replacing that proxy with the real thing — and about killing the ideas that don't survive a null.

---

## 0. What the OP actually claims (the mechanism stack, stripped of fluff)

The OP trades NQ/ES, 2–3 discretionary trades per day, holds under 5 minutes, sizes 1 NQ or 6–8 MNQ by stop distance, runs a separate conservative algo across 4 other accounts. Stack, in the OP's own layering:

| Layer | OP's words | Translation into a testable object |
|---|---|---|
| **Framework** | "game theory as the basis" — informed vs uninformed flow; "if millions are using a system it must be broken or bluffed" | Classify participants by *who is absorbing whom* at a level. Crowded retail rules (ICT, fib) become the counterparty. |
| **Context** | "microstructure as the context" — learned from the CME matching engine + Larry Harris | Where in the queue/level structure the trade sits; what the matching engine does to resting vs aggressive orders. |
| **Trigger** | "forced / trapped inventory as the entry trigger"; "I trade forced flow and cascades" | A burst of aggressor volume (stop run / liquidation) *into* a level that gets absorbed by the other side. Direction = the absorber. |
| **Prerequisite 1** | "if sellers are being absorbed at a low, buyers are the informed flow" | Absorption detection from **big trades** (L1 prints), not footprint/CVD/delta/imbalance (OP explicitly rejects those). |
| **Prerequisite 2** | "reload dynamics of the aggressor" — which side keeps replenishing | Iceberg / reload detection — needs MBO (order-level) data. **We have no free MBO source → H7 blocked** (§2). |
| **Charting** | Volume-based bars only, no time charts; Bookmap = instantaneous bid/ask; "Level 2 has a lot of noise" | Sample on a volume clock; use L1 + trades, treat depth as timing nuance, not signal. |
| **Data** | Rithmic MBO via Lucid, "$30–40/mo, $13 if only CME pairs"; ATAS + Bookmap | MBO for icebergs/stop runs — OP calls this "still noise for retail, not necessarily an edge" but useful for *when* to enter/exit. **We are not buying this** (§2); the trade+quote layer beneath it we already have free. |
| **Rejected** | Options chain / GEX: "once market makers hedge, that information gets arbitraged away through the order flow" | **Direct contradiction of our W2 GEX forward-bank thesis** — see §4 H4. |
| **Learning method** | Papers + books loaded into Claude/Codex, "dissect … without all the fluff"; YouTube "leaves out the deeper stuff" | The `paper-dissect` loop in §3. |

**The one book named** (posted twice as an image): **Larry Harris, *Trading and Exchanges: Market Microstructure for Practitioners*** (Oxford University Press, FMA Survey and Synthesis Series). Zero prior mentions of it anywhere in this repo as of 2026-09-06.

**The best comment in the thread was a negative result**, not the OP's. u/hteecs, backtesting TBBO + MBO on NQ: *aggression had the most predictive power, but "by the time the aggression was observed sufficiently the price had already moved which destroyed the edge."* That is the latency-budget problem and it is the first thing any absorption/aggression study here must measure (§4 H3).

---

## 1. Skeptic pass — what survives contact with evidence

| Claim | Status | Why |
|---|---|---|
| Absorption at a level predicts a reversal in the absorber's direction | **STRONG mechanism, MODERATE evidence at our horizon** | Osler's order-book work (already cited in `market-structure-execution.md` §1.3) shows take-profit clustering *is* absorption. Short-horizon predictive power of order-flow imbalance is core microstructure (Cont/Kukanov/Stoikov 2014). Whether it survives a 1–5 min entry latency is exactly hteecs's open question. |
| Stop runs / forced flow cascade then mean-revert | **STRONG mechanism** | Osler: stop-loss clustering just past round numbers → fast moves after a break. Whether the *reversal* after the cascade is tradeable is the test. OP notes August "was good for mean reverting" — regime-dependent by his own account. |
| Informed vs uninformed flow is separable from L1 prints | **FOLKLORE as stated, STRONG as literature** | Kyle (1985), Glosten–Milgrom (1985), Easley–O'Hara PIN, Easley–López de Prado–O'Hara VPIN (2012) all model this. Retail-grade separability from big-trade prints alone is unproven. |
| Iceberg / reload detection needs MBO | **TRUE by construction** | Reload = same queue position refilled; only visible order-by-order. Our free SIP feed is trade+quote, **not** order-by-order → H7 is blocked, no free source found (§2). |
| GEX is arbitraged into order flow, no standalone edge | **UNVERIFIED — testable, and it collides with our own W2** | If true, GEX sign adds nothing *conditional on* order-flow imbalance. That is a clean incremental-information test once we hold both series (§4 H4). |
| Volume bars beat time bars for these signals | **MODERATE** | Easley/López de Prado/O'Hara argue for the volume clock; practitioner consensus agrees. Cheap to test as a sampling choice, not a strategy. |
| 88% win rate, 2–3 trades/day, one month | **UNVERIFIED, discount to zero** | A commenter's number, from screenshots. Irrelevant to the research program. |

Two honest caveats before anyone gets excited: (1) the OP is discretionary; the research below asks whether the *mechanisms* are mechanizable, which is a different and harder question; (2) **the OP trades NQ/ES and we are testing on SPY** — the instrument our live 0DTE lane actually trades, and the one we have free trade data for. The mechanisms are exchange-agnostic (both are deep, level-driven equity-index markets) but a finding on SPY is evidence about SPY, not a verified transfer from his futures results.

---

## 2. Gap map — what Gamma has vs what the stack needs

> **⚡ RESOLVED 2026-09-06 — the data blocker was never real. We already own the feed.** J ruled out any new spend ("either you find it free or it's dead"), so the futures/Databento path was dropped and the existing Alpaca key was probed instead. **Alpaca SIP returns the full consolidated tape for SPY — every individual trade AND the NBBO quote stream — on the key already in `.mcp.json`.** Verified live this session:
>
> - `GET /v2/stocks/SPY/trades?feed=sip` → per-trade price, **size**, exchange, condition codes, **nanosecond** timestamps
> - `GET /v2/stocks/SPY/quotes?feed=sip` → bid/ask **with sizes** at each update (this is what makes aggressor classification possible)
> - **History reaches back to at least 2016** (probed 2016 / 2021 / 2023 / 2024 / 2025 — all returned data)
> - Volume: **2,251 trades in one RTH minute** → roughly 900k trades/day. Pull sample days, not years.
>
> **Consequence:** H1–H6 below all become runnable at **$0 on the instrument we actually trade** (SPY, the live 0DTE lane) instead of on a futures proxy we'd have had to buy. No new vendor, no J decision needed. The only casualty is H7 — see the MBO row.

| Need | Gamma today | Gap | Cost to close |
|---|---|---|---|
| Trades + quotes (the absorption inputs) | ✅ **HAVE IT** — Alpaca SIP `/trades` + `/quotes` on SPY, existing key, back to 2016 | none | **$0.** Write a fetch+cache tool alongside the existing OPRA fetchers. |
| Same, on futures (ES/NQ/MES) | `backtest/data/futures/MES_1m_continuous.csv` — bars only | No trade-level futures data | Would cost money (Databento). **DROPPED per J 2026-09-06.** SPY is the live instrument anyway; ES and SPY track each other closely enough that mechanism findings transfer. |
| MBO (order-by-order) for icebergs / reloads | none | **SIP is trade+quote, NOT order-by-order** — it cannot show queue refills | No free source found. **H7 is BLOCKED, not queued.** Honest read: the OP himself calls MBO "still noise for retail, not necessarily an edge," so this is the cheapest thing on the list to give up. |
| Live L1 for the futures tick | Alpaca REST bars + TradingView CDP (`MES_5m_live.csv`) | No live prints | Out of scope until a backtest earns it (futures plan §5 rule). |
| A validated absorption *proxy* from bars | `market-structure-execution.md` §5 "high volume + narrow range at a level" — **never calibrated against real absorption** | Unknown precision/recall | Free once trades data exists (§4 H6). This is the highest-leverage item: it upgrades an input the engine already uses. |
| Reading base | Auction theory + Osler in `market-structure-execution.md` | No Harris, no Kyle/Glosten–Milgrom/VPIN, no CME matching-engine docs | $0, subscription-only LLM time (§3). |
| GEX series | `Gamma_CboeOiBank` forward-banking daily since 2026-06-22 (backlog W2) | Nothing to test it *against* yet | H4 needs the futures trades data + this archive — both are on the path. |

**No decision owed to J any more.** The Databento question is closed: J ruled out new spend 2026-09-06, and the SIP probe made it moot. Everything below runs on the existing key. **Nothing in this doc costs money.**

---

## 3. Reading ladder + the paper-dissect loop ($0, subscription only)

Order matters: mechanism first, then models, then the exchange's own rules. Every item ends with the *one question it must answer for us*.

1. **Harris, *Trading and Exchanges* (2003).** The OP's only named source. Read for: trader taxonomy (informed / uninformed / liquidity / parasitic), how order-driven markets match, why stop orders create cascades, what "front-running the uninformed" looks like in a book. *Question for us: which of Harris's trader types is the counterparty at J's flipped levels?*
2. **Osler — already in §1.3 of the companion doc.** Re-read with the absorption lens. *Question: does take-profit clustering explain the absorption we think we see in bar proxies?*
3. **Kyle (1985) "Continuous Auctions and Insider Trading"; Glosten–Milgrom (1985).** The informed-flow models. *Question: what observable does informed flow leave in prints at a 1–5 minute horizon?*
4. **Easley, López de Prado, O'Hara (2012) "Flow Toxicity and Liquidity in a High-Frequency World" (VPIN).** Volume-clock sampling + bulk classification of buy/sell volume. *Question: is VPIN on MES a usable regime input, and does volume-clock sampling sharpen H1–H3?*
5. **Cont, Kukanov, Stoikov (2014) "The price impact of order book events."** Order Flow Imbalance (OFI) as a linear short-horizon predictor. *Question: what is the OFI-to-price lag on ES/NQ, and is it longer than our execution latency?* (This is hteecs's failure mode made quantitative.)
6. **Bouchaud, Bonart, Donier, Gould, *Trades, Quotes and Prices* (2018)** and **Gould et al. (2013) "Limit order books" survey.** The empirical regularities: square-root impact, order-flow autocorrelation, queue dynamics. *Question: which regularities hold at MES tick size / queue depth?*
7. **CME Group — Globex matching algorithms and the MDP 3.0 MBO spec.** ES/NQ are widely documented as FIFO ("F" algorithm) — **UNVERIFIED here: the CME page timed out on 2026-09-06; confirm before citing.** Also read CME's iceberg (display-quantity) order rules. *Question: what does a reload look like on the wire, exactly?*
8. **Prop-firm / Rithmic MBO specifics** — only if we ever trade a funded account; irrelevant to the research.

**The paper-dissect loop** (what the OP does with Claude/Codex, made repeatable): for each item → (a) one-page mechanism summary, no jargon; (b) the *observable* it predicts at our horizon and on our data; (c) one falsifiable hypothesis with a kill criterion; (d) append to §4 below, never a new file. Run it on the subscription; no API spend. A `paper-dissect` skill is worth writing only after the loop has been run by hand twice and the template is stable (CLAUDE.md §3: repeated question → instrument).

---

## 3b. "Game theory" — what the OP's core comment actually decomposes into

J flagged this comment as the one to dig into (2026-09-06). Quoted in full for provenance:

> "i divide the market into informed and uninformed flow, basically buyer flow and seller flow. anyone could be either. at an area of interest, i observe how the two interact with each other. if sellers are being absorbed at a low, i'd categorize the buyers as the informed flow since they're the ones doing the absorbing. that's my first prerequisite. this is just the tip of the iceberg, though, and absorption keeps happening everywhere. the way i differentiate which absorption is actually worth trading is a bit more nuanced. for that, i observe the reload dynamics of the aggressor and pick the side that appears to have the stronger edge, provided the threshold is good enough for me to take the trade."

**It is not a strategy; it is three measurements and a threshold.** Written as quantities we can compute from prints + book at a level *L*:

| # | OP's phrase | Quantity | Data needed |
|---|---|---|---|
| Q1 | "sellers are being absorbed at a low" | **Absorption ratio** at L: aggressor volume hitting the bid ÷ downward price progress (ticks) over the touch window. High volume, ~zero progress → absorbed. Sign tells you *who* is informed (the passive side). | trades + L1 (`tbbo`) |
| Q2 | "reload dynamics of the aggressor" | **Aggressor persistence**: after each absorbed burst, does the *same* side come back (burst count, inter-burst interval, size trend)? A side that keeps reloading and keeps getting absorbed is the losing side of a war of attrition. | trades (bursts); `mbo` if you want to see the *passive* side's queue refills too |
| Q3 | "pick the side that appears to have the stronger edge" | **Relative persistence**: passive refill rate at L vs aggressor reload rate. The side whose supply outlasts the other's demand is the one to trade with. | `mbo` for refills, trades for reloads |
| T | "provided the threshold is good enough" | A cutoff on Q1×Q3 (and, for us, a latency budget — §4 H3). | — |

**Why he calls this "game theory" and not "order flow":** each of Q1–Q3 is a *strategic interaction*, not a statistic about price. Absorption is one player revealing it is willing to hold a price; reloading is the other player testing whether that willingness is real or a bluff; the level breaks when the passive side runs out of ammunition (or was bluffing with icebergs that stop refilling). The literature has exact models for every piece:

**Game-theory reading ladder** (citations from memory of the standard literature — **verify each before quoting a result**; the works themselves are canonical):

1. **Kyle (1985)** — the informed trader's problem *is* a game: trade size chosen against a market maker who infers from order flow. Q1's "who is informed" is Kyle's λ in reverse.
2. **Glosten–Milgrom (1985)** — sequential-trade game; the spread exists because the market maker loses to informed flow. The spread and its behavior at L are a direct read on how informed the counterparty thinks the flow is.
3. **Parlour (1998) "Price Dynamics in Limit Order Markets"** and **Foucault, Kadan, Kandel (2005) "Limit Order Book as a Market for Immediacy"** — the *queue* is a game: join the queue (passive) vs cross the spread (aggressive), conditional on what everyone else does. Q3 (refill vs reload) is this game observed live.
4. **Roşu (2009) "A Dynamic Model of the Limit Order Book"** — equilibrium of patient vs impatient traders; predicts when the book thins and price jumps. Reload exhaustion → break is this model's prediction.
5. **Brunnermeier & Pedersen (2005) "Predatory Trading"** — *forced* sellers (liquidations, stop-outs) are prey; informed players front-run then provide liquidity. This is the OP's "forced flow and cascades" with a model attached: the absorber at the low after a cascade is the predator finishing the trade.
6. **Osler (2003) "Currency Orders and Exchange Rate Dynamics"** — stop clustering just past round numbers is why the cascade is *predictable* in location. Already in the companion doc §1.3.
7. **Foucault, Pagano, Röell, *Market Liquidity: Theory, Evidence, and Policy* (2013)** — the textbook that ties 1–5 together. Read after Harris, before the papers, if a single unified treatment is wanted.
8. **The crowding argument** ("if millions are using a system it must be broken or bluffed") is a coordination-game claim: a public rule with predictable orders becomes the counterparty's information. Osler's evidence *is* the proof for stops; for ICT/fib-style rules it is folklore until someone measures order clustering at those prices. Cheap test for us: does volume cluster at "retail" levels (equal highs/lows, fib retracements) beyond round-number clustering? If yes, those are additional stop pools to grade.

**What this adds to §4:** H1 = Q1 alone. H2 = Q1 after a cascade (Brunnermeier–Pedersen). **H7 = Q2/Q3, and it is the only hypothesis that needs MBO** — the OP is explicit that Q2/Q3 is what separates tradeable absorption from the "absorption that keeps happening everywhere." So if H1 survives but produces too many signals, H7 is the filter, and that is the point at which the MBO pull becomes worth its cost. Until then it stays last.

---

## 4. Hypotheses — ranked by (value to the live edge × testability × cost)

Every one gets the standard bar: real fills where applicable (C1), the **direction-controlled null** (`STRATEGY-BACKLOG.md` 5b — random bars, side = the bar's own direction), IS/OOS split, multiple-testing haircut, and a stated latency budget. None of these is a strategy; they are **inputs** to the level-grading and entry-timing the engine already does.

### H6 (first, because it needs the least and upgrades an existing input) — Calibrate the bar-level absorption proxy against real absorption
- **Claim:** "high volume + narrow range at a graded level" (companion doc §5) actually corresponds to aggressor volume being absorbed by resting size.
- **Data:** Alpaca SIP SPY trades + quotes on days the engine already has graded levels for. Same instrument, no proxy, no scaling.
- **Test:** label each level-touch bar with true absorption (aggressor volume at the level ÷ price progress); measure precision/recall of the bar proxy; find the proxy threshold that maximizes agreement.
- **Kill:** proxy AUC < 0.6 against the true label → stop calling it absorption in the engine; downgrade the lever.
- **Payoff even on failure:** we learn whether an input the engine trusts today is real.

### H1 — Absorption-then-reversal at graded levels

> ## ⚠️ RESULT 2026-09-07 — H1 at PD-levels: NO EDGE at this sample. H6: the bar proxy is a COIN FLIP.
> 176 PDH/PDL/PDC touches on the 20 cached sessions (HOLD 30 / BREAK 65 / NEITHER 81), 8 tape features × 2 windows vs a 600-draw direction-controlled null. Two 60s cells nominally clear (absorption_ratio 0.573 vs 0.523; big_print_share 0.613 vs 0.564) but n_HOLD=30, 18 comparisons, neither survives at 300s, and **tercile 30-min returns are all within ±3 bp and non-monotonic** — no tradeable magnitude. **H6:** the engine's "high-vol + narrow-range" proxy scored **AUC 0.492** for HOLD vs BREAK and correlates 0.12 with real absorption. It is doctrine prose only (not wired in `filters.py`/`level_strength.py` — verified), so nothing live is affected; **do not wire it.** → `analysis/recommendations/h1-absorption-at-levels.json`.
>
> ## ✅ THE ONE THAT SURVIVED — big-print alignment before the engine's OWN entries (edge-capture, OP-16)
> Different question, same tape: for the engine's 590 covered trades (2026-04-29→09-04), does the 5 min of tape BEFORE entry separate winners from losers? Feature that survives: **`big_share_300s` = signed volume of the window's top-5%-size prints, aligned to trade direction, ÷ big-print volume.** Plain signed flow (`sv_share`) and the last-5-min return sign do NOT survive — it is specifically the *large* prints that carry it, which is the OP's "big trades, not CVD" claim.
>
> | Setup | n | AUC | within-day null 95th | p (within-day perm) | tercile mean $ (low→high) | top-tercile $ / total $ |
> |---|---|---|---|---|---|---|
> | BULLISH_RECLAIM | 337 | **0.670** | 0.658 | **0.011** | −6 / +4 / **+54** | 6,131 / 5,880 |
> | BEARISH_REJECTION | 136 | **0.651** | 0.634 | **0.011** | −22 / −38 / **+67** | 3,082 / 361 |
>
> **In both setups the top tercile is the entire profit; the bottom two are flat-to-negative.** Null used is a *within-day* label permutation (2,000×), which preserves day clustering exactly — this matters because winners are day-concentrated (top-5 days = 60–65% of winners, C4) and the between-day rho is large (+0.33 / +0.51). The signal survives *inside* days. Two independent setups at p≈0.01 each; 8 cells in the re-check, 24 in the original.
>
> ## ⚠️ INDEPENDENT SAMPLE 2026-09-07 — does NOT replicate as a general property. DOWNGRADED to "weak / likely conditional-population artifact".
> J's 564 real-money SPY/SPX RTH trades (2021-06→2023-10, 221 days, SPY tape as proxy for SPX, 100% coverage): `big_share_300s` **AUC 0.521 overall (p=0.077), 0.514 on 1–2 lots, 0.486 on bull (null)**. Only a faint bear-side echo: **bear n=272 AUC 0.558, p=0.005** — same direction as the engine's bearish cell, but AUC 0.56 across ~30 searched cells is not a filter. Side note, not a lead: J's 0DTE entries did better when the last 5 min already moved his way (`ret_sign_300s` AUC 0.549, p=0.007) — i.e. the VWAP-aligned-continuation doctrine, already known. Leak check on the engine sample passed (entries stamped at the 1-min heartbeat, median 8s; window ends pre-fill). **Decision: no shadow-gate build; parked.** Re-open only if the live engine sample doubles and the bearish cell holds. → `analysis/recommendations/h-edge-capture-jreal.json`.
>
> **Status (superseded above): FORWARD-VALIDATE, not ship.** Owed before any gate: (a) live shadow ledger of `big_share_300s` at every real entry (Alpaca `/trades` last-5-min pull at decision time, ~3s, $0); (b) an independent sample — replay tape around J's real-money historical trades if timestamps exist; (c) single-regime + paper-fill caveats. Artifacts: `h_edge_capture_tape.py`, `h_edge_capture_dayclustered.py`, `analysis/recommendations/h-edge-capture-{tape,dayclustered}.json`.

- **Claim:** at a level, a cluster of large aggressive prints with no price progress predicts a move in the absorber's direction over the next 5–15 minutes.
- **Data:** SIP SPY trades + quotes. Classify each print as buyer- or seller-initiated (Lee-Ready: compare trade price to the prevailing NBBO midpoint). Big-trade threshold set by percentile of the day's print sizes, not a fixed number.
- **Test:** event study on next-N-minute signed return vs matched non-absorption touches of the same level class. Direction-controlled null.
- **Kill:** no excess return beyond the null at *any* N in 1–15 min, or excess that vanishes with a 30-second entry delay.

### H2 — Forced-flow cascade → snap-back
- **Claim:** a burst of aggressor volume through a level (stop run) that is then absorbed produces a tradeable reversal; without absorption it continues.
- **Data:** same as H1, plus level breaks from the existing level refresher.
- **Test:** two-way split: cascade+absorbed vs cascade+not-absorbed. The *difference* is the signal, not the cascade.
- **Kill:** the split does not separate outcomes beyond the null, or only separates in one regime (OP admits August was mean-reverting — regime-tag every day).

### H3 — OFI / aggression as a predictor *net of latency* (the hteecs test)

> ## ❌ RESULT 2026-09-06 — **DEAD, and for a stronger reason than latency.** Ran on 20 SPY sessions (2026-08-10 → 09-04), ~9.6M real trades, 16,800 observations, $0. Artifacts: `analysis/recommendations/h3-ofi-latency.json`, `backtest/autoresearch/h3_ofi_latency.py`.
>
> **Order-flow imbalance has no forward-predictive power over SPY returns at ANY tested delay — including zero delay.**
>
> | | correlation with forward return |
> |---|---|
> | Best of all 40 cells (abs) | **0.064** |
> | Median of all 40 cells (abs) | **0.026** |
> | At 0s delay, 60s lookback, 1m horizon | **0.0018** |
>
> Grid was pre-registered, not swept: 2 lookbacks (60s, 300s) × 4 horizons (1/5/15/30 min) × 5 delays (0/5/15/30/60 s). All 40 cells reported, none cherry-picked.
>
> **The latency framing turned out to be the wrong question.** hteecs's report was that aggression predicted price until execution delay ate it. On SPY we never got that far: at **zero** delay — instantaneous, physically impossible execution — the correlation is already ~0.002. There is no edge for latency to destroy.
>
> **PIPELINE VALIDATED before accepting the null** (`h3_sanity_contemporaneous.py`, cached tape, zero API calls). A null result is worthless if the code is broken, so we checked that the pipeline detects the one relationship that MUST exist mechanically — aggressive buying lifting price *within* its own window:
>
> | Lookback | corr(OFI, contemporaneous return) | n |
> |---|---|---|
> | 60s | **+0.305** | 105 |
> | 300s | **+0.273** | 105 |
>
> The pipeline sees the mechanical effect clearly and the forward effect not at all. **Interpretation: the information is already in the price by the time the window closes.** Order flow describes the move that just happened; it does not forecast the next one.
>
> **What is NOT trustworthy in the artifact:** the direction-controlled null ran only **1 draw/day/lookback → n=20 per cell** vs n=420 real. Null correlations swing −0.27 to +0.42, i.e. larger than the real signal purely from noise. So every `beats_null` / `stops_beating_null_after_delay_sec` verdict in the JSON headline is **unreliable and should be ignored** — the non-monotonic true/false patterns are the noise signature. The kill does not rest on them; it rests on the raw effect size being ~0 everywhere. If H3 is ever revisited, fix the null to ≥30 draws/day first.
>
> **SCOPE LIMIT — this does NOT kill H1.** The decision points were an arbitrary 15-minute clock grid (10:00–15:00 ET), so this tests **unconditional** order flow at random moments. The OP's actual claim is *conditional*: absorption **at an area of interest**. H1 tests that, and it remains open and untested.

- **Claim:** OFI (Cont et al.) predicts short-horizon price change on SPY, but the usable edge after observation-plus-execution delay is what matters. SIP quote sizes give the true OFI, not a proxy.
- **Test:** regress forward return on OFI over windows 1–60 s; then re-run with entry delayed by 5 / 15 / 30 / 60 s. Report edge *as a function of delay.* Our heartbeat is not a colocated engine — pick the delay we can actually meet.
- **Kill:** edge at our realistic delay ≤ null. This is the most likely outcome and the most important number to have on record, because it would close the "just read the order flow" idea for the engine with evidence instead of opinion.

### H4 — Does GEX add information *conditional on* order flow? (OP's claim vs our W2)
- **Claim (OP):** dealer hedging is already in the order flow; GEX sign has no incremental value. **Claim (W2 / Baltussen et al. 2021):** short-gamma regime amplifies continuation.
- **Data:** `journal/gex-archive/*-cboe.json` (banked daily since 2026-06-22) joined to SIP SPY trades on the same days. Both sides free and already on hand — **this one is runnable today.**
- **Test:** predict next-30-min continuation from OFI alone vs OFI + zero-gamma-flip side. Likelihood-ratio / incremental R². One number settles a doctrinal dispute.
- **Kill (of W2):** zero incremental information → W2 downgrades to advisory only. **Kill (of OP):** significant incremental information → OP's claim is wrong for our horizon.

### H5 — Volume-clock vs time-clock sampling
- **Claim:** H1–H3 signals are cleaner on volume bars.
- **Test:** re-run H1–H3 on volume bars sized to ~1 min of median RTH volume. Sampling choice only; no new features.
- **Kill:** no improvement in signal-to-null ratio → stay on time bars (the whole engine is time-bar native).

### H7 (BLOCKED — no free MBO source) — Iceberg / reload detection as a "who is defending" tell
- **Claim:** queue replenishment at a level identifies the informed side before the absorption is visible in prints.
- **Data:** order-by-order (MBO) feed. **We do not have one and found no free source** (SIP is trade+quote only). Parked unless H1 survives *and* produces too many signals to trade — only then is the OP's Q2/Q3 filter worth revisiting. 
- **Test:** does reload count at a level, measured *before* the big-print cluster, predict the H1 outcome? If it only confirms what prints already show, it is redundant — the OP himself calls it "noise for retail."
- **Kill:** no lead over H1's print-based signal.

**Sequencing (all $0, no gate):** **H4 first — it needs zero new data** (GEX archive + SIP, both on hand) and settles a live doctrinal dispute. Then build the SIP trades/quotes cache tool → **H6** (calibrate the proxy the engine trusts today) → **H3** (the latency kill test) → H1/H2 → H5. H7 stays blocked. Reading ladder runs in parallel on the subscription.

---

## 5. What this does NOT change

- No new signal family enters the 0DTE lane from this doc. The 0DTE lane sees bars and OPRA; the mechanisms here need prints.
- No live futures change. The futures lane stays on its simulated tick until a backtest clears the bar (`AUTONOMOUS-FUTURES-LANE.md`).
- **No vendor spend at all.** The Databento path is dropped (J 2026-09-06); everything runs on the Alpaca key we already have.
- No prop-firm anything. Lucid / Rithmic / ATAS / Bookmap are the OP's stack, not ours; they are recorded here for provenance only.

---

## Sources

- Reddit thread: https://www.reddit.com/r/LucidProp/comments/1w3ew9o/they_said_i_would_never_make_it/ (captured via RSS 2026-09-06; ~190 entries)
- Databento pricing (free credits, MBO retention): https://databento.com/pricing (read 2026-09-06)
- Harris, L. (2003). *Trading and Exchanges: Market Microstructure for Practitioners.* Oxford University Press.
- Kyle, A. (1985). Continuous Auctions and Insider Trading. *Econometrica.*
- Glosten, L., Milgrom, P. (1985). Bid, Ask and Transaction Prices in a Specialist Market with Heterogeneously Informed Traders. *JFE.*
- Easley, D., López de Prado, M., O'Hara, M. (2012). Flow Toxicity and Liquidity in a High-Frequency World. *RFS.*
- Cont, R., Kukanov, A., Stoikov, S. (2014). The Price Impact of Order Book Events. *J. Financial Econometrics.*
- Bouchaud, J-P., Bonart, J., Donier, J., Gould, M. (2018). *Trades, Quotes and Prices.* Cambridge University Press.
- Gould, M. et al. (2013). Limit order books. *Quantitative Finance.*
- Baltussen, Da, Lammers, Martens (2021). Hedging Demand and Market Intraday Momentum. *JFE.* (already cited in `STRATEGY-BACKLOG.md` W2)
- CME Group Globex matching algorithms / MDP 3.0 MBO — **page fetch timed out 2026-09-06; re-verify before citing specifics.**
