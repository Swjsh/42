# Architecture Overview — Project Gamma

> Living cold-start doc: how the rig is wired **today**, for an agent who just walked in. When wiring changes, update this in the same commit. Canonical doc index: [`markdown/README.md`](../README.md). Soul file: [`CLAUDE.md`](../../CLAUDE.md).
>
> **Last refreshed: 2026-06-20.** (Prior content was a 2026-05-09 snapshot — superseded.)

---

## 1. Project Structure

```
C:\Users\jackw\Desktop\42\                  # repo root — IS a git repo (branch: main)
├── CLAUDE.md                               # Soul file. Mission, 10 rules, operating principles. Read first.
├── CHANGELOG.md                            # Doctrine evolution log (append-only history).
├── README.md                               # Quick-start orientation.
│
├── markdown/                               # ALL human-authored docs (consolidated 2026-06-20)
│   ├── README.md                           #   folder index / filing rule
│   ├── 0dte/                               #   SPY strategy: playbook, risk-rules, key-levels, J-edge, patterns
│   ├── futures/                            #   MNQ/MES specs, margin, sessions
│   ├── research/                           #   backtests, studies, swarm benchmarks, R&D findings
│   ├── planning/                           #   roadmaps, checklists, gameplans, daily-review
│   ├── doctrine/                           #   LESSONS-LEARNED, doctrine archive, edge doctrine
│   ├── specs/                              #   engine + wiring specs (THIS file lives here)
│   ├── audits/                             #   point-in-time health checks, postmortems
│   └── infra/                              #   setup, MCP install, KITCHEN-SPEC, SKILLS-CATALOG
│
├── automation/                             # The autonomous engine
│   ├── prompts/                            #   markdown prompts run by scheduled tasks
│   │   ├── premarket.md                    #     08:30 ET — level audit, bias, hypothesis, drift gate
│   │   ├── heartbeat.md                    #     09:30–15:55 ET — per-tick decisioning (Safe)
│   │   ├── aggressive/heartbeat.md         #     same, Bold account
│   │   ├── conductor.md                    #     the "Gamma drives" after-hours autonomy loop
│   │   ├── eod-*.md / weekly-review.md     #     post-market grading, drift sync, rollups
│   │   └── heartbeat-v14-prod-backup.md    #     revert target
│   ├── state/                              #   runtime state (JSON + JSONL) — canonical interchange
│   │   ├── params.json                     #     CANONICAL config (Safe); aggressive/params.json (Bold)
│   │   ├── current-position.json, loop-state.json, circuit-breaker.json, today-bias.json, news.json …
│   │   ├── decisions.jsonl, hypothesis-grades.jsonl, rule-breaks.jsonl …
│   │   ├── SCHEDULED-TASKS.md              #     canonical scheduled-task registry
│   │   ├── claude-md-backups/              #     gitignored CLAUDE.md pre-trim backups
│   │   └── .lastgood/                      #     atomic JSON recovery snapshots
│   └── overnight/STATUS.md                 #   the LIVE status file (Known-broken board)
│
├── backtest/                               # Python research engine (mirrors live logic — OP-4)
│   ├── run.py                              #   main CLI
│   ├── lib/                                #   orchestrator, filters, ribbon, simulator(_real), pricing,
│   │                                       #   levels, risk_gate, shadow, repro, engine/gex_regime, watchers/
│   ├── autoresearch/                       #   grinders, evaluators, eod_deep pipeline, daily_status, audits
│   │   └── _state/                         #   resumable optimization runs
│   ├── tests/                              #   pytest suite + graduated guards (fast/slow split)
│   └── .venv/                              #   Python 3.13 venv (pandas/pytest live HERE, not system python)
│
├── strategy/
│   └── candidates/                         #   The Kitchen's DRAFT output (machine-generated, ~900 files)
│
├── analysis/                               # research outputs: backtests/, recommendations/, eod/, gym/, daily-brief/
├── journal/                                # system of record: YYYY-MM-DD.md, trades.csv, mistakes.md, losses/
├── crypto/                                 # gym-only chart-reading validation harness (NOT traded)
├── dashboard/                              # Trade House pixel-art UI (Next.js 15 / React 19, localhost:3000)
├── setup/                                  # PowerShell orchestration (_shared.ps1, launchers, install-*.ps1, scripts/)
│
├── .claude/                               # Claude Code config — agents/ + skills/ loaded BY PATH (don't move)
│
└── docs/  doctrine/  workflow/             # TOMBSTONED legacy dirs — redirect READMEs only; never write docs here
                                            # (docs/ also retains WeBull History/*.csv trade data, read by code)
```

