# markdown/ — consolidated documentation

All human-authored docs live here, organized by topic. Operational files
(`automation/`, `.claude/`, `journal/`, `strategy/candidates/`, `analysis/`)
stay where the engine reads them.

> **Doc-architecture doctrine:** [`infra/DOC-ARCHITECTURE.md`](infra/DOC-ARCHITECTURE.md) — how files are tiered,
> when to CREATE vs APPEND, and how dated one-offs FOLD into living docs instead of accumulating.
> Read it before adding any new `.md`. Dated one-offs fold UP into the "living doc" named per folder below;
> closed-out point-in-time studies are archived to [`_attic/`](_attic/).

| Folder | Contents | Living doc(s) — fold dated one-offs here |
|---|---|---|
| `0dte/` | SPY 0DTE strategy, playbook, patterns, key levels, J-edge, risk rules | `playbook.md`, `risk-rules.md`, `J-EDGE-GROUND-TRUTH.md` |
| `futures/` | MNQ/MES contract specs, margin, sessions, sources | `CONTRACT-SPECS.md`, `README.md` |
| `research/` | Backtest findings, studies, swarm benchmarks, R&D writeups | `STRATEGY-BACKLOG.md`, `GRIND-RESULTS.md`, `SWARM-BENCHMARK.md`, `BACKTESTING-PLAYBOOK.md` |
| `planning/` | Roadmaps, checklists, gameplans, daily-review process | **[`ROADMAP.md`](planning/ROADMAP.md) — THE canonical destination/gates roadmap, read this first**; [`OPUS-WORK-ORDER-2026-09.md`](planning/OPUS-WORK-ORDER-2026-09.md) — the live execution order to the 2026-10-30 decision; `WEEKLY-OPTIONS-PROGRAM.md` (the weekly-options second lane, J-directed 2026-08-18), `AUTONOMY-ROADMAP.md`, `LIVE-PATH-WORKPACKAGE.md`, `JARVIS-WATCH-DESIGN.md`, `GAMMA-COCKPIT-EXECUTION-LOG.md`, `FUTURE-IMPROVEMENTS.md`, `BRAIN-SOVEREIGNTY.md`, `GAMMA-WORKER.md` |
| `doctrine/` | Lessons learned, doctrine archive, edge doctrine, agent orchestration | **[`AGENT-ORCHESTRATION.md`](doctrine/AGENT-ORCHESTRATION.md) — tier map + the 15x multi-agent cost reality + the autonomy goal-loop**; `LESSONS-LEARNED.md`, `DOCTRINE-ARCHIVE.md`; [`STUDY-CURRICULUM.md`](doctrine/STUDY-CURRICULUM.md) — Gamma's standing learning rotation (conductor STUDY MODE, `setup/scripts/study_curriculum.py`) |
| `specs/` | Engine design + wiring specs | `ARCHITECTURE.md` |
| `trading-knowledge/` | Options mechanics (Greeks, structures), DTE/IV theory, market-structure execution, regulatory + broker research | `options-greeks-structures.md`, `dte-iv-volatility.md`, `market-structure-execution.md`, `GENERATIVE-LENS.md` |
| `audits/` | Point-in-time health checks, postmortems, status snapshots | `HEARTBEAT-TICK-AUDIT-LOG.md` (rolling, keep ~10), `HEALTH.md` |
| `infra/` | Setup, MCP install, kitchen spec, skills catalog, tooling, doc-architecture | **[`DOCTRINE-HOOKS.md`](infra/DOCTRINE-HOOKS.md) — the enforcement layer under CLAUDE.md (why doctrine stopped sticking + what now hard-blocks)**; `DOC-ARCHITECTURE.md`, `mcp-install.md`, `KITCHEN-SPEC.md`, `UNATTENDED-REGISTRY.md` |
| `meta/` | Reframe-engine / meta-ideation doctrine (P2 pipeline, OP-32) | `REFRAME-ENGINE.md` |
| `_attic/` | **Archive** — closed-out, superseded, point-in-time studies kept for provenance (conclusions already live in MEMORY/params/living docs). Discovered via glob, never linked from CLAUDE.md. | (archive — do not add living docs here) |
