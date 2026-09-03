# PREREG-DOUBLE-BOTTOM-LOOKBACK-AB-2026-09-03

**Status:** FROZEN — NOT RUN. Design committed before any forward outcome is computed.
No trading-path file is touched by this document or by executing it.

**Filed by:** Sonnet worker session (document-only), queue items `DOUBLE-BOTTOM-LOOKBACK-AB`
(MED) and `DB-BASE-QUIET-PROXIMITY-GATE-LEAD` (MED), `automation/overnight/queue.md`
lines 735-765 (both filed 2026-07-21 dojo overnight).

**Filed at ET:** 2026-09-03 04:57:46 Thursday EDT (`python setup/scripts/et_clock.py`).

**Supersedes:** nothing — first prereg for this item. The 2026-07-21 queue text explicitly
says "PROPOSAL (not wired)" and forbids hand-widening; this document is that pre-reg.

---

## Verified diagnosis (re-checked live today, not taken on the queue's word)

Both binding constraints named in the queue item still hold, verified fresh this session
(not copied from the 07-21 diagnostic's prose):

1. **RTH-only `prior_bars` construction — unchanged in substance, line numbers drifted.**
   `setup/scripts/heartbeat_core.py:898-903` (queue cited 551-556 — file grew since
   07-21; content identical):
   ```
   # RTH-ONLY (>=09:30, <16:00 ET) BEFORE anything -- the backtest computes its ribbon +
   # baselines on RTH-only bars (orchestrator.py:786-798, "matches the live indicator").
   ...
   df = df[(_ts.dt.time >= time(9, 30)) & (_ts.dt.time < time(16, 0))].reset_index(drop=True)
   ```
   `backtest/lib/orchestrator.py:819-830` (queue cited 798-803 — same drift):
   ```
   # Split: RTH-only (>= 09:30, < 16:00) for ribbon + baselines + evaluation.
   rth_mask = (
       (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
       & (spy_df_full["timestamp_et"].dt.time < dt.time(16, 0))
   )
   ```
   Both still exist, both still strip every premarket bar before `ctx.prior_bars` is ever
   built. This is the deliberate 2026-06-25 score-parity fix (42%→byte-identical replay) --
   this prereg does NOT propose touching it, per the queue item's own instruction.

2. **`double_bottom_detector` default lookback — unchanged.**
   `crypto/lib/chart_patterns.py:102`: `lookback: int = 20`. Docstring line 131: "how many
   recent bars to scan (default 20 = ~1h40m on 5m)" = 100 minutes. The watcher's only call
   site, `backtest/lib/watchers/double_bottom_base_quiet_watcher.py:192`
   (`hit = double_bottom_detector(bars)`), passes no `lookback` override -- confirmed today,
   not just quoted from the diagnostic.

3. **Watcher constants, unchanged.** `_WINDOW_BARS = 30` (watcher.py:97),
   `PROXIMITY_MAX_DISTANCE: float = 0.50` (watcher.py:94), Gate 6 proximity block at
   watcher.py:203-208 (`enrich_hit_with_proximity(..., max_distance=PROXIMITY_MAX_DISTANCE)`,
   blocks when `near_key_level is True`).

J's 07-21 gap (08:15 low -> 10:15 low) is 120 minutes = 24 bars; default lookback=20 (100 min)
is 20 minutes short, matching the queue's arithmetic exactly.

---

## Cells

All four cells are watch-only / shadow-only. None is wired into `heartbeat_core.py`,
`orchestrator.py`, `params.json`, or any armed watcher path. `_WINDOW_BARS` (30) already
covers every lookback value below, so no widening of the bars fed into the detector's frame
is needed beyond cell B's explicit premarket admission.

- **CONTROL** -- lookback=20, RTH-only `prior_bars` (today's live shape, unchanged).

- **Cell A** -- lookback=**26** (130 min), RTH-only `prior_bars` unchanged. Reasoning for the
  single chosen value (queue's own grid was {20 control, 30, 40, 60} -- this pre-reg commits
  to ONE cell rather than re-opening the grid): J's real gap is exactly 24 bars; 26 gives one
  bar (5 min) of slack past the exact gap without reaching for an arbitrary round number like
  30/40/60, which would each admit 30-100 extra minutes of unrelated history into the
  local-lows search and risk pulling in unrelated pivots (diagnostic Step 4 shows the
  algorithm always picks the LAST two local lows in the window -- a wider window changes
  candidate pairs, not just visibility). Threaded via an explicit
  `double_bottom_detector(bars, lookback=26)` kwarg at the watcher's one call site -- no
  change to `_WINDOW_BARS` (26 <= 30, already sufficient).

- **Cell B** -- lookback=20 (CONTROL), **premarket bars admitted to the detector's frame
  ONLY**. How, precisely: the watcher gains a second, parallel bar frame -- built inside
  `_build_bars_from_context` (or a sibling helper) from a premarket+RTH slice the caller
  supplies alongside `ctx.prior_bars`, e.g. a new `ctx.prior_bars_with_premarket` field
  populated ONLY where a caller chooses to (shadow harness, not the live payload builder) --
  and ONLY `double_bottom_detector`'s input (Gate 4) reads it. `heartbeat_core._build_payload`
  (heartbeat_core.py:898-903) and `orchestrator.py`'s `rth_mask` (819-827) are NOT touched --
  ribbon, baselines, VIX alignment, and every other watcher keep reading the existing
  RTH-only `ctx.prior_bars` exactly as today, preserving the 2026-06-25 parity fix
  end-to-end. This is a design spec only in this document -- not built, per this session's
  document-only scope.

- **Cell C** = A + B (lookback=26 AND premarket admitted to the detector's frame only).

- **Cell D** -- the `DB-BASE-QUIET-PROXIMITY-GATE-LEAD`, frozen as its own cell rather than
  folded into A/B/C: detector fire (CONTROL shape: lookback=20, RTH-only) **AND** a
  `levels_active` zone within a pre-registered proximity band. Band width is pre-registered
  at **$0.50**, matching the existing Gate 6 `PROXIMITY_MAX_DISTANCE` exactly, so cell D is a
  same-radius flip of the existing exclusion gate (NOT_NEAR_NAMED -> NEAR_NAMED) rather than
  a new, unvalidated band -- consistent with the "levels are ZONES not prices, pre-reg the
  band width" doctrine (J 2026-07-17, `feedback_levels_are_zones_2026_07_17`). Cell D is
  independent of cells A/B/C (it varies the proximity condition, not lookback/frame), so it
  is scored on its own line, never combined with A/B/C's grid.

---

## Populations

- **IS (disclosed as SEEN, not blind):** the 35-day scan the diagnostic already ran
  (`backtest/tools/diag_double_bottom_base_quiet_20260721.py` Steps 5-6) --
  26 fires with VIX pinned to 15.0 / 22 fires with real VIX, both with `levels_active=[]`
  (proximity gate neutralized, isolating Gate 4/5). This population is PRE-SEEN -- it may
  motivate cell selection (it already did, for cell A's lookback value) but it CANNOT be
  used to compute or report OOS_positive / WF / any pass/fail bar metric for any cell. It is
  disclosed here so the OOS population below is judged as genuinely held-out.

- **OOS:** a forward shadow ledger of detector fires per cell (CONTROL/A/B/C/D), recorded on
  live or replay bars going forward with **zero behaviour change** to any armed path, for
  **>= 30 sessions**. Each fire is scored by the same forward-outcome proxy the sole-blocker
  miner uses: `price_sole_blocker_cohort()` in
  `backtest/tools/frequency_ceiling_cascade_2026_08_03.py:696`, which walks each candidate
  through the SAME real-OPRA + real `lib.exit_manager_walk.walk_exit_manager` pipeline
  `day_report_card.py`'s oracle walks use (structure-stop enabled, entry+1 / real-OPRA /
  BS-synthetic-disclosure logic) -- not a re-implemented pricer.

---

## The bar

Standard 4 conditions (CLAUDE.md OP-16 auto-ratify gate, verbatim): **OOS_positive AND
WF >= 0.70 AND sub_window_stable AND anchor_no_regression.** This is the same shape as the
queue item's own paraphrase ("must clear the existing OP-21 bar (OOS>0, posQ>=4/6, N>=20,
WF stable)", queue.md line 750) -- both cited here rather than invented fresh.

Plus, per lesson class C4 (concentration disclosure -- `markdown/doctrine/LESSONS-LEARNED.md`):
report the max single-day / single-trade share of each cell's OOS sample; a cell cannot pass
on the strength of one anchor day.

Plus the **sign-only walker caveat**: if real-OPRA pricing is unavailable for any forward
shadow fire (as with `backtest/tools/bear_f8_sign_costing.py`'s precedent), that fire's
win/loss SIGN may still be logged, but its $ magnitude is WITHHELD from `OOS_positive`'s
threshold check -- sign-only fires are disclosed separately and never counted toward the $
bar, matching the house convention already in use today
(`analysis/recommendations/prereg-whole-engine-null-v2-stop-mode-faithful-2026-09-03.md`
line 121, "stay disclosed as sign-only, matching v1's existing WITHHELD convention").

---

## Prediction / refutation lines

- **CONTROL:** predicted near-zero real-world fills over 30 OOS sessions (matches current
  production "0 fills since arm" per `STATUS.md` LICENSE-MONITOR) -- refuted if CONTROL
  fires and passes the bar, which would mean the lookback/RTH story was never the real
  blocker.
- **Cell A:** predicted to catch J's specific gap-shape (120-min separated lows) that
  CONTROL misses, WITHOUT materially changing total fire count (lookback+6 bars is a narrow
  widen) -- refuted if fire count jumps disproportionately (would indicate unrelated pivot
  pairs are being pulled in, per the Step 4 "algorithm picks the LAST two local lows"
  mechanism) or if OOS_positive fails.
- **Cell B:** predicted to catch J's EXACT case (true premarket low) with the fewest
  side-effect fires of any cell, since it only widens the frame's TIME coverage, not the
  scan-window SIZE -- refuted if it fires no more often than CONTROL (would mean premarket
  bars rarely feed the local-lows pair even when visible) or fails the bar.
- **Cell C:** predicted to be a strict superset of A's ∪ B's fires -- refuted if C fires
  less than max(A, B) (would indicate an interaction bug between the two changes).
- **Cell D:** predicted to show materially HIGHER real-fills expectancy than CONTROL/A/B/C
  at equal or lower N (proximity-to-named-level as a positive filter rather than the
  current exclusion filter) -- refuted if D's expectancy is statistically indistinguishable
  from an unfiltered detector-fire population (would mean the "0 fills since arm" gap is
  NOT proximity-driven, contrary to the lead's hypothesis).

---

## build_step (shadow recorder)

- **name:** `backtest/tools/db_lookback_shadow_recorder.py`
- **must_contain** (verified against this spec before it is considered built):
  - [ ] Imports `detect_db_base_quiet_setup` and `double_bottom_detector` from their real
        modules -- no re-implementation.
  - [ ] Runs all 5 cells (CONTROL, A, B, C, D) per tick, read-only, against either live
        bars or a replay cache -- writes zero trading-path state.
  - [ ] Does NOT modify `heartbeat_core.py`, `orchestrator.py`, `params.json`, or any armed
        watcher registration.
  - [ ] Appends one JSONL row per cell per fire to
        `analysis/prospector/db-lookback-shadow-ledger.jsonl` (new file; does not collide
        with any existing ledger) with at minimum: `date`, `time_et`, `cell`, `fired`,
        `confidence`, `levels_active`, `sign_only` (bool).
  - [ ] Never calls `place_option_order` / any Alpaca MCP order tool, and has no `--live`
        or `--apply` flag that could wire a cell into an armed path.
  - [ ] Scoring pass (separate script or a `--score` mode) calls
        `price_sole_blocker_cohort` (or an equivalent read of
        `lib.exit_manager_walk.walk_exit_manager`) rather than re-deriving P&L, per the
        forward-outcome-proxy requirement above.

---

## Expansion clause

**EXPANSION -> not before 2026-10-30.** No cell, lookback value, proximity band, or bar
threshold in this document may be hand-widened after seeing OOS results -- that is the
exact failure mode the queue item's title (`pre-reg then A/B -- do NOT hand-widen`)
forbids. Any change before 2026-10-30 requires a superseding, dated prereg document (this
file's own convention), not an in-place edit.
