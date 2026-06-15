---
proposed_validator: v_sizing_risk_cap_guard
title: Assert backtest position notional respects per_trade_risk_cap_pct at simulated equity
date: 2026-05-31
source: missed-week analysis (analysis/backtests/_TRUTH.md sizing caveat)
priority: medium
---

## Why
backtest/lib/orchestrator.py (L669-702) assigns trade_qty by a FIXED quality-tier ladder
(SUPER=15/ELITE=10/LEVEL=22/TRENDLINE_LEG2=20/TRENDLINE,BASE=3), decoupled from initial_equity
and per_trade_risk_cap_pct. Found 2026-05-31: a LEVEL-tier trade prints qty=22 even when
simulating the $747 Safe account -- 22 x ~$1.24 x 100 = ~$2,728 = ~365% of equity, which
Rule 6 (30% Safe / 50% Bold) forbids live. Raw backtest dollar P&L is therefore
non-representative at small accounts (only per-contract is portable). Live<->backtest drift (OP-16).

## Check (offline)
For each fired trade given run initial_equity E and account cap R (0.30 Safe / 0.50 Bold):
    notional = qty * entry_premium * 100
    ASSERT notional <= E * R + tolerance
Report per-run breach count + worst offender (% of equity). Converts the silent decoupling
into a visible, gym-tracked signal.

## run_live() stub
Audit-only: read latest dual-account run trades.csv (missed_week_{safe,bold}); report breach
counts. Do NOT alter sizing logic (Rule 9). Validator only SURFACES drift so J can decide:
wire equity-aware sizing into the backtest, or standardize on per-contract reporting.

## Acceptance
- crypto/validators/v{NN}_sizing_risk_cap_guard.py with run_offline()+run_live()
- registered in runner.py; full gym PASS; bump OP-26 stage count
- engine-benefit observability per OP-22 -- ships without weekend ratification
