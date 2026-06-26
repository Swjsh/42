# NEW-STRATEGY HUNT — Honest Ranked Scorecard

> **Run date:** 2026-06-20 · **Window:** 2025-01-01 .. 2026-05-15 (IS-2025 / OOS-2026 split) · **Fills:** real OPRA option fills (`simulator_real`), not BS-sim.
>
> **Mission:** test 7 externally-sourced 0DTE SPY strategy *classes the fleet lacks* (gap-fade, VWAP-extension MR, RSI2 MR, IBS MR, opening-range fade, pivot/CPR bounce, power-hour momentum) and report — per **OP-20** — whether any is a real, stop-robust, broadly-based **0DTE option** edge worth adding to the fleet.

---

## BOTTOM LINE — read this first

**ZERO of the 7 strategies clears the candidate bar. NONE is a tradeable new edge today. NOTHING ships.**

Every one of these is a real, correctly-cited edge **on SPY price / spot** (or on swing-held equity). Not one survives the translation to a **0DTE single-leg option** under real fills. This is the recurring lesson **C3 / L58 — *SPY-direction != option edge*** — confirmed seven times over: theta decay, adverse delta on the wrong side, and premium-stop misfire eat the underlying signal. The "best" cells that look positive are, almost without exception, rescued by a handful of outlier days (concentration) or by the **−8% premium-stop mechanically capping losers** (a truncation/exit-structure artifact, *not* signal quality).

This is reported honestly per **OP-20 anti-pattern 2.10**: the strongest-looking cells are disclosed as **non-survivors**, deliberately NOT cherry-picked.

| Gate (candidate bar) | Threshold |
|---|---|
| OOS per-trade | > $0 |
| positive_quarters | ≥ 4 / 6 |
| top5_day_pct (concentration) | < 200% |
| drop-top-5-days per-trade | > $0 |
| n (sample) | ≥ 20 |
| stop-robust / no-truncation-artifact | edge must NOT depend solely on the −8% stop; must not invert sign vs chart-stop-only |

---

## RANKED TABLE — by OOS per-trade (disclosure ranking; remember NONE clears the bar)

| # | Strategy | NEW vs fleet | OOS $/trade | overall $/trade | pos Q | top5% | drop-top5 $/trade | clears? | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | RSI(2) mean-reversion | YES | **+6.65** | +6.11 | 5/6 | 54 | +2.87 | ❌ | **DEAD** — beaten by a random-entry null seed; edge is the exit bracket, not RSI(2) |
| 2 | VWAP-extension reversion | YES | +9.3* | +1.79 | 3/6 | **944.5** | **−16.02** | ❌ | **DEAD** — IS negative; all profit is OOS concentration |
| 3 | Power-hour momentum | YES | +4.4 | +7.1 | 5/6 | 69 | +2.23 | ❌ | **DEAD** — clears only at −8% stop; fragile, thin, lottery WR=25% |
| 4 | Opening gap-fade | YES | +7.7 | +10.9 | 4/6 | 103 | **−0.29** | ❌ | **DEAD** — 8 winning days carry the whole net; drop-top5 negative |
| 5 | CPR / pivot first-touch bounce | YES | +9.4* | +1.8 | 3/6 | **423** | **−5.9** | ❌ | **DEAD** — concentration mirage; 4/4 2025 quarters negative |
| 6 | IBS mean-reversion | YES | +1.6 | +5.3 | 5/6 | 31 | +3.68 | ❌ | **DEAD** — truncation artifact; signal inverts to −$19.6 at chart-stop-only |
| 7 | Opening-range fade | YES | **−12.29** | −0.24 | 2/6 | 323 | −7.27 | ❌ | **DEAD** — zero cells positive OOS; worst of the seven |

\* High OOS per-trade is a **concentration mirage** (its own OOS top5 / drop-top5 fail). Ranking by OOS $/trade alone is misleading — that's exactly why the multi-gate bar exists. The table is ordered for disclosure, not desirability.

---

## DETAIL — each strategy, sourced rules + citation, best real-fills config, gate readout, verdict

