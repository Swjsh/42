# PRE-REGISTRATION — CONVICTION C4 CONTINUATION-POLARITY SIDECAR, 2026-09-03

**Status: FROZEN before any forward reading of this instrument's decision rule.** Commit
timestamp of this file is the freeze proof. `setup/scripts/conviction_c4_sidecar.py` (the
ledger/summary builder) and `setup/install-conviction-c4-sidecar.ps1` (the scheduled task)
are committed alongside this file.

Queue item: `F4` in `analysis/deep-research/2026-09-03-money/SYNTHESIS.md` §3 ("Conviction
C4 polarity recalibration (shadow sidecar)"), descended from hypothesis H2
(`analysis/deep-research/2026-09-03-money/range-extreme-dead.md`) and its probe
(`backtest/tools/money_range_extreme_probe.py`).

---

## 1. What is being judged

`conviction.py`'s C4 `range_extreme` component is **FROZEN and UNCHANGED** — this prereg
never touches it (config freeze through 2026-10-30, and C4 is shadow-only regardless: there
is no `SKIP_LOW_CONVICTION` branch anywhere in the live engine). What is judged is a
**candidate replacement polarity for C4**, scored entirely off to the side:

- **LIVE polarity** (`conviction.py`'s shipped rule, unchanged): calls want
  `range_position <= 0.30`, puts want `range_position >= 0.70` — a MEAN-REVERSION shape
  ("bounce at the extreme").
- **CONTINUATION polarity** (the candidate): calls want `range_position >= 0.70`, puts want
  `range_position <= 0.30` — the MIRROR IMAGE, matching the shape the live trigger family
  (`BULLISH_RECLAIM_RIDE_THE_RIBBON` / `BEARISH_REJECTION_RIDE_THE_RIBBON`, 100% of scored
  rows per H2) actually produces.

## 2. Why H2's own counterfactual (money_range_extreme_probe.py Part 4) is not enough

H2's probe already computed one counterfactual flip on the SAME population this sidecar
reads (482 post-fix core rows as of 2026-09-02) and found **n=5** outcome-joined rows,
**CI [-$93.00, +$66.40] straddling zero — INCONCLUSIVE by its own report**. That is not
evidence either way; it is a thin read that happened to be computable that day. This prereg
exists so the SAME question gets a properly powered, honestly-labeled read instead of being
re-quoted as settled from n=5:

1. **Fleet coverage.** H2 found **zero** conviction coverage on the four fleet arms
   (`risky-1`, `risky-3`, `safe-1`, `safe-3`) — `_conviction_shadow()` runs only on the core
   tick path. The probe's n=5 outcome join is core-only. This sidecar recomputes the ONE
   component that is reconstructable from a fleet PLACED row's own fields (`range_position`,
   off the cached SPY 1-minute tape) and joins those PLACED rows to real fills too — the
   book-wide outcome-join population this candidate needs to be read honestly.
2. **A frozen, standing instrument**, not a one-shot script run once by a probe. Every
   session — trading or not — the population grows; the decision rule below is evaluated
   against whatever has accrued, not against one Thursday's snapshot.

## 3. Population and measurement (frozen)

- **Core rows:** every row in `automation/state/core-decisions.jsonl` that carries a
  `conviction` block with `ts_et >= 2026-08-14T19:15:22` (the `974ca235` fix boundary that
  `conviction_shadow_report.py` already uses — pre-fix rows scored C4/C5 degraded by
  construction and are excluded here for the same reason). `coverage: "full_conviction"` —
  these rows already carry all 7 components + a real floor (`floor_effective`) + a real
  `would_block` (`total < floor_effective`). C4 is re-scored under both polarities from the
  row's own **stored** `components.range_position`; `total` is **re-derived**
  (`total_live - orig_C4 + flipped_C4`), never re-invoked through `score_conviction()` (that
  call needs `level_records`/`level_states`/`structure_side` a decision-ledger row does not
  retain). Equivalence between this re-derivation and the row's own stored `total` is proven
  on >=20 real rows in `backtest/tests/test_conviction_c4_sidecar_2026_09_03.py`.
- **Fleet rows:** every `placement.placed == true` row across the four fleet ledgers
  (`automation/state/fleet/{risky-1,risky-3,safe-1,safe-3}/decisions.jsonl`).
  `coverage: "c4_component_only"` — a fleet PLACED row carries no C1/C2/C3/C5/C6/C7 (no
  level_records, no memory, no structure read at placement time), so there is **no real
  floor and no real `would_block`** for these rows. `range_position` is recomputed as
  `(trigger_close - session_low) / (session_high - session_low)`, session hi/lo taken
  **THROUGH the row's own `ts_et` only** (no look-ahead — the same
  `win.iloc[:trig_idx+1]`-style prefix convention `heartbeat_core.py` uses for the core
  path), off the cached `backtest/data/spy_sip_cache/spy_1m_<date>.json` 1-minute tape. A
  date with no cached tape (e.g. the live session on build day) is skipped and recorded with
  `skip_reason: "no_cached_spy_tape_for_date"` — never fabricated. The
  `would_block_*_c4proxy` fields on fleet rows name EXACTLY what they measure — "did the C4
  point alone fail to score" — and are never pooled with core's real floor-based
  `would_block` under the same key (`coverage` labels every row and every summary cell).
