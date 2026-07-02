# PHASE 1 — MES Multiday Swing Battery — pre-registered DESIGN

> **Committed BEFORE grinding** (protocol pre-registration; the grinder implements this spec verbatim).
> Parent plan: [`markdown/futures/FUTURES-REVIVAL-PLAN-2026-07-02.md`](../../../../markdown/futures/FUTURES-REVIVAL-PLAN-2026-07-02.md) §Phase 1.
> Question under test: **does the direction alpha in the theta-killed seed pile survive on the linear instrument (MES) at 1–5 day swing horizons?**
> Research only. $0. No broker, no creds, no edits to anything the live 0DTE engine reads.

## 1. Data & sessions

- **Source:** `backtest/data/futures/MES_1m_continuous.csv` — Databento GLBX.MDP3, back-adjusted (Panama) continuous front-month `MES.c.0`, pulled 2026-06-16. Verified this session: **508,586 one-minute bars, 2025-01-01 18:00 ET → 2026-06-12 16:59 ET, full ETH Globex sessions** (23h/day, median 1,380 bars/day, 452 dates). *Correction to the plan doc: the cached 1m data is ETH, not RTH-only — real overnight bars exist, so gap/stop modeling is native, not approximated.*
- **Resamples (produced by the grinder, written to `backtest/data/futures/derived/`):**
  - `MES_5m_eth.csv` — 5m full-session (the exit-walk stream).
  - `MES_5m_rth.csv` — 5m 09:30–16:00 ET (the signal stream).
  - `MES_4h_eth.csv` — 4h anchored to the 18:00 ET Globex open (artifact for Phase 2/3; not load-bearing here).
  - `MES_daily_rth.csv` — daily RTH bars (09:30–16:00 ET).
- **Convention (explicit):**
  - **Signals are computed on RTH bars** — the RRW detector was validated on SPY RTH 5m frames (ES and SPY are the same underlying read), J's named levels (PDH/PDL/PDC, weekly H/L) are cash-session chart levels, and VWAP is the RTH session VWAP J actually trades against.
  - **Fills, stops, targets, and holds are walked on ETH 5m bars** — a real GTC stop at the broker is live on Globex overnight; gaps must hit at real overnight prices, not be assumed away.
  - **Daily bars are RTH daily** — ATR(14), prior-day H/L/C, weekly H/L, and BOS/CHoCH structure all read the cash session. Disclosed limitation: RTH-daily ATR understates full-session volatility, so stops are sized slightly tight relative to overnight range; the gap-aware fill model (below) charges the true cost of that.

## 2. Seeds — 24 signal combos (the pre-screened kill-pile; no new signals)

