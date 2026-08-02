# ANCHOR-VALIDATED -- fleet arm replay: safe-3 @ bold

Generated 2026-08-02T01:19:55.239081. Runner: `backtest/tools/fleet_arm_replay.py`.
Window: 2025-01-02 .. 2026-07-22.

## Config (all INPUTS -- every field overridable)

- arm_id: `safe-3`
- gate_override: `{'min_triggers': 2, 'require_confluence_or_sequence': True}`
- direction_lock: `None`
- strike_tiers: `bold` = [{'equity_min': 0.0, 'equity_max': 2000.0, 'strike_offset': -3, 'label': 'OTM-3'}, {'equity_min': 2000.0, 'equity_max': 10000.0, 'strike_offset': -2, 'label': 'OTM-2'}, {'equity_min': 10000.0, 'equity_max': 25000.0, 'strike_offset': -1, 'label': 'OTM-1'}, {'equity_min': 25000.0, 'equity_max': 999999999.0, 'strike_offset': 2, 'label': 'ITM-2'}]
- equity: $1,967.81
- exit_patch: `{'stop_mode': 'structure', 'profit_lock_mode': 'trailing'}`
- min_contracts: 3 | full_send: False
- structure_stop_enabled: True | structure_veto entry-layer modeled: False (inherited disclosed gap, see module docstring)

## Anchor validation (OP-16 sim-accuracy gate)

**23/27 real safe-3 engine fills reproduce within tolerance (85%). ALL PASS: False.**

> pass = same win/loss sign AND |replay-real| <= max($60.0, 30% of |real|) -- same convention as bold_fullhist_replay.py's own anchor gate; exact-cent parity not expected (resting-order-fill approximation, see exit_manager_walk.py's FILL-PRICE CONVENTION).

| Date | Symbol | Real P&L | Replay P&L | Same sign | Within tol | PASS |
|---|---|---|---|---|---|---|
| 2026-06-29 | SPY260629C00743000 | $-8.00 | $-17.60 | True | True | PASS |
| 2026-06-30 | SPY260630C00746000 | $-33.00 | $-36.60 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-3.00 | $-6.00 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-6.00 | $-4.20 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-6.00 | $-4.20 | True | True | PASS |
| 2026-06-30 | SPY260630C00750000 | $-18.00 | $-4.80 | True | True | PASS |
| 2026-06-30 | SPY260630C00751000 | $-6.00 | $-1.80 | True | True | PASS |
| 2026-07-01 | SPY260701C00751000 | $-12.00 | $-15.60 | True | True | PASS |
| 2026-07-02 | SPY260702C00754000 | $-15.00 | -- | -- | -- | **NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM** |
| 2026-07-06 | SPY260706C00754000 | $-6.00 | $-2.40 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $-3.00 | $-1.80 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $-3.00 | $-3.00 | True | True | PASS |
| 2026-07-06 | SPY260706C00754000 | $+0.00 | $-2.40 | True | True | PASS |
| 2026-07-06 | SPY260706C00755000 | $-3.00 | $-1.20 | True | True | PASS |
| 2026-07-08 | SPY260708P00741000 | $-69.00 | $-60.00 | True | True | PASS |
| 2026-07-08 | SPY260708C00749000 | $-6.00 | $-7.80 | True | True | PASS |
| 2026-07-08 | SPY260708C00748000 | $-9.00 | $-5.40 | True | True | PASS |
| 2026-07-09 | SPY260709C00751000 | $-48.00 | $-30.60 | True | True | PASS |
| 2026-07-09 | SPY260709C00750000 | $-18.00 | $+131.30 | False | False | FAIL |
| 2026-07-15 | SPY260715C00757000 | $-42.00 | $-45.00 | True | True | PASS |
| 2026-07-17 | SPY260717P00741000 | $+0.00 | $-3.00 | True | True | PASS |
| 2026-07-17 | SPY260717P00742000 | $+0.00 | $-63.00 | True | False | FAIL |
| 2026-07-27 | SPY260727P00734000 | $-87.00 | $-66.00 | True | True | PASS |
| 2026-07-28 | SPY260728C00744000 | $-33.00 | $-46.50 | True | True | PASS |
| 2026-07-29 | SPY260729P00734000 | $+72.00 | $+81.00 | True | True | PASS |
| 2026-07-29 | SPY260729C00740000 | $+265.00 | $+357.00 | True | False | FAIL |
| 2026-07-31 | SPY260731C00747000 | $+75.00 | $+87.80 | True | True | PASS |

## Population

- Raw gated entries: 54
- Excluded, synthetic-priced (disclosed, never blended into P&L): 2
- Excluded, no SPY day: 0
- Benched by confidence (design-level, not a data gap): False

Notes:
- v15_strike_offset_per_tier injected @ equity=$1,967.81 -> resolved sim strike_offset=3 (table=bold)
- require ELITE (confluence/sequence) -> keep ELITE only

## Headline (real fills only -- synthetic-priced trades excluded)

| Total P&L | N trades | WR | Avg/trade |
|---|---|---|---|
| $+243.78 | 52 | 0.3654 | $+4.69 |

---
_Source: `backtest/tools/fleet_arm_replay.py`. Raw JSON with full trade log: see the sibling `.json` file next to this report._
