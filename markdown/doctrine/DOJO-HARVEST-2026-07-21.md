# DOJO HARVEST — J's live reads, 2026-07-21 session (days walked: 07-21 + 07-17)

> Captured verbatim-in-substance from J's spoken reads during the first two real dojo
> walkthroughs. Two-lane routing per DOJO-REPLAY-TRAINING-SPEC.md. NOTHING here is ratified —
> Lane B items are hypotheses to pre-register, not rules to wire. Anti-overfit law binds:
> every observation below is n=1 or n=2 days.

## J'S READ — 2026-07-21 (bull day)

- 745.89 level: S/R-flipped in premarket. Bounced off it 04:10→07:00, broke through, then
  wicked off it from below at 08:10. **VERIFIED from tape**: dozens of touches 745.85-745.94
  in that window; 07:00 closed 745.50 (the break); 08:10 high 745.87.
- 745.39 level: real drawn line (confirmed 745.3926 from chart entity `zgMQiN`). **VERIFIED
  tagged at 09:20** (L745.36, closed back above). NOT tagged by the 10:15/10:25 candles —
  10:15 blew 59c through it to 744.795.
- Double bottom: 08:15 low 744.79 + 10:15 low 744.795 (half a cent apart). Shows identically
  on 5m/15m/30m because it is ONE structural low, not three confirmations.
- Entry: 11:05 bullish engulfing (O746.00 → C746.98, swallows prior red) at the double bottom.
  Engine read bull 9-10 at that moment and fired NO trigger.
- Multi-TF: engulfing present on 5m, 15m (10:15 bar) and 30m (10:00 bar); 30m ribbon stacked
  Fast 746.17 > Pivot 745.32 > Slow 745.06.
- **RULING on 12:21**: "in what world is that an entry? The move is already happening... that
  needs to get cut." VERIFIED: RSI(14) 68.8, +$4.40 off session low, no reset. Contrast 11:15
  (J: "would have been a fucking great entry"): RSI 63.6, +$3.23, and came right after RSI
  reset to 50.8 at 11:00. Structure: 10:40 L745.77 / 11:00 L745.83 / 11:05 L745.85 (three taps
  of one shelf) then 11:15 CLOSED 747.41 above the 10:30/10:45 highs (747.25/747.26).

## J'S READ — 2026-07-17 (reversal day, the +$679 day)

- Overnight gap down. Price comes up, tests the 745 level, sells off sharp.
- On the run up, **fills the gap (not a complete close)** — touches ~747.90, which is the WICK
  BOTTOM of the prior session's (2026-07-16) 15:45 candle. Touches that zone, then reverses down.
- Where it drops back to is the **middle of premarket** — an S/R flip level defined by: the
  05:30 candle top, the 04:15 candle dump at the start of premarket, and re-tested at 07:20.
  J: "so we know it's a significant level" — drew a line there live.
- Then: up to the gap level ~747.80 → REJECT → back down to the premarket level → back up →
  **rejects 747.48 again** → "kinda rides it and keeps rejecting it."
- **J's thesis: repeated rejection of the same level ⇒ put setup.** His own caveat, quoted:
  "obviously it's coin flip — it just depends if it's a level breaker or not."
- On the engine: **"very good that the engine got in at 13:01"**, and **"13:50 is a nice break
  and then retest — I like how it got in there too."**
- After the breakdown, price came back up ~**14:55 and retested the premarket level again**.
- Exit/target idea: could have targeted the **742.70** or **743.36** area for a sell/exit.

## QUANTIFIED FINDING (mine, from 07-17 real fills — the strongest of the night)

Same trigger family (`level_rejection + confluence`), opposite outcomes, split by ribbon state:

| entries | ribbon at entry | hold | result |
|---|---|---|---|
| 11:06, 11:40 | bullish + price riding it UP | 5-16 min | **-$37, -$102** |
| 13:01, 13:51, 13:52 | rolled over at the highs | 40-96 min | **+$241, +$191, +$233** |

Every 07-17 winner exited via `trail` after a 40-96 min hold; every loser via `structure_stop`
inside 16 min. -$139 vs +$665 on the same trigger type.

## LANE A — capability gaps (ship as plumbing, no pre-reg needed)

1. **Per-arm exits need one directive call each** — `directive.exits` is a single flat dict, so
   "puts on 2 arms with different stops" = 2 calls. Collapse to a per-arm map. (Found by the
   runbook builder; confirmed live this session.)
2. **No trigger vocabulary for "bullish engulfing at a level"** — J's 11:05 entry. The armed
   `double_bottom_base_quiet` detector has fired ZERO times since arming 2026-07-01 (20+ days)
   and stayed silent through a textbook double bottom. Detector is either dead-strict or broken.
3. **No vocabulary for "Nth rejection of the same level"** — J's core 07-17 thesis. `level_states`
   tracks touches but no trigger consumes a rejection COUNT.
4. **No vocabulary for "break and retest"** — J explicitly praised the 13:50 entry as this shape.
5. **No premarket-derived S/R levels** — J's 07-17 level came from 04:15/05:30/07:20 premarket
   structure. Engine's level set is RTH-derived (see the already-filed
   PREMARKET-TOUCH-CREDIT-STUDY, same root).
6. **Gap-fill / prior-session-wick levels absent** — J's 747.90 came from the PRIOR day's 15:45
   candle wick bottom.

## LANE B — policy hypotheses (MUST pre-register before any wiring)

1. **RIBBON-STATE-AT-ENTRY gate on bear entries** (the quantified finding above). Hypothesis:
   suppress/de-tier a bear entry while the ribbon is still stacked bullish and rising. STRONGEST
   candidate — has a real mechanism and a real dollar split, but n=2 days.
2. **EXTENSION/RSI-RESET block on ELITE bull** — already filed as RSI-EXTENSION-BLOCK-ELITE-BULL.
   Note textbook RSI>70 would NOT have caught 12:20 (68.8).
3. **EXIT HOLD-TIME / trail width.** Convergent from BOTH days: 07-17 real fills (winners =
   trail, 40-96 min; losers = structure_stop, <16 min) AND the 07-21 dojo sim (RIDE profile
   trail 0.30 beat CONTROL trail 0.15 by 42% on an IDENTICAL entry). Hypothesis: current trail
   is too tight / structure stop too quick. CAUTION: tonight's structure-stop-reference-level
   A/B already returned NO-SHIP for widening the stop REFERENCE — this is the trail-WIDTH axis,
   a different knob; do not conflate, and reconcile explicitly with that frozen result.
4. **Nth-rejection-of-level as a bear trigger condition** (J's 07-17 thesis, with his own
   coin-flip caveat — needs the level-breaker base rate measured before it's a rule).

## OPEN TENSION TO RESOLVE, NOT PAPER OVER
J has now supplied two filters that pull opposite ways: "let winners ride longer" (07-21 RIDE
result, 07-17 trail winners) and "don't enter extended" (12:21 ruling). Both plausible, both
small-n. They are NOT contradictory in principle (one is an EXIT knob, one is an ENTRY filter)
but a careless implementation could cancel them out. The battery reconciles them, not the chat.
