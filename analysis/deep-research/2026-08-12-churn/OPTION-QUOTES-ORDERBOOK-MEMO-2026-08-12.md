# Option quotes / order book — decision memo (agent research, 2026-08-12 night)

**VERDICT: BUY NOTHING. J has no steps to take.** All three use cases are already solved, and
two independent methods agree to the cent.

## The killer fact: SPY 0DTE is quoted at the PENNY FLOOR

Live pull of today's full RTH tape — **554,198 ticks across the 30 near-ATM 0DTE contracts**:
**minimum observed tick = $0.010 on ALL 30 contracts**, including one with a $7.69 mid. For
the premiums we actually trade ($0.11-$0.74 across the 182-position anchor set), the Roll
effective spread is **$0.008-$0.013 — one tick.**

You cannot be more precise than a penny when the market is a penny wide. **A quote feed would
sell us information we already have.** The in-code comment claiming "half-spread ~0.02-0.05"
is simply wrong for this instrument.

## Do we need NBBO history? No, per use case

| use case | needs NBBO? | why |
|---|---|---|
| entry conviction on 5-min bars | ❌ | entry is driven by SPY structure; the option's spread doesn't change whether the setup fired |
| exit replays through `exit_manager` | ❌ | the replay error is STRUCTURAL, not friction — see decomposition |
| friction estimation | ❌ | already measured, two ways, converging |

**Error decomposition kills the exit case** (n=182 real broker positions, harness-fidelity.json):
**42% of positions carry per-contract error >$0.04 — larger than a full 2x round-trip spread —
and those hold 93% of total absolute error.** Perfect spread knowledge can only touch the other
7%. The calibration history agrees: adding the SPY feed cut bias $5,949 -> $2,051 (~$3,900 of
the fix); slippage modelling was a distant second. Residual error is intra-bar path ambiguity
and exit-stage mismatch. **Quotes fix neither. Finer bars would — and 1-min bars are free.**

**Proportionality:** $80-400/mo against a $2K account is 4-20% of equity per year to refine a
one-cent constant.

## The free path, independently validated ✅

- 591,174 trade ticks/day on the SPY 0DTE chain; **~94% concentrated in the top-30 near-ATM
  contracts** — exactly what we trade. Exchange + condition codes present.
- **Roll (1984) estimator** estimable on 26/30 contracts: median effective spread **$0.0208**
  => **half-spread $0.0104/side**. (Fails on the 4 thinnest — drift swamps the bounce, a
  standard Roll limitation.)
- **Convergence:** the v5 harness calibration, regressed against 182 real broker fills,
  independently landed on **1c**. Microstructure theory and broker truth agree to the cent.
  That is the strongest validation obtainable *without* buying quotes.

## 🚨 Free finding: the sim default is 2x the measured cost

`simulator_real.py:107-108` (and `simulator_credit.py:70-71`) default entry/exit slippage to
**$0.02** — double the measured $0.0104. **255 call sites exist; only 14 pass slippage
explicitly**, so ~241 studies ran on the 2x default.

**NOT changed tonight, deliberately.** Halving it shifts ~+$0.02/contract/round-trip into
EVERY historical cell simultaneously — enough to flip previously-KILLED cells positive on a
config edit rather than on new evidence. That is how a kill decision gets laundered. The 2c
default errs CONSERVATIVE (understates edge, never overstates), so leaving it costs only
pessimism. The code comment has been corrected with the measurement + a work order.
**Re-baseline needs its own frozen prereg**: change in ONE commit, re-run the affected verdict
set, publish a before/after table for every cell whose sign flips.

## Priced table — reference only, since we're not buying

| vendor / product | type | price | published? |
|---|---|---|---|
| **Databento** OPRA PAYG | BBO (`mbp-1`/`bbo-1s`/`bbo-1m`) or depth (`mbp-10`/`mbo`) | from **$0.04/GB** + **$125 free credit**; SPY-only scoping confirmed | ✅ headline only |
| ThetaData Standard | tick NBBO, 2016+ | $80/mo | ✅ |
| ThetaData Value | 1-min bid/ask, 2020+ | $40/mo | ✅ |
| CBOE DataShop option quotes | 1-min NBBO snapshots | cart-computed | ❌ sales-gated |
| ORATS Intraday | 1-min snapshots | $399/mo | ✅ |
| Massive (ex-Polygon) Advanced | NBBO | $199/mo min | ✅ |

**No vendor sells a single-symbol discount tier** — flat-fee vendors charge full-market rates
regardless of symbol count. The only exception is Databento's usage-based model, where SPY-only
scoping genuinely cuts the bill.

**EOD-only traps confirmed** (on top of the earlier MarketData.app / FirstRate / IBKR):
ORATS core Data API, Massive Basic/Starter/Developer, CBOE Option EOD Summary, Nasdaq NOTOEOD,
Intrinio Silver (15-min delayed).

## Storage: tick would be the wrong product anyway

SPY 0DTE only — tick NBBO ~**358 GB/yr** (3,000x our entire 115 MB cache, needs parquet/DBN);
1-second BBO ~90 GB/yr; **1-minute BBO ~1.5 GB/yr** and matches our replay granularity. Even
in the buy scenario, tick is over-buying.

## If this ever reopens

The trigger is a MECHANISM change, not appetite: a strategy that **rests passive limits at mid
instead of crossing** is the only question trade ticks cannot answer. Even then the whole prize
at a 1c spread is ~$4 per round-trip side on 4 contracts, against a $13 median replay error.
Route: Databento's $125 free credit on `bbo-1m`, SPY-scoped — likely $0 out of pocket.

**The real fidelity lever is free and already identified: replay error is dominated by
intra-bar path resolution, and Alpaca gives us 1-min bars at $0 while the harness runs 5-min.**

## Could not determine
True Roll-vs-actual-NBBO error (unmeasurable — no historical NBBO exists to score against;
substituted the convergence check). Databento per-schema multipliers. CBOE resolved cart price.
dxFeed / Nasdaq Data Link options historical products. The agent's raw NBBO snapshot was taken
after hours (21:48 ET) so those quoted spreads were inflated and were NOT used — all spread
conclusions come from RTH ticks only.
