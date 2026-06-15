# Backtesting Playbook — A Transferable Knowledge Base

> **Audience:** any future project (yours or someone else's) building a quantitative backtesting + autonomous research pipeline.
>
> **What this is:** the distilled lessons, patterns, doctrine, and architecture from building Project Gamma's 0DTE SPY trading engine. Hard-won across many mistakes. Read this first to skip them.
>
> **What this is NOT:** Project Gamma–specific code. The patterns apply broadly to any strategy backtesting effort (options, equities, crypto, futures, sports betting, ML training pipelines, etc).
>
> **Origin:** ratified 2026-05-10 after a weekend grind that produced a $19,627 wide-window winner that almost shipped without disclosing 176% top-5 concentration risk and Q3+Q4 2025 net-negative quarters. The non-theatre validation doctrine (OP 20 in `CLAUDE.md`) emerged from that near-miss.

---

## TABLE OF CONTENTS

1. [The North Star Principles](#1-north-star-principles)
2. [Anti-Patterns We Already Made (don't repeat)](#2-anti-patterns)
3. [The 5-Stage Grinder Pipeline](#3-five-stage-pipeline)
4. [Validation Stack (the order matters)](#4-validation-stack)
5. [Disclosure Standards (non-theatre)](#5-disclosure-standards)
6. [Infrastructure Patterns](#6-infrastructure-patterns)
7. [Autonomy Patterns](#7-autonomy-patterns)
8. [Cost Discipline](#8-cost-discipline)
9. [Adapting This To Your Strategy](#9-adapting)
10. [Reference: file map + glossary](#10-reference)

---

## 1. North Star Principles

These are the principles that, in hindsight, would have saved us weeks of churn. Adopt them on day 1.

### 1.1 Source-of-truth FIRST, optimization SECOND

Define your **anchor trades** (or anchor outcomes) before tuning any knob. These are the trades/outcomes the backtest MUST produce — they encode the human edge being captured.

For Gamma: 3 winning trades by J + 4 losing trades. The engine MUST take similar trades on winning days AND skip/profit on losing days. That's the PRIMARY metric.

For your project: pick the equivalent. It might be:
- A list of historical trades a senior trader made
- A list of regime-change moments the strategy must catch
- A specific user behavior pattern the model must reproduce

Without anchor trades, optimization drifts toward whatever maximizes aggregate Sharpe — which is OFTEN unrelated to the actual edge you're trying to encode.

### 1.2 Aggregate metrics are SECONDARY tiebreakers

Win rate, total P&L, Sharpe, expectancy — all are SECONDARY. They tie-break candidates with similar primary-metric performance. **Never optimize on aggregate alone.** It almost always overfits to noise.

### 1.3 Floor protection beats max-finding

Define metrics that the candidate MUST not regress on. Reject ANY candidate that breaks a floor, no matter how good its aggregate looks. Floors are typically:
- Anchor-trade P&L thresholds (4/29 ≥ $372)
- "Don't add losers on known loss days"
- "Don't introduce concentration risk above X%"

### 1.4 The strategy is regime-fragile (always)

Every strategy works in some regimes and fails in others. The question is which. **Discover the regime sensitivity before live trading**, not after.

For Gamma: stage 4 caught that ALL top candidates lose money in Q3+Q4 2025 (low-vol regime). Without that gate, we'd ship and lose money in summer.

### 1.5 In-sample wins are theatre. OOS wins are real.

Walk-forward validation (train on T-1 years, test on held-out T) is the gold-standard. Run it BEFORE any "ready" claim.

### 1.6 The simulator is a model, not reality

Black-Scholes ≠ real OPRA fills. Idealized fills ≠ real exchange microstructure. Run the top candidates through the most realistic simulator before live trading. Diff them against the cheap simulator. If the diff is large, your research is built on sand.

### 1.7 Cost discipline = $0 LLM in research loops

LLMs are for orchestration and judgment. Numerical research = pure Python. If you're calling an LLM inside a 432-combo grinder, you're burning budget for no gain.

---

## 2. Anti-Patterns We Already Made

Each entry has: **what we did wrong, what it cost, the fix.**

### 2.1 Aggregate Sharpe optimization

**What:** optimized on aggregate Sharpe over a 38-day window.
**Cost:** weekend of research. Found a "winner" that scored +49% WR / +$4,731 on the cherry-picked window but lost money on every broader window tested.
**Fix:** OP 16 — anchor-trade edge_capture is PRIMARY. Aggregate Sharpe only tie-breaks among candidates with similar edge_capture. Never let the optimizer choose a candidate that misses your anchor trades.

### 2.2 Sim ignored a critical parameter

**What:** Black-Scholes simulator hardcoded ATM strikes regardless of `strike_offset` parameter.
**Cost:** invalidated an entire weekend of grinder runs. Every "winner" was actually trading the wrong strikes.
**Fix:** before any candidate ratifies, write a sanity test that verifies the simulator's strike picker matches what production will use. Run it as part of CI.

### 2.3 Trendline trigger shipped without isolated unit test

**What:** wrote a complex multi-bar pivot algorithm + integrated it into the engine in the same commit.
**Cost:** trigger fired on noise pivots. Had to revert + rebuild 3 times.
**Fix:** **TDD.** Write the unit test FIRST with a hand-computed expected value for a specific historical bar. Iterate the algorithm until the test passes. ONLY THEN integrate into the engine.

### 2.4 Single-metric reporting

**What:** announced wide_pnl $12,105 (+231% baseline) without checking concentration.
**Cost:** user (correctly) called out that 176% concentration in top-5 days = strategy depends on outliers.
**Fix:** OP 19 — every evaluator computes top5_pct, quarter_pnl, positive_quarters, max_drawdown by DEFAULT. They're stored on every result row, not computed separately. Report them inline.

### 2.5 Naive total-P&L test/train ratio

**What:** computed test/train ratio as `test_pnl / train_pnl` with train=12mo and test=4.3mo.
**Cost:** ratio looked terrible (0.29-0.40x) when actually per-month rates were CONSISTENT.
**Fix:** always normalize ratios by time. `test_pnl_per_month / train_pnl_per_month` is the honest metric.

### 2.6 Going dark / chatbot reflexes

**What:** ended status updates with "Going dark, wake me up if anything important."
**Cost:** wasted hours. User had to prompt repeatedly to get progress.
**Fix:** OP 18 — banned phrases ("let me know", "your call", "want me to also..."). Required format: state + concerns-already-addressed + what-I'm-doing-next-and-when-I'll-check-back.

### 2.7 Same-quality re-entry without min-gap

**What:** allowed leg-2 trade re-entry after a stop without a time gap.
**Cost:** back-to-back stops on same setup compounded losses on 5/01 (-$22 → -$159).
**Fix:** 45-min minimum gap between same-quality re-entries.

### 2.8 Per-trade exit knobs hardcoded globally

**What:** SUPER-tier exit knobs (`tp1=+75%`, `stop=-20%`) applied to weak TRENDLINE trades, scratching them prematurely.
**Cost:** weak triggers held too long, blocked higher-quality re-entries.
**Fix:** per-quality exit knobs. SUPER gets the doctrine knobs; TRENDLINE gets fast scratch (tp1=+30%, stop=-8%).

### 2.9 First-entry-per-day lock

**What:** "first trade locks the day" rule to prevent churn.
**Cost:** killed 5/04's BIG SUPER trade because an early TRENDLINE locked the day.
**Fix:** quality-rank-based escalation lock. Allow strictly higher quality to break the lock.

### 2.10 Optimization-induced overfit (the BIG one)

**What:** ran 432+324+155+81 = ~1000 combos. Picked the winner. Reported the result.
**Cost:** the winner is selected from a distribution of randomness. Some appear good by chance.
**Fix:** Stage 3 (concentration) + stage 4 (sub-window) gates filter survivorship. Walk-forward validates OOS. Real-fills check. All must pass.

### 2.11 Reporting "ready" without disclosures

**What:** announced "$19,627 wide_pnl" as if it was a $1K-account return.
**Cost:** user thought paper account would 19x in 16mo. Actually requires $25K+ to fit per-trade risk cap.
**Fix:** OP 20 — every numeric claim requires account-size scaling table, sample bias note, OOS evidence, failure modes, concentration disclosure, and regime sensitivity.

---

## 3. The 5-Stage Grinder Pipeline

Each stage has stricter gates than the previous. Candidates flow stage→stage; only those passing every gate make it to ratification.

```
                        ┌──────────────────────────────────────┐
                        │   STAGE 1: Floor + parameter sweep   │
                        │   (~432 combos, broad exploration)   │
                        └─────────────────┬────────────────────┘
                                          │ keepers (4-10)
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   STAGE 2: Refine top-5 keepers      │
                        │   (~324 combos, ±1-step neighborhood)│
                        └─────────────────┬────────────────────┘
                                          │ keepers (2-5)
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   STAGE 3: Regime-robustness gates    │
                        │   (top5≤200%, ≥4/6 quarters net+)    │
                        └─────────────────┬────────────────────┘
                                          │ keepers (4-8)
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   STAGE 4: Sub-window stability       │
                        │   (every quarter net+ AND ≥3 trades) │
                        └─────────────────┬────────────────────┘
                                          │ keepers (0-3)
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   STAGE 5: Final ratification         │
                        │   (writes scorecard, awaits human YES)│
                        └─────────────────┬────────────────────┘
                                          │
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   WALK-FORWARD VALIDATION (OOS)       │
                        │   (train T-1, test held-out T)       │
                        └─────────────────┬────────────────────┘
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   REAL-FILLS VALIDATION               │
                        │   (top-3 days via realistic simulator)│
                        └─────────────────┬────────────────────┘
                                          ▼
                        ┌──────────────────────────────────────┐
                        │   MONDAY-READY CHECKLIST              │
                        │   (all 6 gates must pass)             │
                        └─────────────────┬────────────────────┘
                                          ▼
                              HUMAN RATIFICATION (rule 9)
```

### Stage-by-stage detail

#### Stage 1: Broad parameter sweep with floor protection
- **Goal:** find candidates that DON'T break the anchor floors
- **Grid:** 200-500 combos covering the full preserve-the-edge knob ranges
- **Gates:** anchor trades must not regress; losers_added = 0
- **Output:** `keepers.jsonl` with 4-10 candidates
- **Time budget:** 4-8 hours

#### Stage 2: Refine around top-5 keepers
- **Goal:** explore tighter neighborhoods around stage 1 winners
- **Grid:** ±1-step variations on each axis, deduplicated
- **Gates:** same as stage 1
- **Output:** 2-5 refined keepers
- **Time budget:** 4 hours

#### Stage 3: Regime-robustness gates
- **Goal:** filter survivorship-biased candidates
- **NEW gates:**
  - `top5_pct ≤ 200%` (concentration cap)
  - `≥4/6 quarters net-positive` (regime coverage)
- **Output:** 4-8 candidates that aren't 1-day wonders
- **Time budget:** 4-6 hours

#### Stage 4: Sub-window stability
- **Goal:** strictest gate — every quarter must work
- **NEW gates:**
  - EVERY sub-window (Q1...Q6) net-positive
  - ≥3 trades per quarter (statistical significance)
- **Output:** 0-3 truly regime-robust candidates
- **Time budget:** 1-4 hours
- **Note:** 0 keepers is a valid finding — means strategy IS regime-fragile, fall back to stage 3 best with explicit caveat

#### Stage 5: Final ratification
- **Goal:** pick THE winner + write publish-ready scorecard
- **One-shot Python script** (not a grinder)
- **Output:** `analysis/recommendations/{rule_id}-final.json` + human-readable `docs/RATIFICATION-READY.md`
- **No human-write of params:** the scorecard is read-only, awaits human YES

### Why each stage exists (catch matrix)

| Stage | Catches |
|---|---|
| 1 | "this combo breaks the proven setup" |
| 2 | "we already know this neighborhood works, can we improve?" |
| 3 | "this combo wins on 5 outlier days and otherwise loses" |
| 4 | "this combo wins in some regimes and loses in others" |
| 5 | publication discipline |
| Walk-forward | "this combo overfits in-sample" |
| Real-fills | "the simulator is wrong" |

---

## 4. Validation Stack

Every candidate must pass IN THIS ORDER:

### 4.1 Floor protection
Anchor trades must not regress. Losers must not be added. Hard kill.

### 4.2 Default per-row metrics
Every evaluator computes: `top5_pct`, `quarter_pnl` dict, `positive_quarters`, `max_drawdown`, `wide_n_trades`, `wide_wr`. **No separate "validation step" — they're stored inline.**

### 4.3 Concentration gate
`top5_pct ≤ 200%`. If your top-5 days = 200%+ of P&L, the strategy depends on outliers. Most days NET-LOSE.

### 4.4 Quarter coverage gate
`positive_quarters ≥ 4 of 6`. Regime variety check.

### 4.5 Sub-window stability gate
EVERY sub-window net-positive. Strictest gate. 0 keepers is informative.

### 4.6 Walk-forward (OOS)
- Split: train = T-1 years, test = most recent year(s) held-out
- Per-month normalized: `test_pnl_per_month / train_pnl_per_month >= 0.5`
- Test P&L > 0
- Naive total-P&L ratio is misleading when window sizes differ

### 4.7 Real-fills validation
- Top-3 days through realistic simulator (real OPRA, real bid-ask, real microstructure)
- Diff against cheap simulator
- If diff > ±20%, the cheap simulator can't be trusted for ratification

### 4.8 Monday-ready checklist
Final gates before ratification:
- Stage 5 fired (`{rule_id}-final.json` exists)
- Walk-forward OOS positive
- All required scheduled tasks enabled
- Bridge alive
- Responder healthy
- Winner metrics pass all floors

---

## 5. Disclosure Standards (Non-Theatre, OP 20)

Every numeric claim entering doctrine, recommendation files, CHANGELOG, or user-facing report MUST come bundled with:

### 5.1 Account-size scaling table
"This number requires $X account. On $Y paper, you'd realize $Z."

```
qty=28 LEVEL trade × $1.20 entry = $3,360 capital required
At 50% per-trade risk cap:
  $1K account → max qty=4  → realized P&L ≈ 14% of headline
  $5K account → max qty=20 → realized P&L ≈ 71% of headline
  $25K account → no cap binds → 100% of headline
```

### 5.2 Sample bias note
"Selected from N grinder combos. Survivorship bias: filtered by gates X, Y. Z% chance of pure-randomness selection at this combo."

### 5.3 Out-of-sample evidence
"Walk-forward 2026 test = $A (per-month rate matches train within ±B%)."

### 5.4 Failure mode enumeration
- Worst single day P&L
- Longest losing streak
- Max drawdown (sequential)
- Account-blow-up scenario (e.g. -50% kill-switch limits day to ≤$X loss)
- Regime-shift sensitivity (e.g. "loses in low-vol periods like Q3-Q4 2025")

### 5.5 Concentration disclosure
"Top-5 days = X% of total P&L. Implication: ordinary-day outcome ≈ $0, big wins on few high-vol days."

### 5.6 Regime sensitivity
"Worked in regime A (high VIX, post-FOMC). Failed in regime B (summer low-vol). Current regime status: A."

### Banned phrasings

- "Strategy works" → "Strategy works in-sample; OOS verdict pending"
- "Engine BEATS [human]" → "Engine optimized to BEAT [human]'s specific N days; not extrapolated"
- "Wide P&L $X" → "$X (16-month aggregate, requires $Y+ account, top-5 concentration Z%)"
- "Monday ready" → only if checklist gate-pass file is current
- Any "ready" claim without the 6 disclosures

---

## 6. Infrastructure Patterns

### 6.1 Silent multiprocessing on Windows
```python
import multiprocessing as mp
import sys
from pathlib import Path

# CRITICAL: must run BEFORE Pool() and BEFORE any other mp call
if sys.platform == "win32":
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if pythonw.exists():
        mp.set_executable(str(pythonw))

# Now Pool() workers spawn pythonw.exe — no console flash
with mp.Pool(workers) as pool:
    for result in pool.imap_unordered(evaluate_combo, grid):
        ...
```

**Why:** Windows multiprocessing.Pool spawns child processes. Default = python.exe → console window flashes. pythonw.exe = silent.

### 6.2 Hard concurrency cap
`MAX_PARALLEL_RESEARCH_WORKERS = 4` — even on 16-core machines. Going higher thrashes RAM and gives net-negative throughput.

### 6.3 Process-based parallelism only
Module-level state mutation (e.g., `lib.filters` constants patched via context manager) is NOT thread-safe. Use `multiprocessing.Pool`, never `concurrent.futures.ThreadPoolExecutor`.

### 6.4 Idempotent launchers
Every launcher script checks for an existing PID file. If alive → exit (no double-launch). If dead → relaunch. Watchdog tasks call launchers at intervals = self-healing.

```powershell
if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile).Trim()
    if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {
        Write-Output "already running"; exit 0
    }
}
# ... start process
```

### 6.5 Atomic state writes
```python
def _write_progress(state: dict) -> None:
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS)  # atomic rename
```

Crash mid-write = no partial JSON file. Other processes always see a complete state.

### 6.6 Append-only result logs
Every keeper / rejection appended to `results.jsonl` / `rejections.jsonl`. Never overwrite. Replay-able. Human-greppable.

### 6.7 Per-stage progress.json
Schema:
```json
{
  "started_at": "ISO timestamp",
  "deadline_at": "ISO timestamp",
  "total_combos": int,
  "completed": int,
  "passed_floors": int,
  "rejected": int,
  "keepers": int,
  "best_edge_capture": float,
  "best_wide_pnl": float,
  "current_pid": int,
  "workers": int,
  "last_update": "ISO timestamp",
  "status": "running" | "completed" | "deadline_reached"
}
```

External monitors read this. Dashboards visualize it. Watchdogs detect stalls.

### 6.8 Hard deadlines on every grinder
Every stage has `--hours N` cap. Process exits gracefully at deadline regardless of completion. Prevents runaway grinds.

### 6.9 Random shuffle the grid
Always `random.Random(seed).shuffle(grid)`. If killed early, you've explored randomly across the whole space, not just one corner.

---

## 7. Autonomy Patterns

### 7.1 Hourly watchdog
Scheduled task runs every hour:
- Checks each grinder PID
- Restarts dead grinder if before deadline
- Auto-launches next stage when prior completes
- Writes monitor.json + monitor.jsonl

### 7.2 Daily morning summary
Scheduled task runs at 08:00 ET daily:
- Aggregates state from all stages
- Writes `automation/state/research-queue.json` (machine-readable)
- Writes `docs/STATUS.md` (human-readable)
- Any session/dashboard/human reads from these = single source of truth

### 7.3 Self-audit
Scheduled task runs every hour:
- Verifies bridge + responder alive
- Checks scheduled task states
- Writes `docs/HEALTH.md`
- **Discord ping ONLY on RED flags** — no green-status spam

### 7.4 Discord bidirectional bridge
- Bridge process: polls Discord channel → writes inbox.jsonl ; watches outbox.jsonl → sends to Discord
- Responder task: every 5 min, reads inbox for new messages, invokes `claude --print` with context, queues response to outbox
- Bridge sends within 15s

### 7.5 Cross-session memory
Persistent files that any new session reads to know state:
- `automation/state/research-queue.json` — pipeline next-action
- `docs/HEALTH.md` — component health
- `docs/STATUS.md` — full grinder summary
- `automation/state/usage-snapshot.json` — cost spent
- `automation/state/self-audit.json` — last health check

---

## 8. Cost Discipline

### 8.1 LLM cost map
| Component | Cost |
|---|---|
| Grinder chain | $0 (pure Python, pythonw.exe) |
| Watchdog / monitor | $0 (file ops + tasklist) |
| Daily summary | $0 |
| Discord bridge | $0 (Discord HTTP API) |
| Self-audit | $0 |
| Discord responder | $0.05-0.15 per user message (only when message arrives) |
| THIS chat session | $0.05-0.15 per turn (only when user prompts) |

### 8.2 Hard rate limits
```python
DAILY_CAP = 50   # claude --print invocations / day
HOURLY_CAP = 15
PER_MIN_CAP = 1  # burst protection

EST_COST_PER_INVOCATION = 0.10  # midpoint $0.05-0.15

# Max daily LLM cost: 50 * $0.10 = $5/day
```

### 8.3 Refuse over cap
If cap exceeded, queue a "rate-limited" reply to user instead of invoking. Watermark advances so message isn't reprocessed forever.

### 8.4 No LLM in research loops
432 combos × $0.10 / call = $43.20 per stage if you call LLM in the loop. Pure Python = $0. **The LLM is for orchestration, not iteration.**

---

## 9. Adapting This To Your Strategy

This playbook is strategy-agnostic. Here's what to swap when applying it elsewhere:

### 9.1 Define your anchor outcomes
- Trading: list of trades a senior trader made
- ML training: dataset + target metrics on held-out validation
- A/B testing: list of historical experiments + their outcomes
- Anything: a SHORT immutable list of "the system MUST handle these correctly"

### 9.2 Build your evaluator
The `evaluate_combo(combo)` function is your strategy's heart. It must:
- Take a parameter dict
- Run the strategy with those params
- Return a result dict with: anchor outcomes, aggregate metrics, default disclosures (top5_pct, quarter_pnl, max_drawdown), `passed_floors` boolean, `regressions` list

Everything else (grinder loop, monitors, watchdogs) is reusable.

### 9.3 Define knob ranges that PRESERVE anchor wins
Test ±1 step from your current best. Sweep within those bounds. Going outside breaks anchor wins (we proved this 4× with OTM-2 forcing, wider stops, etc.).

### 9.4 Pick stage gates appropriate to your domain
- Concentration cap (most domains)
- Sub-window stability (most domains with regime variation)
- Walk-forward (anything time-series)
- Real-fills equivalent: any "cheap-vs-realistic simulator" diff

### 9.5 Inherit the doctrine
Most of OP 18 (autonomous), OP 19 (self-healing), OP 20 (non-theatre) is universal. Copy these into your project's CLAUDE.md / equivalent.

---

## 10. Reference

### 10.1 File map (Project Gamma — for your reference)

```
backtest/autoresearch/
├── overnight_grinder.py      # Stage 1
├── stage2_grinder.py         # Stage 2
├── stage3_grinder.py         # Stage 3 (regime-robustness)
├── stage4_grinder.py         # Stage 4 (sub-window stability)
├── stage5_ratify.py          # Stage 5 (one-shot ratification)
├── walk_forward_validate.py  # OOS walk-forward
├── monday_ready_check.py     # Final gate aggregator
├── overnight_monitor.py      # Hourly chain monitor
├── daily_status.py           # Daily 08:00 ET summary
├── self_audit.py             # Hourly health check
├── usage_tracker.py          # LLM cost cap
├── grinder_discord_notify.py # Discord pings on transitions
├── bullish_grinder.py        # Bullish-side optimization
├── inspect_combo.py          # Per-day breakdown for any combo
└── overnight_summary.py      # Top-K candidate report

setup/scripts/
├── launch-overnight-grinder.ps1   # Stage 1 silent launcher
├── launch-stage2-grinder.ps1
├── launch-stage3-grinder.ps1
├── launch-stage4-grinder.ps1
├── launch-bullish-grinder.ps1
├── run-stage5-ratify.ps1
├── run-overnight-monitor.ps1
├── run-daily-status.ps1
├── run-self-audit.ps1
├── run-monday-ready-check.ps1
├── run-grinder-discord-notify.ps1
├── run-discord-responder.ps1
├── ensure-discord-bridge-alive.ps1
├── discord-bridge.py
├── discord-responder.py
└── discord-watcher.py

docs/
├── BACKTESTING-PLAYBOOK.md      # this file (transferable knowledge)
├── FUTURE-IMPROVEMENTS.md       # queued improvements (don't distract)
├── STATUS.md                    # daily auto-generated
├── HEALTH.md                    # hourly auto-generated
├── MONDAY-READY-CHECKLIST.md    # auto-generated, gates pass/fail
├── WALK-FORWARD.md              # auto-generated OOS verdict
├── RATIFICATION-READY.md        # auto-generated when stage 5 picks winner
└── WAKE-UP-{date}.md            # session-handoff briefings

automation/state/
├── research-queue.json          # cross-session pipeline state
├── monday-ready.json            # current gate-pass state
├── self-audit.json              # current health
├── usage-snapshot.json          # current LLM cost
├── discord-inbox.jsonl          # Discord → me
├── discord-outbox.jsonl         # me → Discord
└── usage-tracker.jsonl          # append-only invocation log

doctrine/
├── edge-master-doctrine.md      # the proven anchor patterns + knob ranges
├── seed10095-exit-doctrine.md   # specific exit doctrine
├── rules-as-gates.md            # gate-pattern doctrine
├── iron-law-trades.md           # never-violate rules
└── rationalization-counters.md  # discipline patterns

CLAUDE.md                         # operating principles + soul file
CHANGELOG.md                      # audit trail of every doctrine change
```

### 10.2 Glossary

- **Anchor trade / outcome**: an immutable historical event the system MUST handle correctly. Defines edge_capture metric.
- **Edge capture**: `sum(engine_pnl on anchor wins) - sum(engine_loss on anchor losses)`. PRIMARY metric.
- **Floor**: a metric threshold the candidate must not regress on. Hard reject if breached.
- **Keeper**: a candidate that passed all gates of the current stage.
- **Top5_pct**: top-5 winning days as % of total P&L. Concentration measure.
- **Walk-forward**: train on T-1 years, test on held-out T. OOS validation.
- **Real-fills**: realistic simulator (real exchange microstructure) vs cheap simulator (Black-Scholes etc).
- **OP N**: numbered operating principle in CLAUDE.md.
- **Stage 1-5**: the grinder pipeline (sweep → refine → robustness → stability → ratification).

### 10.3 Critical operating principles (from CLAUDE.md)

- **OP 16**: anchor-trade edge_capture is PRIMARY metric. Aggregate is secondary tiebreaker.
- **OP 17**: GRIND-UNTIL-DONE. The standard IS the assignment. No permission-asking.
- **OP 18**: Truly autonomous research mode. Banned phrases. Required format. Pre-plan full pipelines.
- **OP 19**: Self-healing pipeline. Each stage reads prior keepers. Auto-launches next. Default validation metrics.
- **OP 20**: Non-theatre validation. Disclosures mandatory. Banned phrasings. Default validation pipeline.
- **OP 14**: WR is NOT primary metric.
- **OP 11**: Karpathy method (eval-first, data flywheel, propose/eval/ratify).
- **OP 3**: Cost-effectiveness gate. $0 LLM in research loops.

### 10.4 The 5-step "starting from scratch" flow

If you're a new project applying this playbook:

1. **Define your 3-7 anchor outcomes.** Write them in immutable form (a markdown table or JSON file). They cannot change once you start optimizing.
2. **Build evaluate_combo(combo) → dict.** Test it with a single hand-picked combo. Verify every default metric (top5_pct, quarter_pnl, etc.) computes correctly.
3. **Build stage 1.** Floor protection only. Run it on ~200 combos. Verify keepers.jsonl populates.
4. **Add stages 2-5 incrementally.** Each adds ONE new gate. Test that each stage's rejections explain WHY (which gate fired).
5. **Wire monitor + scheduled tasks.** Don't skip this. Manual orchestration WILL bite you.

### 10.5 The 5 things to do FIRST when adapting

1. Write your equivalent of `j_edge_tracker.py` (anchor scorer)
2. Write your equivalent of `evaluate_combo()` (full evaluator with default metrics)
3. Write your equivalent of `edge-master-doctrine.md` (proven knob ranges)
4. Write your equivalent of `monday_ready_check.py` (checklist gates)
5. Write your equivalent of `BACKTESTING-PLAYBOOK.md` (this file, customized to your domain)

After that, the grinder + monitor + autonomy patterns transfer with minimal modification.

---

## License + attribution

This playbook captures lessons learned by Project Gamma between 2026-04-29 and 2026-05-10. It is intended to be copied freely into any other project. The patterns are not novel individually — most are standard quant-research practice. Their VALUE is in being collected here, learned-from-mistakes-attached, and battle-tested in a live autonomous research pipeline.

**If you adopt this playbook, the highest-value sections to copy verbatim are:**
- §1 (North Star Principles)
- §2 (Anti-Patterns) — already-paid-for lessons
- §5 (Disclosure Standards)
- §8 (Cost Discipline)

The architectural patterns (§3, §6, §7) are reusable but require adaptation to your stack.
