# H1 ENTRY LOCATION -- does chasing the range extreme lose money?

**Stamp:** 2026-09-03T10:24 ET · **Slug:** entry-location · **Verdict: INCONCLUSIVE**
Data + tools: `analysis/deep-research/2026-09-03-money/entry-location.json` (stats),
`entry-location-rows.json` (per-trade rows), `backtest/tools/money_entry_location.py` +
`money_entry_location_stats.py` (builders, cached-data-only, re-runnable, $0, no network).

## TL;DR

- **The literal global rule (calls >=0.75 / puts <=0.25 range_position lose) is not supported.**
  Point estimate is in the hypothesized direction at 0.75/0.25 (chase mean **$2.12**/trade vs
  rest **$18.90**/trade) but the 95% CI on that gap is **[-$72.84, +$38.91]** -- crosses zero.
  At 0.90/0.10 the **sign flips**: the most extreme entries do *better* (chase **$20.07** vs
  rest **$3.44**). A real, monotonic "chasing the extreme is bad" effect should get *worse*, not
  reverse, as the threshold tightens. It doesn't.
- **The rule would gut the trade count.** At 0.75/0.25 it skips **103 of 186 trades (55%)**.
  Net dollar effect of refusing all of them: **-$218, CI [-$3,757, +$3,220]** -- statistically
  indistinguishable from zero, because it forgoes **33 winners worth $7,129** almost exactly as
  it avoids **70 losers worth $6,911**.
- **It kills one of the four named winning days outright.** Applied literally on **2026-08-13**,
  the rule blocks $1,895 of that day's $1,748 total, turning a **+$1,748 day into a -$147 day**.
  On 2026-08-27 it keeps the day positive but cuts it 59% (+$1,897 -> +$775). It is closer to
  neutral on 08-06 and net *helps* on 08-28. See "Kills winners" below -- **this alone is
  sufficient to refuse the naive/global form of this rule.**
- **A real, setup-conditional signal exists but is underpowered.** Within
  `BULLISH_RECLAIM_RIDE_THE_RIBBON` alone (58% of the population, n=108), chase entries
  (n=67) net **-$0.87/trade, PF 0.988** vs rest (n=41) **+$42.27/trade, PF 1.665** -- a
  **$43/trade gap**, directionally exactly the hypothesis. But the CI on that gap is still
  **[-$128.89, +$37.97]**, and the very trades that drove 08-13 and 08-27's blocked-cluster
  wins ($534, $475, $405, $366, $348, $332, $285, $184, $138, $95, $85 -- all range_position
  = 1.0, all `BULLISH_RECLAIM_RIDE_THE_RIBBON`, all on confirmed BULL-ribbon/BULL-15m days)
  sit *inside* this same chase bucket. The metric as built cannot tell a fresh breakout
  continuation (winning) from an exhaustion chase (losing) -- both print range_position near
  1.0. **Proposed change: INSTRUMENT_ONLY** (below) -- keep measuring, do not gate live.

## Method

**Population.** Every trade in `analysis/pain-ledger/mae-mfe.json` (the existing, already-
verified real-fills-derived position ledger: broker fills + real Alpaca OPRA 1-min bars, engine
attribution only, one row per reconstructed position) with `date >= 2026-08-06`. **n=191**
positions across `bold-2` (32), `risky-1` (47), `risky-3` (41), `safe-2` (42), `safe-3` (29).
This is a materially larger, cleaner population than `analysis/entry-quality/entry-location-
shadow.jsonl` (n=23, 08-13 only, requires a live Alpaca fetch to grow -- can't be extended
under this task's network ban) and than the 2026-08-14 ENTRY-LOCATION-GATE study (n=29 on the
bull side, explicitly NOT-RUN for a floor of n>=30).

