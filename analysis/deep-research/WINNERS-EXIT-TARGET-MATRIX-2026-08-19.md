# WINNERS — EXIT TARGET / TP1 SHAPE MATRIX (every trade we have ever taken)

**Lane:** BIGGER WINNERS · **Lever:** exit target / TP1 shape · **Scope:** ANALYSIS ONLY — nothing armed, no `params*.json` touched, no orders placed.

_Clock verified before work: `setup/scripts/et_clock.py` → **`2026-08-20 00:26:09 Thursday EDT, market_hours=False`** (after-hours work block)._

**Dataset:** [`analysis/recommendations/trade-matrix.json`](../recommendations/trade-matrix.json) — 303 closed round trips, 5 arms, 35 trading days, 2026-06-26 → 2026-08-19. **0 rows dropped**, 0 setups unmapped, 109/109 contract-days of full-day 1-minute OPRA bars already cached (0 network fetches).

**Builders** (all new, all mine):
[`backtest/tools/winners_exit_target_matrix_2026_08_19.py`](../../backtest/tools/winners_exit_target_matrix_2026_08_19.py) (the 74,538-walk grid) ·
[`backtest/tools/winners_exit_target_report_2026_08_19.py`](../../backtest/tools/winners_exit_target_report_2026_08_19.py) (scoring + tables) ·
[`backtest/tools/winners_exit_target_robustness_2026_08_19.py`](../../backtest/tools/winners_exit_target_robustness_2026_08_19.py) (LODO / bootstrap / Rule-5).
**Data:** [`…-2026-08-19.json`](WINNERS-EXIT-TARGET-MATRIX-2026-08-19.json) (scored cells) · `backtest/data/winners-exit-target-matrix-2026-08-19.raw.json` (32 MB of per-trade × per-cell detail — **gitignored, regenerate with the grid builder, ~10 min**) · [`…robust.json`](WINNERS-EXIT-TARGET-MATRIX-2026-08-19.robust.json) · [`…tables.md`](WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md) (the full 246-cell matrix).

---

## VERDICT — 🔴 **NO EDGE. The exit-target matrix is one trend day wearing 246 costumes.**

**The one line asked for:** *no cell beats production by more than its own concentration can explain.* The best cell wins **+$13,214** and **86.6% of that is 2026-08-04 alone**; drop that one day and it wins **+$1,775**, drop the second day too and it **loses −$951**. Its bootstrap 95% CI is **[−$1,875, +$39,480]** and its first half of the book is **+$149**.

| | |
|---|---:|
| Production, broker truth, gross / net of real fees | **−$1,805 / −$1,940** |
| Production shape re-walked, primary realistic model (the comparison baseline) | **−$1,599** net |
| …its reconciliation error vs broker truth | **+$341 on 303 trades (+$1.13/trade)** ✅ |
| **Best cell** — `f0.5_t1.0_r99.0_x0.4` (TP1 sell **50%** @ **+100%**, **no** runner target, **40%** trail) | **+$11,615** net |
| …delta vs production — gross (no-realism convention) / after fees + exit slippage | **+$12,949 / +$13,214** |
| …**share of that delta from 2026-08-04 alone** | **86.6%** 🚨 |
| …top single trade's share | **22.5%** (risky-3 `SPY260804C00763000`) |
| …leave-one-day-out minimum / leave-**two**-days-out | **+$1,775 / −$951** 🚨 |
| …first half of book (2026-06-26→07-23) / second half | **+$149 / +$13,065** 🚨 |
| …day-cluster bootstrap P(delta>0), 95% CI | **89%**, **[−$1,875, +$39,480]** |
| …win rate | **25.1% — identical to production.** Only `avg_win` moves (+$196 → +$370) |
| …worst arm-day / Rule-5 breaches | `safe-3 2026-08-07 −$1,067` / **1 — same as production** ✅ |

**What is true:** the shape of the answer is J's shape. *Every single axis is monotone in "take less off, hold longer, trail wider."* Sell less at TP1 → more money. Raise the TP1 trigger → more money. Delete the runner target → more money. Widen the trail → more money. Nothing in this matrix says "bank earlier."

**What is false:** that this is a lever. **All four monotone axes are the same +$11.4k on 2026-08-04**, a **+1.40% SPY trend day**, mostly two contracts. Strip 08-04 and the entire 4-axis, 246-cell surface collapses into a band of **−$0.1k to +$0.9k over 34 days** with bootstrap intervals straddling zero.

