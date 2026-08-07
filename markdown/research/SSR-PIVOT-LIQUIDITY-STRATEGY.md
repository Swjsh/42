# SSR — Sweep → Structure-shift → Retest (pivot-liquidity reversal, futures-first)

> **Living doc** for the SSR strategy family. Origin: J-supplied screenshots 2026-08-07 of
> Instagram trader "Socrates Dimataris" — his 6-step entry checklist + a GCZ2026 short he
> posted the same day. Extraction + autopsy authored by Gamma from the images (subagents
> never saw them; this doc is the source of truth for the ruleset).
> Status: **RESEARCH → spec → backtest smoke. Nothing armed. Paper/shadow only.**

---

## 1. The 6-step checklist (extracted verbatim-in-substance from the screenshots)

**Step 1 — Establish Market Context.** Before looking for entries, identify where price is
trading on the higher timeframes: Major Supply, Major Demand, Previous Highs, Previous Lows,
Support, Resistance, Weekly/Daily/4H Pivot Zones. These areas are where institutions are most
likely to create liquidity events. Question: *Is price approaching an important area? If not —
no trade.*

**Step 2 — Wait for Liquidity.** "I never chase breakouts." Wait for price to move beyond the
nearest pivot zone: break above resistance / below support, sweep previous highs/lows, push
through supply/demand. This move is designed to trigger stops and lure breakout traders in.
*Liquidity must be taken first.*

**Step 3 — Wait for Market Structure to Shift.** After liquidity is taken, need proof the move
is failing: Higher Low after a sell-side sweep; Lower High after a buy-side sweep; break of
the opposing structure; strong displacement away from the liquidity grab. *Without a structure
shift — no trade.*

**Step 4 — Trade the Retest.** Never enter during the sweep. Wait for price to return to the
area institutions defended. The retest provides: lower risk, better reward, confirmation that
liquidity has already been collected. *Trade the reaction off the retest — not the initial move.*

**Step 5 — Confirm with the VIX** (index trades). Only take trades when Nasdaq and VIX show
inverse agreement. Long Nasdaq: VIX is selling AND VIX rejects a resistance/pivot/magnet zone,
while Nasdaq has completed its sweep + structure shift + retest. Short Nasdaq: mirror image
(VIX buying from demand/support). Extra nuance: **the VIX itself should be reacting from an
important technical level** — "if it's in the middle of nowhere, its signal carries less weight."

**Step 6 — Follow the Money** (index trades). Final confirmation = market leadership (Mag 7:
AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA). Buying Nasdaq → want broad strength across
leaders; selling → broad weakness. Leaders disagree → *reduce size or pass*. "The indexes
rarely sustain directional moves without participation from their largest weighted components."

Steps 1–4 are the engine. Steps 5–6 are instrument-scoped confirmation filters (equity
indices only — N/A for gold).

---

## 2. Trade autopsy — his GCZ2026 short (2026-08-07)

From the two chart screenshots (TradingView mobile, 15m, GCZ2026 = Dec-26 COMEX gold):

- **Levels on his chart** (session-levels indicator): Prev 4H High / New York High ≈ **4,429.8**;
  4H Open ≈ 4,410; New York ≈ 4,381; Asia ≈ 4,378; Prev Day ≈ 4,363; Prev 4H Low ≈ 4,362;
  London ≈ 4,355 / 4,341.
- **Sequence:** overnight rally into the Prev-4H-High/NY-High confluence → tall green candle
  **spikes above the level and closes back off it (buy-side sweep, Step 2)** → lower highs form
  + displacement down (Step 3) → short entered at the zone retest; position tag shows
  **−25 contracts @ ~4,429.8**.
- **Exit:** "Market order executed on GCZ6 — Buy 25 at 4,392.9" (~09:37 chart time).
- **P&L math checks out:** 4,429.8 − 4,392.9 = 36.9 pts × $100/pt × 25 = **$92,250** ≈ the
  +$90,250 shown (fees/partial-fill drift). The screenshot is internally consistent.

**Honest caveats (no-oversell):**
- 25 full-size GC contracts ≈ **$11M notional / ~$300–600K margin**. The *edge shape* is
  replicable; the *dollars* are a function of his account size, not the setup. Our lane is
  MGC ($10/pt) / MES-scale.
- A TradingView execution toast can be a paper account. Unverifiable, and irrelevant: we judge
  the mechanism by OUR backtest + forward shadow, never by a screenshot.
- One posted winner = survivorship display. The checklist is what we're testing, not his P&L.

---

## 3. Why this fits our rig (the load-bearing observation)

