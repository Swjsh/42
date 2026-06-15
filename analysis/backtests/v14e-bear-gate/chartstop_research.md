# V14E Bear Chart-Stop Research — L51 Analog

> Generated: 2026-05-21 by v14e_chartstop_research.py
> Question: does the -8% premium stop fire BEFORE the directional bear move?

## Summary

| Metric | Value |
|---|---|
| Total stopped high-conf bear obs | 5 |
| L51 analog confirmed | 5 / 5 with data |
| No option data | 0 |
| **Recommendation** | **SWITCH_TO_CHART_STOP** |

## Per-Observation Detail

### 2025-01-07 10:35 — VIX_MODERATE (VIX=17.82, score=9)

- Entry: SPY 596.25 | Chart stop: 597.2 (+0.95) | Original P&L: $-95.0
- Triggers: ['trendline_rejection', 'level_rejection', 'confluence']
- Jan 7 2025 — the sole VIX_MODERATE loss

**Option data:** SPY250107P00594000 (strike 594)
- Entry premium (bar-0 VWAP): $0.6545
- -8% stop threshold: $0.6021
- Premium stop fires: bar 1 (10:45:00) drop=-38.9%
- Bear confirmation (SPY<entry): bar 1
- Chart stop (SPY>597.2): bar None
- SPY adverse move first: False
- Max adverse exposure bars 1-3: +-5.43c
- **Conclusion: PREMIUM_STOP_FIRES_BEFORE_BEAR_MOVE** | L51 analog: True

**SPY path (bars 0-5 after entry fill):**

| Bar | Time | O | H | L | C | vs_entry |
|---|---|---|---|---|---|---|
| 0 | 10:40:00 | 590.06 | 590.58 | 589.86 | 590.58 | -5.67 |
| 1 | 10:45:00 | 590.62 | 590.82 | 590.01 | 590.01 | -6.24 |
| 2 | 10:50:00 | 590.07 | 590.27 | 590.04 | 590.11 | -6.14 |
| 3 | 10:55:00 | 590.15 | 590.22 | 589.97 | 590.0 | -6.25 |
| 4 | 11:00:00 | 590.04 | 590.06 | 589.34 | 589.67 | -6.58 |
| 5 | 11:05:00 | 589.62 | 589.83 | 589.09 | 589.09 | -7.16 |

### 2025-02-27 11:00 — VIX_ELEVATED (VIX=21.16, score=10)

- Entry: SPY 591.85 | Chart stop: 592.2 (+0.35) | Original P&L: $-35.0
- Triggers: ['ribbon_flip', 'level_rejection', 'confluence']
- Feb 27 2025 — VIX_ELEVATED

**Option data:** SPY250227P00590000 (strike 590)
- Entry premium (bar-0 VWAP): $1.4705
- -8% stop threshold: $1.3529
- Premium stop fires: bar 1 (11:10:00) drop=-49.0%
- Bear confirmation (SPY<entry): bar 1
- Chart stop (SPY>592.2): bar None
- SPY adverse move first: False
- Max adverse exposure bars 1-3: +-3.87c
- **Conclusion: PREMIUM_STOP_FIRES_BEFORE_BEAR_MOVE** | L51 analog: True

**SPY path (bars 0-5 after entry fill):**

| Bar | Time | O | H | L | C | vs_entry |
|---|---|---|---|---|---|---|
| 0 | 11:05:00 | 587.78 | 588.15 | 587.44 | 587.61 | -4.24 |
| 1 | 11:10:00 | 587.59 | 587.83 | 586.76 | 587.31 | -4.54 |
| 2 | 11:15:00 | 587.26 | 587.54 | 586.64 | 586.84 | -5.01 |
| 3 | 11:20:00 | 586.69 | 587.98 | 586.53 | 587.33 | -4.52 |
| 4 | 11:25:00 | 587.45 | 587.71 | 586.32 | 586.33 | -5.52 |
| 5 | 11:30:00 | 586.44 | 587.42 | 586.44 | 586.96 | -4.89 |

### 2025-05-05 11:05 — VIX_ELEVATED (VIX=23.64, score=10)

- Entry: SPY 564.69 | Chart stop: 565.2 (+0.51) | Original P&L: $-51.0
- Triggers: ['seq_rejection', 'trendline_rejection', 'level_rejection', 'confluence']
- May 5 2025 — VIX_ELEVATED

**Option data:** SPY250505P00563000 (strike 563)
- Entry premium (bar-0 VWAP): $0.7233
- -8% stop threshold: $0.6654
- Premium stop fires: bar 1 (11:15:00) drop=-11.5%
- Bear confirmation (SPY<entry): bar 2
- Chart stop (SPY>565.2): bar 1
- SPY adverse move first: True
- Max adverse exposure bars 1-3: +0.88c
- **Conclusion: PREMIUM_STOP_FIRES_BEFORE_BEAR_MOVE** | L51 analog: True

**SPY path (bars 0-5 after entry fill):**

