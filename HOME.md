# 🎛️ Gamma — HOME

> Auto-generated `2026-08-23 17:03:46 Sunday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,103.25 | **-0.12** | flat |
| bold-2 | 5,243.68 | **+0.00** | flat |
| safe-3 | 4,724.13 | **+0.00** | flat |
| risky-1 | 5,118.97 | **+0.00** | flat |
| risky-3 | 4,802.79 | **+0.00** | flat |
| **BOOK** | | **-0.12** | |

## Today's levels

*as of `2026-08-23T17:03:36-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **748.09** — SHELF_747.29_748.89_2026-08-23
- **750.82** — SHELF_750.02_751.62_2026-08-23
- **764.17** — PRIOR_DAY_LOW_2026-08-23
- **765.62** — PRIOR_DAY_CLOSE_2026-08-23
- **765.94** — MEMORY_SUP_111
- **767.85** — PRIOR_DAY_HIGH_2026-08-23
- **768.29** — MEMORY_RES_92
- **768.9** — SHELF_768.10_769.70_2026-08-23
- **769.46** — MEMORY_RES_77
- **770.38** — MEMORY_RES_71
- **772.62** — SHELF_771.82_773.42_2026-08-23

## What the engine sees

> No core decision rows for 2026-08-23 (weekend, holiday, or the engine is dark).
- bias: **no-trade**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **book lane** (fillsim) `HOLD` — last tick `2026-08-21T16:00:01` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `FLATTEN` — last tick `2026-08-21T16:00:01` · session GLOBEX
- **sim book** equity $1,899.83 (start $2,000.00) · day $-69.99 · 8 trades
- **feed** GREEN MES GREEN (10.1m)
- **edge #3** (MES→MNQ divergence) 11/20 round trips · mean $23.84 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 17 round trips · forward clock running
- **last review** `2026-08-21` **GREEN** · coverage GREEN (79/78 ticks) · 0 rule break(s)
- **broker probe** `2026-08-22T18:05:03` → **SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)** (session WEEKEND, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 3/7 audits GREEN · validators: 104/104 pass · for `2026-08-21`
    - ⚠️ `heartbeat-tick-audit` **YELLOW** — 381 live ticks, 1 MISALIGNED-CRITICAL (0.3%) [HOLD-only — no trading impact]
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=152)
- **twin** last journal row `2026-08-23T20:55:38.480143+00:00` · 1846 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-08-23\|2026-08-23]] | **-0.12** | -0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-21\|2026-08-21]] | **-589.46** | -312.36 | -66.75 | -99.60 | -44.00 | -66.75 | 36 |
| [[journal/2026-08-20\|2026-08-20]] | **808.65** | 265.15 | 174.50 | 0.00 | 0.00 | 369.00 | 19 |
| [[journal/2026-08-19\|2026-08-19]] | **262.54** | -114.51 | 89.25 | 185.55 | 253.25 | -151.00 | 29 |
| [[journal/2026-08-18\|2026-08-18]] | **161.54** | 81.79 | 79.75 | 0.00 | 0.00 | 0.00 | 5 |
| [[journal/2026-08-17\|2026-08-17]] | **122.22** | -36.33 | 359.75 | 0.00 | 0.00 | -201.20 | 11 |
| [[journal/2026-08-14\|2026-08-14]] | **-1839.98** | -390.67 | -620.76 | -287.35 | -468.60 | -72.60 | 18 |
| [[journal/2026-08-13\|2026-08-13]] | **1744.05** | 443.49 | 248.25 | 456.56 | 401.25 | 194.50 | 38 |
| [[journal/2026-08-12\|2026-08-12]] | **-900.14** | -141.81 | -229.24 | -102.60 | -137.00 | -289.49 | 77 |
| [[journal/2026-08-11\|2026-08-11]] | **38.34** | 101.49 | 6.25 | 0.00 | -110.50 | 41.10 | 35 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-08-23|2026-08-23]]
- [[journal/2026-08-21|2026-08-21]]
- [[journal/2026-08-20|2026-08-20]]
- [[journal/2026-08-19|2026-08-19]]
- [[journal/2026-08-18|2026-08-18]]
- [[journal/2026-08-17|2026-08-17]]
- [[journal/2026-08-14|2026-08-14]]
