# G13 — Treasurer Audit: Gamma-Safe-2 Equity Trajectory

> Analysis only. Read-only Alpaca MCP queries. No orders placed/cancelled. No equity reset performed — reset is decision D4, J-only.

## 1. Real numbers (quoted directly from Alpaca, `mcp__alpaca__*`, account `PA3S2PYAS2WQ`)

**get_account_info:**
```
equity: "1513.01"
last_equity: "1351.34"   (prior trading-day close, 2026-07-06)
cash: "1513.01"
buying_power: "1513.01"
balance_asof: "2026-07-06"
created_at: "2026-06-16T03:03:40Z"
```

**get_portfolio_history** (period=1M, timeframe=1D, base_value=2000, base_value_asof=2026-06-12):
```
equity series (last 6 bars):  2000.00 → 2000.00 → 1762.69 → 1762.69 → 1762.69 → 1758.94 → 1425.35 → 1351.34
profit_loss (last 3 bars):    -3.75, -333.59, -74.01
profit_loss_pct (last 3):     -0.0021, -0.1897, -0.0519
```
Peak equity in this history = **$2,000** (base value, 2026-06-12 reset point — this is the fresh-$2K Gamma-Safe-2 account CLAUDE.md documents, distinct from the retired Safe-1).

`get_all_positions` → `[]` (flat, no open risk right now).

## 2. Verify/refute "down ~32% over 3 weeks"

**VERIFIED — approximately correct at the trough.**

- Peak $2,000 (2026-06-12) → trough $1,351.34 (2026-07-06 close) = **-$648.66 / -32.43%**. This matches the "~32% over 3 weeks" claim almost exactly (25 calendar days, ~18 trading days ≈ "3 weeks").
- Current intraday equity has since partially recovered: $2,000 → $1,513.01 = **-$486.99 / -24.35%** as of this pull (2026-07-07/08 intraday, cash-only, flat).
- So: the 32% figure was accurate as a snapshot of the worst point reached: it is now stale by about 8 points of recovery — current live drawdown is **-24.35%**, not -32%.

## 3. Reconciliation — what actually moved the equity (the key finding)

G9 established the deterministic ENGINE shows **zero reconciled fills** (filled_avg_price null everywhere in the decision ledger, core + all 6 fleet arms). But `get_account_activities(FILL)` on the live broker shows **dozens of real, broker-confirmed fills** on this account since 2026-06-26. Two categories:

**A. SPY 0DTE option round-trips (the P&L-relevant activity, all size=3 contracts, consistent with `min_contracts=3` / `position_sizing_tiers[0-2000].base_qty=3`):**

| Date | Symbol | Side seq | Entry | Exit | Result/ct (approx) |
|---|---|---|---|---|---|
| 06-26 | SPY 732P | buy 3 @ 0.98 → sell 3 @ 0.19 | | | **-$237** (-80.6%) |
| 07-02 | SPY 746P | buy 3 @ 1.27 → sell 3 @ 1.05 | | | -$66 |
| 07-02 | SPY 750C ×5 legs | buy/sell churn 1.63→1.53, 1.65/1.67→1.41, 1.49→1.40 | | | net loss, multiple round-trips same contract |
| 07-02 | SPY 751C ×3 legs | 0.94→0.87→0.84→0.77→0.76→0.69 | | | net loss, repeated re-entries same strike |
| 07-02 | SPY 743P | buy 3 @ 1.36 → sell 3 @ 1.13 | | | -$69 |
| 07-06 | SPY 751C | buy 3 @ 0.81 → sell 3 @ 0.73 → buy 3 @ 0.73 → sell partial 0.66 | | | net loss, re-entered same name same day |
| 07-06 | SPY 750P | **11 fills**, repeated buy/sell 0.50-0.61 range, same strike same day | | | net loss, heavy churn |
| 07-06 | SPY 751C | buy 3 @ 0.80 → sell 3 @ 0.67 | | | -$39 |
| 07-07 | SPY 747P | buy 5 @ 0.82 → sell 4 @ ~1.255 → sell 1 @ 0.69 | | | net small gain (qty=5, not 3 — see note) |

**B. Crypto scalping (UNI/USD, BTC/USD) — completely outside CLAUDE.md scope.** Dozens of sub-second-to-minute round trips in UNI/USD (06-30/07-01, ~20+ fills) and BTC/USD (recurring ~00:45 UTC daily, 07-02 through 07-08). CLAUDE.md is explicit: **"Trading crypto as an instrument — crypto is gym-only (trading loop retired 2026-06-17)."** These fills exist on the live Safe-2 broker account regardless.

**Conclusion: this is NOT engine activity.** The fill pattern — same-strike immediate re-entries within the same session (up to 11 fills on one contract in one day), partial-fill legs, a qty=5 SPY fill (violates the documented qty=3 tier), and active crypto pair scalping (UNI/USD, BTC/USD) — does not match the deterministic engine's behavior (which per G9 has recorded **zero** reconciled fills anywhere) and does not match the single-causal-entry-per-signal doctrine in params.json (`j_vwap_cont`, `j_vix_dayside`, etc. are each "ONE causal entry/day"). This pattern — manual same-strike scalping/repeated re-entry, non-SPY instruments — is consistent with **manual trading activity, not the autonomous engine.** The $648.66 peak-to-trough loss and the crypto fills are attributable to non-engine activity on this account. This needs J's confirmation but the evidence points away from the automated system as the source.

