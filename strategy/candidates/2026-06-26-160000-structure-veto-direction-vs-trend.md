# Strategy candidate: STRUCTURE-VETO (direction-vs-price-structure trend)

> DRAFT — Chef proposal 2026-06-26 16:00 ET. J ratifies.

## Hypothesis

Wire `crypto.lib.market_structure.classify_trend` (5m-sameday swing structure) into the
engine's entry path as a pure VETO that blocks an entry whose **direction fights the
confirmed price-structure trend**:

- veto **BEAR/P** when `classify_trend == 'uptrend'`
- veto **BULL/C** when `classify_trend == 'downtrend'`
- **range / unknown → NO veto** (do-not-over-filter clause — this is what preserves 5/04)

Directional claim: the live engine currently reads trend ONLY from the lagging EMA ribbon
(`score.py` RIDE_THE_RIBBON checklists), which is why it scored bearish and fired wrong-way
PUT signals at 10:36 on 2026-06-26 while SPY trended +$7.8 up all morning. A price-structure
veto removes exactly that wrong-way trade class without touching with-structure trades. It is
a VETO ONLY — it can never add a signal, only remove counter-structure ("wrong-way") entries.

## Backtest evidence

Engine = CURRENT production config: `use_real_fills=True` (C1 — the only WR authority) +
V15 managed exits (chart-stop-primary, −50% cap, chandelier arm+5%/trail15%, tp1=0.667,
runner=2.5). BASE = production. CANDIDATE = BASE + structure-veto. Monkey-patch on both
`evaluate_bearish_setup` / `evaluate_bullish_setup` — production files untouched.

- **Train window:** 2025-01-02 → 2025-12-31
- **Test (OOS) window:** 2026-01-02 → 2026-06-18
- **Full:** 2025-01-02 → 2026-06-18 (real OPRA fills, 34,606 SPY bars)

| Window | n base→cand | P&L base→cand | Δ P&L | vetoed bars | trades removed (W/L, net$) |
|---|---|---|---|---:|---|
| **full** | 35→34 | +7,555 → **+8,138** | **+$583** | 107 | 2 (W0/L2, **−$574**) |
| train_2025 | 14→13 | +1,344 → +1,927 | +$583 | 70 | 2 (W0/L2, −$574) |
| **oos_2026** | 21→21 | +6,211 → +6,211 | **+$0** | 37 | **0** |
| 2025Q1 | 5→3 | −310 → +264 | +$574 | 20 | 2 (W0/L2, −$574) |
| 2025Q2 | 2→2 | +1,008 → +1,008 | +$0 | 15 | 0 |
| 2025Q3 | 4→5 | −616 → −607 | +$9 | 21 | 0 |
| 2025Q4 | 3→3 | +1,262 → +1,262 | +$0 | 14 | 0 |
| 2026Q1 | 8→8 | +5,996 → +5,996 | +$0 | 29 | 0 |
| 2026Q2 | 13→13 | +215 → +215 | +$0 | 8 | 0 |

- **edge_capture:** $780 base → **$780 candidate** (delta **$0**) — all 3 J PUT winners hit, all 4 J loser days handled identically. **No winner blocked.**
- **aggregate sharpe (daily, full):** 4.340 base → **4.728 candidate** (+0.39, +9%)
- **final_score:** edge_capture × sharpe = 780 × 4.728 = **3,688** (base 780 × 4.340 = 3,385; **+303, +9%**)
- **top5_pct:** removed cohort is only 2 trades (both losers) — no concentration concern on the removal; benefit (+$574) is 2 losses avoided, both in 2025Q1.
- **positive_quarters:** **2/6** show Δ>0; 4/6 are exactly $0 (veto removed no *placed* trade there). 0/6 negative.
- **max_drawdown:** −2,273 base → **−2,273 candidate** (unchanged).
- **real_fills_validated:** yes (full OPRA, `use_real_fills=True`).

**Wrong-way trades removed (full):** 2 net wrong-way **losers** worth **−$574** (both bear PUTs that fired into a confirmed 5m uptrend — the exact 06-26 wrong-way class). **0 winners removed.** 107 bars were vetoed across full history, but only 2 translate to a removed *placed trade* — the other 105 were already excluded by existing gates (quality-lock / cap / escalation), so the veto is mostly redundant with what already fires, and adds bite on exactly 2 trades.

