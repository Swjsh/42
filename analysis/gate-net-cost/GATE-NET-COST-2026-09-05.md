# GATE-NET-COST-2026-09-05

Session a16e320c, 2026-09-05 ~03:5x ET (`et_clock.py` quoted: `2026-09-05 03:54:48 Saturday EDT`).

## Status: N1 DONE, N2/N3 NOT COMPUTED, N4/N5 NOT STARTED (honest partial)

This goal asked for a full per-gate NET (winners $ minus losers $, walked through each
refusing arm's real exit shape on OPRA bars) so the two 10-30 preregs and the standing
structure-veto A/B could be decided net-of-losers instead of on the refused-winners CEILING
alone. **Only the refusal inventory (N1) was completed this pass.** The exit-shape walk (N2),
the resulting net table (N3), the prereg evidence appends + `checkpoint_packet.py` swap (N4),
and the cockpit tile + doctrine append (N5) were **not** completed, and are reported that way
rather than filled in with invented numbers.

**Why stopped here, stated honestly:** N2 requires assembling, per refused wave, per arm
(up to 4 arms x ~340 waves across the 20 gate/arm buckets below), the option-bar series +
ribbon-tick series + 5-min SPY series `backtest/lib/exit_manager_walk.walk_exit_manager`
needs, then running that arm's REAL `exit_shape` (read-only from
`automation/state/fleet/strategies.py`/`exit_manager.py`) tick-by-tick, plus the goal's
mandatory 2 hand-checked examples against real same-day fills in `journal/trades.csv`. That
is a multi-hour build (data assembly + the walk + the hand-check verification), not something
that can be done credibly -- to the goal's own "quote both hand-checks" bar -- inside this
bounded pass without either skipping the verification step or fabricating numbers. Per the
project's own anti-fabrication rule (no placeholder/fake data in any real code path, especially
one three pre-registered decisions read from), the responsible move is to ship N1 real and
flag N2-N5 for a dedicated follow-up session, not to synthesize a "net" figure.

## N1 -- refusal inventory (DONE, quoted from `setup/scripts/gate_net_cost_inventory.py` /
`analysis/gate-net-cost/refusals-2026-09-05.json`)

Window: 2026-08-01 -> 2026-09-05. Frozen window: 2026-08-31 -> 2026-09-05. Waves are
deduped using the same 30-minute same-episode grouping `backtest/lib/right_tail_waves.py`
uses (`WAVE_GAP_MINUTES = 30`).

| Gate / arm | Source | Refusal rows | Waves (full) | Waves (frozen) |
|---|---|---|---|---|
| SKIP_STRUCTURE_VETO (core) | core-decisions.jsonl verdict | 93 | 15 | 4 |
| SKIP_LATE_ENTRY (core) | core-decisions.jsonl verdict | 86 | 10 | 2 |
| SKIP_STALE_TRIGGER (core) | core-decisions.jsonl verdict | 314 | 30 | 5 |
| SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY (core) | core-decisions.jsonl verdict | 121 | 23 | 5 |
| SKIP_MIN_PREMIUM_FLOOR (core) | core-decisions.jsonl verdict | 51 | 15 | 7 |
| settlement cap (core, RISK_DENY_SETTLEMENT) | core-decisions.jsonl verdict | 33 | 5 | 3 |
| NOT_FLAT (core) | core-decisions.jsonl verdict | 449 | 48 | 10 |
| min_triggers, risky-1 | fleet decisions.jsonl reason "gate: 1 triggers < 2" | 112 | 16 | 5 |
| require_confluence_or_sequence, risky-1 | fleet decisions.jsonl reason | 204 | 9 | 4 |
| min_triggers, safe-3 | fleet decisions.jsonl reason | 180 | 22 | 5 |
| require_confluence_or_sequence, safe-3 | fleet decisions.jsonl reason | 284 | 15 | 4 |
| SKIP_MIN_PREMIUM_FLOOR, risky-1 | fleet decisions.jsonl reason | 41 | 6 | 1 |
| SKIP_MIN_PREMIUM_FLOOR, risky-3 | fleet decisions.jsonl reason | 235 | 34 | 0 |
| SKIP_MIN_PREMIUM_FLOOR, safe-3 | fleet decisions.jsonl reason | 39 | 5 | 1 |
| NOT_FLAT, risky-1 | fleet decisions.jsonl reason | 347 | 37 | 5 |
| NOT_FLAT, risky-3 | fleet decisions.jsonl reason | 216 | 25 | 0 |
| NOT_FLAT, safe-3 | fleet decisions.jsonl reason | 258 | 33 | 5 |
| settlement cap, risky-1 | fleet decisions.jsonl reason | 32 | 3 | 3 |
| settlement cap, risky-3 | fleet decisions.jsonl reason | 5 | 1 | 0 |
| settlement cap, safe-3 | fleet decisions.jsonl reason | 32 | 3 | 3 |

