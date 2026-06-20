# Architecture Overview — Project Gamma

> Living document. Snapshot of how the rig is wired today, written for an agent who's just walked in cold.
> When components or wiring change, update this file in the same commit.

---

## 1. Project Structure

```
C:\Users\jackw\Desktop\42\                  # repo root (not a git repo — local workspace)
├── CLAUDE.md                               # Soul file. Mission, 10 rules, 11 operating principles. Read first.
├── CHANGELOG.md                            # 80+ doctrine evolution entries. The "why" behind every rule.
├── markdown/specs/ARCHITECTURE.md                         # This file.
├── README.md                               # Quick-start orientation.
│
├── automation/                             # The autonomous engine
│   ├── prompts/                            # Markdown prompts invoked by scheduled tasks
│   │   ├── premarket.md                    # 08:30 ET — level audit, bias, hypothesis, drift checks
│   │   ├── heartbeat.md                    # 09:30–15:50 ET, every 3min — per-tick decisioning
│   │   ├── eod-flatten.md                  # 15:55 ET — safety-net position close
│   │   ├── eod-summary.md                  # 16:00 ET — trade grades, drift sync, hypothesis grades
│   │   ├── daily-review.md                 # 16:30 ET — strategic reflection, tomorrow's levels
│   │   └── weekly-review.md                # Sunday 18:00 ET — rollup + ratification proposal
│   ├── state/                              # Runtime state (JSON + JSONL)
│   │   ├── params.json                     # CANONICAL config — rule_version, stops, sizing, gates
│   │   ├── mode.json                       # live-paper | dry-run | paused
│   │   ├── current-position.json           # Open position state (null = flat)
│   │   ├── today-bias.json                 # Day's bias + key levels + falsifiable hypothesis
│   │   ├── key-levels.json                 # Schema v3: support/resistance with strength scoring
│   │   ├── circuit-breaker.json            # Daily-loss kill switch flag
│   │   ├── loop-state.json                 # session_id, vix_cache, ribbon, htf, mode (HOT/BASE/COOL)
│   │   ├── news.json                       # Macro calendar (FOMC/CPI/NFP)
│   │   ├── shadow-version.json             # A/B test candidate rule version
│   │   ├── decisions.jsonl                 # Per-tick decision log (post-hoc graded EOD)
│   │   ├── hypothesis-grades.jsonl         # Per-prediction grading (PASS/FAIL/PARTIAL_*)
│   │   ├── rule-breaks.jsonl               # Cost-tagged rule violations
│   │   ├── process-compliance.jsonl        # Daily clean/dirty flag + leading indicators
│   │   ├── backtest-drift.json             # EOD drift severity → next premarket gate
│   │   ├── .lastgood/                      # Atomic recovery backups (validated JSON snapshots)
│   │   └── logs/                           # Per-task per-day text logs
│   ├── morning-kickoff.md                  # Doctrine for autonomous startup
│   ├── loop-v2.md                          # Heartbeat protocol notes
│   ├── loop-state.json                     # Mode persistence between ticks
│   └── decision-log.md                     # Architecture-decision log
│
├── backtest/                               # Python research engine (mirrors live engine)
│   ├── run.py                              # Main CLI: `python run.py --start ... --end ... [--label ...]`
│   ├── lib/                                # Engine internals (must stay in sync with heartbeat.md)
│   │   ├── orchestrator.py                 # Wires data → ribbon → filters → pricing → simulator
│   │   ├── filters.py                      # 10 bearish + bullish filters, asymmetric triggers
│   │   ├── ribbon.py                       # Saty Pivot Ribbon (Fast/Pivot/Slow EMA)
│   │   ├── simulator.py                    # Synthetic-fill bracket simulator (Black-Scholes)
│   │   ├── simulator_real.py               # OPRA real-fill simulator (bid/ask/H/L)
│   │   ├── pricing.py                      # Black-Scholes ATM 0DTE
│   │   ├── levels.py + level_strength.py   # Level detection + retest history scoring
│   │   ├── trendlines.py                   # Multi-day confluence (±$0.30 tolerance)
│   │   ├── shadow.py                       # Live vs backtest parity checker
│   │   └── repro.py                        # Karpathy-style content-hash reproducibility
│   ├── autoresearch/                       # Autonomous parameter optimization
│   │   ├── loop.py                         # Iteration driver (proposer → backtest → decider)
│   │   ├── config.py                       # SEARCH_SPACE (23 knobs) + tiers + KEEP_THRESHOLDS
│   │   ├── proposer.py                     # Single/multi-knob mutator
│   │   ├── decider.py                      # KEEP/REVERT logic (sharpe-driven + hard gates)
│   │   ├── watchdog_report.py              # Health monitor + dead-end detection
│   │   ├── state.py                        # Per-mode state persistence + history append
│   │   └── _state/                         # {strict,balanced,aggressive}/{state.json,history.jsonl}
│   ├── data/                               # Historical bars
│   │   ├── spy_5m_2025-01-01_2026-05-07.csv  # 30,389 SPY 5m bars (master)
│   │   ├── vix_5m_*.csv                      # VIX 5m bars (matched range)
│   │   └── options/                          # OPRA cache, per-ticker-date-strike-type
│   ├── tests/                              # 117+ pytest tests, 2417 LOC
│   └── .venv/                              # Python 3.13 virtualenv
│
├── dashboard/                              # Live "Trade House" pixel-art UI (Next.js 15)
│   ├── app/                                # App Router: page.tsx, /api/state, /api/autoresearch, /api/snapshot
│   ├── components/                         # TradingFloor, AutoresearchPanel, TopBar, Left/RightPanel
│   ├── public/                             # trade-floor.png + sprite assets
│   └── package.json                        # next 15 + react 19 + swr + tailwind
│
├── setup/                                  # OS-level integration (PowerShell)
│   ├── _shared.ps1                         # Repair-StateFiles, Invoke-Claude, reaper, time/disk helpers
│   ├── launch_tv_debug.ps1                 # MSIX-bypass TradingView launcher with CDP
│   ├── install-tasks.ps1                   # Register all Gamma_* Windows scheduled tasks
│   ├── uninstall-tasks.ps1                 # Reverse of above
│   ├── run-modes-sweep.ps1                 # Manual autoresearch driver
│   └── scripts/                            # Per-task wrappers (run-premarket.ps1, run-heartbeat.ps1, …)
│
├── strategy/                               # Doctrine — the playbook
│   ├── playbook.md                         # Named setup patterns (rejection, reclaim, sequence)
│   ├── risk-rules.md                       # Sizing tiers, kill switches, PDT awareness
│   ├── chart-anatomy.md                    # Candlestick patterns (awareness-only)
│   ├── scale-out-math.md                   # TP1/runner exit math
│   └── checklists.md                       # Pre-trade checklist
│
├── analysis/                               # Research outputs
│   ├── backtests/{label}/                  # Per-run trades.csv + decisions.csv + summary.md + metadata.json
│   ├── weekly-reviews/                     # YYYY-Www.md
│   └── shadow-scorecards/                  # Per-day A/B test scorecards
│
├── journal/                                # System of record
│   ├── YYYY-MM-DD.md                       # Daily journal — pre-market, every trade, EOD reflection
│   ├── trades.csv                          # 41-column structured trade log
│   ├── mistakes.md                         # Rule-break archive (read every Monday)
│   └── losses/                             # Per-loss post-mortems with filter audit
│
├── workflow/                               # Process docs (some outdated)
│   ├── architecture.md                     # Earlier phased view (Phase 1/2/3, all now shipped)
│   └── daily-review.md
│
└── setup/.claude/                          # Project-scoped Claude Code config (settings, hooks)
```

