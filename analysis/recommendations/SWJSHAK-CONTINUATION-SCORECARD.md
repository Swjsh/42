# SwjshAK Strategy Hunt — HONEST Scorecard

**Date:** 2026-06-20
**Source:** 4 strategies ported from J's separate SwjshAlgoKnife project, tested on REAL 0DTE OPRA fills.
**Survivor structure under test:** ITM-2 strike (`strike_offset=-2`) + tight −8% premium stop — the only profile that has ever survived 0DTE in this repo.
**Mandatory gates (OP-11 / OP-16):** all three must pass to be promotable.

| Gate | Requirement | Why it exists |
|---|---|---|
| **(a) OP-11 out-of-sample** | OOS-2026 per-trade **> 0** AND positive_quarters **≥ 4/6** AND drop-top-5-days per-trade **> 0** | Edge must persist forward and survive de-concentration. |
| **(b) Random-null** | Strategy per-trade **>** random-entry null (20 seeds) by a real margin | Proves the *signal* picks better than coin-flip entries, not just the bracket. |
| **(c) No-truncation** | Per-trade **sign stable** from −8% stop → chart-stop-only | If the sign inverts when the tight stop is removed, the "edge" was pure stop-truncation of a SPY-price signal, NOT a per-trade option edge. |

---

## Ranked scorecard (best → worst)

| Rank | Strategy | Class | n (trades) | Survivor-struct $/tr | OOS-2026 $/tr | Quarters | Drop-top5 $/tr | Random-null Δ | Truncation | Clears bar? | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **bollinger_squeeze** | continuation-breakout | 19 | **+57.28** | **−88.24** | 4/6 | **−467** | +45.6 (PASS) | sign-stable (SAFE) | **NO** | **DEAD** — signal-starved (n=19<20, 3 OOS), OOS sign-flips negative, all profit in <5 days |
| 2 | **ema_adx_gate** | continuation | 97 | +3.4 | **−8.4** | 4/6 | **−16.8** | +2.5 (pass, faint) | **sign INVERTS** (+3.4→−41.6) | **NO** | **DEAD** — textbook stop-truncation artifact: null-pass + truncation-fail = SPY-direction tilt, not option edge |
| 3 | **sd_zone_reversal** | reversion | 3 (PRIMARY) / 151 (companion) | +65.1 (n=3, meaningless) | −67.7 / −4.5 (companion) | 1/3 / 2/6 | n/a / −15.65 | inside null band (FAIL) | sign-stable (SAFE) | **NO** | **DEAD** — primary uninvestigable (n=3); powered companion genuinely negative, ties random |
| 4 | **three_ducks** | continuation | 351 | **−6.08** | **−9.27** | 1/6 | **−12.82** | **−9.68 (FAIL hard)** | sign-stable (both negative) | **NO** | **DEAD (worst)** — signal is $9.68/tr WORSE than coin-flip; MTF alignment actively harmful |

---

## Per-strategy detail

### 1. bollinger_squeeze (continuation-breakout) — DEAD
- **Best config:** ITM-2 (`strike_offset=-2`), −8% premium stop, v15 default exits.
- Survivor-struct **+$57.28/trade**, and it is **NOT a stop artifact** — passes random-null (+$57.28 vs null +$11.68) AND truncation (−8% +$57.28 vs chart-stop-only +$53.41, sign stable). The *signal* is real.
- **Why dead anyway — fails OP-11 on three counts:**
  1. **Signal-starved:** n=19 < 20 overall, only **3 OOS trades**. The squeeze→expansion→volume→band-break combo fired just 19× in 16 months.
  2. **OOS sign-flips:** OOS-2026 per-trade **−$88.24** (0/3 wins). The +$84/tr IS-2025 edge does NOT carry forward.
  3. **Concentration:** drop-top-5-days **−$467** (top5_day_pct = 143%). Entire IS profit lives in fewer than 5 days.
- **Diagnosis:** C3/L58 — a genuine SPY-price pattern with no durable 0DTE option edge once OOS-positivity + de-concentration are demanded.

### 2. ema_adx_gate (continuation) — DEAD
- **Survivor-struct +$3.4/trade** (97 real OPRA fills) looks positive, but it is the textbook **stop-truncation artifact**:
  - **(a) FAILS:** OOS-2026 per-trade **−$8.4** (sign flips OOS); top5-day concentration **574%** of total; drop-top-5-days per-trade **−$16.8**.
  - **(b) PASSES narrowly:** +$3.4 vs null +$0.9 (Δ +$2.5, 20 seeds) — a *faint* SPY-direction tilt.
  - **(c) FAILS:** per-trade **sign inverts** from +$3.4 at −8% to **−$41.6** at chart-stop-only (−99%).
