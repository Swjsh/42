# Strategy candidate: 2-Miss Bull Gate (bull_score >= 9)

> DRAFT — Chef proposal 2026-06-17T21:44:42. J ratifies.

## Hypothesis

Relax the bullish setup gate from 11/11 strict to 9/11 (up to 2 non-structural filters may miss).
Structural filters {1,2,3,4,5} — time gate, news, kill-switch, day-trades, ribbon direction — cannot
be bypassed. Filters 6-11 (quality tiers: vol ratio, VIX levels, trendline, confluence) may miss up
to 2. The claim: some valid CALL entries are excluded by marginal filter conditions on reversal days
where J lost on PUTs.

**Critical scope note:** This candidate is a BULL expansion (adds CALL entries), not an improvement
of J's BEAR edge. J's source-of-truth winner trades (4/29, 5/01, 5/04) are PUT trades. The OP-16
score exceeds max_possible (1818 > 1542) precisely because the engine takes CALLS on J's loser
PUT days and wins — a fundamentally different instrument and direction.

## Backtest evidence

- Train/test window: 2025-01-02 to 2026-06-16 (full 16-month, J-day subset for OP-16)
- **J-day P&L detail:**
  - 4/29 (J PUT winner, +$342): engine = +$63 (baseline unchanged — no new call trades added)
  - 5/01 (J PUT winner, +$470): engine = +$1,636 (CALL trade fires on SAME DAY J had profitable PUT)
  - 5/04 (J PUT winner, +$730): engine = +$120 (baseline unchanged — no new call trades added)
  - 5/05 (J PUT loser, -$260): engine = +$204 (CALL trade fires — bull relaxation on bear day)
  - 5/06 (J PUT loser, -$300): engine = +$317 (CALL trade fires — bull relaxation on bear day)
  - 5/07 (J PUT loser, -$165): engine = +$178 (CALL trade fires — bull relaxation on bear day)
- edge_capture: 1818 (winner contrib = 63 + 1636 + 120 = 1819; loser exposure = 0 because engine
  MADE money on all three loser days via CALLS)
- **NOTE: edge_capture=1818 > max_possible=1542 — this indicates the OP-16 formula is being applied
  to a different strategy class (bull expansions on bear reference days). The metric is not
  measuring J's bear edge improvement — it's measuring a separate bull opportunity.**
- OP-16 floor (771): **PASS** (1818 > 771)
- aggregate sharpe: 5.099 (vs baseline 3.401)
- final_score: 1818 × 5.099 = **9,273**
- n_trades: 601 (vs baseline 361, +240 marginal trades — all bull/CALL direction)
- total_pnl: $44,662 (vs baseline $18,661, +$26,001)
- win_rate: 57.4% (vs baseline 54.6%)
- top5_pct: NOT COMPUTED
- positive_quarters: NOT COMPUTED
- max_drawdown: NOT COMPUTED
- real_fills_validated: NO

## What actually happened on each J-day

- **5/01**: The engine took a BULL CALL trade on the same day J's PUT made +$470. These are NOT
  simultaneous — the engine fires one direction per bar (bear vs bull trigger resolution picks the
  stronger). The $1,636 CALL gain on 5/01 suggests SPY had a bullish segment AFTER or BEFORE the
  bearish segment that J traded as a PUT. Both can be profitable on the same day.
- **5/05, 5/06, 5/07**: J took losing PUTs on these days. The bull relaxation found CALL entries on
  the same days and profited — consistent with "J was fighting the tape, the tape bounced." The engine
  with relaxed bull gate is CONTRARIAN to J's thesis on these days.

## Directional interpretation

A5's "edge" comes from a different setup class than BEARISH_REJECTION_RIDE_THE_RIBBON. It is
discovering that on J's worst PUT days, there are profitable CALL setups available. This is a genuine
finding about market structure (bear-day bounces) but:

1. It does NOT improve J's bear edge
2. It adds CALL risk on bear days, potentially in the same session as a PUT loss
3. The 5/01 CALL firing ($1,636) means the engine ignores a profitable bear opportunity in favor
   of a bull trade — this may or may not be net beneficial depending on timing

## Disclosures (per OP-20)

