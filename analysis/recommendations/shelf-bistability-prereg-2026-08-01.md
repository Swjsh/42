# PRE-REGISTRATION — shelf bistability SOURCE-FIX A/B (Next-Twelve #7, verifier-endorsed follow-up to WS3)

**Frozen:** et_clock `2026-08-01 14:23:21 Saturday EDT` (market_hours=False), stamped and
committed BEFORE the runner `backtest/tools/shelf_bistability_source_fix_2026_08_01.py`
exists. Freeze order is git-provable: this file's commit precedes the runner's first commit
and any run output. HEAD at freeze: `beaa7ba8`.

**Parent finding (WS3, shipped `114a7a6b`):** `refresh_levels_intraday._hysteresis_carry`
(N=5) bridges the 743.25-class flicker at the FEED CHOKE-POINT — a symptom damper, disclosed
as such by WS3's own audit review ("symptom-bridge at the feed choke-point (source fix
properly deferred to a pre-registered A/B)"). This study attacks the SOURCE:
`daily_context._merge_shelf_candidates` and its caller `_shelf_zones` / `_find_shelf_candidates`.
Do NOT touch `refresh_levels_intraday.py`'s shipped hysteresis logic beyond reading it, and do
NOT touch params/exit files — both honored throughout.

---

## 1. Mechanism (named precisely, reproduced, concrete flip quoted)

