# Winning-Trade Map — Fable synthesis (2026-07-20 evening)

> Input: [MAP-2026-07-20.md](MAP-2026-07-20.md) (n=27 real-fill episodes, 07-13..07-20,
> broker-truth reconciled). This doc is the judgment layer J asked for ("map some winning
> trades... purely logic now"). Every claim below carries its caveat — n=27 over 6 sessions
> in ONE regime (choppy-bearish week); nothing here ratifies by itself.

## The one-sentence read

Every dollar of profit this window came from BEAR trades entered at a level, aligned with
the higher-timeframe trend, that survived long enough to reach the trailing exit; every
bull-side entry (9/9 engine ones) and every sub-5-minute premium-stop death was a loss.

## Signals, ranked by strength × non-tautology

1. **Alignment sign at entry: 0/11 wins on positive-alignment entries (-$539), 6/15 on
   negative (+$625).** This is an ENTRY-TIME feature, not survivorship. CONFOUND disclosed:
   profit was all bear-side in a bear week, and alignment sign partially encodes direction.
   The clean test is the Phase-1 trend-alignment correlation scorer (built + frozen pre-reg,
   task completed 2026-07-16) run over ALL tagged decision rows — signals taken AND skipped —
   with nulls, not just these 27 fills. J pre-approved Phase 2 (conviction/sizing modulation,
   never trade-removal) if Phase 1 clears. → LEVER 1, dispatched tonight.

2. **Exit stage: trail 4/4 +$770, premium_stop 0/11 -$509.** PARTLY tautological (premium
   stop firing means the trade went against us). The non-tautological core: 7 of the 11
   premium-stop deaths were < 5-minute holds, and today's audit showed 2 of 3 morning
   stop-outs had ZERO SPY movement during the hold — the stop read spread noise, not price.
   All 11 came from lanes still running the old +30%/-8% premium bracket (extra-signal
   lanes) or pre-cooldown churn. Chart-stop-primary lanes produced every winner.
   → LEVER 2: counterfactual replay of those 11 episodes under the chart-stop shape,
   dispatched tonight (informs the queued EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT A/B; its
   pre-committed organic-n rule still gates the ship).

3. **Bull side: engine bull entries 0/9, -$513 this window** (BULLISH_RECLAIM 0/4 -$309,
   vix_regime calls 0/3 -$87, core reclaim -$117); the only bull winner was J's manual +$89.
   Consistent with the standing corrected evidence (live bull n=80, WR 1.2%). The 07-15
   fleet bleed was cheap OTM-3 757C lottery entries via the fleet "bold" tier table — the
   same floor-collision shape already killed on core Bold. NO unilateral fleet-grid rewrite
   (arms are frozen risk profiles; safe-3's OTM tier is deliberate); the new per-arm exit
   column + daily arm table now surfaces this bleed daily, and the standing bull re-eval bar
   (n>=20 under SS-B + ATM) accretes. Evidence filed; no ship tonight.

4. **Level proximity <$0.25 at entry: +$340 vs -$254 for $0.25-1.** Supports J's pong/zone
   thesis directionally; n too small to pre-reg a gate from this table alone. Folded into
   the premarket touch-credit study's scope (same instrument family: level-state quality).

5. **Time-of-day (09:30-10:30 = 0/8, -$347): heavily confounded** — the morning losers are
   dominated by the now-dead churn cluster (3) and the bull lane (3+). Not actionable as a
   time gate on this evidence; the goal-loop's prior finding (morning ELITE bear class +EV
   under correct exits) still stands on its larger window.

## What ships tonight vs what accretes

- SHIP-PATH (dispatched, gated on their own pre-regs): Lever 1 (Phase-2 alignment
  modulation A/B run-to-verdict), Lever 2 (premium-stop counterfactual replay, report-only).
- ACCRETES (instruments already live): per-arm exit-diversity table (from tonight),
  cooldown (shipped), bull re-eval n, EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT organic n,
  premarket touch-credit study (queued).
- EXPLICITLY NOT DONE: any gate/knob hand-fit to this 6-day window (anti-overfit law;
  C4 concentration, C24 anchor-trade lessons).
