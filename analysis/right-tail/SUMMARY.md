# RIGHT-TAIL CAPTURE -- backfill summary (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R4)

Backfilled 2026-08-01 -> 2026-09-04 (last trading day before today, Saturday
2026-09-05), 25 trading weekdays, 0 errors. Writes:
`analysis/right-tail/CAPTURE-<date>.json` (one per day, 25 files) +
`analysis/right-tail/ledger.jsonl` (240 rows).

**CORRECTION (2026-09-05, reader-truncation fix)**: this file originally
claimed core-decisions.jsonl "has NO rows before 2026-08-26" and ran
2026-08-01 -> 2026-08-25 in FLEET_FALLBACK mode on that basis. That claim was
FALSE -- see `backtest/lib/right_tail_waves.py`'s module docstring for the
full mechanism (a `_decisions_for_day` reader that filtered strictly on a
`date` key `heartbeat_core.py` only started writing on 2026-08-25; every
earlier row carries `ts_et` only and was silently excluded). The reader now
falls back to `ts_et[:10]`, and 2026-08-01 -> 2026-08-25 (17 trading days)
has been RE-BACKFILLED in the correct `CORE_SCORE` mode. Every table below
reflects the re-backfilled numbers. `2026-08-26 -> 2026-09-04` was already
correct (those rows do carry a `date` field) and is unchanged.

## Wave source mode by date range

- **2026-08-01 -> 2026-08-25** (17 trading days): `CORE_SCORE` mode (bear/
  bull score >= 9, zero blockers, deduped to unique 5-min bars via
  `zero_enter_autopsy._dedup_by_bar`) -- the literal mechanism the goal text
  specified, now correctly selected for the whole backfill window.
- **2026-08-26 -> 2026-09-04**: `CORE_SCORE` mode, unchanged.
- `FLEET_FALLBACK` mode is a documented degrade path that no longer fires
  anywhere in this backfill window -- every date in it has real
  core-decisions.jsonl coverage. It remains available (and RED-proof tested)
  for a genuinely missing day.

## The five August big days -- re-verified against the CORE_SCORE numbers

CORE_SCORE mode is anchored to the `safe` core account's own admission ticks
-- a genuinely different, independent eligibility source from the fleet
arms' own admission gates the old FLEET_FALLBACK anchor used. It does NOT
reproduce the same wave count/times/peaks the FLEET_FALLBACK-era numbers
below (previously reported here) showed; this is evidence, not forced:

| Day | Doctrine shape | OLD (FLEET_FALLBACK, wrong mode) | NEW (CORE_SCORE, correct mode) |
|---|---|---|---|
| 08-04 | BULLISH_RECLAIM, gap-go, 09:41-10:22 wave + noon wave (12:28) | 4 waves, peaks 5.44x/5.90x/3.01x/1.83x | 4 waves at 10:00/13:00/13:35/15:40 ET, peaks 7.0758x/2.1849x/1.7091x/1.1011x (3 of 4 clear 1.3x). Per-arm: safe-2 3/3, bold-2 1/3, safe-3 3/3, risky-1 1/3. |
| 08-06 | BEARISH_REJECTION mirror, range-chop | 1 wave (peak 1.85x) | **0 waves** -- no bar on 08-06 has bear_score>=9 with zero bear_blockers on the `safe` account after `_dedup_by_bar`'s last-occurrence-per-bar dedup. The doctrine-documented bear mirror does not show up as a core-safe-account admission tick this day. |
| 08-13 | BULLISH_RECLAIM, gap-go | 3 waves | **1 wave** at 14:30 ET, peak 2.459x, clears 1.3x. Per-arm: safe-2 1/1, bold-2 0/1, safe-3 1/1, risky-1 1/1. |
| 08-27 | BULLISH_RECLAIM, gap-go | 3 waves | unchanged (08-27 already ran CORE_SCORE mode pre-fix; not in the re-backfilled window) |
| 08-28 | BULLISH_RECLAIM, range-chop | 1 wave | unchanged (same reason) |

