# PRE-REGISTRATION — SHELF_HOLD_RECLAIM full-population study (WS5, weekend main event)

**Frozen:** et_clock `2026-08-01 12:45:56 Saturday EDT` (market_hours=False), stamped and committed
BEFORE the runner `backtest/tools/shelf_hold_reclaim_study.py` exists. Freeze order is
git-provable: this file's commit precedes the runner's first commit and any run output.

**Parent spec (followed faithfully):** `analysis/deep-research/J-CALLED-ENTRIES-2026-07-31.md` §5
candidate detector spec `shelf_hold_reclaim`. This study is that spec's Lane-B validation.

---

## 1. Hypothesis (falsifiable, written before any run)

**H1 (primary):** Entering LONG on the DEFENDED TOUCH of a persistent multi-session shelf
(w5 anchor class) — via wick-defense (geometry A) or touch-and-hold (geometry B) — has positive
aggregate P&L and positive per-trade expectancy on real OPRA fills over the full 391-day
population, under the engine's own registry exit shape.

**H2 (dose-response, the J question):** the EARLY defense-entry geometries each beat the LATE
close-cross confirmation on per-trade expectancy at the same anchor class:
`expectancy(A) > expectancy(C)` AND `expectancy(B) > expectancy(C)` (primary cells).
Full A/B/C ordering reported either way.

**H3 (secondary, axes not gates):** trend-stack filters F5/F8/F10 do not distinguish winners at
this anchor class (evidence: e1's refusal set {5,8,10} on a +392% MFE path; e3 passed all three).
Tested as pre-registered A/B axes, never inherited as hard blockers.

**Null outcome is a deliverable:** if no geometry clears, the graveyard entry closes J's
"enter on the defense" question with full-population numbers.

## 2. Population & data

- **Days:** RTH sessions `2025-01-02 .. 2026-07-31` — the VERIFIED 391-day population.
  Frames: `backtest/data/spy_5m_2025-01-01_2026-07-22.csv` + strictly-after-07-22 tail of
  `backtest/data/spy_5m_2026-05-19_2026-07-31.csv` (ladder_fullhist_replay `load_extended_data`
  convention, extended 07-27→07-31). VIX same construction. Actual day count reported.
- **2024 EXCLUDED:** tonight's 2024 OPRA backfill is unverified
  (`analysis/deep-research/OPRA-BACKFILL-2026-07-31.md` does not exist → hard exclusion,
  no 2024 stratum in this study).
- **Option P&L: real OPRA only** — cached contract bars `backtest/data/options/{symbol}.csv` via
  `lib.option_pricing_real.load_contract_bars`. Missing contract / missing entry print / zero
  print ⇒ row EXCLUDED and counted per cell (never synthetic). Exclusion rates reported
  per cell and window-stratified (2025H1/2025H2/2026).

## 3. Anchor class (the scope, not a knob)

Retro equivalent of live compiler-v2 `weight ≥ 5` shelves, C6-clean:

- Per session D: daily OHLC aggregated from the cached RTH 5m bars, dates in `[D−60cal, D)`
  STRICTLY before D; shelves via `setup/scripts/daily_context.py#_find_shelf_candidates` +
  `_merge_shelf_candidates` with module defaults (band $1.60, ≥3 touches, ≥10-session span).
  This is `backtest/tools/levels_v2_retro_ab.py`'s established retro feed, reused verbatim.
- **Level price = band mid** (live parity: `refresh_levels_intraday.py` shelf upsert writes
  `price=mid`, `weight=5`, `zone_width=(hi−lo)/2`, `touches`, `span_sessions`).
- **Zone floor = band_low; zone ceiling = band_high; zone_width = (hi−lo)/2** — the file's own
  zone geometry, never hand-picked (levels-are-zones, J 2026-07-17).
- **Spot filter (live parity):** only anchors with `|mid − day's first RTH open| ≤ $20`
  (SHELF_UPSERT_BAND) are active for D.
- **Disclosed scope limit:** the live w5 class also includes level-memory levels
  (`touches ≥ 3` memory entries). Memory levels are not retro-reconstructable in this harness;
  this study's anchor class = shelf-derived w5 anchors only.
- Days with zero anchors are the SKIP_NO_LEVELS analog: no entries possible; count reported.

## 4. Admission geometries (the axis under test — OR at the anchor class)

Evaluated per CLOSED 5m bar of D against the day's anchor set (existing detectors, reused —
never re-implemented):

- **A. wick-defense** = `backtest.lib.filters.detect_wick_reclaim_bullish(bar, anchor_mids)`
  with its module defaults (wick ≥ max($0.15, 50% of range), close ≥ level − $0.10).
- **B. touch-and-hold** = `filters.detect_pullback_hold_bullish(bar, day_bars, bar_idx,
  [anchor_mid], zone_band_dollars=<that anchor's own zone_width>, min_hold_bars=2,
  lookback_bars=12)`, called per-anchor. **Pre-registered deviation from the detector's $0.30
  default band:** the anchor class defines the zone; admission band and structure stop must
  share the file's own zone geometry (spec §5 "zone band = the file's own zone_width").
  Multi-anchor same-bar fire tie-break: tightest `|bar low − mid|`.
