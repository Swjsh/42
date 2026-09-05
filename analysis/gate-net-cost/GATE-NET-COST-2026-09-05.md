# GATE-NET-COST-2026-09-05

N3 -- per-gate net-of-losers table, GOAL-GATE-NET-COST-2026-09-05. Built from `analysis\gate-net-cost\walk-2026-09-05.json` (305 walk_ok / 50 walk_error rows) by `setup/scripts/gate_net_cost_table.py`.

## Definition used for the $ number

- **Winner:** `realized_if_taken_dollars > 0`. **Loser:** `realized_if_taken_dollars <= 0`.
- **Net:** `sum(realized_if_taken_dollars) over all walk_ok rows == winners_dollars + losers_dollars`.
- **Why realized, not peak:** a wave can peak >= 1.3x and still reverse before the walked exit stage fires; using realized (not peak) avoids crediting a reversal as a win. n_waves_peak_ge_1p3x is reported alongside as the alternate/ceiling metric.
- **Verdict rule:** net_dollars < 0 -> EARNING (refusing saved money); net_dollars > 0 -> COSTING (refusing lost money); n_waves < floor -> UNDERPOWERED regardless of sign. (UNDERPOWERED floor = 10 waves.)

## Per gate, deduped to WAVES (one signal, up to 4 arms collapsed) -- full window 2026-08-01..today

| Gate | Arms touched | Waves | Waves peak>=1.3x | Winners $ | Losers $ | Net $ | Net $ (1-min) | Δ (1min-5min) | Ex-best-day net $ | walk_error | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| NOT_FLAT | bold-2, risky-1, risky-3, safe-2, safe-3 | 99 | 66 | $18,685.00 | $-11,142.00 | $7,543.00 | $7,726.00 | $183.00 | $2,759.00 | 1 | COSTING |
| SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY | bold-2 | 21 | 8 | $729.00 | $-1,025.00 | $-296.00 | $-128.00 | $168.00 | $-506.00 | 2 | EARNING |
| SKIP_LATE_ENTRY | safe-2 | 9 | 3 | $162.00 | $-264.00 | $-102.00 | $-276.00 | $-174.00 | $-165.00 | 1 | UNDERPOWERED |
| SKIP_MIN_PREMIUM_FLOOR | bold-2, risky-1, risky-3, safe-3 | 50 | 20 | $3,777.00 | $-2,379.00 | $1,398.00 | $1,876.00 | $478.00 | $-1,495.00 | 1 | COSTING |
| SKIP_STALE_TRIGGER | safe-2 | 1 | 1 | $898.00 | $0.00 | $898.00 | $906.00 | $8.00 | $0.00 | 29 | UNDERPOWERED |
| SKIP_STRUCTURE_VETO | safe-2 | 7 | 2 | $241.00 | $-396.00 | $-155.00 | $123.00 | $278.00 | $-303.00 | 8 | UNDERPOWERED |
| min_triggers | risky-1, safe-3 | 20 | 14 | $2,791.00 | $-2,275.00 | $516.00 | $544.00 | $28.00 | $-66.00 | 4 | COSTING |
| require_confluence_or_sequence | risky-1, safe-3 | 13 | 5 | $1,669.00 | $-3,475.00 | $-1,806.00 | $-856.00 | $950.00 | $-2,700.00 | 4 | EARNING |
| settlement_cap | bold-2, risky-1, risky-3, safe-2, safe-3 | 9 | 1 | $50.00 | $-1,381.00 | $-1,331.00 | $-624.00 | $707.00 | $-1,271.00 | 0 | UNDERPOWERED |

1-min column source: `analysis\gate-net-cost\walk-2026-09-05-1min.json` (GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3 -- same _agg definition, full window only, gates with no 1-min-walked rows show n/a rather than a fabricated 0).

## Per gate, deduped to WAVES -- frozen window 2026-08-31..today

