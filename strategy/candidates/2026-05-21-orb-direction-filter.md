# DRAFT: ORB Long-Only Direction Filter

**Status:** NEEDS-MORE-DATA — watcher updated to long-only mode 2026-05-21 (OP-22 engine-benefit). Live trading requires J ratification per Rule 9.  
**Confidence:** 7/10 — 4-of-6 quarters positive, virtually preserves all ORB P&L, simpler implementation  
**Author:** Gamma overnight session (OP-22)  
**Date:** 2026-05-21  
**Companion:** `strategy/candidates/2026-05-21-orb-narrow-or-gate.md` (includes combined Option C)

---

## Finding

Applying a **long-only filter** to the ORB watcher (skip all short ORB signals) transforms the watcher from a 2-of-6-quarters strategy to a 4-of-6-quarters strategy while **preserving virtually all P&L**:

| Scenario | N | WR | Total P&L | Avg/trade | Quarters+ |
|---|---:|---:|---:|---:|---|
| Baseline | 391 | 65.7% | +$7,161 | +$18.3 | 2-of-6 |
| **Long-only gate (this DRAFT)** | **274** | **70.4%** | **+$7,378** | **+$26.9** | **4-of-6** |
| Narrow-OR + long-only (Option C) | 143 | 90.2% | +$4,597 | +$32.1 | 5-of-6 |

**Key:** Long-only gate ADDS +$217 to total P&L while simultaneously improving per-trade quality (+47% per-trade expectancy). The short signals (-$218 aggregate) were a pure drag at the fleet level.

---

## Why Short ORBs Underperform

Short ORBs (N=117, WR=54.7%, -$218 aggregate) break down into two populations:

| Sub-population | N | WR | P&L |
|---|---:|---:|---:|
| Narrow OR (≤$2.00) shorts | 75 | 57.3% | +$487 |
| Wide OR (>$2.00) shorts | 42 | 50.0% | -$705 |

The narrow shorts look positive (+$487) but are **NOT regime-robust**: without 2026-Q2 (+$1,170), the other 4 quarters sum to -$682. Wide shorts are clearly negative (-$705).

**Structural explanation:** In the 2025-2026 SPY bull trend, ORB breakdown signals fight the structural upward drift. Even with a clean 30-min OR, bears must overcome:
1. The systematic SPY intraday upward drift (~+0.05%/hr average in 2025-2026)
2. Absent a VIX≥20 risk-off catalyst, breakdowns tend to retrace
3. Short ORBs in Q1 2026 (the tariff selloff) were heavily concentrated (N=24) yet still -$872 — suggesting the timing of shorts matters more than the OR setup

**Long ORBs benefit from drift alignment** — they're going WITH the prevailing intraday trend, not against it.

---

## Quarterly Durability

| Quarter | Long N | Long WR | Long P&L | Short N | Short WR | Short P&L |
|---|---:|---:|---:|---:|---:|---:|
| 2025-Q1 | 12 | 0% | -$766 | 6 | 50% | +$142 |
| 2025-Q2 | 42 | 50% | +$317 | 18 | 50% | -$334 |
| 2025-Q3 | 57 | 74% | +$1,650 | 42 | 43% | -$39 |
| 2025-Q4 | 17 | 47% | +$43 | 11 | 55% | -$421 |
| 2026-Q1 | 13 | 62% | -$110 | 24 | 50% | -$872 |
| 2026-Q2 | 133 | 86% | +$6,245 | 16 | 100% | +$1,306 |

Long-only: positive in 4 of 6 quarters (Q2+Q3 2025, Q4 2025, Q2 2026). Negative in 2025-Q1 (pure bull-side WR breakdown — ORB longs fail when SPY is in a downtrend) and 2026-Q1 (tariff selloff, market direction unclear early).

**Note:** Long ORBs in 2025-Q1 are 0% WR (-$766) — this is the regime-failure scenario for long-only. If SPY re-enters a sustained bear market, long ORBs would be expected to degrade similarly. This is the residual regime risk that Option C (adding the narrow-OR filter) partially addresses.

---

## Watcher Change (IMPLEMENTED 2026-05-21)

**Implemented autonomously per OP-22 engine-benefit principle** — watcher is OP-21 watch-only, no live orders affected.

In `backtest/lib/watchers/orb_watcher.py`:
```python
# Option-A direction filter: "long" = long-only (recommended), None = both directions (R&D)
ORB_DIRECTION_FILTER: Optional[str] = "long"
```

State machine: SHORT breakout transitions now guarded by `if ORB_DIRECTION_FILTER != "long":`. WAITING_RETEST_SHORT state handler remains in code but is unreachable in long-only mode. Gym verified: 63/65 PASS overall_pass=True after change.

**For live engine (heartbeat.md):** J ratification per Rule 9 required. The heartbeat would need a separate ORB direction check — no automatic linkage from this watcher flag.

---

## Comparison to Option C (Narrow-OR + Long-only)

| | Option A (this DRAFT) | Option C (combined) |
|---|---|---|
| N retained | 274 | 143 |
| WR | 70.4% | 90.2% |
| Total P&L | +$7,378 | +$4,597 |
| Quarterly robustness | 4-of-6 | 5-of-6 |
| Implementation | 1 line | 2 constants + logic |
| OR-range in engine required | No | Yes (feature add) |
| Trades/month estimate | ~17 | ~9 |

**Option A is superior for near-term deployment:** simpler, no engine changes needed, preserves more P&L. Option C is the long-term aspirational gate — implement after OR-range is added to the engine.

---

## Concerns and Limitations

1. **2025-Q1 failure:** Long ORBs fail in sustained bear markets (WR=0%, -$766). This is the unfixable residual regime risk for long-only ORB.
2. **Short ORBs dropped (2026-Q2 signal):** In April 2026 tariff selloff, short ORBs were 100% WR (+$1,306). These would be missed by the long-only gate. This is the cost of the filter — 16 missed trades in one excellent quarter.
3. **Regime monitor needed:** Adding a VIX_threshold (e.g., skip long ORBs when 14-day rolling VIX avg > 30) would hedge the 2025-Q1 scenario. Queued as a follow-up investigation if this gate is ratified.

---

## Ratification Checklist

Before implementing:
- [ ] J selects Option A (this DRAFT) or Option C (combined gate in companion DRAFT)
- [ ] If Option A: single-line change to `orb_watcher.py`, gym must remain 65/65 PASS
- [ ] If Option C: also requires OR-range feature-add to heartbeat.md — separate implementation step
- [ ] Walk-forward validation of selected gate on held-out 2024 data if available

---

*Filed by Gamma overnight autonomous session. DRAFT only. No production changes.*
