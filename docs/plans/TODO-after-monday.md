# TODO — After Monday Trading Session Proves Stable

> Items deferred until after Monday's first session on the new heartbeat infrastructure (state digest + hash early-exit + PID lockfile). Operating principle 1: don't change production logic during market hours; these changes wait for the post-market window or the next weekend.

---

## Pre-Monday (still safe to do this weekend)

- [x] Wire HG1 rationalization counters into heartbeat.md doctrine references
- [x] Wire #2 adversarial review + #10 two-stage promotion into weekly-review.md Section 7.1
- [ ] **Dashboard left column cleanup** (J's request 2026-05-09 PM):
  - Audit `dashboard/` left column for stale/cluttered widgets
  - Show useful: rule version, kill-switch state, today's P&L, last 3 actions, weekend-research progress, v15 ratification status
  - Hide: anything pre-Karpathy-method that's no longer load-bearing
  - Constraint: don't spend > 30 min on this; J wants signal not polish

---

## Post-Monday (after first stable session on new infra)

### Confidence-gated swaps

- [ ] **Swap Task Scheduler EOD target** to `run-eod-summary-parallel.ps1` after parallel EOD has run cleanly for 3 days OR after manual single-fire test passes.
  - Command: `Set-ScheduledTask -TaskName 'Gamma_EodSummary' -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\jackw\Desktop\42\setup\scripts\run-eod-summary-parallel.ps1"')`
  - Rollback: same command but with `run-eod-summary.ps1` (no `-parallel`)

### Doctrine enforcement (currently passive references)

- [ ] **Sequence the gates in heartbeat.md Entry Branch** per `doctrine/rules-as-gates.md`. Currently the doctrine is referenced at top but the entry branch doesn't EXPLICITLY enforce gate-by-gate; Claude follows the doctrine softly. Risk: needs careful integration with existing 10-bear / 11-bull filter scoring.
- [ ] **Iron Law in Position Branch** per `doctrine/iron-law-trades.md`. Add explicit `mcp__alpaca__get_order_by_id` confirmation step BEFORE every `journal/trades.csv` or `decisions.jsonl` exit-row write.

### Pressure-test methodology activation

- [ ] **Write first 2-3 R-NNNN pressure tests** based on actual loss-walks in `journal/losses/`. Currently `pressure_tests/` is template-only.
- [ ] **Wire premarket Step 1c** to run `pytest backtest/tests/pressure_tests/ratified/ --tb=line -q`. Failure = kill-switch the day. Cost: ~5 sec, $0 LLM.

### Misc

- [ ] **Cleanup orphan PowerShell windows** from old `run-random-search.ps1` and `run-next-steps.ps1` invocations. Either modify those scripts to NOT use `-NoExit`, or document the cleanup procedure.
- [ ] **Decide on superpowers plugin install.** I extracted patterns from obra/superpowers without installing the plugin. If we want the dev-side skills (TDD, debugging, git worktrees) too, run `claude /plugin install superpowers@obra`. Recommendation: skip — already 100+ skills loaded.

---

## Monday morning checklist (J)

When you sit down Monday morning to verify the autonomy stack worked over the weekend:

1. [ ] Check `docs/plans/multi-agent-gamma.md` Phase Tracking table — should show all green
2. [ ] Read `analysis/recommendations/v15.json` — does Sunday weekly-review have a verdict?
3. [ ] If verdict==RATIFIED: read `automation/state/params.json#rule_version` to see if it bumped to v15
4. [ ] Run `setup\scripts\test-multi-agent-gamma.ps1` — should pass 68/68
5. [ ] Check `dashboard` (localhost:3000) for any agent dialog that surfaced overnight
6. [ ] Skim `automation/state/logs/heartbeat-2026-05-09.log` for any TIMEOUT or POST_KILL_RECOVERY entries

If anything is RED in those checks, halt premarket via `New-Item automation\state\kill-switch -ItemType File` until you've reviewed.
