# Sunday Fresh-Angles Scorecard

Web-sourced hypotheses tested against OUR data (real OPRA fills via `lib.simulator_real`,
SPY/VIX 5m, MES/MNQ overnight futures). Each entry applies the RIGHT bar for its `kind`:
a DEPLOY-TIMING layer must lift the BOOK's risk-adjusted return AND pass no-regression
(abstained days NET-NEGATIVE, not winner-removal — L174); a NEW signal must pass the full
11-gate bar. Most are WALL/DEAD (C3/L58); named honestly.

---

## HEADLINE (2026-06-21) — the DEPLOY-TIMING vein is a WALL; the honest path is HOLD + monitor recency

**The genuinely-fresh, live-relevant question this batch chased:** can we *time deployment* of the 3 VWAP-native edges (#1 `vwap_continuation` LIVE / #2 `vwap_reclaim_failed_break` / #4 `vix_regime_dayside`) — deploy when the regime favors them, abstain when it doesn't — WITHOUT a winner-killing per-trade gate, to ride out the current ~2.2σ recency drawdown (last 25 trading days RED at n=10–11)? A deploy-timing signal that cleared its bar would have been **the most valuable find since the drawdown began**, because it directly addresses the open problem (the drawdown is a stretched-uptrend regime tail, NOT decay, NOT stop-fixable [−8% is optimal], NOT cleanly per-trade-gateable [trend>3% gate hurts ITM-2]).

**Result: 5 of 5 deploy-timing hypotheses are WALL/DEAD. NO deploy-timing signal cleared its bar. NO new edge. NO live-path change.** The honest path remains **HOLD + monitor recency** (the `recency_check.py` weekly CONFIRM-BEFORE-CAPITAL gate already governs the live flips; today's verdict is RED-blocked on #1).

### The 5 angles, all the same structural death (winner-removal, L174)

| # | Angle (kind) | Verdict | The killer (real numbers) | Harness / JSON |
|---|---|---|---|---|
| La-1 | overnight gap-up fades the day *(deploy_timing)* | **WALL** | Abstained large-up-gap days sum **NET-POSITIVE** every book/threshold (Safe2 +$2,861 @0.30%, Bold +$3,772); total P&L DROPS in every cell; Sharpe "lift" is a denominator artifact | `_sub_overnight_gap_fade.py` / `overnight-gap-fade.json` |
| La-2 | overnight-range %-ATR regime gate *(regime_gate)* | **DEAD** | Degenerate band (chop=10 / neutral=124 / trend=218 of 352d; ZERO chop days in the live drawdown, min ratio 0.330>0.25) AND sign INVERTED in-window (bleed concentrates in the TREND band the rule says to DEPLOY into: Bold trend −$852) | `_sun_overnight_range_atr_gate.py` / `_sun_overnight_range_atr_gate.json` |
| La-3 | overnight vol-expansion favors edges *(regime_gate)* | **WALL** | Hypothesis HALF-TRUE (hi-overnight-vol days do produce higher mean P&L, survives a VIX control) but abstained low-vol days are net-POSITIVE (+$4,803 Safe / +$6,816 Bold) → abstaining buys +0.04–0.05 Sharpe at the cost of $5–7K real P&L | `_deploytiming_overnight_vol.py` / `deploytiming-overnight-vol.json` |
| La-4 | overnight trend-agreement / blow-off *(deploy_timing)* | **WALL** | Cross-validation guard FIRED: mask "works" on MES (9 blowoff days net −$0.76 ITM-2) but REVERSES on MNQ (13 days net +$523.28 = winner-killing); no MES/MNQ sign-agreement = single-instrument overfit on tiny n (9–13 of ~85 days) | `_b9_overnight_trend_agreement.py` / `overnight-trend-agreement-bullish.json` |
| Lb/La-5 | Monday overnight gap-up skip *(deploy_timing)* | **DEAD** | INVERTED on real fills, all 4 cohorts × 4 thresholds: Mondays are the BEST weekday; Monday-gap-up days strongly net-POSITIVE (Bold +$1,173 @0.30%, 37 Mondays = ~32% of P&L from ~24% of days). Isolates+rules-out the weekend-effect variant of La-1 | `_sunday_monday_gap_skip.py` / `sunday-monday-gap-skip.json` |

### The one mechanism behind all five (the deploy-timing TRAP, now documented as a WALL)

**A signal can be a TRUE day-QUALITY ranker yet still be a net-destructive abstain GATE.** Three of the five (overnight-vol, gap-up, even the MES leg of blow-off) are *real, sometimes VIX-independent* signals of which days are better-or-worse. But the deploy-timing bar (L174) demands the abstained days be net-NEGATIVE. In a stretched-uptrend regime the "worse" days are still *profitable* — so abstaining is winner-removal, not loss-avoidance. The Sharpe lift it buys is a denominator artifact (deleting below-mean-but-positive days). **This is the deploy-timing analog of C3/L58:** an overnight-futures/SPY-price character signal is not a 0DTE option deploy gate — the overnight move is priced in by 09:30 and theta/stop mechanics dominate the intraday option outcome regardless of overnight character.

### Lb (OPEX/calendar) and Lc (novel setups) — assessed, not separately re-mined here

- **Lb OPEX/calendar finer-than-B9 angles:** the strongest candidate (H2 = deploy continuation in the post-OPEX low-GEX trend window / abstain pre-monthly-OPEX) aligns the gamma-regime mechanic WITH the edge's continuation structure and is the only defensible one — but the OPEX-DAY-itself buckets are n=3–4 (below the n≥10 floor / L175). The Monday-gap variant (La-5) already INVERTED, and B9 already killed generic day-type routing with every calendar/day-type bucket net-positive (no non-regressive abstention exists). The calendar vein is advisory/exploratory only; nothing testable clears the floor.
- **Lc novel setups:** **Lc-1 market intraday momentum** (Gao-Han-Li-Zhou first-30min→later-session return autocorrelation) was the single most-promising genuinely-new testable idea — but it was ALREADY tested as the **H1_intraday_momentum** family (2026-06-19, real OPRA fills, chart-stop-only LIVE config; see `H1_intraday_momentum-LIVE.json`); not a fresh-untested angle for this batch. **Lc-2 negative-gamma trend-day deploy-timing** is conceptually the RIGHT answer to the open problem but **testable=false** in its real form (needs a live GEX feed we do not have, marked NOT available); its testable price/VIX proxy re-treads already-dead regime-gating. **Honest: aside from Lc-1 (already done), the novel-setup vein is essentially dry.**

### Disposition + honest verdict

**Add to the DEAD / do-not-re-mine list:** overnight-extreme (gap-up OR blow-off) deploy-timing abstain; overnight-range/ATR regime deploy gate; overnight-realized-vol deploy-timing abstain; weekday/calendar (incl. Monday) deploy-timing of the continuation edges. The whole **overnight-futures + calendar deploy-timing class is a WALL for the VWAP-native bull book** — every variant fails no-regression (removes net-winners) because in a stretched uptrend the "unfavorable" days are still profitable.

**NO new DEPLOY_TIMING_SIGNAL and NO EDGE/IMPROVEMENT cleared its bar → nothing appended to `LIVE-PATH-WORKPACKAGE.md` (no dormant-flip-ready spec produced this batch).** A deploy-timing find would have been the highest-value result since the drawdown; it did not materialize. **The honest path is unchanged: HOLD the live #1 edge, do NOT add a deploy/abstain gate, and let `recency_check.py` (the weekly CONFIRM-BEFORE-CAPITAL gate) govern when capital re-engages.** The drawdown is a regime tail to be WAITED OUT on the full-OOS-positive base, not gated away. **Single highest-EV next action: the already-validated daytime money-path fix WP-5** (re-strike the ALREADY-LIVE #1 off the OTM-2 mis-strike to its validated cell, Safe→ATM via the parity-tested per-setup strike dispatch behind A5) — it is independent of the (failed) deploy-timing question and fixes the edge trading real paper capital right now (subject to the recency-RED REVOKE note on the Bold ITM-2 leg).

---

## overnight-gap-up-fades-the-day  —  kind=deploy_timing  —  VERDICT: WALL (REJECT, all books/thresholds)

**Run:** 2026-06-21 | **Window:** 2025-01-01 .. 2026-06-12 (361 trading days) |
**Harness:** `backtest/autoresearch/_sub_overnight_gap_fade.py` |
**Scorecard JSON:** `analysis/recommendations/overnight-gap-fade.json`

**Claim (web-sourced):** On days where SPY opens with a LARGE up-gap (prior-RTH-close ->
09:30 open > +0.30%), the bull-trend-continuation 0DTE edges UNDERPERFORM (negative/flat
day P&L), because daytime arbitrageurs fade persistent overnight up-pressure and the day's
equity premium was already spent overnight. **Deploy-timing rule tested:** ABSTAIN the book
on large overnight-up-gap days.

**Why it was worth a test (cites):** the gap-fade literature is real — large overnight
gaps in SPY/QQQ often set up mean-reversion, the average intraday return following a large
gap tends to *oppose* the gap, and ~all market gains historically accrue overnight (the
"intraday gives some back" thesis). BUT the same literature flags the asymmetry that sank
this test: **gap-DOWNS reverse far more than gap-UPS (~52% vs ~35%)** — fading an up-gap is
the *weaker* side of the effect. Sources below.

**Gap proxy is sound:** SPY 5m overnight gap vs MES overnight-futures gap (18:00 ET prior ->
09:25 ET) correlate **0.835** across 353 overlap days — the cross-check corroborates the gate.

### Result — the deploy-timing bar FAILS on the no-regression leg, decisively

| Book | Baseline total | Baseline Sharpe | gap thr | Abstained days (traded) | **Abstained day P&L** | Deployed Sharpe (lift) | Deployed total | Verdict |
|---|---|---|---|---|---|---|---|---|
| Safe2 ATM #1+#2+#4 | $13,346 | 4.134 | 0.20% | 128 (56) | **+$2,866** | 4.945 (+0.81) | $10,480 | REJECT |
| | | | 0.30% | 97 (47) | **+$2,861** | 4.563 (+0.43) | $10,485 | REJECT |
| | | | 0.50% | 58 (31) | **+$2,671** | 4.165 (+0.03) | $10,676 | REJECT |
| Bold ITM-2 #1+#2 | $17,903 | 4.305 | 0.30% | 97 (48) | **+$3,772** | 4.436 (+0.13) | $14,131 | REJECT |
| LIVE #1 vwap_cont ATM | $6,976 | 3.866 | 0.30% | 97 (47) | **+$1,129** | 4.275 (+0.41) | $5,847 | REJECT |
| LIVE #1 vwap_cont ITM-2 | $11,122 | 4.139 | 0.30% | 97 (48) | **+$1,913** | 4.543 (+0.40) | $9,209 | REJECT |

(Full grid incl. 0.20/0.50% for every book in the JSON.)

### The honest finding (the opposite of the hypothesis)

1. **No-regression FAILS — this is pure winner-removal (L174).** On every book and every
   threshold the abstained large-up-gap days sum **NET-POSITIVE**, not negative. Large
   overnight up-gaps are *modestly profitable* for these bull-continuation 0DTE edges, not
   faded. The hypothesis predicted the abstained bucket would be net-negative; it is the
   reverse.
2. **The Sharpe "lift" is a denominator artifact, not real edge.** Deployed Sharpe rises
   slightly only because you remove profitable-but-below-mean days (lowers sd more than
   mean). **Total P&L DROPS in every single cell** (e.g. Safe2 -$2,861 at 0.30%; Bold
   -$3,772). Higher Sharpe + lower money on fewer trades = textbook winner-removal. Both
   legs of the bar must hold; the no-regression leg fails, so the lift is rejected.
3. **DSR caveat:** even the Sharpe lift would be fragile — driven by 31-56 abstained
   *traded* days at most, and it collapses toward zero (or negative for Bold) as the
   threshold tightens to 0.50%. Nothing here survives a drawdown-window discount.

**Disposition:** WALL. Up-gap days are not a deploy-abstain signal for the VWAP-native bull
edges — abstaining them throws away money. Do NOT add a gap-up abstain gate. The genuinely
open problem (timing the regime drawdown without winner-killing) remains unsolved by this
angle. Add to the DEAD list: *overnight up-gap deploy-timing abstain*.

**Sources:**
- [Fading the Gap: How SPY and QQQ Overnight Moves Play Out — SharePlanner](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html)
- [How Often Do Overnight Gaps Get Reversed? — QuantifiedStrategies](https://www.quantifiedstrategies.com/how-often-do-overnight-gaps-get-reversed/)
- [Overnight and Intraday SPX returns — Robot Wealth](https://robotwealth.com/overnight-and-intraday-spx-returns/)
- [Overnight Mean-Reversion — QuantReturns](https://quantreturns.com/strategy-review/overnight-mean-reversion/)

---

## [2026-06-21] overnight-range-pct-atr-regime-gate — DEAD (degenerate band; backwards in the drawdown)

**Slug:** `overnight-range-pct-atr-regime-gate` | **Kind:** regime_gate (DEPLOY-TIMING layer on the book) | **Built + ran:** yes
**Harness:** `backtest/autoresearch/_sun_overnight_range_atr_gate.py` | **JSON:** `analysis/recommendations/_sun_overnight_range_atr_gate.json`
**Reuses:** `recency_check.detect_all` (byte-for-byte LIVE detectors #1/#2/#4) + `recency_check.simulate_set` (real OPRA fills via `lib.simulator_real`, C1) + `BOOKS` composition; NEW overnight-range/ATR from `backtest/data/futures/MES_1m_continuous.csv`.

**Web-sourced claim (the published framework):** TradingView "NQ Overnight Range (% of Daily ATR)" (rodtradessometimes) classifies the coming RTH session by overnight range (18:00 ET prior -> 09:30 ET) as a fraction of daily ATR: **<25% = chop-leaning** (fakeouts, weak follow-through), 25-50% neutral, **>50% = expansion/trend-leaning**. Hypothesis: trend-continuation edges bleed in the chop band, work in the trend band -> deploy the book only in the trend-leaning band, abstain in chop.

**The bar applied (deploy-timing, L174):** ACCEPT only if (a) the mask lifts the book's risk-adjusted return (Sharpe/Sortino, maxDD no worse) AND (b) the abstained days sum NET-NEGATIVE (removing losers, not winners). Winner-removal => REJECT.

### REAL numbers

**Band distribution is degenerate for ES.** Overnight ratio computed for 352 dates (2025-01-24..2026-06-12, MES 1m). Full-history band counts: **chop=10, neutral=124, trend=218**. The ES overnight session is almost never quiet relative to ATR — the <25% chop band catches under 3% of days.

| Book | full-hist (overnight-covered) | chop band | neutral band | trend band |
|---|---|---|---|---|
| Safe2 ATM #1+2+4 | n=152, $12,682, Sharpe 6.40 | n=2, **−$172** | n=52, +$3,401 | n=96, +$9,273 |
| Bold ITM2 #1+2 | n=151, $17,198, Sharpe 6.76 | n=2, **−$192** | n=51, +$5,441 | n=97, +$11,678 |

The only rule that nominally clears the bar full-history (`deploy_if_ratio>=25%`, drop chop) removes **2 days** worth −$172/−$192 and lifts Sharpe a trivial +0.15/+0.16. A 2-day mask is not a deploy-timing layer — it is noise.

**The live-relevant test — the 25-day drawdown window (2026-05-14..06-18) — kills it outright.** Every single covered day in the drawdown is neutral or trend; the lowest overnight ratio is **0.330** (still above the 0.25 chop threshold). There is NOT ONE chop day in the entire drawdown:

| Book (DD window) | book total | chop | neutral | **trend** | unclassified (06-13..18, no futures) |
|---|---|---|---|---|---|
| Safe2 ATM | n=10, −$216 | **n=0** | n=3, −$179 | **n=5, +$8** | n=2, −$45 |
| Bold ITM2 | n=11, −$1,465 | **n=0** | n=3, −$324 | **n=6, −$852** | n=2, −$289 |

The bleed is concentrated in the **trend band — the exact band the hypothesis says to DEPLOY into** (Bold trend days = −$852, the largest chunk of the drawdown). The hypothesis is not just inert here, it is **backwards**: the days it labels "favorable / trend-leaning" are the losers. The two "ACCEPT" verdicts the harness prints on the DD window are artifacts — `trend_drawdown` only "passes" by abstaining the 3 *neutral* days (−$179/−$324) while KEEPING the bleeding trend days, so the book stays net-negative; it does not fix the drawdown and it relies on a band that is not the hypothesized chop band.

### Why it dies (C3/L58 + degenerate signal)

1. **No chop days to abstain.** The mechanism ("edges bleed on chop days") has zero instances during the period it was meant to fix. The lowest-overnight day in 22 drawdown days is still 0.33×ATR.
2. **Sign is inverted in-window.** Overnight expansion did not produce RTH follow-through for the option book — the most-expanded overnight days (Bold trend band) were the worst. SPY/ES overnight-range expansion != 0DTE option continuation edge (C3/L58): the futures overnight move is already priced in by 09:30, and theta/stop mechanics on the option dominate the intraday outcome regardless of overnight character.
3. **Full-history "lift" is a 2-day artifact** that would not survive any DSR/multiple-testing discount.

**Disposition:** DEAD. Overnight-range/ATR is not a usable deploy-timing gate for the VWAP-native book: the chop band is empty exactly when we need it, and overnight expansion is uncorrelated-to-inverted with the option book's intraday P&L in the live drawdown. Add to the DEAD list: *overnight-range/ATR regime deploy-timing gate*. The genuinely open problem — timing the regime drawdown without a winner-killing per-trade gate — remains unsolved by this angle.

**Sources:**
- [Futures: NQ Overnight Range (% of Daily ATR) — TradingView (rodtradessometimes)](https://www.tradingview.com/script/B4hdMfY5-Futures-NQ-Overnight-Range-of-Daily-ATR/)
- [Average True Range (ATR) and ATRP — StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-true-range-atr-and-average-true-range-percent-atrp)
- [ATR vs ADR vs Intraday Range — Trade That Swing](https://tradethatswing.com/which-is-better-average-true-range-atr-average-day-range-adr-or-intraday-range-ir/)

---

## overnight-vol-expansion-favors-edges  —  kind=regime_gate (deploy-timing)  —  VERDICT: WALL (REJECT, all books)

**Run:** 2026-06-21 | **Window:** 2025-01-02 .. 2026-06-12 (374 overnight-vol days; 157–374
classifiable edge-days/book) | **Harness:** `backtest/autoresearch/_deploytiming_overnight_vol.py` |
**Scorecard JSON:** `analysis/recommendations/deploytiming-overnight-vol.json`

**Claim (web-sourced):** Overnight realized vol positively predicts next-day intraday
realized vol (volatility clustering / persistence). The VWAP-native continuation edges need
intraday RANGE to reach TP1/runner, so days FOLLOWING a high-overnight-vol session should
out-produce dead-overnight (theta-bleed/chop) days. **Deploy-timing rule tested:** DEPLOY
the book when overnight realized vol (sum of |MES 1m log returns| over 18:00→09:30 ET, globex
incl. overnight) exceeds its rolling-60d median; ABSTAIN on low-overnight-vol nights.

**Overnight-vol feature is sound:** `sum(|MES 1m log-ret|)` over the globex overnight window,
bucketed to the cash day it leads into, ≥120 bars required (drops holiday stubs). Causal
rolling-60d-median deploy threshold (shift-1), static-median fallback pre-warmup.

### The hypothesis is HALF-TRUE — but the deploy-timing bar FAILS on no-regression (L174)

High-overnight-vol days genuinely produce a **higher mean day P&L** and a small Sharpe bump.
The directional claim holds. But you cannot harvest it by abstaining, because the abstained
(low-overnight-vol) days are **net-POSITIVE** — abstaining throws away real profit.

| Book | deploy-ALL total / mean / Sharpe / Sortino / maxDD | deploy-HI-only total / mean / Sharpe | **ABSTAINED (lo) days total** | Sharpe lift | net-neg? | Verdict |
|---|---|---|---|---|---|---|
| Safe2 ATM #1+#2+#4 (hi 77 / lo 80) | $13,346 / $85.01 / 0.413 / 1.385 / −$1,007 | $8,543 / $110.95 / 0.462 | **+$4,803** | +0.049 | **NO** | **WALL** |
| Bold ITM-2 #1+#2 (hi 78 / lo 78) | $17,903 / $114.76 / 0.433 / 1.898 / −$1,495 | $11,087 / $142.14 / 0.474 | **+$6,816** | +0.041 | **NO** | **WALL** |

Per-edge (ATM single): vwap_continuation → **DEAD** (abstained +$3,060), vwap_reclaim_failed_break
→ WALL (abstained +$853), vix_regime_dayside → WALL (abstained +$890). Every cut: abstained days
net-positive.

### VIX-disambiguation — the signal is real overnight-FLOW, NOT the dead VIX-level knob

- **corr(overnight_rv, entry VIX) = 0.874** — strongly collinear, so a naive split would just
  be the (DEAD, C5/L122) VIX-level knob in disguise.
- **Within-VIX control survives:** restricting to the MIDDLE VIX tercile (entry VIX 16.72–18.61,
  53 days, holding VIX ~constant), HI-overnight days = **$141.35/day** (Sharpe 0.745, 16W/7L)
  vs LO-overnight = **$24.20/day** (Sharpe 0.170, 12W/18L). The overnight-flow effect is
  genuinely independent of VIX level — overnight realized vol *is* a quality ranker of days.

### Why it's a WALL despite a real effect — the deploy-timing trap

This is the same structural failure as the gap-fade angle above, and it's the crux of the
"can we time deployment?" problem: **a signal can be a true day-QUALITY ranker yet still be a
net-destructive GATE.** Low-overnight-vol days are *worse* but still *profitable* (+$4.8K Safe /
+$6.8K Bold across ~80 days). The no-regression bar (L174) demands the abstained days be net-
NEGATIVE; they are net-positive, so the mask is winner-removal. The only thing abstaining buys
is a +0.04–0.05 Sharpe bump bought by deleting $5–7K of P&L — a trade no risk-adjusted objective
would take, and one that would not survive a DSR/drawdown-window discount.

**Disposition:** WALL. Overnight-vol expansion is a *legitimate, VIX-independent quality signal*
for day outcomes — but NOT a deploy-abstain gate, because dead-overnight days remain profitable.
Do NOT add an overnight-vol deploy-timing abstain gate. (Forward-looking note, NOT a ship: the
*positive* finding — overnight_rv ranks day quality independent of VIX — could only ever justify
a SIZE-UP-on-high-overnight-vol study, never an abstain; that is a separate sizing hypothesis
under L175, not actioned here.) Add to the DEAD list: *overnight-realized-vol deploy-timing abstain*.

**Coverage caveat (honest):** the join is bounded by MES 1m, which ends 2026-06-12, so the
freshest ~4 trading days (06-15…06-18, present in the OPRA cache) are NOT classifiable. The
recency-drawdown tail is therefore only partially inside this window — but the no-regression
failure is structural (abstained days net-positive across the full 374-day frame), not a
window artifact.

**Sources:**
- Engle (1982) ARCH; Bollerslev (1986) GARCH — volatility clustering / persistence (high vol follows high vol).
- [Andersen, Bollerslev, Diebold & Labys — Modeling and Forecasting Realized Volatility (Econometrica 2003)](https://www.ssc.upenn.edu/~fdiebold/papers/paper29/temp.pdf) — lagged RV (incl. overnight component) predicts next-period RV (HAR-RV).
- [Berkman, Koch, Tuttle & Zhang — Paying Attention: Overnight Returns and Firm-Specific Investor Sentiment (JFQA 2012)](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/paying-attention-overnight-returns-and-the-handson-of-individual-investors/) — overnight returns carry information into the cash session.
- [CBOE — Overnight vs. Intraday Volatility in SPX](https://www.cboe.com/insights/) — overnight realized-vol component as a distinct, persistent vol regime indicator.

---

## overnight-trend-agreement-bullish  —  kind=deploy_timing  —  VERDICT: WALL (REJECT — fails MES/MNQ sign-agreement)

**Run:** 2026-06-21 | **Window:** 2025-01-02 .. 2026-06-18 (365 trading days; futures overnight to 2026-06-12) |
**Harness:** `backtest/autoresearch/_b9_overnight_trend_agreement.py` |
**Scorecard JSON:** `analysis/recommendations/overnight-trend-agreement-bullish.json`

**Hypothesis (web-sourced):** the bull-continuation edge (LIVE #1 `vwap_continuation`, CALL
side) wins more when the OVERNIGHT futures session confirmed a *healthy, not-exhausted*
uptrend, and fails on **overnight blow-off** days where price closed at the overnight
extreme. Deploy-timing rule: ABSTAIN when `on_close_position > 0.85 AND higher_high vs
prior overnight high` (overnight closed in the top 15% of its own range AND extended the
prior overnight high = sitting at the exhaustion extreme). Causal: known by 09:30, before
the 09:35 entry gate. Computed independently from **MES_1m** and **MNQ_1m** Globex bars
(18:00 prior ET .. 09:30); cross-validation requires the two instruments to SIGN-AGREE.

**Edge / fills:** `_edgehunt_vwap_continuation.detect_signals` (the live #1 detector),
CALL signals only (90 of 167 total signals); real OPRA fills via
`lib.simulator_real.simulate_trade_real` (C1). Hard-windowed to OPRA cache last 2026-06-18.
Tiers: ITM-2 (-2, validated Bold) + ATM (0).

| Tier | Instr | full mean/day | keep mean/day | full→keep Sharpe | keep total | abstained (blowoff) total | n blowoff | lifts? | blow net-neg? | ACCEPT |
|---|---|---|---|---|---|---|---|---|---|---|
| ITM-2 | MES | $78.61 | $87.93 | 0.446→0.499 | $6,683 | **−$0.76** | 9 | yes | yes | **yes** |
| ITM-2 | MNQ | $78.61 | $85.54 | 0.446→0.480 | $6,159 | **+$523.28** | 13 | no | **no** | **no** |
| ATM | MES | $41.90 | $48.05 | 0.393→0.450 | $3,652 | **−$90.92** | 9 | yes | yes | **yes** |
| ATM | MNQ | $41.90 | $47.21 | 0.393→0.434 | $3,399 | **+$161.64** | 13 | no | **no** | **no** |

**The honest finding — the cross-validation guard caught a single-instrument overfit.**

1. **MES "works", MNQ flips it — they do NOT sign-agree → REJECT.** On MES the 9 blowoff
   days sum ≈$0 (ITM-2) to −$91 (ATM), so the keep-book lifts and the abstained set is
   net-negative → MES ACCEPTs. But the *same* rule on MNQ flags 13 blowoff days that are
   **net-POSITIVE** (+$523 ITM-2 / +$162 ATM) — on Nasdaq-overnight-blowoff days the bull
   edge actually WON, so abstaining them is **winner-killing (L174)**. Required MES/MNQ
   sign-agreement is the exact small-n overfit guard the brief mandated; it fired.

2. **The disagreement is structural, not a bug.** The 8 *consensus* (MES∩MNQ) blowoff days
   sum **+$71** at ITM-2 (the live tier) and only −$55 at ATM (≈−$7/day, noise) — so even
   the robust intersection version fails no-regression at the tier that matters. MNQ's
   verdict is flipped by 5 extra days it alone flags, two of them large winners
   (2026-01-26 +$301, 2026-05-05 +$168). Nasdaq's thinner, noisier overnight tape (Bookmap:
   NQ and ES decouple precisely on risk/volatility days) manufactures different "blowoff"
   labels on small n — the textbook single-instrument overfit.

3. **n is tiny by construction.** 9–13 blowoff days out of ~85 edge-fill days. A 9-day MES
   signal that one cross-check (MNQ) reverses has no DSR headroom; nothing here survives.

**Disposition: WALL.** Overnight-exhaustion / blow-off is NOT a robust deploy-abstain signal
for the VWAP-native bull edge — the only instrument that "confirms" it (MES) is contradicted
by the one chosen to de-overfit it (MNQ), and the live ITM-2 consensus set is net-positive
(winner-removal). Do NOT add an overnight-blowoff abstain gate. Combined with the sibling
`overnight-gap-up-fades-the-day` WALL above, the broader conclusion holds: **overnight
futures price-extremes do not time deployment of the bull 0DTE edge** (C3/L58 — SPY/futures
price character ≠ 0DTE option edge). Add to DEAD list: *overnight-extreme (gap or blow-off)
deploy-timing abstain*. The genuinely open problem (timing the regime drawdown without
winner-killing) remains unsolved by this angle.

**Sources:**
- [NQ vs ES: Why They Move Together, Until They Don't — Bookmap](https://bookmap.com/blog/nq-vs-es-why-they-move-together-until-they-dont) (NQ/ES decouple on risk days — the mechanism behind the MES/MNQ blowoff-label disagreement)
- [NQ Futures Scheduling: Day and Night Sessions — TraderVPS](https://www.tradervps.com/blog/nq-futures-scheduling-day-night-sessions) (overnight = lowest-volume, thin liquidity, false signals reverse at day-session open)

---

## monday-overnight-gap-up-skip  —  kind=deploy_timing  —  VERDICT: DEAD (hypothesis INVERTED, all cohorts/thresholds)

**Run:** 2026-06-21 | **Window:** 2025-01-02 .. 2026-06-18 (365 trading days; 68 Mondays) |
**Harness:** `backtest/autoresearch/_sunday_monday_gap_skip.py` |
**Scorecard JSON:** `analysis/recommendations/sunday-monday-gap-skip.json`

**Distinct from the all-days `overnight-gap-up-fades-the-day` entry above:** this isolates the
*weekend-effect* claim specifically — that the fade is concentrated on **Mondays** (weekend news
premium), where the calendar-anomaly literature is strongest. Tested on its own to rule the Monday
subset in/out.

**Claim (web-sourced):** Monday gap-UPs face heightened intraday FADE risk (weekend "news premium"
over-corrects). The continuation edges should bleed on Mondays that open gap-up -> abstain/de-size the
book on Monday large-up-gap days.

**Deploy-timing bar (L174):** ACCEPT only if removed Monday-gap-up days are NET-NEGATIVE (removing
losers) AND removing them lifts book daily Sharpe AND Sortino with maxDD not worse.

**Gap definition:** `RTH-open(09:30)/prior-RTH-close - 1`, causal from the SPY 5m frame the edges run
on. Thresholds scanned +0.10/+0.20/**+0.30 (headline)**/+0.50 %. Real OPRA fills via
`simulate_trade_real`, 3 live detectors via `recency_check.detect_all`, hard-windowed to OPRA cache
last 2026-06-18.

### Result — the claim is BACKWARDS: Mondays (and Monday gap-ups) are the BEST days

| cohort | full total / Sharpe / Sortino | ALL Mondays (n) total / mean | Mon-gap>+0.30% (n=16) removed total / mean | net-neg? | ACCEPT |
|---|---|---|---|---|---|
| BOOK Safe2 ATM #1+2+4 | $13,131 / 0.404 / 1.359 | 36 -> **+$3,756 / +$104.3** | **+$513 / +$32.1** | NO | x |
| BOOK Bold ITM-2 #1+2 | $17,334 / 0.416 / 1.842 | 37 -> **+$5,528 / +$149.4** | **+$1,173 / +$73.3** | NO | x |
| EDGE #1 vwap_cont ATM (LIVE) | $6,981 / 0.385 / 1.486 | 36 -> **+$2,541 / +$70.6** | **+$512 / +$32.0** | NO | x |
| EDGE #1 vwap_cont ITM-2 | $10,846 / 0.402 / 2.526 | 37 -> **+$4,176 / +$112.9** | **+$1,047 / +$65.4** | NO | x |

(All four thresholds in the JSON; every threshold x cohort = removed P&L POSITIVE, mean +$32..+$87/day.)

### The honest finding

1. **No-regression FAILS — pure winner-removal (L174).** `removed_net_negative = False` on every
   cohort x every threshold. Monday gap-up days are *strongly profitable* for these
   trend-continuation edges, not faded.
2. **Mondays out-earn their day-share.** Bold book: 37 Mondays = $5,528 of $17,334 total (~32% of
   P&L from ~24% of traded days). The "Monday is weak" folklore does NOT hold for OUR 0DTE
   continuation book in 2025-26.
3. **Sanity:** kept-day Sharpe barely moves (~+/-0.003 vs full) — there is no fade tail to harvest;
   the Monday-gap-up subset is in-line-or-better than the book.
4. **MES 1m overnight cross-check** (75 Monday gaps, reported only): Monday gaps are mixed-sign and
   small (recent +0.22 / +0.93 / -0.19 / +0.79 %); no systematic up-gap-then-fade structure.

**Root cause (why it's DEAD):** the weekend/Monday effect is a **SPY cash-index calendar anomaly**,
aggregate and direction-agnostic — not a 0DTE option edge (C3/L58), and not a per-trade option timing
rule (C4/L166). The directional sign is also wrong for US: our edges are *trend-continuation*, and a
Monday gapping up into an established uptrend is exactly the regime they ride. Any weekend fade (if
present in this stretched-uptrend tape) is swamped by the continuation the edge captures.

**Disposition:** DEAD. Do NOT deploy a Monday-gap-up abstain/de-size mask — it removes winning days.
Add to the do-not-retest list: *weekday/calendar deploy-timing of the continuation edges*. The real
open problem (regime-timing the drawdown without winner-killing) is unaddressed by weekday/gap tags.

**Sources:**
- French (1980) "Stock returns and the weekend effect", J. Financial Economics 8(1) — Monday returns historically negative.
- Gibbons & Hess (1981) "Day of the Week Effects and Asset Returns", J. Business 54(4).
- Jegadeesh (1990) "Evidence of Predictable Behavior of Security Returns", J. Finance 45(3) — short-horizon reversal incl. weekend.