- **No backfill boundary, unlike the sibling `tp1_r50_forward_shadow.py` clock.** This
  sidecar re-scores the FULL existing post-fix history on its first run (534 core rows / 270
  fleet rows as of the freeze date) rather than starting an empty forward-only clock — a
  deliberate difference from `tp1_r50_forward_shadow.py`'s no-backfill design, because this
  instrument's job is "how would a different C4 polarity have read the SAME already-closed
  decisions", not "what does a NEW knob do to NEW trades". This is stated explicitly so the
  bar below is read correctly: it is a MINIMUM SAMPLE SIZE floor on the accrued population,
  not a "wait N sessions from zero" clock — and the population is real closed decisions and
  real fills, never simulated ones.

## 4. Forward bar (frozen — NOT softened at read time)

**AMENDED 2026-09-03 (post-freeze fix, see §9 below): the decision-bearing bar is CORE ROWS
ONLY.** BOTH required before this shadow's decision rule may be READ:

- **>= 20 trading sessions accrued** (distinct dates across applicable **core** rows only —
  `coverage: "full_conviction"`, `not_applicable: false`).
- **>= 60 scored core rows** (`coverage: "full_conviction"`, `not_applicable: false`).

Fleet coverage (`coverage: "c4_component_only"`, summed across the four fleet arms) is still
measured and reported every night (`bar.fleet_rows_scored_disclosure_only`,
`bar.fleet_sessions_disclosure_only`, `bar.min_fleet_rows_disclosure_only`) but is
**disclosure only — it never gates `bar_met`**, because a fleet row carries no real floor /
`would_block` to decide anything with (§3).

Below the bar the instrument's `status` is `ACCRUING` — `bar.sessions_accrued` /
`bar.core_rows_scored` name the current counts every night, and `decision_rule` values are
still computed and written (for visibility, per OP-33) but MUST NOT be read as a verdict
below the bar.

## 5. Decision rule (frozen — cannot be softened after data starts arriving)

