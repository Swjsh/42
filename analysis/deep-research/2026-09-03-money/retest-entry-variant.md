# H10 RETEST ENTRY -- replay vs actual breakout entries

Stamp: 2026-09-03T10:24 ET. Generated: 2026-09-03T11:00 ET (`et_clock.py`, verified fresh this
session). Analyst: subagent, read-only against `automation/state/**` and `journal/**` (US
market OPEN, live paper engine running on this box during this analysis). No broker/market-data
calls made -- cached bars only, per hard constraint.

## Verdict

**INCONCLUSIVE.** The sign of H10's aggregate effect **flips** depending on one free parameter
this study could not pin down from cached data: the retest zone's width. At the instructed
$0.30 default (no historical `key-levels.json` zone-width archive exists for this window), H10
loses **-$2,850.30** (-79%) against the actual breakout entries, driven almost entirely by
gutting the book's two biggest recent trend days. At a $0.50 zone (well inside the $0.30-$0.85
range actually observed in *today's live* `key-levels.json`), H10 **wins** **+$954.60** (+26%)
and specifically fixes the 08-28 problem. Neither point estimate clears a 95% bootstrap
significance bar on its own. **Do not ship, not even to shadow**, until the zone-width
parameter has real footing (see Recommendation).

## Hypothesis

J's philosophy: levels are zones, wait for the return, don't chase. H10 defines a retest
variant of RIDE_THE_RIBBON: instead of entering on the breakout tick, wait for the first
pullback that touches the trigger zone (trigger_level +/- zone width) and then prints a 1-minute
close back in the trade direction, within 30 minutes of the trigger; cancel if the zone breaks
first.

## Method

1. **Population**: every `PLACED` (core: safe-2/bold-2) or `ENTER_BULL`/`ENTER_BEAR` with
   `placement.placed=true` (fleet: safe-3/risky-1/risky-3/safe-1 -- the 5 active real-fills
   arms per CLAUDE.md) row for `setup` in `{BULLISH_RECLAIM_RIDE_THE_RIBBON,
   BEARISH_REJECTION_RIDE_THE_RIBBON}` since 2026-08-06: **125 candidate orders** (21 core + 104
   fleet). Joined to `automation/state/fills-ledger.jsonl` on the decision row's broker
   `order_id`, `side="buy"`, `attribution="engine"` (decision-row broker blocks are a PLAN-TIME
   snapshot, often still `pending_new`/`new` -- the ledger is the only broker-verified fill
   truth). **122/125 matched a real buy fill** (3 orders never filled/rejected -- excluded, no
   further attempt to reconstruct them).
