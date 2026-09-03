# PREREG-WHOLE-ENGINE-NULL-V2-STOP-MODE-FAITHFUL-2026-09-03

**Status:** FROZEN — NOT RUN. Design committed before any outcome was computed. Supersedes
`prereg-whole-engine-null-2026-09-01.json` at the effective date below; v1 stays live and
published until then (two-Friday overlap, see Effective date).

**Filed by:** Sonnet worker session, queue item `NULL-LEGS-WALK-STRUCTURE-ONLY` (MEDIUM,
filed 2026-09-01 Opus, `automation/overnight/queue.md` line 105).

**Filed at ET:** 2026-09-03T04:23 (`python setup/scripts/et_clock.py` → `2026-09-03 04:23:56
Thursday EDT`).

**Supersedes:** `analysis/recommendations/prereg-whole-engine-null-2026-09-01.json`
(`PREREG-WHOLE-ENGINE-NULL-2026-09-01`). That prereg is FROZEN and cannot be edited
in-window — editing a null leg's design after seeing the study's results is the exact
post-hoc pattern the 2026-09-01 `addendum_2026_09_01_validator_fidelity` incident already
had to reverse (see that file). This v2 document is the correction path: a new prereg that
takes effect at a stated future cadence boundary, not a silent patch to the frozen one.

---

## Purpose

`setup/scripts/whole_engine_null.py#walk_one` accepts a `stop_mode` kwarg (added in the V9
INPUT-FIDELITY FIX, 2026-09-01) that threads a trade's REAL live-resolved stop mode
(`"structure"` / `"premium"` / `None`) into `structure_stop_enabled`. V9 (the
validate-the-validator replay) uses it. **Neither null leg does.** `run_null_a` (~line 756)
and `run_null_c` (~line 884) both call `walk_one` without `stop_mode`, so `walk_one`'s
default (`stop_mode=None` → `structure_stop_enabled=True`) fires for every walk in both
legs — a structure-only variant of an engine whose real P1 population resolved
**structure 107/156 = 68.6% / premium 42/156 = 26.9% / none 7/156 = 4.5%** (verified:
`grep -n "structure_stop_enabled = True if stop_mode is None"
setup/scripts/whole_engine_null.py` line 495; population counts from the queue item, not
independently recomputed by this document).

N_c is the sharper case: it replays the engine's OWN P1 entries
(`run_null_c(p1_rows, ...)`, line 884), each of which already carries a recorded
`stop_mode` on the row (`row.get("stop_mode")`, used elsewhere in the same file at line
591 for V9) — and ignores it. N_a has no per-draw real stop_mode to thread (its entries are
resampled, not the engine's own rows), so its fix is different in kind: draw stop_mode from
the empirical population mix rather than read it off a row.

This document specifies the null-leg fix as a new, dated prereg so the correction ships
without touching the frozen v1 design in-window.

---

## Frozen date

2026-09-03 (this document). Not run before this date; no outcome has been computed under
this design.

---

## Populations

Unchanged from v1, verbatim:

- **P1_post_ladder** — engine-attributed trading days ≥ 2026-08-11, 4 active arms, from
  `analysis/trades-enriched.jsonl` / fills-ledger FIFO.
- **P2_frozen_window** — trading days ≥ 2026-09-01 (the config under the September freeze);
  scored as days accrue, adjudicated at ≥ 20 days and again at the 2026-10-30 TIGHT-LADDER
  close.
- **P3_spy_down_days** — subset of P1 with SPY RTH open→close return < 0.

---

## Legs (nulls) — what changes and what does not

**Changes (stop-mode fidelity only):**

1. **N_c (`run_null_c`)** — each replayed entry threads its OWN recorded `stop_mode`
   (`"structure"` / `"premium"` / `None`) into `walk_one`, verbatim, exactly as V9 already
   does for the same rows. No resampling, no synthetic assignment — the field already
   exists on every P1 row.
2. **N_a (`run_null_a`) and N_b (buy-and-hold)** — N_a's entries are resampled draws with no
   per-draw real stop_mode to read, so each draw's `stop_mode` is instead drawn by
   **stratified sampling from the engine population's empirical mix**
   (structure 0.686 / premium 0.269 / none 0.045, from the same P1 population N_a is
   compared against), using a **fixed seed** so the draw is reproducible run-to-run. N_b is
   buy-and-hold with no exit machinery (`walk_exit_manager`/`walk_one` is not in its path at
   all — see `run_null_b`, ~line 830) so `stop_mode` fidelity does not apply to it; N_b is
   listed here only to record that it is explicitly unaffected, not silently forgotten.

**Not changed:**

1. **Entry populations** — P1/P2/P3 definitions, arm set (`ACTIVE_ARMS`), and windows are
   unchanged verbatim (see Populations above).
2. **Bootstrap / resampling mechanics** — `resamples` count, `entry_grid` (09:35–15:00 RTH
   uniform draw), strike-selection rule (ATM), and the walker call path
   (`backtest/lib/exit_manager_walk.walk_exit_manager` via `walk_one`) are unchanged.
3. **Thresholds** — `pass_criterion_frozen`'s four checks (engine > N_a p95; engine >
   N_b_call + N_a IQR; engine on P3 ≥ 0 or > N_a p75 on P3; N_c ≤ 0) and the `kill_nails`
   definitions (`BETA`, `NULL_DOMINATED`, `REGIME_BOUND`, `DOWN_DAY_BLIND`, `UNPOWERED`) are
   copied byte-identical from v1's `pass_criterion_frozen` / `kill_nails`.