1. **Account-size assumption:** All trades at production sizing (OTM-2, 5 base contracts, $2K account).
   +240 marginal CALL trades added. These trades fire on different days and direction from J's anchor
   trades — sizing math applies independently.
2. **Sample-bias disclosure:** 5/01 CALL gain (+$1,636) is 89% of the winner contribution delta vs
   baseline. The 5/01 session was exceptional (SPY reversal from bear to bull intraday). Whether the
   bull relaxation consistently captures this pattern across the full 16 months is unknown without
   quarterly breakdown.
3. **Out-of-sample test result:** Full 16-month window only (no IS/OOS split). The "PROMOTE" verdict
   from OP-16 uses the formula in an unintended way — the formula was designed to score improvement
   on J's SPECIFIC trade setups, not to reward finding bull trades on bear days.
4. **Real-fills check:** NOT RUN. The +$1,636 on 5/01 via CALLS uses BS-sim. Real CALL pricing on
   5/01 (high-vol reversal day) may differ substantially.
5. **Failure-mode enumeration:**
   - Direction conflict: On 5/01, the engine takes a CALL while baseline takes a PUT. If a future
     session fires both, the engine must pick one direction per bar. The CALL may fire INSTEAD OF a
     profitable PUT.
   - Bull-in-bear-session risk: Relaxing bull filters to fire on 5/05-5/07 (confirmed bear days with
     sustained downtrends) adds tail risk. These specific sessions happened to bounce, but the
     STRUCTURAL reason is that VIX was declining on those days (bear exhaustion), not that bull_score
     relaxation specifically identifies bounce days.
   - OP-16 formula misapplication: edge > 1542 is structurally impossible under the formula's
     intended use (it assumes max winner capture is $1542). This candidate should be evaluated on
     aggregate Sharpe and WR improvement vs its OWN baseline, not via the bear-edge OP-16 formula.
   - +1 miss A4 (bull_score>=10) shows edge=-220 (FAIL). Only the 2-miss jump produces PASS. This
     non-monotone response (A4 worse than baseline, A5 much better) suggests a specific set of setups
     crosses the threshold between 10/11 and 9/11 that happen to be profitable — not a smooth
     degradation curve.
6. **Concentration: top5_pct = UNKNOWN.** With 5/01 contributing +$1,636 of the $26,001 marginal gain
   (6.3% of marginal P&L from one day), day-concentration may be acceptable. But full-window analysis
   required.

## Knob changes proposed

No params.json change recommended without further validation. Implementation would require:
- Adding `min_bull_score_override` param
- OR extending `allow_one_blocker` logic for bull setup

**Chef recommendation: VALIDATE, not PROMOTE.** This candidate needs:

1. Quarterly breakdown of the +$26,001 marginal CALL P&L — confirm dispersed, not concentrated in
   Q2-2026 tariff-bounce regime.
2. Real-fills validation on the 5/01 CALL trade specifically (high-vol reversal day pricing).
3. Separate OP-16 measurement for the BULL trade class using J's actual CALL winner trades as anchors
   (J's source-of-truth calls: if J ever takes a CALL trade that wins, those become the floor).
4. Walk-forward: IS 2025 vs OOS 2026 for the bull relaxation component specifically.

## Pre-merge gate

`python crypto/validators/runner.py` must show all stages PASS. Current status: 83/84 PASS (1
pre-existing failure, pre-dates this fire). No code changes proposed in this session.

## My confidence (1-10) and why

**3/10.** The OP-16 PASS is an artifact of the formula being applied cross-directionally — the engine
is discovering BULL trades on J's BEAR reference days. The aggregate Sharpe lift (+50%: 3.401→5.099)
and WR lift (+2.8pp) are real and encouraging, suggesting the 9/11 bull gate does capture genuine
signal. But the mechanism (bull-in-bear-session) needs a dedicated walk-forward with bear days as
the training ground, not the OP-16 bear-edge formula. The non-monotone response between A4 and A5
further reduces confidence. Worth a follow-up investigation as a pure BULL-strategy improvement,
disconnected from the OP-16 bear measurement.

**Status: VALIDATE — needs dedicated BULL OP-16 analysis before promotion**
