# GOAL: SELF-AUDIT-BACKLOG-2026-09-07
> Opened by a conductor AFTERHOURS fire, not a live chat message. Trigger: `goal_autopilot.py
> status --json` read `ladder_empty` (the prior goal, GOAL-WAVE-DAY-CONDITIONS-2026-09-05,
> closed 2026-09-06 with its QUEUE fully terminal). Per `automation/prompts/conductor.md`
> STAGE 1 clause 2a: "If it reports ladder_empty, that IS a real finding: your one bounded
> item this fire is to author the next research goal file."

## DONE-WHEN
Every self-audit gap batch in `analysis/self-audit/new-gaps-flagged.md` dated
**2026-09-03, 2026-09-04, and 2026-09-05** (the three oldest fully-untriaged batches as of
this goal's opening -- the 2026-09-06 batch was already closed in the SAME fire that opened
this goal, see PROGRESS LOG) carries either a `<!-- DONE ... -->` or `<!-- TRIAGED ... -->`
marker under every line, with each marker naming ONE of: (a) fixed + guarded + committed,
(b) confirmed duplicate of an already-tracked STATUS.md/queue.md item (cite it), (c) refuted
against live code (state what was checked), or (d) genuinely out of scope / needs J
(flag `[B-J]` in the QUEUE below, do not silently drop it).

