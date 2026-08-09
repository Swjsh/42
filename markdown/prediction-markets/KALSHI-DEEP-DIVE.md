# Kalshi — the full deep dive

> **Researched 2026-08-09.** Fee formulas verified against two independent sources; market
> structure, categories and spreads pulled live from the public API. Nothing armed, no account,
> no orders, no money moved.
>
> **Tools:** [`kalshi_economics.py`](../../research/kalshi/kalshi_economics.py) (unit economics) ·
> [`kalshi_liquidity_survey.py`](../../research/kalshi/kalshi_liquidity_survey.py) (venue recon)
>
> **Boundary:** this is venue mechanics and sensitivity math for a system we're building. It is
> not investment or tax advice — I'm not licensed for either, and the tax section below is
> genuinely unsettled law, not a gap in the research.

---

## 0. The one-paragraph answer

Friction on Kalshi is **very low and structurally cleaner than options** — no theta, no exit cost
if held to settlement, defined max loss, and a maker fee of **0.44¢ per contract** at the money.
But **there is no leverage**: a contract costs what it costs and pays at most $1. That single fact
governs everything — **returns scale with capital, not with cleverness.** At a realistic 3-point
edge, **$100/day requires roughly $13k–$43k of deployed capital**, not $2k. Kalshi is an excellent
*research and diversification* venue and a poor *small-account income* venue. And no edge has been
demonstrated — everything below prices the **cost of trying**, not the payoff.

---

## 1. How a contract actually works

- Every contract settles at exactly **$1.00** (correct) or **$0.00** (wrong).
- It trades between **1¢ and 99¢**. **The price IS the market's probability.** 63¢ = 63% implied.
- You can buy **YES** or **NO**. Buying NO at 37¢ ≡ selling YES at 63¢ — always take the cheaper side.
- **Max loss = what you paid.** Always. No margin, no assignment, no gap risk.
- **Return if right = (1 − P)/P.**

| Buy at | Cost per contract | Pays | Return if right | Implied win rate needed |
|---|---|---|---|---|
| 10¢ | $0.10 | $1.00 | **+900%** | 10% |
| 20¢ | $0.20 | $1.00 | **+400%** | 20% |
| 50¢ | $0.50 | $1.00 | **+100%** | 50% |
| 80¢ | $0.80 | $1.00 | **+25%** | 80% |
| 95¢ | $0.95 | $1.00 | **+5.3%** | 95% |

There is no free lunch in that table — the payoff is exactly the inverse of the probability. You
make money **only** if your probability estimate is better than the market's.

---

## 2. Fees — verified, exact

```
taker fee = ceil(0.07   × contracts × P × (1−P))     ← crossing the spread
maker fee = ceil(0.0175 × contracts × P × (1−P))     ← resting on the book (25% of taker)
```
**The ceiling applies to the order total, not per contract** (this was the one detail two sources
initially disagreed on — resolved). There are **no settlement fees, no inactivity fees, no data
fees, no platform fees, and no cost to hold a position overnight.**

| Price | Taker/contract | Maker/contract | Taker as % of stake | Maker as % of stake |
|---|---|---|---|---|
| 20¢ | 1.13¢ | **0.29¢** | 5.65% | 1.45% |
| 35¢ | 1.60¢ | **0.40¢** | 4.57% | 1.14% |
| **50¢** | **1.76¢** | **0.44¢** | 3.52% | **0.88%** |
| 65¢ | 1.60¢ | **0.40¢** | 2.46% | 0.62% |
| 80¢ | 1.13¢ | **0.29¢** | 1.41% | 0.36% |

Fees peak at 50¢ (maximum uncertainty) and vanish toward the extremes.

### ⭐ The single most important design fact
**Posting (maker) instead of taking cuts required edge by 5–6×.**

| Price | Take + cross 2¢ spread | Post as maker | Ratio |
|---|---|---|---|
| 20¢ | 2.13¢ | 0.29¢ | **7.3×** |
| 50¢ | 2.76¢ | 0.44¢ | **6.3×** |
| 80¢ | 1.63¢ | 0.29¢ | **5.6×** |

**Any Kalshi lane must be a limit-order design.** A market-order bot would need several points of
edge just to reach breakeven. This is the architectural decision, made before a line of engine code.

### ⭐ You pay the fee ONCE
A contract **held to settlement pays the entry fee only** — there is no exit fee and no exit
spread. Round-tripping early pays twice. This inverts the options instinct: on Kalshi, **holding to
expiry is the cheap path**, not the expensive one.

### Order size matters — the ceiling punishes small orders
| Contracts | Fee @50¢ | Per contract | vs formula |
|---|---|---|---|
| 1 | $0.02 | 2.000¢ | **1.14×** |
| 10 | $0.18 | 1.800¢ | 1.03× |
| 25+ | — | 1.760¢ | 1.01× |

