# B2 -- SCHEDULED-RELEASE BLACKOUT STUDY (2026-09-03, stamp 12:40 ET)

**Generated:** 2026-09-03T12:54:13.690039 · **Script:** `backtest/tools/release_gap_study.py` · **B1 source:** `setup/scripts/macro_calendar.py#scheduled_releases (imported live, confirmed usable)`

**Study window:** 2026-06-26 .. 2026-09-02 (44 trading days with an archived SPY 1-min cache). **2026-09-03 is EXCLUDED from the cached-bar distributional sections (2) below** -- its SPY 1-min cache has not been archived yet (market open at build time) -- but IS included in the fills-ledger-driven sections (3)/(4), which need only fill timestamps. This asymmetry is intentional and stated once here, applies everywhere below.

## 1. Release calendar over the study window (B1 `scheduled_releases`, ISM tier-1 + secondary)

- **ISM (tier-1, severity=high) days:** 5 -- 2026-07-01, 2026-07-06, 2026-08-03, 2026-08-05, 2026-09-01
- **Secondary-only (CB/UMich, severity=med, RULE_BASED_UNVERIFIED) days:** 6 -- 2026-06-26, 2026-06-30, 2026-07-28, 2026-08-14, 2026-08-25, 2026-08-28
- **Non-release days:** 33
- **Named ISM days from this task's briefing:** 2026-08-03, 2026-08-05 -- both confirmed ISM in the calendar above.

**Four named winning days, checked against the calendar:**

| Day | ISM (tier-1)? | Secondary 10am event? |
|---|---|---|
| 2026-08-06 | False | False (none) |
| 2026-08-13 | False | False (none) |
| 2026-08-27 | False | False (none) |
| 2026-08-28 | False | True (umich_sentiment_final) |

