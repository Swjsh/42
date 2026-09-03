# H5 STRUCTURE-STOP WHIPSAW (2026-09-03)

Stamp: 2026-09-03T10:24 ET. Full machine-readable data + citations:
[`structure-stop-whipsaw.json`](structure-stop-whipsaw.json). Raw population:
[`structure-stop-population.json`](structure-stop-population.json). Full per-position
detail: [`structure-stop-buffer-sim.json`](structure-stop-buffer-sim.json). Builders
(read-only on `automation/state`/`journal`, cached data only, no network/broker calls):
[`backtest/tools/money_structure_stop_extract.py`](../../../backtest/tools/money_structure_stop_extract.py),
[`money_structure_stop_buffer_sim.py`](../../../backtest/tools/money_structure_stop_buffer_sim.py),
[`money_structure_stop_report_build.py`](../../../backtest/tools/money_structure_stop_report_build.py).

## VERDICT: whipsaw is REAL. A price/time buffer to fix it is REFUTED — no candidate ships.

- **The diagnostic premise is SUPPORTED**: after a real `structure_stop` exit, SPY closes back
  through the trigger level (in the exited side's favor) **55.7%** of the time within 15 minutes,
  **70.9%** within 30, **78.5%** within 60 (n=79). Structure stops are whipsaw-prone, exactly as
  hypothesized.
- **Every one of the 5 candidate fixes is REFUTED as a live rule**: all 5 go **net NEGATIVE**
  once the single best-contributing day is excluded (drop-best-day), and the two candidates with
  a positive headline number (`BUF-0.25`, `BUF-ATR0.5x`) owe **96.6%** of their positive dollars to
  the top 3 (of 79) positions — the exact dead-frequency/concentration pattern the prior
  `structure-stop-zone-band` prereg (CLOSED 2026-08-11) already found and closed on a different
  population.
- **change_class: NONE.** No trading-path edit is proposed or licensed by this study.

## Population

93 raw `structure_stop` SELL_ALL actions with `placed:true` extracted directly from
`automation/state/core-decisions.jsonl` (38) and `automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl`
(55), matched 1:1 to their entry trade in the frozen `analysis/pain-ledger/mae-mfe.json`
(89/93 matched cleanly, 0 ambiguous/reused matches). Excluded from the buffer simulation: 4 events
from **today, 2026-09-03** (market open, in progress — no forward bars exist yet to measure a
15/30/60-minute counterfactual against, so they cannot be scored either way), and 10 events with no
cached 5-minute option bars (`backtest/data/options/` covers 30/34 unique symbols in the
population). **n=79 usable**, 17 distinct trading days, 2026-07-13..2026-08-27, all 5 live arms
(safe-2 18, bold-2 16, safe-3 20, risky-1 18, risky-3 7).

5/89 events show a >$0.10 discrepancy between the ledger's own `last_closed_5m_close` and the
cached SPY 5m series at the same timestamp (median discrepancy $0.015, disclosed as rounding
noise; the 5 outliers are retained, not dropped — same live-feed-vs-cached-CSV provenance gap
`WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03` documents elsewhere). Every "control" bar in
this study is anchored by **time** (nearest closed 5m bar strictly before the ledger's own stop
timestamp) — never re-derived by walking forward from an approximate entry match, and never by a
full walker replay — precisely so this study inherits none of that documented replay-vs-live gap.

## Whipsaw diagnostic

| Horizon | Reclaims trigger level | Rate |
|---|--:|--:|
| 15 min (3 bars) | 44/79 | 55.7% |
| 30 min (6 bars) | 56/79 | 70.9% |
| 60 min (12 bars) | 62/79 | 78.5% |

Reclaim = SPY closes back through `trigger_level` in the ORIGINAL side's favor (a call's stop
level reclaimed from below; a put's stop level reclaimed from above) at any point in the window.
This is a strong, unambiguous signal that the live rule's single-closed-5m-bar, zero-buffer test
(`automation/state/fleet/exit_manager.py::_structure_stop_hit` — calls exit `close < trigger_level`,
puts exit `close > trigger_level`, no buffer, no confirm count) is catching a lot of noise, not
just genuine structure breaks — the premise motivating H5 holds up on real, recent data.

## Candidate buffer/confirm variants tested

All 5 use **only entry-tick-available information** (closed bars strictly before the evaluation
point; the ATR variant's lookback never reaches past the bar being evaluated) and are walked
forward from the REAL stop bar — a buffered/confirmed rule can, by construction, never fire
*before* the raw unbuffered rule does, so every variant is bounded to fire on or after the actual
stop bar. Every variant enforces the SAME -50% catastrophe cap and 15:50 ET hard time-stop as a
floor/ceiling, identically, so "loosening" the structure stop never removes the safety net —
only whether/when the tighter structure exit itself fires.

| Variant | n | mean Δ$ (95% CI) | sum Δ$ (95% CI) | helped / hurt / flat | $ saved | $ extra loss absorbed | drop-best-day sum |
|---|--:|---|---|---|--:|--:|--:|
| BUF-0.15 ($0.15 fixed) | 79 | −$6.30 (−27.65, 21.24) | −$498 (−2,184, 1,678) | 3 / 35 / 41 | +$1,547 | −$2,045 | **−$2,045** (best day 08-11 +$1,547) |
| BUF-0.25 ($0.25 fixed) | 79 | +$56.98 (−8.89, 135.11) | +$4,502 (−702, 10,674) | 10 / 43 / 26 | +$8,002 | −$3,501 | **−$584** (best day 08-04 +$5,085) |
| BUF-ATR0.5x (0.5× trailing 12-bar 5m ATR) | 79 | +$47.01 (−22.13, 125.22) | +$3,714 (−1,748, 9,892) | 10 / 48 / 21 | +$8,002 | −$4,288 | **−$1,203** (best day 08-04 +$4,917) |
| TWO-CLOSES (2 consecutive raw-breach closes) | 79 | −$20.63 (−44.53, 8.25) | −$1,630 (−3,518, 652) | 13 / 57 / 9 | +$1,748 | −$3,378 | **−$3,197** (best day 08-11 +$1,567) |
| GRACE-1BAR (fire 1 bar later, unconditionally) | 79 | −$3.42 (−17.24, 10.63) | −$271 (−1,362, 840) | 29 / 41 / 9 | +$1,620 | −$1,891 | **−$687** (best day 08-19 +$416) |

**Every 95% CI on the aggregate crosses zero except when regime-split (see below) — none of the 5
candidates clears significance on the pooled population, and every one of the 5 flips net negative
once its single best day is excluded.**

### Concentration (why the headline BUF-0.25/BUF-ATR0.5x numbers are not real)

BUF-0.25's net +$4,502 total is **96.6%** attributable to its top 3 (of 79) positions alone
(+$4,350 of the $4,350 vs. gross positive contribution of $8,002 spread across 10 helped
positions) — removing just those 3 positions collapses the net result from +$4,502 to **+$152**,
i.e. statistically indistinguishable from zero. Those 3 positions are 3 of the 4 arms hit by the
**same single SPY signal-day** (2026-08-04, `SPY260804C00768000`, bold-2/risky-1/risky-3 legs each
worth +$1,450, safe-3 +$870 not in the top 3) — one whipsaw event, replicated across arms by the
shared signal (CLAUDE.md: "arms are risk profiles, NOT strategies... they trade the SAME shared
signal" — the same correlated-replication pattern
`WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03` documents independently for its own 08-13
worked example). Treating n=79 as 79 independent trials overstates the evidence; the true
independent-signal-day count behind BUF-0.25's headline number is closer to 2-3.

Every variant's "extra loss absorbed" side is concrete and mechanical, not a modeling artifact:
loosening the structure stop increases how often a position instead rides down into the -50%
catastrophe cap. Under the CURRENT live rule (zero buffer) none of these 79 positions ever reaches
the cap by definition (the tighter stop always fires first). Under BUF-0.15 that rises to **14/79
(18%)**; under BUF-0.25/BUF-ATR0.5x to **23-24/79 (29-30%)**; under TWO-CLOSES **18/79 (23%)**;
under GRACE-1BAR (the least aggressive loosening) **8/79 (10%)**. This is the direct dollar cost of
"catching more whipsaws" — some fraction of the delayed stops are not whipsaws at all, and the
buffer just lets a real breakdown run further before the -50% floor finally catches it.

## Regime split (VIX)

BUF-0.25's effect is regime-dependent and the SAME concentration problem shows up as a
regime artifact, not a real edge:

| Variant | vix<15 (n=29) | vix 15-17 (n=39) | vix>17 (n=11) |
|---|---|---|---|
| BUF-0.25 | −$11 (−1,444, 1,703) | **+$5,557 (+779, 11,514)** — CI excludes zero | **−$1,044 (−1,777, −493)** — CI excludes zero |
| TWO-CLOSES | **−$1,402 (−1,960, −905)** — CI excludes zero | +$803 (−798, 2,881) | **−$1,031 (−1,778, −468)** — CI excludes zero |
| GRACE-1BAR | **−$825 (−1,523, −104)** — CI excludes zero | +$101 (−489, 731) | **+$453 (+82, 839)** — CI excludes zero |

The one regime cell with a clean positive CI (BUF-0.25, vix 15-17) IS the 08-04/08-11/08-13
cluster driving the top-3 concentration above — not an independent regime finding. Every other
regime cell that clears significance clears it in the **negative** direction. There is no
regime split here that survives the concentration disclosure as a standalone justification to ship.

## Per-arm split

No arm shows a clean, CI-excludes-zero positive result for any variant (full table in the JSON —
`variant_results.<id>.by_arm`). bold-2 and risky-3 lean positive on BUF-0.25/ATR (driven by the
same 08-04/08-13 cluster, present in both); safe-2 is flat-to-negative on every variant; safe-3 is
the most consistently negative on TWO-CLOSES (−$854, CI −1,382 to −429, excludes zero).

## Would this have blocked or hurt the named winning days (08-06, 08-13, 08-27, 08-28)?

**No exposure at all on 2 of the 4**: 2026-08-06 and 2026-08-28 have **zero** `structure_stop`
exits anywhere in the population — none of these 5 candidates touches those days in any way; they
cannot have blocked or hurt those wins under any variant.

2026-08-13 carries 5 structure_stop legs (the `SPY260813C00776000`/`P00776000` cluster) and
2026-08-27 carries 1 (`bold-2 SPY260827C00771000`) — both were themselves LOSING legs on days that
were net winners book-wide. Effect on just those legs, summed:

| Variant | 08-13 + 08-27 net Δ$ |
|---|--:|
| BUF-0.15 | −$162.50 |
| BUF-0.25 | **+$1,180.50** |
| BUF-ATR0.5x | **+$1,180.50** |
| TWO-CLOSES | −$197.50 |
| GRACE-1BAR | −$57.00 |

None of these deltas (max $1.2K either direction) is large relative to those days' overall
book-wide gains — no candidate would have flipped either winning day to a loss, and 2 of 5
candidates (the ones with a positive headline, for the reasons above already discounted) would
have made the losing legs on those specific winning days slightly LESS bad, not worse.

## Prior art

- **`structure-stop-zone-band` (CLOSED 2026-08-11)** —
  [`analysis/recommendations/prereg-structure-stop-zone-2026-08-11.json`](../../recommendations/prereg-structure-stop-zone-2026-08-11.json).
  Same family of question (a price band around `trigger_level`), CLOSED by its own G4: "only 3 of
  29 positions ever touched by any band cell" — too rare to validate, no forward trial licensed.
  This study reproduces the identical dead-frequency/concentration pattern independently, on a
  disjoint and more recent population (2026-07-13..08-27 here vs 2026-06-29..07-17 there).
- **`WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03`** —
  [`analysis/deep-research/WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03.md`](../WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03.md).
  Filed the same day. Documents that a full walker REPLAY of structure_stop disagrees with LIVE's
  own discrete/tick-gated poll on a correlated, arm-replicated subset of positions (11 signal-days
  covering 26/42 disagree rows) — a **replay fidelity** gap, distinct from this study's question.
  This study deliberately does **not** walk-replay structure_stop through
  `exit_manager_walk.py`; every "control" bar here is anchored directly off the REAL ledger's own
  `last_closed_5m_close` + `ts_et` (what LIVE actually used to fire), so it inherits none of that
  gap. The SAME correlated-across-arms recurrence pattern (one SPY-level event hitting 3-4 arms at
  once via the shared signal) shows up independently in this study's own top-3 concentration finding.
- **`ribbon_flipback_buffer_ab.py`** —
  [`backtest/tools/ribbon_flipback_buffer_ab.py`](../../../backtest/tools/ribbon_flipback_buffer_ab.py)
  / [`analysis/recommendations/ribbon-flipback-buffer-2026-08-08.md`](../../recommendations/ribbon-flipback-buffer-2026-08-08.md).
  Different exit stage (ribbon-flip-back, not structure_stop) but the source of this study's
  market-style-fill convention (bar close − $0.02 slippage) and confirm-closes framing; that study
  also concluded UNDERPOWERED (only 10/219 control replays ever fired a raw ribbon-flip exit at
  all) — a third independent instance of the same "the raw event is too rare in the live population
  to power a buffer study" pattern this study's own drop-best-day/concentration numbers reproduce
  for structure_stop specifically.

## Methodology and disclosed limitations

- **No look-ahead**: every candidate's fire decision at bar *i* uses only bars ≤ *i* (ATR uses only
  bars strictly before *i*); the counterfactual's forward option-bar scan is a MEASUREMENT
  (what would this delayed/avoided exit have realized), not information available to the live rule
  itself — consistent with "a live rule may only use information available at the entry tick."
- **Counterfactual exit premium** = cached 5-minute option-bar CLOSE minus $0.02 slippage at the
  variant's own fire bar, or the 15:50 ET time-stop close, or the −50% catastrophe-cap floor —
  whichever binds first scanning forward from the REAL stop bar. The "actual" baseline uses the
  identical convention (option bar close at the real stop bar, not the raw broker fill) so the
  reported quantity is a valid PAIRED delta — it is not a claim about either side's absolute dollar
  level.
- **Not modeled**: TP1 partial exits, chandelier trail, ribbon-flip-back. A delayed/avoided
  structure stop that production would, in full fidelity, have instead exited via a legitimate TP1
  or trail is credited here as riding to whichever of {catastrophe cap, 15:50 close} binds first —
  disclosed as two-sided (can overstate OR understate the buffer's benefit) rather than corrected,
  since a full-fidelity re-walk needs `exit_manager_walk.py` and inherits the exact live-poll-cadence
  gap `WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM` documents.
- **ATR multiplier (0.5×, 12-bar trailing 5m)** chosen a priori, not fitted to this study's dollar
  outcome; it happens to land close to BUF-0.25 in aggregate effect (informative: median trailing-hour
  SPY 5m ATR on these days is in the same $0.20-0.30 neighborhood as the fixed-dollar candidates).
- **n=79 is 17 trading days, several signal-days replicated 3-4x across arms** off the same shared
  signal — the naive per-position bootstrap CI in the results table overstates independent evidence;
  the drop-best-day and top-3-concentration numbers are reported specifically to correct for that.
- 10/89 matched events excluded for missing cached option bars; 4/93 raw events are TODAY
  (2026-09-03, in progress) and excluded because no forward bars exist yet — neither exclusion was
  chosen after seeing its effect on the aggregate.
- Every number above is UNVERIFIED against a live re-fill (this is a paper/analysis-only replay of
  cached bars, per this session's hard constraints — no broker or market-data calls were made).