**Batch to 25+ contracts.** One-at-a-time trading pays a ~14% surcharge.

---

## 3. Breakeven — how right do we have to be?

| Price | Maker breakeven | Taker breakeven | Taker + 2¢ spread |
|---|---|---|---|
| 20¢ | 20.29% | 21.13% | 22.13% |
| **50¢** | **50.44%** | 51.76% | **52.76%** |
| 80¢ | 80.29% | 81.13% | 82.13% |

At the money a **maker needs to be right 50.44%** of the time. A **taker crossing a 2¢ spread needs
52.76%.** That 2.3-point gap is the entire strategy — and it's an *execution* decision, not a
*prediction* one. That's the cheapest edge available on this venue.

---

## 4. What it pays — sensitivity, not promise

Net EV per **$1,000 deployed**, maker fees, held to settlement. Read as *"if our estimate beats the
market by X points, we earn Y."*

| Edge | P=20¢ | P=35¢ | P=50¢ | P=65¢ | P=80¢ |
|---|---|---|---|---|---|
| 1pp | $36 | $17 | $11 | $9 | $9 |
| 2pp | $86 | $46 | $31 | $25 | $21 |
| **3pp** | **$136** | **$74** | **$51** | **$40** | **$34** |
| 5pp | $236 | $131 | $91 | $71 | $59 |
| 10pp | ~$486 | ~$274 | ~$191 | ~$148 | ~$121 |

The same edge is worth **4× more at 20¢ than at 80¢** — $1,000 buys 5,000 contracts at 20¢ but only
1,250 at 80¢, and edge is earned **per contract**. Offsetting that: cheap contracts have the worst
fee-as-%-of-stake and brutal variance (a 20¢ book loses 4 times out of 5 — a long losing streak is
the *expected* experience, not a malfunction).

---

## 5. 🚨 Capital required — the decision number

**There is no leverage.** This is the fundamental break from 0DTE options and it governs the whole
lane. Capital needed to clear **$100/day**:

| Edge | Kelly | 1 trade/day | 3/day | 10/day | 30/day |
|---|---|---|---|---|---|
| 2pp | 1/4 | $320,513 | $106,838 | $32,051 | $10,684 |
| **3pp** | **1/4** | $130,208 | **$43,403** | **$13,021** | $4,340 |
| 5pp | 1/4 | $43,860 | $14,620 | $4,386 | $1,462 |
| 10pp | 1/4 | $10,460 | $3,487 | $1,046 | $349 |
| 3pp | full | $32,552 | $10,851 | $3,255 | $1,085 |

*(Full Kelly is included only for reference — nobody should run it. Quarter-Kelly is the practical row.)*

**Read the 3pp / quarter-Kelly row.** A 3-point edge is already good — professional sports bettors
live around 2–4 points. To make $100/day off it you need **$13k (at 10 trades/day) to $43k (at 3
trades/day)**.

> **A $1–2k Kalshi bankroll is a RESEARCH account, not an income account.** Sizing it like the
> 0DTE arms would be a category error — those work on option leverage that simply does not exist here.

---

## 6. Deposits and withdrawals

**No minimum deposit. No withdrawal minimum. No monthly limit.**

| Method | Deposit | Withdrawal | Timing |
|---|---|---|---|
| **ACH bank transfer** | **Free** | **Free** | 1–3 business days (3–5 for a new account; instant once verified) |
| Debit card | ~2% fee | Free | Instant |
| Wire | Free (your bank may charge $0–30) | Free (bank may charge ~$25–30) | Same/next day — for very large sums only |
| PayPal / Venmo / Google Pay | Available | — | Instant |
| Crypto | No platform fee (gas/processor applies) | — | Chain-dependent |

**Use ACH both directions — it is free and has no limits.** Avoid debit deposits: 2% is more than a
year of maker fees. Cash balances have historically earned interest (reported on a 1099-INT).

---

## 7. 🚨 Taxes — genuinely unsettled, not a research gap

- Kalshi issues **1099-INT** (interest on cash) and **1099-MISC** (referral bonuses/credits).
- Reporting on **1099-B for event-contract trades is inconsistent/limited** — several sources say
  it is *not* issued for event contracts. **You are still legally required to report all gains.**
  Assume you will have to self-report from your own trade log.
- **Section 1256 (60/40 long/short-term) treatment is contested.** Many tax professionals argue
  contracts on a CFTC-regulated DCM qualify. But the CFTC classifies event contracts as binary
  options categorized as swaps, which may trigger the **Dodd-Frank exclusion under §1256(b)(2)(B)**
  — enacted specifically to deny such contracts 60/40 treatment. **The IRS has issued no explicit
  guidance.**

