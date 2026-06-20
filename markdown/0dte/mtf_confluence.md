# MTF_CONFLUENCE — Strategy Spec

> Status: **DRAFT — WATCH-ONLY per OP 21**. Backtest scheduled by J's call (not running tonight). Not auto-tradable.
> Numeric values are NOT canonical here — they live in [`automation/state/params.json`](../automation/state/params.json) once promoted.
> Hard rules + operating principles inherited from [`CLAUDE.md`](../CLAUDE.md).
> Mirrors the Setup Template in [`markdown/0dte/playbook.md`](markdown/0dte/playbook.md) and the spec format of [`markdown/0dte/vwap_rejection_prime.md`](markdown/0dte/vwap_rejection_prime.md) and [`markdown/0dte/opening_drive_fade.md`](markdown/0dte/opening_drive_fade.md).
> Source-thesis anchor: [`markdown/planning/FUTURE-IMPROVEMENTS.md#6`](../markdown/planning/FUTURE-IMPROVEMENTS.md) — "Multi-timeframe confirmation (5min + 15min ribbon)".

**Setup name:** MTF_CONFLUENCE
**Direction:** PUTS (bearish stack on BOTH timeframes) or CALLS (bullish stack on BOTH timeframes) — fires both sides symmetrically
**Status:** DRAFT (WATCH-ONLY)
**Date created:** 2026-05-13
**Author:** Gamma (architect agent)

---

## 1. Setup name + 1-line summary

**MTF_CONFLUENCE** — The 5-minute EMA ribbon AND the 15-minute EMA ribbon are stacked in the SAME direction with adequate spread (≥30¢ on 5m, ≥50¢ on 15m), price is testing a named ★★+ key level within proximity, volume confirms ≥1.3× 20-bar average, and the trigger bar prints a directional body → enter ITM-2 0DTE in the ribbon direction.

---

## 2. Thesis

**Mechanism — HTF agreement filters false positives.** The 5-minute ribbon flips frequently during intraday chop; many of v14's losing days (5/05, 5/06, 5/07) show the 5m ribbon momentarily stacking against a higher-timeframe reality, generating signals that immediately reverse. The 15-minute ribbon is structurally slower — it requires roughly 3× more directional energy to flip — so when the 15m AND 5m agree, the signal is anchored to a regime, not a wobble. The intuition is the same one behind multi-timeframe analysis in classical TA: lower-timeframe noise is filtered by higher-timeframe trend.

**Existing v14 wiring.** The current bearish ribbon-ride evaluator already uses 15m HTF stack as a **score modifier** (a soft +1 to quality when 15m agrees, see `lib/filters.py#htf_confirmation_score`). MTF_CONFLUENCE promotes this from a soft additive bonus to a **HARD GATE** — no agreement, no trade. Per OP 17 (first-try shipping + 3-of-3): the spec defines the gate cleanly, the backtest tells us whether it pays.

**Why ITM-2 vs ATM/OTM.** ITM-2 has higher delta (~0.55–0.65), lower theta sensitivity, tighter bid-ask, and survives chop better than OTM. Inherited from SNIPER + seed10095 doctrine — backtest will confirm carryover.

**Which J trades it would have caught (anchor analysis).**