**And the exhibit that motivated the lane does not generalise.** On real fills, across all 44 two-leg TP1+runner exits in the book, the runner filled **above** its own TP1 only **34% of the time**, at a **median −$0.065/contract**. The whole +$345 dollar effect of "let the runner run" is **95.7% one trade** and its top day is **208%** of the total. 2026-08-19's own +$299 winner earned only **+$34** from its runner — the other $265 came from the entry and TP1.

---

## 0. What I changed, and what I deliberately did not

The grid moves **one axis family**: `tp1_qty_fraction` × `tp1_premium_pct` × `runner_target_pct` × `trail_pct`.

Everything else is **pinned at the row's live production shape** and never varied: `premium_stop_pct`, `stop_mode`, the pre-TP1 ladder `[[0.50,0.30],[0.75,0.60]]`, the pre-TP1 trail `(arm 0.75 / 0.20)`, `profit_lock_mode`/`arm_pct`, the `−50%` catastrophe cap, `structure_stop_enabled=true`, and the `15:40` time stop — all read verbatim from [`automation/state/fleet/strategies.py`](../../automation/state/fleet/strategies.py) and [`automation/state/params.json`](../../automation/state/params.json). **The stop is not my lane and I did not touch it.**

| nominal cells | 360 |
|---|---|
| unique after dedupe (frac=0 makes TP1/runner/trail inert; frac=1 makes runner/trail inert) | **246** |
| trades per cell | 303 |
| exit-manager walks executed | **74,538** |

---

## 1. The harness, and the sim-fidelity audit I ran before believing any number

Exits are replayed by the **real live decision core** — `automation/state/fleet/exit_manager.plan_exit_actions`, ticked by [`backtest/lib/exit_manager_walk.walk_exit_manager`](../../backtest/lib/exit_manager_walk.py) — over **full-day** 1-minute OPRA bars, entry → 15:40 ET.

**No look-ahead (C6).** Each tick point-samples that minute's **open** as both best and worst premium, which is the harness's live-NBBO-snapshot analog. Nothing reads a future high. A wider target that "knew" where the top was would be a bug, not a finding.

**Bar sparsity killed as an artifact, with evidence.** A trail evaluated only on minutes that printed would under-trigger and manufacture free money. Measured: bar coverage of the entry→15:40 window is **median 100.0%, mean 99.6%, p10 99.2%**, and **0 of 303** windows fall below 50%. Cheap contracts (<$0.60 entry) are also at 100%. Hypothesis dead.

**The fill model was the artifact — and it is the repo's default.** `exit_manager_walk` fills 6 of its 9 stages *exactly at the trigger level with zero slippage*. Its own docstring records that this is false: `fleet_broker.market_sell` emits `{"type":"market"}` with no `limit_price` for **every** exit stage, TP1 included. Re-walking the production shape under each model:

| model | production replay, gross | vs broker truth (**−$1,805**) |
|---|---:|---:|
| legacy **limit** (repo default) | **+$1,587** | **+$3,392** 🚨 |
| market, flat 2¢/contract | **−$2,595** | −$790 |
| **market, `exit_fill_realism` 0.13-of-bar-range** ← **PRIMARY** | **−$1,464** | **+$341** ✅ |

The legacy convention alone manufactures **+$3,392** on this book. Every number in this report is therefore primary-quoted under the range-realism market model, with the other two shown per cell in [table C](WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md). **Fill price never feeds back into the decision path**, so all three accountings come from the same walk. The cell RANKING is near-invariant to the model — Spearman ρ = **0.9998** (range vs flat-2¢) and **0.9803** (range vs legacy limit), 9/10 top-ten overlap — so the model choice moves the LEVEL, not the ordering. Which is precisely why the level is where the +$3,392 lie hides.

⚠️ **Two disclosures I will not bury.**
1. **Circularity.** The 0.13 constant was calibrated on this same population, so "+$341 reconciliation" is a consistency check, not an out-of-sample validation. It is why I lead with cell-vs-cell *deltas*, never absolute levels.
2. **My sell model is gentler than the hold-time lane's.** [`WINNERS-HOLD-TIME-MATRIX-2026-08-19`](WINNERS-HOLD-TIME-MATRIX-2026-08-19.md) uses `SELL_POS_IN_RANGE = 1/3` and prices production at **−$4,132**; mine prices it at **−$1,599**. Neither is wrong; mine reconciles to broker truth and theirs is more punitive. **Both lanes reach the same verdict**, which matters more than the gap.

