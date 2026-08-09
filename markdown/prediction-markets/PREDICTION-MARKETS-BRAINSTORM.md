# The 24/7 Arm — prediction markets, sports, and what the framework actually transfers to

> **Status:** BRAINSTORM + Phase-0 recon complete. Nothing armed, nothing funded, no orders. J-gated.
> **Opened:** 2026-08-09 (Sunday 18:33 ET, weekend grind window).
> **Recon tool:** [`research/kalshi/kalshi_liquidity_survey.py`](../../research/kalshi/kalshi_liquidity_survey.py) → `liquidity-survey.json`

---

## Verdict

**Kalshi is the arm. It is a CFTC-regulated exchange with a public API, a demo environment, and
event contracts that are literally priced as probabilities — the framework transfers almost 1:1.**
Two of J's four ideas are traps and are killed below with arithmetic, not opinion.

The single highest-value idea in this document costs almost nothing:
**Gamma already produces a validated intraday opinion on SPX. Kalshi lists hourly and daily SPX
range contracts. That is a second monetization of a signal we already own — no new alpha required.**

---

## KILL #1 — Crypto casino. Arithmetic, not squeamishness.

Provably-fair casino games (dice, Plinko, crash, roulette) carry a **fixed house edge applied per
wager** — typically 1–3%. Expectation is linear: `E[total] = Σ E[each wager]`. If every wager is
−1%, the sum is −1% of lifetime volume. **No bet-sizing scheme changes this.** Martingale, Kelly,
D'Alembert, flat-betting — all reshape *variance*, none touch *expectation*. That is a theorem,
not a strategy gap.

So "Gamma plays crypto casino" builds a machine that loses a known percentage of everything it
wagers, **at machine speed, 24/7**. Gamma's core competencies — tirelessness, discipline, speed,
size consistency — all make it lose *faster and more reliably* than a human would.

The two adjacent things that are genuinely +EV, and why they still fail here:
- **Bonus / rakeback arbitrage** — real math (bonus EV vs. house-edge × rollover), but operator
  terms explicitly ban it, and the edge is contingent on a counterparty choosing to pay. That is
  the one variable no model can price.
- **Affiliate revenue** — not a bet; a marketing business. Out of scope.

Offshore crypto casinos also carry no consumer protection and non-payment on large wins is a
documented outcome. **Counterparty risk dwarfs any modeled edge.** Killed at intake under OP-16 —
there is no edge to capture.

## KILL #2 — "Find profitable sports bettors and copy them." Survivorship bias, industrialized.

This is the same failure mode that nearly shipped a $19,627 backtest winner with undisclosed
concentration (the near-miss that produced OP-20). Four independent mechanisms sink it:

1. **Survivorship at scale.** Across thousands of public bettors, a large number will show 60%+
   over 100 bets from pure chance. Screening on realized P&L selects for luck, then calls it skill.
   This is lesson-cluster **C4** verbatim, in a new costume.
2. **The tout industry is adversarial.** Documented practices: posting picks at prices nobody could
   get, deleting losers, and split-list scams (half the list told Over, half Under — one half always
   sees a genius). The data source is not merely noisy, it is *hostile*.
3. **Latency kills the edge — this is C1 in another market.** By the time a sharp's bet is visible,
   the line has moved. Their +3% at −105 becomes your −2% at −120. Copy-trading is a signal with a
   slippage problem, and **slippage is exactly where this project has learned edges die**
   ("real fills is the only WR authority").
4. **Books limit winners.** Retail sportsbooks restrict or ban winning accounts within weeks. That
   is a structural ceiling on scale that does not exist on an exchange.

### The version that is NOT a trap
If J wants to mine other bettors, **track Closing Line Value (CLV), not P&L.** CLV = did the bet
beat the market's closing price? It is the only sports metric that *forward*-predicts profit, and
it is the direct analog of "measure the mechanism, not the outcome." A bettor beating the close by
2%+ over 500+ bets is genuinely sharp; one with a hot 100-bet P&L is noise. Same bar we already
hold our own strategies to.

---

## SHIP — Kalshi. Measured, not assumed.

**Why it fits the framework we already built:**

| Gamma already has | What Kalshi needs |
|---|---|
| Probability → price → edge machinery | Same, but *simpler* — price **is** the probability, no Greeks, no theta, no strike ladder |
| Real-fills-only WR authority (C1) | Same — books are thin, simulated fills would lie louder here than anywhere |
| Per-arm kill switches + risk caps | Same |
| shadow → paper → real-fills → arm ladder | Demo API supports the whole ladder |
| **Broker-as-a-parameter seam** (futures lane, 2026-08-09) | Drop-in venue — this is why the futures design move matters |
| Structure/level reading on SPY | **Direct transfer** — Kalshi lists SPX hourly + daily range markets |

Kalshi is a CFTC-regulated designated contract market. Event contracts are **regulated derivatives,
not gambling** — which means clean 1099-B tax treatment and real counterparty protection. That is a
categorically different legal object from an offshore casino or a sportsbook.

### Phase-0 recon: measured ATM spreads (2026-08-09, Sunday evening)

Sampling discipline: **ATM band only** (mid 0.20–0.80). Deep-OTM tails are always wide and would
slander the venue — measuring them would have been the C4 error again.

| Series | What | Median ATM spread | Read |
|---|---|---|---|
| `KXNFLGAME` | NFL moneyline | **1.0c** | Tightest book in the survey, 62 of 64 markets ATM |
| `KXMLBGAME` | MLB moneyline | **2.0c** | 64 of 72 ATM — deep and live |
| `KXBTCD` / `KXETHD` | BTC / ETH daily range | **1.0c / 2.0c** | Genuine 24/7, USD-settled |
| `KXHIGHMIA/AUS/NY/CHI` | Daily high temp | **1.0–1.5c** | Tight, but only ~2 ATM markets per city per day |
| `KXINXU`, `KXNASDAQ100U`, `KXFED`, `KXCPIYOY` | Index / macro | 21–48c median | ⚠️ **See artifact warning** |

