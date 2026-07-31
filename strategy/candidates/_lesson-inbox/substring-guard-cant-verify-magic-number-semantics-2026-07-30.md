---
filed: 2026-07-30
filed_by: conductor (AFTERHOURS fire, ~20:30-21:10 ET)
kind: lesson
status: pending
---

# `assert "942" in src` cannot tell "09:42 as clock digits" from "942 as minutes-since-midnight" — a guard test needs to verify the DECODED value, not the presence of a magic-number substring

## Symptom

Same-day follow-on to `level-refresh-silent-stall-2026-07-30.md`: the fix built for that
incident (self-heal `Gamma_LevelRefresh` via `run-tv-watchdog.ps1`'s 5-min cadence) itself
shipped broken. The window guard `if ($mins -ge 942 -and $mins -le 955)` used `$mins =
Hour*60+Minute` (minutes-since-midnight, the SAME convention the three lines above it use
correctly via `575`/`955` for 09:35/15:55) — but `942` minutes-since-midnight is 15:42 ET,
not 09:42 ET. The self-heal that was built specifically to prevent a repeat of a ~20h
silent stall only ever activated in the final 13 minutes before the close (942-955),
covering ~3% of the RTH session it was supposed to protect.

Its own guard test (`test_level_refresh_watchdog_2026_07_30.py::test_watchdog_wires_the_self_heal`)
asserted `assert "942" in src, "self-heal window must start at 09:42 ET"` — which is TRUE
of both the buggy code and correct code, because the author (and the test author, making
the identical error) read "09:42" and typed its clock digits rather than computing
`9*60+42=582`. The test could not have caught this by construction: a substring-presence
check on a magic number can never distinguish two different semantic readings of the same
digits.

## Root cause

Writing a guard as "does this string appear in the source" instead of "does the DECODED /
COMPUTED value mean what I intend" turns a semantic assertion into a syntactic one. It
passes whether the author's number is right or wrong, as long as the wrong number happens
to look plausible as a substring (here: an actual valid 24h-clock-like value, 942, that a
skimming reviewer reads as "9:42").

## Generalizable rule

When a guard test's whole job is to pin a magic number that encodes a real-world unit
(minutes-since-midnight, seconds, cents, basis points, an index offset) — **extract the
number from the source via regex and assert on the DECODED/COMPUTED meaning**, not on the
number's textual presence. `(lo // 60, lo % 60) == (9, 42)` catches what `"942" in src`
cannot. This is the same C14 family ("dead/translated-but-unapplied knobs: vary-and-assert")
one level deeper: it is not enough to vary-and-assert that a knob AFFECTS behavior — a
guard for a unit-bearing constant must also assert the constant DECODES to the intended
real-world value, or two different units (clock digits vs. minutes-since-midnight; percent
vs. bps; dollars vs. cents) can silently swap under a passing test.

## Suggested L# slot

Fold into C14 (dead/translated-but-unapplied knobs) as a new bullet, or C7 (silent success
is failure) — this is a *test* form of silent success: the guard reported green while the
code it guarded delivered ~3% of its intended coverage.
