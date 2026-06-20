# Margin, Leverage & Risk — Futures

> Sources: NinjaTrader (margin day vs overnight), Optimus Futures, AMP/QuantVPS, Britannica Money. See [SOURCES.md](markdown/futures/SOURCES.md). **Margin dollar figures change with volatility — always confirm live with the broker.** Mechanics below are stable.

## Margin is a good-faith deposit, NOT the cost of the trade

This is the single biggest mental shift from options. When you buy an option, the premium **is** your money at risk — max loss is capped at premium. When you trade a future, you post **margin**: a fraction of the contract's notional value, held as collateral. You control the **full notional** and your P&L is on the full notional. **Losses are not capped at the margin you posted.**

## The four margin numbers

| Term | What it is | Who sets it |
|---|---|---|
| **Initial margin** | Deposit required to **open** an overnight position | The **exchange** (CME). ~10% above maintenance. |
| **Maintenance margin** | Minimum equity to **keep** a position open. Drop below → margin call. | The **exchange** (CME). |
| **Day-trade (intraday) margin** | Reduced requirement to hold **during RTH only**, closed before session end | The **broker** (much lower — often a small fraction of initial) |
| **Overnight margin** | = initial margin; required to **carry past the close** | The **exchange** |

**Key rule:** day-trade margin only applies if you **close before the session-end cutoff** (≈4:45 p.m. ET for most CME contracts at NinjaTrader; varies by broker). **Hold past the cutoff and the full overnight/initial margin snaps back** — if the account can't cover it, the broker may **auto-liquidate** the position and charge fees.

> This is a *real* reason for flat-by-close (separate from options expiry): a day-margin position held overnight by accident can trigger a margin call. Our heartbeat time-stop at the close handles this once intraday trading is re-enabled.

## Typical micro margins (illustrative — confirm live)

Micro contracts (MNQ/MES) are the cheapest equity-index futures to margin:
- **Day-trade margin:** often in the low **hundreds of dollars** per contract (broker-set; e.g. ~$50–$500 depending on broker/volatility).
- **Overnight/initial margin:** **higher** — typically several hundred to ~$2,000+ per micro depending on volatility regime.

For a $2K sandbox account this means: a handful of MNQ contracts intraday is feasible on day-margin, but holding overnight could exceed account equity. **Stay intraday, stay in micros.**

## Leverage & notional — respect the multiplier

```
notional_value = multiplier × index_level × qty
leverage       = notional_value / margin_posted
```
One MNQ at index 21,500 = **$43,000 notional** controlled on a few hundred dollars of day-margin → **leverage easily 50–100×+**. A 1% index move (215 pts) = **$430 per contract** — which can be more than the day-margin posted.

> "Financial leverage can result in losses greater than the initial margin." — NinjaTrader. This is the warning that does not exist for long options.

## Mark-to-market: P&L settles into cash daily

Futures are **marked to market at the daily settlement (16:00 CT)**. Unlike options (unrealized until close), futures gains/losses move **variation margin** in and out of the account every day. Win → cash credited; lose → cash debited, and if equity dips below maintenance you get a **margin call** (broker requests funds, typically within 24h, or liquidates).

## Margin call mechanics

1. Position equity falls below **maintenance margin**.
2. Broker issues a **margin call** — bring the account back to the required level.
3. Fail to meet it → broker **liquidates** positions (often at the worst time) + fees.

## How this maps to OUR risk controls

- **Kill-switch floor:** sandbox account `5WW73759`, $2K start, floor **$1,600** (−$400 / −20%), daily loss limit **−$200/day**. These are *our* guardrails, tighter than any margin call.
- **Micros only:** 1/10 the notional of E-minis — keeps leverage sane on a small account.
- **Intraday only:** avoids overnight/initial margin entirely while learning.
- **Point-based stops:** every trade has a defined point stop = defined dollar risk (`points × $2 × qty` for MNQ). This is how we cap the uncapped-loss nature of futures.
- **Position sizing rule:** size so that **stop-distance × point_value × qty ≤ per-trade $ risk cap**. Never size by "what margin allows" — size by what the **stop** allows.