- **The decisive tell:** (b)-pass + (c)-fail is the signature of a SPY-price signal whose "edge" is pure stop-truncation, not a per-trade option edge. Positive only because the tight −8% bracket cuts losers + 5 concentrated days carry it.
- **Secondary:** per-session ADX(14) warmup forces all signals to 11:00–15:50 ET, so the survivor profile's morning leg never engages.

### 3. sd_zone_reversal (reversion) — DEAD
- **Primary (09:30–11:00 ET morning retest):** only **4 signals / 3 fillable trades in 16 months** — uninvestigable per OP-11. The morning retest of a fresh impulse zone is a near-non-existent SPY 5m event (188 zones form, 166 retested, only 4 retests land in the morning window). The +$65/tr / beats-random / truncation-safe flags are **statistically meaningless at n=3.**
- **Powered all-RTH companion (n=151):** FAILS the bar — OOS per-trade **−$4.5**, total −$309, positive_quarters 2/6, drop-top5 per-trade −$15.65, WR 27.2%. Per-trade (−$2.0) sits **inside** the random-null band (min −$22.5 / mean −$2.92 / max +$10.3) → random ties it, no signal edge.
- Sign preserved −8%→−99% (−$2.0 → −$28.0) so NOT a truncation artifact — it is *genuinely* negative.
- **Diagnosis:** the expected 0DTE-wall failure for a counter-trend reversion class (C3/L58, C16).

### 4. three_ducks (continuation) — DEAD (worst)
- **Survivor-struct −$6.08/trade** over 351 trades (WR 21.9%, total −$2,134). Negative even in the best profile.
- **(a) FAILS:** OOS −$9.27, positive_quarters 1/6, drop-top5 −$12.82.
- **(b) FAILS HARD:** random-null is **+$3.60** while the strategy is −$6.08 → the signal is **$9.68/trade WORSE than coin-flip**. The MTF (4H+1H SMA60 regime + 5m SMA60 cross) alignment is *actively harmful*, not merely non-additive.
- **(c) PASSES** (sign stable, both negative) — moot, both are losers.
- All 12 sweep cells (offset {−2,−1,0} × stop {−0.08,−0.20,−0.50,−0.99}) negative; tighter stops only LOSE LESS, looser stops monotonically worsen → zero directional edge, pure theta bleed.
- **Causality (C6) hand-verified:** HTF regimes via `merge_asof(backward, allow_exact_matches=False)` on bar CLOSE times — 0 look-ahead violations across 1000 sampled bars.

---

## Thesis verdict

**ALL FOUR STRATEGIES ARE DEAD.** Zero clears the bar. No continuation-class strategy survived where reversion died — **continuation did NOT beat reversion here.** Both the best continuation strat (bollinger_squeeze, real-but-starved-and-non-OOS) and the worst (three_ducks, anti-edge) failed, and the reversion strat failed identically.

What this run actually shows:
- The "only trend-continuation + ITM-2 + tight-stop survives 0DTE" thesis is **NOT corroborated** by these four — but it is **not refuted** either. None of these four *was* a survivor; they are four more **0DTE-wall casualties** (C3 / L58 / L74). The class label (continuation vs reversion) did not predict survival; the **0DTE option wall** killed all of them regardless of class.
- The standout methodological win is the **(b)-pass + (c)-fail discriminator** (ema_adx_gate): it cleanly separates a true per-trade option edge from a SPY-price signal that only looks profitable because a tight stop truncates its losers. This is the diagnostic that should gate every future continuation candidate.

**RECOMMENDATION (OP-22): STOP.** This is a valid terminal state. The SwjshAK port is exhausted — all 4 extracted rules are confirmed dead on real 0DTE fills. Do NOT flip any of these live. Do not sweep further configs (the sweeps are saturated: every cell is negative or non-OOS). Bank the lesson and move the loop to the next bounded task per OP-22 priority order.

**Lesson to encode (candidate L###):** A continuation/equity/FX trend-following rule that is (b)-null-positive but (c)-truncation-negative is a SPY-direction tilt cashing in on stop-truncation, NOT a 0DTE per-trade option edge — reject on truncation-fail alone even when OOS and random-null look acceptable. (Generalizes C3 with an actionable two-test discriminator.)

---

## Artifacts

- `analysis/recommendations/swjshak-bollinger-squeeze.json`
- `analysis/recommendations/swjshak-ema-adx-gate.json`
- `analysis/recommendations/swjshak-three-ducks.json` (script: `backtest/autoresearch/_swjshak_three_ducks.py`)
- `analysis/recommendations/swjshak-sd-zone-reversal.json` (script: `backtest/autoresearch/_swjshak_sd_zone_reversal.py`)
- Extraction source: `markdown/research/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md`
