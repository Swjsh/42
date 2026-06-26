<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=5.907s | action=IDEATE -->
<!-- reason:  -->

**Variant:** VWAP‑Continuation + RVOL‑Floor (RVOL ≥ 1.3)

**Base file to clone:** `sim_vwap_continuation.py` (the existing VWAP‑continuation strategy).

**Entry logic (per bar):**  
1. Price must close **above** the VWAP on the current bar (long) or **below** VWAP (short).  
2. The bar’s **RVOL** (relative volume vs. 20‑period average) must be **≥ 1.3**.  
3. Additionally, require the prior bar’s close to be on the same side of VWAP (to avoid whipsaws).  
When both conditions fire, enter a market order at the close of the signal bar.

**Stop placement:**  
- **Long:** Stop‑loss placed at the **lowest low** of the last 3 bars (or 1 × ATR(14) below entry, whichever is tighter).  
- **Short:** Stop‑loss placed at the **highest high** of the last 3 bars (or 1 × ATR(14) above entry).  
- Trail the stop with a 1.5 × ATR multiplier after the trade moves in favor by 1 × ATR.

**Risk management:** Keep position size at 1 % of equity per trade; max 2 concurrent VWAP‑continuation positions.

This RVOL floor filters out low‑conviction breaks, improving win‑rate while preserving the original VWAP‑continuation trend‑following edge. (≈115 words)