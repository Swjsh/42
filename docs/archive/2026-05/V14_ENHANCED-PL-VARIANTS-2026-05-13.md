# v14_enhanced Profit-Lock Variants — 2026-05-13 (T44d)

Generated: `2026-05-13T21:51:44.344990`

## Hypothesis

v14_enhanced was ratified tonight with FIXED profit-lock (threshold 5%, offset 10%). The 5/13 738C variant test (4,410 combos) showed FIXED PL caps ride-the-ribbon winners — the actual J trade was +$2,932 but the same combo with PL armed would have been +$304. TRAILING (chandelier-style) and STEPPED PL hypothesised to preserve chop-day rescue WITHOUT capping big-day upside.

## Variants tested

| Label | Mode | Threshold | Offset | Trail % |
|-------|------|-----------|--------|---------|
| A_fixed_baseline | fixed | 5% | 10% | — |
| B1_trailing_20pct | trailing | 5% | 10% | 20% |
| B2_trailing_30pct | trailing | 5% | 10% | 30% |
| B3_trailing_40pct | trailing | 5% | 10% | 40% |
| B4_trailing_50pct | trailing | 5% | 10% | 50% |
| C_stepped | stepped | 5% | 10% | — |

## Locked combo (v14_enhanced winner from walk-forward)

```python
{
  "strike_offset_bear": 0,
  "min_triggers_bear": 1,
  "premium_stop_pct_bear": -0.2,
  "tp1_qty_fraction": 0.5,
  "no_trade_before": "09:35",
  "profit_lock_threshold_pct": 0.05,
  "profit_lock_stop_offset_pct": 0.1,
  "tp1_premium_pct": 0.3,
  "runner_target_premium_pct": 2.5
}
```

## Per-variant verdict summary

| Variant | wide_pnl | n | WR | max_dd | top5 | +Q | 4/29 | 5/01 | 5/04 | 5/07 | 5/12 | 5/05 | 5/06 | Verdict |
|---------|---------:|---:|----:|-------:|-----:|---:|------:|------:|------:|------:|------:|------:|------:|---------|
| A_fixed_baseline | $36,450 | 317 | 56.8% | $2,857 | 37.1% | 6 | $869 | $3 | $214 | $616 | $464 | $198 | $0 | **PASS** |
| B1_trailing_20pct | $36,621 | 323 | 57.3% | $2,857 | 32.0% | 6 | $869 | $3 | $220 | $616 | $464 | $198 | $0 | **PASS** |
| B2_trailing_30pct | $29,776 | 321 | 57.3% | $2,857 | 30.6% | 6 | $869 | $3 | $214 | $616 | $464 | $198 | $0 | **FAIL** |
| B3_trailing_40pct | $33,726 | 318 | 56.9% | $2,857 | 34.9% | 6 | $869 | $3 | $214 | $616 | $464 | $198 | $0 | **FAIL** |
| B4_trailing_50pct | $33,231 | 318 | 56.9% | $2,857 | 34.1% | 6 | $869 | $3 | $214 | $616 | $464 | $198 | $0 | **FAIL** |
| C_stepped | $34,635 | 319 | 56.7% | $2,857 | 31.0% | 6 | $869 | $3 | $214 | $616 | $464 | $198 | $0 | **FAIL** |

## Verdict gates

