# docs/archive

Dated, one-shot documentation: morning briefs, tick-audit snapshots, dated
lesson/analysis notes, session handoffs, dated readiness/validation reports.
Organized by month (`2026-05/`, `2026-06/`). Archived progressively; the
2026-06-18 de-sprawl pass moved another batch of dated docs here.

Git history is the canonical record. These were moved out of `docs/` (and the
repo root) to keep the canonical doc set lean — they are point-in-time snapshots,
not living references.

## Deliberately KEPT in docs/ (NOT archived)
- **Canonical/living:** `BACKTESTING-PLAYBOOK.md`, `LESSONS-LEARNED.md`,
  `LESSONS-CHRONOLOGICAL-LOG.md`, `DOCTRINE-ARCHIVE.md`, `FUTURE-IMPROVEMENTS.md`,
  `SKILLS-CATALOG.md`, `KITCHEN-SPEC.md`, `CONTEXT-LEANNESS.md`,
  `GAMMA-AUTONOMY-BLUEPRINT-2026-06-18.md` (current blueprint), active specs.
- **Generated-in-place (a live script rewrites them in `docs/`):** `STATUS.md`,
  `HEALTH.md`, `WATCHER-REPORT.md`, `MONDAY-READY-CHECKLIST.md`, the *current*
  `HEARTBEAT-TICK-AUDIT-{today}.md`, `T81-BULL-VIX-GATE.md`,
  `V14E-REALFILLS-26K-2026-05-23.md`.
- **Code/comment-referenced or revert-path:** `V15-ACTIVATION-2026-05-13.md`
  (3-step v15→v14 revert, cited in CLAUDE.md), `HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md`,
  `T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md`, `T80-ORB-BULL-REGRESSION.md`,
  `SNIPER-MORNING-BRIEF.md`, `SNIPER-FINAL-VERDICT-2026-05-13.md`.

Two stale duplicate root tick-audit outputs (`2026-05-14`, `2026-05-18`) were
hard-deleted: the fuller copies already lived here, and the files are regenerable
by `backtest/autoresearch/heartbeat_tick_audit.py`.
