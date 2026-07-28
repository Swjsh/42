# ZONE-WIDTH -- pre-registered 3-cell band study (levels-are-zones), 2025-01-02..2026-07-27

Generated 2026-07-27T22:19:13.532564. Runner: `backtest/tools/zone_width_fullhist_replay.py`. Runtime 221.3s.

## Verdict first

| Cell | Marginal n | Marginal P&L | Marginal WR | Day-majority | Drop-best | Held-out (>=2026-03-06) | Displaced n / P&L | NET vs control | Ship-eligible |
|---|--:|--:|--:|---|---|---|---|--:|:--:|
| **0c (control)** | 0 (definitional) | -- | -- | -- | -- | -- | 0 / -- | $0.00 | -- |
| **10c** | 13 | +$214.00 | 0.3846 | 5/13 (False) | -$228.50 (False) | 4tr -$83.40 | 37 / +$632.00 | -$418.00 | NO (thin) |
| **25c** | 19 | -$1,247.20 | 0.1053 | 2/17 (False) | -$1,675.20 (False) | 2tr -$223.80 | 61 / -$106.20 | -$1,141.00 | NO |

Control full book (must equal LADDER-FULLHIST baseline): n=191, +$5,306.95, WR=0.2984. **Verification anchor pass: True.**

## Pre-registration (frozen before the run)

Stated in-session before any cell ran; frozen verbatim in this runner's module docstring (`backtest/tools/zone_width_fullhist_replay.py`). Cells: band b in {0.00 control, 0.10, 0.25} applied to `detect_level_rejection` as: (1) strict-preserving (production fire always returned unchanged), (2) wick-deference (production's `detect_wick_rejection_bearish` fall-through keeps ownership of its bars), (3) banded fall-through `high > level - b AND close < level + b`, max-level tiebreak. Pass bar on the MARGINAL cohort: positive aggregate AND day-majority AND survives-drop-best AND held-out positive AND net-effect >= 0. n<15 = evidence-thin advisory.

## Per-cell detail

### Cell 10c (band $0.10)

- Band-branch fires (trigger-level, pre-cascade): 6822 -- modes {'approach_touch': 4312, 'pierced_close_in_zone': 2510}
- Raw entries 183 = shared 154 + marginal 13 (+2 marginal no-OPRA excluded); displaced 37 (same-bar shifted pairs: 2)
- Full book under this band: n=167 +$4,888.95 WR=0.2994 maxDD=-$2,011.65 vs control +$5,306.95
- Gates: {'a_positive_aggregate': True, 'b_day_majority': False, 'c_survives_drop_best': False, 'd_held_out_positive': False, 'e_net_effect_nonnegative': False, 'ship_eligible': False, 'evidence_thin': True}

| Date | Entry | Tier | Triggers | Level | Fire mode | P&L | Exit |
|---|---|---|---|---|---|--:|---|
| 2025-01-08 | 12:55 | TRENDLINE | trendline_rejection | None | approach_touch | +$442.50 | runner_stop @ 3.15 |
| 2025-01-29 | 13:00 | TRENDLINE | trendline_rejection | None | approach_touch | -$109.20 | premium_stop @ 1.46 |
| 2025-02-07 | 14:50 | TRENDLINE | trendline_rejection | None | None | +$55.00 | time_stop_15:50 |
| 2025-02-24 | 14:50 | TRENDLINE | trendline_rejection | None | None | +$91.00 | ribbon_flip_back |
| 2025-08-07 | 12:45 | TRENDLINE | trendline_rejection | None | None | -$79.20 | premium_stop @ 1.06 |
| 2025-09-10 | 13:15 | TRENDLINE | trendline_rejection | None | approach_touch | +$178.10 | runner_stop @ 1.24 |
| 2025-10-07 | 12:10 | TRENDLINE | trendline_rejection | None | None | -$63.00 | premium_stop @ 0.84 |
| 2025-11-04 | 12:35 | TRENDLINE | trendline_rejection | None | None | -$72.00 | premium_stop @ 0.96 |
| 2026-02-17 | 10:30 | TRENDLINE | trendline_rejection | None | None | -$145.80 | premium_stop @ 1.94 |
| 2026-05-07 | 13:45 | TRENDLINE | trendline_rejection | None | None | -$67.80 | premium_stop @ 0.9 |
| 2026-05-22 | 13:15 | TRENDLINE | trendline_rejection | None | approach_touch | +$45.00 | ribbon_flip_back |
| 2026-06-16 | 13:35 | TRENDLINE | trendline_rejection | None | approach_touch | -$42.60 | premium_stop @ 0.57 |
| 2026-07-21 | 14:55 | TRENDLINE | trendline_rejection | None | approach_touch | -$18.00 | ribbon_flip_back |

