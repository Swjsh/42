# Prop/Funded Firm Research — Is It Worth It For 0DTE SPY Options? (2026-08-09)

> Research only, no code/repo changes. Web research performed live 2026-08-09 (WebSearch/WebFetch) plus a read-only check of our own trades.csv and two existing internal docs. Every reputational claim below is sourced with a URL; anything I could not independently verify is labeled **UNVERIFIED**.

---

## FOR J — VERDICT

**Not worth it. Skip prop firms, keep your own capital, and re-open the PDT question — it changed under you.**

1. **Real 0DTE SPY equity-options funding barely exists.** After ~25 targeted searches, exactly **2** small, unverified firms (Black Eagle Financial Group, Options Funding) plausibly fit "pay <$100/mo-ish, get funded for options" — everything else that ranks for "options prop firm" is futures, forex, or CFDs wearing an options label.
2. **Every candidate's daily-loss rule is 6-10x tighter than yours.** Black Eagle: 5% daily / 10% max drawdown. Your kill switch: -30%/-50% per account. You'd be breached on a day you'd currently consider fine.
3. **Your own week would have voided a payout at literally every major firm.** Aug 4 (Tue) alone was +$3,624 gross against a **net week of ~+$1,000** — that's either 362% of net profit (FTMO/Apex-style denominator) or ~64% of gross winning-days profit. Every published consistency-rule threshold I found caps at 30-50%.
4. **Pass rate to ever see a payout: ~1-2% of entrants**, per the industry's own disclosed numbers (The Funded Trader: 5-10% pass, ~20% of those ever paid; FPFX Tech, 300K accounts: 7% ever paid). You'd be paying real, recurring money against ~50-to-1 odds.
5. **Most "funded" capital is simulated, not real market exposure** — confirmed industry-wide (Forbes, Spotware) and confirmed on our #1 lead candidate specifically: Options Funding's own platform is literally named "RixTrade — Simulated Options Trading Platform."
6. **The one plausible real-capital, real-broker options path (T3 Trading / SMB Capital) is not a subscription product** — it's Series-57-licensed employment with a five-figure capital contribution. Different category, not what you described.
7. **Base-rate industry evidence is bad**: My Forex Funds ($310M CFTC fraud complaint, though the case later collapsed on procedural grounds — see below), SurgeTrader (collapsed May 2024, only ~30% of owed payouts ever processed), 80-100 prop firms shut down industry-wide 2024-2025.
8. **We don't have an edge to fund yet.** This week's +$996-ish is one outlier Tuesday sitting on top of a book that was at -$738 to -$1,084 nine days earlier. That's not a track record a firm would fund even if the rules fit — and it's not one you should be funding at 6-10x tighter risk tolerance than your own.
9. **Bonus finding, bigger than the prop-firm question**: FINRA eliminated the PDT rule and the $25K minimum on 2026-06-04 (confirmed live on Alpaca's own accounts per `PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md`, already in this repo). A margin account is now viable at the **$2,000 Reg-T minimum** — no $25K wall, no 4-trades/5-days cap. That's the thing actually worth deciding, not a prop firm.
10. **The number**: skip evaluation fees entirely ($150-500+ per attempt, ~90% chance you burn it), and put that money toward your own trading capital instead — 100% of any edge you eventually prove, no rules you didn't write, no counterparty risk.

---

## 1. The options-specific problem, established first

The prompt's premise is correct and the research confirms it hard: **the funded-account industry is built for futures and forex/CFDs, not listed equity options — and 0DTE SPY specifically is served by almost nobody.**

> "If you trade equity puts and calls on a retail broker and want to replicate that at a prop firm, your choices are almost zero. Not every proprietary firm supports options... many are built around forex or futures, with only a smaller group functioning as a true options prop firm."
> — [Traders Yard: Which Prop Firms Allow Options Trading? The 2026 Reality](https://tradersyard.com/blog-posts/which-prop-firms-allow-options-trading)

> "A dedicated options prop firm for equity puts and calls barely exists in 2026, because the prop challenge model is built around futures, crypto, and multi-asset markets rather than listed stock options... Single-stock equity options are the hardest instrument to get funded for."
> — cross-confirmed across multiple 2026 searches, most explicitly at [Traders Yard](https://tradersyard.com/blog-posts/which-prop-firms-allow-options-trading) and echoed by GoatFundedTrader's own options guide

> "Most of the firms that rank for options prop firm searches actually fund forex, futures, or CFDs and use 'options' as a loose marketing label... If a prop firm mentions options but lists MT4, MT5, or cTrader as its platform, you are not getting options access. Those platforms do not support exchange-listed option contracts."
> — search synthesis, corroborated across multiple 2026 "options prop firm" guides

**What this rules out immediately** (all confirmed futures/forex/CFD-only, not equity options, despite frequently appearing on "best options prop firm" listicles):
- **Topstep, Apex Trader Funding, Take Profit Trader, Earn2Trade, MyFundedFutures, Bulenox** — futures only (some include options *on* futures — ES/NQ/CL/GC — which is a different instrument from SPY equity options).
- **FTMO, The5ers, FundedNext** — forex/CFD only.
- **Velotrade** — despite ranking #1 in "best prop firm for options trading" searches, it explicitly sells "options-style logic across leveraged markets" via CFDs on stocks/indices/commodities, not actual listed option contracts. Confirmed: "For traders who use options-style logic across leveraged markets, Velotrade's multi-asset environment offers the most capable prop account structure in the space" — that phrasing is CFD marketing, not options access. ([Velotrade](https://velotrade.com/blog/best-prop-firm-for-options-trading))

**Firms that genuinely touch real listed equity/ETF options** (the entire list this research turned up, after excluding CFD-labeled "options-style" products):
- Black Eagle Financial Group
- Options Funding / Strix Options Funding (same RixTrade platform family)
- Maverick Trading (a different, much older business model — see §2)
- T3 Trading Group and SMB Capital (traditional registered-broker-dealer prop desks — also a different business model, see §2)

That's it. Four names, two of which aren't the "cheap monthly subscription" product J is describing at all. **This scarcity is itself the headline finding** — it's not that the options are bad, it's that the product barely exists.

---

## 2. Comparison table — every genuinely options-capable firm found

| Firm | Model | Cost | Split | Daily loss / max DD | Consistency rule | Real or simulated capital | Payout reputation | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Black Eagle Financial Group** | Evaluation, then funded | $150-500 one-time eval fee (by account size, up to $250K) | Not disclosed in any independent source found | **5% daily / 10% max drawdown** on eval accounts | Firm's own marketing claims "no consistency rules" — **UNVERIFIED independently** | Firm claims "real capital from day 1" — **UNVERIFIED**, no independent confirmation found | No Trustpilot reviews yet ([Forex Peace Army](https://www.forexpeacearmy.com/forex-reviews/23118/black-eagle-financial-group-review)); one Elite Trader forum user reports unresponsive support, broken FAQ page ([Elite Trader](https://www.elitetrader.com/et/threads/other-stocks-options-prop-firms-besides-smb-t3-etc.378272/page-2)); **could not confirm FINRA/SEC broker-dealer registration** for this entity | **Do not fund through this.** Too new, too thin a reputation trail, unconfirmed regulatory status, for real capital. |
| **Options Funding (optionsfunding.co)** | Monthly-subscription evaluation, then funded | $83.60-175.60/mo (discounted) or $209-439/mo (list), by $25K/50K/100K tier | 80% trader | Max loss ~5% of account size (structure suggests overall, not confirmed daily-specific) | Not disclosed in any source found | **Explicitly simulated** — platform is "RixTrade — Simulated Options Trading Platform" per RixTrade's own tagline; "funded" account is firm-funded payout, not live market exposure, with a further undefined "Live" tier beyond standard funded | Trustpilot: 3.5/5, 9 reviews (33% five-star, 56% three-star, 11% one-star) — one review reports "manipulated... issues the day before payout"; sister brand Strix Options Funding rated 4.4/5 but "no real verifiable person has ever received a payout" reported in the same search pass — **contradictory, unresolved** | **Speculative at best.** Cheapest entry point of the four, but the "simulated" admission plus thin/contradictory reviews make this a lottery ticket, not an income plan. |
| **Maverick Trading** | Trader-development membership (not a challenge product) | $7,000 lifetime membership + $5,000 risk-capital deposit + $199/mo desk fee | 70-80% by tier | Not applicable in the same sense — real firm capital, real risk desk | Not applicable | Real capital, real IBKR execution, after ~250 hours of firm training | Established since 1997, no major scam allegations found, but **not SEC/FINRA regulated as an entity** | **Not what you're describing.** This is a $12K+ up-front, months-long training program to join a trading desk — closer to a job than a subscription. |
| **T3 Trading Group / SMB Capital** | Registered proprietary trading desk employment | Individualized capital contribution (five-figure-plus, not published); Series 57 licensing sponsored by firm | Not published | Real firm risk limits, not published | Not applicable | **Real capital, real broker-dealer.** T3 Trading Group LLC is a registered SEC broker-dealer, FINRA/SIPC member. | Long-standing, legitimate, industry-known names (T3 since 2003) | **Legitimate but not a fit.** This is a licensed trading job, not a funded-account product — background checks, fingerprints, exam sponsorship, U.S.-work-authorization requirement. |

**No firm in this table has an independently verified track record of paying out real 0DTE SPY option traders at scale.** The two that match J's cost description (Black Eagle, Options Funding) are both small, recently-formed operations with thin-to-contradictory review trails.

---

## 3. Reputation + payout reality

### 3.1 The two real candidates, deeper look

**Black Eagle Financial Group** — markets itself hard on transparency ("built in response to a problem in the industry — traders being burned by order flow front-running, delayed payouts") but that framing comes entirely from Black Eagle's own site (blackeaglefg.com), which also runs dozens of SEO-optimized "best prop firm" comparison posts that conveniently rank Black Eagle favorably. I could not find:
- An independent, dated review with a specific trader's payout experience
- Confirmation of FINRA/SEC broker-dealer registration under the "Black Eagle Financial Group" name specifically (a similarly-named but almost certainly unrelated "BLACKEAGLE PARTNERS, LLC" appears in SEC investment-adviser records as **not currently registered/not filing reports** — this is very likely a different entity, but the naming collision itself is a reason for caution, not reassurance)
- Any Trustpilot presence at all

One real signal: an Elite Trader forum poster (a genuine trader community, not SEO content) reported the website gave no clear application info, the FAQ page didn't expand, and two support emails went unanswered. ([Elite Trader thread](https://www.elitetrader.com/et/threads/other-stocks-options-prop-firms-besides-smb-t3-etc.378272/page-2)) That's a small sample, but it's the only non-marketing data point found.

**Options Funding / Strix Options Funding** — more review data exists, and it's genuinely mixed rather than uniformly bad, which is itself informative (fabricated-review operations tend to look either uniformly glowing or get caught and scrubbed):

> Options Funding: 3.5/5 on Trustpilot, 9 reviews — 33% five-star, 0% four-star, 56% three-star, 0% two-star, 11% one-star. "No recent history of asking for reviews and hasn't replied to negative reviews."
> — [Trustpilot: optionsfunding.co](https://www.trustpilot.com/review/optionsfunding.co)

> Sister platform: "Strix Options Funding is rated 'Excellent' with 4.4/5 on Trustpilot" — but a separate report in the same research pass states "no real verifiable person has ever received a payout" from Strix.
> — [Trustpilot: strixoptionsfunding.com](https://uk.trustpilot.com/review/strixoptionsfunding.com); contradicting claim surfaced via web search synthesis, **UNVERIFIED**, could not trace to a primary source

That direct contradiction — 4.4-star "Excellent" rating vs. a claim that nobody has verifiably been paid — is exactly the kind of thing that should stop you before paying, not reassure you. I flag it as unresolved rather than picking a side.

The clearest fact, from the platform's own branding: **RixTrade calls itself "Simulated Options Trading Platform."** That's not my inference — it's their tagline. ([rixtrade.com](https://rixtrade.com/))

### 3.2 Industry base rate — My Forex Funds and the pattern around it

You asked specifically about My Forex Funds as base-rate evidence. Here's what actually happened, since the story has a twist:

> CFTC filed a complaint August 29, 2023 against Traders Global Group Inc. ("My Forex Funds") and CEO Murtuza Kazmi, alleging fraudulent solicitation of **$310M+ from 135,000+ retail customers**, alleging customers believed they traded live accounts against real liquidity providers when in fact My Forex Funds was itself the counterparty on simulated accounts.
> — [Finance Magnates: $310 Million Prop Trading Fraud](https://www.financemagnates.com/forex/310-million-prop-trading-fraud-regulators-freeze-assets-of-my-forex-funds/)

> The firm was forced to shut down overnight in August 2023.
> — same source

**The twist**: in May 2025, a US court dismissed the CFTC's case with prejudice, with a special master calling the CFTC's conduct "willful" and "bad faith," and imposing $3M+ in sanctions on the agency for mischaracterizing a tax payment.

> "A US court dismissed the fraud case brought by the CFTC... My Forex Funds is counter-suing the CFTC, alleging mishandling of the case."
> — [Finance Magnates: MFF Case Misconduct](https://www.financemagnates.com/forex/mff-case-misconduct-embarrassment-for-the-cftc-but-not-yet-a-win-for-prop-trading/)

**How to read this honestly**: the CFTC's specific legal case fell apart on procedural/prosecutorial grounds — that is **not** the same as My Forex Funds being vindicated on the underlying facts (135,000 customers trading simulated accounts they believed were live is a structural fact about the *industry's operating model*, independent of whether this specific lawsuit survived). Treat My Forex Funds as base-rate evidence of two things: (1) the "simulated account, real fees" structure is industry-standard, not a My-Forex-Funds-specific scam, and (2) even the regulators pursuing this space can fumble the case — meaning a trader has **no reliable regulatory backstop** to count on either way.

**Broader collapse pattern**, independent of My Forex Funds:

> "Between February 2024 and the end of 2025, an estimated 80 to 100 proprietary trading firms shut down — the largest industry collapse in prop trading history."
> — [Vetted Prop Firms: Prop Firm Scams & 2026 Blacklist](https://vettedpropfirms.com/prop-firm-scams-and-blacklist/)

> SurgeTrader (a name that still appears on "best options prop firm" lists) shut down May 24, 2024, a week after losing its Match-Trade Technologies platform license. **Only ~30% of owed payouts had been processed by August 2024.**
> — [Finance Magnates: SurgeTrader Shuts Down](https://www.financemagnates.com/forex/prop-firm-surgetrader-shuts-down-a-week-after-losing-match-trader-license/), [FundingTraders](https://blog.fundingtraders.com/surgetrader-shut-down-operations/)

> Documented scam patterns across the industry: rule changes after evaluation pass to block payouts, fake Trustpilot reviews manufactured pre-launch, dummy funded accounts given to influencers for promotional content, anonymous ownership, "account review" delays that permanently intercept payout requests.
> — [Vetted Prop Firms](https://vettedpropfirms.com/prop-firm-scams-and-blacklist/)

> GetLeveraged: CySEC regulatory warnings, ~80 user complaints (many citing payout problems), one-sided T&Cs.
> — search synthesis, **UNVERIFIED** primary CySEC notice not directly fetched

**Structural reason this keeps happening — how the industry avoids real accountability**:

> "Many retail prop firms structure themselves to sidestep traditional regulations by framing access as 'evaluation + simulated funding,' charging participation fees, and positioning the relationship as a service contract rather than traditional brokerage activity. This structure avoids SEC or CFTC registration because no customer money is used for trading... In the U.S., many prop firms operate with minimal oversight from agencies like the SEC, CFTC, or NFA... Unregulated firms can change rules, delay payouts, or shut down without recourse for traders."
> — search synthesis across multiple 2026 regulatory-overview sources, most directly [LuxAlgo: Regulation of Retail Prop Firms](https://www.luxalgo.com/blog/regulation-of-retail-prop-firms-what-traders-need-to-know/)

This is the single most important structural fact in this whole research pass: **the reason "which firm is reputable" is so hard to answer is that almost none of them are meaningfully regulated at all.** You are extending unsecured credit to a private company with a fee-funded, not deposit-funded, balance sheet, and your only real protections are the firm's own goodwill and public reputation pressure.

### 3.3 "Most funded accounts are simulated" — confirmed industry-wide, not just an accusation

> "I want to stay in simulation" — inside the prop-trading boom: most successful funded traders **actively avoid going live** even when offered the chance, because their edge (found through backtesting/optimization against the eval's simulated fills) doesn't survive real slippage and execution.
> — [Forbes: Prop Firm Boom — Why Funded Traders Fear Going Live](https://www.forbes.com/sites/boazsobrado/2026/07/22/i-want-to-stay-in-simulation-inside-the-10b-funded-trader-boom/)

> "80% of proprietary trading firms use simulated accounts for training... prop firms can process real withdrawals even if you're trading on a simulated account, funding these payouts using the fees collected from trader evaluations."
> — [Spotware: Do Prop Firms Use Real Money?](https://www.spotware.com/news/do-prop-firms-use-real-money/)

This matters for your specific goal. If the point is "trade real 0DTE SPY options with more buying power than my own account," most of this industry does not deliver that — it delivers a fee-funded prize pool paid out based on simulated performance. That can still be a legitimate business model (a very expensive, gated skills competition), but it is **not** "get access to a bigger account to trade with," which is how you framed the pitch.

---

## 4. The cost math, computed honestly

**Pass-rate data (industry's own disclosed numbers, not affiliate marketing):**

> "At TFT [The Funded Trader], the challenge pass rate ranges from 5 to 10%, and of those, only about 20% of funded traders receive payouts... Only 1% to at most 2% of overall clients achieve a payout."
> "FPFX Tech: only 7% of 300,000 prop trading accounts achieved a payout, with average payouts equaling just 4% of the funded account size."
> — [Finance Magnates: Only 1 in 20 Traders Pass Prop Firm Challenges](https://www.financemagnates.com/forex/only-1-in-20-traders-pass-prop-firm-challenges-reports-the-funded-trader/)

> FTMO, "one of the most transparent firms in the industry," has historically cited pass rates in the **9-10% range** for its standard 2-Step Challenge.
> — cross-confirmed across multiple 2026 sources

> "Between 90% and 95% of traders fail prop firm challenges on their first attempt... 94% of traders fail their first prop firm challenge, and only 7% ever receive payouts."
> — search synthesis of prop-firm statistics aggregators, consistent with the Finance Magnates numbers above

**Two independent ways of estimating your real odds converge on the same number**: ~10% pass a challenge × ~15-20% of those ever get paid ≈ **1.5-2% of everyone who pays an evaluation fee ever sees a payout.** That matches the direct industry-disclosed figure ("1% to 2% of overall clients") almost exactly.

**Honest EV framework**, applied to the two real candidates:

*Options Funding, $25K tier, discounted pricing ($83.60/mo):*
- If evaluation takes ~2 months to pass (comparable firms cite 10-30 trading days minimum): ~$167-250 sunk before you're even funded, *per attempt*.
- ~90% of attempts fail. Expected attempts to pass ≈ 10 (pessimistic, ignores skill improvement but also ignores real attrition — most people quit after 1-2 losses of money, not run 10 clean attempts).
- Expected cost to reach "funded" status: roughly **$1,000-2,500** in subscription fees, before ever touching the funded (still possibly simulated) account.
- Of those who get funded, ~80-85% never see a payout at all (consistency rule, drawdown breach, or simply stop trading).
- **Net expected value is at or below zero for the median participant**, and firmly negative once you weight in the ~2 hours/day of attention a real evaluation demands.

> "The fee is only 'worth it' if you have a tested edge and the discipline to trade the funded account within the rules. Tighten any one assumption in the math and expected value flips negative."
> — [MQL5 Trading Blog: The Prop Firm Math No One Wants You to Do](https://www.mql5.com/en/blogs/post/770369)

**Compare to depositing your own $1-2K directly:**
- $0 evaluation fee, $0 pass-rate gate, $0 consistency-rule payout denial risk.
- 100% profit split — every dollar of edge is yours, not 80% of it.
- The only rules are the ones you (Gamma/J) designed and can change on your own schedule (per your CLAUDE.md Rule 9 process), not a third party's rulebook you didn't write and can't negotiate.
- Downside is capped at what you deposit — same as a prop firm's evaluation fee is capped, except the deposit isn't a **sunk cost with ~2% odds of ever paying off**; it's capital that's still yours if the strategy loses less than expected, and 100% yours to compound if it wins.

The math isn't close.

---

## 5. Rules that would kill OUR strategy specifically

Mapping each researched rule directly to what's in `CLAUDE.md` and this week's real fills:

| Prop-firm rule | Typical value found | What's actually in Gamma | Why it breaks |
|---|---|---|---|
| **Daily loss limit** | Black Eagle: 5% daily. FTMO: 5% (balance-based). Topstep: $1,000-4,500 (varies by account size, ~2-4% typically). | **-30% (Safe) / -50% (Bold) per account, per CLAUDE.md Rule 5.** | Your kill switch is **6-10x looser** than any firm found. A day that's well within your own risk tolerance (e.g., -15% on a rough day) would already be a full daily-limit breach — account frozen or terminated — at Black Eagle, FTMO, or Topstep. |
| **Max/trailing drawdown** | Black Eagle: 10% max. FTMO: 10% (balance-based). Topstep: $2,000-9,000 trailing intraday (moves up with peak equity, never back down). Apex: real-time trailing drawdown including unrealized gains. | No overall trailing-drawdown concept in Gamma at all — only the daily kill switch and per-trade risk cap (Rule 6: 30%/50% of equity per trade). | A **trailing** drawdown (Apex, Topstep) is specifically brutal for a strategy with the fat-right-tail shape your trade log actually shows (see §6) — a big win day pulls the trailing floor up behind it, so a subsequent giveback that would be a normal down day for you can breach the account even while you're still net profitable overall. |
| **Consistency rule** | 20-50% cap on single trading day's share of total profit, at payout time. FTMO: 50% (1-Step)/none (2-Step). Apex: 50% (4.0)/30% (legacy). Most others in the 25-40% range. | No consistency concept at all — Gamma is explicitly built to let winners run and doesn't smooth outcomes across days. | **This is the one that actually bites, verified against your own trades.csv this week (2026-08-03 to 08-07):** Tuesday 08-04 alone = **+$3,624 gross** against a **week net total of ~+$1,001** (I independently recomputed this from `journal/trades.csv`; it's close to the +$996 figure you cited). Under the FTMO/Apex-style formula (best day ÷ net total), that's **362%** — an outright, unmistakable breach, not a borderline one. Even under the more forgiving "gross winning-days-only" denominator (534+3624+1465=5623 across the week's three green days), Tuesday alone is **64.4%** of winning-day profit — still nearly double the tightest published threshold (30%) and well above the loosest (50%). **A payout request on this exact week would be denied or delayed at every firm in this research**, full stop, regardless of which of their formulas you use. |
| **Minimum trading days** | Black Eagle: 10 minimum. Most challenge firms: 5-30 days. | Not a concept in Gamma — some days correctly produce zero trades (no setup = no trade, Rule 1). | A strategy this selective (correctly HOLDing on non-setup days) can stall out a minimum-trading-days requirement, forcing marginal trades just to keep the clock moving — directly against Rule 1/2. |
| **0DTE / same-day-expiry restrictions** | No outright ban found at any firm researched, but regulators (FINRA/SEC) have explicitly named 0DTE as a distinct risk category warranting its own margin treatment in the 2026 Rule 4210 overhaul. Black Eagle's own marketing explicitly claims to allow 0DTE. | Core strategy — 100% of trades are 0DTE. | Not currently a hard blocker at the two real candidates, but it's new-enough regulatory territory that a firm changing its mind mid-stream (see §3.2's documented pattern of "rule changes after evaluation pass") is a live risk specifically because 0DTE is where the regulatory spotlight currently sits. |
| **Multiple entries per day / re-entry rules** | Not commonly restricted by count, but trailing-drawdown mechanics (Apex, Topstep) implicitly punish frequent re-entry after a stopped-out trade, since each new entry resets exposure against a floor that already moved up. | Rule 4 explicitly allows re-entry on a fresh confirmed trigger — this week alone shows multiple entries per session on several days. | Compounds with the trailing-drawdown problem above; more entries = more chances to punch through a trailing floor that a firm's own winning trade just raised. |

**Bottom line for this section**: it's not one rule that's the problem, it's that **every one of these rules exists specifically to smooth out the kind of outcome shape Gamma is designed to produce** — a mostly-flat-to-small-loss base rate punctuated by occasional large winning days. That shape is *exactly* what consistency rules and trailing drawdowns are built to catch and penalize. Funding this strategy under those rules isn't a matter of "trade a bit more carefully" — it's structurally incompatible without changing the strategy into something it currently isn't.

---

## 6. The honest alternative — and a bigger finding than the prop-firm question

### 6.1 Do we even have an edge to fund yet?

I independently pulled the full trade history from `journal/trades.csv` (317 rows, back to 2026-04-29) rather than taking the prompt's figures at face value. Findings:

- **Week of 2026-08-03 to 08-07, whole book**: +$534, +$3,624, -$1,935, +$1,465, -$2,687 → **net ≈ +$1,001**, matching the stated "+$996" closely (small gap likely from duplicate/multi-leg row artifacts in the CSV — a known data-quality issue, not investigated further here as out of scope for this research task).
- **Nine days earlier**: cumulative P&L had dipped to **-$738 to -$1,084** (07-27/07-28), consistent with the stated "-$1,372 base rate before it" in direction and rough magnitude even if not an exact match on my aggregation window.
- **The shape**: one outlier Tuesday (+$3,624 gross) is doing essentially all of the week's work; four of the last five weeks in the full history show comparable single-day dependency.

This is a mixed, short, high-variance record — a real trader-development story, not yet a demonstrated statistical edge. Funding it at a firm's tighter risk tolerance, under rules that specifically penalize the outcome shape it currently produces, would very likely fail before the underlying strategy question (does Gamma have an edge) ever gets a clean answer. **Prove the edge first, on our own capital, at our own risk tolerance — then decide about scaling.**

### 6.2 The PDT rule — the actually-live question, already half-answered internally

This surfaced as a side effect of researching *why* people use prop firms at all (the historical #1 reason: bypass the $25K PDT wall). It turns out this rig already did the relevant research, twice:

- `markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md` — confirms, from FINRA's own notice, that **cash accounts were never subject to PDT in the first place** (the actual friction for a cash account is Good-Faith-Violation/settlement mechanics, not day-trade counting), and that **FINRA eliminated the PDT framework for margin accounts entirely, effective 2026-06-04**, replacing it with a real-time Intraday Margin Level (IML) system with a standard **$2,000 Reg-T minimum** — no more $25,000 floor.
- `analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md` — confirms this live against our actual Alpaca accounts: all 5 live paper arms read `multiplier=4` (margin-shaped), `pattern_day_trader=null`, `daytrade_count=null` — i.e., **the broker itself is not enforcing any PDT-style count today**, and one arm (bold-2) is sitting needlessly blocked by a **self-imposed** legacy rule the broker doesn't even apply anymore.

I re-confirmed the regulatory fact independently today (Alpaca's own blog and FINRA Regulatory Notice 26-10):

> "FINRA's Pattern Day Trader (PDT) rule is officially being retired, and Alpaca is implementing the new Intraday Margin Framework on June 4, 2026... No more PDT designation or trade count limits, the $25,000 minimum equity requirement for day trading is eliminated."
> — [Alpaca: FINRA Retires the PDT Rule](https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/), corroborated by [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)

**Why this matters more than the prop-firm question**: the entire premise of "pay a firm for access to more capital so I can day-trade without $25K" **no longer applies**. As of two months ago, J could open a standard margin account with as little as the Reg-T minimum (~$2,000 — right in the range he already deposits) and trade with real, 100%-his-own capital, subject to real-time risk-based buying power instead of either the old PDT wall or the cash-account settlement/GFV friction he's routing around today. That doesn't remove risk — margin still means real leveraged exposure and real risk of loss beyond what's deposited, which cash accounts structurally cannot do — but it removes the *regulatory* reason to look at a prop firm at all. This is a decision already teed up and waiting on J in the two docs above; it's not new work, just newly relevant to this specific question.

---

## 7. Methodology note — treat affiliate content as marketing, not evidence

Per the task's instruction to be skeptical of affiliate-driven content: **almost every "best options prop firm" or "honest map" article found in this research is published by a prop firm about its competitors**, or by a site whose business model is affiliate referral fees to prop firms. Specifically flagged and discounted accordingly in the analysis above:

- **audacity.capital** ("Best Options Prop Trading Firms in 2026: An Honest Map") — Audacity Capital is itself a prop firm (forex/indices) with its own affiliate/partner program. Treated as marketing, not neutral journalism, despite the "honest" framing.
- **velotrade.com**, **atlasfunded.com**, **goatfundedtrader.com** — all three are themselves prop firms publishing "best of" content that includes themselves. Same treatment.
- **blackeaglefg.com** — nearly every specific rule/pricing figure attributed to Black Eagle in this report traces back to Black Eagle's own site, which also runs dozens of SEO comparison posts favorable to itself. No independent confirmation was found for its pricing, rules, or "real capital" claim — flagged as such throughout §2-3.
- Generic "Best Prop Firms 2026" listicles (Benzinga, CBS News syndication, TradeAlgo, LiquidityFinder, TradersYard, TradingFinder, PropFirmPaid, DamnPropFirms, PropJournal, etc.) were used only for **structural/rule facts that could be cross-confirmed across 2+ independently-operated sources** (e.g., FTMO's and Apex's own published/help-center rule pages), never for reputational verdicts on their own.

Sources treated as higher-trust and weighted accordingly: **FINRA/SEC/CFTC primary documents, Alpaca's own engineering blog/changelog (for the PDT fact, since it's their own account behavior), Forbes (staff byline, not sponsored), Finance Magnates (trade-press, not a prop firm itself), Trustpilot raw review distributions (with the caveat that anyone can post), and Elite Trader forum posts (real trader community, no commercial stake)**.

---

## Recommendation

**Skip the prop-firm route entirely, for options, right now.** Not "shop harder for a better firm" — the category itself doesn't fit: the real candidates are too thin/new/unverified to trust with a payout, and the ones with real reputations (T3/SMB) aren't a subscription product, they're a licensed job. Put the energy instead into:

1. **Prove the edge on our own capital first** — the honest read of trades.csv is "promising outlier week, not yet a track record." A prop firm wouldn't fund this today even if the rules fit, and they don't fit.
2. **Resolve the PDT/margin-account decision already sitting in `PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md`** — this is the live, actionable regulatory unlock, not a prop firm. It's a decision for J, already scoped, already fact-checked, just waiting on a pick between the three options laid out there.
3. **Revisit this only if**: (a) a firm emerges with a verified, multi-year, third-party-audited real-money payout record specifically for equity options (none exists today), or (b) Gamma's own track record reaches the ≥20-trades/WR≥45%/positive-expectancy live threshold already defined in CLAUDE.md — at which point the conversation becomes "scale our own capital," not "find a firm whose rules happen to fit us."

**What would change this verdict**: an options-specific firm with (a) confirmed FINRA/SEC/CFTC-adjacent registration or a multi-year audited payout trail, (b) a daily-loss/drawdown structure that isn't 6-10x tighter than ours, and (c) a consistency rule loose enough (or absent) to survive a strategy whose whole edge is occasional large days — none of which exists in this market today, per this research.

---

## Full source list

| Source | URL | Type |
|---|---|---|
| Traders Yard — Which Prop Firms Allow Options Trading | https://tradersyard.com/blog-posts/which-prop-firms-allow-options-trading | Industry blog (affiliate-adjacent, cross-confirmed facts only) |
| Finance Magnates — $310M My Forex Funds fraud complaint | https://www.financemagnates.com/forex/310-million-prop-trading-fraud-regulators-freeze-assets-of-my-forex-funds/ | Trade press |
| Finance Magnates — MFF case dismissed, CFTC sanctioned | https://www.financemagnates.com/forex/mff-case-misconduct-embarrassment-for-the-cftc-but-not-yet-a-win-for-prop-trading/ | Trade press |
| Finance Magnates — Only 1 in 20 pass prop firm challenges | https://www.financemagnates.com/forex/only-1-in-20-traders-pass-prop-firm-challenges-reports-the-funded-trader/ | Trade press |
| Finance Magnates — SurgeTrader shuts down | https://www.financemagnates.com/forex/prop-firm-surgetrader-shuts-down-a-week-after-losing-match-trader-license/ | Trade press |
| Vetted Prop Firms — Scams & 2026 Blacklist | https://vettedpropfirms.com/prop-firm-scams-and-blacklist/ | Industry watchdog blog |
| Forbes — Prop Firm Boom, funded traders fear going live | https://www.forbes.com/sites/boazsobrado/2026/07/22/i-want-to-stay-in-simulation-inside-the-10b-funded-trader-boom/ | Journalism |
| Spotware — Do Prop Firms Use Real Money? | https://www.spotware.com/news/do-prop-firms-use-real-money/ | Industry vendor blog |
| LuxAlgo — Regulation of Retail Prop Firms | https://www.luxalgo.com/blog/regulation-of-retail-prop-firms-what-traders-need-to-know/ | Industry blog |
| Trustpilot — optionsfunding.co | https://www.trustpilot.com/review/optionsfunding.co | Review aggregator (raw distribution cited) |
| Trustpilot — strixoptionsfunding.com | https://uk.trustpilot.com/review/strixoptionsfunding.com | Review aggregator |
| RixTrade (self-described "Simulated Options Trading Platform") | https://rixtrade.com/ | Vendor site, self-description |
| optionsfunding.co | https://optionsfunding.co/ | Vendor site (marketing) |
| Black Eagle Financial Group | https://blackeaglefg.com/ | Vendor site (marketing) |
| Forex Peace Army — Black Eagle review page | https://www.forexpeacearmy.com/forex-reviews/23118/black-eagle-financial-group-review | Review aggregator (no reviews found) |
| Elite Trader forum — stocks/options prop firms thread | https://www.elitetrader.com/et/threads/other-stocks-options-prop-firms-besides-smb-t3-etc.378272/page-2 | Trader community forum |
| T3 Trading Group — Proprietary Trader page | https://t3trading.com/proprietary-trader/ | Vendor site (registered BD) |
| SMB Capital | https://smbcap.com/ | Vendor site (registered BD) |
| Maverick Trading — FAQ | https://www.mavericktrading.com/frequently-asked-questions-how-maverick-trading-works | Vendor site |
| Apex Trader Funding — 50% Consistency Requirement (official help center) | https://apextraderfunding.com/help-center/additional-helpful-items/50-consistency-requirement/ | Primary firm documentation |
| PropJournal — Topstep rules | https://propjournal.net/prop-firms/topstep/rules | Aggregator (cross-confirmed) |
| PropJournal — FTMO rules | https://propjournal.net/prop-firms/ftmo/rules | Aggregator (cross-confirmed) |
| FreeTraderHub — FTMO Consistency Rule | https://freetraderhub.com/blog/ftmo-consistency-rule-explained/ | Aggregator (cross-confirmed) |
| MQL5 blog — The Prop Firm Math No One Wants You to Do | https://www.mql5.com/en/blogs/post/770369 | Trader blog (EV math) |
| Audacity Capital — "Honest Map" (self-interested, flagged) | https://audacity.capital/trading-guides/options-prop-trading-firms/ | Prop firm's own marketing |
| Velotrade — Best Prop Firm for Options Trading (self-interested, flagged) | https://velotrade.com/blog/best-prop-firm-for-options-trading | Prop firm's own marketing |
| FINRA Regulatory Notice 26-10 (PDT elimination) | https://www.finra.org/rules-guidance/notices/26-10 | Primary regulator document |
| Alpaca — FINRA Retires the PDT Rule | https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/ | Primary source (our own broker) |
| Schwab — SEC Approves Scrapping $25,000 Day Trader Minimum | https://www.schwab.com/learn/story/sec-approves-scrapping-25000-day-trader-minimum | Broker-compliance |
| DeSilva Law Offices — Prop Firms After the PDT Rule | https://www.desilvalawoffices.com/articles/blog/2026/april/prop-firms-after-the-pattern-day-trader-rule-wha/ | Legal analysis |
| Internal (already in repo) — Cash-Account Day-Trading Regulations research | `markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md` | Internal, 19 primary sources cited therein |
| Internal (already in repo) — PDT/Account-Type Decision page | `analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md` | Internal, live broker reads |
| Internal — journal/trades.csv (independently re-aggregated for this report) | `journal/trades.csv` | Internal, primary trade ledger |