**Rule-break flags if manual (informational, not enforcement — Treasurer doesn't adjudicate trade quality):**
- Rule 4 (no adding without a new trigger) — the SPY 751C / 750P re-entry clusters on 07-02 and 07-06 look like repeated same-strike re-entries within one session.
- Crypto trading on this account directly contradicts the CLAUDE.md scope lock ("crypto is gym-only").
- One SPY fill (07-07, 747P) sized at qty=5, not the documented qty=3 tier floor for this equity band.

## 4. Sizing floor vs current equity — does the floor disqualify validated edges?

**Per `automation/state/params.json`:**
- `position_sizing_tiers[0]`: equity $0-$2,000 → `base_qty: 3`, `elite_qty: 3` ("no upsize — capital constraint")
- `per_trade_risk_cap_pct: 0.3` (30% of equity)
- `min_contracts: 3`

**At current equity $1,513.01:**
- 30% risk cap = **$453.90** max notional per trade.
- qty=3 at the validated ATM cells (median premium ~$1.35-$1.40 per the vwap_continuation / vix_dayside / bollinger_squeeze docs) → notional ≈ $405-$420. **Still fits under the $453.90 cap** — roughly 89-93% utilization of the cap, tighter than at $1,763 (where the same qty=3 was ~76-80% utilization) but not yet breached.
- **At the trough ($1,351.34):** 30% cap = $405.40. qty=3 at ~$1.40 premium = $420 notional → **would BREACH the cap by ~$14.60 (3.6% over)**. This is a real near-miss: the account dipped to a level where the validated qty-3 cell would have been mechanically blocked by `risk_gate` (BLOCK [RISK_CAP], same mechanism documented in the `_wp8_revert_2026_06_21` note for the 1DTE cell at $2,000 equity).
- **Floor disqualification: YES, at the trough** (equity < ~$1,400 makes qty=3 at ATM ~$1.40 premium infeasible under the 30% cap without a qty-2 fallback, which is itself blocked by `min_contracts: 3` — same "unaffordable cell, no auto-reduce" failure mode already documented in params.json for the WP-8 1DTE case).
- **At current equity ($1,513.01): NO** — still fits, with roughly 7-11% headroom.
- This is exactly the D5 (min-1 for single-exit shapes) tension: the min-3 floor exists for the "2 TP1 + 1 runner" structure, but several of the newly-armed extra setups (`vwap_reclaim_failed_break`, `vix_regime_dayside`, `bollinger_squeeze`, `double_bottom_base_quiet`) are single-exit-shape cells that don't need 3 legs to express the edge — they need 3 contracts only because `min_contracts=3` is a blanket floor, not a per-setup requirement.

## 5. Options (analysis only — no action taken)

These are OBSERVATIONS for J's weekend review, not executed changes:

1. **D4 (reset-to-$2K):** current equity $1,513.01 is 24.35% below the $2,000 reset baseline. If the manual/crypto fills identified in §3 are confirmed as the drawdown source (not the engine), a reset would restore the engine's ability to trade its validated cells without the risk-cap near-miss identified in §4 — but the reset decision itself belongs to J alone.
2. **D5 (min-1 for single-exit shapes):** at $1,513.01 the standard min-3 floor still fits (barely). At the trough it did not. Worth flagging whether the min-3 floor should be relaxed to min-2 or min-1 specifically for the single-exit-shape extra setups (vwap_reclaim_failed_break / vix_regime_dayside / bollinger_squeeze / double_bottom_base_quiet), decoupling their qty floor from the legacy "2 TP1 + 1 runner" 3-leg structure that min-3 was originally sized for.
3. **Crypto activity on Safe-2:** dozens of UNI/USD and BTC/USD fills exist on this SPY-0DTE-designated account. This is out-of-scope per CLAUDE.md ("crypto is gym-only") regardless of P&L impact (these round-trips appear roughly breakeven-to-small-loss, not large drawdown drivers) — flagged for J's awareness, not adjudicated here.

## Summary of numbers for reference

| Metric | Value |
|---|---|
| Peak equity (base_value, 2026-06-12) | $2,000.00 |
| Trough equity (2026-07-06 close) | $1,351.34 |
| Current equity (live pull) | $1,513.01 |
| Max drawdown $ / % (peak→trough) | -$648.66 / -32.43% |
| Current drawdown $ / % (peak→now) | -$486.99 / -24.35% |
| 30% risk cap at current equity | $453.90 |
| 30% risk cap at trough equity | $405.40 |
| qty=3 ATM notional (~$1.40 premium) | ~$420 |
| Floor disqualifies validated edge at current equity | NO (7-11% headroom) |
| Floor disqualified validated edge at trough | YES (~3.6% breach, no qty-2 fallback under min_contracts=3) |