| J trade | 15m ribbon at trigger time | 5m ribbon at trigger time | Level confluence? | MTF would catch? |
|---|---|---|---|---|
| **2026-04-29 SPY 710P (+$342)** | Bear-stacked, spread > $0.60 | Bear-stacked, spread > $0.35 | 711.40 trendline (★★★) | **YES — high-confidence catch.** |
| **2026-05-01 SPY 721P (+$470)** | Bear-stacked on leg 2 (AM gap had not yet propagated to 15m on leg 1) | Bear-stacked both legs | 720.50 prior-day low (★★) | **YES — leg 2 only**, not the anticipation leg 1. |
| **2026-05-04 SPY 721P (+$730)** | Bear-stacked, spread > $0.55 | Bear-stacked, spread > $0.40 | Multi-day trendline (★★★) | **YES — ELITE tier confluence.** |
| 2026-05-05 SPY 722P (−$260) | Compressed (spread < $0.30 — chop signature) | Briefly bear-stacked then flipped | None ★★+ within $0.30 | **SKIP — 15m spread gate rejects.** |
| 2026-05-06 SPY 730P (−$300) | Bull-stacked (DISAGREES with 5m bear flip) | Briefly bear-stacked | None ★★+ within proximity | **SKIP — HTF disagrees with LTF.** |
| 2026-05-07 SPY 734C (−$45) | Pre-FOMC compression | 5m flipped late then reversed | None | **SKIP — macro veto + HTF compression.** |
| 2026-05-07 SPY 737C (−$120) | Pre-FOMC compression | Bullish anticipation entry | None | **SKIP — anticipation forbidden + HTF compression.** |

**Edge-capture target (per OP 16):** ≥ $771 on J winners (50% of $1,542 floor). Stretch: $1,542 (full). HTF gate is expected to reduce trade count by ~40-50% vs 5m-only — the bet is that what survives is materially higher-expectancy.

---

## 3. Trigger conditions (ALL required)

A signal fires on a 5-minute SPY bar (closed) when **every** one of the 8 conditions below is true:

1. **5m ribbon stack + spread:** EMA ribbon on 5m matches direction with `spread_5m ≥ ribbon_5m_min_spread_cents` (default $0.30). Bears: `Fast EMA < Pivot EMA < Slow EMA`. Bulls: `Fast EMA > Pivot EMA > Slow EMA`.
2. **15m ribbon stack + spread (THE HARD GATE):** EMA ribbon on 15m matches the SAME direction with `spread_15m ≥ ribbon_15m_min_spread_cents` (default $0.50). Computed from the most-recently CLOSED 15m bar (no peeking — see §3a). Disagreement OR sub-threshold spread = REJECT.
3. **Level proximity:** `min(|spot − level.price|) ≤ proximity_dollars` (default $0.30) where `level` ∈ `today-bias.json` AND `level.strength ≥ ★★` (2+ stars). Lone-star levels and round-numbers-only do NOT qualify (OP 5).
4. **Volume confirmation:** `current_bar.volume ≥ vol_mult × avg(prior 20 bars volume)` (default `vol_mult` = 1.3).
5. **Body commitment:** trigger bar's body `abs(close − open) ≥ body_min_cents` (default $0.10). Pure wicks (doji at level with no body commit) = REJECT — wicks are awareness, not triggers (OP 6).
6. **Time gate:** `bar_time ∈ [10:00 ET, 14:00 ET) ∪ [15:00 ET, 15:35 ET)` — inherits v14's 10:00 entry gate AND v14's 14:00–15:00 no-trade window.
7. **Macro veto inheritance + VIX confirmation:**
   - If `today-bias.json` macro flag is HARD VETO (event ≤ 120 min counter-trend), SKIP.
   - PUTS → VIX rising OR VIX > 17.30 (params.json `vix_bear_threshold`).
   - CALLS → VIX falling OR VIX < 17.20 (params.json `vix_bull_low_threshold`) AND VIX < 22.0 (`vix_bull_hard_cap`).
8. **Per-day guards:**
   - No current 0DTE leg open (one-and-done per direction per day).
   - First-entry-after-stop: if a prior MTF_CONFLUENCE leg today already stopped out, NO RE-ENTRY today.
   - Daily-loss budget remaining > planned $-risk (Rule 5 inheritance).

**Anticipation entries are forbidden** (Rule 2). All 8 conditions must have JUST printed on the most-recently CLOSED 5m bar. The 15m bar referenced in condition 2 must be the most-recently CLOSED 15m bar at the time of the 5m close.

### 3a. 15m bar discipline (anti-lookahead)