### 1. RSI(2) mean-reversion — DEAD (best OOS/trade, still fails)
- **Sourced rules:** Larry Connors 2-period Wilder RSI. Trend filter SMA200 (long only > 200MA / short only < 200MA). Long RSI(2) < 10 → CALL; short RSI(2) > 90 → PUT (also swept the more-extreme 5/95). Connors explicitly **does not advocate fixed stops** ("stops hurt performance") → truest cell is chart-stop-only; original 5-SMA-close exit is a 1–3 **day** swing exit, impossible for 0DTE, so substituted v15 intraday exits.
- **Citations:** StockCharts ChartSchool RSI-2; quantifiedstrategies.com/rsi-2-strategy; optionstradingiq.com 2-period-rsi.
- **Best real-fills config:** thresholds 10/90, strike_offset=−1 (OTM-1), premium_stop=−0.08, qty=3 (every tighter-edge stop −0.20/−0.50/−0.99 deeply negative; 5/95 negative in every cell). n=952.
- **Gates:** OOS **+$6.65**/trade · overall +$6.11 · **5/6** pos Q · top5 **54%** · drop-top5 **+$2.87**. Mechanically passes all five structural gates.
- **Why it still fails:** **C3/L58 structure-vs-signal test.** A coin-flip random-entry null (same count / side-mix / −8% stop / OTM-1 / invalidation, 10 seeds) returns **+$2.66/trade mean, +$8.10 MAX** — a lucky random seed **beats** the RSI(2) signal (+$6.11). The signal's edge over the null mean is only +$3.45, well inside null seed variance [−5.73, +8.10]. The positive expectancy is the **asymmetric exit bracket** (−8% cap vs +30% TP1 + runner; WR only 26%), not RSI(2) prediction. Connors RSI(2) is an end-of-day-close equity-**swing** edge; it does not survive intraday → 0DTE single-leg.

### 2. VWAP-extension reversion — DEAD
- **Sourced rules:** Fade VWAP ± 2σ band (the threshold every source converges on). close ≥ VWAP+2σ → PUT; close ≤ VWAP−2σ → CALL. Confirm with RSI(14) exhaustion (≥70 / ≤30). FRESH: only the first bar to cross fires. Target = revert to VWAP. Invalidation at ±3σ ("beyond 3σ the reversion edge weakens") passed as the chart-stop rejection_level. Cooldown 35 min.
- **Citations:** tradewink.com mean-reversion; chartswatcher VWAP guide; crosstrade.io VWAP reversion; StockCharts VWAP; quantifiedstrategies VWAP.
- **Best real-fills config:** strike_offset=−2 (ITM-2), premium_stop=−0.08, qty=3. **Disclosure-only least-bad cell.** 160 signals (93 CALL / 67 PUT). n=139.
- **Gates:** OOS +$9.3/trade BUT overall only +$1.79 · **3/6** pos Q · top5 **944.5%** · drop-top5 **−$16.02** (NEGATIVE without the 5 best days). IS-2025 itself **negative** (−$1.1/trade, n=100) — entire positive showing is OOS concentration (OOS top5=323%).
- **Why it fails:** textbook long-premium MR-fade failure — small frequent wins, rare trend-day losses (adverse delta + theta) dominate. WR ~28%. The sources' own "reversion fails badly on trend days" caveat + C3/L58. **Fleet note:** engine has VWAP *continuation/rejection* (j_vwap_cont) but NO VWAP σ-band extension fade — gap tested, no edge.

### 3. Power-hour momentum — DEAD (academically sourced, modern regime kills it)
- **Sourced rules:** Gao/Han/Li/Zhou "Market Intraday Momentum" (JFE 2018 / SSRN 2440866). First half-hour return (prior close → 10:00 ET) predicts sign of last half-hour. Rule: at 15:30 ET go LONG if first-half-hour return > 0, SHORT if < 0, hold to close. 0DTE adaptation: fire on 15:30 bar → CALL (first_half > +5bps) / PUT (< −5bps), v15 15:50 time-stop = the "hold into close" exit. One signal/day.
- **Citations:** SSRN 2440866; ScienceDirect S0304405X18301351; QuantConnect intraday-ETF-momentum; quantifiedstrategies last-hour SP500.
- **Best real-fills config:** first_half_only mode, strike_offset=−1 (ITM-1), premium_stop=−0.08, qty=3. n=292 (one of only 3/40 cells mechanically clearing 5 gates — all at −8% stop).
- **Gates:** OOS +$4.4/trade · overall +$7.1 · **5/6** pos Q · top5 69% · drop-top5 +$2.23.
- **Why it fails:** (1) **stop-robust = FALSE** — clears at ONLY the −8% stop; every wider stop goes OOS-negative → the "edge" is the tight stop, not the time-of-day signal. (2) expectancy thin (+$4.4/3-lot ≈ +$1.47/contract, below slippage/fee noise). (3) WR=25% — hold-into-close lottery, not a directional edge. (4) per-QUARTER concentration extreme (2025Q3 top5=2655% — one day carried the quarter). The academic underlying-drift base rate is already unfavorable in the modern regime (QuantConnect SPY 2015–2020 replication: **negative Sharpe −0.628**). If ever revisited: test as long-underlying / wider-DTE, NOT a 0DTE single leg, and require stop-robustness.

