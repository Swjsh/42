# SSR Battery — PRE-REGISTRATION (frozen before first grind)

> Authored 2026-08-07 (Fable, J-directed session). Spec source: [markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md](../../../markdown/research/SSR-PIVOT-LIQUIDITY-STRATEGY.md).
> Per the standing rule from PHASE1-swing-battery/RESULTS.md: this is a NEW pre-registered
> battery. Every knob below is FROZEN before the first run. No post-hoc grid additions.

## 0. Registry collision — disclosed up front

`STRATEGY-SPACE-REGISTRY.jsonl` closed `ohlcv_bar_pattern_mining_family` DEAD (2026-07-14,
reopen = "new NON-OHLCV data only"). SSR is facially OHLCV price-structure. This battery
proceeds as a **J-directed reopen petition**, on four named grounds:
1. **J's explicit directive today (2026-08-07)** to formalize and test a specific external
   practitioner's checklist — a named hypothesis with a prior (C32-compliant), not idle mining.
2. The prior kills' own carve-outs: RESULTS.md explicitly did NOT kill **intraday**
   expressions or structure-as-**trigger** compositions; SSR is intraday (15m) and a
   sweep→shift→retest **composition** never before tested here.
3. **New non-target-OHLCV feeds** enter the family: session-boundary (clock) levels,
   cross-asset VIX structure, Mag7 breadth (the latter two as shadow columns this round).
4. New instrument (GC) never touched by any prior futures battery (all were MES/MNQ).

The registry is NOT edited this session; the verdict row is appended only when this battery
lands, per convention. If J revokes the petition, this battery's outputs stand as research-only.

## 1. Hypothesis

At higher-timeframe liquidity levels, a **sweep beyond the level → market-structure shift
against the sweep → retest of the level** predicts reversal with positive after-cost
expectancy on futures (GC primary; NQ/ES secondary), superior to random-entry and
buy-and-hold-to-timestop nulls on the same dates.

## 2. Data (disclosed)

- yfinance (sanity-tier per `backtest/futures/data.py` doctrine — disclosed, this is a
  SMOKE battery, not multi-month validation): GC=F/NQ=F/ES=F 15m × 60d (2026-05-28..2026-08-07);
  GC=F 1h × 730d; ^VIX 15m×60d + daily×2y. Cached under `backtest/data/futures/ssr/` with a
  local provenance ledger. UTC → tz-aware America/New_York conversion directly (no wall-v1).
- **Exhibit contamination disclosure:** the strategy was formalized from a 2026-08-07 GC
  trade; 2026-08-07 is inside the smoke window. Headline stats are reported WITH and WITHOUT
  2026-08-07.

## 3. Definitions (frozen)

- Trading day: 18:00 ET (D−1) → 17:00 ET (D). Sessions: Asia 18:00–03:00, London 03:00–09:30,
  NY 09:30–17:00 ET. 4H blocks anchored 18:00 ET: 18/22/02/06/10/14 (last block 3h).
- Sweepable levels (extremes only): PDH/PDL, PWH/PWL, prev-completed-4H H/L, prior completed
  Asia/London/NY session H/L. Opens (day open, 4H open) are runner-target magnets only —
  NOT sweepable in v0.
- All levels causal: computed strictly from completed periods before the current bar.
- ATR = Wilder 14 on exec TF (`swing_sim.wilder_atr`). Zone band = k1×ATR around level.
- State machine: IDLE →(bar exceeds level by ≥ s×ATR then closes back through within N=2 bars)→
  SWEPT →(within M1=16 bars: opposing BOS via `crypto.lib.market_structure.walk_structure`
  (window=2), OR post-sweep LH/HL pivot, OR displacement bar ≥ d=1.5×ATR against the sweep)→
  SHIFTED →(within M2=16 bars: price re-enters zone band AND prints a reaction close in trade
  direction)→ SIGNAL at that close → **entry = next bar open**. Timeout at any stage → IDLE.
  Buy-side sweep of a high-type level arms SHORT; sell-side sweep of a low-type level arms LONG.
- Entry window: signal close 03:00–15:00 ET. Forced flat 16:55 ET same trading day (bars
  truncated at time-stop; `futures_sim` time-exits at last provided bar).
- Risk: stop = sweep extreme ± b×ATR (b=0.15). R = |entry−stop|. TP1 = 1.5R, qty 3,
  tp1_fraction = 2/3, stop→BE after TP1 (futures_sim doctrine). Runner = nearest opposing
  level beyond TP1 (any family incl. opens); fallback 3R if none within 5R.
- Concurrency: ONE open position per instrument at a time; signals arriving while a position
  is open are skipped and logged (skip count disclosed per cell).
- Fills/costs: `futures_sim.simulate_futures`, slippage 1 tick/side, round_turn_usd from
  `instruments.py` (ES/NQ/MES/MNQ); NEW local specs (not edits to shared instruments.py):
  GC point $100/tick 0.1/round-turn $6.00; MGC point $10/tick 0.1/round-turn $3.00.

## 4. Grid (FROZEN — 2×2 = 4 combos)

k1 (zone width, ATR mult) ∈ {0.25, 0.50} × s (sweep depth, ATR mult) ∈ {0.10, 0.25}.
Everything else fixed as §3. No other knobs exist in this battery.

