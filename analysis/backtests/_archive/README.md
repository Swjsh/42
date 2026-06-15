# Archived Backtest Versions

Historical backtest runs and findings docs, kept for forensics. Do not cite
these numbers as current — they reflect prior versions of the simulator.

## Version history

| Version | Date | Status | Why archived |
|---|---|---|---|
| historical_regime_no_8_no_9 | 2026-05-07 | superseded | First sweep; filter 8/9 disabled to test pre-2026-05-05 historical regime |
| production_rules_v1 | 2026-05-07 | superseded | First production-rules attempt |
| production_rules_v2_post_fixes | 2026-05-07 | superseded | After mid-day filter fixes |
| production_rules_v3_full_sync | 2026-05-07 | superseded | After heartbeat/filters.py drift sync |
| production_rules_v4_with_candlesticks | 2026-05-07 | DECISIVELY REJECTED | Candles-as-triggers test: −56% P&L vs v3, codified as operating principle 6 |
| production_rules_v5_candlesticks_as_awareness | 2026-05-07 | superseded | v3 numbers exactly; rolled back v4 candle triggers |
| production_rules_v6_real_fills | 2026-05-07 | SUPERSEDED (look-ahead bug) | Real OPRA fills first attempt; entry used trigger-bar VWAP (look-ahead) — fake +$891 result |
| production_rules_v7_honest_fills | 2026-05-07 | superseded | Fixed look-ahead; honest -$364 baseline |
| findings_2026-05-07.md | 2026-05-07 | superseded | Original findings doc, stale numbers |
| v5_vs_v6_real_fills.md | 2026-05-07 | superseded | v6 used look-ahead bug, claims invalidated |
| v7_honest_findings.md | 2026-05-07 | superseded by v8 | v7 was the previous canonical; v8 added tiered exits + chart TP1 |

## Current canonical

Live production rules are in `analysis/backtests/production_rules_v8_tiered_exits/`
and the decision-making doctrine is in `CLAUDE.md` operating principle 11.

Filter ratification: `analysis/backtests/filter_sweep_findings.md` (2026-05-07
ratified Configuration B = min_triggers ≥ 1).
