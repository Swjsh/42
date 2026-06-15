# EOD Summary Orchestrator (Parallel)

> **Multi-Agent Gamma 2.0 — Big Win #4.** Replaces the monolithic eod-summary.md with an
> orchestrator that dispatches independent EOD steps to parallel sub-agents, then synthesizes.
>
> **Why:** EOD-summary's 8 steps include 6 that are independent (read immutable inputs, write to
> separate files). Running them serially wastes 4-6 minutes per night. Parallel = ~2-3 min wall.
>
> **Cost discipline (operating principle 3):** sub-agents share the parent budget. Orchestrator
> budget capped at $4. Each worker stays under ~$0.50 by design. Failure of one worker MUST NOT
> abort the others — log and continue.
>
> **Concurrency cap (operating principle 15):** MAX_PARALLEL_EOD_WORKERS=4. Even though we have
> 6+ workers, dispatch 4 at a time to respect rate limits.

---

## Step 0 — Pre-flight (sequential, fast)

Read these state files ONCE up front. Pass extracted values down to workers via prompt context.

- `automation/state/loop-state.json` (today's session_id, mode, score history)
- `automation/state/circuit-breaker.json` (start equity, current equity, day_trades)
- `automation/state/current-position.json` (any position still open?)
- `automation/state/today-bias.json` (predictions to grade)
- `journal/{today}.md` (existing skeleton + entries)
- `journal/trades.csv` (today's trades — read last 30 lines for context)
- `automation/state/decisions.jsonl` (today's tick decisions — read last 200 lines)

If `current-position.status != null`, ABORT this orchestrator with a journal NOTE — running EOD
analysis against an open position produces stale reflection. Wait for eod-flatten safety net.

---

## Step 1 — Dispatch parallel workers (the meat)

Use the Agent tool 4 times **in a single response** (parallel execution per agents.md doctrine).
Wait for all 4 to return before proceeding.

### Worker A: Metrics + Trade Grading
```
Agent(
  description="EOD metrics + trade grading",
  subagent_type="general-purpose",
  prompt="<contents of automation/prompts/eod-workers/01-metrics-and-grading.md
          PLUS today's date PLUS pre-flight summary>"
)
```
Returns JSON to: `automation/state/eod-workers/{date}-metrics.json`

### Worker B: Predictions + Rule Audit
```
Agent(
  description="EOD predictions + rule audit",
  subagent_type="general-purpose",
  prompt="<contents of automation/prompts/eod-workers/02-predictions-and-audit.md PLUS context>"
)
```
Returns JSON to: `automation/state/eod-workers/{date}-predictions.json`

### Worker C: Chart-Walk Suite (7b, 7e, 7g, 7h, 7i)
```
Agent(
  description="EOD chart-walks for losses + counterfactuals",
  subagent_type="general-purpose",
  prompt="<contents of automation/prompts/eod-workers/03-chart-walks.md PLUS context>"
)
```
Returns JSON to: `automation/state/eod-workers/{date}-chart-walks.json`
Heaviest worker (TradingView replays). Budget cap $1.

### Worker D: Shadow + Dark-Pool (8b + 8c)
```
Agent(
  description="EOD shadow scorecard + dark-pool aggregation",
  subagent_type="general-purpose",
  prompt="<contents of automation/prompts/eod-workers/04-shadow-and-darkpool.md PLUS context>"
)
```
Returns JSON to: `automation/state/eod-workers/{date}-shadow-darkpool.json`

---

## Step 2 — Wait + read worker outputs

After all 4 Agent calls return, read the 4 JSON files. If any worker file is missing or malformed:
- LOG the failure to `automation/state/logs/eod-summary-{date}.log` with WORKER_FAILED tag
- CONTINUE with whatever workers DID succeed (don't lose the night because one timed out)
- Set the missing section's data to `{"failed": true, "reason": "<what was missing>"}`

---

## Step 3 — Synthesize reflection (sequential, in orchestrator context)

Build the EOD reflection block in markdown. Sections (in order):
1. Header: `## End-of-Day Reflection — {date}`
2. **Metrics** (from Worker A): final equity, P&L $ + %, day-trades used, trade count, win rate
3. **Predictions** (from Worker B): graded vs today-bias.falsifiable_predictions
4. **Rule audit** (from Worker B): any breaks; if none, "Clean session ✓"
5. **Trade grades** (from Worker A): per-trade grade A/B/C/D/F + archetype + hold-quality
6. **Chart walks** (from Worker C): per-loss summary + counterfactual exit P&L
7. **Shadow scorecard** (from Worker D): if shadow-version.enabled, diff verdict
8. **Dark-pool levels** (from Worker D): new levels added to key-levels.json
9. **Tomorrow's notes**: bias inheritance, levels carry-over, kill-switch state

Append the synthesized block to `journal/{today}.md`.

---

## Step 4 — Update setup-performance + equity-curve (sequential)

These depend on Worker A's output:
- Append today's trades to `analysis/setup-performance.json` (per-setup rolling stats)
- Append today's final equity to `analysis/equity-curve.json`

---

## Step 5 — Hand off to Python data flywheel

After all writes, the wrapper PS1 invokes `backtest/tools/append_today.py`. Don't run it from
inside this prompt — the wrapper handles it.

---

## Step 6 — One-line emit + log

Output ONE LINE to stdout summarizing the night:

```
EOD {date} | trades={n} pnl=${pnl_dollars:+.0f} ({pnl_pct:+.1f}%) | grade_avg={X} | clean={true|false} | drift={low|med|high} | shadow={off|verdict} | wall={total_seconds}s
```

Append this exact line to `automation/state/logs/eod-summary-{date}.log` AND
`automation/state/dashboard-dialogue.json#eod_summary`.

---

## Failure modes (read these BEFORE running)

| Failure | What to do |
|---|---|
| Worker times out | Continue with `{"failed": true, "reason": "timeout"}`. Log it. |
| Worker writes invalid JSON | Continue with `{"failed": true, "reason": "invalid_json"}`. Log raw output to debug file. |
| All 4 workers fail | Log critical, write minimal fallback reflection ("EOD synthesis unavailable, manual review required"), exit code 1. |
| Position still open | ABORT before dispatching workers. EOD against open position is stale. |
| `automation/state/eod-workers/` missing | Create it. mkdir -p safe. |
| `journal/{today}.md` missing | Create it from template. Don't fail. |

---

## Output format (what THIS orchestrator returns)

ONE LINE to stdout (the summary above). All real outputs are file writes. Verbosity discipline
matches heartbeat.md — keep parent context light.