| Gate | Waves | Waves peak>=1.3x | Winners $ | Losers $ | Net $ | Ex-best-day net $ | Verdict |
|---|---|---|---|---|---|---|---|
| NOT_FLAT | 14 | 4 | $1,384.00 | $-2,015.00 | $-631.00 | $-974.00 | EARNING |
| SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY | 3 | 1 | $163.00 | $-180.00 | $-17.00 | $-85.00 | UNDERPOWERED |
| SKIP_LATE_ENTRY | 1 | 0 | $0.00 | $-3.00 | $-3.00 | $0.00 | UNDERPOWERED |
| SKIP_MIN_PREMIUM_FLOOR | 7 | 0 | $0.00 | $-788.00 | $-788.00 | $-683.00 | UNDERPOWERED |
| SKIP_STALE_TRIGGER | 0 | 0 | $0.00 | $0.00 | $0.00 | $0.00 | UNDERPOWERED |
| SKIP_STRUCTURE_VETO | 3 | 1 | $78.00 | $-135.00 | $-57.00 | $0.00 | UNDERPOWERED |
| min_triggers | 3 | 2 | $694.00 | $-464.00 | $230.00 | $-136.00 | UNDERPOWERED |
| require_confluence_or_sequence | 2 | 2 | $475.00 | $-336.00 | $139.00 | $-336.00 | UNDERPOWERED |
| settlement_cap | 6 | 1 | $50.00 | $-1,225.00 | $-1,175.00 | $-1,087.00 | UNDERPOWERED |

## Per gate x arm rows (raw table rows, NOT wave-deduped -- full window)

| Gate | Arm | Arm rows | Waves | Winners $ | Losers $ | Net $ | Ex-best-day net $ | walk_error | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| NOT_FLAT | bold-2 | 12 | 12 | $867.00 | $-325.00 | $542.00 | $258.00 | 0 | COSTING |
| NOT_FLAT | risky-1 | 37 | 37 | $8,306.00 | $-4,620.00 | $3,686.00 | $1,733.00 | 0 | COSTING |
| NOT_FLAT | risky-3 | 25 | 25 | $2,349.00 | $-1,460.00 | $889.00 | $93.00 | 0 | COSTING |
| NOT_FLAT | safe-2 | 35 | 35 | $3,087.00 | $-2,301.00 | $786.00 | $112.00 | 1 | COSTING |
| NOT_FLAT | safe-3 | 33 | 33 | $4,076.00 | $-2,436.00 | $1,640.00 | $505.00 | 0 | COSTING |
| SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY | bold-2 | 21 | 21 | $729.00 | $-1,025.00 | $-296.00 | $-506.00 | 2 | EARNING |
| SKIP_LATE_ENTRY | safe-2 | 9 | 9 | $162.00 | $-264.00 | $-102.00 | $-165.00 | 1 | UNDERPOWERED |
| SKIP_MIN_PREMIUM_FLOOR | bold-2 | 14 | 14 | $249.00 | $-1,100.00 | $-851.00 | $-1,004.00 | 1 | EARNING |
| SKIP_MIN_PREMIUM_FLOOR | risky-1 | 6 | 6 | $2,176.00 | $-90.00 | $2,086.00 | $-5.00 | 0 | UNDERPOWERED |
| SKIP_MIN_PREMIUM_FLOOR | risky-3 | 34 | 34 | $571.00 | $-1,135.00 | $-564.00 | $-723.00 | 0 | EARNING |
| SKIP_MIN_PREMIUM_FLOOR | safe-3 | 5 | 5 | $781.00 | $-54.00 | $727.00 | $-3.00 | 0 | UNDERPOWERED |
| SKIP_STALE_TRIGGER | safe-2 | 1 | 1 | $898.00 | $0.00 | $898.00 | $0.00 | 29 | UNDERPOWERED |
| SKIP_STRUCTURE_VETO | safe-2 | 7 | 7 | $241.00 | $-396.00 | $-155.00 | $-303.00 | 8 | UNDERPOWERED |
| min_triggers | risky-1 | 14 | 14 | $1,371.00 | $-1,195.00 | $176.00 | $-192.00 | 2 | COSTING |
| min_triggers | safe-3 | 20 | 20 | $1,420.00 | $-1,080.00 | $340.00 | $-5.00 | 2 | COSTING |
| require_confluence_or_sequence | risky-1 | 7 | 7 | $683.00 | $-1,705.00 | $-1,022.00 | $-1,461.00 | 2 | UNDERPOWERED |
| require_confluence_or_sequence | safe-3 | 13 | 13 | $986.00 | $-1,770.00 | $-784.00 | $-1,239.00 | 2 | EARNING |
| settlement_cap | bold-2 | 1 | 1 | $50.00 | $0.00 | $50.00 | $0.00 | 0 | UNDERPOWERED |
| settlement_cap | risky-1 | 3 | 3 | $0.00 | $-715.00 | $-715.00 | $-660.00 | 0 | UNDERPOWERED |
| settlement_cap | risky-3 | 1 | 1 | $0.00 | $-60.00 | $-60.00 | $0.00 | 0 | UNDERPOWERED |
| settlement_cap | safe-2 | 4 | 4 | $0.00 | $-177.00 | $-177.00 | $-96.00 | 0 | UNDERPOWERED |
| settlement_cap | safe-3 | 3 | 3 | $0.00 | $-429.00 | $-429.00 | $-396.00 | 0 | UNDERPOWERED |

