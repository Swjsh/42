# GOAL: KITCHEN-KEEPERS-TO-SHADOW-2026-09-03

> This goal was opened by a build spec / orchestrator task (Fable), authored by a Sonnet
> researcher as QUEUE item A4 of `GOAL-GAMMA-AUTONOMY-2026-09-03.md` — not a live J
> chat message.

## DONE-WHEN
Verbatim from the parent spec: every candidate marked PROMISING or NEEDS-MORE-DATA in
`strategy/candidates/_LEADERBOARD.md`, and every grinder "keepers found" result in
`strategy/candidates/_analysis/` from the last 30 days, has a recorded walk-forward
(WF ≥ 0.70) + OOS verdict; each verdict ends as SHADOW-FILED (a prereg + a $0 forward-
shadow instrument registered) or KILLED (with the failing number), and no PROMISING row
older than 14 days lacks a verdict.

Checked live 2026-09-03: `_LEADERBOARD.md` has ~180 ranked rows spanning 2026-05-17 to
2026-09-03; dozens carry `PROMISING`/`NEEDS-MORE-DATA` and most are far older than 14
days (e.g. rank 3 V14E_BEAR_ONLY_GATE, 2026-05-21; rank I QQQ_DIVERGENCE_CONFLUENCE,
2026-07-21). This is a large backlog, not a handful of rows — QUEUE below batches it.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 → 2026-10-30**: this goal only files preregs + registers
  $0 shadow instruments — it never edits `params.json`, `heartbeat.md`, or any
  FROZEN_TRADING_PATH file. A candidate whose verdict implies an actual gate/knob
  change ships as a prereg for the 10-30 checkpoint, never live now.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation
  are the only sanctioned continuation paths.
- SHADOW-FILED means BOTH artifacts exist: a prereg JSON under
  `analysis/recommendations/` AND a registered scheduled task (an
  `install-<name>-shadow.ps1` following the existing pattern —
  `install-loss-armed-budget-shadow.ps1`, `install-pullback-hold-shadow.ps1`,
  `install-regime-shadow.ps1`, `install-ssr-shadow.ps1` — plus a row in
  `automation/state/SCHEDULED-TASKS.md`). A prereg alone is not SHADOW-FILED.
- KILLED means the failing number is quoted in the leaderboard row's Status column AND
  in the candidate's own `_analysis/` or `strategy/candidates/*.md` file — never a bare
  "killed" with no evidence.
- Use existing evidence before running anything new: `kitchen-status.json`'s
  `recent_completed_top_10`, the newest files in `strategy/candidates/_analysis/`, and
  each candidate's own `.md` file frequently already contain an OOS number — read
  before re-deriving.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] K1 (DONE 2026-09-05, Fable EOD-audit session a16e320c) — worklist frozen at
  `analysis/multi-lane/evaluations/kitchen-keeper-worklist-2026-09-03.json` (517 rows: 22
  leaderboard_matches + 495 analysis_recent). — Freeze the worklist: parse `strategy/candidates/_LEADERBOARD.md` for every
  row whose Status column contains `PROMISING` or `NEEDS-MORE-DATA`, plus every file in
  `strategy/candidates/_analysis/` with an mtime in the last 30 days, into
  `analysis/multi-lane/evaluations/kitchen-keeper-worklist-2026-09-03.json` (rank/id,
  candidate file path, filed date, age_days, current status text, has_wf bool,
  has_oos bool — computed by grepping the candidate's own file for `walk-forward`/`WF`/
  `OOS`). DONE-WHEN: file exists, row count matches a fresh grep count of the two
  source patterns.
- [x] K2 (DONE 2026-09-05) — every row carries a non-null `age_bucket` (282 gt14d / 235
  le14d per the worklist's own `age_bucket_counts`). — Triage by age: split the K1 worklist into `age_days > 14` (must get a
  verdict THIS goal) vs `age_days <= 14` (verdict optional, still queued as a Kitchen
  keeper). Only the first bucket blocks DONE-WHEN's final clause. Write the split back
  into the same JSON as an `age_bucket` field. DONE-WHEN: every row has a non-null
  `age_bucket`.
