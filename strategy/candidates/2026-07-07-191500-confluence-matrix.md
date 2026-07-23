# Strategy candidate: CONFLUENCE_MATRIX (multi-lens, multi-timeframe confluence sweep)

> DRAFT — Chef proposal 2026-07-07 19:15 ET. J ratifies.
> **VERDICT: NO-DISCIPLINED-CONFLUENCE-EDGE (OP-16 REJECT).** Two positive by-products J asked for
> are delivered (the b7 recalibration diagnosis + the multi-timeframe answer).

## Hypothesis
J's methodological correction: his edge is CONFLUENCE across multiple lenses + MULTI-TIMEFRAME, and a
new lens (level-memory) must be tested as a GATE LAYERED INTO a confluence matrix, not standalone. The
directional claim: some disciplined subset of {day-trendline reject, multi-day-trendline, named level,
level-memory role-flip, multi-TF agreement, VWAP-alignment} both FIRES on J's 3 real winners and clears
the 9-gate bar OOS on real OPRA fills.

## Backtest evidence
- Window: 2025-01-02 .. 2026-06-18 (real OPRA fills; `load_data` ignores the passed window and always
  returns the full master — verified this run, disclosed; there is no faster "smoke", the default run
  IS the full run, ~2.5 min).
- Candidate bars: 346 (one LM reject/retest per day in the 10:00–14:45 ET entry window).
- **Recalibration (the key fix) — RESULT: FAILED to capture J on the correct side.**
  - b7 fired 0/3 on J's winners because it required the day-trendline within $0.75-$1.00 of a multi-day
    *trendline*; **verified bar-by-bar** that on all 3 anchor days the multi-day resistance line sits
    $1.5 (4/29), ~$10 (5/01), ~$18 (5/04) away from price — the two structures are NOT co-located on
    J's trades. So mdt-colocation was replaced by a level-memory role-flip lens (the LM engine sees
    reject/retest at high-memory role-flipped levels on every anchor bar — mem 60-186, flips 5-25).
  - BUT: with direction derived from the LM level's role, the FIRST in-window reject bar reads **4/29
    and 5/01 (both J PUTs) as support → CALL** — the OPPOSITE of J. Only 5/04 comes out PUT. So the
    base fires 1/3 winners correct-side, and it fires on all 3 losers.
  - `combos_keeping_all_3_winners` correct-side = **[]** (empty). No lens subset captures J's 3 winners.
- edge_capture: **FAILS OP-16.** Best 9-gate-clearing cell takes **0/3 winners correct-side** and fires
  on **2/3 losers** → edge_capture is negative/anti-J, far below the 771 floor. REJECTED at the door.
- The single cell clearing all 9 gates (`req=[L_lm_reject,L_level,L_lm_flip,L_vwap]` ITM-2 / −50%):
  n=134, oos_exp=$83.71/t, posQ 4/6, top5% 83.1, fraud null_pass=True, no_truncation=True — **but it is a
  generic level-fade with no relation to J's source-of-truth trades** (anchor Wtaken=0, Lfired=2).
- FDR: 30 cells fraud-tested at q=0.10 → ~3.0 expected false discoveries. **1 survivor is at/below the
  noise floor.** Multiplicity, not signal.
- real_fills_validated: yes (per-trade real OPRA, C1).

## The multi-timeframe answer (J asked directly — DELIVERED)
Does a level respected on MORE timeframes (5/15/30/60m agreement) predict a bigger/more-reliable reaction?
**No — it predicts a SMALLER reaction. J's belief is refuted by the data.**
- corr(#agreeing-TFs, forward SPY excursion) = **−0.267**, monotone-increasing = **False**.
- Strata (mean forward excursion, $): 0 TFs → 3.15 | 1 → 2.11 | 2 → 1.47 | 3 → 1.03 | **4 → 0.88**.
- Interpretation: a level respected on many timeframes is a *consolidated/chopped-out shelf*; price has
  already spent its energy there, so the subsequent move is smaller. A level that only the fast TF
  "sees" (fresh, not yet chopped) precedes the bigger move. This is the opposite of "30m respects it
  more than 15m so the reaction is bigger." Actionable inversion (untested): MTF-agreement may be a
  *fade/avoid* filter, not a confirmation filter.

## Disclosures (per OP-20)
1. **Account-size assumption:** ATM (Safe-2) + ITM-2 (Bold), QTY=3, C29 tier lock. −50% catastrophe cap.
2. **Sample-bias:** all 3 J winners + 3 losers are 2026 (OOS) dates — an anchor take is a
   structural-fidelity check, not independent OOS evidence. The sweep found no anchor capture at all.
3. **Out-of-sample:** IS=2025 / OOS=2026. The one 9-gate cell is OOS-positive ($83.71/t) but anti-anchor.
4. **Real-fills check:** yes — real per-trade OPRA via `simulate_trade_real`; fraud gates (random-entry
   null L172 + truncation L171) run on the OOS-positive n≥20 cells.
5. **Failure-mode enumeration:** (a) LM-role direction is wrong for J on 2/3 winners (support/CALL where
   J was PUT); (b) no lens subset keeps all 3 winners; (c) the lone 9-gate survivor is a generic
   level-fade at the FDR noise floor; (d) volume-shelf lens is unusable on thin IEX data.
6. **Concentration:** best cell top5_day_pct = 83.1% (that cell only; irrelevant given OP-16 fail).

## Volume-shelf status
**OWED-PENDING-SIP.** SPY backtest volume is thin IEX (median 5m volume this run ≈ the C-note's ~1-2%
ADV; guard `_volume_usable` correctly refuses it, threshold 2e5). The HVN/volume-shelf lens was NOT added
(refused to fake it). Revisit only after a paid SIP backfill.

## Knob changes proposed
**NONE.** This is a rejected entry hypothesis. No `params.json` change. The perception/lens machinery is
retained as offline R&D infrastructure (potential VETO/input, per the level-memory verdict), not an entry.

## Pre-merge gate
`crypto/validators/runner.py` (gym) is unaffected — this fire touched only NEW files under
`backtest/autoresearch/` + `backtest/tests/`, no live/prod/params/heartbeat file. Relevant guard:
`backtest/tests/test_confluence_matrix.py` **9/9 PASS** + `test_level_memory.py` 5/5 PASS = 14/14.
Guards lock: MTF causality (planted-future pivot invisible), volume-refusal, strict-AND combo, forward-
excursion direction + look-forward-only.

## My confidence (1-10) and why
**8/10** in the REJECT + the MTF finding. The direction-mismatch (LM reads 2/3 J-PUT winners as CALL) and
the empty `combos_keeping_all_3_winners` are unambiguous, and the MTF anti-correlation is clean (−0.267,
monotone-decreasing across 5 strata, n=346). The lone 9-gate survivor is textbook FDR survivorship
(1 of 30 at q=0.10). This is the 5th ribbon/confluence-family kill: **J's edge is NOT a mechanizable
structural confluence at the 5m entry-bar level** — it is discretionary direction-reading (he shorts a
grind-down that a role-based level engine reads as a support bounce). The honest next lever is not "more
lenses" (that just overfits, as this proved) but capturing J's *directional context* (he was PUT into a
down-trending session regardless of the local level's role) — i.e. a trend/regime prior, not confluence.