---

## 2. High-Level System Diagram

```
                                       ┌──────────────────────────────────────┐
                                       │   J (operator, browser, dashboard)   │
                                       └─────────────┬────────────────────────┘
                                                     │ visual checks, ratification
                                                     ▼
   ┌────────────────────────┐    polls 3-5s    ┌─────────────────────────┐
   │  Dashboard (Next.js)   │ ◄────────────────│  automation/state/*.json │
   │  localhost:3000        │                  │  (canonical runtime)     │
   └────────────────────────┘                  └────────────▲─────────────┘
                                                            │ atomic write + .lastgood/ mirror
                                                            │
   ┌────────────────────────────────────────────────────────┴───────────────────────────┐
   │ Windows Task Scheduler (9 tasks)                                                   │
   │   08:00 LaunchTV  ─►  setup/launch_tv_debug.ps1                                    │
   │   08:30 Premarket ─►  setup/scripts/run-premarket.ps1                              │
   │   09:30 Heartbeat ─►  setup/scripts/run-heartbeat.ps1   (3min cadence, 6h25m)      │
   │   15:55 EodFlatten                                                                 │
   │   16:00 EodSummary                                                                 │
   │   16:30 DailyReview                                                                │
   │   Sun 18:00 WeeklyReview                                                           │
   │   (parallel set: *_Aggressive tasks for second paper account)                      │
   └────────────────────────┬───────────────────────────────────────────────────────────┘
                            │ Each task: setup/_shared.ps1 → Repair-StateFiles → Invoke-Claude
                            ▼
   ┌────────────────────────────────────────────┐    spawns      ┌──────────────────────────┐
   │ claude --print --prompt-file <prompt.md>   │───────────────►│ Claude Opus/Sonnet/Haiku │
   │ (the Gamma persona, CLAUDE.md loaded)      │                │ (inference, tool use)    │
   └────────┬─────────────────┬─────────────────┘                └──────────────────────────┘
            │                 │
   reads chart        places paper orders
            │                 │
            ▼                 ▼
   ┌────────────────┐  ┌─────────────────┐         ┌─────────────────────────────────────┐
   │ TradingView    │  │ Alpaca MCP      │ ───────►│ Alpaca Paper API (orders, fills,    │
   │ MCP (CDP 9222) │  │ (paper)         │         │  account, P&L)                       │
   └────────────────┘  └─────────────────┘         └─────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────────────────────┐
   │ Research path (offline, no live MCP):                                       │
   │                                                                             │
   │   backtest/run.py ─► lib/orchestrator → filters → pricing → simulator       │
   │                  ─► analysis/backtests/{label}/ (trades, decisions, summary)│
   │                                                                             │
   │   backtest/autoresearch/loop.py ─► proposer → run.py → decider              │
   │                                ─► autoresearch/_state/{mode}/ + watchdog    │
   └─────────────────────────────────────────────────────────────────────────────┘
```

