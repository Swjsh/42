# A queue.md item whose priority-paren wraps to a second physical line vanishes from task_scorer ENTIRELY — not just ready:false, absent from --all too

**Date:** 2026-07-22 (conductor, AFTERHOURS — self-inflicted, self-caught same fire)

**Class:** C14 sibling (multi-line queue.md parsing fragility) + C7 (an author must verify
the tool's OWN output after editing the file it reads, not assume the edit "obviously"
parses). Sibling bug to [[2026-07-22-task-scorer-multiline-status-read-as-empty-ready]] —
same file, same append-only convention, a DIFFERENT physical-line-boundary assumption.

## Symptom

While shipping `CHEF-FOCUS-FILTER` (parts 1-3) this fire, I appended a new follow-up item
`CHEF-CANDIDATES-CONSOLIDATION-SWEEP` to `queue.md`. After editing, `task_scorer.py --all`
silently returned ZERO tasks with that id — not `ready:false`, not present in the JSON at
all. Worse than the sibling multi-line-status bug (which at least mis-ranked a real Task
object); here no Task object was ever created.

## Root cause

`ITEM_RE` requires the priority parenthetical `(<PRIORITY, ...>)` to open AND close on the
checkbox's own physical line — `\((?P<paren>[^)]*)\)` cannot match across a newline. My
first draft of the item wrote a long priority annotation that wrapped:
```
- [ ] CHEF-CANDIDATES-CONSOLIDATION-SWEEP (HIGH, one-time triage, bounded but LARGE -- do in
  batches, not one fire) :: `strategy/candidates/` holds 1619 files ...
```
`ITEM_RE.match(line.strip())` on line 1 alone fails (no closing `)` on that line) — so
`_item_blocks()`'s own `is_new_item` check never fires, meaning the checkbox line isn't
even recognized as starting a block. Because a genuinely-open `- [ ]` item happened to
`- [x]`-shaped precedent existed elsewhere in the file (three ALREADY-DONE items with the
identical wrapped-paren shape — `DECISION-ROW-SPY-STALENESS`, two lesson-inbox/producer-bug
items — lines 508/1649/1679, confirmed by grep), this defect had clearly existed before
tonight and simply never bit anything live, because `- [x]` items are skipped anyway
regardless of whether they parse. Tonight was the first time it landed on an OPEN item.

## Fix (this fire)

Rewrote the item so the full `(HIGH, ...)` parenthetical closes on the SAME line as the
checkbox (`(HIGH, one-time triage, do in batches) ::`), moving the longer explanation into
the body text after `::` instead of inside the parens. Verified via direct script probe
(`_item_blocks` + `ITEM_RE.match` against the live file) before and after — id absent
before, `ready:True` (correctly, `depends:none :: status:pending`) after.

## Guard

Not yet graduated to a code assertion this fire (rail 3 — one bounded task; the fix above
plus this lesson IS the bounded unit of learning for this fire). Recommended graduation for
`skill-author`/`validator-author`: a small pytest that scans the REAL `queue.md` for any
`- [ ]` (OPEN, unchecked) line matching `^- \[ \]\s+\S+\s+\(` with no closing `)` on that
same physical line, and fails loud (mirrors the ad-hoc probe used to verify this fire's fix,
made permanent and run every CI/pytest pass instead of only when someone happens to check).
Scope it to `- [ ]` only — `- [x]` occurrences are provably harmless (skipped either way)
and re-writing three already-closed historical items is not worth the diff risk.

## Generalization

Any handwritten annotation inside `queue.md`'s `(<priority>, <freeform notes>)` parenthetical
must stay physically single-line, same discipline as keeping `status:`/`depends:` fields
line-scoped. When a priority annotation wants to say more than fits on one line, put the
elaboration in the body after `::`, never inside the parens across a wrap.
