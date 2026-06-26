# SUNDAY WEB-LEARN-2 — Managing a book of correlated/overlapping signals + 0DTE execution edges

Real-data tests of web-sourced hypotheses on OUR cached data. $0, offline, no live edits (Sunday/Mon
markets-closed; research track only). PASTE REAL NUMBERS (C7). Real OPRA fills = the only WR authority (C1).

---

## HEADLINE — what this web-learn LEARNED (synthesis, 2026-06-21)

**Frontier:** how do professional quant desks ALLOCATE capital across a book of HIGHLY-CORRELATED,
overlapping strategies (our #1/#2/#4 are all VWAP-native, all call/bull-biased, positively correlated
on the 2026 bull tape) — and is there any 0DTE-specific execution edge (limit-vs-market, opening
auction, partial fills) we have not tested?

**The single most-promising, our-data-testable idea — correlation-aware allocation (IVW / ERC /
min-variance) vs our live naive equal-weight book — was TESTED on real OPRA fills and is DEAD.**
**Every** correlation-aware scheme *lowers* both OOS book-Sharpe and book-Sortino vs the live
equal-weight (qty-3-each) book. Verdict: **DEAD_EQUALWEIGHT_HOLDS** (`web2-correlated-book-allocation.json`).

**The 0DTE execution-edge angles (limit-vs-market at the open, opening-auction timing, partial-fill
handling) are all `testable=false` on our data** — they need the L2 order book / real-time NBBO quote
tape / queue-position model our sim does not have (we fill on OPRA *trade prints*, not a microstructure
queue). Marked false honestly, NOT mined. See "Untestable" section.

**Why equal-weight wins here (the real learning, not a fluke):** the classic
diversification-from-correlation-aware-weighting result (de Prado HRP, Maillard ERC, min-variance)
assumes the streams differ enough that down-weighting a high-variance/high-correlation leg buys you
risk reduction worth more than the expectancy you give up. **Our three edges fail that premise**: they
are the *same bull-side long-premium bet* expressed three ways — all positively correlated
(IS corr e1/e2 = 0.33, e1/e4 = 0.43, e2/e4 = 0.02; Bold e1/e2 = 0.46), all individually
positive-expectancy, with similar daily vol ($107–$184 daily std). So any correlation-aware
down-weight just **discards expectancy from a profitable leg** without a compensating risk cut large
enough to raise the risk-adjusted return. This is a portfolio-construction corollary of **C3/L58**:
a textbook cross-asset technique does not transfer to a book of one-directional 0DTE option bets.

**Highest-EV next action:** NONE shippable. **Keep the live equal-weight (qty-per-edge, min-3-floor)
book.** The genuine deliverable is the documented WALL — correlation-aware reweighting of a
same-direction edge book is a dead lever; do not re-mine HRP/ERC/min-var for this book until the
book holds a *genuinely negatively/zero-correlated* edge (e.g. a real bear/short-vol edge — see
the B9-bear-book line — which would be the only condition under which diversification weighting pays).

---

## WEB RESEARCH — what the literature actually says (CITED)

### A. Allocating across correlated/overlapping strategies
- **Equal-weight (naive 1/N) is the baseline to beat, and it is hard to beat.** The classic finding
  (DeMiguel-Garlappi-Uppal "1/N") is that estimation error in the covariance/mean usually swamps the
  theoretical gain of optimized weights out-of-sample. Our live book IS naive 1/N (every edge fires
  qty=3).