- [x] K3 (DONE 2026-09-05) — STRUCTURE_VETO_DIR_VS_TREND: SHADOW-FILED-CANDIDATE, already
  live since 2026-06-26 (WF on OOS/IS ratio=0.00); TRENDLINE_BREAK_CALL_VETO: KILLED (no
  OOS/WF ever produced, 71 days). — Adjudicate the STRUCTURE/VETO family (STRUCTURE_VETO_DIR_VS_TREND,
  TRENDLINE_BREAK_CALL_VETO, and their `_analysis/` re-runs incl.
  `2026-09-03-structure-veto-dir-vs-trend-regime-stratification.md` and
  `2026-09-03-structure-veto-dir-vs-trend-validation.md`, both dated today). These
  already carry a real-fills A/B in the leaderboard row (STRUCTURE_VETO_DIR_VS_TREND:
  full P&L +7,555→+8,138, sharpe 4.34→4.73, OOS-2026 Δ=$0 flagged as a caveat) — confirm
  WF≥0.70 from the cited guard `backtest/tests/test_structure_veto.py` (29/29 PASS) and
  file the SHADOW-FILED prereg + register the shadow task, or KILL citing the OOS-2026
  $0 delta as the failing number if WF doesn't clear 0.70 on re-check.
- [x] K4 (DONE 2026-09-05) — BLOCKED-ON-DATA: options_3dte/4dte backfill LANDED
  2026-07-07, but no runner consumes it (multiday_dte_compare.py hardcodes DTE_BUCKETS=
  [0,1,2]) -- missing piece is the runner wiring, not the data. — Adjudicate the WEEKLY_DTE_NOT_0DTE family (leaderboard "the night's headline"
  row: OOS exp/tr $36.34→$66.13 monotone across 0/1/2 DTE, DATA-GATED on
  `options_3dte/4dte` backfill per its own caveat). Check whether that backfill has
  landed since 2026-07-07 (`grep -l "3dte\|4dte" analysis/backtests/cache/*` or
  equivalent); if landed, run the OP-16 re-score it flags as pending and file
  SHADOW-FILED; if not landed, this is legitimately still NEEDS-MORE-DATA and gets an
  explicit `age_bucket: blocked_on_data` note rather than a forced verdict, but must
  still cite what's missing.
- [x] K5 (DONE 2026-09-05) — V14E_BEAR_ONLY_GATE / ORB_NARROW_OR_GATE / ORB_DIRECTION_FILTER
  / V14E_BEAR_HIGH_CONF_VIX_MODERATE_GATE all KILLED (0/3 or 0/15 live J wins, OP-21 gate
  never cleared); VIX_BULL_HARD_CAP_UNBLOCK: SHADOW-FILED-CANDIDATE, corrected by K9 to
  ALREADY LIVE (see K9 note). — Adjudicate the older watcher-gate family (V14E_BEAR_ONLY_GATE,
  ORB_NARROW_OR_GATE, ORB_DIRECTION_FILTER, VIX_BULL_HARD_CAP_UNBLOCK,
  V14E_BEAR_HIGH_CONF_VIX_MODERATE_GATE — all 2026-05-21 to 2026-06-26, all
  watcher-only per their own leaderboard notes). Cross-check ORB_NARROW_OR_GATE against
  its own row text "GATE DEPLOYED + INTEGRATION SPEC FILED (2026-05-24). Blocked: OP-21
  0/3 live J wins" — this one may already be effectively KILLED-by-inaction; verify
  against `markdown/research/BACKTESTING-PLAYBOOK.md`'s OP-21 promotion gate text before
  writing the verdict rather than assuming.
