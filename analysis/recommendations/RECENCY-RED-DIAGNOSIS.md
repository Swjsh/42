# RECENCY-RED DIAGNOSIS — edge #1 `vwap_continuation`

> **REGIME_UNFAVORABLE** — run 2026-06-21, recent window `2026-05-14..2026-06-18` (25 trading days), OPRA cache last 2026-06-18.

SAFE research, $0, NOT live path. Real OPRA fills (C1); detector + sim REUSED byte-for-byte from `recency_check.py` / `_edgehunt_vwap_continuation.py`. Per-trade EXPECTANCY, not WR (OP-14). RESEARCH ONLY — no live edit, no orders.

## Verdict

**REGIME_UNFAVORABLE**

- Variance: rolling-25 RED fraction per tier = 3.8%, 5.2%; current-window percentile = 0.0th, 0.0th; z-score = -2.2, -2.43.
- Decay: rolling-90d expectancy verdict per tier = ['DISCRETE_DRAWDOWN_STATIONARY', 'DISCRETE_DRAWDOWN_STATIONARY'].
- Regime: signatures flagged -> spy_20d_trend_pct_causal: recent median 5.367 is OUTSIDE winners' IQR [-0.33, 3.046] (winners median 1.686) -> possible signature | spy_20d_trend_pct_causal: recent median 5.344 is OUTSIDE winners' IQR [-0.33, 3.753] (winners median 1.764) -> possible signature

**Nuance: REGIME_UNFAVORABLE = tail-variance + a partial, ATM-only-gateable stretched-uptrend signature — NOT decay.** The dominant loss mechanism is premium-stop-out (C2/C3), and the trend gate is winner-costly on the worst-bleeding tier (ITM-2), so the honest action is HOLD-and-wait-for-CONFIRM, not gate-and-ship.

### Re-entry guidance

- **PRIMARY:** the recency RED is a genuine **~2.2–2.4 sigma TAIL** (0th pct; only 3.8%/5.2% of historical rolling-25 windows are RED) with **NO monotonic decay** (rolling-90d = discrete drawdown in a stationary mean). Worse than ordinary variance, but NOT alpha death.
- A real, **partial** regime signature exists: recent losers cluster in a **stretched uptrend** (SPY 20d causal trend median ~5.3% vs winners IQR top ~3.0–3.8%). It is the *only* feature that separates (rvol / VIX level+slope / side mix / day-label do not).
- **GATEABILITY (A/B on full history — C5/C22 mandatory check):** a `trend>3%` gate **HELPS ATM** (OOS exp $47.55 → $73, recent rescued to +$45, removed trades only +$694) but **HURTS ITM-2** (removes +$2,110 of profit AND recent stays −$94). DO NOT add a blanket trend gate to the live ITM-2/Bold tier — winner-costly there and does not fix the bleed.
- **MECHANISM:** 9/10 ATM and **11/11 ITM-2** recent losers exited on `EXIT_ALL_PREMIUM_STOP` (C2/C3 fingerprint). The bleed continued into normal-trend days (06-11/15/18) → premium-stop fragility, not just the regime, is doing the damage. Re-confirms standing doctrine: chart-stops > premium-stops on first-strike entries.
- **RE-ENTRY:** HOLD capital scaling on #1 until `recency_check.py` flips it to **CONFIRM** (recent exp/tr > 0, n ≥ floor). The gate is working correctly. Do NOT live-flip a blanket regime gate; the ATM-only trend tilt is at most a *research candidate* to A/B further, NOT a ship.
- **WATCH:** re-run weekly. Escalate to DECAY_CONCERN only if rolling-90d turns monotonically negative over 2+ more windows.

## Tier ATM (strike_offset +0)

- Full real-fills: n=157, exp/tr $45.01, std/tr $116.0, total $7065.96
- Full OOS-2026: n=50, exp/tr $47.55
- Recent window: n=10, exp/tr $-22.46, WR 10.0%

### 1. Variance test