---

## 2. High-Level System Diagram

```
                         ┌─────────────────────────────────────────────┐
                         │  J (operator) — Dashboard + Discord (approve/revoke) │
                         └───────────────┬─────────────────────────────┘
                                         │ visual checks; REVOKE-only on shipped edges
                                         ▼
   ┌────────────────────┐  polls 3-5s  ┌──────────────────────────┐
   │ Dashboard (Next.js)│ ◄────────────│ automation/state/*.json   │  atomic write + .lastgood/ mirror
   │ localhost:3000     │              │ (canonical runtime state) │ ◄──────────────────────────┐
   └────────────────────┘              └──────────────────────────┘                            │
                                                                                                │
   ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
   │ Windows Task Scheduler  (~27 active Gamma_* tasks; canonical list: SCHEDULED-TASKS.md) │    │
   │  08:00 LaunchTV · 08:30 Premarket · 09:30–15:55 Heartbeat + Heartbeat_Aggressive       │    │
   │  15:55 EodFlatten (x2) · EOD/weekly pipelines · 18:00–07:00 Conductor (after-hours)     │    │
   │  24/7 KitchenDaemonKeepalive · hourly KitchenSeeder · 2h KitchenReviewer · guards/audits │   │
   └───────────────┬─────────────────────────────────────────────────────────────────────────┘  │
                   │ each task: setup/_shared.ps1 → Repair-StateFiles → claude --print (Max sub)  │
                   ▼                                                                               │
   ┌───────────────────────────────┐   reads chart        places paper orders                     │
   │ Claude (Opus/Sonnet/Haiku)    │──────────┬──────────────────┬──────────────────────────────┘
   │ Gamma persona, CLAUDE.md      │          ▼                  ▼
   └───────────────────────────────┘  ┌──────────────┐  ┌─────────────────────────────────────────┐
                                       │ TradingView  │  │ Alpaca MCP  ── alpaca → Safe-2          │
                                       │ MCP (CDP 9222)│  │  ── alpaca_aggressive → Risky-2 (paper) │
                                       └──────────────┘  └─────────────────────────────────────────┘

   Research / autonomy paths (offline, $0 or free-tier):
     backtest/run.py ─► lib/orchestrator → filters → pricing → simulator(_real) ─► analysis/backtests/{label}/
     The Kitchen ─► free-tier model ladder (Nemotron→DeepSeek→MiniMax) ─► strategy/candidates/ (DRAFTs)
     Conductor ─► reads health+queue, fans out ONE specialist persona/fire, ships only if auto-ratify gate clears
     Fleet executor ─► one perception/tick → N frozen configs across paper accounts (champion/challenger)
```

**Key boundaries**
- **Live engine** (`automation/prompts/heartbeat.md`) and **research engine** (`backtest/lib/`) implement the same logic; **OP-4** mandates they move together (gamma-sync skill + pytest catch drift).
- **State files are the universal interchange.** Prompts read state in, write decisions out; dashboard reads the same files; backtest reads `params.json`.
- **No Claude→Claude direct calls in production ticks** — each scheduled task is an independent invocation with fresh context. (The Conductor *does* fan out specialist sub-agents during after-hours work.)
- **Heartbeat runs on the Max subscription (shared rate-limit pool).** A market-hours interactive session can starve ticks → **discipline: no interactive sessions 09:30–15:55 ET** is the only guard.

---

## 3. Core Components

### 3.1 Frontend — Trade House Dashboard
Next.js 15 (App Router) · React 19 · SWR (3-5s polling) · Tailwind · Canvas pixel-art. Read-only monitor of position, levels, ribbon, agent activity. File-based reads from `automation/state/`. `npm run dev` on :3000, single-user.

