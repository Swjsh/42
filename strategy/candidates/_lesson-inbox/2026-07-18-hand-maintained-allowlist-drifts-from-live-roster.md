## Hand-maintained allowlist drifts from the live roster it mirrors — 2nd occurrence, same bug class

**Found:** 2026-07-18, conductor fire (PROMOTER-WRITES-LIVE-KEY task), while checking gym
backpressure before shipping.

**Symptom:** `crypto/data/scorecards/latest.json` RED — `v53_setup_dispatch.live` fails
`names_ok: false`. `level_break_first_strike` is a live entry in `setup_dispatch.py`'s
roster (wired via `backtest/lib/watchers/level_break_first_strike_watcher.py`) but is
absent from `crypto/validators/v53_setup_dispatch.py`'s hardcoded `_KNOWN_SETUP_NAMES` set.

**Root cause:** `_KNOWN_SETUP_NAMES` is a hand-maintained Python set that must be manually
kept in sync with `setup_dispatch.py`'s roster every time a new setup is wired. Nothing
enforces the sync — the two lists can only agree by discipline, not by construction.

**This is the SECOND occurrence of this exact class**, not a new bug:
- **1st (F26-DISPATCH-191-FAILED-GREEN, closed 2026-07-11):** `double_bottom_base_quiet`
  (wired 2026-07-01) and `bollinger_squeeze` (wired 2026-07-02) were both missing from the
  same allowlist, causing 191 consecutive silent-green-while-dead validator fires before
  discovery.
- **2nd (this entry, 2026-07-18):** `level_break_first_strike`, same file, same allowlist,
  same failure mode.

**Per OP-25: a re-violated lesson MUST become a code assertion, not a second hand-fix.**
Patching the allowlist a 2nd time (add one more string) fixes today's symptom but leaves
the SAME unenforced-sync mechanism in place for a 3rd occurrence next wiring. The
generalizable fix: `_KNOWN_SETUP_NAMES` should be DERIVED from
`pipeline_promoter.read_dispatcher_roster()` (parses `setup_dispatch.py`'s roster tuples —
already built, already used by `pipeline_promoter.py` for exactly this "what's really wired"
question) instead of hand-listed, so being-in-the-roster structurally IS being-in-the-
allowlist. This is the same shape as the watcher-registry fix (`backtest/lib/watchers/runner.py`
`WATCHERS` + `test_watcher_registry.py`: "being-defined == being-registered == being-run" —
one test caught all 26 invisible watchers at once). The "hand-maintained mirror of a roster
that changes independently" pattern is now confirmed to recur; worth a general principle,
not just a v53-specific fix.

**Filed to queue.md:** `V53-GYM-RED-LEVEL-BREAK-FIRST-STRIKE` (HIGH). Not fixed this fire —
surfaced via gym-backpressure check while validating an unrelated task, kept in scope per
rail-3 (one bounded task per fire).

**Suggested graduation target for lesson-author:** a new L# under theme C14 (dead/translated
knobs) or a new sibling theme "hand-maintained allowlist mirrors a live roster" — and a
generic guard pattern recommendation: whenever a validator/allowlist exists purely to check
"is X in the current roster," parse the roster at check-time instead of hardcoding a
snapshot of it.
