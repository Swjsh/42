# strategy/candidates/_archive

Archived Kitchen brainstorm candidates. Git history is the canonical record.

## 2026-05/
172 pre-June-2026 `chef-nemo-*` free-tier brainstorm candidates, archived
2026-06-18 (de-sprawl Phase 3). These are unpromoted Kitchen output (Nemotron /
DeepSeek / MiniMax free-tier drafts) — none were cited in `_LEADERBOARD.md` or
`_LEADERBOARD-pending.md`, and nothing on the live path reads them. Per OP-22
("a 371st untriaged candidate is debt, not progress"), they were moved out of the
active candidate pile to keep it scannable.

## sweep-2026-07-22/
Batch 1 of `CHEF-CANDIDATES-CONSOLIDATION-SWEEP` (queue.md, filed 2026-07-22
night, executed same night by the AFTERHOURS conductor via
`backtest/tools/chef_candidates_consolidation_sweep.py`). 250 candidates
moved (of 322 eligible; 72 remain eligible for the next batch), oldest-first
out of 1619 top-level files scanned. Eligibility = stale (>30d old by
filename date) AND non-level-family (no `level_family: true` tag and no
FOCUS-DOCTRINE level-vocabulary match in title/heading) AND no traction
(not cited in `_LEADERBOARD.md`/`_LEADERBOARD-pending.md` or any live
inbox). Same class as the 2026-05/ batch below — mostly `chef-nemo-*`
free-tier Kitchen brainstorm drafts from the May/June cook cycles, never
promoted, nothing on the live path reads them. Disposition logged at
`_chef-log.jsonl` (one summary line per batch, `"verdict":
"archived-consolidation-sweep"`, with the full `moved_files` list — a
per-file log line was judged log-spam given 250 files/batch; the summary
line + this README entry + git history together are the audit trail).
Move-not-delete per OP-22; `git mv` history is preserved. Remaining
batches (next ~72+ eligible, plus whatever ages into eligibility) follow
the same script, same conservative "when in doubt KEEP" policy.

## Deliberately KEPT in strategy/candidates/ (NOT archived)
- `_LEADERBOARD.md`, `_LEADERBOARD-pending.md` — the curated promotion ledger.
- `_analysis/` — Chef/Analyst analysis notes.
- `_chef-inbox/`, `_lesson-inbox/`, `_skill-inbox/`, `_validator-inbox/`,
  `_chef-log.jsonl`, `_review-log.jsonl` — live Kitchen pipeline state.
- **All June-2026 candidates** (current cooking cycle).
- **31 curated/hand-authored May candidates** (named strategy specs, not
  `chef-nemo-*` noise — e.g. `2026-05-20-named-level-wick-bounce-bull.md`,
  `2026-05-17-live-price-first-bar-trigger.md`). Several are referenced in
  project memory; kept per "when in doubt, keep it."
