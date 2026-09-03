# SSR Exit-Quality Decomposition (2026-09-03)

**DIAGNOSIS ONLY. No production code changed.** Answers queue item
`SSR-REAL-BLOCKER-IS-EXIT-QUALITY-NOT-SIZING` (filed 2026-08-23, Opus adjudication):
SSR-v1 reached n=17 round trips with positive absolute expectancy (+$27,335.69) but FAILED
`beats_null` — an unmanaged same-direction hold to the same closing bar returned MORE
(+$30,828.09). The ssr-v2 respec (micro contracts) fixed a **sizing** problem; it did nothing
to the exit logic, so the same failure mode is expected to reproduce at n=20 unless the exit
math itself changes. This note decomposes WHY, per round trip.

## Method

Reused `ssr_shadow.compute_round_trips` + `ssr_shadow.compute_null_pnl` (both pure,
unmodified — no new logic was written to score P&L, only to bucket/sum the existing
per-trip numbers) against `automation/state/futures/ssr-shadow-would-be.jsonl`. Every legacy
(`spec_version != "ssr-v2"`) round trip carries `close_reason` in
`{stopped_pre_tp1, stopped_be, runner, time_flat}` — mapped 1:1 to the requested exit-stage
vocabulary as `stop` / `stop` / `trail` / `time` (SSR's frozen spec never triggers
`stopped_be` in this ledger — 0 occurrences, see below). `compute_null_pnl` is the SAME
same-direction unmanaged full-qty hold from entry to that trip's own `close_bar_close` the
`beats_null` arming check already uses — this note does not invent a new null definition, it
just attributes the existing one per trip.

**Ledger has grown since the queue item was filed** (2026-08-23): 18 legacy round trips exist
tonight, not 17 — one more (`#18`, a `runner` exit, entry 2026-08-21T11:45 ET) closed after
the filing date (consistent with the ssr-v2 respec module docstring: the one position still
open under v1 at respec time was walked forward to its own natural close under
`LEGACY_CONFIG_ALIASES`, never orphaned). **Reproduction check**: summing managed P&L over
the first 17 trips (sorted by `closed_at_et`, the same order `compute_round_trips` returns)
gives **exactly $27,335.69** and their null total is **exactly $30,828.09** — both match the
queue item's cited figures to the cent, confirming this decomposition is reading the same
ledger/logic the original finding used. The 18th trip is reported separately below so the
diagnosis isn't silently rebased on a bigger sample than the one being explained.

## Per-trip table (n=17, the queue's own evidence set)

| # | config | reason | managed $ | null $ | delta (mgd−null) | class |
|---|---|---|---:|---:|---:|---|
| 1 | NQ | runner | 4,495.68 | 3,708.00 | **+787.68** | other |
| 2 | NQ | stopped_pre_tp1 | -2,091.58 | -567.00 | **-1,524.58** | stops_hit_then_reversed |
| 3 | NQ | time_flat | 3,603.00 | 3,603.00 | 0.00 | other |
| 4 | NQ | runner | 6,048.06 | 6,228.00 | **-179.94** | winners_cut_early |
| 5 | GC | time_flat | 4,512.06 | 4,512.06 | 0.00 | other |
| 6 | NQ | stopped_pre_tp1 | -1,348.20 | -4,872.00 | **+3,523.80** | other |
| 7 | NQ | runner | 3,156.98 | 3,453.00 | **-296.02** | winners_cut_early |
| 8 | NQ | stopped_pre_tp1 | -2,544.19 | -3,282.00 | **+737.81** | other |
| 9 | GC | time_flat | 3,582.03 | 3,582.03 | 0.00 | other |
| 10 | NQ | stopped_pre_tp1 | -761.09 | -1,182.00 | **+420.91** | other |
| 11 | NQ | time_flat | 4,353.94 | 1,458.00 | **+2,895.94** | other |
| 12 | GC | stopped_pre_tp1 | -6,600.99 | -6,348.00 | **-252.99** | stops_hit_then_reversed |
| 13 | NQ | time_flat | 7,353.00 | 7,353.00 | 0.00 | other |
| 14 | NQ | stopped_pre_tp1 | -2,054.18 | -1,812.00 | **-242.18** | stops_hit_then_reversed |
| 15 | NQ | runner | 3,394.50 | 6,798.00 | **-3,403.50** | winners_cut_early |
| 16 | NQ | time_flat | -612.00 | -612.00 | 0.00 | other |
| 17 | NQ | runner | 2,848.67 | 8,808.00 | **-5,959.33** | winners_cut_early |