2. **Exclusions** (named, in order applied):
   - **8 rows dated 2026-09-03** (today, the live session) -- no cached SPY/option bars exist
     for a session still in progress. Excluded outright, not backfilled with any assumption.
   - **5 rows with no `trigger_level`** recorded on the decision row -- a retest zone can't be
     defined without one. Excluded.
   - **6 rows on 2026-08-07** (3 distinct decision ticks x the arms that fired on each) --
     `backtest/data/spy_sip_cache/spy_1m_2026-08-07.json` is truncated (ends 12:01 ET; the
     entries land at 12:07/12:37/12:40 ET), a genuine data-collection gap, not a code bug
     (confirmed: cache file's last bar is `2026-08-07T12:01:00`). Excluded from the
     retest-vs-actual comparison so both sides are scored over the identical population; their
     actual (breakout-only) walked P&L is disclosed separately (-$1,885.50 aggregate, not
     counted in any headline number below).
   - **Net comparable population: 103 trades across 15 distinct trading days**
     (2026-08-06 .. 2026-09-02).
3. **Retest zone**: `trigger_level +/- $0.30` (the hard-constraint-stated default -- no archived
   `key-levels.json` snapshot exists for any date in this window under
   `analysis/level-quality/snapshots/` or elsewhere; today's live file shows zone widths ranging
   $0.30-$0.85 across active levels, so $0.30 is the *narrow* end of what's actually used live).
   Retest logic (1-minute SPY bars, `backtest/data/spy_sip_cache/spy_1m_<date>.json`, strictly
   after the original trigger tick, <=30 min window): for a CALL, `seen_touch` flips true on the
   first bar whose LOW reaches the zone top; once touched, the first bar whose CLOSE reclaims
   >= trigger_level is the retest entry (can be the same bar -- a wick-and-reclaim). Invalidate
   (no trade) if any bar CLOSES below the zone floor before confirmation. Symmetric for PUTs.
   Timeout (no trade) if 30 minutes elapse with neither outcome. Full logic:
   `backtest/tools/money_retest_entry_variant.py:retest_decision`.
4. **Entry price** (retest side, synthetic -- no real fill exists for a trade that wasn't
   taken): the OPEN of the first cached option bar at/after (confirmation-bar-close + 1 minute)
   -- the engine's next tick after the confirming bar closes, same point-sample convention
   `exit_manager_walk.py` itself uses (bar open as the NBBO-fill proxy).
5. **Exit engine, BOTH sides**: `backtest/lib/exit_manager_walk.walk_exit_manager`, i.e. the
   REAL production `automation/state/fleet/exit_manager.py plan_exit_actions` ticked over cached
   bars -- same exit shape (`strategies.by_name("ribbon_ride").exit.to_dict()`),
   `structure_stop_enabled=True`, `time_stop_et=15:40` (verified live in both `params.json`
   files), same `trigger_level`, same qty, for both the actual breakout entry (real fill
   price/time) and the retest entry (synthetic price/time) where one occurred. This makes the
   comparison **simulated-vs-simulated** (isolates the entry-timing change from the exit model)
   rather than simulated-vs-real-fill: 22 of 82 (arm,symbol) groups had multiple same-day
   re-entries with no reliable way to attribute later sell fills to a specific buy order, so a
   real-fill P&L comparison per specific entry was not attemptable faithfully.
6. **Bars**: `backtest/data/spy_5m_2026-05-19_2026-09-02.csv` (RTH-filtered, ribbon computed via
   `lib.ribbon.compute_ribbon` -- causal EMAs, no look-ahead) for `five_min_spy_df` and the
   ribbon-flip-back check (day-sliced + positionally realigned to each contract's own bar
   series, exactly mirroring `exit_manager_replay.py`'s established convention);
   `backtest/data/options/<symbol>.csv` (5-min OPRA) for option bars, falling back to
   `backtest/data/highres/<symbol>_1m_<date>.csv` (1-min) for the 4 contracts (all 2026-09-02)
   missing from the 5-min cache.

## No-look-ahead statement

The retest decision at trigger tick `t0` only reads SPY 1-minute bars strictly *after* `t0`
(sequential walk-forward, not a peek at how the move ultimately resolved). The ribbon is causal
(EMA state at bar *i* depends only on bars `<= i`). The structure-stop check
(`last_closed_bar_close_at`) only uses 5-min bars already closed by each walk tick's own "now"
-- unmodified production code. The retest entry price uses only the option bar available at/after
the confirmation instant. The one acknowledged uncertainty is the zone-width value itself (see
Verdict) -- a *parameter* choice, not a temporal leak.

## Headline result -- $0.30 zone (primary, per the stated default)

| | Actual (breakout, walked) | H10 retest variant |
|---|---|---|
| Trades taken | 103 | 70 (68%) -- 33 sat out (11 invalidated, 22 timeout) |
| Total P&L | **+$3,619.20** | **+$768.90** |
| WR | 39.8% | 40.0% (of the 70 taken) |
| PF | 1.458 | 1.143 (of the 70 taken) |
| Bootstrap 95% CI, mean $/trade (retest - actual), 5000 resamples | -- | **-$27.67** [-$65.38, +$7.95] -- spans zero |

- **Net effect: -$2,850.30 (-79% of the actual book).** Every one of the 5 arms is
  individually negative (bold-2 $283.80 vs $939.60; risky-1 $284.20 vs $708.50; risky-3 $136.80
  vs $910.20; safe-3 -$220.90 vs $175.95; **safe-2 $285.00 vs $884.95** -- safe-2 is the *only*
  arm `WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md` clears for walker magnitude fidelity
  (aggregate_ratio 0.96); its n=5 here is too small to stand alone, but its direction agrees
  with the pooled SIGN-ONLY read for the other 4 arms).
- **Missed winners: 17 trades, +$5,951.60** -- larger than the entire actual book total.
  **Saved losers: 16 trades, -$2,314.00.** Missed winners outweigh saved losers 2.6x in dollars.
- Of trades the variant DID take: 8 flip an actual loser into a retest winner; 4 flip an actual
  winner into a retest loser/scratch.
- **kills_winners = YES, severely, at this zone width.** Day-by-day, the effect is concentrated
  almost entirely in two days:

  | Date | n | confirmed | actual $ | retest $ | delta |
  |---|---|---|---|---|---|
  | 2026-08-27 | 12 | 7/12 | +3,359.80 | +1,967.60 | **-1,392.20** |
  | 2026-08-28 | 9 | 2/9 | +2,662.60 | -420.00 | **-3,082.60** |
  | all other 13 days combined | 82 | 61/82 | -402.20 | +1,222.30 | **+1,624.50** |

  Excluding just 08-27/08-28, H10 would have been **net positive** (+$1,624.50) over the
  other 13 days -- it helps on chop/losing days (08-21: -$1,469.00 -> -$373.00, delta +$1,096)
  but is disqualifying on the book's biggest right-tail winners. Both 08-27 (VIX 14.5-15.1) and
  08-28 (VIX 14.2-14.8) sit in the `<15` VIX bucket, which shows the same pattern in aggregate:
  **VIX <15 (n=44): actual +$3,432.50 -> retest -$584.90.** VIX 15-17 (n=59): actual +$186.70 ->
  retest +$1,353.80 (retest *helps* in this band). No VIX >17 entries in the window (population
  empty -- that regime is untested here, not confirmed either way). On 08-28 specifically only
  2 of 9 signals got a qualifying retest before the 30-minute window expired -- a fast,
  one-directional trend day offered almost no clean pullback to a $0.30 zone.

## Sensitivity check -- $0.50 zone (same 103-row population, same method, same code)

$0.50 sits inside the $0.30-$0.85 range of zone widths actually carried on *today's* live
`key-levels.json` levels (no historical widths exist for the study window, so this is a
plausible alternate value, not a cherry-pick toward a preferred answer -- it was the first
"one size up" value tried).

| | Actual | H10 retest ($0.50 zone) |
|---|---|---|
| Trades taken | 103 | 83 (81%) |
| Total P&L | +$3,619.20 | **+$4,573.80** |
| WR (of taken) | 39.8% | 45.8% |
| PF (of taken) | 1.458 | 1.729 |
| Bootstrap 95% CI, mean $/trade | -- | **+$9.27** [-$14.54, +$32.36] -- spans zero |
| Missed winners / saved losers | -- | 6 / +$1,555.45 vs 14 / -$1,632.00 (roughly balanced) |
| 08-28 delta | -- | **+$147.00** (was -$3,082.60 at $0.30 -- 8/9 now confirmed vs 2/9) |
| 08-27 delta | -- | -$783.80 (was -$1,392.20 -- 8/12 now confirmed) |

**The sign reverses.** The $0.30-vs-$0.50 gap is explained almost entirely by how many of
08-27/08-28's fast-trend pullbacks a narrow zone catches before the 30-minute window expires --
this is a genuine parameter-sensitivity finding, not noise from a different trade population
(same 103 rows, same exit engine, same everything except the zone width).

## Fidelity caveat (governs every dollar figure above)

Per `analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md`, `walk_exit_manager`
magnitude-fidelity vs real fills **PASSES only for safe-2** (aggregate_ratio 0.96,
sign_agreement 95.8%). bold-2/risky-1/safe-3 individually **FAIL** the magnitude criterion
(ratios 1.72-6.44x, one arm sign-flipped net) -- their dollars here are **SIGN-ONLY** (trust the
direction of P&L, not the magnitude). risky-3 was outside that anchor's scope entirely (not a
go-live-gate `ACTIVE_ARMS` member) -- treat as SIGN-ONLY, unverified even for sign. Only 5 of
103 rows are on the one magnitude-trusted arm (safe-2) -- too few to stand alone on magnitude;
the pooled dollar totals above should be read as directionally indicative, not bankable.

## Would this change have blocked the big winning days?

Checked directly (not inferred) against the 4 named anchor days, at $0.30:

| Date | n entries | confirmed | actual $ | retest $ | Blocked the day entirely? |
|---|---|---|---|---|---|
| 2026-08-06 | 2 | 2/2 | +676.20 | +881.40 | No -- retest slightly BETTER |
| 2026-08-13 | 9 | 9/9 | +994.10 | +1,220.10 | No -- retest slightly BETTER |
| 2026-08-27 | 12 | 7/12 | +3,359.80 | +1,967.60 | No, but -41% |
| 2026-08-28 | 9 | 2/9 | +2,662.60 | **-420.00** | No trade was individually "blocked" to zero, but the DAY flips from the study window's 3rd-biggest win to a net loser |

At $0.30, H10 never fully zeroes a day, but it guts 08-28 and materially cuts 08-27 -- the two
most recent, most concentrated winning days. At $0.50, 08-28 is fixed (delta +$147.00) and 08-27
is still a drag (-$783.80). 08-06/08-13 (smaller, choppier days) are helped by H10 under either
zone width.

## Concentration

At $0.30: actual top-3 trades = $1,966.20 of $3,619.20 total (**54.3%**) -- risky-1 08-28 771C
($885.40), risky-1 08-13 777C ($546.60), safe-3 08-28 771C ($534.20). Retest top-3 = $1,575.00
of $768.90 total (204.8% -- the retest book is thin enough that 3 trades exceed its whole net,
i.e. the rest of the retest book is a net drag on those 3 winners). Both sides are
concentration-heavy; the actual book's concentration is the more normal shape for a
right-tail-edge strategy (per this project's own doctrine, C24/edge-master-doctrine) --
retest's inverted concentration (top-3 > total) is itself a symptom of how much the narrow
zone bled from the rest of the book.

## Regime split

| VIX bucket | n | actual $ | retest $ ($0.30) | confirmed |
|---|---|---|---|---|
| <15 | 44 | +3,432.50 | -584.90 | 29/44 |
| 15-17 | 59 | +186.70 | +1,353.80 | 41/59 |
| >17 | 0 | -- | -- | -- (untested, population empty) |

VIX assigned via `core_tick_id` join to `core-decisions.jsonl` (tick-level, shared by every
arm consuming the same signal tick) -- populated for all 103 comparable rows, not just core
arms.

## Interpretation

H10 is not a uniform win or loss -- it is a **trade-off between chop-day protection and
right-tail capture**, and the sign of the net dollar effect depends on a parameter
(zone width) this study cannot independently verify from cached history. This project's stated
edge model (CLAUDE.md: "the engine's edge is a RIGHT TAIL: low WR, losses capped, wins must run
>=1.3x"; C24: "Anchor trades are one-off exceptional setups") makes the 08-27/08-28 sensitivity
the decisive fact, not the aggregate dollar sign: a rule that reliably guts the biggest
right-tail days at a plausible parameter value, and only "fixes" itself at a different
untested-in-history parameter value, is not a rule with a known effect yet.

## Recommendation

**Do not ship. Do not even shadow yet.** Before H10 can be adjudicated:
1. Start persisting historical zone widths (a dated snapshot of `key-levels.json`'s `zone_width`
   field per level, or embedding the zone width actually in force onto each decision row at
   trigger time) so a future replay of this exact hypothesis has real, not assumed, inputs.
2. If a decision is needed sooner, run a **pre-registered** zone-width grid ($0.20/$0.30/$0.40/
   $0.50/$0.75) with the decision rule fixed *before* looking at results (per this project's own
   eval-first doctrine, OP-11 §16) -- two ad hoc points ($0.30, $0.50) is enough to show the
   sensitivity exists, not enough to locate where the effect crosses zero or to trust an
   interpolated "good" value.
3. Any future run should also widen the retest-timing definition test (this run fixed
   30 minutes and 1-minute-close confirmation as literally specified in H10 -- those were not
   swept and could independently matter as much as zone width).

## Data sources

`automation/state/core-decisions.jsonl`, `automation/state/fleet/{safe-3,risky-1,risky-3,
safe-1}/decisions.jsonl`, `automation/state/fills-ledger.jsonl`,
`backtest/data/spy_5m_2026-05-19_2026-09-02.csv`, `backtest/data/spy_sip_cache/spy_1m_*.json`,
`backtest/data/options/*.csv`, `backtest/data/highres/*.csv`, `automation/state/params.json`,
`automation/state/aggressive/params.json`, `automation/state/fleet/strategies.py`,
`backtest/lib/exit_manager_walk.py`, `automation/state/fleet/exit_manager.py`,
`analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md`. Today's live
`key-levels.json` was read only to characterize the plausible zone-width range, never as a
per-trade input (no historical archive exists).

## Caveats (full list)

- Zone width is the dominant, unresolved sensitivity -- see above. This is the single biggest
  reason for INCONCLUSIVE rather than a directional verdict.
- Retest side is 100% simulated (no real fills exist for a trade the live engine never took);
  actual side is walker-simulated too (not real broker P&L), for apples-to-apples comparability
  -- see Method §5. A secondary real-fill-vs-walker cross-check was not attempted (order-level
  sell attribution ambiguity, disclosed in Method §5).
- Non-safe-2 dollars are SIGN-ONLY per the walker fidelity anchor; only 5/103 rows sit on the
  one magnitude-trusted arm.
- 6 rows (2026-08-07) excluded from comparison for a genuine 1-min SPY cache gap, not
  incorporated into any headline number.
- 2026-09-03 (today, still live at analysis time) fully excluded -- 8 candidate entries, no
  cached bars, not backfilled with any assumption or live fetch (hard constraint).
- Entry timestamp for the "actual" side uses the decision row's own `ts_et` (order-placement
  tick) as `t0`, not a separately re-derived "trigger bar" timestamp -- the two are within
  0-5 minutes of each other in this engine's architecture; this is a simplification, disclosed
  rather than silently assumed exact.
- No transaction costs/fees modeled on either side (neither the original studies this project
  runs typically do at this stage; consistent with existing convention, not a gap unique to
  this study).
- Bootstrap: 5000 resamples, 2.5%/97.5% percentile CI, seed fixed (20260903) for reproducibility.
