# 🎛️ Gamma — HOME

> Auto-generated `2026-08-29 16:19:18 Saturday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,562.98 | **-0.06** | flat |
| bold-2 | 5,749.47 | **+0.00** | flat |
| safe-3 | 5,852.70 | **+0.00** | flat |
| risky-1 | 6,495.12 | **+0.00** | flat |
| risky-3 | 4,282.65 | **+0.00** | flat |
| **BOOK** | | **-0.06** | |

## Today's levels

*as of `2026-08-29T07:58:36-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **750.82** — SHELF_750.02_751.62_2026-08-29
- **761.32** — SHELF_760.52_762.12_2026-08-29
- **765.5** — MEMORY_SUP_205
- **766.76** — MEMORY_SUP_103
- **767.58** — SHELF_766.78_768.38_2026-08-29
- **768.3** — MEMORY_SUP_116
- **769.33** — PRIOR_DAY_CLOSE_2026-08-29
- **769.51** — MEMORY_RES_163
- **770.62** — MEMORY_RES_92
- **772.62** — SHELF_771.82_773.42_2026-08-29
- **774.71** — SHELF_773.91_775.51_2026-08-29
- **775.3** — PRIOR_DAY_HIGH_2026-08-29

## What the engine sees

> No core decision rows for 2026-08-29 (weekend, holiday, or the engine is dark).
- bias: **no-trade**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **lane health** `RED` (as of `2026-08-29 16:19:02`) — [RED] can_enter: MES pending_entry STUCK 21929.0m (>30m) since 2026-08-14T10:50:04 -- GHOST-ORDER DEADLOCK signature (outage #1, 2026-08-14): the lane cannot open a new position while this row exists
- **book lane** (fillsim) `HOLD` — last tick `2026-08-28T16:00:01` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `ERROR_NOT_CONNECTED` — last tick `2026-08-28T16:00:01` · session GLOBEX
- **sim book** equity $1,899.83 (start $2,000.00) · day $-69.99 · 8 trades
- **feed** GREEN MES GREEN (10.1m)
- **edge #3** (MES→MNQ divergence) 13/20 round trips · mean $24.22 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 11 round trips · forward clock running
- **last review** `2026-08-28` **GREEN** · coverage GREEN (80/78 ticks) · 0 rule break(s)
- **broker probe** `2026-08-29T16:18:01` → **SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)** (session WEEKEND, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 4/7 audits GREEN · validators: 104/104 pass · for `2026-08-28`
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=103)
- **twin** last journal row `2026-08-29T15:36:39.228902+00:00` · 2239 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-08-28\|2026-08-28]] | **1301.00** | 256.64 | 293.50 | 562.85 | 649.75 | -461.74 | 26 |
| [[journal/2026-08-27\|2026-08-27]] | **1893.79** | 321.58 | 213.25 | 587.70 | 827.51 | -56.25 | 29 |
| [[journal/2026-08-26\|2026-08-26]] | **38.85** | 0.00 | 0.00 | 38.85 | 0.00 | 0.00 | 2 |
| [[journal/2026-08-25\|2026-08-25]] | **-220.55** | -60.15 | 0.00 | -60.15 | -100.25 | 0.00 | 6 |
| [[journal/2026-08-24\|2026-08-24]] | **-57.48** | -57.48 | 0.00 | 0.00 | 0.00 | 0.00 | 4 |
| [[journal/2026-08-23\|2026-08-23]] | **-0.12** | -0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-21\|2026-08-21]] | **-589.46** | -312.36 | -66.75 | -99.60 | -44.00 | -66.75 | 36 |
| [[journal/2026-08-20\|2026-08-20]] | **808.65** | 265.15 | 174.50 | 0.00 | 0.00 | 369.00 | 19 |
| [[journal/2026-08-19\|2026-08-19]] | **262.54** | -114.51 | 89.25 | 185.55 | 253.25 | -151.00 | 29 |
| [[journal/2026-08-18\|2026-08-18]] | **161.54** | 81.79 | 79.75 | 0.00 | 0.00 | 0.00 | 5 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-08-28|2026-08-28]]
- [[journal/2026-08-27|2026-08-27]]
- [[journal/2026-08-26|2026-08-26]]
- [[journal/2026-08-25|2026-08-25]]
- [[journal/2026-08-24|2026-08-24]]
- [[journal/2026-08-23|2026-08-23]]
- [[journal/2026-08-21|2026-08-21]]
