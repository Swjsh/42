# Swarm Replay Playbook

> How to replay the Gamma Swarm against any historical day (2025-01-02 → 2026-05-15).
> Shipped 2026-05-16 — see [`SWARM-BENCHMARK-WEEK-1.md`](SWARM-BENCHMARK-WEEK-1.md) for first-week results.

---

## TL;DR

```powershell
# 1. Replay (builds overlay + runs stages 2-4)
python automation/swarm/replay/runner_replay.py --date 2026-05-14 --as-of 06:00

# 2. Grade vs actual
python automation/swarm/replay/grader_replay.py --date 2026-05-14 --as-of 06:00

# 3. Re-aggregate scorecard across all replays
python automation/swarm/replay/grader_replay.py --grade-all
```

Output lands in `analysis/swarm-benchmark/replay-{date}-{asof}/`.

---

## What replay mode is

Replay mode **runs the live swarm's 6 downstream agents** (technical, macro, level_thesis, internals, validator, synthesis) against **synthetic historical inputs** instead of live MCP fetches.

The only stage that gets replaced is the live `data_fetcher.md` (the MCP-bound stage). Three new Python builders synthesize the inputs the agents need from cached CSVs:

| Live stage | Replay replacement |
|---|---|
| `data_fetcher.md` (TV + Alpaca MCP) | `build_raw_data.py` (spy_5m CSV + vix_5m CSV + yfinance sectors) |
| `automation/state/key-levels.json` (J-curated + heartbeat-derived) | `build_key_levels.py` (algorithmic: prior OHLC + pivots + PMH/PML) |
| `automation/state/macro-calendar.json` (J-maintained) | `build_macro_calendar.py` (filtered to target week) |

The 4 specialists + validator + synthesis run against the synthetic overlay via runtime header injection — **zero changes to the agent prompts.**

---

## Architecture

```
runner_replay.py
├── Stage 0: build_overlay()
│   ├── build_raw_data.py    → analysis/swarm-benchmark/replay-{date}-{asof}/raw_data.json
│   ├── build_key_levels.py  → analysis/swarm-benchmark/replay-{date}-{asof}/key-levels.json
│   └── build_macro_calendar.py → analysis/swarm-benchmark/replay-{date}-{asof}/macro-calendar.json
│
├── Stage 2: Pool(4) — parallel specialists
│   ├── technical_agent  (haiku, 0.15 budget, 120s timeout)
│   ├── macro_agent      (haiku, 0.15 budget, 120s timeout)
│   ├── level_thesis     (haiku, 0.10 budget, 90s timeout)
│   └── internals        (haiku, 0.10 budget, 90s timeout)
│   ↓ retry once if no output
│
├── Stage 3: validator     (haiku, 0.15 budget, 120s timeout, sequential)
│
└── Stage 4: synthesis CIO (sonnet, 0.65 budget, 240s timeout, sequential)
    ↓ writes swarm_output.json
```

Each agent gets a runtime header injected before its prompt that **redirects all file paths** to the replay overlay directory. Production state at `automation/state/*` is never touched.

---

## Output files

After a successful replay:

```
analysis/swarm-benchmark/replay-2026-05-14-0600/
├── raw_data.json              # synthetic input (data_fetcher replacement)
├── key-levels.json            # synthetic input
├── macro-calendar.json        # synthetic input
├── technical_output.json      # stage 2 specialist
├── macro_output.json          # stage 2 specialist
├── level_thesis_output.json   # stage 2 specialist
├── internals_output.json      # stage 2 specialist
├── validator_output.json      # stage 3
├── swarm_output.json          # stage 4 — the final consensus
├── runner_summary.json        # timings, agent successes, retries
└── grade.json                 # (after grader runs) vs actual outcome
```

---

## Grading

`grader_replay.py` evaluates each replay across 3 dimensions:

### 1. Direction (auto-graded)
```
consensus_bias vs actual day's close direction
  - actual_bias: bullish if (close - open > $1), bearish if (close - open < -$1), else no_trade
  - grades: CORRECT | WRONG | ABSTAIN | ABSTAIN_ACTUAL
```

### 2. Battle level (auto-graded)
```
Did SPY's price ever touch within $0.25 of the predicted battle_level during RTH?
  - grades: HELD (support held / resistance held) | BROKE (level broken in expected direction)
           | TESTED_MIXED (touched but ambiguous outcome) | UNTESTED (price never reached)
```