**Totals: managed $27,335.69 vs null $30,828.09 → gap −$3,492.40 (matches queue exactly).**

18th trip (closed after the 2026-08-23 filing, NOT in the totals above): `runner`,
2026-08-21T11:45 ET entry, managed $4,804.32, null $6,648.00, delta **-$1,843.68**
(`winners_cut_early`) — same failure mode, makes it worse: n=18 managed $32,140.01 vs
null $37,476.09, gap widens to **-$5,336.08**.

## Histogram — dollar share by exit-stage class (n=17)

| class | n trips | dollar sum (delta) | share of gross downside |
|---|---:|---:|---:|
| **winners_cut_early** (`trail`/runner exits below the bar's max favourable point) | 4 | **-$9,838.79** | **83.0%** |
| stops_hit_then_reversed (`stop` fired, bar then closed back favourably) | 3 | -$2,019.75 | 17.0% |
| time_exit_cutting_right_tail (`time` flatten below the bar's favourable close) | 0 | $0.00 | 0.0% |
| other (exit matched or beat the null) | 10 | +$8,366.14 | n/a (net positive) |
| **net (managed − null)** | 17 | **-$3,492.40** | — |

Gross downside = sum of every trip with a negative delta = $9,838.79 + $2,019.75 =
**$11,858.54**; winners-cut-early alone is 83% of it despite being only 4 of 17 trips (23.5%
of count). Gross upside from the `other` bucket (+$8,366.14) partially offsets it, netting to
the queue's -$3,492.40 gap.

## What each class actually shows

- **`runner` (trail) exits are the entire mechanism.** 5 of 6 runner-class trips in the n=17
  set underperform an unmanaged hold to the same bar (only trip #1 beat it); dollar-weighted,
  the runner leg alone is worse than the WHOLE reported gap ($9.05K shortfall on 17 trips —
  more than 2.5x the net -$3.49K failure — because the other two exit classes are net
  *helpful*, not neutral). The runner's fixed target — nearest opposing level beyond TP1,
  else 3R fallback capped at 5R (`ssr_shadow.py` `RUNNER_FALLBACK_R_MULT`/
  `RUNNER_CAP_R_MULT`) — is exiting the final 1/3 of size before the bar's fuller favourable
  excursion, on trips 4, 7, 15, 17 (and 18). Trip #17 alone gives back $5,959.33 this way.
- **Stops are NOT the problem — net positive vs null.** 6 `stopped_pre_tp1` trips sum to
  **+$2,662.77** vs their own null (3 trades where the stop clearly saved money over holding
  through a much worse close — #6, #8, #10 — vs 3 where the bar closed back favourably after
  the stop fired, giving up a small amount — #2, #12, #14, the `stops_hit_then_reversed`
  bucket, -$2,019.75 combined). A pre-registered stop-widening or stop-removal fix would be
  chasing the wrong 17% of the gap.
- **Time-based exits are NOT the problem either — net positive, zero instances of the
  hypothesized "cuts the right tail" pattern.** 6 `time_flat` trips sum to **+$2,895.94** vs
  null; five of the six have an EXACT $0.00 delta (never got a TP1 partial before the
  16:55 ET flatten, so the time-exit price and the null's `close_bar_close` price are
  identical by construction — flattening at the close is, in those cases, mathematically
  equivalent to holding to that close). Trip #11 is the one exception, and it's *positive*
  ($2,895.94): a TP1 partial locked in a better blended price than a pure hold would have.
  The a priori hypothesis "time-based exit cutting the right tail" (named explicitly in the
  queue item as a candidate cause) is **not supported by this ledger** — 0 of 17 trips show
  that pattern.

## The one-sentence candidate for v2 (NOT implemented — pre-registration note only)

**Widen or remove the runner leg's fixed profit cap** — replace the "nearest opposing level
beyond TP1, else 3R fallback capped at 5R" runner target with either a genuine trailing stop
or a materially higher R-cap (e.g. 8-10R / uncapped-until-reversal-signal), since 83% of the
n=17 beats_null shortfall traces to that single exit stage capping winners before the bar's
own favourable close, while the stop and time-exit legs are already net-additive and should
be left alone.

## Guard against re-litigating stops/time-exits without cause

Any v2 proposal that touches stop placement or the 16:55 ET time-flatten instead of the
runner target is optimizing legs this decomposition shows are already net-positive — that
would be spending a forward clock on the wrong 17%/0% of the gap while leaving the 83%
mechanism (the runner cap) untouched, reproducing the same `beats_null` failure at n=20+
exactly as the queue item warned.
