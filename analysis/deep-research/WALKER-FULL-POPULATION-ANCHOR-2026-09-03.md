# WALKER-FULL-POPULATION-ANCHOR -- 2026-09-03

RESEARCH -- decides nothing, arms nothing, ships nothing. Filed off
WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION's decision to stop tuning against the 43/41-row PDT
subset (too small, premium_stop-heavy, loss-skewed to serve as a magnitude-fidelity anchor) and
instead re-anchor `walker_magnitude_fidelity`'s criterion on the full engine-attributed real-fill
population. Built by `backtest/tools/walker_full_population_anchor.py`, which reuses
`pdt_blocked_counterfactual`'s adapter functions (`canonical_shape`, `anchor_trigger_level`,
`_load_anchor_bars`, `_price_via_walker`/`_walk_via_exit_manager`, `spy_by_day`,
`harness_validation` itself via a monkeypatch of `load_anchor_sample`) and
`whole_engine_null._core_account_for_arm`/`build_ribbon_tick_df` -- no re-implementation of the
walking logic.

## PRE-REGISTRATION (written before any number below was read)

**Criterion (UNCHANGED from `backtest/lib/walker_magnitude_fidelity.py`):**
`|aggregate_ratio - 1| <= 0.40` AND `median_abs_error_dollars <= $40` AND `n >= 20`. PASS only
if all three hold; FAIL if n is sufficient but either dollar condition fails; INSUFFICIENT if
n < 20 or a ratio/median could not be computed.

**Population:** every row in `analysis/trades-enriched.jsonl` with `attribution == "engine"`
(the exact filter `go_live_gate.py`'s `statistical_criterion`/reconciliation paths use),
`arm` in `{safe-2, bold-2, safe-3, risky-1}` (go-live gate's `ACTIVE_ARMS`, minus risky-3/safe-1
which are not gate-scored), `date` in `[2026-07-08, latest session in the file]`, and
`pnl_dollars`/`entry_px`/`qty` all present (the same completeness filter
`pdt_blocked_counterfactual.load_anchor_sample` already applies). safe-3/risky-1 rows are
included only via this same row-level filter -- most of their rows DO carry a resolvable
`trigger_level` (verified before running: safe-3 44/49, risky-1 49/69 engine-attributed rows in
the window have `trigger_level is not None`); the ones that don't fall back to premium mode via
`anchor_trigger_level`'s existing null-trigger_level convention, identically to how the 43-row
PDT anchor already handles safe-2/bold-2 rows without a trigger level. No row is excluded for
lacking a trigger level.

**Bars:** `--bars 1min` via `_option_bars_1min_cache.fetch_1min_cached`, single-reader,
disk-cached under `backtest/data/highres/`. All distinct (symbol, date) contracts in this
population were checked against that cache BEFORE this script ran (see Cache status below) --
if any were missing, a bounded live REST fetch would run this session alone; the actual result
is reported in "Skipped contracts" below, never fabricated.

**Settings:** `exit_manager` walker's own default `exit_slippage` (0.01, applied only to the 3
market-style stages) and zero -- same two settings the prior ablation used, for direct
comparability. "live" slippage stays SKIPPED for the same reason the ablation already
disclosed (`analysis/pain-ledger/latency.json` carries no dollar-denominated exit-slippage
field).

**Table shape (filled in below, not before running):**
1. Three-anchor summary table (full pooled population / V9 121-row / PDT-43 subset) x
   (default slippage / zero slippage), columns: n, sign_agreement, aggregate_ratio,
   median_abs_error_dollars, verdict. V9's zero-slippage cell is out of scope for this item
   (V9 continuity is reported at default slippage only, per the task).
2. Per-arm table (full population, both slippage settings): n, sign_agreement,
   aggregate_ratio, median_abs_error_dollars, verdict.
3. Per-recorded-stage table (full population, both slippage settings): n, sign_agreement,
   aggregate_ratio, median_abs_error_dollars.
4. Skipped-contract list (bars fetch failures) and skipped-row list (walker errors), with
   reasons -- never silently dropped.
5. One-sentence conclusion: does the pooled full population clear the criterion at either
   slippage setting, and if not, which stage bucket carries the residual.

**Decision rule (stated before running):** if the pooled full population clears
`|ratio-1|<=0.40` AND `median<=$40` at either slippage setting, the PDT counterfactual and the
three outstanding prereg RUNs may migrate onto `exit_manager_walk` at 1-min bars
(WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK unblocks). If it does not clear at either
setting, the residual is named per stage bucket before any further tuning is attempted --
tuning against a still-unproven anchor is exactly the mistake the prior three queue items
(WALKER-PDT-ANCHOR-FIDELITY-INPUTS, WALKER-STAGE-DISAGREE-RESIDUAL,
WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION) already spent three rounds correcting against too
small an anchor.

