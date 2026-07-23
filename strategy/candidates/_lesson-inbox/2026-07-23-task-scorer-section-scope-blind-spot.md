## Foot-gun: task_scorer.py silently invisible to items outside "## Active backlog"

**Symptom:** `task_scorer.py`'s `_active_lines()` stopped parsing at the FIRST
top-level `## ` heading after `## Active backlog` (treating it like the
`Completed`/`Archived` terminator). But `automation/overnight/queue.md`'s
actual append discipline never matched that assumption — many past conductor
fires filed new dated `## <event>` sections BELOW Active backlog (`## Blocked`,
`## Twin escalations`, `## TRENDLINE-FIXES-2026-07-17 (HIGH...)`, real items
that drifted into `## HARVESTED-FROM-GYM`'s body like `GATE-TIERS-IMPLEMENT`)
instead of adding rows to Active backlog itself.

**Root cause:** a per-section parser boundary that assumed a doc-authoring
convention the actual authors (conductor fires themselves) never consistently
followed — the C14/L245-L246 dead-scope class (a producer moves past where a
consumer expects it, consumer stays silently blind).

**Impact (confirmed live, 2026-07-23 ~18:xx ET conductor fire):**
`task_scorer.py --all` went from parsing 45 items to 79 after the fix — **34
items were completely invisible**, including **18 genuine `status:pending`
items, 9 of them HIGH** (`GATE-TIERS-IMPLEMENT`, `ENGINE-VECTORIZATION`,
`OPEN-BELL-STATUS-PUSH`, `TWIN-B6-SIM-FRICTION-CALIBRATION`,
`VWAP-TREND-PULLBACK-VERIFY-FAILED`, and 4 more). Some had sat unrankable for
weeks — only found by conductors who happened to `grep` the file directly
instead of trusting `--top`.

**Fix shipped this fire:** `_active_lines()` now scans `## Active backlog`
onward to EOF, only skipping sections whose heading matches
`EXCLUDED_SECTION_RE` (`archived`/`completed` — the two names that are
*provably* resolved/historical). Everything else — including
`HARVESTED-FROM-GYM`, whose genuine auto-harvest rows already self-exclude via
`status:queued` (not in `READY_STATUSES`) — is now visible. RED-proofed via
`git stash`: the two new regression tests fail with the exact expected
`AssertionError` on the old code, pass clean on the fix. `backtest/tests/
test_task_scorer.py` (13/13) + full task_scorer suite (63/63) + curated
safety gate (31+5) all green. Commit: (see queue.md / STATUS.md entry same
timestamp).

**Graduation ask for lesson-author:** fold into LESSONS-LEARNED.md as a new
`L###` under class **C14 (dead/translated-but-unapplied knobs: vary-and-assert)**
— this is the same family as L245/L246 (queue.md multi-paragraph convention
breaking a per-line parser two ways) but for SECTION scope instead of field
scope: *"a per-section parser boundary is a contract with the doc's authors —
verify the authors actually follow it before trusting a 'stop at heading X'
rule; when in doubt, scan wider and let status/dependency fields do the
exclusion instead of positional section boundaries."*
