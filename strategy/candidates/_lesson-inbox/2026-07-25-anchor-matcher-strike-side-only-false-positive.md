# Lesson candidate: a strike+side-only anchor matcher can silently accept a 2h+ time-distant collision as "matched"

**Filed:** 2026-07-25 (conductor, AFTERHOURS/weekend), ZERO-FOR-TWELVE-POSTMORTEM follow-up.

**Symptom:** `engine_fullhist_replay.py`'s sanity-anchor check reported the 2026-07-17 anchor day
as "2/4 live entries reproduced by strike+side" -- a partial pass. The real number, once the
matcher required time proximity, is 1/4. One of the two "matched" rows paired a live 11:40 P745
fill to a replay 13:55 P745 entry -- **2h15m apart**, a genuinely different signal that happened
to share strike+side (options only have ~10-20 strikes trading a given day, so strike+side
collisions across unrelated signals are common, not rare).

**Root cause:** the matcher's join key (strike + side) was necessary but not sufficient. Without
a time-proximity bound, "did the same trade happen" degenerates into "did ANY trade on this
strike+side happen anywhere in the session" -- which two independently-triggered signals will
satisfy by chance far more often than intuition suggests, especially on a single-underlying
0DTE book where the whole day's activity clusters around a handful of ATM/near-ATM strikes.

**Fix:** `match_entries_by_strike_side_time(expected, replayed, time_tol_minutes=20)` --
requires strike+side+time-window (closest-in-time tiebreak among candidates), consumes each
replayed entry at most once. Guard: `backtest/tests/test_engine_fullhist_replay.py::
test_match_entries_rejects_time_distant_strike_side_collision` (RED on the old 2h15m-accepting
behavior, anti-vacuity sibling confirms an exact-time match still passes).

**Generalizable rule (fold target: C6 causality / C4 disclosure, or a new sibling):** any
anchor/ground-truth matcher that joins on a coarse key (symbol, strike+side, ticker, setup name)
MUST also bound the match by TIME PROXIMITY to the expected event. A coarse-key-only match
degrades silently from "verified this specific trade happened" to "verified something with this
label happened somewhere in the window" -- and the failure is invisible because the match still
reports as a PASS, just a wrong one. Any future full-history/anchor-fidelity harness (there will
be more, per the SHARED-DECISION-LIBRARY-MIGRATION effort) should default its matcher to a
strike+side+time-window join, never strike+side alone.

**Downstream consequence (do not over-claim):** this correction does NOT change the ALREADY
KNOWN root cause of the entry-layer gap itself (live's curated + multi-day memory-merged
`key-levels.json` feed vs `orchestrator.run_backtest`'s bars-only level recomputation, disclosed
in `test_engine_fullhist_replay.py`'s own docstring before this fire) -- it quantifies that the
gap bites 3x harder than first reported (3/4 live entries have zero batch counterpart, not 2/4).
It also does NOT explain `vwap_continuation`/`vix_regime_dayside`'s 0-for-12 result directly --
those are validated by a SEPARATE harness family (`backtest/autoresearch/_b5_vix_regime_dayside.py`
and siblings), not `orchestrator.run_backtest`. Named next step (queue.md
`ZERO-FOR-TWELVE-POSTMORTEM`): audit whether that autoresearch harness family sources levels the
same batch-computed-only way -- if so, that is the mechanism that would explain the 0-for-12.