**Key boundaries:**
- **Live engine** (`automation/prompts/heartbeat.md`) and **research engine** (`backtest/lib/`) implement the same logic in two languages. **Operating Principle 4** mandates they update together; daily backtest sync (eod-summary 8b) detects drift.
- **State files** are the universal interchange format. Prompts read state in, write decisions out. Dashboard reads the same files. Backtest reads `params.json` for canonical config.
- **No Claude → Claude direct calls.** Each scheduled task is an independent Claude invocation with fresh context.

---

## 3. Core Components

### 3.1. Frontend — Trade House Dashboard

- **Name:** Dashboard (Trade House pixel-art monitor)
- **Description:** Live read-only monitor showing position, key levels, ribbon state, agent activity, and autoresearch progress. Canvas pixel-art "trading floor" overlay with text panels. V1 = production layout (sidebar 420px + 3D canvas), V2 = alt layout (untested).
- **Technologies:** Next.js 15 (App Router) · React 19 · SWR (3-5s polling, no websocket) · TailwindCSS · Canvas 2D · TypeScript
- **Deployment:** Local dev server (`npm run dev` on port 3000). No production build / hosting. Single-user (J).
- **Data sources:** All file-based reads from `C:\Users\jackw\Desktop\42\automation\state\` and `backtest\autoresearch\_state\`.

### 3.2. Backend — Autonomous Trading Engine

#### 3.2.1. Heartbeat Engine (live)

- **Name:** Heartbeat (per-tick decisioner)
- **Description:** Every 3 min during 09:30–15:50 ET, reads chart via TradingView MCP, applies 10-filter setup detection (asymmetric bear/bull triggers), manages open position via mechanical stops/TP/runner exits. Cadence-throttled HOT/BASE/COOL based on developing-setup signal. Emits one-line action log per tick.
- **Technologies:** PowerShell wrapper (`setup/scripts/run-heartbeat.ps1`) · Claude Code CLI (`claude --print`) · Markdown prompt (`automation/prompts/heartbeat.md`) · TradingView MCP · Alpaca MCP
- **Deployment:** Windows Task Scheduler `Gamma_Heartbeat` (3-min repeat over 6h25m window)
- **Self-heal:** Pre-/post-tick `Repair-StateFiles`, 160s wall-clock timeout + tree-kill, stale-process reaper, disk-space pre-flight (≥100MB).

#### 3.2.2. Premarket / EOD / Review Prompts

- **Name:** Premarket (08:30), EodFlatten (15:55), EodSummary (16:00), DailyReview (16:30), WeeklyReview (Sun 18:00)
- **Description:** Pre/post-market non-tick prompts — level audit, bias seed, falsifiable hypothesis, EOD trade grading, hypothesis grading, rule-break tagging, drift detection (Step 8b daily backtest sync), weekly metrics rollup.
- **Technologies:** Same stack as heartbeat. Each prompt is a single markdown file.
- **Deployment:** Per-prompt Windows Scheduled Task. WakeToRun enabled.

#### 3.2.3. Backtest Engine

- **Name:** Backtest (research)
- **Description:** Replays historical SPY 5m bars through the same logic as the live heartbeat. Two simulators: synthetic Black-Scholes fills (fast) and OPRA real-fill (accurate). Outputs trades.csv, decisions.csv, summary.md, metadata.json (with content-hash reproducibility). ~3.5 min for a 16-month run.
- **Technologies:** Python 3.13 · pandas · numpy · pytest (117+ tests)
- **Deployment:** Local CLI. Driven manually or by autoresearch loop.

#### 3.2.4. Autoresearch Loop

- **Name:** Autoresearch (autonomous parameter optimization)
- **Description:** Mutates one knob (or N for multi-knob experiments) → runs train+validate backtest → KEEP if train sharpe improves and validate doesn't regress >20% AND hard gates pass (min 10 trades, WR ≥10%, W/L ≥0.80, expectancy ≥-$10). Three modes: STRICT / BALANCED / AGGRESSIVE, each with their own starting params. Five experiment scopes: lean / entries / exits / full / kitchen_sink.
- **Technologies:** Python 3.13 · same `backtest/lib/` engine.
- **Deployment:** Manual via `setup/run-modes-sweep.ps1`, or planned `Gamma_WeekendResearch` recurring task.

### 3.3. MCP Servers (Tool Layer)

#### 3.3.1. TradingView MCP
- **Read:** chart state, OHLCV, study values, levels, indicators, drawing primitives
- **Write:** chart symbol/timeframe, indicators, drawings (via `ui_evaluate` workarounds for CRUD)
- **Wire:** TradingView Desktop launched with `--remote-debugging-port=9222` (MSIX bypass via direct process creation in `launch_tv_debug.ps1`)

#### 3.3.2. Alpaca MCP (paper)
- **Read:** account info, positions, P&L, option chain, Greeks, fills, calendar, day-trade count
- **Write:** place_option_order, cancel_order, close_position (paper account only — `mode.json` gates this)
- **Wire:** `uvx alpaca-mcp-server` v2.0.1, paper API keys in `~/.claude.json` (per-project MCP config)

---

## 4. Data Stores

### 4.1. Runtime State (canonical)

- **Name:** `automation/state/`
- **Type:** Filesystem (JSON + JSONL on NTFS)
- **Purpose:** Single source of truth for runtime values consumed by every prompt and the dashboard. Chosen over a database because (a) trivially observable, (b) atomically restorable from `.lastgood/`, (c) git-diffable for postmortem.
- **Key files:**
  - `params.json` — canonical rule_version + stops + sizing + gates (drift = kill-switch)
  - `mode.json` — live-paper | dry-run | paused
  - `current-position.json` — open position state (null = flat)
  - `today-bias.json` — bias + levels + falsifiable hypothesis
  - `key-levels.json` — schema v3 strength-scored levels
  - `circuit-breaker.json` — daily-loss flag
  - `loop-state.json` — heartbeat-tick context (session, vix, ribbon, htf)
  - `news.json` — macro calendar
  - `shadow-version.json` — A/B test candidate
  - `decisions.jsonl` — per-tick decision log (graded post-hoc)
  - `hypothesis-grades.jsonl` — per-prediction grades
  - `rule-breaks.jsonl` — cost-tagged violations
  - `process-compliance.jsonl` — daily clean/dirty + leading indicators
  - `backtest-drift.json` — EOD drift severity flag
- **Backups:** `automation/state/.lastgood/` mirrors every `*.json` after each successful validate. Restored automatically by `Repair-StateFiles` on parse failure.

### 4.2. Historical Market Data (research)

- **Name:** `backtest/data/`
- **Type:** Filesystem (CSV on NTFS)
- **Purpose:** Bar data for offline replay and parameter optimization.
- **Files:** `spy_5m_2025-01-01_2026-05-07.csv` (master, 30,389 bars), matching VIX bars, `options/` OPRA cache (per ticker-date-strike-type).

### 4.3. Trade Journal (system of record)

- **Name:** `journal/`
- **Type:** Filesystem (Markdown + CSV on NTFS)
- **Purpose:** Human-readable system of record per **Rule 8** ("If it's not in the journal, it didn't happen").
- **Files:**
  - `YYYY-MM-DD.md` — daily entries (pre-market, every trade, EOD)
  - `trades.csv` — 41-column structured trade log
  - `mistakes.md` — rule-break archive (read every Monday)
  - `losses/` — per-loss post-mortems with filter-audit checklist

### 4.4. Research Outputs

- **Name:** `analysis/`
- **Type:** Filesystem (CSV + Markdown + JSON)
- **Purpose:** Backtest results, weekly reviews, shadow-mode scorecards.
- **Files:** `backtests/{label}/{trades.csv, decisions.csv, summary.md, metadata.json}` · `weekly-reviews/YYYY-Www.md` · `shadow-scorecards/{date}.jsonl`

### 4.5. Autoresearch State

- **Name:** `backtest/autoresearch/_state/`
- **Type:** Filesystem (JSON + JSONL)
- **Purpose:** Resumable optimization runs across modes.
- **Files:** `{strict,balanced,aggressive}/state.json` (current params + baselines + iter count) · `{mode}/history.jsonl` (one record per iteration) · `watchdog_report.{md,json}`

---

## 5. External Integrations / APIs

| Service | Purpose | Integration |
|---|---|---|
| **TradingView Desktop** | Read chart state, levels, indicators, candles | Chrome DevTools Protocol on port 9222, accessed via TradingView MCP |
| **Alpaca Paper API** | Account state, option chain, Greeks, place/cancel/close paper orders | REST via `alpaca-mcp-server` (v2.0.1) |
| **Macro calendar source** | FOMC / CPI / NFP scheduling for hard-veto windows | Daily WebFetch in premarket Step 1b (alpaca.markets/calendar + manual refresh) |
| **Anthropic API** | Claude inference (Opus/Sonnet/Haiku) | `claude --print` via Claude Code CLI |

---

## 6. Deployment & Infrastructure

- **Cloud Provider:** None (single-machine local deployment)
- **Host:** Windows 11 Home (J's desktop), 24H2
- **Runtime:** Claude Code CLI (host) · Python 3.13 (backtest) · Node 18+ (dashboard) · PowerShell 5.1 (orchestration)
- **Scheduler:** Windows Task Scheduler (9 `Gamma_*` tasks). WakeToRun enabled — machine wakes from sleep to fire.
- **CI/CD:** None. Changes are made, tested locally via `pytest backtest/tests/`, daily backtest sync detects live/research drift.
- **Monitoring & Logging:**
  - Per-task plain-text logs at `automation/state/logs/<task>-YYYY-MM-DD.log`
  - Dashboard polls state files every 3-5s
  - Per-tick decisions written to `decisions.jsonl` (graded post-hoc EOD)
  - Watchdog report regenerated on every autoresearch iteration

---

## 7. Security Considerations

- **Authentication:** Alpaca paper API keys stored in `~/.claude.json` (per-project MCP config), not in repo. Real-money keys not provisioned (paper-only mode).
- **Authorization:** Single-user system. `mode.json` gates live order placement (`live-paper` | `dry-run` | `paused`). `dry-run` blocks all `place_option_order` calls.
- **Data Encryption:** TLS for Alpaca API calls. State files unencrypted at rest (single-user local machine).
- **Kill switches (multi-layer):**
  - `circuit-breaker.json` — daily loss ≥50% of SOD equity → all entries blocked
  - `mode.json paused` — manual emergency pause
  - `params.json#rule_version` drift vs prompt's `RULE_VERSION_EXPECTED` → kill-switch (premarket Step 1a)
  - `backtest-drift.json severity:high` → kill-switch (premarket Step 1d)
