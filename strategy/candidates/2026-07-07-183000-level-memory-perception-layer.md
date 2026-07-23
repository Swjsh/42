# Strategy candidate: LEVEL_MEMORY perception layer

> DRAFT — Chef proposal 2026-07-07 18:30 ET. J ratifies.

## Hypothesis
J's real edge is **multi-day horizontal level memory + role-flips**, not a candle
pattern (the mislabeled "ribbon rejection" family was killed 5 ways). Worked example
verified on the tape: the **750.90** level flip-flopped support<->resistance across
2026-07-06/07-07 and the 07-07 open rejected off it -> the dump. The live engine has
no memory-weighted multi-day levels and deliberately suppresses role-flips.

Two claims tested:
- **H1:** a fresh REJECTION at a high-memory level predicts a next-K-bar directional
  SPY move better than (A) a rejection at a random horizontal price and (B) random entry.
- **H2:** more memory (higher memory_score) predicts a bigger/more reliable reaction.

## Backtest evidence
- **Perception (built + guarded):** `LevelMemory(df).snapshot(i)` — stateless,
  look-ahead-safe. Clusters swing pivots into levels; role flips only on a decisive
  CLOSE through; memory_score = touches + wicks + consolidation + 2·role_flips.
- **ANCHOR HIT:** over 07-06/07-07, surfaces a level at **750.92** (J's 750.90 +2c),
  role=resistance, role_flips=4, and flags the 07-07 09:30 bar as a **REJECT** of a
  role-flipped resistance shelf. Also surfaces the shelf centroid 750.4–750.7.
- **Look-ahead guard:** planted-future-level correctly INVISIBLE at an earlier bar;
  truncating the frame after bar i yields the identical snapshot. 5/5 guards PASS.
- **NULL TEST** (smoke 2026-05-19..07-01, OOS vs the anchor; K=6 bars=30min):
  - Naive "reject at high-memory level" fires ~41/day (C27 noise floor).
  - Favorable-excursion lift vs **random-LEVEL: +0.048pt, p=0.17 (FAILS)**;
    vs random-entry: +0.056pt, p=0.089.
  - **Beats random-ENTRY but NOT random-LEVEL** → the (weak) edge is "a horizontal
    rejection generically", not memory specifically.
  - Selective variant (role_flips≥2 + top-3 memory + wick≥15c + close-back≥15c;
    3.2/day, N=97/16d) ENDPOINT lift by horizon: K3 +0.008, K6 −0.093, K12 +0.036,
    K24 +0.262 (2h trend drift, hit ~52% = coin flip). No horizon-robust edge.
  - **H2:** corr(memory_score, excursion) = **−0.006**; terciles non-monotone.
    More memory does NOT predict a bigger reaction (C25/C27 confirmed).
- edge_capture: **N/A** — this establishes PRICE-STRUCTURE signal presence first
  (per the build spec: options P&L is a separate C3 question, only pursued if a
  price-structure edge exists). It does not, so no options test was run.
- real_fills_validated: N/A (no entry to validate — signal has no lift).

## Disclosures (per OP-20)
1. **Account-size assumption:** none — SPY-price-move metric only, no sizing.
2. **Sample-bias:** smoke window is 30 trading days (05-19..07-01); the anchor
   (07-06/07) is held OUT of the null test to avoid fitting to it.
3. **Out-of-sample:** the null test IS out-of-sample vs the anchor. Result: no lift.
4. **Real-fills check:** not run — gated behind a price-structure edge that was not found.
5. **Failure-mode enumeration:** (a) dense sub-level clustering fires "reject" on
   ~every bar (fixed the metric, not the density); (b) favorable-excursion metric
   captures generic 30-min volatility (~0.66pt on both nulls) — endpoint move is the
   honest directional metric; (c) centroid clustering can't replicate J's discretionary
   pick of WHICH shelf matters.
6. **Concentration:** N/A (no P&L series).

## Knob changes proposed
**NONE.** This is a REJECTED entry hypothesis. The perception layer itself is correct
and guarded and is retained as a potential engine INPUT/VETO (e.g. "don't enter long
into a role-flipped resistance"), NOT a standalone entry. No params.json change.

## Pre-merge gate
`python crypto/validators/runner.py` unaffected — all new files are offline R&D under
`backtest/`. Guard `backtest/tests/test_level_memory.py`: **5/5 PASS**. No live-engine,
params, or heartbeat files touched.

## My confidence (1-10) and why
**8/10 that the naive-rejection-entry has NO edge** (beats random entry but not a
random horizontal level; memory non-monotone; endpoint lift oscillates around zero).
The perception layer is verified-correct (anchor hit + look-ahead-safe) and worth
keeping as an input, but "buy the rejection at a memory level" is NOT a candidate.
Verdict: **NO-LIFT** for the entry; **YES** for perception-as-infrastructure.