- **C. close-cross reclaim** = `filters.detect_level_reclaim(bar, anchor_mids)`
  (`low < level < close`), routed WITHOUT `block_elite_bull` (spec §5: the gate's entire
  24-fill evidence base predates the levels-v2 compiler; its own written re-eval condition is
  binding; on 07-31 it refused 111 rows of the only profitable signal class).
- **UNION** = first fire of any of A/B/C (the composite `shelf_hold_reclaim` candidate).

**Graveyard compliance (explicit):** `wick_reclaim`/`trendline_reclaim` as STANDALONE triggers
on the general level book tested NEGATIVE (2026-07-31) and stay dead. Geometry A here is NOT
that retest: it is the w5-ANCHOR-CLASS-SCOPED admission form the parent spec prescribes —
different scope (persistent shelves only), different role (admission to a dedicated lane, not a
score-contributor on the whole book). No trendline geometry appears in this study. Also not
retested: pre-TP1 trailing locks, BE-floor-fixed, exit-all-at-touch, zone-banded close-cross
detector (C is the plain live `detect_level_reclaim` at anchor mids), score ladders,
structure-shift standalone/in-cascade, take-profit-earlier, ATM-on-the-whole-book,
arm-looseness.

## 5. Filters

**Hard in every cell (spec §5 "kept hard"):**
- F1 time gates: bar time ≥ 09:35 ET and NOT in [15:00, 16:00) (SAFE_BASE live values).
- F6 ribbon spread sanity: `spread_cents ≥ 30` (RIBBON_SPREAD_MIN_CENTS).
- F9 VIX hard cap: `vix_now < 22.0`.
- Entry premium floor: fill premium ≥ $0.30 (min_entry_premium, real provenance — KEEP per
  2026-07-31 study).
- Structural no-add / one-position-at-a-time per cell (C31); SKIP_NO_LEVELS vacuously satisfied
  (entries exist only at anchors).
