# WALKER-STAGE-DISAGREE-RESIDUAL — diagnosis (2026-09-03 03:4x ET, Sonnet, diagnose-only)

Queue item: `automation/overnight/queue.md` WALKER-STAGE-DISAGREE-RESIDUAL, filed 03:22 ET
from the PDT port (WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK). No code changed — this is
a read-only replay of the existing harness plus targeted per-row lookups against
`analysis/trades-enriched.jsonl` (live/broker truth) and re-walks of the 12 flagged rows with
full per-leg detail captured (the standard `harness_validation()` call only keeps the final
leg's stage, not the full leg list).

**Reproduced exactly**: `pdt_blocked_counterfactual.harness_validation(walker="exit_manager")`
on the 43-row PDT anchor gives aggregate_ratio **2.4212**, stage_agree n=30 (median abs err
$26.10), stage_disagree n=13 (median abs err $66.00), disagree_share_of_total_abs_error
**0.5249** — byte-identical to the numbers already logged in the queue item.

## Finding 0 (before the diagnosis): the "13 disagree" count is inflated by a labeling artifact

`stage_decomposition()` (`backtest/lib/walker_magnitude_fidelity.py`) compares
`recorded_stage.split("+")[0]` against `walked_stage.split("+")[0]`. But `walked_stage` (built
in `pdt_blocked_counterfactual._walk_via_exit_manager`, line ~238) is ALWAYS the single last
leg's stage (`legs[-1]["stage"]`), never a compound string — while `recorded_stage`
(`trades-enriched.jsonl`'s `exit_reason`) IS compound whenever the live position closed in two
tranches (e.g. `"tp1+trail"`). Re-walking the 7 `tp1+trail`→`trail` "disagree" rows with full
per-leg detail shows the replay fired **exactly the same two-leg sequence** the broker recorded
(TP1 partial, then trail on the runner) in all 7 cases — e.g. 07-17 `SPY260717P00745000`:
live `tp1+trail` $105; replay legs `[tp1 qty2 @2.00 pnl+200, trail qty1 @1.734 pnl+73.4]` =
$273.4. These are **not stage disagreements** — they are the SAME event sequence, mislabeled as
a mismatch because the comparator's first-token rule (`"tp1+trail"`→`"tp1"`) can never match a
single-token `walked_stage` (`"trail"`) by construction.

Removing those 7 false positives: **true stage_disagree n=6** (not 13), and the abs-error
attributable to genuine event mismatches drops from 52.5% to **28.9%** of total abs error
(605.5 / 2094.3). The remaining 71.1% is pricing drift on CORRECTLY-identified events — see
Finding 2.

## The 6 true disagree rows

| Date | Arm | Symbol | Live stage (time, recorded) | Replay stage (bar) | $ live | $ replay | err | Cause |
|---|---|---|---|---|---|---|---|---|
| 2026-07-15 | safe-2 | SPY260715C00754000 | premium_stop @14:50:05 | structure_stop @14:50 | -117.00 | -147.00 | -30.00 | (a) 5-min bar cadence collapses structure-vs-premium ordering |
| 2026-07-21 | safe-2 | SPY260721P00748000 | ribbon_flip @14:59:03 | premium_stop @15:40 | 0.00 | -49.50 | -49.50 | (f) `ribbon_tick_df=None` — ribbon_flip structurally unreachable |
| 2026-07-23 | bold-2 | SPY260723P00735000 | premium_stop @11:56:04 | structure_stop @12:00 | -305.00 | -385.00 | -80.00 | (a) 5-min bar cadence collapses structure-vs-premium ordering |
| 2026-07-27 | bold-2 | SPY260727P00737000 | premium_stop @14:00:06 | structure_stop @14:00 | -355.00 | -320.00 | 35.00 | (a) 5-min bar cadence collapses structure-vs-premium ordering |
| 2026-07-28 | safe-2 | SPY260728P00741000 | ribbon_flip @13:51:04 | premium_stop @14:50 | 15.00 | -51.00 | -66.00 | (f) `ribbon_tick_df=None` — ribbon_flip structurally unreachable |
| 2026-08-06 | safe-2 | SPY260806P00770000 | tp1+trail (2h47m hold) | time_stop @15:50, 1 leg only | 375.00 | 30.00 | -345.00 | (a) point-sample-at-open on a 5-min bar never reaches the TP1 threshold the bar's HIGH crossed |

median abs error (true disagree, n=6): **$57.75**. mean: $100.92. total: $605.50.

## Cause histogram (n=6 true disagree rows)

| Cause | n | share |
|---|---|---|
| (a) 5-min bar granularity / point-sample-at-open | 4 | 67% |
| (f) missing ribbon signal (`ribbon_tick_df=None`) | 2 | 33% |
| (b) chandelier HWM source, (c) distinct level source, (d) entry-bar convention, (e) time-stop handling | 0 | 0% |

**Dominant mechanism (verified, not inferred from priors):** `plan_exit_actions` checks
structure_stop BEFORE premium_stop, in BOTH live and replay — same production function
(`automation/state/fleet/exit_manager.py:415`), confirmed by reading the code, so the ordering
itself is not the bug. What differs is the INPUT cadence: every one of the 31 distinct option
contracts in the 43-row PDT anchor is cached at **5-minute** resolution (verified —
`load_contract_bars` median bar-to-bar cadence = exactly 5:00 for all 31, zero exceptions), and
`exit_manager_walk.walk_exit_manager` point-samples `best_premium = worst_premium = bar["open"]`
(never bar high/low, by design — see that module's own docstring). At 5-min cadence this
collapses many ticks' worth of live, ~continuously-polled decisions into a handful of coarse
checks: (i) for the 3 structure/premium swaps, both conditions can appear simultaneously true
at the SAME 5-min-bar snapshot even though live's finer polling would have hit premium first,
several minutes before the 5-min bar (that carries the structure cross) even closed; (ii) for
the 08-06 row, the bar's `open` price never reaches the TP1 threshold ($2.56 = 1.28×2.0) even
though that bar's `high` did (2.80 at the 12:15 bar) — a live NBBO poll would have caught it,
the 5-min-open point-sample cannot. This is the SAME residual named in
WALKER-MARKET-STAGE-FILL-ROOT-FIX's negative result ("the 5-min bar decides an exit a live
1-min poll may never have confirmed") — now localized to a specific, checkable input fact
(bar cadence in the cache) rather than a general timing hand-wave. V9 (below) sidesteps most of
this by walking on 1-minute bars.

The other 2/6 (ribbon_flip rows) are a SEPARATE, distinct mechanism: `_walk_via_exit_manager`
(`setup/scripts/pdt_blocked_counterfactual.py:187-238`) passes `ribbon_tick_df=None`
unconditionally — its own docstring already states "ribbon_flip exits are therefore
structurally unreachable." Confirmed: both rows the broker recorded `ribbon_flip` replayed as
whatever OTHER threshold happened to be next (`premium_stop` in both cases), because the
replay has no ribbon signal to check at all.

## Finding 2: the agree-row sign is consistently one-sided (not random noise)

Within the (corrected) stage_agree bucket, `err = replay - actual` is **negative (replay more
adverse) in 25/30 of the module-classified agree rows (83%)**, only 4 positive and 1 exact
zero. This is not symmetric pricing noise — the replay skews adverse on the SAME correctly-
identified event almost every time. Consistent with (not proven to be caused solely by) two
already-disclosed, compounding facts: (1) `exit_slippage` is applied to the 3 market-style
stages (`time_stop`/`ribbon_flip`/`structure_stop`) but not to limit-style stages
(`exit_manager_walk.py`'s own FILL-PRICE CONVENTION note), and this population is
premium_stop/structure_stop-heavy (see composition below); (2) 5-min-open point-sampling
tends to catch a worse fill on a stop (a losing move) than a continuous live poll would, for
the same reason it misses a favorable peak on a winner (Finding above, row 6).

## V9 (121-row) vs PDT (43-row) composition — why the two anchors read opposite signs

| exit stage | V9 n (121) | V9 share | V9 agreement | PDT-anchor n (43) | PDT share |
|---|---|---|---|---|---|
| premium_stop | 31 | 25.6% | 96.8% | 21 (+2 combo) | 48.8% (+4.7%) |
| structure_stop | 46 | 38.0% | 91.3% | 10 | 23.3% |
| tp1+trail | 27 | 22.3% | 88.9% | 8 | 18.6% |
| ribbon_flip | 15 | 12.4% | 66.7% (lowest of all stages) | 2 (+2 combo) | 4.7% (+4.7%) |
| time_stop | 2 | 1.7% | 100% | 0 | 0% |

Source: `analysis/whole-engine-null/2026-09-02.json` → `v9_harness_validation.agreement_by_exit_reason`
(V9), this run's `walker_rows.json` (PDT anchor).

Two independent, additive reasons the PDT anchor reads 2.42 (over-replays losses) while V9
reads 0.645 (under-replays, i.e. conservative):

1. **Granularity.** V9's `walk_one`/`get_1m_bars` (`setup/scripts/whole_engine_null.py`) fetches
   **1-minute** option bars and builds a REAL, reconstructed `ribbon_tick_df` per (date,
   account) via `build_ribbon_tick_df` — so V9's ribbon_flip rows get SOME agreement (10/15,
   66.7%) instead of the PDT anchor's structural zero. The PDT anchor's `load_contract_bars`
   cache is 5-minute-only for every contract checked (31/31), and `ribbon_tick_df` is hardcoded
   `None`.
2. **Composition.** The PDT anchor is disproportionately `premium_stop`-heavy (48.8%+4.7% vs
   V9's 25.6%) and more loss-skewed (32 losers / 10 winners = 76% losing vs V9's 68/121 = 56%
   losing). `premium_stop`'s known fallback price (`runner_stop_premium`, the LEAST-adverse
   price a downside cross can have — the exact mechanism the WALKER-MARKET-STAGE-FILL-ROOT-FIX
   negative result already named) systematically over-replays losses, and a population with
   MORE premium_stop exits AND MORE losers concentrates that bias instead of averaging it out
   against the structure-heavy, more win-balanced V9 population.

Both effects push the SAME direction (PDT replay skews more negative than V9's), which is
consistent with — not merely coincident with — the observed opposite-sign ratios.

## What this changes about the queue item's own framing

The 52.5%-of-abs-error figure attributed to "stage disagreement" in
WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK's partial note is **overstated by a measurement
artifact** (Finding 0): the true structural-disagreement share is 28.9%, not 52.5%. The
remaining ~71% of abs error is a PRICING gap on correctly-identified events (Finding 2), not an
event-selection gap — a different, and arguably harder, problem (it needs the same 5-min→1-min
bar upgrade, not a stage-logic fix).

## Proposed fixes (named, not implemented — evidence only)

1. **Measurement artifact** (Finding 0): `backtest/lib/walker_magnitude_fidelity.stage_decomposition`
   should compare `recorded_stage`'s LAST token (or the full compound string reconstructed from
   `res["legs"]`) against `walked_stage`, not the first token — `walked_stage` in
   `pdt_blocked_counterfactual._walk_via_exit_manager` (line 238) should report the FULL
   `"+".join(leg["stage"] for leg in legs)` instead of only `legs[-1]["stage"]`.
2. **Ribbon gap** (2/6 true disagree): wire `_walk_via_exit_manager` to build a real
   `ribbon_tick_df` the same way `setup/scripts/whole_engine_null.py#build_ribbon_tick_df` does
   for V9, keyed off `fill["account"]`/`fill["date"]` (the PDT population already carries
   `account` on every intent).
3. **Bar granularity** (4/6 true disagree, and likely most of the 71% pricing-only error too):
   this population needs 1-minute option bars, not the 5-minute OPRA cache
   `load_contract_bars` currently serves — either fetch 1-min bars the way
   `whole_engine_null.get_1m_bars` does (network/cache cost, not free) for the 43-row PDT
   population, or disclose the ratio-2.42 verdict as bounded by "5-min-bar-cache resolution,"
   not treat it as a walker defect independent of input data.

## Verdict on the queue item's own gate

**Do NOT migrate `WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK`'s remaining consumers yet.**
Both anchors still fail `walker_magnitude_fidelity`'s PASS criterion (V9 0.645, PDT 2.42) and
this diagnosis did not change either number — it explains WHY they diverge, and shows the fixes
(#2, #3 above) are inherently different in kind (an input-completeness fix vs a bar-cache
resolution upgrade with a real fetch cost), not one shared knob.

## UNVERIFIED / not checked this session

- Whether upgrading the PDT anchor to 1-minute bars (fix #3) would actually move its ratio
  toward 1.0 — not simulated; the fetch/cache cost was not attempted tonight (single-reader
  OPRA-cache constraint, and this was scoped as diagnose-only).
- The `exit_slippage` asymmetry's exact dollar contribution to Finding 2's 83% one-sidedness
  was not isolated (would need an ablation re-walk with `exit_slippage=0`) — named as
  consistent with, not proven to fully explain, the sign skew.
- V9's own ribbon reconstruction (`build_ribbon_tick_df`) is itself a disclosed approximation
  (not the literal live ribbon read) — its 66.7% agreement is a ceiling, not ground truth.

## Closure text for the queue item

**status: diagnosed** (not closed — no fix implemented per this item's own "diagnose only" scope).
Cause histogram for the true 6-row residual: 4/6 (67%) 5-min-bar-cadence/point-sample-at-open,
2/6 (33%) missing ribbon signal. Neither anchor passes the magnitude criterion yet; the
WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK migration stays blocked. New follow-on candidates
named above (#1 measurement-artifact fix is cheap/pure; #2 ribbon wiring is moderate; #3 bar
upgrade has a real fetch cost and should be scoped/budgeted separately, not folded in silently).
