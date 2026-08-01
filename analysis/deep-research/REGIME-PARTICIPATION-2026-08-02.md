# Regime Participation — decomposing gap-go's dominance and trend-day starvation

**Written 2026-08-02.** Decomposes the weekend's headline finding (full-history replay of the
live core-Safe engine, 2025-01-02..2026-07-22, commit df0348d9: $4,808.75 / 191 trades, gap-go
= 60.5% of ALL P&L on ~22% of days, trend-up/trend-down/V-reversal/inverted-V all n<15) into
PARTICIPATION (why so few entries on trend days) and PERFORMANCE (is gap-go's dominance edge
or a concentration artifact) — two questions, two different fixes. Ends with a ranked
candidate list and ONE frozen pre-registration. **No study was run. Nothing is armed.**

## Verdict first

- **PARTICIPATION: the engine mostly SEES trend-day setups and refuses them — it does not
  fail to generate candidates.** On trend-up/trend-down/V-reversal/inverted-V days combined
  (62 of 389 full-population days), only 1 of 62 is genuine `NO_VOCABULARY` (zero triggers all
  session). The rest split between `GATE_BLOCKED` (named filter fired) and `CORRECTLY_FLAT`
  (a trigger fired but never reached the score-8 qualifying bar).
- **`GATE_BLOCKED[filter_8]` (the VIX-regime gate) is the single largest blocker in EVERY one
  of the 8 archetypes without exception** — 121 of 389 days full-population (31.1%), oracle-bound
  +$26,547 (bear-side, single-candidate, NOT an achievable number — see caveats). It dominates
  trend-up specifically (10 of 28 days, 71% of trend-up's gate-blocks).
- **PARTICIPATION is NOT uniformly low across "trending" regimes** — trend-up participates at
  only 14.3% (4/28 days) but trend-down participates at 57.1% (8/14), close to range-chop's
  41.1% baseline. The starvation is concentrated in trend-up and, to a lesser extent,
  inverted-V (22.2%) and pin-day (19.0%) — not a blanket "trend regimes are starved" story.
- **PERFORMANCE: gap-go's edge is real, not a one-day artifact — trend-up's is the opposite.**
  gap-go's best single day is only 28.9% of its total ($841.35 of $2,911.10); drop that day and
  gap-go is still +$2,069.75. Trend-up's best single day (2026-06-11, +$752.00) is **416% of
  its own total** ($180.60) — drop that ONE day and trend-up goes **negative** (-$571.40). Same
  story for V-reversal (drop-best flips to -$54.35) and inverted-V (flips to -$24.00).
  Trend-down is the one underpowered archetype whose edge survives drop-best (+$195.05).
- **Power:** trend-up/trend-down/V-reversal/inverted-V are all n<15 trades and MUST stay
  labeled unsupportable as standalone edges. The 2024 backfill stratum (239 usable days) is
  NOT currently usable to fix this — it isn't archetype-tagged and has no engine replay yet
  (see §2). Extending it is flagged as a fast-follow, not attempted here.
- **Pre-registered:** `VIX-REGIME-GATE-ARCHETYPE-PARTICIPATION-2026-08-02`
  (`analysis/recommendations/prereg-vix-regime-gate-archetype-2026-08-02.json`, frozen
  2026-08-01 16:53:48 ET, before any run). Tests relaxing filter_8 via two ALREADY-WIRED flags
  (`vix_soft_mode=True`, `disable_filters=[8]`) against the real exit-walk methodology — the
  ONLY methodology that may be trusted here (see §4, prior "evidence" on this exact gate is
  disqualified).

---

## 1. Participation vs Performance

### 1a. PARTICIPATION — blocker histogram

Two independent sources, cross-referenced against the WS6 regime library
(`analysis/regime-library/day-archetypes.json`) by calendar date:

- **Full-population bear-side decision trace** — `backtest/tools/regime_participation_replay.py`
  (new this session), a full-population (2025-01-02..2026-07-27, 390 RTH days) extension of the
  already-validated `day_report_card.py` pipeline (same `classify_day`/`aggregate_cards`
  functions, reused not reimplemented — see §5). Bear-side (`RIDE_THE_RIBBON` bear) candidate/
  gate trace only; this is `day_report_card.py`'s own documented v1 scope limit, inherited
  unchanged. Artifact: `analysis/regime-library/participation-replay-fullhist-2026-08-02.json`.
- **Live core-decisions window** — `automation/state/core-decisions.jsonl`, filtered
  `armed==True` (task-specified: 302 of 19,625 rows carry `armed:false`, off-hours diagnostic
  noise, correctly excluded), both `safe` and `bold` core accounts, deduped into events via the
  ALREADY-TESTED `participation_cascade.build_events` (never reimplemented). Observed window:
  **2026-06-25..2026-07-31** (the ledger's own actual span — thin, ~5.5 weeks, but this IS "the
  recent window" per J's dynamic-market doctrine, reported first-class, not an afterthought).
  Both sides (bull+bear), and the ONLY source here with risk-gate visibility.

**Full-population per-archetype table** (bear-side replay; `n_days` = every calendar day of
that archetype in the 390-day window; `entered` = engine took >=1 trade that day, either side,
since `entered` comes from the engine's real trade log, not the bear-only candidate lens):

| Archetype | n_days | entered | participation rate | GATE_BLOCKED | CORRECTLY_FLAT (sub-8 trigger) | NO_VOCABULARY (zero triggers) |
|---|---:|---:|---:|---:|---:|---:|
| **trend-up** | 28 | 4 | **14.3%** | 14 | 9 | 1 |
| trend-down | 14 | 8 | **57.1%** | 5 | 1 | 0 |
| V-reversal | 11 | 8 | **72.7%** | 3 | 0 | 0 |
| inverted-V | 9 | 2 | **22.2%** | 6 | 1 | 0 |
| gap-go | 86 | 30 | 34.9% | 33 | 22 | 1 |
| gap-fade | 62 | 21 | 33.9% | 34 | 7 | 0 |
| pin-day | 21 | 4 | 19.0% | 6 | 11 | 0 |
| range-chop | 158 | 65 | 41.1% | 64 | 29 | 0 |
| **ALL (8 archetypes)** | **389** | **142** | **36.5%** | **165 (42.4%)** | **80** | **2** |

**The question the task asked crisply: seeing-and-refusing, or never-generating?** Across the
full population, only **2 of 389 days (0.5%)** are genuine `NO_VOCABULARY` — the engine almost
never fails to generate ANY candidate. The real split is `GATE_BLOCKED` (42.4% of all days) vs
`CORRECTLY_FLAT` (20.6%, a trigger fired but stayed below the score-8 qualifying bar). **The
engine is overwhelmingly SEEING setups and either blocking or under-scoring them — it is not
blind.** This holds archetype-by-archetype too, including trend-up (14 blocked + 9 sub-threshold
= 23 of 24 non-entry days had SOME signal; only 1 was truly silent).

**Modal blocker, per archetype** (`GATE_BLOCKED[filter_N]` breakdown, from the same replay):

| Archetype | Top blocker | 2nd blocker |
|---|---|---|
| trend-up | **filter_8 (vix_regime) x10** | filter_5 (ribbon_not_BEAR) x4 |
| trend-down | **filter_8 x4** | filter_9 (breakdown_bar_vol_confirm) x1 |
| V-reversal | **filter_8 x3** | — |
| inverted-V | **filter_8 x4** | filter_5 x2 |
| gap-go | **filter_8 x21** | filter_5 x12 |
| gap-fade | **filter_8 x33** | filter_9 x1 |
| pin-day | filter_6 (spread) x2, filter_8 x3 | filter_1 x1 |
| range-chop | **filter_8 x43** | filter_5 x17, filter_6 x4 |
| **TOTAL** | **filter_8: 121/389 days (31.1%), oracle-bound +$26,547.00** | filter_5: 35 days |

`filter_8` (VIX regime) is the dominant blocker in **every single archetype** — not a
trend-specific mechanism, a whole-book mechanism that happens to also explain a majority
(10/14 = 71%) of trend-up's specific gate-blocks. Oracle-bound $ figures are bear-side,
single-best-candidate, hindsight, NOT achievable — reported as a magnitude signal only, per the
`day_report_card.py` disclosure convention this reuses.

**Live window (2026-06-25..2026-07-31, armed==True, both accounts) — cross-check, not primary:**

| Archetype | days observed (safe) | dominant blocker (safe) | dominant blocker (bold) |
|---|---:|---|---|
| trend-up | 1 | block_elite_bull x6 | block_elite_bull x6 |
| trend-down | 1 | risk_deny_risk_cap x3, block_elite_bull x2 | require_bearish_fill_bar x2 |
| pin-day | 1 | block_elite_bull x4 | block_elite_bull x4 |
| V-reversal | 3 | block_elite_bull x15 | block_elite_bull x18 |
| range-chop | 9 | block_elite_bull x22 | require_bearish_fill_bar x26 |
| gap-go | 5 | block_elite_bull x8 | block_elite_bull x9, require_bearish_fill_bar x9 |
| gap-fade | 5 | min_ribbon_momentum_cents x4, structure_veto x4 | require_bearish_fill_bar x11 |

The live window shows a genuinely **different** dominant blocker — `block_elite_bull` (a
tier/cohort gate restricting bull entries to ELITE tier), not `filter_8`. This is coherent, not
contradictory: the full-population replay only instruments the BEAR candidate pipeline, so it
cannot see bull-side blocking at all; the live window sees both sides but is only 1 day deep on
trend-up/trend-down/pin-day — **anecdote-tier, not evidence-tier** (mirrors the standing
"n=1 day = ANECDOTE" convention from the 2026-07-31 filter-5 incident). `block_elite_bull` is
already another agent's claimed lane (see §4) and is flagged there, not absorbed into this
study's pre-registration.

### 1b. PERFORMANCE — is gap-go's dominance edge, or one lucky day?

Source: `analysis/recommendations/engine-fullhist-replay-2026-07-23.json` (191 real-OPRA trades,
2025-01-06..2026-07-21, the walked/priced trade log behind the $4,808.75 headline) x the
regime library. Concentration check per the task's own framing — **top-day share** = the
single best calendar day's $ as a fraction of the archetype's total; **drop-best** = does the
archetype stay positive after removing its best day/trade.

| Archetype | n trades | n days | Total P&L | WR | Avg/trade | Top day | Top-day share | Drop-best-day | Still + ? | Underpowered |
|---|---:|---:|---:|---:|---:|---|---:|---:|:---:|:---:|
| **gap-go** | 37 | 29 | **+$2,911.10** | 32.4% | +$78.68 | 2025-08-22 +$841 | **28.9%** | **+$2,069.75** | **YES** | no |
| range-chop | 86 | 65 | +$1,396.40 | 29.1% | +$16.24 | 2026-05-18 +$1,465 | **104.9%** | -$68.70 | **NO** | no |
| trend-down | 13 | 8 | +$811.05 | 30.8% | +$62.39 | 2025-02-21 +$616 | 76.0% | +$195.05 | **YES (thin)** | **yes** |
| V-reversal | 11 | 8 | +$602.50 | 36.4% | +$54.77 | 2026-01-29 +$657 | **109.0%** | -$54.35 | **NO** | **yes** |
| trend-up | 5 | 4 | +$180.60 | 20.0% | +$36.12 | 2026-06-11 +$752 | **416.4%** | **-$571.40** | **NO** | **yes** |
| inverted-V | 2 | 2 | +$156.25 | 50.0% | +$78.12 | 2025-01-06 +$180 | 115.4% | -$24.00 | **NO** | **yes** |
| pin-day | 6 | 4 | -$430.80 | 0.0% | -$71.80 | 2025-10-06 -$51 (least-bad) | n/a (loser) | -$379.80 | no (already neg.) | **yes** |
| gap-fade | 30 | 20 | -$884.35 | 26.7% | -$29.48 | 2025-12-11 +$486 | n/a (sign mismatch) | -$1,370.55 | no (already neg.) | no |

**Reading this straight: gap-go is the ONLY positive underpowered-or-not archetype whose edge
is genuinely broad-based** (29 different contributing days, drop-best still leaves 71% of the
total standing). **Every other "positive" archetype except trend-down is a single-day
artifact wearing a regime label** — trend-up, V-reversal, and inverted-V all go negative the
moment their best day is removed. Trend-down is the one exception: thin (n=13, still
underpowered) but its edge survives drop-best, making it the most credible of the four
underpowered archetypes, consistent with its much healthier 57.1% participation rate in
§1a. Range-chop (NOT underpowered by n — 86 trades) is worth a flag too: even this large
bucket is majority-carried by one day (2026-05-18) at the DAY level, though it survives
drop-best at the trade level (+$760.35) — a softer version of the same concentration risk,
noted but not this study's focus.

**Recent-25-trading-day cut** (2026-05-28..2026-07-21, the last 25 distinct dates in the trade
population — NOTE this trade log ends 2026-07-22, so this window is NOT identical to the regime
library's own last-25 window which runs through 2026-07-31; both are disclosed with their exact
dates, never silently conflated):

| Archetype | n trades | Total P&L | Avg/trade |
|---|---:|---:|---:|
| range-chop | 15 | +$988.70 | +$65.91 |
| **trend-up** | 1 | +$752.00 | +$752.00 |
| gap-go | 4 | +$615.65 | +$153.91 |
| V-reversal | 4 | -$133.00 | -$33.25 |
| trend-down | 1 | -$355.50 | -$355.50 |
| gap-fade | 7 | -$1,618.60 | -$231.23 |

Trend-up's entire recent-window trade is the SAME 2026-06-11 outlier that carries its whole
full-population total — confirms the drop-best finding two ways, not a coincidence of one cut.
Per J's standing rule (recency > aggregate), this recent cut does not change any verdict here:
gap-fade is a worse loser recently than in aggregate (disclosed, not buried), and gap-go/range-
chop hold up.

---

## 2. Honest power accounting

| Archetype | n trades (full pop) | Verdict on standalone edge claim |
|---|---:|---|
| gap-go | 37 | **Supportable.** n>=15, broad-based (§1b), matches its own 60.5%-of-P&L headline. |
| gap-fade | 30 | **Supportable as a loser.** n>=15, loss survives drop-best -- not one bad trade. |
| range-chop | 86 | **Supportable in aggregate, flag the day-level concentration** (§1b) as a caveat on how "safe" this bucket really is. |
| trend-down | 13 | **NOT supportable as a standalone edge** (n<15) but the LEAST unsupportable of the four -- edge survives drop-best and participation is healthy. Worth a targeted re-check once n grows. |
| V-reversal | 11 | **NOT supportable.** n<15 AND fails drop-best -- likely one good trade, not a regime effect. |
| trend-up | 5 | **NOT supportable, actively misleading if read naively.** n<15, single outlier day, drop-best goes negative. The "positive $180.60" headline number should never be quoted alone. |
| inverted-V | 2 | **NOT supportable, extremely thin.** n=2. Directionally noted only. |

**The 2024 backfill stratum does NOT resolve this today.** `analysis/deep-research/OPRA-BACKFILL-2026-07-31.md`
clears 239 usable 2024 trading days (2024-01-18..2024-12-31) — in principle enough to roughly
double n for every underpowered archetype. Checked before assuming it helps:

1. **The WS6 regime library does not tag 2024 at all.** `build_day_archetypes.py`'s own data
   lineage deliberately excludes it ("verified population starts 2025-01-02; feed seams are a
   known corruption source" — regime-library/README.md). No archetype labels exist for any
   2024 date today.
2. **No engine replay exists for 2024.** `engine-fullhist-replay-2026-07-23.json` stops at
   2026-07-22 going forward only; nobody has run the current gold-standard exit-walk pipeline
   backward into 2024.
3. Using 2024 here would therefore require BOTH extending the archetype tagger's lineage AND
   running a brand-new full engine replay over 239 more days — two separate, non-trivial,
   appropriately-cautious pieces of infrastructure work, not a same-session bolt-on to a
   decomposition study. Also: 2024-01-18..2024-07-30 has daily-only VIX (no intraday) —
   directly relevant here since filter_8 IS a VIX-character gate, so even after tagging+replay,
   roughly half the new 2024 days would be ineligible for any filter_8-specific analysis.

**Verdict: flagged as a legitimate fast-follow (see §3 candidate #4), not attempted this
session.** Every table above is 2025-2026 population only, honestly labeled as such.

---

## 3. Ranked candidate interventions

| # | Intervention | Specific mechanism it changes | Status |
|---|---|---|---|
| **1** | **Relax filter_8 (VIX regime gate)** via `vix_soft_mode=True` (bear-only, already wired) or `disable_filters=[8]` (both sides, already wired) | Converts the single largest blocker in every archetype (31.1% of all days, +$26,547 oracle-bound) from a hard veto to either a soft score demerit or a no-op. Zero new code. | **PICKED — pre-registered below.** |
| 2 | Relax filter_5 (ribbon direction / bull-bear MA-stack) | 2nd-most-common blocker (35/389 days); directly relevant to trend-up (4/14 gate-blocks). | **Already claimed** — `prereg-filter5-ribbon-2026-07-31.json`, frozen 2026-07-31, not re-proposed. |
| 3 | `block_elite_bull` requalification | Dominant LIVE-window blocker across every observed archetype, both accounts (§1a) — most directly implicated in bull-side trend-day participation, which this study's bear-only replay lens cannot see at all. | **Already claimed** — another agent's lane per the filter-5 prereg's own `out_of_lane_do_not_touch` list. Flagged here for that lane's attention given how strongly it shows up in trend-archetype live data. |
| 4 | Extend WS6 regime library + run a full engine replay over the cleared 2024 stratum | Roughly doubles n for every currently-underpowered archetype (§2), enabling a real second-population check on trend-up/trend-down/V-reversal/inverted-V specifically. | Infra fast-follow, not a gate/participation change — separately scoped, not this study. |
| 5 | Diagnose which score COMPONENT under-fires on trend days (CORRECTLY_FLAT = 9 of trend-up's 28 non-entry days — a trigger fired but never reached score>=8) | A distinct mechanism from gate-blocking: the scoring formula itself, not a named veto. | Exploratory only — needs its own diagnostic pass before it's even a testable A/B. Not scoped here. |

**#1 is the pick.** It is structural (every archetype, not a narrow edge case), already
independently flagged by the 90-day `DAY-CARDS-90D-2026-07-28.md` study as the #2 systemic cause
with a large oracle bound ("First-shot +$2,859/17d is the hypothesis, NOT a validated edge...
needs the full pre-reg battery" — this IS that battery), unclaimed by any other lane, and
requires zero new code (both relaxation mechanisms already exist and are already wired into
production paths). Critically, **the only prior research on this exact gate is disqualified**
(see next section) — this is a genuinely open question, not a re-litigation.

## 4. The pre-registration

**`analysis/recommendations/prereg-vix-regime-gate-archetype-2026-08-02.json`** — frozen
**2026-08-01 16:53:48 ET** (`python setup/scripts/et_clock.py`), before any run, committed with
this document.

**Why prior filter_8 research doesn't count:** 8 autoresearch scripts swept `vix_soft_mode` /
`disable_filters=[8]` on 2026-05-19 (`vix_soft_16mo_backtest.json`, `vix_mode_edge_sweep.json`,
`vix_soft_walk_forward.json`, `vix_perbar_deep_dive.json`, + 4 more). The best config's reported
full-16-month total was **$107,859–$111,254** — a >20x gap over this engine's actual validated
18-month total of $4,808.75. Read the code (`vix_soft_16mo_backtest.py:112-118`,
`analyze_result()`): it sums `t.dollar_pnl` **directly off the raw `run_backtest()` trade
objects**, never re-deriving through `lib/exit_manager_walk.walk_exit_manager`. That is exactly
the KNOWN-DIVERGENT `simulate_trade_real`-shaped path `engine_fullhist_replay.py`'s own
EXIT-SHAPE-PARITY guard test was built to catch. **None of those 8 files' P&L numbers may be
cited as evidence for or against filter_8**, in this study or any future one, until re-run
through the current exit-walk standard. This prereg is that re-run — pre-registered, not yet
executed.

**Hypothesis:** filter_8 is a lagging veto whose block-set is not net-negative under the real
exit walk, and relaxing it disproportionately restores participation in the starved trend/V
archetypes without breaking gap-go/range-chop or the runner-cohort profit engine.

**Arms (both toggle existing, already-wired flags — zero new code):**
- CONTROL: production unchanged.
- ARM_A_soft: `vix_soft_mode=True` — **bear-side only** (bull path has no soft-mode parameter
  at all, confirmed by reading `evaluate_bullish_setup`'s full signature).
- ARM_B_delete: `disable_filters=[8]` — symmetric, both sides.

**Gates (ship requires ALL of G1-G5):** G1 recent-25-day delta > 0 (**primary**, per J's
dynamic-market doctrine) · G2 day-majority positive in the recent window · G3 survives
drop-best in the recent window · G4 runner-cohort exits (count + $) >= 95% of CONTROL, zero
tolerance · G5 fire-count floor (>=10 new entries full pop, >=2 recent — L243 guard against a
fix too narrow to ever fire). **Reported, not gating:** G6 per-archetype participation delta
(the motivating question, but descriptive — gating on an 8-way-sliced already-thin population
on top of the aggregate gates would be uncorrected multiple comparisons) · BH-FDR across the 2
arms at alpha=0.10 · full-population delta.

**Not run. Not armed.** The study executes clean later, against this frozen spec.

---

## 5. Guard tests (RED-proofed)

Two new tools this session, both reusing already-guarded machinery rather than reimplementing
scoring/classification logic:

- **`backtest/tools/regime_participation_replay.py`** — full-population extension of
  `day_report_card.py` (identical `classify_day`/`aggregate_cards`/`modal_blocker_of`/
  `trade_excursions` calls, already guarded by `test_day_report_card.py`, not re-tested here).
  The one new function, `aggregate_by_archetype()`, is guarded by
  `backtest/tests/test_regime_participation_replay.py` (10 tests: entered-cause classification,
  gate/correctly-flat/no-vocabulary bucket separation, archetype isolation, UNTAGGED fallback,
  and two tests proving the function DELEGATES to `day_report_card.aggregate_cards()` rather
  than reimplementing it — including that it still fail-loudly rejects an out-of-taxonomy
  cause).
- **`backtest/tools/regime_participation_study.py`** — the PERFORMANCE/PARTICIPATION
  consolidation. Three pure functions guarded by
  `backtest/tests/test_regime_participation_study.py` (18 tests): `performance_by_archetype()`
  (concentration-check arithmetic — broad-based vs single-outlier-day cases, the zero-total
  divide-by-zero guard, multi-trade-same-day aggregation, the underpowered n<15 boundary at
  exactly 14 vs 15), `recent_n_trading_days()` (last-N selection, dedup, the intentional
  `n=0`-means-unlimited convention matching `participation_cascade.discover_sessions`), and
  `core_decisions_participation()` (stage histograms, blocker-leaderboard exclusions, per-
  account isolation).

**RED-proofed live, this session:** inverted the `top_day_share_of_total` ratio
(`total/top_day` instead of `top_day/total`) and dropped `"GREEN"` from `_ENTERED_CAUSES` —
5 tests failed exactly as expected across both files, then both mutations were reverted and the
full 28-test suite confirmed green again.

```
backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_regime_participation_replay.py backtest/tests/test_regime_participation_study.py -q
28 passed
```

## 6. Data provenance note — a small, investigated, non-blocking discrepancy

`regime_participation_replay.py`'s anchor cross-check (the SAME `baseline_n_trades=191` /
`baseline_total_pnl=$5,306.95` / `candidates_at_floor8=2308` anchor `day_report_card.py` itself
carries, from `analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json`) came back **FAIL**: this
run got 194 walked trades / $4,723.95 / 2306 candidates. Investigated before trusting anything
downstream of it (per the "extraordinary/surprising result -> hunt the artifact first"
discipline):

- **Code drift ruled out:** `git log --oneline df0348d9..HEAD -- backtest/lib/ backtest/tools/ladder_fullhist_replay.py backtest/tools/day_report_card.py`
  returns zero commits — the scoring/filter/exit-walk code has not moved.
- **Data drift ruled out for the pinned files:** `spy_5m_2026-05-19_2026-07-27.csv` and
  `vix_5m_2026-05-19_2026-07-27.csv` (the hardcoded ladder data window) carry mtimes of
  2026-07-27 14:16 — untouched since the anchor was pinned.
- **Residual not fully traced** within this session's time budget: candidate count (a pure
  function of SPY/VIX bars + unchanged code) differing by 2 of 2308 (0.09%) with confirmed-
  identical inputs suggests either non-determinism this session did not chase down, or a
  difference between `engine_fullhist_replay.py`'s own 2026-07-23 run and the `ladder_fullhist_
  replay.py`-based pipeline this study reuses that predates this session (the two published
  artifacts, `engine-fullhist-replay-2026-07-23.json` at $4,808.75/191 and
  `LADDER-FULLHIST-2026-07-27.json` at $5,306.95/191, already disagreed with each other by $498
  before this study ran anything).
- **Does not affect this document's conclusions:** the PERFORMANCE table (§1b) cites
  `engine-fullhist-replay-2026-07-23.json` verbatim, untouched by this residual. The
  PARTICIPATION blocker histogram (§1a) uses only candidate/gate COUNTS from this session's own
  self-consistent run (2306 candidates, not reconciled against the older 2308 pin) — a <0.1%
  count difference cannot flip a "filter_8 blocks 31% of all days" finding.
- Flagged, not fixed: reconciling `engine_fullhist_replay.py` vs `ladder_fullhist_replay.py`'s
  slightly different trade counts is a separate, pre-existing cross-artifact question, out of
  this study's scope.

---

_Sources: `analysis/regime-library/day-archetypes.json` (WS6, spec 1.0.0) ·
`analysis/recommendations/engine-fullhist-replay-2026-07-23.json` ·
`analysis/regime-library/participation-replay-fullhist-2026-08-02.json` (new) ·
`analysis/regime-library/REGIME-PARTICIPATION-STUDY-2026-08-02.json` (new) ·
`automation/state/core-decisions.jsonl` · `analysis/deep-research/DAY-CARDS-90D-2026-07-28.md` ·
`analysis/deep-research/OPRA-BACKFILL-2026-07-31.md` ·
`analysis/recommendations/prereg-filter5-ribbon-2026-07-31.json` ·
`analysis/recommendations/vix_soft_16mo_backtest.json` (disqualified, cited only as
provenance)._
