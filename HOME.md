# 🎛️ Gamma — HOME

> Auto-generated `2026-09-13 10:15:20 Sunday EDT` · market **CLOSED** · regenerate: `python setup/scripts/obsidian_vault_sync.py`
> Nothing here is hand-maintained. If a number looks stale, the producer behind it is stale.

## Position & P&L

| Arm | Equity | Day | Holding |
|---|---:|---:|---|
| safe-2 | 5,311.59 | **-0.07** | flat |
| bold-2 | 5,483.19 | **+0.00** | flat |
| safe-3 | 5,779.65 | **+0.00** | flat |
| risky-1 | 5,991.38 | **+0.00** | flat |
| risky-3 | 4,282.65 | **+0.00** | flat |
| **BOOK** | | **-0.07** | |

## What Gamma learned today

*H1: risky-3 (challenger) vs risky-1 (control) -- `gate_override.anchor_class_denylist=["INTRADAY_SWING_"]`, clean window from `2026-09-14`. P&L source: `pnl-statement.json` per_day (T1 broker-truth round trips).*

> no sessions yet (first 2026-09-14)

**Tomorrow's change:** none (H1 clock running: 0/6 refused)

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

- **null study:** WHOLE-ENGINE-NULL 2026-09-11: FAIL -- NULL_DOMINATED. engine P1 $+2072.00, N_a p95 2545.5375000000004, N_c $-3674.00.
- **governing clock:** `2026-10-30`

- **Claude consumption 14d:** $1170.89 API-equiv/day · interactive 62.8% · scheduled 3.8% · subagents 33.4%

## Today's levels

*as of `2026-09-13T10:15:01-04:00`*

- **748.09** — SHELF_747.29_748.89_2026-09-13
- **761.32** — SHELF_760.52_762.12_2026-09-13
- **762.65** — MEMORY_SUP_85
- **763.6** — PRIOR_DAY_LOW_2026-09-13
- **765.46** — MEMORY_RES_213
- **766.2** — MEMORY_RES_89
- **766.38** — PRIOR_DAY_HIGH_2026-09-13

## What the engine sees

> No core decision rows for 2026-09-13 (weekend, holiday, or the engine is dark).
- bias: **no-trade**

## Other lanes

### 📈 Futures (MES · two lanes: fillsim = book, tastytrade SANDBOX = real fills)

- **lane health** `RED` (as of `2026-09-13 10:00:00`) — [YELLOW] broker_transport: 3/6 recent probe(s) show transport errors (rate 50%), 4 excluded as session-closed -- newest 2026-09-12T23:29:15 -> SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open); CME session_phase=WEEKEND (open=False, per futures_session/et_clock); broker-transport.jsonl: 253 row(s), 210 transport-error, 5 broker-rejected, 6 NOT-RETRIED-AMBIGUOUS (possible unconfirmed order); newest 2026-09-11T16:01:27 get_account_equity/transport_error
- **book lane** (fillsim) `HOLD` — last tick `2026-09-11T16:00:01` · session GLOBEX
- **broker lane** (tastytrade SANDBOX, REAL fills) `HOLD` — last tick `2026-09-11T16:00:01` · session GLOBEX
- **sim book** equity $1,595.86 (start $2,000.00) · day $-256.24 · 11 trades
- **feed** GREEN MES GREEN (10.1m)
- **edge #3** (MES→MNQ divergence) 16/20 round trips · mean $30.00 vs validated $71.46 · **PENDING_MORE_DATA**
- **SSR shadow** 23 round trips · forward clock running
- **last review** `2026-09-11` **GREEN** · coverage GREEN (79/78 ticks) · 0 rule break(s)
- **broker probe** `2026-09-12T23:29:15` → **SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)** (session WEEKEND, futures_bp 0.0)

### 🧪 Crypto (maintenance freeze — regression suite + mechanism twin)

- **gym** YELLOW · 3/7 audits GREEN · validators: 104/104 pass · for `2026-09-11`
    - ⚠️ `heartbeat-tick-audit` **YELLOW** — 333 live ticks, 1 MISALIGNED-CRITICAL (0.3%) [HOLD-only — no trading impact]
    - ⚠️ `pin-chain-verify` **YELLOW** — rule_version=v15.3, mismatches=1
    - ⚠️ `heartbeat-pulse-check` **NOT_APPLICABLE** — max gap 0.0min
    - ⚠️ `watcher-state-inspector` **YELLOW** — odf_state empty (may be correct if no drive-then-fade pattern) (obs_today=119)
