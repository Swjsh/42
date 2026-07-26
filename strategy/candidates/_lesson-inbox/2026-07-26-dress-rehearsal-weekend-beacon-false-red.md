# Weekend freshness checks need the SAME market-closed exemption idiom as their siblings

**Filed:** 2026-07-26, conductor (AFTERHOURS fire)
**Commit:** `e370b0dc` (setup/scripts/dress_rehearsal.py + backtest/tests/test_dress_rehearsal.py)

## Symptom

`Gamma_DressRehearsal` (nightly 20:45 ET, `DaysInterval=1` — every calendar day incl.
weekends) RED'd `overall` on EVERY Saturday/Sunday night, forever, because its
`check3_sanity` sub-check enforced `sight-beacon.json age < 24h` with no exemption for
days when the beacon legitimately doesn't tick (weekends — the beacon only runs during
weekday RTH). `self_check.py`'s `check_dress_rehearsal` reader correctly-but-misleadingly
escalated this to `BROKEN` every weekend, training the eye to associate "DRESS-REHEARSAL
RED" with noise instead of a real broker-boundary failure (the exact alert-fatigue class
`markdown/doctrine/LESSONS-LEARNED.md` already warns about elsewhere).

## Root cause

`engine_health.py` already has the correct idiom, used consistently across
`check_sight_beacon`, `check_engine_core`, `check_watcher_feed`, etc.: every freshness
check takes a `market_open` bool and short-circuits to `GREEN "(market closed -- quiet
OK)"` when the market isn't open, regardless of how stale the underlying producer's
timestamp is. `dress_rehearsal.py` was built later (2026-07-01) as a SIBLING instrument
(same "is the engine's eye alive" question) but re-derived its own freshness check from
scratch — a flat `age_h >= 24` — without importing or mirroring that idiom. Nobody
compared the two freshness-check implementations at build time.

## Generalizable rule

**Before shipping a NEW freshness/liveness check against a producer that only runs
during weekday RTH (a beacon, a heartbeat tick, a level refresh, a watcher feed), search
for the EXISTING idiom first** (`grep "quiet OK" setup/scripts/*.py` or
`grep "market_open" setup/scripts/*.py`) and reuse/mirror it, rather than re-deriving a
bespoke wall-clock threshold. A flat `<Nh` check without a weekday/market-hours gate will
ALWAYS false-positive on weekends (and likely holidays) for any weekday-only producer —
this is not specific to the beacon, it applies to any future check of the same shape.

## Fix shipped

`check3_sanity(creds_map, next_day, *, is_weekend: bool = False)` — `is_weekend` derived
in `main()` via the canonical `et_clock.et_weekday() >= 5` (matching `is_market_hours`'s
own convention, no new helper invented). A stale-but-PRESENT beacon is GREEN "quiet OK"
on a weekend; a MISSING beacon still RED's regardless of day (a genuine unknown is never
softened, only a KNOWN-quiet staleness is).

**Named follow-up, not chased to stay bounded:** the fix is weekday-only (Sat/Sun), not
market-holiday-aware. A market holiday landing on a weekday would still false-RED. Lower
priority — holidays are rarer than the guaranteed-every-week weekend case this fire fixed,
and `dress_rehearsal.py` already has a `_next_trading_day` broker-calendar call in scope
that a future fix could reuse to derive holiday-awareness without a new API call.

## Guard

`backtest/tests/test_dress_rehearsal.py::TestCheck3SanityWeekendExemption` (5 tests) —
RED-proofed via a scoped `git stash -- setup/scripts/dress_rehearsal.py` (not tree-wide),
confirmed all 5 fail against pre-fix code, restored clean.