- **Family A (smoke, 15m×60d):** {GC=F, NQ=F, ES=F} × {long, short} × 4 combos = **24 cells**.
  IS < 2026-07-20 ≤ OOS.
- **Family B (regime, GC=F 1h×730d):** {long, short} × 4 combos = **8 cells**.
  IS < 2026-01-01 ≤ OOS (battery convention OOS_CUT).

## 5. Statistics (2nd-gen battery conventions — `backtest/futures/battery.py`)

Per cell: n, WR, total/mean net (after costs), IS/OOS split, random-entry null (300 draws,
same session-window eligible bars, same exit shape) → `bootstrap_null_pvalue` (B=2000),
buy-and-hold-to-timestop null on the same entry bars (the discriminator that killed 2 of 3
prior seeds), drop-top-3 concentration, halves stability. BH-FDR (`battery.bh_fdr`,
alpha=0.05) within each family separately. MIN_OOS_N=5.

**Cell clears** iff: OOS n≥5 AND OOS mean>0 AND FDR survivor AND beats B&H null AND
drop-top-3 > 0. **Battery verdict: PASS if ≥1 cell clears, else KILL.** No WEAK rung.

Shadow columns (logged per trade, never gates in v0): vix_agree (VIX 15m structure opposite
trade direction), mag7_breadth (−7..+7 day-change count) — NQ/ES cells only.

## 6. On PASS / on KILL

- PASS → file candidate + build own-book forward shadow (Edge3Sim pattern; no broker, no live;
  Alpaca has zero futures). Arming bar mirrors the mirror-shadow bar: ≥20 forward round trips,
  positive expectancy, beats B&H null. LIVE arming is J-only (OP-0 #1), and note PROD-token
  rotation still owed.
- KILL → verdict row into the registry, lesson if a new failure shape appears, done. No
  knob-turning on this battery; any follow-up = new pre-registration.

Prior art cited: futures-swing-{rrw_short, e2_context, structure_bos_choch, rrw_rare}.json
(all KILL/INCONCLUSIVE), PHASE1-swing-battery DESIGN/RESULTS, mirror-shadow arming bar.

---

# SSR-v1 ADDENDUM — PRE-REGISTRATION (frozen 2026-08-07 ~17:00 ET, before any v1 run)

**v0 verdict stands: KILL (0/24 A, 0/8 B), scorecards `futures-ssr-{smoke,regime}.json`.**
v1 is a NEW battery testing exactly ONE hypothesis class — **level-definition fidelity** —
motivated by the pre-registered exhibit diagnostic, which found our causal PREV_4H_HIGH
(18:00-anchored) = 4380.1 at the exhibit moment while the practitioner's 4,429.8 line matches
a **20:00-ET-anchored (UTC-style) 4H block completing 08:00 ET** and/or a running session
extreme. No exit, stop, stat, or window knobs are opened.

## v1 changes (complete list)

1. **Running-extreme sweepable families** (opt-in `include_running=True`, v0 defaults
   untouched): RUN_DAY_HIGH/LOW (current trading day extreme over [day start, bar i−1]) and
   RUN_ASIA/LONDON/NY_HIGH/LOW (current session-so-far, same i−1 rule). Sweepable only once
   ≥8 bars of the period have elapsed. **Sweep reference locks at the pierce bar** (the
   running value as of the pierce bar's i−1) — the level must not chase price during the
   close-back/retest sequence. Opens stay non-sweepable.
2. **4H anchor knob** `h4_anchor ∈ {18:00 (v0), 20:00 (UTC-style)}` — applies to
   PREV_4H_HIGH/LOW + H4_OPEN only.
3. **Detector completeness fix** (v0 WARN): a bar that times out a stale episode AND itself
   qualifies as a fresh sweep now starts the new episode same-bar. The v0 adversarial test
   pinning the dropped behavior flips to pin the fixed behavior (documented change).

## v1 families (FROZEN)

- **A′ (smoke 15m×60d):** {GC=F, NQ=F, ES=F} × {long, short} × [h4_anchor {1800,2000} ×
  k1 {0.25,0.5} × s {0.10,0.25}] = **48 cells**. OOS cut 2026-07-20.
- **B′ (regime GC 1h×730d):** {long, short} × same 8 combos = **16 cells**. OOS cut 2026-01-01.
- Stats/ladder/exit shape: identical to v0 §5 verbatim. BH-FDR alpha=0.05 within each family.
  Outputs: `futures-ssr-v1-smoke.json` / `futures-ssr-v1-regime.json` + RESULTS.md v1 section.

## v1 diagnostics (report-only, never FDR cells)

Per-cell per-level-family breakdown (n/net by level_name); per-day funnel for the best 2
cells per family (day → sweeps → shifts → retests → trades → net); exit-reason attribution;
B&H-null direction semantics disclosed explicitly in RESULTS.md.

## v1 verdict rules

Same ladder. Additional pre-commitment: if NO v1 cell clears but ≥1 cell shows
(OOS n≥10 AND OOS mean>0 AND beats_bh AND drop_top3>0) — "PULSE" tier — the sanctioned next
step is a **forward own-book shadow ledger** (Edge3Sim pattern, watch-only, arming bar =
≥20 trips + positive expectancy + beats null), NOT another historical grind on sanity-tier
data. v0's Family-B best cell (GC short 0.5/0.1: OOS n=35, +$852/tr, beats_bh) already meets
PULSE; v1 decides which config the shadow runs.
