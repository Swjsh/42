# v14_enhanced Real-Fills Validation — 2026-05-13

Generated: `2026-05-13T17:39:31.399648`

## Context

This morning's v14_enhanced grinder produced 60 sampled combos before silent-dying (3rd time). Three near-identical combos converged on a strong recipe but were REJECTED only by the per-loser-day floor (5/05 BS-sim -$153 < -$50 floor — but J had -$260 on 5/05, so engine loses LESS than J, which should be a WIN not a rejection).

Per CLAUDE.md OP 20 disclosure 4, this report runs the top-3 candidates through REAL OPRA fills (not BS sim) over the wide 2025-01-01 → 2026-05-12 window to determine if any survives real-fills validation.

## Caveats (read first)

- **Profit-lock NOT applied.** `simulator_real` does not implement the profit-lock primitive (only in BS `simulator`). The combo's `profit_lock_threshold_pct=0.05` and `profit_lock_stop_offset_pct=0.10` are no-ops here. This affects 5-10% of trades where favourable premium spiked then reversed — those trades may show worse real-fills PnL than BS-sim with profit-lock would have.
- **Per-quality exit-knob matrix NOT applied.** The orchestrator's TRENDLINE/LEVEL/ELITE/SUPER per-quality `_grinder_overrides` only fires through the BS path. Real-fills uses a UNIFORM exit policy (the combo's `tp1_premium_pct` + `runner_target_premium_pct` applied to all trades regardless of trigger quality).
- **BS-sim fallback on OPRA cache miss.** `simulate_trade_real` returns `None` if the OPRA contract isn't cached; the orchestrator falls back to BS sim with a `::BS_FALLBACK` tag. The fallback fraction per combo is surfaced below — if it's >20% the result is less than a true real-fills test.
- **Strike offset = 0 → ATM (round-spot).** v14_enhanced's `strike_offset_bear=0` matches OP 17 doctrine's J-edge config (ATM strikes, not ITM-2).

## Per-Combo Verdict Summary

| Combo | BS wide | Real wide | 4/29 BS | 4/29 Real | 5/12 BS | 5/12 Real | 5/05 BS | 5/05 Real | BS-fallback % | Verdict |
|-------|---------|-----------|---------|-----------|---------|-----------|---------|-----------|---------------|---------|
| candidate_1_0935_tp1_0.30 | $23,188 | $36,450 | $293 | $869 | $241 | $464 | $-153 | $198 | 7.6% | **PASS** |
| candidate_2_0945_tp1_0.50 | $21,769 | $31,519 | $0 | $869 | $0 | $464 | $0 | $198 | 7.6% | **PASS** |
| candidate_3_1000_tp1_0.75 | $19,501 | $30,986 | $0 | $869 | $0 | $464 | $0 | $198 | 7.9% | **PASS** |

## candidate_1_0935_tp1_0.30

**Combo:**
```python
{
  "strike_offset_bear": 0,
  "min_triggers_bear": 1,
  "premium_stop_pct_bear": -0.2,
  "tp1_qty_fraction": 0.5,
  "profit_lock_threshold_pct": 0.05,
  "profit_lock_stop_offset_pct": 0.1,
  "runner_target_premium_pct": 2.5,
  "no_trade_before": "09:35",
  "tp1_premium_pct": 0.3
}
```

**BS metrics (provided by caller):**
- `wide_pnl`: 23188
- `pnl_4_29`: 293
- `pnl_5_12`: 241
- `pnl_5_07`: 249
- `pnl_5_05`: -153
- `wide_n_trades`: 339
- `wide_wr`: 0.614
- `positive_quarters`: 6
- `top5_pct`: 0.2

**Real-fills metrics:**
- wide_pnl: $36,449.97
- wide_n_trades: 317
- wide_wr: 56.8%
- positive_quarters: 6/6
- top5_pct: 37.1%
- max_drawdown: $2,857.10
- real_fills/bs_fallback: 293/24 (7.6% BS fallback)

**Per-J-anchor day:**

| Date | J PnL | Real PnL | BS PnL |
|------|-------|----------|--------|
| 2026-04-29 (winner) | $342 | $869 | $293 |
| 2026-05-01 (winner) | $470 | $3 | — |
| 2026-05-04 (winner) | $730 | $214 | — |
| 2026-05-12 (winner) | $400 | $464 | $241 |
| 2026-05-05 (loser) | $-260 | $198 | $-153 |
| 2026-05-06 (loser) | $-300 | $0 | — |
| 2026-05-07 (loser) | $-45 | $616 | $249 |

**Per-quarter PnL:**
- 2025-Q1: $2,707.94
- 2025-Q2: $799.39
- 2025-Q3: $6,019.36
- 2025-Q4: $9,022.64
- 2026-Q1: $14,363.65
- 2026-Q2: $3,537.00

**Verdict:** PASS

**Reason:** wide_pnl=$36450, 4/29=$869, 5/12=$464, 5/05=$198 (J=$-260) — all gates pass.

## candidate_2_0945_tp1_0.50