When a 5m bar closes at, say, 10:35 ET, the most-recent CLOSED 15m bar is the one that closed at **10:30 ET** (NOT the still-forming 10:30–10:45 bar). The evaluator MUST use the prior-closed 15m bar — pulling an in-progress 15m bar is lookahead bias and is the kind of mistake that kills regime-robustness. This is enforced via `htf_bar_closed_ts <= ltf_bar_open_ts` in the trigger code. Cross-reference [`markdown/doctrine/LESSONS-LEARNED.md`](../markdown/doctrine/LESSONS-LEARNED.md) for the lookahead-bias anti-patterns.

---

## 4. Direction logic

| 5m ribbon stack | 15m ribbon stack | Spread gates pass? | Level proximity met? | Resulting direction |
|---|---|---|---|---|
| Bear (`Fast < Pivot < Slow`) | Bear (`Fast < Pivot < Slow`) | Yes (5m ≥ 30¢, 15m ≥ 50¢) | Yes | **PUT** |
| Bull (`Fast > Pivot > Slow`) | Bull (`Fast > Pivot > Slow`) | Yes (5m ≥ 30¢, 15m ≥ 50¢) | Yes | **CALL** |
| Bear | Bull | — | — | **SKIP — disagreement.** |
| Bull | Bear | — | — | **SKIP — disagreement.** |
| Bear | Bear | 15m spread < 50¢ (compressed) | — | **SKIP — HTF compression = chop signature.** |
| Bull | Bull | 15m spread < 50¢ (compressed) | — | **SKIP — HTF compression.** |
| Bear or Bull | Same | Spreads OK | No ★★+ within $0.30 | **SKIP — no level anchor.** |

**Tie-break:** there is no tie. The gates are AND-conjoined — a single FAIL ⇒ SKIP. The setup is intentionally narrow per the thesis (fewer trades, higher quality).

---

## 5. Strike + size

- **Strike rule:** ITM-2 (params.json `strike_offset_itm` = 2):
  - PUTS: `strike = round(spot) + 2`
  - CALLS: `strike = round(spot) − 2`
- **DTE:** 0
- **Order type:** limit at mid; reassess in 30s if not filled.
- **Premium ceiling:** ≤ $3.30. If exceeded, fall back to ITM-1 — log fallback in journal.
- **Size (v13b sizing tiers, mirrors `params.json#position_sizing_tiers`):**

| Account equity | base_qty | elite_qty | Structure |
|---|---|---|---|
| $0 – $2,000 | **3** | **3** | 2 TP1 + 1 runner (capital constraint; no upsize) |
| $2,000 – $10,000 | **5** | **8** | 3 TP1 + 1 conservative + 1 aggressive runner |
| $10,000+ | **10** | **15** | 6 TP1 + 2 conservative + 2 aggressive runners |

**Quality tier:**
- **ELITE** if ALL of: (a) 15m spread ≥ $0.80 (strong HTF conviction), (b) 5m spread ≥ $0.50, (c) the anchoring level is ★★★ (3-star), (d) volume ratio ≥ 1.6× (not just the 1.3× threshold). All four = ELITE.
- **BASE** otherwise (gates passed but one or more above conditions short of ELITE).

**Liquidity gate** per `params.json#_liquidity_gate_section` applies (bid-ask spread ≤ 8c or ≤ 10% of mid; |delta| ∈ [0.30, 0.55]; OI ≥ 500). ITM-2 0DTE on SPY clears these comfortably during RTH.

---

## 6. Exits

### Premium stop (initial)
- **Default:** `−8%` of entry premium (params.json `premium_stop_pct`).
- **Rationale:** HTF gate filters out chop-day signals — −8% is appropriate because surviving trades should be regime-aligned and the wobble window is narrower than 5m-only setups.

### TP1
- **Trigger:** premium ≥ entry × 1.30 (+30%) OR SPY reaches first major chart level past entry from `today-bias.json`.
- **Size:** sell `tp1_qty_fraction = 0.667` (2 of 3 contracts at minimum-size; mirrors sniper).

