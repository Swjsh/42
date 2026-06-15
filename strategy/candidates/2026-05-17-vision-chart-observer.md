# Strategy candidate: VISION_CHART_OBSERVER

> DRAFT — autonomous wake-fire scaffold 2026-05-17. J ratifies live observation start.
>
> **Work item:** A new OBSERVER-ONLY chart-reading layer that runs alongside the heartbeat,
> captures the SPY 5m chart screenshot each tick, sends it to a vision-capable Claude (haiku),
> and emits a structured judgment ("bull / bear / chop / unclear" + confidence + grounding
> notes). Outputs are graded EOD against next-bar truth.
>
> **Hypothesis class:** chart-reading-skill — does Claude SEE chart features (in-progress
> patterns, level interactions, momentum acceleration) that the closed-bar filter framework
> is structurally blind to?
>
> **NOT a new entry trigger.** NOT a doctrine modification. NOT a relaxation of any v15.1
> rule. The candidate's ONLY runtime effect during the observation phase is one new file
> growing append-only (`vision-observations.jsonl`) plus one new EOD scorecard
> (`analysis/vision-vs-heartbeat-{date}.json`).

---

## Hypothesis

In DIVERGED ticks — where the vision observer's `q5_direction_call` differs from the
heartbeat decision's mapped direction (ENTER_BULL→bull, ENTER_BEAR→bear, HOLD/SKIP→chop) —
the vision call is correct on the next-5m-bar by a margin of at least 10pp vs the
heartbeat call.

The driving belief is that the closed-bar rule (v15.1 R1, ratified 2026-05-14 evening)
correctly prevents the in-progress-bar misalignment foot-gun on the BULL side (the 5/14
09:58 +$913 winner was structurally premature per `docs/R4-HEARTBEAT-MISALIGNMENT-2026-05-14.md`)
but at the cost of waiting the full 5-min bar even when the forming candle is obvious to
a human trader. The 5/15 −$770 fast-V loss is the canonical foot-gun on the BEAR side.

If H1 is true, a NARROW vision-veto branch added to heartbeat doctrine after the 20-day
observation phase could capture a measurable share of the fast-V foot-guns without
re-introducing the in-progress-bar misalignment risk.

---

## Backtest evidence

