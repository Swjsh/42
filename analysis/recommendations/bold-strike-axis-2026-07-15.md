# BOLD strike-axis A/B — BOLD-STRIKE-X-FLOOR-COLLISION

Generated: 2026-07-15T17:16:03.363825. Source: `backtest/tools/bold_strike_axis_ab.py`. Pre-reg: `analysis/recommendations/prereg-bold-strike-axis-2026-07-15.json`.

## TL;DR

**NULL RESULT at the pre-registered 5-gate bar — nothing SHIPS tonight.** But the study confirms the incident is real and structural, not a one-off: OTM-3 (Bold's current live <$2K tier) clears the min_entry_premium floor on only **41.7%** of its opportunities overall and **33.8%** in the afternoon, and is an economic loser on top of that (expectancy -$10.81/tr, OOS -$14.37/tr). **ATM is the evidence-backed near-miss** — beats OTM-3 on OOS expectancy (+$28.77/tr), clears BH-FDR, the anchor, sub-window stability, and the floor (97-98%) — and fails ONLY the walk-forward gate, which this study shows is **structurally unreachable for ALL 6 cells** (every cell's 2025 in-sample half is net-negative under Bold's real SS-B/friction/floor convention, cross-confirmed against the Safe reconciliation study's job1a, which shows the identical `wf: null` pattern on its own 4 cells). See `near_miss_diagnostic` in the JSON for the one-line diff + guard-test spec, drafted and ready but **NOT applied**. Full per-cell numbers below.