- Rolling-25-trade windows: 133 windows, **3.8% RED**, window-mean distribution p05/p50/p95 = $2.55/$39.08/$93.91, std $30.49.
- Bootstrap (IID, n=20000): **9.6% RED**.
- **Current window** exp/tr $-22.46 -> **0.0th percentile** of rolling dist, **z = -2.2** (bootstrap pct 1.9, z -1.85).
- 3.8% of all rolling 25-trade windows are RED; current window per-trade $-22.46 sits at the 0.0th pct (z=-2.2) of the rolling distribution. BEYOND ~2 sigma -> unusually bad even for this high-variance edge (lean toward regime/decay).

### 2. Regime check (recent trades vs full-history winners)

- **spy_20d_trend_pct_causal**: recent median 5.367 (n=10, IQR [4.325,5.994]) vs winners median 1.686 (IQR [-0.33,3.046])
- **realized_vol_of_day_bp**: recent median 5.075 (n=10, IQR [4.822,6.025]) vs winners median 6.055 (IQR [4.388,9.262])
- **entry_vix_level**: recent median 16.735 (n=10, IQR [16.12,17.777]) vs winners median 17.415 (IQR [16.303,18.902])
- **entry_vix_slope_5bar**: recent median -0.03 (n=10, IQR [-0.087,0.18]) vs winners median 0.0 (IQR [-0.172,0.0])
- **day_followthrough_pct**: recent median 0.044 (n=10, IQR [-0.151,0.362]) vs winners median 0.126 (IQR [-0.34,0.583])
- Day-label mix — recent: {'CHOP': 4, 'MIXED': 1, 'TREND': 5}; winners: {'CHOP': 20, 'MIXED': 17, 'TREND': 41}
- Side mix — recent: {'C': 5, 'P': 5}; winners: {'C': 44, 'P': 34}
  - spy_20d_trend_pct_causal: recent median 5.367 is OUTSIDE winners' IQR [-0.33, 3.046] (winners median 1.686) -> possible signature
  - realized_vol_of_day_bp: recent median 5.075 within winners' IQR [4.388, 9.262] -> no clear signature
  - entry_vix_level: recent median 16.735 within winners' IQR [16.303, 18.902] -> no clear signature
  - entry_vix_slope_5bar: recent median -0.03 within winners' IQR [-0.172, 0.0] -> no clear signature
  - day_followthrough_pct: recent median 0.044 within winners' IQR [-0.34, 0.583] -> no clear signature

### 3. Decay check (rolling-90-calendar-day expectancy)

- Verdict: **DISCRETE_DRAWDOWN_STATIONARY** (OLS slope 0.221/step, Spearman r-vs-time 0.132, first-half exp $32.24 vs second-half $54.79).

## Tier ITM-2 (strike_offset -2)

- Full real-fills: n=158, exp/tr $69.53, std/tr $171.45, total $10986.12
- Full OOS-2026: n=51, exp/tr $73.66
- Recent window: n=11, exp/tr $-75.27, WR 0.0%

### 1. Variance test

- Rolling-25-trade windows: 134 windows, **5.2% RED**, window-mean distribution p05/p50/p95 = $-1.05/$52.22/$197.95, std $62.14.
- Bootstrap (IID, n=20000): **8.4% RED**.
- **Current window** exp/tr $-75.27 -> **0.0th percentile** of rolling dist, **z = -2.43** (bootstrap pct 0.0, z -2.81).
- 5.2% of all rolling 25-trade windows are RED; current window per-trade $-75.27 sits at the 0.0th pct (z=-2.43) of the rolling distribution. BEYOND ~2 sigma -> unusually bad even for this high-variance edge (lean toward regime/decay).

### 2. Regime check (recent trades vs full-history winners)