- **Operational safety:**
  - `Repair-StateFiles` validates JSON pre/post every prompt
  - 160s wall-clock timeout per heartbeat tick + tree-kill on overrun
  - Disk-space pre-flight (<100MB free → abort)
  - First-entry-after-stop blocked by `params.json` flag (no second entry on same setup that already lost today)

---

## 8. Development & Testing Environment

- **Local Setup:**
  - Clone repo to `C:\Users\jackw\Desktop\42`
  - `cd backtest && python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt`
  - `cd dashboard && npm install && npm run dev`
  - `setup\install-tasks.ps1` registers Windows scheduled tasks
  - Configure MCPs in `~/.claude.json` (TradingView + Alpaca paper keys)
- **Testing:**
  - `pytest backtest/tests/ -v` (117+ tests, ~2417 LOC)
  - `pytest -m unit` / `-m integration` for filtered runs
  - **Live verification:** daily backtest sync (eod-summary 8b) compares live `decisions.jsonl` vs simulator output on same bars; >30% divergence → kill-switch next morning
- **Code Quality:**
  - Python: ruff + black + isort (per `~/.claude/rules/python/`)
  - TypeScript: dashboard inherits Next.js + ESLint defaults
  - PowerShell: no formal linter (intentional — surface area is small, hand-reviewed)

