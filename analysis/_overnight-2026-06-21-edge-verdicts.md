# Overnight Edge Verdicts — 2026-06-21

> Autonomous overnight specialist (J asleep). PROPOSALS/VERDICTS ONLY — no production touched (no params/heartbeat/filters/CLAUDE edits, no orders).
> This is the **causal forward-edge SCREEN** — the precondition that must pass BEFORE a real-fills + null + anchor A/B is worth running. C3/L58: SPY-PRICE direction is necessary-not-sufficient for an OPTION edge. A FAIL here kills the hypothesis; a PASS earns the next gate, it does not ratify anything.

- Data: `backtest/data/spy_5m_2025-01-01_2026-06-16.csv` (5m SPY). Forward horizon K=6 bars (~30m), same-session, look-ahead-free (bars[:i+1]).
- Split: IS = before 2026-04-01 ; OOS = on/after (2026-Q2 held out).
- `avg_bps` = mean forward return in the *predicted* direction (bps); `wr` = fraction of reads where price moved the predicted way.

## H1 — VWAP-side alignment gate

Question: does entering in the *with-VWAP* direction (call above / put below session VWAP) beat entering *against* VWAP, on SPY-now?

| split | arm | n | avg_bps | wr |
|---|---|---|---|---|
| IS | with-VWAP | 24568 | +0.02 | 0.510 |
| IS | against-VWAP | 24568 | -0.02 | 0.486 |
| OOS | with-VWAP | 7215 | -0.18 | 0.498 |
| OOS | against-VWAP | 7215 | +0.18 | 0.499 |

**Separation (with − against): IS +0.04 bps, OOS -0.36 bps.**

**VERDICT: REJECT (screen FAIL).** With-VWAP forward edge does not robustly beat against-VWAP across IS+OOS — the C22 SPX-2021-23 → SPY-now transfer does not hold at the price-direction layer, so no option edge is possible. Do not spend a real-fills A/B on it. Re-open only if a regime-stratified read separates.

## H2 — Morning-shoulder (10:00) bleed gate

Question (L167 reproducer on SPY-now): is 10:00-10:59 ET the worst forward-edge hour and 11:00 among the best, for a with-VWAP directional entry?

| hour ET | IS n | IS avg_bps | IS wr | OOS n | OOS avg_bps | OOS wr |
|---|---|---|---|---|---|---|
| 04:00 | 72 | +2.82 | 0.569 | 294 | +0.12 | 0.527 |
| 05:00 | 144 | +1.88 | 0.576 | 590 | +0.25 | 0.481 |
| 06:00 | 144 | -12.03 | 0.472 | 600 | -1.24 | 0.455 |
| 07:00 | 144 | +2.79 | 0.514 | 600 | -0.80 | 0.443 |
| 08:00 | 160 | +1.97 | 0.544 | 602 | -0.15 | 0.472 |
| 09:00 | 606 | -0.54 | 0.497 | 488 | -2.05 | 0.459 |
| 10:00 | 2817 | -0.33 | 0.522 | 629 | +1.79 | 0.556 |
| 11:00 | 3720 | +0.07 | 0.528 | 624 | +0.87 | 0.514 |
| 12:00 | 3720 | +1.16 | 0.528 | 624 | +0.13 | 0.561 |
| 13:00 | 3711 | +0.05 | 0.512 | 624 | -1.98 | 0.470 |
| 14:00 | 3686 | +1.16 | 0.535 | 624 | +0.68 | 0.542 |
| 15:00 | 3644 | -0.98 | 0.474 | 585 | +0.38 | 0.515 |
| 16:00 | 1731 | -2.16 | 0.437 | 87 | -0.13 | 0.494 |
| 17:00 | 269 | +1.63 | 0.476 | 83 | -1.79 | 0.446 |
| 18:00 | 0 | +0.00 | 0.000 | 84 | -0.94 | 0.429 |
| 19:00 | 0 | +0.00 | 0.000 | 77 | -1.03 | 0.481 |

**IS worst hour = 15:00 (-0.98 bps); IS best hour = 12:00 (+1.16 bps).** OOS 10:00 = +1.79 bps.

**VERDICT: NEEDS-MORE / RETARGET.** The single worst IS hour is 15:00, not necessarily 10:00 on this 5m-price screen — per L167 discipline the gate must target the hour that ACTUALLY bleeds in the real-fills histogram, not folklore. NEXT STEP: regenerate the real-fills per-hour histogram (the authority) before choosing the gated hour; do not hard-code 10:00. Confirm anchor no-ops + null + OOS sign-stability. File `analysis/recommendations/h2-morning-shoulder-gate.json`.

## H3 — Market-structure BOS/CHoCH as an ENTRY signal

Question: on a CONFIRMED structure break (causal, scored only on the bar the break is confirmed), does the break direction predict the forward move? And is the firing rate below the C27 noise ceiling (<~40% of days)?

| split | event | n | avg_bps | wr |
|---|---|---|---|---|
| IS | BOS | 1060 | -0.93 | 0.503 |
| IS | CHoCH | 644 | +0.10 | 0.467 |
| OOS | BOS | 271 | -0.25 | 0.480 |
| OOS | CHoCH | 216 | -0.12 | 0.495 |

- IS firing density: 1704/24568 bars = 6.94% per-bar (well within C27 noise ceiling) (~5.5 breaks/day across 310/310 days — a structure break ~every session is expected; C27 governs PER-BAR density, which is fine).

- OOS firing density: 487/7215 bars = 6.75% per-bar (well within C27 noise ceiling) (~9.2 breaks/day across 53/53 days — a structure break ~every session is expected; C27 governs PER-BAR density, which is fine).

**VERDICT: REJECT or REWORK (BOS screen WEAK/FAIL).** Confirmed BOS break-direction does not show robust positive forward edge across IS+OOS at K=6 — either the break is already priced by confirmation time (lagging) or the window is wrong. NEXT STEP: before any real-fills A/B, sweep the forward horizon K and the swing window, and test CHoCH-as-reversal separately; if no horizon separates, keep market_structure WATCH_ONLY (detection-correct but no standalone entry edge) per its current status.

## Cross-cutting notes (OP-16 / OP-20)

- **None of the three is ratify-ready.** This screen is the *first* gate; each PASS still owes the full bundle: OPRA real-fills (C1 authority — BS/price is ranking-only), `null_baseline.null_gate` (beat the null MAX, L172), `j_edge_tracker` anchor-no-regression (keep $1542 winners, add no $725 losers, OP-16), truncation cross-check (no sign-flip at chart-stop-only, L171), and ≥4/6 positive quarters + top5≤200%.
- **C3/L58 disclosure:** every number above is SPY 5m PRICE direction, not option premium P&L. A price-bps edge can still die in the delta/theta/stop translation. The real-fills validator is the only WR/expectancy authority.
- **C22 disclosure (H1):** J's VWAP/time findings are SPX 2021-23 (n=9 / histogram). The IS+OOS columns above are the SPY-now re-validation; they are reported as measured, not assumed.

_Generated by `backtest/autoresearch/_overnight_0621_edge_validate.py` (pure-Python, $0). Reproducer: `backtest/.venv/Scripts/python.exe -m autoresearch._overnight_0621_edge_validate` from `backtest/`._