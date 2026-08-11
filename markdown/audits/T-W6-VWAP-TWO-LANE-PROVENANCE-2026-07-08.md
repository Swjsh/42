> ⚠️ **CORRECTION 2026-08-11:** this doc's characterization of vwap_continuation's live −6% premium stop as *validated* is contradicted by broker-realized evidence: across n=126 real fills, tight %-stop configs returned −$28.96/tr vs +$33.43/tr for structure/−50% (PIPELINE-AUDIT 2026-08-11), VWAP failed its frozen prereg (TIGHT-STOP-VWAP-2026-08-11: drop-best −$1,631, 2/4 days), and the G4 mechanism check found 12/17 premium-stop deaths at <10% adverse — the stop reads the spread. Stop-widening is licensed at 8 VWAP fill days (now 4/8). The two-lane provenance HISTORY below remains accurate as history.

# T-W6 — vwap_continuation two-lane exit-shape provenance (investigation, read-only)

**Per HANDOFF-2026-07-11-CONFIRM-AND-WIRE T-W6. Git-archaeology + code-read only — no code
changed. Reconciliation itself is a J/STOP-B decision (flagged below).**

## THE ANSWER

**The `-0.06/+0.40` core-lane cell is the currently-validated one. The `-0.08/+0.30`
fleet-lane cell (`strategies.py`) is STALE — it is the value BOTH lanes shared as of
2026-07-02, but only the core lane received a later, separately-validated walk-forward
refinement (2026-07-07) that nobody propagated to `strategies.py`.**

## THE TWO LANES, WITH RECEIPTS

| lane | arms | source | current value | last touched |
|---|---|---|---|---|
| **fleet** | safe-1/3, risky-1/3 | `automation/state/fleet/strategies.py` `VWAP_CONTINUATION.exit` | `premium_stop_pct=-0.08, tp1_premium_pct=0.3` | commit `667217a` (2026-06-26) — **the only commit that has ever touched this file's VWAP_CONTINUATION block.** `git log -p -- automation/state/fleet/strategies.py` shows exactly one historical version of that line. |
| **core** | safe-2, bold-2 | `automation/state/params.json` `j_vwap_cont_premium_stop_pct` / `j_vwap_cont_tp1_pct`, read via `heartbeat_core.py` `_SETUP_EXIT_OVERRIDES["vwap_continuation"]` (L998-1000) | `premium_stop_pct=-0.06, tp1_premium_pct=0.40` | params.json diff `-0.08/0.30 -> -0.06/0.40`, doc key `_j_vwap_cont_exit_updated_2026_07_07` |

## TIMELINE (both lanes started IDENTICAL, then diverged)

1. **2026-06-26** — `strategies.py` created (fleet lane). `VWAP_CONTINUATION.exit` set to
   `-0.08/+0.30/tp1_qty_fraction=0.667/trailing`. This is the ONLY value it has ever had.
2. **2026-07-02** — `vwapcont-exit-parity.json` A/B study (n=149 real-fills, ATM Safe-2):
   found that, un-overridden, a vwap_continuation fill was exit-managed by the
   `ribbon_ride` shape (`-20%/+150%`) because `_SETUP_EXIT_OVERRIDES` omitted the setup —
   a WR-22.1%, negative-anchor-capture (-$97.2) mismatch. Winner cell
   `proposed_live_atm_stop8` (`-0.08/+0.30`) shipped to the **core lane only**:
   `params.json: j_vwap_cont_premium_stop_pct=-0.08, j_vwap_cont_tp1_pct=0.30` +
   `heartbeat_core.py: _SETUP_EXIT_OVERRIDES += vwap_continuation` (CHANGELOG.md, same date).
   At this instant the two lanes AGREE (`-0.08/+0.30` on both).
3. **2026-07-07** — `vwapcont-exit-ab-ship-gate.json` walk-forward + A/B study (same n=149
   population, ATM Safe-2 cell): candidate `-0.06/+0.40` beats the then-current `-0.08/+0.30`
   — full expectancy $47.27->$54.73, OOS(2026, n=42) $66.83->$75.47/tr (+$8.64/tr), WF 1.62,
   drop-top3 +$45.86, anchor edge_capture 44.52->82.04, quarters 5/6 win with 0 much-worse
   window, **all 5 OP-22 gates PASS**, fill coverage exact parity (149/149, 0 dropped either
   side). Guard: `backtest/tests/test_vwapcont_exit_ab_ship_gate.py`. This shipped to
   **params.json only** (`j_vwap_cont_premium_stop_pct=-0.06`, `_tp1_pct=0.40`,
   doc key `_j_vwap_cont_exit_updated_2026_07_07`). `strategies.py` was not part of this
   commit's diff — nothing touched the fleet lane.
