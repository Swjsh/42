# Bold full-history replay -- CURRENT LIVE core-Bold engine, 2025-01-02..2026-07-22

Generated 2026-08-01T12:27:24.365422. Runner: `backtest/tools/bold_fullhist_replay.py`.
Account: core_bold (Gamma-Bold-2, PA33W2KUAT40). Equity used: $1,197.52 (mcp__alpaca_aggressive__get_account_info, live-verified 2026-08-01 this session).

Full translation table + methodology: `analysis/deep-research/BOLD-HARNESS-2026-08-01.md`.

## Gate-state comparison (task requirement: gate state as an input)

| Gate state | block_elite_bull | N trades | Total P&L | WR | Avg/trade |
|---|---|---|---|---|---|
| pre_trial_block_elite_bull_true | True | 156 | $+7,448.40 | 0.3333 | $+47.75 |
| post_trial_block_elite_bull_false | False | 202 | $+6,490.80 | 0.302 | $+32.13 |

## Anchor validation (OP-16 sim-accuracy gate, task step 3)

**6/7 real bold-2 engine fills reproduce within tolerance. ALL PASS: False.**

> pass = same win/loss sign AND |replay-real| <= max($60.0, 30% of |real|) -- exact-cent parity not expected, see exit_manager_walk.py's own FILL-PRICE CONVENTION docstring (resting-order-limit-fill approximation, real fills reflect live spread/timing)

| Date | Symbol | Real P&L | Replay P&L | Same sign | Within tol | PASS |
|---|---|---|---|---|---|---|
| 2026-06-26 | SPY260626P00729000 | $-15.00 | $-21.00 | True | True | PASS |
| 2026-07-02 | SPY260702P00743000 | $-60.00 | $-48.00 | True | True | PASS |
| 2026-07-02 | SPY260702P00740000 | $+290.00 | $+218.80 | True | True | PASS |
| 2026-07-17 | SPY260717P00743000 | $+191.00 | $+177.40 | True | True | PASS |
| 2026-07-23 | SPY260723P00735000 | $-305.00 | $-390.00 | True | True | PASS |
| 2026-07-27 | SPY260727P00737000 | $-355.00 | $-325.00 | True | True | PASS |
| 2026-07-28 | SPY260728C00741000 | $-295.00 | $-185.00 | True | False | FAIL |

## First consumer: elite-bull blocked-cohort re-run under the TRUE bold shape (task step 4)

Source study: `analysis\recommendations\elite-bull-requal-2026-07-31.json` (verdict `a`, primary cell `safe_sequential_hold_qty3`).

**MISLABELED: the trial armed on aggressive/params.json (bold-2 account) was justified by verdict_rule_inputs.primary_cell='safe_sequential_hold_qty3' -- SAFE's blocked-signal cohort, not bold-2's own. Bold's OWN cohort (bold_sequential_hold_qty3) was reported in the same file but never used as the frozen verdict rule's PRIMARY input.**

- Friday's cited PRIMARY (SAFE's cohort, qty3): n=5 total=$+867.00
- Bold's OWN cohort at the study's qty3: sequential-hold n=5 total=$-2.60 drop-best=$-321.00
- **Bold's OWN cohort at TRUE qty=5, independent-replay-authoritative (this tool)**: sequential-hold n=5 total=$+7.80 drop-best=$-535.00 (analytic 5/3 rescale cross-check: $-4.33 -- linearity held exactly: False; where it doesn't, TP1/runner integer-split truncation is the cause, see tool docstring)
- Fleet net (unchanged, proxy arms not bold-2 itself): $+1242.00

**Corrected verdict using Bold's own cohort as primary: `a` (LIFT_GATE_TRIAL supported)**

Friday's cited evidence (+$867.00, n=5) was SAFE's cohort, not bold-2's own. Bold's OWN cohort at its TRUE qty=5 sizing (independent re-replay, authoritative -- the analytic 5/3 rescale cross-check gives $-4.33, a close but NOT exact match: TP1/runner qty-splits at int(qty*0.667) differ 2/1 at qty3 vs 3/2 at qty5, so winners that reach TP1 scale super-linearly) is $+7.80 (n=5) -- a COIN-FLIP total, not a robust positive -- with drop-best $-535.00: ONE single trade (07-31 12:16 C744, +$542.80) IS the entire positive total; remove it and the cohort is deeply red. The frozen verdict rule (verdict_rule_frozen in the prereg) tests SIGN ONLY (primary_total>0 AND fleet_net>0 => 'a'), so it still mechanically outputs 'a' here -- $7.80 and $867.00 both clear '>0'. LOUD FLAG (task's own explicit trigger: drop-best negative): the rule's sign-only test is blind to the fact that Bold's OWN true evidence is a razor-thin coin flip resting on a single trade, with the other 4 losing -$542.80 combined -- a dramatically weaker and more concentrated picture than the +$867/n=5/drop-best+$177 Friday actually saw (that number was never bold-2's own to begin with). The trial's forward kill-criterion (n>=10 fills OR 10 sessions, net<0 -> re-block) still stands as the LIVE guard and is doing real work here -- but J should know the armed trial's disclosed justification was a different account's number, and bold-2's own number is a coin flip propped up by one trade.

---
_Source: `backtest/tools/bold_fullhist_replay.py`. Raw JSON: `analysis/recommendations/bold-fullhist-replay-2026-08-01.json`._
