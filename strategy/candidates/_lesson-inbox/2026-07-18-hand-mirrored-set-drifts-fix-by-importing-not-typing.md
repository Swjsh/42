## Lesson candidate: a hand-typed "mirror" set/allowlist WILL drift — fix by importing the derived value, not by re-typing it correctly one more time

**Date:** 2026-07-18 (evening conductor fire)
**Theme:** C14 (dead/translated-but-unapplied knobs) sibling — registry drift, not dead-knob drift

**What happened:** `crypto/validators/v53_setup_dispatch.py` hand-typed a `_KNOWN_SETUP_NAMES`
set mirroring `setup_dispatch.py`'s live dispatcher roster. This drifted out of sync **3
times** (2x `F26-DISPATCH-191-FAILED-GREEN` 2026-07-11 + `level_break_first_strike`
2026-07-18, 120 consecutive cron failures over ~60h before discovery). Each prior fix
patched the mirror set correctly — and each time, the mirror set was still a *second,
independently-maintained copy* waiting to drift again on the next dispatcher edit.

**Root cause (one sentence):** fixing a drifted mirror by re-typing it correctly does not
remove the drift *mechanism* — only removing the second copy (import the derived value
instead of retyping it) removes the mechanism.

**The fix, generalized:** when file B hand-maintains a set/list that is supposed to mirror
file A's real registry, the durable fix is never "correct B's copy" — it is "make B
IMPORT a value DERIVED from A" so there is structurally only one copy in memory. Concretely
this session: hoisted `setup_dispatch.py`'s inline `dispatchers` list to a module-level
`DISPATCH_ROSTER` constant + a derived `KNOWN_SETUP_NAMES` frozenset, and had the validator
`from setup.scripts.setup_dispatch import KNOWN_SETUP_NAMES as _KNOWN_SETUP_NAMES` instead
of hand-typing a set literal.

**Generalizable check for future graduated guards:** when a 3rd occurrence of the same
"mirror drifted" bug class is found, don't write a 3rd patch — ask "can the copy be
deleted and replaced with an import of the source of truth?" first. A guard test should
then assert IMPORT-NOT-HAND-TYPE at the source level (grep the mirror file's source for the
literal set-brace pattern and fail if found), not just value-equality — value-equality
alone still passes for a re-typed-but-still-independent copy.

**Cross-reference:** `2026-07-18-hand-maintained-allowlist-drifts-from-live-roster.md` and
`2026-07-18-setup-dispatch-registry-validator-drift.md` (filed earlier the same day,
recommending this exact fix — `pipeline_promoter.read_dispatcher_roster()` already existed
as a *third*, source-text-regex-based reader of the same roster; this fire's fix is the
"derive from the roster, don't hand-type a copy" pattern applied to the validator side
specifically, while `read_dispatcher_roster()`'s regex was left intact — it deliberately
does NOT import, to stay backtest-venv-free — but its regex WAS updated to match the new
`DISPATCH_ROSTER` row shape in the same commit, another instance of "the mirror must track
the source's shape, not just its values").

**Candidate L# theme:** fold under C14, or a new sibling "N-copies-of-one-roster must
import-not-retype" theme if C14 doesn't fit cleanly — lesson-author's call.
