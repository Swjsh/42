# PREREG — SPY SWING LANE BY EVIDENCE (frozen 2026-09-16, before the walk runs)

> **Status: FROZEN.** Written 2026-09-16 (Wednesday, market closed) by `Gamma_Conductor`
> (AFTERHOURS), before `multiday_walk.walk()` + `weekly_exit_gate` + the random-entry null have
> been run against ANY SPY data. Nothing below may be edited after the walk runs — corrections
> go in a dated addendum below the signature line, never as an in-place rewrite (OP-33: a
> prereg that can be silently reworded after seeing the result is not a prereg).
>
> **This file arms nothing.** Read-only research against the production scorer. A `swing/` fork
> with its own registry is created ONLY IF the null passes (goal item (14) DONE-WHEN, verbatim).
> Live money is never in scope for this item.

---

## 0. Provenance

Parent goal: `automation/state/goals/GOAL-GAMMA-STATION-2026-09-13.md` item (14) — "SPY swing
lane by evidence... Order fixed: data → prereg → null → shadow fork; never live." This file is
step 2 of that fixed order. Step 1 (DATA) landed this same fire — see §1. Steps 3 (NULL) and 4
(FORK) are explicitly **NOT YET RUN** — that is the honest state as of this freeze, not an
oversight.

## 1. THE DATA (step 1, done this fire — 2026-09-16)

`backtest/tools/derive_spy_swing_sessionbars.py` derives **daily SessionBar files** (the schema
`backtest/lib/multiday_walk.load_contract_bars` reads) from the ALREADY-FETCHED real 3DTE/4DTE
intraday OPRA cache (`backtest/data/options_3dte/`, `options_4dte/` — 2,961 contracts, chef
2026-07-07 offline backfill, `vwap_continuation` family, ±4 strikes). **$0, no new network
calls.** Verified this fire:

- `derive_spy_swing_sessionbars.py` run: `ok=2961 fail=0 total_session_rows=13342
  avg_sessions/contract=4.51`.
- Output: `backtest/data/weekly-options/SPY/*.csv` (2,790 unique contract files — 171 filenames
  are shared between the 3DTE and 4DTE source population because the SAME expiry/strike/side
  contract can be a 3DTE target from one entry day and a 4DTE target from an earlier one; the
  later-processed 4DTE version wins and is a strict superset of sessions, so no path data is
  lost).
- Round-trip verified: `multiday_walk.load_contract_bars("SPY250107P00584000", "SPY")` returns
  4 `SessionBar` rows (2025-01-02/03/06/07), `is_expiry_day=True` on exactly the last one.
- Guard: `backtest/tests/test_derive_spy_swing_sessionbars_2026_09_16.py` (5 tests: OCC parsing,
  OHLCV aggregation correctness, expiry-flag correctness, loud failure on a zero-row source,
  full round-trip through the real consumer) — 5/5 passed.

**HONEST COVERAGE GAP — this is 3-4 DTE only, not the full 1-10 DTE the goal item names.**
`options_1dte`/`options_2dte` store ENTRY-DAY-ONLY bars (no true multi-day path exists in that
cache — see `_dte34_multiday_backfill.py`'s own docstring); DTE 5-10 have never been fetched at
all. Extending coverage is a fresh fetch shaped like `_dte34_multiday_backfill.py` (signal days
× strike band × DTE), not a derivation of data already on disk — that is next-fire work, in
order, before any walk that needs those DTEs. **This walk (§3) is scoped to 3-4 DTE only**,
matching what real data actually supports today; it does not claim 1-2 or 5-10 DTE evidence.

## 2. THE PRIOR TO BEAT — G6 weekly-hold KILL (`markdown/audits/G6-WEEKLY-HOLD-2026-07-08.md`)

G6 ran the SAME `vwap_continuation` signal, the SAME 3DTE/4DTE real cache, through
`multiday_walk` + `weekly_exit_gate` already, and it was **KILLED**:

| DTE | held_overnight% | OOS_exp | p_null (random-entry) | gap_loss$ |
|---|---:|---:|---:|---:|
| 3 | **17.6%** | $53.21 | 0.075 (fails, >0.05) | **−$4,050** |
| 4 | **26.4%** | $44.65 | 0.105 (fails, >0.05) | **−$6,413** |

Three independent reasons it was killed: (a) **null-failed** — indistinguishable from
random entry at 3-4 DTE; (b) **gap-exposed** — the overnight tail alone cost more than the
edge produced; (c) **doesn't even hold** — held-overnight was only 17.6%/26.4%, so the
"ride the move across days" thesis the hold was built to test never actually happened for
most positions.

**This is the prior this item must beat, named explicitly per the goal's own DONE-WHEN.**
Re-running the identical signal/data/exit-shape combination G6 already ran would not be new
evidence — it would reproduce a kill already on record. So:

## 3. WHAT THIS WALK ACTUALLY TESTS (the falsifiable difference from G6)

G6's exit shape was the WEEKLY-lane default (`weekly_exit_gate` defaults tuned for the
30-45-day weekly-options basket, never re-fit for a short-DTE SPY population). This walk holds
the signal and data fixed (same 3-4DTE population, same `vwap_continuation` entries — the only
real data this box has) and asks a narrower, still-falsifiable question:

> **H1 — a stop/target shape RE-FIT to the 3-4DTE SPY population (not inherited from the
> 30-45-day weekly basket) survives the random-entry null AND holds a materially larger
> share of positions overnight than G6's 17.6%/26.4%, without re-opening the gap-loss tail
> at a comparable magnitude.**

This is a real chance to fail: if the re-fit shape still fails the null, or still gaps for a
comparable dollar loss, or still resolves >80% of positions intraday, H1 is refuted and the
correct verdict is a SECOND kill entry (a null result IS a valid terminal state per this
goal's own DONE-WHEN clause) — not a re-framing to keep looking for a pass.

## 4. NULL HYPOTHESIS + PASS BAR (must ALL hold to proceed to step 4, the shadow fork)

1. **Beats random-entry null:** bootstrap p < 0.05 on OOS expectancy vs. random-entry-date
   baseline on the SAME contract population (methodology identical to G6's own null test —
   comparability is the point).
2. **Actually holds overnight:** held_overnight% materially exceeds G6's 26.4% ceiling (bar:
   ≥ 40%, i.e. the position genuinely spans a session more often than not-quite-a-third of the
   time) — otherwise "multi-day" is nominal, not real.
3. **Gap tail does not re-open at comparable cost:** total gap_loss$ across the walked
   population must not exceed G6's per-position gap-loss rate (−$4,050 / 165 positions ≈ −$24.5
   avg at 3DTE; −$6,413 / 163 ≈ −$39.3 avg at 4DTE) — a re-fit shape that merely trades a wider
   stop for a bigger gap tail has not solved anything.
4. **anchor_no_regression:** the existing G6 kill result itself must remain reproducible
   byte-for-byte on the unchanged exit shape (i.e. this walk adds a NEW shape variant, it does
   not silently mutate the shared `weekly_exit_gate` defaults G6 measured against).

All four fail → **KILL, log the null, stop** (do not build the `swing/` fork). Any one holds
provisionally but not all four → **hold at YELLOW, report the partial, do not fork.** All four
hold → proceed to step 4 exactly as specified: "a `swing/` fork with its own registry exists
ONLY if the null passes."

## 5. WHAT THIS FIRE DOES **NOT** DO (explicitly, so the next fire does not re-derive it)

- Does **not** run the walk yet. Steps 3 (NULL) and 4 (FORK) are next-fire work, in the fixed
  order the goal specifies — this file exists so that work runs against a FROZEN measurement,
  not one written after peeking at a result.
- Does **not** extend data past 3-4 DTE. That is a separate, larger fetch task (§1) queued
  behind this one, not silently folded in.
- Does **not** touch `heartbeat_core.py`, any `params*.json`, `filters.py`, `risk_gate.py`,
  `exit_manager.py`, or any other file on `FROZEN_TRADING_PATH` — this is pure research
  (2 new files: the derivation tool + its guard test), reversible via `git revert`.

---

**Signature line — frozen 2026-09-16, `Gamma_Conductor` (AFTERHOURS), Sonnet.**

## Addenda (post-freeze corrections only, never in-place edits above this line)

_(none yet)_
