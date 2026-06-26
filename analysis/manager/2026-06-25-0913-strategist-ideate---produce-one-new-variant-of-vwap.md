<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=18.827s | action=IDEATE — Produce ONE new variant of vwap -->
<!-- reason:  -->

# Strategy Variant: vwap_reclaim_rvol_gate_DRAFT

**Base Strategy:** vwap_reclaim_failed_break  
**Variant Goal:** Introduce an RVOL (Relative Volume) filter requiring RVOL ≥ 1.2 as an additional entry condition to improve signal quality.

---

## Overview
The original *vwap_reclaim_failed_break* strategy enters long positions when price reclaims the VWAP after a failed breakout below it. This variant adds a volume‑based gate: the trade is only taken if the current bar’s RVOL (volume relative to its 20‑period average) is at least 1.2, indicating stronger participation and reducing false‑positive reclaims.

---

## Entry Conditions
1. **Price Action:**  
   - The current bar’s close is **above** the VWAP.  
   - The prior bar’s close was **below** the VWAP (i.e., a reclaim event).  
2. **Failed Breakout Filter (retained from base):**  
   - Within the look‑back window (default 5 bars), price must have penetrated below the VWAP by at least X% (parameter `failed_break_pct`) and then closed back above it, indicating a failed breakout.  
3. **RVOL Gate (new):**  
   - Compute RVOL = (Current bar volume) / (Average volume of the last N bars, default N=20).  
   - Require **RVOL ≥ 1.2**.  
4. **Optional Filters (unchanged):**  
   - Any existing trend, volatility, or time‑of‑day filters remain as defined in the base strategy.

*All conditions must be true on the same bar to trigger an entry.*

---

## Exit Conditions
- **Stop‑Loss:** Same as base (e.g., ATR‑based or fixed percentage below entry).  
- **Take‑Profit:** Same as base (e.g., risk‑reward ratio or VWAP‑target).  
- **Time‑Based Exit:** Unchanged (if applicable).  
- **RVOL‑Based Exit:** Not applied; RVOL is only an entry gate.

---

## Parameters
| Parameter | Description | Default |
|-----------|-------------|---------|
| `failed_break_pct` | Minimum percentage price must breach below VWAP to qualify as a failed breakout | 0.5% |
| `rvol_period` | Look‑back period for average volume used in RVOL calculation | 20 |
| `rvol_threshold` | Minimum RVOL required for entry | 1.2 |
| (Other base parameters) | Unchanged from original strategy | — |

---

## Rationale
- **Volume Confirmation:** A reclaim accompanied by above‑average volume suggests stronger buying interest, lowering the chance of a quick reversal.  
- **Filter Tightening:** Adding RVOL ≥ 1.2 reduces trade frequency but aims to increase win rate and profit factor.  
- **Compatibility:** The gate is purely additive; existing logic remains intact, allowing easy toggling via the `rvol_threshold` parameter.

---

## Usage Note
- Enable the variant by setting `rvol_threshold` to 1.2 (or another desired minimum) in the strategy configuration.  
- Backtest across multiple timeframes and instruments to validate the impact of the RVOL gate before live deployment.