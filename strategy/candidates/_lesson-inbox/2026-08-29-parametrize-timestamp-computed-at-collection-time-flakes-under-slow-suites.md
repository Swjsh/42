# Lesson candidate: `@pytest.mark.parametrize` values computed at collection time create a time-bomb flake in a slow full-suite run

**Filed:** 2026-08-29, conductor AFTERHOURS/WEEKEND fire, while triaging the 2026-08-28 23:46 ET
FULL-SUITE RED (10336 passed, 15 failed).

**What happened:** 12 of the 15 failures were a real, already-diagnosed root cause (risky-3
retirement leaving 6 tests pinned to the old 5-arm roster) that a prior fire (commit
`e911499e`) had already fixed by the time this fire ran. The remaining 3 —
`test_discord_bridge_staleness_2026_08_12.py::test_all_three_on_disk_timestamp_formats_parse[...]`
— were NOT a regression at all. Re-run individually (and as a whole file) they passed
instantly. Root cause: the test used
```python
@pytest.mark.parametrize("stamp", [
    _ago(minutes=30).isoformat().replace("+00:00", "Z"),
    _ago(minutes=30).isoformat(),
    _ago(minutes=30).replace(tzinfo=None).isoformat(),
])
def test_all_three_on_disk_timestamp_formats_parse(bridge, stamp):
    age = bridge._row_age_min({"queued_at": stamp})
    assert 25 < age < 35
```
`_ago(minutes=30)` runs ONCE, at **pytest collection time** (parametrize argument lists are
evaluated when the module is imported/collected, not when the test body runs). The assertion
`25 < age < 35` is checked at **execution time**. In a normal fast run collection and
execution are seconds apart, so the ±5min window always holds. In a **10,000+ test full-suite
run that takes 20+ minutes wall clock**, if this file's test happens to execute more than
~5 minutes after the whole suite was collected, the window slips and the test fails with no
code regression behind it — a self-inflicted, load-dependent flake.

**Fix applied:** moved `_ago(minutes=30)` INSIDE the test body (parametrize over a format tag
string instead of a precomputed timestamp), so the timestamp is generated at execution time,
when the assertion window actually needs to hold. File:
`backtest/tests/test_discord_bridge_staleness_2026_08_12.py`.

**Generalizable rule (candidate L#):** any `@pytest.mark.parametrize` argument that embeds
`datetime.now()` / `time.time()` / any wall-clock value MUST be computed inside the test
function (or via an `indirect=True` fixture), never in the parametrize decorator's argument
list. A parametrize list is evaluated once at collection time for the whole session; a test
asserting a narrow window against "now" needs "now" to mean "when I actually run", not "when
pytest imported this file." This is the same class of bug as C6 (no look-ahead: filter <=
current bar) but applied to test infrastructure instead of trading logic — a producer/consumer
timing mismatch between when a value is stamped and when it is checked.

**Sweep not yet done (out of scope this fire):** grep the test suite for other
`@pytest.mark.parametrize` argument lists that call `datetime.now()`/`_ago()`/`time.time()`
directly in the decorator (as opposed to inside the test body) — this exact file was the only
one FOUND failing this run, but the pattern could exist elsewhere and just not yet have hit an
unlucky collection-to-execution gap.

**Evidence:**
- `automation/overnight/STATUS.md` 2026-08-28 23:46 ET FULL-SUITE RED entry (original 15 failures).
- `git show e911499e` (prior fire's fix for the other 12).
- This fire: individually re-ran all 15 originally-failed tests — 12 already green from the
  prior commit, 3 (discord-bridge-staleness) green on isolated re-run, confirming timing not
  code as the cause; then applied the collection-vs-execution-time fix and re-verified
  `pytest tests/test_discord_bridge_staleness_2026_08_12.py -q` → `16 passed`.
