# HANDOFF — engine review, 2026-08-14 close → 2026-08-15 midday

Paste the block at the bottom into a fresh session. Everything above it is the detail that block points at.

---

## What this review was

After Friday's −$1,569 morning (box slept 04:27–09:46 ET → double entry + a blind first tick), a
full post-close review ran through Saturday midday. ~40 commits, all after 15:55 ET. Nothing
touched live trading. Full log, newest first: `automation/overnight/STATUS.md`.

## THE HEADLINE FINDING — exits

Measured MFE capture from **live** telemetry (`best_premium` in `exit_pass`, joined to fills):

| window | n | median give-back | avg win | avg loss | WR | payoff |
|---|---|---|---|---|---|---|
| PRE 07-20..08-09 | 85 | −32.0% | $300 | −$115 | 29% | 2.61 |
| POST 08-10..08-14 | 77 | **−6.7%** | **$144** | −$89 | 31% | **1.62** |

On 08-10 three exit tightenings shipped in one day onto `ribbon_ride` — pre-TP1 ratchet
(`1a9b1409`), J's ladder (`af6cf286`), trail arm +40→+75 (`658ecc79`).

**The ratchet works.** Give-back collapsed −32% → −7%. It is the reason trades stopped
round-tripping to red. **But it truncates both tails**, and at ~30% WR breakeven payoff is ~2.3.
The book went 2.61 → 1.62.

**Conclusion: the ladder STAYS. The next lever is entry selectivity, not exit width.** Exits have
been re-tuned three times in five days and the payoff ratio degraded every time. A 30%-WR book
lives on its right tail; you cannot tighten into it. Raise WR first.

## FOUR CORRECTIONS — do not inherit the retracted versions

1. **"Live fills confirm the exit hypothesis"** — WRONG, confounded. `1a2692c4` armed risky-3 on
   the premium-stop lane 08-09; risky-1 traded part of the window with a selectivity gate
   DELETED until `97734a7b` restored it 08-12; `3ac1d7b2` killed risky-3's ATM tier 08-06. Those
   two arms drive the aggregate. **safe-3 went the OTHER way** (avg_win $188 → $197).
2. **"The engine does not record why a position exited"** — **WRONG.** It does. `exit_pass` rows
   carry `actions[]`, each with `kind` + `reason`. I read `reason` off the *result* dict (no such
   key), saw `None`, and declared a missing instrument. **545 attributed exit actions are on
   disk.** Do not rebuild this.
3. **"runner_target 3 fires → 0 implicates the ladder"** — WRONG. `runner_target_pct = 99.0` is
   deliberately "tgt-none" from the SS-B cell shipped **2026-07-09**, a month before the ladder.
4. **"The ladder clips winners, remove it"** — WRONG, reversed by the capture data above.

All four came from publishing a headline before exhausting data already on disk.

## Real exit attribution (the correct query)

| reason | PRE | POST |
|---|---|---|
| `premium_stop` | 62% | 19% |
| `structure_stop` | 12% | **32%** |
| `ribbon_flip_back` | 4% | **22%** ⚠ C28 says this is a LAGGING exit |
| `runner_stop` | 11% | 13% |

`ribbon_flip_back` at 22% of closes is an open lead nobody has explained.

## PROVENANCE DEFECT (found, guarded, needs a decision)

`analysis/recommendations/engine-fullhist-replay-2026-07-23.json` published **+$5,064.75 / 190
trades**; it now reads **+$4,808.75 / 191**. Exactly one row added — `2025-02-07 10:45
SPY250207C00608000`, a −$256 loser — by `df0348d9`, a regime-threshold commit with no business
touching a replay artifact.

- Three tests were the only thing that noticed. They were nearly dismissed as stale pins.
- The ENTRY-LOCATION-GATE study read the mutated file and published 191 as its population.
- **J decides:** restate the study headline and re-derive downstream pins from 191, or restore
  the 190-row file.
- **Guard now exists:** `setup/scripts/dataset_integrity.py` + `assert_intact()` wired into the
  study runners. RED-proofed against the real 190-row blob pulled from git.

## Live bug found mid-trace, NOT yet fixed

`setup/scripts/unattended_health.py:173` `_scheduled_days_mask` does `int(dow)` where `dow` can
be a **list** (`days_of_week: ["Monday", ...]`) → `TypeError`. Reproduce:

```
backtest/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'setup/scripts'); import unattended_health as uh; uh._scheduled_days_mask([{'type':'MSFT_TaskWeeklyTrigger','days_of_week':['Monday'],'enabled':True,'start_boundary':'2026-08-07T06:35:00-06:00','repetition_interval':None,'repetition_duration':None}])"
```

