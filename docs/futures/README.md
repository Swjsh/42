# Futures Reference Library

> Built 2026-06-17 from authoritative primary sources (CME Group, NinjaTrader, tastytrade, Schwab, Green Trader Tax). Every fact here is cited — see [SOURCES.md](SOURCES.md). This exists so the engine and Gamma reason about futures from documented reality, not assumptions.

## Files

| File | Covers |
|---|---|
| [CONTRACT-SPECS.md](CONTRACT-SPECS.md) | MNQ / MES / NQ / ES exact specs, tick math, notional value |
| [MARGIN-LEVERAGE-RISK.md](MARGIN-LEVERAGE-RISK.md) | Initial/maintenance/day/overnight margin, leverage, notional risk, margin calls |
| [SESSIONS-ROLLOVER-TAX.md](SESSIONS-ROLLOVER-TAX.md) | Trading hours, maintenance break, settlement, quarterly rollover, Section 1256 tax, costs |
| [SOURCES.md](SOURCES.md) | All authoritative source links + retrieval dates |

---

## THE FUTURES MENTALITY — how this is NOT 0DTE options

Our SPY engine trades **0DTE options**. The MNQ/MES engine trades **futures**. They are structurally different instruments, and trading futures with an options mindset is a foot-gun. This is the core reframe.

### 1. Linear P&L — no theta, no premium decay
- **Options:** you pay premium; the position bleeds value every hour (theta); P&L is non-linear (delta/gamma). "+30% premium" is the unit.
- **Futures:** P&L is **linear and symmetric**. Each index point = a fixed dollar amount (MNQ $2/pt, MES $5/pt). No decay. Holding costs nothing but margin. The unit is **points / ticks**, not premium %.
- **Engine impact:** stops and targets are set in **points**, not premium percentages. A "−8% premium stop" has no meaning here. Use point-based or level-based stops.

### 2. No daily expiry — futures roll quarterly, they don't expire worthless overnight
- **Options:** 0DTE expires tonight, worthless if OTM. The 15:50 flatten exists because *expiry destroys the instrument*.
- **Futures:** the front month expires **once a quarter** (3rd Friday of Mar/Jun/Sep/Dec). Between rolls, a position can be held indefinitely — overnight, for days. There is **no expiry-driven reason to flatten daily.**
- **Engine impact:** "flat by EOD" is now a *strategy choice* (avoid overnight margin + gap risk), not a mechanical necessity. It belongs as a **time-stop inside the heartbeat**, not a separate expiry-flatten task. (This is exactly why we removed `futures-eod-flatten` on 2026-06-17.) See [SESSIONS-ROLLOVER-TAX.md](SESSIONS-ROLLOVER-TAX.md) for roll mechanics.

### 3. Leverage is via MARGIN, not premium — you can lose more than you put up
- **Options (long):** max loss = premium paid. Defined risk, always.
- **Futures:** you post **margin** (a good-faith deposit, a fraction of notional). You control the **full notional** value. Losses are **not capped at margin** — a gap can take more than you deposited, triggering a margin call. See [MARGIN-LEVERAGE-RISK.md](MARGIN-LEVERAGE-RISK.md).
- **Engine impact:** position sizing is **notional- and point-risk-based**, not premium-based. One MNQ ≈ $2 × index notional exposure on a few hundred dollars of day-margin. Respect the leverage — the kill-switch floor ($1,600 on the $2K sandbox) is the real guardrail.

### 4. Mark-to-market daily — P&L is realized continuously
- **Options:** unrealized until you close.
- **Futures:** every position is **marked to market at the daily settlement** (16:00 CT). Gains/losses move cash in/out of the account each day. Year-end, all open Section 1256 positions are deemed sold (see tax section).
- **Engine impact:** account equity reflects settled P&L daily; the account.json daily_pnl tracking maps cleanly to this.

### 5. Near-24-hour liquidity
- **Options:** SPY options trade RTH only (09:30–16:00 ET). Illiquid at the edges.
- **Futures:** MNQ/MES trade **Sunday 6pm ET → Friday 5pm ET**, with a 1-hour daily maintenance break (5–6pm ET). Deep liquidity around the clock; the 15:55 close is liquid (Globex is open).
- **Engine impact:** our strategy still trades the **RTH window (09:30–16:00 ET)** because that's what the v3 backtest validated. But exits at the close don't suffer the options-style liquidity cliff.

### 6. Tax: Section 1256 60/40 — structurally better than equity/options day-trading
- Futures get **60% long-term / 40% short-term** treatment **regardless of holding period** — even on day trades. Blended top rate ≈ **26.8%** vs 37% ordinary. Wash-sale rule does **not** apply. See [SESSIONS-ROLLOVER-TAX.md](SESSIONS-ROLLOVER-TAX.md). (Paper account now, but this is a real edge when live.)

---

## One-line summary for the engine

> **Futures = linear point-based P&L on a leveraged notional position that you hold by posting margin, settle daily, and roll quarterly. Stops in points, size by notional/point-risk, flatten-by-close is optional risk management not expiry defense, and the tax treatment is materially better.**
