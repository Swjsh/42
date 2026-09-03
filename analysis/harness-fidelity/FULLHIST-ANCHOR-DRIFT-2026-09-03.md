# FULLHIST-ANCHOR-DRIFT — 2026-09-03

## Verdict

**Root cause: engine correctness fix (commit `4249d95e`, 2026-08-23), not a bug in tonight's
changes, not a data-file swap, not nondeterminism.** The stored anchor the test hardcodes
(190 trades / $5,064.75) — and even the currently-committed scorecard file's own headline
(191 / $4,808.75) — are both STALE relative to the current, more-correct engine. **Recommended
action: re-anchor (proposal below), do not revert the filter fix.**

## Reproduction

```
backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_structure_shift_cascade_ab.py::TestBaselineAnchorReproduction::test_control_prefix_reproduces_stored_scorecard -m slow -v
```

Output (77s):
```
E       AssertionError: expected 190 trades in the <=2026-07-22 prefix (stored engine-fullhist-replay-2026-07-23 scorecard), got 189
E       assert 189 == 190
FAILED backtest\tests\test_structure_shift_cascade_ab.py::TestBaselineAnchorReproduction::test_control_prefix_reproduces_stored_scorecard
======================== 1 failed in 77.16s (0:01:17) =========================
```

Ran a second time via a standalone dump script (`ssc.run_control_with_candidate_capture()` +
`derive_control_rows`, byte-identical to the guarded test): `PREFIX_N 189 TOTAL 4381.05`.
Combined with the overnight guard-watch run (also 189), that is **3 independent runs, all 189
— deterministic**, ruling out cause (d).

## The missing/extra trades (diffed against the stored scorecard, n=191, `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`)

Matched by (date, entry_time_et, symbol). 5 missing, 3 extra — net -2, consistent with 191→189:

| Change | Date | Entry ET | Symbol | Triggers | Tier | P&L |
|---|---|---|---|---|---|---|
| MISSING | 2025-07-17 | 09:40 | SPY250717C00625000 | level_reclaim, confluence, **sequence_reclaim** | SUPER | +541.00 |
| MISSING | 2025-12-11 | 12:40 | SPY251211C00686000 | level_reclaim, confluence, **sequence_reclaim** | SUPER | +486.20 |
| MISSING | 2026-01-27 | 10:50 | SPY260127C00694000 | level_reclaim, confluence, **sequence_reclaim** | SUPER | +442.00 |
| MISSING | 2026-05-19 | 14:10 | SPY260519C00737000 | level_reclaim, confluence, **sequence_reclaim** | SUPER | -280.00 |
| MISSING | 2026-07-15 | 09:55 | SPY260715C00754000 | level_reclaim, confluence, **sequence_reclaim** | SUPER | -153.00 |
| EXTRA | 2025-12-03 | 12:35 | SPY251203C00683000 | level_reclaim, confluence, **sequence_reclaim** | SUPER | -180.00 |
| EXTRA (same-day cascade) | 2026-05-19 | 14:20 | SPY260519P00737000 | trendline_rejection | TRENDLINE | +159.00 |
| EXTRA (same-day cascade) | 2026-07-15 | 13:55 | SPY260715C00754000 | level_reclaim, ribbon_flip | LEVEL | -325.00 |

Every one of the 5 removed and the 1 net-new bull entry carries `sequence_reclaim` as a trigger
— the exact predicate `resolve_level_state()` feeds. The other 2 "extras" on 2026-05-19 and
2026-07-15 are same-day NOT_FLAT cascade effects: removing the earlier SUPER sequence_reclaim
entry freed the position slot for a different setup to fire later that day. Not independent bugs.

## Attribution

**(a) Engine change since 2026-07-23 — CONFIRMED.** Commit `4249d95e` "fix(filters):
deterministic level_state resolution (exact-key first, then role+recency)" (2026-08-23),
followed by `30e51b9f` (NaN-safety hardening, same mechanism, no behavior-scope change).
`4249d95e`'s own message: "The shared price->LevelState lookup in filters.py scanned
ctx.level_states in DICT-INSERTION ORDER and took the first entry within $0.05 ... Applied to
BOTH sites (bearish sequence_rejection, bullish **sequence_reclaim**) ... GT 5/5 known
mis-resolutions corrected." `ctx.level_states` is the orchestrator's own dict, built once and
never reset across a multi-day replay — exactly the code path `run_backtest` (CONTROL) walks.
This is a **deliberate, evidence-backed correctness fix** (RED-proofed, guard suite went from
12 failed / 13 passed pre-fix to 13/13 post-fix), not an accidental regression.