**Read this honestly**: 08-04 keeps the qualitative shape (a big morning wave
+ a smaller afternoon wave) but different exact times/peaks; 08-06 and 08-13
reproduce a WEAKER version of the doctrine anchor (0 waves and 1 wave
respectively) under the doctrine-specified CORE_SCORE mechanism than the
FLEET_FALLBACK numbers previously reported. This is a genuine finding about
`_dedup_by_bar`'s "last occurrence per 5-min bar wins" semantics (borrowed
correctly from `zero_enter_autopsy.py` for day-level grading, not redesigned
here) interacting with a single-account (`safe`) admission signal that can
flicker in and out of eligibility within one 5-min bucket -- e.g. 08-04's
real 09:58:03 ENTER-eligible tick (`triggers: ["level_reclaim","confluence"]`,
bull_score 11, matching edge-master-doctrine.md exactly) is overwritten in
its 09:50 bucket by a 10:00:04 row that picked up a blocker, so the wave
that's actually found starts at the NEXT bucket (10:00) instead. Flagged as a
finding for a future goal, not silently re-tuned here (scope: this fire's
task was the reader-truncation fix + backfill, not `_dedup_by_bar`'s design).

**08-04's safe-2 P&L cross-check** (unchanged by this fix -- fills-ledger.jsonl
data, not core-decisions.jsonl): the goal text's DONE-WHEN asks this day to
reproduce "safe-2 +$758". The two paying waves' real fills
(journal/trades.csv, strikes 763/769/772: 270+113+254+121) gross +$758 --
that number IS right, it is the two paying waves' GROSS. safe-2's actual DAY
NET is +$662, which also includes a real 13:41 ET loss (-$96) the gross
figure excludes. Both numbers are correct; they answer different questions
(gross of the two winning waves vs. the account's full-day net) -- neither
supersedes the other.

## Per-arm capture rate, whole backfill (35 total waves/arm)

| Arm | Taken | Total waves | Capture rate |
|---|---|---|---|
| safe-2 | 25 | 35 | 71.4% |
| bold-2 | 18 | 35 | 51.4% |
| safe-3 | 21 | 35 | 60.0% |
| risky-1 | 19 | 35 | 54.3% |

(Previously reported, wrong-mode numbers: safe-2 79.4%, bold-2 61.8%, safe-3
73.5%, risky-1 85.3% of 34 waves -- risky-1's drop is the largest because the
old FLEET_FALLBACK waves were partly ANCHORED TO risky-1's own admission
ticks, self-referentially inflating its apparent capture rate; CORE_SCORE
mode breaks that self-reference by anchoring to an independent account.)

## Refusal attribution (all arms, all missed waves, whole backfill)

| Gate | Count |
|---|---|
| No matching fleet decision row found (arm never fired an admissible tick near the wave -- fail-open label, not a gate name) | 44 |
| `NOT_FLAT` (risk_gate: position already open) | 5 |
| `SKIP_MIN_PREMIUM_FLOOR` (premium below the 0.30 min_entry_premium floor) | 8 |

`would_be_refused_under_cap4` (max_same_day_roundtrips=4) flags: **10** across
the whole backfill (was 13 under the wrong mode). No `FLEET_SETTLEMENT_CAP`
refusal was observed as the ACTUAL blocking reason for any missed wave in
this window -- the cap only ever bound on entries #5+ that were STILL taken.
This matches edge-master-doctrine.md's own finding ("It first bound on 09-03
... 28 refusals ... cost nothing that day") -- still true post-fix; the
forward ledger (`Gamma_RightTailCapture`, running daily) is what will catch
it if that changes before the 09-29 checkpoint.

## Second-wave presence

10 of 25 days (40%) had a second wave (>=60 min after the first wave's
start, per the goal's definition) somewhere in the day's wave list (was 7/25
under the wrong mode).

## Known approximation caveats (stated, not hidden)

- Entry premium = the OPRA bar at/after (wave-start + 5 min)'s `open` +
  `DEFAULT_ENTRY_SLIPPAGE` (`simulator_real.py`'s real cost model) -- an
  approximation of the "next-bar" fill convention already documented in
  `option_pricing_real.py`, not a tick-level replay.
- Peak multiple scans the ENTIRE remaining session (through 16:00 ET), not
  just the arm's own actual hold window -- this measures "how big could this
  wave have gotten", which is why several peaks (5-6x) run well above the
  ~2-3.5x the arms' real fills captured (per edge-master-doctrine.md) even on
  days the arms captured the wave correctly to TP1.
- `_find_entry_fill`'s matching window allows a 10-minute lookback before the
  detected wave-start tick (originally justified by a since-superseded
  FLEET_FALLBACK-era anchor for 08-04; the tolerance itself is unaffected by
  the CORE_SCORE reader fix and is kept as designed) -- a per-arm real fill
  slightly ahead of the wave-detection anchor is still credited as "taken".
