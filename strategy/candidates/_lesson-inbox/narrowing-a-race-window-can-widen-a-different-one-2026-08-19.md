---
filed: 2026-08-19
filed_by: conductor fire (~20:30-21:xx ET AFTERHOURS)
kind: lesson
status: pending
---

# Fixing a TOCTOU by widening the "path absent" window turned a 1/40 double-entry race into 39/40 — narrowing/moving a race window is not the same as closing it

## Symptom

`incident_fix_status.py --alert` (the 2026-08-14 double-entry incident roster) flagged
`atomic-entry-claim` RED: `test_stale_takeover_is_arbitrated_under_REPEATED_contention` failed
1/40 trials (ship-time baseline for that exact test was 0/300). Re-running it in isolation 3
more times passed clean — this was a real, rare residual race, not environmental flakiness.

## Root cause (two distinct races stacked on the same mechanism)

`_acquire_claim()` in `setup/scripts/heartbeat_core.py` (the guard that stops a wake-storm
double-placing an order — the exact 2026-08-14, -$1,569 incident) arbitrated a stale-claim
takeover via `os.rename(path, taking)` (kernel-serialized: exactly one contender can rename a
given source away). Two problems hid in that shape:

1. **TOCTOU**: staleness was READ from `path` *before* the takeover rename. A slow contender
   (T1) could read the original stale record, get preempted while a fast contender (T2) won a
   full legitimate takeover and installed a brand-new FRESH claim, then T1 would wake and act
   on its now-outdated "stale" verdict — renaming T2's fresh claim away and replacing it with
   its own. Both T1 and T2 returned `True`.
2. **A second, independent gap**: the winner's `os.rename(path, taking)` step leaves `path`
   genuinely absent from the directory until the winner writes something back. Any completely
   unrelated contender's own top-of-function `os.open(path, O_CREAT|O_EXCL)` fast path — which
   has no idea a takeover is in progress — can succeed if it happens to run during that window.

**The trap**: fixing #1 alone (judge staleness on custody taken via the SAME rename, instead of
a pre-rename read) required doing real work (json parse, decide, write) while still holding
`path` in the "renamed away" state — which *widened* window #2 rather than closing it. Measured
directly: the TOCTOU-only fix took the storm-test failure rate from 1/40 to **39/40**. A live
trace (hooking `os.rename` with per-call logging) caught the smoking gun: one of the two
"winners" in a failing trial never called `os.rename` at all — it won purely through the
untouched `_try_excl()` fast path while `path` sat empty during the other thread's now-longer
critical section.

**The actual fix**: eliminate the "path absent" state entirely. Every contender takes a real
OS-level exclusive lock (`msvcrt.locking`, Windows) on the *existing* file and overwrites its
content in place while holding the lock; the file is never removed/renamed at all past the very
first creation. Two structurally different primitives (`O_CREAT|O_EXCL` create vs. a
rename-based takeover) can no longer race on the same namespace slot, because there is only one
primitive (the lock) governing every contender past the first-ever claim.

## Rule to carry forward

1. **A race fix that changes WHEN the unsafe window opens, without asking whether it also
   changed HOW WIDE that window is, can make the defect more likely, not less.** Always
   re-run the SAME storm/stress test after a race fix — not just a single-shot check — and
   compare the failure *rate*, not just pass/fail. 1/40 -> 39/40 was caught exactly because the
   guard test still ran the full 40-trial x 16-thread storm, not a single trial.
2. **When two independent code paths can both claim ownership of the same resource, the fix
   needs ONE arbiter, not two arbiters racing each other.** `O_CREAT|O_EXCL` (for "nothing
   exists yet") and a rename-based takeover (for "something stale exists") are two different
   primitives contending for the same slot; narrowing one contender's window does nothing to
   protect against the OTHER primitive's independent success condition. The fix that actually
   worked reduced this to a single arbiter (one lock) for every path past first-creation.
3. **Prefer an OS-guaranteed primitive over a self-built one when crash-safety matters.** A
   file-based lock (rename or O_EXCL) needs its own staleness/TTL recovery story for the
   crash-mid-critical-section case — which is itself a smaller version of the same TOCTOU
   problem, just rarer. An OS-level lock (`msvcrt.locking` on Windows) is released automatically
   by the kernel on process exit/crash, with no separate recovery logic to get wrong.
4. **A static string-match check on "does the fix's identifying string exist in the source" is
   itself a foot-gun once the mechanism legitimately changes.** `incident_fix_status.py`'s
   `_chk_claim()` checked for the literal string `"os.rename(str(path), str(taking))"` — when
   the mechanism moved to a lock, that check went RED for the wrong reason (mechanism absent,
   not mechanism broken) until updated to check for the NEW mechanism's identifying strings.
   The row's actual correctness is (and was) verified by the real guard test suite run
   separately by the roster's `guard` column — the live-check function should assert presence
   of the CURRENT mechanism, not re-verify correctness itself (that's what the guard test is
   for; don't duplicate the same pytest run in two places).

## Evidence trail (this fire)

- `backtest/tests/test_atomic_entry_claim_2026_08_14.py::test_toctou_steals_a_legitimately_fresh_claim_from_under_a_new_owner`
  — new deterministic regression test, reproduces the TOCTOU 2/2 on pre-fix code via a
  monkeypatched `json.loads` that pauses a slow contender exactly after it reads the stale
  record, releasing it only once a second contender has completed a full legitimate takeover.
- 11/11 tests in that file green after the lock-based fix, re-run 5x clean (55 executions, 0
  failures) plus the full `backtest/tests/ -k "heartbeat_core or entry_claim or claim"` suite
  (167 passed, 1 skipped).
- `incident_fix_status.py --alert`: `atomic-entry-claim` GREEN (was RED, `no-console-popups`
  and `conviction-c4-c5` remain RED — pre-existing, unrelated, out of this fire's bounded scope).

Kin: C7 (audit outputs not exit codes — the static checker trusting a string), C34-adjacent
(shared-state race classes), the 2026-08-14 incident roster itself.
