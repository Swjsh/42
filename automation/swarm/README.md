# Gamma Swarm — Pre-Market Hypothesis Engine

> 6-agent swarm that fires premarket and produces a structured, falsifiable consensus
> hypothesis for the day's 0DTE SPY trade. Advisory-only per OP-28 — does not block
> or trigger trades.

---

## Files

```
automation/swarm/
├── runner.py                 # Live orchestrator (06:00 ET weekday fires)
├── swarm_grader.py           # Per-day grader called by EOD pipeline
├── prompts/                  # 7 agent prompts (data_fetcher + 4 specialists + validator + synthesis)
├── state/                    # Live state (raw_data.json + 6 agent outputs + swarm_output.json)
└── replay/                   # OFFLINE REPLAY MODE (2026-05-16) — see Replay section
    ├── build_raw_data.py        # Synthesizes raw_data.json from spy_5m + vix + sector ETF caches
    ├── build_key_levels.py      # Synthesizes key-levels.json algorithmically (no journal)
    ├── build_macro_calendar.py  # Filters macro-calendar.json to target week
    ├── runner_replay.py         # Skips Stage 1; reuses prompts 2-4 unchanged
    ├── grader_replay.py         # Grades replay vs actual (direction + battle + predictions)
    └── cache/                   # yfinance sector ETF daily cache (auto-fetched on first run)
```

---

## Stages (live mode)

```
06:00 ET → Stage 1 data_fetcher (sequential, MCP-bound, ~$0.50)
         ↓ writes raw_data.json
         → Stage 2 specialists (Pool(4), MCP-free): technical + macro + level_thesis + internals
         ↓ each writes {agent}_output.json
         → Stage 3 validator (sequential, MCP-free)
         ↓ reads stage-2, argues contrarian, writes validator_output.json
         → Stage 4 synthesis CIO (sequential, sonnet, MCP-free)
         ↓ reads all 5, writes swarm_output.json
06:10 ET ← consumable by premarket.md Step 1c
```

**Total cost:** ~$0.065 per fire.
**Total runtime:** 5-7 minutes.

---

## Replay mode (new — 2026-05-16)

The 4 specialists + validator + synthesis are **already MCP-free by design**.
Only data_fetcher touches TradingView/Alpaca MCP. That makes the system trivially
replay-able offline:

```
build_raw_data.py     → spy_5m CSV + vix_5m CSV + yfinance sectors → raw_data.json
build_key_levels.py   → spy_5m CSV (prior OHLC + pivots + premarket H/L) → key-levels.json
build_macro_calendar.py → filter macro-calendar.json to date's week → macro-calendar.json
runner_replay.py      → injects path overlay header, runs stages 2-4 unmodified
grader_replay.py      → grades vs spy_5m RTH bars (direction + battle level + predictions)
```

**Critical design:** production state at `automation/state/*` is **never touched**.
All replay overlay files live in `analysis/swarm-benchmark/replay-{date}-{asof}/`.
Agents read from the overlay via a runtime header injection.

### Replay a single day

```powershell
python automation/swarm/replay/runner_replay.py --date 2026-05-14 --as-of 06:00
python automation/swarm/replay/grader_replay.py --date 2026-05-14 --as-of 06:00
```

Result lands in `analysis/swarm-benchmark/replay-2026-05-14-0600/`:
- `raw_data.json`, `key-levels.json`, `macro-calendar.json` — synthetic inputs
- `technical_output.json`, `macro_output.json`, `level_thesis_output.json`, `internals_output.json` — specialists
- `validator_output.json` — devil's advocate
- `swarm_output.json` — final CIO synthesis with consensus_bias + 3 falsifiable predictions
- `runner_summary.json` — timings, agent successes
- `grade.json` — vs actual outcome

### Grade all replays

```powershell
python automation/swarm/replay/grader_replay.py --grade-all
```

Rebuilds `analysis/swarm-benchmark/aggregate.json` with overall accuracy,
battle-level test rate, confidence calibration.

---

## What each agent does

| Agent | Weight | Reads | Decides |
|---|---|---|---|
| data_fetcher | — | TV + Alpaca MCP | raw_data.json (shared truth) |
| technical | 0.35 | raw_data + key-levels | Ribbon verdict, bar structure, momentum |
| macro | 0.30 | raw_data + macro-calendar | VIX regime, event risk, gap context |
| level_thesis | 0.25 | raw_data + key-levels | Battle level, scenario map |
| internals | 0.10 | raw_data | Sector rotation, breadth |
| validator | — | 4 specialist outputs | Devil's advocate, invalidation scenarios |
| synthesis | — | 5 outputs + key-levels | Final consensus, confidence, 3 predictions |

