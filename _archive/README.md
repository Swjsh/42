# _archive (top-level)

Holding area for retired local backups, archived 2026-06-18 (de-sprawl Phase 3).
Git history is the canonical record.

| Item | What it is |
|---|---|
| `_local_backups_20260614/` | Dated pre-change backups (`CLAUDE.md.orig`, `orchestrator.py.orig`, `params.json.orig`, `shadow.py.orig`) from the 2026-06-14 Stage-0 reversibility work. **Intentionally git-ignored** (`.gitignore` `_local_backups_*/`) — restore the live source from git if ever needed, not from here. |

Note: per-domain archive trees live next to their domain, not here:
`automation/prompts/_archive/`, `docs/archive/`, `strategy/candidates/_archive/`,
`backtest/autoresearch/_archive/`.
