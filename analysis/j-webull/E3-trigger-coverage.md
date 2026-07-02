# E3 — Trigger-coverage audit (engine 2025-26 vs J's profit context 2021-23)

> Generated 2026-07-02T02:20:27.690690+00:00 by `scripts/e3_trigger_coverage.py`. JSON twin: `E3-trigger-coverage.json`.

## Verdict

- All J profitable cells (n>=15, +exp) have >=10 engine entries — coverage already expresses J's profit context.
- J PROFIT-CELL (at_level=Y|aligned=Y|midday): J n=13, exp $-29.9/tr; engine entries: 25 (4.4% of engine flow).
- Engine flow in J's TOXIC open window (09:30-10:00): 44.2% (J there: -$35.9/tr on 24% of his volume).

## Coverage matrix (context cell x trigger)

| Cell | J n | J total $ | J $/tr | Engine n | Engine % | core_bear | core_bull | vwap_cont | vwap_reclaim_fb | vix_dayside | double_bottom |
|---|---|---|---|---|---|---|---|---|---|---|---|
| at_level=Y|aligned=Y|morning | 29 | +2613 | +90.1 | 38 | 6.7% | 2 | 0 | 4 | 18 | 3 | 11 |
| at_level=Y|aligned=N|open | 4 | +245 | +61.2 | 6 | 1.1% | 1 | 1 | 0 | 0 | 4 | 0 |
| at_level=N|aligned=N|other | 1 | +100 | +100.0 | 0 | 0.0% | 0 | 0 | 0 | 0 | 0 | 0 |
| at_level=Y|aligned=Y|late | 4 | -17 | -4.2 | 13 | 2.3% | 7 | 0 | 0 | 0 | 0 | 6 |
| at_level=N|aligned=N|late | 14 | -148 | -10.6 | 11 | 1.9% | 1 | 0 | 0 | 0 | 0 | 10 |
| at_level=Y|aligned=N|late | 7 | -173 | -24.7 | 4 | 0.7% | 0 | 0 | 0 | 0 | 0 | 4 |
| at_level=Y|aligned=N|morning | 12 | -173 | -14.4 | 6 | 1.1% | 1 | 1 | 0 | 0 | 3 | 1 |
| at_level=Y|aligned=Y|midday | 13 | -388 | -29.9 | 25 | 4.4% | 9 | 3 | 0 | 0 | 2 | 11 |
| at_level=N|aligned=Y|midday | 100 | -491 | -4.9 | 58 | 10.2% | 34 | 2 | 0 | 0 | 3 | 19 |
| at_level=N|aligned=Y|late | 36 | -705 | -19.6 | 26 | 4.6% | 6 | 2 | 0 | 0 | 0 | 18 |
| at_level=Y|aligned=N|midday | 11 | -809 | -73.5 | 10 | 1.8% | 1 | 0 | 0 | 0 | 0 | 9 |
| at_level=N|aligned=N|midday | 59 | -849 | -14.4 | 20 | 3.5% | 5 | 0 | 0 | 0 | 2 | 13 |
| at_level=Y|aligned=Y|open | 14 | -947 | -67.6 | 66 | 11.6% | 1 | 4 | 43 | 8 | 10 | 0 |
| at_level=N|aligned=Y|open | 73 | -2015 | -27.6 | 171 | 29.9% | 1 | 10 | 105 | 13 | 42 | 0 |
| at_level=N|aligned=N|open | 23 | -2122 | -92.3 | 9 | 1.6% | 0 | 1 | 0 | 0 | 8 | 0 |
| at_level=N|aligned=N|morning | 38 | -2385 | -62.8 | 11 | 1.9% | 1 | 0 | 0 | 0 | 5 | 5 |
| at_level=N|aligned=Y|morning | 104 | -4473 | -43.0 | 97 | 17.0% | 1 | 3 | 15 | 48 | 5 | 25 |

## Engine totals by trigger

- core_bear: 71
- core_bull: 27
- vwap_continuation: 167
- vwap_reclaim_failed_break: 87
- vix_regime_dayside: 87
- double_bottom_base_quiet: 132

## Caveats

- C22: J cells are 2021-23 SPX/SPY context; engine cells are 2025-26 SPY. Structure port only.
- Coverage audit ONLY — extra-setup P&L authority remains their own real-fills scorecards (C1).
- double_bottom replay omits NOT_NEAR_NAMED (over-counts that watcher's coverage slightly).
- Watcher-replay VWAP = typical-price session cumulative; marginal count drift possible vs live wrappers.
- core engine = run_backtest(use_real_fills=True) with live params.json (Safe) — the real gate cascade.

## Interpretation (added 2026-07-01 evening, same session)

1. **PREMISE REVISION — the E1 spec's "midday profit cell" does not exist in J's own book
   at the 3-axis intersection.** The headline "+$3.7/tr at-level (n=94)" pools all times;
   cut by all three axes, `at_level=Y|aligned=Y|midday` is n=13, **-$29.9/tr**. The ONLY
   n>=15 positive 3-axis cell is `at_level=Y|aligned=Y|MORNING` (10:00-11:00): n=29,
   **+$90.1/tr, +$2,613 total** — J's real repeatable cell was a morning at-level aligned
   entry, not midday.
2. **Coverage verdict: no fully-uncovered profitable cell.** The morning profit cell already
   receives 38 engine entries (6.7% of flow) — mostly `vwap_reclaim_failed_break` (18) +
   `double_bottom` (11); the CORE engine fires there only 2x. Coverage exists via the armed
   extra setups, thin via core.
3. **Engine flow concentrates 44.2% in the 09:30-10:00 open window** — J's toxic window
   (-$35.9/tr on 24% of his volume). NOT automatically a defect (the engine's open-window
   setups were independently validated on 2025-26 real fills, and J's toxicity there was
   driven by his own averaging-down behavior), but it is the single largest structural
   divergence between where the engine trades and where J made money.
4. **E1 verdict (both windows) closed the loop:** J_LEVEL_MIDDAY **and** the E3-corrected
   J_LEVEL_MORNING are both DRY on 2025-26 OPRA real fills (see
   `analysis/recommendations/j-level-midday.json` / `j-level-morning-screen.json`) — the
   raw 3-feature fingerprint is not a portable standalone trigger (C22/C24); whatever
   carried J's 2021-23 morning cell is not captured by level-proximity + VWAP-side + clock.
