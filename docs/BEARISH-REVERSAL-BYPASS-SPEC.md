# BEARISH_REVERSAL_BYPASS — Setup Class Spec

**Created:** 2026-06-17  
**Motivating trade:** 5/01/2026 +$470 (J anchor, EC=470, unreachable by BEARISH_REJECTION)  
**Status:** REJECTED 2026-06-18. IS phase failed (N=13, WR=38.5%). A/B OOS REJECT (WF=0.348 < 0.70).  
**Code gate:** `bearish_reversal_bypass=True` in filters.py  

---

## Why this setup exists

BEARISH_REJECTION_RIDE_THE_RIBBON requires ribbon=BEAR (filter_5). On 5/01/2026, ribbon was BULL all day — the engine never considered entry even as price rejected hard from FHH 724.24 for a +$470 move.

This setup class unlocks bearish entries when price clearly rejects a named resistance while the ribbon is still BULL. It is **countertrend**, not a ribbon-aligned trade, so it carries wider risk and smaller size.

---

## Entry Conditions

| # | Condition | Notes |
|---|-----------|-------|
| a | Ribbon = BULL or MIXED | NOT BEAR — BEAR entries already covered by BEARISH_REJECTION |
| b | First Hour High (FHH) formed | FHH = max(09:30–09:55 ET bars) computed once per session |
| c | Price tests FHH from above **after 10:05 ET** | Bar closes BELOW FHH (`fhh_level_rejection` trigger fires) |
| d | NO `trendline_rejection` co-trigger | Trendline-only relaxation path already exists; this is level-only |
| e | VIX gate **bypassed** | Countertrend in calm regime (low VIX) is valid; VIX gate doesn't apply |

---

## Architecture

### How it's implemented (filters.py)

```
bearish_reversal_bypass: bool = False
```

When `bearish_reversal_bypass=True`:
1. `fhh_level_rejection` fires (requires `include_first_hour_high=True`)
2. `trendline_rejection` NOT in triggers
3. `ribbon_now.stack == "BULL"`

→ filter_5 (ribbon stack blocker) removed  
→ filter_8 (VIX gate blocker) removed  
→ Each removal adds -1 to `bearish_reversal_demerit` (score penalty)

### Prerequisite params

```python
include_first_hour_high=True     # enables FHH level computation (max 09:30-09:55 high)
include_bearish_reversal_bypass=True  # enables the ribbon bypass logic in filters
```

### What stays active

All other filters remain unmodified:
- F1: time >= 09:35 ET gate
- F6: ribbon spread >= 30 cents
- F7: SPY trend not strongly BULL (bearishness context)
- F9: volume confirmation
- F10: minimum trigger count (min_triggers)

---

## Why FHH specifically (not all level_rejection)

The bypass is restricted to `fhh_level_rejection` and NOT standard `level_rejection`. Rationale:

- Standard `level_rejection` on a BULL ribbon fires on any multi-day level in any context — too noisy, would produce dozens of false countertrend entries
- FHH is a **session-fresh resistance**: price built up momentum to a new session high, then failed to hold it — a clean, time-defined reversal signal
- FHH rejection specifically: "price ran up to the morning high and failed" — the setup has a clear narrative
- Note: standard `level_rejection` is also blocked by `block_level_rejection=True` in AGG baseline params

---

## Key differences from BEARISH_REJECTION

| Dimension | BEARISH_REJECTION | BEARISH_REVERSAL_BYPASS |
|-----------|------------------|------------------------|
| Ribbon requirement | BEAR (filter_5 hard) | BULL or MIXED (filter_5 bypassed) |
| VIX requirement | >threshold + rising | Bypassed (filter_8 removed) |
| Level type | Any named level (multi_day, VWAP, round, etc.) | FHH only |
| Score impact | Full 10 points | -2 demerit (countertrend penalty) |
| Trigger pattern | Ribbon-aligned continuation | Countertrend level rejection |
| Size | Full risk cap | Smaller (countertrend) |

---

## Suggested separate params (for Phase 2)

These are hypotheses, not ratified. Phase 1 (IS validation) uses AGG default params:

| Param | Current AGG | Proposed bypass |
|-------|-------------|-----------------|
| `per_trade_risk_cap_pct` | 0.50 | 0.30 |
| `premium_stop_pct_bear` | -0.07 | -0.12 (wider, countertrend moves faster) |
| `tp1_premium_pct` | 0.75 | 0.50 (take profits sooner, countertrend) |
| `tp1_qty_fraction` | 0.667 | 0.50 (smaller TP1, keep runner) |

Phase 2 param sweep: only after IS validation passes (N>=15, WR>=0.50).

---

## V4 quality discriminators (tested 2026-06-16, not ratified)

Two optional quality gates exist in filters.py. Both are ANTI-CORRELATED with J's 5/01 anchor:

| Gate | Effect | Why NOT used |
|------|--------|--------------|
| `fhh_quality_proximity` | Require FHH within X$ of multi_day_level | Removes 5/01 (FHH above all prior levels) |
| `fhh_above_max_prior_min` | Require FHH >= X above max(multi_day_levels) | Gap-up screen, 5/08 specific |

Both gates are set to `None` (off) for IS validation.

---

## IS Validation Results (FINAL)

**Phase 1 (2025-01-02 to 2025-09-30):** N=14 bypass trades, WR=28.6%, total=+5. TARGET FAIL (need N>=15, WR>=50%).  
**Full IS (2025-01-02 to 2026-02-26):** N=13 new bypass trades, WR=38.5%, total=-322. TARGET FAIL.  
**A/B OOS test (2026-06-18):** Best config BYPASS_GAP1.0: OOS_D=+36, WF=0.348 (need 0.70). ALL REJECT.

Key finding: 5/01 J anchor (+$470) fires in bypass at simulated +$24 only — 20x gap due to strike mismatch (simulator uses ITM-2 generic puts; J traded SPY 721P with specific fill). The bypass architecture correctly identifies the setup but cannot replicate J's actual option P&L.

Feature is IMPLEMENTED (gated behind `include_bearish_reversal_bypass=True`), not enabled in production. Revisit when:
1. FHH rejection population grows to N>=20 in OOS
2. Strike-selection logic can target the specific contracts J would buy
3. Results: `analysis/recommendations/bearish_reversal_bypass_is.json`, `analysis/recommendations/bearish_reversal_bypass_ab.json`

---

## Relationship to existing scripts

| Script | Purpose |
|--------|---------|
| `backtest/autoresearch/bearish_reversal_bypass_is.py` | Phase 1: 2025-01 to 2025-09, raw signal |
| `backtest/autoresearch/agg_fhh_bypass.py` | Phase 2: Full IS+OOS, AGG, 5-gate validation |
| `backtest/autoresearch/safe_fhh_bypass.py` | Phase 2: Full IS+OOS, Safe, 5-gate validation |

---

## Not in scope (for this spec)

- BULLISH_REVERSAL equivalent (price tests support from below with ribbon=BEAR) — separate spec
- Chart stop implementation (`chart_stop_distance` param) — requires 2-3h simulator change
- Non-FHH level bypass (e.g. PDH, VWAP rejection with ribbon=BULL) — too noisy, tracked in FUTURE-IMPROVEMENTS
