# ⛔ VOID RESULT — DO NOT TRUST THIS VERDICT (annotated 2026-07-21 by Opus)

> This run is INVALID. Two load-bearing harness bugs, confirmed from the episode data:
> (1) ENTRY-SCAN SCOPE BUG: entries were scanned across the WHOLE multi-month cache frame, not
>     the target day -- e.g. a `day=2026-06-30` episode has `cursor_et=2026-05-21`. This inflated
>     4 days to 810 episodes / 270 'entries' (most BS-synthetic, since OPRA doesn't cover the
>     wrong old dates). load_day_bars returns full history; the entry extraction must filter to
>     replay_day's RTH bars only.
> (2) EXIT PROFILES DO NOT DIFFERENTIATE: CONTROL and RIBBON P&L are identical to the penny
>     ($-17261.35) across all 115 episodes, and a CONTROL episode shows exit_reason=ribbon_flip_back.
>     The profile->exit_patch mapping collapses; the harness is not testing different exits.
> The 'CONTROL_HOLDS' verdict below is comparing garbage to garbage. The exit-diversity question
> is UNANSWERED. Fix tracked in queue.md DOJO-EXIT-HARNESS-BUGS. The DST-cache fix (c8c0a0d) and
> the INTERACTIVE dojo (24bc365, all 5 arms) are unaffected and real.

---

# DOJO Exit-Diversity Replay -- 2026-07-20

Generated: 2026-07-21T10:30:27.494655-04:00
Pre-registration: `analysis/dojo/exit-diversity-prereg-2026-07-20.json` (sha256-16 `1f946a883866465f`)

## Scope

Ran a REDUCED day-set: `['2026-06-30', '2026-07-02', '2026-07-17', '2026-07-20']` (scope filter `--days 2026-06-30,2026-07-02,2026-07-17,2026-07-20`). Skipped-for-scope: `['2026-06-29', '2026-07-01', '2026-07-06', '2026-07-07', '2026-07-08', '2026-07-09', '2026-07-10', '2026-07-13', '2026-07-14']`. The reduction lowers n ONLY -- the frozen pre-reg's win-gate thresholds and profile definitions are untouched (verified: same pre-reg sha256). Held-out days in the frozen pre-reg = `['2026-07-14', '2026-07-17', '2026-07-20']`; of those, actually run under this scope = `['2026-07-17', '2026-07-20']` -- so condition_4 (held-out) rests on that thinner basis, disclosed here, not silently.

## Headline (real fills only -- OPRA-priced episodes, gate-eligible)

| Profile | n | Total P&L | Expectancy/tr | WR |
|---|---|---|---|---|
| CONTROL | 115 | $-17261.35 | $-150.1 | 0.0348 |
| RIBBON | 115 | $-17261.35 | $-150.1 | 0.0348 |
| ZONE-RIDE | 115 | $-17292.35 | $-150.37 | 0.0348 |

## Headline (including BS-synthetic episodes -- disclosed, not gate-eligible)

| Profile | n | Total P&L | Expectancy/tr | n synthetic | n no-fill/error |
|---|---|---|---|---|---|
| CONTROL | 270 | $-19842.04 | $-73.49 | 155 | 0 |
| RIBBON | 270 | $-19842.04 | $-73.49 | 155 | 0 |
| ZONE-RIDE | 270 | $-19881.2 | $-73.63 | 155 | 0 |

## Win-gate verdicts (challengers vs CONTROL, real fills only)

### RIBBON -- **CONTROL_HOLDS**

- Beats CONTROL aggregate: False ($-17261.35 vs $-17261.35)
- Day-majority: False (0/3 days)
- Survives top-trade drop: False (total-minus-top $-17683.3 vs control $-17261.35)
- Holds on held-out subset: False ($-15531.16 vs control $-15531.16)

### ZONE-RIDE -- **CONTROL_HOLDS**

- Beats CONTROL aggregate: False ($-17292.35 vs $-17261.35)
- Day-majority: False (0/3 days)
- Survives top-trade drop: False (total-minus-top $-17696.8 vs control $-17261.35)
- Holds on held-out subset: False ($-15544.66 vs control $-15531.16)

## Per-day entry counts

| Day | Entries | OPRA available | Error |
|---|---|---|---|
| 2026-06-29 | 0 | True |  |
| 2026-06-30 | 56 | True |  |
| 2026-07-01 | 0 | True |  |
| 2026-07-02 | 58 | True |  |
| 2026-07-06 | 0 | True |  |
| 2026-07-07 | 0 | True |  |
| 2026-07-08 | 0 | True |  |
| 2026-07-09 | 0 | True |  |
| 2026-07-10 | 0 | True |  |
| 2026-07-13 | 0 | True |  |
| 2026-07-14 | 0 | True |  |
| 2026-07-17 | 75 | True |  |
| 2026-07-20 | 81 | False |  |

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
