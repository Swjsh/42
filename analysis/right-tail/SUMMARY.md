# RIGHT-TAIL CAPTURE -- backfill summary (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R4)

Backfilled 2026-08-01 -> 2026-09-04 (last trading day before today, Saturday
2026-09-05), 25 trading weekdays, **0 errors** (`python
scratchpad/backfill_right_tail.py` this session: "backfilled 25/25 days, 0
errors"). Writes:
`analysis/right-tail/CAPTURE-<date>.json` (one per day, 25 files) +
`analysis/right-tail/ledger.jsonl` (240 rows).

**R4 ROOT-CAUSE FIX (2026-09-05, this fire)**: R4 was REOPENED because the
CORE_SCORE wave detector did not reproduce edge-master-doctrine.md's "August
2026 big-day anatomy" anchors (08-04 wrong times/peaks, 08-06 zero waves,
08-13 1 of 3 waves). Root cause, confirmed by discriminating evidence
against the real `core-decisions.jsonl` rows (`backtest/lib/
right_tail_waves.py`'s module docstring has the full hypothesis table):

1. **Wrong anchor.** The old test (`bull_score/bear_score >= 9, zero
   blockers`) is not a discrete trigger -- once a ribbon reclaim fires, the
   score/blockers fields stay >= 9 / empty for the REST of the session (they
   encode "still admissible right now", not "a new trigger just fired"). The
   real admission tick is `core-decisions.jsonl`'s own `verdict` field
   (`ENTER_BULL`/`ENTER_BEAR`), which the old reader never looked at.
2. **Wrong dedup.** `zero_enter_autopsy._dedup_by_bar` keeps the LAST row per
   5-min bucket -- correct for its own job (grading a NO-ENTER day) but wrong
   here: a bar with a real `09:56:03 ENTER_BULL` row often got a later
   `10:00:04 HOLD` row (already-in-position blocker) in the SAME bucket,
   silently overwriting the entry and producing the 7.0758x artifact (a
   different bar/contract than the real entry).
3. **Single-account undercount.** 2026-08-06's real `ENTER_BEAR` tick scored
   `bear_score=8` (below the old threshold of 9) -- the score/blockers proxy
   simply does not track the engine's own entry decision, which is why 08-06
   showed 0 waves. Separately, 2026-08-27's 11:52 doctrine wave only exists
   in the `bold` core account's own `ENTER_BULL` rows; a `safe`-only reader
   misses it and reports the wrong, 39-minutes-later start (12:31) instead.

**Fix**: `find_waves` now anchors CORE_SCORE eligibility directly on
`verdict` in {ENTER_BULL, ENTER_BEAR} rows whose `setup` is the doctrine
two-trigger ribbon shape (`BULLISH_RECLAIM_RIDE_THE_RIBBON` /
`BEARISH_REJECTION_RIDE_THE_RIBBON`), unioned across both core accounts
(`safe` + `bold`) -- no score threshold, no bar-dedup. RED-proofed:
`backtest/tests/test_right_tail_waves.py` (10/10 green post-fix; the OLD
fixture asserting the stale 10:00/13:00/13:35/15:40 numbers now fails
against the fixed code, which is the RED-proof for this change).

## The five August big days -- re-verified against the fixed detector

| Day | Doctrine anchor | Detected start | Gap | Peak multiple | Meets 1.3x |
|---|---|---|---|---|---|
| 08-04 | 09:56 (cores) | 09:56:03 | 0 ticks | 5.4421x (tape truth; real runner exits capped at 3.29-3.34x -- see caveat below) | yes |
| 08-04 | 12:28 (2nd wave) | 12:26:03 | 2 ticks early | 3.0137x (within 8-10% of the real 3.29x/3.34x runner exits) | yes |
| 08-06 | 10:31-10:32 (bear) | 10:31:03 | 0 ticks | 1.8543x (inside the real fills' 1.325x-2.117x realized-exit range) | yes |
| 08-13 | 09:51 (~2.0-2.2x) | 09:51:03 | 0 ticks | 1.875x | yes |
| 08-13 | 14:36 (~2.0x) | 14:36:04 | 0 ticks | 1.7045x (15% off, borderline-in-tolerance) | yes |
| 08-27 | 09:41 (1.3-1.6x realized) | 09:41:02 | 0 ticks | 2.8824x (tape truth; see caveat) | yes |
| 08-27 | 11:52 (~2.0x) | 11:51:04 | 1 tick early | 1.9685x (1.6% off, tight) | yes |
| 08-28 | 10:21 (~2.0x) | 10:21:02 | 0 ticks | 2.9733x (tape truth; see caveat) | yes |

All eight doctrine anchors reproduce within 2 ticks on start time and all
clear the 1.3x wave-existence threshold. Three peaks (08-04 09:56, 08-27
09:41, 08-28 10:21) exceed the 15% tolerance against the REALIZED runner
exit multiple quoted in the doctrine text -- see caveat below; this is a
verified, tape-confirmed existence-vs-capture gap, not a detector bug, and
was NOT closed by narrowing the pricing window (which would be tuning to the
fixtures, out of scope for this fix).

**Caveat, verified this session**: for those three waves, SPY kept
genuinely drifting for hours after every arm's own trailing-stop/time exit
(08-27 09:41 wave: SPY 768.20 at 09:41 -> 772.00 at 13:10, verified via
`core-decisions.jsonl`'s `spy` field and the OPRA 5-min bars for
`SPY260827C00768000`) -- the wave's SESSION peak legitimately exceeds what
any arm captured. R2's per-arm join (capture rate below) is exactly the
instrument that scores this gap; R4's job was correctly detecting the wave's
existence and start tick, which it now does.

## Wave source mode

Every date in the 2026-08-01 -> 2026-09-04 backfill window resolves to
`CORE_SCORE` mode (real `core-decisions.jsonl` coverage exists for all of
it, verified via `_core_decisions_has_date`). `FLEET_FALLBACK` remains
available (and RED-proof tested) as a documented degrade path for a
genuinely missing day; it never fires in this window.

## Per-arm capture rate, whole backfill (36 waves/arm -- unioning both core
accounts for wave detection changes the wave universe vs. the earlier
`safe`-only default)

| Arm | Taken | Total waves | Capture rate |
|---|---|---|---|
| safe-2 | 29 | 36 | 80.6% |
| bold-2 | 22 | 36 | 61.1% |
| safe-3 | 21 | 36 | 58.3% |
| risky-1 | 26 | 36 | 72.2% |

(Superseded numbers from the pre-R4-fix backfill: safe-2 71.4%, bold-2
51.4%, safe-3 60.0%, risky-1 54.3% of 35 waves -- those were PROVISIONAL per
R4's reopen note and are replaced by the table above now that R4 is closed.)

## 20-session cockpit tile (verified this session)

`python -c "from gamma_cockpit_righttail import build; print(build())"`:
**20-session book capture 67%, 8 cap-4 would-refuse flags** (verdict
"amber"). Per-arm 20-session capture: safe-2 76.7% (23/30), bold-2 66.7%
(20/30), safe-3 56.7% (17/30), risky-1 66.7% (20/30).

## Refusal attribution (all arms, all missed waves, whole backfill)

| Reason | Count |
|---|---|
| No matching fleet decision row found near the wave (fail-open label, not a named gate) | 43 |
| `NOT_FLAT` (risk_gate: position already open) | 3 |

`would_be_refused_under_cap4` (max_same_day_roundtrips=4) flags: **11**
across the whole backfill. No `FLEET_SETTLEMENT_CAP` refusal was observed as
the ACTUAL blocking reason for any missed wave -- consistent with
edge-master-doctrine.md's own finding that the cap only ever bound on
entries #5+ that were still taken.

## Second-wave presence

9 of 25 days (36%) had a second wave (>=60 min after the first wave's start)
somewhere in the day's wave list.

## Known approximation caveats (stated, not hidden)

- Entry premium = the OPRA bar at/after (wave-start + 5 min)'s `open` +
  `DEFAULT_ENTRY_SLIPPAGE` (`simulator_real.py`'s real cost model) -- the
  documented "next-bar" fill convention, not a tick-level replay.
- Peak multiple scans the ENTIRE remaining session (through 16:00 ET), not
  the arm's own actual hold window -- this measures "how big could this
  wave have gotten", which is why some peaks run well above what any arm's
  real fills captured (see the three-wave caveat above) even on days the
  arms captured the wave correctly to TP1.
- A missing OPRA 5-min cache for the exact ATM strike (e.g. 08-28's second
  wave, strike 775, no `analysis/options` cache row despite a `highres`
  1-min file existing) degrades that one wave to `computed: False` with a
  labeled reason -- fail-open, not a crash, not a fabricated number.

## 1-min re-walk (GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3)

`backtest/lib/right_tail_waves.find_waves`/`_price_wave` gained a `resolution` param
("5min" default, unchanged behavior; "1min" reads `backtest/data/highres/` read-only via the
shared `_option_bars_1min_cache.load_1min_cache_readonly`, falling back to the 5-min cache
per-row on a miss -- disclosed via `resolution_used`/`resolution_1min_fallback`, never a
silent blend). `setup/scripts/right_tail_capture.py` exposes it as `--resolution`, plus
`--out-suffix`/`--ledger-path` so the re-run writes `CAPTURE-<date>-1min.json` (25 files,
2026-08-03..2026-09-04) and `analysis/right-tail/ledger-1min.jsonl` without touching the
originals.

Ran all 25 days at `--resolution 1min`. Over the 140 scored rows present in both ledgers:
- **peak_multiple_on_tape**: mean delta (1min - 5min) = **+0.0057**, small and consistent
  across all 4 arms (safe-2/bold-2/safe-3/risky-1 each +0.0057 -- they share the same
  underlying waves, so this is expected, not 4 independent confirmations).
- **`taken` (capture) never flipped**: 0/140 rows changed taken/not-taken between
  resolutions.
- **capture_rate** (per-arm daily aggregate) shifted a little either way: safe-2 -0.0417,
  bold-2 +0.0250, safe-3 -0.0125, risky-1 -0.0125 (mean deltas over 20 day-rows per arm) --
  no arm's qualitative capture story (which days had a second wave, which arm's rate is
  higher) changed.

Full per-row numbers: `automation/state/goals/_opra_1min_righttail_deltas_2026_09_05.json`.
