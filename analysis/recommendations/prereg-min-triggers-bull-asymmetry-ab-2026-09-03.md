# PREREG — MIN-TRIGGERS-BULL-ASYMMETRY-AB

**Status:** FROZEN PRE-REGISTRATION — NOT YET EXECUTED. Document-only fire; no code, params,
queue.md, or STATUS.md touched by this file. Frozen 2026-09-03 04:59 ET (`et_clock.py`, quoted
below: `2026-09-03 04:59:32 Thursday EDT market_hours=False`).

**Source queue item (`automation/overnight/queue.md:451-460`, verbatim):**
> `MIN-TRIGGERS-BULL-ASYMMETRY-AB (MED) :: The 2026-07-22 mirror-parity audit found a live,
> armed, non-cited asymmetry: filter_10_min_triggers_bull=2 vs bear=1 (orchestrator.py:778-779)
> -- bulls need DOUBLE the confirming triggers. NOT loosened tonight and deliberately so: real
> bull fills under current config are n=24 WR 0% -$885 (bull-requalification-2026-07-22.json),
> so easing bull entry admission is contraindicated by the same data. But the knob has no
> current-config provenance either way. PRE-REG A/B when bull evidence accrues or regime turns:
> does min_triggers_bull=1 admit winners or just more of the losing population? Replay at
> ATM+SS-B through exit_manager_walk, standing 4-condition bar.`

---

## 0. CORRECTIONS OF RECORD (verified this session — load-bearing, read before §1)

The task brief that spawned this document cited two facts from the 09-03 01:17 ET queue note
(`queue.md:121`, Fable). Both were checked against the underlying instruments and **do not
hold as stated**. Neither correction changes the queue item's own text above; both change how
its "when bull evidence accrues or regime turns" trigger condition must be read.

**(a) "bull sole-[10]" is NOT `filter_10_min_triggers_bull`.** The task brief read the
sole-blocker miner's `filter-10-bull-sole` cell as evidence about the trigger-count knob. Traced
through the code: `backtest/tools/postfix_gate_costing.py`'s `SOLE_BLOCKER_FLAGSHIPS` dict
(`gate_expiry_check.py:586-588`) defines `"filter-10-bull-sole": ("bull", 10)` with the comment
`# buyer pressure -- bull-f10-buyer-pressure-prereg-2026-08-04.json`. That prereg
(`analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json`) confirms filter 10
on the bull door is the **buyer-pressure volume multiplier** (`f10_vol_mult_bull`, default
0.7, params key absent on both accounts today) — a volume-bar gate, unrelated to trigger count.
The bull/bear blocker-index-to-name map in
`backtest/tools/frequency_ceiling_cascade_2026_08_03.py:156,164` makes the actual numbering
explicit: bear `10: "min_triggers_bear"`, bull `10: "buyer_pressure_bar"`,
**bull `11: "min_triggers_bull_or_no_level_tied"`** — bull's checklist has one extra upstream
gate (`filter_10_level_tied_required`) ahead of min_triggers, shifting its index by one relative
to bear's. The 39-distinct-episode / n_cost_money_distinct=14 / n_saved_money_distinct=25
figure (`automation/state/gate-registry-status.json` → `filter-10-bull-sole`, rolling window
`2026-08-05..2026-09-01`, 20 trading days) is real and RED, but it is evidence about the
buyer-pressure gate, not about `min_triggers_bull`. It is **out of scope for this A/B** and is
not used as a population below.

The closer analog is `bull_filter11_{safe,bold}` in the same miner (`gate-registry-status.json`
`sole_blocker_miner.cells_rolling_window`, same 20-day window): **n_events=33,
episodes_distinct=33, n_cost_money_distinct=22, n_saved_money_distinct=11** per account cell
(bold-cell is byte-identical to the safe-cell — expected per the miner's own
GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT doc, `gate_expiry_check.py:699-708`: safe and bold
evaluate the identical bull/bear checklist against the same market data, so a refused moment
produces one HOLD row per account). **This cohort is NOT a clean min_triggers_bull isolation
either** — filter 11 is a combined `min_triggers_bull OR no_level_tied` blocker id, so an
unknown fraction of the 33 refused episodes were refused by the level-tied requirement, not by
trigger count, and the raw decision rows would need to be re-split on the underlying boolean to
isolate the trigger-count-only subset. This is the TREATMENT-adjacent population defined in §2,
with that entanglement disclosed as an open item the runner must resolve before trusting cohort
size.

