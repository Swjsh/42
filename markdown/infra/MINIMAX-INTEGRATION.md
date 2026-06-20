# MiniMax via OpenRouter — Integration Guide

> **Ratified:** 2026-05-20 by J. **Status:** shipped (foundation + swarm Stages 2-3).
> **Doctrine:** OP-25 engine-benefit autonomy (advisory-only infrastructure).
>
> **2026-05-21 extension:** OpenRouter FREE TIER added (Nemotron 3 Super 120B,
> DeepSeek V4 Flash, MiniMax M2.5:free). New tool `setup/scripts/chef_nemotron.py`
> runs the Chef R&D persona entirely on free models with a 4-tier fallback ladder.
> Per CLAUDE.md OP-30 (effort + concurrency + free-tier-first routing).

## Free tier ladder (ratified 2026-05-21)

For autonomous text-analytical work (Chef R&D, lesson authoring, EOD analyst /
manager / summary, wake fires, weekly review pattern-mining), the OpenRouter
free tier is the DEFAULT route. Models are tried in this order; on 429 or
auth-failure the next tier is attempted:

| Tier | Model ID | Context | Cost | Notes |
|---:|---|---:|---:|---|
| 0 | `nvidia/nemotron-3-super-120b-a12b:free` | 1M | $0 | 120B MoE / 12B active, reasoning-tuned, agentic primary |
| 1 | `deepseek/deepseek-v4-flash:free` | 1M | $0 | Coding-focused, faster than Nemotron |
| 2 | `minimax/minimax-m2.5:free` | 204K | $0 | Same family as paid M2.5, sometimes 429s earlier |
| 3 | `minimax/minimax-m2.5` (paid) | 204K | ~$0.003/call | Last resort if all free tiers exhausted |

Free tier is RATE-LIMITED (not $-capped). Daily $-cap logic in `run_minimax.py`
is skipped for `:free` models via `_is_free_model()`. Telemetry still records
input_tokens / output_tokens / elapsed_s so we can audit rate-limit headroom.

## Why this exists

J's $100/mo Claude Max 5x plan was getting rate-limit-throttled during
interactive testing because autonomous fires (swarm, EOD, wake fires)
shared the same quota pool. **OpenRouter / MiniMax M2** is ~5-20x cheaper
per token than Sonnet/Haiku, runs on a separate API account, and
benchmarks well on the agentic/coding work patterns we delegate.

| Surface | Provider |
|---|---|
| Live trading (heartbeat, Pilot, orders) | **Claude — hard rule, never migrate** |
| Swarm Stage 1 (data_fetcher — needs MCP) | Claude (Haiku) |
| Swarm Stages 2-3 (technical, macro, level_thesis, internals, validator) | **MiniMax M2** ← shipped |
| Swarm Stage 4 (synthesis CIO) | Claude (Sonnet) |
| Personas (Scout, Analyst, Manager, Treasurer) | Claude — persona-bound via Agent SDK |
| EOD pipeline (`backtest/autoresearch/eod_deep/`) | Pure Python — no LLM in loop |
| Overnight wake fires | **PAUSED by J 2026-05-20** — see Wake-Fire Revival section |
| Chart Vision Observer | Claude — needs vision, M2 is text-only |

---

## Architecture

```
                ┌─────────────────────────────────────┐
                │   automation/swarm/runner.py        │
                │   dispatch_agent(args) on cfg.provider │
                └────┬───────────────────────┬────────┘
                     │                       │
              provider=claude         provider=minimax
                     │                       │
                     ▼                       ▼
              run_claude_agent       run_minimax_agent
              (subprocess to              (in-process,
               claude --print)             OpenAI SDK → OpenRouter)
                     │                       │
                     ▼                       ▼
              writes {agent}_output.json  same {agent}_output.json
```

Both providers write the **same output JSON files** — synthesis (CIO) is
agnostic to which engine produced each specialist output.

---

## Files

| File | Role |
|---|---|
| `setup/scripts/run_minimax.py` | Generic MiniMax client. Library + CLI. Telemetry + $5/day spend cap. |
| `automation/swarm/minimax_dispatcher.py` | Swarm-specific wrapper: input-file inlining, prompt assembly, JSON extraction, output file write. |
| `automation/swarm/runner.py` | Updated: `AGENT_CONFIG[*].provider` field + `dispatch_agent()`. Pool.map uses the dispatcher. |
| `automation/swarm/test_minimax_smoke.py` | Stages 2-3 smoke test (skips Claude-bound stages 1 + 4). |
| `automation/state/.openrouter.key` | API key (gitignored). |
| `automation/state/minimax-calls.jsonl` | Per-call telemetry: ts, task_id, model, tokens, cost, ok, error. |
| `markdown/infra/MINIMAX-INTEGRATION.md` | This file. |

