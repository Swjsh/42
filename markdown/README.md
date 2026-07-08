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
| `planning/` | Roadmaps, checklists, gameplans, daily-review process | `AUTONOMY-ROADMAP.md`, `LIVE-PATH-WORKPACKAGE.md`, `JARVIS-WATCH-DESIGN.md`, `GAMMA-COCKPIT-EXECUTION-LOG.md`, `FUTURE-IMPROVEMENTS.md`, `BRAIN-SOVEREIGNTY.md`, `GAMMA-WORKER.md` |
| `doctrine/` | Lessons learned, doctrine archive, edge doctrine | `LESSONS-LEARNED.md`, `DOCTRINE-ARCHIVE.md` |
| `specs/` | Engine design + wiring specs | `ARCHITECTURE.md` |
| `audits/` | Point-in-time health checks, postmortems, status snapshots | `HEARTBEAT-TICK-AUDIT-LOG.md` (rolling, keep ~10), `HEALTH.md` |
| `infra/` | Setup, MCP install, kitchen spec, skills catalog, tooling, doc-architecture | `DOC-ARCHITECTURE.md`, `mcp-install.md`, `KITCHEN-SPEC.md` |
| `meta/` | Reframe-engine / meta-ideation doctrine (P2 pipeline, OP-32) | `REFRAME-ENGINE.md` |
| `_attic/` | **Archive** — closed-out, superseded, point-in-time studies kept for provenance (conclusions already live in MEMORY/params/living docs). Discovered via glob, never linked from CLAUDE.md. | (archive — do not add living docs here) |