**(b) The regime-turn numbers are stale relative to the file they cite.** The queue note quotes
"core recency GREEN_CONCENTRATED n=38 +$49.55/tr." Read fresh this session,
`automation/state/core-strategy-recency.json` (`run_date: 2026-09-02`, window
2026-07-30..2026-09-02, 25 trading days) currently shows:

```
headline: "core strategy recency: bear RED_CONCENTRATED n=31, bull GREEN_CONCENTRATED n=42 (floor 10, 25d to 2026-09-02)"
bull.n = 42, bull.exp_per_trade = 41.48, bull.verdict = "GREEN_CONCENTRATED"
bull.reason = "NOT ACTIONABLE (concentration-carried): real-fills exp +$41.48/tr, n=42 >= floor
  10, but drop-top3=$67.0, drop-best2-days=$-435.0 -- does NOT survive (sign flips or zeroes
  out) -- this positive mean is NOT a broad edge; treat as unproven until a fuller sample
  supports it.; replay supplement (Safe shape, engine-sim, DISCLOSED not blended): n=3
  exp=$-131.33/tr recent"
```

n=42/+$41.48 vs the quoted n=38/+$49.55 is a same-file discrepancy (the file regenerates daily;
the queue note was written 01:17 ET, this read is 04:59 ET the same calendar night — a
regeneration between those timestamps is the likely mechanism, not independently verified here).
**The number that matters is not the drift, it is the label the queue note dropped:**
`GREEN_CONCENTRATED` on this exact metric is explicitly documented as a self-reversing verdict
class. `markdown/research/BACKTESTING-PLAYBOOK.md` §4.3 names this precise instrument as a prior
false positive: *"`core_strategy_recency.py::direction_verdict` (BULL GREEN stamped from 2,767%
of net coming from 2 days — triggered a 13-agent investigation into a mechanism that didn't
exist)."* The current read's own `drop_best2_days=-$435.0` (2 of 12 days removed flips the
25-day net from +$1,742 to a loss) and `best_day_share_pct=65.5%` on 2026-08-04 alone are the
same failure shape recurring. **Conclusion: "the bull side is now the winner" is not
established.** What is established is that bull real-fills recency is GREEN on the raw mean and
explicitly self-flagged NOT ACTIONABLE on concentration — i.e. "regime turned" is unverified;
"evidence is accruing and needs the population study this queue item already asks for" is the
honest reading, and is the one this prereg is frozen against.

**(c) The bull/bear asymmetry is Safe-only, not fleet-wide — verified directly.**
`automation/state/params.json:60-62` (feeds safe-2 core + safe-3 fleet, per that file's own
inheritance doc pattern): `filter_10_min_triggers_bear: 1`, `filter_10_min_triggers_bull: 2`,
`filter_10_level_tied_required: true` — asymmetric, matches the queue item's citation.
`automation/state/aggressive/params.json:49-50` (feeds bold-2 core + risky-1 fleet, per that
file's own `_doc` header: "Safe strategy params: automation/state/params.json"):
`filter_10_min_triggers_bear: 1`, `filter_10_min_triggers_bull: 1` — **already symmetric,
already at the value this A/B asks whether to ship.** `orchestrator.py:790-793`'s
`bull_min_triggers = min_triggers_bull if min_triggers_bull is not None else max(2, min_triggers)`
is the backtest-path fallback default (2 when the key is absent); the live path
(`setup/scripts/heartbeat_core.py:994-995`) reads
`account_params.get("filter_10_min_triggers_bull", 2)` directly off each account's own params
file, so Bold's explicit `1` overrides that same fallback. **This means Bold has been running
the treatment condition live since whenever this key was set** (git blame not run this session
— flagged as an open item for the runner, §5) **and its real fills are a second, cleaner
evidence source this A/B should pull before any shadow ledger accrues from scratch.** This
correction changes §5's forward-shadow requirement below: part of the "forward" evidence may
already exist retroactively on bold-2/risky-1.

---

## 1. Hypothesis

**Question (unchanged from the queue item):** does `min_triggers_bull=1` admit winners, or
just more of the losing population that `bull-requalification-2026-07-22.json` already measured
at n=24, WR 0%, -$885 (base_trade_count=42, block_elite_bull added-cohort:
`n=9, win_rate=0.0, total_pnl=-1720.5, expectancy_per_trade=-191.17`, both halves of the sample
negative — `first_half_pnl=-529.0, second_half_pnl=-1191.5`)?

**Hypothesis:** relaxing bull's trigger-count floor from 2 to 1 (matching bear, matching Bold's
already-live config) admits a cohort whose full-population expectancy is non-negative and whose
quality is not explained by the same failure mode the 2026-07-22 study found (elite-tagged,
0% WR, both-halves-negative).

