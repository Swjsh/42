# SNIPER_LEVEL_BREAK Morning Brief

_Generated: 2026-05-13T04:04:10_
_Real-fills RE-RUN: 2026-05-13T09:09:16 with FULL OPRA cache (7,358 contracts)_

## ⚠️ REAL-FILLS VERDICT: CAVEAT (effective FAIL) — SNIPER NOT RATIFIABLE

**4 of 4 measured days FLIP from BS-winners to real-fills LOSSES** (full OPRA cache, OP 20 ±20% tolerance gate):

| Date | BS sim | Real OPRA fills | Diff% | Status |
|---|---|---|---|---|
| 2025-04-07 (top-3 abs) | +$288 | **-$926** | -422% | MEASURED FAIL |
| 2026-04-29 (J anchor) | +$182 | **-$329** | -281% | MEASURED FAIL |
| 2026-05-04 (J anchor) | +$192 | **-$234** | -222% | MEASURED FAIL |
| 2026-05-05 (J anchor) | +$202 | **-$236** | -217% | MEASURED FAIL |
| 2025-04-08 (top-3 abs) | +$278 | n/a | n/a | BLOCKED (OPRA strike-edge) |
| 2026-03-26 (top-3 abs) | +$264 | n/a | n/a | BLOCKED (OPRA strike-edge) |

**Pattern:** SNIPER enters then immediately gets stopped at -10% premium. BS sim systematically over-estimates entry premium (likely IV proxy `vix/100` ignores per-strike per-DTE skew). The BS sim's positive P&L predictions are NOT achievable with real fills.

**This is OP 20 non-theatre validation working as designed** — caught a strategy that looked great on BS but doesn't survive real money before deployment.

**Path forward (tonight's queue):** Retire BS sim entirely per J. Re-run entire SNIPER pipeline (Stages 1-5) using `simulator_real.py` against the now-full OPRA cache. New winner combo expected to differ — particularly premium_stop=-0.10 may need to relax to absorb real-fills entry slippage.

## Pre-real-fills BS-sim numbers (INVALIDATED — keep for reference only):

- Stage 5 winner. **edge_capture=$373** on J anchor days, **wide_pnl=$38022** over 16 months.
- Wide WR **93.0%** across **228** trades (all BS).
- Max drawdown **$415** sequential (BS).
- Top-5 days = **3.5%** of P&L (BS).
- Positive in **6/6** quarters (BS).

**These metrics derive from BS sim and DO NOT reflect achievable P&L.**

## Winning combo

| Knob | Value |
|---|---|
| `vol_mult` | `1.1` |
| `body_min_cents` | `0.02` |
| `min_stars` | `2` |
| `strike_offset` | `2` |
| `premium_stop_pct` | `-0.1` |
| `tp1_premium_pct` | `0.4` |
| `runner_target_pct` | `1.25` |
| `profit_lock_threshold_pct` | `0.0` |
| `profit_lock_stop_offset_pct` | `0.08` |
| `tp1_qty_fraction` | `0.667` |
| `qty` | `10` |
| `proximity_dollars` | `1.5` |
| `require_break_above_open` | `True` |

## J anchor days (must catch winners, must skip losers)

| Date | Engine P&L |
|---|---|
| 2026-04-29 | $+182 |
| 2026-05-01 | $+0 |
| 2026-05-04 | $+192 |
| 2026-05-05 | $+202 |
| 2026-05-06 | $+0 |
| 2026-05-07 | $+235 |
| 2026-05-07_2 | $+235 |

## Quarter breakdown (regime stability)

| Quarter | P&L |
|---|---|
| 2025-Q1 | $+6316 |
| 2025-Q2 | $+5230 |
| 2025-Q3 | $+6374 |
| 2025-Q4 | $+7757 |
| 2026-Q1 | $+8980 |
| 2026-Q2 | $+3365 |

## Stage funnel

- Stage 1: 1728 combos sweep
- Stage 2: 4 keepers refined
- Stage 3 (regime-robustness gates): 4 passed
- Stage 4 (sub-window stability): 4 passed
- Stage 5: 1 winner picked

## OP 20 disclosures (the honest read)

- **Account-size scaling:** Headline assumes qty=10. $1K paper → qty=3 (~30% of P&L). $10K paper → qty=10 full. $25K+ no cap.
- **Sample bias:** picked from 1728+ combos via 4 stage gates. Survivorship bias possible.
- **OOS (BS-sim, invalidated):** Walk-forward TRAIN $25,676 / TEST $12,537. Per-month ratio 1.35x. UNRELIABLE because the underlying sim is broken (see Real-fills row).
- **Real-fills (FULL OPRA cache 7,358 contracts, T35 RE-RUN 2026-05-13 09:09 ET):** **CAVEAT confirmed.** 4 of 4 measured days FAIL ±20% gate: 2025-04-07 BS +$288 → real -$926 (-422%); 2026-04-29 J anchor BS +$182 → real -$329 (-281%); 2026-05-04 J anchor BS +$192 → real -$234 (-222%); 2026-05-05 J anchor BS +$202 → real -$236 (-217%). 2 of top-3 still BLOCKED on strike-edge (2025-04-08 strike 521, 2026-03-26 strike 652). BS sim systematically over-estimates entry premium; real fills hit -10% premium stop immediately. See `analysis/recommendations/sniper-v1-realfills.json`.
- **Worst quarter:** ('2026-Q2', 3365.47)
- **Concentration:** top-5 days = 3.5% of P&L.
- **Regime sensitivity:** 6/6 quarters net-positive.

## Next actions (J review)

1. Review scorecard at `analysis/recommendations/sniper-v1.json`
2. **Walk-forward validation: PASS 2026-05-13** — TRAIN $25,676 / TEST $12,537 / per-month 1.35x. Full report: `docs/WALK-FORWARD-SNIPER-2026-05-13.md`.
3. **Real-fills validation: CAVEAT CONFIRMED 2026-05-13 09:09 ET** — RE-RUN with FULL OPRA cache (7,358 contracts). BS sim does NOT survive contact with OPRA on 4/4 measured days. Full report: `docs/REAL-FILLS-SNIPER-2026-05-13.md`. **DO NOT LIVE-PROMOTE on BS sim numbers. Tonight's queue: T41 retire BS sim entirely + T42 re-run SNIPER pipeline on real fills.**
4. **P0 blocker:** expand OPRA ingest (J anchors + top-20 BS days, all candidate strikes ±2) before any further SNIPER iteration.
5. Watch-only deployment ONLY: log to `watcher-observations.jsonl`; do not trade until BS sim is recalibrated against OPRA AND 3+ live wins.
6. J ratification (rule 9): no live trading until human approval + real-fills caveat resolved.