---

## Setup (one-time)

1. **OpenRouter account:** signed up at openrouter.ai, loaded credits.
2. **API key:** paste single-line into `automation/state/.openrouter.key`
   (key must start with `sk-or-`). Already gitignored.
3. **Python SDK:** `openai` (>=2.x) already in the venv. No new deps.
4. **Smoke test:**
   ```bash
   python setup/scripts/run_minimax.py --check-status     # cap state
   python setup/scripts/run_minimax.py --prompt "ping"    # 1 API call
   python automation/swarm/test_minimax_smoke.py          # full Pool test
   ```

---

## Cost discipline

Per CLAUDE.md OP-3 ($100/mo budget gate) + OP-20 (telemetry):

- **Specialists + EOD fallback:** `minimax/minimax-m2.5` ($0.15/M input, $1.15/M output).
  Confirmed production model as of 2026-05-21 (38 calls, 100% ok over 5+ swarm fires). Cheaper
  than m2 and quality-confirmed. Used by all 12 specialists + EOD fallback agents.
- **Synthesis agent:** `minimax/minimax-m2` ($0.255/M input, $1.00/M output). Pinned to m2
  (J-approved): synthesis reads all 12 specialist outputs (~8K context) — m2.5 timed out
  consistently at that context size; m2 completed in 21s. See `runner.py` AGENT_CONFIG.
- **Hard daily cap:** $5/day. Refuses calls past this; writes a BROKEN flag
  to `automation/overnight/STATUS.md`.
- **Soft alert:** $4/day appends a WARN to STATUS.md.
- **Per-call telemetry:** every call appended to `minimax-calls.jsonl`.

### Observed swarm cost (5/19 raw_data smoke)

| Agent | Input tokens | Output tokens | Cost USD | Elapsed |
|---|---|---|---|---|
| technical | 6,549 | 630 | $0.0023 | 11.7s |
| macro | 6,970 | 938 | $0.0027 | 13.9s |
| level_thesis | 6,832 | 1,511 | $0.0033 | 19.2s |
| internals | 1,539 | 705 | $0.0011 | 12.6s |
| validator | 3,470 | 1,274 | $0.0022 | 17.1s |
| **TOTAL** | **25,360** | **5,058** | **$0.0116** | **~37s (Pool)** |

Stage 2+3 cost per fire: **$0.012**. Monthly (21 fires): **~$0.25/mo**.
(Plus Claude time for stages 1+4 which is unchanged.)

### Estimated full migration savings (if/when wake fires move too)

Wake fires were ~$50/night × 30 = ~$1,500/mo Sonnet-equivalent. Same work
on MiniMax M2 (text-only, no MCP): ~$5-15/mo. Net OpenRouter spend with
wake fires + swarm Stages 2-3: ~$10-25/mo. Total all-in: ~$110-125/mo.

---

## Key design decisions

### 1. Input files are inlined into the prompt, not tool-fetched

MiniMax via OpenRouter chat-completions doesn't have native file-system
tools. Instead of building a tool harness, the dispatcher reads the
relevant input files (per `AGENT_INPUTS` map in `minimax_dispatcher.py`)
and inlines them as fenced JSON blocks in the user prompt. Each specialist
prompt was already designed to read a small, fixed set of state files
(2-4 files of ~1-3KB each) so inlining is cheap.

### 2. Output is JSON-only; the dispatcher writes the file

Agent prompts originally instructed agents to "Write
`{agent}_output.json`". MiniMax can't write files. The dispatcher appends
an `OUTPUT RULE (CRITICAL)` block that overrides: respond with **only the
raw JSON object**, no preamble/markdown/explanation. The dispatcher then
extracts, validates, and writes the file atomically.

The original prompts are **unchanged** — the OUTPUT RULE override is
appended at runtime by the dispatcher. This preserves backward compat for
the Claude path (Stage 1 + Stage 4 still use the original prompt
verbatim).

### 3. JSON extraction tolerates markdown fences