> **Caveat upfront (per OP-20 disclosure #3):** ZERO historical backtest evidence. This
> candidate is a NEW observation surface — there is no historical "vision observations" log
> to backtest against. The 20-day observation phase IS the data-gathering phase. After
> 20 days the grader's aggregate `vision_minus_heartbeat_diverged_pp` is the primary
> evidence base.

| Claim | Evidence | Source |
|---|---|---|
| Vision prompt schema valid + produces parseable JSON | sample record in `automation/prompts/chart_vision_observer.md` Sample output section | scaffold |
| Grader pairs vision obs with heartbeat decisions correctly | pair_observations logic by tick_id within date | `backtest/autoresearch/vision_observer_grader.py` |
| Grader grades on next-bar SPY close from master 5m CSV | `_load_spy_bars_for_date` + `_next_bar_close_after` | same |
| Per-day scorecard writes to `analysis/vision-vs-heartbeat-{date}.json` | `write_output=True` path | same |
| EOD pipeline integration is fail-soft (one stage failure cannot crash EOD) | Stage 4a.7 wrapped in try/except | `backtest/autoresearch/eod_deep/main.py` Stage 4a.7 |

### What the observer will produce on day 1 of live observation

Per the schema in `chart_vision_observer.md`:

```json
{"schema_version":"1.0.0","tick_id":47,"date":"2026-05-18","time_et":"09:42:30","screenshot_path":"C:\\Users\\jackw\\Desktop\\42\\automation\\state\\vision-snapshots\\2026-05-18\\tick_047.png","symbol":"SPY","timeframe":"5","price_now":738.92,"session_high":740.20,"session_low":738.62,"vix_now":18.45,"q1_price_action_now":"SPY trading 738.92, the 09:40 bar in progress is forming a long lower wick down to 738.62 then bouncing — looks like a hammer testing PML 739.04 from below.","q2_in_progress_pattern":"hammer_forming","q3_level_interaction":{"named_level":"PML 739.04","interaction":"holding_below","distance_dollars":-0.12},"q4_momentum":"fading_down","q5_direction_call":"bull","q5_horizon_minutes":10,"q6_confidence_1_10":6,"q6_what_would_change_my_call":"a close below 738.50 with rising volume would flip me bear — the hammer wick needs follow-through on the 09:45 close to confirm.","grounded_against_ohlcv":true,"model_used":"haiku","elapsed_seconds":17}
```

### Edge-capture impact (J's source-of-truth days)

NOT MEASURABLE during observation phase. Vision does NOT modify any heartbeat decision.
The grader records what vision SAID for each tick on those days — but the heartbeat's
P&L is unchanged. The earliest meaningful comparison is post-promotion, IF the gate passes.

| Day | J trade | J P&L | Engine impact from VISION_CHART_OBSERVER (observation phase) |
|---|---|---:|---|
| 2026-04-29 | SPY 710P × 6 | +$342 | UNCHANGED — vision is observer-only |
| 2026-05-01 | SPY 721P × 20 | +$470 | UNCHANGED |
| 2026-05-04 | SPY 721P × 10 | +$730 | UNCHANGED |
| 2026-05-05 | SPY 722P × 20 | -$260 | UNCHANGED |
| 2026-05-06 | SPY 730P × 10 | -$300 | UNCHANGED |
| 2026-05-07 | SPY 734C × 3 | -$45 | UNCHANGED |
| 2026-05-07 | SPY 737C × 10 | -$120 | UNCHANGED |

**Honest tension:** because this is a pure observation layer, the candidate cannot affect
edge_capture during its first 20 days. The candidate's value is the DATA the layer
produces, not P&L impact. Per OP-16, candidates with `edge_capture < 771` are normally
REJECTED at the door. This candidate is an exception under OP-21 watch-first promotion —
it produces NO immediate edge_capture but is the OBSERVATION SURFACE needed to evaluate
future doctrine changes. Filed for J's awareness; rank #3 on `_LEADERBOARD.md`.

### Projected aggregate (post-observation, only IF promotion gate passes)

- **edge_capture estimate:** PLACEHOLDER — measurable only AFTER 20-day observation phase
  IDENTIFIES specific DIVERGED patterns where vision was right and heartbeat was wrong.
  Per the promotion gate (OP-21) the promotion would convert to a narrow `vision_veto`
  filter — at that point, an OPRA-real-fills replay of the v15.1 production heartbeat WITH
  the vision_veto applied vs WITHOUT can produce a measurable edge_capture delta on the
  16-month dataset.
- **edge_capture floor (771) status:** PLACEHOLDER — NOT measurable during observation phase.
- **aggregate sharpe:** PLACEHOLDER.
- **final_score:** PLACEHOLDER.

---

## Disclosures (per OP-20)

1. **Account-size assumption.** PLACEHOLDER. The observer layer does NOT touch sizing. The
   downstream vision-veto branch (if promoted) would inherit v15.1's per-tier sizing exactly.
   No sizing knobs proposed.

2. **Sample-bias disclosure.** ZERO historical evidence — the observer is a NEW surface so
   the 20-day live phase IS the first sample. Risk: vision accuracy on observed days may
   not generalize to unobserved market regimes (low-vol days, holiday-shortened sessions,
   FOMC-day chop). Per OP-21 the promotion gate explicitly requires 20+ trading days AND
   a minimum of 50 DIVERGED-only ticks to mitigate small-sample lookahead bias. Sweep
   recommendations after 20 days:
   - Per-VIX-bin accuracy (does vision skill vary with regime?)
   - Per-confidence-bin calibration (is Q6 1-10 honest?)
   - Per-pattern accuracy (does Q2 in_progress_pattern predict next-bar direction better
     than chance for bars where Q2 ≠ "none"?)

3. **Out-of-sample test result.** NOT RUN. The candidate enters live observation as
   in-sample data collection. There is no held-out window during observation phase.
   Post-promotion, walk-forward validation of any proposed vision_veto branch is
   mandatory per OP-20 default pipeline.

4. **Real-fills check.** N/A during observation phase — no fills attempted. Post-promotion,
   any vision_veto branch must be validated via `simulator_real.py` against OPRA bars,
   per the 2026-05-13 BS-sim-retirement lesson (OP-25 entry).

5. **Failure-mode enumeration.**
   - **Wrong-direction call into TP1.** N/A — observer makes no entry.
   - **Vision misreads chart annotations as price action.** Mitigated by the prompt's
     6-question framework forcing pattern recognition vs annotation recognition.
   - **Vision over-confidence on chop days.** Mitigated by the calibration secondary
     hypothesis (H3) — Q6 confidence ≥ 8 must outperform Q6 ≤ 5 by > 25pp; if not,
     post-promotion the vision_veto branch is gated on `confidence ≥ 8` only.
   - **Cost overshoot.** Mitigated by per-tick budget ceiling ($0.15), monthly auto-disable
     at $80, half-cadence default deployment (every 2nd heartbeat tick).
   - **TV CDP contention with heartbeat.** Mitigated by the wrapper's heartbeat-busy yield
     gate (30s wait, then skip-tick if still busy).
   - **Vision prompt injection via chart annotation.** Mitigated by the prompt's explicit
     refusal protocol — emits `direction_call: "unclear"` + flag in `what_would_change_my_call`.
   - **Idempotency failure (same tick observed twice).** Mitigated by wrapper Gate 4
     (tail-50 scan of JSONL for matching tick_id+date).

6. **Concentration.** N/A — observer layer is per-tick. No P&L distribution to concentrate.
   Post-promotion the vision_veto branch would inherit concentration disclosure from the
   target setup it's vetoing (likely BEARISH_REJECTION_RIDE_THE_RIBBON given the 5/15
   foot-gun motivation).