2026-08-28 carries a **secondary** (`umich_sentiment_final`) release, not ISM. The frozen candidate rules (R1/R2/R3, see §4) are scoped to **ISM-only** ("tier-1" per this task's own wording) so 2026-08-28 is untouched by the frozen rules; §4 also reports an EXPLORATORY ISM+secondary variant for transparency, never part of the frozen decision.

## 2. SPY $ and option % moves across the 10:00 ET window

### SPY, |move| from close(09:59 bar) to close(10:00 bar) -- the release-print minute

| Cohort | n days | mean \|move\| $ | max \|move\| $ | day-clustered CI on mean |
|---|---:|---:|---:|---|
| ISM days | 5 | 0.2329 | 0.6646 | [0.084, 0.4548] (n_days=5, n_boot=2000) |
| Secondary-only days | 6 | 0.5808 | 1.01 | [0.2533, 0.8717] (n_days=6, n_boot=2000) |
| Non-release days | 33 | 0.2264 | 0.7899 | [0.1607, 0.2978] (n_days=33, n_boot=2000) |
| (2026-08-03, named in briefing) | 1 | 0.225 | 0.225 | -- |
| (2026-08-05, named in briefing) | 1 | 0.6646 | 0.6646 | -- |

### Option worst 1-minute adverse move (min over that day's cached contracts), close(09:59)->close(10:00)

| Cohort | n days w/ option bars | mean worst-adverse % | min (most negative) % | days with a >=15% adverse move | CI on mean |
|---|---:|---:|---:|---:|---|
| ISM days | 5 | -12.508 | -25.0 | 2 | [-18.7996, -6.4552] (n_days=5, n_boot=2000) |
| Secondary-only days | 6 | -19.706 | -36.17 | 4 | [-27.6913, -10.6397] (n_days=6, n_boot=2000) |
| Non-release days | 33 | -8.622 | -21.053 | 6 | [-11.2331, -6.0579] (n_days=33, n_boot=2000) |

_Option coverage is sparse (only contracts actually held/cached that day survive in `backtest/data/highres/`) -- 44 of 44 cached-SPY days have >=1 matching option file. Treat cell n's literally; this is not a full-chain study._

## 3. Engine positions around the 10:00 window (fills-ledger reconstruction, n=454 positions, includes 2026-09-03)

### Positions OPEN across 10:00:00 ET, and entries in [09:45,10:05) -- ISM vs non-ISM days

| | n positions | n closed | sum P&L | mean P&L | cap-hit rate (proxy <=-45% premium) | mean hold (min) |
|---|---:|---:|---:|---:|---:|---:|
| ISM days | 76 | 76 | -840.0 | -11.05 | 0.1842 | 12.71 |
| Non-ISM days | 378 | 377 | 2125.0 | 5.64 | 0.0955 | 23.07 |

_(this cohort mixes "open across 10:00" and "entered in window" positions since `describe_cohort` buckets purely by day-is-ISM; see the JSON's `R1`/`R3` sections for the precisely-scoped rule populations.)_

## 4. Candidate rule costing (ENTRY-TICK information only, ISM-scoped, frozen)

### R1 -- no entries [09:45,10:05) on an ISM day

- n trades removed: **3** (3 fully closed & costed, 0 excluded still-open)
- net $ saved (losses avoided − winners forgone): **305.0** (losses avoided 305.0, winners forgone 0)
- day-clustered bootstrap CI on net-saved/day: n/a (n_days<2)
- top-3 |delta| concentration share: 1.0
- drop-best-day: best day 2026-08-05 contributed 305.0; ex-best-day total = **0.0**
- big-win-days touched: NONE
- by arm: {"risky-1": {"n": 1, "saved": 85.0}, "risky-3": {"n": 1, "saved": 136.0}, "safe-2": {"n": 1, "saved": 84.0}}
- dates touched: ['2026-08-05']

### R2 -- no entries [09:35,10:05) on an ISM day (R1 + kills the whole pre-release morning)

- n trades removed: **11** (11 fully closed & costed, 0 excluded still-open)
- net $ saved (losses avoided − winners forgone): **618.0** (losses avoided 1084.0, winners forgone 466.0)
- day-clustered bootstrap CI on net-saved/day: [-155.3333, 155.8] (n_days=3, n_boot=2000)
- top-3 |delta| concentration share: 0.3961
- drop-best-day: best day 2026-09-03 contributed 779.0; ex-best-day total = **-161.0**
- big-win-days touched: NONE
- by arm: {"safe-3": {"n": 2, "saved": 125.0}, "risky-1": {"n": 4, "saved": 220.0}, "risky-3": {"n": 2, "saved": -40.0}, "safe-2": {"n": 2, "saved": 228.0}, "bold-2": {"n": 1, "saved": 85.0}}
- dates touched: ['2026-08-03', '2026-08-05', '2026-09-03']

### R3 -- R1 + flatten any position open at T-2 = 09:58 ET on an ISM day (kill-type)

- n positions flattened & costed: **3**
- excluded: 0 already closed before 09:58 (no effect), 68 entered at/after 09:58 (position didn't exist yet), 5 no matching option bar, 0 still open at ledger-read time
- net $ delta (flatten-at-09:58 counterfactual vs actual): **-42.0**
- day-clustered bootstrap CI on delta/day: n/a (n_days<2)
- top-3 |delta| concentration share: 1.0
- drop-best-day: best day 2026-08-03 contributed -42.0; ex-best-day total = **0.0**
- big-win-days touched: NONE
- by arm: {"safe-3": {"n": 1, "delta": -37.0}, "risky-1": {"n": 1, "delta": -4.0}, "risky-3": {"n": 1, "delta": -1.0}}

### EXPLORATORY (not frozen) -- R1 scope widened to ISM + secondary (CB/UMich)

- n trades removed: 15, net saved: 2083.0
- big-win-days touched: NONE
- EXPLORATORY ONLY -- includes secondary (CB/UMich) 10am releases, NOT part of the frozen ISM-only rule. Included because 2026-08-28 (a named big-win day) carries a UMich release; this shows what would happen if the rule's scope were widened, which it is not.

## 5. Data sources (all read-only, no trading-path or generated-surface file touched)

- `setup/scripts/macro_calendar.py#scheduled_releases` (B1, imported live)
- `backtest/data/spy_sip_cache/spy_1m_<date>.json` (SPY 1-min bars)
- `backtest/data/highres/<OCC>_1m_<date>.csv` (per-contract 1-min option bars)
- `automation/state/fills-ledger.jsonl` (raw broker fills, `attribution=="engine"`, `is_option==True`)
- `analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md` (decision rule, frozen)

## 6. What this does NOT claim

- No exact per-fill exit-REASON field survives to `fills-ledger.jsonl` -- the cap-hit-rate in §3 is a proxy (`realized_pnl <= -45% of cost basis on the closed qty`), not a parsed `premium_stop`/`structure_stop`/`tp1`/`trail` classification.
- R3's counterfactual flatten price uses the SAME contract's own cached 1-min bar close at/just-before 09:58 -- not a bid/ask fill simulation, no slippage modeled.
- 2026-09-03 (today, an ISM day, market open at build time) contributes NO row to the §2 SPY/option distributional study (no archived 1-min cache yet) -- its already-verified facts live in `dissect-wave-autopsy.md`, cross-referenced not reproduced.
- Option contract coverage in `backtest/data/highres/` is sparse and skewed toward contracts the engine actually held that day -- not a full OPRA chain snapshot.

