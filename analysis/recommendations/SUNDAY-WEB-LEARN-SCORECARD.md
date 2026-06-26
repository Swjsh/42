# SUNDAY WEB-LEARN SCORECARD
Real-data tests of web-sourced hypotheses on OUR cached data. $0, offline, no live edits.

---

## HEADLINE — what the web-learn batch LEARNED (synthesis, 2026-06-21)

**7 web-sourced hypotheses learned + real-fills-tested on our exact data (real OPRA fills, HARD-windowed ≤ 2026-05-29, C1). 6 DEAD, 1 LIVE_EDGE_IMPROVEMENT. The single shippable win: tighten the live chandelier trail BELOW the current 0.15.**

The three learn-angles (L1 time-of-day/IV microstructure, L2 exit/management, L3 sizing) all converge on a hard wall and one open lever:

- **L1 (time-of-day / intraday-IV microstructure) — WALL HELD, 4-for-4 DEAD.** The web picture is real and well-sourced (U-shaped realized-vol curve — Wood/McInish/Ord 1985, Harris 1986, Andersen-Bollerslev 1997; the 0DTE theta cliff after ~15:30; final-hour gamma/pinning compression to ≈0.62× the open-hour range, ≈0.46× on OPEX-Fri). But **none of it is actionable on edge #1** for one structural reason discovered across all four sub-studies: **`vwap_continuation` is a once-per-day, morning-trend-established detector hard-capped at `ENTRY_CUTOFF=10:30 ET`** — 153 of 158 real fills are ≤10:30 by construction. So the morning-restrict lever (changes 3 trades, +$0.00 OOS), the late-cutoff lever (zero entries fire 14:00–15:00; the lever is inert), the final-hour-pinning guard (the edge already enters morning-only + flattens 15:50), and the intraday-IV-regime gate (fails the random null p=0.355; OOS sign FLIPS — LOW VIX actually wins, which is edge #4 territory, not "elevated vol") are all DEAD. **The web research instead CONFIRMS why the morning-only + 15:50-flatten design is structurally — not just empirically — correct for a long-premium 0DTE buyer.** Re-confirms C3/L58 (a SPY realized-variance regularity ≠ a per-contract 0DTE option edge once theta/delta/stop-misfire are paid).
- **L2 (exit / trade-management) — 1 LIVE_EDGE_IMPROVEMENT (the only shippable result of the batch), 1 DEAD.** The two highest-profile management levers were already spent (earlier time-stop = NULL; vol-scaled/regime chandelier = INVERTED, tighter-fixed wins). The surviving lever — **tightening the v15 chandelier trail** — is genuinely a LIVE_EDGE_IMPROVEMENT, but the hypothesis premise was STALE: params.json **already shipped 0.20→0.15 LIVE on 2026-06-19**. The real finding is two-fold: (a) the 0.15<0.20 ship is RE-CONFIRMED on the vwap_continuation population specifically + survives WF; (b) **going TIGHTER STILL (0.125, 0.10) beats the current live 0.15 and clears the full L175 gate** (exp-lift + OOS-positive + per-trade Sharpe/Sortino/maxDD no-worse + anchor-no-regression). Mechanism (not a fluke): at the −8% premium stop, 148/149 trades exit on the premium stop and the chandelier almost never fires as a trailing exit — instead **the trail floor IS the runner profit-lock floor**, so a tighter trail locks winning runners HIGHER before they fade back into the −8%/ribbon stop. This is an EXIT knob on an already-live edge, so C3/L58 does NOT apply → SHIP-spec filed (see LIVE-PATH-WORKPACKAGE WP-6). The DEAD one: **TP1 +30%→+50% = L175_TRAP_REJECT** — the original +$90 vs +$78 lift was a CHANDELIER-OFF artifact; under the live trailing-0.15 config the trail/premium-stop fires before TP1 (148/149 EXIT_ALL_PREMIUM_STOP, TP1 fires once), so raising tp1 touches 1 trade → sub-$1.20 wiggles + per-trade Sharpe drop. A C30/L148 dead-knob masked by a dominant upstream exit (C14).
- **L3 (sizing / compounding) — already produced (B10-A → WP-3); not re-tested this batch.** The web sizing methods (RCK / VIX-rank / vol-targeting) remain testable against `_b10_sizing.py` but the standing recommendation (quarter-Kelly + min-3 floor, ruin 0.0, caps binding sub-$5K) holds; RCK/VIX-rank are the next sizing-research candidates ABOVE $5K where caps stop binding.