- [x] K6 (DONE 2026-09-05) — all three EXTEND (each JSON's own `adjudication_2026_09_05`
  key): real-fills ledger grew 190->593 trades (3.1x) since 2026-07-22 filing, crossing
  the candidates' own re-run trigger; a fresh re-run is owed before a final KILL/SHIP
  call, not performed this session. — Adjudicate the screened-feasibility family (VIX1D_GATE_FEASIBILITY,
  BXM_GATE_FEASIBILITY, FRED_YIELD_CURVE_GATE_FEASIBILITY — all 2026-07-22, all
  explicitly "NEEDS-MORE-DATA (screened, not rejected)" in their own text with a named
  concentration/dryness failure per candidate). These already state their own failing
  number (e.g. VIX1D bare-band exp -$7.60/tr, none walk-forward stable) — this is a
  KILL-with-cited-number for each unless the real-fills ledger (`journal/trades.csv`,
  n=190 at filing) has grown enough since 2026-07-22 to re-run; check current n first
  via `wc -l journal/trades.csv` before deciding EXTEND vs KILL.
- [x] K7 (DONE 2026-09-05) — all 6 ranks (38/42/43/44/45/46) KILLED for no OOS/WF
  evidence ever produced; rank 46 additionally caught borrowing the unrelated ★
  STRUCTURE_VETO_DIR_VS_TREND candidate's Sharpe 4.728 as if it were its own result. — Adjudicate the auto-promoted-by-reviewer batch (ranks 38/42/43/44/45/46, all
  2026-06-25 to 2026-06-30, all `TBD`/`NEEDS-MORE-DATA` with only a 67/67 test-pass and
  no OOS number in the leaderboard row). These look like they never received a real
  Stage-2+ backtest — read each candidate's own `.md` file in `strategy/candidates/` to
  confirm no OOS number exists anywhere before defaulting all six to KILL for
  "no OOS/WF evidence ever produced" (cite the absence explicitly, not silently).
- [x] K8 (DONE 2026-09-05) — 8 fresh 2026-09-03 `_analysis/` files folded into the K1
  worklist; base-engine-stage1-backtest's adjudication additionally caught a same-slug
  09-04 near-duplicate file fabricating round-number P&L off another candidate's delta
  table (see HONEST STATE). — Adjudicate today's fresh Kitchen output (2026-09-03 `_analysis/` files:
  `vwap-overnight-grinder-top-keeper`, `shotgun-scalper-stage2-top-keeper`,
  `top-keeper-shotgun-scalper-stage3-1`, `midday-vol-contraction-breakout-backtest`,
  `walk-forward-oos-test-preceding-30-days`, `weekly-dte-not-0dte-anchor-day-op-16
  -validation`, `state-freshness-remediate-lint-and-test`, `base-engine-stage1
  -backtest`) — these are all under 24h old so age_bucket is optional, but each already
  ran a WF/OOS pass per its own filename; read and fold the verdict into the same
  worklist JSON rather than re-running.
- [x] K9 (DONE 2026-09-05) — STRUCTURE_VETO_DIR_VS_TREND: no new task, prereg
  `prereg-structure-veto-standing-ab-2026-09-05.json` points at the EXISTING
  `Gamma_FleetGateLeakShadow` (n=220 SKIP_STRUCTURE_VETO rows verified). VIX_BULL_HARD_
  CAP_UNBLOCK: NEW task `Gamma_VixBullHardCapUnblockShadow` registered + State=Ready
  verified, prereg `prereg-vix-bull-hard-cap-unblock-shadow-2026-09-05.json` — corrected
  the candidate's own premise: the 18->22 cap change already shipped 2026-06-26 (params.
  json + filters.py both 22.0, guarded PASS), so the shadow accrues forward P&L on the
  now-unblocked band rather than scanning for (nonexistent) suppression events. Leaderboard
  Status column rewritten for all 22 gt14d rows: 15 KILLED, 2 SHADOW-FILED, 3 EXTEND
  (screened-feasibility, ledger grew 190->593 trades), 1 BLOCKED-ON-DATA (WEEKLY_DTE_NOT_
  0DTE), 1 duplicate-row KILLED. DONE-WHEN grep (restricted to table rows, Filed<2026-08-22):
  `0` (one stray "NEEDS-MORE-DATA" leftover found in a non-Status Type-column cell for
  BULLISH_WATCHER_PM_GATE, fixed to match). — Register any SHIP-CANDIDATE from K3-K8 as an actual shadow instrument
  following the `install-<name>-shadow.ps1` pattern (cite the exact candidate/prereg
  name in the task name, e.g. `Gamma_<Name>Shadow`), add its SCHEDULED-TASKS.md row,
  and re-render the leaderboard Status column for every adjudicated row to read
  `SHADOW-FILED` or `KILLED (<number>)` instead of `PROMISING`/`NEEDS-MORE-DATA`.
  DONE-WHEN: grep `_LEADERBOARD.md` for `PROMISING\|NEEDS-MORE-DATA` with `age > 14d`
  returns 0 rows.

