# Package: score-ladder-v2-shadow-retirement

**Packet row:** `score-ladder-v2-shadow-retirement` (classification `reduction`) in
`analysis/recommendations/checkpoint-2026-09-29-inventory.json`, verdict **RULE MET**
2026-09-05 per `setup/scripts/checkpoint_packet.py` (`_score_score_ladder_v2_retirement`).

**Prereg:** `analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json` — status
**KILLED**. Ledger: `analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl` — extras net
**-$13,760** (risky-1) / **-$13,435** (risky-3-era) over 28 sessions.

## What this retires

The SCORE-LADDER-RUNG (LANE 1) $0 forward shadow clock. Organs (identified by grepping
`automation/state/SCHEDULED-TASKS.md`, `setup/install-*.ps1`, `backtest/tools/*.py`,
`analysis/arm-ladder/` for "ladder"/"rung"/"score_ladder"):

| Organ | Path |
|---|---|
| Scheduled task | `Gamma_LadderRungShadow` (14:40 MT / 16:40 ET weekdays, State=Ready as of 2026-09-05) |
| Installer | `setup/install-ladder-rung-shadow.ps1` |
| Nightly worker (ledger writer) | `backtest/tools/score_ladder_rung_shadow_nightly.py` (`run_for_date`, writes `LEDGER_OUT`) |
| Mechanism it imports (C14, unchanged, still used elsewhere) | `backtest/tools/ladder_rung_replay_2026_08_07.py` |
| Ledger | `analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl` |
| Existing guard | `backtest/tests/test_score_ladder_rung_shadow_nightly.py` (kept, still passes post-patch: source still writes ledger append-mode only, still never references live-order surfaces) |
| Readers (left alone — read-only historical consumers, not organs to remove) | `setup/scripts/checkpoint_packet.py` (`_score_score_ladder_v2_retirement`), `setup/scripts/learning_ledger.py`, `setup/scripts/obsidian_vault_sync.py` |
| Params keys | **NONE.** `accounts.json` carries no `score_ladder_rung` key today (confirmed in the installer's own docstring) — no FROZEN_TRADING_PATH file is touched by this package. |
| Cockpit tiles reading the ledger | none found (`grep -rl "ladder-rung-shadow" dashboard/` = empty) |

## The patch

`change.patch` (from `git diff` against HEAD, reverted after capture — HEAD's working
tree is unchanged by authoring this package):

1. `backtest/tools/score_ladder_rung_shadow_nightly.py` — adds `RETIRED = True` and an
   early-return guard at the top of `run_for_date()` that no-ops (prints, returns 0)
   before touching `lrr.load_core_rows` or the ledger. Leaves the append-mode write path
   and the C14 import intact (so the existing guard test's source-text assertions still
   pass) — this is a kill-switch, not a deletion, so the revert is a one-line flip.
2. `setup/install-ladder-rung-shadow.ps1` — strips the `Register-ScheduledTask` block;
   the installer now only unregisters `Gamma_LadderRungShadow` and exits. Re-running the
   installer after a revert would no longer resurrect the task — the revert path is
   `git revert` (restores the Register block), then re-run the installer.

Scheduled-task removal itself is **not** a file diff — `apply.ps1` calls
`Unregister-ScheduledTask -TaskName Gamma_LadderRungShadow` directly, in addition to
applying the patch.

## Revert

```
git revert <sha-of-the-applying-commit>
setup/install-ladder-rung-shadow.ps1   # re-registers the task
```

## RED-proof (this session, 2026-09-05, quoted verbatim)

**Pre-patch** (`git checkout -- backtest/tools/score_ladder_rung_shadow_nightly.py
setup/install-ladder-rung-shadow.ps1`, i.e. HEAD, patch NOT applied):

```
[FAIL] test_retirement_flag_short_circuits_before_any_write -- RETIRED flag missing or False -- change.patch not applied, or reverted
[FAIL] test_scheduled_task_absent -- Gamma_LadderRungShadow is still registered -- expected only AFTER apply.ps1 runs Unregister-ScheduledTask on 2026-09-29 with GAMMA_FREEZE_OVERRIDE=1
exit=1
```

**Post-patch** (patch applied to the working tree, then reverted again before ending the
session — never left applied):

```
[ladder-rung-shadow] RETIRED 2026-09-29 -- no-op for 2099-01-01, ledger frozen. See analysis/recommendations/packages/score-ladder-v2-shadow-retirement/README.md
[PASS] test_retirement_flag_short_circuits_before_any_write
[FAIL] test_scheduled_task_absent -- Gamma_LadderRungShadow is still registered -- expected only AFTER apply.ps1 runs Unregister-ScheduledTask on 2026-09-29 with GAMMA_FREEZE_OVERRIDE=1
exit=1
```

`test_scheduled_task_absent` legitimately reads FAIL both times right now — it is a
**live system check**, not a mechanism check, and the task is (correctly, per config
freeze) still registered as of this session. It is expected to flip to PASS only once
`apply.ps1` runs for real on 2026-09-29. `guard_test.py`'s own `main()` exit code is 1
until both pass, matching "the guard test that fails before and passes after" per the
goal's DONE-WHEN — "after" here means after the real apply, not after authoring the
package.

Existing regression guard unaffected (run with the patch applied):
```
backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_score_ladder_rung_shadow_nightly.py -q
....                                                                     [100%]
4 passed in 1.00s
```

## Nothing applied

`change.patch` was captured via `git diff`, then the working-tree edits were reverted
with `git checkout -- backtest/tools/score_ladder_rung_shadow_nightly.py
setup/install-ladder-rung-shadow.ps1` before this README was finalized. `Gamma_LadderRungShadow`
remains registered (`State=Ready`) as of this session — verify with
`Get-ScheduledTask -TaskName Gamma_LadderRungShadow`.
