# htf_15m morning-suppression measurement (G12, 2026-07-08)

**Question (gap-audit G12):** how often does the 09:30–11:00 ET `htf_15m` stack contradict the
realized session trend, and does it suppress ENTERs? Measured on `core-decisions.jsonl` (Safe
core), 9 trading days, no code change.

## Mechanism (verified first)
`htf_15m` is NOT a hard veto — it is a **−1 score modifier** on directional disagreement
(`filters.py:837` bull setup `htf != BEAR`; `:1144` bear setup `htf_disagrees = htf == BULL`).
So "suppression" is indirect: on a near-threshold score the −1 can tip it below the entry bar.

## Numbers
- Safe rows: 3190 · days: 9 · morning ticks (09:30–11:00): 708.
- Entry bar (min score that actually ENTERed): **bear 8**, bull 11.
- **htf_15m contradicts the realized day trend: 245/708 morning ticks = 35%.** (htf is a noisy
  morning direction signal — but 65% it AGREES, i.e. net better than a coin flip.)
- **Likely htf-suppressed near-threshold entries** (HOLD, realized-correct direction, htf
  disagreeing, score ≥ bar−1): **bear 16, bull 0.** The 16 are consecutive-minute clusters on
  a handful of setups (~3–5 distinct), scores all 7 (exactly 1 below the bar of 8), realized
  moves small (−0.91 to −2.99 SPY pts).

## Verdict — REAL but NOT clearly costly → DO NOT FIX (per G12: don't fix before measuring)
1. The suppressions are **marginal** (score 7 vs bar 8 — the exact cases the bar is meant to filter) on **small moves**.
2. This measures only the **cost** side; the −1 modifier's **benefit** (correctly vetoing wrong-way entries when htf agrees, 65% of the time) is unmeasured — concluding "htf is costly" would be one-sided (Fable: measure both nulls).
3. Proper settlement = an htf-modifier **on-vs-off A/B through the real engine on real fills** (bigger study). Not warranted tonight on a marginal signal.

**Monitoring datapoint filed:** the 35% morning-contradiction rate is worth watching; if it
climbs (htf turning actively anti-correlated with the session), re-open with the on/off A/B.
Guardable later via a periodic recompute of this script.
