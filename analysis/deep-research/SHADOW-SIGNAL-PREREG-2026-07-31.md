# PRE-REGISTRATION — Shadow-Signal Inventory + Promotion
Pre-registered: 2026-07-31 17:29:26 ET Friday EDT (et_clock.py, market_hours=False)
Lane: shadow-signal inventory / wiring architecture
Agent: distinct lane (NOT block_elite_bull, NOT premium floor, NOT level-persistence, NOT OPRA backfill)

## HYPOTHESIS
H1: A material fraction of this engine's detectors produce output that NO decision path consumes
    (ORPHANED / SHADOW). The 10:15 wick_reclaim case is not an isolated bug, it is a class.
H2 (testable): At least one shadow/orphaned signal, joined to forward real-OPRA outcomes at
    entry+1 with real exit walk, carries positive per-trade expectancy that survives BH-FDR
    across the full set of signals tested.

## GATES (declared BEFORE any run)
Promotion of the TOP candidate requires ALL of:
  G1. n >= 20 firings with resolvable forward outcomes (real OPRA only; synthetic excluded)
  G2. total P&L > 0 AND per-trade > 0
  G3. drop-best-single-trade still >= 0 total (no single-trade dependence)
  G4. BH-FDR q<=0.10 significant across the WHOLE set of signals measured (multiplicity honest)
  G5. does NOT degrade the RUNNER_TRAIL cohort (35 winners / +$15,774) -- entry-side only changes
      are exempt-by-construction but must be argued
If NOTHING clears: ship the inventory + checker, arm nothing, report NULL. A clean null is a result.

## MEASUREMENT CONVENTIONS (locked now)
- entry+1 bar convention (markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md)
- real OPRA P&L only; any synthetic-priced cell is DISCLOSED and EXCLUDED from verdicts
- min size (1 contract) for per-signal attribution
- report ALL cells, no cherry-picking; UNDERPOWERED signals report n and get NO verdict

## DELIVERABLES (committed regardless of outcome)
D1. analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md (standing inventory)
D2. a checker script that regenerates it + flags NEW orphans
D3. nightly scheduled task, DailyTrigger, registered AND verified Ready (not just documented)
D4. ranked promotion queue; at most ONE armed change with guard + RED-proof + A/B scorecard