## /fable-too-good disclosure -- gates with |net| > $3,000 (full window)

### NOT_FLAT -- net $7,543.00 (ex-best-day $2,759.00, best day 2026-08-04 contributed $4,784.00)
**CONCENTRATION FLAG:** the single best wave-day contributes >= 50% of this gate's net -- one day dominates; treat the aggregate with suspicion per `/fable-too-good`.

| Wave id | Arm | Contract | Side | Entry $ | Exit stage | Exit $ | Realized $ | Peak x |
|---|---|---|---|---|---|---|---|---|
| 2026-08-03|2026-08-03T09:44:03.812734-04:00 | risky-1 | SPY260803C00752000 | C | 1.29 | time_stop | 6.09 | $1,176.00 | 5.0465 |
| 2026-08-28|2026-08-28T10:23:05.698823-04:00 | risky-1 | SPY260828C00771000 | C | 1.48 | trail | 3.41 | $875.00 | 2.75 |
| 2026-08-04|2026-08-04T11:28:05.337509-04:00 | risky-1 | SPY260804C00767000 | C | 1.37 | trail | 4.51 | $832.00 | 4.1898 |


## N1 coverage notes (carried forward from `refusals-2026-09-05.json` / prior revision of this file -- unchanged by N3)

- **fleet gate_override (`min_triggers`/`require_confluence_or_sequence`) is NOT tracked by `fleet-gate-leak-ledger.jsonl`** -- that ledger only instruments 4 other gates (`require_bearish_fill_bar`, `structure_veto_enabled`, `block_bull_1100_1200`, `block_conf_lvl_rec_afternoon`); the two selectivity gates this goal names were recovered instead from each fleet arm's own `decisions.jsonl` free-text `reason` strings (`"gate: 1 triggers < 2"`, `"gate: requires confluence/sequence"`) -- a real ledger-coverage gap, disclosed rather than papered over.
- **filter 8 / filter 10** (bear/bull min-triggers volume-multiplier blockers) were NOT COMPUTED by N1's wave inventory (fire on the large majority of every tick regardless of ENTER-eligibility -- isolating the true refusal population needs a full `backtest/lib/filters.py` gate-stack replay, out of scope for this goal). The SIDE-TASK fix in this same session touches `gate_expiry_check.py`'s OWN separate sole-blocker instrument for filter-8/filter-10 (its `_stop_level_for_row` side-blind bug) -- that check remained RED after the fix (re-run below) for reasons independent of the fix (the sole-blocker path is a `NOT_REPLAYED` proxy that never calls `_stop_level_for_row`).

## Error bar (T3, 1-min vs 5-min resolution bias)

Of 305 rows N2 walked OK on 5-min OPRA bars, 305 already have a 1-minute OPRA cache on disk (`backtest/data/highres/`) -- re-walked via the SAME `walk_exit_manager` core (`gate_net_cost_walk._walk_entry`, `opt_df_resolution="1min"`), zero new fetch. 305 of those re-walked successfully.

| Exit stage | n | mean $ delta (5min-1min) | median $ delta | 5min overstates | 5min understates | sign-consistency |
|---|---|---|---|---|---|---|
| premium_stop | 109 | $-42.61 | $-20.00 | 34 | 72 | 66.06% |
| ribbon_flip | 23 | $-14.78 | $-18.00 | 8 | 15 | 65.22% |
| structure_stop | 66 | $-8.80 | $-1.50 | 28 | 33 | 50.00% |
| time_stop | 30 | $14.07 | $-7.00 | 13 | 17 | 56.67% |
| trail | 77 | $44.17 | $13.00 | 43 | 32 | 55.84% |
| **ALL STAGES** | 305 | $-5.71 | $-5.00 | 126 | 179 | 55.41% |

Exit stage changed between the 5-min and 1-min walk on 45 of 305 rows.

This section is APPENDED by `setup/scripts/gate_net_cost_resolution_bias.py` (T3, GOAL-RIGHT-TAIL-FOLLOWUPS-2026-09-05) and is idempotent -- a re-run replaces this section in place rather than duplicating it.
