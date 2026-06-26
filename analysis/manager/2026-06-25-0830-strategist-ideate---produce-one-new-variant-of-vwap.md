<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=23.955s | action=IDEATE — Produce ONE new variant of vwap -->
<!-- reason:  -->

#VWAP Reclaim Failed Break – RVOL≥1.2 Gate (Draft)

**File:** `strategy/candidates/vwap_reclaim_rvol_gate_DRAFT.md`  
**Status:** Draft – for review and backtesting  

---

## 1. Overview
A variant of the dormant `vwap_reclaim_failed_break` strategy that adds a **Relative Volume (RVOL) ≥ 1.2** filter to the entry condition. The core idea remains: enter long when price fails to break below VWAP, then reclaims VWAP on the same or next bar. The RVOL gate ensures the reclamation occurs on unusually high volume, increasing the probability of genuine institutional interest.

---

## 2. Parameters
| Parameter | Description | Default | Notes |
|-----------|-------------|---------|-------|
| `vwap_period` | Look‑back period for VWAP calculation | 20 | Typical intraday VWAP window |
| `rvol_period` | Period used to compute average volume for RVOL | 20 | Same as VWAP period for consistency |
| `rvol_threshold` | Minimum RVOL required for entry | 1.2 | Must be ≥ this value |
| `failed_break_lookback` | Number of bars to search for a prior VWAP break‑down | 3 | How far back we look for the failed break |
| `reclaim_tolerance` | Price tolerance for considering a VWAP reclaim (as % of ATR) | 0.005 | Allows minor noise |
| `stop_loss_atr_mult` | Stop‑loss distance as a multiple of ATR | 1.5 | Adjustable risk |
| `take_profit_atr_mult` | Take‑profit distance as a multiple of ATR | 3.0 | Adjustable reward |
| `max_hold_bars` | Maximum bars to hold a position before forced exit | 20 | Prevents stale trades |

---

## 3. Indicators
- **VWAP** – Volume‑Weighted Average Price over `vwap_period`.
- **ATR** – Average True Range (14‑period) used for stop‑loss/take‑profit sizing.
- **RVOL** – Current bar volume divided by the average volume over `rvol_period`.  
  `RVOL = volume_current / SMA(volume, rvol_period)`

---

## 4. Entry Logic (Long Only)
1. **Failed Break Detection**  
   - Within the last `failed_break_lookback` bars, there must be at least one bar where the low price `< VWAP - ε` (a clear break below VWAP).  
   - `ε` can be set to a small fraction of ATR (e.g., 0.1*ATR) to avoid false signals from noise.

2. **Reclaim Condition**  
   - On the current bar (or the immediate next bar after the failed break), the close price must be **≥ VWAP + reclaim_tolerance * ATR**.  
   - This confirms price has reclaimed the VWAP level.

3. **RVOL Gate**  
   - The current bar’s RVOL must be **≥ rvol_threshold (1.2)**.  
   - Ensures the reclamation is accompanied by above‑average volume.

4. **Entry Execution**  
   - Enter a long position at the close of the bar that satisfies all three conditions, or at the open of the next bar if a stricter entry is desired (specify in implementation).

---

## 5. Exit Logic
- **Stop‑Loss:** Place a stop‑loss order at `entry_price - stop_loss_atr_mult * ATR(entry_bar)`.  
- **Take‑Profit:** Place a profit target at `entry_price + take_profit_atr_mult * ATR(entry_bar)`.  
- **Time‑Based Exit:** If neither stop nor target is hit within `max_hold_bars`, close the position at the close of the `max_hold_bars`‑th bar after entry.  
- **Trailing Option (optional):** A trailing stop can be added at `X * ATR` behind the highest high since entry, if desired.

---

## 6. Risk Management
- **Position Size:** Determined by a fixed fractional risk model (e.g., risk 1% of equity per trade) using the stop‑loss distance.  
- **Maximum Concurrent Positions:** Limit to 1 (or a small number) to avoid over‑exposure on the same instrument.  
- **Daily Loss Cap:** Halt trading for the day if cumulative loss exceeds a pre‑set daily drawdown limit (e.g., 3% of equity).

---

## 7. Timeframe & Market
- Designed for **intraday** trading (e.g., 5‑minute or 15‑minute bars) on liquid futures, equities, or ETFs where VWAP is a meaningful reference.  
- Can be adapted to higher timeframes with appropriate parameter scaling.

---

## 8. Implementation Notes (Non‑Code)
- Ensure VWAP is reset at the start of each trading session (or as per the instrument’s session definition).  
- RVOL should be calculated using the same session‑aligned volume average to avoid look‑ahead bias.  
- The failed break detection may require tracking the lowest low within the lookback window relative to VWAP.  
- Consider adding a filter to avoid entries during major news events if desired.

---

## 9. Backtesting Checklist
- [ ] Verify VWAP calculation aligns with session boundaries.  
- [ ] Confirm RVOL ≥ 1.2 triggers only on bars with volume significantly above average.  
- [ ] Test multiple `failed_break_lookback` values (2‑5) to optimize robustness.  
- [ ] Evaluate performance across different market regimes (trending, ranging, high‑volatility).  
- [ ] Assess sensitivity to `rvol_threshold` (try 1.0, 1.2, 1.5).  

---

*End of Draft Specification.*