**Combo:**
```python
{
  "strike_offset_bear": 0,
  "min_triggers_bear": 1,
  "premium_stop_pct_bear": -0.2,
  "tp1_qty_fraction": 0.5,
  "profit_lock_threshold_pct": 0.05,
  "profit_lock_stop_offset_pct": 0.1,
  "runner_target_premium_pct": 2.5,
  "no_trade_before": "09:45",
  "tp1_premium_pct": 0.5
}
```

**BS metrics (provided by caller):**
- `wide_pnl`: 21769

**Real-fills metrics:**
- wide_pnl: $31,519.23
- wide_n_trades: 302
- wide_wr: 57.6%
- positive_quarters: 6/6
- top5_pct: 35.8%
- max_drawdown: $2,582.50
- real_fills/bs_fallback: 279/23 (7.6% BS fallback)

**Per-J-anchor day:**

| Date | J PnL | Real PnL | BS PnL |
|------|-------|----------|--------|
| 2026-04-29 (winner) | $342 | $869 | $0 |
| 2026-05-01 (winner) | $470 | $3 | — |
| 2026-05-04 (winner) | $730 | $214 | — |
| 2026-05-12 (winner) | $400 | $464 | $0 |
| 2026-05-05 (loser) | $-260 | $198 | $0 |
| 2026-05-06 (loser) | $-300 | $0 | — |
| 2026-05-07 (loser) | $-45 | $616 | $0 |

**Per-quarter PnL:**
- 2025-Q1: $1,191.14
- 2025-Q2: $1,743.07
- 2025-Q3: $3,952.72
- 2025-Q4: $8,083.76
- 2026-Q1: $12,287.47
- 2026-Q2: $4,261.08

**Verdict:** PASS

**Reason:** wide_pnl=$31519, 4/29=$869, 5/12=$464, 5/05=$198 (J=$-260) — all gates pass.

## candidate_3_1000_tp1_0.75

**Combo:**
```python
{
  "strike_offset_bear": 0,
  "min_triggers_bear": 1,
  "premium_stop_pct_bear": -0.2,
  "tp1_qty_fraction": 0.5,
  "profit_lock_threshold_pct": 0.05,
  "profit_lock_stop_offset_pct": 0.1,
  "runner_target_premium_pct": 2.5,
  "no_trade_before": "10:00",
  "tp1_premium_pct": 0.75
}
```

**BS metrics (provided by caller):**
- `wide_pnl`: 19501

**Real-fills metrics:**
- wide_pnl: $30,985.89
- wide_n_trades: 292
- wide_wr: 57.2%
- positive_quarters: 6/6
- top5_pct: 41.1%
- max_drawdown: $2,435.30
- real_fills/bs_fallback: 269/23 (7.9% BS fallback)

**Per-J-anchor day:**

| Date | J PnL | Real PnL | BS PnL |
|------|-------|----------|--------|
| 2026-04-29 (winner) | $342 | $869 | $0 |
| 2026-05-01 (winner) | $470 | $3 | — |
| 2026-05-04 (winner) | $730 | $214 | — |
| 2026-05-12 (winner) | $400 | $464 | $0 |
| 2026-05-05 (loser) | $-260 | $198 | $0 |
| 2026-05-06 (loser) | $-300 | $0 | — |
| 2026-05-07 (loser) | $-45 | $616 | $0 |

**Per-quarter PnL:**
- 2025-Q1: $1,598.82
- 2025-Q2: $1,784.35
- 2025-Q3: $3,279.32
- 2025-Q4: $9,064.76
- 2026-Q1: $11,733.55
- 2026-Q2: $3,525.10

**Verdict:** PASS

**Reason:** wide_pnl=$30986, 4/29=$869, 5/12=$464, 5/05=$198 (J=$-260) — all gates pass.

## Next-Step Recommendation

**3 of 3 candidates passed real-fills validation.** Best is **candidate_1_0935_tp1_0.30** with real wide_pnl $36,450.

**Recommended next steps:**
1. Run walk-forward validation on the best candidate (`walk_forward_validate.py`).
2. Generate full 6-disclosure scorecard at `analysis/recommendations/v14_enhanced.json`.
3. Add to wake-loop queue: Monday-Ready Checklist for v14_enhanced.
4. **Do NOT auto-ratify** — J reviews scorecard before any production heartbeat.md change (CLAUDE.md OP 25).

## Provenance

- Script: `backtest/autoresearch/v14_enhanced_real_fills.py`
- Wide window: `2025-01-01` → `2026-05-12`
- OPRA cache: `backtest/data/options/` (7464 contracts)
- Master SPY/VIX: `data/spy_5m_2025-01-01_2026-05-12.csv`


---

**Walk-forward verdict: PASS** (T44c, 2026-05-13T19:44:18.539195) — TRAIN $18,549 (225 trades, 1,547/mo) vs TEST $17,901 (92 trades, 4,128/mo). Per-month ratio: 2.67x (>= 0.5x floor). See `docs/V14_ENHANCED-WALK-FORWARD-2026-05-13.md`.