**Null / refutation (pre-committed):** if the added cohort (bull entries admitted at
`min_triggers_bull=1` that are refused at `=2`) reproduces the 2026-07-22 shape — 0% or
near-0% WR, negative in both the first and second half of the window, concentrated in the same
"elite bull" tag — the knob stays at 2 and this prereg is marked KILL, not re-run on a larger
sample hoping for a different sign.

---

## 2. Populations

**TREATMENT (backtest-side, entanglement disclosed):** `bull_filter11_{safe,bold}` sole-blocked
episodes from `sole_blocker_miner`, `automation/state/gate-registry-status.json`. Two windows
per the miner's own schema:
- Rolling 20 trading days (2026-08-05..2026-09-01): n=33 distinct episodes, 22 read
  cost-money / 11 read saved-money via the day's own P1 win (NOT_REPLAYED directional proxy).
- Last session only (2026-09-02): 0 events in this cell (not present in `cells_last_session`
  as read — filter 11 did not fire sole-blocked on 09-02; filters 5/6/10/11(other doors) did).
- **Pre-runner requirement:** re-derive this cohort split by the underlying boolean
  (`min_triggers_bull < 2` alone vs `level_tied_required` alone vs both) from the raw
  `bull_blockers`-tagged HOLD rows in `automation/state/core-decisions.jsonl` (or wherever
  `CORE_DECISIONS` resolves — not independently located this session) — the runner may NOT
  treat the 33 as a pure trigger-count population without this split.

