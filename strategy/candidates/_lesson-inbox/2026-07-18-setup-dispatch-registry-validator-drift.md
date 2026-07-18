# Lesson candidate: dispatcher registry name added without updating validator's allowlist -> silent 120-fire cron RED

> Queued by conductor-weekend fire 2026-07-18. lesson-author picks up at next wake fire.

## Symptom
`crypto/data/scorecards/drift_report.json` `overall_health` = RED, `consecutive_fail_streak` = 120 (the `Gamma_CryptoRegression` cron fires every 30 min; 120 fires = ~60 hours, since 2026-07-15). `stage_pass_rate_24h.v53_setup_dispatch.live` = 0.0% (0/48). Log tail showed a distracting red herring first — `STDERR: [DISPATCH] _build_ctx failed: AttributeError: 'str' object has no attribute 'get'` — which turned out to be EXPECTED noise from the validator's own T5 garbage-payload robustness test (`dispatch_extra_setups("safe", ..., "NOT_A_DICT", {})`), not the actual bug.

## Root cause
`setup/scripts/setup_dispatch.py`'s `SetupDispatcher.run()` `dispatchers` registry gained a new entry, `("level_break_first_strike", "j_lbfs_enabled", self._dispatch_lbfs)`, on 2026-07-15 (SHADOW-LOGGED wiring — detect+log every tick, deliberately not exec-armed). `crypto/validators/v53_setup_dispatch.py`'s `run_live()` structural check asserts every live `setup_name` is in a hardcoded `_KNOWN_SETUP_NAMES` allowlist (`names_ok`). That allowlist was never updated at wiring time, so every live tick that dispatched `level_break_first_strike` (which is every tick, since it's SHADOW-LOGGED not flag-gated-off) returned `names_ok=False` -> `pass=False` -> the whole `v53_setup_dispatch.live` stage FAILs, forever, since the registry and the allowlist are two independent lists that nothing forced to stay in sync.

This is the exact C14 "dead/orphaned registry" class already documented for watchers (`backtest/lib/watchers/runner.py` `WATCHERS` + `test_watcher_registry.py`, L182-style: being-defined must == being-registered == being-checked) — but here it recurred on a SIBLING registry (the setup-dispatch layer, not the watcher layer) that had no equivalent guard. A producer (the dispatcher registry) gained a name the consumer (the validator's allowlist) never learned about, and nothing enforced they had to move together.

## Fix
`crypto/validators/v53_setup_dispatch.py` — added `"level_break_first_strike"` to `_KNOWN_SETUP_NAMES` (one-line data fix; validator immediately went `pass: true`, gym 104/104 GREEN).

`backtest/tests/test_graduated_guards.py::test_setup_dispatch_names_registry_sync` (NEW) — AST-parses `SetupDispatcher.run()`'s inline `dispatchers` list to extract the registered setup_name strings, diffs against `v53_setup_dispatch._KNOWN_SETUP_NAMES` in both directions (missing-from-validator = hard fail; stale-in-validator = hard fail, cleanup nudge). RED-proofed: stashed the one-line validator fix, guard failed with the exact diagnosis (`missing_from_validator = {'level_break_first_strike'}`); restored, guard passes. This makes the class of bug structurally impossible to reintroduce silently — the NEXT time a name is added to one side without the other, `pytest` catches it immediately instead of a 60-hour silent cron RED streak.

## Encoded in
- `crypto/validators/v53_setup_dispatch.py` (`_KNOWN_SETUP_NAMES`, data fix)
- `backtest/tests/test_graduated_guards.py::test_setup_dispatch_names_registry_sync` (new graduated guard, RED-proofed)
- This lesson-inbox item (pending L## assignment + `markdown/doctrine/LESSONS-LEARNED.md` + CLAUDE.md OP-25 index fold)

## L## (optional)
Suggested theme: fold into existing C14 row (`markdown/doctrine/LESSONS-LEARNED.md` — "Dead/translated-but-unapplied knobs: vary-and-assert") as a new L### entry, OR file as its own row if lesson-author judges "registry drift between two independently-maintained name lists" distinct enough from "dead knob" to warrant a new cross-reference (C1-style: "N registries claiming to describe the same set of names must be generated from one source of truth, or guarded to stay in sync"). lesson-author picks the number (greps current max in LESSONS-LEARNED.md).
