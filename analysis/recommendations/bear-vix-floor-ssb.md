# Bear VIX Floor under SS-B — VOID (no live gate to test)

**Task (A3, OPRA-sequential lane job 2/3, 2026-07-14 ~16:41-17:00 ET):** pre-register 3 variants
of the "bear-entry VIX floor ~17.30" (control vs 16.0 vs no-floor) and run under SS-B exits at
live scope on real OPRA fills, because the floor supposedly blocked bear entries today at VIX
16.80.

**Verdict: VOID.** No pre-registration was frozen. No OPRA grind ran. The gate named in the task
briefing does not exist on the live order-placing path — testing 3 variants of it would change
zero live behavior no matter what the numbers said. Full evidence in
[`bear-vix-floor-ssb.json`](bear-vix-floor-ssb.json).

## Why — verified fresh this session, not taken on faith

1. **`backtest/lib/engine/gates.py`** (the canonical 15-gate list `heartbeat_core.py` actually
   calls via `engine_cli` for every live tick) has exactly 2 VIX gates: `block_elite_bull`
   (bull-only VIX band, ELITE tier only) and `vix_bear_hard_cap` (bear VIX **ceiling** ≥23, the
   opposite of a floor). No bear-floor gate exists. Confirmed by direct grep this session
   (`gates.py` lines 25, 37, 142, 415-419).
2. **`vix_entry_thresholds.bear_min_exclusive_and_rising` = 17.30`** (the key holding the value
   the task named) has exactly 3 consumers repo-wide: a schema field with no logic, a dormant
   shadow "observer" lane (`fast_path_executor.py`, never places orders, last wrote a row
   2026-05-20 — 55+ days stale), and the crypto gym (non-edge, out of scope per CLAUDE.md).
3. **Today's actual decision log** (`core-decisions.jsonl`, 1,156 ticks, both core accounts) has
   **zero** VIX-bear-floor SKIP actions. The 2 named "missed full-quality signals" died to the
   free-model veto layer + `SKIP_MIN_PREMIUM_FLOOR`/PDT — already graded net **+$565.50 positive**
   today by the sibling `A6-VETO-GRADE-2026-07-14` item.
4. A **sibling same-day analysis** (`queue.md` item `VIX-DEADZONE-MAP`, `status:done`,
   completed ~16:20 ET, *before* this task started) independently reached the identical
   conclusion — I re-derived it from source rather than chaining an unverified claim into a KILL
   decision.

## Provenance of the 17.30 number itself (for the record, since it was asked for)

- `backtest/lib/filters.py`'s `VIX_BEAR_THRESHOLD = 17.30` (the research-only 10-filter
  BEARISH_REJECTION checklist, feeds backtest simulation only, not the live path) was introduced
  in commit `d0c8ac0` ("evening snapshot 2026-06-15") — a bulk snapshot, not a ratification commit.
- **No SAFE-specific sweep or scorecard exists anywhere in `analysis/recommendations/`.** Every
  `*vix_bear_threshold*` sweep file in the repo is AGG-scoped
  (`aggressive_vix_bear_threshold_sweep.py`, `agg_vix_bear_threshold_sweep*.json`).
- `markdown/planning/FUTURE-IMPROVEMENTS.md`'s own closure note: *"15.0 confirmed optimal for
  AGG ... **Safe default 17.30 in production**"* — "default," not "validated." Even the AGG
  sweep's own results don't clearly favor 17.30 (16.0 shows higher IS_pnl than the 15.0 baseline
  in the raw results file).
- **Conclusion:** 17.30 for Safe is exactly the kind of evidence-optional constant OP-11/T2 flags
  — but it's moot, because it never gates a live order either way (see above).

## What I did instead of burning the OPRA lane

- **No OPRA grind consumed.** Sequential lane released immediately — clear for job 3.
- **No live params/config semantics touched.**
- Applied the already-flagged `queue.md` item `VIX-VESTIGIAL-KNOB-CLEANUP` (doc-only,
  non-executable): added a `_vix_entry_thresholds_doc` marker comment to both `params.json` and
  `aggressive/params.json` stating the key is vestigial/dormant-lane-only, so a 3rd session
  doesn't repeat this exact misread (this task *was* that 3rd misread, caught before any compute
  was spent).

## Recommendation going forward

Retire "bear VIX floor 17.30" from future task briefings as a live lever — it isn't one. If a
real bear-side VIX regime filter is wanted, that's new design work (mirroring `block_elite_bull`
for bears), not a threshold tweak on a dead key. The two VIX levers that *are* live:
`block_elite_bull` (bull-only, already SS-B-KEEP-validated 2026-07-10) and `vix_bear_hard_cap`
(Safe=23.0 ceiling, ratified 2026-06-18; Bold has no cap at all — separately flagged as
`BOLD-VIX-BEAR-CEILING-GAP`, out of this task's scope).