**Residual, honestly stated:** the production replay's exit mix is close to but not identical to the realised book (sim `premium_stop` 164 / `structure_stop` 76 / `ribbon_flip` 35 / `runner_stop` 24 vs real 154 / 67 / 31 / —). Today's shape shipped in stages (structure stop 2026-07-09, ladder 2026-08-10), so replaying it over June/July is a counterfactual by construction. My fee recomputation charges per-execution ceilings per leg and lands **+$1.39 over the matrix's own $134.90** — 1%, disclosed, not decision-relevant.

---

## 2. Sample size — what 303 rows is actually worth

The 5 arms trade **one shared signal** (r=0.846, 95.7% sign agreement). Clustering entries within `(date × side)`:

| cluster window | 3 min | 10 min | 15 min | 30 min | **60 min** | date×side | days |
|---|---:|---:|---:|---:|---:|---:|---:|
| independent events | 142 | 116 | 108 | 99 | **84** | 49 | 35 |

**I use n_effective = 84.** All bootstraps in [table F](WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md) resample **trading days** (35 blocks), which is stricter still.

⚠️ **The number that actually bounds this study is smaller.** The best cell's delta is non-zero on **28 trades across 10 days**. Judged on its own effect, this matrix has an effective n of **≈10**, of which **one day is 87%**.

---

## 3. The full matrix

The complete 246-cell ranking, the fill-model sensitivity, the marginals and the robustness layer live in **[`WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md`](WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md)** (sections A–F). The headline surface, best `(runner, trail)` per pair, net of fees, primary model — **production is marked**:

| TP1 frac | TP1 +30% | TP1 +50% | TP1 +75% | TP1 +100% | TP1 +150% |
|---|---|---|---|---|---|
| **0.0** (never take TP1) | +8638 / d +10237 | — | — | — | — |
| **0.333** | +10494 / d +12093 | +9443 / d +11042 | +10786 / d +12385 | **+11465 / d +13064** | +6924 / d +8523 |
| **0.5** | +9151 / d +10750 | +8926 / d +10525 | +10333 / d +11932 | **+11615 / d +13214** ← best | +5337 / d +6936 |
| **0.667** | +3987 / d +5586 | +4390 / d +5989 | +5733 / d +7332 | +6961 / d +8560 **← PROD row** | +4098 / d +5697 |
| **0.8** | +888 / d +2487 | +1686 / d +3286 | +2891 / d +4490 | +4190 / d +5789 | +2831 / d +4430 |
| **1.0** (no runner) | **−4961 / d −3362** | −3449 / d −1850 | −2408 / d −809 | −1149 / d +450 | +980 / d +2579 |

_Production itself is `frac 0.667 / TP1 +100% / runner none / trail 0.15` → net **−$1,599**. The `0.667 / +100%` grid entry reads +$6,961 because that column shows the best trail (0.40); at production's own 0.15 trail it is **+$2,472**, of which **+$4,072 delta is 95% one day** — see §4._

**Win rate is flat at ~25% across the entire top of the matrix.** This lever does not buy wins; it only changes what a win pays. That is the correct shape for a right-tail book — and it is exactly why concentration is the only test that matters here.

### One-axis marginals, isolated

Measured against the reference cell `f0.667_t1.0_r99.0_x0.15` (**not** production — production differs on 4 non-ribbon rows worth +$4,072, which would contaminate every marginal):

| axis | move | total delta | **ex-top-day** | ex-top-2-days | ex-top-day P(>0) |
|---|---|---:|---:|---:|---:|
| TP1 fraction | 0.667 → **0.0** | +6,165 | **+394** | −536 | 61% |
| TP1 fraction | 0.667 → **0.333** | +3,807 | **+203** | −348 | 60% |
| TP1 fraction | 0.667 → 0.5 | +1,447 | +17 | −228 | 49% |
| TP1 fraction | 0.667 → 0.8 | −1,478 | −45 | +131 | 44% |
| TP1 fraction | 0.667 → **1.0** | −3,622 | −60 | +361 | 49% |
| TP1 trigger | +100% → **+150%** | +1,374 | **+336** | +14 | 77% |
| TP1 trigger | +100% → +30% | −1,951 | −84 | −986 | 47% |
| runner target | none → +250% | −2,228 | **+226 (sign flips)** | −0 | 64% |
| trail | 0.15 → **0.25** | +1,900 | **+249** | +147 | **98%** |
| trail | 0.15 → **0.40** | +4,489 | +948 | −703 | 64% |