This is the root of the 5 `test_unattended_health` failures — **not** the helper-contract drift I
hypothesised earlier. Fix the crash, then re-run those 5.

## Suite state

Full suite measured for the first time: **6,374 passed / 59 failed**, then ~30 repaired. Must be
run in **30-file batches** — the reaper kills any python process over 5 minutes, which silently
truncated every earlier full-suite attempt.

Remaining failures cluster into families (detail + fix shapes in STATUS.md):
- **A — replay/anchor pins that drift with live config or an append-only ledger.** Mostly fixed.
  `trail_width_exit_ab` is xfail: its population is OPRA-cache-dependent and grew retroactively
  113 → 284, so it is **not date-reconstructible**. Correct fix = prereg stores (symbol,
  entry_ts_utc) IDs. Do not retry the date bound; it was tried.
- **B — live-state coupling in fixtures** (`unattended_health` ×5, `trade_today_watcher` ×3,
  `state_contracts`). Sandbox each, as done for the keystone/nbbo repairs.
- **C — stale shape pins** (~10). **D — network-dependent** (2, confirm network-only first).

## Traps already paid for

1. A claim and its retraction look identical to grep — **use AST**, never absence checks. Hit
   three times this week, once *inside* the instrument built to prevent it.
2. `schtasks /fo csv` truncates — use `Get-ScheduledTask`.
3. exit 0 / GREEN / "alive" mean "nothing raised", not "the work happened".
4. STATUS.md rotates (`status_retention.py`, 45KB cap) — content missing vs HEAD is probably in
   `STATUS-archive-*.md`. Check before "restoring".
5. Fixes must land on ALL call sites — three half-landed fixes this week, mine.
6. Never `git stash` here; never `git add -A`; use `setup/scripts/commit_scoped.py`.
7. Time = `setup/scripts/et_clock.py` only. Never bash `TZ`.
8. No `powershell -Command` from Bash — console popups.

## Standing state

- `min_contracts_equity_scaled` = **false**. Re-arm needs a VALIDATED entry-quality gate. Two
  studies (location, range) returned null/NOT-RUN — the condition is not met.
- Conviction is **shadow-only, disarmed**. C4/C5 now actually score for the first time
  (transposed key + hardcoded `None` fixed 08-14); it previously blocked 102/102 rows.
- Incident roster: 10/10 fixes guarded, re-verified daily 07:30 via `Gamma_IncidentFixStatus`,
  silent unless one regresses.

---

# PASTE THIS INTO THE NEW SESSION

```
Read automation/overnight/STATUS.md (newest entries first) and
markdown/planning/HANDOFF-2026-08-15-ENGINE-REVIEW.md before doing anything. They carry a full
engine review from Friday's close through Saturday midday, including FOUR corrections of my own
earlier wrong conclusions — do not inherit the retracted versions. In particular: the engine DOES
log why positions exit (exit_pass -> actions[] -> reason); do not rebuild that.

Headline: three exit tightenings shipped 2026-08-10 cut median give-back from -32% to -7% (the
ratchet works) but halved avg win $300 -> $144, taking the payoff ratio 2.61 -> 1.62 against a
~2.3 breakeven at 30% WR. Verdict already reached: the ladder STAYS, the next lever is ENTRY
selectivity, not exit width. Do not re-tune exits.

Work this queue, in order, and do not stop to ask me what to do next:

1. FIX unattended_health.py:173 _scheduled_days_mask -- it does int(dow) where dow can be a list,
   raising TypeError. Repro command is in the handoff. This is the root of 5 test failures. Fix,
   add a guard, re-run those 5.
2. Family B fixture sandboxing: trade_today_watcher (3), state_contracts (1).
3. Family C stale shape pins (~10) and Family D (2 -- confirm they are network-only first).
4. Explain why ribbon_flip_back went from 4% to 22% of all closes. C28 says it is a LAGGING exit.
   This is the largest unexplained compositional shift in the book.
5. Entry-quality: conviction C4/C5 now score for the first time. Accumulate shadow rows, report
   the would_block distribution weekly. It stays DISARMED.

Rules: run pytest in 30-file batches (the reaper kills python >5min). Use
setup/scripts/commit_scoped.py, never git add -A, never git stash. AST not grep for
claim-vs-retraction checks. Verify before claiming -- four wrong headlines were published
yesterday by not doing that. Report only when a queue item is DONE, not when you are about to
start one.
```