---

## Knob changes proposed (DRAFT only — Chef does NOT edit params.json)

During the observation phase: ZERO knob changes. The observer reads chart, emits JSON,
exits. No state mutation, no params changes, no doctrine edits.

Post-promotion (only if 20-day gate passes per OP-21), proposed `params.json` additions
under a new `v16_vision_veto` sub-object:

```json
"v16_vision_veto": {
  "enabled": false,
  "min_vision_confidence": 7,
  "max_horizon_minutes": 10,
  "veto_directions": ["bull_when_vision_says_bear", "bear_when_vision_says_bull"],
  "max_veto_count_per_session": 5,
  "fallback_action_on_veto": "delay_one_tick_and_re_evaluate"
}
```

Open J questions per VISION-OBSERVER-PROTOCOL.md §9:
- (Q-A) Observation cadence — half-cadence ($67/mo) vs full-cadence ($133/mo) vs HOT-only ($30/mo)?
- (Q-B) Vision blackout window — match heartbeat 09:35-15:00 ET only, or extend to 09:30-15:55 ET?
- (Q-C) Pre-capture screenshot via Python TV MCP client (cleaner, $0.02 savings) vs prompt-captures-itself (simpler scaffold)?
- (Q-D) `data_get_ohlcv` grounding cadence — always vs only-when-confidence-low?

---

## Pre-merge gate

NOT APPLICABLE during observation phase — the observer does not touch production state, doctrine,
or filter logic. Pre-merge gates only apply when (and if) promotion occurs.

Post-promotion pre-merge gates:

| Gate | Threshold | Source |
|---|---|---|
| `python crypto/validators/runner.py` | 29/29 PASS | OP-26 |
| `python backtest/autoresearch/vision_observer_grader.py --date {today}` | exits 0 | scaffold |
| EOD Stage 4a.7 has run on ≥ 20 trading days | grader output files count | `analysis/vision-vs-heartbeat-*.json` |
| `_LEADERBOARD.md` row reflects POST-OBSERVATION evidence (not PLACEHOLDER) | leaderboard edit | this file |

Pre-merge gate during observation phase (light):
- `python -m autoresearch.vision_observer_grader --date {today}` must exit 0 each EOD. If
  exit non-zero, surface to `STATUS.md` known-broken section. Does NOT auto-disable observation.

---

## My confidence (1-10) and why

**3/10.**

**Why this low (not 5+):**
- ZERO historical evidence. Pure prospective observation surface — could fail completely on
  Day 1 (e.g., the chart screenshot is unreadable; the level lines are too thin for vision
  to see; the in-progress bar identification is unreliable).
- The hypothesis is highly speculative. The closed-bar rule WAS introduced for a real reason
  (R1 fix prevented +$913 winner from being scored on a phantom in-progress bar). Adding ANY
  in-progress-bar-aware layer is re-introducing the class of risk that R1 was designed to
  eliminate. The OBSERVATION SURFACE is safe (zero state mutation) but the FUTURE doctrine
  branch (if promoted) is structurally risky.
- The grader's signal-to-noise on Day 1 will be very weak. ~50 ticks/day, of which maybe
  10-20 are DIVERGED, of which maybe 5-15 are gradable (next-bar close exists and is not
  flat). A 20-day cumulative DIVERGED-graded sample of 100-300 ticks is the minimum for
  any meaningful statistical signal.