**AMENDED 2026-09-03 (post-freeze fix, see §9 below): the decision statistic is CORE ROWS
ONLY.** Once the bar in §4 is met, the CONTINUATION polarity becomes eligible to be cited as
forward evidence for a real conviction-recalibration proposal ONLY if BOTH hold on the
accrued **core-only** ledger (`core_outcome_join` in the summary — rows with the real stored
7-component conviction block and a real `floor_effective`-based `would_block`; **never**
pooled with the fleet C4-proxy cells, which carry no real floor and are surfaced separately,
disclosure-only, under `fleet_c4proxy_outcome_join` — see §7's `do_not`):

1. **The `would_block` cohort's mean-$ CI-upper < 0 under continuation polarity** — a
   day-clustered percentile bootstrap (resampling trading DAYS with replacement, matching
   `go_live_gate.bootstrap_pf_ci`'s methodology, 2000 resamples, fixed seed) on the real-$
   outcome-joined **core** rows that continuation polarity WOULD have blocked. This is the
   "it blocks losers" test — the upper bound of the CI must sit strictly below zero, not
   merely the mean.
2. **All four named big winning days' entries are `would_allow` under continuation
   polarity** — `2026-08-06`, `2026-08-13`, `2026-08-27`, `2026-08-28` (the same four days
   named throughout the 2026-09-03 money-leak audit, `SYNTHESIS.md` §1). This check still
   spans both core and fleet rows individually (each row's own `would_block_continuation` /
   `would_block_continuation_c4proxy` field, read per-row, never aggregated into a pooled
   statistic) — a polarity that blocks even one entry on a day that pays the book is
   disqualified regardless of what its CI says elsewhere, the same "touches zero winners" bar
   `range-extreme-dead.md`'s own counterfactual already applied informally to the flip-only
   case.

Any single failure = **the forward evidence does not support recalibrating C4 to
continuation polarity**, full stop. Reaching the bar is permission to READ the verdict, not
to ship it — a positive read here is the PERMISSION for a SEPARATE, later ratification
decision (which would need its own eval-first scorecard per CLAUDE.md OP-11) to cite this
ledger as its evidence base, exactly the two-step contract `tp1_r50_forward_shadow.py` and
`stop_mode_shadow_ledger.py` both already use for their own sibling clocks.

## 6. What this instrument is not

Descriptive and shadow-only. It writes a ledger + a summary, changes nothing in
`conviction.py` (which stays FROZEN through 2026-10-30 regardless of what this sidecar
reads), proposes no live change, places no order, and gates nothing — there is no
`SKIP_LOW_CONVICTION` branch in the engine today and this sidecar does not add one. A
positive verdict here is never itself sufficient to recalibrate C4.

## 7. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "F4-conviction-c4-sidecar",
    "queue_source": "analysis/deep-research/2026-09-03-money/SYNTHESIS.md#F4",
    "descends_from": ["analysis/deep-research/2026-09-03-money/range-extreme-dead.md",
                       "backtest/tools/money_range_extreme_probe.py"],
    "frozen_date": "2026-09-03",
    "backfill": "full post-fix history scored on first run -- NOT a no-backfill clock, see section 3",
    "thresholds": {
      "live_call_max_pos": 0.30, "live_put_min_pos": 0.70,
      "continuation_call_min_pos": 0.70, "continuation_put_max_pos": 0.30
    },
    "population": {
      "core_source": "automation/state/core-decisions.jsonl",
      "core_fix_boundary_et": "2026-08-14T19:15:22",
      "fleet_sources": ["automation/state/fleet/risky-1/decisions.jsonl",
                         "automation/state/fleet/risky-3/decisions.jsonl",
                         "automation/state/fleet/safe-1/decisions.jsonl",
                         "automation/state/fleet/safe-3/decisions.jsonl"],
      "fleet_row_filter": "placement.placed == true"
    },
    "bar": {
      "min_sessions": 20,
      "min_core_rows_scored": 60,
      "min_fleet_rows_scored_disclosure_only": 60,
      "decision_gating": "core_only -- fleet coverage is disclosure only, see section 9"
    },
    "decision_rule": {
      "would_block_ci_upper_lt_zero_core_only": true,
      "big_days_all_would_allow": true,
      "big_winner_days": ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"],
      "all_required": true,
      "softenable": false
    },
    "artifacts": {
      "ledger": "analysis/recommendations/conviction-c4-sidecar-ledger.jsonl",
      "summary": "analysis/recommendations/conviction-c4-sidecar-summary.json",
      "builder": "setup/scripts/conviction_c4_sidecar.py",
      "scheduled_task": "Gamma_ConvictionC4Sidecar",
      "install_script": "setup/install-conviction-c4-sidecar.ps1"
    },
    "do_not": [
      "flip conviction.py's live C4 polarity based on this sidecar alone",
      "pool fleet c4proxy would_block with core's real floor-based would_block under one key -- there is no pooled cell in the summary (book_outcome_join removed 2026-09-03, see section 9); core_outcome_join is the ONLY decision-bearing cell, fleet_c4proxy_outcome_join is disclosure-only",
      "soften the decision rule in section 5 after data starts arriving"
    ]
  }
}
```

## 8. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_ConvictionC4Sidecar
-Confirm:$false` + delete `setup/scripts/conviction_c4_sidecar.py` +
`setup/install-conviction-c4-sidecar.ps1` + this file. Nothing on the trading path depends
on this instrument — `conviction.py` is untouched throughout, and this is an analysis-only
leaf exactly like `Gamma_LadderRungShadow` / `Gamma_Tp1R50ForwardShadow`.