---

## 9. Future Considerations / Roadmap

- **Self-healing gaps to close** (from 2026-05-09 audit):
  1. **Slippage feedback loop** — track marked-price vs actual-fill divergence; surface trades where bid-ask slip ate >X% of edge.
  2. **Macro-regime tagging in predictions** — segment hypothesis-grades by VIX band / event proximity for cross-day pattern mining.
  3. **Automated filter-effectiveness mining** — Section 7i loss-walk template exists, but aggregation over weeks is manual.
- **Live deployment** — paper → real-money transition gated on (a) ≥20 trades, (b) WR ≥45%, (c) positive expectancy, (d) ≤2 rule breaks (per CLAUDE.md account-context block).
- **Optimization-target diversification** — current loop optimizes train sharpe; weekend research will add `--objective {sharpe_validate, pnl_validate, expectancy_validate}` to find robust winners.
- **Out-of-sample 2024 holdout** — extend `data/` back to 2024 for walk-forward overfit detection.
- **Webhook-driven setup detection** — TradingView alerts → local server → Claude session (Phase 3 in `markdown/specs/workflow-architecture.md`). Not yet built; current 3-min cadence is sufficient.
- **Dashboard upgrades** for weekend research:
  - `/api/equity-curve` endpoint
  - `/api/sweep-progress` real-time progress bar
  - Parameter-genealogy view (which iteration drifted which knob)

