# Winner autopsy — synthesis
## risky-3, SPY 746C 0DTE, entered 12:19:03 ET Friday 2026-07-31

> **Written 2026-07-31 18:10 ET** (verified via `setup/scripts/et_clock.py` — market closed; the box runs Mountain, ET = local+2). Git sha at time of writing: `abb1f42d`.
> **Frames:** every wall-clock time in this document is **ET**. Alpaca MCP returns **UTC** and was converted explicitly on every read. Repo state files (`decisions.jsonl`, `fills-ledger.jsonl`, `core-decisions.jsonl`) are already ET-stamped (`-04:00`). Raw OPRA/SIP bar timestamps are UTC and are labelled as such wherever quoted.
> **Data:** real OPRA trade bars and real broker fills only. Zero synthetic / Black-Scholes premiums anywhere in this document. Where a number is an oracle bound or a convention artifact, it is labelled inline.

---

## 1. The one thing

**Staying in longer was worth +$859 on this trade and −$451.50 across all 21 winners — so the lesson is not "hold longer." The lesson is that we gave up $14.40 of a $126 trade to a stop we ourselves set at $0.552 and then did not look at again for three minutes, filling at $0.48.**

The runner's underperformance was **plumbing, not strategy**. And the structural reason it was *always* going to underperform TP1 is arithmetic, not luck — see §3.

---

## 2. The story

### 2.1 Why it got in

The engine scored the bullish setup **11 out of 11 with zero blockers**. Here is every filter, at the 12:16:02 ET core tick:

| # | Filter | Reading | Verdict |
|---|---|---|---|
| F1 | Entry-time gate | trigger bar 12:10 ≥ 09:35 | PASS |
| F2 | News blackout | zero events today (next NFP 08-07) | PASS |
| F3 | Loss budget | intact | PASS |
| F4 | Day-trade count | 0 of 3 used | PASS |
| F5 | Ribbon MA stack | BULL-stacked | PASS |
| F6 | Ribbon spread | 94.66¢ ≥ 30¢ floor | PASS |
| F7 | Volume divergence | none bullish | PASS |
| F8 | VIX level | **17.24 vs a 17.20 threshold — FAILS on level**, passes only because VIX was *falling* (17.27 → 17.24) | PASS (on the falling clause) |
| F9 | VIX hard cap | 17.24 < 22 | PASS |
| F10 | Buyer pressure | green bar (743.045 → 743.55) **and** volume 395,851 ≥ 0.7 × 446,739 = 312,717 (0.89× the 20-bar baseline) | PASS |
| F11 | Level-tied trigger + HTF | `level_reclaim` @ 743.25 + `confluence`; 15m HTF = BULL (no demerit) | PASS |

`bull_score = 11 − len(blockers) = 11 − 0 = 11`.

**The trigger bar** was the 12:10 ET 5-minute candle (closed 12:15:00.000). SIP: O 743.045 / H 743.66 / **L 743.00** / C 743.55 / V 395,851. It was the first bar of the session whose **low pierced 743.25 and whose close was above it** — the definition of `detect_level_reclaim`.

**What actually flipped the switch was F10, not the level.** The 12:05 bar was *red* (743.24 → 743.04), so buyer-pressure blocked the setup on every tick from 12:06 through 12:15. The 12:10 bar was green *and* pierced-and-reclaimed. Both conditions landed on the same bar for the first time all day.

**Where 743.25 came from.** It is **not** a premarket low and **not** an intraday construct. It is `SHELF_742.45_744.05_2026-07-31` — source `daily_context_shelf`, tier **Active**, weight 5, **8 touches across 28 sessions**, zone width $0.80, last broken *downward* on 2026-07-23 (six sessions earlier). It was written premarket at **08:33:37 ET** by `daily_context.py`, before the open, and never re-derived from intraday action.

