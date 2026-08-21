# 🎛️ Gamma — HOME

> Auto-generated `2026-08-20 22:09:08 Thursday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,416.53 | **+265.15** | flat |
| bold-2 | 5,311.37 | **+174.50** | flat |
| safe-3 | 4,824.21 | **+0.00** | flat |
| risky-1 | 5,163.73 | **+0.00** | flat |
| risky-3 | 4,871.47 | **+369.00** | flat |
| **BOOK** | | **+808.65** | |

## Today's levels

*as of `2026-08-20T22:08:37-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **744.98** — SHELF_744.18_745.78_2026-08-20
- **748.09** — SHELF_747.29_748.89_2026-08-20
- **750.82** — SHELF_750.02_751.62_2026-08-20
- **762.04** — INTRADAY_RTH_LOW_2026-08-20
- **763.8** — INTRADAY_SWING_HIGH_2026-08-20
- **764.15** — INTRADAY_PML_2026-08-20
- **768.1** — PRIOR_DAY_LOW_2026-08-20
- **768.29** — MEMORY_RES_92
- **768.9** — SHELF_768.10_769.70_2026-08-20
- **769.0** — PRIOR_DAY_CLOSE_2026-08-20
- **769.5** — MEMORY_RES_87
- **770.63** — INTRADAY_PMH_2026-08-20
- **772.47** — PRIOR_DAY_HIGH_2026-08-20
- **772.62** — SHELF_771.82_773.42_2026-08-20

## What the engine sees

- **772 ticks** today — `HOLD` 679 · `NOT_FLAT` 27 · `SKIP_LATE_ENTRY` 23 · `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` 16 · `SKIP_STALE_TRIGGER` 12 · `SKIP_MIN_PREMIUM_FLOOR` 9
- last tick `2026-08-20T15:55:05` — spy **763.37** · ribbon **BEAR** · vix 15.99 · bull **7** / bear **6**
- bull triggers `[]` · blocked by `[5, 7, 11]`
- bias: **bearish**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **book lane** (fillsim) `HOLD` — last tick `2026-08-20T16:00:01` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `FLATTEN` — last tick `2026-08-20T16:00:01` · session GLOBEX
- **sim book** equity $1,899.83 (start $2,000.00) · day $-69.99 · 8 trades
- **feed** YELLOW MES YELLOW (15.1m)
- **edge #3** (MES→MNQ divergence) 10/20 round trips · mean $37.60 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 0 round trips · forward clock running
- **last review** `2026-08-20` **GREEN** · coverage GREEN (79/78 ticks) · 0 rule break(s)
- **broker probe** `2026-08-20T18:05:03` → **H2_SESSION_ARTIFACT** (session GLOBEX, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 3/7 audits GREEN · validators: 103/104 pass (KNOWN_FLAKY excluded: 1) · for `2026-08-20`
    - ⚠️ `heartbeat-tick-audit` **YELLOW** — 381 live ticks, 1 MISALIGNED-CRITICAL (0.3%) [HOLD-only — no trading impact]
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=99)
- **twin** last journal row `2026-08-21T01:58:37.511288+00:00` · 1630 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-08-20\|2026-08-20]] | **808.65** | 265.15 | 174.50 | 0.00 | 0.00 | 369.00 | 19 |
| [[journal/2026-08-19\|2026-08-19]] | **262.54** | -114.51 | 89.25 | 185.55 | 253.25 | -151.00 | 29 |
| [[journal/2026-08-18\|2026-08-18]] | **161.54** | 81.79 | 79.75 | 0.00 | 0.00 | 0.00 | 5 |
| [[journal/2026-08-17\|2026-08-17]] | **122.22** | -36.33 | 359.75 | 0.00 | 0.00 | -201.20 | 11 |
| [[journal/2026-08-14\|2026-08-14]] | **-1839.98** | -390.67 | -620.76 | -287.35 | -468.60 | -72.60 | 18 |
| [[journal/2026-08-13\|2026-08-13]] | **1744.05** | 443.49 | 248.25 | 456.56 | 401.25 | 194.50 | 38 |
| [[journal/2026-08-12\|2026-08-12]] | **-900.14** | -141.81 | -229.24 | -102.60 | -137.00 | -289.49 | 77 |
| [[journal/2026-08-11\|2026-08-11]] | **38.34** | 101.49 | 6.25 | 0.00 | -110.50 | 41.10 | 35 |
| [[journal/2026-08-10\|2026-08-10]] | **-760.52** | -141.32 | -270.25 | -156.30 | -465.50 | 272.85 | 19 |
| [[journal/2026-08-09\|2026-08-09]] | **-0.11** | -0.11 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-08-20|2026-08-20]]
- [[journal/2026-08-19|2026-08-19]]
- [[journal/2026-08-18|2026-08-18]]
- [[journal/2026-08-17|2026-08-17]]
- [[journal/2026-08-14|2026-08-14]]
- [[journal/2026-08-13|2026-08-13]]
- [[journal/2026-08-12|2026-08-12]]
