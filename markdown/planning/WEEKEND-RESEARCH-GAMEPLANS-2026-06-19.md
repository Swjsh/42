# Weekend Research → Game Plans (2026-06-19)

> Curated from 4 web-research streams (0DTE exit/regime, dark pool/order flow, AI-trading, intraday microstructure). Hard credibility filter: peer-reviewed / exchange / regulator weighted heavily; practitioner claims flagged + discounted; signal-sellers/get-rich/product-pitches rejected. The value is the FILTER — only validated, actionable, cheap items survived. Everything here corroborates this week's finding: **our edge is bearish-continuation; the leverage is exit/regime; the bounce family is dead.**

---

## The headline (what multiple independent streams + peer review agreed on)

1. **Market Intraday Momentum is the best-documented intraday-SPY edge** — and it's directionally bearish when the morning is red, independently corroborating our bearish-continuation edge. (Surfaced by 2 of 4 streams.)
2. **Dealer-gamma (GEX) is a real REGIME switch** — short-gamma days trend (our edge works), long-gamma days pin (we should abstain). Peer-reviewed mechanism. **Computable for ~$0 from the option chain we already pull** — the paid products ($100-350/mo) are not worth it.
3. **The "liquidity shelf" J saw at PML→PMH is documented microstructure** (Kavajecz & Odders-White, RFS 2004) — the level itself is the tradeable proxy; no dark-pool subscription needed.
4. **Our EMA ribbon is our WEAKEST-evidence signal** (data-snooping literature) — matches our own C28 lesson. Demote it from "edge" to "context."
5. **AI is research-staff, not trader** — every rigorous benchmark says LLM-as-trader is weak; LLM-as-adversarial-researcher + overfitting controls is the real leverage. We're shaped right; two gaps are enforcement.

---

## GAME PLAN 1 — Intraday-Momentum + Gamma regime layer  ★ highest value, NEW edge

**The find (peer-reviewed, convergent):**
- **Market Intraday Momentum** — Gao, Han, Li & Zhou, *J. Financial Economics* 2018 (SPY 1993-2013): the first half-hour return predicts the last half-hour return (R²~1.6%, sign-following Sharpe ~1.08 net of costs), and is **STRONGER on high-volatility, high-volume, and macro-news days** — exactly our conditions. The 12th half-hour (~14:30-15:00 ET) is a documented continuation entry/add window.
- **Dealer-gamma regime** — Barbon & Buraschi "Gamma Fragility" + Baltussen et al. *JFE* 2021: net-SHORT dealer gamma → end-of-day hedging amplifies the trend (continuation); net-LONG gamma → pinning/mean-reversion. CBOE's own data says don't believe the "0DTE gamma squeeze" hype, but the *regime sign* is real and complementary to VIX/IV.

**What we'd do (LEAN — two derived features, $0):**
- A daily **regime tag** written at premarket + refreshed intraday: (a) `morning_sign` = sign of open→~10:00 ET SPY return; (b) `net_gex_sign` + `zero_gamma_flip` + nearest call/put wall, computed in-house from the Alpaca SPY option chain (formula: `GEX_strike = gamma x OI x 100 x spot^2 x 0.01`, dealer long-calls/short-puts; open-source ref: Matteo-Ferrara/gex-tracker).
- Use it as a **bias gate, not a trigger**: take bearish-continuation entries when `morning_sign` is down AND we're not in a strong long-gamma pin regime; abstain (or size down) on long-gamma pin days and when fighting the morning tape. This is the principled, evidence-based version of the regime-gate already in our cook-queue.
- Validate against our real-fills backtest + anchor-no-regression before any live gating (Rule 9).

**Why it's the top pick:** new, peer-reviewed, ~$0, and it sharpens the exact edge we just confirmed. Effort: a regime-tag module + a backtest. Sources: [Gao-Han-Li-Zhou SSRN 2440866](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866), [Baltussen JFE 2021](https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598), [Barbon-Buraschi SSRN 3725454](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454), [gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker).