4. **Verdict vocabulary** — PASS / FAIL / WITHHELD (`HARNESS_UNRELIABLE`) is unchanged; see
   Verdict vocabulary below.

---

## Walker + fidelity criterion

Walker is unchanged: `backtest/lib/exit_manager_walk.walk_exit_manager`, invoked through
`whole_engine_null.py#walk_one` (verified present: `grep -n "def walk_one"
setup/scripts/whole_engine_null.py` → line 448; `grep -rn "def walk_exit_manager"
backtest/lib/exit_manager_walk.py` confirms the target module exists and is imported by
`whole_engine_null.py`).

The magnitude criterion — v1's `pass_criterion_frozen` four checks — stays as published,
copied verbatim (see Legs, "Not changed," item 3).

**Fidelity precondition (V9, carried forward unchanged):** before any null verdict is
reported, the walker must reproduce the engine's own real P1 entries with sign agreement
≥ 0.85 (`addendum_2026_09_01_validator_fidelity`). Below that bar the study reports every
mechanical sub-check but the overall verdict is WITHHELD (`HARNESS_UNRELIABLE`). This v2
prereg does not relax or restate that bar — it is inherited from v1 as-is. The first V9
reading (2026-09-01) measured 0.793 (n=121), below bar; this v2 does not assume that number
has moved. **The current SIGN-ONLY disclosure is carried forward until both anchors clear**
— i.e. until V9 sign agreement clears ≥ 0.85 AND the stop-mode-faithful null legs specified
here have a real reading, magnitude comparisons (the four `pass_criterion_frozen` checks)
stay disclosed as sign-only, matching v1's existing WITHHELD convention.

---

## Verdict vocabulary

Unchanged from v1: `PASS` / `FAIL` (with the failing check's `kill_nails` name attached) /
`WITHHELD` (`HARNESS_UNRELIABLE`, when the V9 fidelity precondition is not met) /
`UNPOWERED` (P2 < 20 days at adjudication — park, do not conclude).

---

## Pre-committed prediction

If structure-only replay was biasing N_c toward looking too favorable to the engine (by
forcing every flipped-side entry through the tighter, faster structure stop instead of the
wider premium/no-stop modes the real population actually used 31.4% of the time), then
**stop-mode-faithful N_c should move AWAY from ≤ 0 (toward less negative / more positive)
relative to the v1 structure-only reading** — i.e. the opposite-direction null should look
LESS clearly dominated once it is allowed to run the same stop-mode mix the engine itself
ran. **This would be REFUTED by N_c staying ≤ 0 (or moving further negative) under the
stop-mode-faithful walk** — that result would show the structure-only bias was not
material to N_c's sign, and the `REGIME_BOUND` kill_nail's standing verdict would be
unaffected by this fix.

---

## Build step (structured, per `PREREG-BUILD-CLAIMS-ARE-UNFALSIFIABLE-AS-WRITTEN`,
`automation/overnight/queue.md` line 2538 / `automation/overnight/STATUS.md` line 280)

```
build_step:
  file: setup/scripts/whole_engine_null.py
  symbol: run_null_c
  must_contain: 'stop_mode=row.get("stop_mode")'
```

