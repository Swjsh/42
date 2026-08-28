## Foot-gun: Edit tool with replace_all=false can silently land in a giant changelog line

**Date:** 2026-08-28
**Where found:** conductor fire fixing QUOTE-RECORDER RED (commit `69e6c1bf`), editing
`automation/state/SCHEDULED-TASKS.md`.

**What happened:** `SCHEDULED-TASKS.md`'s "Active tasks" section opens with a single giant
line (line 50, ~50KB) that has accumulated a `(**+1 <date>: TaskName** -- description)`
parenthetical for every task ever added to the registry -- effectively an append-only
changelog compressed into one line. When adding a new table row via `Edit(old_string=<the
row immediately before my insertion point>, new_string=<that row + my new row>)`, the tool
reported success, but the actual byte-for-byte match landed inside that giant changelog
line rather than at the real table row further down -- verified via `grep -c` showing 2 (then
3, after a parallel session also touched the file) occurrences of the new task name, and
`git diff` confirming the edit's context was the changelog paragraph, not the table.

**Root cause:** `old_string` was a row's rendered Markdown text (`| \`TaskName\` | cadence | cost
| description text |`). Because the file separately *quotes or closely paraphrases* old row
text inside its own changelog-of-changes preamble (to document what was added and why), an
`old_string` chosen from "the row I want to insert after" can have a near-duplicate earlier in
the file that the matcher treats as equally valid -- and since `replace_all` defaults to
`false`, the FIRST match wins, which is not necessarily the one visually chosen when reading
the file top-to-bottom in an editor (a 50KB single line renders as one screen-line in most
viewers/greps, easy to skip past without registering how much text it contains).

**Impact this time:** benign -- caught before commit via `grep -n` sanity check + a duplicate
table row was found and removed. No corruption shipped. But it could easily have shipped a
malformed changelog line (broken Markdown, wrong location) undetected, since a huge single
line does not visually diff well in a terminal.

**Generalizable fix:** before any `Edit` on a file with a known giant/append-only single-line
section (this file's line-50 changelog; likely elsewhere in this repo's other "reconciled"
status docs), grep the target `old_string` snippet for occurrence COUNT first
(`grep -c` or a `python -c` line-count check) -- if count > 1, either use a longer/more unique
`old_string` that cannot also appear in the changelog prose, or target by explicit line number
via a small Python read-modify-write instead of the Edit tool's fuzzy string match. This is
the same discipline as `replace_all` guidance but the failure mode here is BEFORE
`replace_all` even matters -- it's about `old_string` uniqueness across the WHOLE file, not
just within the intended edit region.

**Suggested guard:** none proposed yet -- this is a process lesson for future Edit-tool usage
on `SCHEDULED-TASKS.md` specifically (and any file with a similar append-only single-line
changelog pattern), not a code assertion. If this class recurs on the SAME file, consider a
pre-commit check that greps for duplicate `| \`Gamma_*\`` table rows (same task name appearing
twice as a markdown table row) and fails the safety gate.
