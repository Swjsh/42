# RIBBON-FLIP-BACK INVALIDATION BUFFER A/B -- real-fills pain-ledger anchor (2026-08-08)

Generated 2026-08-08T03:38:59.558263. Runner: `backtest/tools/ribbon_flipback_buffer_ab.py`. Pre-reg: `analysis/recommendations/prereg-ribbon-flipback-buffer-2026-08-08.json`.

## OVERALL VERDICT: **UNDERPOWERED**

## Control semantics (quoted verbatim per the prereg)

As literally implemented by backtest/lib/exit_manager_walk.py:292-297 (ribbon_stack_at): flip = (stack=='BULL') if side=='P' else (stack=='BEAR'), where 'stack' is the aligned ribbon_tick_df's categorical column at this tick. RAW single-bar test: NO price buffer, NO confirming-close count, NO spread_cents gate. This differs from simulator_real.py's precedented opposite_stack + spread_cents>=ribbon_flip_back_min_spread_cents(30c) + optional $0.50 entry-anchored RIBBON_FLIP_PRICE_BUFFER, and from params.json's declared-but-BARE ribbon_flip_back_requires_opposite_stack/ribbon_flip_back_min_spread_cents knobs -- walk_exit_manager consumes neither. This study's CONTROL reproduces exit_manager_walk's raw derivation exactly; the spread_cents gate is NOT part of this frozen grid (buffer x confirm only, per candidates_frozen.grid).

## Stop-rule evaluation

prereg stop_rule triggers only if 'the current flip-back derivation has no coherent surface for a price buffer'. FALSE here: entry_spot is recovered via exit_manager_walk.last_closed_bar_close_at (no-lookahead) and ribbon.py's compute_ribbon exposes a real SPY-dollar spread_cents alongside 'stack' -- the caller-side ribbon_tick_df construction below builds a coherent, no-lookahead numeric boundary-distance surface. STOP_RULE NOT TRIGGERED -- candidates ran.

Population: 219 replayed (0 no-bars, 0 no-SPY-ribbon-coverage), 2026-06-26..2026-08-07, arms=['bold-2', 'risky-1', 'risky-3', 'safe-1', 'safe-2', 'safe-3']. CONTROL total = $-614.38, ribbon_flip_back fired on 10 control replays.

## Candidates

| id | buffer $ | confirm closes | n | n changed | power floor | control $ | candidate $ | delta | verdict |
|---|--:|--:|--:|--:|:--:|--:|--:|--:|:--:|
| BUF0.15-C0 | 0.15 | 1 | 219 | 10 | False | $-614.38 | $-790.08 | $-175.70 | **UNDERPOWERED** |
| BUF0.15-C1 | 0.15 | 2 | 219 | 10 | False | $-614.38 | $-790.08 | $-175.70 | **UNDERPOWERED** |
| BUF0.30-C0 | 0.3 | 1 | 219 | 10 | False | $-614.38 | $-790.08 | $-175.70 | **UNDERPOWERED** |
| BUF0.30-C1 | 0.3 | 2 | 219 | 10 | False | $-614.38 | $-790.08 | $-175.70 | **UNDERPOWERED** |
| BUF0.50-C0 | 0.5 | 1 | 219 | 10 | False | $-614.38 | $-790.08 | $-175.70 | **UNDERPOWERED** |
| BUF0.50-C1 | 0.5 | 2 | 219 | 10 | False | $-614.38 | $-790.08 | $-175.70 | **UNDERPOWERED** |

## Gates (per candidate)

| id | G1 agg | G2 chop | G3 runner+anchor | G4 subwindow | G5 drop-best-day | G6 worst-day | G7 per-account | G8 BH-FDR sig |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| BUF0.15-C0 | False | False | True | False | False | True | False | False (p=None) |
| BUF0.15-C1 | False | False | True | False | False | True | False | False (p=None) |
| BUF0.30-C0 | False | False | True | False | False | True | False | False (p=None) |
| BUF0.30-C1 | False | False | True | False | False | True | False | False (p=None) |
| BUF0.50-C0 | False | False | True | False | False | True | False | False (p=None) |
| BUF0.50-C1 | False | False | True | False | False | True | False | False (p=None) |

## Disclosures

- population loser-skew (169L/39W/11S) + single-regime ~6-week window ({'n_frozen_target': 219, 'n_reconstructed_total': 221, 'n_matched': 219, 'n_unmatched_target_keys': 0}) -- IS/OOS-style sub-window labels overstate independence (all one continuous live period, not two independent samples).
- setup-family x account confound: {"BEARISH_REJECTION_RIDE_THE_RIBBON": {"bold": 29, "safe": 24}, "BULLISH_RECLAIM_RIDE_THE_RIBBON": {"safe": 53, "bold": 60}, "(unattributed)": {"safe": 35, "bold": 1}, "VWAP_CONTINUATION": {"bold": 17}}
- stop_mode unrecoverable for 107/219 -- shapes resolved via winner_autopsy.resolve_shipped_shape fallback (mae-mfe.json's own stop.stop_mode_source=='unrecoverable'), counted not dropped.
- 1-min OPRA point-sample convention per walk_exit_manager (bar OPEN used as both best/worst -- OPTION-BAR-RESOLUTION-BIAS-2026-08-02); market-style stages (ribbon_flip/structure_stop/time_stop) fill at that bar's close minus $0.02 slippage; limit-style stages (tp1/premium_stop/trail/runner_target) fill exactly at the triggered premium level.
- G3's 'J-anchor' set is bold_fullhist_replay.py's ANCHOR_FILLS (the only individually-flagged real-trade regression set in this exit-replay family) -- an interpretive choice disclosed here since the prereg does not name a specific list; 10.00-dollar noise tolerance per anchor.
- SAFE_ARMS={safe-1,safe-2,safe-3} / BOLD_ARMS={bold-2,risky-1,risky-3} for G7 -- matches the codebase's standing safe-vs-aggressive(risky/bold) account-family naming; not a new taxonomy.
- entry_spot (the buffer's price anchor) is unrecoverable for any position whose entry timestamp precedes the first CLOSED 5m SPY bar in-sample -- those positions fail-CLOSED on the buffer axis (candidate flip can never fire), never silently reverting to the unbuffered control behavior.
- GRID-COLLAPSE FINDING (investigated per fable-too-good discipline before reporting, NOT a code bug): all 6 candidates produced BYTE-IDENTICAL per-position PnL on 219/219 positions (fully collapsed: True). Verified via (a) backtest/tests/test_ribbon_flipback_buffer_ab.py's synthetic buffer/confirm differentiation unit tests, which DO show the suppression mechanism correctly varying with buffer_dollars/confirm_closes on constructed fixtures (21/21 pass); (b) manual per-position trace of 2 of the 10 CONTROL-flip-firing positions -- both show every buffer threshold (0.15/0.30/0.50) and confirm tier (1/2 closes) getting satisfied on the SAME single 5-min-bar step (a decisive break, or a put entered directly against an already-49-bar-old BULL ribbon), so a suppressed flip is always delayed onto the SAME downstream premium_stop event regardless of which of the 6 grid points suppressed it. Only 10/219 CONTROL replays ever fired a raw ribbon_flip_back exit at all -- the population's raw flip-event rate is the binding constraint, not this runner's mechanism; every candidate is UNDERPOWERED (n_changed=10 < power_floor=15) as a direct consequence.

---
_Source: `backtest/tools/ribbon_flipback_buffer_ab.py`. Full per-position detail in the companion `.json`._