**Signal cohort:** n=250 (call/bull=59, put/bear=191). Control: **OTM-3** (Bold's current live <$2K tier).

**Method:** SS-B exit shape (structure-stop chart layer ON) + honest friction + time_stop=15:40:00 ET + qty=5 (Bold's real live size) + min_entry_premium floor=0.3 applied IN-SIM + BH-FDR (alpha=0.1) across all 6 cells.

## Per-cell table

| strike | n | exp $/tr | OOS exp $/tr | WR | OOS+ | WF | sub_win | anchor_ok | bh_survivor | floor_clear | floor_clear_PM | n_opp | n_opp_PM |
|---|--:|--:|--:|--:|:--:|--:|:--:|:--:|:--:|--:|--:|--:|--:|
| OTM-3 (control) | 100 | $-10.81 | $-14.37 | 0.3 | False | None | False | True | False | 0.4167 | 0.3376 | 240 | 157 |
| OTM-2 | 157 | $-8.77 | $-3.04 | 0.325 | False | None | False | False | False | 0.628 | 0.5276 | 250 | 163 |
| OTM-1 | 201 | $0.4 | $19.12 | 0.313 | True | None | False | True | True | 0.8072 | 0.7099 | 249 | 162 |
| ATM | 239 | $8.3 | $28.77 | 0.335 | True | None | True | True | True | 0.9795 | 0.9688 | 244 | 160 |
| ITM-1 | 237 | $7.71 | $94.48 | 0.346 | True | None | False | True | False | 1.0 | 1.0 | 237 | 156 |
| ITM-2 | 231 | $-2.56 | $86.05 | 0.372 | True | None | False | True | True | 1.0 | 1.0 | 231 | 152 |

## Decisions (per candidate, vs OTM-3 control)

- **OTM-2**: beats_control_OOS=True, can_actually_trade=False, **ship_ready=False** -- fails: ['B_gate_fail_oos_positive', 'B_gate_fail_wf_ge_070', 'B_gate_fail_sub_window_stable', 'B_gate_fail_anchor_no_regression', 'B_gate_fail_bh_fdr_survivor', 'C_floor_clearance_below_70pct_overall_or_afternoon']
- **OTM-1**: beats_control_OOS=True, can_actually_trade=True, **ship_ready=False** -- fails: ['B_gate_fail_wf_ge_070', 'B_gate_fail_sub_window_stable']
- **ATM**: beats_control_OOS=True, can_actually_trade=True, **ship_ready=False** -- fails: ['B_gate_fail_wf_ge_070']
- **ITM-1**: beats_control_OOS=True, can_actually_trade=True, **ship_ready=False** -- fails: ['B_gate_fail_wf_ge_070', 'B_gate_fail_sub_window_stable', 'B_gate_fail_bh_fdr_survivor']
- **ITM-2**: beats_control_OOS=True, can_actually_trade=True, **ship_ready=False** -- fails: ['B_gate_fail_wf_ge_070', 'B_gate_fail_sub_window_stable']

## Verdict

**NULL RESULT — no candidate clears beats-control-OOS + all 5 ratification gates + >=70% floor clearance (overall AND afternoon). Valid outcome, reported honestly, not a study failure.**

OTM-3 control's own floor-collision: floor_clearance_rate=0.4167, floor_clearance_rate_afternoon=0.3376.

**Live flip deferred per task instruction** — this study does NOT flip `crypto/lib/strike_selection.py#V15_BOLD_TIERS` or `aggressive/params.json` tonight regardless of verdict; recommendation only, for a same-morning J REVOKE window.

## Near-miss diagnostic (hand-authored, appended after the run — does not alter any number above)

**Why every cell fails gate 2 (WF):** `wf` is only defined when the IS-half (2025) per-trade mean is positive (`t4_exit_matrix.battery`'s own convention). Every one of the 6 Bold cells has a NEGATIVE 2025 mean under SS-B/honest-friction/floor, while every cell's 2026 YTD OOS half is positive-or-near-zero — so the gate is unreachable by construction for this entire cohort, not a per-cell weakness. **Cross-validated**: the Safe reconciliation study's `job1a_strike_axis_honest_ssb` (same cohort, same SS-B shape, same honest-friction convention) shows `"wf": null` for ALL 4 of ITS cells too (OTM-2/OTM-1/ATM/ITM-2) — independently confirmed on both accounts. Not patched here (the frozen pre-reg allows zero post-hoc gate changes); flagged as a future queue item.

**Watch-tier candidate: ATM.** The only cell that is `sub_window_stable=true` AND clears BH-FDR AND the anchor AND the floor (>=70% overall and afternoon) AND beats OTM-3 on OOS expectancy — fails only the structurally-unreachable WF gate. ITM-1 (+$94.48/tr OOS) and ITM-2 (+$86.05/tr OOS) post bigger headline OOS numbers but both fail `sub_window_stable` with huge first/second-half swings (ITM-1: -$5,066.8 → +$6,893.3; ITM-2: -$4,621.0 → +$4,029.1) and negative `exp_drop_top3` — a small number of concentrated days is carrying the whole result (the fable-too-good pattern the gate battery exists to catch). ITM-1 additionally misses BH-FDR. ATM's own `exp_drop_top3` is also negative (-$6.73/tr) but the smallest-magnitude of the 4 OOS-positive cells — disclosed, not hidden.

**Conditional one-line diff (drafted, NOT applied):** `crypto/lib/strike_selection.py`, `V15_BOLD_TIERS`'s first `StrikeTier` —

```
- StrikeTier(0.0,        2_000.0,     -3, "OTM-3"),
+ StrikeTier(0.0,        2_000.0,     0, "ATM"),
```

**Guard-test spec if ever shipped:** `crypto/validators/v20_strike_selection.py`'s `T1_bold_1k_bull_OTM3`/`T2_bold_1k_bear_OTM3` (currently pin strike 743/737) MUST be updated to pin strike 740/740, and `T12`'s moneyness cases for `(1_000, "C"/"P")` MUST flip from `"OTM"` to `"ATM"` — expected RED-then-GREEN per the vary-and-assert convention (C14), not a silent pass-through. A new `backtest/tests/test_bold_strike_axis_ab.py` should pin `pick_tier(1_500, V15_BOLD_TIERS).strike_offset == 0` post-flip. **Revert:** restore the `-3, "OTM-3"` tuple — instant de-arm, byte-identical to tonight's live behavior.

**Verdict label: WATCH — not ship-ready.** A near-miss worth a human/Fable look on the WF-gate question, not an auto-ship.

## Disclosures

- MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay artifact, no broker fills exist for these strike/floor combinations.
- Signals with no recoverable trigger_level fall back to SS-B's premium-only catastrophe-cap behavior (never dropped for that reason), per structure_stop_study's documented fallback contract -- same convention every study in this lineage uses.
- min_entry_premium floor is checked against the RAW entry-bar OPEN premium (before entry slippage) -- the same fill-price proxy every study in this lineage treats as the plan-time premium; friction is applied only to trades that clear the floor.
- edge_capture_rel (anchor gate) uses the account-agnostic J_WINNERS/J_LOSERS SPY-price-level pattern anchor (t4_exit_matrix.battery) at QTY=5 -- NOT directly comparable to OP-16's $1542 absolute or the Safe studies' QTY=10 figures (disclosed, not conflated); the gate itself (candidate_ecr >= control_ecr) is scale-invariant within this study.
- Random-entry null is SEED-LEVEL (20 seeds, add-one empirical p_null over seed means), drawn from Bold's OWN (09:35,15:00) ET entry gate and routed through the identical shape/time-stop/floor gate as the real cells -- distinct from a generic coin-flip.
- Risk-cap notional clamps (per_trade_risk_cap_pct, daily_loss_kill_switch_pct) are NOT modeled -- same disclosed gap every strike-AB study in this lineage carries.
- ONE process, no multiprocessing.Pool (see prereg method.process_note) -- the in-memory per-symbol OPRA bar cache is process-local; concurrent workers would multiply cache misses, not parallelize usefully, on this data source.