### Profit-lock (per J's 2026-05-12 rule)
- **Arm at:** `favor_premium ≥ entry × 1.10` (+10%).
- **Action when armed:** raise stop to `entry × 1.05` (+5%). Stop NEVER lowers below original −8%.
- **Effect:** once a trade ticks +10%, it can no longer go negative.

### Runner (after TP1 fires)
- **Stop:** breakeven (entry premium).
- **Target:** `runner_target_pct = 1.5` (premium ≥ entry × 2.5 = +150%).
- **HTF-disagree exit:** runner sells if the 15m ribbon flips against direction with spread ≥ $0.30 — HTF re-statement of intent terminates the thesis cleanly.
- **5m ribbon-flip exit (intermediate):** if 5m ribbon flips with spread ≥ $0.30 but 15m still agrees, TIGHTEN runner stop to prior 5m bar's extreme (no full exit).
- **Hard cap:** premium ≥ entry × 3.0 → market sell.

### Time stop
- 15:50 ET hard flatten (params.json `time_stop_et`).

### Fallback (small-trade catcher)
- If runner-exit signal fires BEFORE TP1 → exit ALL contracts at signal price.

---

## 7. Knob grid for Stage 1 backtest (~864 combos)

| # | Knob | Values | Count |
|---|---|---|---|
| 1 | `vol_mult` | 1.1, 1.3, 1.5 | 3 |
| 2 | `proximity_dollars` | 0.20, 0.30, 0.40 | 3 |
| 3 | `htf_min_spread_cents` | 30, 50, 70, 90 | 4 |
| 4 | `body_min_cents` | 0.05, 0.10, 0.15 | 3 |
| 5 | `premium_stop_pct` | −0.06, −0.08, −0.10 | 3 |
| 6 | `tp1_premium_pct` | 0.20, 0.30, 0.50 | 3 |
| 7 | `runner_target_pct` | 1.0, 1.5, 2.0 | 3 |
| 8 | `profit_lock_threshold_pct` | 0.08, 0.10, 0.15 | 3 |

**Combo count:** 3 × 3 × 4 × 3 × 3 × 3 × 3 × 3 = **2,916 combos.**

That's above the 864 budget. Stage 1 will use the **reduced grid** by collapsing two of the wider sweeps to a coarser pass first, then expand the winners in Stage 2 per OP 19 (self-healing/self-improving pipeline):

**Stage 1a (coarse — ~864 combos):**

| Knob | Stage 1a values | Count |
|---|---|---|
| `vol_mult` | 1.1, 1.3, 1.5 | 3 |
| `proximity_dollars` | 0.20, 0.30, 0.40 | 3 |
| `htf_min_spread_cents` | 30, 50, 80 | 3 |
| `body_min_cents` | 0.05, 0.10 | 2 |
| `premium_stop_pct` | −0.06, −0.08, −0.10 | 3 |
| `tp1_premium_pct` | 0.20, 0.30, 0.50 | 3 |
| `runner_target_pct` | 1.0, 1.5, 2.0 | 3 |
| `profit_lock_threshold_pct` | 0.08, 0.10 | 2 |

**Stage 1a total: 3 × 3 × 3 × 2 × 3 × 3 × 3 × 2 = 972 combos.** (Close to the 864 envelope; matches VWAP_REJECTION_PRIME budget.)

**Stage 1b (refine):** the keepers from 1a feed Stage 1b, which sweeps the full 4-value `htf_min_spread_cents` and 3-value `profit_lock_threshold_pct` and `body_min_cents` grids around the survivors — total combos in 1b will be ≤ 1500 based on keeper count.

**Locked (NOT swept in Stage 1):**
- `ribbon_5m_min_spread_cents = 30` (per CLAUDE.md OP 12 ribbon-flip definition)
- `tp1_qty_fraction = 0.667`
- `strike_offset = +2` (ITM-2; OP 16 sim-accuracy gate)
- Time gate 10:00–15:35 ET excluding 14:00–15:00
- `qty = 3` (paper account binding constraint)
- 15m bar-closed enforcement (anti-lookahead, §3a)