---

## 10. Project Identification

- **Project Name:** Project Gamma (call sign "Gamma")
- **Repository:** Local workspace at `C:\Users\jackw\Desktop\42` (not version-controlled — local-only by design)
- **Primary Contact:** J (jack.watergun@gmail.com), single operator
- **Mission:** Autonomous 0DTE SPY directional options trading. Paper account first; real-money after gating thresholds clear.
- **Date of Last Update:** 2026-05-09

---

## 11. Glossary / Acronyms

- **0DTE** — Zero Days to Expiration. Options expiring same day.
- **CDP** — Chrome DevTools Protocol. Used to drive TradingView Desktop.
- **CORE / SECONDARY / NOISE_PRONE** — Autoresearch knob tiers (config.py).
- **EOD** — End of Day.
- **ET** — US Eastern Time. All trading hours expressed in ET.
- **HOT / BASE / COOL** — Heartbeat cadence modes (every tick / every 3rd / every 4th).
- **HTF** — Higher Time Frame (15-min vs 5-min primary).
- **ITM-2** — In-The-Money by 2 strikes (current default strike offset).
- **JANUS / Darwin** — Built-but-unwired regime/filter feedback subsystems (referenced in audit; not in active flow yet).
- **KEEP / REVERT** — Autoresearch decisions on a parameter mutation.
- **MCP** — Model Context Protocol. Wires Claude to external tools (TradingView, Alpaca).
- **MSIX** — Microsoft Store package format. Why TradingView normal launch strips CDP flag.
- **OPRA** — Options Price Reporting Authority. Source of real option bars in `simulator_real.py`.
- **PDH / PDL** — Prior Day High / Low.
- **PDT** — Pattern Day Trader. SEC rule limiting day trades on accounts <$25K.
- **RTH** — Regular Trading Hours (09:30–16:00 ET).
- **Saty Pivot Ribbon** — Custom EMA-based trend indicator (Fast/Pivot/Slow).
- **Shadow mode** — A/B test where candidate rule version emits parallel decisions, scored EOD.
- **SOD** — Start of Day equity (snapshot at 09:30 ET for daily-loss kill switch math).
- **Sub-window stability** — A backtest is "sub-window stable" if both halves of the validation window pass independent thresholds (4-of-4 PASS).
- **TP1** — Take Profit 1. First scale-out target.
- **VWAP / AVWAP** — (Anchored) Volume Weighted Average Price.
- **v14** — Current ratified rule version (premium stop -8%, ITM-2, asymmetric trigger bear≥1 / bull≥2, 10:00 ET entry gate, 14:00–15:00 ET no-trade window, quality-tiered sizing).