---

## GAME PLAN 2 — Exit refinement around the theta cliff  ★ the leverage we already named

**The find (triple-corroborated):**
- 0DTE theta decay is **back-loaded**: ~2%/hr at the open climbing past ~15%/hr after 14:00, with a sharp cliff ~15:30 ET (two independent minute-level studies agree).
- Trend-following's edge is **volatility-scaled risk management, not the entry** (Kim-Tse-Wald, peer-reviewed) + convex "let the winner run" payoff (AQR century-of-evidence). Chandelier trail belongs on the **underlying**, regime-conditional ATR multiple — never on option premium (that's the whipsaw we already killed).

**What we'd do (builds on the chart-stops win):**
- **Time-conditional exit**: replace the single 15:50 guillotine — keep the chandelier trail for positions in strong favor (let convex winners ride), but pull the exit forward to ~15:00-15:30 for any stagnant/non-favored position to step off the steepest decay. We already have the knob.
- Make the chandelier ATR-multiple **regime-conditional** (wider on high-ATR trend days, tighter on chop) instead of fixed 20%-off-HWM.
- Run the **partial-exit-vs-held-to-target A/B** from our 41-col trades.csv counterfactuals — confirm `tp1_qty_fraction 0.50` is buying reversal-protection vs quietly bleeding edge on the BEARISH_REJECTION population.