---

## 8. Anchor floors (must catch / must skip)

### MUST catch (engine_pnl > 0)
- **2026-04-29 SPY 710P (+$342 J)** — Floor: engine_pnl ≥ $100 (≥ 30% of J).
- **2026-05-01 SPY 721P (+$470 J)** — Floor: engine_pnl ≥ $100 (leg 2 only; leg 1 must SKIP — HTF had not yet flipped).
- **2026-05-04 SPY 721P (+$730 J)** — ELITE tier. Floor: engine_pnl ≥ $250 (≥ 35% of J).
- **2026-05-12 J's reference winner** (placeholder for the 5/12 PROFIT-LOCK rule anchor) — Floor: per-trade profit-lock rule must arm at +10% and lock +5% floor. Hand-test verification: simulate a trade where the trade peaks at +12% then retraces to entry; engine must close at +5%, NOT at the −8% stop. This is a *behavioral* floor (per OP 17 unit-test-first), not a P&L number.

### MUST skip OR lose ≤ floor
- **2026-05-05 SPY 722P (−$260 J)** — Floor: engine_pnl ≥ −$50 (must SKIP via HTF compression / spread gate).
- **2026-05-06 SPY 730P (−$300 J)** — Floor: engine_pnl ≥ $0 (must SKIP — HTF disagreed with LTF).
- **2026-05-07 SPY 734C (−$45 J)** — Floor: engine_pnl ≥ $0 (macro veto must SKIP + HTF compression).
- **2026-05-07 SPY 737C (−$120 J)** — Floor: engine_pnl ≥ $0 (anticipation forbidden + HTF compression).

