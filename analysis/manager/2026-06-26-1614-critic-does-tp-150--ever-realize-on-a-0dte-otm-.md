<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=67.57s | action=Does tp+150% ever realize on a 0DTE OTM- -->
<!-- reason:  -->

**Short answer**

| Question | Practical verdict | Why |
|----------|-------------------|-----|
| **tp+150 % on a 0‑DTE OTM‑2** | **Almost never realized in live trading** | The combination of zero‑days‑to‑expiration, far‑out‑of‑the‑money strike, and a 150 % profit target pushes the required price move far beyond what the underlying can typically achieve in a single session, especially when gamma‑risk is extreme. |
| **sell80 % + min_contracts=3** | **Compatible only if you allow fractional contracts or round‑up/down** | 80 % of 3 contracts = 2.4 contracts. With a strict integer‑contract rule you would either sell 2 contracts (‑66.7 %) or 3 contracts (‑100 %). Most platforms will either reject the order or automatically adjust to the nearest allowable size, so the exact “sell80 %” intent is not preserved unless you permit fractional sizing. |
| **WR = 0.12 (≈1‑winner‑in‑9) operationally viable?** | **Marginal – only viable if the reward‑to‑risk ratio is very high** | A 12 % win‑rate means you lose ~88 % of trades. To stay profitable you need an average win‑size ≳ 7‑8× the average loss‑size (Expectancy = 0.12·AvgWin − 0.88·AvgLoss > 0). If your strategy’s TP/SL structure does not deliver that kind of asymmetry, the approach will bleed equity over time. |

---

### 1. tp+150 % on a 0‑DTE OTM‑2

**What the numbers mean**

- **0‑DTE**: the option expires today; theta decay is essentially 100 % of the remaining extrinsic value.
- **OTM‑2**: typically “2 strikes out‑of‑the‑money” (e.g., if the underlying is at $100, a call with strike $110 or a put with strike $90, depending on the product’s strike spacing).
- **tp+150 %**: you set a take‑profit level that is 150 % above the entry premium (i.e., you aim to exit when the option’s price has risen to 2.5× what you paid).

**Why it rarely happens**

| Factor | Effect on a 0‑DTE OTM‑2 |
|--------|------------------------|
| **Gamma explosion** | Near expiration, gamma spikes dramatically for deep OTM options. A small underlying move can cause the option’s delta to swing from near‑0 to near‑1 (or vice‑versa) in a matter of minutes, but the *absolute* price change remains limited because the option’s extrinsic value is already tiny. |
| **Intrinsic value ceiling** | For an OTM option, intrinsic value is zero until the underlying crosses the strike. To achieve a 150 % gain on premium, you need the option’s *extrinsic* value to increase by that amount, which is unlikely because extrinsic value decays rapidly (theta ≈ ‑premium/time‑to‑expiry). |
| **Typical intraday ranges** | Even in volatile markets, a 0‑DTE OTM‑2 rarely sees more than a 30‑50 % move in premium before either being knocked ITM (and then quickly losing value due to gamma‑flip) or expiring worthless. A 150 % move would require the underlying to jump several standard deviations in a single session — an event that occurs far less than 1 % of the time for most liquid underlyings. |
| **Execution slippage & bid/ask spread** | The bid/ask on deep OTM 0‑DTE options can be wide (often 10‑30 % of the premium). To net a 150 % gain you must overcome that spread, further lowering the probability. |

**Bottom line:** In practice you will see the tp+150 % trigger only on rare, extreme news‑driven spikes (e.g., a surprise earnings gap or macro shock). For a systematic, repeatable strategy it is effectively unrealizable.

---

### 2. sell80 % + min_contracts=3

**Interpretation**

- **sell80 %**: the algorithm intends to liquidate 80 % of the current position when a certain condition is met.
- **min_contracts=3**: the strategy refuses to open or maintain a position smaller than three contracts.

**Mathematical check**

If you hold exactly **N** contracts at the moment the sell signal fires, the number to sell is:

\[
\text{SellQty} = 0.8 \times N
\]

For the sell quantity to be an integer (most broker APIs require whole‑contract orders), **N** must be a multiple of 5:

\[
0.8N \in \mathbb{Z} \;\Longleftrightarrow\; N = 5k \;(k\in\mathbb{Z})
\]

With **min_contracts=3**, the smallest allowable N is 3, which is **not** a multiple of 5. Therefore:

- **N = 3 → SellQty = 2.4** (non‑integer) → most platforms will either:
  - Reject the order (“invalid quantity”), or
  - Auto‑round to the nearest allowable size (2 or 3 contracts), which deviates from the intended 80 % (giving 66.7 % or 100 % liquidation).

**Work‑arounds**

1. **Allow fractional contracts** (e.g., via CFDs, futures mini‑contracts, or a broker that supports odd‑lot options). Then 2.4 contracts is acceptable and the rule is compatible.
2. **Adjust the minimum** to a multiple of 5 (e.g., `min_contracts=5`) if you must stay integer‑only.
3. **Implement a rounding policy** (e.g., always sell `floor(0.8*N)`) and accept a slight deviation from the exact 80 % target.

**Verdict:** With a strict integer‑contract constraint and `min_contracts=3`, the exact `sell80%` instruction is **not compatible** unless