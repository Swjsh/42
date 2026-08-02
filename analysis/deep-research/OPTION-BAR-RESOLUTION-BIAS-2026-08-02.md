# OPTION-BAR-RESOLUTION-BIAS-2026-08-02

**Integrity lane, overnight 2026-08-02 (Sunday, into Monday 2026-08-03).** Verdict: the
defect is real, measured, and material — but the two named live knobs both **CONFIRMED** at
honest resolution. No live setting was wrong. The source is fixed (disclosure + opt-in guard,
not a silent default). One adjacent, unrelated data-completeness bug was found and filed as a
separate low-priority follow-up, not conflated with the resolution finding.

---

## 0. The question

`backtest/lib/option_pricing_real.py` serves OPRA option bars at a silent-default
**5-minute** resolution (`backtest/tools/fetch_option_data.py` hardcodes `timeframe="5Min"`).
A stop that is breached and recovers INSIDE a 5-minute bar is invisible at that resolution —
the replay records no stop hit where a real 1-minute tick (and the live engine) would have
taken one. This was already found once, on 2026-07-17, and left unfixed
(`automation/overnight/GOAL-REPLAY-TODAY-GREEN.md`, which found 5-minute resolution zeroed 3
of 5 real trades to exactly $0.00, then closed with a `FUTURE-IMPROVEMENTS.md` note that never
got picked up). Tonight, `backtest/tools/level_target_exit_study.py` (a different,
already-running lane) independently rediscovered it while G8-checking its own harness's parity
against real fills: **first run (5-min cached bars) showed harness +$2,377.86 vs actual
real fills −$1,259.99 (a sign-flipped $3,637.85 gap); refetched at true 1-minute resolution,
the gap shrank to $1,920.40 (harness +$660.41 vs actual −$1,259.99)** — a $1,717.45 swing
attributable to resolution alone, root-caused exactly on `SPY260709C00750000` (risky-3): the
real position stopped out on a dip to $0.40 inside a 5-min bar whose own open was $0.52, so
the 5-min-bar walk rode straight through the stop and posted a phantom gain.

**Blast radius:** the 5-min cache feeds `simulator_real.py` (~250+ importers, confirmed via
`grep -rn "load_contract_bars("` — every call site passes only `symbol`, zero exceptions) and
`exit_manager_walk.py`, and therefore transitively most of `analysis/recommendations/*.json`.
The two named highest-stakes consumers: `structure_stop_study.py` (feeds the live v15.3
CHART-STOP-PRIMARY flag) and `ribbon_ride_strike_exit_ab.py` (the strike-tier evidence base for
the live ATM strike under that same exit shape).

The question this lane answers: **do those live knobs survive at honest resolution?** A
replay that under-detects stop hits should systematically flatter strategies that hold through
drawdowns and penalize tight stops — the bias points in a specific direction, not randomly, so
it could plausibly have selected the wrong setting.

---

## 1. STEP 1 — quantify the bias (cheap, general, before re-running anything expensive)

**Method.** Took the canonical real-fills population
(`backtest/tools/level_target_exit_study.build_population()`, reused unchanged — 129
positions, all 6 live arms, each joined to its own REAL fired exit shape / stop mode /
trigger level from the decision log) and walked **every position twice** through the
identical production decision core (`backtest/lib/exit_manager_walk.walk_exit_manager`,
byte-identical both times) — once on 5-minute bars (`option_pricing_real.load_contract_bars`,
the exact defect function) and once on 1-minute bars (`exit_shape_parity_study.
fetch_option_bars`, the same live-REST path the level-target-exit lane proved out on this
population tonight). Entry price, exit shape, trigger level, stop mode, qty, strategy, and
time-stop were held byte-identical between the two walks — **the only variable was option-bar
resolution.** Tool: `backtest/tools/option_bar_resolution_bias_2026_08_02.py`. Output:
`analysis/recommendations/option-bar-resolution-bias-2026-08-02.json`.

**Result — material, and cleanly one-directional:**

| Metric | Value |
|---|---|
| Positions with both resolutions available | 123 / 129 (6 lacked a 5-min disk-cache entry) |
| Stop hits appearing **only** at 1-min (invisible at 5-min) | **4** |
| Stop hits appearing **only** at 5-min (phantom, false positive) | **0** |
| Aggregate P&L at 5-min | $2,569.56 |
| Aggregate P&L at 1-min | $747.81 |
| **Gap (5-min − 1-min)** | **$1,821.75** |
| Direction | **5-min FLATTERS P&L** (never the reverse) |

