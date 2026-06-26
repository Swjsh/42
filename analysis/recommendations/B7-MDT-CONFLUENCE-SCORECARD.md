# B7 — Multi-Day-Trendline J-Confluence (Angle B) — Scorecard

## VERDICT: DEAD — structural multi-day-trendline confluence is a SPY-direction read, not a 0DTE option edge (C3/L58)

- Run: 2026-06-21  |  Window: 2025-01-02..2026-06-16  |  Trading days: 363
- Harness: `backtest/autoresearch/_b7_mdt_confluence.py` (new discrete-setup harness)
- Fills: real OPRA via `lib.simulator_real.simulate_trade_real` (C1); causal next-bar-open entry; chart-stop = session extreme
- Detector reuse: `crypto.lib.trendlines` (swing points + fit) + causal named levels (PDH/PDL/PDC/PMH/PML/IBH/IBL) + `infinite_ammo` day scaffolds + strike snapping
- Fraud gates: `fraud_gates` (random-null L172 + truncation L171)
- Tiers: ATM (Safe-2) + ITM-2 (Bold), C29  |  Stops: -8% / -20% / -50% / chart-stop-only
- **0 of 8 cells clear the 9-gate bar.**

## The setup tested

One causal entry/day: a bar **rejects a same-session trendline** while it sits **within tolerance of a multi-day trendline** (prior-4-day swings, ≥3 touches) **AND a named level**, same direction. STRUCTURAL co-incidence (all three align), NOT additive confluence scoring. This is the clean J 5/4 signature, never real-fills-tested as a discrete setup.

- N = 67 signals, fires **18.5% of days**, side split C:39 / P:28.

## RAW GRID — all 8 cells (no cherry-pick)

| tier | stop | n | exp/tr | OOS/tr | full drop-top5 | OOS drop-top5 | posQ | clears |
|---|---|---|---|---|---|---|---|---|
| ATM | -8% | 66 | +5.20 | +11.19 | **-11.53** | **-28.05** | 4/6 | NO |
| ATM | -20% | 66 | -17.16 | +1.54 | -35.73 | -46.33 | 2/6 | NO |
| ATM | -50% | 66 | -36.01 | -36.99 | -58.45 | -106.27 | 1/6 | NO |
| ATM | chart-only | 66 | -58.56 | -74.14 | -83.60 | -164.06 | 2/6 | NO |
| ITM2 | -8% | 64 | -6.82 | **+29.74** | **-35.90** | **-60.60** | 3/6 | NO |
| ITM2 | -20% | 64 | -44.53 | -11.77 | -80.36 | -149.70 | 2/6 | NO |
| ITM2 | -50% | 64 | -55.32 | -33.04 | -94.30 | -221.59 | 3/6 | NO |
| ITM2 | chart-only | 64 | -79.32 | -71.69 | -120.33 | -284.40 | 1/6 | NO |

**Best cell (ITM-2 / -8%):** OOS/tr +$29.74 (n=64, oos_n=13) — but fails decisively:
- G9 OOS-alone drop-top5 = **-$60.60** (remove 5 best OOS days → OOS goes negative)
- G5 full-sample drop-top5 = -$35.90  ·  G6 IS-first-half exp = -$16.15  ·  G2 posQ = 3/6  ·  G7 fails random-null
- **Every cell has NEGATIVE drop-top5 on BOTH the full sample AND OOS-alone.**

**The ATM "positive" is a pure truncation artifact (L171):** ATM/-8% chosen per-trade +$6.66 INVERTS to **-$51.72 at chart-stop-only** (`is_truncation_artifact=true`), and fails the null (null_max=+$33.78, beats_max=false). The capped-loss bracket is manufacturing the small positive, not signal.

## OP-16 anchor check — the "J 5/4 signature" is mischaracterized

| anchor | result |
|---|---|
| Winners taken (engine MUST take) | **0 of 3** — 4/29P, 5/01P, 5/04P all MISSED |
| Losers skipped (engine MUST skip) | 3 of 3 (4/05P, 5/06P, 5/07C) — but only because the setup fires almost nowhere |

J's anchor days **grind UP all morning**; his puts were **later-session rejections**. The morning-only multi-day-trendline version fires ~3×/363d and catches **0 anchors**. The setup does not reproduce J's actual entries — the "5/4 multi-day-trendline morning signature" is folklore, not what the tape shows.

## Two honest findings

1. **Structural multi-day-trendline confluence dies the same way the B0 additive triple-kill did (C3/L58):** the trendline-∩-level co-incidence is a SPY-direction read. Cheaper/righter strikes + capped losers shift magnitude, not sign — no option edge survives.
2. **The J 5/4 signature is mischaracterized:** anchor days are morning up-grinds with late-session put rejections, not a morning trendline-confluence trigger. The discrete morning version catches none of J's real winners.

## Disclosure
- Per-trade EXPECTANCY reported, not WR alone (OP-14). All J anchors fall in the 2026 OOS window → an anchor TAKE would be a structural-fidelity check, NOT independent OOS evidence (disclosed).
- Both tiers + 4 stops reported, no survivor cherry-pick (anti-2.10).
- Real OPRA fills; SPY-direction != option edge (C3/L58). Numbers from the actual `_b7_mdt_confluence.py` run (C7).