**TREATMENT (live-side, NEW per §0c):** bold-2 and risky-1 real bull fills since
`filter_10_min_triggers_bull=1` went live on `aggressive/params.json` (effective date not
verified this session — runner's first job, via `git log -p -S filter_10_min_triggers_bull --
automation/state/aggressive/params.json`). This is retroactive live evidence, not a shadow
ledger that needs to accrue — potentially the fastest path to an answer and must be checked
before building anything new.

**CONTROL:** bull entries the engine actually took on safe-2/safe-3 under the live
`min_triggers_bull=2` config over the same calendar windows as both treatment slices above —
the existing `core_strategy_bull` real-fills cohort (`core-strategy-recency.json`, n=42,
2026-07-30..2026-09-02) is the ready-made control population; the historical
`bull-requalification-2026-07-22.json` base cohort (n=42, window 2026-05-21..2026-07-17,
strike_offset=0, `SS-B`-shaped exit: `premium_stop_pct=-0.2, tp1_premium_pct=1.0,
tp1_qty_fraction=0.667, profit_lock_mode=trailing, runner_target_pct=99.0, trail_pct=0.15,
profit_lock_arm_pct=0.05, stop_mode=structure, catastrophe_stop_pct=-0.5,
profit_lock_arm_scope=post_tp1`) is the control's historical-replay anchor.

**Replay instrument, sign-only caveat (mandatory disclosure, not optional):** any backtest-side
replay of the treatment cohort MUST go through `exit_manager_walk` at ATM + the SS-B exit shape
above per the queue item's own instruction. Per
`analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.{md,json}` (pooled 223-row
full-engine anchor, `backtest/tools/walker_full_population_anchor.py`, 20 plumbing tests, $0):
the walker's **pooled** magnitude read (default-slippage ratio 0.690, median $16, sign 88%
PASS) is **cancellation, not fidelity** — the per-arm breakdown is safe-2 **0.963 PASS**, bold-2
**6.44 FAIL**, risky-1 **1.72 FAIL**, safe-3 **-0.12 FAIL (sign-flipped: actual +$750, replay
-$93)**. The decision on file (queue.md:2474, Fable) is: *"the magnitude criterion is scored PER
ARM from now on; a pooled number is disclosure only."* Bull's core arms are safe-2 (PASSES
magnitude) and bold-2 (FAILS magnitude, ratio 6.44). **Any dollar figure this A/B's replay
produces on bold-2-attributable rows is SIGN-ONLY — direction (cost-money vs saved-money) may
be trusted, magnitude may not**, until `WALKER-CONSUMERS` unblocks (currently blocked pending
`WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM`, filed 2026-09-03 04:43 ET, root cause: 42/223 rows
where the replay fires `structure_stop` but the broker recorded `premium_stop`/`tp1+trail`,
carrying 56% of the pooled dollar error). Safe-2-attributable replay rows may be read for
magnitude with normal caution; bold-2/risky-1/safe-3-attributable rows may not.

---

## 3. Standing bar (unchanged shape, playbook §4.1/§4.5/§4.6, plus the two additions below)

All required, on the added cohort (treatment minus control overlap):
1. **OOS positive** — added-cohort P&L > 0 out-of-sample.
2. **WF >= 0.70** — `test_pnl_per_month / train_pnl_per_month >= 0.5` per playbook §4.6's
   walk-forward split, or an explicit disclosed-null per the standing WF-gate escape hatch.
3. **Sub-window stable** (playbook §4.5) — window-scheme choice is itself a PREREG decision,
   frozen here, not revised after data is seen. Given the added-cohort's expected size (33
   backtest-side, unknown live-side n until git-blame dates the config change) and bull's
   overall fire rate, **this A/B pre-registers EQUAL-CHANGED-TRADE-COUNT buckets**
   (`backtest/lib/canonical_battery.py::equal_count_buckets`, `n_buckets=4`) rather than fixed
   calendar windows — the added-cohort's changed-trade fraction is unknown but the base
   population (n=42 over 25 days, or n=9 in the 2026-07-22 elite-bull study) is well below the
   33%-of-population threshold playbook §4.5 sets for calendar windows to be safe from the
   starvation failure mode it documents (worked example: `tp1-r50-readjudication-2026-08-23.json`).
4. **Anchor no-regression** (playbook §4.1) — the existing n=42 core bull control cohort must
   not degrade when re-run under the treatment config.
5. **Concentration term (added, playbook §4.3, directly motivated by §0b above)** — the added
   cohort must clear `top5_pct <= 200%` AND must NOT be predominantly carried by
   `drop_best2_days` the way the current core-strategy-recency read is
   (`drop_best2_days=-$435.0` on the base cohort this A/B extends). A verdict that only survives
   because of 1-2 days does not pass, full stop — this is the exact failure this prereg's own
   §0b correction exists to prevent recurring.
6. **Sign-only disclosure (added, per §2 above)** — any walker-replayed dollar figure
   attributable to bold-2, risky-1, or safe-3 rows is reported as SIGN ONLY (cost-money /
   saved-money direction) with magnitude explicitly labeled UNRELIABLE until
   `WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM` closes and `WALKER-CONSUMERS` unblocks. Safe-2
   rows may report magnitude normally (arm-level PASS, ratio 0.963).

**Decision rule:** SHIP requires all 6. Partial pass (e.g., OOS positive but fails
concentration) is NOT a ship — it re-files as WATCH with the specific failing gate named, per
playbook's existing verdict vocabulary, never a silent downgrade to "looks promising."

---

## 4. Pre-committed prediction and refutation line

**Prediction:** the added cohort (both the backtest sole-[11] population, split to isolate
trigger-count-only refusals, and the bold-2/risky-1 live retroactive cohort) reproduces the
2026-07-22 elite-bull shape closely enough to fail gate 1 (OOS positive) outright — because the
mechanism that produced that -$191.17/tr, 0%-WR result (structure-fired 7/9, both halves
negative) is a signal-quality problem (fewer confirming triggers = weaker reclaims), not a
sample-size or regime artifact, and nothing in §0's corrections changes that mechanism.

**Refutation line (pre-committed, not adjustable after data is seen):** if the added cohort
clears gates 1-4 with n >= 20 (playbook's decision floor) AND does not fail gate 5
(concentration) AND the bold-2/risky-1 live retroactive read independently corroborates (same
sign, same rough magnitude direction, sign-only per gate 6) — the prediction above is wrong and
`min_triggers_bull: 2 -> 1` becomes a live SHIP candidate, not before.

---

## 5. Forward-shadow requirement before any 10-30 change

Before `filter_10_min_triggers_bull` changes on safe-2/safe-3, a **sole-[11]-refused shadow
ledger** (same pattern as `analysis/recommendations/day-throttle-shadow-ledger.jsonl` /
`loss-armed-budget-shadow-ledger.jsonl`) must run **>= 20 trading sessions**, tracking: every
safe-side HOLD sole-blocked on the isolated trigger-count-only condition (post §2 split), its
would-have-fired outcome via the day's own P1 read (same NOT_REPLAYED-disclosed proxy the miner
already uses), and a running gate-1-through-6 scorecard. This is IN ADDITION TO, not instead of,
the bold-2/risky-1 retroactive live-fill read (§0c, §2) — the retroactive read may shorten or
eliminate the forward wait if it independently clears all 6 gates on its own already-accrued
sample, but that must be verified, not assumed, before treating the forward requirement as
satisfied.

---

## 6. Build step (structured, for whoever executes the RUN)

```yaml
build_step:
  step_1_retroactive_check:
    action: git log -p -S filter_10_min_triggers_bull -- automation/state/aggressive/params.json
    purpose: date bold-2/risky-1's switch to min_triggers_bull=1; defines the live retroactive window
  step_2_population_split:
    file: backtest/tools/postfix_gate_costing.py  # or wherever CORE_DECISIONS resolves
    action: re-derive bull_filter11 sole-blocked rows split by (min_triggers_bull<2 XOR no_level_tied)
    must_not: treat the raw 33-episode cohort as a pure trigger-count population
  step_3_backtest_replay:
    tool: exit_manager_walk
    strike: ATM
    exit_shape: SS-B (per bull-requalification-2026-07-22.json exit_shape_used, quoted in §2)
    disclose: sign-only for bold-2/risky-1/safe-3-attributable rows (WALKER-FULL-POPULATION-ANCHOR-2026-09-03 per-arm gate)
  step_4_forward_shadow:
    pattern: day-throttle-shadow-ledger.jsonl / loss-armed-budget-shadow-ledger.jsonl
    population: bull_filter11 sole-blocked, trigger-count-only subset (from step_2)
    floor: n_trading_days >= 20
  step_5_gates:
    apply: standing 6-gate bar (this document §3)
    window_scheme: equal_count_buckets(n_buckets=4)  # frozen per §3.3, not revisable after data seen
  step_6_verdict:
    vocabulary: SHIP | WATCH | NO-SHIP | KILL  # no new terms introduced mid-run
```

---

## 7. Freeze / date

**Not before 2026-10-30 — this is an EXPANSION (loosening a live admission gate), so it waits
for 10-30 regardless of what the RUN above finds**, per the standing SPY-wiring framing used
throughout this session and queue.md (a trigger-rule change is a 10-30-gated shape change,
distinct from the nearer freeze-compatible measurement/documentation work this document itself
is). The RUN (steps 1-5 above) is freeze-compatible measurement and may execute before 10-30;
only step 6's SHIP branch, and any resulting params.json edit, is gated to 10-30 or later. If
the RUN's own answer is NO-SHIP or KILL, nothing further waits on any date — the knob stays at
its current per-account values (safe: 2, bold: 1, unchanged either way) and this prereg closes
on that verdict.

---

## 8. Revert

N/A for this document — no code, params, or generated surface was touched. If the eventual RUN
ships a change, its own commit must state a one-line revert (set `filter_10_min_triggers_bull`
back to its prior per-account value in the relevant params file) per this repo's standing
revert-in-the-same-commit convention.
