# Conviction v2 historical replay -- does it agree with past winners?

**Generated:** 2026-08-18T18:20:49 ET  
**Status:** conviction stays DISARMED; v2 stays shadow-only. This is analysis only.

## VERDICT

> NO -- the RESPECTS/VIOLATIONS quality bar does not discriminate: C1 fires on 32/32 trendline-triggered round trips, winners and losers alike (matched-line distance from spot up to $1.1, median $0.223 -- _match_trendline has no distance cap of its own). The only outcome-linked effect comes from the SEPARATE $0.60 'AT the line' check (C4): winners 9/9, losers 17/23 -- which is architecturally a rebrand of the ALREADY-KNOWN proximity signal (prior replay: winners 96%/losers 85% within $0.60 of ANY trendline), not new evidence contributed by the quality bar.

## Method

12 days with trendline history (2026-06-26,07-08,07-09,07-10,07-13,07-14,08-11,08-12,08-13,08-14,08-17,08-18). Every closed real round trip (fills_fifo, arms safe-2, bold-2, safe-3, risky-1, risky-3) scored twice via setup/scripts/conviction.py's score_conviction() -- v0 with trendline_records=None, v2 with lines reconstructed by CALLING backtest/autoresearch/trendline_engine.py's detect() (the live producer itself, not a port) on the production trailing-lookback bar window, truncated to bars fully CLOSED at-or-before the entry instant (C6 no-look-ahead). Real spot + fired triggers joined from the nearest automation/state/core-decisions.jsonl tick (shared signal, +/-150s window). Session envelope and same-day structure side reconstructed from bars the same no-look-ahead way; level_records/level_states/confluence_zones are NOT reconstructable historically (no archive) and are passed None -- this affects the ABSOLUTE score floor for both v0 and v2 equally, never the v0-v2 delta (only C1/C4 are trendline-reachable).

DST safety: 936 target-day bars checked, 0 wall-v1/et-v2 mismatches (SAFE) -- all 12 days are EDT months so the known -04:00-year-round mislabeling bug does not apply here.

## Discrimination table -- trendline-triggered round trips only (the population v2 can actually change)

This is the table that answers the question: would ARMING conviction at floor F have kept the winners and blocked the losers, and is v2 any better than v0 at that job?

| Floor | v0 winners blocked | v0 losers blocked | v0 delta_if_armed | v2 winners blocked | v2 losers blocked | v2 delta_if_armed |
|---|---|---|---|---|---|---|
| 0 | 0/9 (0.0%) | 0/23 (0.0%) | $+0.00 | 0/9 (0.0%) | 0/23 (0.0%) | $+0.00 |
| 1 | 8/9 (88.9%) | 17/23 (73.9%) | $+236.00 | 0/9 (0.0%) | 0/23 (0.0%) | $+0.00 |
| 2 | 9/9 (100.0%) | 22/23 (95.7%) | $+199.00 | 0/9 (0.0%) | 0/23 (0.0%) | $+0.00 |
| 3 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 | 0/9 (0.0%) | 6/23 (26.1%) | $+615.00 |
| 4 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 | 8/9 (88.9%) | 17/23 (73.9%) | $+236.00 |
| 5 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 |
| 6 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 |
| 7 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 |
| 8 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 | 9/9 (100.0%) | 23/23 (100.0%) | $+199.00 |

Trendline-triggered population: n=32 (winners n=9, losers n=23).

### Score summary (trendline-triggered only)

| Group | n | v0 mean | v0 median | v2 mean | v2 median | mean delta | rows v2>v0 |
|---|---|---|---|---|---|---|---|
| Winners | 9 | 0.111 | 0 | 3.111 | 3 | 3 | 9 |
| Losers | 23 | 0.304 | 0 | 3 | 3 | 2.696 | 23 |

## Discrimination table -- FULL population (all triggers, all 5 arms, all 12 days)

For context: v0/v2 are byte-identical here except on trendline-triggered rows, so any v0-v2 gap in this table is diluted by the (majority) non-trendline population.

| Floor | v0 winners blocked % | v0 losers blocked % | v0 delta_if_armed | v2 winners blocked % | v2 losers blocked % | v2 delta_if_armed |
|---|---|---|---|---|---|---|
| 0 | 0.0% | 0.0% | $+0.00 | 0.0% | 0.0% | $+0.00 |
| 1 | 42.9% | 33.3% | $+378.00 | 14.3% | 10.7% | $+142.00 |
| 2 | 92.9% | 68.0% | $+135.00 | 60.7% | 38.7% | $-64.00 |
| 3 | 100.0% | 97.3% | $+1134.00 | 67.9% | 74.7% | $+1550.00 |
| 4 | 100.0% | 100.0% | $+1270.00 | 96.4% | 92.0% | $+1307.00 |
| 5 | 100.0% | 100.0% | $+1270.00 | 100.0% | 100.0% | $+1270.00 |
| 6 | 100.0% | 100.0% | $+1270.00 | 100.0% | 100.0% | $+1270.00 |
| 7 | 100.0% | 100.0% | $+1270.00 | 100.0% | 100.0% | $+1270.00 |
| 8 | 100.0% | 100.0% | $+1270.00 | 100.0% | 100.0% | $+1270.00 |

## Artifact hunt (run BEFORE trusting the table above)

### Does the QUALITY BAR (respects/violations) itself discriminate?

