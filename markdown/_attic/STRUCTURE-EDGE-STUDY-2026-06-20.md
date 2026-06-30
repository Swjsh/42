# Structure / Confluence Edge Study — 2026-06-20

> **Question:** does the new confluence read actually PREDICT SPY direction — i.e., as conviction rises, does forward edge rise? The elite move isn't more patterns; it's *measuring* edge on our own instrument.
> **Method:** [`backtest/autoresearch/structure_edge_study.py`](../../backtest/autoresearch/structure_edge_study.py) ran the confluence engine **causally** across **342 SPY days / 18,161 reads** (16 mo). Each read used only trailing bars; forward outcome = a ±0.15% directional bracket over the next 6 bars (~30 min), conservative (stop checked first). Raw JSON: [`analysis/structure-edge-study-full.json`](../../analysis/structure-edge-study-full.json).

## The honest verdict

**Confluence conviction is AWARENESS, not alpha.** Trading every signal is a coin flip.

| Cut | Win rate | Mean fwd (bps) |
|---|---|---|
| Overall (18,161) | 50.2% | +0.2 |
| Conviction 20-40 | 50.7% | +0.3 |
| Conviction 40-60 | 48.8% | +0.2 |
| Conviction 60-80 | 51.1% | 0.0 |
| Conviction 80-100 | 47.7% | +3.7 |
| **`conviction_monotonic_winrate`** | **FALSE** | — |

Conviction does **not** rise monotonically with forward win-rate. A higher confluence score does not, by itself, mean a higher-probability trade on raw 5m SPY.

## The one robust, corroborated effect: the bull tilt

| Bias | n | Win rate | Mean fwd (bps) |
|---|---|---|---|
| **bullish** | 10,112 | **52.0%** | +0.7 |
| **bearish** | 8,049 | **48.0%** | −0.4 |

A ~4pp bullish-vs-bearish asymmetry on an 18k sample — and it **independently corroborates the bull-tilt** the J-data campaign found from a completely different angle (see [`markdown/research/J-DATA-CAMPAIGN-FINAL.md`]). Two independent methods landing on the same asymmetry is the signal worth trusting. *Fresh* breaks (decision points, n=1,802) lean mildly better (51.1%) but not strongly/monotonically enough to claim as alpha.

## Why this is the *elite* outcome (not a failure)

An amateur ships the confluence engine assuming it works. We **measured** and found it's a coin flip per-bar — which **stops us from gating trades on a false signal.** That is the exact discipline (OP-16 measure-edge, anti-overfit, real-fills authority) that separates an elite desk from a chartist. We deliberately did **not** overfit weights to chase the fresh-break 52% — that's the multiple-testing trap the blueprint warns about (Deflated Sharpe / PBO).

## What the confluence engine IS good for (its real, validated role)

1. **Situational awareness / narration** — one synthesized read (bias, the confirming/conflicting factor stack, the invalidation level, a scenario line in J's language) instead of seven siloed signals. This is the `chart-read` skill's "wizard read."
2. **Conflict detection** — explicitly flags when structure, ribbon, VWAP, and levels *disagree* (the highest-information state).
3. **A screen, not a trigger** — narrow the universe; never size off conviction.

## Disclosure (load-bearing)

This study measures **SPY-price direction**, which is necessary but **NOT sufficient** for an **option** edge — delta/theta/stop-misfire corrupt the translation (C3 / L58). The **real-fills simulator remains the option-edge authority.** Before any structure/confluence signal becomes a live trigger: re-measure on real option fills, on the fresh-break + bullish subset, with DSR/PBO rigor.

## Next steps (DRAFT)
- Real-fills validation of the **fresh-break + bullish + mid-conviction** subset (the only lean worth chasing).
- Calibrate the `[def]`-tagged confluence weights from per-factor forward edge (currently reasoned defaults).
- Treat the **bull tilt** as a documented prior, not a hard-coded bias.
