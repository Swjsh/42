# Contract Specifications — Equity Index Futures

> Source: CME Group official contract-spec pages (see [SOURCES.md](markdown/futures/SOURCES.md)). Specs are stable; **margins move** and are covered in [MARGIN-LEVERAGE-RISK.md](markdown/futures/MARGIN-LEVERAGE-RISK.md).

## The four contracts we care about

| Contract | Product code | Underlying | Multiplier | Tick size | **Tick value** | **Point value** | Notional @ illustrative index |
|---|---|---|---|---|---|---|---|
| **Micro E-mini Nasdaq-100** | **MNQ** | Nasdaq-100 | **$2 × index** | 0.25 pt | **$0.50** | **$2** | $2 × 21,500 ≈ **$43,000** |
| **Micro E-mini S&P 500** | **MES** | S&P 500 | **$5 × index** | 0.25 pt | **$1.25** | **$5** | $5 × 6,000 ≈ **$30,000** |
| E-mini Nasdaq-100 | NQ | Nasdaq-100 | $20 × index | 0.25 pt | $5.00 | $20 | $20 × 21,500 ≈ $430,000 |
| E-mini S&P 500 | ES | S&P 500 | $50 × index | 0.25 pt | $12.50 | $50 | $50 × 6,000 ≈ $300,000 |

> **Notional figures are illustrative** — multiply the multiplier by the **current** index level off the live chart. They move every day. The point of the column is scale: one MNQ controls tens of thousands of dollars of exposure.

**Micros are exactly 1/10 of their E-mini sibling.** MNQ = NQ ÷ 10, MES = ES ÷ 10. Same tick size (0.25), 1/10 the dollar value. This is why we trade micros: same strategy, 1/10 the risk per contract — correct for a $2K learning account.

## Tick math (the unit of futures P&L)

```
tick_value = multiplier × tick_size
MNQ:  $2  × 0.25 = $0.50 per tick   (4 ticks = 1 point = $2)
MES:  $5  × 0.25 = $1.25 per tick   (4 ticks = 1 point = $5)
NQ:   $20 × 0.25 = $5.00 per tick   (4 ticks = 1 point = $20)
ES:   $50 × 0.25 = $12.50 per tick  (4 ticks = 1 point = $50)
```

**P&L formula (what the engine uses):**
```
pnl_usd = (exit_price - entry_price) × point_value × qty × direction
          where direction = +1 for long, -1 for short
```
Example: long 3 MNQ, entry 21,340 → exit 21,390 = +50 points × $2 × 3 = **+$300**.

> This matches `POINT_VALUE = {"MNQ": 2, "MES": 5, "NQ": 20, "ES": 50}` in `backtest/futures/tastytrade_paper.py` — **verified correct against CME specs 2026-06-17.**

## Settlement & expiration (summary — full detail in SESSIONS-ROLLOVER-TAX.md)

- **Settlement:** **Cash-settled** to the spot index value. No physical delivery, no share assignment. (Contrast: 0DTE SPY options *can* assign shares if held ITM — the 2026-05-11 incident. Futures have **no assignment risk**.)
- **Expiration:** Quarterly — **3rd Friday of March (H), June (M), September (U), December (Z).**
- **Listed contracts:** Nearest quarterly months. The continuous front-month chart symbol is `CME_MINI:MNQ1!` / `MES1!` (the `1!` = front month, auto-rolling).

## Trading hours (summary)

- **Globex:** Sunday 5:00 p.m. CT → Friday 4:00 p.m. CT (≈23h/day), with a **daily maintenance break 4:00–5:00 p.m. CT (5:00–6:00 p.m. ET)**.
- **Our strategy window:** RTH **09:30–16:00 ET** (the cash-market session), because that's what the v3 backtest validated.

## Why MNQ first, MES second (our sequencing)

- **MNQ** v3 config: OOS **+$15,027**, WR **67.4%** — strong, robust. Primary.
- **MES** v3_mes config: OOS **+$2,238**, WR **56.4%** — passes but **thin** (+2-tick stress only +$664). Add **after** MNQ validates ≥20 paper trades. Do **not** run the MNQ config on MES (erl_irl long loses −$5,788 on real MES bars — different instrument character).