**Implication for us:** keep a complete, immutable trade ledger from trade #1 — same discipline as
`journal/trades.csv`, with the mandatory `fills` column. Do not assume favorable tax treatment when
modeling after-tax returns. **This one genuinely needs a CPA, not me.**

---

## 8. What else is tradeable — far beyond direction

Live API sample, 1,200 events across **13 categories / 500+ distinct series**:

| Category | Series | Examples |
|---|---|---|
| **Elections** | 167 | Chamber control, governor/senate races by state |
| **Politics** | 107 | Legislation, appointments, geopolitical events |
| **Sports** | 41+ | MLB/NFL moneylines, totals, first-5-innings, tournaments, retirements |
| **Entertainment** | 64 | Awards, album/film release dates, casting, collaborations |
| **Economics** | 22 | Fed decisions, fed funds path, GDP, CPI |
| **Financials** | 41 | Single-name stock ranges (AAPL, AMZN), M&A announcements |
| **Companies** | 23 | Corporate milestones, product launches |
| **Science & Tech** | 19 | FDA approvals, launches, data-center buildout |
| **Climate & Weather** | 10+ | Daily city high temps, earthquakes, climate thresholds |
| Health / World / Social / Transportation | 11 | Public-health, geopolitical, demographic |

Plus the high-frequency recurring series confirmed directly: `KXINXU` (S&P **hourly**), `KXINX`
(S&P daily), `KXNASDAQ100U` (Nasdaq hourly), `KXBTCD`/`KXETHD` (crypto daily ranges), `KXHIGHNY`
/`KXHIGHCHI`/`KXHIGHMIA`/`KXHIGHAUS` (daily temps), `KXCPIYOY`, `KXFEDDECISION`.

### 🚨 The parlay trap — a real finding
Sampling **8,000 open markets** returned only **2 distinct series**: `KXMVESPORTSMULTIGAMEEXTENDED`
and `KXMVECROSSCATEGORY` — **auto-generated multi-leg parlays that flood the listing.**

Avoid them. A parlay **compounds spread and fee across every leg** while paying a single combined
price. They exist because they're profitable for the house, and any naive "scan all markets" crawler
will drown in them. **Filter the multivariate (`KXMVE*`) series out at the data layer** or every
downstream statistic will be about parlays.

---

## 9. Where edge could plausibly come from — ranked

1. **⭐ Execution, not prediction.** Being a **maker instead of a taker** is worth 5–6× on required
   edge. It's mechanical, needs no forecasting skill, and it's available on day one.
2. **⭐ SPX/NDX hourly ranges** — a second monetization of the intraday signal Gamma already has
   real-fills validation for, with **no theta and no strike selection**. Gated on the RTH liquidity
   re-run.
3. **Weather** — free NOAA/NWS probabilistic ensembles (NBM, GEFS) vs. a retail crowd with no model.
   $0 data cost, **fully uncorrelated with equities**. Capacity-capped (~2 ATM markets/city/day).
4. **Cross-venue arbitrage vs sportsbooks** — Kalshi is an exchange (fee, no vig); sportsbooks carry
   vig. Divergence is **mechanical edge requiring zero prediction**. Least glamorous, most robust.
5. **Macro nowcasts** — Cleveland Fed inflation nowcast and similar are public and free; the scout
   layer already watches this ground.

**Explicitly not on this list:** predicting sports better than a 1¢-spread market. Those books are
tight *because* they're efficiently made.

---

## 10. Open unknowns

| Unknown | Why it matters | Cost to resolve |
|---|---|---|
| **Book depth** | A 1¢ spread on 5 contracts isn't tradeable. **Biggest gap.** Caps capacity. | Authed API key |
| **RTH index spreads** | Weekend sample was contaminated by absent makers | Free — re-run in RTH |
| **Maker fill rate** | The whole thesis rests on resting orders getting filled | Demo environment |
| **Tax treatment** | Changes after-tax returns materially | A CPA |

## 11. Honest bottom line

- ✅ Friction is **low** and structurally **cleaner than options** — no theta, no exit cost, defined risk.
- ✅ Legally clean: CFTC-regulated exchange, not an offshore book.
- ✅ Genuinely 24/7, genuinely diversifying, with a demo environment supporting the full ladder.
- 🚨 **No leverage** — returns scale with capital. $100/day is a **$13k–43k** proposition at a good edge.
- 🚨 **No edge demonstrated.** Everything above prices the **cost of trying**, not the payoff.
- 🚨 **Capacity is the binding constraint**, and it is still unmeasured.