### 3.2 Backend — Autonomous Trading Engine
- **Heartbeat (live, x2 accounts):** every ~3 min in RTH, reads chart via TV MCP, applies the v15 setup rubric + `risk_gate`, manages exits (chart-stop primary on Safe). Cadence-throttled HOT/BASE/COOL (up to 127 ticks/day). Self-heal: `Repair-StateFiles`, wall-clock timeout + tree-kill, stale-process reaper, disk pre-flight.
- **Premarket / EOD / Review prompts:** level audit, bias + falsifiable hypothesis, EOD grading, hypothesis grading, rule-break tagging, daily backtest drift sync, weekly rollup + auto-ratify scorecards (OP-11 Karpathy loop).
- **Backtest engine:** replays SPY 5m bars through the same logic; synthetic (Black-Scholes) + OPRA real-fill simulators; content-hash reproducibility (`repro.py`). **Real-fills is the only WR authority; BS-sim is ranking-only.**
- **The Kitchen (24/7 R&D):** `kitchen_daemon.py` + free-tier model ladder writes DRAFT candidates to `strategy/candidates/`; seeder brainstorms, reviewer triages. $3/day paid cap. Never touches live doctrine/orders.
- **Conductor ("Gamma drives"):** after-hours hourly loop (`conductor.md`); each fire picks ONE highest-value ready task, fans out the right specialist persona, validates (gym/tests), SHIPS only if the auto-ratify gate clears, else proposes. Fail-open, propose-only on doctrine/params/orders.
- **Fleet executor (champion/challenger):** one perception per tick → deterministic fan-out of N frozen configs across validated paper accounts; same `risk_gate.check_order` decides.
- **Watcher fleet:** ~28 detectors read each tick (WATCH_ONLY) via the unified heartbeat layer; promotion-gated before any go live.

### 3.3 Agents & Skills (`.claude/`, loaded by path)
Personas: `gamma` (conductor), `pilot` (live trader), `scout`, `analyst`, `chef`, `treasurer`, `coach`, `lesson-author`, `skill-author`, `validator-author`. Skills: gym-session, preflight-gate/connectivity-gate, context-leanness, heartbeat/-tick-audit, gamma-sync, log-trade, etc. (catalog: `markdown/infra/SKILLS-CATALOG.md`).

### 3.4 MCP Servers (tool layer)
- **TradingView MCP** — chart/OHLCV/study/levels read; chart control + drawings write. TradingView Desktop launched with `--remote-debugging-port=9222` (MSIX bypass in `launch_tv_debug.ps1`).
- **Alpaca MCP (paper)** — two servers: `alpaca` → Gamma-Safe-2, `alpaca_aggressive` → Gamma-Risky-2. Account/chain/Greeks/fills read; place/cancel/close write (paper only).
- **Discord** — proactive presence + approve/revoke bus.
- **Free-tier OpenRouter** — Kitchen ladder + `swarm_consult.py` adversarial review ($0).

---

## 4. Data Stores (all filesystem on NTFS — observable, git-diffable, atomically restorable)

| Store | Purpose |
|---|---|
| `automation/state/` | Canonical runtime: `params.json` (Safe) + `aggressive/params.json` (Bold), position, loop, circuit-breaker, ledgers (`decisions.jsonl` …). `.lastgood/` auto-restore. |
| `journal/` | System of record (Rule 8): daily MD, `trades.csv` (41 cols), `mistakes.md`, `losses/`. |
| `backtest/data/` | Historical SPY/VIX 5m bars + OPRA option cache. |
| `analysis/` | Backtest runs, `recommendations/{rule_id}.json` A/B scorecards, EOD digests, gym scorecards, daily briefs. |
| `strategy/candidates/` | Kitchen DRAFT output (machine-generated). |
| `markdown/` | All human docs (this consolidation). |

---

## 5. External Integrations

| Service | Purpose | Wire |
|---|---|---|
| TradingView Desktop | chart/levels/indicators read | CDP :9222 via TV MCP |
| Alpaca Paper API (x2) | account/chain/orders, both accounts | `alpaca-mcp-server`, keys in `~/.claude.json` |
| Anthropic (Max sub) | Claude inference, all tasks | `claude --print` (shared pool — see discipline note) |
| OpenRouter free tier | Kitchen ladder + swarm review | $0 |
| Discord | presence + approve/revoke | discord MCP + bridge daemons |

---