- Vision-capable Claude haiku reading a complex chart with multiple indicators + drawing
  layers + level lines is an UNTESTED capability claim. The crypto harness validates the
  numeric primitives (OP-26); the vision capability is unvalidated.

**Why this not lower (not 1 or 2):**
- The scaffold is CHEAP to ship (~600 LOC across 5 files + 1 EOD wiring edit) and CHEAP to
  run during observation phase ($67/mo at proposed half-cadence — under OP-3 budget).
- The OBSERVATION SURFACE itself is safe by construction. The prompt has zero write authority
  to production state; the wrapper has zero authority to modify doctrine. The worst-case
  outcome from a buggy observation is a malformed JSONL line the grader skips with a warning.
- The grader's aggregate per-day scorecard is INFORMATIONALLY VALUABLE even if the H1
  hypothesis is rejected — it tells us whether Claude-vision can read SPY 5m charts AT ALL
  at the trader-eye level. That's a capability question relevant to many future features.
- The candidate is filed transparently with all 6 OP-20 disclosures (most as PLACEHOLDER —
  honest signal of where the gaps are).
- The promotion gate (OP-21) is strict — 20+ days, 50+ DIVERGED ticks, 10pp margin, J's
  explicit ratification, crypto-harness GREEN. If the hypothesis fails, the observation
  phase produces a permanent advisory artifact and the candidate quietly retires.

**Verdict: NEEDS-MORE-DATA — scaffold shipped; observation phase requires J's authorization
of task registration to start collecting first 20 trading days of data.**

---

## Next steps (J's call)

1. **Review the scaffold.** Files shipped (paths and LOC at bottom of this section).
2. **Authorize task registration.** When ready, run the 4-step install command per
   `docs/VISION-OBSERVER-PROTOCOL.md` §8.1. The `setup/install-chart-vision-observer.ps1`
   task-registration script is Stage 2 work (NOT shipped tonight per scaffold-only mandate).
3. **Pick observation cadence.** Q-A in §9 of the protocol doc. Recommend half-cadence to
   start (every 2nd heartbeat tick, $3.20/day, comfortably under OP-3 budget).
4. **Watch first week.** After 5 trading days of live observation, manually inspect
   `analysis/vision-vs-heartbeat-*.json` for one sanity-check: is vision producing parseable
   JSON every fire? Is the grader pairing correctly? Is the next-bar grading working?
5. **Day 20 promotion-path decision.** Run the aggregate-20-day scorecard (Stage 3 work,
   builds on the per-day scorecards). Apply the OP-21 promotion gate. If GREEN, propose
   the narrow vision-veto branch as a SEPARATE candidate spec.
6. **If RED at any check:** observation continues (cost-free informational artifact). No
   doctrine change. Candidate stays NEEDS-MORE-DATA indefinitely.

### Files shipped tonight (paths and approximate LOC)

| File | Lines | Purpose |
|---|---:|---|
| `automation/prompts/chart_vision_observer.md` | ~110 | Vision-reading system prompt (the OBSERVER prompt) |
| `setup/scripts/run-chart-vision-observer.ps1` | ~125 | Wrapper PS1 (gating + idempotency + heartbeat-yield + invoke) |
| `backtest/autoresearch/vision_observer_grader.py` | ~370 | EOD grader (pairs vision vs heartbeat vs next-bar truth) |
| `backtest/autoresearch/eod_deep/main.py` | +30 (Stage 4a.7) | EOD pipeline wiring (calls the grader nightly) |
| `docs/VISION-OBSERVER-PROTOCOL.md` | ~290 | Design doc (why, architecture, promotion path, J install steps) |
| `strategy/candidates/2026-05-17-vision-chart-observer.md` | ~250 | This candidate spec |
| `strategy/candidates/_LEADERBOARD.md` | +1 row | Leaderboard entry (row #3, NEEDS-MORE-DATA) |

**Total scaffold:** ~1175 LOC + 1 leaderboard row + 1 EOD wiring edit. Zero production
state files modified. Zero scheduled tasks registered.

---

_Vision prompt: `automation/prompts/chart_vision_observer.md`._
_Wrapper: `setup/scripts/run-chart-vision-observer.ps1`._
_Grader: `backtest/autoresearch/vision_observer_grader.py`._
_Design doc: `docs/VISION-OBSERVER-PROTOCOL.md`._
_Doctrine basis: CLAUDE.md OP-3 / OP-11 / OP-20 / OP-21 / OP-22 / OP-26 / OP-27._
