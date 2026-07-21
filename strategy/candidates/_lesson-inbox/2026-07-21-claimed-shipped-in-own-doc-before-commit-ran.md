# Lesson candidate: a doc claiming "shipped" is not proof it was committed

**Found by:** conductor (AFTERHOURS), 2026-07-21 ~18:15 ET, while triaging STATUS.md/queue.md
before picking this fire's task (EOD-DOJO-EXHIBIT-MANIFEST).

**What happened:** `CLAUDE.md`'s own Update log carried a dated entry ("2026-07-21:
context-leanness trim, RED(9017)→YELLOW(8359/9000). ... Verify: PASS all 8 integrity checks")
describing a completed, self-verified change. The change WAS real and complete (the relocation
target `markdown/doctrine/OP-33-verify-visibility.md` existed with the full text, and
`check-context-budget.ps1` independently confirmed the claimed YELLOW/94% effect) — but `git
status` showed `CLAUDE.md` still MODIFIED and the new doctrine file still UNTRACKED. No `git
commit` had ever been run for this change. It sat in the working tree, invisible to any other
session/worktree, for an unknown number of fires between whenever it was built and this fire
finding it.

**Root cause:** a prior fire wrote its own "done" claim (matching L221/OP-33's "built ≠ shipped
until committed") in the SAME artifact it was editing (CLAUDE.md's own Update log), then
apparently stopped before running `git commit` — the self-referential proof-quote ("Verify: PASS
all 8 integrity checks") looked exactly like a normal committed-and-shipped changelog entry, with
nothing distinguishing "I verified the CHANGE" from "I verified the change AND committed it."
`verify_committed.py` exists and would have caught this (`assert_all_tracked`), but nothing in
the conductor loop's STAGE 5 (update state) or a fire's own closing checklist actually CALLS it
before writing a STATUS/queue "shipped" line.

**Proposed test / graduation (OP-25):** this is the SAME class L221 already names ("built ≠
shipped until committed"), so it's a candidate for STRENGTHENING that guard rather than a new
L-number: wire `verify_committed.assert_all_tracked` (or a cheap `git status --porcelain
--untracked-files=all -- <touched-files>` check) into the conductor's own STAGE 5 close-out as a
final assertion before the fire writes its "OK -- shipped" STATUS.md line, so a fire can no
longer claim shipped without having actually run `git commit` for the files it touched. Scope:
only the files the fire itself intended to touch (not a repo-wide sweep — this is a shared,
constantly-churning production tree; a broad check would false-positive on background writers).

**Disposition:** the specific instance was fixed in-fire (committed as `6a2e641`, verified via
`git ls-tree HEAD`) as a side quest before the main EOD-DOJO-EXHIBIT-MANIFEST build. This inbox
item is the generalizable follow-up: wire the check, don't just remember to look next time.