> **Correction to an earlier draft of this lane, verified cold this session.** The SIP premarket low (04:00–09:29:59 ET) was **742.79**, on the 08:40 ET 5-minute bar — not 744.02 (744.02 is only the 04:00 bar's low). J's remembered **742.97** is itself a real premarket print — it is the low of the 08:55 ET bar — and sits $0.18 above the true extreme. The level file's own `INTRADAY_PML` read **742.79** at its 09:28 refresh, i.e. **exactly correct**. The "label-vs-measurement gap" alleged in an earlier draft is **withdrawn**. What remains true and load-bearing: the engine traded a **28-session shelf**, not a premarket extreme. Both levels sit inside the same 742.45–744.05 zone, so J's instinct about the neighbourhood was right.

**A caution about the "ELITE" quality tag.** `detect_confluence(743.25, …)` returned **743.25 itself** — the only level within the ±$0.30 tolerance was the level being reclaimed. Across the entire core-decisions ledger, confluence fires on **532 of 532** ticks where a bull `level_reclaim` fires (**100.0%**; bear side 562/577 = 97.4%). The mechanism is in `heartbeat_core._read_levels`, which builds `multi_day_levels` as a role-filtered *subset* of `levels_active` — so the reclaimed level is almost always in its own confluence pool. **"ELITE" is close to a restatement of "a level trigger fired," not a second, independent confirmation.** That is pre-registered below (PR-1), not acted on.

**The signal was already dead when the order was placed.** The 11/11 lived exactly **three core ticks**: 12:16:02, 12:17:02, 12:18:02. At **12:19:02** it fell to 10/11 — not because price moved, but because a **level-file refresh landed between two 1-minute ticks and removed 743.25 from `levels_active`** (741.6 also became 741.63 in the same refresh). The fleet's placing decision at 12:19:02.259 carries `trigger_level 743.25` + ELITE, which only exists in the 12:16–12:18 rows. **It entered on a snapshot the core had retired ~1 second earlier.** 743.25 was present in only 331 of the day's 386 core ticks (85.8%) with **14 appear/disappear flips**.

**Latency, exactly.** Bar close 12:15:00.000 → fill 12:19:03.937 = **243.94 s (4m 03.9s)**:

| Segment | Elapsed | Cause |
|---|---|---|
| Bar close → core scores 11/11 (12:16:02) | 62.0 s | 1-minute core cadence |
| Core verdict → fleet decision (12:19:02.259) | **180.26 s (74%)** | see correction below |
| Decision → order submit (12:19:03.839) | 1.58 s | — |
| Submit → fill (12:19:03.937) | 0.098 s | — |

> **Corrected attribution.** An earlier draft blamed the 180 s purely on the 3-minute fleet cadence. Verification found the fleet **did** tick at **12:16:02.508** and logged *"no qualifying setup"* for all three arms — 0.45 s after the core wrote its 11/11 row. `build_shared_signal.py` reads the *last-written* core row, and the `bold` row did not land until 12:16:03. So the 180 s is a **sub-second write/read race that cost a full 3-minute cadence slot**, not the cadence alone. The elapsed time is right; the earlier causal story was incomplete.

**What the lag cost — and the irony.** At the 12:16 minute the 746C traded 0.27; we paid 0.33 at 12:19. On 5 lots that is **$30, or 24% of the realized $126**. But the logged mid at 12:19 was **exactly $0.30** against a `min_entry_premium` floor of **$0.30** — it cleared by $0.00. At a 0.27 print the mid would very likely have been *under* the floor and the order refused. **On this one trade, the latency that cost us $30 is what made the trade legal at all.** (That last clause is an inference from trade prints, not a logged mid — the fleet never probed a premium at 12:16.)

### 2.2 Why 746 — and what the other strikes would have paid

**One reason only: risky-3's equity was $76.35 over a tier boundary.**

All three arms resolve to the *same* table, `V15_BOLD_TIERS`. `pick_strike` for calls is `round(spot) − offset`. Spot 743.54 → 744.

| Arm | Equity | Tier | Offset | Strike | Outcome |
|---|---|---|---|---|---|
| **risky-3** | **$2,076.35** | [$2K, $10K) | −2 | **746** | filled $0.33, **+$126** |
| safe-3 | $1,893.04 | [$0, $2K) | −3 | 747 | mid $0.15 → **refused** by the $0.30 floor; re-entered 747 at 12:31 at a repriced $0.33 (+$74.88) |
| risky-1 | $1,756.87 | [$0, $2K) | −3 | 747 | mid $0.15 → **refused** |

Not moneyness logic, not quote timing, not a per-arm strategy config. A **$76 equity margin** moved the strike by $1.

**The strike counterfactual** — real OPRA 1-minute *trade* bars, 5 lots, 3 TP1 / 2 runner, on a **frozen clock** (in at the 12:19 minute open, out at the 12:34 and 12:43 closes — a convention calibrated to reproduce the actual 746 fills 0.33 / 0.65 / 0.48 **exactly**):

| Strike | Entry | P&L (5 lots, frozen clock) | Return on capital | Note |
|---|---|---|---|---|
| 744 (ATM) | $0.97 | **+$276** | 56.9% | $485 capital |
| 745 (OTM-1) | $0.58 | +$200 | 69.0% | |
| **746 (OTM-2)** | **$0.33** | **+$126** | **76.4%** | **ACTUAL**, $165 capital |
| 747 (OTM-3) | $0.17 | +$73 | 85.9% | *this is the strike the floor refused* |
| 748 (OTM-4) | $0.09 | +$35 | 77.8% | ROC breaks monotonicity |

The rank 744 > 745 > 746 > 747 > 748 holds at fixed quantity under all three fill conventions tested (open/close, worst-case high-in/low-out, VWAP).

**But the ranking inverts on capital.** At an equal **$165 risked**: 744 → +$68, 745 → +$75, **746 → +$126**, 747 → +$138, 748 → +$132. The nearer strikes win on dollars; the further strikes win per dollar risked.

**Verdict: 746 was not a wrong pick — it was the best strike actually *available*.** 747 and 748 were both under the $0.30 entry floor, which is precisely what happened to safe-3 and risky-1 at 12:19.

**Sizing context.** Base quantity was **12**, hard-clamped to **5** by `_apply_recency_min_sizing` on a RED recency verdict. The clamp is premium-independent, so the strike table above is unaffected — but at 12 lots (8 TP1 / 4 runner) the identical fills pay **+$316** instead of +$126.

### 2.3 What it saw while it held

The arm evaluates the position every **3 minutes**. All 9 ticks of the hold are present in the ledger — none missing.

| Tick ET | SPY | Ask (best) | Bid (worst) | Unrealized | Trail floor | Ribbon | Action |
|---|---|---|---|---|---|---|---|
| 12:19:02 | 743.54 | 0.30 mid | — | — | — | BULL | **ENTER 5** |
| 12:22:03 | 743.84 | 0.41 | — | +24% | — (not armed) | BULL | HOLD |
| 12:25:03 | 743.96 | 0.44 | — | +33% | — | BULL | HOLD |
| 12:28:02 | 744.14 | 0.47 | — | +42% | — | BULL | HOLD |
| 12:31:02 | 744.77 | 0.58 | — | +76% | — | BULL | HOLD |
| **12:34:02** | 744.78 | **0.69** | — | **+109%** | — | BULL | **SELL 3 @ tp1**; ratchet stop → 0.34 (BE) |
| 12:37:03 | 744.63 | — | **0.58** | +76% | **0.552** | BULL | HOLD — 2.8¢ above the floor |
| 12:40:04 | 744.69 | — | **0.57** | +73% | 0.552 | BULL | HOLD — 1.8¢ above the floor |
| **12:43:02** | 744.26 | — | **0.50** | +52% | 0.552 | BULL | **SELL 2 — trail breached** |

**What it was "thinking":** nothing narrative — it was checking three things every three minutes. (1) Is the ask ≥ 2× the registered entry? *No, until 12:34.* (2) Post-TP1, is the bid below HWM × 0.80? *No, until 12:43.* (3) Did the last closed 5-minute bar close below the structure level 743.25? *No — SPY never came within $1 of it during the hold.*

**Two things it could not see.** The engine sampled a high-water ask of **$0.69** at 12:34; the real OPRA tape traded **$0.71** at 12:35 (SPY high 745.03). And at **12:40:04** the row's `last_closed_5m_close` was **null** — the structure-stop check was **silently skipped** for that tick (documented fail-open). Immaterial here, but the engine was structurally blind on one of the nine looks.

**The ribbon read BULL on every single tick of the hold.** Full-day histogram: BULL 682 / MIXED 90 / **BEAR 0**. The `ribbon_flip_back` exit was **structurally incapable of firing on this trade** — it needs a BEAR stack for a call, and there wasn't one all day.

**746.30 — J's "high of day at the start of the day."** It is real, it was in the engine's own level file at 12:00 as `INTRADAY_RTH_HIGH 746.30`, and it was set in the first five minutes (the 09:30 ET 5m bar high = 746.301, confirmed against SIP this session). **SPY did not touch it until 13:27 — 44 minutes after the runner was already out.**

### 2.4 How each leg closed, and which rule closed it

| Leg | Qty | Fill | Time ET | Rule that fired | Log line | P&L |
|---|---|---|---|---|---|---|
| TP1 | 3 | $0.65 | **12:34:04.015** | `tp1 @ +100%` — ask 0.69 ≥ 0.68 threshold | `SELL_PARTIAL … stage tp1` | **+$96.00** |
| Runner | 2 | $0.48 | **12:43:03.847** | **chandelier trail** — bid 0.50 ≤ runner_stop 0.552 (= 0.69 HWM × 0.80) | `SELL_ALL … stage trail, "runner_stop @ 0.55"` | **+$30.00** |

Total realized **+$126.00**. Arm equity $2,076.35 → $2,202.15 immediately after (+$125.80).

### 2.5 J's literal question: was it sold at ~13:45 into the ribbon close?

**No. And the thing J remembers is a different trade.**

The runner was flat at **12:43:03 ET** — **69 minutes before** 13:45 — on the chandelier trail, with the ribbon still reading BULL.

risky-3 then took a **second** trade that afternoon:

| | |
|---|---|
| Entry | 5× SPY260731**C00747000** @ **$0.52**, **13:25:05.848 ET** |
| Exit | 5 @ **$0.36**, **13:52:04.641 ET** |
| Rule | **structure stop @ 745.31** — the 13:45 5-minute bar closed **745.29**, missing the level by **1.5 cents** |
| P&L | **−$80.00** |

That is the 13:45-ish event. It was a **structure stop on a loser**, not a ribbon flip, and not this trade. **Arm net for the day: +$126 − $80 = +$46.**

---

## 3. The giveback

| Leg | Qty | Entry | Exit | Return | Peak available ($0.71) | Realized | Captured |
|---|---|---|---|---|---|---|---|
| TP1 | 3 | $0.33 | $0.65 | **+97%** | $114.00 | $96.00 | **84.2%** |
| Runner | 2 | $0.33 | $0.48 | **+45%** | $76.00 | $30.00 | **39.5%** |
| **Total** | 5 | | | | $190.00 | **$126.00** | **66.3%** |

**Total giveback vs the in-trade peak: $64.00.**

### The mechanism, decomposed to the cent

The runner's $0.230/contract giveback (0.71 → 0.48) breaks down exactly:

| Component | $/ct | What it is |
|---|---|---|
| HWM sampling | 0.020 | engine saw 0.69 ask; tape traded 0.71 |
| Mechanical trail band | **0.138** | 20% of the high-water mark — the design, working as designed |
| Sampling gap at the firing tick | **0.052** | floor was 0.552; next look saw 0.50 |
| Fill slippage | 0.020 | market sell took 0.48 off a 0.50 bid |
| **Sum** | **0.230** | = 0.71 − 0.48 ✓ |

**Two of those four are the trail doing its job. Two of them — 0.072/ct, $14.40 on 2 lots — are us not looking.**

### The structural reason the runner was doomed to lose to TP1

For the runner to realize more than TP1's $0.65, the chandelier floor had to sit above 0.65:

> HWM × (1 − trail_pct) > TP1_fill  →  HWM > 0.65 / 0.80 = **$0.8125**

The peak was **$0.71**. It fell **13% of premium short**.

Generalized: **with a +100% TP1 and a 20% trail, the runner only beats TP1 if the premium rallies another 25% above the TP1 print** (`1/(1−0.20) − 1`). At the registry's 0.15 trail the bar is 17.6%. This is arithmetic, not a hypothesis — but *how often 0DTE winners clear that bar* is an empirical question that n=1 cannot answer.

**The counter-intuitive result, stated because it is unflattering:** on this trade, exiting **earlier** was better. risky-3's own looser 0.20 trail — its entire A/B thesis, "the arm that rides them better" — **underperformed** the registry's 0.15. A 0.15 trail (floor 0.5865) would have exited at 12:37:03 into a 0.58 bid, worth roughly **+$16.00 more** on the 2 lots. This is n=1 on a peak-and-fade, exactly the regime a tighter trail flatters. **Do not move `trail_pct` on the strength of this row.**

---

## 4. The exit grid

46 live-executable variants, replayed through the **real** `exit_manager.plan_exit_actions` on real OPRA 1-minute bars. Full cell-by-cell data: `analysis/recommendations/exit-grid-n1-2026-07-31-746c.json`.

### 4.0 The error bar — read this before believing any delta

The harness reproduces this exact position at **$147.80** against the real **$126.00** — it is **+17.3% optimistic**. Mechanisms: (a) it fills limit-style *at* the trigger level while the live arm market-sells into the bid ($9.00 on TP1, $12.80 on the runner); (b) it ticks every 1 minute while the arm ticks every 3.

> **Any delta smaller than $21.80 is model error, not a finding.** Those cells are marked ⓑ below.

### 4.1 ORACLE BOUNDS — hindsight only, NOT achievable, NOT variants

| Bound | Value |
|---|---|
| Post-entry peak premium, full session | **$2.83 at 15:54 ET** |
| Oracle P&L, all 5 sold at that peak | **$1,250.00** |
| Peak before the 15:40 time stop | $2.05 at 15:22 |
| Oracle P&L before the time stop | $860.00 |
| **Baseline capture vs the full-session oracle** | **10.08%** |

*Nothing below this line should ever be compared to these numbers as if a rule could have reached them.*

### 4.2 LIVE-EXECUTABLE VARIANTS — all 46 cells, best to worst

| # | Variant | Family | P&L | Δ vs live | Exit ET | Flags |
|---|---|---|---|---|---|---|
| 1 | HOLD_ALL_TO_EOD_FLATTEN_1555 | hold | **$985.00** | +$859.00 | 15:55 | ⓕ |
| 2 | LEVELTP 746.55 `INTRADAY_PMH` close5 | level | $695.00 | +$569.00 | 15:20 | |
| 3 | LEVELTP 748.09 SHELF touch | level | $615.00 | +$489.00 | 15:40 | ⓝ |
| 4 | LEVELTP 748.09 SHELF close5 | level | $615.00 | +$489.00 | 15:40 | ⓝ |
| 5 | LEVELTP 748.50 `MEMORY_RES_95` touch | level | $615.00 | +$489.00 | 15:40 | ⓝ |
| 6 | LEVELTP 748.50 `MEMORY_RES_95` close5 | level | $615.00 | +$489.00 | 15:40 | ⓝ |
| 7 | HOLD_ALL_TO_TIMESTOP_1540 | hold | $615.00 | +$489.00 | 15:40 | ⓕ |
| 8 | NO_TP1_ALL5_ON_CHANDELIER scope=post_tp1 | hold | $615.00 | +$489.00 | 15:40 | ⓓ ⓕ |
| 9 | RIBBON_FLIP_ARMED_NO_TP1 | ribbon | $615.00 | +$489.00 | 15:40 | ⓓ ⓕ |
| 10 | TP1_THEN_RUNNER_TO_EOD_NO_TRAIL | hold | $499.00 | +$373.00 | 15:55 | ⓕ |
| 11 | **LEVELTP 746.30 `INTRADAY_RTH_HIGH` close5** | level | **$430.00** | +$304.00 | 13:35 | **← J's idea** |
| 12 | LEVELTP HOD-so-far 746.30 close5 | level | $430.00 | +$304.00 | 13:35 | (same level) |
| 13 | TRAIL_0.500 | trail | $351.00 | +$225.00 | 15:40 | |
| 14 | LEVELTP 746.30 `INTRADAY_RTH_HIGH` touch | level | $330.00 | +$204.00 | 13:27 | |
| 15 | LEVELTP HOD-so-far 746.30 touch | level | $330.00 | +$204.00 | 13:27 | |
| 16 | LEVELTP 746.55 `INTRADAY_PMH` touch | level | $295.00 | +$169.00 | 15:00 | |
| 17 | TP1_PCT_1.50 | tp1 | $283.60 | +$157.60 | 13:40 | ⓖ |
| 18 | TRAIL_0.400 | trail | $184.20 | +$58.20 | 13:48 | |
| 19 | LEVELTP 744.98 SHELF touch | level | $170.00 | +$44.00 | 12:35 | |
| 20 | LEVELTP open-0930 744.68 close5 (level only) | level | $170.00 | +$44.00 | 12:35 | |
| 21 | LEVELTP open-0930 744.68 close5 (TP1→level) | level | $170.00 | +$44.00 | 12:35 | |
| 22 | TRAIL_0.100 | trail | $161.40 | +$35.40 | 12:37 | ⓑ |
| 23 | TRAIL_0.125 | trail | $158.00 | +$32.00 | 12:37 | ⓑ |
| 24 | TRAIL_0.150 (registry default) | trail | $154.60 | +$28.60 | 12:37 | ⓑ |
| 25 | HARNESS_REPRO_PRODUCTION_SHAPE | parity | $147.80 | +$21.80 | 12:39 | ⓑ **the error bar itself** |
| 26 | TRAIL_0.200_LIVE | trail | $147.80 | +$21.80 | 12:39 | ⓑ |
| 27 | TP1_PCT_1.00_LIVE | tp1 | $147.80 | +$21.80 | 12:39 | ⓑ |
| 28 | RIBBON_FLIP_EXIT_ARMED | ribbon | $147.80 | +$21.80 | 12:39 | ⓑ **never fired — 0 BEAR bars** |
| 29 | LEVELTP HOD 746.30 touch (TP1→level) | level | $145.00 | +$19.00 | 12:39 | ⓑ ⓝ |
| 30 | LEVELTP HOD 746.30 close5 (TP1→level) | level | $145.00 | +$19.00 | 12:39 | ⓑ ⓝ |
| 31 | TRAIL_0.250 | trail | $141.00 | +$15.00 | 12:42 | ⓑ |
| 32 | TRAIL_0.300 | trail | $134.20 | +$8.20 | 12:42 | ⓑ |
| 33 | LEVELTP 744.98 SHELF close5 | level | $130.00 | +$4.00 | 13:05 | ⓑ |
| **34** | **BASELINE — ACTUAL LIVE FILLS** | actual | **$126.00** | **$0.00** | **12:43:03** | **what happened** |
| 35 | TP1_PCT_0.75 | tp1 | $122.30 | −$3.70 | 12:39 | ⓖ |
| 36 | LEVELTP 744.31 `MEMORY_RES_65` close5 | level | $100.00 | −$26.00 | 12:30 | ⓝ* |
| 37 | LEVELTP open-0930 744.68 touch (level only) | level | $100.00 | −$26.00 | 12:30 | |
| 38 | LEVELTP open-0930 744.68 touch (TP1→level) | level | $100.00 | −$26.00 | 12:30 | |
| 39 | LEVELTP 744.31 `MEMORY_RES_65` touch | level | $85.00 | −$41.00 | 12:24 | ⓝ* |
| 40 | TP1_PCT_0.50 | tp1 | $72.80 | −$53.20 | 12:28 | ⓖ |
| 41 | TP1_PCT_0.30 | tp1 | $52.40 | −$73.60 | 12:28 | ⓖ |
| 42 | NO_TP1_ALL5_ON_CHANDELIER scope=**full** | hold | $47.00 | −$79.00 | 12:28 | ⓖ **= the graveyarded pre-TP1 lock** |
| 43 | LEVELTP PDH 742.45 touch (level only) | level | $5.00 | −$121.00 | 12:20 | ⓧ |
| 44 | LEVELTP PDH 742.45 touch (TP1→level) | level | $5.00 | −$121.00 | 12:20 | ⓧ |
| 45 | LEVELTP PDH 742.45 close5 (level only) | level | $5.00 | −$121.00 | 12:20 | ⓧ |
| 46 | LEVELTP PDH 742.45 close5 (TP1→level) | level | $5.00 | −$121.00 | 12:20 | ⓧ |

**Legend**
ⓑ **inside the $21.80 model-error band — not a finding.**
ⓝ **no-op: the level was never reached; this cell is really a time-stop or a trail result wearing a level-target label.** (ⓝ* = the naive "nearest level above spot" pick, which *did* fire and lost money.)
ⓖ **graveyard collision** — see §4.3.
ⓕ **only wins because SPY went up and kept going up after 12:19.** On the many days it doesn't, these are the cells that give back the whole trade.
ⓧ **degenerate** — prior-day high 742.45 was already *below* entry spot, so it "fires" instantly.

### 4.3 Graveyard collisions — flagged, not re-litigated

| Family | Status |
|---|---|
| Every `TP1_PCT` cell below 1.00 | **take-profit-earlier, ×3 iterations.** Cell E2 of `exit-armscope-tp1-ab-2026-07-28` tested a uniform tp1 1.0→0.5 and returned **−$2,491 aggregate / −$5,616 on the runner cohort**. |
| `NO_TP1_ALL5_ON_CHANDELIER scope=full` (#42) | **IS the pre-TP1 trailing lock.** Graveyarded at 4 thresholds; clipped the runner cohort at every one (−$7,759 → −$3,898). |
| Ribbon-flip exit | **shipped production behaviour** since G14, not a proposal. C28 already documents it as a lagging exit. |
| `trail_pct` sweep | not graveyarded, but it is a **live A/B axis already** (risky-3 runs 0.20 vs the registry 0.15). n=1 cannot move it. |
| Level-referenced take-profit | **the one genuinely untested family here.** Adjacent graveyard entries — exit-all-at-touch, the zone-banded CLOSE-cross detector — were *entry/stop-side* detectors, not profit targets. Which is exactly why it gets a **pre-registration and not a ship.** |

### 4.4 Two things the grid says that the headline numbers hide

**(a) The exit MINUTE, not the exit RULE, dominates every "hold longer" cell.** The same hold-to-EOD position is worth **$1,190 at 15:53** and **$180 at 15:59**. Every cell above $499 resolves inside a 20-minute window where the 746C ran 1.58 → 2.83 → 0.71 on 9–21 prints a minute. The $985 headline is four minutes away from $180.

**(b) A naive level-target detector would have LOST money.** "Nearest eligible level above spot" picks **744.31**, which returns $85–$100 — worse than the actual $126. J's instinct is right about the *frame*; it says nothing about *which level qualifies*, and that choice is the entire hypothesis. It must not be picked by looking at this day.

**(c) One schema finding, not a result.** "Never take TP1, ride all 5 on the chandelier" is **not expressible today**. With `profit_lock_arm_scope=post_tp1`, killing TP1 also means the chandelier never arms — so the variant silently degenerates into hold-to-time-stop. The knob J is imagining does not exist.

---

## 5. What this is not

> ## ⛔ n=1 PROVES NOTHING.
> **This is ONE trade on ONE day — a V-recovery that melted up into the close. Every "hold longer" cell wins here by construction. Nothing in this document ratifies a strike change, an exit change, a level change, a gate change, or a cadence change. No parameter was touched. No hypothesis was queued. `params.json`, `aggressive/params.json`, `strategies.py`, `exit_manager.py` and risky-3's own `exit_patch` are byte-identical to where they started.**

**What got PRE-REGISTERED instead** (frozen 2026-07-31, git sha `abb1f42d`):

| ID | Hypothesis | Status |
|---|---|---|
| **Level-target exit** | Can a level-referenced take-profit beat the chandelier? 144 declared cells, gates G1–G8 (incl. **runner-cohort no-regression at ZERO tolerance**), BH-FDR q=0.10 over all 144, n≥30 minimum with `INCONCLUSIVE_UNDERPOWERED` below it, explicit kill criterion, no band-moving-and-re-running. | **FILED** — `analysis/recommendations/level-target-exit-prereg-2026-07-31.json`. **Blocked**: `key-levels-history` holds only 6 dates × ~4 snapshots; as-of reconstruction must first prove the level producers are causal (vary-and-assert) or the study's only honest output is a power estimate. **Hard falsifier attached:** any upside level-target formulation must explain how it survives the 12:38 trail breach on this anchor, or it is dead before the study starts. |
| **PR-1 Confluence-is-tautological** | Does `confluence` carry *any* information over `level_reclaim` on the bull side? Observed 532/532 co-occurrence. Test: ELITE vs non-ELITE bull entries, real fills, n≥20/cell, expectancy + BH-FDR. If indistinguishable → either exclude the reclaimed level from its own confluence pool, or retire the ELITE tag on the bull side. | **FROZEN, not filed** |
| **PR-2 Equity-tier discontinuity** | Does the $2,000 boundary in `V15_BOLD_TIERS` (OTM-3 below / OTM-2 above) affect realized expectancy? Here a $76 margin changed the strike by $1, changed frozen-clock P&L 2.2×, and **inverted** return-on-capital. Test: replay all fleet arm-days across the boundary on **both** absolute P&L and ROC, with **floor-clearance participation rate as a first-class metric**. | **FROZEN, not filed** |
| **PR-3 Signal-staleness window** | Does entering on an N-tick-stale shared-signal snapshot change expectancy? Here the winning entry rode a snapshot the core retired ~1 s earlier. Test: tag every fleet fill with `fleet_decision_ts − source_core_row_ts` and stratify. **Measurement only — must not become a cadence change.** | **FROZEN, not filed** |
| **PR-4 Level flicker** | Is `daily_context_shelf` level identity stable within a session? 743.25 flickered 14× over 386 ticks (85.8% present) and its *disappearance*, not price, killed the 11/11. Test: per-level flicker rate across all sessions, then whether high-flicker-anchored entries underperform. **Coordinate with the level-persistence agent — do not double-build.** | **FROZEN, not filed** |
| **PR-5 Runner giveback / tick granularity** | The runner leg systematically gives back a material fraction of its own peak (median **32.4%**; 7 of 11 scaled-out winners exited *below their own TP1*). First mechanism to test is **tick granularity, not trail width** — on this trade the stop sat at 0.552 and filled at 0.48 because the arm looks every 3 minutes. **Must be run over the FULL population, winners AND losers.** Not in the graveyard (not pre-TP1 lock, not BE-floor, not exit-all-at-touch, not take-profit-earlier) and does not change the runner cohort's exit *shape*. | **FROZEN, not filed** |

PR-1 through PR-5 were deliberately **not** written into `automation/overnight/queue.md` this session: multiple agents are editing that file concurrently and its per-line parser is L245/L246-fragile. They are frozen here, verbatim, with a git sha. **Filing them is the parent's call.**

One **non-hypothesis instrument** worth building because it is pure visibility and costs $0: log `source_core_row_ts` into every fleet decision row, so PR-3 stops requiring a timestamp-race reconstruction.

---

## 6. The standing capability, and its number

Winner autopsy is now an **organ, not a one-off.** `setup/scripts/winner_autopsy.py` runs nightly as `Gamma_WinnerAutopsy` at **16:25 ET** (10 min after the loss-side `Gamma_TradeAutopsy`), verified registered *and* fired: `LastTaskResult=0`, LastRunTime 17:54 ET, fresh output, empty stderr. 34/34 guards green, all RED-proofed. Cost **$0** — pure Python, no LLM on any path. It is **descriptive-only by construction**: unlike the loss autopsy it never writes `hypothesis-queue.jsonl` and never appends to `queue.md`, so it *cannot* degrade the runner cohort. Surfaced in `firm_brief.py` under **"Winner autopsy (capture rate)."**

### CAPTURE RATE = 101.9%

| Measure | Value | What it means |
|---|---|---|
| **Realized, n=21 winners** | **$3,479.00** | real broker fills, 0 no-bars |
| Best **single fixed** policy (`all_out_at_tp1_100`) | $3,414.50 | one policy, applied to every trade |
| **Capture rate (headline)** | **101.9%** | **our shipped exits beat every menu policy** |
| *Disclosure:* per-trade-best (hindsight shape-picking) | 63.7% of $5,464.93 | not live-selectable |
| *Disclosure:* oracle (sell 100% at the post-entry high) | 26.3% of $13,234.00 | unachievable |
| Runner cohort | **7 of 11** scaled-out winners had the runner realize *below its own TP1*; median runner-leg giveback **32.4%** | the real recurring shape |
| Exit-leg attribution coverage | 86.1% (31/36 legs; 5 honestly unattributed) | |

**And here is the whole point of building the organ:** this trade alone reads **10.08% capture** against the day oracle and screams *"hold longer."* The population reads **101.9%** and says the opposite. **The anecdote and the book disagree, and the book wins.**

> **The single biggest caveat, printed on every report and on the brief line: this is a WINNERS-ONLY sample.** Every number is computed over trades that already won. A policy column answers *"what would this make on the trades our current exits happened to win"* — **not** *"what would this policy make."* Switching policy changes which trades win, and says nothing about the ~140 losers. **101.9% does not mean adopt the runner-up. A sub-100% reading would not mean adopt it either.**

---

## 7. What was held back

Four lanes were independently verified. **None was refuted. None returned MAJOR_GAPS.** One (the exit grid) came back **SOLID**; three came back **MINOR_GAPS**. The following claims from those three are **withdrawn, corrected, or downgraded**, and are **not** reported above as established:

| Claim | Status | Why |
|---|---|---|
| "SIP premarket low = 744.02; the level file's `INTRADAY_PML` shows a label-vs-measurement gap; J's 742.97 reconciles to no feed" | **WITHDRAWN — refuted, corrected in §2.1** | I re-pulled SIP 5m myself this session: the premarket low is **742.79** at the 08:40 ET bar. 744.02 was only the 04:00 bar's low. The level file's 09:28 `INTRADAY_PML` read **742.79 — exactly right**. J's 742.97 is a real premarket print (08:55 ET bar low), $0.18 off the extreme. The accusation against the level file was wrong. |
| "743.25's value is identical in the 08:35 / 09:30 / 12:00 / 15:50 snapshots" | **WITHDRAWN** | 743.25 is **absent entirely** from `1200.json`. Three of four snapshots were actually checked; the fourth was asserted — and it is precisely the one where the level was missing, which *corroborates* the competing flicker finding rather than the stability claim. |
| "180 s of latency is caused by the 3-minute fleet cadence" | **DOWNGRADED — recast in §2.1** | The fleet **did** tick at 12:16:02.508 and logged "no qualifying setup" 0.45 s after the core scored 11/11. `build_shared_signal` reads the last-written core row; the `bold` row landed at 12:16:03. The elapsed 180 s is right; the mechanism is a **sub-second write/read race that forfeited a cadence slot**, not the cadence itself. |
| "Under the actual rules, strike 744 pays +$180" | **RECLASSIFIED AS ORACLE** | No rule produces a 12:43 exit for 744. With no TP1 the chandelier never arms (`arm_scope=post_tp1`), so the runner stop stays at the catastrophe level and the 12:43 exit time is **imported from the 746 trade's timeline**. It is convention-truncated, not rule-generated. (The truncation *understates* 744 — it was still rising.) Not used in §2.2's headline table, which is honestly labelled frozen-clock. |
| "A 0.15 trail would have been worth ~+$18 on this trade" | **CORRECTED to +$16.00** | The $18 mixed frames (0.59 ask vs 0.50 bid). Frame-consistent bid-to-bid with the same observed 2¢ slippage gives **$0.08/ct = $16.00**. ~12% overstatement; sign and conclusion unaffected. §3 uses $16.00. |
| "The $0.40 equity delta is fees" | **HELD BACK — unsourced** | The only unverified assertion in an otherwise fully-sourced lane. Immaterial in magnitude; not repeated above. |
| "'Hold longer' policies = −$451.50, the WORST column — **two** independent policies" | **DOWNGRADED to ONE policy** | `trail_only_no_tp1` is **mathematically identical** to `hold_to_time_stop` on **21 of 21** trades: with `profit_lock_arm_scope=post_tp1` and `tp1_premium_pct=999`, the trailing lock can **never arm**. The 7-policy menu delivers **6** distinct policies. The −$451.50 is real but rests on **one unprotected-hold shape counted twice**. **The most interesting cell for J's actual question — "hold longer *with* protection" — was never tested.** (Testing it requires pre-TP1 arming, which is itself graveyard — a defensible exclusion that should have been *stated*, not silently produced as a duplicate row.) This is a C14 dead-knob in a module whose own docstring cites L248/L234. |
| "Capture-vs-best-policy is the one number not contaminated by hindsight" | **SOFTENED** | The policy is uniform across trades (no per-trade shape-picking), but *which* policy is best is still selected in-sample. The bias runs **conservative** — beating even the ex-post best uniform policy is a stronger statement, not a weaker one — so 101.9% is not inflated. The absolute phrasing was. |

**One live bug surfaced and left unfixed (out of scope, flagged here so it does not get lost):** `setup/scripts/firm_brief.py:448` appends the *winners-only* caveat to the **loss** autopsy's `NO_BARS` branch, where it is factually wrong and would mislabel a genuine degraded-data alert. Copy-paste leak; no test covers that branch.

**What survived verification untouched:** every fill, every timestamp, every score component, the strike derivation, all five OPRA strike prices, the capture-rate arithmetic, the 4-component giveback decomposition, the ribbon diagnostic, the two-trades correction, and the entire 46-cell grid (which one verifier re-ran and reproduced **byte-for-byte**).

---

## 8. Spoken summary — morning brief

> The twelve-nineteen call was a good trade and it closed cleanly, but not the way you remember it. The runner was already flat at twelve forty-three on the trailing stop — the one-forty-five thing you're thinking of was a second, separate trade that afternoon, and that one lost eighty dollars.
>
> Take-profit made ninety-seven percent. The runner only made forty-five. That gap was mostly the trail doing exactly what it's designed to do — but fourteen dollars of it was us setting a stop at fifty-five cents and then not looking at the position again for three minutes. We filled at forty-eight.
>
> On the strike: it picked seven-forty-six for one reason — the account was seventy-six dollars over an equity boundary. The other two arms sat below it, picked seven-forty-seven, and got refused by the thirty-cent premium floor. Seven-forty-six was the best strike we could actually buy.
>
> Your morning-high idea is real. Seven-forty-six-thirty was the opening high, it was sitting in our own level file, and holding to it would have paid four-thirty instead of one-twenty-six. But price didn't get there until one twenty-seven — forty-four minutes after we were out — and a naive version of that rule would have picked the wrong level and made less than we did.
>
> I checked whether "hold longer" generalizes. On this one trade it's worth another eight hundred fifty-nine dollars. Across all twenty-one winners it loses four hundred fifty. So I'm not touching the exits.
>
> Winner autopsy is a nightly job now, same as the loss one. Capture rate is a hundred and one point nine percent across twenty-one winners — our shipped exits are beating every fixed policy I can test. That number is winners-only, so don't over-read it. Five hypotheses are frozen and pre-registered; none of them are armed.

---

### Source ledger

| Fact class | Source |
|---|---|
| Fills (broker truth) | `automation/state/fills-ledger.jsonl` — re-read cold this session, all 8 risky-3/safe-3 rows quoted |
| Entry decision + 9 hold ticks + both exits | `automation/state/fleet/risky-3/decisions.jsonl` |
| Score decomposition, blockers, `levels_active`, ribbon | `automation/state/core-decisions.jsonl` |
| Filter definitions | `backtest/lib/filters.py#evaluate_bullish_setup`, `detect_level_reclaim`, `detect_confluence` |
| Confluence self-match mechanism | `setup/scripts/heartbeat_core.py#_read_levels` |
| Strike + sizing path | `automation/state/fleet/fleet_executor.py#_tiers_for_arm`, `#_apply_recency_min_sizing`; `crypto/lib/strike_selection.py#V15_BOLD_TIERS`, `#pick_strike` |
| Exit rules that fired | `automation/state/fleet/exit_manager.py#plan_exit_actions`; `automation/state/fleet/strategies.py#RIBBON_RIDE`; `automation/state/fleet/accounts.json` risky-3 `exit_patch` |
| Level provenance + as-of snapshot | `automation/state/key-levels-history/2026-07-31/{0835,0930,1200,1550}.json` |
| Option prices | real OPRA 1-min trade bars via `mcp__alpaca__get_option_bars` (feed `opra`); local `backtest/data/options/SPY2607*.csv` |
| SPY tape + premarket low correction | Alpaca SIP 1m/5m, re-pulled and converted UTC→ET in this session |
| Full 46-cell grid | `analysis/recommendations/exit-grid-n1-2026-07-31-746c.json` |
| Level-target pre-registration | `analysis/recommendations/level-target-exit-prereg-2026-07-31.json` |
| Tick-by-tick narrative | `analysis/deep-research/WINNER-AUTOPSY-2026-07-31-1219.md` |
| Standing capability | `setup/scripts/winner_autopsy.py`, `analysis/winner-autopsies/all.{md,jsonl}`, `automation/state/winner-autopsy-last.json` |
| Commits | `fb6c1dc6` (exit grid + pre-reg), `64dbe42f` (tick narrative), `45d0dc34` (winner autopsy organ) — all pathspec-scoped, none pushed |