### 3. Predictions (partial auto-grade)
```
For each of the 3 falsifiable predictions:
  - LEVEL prediction: parses target price from claim, checks if touched in time window
                      → TOUCHED_IN_WINDOW | MISSED
  - MACRO + TECHNICAL predictions: narrative — flagged REVIEW_NEEDED
                                   (needs LLM grader or manual review)
```

---

## Common workflows

### Replay yesterday and grade
```powershell
python automation/swarm/replay/runner_replay.py --date 2026-05-15 --as-of 06:00
python automation/swarm/replay/grader_replay.py --date 2026-05-15 --as-of 06:00
```

### Replay an entire week
```powershell
foreach ($d in '2026-05-11','2026-05-12','2026-05-13','2026-05-14','2026-05-15') {
    python automation/swarm/replay/runner_replay.py --date $d --as-of 06:00
}
python automation/swarm/replay/grader_replay.py --grade-all
```

### Reuse cached overlay (skip Stage 1)
```powershell
python automation/swarm/replay/runner_replay.py --date 2026-05-14 --as-of 06:00 --skip-build
```

Useful when iterating on an agent prompt change — rebuild inputs once, re-run agents many times.

### Replay at a different as-of time
```powershell
# Premarket replay (typical) — 06:00 ET, before any data_fetcher would fire
python automation/swarm/replay/runner_replay.py --date 2026-05-14 --as-of 06:00

# Live-tick replay — 09:35 ET, after the open absorbs CPI
python automation/swarm/replay/runner_replay.py --date 2026-05-14 --as-of 09:35
```

---

## Cost & runtime

| Item | Cost | Time |
|---|---|---|
| Single replay | ~$0.07 | 3-5 min |
| Full week (5 days) | ~$0.35 | 15-25 min |
| 30-day backfill | ~$2 | 1.5-2 hours |
| 90-day backfill | ~$6 | 4.5-6 hours |
| 16-month backfill | ~$22 | 16-24 hours |

All costs assume haiku for specialists/validator, sonnet for synthesis.

---

## Data fidelity caveats

The CSV-driven replay is **mostly faithful** to what live data_fetcher would pull, with these differences:

| Gap | Cause | Impact |
|---|---|---|
| Ribbon math uses 13/20/48 EMA (per `backtest/lib/ribbon.py`) | Fingerprinted from live chart | exact parity (~0.05¢) |
| PMH/PML may include thin overnight spikes | CSV captures all bars; journal-curated values filter to clean refs | minor (e.g., 5/15 PMH 748.17 CSV vs 744.35 journal) |
| Sector data is daily-only | yfinance cache | OK — agents only use prior-session direction |
| VIX is from cached 5m bars | Matches what TV would show | exact parity |
| Macro events filtered to target week | Same source file as live | exact parity |
| Key levels algorithmic-only | Live includes J-curated Carry levels | known gap — see Finding 4 in Week-1 benchmark |

The key-levels gap is the largest fidelity difference. Live swarm has J's hand-curated Carry levels (e.g., 5/15 738.10 ★★★ 5-touch hold) that the algorithmic builder cannot reproduce. Despite this, replay-mode swarm hit 80% direction accuracy on Week 1 — suggesting the agents are robust to lighter level curation.

---

## Foot-guns

- **Don't write to `automation/state/*` from replay** — always lands in `analysis/swarm-benchmark/replay-*/`. The header injection enforces this.
- **Synthesis writes to `swarm_output.json`, not `synthesis_output.json`** — special-cased in `_replay_header()`. Don't rename.
- **5m CSV bars include the in-progress bar** — `_filter_to_as_of()` strips bars with `timestamp_et >= as_of`. Never bypass.
- **First-bar volume can spike thin** — 04:00 ET premarket bars often have wide ranges on low volume. The agents see the raw data; if you want clean PMH/PML, filter to volume > 1000 in `build_key_levels.py`.
- **yfinance fetch can fail offline** — sector cache falls back to last-good if available, else `sectors: null`. Agents handle gracefully.

---

## What's next (queued)

- **Phase 3 (overnight wake fires):** 90-day backfill → populates `analysis/swarm-benchmark/aggregate.json` with 60+ days
- **Phase 4 (after backfill):** confidence calibration fix + agent weight sweep
- **Phase 5 (post-backfill):** weekend Saturday review task to feed weekly-review pipeline
- **Phase 6 (long-term):** plumb battle_level + dissent_active into `today-bias.json` as awareness fields

See [`SWARM-BENCHMARK-WEEK-1.md`](SWARM-BENCHMARK-WEEK-1.md) — Findings section — for the rationale on each.
