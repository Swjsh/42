# 🎛️ Gamma — HOME

> Auto-generated `2026-08-11 18:55:07 Tuesday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,311.82 | **+101.49** | flat |
| bold-2 | 5,213.51 | **+6.25** | flat |
| safe-3 | 4,573.55 | **+0.00** | flat |
| risky-1 | 5,120.55 | **-110.50** | flat |
| risky-3 | 5,029.06 | **+41.10** | flat |
| **BOOK** | | **+38.34** | |

## Today's levels

*as of `2026-08-11T18:53:37-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **750.98** — SHELF_750.18_751.78_2026-08-11
- **752.63** — SHELF_751.83_753.43_2026-08-11
- **754.71** — SHELF_753.91_755.51_2026-08-11
- **768.3** — MEMORY_SUP_64
- **769.03** — MEMORY_SUP_66
- **769.2** — INTRADAY_RTH_LOW_2026-08-11
- **769.79** — INTRADAY_SWING_LOW_2026-08-11
- **771.1** — INTRADAY_SWING_HIGH_2026-08-11
- **771.44** — MEMORY_RES_156
- **771.62** — PRIOR_DAY_LOW_2026-08-11
- **772.27** — MEMORY_RES_131
- **772.39** — INTRADAY_PML_2026-08-11
- **772.87** — PRIOR_DAY_CLOSE_2026-08-11
- **773.03** — MEMORY_RES_162
- **774.61** — INTRADAY_RTH_HIGH_2026-08-11
- **774.96** — INTRADAY_PMH_2026-08-11

## What the engine sees

- **772 ticks** today — `HOLD` 701 · `NOT_FLAT` 32 · `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` 16 · `SKIP_STALE_TRIGGER` 12 · `PLACED` 5 · `SKIP_DOJI_ENTRY_BAR` 5
- last tick `2026-08-11T15:55:05` — spy **770.39** · ribbon **BEAR** · vix 15.25 · bull **6** / bear **8**
- bull triggers `[]` · blocked by `[5, 7, 10, 11]`
- bias: **no-trade**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **book lane** (fillsim) `HOLD` — last tick `2026-08-11T16:00:03` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `FLATTEN` — last tick `2026-08-11T16:00:04` · session GLOBEX
- **sim book** equity $1,969.80 (start $2,000.00) · day $3.77 · 5 trades
- **feed** GREEN MES GREEN (10.1m)
- **edge #3** (MES→MNQ divergence) 7/20 round trips · mean $97.16 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 0 round trips · forward clock running
- **last review** `2026-08-11` **GREEN** · coverage GREEN (80/78 ticks) · 0 rule break(s)
- **broker probe** `2026-08-11T18:05:03` → **H2_SESSION_ARTIFACT** (session GLOBEX, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 4/7 audits GREEN · validators: 104/104 pass · for `2026-08-11`
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=128)
- **twin** last journal row `2026-08-11T21:40:58.843164+00:00` · 909 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-08-11\|2026-08-11]] | **38.34** | 101.49 | 6.25 | 0.00 | -110.50 | 41.10 | 35 |
| [[journal/2026-08-10\|2026-08-10]] | **-760.52** | -141.32 | -270.25 | -156.30 | -465.50 | 272.85 | 19 |
| [[journal/2026-08-09\|2026-08-09]] | **-0.11** | -0.11 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-07\|2026-08-07]] | **-2687.00** | -375.00 | 0.00 | -1048.00 | -640.00 | -624.00 | 24 |
| [[journal/2026-08-06\|2026-08-06]] | **1465.00** | 339.00 | 0.00 | 0.00 | 296.00 | 830.00 | 11 |
| [[journal/2026-08-05\|2026-08-05]] | **-1935.00** | -339.00 | 0.00 | 0.00 | -138.00 | -1458.00 | 29 |
| [[journal/2026-08-04\|2026-08-04]] | **3624.00** | 662.00 | 479.00 | 637.00 | 1041.00 | 805.00 | 59 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-08-11|2026-08-11]]
- [[journal/2026-08-10|2026-08-10]]
- [[journal/2026-08-09|2026-08-09]]
- [[journal/2026-08-07|2026-08-07]]
- [[journal/2026-08-06|2026-08-06]]
- [[journal/2026-08-05|2026-08-05]]
- [[journal/2026-08-04|2026-08-04]]