**range_position at entry (no look-ahead).** `core-decisions.jsonl` logs the underlying SPY
price at **1-minute cadence for both the safe and bold accounts**, for every trading day --
this is the *same underlying instrument* regardless of which of the 5 arms actually took the
trade, so it is a valid, already-cached, per-minute SPY tape for every arm's fills. For each
trade: take every tick on that date with `ts_et <= entry_ts` (entry time converted UTC->ET via
`zoneinfo`, DST-correct), compute `session_hi = max(spy)`, `session_lo = min(spy)` over that
prefix only, and `spy_at_entry` = the last such tick's price. `range_position = (spy_at_entry -
session_lo) / (session_hi - session_lo)`, rounded to 4dp. This is **byte-identical in formula**
to the engine's own `conviction.py` C4 component (`pos = (c - lo) / (hi - lo)`), with one
deliberate difference: conviction's envelope is "prior-day-union-today" (frozen default,
`RANGE_EXTREME_PCT=0.30`); this study's envelope is **session-so-far only**, per the harness's
explicit instruction ("high/low of the session so far"). 5 rows (all 2026-08-14, entries at
09:46-09:47 ET, 2-6 minutes into the session) had `session_hi == session_lo` (no range had
developed yet) and are **excluded and named** in `meta.excluded_rows` of the JSON -- never
zero-filled. **n=186 usable.**

**Side.** Parsed from the OCC symbol (`SPY<YYMMDD><C|P><strike>`).

**Chase-extreme definition** (matches the harness's stated hypothesis, which is the *inverse*
of what `conviction.py` C4 rewards -- C4 pays +1 for puts near the TOP and calls near the
BOTTOM of the envelope, i.e. reversal-at-extreme; this study tests calls near the TOP / puts
near the BOTTOM, i.e. momentum-chase-at-extreme): `chase = (side=='C' and pos>=hi_t) or
(side=='P' and pos<=lo_t)`, swept at `(hi_t, lo_t) in {(0.75,0.25), (0.80,0.20), (0.90,0.10)}`.

**VIX regime** at entry: last known `vix` tick at/before entry, same no-look-ahead rule, bucketed
`<15 / 15-17 / >17` per doctrine. (No `>17` days in this window fell in the usable population's
regime cut with a nonzero chase bucket after the 0.75/0.25 split -- see `by_regime` in the JSON;
only `<15` and `15-17` populate.)

**First-exit stage.** For safe-2/bold-2, scanned every `core-decisions.jsonl` row for that
`(arm, date, symbol)` with a `placed:true` `exit_pass` action, took the earliest by timestamp.
Same for `safe-3`/`risky-1`/`risky-3` against their own `automation/state/fleet/<arm>/
decisions.jsonl`. Matched **190/191** trades; 1 (2026-08-10, risky-1, `SPY260810P00773000`,
-$440) had no matching placed exit action in either source and is reported with
`first_exit_stage: null` -- **named, not dropped.**

**Bootstrap.** All CIs are 5,000-resample nonparametric bootstrap (numpy `default_rng(20260903)`
fixed seed, reproducible), 2.5/97.5 percentile.

**No look-ahead.** Every feature (`range_position`, `vix_at_entry`) uses only ticks with
`ts_et <= entry_ts` on the same date. `first_exit_stage` is diagnostic only (recorded strictly
after entry, used to characterize *how* a trade ended, never as an entry-time feature).

## Threshold sweep (primary result)

| Threshold | Chase n | Chase mean $ (CI95) | Chase WR / PF | Rest n | Rest mean $ (CI95) | Rest WR / PF | Diff (chase-rest), CI95 |
|---|---|---|---|---|---|---|---|
| 0.75 / 0.25 | 103 | $2.12 [-31.71, 36.01] | 0.320 / 1.032 | 83 | $18.90 [-25.46, 63.72] | 0.373 / 1.338 | -$16.79 [-72.84, 38.91] |
| 0.80 / 0.20 | 99 | -$5.14 [-37.66, 29.64] | 0.303 / 0.926 | 87 | $26.39 [-14.40, 72.46] | 0.391 / 1.492 | -$31.53 [-85.91, 22.40] |
| 0.90 / 0.10 | 69 | $20.07 [-22.61, 66.04] | 0.333 / 1.317 | 117 | $3.44 [-30.29, 38.37] | 0.350 / 1.056 | **+$16.64** [-40.38, 72.37] |

Every CI on the chase-vs-rest gap crosses zero. The sign flips between 0.80/0.20 and 0.90/0.10.
**This is not a threshold-robust effect.**

**Literal mid-band check** (0.40-0.65, the band the operator context cited for winners):
n=32, mean $51.69/trade, WR 0.406, PF 2.14, vs everything outside the band (n=154, mean
$0.86/trade, WR 0.331, PF 1.01). Diff **+$50.82, CI95 [-25.32, 133.99]** -- the largest point
estimate in this study and directionally the strongest support for "mid-range wins," but still
not significant at n=32.

## By arm (0.75/0.25 split)

| Arm | Chase n / mean $ / WR / PF | Rest n / mean $ / WR / PF |
|---|---|---|
| bold-2 | 21 / $15.71 / 0.429 / 1.232 | 10 / $26.00 / 0.300 / 1.431 |
| risky-1 | 19 / $5.53 / 0.263 / 1.074 | 27 / $18.15 / 0.444 / 1.340 |
| risky-3 | 20 / -$0.70 / 0.300 / 0.990 | 20 / -$5.25 / 0.300 / 0.908 |
| safe-2 | 26 / $7.81 / 0.308 / 1.142 | 15 / $24.20 / 0.267 / 1.494 |
| safe-3 | 17 / -$23.88 / 0.294 / 0.665 | 11 / $51.00 / 0.545 / 1.770 |

4 of 5 arms point the hypothesized direction (chase worse than rest); risky-3 is flat-to-inverse
but both buckets are near-breakeven there regardless. Per-arm n is too small (17-27 per cell) for
its own CI to be informative -- reported for directional consistency only, not as independent
evidence.

## By regime (VIX at entry, 0.75/0.25 split)

| Regime | Chase n / mean $ / WR / PF | Rest n / mean $ / WR / PF |
|---|---|---|
| VIX < 15 | 30 / -$14.07 / 0.267 / 0.847 | 49 / $28.37 / 0.388 / 1.581 |
| VIX 15-17 | 73 / $8.77 / 0.343 / 1.154 | 34 / $5.26 / 0.353 / 1.079 |

The effect is concentrated in the calm regime (VIX<15): chase entries lose there (PF 0.847)
while rest entries do well (PF 1.581). In the 15-17 band the two buckets are nearly identical.
No `>17` days had enough chase-bucket volume in this window to report a cell.

## By setup (confound disclosure)

| Setup | n | Chase n / mean $ / PF | Rest n / mean $ / PF | Diff CI95 |
|---|---|---|---|---|
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 108 (58%) | 67 / -$0.87 / 0.988 | 41 / $42.27 / 1.665 | -$43.13 [-128.89, 37.97] |
| BEARISH_REJECTION_RIDE_THE_RIBBON | 43 (23%) | 31 / $15.13 / 1.228 | 12 / $55.58 / 1.786 | -$40.45 [-227.37, 118.88] |
| VWAP_CONTINUATION | 24 (13%) | 0 (never chases) | 24 / -$22.08 / 0.402 | n/a |
| VWAP_RECLAIM_FAILED_BREAK | 3 | 1 / -$64.00 | 2 / -$68.00 | n/a (n too small) |
| (unattributed) | 8 | 4 / -$32.25 | 4 / -$41.25 | n/a (n too small) |

`BULLISH_RECLAIM_RIDE_THE_RIBBON` alone is 58% of the whole population and carries the
cleanest, largest point-estimate gap ($43/trade) -- but it is also exactly the setup behind the
08-13/08-27 blocked-winner clusters below, and its own CI still crosses zero. `VWAP_CONTINUATION`
never chases at all under this definition (0 of 24 trades hit the 0.75/0.25 bucket) and is a
straight loser (PF 0.402) regardless of location -- location is not this setup's problem.

## Counterfactual: refuse all chase-extreme entries

| Threshold | Would skip | % of population | $ saved (losers avoided) | $ forgone (winners skipped) | Net effect, CI95 |
|---|---|---|---|---|---|
| 0.75/0.25 | 103 | 55.4% | $6,911 (70 losers) | $7,129 (33 winners) | **-$218** [-3,757, +3,220] |
| 0.80/0.20 | 99 | 53.2% | $6,884 (69 losers) | $6,375 (30 winners) | +$509 [-2,955, +3,869] |
| 0.90/0.10 | 69 | 37.1% | $4,372 (46 losers) | $5,757 (23 winners) | -$1,385 [-4,518, +1,574] |

No threshold clears a net-positive CI. The rule is not "avoid a few bad trades" -- it removes
37-55% of ALL engine entries and the dollars saved and forgone are within noise of each other at
every threshold tested.

## Kills winners? -- the required check

| Day | Day total | Trades | Blocked by 0.75/0.25 | $ from blocked trades | Day total if rule applied |
|---|---|---|---|---|---|
| 2026-08-06 | $1,465 | 4 | 1 | -$36 | $1,501 (marginally better) |
| **2026-08-13** | **$1,748** | 15 | **6** | **+$1,895** | **-$147 (day flips to a LOSS)** |
| 2026-08-27 | $1,897 | 12 | 8 | +$1,122 | $775 (cut 59%) |
| 2026-08-28 | $1,304 | 11 | 5 | -$755 | $2,059 (better) |

**2026-08-13 is decisive against the naive rule.** All 6 blocked trades that day are
`BULLISH_RECLAIM_RIDE_THE_RIBBON` calls at `range_position=1.0`, confirmed `ribbon=BULL`,
`htf_15m=BULL` -- a fresh-breakout continuation entry, not an exhaustion chase, and 5 of the 6
were winners ($534, $405, $366, $348, $332; one -$90 loser). Same pattern on 08-27 (7 of 8
blocked trades at `range_position=1.0`, one at 0.987, same setup, same BULL/BULL confirmation;
**6 winners of 8**: $475, $285, $184, $138, $95, $85; 2 losers: -$100, -$40).
`range_position` alone cannot distinguish "SPY is making a fresh high and this call is riding
it" from "SPY is exhausted at the extreme and this call is about to reverse" -- both print
`pos≈1.0` by construction (the entry print IS the new high). A global gate on location without a
trend-quality co-signal would have converted one of the four named anchor days into a losing
day. **This is disqualifying for the literal global rule as a live change.**

## Cross-reference: companion H2 finding (independent corroboration)

A parallel analysis in this same session, `range-extreme-dead.md` (H2, `conviction.py` C4
dead-component audit), found -- independently, from the full ledger population rather than
this study's mae-mfe subset -- that `BULLISH_RECLAIM_RIDE_THE_RIBBON` calls have **mean
range_position 0.812** (range 0.336-1.000, n=270) and `BEARISH_REJECTION_RIDE_THE_RIBBON` puts
have **mean range_position 0.138** (range 0.000-0.445, n=242), because both triggers fire
*after* the directional push that puts price near the session extreme -- it is how the trigger
is built, not a discretionary "chase" decision at entry time. That mechanically explains why
this study's chase bucket swallows 67 of 108 (62%) `BULLISH_RECLAIM` trades: most of that
setup's population sits above 0.75 by construction, so the "chase vs not" split inside this
setup is mostly separating early-in-the-push entries (lower pos, this study's "rest") from
later-in-the-push entries (higher pos, "chase") -- not separating "good setup" from "bad setup."
This corroborates, from an independent read of a different ledger slice, the same conclusion:
`range_position` on these triggers measures *how far the move had already run*, not an
independent location edge, and a gate on it needs a trend-quality co-signal to mean anything.

## Conviction cross-check

36 of the 191 trades (safe-2/bold-2 only, `conviction` shadow logging started 2026-08-13) carry
the engine's own `conviction.components.range_position` alongside this study's recomputation.
Mean absolute difference: **0.138** (expected -- conviction's envelope is prior-day-union-today,
this study's is session-so-far, per harness instruction). Directionally correlated, not
identical -- see `conviction_cross_check.sample_rows` in the JSON. Separately: **all 36** of
these rows scored `conviction.components.range_extreme == 0` -- the engine's own stricter,
reversal-favoring location component (top/bottom 30% of the prior-day-union envelope) never
once rewarded these entries. Conviction is `shadow_only: true` and does not gate any live
trade today, consistent with CLAUDE.md.

## Concentration disclosure

Chase bucket (0.75/0.25, n=103, net $218): top-3 trades by |$| sum to **$521** (534 win / -488
loss / 475 win) -- more than 2x the bucket's net total; the bucket's net result is a coin-flip
between a handful of large prints, not a broad small edge. Rest bucket (n=83, net $1,569):
top-3 sum to **$2,043** (830 / 650 / 563, all winners) -- **130% of the bucket's own net total**,
meaning the "rest wins more" result is itself carried by 3 trades, with the remaining 80 trades
netting **-$474** combined. Neither bucket's result should be read as a broad, dependable edge at
this n.

## What this does NOT test

- No causal claim about *why* extreme-location entries sometimes lose -- MAE-before-first-exit
  timing, spread cost, or theta at entry are not decomposed here.
- `first_exit_stage` in the tables above is descriptive (what stopped the trade), not causal --
  per the pain-ledger's own prereg, MAE/exit-shape knowledge is hindsight (C6) and validates no
  stop-placement change.
- Regime cut is thin (`>17` unpopulated for the chase bucket in this 08-06..09-03 window) --
  every VIX>17 day this window either had zero engine fills or zero fills landing in the chase
  bucket.

## Proposed change

**NONE to any live gate.** The evidence fails the harness's own bar three ways: (1) not
threshold-robust (sign flip 0.80->0.90), (2) every CI on the dollar effect crosses zero at
every threshold and cut tested including the single best-looking sub-slice
(`BULLISH_RECLAIM_RIDE_THE_RIBBON`), (3) the naive global rule turns a $1,748 named winning day
into a -$147 day. A live rule change is also moot procedurally: the September config freeze
(through 2026-10-30) and this task's own trading-path-file lock both block it regardless.

**INSTRUMENT_ONLY (recommended next step, $0, no network):** promote `money_entry_location.py` /
`money_entry_location_stats.py` from scratch tools into a small nightly-refreshable shadow
ledger (reads only `core-decisions.jsonl` + `mae-mfe.json`, both already produced by existing
fires -- no new data source, no new cost) that logs `range_position`, `setup`, `side`, and
`realized_pnl` per trade going forward. Pre-register ONE follow-up test before touching any
live rule: `BULLISH_RECLAIM_RIDE_THE_RIBBON` chase (pos>=0.75) vs rest, re-run once
`n_chase >= 150` for that setup alone (currently 67) -- and require the chase bucket to be
conditioned on a trend-quality co-signal (e.g. `htf_15m`/`ribbon` confirmation duration, or
distance since the ribbon flip) so a fresh-breakout continuation can be told apart from an
exhaustion chase before any gate is proposed. Until then this is a measured, disclosed, KNOWN
open question -- not a rule.

## Data sources

- `analysis/pain-ledger/mae-mfe.json` (population + realized_pnl; provenance: broker fills +
  real OPRA 1-min bars, engine attribution only)
- `automation/state/core-decisions.jsonl` (per-minute SPY/VIX tape for range_position + VIX
  regime; exit_pass actions for safe-2/bold-2 exit stage; conviction cross-check)
- `automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl` (exit_pass actions for
  fleet-arm exit stage)
- `setup/scripts/conviction.py` (range_position formula reference, C4 component)
- `analysis/entry-quality/entry-location-shadow.jsonl` (checked, not used as primary population
  -- n=23, network-dependent to extend, superseded here by the larger cached-data pipeline)

All figures in this report are reproducible from the two JSON artifacts beside this file by
re-running the two `backtest/tools/money_entry_location*.py` scripts (deterministic bootstrap
seed `20260903`).
