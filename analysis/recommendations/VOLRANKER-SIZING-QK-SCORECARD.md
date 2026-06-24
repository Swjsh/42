# VOLRANKER SIZING overlay — QUARTER-KELLY BASE (the 1DTE NEXT-DIRECTION #1 test)

**Run:** 2026-06-24 (after-hours research, $0, no live edit)
**Slug:** `overnight-vol-sizing-overlay-1dte-QUARTER-KELLY-BASE`
**Harness:** `backtest/autoresearch/_volranker_sizing_qk.py`
**Output JSON:** `analysis/recommendations/volranker-sizing-qk.json`

## VERDICT: **SIZING_IMPROVEMENT**

> does swapping the overlay BASE from min-3 to quarter-Kelly give the overnight-vol tercile overlay genuine TWO-SIDED room (down-size bot days AND headroom on top days) at $10K/$25K, so it becomes a COMPOUNDING lever rather than the min-3-floor-bound UP-ONLY variance trade the 1DTE min-3 harness found? (VOLRANKER-SIZING-1DTE-SCORECARD NEXT DIRECTION #1.)

- **Base change:** BASE fraction swapped min-3 -> f_quarter_kelly (B10 continuous-Kelly capped at discrete, /4), computed on the IS-2025 slice only and frozen for OOS
- **Stream:** WP-8 1DTE / DOLLAR-STOP (Safe-2 ATM/$35.88, Bold ITM-2/$67.68) — byte-for-byte
- **Tercile multipliers:** {'top': 1.5, 'mid': 1.0, 'bot': 0.6}
- **Roll-up:** improves $2K=True | $10K improves=True OOS-clean=True | $25K improves=True OOS-clean=True | caps_ok=True zero_days=0

## Safe-2 — ATM (off +0, $-stop $35.88)

- **f_quarter_kelly (IS-2025):** 0.0769 (full=0.3077, continuous=3.1696, discrete=0.3077)
- **stream:** 165 classifiable 1DTE trades (IS=115 / OOS=50), median premium $2.5

| equity | FLAT(QK) total | OV(QK) total | FLAT shTr | OV shTr | FLAT sortDay | OV sortDay | FLAT maxDD | OV maxDD | IMPROVES | OOS-clean | overlay qty hist |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2000 | 3416.47 | 6787.99 | 0.3574 | 0.5236 | 13566.1732 | 4.8024 | 0.0759 | 0.0597 | True | True | {1: 50, 2: 64, 3: 46} |
| $10000 | 11156.01 | 11917.09 | 0.4895 | 0.4903 | 16.8805 | 15.4048 | 0.047 | 0.0371 | True | True | {2: 2, 3: 134, 4: 13, 5: 7, 6: 6, 7: 1, 8: 2} |
| $25000 | 26056.97 | 26586.41 | 0.5221 | 0.493 | 5.5849 | 5.7549 | 0.0489 | 0.039 | True | True | {3: 12, 4: 21, 5: 36, 6: 20, 7: 17, 8: 15, 9: 15, 10: 7, 11: 6, 12: 1, 13: 4, 14: 2, 15: 2, 16: 3, 17: 1, 18: 1, 21: 2} |

## Bold — ITM-2 (off -2, $-stop $67.68)

- **f_quarter_kelly (IS-2025):** 0.0777 (full=0.3109, continuous=2.9117, discrete=0.3109)
- **stream:** 165 classifiable 1DTE trades (IS=115 / OOS=50), median premium $3.57

| equity | FLAT(QK) total | OV(QK) total | FLAT shTr | OV shTr | FLAT sortDay | OV sortDay | FLAT maxDD | OV maxDD | IMPROVES | OOS-clean | overlay qty hist |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $2000 | 7680.91 | 11448.94 | 0.4153 | 0.5015 | 17293.512 | 4.3841 | 0.0971 | 0.1123 | True | False | {1: 29, 2: 70, 3: 64} |
| $10000 | 14064.71 | 14536.61 | 0.449 | 0.4571 | 21053.1736 | 21759.5511 | 0.0524 | 0.0524 | True | True | {3: 159, 4: 4, 5: 2} |
| $25000 | 25598.82 | 27565.45 | 0.5052 | 0.4922 | 5.8378 | 4.9734 | 0.0511 | 0.0506 | True | True | {3: 54, 4: 33, 5: 26, 6: 22, 7: 12, 8: 7, 9: 5, 10: 1, 11: 3, 12: 1, 14: 1} |

## Disclosure

- **overlay_logic:** BYTE-FOR-BYTE _volranker_sizing.{run_cell, overlay_contracts, _improvement_verdict, causal_terciles}; only the BASE fraction rebound
- **base_rebind:** VR._base_fraction + VR.flat_contracts rebound to quarter-Kelly per account (the established module-global rebind pattern, cf. --sweep TERCILE_MULT); restored after each account
- **kelly:** f_quarter_kelly = _b10_sizing.kelly_fraction(trade_return_stats(IS_trades)); continuous m/v capped at discrete two-outcome, /4 — conservative
- **oos_honesty:** f_qk computed on IS-2025 ONLY, frozen for OOS; FLAT baseline is QK-flat (mult 1.0), so the verdict isolates the TERCILE modulation, not the Kelly level (B10 already covered the level)
- **caps:** Rule-6 clamp = _b10_sizing.contracts_from_fraction; audited 0 breaches; never-zero
- **research_only:** no watcher/params/risk_gate/heartbeat edit, no orders, no commit
- **spy_vs_option:** C3/L58 — overnight-FLOW ranker validated on the OPTION P&L
