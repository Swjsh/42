# SAFE3-RISKY1-GATE-RETEST-EXTEND -- sample extension pass (2026-09-03)

**Queue item:** `SAFE3-RISKY1-GATE-RETEST-EXTEND` (automation/overnight/queue.md line 1291).
**Pre-reg:** `analysis/recommendations/safe3-risky1-gate-retest-preregistration.json`.
**Author of this pass:** report-only Sonnet worker, read-only against ledgers current through
2026-09-02 15:55 ET. No code/params/queue/STATUS edits made. ET verified via `et_clock.py`
at run time: `2026-09-03 04:50:14 Thursday EDT`.

**Tooling built:** `backtest/tools/gate_override_blocked_cohort.py` (extractor, read-only) +
`backtest/tests/test_gate_override_blocked_cohort_2026_09_03.py` (5/5 pass, synthetic fixtures
only -- does not touch live ledgers).

---

## 1. Gate-override reason strings (verified by grep against the fleet ledgers)

- `"gate: 1 triggers < 2"`
- `"gate: requires confluence/sequence"`

Source: `automation/state/fleet/safe-3/decisions.jsonl` and `.../risky-1/decisions.jsonl`,
field `reason` on `action: "HOLD"` rows.

## 2. Method

1. Pulled every gate-blocked `HOLD` tick for safe-3 and risky-1 (`reason` matching the two
   strings above) from **2026-07-16 to 2026-09-02** (07-16 = redesign date per the queue item).
2. Pulled every core-arm `ENTER_BEAR`/`ENTER_BULL` tick from `automation/state/core-decisions.jsonl`
   (`account: "safe"` -> arm `safe-2`, `account: "bold"` -> arm `bold-2`, per the CLAUDE.md
   account table) in the same window.
3. Matched a blocked tick to a core ENTER when: same date, same side (direction), core ENTER
   `ts_et` within +/-2 min of the blocked tick, **and same `setup_name`/`setup`**.
   - Strike could not be used as an independent filter: gate-blocked `HOLD` rows carry
     `strike: null` (the gate fires *before* strike selection) -- disclosed, not a silent gap.
   - **Setup-name matching was added after a verified false positive**: on 2026-08-04 09:56 ET,
     safe-3 was blocked on `VWAP_CONTINUATION` while the nearest core ENTER in the same
     2-minute/same-direction window was `BULLISH_RECLAIM_RIDE_THE_RIBBON` -- a different
     pattern that happened to fire in the same window. Without the setup filter this and
     similar rows would count as false comparable fills. With it, **all matches on the
     `"gate: requires confluence/sequence"` reason dropped to zero** (n_setup_mismatch_near_misses
     = 31) -- every apparent confluence-gate comparable fill in the loose pass was a coincidental
     unrelated setup, not a real one. All 32 surviving matches are on `"gate: 1 triggers < 2"`,
     setup `BEARISH_REJECTION_RIDE_THE_RIBBON`, side `P`.
4. Each core ENTER was resolved to the single nearest `trades-enriched.jsonl` row by
   `entry_ts_et` (tolerance 5 min) -- not "all rows for that symbol that day" (0DTE strikes get
   re-entered same-day after stop-outs; naive symbol-matching double- and quadruple-counted
   before this fix).
5. Deduped on the **resolved trade identity** (`fifo_trip_ids`), not the raw core-decisions log
   line -- the engine occasionally logs two near-duplicate ENTER verdicts <=1 tick apart for
   what resolves to one fill.
