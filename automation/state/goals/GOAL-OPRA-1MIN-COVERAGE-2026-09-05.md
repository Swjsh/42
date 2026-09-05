# GOAL: OPRA-1MIN-COVERAGE-2026-09-05

> Opened by Fable 2026-09-05 07:41 ET. The gate-net-cost walk (305 rows) and the right-tail capture ledger
> (144 scored arm-waves) run on 5-min OPRA bars; the measured 5-vs-1-min error bar is small on
> average (-$6.58 mean) but stage-dependent (premium_stop -$52 mean, trail +$47 mean) and only 262
> rows had 1-min bars cached. Every checkpoint number that depends on a walk inherits that bar.
> The hand-checks used 1-min bars from the same free fetcher. This goal fills the 1-min cache for
> exactly the contracts those two ledgers touch -- free source only -- and re-walks.

## DONE-WHEN
The 1-min OPRA cache covers every (contract, session) pair referenced by
analysis/gate-net-cost/walk-2026-09-05.json and analysis/right-tail/ledger.jsonl (quote coverage
before/after as pairs and pct); the fetch used the same free source the hand-checks used (name it;
$0; if it is paid or rate-limited beyond the weekend, STOP and report what was reachable); the walk
and the right-tail capture are re-run at 1-min (walker flag), producing `walk-2026-09-05-1min.json`
and `ledger-1min.jsonl` beside the originals (originals untouched); the gate-net-cost table and the
capture SUMMARY gain a "1-min" column with the deltas; the checkpoint scorers read the 1-min files
where present (RED-proofed test); the resolution-bias section is updated with the full-coverage
numbers. Cache growth in MB quoted; retention row added to markdown/infra/RETENTION.md.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: measurement, data and preregs only; no gate/position-limit changes.
- $0: free/local data sources only (the same fetcher the walker's hand-checks used); if a step needs a paid source, STOP and report.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] O1 (DONE 2026-09-05 08:10 ET, session a16e320c) -- Inventoried 98 distinct (contract, session)
  pairs (union of 92 from walk-2026-09-05.json's walk_ok rows + 38 from ledger.jsonl's scored rows,
  6 ledger-only). Coverage before: 79/98 (80.6%). Fetcher: `backtest/tools/exit_shape_parity_study.
  fetch_option_bars` (Alpaca `/v1beta1/options/bars`, already-wired live-arm key, $0) wrapped by
  `backtest/tools/_option_bars_1min_cache.fetch_1min_cached` (cache-first, 0.12s pacing). Limits:
  standard Alpaca data-plane rate limit, no paid tier used.
- [x] O2 (DONE 2026-09-05 08:10 ET, session a16e320c) -- Fetched the 19 missing pairs sequentially
  (log: automation/state/goals/_opra_1min_fetch_log_2026_09_05.jsonl). 19/19 ok, 0 failures.
  Coverage after: 98/98 (100%). Cache growth: 19.408 MB -> 19.726 MB (+0.319 MB).
- [x] O3 (DONE 2026-09-05 08:10 ET, session a16e320c) -- Added `--resolution {5min,1min}` to
  gate_net_cost_walk.py (default unchanged) and a shared read-only 1-min loader
  (`backtest/tools/_option_bars_1min_cache.load_1min_cache_readonly`, reused by right_tail_waves.py
  per OP-22). Re-walked -> analysis/gate-net-cost/walk-2026-09-05-1min.json (305/305 walk_ok, 0
  fallback-to-5min, exact parity with the 5-min error counts). Added the same `resolution` param to
  `right_tail_waves.find_waves`/`_price_wave` and `--resolution`/`--out-suffix`/`--ledger-path` to
  right_tail_capture.py; re-ran all 25 days -> analysis/right-tail/ledger-1min.jsonl + 25
  CAPTURE-<date>-1min.json files (originals untouched). Deltas: walk mean $8.61/row over 305 common
  walk_ok rows (per-stage: premium_stop +$42.61, trail -$44.17, structure_stop +$22.18, time_stop
  -$14.07, ribbon_flip +$14.78 -- signs here are 1min-5min, opposite convention from the
  resolution-bias section's 5min-1min; per-gate deltas in
  automation/state/goals/_opra_1min_deltas_2026_09_05.json); right-tail peak_multiple_on_tape mean
  delta +0.0057 over 140 common scored rows, 0/140 `taken` flips, capture_rate per-arm deltas
  safe-2 -0.0417 / bold-2 +0.0250 / safe-3 -0.0125 / risky-1 -0.0125 (full numbers in
  automation/state/goals/_opra_1min_righttail_deltas_2026_09_05.json). Updated
  GATE-NET-COST-2026-09-05.md/.json (new "Net $ (1-min)" / "Δ (1min-5min)" columns on both
  gate_arm_rows and gate_rows_deduped_to_waves; NO checkpoint verdict flipped -- verified every
  n>=10 gate kept its net-$ sign under 1-min, SKIP_STRUCTURE_VETO flipped sign but stays
  UNDERPOWERED both ways at n=7); re-ran gate_net_cost_resolution_bias.py so the Error bar section
  now covers 305/305 rows (was 262) with the full-coverage numbers (overall mean $-5.71,
  5min-1min convention); appended a "1-min re-walk" section to analysis/right-tail/SUMMARY.md.
  checkpoint_packet.py's `_net_of_losers_for_mechanism` now prefers each gate/arm's
  `net_dollars_1min` (discloses the un-preferred 5min sum too) and `_score_capture_gap_mechanism`/
  `_score_not_flat_second_wave` prefer the `-1min` ledger sibling when present (both disclosed via
  new `ledger_resolution`/`net_of_losers_dollars_full_window_5min` fields) -- RED-proofed in
  `backtest/tests/test_checkpoint_packet_prefers_1min_2026_09_05.py` (5/5 pass; confirmed the RED
  by temporarily removing ledger-1min.jsonl -- 3/5 flipped to fail, restored). Regenerated
  CHECKPOINT-2026-09-29.md/CHECKPOINT-2026-10-30.md and checkpoint-packet-2026-09-05.json -- no
  verdict changed, only disclosed numbers gained 1-min fields. Side-fix: a pre-existing (not
  caused by this goal) `test_dst_frame_no_new_unguarded_opra_join_consumers` failure on
  `setup/scripts/gate_net_cost_resolution_bias.py` (committed in an earlier session, never
  allowlisted) was classified SAFE(fp) and added to the allowlist so the graduated-guards suite
  could run at all this session.
- [x] O4 (DONE 2026-09-05 08:10 ET, session a16e320c) -- Added a `backtest/data/highres/` row to
  markdown/infra/RETENTION.md (1,215 files / 23 MB; already `.gitignore`-covered, no sweep needed).
  Verified + RED-proofed fail-open: `_price_wave(..., resolution="1min")` on a pair with no 1-min
  cache returns `{"computed": False, "resolution_1min_fallback": True, ...}`, never raises --
  `backtest/tests/test_right_tail_1min_fail_open_2026_09_05.py` (3/3 pass).

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 07:49 ET — opened by goal_autopilot
- 2026-09-05 08:10 ET -- O1-O4 all DONE, session a16e320c. Safety gate 59/59 green;
  `pytest -k "gate_net or right_tail or checkpoint or resolution"` 110/110 green (was 107 before
  O4's 3 new tests). No commit made (per hard rules) -- files listed above are all on disk,
  uncommitted.
- 2026-09-05 08:13 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
All four objectives complete and verified this session (commands quoted above). Nothing blocked
on J. Files are uncommitted (no-commit hard rule) -- next session or J's own commit picks these up.
AUTOPILOT CLOSE 2026-09-05 08:13 ET: queue fully terminal (no bare '- [ ] ' item left)