Steps 1–4 are **J's own dictated market philosophy (2026-07-28)** almost verbatim: supply/demand
zones → wait for the return → structure shift at the zone → never chase candles. Our
`crypto/lib/market_structure.py` (HH/HL/BOS/CHoCH) is the exact chassis Step 3 needs, and the
futures chassis (`backtest/futures/`: sim, runner, exit manager, mirror-shadow forward path)
already exists from the futures revival program. SSR = J's philosophy + a session-level library
+ two new confirm filters. Futures leg kills theta — the reason J wants this lane.

---

## 4. SSR v0 — formal spec (pre-registered)

**Instruments:** GC=F (primary — matches the exhibit), NQ=F, ES=F. Execution sizing lane =
micros (MGC/MNQ/MES). **Execution TF:** 15m (his chart). **Context TF:** 4H + daily + sessions.
**Variant B (regime test):** 1h execution / daily-week levels over 730d history.

**Level families (Step 1)** — all computed ONLY from completed prior periods (no look-ahead):
`prev_day_high/low`, `prev_4h_high/low`, session highs/lows (Asia, London, New York — prior
completed sessions), `prev_week_high/low`, `4h_open`, `daily_open`. Levels are **ZONES** per
J doctrine: band = `k1 × ATR(14, exec TF)`, k1 ∈ {0.25, 0.5}.

**State machine (per instrument, one position max):**
1. `IDLE → SWEPT`: bar trades ≥ `s × ATR` beyond a level (s ∈ {0.1, 0.25}) then **closes back
   through it** within `N` bars (N ∈ {1, 2, 3}). Direction: buy-side sweep (above a high-type
   level) arms SHORT; sell-side sweep arms LONG.
2. `SWEPT → SHIFTED`: within `M1` bars (M1 ∈ {8, 16}), market_structure confirms: opposing
   BOS on exec TF, OR post-sweep lower-high (short) / higher-low (long) pivot, OR displacement
   candle ≥ `d × ATR` away from the grab (d ∈ {1.5, 2.0}).
3. `SHIFTED → ENTRY`: price **returns into the zone band** (retest) within `M2` bars
   (M2 ∈ {8, 16}) and prints a reaction close in trade direction inside/at the band →
   **enter next bar open** (C6 entry-bar convention).
4. Timeout at any stage → back to `IDLE`. No entry during the sweep itself, ever.

**Risk (chart-stop doctrine):** stop = sweep extreme ± `b × ATR` (b ∈ {0.1, 0.25}).
TP1 = 1.5R (bank majority), runner to next opposing session/day level; stop-first same-bar
tie-break (pessimistic). Session time-stop: flat by session close (no overnight in v0).

**Filters (SHADOW COLUMNS in v0, never gates):** VIX inverse agreement (15m VIX structure
opposite to index direction + VIX at its own level) — NQ/ES only; Mag7 breadth ≥5/7 same
direction on day-change — NQ/ES only. Logged per-trade for later A/B; gating them in v0 would
be an unvalidated Claude-invented lock (forbidden).

**Fills realism:** entry at next-bar open ± 1 tick slippage; commissions per side per the
futures chassis convention. All timestamps ET via `et_frame` discipline (yfinance returns UTC).

