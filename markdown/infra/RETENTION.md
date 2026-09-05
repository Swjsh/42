# RETENTION — untracked generated-output directories

> Created 2026-09-05 (GOAL-RIG-HYGIENE-2026-09-05 H2/H3). No retention doc existed before
> this one — checked first per OP-22/OP-25 (grepped `markdown/infra` for "retention"; only
> hit was `status_retention.py`'s STATUS.md-specific consolidation, which this doc does not
> duplicate — STATUS.md keeps its own byte-budget mechanism). This is a NEW file, so per
> Doc-Architecture it is linked from `markdown/README.md`'s infra row.
>
> Scope: every top-level directory that `git status --porcelain | grep '^??'` surfaces as an
> **append-only producer output root** — dated one-off files or JSONL/JSON ledgers written by
> a script every fire, with no producer-side retention cap. This is NOT an inventory of every
> untracked path in the repo — journal/, backtest/tools/, backtest/tests/, .claude/agent-memory/,
> analysis/recommendations/, analysis/deep-research/*.md, markdown/audits/ etc. are real
> content (evidence, code, or docs someone will `git add`), not regenerable log spam, and are
> called out below as **NO ACTION** rather than swept.
>
> **H4 guard** (`backtest/tests/test_retention_doc_coverage_2026_09_05.py`) fails if a
> directory glob-matched from the producer roots below has no row here.

## Policy legend

| Policy | Meaning |
|---|---|
| `keep-N` | Keep the N most-recently-modified files in the directory (or matching the prefix); move the rest. |
| `keep-days` | Keep files modified within the last N days; move the rest. |
| `archive-to-monthly` | Destination for anything moved: `<dir>/_archive/YYYY-MM/<original filename>` (grouped by the file's own mtime month), MOVE never delete. |
| `evidence — no action` | Cited by / structurally equivalent to a prereg, adjudication, or STATUS entry, or explicitly protected by GOAL-RIG-HYGIENE-2026-09-05's DONE-WHEN clause. Stays tracked (or awaits a future `git add`), never gitignored, never archived. |
| `.gitignore` | Directory (or dated-file glob) added to `.gitignore` because it is pure regenerable state — the working tree never needs it committed at all, archived copies included. |

## Producer inventory (counts as of 2026-09-05, `git status --porcelain` snapshot)

| Directory / glob | Producer script | Untracked count | Evidence or state | Policy |
|---|---|---|---|---|
| `analysis/manager/` | `setup/scripts/gamma_manager.py` (+ `eod_full_audit.py`, `tick_freshness_audit.py`, `worker_output_verify.py` writers) | 874 | State — swarm critic/validator/worker transcripts, one file per role-call | `keep-N=200` + `archive-to-monthly` + `.gitignore` on the `_archive/` subfolder |
| `analysis/daily-brief/` | daily-brief generator (premarket/EOD chain) | 113 | State — one per day | `keep-days=30` + `archive-to-monthly` |
| `analysis/swarm-consult/` | swarm consult roles (`automation/swarm/`) | 112 | State | `keep-N=60` + `archive-to-monthly` |
| `analysis/free-model-audit/{heartbeat-veto,prospector,swarm-consult,twin-review}/` (4 per-touchpoint subdirs, not flat files) | `free_model_audit.py` (OP-32 trust gate, one subdir per touchpoint) | 95 (25-27 per subdir) | State — periodic grading runs | `keep-N=15` per subdir + `archive-to-monthly` |
| `automation/state/crypto-twin/reviews/` (the dated-review subdir only — the directory's other ~21 top-level files, `breaker.json`/`decisions.jsonl`/`exit-state.json`/etc., are live current-state singletons the gym reader depends on and are never swept) | crypto-twin gym runner's daily review writer | 86 | State — one `.json`+`.md` pair per day | `keep-days=30` + `archive-to-monthly` |
| `analysis/autopsies/` | trade-autopsy generator (distinct from the protected `analysis/winner-autopsies/`, which is untouched — 0 untracked there already) | 77 | State (per-trade autopsy, superseded by digest) | `keep-days=30` + `archive-to-monthly` |
| `analysis/eod/` (loose files; `_analyst-log.jsonl` excluded — already tracked/modified, not new) | `setup/scripts/eod_full_audit.py` + Analyst persona | 45 | State | `keep-days=30` + `archive-to-monthly` |
| `analysis/gym/` | `gym-session` skill (`analysis/gym/{date}.md`) | 48 | State — daily scorecard, digest is the durable artifact | `keep-days=45` + `archive-to-monthly` |
| `analysis/participation-cascade/` | participation-cascade watcher | 33 | State | `keep-N=20` + `archive-to-monthly` |
| `automation/state/*` loose dated files: `heartbeat-tick-audit-*`, `entry-block-alert-*`, `spend-*`, `heartbeat-pulse-check-*`, `gym-scorecard-*`, `daily-loop-status-*`, `chart-data-verify-*`, `watcher-state-inspector-*`, `fill-funnel-*`, `chop-exposure-*`, `daily-review-*` | one script per prefix (heartbeat-tick-audit → `heartbeat_tick_audit`, chart-data-verify → `chart_data_verify` skill, watcher-state-inspector → `watcher_state_inspector` skill, etc. — all daily/tick self-audits) | 623 combined | State — every one is a dated point-in-time self-check snapshot, superseded the next tick | `keep-days=14` per prefix + `archive-to-monthly` |
| `automation/state/archive/` | already a manual archive destination (watcher-observations-autoheal rolls) | 7 | State (already an archive — leave in place, just gitignore) | `.gitignore` (no sweep — it IS the archive) |
| `automation/state/claude-md-backups/` | `context-leanness` skill's pre-trim backup | 8 | State — safety backups of CLAUDE.md before a trim | `keep-N=10` (no monthly split needed at this volume) |
| `automation/state/futures/` | futures-lane engine state | 12 | State — mostly `.jsonl` ledgers actively appended | `evidence — no action` for now (small volume, actively read by `futures_health.py`; sweeping risks breaking a live read — defer to a dedicated futures-lane pass) |
| `automation/state/multi/` | multi-symbol lane `level-states-*.json` | 10 | State — small, per-symbol current level cache, no history to prune | `evidence — no action` (single current file per symbol, not an append-only ledger) |
| `automation/state/fleet/` (loose files under per-arm subdirs) | fleet per-arm state | 8 | State | `evidence — no action` (live per-arm state files the engine reads on every tick; not safe to sweep without per-arm review) |
| `backtest/autoresearch/_state/` (the `_state/` subtree only — `.py` files in `backtest/autoresearch/` are code) | individual grinder/stage scripts (shotgun_scalper stages, ribbon_rejection_wick, etc.) | ~15 of the 21 counted under `backtest/autoresearch/` | State — grinder intermediate progress/results | `keep-days=30` + `archive-to-monthly` |
| `markdown/audits/` | one-off audit reports (HEARTBEAT-TICK-AUDIT-*, GATE-PROVENANCE-CENSUS, etc.) | 53 | **Evidence** — human/session-authored audit docs are exactly the OP-22 "dated one-off" class that should eventually FOLD into a living doc, but that is a doc-architecture rewrite, not a hygiene sweep; several already `git ls-files`-tracked (28) alongside these 53 new ones | `evidence — no action` (belongs to a future OP-22 fold pass per `DOC-ARCHITECTURE.md`, not this goal) |
| `analysis/deep-research/*.md` | deep-research session outputs | ~10 | Evidence — cited research docs | `evidence — no action` |
| `analysis/deep-research/_*.json` (underscore-prefixed scratch: `_lever4_spy1m.json`, `_orphan_band_positions.json`, `_orphan_band_trips.json`) + `pdt_ledger_result.json`, `week_book_result.json` | ad-hoc analysis scratch computations | 5 | State — intermediate computation dumps, not cited | `.gitignore` (glob `analysis/deep-research/_*.json`, `analysis/deep-research/*_result.json`) |
| `analysis/recommendations/` | Karpathy-method A/B scorecards | 61 new (996 already tracked) | **Evidence — OP-11 eval-first gate artifact, explicitly protected by this goal's DONE-WHEN** | `evidence — no action` (awaits ordinary `git add` in a future commit; never swept) |
| `journal/`, `journal/futures/` | trade journaling (Rule 8) | 20 (futures) + a handful of dailies | **Evidence — the journal is the trade record** | `evidence — no action` |
| `backtest/tools/`, `backtest/tests/`, `backtest/autoresearch/*.py`, `.claude/agent-memory/`, `setup/scripts/*.py` | hand-written code / session memory | n/a | Code / reference, not generated log output | `evidence — no action` (out of scope for a retention sweep — these are real content awaiting `git add`) |
| `analysis/backtests/`, `analysis/conviction/`, `analysis/fleet-weekly/`, `analysis/futures-eod/`, `analysis/multi-lane/`, `analysis/prospector/`, `automation/swarm/` | assorted small research/eval producers (trend-alignment cache, conviction backtests, risky-divergence weekly, futures EOD digest, multi-lane evaluations, prospector scouting, swarm data-fetch) | <10 each as of 2026-09-05 | Mixed — small dated research outputs, below the accumulation threshold that triggered this goal | `evidence — no action, deferred` — H4's guard allow-lists these explicitly; revisit if any crosses ~50 untracked files the way `analysis/manager` did |

## Applying the policy

`setup/scripts/retention_sweep.py` reads this table's directory list (kept in sync with the
`DIRECTORIES` constant at the top of that file — if you add a row here, add the matching
entry there, and vice versa; the H4 guard test cross-checks both against the live
`git status --porcelain` output) and, for every `keep-N` / `keep-days` row:

1. Lists candidate files (excluding anything already under `_archive/`).
2. Greps every candidate's exact filename across `markdown/`, `automation/overnight/STATUS.md`,
   and `analysis/recommendations/` for a citation; skips (never moves) a hit.
3. Dry-run by default — prints move counts per directory, no filesystem change.
4. `--apply` performs the moves (`shutil.move`, never delete) into
   `<dir>/_archive/<file's own mtime YYYY-MM>/`.

`.gitignore` additions cover only the directories/globs marked `.gitignore` above — pure
state that never needs a commit at all, archived copies included.