- **twin** last journal row `2026-09-13T14:14:56.299725+00:00` · 47246 events (24/7 mechanism validator — its P&L is NEVER SPY evidence)

### 🎯 Tickers (non-SPY 0DTE, 3 paper arms, production scorer)

*Evidence class: paper fills on real quotes -- same scorer as SPY core.*

| Session | Arm | SoD equity | Realized P&L | Kill | Fills | Symbols |
|---|---|---:|---:|---|---:|---|
| 2026-09-04 | tickers-1 | $5,000.00 | -156.00 | no | 2 | AMZN |
| 2026-09-04 | tickers-2 | $5,000.00 | -93.00 | no | 2 | AVGO |
| 2026-09-04 | tickers-3 | $5,000.00 | -396.00 | no | 2 | QQQ |
| 2026-09-08 | tickers-1 | $4,843.72 | +45.00 | no | 2 | AAPL |
| 2026-09-08 | tickers-2 | $4,906.72 | +135.00 | no | 3 | TSLA |
| 2026-09-08 | tickers-3 | $4,603.72 | -72.00 | YES | 2 | QQQ |
| 2026-09-09 | tickers-1 | $4,888.43 | +0.00 | no | 0 | - |
| 2026-09-09 | tickers-2 | $5,186.42 | -312.00 | YES | 2 | TSLA |
| 2026-09-09 | tickers-3 | $4,531.44 | -75.00 | YES | 2 | GLD |
| 2026-09-10 | tickers-1 | $4,888.43 | +0.00 | no | 1 | NVDA |
| 2026-09-10 | tickers-2 | $4,874.13 | +0.00 | no | 0 | - |
| 2026-09-10 | tickers-3 | $4,456.16 | -198.00 | YES | 2 | QQQ |
| 2026-09-11 | tickers-1 | $4,876.15 | +22.00 | no | 6 | AAPL,AMZN |
| 2026-09-11 | tickers-2 | $4,874.13 | +66.00 | no | 2 | AVGO |
| 2026-09-11 | tickers-3 | $4,257.88 | +249.00 | no | 5 | QQQ |

- **tickers-1** cumulative since 09-04: -89.00 · 11 fills over 5 sessions
- **tickers-2** cumulative since 09-04: -204.00 · 9 fills over 5 sessions
- **tickers-3** cumulative since 09-04: -492.00 · 13 fills over 5 sessions
- **lane total** (3 arms, 5 sessions since 09-04): -785.00 · 33 fills

## This week

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | Legs |
|---|---:|---:|---:|---:|---:|---:|---:|
| [[journal/2026-09-11\|2026-09-11]] | **-621.92** | -219.67 | -75.25 | -181.00 | -146.00 | 0.00 | 27 |
| [[journal/2026-09-10\|2026-09-10]] | **-791.07** | -0.07 | -190.50 | -280.25 | -320.25 | 0.00 | 8 |
| [[journal/2026-09-08\|2026-09-08]] | **-116.40** | -21.15 | -95.25 | 0.00 | 0.00 | 0.00 | 4 |
| [[journal/2026-09-07\|2026-09-07]] | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-09-05\|2026-09-05]] | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| [[journal/2026-09-04\|2026-09-04]] | **337.60** | 212.85 | 124.75 | 0.00 | 0.00 | 0.00 | 4 |
| [[journal/2026-09-03\|2026-09-03]] | **730.34** | -312.66 | 128.00 | 604.00 | 311.00 | 0.00 | 37 |
| [[journal/2026-09-02\|2026-09-02]] | **-701.53** | -126.43 | -15.50 | -213.60 | -346.00 | 0.00 | 24 |
| [[journal/2026-09-01\|2026-09-01]] | **77.45** | 217.70 | -140.25 | 0.00 | 0.00 | 0.00 | 7 |

## Open loops

- [[automation/overnight/STATUS|STATUS]] — known-broken + the REVOKE surface
- [[automation/overnight/queue|queue]] — everything preregged with its forward clock
- [[analysis/deep-research/WEEK-ORDER-2026-08-10|THE WEEK ORDER]] — this week's armed state
- [[CLAUDE|CLAUDE.md]] — doctrine · [[markdown/README|markdown index]]

## Daily notes

- [[journal/2026-09-11|2026-09-11]]
- [[journal/2026-09-10|2026-09-10]]
- [[journal/2026-09-09|2026-09-09]]
- [[journal/2026-09-08|2026-09-08]]
- [[journal/2026-09-07|2026-09-07]]
- [[journal/2026-09-05|2026-09-05]]
- [[journal/2026-09-04|2026-09-04]]