## 6. Deployment & Infrastructure
- **Host:** single Windows 11 machine (J's desktop). No cloud, no CI.
- **Runtimes:** Claude Code CLI · Python 3.13 (`backtest/.venv` — pandas/pytest live there, NOT system python) · Node 18+ (dashboard) · PowerShell 5.1 (target 5.1 syntax).
- **Scheduler:** Windows Task Scheduler, ~27 active `Gamma_*` tasks (WakeToRun). Canonical registry: `automation/state/SCHEDULED-TASKS.md`. Rig is **Mountain time** — tasks scheduled at ET-converted-to-local.
- **Headless spawn pattern:** wscript → `run_exe_hidden.vbs` → `pythonw` (CREATE_NO_WINDOW) to avoid console flashes.
- **Self-heal:** `_shared.ps1#Repair-StateFiles` validates state JSON pre/post each fire; restores from `.lastgood/`.

## 7. Security & Safety
- **Paper-only.** Alpaca keys in `~/.claude.json` (gitignored); a fleet `secrets.json` is gitignored. Real-money keys not provisioned. (Open hygiene item: a hardcoded paper key in a few `setup/scripts/*.py` to migrate to the secrets mechanism.)
- **Kill switches (per-account, isolated):** Safe −30% / Bold −50% of SOD equity → entries blocked for that account only. `params.json#rule_version` drift vs prompt = kill-switch. `backtest-drift severity:high` = premarket gate.
- **Guards FAIL OPEN** — no automated process may lock out J's interactive session (OP-32 scar).

## 8. Development & Testing
- `pytest backtest/tests/` + **graduated guards** (fast per-edit hook + nightly `-m slow`). Gym: 42+ validators + chart-reading replay ($0).
- Live↔research parity: daily backtest sync + `gamma-sync` skill on any rule change.
- Ratify autonomously when: OOS positive AND WF ≥ 0.70 AND sub-window stable AND anchor no-regression AND A/B scorecard filed (OP-11/OP-22). J's role = REVOKE, not approve.

## 9. Roadmap (current)
- Fleet executor M2 (live REST placement + heartbeat shared-signal emit + MES arm).
- Shared-decision-library refactor (unify `params ↔ heartbeat ↔ filters`) — spec in `markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md`.
- Conductor phases (model routing Haiku/Opus; Discord approve/revoke bus).
- Wire GEX regime tag into premarket/heartbeat (capture is live; consumption is a separate proposal).

## 10. Project Identification
- **Project:** Project Gamma (call sign "Gamma"). **Operator:** J (jack.watergun@gmail.com), single user.
- **Instruments:** 0DTE SPY options (primary) + futures MNQ/MES (TT sandbox, heartbeat disabled for cost). Crypto = gym-only, never traded.
- **Accounts (paper):** Gamma-Safe-2 `PA3S2PYAS2WQ` (~$2K, conservative) · Gamma-Risky-2 `PA33W2KUAT40` (~$1.67K, aggressive).
- **Strategy:** rule version **v15** (live 2026-05-13); chart-stops-primary on Safe (2026-06-18); per-tier strikes (OTM-3 $1K / OTM-2 $2-10K / OTM-1 $10-25K / ITM-2 $25K+); chandelier trailing; 09:35 ET entry gate.
- **Date of Last Update:** 2026-06-20.

## 11. Glossary
- **0DTE** — zero days to expiration. **ET / RTH** — Eastern time / regular hours (09:30–16:00).
- **v15** — current ratified rule version (asymmetric stops, per-tier strikes, chandelier trailing, 09:35 gate).
- **Chart-stop-primary** — chart-level/ribbon-flip/chandelier are primary invalidation; premium stop demoted to a −50% catastrophe cap (Safe; Bold keeps tight stop).
- **The Kitchen** — 24/7 free-tier R&D loop producing DRAFT candidates.
- **Conductor** — the after-hours "Gamma drives" autonomy loop (one bounded task per fire).
- **Fleet (champion/challenger)** — N frozen configs run in parallel across paper accounts off one perception.
- **risk_gate** — single risk-rule implementation (`backtest/lib/risk_gate.check_order`) used live + backtest.
- **OP-4 / OP-11 / OP-16 / OP-22 / OP-25** — operating principles: live/backtest parity · Karpathy eval-first loop · J-edge primacy · always-improving cadence · self-correcting lessons.
- **edge_capture / J-edge** — score of engine P&L on J's source-of-truth winning/losing days.
- **Saty Pivot Ribbon** — EMA trend indicator (Fast/Pivot/Slow). **OPRA** — real option bar source. **CDP** — Chrome DevTools Protocol (drives TV). **MCP** — Model Context Protocol.
- **HOT/BASE/COOL** — heartbeat cadence modes. **PDT** — pattern-day-trader rule (<$25K).
