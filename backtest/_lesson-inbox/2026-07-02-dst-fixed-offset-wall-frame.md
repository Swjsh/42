# Lesson candidate: a hardcoded UTC offset in the WRITER poisons every naive parse downstream

**Date:** 2026-07-02
**Found during:** WIRE-BOLLINGER (bollinger-squeeze fresh re-verify)
**Canonical audit:** markdown/audits/DST-FRAME-AUDIT-2026-07-02.md

**Symptom:** bollinger_squeeze yielded 316 signals on the research frame but 351
on a DST-correct re-parse of the identical window; diffs clustered exclusively
Nov-Mar.

**Root cause:** `tools/extend_data_v2.py` (SPY branch) wrote `utc - 4h` + a
hardcoded `-04:00` suffix year-round. UTC instants correct, offset LABEL wrong
in EST months. Every consumer that parsed naively and stripped tz (build_rth,
orchestrator RTH slice, replays, null_baseline) kept WALL time: EST sessions
lost their last true trading hour to the RTH filter, thin IEX premarket prints
parsed as the RTH open, and all winter labels sat +1h. 129/365 trading days of
the master affected. The VIX branch of the SAME file did it correctly
(tz_convert + %z) — the asymmetry hid for 6 months because all validation
sprees since May ran on EDT months where the conventions agree.

**Fix shape (Phase A shipped):** canonical frame module `lib/et_frame.py`
(wall-v1 legacy / et-v2 correct), explicit `frame=` threading through
build_rth -> family_grind -> simulate_trade_real so the SPY<->OPRA join can
never mix conventions; writer emits real `%z`; 8 graduated guards
(`tests/test_et_frame_guards.py`) pin BOTH conventions; defaults stay wall-v1
until re-validation diffs are filed (no silent swap).

**Generalizable lessons:**
1. **Serialize timestamps with the REAL offset (`%z` after tz_convert), never a
   constant suffix.** A wrong label with a right instant is a delayed-fuse bug:
   correct in the season it was written, wrong half the year.
2. **A naive `pd.to_datetime` + tz-strip is a frame CHOICE, not a no-op** —
   name the convention, guard both, and thread it explicitly across every join
   boundary (bars<->options<->VIX).
3. **Season-blind validation hides season-dependent bugs**: every "fresh
   re-verify" since May ran on EDT-only tails. Re-validation batteries must
   include at least one EST-month slice (candidate graduated guard: any
   detector re-verify window must span both DST regimes or disclose why not).
4. When two writers in one file disagree on convention (SPY vs VIX branch),
   that asymmetry IS the bug report — diff sibling code paths.

**Candidate lesson families:** C6 (look-ahead: naive SPY<->VIX joins gave
winter VIX 1h ahead), C7 (silent success — grinds exited 0 on a truncated
frame), C14 (convention knob unbound/implicit).
