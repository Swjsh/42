# LESSON CANDIDATE: a gate's STATUS LABEL can drift from the boolean it's supposed to describe

**Date:** 2026-08-01 (conductor WEEKEND fire, ~04:15-05:10 ET)

**Symptom:** `g2_trendline_bypass_ab_2026_08_01.py`'s first run reported ARM_EXTEND as
`SHIP_CANDIDATE` with gates `[UNDETERMINED, PASS, PASS, PASS, PASS]`. The frozen pre-reg
(`prereg-g2-trendline-bypass-2026-08-01.json`, `known_data_gap_disclosed_before_running`)
explicitly states: *"If G1 comes back UNDETERMINED, the ship rule below treats it as a
non-PASS ... it does not silently default to PASS."* The printed gate list showed
`UNDETERMINED` in plain sight — and the arm still shipped, because `all_gates_pass` was
computed from a `pass` boolean that `relabel_g1_measurability` never touched.

**Root cause:** the relabeling function (adapted from `filter5_ribbon_fate_2026_07_31.py`'s
own `relabel_g1_measurability`, which has the SAME latent gap but happened not to be
exercised there — its ARM_A/ARM_B both failed G2/G3 independently regardless) only mutated
`gates["G1..."]["status"]` (a display string) while leaving `gates["G1..."]["pass"]` (the
boolean `all_gates_pass = all(g["pass"] for g in gates.values())` actually reads) at
whatever the raw measured-sign test produced. A human/report reader sees `UNDETERMINED` and
correctly infers "not decided" — but the code computing the SHIP/NULL verdict was still
reading the boolean underneath, which said `True`.

**Why it matters (C7 class, one level deeper than the usual "silent success"):** this is
not a producer going quiet — it is a producer LOUDLY printing the correct caveat
(`UNDETERMINED`) right next to a verdict that ignores it. The two fields told different
stories from the same gate object, and only the boolean one drove behavior. A reviewer
skimming the console log or the markdown table would see "UNDETERMINED" in the gate column
and reasonably assume the ship rule respected that — the same failure shape as any
dashboard where the display and the decision path read different state.

**Caught how:** OP-33 self-review before reporting the result — re-read the frozen pre-reg's
own ship-rule text against the printed gate table and noticed the mismatch, rather than
reporting the `SHIP_CANDIDATE` headline. No downstream action (no params/live wiring) had
been taken on the buggy result yet, so the fix was a same-session postprocessing correction
re-derived from the already-computed per-trade JSON (no re-run of the ~3.5min backtest) —
final verdict flipped `ARM_EXTEND_SHIPS` -> `NEITHER_SHIPS_STAYS_TRENDLINE_ONLY`.

**Fix shipped (this fire):** `relabel_g1_measurability` now sets `g1["pass"] = False`
whenever it sets `status = "UNDETERMINED"`, and a new `_recompute_verdict()` re-derives
`all_gates_pass`/`verdict` from the gates dict AFTER relabeling runs (the original
`score_arm()` computes `all_gates_pass` too early, before any relabeling can touch it — that
ordering dependency is itself worth remembering: any post-hoc gate relabeling function MUST
recompute the aggregate verdict, never assume the caller will).

**Generalizable pattern — worth auditing anywhere a gate's status is "corrected" after the
fact:** if a function's job is to override or annotate an EXISTING pass/fail decision (a
relabel step, a manual override, a data-quality caveat), check that it mutates the SAME
field the aggregate/ship decision actually reads, not just a sibling display field. Two
fields describing "the same fact" (a human-readable status string + a machine-readable
boolean) will drift unless one is derived FROM the other, never maintained in parallel.
Specifically flagged for follow-up: `filter5_ribbon_fate_2026_07_31.py`'s own
`relabel_g1_measurability` has the identical latent gap (never exercised because both its
arms failed other gates independently) — worth a defensive pass if that script is ever
reused as a template again, which it already has been twice (structure-shift-cascade,
filter5, and now this study).