- **Inverse-Variance Weighting (IVW):** down-weight higher-variance legs; the leaf step of de Prado's
  HRP. Ignores correlation. [Wikipedia — Inverse-variance weighting](https://en.wikipedia.org/wiki/Inverse-variance_weighting),
  [ml4trading.io ch.17 Portfolio Construction](https://ml4trading.io/third-edition/chapters/17_portfolio_construction/)
- **Equal-Risk-Contribution / Risk Parity (ERC):** each leg contributes equal risk; UNLIKE IVW it uses
  the correlation matrix, so two highly-correlated legs get jointly down-weighted ("33% in two perfectly
  correlated assets is really 66% in one"). Maillard-Roncalli-Teiletche (2010), "Properties of Equally
  Weighted Risk Contribution Portfolios."
  [robotwealth — EW covariance in ERC](https://robotwealth.com/exponentially-weighted-covariance-in-an-equal-risk-contribution-portfolio-optimisation-problem/),
  [QuantPedia — Risk Parity Asset Allocation](https://quantpedia.com/risk-parity-asset-allocation/)
- **Hierarchical Risk Parity (HRP), de Prado 2016:** cluster correlated assets so they "compete only
  against similar assets," then recursive inverse-variance bisection; lower OOS vol + higher
  risk-adjusted return than inverse-variance/min-var on large, structured universes. **Caveat for us:
  HRP's clustering value appears with MANY assets in MULTIPLE clusters — with 2–3 same-cluster edges
  there is nothing to cluster, so HRP degenerates to IVW/ERC** (which we tested directly).
  [gmarti — HRP implementation](https://gmarti.gitlab.io//qfin/2018/10/02/hierarchical-risk-parity-part-1.html),
  [QuantStratTradeR — de Prado HRP](https://quantstrattrader.com/2017/05/22/the-marcos-lopez-de-prado-hierarchical-risk-parity-algorithm/),
  [Wikipedia — Hierarchical Risk Parity](https://en.wikipedia.org/wiki/Hierarchical_Risk_Parity),
  [QuantPedia — HRP](https://quantpedia.com/hierarchical-risk-parity/)
- **Min-variance long-only:** the lowest-variance mix; tends to concentrate in the lowest-vol /
  least-correlated leg (it did exactly this for us — see below).

### B. 0DTE-specific execution edges
- **SPY 0DTE penny spreads but high *relative* cost:** quotes are $0.01–0.03 wide, but on a $0.15
  premium that's ~13% of value vs ~3% on SPX — so spread/slippage is a real, large drag for a
  frequent 0DTE buyer; this is the standard argument for SPX-over-SPY for 0DTE.
- **Market-vs-limit in fast 0DTE tape:** mid-price limits routinely don't fill while price runs away;
  practitioners recommend slightly *aggressive* limits (pay toward the natural/ask when buying) because
  "a penny of spread beats missing the trade." Spreads widen fast in volatile windows (open / final 30m).
- **Final-hour gamma / liquidity thinning:** many 0DTE desks flatten by ~15:00 ET (gamma extreme,
  liquidity thins) — consistent with our existing 15:50 flatten + morning-only entry (re-confirmed in
  SUNDAY-WEB-LEARN-1's final-hour-pinning study).
  [Alpaca — 0DTE explained](https://alpaca.markets/learn/0dte-options),
  [Schwab — 0DTE basics](https://www.schwab.com/learn/story/zeroing-on-0dte-options-learn-basics),
  [FlyOnTheWall — SPX vs SPY for 0DTE](https://flyonthewall.ai/spx-vs-spy-options/),
  [MarketXLS — 0DTE SPY playbook](https://marketxls.com/blog/how-to-trade-0dte-spy-options-expert-insights)

---

## TEST — correlation-aware allocation vs the live equal-weight book (real OPRA fills)

**Kind:** SIZING/ALLOCATION change on already-validated edges -> bar = **L175 risk-adjusted** (book
Sharpe AND Sortino no-worse AND maxDD no-worse AND OOS-positive; MATERIAL Sharpe lift > 0.05 to
PROMOTE). NOT the 11-gate (no new signal).

**Harness:** `backtest/autoresearch/_web2_correlated_book_allocation.py` — reuses the **byte-for-byte
B9 detectors + `simulate_set`** (`_b9_portfolio.py`) on real OPRA fills (C1). **JSON:**
`analysis/recommendations/web2-correlated-book-allocation.json`.

**Method (no look-ahead, L161/L166):** covariance/weights estimated **IN-SAMPLE 2025 only**, applied
**OUT-OF-SAMPLE 2026**. Weights normalized so equal-weight = all-ones (the live book is the unit
baseline). Schemes: equal-weight (LIVE) · inverse-variance · ERC · min-variance.

**Data:** SPY/VIX 5m 2025-01-02..2026-05-15, 342 trading days. HARD OPRA cap ≤ 2026-05-29 asserted
(0 post-window fills dropped). Signals #1=158, #2=81, #4=80.

### Safe-2 (ATM): #1 + #2 + #4 — IS corr e1/e2=0.326, e1/e4=0.431, e2/e4=0.015

| scheme | weights (IS-est) | OOS Sharpe | OOS Sortino | OOS maxDD $ | OOS total $ | ALL Sharpe |
|---|---|---|---|---|---|---|
| **equal_weight (LIVE)** | 1.00 / 1.00 / 1.00 | **6.896** | **33.55** | -836.40 | 4692.24 | 7.242 |
| inverse_variance | 0.54 / 0.78 / 1.68 | 6.610 | 29.64 | -726.55 | 4565.71 | 6.729 |
| equal_risk_contribution | 0.66 / 0.97 / 1.37 | 6.654 | 31.00 | -752.43 | 4446.98 | 7.027 |
| min_variance | 0.00 / 0.00 / 3.00 | 6.123 | 27.48 | -722.88 | 5007.72 | **4.524** |

### Bold (ITM-2): #1 + #2 — IS corr e1/e2=0.464

| scheme | weights (IS-est) | OOS Sharpe | OOS Sortino | OOS maxDD $ | OOS total $ | ALL Sharpe |
|---|---|---|---|---|---|---|
| **equal_weight (LIVE)** | 1.00 / 1.00 | **7.966** | **56.51** | -847.80 | 5734.12 | 7.546 |
| inverse_variance | 0.86 / 1.14 | 7.605 | 45.74 | -793.93 | 5285.04 | 7.412 |
| equal_risk_contribution | 0.93 / 1.07 | 7.793 | 52.45 | -820.73 | 5508.48 | 7.487 |
| min_variance | 0.74 / 1.26 | 7.242 | 41.85 | -754.41 | 4903.44 | 7.246 |

### L175 gate (each scheme vs equal-weight, OOS)
- Safe-2 inverse_variance: **PROMOTE=False** (Sharpe lift **-0.286**, Sortino_no_worse=False)
- Safe-2 ERC: **PROMOTE=False** (Sharpe lift **-0.242**, Sortino_no_worse=False)
- Safe-2 min_variance: **PROMOTE=False** (Sharpe lift **-0.773**, Sortino_no_worse=False)
- Bold inverse_variance: **PROMOTE=False** (Sharpe lift **-0.361**, Sortino_no_worse=False)
- Bold ERC: **PROMOTE=False** (Sharpe lift **-0.173**, Sortino_no_worse=False)
- Bold min_variance: **PROMOTE=False** (Sharpe lift **-0.724**, Sortino_no_worse=False)

### VERDICT: **DEAD_EQUALWEIGHT_HOLDS**

**Death named honestly:**
1. **Every correlation-aware scheme LOWERS risk-adjusted return OOS.** Sharpe drops -0.17 to -0.77,
   Sortino drops on all 6 cells. They DO cut maxDD (smaller book ⇒ smaller drawdown) but that is just
   de-leveraging, not diversification — the per-unit-risk return falls.
2. **The diversification premise fails because the edges are the same bet.** All three are
   long-premium, call/bull-biased, positively correlated, all positive-expectancy with similar daily
   vol. Correlation-aware weighting can only help when down-weighting a leg buys more risk reduction
   than the expectancy lost — here it doesn't, because there's no truly-uncorrelated leg to lean into.
3. **Min-variance exposes the concentration trap (C4/L173).** Safe-2 min-var collapses to **100% edge
   #4** (lowest variance + ~0 corr to #2). That *raises* OOS total ($5007 > $4692) — tempting — but its
   **ALL-window Sharpe is 4.52 vs equal-weight 7.24**, i.e. the single-leg concentration is fragile;
   the OOS "win" is one regime's luck, not a robust risk improvement. Exactly the kind of
   in-sample-flattering concentration the drop-top5 / OOS-alone gates exist to reject.

**No SHIP, no live edit.** Keep the live equal-weight (qty-per-edge, min-3 floor) book.

**Lesson candidate (folds into C3/C4 family):** *Correlation-aware capital allocation (IVW / ERC /
min-variance / HRP) does NOT beat naive equal-weight on a book of SAME-DIRECTION, all-positive-
expectancy, positively-correlated 0DTE edges — every reweight discards expectancy from a profitable
leg without a compensating risk cut. Diversification weighting only pays once the book holds a
genuinely zero/negatively-correlated edge (a real bear/short-vol leg). Until then, equal-weight +
min-3 floor is correct.* (Portfolio-construction corollary of C3/L58.)

---

## Untestable on our data (marked `testable=false`, NOT mined — honest WALL)

| Web idea | Why testable=false |
|---|---|
| **Limit-vs-market entry timing** (mid vs aggressive limit, fill-or-chase) | Our sim fills on OPRA **trade prints**, not a queue/NBBO model. We have no real-time bid/ask tape or queue-position to simulate "limit at mid didn't fill, price ran away." Cannot measure limit-vs-market slippage on our data. Needs the L2 book / quote tape (we have a 1-day archive only). |
| **Opening-auction (09:30:00) entry** | vwap_continuation's first-continuation-bar structure + 09:35 entry gate means it never enters at the auction; and we have no auction-imbalance/auction-print data to model an auction fill. |
| **Partial-fill handling** | No order-book depth / size-at-price; our fills are all-or-none at the print. Partial-fill modeling needs depth-of-book we lack. |
| **SPX-over-SPY spread saving** | A real edge in the literature (penny SPY spread = ~13% of a $0.15 premium vs ~3% on SPX), but we trade SPY by mandate (CLAUDE.md instrument lock = SPY 0DTE); not an allocation/sizing change we can test, and instrument switch is J's call, not a research-track ship. Flagged for J, not mined. |
| **Dealer-GEX / charm / vanna pin attribution** | (Re-confirmed from WEB-LEARN-1) no real-time dealer-positioning feed; 1-day archive only. |

---

## Cross-check vs prior work (no duplication)
- **B9** (`B9-PORTFOLIO-SCORECARD`) *measured* the correlated book (corr matrix, overlap, calendar
  routing) but never *allocated* weights — this study fills exactly that gap and finds equal-weight
  is already optimal, so B9's PORTFOLIO_MEASURED stands with no allocation change.
- **SUNDAY-WEB-LEARN-1** covered time-of-day/IV-microstructure (WALL), exit/management (chandelier
  tighten — the one ship), sizing (quarter-Kelly). This file is the NEW frontier: cross-signal
  allocation + 0DTE execution microstructure. No overlap.
- **B10-SIZING** covered *single-edge* position sizing (quarter-Kelly + min-3); this is *cross-edge*
  allocation — orthogonal, and it confirms you don't reweight BETWEEN the correlated edges.
