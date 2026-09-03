# PRE-REGISTRATION — RETEST ZONE-WIDTH GRID + ZONE-WIDTH PERSISTENCE, 2026-09-03

**Status: FROZEN before any forward data accrues.** Commit timestamp of this file is the
freeze proof. `setup/scripts/retest_zone_shadow.py` (the ledger/summary builder) and
`setup/install-retest-zone-shadow.ps1` (the scheduled task, NOT yet registered — installer
written, not run) are committed alongside this file. `FREEZE_DATE = "2026-09-03"` inside the
script marks every trade dated on/before this file's freeze date `in_sample: true`
(backfill, already-seen population) and every trade dated after it `in_sample: false`
(forward, judged population) — deterministically, by the trade's own `date_et`, independent
of which nightly run happens to process it.

Slug: `F3-retest-zone-grid`. Descends from
`analysis/deep-research/2026-09-03-money/retest-entry-variant.md` (H10, "RETEST ENTRY") and
its own Recommendation section, which named exactly the two follow-ups this instrument
delivers together.

---

## 1. What is being judged

H10's retest-entry variant of `ribbon_ride`: instead of entering `BEARISH_REJECTION_RIDE_THE_
RIBBON` / `BULLISH_RECLAIM_RIDE_THE_RIBBON` on the breakout tick, wait for the first pullback
that touches the trigger zone (`trigger_level ± zone_width`) and prints a 1-minute CLOSE back
in the trade direction within 30 minutes; cancel if the zone breaks first
(`backtest/tools/money_retest_entry_variant.py:retest_decision`, reused by import, never
modified). H10 found the AGGREGATE SIGN of this variant's effect flips between a $0.30 and a
$0.50 zone width — a free parameter the project could not previously pin down from history.

## 2. Step 1 finding — why the zone-width parameter has been unresolvable until now

Verified fresh this build:

- `journal/key-levels-archive/` holds **18 dated snapshots**, `key-levels-2026-05-19.json` ..
  `key-levels-2026-07-02.json`. **None of the 18 carry a `zone_width` field on any level**
  (schema_version 3 throughout — price/type/role/label/tier/source/verified_at/expires_at/
  reasoning/notes/entity_id/draw_needed only). The field exists only on today's *live*
  `automation/state/key-levels.json`, added to the schema sometime after the archive went
  stale.
- `analysis/level-quality/snapshots/` holds only 2 dates (2026-06-16, 2026-06-19), also
  pre-dating `zone_width`.
- **The archive is not currently advancing.** `Gamma_ArchiveKeyLevels` is not a registered
  scheduled task at all (`Get-ScheduledTask` returns nothing). `Gamma_DailyReview` — the
  other documented writer of this same archive path — IS registered but `State=Disabled`.
  Neither has fired since the last snapshot, **2026-07-02** — over two months before this
  freeze date.
- **Practical consequence:** every trade this backfill scores resolves
  `zone_source="default"` ($0.30) — verified in the actual backfill run below, 200/200 rows.
  The "in-force width" column cannot yet be distinguished from the $0.30 grid point for the
  historical population. This is disclosed on every row and in the summary
  (`in_force_zone_source_counts`), never silently assumed away. If the archive resumes AND a
  future snapshot's schema carries `zone_width` (as today's live file already does), forward
  rows will begin resolving real per-level widths automatically — the resolver
  (`retest_zone_shadow.resolve_zone_width`) already reads whatever a dated snapshot contains;
  no code change is needed for that transition.
- This finding is itself part of what this instrument persists going forward: every future
  night's `in_force_zone_source_counts` in the summary makes it visible the moment the
  archive (if ever revived) starts actually carrying real widths.

## 3. Population and measurement (frozen)

- **Scope:** every CLOSED (`exit_qty >= qty`) engine entry whose `setup` is
  `BEARISH_REJECTION_RIDE_THE_RIBBON` or `BULLISH_RECLAIM_RIDE_THE_RIBBON`, **all arms**
  (safe-1/2/3, bold-2, risky-1, risky-3), sourced from
  `analysis/entry-quality/entry-quality-ledger.json`'s `events` (an existing nightly
  producer, already broker-truth-joined; carries `setup`/`trigger_level`/`arm` — EXTEND,
  DON'T FORK, same convention `tp1_r50_forward_shadow.py` documents for the same file).
  Entries with no `trigger_level` recorded cannot define a retest zone and are excluded
  (counted, not silently dropped — `n_no_trigger_level_excluded` in the summary).
- **Zone-width resolution (frozen):** for each entry, look up
  `journal/key-levels-archive/key-levels-<date_et>.json`; the level whose `price` is within
  $0.01 of the entry's `trigger_level` supplies `zone_width` when present. Any miss (no
  snapshot for the date, no level within tolerance, or a matched level with no `zone_width`
  key) falls back to the $0.30 default, flagged `zone_source: "default"`.
- **Per entry, score:**
  1. The ACTUAL breakout entry, walked once through the real production exit code
     (`backtest.lib.exit_manager_walk.walk_exit_manager`, via `money_retest_entry_variant.
     walk_one`, reused by import).
  2. The RETEST variant at the **frozen grid** {0.20, 0.30, 0.40, 0.50, 0.75} — five
     independent scorings, same population, same exit code.
  3. The RETEST variant at the entry's own **in-force width** (§ above) — reused from the
     matching grid column when the in-force width coincides with a grid value (it does for
     100% of the current backfill, since every row resolves to the $0.30 default), scored
     independently otherwise.
- **No look-ahead:** the retest decision at trigger tick `t0` reads only SPY 1-minute bars
  strictly after `t0` (unmodified `retest_decision`). The zone-width resolution reads only
  the archived snapshot dated to the trade's OWN session — never today's live file, never a
  future snapshot. A trade whose session's cached bars are not yet available is skipped with
  a reason (`skip_no_option_bars` / `skip_no_spy_1m_for_ribbon`), retried the next run, never
  backfilled with an assumption.
- **`in_sample` tag:** `date_et <= 2026-09-03` → `in_sample: true` (the one-time backfill of
  the population that exists at this freeze). `date_et > 2026-09-03` → `in_sample: false`
  (forward, judged data). This mirrors `tp1_r50_forward_shadow.py`'s `ACCRUAL_START_DATE`
  contract but keeps the (already-studied-once, contaminated for verdict purposes) backfill
  visible for disclosure rather than discarding it.

## 4. Backfill result (this build, run once)

`setup/scripts/retest_zone_shadow.py` was run once against the full current history: **200
scoreable entries** (of 347 RIDE_THE_RIBBON closed entries; 147 excluded for no
`trigger_level`), spanning **2026-07-13 .. 2026-09-02** (26 distinct days). All 200 are
tagged `in_sample: true`. `in_force_zone_source_counts: {"default": 200}` — confirms the § 2
finding empirically: the in-force column is identical to the $0.30 grid column for the
entire backfill. Full per-width, per-arm-trust-class, per-VIX-band, and per-big-day figures
are in `analysis/recommendations/retest-zone-shadow-summary.json` (`by_backfill_only`) —
**disclosure only, not a verdict**: this population overlaps H10's own already-studied
window and must never be read as an answer (exactly H10's own Recommendation item 2's
reasoning for why a fresh, pre-registered read is needed).

## 5. Forward bar (frozen — NOT softened at read time)

Both conditions required before this shadow may be READ as a verdict, evaluated on
**forward-only (`in_sample: false`) data**:

- **>= 20 forward trading sessions** (`n_forward_days >= 20`), AND
- **>= 40 forward signals** (`n_forward >= 40` — a qualifying RIDE_THE_RIBBON entry that
  reached scoring, i.e. closed with a `trigger_level`).

Below the bar the summary's `status` is `ACCRUING` and carries no ship/kill signal;
`forward_bar.sessions_to_bar` / `signals_to_bar` name the remaining distance every night.

## 6. Decision rule (frozen — the bar cannot be softened after data starts arriving)

Once the bar in § 5 is met, read **once**, on forward-only data:

1. **`by_forward_only.in_force.safe2_trusted.session_clustered_ci.ci_lower_2.5 > 0`** — the
   2.5th-percentile of a day-clustered percentile bootstrap (resampling trading DAYS with
   replacement, matching `go_live_gate.bootstrap_pf_ci`'s methodology) over the per-trade
   `(retest − actual)` delta, computed at each entry's own in-force width, restricted to
   **safe-2** (the only arm `WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md` clears for
   `walk_exit_manager` magnitude fidelity — every other arm's dollars are SIGN-ONLY, never
   the deciding number), is strictly positive.
2. **No big-winner-day sign flip at the in-force width** —
   `by_all_time.in_force.big_winner_days[<date>].sign_flip` is `false` for every one of the
   four named anchor days (2026-08-06, 2026-08-13, 2026-08-27, 2026-08-28). These are
   historical (all `in_sample: true`), so this check is read from the all-time cut, not the
   forward-only cut — the rule is "the in-force width must never have guttable the book's own
   biggest right-tail days," not "a NEW big day must appear forward" (none can, by
   construction — they are named historical anchors).

**Both conditions must hold.** Either failure = the forward evidence does not support
shipping any retest-entry variant, full stop.

**The grid columns are DISCLOSURE ONLY.** No width — not $0.20, not $0.50, not any value the
grid or the in-force column happens to show in a favorable light — may be picked *after*
looking at results. The only width this prereg licenses reading a verdict for is
**whatever width the archive actually puts in force**, exactly the thing H10's own
Recommendation asked this instrument to start persisting. If the archive never resumes, the
in-force width stays pinned at the $0.30 default and this prereg judges *that* value, forward,
honestly — it does not become permission to cherry-pick a grid column instead.

## 7. Scope discipline — expansion-class, config freeze

This is a **shadow-only, expansion-class** instrument (a NEW analysis file, a NEW nightly
task) — it does not touch, and per CLAUDE.md's config freeze (through **2026-10-30**) MUST
NOT touch before that date, any trading-path file: `automation/state/params.json`,
`automation/state/aggressive/params.json`, `setup/scripts/heartbeat_core.py`,
`backtest/lib/filters.py`, `backtest/lib/risk_gate.py`, `backtest/lib/exit_manager.py`,
`automation/state/fleet/exit_manager.py`, `automation/state/fleet/exit_actuator.py`,
`backtest/lib/strategies.py`, `automation/state/fleet/build_shared_signal.py`,
`automation/state/fleet/accounts.json`, `setup/scripts/conviction.py`. It flips no knob,
proposes no default, and places no order — even a positive verdict at § 6 is only the
PERMISSION for a separate, later, post-freeze ratification decision to cite this ledger as
its forward evidence base (same two-step contract `tp1_r50_forward_shadow.py`'s docstring
states for its own sibling clock).

## 8. Fidelity caveat (governs every dollar figure)

Per `analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md`,
`walk_exit_manager` magnitude-fidelity vs real fills **PASSES only for safe-2**
(aggregate_ratio 0.96, sign_agreement 95.8%). bold-2/risky-1/safe-3 individually **FAIL** the
magnitude criterion; risky-3 is outside that anchor's scope entirely. Every summary cut
discloses this split explicitly (`safe2_trusted` vs `other_arms_sign_only`) and never blends
them into one trusted number, per § 6's decision rule reading only the safe-2-trusted cut.

## 9. VIX join (disclosed approximation)

VIX is tick-level and shared across every arm consuming the same signal tick (per
`retest-entry-variant.md`'s own Method). Fleet arms (safe-1/safe-3/risky-1/risky-3) resolve
`order_id -> core_tick_id` from their own `automation/state/fleet/<arm>/decisions.jsonl`.
Core arms (safe-2/bold-2) resolve `order_id -> decision_tick_id` from the existing
`automation/state/fills-enriched.jsonl` join. Either tick id then joins `core-decisions.
jsonl`'s `vix` field (`money_retest_entry_variant.load_core_tick_vix`, reused). A trade with
no resolvable tick carries `vix: null` and is excluded from the VIX-band split only (152/200
rows, 76%, resolved a VIX in the backfill run) — never fabricated, never dropped from any
other cut.

## 10. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "F3-RETEST-ZONE-GRID",
    "descends_from": "analysis/deep-research/2026-09-03-money/retest-entry-variant.md",
    "frozen_date": "2026-09-03",
    "freeze_date_field": "FREEZE_DATE",
    "backfill": "once, in_sample:true, 200 entries, 2026-07-13..2026-09-02",
    "population": {
      "setups": ["BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"],
      "source": "analysis/entry-quality/entry-quality-ledger.json events",
      "arms": "all (safe-1, safe-2, safe-3, bold-2, risky-1, risky-3)"
    },
    "grid": [0.20, 0.30, 0.40, 0.50, 0.75],
    "grid_role": "disclosure_only",
    "in_force_resolution": {
      "archive": "journal/key-levels-archive/key-levels-<date_et>.json",
      "match_tolerance_usd": 0.01,
      "default_width": 0.30,
      "default_reason": "no dated archive currently carries a zone_width field (Step 1 finding)"
    },
    "bar": {"min_forward_sessions": 20, "min_forward_signals": 40},
    "decision_rule": {
      "safe2_ci_lower_2p5_gt_zero": true,
      "no_big_winner_day_sign_flip_at_in_force_width": true,
      "all_required": true,
      "softenable": false,
      "grid_pickable_after_reading": false
    },
    "artifacts": {
      "ledger": "analysis/recommendations/retest-zone-shadow-ledger.jsonl",
      "summary": "analysis/recommendations/retest-zone-shadow-summary.json",
      "builder": "setup/scripts/retest_zone_shadow.py",
      "scheduled_task": "Gamma_RetestZoneShadow",
      "install_script": "setup/install-retest-zone-shadow.ps1"
    },
    "config_freeze": "2026-10-30",
    "do_not": [
      "pick a grid width after reading results",
      "read the decision rule before the forward bar is met",
      "touch any trading-path file before 2026-10-30",
      "treat the in_sample:true backfill population as forward evidence"
    ]
  }
}
```

## 11. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_RetestZoneShadow
-Confirm:$false` (task not yet registered at freeze time — installer written, not run) +
delete `setup/scripts/retest_zone_shadow.py` + `setup/install-retest-zone-shadow.ps1` +
`analysis/recommendations/retest-zone-shadow-ledger.jsonl` +
`analysis/recommendations/retest-zone-shadow-summary.json` + this file. Nothing on the
trading path depends on this instrument — it is an analysis-only leaf, same class as
`Gamma_LadderRungShadow` / `Gamma_Tp1R50ForwardShadow`.
