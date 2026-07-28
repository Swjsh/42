# LEVELS-V2 RETRO — do correct (shelf-augmented) levels change the engine's answer?

<!-- ============================ PRE-REGISTRATION (FROZEN) ============================
     Written 2026-07-27 ~23:58 ET, BEFORE any run of the harness. Nothing above the
     RESULTS-BELOW marker may be edited after the first full-window run. -->

## Pre-registration (frozen before run)

**Context.** Tonight's fix (7b4aa3f4) gave the LIVE engine SIP premarket + weighted/zoned
levels + shelf detection (`setup/scripts/daily_context.py`). The 2026-07-27 incident showed
the live premarket-high level was garbage (one 80-share IEX print). Question for the 390-day
history: **was level data quality the binding constraint, or not?** A null here is important —
it would say data quality was NOT the binding constraint historically (the replay's OHLC-derived
levels were already good enough), and the money is elsewhere.

**Hypothesis (H1).** With shelf-augmented levels — shelf zones computed as-of-date, no
look-ahead, from daily OHLC strictly before each session — the engine's level-tied triggers
fire on more of the profitable rejection days, and its entries walked through the real exit
core improve on the baseline's day-set.

**Null (H0).** The augmented level set changes few or no entries, or changes them without
improving P&L — i.e., historical level quality was not the binding constraint.

**Control lane.** The binary engine full-history replay, byte-identical machinery to
`backtest/tools/ladder_fullhist_replay.py`'s BASELINE lane: `run_backtest(**SAFE_BASE_LIVE)`
(`elite_bear_level_reject_gate_ab.SAFE_BASE` + `initial_equity=1746.75`) over 2025-01-02..
2026-07-27, entries' raw `dollar_pnl` discarded, exits re-derived via
`backtest/lib/exit_manager_walk.walk_exit_manager` under `strategies.py#RIBBON_RIDE.exit`
(structure-stop enabled, time stop 15:40 ET). **Calibration gate:** the control MUST reproduce
the pinned baseline from `analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json`
(n=191 trades, total +$5,306.95, WR 0.2984) or the run aborts — no treatment numbers are
reported over a broken control.

**Treatment lane.** Identical machinery, identical config, identical data. The ONLY change:
`lib.orchestrator._detect_from_history` is wrapped (monkeypatch, restored in `finally`) so
that each session D's per-day level set is augmented with shelf-zone points:

- Shelf zones per session D: `daily_context._find_shelf_candidates` +
  `daily_context._merge_shelf_candidates` (imported read-only from `setup/scripts/
  daily_context.py`, module defaults frozen: band width $1.60, >=3 touches, >=10-session
  span), run on daily OHLC bars aggregated from the cached 5m RTH bars (09:30-16:00),
  **dates in [D - 60 calendar days, D) — strictly before D. No bar of day D contributes.**
- Each merged zone [lo, hi] contributes THREE candidate points: lo, mid=(lo+hi)/2, hi
  (rounded to cents). Levels are zones (J doctrine 2026-07-17); edges+mid is the minimal
  point representation the engine's point-level triggers can consume. ONE mapping,
  pre-registered here — no band/width/point grid will be run.
- **Strictly additive:** a candidate point within $0.05 (the level-set dedupe tolerance) of
  an existing base level is NOT added; base levels are never moved or removed. Added points
  go to BOTH `active` and `multi_day` (they derive from >=10-session structure, i.e.
  multi-day by construction — this makes them eligible for the `confluence` trigger).

**Known scope facts, stated up front (not post-hoc excuses):**
- Production Safe config has `block_level_rejection=True` — a NEW bare LEVEL-tier
  `level_rejection` cannot enter. Treatment effects flow through: tier upgrades
  (confluence with a shelf multi-day level), changed `rejection_level` selection (changes
  the structure-stop anchor), level-state/sequence effects, and the bull side
  (`enable_bullish=True`). This is deliberate: the question is whether correct levels change
  THE PRODUCTION ENGINE's answer, not a hypothetical ungated engine's.
- Live `daily_context` runs on SIP daily bars and includes today's forming bar in its
  break/backside-retest state; the retro treatment uses 5m-RTH-aggregated dailies and
  excludes day D entirely (no look-ahead). Shelf coverage ramps in from ~mid-Jan 2025
  (a shelf needs a >=10-session span of history; the cached window starts 2025-01-02).
- Both lanes inherit run_backtest's own entry convention (entry fills on the bar after the
  trigger bar, per markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md) and
  walk_exit_manager's point-sample-at-open exit convention — identical across lanes, so
  convention subtleties cancel in the comparison.
- Real OPRA fills only in P&L (C1). Entries whose contract has no cached OPRA bars are
  excluded and COUNTED per lane (`n_excluded_no_opra`); if the treatment's exclusion count
  materially exceeds the control's, that participation gap is reported as a caveat.

**Held-out.** Last ~25% of the window by date (cutoff 2026-03-06, same as
LADDER-FULLHIST-2026-07-27), touched once, reported separately, never used to tune anything.