**HONEST WALL STATEMENT:** the web-learn batch did NOT find a new edge and was not expected to (the research frontier was already logged EXHAUSTED at B9/B10). Its value is (1) documenting that the time-of-day / intraday-IV angle is a WALL for edge #1 — preventing re-mining of a whole literature class — and (2) surfacing ONE clean shippable exit improvement (chandelier 0.15→0.125/0.10). **Single highest-EV next action: daylight-flip `v15_profit_lock_trail_pct` 0.15→0.125 (or 0.10) for the vwap_continuation book** — see WP-6.

**Untestable-on-our-data (marked testable=false, NOT mined):** real-time dealer-GEX/charm/vanna feed (1-day archive only — gamma-pinning ATTRIBUTION is unverifiable, we measure the realized effect not its cause), VIX1D/VVIX history, IV-surface history, options-flow tape, order-book depth.

---

## chandelier-tighten-20-to-15-oos-wf  (2026-06-21)
**Kind:** EXIT/MANAGEMENT change on LIVE edge #1 (vwap_continuation)

**STALE-PREMISE NOTE:** The hypothesis premise ('un-shipped forward-pointer, tighten 0.20->0.15') is STALE: params.json v15_profit_lock_trail_pct is ALREADY 0.15 (shipped LIVE 2026-06-19 via the full-engine reconfirm, scorecard weekend-fixes-live-reconfirm-2026-06-19.json). So the LIVE BASELINE is 0.15, not 0.20. This sub-study therefore re-frames the open question as: (a) does the 0.15>0.20 ranking hold on the vwap_continuation population + survive WF, and (b) does going TIGHTER than live (0.125 / 0.10) beat the current 0.15.

**Live cell tested:** ITM-2 / -0.08 stop / trailing arm@0.05 / tp1 0.5 / runner 2.5x. **Current LIVE trail = 0.15** (was 0.2 pre-2026-06-19).

**Fills:** real OPRA via lib.simulator_real (C1). HARD-window asserted <= 2026-05-29. Actual fill window `2025-01-02..2026-05-15`. Signals=158.

| trail | n | exp $ | OOS exp $ | posQ | Sharpe | Sortino | maxDD $ | anchor $ |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 149 | 80.62 | 98.1 | 6/6 | 9.73 | 15.907 | -315.12 | 145.5 (n=2) |
| 0.125 | 149 | 69.94 | 82.06 | 6/6 | 9.038 | 13.799 | -315.12 | 118.87 (n=2) |
| 0.15 (LIVE) | 149 | 59.94 | 67.09 | 6/6 | 8.362 | 11.827 | -315.12 | 92.25 (n=2) |
| 0.2 (prior) | 149 | 57.07 | 65.1 | 6/6 | 7.41 | 11.26 | -350.52 | 39.0 (n=2) |

**Monotonic (tighter beats wider on total P&L):** True

**L175 gate verdicts vs the current LIVE 0.15:**
- trail **0.1**: PROMOTE=True -- {'exp_lift_vs_live015': 20.68, 'oos_lift_vs_live015': 31.01, 'exp_better': True, 'oos_positive': True, 'sharpe_no_worse': True, 'sortino_no_worse': True, 'maxdd_no_worse': True, 'anchor_no_regression': True}
- trail **0.125**: PROMOTE=True -- {'exp_lift_vs_live015': 10.0, 'oos_lift_vs_live015': 14.97, 'exp_better': True, 'oos_positive': True, 'sharpe_no_worse': True, 'sortino_no_worse': True, 'maxdd_no_worse': True, 'anchor_no_regression': True}
- trail **0.2**: PROMOTE=False -- {'exp_lift_vs_live015': -2.87, 'oos_lift_vs_live015': -1.99, 'exp_better': False, 'oos_positive': True, 'sharpe_no_worse': False, 'sortino_no_worse': False, 'maxdd_no_worse': False, 'anchor_no_regression': False}

