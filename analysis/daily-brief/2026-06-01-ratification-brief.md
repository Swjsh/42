# RATIFICATION BRIEF — Sunday June 1, 2026

## Engine status for Monday open
- Gamma-Safe: $747.11, 0/3 PDT, FLAT
- Gamma-Bold: $1,535.83, 0/3 PDT, FLAT  
- All 14 scheduled tasks: READY
- Ribbon at Friday close: BULL-stacked, Fast=756.67, Spread=23c
- VIX proxy: 15.04 (MID, bull-eligible <17.20)
- Macro Monday June 1: NO high-impact events. ISM is Tuesday June 2.

## Two candidates for J ratification this weekend (Rule 9)

### Option 1: RIBBON_MOMENTUM_GATE only
Params.json additions:
  "min_ribbon_momentum_cents": 5.0  
  "max_ribbon_duration_bars": 15   <- tighter, best WR
  "midday_trendline_gate": true

Full 16-month IS/OOS: WR 0.77, +28.3/c per-trade, WF 4.29, 48 OOS signals.
Anchor: 5/6 PASS, 4/29 captured +35/c, 5/04 captured net +8/c, losers skipped.
Threshold sweep: ALL 12 combinations pass WR>=0.71 — a PLATEAU, not a spike.
Production unchanged until ratified. Implemented in orchestrator.py (kwarg=off).

### Option 2: COMBINED (ribbon gate + V14E exits) -- recommended
All of Option 1 PLUS:
  "tp1_premium_pct": 0.30    (vs 0.75 production)
  "runner_target_premium_pct": 2.5  (vs 3.0)
  "profit_lock_threshold_pct": 0.05
  "profit_lock_stop_offset_pct": 0.10

Combined result: OOS WR 0.73, +25.7/c, WF 3.78. Anchor: 5/6 PASS +71.2/c.
The entries AND exits compound: separately 0.47 and 0.64 WR; together 0.73.

## What this means in plain English

Before: engine takes every setup that passes 11 filters. WR 0.30, +3.7/c.
After: engine checks 3 more visual conditions before entering:
  1. "Are the EMAs spreading apart?" (ribbon momentum >= 5 cents / 15 min)
  2. "Is this a fresh flip?" (not a 2-hour stale trend, <= 15 bars old)
  3. "Is this midday chop?" (skip weak trendline entries 11:30-14:00)

Engine takes 27% of its prior signals. Makes 43% more total money. WR from 0.30 to 0.77.
THIS is what it means to see the chart the way J reads it.

## What is NOT changing

- Rule 9 honored: production params.json and heartbeat.md are UNCHANGED until J ratifies.
- All three gates are implemented as off-by-default kwargs in orchestrator.py.
- No live orders placed tonight. No doctrine modified.
- BEARISH_REJECTION scope unchanged. BULLISH_RECLAIM still DRAFT.

## J weekend action items

1. Review analysis/recommendations/ribbon-gate-wf-scorecard.md (the ratification checklist)
2. Review analysis/recommendations/combined-ratification-proposal.md  
3. If satisfied, gamma-sync: update params.json + heartbeat.md simultaneously
4. Trade Monday with current v15.2 production (no change until gamma-sync)
5. SNIPER_VIX_TREND (rank 15) needs 3 live shadow trades before it can ratify — J can start logging those

## Kitchen queue
47 cooks pending (all medium/low priority, high-priority processed).
Key cooks active: threshold sensitivity OOS sweep, day-type combined gate test,
regime-adaptive filter live design spec, INTRADAY context score, ribbon equity curve deep dive.
Daemon alive at pid 11400. /usr/bin/bash paid tier cost today.