Consensus weights (specialists only, validator is contrarian):
- `weighted_score = sum(weight_i * (1 if agent_i_voted_consensus else 0))`
- Consensus strength: strong ≥ 0.65, moderate 0.45-0.64, weak 0.25-0.44, split < 0.25
- Confidence (0-100) = weighted_score × 100, adjusted for: 4/4 agreement (+10), 3/4 (+5),
  high event_risk (-15), validator robustness (+5/-10). Capped [10, 95].

---

## Output schema (`swarm_output.json`)

See `prompts/synthesis_agent.md` for the canonical schema. Key fields:

| Field | Type | Description |
|---|---|---|
| `consensus_bias` | enum | `bullish` / `bearish` / `no_trade` |
| `consensus_strength` | enum | `strong` / `moderate` / `weak` / `split` |
| `swarm_confidence` | int 10-95 | Calibrated confidence |
| `vote_map` | dict | Which agents voted which way |
| `weighted_scores` | dict | Weighted score per direction |
| `dissent_flag` | dict | Active dissenters + reason |
| `battle_level` | dict | The day's critical level (price, tier, role) |
| `level_priority` | list | Top 5 in-play levels ranked |
| `scenario_map` | dict | Primary + secondary + invalidation scenarios |
| `swarm_predictions` | list[3] | 3 falsifiable predictions (level + macro + technical) |
| `synthesis_narrative` | str | 2-3 sentence CIO commentary |

---

## When does the swarm fire?

| Mode | Trigger | Output destination | Purpose |
|---|---|---|---|
| **Live premarket** | `Gamma_SwarmPremarket` task, 06:00 ET weekday | `automation/swarm/state/swarm_output.json` | Premarket Step 1c reads as advisory context |
| **Replay** | Manual `runner_replay.py` invocation | `analysis/swarm-benchmark/replay-{date}-{asof}/` | Historical benchmarking, weekend review |

---

## Operating principles

- **OP-28** — Swarm is advisory-only. Doesn't block trades. Doesn't move stops.
- **OP-11 (Karpathy method)** — Replay results feed prompt evolution after N ≥ 20 days.
- **OP-20 (non-theatre validation)** — every benchmark claim must bundle account-size
  assumption + sample-bias disclosure + OOS evidence + concentration disclosure.

---

## Cost discipline

- **Live fires:** ~$0.065 × 21 trading days/month ≈ $1.40/mo
- **Weekend review (Saturday):** ~$0.065 × 5 days replayed ≈ $0.33/week
- **90-day backfill:** ~$6 one-shot (overnight)
- **Ablation/weight sweep:** $5-15 (only run on demand)

**Total recurring:** ~$3/mo. Well within OP-3 budget gate.

---

## Foot-guns

- **Don't write to `automation/state/*` from replay mode.** Always use `analysis/swarm-benchmark/replay-*/`.
- **Synthesis agent writes to `swarm_output.json`, NOT `synthesis_output.json`.** Special-cased in `_replay_header()`.
- **Ribbon math is fingerprinted at 13/20/48 EMA per `backtest/lib/ribbon.py`.** Don't change without re-running the 16-month benchmark.
- **5m CSV bars include the in-progress bar.** Always filter with `timestamp_et < as_of` BEFORE indicator math.
- **yfinance sector cache is daily-only.** Don't depend on intraday sector data — it's not in the cache.
- **NEVER spawn `claude --print` for stages 2-4 without `--strict-mcp-config --mcp-config <empty-mcp.json>`** + **`creationflags=0x08000000` (CREATE_NO_WINDOW) on `subprocess.run`.** Without both, each agent call orphans an alpaca-mcp-server.exe with a visible console window. Already correct in `runner.py` + `runner_replay.py`; preserve when editing. See CLAUDE.md OP 27 subprocess discipline + LESSONS-LEARNED L41.

---

## See also

- [`docs/SWARM-REPLAY-PLAYBOOK.md`](../../docs/SWARM-REPLAY-PLAYBOOK.md) — how to replay any historical day
- [`docs/SWARM-BENCHMARK-WEEK-1.md`](../../docs/SWARM-BENCHMARK-WEEK-1.md) — current scorecard
- [`CLAUDE.md` OP-28](../../CLAUDE.md) — doctrine governing swarm role + evolution gates
