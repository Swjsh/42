# Strategy candidate: 3-Miss Bear Gate (bear_score >= 7)

> DRAFT — Chef proposal 2026-06-17T21:44:42. J ratifies.

## Hypothesis

Relax the bearish setup gate from 10/10 strict (all filters must pass) to 7/10 (up to 3 non-structural
filters may miss). Structural filters {1,2,3,4,5} — time gate, news, kill-switch, day-trades, ribbon
direction — cannot be bypassed. Filters 6-10 (quality tiers: vol ratio, VIX level, trendline, ribbon
duration, VIX delta) may miss up to 3. The claim: some very high quality bear setups are excluded by
marginal filter conditions on otherwise valid directional days.

**Measured via:** monkey-patch of `evaluate_bearish_setup` in backtest engine — passes result through
as `passed=True` when `bear_score >= 7` and no structural blocker fires and at least one trigger
fired.

## Backtest evidence

- Train window: 2025-01-02 to 2026-06-16 (full 16-month production data)
- Test window: J-day subset only for OP-16 edge measurement; full window for Sharpe
- **J-day P&L detail:**
  - 4/29 (J winner, +$342): engine = -$412 (LOSS — 3-miss allows poor quality entries)
  - 5/01 (J winner, +$470): engine = -$165 (LOSS — missed J's countertrend setup entirely)
  - 5/04 (J winner, +$730): engine = +$1,751 (WIN and 2.4x J's gain — multiple quality bear trades)
  - 5/05 (J loser, -$260): engine = no trade (AVOIDED — structural filters held)
  - 5/06 (J loser, -$300): engine = no trade (AVOIDED — structural filters held)
  - 5/07 (J loser, -$165): engine = +$192 (MADE MONEY on J loser day)
- edge_capture: 1174 ((-412) + (-165) + 1751 = 1174 winner contribution; loser exposure = 0 net)
- OP-16 floor (771): **PASS**
- aggregate sharpe: 6.389 (vs baseline 3.401)
- final_score: 1174 × 6.389 = **7,498**
- n_trades: 613 (vs baseline 361, +252 marginal trades)
- total_pnl: $71,858 (vs baseline $18,661, +$53,197)
- win_rate: 58.4% (vs baseline 54.6%)
- top5_pct: NOT COMPUTED — 252 marginal trades across full 16-month window, concentration unknown
- positive_quarters: NOT COMPUTED (full-window sweep, quarterly breakdown not extracted)
- max_drawdown: NOT COMPUTED
- real_fills_validated: NO

## Critical disclosures

### The 5/04 single-day concentration flag

**The +$1,751 on 5/04 is doing ALL the heavy lifting.** Without 5/04, winner contribution = -412 + -165
= -577. The engine LOSES on 4/29 and 5/01 (J's other two winner days) with this relaxed gate. The
OP-16 PASS is entirely driven by one day of massive bear-setup firing.

5/04 was an exceptional tariff-shock bear day. The 3-miss relaxation fires MORE trades on that extreme
day (possibly multiple setups across the session). This is the classic regime-concentration risk: the
parameter works on the highest-vol bear day in the dataset and may be trained on that outlier.

The J-day fast sweep (6 days) found 4 marginal trades total, with WR=0% on J-winner days (the 4/29
and 5/01 losses are the only J-winner fires that changed vs baseline). The 5/04 gain is NOT from 1
marginal trade — it's from multiple bear trades that baseline would not have taken.

### 5/01 structural miss

5/01 (+$470 J winner) fires a COUNTERTREND setup (ribbon=BULL, bearish rejection at FHH). This setup
requires filter_5 bypass and a separate BEARISH_REVERSAL class. Bear_score relaxation cannot capture
it — filter 5 is in STRUCTURAL_REQUIRED and is never relaxed by this candidate. Engine shows -$165 on
5/01 under A3 (same pattern as baseline minus a losing bear trade that the relaxed gate enabled).

## Disclosures (per OP-20)

1. **Account-size assumption:** Baseline params ($2K account, OTM-2 strike offset=0, 5 contracts base)
   apply. Trade count jumps +70% (252 marginal trades). At $2K account with per-trade risk cap, these
   additional trades may trigger kill-switch sooner on bad days.
2. **Sample-bias disclosure:** 5/04 extreme tariff-shock day drives 100% of the OP-16 pass. Without
   that day, edge_capture = -577 (FAIL). This is a single-day dependency, not a recurring pattern.
3. **Out-of-sample test result:** Full 16-month window used (no IS/OOS split). Quarterly breakdown not
   extracted. The A1 (1-miss) and A2 (2-miss) variants both FAIL OP-16, which establishes that the A3
   pass is marginal and regime-dependent (A2 at -592 edge suggests non-monotone response).
4. **Real-fills check:** NOT RUN. The +$1,751 5/04 figure uses BS-sim (use_real_fills=True in
   BASE_KWARGS but BS-sim for intraday option pricing). Given L71/L74 (real-fills often exceed BS-sim
   for TP1 captures), actual edge could be higher. But L100 (real-fills often fail for premium-based
   setups), the marginal trades need real-fills validation before production consideration.
5. **Failure-mode enumeration:**
   - Regime-specific: Only works in extreme high-vol bear sessions (tariff shock type). In trending
     bull or low-VIX environments, the 252 marginal trades are likely losers (relaxed quality gate
     = noise trades).
   - 4/29 regression: A3 LOSES -$412 on 4/29 where baseline made +$63. The relaxed gate fires a
     losing bear trade in a morning session that J's strict filter correctly avoided.
   - 5/01 loss: Same pattern. A3 loses -$165 on 5/01 where baseline loses only -$22.
   - Kill-switch interaction: +70% trade count on bad days could hit daily loss limits faster.
   - Non-monotone: A2 (8/10) has edge=-592 FAIL, A3 (7/10) has edge=+1174 PASS. This
     non-monotone response (8/10 worse than 7/10) strongly suggests the A3 PASS is one-day noise.
6. **Concentration: top5_pct = UNKNOWN.** The 252 marginal trades are not analyzed for concentration.
   Given 5/04 dominates J-day edge, full-window top5 is likely very high.

## Knob changes proposed

This is NOT a params.json knob — there is no `min_bear_score` parameter. Implementation would require
either:
- Adding `min_bear_score_override` param to `run_backtest` and `evaluate_bearish_setup`
- OR modifying `allow_one_blocker` logic to extend to N-blocker relaxation with a score floor

**Chef recommendation: DO NOT IMPLEMENT as-is.** The non-monotone edge (A2 fails, A3 passes) and
extreme 5/04 concentration make this a high-risk false positive. The right next step is:

1. Run quarterly breakdown on A3's +$53,197 marginal P&L — if Q2-2026 tariff shock is >80% of it,
   REJECT.
2. If quarterly is dispersed, run real-fills on a sample of marginal trades.
3. Re-evaluate A1 (9/10) for targeted use — 122 marginal trades with a smaller 5/04 outlier risk.

## Pre-merge gate

`python crypto/validators/runner.py` must show all stages PASS. Current status: 83/84 PASS (1
pre-existing failure, pre-dates this fire). No code changes proposed in this session.

## My confidence (1-10) and why

**2/10.** The OP-16 PASS is driven by a single extreme-vol day. The non-monotone response (A2 fails at
-592, A3 passes at +1174) is a red flag — it means the A3 edge is not from systematic bear_score
discrimination but from an outlier day in the 7-threshold window that the 8-threshold accidentally
excluded. The 5/04 concentration makes this a bet on tariff-shock recurrence, not a general
improvement. Genuine candidates would show monotone improvement (A1 < A2 < A3) not the observed
zigzag.

**Status: NEEDS-MORE-DATA (quarterly breakdown required before any promotion)**
