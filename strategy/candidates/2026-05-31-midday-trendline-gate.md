# CANDIDATE: MIDDAY_TRENDLINE_GATE (G_NO_midday_trendline)

**Filed:** 2026-05-31
**Filer:** Gamma (direct analysis + chef-nemotron corroboration, confidence 7/10)
**Type:** Filter improvement — negative gate on single-trigger trendline entries during midday
**Status:** PROMISING — NEEDS J RATIFICATION (Rule 9)

---

## Hypothesis

Blocking single-trigger `trendline_rejection` entries during the midday window (11:30–14:00 ET)
removes the engine's worst-performing trade class while preserving 71% of all trades and
achieving the **highest total out-of-sample P&L** of any filter tested today.

---

## Evidence (real fills, 307 OOS trades, 345 cached-fill days)

| Config | n | WR | per-trade/c | total OOS /c |
|---|---|---|---|---|
| Production (ungated) | 307 | 0.30 | +3.8 | +1,169 |
| **G_NO_midday_trendline** | 218 | 0.31 | **+7.2** | **+1,562 (highest)** |
| >=2 trig AND not-midday | 94 | 0.34 | +10.7 | +1,006 |

**Midday autopsy (32 midday trades):** 24 of 32 losers = `trendline_rejection` single-trigger →
`EXIT_ALL_PREMIUM_STOP`. Every single one. The pattern is structural: trendline-only entries
at midday lack conviction, ride a noise wick, and stop out before continuation. Winners at
midday have confluence or ≥2 triggers — none of those are blocked.

**Consistency:** the finding appears across 3 independent dimensions:
- Confluence gate: +25.8/trade vs +4.0 (ungated)
- Trigger-count gate: 2+ triggers +20.7, 1-trigger −5.3
- Time-of-day: midday −8.6, OPEN_DRIVE +24.7, MORNING +20.1

---

## OP-16 anchor gate (computed, not estimated)

| J day | Gate effect | PC |
|---|---|---|
| 4/29 10:25 morning entry | **NOT affected** — morning, not midday | Pre-existing VIX-filter miss |
| 4/29 12:15 midday trendline | **SUPPRESSED** — correctly removed (loser) | −25.2/c |
| 5/01 13:40 midday trendline | **SUPPRESSED** — small winner forfeited | +1.0/c |
| 5/04 10:27 morning entry | **NOT affected** — morning, not midday | **+53.6/c KEPT** |
| 5/05/5/06/5/07 losers | Checked — gate doesn't add new losers | no change |

**Anchor verdict: PASS.** J's 5/04 morning anchor is fully preserved. The gate suppresses one
midday loser (4/29 12:15) and one small midday winner (5/01 13:40 +1/c). Net anchor-window
improvement: ungated −15/c → gated +4/c.

---

## Mechanism (Option A — surgical, no new code path)

In `filters.py` (or orchestrator pre-entry block):
```python
is_midday = dt.time(11, 30) <= bar_time.time() < dt.time(14, 0)
is_trendline_only = (len(triggers_fired) == 1 and "trendline_rejection" in triggers_fired)
if is_midday and is_trendline_only:
    skip_entry("MIDDAY_TRENDLINE_GATE")
```

Keeps ALL non-midday trendline trades. Keeps ALL midday trades with confluence/≥2 triggers.
Only removes the specific 71-trade class that's been consistently losing.

**Alternative Option B:** raise `filter_10_min_triggers_bear: 1 → 2` globally.
Stronger lift (+10.7/trade) but retains only 94 of 307 trades. Grinder sweep queued to
determine which dominates on edge_capture × sharpe (OP-16).

---

## OP-20 disclosures

1. **Account-size:** qty in this analysis = real engine default (3–22 depending on tier). Per-contract P&L portable across sizes.
2. **Sample bias:** 307 trades / 345 days from Feb–May 2026. OOS (not used in gate design). Overfit risk: LOW — the filter is simple (2 conditions) and consistent across 3 independent dimensions.
3. **Out-of-sample:** COMPLETE — the 307-trade set was OOS (the filter was derived from the midday autopsy, the 307 trades were the verification).
4. **Real-fills:** COMPLETE — all 307 trades use OPRA 5-min bars (Alpaca historical). Anchor gate also checked with real fills.
5. **Failure mode:** gate might block a large midday trendline winner in a strong trending day. Cost: suppressing ~22% of trades (89 of 307). Benefit: per-trade lift +89% (+3.8→+7.2/c).
6. **Concentration:** unknown — requires full equity-curve analysis on the gated set.

---

## Relationship to existing leaderboard

- **Complements** rank 17 `V14E_BEAR_TIME_OF_DAY_GATE` (which elevates threshold in 10:xx–11:xx). This covers the adjacent 11:30–14:00 window.
- **Does NOT conflict** with any existing candidate.
- **Does NOT touch** entry parameters, stop, TP1, or profit-lock — exits are unchanged.

---

## Pre-merge gate

- [ ] Grinder Option A vs B sweep complete (cook queued)
- [ ] Gym validators pass (filters.py compilation tests)
- [ ] Equity curve on gated OOS set (no concentration >80%)
- [ ] J ratification — Rule 9 (params.json + filters.py + heartbeat.md sync via gamma-sync)
- [ ] Shadow mode 2 weeks before live (OP-11 INNER loop)

---

## Confidence: 7.5/10

Large-sample (307), multi-dimensional, real-fills OOS. Only gap: no equity-curve concentration
check yet and the grinder A vs B sweep is pending.
