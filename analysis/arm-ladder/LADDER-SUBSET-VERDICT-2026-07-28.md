# LADDER-SUBSET-PREREG verdict -- 2026-07-28

Generated 2026-07-27T22:10:16.654630. Runner: `backtest/tools/ladder_subset_prereg.py` (1.5s). Population: `analysis\arm-ladder\LADDER-FULLHIST-2026-07-27.json` lane 9.

## Verdict first

**FAIL -- the ladder concept is dead at every granularity we can currently express.** (The frozen consequence, recorded as written.)

- positive_aggregate: **False** (total -$3864.00 on 109 trades, WR 0.2202)
- day_majority: **False** (23/70 win days)
- survives_drop_best: **False** (best trade +$892.00, total minus best -$4756.00)
- held-out last 25% (cutoff 2026-03-06, reported separately per the pre-reg): 25tr +$2326.75 WR 0.4

## Frozen hypothesis (queue.md, filed 2026-07-27 ~23:35 ET at disarm time)

> entries restricted to bear_score >= 9 AND 'confluence' in bear_triggers_raw AND htf_15m == 'BEAR' at the trigger tick
>
> Pass bar: positive aggregate AND day-majority AND survives-drop-best on the SAME replay population (LADDER-FULLHIST-2026-07-27.json per-trade detail), held-out last-25% reported separately

## All cells run (nulls included)

| Cell | N | Total P&L | WR | Day-majority | Drop-best survives | Held-out (last 25%) |
|---|---|---|---|---|---|---|
| PRIMARY_lane9_subset | 109 | -$3864.00 | 0.2202 | 23/70 (False) | False | 25tr +$2326.75 |
| INTERMED_lane9_confluence_anyHTF | 165 | -$6875.60 | 0.2182 | 32/101 (False) | False | 35tr +$4043.65 |
| INTERMED_lane9_htfBEAR_anyTrigger | 226 | -$5717.45 | 0.2478 | 40/109 (False) | False | 68tr +$1381.10 |
| SENSITIVITY_lane7_subset | 51 | +$306.25 | 0.2941 | 14/41 (False) | False | 12tr +$2434.15 |
| SENSITIVITY_lane8_subset | 62 | -$2347.25 | 0.2419 | 14/43 (False) | False | 13tr +$1772.65 |

HTF-15m distribution across lane9 confluence trades: `{'MIXED': 56, 'BEAR': 109}`

## Disclosures

- **Population + serialization**: pure slice of lane 9's already-walked trades (real OPRA fills, walk_exit_manager exits). Lane 9's NOT_FLAT skipping was driven by the broader floor-9 rule, so the slice under-represents a subset-only lane's participation; a slice FAIL is still decisive on the cohort's per-trade economics (see module docstring).
- **HTF re-derivation**: _precompute_htf_15m_stacks over the reconstructed RTH frame, indexed at trigger_bar_idx -- identical code path to what fed the scoring ctx (orchestrator.py:839,970,1115). Alignment: PASS on 829 referenced bars (timestamp-exact).
- **Synthetic-priced candidates matching the subset**: 51 (disclosure only, never in P&L -- C1).
- **Incident-bar caveat**: the 2026-07-27 09:40 bar that motivated this hypothesis scores 8 (blockers [5,9]) in this replay vs 9 ([5]) live -- known feed-provenance gap (ARM-LADDER-V1-2026-07-27.md); the motivating bar itself is NOT in the population. The hypothesis was still tested exactly as frozen.
- Entry+1 convention, structure-stop RIBBON_RIDE exit shape, ATM strike, min-size 3 contracts -- all inherited unchanged from the parent replay.

## Honest read

Every cell's held-out window (last 25% by date, cutoff 2026-03-06) is POSITIVE while the full window fails all three gates -- the same signature the parent lane 9 shows (full -$10,903.50 / held-out +$2,866.00). That is a REGIME observation, reported separately exactly as the pre-registration required. It does NOT rescue the frozen hypothesis: the pass bar was the full population, and a 'recent-window-only' variant would be a NEW hypothesis needing its own pre-registration BEFORE anyone looks at how to cut the window -- this file must not be that pre-registration, because the cut is now data-suggested. The frozen consequence stands as written.

---
_Full per-trade subset detail: `analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.json` (`primary_trades`)._