### 4. Opening gap-fade — DEAD (real literature edge on price, not on options)
- **Sourced rules:** Gap = prior RTH close → today RTH open; FADE toward prior close (down-gap → CALL, up-gap → PUT). Target = gap fill. Sources find stops ineffective → loose arm + 15:50 time-stop. Smaller gaps fill more: ~76% of all gaps fill same-day; SPY bands <0.5% ~70–90%, 1–2% ~45%, 2%+ ~30%. Down-gaps fill slightly more (down-gap-bounce asymmetry). 0DTE adaptation: 1 signal/day, gap measured 09:30 vs prior close (causal), enter ≥09:35, band-gated 0.15%–1.50%, rejection_level = opening extreme against the fade.
- **Citations:** mypivots fading-the-gap; shareplanner; quantifiedstrategies gap-fill; tradethatswing SPY/ES gap-fill; ainvest gap-trade-edge.
- **Best real-fills config:** strike_offset=0 (ATM), premium_stop=−0.08, qty=3. n=186. (`n_cells_clearing_all_gates=0`.)
- **Gates:** OOS +$7.7/trade · overall +$10.9 · **4/6** pos Q · top5 **103%** · **drop-top5 −$0.29** (the decisive failure). The top 8 winning days ($511/$455/$392/$379/$350…) carry the entire $2,035 net; over the remaining 181 trades it is −$0.29/trade. WR ~26%.
- **Why it fails:** premium-buying fade decays most days, rescued by rare big fills — exactly the profile drop-top5 rejects. Down-gap CALL is the stronger side (+$20.9 vs up-gap PUT +$4.2, matching the sourced asymmetry) but is itself concentrated (top5=122%). Same-day SPY gap-fill rate in this band = 47.4% (band-gate + 09:35 entry + 0DTE mechanics decouple price-fill from option P&L). This is the **opposite** of the existing `gap_and_go` continuation. No cherry-pick available.

### 5. CPR / pivot first-touch bounce — DEAD
- **Sourced rules:** Floor-trader pivots from prior-day RTH HLC (StockCharts canonical; reuses repo `level_strength.floor_trader_pivots()`). ENTRY: price tags S1/S2 (CALL) or R1/R2 (PUT) within $0.20, prints a rejection candle (≥40% dominant wick), enter with rejection, stop beyond level, target the pivot, first-touch only. CPR width (Zerodha) used ONLY as a reported regime tag (narrow vs wide), no fabricated breakout leg.
- **Citations:** StockCharts pivot points; edgeful pivot-points-guide; Zerodha Varsity CPR; mywinnerdays pivot strategy; daytrading.com pivot points.
- **Best real-fills config:** strike_offset=+2 (OTM-2), premium_stop=−0.08, qty=3 (every wider stop −$1.6K to −$10.2K). 218 signals. n=194.
- **Gates:** OOS +$9.4/trade BUT overall only +$1.8 · **3/6** pos Q (all four 2025 quarters net-negative, every dollar from 2026) · top5 **423%** (5 days = +$1,457 of a +$344 total) · drop-top5 **−$5.9** (−$1,112 over the remaining 187 trades). WR 16%. OOS look is a concentration mirage (its own top5=194%).
- **Honest sub-observations (neither clears alone, both fail concentration):** CALL/support-bounce side (+$596, 23.7% WR) >> PUT/resistance-reject side (−$252, 8.9% WR); wide-CPR days (+$323) > narrow-CPR (+$21). The edgeful "PP touched 85.2%" stat is **futures cross-sectional**, did NOT translate to an SPY option edge (C4/L58).

### 6. IBS mean-reversion — DEAD (clearest truncation artifact)
- **Sourced rules:** IBS = (close − low) / (high − low). LONG IBS < 0.20 → CALL; SHORT IBS > 0.80 → PUT; buy on the close.
- **Citations:** therobusttrader IBS; jonathankinlay IBS indicator; alvarezquanttrading IBS; quantifiedstrategies IBS.
- **Best real-fills config:** strike_offset=−1, premium_stop=−0.08, qty=3. 3731 signals. n=3396.
- **Gates (naive 5-gate self-verify PASSES — false positive):** OOS +$1.6/trade · overall +$5.3 · **5/6** pos Q · top5 **31%** · drop-top5 +$3.68.
- **Why it fails (6th gate added):** **truncation artifact (C2/L51/L55).** The ONLY positive cells in the whole 20-cell grid sit at premium_stop=−0.08, where WR **collapses to ~26%** — but the IBS thesis is a ~70%-WR mean-reversion edge, so the inversion is the tell. The SAME IBS signal at chart-stop-only (−0.99) on the same strike is **−$19.6/trade**, and every non-tight-stop cell is −$5.7 to −$26.6. The positive $ comes purely from cutting every loser at −8% while a few fast winners run — NOT IBS quality. Also a **firehose:** 3731 signals/16mo (~14/day) is noise, not a selective setup. A no-truncation-artifact gate (chosen cell must not invert sign vs chart-stop-only on the same strike) was added and correctly sets clears_bar=false. (The published IBS edge is a DAILY hold-to-next-close spot %-return edge.)

