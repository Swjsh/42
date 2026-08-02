# ANCHOR-VALIDATED -- fleet arm replay: risky-3 @ bold_core

Generated 2026-08-02T01:22:20.556225. Runner: `backtest/tools/fleet_arm_replay.py`.
Window: 2025-01-02 .. 2026-07-22.

## Config (all INPUTS -- every field overridable)

- arm_id: `risky-3`
- gate_override: `{'min_triggers': 1}`
- direction_lock: `None`
- strike_tiers: `bold_core` = [{'equity_min': 0.0, 'equity_max': 2000.0, 'strike_offset': 0, 'label': 'ATM'}, {'equity_min': 2000.0, 'equity_max': 10000.0, 'strike_offset': -2, 'label': 'OTM-2'}, {'equity_min': 10000.0, 'equity_max': 25000.0, 'strike_offset': -1, 'label': 'OTM-1'}, {'equity_min': 25000.0, 'equity_max': 999999999.0, 'strike_offset': 2, 'label': 'ITM-2'}]
- equity: $2,121.61
- exit_patch: `{'stop_mode': 'structure', 'profit_lock_mode': 'trailing', 'trail_pct': 0.2}`
- min_contracts: 5 | full_send: False
- structure_stop_enabled: True | structure_veto entry-layer modeled: False (inherited disclosed gap, see module docstring)

## Anchor validation (OP-16 sim-accuracy gate)

**34/38 real risky-3 engine fills reproduce within tolerance (89%). ALL PASS: False.**

> pass = same win/loss sign AND |replay-real| <= max($60.0, 30% of |real|) -- same convention as bold_fullhist_replay.py's own anchor gate; exact-cent parity not expected (resting-order-fill approximation, see exit_manager_walk.py's FILL-PRICE CONVENTION).

| Date | Symbol | Real P&L | Replay P&L | Same sign | Within tol | PASS |
|---|---|---|---|---|---|---|
| 2026-06-29 | SPY260629C00743000 | $-48.00 | $-33.60 | True | True | PASS |
| 2026-06-30 | SPY260630C00746000 | $-60.00 | $-60.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-5.00 | $-10.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-10.00 | $-7.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-10.00 | $-8.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-5.00 | $-9.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00751000 | $-15.00 | $-5.00 | True | True | PASS |
| 2026-07-01 | SPY260701C00751000 | $-20.00 | $-26.00 | True | True | PASS |
| 2026-07-02 | SPY260702P00743000 | $-80.00 | $-50.00 | True | True | PASS |
| 2026-07-02 | SPY260702C00754000 | $-25.00 | -- | -- | -- | **NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM** |
| 2026-07-02 | SPY260702P00742000 | $+491.00 | $+225.00 | True | False | FAIL |
| 2026-07-02 | SPY260702P00739000 | $-152.00 | -- | -- | -- | **NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM** |
| 2026-07-06 | SPY260706C00753000 | $-24.00 | $-19.20 | True | True | PASS |
| 2026-07-06 | SPY260706C00753000 | $-12.00 | $-14.40 | True | True | PASS |
| 2026-07-06 | SPY260706C00753000 | $-24.00 | $-24.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $+0.00 | $-4.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00755000 | $-5.00 | $-2.00 | True | True | PASS |
| 2026-07-07 | SPY260707P00743000 | $-25.00 | $-45.00 | True | True | PASS |
| 2026-07-07 | SPY260707P00746000 | $-25.00 | $-24.00 | True | True | PASS |
| 2026-07-07 | SPY260707P00746000 | $-10.00 | $-20.00 | True | True | PASS |
| 2026-07-08 | SPY260708P00741000 | $-80.00 | $-94.00 | True | True | PASS |
| 2026-07-08 | SPY260708P00741000 | $+0.00 | $-25.00 | True | True | PASS |
| 2026-07-08 | SPY260708C00749000 | $-10.00 | $-13.00 | True | True | PASS |
| 2026-07-08 | SPY260708C00748000 | $-20.00 | $-10.00 | True | True | PASS |
| 2026-07-09 | SPY260709C00751000 | $-35.00 | $-49.00 | True | True | PASS |
| 2026-07-09 | SPY260709C00751000 | $-30.00 | $-53.00 | True | True | PASS |
| 2026-07-09 | SPY260709C00750000 | $-35.00 | $+204.80 | False | False | FAIL |
| 2026-07-13 | SPY260713P00747000 | $-25.00 | $-25.00 | True | True | PASS |
| 2026-07-15 | SPY260715C00757000 | $-75.00 | $-77.50 | True | True | PASS |
| 2026-07-17 | SPY260717P00741000 | $+15.00 | $+5.00 | True | True | PASS |
| 2026-07-17 | SPY260717P00743000 | $+233.00 | $+170.20 | True | True | PASS |
| 2026-07-27 | SPY260727P00734000 | $-85.00 | $-107.50 | True | True | PASS |
| 2026-07-29 | SPY260729P00734000 | $+115.00 | $+135.00 | True | True | PASS |
| 2026-07-29 | SPY260729C00740000 | $+471.00 | $+596.20 | True | True | PASS |
| 2026-07-30 | SPY260730P00733000 | $-165.00 | $-116.00 | True | True | PASS |
| 2026-07-30 | SPY260730P00734000 | $-110.00 | $-104.00 | True | True | PASS |
| 2026-07-31 | SPY260731C00746000 | $+126.00 | $+138.60 | True | True | PASS |
| 2026-07-31 | SPY260731C00747000 | $-80.00 | $-100.00 | True | True | PASS |

## Population

- Raw gated entries: 360
- Excluded, synthetic-priced (disclosed, never blended into P&L): 15
- Excluded, no SPY day: 0
- Benched by confidence (design-level, not a data gap): False

Notes:
- v15_strike_offset_per_tier injected @ equity=$2,121.61 -> resolved sim strike_offset=2 (table=bold_core)

## Headline (real fills only -- synthetic-priced trades excluded)

| Total P&L | N trades | WR | Avg/trade |
|---|---|---|---|
| $+17,782.16 | 345 | 0.2696 | $+51.54 |

---
_Source: `backtest/tools/fleet_arm_replay.py`. Raw JSON with full trade log: see the sibling `.json` file next to this report._
