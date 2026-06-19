# HANDOFF 1 — Build the free-model (Nemotron) shadow-heartbeat evaluator

**Paste this whole file as the first message of a new Sonnet chat in this project.**
You are picking up a specific, self-contained build. Read this top to bottom before doing anything.

---

## Mission (one sentence)
Build a **read-only shadow evaluator** that asks a **free OpenRouter model (NVIDIA Nemotron)** to make the same per-tick trading decision the live heartbeat makes, logs what it *would* do **without placing any orders**, and scores how often it agrees with the real (Claude Haiku) heartbeat — so the owner (J) can decide whether a free model can safely run the heartbeat and get **rate-pool isolation for $0**.

## Why this exists
- The live heartbeat runs as `claude --print` (Claude Haiku) every 3 min during RTH, reading the chart via the TradingView MCP and placing/managing Alpaca **paper** orders via the Alpaca MCP. It shares Anthropic's rate-limit pool with interactive Claude — and on 2026-06-15 a heavy interactive session **starved the heartbeat 13:42–15:30 ET**, blinding runner management.
- J wants isolation without paying ~$150–200/mo for a dedicated Anthropic key. Idea: run the heartbeat on a **free** OpenRouter model.
- The catch: a free model on **live orders** is unproven and risky. So we evaluate it in **shadow** first. **This task is the shadow evaluator only. It must never place an order.**

## What to build
A script: `setup/scripts/shadow_model_eval.py` (Python 3, runs under the project venv on Windows, Python 3.13).

It must:
1. **Replay** a given day's heartbeat ticks from the decision ledgers (`automation/state/decisions.jsonl` for Safe, `automation/state/aggressive/decisions.jsonl` for Bold). Each row is one tick and already contains the market snapshot the heartbeat saw: `spy`, `vix`, `vix_dir`, `ribbon_stack`, `ribbon_spread_cents`, `bull_score`, `bear_score`, `action`, `position_status`, `time_et`, etc.
2. For each tick, **construct a decision prompt** for the free model using the heartbeat's own decision rubric (read it from `automation/prompts/heartbeat.md` — the 11 BULLISH / 10 BEARISH filters, the trigger logic, the score thresholds, the entry/exit gates). Give the model the same snapshot fields and ask it to output a **strict JSON** decision: `{"action": "...", "bull_score": N, "bear_score": N, "reason": "..."}` using the same action vocabulary the ledger uses (`HOLD`, `HOLD_RUNNER`, `ENTER_BULL`, `ENTER_BEAR`, `EXIT_*`, `SKIP_*`).
3. **Call the free model via OpenRouter.** Reuse the existing calling pattern — read `setup/scripts/kitchen_daemon.py` (and any `run_minimax.py` / `run_nemotron.py` helper) to see exactly how the Kitchen authenticates and calls OpenRouter, and copy it. The key is at `automation/state/.openrouter.key`. Use the **free** Nemotron slug from the Kitchen's model ladder (find the exact `nvidia/nemotron-...:free` string in the Kitchen code/config — do not guess it).
4. **Log** one row per tick to `automation/state/shadow-model-decisions.jsonl`:
   ```json
   {"date":"...","time_et":"...","account":"safe|bold","real_action":"...","shadow_action":"...","agree":true,"real_scores":[bull,bear],"shadow_scores":[bull,bear],"model":"nvidia/nemotron-...:free","latency_ms":N}
   ```
5. **Score** at the end: overall agreement %, and **separately** the agreement on *decision* ticks only (anything that is not a plain `HOLD`/`HOLD_RUNNER` — i.e. the entries, exits, and skips that actually matter). Print a scorecard and write it to `analysis/shadow-model/{date}-scorecard.md`.

## Hard guardrails (do not violate)
- **NEVER import or call any Alpaca tool or order function.** This script reads ledgers and calls OpenRouter. Nothing else.
- **Free tier only.** Use only the free Nemotron slug. If OpenRouter returns a rate-limit/quota error, log `RATE_LIMITED` for that tick and continue — do not fall back to a paid model.
- **Read-only on production state.** Do not modify `params.json`, `heartbeat.md`, `decisions.jsonl`, `current-position*.json`, or anything the live system writes. Only create the two new output files above.
- Cost ceiling: $0 (free tier). If you cannot stay free, stop and report.

## How to run / validate
- Run over the most recent full trading day that has ticks: e.g. `python setup/scripts/shadow_model_eval.py --date 2026-06-15 --account both`.
- It should process every tick in that day's ledgers and produce the scorecard.
- Sanity check by hand: pick 3 ticks (one HOLD, one entry/exit, one high-score) and confirm the shadow prompt contained the right snapshot and the model returned parseable JSON.

## Acceptance criteria
- `shadow_model_eval.py` runs clean over a full day, no orders touched, free tier only.
- Produces `shadow-model-decisions.jsonl` + a `{date}-scorecard.md` with overall and decision-only agreement %.
- A short written verdict at the bottom of the scorecard: *can Nemotron match Haiku on the decisions that matter?* (high agreement on entries/exits = candidate to promote; sloppy = keep Haiku).

## Environment gotchas — READ THIS, it will save you hours (lesson L78)
This repo is a **FUSE mount** into a Linux sandbox; the real files live on Windows at `C:\Users\jackw\Desktop\42`.
- **git does NOT work in the sandbox** — it corrupts itself. Run git on Windows only (`setup/setup-git.ps1`). Don't `git init` in the sandbox.
- **The mount serves TRUNCATED reads of files you just edited.** After you Edit/Write a file, the sandbox's `python`/`cat` may see a cut-off version. To run/validate Python: copy the files to **`/tmp`** and run there, with `PYTHONPYCACHEPREFIX=/tmp/pyc` to avoid stale bytecode. The Read/Grep tools (Windows side) see the complete file — trust those for content.
- **Deletes are forbidden** on the mount (`rm` = Operation not permitted). Don't rely on deleting; write to `/tmp` for scratch.
- **Back up before editing**: `cp file _local_backups_YYYYMMDD/` (writes are allowed).
- Sandbox Python is **3.10**; the project venv is **3.13** (`backtest/.venv`). Some code uses 3.13 features (e.g. `copy.replace`). Validate logic accordingly; the authoritative run is on Windows.
- **Do not run heavy work during market hours (09:30–15:55 ET)** — it starves the live heartbeat's rate pool. This shadow eval is offline/after-hours.

## Files to read first (in order)
1. `automation/prompts/heartbeat.md` — the decision rubric you're replicating (filters, triggers, gates, action vocabulary).
2. `setup/scripts/kitchen_daemon.py` — the working OpenRouter call pattern + the exact free Nemotron slug + key handling.
3. `automation/state/decisions.jsonl` and `automation/state/aggressive/decisions.jsonl` — the tick schema you replay.
4. `backtest/lib/shadow.py` — the existing OP-11 *param* shadow (different purpose — it A/Bs params in backtest — but shows the house style for "shadow = read-only comparison").
5. `automation/state/.openrouter.key` — the key (gitignored; never print it).

When done, write a 10-line summary to `analysis/shadow-model/BUILD-NOTES.md` so the next session knows what you built and what the agreement numbers were.
