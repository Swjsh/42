# Shared-index absorption: another lane's bare `git commit` can swallow YOUR staged files

**Date:** 2026-08-01 (WS12 reset-prep lane, weekend multi-lane grind)
**Family:** C34/C35 (shared-checkout git ops; committed != verified) — NEW mechanism vs
L239 (own multi-path add fails atomically) and L247 (own later commit absorbs a staged
delete): here the absorber was a DIFFERENT concurrent session.

**Symptom:** WS12 ran `git add <4 files>` at 12:53, but its `git commit -- <paths>` was
blocked ~15 min by an unrelated RED pre-commit gate (WS7's undocumented scheduled task).
While blocked, WS11's lane ran a BARE `git commit` (no pathspec) for its own work — the
shared index still carried WS12's 4 staged files, so WS11's commit `da18da34`
("feat(recency): core-strategy recency clock") silently absorbed 490 lines of WS12
deliverables (RESET-PLAN-2026-08-01.md, a guard test, SKILL.md, a STATUS entry). WS12's
own commit `75e9acd5` then recorded only a 3-line follow-up edit under the full WS12
message — the message/content mapping across both commits is misleading forever.

**Detection that worked (keep doing):** the commit summary line said
"1 file changed, 3 insertions" against an intended 490 — the L247 post-commit
`git show <sha> --stat` habit caught it within one command.

**Root cause (one sentence):** in a shared checkout, `git add` state is GLOBAL — any
parallel lane's pathspec-less `git commit` commits YOUR staged-but-uncommitted files.

**Fixes to encode:**
1. Stage-and-commit must be ATOMIC in this repo: run `git add` immediately before
   `git commit`, never with a gap (a blocked/failed commit LEAVES files staged — restage
   check before retry, or `git restore --staged` on abort).
2. Every lane commits with an explicit pathspec (`git commit -- <paths>`) — this both
   scopes the commit AND refuses to absorb others' staged files. Bare `git commit` in this
   shared checkout is the absorption weapon; candidate for a graduated guard (pre-commit
   hook could warn when the index contains files untouched by the current lane... hard to
   attribute — at minimum, doctrine: pathspec-commit is MANDATORY, already the WS-prompt
   convention; this incident shows one lane skipping it silently damages ANOTHER lane's
   attribution).
3. Post-commit `git show <sha> --stat` stays mandatory (it caught this).

**Impact here:** content all landed correctly at HEAD (verified: working tree == HEAD for
all 4 files; final tables present); damage is commit-attribution only. No revert performed
— rewriting either commit would be worse (both are pushed-adjacent shared history).