Displaced (control trades this band's cascade removed):

| Date | Entry | Tier | Triggers | Control P&L (foregone) |
|---|---|---|---|--:|
| 2025-01-06 | 14:45 | TRENDLINE | trendline_rejection | +$180.25 |
| 2025-01-08 | 12:50 | TRENDLINE | trendline_rejection | +$545.65 |
| 2025-01-29 | 12:40 | TRENDLINE | trendline_rejection | -$114.60 |
| 2025-02-06 | 12:40 | TRENDLINE | trendline_rejection | -$21.00 |
| 2025-02-06 | 13:45 | TRENDLINE | trendline_rejection | -$100.00 |
| 2025-02-07 | 14:25 | TRENDLINE | trendline_rejection | -$95.00 |
| 2025-02-24 | 13:50 | TRENDLINE | trendline_rejection | +$77.00 |
| 2025-05-20 | 12:15 | TRENDLINE | trendline_rejection | -$76.20 |
| 2025-07-07 | 11:00 | TRENDLINE | trendline_rejection | +$276.30 |
| 2025-07-07 | 14:20 | TRENDLINE | trendline_rejection | -$99.00 |
| 2025-08-07 | 11:50 | TRENDLINE | trendline_rejection | -$62.40 |
| 2025-08-07 | 13:05 | TRENDLINE | trendline_rejection | -$90.40 |
| 2025-09-10 | 13:10 | TRENDLINE | trendline_rejection | +$136.55 |
| 2025-10-07 | 11:40 | TRENDLINE | trendline_rejection | -$79.80 |
| 2025-10-24 | 14:45 | TRENDLINE | trendline_rejection | -$9.00 |
| 2025-11-04 | 11:10 | TRENDLINE | trendline_rejection | -$100.80 |
| 2025-11-04 | 12:45 | TRENDLINE | trendline_rejection | +$418.20 |
| 2025-11-04 | 14:00 | TRENDLINE | trendline_rejection | -$96.80 |
| 2025-12-08 | 12:05 | TRENDLINE | trendline_rejection | -$67.80 |
| 2025-12-09 | 10:30 | TRENDLINE | trendline_rejection | -$84.00 |
| 2025-12-10 | 10:30 | TRENDLINE | trendline_rejection | -$150.60 |
| 2026-02-04 | 10:30 | TRENDLINE | trendline_rejection | +$6.00 |
| 2026-02-17 | 10:30 | TRENDLINE | trendline_rejection | -$123.60 |
| 2026-02-17 | 13:10 | TRENDLINE | trendline_rejection | +$42.00 |
| 2026-03-02 | 10:55 | TRENDLINE | trendline_rejection | -$144.00 |
| 2026-03-17 | 11:50 | TRENDLINE | trendline_rejection | -$81.60 |
| 2026-04-29 | 12:15 | TRENDLINE | trendline_rejection | -$125.40 |
| 2026-05-01 | 13:40 | TRENDLINE | trendline_rejection | -$24.00 |
| 2026-05-07 | 12:50 | TRENDLINE | ribbon_flip,trendline_rejection | +$382.40 |
| 2026-05-07 | 13:45 | TRENDLINE | trendline_rejection | -$90.40 |
| 2026-05-18 | 10:00 | TRENDLINE | trendline_rejection | +$504.25 |
| 2026-05-22 | 13:00 | TRENDLINE | trendline_rejection | -$56.40 |
| 2026-06-16 | 11:40 | TRENDLINE | trendline_rejection | +$93.00 |
| 2026-07-02 | 13:05 | TRENDLINE | trendline_rejection | -$88.80 |
| 2026-07-14 | 14:45 | TRENDLINE | trendline_rejection | -$54.00 |
| 2026-07-15 | 14:30 | TRENDLINE | trendline_rejection | +$18.00 |
| 2026-07-21 | 14:50 | TRENDLINE | trendline_rejection | -$12.00 |

### Cell 25c (band $0.25)

- Band-branch fires (trigger-level, pre-cascade): 13378 -- modes {'pierced_close_in_zone': 4656, 'approach_touch': 8722}
- Raw entries 163 = shared 130 + marginal 19 (+3 marginal no-OPRA excluded); displaced 61 (same-bar shifted pairs: 2)
- Full book under this band: n=149 +$4,165.95 WR=0.2953 maxDD=-$1,969.05 vs control +$5,306.95
- Gates: {'a_positive_aggregate': False, 'b_day_majority': False, 'c_survives_drop_best': False, 'd_held_out_positive': False, 'e_net_effect_nonnegative': False, 'ship_eligible': False, 'evidence_thin': False}

| Date | Entry | Tier | Triggers | Level | Fire mode | P&L | Exit |
|---|---|---|---|---|---|--:|---|
| 2025-01-29 | 13:00 | TRENDLINE | trendline_rejection | None | approach_touch | -$109.20 | premium_stop @ 1.46 |
| 2025-02-07 | 14:55 | TRENDLINE | ribbon_flip,trendline_rejection | None | approach_touch | -$20.00 | time_stop_15:50 |
| 2025-02-24 | 14:50 | TRENDLINE | trendline_rejection | None | None | +$91.00 | ribbon_flip_back |
| 2025-03-20 | 14:15 | TRENDLINE | trendline_rejection | None | None | -$96.00 | premium_stop @ 0.96 |
| 2025-05-21 | 15:00 | TRENDLINE | trendline_rejection | None | approach_touch | -$61.20 | premium_stop @ 0.82 |
| 2025-07-28 | 13:55 | TRENDLINE | trendline_rejection | None | approach_touch | -$24.00 | premium_stop @ 0.32 |
| 2025-07-28 | 15:00 | TRENDLINE | trendline_rejection | None | None | -$98.00 | premium_stop @ 0.28 |
| 2025-08-07 | 12:45 | TRENDLINE | trendline_rejection | None | None | -$79.20 | premium_stop @ 1.06 |
| 2025-09-17 | 12:15 | TRENDLINE | trendline_rejection | None | None | -$150.00 | premium_stop @ 2.0 |
| 2025-10-07 | 12:10 | TRENDLINE | trendline_rejection | None | None | -$63.00 | premium_stop @ 0.84 |
| 2025-10-09 | 13:20 | TRENDLINE | trendline_rejection | None | pierced_close_in_zone | -$99.00 | premium_stop @ 0.79 |
| 2025-11-04 | 12:35 | TRENDLINE | trendline_rejection | None | None | -$72.00 | premium_stop @ 0.96 |
| 2025-11-06 | 11:05 | ELITE | level_rejection,confluence | 674.22 | approach_touch | -$330.00 | structure_stop @ 674.22 |
| 2025-12-12 | 12:40 | TRENDLINE | trendline_rejection | None | approach_touch | -$123.60 | premium_stop @ 1.65 |
| 2026-02-17 | 10:30 | TRENDLINE | trendline_rejection | None | None | -$145.80 | premium_stop @ 1.94 |
| 2026-02-23 | 13:50 | TRENDLINE | trendline_rejection | None | approach_touch | -$71.40 | premium_stop @ 0.95 |
| 2026-02-23 | 14:55 | TRENDLINE | trendline_rejection | None | None | +$428.00 | time_stop_15:50 |
| 2026-05-07 | 13:45 | TRENDLINE | trendline_rejection | None | None | -$67.80 | premium_stop @ 0.9 |
| 2026-05-19 | 10:30 | ELITE | level_rejection,confluence | 733.3900146484375 | approach_touch | -$156.00 | structure_stop @ 733.3900146484375 |

Displaced (control trades this band's cascade removed):

| Date | Entry | Tier | Triggers | Control P&L (foregone) |
|---|---|---|---|--:|
| 2025-01-06 | 14:45 | TRENDLINE | trendline_rejection | +$180.25 |
| 2025-01-08 | 12:50 | TRENDLINE | trendline_rejection | +$545.65 |
| 2025-01-29 | 12:40 | TRENDLINE | trendline_rejection | -$114.60 |
| 2025-02-06 | 12:40 | TRENDLINE | trendline_rejection | -$21.00 |
| 2025-02-06 | 13:45 | TRENDLINE | trendline_rejection | -$100.00 |
| 2025-02-07 | 14:25 | TRENDLINE | trendline_rejection | -$95.00 |
| 2025-02-14 | 13:25 | TRENDLINE | trendline_rejection | -$40.80 |
| 2025-02-14 | 15:00 | TRENDLINE | trendline_rejection | -$117.00 |
| 2025-02-24 | 13:50 | TRENDLINE | trendline_rejection | +$77.00 |
| 2025-03-20 | 13:50 | TRENDLINE | trendline_rejection | -$100.80 |
| 2025-04-02 | 15:00 | TRENDLINE | trendline_rejection | -$121.80 |
| 2025-05-20 | 12:15 | TRENDLINE | trendline_rejection | -$76.20 |
| 2025-06-17 | 11:20 | TRENDLINE | trendline_rejection | -$55.80 |
| 2025-06-20 | 12:15 | TRENDLINE | trendline_rejection | -$59.40 |
| 2025-07-07 | 11:00 | TRENDLINE | trendline_rejection | +$276.30 |
| 2025-07-07 | 14:20 | TRENDLINE | trendline_rejection | -$99.00 |
| 2025-07-29 | 14:45 | TRENDLINE | trendline_rejection | +$192.00 |
| 2025-08-07 | 11:50 | TRENDLINE | trendline_rejection | -$62.40 |
| 2025-08-07 | 13:05 | TRENDLINE | trendline_rejection | -$90.40 |
| 2025-08-11 | 14:45 | TRENDLINE | trendline_rejection | -$49.80 |
| 2025-08-29 | 13:20 | TRENDLINE | trendline_rejection | -$63.00 |
| 2025-09-03 | 13:30 | TRENDLINE | trendline_rejection | +$168.60 |
| 2025-09-10 | 13:10 | TRENDLINE | trendline_rejection | +$136.55 |
| 2025-09-17 | 11:55 | TRENDLINE | trendline_rejection | -$144.00 |
| 2025-09-17 | 13:20 | TRENDLINE | trendline_rejection | -$154.20 |
| 2025-10-06 | 11:40 | TRENDLINE | trendline_rejection | -$51.00 |
| 2025-10-07 | 11:40 | TRENDLINE | trendline_rejection | -$79.80 |
| 2025-10-09 | 13:15 | TRENDLINE | trendline_rejection | -$100.80 |
| 2025-10-24 | 14:45 | TRENDLINE | trendline_rejection | -$9.00 |
| 2025-11-04 | 11:10 | TRENDLINE | trendline_rejection | -$100.80 |
| 2025-11-04 | 12:45 | TRENDLINE | trendline_rejection | +$418.20 |
| 2025-11-04 | 14:00 | TRENDLINE | trendline_rejection | -$96.80 |
| 2025-11-06 | 14:05 | TRENDLINE | trendline_rejection | -$72.60 |
| 2025-11-12 | 14:25 | TRENDLINE | trendline_rejection | -$36.00 |
| 2025-12-02 | 15:00 | TRENDLINE | trendline_rejection | -$41.40 |
| 2025-12-08 | 12:05 | TRENDLINE | trendline_rejection | -$67.80 |
| 2025-12-09 | 10:30 | TRENDLINE | trendline_rejection | -$84.00 |
| 2025-12-10 | 10:30 | TRENDLINE | trendline_rejection | -$150.60 |
| 2025-12-12 | 12:25 | TRENDLINE | trendline_rejection | -$108.00 |
| 2026-02-04 | 10:30 | TRENDLINE | trendline_rejection | +$6.00 |
| 2026-02-17 | 10:30 | TRENDLINE | trendline_rejection | -$123.60 |
| 2026-02-17 | 13:10 | TRENDLINE | trendline_rejection | +$42.00 |
| 2026-02-19 | 12:05 | TRENDLINE | trendline_rejection | -$105.60 |
| 2026-02-23 | 13:35 | TRENDLINE | trendline_rejection | -$69.60 |
| 2026-02-23 | 14:45 | TRENDLINE | trendline_rejection | +$616.00 |
| 2026-02-27 | 14:20 | TRENDLINE | trendline_rejection | -$89.40 |
| 2026-03-02 | 10:55 | TRENDLINE | trendline_rejection | -$144.00 |
| 2026-03-17 | 11:50 | TRENDLINE | trendline_rejection | -$81.60 |
| 2026-04-10 | 14:05 | TRENDLINE | trendline_rejection | -$44.40 |
| 2026-04-29 | 12:15 | TRENDLINE | trendline_rejection | -$125.40 |
| 2026-05-01 | 13:40 | TRENDLINE | trendline_rejection | -$24.00 |
| 2026-05-07 | 12:50 | TRENDLINE | ribbon_flip,trendline_rejection | +$382.40 |
| 2026-05-07 | 13:45 | TRENDLINE | trendline_rejection | -$90.40 |
| 2026-05-15 | 11:45 | TRENDLINE | trendline_rejection | -$89.40 |
| 2026-05-18 | 10:00 | TRENDLINE | trendline_rejection | +$504.25 |
| 2026-05-22 | 13:00 | TRENDLINE | trendline_rejection | -$56.40 |
| 2026-06-16 | 11:40 | TRENDLINE | trendline_rejection | +$93.00 |
| 2026-07-02 | 13:05 | TRENDLINE | trendline_rejection | -$88.80 |
| 2026-07-14 | 14:45 | TRENDLINE | trendline_rejection | -$54.00 |
| 2026-07-15 | 14:30 | TRENDLINE | trendline_rejection | +$18.00 |
| 2026-07-21 | 14:50 | TRENDLINE | trendline_rejection | -$12.00 |

## Disclosures

- MEASURED replay, not realized fills: the banded trigger does not exist in production; entries flow through run_backtest's audited entry+1 layer and the real `walk_exit_manager` exit core, real OPRA fills only.
- The band patch reaches BOTH bear call sites (levels_active + FHH); the bull `detect_level_reclaim` is untouched (lane = rejection only). Wick-deference also suppresses banded-FHH fires where a wick pattern exists vs FHH (production never wick-tests FHH) -- slightly conservative, disclosed.
- Touch-side banded fires have no effective close constraint (green approach bars can fire) -- known property of the pre-registered predicate, deliberately not patched mid-run.
- Safe-account config only (SAFE_BASE_LIVE), matching the ladder baseline's scope; Bold not run.
- `block_level_rejection=True` is live in SAFE_BASE_LIVE: single-trigger LEVEL-tier entries are suppressed by the production cascade, so marginal trades are band-fires that compose into multi-trigger setups (or FHH/confluence paths). A small marginal n is the cascade working, not a bug.
- Same-bar shifted pairs (displaced control trade + marginal cell trade on one bar, e.g. via the L96 trendline_only interaction) stay in the marginal cohort and are counted separately.
- The motivating 2026-07-17 10:15 live miss was 61c shy -- OUTSIDE both pre-registered bands (10c/25c). These cells cannot capture that specific incident; widening beyond 25c was deliberately NOT added post-hoc.

---
_Raw JSON with per-trade detail + fire-log sample: `analysis/deep-research/ZONE-WIDTH-2026-07-28.json`._