**VERDICT: PROMOTE trail(s) [0.1, 0.125]** -- clears expectancy-lift + OOS-positive + Sharpe/Sortino/maxDD no-worse + anchor-no-regression vs the live 0.15.


---

## tp1-partial-50pct-vs-30pct — vwap_continuation (#1) — 2026-06-21

**Claim:** Raising TP1 partial-out +30%->+50% (runner/trail/stop/qty held) improves vwap_continuation expectancy without tripping the L175 risk-adjusted gate.

**Kind:** EXIT/MANAGEMENT change on the LIVE edge #1 -> bar = expectancy lift AND L175 risk-adjusted gate (Sharpe/Sortino/maxDD not worse).

- Window loaded: 2025-01-02..2026-05-15 | HARD OPRA cap: 2026-05-29 (asserted) | OOS: IS=2025 / OOS=2026
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1); HARD-window asserted <=2026-05-29
- Detector: BYTE-FOR-BYTE _edgehunt_vwap_continuation.detect_signals (= live vwap_continuation_watcher port)
- Held constant (live config): tp1_qty=0.5, runner=2.5x, trail=0.15 (mode trailing, arm 0.05), stop=-0.08, qty=3. **Only tp1_premium_pct swept.**
- Signals: 158 ({'C': 86, 'P': 72})

### VERDICT: **L175_TRAP_REJECT**

#### Safe-2_ATM (strike_offset=0)

| tp1 | n | exp $ | OOS exp $ | WR% | posQ | top5%day | sharpe/tr | book Sharpe | book Sortino | maxDD $ |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.30 (baseline) | 149 | 49.84 | 60.79 | 55.0 | 6/6 | 22.5 | 0.5338 | 8.475 | 31.64 | -205.86 |
| 0.40 | 149 | 49.98 | 60.79 | 55.0 | 6/6 | 22.5 | 0.5339 | 8.475 | 31.735 | -205.86 |
| 0.50 | 149 | 50.13 | 60.79 | 55.0 | 6/6 | 22.4 | 0.5337 | 8.472 | 31.829 | -205.86 |

- **L175 tp1_40_vs_30**: PASS_RISK_ADJUSTED — exp Δ=+0.14, OOS exp Δ=+0.0, WR Δ=+0.0pp; higher_mean=True, per-trade Sharpe holds=True, book Sharpe holds=True, Sortino holds=True, maxDD worsen=+0.0% (material=False).
- **L175 tp1_50_vs_30**: L175_TRAP_REJECT — exp Δ=+0.29, OOS exp Δ=+0.0, WR Δ=+0.0pp; higher_mean=True, per-trade Sharpe holds=False, book Sharpe holds=False, Sortino holds=True, maxDD worsen=+0.0% (material=False).

#### Bold_ITM2 (strike_offset=-2)

| tp1 | n | exp $ | OOS exp $ | WR% | posQ | top5%day | sharpe/tr | book Sharpe | book Sortino | maxDD $ |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.30 (baseline) | 149 | 57.55 | 68.4 | 54.4 | 6/6 | 22.3 | 0.489 | 7.762 | 24.068 | -317.64 |
| 0.40 | 149 | 57.32 | 68.65 | 54.4 | 6/6 | 22.4 | 0.4852 | 7.703 | 23.971 | -317.64 |
| 0.50 | 149 | 56.35 | 67.09 | 54.4 | 6/6 | 22.7 | 0.4833 | 7.672 | 23.566 | -317.64 |

- **L175 tp1_40_vs_30**: L175_TRAP_REJECT — exp Δ=-0.23, OOS exp Δ=+0.25, WR Δ=+0.0pp; higher_mean=False, per-trade Sharpe holds=False, book Sharpe holds=False, Sortino holds=False, maxDD worsen=+0.0% (material=False).
- **L175 tp1_50_vs_30**: L175_TRAP_REJECT — exp Δ=-1.2, OOS exp Δ=-1.31, WR Δ=+0.0pp; higher_mean=False, per-trade Sharpe holds=False, book Sharpe holds=False, Sortino holds=False, maxDD worsen=+0.0% (material=False).