Zero false positives in 123 positions is itself a finding: the bias isn't noise, it's a
one-directional under-detection, exactly the mechanism the task hypothesized.

**Concentration check (fable-too-good discipline, not skipped):** all 4 stop-only-at-1-min
flips are the **same underlying signal** — `SPY260709C00750000`, 2026-07-09 — replicated
across 4 sibling arms (safe-1, safe-3, risky-1, risky-3) that all traded it. At 5-min, this
resolves via TP1-then-ride-to-time-stop (+$213 to +$392 per arm); at 1-min, a `premium_stop`
fires first (−$17 to −$29 per arm). Per this repo's own L174/2026-08-02 lesson
("OOS signal populations can silently overlap across setups — pool by distinct trial, not
raw row count"), this is **n=1 distinct occurrence, not 4 independent trials** — it accounts
for $1,294.20 of the $1,821.75 total gap, with the remaining $527.55 spread thinly across the
other 119 positions (smaller per-trade fill-price/timing deltas, not additional stop flips).
Disclosed, not smoothed over: the bias is real and directionally unanimous, but its dollar
magnitude in this sample is concentrated, not broadly diffuse. `SPY260709C00750000` is the
exact contract the task brief named as "confirmed to the cent tonight" — independent
cross-validation via a completely different computation path (this script vs. the
level-target-exit lane's G8 parity check) landing on the same symbol.

**Verdict: MATERIAL. Proceed to Step 2** (not a false alarm, not manufactured — the effect is
small-n-concentrated but real, one-directional, and independently cross-validated).

---

## 2. STEP 2 — re-run the two live-knob studies at 1-minute resolution

Both re-runs are **replications**: same frozen shapes, same signal cohorts, same gates — the
only change is the bar source. No new hypotheses, no threshold sweeping.

### 2a. `structure_stop_study.py` → live v15.3 CHART-STOP-PRIMARY (SS-B shape)

Layer B (79-position real-fills anchor) was **already 1-minute** in the original study (its
own disclosure: "layer (b)/exhibit are REAL 1-min Alpaca OPRA bars, live-fetched") — re-run
live tonight as a reproducibility check, not a fix: **byte-match confirmed** against the
persisted 2026-07-09 numbers. Layer A (18-signal fresh-slice) was 5-min
(`t4_exit_matrix._load_bars`) — rebuilt at 1-minute resolution, everything else (OTM-2 strike
convention, `>=` fill-bar inclusion, C6 close-based structure detection, shapes, buffers,
15:40 ET time-stop) held identical. Tool:
`backtest/tools/structure_stop_study_1min_2026_08_02.py`. Output:
`analysis/recommendations/structure-stop-1min-replication-2026-08-02.json`.

| Candidate | Layer A exp (orig → 1-min) | Layer B anchor (orig → 1-min) | Verdict orig → 1-min |
|---|---|---|---|
| CONTROL | $-100.67 → $-100.67 (unchanged) | $-757.1 → $-757.1 (MATCH) | — |
| SS-A | $-235.60 → $-241.11 | $-61.1 → $-61.1 | FAIL → FAIL — **CONFIRMED_FAIL** |
| **SS-B (live)** | **$-47.34 → $-52.86** | **$-604.7 → $-604.7** | **PASS → PASS — CONFIRMED** |
| SS-C | $-236.16 → $-241.67 | $1,799.9 → $1,799.9 | FAIL → FAIL — **CONFIRMED_FAIL** |

SS-A/B/C shift by a near-identical ~$5.5/tr at 1-min (structure-stop fires at the same SPY
5-min-close-derived time in both — structure_stop is 5-min-native by v15.3 design and wasn't
varied — but the OPTION premium fill at that instant reprices slightly finer at 1-min); CONTROL
(no structure-stop layer at all) is untouched to the cent, consistent with that mechanism.
**SS-B's margin over CONTROL survives intact** (Layer A: −47.34 vs −100.67 → still the best of
the four by a wide margin; both negative in this thin n=18 sample, exactly as in the original).

**KNOB A — v15.3 CHART-STOP-PRIMARY (SS-B): CONFIRMED.**

### 2b. `ribbon_ride_strike_exit_ab.py` → live ATM strike tier under SS-B

Full n=250-signal cohort, both axes, refetched at 1-min. Scope reduction (disclosed): the
random-entry null (20 seeds/cell) and BH-FDR were **not** recomputed — they are not part of
`ribbon_ride_strike_exit_ab.compare()`'s auto-ratify condition (verified by reading its source:
`compare()` touches only `metrics` + `sensitivity_old_fillbar_convention`), and re-running them
at 1-min would need ~20× the fetches for a check that doesn't gate SHIP/WAIT. Tools:
`backtest/tools/ribbon_ride_strike_exit_ab_1min_2026_08_02.py` (full population) +
`ribbon_ride_strike_exit_ab_1min_coverage_matched_2026_08_02.py` (isolation follow-up, see
below). Outputs: `ribbon-ride-strike-exit-ab-1min-replication-2026-08-02.json` +
`ribbon-ride-strike-exit-ab-1min-coverage-matched-2026-08-02.json`.