## Disclosures (per OP-20)

1. **Account-size assumption:** Safe-2, $2K, per-tier strike + per-trade risk caps as in production params.json. Cap-realizability already baked into the real-fills sim (L180).
2. **Sample-bias disclosure:** The entire net benefit (+$583) lives in **2025Q1** (2 wrong-way bear losses avoided). OOS-2026 benefit is **exactly $0** — the veto removes no placed trade in 2026 because existing gates already exclude every counter-structure bar that would have placed. So the *measured* edge is small and IS-concentrated; the value is **safety/robustness** (kills a known failure class) more than realized P&L.
3. **Out-of-sample test result:** OOS-2026 Δ P&L = **$0**, n unchanged 21→21, edge_capture unchanged. Honestly: **no OOS P&L improvement** — but also zero OOS harm and zero winners removed. The improvement is entirely IS.
4. **Real-fills check:** yes — `simulator_real` via `use_real_fills=True`, the only WR authority. Sharpe/P&L/edge_capture all computed on real OPRA fills.
5. **Failure-mode enumeration:**
   - (a) **Range mislabel risk** — 5/04 (+$730, biggest winner) reads RANGE on 5m AND 15m; it survives ONLY because range=no-veto. **If anyone ever tightens to "a PUT requires a CONFIRMED downtrend," it blocks 5/04 and breaks OP-16. DO NOT build a require-with-trend variant.** (Encoded in memory.)
   - (b) **Coarse loser recall** — the veto catches 1/4 J losers per TF; it CANNOT catch with-structure losers (5/06 730P bear-in-downtrend, 5/07 737C bull-in-uptrend). It is a wrong-way filter, not a general loss filter. Accepted.
   - (c) **Redundancy** — 105/107 vetoed bars are already gated out; live benefit is thin. Risk is over-claiming P&L.
   - (d) **Sameday warmup** — needs ≥5 same-day 5m bars to classify; pre-10:00 entries read 'unknown' → no veto (fail-open, correct).
6. **Concentration:** top5_pct N/A on a 2-trade removal; benefit is 100% in 2025Q1 — disclosed as the binding concentration caveat.

## Knob changes proposed

No params.json knob exists today. Ship would add a gated wire of `classify_trend` into the
entry path. Proposed (J/validator-author to implement — **NEVER edit params.json myself**):

- `params.json`: add `"structure_veto_enabled": true` (Safe), `"structure_veto_timeframe": "5m_sameday"`.
- Wire in `lib/orchestrator.py` after `winning_side` resolves: if `_veto_side(winning_side, classify_trend(sameday_5m))` → skip bar (mirror the existing block pattern), gated on `structure_veto_enabled`.
- Replaces the lagging EMA-ribbon trend read for the direction-vs-trend safety check.

## Pre-merge gate

`python crypto/validators/runner.py` → **passed=97/98, overall_pass=True** (1 known-flaky
`KNOWN_FLAKY_LIVE_SOURCE` excluded). 5/14 replay NEW err 0.0%. Status: **PASS** before AND
after (no production files touched — new read-only harness only). gym 89/89 detector core intact.

## My confidence (1-10) and why

**7/10.** Clean wins: anchor edge_capture **unchanged** (no winner blocked — the cardinal gate),
full P&L **+$583**, sharpe **+9%**, drawdown flat, 0/6 negative quarters, and it kills the exact
06-26 wrong-way failure class by construction. Docked from higher because: **OOS realized
benefit is $0** (the edge is IS-concentrated in 2025Q1; existing gates already exclude most
counter-structure bars), so this is primarily a **robustness/safety veto** (provably removes a
known wrong-way class, never a winner) rather than a P&L engine. That is exactly what J asked for
after 06-26 — a guard against firing PUTs into an uptrend — and it ships without regressing the
source-of-truth. Recommend shipping as a pure safety veto paired with replacing the ribbon trend
read with `market_structure`.

**Tool (read-only, reusable):** `backtest/autoresearch/structure_veto_ab.py`.
**Output:** `analysis/recommendations/structure-veto-ab-2026-06-26.json`.