- **spy_20d_trend_pct_causal**: recent median 5.344 (n=11, IQR [2.505,5.917]) vs winners median 1.764 (IQR [-0.33,3.753])
- **realized_vol_of_day_bp**: recent median 5.14 (n=11, IQR [4.865,6.72]) vs winners median 5.6 (IQR [4.08,9.24])
- **entry_vix_level**: recent median 16.91 (n=11, IQR [16.17,18.225]) vs winners median 17.44 (IQR [16.26,18.91])
- **entry_vix_slope_5bar**: recent median 0.0 (n=11, IQR [-0.085,0.23]) vs winners median 0.0 (IQR [-0.22,0.0])
- **day_followthrough_pct**: recent median 0.066 (n=11, IQR [-0.13,0.496]) vs winners median 0.273 (IQR [-0.346,0.601])
- Day-label mix — recent: {'CHOP': 4, 'MIXED': 1, 'TREND': 6}; winners: {'CHOP': 17, 'MIXED': 17, 'TREND': 43}
- Side mix — recent: {'C': 5, 'P': 6}; winners: {'C': 44, 'P': 33}
  - spy_20d_trend_pct_causal: recent median 5.344 is OUTSIDE winners' IQR [-0.33, 3.753] (winners median 1.764) -> possible signature
  - realized_vol_of_day_bp: recent median 5.14 within winners' IQR [4.08, 9.24] -> no clear signature
  - entry_vix_level: recent median 16.91 within winners' IQR [16.26, 18.91] -> no clear signature
  - entry_vix_slope_5bar: recent median 0.0 within winners' IQR [-0.22, 0.0] -> no clear signature
  - day_followthrough_pct: recent median 0.066 within winners' IQR [-0.346, 0.601] -> no clear signature

### 3. Decay check (rolling-90-calendar-day expectancy)

- Verdict: **DISCRETE_DRAWDOWN_STATIONARY** (OLS slope 1.419/step, Spearman r-vs-time 0.37, first-half exp $38.4 vs second-half $108.52).

## Supplementary — A/B trend gate (C5/C22 winner-kill check)

Gate out days where SPY 20d causal trend > THRESH; report removed-trade total $, OOS-2026 kept exp, recent kept exp.

| Tier | thresh | removed (tot $) | OOS-2026 kept exp (was) | recent kept exp (was) |
|---|---|---|---|---|
| ATM | 3.0% | 54 (+$694) | $73.06 ($47.55) | +$45.0 (−$22.46) |
| ATM | 4.0% | 39 (+$725) | $69.96 ($47.55) | +$45.0 (−$22.46) |
| ATM | 4.5% | 32 (+$497) | $66.70 ($47.55) | +$17.44 (−$22.46) |
| ITM-2 | 3.0% | 54 (**+$2,110**) | $113.69 ($73.66) | **−$94.24** (−$75.27) |
| ITM-2 | 4.0% | 39 (+$1,277) | $108.49 ($73.66) | −$94.24 (−$75.27) |
| ITM-2 | 4.5% | 32 (+$699) | $103.48 ($73.66) | −$86.16 (−$75.27) |

**Read:** ATM → the trend gate is a *legitimately helpful* filter (raises OOS, rescues recent, removes little profit). ITM-2 → the trend gate is a **C5/C22 trap**: it raises per-trade exp but removes ~$2,110 of total profit and the recent window stays negative — it does NOT explain the ITM-2 bleed and would kill winners on the Bold tier.

## Supplementary — exit mechanism (the loss fingerprint)

- **ATM recent:** 9 of 10 `EXIT_ALL_PREMIUM_STOP`; the lone winner ran `TP1_THEN_RUNNER_RIBBON` (+$122.40, 06-18).
- **ITM-2 recent:** **11 of 11 `EXIT_ALL_PREMIUM_STOP`** — every recent trade hit the premium stop.
- The last 3 recent trades (06-11/15/18) fired in **flat/normal trend** (trend20 −1.65 .. +0.92) yet ITM-2 still stopped out on all 3 → the bleed is **NOT purely the high-trend regime**; the premium-stop-out mechanism (C2/C3) persists into normal-trend days.

---

Files: `analysis/recommendations/RECENCY-RED-DIAGNOSIS.json` (machine), `backtest/autoresearch/_recency_red_diagnosis.py` (this script).