**A confound found and isolated before trusting the headline number (fable-too-good, applied
for real):** the naive full-population 1-min re-run showed `ITM-2` — the original study's
**cleanest rejected candidate** ("NOT a valid gradient endpoint... IS-2025 −$16,994... a
2026-regime-concentration profile") — flipping to clear *every* auto-ratify gate
(`wf_ge_070`/`sub_window_stable`/`oos_positive` all True, `top3_day_share` collapsing from
5.5× to 0.5×, one chronological half flipping from −$9,230 to +$11,444). That is an
extraordinary result and it was hunted, not celebrated: switching from the 5-min disk cache to
live 1-min REST didn't just reprice the same trades — it also **recovered trades the 5-min
cache never had at all.** Checking local disk-cache coverage per strike (no network, pure
disk read) found the gap widens monotonically with distance from the OTM-2 default:

| Strike | 5-min disk-cache coverage | Signals recovered by switching to 1-min REST |
|---|---|---|
| OTM-2 (control) | 250/250 | 0 |
| OTM-1 | 249/250 | 1 |
| ATM | 244/250 | 6 |
| ITM-2 | 231/250 | **19** |

So the full-population ITM-2 read conflates two different effects: genuine resolution
repricing on the original 231 trades, plus 19 brand-new trades the original study never scored
under *any* resolution. Re-ran every cell restricted to **exactly** the original study's own
covered subset (n confirmed to match the original scorecard's own table for all 4 strikes) —
this isolates resolution as the sole variable:

| Strike | Original delta vs OTM-2 (5-min, matched n) | 1-min delta vs OTM-2 (**same n**) | wf_ge_070 / sub_window_stable (1-min) | Verdict |
|---|---|---|---|---|
| OTM-1 | +$19.12/tr | **+$18.30/tr** | True / True | **CONFIRMED** (ship-eligible both times; dominated by ATM both times, correctly never armed) |
| **ATM (live)** | **+$47.96/tr** | **+$47.39/tr** | True / True | **CONFIRMED** |
| ITM-2 | −$6.78/tr (fails beats-control) | +$14.53/tr (now beats control) | **False / False** | **CONFIRMED_FAIL** — still fails wf_ge_070 and sub_window_stable, `exp_drop_top3` still negative (−$25.43 vs original −$30.19) — the original rejection survives once population composition is held fixed |

ATM's edge over OTM-2 is unchanged to within ~1% of the original ($47.96 → $47.39/tr) —
about as clean a confirmation as this kind of measurement produces. OTM-2 (the pre-migration
baseline, not itself gated) is worth flagging on its own: its own expectancy on the matched
population collapses from $17.86/tr to $1.25/tr at honest resolution (`wf_ge_070` flips
False, `exp_drop_top3` −$17.17) — consistent with, and reinforcing, the original study's own
observation that OTM-2's edge "rides its 3 best trades." This doesn't change any verdict (OTM-2
isn't a candidate being ship-gated), but it is further evidence that moving off it to ATM
(already live since 2026-06-18) was the right call.

Axis 2 (P5-CHALLENGER exit shape vs SS-B) never shipped originally
(`WAIT_OPEN_AUDIT_CHIPS` at OTM-2, `WAIT_EVIDENCE` at ITM-2) and still doesn't at 1-min — at
OTM-2 the specific blocking reason shifted (the fill-bar-convention toggle instability that
blocked it resolved to *stable* at 1-min, but it now fails `anchor_no_regression` instead); at
ITM-2 the same `anchor_no_regression` failure persists. Net: **still WAIT both ways —
CONFIRMED (non-ship stays non-ship).**

**KNOB B — ATM strike (vs OTM-2) under SS-B: CONFIRMED.**

**Adjacent finding, filed separately, not conflated with the resolution verdict:** the 5-min
disk cache's ITM-strike coverage gap is real and material to *any future* strike-comparison
study that doesn't check per-cell `n` against a matched control — filed as
`OPTION-CACHE-ITM-COVERAGE-GAP` (LOW, spec-only) in `automation/overnight/queue.md`. It did
not change tonight's verdict once isolated, but a less careful re-run could have shipped a
wrong conclusion on it.

---

## 3. Verdicts, plainly

| Live knob | Source study | Verdict | Evidence |
|---|---|---|---|
| v15.3 CHART-STOP-PRIMARY (SS-B: chandelier trail 15%, arm +5%, tp1 100%, tp1_qty 0.667) | `structure_stop_study.py` | **CONFIRMED** | Layer A margin over CONTROL survives ($52.86 gap, was $53.33); Layer B unchanged (already 1-min, byte-match reproduced live) |
| ATM strike (vs OTM-2) under SS-B | `ribbon_ride_strike_exit_ab.py` axis 1 | **CONFIRMED** | Delta over OTM-2 unchanged to ~1% on the coverage-matched population ($47.96 → $47.39/tr) |
| OTM-1 ship-eligible-but-dominated-by-ATM | same, axis 1 | **CONFIRMED** | Delta $19.12 → $18.30/tr, still dominated by ATM |
| ITM-2 rejected (concentration) | same, axis 1 | **CONFIRMED_FAIL** | Still fails wf_ge_070 + sub_window_stable on the matched population; the apparent full-population flip is a coverage-gap artifact, isolated and disclosed above |
| P5-CHALLENGER exit shape (never shipped) | same, axis 2 | **CONFIRMED** (stays non-ship) | Both OTM-2 and ITM-2 comparisons still WAIT, for the same or an adjacent reason |

**No knob inverted.** This is the reassuring outcome the task explicitly allows for — CONFIRMED,
now honestly evidenced rather than assumed — not a manufactured crisis. Per task instruction 4,
no `STATUS.md` "Known broken" entry and no corrective-A/B pre-registration were filed for any
live knob, because nothing inverted. The one thing that *was* filed
(`OPTION-CACHE-ITM-COVERAGE-GAP`) is a separate, low-priority, non-urgent data-completeness
observation, not a live-knob break.

---

## 4. What shipped (source fix)

Per task step 5's own escape hatch ("if touching all ~250 importers is unsafe tonight, ship
only the logging/disclosure half") — verified via
`grep -rn "load_contract_bars(" **/*.py"` that every existing call site across the repo passes
only `symbol` (zero exceptions), so a **backward-compatible, additive** fix was safe:

- **`backtest/lib/option_pricing_real.py`**: `load_contract_bars` gains an explicit,
  keyword-only `resolution: str = "5min"` parameter. Every existing caller is unaffected
  (default unchanged, byte-identical output — pinned by
  `test_load_contract_bars_default_call_unchanged`, which asserts frame-equality between the
  bare call and the explicit `resolution="5min"` call). Passing anything other than `"5min"`
  now raises `NotImplementedError` instead of silently returning 5-min data mislabeled as
  something else. A one-time-per-process `logging.info` disclosure fires on first use (not
  per-call — 250+ importers would drown stdout). New `assert_intraday_stop_fidelity(resolution,
  *, allow_5min=True)` guard function: raises `ValueError` when `resolution="5min"` and the
  caller hasn't set `allow_5min=True`.
- **`backtest/lib/exit_manager_walk.py`**: `walk_exit_manager` gains optional
  `opt_df_resolution: Optional[str] = None, allow_5min: bool = True` kwargs, wired to the new
  guard. Every existing call site (7 across the repo) omits both — a true no-op for them.
- **Regression found and fixed in the same session, not shipped broken**: the first version of
  this fix used a package-relative import (`from .option_pricing_real import ...`), matching
  `simulator_real.py`'s own convention — but `exit_manager_walk.py` is imported **three**
  different ways across the codebase (bare top-level `import exit_manager_walk` in 4 test
  files + `level_target_exit_study.py` + this investigation's own scripts; `from lib import
  exit_manager_walk`; `from backtest.lib.exit_manager_walk import ...`), and the relative
  import broke the bare-top-level form ("attempted relative import with no known parent
  package"). Caught by a full regression sweep (238 passed / 1 unrelated pre-existing failure
  — see below) before this was reported done, not after. Fixed with a try-relative-then-
  bare-absolute fallback that works under all three conventions.
- **Guard tests**: `backtest/tests/test_option_bar_resolution_1min_guards_2026_08_02.py`
  (13 tests, all green) — backward-compatibility pins, guard-raises pins, and two regression
  pins on Step 1's persisted measurement (`n_stop_only_at_5min == 0`,
  `SPY260709C00750000 in stop_only_at_1min_detail`) so a future re-run drifting off these
  load-bearing claims fails loudly.
- **Regression sweep**: every test importing `exit_manager_walk`/`option_pricing_real`
  (17 files, 238 tests via `-m "not slow"`) — 238 passed, 1 failed
  (`test_trail_width_exit_ab.py::test_anchor_population_hash_matches_frozen_prereg`), confirmed
  **unrelated**: `fills-ledger.jsonl` is untracked/gitignored live state that has grown since
  that study's prereg was frozen 2026-07-21 — a pre-existing population-drift condition its own
  docstring anticipates, not caused by anything touched tonight.

**Not shipped (scope discipline, matches task's own escape hatch):** `load_contract_bars`
itself still only ever serves 5-min data — no in-place 1-minute fetch/convert path was added
to it, and the guard was wired into `exit_manager_walk.walk_exit_manager` only (the one file
literally named "exit-walk consumer" in the task), not retrofitted into all ~250
`load_contract_bars` callers or the other 6 pre-existing `walk_exit_manager` call sites. Doing
that safely is a bigger, separate pass.

## 5. Documentation updated

- `markdown/infra/DATA-PROVENANCE.md` — new row-level caveat on `data/options*` with the
  measured magnitude, direction, and the separate ITM coverage-gap finding.
- `analysis/recommendations/README.md` — one standing disclosure block (not ~100 rewritten
  scorecards) covering every pre-2026-08-02 scorecard that walked stops/TPs off this cache.
- `automation/overnight/queue.md` — `OPTION-CACHE-ITM-COVERAGE-GAP` filed (LOW, spec-only);
  parser-safety verified (`test_task_scorer*.py` 63/63 green + a live `task_scorer.py --top`
  run against the edited file, unchanged top pick, matching this repo's own established
  post-queue-edit verification convention).

## 6. Files

**New tools:** `backtest/tools/option_bar_resolution_bias_2026_08_02.py` (Step 1),
`backtest/tools/_option_bars_1min_cache.py` (shared 1-min fetch+cache helper, reused by all
three investigation scripts), `backtest/tools/structure_stop_study_1min_2026_08_02.py` (Step
2a), `backtest/tools/ribbon_ride_strike_exit_ab_1min_2026_08_02.py` (Step 2b),
`backtest/tools/ribbon_ride_strike_exit_ab_1min_coverage_matched_2026_08_02.py` (confound
isolation).

**New outputs:** `analysis/recommendations/option-bar-resolution-bias-2026-08-02.json`,
`analysis/recommendations/structure-stop-1min-replication-2026-08-02.json`,
`analysis/recommendations/ribbon-ride-strike-exit-ab-1min-replication-2026-08-02.json`,
`analysis/recommendations/ribbon-ride-strike-exit-ab-1min-coverage-matched-2026-08-02.json`.

**New guard:** `backtest/tests/test_option_bar_resolution_1min_guards_2026_08_02.py` (13/13
green).

**Modified:** `backtest/lib/option_pricing_real.py`, `backtest/lib/exit_manager_walk.py`,
`markdown/infra/DATA-PROVENANCE.md`, `analysis/recommendations/README.md`,
`automation/overnight/queue.md`.

**1-minute bar cache (not committed — `backtest/data/` is gitignored, matches existing
convention):** `backtest/data/highres/{symbol}_1m_{date}.csv`, ~18MB, shared across all three
investigation scripts so a re-run never re-fetches.

## 7. Commit shas

Filled in after commit — see the session's final report.
