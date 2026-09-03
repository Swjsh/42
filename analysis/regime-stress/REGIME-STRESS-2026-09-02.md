# REGIME-STRESS-2026-09-02

SIM-ONLY. Measurement only -- arms nothing, gates nothing, changes no params.
Measures: `regime-stress-replay-2026-09-02`. Generated 2026-09-02T22:47:35 ET.

## Q6 PARTICIPATION (read this first)

**2 of 24 frozen stress days produced at least one ladder-permitted entry.**

Zero-entry days: 2024-08-05, 2024-09-03, 2024-12-18, 2025-03-03, 2025-03-11, 2025-03-28, 2025-04-03, 2025-04-04, 2025-04-07, 2025-04-08, 2025-04-09, 2025-04-10, 2025-04-11, 2025-04-16, 2025-04-21, 2025-10-10, 2025-11-20, 2026-03-23, 2026-03-31, 2026-04-14, 2026-04-24, 2026-06-05

Of those, **2 are DATA_MISSING** (a trigger fired but the trade was excluded for a missing OPRA contract/SPY bars, never dropped silently): 2025-03-03, 2026-06-05

A stress-day study where the engine mostly sits out is a finding about the GATES, not the exits, and must not be read as an exit result. 'Entry' here means a trade the ladder actually permitted (skip=False) -- a day whose only proposal was a ladder-conflict skip counts as NO entry, honestly, since the live engine would never have placed that order either. A day in the DATA_MISSING sub-list had a real trigger fire but the resulting trade was excluded for a missing OPRA contract or SPY bars, NEVER silently dropped or modelled -- that day's zero is a DATA gap, not a GATES finding, and must not be conflated with the gates-only zeros.

## Frame fix (data provenance)

3/24 frozen days had a naive-label winter shift in the SPY wide file, corrected via `et_frame.parse_timestamp_et(frame='et-v2')`. See `automation/overnight/queue.md` item SPY-BAR-FILE-MIXES-TWO-TIME-FRAMES for the full defect analysis.

## Q1 -- mechanism mix (all stress days)

n=2, total P&L=$-75.7

Final exit stage mix: {'trail': 1, 'premium_stop': 1}

## Q2 -- side asymmetry

- Bull (calls): n=0 pnl=$None
- Bear (puts): n=2 pnl=$-75.7

## Q3 -- cap binding rate

Of 1 binding exits (structure-mode trades only), 1 were the -50% catastrophe cap and 0 were the chart/structure stop -- cap binding rate = 1.0.

Denominator is exits that were EITHER the -50% catastrophe cap OR the chart stop, restricted to structure-mode trades. tp1/runner/time-stop/profit-lock exits are excluded from this rate by construction -- they are not the invalidation-hierarchy question Q3 asks.

## Q4 -- ladder sizing

- n_trades_placed_under_ladder: 2
- n_capped_by_dollars_(max_position_dollars_binds): 0
- n_capped_by_contracts_only_(max_contracts_per_entry_binds): 0
- n_capped_by_both_simultaneously: 0
- n_uncapped_(min_contracts_never_touched_either_cap): 2
- n_ladder_conflict_skips_(no_legal_qty_>=_min_contracts): 0

A trade is counted 'capped_by_dollars' whenever the flat $1,000 cap reduced qty below what max_contracts_per_entry alone would have allowed -- this is the direct answer to whether the dollar cap binds before the contract-count cap on elevated stress-day premiums.

## Q5 -- worst case

Worst single trade P&L: $-390.0
- Gamma-Safe: worst day $-390.0 = -7.41% of $5,266.38 (kill switch at -30.0%) -> tripped=False
- Gamma-Bold: worst day $-390.0 = -7.73% of $5,048.40 (kill switch at -50.0%) -> tripped=False

## Stratification

**CAVEAT (UNVERIFIED):** this module's recomputed drop-day/range-day split does not reproduce the prereg's own subset counts (recomputed 13 cc<=-2% vs prereg-stated 16; recomputed 6 range>=3% vs prereg-stated 15). 5 frozen days satisfy neither recomputed threshold and are excluded from both strata below: 2026-02-05, 2026-03-23, 2026-03-31, 2026-04-14, 2026-04-24. See `_stratification_caveat` in the runner for the full disclosure.

- Excluding April 2025 block: n=2 pnl=$-75.7
- April 2025 block only: n=0 pnl=$None
- Drop-days (cc<=-2%): n=0 pnl=$None
- Range-days (range>=3%, cc>-2%): n=1 pnl=$-390.0

## Exclusions (counted, never dropped)

- n_no_opra_contract: 15
- n_no_spy_day: 0
- n_data_missing_on_stress_days: 2
- n_ladder_conflict_skips_all_window: 1
- n_ladder_conflict_skips_on_stress_days: 0

## Disclosures

- CONCENTRATION, and it is severe: NINE of the 24 days (37.5%) fall inside a single three-week stretch, 2025-04-03..2025-04-21 -- the April 2025 tariff sequence. This is one macro event, not nine independent observations. Every aggregate MUST be reported both with and without that block, and no headline may be quoted from the pooled number alone. This is C4 (disclose concentration) and it is pre-registered rather than discovered because the day list was enumerated before any P&L existed.
- n=24 IS SMALL and the effective n is smaller still once the April block is treated as one event -- roughly 16 independent episodes. No significance claim survives that; this study is DESCRIPTIVE. It answers 'what does the machinery do' and cannot answer 'is the edge positive in stress'.
- SIM-ONLY, as the work order requires. Entries and exits are simulated against real OPRA bars where the contract is cached; any entry whose contract CSV is absent is EXCLUDED and COUNTED (n_no_opra reported), never silently dropped and never filled at a modelled price. Cache coverage is 2024-01-18..2026-08-28, so it spans the window, but per-day coverage must be reported per day.
- NO SLIPPAGE MODEL beyond the OPRA bar. Real stress-day spreads are wider than the calm-regime record; a bar-derived fill is therefore OPTIMISTIC in exactly the population being studied. The direction of that bias must be stated beside every P&L number in the output.
- THE ENGINE IS FROZEN and this study cannot change it. Config freeze runs to 2026-10-30; nothing here proposes a shape change, and any change this motivates is a 10-30 menu item requiring its own prereg.
- PAST REGIMES ARE NOT THE NEXT ONE. Two of the three largest episodes here (Aug 2024 yen-carry, Apr 2025 tariffs) were single-cause macro shocks. A result that the engine survives these is not a result that it survives an unlike shock.

Elapsed: 111.3s. Full row-level data: `REGIME-STRESS-2026-09-02.json` in this directory.