| Bar | Time | O | H | L | C | vs_entry |
|---|---|---|---|---|---|---|
| 0 | 11:10:00 | 565.24 | 565.46 | 565.18 | 565.27 | +0.58 |
| 1 | 11:15:00 | 565.28 | 565.57 | 565.25 | 565.27 | +0.58 |
| 2 | 11:20:00 | 565.23 | 565.27 | 564.64 | 564.65 | -0.04 |
| 3 | 11:25:00 | 564.66 | 564.99 | 564.59 | 564.84 | +0.15 |
| 4 | 11:30:00 | 564.8 | 564.89 | 564.7 | 564.85 | +0.16 |
| 5 | 11:35:00 | 564.92 | 565.36 | 564.92 | 565.0 | +0.31 |

### 2025-10-10 11:05 — VIX_ELEVATED (VIX=21.63, score=10)

- Entry: SPY 665.71 | Chart stop: 666.26 (+0.55) | Original P&L: $-55.0
- Triggers: ['ribbon_flip', 'level_rejection', 'confluence']
- Oct 10 2025 — VIX_ELEVATED

**Option data:** SPY251010P00666000 (strike 666)
- Entry premium (bar-0 VWAP): $1.3454
- -8% stop threshold: $1.2378
- Premium stop fires: bar 1 (11:15:00) drop=-33.1%
- Bear confirmation (SPY<entry): bar 1
- Chart stop (SPY>666.26): bar None
- SPY adverse move first: False
- Max adverse exposure bars 1-3: +-8.46c
- **Conclusion: PREMIUM_STOP_FIRES_BEFORE_BEAR_MOVE** | L51 analog: True

**SPY path (bars 0-5 after entry fill):**

| Bar | Time | O | H | L | C | vs_entry |
|---|---|---|---|---|---|---|
| 0 | 11:10:00 | 657.18 | 657.26 | 656.31 | 656.66 | -9.05 |
| 1 | 11:15:00 | 656.47 | 657.16 | 656.38 | 657.01 | -8.7 |
| 2 | 11:20:00 | 657.22 | 657.25 | 656.28 | 656.28 | -9.43 |
| 3 | 11:25:00 | 656.39 | 656.65 | 655.56 | 655.99 | -9.72 |
| 4 | 11:30:00 | 656.09 | 656.3 | 655.44 | 655.51 | -10.2 |
| 5 | 11:35:00 | 655.42 | 655.46 | 654.07 | 654.21 | -11.5 |

### 2026-03-06 11:05 — VIX_HIGH (VIX=29.51, score=10)

- Entry: SPY 671.02 | Chart stop: 673.04 (+2.02) | Original P&L: $-137.2
- Triggers: ['trendline_rejection', 'level_rejection', 'confluence']
- Mar 6 2026 — VIX_HIGH, worst loss -$137

**Option data:** SPY260306P00669000 (strike 669)
- Entry premium (bar-0 VWAP): $1.5424
- -8% stop threshold: $1.419
- Premium stop fires: bar 1 (11:15:00) drop=-32.6%
- Bear confirmation (SPY<entry): bar None
- Chart stop (SPY>673.04): bar 1
- SPY adverse move first: True
- Max adverse exposure bars 1-3: +3.35c
- **Conclusion: PREMIUM_STOP_FIRES_BEFORE_BEAR_MOVE** | L51 analog: True

**SPY path (bars 0-5 after entry fill):**

| Bar | Time | O | H | L | C | vs_entry |
|---|---|---|---|---|---|---|
| 0 | 11:10:00 | 675.0 | 675.1 | 673.49 | 673.94 | +2.92 |
| 1 | 11:15:00 | 673.94 | 674.37 | 673.55 | 673.97 | +2.95 |
| 2 | 11:20:00 | 673.9 | 673.94 | 672.88 | 672.93 | +1.91 |
| 3 | 11:25:00 | 672.95 | 672.95 | 671.99 | 672.23 | +1.21 |
| 4 | 11:30:00 | 672.18 | 672.54 | 671.7 | 671.95 | +0.93 |
| 5 | 11:35:00 | 671.92 | 672.32 | 671.24 | 672.21 | +1.19 |

---

## Methodology

- Entry fill = first bar after trigger bar (at that bar's open as proxy)
- Entry premium = first option bar VWAP after entry bar timestamp
- -8% threshold = entry_premium × 0.92
- L51 analog = premium stop fires at or before first bar where SPY close < entry
- Chart stop = SPY high crosses stop_price_spy (rejection_level + $0.20)
- Options: OTM-2 puts first; ATM puts as fallback (strike_offset=0)

## Comparison: Production Stop vs Chart-Stop-Only

| Mode | Fires when | Effect on L51-analog obs |
|---|---|---|
| Production (-8%) | Put premium drops 8% | Fires during initial bounce BEFORE bear move |
| Chart stop (-0.99) | SPY crosses rejection_level + $0.20 | Fires ONLY if the rejection fails (false signal) |
