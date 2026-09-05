# 🎛️ Gamma — HOME

> Auto-generated `2026-09-05 00:56:03 Saturday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,553.35 | **+212.85** | flat |
| bold-2 | 5,845.16 | **+124.75** | flat |
| safe-3 | 6,241.85 | **+0.00** | flat |
| risky-1 | 6,458.59 | **+0.00** | flat |
| risky-3 | 4,282.65 | **+0.00** | flat |
| **BOOK** | | **+337.60** | |

## The gate

- **overall verdict:** `RED` (as of `2026-09-03T14:43:34`)
- **criterion 5 (prod-shadow)** — arm `safe-3` · 2/20 days scored · CI-lo(2.5%) `0.0` · status `INSUFFICIENT_DAYS`
- **frozen-window BOOK** (ex-best-day) — PF `0.112` · CI-lo(2.5%) `0.0`

| Arm | $/day needed by `2026-10-30` | already clears |
|---|---:|---|
| safe-3 | 60.67 | False |
| safe-2 | 83.64 | False |
| risky-1 | 58.08 | False |
| bold-2 | 57.13 | False |

- **null study:** WHOLE-ENGINE-NULL 2026-09-04: PASS -- engine P1 $+3597.00 beats N_a p95 (2545.5375000000004), N_b call, P3, and N_c <= 0.
- **governing clock:** `2026-10-30`

## Today's levels

*as of `2026-09-05T00:53:36-04:00`*

- **731.22** — PRIOR_CLOSE_2026-06-26
- **734.52** — PML_2026-06-29
- **761.32** — SHELF_760.52_762.12_2026-09-05
- **765.47** — MEMORY_SUP_259
- **766.33** — MEMORY_SUP_99
- **767.58** — SHELF_766.78_768.38_2026-09-05
- **769.0** — PRIOR_DAY_LOW_2026-09-05
- **769.36** — SHELF_768.56_770.16_2026-09-05
- **769.76** — MEMORY_SUP_155
- **770.47** — MEMORY_RES_81
- **770.99** — SHELF_770.19_771.79_2026-09-05
- **771.21** — MEMORY_RES_67
- **772.62** — SHELF_771.82_773.42_2026-09-05
- **772.87** — PRIOR_DAY_HIGH_2026-09-05
- **774.71** — SHELF_773.91_775.51_2026-09-05

## What the engine sees

> No core decision rows for 2026-09-05 (weekend, holiday, or the engine is dark).
- bias: **bullish**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **lane health** `RED` (as of `2026-09-05 00:30:01`) — [YELLOW] fills_recency: isolated ENTER_REFUSED, not yet a pattern -- last ENTER 2026-09-01 (3 session(s) since in the read window); 1 ENTER_REFUSED row(s) across 1/5 recent session(s) ['2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04']
- **book lane** (fillsim) `HOLD` — last tick `2026-09-04T16:00:01` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `HOLD` — last tick `2026-09-04T16:00:01` · session GLOBEX
- **sim book** equity $1,595.86 (start $2,000.00) · day $-256.24 · 11 trades
- **feed** GREEN MES GREEN (10.2m)
- **edge #3** (MES→MNQ divergence) 15/20 round trips · mean $38.15 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 20 round trips · forward clock running
- **last review** `2026-09-04` **YELLOW** · coverage YELLOW (69/78 ticks) · 0 rule break(s)
- **broker probe** `2026-08-31T21:31:57` → **H2_SESSION_ARTIFACT** (session GLOBEX, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 4/7 audits GREEN · validators: 104/104 pass · for `2026-09-04`
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=78)
- **twin** last journal row `2026-09-05T04:18:38.386214+00:00` · 2691 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-09-05\|2026-09-05]] | **337.60** | 212.85 | 124.75 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-09-04\|2026-09-04]] | **337.60** | 212.85 | 124.75 | 0.00 | 0.00 | 0.00 | 4 |
| [[journal/2026-09-03\|2026-09-03]] | **730.34** | -312.66 | 128.00 | 604.00 | 311.00 | 0.00 | 37 |
| [[journal/2026-09-02\|2026-09-02]] | **-701.53** | -126.43 | -15.50 | -213.60 | -346.00 | 0.00 | 24 |
| [[journal/2026-09-01\|2026-09-01]] | **77.45** | 217.70 | -140.25 | 0.00 | 0.00 | 0.00 | 7 |
| [[journal/2026-08-31\|2026-08-31]] | **-0.19** | -0.19 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-08-28\|2026-08-28]] | **1301.00** | 256.64 | 293.50 | 562.85 | 649.75 | -461.74 | 26 |
| [[journal/2026-08-27\|2026-08-27]] | **1893.79** | 321.58 | 213.25 | 587.70 | 827.51 | -56.25 | 29 |
| [[journal/2026-08-26\|2026-08-26]] | **38.85** | 0.00 | 0.00 | 38.85 | 0.00 | 0.00 | 2 |
| [[journal/2026-08-25\|2026-08-25]] | **-220.55** | -60.15 | 0.00 | -60.15 | -100.25 | 0.00 | 6 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-09-05|2026-09-05]]
- [[journal/2026-09-04|2026-09-04]]
- [[journal/2026-09-03|2026-09-03]]
- [[journal/2026-09-02|2026-09-02]]
- [[journal/2026-09-01|2026-09-01]]
- [[journal/2026-08-31|2026-08-31]]
- [[journal/2026-08-28|2026-08-28]]