**Effort:** backtest sweeps on knobs we own (real-fills + anchor-no-regression). Sources: [Option Alpha 0DTE decay study](https://optionalpha.com/blog/0dte-options-time-decay), [Kim-Tse-Wald SSRN 2786955](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2786955), [AQR Century of Evidence](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing).

---

## GAME PLAN 3 — Signal-honesty audit (the "logic" cleanup)

**The find (uncomfortable but evidence-backed):**
- **EMA ribbon / MA-stack = our weakest-evidence signal.** Sullivan-Timmermann-White (*J. Finance* 1999) + Zakamulin (2018): MA-timing edge doesn't survive data-snooping correction / is indistinguishable from buy-and-hold. No peer-reviewed support for "ribbon" as an intraday entry. Matches our own C28 ("ribbon flip is a lagging exit").
- **Levels are real — via order-clustering, not magic** (Osler 2000/2003; Kavajecz-Odders-White RFS 2004): orders/stops cluster at round numbers + prior-day levels, creating real depth. BUT the same research shows levels are **stop-run/sweep zones** (penetrate→reverse) as much as bounce zones — so "reclaim/break = go" can be providing exit liquidity to the fade.
- **VWAP** is a real *execution benchmark* (institutional fair-value line) but "VWAP bounce" as a precise trigger is practitioner folklore; anchored-VWAP has no peer-reviewed reaction edge.

**What we'd do (logic refinement, propose-only):**
- **Demote the ribbon** from edge-originator to context/exit-timing — don't let a ribbon flip *originate* a trade (it can confirm/time one). This aligns the engine with the evidence + our own lessons.
- Treat named levels as **liquidity zones, sweep-aware** — favor the reaction *after* a sweep (penetrate-then-reclaim with confirmation) over anticipating the hold. Rank prior-day H/L/C + round numbers above PMH/PML in confidence (PMH/PML have less dedicated academic support).
- Keep VWAP as **trend-context**, not a bounce trigger.

**Effort:** doctrine/logic review (Rule 9, propose for J) + backtest to confirm demoting-ribbon-as-originator doesn't regress. Sources: [STW 1999 SSRN 65140](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=65140), [Zakamulin 2018](https://onlinelibrary.wiley.com/doi/abs/10.1111/irfi.12132), [Kavajecz-Odders-White RFS 2004](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=315660), [Osler](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf).

---

## GAME PLAN 4 — Use AI as research-staff, harder (the "how others use AI" answer)

**The find (every rigorous benchmark agrees):**
- **LLM-as-trader is weak** (StockBench ICLR'26: most LLMs can't beat buy-and-hold; FINSABER KDD'26: LLM strategies are "too passive in bull markets, too aggressive in bear" — *needs regime-aware risk controls*). **LLM-as-adversarial-researcher + overfitting controls is where the documented value is** (AlphaAgent; Anthropic's own orchestrator-worker: +90% on research breadth).
- The AI-trading *product* space is ~90% scams (CFTC formal advisory).

**What we'd do (both are ENFORCEMENT gaps, not new builds — we're already shaped right):**
- **Wire the Deflated-Sharpe / PBO promotion gate.** We BUILT the `backtest/lib/validation/` DSR/PBO lib this week but it's advisory-only. The Kitchen mines hundreds of candidates and ranks on raw Sharpe — de Prado's math guarantees that surfaces false positives. Make DSR/PBO a real gate on promotion (penalize by candidates-tried). Highest-leverage, $0, directly attacks "the 371st candidate is debt."
- **Adversarial bull/bear validation in the conductor.** Before any candidate promotes, a bull-researcher vs bear-researcher pass (TradingAgents/AlphaAgent pattern) — our conductor is already orchestrator-worker shaped; this adds the adversarial guard our swarm-decision-engine memory already wants.
- **Audit for the FINSABER signature**: is our engine systematically too passive in trends / too aggressive in chop? (That's the documented LLM failure mode; check our decisions.jsonl.)
- LLM-as-judge hygiene if we grade trades with Claude: counter position bias (judge A/B and B/A), prefer a different model family as judge.

**Effort:** wire an existing lib as a gate + an adversarial step in the conductor (both deliberate, conductor-appropriate). Sources: [StockBench arXiv 2510.02209](https://arxiv.org/abs/2510.02209), [FINSABER arXiv 2505.07078](https://arxiv.org/abs/2505.07078), [AlphaAgent arXiv 2502.16789](https://arxiv.org/html/2502.16789), [Anthropic multi-agent](https://www.anthropic.com/engineering/built-multi-agent-research-system), [CFTC advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html), de Prado [Deflated Sharpe](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551).

---

## SKIPPED AS NOISE / OVERPRICED (the filter working)

- **Paid GEX/dark-pool subscriptions** (SpotGamma/MenthorQ/Tradytics $69-349/mo) — the marginal signal doesn't survive a VIX+IV control (FlashAlpha 8yr backtest: ρ=−0.03, p=0.18); we compute the useful regime-sign part ourselves for $0.
- **DIX / dark-pool prints for intraday** — DIX is a *monthly/positional* signal (free if ever wanted for swing bias); irrelevant to 0DTE timing. "Dark pool levels" products = marketing.
- **The "0DTE gamma squeeze moves the market" narrative** — CBOE's own data: net 0DTE dealer gamma is small (balanced flow); don't build on it.
- **ADX as a trend filter** — parameter-fragile, overfitting-prone, contradictory backtests. Use MA-slope if anything, validated on our data.
- **Anchored VWAP reaction edge, NYSE TICK/breadth extremes** — practitioner-only, no peer-reviewed support. Test before trusting, don't adopt on faith.
- **tastytrade "manage winners at 50%/21DTE"** — high-quality research but SELLER-side; structurally wrong for a directional buyer (theta is our enemy, payoff is convex).
- **All AI-trading bots / signal-sellers / "copy my AI" / profit-claim influencers** — CFTC-flagged scam territory.

---

## Recommended order (if we execute)
1. **Game Plan 1** (intraday-momentum + gamma regime tag) — the standout new edge, $0, corroborates our direction. Start here.
2. **Game Plan 2** (exit refinement) — the leverage we already named, builds on the chart-stops win.
3. **Game Plan 4** (DSR/PBO gate + adversarial validation) — cheap enforcement of what we built.
4. **Game Plan 3** (signal-honesty audit) — important logic cleanup, but a Rule-9 doctrine review (J's call).

All are propose/research-first (Rule 9); none auto-ship. Each is a bounded conductor-sized track, not a framework — deliberately lean.