4. **2026-07-08 (Fable STOP-A review)** — the corrected engine-contract card surfaces the
   resulting discrepancy: fleet arms trade `-8%/+30%`, core arms trade `-6%/+40%`. Same
   strategy, two numbers, no one had noticed because nothing CHECKS the two lanes agree.

## WHY THIS HAPPENED (root cause, not just symptom)

There is no single source of truth for `vwap_continuation`'s exit shape — it is
duplicated in two independently-editable places (`strategies.py` literal vs.
`params.json` keys read through `_SETUP_EXIT_OVERRIDES`). The 2026-07-07 study updated
the params-key copy (because that's the one `vwapcont-exit-ab-ship-gate.json`'s own
"ship" instructions named) and had no reason to know a second copy existed in
`strategies.py` — the WIRING MAP in HANDOFF-2026-07-11 itself only documents this
duplication as of the 2026-07-08 review. This is the SAME class of bug as C14 (dead/
translated-but-unapplied knobs) but inverted: not a dead knob, a **duplicated live
knob** that drifted after one copy was updated and the other wasn't.

## RECOMMENDATION

**Sync `strategies.py`'s `VWAP_CONTINUATION.exit` to `-0.06/+0.40`** (adopt the core
lane's more recent, separately walk-forward-validated numbers) rather than the reverse,
because:
- `-0.06/+0.40` is the LATER of the two validated cells (07-07 supersedes 07-02) and beat
  `-0.08/+0.30` on the identical 149-trade population under the canonical OP-16 battery
  (all 5 gates PASS, no regression on any sub-window).
- `-0.08/+0.30` was never independently re-validated after 07-07; it is not a competing
  candidate, it is the same cell the 07-07 study already beat.

**This is a wiring fix (propagate an already-validated number), not new research** — but
per the WIRING MAP's shipping gate ("ANY shape change... needs `test_p5_shape_gate.py`
green + STOP-B sign-off"), it still needs a P5-survivor check (or waiver) for the fleet
lane plus STOP-B, same as every other exit-shape edit in this handoff chain. **Do not
edit `strategies.py` from this investigation** — file the recommendation and queue the
J/STOP-B decision per the task's own instruction.

## J-DECISION QUEUED

**[J: sync `strategies.py` VWAP_CONTINUATION.exit to `-0.06/+0.40` (adopt the 07-07
core-lane refinement), or keep both lanes at their current values until a fresh combined
A/B? Recommendation above is to sync to `-0.06/+0.40`.]**

## ⚠ FABLE REVIEW CAVEAT (2026-07-08 late — sharpens the recommendation, C29)

The 07-07 validation of `-0.06/+0.40` was of the **full core-lane shape**: ATM strike
(`j_vwap_cont_strike_offset_safe=0`), `tp1_qty_fraction=0.8`, profit-lock **fixed** arm
+5% — the exit_manager live shape on Safe-2. The fleet lane's `VWAP_CONTINUATION`
ExitShape differs on THREE other fields: `tp1_qty_fraction=0.667`, `profit_lock_mode=
"trailing"`, and per-arm strike tiers (fleet arms size strikes per account, not ATM-locked).
So "sync stop/tp1 to −0.06/+0.40" does NOT reproduce the validated cell on the fleet —
it creates a THIRD combination `(-0.06, +0.40, 0.667, trailing, per-arm strikes)` that no
study has ever run. C29 is exactly this scar: exit knobs ratified on one strike
tier/config don't transfer to another.

**Sharpened recommendation:** the sync decision is not two fields, it is *which full
shape* the fleet should trade. Either (a) port the ENTIRE validated core cell
(−0.06/+0.40/0.8/fixed) into the fleet ExitShape — closest to "propagate the validated
number", still needs its own P5-or-waiver + STOP-B because the fleet's strikes differ —
or (b) leave the fleet lane as-is until the vwap entry/exit matrix (owed, ground rule 11)
covers the fleet's actual strike distribution. Do NOT do the naive two-field edit.

## Sources (quoted, not re-derived)
- `git log -p -- automation/state/fleet/strategies.py` (one commit, `667217a`, touches this file)
- `git log -p -- automation/state/params.json` (the `-0.08/0.30 -> -0.06/0.40` diff hunk +
  `_j_vwap_cont_exit_updated_2026_07_07` doc key)
- `automation/state/params.json` L998-1013 (`heartbeat_core.py` `_SETUP_EXIT_OVERRIDES`)
- `analysis/recommendations/vwapcont-exit-parity.json` (2026-07-02 study, winner
  `proposed_live_atm_stop8`)
- `analysis/recommendations/vwapcont-exit-ab-ship-gate.json` (2026-07-07 study, winner
  `-0.06/+0.40`)
- `backtest/tests/test_vwapcont_exit_ab_ship_gate.py` (guard for the 07-07 ship)
