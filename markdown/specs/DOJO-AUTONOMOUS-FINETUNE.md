# THE DOJO — autonomous fine-tune mode (Opus, 2026-07-20 night, J-directed)

> J (going to bed): "figure out how to use the dojo like i wanted and fine tune the engine for
> us." This is the AUTONOMOUS complement to the interactive walkthrough. Companion to
> DOJO-REPLAY-TRAINING-SPEC.md + DOJO-ARCHITECTURE-DECISION.md.

## The split (what CAN vs CANNOT be done without J in the room)

- **ENTRY fine-tuning is interactive-only.** "Should the engine have taken this / skipped that"
  is J's discretionary chart read. It needs him at the wheel, bar by bar. The dojo's live
  sessions own this. NOT done autonomously (doing so = inventing J's judgment = exactly the
  overfit-to-my-own-guess trap).
- **EXIT fine-tuning IS autonomous-safe.** "Given the engine's OWN entries, which of J's defined
  exit profiles banks best" is a deterministic, real-fills question. The engine picks the
  entries (no human needed); the arms' exit profiles are the variable. This is the exact
  exit-diversity experiment J defined 2026-07-20, run headless. THIS is what "fine tune the
  engine for us" cashes out to overnight.

## The autonomous harness (exit-diversity replay)

`backtest/tools/dojo_exit_diversity_replay.py` — reuses dojo/engine_step (entries) +
dojo/sim_executor (per-profile fills/exits via exit_manager_walk). NO TV MCP (headless).

1. **Curriculum days:** 2026-07-17 (+$679 day), 2026-07-20 (red), 06-30 / 07-02 / 07-08 (the
   HTF-level days J flagged), plus every real-fills day with >=1 engine entry in the OPRA cache
   window. More days = more n = less overfit.
2. **Signals = the engine's own entries.** For each day, engine_step over the RTH bars; every
   would_place=True bar (ENTER_BEAR/ENTER_BULL) is an entry event (strike/qty per the live tier).
3. **Race the exit profiles on the SAME entry:** CONTROL (live trigger-exact structure stop +
   chandelier = risky-1/core), RIBBON (ribbon-flip stop = safe-3), ZONE-RIDE (wider trail =
   risky-3) — the exact exit_patch configs in accounts.json. sim_executor walks each.
4. **Score:** per-profile P&L per-day AND aggregate; per-episode; concentration (does a winner
   ride on 1-2 trades? — C4/C24); sub-window stability across the curriculum; real-fills only.

## THE SHIP GATE (anti-overfit law binds — this is the danger zone)

A profile is a SHIP candidate ONLY if it beats CONTROL on aggregate AND on a majority of
curriculum days AND the edge is NOT concentration-driven (survives dropping its top trade) AND
holds on a held-out day subset. Frozen pre-reg BEFORE running. Consistency check: tonight's
STRUCTURE-STOP-REFERENCE-LEVEL A/B already found REF-ZONE WORSE on population (-$63.73/tr vs
-$47.34) — if this broader harness disagrees, RECONCILE before trusting it (don't let the new
instrument overturn a frozen finding without explaining why). If a candidate clears: wire core's
exit behind a guard + one-line revert + REVOKE report (paper path, doctrine-allowed). If NOT:
honest kill/hold — "CONTROL holds" is a valid, valuable morning answer. NEVER flip a live param
on dojo replays alone without the full gate.

## Also tonight: make the interactive dojo J's FULL vision

Wire the 3 fleet arms (DOJO-FLEET-HISTORICAL-SIGNAL) so his next live walkthrough shows all
arms differing on the same signal — the "watch them differ" experience. Separate from the
harness (the harness needs only entries + exit profiles, not the fleet gate machinery).

## Morning deliverable to J
(1) The dojo now shows all arms (interactive-ready). (2) The exit-diversity harness ran the
curriculum; here's which exit profile wins, honestly, with the anti-overfit disclosures — and
either a gated ship candidate or a clean "CONTROL holds." (3) Entry fine-tuning awaits your live
sessions; voice-dictation (Win+H) + the runbook make that a sit-down-and-talk experience.
