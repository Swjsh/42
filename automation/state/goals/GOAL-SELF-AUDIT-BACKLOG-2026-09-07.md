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

- [ ] Triage the 2026-09-03T17:31:34 batch (12 lines, `new-gaps-flagged.md` line ~1699).
      Notable candidates already scanned at open time (verify, don't assume): ROSTER-LIVENESS
      `p::m` lane reported DEAD/404 -- check if it self-healed or needs a real fix or a
      formal retirement; MCP_AUDIT_YELLOW (0 alpaca-mcp-server processes) -- check whether a
      lightweight auto-restart is warranted or whether this is expected on this box's
      current process model; gate-expiry RED auto-retry gap (filter-8-bear-sole /
      filter-10-bull-sole) -- cross-check against the ALREADY-CLOSED
      GOAL-GATE-EXPIRY-RECONCILE-2026-09-05 before treating this as new work, it likely
      duplicates that closed goal.
- [ ] Triage the 2026-09-04T17:31:34 batch (12 lines, line ~1713). Notable candidates:
      "multi-tick state-accumulation bug class not closed" (bounce_history fix 7ebbeeec
      patched ONE instance -- is there a second known accumulator with the same defect
      shape, or was this speculative?); "no staleness watchdog on output files" (verify
      against the fix already shipped 2026-09-05 self-audit batch#6, check_live_watch_liveness
      -- likely a PARTIAL duplicate, scope what's still missing beyond live-watch.json);
      "kill switch over-latches across all arms" (SPY-0DTE core: verify per-account isolation
      in `backtest/lib/risk_gate.py::check_order` call sites -- a first-pass check this fire's
      opening investigation already found the core function signature takes per-account
      `kill_switch_tripped`/`sod_equity_f`/`equity_f`, consistent with isolation; confirm the
      FLEET arms question is fully answered by the existing FLEET-KILL-SWITCH-NOT-LATCHED
      queue item (built on branch `safety-bundle-2026-09-29`, awaiting the checkpoint) rather
      than a new defect); "theta_budget model unvalidated / systematically overshooting" --
      this is a genuine open question, freeze-compatible to MEASURE (not to fix/ship), file a
      measurement-only script if none exists; "Alpaca greeks endpoint has never worked" (41/41
      empty) -- confirm current status, decide DOCUMENT-AS-MODEL-ONLY vs a real integration
      bug worth a queue item.
- [ ] Triage the 2026-09-05T17:31:21 batch (12 lines, line ~1727). Notable candidates:
      "status-preamble drift... pin with a CONTENT test" (extend
      `test_status_known_broken_preamble_2026_09_02.py` if it doesn't already assert content,
      not just structure); "github_audit.py --history has been broken since 09-03, six paper
      keys shipped while offline" -- HIGH, verify current state (was this fixed alongside the
      2026-09-03 SECRETS-ON-PUBLIC-REMOTE incident's guard work? check `github_audit.py` runs
      clean now); "central registry for what's scheduled at HH:MM" -- likely satisfied by
      `SCHEDULED-TASKS.md` already, verify it actually answers "what runs when" queryably or
      file a small follow-on if it's prose-only.
- [ ] After all three batches are disposed, run `goal_autopilot.py ensure` to confirm this
      goal closes cleanly and the next ladder entry (if any) picks up.

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
