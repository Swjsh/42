# Architecture Overview — Project Gamma

> Living cold-start doc: how the rig is wired **today**, for an agent who just walked in. When wiring changes, update this in the same commit. Canonical doc index: [`markdown/README.md`](../README.md). Soul file: [`CLAUDE.md`](../../CLAUDE.md).
>
> **Last refreshed: 2026-09-02.** This doc had gone stale since 2026-06-25 and contained **zero** mentions of `fleet_live`, `fleet_executor`, `exit_manager`, `safe-3`, `dead_mans_switch`, or `tight-ladder` — it silently omitted an entire, separate execution path. New **§3.2a** documents that path end-to-end (launch chain, signal flow, order shape, halts, the dead-man's switch, EOD/early-close flatten) and its honestly-disclosed gaps (fleet's kill switch is a live per-tick recompute, not a durable latch; fleet PDT enforcement defaults off). Also corrected here (verified against live code, not comments): `heartbeat_core.py` is **ARMED** (`GAMMA_CORE_ARMED=1` since 2026-06-25, exits managed since 2026-06-26 — the prior "Status: DISARMED" line in §3.2 was stale) and the `alpaca_aggressive` MCP server maps to **Bold-2**, not "Risky-2" (§2, §3.4, §5 — the account was renamed; `.mcp.json`, not `~/.claude.json`, is the live credential store, per CLAUDE.md's 2026-07-09 correction). Prior content was a 2026-06-25 snapshot (itself replacing 2026-06-20).

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
   │ Windows Task Scheduler  (148 registered tasks; SCHEDULED-TASKS.md is canonical)         │    │
   │  08:00 LaunchTV · 08:30 Premarket · 09:30–15:55 SightBeacon(1m) + HeartbeatCore(1m,ARMED)│    │
   │  09:31–16:01 FleetExecutor(1m, +1m offset) · 09:32–15:58 DeadMansSwitch(2m)             │    │
   │  [LLM Heartbeat + Heartbeat_Aggressive RETIRED 2026-06-25 — disabled, kept as fallback] │    │
   │  12:32 EodFlattenEarlyClose · 15:52 EodFlattenCore · 15:55 EodFlatten(LLM) · weekly pipes│    │
   │  18:00–07:00 Conductor (after-hours) · 24/7 KitchenDaemonKeepalive · guards/audits       │    │
   └───────────────┬─────────────────────────────────────────────────────────────────────────┘    │
                   │ each task: setup/_shared.ps1 → Repair-StateFiles → claude --print (Max sub)  │
                   ▼                                                                                │
   ┌────────────────────────────────┐   reads chart        places paper orders                      │
   │ Claude (Opus/Sonnet/Haiku)    │──────────┬──────────────────┬───────────────────────────────┘
   │ Gamma persona, CLAUDE.md      │          ▼                  ▼
   └────────────────────────────────┘  ┌──────────────┐  ┌─────────────────────────────────────────┐
                                        │ TradingView  │  │ Alpaca MCP — alpaca → Safe-2           │
                                        │ MCP (CDP 9222)│  │  — alpaca_aggressive → Bold-2 (paper)  │
                                        └──────────────┘  │  + fleet_broker direct REST (safe-3,     │
                                                           │    risky-1 — own secrets.json, no MCP)  │
                                                           └─────────────────────────────────────────┘

   TWO SEPARATE EXECUTION ENGINES place real paper orders — this is the single most important
   fact for a newcomer, and the thing the pre-2026-09-02 version of this doc omitted entirely.

   Never-blind sight + deterministic CORE trade path (arms: safe-2, bold-2 — NEW 2026-06-25, ARMED):
     Sight beacon → direct Alpaca REST + yfinance (no MCP/CDP) → sight-beacon.json
       → heartbeat_core (pure Python: engine_cli score+gates → 2 free-model veto → risk_gate
          → REST bracket-then-simple-limit placement, exit_manager scale-out; GAMMA_CORE_ARMED=1)
       → ALSO writes core-decisions.jsonl, the "one perception" the fleet path below reads

   FLEET execution path (arms: safe-3, risky-1 — a SEPARATE process; see NEW section 3.2a below):
     core-decisions.jsonl → build_shared_signal.py → shared-signal.json
       → fleet_live.py → fleet_executor.py (per-arm sizing/admission, gate/sizing profile)
       → exit_actuator.py / exit_manager.py (TP1 / runner / trail / structure-stop / -50% cap)
       → fleet_broker.py (the only broker surface fleet arms use — direct REST, own creds)

   Research / autonomy paths (offline, $0 or free-tier):
     backtest/run.py → lib/orchestrator → filters → pricing → simulator(_real) → analysis/backtests/{label}/
     The Kitchen → free-tier model ladder (Nemotron→DeepSeek→MiniMax) → strategy/candidates/ (DRAFTs)
     Conductor → reads health+queue, fans out ONE specialist persona/fire, ships only if auto-ratify gate clears
```

**Key boundaries**
- **There are TWO execution engines, not one — `heartbeat_core.py` drives ONLY safe-2 and bold-2.** Every other actively-trading arm (today: safe-3, risky-1) runs through the entirely separate fleet path (`fleet_live.py` → `fleet_executor.py` → `exit_manager.py`/`exit_actuator.py` → `fleet_broker.py`), on its own scheduled task, with its own per-arm state files and circuit breaker. See §3.2a — this omission was the reason for this refresh.
- **Live engine and research engine now share ONE codebase.** The deterministic core (`heartbeat_core.py`) calls the backtest's own `engine_cli` (`score_bar` + 15 gates) directly, so live and backtest decisions are byte-identical *by construction* (101 parity tests) — the prose-vs-code drift that OP-4's gamma-sync discipline guarded against (for the retired `heartbeat.md`) is now structurally impossible on the decision path.
- **State files are the universal interchange.** Prompts read state in, write decisions out; dashboard reads the same files; backtest reads `params.json`.
- **No Claude→Claude direct calls in production ticks** — each scheduled task is an independent invocation with fresh context. (The Conductor *does* fan out specialist sub-agents during after-hours work.)
- **Heartbeat runs on the Max subscription (shared rate-limit pool).** A market-hours interactive session can starve ticks → **discipline: no interactive sessions 09:30–15:55 ET** is the only guard. (The fleet path is pure Python/REST — no Max-pool exposure.)

---

## 3. Core Components

### 3.1 Frontend — Trade House Dashboard
Next.js 15 (App Router) · React 19 · SWR (3-5s polling) · Tailwind · Canvas pixel-art. Read-only monitor of position, levels, ribbon, agent activity. File-based reads from `automation/state/`. `npm run dev` on :3000, single-user.

### 3.2 Backend — Autonomous Trading Engine
- **Sight beacon (never-blind eye, NEW 2026-06-25):** `setup/scripts/sight_beacon.py` (`Gamma_SightBeacon`, every 1 min RTH) reads SPY 5m bars via DIRECT Alpaca REST + yfinance — **no MCP, no CDP, no Max pool**, so it cannot be blocked or starved. Computes the ribbon (`backtest/lib/ribbon.py`), writes `automation/state/sight-beacon.json`, and drives the fleet `shared-signal.json`. This is the eye every other engine reads when TV/Alpaca MCP fail (heartbeat Layer-1b + fleet fallback). Why it exists: TV-over-CDP and the uvx Alpaca MCP could die together in-process and leave the engine blind ~daily.
- **Deterministic decision core (NEW 2026-06-25, replacing the LLM heartbeat):** `setup/scripts/heartbeat_core.py` (`Gamma_HeartbeatCore`, every 1 min RTH — trades ONLY `safe-2` and `bold-2`, the two `mcp_heartbeat` arms; see §3.2a for every other arm) is pure Python — reads the beacon, marshals the market state to `backtest/lib/engine/engine_cli.py` (the SAME `score_bar` + 15 entry gates the backtest uses, proven byte-identical by 101 parity tests), gets a veto from 2 free models (`swarm_client`), sizes via `risk_gate`, places an order via direct Alpaca REST (`fleet_broker`) as a **single marketable simple limit — no bracket is attempted at all** since FIX2 (2026-07-01): Alpaca NEVER accepts bracket/oto for options (42210000), and the old `place_bracket(simple_fallback=...)` ladder burned two guaranteed 422s on every entry. ⚠️ A simple entry has **no broker-side stop**, so it is placed ONLY when `CORE_MANAGES_EXITS=1` and `exit_manager` owns TP/stop — otherwise it refuses (`PLACE_FAIL`). The fleet path is identical (§3.2a "order shape"). **Note both modules' own top docstrings still say `place_bracket`; they are stale — the code at `heartbeat_core.py:2848` and `fleet_live.py:621` is authoritative.**. No LLM / MCP / CDP on the hot path → cannot crash the way the LLM heartbeat did. **Status: ARMED** — `run-heartbeat-core.ps1` sets `GAMMA_CORE_ARMED=1` (armed 2026-06-25, once the historical replay (`backtest/replay_heartbeat_core.py`) cleared its own gate: score parity 98.0%, entry fidelity 5/5 matched/0 extra/0 missed) and `GAMMA_CORE_MANAGES_EXITS=1` (applied 2026-06-26 — the validated partial-TP1/runner/profit-lock `exit_manager` is live on this path, not just a basic bracket). **Correction (2026-09-02): this doc previously said "Status: DISARMED" — that was stale; verified against the live launcher script, not the module's own default-off comment, which describes the safety fallback, not production state.**
- **LLM heartbeat (RETIRED 2026-06-25):** `Gamma_Heartbeat` + `Gamma_Heartbeat_Aggressive` (`automation/prompts/heartbeat.md`, Haiku reading TV MCP, ~3 min cadence) are **disabled** — they ran see→decide→act on the fragile LLM + MCP + CDP + 97 KB-prompt substrate and crashed ~daily (confabulated 401s from stale flags, skipped ledger writes). Kept on disk as a fallback; not scheduled. The beacon's Layer-1b fallback + beacon-aware kill-switch were retro-fitted into `heartbeat.md` before retirement.
- **Premarket / EOD / Review prompts:** level audit, bias + falsifiable hypothesis, EOD grading, hypothesis grading, rule-break tagging, daily backtest drift sync, weekly rollup + auto-ratify scorecards (OP-11 Karpathy loop).
- **Backtest engine:** replays SPY 5m bars through the same logic; synthetic (Black-Scholes) + OPRA real-fill simulators; content-hash reproducibility (`repro.py`). **Real-fills is the only WR authority; BS-sim is ranking-only.**
- **The Kitchen (24/7 R&D):** `kitchen_daemon.py` + free-tier model ladder writes DRAFT candidates to `strategy/candidates/`; seeder brainstorms, reviewer triages. $3/day paid cap. Never touches live doctrine/orders.
- **Conductor ("Gamma drives"):** after-hours hourly loop (`conductor.md`); each fire picks ONE highest-value ready task, fans out the right specialist persona, validates (gym/tests), SHIPS only if the auto-ratify gate clears, else proposes. Fail-open, propose-only on doctrine/params/orders.
- **Fleet executor (champion/challenger):** one perception per tick → deterministic fan-out of N frozen configs across validated paper accounts; same `risk_gate.check_order` decides. **This is a SEPARATE running engine from the core above, not a sub-component of it — see §3.2a for the full wiring, order shape, halts, and disclosed gaps.**
- **Watcher fleet:** ~31 detectors read each tick (WATCH_ONLY) via the unified heartbeat layer; promotion-gated before any go live.
- **Market-structure trend layer:** `crypto/lib/market_structure.py` + `market_structure_watcher` reads trend from price structure (swing HH/HL/LH/LL sequence + BOS/CHoCH), the layer the engine previously lacked (it read trend off the ribbon only).

### 3.2a Fleet execution path — a SECOND, separate engine (NEW section, 2026-09-02)

**The single most important fact for a newcomer: there are TWO execution engines wired to real paper broker accounts, not one.** §3.2 above is `heartbeat_core.py`, and it drives ONLY the two `mcp_heartbeat` arms, safe-2 and bold-2. Every other actively-trading arm runs through a wholly separate process chain that the pre-2026-09-02 version of this doc never mentioned: `fleet_live.py` → `fleet_executor.py`/`strategies.py` (per-arm sizing + admission) → `exit_actuator.py`/`exit_manager.py` (TP1/runner/trail/structure-stop/catastrophe cap) → `fleet_broker.py` (the only broker surface this path uses — direct REST, its own `automation/state/fleet/secrets.json`, no MCP).

As of 2026-09-02, the `execution: "fleet_rest"` roster in `automation/state/fleet/accounts.json` is **safe-3** and **risky-1** (both `status: "active"`, `live: true`). `setup/scripts/go_live_gate.py`'s own scored roster is `_FALLBACK_ACTIVE_ARMS = ["safe-2", "bold-2", "safe-3", "risky-1"]` — the same 4 arms this section and §3.2 together now fully document. **safe-3 is the fleet arm the 2026-10-30 go-live decision rests on.** A third fleet arm, **risky-3**, traded the loose-gate/premium-stop cell until its **2026-08-28 retirement** (J-approved once forward data settled its premium-vs-chart-stop question against it — bold-2 and risky-3 bought the identical SPY contract 65 seconds apart on 2026-08-28; bold-2's chart stop rode it to +195%, risky-3's premium stop closed it at −19% two minutes in). Its account was repurposed for the not-yet-armed `weekly-1` non-SPY lane; its own history (`decisions.jsonl`, `circuit-breaker.json`) is preserved under `automation/state/fleet/risky-3/` with `status: "retired"`.

- **Launch chain** — `Gamma_FleetExecutor`, registered every 1 min 09:31–16:01 ET (verified in `automation/state/SCHEDULED-TASKS.md` and `setup/install-fleet-executor.ps1`), fires through the SAME hidden headless chain as the core: `wscript.exe //nologo run_exe_hidden.vbs pythonw.exe run_ps1_hidden.py run-fleet-executor.ps1`, `-MultipleInstances IgnoreNew`, 2-minute `ExecutionTimeLimit`, 1 min behind `Gamma_HeartbeatCore` so it always reads the freshest signal row. Cadence was tightened 3min→1min on 2026-08-02 once `fleet_live.py`'s order-level idempotency guard shipped.
- **Signal flow** — `run-fleet-executor.ps1` runs two serial pure-Python steps: `build_shared_signal.py` (derives `automation/state/fleet/shared-signal.json` from the core's latest `core-decisions.jsonl` row — "one perception, N policies") then `fleet_live.py --quiet --live`. A signal older than `SIGNAL_MAX_AGE_SEC = 420` (7 min; `fleet_live.py`) is treated as unusable and blocks new **entries** only — exit management (`exit_actuator.manage_tick`) runs every tick regardless of signal freshness, pricing off live broker quotes, not the shared signal.
- **State per arm** — `automation/state/fleet/<arm>/{decisions.jsonl, exit-state.json, circuit-breaker.json, entry-claim.json, settlement-ledger.json}` (verified present for both safe-3 and risky-1). Roster + per-arm gate/sizing config: `automation/state/fleet/accounts.json`.
- **Order shape** — an entry is attempted as a bracket, then an `oto`, then falls back to a **single marketable limit**: Alpaca rejects both complex order classes for options (`fleet_broker.place_bracket`, code 42210000 — "complex orders not supported for options trading"), so in practice every fleet (and core) options entry ends up a plain limit order with TP/stop managed off-broker, never a resting bracket, whatever an in-code comment elsewhere says. Every exit — TP1, runner target, trail, structure stop, or the −50% catastrophe cap — is an **unconditional market order** via `fleet_broker.market_sell`, submitted by `exit_actuator.manage_tick`. `fleet_broker.replace_stop_order` exists but nothing on the real path calls it (only a test double does) — **there is no resting broker-side stop, ever**; the runner ratchet is realized by persisting a new stop level into `ExitState` and letting the per-tick worst≤stop check enforce it (`exit_actuator.py`'s own docstring: "a tick-managed stop, not a resting broker order").
- **Halts** — `automation/state/fleet/<arm>/circuit-breaker.json` is read every tick and blocks new entries when `tripped`. Exits are **deliberately never halted**: a 2026-08-10 night-audit fix in `fleet_live.py` removed a `not breaker.tripped` term from the exit pass's `live=` gate after empirical proof it had frozen a stop-loss at the worst possible moment — a 3-lot at entry premium 1.16, quoted 0.45 (61% down, past the −50% cap), placed 1 sell while the breaker read OK and ZERO sells once it tripped, riding to the 15:55 flatten instead of being cut. Rule 5 ("day closed... no revenge trades") is an entry rule; closing an existing position is risk reduction, never a revenge trade, and freezing it converts a bounded loss into an unbounded one. Phone `HALT <arm>` / `HALT ALL` / `HALT <arm> FLATTEN` / `RESUME` (`setup/scripts/halt_command.py`, TASK B5) writes/clears this file remotely, logging every action.
- **Independent watchdog** — `dead_mans_switch.py` / `Gamma_DeadMansSwitch`, every 2 min 09:32–15:58 ET (registered 2026-09-01, TASK W1, closing `go_live_gate.py` operational criterion 2's last named gap). Computes per-arm ENGINE liveness (minutes since the newest decision-ledger row — `core-decisions.jsonl` for safe-2/bold-2, `fleet/<arm>/decisions.jsonl` for safe-3/risky-1) every fire; if an arm is stale (`STALE_MIN = 10`, deliberately after `heal-engine.ps1`'s `CORE_STALE_MIN=8`) AND the broker confirms ≥1 open SPY option position, it flattens via `fleet_broker.close_all_spy_options`, verifies with a second read, and logs a loud line to `automation/overnight/STATUS.md`. Covers BOTH core and fleet arms — the one mechanism that watches for a dead *process*, distinct from `heal-engine.ps1` (restarts a dead process, never checks broker positions) and the EOD flattens below (fire on a schedule, not on mid-session process death).
- **EOD / early-close flatten** — `Gamma_EodFlattenCore` (15:52 ET) is the primary non-LLM backstop for safe-2 + bold-2 via `eod_flatten.py`/`fleet_broker`; the fleet's own tick (`run-fleet-executor.ps1`) additionally fires `fleet_eod.py` on its 15:50+ ticks, an independent flatten the fleet had NO equivalent of before going live. `Gamma_EodFlattenEarlyClose` (12:32 ET, registered 2026-09-01, TASK B2) handles the two dates the broker calendar closes early (2026-11-27, 2026-12-24 at 13:00 ET) — a silent NOOP on every normal 16:00 day, fails CLOSED (no action) on an unknown calendar state. `heartbeat_core.py`'s matching entry-side early-close fix is written but frozen until the 2026-09-29 config-freeze window closes.

**Known gaps — disclosed here on purpose, not fixed (config freeze is active):**
- **Rule 5's daily-loss kill switch is NOT a durable latch on fleet arms.** `daily_loss_guard.py` — the process that actually COMPUTES cumulative loss and flips a breaker's `tripped` field to `true` — only covers the two core accounts (`ACCOUNTS = {"safe": ..., "bold": ...}`, reading the root and `aggressive/` `circuit-breaker.json` files). No equivalent runs against the fleet's per-arm breakers: `fleet_live.py::_load_or_arm_breaker` arms `tripped: False` fresh each day and nothing in that module was found setting it back to `True`. The only thing actually stopping a fleet arm mid-breach is `risk_gate.check_order`'s own **live per-tick recompute** (`equity_f <= sod_equity_f * (1 - kill_pct)`, evaluated fresh on every proposed order, no memory between ticks) — an account that dips through the floor and recovers even slightly is not locked out for the rest of the day the way core is.
- **PDT is computed but not enforced on the fleet lane.** `fleet_live.py` always computes the true trailing-5-business-day day-trade count (`_true_day_trades_5d`, mirroring `heartbeat_core.py`'s own `pdt_tracker` call), but only ACTS on it when `params.fleet_pdt_enforce` is truthy — absent from every live fleet config checked (`accounts.json`, every arm's `params_patch`), so it defaults `False` and the legacy broker day-trade field is used instead.

### 3.2b Multi-symbol lane — a THIRD codebase, shadow-only and currently paused (added 2026-09-02)

`multi/` is a symbol-generic **fork** of the SPY engine, not an import of it (AST-verified zero `"SPY"` literals in its code). LANE `multi-symbol` / ARM `multi-1`, account `PA38EG1JTFBT`. It funnels ~72 names down to ≤3 through liquidity → attention → setup stages and writes `automation/state/multi/shadow-ledger.jsonl`. **It has no order-placement call anywhere in `multi/core.py`** — that is the property that makes it safe to leave scheduled, and it is what "SHADOW" means here.

**Current state, verified 2026-09-02 — read this before assuming it is running:**
- `Gamma_MultiCore` (the signal producer) is **`Disabled`**, last ran **2026-08-20T15:35**, **300 missed runs**. The lane stopped when its own frozen gate returned a null; nothing broke.
- `Gamma_MultiEvaluate` (07:00) and `Gamma_MultiOutcomes` (14:45) are **`Ready` and still firing daily** (both ran 2026-09-01) — against a ledger frozen at 231 rows since 2026-08-20. Two live consumers scoring a static file. Cheap, and it is what keeps the lane resumable, but a reader seeing green tasks would otherwise conclude the lane is producing.

Doctrine: [`WEEKLY-OPTIONS-PROGRAM.md`](../planning/WEEKLY-OPTIONS-PROGRAM.md) §9a/§9c. The account is shared with the crypto twin, so **its equity is not evidence for either lane.**

### 3.3 Agents & Skills (`.claude/`, loaded by path)
Personas: `gamma` (conductor), `pilot` (live trader), `scout`, `analyst`, `chef`, `treasurer`, `coach`, `lesson-author`, `skill-author`, `validator-author`. Skills: gym-session, preflight-gate/connectivity-gate, chart-read (market-structure + pattern + level fused read, connectivity-gated), context-leanness, heartbeat/-tick-audit, gamma-sync, log-trade, etc. (catalog: `markdown/infra/SKILLS-CATALOG.md`).

### 3.4 MCP Servers (tool layer)
- **TradingView MCP** — chart/OHLCV/study/levels read; chart control + drawings write. TradingView Desktop launched with `--remote-debugging-port=9222` (MSIX bypass in `launch_tv_debug.ps1`).
- **Alpaca MCP (paper)** — two servers, wired for the CORE arms only: `alpaca` → Gamma-Safe-2, `alpaca_aggressive` → Gamma-Bold-2 (corrected 2026-09-02; renamed from Gamma-Risky-2, see CLAUDE.md's 2026-08-18 account-identifier fix). Account/chain/Greeks/fills read; place/cancel/close write (paper only). The FLEET arms (safe-3, risky-1) do **not** go through MCP at all — `fleet_broker.py` hits the Alpaca REST API directly with credentials from the gitignored `automation/state/fleet/secrets.json` (see §3.2a).
- **Discord** — proactive presence + approve/revoke bus.
- **Free-tier OpenRouter** — Kitchen ladder + `swarm_consult.py` adversarial review ($0).

---

## 4. Data Stores (all filesystem on NTFS — observable, git-diffable, atomically restorable)

| Store | Purpose |
|---|---|
| `automation/state/` | Canonical runtime: `params.json` (Safe) + `aggressive/params.json` (Bold), position, loop, circuit-breaker, ledgers (`decisions.jsonl` …). `.lastgood/` auto-restore. |
| `automation/state/fleet/` | The FLEET path's own runtime: `accounts.json` roster, `shared-signal.json`, and per-arm `<arm>/{decisions.jsonl, exit-state.json, circuit-breaker.json}` for safe-3/risky-1 (retired: risky-3). Separate from the row above — see §3.2a. |
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
| Alpaca Paper API (4 wired accounts) | account/chain/orders — core (safe-2, bold-2) via MCP; fleet (safe-3, risky-1) via direct REST | `alpaca-mcp-server` for core, keys in project-root `.mcp.json` (the ONLY credential store — corrected 2026-09-02, global-config mirrors removed 2026-07-09); fleet keys in gitignored `automation/state/fleet/secrets.json` |
| Anthropic (Max sub) | Claude inference, all tasks | `claude --print` (shared pool — see discipline note) |
| OpenRouter free tier | Kitchen ladder + swarm review | $0 |
| Discord | presence + approve/revoke | discord MCP + bridge daemons |

---

## 6. Deployment & Infrastructure
- **Host:** single Windows 11 machine (J's desktop). No cloud, no CI.
- **Runtimes:** Claude Code CLI · Python 3.13 (`backtest/.venv` — pandas/pytest live there, NOT system python) · Node 18+ (dashboard) · PowerShell 5.1 (target 5.1 syntax).
- **Scheduler:** Windows Task Scheduler, 148 registered `Gamma_*` tasks as of 2026-09-02 (corrected — was stated here as "~35 active, 38 registered" since 2026-06-25; WakeToRun). Canonical registry, including the live active/disabled breakdown: `automation/state/SCHEDULED-TASKS.md`. Rig is **Mountain time** — tasks scheduled at ET-converted-to-local.
- **Headless spawn pattern:** wscript → `run_exe_hidden.vbs` → `pythonw` (CREATE_NO_WINDOW) to avoid console flashes.
- **Self-heal:** `_shared.ps1#Repair-StateFiles` validates state JSON pre/post each fire; restores from `.lastgood/`.

## 7. Security & Safety
- **Paper-only.** Core Alpaca keys live in project-root `.mcp.json` (gitignored, corrected 2026-09-02 — not `~/.claude.json`, which was de-mirrored 2026-07-09); the fleet's own `automation/state/fleet/secrets.json` is also gitignored. Real-money keys not provisioned. (Open hygiene item: a hardcoded paper key in a few `setup/scripts/*.py` to migrate to the secrets mechanism.)
- **Kill switches (per-account, isolated):** Safe −30% / Bold −50% of SOD equity → entries blocked for that account only. `params.json#rule_version` drift vs prompt = kill-switch. `backtest-drift severity:high` = premarket gate. **On the fleet path this is a live per-tick recompute against `risk_gate.check_order`, not a durable daily latch — see §3.2a "Known gaps" for the disclosed difference from core.**
- **Tight-ladder position caps (added 2026-08-29, `PREREG-TIGHT-LADDER-2026-08-28.md` S2).** Three keys in `params.json` (and its `aggressive/` twin): `min_contracts: 3`, `max_contracts_per_entry: 5`, `max_position_dollars: 1000`. Enforced by **`backtest/lib/risk_gate.py#cap_entry_qty`**, a pre-check that clamps qty DOWN and never denies outright, called from BOTH money paths — `heartbeat_core.py#_execute` and `fleet_executor.py#finalize` — before `risk_gate.check_order`, which carries matching backstop denies (defence in depth; should never fire). **These caps were previously UNENFORCED on both paths**: core sizing stayed ≤5 only by accident of the current `min_contracts` values, while `fleet_executor._qty_for`'s tier table returned up to 15 (and 20 on the aggressive tier) — a real, binding gap for safe-3, which sizes 8 at ELITE quality on ~$5K equity. The two caps interact: **whichever is tighter for a given premium wins**, and at current equity the flat $1,000 is tighter than 30% of ~$5.3K (~$1,590). If even `min_contracts` breaches both, `cap_entry_qty` returns `skip=True` rather than a sub-floor qty. Absent key = OFF, byte-identical. Guard: `backtest/tests/test_tight_ladder_controls_2026_08_29.py`.
- **`live: true` in `accounts.json` does NOT mean live money.** It means the arm places orders at its **paper** broker rather than sitting inert; every account in this system is paper (see the first bullet). Arming real money is a separate, J-only decision gated on `setup/scripts/go_live_gate.py`. Worth stating because the field name reads the other way — and note the two engines are armed by **different mechanisms**: the fleet arms carry `live: true` in the roster (safe-3, risky-1), while the core pair (safe-2, bold-2) has **no `live` key at all** and is armed by `GAMMA_CORE_ARMED=1` exported in `run-heartbeat-core.ps1`. Checking one mechanism tells you nothing about the other; the roster alone will never show you that core is armed.
- **Guards FAIL OPEN** — no automated process may lock out J's interactive session (OP-32 scar).

## 8. Development & Testing
- `pytest backtest/tests/` + **graduated guards** (fast per-edit hook + nightly `-m slow`). Gym: 50 validators + chart-reading replay ($0).
- Live↔research parity: daily backtest sync + `gamma-sync` skill on any rule change.
- Ratify autonomously when: OOS positive AND WF ≥ 0.70 AND sub-window stable AND anchor no-regression AND A/B scorecard filed (OP-11/OP-22). J's role = REVOKE, not approve.

## 9. Roadmap (current)
> **Destination, current position, and ordered gates now live in ONE place:**
> [`markdown/planning/ROADMAP.md`](../planning/ROADMAP.md) (2026-08-18 consolidation — this
> section used to restate that content and drifted stale; folded per OP-22). The infra
> work-items formerly listed here are tactical backlog, not destination/gates — they live in
> [`markdown/planning/FUTURE-IMPROVEMENTS.md`](../planning/FUTURE-IMPROVEMENTS.md) (Gamma
> companion Electron follow-up, Fleet executor M2, shared-decision-library refactor, conductor
> model-routing phases, GEX regime-tag consumption) if not already superseded — re-verify
> currency before treating any as an open task; this doc's own staleness (§10 below, until
> tonight) is exactly the failure mode ROADMAP.md exists to stop.

## 10. Project Identification
- **Project:** Project Gamma (call sign "Gamma"). **Operator:** J (jack.watergun@gmail.com), single user.
- **Instruments:** 0DTE SPY options (primary) + futures MNQ/MES (TT sandbox, heartbeat disabled for cost). Crypto = gym-only, never traded.
- **Accounts (paper, corrected 2026-08-18 — see `ROADMAP.md` §2 for live-verified equity):** Gamma-Safe-2 `PA3POKNV46VG` (core, conservative) · Gamma-Bold-2 `PA3WEBXJU67N` (core, aggressive). `PA3DHPT7KIQE`/`PA33W2KUAT40` (previously listed here) are dead identifiers — corrected in `CLAUDE.md` commit `ac9e84a7`, 2026-08-18. **Fleet accounts (added 2026-09-02, source `automation/state/fleet/accounts.json`):** safe-3 `PA32T7Q1O20H` · risky-1 `PA3S9N1IV0A4` — both paper, real_fills, traded via the fleet path (§3.2a), not MCP. risky-3 `PA3V7JT25H6Z` is retired (2026-08-28); its account is earmarked for the not-yet-armed weekly-1 non-SPY lane.
- **Strategy:** rule version **v15.3 Safe / v15.2 Bold**; chart-stops-primary (2026-06-18); **live truth (fills-verified 2026-07-11): core Safe trades ATM** via `crypto/lib/strike_selection.py#V15_SAFE_TIERS` — the OTM-3/OTM-2/OTM-1/ITM-2 ladder previously stated here is vestigial on the live core path (`CLAUDE.md:30`); chandelier trailing; 09:35 ET entry gate.
- **Date of Last Update:** 2026-08-18 (account identifiers + strategy line corrected; prior update 2026-07-11 — the 38-day gap is itself the drift this fix addresses).

## 11. Glossary
- **0DTE** — zero days to expiration. **ET / RTH** — Eastern time / regular hours (09:30–16:00).
- **v15** — current ratified rule version (asymmetric stops, per-tier strikes, chandelier trailing, 09:35 gate).
- **Chart-stop-primary** — chart-level/ribbon-flip/chandelier are primary invalidation; premium stop demoted to a −50% catastrophe cap (Safe; Bold keeps tight stop).
- **The Kitchen** — 24/7 free-tier R&D loop producing DRAFT candidates.
- **Conductor** — the after-hours "Gamma drives" autonomy loop (one bounded task per fire).
- **Fleet (champion/challenger)** — N frozen configs run in parallel across paper accounts off one perception; the SECOND execution engine (§3.2a), distinct from `heartbeat_core`.
- **mcp_heartbeat vs fleet_rest** — the two `execution` values in `accounts.json`. `mcp_heartbeat` (safe-2, bold-2) trades via `heartbeat_core.py` + Alpaca MCP. `fleet_rest` (safe-3, risky-1; retired: risky-3) trades via `fleet_live.py` + direct `fleet_broker.py` REST, no MCP.
- **Dead man's switch** — `dead_mans_switch.py` / `Gamma_DeadMansSwitch`, an independent 2-min watchdog that flattens any arm (core or fleet) whose decision ledger has gone stale while the broker still shows an open position — covers the "process died mid-session" gap no other mechanism closes (§3.2a).
- **risk_gate** — single risk-rule implementation (`backtest/lib/risk_gate.check_order`) used live + backtest. Its `kill_switch_tripped` argument is a caller-supplied LATCH; `check_order` separately recomputes the SoD-equity floor live on every call — on fleet arms the latch is never actually set by anything (see §3.2a "Known gaps"), so the live recompute is the only thing enforcing Rule 5 there.
- **OP-4 / OP-11 / OP-16 / OP-22 / OP-25** — operating principles: live/backtest parity · Karpathy eval-first loop · J-edge primacy · always-improving cadence · self-correcting lessons.
- **edge_capture / J-edge** — score of engine P&L on J's source-of-truth winning/losing days.
- **Saty Pivot Ribbon** — EMA trend indicator (Fast/Pivot/Slow). **OPRA** — real option bar source. **CDP** — Chrome DevTools Protocol (drives TV). **MCP** — Model Context Protocol.
- **HOT/BASE/COOL** — heartbeat cadence modes. **PDT** — pattern-day-trader rule (<$25K).
