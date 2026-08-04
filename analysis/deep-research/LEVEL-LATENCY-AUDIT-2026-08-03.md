# LEVEL LATENCY AUDIT — "play the levels like a violin" (LANE 4, 2026-08-03 evening)

**Verdict: the level pipeline's eye was 15 minutes behind the tape — root-caused, fixed
tonight (IEX real-time tail), and the violin metric is now a nightly number.**

J's directive (verbatim): *"playing these key levels like a violin"* + *"check every step
of the pipeline... 'we didn't account for those three things to happen, so the fourth thing
couldn't happen, and we didn't trade' — that's not gonna fly."*

---

## 1. The known case, forensically closed

749.33 (final premarket low AND the bias-file support) — respected 09:25-09:29, in
`levels_active` **09:44:03**. The chain, minute by minute (all quoted from
`automation/state/logs/level-refresh-2026-08-03.log` + `core-decisions.jsonl`):

| Fire (ET) | INTRADAY_PML written | `spot` in output | What the frame could see |
|---|---|---|---|
| 09:28:36 | 749.65 | 751.07 | bars through ~09:13 |
| 09:33:36 | **749.65 (stale)** | 751.35 | bars through ~09:18 |
| 09:38:36 | **749.65 (stale)** | 751.25 | bars through ~09:23 |
| 09:43:36 | **749.33 (finally)** | 749.39 = the 09:25 bar's close | bars through ~09:28 |
| 09:48:36 | 749.33 | 750.74 = the 09:30 bar's close | first RTH bar visible; RTH H/L refused "only 1 bar(s)" **18 min into the session** |

Engine ledger: 749.65 in `levels_active` from 09:30:04; 749.33 first at **09:44:03** (the
tick after the 09:43:36 write). 

**Root cause (one sentence):** `refresh_levels_intraday.py`'s SIP bars request is served a
**~15-minute-delayed window on this key's data plan** (free tier = real-time IEX +
delayed SIP), so every intraday level was born feed-delay + refresh-cadence + engine-read
(~15-20 min) after the tape made it.

Competing hypotheses killed: limit-truncation (7-day SIP ≈ 1,000 bars < the 1,500 limit;
truncation freezes the OLD end, not a sliding 15-min lag) · task-not-firing (log shows every
5-min fire `ok:true`) · 09:30-09:35 stale-guard blanking (**it does NOT blank levels** —
ledger rows carry 18-19 levels through the whole window; the guard only relabels the
tick's ACTION) · hysteresis holding the old price (label-identity retires it instantly, and
the refresher itself *wrote* 749.65 — upstream data, not carry).

## 2. Per-source latency mechanisms (the "name the mechanism" table)

| Source | First availability observed (08-03) | Mechanism of the gap |
|---|---|---|
| daily_context shelves (08:33) | at the open (09:28:36 file) | **No intraday gap** — derived from daily bars premarket. Failure mode was the 07-31 re-derivation flicker, already fixed by WS3 hysteresis (5 flips Mon vs 14 Fri). |
| INTRADAY_PMH/PML | final value 09:43:36 (should exist by 09:29) | **15-min SIP delay** + 5-min cadence (:x3:36/:x8:36 phase) + ≤1-min engine read. The last premarket fire (09:28:36) sees only ~09:13. |
| INTRADAY_RTH_HIGH/LOW | 09:53:36 (open + 23 min) | Same 15-min delay **+ 3-bar degeneracy warmup** (needs 3 *visible* RTH bars: 3rd completes 09:45, visible ~09:48 fire) — and the *running* extreme stays 15-20 min stale all day. |
| INTRADAY_SWING_H/L | 10:23:36 | Same delay + 5-bar pivot warmup on the delayed frame. |
| memory levels (10-min producer) | 59m median latency on 07-28 (violin) | Separate producer on **yfinance** bars + 10-min cadence + score threshold — slower by construction; multi-day levels rarely need intraday speed. |
| trendline engine (5-min RTH) | n/a (sloped) | **feed=iex → real-time; no feed delay.** Latency = 09:30 task start + 5-min cadence. Premarket: task simply does not run (see §4). |
| prior_day H/L/C | close: **0/15 covered** across 07-28/29 | Not a latency gap — a **dead-knob gap (C14)**: `LEVEL_WEIGHT_PRIOR_DAY_HLC` exists but NO producer writes fresh prior-day levels; the file's PRIOR_CLOSE is from June. Queued (below), not shipped tonight. |

## 3. Fixes shipped tonight (paper-path, guarded, one-line reverts)

