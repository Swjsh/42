# GOAL: FUTURES-YELLOWS-2026-09-05

> Opened by Fable 2026-09-05 12:01 ET. `setup/scripts/futures_health.py` reads RED today: no_stray_exposure
> (8 anomaly rows, 2026-09-03T00:43 unattributed_closing_fill MES -- the already-fixed 09-03
> flatten cascade, health now buckets by fill date), plus two YELLOWs never root-caused:
> broker_transport (3/7 probes transport errors, 43%, newest 2026-08-31T21:31:57 ->
> H2_SESSION_ARTIFACT) and fills_recency (1 ENTER_REFUSED, last ENTER 2026-09-01). The lane is
> armed intraday-only on paper; a health board that is RED on stale rows and YELLOW on
> unexplained probes is not a board J can trust on Tuesday.

## DONE-WHEN
(F1) no_stray_exposure: prove the 8 anomaly rows are all the 09-03 cascade (order ids / fill
times quoted against the journaled flatten) and that the check's window ages them out by
2026-09-08 (state the exact rule and date); if any row is NOT the cascade, name it and treat as
a live defect. Broker read flat NOW (quote positions + open orders from the futures paper
account via the lane's own client, never a hand-typed number).
(F2) broker_transport: read the probe log the check scores; classify each of the 3 error probes
(transport error vs session-closed artefact mis-bucketed); if H2_SESSION_ARTIFACT probes are
being scored as transport errors, fix the classifier (off-path) with a RED-proofed test; else
name the real transport fault (endpoint, HTTP code, time) and fix or file it. Rate after the
fix quoted.
(F3) fills_recency: the ENTER_REFUSED row -- which gate refused, was it correct (the lane's own
rules), and does the check's "isolated" language match its rule; no change unless the row
reveals a defect; verdict quoted.
(F4) futures_health.py re-run: verdict line quoted; any remaining non-GREEN carries a dated
reason in the goal file.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: no trading-path edits (FROZEN_TRADING_PATH in the pre-commit hook); measurement, instruments, off-path fixes, preregs only.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. No task chips.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire; workers never edit STATUS.md or commit -- the orchestrator does.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.
- Every fix ships with a RED-proofed test (the test fails on the pre-fix code) and one-sentence root cause.
- Verify, don't claim: every DONE item quotes the command output that proves it.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] F1 -- stray-exposure rows attributed to the 09-03 cascade (or not); age-out date stated; broker flat quoted. (DONE: all 8 rows = the fixed cascade; age-out rule was a defect, fixed)
- [x] F2 -- transport probes classified; classifier fixed with RED-proof or the real fault named + fixed/filed. (DONE: no misclassification found; real transport fault named)
- [x] F3 -- ENTER_REFUSED row adjudicated. (DONE: correct no-stacking gate behavior, no defect)
- [x] F4 -- futures_health re-run quoted. (DONE: verdict=RED, no_stray_exposure not-yet-aged-out is EXPECTED per the new rule, not a new defect)

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- authored by Fable (Saturday morning session).
- 2026-09-05 14:33:31 ET -- Fable session a16e320c worker F started F1-F4.
- 2026-09-05 14:41:20 ET -- F1 DONE: all 8 no_stray_exposure anomaly rows are `unattributed_closing_fill`
  MES rows, order_ids {1429073/1429074, 1435171-3} matching the 09-01/09-02 5-contract cascade
  described in STATUS.md ("5-contract cascades on 09-01/09-02 was close-without-cancel", fixed
  09-03 03:23 ET commit 3037fbe4). By fill-event date (`_anomaly_event_date_et`, already fixed
  2026-09-05 differential): 4 rows on 2026-09-01, 4 rows on 2026-09-02 -- 2 sessions, matches
  live `no_stray_exposure` detail "2 session(s)". Age-out rule: pre-fix, `check_no_stray_exposure`
  windowed on `sorted(distinct anomaly-dates in the file)[-5:]` -- since anomalies.jsonl only
  gains rows on NEW incidents and none have landed since the 09-03 fix, that window would have
  stayed pinned on {09-01, 09-02} FOREVER (never ages out) -- a real defect, not what the goal
  assumed. Fixed: setup/scripts/futures_health.py now bounds the window by
  `ANOMALY_MAX_AGE_DAYS = 5` calendar days from `now_et`, independent of new rows landing.
  Exact rule: a row's ET fill-event date must be `>= now_et.date() - 5 days` to count; cutoff on
  2026-09-08 is 2026-09-03, which excludes both 09-01 and 09-02 -- verdict flips RED->GREEN on
  2026-09-08 (pinned by test_stray_exposure_ageout_cutoff_is_exactly_5_calendar_days: still RED
  2026-09-07, GREEN 2026-09-08). RED-proofed: 3/4 new tests FAIL on pre-fix code (git stash
  confirmed), all pass post-fix. Broker flat NOW (TastytradeBroker.connect()+get_positions()+
  get_live_orders(), read-only, no orders/cancels): connected=true, positions=[], is_flat_MES=
  true, 104 total orders returned by API, 0 non-terminal/working orders.
- 2026-09-05 14:41:20 ET -- F2 DONE: read last 10 rows of broker-probe.jsonl (PROBE_RECENT_N).
  Classified via `_probe_row_class`: 3 session_closed (2026-08-29 SESSION_NOT_ACTIVE x3), 4
  healthy (2026-08-23/24/31x2, all H2_SESSION_ARTIFACT with dry_run_ok=true -- correctly bucketed
  healthy, NOT scored as transport errors), 3 error (2026-08-26 PROBE_FAILED, 2026-08-27
  H1_PERMISSIONS, 2026-08-28 H1_PERMISSIONS -- all three carry literal `"error": "ReadTimeout: "`,
  an httpx transport timeout, dry_run_ok=false/None). denom=7, rate=3/7=43%, matches the goal's
  stated "3/7, 43%". Newest row (2026-08-31T21:31:57, H2_SESSION_ARTIFACT) is healthy, not one of
  the 3 errors -- goal text was describing the newest probe, not miscounting it. NO H2_SESSION_
  ARTIFACT probe is scored as a transport error anywhere in the window -- classifier is correct,
  no fix needed. Real transport fault named: all 3 error rows are genuine httpx.ReadTimeout
  against the Tastytrade sandbox cert API on 2026-08-26/27/28 (pre-dating the 2026-08-29 probe
  verdict-taxonomy fix documented in futures_broker_probe.py's own docstring -- these are exactly
  the rows that fix's comment references). No HTTP status code exists (a ReadTimeout never gets a
  response). No further code fix indicated: `_probe_row_class`'s dry_run_ok-based classification
  already correctly identifies these as "error" regardless of the (partly stale/pre-fix) verdict
  string; the fault itself is external sandbox-side network flakiness, self-resolved since (no
  transport-class probe errors in the log after 2026-08-28). Filed here as the record.
- 2026-09-05 14:41:20 ET -- F3 DONE: the only ENTER_REFUSED row in the fills_recency window is
  automation/state/futures/trader/decisions.jsonl line ~1350, ts_et 2026-09-01T09:30:04, reason
  TRENDLINE_BREAK_RETEST. Adjudicated: 2 seconds earlier (09:30:02) the SAME setup/entry/stop/tp1
  successfully ENTERed (order_ids FILLSIM-MES-BRK-c22ff950/-TP1/-STOP). The 09:30:04 tick refused
  because `FillSimBroker.place_bracket` returns [] whenever an active (pending_entry/open)
  position already exists for the instrument (fill_sim_broker.py:351-365, "no-stacking, mirrors
  Rule 6 / futures_heartbeat_core's own decide_skip=position_open_no_stack discipline") -- a
  duplicate-tick re-fire of the same signal was correctly refused rather than stacking a second
  bracket on top of the just-placed one. This is the gate working as designed, per the lane's own
  no-stacking rule -- not a defect. Check language match: `check_fills_recency` labels 1 refused
  row in 1/5 sessions "isolated ENTER_REFUSED, not yet a pattern" at YELLOW (RED needs >=2
  distinct sessions) -- accurate; "isolated" correctly describes a single non-repeating event.
  Verdict: no change made.
- 2026-09-05 14:41:20 ET -- F4 DONE: `backtest/.venv/Scripts/python.exe setup/scripts/
  futures_health.py` re-run post-fix: `[futures_health] verdict=RED at 2026-09-05 14:40:58 ET`.
  Sub-checks: can_enter GREEN; fills_recency YELLOW (F3, unchanged, correct); broker_transport
  YELLOW 3/7=43% (F2, unchanged, correct, no classifier defect); data_freshness GREEN;
  broker_exit_pairing GREEN; no_stray_exposure RED "8 stray-exposure anomaly row(s) in the last 2
  session(s)" (F1 -- EXPECTED: today 2026-09-05 is inside the new 5-calendar-day age-out window,
  which by design doesn't roll to GREEN until 2026-09-08 -- this is the fix behaving correctly,
  not a residual defect); task_liveness GREEN (all 7 futures tasks Ready, last_result=0).
  Top-level RED is carried entirely by no_stray_exposure's not-yet-elapsed age window --
  dated reason: no_stray_exposure ages RED->GREEN on 2026-09-08 per ANOMALY_MAX_AGE_DAYS=5,
  assuming no new anomaly rows land before then.

## HONEST STATE
F1-F4 all DONE. One real off-path defect found+fixed (no_stray_exposure's age-out window never
rolled forward without new anomaly rows -- fixed with a calendar-day cutoff, RED-proofed, 32/32
futures_health tests green). F2/F3 adjudicated clean (no code defect). Top-level verdict is still
RED post-fix because the age-out window (2026-09-08) hasn't elapsed yet -- expected, not new work.