**How to read:** a higher TP1 partial mechanically LOWERS WR (first half banks less often) — expected, hence the gate is risk-adjusted not WR-based (OP-14). PASS requires dollar-expectancy to rise AND every risk metric (per-trade Sharpe, book Sharpe, book Sortino, maxDD) to hold; a dollar-exp rise with a Sharpe drop or maxDD blowout is the L175 TRAP and is REJECTED.

- _real_fills_: real OPRA fills, the only 0DTE WR authority (C1); SPY-dir != option edge (C3/L58).
- _wr_caveat_: a higher TP1 partial mechanically LOWERS WR -- the first half banks less often -- so WR delta will be negative; that is EXPECTED and is why the gate is risk-adjusted (Sharpe/Sortino), not WR-based (OP-14).
- _relative_comparison_: Sharpe/Sortino are RELATIVE (tp1 vs tp1 on the SAME trade set / SAME bull-flattered tape) so the bull bias cancels; the ABSOLUTE Sharpe is not a forward forecast.
- _tier_honesty_: C29 -- exit knobs do not transfer across strike tiers; ATM (Safe-2) and ITM-2 (Bold) reported independently; the live edge ships dual-account.
- _hard_window_: OPRA real-fill cache ends ~2026-05-29; every filled trade asserted <= that date so no blind-spot leakage inflates OOS.


---

## avoid_final_hour_pinning_compression_long  (2026-06-21)
**Kind:** EXIT/MANAGEMENT — entry-cutoff confirmation (NOT a new entry signal). Harness: `backtest/autoresearch/_web_avoid_final_hour_pinning.py`. JSON: `analysis/recommendations/_web_avoid_final_hour_pinning.json`.

**Web claim:** On non-expiration-Friday SPY 0DTE, the 15:00–16:00 ET window shows dealer-hedging-driven realized-move COMPRESSION / pinning toward heavy strikes, suppressing the sustained directional follow-through a long-premium buyer needs — so any vwap_continuation entry surviving into / initiated in the final hour underperforms, reinforcing an earlier cutoff + the 15:50 flatten. **Sources (web research):** the gamma-pinning / "max-pain" pin-toward-heavy-OI-strikes literature (SqueezeMetrics *Implied Order Book* / dealer-GEX framing; Spotgamma/Menthor-Q "positive net-gamma ⇒ dealers sell rallies/buy dips ⇒ realized-vol compression into the close on OPEX"); the well-documented intraday U-shaped volatility curve (high at open, trough mid-to-late session) — Harris (1986), Wood/McInish/Ord (1985), and the practitioner "lunchtime/afternoon lull" finding.

**Testable on OUR data:** PART A (realized compression) = YES, full SPY 5m window `2025-01-02..2026-06-16`, 359 days. PART B (late-entry option P&L) = YES on real OPRA fills (HARD-window asserted ≤ 2026-05-29; 4 post-window signals dropped). **Gamma/pinning ATTRIBUTION = UNVERIFIABLE** — no real-time GEX/dealer-positioning feed (1-day archive only). We measure the realized *effect*, not its cause.

### PART A — realized compression (SPY 5m, ATR-normalized), median final-hour vs open-hour range

| day-type | n | open-hr range/ATR | final-hr range/ATR | final/open ratio | % days final<open |
|---|---|---|---|---|---|
| **OVERALL** | 359 | 5.50 | 3.26 | **0.62** | **79.4%** |
| non-Friday | 287 | 5.50 | 3.32 | 0.63 | 78.0% |
| non-OPEX Friday | 56 | 5.23 | 3.18 | 0.58 | 83.9% |
| OPEX Friday (3rd Fri) | 16 | 5.74 | 2.78 | **0.46** | **87.5%** |

**Finding A:** Compression is **REAL and robust** — the final hour realizes a median 0.62× the open-hour range and is smaller than the open hour on ~4 of 5 days. The effect is **monotonically stronger** into OPEX (0.63 non-Fri → 0.58 non-OPEX-Fri → 0.46 OPEX-Fri), directionally consistent with the gamma-pinning story — though our data cannot confirm gamma is the *cause* (could equally be the generic intraday U-shape vol curve). Note the claim singled out *non*-OPEX-Friday, but our data shows OPEX-Friday is where compression is **strongest**, not weakest.

### PART B — late-entry vwap_continuation P&L (LIVE config: ITM-2, −8% stop, qty 3; real fills)

