# A RED-proof mutation that ESCAPES is the finding — don't just note it, chase it

**Date:** 2026-09-02 (Opus session, `markdown/planning/OPUS-WORK-ORDER-2026-09.md` §2d)
**Theme:** C7 / guard quality — a guard that cannot fail is a guard that isn't testing

## Symptom

Three RED-proof runs in one box produced an escape or a wrong-reason pass:

| mutation | should have been caught by | what actually happened |
|---|---|---|
| default path swapped to the retired producer (`STATE / "key-levels.json"`) | `test_the_check_reads_the_live_producer_not_the_retired_one` | **13 passed** — the test asserted the retired field's NAME and the module constant's NAME, and the mutant contained neither string |
| `PINNED_SECTIONS = ()` | `test_the_marker_survives_a_real_roll_wherever_it_sits` | caught by *other* tests, but not this one — the fixture put the marker in the NEWEST entry, which `min_keep=1` preserves regardless |
| hoist copies instead of moves | (nothing) | **21 passed, blind** |

Each escape was a *different* defect in the guard, and one of them (`done` keyed on the
original preamble, so every historical copy was hoisted) was a real bug in the shipped code
that only surfaced because a strengthened test was written to chase the escape.

## Root cause

A RED-proof is only evidence if the mutation actually changes the outcome the test observes.
Two ways that silently fails:

1. **The test asserts the regression's SPELLING, not its behaviour.** "Does the source
   mention the retired field?" passes for every regression phrased differently. (Same family
   as [[2026-09-02-string-search-cannot-answer-code-questions]] — here it bit a *test* rather
   than a guard.)
2. **The fixture is arranged so the mutant and the fix agree.** A marker in the newest entry
   survives with pinning ON and with pinning OFF. The test was well-named, well-documented,
   and proved nothing.

Both look identical to a passing suite. The only thing that distinguishes them is running
the mutation and *reading which test names appear in the FAILED list* — not just the count.

## The rule

**Print the names of the tests each mutation kills, and require the intended one to be
among them.** "N failed" is not a RED-proof; "failed *for the reason I claimed*" is.

```python
failed = [l.split("::")[1].split()[0] for l in out.splitlines() if l.startswith("FAILED")]
print(f"{label}: caught by: {', '.join(failed) or 'NOTHING -- GUARD IS BLIND'}")
```

And when a mutation escapes: **the escape is the finding.** Strengthen the guard until it
catches it — never drop the mutation for being "unrealistic", and never settle for "some
other test caught it". The other test may be catching it for an unrelated reason that a
future edit removes.

Corollary, learned the same box: **mutate in both directions.** A dedupe needs a mutation
proving it still lets a genuinely NEW problem through; a hoist needs one proving it MOVES
rather than copies. Half of the escapes above were on the direction nobody thinks to test —
the one where the fix does too much rather than too little.

## Also from this box: a guard that ordinary use turns RED will be ignored

`test_marker_is_above_the_first_dated_entry` asserted that `## Known broken` sat physically
above the first `## [` entry. It went RED within a day — not because anything broke, but
because a producer prepended a dated entry, which is correct behaviour. Position was a
*proxy* for "survives the retention roll". The proxy stopped tracking, so it was replaced by
the invariant itself, and the underlying code was changed to pin by NAME instead of position.

Deleting a test to make a suite green is forbidden. **Replacing a proxy assertion with the
property it was proxying for is the opposite of that** — but say which one you are doing,
and say why, in the test's own docstring.

Related: [[2026-09-02-state-ready-is-not-it-ran]] ·
[[2026-09-02-string-search-cannot-answer-code-questions]]