- F7 volume-divergence NOT applied (not in the spec's kept-hard list — disclosed).

**Pre-registered A/B axes (spec §5 "demoted"):**
- F5 ∈ {require: 5m ribbon stack == BULL · drop · htf: 15m stack != BEAR
  (via `orchestrator._precompute_htf_15m_stacks` on the continuous RTH frame)}
- F8 ∈ {on: VIX < 17.20 OR vix_direction == falling · off}
- F10 ∈ {on: close > open AND volume ≥ 0.7 × 20-bar baseline (`vol_baseline_20bar`,
  continuous RTH frame, global idx) · off}

Filter evaluation happens on the TRIGGER bar. Ribbon/VIX/volume/htf series computed on the
continuous RTH frame exactly as `orchestrator.run_backtest` does (warmup preserved across days;
VIX ffill-aligned; vix_prior = previous aligned value).

## 6. Entry / contract / sizing conventions (frozen)

- Trigger bar = the closed 5m bar the geometry confirms on. Entry tick = trigger-bar start
  + 5 min (the bar's close instant). **Fill = OPEN of the first cached OPRA 5m bar with
  `timestamp_et ≥ entry tick`** (J-CALLED-2026-07-31 convention). Exits walked STRICTLY after
  the fill timestamp — entry+1 ruling (`markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md`).
- Contract: **ATM call = round(trigger-bar close)** → nearest $1 strike, 0DTE (session D expiry).
  Direction bull only (bear mirror = separate future pre-reg, per spec).
- **qty = 3** (min-contract floor, Rule 6 — min size per the WS5 charter).
- Occupancy: while a position is open (per cell), new fires are ignored. **Occupancy is defined
  by the CONTROL-lane exit time** so both exit lanes share an IDENTICAL trade set (paired exit
  A/B; the ZONE-RIDE lane re-walks the same entries). Disclosed limitation: a real ZONE-RIDE
  policy whose exits run longer could miss later entries this pairing keeps.
- Re-entry after exit: allowed on any NEW fire (no invented re-entry locks — J 2026-07-02).

## 7. Exit lanes (registry CONTROL vs ZONE-RIDE, per spec §5)

- **CONTROL** = `automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict()` byte-identical
  (tp1_premium_pct=1.0, tp1_qty_fraction=0.667, profit_lock_mode="trailing", trail_pct=0.15,
  runner_target_pct=99.0, stop_mode="structure", catastrophe_stop_pct=−0.50). The runner
  ASSERTS byte-equality against the live registry at run time.
- **ZONE-RIDE** = CONTROL + `trail_pct=0.2` (risky-3's accounts.json exit_patch overlay).
- Both lanes: `walk_exit_manager` (the REAL `exit_manager.plan_exit_actions` core),
  `structure_stop_enabled=True`, **`trigger_level` = the fired anchor's ZONE FLOOR (band_low)**
  (spec: structure stop at zone floor), catastrophe −50% cap, `time_stop_et = 15:40`
  (live Safe `params.json time_stop_et`; NOTE the n=4 anecdote used 15:50 — this study uses
  live production value), `ribbon_tick_df` SUPPLIED via `engine_fullhist_replay.build_ribbon_lookup`
  + `ribbon_tick_df_for` (flip-back exits CAN fire — higher fidelity than the n=4 anecdote's
  disclosed df=None), `five_min_spy_df` = session D RTH frame.

## 8. Grid — ALL cells reported, none dropped

`4 geometries × 3 F5 × 2 F8 × 2 F10 × 2 exit lanes = 96 cells.`

**Primary cells (hypothesis-native, 4):** each geometry under {F5=drop, F8=off, F10=off,
exit=CONTROL} — the pure defended-touch lane with only the spec's hard filters. Everything
else is a secondary axis. No cell is a tuning knob; nothing gets re-run with different
constants after results are seen.

## 9. Gates (frozen pass bars)

A geometry SHIPS (as a shadow-scored contributor) only if its PRIMARY cell clears ALL of:

1. **Positive aggregate** total P&L > 0 on the real-OPRA filled set.
2. **Day-majority:** winning entry-days > 1/2 of entry-days.
3. **Drop-best:** total − best single trade > 0.
4. **Held-out OOS:** last-25%-of-population window (cutoff = the 294th trading day, date
   computed and reported) total ≥ 0.
5. **Recent-25-day window FIRST-CLASS** (J's dynamic-market rule 2026-07-31): reported for
   every cell (n / total / WR / expectancy). Recent-25 total ≥ 0 is REQUIRED for the
   arming-queue recommendation; a geometry positive on aggregate but negative on recent-25 may
   ship shadow-only, flagged stale-edge on the scorecard.
6. **Dose-response on the admission axis (H2):** expectancy(A) > expectancy(C) AND
   expectancy(B) > expectancy(C) among primary cells. Reported for the full ordering.
7. **BH-FDR q=0.10 across ALL 96 cells** (one-sample t on per-trade P&L,
   `pullback_hold_bull_replay` convention): the primary cell must survive.
8. **Runner-cohort no-regression:** this study is entry-additive and proposes NO exit-knob
   change to any existing lane; CONTROL byte-identity is asserted. The sacred 35-winner
   +$15,774 runner cohort is untouched by construction. Any future arming ships with the
   existing registry exit shape unchanged.
9. **Minimum evidence:** geometry needs n ≥ 15 filled trades in its primary cell for gate
   evaluation; below that the verdict is UNDERPOWERED (reported; neither ships nor graveyards).
10. **Concentration disclosure:** top-day P&L share per cell.

**Harness fidelity gate (not a cell gate) — sanity anchors from the verified 07-31 tape:**
- e1: geometry A fires 2026-07-31 with entry_ts ∈ [10:20, 10:45] at an anchor within $0.80 of 737.68.
- e2: geometry B fires 2026-07-31 with entry_ts ∈ [11:40, 12:05] at an anchor within $0.80 of 739.73.
- e3: geometry C fires 2026-07-31 with entry_ts ∈ [12:15, 12:40] at an anchor within $0.80 of 743.25.
≥2 of 3 must hit for the harness to be trusted (retro shelf zones are recomputed, not the live
curated file — small placement drift is possible and disclosed); all 3 reported with near-miss
diagnostics (nearest anchor, nearest fire) on any miss.

## 10. Statistics

- One-sample p: normal-approx t on per-trade P&L (existing `_one_sample_p` convention).
- BH-FDR: Benjamini-Hochberg q=0.10 over all 96 cell p-values (existing `_bh_fdr` convention).
- No other slicing. Any post-hoc exploratory cut is labeled DIAGNOSTIC and gates nothing.

## 11. Outcomes (pre-committed)

- **Some geometry clears all gates →** ship it as a shadow-scored contributor (additive,
  shadow-only — paper autonomy) + queue the arming decision with the scorecard at
  `analysis/recommendations/queue.jsonl` conventions.
- **All null →** graveyard entry ("shelf-hold defended-touch entries at w5 anchors — tested
  full-population, all geometries null") closing J's "enter on the defense" question with
  numbers. That is itself the deliverable.
- **UNDERPOWERED (n<15) →** reported as such; the spec's question stays open with the firing
  rate as the finding.

Artifacts: `analysis/recommendations/shelf-hold-reclaim-2026-08-01.{md,json}` (all 96 cells in
the JSON; MD = synthesis). Runner: `backtest/tools/shelf_hold_reclaim_study.py` (committed
AFTER this prereg).

*Analysis only: no live config, param, gate, or order is touched by the runner. Concurrent-lane
fence respected: no writes to crypto_twin_core.py / theta_clock.py / trades.csv writer / twin
cadence / firm_brief theta line.*