**Read the ex-top-day column, not the total column.** **Every one of the ten axis moves loses 76–100% of its effect to a single day**, and **six of them flip sign** once the second day goes too. One move survives both — see §6.

---

## 4. Where all the money actually is

2026-08-04 was a **+1.40% SPY trend day** (760.62 → 771.25). Under the best cell, that one session contributes **+$11,440 of the +$13,214**. Two rows do most of it:

| arm | contract | qty | entry | PRODUCTION | BEST CELL |
|---|---|---:|---:|---:|---:|
| risky-1 | `SPY260804C00763000` | 5 | 1.39 | +$540 (`runner_target @ +250%`) | **+$3,426** (`time_stop 15:40`, runner @ **$9.84**) |
| risky-3 | `SPY260804C00763000` | 8 | 1.40 | +$966 (`runner_target @ +250%`) | **+$5,158** (`time_stop 15:40`, runner @ **$9.84**) |

The $9.84 print is **real** — verified in the OPRA cache (15:39 print 9.89, day high 10.34, 219k contracts traded). A 763 call with SPY at 771 is genuinely worth that.

But look at *what changed*: both rows are `VWAP_CONTINUATION`, whose production shape carries `runner_target_pct = 2.5` (**+250%**). **Those two trades are the only two in the entire 303-row book where the +250% runner target ever bound.** Deleting the runner target is therefore an n=2, one-day "edge."

⚠️ **Execution realism, unmodelled and adverse.** The 15:40 exit minute traded **15 contracts total**. The cell sells **13** into it. Two arms hitting one thin minute with market orders would not both get $9.84. The primary model docks 0.13 of that bar's range; it does not model market impact of 87% of a minute's volume. **The best cell's headline is optimistic in a direction I cannot bound with this data.**

---

## 5. Does the 2026-08-19 exhibit generalise? — **No.**

The lane brief named it: on 2026-08-19 the day's biggest winner (+$299, risky-1) was the only 2-leg TP1+runner exit, and its runner beat its TP1 ($1.82 vs $1.65).

Both halves are true. Neither generalises.

**On real broker fills, all 44 two-leg exits that reached TP1:**

| | |
|---|---:|
| runner filled **above** its own TP1 | **15 / 44 = 34%** |
| median runner-minus-TP1 edge | **−$0.065 / contract** |
| mean | +$0.030 / contract |
| **total dollar effect of running the runner vs selling all at TP1** | **+$345** |
| …**share from the single best trade** (2026-08-04 risky-1) | **95.7%** 🚨 |
| …top day (2026-08-04) share | **208%** — every other day nets negative |
| mean edge with that one trade removed | **+$0.005 / contract** |

**And the exhibit trade itself argues the other way.** risky-1 sold 3 @ $1.65 and 2 @ $1.82 from a $1.12 entry: the runner contributed **+$34** of the $299. Meanwhile on the *same signal, same contract*, safe-3 took **no** TP1 and exited all 3 at $1.83 — **$69/contract vs risky-1's $59.80/contract**. On 2026-08-19, "don't take TP1 at all" beat "TP1 + runner." That is the `frac = 0.0` cell — which the matrix ranks 12th and which is **94% one day**.

---

## 6. The only thing that survived its own concentration test

**Widening the chandelier trail from 0.15 → 0.25**, holding TP1 fraction, trigger and runner target at production:

| | |
|---|---:|
| total delta | +$1,900 |
| top day (2026-08-03, +1.10% SPY) share | 87% |
| **ex-top-day delta** | **+$249** |
| ex-top-2-days | **+$147** (sign holds) |
| ex-top-day bootstrap P(>0) | **98%** |
| ex-top-day bootstrap 95% CI | **[+$13, +$532]** — excludes zero |
| days with any delta | 9 (6 up / 3 down) |
| Rule-5 breaches | 1 — unchanged from production |

It is the **only** move in 246 cells whose post-concentration confidence interval excludes zero.

**It is also economically trivial and I will not dress it up.** +$249 over 34 days across 5 arms is **+$7.3/day book-wide ≈ $1.50/day/arm** — about **1% of the $100–200/day/arm target** (per-account, per J 2026-08-09). And the interval is driven by 9 non-zero days, not 34. This clears a statistical bar and fails an economic one.

---

## 7. What this lane proves about the book

Two facts sit underneath every cell, and neither is an exit-shape problem:

1. **Only 14% of trades ever touched +100% inside the window we actually held them.** Held to 15:40, **34%** touch +100% and **24%** touch +150%. The trigger is not unreachable — **our stop gets there first.** That is the stop lane's finding, not mine, and it is why my monotone axes all point at "hold longer."
2. **All winner dollars come from one exit stage.** Real fills: `tp1` = 44 trades, **+$14,514** (avg +$330). Every other stage is negative or zero (`premium_stop` 154 trades −$10,090; `structure_stop` 67 trades −$5,998). The book's problem is not that TP1 is mis-set; it is that 233 of 303 trades never get to any profitable stage.

Breakeven arithmetic on the **full 303-row book**: WR 23.1%, avg win +$224.1, avg loss −$75.1 → **breakeven WR 25.09%**, short by **1.99pp**. (The lane brief's 28.59% / 26.98% / −1.6pp is the same arithmetic on the **safe-2 + bold-2 subset, n=63** — both are correct, different populations. Per-arm: safe-2 −5.7pp, bold-2 −3.0pp, safe-3 −1.6pp, risky-3 −1.1pp, risky-1 −0.2pp.) Perfect foresight over the *held* window is **+$41,821** and the worst case is **−$27,949** — the tail is enormous in both directions, and no rule in this matrix separates them prospectively.

---

## 8. PRE-REGISTERED HYPOTHESIS — the only shippable output

Per OP-11 / lane scope, this ships as a **pre-registration, not a change.** Nothing is armed. `params*.json` untouched.

> ### PREREG `EXIT-TRAIL-WIDEN-2026-08-19`
>
> **Claim.** Widening the ribbon_ride chandelier trail `trail_pct` **0.15 → 0.25**, with `tp1_qty_fraction`, `tp1_premium_pct` and `runner_target_pct` unchanged, adds a small positive expectancy that is not carried by a single day.
>
> **Frozen before observation.** Effect measured **ex-top-day**: **+$249 over 34 days**, ex-top-2 **+$147**, day-bootstrap **P(>0)=98%**, 95% CI **[+$13, +$532]**, **+$7.3/day book-wide**. Sole axis moved. Rule-5 exposure unchanged (worst arm-day `safe-3 2026-08-07 −$1,067`, identical to production).
>
> **Shadow, not armed.** Log the counterfactual per trade for **40 fresh trading days** — long enough for ≥12 days to produce a non-zero delta (only 9 of 35 did historically).
>
> **KILL CRITERION (any one fires → dead, do not re-test):**
> 1. Cumulative shadow delta **ex-its-own-top-day** is **≤ $0** at day 40; **or**
> 2. any **single day** supplies **> 60%** of the cumulative delta; **or**
> 3. fewer than **12 days** produce a non-zero delta (the effect is too rare to measure); **or**
> 4. the shadow delta's day-bootstrap **P(>0) < 90%** at day 40.
>
> **Explicitly NOT pre-registered** — killed here on concentration, do not resurrect without a new mechanism: lowering `tp1_qty_fraction` below 0.667, raising `tp1_premium_pct` above +100%, deleting `runner_target_pct`, `trail_pct` ≥ 0.40, and the `frac = 0.0` (never-take-TP1) shape.

---

## 9. Loose ends I did not close

- **Market impact is unmodelled.** The best cell's top two trades sell 13 contracts into a 15-contract minute. My realism model docks bar-range slippage, not impact. Any future ride-to-EOD study needs a volume-aware fill model before its headline can be trusted.
- **Historical per-arm `exit_patch` overlays.** `accounts.json` shows `exit_patch: null` for all arms today, but `strategies.py` notes past overlays (risky-3 trail 0.20, risky-1 TP1 0.5). If those were live at the time, the production baseline for those arm-days is slightly off. Direction unknown; magnitude bounded by the 4 non-ribbon rows that already differ (+$4,072, 95% one day).
- **Structure-stop era.** `structure_stop_enabled=true` is applied across the whole book though it shipped 2026-07-09. This is disclosed, not corrected: the matrix compares cells to each other under one fixed stop regime, which is the comparison that isolates my lever.

---

_Related lanes, same dataset, same day: [`WINNERS-STRIKE-MATRIX-2026-08-19`](WINNERS-STRIKE-MATRIX-2026-08-19.md) (WEAK) · [`WINNERS-HOLD-TIME-MATRIX-2026-08-19`](WINNERS-HOLD-TIME-MATRIX-2026-08-19.md) (NO EDGE) · [`LOSER-SEPARABILITY-2026-08-19`](LOSER-SEPARABILITY-2026-08-19.md) (losers not separable). Three of four winner-side levers now return NO EDGE on the same 2026-08-04-shaped concentration._
