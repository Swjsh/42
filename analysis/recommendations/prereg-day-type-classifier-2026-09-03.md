# PREREG — F5 Day-Type Classifier (paying day / tax day)

**Stamp:** 2026-09-03T11:20 ET · **Slug:** `day-type-classifier` · **Descends from:**
[`analysis/deep-research/2026-09-03-money/SYNTHESIS.md`](../deep-research/2026-09-03-money/SYNTHESIS.md)
section 2 ("the lever is a day-type discriminator known at entry time, not a stop or a
gate") and forward instrument **F5** in that document's section 3 table, plus the regime
splits documented in
[`entry-location.md`](../deep-research/2026-09-03-money/entry-location.md) (VIX<15 chase
penalty),
[`retest-entry-variant.md`](../deep-research/2026-09-03-money/retest-entry-variant.md)
(VIX-band-conditional retest edge),
[`bold-otm-tickets.md`](../deep-research/2026-09-03-money/bold-otm-tickets.md), and
[`loss-size-math.md`](../deep-research/2026-09-03-money/loss-size-math.md) (the four named
big winning days + the VIX-regime cap sweep).

**Status: RESEARCH PREREG + $0 FREE-SWARM SEED. NOT a live rule. Nothing here touches the
trading path.** This document freezes (1) the realized label definition, (2) the label
table for every session since 2026-07-01, (3) the entry-time feature list, (4) the model
class, (5) the validation protocol, (6) the ship-to-SHADOW decision rule, and (7) the
forward clock — all BEFORE any classifier is fit, per the standing eval-first discipline
(CLAUDE.md rule 11). Builder:
[`backtest/tools/day_type_labels.py`](../../backtest/tools/day_type_labels.py). Output:
[`analysis/recommendations/day-type-labels.json`](day-type-labels.json). Guard:
[`backtest/tests/test_day_type_labels_2026_09_03.py`](../../backtest/tests/test_day_type_labels_2026_09_03.py)
(12 tests). Kitchen seed:
[`strategy/candidates/_chef-inbox/2026-09-03-day-type-classifier-f5.md`](../../strategy/candidates/_chef-inbox/2026-09-03-day-type-classifier-f5.md).

**Prior art, cited not duplicated:** `backtest/tools/build_regime_early_classifier.py`
(2026-08-02, feasibility gate for an EARLY archetype classifier, walk-forward-honest,
sklearn `DecisionTreeClassifier`) and its feature module
`backtest/lib/regime_early_features.py` (the closed-bar-cutoff no-look-ahead pattern this
prereg's feature split borrows). That instrument classifies the POST-HOC `day-archetypes.
json` taxonomy (a shape label — trend/chop/pin/gap-fade). **F5 is a different target**: the
label here is the engine's own REALIZED, ARM-JOINED BOOK P&L on the current v15.3
population, not a shape archetype — genuinely new, not a duplicate of that build.
`backtest/tools/day_type_classifier.py` (2026-05-xx) is an even older heuristic day-type
tagger (TREND_FOLLOW/GAP_AND_GO/REVERSAL/CHOP from 5m bars) that was never wired to a P&L
label at all; also cited, also superseded in scope by this prereg's realized-outcome target.

---

## 1. The target label — defined from realized data

Computed by `backtest/tools/day_type_labels.py` from `automation/state/fills-ledger.jsonl`
(broker truth), **engine-attributed option fills only** (`is_option==True AND
attribution=='engine'` — excludes the small manual/crypto bycatch that carries a handful of
weekend/holiday `date_et` values in the raw ledger; see the script's own docstring for the
verification). FIFO buy/sell leg matching per `(arm, symbol, date_et)`, reproducing
`setup/scripts/tp1_r50_forward_shadow.py`'s `legs_by_activity_id` grouping contract exactly
(pinned by this prereg's own test file, not imported cross-tree).

| Label | Condition |
|---|---|
| **`paying`** | book P&L across arms (sum of realized P&L on every closed activity entered that session) **> $0** AND **at least one exit (any leg, any activity, any arm) priced ≥ 1.3× that activity's entry premium** |
| **`tax`** | book P&L **< $0** AND **every closed activity that session was a loser** (zero winners) |
| **`mixed`** | neither condition holds (e.g. book > 0 without a qualifying 1.3× exit; book < 0 with ≥1 winner; book ≈ $0) |
| **`no_trade`** | zero closed activities that session (flat day) |
| **`in_progress`** | the CURRENT trading session — **never** given a final verdict while the market is open, regardless of how many legs have already closed that day |

**Two disclosed operational approximations, both forced by a real data gap, both stated
explicitly rather than silently assumed:**

1. **"1.3× entry premium"** is the engine's own already-established edge definition
   (`setup/scripts/winner_signature.py::_mult_band`, `MEMORY.md` "Engine edge = a RIGHT
   TAIL … edge=exits ≥1.3x premium") — reused, not invented for this prereg. Evaluated
   **per leg** (max of `leg.price / entry_price` over all sell legs of an activity), not on
   a quantity-weighted average exit, so a partial TP1 that clears 1.3× still qualifies the
   day even if the runner gives some of it back.
2. **"every exit a stop"** is approximated as **"every closed activity that session lost
   money."** `fills-ledger.jsonl` and `mae-mfe.json` carry no ground-truth exit-reason tag
   (`loss-size-math.md` section 8 discloses the identical gap for its own `cap_hit` /
   `structure_or_time_loss` labels) — so a genuine stop-out cannot be distinguished from a
   time-stop or structure-stop loss. All are "a stop" for this label's purpose. This is a
   coarser statement than the literal English ("every exit was AT the configured stop
   price") but it is the only version answerable from data that actually exists, and it is
   named as an approximation here rather than silently assumed.

### 1a. Label table — every session since 2026-07-01 (n=42, from `fills-ledger.jsonl`)

| Date | Day | Book P&L | Winners/Losers/Scratch | ≥1.3× exit | Label |
|---|---|---:|---|---|---|
| 2026-07-01 | Wed | $-64.00 | 0/4/0 | N | tax |
| 2026-07-02 | Thu | $244.00 | 4/18/0 | Y | paying |
| 2026-07-06 | Mon | $-217.00 | 5/23/7 | N | mixed |
| 2026-07-07 | Tue | $-123.00 | 0/7/0 | N | tax |
| 2026-07-08 | Wed | $-382.00 | 0/12/3 | N | tax |
| 2026-07-09 | Thu | $-381.00 | 0/10/0 | N | tax |
| 2026-07-13 | Mon | $-25.00 | 0/1/0 | N | tax |
| 2026-07-15 | Wed | $-309.00 | 0/4/0 | N | tax |
| 2026-07-16 | Thu | $-83.00 | 0/4/0 | N | tax |
| 2026-07-17 | Fri | $590.00 | 7/4/5 | Y | paying |
| 2026-07-20 | Mon | $-141.00 | 0/5/0 | N | tax |
| 2026-07-21 | Tue | $-76.00 | 1/2/1 | N | mixed |
| 2026-07-22 | Wed | $-108.00 | 0/3/0 | N | tax |
| 2026-07-23 | Thu | $-305.00 | 0/1/0 | N | tax |
| 2026-07-27 | Mon | $-828.00 | 0/7/0 | N | tax |
| 2026-07-28 | Tue | $-346.00 | 1/4/0 | N | mixed |
| 2026-07-29 | Wed | $1,341.00 | 6/0/0 | Y | paying |
| 2026-07-30 | Thu | $-275.00 | 0/2/0 | N | tax |
| 2026-07-31 | Fri | $121.00 | 2/1/0 | Y | paying |
| 2026-08-03 | Mon | $534.00 | 4/0/0 | Y | paying |
| 2026-08-04 | Tue | $3,624.00 | 11/18/0 | Y | paying |
| 2026-08-05 | Wed | $-1,935.00 | 1/13/0 | Y | mixed |
| **2026-08-06** | Thu | $1,465.00 | 3/1/0 | Y | **paying** (anchor) |
| 2026-08-07 | Fri | $-2,687.00 | 0/14/0 | N | tax |
| 2026-08-10 | Mon | $-758.00 | 1/8/0 | Y | mixed |
| 2026-08-11 | Tue | $43.00 | 7/10/0 | Y | paying |
| 2026-08-12 | Wed | $-890.00 | 12/26/2 | Y | mixed |
| **2026-08-13** | Thu | $1,748.00 | 9/8/0 | Y | **paying** (anchor) |
| 2026-08-14 | Fri | $-1,837.00 | 0/12/0 | N | tax |
| 2026-08-17 | Mon | $124.00 | 1/4/0 | Y | paying |
| 2026-08-18 | Tue | $162.00 | 2/0/0 | Y | paying |
| 2026-08-19 | Wed | $266.00 | 4/8/2 | Y | paying |
| 2026-08-20 | Thu | $811.00 | 6/3/0 | Y | paying |
| 2026-08-21 | Fri | $-585.00 | 6/12/0 | Y | mixed |
| 2026-08-24 | Mon | $-57.00 | 0/3/0 | N | tax |
| 2026-08-25 | Tue | $-220.00 | 0/3/0 | N | tax |
| 2026-08-26 | Wed | $39.00 | 1/0/0 | N | mixed |
| **2026-08-27** | Thu | $1,897.00 | 9/4/0 | Y | **paying** (anchor) |
| **2026-08-28** | Fri | $1,304.00 | 4/7/0 | Y | **paying** (anchor) |
| 2026-09-01 | Tue | $78.00 | 1/2/0 | Y | paying |
| 2026-09-02 | Wed | $-699.00 | 1/11/0 | Y | mixed |
| 2026-09-03 | Thu | $-388.00 | 3/9/0 | Y | **in_progress** (market open at build time) |

**Counts: 16 paying / 16 tax / 9 mixed / 1 in_progress (n=42).** All four named anchor
winning days (`loss-size-math.md` section 5) land `paying`, verified as a hard-coded sanity
check both in the builder's own printed output and in
`test_named_anchor_days_are_paying_on_real_ledger`. This is a necessary consistency check
(the labels must agree with the days the whole money-audit is protecting), not itself
evidence the label definition is "correct" — the label is definitional, not fit to the data.

**Missing dates:** `core-decisions.jsonl` shows zero fills-ledger activity on 2026-07-10 and
2026-07-11 despite the engine being live those days (0 entries, not a data gap — both dates
appear in `core-decisions.jsonl`'s own tick history). Correctly absent from the label table
under this definition (a `no_trade` day would only appear if it had zero closed
activities AND appeared in `fills-ledger.jsonl` at all; these two dates never generated a
single fill row, so they never entered the by-date grouping in the first place — disclosed
here rather than silently unaccounted for).

---

## 2. Frozen feature list — computable with NO look-ahead

Two buckets, split by when each quantity is actually knowable — **the one load-bearing
assumption this prereg resolves explicitly** (stated once, here, not re-litigated per
feature): the task's own feature list mixes quantities knowable at the 09:35 ET entry gate
with the 09:30–09:45 opening range, which by definition is not closed until 09:45. Rather
than silently picking one cutoff for everything (which would either look ahead on the OR
features or throw away the overnight features), the list is frozen as two snapshots a
classifier build can join on `date`:

### 2a. `features_0935` — knowable by the 09:35 ET entry gate

| Feature | Definition | Coverage (of 42 sessions) |
|---|---|---|
| `overnight_gap_dollars` / `overnight_gap_pct` | today's 09:30 tick SPY − prior session's last SPY tick | 42/42 |
| `prior_day_range_dollars` | prior session's max SPY tick − min SPY tick | 42/42 |
| `vix_level_0935` | VIX at the last core-decisions tick at/before 09:35 | 42/42 |
| `vix_overnight_change` | `vix_level_0935` − prior session's last VIX tick | 42/42 |
| `vix_5d_slope` / `vix_20d_slope` | OLS slope of the trailing 5 / 20 prior sessions' closing VIX (full `core-decisions.jsonl` history back to 2026-06-25 used for the trailing window, even though the label table itself starts 07-01) | 42/42 (n_points disclosed per row; early sessions have fewer than 20 trailing points and are honestly reported as such, never padded) |
| `day_of_week` | from the date | 42/42 |
| `event_calendar_flag` (+ severity) | from THAT tick's own `context_bundle.events.next_event_et/severity` — **not** `automation/state/news.json`, which is a today-only snapshot with no historical answer | 31/42 (context_bundle v1.1 shipped 2026-07-15; sessions before that carry no bundle, `null` not fabricated) |
| `es_spy_premarket_trend` | frozen `null` | 0/42 — **no cached ES/premarket-futures bar series exists anywhere in this repo** (verified this build: `find . -iname '*es_futures*'` and `*premarket*` return only logs/docs, never a bar cache). Kept in the frozen list per the task brief's "if cached" qualifier; a future session that adds an ES cache can backfill this column without reopening the prereg. |

### 2b. `features_0945` — knowable once the opening range has closed

| Feature | Definition | Coverage |
|---|---|---|
| `opening_range_width_dollars` | max SPY tick − min SPY tick over `09:30 ≤ t < 09:45` (15 one-minute ticks; the 09:45 tick itself is excluded — same closed-bar convention as `regime_early_features.bars_through_cutoff`) | 40/42 |
| `opening_range_position_vs_prior_range` | `(OR midpoint − prior day low) / prior day range` | 40/42 |
| `first_15min_ribbon_flips_count` | count of `ribbon` (BULL/BEAR) transitions across the same 15-tick window | 40/42 |

(2 of 42 sessions have `< 2` core-decisions ticks in the 09:30–09:45 window — a feed gap,
not fabricated — and carry `null` for this bucket.)

**No-look-ahead guarantee is structural, not a runtime check**: `_features_0935_from_ticks`
and `_features_0945_from_ticks` each receive an ALREADY-SLICED tick list from their single
call site in `build_features()` — mirroring `regime_early_features.early_features`'s
"reduce over whatever you're handed, no cutoff parameter" contract. Proven by
`test_features_0935_ignores_tick_dated_after_cutoff` (plants a corrupted tick timestamped
09:40 with insane spy/vix/ribbon values on the same date and asserts the computed 09:35 row
is byte-identical with and without it) and `test_features_0945_opening_range_and_ribbon_
flips` (same technique at the 09:45 boundary).

---

## 3. Frozen model class

**Two forms only, both deliberately simple given n=32 non-`mixed`/`no_trade`/`in_progress`
labeled sessions (16 paying + 16 tax) to train against:**

1. **Single-split rule** — one threshold on ONE feature from section 2 (e.g. "stand down if
   `vix_20d_slope > X`"). 2 leaves.
2. **Depth-2 decision tree** — at most 2 splits (≤4 leaves) over the frozen feature
   vocabulary, `sklearn.tree.DecisionTreeClassifier(max_depth=2, class_weight="balanced")` —
   same library already installed and used for the same class of problem in
   `build_regime_early_classifier.py` (no new vendor/dependency risk, per CLAUDE.md's
   cost-effectiveness gate).

**Explicitly OUT of scope**: any ensemble (random forest, boosting), any depth beyond 2, any
model that is not directly inspectable as a small set of threshold rules. The reason is
disclosed, not just asserted: at n≈32 usable-labeled sessions, anything with more capacity
than a depth-2 tree is overfitting risk dressed as sophistication, and the whole point of
this instrument is a rule J or a future session can read and reason about, not a black box.

---

## 4. Frozen validation protocol

**Leave-one-week-out (LOWO) cross-validation** — no ready-made harness for this exact fold
structure exists in this repo (confirmed by inspection: the two existing "WF" patterns are
either a single fixed IS/OOS date-split PF ratio, `setup/scripts/vix_floor_shadow.py::
summarize`, or the fixed 4-calendar-window G4 gate; neither is a rolling week-level fold).
This protocol is frozen fresh here, reusing the established **`WF >= 0.70`** threshold
(CLAUDE.md OP-11 / `vix_floor_shadow.py`'s own naming) and the go-live gate's own bootstrap
PF criterion (`setup/scripts/go_live_gate.py::bootstrap_pf_ci`, day-resampled percentile
bootstrap, `ci_lower_2.5 > 1.0`) rather than inventing new statistics:

1. Partition the labeled sessions (`paying` + `tax` only — `mixed`/`no_trade`/`in_progress`
   sessions are never used to fit or score a candidate, since the classifier's job is to
   separate the two extremes, not adjudicate the ambiguous middle) into ISO calendar weeks.
2. For each week `w` held out in turn: fit the candidate rule/tree on every OTHER week's
   sessions, then apply it OUT-OF-FOLD to week `w`'s sessions.
3. A fold "succeeds" if, on that held-out week: (a) it never predicts stand-down on a
   session that is one of the 4 named anchor days (if one falls in `w`), and (b) its
   stand-down/trade split moves in the correct direction (blocks a higher share of that
   week's `tax` sessions than `paying` sessions).
4. **`WF`** = fraction of folds that succeed. Ship-eligible requires `WF >= 0.70`.
5. **OOS positive**: pool every held-out fold's `trade`-predicted sessions' actual entries
   (from `fills-ledger.jsonl`) and run `go_live_gate.bootstrap_pf_ci` (day-resampled,
   `n_boot=20000`) over their daily P&L. Ship-eligible requires `ci_lower_2.5 > 1.0` — the
   SAME criterion the go-live gate itself uses, not a softer bar invented for this instrument.
6. **Sub-window stability**: no single held-out week may account for more than 50% of the
   pooled OOS P&L (mirrors the existing `sub_window_stable` convention's concentration
   check).

---

## 5. Frozen ship-to-SHADOW decision rule

A candidate classifier (single-split or depth-2 tree, per section 3) ships to **SHADOW ONLY**
— never live, per the standing config freeze until 2026-10-30 — if and only if, on the
pooled leave-one-week-out OOS folds:

- **Keeps all four named anchor days `paying`**: zero of `2026-08-06` / `2026-08-13` /
  `2026-08-27` / `2026-08-28` is ever predicted stand-down in ANY fold where its week is
  held out.
- **Removes ≥ 50% of tax-day entries OOS**: of all closed activities that occurred on
  ACTUAL `tax`-labeled sessions across the pooled OOS folds, at least half occurred on a
  session the classifier predicted stand-down for (session-level flag — a day's entries are
  either all skipped or none are, since day-type is one flag per session, so this is
  equivalent to "the classifier's stand-down sessions cover ≥50% of total tax-session entry
  count, weighted by entries-per-session, not by session count").
- Clears `WF >= 0.70` and the go-live-gate `ci_lower_2.5 > 1.0` PF criterion from section 4.

**Reaching this bar is permission to build the SHADOW forward clock, not to ship live** —
identical framing to `tp1_r50_forward_shadow.py`'s own decision rule ("reaching the bar is
permission to READ the verdict, not to ship").

---

## 6. Frozen forward clock

**No classifier exists yet as of this prereg** — section 3–5 freeze the rules a FUTURE
classifier-fit session must follow; this prereg does not fit one. Once a candidate is
actually selected and frozen (a distinct future build, out of this task's scope), a forward
shadow ledger — same append-only, day-clustered-bootstrap-CI pattern as
`tp1_r50_forward_shadow.py` / `day_throttle_shadow.py` — begins accruing FROM THAT FREEZE
DATE, with **no backfill**. The bar for any ship-consideration read of that forward ledger
is **≥ 20 forward trading sessions after the freeze date** (matching the go-live gate's own
"smallest measurement that settles it" convention, `analysis/go-live-gate.json`), scored
strictly on sessions the classifier had never seen at fit time.

---

## 7. What this prereg deliberately does NOT do

- Does not fit, select, or rank any classifier — that is Kitchen/Chef's job, seeded per
  section 8 below, following sections 3–5 exactly as frozen.
- Does not touch `automation/state/**`, `journal/**`, or any trading-path file (read-only on
  all of the above; writes only its own output files).
- Does not soften or re-derive the `WF >= 0.70` / `ci_lower_2.5 > 1.0` bars after seeing this
  build's own label counts (16/16/9/1) — they were fixed by existing project convention
  (section 4), not chosen to make this population's numbers look good.
- Does not claim the 1.3×/every-exit-a-stop operationalizations are the ONE correct reading
  of "paying"/"tax" — they are the most literal, defensible reading of the task's own
  English given the fields that actually exist in `fills-ledger.jsonl`, disclosed as
  approximations in section 1, not asserted as ground truth.

---

## 8. Kitchen seed — CORRECTED 2026-09-03T11:40 ET (original text below was wrong)

**The original version of this section claimed the `_chef-inbox` file alone was picked up by
"the free swarm (Chef / Kitchen daemon)... per `markdown/infra/KITCHEN-SPEC.md`'s... contract"
— that was false, and the KITCHEN-SPEC.md sentence it implied ("Chef picks up inbox items") is
not a direct quote of anything in that file.** `KITCHEN-SPEC.md` documents ONE intake for the
24/7 automated daemon: `automation/state/cook-queue.jsonl`, populated by
`setup/scripts/kitchen_seeder.py` or `python setup/scripts/kitchen_daemon.py enqueue`.
`Gamma_KitchenDaemonKeepalive` / `kitchen_daemon.py` never reads `_chef-inbox/` — that
directory is a *separate*, human/Chef-persona-triggered path (`.claude/agents/chef.md`, picked
up via the wake-protocol conductor loop's Stage-1 priority-5 rail,
`automation/prompts/conductor.md` ~line 106), not the automated free-swarm.

**TRUE routing, both filed 2026-09-03:**

1. **Primary — automated 24/7 free swarm.** A `cook-queue.jsonl` task was enqueued via the
   daemon's own CLI: `python setup/scripts/kitchen_daemon.py enqueue --task "..." --priority
   high --source claude`, producing task_id `79d2384f-ee1c-4f71-bec6-57b7311a148e` (created
   2026-09-03T15:42:35Z, `automation/state/cook-queue.jsonl`). This is what
   `Gamma_KitchenDaemonKeepalive` actually picks up on its normal 5-minute-poll cadence. The
   task text points at this prereg + the frozen feature list + `day-type-labels.json`, with an
   explicit disclosure that a free-LLM `llm_cook` pass drafts a candidate rule/tree + reasoning
   only — it cannot literally execute sklearn/LOWO-CV code (`kitchen_daemon.py`'s `llm_cook`
   task type always writes a text completion to `strategy/candidates/*.md` via
   `_write_candidate`; it never runs Python). The real coded LOWO-CV fit is a follow-up
   Claude/engineering task, not something this cook mechanism can produce on its own.
2. **Secondary — human/Chef-persona-triggered, manual only.** The inbox item at
   [`strategy/candidates/_chef-inbox/2026-09-03-day-type-classifier-f5.md`](../../strategy/candidates/_chef-inbox/2026-09-03-day-type-classifier-f5.md)
   was rewritten (2026-09-03) into the canonical `_chef-inbox` format (`# Chef Inbox — <title>`
   H1 + `**Routed by:**`/`**Priority:**`/`**Category:**`/`**Source:**` metadata +
   `## The Finding` / `## Research Question for Chef` / `## Backtest Request` /
   `## Files for Reference` / `## Priority / Dependencies` ending `depends:... :: status:
   pending`, per `strategy/candidates/_chef-inbox/README.md`'s documented format) — its
   original non-canonical shape was unreadable by the `chef` agent's intake convention. This
   path only fires when the `chef` agent or the conductor wake-loop explicitly picks it up; it
   is not automatic in the way path 1 is.

**No scheduled task was added for either path** — the daemon's existing keepalive/seeder and
the conductor's existing wake-protocol cover both without new automation surface.