`_extract_json()` strips ` ```json ` fences if present, then attempts
parse. On failure it slices to the first `{` and last `}` and retries.
On total failure it persists the raw response to
`automation/swarm/state/{agent}_minimax_raw.txt` for forensic review.

### 4. No auto-fallback to Claude on MiniMax failure

If MiniMax fails for an agent, that agent's output is missing. The swarm
runner already handles partial failures gracefully via `n_available`. If
**all** specialists fail, premarket will see `SWARM_CONTEXT_UNAVAILABLE`
and skip the swarm-conditioned logic.

Rationale: auto-fallback complicates Pool.map semantics and burns Claude
quota during a MiniMax outage. The swarm is advisory (OP-28); a missing
day of swarm context is recoverable. Future iteration may add a single
retry on `429` rate-limit before giving up.

### 5. Synthesis (CIO) stays on Claude

Per J 2026-05-20 ratification ("keep Stage 1 + Stage 6 on Claude"). The
synthesis agent is the only stage that:
- Reads all 5 specialist outputs
- Makes the day's bias call
- Writes the 3 falsifiable predictions

Quality matters more than cost here. Synthesis is ~$0.05/fire on Sonnet
and unchanged by this migration.

---

## Failure modes + mitigations

| Failure | Symptom | Mitigation |
|---|---|---|
| API key missing | `auth-failed: OpenRouter key missing at ...` in STATUS.md | Paste key into `.openrouter.key`, re-fire. |
| API key invalid | `auth-failed: key doesn't start with sk-or-` | Get a fresh key from openrouter.ai. |
| Daily cap exhausted | `daily-cap-exhausted $5.XX >= $5.00` in STATUS.md | Wait 24h (UTC reset) or raise `DAILY_CAP_USD` in `run_minimax.py`. |
| OpenRouter 429 / rate limit | Agent's `ok=False`, `error: RateLimitError` | Single agent's output missing. Swarm continues with n_available < 4. |
| OpenRouter 5xx | Agent's `ok=False`, `error: APIStatusError` | Same as above. Issue logged to telemetry. |
| MiniMax outputs non-JSON | `json parse failed; raw saved to {agent}_minimax_raw.txt` | Inspect raw file. Common cause: response truncated by `max_tokens`. Raise budget. |
| `max_tokens` too low | `finish_reason: length` + empty content | M2 is a reasoning model; raise `max_tokens` to ≥4000 for analytical tasks. |

---

## Wake-Fire Revival (proposed — awaiting J ratification)

Per `automation/overnight/STATUS.md` 2026-05-20: J paused the
gamma-overnight-grinder cron because it was burning Max plan quota during
interactive testing. With MiniMax in place, wake fires could resume on a
much cheaper budget.

**DRAFT in `automation/overnight/queue.md` priority HIGH** for J's morning
review. Not auto-launched — J says go, then go.

---

## When to extend this to a new surface

The 3-question checklist:
1. **Is the work LLM-driven?** (If pure Python, no LLM in loop → skip.)
2. **Does it modify live trading doctrine?** (`heartbeat.md`, `params*.json`,
   live-order placement → skip per Rule 9.)
3. **Is the model's job analytical/text-output, or does it need tools/vision?**
   (M2 is text-only with reasoning. Vision tasks → keep Claude.)

If all three answers say "yes, migrate," follow the pattern in
`minimax_dispatcher.py`:
- Declare per-task input files
- Declare output file path
- Build composite prompt with inlined inputs + OUTPUT RULE
- Call `call_minimax()` with `task_id="{surface}.{task_name}"`
- Extract JSON + write file atomically

---

## Telemetry queries (one-liners)

```powershell
# Today's spend
python setup/scripts/run_minimax.py --check-status

# Recent calls
Get-Content automation\state\minimax-calls.jsonl -Tail 20 | ConvertFrom-Json | Format-Table ts, task_id, model, cost_usd, elapsed_s

# Cost by task_id over last 24h
Get-Content automation\state\minimax-calls.jsonl | ConvertFrom-Json | Group-Object task_id | Select-Object Name, @{Name='cost';Expression={($_.Group | Measure-Object cost_usd -Sum).Sum}} | Sort-Object cost -Descending

# All non-ok calls today
Get-Content automation\state\minimax-calls.jsonl | ConvertFrom-Json | Where-Object {$_.ok -eq $false}
```

---

## Doctrine cross-references

- **CLAUDE.md OP-3** — Cost-effectiveness gate ($100/mo Max budget).
- **CLAUDE.md OP-15** — Multi-Agent Gamma 2.0 (Pool-based parallelism; this extends it to multi-provider).
- **CLAUDE.md OP-20** — Non-theatre validation (cost + telemetry disclosed up-front).
- **CLAUDE.md OP-25** — Engine-benefit autonomy (advisory infrastructure ships without ratification).
- **CLAUDE.md OP-28** — Swarm is advisory-only (no live-trade gating).
- **Rule 9** — No mid-session live-doctrine changes (this migration touches NONE).