**(b) Bar-file swap/two-time-frame mix — RULED OUT.** `backtest/data/spy_5m_2025-01-01_2026-07-22.csv`
and the matching VIX file are untracked (gitignored) but their mtimes are frozen at
`2026-07-22 20:36` — unchanged since creation, never touched since. Byte-identical input data.

**(c) Tonight's changes (attic move `d45c673f`, et_frame parsing `9939b15e`, go_live_gate
refresh `c362b5b2`) — RULED OUT.** None of those touch `backtest/lib/filters.py`,
`backtest/lib/orchestrator.py`, or the SPY/VIX data files; a broken import from the attic move
would surface as an ImportError, not a silent trade-count drift. The causal commit (`4249d95e`)
is 10 days old, landed 2026-08-23 — the drift is exactly the "weeks old, surfacing only now
because slow tests were never run" scenario the task brief flagged.

**(d) Nondeterminism — RULED OUT.** 3 independent runs, all 189.

## A second, independent, pre-existing anchor-drift layer

The test's hardcoded literals (190 / $5,064.75) are themselves already stale versus the
currently **committed** scorecard file, independent of tonight's finding: commit `df0348d9`
(2026-08-01, "fix(regime-library): pin all 15 threshold constants") regenerated
`engine-fullhist-replay-2026-07-23.json` and its own commit message discloses "Entry count
drifted from the 2026-07-23 cached run (207 raw entries now vs then)... NOT introduced by this
change" — rewriting the file's headline from 190/$5,064.75 to the currently-committed
**191/$4,808.75**. The test was never updated to match. Unlike `structure_shift_cascade_ab.py`'s
own runtime check (`main()`, reads `stored["headline"]["n_trades"]` live off disk — always
correct by construction), `tests/test_structure_shift_cascade_ab.py` hardcodes the literals
instead of reading the file, so it silently fell one anchor-generation behind in August and
would have failed regardless of the 08-23 filter fix, just against a different expected number
(191, not 190).

## Recommended action

1. **Do not revert `4249d95e`/`30e51b9f`** — the LevelState fix is evidence-backed (RED-proofed,
   explains a real live-vs-GT accident, not a live behavior regression: "LIVE 0/9 documented
   ambiguous states change (live behaviour byte-identical)").
2. **Re-anchor** (a reviewed change, not applied here): regenerate
   `analysis/recommendations/engine-fullhist-replay-2026-07-23.json` by re-running
   `backtest/tools/engine_fullhist_replay.py` against current code, then update
   `tests/test_structure_shift_cascade_ab.py::TestBaselineAnchorReproduction` to either (a) read
   `stored["headline"]["n_trades"]`/`total_pnl` from the regenerated file dynamically instead of
   hardcoding literals — closing the "second drift layer" above permanently — or (b) hardcode
   the new verified n=189 / $4,381.05 with a comment citing this report and commit `4249d95e`.
   Option (a) is the durable fix; the test's own docstring already argues for calling the tool's
   real functions instead of reimplementing, the same principle applies to the expected value.
3. File a queue item: any future `filters.py`/`orchestrator.py` change that touches entry-scoring
   predicates should re-run `engine_fullhist_replay.py` and `structure_shift_cascade_ab.py`'s
   baseline-anchor test in the SAME PR/session that lands it — the 10-day silent-drift window
   here existed only because the slow suite wasn't running (already fixed today, separately).

## UNVERIFIED / not checked

- Whether `4249d95e`'s other 4 corrected GT mis-resolutions (it says "5/5") land inside this
  same 2025-01-02..2026-07-22 window or outside it — only inferred from the trade diff above,
  not cross-referenced against the commit's own test file line-by-line.
- Whether the P&L delta on the 3 "extra" cascade rows fully reconciles to the $683.70 total
  swing (5064.75 -> 4381.05) at the cent level — the trade-level diff is exact; the full
  day-by-day reconciliation of downstream exit re-derivation was not walked.