This is the minimum verifiable change: `run_null_c`'s call to `walk_one` (currently, line
~906: `walked = walk_one(symbol=symbol, side=flip_side, date=row["date"],
entry_time_et=entry_time, entry_premium=entry_px, qty=int(row["qty"]),
trigger_level=trig, spy5=spy5, budget=budget)` — no `stop_mode` kwarg) must add
`stop_mode=row.get("stop_mode")` to that call, matching the existing pattern at line 591
(`real_stop_mode = row.get("stop_mode")` / `walk_one(..., stop_mode=real_stop_mode, ...)`
inside `run_v9`). N_a's stratified-sampling change (a second, larger addition — a seeded
draw from the 0.686/0.269/0.045 mix per entry, threaded the same way) is a separate,
larger diff not captured by this single-symbol `must_contain` check; it is specified in
"Legs" above and should get its own `build_step` entry when someone builds it, per the
standing rule's own "one field per prereg build claim" shape.

---

## Effective date

**2026-10-02** — the first Friday reading after the 2026-09-29 checkpoint. Chosen per the
CLAUDE.md OP-9 cadence convention (rule/design changes land on a stated boundary, not
mid-window) and the study's own existing "Friday gate cadence" (`prereg-whole-engine-null-
2026-09-01.json#status`). For **two Fridays** starting 2026-10-02, the v1 (structure-only)
reading is published BESIDE the v2 (stop-mode-faithful) reading in the same output — so the
size and direction of the correction is visible before v1 is retired from the published
surface. v1 is not deleted or edited at any point; it stays the historical record.

---

## No-ship clause

Unchanged in spirit from v1's `does_this_ship_anything`: **No. Measurement only.** A FAIL
(or a stop-mode-faithful reading that flips a currently-passing check) freezes any
live-arming discussion regardless of gate colour; a PASS remains a necessary, not
sufficient, condition for the 2026-10-30 arming question. This v2 does not change the
`pass_criterion_frozen` thresholds — only the fidelity of what is fed into them for N_a and
N_c.

---

## Revert

Delete this file. Until the effective date (2026-10-02), it has no runtime effect — no code
under `setup/scripts/` or `backtest/` reads it, and `whole_engine_null.py`'s null legs
continue running exactly as v1 specifies until the `build_step` above is implemented and
wired at the effective date.

---

## Verification log (this document)

- `grep -n "run_null_a\|run_null_c\|def walk_one\|structure_stop_enabled\|stop_mode"
  setup/scripts/whole_engine_null.py` — confirmed `walk_one` (line 448), `stop_mode` kwarg
  (line 451), `structure_stop_enabled = True if stop_mode is None else ...` (line 495),
  `run_null_a` def (line 756), `run_null_c` def (line 884), and that `run_v9`'s call site
  (line ~591-607) is the only one passing `stop_mode=real_stop_mode` today.
- Read `run_null_a` (lines 756-806) and `run_null_c` (lines 884-909) in full — neither
  passes `stop_mode` to `walk_one`.
- `analysis/recommendations/prereg-whole-engine-null-2026-09-01.json` read in full (43
  lines) — section structure and exact frozen text (`pass_criterion_frozen`, `kill_nails`,
  `nulls`, `populations`, `does_this_ship_anything`, `revoke`) copied/paraphrased above from
  the real file, not from memory.
- `automation/overnight/queue.md` line 105 (`NULL-LEGS-WALK-STRUCTURE-ONLY`) and line 2538
  (`PREREG-BUILD-CLAIMS-ARE-UNFALSIFIABLE-AS-WRITTEN`) both grepped and read in full;
  `automation/overnight/STATUS.md` line 280 read for the standing-rule wording
  (`build_step: {file, symbol, must_contain}`).
- Population percentages (structure 68.6% / premium 26.9% / none 4.5%, n=156) are taken
  verbatim from the queue item text — NOT independently recomputed against
  `trades-enriched.jsonl` in this session (no replay was run, per this task's constraints).
  Flagged here as UNVERIFIED-BY-THIS-SESSION, sourced-from-queue-item.
- ET timestamp read fresh via `python setup/scripts/et_clock.py` this session (not
  inferred): `2026-09-03 04:23:56 Thursday EDT`.
- 2026-10-02 confirmed Friday via `python -c "import datetime;
  print(datetime.date(2026,10,2).strftime('%A'))"` → `Friday`.