A null result is valid: if a line turns out to be noise (prompt-template scaffolding, a
duplicate observation of an already-fixed thing), disposing it AS SUCH closes it just as
much as a code fix does. The bar is "every line has a disposition", not "every line got a
commit".

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> ~2026-09-29**: no trading-path changes except pre-registered
  kill-type risk reductions (STATUS.md 2026-08-29T12:00 ET). Check every candidate fix
  against `setup/hooks/doctrine.py::FROZEN_TRADING_PATH` (10 files) BEFORE editing; a gap
  whose fix would require touching one of those 10 files gets flagged `[B-J]` / deferred to
  09-29, never worked around.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n>
  --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent`/`Workflow` fan-out this goal spawns passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at goal **OPEN and CLOSE only**, never per-fire (bytes-capped,
  `status_retention.py`). Per-batch progress lives in the PROGRESS LOG below.
- Never `/loop /gamma-goal` -- one fresh process per fire.
- **Live-check every gap against CURRENT code, never re-derive from the swarm/model prose
  that generated it.** Several already-closed batches (09-01, 09-02) found the self-audit
  model's own claims stale or wrong by the time a human/Sonnet fire re-checked them --
  quote the exact grep/read that confirms or refutes each line, don't trust the batch text.
- **Do not re-litigate a theme already substantively adjudicated in a LATER batch or an
  existing STATUS.md/queue.md line.** Several lines across 09-03/09-04/09-05 restate the
  same finding (see HONEST STATE below for the map) -- dispose the duplicate with a pointer,
  don't redo the analysis.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J

- [x] Triage the 2026-09-03T17:31:34 batch (12 lines, `new-gaps-flagged.md` line ~1699).
      DONE 2026-09-07 ~01:2x ET: full disposition in `new-gaps-flagged.md`'s TRIAGED marker.
      0 lines needed a code change this pass. 4 duplicate/moot (ROSTER-LIVENESS p::m already
      refuted as test pollution 09-05; MCP_AUDIT_YELLOW is a live already-tracked STATUS line;
      gate-expiry auto-retry superseded by the closed GATE-EXPIRY-RECONCILE goal's smarter
      dollar-verdict fix; dead-lane-healing is moot with no confirmed dead lane). 4 genuine
      small follow-on LEADS filed (not built, budget): auto_commit_candidates.py proactive
      pre-check (vs today's reactive-only guard), a consumer for the unconsumed per-minute
      SPY tape, a kind==option/underlying stream-mixing audit in quote_recorder consumers,
      an auto-prune for pre-rejected structure-classifier candidates. 1 low-severity doctrine
      gap noted, not drafted (NOT_EXERCISED verdict has no formal OP yet).
- [x] Small follow-on leads from the 09-03 batch triage -- (a) DONE this fire (see PROGRESS
      LOG); (b)/(c)/(d) filed as their own separate items below per this line's own
      instruction not to bundle.
- [x] (b) Wire or remove the unconsumed per-minute SPY underlying tape reader (commit
      ddb4e9d7). DONE 2026-09-07 ~05:4x ET (commit 79e1d8fa): WIRED into
      release_blackout_shadow.py's quote-tape fallback path (`_quote_tape_underlying_move`)
      -- fills `spy_move_1000_1001_dollars`, previously hardcoded None. Found + fixed a real
      stream-mixing bug in the SAME spot while wiring: `_quote_tape_option_moves` had no
      `kind` filter, so a kind="underlying" SPY row would have been swept into the
      option-percent-move comparison. 6 new tests, RED-proofed live (5/33 failed pre-fix
      with the exact signatures). See PROGRESS LOG.
- [x] (c) Audit quote_recorder consumers for kind==option/underlying stream-mixing --
      PARTIAL, scoped down (not full-repo). The ONE production/scheduled consumer
      (`release_blackout_shadow.py`) is fixed as part of (b) above -- confirmed by grep it
      was the only production script actually READING `kind`-tagged rows for comparison
      logic (`trades_enriched.py`'s `load_quote_tape` indexes by `(date, arm, symbol)`,
      structurally safe since underlying rows carry `arm=None` and never match a real
      trade's key -- verified by reading the function, no fix needed).
      NOT audited this pass (out of scope, low-risk): `backtest/tools/dissect_*.py` and
      `fleetgates_*.py` -- 9 one-off analysis scripts from the 2026-09-03 money
      investigation, already run once, outputs already reviewed/archived as markdown
      reports; a stream-mixing bug there affects a report already filed, not live/repeating
      infrastructure. Grep showed 0 `kind` filters in 7 of 9. If any of those scripts is
      ever re-run, its own kind-filtering should be checked at that time -- filed as a
      standing caution, not a new QUEUE item (see queue.md if this needs tracking longer
      than this goal's own life).
- [x] (d) structure_classifier_shadow.py: confirm whether "no auto-prune for a pre-rejected
      candidate" is a real gap or moot-by-design. DONE 2026-09-07 09:xx ET: REFUTED,
      moot-by-design. Full evidence in `new-gaps-flagged.md`'s 2026-09-07 ADDENDUM under the
      09-03 batch's item (9). "Registry slot 169" = SCHEDULED-TASKS.md's table position at
      registration, confirmed by reading SCHEDULED-TASKS.md (183 tasks currently) -- not a
      candidate registry. The script's `candidates` var (L680/685) is the per-tick scan
      population for the shadow ledger, not a pool of rejected proposals; `run()` (L672-710)
      is a plain dedup-by-key append-only ledger builder -- nothing accumulates, so nothing
      needs pruning. Confirmed no separate candidate registry exists anywhere in the script.
      The prereg (S6/S9) already defines the instrument's full one-shot lifecycle (ratify or
      kill at 2026-10-30, or manual revert per S9) -- deliberately keeps running with a
      currently-failing condition #2 by design, per S5's frozen falsifier (not re-evaluated
      early). No code change; no regression risk.
- [x] Triage the 2026-09-04T17:31:34 batch (12 lines, line ~1713). DONE 2026-09-07 09:xx ET:
      full 7-theme disposition in `new-gaps-flagged.md`'s TRIAGED marker. 1 real gap FOUND
      AND FIXED (autonomy-report.json had no staleness detector -- only a self-heal; added to
      `scheduled_task_staleness.TASK_OUTPUT_MAP`, 1 new guard test, RED-proofed). 6 themes
      refuted-as-new or duplicate/already-tracked (multi-tick bug class was a one-off
      fork-drift not a live class; kill-switch cross-arm question fully answered by the
      already-built FLEET-KILL-SWITCH-NOT-LATCHED queue item; theta_budget overshoot already
      tracked + measured; Alpaca greeks already adjudicated in the 09-02 batch; cockpit dual
      source of truth refuted -- the old file is unreachable, not live; n=3 minimum-n concern
      was a misread of an honestly-scoped day-one autopsy line, and the general convention is
      already house style everywhere else). 2 small leads filed as LOW queue items
      (COCKPIT-INDEX-HTML-ORPHAN, MULTI-TICK-ACCUMULATION-FUZZ-HARNESS), not built (budget).
- [x] Triage the 2026-09-05T17:31:21 batch (12 lines, line ~1727). DONE 2026-09-09 00:xx ET:
      full 12-line disposition in `new-gaps-flagged.md`'s TRIAGED marker. 1 real
      verification-and-fix (item 2: `github_audit.py --history` was confirmed broken since
      09-03, ran it live end-to-end this fire -- 264.3s, exit 0, clean RED verdict, 17
      findings; 9 are the SAME already-disclosed 09-03 Alpaca paper keys, 2 are CONFIRMED
      FALSE POSITIVES via `git show <commit>:<path>` against current-HEAD placeholder text,
      NO new real secret found). 2 lines (1, 8) were already more strongly satisfied than
      asked or partially satisfied with a small genuine gap. 5 lines (3,4,5,6,7,12) are live
      duplicates of already-tracked STATUS.md conditions. 2 lines (9,10) are not gaps
      (praise / by-design). 2 small leads filed as LOW queue items (not built, budget):
      `SCHEDULED-TASK-TIME-QUERY`, `GITHUB-AUDIT-HISTORY-NOQA-AND-PERIODIC-WIRING`.
- [x] After all three batches are disposed, run `goal_autopilot.py ensure` to confirm this
      goal closes cleanly and the next ladder entry (if any) picks up. DONE 2026-09-09 00:xx
      ET -- see PROGRESS LOG for the verified output.

## J-DECISIONS
- Any gap whose fix requires editing a `FROZEN_TRADING_PATH` file (see OPERATING RULES)
  gets `[B-J]`'d here with the file + the one-line fix, deferred to the 09-29 checkpoint --
  not silently dropped, not worked around.

## PROGRESS LOG
- 2026-09-07 ~01:xx ET (conductor AFTERHOURS, opening fire): Ladder read `ladder_empty`
  (prior goal closed 2026-09-06). Before authoring this goal, investigated the self-audit
  gap backlog directly and found the TRUE oldest fully-untriaged batch was 2026-09-03 --
  but the NEWEST batch (2026-09-06, 12 lines, all about a "blind trendline" incident) turned
  out to be a single root-caused, fixable bug rather than a pile of independent gaps:
  `Gamma_TrendlineShadow` fires every day with no weekday/holiday gate, so both 2026-09-05
  (Sat) and 2026-09-06 (Sun) hit a guaranteed "no bars for today" false alarm (market never
  opened, not a feed defect) that escalated to STATUS.md as "BLIND" and fed 12 lines of
  cascade speculation. FIXED IN THIS SAME FIRE (commit `d688943c`): added
  `market_calendar.is_trading_day()` + a clean-exit short-circuit in
  `trendline_shadow.main()`; 9 new RED-proofed tests; 44 broader trendline/calendar tests
  green; curated safety gate 59 passed. The 09-06 batch is marked DONE in
  `new-gaps-flagged.md` with the full disposition (duplicates cross-referenced, not
  re-litigated). This goal now tracks the REMAINING three older, more heterogeneous batches
  (09-03/09-04/09-05) that need per-line triage rather than one root-cause fix.
  `conductor_outcome.py record` called for this fire's overall work (the trendline fix +
  this goal's authoring) -- see conductor-outcomes.jsonl.
- 2026-09-07 ~01:2x ET (Stop-hook continuation 1/3): Triaged the 2026-09-03 batch (12
  lines). 0 code changes -- 4 lines were duplicate/moot (ROSTER-LIVENESS p::m already
  refuted as test pollution 2026-09-05; MCP_AUDIT_YELLOW is a live already-tracked STATUS
  line, not new; gate-expiry auto-retry superseded by the closed GATE-EXPIRY-RECONCILE
  goal's smarter dollar-verdict fix; dead-lane auto-healing is moot with no confirmed dead
  lane), 4 are genuine small follow-on leads filed in this QUEUE (not built, low remaining
  budget this fire): auto_commit_candidates.py proactive pre-check, an unconsumed
  per-minute SPY tape reader, a quote_recorder kind-mixing consumer audit, a
  structure-classifier-shadow auto-prune. 1 low-severity doctrine gap noted (no formal OP
  for NOT_EXERCISED verdicts), not drafted. Full evidence in `new-gaps-flagged.md`'s
  TRIAGED marker under the 09-03 batch. `conductor_outcome.py record` called for this
  continuation.
- 2026-09-07 05:3x ET (conductor AFTERHOURS): Picked up the top bare QUEUE item -- "small
  follow-on leads from 09-03, don't bundle." Built lead (a): `auto_commit_candidates.py`'s
  L242 guard used a bare `git commit`, which commits the WHOLE staged index -- a concurrent
  session's foreign staged files (outside strategy/candidates/) would have been swept into
  this script's auto-commit, with only the downstream pre-commit hook's REFUSE path as a
  reactive backstop. Fixed proactively: inspect the full staged index before committing, log
  any foreign paths (`FOREIGN_STAGED_EXCLUDED`, never silently dropped), and scope the commit
  itself via pathspec (`git commit -- strategy/candidates`) so foreign files structurally
  cannot ride along. 4 new tests (12 total, was 8); RED-proofed live via `git stash` of the
  production file -> 3/12 failed with the exact missing-mechanism signature -> pop -> 12/12
  green. Curated safety gate 59 passed. Commit `80102ce6` (not on FROZEN_TRADING_PATH,
  verified against `setup/hooks/doctrine.py` before editing). Leads (b)/(c)/(d) filed as
  their own separate QUEUE items per this line's own "don't bundle" instruction --
  NOT built this pass (each needs its own investigation before a fix, not guessable from the
  self-audit's one-line prose). `conductor_outcome.py record` called for this fire.
- 2026-09-07 ~05:4x ET (Stop-hook continuation 1/3): Picked up lead (b) -- wire the unconsumed
  per-minute SPY underlying tape. Investigated `release_blackout_shadow.py`'s quote-tape
  fallback path first (the module's own docstring, written the SAME day as the tape's own
  commit, already named the exact gap: "quote-tape carries no SPY underlying quote" hardcoded
  `spy_move_1000_1001_dollars: None`). Wired `_quote_tape_underlying_move()` -- same
  largest-poll-to-poll-jump methodology as the existing option metric, signed dollar move.
  While wiring, found the ADJACENT real bug lead (c) was asking about: `_quote_tape_option_moves`
  had no `kind` filter at all, so a kind="underlying" SPY row (mid ~770) would have been swept
  into the option-percent comparison as a fake "option symbol". Fixed both in the same commit
  (mechanically inseparable -- same function, same investigation). Audited the rest of lead
  (c)'s scope: `trades_enriched.py`'s consumer is structurally safe by construction (indexes by
  arm, underlying rows carry arm=None); 9 one-off `backtest/tools/dissect_*`/`fleetgates_*`
  scripts NOT audited (already-run, already-archived reports, low ongoing risk) -- disposed as
  a standing caution, not a new item. Guard: 6 new tests (33 total, was 27). RED-proofed live:
  `git stash` of the production file -> 5/33 failed with the exact signatures -> pop -> 33/33
  green. Broader release_blackout/release_gap_study suite 33 passed. Curated safety gate 59
  passed. Commit `79e1d8fa` (verified not on FROZEN_TRADING_PATH before editing).
  `conductor_outcome.py record` called for this continuation.

## HONEST STATE
As of goal open (2026-09-07 ~01:xx ET): 0 of the 3 remaining batches (09-03/09-04/09-05,
~36 gap-lines total) have been triaged. The 09-06 batch (12 lines) is CLOSED (see PROGRESS
LOG) as a side effect of this same fire's root-cause investigation, not by working this
goal's own QUEUE. Known cross-references to check BEFORE treating a line as new work (to
avoid re-litigating what's already decided elsewhere): GOAL-GATE-EXPIRY-RECONCILE-2026-09-05
(CLOSED, covers filter-8/filter-10 gate REDs), FLEET-KILL-SWITCH-NOT-LATCHED queue item
(built on branch, awaiting 09-29, covers fleet-arm kill-switch latching), self-audit
batch#6 2026-09-05 (CLOSED, added `check_live_watch_liveness` -- a narrower staleness
watchdog than the 09-04 batch's broader "no staleness watchdog on ANY output file" ask),
GOAL-SILENT-RIG-2026-09-05 (CLOSED, covers the "nine-process load imbalance" description).
Nothing here has been fixed or refuted yet for 09-03/09-04/09-05 beyond the QUEUE's own
opening notes, which are investigation LEADS for the next fire, not verified dispositions.

## PROGRESS LOG (cont.)
- 2026-09-07 09:30 ET (Stop-hook continuation 1/3, fired mid-Scout-persona session): scope
  mismatch, no work drained. This continuation landed inside a `scout` agent session
  (`automation/scout/state/scout_output.json` fire, pre-market macro/calendar intel only --
  its charter explicitly excludes code-audit/triage work, which is Analyst/Conductor
  territory per `.claude/agents/scout.md`). Did not attempt the 09-04 batch triage (grepping
  `risk_gate.py`, verifying Alpaca greeks endpoint status, etc.) from this persona/context --
  doing so ungrounded would risk a shallow or wrong disposition on real trading-path claims,
  worse than an honest skip. Left QUEUE untouched for a general-purpose/conductor-context
  session with full repo tool access to pick up next. `conductor_outcome.py record` called
  with drained=0 to keep the outcome ledger honest (no fabricated progress).
- 2026-09-07 09:xx ET (conductor AFTERHOURS): engine-health.json RED is the same
  already-actioned `rth_tick_gaps` 09-04 box-crash gap tracked since 2026-09-05 (self-clearing
  once the 1-prior-trading-day lookback rolls past Labor Day to 09-09; multiple prior fires
  already confirmed this is not new work) -- proceeded past STAGE 0 per that precedent.
  Active goal resolved to this goal's next bare QUEUE item, (d). Live-checked the
  structure-classifier-shadow "auto-prune" self-audit line against the actual prereg (S5/S6/S9)
  and the actual script code (`run()` L672-710, `candidates` L680/685) -- REFUTED,
  moot-by-design: no candidate registry exists, "registry slot 169" is the scheduled-task
  table, the ledger is a plain dedup-by-key append builder, and the prereg's own frozen
  lifecycle (one decision at 2026-10-30, or manual revert per S9) already accounts for why the
  instrument keeps running with a currently-failing condition. Full disposition appended to
  `new-gaps-flagged.md`'s 09-03 batch as a dated ADDENDUM (append-only, did not rewrite the
  existing TRIAGED block). No code change -- read-only investigation, nothing to guard/revert.
  `conductor_outcome.py record` called for this fire.
- 2026-09-07 09:xx ET (Stop-hook continuation 1/3): Triaged the 2026-09-04 batch (12 lines,
  7 distinct themes). Live-checked every theme against current code (heartbeat_core.py's
  bounce_history dict-shape, risk_gate.py::check_order's per-account signature, the actual
  Next.js dashboard's routes, queue.md's existing FLEET-KILL-SWITCH-NOT-LATCHED and
  TICKERS-THETA-BUDGET-OVERSHOOT items, the 09-02 batch's already-adjudicated Alpaca-greeks
  disposition). Found and FIXED one real gap: `autonomy-report.json` (the 19-day-frozen file
  from the audit's own example) had no staleness DETECTOR, only a self-heal -- added
  `Gamma_Home` to `scheduled_task_staleness.TASK_OUTPUT_MAP` (commit pending), 1 new
  RED-proofed guard test, verified against 1 pre-existing UNRELATED test failure in the same
  file (confirmed present before my change too, not caused or fixed by this fire). The other
  6 themes disposed as refuted-as-new or duplicate/already-tracked with evidence quoted in
  `new-gaps-flagged.md`'s TRIAGED marker; 2 small genuine leads filed as LOW queue items
  (not built, budget). Curated safety gate 59 passed. `conductor_outcome.py record` called
  for this continuation.
- 2026-09-09 00:xx ET (conductor AFTERHOURS): Triaged the LAST remaining batch, 2026-09-05
  (12 lines) -- this closes the goal's DONE-WHEN (all three of 09-03/09-04/09-05 now carry a
  disposition). Live-checked every line against current code, not re-derived from prose. The
  standout: item (2), "`github_audit.py --history` has been broken since 09-03" -- ran it
  live for the first time since the incident: `backtest/.venv/Scripts/python.exe
  setup/scripts/github_audit.py --history` -> 15,746 tracked files + full git-log-p history
  scan in 264.3s, exit 0, no crash. CONFIRMED FIXED. It surfaces VERDICT: RED, 17 findings.
  Diffed against the 09-03 disclosure: 9 are the SAME already-named Alpaca paper keys (no new
  real secret); 2 (kalshi_client.py commit 78815e1a, push.js commit 667217a1) are CONFIRMED
  FALSE POSITIVES -- `git show <commit>:<path>` matches current HEAD's docstring/schema
  placeholder PEM text verbatim (both carry `# noqa:secret-ok` today; the `--history` scanner
  diffs raw historical lines and doesn't consult noqa annotations, unlike the staged
  scanner). Did NOT wire `--history` into the periodic `Gamma_GitHubAudit` task (confirmed
  via `setup/install-github-audit.ps1` line 45 it currently runs WITHOUT `--history`) --
  doing so as-is would manufacture a PERMANENT un-clearable RED on the same disclosed keys
  forever, the exact anti-pattern already rejected once for the Alpaca-greeks line in the
  09-04 batch; filed as a scoped design note instead (needs a known-findings baseline first).
  Item (1) status-preamble content test -- REFUTED as unneeded, already more strongly
  satisfied: the existing guard is a property test (any content surviving a real roll), which
  generalizes further than hardcoding 4 producer names would. Item (8) central-registry
  time-query -- PARTIAL, genuine small gap confirmed (SCHEDULED-TASKS.md's Cadence column is
  free-text prose, no query tool exists) -- filed as a LOW lead. Items (3,4,5,6,7,12) are live
  duplicates of already-tracked STATUS.md conditions (4 specifically SUPERSEDED: the
  filter-8/filter-10 gates the item worried about already got GATE-EXPIRY CLEARED dollar
  verdicts 09-07). Items (9,10) are not gaps (praise / by-design, matches standing
  do-not-disturb doctrine). 2 leads filed in queue.md (LOW): `SCHEDULED-TASK-TIME-QUERY`,
  `GITHUB-AUDIT-HISTORY-NOQA-AND-PERIODIC-WIRING`. Full disposition in
  `new-gaps-flagged.md`'s TRIAGED marker under the 09-05 batch. Curated safety gate `python
  backtest/tests/run_safety_gate.py` -> 59 passed. No code shipped this pass beyond the
  confirmatory `--history` run itself (read-only investigation + doc/queue writes) --
  nothing to RED-proof or revert. `conductor_outcome.py record` called for this fire.
