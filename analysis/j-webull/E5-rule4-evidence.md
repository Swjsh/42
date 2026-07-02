# E5 — Never-average-down guard evidence pack (2026-07-01)

> $0, pure arithmetic on J's REAL WeBull fills (2021-06..2023-10, 567 closed
> SPX/SPY-family episodes, net −$12,885). No simulation anywhere in this file
> except where marked BOUND. Script: `analysis/j-webull/scripts/e2_e5_replay.py`
> (rebuild self-checked to the published parse: 567 episodes, −$12,885 exactly).
> Machine-readable: `E5-rule4-evidence.json`.
>
> Purpose: the standing empirical justification for `risk_gate`'s **no-add
> (Rule 4)** + **−50% catastrophe cap** settings, from J's own money.

## Headline numbers

### (1) Scaled-in episodes vs first-fill-size-only counterfactual

| | n | Total P&L | Exp/trade |
|---|---|---|---|
| Scaled-in episodes, actual | 67 | **−$9,281** | −$138.5 |
| Counterfactual: FIRST fill only, sold FIFO at his REAL sell prices | 67 | −$8,487 | −$126.7 |
| **Saved by no-adds alone (exits held fixed)** | | **+$794** | |
| Counterfactual: no-adds AND −50% cap on the first lot (BOUND) | 67 | −$5,853 | −$87.4 |
| **Saved by the no-add + cap PACKAGE** | | **+$3,428** | |

Single-fill episodes for contrast: n=500, **−$7.2/trade** — scaled-in episodes
are ~19× worse per trade even at first-fill size.

### (2) The averaged-DOWN subset (adds at a lower premium than the first fill)

| | value |
|---|---|
| n (of 67 scaled-in) | **63 (94.0%)** |
| WR | 31.7% |
| Actual total | **−$8,628** |
| First-fill-only counterfactual | −$8,107 |
| Saved by no-adds alone | +$521 |

### (3) Losers held past −50% of premium

| | value |
|---|---|
| Losers (all closed family) | 330 |
| Held past −50% | **130 (39.4% of losers)** |
| Gross loss of those 130 | **−$30,381** |
| Excess loss beyond a −50% cap (BOUND: assumes exit at exactly −50%; no option-path data, gap-through unknown) | **+$6,176 recoverable** |

### The coupling stat (why these are ONE guard, not two)

**29 of the 67 scaled-in episodes were ALSO held past −50% — those 29 alone
lost −$13,655**, more than the entire scaled-in category net (the other 38
scaled-in episodes net +$4,374). Averaging down and refusing the stop are the
same behavior observed at two checkpoints: the add manufactures the conviction
to blow through the stop.

Worst scaled-in rows (episode = flat→flat, real fills):

| Contract | Entry | Max qty | First fill | Actual P&L |
|---|---|---|---|---|
| SPXW 220513 P3750 | 2022-05-12 09:50 | 6 | 2 | −$1,380 |
| SPXW 220729 P4060 | 2022-07-29 11:12 | 6 | 4 | −$990 |
| SPXW 230616 C4460 | 2023-06-16 10:01 | 5 | 4 | −$860 |
| SPXW 230605 P4270 | 2023-06-05 10:15 | 3 | 2 | −$839 |
| SPXW 220608 P4090 | 2022-06-08 13:33 | 8 | 4 | −$820 |

## Honest re-framing vs the TRAITS-REPORT headline

TRAITS-REPORT.md says Rule 4 "alone addresses −$9,281 of the −$12,885 net
loss." **That attribution is too generous as stated.** The clean arithmetic:

1. Holding his real exits fixed, deleting the adds recovers only **$794** —
   because averaging down lowers cost basis, the added (cheaper) contracts lose
   less per contract than the first fill at the same exits.
2. The −$9,281 category loss is mostly a **marker effect**: scaled-in episodes
   were toxic trades J refused to cut (−$126.7/trade at first-fill size alone).
   The add doesn't create most of the loss; it FLAGS the psychological state
   that does — and then multiplies exposure to it.
3. The recoverable money lives in the **package**: no-add + −50% catastrophe
   cap = **$3,428 bound on the scaled-in cohort** plus **$6,176 bound
   book-wide** from capping the 130 past-−50% losers (cohorts overlap by the
   29 episodes above; do not sum the two figures).
4. The fixed-exit counterfactual is a **lower bound** on the guard's true
   value: a trader who cannot add has no averaging-down story to justify
   holding — the behavioral coupling means real savings likely sit between
   $794 and the package bound.

## Mapping to live settings (no changes proposed here)

- **Rule 4 / risk_gate no-add:** every add requires a NEW confirmed trigger;
  "it's cheaper now" is precisely the 94%-of-adds-at-lower-premium pattern.
- **−50% catastrophe cap both sides** (chart-stop-primary, 2026-06-18): J's
  own book shows 39.4% of losers blowing through that line for −$30,381 gross.
- Proposed graduated guard (filed to `strategy/candidates/_lesson-inbox/`):
  a code assertion that the engine can NEVER submit a buy that increases an
  existing position at a premium below its first fill — see
  `2026-07-01-never-average-down-graduated-guard.md`.