> ### ⚠️ The index numbers are a weekend artifact — do NOT read them as a verdict
> The survey ran Sunday evening with the equity market closed. Market makers pull quotes off-hours,
> so a 33–48c *median* is measuring **absent makers, not venue quality**. The corroborating detail:
> the **tightest** ATM spread on `KXINXU` and `KXNASDAQ100U` was **1.0c** — tight quotes exist even
> now. **The index series are UNJUDGED until the survey is re-run during RTH.** Reporting them as
> "BLEED" would be an unfounded claim from a known-contaminated sample.

> ### ⚠️ Depth is unmeasured — spread is only half the picture
> The orderbook endpoint appears to require auth, so **every depth cell is empty**. A 1c spread on
> 5 resting contracts is not tradeable at size. Until depth is read with an authed key, "TRADEABLE"
> means *"friction is low enough to be worth measuring properly"* — **not** "we can put money
> through it." This is the largest open unknown.

---

## Ranked lanes — by edge-per-effort, best first

**1. ⭐ SPX/NDX range contracts — second monetization of the signal we already own.**
Gamma has a real-fills-validated opinion about SPY's intraday path. `KXINXU` (hourly) and `KXINX`
(daily) pay out on exactly that view, with **no theta decay and no strike-selection problem** —
two of the three things that have historically eaten this engine's edge. Requires zero new alpha.
Gated on the RTH liquidity re-run.

**2. Weather — the only genuinely *new* alpha source here, and the cheapest.**
NOAA/NWS publish free, high-quality probabilistic ensembles (NBM, GEFS). The counterparty is a
retail crowd with no model. This is the classic "free public model vs. unsophisticated flow" setup,
it is **100% uncorrelated with equities**, and data cost is **$0**. Caveat: ~2 ATM markets per city
per day — real but **capacity-capped**, a research win before a revenue win.

**3. Sports — tradeable, but tight ≠ edge.**
1–2c spreads mean *low friction*, which is necessary and not sufficient. A 1c NFL moneyline is
tight **because it is efficiently made** — you are trading against sharp flow. Two honest routes:
- **Cross-venue arbitrage:** Kalshi is an exchange (fees, no vig); sportsbooks carry vig. Genuine
  divergences are *mechanical* edge requiring no prediction. Most promising, least glamorous.
- **A real model** — expensive, and we would be late to a crowded field.

**4. BTC/ETH daily ranges — 24/7 coverage without touching crypto spot.**
Tight, always-on, and **USD-settled regulated derivatives, not crypto** — so it does not collide
with the standing crypto-real-money refusal in the way spot would. **That boundary call is J's to
make, not mine to assume.**

**5. Overnight futures — cheapest incremental hours, lane already built.**
The MES lane already exists; extending into the Globex overnight session buys ~23h/day coverage
with no new venue, no new creds, no new doctrine.

**6. Perp funding-rate / basis carry — flagged, not proposed.**
Genuinely 24/7 and market-neutral (harvesting a structural risk premium rather than predicting).
But it needs a crypto venue with perps, which **collides directly with the crypto-real-money
refusal.** Research-only under current doctrine. Listed for completeness; not recommended now.

---

## The generalizable idea worth more than any single lane

Gamma produces **one signal** and currently monetizes it **exactly one way** (buy SPY 0DTE options).
That same signal could express through SPX 0DTE, /MES futures, SPY shares, or Kalshi range contracts
— each a different **(fee, leverage, liquidity, tax, capacity)** profile on the *same edge*.

The fleet framework already runs "same signal, different **risk** profile." This is that idea
extended across **venues** instead of sizing — and the plumbing for it already exists.

---

## The ladder — reuse, don't reinvent

Same bar as any SPY strategy. No new doctrine required:

1. **Recon** ✅ done — public-API liquidity survey, $0, no account.
2. **RTH re-run** — settles the index series. Free.
3. **Shadow** — log what a Kalshi model *would* have done vs. actual settlement. No money, no account.
4. **Demo/paper** — Kalshi demo environment; real order mechanics, fake money.
5. **Real-fills** — the only WR authority (C1). Requires a funded account.
6. **Arm** — OP-0 #1 (live money) **and** a new venue ⇒ **double-gated**, exactly like futures.

**Evidence discipline carried over verbatim:** simulated fills are **mechanism evidence, never edge
evidence.** Any Kalshi trade ledger needs the same mandatory `fills` column (`SIMULATED`/`BROKER`)
the futures lane uses, or aggregates across it will be meaningless.

---

## What needs J (and only these)

1. **Scope call** — does the project's instrument scope open to regulated event contracts? Current
   lock is *0DTE SPY + futures live-eligible, crypto paper-only*. Kalshi is a new instrument class.
2. **Account + funding** — I cannot create accounts or handle credentials. Steps 5–6 are blocked
   until J opens and funds a Kalshi account himself; keys go in the gitignored store, never tracked.
3. **The crypto-adjacency call** — are USD-settled BTC/ETH *range contracts* inside or outside the
   crypto refusal? They are regulated derivatives, not spot, but the boundary is J's to draw.

Steps 2–4 of the ladder need **none** of the above and can proceed on public/demo endpoints alone.

## Explicitly not claimed

- No edge has been demonstrated in any market here. Recon measured **friction**, not profitability.
- Index/macro series are **unjudged** (contaminated weekend sample).
- Depth is **unmeasured** everywhere — the biggest open unknown.
- One snapshot, one evening. Liquidity varies by session, event proximity, and news.