Relaxed the live ENTRY_CUTOFF from 10:30 → 16:00 to *try* to manufacture late entries. Fills=158, fill_rate 0.924.

| entry bucket | n | exp $/trade | WR % | total $ | median $ |
|---|---|---|---|---|---|
| MORNING ≤10:30 (live pop) | 153 | **+74.58** | 50.3% | +11,410 | +3.0 |
| MIDDAY 10:30–13:00 | 4 | +23.61 | 50.0% | +94 | +4.7 |
| AFTERNOON 13:00–15:00 | 1 | −54.24 | 0.0% | −54 | −54 |
| **FINAL HOUR ≥15:00** | **0** | — | — | — | — |

**Finding B:** Even with the cutoff fully relaxed to 16:00, the detector produces **ZERO final-hour entries** and only 5 non-morning entries total (153 of 158 fills are morning). The trend-side + first-continuation structure resolves in the morning by construction, so **there is no late-hour vwap_continuation entry for compression to suppress.** The "entry initiated in the final hour underperforms" clause is **moot for the live edge** — it cannot occur live (ENTRY_CUTOFF=10:30), and even unlocked it does not occur.

### VERDICT: **DEAD** (as an actionable change) / **CONFIRMS existing doctrine**
- **No new entry signal** (and none was claimed). The 11-gate entry bar is N/A.
- **No management change to ship:** the live edge already (a) enters morning-only and (b) flattens 15:50 — the two guards the claim asks for are *already in place*. Tightening the cutoff earlier costs nothing because ~all entries are ≤10:30 anyway; it also gains nothing because no late entries exist to cull. PART B has too few late entries (final-hour n=0) to even *judge* underperformance — `late_entry_underperforms = null (not judgeable)`.
- **What IS validated:** PART A independently corroborates *why* the morning-only + 15:50-flatten design is correct — final-hour SPY realized move is structurally compressed (0.62× open, 79% of days), which is hostile to a long-premium directional buyer (theta runs while range shrinks). This is a **doctrine-confirmation**, not a doctrine-change. Candidate lesson: "final-hour SPY realized range ≈ 0.6× the open hour (≈0.46× on OPEX-Fri); the morning-only cutoff + 15:50 flatten are structurally — not just empirically — correct for a long-premium 0DTE buyer." (Gamma attribution flagged UNVERIFIABLE.)

---

## vwap_cont_morning_iv_regime_filter  (2026-06-21)
**Kind:** ENTRY-candidate-shaping gate, ADDITIVE to LIVE edge #1 (vwap_continuation) — NOT a replacement, NOT a replacement for #4 vix_regime_dayside.

**Hypothesis (web-sourced):** Within the morning window, vwap_continuation entries taken while the intraday vol regime is ELEVATED (open-hour high-IV / wide realized 5m ranges) capture larger favorable moves for a long 0DTE buyer than entries once intraday vol has compressed toward the silent hour. An as-of-trigger-time intraday-realized-vol gate should improve the morning edge.

**Web basis:** U-shaped intraday volatility curve — Wood/McInish/Ord (1985, J. Finance); Harris (1986, JFE); Andersen-Bollerslev (1997, intraday seasonality); CBOE/Nasdaq first/last-hour liquidity notes. Realized variance is front-loaded at the open; long gamma wants range.

**Proxy disclosure (C3/L58):** We do NOT have intraday IV / VIX1D / IV-surface history. "IV regime" is PROXIED by (a) SPY trailing-6-bar realized 5m range % and (b) VIX 5m level — both computed strictly as-of the trigger bar, same-day only (L161/L166 no-look-ahead). A SPY-price-range gate is not an option-IV gate; this is the core caveat.

**Harness:** `backtest/autoresearch/_web_vwap_cont_iv_regime_filter.py` — reuses the byte-for-byte vwap_continuation detector + `simulate_cell`/`metrics`/`clears_bar` from `_edgehunt_vwap_continuation.py` + `lib.simulator_real` (real OPRA fills, C1). Raw: `analysis/recommendations/web-vwap_cont_iv_regime_filter.json`.

