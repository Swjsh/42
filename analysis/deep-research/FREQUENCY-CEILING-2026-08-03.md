# FREQUENCY CEILING — the full gate cascade, not the gates — 2026-08-03

**Written 2026-08-02, overnight into Monday 2026-08-03.** The engine takes 0.49 trades/day
($4,808.75 / 191 trades / 391 days = $25.18/trade). J's $100-200/day target needs ~4
trades/day at the current per-trade quality. Twelve pre-registered attempts to improve
SELECTION nulled this weekend — frequency, not quality, is the binding term. This document
measures the two axes nobody has tested: the JOINT cost of the full gate stack (not each
gate alone), and whether the frequency ceiling is a gating problem or a missing-detector
problem. **Nothing is armed. Nothing shipped.** One narrow, evidence-backed follow-up is
pre-registered for a later session (§6).

---

## Verdict first

- **AXIS 1 (the cascade): most blocking is redundant, not additive.** Of 7,325 blocked
  qualifying candidates (both sides + bear trendline-only, full 390-day population), only
  **34.2% are blocked by exactly ONE filter/gate** — 48.6% by two, 17.2% by three. At the
  post-filter **NAMED-GATE layer specifically** (candidates that already cleared every
  filter and won routing — the genuinely novel cut this study adds), it inverts: **69.6%
  are sole-blocked by exactly one named gate.** Named gates are mostly independently
  load-bearing; filters mostly agree with each other about which candidates are bad.
- **The sole-blocker leaderboard, priced through the real exit walk, mostly REINFORCES
  existing doctrine rather than contradicting it.** `bear:filter_8` (VIX regime) sole-blocks
  676 candidates across 159 days: **−$19,712.30, BH-significant negative** — the biggest,
  most rigorous confirmation yet that this gate should stay. `quality_lock` sole-blocks 130
  candidates across 52 days: **−$6,404.20, BH-significant negative** — the anti-churn
  escalation lock is earning its keep. `block_elite_bull`'s sole-blocker cohort is
  **−$2,168.10 across 87 days, but 100% pre-dates the 2026-07-27 levels-v2 fix** (zero
  overlap with the active post-fix trial in `FRIDAY-DIAL-IN-2026-07-31.md`) — context for
  that trial's tracker, not a contradiction of it.
