# 🎛️ Gamma — HOME

> Auto-generated `2026-08-25 18:43:20 Tuesday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 4,985.49 | **-60.15** | flat |
| bold-2 | 5,243.68 | **+0.00** | flat |
| safe-3 | 4,663.98 | **-60.15** | flat |
| risky-1 | 5,018.72 | **-100.25** | flat |
| risky-3 | 4,802.79 | **+0.00** | flat |
| **BOOK** | | **-220.55** | |

## Today's levels

*as of `2026-08-25T15:58:36-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **748.09** — SHELF_747.29_748.89_2026-08-25
- **750.82** — SHELF_750.02_751.62_2026-08-25
- **761.32** — SHELF_760.52_762.12_2026-08-25
- **762.08** — PRIOR_DAY_LOW_2026-08-25
- **763.05** — INTRADAY_RTH_LOW_2026-08-25
- **763.16** — MEMORY_SUP_75
- **763.7** — PRIOR_DAY_CLOSE_2026-08-25
- **764.15** — INTRADAY_PML_2026-08-25
- **764.3** — MEMORY_SUP_98
- **764.87** — INTRADAY_SWING_LOW_2026-08-25
- **765.22** — PRIOR_DAY_HIGH_2026-08-25
- **765.51** — MEMORY_RES_138
- **765.63** — INTRADAY_SWING_HIGH_2026-08-25
- **765.91** — MEMORY_RES_132
- **766.49** — MEMORY_RES_61
- **766.78** — INTRADAY_RTH_HIGH_2026-08-25
- **768.15** — INTRADAY_PMH_2026-08-25
- **768.29** — MEMORY_RES_92
- **768.9** — SHELF_768.10_769.70_2026-08-25
- **769.46** — MEMORY_RES_77
- **772.62** — SHELF_771.82_773.42_2026-08-25

## What the engine sees

- **772 ticks** today — `HOLD` 750 · `SKIP_STALE_TRIGGER` 12 · `SKIP_MIN_PREMIUM_FLOOR` 5 · `NOT_FLAT` 4 · `PLACED` 1
- last tick `2026-08-25T15:55:04` — spy **765.475** · ribbon **BULL** · vix 15.44 · bull **9** / bear **5**
- bull triggers `['ribbon_flip']` · blocked by `[6, 11]`
- bias: **bullish**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **book lane** (fillsim) `HOLD` — last tick `2026-08-25T16:00:04` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `FLATTEN` — last tick `2026-08-25T16:00:04` · session GLOBEX
- **sim book** equity $1,899.83 (start $2,000.00) · day $-69.99 · 8 trades
- **feed** GREEN MES GREEN (10.2m)
- **edge #3** (MES→MNQ divergence) 12/20 round trips · mean $37.00 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 4 round trips · forward clock running
- **last review** `2026-08-24` **GREEN** · coverage GREEN (80/78 ticks) · 0 rule break(s)
- **broker probe** `2026-08-24T18:05:02` → **H2_SESSION_ARTIFACT** (session GLOBEX, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 3/7 audits GREEN · validators: 103/104 pass (KNOWN_FLAKY excluded: 1) · for `2026-08-24`
    - ⚠️ `heartbeat-tick-audit` **YELLOW** — 381 live ticks, 1 MISALIGNED-CRITICAL (0.3%) [HOLD-only — no trading impact]
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=141)
- **twin** last journal row `2026-08-25T16:40:38.043391+00:00` · 1988 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-08-25\|2026-08-25]] | **-220.55** | -60.15 | 0.00 | -60.15 | -100.25 | 0.00 | 6 |
| [[journal/2026-08-24\|2026-08-24]] | **-57.48** | -57.48 | 0.00 | 0.00 | 0.00 | 0.00 | 4 |
| [[journal/2026-08-23\|2026-08-23]] | **-0.12** | -0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-21\|2026-08-21]] | **-589.46** | -312.36 | -66.75 | -99.60 | -44.00 | -66.75 | 36 |
| [[journal/2026-08-20\|2026-08-20]] | **808.65** | 265.15 | 174.50 | 0.00 | 0.00 | 369.00 | 19 |
| [[journal/2026-08-19\|2026-08-19]] | **262.54** | -114.51 | 89.25 | 185.55 | 253.25 | -151.00 | 29 |
| [[journal/2026-08-18\|2026-08-18]] | **161.54** | 81.79 | 79.75 | 0.00 | 0.00 | 0.00 | 5 |
| [[journal/2026-08-17\|2026-08-17]] | **122.22** | -36.33 | 359.75 | 0.00 | 0.00 | -201.20 | 11 |
| [[journal/2026-08-14\|2026-08-14]] | **-1839.98** | -390.67 | -620.76 | -287.35 | -468.60 | -72.60 | 18 |
| [[journal/2026-08-13\|2026-08-13]] | **1744.05** | 443.49 | 248.25 | 456.56 | 401.25 | 194.50 | 38 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-08-25|2026-08-25]]
- [[journal/2026-08-24|2026-08-24]]
- [[journal/2026-08-23|2026-08-23]]
- [[journal/2026-08-21|2026-08-21]]
- [[journal/2026-08-20|2026-08-20]]
- [[journal/2026-08-19|2026-08-19]]
- [[journal/2026-08-18|2026-08-18]]
