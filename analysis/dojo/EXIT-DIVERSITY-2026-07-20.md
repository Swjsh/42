# CORRECTED RE-RUN 2026-07-21 (conductor, AFTERHOURS) -- DOJO-EXIT-HARNESS-BUGS bug 1 fixed

> The prior VOID banner (bug 1: entry-scan scope leaking cross-day cursors into
> `extract_entries_and_ribbon`) is fixed in `backtest/tools/dojo_exit_diversity_replay.py`
> -- the entry/ribbon cursor loop now walks ONLY the target day's own RTH bars (`day_rth`),
> while the full multi-month `bars` frame is still passed to `engine_step.step()` unchanged
> so ribbon/level EMA warmup is unaffected. RED-proofed via `git stash` on the source file
> alone: new guard `test_extract_entries_scoped_to_target_day_only` failed pre-fix with the
> EXACT leaked-date signature (`saw {'2026-06-30', '2026-06-29'}`), passed post-fix; full
> suite `backtest/tests/test_dojo_exit_diversity_replay.py` 11/11 green. Re-running the SAME
> reduced day-set now gives a sane, non-contaminated n=5 real-fills episodes per profile
> (was the bogus n=115 across 810 cross-day episodes before). **Bug 2 re-assessed, NOT a
> separate defect:** CONTROL==RIBBON identical-to-the-penny is BY DESIGN for this study's
> ribbon_ride-only entry population -- `ribbon_ride`'s REGISTRY exit shape already equals
> RIBBON's own patch (`stop_mode=structure`, `trail_pct=0.15`), a mathematical identity this
> module's own docstring (lines 24-34) and the frozen pre-reg's `exit_profiles_disclosure`
> already called out explicitly BEFORE this run, and `test_exit_profiles_pulled_from_live_
> accounts_json` already pins it. ZONE-RIDE (the only profile that CAN differ) does differ
> below ($369.91 vs $400.91) -- the profile->exit_patch mapping was reaching
> `walk_exit_manager` correctly all along; it was bug 1's cross-day contamination that made
> the earlier 115-episode run look suspicious. Verdict below is CONTROL_HOLDS on a much
> smaller, now-honest n=5 -- read it as "first clean signal", not a final answer; more
> curriculum days (07-08/07-09/etc, currently BS-synthetic/no OPRA per the per-day table)
> would sharpen it. Full detail: `automation/overnight/queue.md` DOJO-EXIT-HARNESS-BUGS
> (closed this fire) + `automation/overnight/STATUS.md` [2026-07-21 ~16:12 ET].

---

# DOJO Exit-Diversity Replay -- 2026-07-20

Generated: 2026-07-21T16:22:53.920428-04:00
Pre-registration: `analysis/dojo/exit-diversity-prereg-2026-07-20.json` (sha256-16 `1f946a883866465f`)

## Scope

Ran a REDUCED day-set: `['2026-06-30', '2026-07-02', '2026-07-17', '2026-07-20']` (scope filter `--days 2026-06-30,2026-07-02,2026-07-17,2026-07-20`). Skipped-for-scope: `['2026-06-29', '2026-07-01', '2026-07-06', '2026-07-07', '2026-07-08', '2026-07-09', '2026-07-10', '2026-07-13', '2026-07-14']`. The reduction lowers n ONLY -- the frozen pre-reg's win-gate thresholds and profile definitions are untouched (verified: same pre-reg sha256). Held-out days in the frozen pre-reg = `['2026-07-14', '2026-07-17', '2026-07-20']`; of those, actually run under this scope = `['2026-07-17', '2026-07-20']` -- so condition_4 (held-out) rests on that thinner basis, disclosed here, not silently.

## Headline (real fills only -- OPRA-priced episodes, gate-eligible)

| Profile | n | Total P&L | Expectancy/tr | WR |
|---|---|---|---|---|
| CONTROL | 5 | $400.91 | $80.18 | 0.4 |
| RIBBON | 5 | $400.91 | $80.18 | 0.4 |
| ZONE-RIDE | 5 | $369.91 | $73.98 | 0.4 |

## Headline (including BS-synthetic episodes -- disclosed, not gate-eligible)