6. Collapsed a blocked arm's own gate ticks into the SAME underlying missed-trade event when
   both safe-3 and risky-1 blocked on the identical core fill (near-total overlap: risky-1's 22
   matches are a strict subset of safe-3's 32) -- counted once, matching the prior n=5 pass's
   own "one new comparable fill" event-counting, not per-arm-attributed duplication.

## 3. n found vs. the prior 5

| | n | wins | losses | ties | sum | mean |
|---|---|---|---|---|---|---|
| **Prior (07-16 + 07-17 audit)** | 5 | 1 | 4 | 0 | **+$148** | +$29.60 |
| **This pass, distinct comparable events, setup-matched (PRIMARY)** | **32** | 12 | 19 | 1 | **-$59** | **-$1.84** |
| This pass, loose (time+direction only, no setup filter -- shown for contrast, NOT primary) | 36 | 16 | 19 | 1 | +$1,974 | +$54.83 |

The setup-name filter is the material finding here: it flips the sign of the extended sample
(+$1,974 loose vs. -$59 correct) and eliminates every confluence-gate comparable fill. The
**-$59 / n=32 figure is the one that should replace the prior +$148 / n=5 headline.**

Per-blocked-arm attribution (same 32 underlying events, arm view): safe-3 n=32 (sum -$59),
risky-1 n=22 (a subset of safe-3's 32; own sum -$233) -- risky-1's `full_send` gate_override
carries the identical `min_triggers`/`require_confluence_or_sequence` block as safe-3, so it is
blocked on nearly every signal safe-3 is.

Distinct trading sessions represented: 14 of 36 sessions in the 07-16..09-02 window carried at
least one comparable event.

## 4. P&L table with CI (primary, n=32, setup-matched)

- **Sum:** -$59.00. **Mean:** -$1.84/event.
- **Drop-top-1** (remove best winner, +$375 on 08-06): n=31, sum=-$434, mean=-$14.00.
- **Drop-bottom-1** (remove worst loser, -$270 on 08-28): n=31, sum=+$211, mean=+$6.81.
- **Session-clustered bootstrap 95% CI on the mean** (resample sessions with replacement, all
  events for a resampled session move together; seed=1337, n=2000 resamples):
  **[-$70.82, +$64.43]**. 48.1% of resamples had a positive mean -- indistinguishable from zero.
- Full daily detail (session -> event P&Ls): 07-17 [191] · 07-21 [0] · 08-05 [-255] · 08-06
  [375] · 08-11 [-63,-145,-145,297] · 08-12 [-6,15,-35,-15] · 08-13 [-69,-200] · 08-14
  [-18,-90,-160] · 08-17 [360] · 08-18 [82,80] · 08-20 [191,90,174,85,-27] · 08-21 [-189,-175] ·
  08-28 [-270,-215] · 09-01 [338,-140,-120].

## 5. Sizing/exit disclosure (accounts.json, this is a COUNTERFACTUAL not a re-simulation)

The core-arm fill is used as-is for each blocked event; this assumes the tight arm would have
sized and exited identically to the core arm, which is **not what the arms' own config says**:

- **safe-3**: `params_patch.exit_patch = {stop_mode: structure, profit_lock_mode: trailing}`,
  `strike_tier_table: bold_core` (ATM). safe-2 (core, `safe` account) runs the standard v15.3
  chart-stop-primary exit doctrine with no such patch.
- **risky-1**: `params_patch.exit_patch = {tp1_premium_pct: 0.5, stop_mode: structure}`,
  `strike_tier_table: bold_core` (ATM). bold-2 (core, `bold` account) has **no** params_patch
  and, per CLAUDE.md's per-tier strike table, trades **OTM-2** at this equity tier -- a
  materially different strike selection than risky-1's ATM `bold_core` table. Every risky-1
  comparable event whose counterfactual is a bold-2 fill (13 of 22) carries this strike-tier
  mismatch on top of the exit-rule mismatch.
- All four arms share `starting_equity: $5,000` -- no equity-scale mismatch.
- Net: the P&L numbers above are the best available real-fill counterfactual, but are **not**
  a clean "gate on vs. gate off, everything else equal" comparison, particularly for risky-1 vs
  bold-2.

## 6. Reachability sentence

Under the cohort's own original event-counting definition (one row per distinct comparable
blocked-vs-filled signal, matching how the prior n=5 was counted -- NOT the pre-reg's
2026-09-02 `adjudicated_2026_09_02` reinterpretation as "n_days=26/30 scored trading days",
which is a different denominator), **the n>=30 floor is already reached: n=32 as of
2026-09-02.** At the observed rate (32 events / 36 trading sessions in the 07-16..09-02
window, clustered on 14 active sessions), no further waiting is needed to hit the floor under
this definition -- it has been crossed. Reaching the floor does **not** flip the verdict: at
n=32 the pass_bar's own `net_pnl positive` condition **fails** (-$59, CI spans zero). Whether
the pre-reg's "n_days=26/30" tracker (a different, narrower metric than what this task was
asked to extend) should be reconciled to this event-based n is a labeling question for whoever
owns that file next -- not resolved here, and not this report's call to make.

## 7. What this does NOT recommend

No gate loosening is recommended by this evidence. The mean is statistically indistinguishable
from zero (CI spans zero, ~48% of bootstrap resamples positive), drop-bottom-1 flips positive
and drop-top-1 goes further negative (not sub-window stable), and the counterfactual carries
disclosed strike/exit mismatches (section 5) that could move the true number either way. This
matches the pre-reg's own instruction: reaching an accrual floor is not itself a ship signal.

## 8. Unverified / open items

- **Not verified against `automation/state/pnl-statement.json`** (the pre-reg's own stated
  authoritative source for per-leg P&L, favored over trades.csv/decisions.jsonl quoted premium)
  -- this pass used `analysis/trades-enriched.jsonl` per the task's explicit instruction, which
  is a downstream-enriched build of the same fills; the two should reconcile but that
  reconciliation was not independently re-checked here.
- **452 blocked ticks (safe-3+risky-1 combined, pre-setup-filter) had no core-arm match at all**
  within the +/-2min/same-side/same-setup window -- not audited individually; some are
  legitimately "core arms also didn't trade this," others may be match-window misses (a core
  ENTER slightly more than 2 min from the blocked tick). Not itemized in this report.
- **434 core-ENTER-matched events had no resolvable trades-enriched fill** within 5 min
  tolerance (includes `PLACE_FAIL`/`RISK_DENY_PDT`/`NOT_FLAT` core-side outcomes where the core
  arm itself didn't get a real fill either) -- excluded from the cohort per the pre-reg's own
  exclusion rule ("no comparable fill exists"), consistent with how risky-3's own downstream
  blocks were excluded in the original n=5 pass.
- The reconciliation between this report's event-based n and the pre-reg's `adjudicated_2026_09_02`
  day-scored n is flagged, not resolved -- outside this task's write scope (pre-reg file not
  edited).