1. **IEX real-time tail** (`refresh_levels_intraday.py::_merge_iex_tail`): the delayed-SIP
   spine is supplemented with IEX bars strictly newer than the SIP tip. Per-bar volume floor
   `TAIL_MIN_BAR_VOLUME = DEGENERACY_MIN_VOLUME / DEGENERACY_MIN_BARS` (derived, not
   hand-picked) keeps the 07-27 80-share single-print wound closed; a thin/failed tail
   degrades to the exact pre-fix SIP-only frame (fail-open). Effect on the 749.33 shape:
   final PML lands at the **09:33:36 fire → levels_active by ~09:34, ahead of the 09:35
   window-open**. The stale-bar guard is UNTOUCHED (heartbeat_core not edited).
   Guards: `test_level_refresh_iex_tail_2026_08_03.py` (10/10, both directions RED-proofed)
   + updated feed-shape guard in `test_level_compiler_v2_guards.py`. Full level suite 50/50.
   Live-verified after hours: `ok:true`, tail correctly no-op on a closed market.
   *Revert: `git revert` the refresher commit.*
2. **UTF-8 refresh log** (`run-level-refresh.ps1`): PS 5.1 `*>>` writes UTF-16LE — every
   refresh log was unreadable to grep/tail (tonight's audit had to decode it). Now explicit
   UTF-8 append + a loud NONZERO EXIT marker line. (This was the orphaned "Data hygiene"
   lane's `run-level-refresh.ps1` item — root cause was the redirect operator's encoding.)
3. **Trendline carry-over visibility** (`premarket_readiness.py` check 8,
   `trendline_watch`, advisory-only): Gamma_Trendlines runs 09:30-16:00 ET only, so at 09:00
   the watch file holds the PRIOR session's lines — now visible on the readiness gate.
   Live-verified against the real file: `3 line(s) carried from 2026-08-03; nearest support
   [WICK] 757.58 (TESTING); producer resumes 09:30 ET`. Can never RED (fuse ceiling), the
   graveyarded entry-signal form stays dead. Suite 37/37 incl. the never-RED RED-proof.
4. **The violin metric, nightly** (`violin_metric.py` + `Gamma_ViolinMetric` 17:35 ET,
   registered State=Ready, real DailyTrigger, smoke-fired through the real wscript chain —
   artifacts verified: stdout table + `violin-metric.json` + history upsert). Definition
   FROZEN as v1-2026-08-03 (TOL $0.15 = zone floor, REACT $0.50/2 bars, match ±$0.10 =
   ROLE_EPSILON, premarket respects covered iff active by the 09:36 window-open tick).
   Guards: `test_violin_metric_2026_08_03.py` (6/6).

## 4. Trendline Tuesday-morning readiness (Part 3 verdict)

- The 5-min task **resumes at 09:30 ET sharp** (StartBoundary 07:30 MT, PT5M × PT6H30M,
  Mon-Fri) — it does NOT run premarket, and its bar feed is real-time IEX.
- A line carried overnight IS on disk (`trendline-watch.json`, dated 08-03, Monday's
  x60-respected wick support TESTING at the close) and is now visible at **08:45** (morning
  brief `premarket_line`, pre-existing WS8 wire) and **09:00** (readiness gate check 8,
  shipped tonight). Engine-side premarket evaluation was deliberately NOT enabled —
  that would be a behavior change on a graveyarded signal form, not visibility.

## 5. The violin table (first honest 5 sessions, defn v1-2026-08-03)

| Session | Coverage | Respects | The story |
|---|---|---|---|
| 2026-07-28 | 66.7% | 76/114 | level_memory 59m median latency; prior_day_close 0/9 |
| 2026-07-29 | 44.8% | 43/96 | worst live day: PMH 232m late, RTH-high 1/8, prior-day family ~0/14 — **unexplained beyond the SIP delay; flagged for the trend to watch** |
| 2026-07-30 | **0.0%** | 0/27 | the LEVELS-BLINDNESS day (LevelRefresh disabled) — **the metric independently re-detects the known incident; instrument self-validates** |
| 2026-07-31 | 84.1% | 69/82 | best day (hysteresis ship day) |
| 2026-08-03 | 75.0% | 21/28 | the 749.33 miss is the premarket_low 1/2; RTH-high 2/7 |

Recurring bleeders across all live days: `intraday_rth_high/low` (28-70% coverage — the
15-min delay + warmup, addressed by fix #1) and the `prior_day_*` dead-knob gap (§2).
Trendlines reported separately (sloped): 3 active, 149 engine-counted respects Monday.

## 6. Queued follow-ups (measured, not shipped tonight — bounded blast radius)

1. **PRIOR-DAY-HLC-LEVELS**: wire fresh prior-day RTH H/L/C into the refresher (weight-3
   constant already exists, dead). Violin shows 0/15 coverage on that family; the fix is
   additive and cheap; ship next after-hours window with its own guard.
2. **07-29 anomaly**: 44.8% coverage predates the blindness day — one session's forensics
   (was the premarket compile late? curated levels wrong?) once the violin trend has 2-3
   more nights.
3. **Plan upgrade option (J's call, $)**: Alpaca Algo Trader Plus (~$99/mo) = real-time SIP
   for the level file; the IEX tail makes this optional, not urgent. REVOKE-surface item,
   NOT auto-actioned (no net-new paid vendors without J).

*All numbers in this doc are real-fill/real-tape derived (SIP bars, engine ledger, refresh
logs). No sim. n-small labeled where applicable (5 sessions).*
