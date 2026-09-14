# Draft params changes (Treasurer accumulator)

> DRAFT only. J ratifies on the weekend per rule 9 + OP-24. Treasurer NEVER edits params*.json.
> Freeze context: config freeze 2026-08-31 → 2026-10-30. Risk REDUCTIONS ship at the 2026-09-29 safety checkpoint with prereg + guard + RED-proof + revert line; risk EXPANSIONS wait for 10-30.

## 2026-08-13 (carried) — Safe: enable equity-scaled min_contracts
- File: `automation/state/params.json`
- Field: `min_contracts_equity_scaled`
- Current: false
- Proposed: true
- Reason: pre-reg'd 2026-08-13 (J: fix account sizing). Executor uses `min_contracts=3` as a CEILING; at $5,779.65 EOD equity the validated ~15%-of-equity sizing is capped at 3 contracts (~9% of equity). Scaling by equity/`min_contracts_baseline_equity` ($2,000) restores the A/B-validated fraction (recency-sizing-ab.json, policy_dominates=true).
- Impact: ceiling rises from 3 → ~8 contracts at current equity; risk fraction returns to validated level. NOT the 5.6x equity-proportional figure (C31 stands).
- Guard: `backtest/tests/test_min_contracts_equity_scaling_2026_08_13.py`
- Revert: set `min_contracts_equity_scaled=false` (single key)
- Freeze classification: risk REDUCTION vs current undersized floor → eligible for 2026-09-29 checkpoint. Awaiting J ratification (open question in 2026-09-14 audit).

## 2026-08-13 (carried) — Bold: enable equity-scaled min_contracts
- File: `automation/state/aggressive/params.json`
- Field: `min_contracts_equity_scaled`
- Current: false
- Proposed: true
- Reason: same as above; Bold baseline $1,648, floor-as-ceiling binds at 5 contracts at $5,483.19 EOD equity.
- Impact: ceiling rises from 5 → ~16 contracts at current equity (capped by tier base 8 / elite 12 and `max_contracts_per_entry=5` — note: `max_contracts_per_entry=5` may re-bind as the new ceiling; J should confirm intended per-entry cap when ratifying).
- Guard: same test file covers both params files.
- Revert: single key to false.
- Freeze classification: risk REDUCTION → eligible for 2026-09-29 checkpoint.

## 2026-09-14 (new) — Stale static kill-switch dollar field (both files)
- File: `automation/state/params.json` and `automation/state/aggressive/params.json`
- Field: `daily_loss_kill_switch_dollars`
- Current: 400 (both)
- Proposed: null (delete) or derive from `daily_loss_kill_switch_pct` × live equity at rearm
- Reason: the operative daily limit is %-based and recomputed at premarket rearm (Safe -$1,659.52, Bold -$2,779.32 as of 9/11). The static $400 field is 4–7x tighter than the enforced limit; any consumer reading it as operative would over-trip. Needs a one-line grep for consumers before ratification — if no live consumer reads it, deletion is safe; if one does, that consumer is misconfigured and routes to Coach.
- Impact: none on enforced behavior (breakers are the source of truth); removes a misleading knob.
- Revert: restore `"daily_loss_kill_switch_dollars": 400`.

## 2026-09-14 (ops question, NOT a draft) — day_trades_used_5d counter source
- Both breakers show `day_trades_used_5d=4` (computed 2026-09-11) while the journal shows 9/11 day-trades: safe=6, safe-3=4, risky-1=5.
- `pdt_gate_mode="cash_settlement"` means no PDT constraint applies IF all arms are cash-settled — but that account-type fact is UNVERIFIED this session (Alpaca MCP unavailable). If any arm is margin under $25K, >3 day-trades in a rolling 5-day window is a broker-side breach.
- No param change proposed. J to confirm account settlement types on Alpaca; if any arm is margin, this escalates to RED and the breaker counter source needs reconciliation.
