# 🎛️ Gamma — HOME

> Auto-generated `2026-09-01 23:28:41 Tuesday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,780.55 | **+217.70** | flat |
| bold-2 | 5,609.22 | **-140.25** | flat |
| safe-3 | 5,852.70 | **+0.00** | flat |
| risky-1 | 6,495.12 | **+0.00** | flat |
| risky-3 | 4,282.65 | **+0.00** | flat |
| **BOOK** | | **+77.45** | |

## The gate

- **overall verdict:** `RED` (as of `2026-09-01T22:17:13`)
- **criterion 5 (prod-shadow)** — arm `safe-3` · 0/20 days scored · CI-lo(2.5%) `n/a` · status `INSUFFICIENT_DAYS`
- **frozen-window BOOK** (ex-best-day) — PF `n/a` · CI-lo(2.5%) `n/a`

| Arm | $/day needed by `2026-10-30` | already clears |
|---|---:|---|
| safe-3 | 59.42 | False |
| safe-2 | 65.91 | False |
| risky-1 | 52.45 | False |
| bold-2 | 57.18 | False |

- **null study:** WHOLE-ENGINE-NULL 2026-09-01: WITHHELD (harness unreliable -- V9 sign agreement 79.3% < 85%). Mechanical sub-checks read PASS on the raw numbers (engine P1 $+3562.00, N_a p95 2545.5375000000004, N_c $-4676.40) but describe the walker, not the engine, until the walker is fixed.
- **governing clock:** `2026-10-30`

## Today's levels

*as of `2026-09-01T23:28:37-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **744.98** — SHELF_744.18_745.78_2026-09-01
- **748.09** — SHELF_747.29_748.89_2026-09-01
- **750.82** — SHELF_750.02_751.62_2026-09-01
- **759.48** — INTRADAY_RTH_LOW_2026-09-01
- **760.58** — INTRADAY_SWING_LOW_2026-09-01
- **761.32** — SHELF_760.52_762.12_2026-09-01
- **761.45** — INTRADAY_SWING_HIGH_2026-09-01
- **763.16** — MEMORY_RES_98
- **764.3** — MEMORY_RES_130
- **764.67** — INTRADAY_RTH_HIGH_2026-09-01
- **765.12** — MEMORY_RES_192
- **767.26** — PRIOR_DAY_CLOSE_2026-09-01
- **767.58** — SHELF_766.78_768.38_2026-09-01
- **767.84** — INTRADAY_PMH_2026-09-01
- **768.0** — PRIOR_DAY_HIGH_2026-09-01
- **769.36** — SHELF_768.56_770.16_2026-09-01
- **772.62** — SHELF_771.82_773.42_2026-09-01
- **774.71** — SHELF_773.91_775.51_2026-09-01

## What the engine sees

- **772 ticks** today — `HOLD` 742 · `SKIP_STALE_TRIGGER` 12 · `NOT_FLAT` 8 · `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` 5 · `PLACED` 3 · `SKIP_MIN_PREMIUM_FLOOR` 2
- last tick `2026-09-01T15:55:05` — spy **761.26** · ribbon **BEAR** · vix 16.41 · bull **8** / bear **7**
- bull triggers `[]` · blocked by `[5, 11]`
- bias: **bearish**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **lane health** `RED` (as of `2026-09-01 18:00:02`) — [RED] fills_recency: SIGNALS SEEN BUT ENTRY REFUSED repeatedly -- last ENTER 2026-09-01 (0 session(s) since in the read window); 15 ENTER_REFUSED row(s) across 4/5 recent session(s) ['2026-08-26', '2026-08-27', '2026-08-28', '2026-08-31', '2026-09-01'] (the engine is seeing setups and failing to fill them -- not the same thing as a quiet no-signal day, which is never a failure)
- **book lane** (fillsim) `HOLD` — last tick `2026-09-01T16:00:01` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `FLATTEN` — last tick `2026-09-01T16:00:01` · session GLOBEX
- **sim book** equity $1,595.86 (start $2,000.00) · day $-256.24 · 11 trades
- **feed** GREEN MES GREEN (10.1m)
- **edge #3** (MES→MNQ divergence) 14/20 round trips · mean $39.25 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 13 round trips · forward clock running
- **last review** `2026-09-01` **RULE_BREAK** · coverage GREEN (80/78 ticks) · 1 rule break(s)
- **broker probe** `2026-08-31T21:31:57` → **H2_SESSION_ARTIFACT** (session GLOBEX, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 3/7 audits GREEN · validators: 104/104 pass · for `2026-09-01`
    - ⚠️ `heartbeat-tick-audit` **YELLOW** — 381 live ticks, 1 MISALIGNED-CRITICAL (0.3%) [HOLD-only — no trading impact]
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=93)
- **twin** last journal row `2026-09-02T03:28:38.101437+00:00` · 2415 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-09-01\|2026-09-01]] | **77.45** | 217.70 | -140.25 | 0.00 | 0.00 | 0.00 | 7 |
| [[journal/2026-08-31\|2026-08-31]] | **-0.19** | -0.19 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-28\|2026-08-28]] | **1301.00** | 256.64 | 293.50 | 562.85 | 649.75 | -461.74 | 26 |
| [[journal/2026-08-27\|2026-08-27]] | **1893.79** | 321.58 | 213.25 | 587.70 | 827.51 | -56.25 | 29 |
| [[journal/2026-08-26\|2026-08-26]] | **38.85** | 0.00 | 0.00 | 38.85 | 0.00 | 0.00 | 2 |
| [[journal/2026-08-25\|2026-08-25]] | **-220.55** | -60.15 | 0.00 | -60.15 | -100.25 | 0.00 | 6 |
| [[journal/2026-08-24\|2026-08-24]] | **-57.48** | -57.48 | 0.00 | 0.00 | 0.00 | 0.00 | 4 |
| [[journal/2026-08-23\|2026-08-23]] | **-0.12** | -0.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-21\|2026-08-21]] | **-589.46** | -312.36 | -66.75 | -99.60 | -44.00 | -66.75 | 36 |
| [[journal/2026-08-20\|2026-08-20]] | **808.65** | 265.15 | 174.50 | 0.00 | 0.00 | 369.00 | 19 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-09-01|2026-09-01]]
- [[journal/2026-08-31|2026-08-31]]
- [[journal/2026-08-28|2026-08-28]]
- [[journal/2026-08-27|2026-08-27]]
- [[journal/2026-08-26|2026-08-26]]
- [[journal/2026-08-25|2026-08-25]]
- [[journal/2026-08-24|2026-08-24]]
