# Lesson candidate: `git stash` for RED-proofing an untracked new file can silently pop an unrelated pre-existing stash

> Queued by conductor (AFTERHOURS) 2026-07-21 ~21:05 ET. lesson-author picks up at next wake fire.

## Symptom

While RED-proofing a brand-new (untracked) file `backtest/tools/qqq_divergence_confluence_study.py`,
ran `git stash -- backtest/tools/qqq_divergence_confluence_study.py` in a Bash tool call
alongside a follow-up `pytest ...` and `git stash pop`, each as separate newline-joined
commands (no `&&`). The `git stash -- <pathspec>` failed immediately (exit 1: "pathspec ...
did not match any file(s) known to git" — `git stash` cannot target a pathspec that has
never been added/tracked). Because the commands were not chained with `&&`, Bash kept
executing the remaining lines anyway, and the bare `git stash pop` at the end popped
`stash@{0}` — a PRE-EXISTING stash left by an unrelated earlier fire/session, not one this
fire created. `git stash pop` aborted safely on its own (conflicts with the ~2,400 files
this shared checkout has modified-but-uncommitted at any given moment — automation writes
constantly to `automation/state/*.json`, `analysis/*.jsonl`, etc.), so no data was actually
lost this time, but the near-miss is real: a clean pop would have silently applied another
session's stashed work-in-progress on top of this fire's tree.

## Root cause

Two compounding issues:
1. `git stash push -- <path>` (and the shorthand `git stash -- <path>`) requires the path to
   already be tracked by git — it cannot stash a brand-new untracked file by pathspec. This
   is a genuine Git behavior gap, not a typo: the correct incantation for an untracked file is
   `git stash push -u -- <path>` (or don't use stash at all for a same-file RED-proof).
2. This repo's shared checkout is PERMANENTLY dirty (per C34/L214/L228/L233 — many daemons
   write to tracked state files continuously), so ANY blind `git stash`/`git stash pop` in
   this repo risks touching hundreds-to-thousands of unrelated in-flight file changes, and —
   worse — the STASH STACK itself is a single shared LIFO that other fires/sessions may also
   be using. A conductor fire popping `stash@{0}` has no way to know whether that stash
   belongs to itself or to a concurrent/prior session.

## Fix (this fire)

Did NOT use `git stash` for the RED-proof. Used `mv <file> <file>.bak`, ran pytest (collection
correctly failed with `ModuleNotFoundError`), then `mv <file>.bak <file>` to restore — safe for
an untracked new file, touches nothing else in the tree. Re-verified 9/9 green after restore.

## Encoded in

Not yet graduated to a code guard — first occurrence, and the Bash tool itself doesn't offer
a way to auto-chain-abort on a mid-sequence non-zero exit inside one multi-line invocation
(the harness explicitly documents Bash as running commands sequentially, not `&&`-joined,
unless the caller chains them). The durable fix is PROCEDURAL for now: **never use `git
stash`/`git stash pop` in this repo's automation/conductor context at all** — this repo's
permanently-dirty shared checkout makes the stash stack unsafe as a scratch space (same root
class as C34's "tree-wide git ops revert live state backward"). For RED-proofing a NEW
(untracked) file, rename-and-restore (`mv`/`Move-Item`) is the correct, contained tool. For
RED-proofing an EXISTING tracked file's specific change, `git diff > tmp.patch && git
checkout -- <file>` (verified path, single file) or a scratch copy is safer than `stash`
because it never touches the shared stash stack other sessions may be using concurrently.
If this pattern recurs (a conductor/chef/other-persona fire reaching for `git stash` in this
repo), THAT is the trigger to graduate this into an actual guard — e.g. a repo-local git
alias/wrapper that refuses `stash` outside an explicit `--i-know-this-repo-is-different`
flag, or a pre-flight note in `automation/prompts/conductor.md`'s tool-use guidance.

## L## (optional)

Suggested next available (lesson-author greps `LESSONS-LEARNED.md` for the current max —
index says "current through L235" as of this fire's earlier STATUS.md read, so this would be
**L236**). Cross-reference C34 (tree-wide git ops in the shared checkout) as the parent class.