**Data:** SPY/VIX 2025-01-02..2026-05-15; real-fills HARD-WINDOW <= 2026-05-29 (asserted, 0 signals dropped). 158 morning signals -> 118 enriched with as-of rvol6 (40 dropped for <6 same-day prior bars). rvol6 median 0.116%, VIX median 17.52.

**Key numbers (median split: rvol_HIGH vs rvol_LOW; per-trade expectancy $):**

| Cell | ungated exp / oos | rvol_HIGH exp / oos | rvol_LOW exp / oos | vix_LOW exp / oos |
|---|---|---|---|---|
| ATM/chart-stop | 61.79 / 48.51 (n112) | 86.88 / **40.20** (n53) | 39.25 / **59.12** (n59) | 59.49 / 94.90 |
| ATM/-8% | 56.37 / 57.69 (n112) | 66.96 / 71.47 (n53) | 46.86 / 40.08 (n59) | 59.17 / **105.07** |
| ITM2/-8% | 94.69 / 100.85 (n112) | 100.01 / 112.02 (n53) | 89.92 / 86.58 (n59) | 116.33 / **196.61** |

**Independence vs #1's VIX gate (L174), orthogonal slice rvolHIGH∩vixLOW vs rvolLOW∩vixLOW:** positive IS delta at every cell (ITM2 +$39.3 IS, +$135 OOS) BUT n=16 (oos_n=5) — too thin, top5%=72-87% = concentration trap.

**Random-entry-time NULL (L172, ATM/-8%, 200 draws, seed 42):** actual rvol_HIGH gated exp $66.96 vs null mean $61.18, null p95 $80.15 — **beats-null p = 0.355.**

**VERDICT: DEAD.**

**Death (named honestly):**
1. **Fails the null (the decisive cut).** A random high-vol-day morning bar earns $61.18 vs the gate's $66.96 (p=0.355). The "lift" is just "trade on high-vol days," not "the rvol gate selects better entries." No selection alpha (C3 wall).
2. **The IS lift does not survive OOS at the chart-stop cell** — rvol_LOW actually beats rvol_HIGH out-of-sample ($59.12 vs $40.20). The hypothesis sign FLIPS OOS.
3. **The hypothesis is backwards on the real driver.** The strong, consistent OOS split is VIX-LOW (ATM/-8% $105, ITM2 $196 OOS), i.e. *compressed/low* vol days are best for the long buyer here — the OPPOSITE of "elevated vol captures larger moves." This is edge #4 (vix_regime_dayside, dormant) territory, already known; the rvol proxy partly re-discovers it with the wrong sign on the elevated side.
4. **Orthogonal slice is a concentration mirage** (n=16, oos_n=5, top5% up to 87%) — cannot clear the 11-gate bar (n>=20, drop-top5, OOS-alone).

