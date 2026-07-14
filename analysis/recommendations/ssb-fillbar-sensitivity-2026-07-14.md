# SS-B fill-bar-convention sensitivity (2026-07-14)

Generated: 2026-07-14T08:35:33.461639

Runs structure_stop_study.py's SS-A/SS-B/SS-C (+ CONTROL) under BOTH the as-run same-bar-inclusion convention (t4._load_bars / norm_bars_from_esp, `>= entry_ts`) AND the fill-bar-excluded convention (simulator_real's entry_idx+1, the P5/mass-grind/ship-gate authority) -- exactly the sensitivity check the 2026-07-11 fillbar audit ran for t4/t5, extended here to structure_stop_study.py which that audit did not cover.

## Verdict

**SS-B: TOGGLE-STABLE. The certification (ssb_certification_study.py) STANDS.** Beats-CONTROL calls at both layers are identical under both fill-bar conventions.

| Candidate | Layer (a) exp as-run | Layer (a) exp excl. | Layer (a) stable | Layer (b) total as-run | Layer (b) total excl. | Layer (b) stable | Toggle-stable | Severity |
|---|---|---|---|---|---|---|---|---|
| SS-A | $-235.6 | $-235.6 | YES | $-61.1 | $-61.1 | YES | YES | OK |
| SS-B | $-47.34 | $-47.34 | YES | $-604.7 | $-604.7 | YES | YES | OK |
| SS-C | $-236.16 | $-236.16 | YES | $1799.9 | $1799.9 | YES | YES | OK |

## CONTROL reference (both conventions)

- Layer (a) CONTROL expectancy: as-run $-100.67/tr -> excluded $-100.67/tr
- Layer (b) CONTROL anchor total: as-run $-757.1 -> excluded $-757.1

## Disclosures

- Scope: extends the 2026-07-11 fillbar audit (entry-exit-matrix-fillbar-audit-2026-07-11.md, T4/T5 only) to structure_stop_study.py's SS-A/SS-B/SS-C, which reuses t4._load_bars (layer a) and norm_bars_from_esp (layer b) unchanged and was never covered by that audit.
- Convention toggle: EXCLUDED = drop element 0 (the fill bar) from each position's already-prepared norm_bars list, identical technique to test_fill_bar_convention.py::test_t4_replay_bar0_stop_semantics_vs_fill_bar_excluded's bars[1:] probe. entry_premium is unchanged in both conventions (matches the 2026-07-11 audit's own method).
- The SPY-close-based structure-stop trigger (structure_stop_signal_time / spy_lifetime) is NOT toggled -- it is a separate SPY-bar data stream, not an option-bar walk, and was outside the audit's flagged scope.
- structure_stop_study.py itself is UNCHANGED -- this module imports it and calls its existing prepare/run/replay functions unchanged; the excluded-convention variant is built by post-processing already-prepared positions, not by editing the frozen pre-registration or its replay engine.
- Layer (b) makes exactly ONE pass of live Alpaca OPRA option-bar fetches (shared by both conventions via the already-prepared position list) -- not doubled.
- No trading-path file touched (strategies.py / params.json / exit_manager.py / structure_stop_study.py all read-only). No orders placed. No config changed regardless of verdict, per JOB 2 instructions.

