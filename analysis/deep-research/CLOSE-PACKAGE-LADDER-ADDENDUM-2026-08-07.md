# CLOSE-PACKAGE ADDENDUM — 2026-08-07 (orchestrator merges at 15:55)

> Lanes append sections below. Do NOT overwrite another lane's section.

## LANE 4 — SIZE ANATOMY (staged for close)

Full artifact: `analysis/deep-research/SIZE-ANATOMY-2026-08-07.md` + `.json`.
Runner: `backtest/tools/size_anatomy_2026_08_07.py` (day totals assertion-reconciled).

**For J's close brief (4 lines):**

- **−$629 was not oversize.** 6.8% of combined Rule-5 kill budgets (no arm above 10.1% of its
  own); ~$22.50/contract; every arm sized exactly per the frozen 2×3 grid — 28 contracts =
  3 (core min) + 8 (safe ELITE tier) + 5 (full-send clamp) + 12 (bold ELITE tier), first
  session the design fully expressed (ELITE + recency GREEN + 4 arms on one shared signal).
  Worst per-contract loss was the SMALLEST position (safe-2, −$51/ct — 64s-earlier 1.67 entry):
  entry timing, not size.
- **Dollar-risk normalization {1.5/2/3}% — REFUTED, no prereg staged.** At $5–6K equities the
  min-contract floors bind 44–50 of 51 week positions → the three cells are the SAME policy
  (shrink variant byte-identical at all f). Best shippable cell: week +$406 but G4 runner −$423,
  sub-window sign-flip, and LEVER-SIZING-2026-08-06 cell (e) already refuted the family on the
  26-day book. Wednesday still −$1,388 in every legal cell — sizing cannot cap a Wednesday.
- **Open finding (no proposal tonight): book-level correlation is unbudgeted.** Per-arm caps are
  all honest; there is no cross-arm budget when 4 arms take one signal. That is the real "$629"
  mechanism.
- **risky-3 OTM-2 revert n=1 forward datapoint:** 12 × $0.62 = $744 notional (13.9% eq), −$204 —
  smaller dollar exposure than ATM-at-12 would have carried into the same stop. Logged, no
  conclusion.

**Cross-lane pointer for the LADDER lane:** `backtest/tools/arm_score_ladder_replay.py` EXISTS
(siblings `ladder_fullhist_replay.py`, `ladder_subset_prereg.py`; evidence in
`analysis/arm-ladder/` — ARM-LADDER-V1-2026-07-27, LADDER-FULLHIST-2026-07-27,
LADDER-SUBSET-VERDICT-2026-07-28). `accounts.json` holds DISARMED score_ladder_doc state on
safe-3 (floor=9: −$10,903/332tr vs +$5,307 baseline) and risky-1 (floor=8: −$16,642/725tr), and
risky-3's armed bear-only ladder. The 07-27 replay tested a FLOOR (score>=N admits), NOT tonight's
demote-not-veto semantics (demotable blockers subtract demerits; non-demotable stay absolute) —
the prereg must state that distinction or the old NULL will be miscounted as evidence against the
new mechanism. Sizing note for the ladder prereg: ladder entries on risky arms will size at bold
tier qty (12 at ELITE, not min) unless the prereg pins qty — the 07-27 armed ladder deliberately
used min_contracts; tonight's should state its sizing explicitly.