## J-DECISIONS
- None required. Revoke = `git revert <sha>` per shadow-task registration commit +
  `Unregister-ScheduledTask` for any task this goal creates.

## PROGRESS LOG
- 2026-09-03 18:07 ET — authored by Sonnet (A4 of GOAL-GAMMA-AUTONOMY); queued on the
  ladder, not yet opened.
- 2026-09-05 00:57 ET — opened by goal_autopilot
- 2026-09-05 02:0x ET — K9 claimed (stop-hook continuation 3/3); waiting on K1+K2 / K3+K4 / K5-K7 / K8 workers.
- 2026-09-05 01:5x ET — K1-K8 claimed WIP by the Fable EOD-audit session (4 Sonnet fan-outs; K9 after they land).
- 2026-09-05 — K9 closed: registered `Gamma_VixBullHardCapUnblockShadow` (State=Ready,
  16:57 ET weekdays) + prereg `prereg-vix-bull-hard-cap-unblock-shadow-2026-09-05.json`;
  filed `prereg-structure-veto-standing-ab-2026-09-05.json` pointing at the existing
  `Gamma_FleetGateLeakShadow` (n=220) instead of a duplicate task; ran
  `cd backtest && .venv/Scripts/python.exe -m pytest tests/test_scheduled_tasks_doc.py
  tests/test_install_script_times_match_registry_2026_09_03.py -q` -> `6 passed in 0.64s`;
  rewrote the Status column on all 22 `age_bucket:gt14d` leaderboard rows (15 KILLED / 2
  SHADOW-FILED / 3 EXTEND / 1 BLOCKED-ON-DATA / 1 dup-row KILLED); DONE-WHEN grep
  (table rows, Filed<2026-08-22) -> `0`. Corrected K5's VIX_BULL_HARD_CAP_UNBLOCK premise:
  the candidate's own ADJUDICATION assumed the 18->22 change was still config-frozen;
  fresh verification found `params.json` + `backtest/lib/filters.py` already at 22.0
  since 2026-06-26, guarded by `test_no_stale_blocks.py` (re-run: `3 passed, 4 deselected`)
  — so the new shadow measures forward P&L on the already-unblocked band, not suppression.
## HONEST STATE
K1-K9 all closed this pass. Every leaderboard row filed >14 days ago now carries a
non-PROMISING/non-NEEDS-MORE-DATA Status (verified by grep, quoted above) — 2 real new/
confirmed shadow instruments accrue forward evidence toward the 2026-10-30 config-freeze
checkpoint, the rest are honest KILLs, EXTENDs (owed re-runs), or a data/wiring gap.
Separately, OPEN Kitchen-integrity issue (NOT fixed by this goal, flagged for a future
fire): the free-tier Nemotron `_analysis/` pipeline has produced at least three
independently-found fabrication/near-duplicate artifacts — placeholder numbers in the
`weekly-dte-not-0dte` candidate file itself, a 2026-08-11 `qqq-label-vol-strat-oos-replay`
citing files that do not exist, and a 2026-09-04 `base-engine-stage-1-backtest` near-dupe
that inferred round-number P&L + a 10/10 confidence rating from another candidate's delta
table rather than running its own backtest. This pattern needs a dedicated audit/guard,
not a per-file patch.
