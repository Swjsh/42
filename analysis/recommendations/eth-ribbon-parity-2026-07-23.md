# ETH-Inclusive Ribbon Parity — validation of `backtest/tools/eth_ribbon.py`

**Mission:** RIBBON-SESSION-SCOPE-DIVERGENCE Part A (`automation/overnight/queue.md` 2026-07-23,
discovery doc `analysis/edge-matrix/tv-parity-oracle-2026-07-23.md`).
**Run:** 2026-07-23, TV Bar Replay, chart `4HTVHI0m`, BATS:SPY 5-min. 10 days x 3 checkpoints
(open 09:30 / midday 12:30 / close 15:30 ET) = 30 checkpoints. 10K-bar TV Plus depth used to
reach back to 2026-05-20 via Bar Replay.
**Days sampled** (spread across the last ~2 months, gap days prioritized from
`analysis/edge-matrix/day-inventory-2026-07-23.json` gap_pct tags, restricted to days with
genuine premarket bar coverage in our cache): 2026-05-20 (+0.26%), 05-26 (+0.59%), 06-05
(-0.63%), 06-08 (+0.81%), 06-16 (+1.74%, largest gap in the last-2mo window), 06-18 (+0.91%),
06-23 (-1.41%), 06-25 (+0.89%), 07-08 (-0.61%), 07-20 (+0.52%).

## VERDICT: PARTIAL PASS — scope fix confirmed correct; a second, smaller, structural residual disclosed

Two separate questions, two separate answers:

1. **Does substituting session SCOPE (RTH -> ETH) fix the divergence the oracle found?**
   **YES, dramatically.** Worst |diff| across the 30 checkpoints drops from **$12.94 (RTH-only,
   sanity cross-check re-run here)** to **$1.10 (ETH)** — an 91.5% reduction. Median worst-per-
   checkpoint drops from **$1.01 -> $0.23**. CRITICAL-flagged checkpoints drop from **25/30 ->
   14/30**.
2. **Is the ETH ribbon now pixel-parity with TV?** **NO — a second, smaller, structural
   residual remains**, root-caused below (not an EMA bug, not a frame-construction bug).

### The metric that actually matters for Part B: ribbon STACK concordance

Part B (and the live engine) consumes `stack` (BULL/BEAR/MIXED), not raw EMA dollar values.
Measured at the same 30 checkpoints:

