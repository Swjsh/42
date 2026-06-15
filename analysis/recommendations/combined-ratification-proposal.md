# COMBINED RATIFICATION PROPOSAL — Ribbon Gate + V14E Exits

> Filed 2026-05-31. RATIFICATION_READY. Both components tested and validated independently then combined.
> Rule 9: params.json + heartbeat.md change requires J ratification on a weekend.

## The Two-Part Proposal

### Part 1: RIBBON_MOMENTUM_GATE (entry filter)
Validates the entry bar has chart quality a human would recognize:
- Ribbon spreading >=5c over 3 bars (EMAs actively separating)
- Ribbon fresh <=20 bars (not a 2-hour exhausted trend)
- No single-trigger trendline in midday window (11:30-14:00 ET)

### Part 2: V14E exit params (better exits)
Earlier TP1 at +30% (vs +75%), wider runner to 2.5x, soft profit-lock at 5%/10%

## Combined OOS Result (16-month walk-forward, real OPRA fills)

| Config | IS n | OOS n | OOS WR | OOS /trade | WF ratio |
|---|---|---|---|---|---|
| BASE v15.2 | 154 | 158 | 0.33 | +6.1 | 5.545 |
| Ribbon gate only | 35 | 51 | 0.47 | +26.9 | 3.736 |
| V14E exits only | 167 | 175 | 0.64 | +11.1 | 1.682 |
| **BOTH (proposal)** | 35 | 52 | **0.73** | **+25.7** | 3.779 |

WR 0.33 -> 0.73: the entries + exits compound, not cancel.

## Params.json change when ratified


## Anchor gate (ribbon gate component)
5/04 721P: PASS (+53.6/c). Anchor window: BASE -14.7 -> gated +33.8/c.

## OP-20 disclosures
- Real OPRA fills; /usr/bin/bash.02 slippage; +/-5-10% vs live
- All gates are binary; threshold sensitivity sweep queued
- Rule 9: NOT ratified. J ratifies this weekend. gamma-sync required (simultaneous heartbeat.md + params.json update).
