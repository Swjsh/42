# B7 — Multi-Day-Trendline Confluence Scorecard (2026-06-21)

**Angle B: the J 5/4 source-of-truth signature, tested as a DISCRETE setup on real OPRA fills for the first time.**

- Harness: `backtest/autoresearch/_b7_mdt_confluence.py`
- Machine output: `analysis/recommendations/b7-mdt-confluence.json`
- Window: 2025-01-02 .. 2026-06-16 (363 trading days). IS = 2025, OOS = 2026.
- Fills authority: real OPRA via `lib.simulator_real.simulate_trade_real` (C1). Causal next-bar-open entry; chart-stop = session extreme.
- Tiers (C29): ATM (Safe-2) + ITM-2 (Bold). Stops swept {-8%, -20%, -50%, chart-only}.

## Verdict: **DEAD**

No cell clears the 9-gate bar. Multi-day-trendline **structural** confluence (NOT additive scoring) does not manufacture a discrete option edge OOS. It mirrors the B0 additive triple-kill and re-confirms C3/L58 (SPY-direction read != option edge).

## What the setup is

One causal entry/day: a bar that **rejects a same-session (day) trendline** (its high/low tags the line and the bar closes back through it) WHILE the day-trendline sits within `MDT_TOL` of a **multi-day trendline** (fit across the prior 4 days' swing points, >=3 touches, projected forward) AND within `LEVEL_TOL` of a **causal named level** (PDH/PDL/PDC, PMH/PML, IBH/IBL) — all pointing the same direction. Resistance cluster -> PUT, support cluster -> CALL.

Reuses `crypto.lib.trendlines` (swings + fit), `crypto.lib.session_levels_spy` + prior-day stats (causal levels), `infinite_ammo_discovery` day scaffolds + strike snapping, and `fraud_gates`/`null_baseline` (L171/L172 gates).

## Key diagnostic finding (why the morning-only version is wrong)

The clean J winners (4/29, 5/01, 5/04 — all **2026**, all PUTS) do **not** reject in the morning. They GRIND UP through the first hour (4/29: 710.1 -> 711.5; 5/01: 721.3 -> 724.6; 5/04: 719.7 -> 721.4). J's put rejections came **after** the morning push topped out, later in the session. A morning-only (<=10:30) reject detector therefore structurally misses the J signature — it fired only **3 times in 363 days** and caught **zero** anchors.

So the setup was tested over the **full RTH session** (15:30 cutoff, 15:45-equivalent time-stop) at realistic confluence widths (day-TL 0.30, MDT 0.75, level 0.75 ticks). That yields a testable population: **67 signals on 67 days (18.5% of days), 39 C / 28 P.**

## The grid (real OPRA fills, 67 signals)

| Tier | Stop | n | exp/t | OOS exp/t (oos_n) | posQ | top5% | full_drop5/t | OOS_drop5/t |
|---|---|---|---|---|---|---|---|---|
| ATM | -8% | 66 | $5.20 | **+$11.19** (14) | 4/6 | 304.9 | -$11.53 | -$28.05 |
| ATM | -20% | 66 | -$17.16 | +$1.54 (14) | 2/6 | neg | -$35.73 | -$46.33 |
| ATM | -50% | 66 | -$36.01 | -$36.99 (14) | 1/6 | neg | -$58.45 | -$106.27 |
| ATM | chart-only | 66 | -$58.56 | -$74.14 (14) | 2/6 | neg | -$83.60 | -$164.06 |
| ITM-2 | -8% | 64 | -$6.82 | **+$29.74** (13) | 3/6 | neg | -$35.90 | -$60.60 |
| ITM-2 | -20% | 64 | -$44.53 | -$11.77 (13) | 2/6 | neg | -$80.36 | -$149.70 |
| ITM-2 | -50% | 64 | -$55.32 | -$33.04 (13) | 3/6 | neg | -$94.30 | -$221.59 |
| ITM-2 | chart-only | 64 | -$79.32 | -$71.69 (13) | 1/6 | neg | -$120.33 | -$284.40 |

## Why every "positive" cell is a fraud

The only OOS-positive cells are the **-8% (tightest stop)** rows, and they die on the graduated gates:

- **G8 truncation (L171):** ATM/-8% (+$6.66/t full) **inverts to -$51.72/t at chart-stop-only**. The tight stop truncates losers; the signal is not the edge. `is_truncation_artifact = True`.
- **G7 random-null (L172):** the ATM/-20% and ITM-2/-8% cells PASS no-truncation but **FAIL the random-entry null** — a coin-flip entry with the same bracket reproduces the per-trade. The edge is the exit structure, not the read.
- **G5 / G9 drop-top5 (L173):** **every cell has negative drop-top5 per-trade, full AND OOS-alone** (e.g. best cell ITM-2/-8%: full -$35.90, OOS-alone -$60.60). The rare positives are pure concentration in a handful of lucky days.
- **G6 IS-half:** best cell is_exp = -$16.15 (<0).

## Anchor check (OP-16)

- Winners fired: **0/3** (missed 4/29P, 5/01P, 5/04P)
- Losers fired: **0/3** (skipped 5/05P, 5/06P, 5/07C)

**Caveat (disclosed):** all J anchors are 2026 dates, so they live in the OOS window — an anchor "take" would be a structural-fidelity check, not independent OOS evidence. The detector takes neither winners nor losers, so it has no fidelity to the J signature either way at these tolerances.

## Conclusion

The discrete **structural** multi-day-trendline confluence is **DEAD** — same outcome as the B0 additive triple-kill, reached by a different (non-additive, co-incidence) construction. The triple co-incidence at tight tolerances is too rare to trade (3/363 days); loosened to a tradeable 18.5% of days it is a SPY-direction read whose only positive cells are stop-truncation / exit-bracket artifacts that a random-entry null reproduces (C3/L58, L171/L172/L173). The J 5/4 "signature" is also mischaracterized as a morning rejection — J's puts were later-session rejections of an established level.
