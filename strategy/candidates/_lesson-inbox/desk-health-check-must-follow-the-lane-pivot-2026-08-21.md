## Desk health-check functions must be re-pointed when a lane pivots to a new producer

**Symptom:** `desk_allocator.py`'s `assess_prediction_markets()` permanently reported
the prediction-markets desk as BROKEN / 0-progress, even though the Kalshi weather
lane (`Gamma_KalshiAuto`, 18:10 ET daily) had been running clean every day since
2026-08-09, most recently writing `weather-predictions.jsonl` at 2026-08-20T22:10 UTC.

**Root cause:** the health check read `last-tick.json` / `shadow-ledger.jsonl` —
files belonging to `kalshi_tick.py`, the ORIGINAL SPY-directional Kalshi lane. That
lane was superseded the SAME DAY it shipped (2026-08-09) by `kalshi_auto.py`, the
weather lane (a deliberate pivot, not a failure — no scheduled task for
`kalshi_tick.py` was ever registered, confirmed via `Get-ScheduledTask`). The
check's OWN 2026-08-20 fix comment even names the exact bug class ("a row count is
a measure of history, not of life") and still missed that it was pointed at a
retired sibling entirely, not just using the wrong metric on the right file.

**This is the SAME bug class caught once already, same file, one function up**:
`assess_multi_sector()` was fixed on 2026-08-20 for exactly this shape — two lanes
share a desk, one dies, and a check written against "a" lane instead of "the live"
lane goes permanently stale. Two occurrences in one file in 24 hours.

**Generalizable rule:** whenever a lane/script is retired in favor of a successor
(a pivot, not a crash), grep the WHOLE repo for readers of the RETIRED lane's
output files before considering the pivot done. `gamma_cockpit_data.py`'s kalshi
engine-tick block has the SAME latent read (`shadow-ledger.jsonl` / `last-tick.json`)
and was NOT fixed this fire (display-only surface, lower urgency than the
allocator's decision-input role — filed as a queue.md follow-up instead of fixed
here, to keep this fire bounded).

**Suggested guard pattern for future pivots:** when a producer script is retired,
either (a) have it write ONE final `{"retired": true, "successor": "..."}` marker
so every consumer can distinguish "intentionally retired" from "silently died", or
(b) grep-audit every consumer of its output path before calling the pivot shipped.

**Fix:** `setup/scripts/desk_allocator.py#assess_prediction_markets()` now reads
liveness + progress from `weather-predictions.jsonl` (the live producer) via a
small inline stdlib-only scorecard re-derivation, not `kalshi_auto.py`'s own
`scorecard()` (avoided importing it to keep the allocator's zero-external-deps
design intact — that module pulls in `requests` + `cryptography` for its live
trading path). 7 new guard tests:
`backtest/tests/test_desk_allocator_kalshi_lane_fix_2026_08_21.py`.

**Not fixed this fire (follow-up filed, queue.md):** `gamma_cockpit_data.py`'s
kalshi engine block (same stale-file read, display-only, lower urgency).