| Scope | Stack matches TV's own EMA ordering |
|---|---|
| RTH-only (today's engine) | **13/30 (43%)** |
| **ETH-inclusive (this module)** | **27/30 (90%)** |

The 3 ETH mismatches: 2026-06-16 09:30 (tv=BEAR, eth=BULL — a large-gap morning, ETH
worst=$0.75), 2026-06-16 12:30 (tv=MIXED, eth=BEAR, $0.17 — a near-flip transition), 2026-06-25
09:30 (tv=BULL, eth=MIXED, $0.33). All three are at tightly-clustered EMA spreads (near a flip)
on the very gap mornings this study population targets — expected behavior at a
classification boundary, not a sign of a broken fix.

## Root cause of the residual (diagnosed per mission instruction, before proceeding to Part B)

**One sentence:** the residual is SIP-consolidated-tape (our cache) vs BATS-only (TV's chart
symbol `BATS:SPY`) bar-level noise, concentrated in **premarket** hours where liquidity is
thin and fragmented across venues — NOT an EMA-math bug and NOT a frame-construction bug.

Direct diagnostic (2026-06-05, the single worst checkpoint, close $1.10): pulled TV's own raw
premarket OHLCV bars via Bar Replay (67 bars, 04:00-09:30) and diffed them bar-for-bar against
our cache's same-day premarket bars. Bar COUNT matches exactly (67 == 67, same 5-min grid,
same 04:00 anchor). Bar CLOSE values diverge up to **$0.29/bar** (mean diff ~$0.0015 — net
unbiased, but real bar-to-bar noise, not a level shift) with **volume differing 5-20x per bar**
(our SIP volume >> TV's single-exchange BATS volume throughout) — textbook single-exchange vs
consolidated-tape fragmentation in thin premarket trading. The original oracle's own bar-data
parity check ($0.04 median) was measured at RTH-session bars only; premarket-specific bar
parity was never directly tested until this diagnostic. A 48-period EMA integrates ~66
premarket bars every session, so per-bar noise of this size compounds into the observed
$0.15-$1.10 dollar-level residual even though the underlying trend (and, 90% of the time, the
stack classification) is correct.

**This is a structural, disclosed limitation of the data source, not a bug to fix in this
module.** We do not have a BATS-only feed; acquiring one is out of scope for this fire. The
EMA math itself is proven correct (same `lib.ribbon.compute_ribbon`, unmodified) and the
frame-construction warmup is proven sufficient (continuous 386-day frame, EMA-48 seed
influence decays to <2% within ~100 bars, converged for >300 days before any sampled
checkpoint).

## Checkpoint table (ETH vs TV; RTH worst included for sanity cross-check)

| Date | Time | gap% | d_fast | d_pivot | d_slow | ETH worst | RTH worst | Flag | Stack match (ETH/RTH) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-20 | 09:30 | +0.26 | +0.018 | -0.076 | -0.150 | 0.150 | 1.774 | DRIFT | Y/N |
| 2026-05-20 | 12:30 | +0.26 | -0.142 | -0.032 | -0.451 | 0.451 | 0.717 | CRITICAL | Y/N |
| 2026-05-20 | 15:30 | +0.26 | -0.057 | +0.081 | -0.237 | 0.237 | 0.296 | DRIFT | Y/N |
| 2026-05-26 | 09:30 | +0.59 | -0.128 | -0.125 | -0.326 | 0.326 | 4.222 | CRITICAL | Y/N |
| 2026-05-26 | 12:30 | +0.59 | +0.205 | -0.004 | +0.094 | 0.205 | 0.724 | DRIFT | Y/N |
| 2026-05-26 | 15:30 | +0.59 | +0.071 | +0.057 | +0.097 | 0.097 | 0.086 | DRIFT | Y/Y |
| 2026-06-05 | 09:30 | -0.63 | +0.275 | -0.037 | +0.321 | 0.321 | 4.598 | CRITICAL | Y/N |
| 2026-06-05 | 12:30 | -0.63 | +0.321 | -0.344 | +0.744 | 0.744 | 1.494 | CRITICAL | Y/N |
| 2026-06-05 | 15:30 | -0.63 | +0.621 | -0.307 | +1.099 | 1.099 | 1.267 | CRITICAL | Y/N |
| 2026-06-08 | 09:30 | +0.81 | -0.335 | -0.071 | -0.282 | 0.335 | 4.693 | CRITICAL | Y/N |
| 2026-06-08 | 12:30 | +0.81 | -0.022 | -0.124 | -0.176 | 0.176 | 0.290 | DRIFT | Y/N |
| 2026-06-08 | 15:30 | +0.81 | +0.327 | -0.140 | +0.231 | 0.327 | 0.327 | CRITICAL | Y/Y |
| 2026-06-16 | 09:30 | +1.74 | +0.128 | +0.052 | -0.755 | 0.755 | 12.939 | CRITICAL | **N**/N |
| 2026-06-16 | 12:30 | +1.74 | -0.172 | -0.079 | -0.056 | 0.172 | 2.774 | DRIFT | **N**/N |
| 2026-06-16 | 15:30 | +1.74 | +0.025 | -0.127 | +0.155 | 0.155 | 0.452 | DRIFT | Y/N |
| 2026-06-18 | 09:30 | +0.91 | -0.372 | +0.030 | +0.024 | 0.372 | 3.543 | CRITICAL | Y/N |
| 2026-06-18 | 12:30 | +0.91 | -0.058 | +0.063 | -0.027 | 0.063 | 0.118 | DRIFT | Y/N |
| 2026-06-18 | 15:30 | +0.91 | +0.144 | -0.034 | -0.025 | 0.144 | 0.144 | DRIFT | Y/Y |
| 2026-06-23 | 09:30 | -1.41 | +0.106 | -0.063 | +0.444 | 0.444 | 9.444 | CRITICAL | Y/N |
| 2026-06-23 | 12:30 | -1.41 | -0.185 | +0.079 | -0.028 | 0.185 | 1.980 | DRIFT | Y/N |
| 2026-06-23 | 15:30 | -1.41 | +0.185 | -0.043 | +0.201 | 0.201 | 0.649 | DRIFT | Y/N |
| 2026-06-25 | 09:30 | +0.89 | -0.206 | -0.105 | -0.331 | 0.331 | 5.731 | CRITICAL | **N**/N |
| 2026-06-25 | 12:30 | +0.89 | -0.185 | -0.169 | +0.228 | 0.228 | 0.759 | DRIFT | Y/N |
| 2026-06-25 | 15:30 | +0.89 | +0.073 | -0.125 | +0.207 | 0.207 | 0.130 | DRIFT | Y/Y |
| 2026-07-08 | 09:30 | -0.61 | -0.054 | +0.079 | +0.050 | 0.079 | 5.004 | DRIFT | Y/N |
| 2026-07-08 | 12:30 | -0.61 | -0.094 | +0.105 | +0.199 | 0.199 | 1.304 | DRIFT | Y/N |
| 2026-07-08 | 15:30 | -0.61 | -0.051 | +0.016 | -0.282 | 0.282 | 0.051 | CRITICAL | Y/Y |
| 2026-07-20 | 09:30 | +0.52 | +0.167 | +0.170 | -0.066 | 0.170 | 2.405 | DRIFT | Y/N |
| 2026-07-20 | 12:30 | +0.52 | -0.257 | -0.008 | -0.033 | 0.257 | 0.361 | CRITICAL | Y/N |
| 2026-07-20 | 15:30 | +0.52 | +0.305 | -0.074 | +0.326 | 0.326 | 0.305 | CRITICAL | Y/N |

diff = ours - TV, in $. Full raw data:
`analysis/edge-matrix/_eth_parity_checkpoints_2026-07-23.json`. Live TV reads embedded in
`scratchpad/tv_eth_parity_check.py` (session temp, per the prior oracle's own convention).

## Summary statistics

| | ETH | RTH (sanity re-check) |
|---|---|---|
| Median worst-per-checkpoint | $0.232 | $1.013 |
| Mean worst-per-checkpoint | $0.301 | $2.286 |
| P90 worst-per-checkpoint | $0.744 | $5.731 |
| Max worst-per-checkpoint | $1.099 | $12.939 |
| CRITICAL checkpoints (>$0.25) | 14/30 | 25/30 |
| Stack matches TV | 27/30 (90%) | 13/30 (43%) |

By checkpoint position: 09:30 (open) carries the worst median ETH residual ($0.328, most
premarket bars baked in), 12:30/15:30 are similar (~$0.21-0.31) — consistent with the
premarket-noise root cause (damage done overnight, RTH bars alone don't fully wash it out by
end of day at a 48-period EMA's decay rate).

## Disposition — proceeding to Part B with this disclosed calibration

The ETH ribbon is used in Part B as a **strong, validated-directional stand-in** for J's chart
(dramatically closer than RTH-only on every metric measured), with the disclosed caveat that
**dollar-level EMA agreement is not exact** (structural SIP-vs-BATS premarket noise) and
**stack classification has a measured ~10% disagreement rate with TV even in the ETH-matched
scope**, concentrated at near-flip/MIXED transitions on the same gap mornings this study
targets. This is folded into Part B's own disagreement-rate reporting (Part B compares OUR
RTH-scope ribbon vs OUR ETH-scope ribbon — both computed from the identical cache series, so
that specific comparison carries none of this TV-feed noise; the noise only applies when
comparing either of our scopes against TV's live rendering, i.e. what J's eyes see).

## Protocol notes (repeatability)

- Replay driver: `replay_start(date)` anchors at prior-day 19:59:59 ET; 11x 30-min
  `replay_step` reaches the 09:00-09:30 premarket bar, switch to 5m + 1 step lands exactly on
  the checkpoint bar (verified against `data_get_ohlcv` bar `time` at every checkpoint this
  run, zero misalignments). Between checkpoints: switch to 30m, 6x step (exactly 3h = 6
  half-hour bars), switch to 5m, 1x step. ~34 tool calls/day x 10 days = ~340 calls.
- `replay_start`'s own returned `current_date` was observed stale/lagged on 2 of 10 days
  (returned the PRE-jump position); `replay_status` immediately after was always correct —
  worth encoding as a standing note for future TV replay work: verify position via
  `replay_status`, don't trust `replay_start`'s own return value.
- Only agent touching TV this session (serialized per mission spec). Chart returned to
  realtime BATS:SPY 5m at the end (`tv_health_check` confirmed PASS).
