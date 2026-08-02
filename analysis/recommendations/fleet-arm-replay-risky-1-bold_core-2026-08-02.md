# ANCHOR-VALIDATED -- fleet arm replay: risky-1 @ bold_core

> **ATM-TIER LIMITATION:** NO real fills exist yet at ANY ATM-priced tier for this arm as of this build (bold_core shipped 2026-07-31 23:13 MT after close; weekend is non-trading) -- this cell's population/exit fidelity is anchored against this arm's OLDER (pre-ATM) real fills, NOT proof the ATM numbers themselves reproduce reality.

Generated 2026-08-02T01:21:08.363556. Runner: `backtest/tools/fleet_arm_replay.py`.
Window: 2025-01-02 .. 2026-07-22.

## Config (all INPUTS -- every field overridable)

- arm_id: `risky-1`
- gate_override: `{'full_send': True}`
- direction_lock: `None`
- strike_tiers: `bold_core` = [{'equity_min': 0.0, 'equity_max': 2000.0, 'strike_offset': 0, 'label': 'ATM'}, {'equity_min': 2000.0, 'equity_max': 10000.0, 'strike_offset': -2, 'label': 'OTM-2'}, {'equity_min': 10000.0, 'equity_max': 25000.0, 'strike_offset': -1, 'label': 'OTM-1'}, {'equity_min': 25000.0, 'equity_max': 999999999.0, 'strike_offset': 2, 'label': 'ITM-2'}]
- equity: $1,756.87
- exit_patch: `{'tp1_premium_pct': 0.5, 'stop_mode': 'structure'}`
- min_contracts: 5 | full_send: True
- structure_stop_enabled: True | structure_veto entry-layer modeled: False (inherited disclosed gap, see module docstring)

## Anchor validation (OP-16 sim-accuracy gate)

**20/24 real risky-1 engine fills reproduce within tolerance (83%). ALL PASS: False.**

> pass = same win/loss sign AND |replay-real| <= max($60.0, 30% of |real|) -- same convention as bold_fullhist_replay.py's own anchor gate; exact-cent parity not expected (resting-order-fill approximation, see exit_manager_walk.py's FILL-PRICE CONVENTION).

| Date | Symbol | Real P&L | Replay P&L | Same sign | Within tol | PASS |
|---|---|---|---|---|---|---|
| 2026-06-29 | SPY260629C00743000 | $-48.00 | $-33.60 | True | True | PASS |
| 2026-06-30 | SPY260630C00746000 | $-80.00 | $+139.30 | False | False | FAIL |
| 2026-06-30 | SPY260630C00750000 | $+0.00 | $-10.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-10.00 | $-7.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-18.00 | $-9.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-30.00 | $-8.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00751000 | $-10.00 | $-3.00 | True | True | PASS |
| 2026-07-01 | SPY260701C00751000 | $-20.00 | $-26.00 | True | True | PASS |
| 2026-07-02 | SPY260702C00754000 | $-25.00 | -- | -- | -- | **NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM** |
| 2026-07-06 | SPY260706C00754000 | $-10.00 | $-4.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $-5.00 | $-3.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $-5.00 | $-5.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $+0.00 | $-4.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00755000 | $-5.00 | $-2.00 | True | True | PASS |
| 2026-07-08 | SPY260708P00741000 | $-80.00 | $-94.00 | True | True | PASS |
| 2026-07-08 | SPY260708C00749000 | $-10.00 | $-13.00 | True | True | PASS |
| 2026-07-08 | SPY260708C00748000 | $-20.00 | $-10.00 | True | True | PASS |
| 2026-07-09 | SPY260709C00751000 | $-75.00 | $-50.00 | True | True | PASS |
| 2026-07-09 | SPY260709C00750000 | $-35.00 | $+116.60 | False | False | FAIL |
| 2026-07-15 | SPY260715C00757000 | $-75.00 | $-77.50 | True | True | PASS |
| 2026-07-17 | SPY260717P00741000 | $+0.00 | $-5.00 | True | True | PASS |
| 2026-07-17 | SPY260717P00742000 | $+0.00 | $+71.90 | False | False | FAIL |
| 2026-07-27 | SPY260727P00734000 | $-85.00 | $-107.50 | True | True | PASS |
| 2026-07-29 | SPY260729C00740000 | $+418.00 | $+502.00 | True | True | PASS |

## Population

- Raw gated entries: 361
- Excluded, synthetic-priced (disclosed, never blended into P&L): 19
- Excluded, no SPY day: 0
- Benched by confidence (design-level, not a data gap): False

Notes:
- v15_strike_offset_per_tier injected @ equity=$1,756.87 -> resolved sim strike_offset=0 (table=bold_core)

## Headline (real fills only -- synthetic-priced trades excluded)

| Total P&L | N trades | WR | Avg/trade |
|---|---|---|---|
| $+12,465.90 | 342 | 0.4123 | $+36.45 |

---
_Source: `backtest/tools/fleet_arm_replay.py`. Raw JSON with full trade log: see the sibling `.json` file next to this report._
