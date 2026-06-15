# Premarket Dry-Run — Monday June 1, 2026

> Generated autonomously 2026-05-31 from verified Alpaca SIP data. VIX is a VIXY proxy.
> This is a simulation of what Gamma_Premarket will produce at 08:30 ET Monday.

## Price Context (from Friday May 29 close)

| Level | Price | Type |
|---|---|---|
| Friday RTH High | 758.08 | PDH (resistance) |
| Friday Close | 756.40 | PDC |
| Friday Open | 755.90 | — |
| Friday RTH Low | 754.69 | PDL (support) |
| Week High | 758.08 | 4-day range top |
| Week Low | 747.38 | 4-day range bottom |
| Round number | 755.00 | Psychological |
| Round number | 750.00 | Psychological (week low area) |

## Ribbon (Friday close)
Stack: **BULL**  
Fast: 756.67 | Pivot: 756.58 | Slow: 756.44  
Spread: 23¢

## VIX Context (Friday close proxy)
VIX proxy close: **15.04** (MID regime)  
Bull eligible (VIX < 17.20): **YES**  
Bear eligible (VIX > 17.30 rising): **NO** (VIX comfortably below threshold)

## Monday June 1 Macro Calendar
- **NO PRE-MARKET HIGH-IMPACT DATA** — clean open
- ISM Manufacturing: **JUNE 2** 10:00 ET (not today)
- NFP: June 5. FOMC: June 16-17.
- Monday June 1 is a FREE session — no macro blocks on the tape.

## Engine Status
- Both accounts FLAT, 0/3 PDT used (reset), ACTIVE
- Safe: $747.11 | Bold: $1,535.83
- VIX in MID regime: BEARISH_REJECTION eligible if VIX >17.30 rising (currently NOT)
- BULLISH_RECLAIM eligible (VIX <17.20) — DRAFT status, needs 3 live J wins

## Ribbon Gate Status (pending ratification)
The RIBBON_MOMENTUM_GATE (WF=3.74, RATIFICATION_READY) is LIVE in orchestrator.py but
OFF by default until J ratifies. Production runs standard v15.2 rules.

## Falsifiable Hypotheses for June 1

**Primary (base case — SPY near highs, low VIX, no catalysts):**
SPY opens near 756.40 and grinds higher in the first 90 minutes. The ribbon at open
is likely BULL-stacked from
Friday's 756.40 close. First meaningful test: whether Friday's high 758.08 acts as resistance.
Invalidation: gap below 754.69 (Friday low) on open OR VIX spikes above 17.30.

**Bear setup condition (BEARISH_REJECTION would fire):**
If SPY rallies to 758.08+ and fails with a rejection candle, ribbon BEAR-stacks,
VIX ticks above 17.30 rising → bearish rejection setup. Level: 758.08 area.
RIBBON_GATE qualification: need spread widening ≥5¢, stack fresh ≤20 bars.

**Bull setup condition (BULLISH_RECLAIM — DRAFT, monitor only):**
If SPY dips to 754.69–755.00 and reclaims with ribbon flip to BULL → bull reclaim.
Not live in production (DRAFT status, OP-16 scope lock). Heartbeat will log but not trade.

## What to watch in the first 15 minutes
1. **Gap direction from 756.40**: >+0.5% = gap-and-go setup for BULLISH_RECLAIM
2. **Ribbon spread at 09:40**: widening from open = trend forming; compressing = chop day
3. **PDH 758.08 hold vs break**: if SPY pops above and holds, first support = 756.40
4. **VIX at open**: any move toward 17.30 = bear setup window opens

## RIBBON_GATE pre-trade checklist (for manual reference)
Before entering ANY setup today, check:
- [ ] Ribbon spread widened ≥5¢ in last 15 minutes (3 bars)?
- [ ] Ribbon has been stacked ≤20 bars in current direction?
- [ ] If 11:30-14:00 ET: does setup have ≥2 triggers or a level_rejection?
If all three: ENGINE ENTERS. If any fail: skip or wait for next setup.