**Metrics reported regardless of outcome:** per lane — n trades, total P&L, WR, avg/trade,
max DD, n entry-days ("trigger-days"), day-majority, survives-drop-best, held-out row.
Cross-lane — day-set diff (days gained / lost / shared, with P&L), paired daily P&L deltas,
n trades identical/new/lost/shifted, shelf-attribution (treatment entries whose
rejection_level is one of the added shelf points), per-day added-level counts.

**Pass bar (SHIP-signal), all four required:**
1. treatment total P&L (real OPRA fills) > control total P&L;
2. of the days where the two lanes' daily P&L differ, the majority favor treatment;
3. the improvement survives dropping the single best treatment-only (new) trade;
4. treatment held-out (last 25%) total P&L >= control held-out total P&L.

**Declared NULL** if the treatment changes fewer than 5 trades or the day-sets are
essentially identical (answer: data quality was not binding historically). **Declared HARMFUL**
if treatment aggregate < control aggregate. One treatment vs one control — no search, no BH
correction needed; this is a single pre-registered A/B.

**Runner:** `backtest/tools/levels_v2_retro_ab.py` (new, analysis-only). Raw output:
`analysis/deep-research/LEVELS-V2-RETRO-2026-07-28.json`.

<!-- RESULTS-BELOW -->

## RESULTS — generated 2026-07-27T22:16:00.316038 (runner `backtest/tools/levels_v2_retro_ab.py`, runtime 159.3s)

### Verdict: **HARMFUL** (improvement -$466.60)

| Lane | N trades | Total P&L | WR | Avg/trade | Max DD | Entry-days | Day-majority | Drop-best | Held-out (last 25%) | No-OPRA excluded |
|---|---|---|---|---|---|---|---|---|---|---|
| **CONTROL (baseline levels)** | 191 | +$5,306.95 | 0.2984 | +$27.79 | -$2,233.40 | 142 | 49/142 (False) | +$4,447.00 (True) | 58tr +$1,548.40 | 18 |
| **TREATMENT (shelf-augmented)** | 184 | +$4,840.35 | 0.3098 | +$26.31 | -$1,955.60 | 141 | 50/141 (False) | +$3,980.40 (True) | 60tr +$1,273.05 | 19 |

### Control calibration vs pinned LADDER-FULLHIST-2026-07-27 baseline

- Reproduced: n=191 total=+$5,306.95 WR=0.2984 | Pinned: n=191 total=+$5,306.95 WR=0.2984 | **match=True**

### Pre-registered pass-bar gates

1. Treatment beats control on total P&L: **False**
2. Majority of changed days favor treatment: **False** (24/50 changed days positive)
3. Survives dropping best NEW trade (+$583.10): **False** (improvement minus best-new = -$1,049.70)
4. Held-out not worse: **False** (treatment +$1,273.05 vs control +$1,548.40)

### What actually changed

- Trades identical across lanes: 148 | new in treatment: 36 | lost from control: 43
- Entry-days: control 142 vs treatment 141 (shared 130; gained 11 days worth -$93.65; lost 12 days that had -$815.40 in control)
- Treatment entries whose rejection_level IS an added shelf point: 34 (+$1,177.05)
- Shelf coverage: 373/390 sessions had >=1 as-of-date shelf zone (mean 9.02 zones, mean 25.56 added points/day; 0 days had zones but zero NEW points after the $0.05 additive gate)

_Full per-trade / per-day detail: `analysis/deep-research/LEVELS-V2-RETRO-2026-07-28.json`._

### Honest read

**Correct levels do NOT change the answer.** All four pre-registered gates FAIL. The
classification is HARMFUL by the frozen rule (improvement < 0 with >=5 trades changed), but
the honest effect size is **indistinguishable from zero**: -$466.60 across 390 days
(-$1.20/day), 24-vs-26 on changed days (a coin flip), and the whole deficit fits inside ONE
changed day (excluding the single worst delta day, 2026-02-23 at -$617.80, the improvement
is +$151.20). Treatment WR is slightly HIGHER (0.3098 vs 0.2984) and max DD slightly
SHALLOWER (-$1,955.60 vs -$2,233.40) — the level augmentation is not poison, it is noise.

Mechanics of the change, for the record:
- The 36 NEW entries the shelf points created summed to **-$1,982.05** — dominated by
  confluence+level_rejection (10) and confluence+level_reclaim+ribbon_flip (9; the known
  C28 lagging-entry pattern). The 43 LOST entries (displaced via NOT_FLAT/quality-lock
  cascades, C15) summed to -$1,346.60 — the engine gave up bad trades too. Net wash.
- The descriptive slice of treatment entries that fired exactly AT an added shelf point
  (n=34, +$1,177.05) looks healthy, but most of them replaced near-identical control
  entries at nearby base levels — it is not incremental money.

**Answer to the lane question:** historical level data quality was NOT the binding
constraint on the 390-day replay. The 2026-07-27 defect (premarket high from one 80-share
IEX print) is a LIVE-feed provenance problem — worth the fix it already got (7b4aa3f4) —
but retrofitting shelf-quality levels into the same engine gates does not move the
historical P&L. The binding constraint on the engine's median -$63 day is elsewhere
(entry/exit selection on the days it already fires — see the trigger-class-split open
question in the 2026-07-23 scorecard), not in the level feed.

