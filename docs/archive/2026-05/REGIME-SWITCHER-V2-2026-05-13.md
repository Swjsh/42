# REGIME_SWITCHER v2 — 2026-05-13 evening

Generated: 2026-05-13T22:51:11.435609
Wide window: 2025-01-01 -> 2026-05-12

## What changed since the morning grinder

- v14_enhanced sub-strategy: rebuilt with **GOOD T44b winner combo** + **T50b trailing-20%** kwargs
  - `strike_offset_bear=0, premium_stop_pct=-0.20, tp1_qty_fraction=0.50`
  - `no_trade_before='09:35', tp1_premium_pct=0.30, runner_target_premium_pct=2.5`
  - `profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10`
  - `profit_lock_mode='trailing', profit_lock_trail_pct=0.20`
  - **Calls orchestrator with `use_real_fills=True`** (NOT BS sim)
- SNIPER excluded entirely (T42-full real-fills 0/432 keepers)
  - Routes that would have hit SNIPER (TREND_DAY, FALLBACK, optionally CHOP) -> NONE_TRADE
  - chop_default_strategy locked to VWAP (SNIPER option removed from grid)
  - Grid size: 972 combos (was 1,296)
- VWAP + ODF cached results retained (still BS sim, was working morning)

## Strategy P&L matrix

| Strategy | Days | Total P&L | Wins | Losses | WR |
|---|---|---|---|---|---|
| v14_enhanced | 339 | $36621 | 125 | 92 | 0.58 |
| VWAP | 339 | $195 | 7 | 1 | 0.88 |
| ODF | 339 | $-480 | 53 | 50 | 0.51 |

## Grinder summary

- Keepers: 0
- Passed floors: 0
- Rejected: 972

## Best combo by edge_capture

- edge_capture: $687
- wide_pnl: $19935
- winners_capture: $687
- losers_added: $0
- anchor_classification_correct: 2/7
- passed_floors: False
- positive_quarters: 4/6
- top5_pct: 0.51
- max_drawdown: $2658

**Combo:**

```json
{
  "vix_high_thresh": 20.0,
  "vix_low_thresh": 19.0,
  "vix_chop_thresh": 18.0,
  "gap_thresh": 0.75,
  "gap_chop_thresh": 0.75,
  "range_thresh": 5.0,
  "range_chop_thresh": 5.0,
  "chop_default_strategy": "VWAP",
  "vix_jump_thresh": 1.5,
  "macro_proximity_hr": 24.0
}
```

**Per-anchor breakdown:**

| Anchor | J P&L | Floor | Engine | Regime | Strategy | Pass |
|---|---|---|---|---|---|---|
| 2026-04-29 | $+342 | $150 | $+0 | FALLBACK | NONE | FAIL |
| 2026-05-01 | $+470 | $30 | $+3 | GAP_DAY | v14_enhanced | FAIL |
| 2026-05-04 | $+730 | $180 | $+220 | GAP_DAY | v14_enhanced | OK |
| 2026-05-05 | $-260 | $150 | $+198 | GAP_DAY | v14_enhanced | OK |
| 2026-05-06 | $-300 | $100 | $+0 | GAP_DAY | v14_enhanced | OK |
| 2026-05-07 | $-165 | $0 | $+0 | MACRO_VETO | NONE | OK |
| 2026-05-12 | $+400 | $200 | $+464 | GAP_DAY | v14_enhanced | OK |

## Best combo by wide_pnl

- wide_pnl: $20770
- edge_capture: $467
- positive_quarters: 5/6

**Combo:**

```json
{
  "vix_high_thresh": 20.0,
  "vix_low_thresh": 17.0,
  "vix_chop_thresh": 18.0,
  "gap_thresh": 1.0,
  "gap_chop_thresh": 1.0,
  "range_thresh": 5.0,
  "range_chop_thresh": 4.0,
  "chop_default_strategy": "VWAP",
  "vix_jump_thresh": 1.5,
  "macro_proximity_hr": 24.0
}
```

**Regime distribution:**

```json
{
  "GAP_DAY": 145,
  "FALLBACK": 15,
  "EVENT_VOL": 110,
  "CHOP": 57,
  "TREND_DAY": 9,
  "MACRO_VETO": 2
}
```

**Strategy distribution (post-SNIPER-remap):**

```json
{
  "v14_enhanced": 145,
  "NONE": 26,
  "ODF": 110,
  "VWAP": 57
}
```

**Per-regime P&L:**

```json
{
  "GAP_DAY": 20770.42,
  "FALLBACK": 0.0,
  "EVENT_VOL": 0.0,
  "CHOP": 0.0,
  "TREND_DAY": 0.0,
  "MACRO_VETO": 0.0
}
```

## Comparison to standalone v14e B1 (trailing 20%)

- Standalone v14e B1 wide_pnl: $36621 (n=323)
- Switcher best wide_pnl: $20770 (n_trade_days=92)
- **Delta: $-15850**

## Verdict

REGIME_SWITCHER v2: 0 keepers passed floors. Best combo by wide_pnl=$20770, by edge=$687. Standalone v14e B1 (trailing 20%) wide_pnl=$36621. Delta=$-15850. v14_enhanced standalone is the headline ratifiable strategy.

- Ratifiable: **False**
- Headline strategy: **v14_enhanced standalone (B1 trailing 20%)**
- Delta vs standalone: $-15850

## Limitations / caveats (per OP 20)

1. **Account-size assumption:** v14e qty defaults from heartbeat (typically 3 contracts at $1k tier).
2. **Sample-bias disclosure:** 972-combo grinder = overfit risk on the 7 anchor days.
3. **OOS test:** NOT run yet — switcher's regime classifier overfits to anchors.
4. **Real-fills check:** v14e routed via `use_real_fills=True`; VWAP/ODF still BS sim (cached).
5. **Failure-mode enumeration:** see max_drawdown above.
6. **Concentration disclosure:** see top5_pct above.

## Files

- Modified `backtest/autoresearch/regime_switcher_prepass.py` (GOOD v14e combo + use_real_fills + SNIPER excluded from default --strategies)
- Modified `backtest/autoresearch/regime_switcher_evaluator.py` (SNIPER routes -> NONE_TRADE remap)
- Modified `backtest/autoresearch/regime_switcher_grinder.py` (chop_default_strategy locked to VWAP, grid 972)
- Regenerated `backtest/autoresearch/_state/regime_switcher_stage1/strategy_pnl_matrix.json`
- Regenerated `backtest/autoresearch/_state/regime_switcher_stage1/keepers.jsonl` + `rejections.jsonl`
- Wrote `analysis/recommendations/regime_switcher-v2.json`
- Wrote `docs/REGIME-SWITCHER-V2-2026-05-13.md`