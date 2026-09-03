# Chef Inbox — F5 Day-Type Classifier (paying day / tax day)

**Routed by:** Gamma (F5 money-audit forward-instrument build) 2026-09-03
**Priority:** HIGH
**Category:** New setup / day-type stand-down gate (research only, SHADOW-only per prereg)
**Source:** `analysis/deep-research/2026-09-03-money/SYNTHESIS.md` forward instrument F5 +
`analysis/recommendations/day-type-labels.json` (16 paying / 16 tax / 9 mixed / 1 in_progress,
n=42 sessions since 2026-07-01)

> **Format note (2026-09-03):** this item was originally filed in a non-canonical shape that
> the Kitchen daemon's automated intake cannot read — rewritten into the canonical format
> below, per `strategy/candidates/_chef-inbox/README.md`. **This inbox item is a SECONDARY,
> human/Chef-persona-triggered pathway only.** The PRIMARY, automatic 24/7 free-swarm seed for
> this research item is a `cook-queue.jsonl` task enqueued via
> `python setup/scripts/kitchen_daemon.py enqueue` (task_id `79d2384f-ee1c-4f71-bec6-57b7311a148e`,
> priority high, source claude, ts 2026-09-03T15:42:35Z) — that task is what
> `Gamma_KitchenDaemonKeepalive` actually picks up on its normal cadence. This file exists for
> the separate, manually-invoked `chef` agent / wake-protocol Stage-1 priority-5 pickup.

## The Finding

`SYNTHESIS.md` (the 10-hypothesis money-leak audit, 2026-09-03) found no single broken
entry/exit knob after four losing sessions — every candidate (entry-location chase filter,
retest zone width, catastrophe-cap tightening) fails on drop-best-day sensitivity or kills one
of the four named anchor winning days (2026-08-06, 2026-08-13, 2026-08-27, 2026-08-28). Its own
conclusion: **"the same breakout entry that pays +$1,500-3,000 on a fast one-directional day is
stopped at -50% or by a 4-cent structure breach on a chop/reversal day, and no filter we can
compute at entry separates the two day types yet."** Three independent hypothesis reports point
at the same gap from different angles (H1's VIX<15 chase penalty, H10's VIX-band-conditional
retest edge, H4's orphan-band winner-kill) — the missing lever is a DAY-TYPE discriminator, not
a per-trade filter.

`backtest/tools/day_type_labels.py` (new this session) already built the realized label table:
of 42 sessions since 2026-07-01, 16 are `paying` (book P&L > 0 AND >=1 exit >=1.3x entry
premium) and 16 are `tax` (book P&L < 0 AND every closed activity that session lost money) — a
near-even split, meaning a working discriminator has real leverage if one exists.

## Research Question for Chef

Can a **single-split rule or depth-2 decision tree** (no larger model class — the frozen prereg
explicitly forbids ensembles/boosting/deeper trees at this sample size), fit on the frozen
feature list below, separate `paying` from `tax` sessions with enough out-of-sample selectivity
to be worth building a live day-type stand-down gate around?

**Frozen feature list** (full definitions + no-look-ahead disclosure in the prereg section 2 —
DO NOT invent additional features or substitute a different one without re-freezing):
`features_0935`: overnight_gap_dollars, overnight_gap_pct, prior_day_range_dollars,
vix_level_0935, vix_overnight_change, vix_5d_slope, vix_20d_slope, day_of_week,
event_calendar_flag (+severity). `features_0945` (opening range only closes at 09:45, so these
join one snapshot later, never used at 09:35): opening_range_width_dollars,
opening_range_position_vs_prior_range, first_15min_ribbon_flips_count.
`es_spy_premarket_trend` is in the list but frozen `null` — no cached ES/premarket series
exists in this repo; leave it null, do not fabricate a value from another source.

## Backtest Request

- **Data**: `analysis/recommendations/day-type-labels.json` — read the `sessions` array
  directly; each row already carries `label`, `features_0935`, `features_0945`. Do not
  re-derive labels or features from the raw ledgers; if the JSON looks stale, re-run
  `python backtest/tools/day_type_labels.py` (idempotent, ~1 second, $0) rather than
  hand-computing.
- **Population for fitting**: `label in {"paying","tax"}` only (n=32). Never fit or score
  against `mixed`/`no_trade`/`in_progress` rows.
- **Validation**: leave-one-week-out cross-validation exactly as specified in prereg section 4
  (WF >= 0.70 over held-out weeks, go-live-gate bootstrap PF ci_lower_2.5 > 1.0 pooled across
  held-out folds, no single held-out week > 50% of pooled OOS P&L). This is a NEW fold
  structure — no existing harness in this repo implements it; build it fresh, matching the
  definitions in prereg section 4 word for word.
- **Ship rule** (prereg section 5): a candidate only becomes SHADOW-eligible if it (a) never
  predicts stand-down on 2026-08-06/08-13/08-27/08-28 in any fold, (b) removes >=50% of
  tax-day entries OOS (entry-weighted, not session-count-weighted), and (c) clears WF>=0.70 and
  the PF CI-lower criterion. **A candidate that fails any of these is a negative result worth
  reporting, not a reason to loosen the bar** — write it up either way.
- **Output**: append a report stating the fitted rule/tree, its LOWO fold results, and whether
  it clears the ship rule. If nothing clears the bar, say so plainly — a null result here is
  real information (it would mean the day-type tax is not separable from entry-time-known
  features at all, which is itself worth knowing per SYNTHESIS.md section 4's open question).
  **A free-LLM `llm_cook` pass cannot literally execute sklearn/LOWO-CV code** — it can only
  draft the candidate + reasoning; the actual coded fit + validation run is a follow-up
  Claude/engineering task (same caveat is stated in the cook-queue task text above).

## Files for Reference

- Frozen prereg (read first, sections 3-5 are FROZEN, do not re-derive or loosen):
  `analysis/recommendations/prereg-day-type-classifier-2026-09-03.md`
- Label table: `analysis/recommendations/day-type-labels.json`
- Guard: `backtest/tests/test_day_type_labels_2026_09_03.py`
- `backtest/tools/build_regime_early_classifier.py` (2026-08-02) — walk-forward-honest early
  classifier for the POST-HOC `day-archetypes.json` taxonomy (a different, shape-based target).
  Reuse its walk-forward-honesty discipline and its choice of
  `sklearn.tree.DecisionTreeClassifier` (already installed, no new dependency); do NOT reuse its
  target variable — F5's target is realized book P&L, not an archetype label.
- `backtest/lib/regime_early_features.py` — the closed-bar-cutoff no-look-ahead convention this
  prereg's `features_0935`/`features_0945` split borrows.
- `backtest/tools/day_type_classifier.py` (2026-05) — an older TREND_FOLLOW/GAP_AND_GO/
  REVERSAL/CHOP heuristic tagger from 5m bars, never joined to a P&L label. Superseded in scope
  by this prereg's realized-outcome target; not reused directly.
- `loss-size-math.md` section 5 — the four named big winning days table (source of the
  anchor-day constraint in the ship rule).
- `setup/scripts/tp1_r50_forward_shadow.py` — the forward-shadow-clock PATTERN this
  instrument's eventual forward stage (prereg section 6, not built yet) will follow.

## Priority / Dependencies

depends: `analysis/recommendations/prereg-day-type-classifier-2026-09-03.md` sections 3-5
(model class, validation protocol, ship rule are FROZEN — do not re-derive or loosen) ::
status:pending