**fleet gate_override (`min_triggers`/`require_confluence_or_sequence`) is NOT tracked by
`fleet-gate-leak-ledger.jsonl`** -- that ledger only instruments 4 different gates
(`require_bearish_fill_bar`, `structure_veto_enabled`, `block_bull_1100_1200`,
`block_conf_lvl_rec_afternoon`), confirmed by tallying its `gate_param_key` values this
session (`require_bearish_fill_bar` 364, `structure_veto_enabled` 220,
`block_bull_1100_1200` 212, `block_conf_lvl_rec_afternoon` 204, none named `min_triggers`).
The two selectivity gates the goal actually named only surface as free-text `reason` strings
in each fleet arm's own `decisions.jsonl` (`"gate: 1 triggers < 2"`,
`"gate: requires confluence/sequence"`) -- this is a real gap in the shadow ledger's coverage,
worth its own follow-up, not something this pass can silently paper over.

**filter 8 / filter 10** (bear/bull min-triggers volume-multiplier blockers): NOT COMPUTED.
Verified this session that blocker code 10 (bull) fires on 4,288 of 6,068 core-decisions rows
since 2026-08-01, and code 8 (bear) on 5,896 of 6,068 -- i.e. these blockers are present on
the large majority of every tick regardless of whether the tick was otherwise ENTER-eligible.
Isolating "ENTER-eligible but for this blocker alone" needs a full replay of
`backtest/lib/filters.py`'s per-side gate stack at each tick (score AND every OTHER blocker
state), which is out of scope for this pass and would risk a wrong number if rushed.

**Cross-check (goal DONE-WHEN for N1):** the right-tail 46-missed-pair attribution
(`analysis/right-tail/CAPTURE-GAP-2026-09-05.json` / `capture-gap-join-2026-09-05.json`, 24
unique wave ids) is a **strict subset** of this inventory: `n_present_in_my_inventory: 24,
n_missing: 0, strict_subset: true` (join method: a capture-gap wave id counts as present if
any refusal tick this script found on the same date falls within the same 30-minute
`WAVE_GAP_MINUTES` tolerance right_tail_waves.py itself uses -- an exact-string match on
`wave_start_et` under-matches because the refusal tick's own timestamp is the SKIP tick, not
the ENTER tick on the arm that DID take the wave).

## N2 -- exit-shape walk: NOT COMPUTED. No hand-checks quoted (goal requires 2; zero done).

## N3 -- per-gate net table: all `winners_$`/`losers_$`/`net_$`/`ex_best_day_net_$` cells are
`null` in `GATE-NET-COST-2026-09-05.json` by construction -- see that file. No gate is called
EARNING or COSTING; every row is `UNDERPOWERED_NO_WALK` (n < 10 waves) or `NO_WALK` (n >= 10
waves but not walked) rather than assigning a verdict this pass cannot support.

## N4 / N5 -- NOT STARTED

No prereg was touched. No `checkpoint_packet.py` edit was made. No cockpit change was made.
No doctrine append was made. These all consume N2/N3's numbers as their evidentiary basis;
touching decision-facing files (preregs gating a 10-30 packet, `checkpoint_packet.py`,
`edge-master-doctrine.md`) with unwalked numbers would be worse than leaving them untouched.

## Recommendation

Continue N2-N5 as a dedicated follow-up fire with its own budget: build a small
`gate_net_cost_walker.py` that, per (gate, arm, wave) row in `refusals-2026-09-05.json`,
loads `option_pricing_real.load_contract_bars` for the ATM/near-ATM contract at the wave's
strike (same convention as `zero_enter_autopsy.py`), the matching 5-min SPY series, and a
ribbon-tick series, resolves that arm's real `exit_shape` from
`automation/state/fleet/strategies.py` (READ-ONLY), and calls
`backtest/lib/exit_manager_walk.walk_exit_manager(..., all_exits_market=True)` per the goal's
OPERATING RULES; hand-check 2 walked rows against `journal/trades.csv` fills on the same
day/side before trusting the aggregate; only then touch the 3 preregs / `checkpoint_packet.py`
/ cockpit / doctrine.
