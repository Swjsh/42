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

## LANE 3 — TV BAR REPLAY WALKTHROUGH (staged for close)

Full artifact (committed a6b17332): `analysis/deep-research/FRIDAY-TV-REPLAY-2026-08-07.md`
— 9 replay screenshots inline, phone-scrollable, binary-vs-ladder annotated at every decision
point on J's own chart (SPY 5m, TV MCP replay, produced intraday 12:07–12:30 ET, no
trading-path file touched, tv_health_check GREEN at exit).

**For J's close brief (3 lines):**

- **The tape shows exactly what J said, 4th ask:** 09:40 close over PDH 771.82 → 11/11 entry
  (both engines identical, −$629 book on the 09:55 dump, stops 10:01–10:02) → then 91 minutes
  (10:15–11:45) of ELITE-grade refusals while SPY ran 770.50 → 773.91 with no meaningful
  pullback — first refused tick 10:15:03 (score 10, sole blocker F10, level_reclaim+confluence
  @770.46, VIX 15.04).
- **Window census (182 HOLD ticks): 70 ladder-admissible** — cells (10,[10])×54, (10,[7])×10,
  (9,[7,10])×6 → BOTH risky rungs (8 and 7) enter at 10:15; the other 112 ticks carry F11
  (bare-confirmation, −$103/entry 0%-WR cohort) and stay refused on EVERY rung — the ladder
  ≠ filter deletion, demonstrated on today's own tape.
- **No oversell:** ladder buys the same 09:46 loss AND the 12:06 re-entry (score-11 cells);
  at ~12:25 the 12:06 position was underwater (spy 771.5 vs 773C @ ~1.10, EST). Narrative ≠
  net-positive proof — that stays on the LADDER lane's sequential walks + battery.

**Dojo/tooling scars for the replay harness (fold into `dojo_session.py`):** (1) a leftover
"Continue your last replay?" modal silently blocks VISUAL replay while the API keeps stepping —
dismiss `[data-name="warning-dialog"]` before `replay_start`; (2) `replay_autoplay` speed is not
honored (~3 bars/s at "1000ms"; "143ms" ran ~98 bars in <6.5s and auto-exited at the live edge) —
fine control is `replay_step` only; (3) API-driven replay keeps painting live bars right of the
yellow cursor — the cursor line + OHLC readout are the frame's authority.
