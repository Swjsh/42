# Conviction + Sit-Out design memo (Fable agent, 2026-08-12 evening) — Opus builds from this

**Mechanism:** a **CONVICTION SCORE (0-8)** per ENTER verdict, from producers already on disk,
gated by an **ESCALATING RATCHET**: entry k of the day requires `conviction >= 4 + (k-1)`
(k = the settlement ledger's existing `entries_used_today`, restart-safe, both core lanes).
The ratchet IS the sit-out: a day offering only conviction-3 signals is declined at k=0; a day
offering one clean level trade takes it and is then effectively done. One sentence for J: *the
engine required reasons to say NO; now the first trade needs four named reasons to say YES,
and every additional trade needs one more.*

## The load-bearing diagnosis (verified)

`bear_score = 10 - len(blockers)` (filters.py:1758), `bull_score = 11 - len(blockers)` (:1273).
**The score counts absent objections, not present reasons** — "38 reasons to trade" is the
architecture. bear_score carries NO conviction signal (floor-9 WR 0.238 < floor-7 WR 0.299,
LADDER-FULLHIST-2026-07-27), so the new score must be a NEW axis. And the inputs already exist:
on 08-12 key-levels.json held `MEMORY_RES_225 @773.06` (139 touches) and `MEMORY_SUP_162
@771.44` (96 touches) — J's exact shelf — plus a 4-source confluence zone at 770.48-771.44
(J's 12:35 bounce zone). **`heartbeat_core._read_levels` (line 412) flattens every record to a
bare float, discarding tier/touches/memory at the point of consumption.** The repeat-touch
scoring EXISTS (G11); the decision path strips it.

## Components (integer, side-specific, nullable→0 + degraded_components)

C1 (+2) NAMED LEVEL — verdict's level matches a non-expired key-levels RECORD (±$0.25) ·
C2 (+1) MULTI-DAY MEMORY (memory_score>=40 / multi_day) · C3 (+1) FRESH TEST (<=1 prior
rejection today, from `level_states` bounce_history) · C4 (+1) RANGE EXTREME (P: top 30% of
prior∪today envelope; C: bottom 30%) · C5 (+1) STRUCTURE AGREEMENT (sameday BOS/CHoCH agrees;
soft, never hard — blocking zero-structure cost Tue −$2,091) · C6 (+1) ELITE TRIGGERS
(confluence/sequence) · C7 (+1) ZONE STACK (confluence-zones n_sources>=3).
C2 scores the LEVEL's history, C3 the TEST's freshness (C25/L142 defense). **Do NOT use
`trend_alignment` (Phase-1 study killed it) or ER30 (frozen prereg; and it APPROVES 08-12).**
Weights are v0: calibrate on two origin exhibits — the 38 fills of 08-12 (most must fail
floor 4) and J's 12:35 bounce + edge-master source-of-truth winners (must pass) — then FREEZE
in a prereg before forward day 1.

## Plumbing (exact)

- `heartbeat_core.run_account`: new `SKIP_LOW_CONVICTION` elif AFTER `SKIP_EARLY_ENTRY`
  (~:1410), BEFORE the `_sight` walrus pair (do not split it). On block: rewrite
  `rec["verdict"]` (preserve original in `conviction_blocked_verdict`) — the rewrite is
  load-bearing because `build_shared_signal._map_core_row:119` feeds fleet arms from `verdict`,
  so ONE seam covers the whole book (blind-block precedent; per-arm opt-out via
  `hard_skip_verdicts`).
- `_read_levels` additionally returns parsed records (same read). engine_cli exposes the
  sameday structure classification additively (parity oracle untouched).
- New `conviction_shadow_counter.py` nightly (mirror regime_shadow_counter incl. PREREG_FROZEN
  discipline + built-in random-k null).
- Params `conviction_floor` / `conviction_ratchet_step`: absent = OFF = byte-identical.
  **Revert = delete the key.**
- Degradation contract: sensors fail OPEN (trade as today) + logger.critical + engine-health
  flag; unreadable ledger → k=0. A broken sensor can never cause silent all-day inaction.

## Ship gates (freeze before forward day 1)

F1 KILL: >=15 forward days AND >=25 would-blocked fills → blocked-cohort P&L <= p05 of a
20,000-draw day-stratified k-matched random-suppression null (simulate the ratchet FORWARD
over each day's verdict stream — only taken entries increment k; L235/L251 frame rule), AND
kept-cohort expectancy improves. F2: every edge-master source-of-truth winner + any J-called
winner in shadow must clear its k-position floor (one miss = KILL, OP-16). F3 (C27): floor-4
passing >80% or blocking >95% of ENTERs = DOA. F4: degraded ticks >20% = don't arm.
Secondary control: time-of-day-matched suppression. Disclose the NOT_FLAT confound (log
ENTER-at-NOT_FLAT during shadow).

## Build order (Opus)

1. Phase A tonight-able: conviction computation + shadow logging + `_read_levels` metadata +
   zero-behavior guard (style: test_context_bundle_tag_no_behavior_change).
2. Prereg (weights frozen on the two exhibits) + nightly shadow counter.
3. Arm on core after F1-F4; fleet inherits via the verdict rewrite.
4. Do NOT build: bear_score floors (refuted), budget-only caps, ER30 day-gates, time cooldowns.

## Unresolved (carry into the build)

- Reconstruct the as-of-12:35 level snapshot from core-decisions + git history of
  key-levels.json BEFORE freezing weights (if 771.4 memory was absent intraday, the fix is
  refresh cadence, not the score).
- C5 threading through engine_cli without disturbing parity.
- The safe-2 09:58 no-decision-row fill: a second execution path bypasses ANY gate at this
  seam — the sit-out has a hole until that lane is found.
- **POST-MEMO ADDENDUM (hold counterfactual, priced same night):** holding 08-12's positions
  to close = −$10,313 (all) / −$2,845 (one per arm/direction) vs churn's −$890 — entries were
  the loss mechanism under EVERY exit policy. This STRENGTHENS the entry-side design (C1/C4
  are the discriminators for J's 12:35-at-the-edge trade) and killed R3's exit-side option.
