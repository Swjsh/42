# All-green config — adversarial validation (CORRECTED)

**ACTUAL best config from the 256-combo sweep:** ATM strike, **-50% premium stop**, FIXED profit-lock (trailing PL OFF), TP1 +30%, qf 0.33, bull-trigger=1. Missed week: +521/+676/+393/+788 = 4/4 GREEN (+148.3/contract).

**The gate (OP-16):** a -50% stop is very wide (half the premium at risk). Does it still capture J's bear anchors, or does it let losers bleed to -50%? A config that wins the bull week but turns the bear book's small losses into -50% disasters is REJECTED.

## A) J-edge anchor window 2026-04-27..05-07 (bear puts; filter 8 off)
| config | trades | total/c | 5/04 capture | 4/29 capture | worst put loss/c |
|---|---|---|---|---|---|
| PROD (ITM2,-8%) | 10 | -14.7 | (53.6, '11:20', 721) | None | -25.2 |
| GREEN (ATM,-50%) | 17 | +5.7 | (31.2, '11:20', 719) | (41.8, '12:15', 710) | -58.0 |

**Gate A read:** GREEN must still show a 5/04 capture (a winning put). Compare the WORST put loss/contract: if -50% turns small -8% losses into deep -50% losses, that is the cost of the wide stop on the bear book — weigh against the bull-week gain.

## B) Missed week 2026-05-26..29 — GREEN vs PROD (per-contract by day)
| config | 05-26 | 05-27 | 05-28 | 05-29 | green | total/c | n |
|---|---|---|---|---|---|---|---|
| PROD (ITM2,-8%) | -19.7 | -25.3 | -21.4 | +46.6 | 1/4 | -19.7 | 4 |
| GREEN (ATM,-50%) | +23.7 | +30.7 | +26.2 | +48.8 | 4/4 | +129.4 | 5 |

## Verdict
- If GREEN keeps the 5/04 capture AND its worst-put-loss isn't catastrophically deeper than PROD's, the -50%-stop / no-trailing-PL finding is a real candidate for J + OOS.
- KEY SECONDARY FINDING from the sweep: pl-FIXED beat pl-TRAILING on 05-28 (+393 vs -94). The trailing profit-lock was arming on the chop then stopping out — it was PART of the chop problem, not just the stop width.
- HONEST RISK: a -50% stop means one max loss = half the position. Sizing/kill-switch interaction must be checked before this is anything but a research hypothesis (Rule 9).