---

## RESULTS (run 04:5x ET 2026-09-03, Sonnet)

Population: 231 engine-attributed rows, arms `{safe-2:74, bold-2:39, risky-1:69, safe-3:49}`,
window 2026-07-08..2026-09-02 (latest session). All 96 distinct (symbol,date) 1-min contracts
were already disk-cached -- **zero new OPRA fetches, $0**, single-reader constraint moot this
run. 8 rows unpriced (`skipped_no_bars`, all 2026-08-05 -- see Skipped section) -> n=223 priced.

PDT-43 subset re-run through this SAME script (same `harness_validation` call, same
monkeypatch mechanism) reproduces the published WALKER-EXIT-SLIPPAGE-ABLATION numbers
**exactly** (2.0128/1.7163, n=41, sign 97.56%, median $15.0 both settings) -- confirms the
monkeypatch-reuse approach is byte-identical to the prior harness, not a parallel
reimplementation that could have drifted.

### Three-anchor table

| Anchor | Setting | n | sign_agreement | aggregate_ratio | median_abs_err | verdict |
|---|---|---|---|---|---|---|
| **Full population** | default | 223 | 88.34% | **0.6896** | $16.00 | **PASS** |
| **Full population** | zero | 223 | 89.24% | **0.9074** | $15.00 | **PASS** |
| V9 (121-row, continuity) | default | 121 | 89.26% | 0.6452 | $15.00 | PASS |
| PDT-43 subset (this run) | default | 41 | 97.56% | 2.0128 | $15.00 | FAIL |
| PDT-43 subset (this run) | zero | 41 | 97.56% | 1.7163 | $15.00 | FAIL |

**The pooled full population clears the criterion at BOTH slippage settings.** Read no further
than this table and the natural conclusion is "migrate." That conclusion is WRONG on its own
terms -- see the per-arm table immediately below, which this queue item also asked for and
which the pooled number alone would have hidden.

### Per-arm table (full population, default slippage; zero-slippage in JSON, same pattern)

| Arm | n | sign_agreement | aggregate_ratio | actual $ | replay $ | median_abs_err | verdict |
|---|---|---|---|---|---|---|---|
| safe-2 | 72 | 95.83% | **0.9634** | 400.00 | 385.35 | $15.00 | **PASS** |
| bold-2 | 39 | 92.31% | **6.4361** | -155.00 | -997.60 | $15.00 | **FAIL** |
| risky-1 | 63 | 80.95% | **1.7195** | 1,351.00 | 2,323.10 | $22.50 | **FAIL** |
| safe-3 | 49 | 83.67% | **-0.1241** | 750.00 | -93.10 | $14.90 | **FAIL** |

**3 of 4 arms individually FAIL the criterion** -- safe-3's replay even flips SIGN net (actual
+$750, replay -$93.10). **The pooled PASS is arithmetic cancellation, not per-arm fidelity**:
bold-2 over-replays losses by ~$843 (actual -$155 -> replay -$998), risky-1 over-replays gains
by ~$972 (actual $1,351 -> replay $2,323), safe-3 under-replays by ~$843 (actual $750 -> replay
-$93) -- these three roughly cancel in the sum (total error -$728 on a $2,346 actual base),
leaving safe-2 (the only genuinely well-replayed arm, and the only arm the original PDT-43
anchor was ever drawn half from) to anchor the pooled ratio near 1.0. Winners/losers split
pooled (0.906 / 0.9375) looks clean specifically because the four arms' biases partially net
out across BOTH the win and loss buckets, not because any given trade replays faithfully.

### Per-recorded-stage table (full population, default slippage)

| Recorded stage | n | sign_agreement | aggregate_ratio | median_abs_err | verdict |
|---|---|---|---|---|---|
| structure_stop | 82 | 92.68% | **1.0178** | $10.00 | **PASS** |
| premium_stop | 72 | 90.28% | **0.9597** | $19.20 | **PASS** |
| tp1+trail | 44 | 86.36% | 0.94 | $76.80 | **FAIL** (median too high) |
| ribbon_flip | 17 | 70.59% | -2.4177 | $20.00 | INSUFFICIENT (n<20, sign-flipped) |
| time_stop | 4 | 75.00% | -3.0 | $49.50 | INSUFFICIENT (n<20) |
| other_rare (UNKNOWN, premium_stop+ribbon_flip, runner_target+tp1) | 4 | 75.00% | 2.9147 | $57.00 | INSUFFICIENT (n<20) |