- **One genuinely new, statistically significant, positive finding:** `bull:filter_8` (the
  bull-side VIX gate — "VIX < 17.20 OR falling," a HARD block with **no soft-mode escape
  valve at all today**, unlike bear's) sole-blocks 183 candidates across **78 distinct
  days — 69 of which currently have ZERO entries at all.** Priced: **+$8,738.00, +$49.37/
  trade, +$112.03 per day-that-fires, WR 36.7%, survives BH-FDR at q=0.10.** This is the
  one sole-blocker cohort worth a real A/B — pre-registered in §6
  (`prereg-bull-vix-soft-mode-2026-08-03.json`), NOT shipped.
- **AXIS 2 (vocabulary): the (a)/(c) split is EMPTY — every one of the 390 days has a
  qualifying candidate somewhere.** Extending candidate generation to both sides AND the
  bear trendline-only shape (89% of real bear entries per CLAUDE.md's own G2-TRENDLINE-
  BYPASS citation, entirely excluded by every prior full-population study) closes the gap
  the bear-only lens left: **267 GATE_BLOCKED_DAY (68.5%) + 123 ENTERED (31.5%) = 390.
  Zero NO_VOCABULARY, zero CORRECTLY_FLAT.** The oracle clean-move scan built for this task
  (§5) has nothing to scan — its input population is empty. **This is itself the answer to
  AXIS 2: the frequency ceiling is not a missing-trigger-type problem. The engine already
  generates SOME qualifying signal on every trading day; what's binding is which of those
  signals the gates let through.**
- **The honest synthesis (task's closing question): 0.49/day is close to the natural rate
  of the CURRENT gate calibration, not of the vocabulary.** The vocabulary already fires
  every day. The one credible lever found is a gate-recalibration (bull VIX soft-mode,
  ~20% of days, unvalidated against real sequencing), not a new detector. The best
  candidate for a genuine future detector gap is named in §7 — with the explicit caveat
  that the SAME philosophical direction (structure-shift confirmation instead of lagging
  EMA) has already been tried and **DOUBLE-NULLED** (`structure-shift-cascade-ab-2026-07-28.md`,
  `structure-shift-replay-2026-07-28.md`, both `DO_NOT_ARM`) — flagged honestly, not oversold.

---

## 1. Method — why this is genuinely new, not a re-run

Two architectural facts, verified by reading the source before writing any new code:

1. `lib.filters.evaluate_bearish_setup` / `evaluate_bullish_setup` already collect the FULL
   per-side filter blocker set — every filter is checked unconditionally, no short-circuit.
   This layer was never the lossy step.
2. `lib.engine.gates.evaluate_gates` — the 15 NAMED gates (`block_elite_bull`,
   `require_bearish_fill_bar`, `min_ribbon_momentum_cents`, ...) — returns
   `Optional[GateBlock]` **by explicit design**: "Evaluate the 15 entry gates in
   `GATE_ORDER`; return the first SKIP." The orchestrator's own inline cascade
   (`orchestrator.py` ~1239-1540) is a sequence of `if <gate>: ...; continue` blocks — a
   candidate that fails gate #3 is **never evaluated against gates #4-15.** This is the
   actual lossy step CLAUDE.md's lesson C15 describes: every gate study to date measured
   its own isolated effect against a population an earlier gate may have already removed.

Additionally: every existing full-population replay (`day_report_card.py`,
`regime_participation_replay.py`, `ladder_fullhist_replay.py`) is explicit about being
**bear-side, level-tied-only.** `is_ladder_candidate` hard-requires `bull_passed is False`.
None of them cover bull candidates or the bear trendline-only shape (89% of real bear
entries) at all.

**New instrumentation, zero duplicated logic:**

- **Gate layer:** `evaluate_gates_full()` (`backtest/tools/frequency_ceiling_cascade_2026_08_03.py`)
  calls the REAL, unmodified `evaluate_gates` repeatedly — get the first-firing gate,
  neutralize *only* that gate's own param to its documented "off" value, call again, repeat
  until none fire. Every predicate is still gates.py's own code; there is no second copy to
  drift. **Cross-validated live, this run: 321/321 (100%) of the real sequential run's own
  logged first-SKIP actions matched this peel-off's first element** — the ordering is
  provably faithful to production, not just to `evaluate_gates()` in isolation.
- **Quality lock** is stateful (depends what already fired earlier that day on the same
  setup) — re-deriving it independently would mean reimplementing ~100 lines of
  path-dependent state at real risk of drift. Instead: read the REAL verdict off the same
  run's own `r.decisions` log. Reported as its own bucket (a lock, not a veto — a different
  mechanism class, kept visibly distinct everywhere).
- **Both sides, plus bear trendline-only:** a new monkeypatch captures BOTH
  `SetupResult`/`BullishSetupResult` objects (not just a boolean) on every bar. Bear
  trendline-only candidates (`trendline_rejection` present, no level-tied trigger) don't
  expose their own price on `SetupResult` — backfilled via a direct, read-only re-call to
  `detect_trendline_rejection_bearish` (the exact function production calls, same inputs) —
  **0 of 410 trendline-only candidates failed to re-derive their level.**
- **Counterfactual $:** every sole-blocker cohort priced through the SAME real-OPRA + real
  `exit_manager_walk.walk_exit_manager` pipeline every trusted study in this repo uses
  (structure-stop, `RIBBON_RIDE` exit shape, entry+1-at-OPEN, min 3 contracts, ATM strike).
  **Oracle, hindsight, NOT achievable, NOT one-position-at-a-time** — same disclosed
  convention as `day_report_card.py`'s own oracle walks.

**Window:** 2025-01-02..2026-07-27 (390 RTH days), same data merge as
`ladder_fullhist_replay.py`/`day_report_card.py` — chosen for anchor-comparability over
maximum recency (this is a structural-architecture question, not a recency-sensitive edge
question). Full runtime: 92.3s. Tool: `backtest/tools/frequency_ceiling_cascade_2026_08_03.py`.
Raw output: `analysis/deep-research/FREQUENCY-CEILING-2026-08-03.json`.

**Anchors (sanity checks before trusting anything downstream):**

| Check | Value |
|---|---:|
| Raw entries (`r.trades`) | 210 |
| Qualifying candidates (score≥8, both sides + bear-trendline) | 7,492 (bear 2,822 incl. 410 trendline-only; bull 4,670) |
| Bear-only level-tied floor-8 count (published ladder-replay anchor) | 2,308 (this run: 2,412 level-tied bear — 4.5% off, consistent with the codebase's own pre-existing cross-artifact drift, e.g. 191 vs 194 trades / $4,808.75 vs $5,306.95 between `engine_fullhist_replay.py` and `ladder_fullhist_replay.py`; not chased further here, does not affect this study's conclusions) |
| Status counts | FILTER_BLOCKED 6,766 · GATE_BLOCKED 559 · ENTERED 167 |
| Gate-order cross-check | **321/321 matched (100%)** |
| Trendline backfill | **0 of 410 dropped** |

**Known, disclosed scope limit:** ENTERED-status candidates (167) undercount raw entries
(210) — the residual 43 are entries via SUPER/ELITE trigger combinations at bars this
study's candidate definition doesn't happen to tag, plus routing/tie-break edge cases. This
is a large improvement over the bear-only, level-tied-only convention (which would have
undercounted by 136, not 43) but not perfect reconciliation — disclosed, not hidden, and
does not affect the blocked-candidate analysis below (which doesn't depend on this count).

---

## 2. The gate-overlap matrix

### 2a. All layers (filters + named gates + quality_lock), n_blocked = 7,325

| Blocked by exactly N reasons | count | % of blocked |
|---|---:|---:|
| 1 (sole blocker) | 2,506 | 34.2% |
| 2 | 3,560 | 48.6% |
| 3 | 1,259 | 17.2% |

**Reading this straight:** two-thirds of everything the engine ever refuses is refused for
MULTIPLE independent reasons at once. Removing any single filter rescues, at most, its own
sole-blocked slice — the other 65.8% stays blocked by something else. The naive "gate X
blocked N candidates, therefore removing it is worth ~N trades" arithmetic every prior
single-gate study implicitly used **overstates the achievable frequency gain** by roughly
3x on average.

### 2b. Gate layer only — post-filter, post-routing (the genuinely novel cut), n_blocked = 559

Candidates that already cleared every filter AND won routing (would have been real trades
but for a named gate or the quality lock):

| Blocked by exactly N named gates | count |
|---|---:|
| 1 (sole blocker) | 389 (69.6%) |
| 2 | 158 (28.3%) |
| 3 | 12 (2.1%) |

This inverts §2a's picture: at the point candidates have already survived the filter layer,
**named gates mostly stand alone** — they are not just piling onto candidates something
else already killed. This is the population where relaxing a specific gate has the most
leverage (routing_loss — both sides passing but tied — is a separate, rare, 0-count bucket
this run, excluded from gate stats per its own mechanism, not a gate).

**Sole-blocker leaderboard, gate layer:**

| Gate | n SOLE | n appears at all | % of appearances that are SOLE |
|---|---:|---:|---:|
| `block_elite_bull` | 175 | 247 | 70.9% |
| `quality_lock` | 130 | 238 | 54.6% |
| `vix_bear_hard_cap` | 26 | 103 | 25.2% |
| `entry_bar_body_pct_min` | 23 | 48 | 47.9% |
| `block_level_rejection` | 21 | 44 | 47.7% |
| `block_bull_1100_1200` | 14 | 61 | 23.0% |

**Top co-firing pairs, gate layer:** `quality_lock`+`vix_bear_hard_cap` (62 — the single
biggest gate-layer overlap) and `block_bull_1100_1200`+`block_elite_bull` (47 of
`block_bull_1100_1200`'s 61 appearances — this pair is **near-totally redundant**:
`block_bull_1100_1200`'s own marginal contribution beyond `block_elite_bull` is tiny).

### 2c. All-layers sole-blocker leaderboard (top 12, the population priced in §3)

| Blocker | n SOLE | n appears at all |
|---|---:|---:|
| `bear:filter_8` | 676 | 1,996 |
| `bull:filter_10` | 363 | 2,255 |
| `bull:filter_11` | 225 | 1,268 |
| `bull:filter_8` | 183 | 1,527 |
| `block_elite_bull` | 175 | 247 |
| `bull:filter_5` | 173 | 1,618 |
| `quality_lock` | 130 | 238 |
| `bull:filter_6` | 113 | 993 |
| `bear:filter_5` | 85 | 441 |
| `bear:filter_1` | 74 | 161 |
| `bear:filter_9` | 64 | 944 |
| `bull:filter_1` | 40 | 223 |

Full leaderboard, pair matrix, and member counts: `FREQUENCY-CEILING-2026-08-03.json`
(`overlap_matrix_all_layers`, `overlap_matrix_gate_layer_only`). Note filter numbers are
**namespaced by side** (`bear:filter_8` and `bull:filter_8` are different predicates that
happen to share a number — bear's is "VIX>17.30 AND rising", bull's is "VIX<17.20 OR
falling" — conflating them would be a real bug, not a shortcut).

---

## 3. Sole-blocker cohorts — counterfactual $, real OPRA + real exit walk

Every cohort below is candidates whose FULL joint blocker set is exactly `{that one
blocker}` — the population where removing that ONE thing would have changed the outcome.
Priced independently (oracle, hindsight, no one-position-at-a-time sequencing — upper bound,
not a forecast). BH-FDR at q=0.10 across all 12 tested (one correction, many slices, per
task instruction).

| Blocker | n blocked | n priced | n days | total $ | $/trade | $/day-that-fires | WR | BH-sig |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| `bear:filter_8` | 676 | 556 | 159 | **−$19,712.30** | −$35.45 | −$123.98 | 25.2% | **YES (neg)** |
| `bull:filter_10` | 363 | 352 | 123 | +$2,929.55 | +$8.32 | +$23.82 | 28.7% | no |
| `bull:filter_11` | 225 | 222 | 87 | −$971.60 | −$4.38 | −$11.17 | 28.8% | no |
| `bull:filter_8` | 183 | 177 | 78 | **+$8,738.00** | +$49.37 | **+$112.03** | 36.7% | **YES (pos)** |
| `block_elite_bull` | 175 | 172 | 87 | −$2,168.10 | −$12.61 | −$24.92 | 22.1% | no |
| `bull:filter_5` | 173 | 167 | 76 | −$162.95 | −$0.98 | −$2.14 | 38.3% | no |
| `quality_lock` | 130 | 115 | 52 | **−$6,404.20** | −$55.69 | −$123.16 | 22.6% | **YES (neg)** |
| `bull:filter_6` | 113 | 112 | 44 | +$213.25 | +$1.90 | +$4.85 | 30.4% | no |
| `bear:filter_5` | 85 | 70 | 39 | −$993.70 | −$14.20 | −$25.48 | 35.7% | no |
| `bear:filter_1` | 74 | 71 | 34 | −$1,872.15 | −$26.37 | −$55.06 | 35.2% | no |
| `bear:filter_9` | 64 | 44 | 25 | +$283.50 | +$6.44 | +$11.34 | 27.3% | no |
| `bull:filter_1` | 40 | 40 | 23 | −$498.00 | −$12.45 | −$21.65 | 32.5% | no |

**Only three cohorts survive BH-FDR** — two reinforce existing doctrine, one is new:

- **`bear:filter_8` (VIX regime, bear side) — significant NEGATIVE.** The biggest, most
  rigorous confirmation yet that the bear VIX-regime gate should stay armed. Reinforces
  CLAUDE.md's own "ALL tested, ALL null or actively negative" verdict on this gate — this
  time from a full-population, sole-blocker-isolated lens rather than a whole-book sweep.
  This evidence should feed the already-frozen, not-yet-run
  `prereg-vix-regime-gate-archetype-2026-08-02.json` (ARM_A/ARM_B), not a new study.
- **`quality_lock` — significant NEGATIVE.** The anti-churn escalation lock (OP-17 GRIND:
  block re-entry on a setup today unless a strictly stronger trigger fires) is earning its
  keep — letting these 115 priced "would-be second entries" through would have cost
  **−$123.16 per day it fires.** Confirms the design intent, not a relaxation candidate.
- **`bull:filter_8` (VIX gate, bull side) — significant POSITIVE.** See §4/§6 — the one
  finding worth a real A/B.

**`block_elite_bull` caveat (important, read before citing this number anywhere):** this
cohort's 87 days run **2025-01-16 through 2026-07-22 — 100% before the 2026-07-27
levels-v2 fix**, zero overlap with the active post-fix trial
(`FRIDAY-DIAL-IN-2026-07-31.md` Lane 1, n=5, +$867, drop-best +$177.40, currently running
on bold-2 with its own kill criterion). These are **not the same population** and this
number does **not** contradict that trial — J's own standing recency-over-aggregate
directive means the small recent post-fix sample stays the operative signal, this large
pre-fix number is context for that trial's tracker, nothing more.

---

## 4. `bull:filter_8` — the one cohort worth a real look

**The gate:** `evaluate_bullish_setup`, filter 8 — `vix_now < 17.20 OR VIX falling`, else
hard block. **Unlike bear's filter 8, bull has NO soft-mode escape valve at all today** —
confirmed by reading the full function signature (no `vix_soft_mode` parameter exists on
the bull side).

**What the sole-blocker cohort is:** bull reclaim setups where VIX was neither low nor
falling — elevated-or-rising VIX, but still under bull's separate hard cap of 22.0 (a
candidate hit by both filter_8 and filter_9 shows up in the 2+ overlap bucket, not here).
Plausible mechanism: a short-covering / capitulation-bounce shape rather than a calm-market
continuation — sharper, faster moves that suit 0DTE optionality even though the entry
"looks wrong" on a naive low-VIX-only heuristic.

**The number, restated:** n=183 sole-blocked candidates / 78 distinct days / **69 of those
78 (88.5%) currently have ZERO entries at all** (not cannibalizing an existing trading day
— filling an empty one) / +$8,738.00 total / +$49.37 per trade / **+$112.03 per day it
fires** / WR 36.7% / survives BH-FDR.

**Why this is not shipped tonight:** this is an unsequenced oracle number. The real
question — does it survive being walked in ACTUAL chronological order, with
one-position-at-a-time discipline, quality-lock now also live, and the other 14 named gates
now also exposed to newly-passing bull candidates that used to be filtered out earlier — is
unanswered. The codebase's own recent history is a strong prior against oracle numbers
holding: 11 of 12 WEEKEND-TWELVE lanes NULLed on real re-testing; filter 5, shadow signals,
and shelf-hold-reclaim all looked interesting in isolation and died on contact with
sequencing. **Pre-registered, not shipped — see §6.**

---

## 5. AXIS 2 — the no-trade-day scan that found nothing to scan

**Method (new):** for every day with zero qualifying candidates on either side,
`clean_move_candidates()` scans every level the engine itself was tracking that day
(`ctx.levels_active`/`ctx.multi_day_levels`, captured at replay time — the engine's own
level set, not re-derived) for a touch-then-clean-break (tolerance touch + a decisive
next-bar close beyond the level + does not give back ≥50% of the run within 60 minutes) —
generalizing `MULTIDAY-STRUCTURE-2026-07-31.md`'s hand-run, one-level, one-week touch-ledger
into a reusable, code-driven scan (every level, every day). The day's best candidate
(hindsight) would be walked through the same real exit-manager pipeline as §3 and classified:

- **`NOTHING_TRADEABLE`** — no clean-break candidate cleared the $100 FOCUS_DAILY_FLOOR even
  with hindsight, or none existed. → task's (a).
- **`DETECTOR_FIRED_WEAK`** — a clean move cleared the floor and some real trigger (shadow
  triggers deliberately excluded — see caveat below) fired within 2 bars of its origin.
- **`NO_DETECTOR_GENUINE_GAP`** — a clean move cleared the floor and NOTHING fired near it.
  → task's (c).

**Result: the input population is empty.** `day_participation_counts`:
**GATE_BLOCKED_DAY 267 (68.5%) + ENTERED 123 (31.5%) = 390. Zero NO_VOCABULARY. Zero
CORRECTLY_FLAT.** Extending candidate generation to bull AND bear-trendline-only (§1) closed
every gap the bear-only, level-tied-only lens left — including the 2/389 NO_VOCABULARY and
~80/389 CORRECTLY_FLAT days the prior bear-only `REGIME-PARTICIPATION-2026-08-02.md` study
found. On every single trading day in 1.5 years, SOME setup on SOME side reached score≥8
with a real trigger.

**This is the answer to AXIS 2, stated plainly:** the frequency ceiling is not a
missing-trigger-type problem at the "does the engine ever generate a candidate" level. It
is entirely a §1-§3 gating problem. `clean_move_candidates`/`oracle_scan_no_trade_day` are
built, guard-tested (13 pure-function tests, RED-proofed), and ready to run the moment a
genuine no-candidate day appears in a future window — they simply have nothing to classify
in this one.

**Caveat, stated once, applies everywhere in this section:** "qualifying candidate" here
means score≥8 + a real (non-shadow) trigger — a coarse bar. It says nothing about whether
that candidate was a GOOD trade, whether it fired at the RIGHT bar, or whether a smarter
confirmation would have caught the move earlier/better. Shadow triggers
(`trendline_reclaim`, `wick_reclaim`, `pullback_hold`) are excluded from
`detector_fired_near` on purpose — `INERT-SIGNALS-2026-07-31.md` already measured
`trendline_reclaim` significantly NEGATIVE and `wick_reclaim` negative-not-significant as
entry triggers; a day one of those fired near a big move is evidence of an
already-quarantined signal being present, not evidence of a vocabulary gap. See §7 for the
finer-grained (and genuinely still-open) version of "vocabulary gap."

---

## 6. Pre-registered — `bull:filter_8` soft-mode (NOT run, NOT armed)

**`analysis/recommendations/prereg-bull-vix-soft-mode-2026-08-03.json`**, frozen
**2026-08-02 11:58:55 ET** (`et_clock.py`), before any run.

This is deliberately **not** a new, competing study. `analysis/recommendations/
prereg-vix-regime-gate-archetype-2026-08-02.json` (frozen 2026-08-01, not yet run) already
covers filter_8 comprehensively — bear-side soft-mode (ARM_A) and a symmetric full delete
touching both sides (ARM_B) — and its own text explicitly reserves a bull-specific soft-mode
as a deferred follow-up: *"If ARM_A/ARM_B's results suggest the bull side specifically is
where the value is, a follow-up prereg should scope that new flag on its own, gated by this
study's findings, not bundled in blind."* This document's §3-§4 finding is exactly that
trigger condition. **The new prereg is that follow-up** — narrower, and honest that it
requires one new parameter (`vix_soft_mode_bull`, a direct structural mirror of bear's
already-shipped `vix_soft_mode`) rather than the sibling prereg's zero-new-code arms.

**Recommended order for whoever picks this up:** run the sibling prereg first (zero new
code, already frozen, sitting idle) — if its ARM_B (symmetric delete) already clears every
gate, this follow-up may be superseded outright (flagged as `G0` in the new prereg, reported
not gated). If ARM_B fails or under-delivers on the bull side specifically, this document's
ARM_C is the next thing to build and run.

**Gates (frozen, mirror the sibling prereg's convention):** G1 recent-25-day delta > 0
(primary) · G2 day-majority positive · G3 survives drop-best · G4 runner-cohort no
regression (≥95% of control, zero tolerance) · G5 fire-count floor (≥10 full-pop, ≥2
recent). Ships only if all five pass. **Not run. Not armed. No J needed to run or graveyard
it — paper only; live-money arming of bull entries already needs J under OP-16 regardless.**

---

## 7. Ranked frequency levers, with measured cost

| # | Lever | Measured effect | Confidence | Cost to pursue |
|---|---|---|---|---|
| 1 | **Run the already-frozen `prereg-vix-regime-gate-archetype-2026-08-02.json`** (bear/both-sides filter_8 soft-mode + delete) | Sitting idle since 2026-08-01. This study's `bear:filter_8` number (−$19,712/159 days, BH-sig) predicts ARM_A/bear-side will likely fail G1; ARM_B's bull-touching half is untested by that study alone | High confidence the bear half fails; genuinely unknown for the bull-touching half | **Zero new code** — just execute the frozen spec. Cheapest lever on this list. |
| 2 | **`bull:filter_8` soft-mode** (this study, §6) | Oracle: +$112.03/day-that-fires, ~78/390 days (20%), 69 currently-empty. BH-significant on the oracle number | Medium — real, statistically significant signal, but UNVALIDATED against sequential re-entry; codebase's own base rate for oracle→real survival is ~1-in-4 to 1-in-12 this session's own citations | One new parameter (mirrors existing bear pattern, low implementation risk) + a full sequential A/B run (not done this session) |
| 3 | **`bull:filter_10` (buyer pressure bar) relaxation** | Oracle: +$23.82/day-that-fires, 123 days | Low — positive but did NOT survive BH-FDR at n=352 | Would need its own prereg; not written this session given the lower signal strength — flagged, not built |
| 4 | **Anything else in the sole-blocker leaderboard** | `bull:filter_11`, `block_elite_bull` (pre-fix era), `bull:filter_5`, `bear:filter_5`, `bear:filter_1`, `bull:filter_1` all negative-or-immaterial; `bear:filter_9` near-zero | — | **Not recommended.** These gates are either net-negative to relax or too small to matter — reported for completeness, not proposed. |
| 5 | **The multi-blocked (2+) population itself** — 65.8% of all filter-layer blocks | Removing any ONE gate only rescues its sole-blocked slice; naive per-gate "total blocked" counts overstate achievable gains ~3x | High confidence as a NEGATIVE result — this closes off "stack several gate loosenings together" as an easy win, since most candidates a second gate would also catch are already caught by the first | N/A — this is a finding, not a lever |
| 6 | **Wire `crypto/lib/market_structure.py`'s HH/HL/BOS/CHoCH into entry-side confirmation** (currently used ONLY for the backward-looking day-trend veto — J-MARKET-PHILOSOPHY.md Gap 2) | **Untested as an entry mechanism.** Genuinely open — the only item on this list with no prior measurement either way | Low-to-unknown, and it shares philosophical DNA with an already-double-NULLed attempt (see caveat below) | New wiring work + its own pre-registered A/B — a real, multi-session build, not a knob flip |

**Caveat on lever #6, stated plainly because it would be easy to oversell:** the SAME
direction — replace lagging EMA/ribbon confirmation with real-time structure-shift
confirmation at levels — was already built and tested TWICE this year
(`structure-shift-cascade-ab-2026-07-28.md`: 1/5 gates passed, G1 delta −$46.00;
`structure-shift-replay-2026-07-28.md`: 1/5 gates passed, G1 negative) using
`backtest/lib/structure_shift.py`'s narrower "prior rejection bar, then a confirming bar"
predicate. **Both DO_NOT_ARM.** `market_structure.py`'s broader HH/HL/LH/LL/BOS/CHoCH
framework is a genuinely different, more general implementation — not strictly "the same
thing a third time" — but anyone picking up lever #6 should read both prior nulls first and
have a clear hypothesis for why THIS implementation differs before spending the build time.

---

## 8. Guards, RED-proofs, disclosures

- **13 pure functions, 37 tests**, `backtest/tests/test_frequency_ceiling_cascade_2026_08_03.py`:
  `neutral_gate_params`, `evaluate_gates_full` (peel-off correctness, including a case where
  the short-circuiting `evaluate_gates()` would report only the FIRST of two independently-
  firing gates and this function correctly reports both, in `GATE_ORDER` order),
  `namespaced_filter_blockers`, `derive_winning_side` (6-case parametrized, matches
  `orchestrator.py`'s tie-break exactly including the tie→conflict-skip branch),
  `build_overlap_matrix`, `one_sample_p`/`bh_fdr` (textbook step-up boundary case),
  `classify_a_vs_c`, `clean_move_candidates` (clean bounce / rejected chop-retrace / no-touch
  cases), `levels_seen_for_day`, `detector_fired_near`.
  ```
  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_frequency_ceiling_cascade_2026_08_03.py -q
  37 passed
  ```
- **RED-proofed live, this session:** flipped `derive_winning_side`'s tie comparison (`>` →
  `>=`) and `build_overlap_matrix`'s sole-blocker condition (`== 1` → `>= 1`) — both targeted
  tests failed exactly as expected (2 failed / 31 passed), both mutations reverted, full
  37-test suite green again. Three additional tests directly assert defensive-guard behavior
  (unregistered-gate-id RuntimeError, empty-blocker-set ValueError, bear/bull namespace
  non-collision).
- **Cross-validation, not just unit tests:** the gate-order peel-off's agreement with the
  REAL sequential run's own logged first-SKIP action was checked on every one of the 321
  candidates where a comparison was possible — **321/321 (100%)**, live, this run, not a
  fixture.
- **BH-FDR (q=0.10)** applied to all 12 sole-blocker cohorts tested in §3 — one correction
  across many slices, per task instruction.
- **Real-OPRA fills only** for every $ figure; BS-synthetic candidates counted and disclosed
  per cohort (`n_synthetic_excluded` column, §3), never blended into a total.
- **Everything in this document is descriptive.** Nothing is armed. The one actionable item
  (§6) is frozen as a pre-registration for a LATER session, per task instruction — not run
  tonight.

---

## 9. What's next (ranked, for whoever picks this up)

1. Execute the already-frozen `prereg-vix-regime-gate-archetype-2026-08-02.json` (zero new
   code, cheapest lever, has been sitting idle since 2026-08-01).
2. Build `vix_soft_mode_bull` per `prereg-bull-vix-soft-mode-2026-08-03.json`'s exact spec
   and run ARM_C against the frozen gates.
3. If both of the above null, the honest read is that gate-layer relaxation is exhausted for
   now, and lever #6 (market_structure.py wired into entry confirmation) is the only
   remaining genuinely-untested axis — budget it as a real multi-session build with its own
   pre-registration, not a quick knob flip, and go in with the two prior structure-shift
   nulls already read.

---

_Sources: `backtest/tools/frequency_ceiling_cascade_2026_08_03.py` (new) ·
`backtest/tools/frequency_ceiling_report_2026_08_03.py` (new, table rendering only) ·
`analysis/deep-research/FREQUENCY-CEILING-2026-08-03.json` (new, raw output) ·
`backtest/lib/engine/gates.py` · `backtest/lib/filters.py` ·
`backtest/tools/ladder_fullhist_replay.py` · `backtest/tools/day_report_card.py` ·
`analysis/deep-research/REGIME-PARTICIPATION-2026-08-02.md` ·
`analysis/deep-research/WEEKEND-TWELVE-2026-08-01.md` ·
`analysis/deep-research/ONE-POSITION-CONSTRAINT-COST-2026-08-02.md` ·
`analysis/deep-research/FRIDAY-DIAL-IN-2026-07-31.md` ·
`analysis/deep-research/INERT-SIGNALS-2026-07-31.md` ·
`analysis/deep-research/MULTIDAY-STRUCTURE-2026-07-31.md` ·
`markdown/doctrine/J-MARKET-PHILOSOPHY.md` ·
`analysis/recommendations/structure-shift-cascade-ab-2026-07-28.md` ·
`analysis/recommendations/structure-shift-replay-2026-07-28.md` ·
`analysis/recommendations/prereg-vix-regime-gate-archetype-2026-08-02.json` ·
`analysis/recommendations/prereg-bull-vix-soft-mode-2026-08-03.json` (new)._