## 9. 2026-09-03 post-freeze corrections (bug fixes, not a softening)

Two blocking defects were found in this instrument on its own freeze day, before any forward
verdict had been ratified from it, and are fixed here. Neither is a "softening" under §7's
`do_not` (a softening loosens a bar or a threshold to manufacture a pass; both fixes below
tighten correctness of what was already specified, and one of them makes the decision rule
*harder* to satisfy by removing rows that were previously helping it):

1. **LOOK-AHEAD in `range_position_from_tape()` (fleet C4-proxy scoring), confirmed on real
   data.** The original filter `[b for b in bars if b['hhmmss'] <= hhmmss]` compared the
   trigger tick's wall-clock time against each cached bar's **START** timestamp using `<=`.
   Because fleet decision ticks fire a few seconds after the minute mark (not exactly on
   it), this let the bar still forming AT tick time (e.g. a 14:49:03 tick pulling in the
   14:49:00-14:50:00 bar) leak up to ~59s of its own future high/low/close into
   `range_position` — the exact look-ahead shape `heartbeat_core.py`'s `trig_idx = n - 2`
   convention exists to prevent on the core path. Fixed: a bar now qualifies only when its
   start is strictly before the tick's own minute floor (`b['t'] < floor_to_minute(tick)`),
   i.e. only bars that have actually closed by the tick. This changes `range_position` (and
   therefore `c4_live`/`c4_continuation`/`would_block_*_c4proxy`) for fleet rows whose
   trigger second was non-zero — most of them. Guard:
   `test_range_position_from_tape_excludes_forming_bar_no_lookahead` and
   `test_range_position_from_tape_mutating_forming_or_future_bar_is_inert` in
   `backtest/tests/test_conviction_c4_sidecar_2026_09_03.py`.
2. **DECISION-RULE CONTRADICTION between §5 and §7.** §7's own `do_not` already forbade
   pooling fleet C4-proxy `would_block` with core's real floor-based `would_block` under one
   key — but §5 (as originally written) read the decision statistic off `book_outcome_join`,
   a pool of core + all four fleet arms. That pooled cell let fleet rows (no real floor, no
   real 7-component score — a proxy on ONE component) move the CI that decides whether C4's
   polarity gets recalibrated. Fixed: §4 and §5 above are now core-only
   (`core_outcome_join`); the fleet C4-proxy cells still exist for disclosure
   (`fleet_c4proxy_outcome_join`) but never feed `decision_rule`. §7's JSON `bar` and
   `decision_rule` blocks were updated to match; `book_outcome_join` no longer exists in the
   summary (`code ~conviction_c4_sidecar.py:602-608` pre-fix). Guard:
   `test_summary_has_no_pooled_outcome_cell` in the test file.

Both fixes were applied, the ledger + summary were rebuilt from scratch (no leaked rows
carried forward), and the guard suite re-passed before this instrument's `status` was next
read. See `setup/scripts/conviction_c4_sidecar.py` module docstring and
`range_position_from_tape()`'s own docstring for the mechanical detail.