- C1 (named_level via trendline anchor) fires on **32/32** trendline-triggered round trips -- UNIFORMLY on winners AND losers (NO discrimination from the quality bar itself).
- Matched-line distance from spot (among rows where a quality line was found): n=32, mean=$0.353, median=$0.223, max=$1.1 -- 6 of those matches sit MORE than the $0.60 C4 proximity tolerance away from spot, i.e. _match_trendline's own quality gate has no distance cap and can credit a line nowhere near the trade.
- C4 ('AT the line', the $0.60 separate proximity check) fires on winners 9/9 vs losers 17/23 -- this, not the quality bar, is where any outcome-linked signal in the floor-sweep table above actually comes from.

### Concentration and proxy checks

- Rows where v2 total > v0 total (the trendline generalization actually fired): n=32
- Credited P&L by date: {"2026-07-08": 0.0, "2026-07-13": -25.0, "2026-08-11": -53.0, "2026-08-12": -106.0, "2026-08-13": -269.0, "2026-08-14": -268.0, "2026-08-17": 360.0, "2026-08-18": 162.0}
- Top day: **2026-08-17**, $+360.00 (0.29 share of GROSS credited-population P&L movement) -- not concentrated
- Correlation(minutes-since-open, n_trendline_candidates found) = -0.038 (time-of-day proxy check #1)
- Correlation(minutes-since-open, v2-v0 delta) = 0.427 -- no strong time-of-day proxy signal

## Reconstruction cross-check against REAL logged v0

core-decisions.jsonl only carries a real `conviction` field from 2026-08-13 onward. n=14 round trips joined to a row carrying one.
- Exact v0.total match: 28.6% (expected to be LOW, not a bug -- my v0 has no level_records/level_states, so it structurally cannot reach the named_level/fresh_test points a fully-informed live v0 could; the gaps in the table below are consistently explained by exactly that, e.g. logged=4 vs reconstructed=1 is a named_level(+2) + fresh_test(+1) shortfall.)
- range_extreme component match: 100.0% -- DEGENERATE: every one of these 14 rows has range_extreme=0 on BOTH sides (no variation in this subset), so this is not real validation, just a trivial agreement on zero. Reported anyway rather than hidden.
- structure_agreement component match: 71.4% -- GENUINE (both 0 and 1 appear on both sides): this caught and fixed a real bug in the FIRST run of this script -- structure_side reconstruction was silently returning None on 103/103 rows because crypto.lib.bar.Bar requires a tz-AWARE timestamp and this script was feeding it a naive one, which raised inside engine_cli._classify_sameday_5m's OWN fail-open except-block and surfaced as a look-alike 'no signal' rather than an error. Fixed by feeding the already-UTC-Zulu 't' string instead of the naive ET one; see reconstruct_structure_side()'s docstring in the tool script.

| Date | Arm | Logged v0 | Reconstructed v0 | Logged range_extreme | Reconstructed range_extreme | Logged structure | Reconstructed structure |
|---|---|---|---|---|---|---|---|
| 2026-08-13 | safe-2 | 4 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-13 | safe-2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-08-13 | safe-2 | 3 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-14 | safe-2 | 4 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-14 | safe-2 | 0 | 1 | 0 | 0 | 0 | 1 |
| 2026-08-14 | safe-2 | 0 | 1 | 0 | 0 | 0 | 1 |
| 2026-08-18 | safe-2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-08-13 | bold-2 | 4 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-13 | bold-2 | 3 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-13 | bold-2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-08-14 | bold-2 | 4 | 1 | 0 | 0 | 0 | 0 |
| 2026-08-14 | bold-2 | 0 | 1 | 0 | 0 | 0 | 1 |
| 2026-08-17 | bold-2 | 0 | 1 | 0 | 0 | 0 | 1 |
| 2026-08-18 | bold-2 | 0 | 0 | 0 | 0 | 0 | 0 |

## Limitations -- what could NOT be scored, and why

- Total closed round trips mined (5 arms, 12 days): 103.
- Unscoreable (no spot recoverable from either decision log or bars): 0.
- Trigger source breakdown: {"raw_any_tick": 84, "verdict_scoped": 9, "unknown": 10} -- 'raw_any_tick' = high-fidelity (post-2026-07-27 schema, every tick logs bear/bull_triggers_raw regardless of verdict); 'verdict_scoped' = pre-07-27 days, only trustworthy when a same-side ENTER verdict landed within the join window; 'unknown' = no matching decision row found -- these rows are conservatively treated as NON-trendline-triggered (v0==v2), which can only UNDER-count v2's population, never inflate it.
- Spot source breakdown: {"decision_log": 103} -- 'decision_log' is the real live tick value; 'bar_close_fallback' is the closed 5m bar's close at-or-before entry (used mainly for fleet-arm entries the core tick log didn't mirror within the join window).
- level_records, level_states, confluence_zones: NOT reconstructed (no historical archive of key-levels.json / confluence-zones.json exists for these 12 days). Passed None to both v0 and v2 uniformly -- degrades named_level (level path)/fresh_test/zone_stack identically for both scores, so it cannot bias the v0-v2 DELTA, only compresses the absolute floor-sweep numbers toward the low end for both.
- k (entries-used-today, feeds the escalating ratchet floor): approximated as this arm's own same-day entry sequence number, not the true per-account settlement counter (unavailable historically). The floor-sweep tables above use a FLAT floor sweep (score < F), not the ratchet, specifically to avoid depending on this approximation.

## Raw data

Full per-row detail (all reconstructed trendline candidates, both score breakdowns) in the JSON sidecar: `analysis/deep-research/CONVICTION-V2-HISTORICAL-REPLAY-2026-08-18.json`.