### Aggregate floors (per OP 16)
- `winners_capture` ≥ $450 (~30% of J's $1,542). Stretch: $771.
- `losers_added` ≤ $100 total.
- `edge_capture` = winners_capture − losers_added ≥ $350. Stretch: ≥ $700.

### Wide-window floors (per OP 14 + OP 19)
- `wide_pnl > 0` over 16-month backfill.
- `positive_quarters ≥ 4 of 6`.
- `top5_pct ≤ 0.50` (concentration disclosure per OP 20).
- `max_drawdown ≤ $1,500` (qty=3 paper assumption).
- `wide_wr ≥ 0.10` (per OP 14 hard floor — WR is awareness-only).
- `wide_n_trades ≥ 20` (statistical-power floor — HTF gate may reduce sample below this; promotion blocks if so).

---

## 9. Promotion path (per OP 21)

**ALL of the below required for live promotion:**

1. **Backfill grader (historical):** 3+ days where the watcher would have fired AND won (graded via `lib/watchers/watcher_grader.py` using OPRA fills, NOT just BS sim).
2. **Live observation (J co-witness):** 3+ live observations confirmed by J in real time.
3. **Full-backfill expectancy:** positive per-trade expectancy over the 16-month window.
4. **Per-confidence-tier expectancy positive:** BASE and ELITE each independently positive. ELITE must show ≥ 1.5× the BASE expectancy.
5. **Per-quality scorecard complement:** Pearson `|r| < 0.50` correlation with BEARISH_REJECTION_RIDE_THE_RIBBON daily P&L (complement, not cancel).
6. **6-disclosure scorecard** at `analysis/recommendations/mtf_confluence.json` per OP 20 (account-size, sample-bias, OOS, real-fills, failure-modes, concentration).
7. **J's explicit ratification.**

**Default watcher knobs during WATCH-ONLY phase:**
- `qty = 3`, `premium_stop_pct = −0.10`, `tp1_premium_pct = +0.30`, `runner_target_pct = 1.5`, `tp1_qty_fraction = 0.667`.
- Wider stop during WATCH because the watcher is logging, not trading — observation footprint should be conservative.

**Watcher implementation location (when built):** `lib/watchers/mtf_confluence_watcher.py`. Mirrors `lib/watchers/bullish_watcher.py` and `lib/watchers/orb_watcher.py` patterns. Daily replay via `Gamma_WatcherReplay` task at 17:00 ET.

---

## 10. Cost / runtime estimate for Stage 1

**Pure Python**, `multiprocessing.Pool(processes=4)` per OP 15. No LLM in loop.

**Per-combo cost considerations:**
- Standard 5m bar loop + BS pricing: ~35-50 s/combo (matches VWAP_REJECTION_PRIME baseline).
- **MTF overhead:** 15m bar lookup adds ~10% per bar (one extra timestamp join and ribbon recompute). Net: ~40-55 s/combo.

**Total runtime (Stage 1a — 972 combos):**
- 972 combos / 4 workers = 243 combos per worker.
- 243 × 50s ≈ **3.4 hours wall-clock.**
- Add data load (15m bars must be pre-computed and cached once) + scorecard write → **~3.7 hours total.**

**Stage 1b refine (~1500 combos):** ~5.5 hours wall-clock. Total Stage 1 (a + b): **~9 hours.**

**Dollar cost:** $0 (pure Python, no Claude calls in loop — per OP 11/13).

**Disk:**
- 15m bar cache: ~30 MB (one-time, reused across all combos and future strategies).
- Per-combo results: ~120 MB intermediate (Stage 1a + 1b).
- Final scorecards: ~8 MB.

**Output paths:**
- 15m bar cache: `backtest/data/cache/spy_15m_bars.parquet`
- Per-combo results (Stage 1a): `backtest/autoresearch/_state/mtf_stage1a/combos/*.json`
- Per-combo results (Stage 1b): `backtest/autoresearch/_state/mtf_stage1b/combos/*.json`
- Stage scorecard: `backtest/autoresearch/_state/mtf_stage1/scorecard.json`
- Top-5 keepers: `backtest/autoresearch/_state/mtf_stage1/keepers.json`

**Validation gate before Stage 2:** scorecard MUST disclose all 6 OP 20 items.

**Scheduling note:** Per J's instruction, Stage 1 is NOT running tonight. The pipeline is specified and ready; trigger via `Gamma_GrinderMonitor` only on J's explicit call.

---

## Appendix — Open questions (per OP 2 — speculative)

1. **(speculative — needs evidence)** The HTF gate may collapse trade count below the `wide_n_trades ≥ 20` floor, blocking promotion on statistical-power grounds. If Stage 1a returns `wide_n_trades < 20` for every combo, the spec is FALSIFIED — relax `htf_min_spread_cents` to 30¢ floor in Stage 1b ONLY IF the looser threshold preserves the 4-of-6 positive-quarters gate.
2. **(speculative — needs evidence)** 15m bar ribbon parameters (EMA lengths) inherited from the 5m parameters may not be optimal on the higher timeframe. Sweep of 15m EMA lengths deferred to Stage 1b expansion if needed.
3. **(speculative — needs evidence)** Anchored to ★★+ levels only — round-numbers explicitly excluded per OP 5. If Stage 1a shows the level-anchor filter is the dominant filter (rather than the HTF gate), the strategy is essentially a level-break play and should not be promoted as a distinct setup from SNIPER_LEVEL_BREAK. Discriminating analysis: P&L attribution per filter, computed in Stage 1a scorecard.
4. **Real-fills uncertainty.** BS sim is the Stage 1 evaluator; final ratification requires `simulator_real.py` cross-check (OP 20 disclosure #4).
5. **Correlation risk with v14 ribbon-ride.** Both setups use ribbon agreement — `|r| < 0.50` floor (promotion gate 5) may be tight. If correlation is too high, MTF_CONFLUENCE is a refinement of v14 rather than a novel setup, and should be merged into v14 as a "high-conviction-only" mode rather than promoted as a separate setup.
