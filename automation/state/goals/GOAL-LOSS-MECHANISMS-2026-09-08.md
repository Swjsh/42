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
- [x] L1 -- chop battery run + adjudication per prereg (Sonnet worker launched 2026-09-08 19:08 ET); verify artifact + evidence block + STATUS line, quote numbers here. VERIFIED 2026-09-10 (conductor): STATUS.md 2026-09-08 19:18:50 ET line quotes "12/12 cells scored (n=208 pos/26 dates ... 2 gate-nominal PREREG killed by multiplicity ... 6 REJECT, 4 NULL". Artifact confirmed live: `analysis/deep-research/CHOP-DEFENSE-2026-08-06.json` exists (40627 bytes), keys `{_doc, artifact, prereg, population_A, population_B, cells, cells_population_B_detail}`.
- [x] L2 -- confirm prereg-catastrophe-cap-by-strike-tier-10-30-2026-09-08 is auto-discovered (SHADOW.md + checkpoint packet after the 23:30 ET regen); if the generator needs a status-string match, fix the generator, never the surface. FIXED 2026-09-10 (conductor), commit follows this entry: the prereg was FROZEN 2026-09-08 with NO matching row in `checkpoint-2026-09-29-inventory.json` -- confirmed absent (grep for "catastrophe" only matched the unrelated parent-study row) and therefore invisible to every packet regen since (checked SHADOW.md + checkpoint-packet-2026-09-10.json before the fix: zero hits). Added inventory row `catastrophe-cap-by-strike-tier` (classification expansion, checkpoint 2026-10-30) + a new `_score_catastrophe_cap_by_strike_tier` scorer in `setup/scripts/checkpoint_packet.py` that splits `catastrophe-cap-shadow-ledger.jsonl` by arm into the ATM/OTM pools per the prereg's own populations text, counts only forward (post-freeze-date) rows, and correctly reports INSUFFICIENT N (live: atm_pool_forward_n=0, otm_pool_forward_n=0, both pools have 0 forward fills as of today, plus no `cap_70_counterfactual_pnl` ledger column exists yet so the ACT gate math can't run even once n accrues). Re-ran the real generator: `python setup/scripts/checkpoint_packet.py` -> row now appears in `analysis/recommendations/checkpoint-packet-2026-09-10.json` and `markdown/planning/CHECKPOINT-2026-10-30.md` (grep confirmed, table row + detail section both present). New guard `backtest/tests/test_checkpoint_packet_catastrophe_cap_by_strike_tier_2026_09_10.py` -- 4 passed; RED-proofed via `git stash` of both source files -> `AttributeError: module 'checkpoint_packet' has no attribute '_score_catastrophe_cap_by_strike_tier'` (exact missing-scorer signature) -> stash popped, 4/4 green again. Broader `pytest tests/ -k checkpoint_packet` -> 33 passed. Curated safety gate `tests/run_safety_gate.py` -> 59 passed, PASS.
- [x] L3 -- append a dated correction to analysis/deep-research/STRIKE-MATRIX-2026-08-18.md section 1.1 (core Bold live table = V15_BOLD_TIERS -> OTM-2 at $2K-10K per heartbeat_core.py:2679; the 08-04 ATM extension was reverted on the core path; the 2026-09-08 766P vs SPY 767.65 fill confirms). Append, never rewrite. DONE 2026-09-10 (conductor): verified live at `heartbeat_core.py:2679` (`ss.V15_BOLD_TIERS if account == "bold" else ss.V15_SAFE_TIERS`, comment block 2667-2678 confirms the ATM wire was reverted 2026-08-20 after `bold_tier_rail.py` triggered negative at n=25, -$808 WR24% vs OTM-3's +$406 WR50%). Appended a `> **DATED CORRECTION (2026-09-10 ...)**` blockquote directly after section 1.1's existing discrepancy paragraph, original table/prose left byte-unchanged (append-only, per instruction).
- [ ] L4 -- CATALYST-DAY-TAG W6 spec (see markdown/planning/FUTURE-IMPROVEMENTS.md): 7th condition for wave_day_conditions, shadow-only, n disclosed; or PARK with reason.

## J-DECISIONS
- None.

## PROGRESS LOG
- 2026-09-08 19:08 ET -- opened by Fable; L1 worker in flight; cap-by-tier prereg written.
- 2026-09-09 23:03 ET — opened by goal_autopilot
- 2026-09-10 01:xx ET (conductor AFTERHOURS) -- L1 verified (STATUS quote + artifact check), L2 FIXED (checkpoint_packet.py gained a `catastrophe_cap_by_strike_tier` scorer + matching inventory row; the prereg now auto-discovers into the real 10-30 checkpoint packet/markdown, confirmed live), L3 DONE (STRIKE-MATRIX-2026-08-18.md section 1.1 dated correction appended). L4 left open for next fire (spec-writing deserves its own bounded pass). Guard: `backtest/tests/test_checkpoint_packet_catastrophe_cap_by_strike_tier_2026_09_10.py` (4 tests, RED-proofed via git-stash). Curated safety gate 59 passed.
## HONEST STATE
Open. Nothing here changes what trades tomorrow. The frozen-window book is negative (rest-of-book -$4.73/trade,
WR 25%, 32 sessions); the September window is the measurement, and 09-15 is the mid-window read.