The two largest, best-attested stage buckets (structure_stop, premium_stop -- 154/223 = 69% of
the population) each individually PASS cleanly. `tp1+trail`'s median error ($76.80, over the
$40 bar) is the one large-n bucket that fails on its own.

### Stage decomposition (full population, default slippage)

Stage AGREEMENT (walked stage == recorded stage): n=181/223 (81.2%), median abs err $13.50.
Stage DISAGREEMENT: n=42/223 (18.8%), median abs err $86.25 -- **56.0% of total absolute error
concentrated in 18.8% of rows.** This is the SAME mechanism WALKER-STAGE-DISAGREE-RESIDUAL
already diagnosed on the 43-row anchor (structure_stop vs premium_stop/tp1+trail ordering at
coarse-bar cadence), now confirmed at 1-min resolution and larger n -- so it is not a
bar-cadence artifact this time, it recurs even on the finer bar series.

**Correlated, not independent:** row-level inspection shows the SAME (symbol, date) events
recur across bold-2/risky-1/safe-3 on the SAME days (e.g. `SPY260819C00770000` 2026-08-19 and
`SPY260813C00777000` 2026-08-13 each appear as a top-8 error row in TWO OR THREE different
arms) -- because every fleet arm runs the identical signal on the identical trigger, just at
different position sizing (per accounts.json: "AN ACCOUNT IS NOT A STRATEGY"). The 42
disagreeing rows are therefore closer to a handful of distinct MISFIRE EVENTS replicated
across arms than 42 independent draws -- the per-arm n's overstate independent evidence for
bold-2/risky-1/safe-3's poor ratios exactly as much as they understate it for the pooled
sample size.

### Skipped contracts (bars fetch failures, `skipped_no_bars`)

8 rows, all dated 2026-08-05, all `_load_anchor_bars` returning empty/None for that day's 1-min
cache (pre-existing cache miss/empty file, not a fetch attempted-and-failed this run since the
cache pre-check found 96/96 contracts on disk already -- these 5 distinct symbols' 2026-08-05
cache entries exist but are apparently empty for the queried date, most likely a genuine
no-trading-activity/holiday-adjacent gap in that day's 1-min OPRA pull done in a prior session;
not re-investigated here, scope is anchor-building not cache repair):
`SPY260805C00776000`(x5, risky-1), `SPY260805P00772000`(x2: risky-1, safe-2),
`SPY260805C00777000`(x1, safe-2). No row was fabricated or estimated in place of these.

### Conclusion (one sentence, as pre-registered)

**The pooled full engine-attributed population passes the aggregate `walker_magnitude_fidelity`
criterion at both slippage settings (0.6896/$16 default, 0.9074/$15 zero), but that pass is
arithmetic cancellation across arms whose individual ratios diverge sharply (bold-2 6.44,
risky-1 1.72, safe-3 sign-flipped at -0.12, only safe-2 0.96 genuinely passing) -- the residual
mechanism is stage-disagreement (structure_stop firing where the broker recorded
premium_stop/tp1+trail, 18.8% of rows carrying 56% of total absolute error, correlated across
arms trading the identical signal) -- so `exit_manager_walk` should NOT be trusted as a
faithful per-arm dollar replay off this pooled number alone, even though it clears the letter
of the criterion.**

### What WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK should do next

Do not migrate on the pooled PASS alone. Two independently actionable next steps, named not
attempted here (scope was anchor-building):
1. **Fix the stage-disagreement mechanism** (structure_stop-vs-premium_stop/tp1 mis-ordering,
   18.8% of rows / 56% of abs error) -- same root question WALKER-STAGE-DISAGREE-RESIDUAL
   raised for the 5-min anchor, now shown to persist at 1-min too, so it is not purely a
   bar-cadence artifact; needs its own differential (is `plan_exit_actions`' structure-before-
   premium check firing on a bar the live poll never would have, or is trigger_level/ribbon
   input itself wrong for these specific rows).
2. **Score any future migration decision per-arm, never pooled-only** -- this run's own
   per-arm table is the concrete argument: a pooled anchor across arms whose replay biases have
   opposite sign will pass the letter of `walker_magnitude_fidelity` while being unreliable for
   3 of 4 individual arms. If a per-arm criterion is adopted, only safe-2 (0.9634, PASS) clears
   today; bold-2/risky-1/safe-3 do not.

status: **partial** -- the pooled anchor was built and it DOES clear the letter of the
criterion, but the per-arm/per-stage decomposition this item also asked for shows that pass is
not trustworthy as a migration gate on its own. WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK
stays blocked pending the two follow-ups above, not because the anchor failed outright but
because it passed in a way that should not be acted on unexamined.