**The bistability:** every 5-min `Gamma_LevelRefresh` fire calls
`daily_context.compute_daily_context()`, which fetches ~60 calendar days of DAILY SPY bars
via `_fetch_daily_bars()`. Because the fetch runs mid-session, the LAST bar in that series is
TODAY's own still-forming daily bar — its O is fixed at the session open, but H/L/C/V keep
changing every fire as the session progresses. `_find_shelf_candidates` seeds a candidate
$1.60-wide band at every unique close/high/low across ALL bars (today's included) and scores
every bar — today's included — as a touch. `_merge_shelf_candidates` then does a GREEDY
strongest-first (ties broken by lower `band_low`) non-overlap merge. Because today's own
evolving H/L/C changes which historical candidate bands today's bar happens to touch, the
touch-count leaderboard for any region with two-or-more near-tied overlapping candidates can
reorder between one fire and the next — the merge's WINNER for that region changes, and
because the winning candidate's own `(band_low, band_high)` mid is the level's PRICE IDENTITY,
the written level's price changes (e.g. 743.25 <-> 742.36) even though nothing broke or moved
structurally. Two upstream corollaries directly evidenced in production data: `_shelf_zones`
also uses `today_idx` (needs the forming bar) for break/backside-retest — that dependency is
legitimate and untouched by any arm below; only the CANDIDATE-FINDING/MERGE step is in scope.

**Reproduction method:** real REST-fetched SIP daily bars (`backtest/data/
spy_daily_bars_real_2024-10-01_2026-08-01.json`, fetched live this session, 459 bars,
2024-10-01..2026-07-31 — NOT derived/resampled) sliced to the trailing 60-calendar-day window
strictly before session D, PLUS a forming bar for D reconstructed from D's own real RTH 5m SIP
tape (`backtest/data/spy_5m_2026-05-19_2026-07-31.csv`) truncated to each fire's timestamp
(running O=session's first RTH open, H=max-high-so-far, L=min-low-so-far, C=latest-close-so-far,
V=cumulative volume) — fed through the REAL, unmodified `daily_context._find_shelf_candidates`
/ `_merge_shelf_candidates` (imported read-only, never copied/re-derived).

**Validation against real production output (before trusting the method at scale):**
cross-checked against every real `automation/state/key-levels-history/*` snapshot from the
days the shelf feature was actually live in production (`daily_context_shelf` source first
appears 2026-07-28; 2026-07-22/23/27 predate the feature and are excluded from this check, not
counted as misses), applying the SAME $20 `SHELF_UPSERT_BAND` distance-from-spot filter
`refresh_levels_intraday.refresh()` applies before writing (daily_context itself returns the
full multi-week universe; the written file is filtered — comparing unfiltered sim output
against the filtered file is an apples-to-oranges error the first draft of this check made and
corrected). At full 5-minute fire cadence across the entire 2026-07-31 RTH session (77 fires,
09:33-15:53 ET) against the REAL observed A/B state sequence baked into
`backtest/tests/test_level_hysteresis_2026_08_01.py::_CHANGES` (sourced from
`core-decisions.jsonl`, ground truth): **63/77 fires match exactly (81.8%)**. This is
consistent with WS3's own disclosed reproduction fidelity on a differently-scoped check
(76-77/89, ~85%) — both cluster mismatches at flip BOUNDARIES (one-fire phase lag) and
session-open boundary noise, not methodology failure. Sparse 4-per-day snapshot cross-checks
on 2026-07-28/29/31 (11 comparable snapshots): 4/11 exact (36.4%); ALL FOUR mid-session,
well-settled snapshots (12:00/15:50 on both 07-29 and 07-31) match exactly bit-for-bit;
mismatches concentrate at premarket/first-16-minutes-of-RTH snapshots, the most forming-bar-
data-starved and reconstruction-boundary-sensitive moments — disclosed honestly, not hidden.
This is a sanity/confidence check on the MECHANISM, not a requirement for the 4-arm study
below: all four arms are computed from the IDENTICAL simulated pipeline, so the internal A/B/
AB-vs-BASELINE comparison is valid regardless of any absolute-fidelity gap to history.

**The concrete flip (tiny input delta, named exactly):** 2026-07-31, fires 09:43:37 -> 09:48:37
ET (5 minutes apart, both real production fire timestamps). Forming bar at 09:43: O=745.06
H=746.55 **L=742.79 C=743.12**. Forming bar at 09:48 (one more real 5m SPY bar printed):
O=745.06 H=746.55 **L=741.98 C=742.28** — the running low ticked -$0.81 and the running close
ticked -$0.84, ordinary intraday noise, no level broken. Effect on candidates in the
740.50-743.50 region:
- `[741.56,743.16]` (mid **742.36**): 10 touches at BOTH fires (unaffected by the delta).
- `[742.45,744.05]` (mid **743.25**): 9 touches at 09:43 (today's bar counted: low 742.79 and
  close 743.12 both land inside) -> **8 touches** at 09:48 (today's bar NO LONGER counted:
  741.98 and 742.28 both now fall below 742.45) — LOSES its today-touch.
- `[740.80,742.40]` (mid **741.60**): 9 touches at 09:43 (today NOT counted: 742.79 is above
  742.40) -> **10 touches** at 09:48 (today NOW counted: 741.98 falls inside) — GAINS a touch.
- A brand-new transient candidate `[742.28,743.88]` (mid 743.08, 10 touches) appears at 09:48,
  seeded directly by today's own new close (742.28) — direct, mechanical proof of forming-bar
  self-seeding.
- Merge at 09:43: highest touch count is 742.36 (10) — nothing else at 10 — **WINNER: 742.36.**
- Merge at 09:48: FIVE candidates now tie at 10 touches; greedy tie-break picks lowest
  `band_low` first — `[740.80,742.40]` (741.60) wins the region, which leaves
  `[742.45,744.05]` (743.25, 8 touches) as the next non-overlapping pick — **WINNER SET:
  {741.60, 743.25}, 742.36 is GONE.**

One ordinary 5-minute bar update to the still-forming daily bar's low/close re-tiles the
merge's output across the entire $740.50-744.05 region. This is the mechanism, reproduced and
quoted exactly. (Sim state transitions to "A"=743.25-present at this same fire per the
harness; real production's observed transition to "A" lands one fire later at 09:53 —
consistent with the disclosed ~18% mismatch rate, a one-fire phase lag, not a different
mechanism.)

---

## 2. Population & data (391-day population, identical construction to WS5/WS6/WS11 lineage)

- **Days:** RTH sessions `2025-01-02 .. 2026-07-31`, 3 half-days excluded
  (2025-07-03, 2025-11-28, 2025-12-24), 2026-06-15 (12-bar gap day) stays IN — the VERIFIED
  391-day population, identical to `shelf_hold_reclaim_study.py`'s `EXPECTED_DAYS = 391`.
  Frame: et-v2 (`lib.et_frame.parse_timestamp_et`, DST-correct — C6). Actual day count
  asserted before any cell is computed; abort if != 391.
- **SPY 5m:** `backtest/data/spy_5m_2025-01-01_2026-07-22.csv` + strictly-after-07-22 tail of
  `backtest/data/spy_5m_2026-05-19_2026-07-31.csv` (ladder_fullhist_replay `load_extended_data`
  convention, reused verbatim).
- **Daily bars (60-cal-day trailing lookback):** REAL SIP daily bars fetched fresh this
  session via the SAME Alpaca REST endpoint `daily_context._fetch_daily_bars` uses
  (`feed=sip&adjustment=raw`), cached at `backtest/data/
  spy_daily_bars_real_2024-10-01_2026-08-01.json` (459 bars, gitignored cache dir). NOT
  resampled from 5m data — some early test days' 60-cal-day lookback reaches into 2024-11,
  before the 5m cache begins.
- **Refresh cadence (simulated):** `:MM:37` ET, `MM % 5 == 3`, clipped to `[09:33, 15:53]` —
  IDENTICAL fire convention to WS3's own guard fixture (`test_level_hysteresis_2026_08_01.py`)
  and the real `Gamma_LevelRefresh` schedule. 77 fires/day x 391 days.
- **Option P&L (metric c only): real OPRA only** — cached `backtest/data/options/{symbol}.csv`
  (14,399 contract files present), loaded exactly as `shelf_hold_reclaim_study.py::
  load_opt_et2` (et-v2 parsed). Missing contract / missing print / zero print / sub-floor
  premium -> row EXCLUDED, counted, never synthetic.
- **2024 EXCLUDED** (population starts 2025-01-02): tonight's 2024 OPRA backfill is
  unverified (`analysis/deep-research/OPRA-BACKFILL-2026-07-31.md` does not exist).

## 3. Arms (frozen mechanisms — code, not prose, before any cell is run)

All four arms share the IDENTICAL `_find_shelf_candidates` touch-counting primitive
(unmodified, imported read-only from `daily_context.py`) — only what feeds it, and how the
merge breaks contests, differs.

- **BASELINE** = current HEAD, unmodified: `_find_shelf_candidates(trailing + forming)` ->
  `_merge_shelf_candidates(candidates)` (existing `(-touches, band_low)` sort). This is what
  production runs TODAY upstream of hysteresis.
- **ARM_B (exclude forming bar):** `_find_shelf_candidates(trailing ONLY — bars with
  `date < D`, forming bar never appended)` -> unmodified `_merge_shelf_candidates`. Mirrors
  the ALREADY-established pattern in this exact codebase
  (`daily_context._prior_day_hlc`'s `date < today_et` filter; `shelf_hold_reclaim_study.py::
  shelf_zones_asof`'s `[b for b in daily_bars if lo <= b["date"] < hi]`) — not a novel
  invention. Break/backside-retest detection (needs `today_idx`) is UNCHANGED — it legitimately
  reacts to today's price action; only shelf DISCOVERY is scoped off the forming bar.
  **Falsifiable structural prediction, stated before any run:** because the candidate set
  ARM_B feeds the merge never changes within a session (all inputs are date<D, fixed for the
  whole day), ARM_B's per-day flicker is EXACTLY ZERO by construction, not merely reduced —
  checked (not assumed) via guard 3 below.
- **ARM_A (incumbent-stable tie-break):** identical candidates to BASELINE (forming bar
  included); merge ranking key becomes `(-touches, 0 if candidate-overlaps-incumbent else 1,
  band_low)` — i.e. on a LITERAL tie in touch count, the candidate overlapping the immediately
  -prior refresh's kept band wins; otherwise identical to today's sort. Zero new magic-number
  margins (no "near-tie" fudge factor) — "stable sort key + prefer-incumbent-zone-on-ties"
  read literally. Incumbent = the arm's OWN previous-fire kept-shelf bands, threaded
  CONTINUOUSLY across the full 391-day x 77-fire timeline in date order (no reset at session
  boundaries — matches production reality: `key-levels.json` is never wiped overnight).
  First fire of the whole population starts with no incumbent (byte-identical to BASELINE on
  that one fire). Confirmed NOT vacuous before committing to it: the reproduced 09:48 flip
  above contains a genuine 5-way exact tie at 10 touches — an incumbent-aware tie-break
  demonstrably changes that specific outcome (verified by hand before freezing this arm).
- **ARM_AB** = ARM_A's merge fed ARM_B's (forming-bar-excluded) candidates. **Falsifiable
  prediction, stated before any run:** since ARM_B's candidate set is invariant intraday,
  ARM_A's tie-break has nothing left to arbitrate after the first fire of each day once inputs
  stop changing — ARM_AB should be numerically IDENTICAL to ARM_B on every fire. Checked, not
  assumed.

## 4. Metrics (all reported; (a)/(b) full 391-day population, (c) proof-pruned subset + full
recent-25 first-class)

**(a) Flicker rate — two layers, both reported, 100% of the 391-day population (a strict
coverage improvement over the sparse 6-day snapshot-only fallback the task allows; the 6-day
real-snapshot subset is used ONLY as the methodology validation in §1, not as the metric-(a)
sample):**
  - RAW: per-day count of fire-to-fire transitions in the near-spot (`|mid - forming_close| <=
    SHELF_UPSERT_BAND=$20`, production's own upsert-band constant) merged shelf-mid SET, BEFORE
    hysteresis. This is the SOURCE-level effect size.
  - WRITTEN: the same near-spot shelf-family entries run through the REAL, unmodified
    `refresh_levels_intraday._hysteresis_carry` (N=5, imported read-only) in fire order,
    exactly mirroring production's pipeline stage order — this is what the engine's
    `levels_active` would actually have seen. Reported per arm, full population AND recent-25.

**(b) Level-set fidelity (steady-state, the fix must not change WHICH levels exist):**
  - PRIMARY (gating): per day, per arm — the EOD (final 15:53 fire, WRITTEN/post-hysteresis,
    near-spot) shelf-mid set vs BASELINE's EOD set on the SAME day. Any mid present in one and
    absent in the other is a "permanent divergence," counted and itemized (day, price, which
    side). Target ~zero per the task's own bar; any nonzero count is reported as a regression,
    not averaged away.
  - SECONDARY (diagnostic, non-gating): full-day UNION set-diff (any-fire-of-the-day) — larger
    by construction, expected to show MORE differences than the EOD check (a level that only
    ever existed as a mid-day bistable artifact SHOULD disappear under a working source fix —
    that is the intended effect, not a fidelity defect). Reported for transparency, explicitly
    labeled non-gating.

**(c) Downstream entry impact (real OPRA P&L):**
  - **Proof-pruned population (not a sample — a proof):** a day is "interesting" iff
    BASELINE's WRITTEN shelf sequence has >=1 flip OR any arm's EOD set diverges from
    BASELINE's EOD set (metric a/b's own output feeds this gate). On every OTHER day, this
    study ASSERTS (not assumes) all four arms' fire-by-fire shelf-anchor sequences are
    identical to BASELINE's — if that assertion ever fails the run aborts loudly rather than
    silently under-covering. Entries on non-interesting days are therefore PROVABLY unchanged
    (zero P&L delta by construction), not skipped by sampling.
  - **Detector (disclosed scope):** `filters.detect_level_reclaim` (close-cross reclaim) ONLY
    — the single most direct, level-price-sensitive existing detector (fires strictly off
    `bar.low < level < bar.close`, so a level's PRICE IDENTITY change is exactly what moves
    its fires). Wick-defense / touch-and-hold geometries are NOT re-tested here (WS5 already
    NULLed shelf_hold_reclaim's tradeable edge on 391 days this same weekend; re-validating
    profitability is out of scope — this study measures whether the SOURCE FIX changes
    entries/P&L relative to today's hysteresis-only baseline, a regression check, not a new
    edge search).
  - **Filters applied:** F1 time gate only (bar >= 09:35 ET, NOT in [15:00,16:00) — SAFE_BASE
    values). Ribbon/VIX/volume filters (F5/F6/F8/F9/F10) NOT applied — disclosed; they are
    orthogonal to the level-identity question this study targets and would dilute the signal
    with unrelated variance.
  - **Anchors:** each arm's own near-spot (`SHELF_UPSERT_BAND=$20`) WRITTEN shelf-family mids,
    active AS OF the most recent fire at-or-before the bar being scanned (mirrors the engine
    reading whatever key-levels.json currently holds).
  - **Fill/exit convention (byte-identical to WS5, reused verbatim):** entry tick = trigger-bar
    close + 5min; fill = OPEN of first cached OPRA bar at/after that tick; entry premium floor
    $0.30; strike = ATM = round(trigger close); qty=3; one-position-at-a-time occupancy (busy
    -until = CONTROL exit time); exits via the REAL unmodified `walk_exit_manager` against the
    CONTROL registry exit shape (`automation/state/fleet/strategies.py RIBBON_RIDE.exit.
    to_dict()`, byte-identity asserted at run time), `structure_stop_enabled=True`,
    `trigger_level` = the fired anchor's zone floor (`band_low`), `time_stop_et=15:40` (live
    Safe `params.json` value).
  - **Reported:** per arm vs BASELINE — entries GAINED (fire under arm, not under baseline),
    LOST (reverse), MOVED (same bar fires under both, different anchor/zone_floor -> same
    entry premium/strike, different structure stop, so potentially different exit/P&L), and
    the real-OPRA total P&L delta. Full population AND recent-25-day window (`all_days[-25]`,
    identical definition to WS5) reported separately and FIRST-CLASS (not buried) per the
    task's own gate requirement.

## 5. Gates (frozen pass bars, per arm)

An arm SHIPS (real edit to `setup/scripts/daily_context.py`, guarded) only if ALL of:

1. **G1 flicker materially reduced:** WRITTEN flip count, full population, strictly less than
   BASELINE's, AND recent-25-day WRITTEN flip count not worse than BASELINE's.
2. **G2 steady-state fidelity preserved:** zero PRIMARY (EOD) permanent divergences vs
   BASELINE across the full 391-day population. Nonzero is a disclosed regression; the arm
   does not ship with an unexplained nonzero count.
3. **G3 entry-population P&L not degraded:** OPRA P&L delta (arm total − baseline total) >= 0
   on BOTH the full proof-pruned population and the recent-25-day window (recent-25
   first-class — required, not advisory).
4. **G4 guard suite (below) green, including RED-proof** (neutered mechanism reproduces the
   BASELINE-flip failure the guard exists to catch).

**Tie-break between clearing arms:** prefer the arm with the SMALLEST production footprint
that clears. ARM_B needs zero new state (a pure filter on `_find_shelf_candidates`'s input).
ARM_A/ARM_AB require threading incumbent state across refreshes (a new, persistent moving
part in `refresh_levels_intraday.py`'s call site). Given ARM_B's structural (not merely
empirical) zero-flicker guarantee, it is expected but not assumed to dominate — reported
either way.

**Hysteresis disposition on ship:** kept as defense-in-depth by default (per task instruction)
UNLESS the winning arm's own RAW-vs-WRITTEN comparison shows `_hysteresis_carry` fires ZERO
times under that arm across the full 391-day population (i.e. it is empirically inert, not
merely untested) — in which case this is stated explicitly as the evidence, and hysteresis is
still left in place (removal is not pre-registered as an action this study takes; it is a
separate, future decision if ever proposed).

**Null outcome is a deliverable:** if no arm clears all gates, hysteresis-only stands, no
production code is touched, and the artifacts record which gate(s) blocked each arm with
numbers.

## 6. Guards (frozen names, before any run)

- `test_mechanism_reproduces_the_named_flip` — feeds the exact 09:43/09:48 07-31 bars (§1)
  through unmodified BASELINE merge; asserts 742.36 wins at 09:43 and {741.60,743.25} wins at
  09:48 (742.36 gone) — pins the reproduced mechanism itself as a regression guard.
- `test_arm_b_structurally_invariant_intraday` — for a sample of days, asserts ARM_B's merged
  candidate list is BYTE-IDENTICAL across every one of that day's 77 fires (proves the "zero
  flicker by construction" claim formally).
- `test_arm_a_resolves_the_named_tie_toward_incumbent` — feeds the 09:48 five-way tie with
  incumbent=742.36 from 09:43; asserts ARM_A keeps 742.36 where BASELINE drops it.
- `test_arm_ab_equals_arm_b_intraday` — checks the stated ARM_AB==ARM_B prediction on the
  sampled days above.
- **RED-proof `test_red_proof_neutered_arms_reproduce_baseline_flip`** — neuter each arm back
  to BASELINE behavior (empty incumbent every fire for ARM_A; re-include the forming bar for
  ARM_B) and assert the flip REAPPEARS (742.36 drops at 09:48) — proves the guards actually
  bite, not vacuous, matching this codebase's established RED-proof convention.
- Any arm that ships gets an additional end-to-end guard mirroring
  `test_refresh_end_to_end_shelf_retiling_is_bridged`'s pattern, added at ship time.

## 7. Outcomes (pre-committed)

- **An arm clears all gates ->** ship the winning mechanism as a real, minimal, guarded edit
  to `setup/scripts/daily_context.py` (ARM_B: filter forming bar out of
  `_find_shelf_candidates`'s input inside `_shelf_zones`, ~3 lines). If ARM_A/AB wins instead,
  additionally wire incumbent-threading at `refresh_levels_intraday.py`'s
  `daily_context.compute_daily_context(now=now)` call site (reading the currently-written
  `daily_context_shelf` entries from the just-loaded `key-levels.json` as the incumbent — no
  new state file). Hysteresis stays, per §5, unless proven inert. Both `refresh_levels_intraday
  .py`'s HYSTERESIS block and params/exit files remain untouched either way.
- **No arm clears ->** hysteresis-only stands. No production file is touched. Artifacts record
  the null with full per-gate numbers per arm — that is itself the deliverable, closing the
  Next-Twelve #7 question with evidence.

Artifacts: `analysis/recommendations/shelf-bistability-2026-08-01.{md,json}` (all cells +
guard results in the JSON; MD = synthesis). Runner:
`backtest/tools/shelf_bistability_source_fix_2026_08_01.py` (committed AFTER this prereg).
Guards: `backtest/tests/test_shelf_bistability_2026_08_01.py`.

*Analysis only until a ship decision is reached: no live config, param, gate, or order is
touched by the runner itself. Concurrent-lane fence respected: no writes to
crypto_twin_core.py / theta_clock.py / trades.csv writer / twin cadence / firm_brief theta
line / any other Next-Twelve lane's files.*
