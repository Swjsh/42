# GOAL: LOSS-MECHANISMS-2026-09-08

> Opened by Fable 2026-09-08 19:08 ET after J asked "what are we doing to improve" on a -$116 day (bold-2 -$95 OTM-2 put,
> premium cap; safe-2 -$21 structure stop; both TRENDLINE-tier BEARISH_REJECTION on a premarket-called chop day).
> The shadow ledgers were read BEFORE deciding: day-throttle T-2 is +$512 (11 winners blocked) in the forward
> window -> not a lever; conviction V-d1 is an adjudicated KILL; trendline-only rail HOLDING (rest-of-book is
> worse); catastrophe cap pooled = NULL but splits by strike tier (new prereg filed). The one never-run
> instrument is the 12-cell chop admissibility battery. This goal turns today's mechanisms into decidable
> checkpoint rows -- it ships NO config change (freeze).

## DONE-WHEN
(1) chop battery executed, 12 cells scored, prereg evidence appended, STATUS line quoted; (2) the cap-by-tier
prereg appears in the next CHECKPOINT-2026-09-29.md / SHADOW.md regeneration under the 10-30 EXPANSION group;
(3) STRIKE-MATRIX-2026-08-18.md section 1.1 carries a dated correction (core Bold = V15_BOLD_TIERS OTM-2, not ATM);
(4) CATALYST-DAY-TAG is a written W6 spec for wave_day_conditions (shadow, prereg first) or explicitly parked.

## OPERATING RULES
- CONFIG FREEZE 2026-08-31 -> 2026-10-30: reads, research, docs, preregs only. No trading-path edits.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- STATUS.md gets a line at OPEN and CLOSE only, never per-fire.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] L1 -- chop battery run + adjudication per prereg (Sonnet worker launched 2026-09-08 19:08 ET); verify artifact + evidence block + STATUS line, quote numbers here.
- [ ] L2 -- confirm prereg-catastrophe-cap-by-strike-tier-10-30-2026-09-08 is auto-discovered (SHADOW.md + checkpoint packet after the 23:30 ET regen); if the generator needs a status-string match, fix the generator, never the surface.
- [ ] L3 -- append a dated correction to analysis/deep-research/STRIKE-MATRIX-2026-08-18.md section 1.1 (core Bold live table = V15_BOLD_TIERS -> OTM-2 at $2K-10K per heartbeat_core.py:2679; the 08-04 ATM extension was reverted on the core path; the 2026-09-08 766P vs SPY 767.65 fill confirms). Append, never rewrite.
- [ ] L4 -- CATALYST-DAY-TAG W6 spec (see markdown/planning/FUTURE-IMPROVEMENTS.md): 7th condition for wave_day_conditions, shadow-only, n disclosed; or PARK with reason.

## J-DECISIONS
- None.

## PROGRESS LOG
- 2026-09-08 19:08 ET -- opened by Fable; L1 worker in flight; cap-by-tier prereg written.

## HONEST STATE
Open. Nothing here changes what trades tomorrow. The frozen-window book is negative (rest-of-book -$4.73/trade,
WR 25%, 32 sessions); the September window is the measurement, and 09-15 is the mid-window read.
