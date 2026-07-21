# Lesson candidate: never-average-down is a graduated-guard candidate — but the money is in the no-add + −50%-cap PACKAGE, not no-add alone

> Queued by Gamma (E5 evidence pack, analysis/j-webull/E5-rule4-evidence.md) 2026-07-01.
> lesson-author picks up at next wake fire. Numbers are pure arithmetic on J's REAL
> 2021-23 WeBull fills (567 closed family episodes, net −$12,885) — no simulation
> except the two figures marked BOUND.

## Symptom

J's scaled-in episodes (n=67) lost −$9,281 (−$138.5/trade vs −$7.2/trade single-fill),
and 94% of them (63/67, WR 31.7%) averaged DOWN — added at a lower premium than the
first fill. Separately, 130 of his 330 losers (39.4%) were held past −50% of premium
for −$30,381 gross. Doctrine (TRAITS-REPORT/C31 lineage) has been crediting Rule 4
with "addressing −$9,281 of the net loss."

## Root cause (the sharpened attribution)

The first-fill-only counterfactual (keep only the first buy lot, sell it FIFO at his
REAL sell prices) recovers just **+$794** of the −$9,281 — because averaging down
lowers cost basis, so the added contracts lose LESS per contract than the first fill
at the same exits. Scale-in is primarily a **marker** of trades J refused to cut
(their first fills alone run −$126.7/trade, ~19x the single-fill baseline), and the
add then multiplies exposure. The behaviors are coupled: **29 of the 67 scaled-in
episodes were also held past −50%, losing −$13,655 by themselves** (the other 38
scaled-in episodes net +$4,374) — the add manufactures the conviction to blow
through the stop. The recoverable money is the PACKAGE: no-adds + −50% catastrophe
cap = **+$3,428 BOUND on the scaled-in cohort**; capping all 130 past-−50% losers =
**+$6,176 BOUND book-wide** (cohorts overlap by those 29; don't sum). Fixed-exit
counterfactuals are LOWER bounds — a trader who cannot add has no story for holding.

## Fix (proposed — do not apply without lesson-author/A-B process)

1. **Graduated guard** (test_graduated_guards.py style): assert the engine can NEVER
   submit an order that increases an existing open position at a premium at-or-below
   the position's first-fill premium without an explicit new-trigger flag set by a
   named playbook setup (Rule 4 as a code assertion, not prose). Both accounts, both
   directions, fleet included.
2. **Companion assertion:** the −50% catastrophe cap must be present, armed, and
   REACHABLE in the exit path for every position (cf. the G14 ribbon-flip-back
   literal-mismatch scar — a dead exit knob is the same disease).
3. **Doctrine correction:** amend the C31/TRAITS framing from "Rule 4 alone addresses
   −$9,281" to "no-add alone recovers ~$794 at fixed exits; the no-add + −50%-cap
   package bounds +$3,428 on the scaled-in cohort and +$6,176 book-wide; scale-in is
   the highest-signal MARKER of a trade being managed by hope."

## Encoded in

`analysis/j-webull/E5-rule4-evidence.md` + `.json` (exact rows cited, e.g. worst
scaled-in: SPXW 220513 P3750 2022-05-12, max qty 6 from first fill 2, −$1,380).
Reproduce: `backtest\.venv\Scripts\python.exe analysis\j-webull\scripts\e2_e5_replay.py`.

## L## (optional)

Grep LESSONS-LEARNED.md for the current max (≥L192 as of 2026-06-28). Themes: C31
(sizing/adding kernel — this REVISES its attribution), C14 (dead knobs — guard the
cap's reachability), C7 (audit outputs — the counterfactual arithmetic, not the
category total, is the authority).
