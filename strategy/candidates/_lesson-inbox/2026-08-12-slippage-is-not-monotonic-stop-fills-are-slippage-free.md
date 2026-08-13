# Lesson candidate: lowering slippage makes some cells WORSE — stop/limit fills are slippage-free, so %-target winners scale with the pessimism

> Queued by the SLIPPAGE-REBASELINE study, 2026-08-12.
> Prereg: `analysis/recommendations/prereg-slippage-rebaseline-2026-08-12.json` (frozen b2ab6943, amended 97d46490).

## Symptom

Re-running `backtest/autoresearch/v14e_ampm_real_fills.py` at `slippage=0.01` instead of the
`0.02` module default made the cell **worse**, not better:

| cell | 0.02 | 0.01 | delta |
|---|--:|--:|--:|
| production_stop AM total_pnl | -45.24 | -45.60 | **-0.36** |
| production_stop PM total_pnl | +159.12 | +157.80 | **-1.32** |

Less friction producing less profit is arithmetically impossible for a well-formed fill model,
and this was pre-registered as a bug signature ("any cell that gets WORSE at lower slippage
indicates a bug in that harness").

It is **not** path dependence. Every single `TP1_THEN_RUNNER_RIBBON` trade moved by
**exactly -$0.60**, with an identical exit reason and identical exit path in both arms.

## Root cause

Two exit paths in `backtest/lib/simulator_real.py` fill at an **exact price with no
`exit_slippage` applied**, while every market exit pays it:

* **TP1 premium fallback** (line ~789): `tp1_fire_premium = tp1_premium_fallback`, where
  `tp1_premium_fallback = entry_premium * (1.0 + tp1_premium_pct)` (line ~475). Defensible —
  a limit order does fill at its limit.
* **Runner stop, including the post-TP1 breakeven stop** (lines ~703, ~832, ~859):
  `runner_exit_premium = runner_stop_premium` with `runner_stop_premium = entry_premium`
  (line ~795). **Not** defensible — a stop executes at market and should pay the half-spread.

Compare the market-exit paths (lines 659, 685, 710, 740, 763, 824-862), which all use
`max(0.01, opt_bar.close - exit_slippage)`.

Consequence for a TP1-limit + breakeven-runner-stop trade:

```
P&L = (entry*(1+tp1_pct) - entry) * tp1_qty * 100  +  (entry - entry) * runner_qty * 100
    = tp1_premium_pct * entry_fill * tp1_qty * 100
```

The whole payoff is **strictly proportional to the entry fill**, and the entry fill *includes
entry slippage*. So a more pessimistic slippage assumption **inflates** the dollar profit on
these winners.

Predicted per-trade delta when halving slippage, with `TP1_PREMIUM_PCT = 0.30`,
`TP1_QTY_FRACTION = 2/3`, `qty=3` → `tp1_qty = int(3 * 2/3) = 2`:

```
0.30 * 0.01 * 2 * 100 = $0.60
```

Observed: **-$0.60 on every such trade.** Exact match — mechanism confirmed, not inferred.

## Why this matters beyond one script

The premise "the 2c default made ~241 studies twice as pessimistic" is **too simple**. The 2c
default was:

* **pessimistic** on entry cost and on every market/ribbon/time exit, but
* **optimistic** on %-target winners (it inflated their dollar profit) and on all stop fills
  (which paid no spread at all).

So the sign of the slippage bias **depends on each cell's exit mix**. A cell dominated by
premium-stop and TP1-limit exits barely moves, or moves the wrong way; a cell dominated by
market exits moves by the full ~$2/contract/round-trip. Measured on the same population:
`v14e_chart_stop_research` prod (94% premium-stop) moved only **+$39.60** while its
chart-stop arm (market exits) moved **+$548.80** — a 14x difference in the same script, on the
same trades, from the exit mix alone.

Corollary: **proportional stops absorb slippage changes.** For a stop at `entry*(1+stop_pct)`,
P&L is `stop_pct * entry_fill`, so the slippage effect is scaled by `stop_pct` (~8%) instead of
passed through at 100%.

## Blast radius — which simulators carry it

| module | slippage-free stop fill? | verdict |
|---|---|---|
| `backtest/lib/simulator_real.py` | YES — lines ~703, ~832, ~859 (`= runner_stop_premium`) + TP1 fallback ~789 | **AFFECTED** |
| `backtest/lib/simulator_real_trailing.py` | YES — lines 294, 383, 408 + TP1 fallback 344 | **AFFECTED** |
| `backtest/lib/simulator_credit.py` | no — every exit is `m ± exit_slippage` (lines 404-406) | clean |
| `backtest/lib/simulator_debit.py` | no — every exit is `m ± exit_slippage` (lines 375-377) | clean |

The two AFFECTED modules are the single-leg directional simulators, which are exactly the ones
the whole verdict-bearing study set runs on. The multi-leg spread simulators are symmetric and
correct.

## Fix

1. Apply `exit_slippage` to the runner-stop fills in BOTH affected modules (`simulator_real.py`
   ~703/~832/~859 and `simulator_real_trailing.py` 294/383/408). A stop is a market order.
   Leaving the TP1 *limit* slippage-free is fine and should be commented as deliberate.
2. Until (1) lands, **never interpret a slippage sweep on this harness as monotonic**, and never
   quote a single "$X of baked-in pessimism" number across cells with different exit mixes.

## Detection / guard

Add a vary-and-assert guard: run any fill-model cell at two slippage values on a fixed
population and assert `total_pnl(lower) >= total_pnl(higher)` for cells whose exits are
market-priced. A violation means an exit path is bypassing the slippage term. This belongs in
`backtest/tests/test_graduated_guards.py` — it is a C14 (dead/unapplied knob) instance where the
knob is applied *inconsistently* rather than not at all.