- `wide_pnl ≥ baseline` (FIXED: $36,449.97)
- `4/29 ≥ $100`
- `5/12 ≥ $100`
- `5/05 ≥ -$260` (J's loss)
- `max_dd ≤ baseline + $1,000` ($3,857.10)

## A_fixed_baseline

- mode: `fixed`
- trail_pct: `None`
- wide_pnl: **$36,449.97** vs baseline $36,449.97 (Δ $+0.00)
- n_trades: 317 vs baseline 317
- wr: 56.8% vs baseline 56.8%
- max_drawdown: $2,857.10 vs baseline $2,857.10
- top5_pct: 37.1%
- positive_quarters: 6/6
- real_fills/bs_fallback: 293/24

**Per-J-anchor:**

| Date | J PnL | Variant PnL | vs Baseline |
|------|------:|------------:|------------:|
| 2026-04-29 (winner) | $342 | $869 | +0 |
| 2026-05-01 (winner) | $470 | $3 | +0 |
| 2026-05-04 (winner) | $730 | $214 | +0 |
| 2026-05-07 (winner) | $616 | $616 | +0 |
| 2026-05-12 (winner) | $464 | $464 | +0 |
| 2026-05-05 (loser) | $-260 | $198 | +0 |
| 2026-05-06 (loser) | $-300 | $0 | +0 |

**Per-quarter:**
- 2025-Q1: $2,707.94
- 2025-Q2: $799.39
- 2025-Q3: $6,019.36
- 2025-Q4: $9,022.64
- 2026-Q1: $14,363.65
- 2026-Q2: $3,537.00

**Verdict:** PASS
**Reason:** wide_pnl=$36450, 4/29=$869, 5/12=$464, 5/05=$198, max_dd=$2857

## B1_trailing_20pct

- mode: `trailing`
- trail_pct: `0.2`
- wide_pnl: **$36,620.77** vs baseline $36,449.97 (Δ $+170.80)
- n_trades: 323 vs baseline 317
- wr: 57.3% vs baseline 56.8%
- max_drawdown: $2,857.10 vs baseline $2,857.10
- top5_pct: 32.0%
- positive_quarters: 6/6
- real_fills/bs_fallback: 299/24

**Per-J-anchor:**

| Date | J PnL | Variant PnL | vs Baseline |
|------|------:|------------:|------------:|
| 2026-04-29 (winner) | $342 | $869 | +0 |
| 2026-05-01 (winner) | $470 | $3 | +0 |
| 2026-05-04 (winner) | $730 | $220 | +6 |
| 2026-05-07 (winner) | $616 | $616 | +0 |
| 2026-05-12 (winner) | $464 | $464 | +0 |
| 2026-05-05 (loser) | $-260 | $198 | +0 |
| 2026-05-06 (loser) | $-300 | $0 | +0 |

**Per-quarter:**
- 2025-Q1: $2,894.14
- 2025-Q2: $1,580.39
- 2025-Q3: $6,049.66
- 2025-Q4: $9,006.84
- 2026-Q1: $12,825.15
- 2026-Q2: $4,264.60

**Verdict:** PASS
**Reason:** wide_pnl=$36621, 4/29=$869, 5/12=$464, 5/05=$198, max_dd=$2857

## B2_trailing_30pct

- mode: `trailing`
- trail_pct: `0.3`
- wide_pnl: **$29,776.47** vs baseline $36,449.97 (Δ $-6,673.50)
- n_trades: 321 vs baseline 317
- wr: 57.3% vs baseline 56.8%
- max_drawdown: $2,857.10 vs baseline $2,857.10
- top5_pct: 30.6%
- positive_quarters: 6/6
- real_fills/bs_fallback: 297/24

**Per-J-anchor:**

| Date | J PnL | Variant PnL | vs Baseline |
|------|------:|------------:|------------:|
| 2026-04-29 (winner) | $342 | $869 | +0 |
| 2026-05-01 (winner) | $470 | $3 | +0 |
| 2026-05-04 (winner) | $730 | $214 | +0 |
| 2026-05-07 (winner) | $616 | $616 | +0 |
| 2026-05-12 (winner) | $464 | $464 | +0 |
| 2026-05-05 (loser) | $-260 | $198 | +0 |
| 2026-05-06 (loser) | $-300 | $0 | +0 |

**Per-quarter:**
- 2025-Q1: $2,768.84
- 2025-Q2: $832.39
- 2025-Q3: $5,617.46
- 2025-Q4: $6,176.34
- 2026-Q1: $10,844.45
- 2026-Q2: $3,537.00

**Verdict:** FAIL
**Reason:** wide_pnl=$29776 < baseline=$36450

## B3_trailing_40pct

- mode: `trailing`
- trail_pct: `0.4`
- wide_pnl: **$33,725.77** vs baseline $36,449.97 (Δ $-2,724.20)
- n_trades: 318 vs baseline 317
- wr: 56.9% vs baseline 56.8%
- max_drawdown: $2,857.10 vs baseline $2,857.10
- top5_pct: 34.9%
- positive_quarters: 6/6
- real_fills/bs_fallback: 294/24

**Per-J-anchor:**

| Date | J PnL | Variant PnL | vs Baseline |
|------|------:|------------:|------------:|
| 2026-04-29 (winner) | $342 | $869 | +0 |
| 2026-05-01 (winner) | $470 | $3 | +0 |
| 2026-05-04 (winner) | $730 | $214 | +0 |
| 2026-05-07 (winner) | $616 | $616 | +0 |
| 2026-05-12 (winner) | $464 | $464 | +0 |
| 2026-05-05 (loser) | $-260 | $198 | +0 |
| 2026-05-06 (loser) | $-300 | $0 | +0 |

**Per-quarter:**
- 2025-Q1: $2,707.94
- 2025-Q2: $799.39
- 2025-Q3: $5,344.46
- 2025-Q4: $8,116.04
- 2026-Q1: $13,220.95
- 2026-Q2: $3,537.00

**Verdict:** FAIL
**Reason:** wide_pnl=$33726 < baseline=$36450

## B4_trailing_50pct

- mode: `trailing`
- trail_pct: `0.5`
- wide_pnl: **$33,230.97** vs baseline $36,449.97 (Δ $-3,219.00)
- n_trades: 318 vs baseline 317
- wr: 56.9% vs baseline 56.8%
- max_drawdown: $2,857.10 vs baseline $2,857.10
- top5_pct: 34.1%
- positive_quarters: 6/6
- real_fills/bs_fallback: 294/24

**Per-J-anchor:**

| Date | J PnL | Variant PnL | vs Baseline |
|------|------:|------------:|------------:|
| 2026-04-29 (winner) | $342 | $869 | +0 |
| 2026-05-01 (winner) | $470 | $3 | +0 |
| 2026-05-04 (winner) | $730 | $214 | +0 |
| 2026-05-07 (winner) | $616 | $616 | +0 |
| 2026-05-12 (winner) | $464 | $464 | +0 |
| 2026-05-05 (loser) | $-260 | $198 | +0 |
| 2026-05-06 (loser) | $-300 | $0 | +0 |

**Per-quarter:**
- 2025-Q1: $2,707.94
- 2025-Q2: $799.39
- 2025-Q3: $5,319.26
- 2025-Q4: $7,859.74
- 2026-Q1: $13,007.65
- 2026-Q2: $3,537.00

**Verdict:** FAIL
**Reason:** wide_pnl=$33231 < baseline=$36450

## C_stepped

- mode: `stepped`
- trail_pct: `None`
- wide_pnl: **$34,634.57** vs baseline $36,449.97 (Δ $-1,815.40)
- n_trades: 319 vs baseline 317
- wr: 56.7% vs baseline 56.8%
- max_drawdown: $2,857.10 vs baseline $2,857.10
- top5_pct: 31.0%
- positive_quarters: 6/6
- real_fills/bs_fallback: 295/24

**Per-J-anchor:**

| Date | J PnL | Variant PnL | vs Baseline |
|------|------:|------------:|------------:|
| 2026-04-29 (winner) | $342 | $869 | +0 |
| 2026-05-01 (winner) | $470 | $3 | +0 |
| 2026-05-04 (winner) | $730 | $214 | +0 |
| 2026-05-07 (winner) | $616 | $616 | +0 |
| 2026-05-12 (winner) | $464 | $464 | +0 |
| 2026-05-05 (loser) | $-260 | $198 | +0 |
| 2026-05-06 (loser) | $-300 | $0 | +0 |

**Per-quarter:**
- 2025-Q1: $2,850.44
- 2025-Q2: $1,508.89
- 2025-Q3: $5,394.81
- 2025-Q4: $7,408.19
- 2026-Q1: $13,037.65
- 2026-Q2: $4,434.60

**Verdict:** FAIL
**Reason:** wide_pnl=$34635 < baseline=$36450

## Best variant

**B1_trailing_20pct** with wide_pnl $36,621 vs baseline FIXED $36,450 (Δ $+171).

**Recommended morning brief headline:** v14_enhanced should be ratified with **TRAILING PL** (trail_pct=0.2) — NOT fixed PL=5%/10%.

**Required follow-up before live deploy:**
- Walk-forward validate the new PL on the train/test split
- Update `analysis/recommendations/v14_enhanced-real-fills.json`
- Update Monday-Ready Checklist with the new PL setting
- J explicit ratification before any heartbeat.md / params.json change

## Caveats

- **Per-quality exit-knob matrix NOT applied.** Same caveat as v14_enhanced-real-fills.json — orchestrator's TRENDLINE/LEVEL/ELITE/SUPER per-quality `_grinder_overrides` only fires through the BS path.
- **BS-sim fallback on OPRA cache miss.** Each variant reports its fallback %; if >20% the result is less than a true real-fills test.
- **TRAILING is asymmetric.** When a winner runs, trailing extends the floor; when a chop-day reverses just past arm threshold, trailing locks +5% (initial arm offset). FIXED locks +10% on the same chop-day. So small chop-day P&L might be slightly LOWER with trailing — that's the expected trade-off, not a bug.

## Provenance

- Script: `backtest/autoresearch/v14_enhanced_pl_variants.py`
- Wrapper: `backtest/lib/simulator_real_trailing.py`
- Wide window: `2025-01-01` → `2026-05-12`
- OPRA cache: `backtest/data/options/` (7486 contracts)
- Master SPY/VIX: `data/spy_5m_2025-01-01_2026-05-12.csv`