### 7. Opening-range fade — DEAD (worst performer)
- **Sourced rules:** OR = high/low of first 30 min RTH. Failed-breakout fade: bar HIGH pokes above OR-high but CLOSES back inside → PUT; bar LOW pokes below OR-low but closes back inside → CALL. Entry on reclaim-bar close, fill next bar. Stop just outside the failed breakout (rejection_level = the OR edge crossed). One fade/side/day, first qualifying poke, 45-min cooldown, no entries after 15:00 ET. v15 exits.
- **Citations:** quantifiedstrategies ORB; buildalpha ORB; litefinance ORB; ungeracademy Crabel ORB; fbs ORB; bullsonwallstreet ORB.
- **Best real-fills config:** strike_offset=0, premium_stop=−0.08. 309 signals (163 PUT / 146 CALL). n=266.
- **Gates:** **ZERO cells have positive OOS.** Best cell: overall −$0.24/trade (WR 22.2%) · OOS **−$12.29**/trade (n=51) · IS-2025 only +$2.62 BUT top5=323% · **2/6** pos Q (both 2026 quarters negative) · drop-top5 −$7.27. PUT side's +$99 is a mirage (top5=1475%).
- **Why it fails:** WR ~22% — the fade gets chopped; SPY pokes back inside then resolves in the original break direction often enough that the 0DTE option bleeds via theta/stop-misfire (C3). Only "positive" cell is IS-only, thin, hyper-concentrated, flips negative OOS. Opposite-direction reversal of the engine's ORB-style continuation.

---

## What this hunt CONFIRMS (doctrine value, even with zero ships)

1. **C3 / L58 is the wall.** Seven independently-sourced, correctly-cited price/spot/equity edges → seven 0DTE-option non-edges. SPY-direction is necessary but nowhere near sufficient for an option edge once theta + delta + spread + stop-misfire are paid.
2. **The −8% premium stop is a confound, not an edge.** Multiple strategies (IBS, power-hour, RSI2, gap-fade) "pass" naive structural gates *only* at premium_stop=−0.08 and either invert at chart-stop-only or beat a random-entry null. The asymmetric exit bracket (−8% cut / +30% TP1 / runner) manufactures positive expectancy on a 22–28% WR coin flip. **Recommendation: the no-truncation-artifact gate (sign must not invert vs chart-stop-only on the same strike) and the random-entry null benchmark should be standard in every future hunt** — they caught IBS and RSI(2) where the 5-gate self-verify did not.
3. **Concentration (top5 / drop-top5) is the second wall.** VWAP-ext, pivot, gap-fade, opening-range all show high OOS-per-trade that is pure outlier-day rescue. OOS-per-trade ranking alone is dangerously misleading — the multi-gate bar earns its keep.
4. **Coverage:** all 7 are genuinely NEW classes vs the fleet (gap-fade is the opposite of `gap_and_go`; VWAP-ext is distinct from j_vwap_cont; RSI2 distinct from RSI-divergence; IBS/pivot-bounce/OR-fade/power-hour entirely absent). The fleet is not leaving an obvious literature edge on the table in these classes.

---

## RECOMMENDATION

**Add NOTHING to the fleet.** No strategy clears the bar; no cell is a defensible survivor under OP-20 anti-pattern 2.10. There is no promising-lead worth a follow-up hunt either — the failures are structural (option mechanics + concentration), not tuning-distance.

**If any of these were to be revisited** (none recommended now): test as long-underlying / wider-DTE structures rather than 0DTE single legs, and require stop-robustness (clears at chart-stop-only, not just −8%) + a random-entry-null beat as preconditions before spending a grid.

> **OP-11 / Rule 9 reminder:** even *if* a future variant cleared this bar, it would still need the OP-11 live-bar (A/B scorecard filed, OOS-positive + WF ≥ 0.70 + sub-window stable + anchor no-regression) and would only flip live in an after-hours block under Rule 9 — never mid-session. Moot here: nothing clears.

---

### Artifacts
- `analysis/recommendations/newhunt-rsi2-mean-reversion.json` · script `backtest/autoresearch/_newhunt_rsi2_mean_reversion.py`
- `analysis/recommendations/newhunt-vwap-extension-reversion.json` · `_newhunt_vwap_extension_reversion.py`
- `analysis/recommendations/newhunt-power-hour-momentum.json`
- `analysis/recommendations/newhunt-opening-gap-fade.json`
- `analysis/recommendations/newhunt-cpr-pivot-bounce.json` · `_newhunt_cpr_pivot_bounce.py`
- `analysis/recommendations/newhunt-ibs-mean-reversion.json` · `_newhunt_ibs_mean_reversion.py`
- `analysis/recommendations/newhunt-opening_range_fade.json`