All signals evaluate on **completed** RTH 5m bars only; entry is the **next ETH 5m bar open** (C6: no look-ahead). Eligible signal-bar window 09:35–15:30 ET (excludes the open bar and the last 25 min; J's toxic 09:30–10:00 window additionally excluded for Seed B per the WeBull fresh-eyes finding).

### Seed A — RRW-short (8 combos)
Port of `backtest/lib/watchers/ribbon_rejection_wick_detector.py` (bear side only — the short cohort was the direction-real side) onto MES RTH 5m bars, Saty ribbon 13/20/48 via `lib.ribbon.compute_ribbon`, superset scan + post-hoc feature filters exactly as the options battery ran it.
- **Dollar-knob scaling disclosed:** SPY-dollar constants ×10 to ES points (MES ≈ SPY×10): `close_margin_dollars` 0.01→**0.10 pt**, `min_bar_range_dollars` 0.10→**1.00 pt**.
- **Config family = the 8 BH-FDR survivors of the options battery** (`analysis/recommendations/ribbon-rejection-wick.json`, ranks 9–16): `wick_frac_min ∈ {0.35, 0.5} × break_lookback_bars ∈ {6, 12} × vol_mult_min ∈ {1.5, 2.5}`, stack=any. The vol=0 survivors are excluded (≈700 fires/18mo ≈ every-other-day ⇒ C27 noise concern, and worst expectancy of the pile). Not the full 24-combo grid.

### Seed B — E2 direction contexts (4 combos)
At-named-level + VWAP-aligned, both directions (E2's direction read was two-sided).
- **Named levels (causal):** PDH/PDL/PDC from the prior trading day's RTH bars; PWH/PWL from the prior completed ISO week's RTH bars.
- **VWAP:** RTH session VWAP, cumulative from 09:30, typical price (H+L+C)/3 on 5m bars, evaluated at the completed signal bar.
- **LONG:** bar low ≤ L×(1+tol) AND close > L AND close > VWAP (touch/undercut of a named level, close back above it, on the long side of VWAP).
- **SHORT:** bar high ≥ L×(1−tol) AND close < L AND close < VWAP.
- Any of the 5 named levels qualifies; first signal per day per direction (dedupe).
- **Grid:** tol ∈ {0.05%, 0.10%} × window ∈ {MIDDAY 11:00–14:00, FULL 10:00–15:00} = **4 combos**.

### Seed C — daily-structure alignment filter (12 combos)
The same A1–A8 and B1–B4 signals with an added **daily BOS/CHoCH working-trend filter** (`crypto.lib.market_structure.walk_structure`, fractal window 2, on RTH daily bars): shorts require working trend = downtrend, longs require uptrend, **as of the last completed daily bar before the signal date** (causal). 8 + 4 = **12 combos**.

**Total: 24 signal combos.** No other signal knobs exist or will be added post-hoc.

## 3. Exit/hold matrix — 36 shapes (the swing part)

Stop distance `S = stop_mult × ATR14`, where ATR14 = Wilder ATR on RTH daily bars **as of the last completed day before entry**.

| Knob | Values |
|---|---|
| `stop_mult` | 1.0, 1.5, 2.0 |
| `target` | 2×S, 3×S, TRAIL (chandelier on daily RTH closes: stop ratchets to best-daily-close-since-entry ∓ stop_mult×ATR_entry; no fixed target) |
| `max_hold` | 3, 5 trading days (exit at the 15:55 RTH close of day N; entry day = day 0) |
| `weekend` | flat_friday (exit at Friday's 15:55 close), hold_weekend |

3×3×2×2 = **36 shapes**. Fill model on the ETH 5m walk, bar by bar from the entry bar onward:
- Bar **opens** beyond stop (gap) → fill **at the open**, never at the stop. Same for target.
- Bar crosses stop intrabar → fill at the stop level. Both stop and target inside one bar → **stop first** (conservative).
- TRAIL stop levels update once per day after the 15:55 RTH close, effective the next bar.
- Data ends 2026-06-12 → any open trade exits at the final bar close, flagged `DATA_END`.
- One position at a time per cell (signals arriving while a position is open are skipped — non-overlapping trades, chronological).

**Sizing:** 1 MES contract, $5/point, per-contract dollars reported. **Costs (disclosed):** $1.24 round-turn commission + 1 tick (0.25 pt = $1.25) slippage per side ⇒ **$3.74 per round turn** deducted from every trade, including nulls. Stop/target prices are not tick-rounded (slippage charge dominates; disclosed).

## 4. Battery discipline (pre-registered — no post-hoc knobs)

1. **Split:** TRAIN = entries dated ≤ 2025-12-31. TEST = 2026-01-02 → 2026-06-12. Ranking uses TRAIN only.
2. **Selection:** among all 24×36 = 864 cells, eligible = train_n ≥ 15 AND train net expectancy > 0. Rank eligible by train net expectancy/trade, **cap ≤3 cells per signal combo** (breadth guard), take **top-K = 12** to ONE test pass. If zero eligible: verdict is decided at the train stage (honest kill, no test burned).
3. **Random-entry null (per tested cell):** pool of 250 random entries per (exit shape × direction × window family), entry bars sampled uniformly from eligible RTH 5m signal bars in the TEST period (window families: RRW_ALL 09:35–15:30, MIDDAY, FULL), walked through the SAME exit shape (same hold distribution by construction), same costs. Null trades are independent samples (overlap permitted — per-trade expectancy is the statistic; disclosed). p-value: 4,000 bootstrap draws of size n_test from the pool matching the cell's direction mix; one-sided P(null mean ≥ observed mean), +1/(B+1) smoothing.
4. **BH-FDR α = 0.1** across the ≤12 test p-values.
5. **Opposite-direction null (per FDR survivor):** identical entry bars, direction flipped, same exit shape, sequential non-overlap. Requirement: opposite expectancy ≤ 0 AND observed − opposite > 0 (the sign must be carried by direction, not by the exit shape harvesting drift).
6. **Concentration:** drop-top3 test P&L must stay > 0.
7. **Stability:** test halves split at entries ≤ 2026-03-22; both halves' total P&L > 0; a half with n < 8 counts as *insufficient-n* (blocks the top verdict rung, does not count as pass).
8. **Drawdown:** max drawdown on the cell's cumulative closed-trade test P&L; *acceptable* = recovery factor (test total P&L / maxDD) ≥ 1.0.

## 5. Verdict ladder (pre-registered)

- **DIRECTION_TRANSFERS:** ≥1 cell passes ALL of: BH-FDR survivor, test n ≥ 15, test expectancy > 0, opposite-direction null pass, drop-top3 > 0, both halves > 0 (each n ≥ 8), recovery factor ≥ 1. → spec Phase 2/3 next steps.
- **WEAK:** ≥1 cell passes BH-FDR + test expectancy > 0 + opposite-direction null, but fails a robustness check (concentration / halves / low-n / recovery).
- **DOES_NOT_TRANSFER:** nothing clears BH-FDR with positive test expectancy and directional separation — the honest kill: the theta thesis was wrong for this seed pile; direction alpha does not survive even on the linear instrument.

## 6. Outputs

- `results.json` — full funnel (superset events → per-combo events → train/test trades → eligible cells → top-12 → FDR → survivors), every tested cell's metrics, null diagnostics, weekend-vs-flat matched comparison (train-level descriptive across all cells + within tested cells), per-contract expectancy, maxDD.
- `RESULTS.md` — funnel table + survivor table (or honest empty) + verdict rung + caveats.
- Provenance row appended to `analysis/backtests/data-versions.jsonl`.

## 7. Known caveats (declared up front)

- Back-adjusted continuous series: absolute price levels are roll-shifted; all signals here are *relative* (ribbon, prior-day/week levels from the same adjusted series, VWAP, ATR) so internally consistent; % tolerances on adjusted prices differ negligibly from raw (adjustment ≈ small vs 6000-pt level).
- 5m walk granularity: intra-5m-bar stop/target ordering resolved conservatively (stop first); at swing-scale ATR stops (tens of points vs ~2–4 pt 5m ranges) the ambiguity is second-order.
- RRW dollar-knob ×10 scaling is a judgment port (disclosed above), not re-fingerprinted.
- Single instrument (MES). MNQ is a Phase-1b follow-up only if MES answers the gate question.
- 18 months, one macro regime pair (2025 chop / 2026 H1). Regime stratification beyond IS/OOS + halves is out of scope at this n.