**Takeaway / lesson candidate:** A SPY-realized-range "intraday IV regime" proxy adds no real-fill option edge over the existing morning timing on vwap_continuation; if anything the durable signal points the other way (LOW VIX favors the long buyer, consistent with edge #4). Confirms C3/L58: SPY-price vol != option edge, AND that the live VIX put-gate on #1 already captures the only orthogonal vol information we can test. Do not pursue an additive intraday-range gate without true intraday-IV data (which we don't have).

---

## vwap_cont_late_entry_theta_cliff_cutoff  (2026-06-21)
**Kind:** ENTRY-WINDOW change to LIVE edge #1 (vwap_continuation). Bar = expectancy lift vs the live cutoff + L175 risk-adjusted (Sharpe/Sortino/maxDD not worse) + no-regression.
**Harness:** `backtest/autoresearch/_web_vwap_cont_late_entry_theta_cliff.py` | **Raw:** `web-vwap-cont-late-entry-theta-cliff.json`

**Web hypothesis:** 0DTE theta decay is non-linear and accelerates into the close (decay >$2.00/hr on a $3 ATM near the bell vs ~$0.30/hr at the open). So a LATE long entry should earn worse net expectancy per unit of favorable SPY move than a morning entry; a hard entry cutoff EARLIER than the [09:35,15:00) limit should raise OOS expectancy without cutting trade count. (Theta-acceleration into expiry is standard options pricing — for an ATM option dTheta/dt grows as t->0; the 0DTE "theta cliff" / "charm into the close" is documented in CBOE 0DTE primers and standard Black-Scholes Greek behavior.)

**PREMISE CORRECTION (L171/OP-20 honesty — load-bearing):** The `[09:35,15:00)` window is the GENERIC heartbeat entry gate (`params.json:entry_no_trade_after_et=15:00`). The vwap_continuation DETECTOR that is actually LIVE (`backtest/lib/watchers/vwap_continuation_watcher.py`, `ENTRY_CUTOFF=dt.time(10,30)`) is hard-capped at **10:30 ET** — it only ever fires in the morning. So for edge #1 a 14:00/14:30 cutoff would be a *widening* (loosen) from 10:30, NOT a tightening from 15:00. Tested both ways: (1) does the cliff exist on real fills if we WIDEN to 15:00, and (2) is any earlier-than-15:00 cutoff an improvement vs the live 10:30.

**Fills:** real OPRA via `lib.simulator_real` (C1). HARD-WINDOW asserted per filled trade <= 2026-05-29. SPY 363 trading days 2025-01-02..2026-06-16. `win_end` swept {10:30(LIVE),11:30,13:30,14:00,14:30,15:00} on BOTH the validated ATM/chart-stop cell and the ITM-2/-8% live-class cell.

**Finding 1 — the detector self-selects morning; the window lever is inert.** vwap_continuation fires on the FIRST in-trend continuation bar of the day, so 153 of 158 entries are <=10:30 regardless of cutoff. Widening 10:30 -> 15:00 adds **only 5 trades over 18 months**; the 14:00 / 14:30 / 15:00 windows are byte-identical (zero signals fire 14:00–15:00). OOS lift of EVERY widened window = **$0.00** (all 5 extra entries are 2025/IS).

**Finding 2 — the theta cliff IS real (directionally confirms the web claim) but economically irrelevant here.** Stratifying the widest (15:00) window's net expectancy by entry hour:

| entry bucket | ATM n | ATM exp $ | ATM ret/prem | ITM2 n | ITM2 exp $ | ITM2 ret/prem |
|---|---|---|---|---|---|---|
| 09:35–10:30 | 153 | **+38.30** | +0.176 | 153 | **+74.58** | +0.144 |
| 10:30–11:30 | 3 | −79.00 | −0.222 | 3 | +49.32 | +0.066 |
| 11:30–13:00 | 1 | +69.00 | +0.200 | 1 | −53.52 | −0.080 |
| 13:00–14:00 | 1 | **−249.00** | **−0.748** | 1 | −54.24 | −0.080 |
| 14:00–15:00 | 0 | — | — | 0 | — | — |

Afternoon entries bleed (ATM 13:00–14:00 = −$249, ret-on-premium −0.75; ITM2 13:00+ both ~−$54) vs the strongly-positive morning bucket — exactly the theta-cliff signature. But n=4–5 afternoon fills total, so this is anecdotal, not an edge.

**Finding 3 — no cutoff change improves edge #1.** Every earlier-cutoff variant is DEAD vs the live 10:30 cell: OOS lift $0.00 and in-sample expectancy *falls* slightly when the bleeding late entries are admitted (ATM −$3.85/tr, ITM2 −$2.11/tr at 15:00); daily Sharpe drops (ATM 2.71->2.44; ITM2 6.89->6.76); L175 fails. The live 10:30 cutoff already captures the whole morning edge and excludes the late bleed.

**VERDICT: DEAD** (as a change to edge #1). The live 10:30 detector cutoff is already at/inside the theta-safe zone — it cannot be improved by any cutoff in {11:30..15:00}, and the cliff it would protect against (afternoon entries) never materializes because the first-continuation-bar structure self-selects the morning. The web claim is *directionally confirmed* on the handful of real afternoon fills but adds no actionable change. **Adjacent live note (separate money-path, out of scope on a weekend — flagged only):** the GENERIC 15:00 heartbeat gate DOES permit OTHER setups to enter in the theta-danger zone; the cliff evidence here is a reason to consider a tighter generic cutoff for those setups, requiring its own per-setup validation.

---

## vwap_cont_morning_window_outperforms_midday  (2026-06-21)
**Kind:** IMPROVES-EXISTING-EDGE on LIVE edge #1 (vwap_continuation) — restrict the live `entry_window`. Harness: `backtest/autoresearch/_sunday_vwap_cont_morning_window.py`. JSON: `analysis/recommendations/sunday-vwap-cont-morning-window.json`.

**Claim:** vwap_continuation entries in the realized-move-rich morning window (09:35–11:00 ET) have materially higher per-trade expectancy (return on premium) than 11:00–14:00 ET, because intraday realized variance is U-shaped — highest in the first hour, ~38% lower in the 12:00–13:00 "silent hour" — so a long-premium 0DTE buyer entered midday rarely earns the move to overcome benign theta.

**Web sources:** intraday volatility U-shape — Wood/McInish/Ord (1985, JoF); Harris (1986, JFE); Andersen & Bollerslev (1997, J. Emp. Finance) "Intraday periodicity and volatility persistence…" (realized vol troughs ~12:00–13:00 ET, the lunch lull). CBOE/practitioner notes on the 0DTE "theta cliff" (same-day theta accelerates into the afternoon → a midday long-premium buyer needs a bigger realized move just to break even).

**Method:** detector + sim + OP-22 `_full_metrics` scorecard imported **verbatim** from `j_entry_specificity.py` (`detect_j_cont_param`/`_sim`/`_full_metrics`/`_ship_gate`) — the parameterized clone of `detect_j_vwap_continuation`. SPY sliced + asserted `<=2026-05-29` (C1/L171) BEFORE day-contexts. ATM tier, both sides, real OPRA fills. Headline = per-trade expectancy + OOS + drop-top5; n>=20 per bucket required.

**Data:** SPY+VIX 5m, 351 trading days, 2025-01-02 .. 2026-05-29 (HARD-WINDOWed).

| bucket | n | exp $/t | exp %ret/t | WR | /wk | OOS exp $ | all-cuts-OOS+ | medWF | drop-top5 $ | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE 09:35–15:00 | 158 | +34.5 | +0.1624 | 75.9% | 2.25 | +22.3 | no | +0.556 | +20.93 | PASS |
| MORNING 09:35–11:00 | 155 | **+38.4** | **+0.1752** | 76.8% | 2.21 | +22.3 | no | +0.484 | +24.74 | PASS |
| MIDDAY 11:00–14:00 | 139 | +20.2 | +0.1165 | 76.3% | 1.98 | **+33.5** | **yes** | **+2.306** | +8.09 | PASS |

Contrasts: morning − midday = **+0.0587 %ret/t (+$18.2/t) in-sample** · morning − baseline OOS = **+$0.0**.

**VERDICT: DEAD** (refuted as a live-edge improvement). Death named:
1. **U-shape is visible in-sample but the restriction can't capture it.** vwap_continuation is a **once-per-day, morning-trend-established** detector (trend side fixed by the first 3 RTH bars; single daily entry usually fires before 11:00). The MORNING bucket (n=155) is ~98% the same trades as BASELINE (n=158) — restricting the live window to 09:35–11:00 changes **3 trades** and yields **+$0.0 OOS lift**. The edge already enters in the morning; there is nothing to improve. IMPROVES-EXISTING-EDGE bar (OOS lift vs baseline) NOT met.
2. **Where the windows actually differ, OOS inverts the thesis.** The MIDDAY-only sliver (rare days the entry slips past 11:00) has **higher** OOS expectancy (+$33.5 vs morning +$22.3), the **only** all-cuts-OOS-positive profile, best walk-forward (medWF +2.31), tighter tails (drop-top5 +$8.09). Morning's in-sample richness rides a fatter winner tail (morning drop-top5 $24.74 > full $20.93) that does NOT survive OOS — a C4/L173 in-sample-concentration tell.
3. **C3 / L58.** A SPY realized-variance regularity (lunch lull) ≠ a per-CONTRACT 0DTE option expectancy edge once theta+delta+stop-misfire are paid; morning's bigger realized move is offset by a bigger adverse-excursion stop-out tail. Net per-trade $ edge does not generalize OOS.

**Net:** no SHIP, no live edit. The continuous live `entry_window` is already correct (the edge is structurally a morning edge); tightening to 09:35–11:00 would drop the OOS-strongest midday sliver for zero baseline lift. Re-confirms C3/L58 + the once-per-day detector-shape caveat — no new lesson required.
