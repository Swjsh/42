# Day inventory — edge matrix 2026-07-23

- **Days covered (SPY 5m RTH ≥30 bars):** 386  (2025-01-02 → 2026-07-22); fragments excluded: 1; partial (<70 bars): 3
- **OPRA real-fill days:** 381 (2025-01-02 → 2026-07-17); 8797 option CSVs; dates with OPRA but no SPY bars: 1
- **Held-out (last 25% of OPRA days BY DATE, ceil):** 96 days — 2026-02-25 → 2026-07-17. Frozen; never read during tuning.
- **Day types (all covered):** trend 97 / range 148 / chop 136 / unclassified 5
- **Day types (OPRA days only):** trend 96 / range 147 / chop 133 / unclassified 5
- **VIX bands:** low 26 / mid 258 / elevated 67 / high 35 / none 0
- **|gap| at open:** median 0.30%, max 3.47%
- **Rules (frozen):** day_type = trend iff range/ATR20 ≥ 1.0 AND |close−open|/range ≥ 0.5; chop iff range/ATR20 < 0.75; else range. ATR20 = prior ≤20 covered days' RTH ranges (min 5).
- **VIX band rule:** day mean RTH close — low <15, mid 15–20, elevated 20–25, high ≥25.
- **Timestamps:** every row parsed with its own UTC offset → true ET (caches use a fixed −04:00 frame year-round; C6/DST-artifact safe).
- **Dedupe:** overlapping spy_5m caches resolved per-day to the single file with max RTH bars; no cross-file row mixing.
- **Gate math population:** OPRA days only; BS-synthetic days are disclosed, never gated.
- **Source:** `analysis/edge-matrix/day-inventory-2026-07-23.json` (per-day gap/type/vix/provenance; excluded fragments listed).

## Amendment 2026-07-22 — OPRA recent-gap backfill

OPRA backfill mission (target: extend cache backward to 2026-01-02) found the backward
extension **already complete** — 381/386 days had real fills spanning 2025-01-02 → 2026-07-17,
verified against live Alpaca (3 spot-checks, identical bars). The only real gap was the 5 most
recent trading days (2026-07-15, 07-16, 07-20, 07-21, 07-22), fetched this session via
`backtest/tools/_backfill_opra_recent_gap.py` (136 contracts, 0 errors). **OPRA real-fill days:
381 → 386 (100% of SPY-covered days).** `day_type`/`gap_pct`/`vix_band` for these 5 rows were
NOT recomputed (needs the original builder's ATR20/VIX pipeline) and `heldout_days` was left
untouched (frozen boundary). Full detail: `analysis/edge-matrix/OPRA-BACKFILL-REPORT.md`.
See `day-inventory-2026-07-23.json#manual_amendments` for the machine-readable diff.