**Validation ladder:** (1) 60d/15m smoke across GC+NQ+ES with the pre-reg grid — kill if
expectancy ≤ 0 after friction on the MAJORITY of the grid (isolated-cell wins don't count, C4);
(2) 730d/1h regime pass on GC — sub-window stability; (3) OOS split + WF per BACKTESTING-PLAYBOOK;
(4) survivor → **mirror-shadow forward** per the futures program (no live money; J holds arming).
Grid is FROZEN as written above before first run — no post-hoc knob additions.

---

## 5. What the codebase map found (2026-08-07, 6-reader workflow)

- **Reusable as-is:** `crypto/lib/market_structure.py` (walk_structure = authoritative BOS/CHoCH,
  TF-agnostic, no-look-ahead proven by `test_swing_seeds.py`); `futures_sim.simulate_futures`
  (bracket fills, stop-before-target, BE-after-TP1, slippage+commission); `swing_sim.wilder_atr`;
  `battery.py` bh_fdr + bootstrap null (2nd-gen conventions, alpha=0.05); `commit_scoped.py`.
- **Net-new builds:** session-boundary levels (Asia/London/NY — nothing timezone-segmented
  existed anywhere), futures-scale sweep detector (existing `_detect_swept_levels` is
  SPY-cents-scoped), the sweep→shift→retest composition itself (three ingredients existed,
  never joined), GC/MGC instrument specs, Mag7 breadth fetch.
- **Doctrine collision, adjudicated:** `ohlcv_bar_pattern_mining_family` registry-closed DEAD
  2026-07-14. This battery runs as a J-directed reopen petition (grounds in
  [DESIGN.md §0](../../backtest/futures/analysis/SSR-battery/DESIGN.md)); prior kills' own
  carve-outs (intraday, trigger-mode) make SSR a new test, not a re-litigation. Bar stays
  brutal: must beat buy-and-hold null (the exact discriminator that killed 2 of 3 prior seeds).
- **Execution reality:** Alpaca has zero futures; Tastytrade path dormant + WATCH_ONLY until
  J rotates PROD tokens; mirror-shadow arming bar today: 48 trips, +$6,068, but
  beats_null=false → armable=false. SSR on PASS goes to own-book forward shadow
  (Edge3Sim pattern), nothing live.

## 6. How to PRACTICE this (J-facing)

### Lane 1 — TV Bar Replay drill (your Plus plan; intraday replay verified for dojo work)

One rep ≈ 10 minutes. Do 3–5 reps a sitting; log every rep.

1. **Setup:** GC (or NQ) 15m chart, your session-levels indicator on. Pick a random past
   day you haven't seen (avoid the last week — you'll remember it). Start Bar Replay at
   **18:00 ET the prior evening** so the overnight levels build honestly.
2. **Step to 07:00 ET, then pause and write the Step-1 context BEFORE advancing:** which
   levels are overhead/underneath, where's the nearest liquidity pool, is price approaching
   an important area? **No level nearby = no-trade rep — say it out loud and score the rep
   on whether you actually stood down.**
3. **Advance bar by bar.** Call each stage OUT LOUD as it forms (this is the discipline
   being trained): "sweep" (pierce + close back), "shift" (LH/HL, opposing break, or
   displacement), "retest" (return to the zone). Only after all three: state entry, stop
   (beyond the sweep extreme), TP1 (1.5R), runner target — THEN advance and watch.
4. **Score the rep** (journal, one line each): setup present? all 3 stages confirmed before
   entry? entered during the sweep (violation)? stop honored? outcome in R.
   Chasing the sweep or entering pre-shift = failed rep **even if it made money** (process
   > P&L, same as live).
5. **Weekly review:** count reps, % rule-clean, avg R on clean vs dirty reps. If clean reps
   don't out-earn dirty ones over ≥30 reps, that's evidence worth bringing to the battery.

### Lane 2 — machine practice (forward shadow, spec)

On PULSE/PASS from v1: own-book watch-only ledger (Edge3Sim pattern — no broker, prices
off live yfinance quotes) running the surviving config on GC 1h and/or 15m; every signal →
synthetic entry/stop/TP1/runner + exit management identical to the battery sim; ledger →
`automation/state/futures/ssr-shadow-*.jsonl`; arming bar = mirror-shadow's (≥20 closed
round trips + positive expectancy + beats same-horizon B&H null); scheduled task in the
Gamma_FuturesMirror pattern. **Real-money arming = J only** — and futures have no live
broker path anyway until the Tastytrade tokens rotate (or a new broker is approved).

## 7. Session log

- 2026-08-07: doc created; extraction + autopsy + v0 spec pre-registered. Data probe: yfinance
  GC/NQ/ES/MES/MGC 15m×60d + GC 1h×730d + ^VIX 15m×60d/daily×2y all available, $0. Map
  workflow (6 readers) done; pre-registration frozen at
  `backtest/futures/analysis/SSR-battery/DESIGN.md`.
- 2026-08-07 (later): **v0 battery KILL** (0/24, 0/8) — commit c28f15bd. **v1 level-fidelity
  battery KILL at FDR** (0/48, 0/16) **but 5 PULSE cells, all SHORT-side** (NQ 15m anchor-2000
  best p=0.0135 OOS +$1,324/tr; GC 1h OOS n≈40 +$816-841/tr beats B&H) — commit 781625e3.
  Diagnostics: stops 3× runner payoffs; high-side sweeps (shorts) = the only profitable
  level families. Exhibit 4,429.8 line unreconstructible from front-month data (contract
  basis / chart TZ) — UNRESOLVED, non-gating. Per pre-registered PULSE rule → shipped
  `Gamma_SsrShadow` forward own-book shadow (two frozen short configs); arming bar ≥20 trips
  + expectancy + beats null; J holds REVOKE. Candidate filed:
  `strategy/candidates/2026-08-07-ssr-sweep-shift-retest-pivot-liquidity.md`.