| Profile | n | Total P&L | Expectancy/tr | n synthetic | n no-fill/error |
|---|---|---|---|---|---|
| CONTROL | 10 | $443.84 | $44.38 | 5 | 0 |
| RIBBON | 10 | $443.84 | $44.38 | 5 | 0 |
| ZONE-RIDE | 10 | $404.68 | $40.47 | 5 | 0 |

## Win-gate verdicts (challengers vs CONTROL, real fills only)

### RIBBON -- **CONTROL_HOLDS**

- Beats CONTROL aggregate: False ($400.91 vs $400.91)
- Day-majority: False (0/2 days)
- Survives top-trade drop: False (total-minus-top $-21.04 vs control $400.91)
- Holds on held-out subset: False ($324.95 vs control $324.95)

### ZONE-RIDE -- **CONTROL_HOLDS**

- Beats CONTROL aggregate: False ($369.91 vs $400.91)
- Day-majority: False (0/2 days)
- Survives top-trade drop: False (total-minus-top $-34.54 vs control $400.91)
- Holds on held-out subset: False ($311.45 vs control $324.95)

## Per-day entry counts

| Day | Entries | OPRA available | Error |
|---|---|---|---|
| 2026-06-29 | 0 | True |  |
| 2026-06-30 | 0 | True |  |
| 2026-07-01 | 0 | True |  |
| 2026-07-02 | 3 | True |  |
| 2026-07-06 | 0 | True |  |
| 2026-07-07 | 0 | True |  |
| 2026-07-08 | 0 | True |  |
| 2026-07-09 | 0 | True |  |
| 2026-07-10 | 0 | True |  |
| 2026-07-13 | 0 | True |  |
| 2026-07-14 | 0 | True |  |
| 2026-07-17 | 2 | True |  |
| 2026-07-20 | 5 | False |  |

## Reconciliation vs structure-stop-reference-level-2026-07-20.json

structure-stop-reference-level-2026-07-20.json tested a DIFFERENT mechanism than this study's ZONE-RIDE: REF-ZONE substitutes the structure stop's REFERENCE LEVEL (this position's entry trigger_level -> the nearest key-level ZONE BOUNDARY) -- a knob that does not exist in ExitShape today (disclosed schema gap, accounts.json 2026-07-20 note). This study's ZONE-RIDE is risky-3's ACTUAL live exit_patch: the SAME trigger-exact structure stop as CONTROL, with a WIDER chandelier trail (trail_pct 0.15 -> 0.20). Naming overlap ('zone') is coincidental -- these are not the same lever, so agreement or disagreement between them is not evidence either way about the other.

- REF-EXACT (their CONTROL) layer(a) fresh-slice expectancy: $-47.34/tr (n=18)
- REF-ZONE layer(a) fresh-slice expectancy: $-63.73/tr (n=18) -- WORSE than control (the CLAUDE.md-cited -$63.73 vs -$47.34 finding)
- REF-EXACT layer(b) real-fills anchor total: $-900.7 (n=99)
- REF-ZONE layer(b) real-fills anchor total: $481.2 (n=99) -- LOOKS better in raw aggregate, but REJECTED: layer(a) exp $-63.73 vs control $-47.34 (FAIL); layer(b) anchor $481.2 vs control $-900.7 (PASS); sub-window deltas first=$1473.4 second=$-91.5 (sign_flip=True); n_recoverable(layer b)=68 (floor-clearing)

The frozen finding's rejection mechanism (sub-window sign flip -- first half $1473.4, second half $-91.5) is EXACTLY the failure class this study's condition_3 (concentration / top-trade-drop) and condition_4 (held-out subset) are built to catch. If ZONE-RIDE's aggregate here also looks good only because of 1-2 trades or only in one half of the curriculum, this study's own gate will independently reject it for the same reason -- mutual corroboration of the underlying doctrine (C4/C24: don't trust an aggregate win without checking who's carrying it), even though the two studies are testing different knobs.

## Verdict

**CONTROL_HOLDS**

No challenger profile cleared the full frozen gate. CONTROL holds -- today's live trigger-exact structure stop + chandelier remains the best-evidenced exit policy for core-safe's own entries over this curriculum. This is an honest, valid, and useful morning answer (per the spec's own framing), not a null result to be hidden.
