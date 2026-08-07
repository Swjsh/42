# SCORE-LADDER BUILD — 2026-08-07 (LANE 1)

**Verdict: BUILT + EVIDENCED + STAGED.** The rung ladder (J's 4th+ ask) exists as (1) a
frozen prereg, (2) a replay harness that reproduced today's miss and walked the week +
390-day population, (3) a dormant, `git apply --check`-verified fleet-only patch, and (4)
RED-proofed guards. Frozen ship gates **G-WEEK and G-POP both pass** for the bull-only lane
at rungs 7 (risky-3) and 8 (risky-1) — ship runbook + patch block in
[CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md](CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md).
The honest caveats (population ~flat overall, positive only in the 2026 slice; drop-best
fails; chop-day frequency) are headlined below, not buried.

Freeze order (git-provable): prereg `a780122e` committed BEFORE runner+guards+patch
`3b3072a9` (`git merge-base --is-ancestor a780122e 3b3072a9` → true).

---

## 1. Prior-art audit (FIND-before-build, per the directive)

`arm_score_ladder_replay.py` EXISTS — found at `backtest/tools/arm_score_ladder_replay.py`
(2026-07-27): a 10-anchor evidence table for the RAW-floor ladder. Alongside it:

| Artifact | What it is | Status |
|---|---|---|
| `backtest/tools/arm_score_ladder_replay.py` | 10 named anchors × 5 arms, raw-floor semantics | superseded evidence, kept |
| `backtest/tools/ladder_fullhist_replay.py` | 390-day raw-floor lanes | **the kill evidence**: floor 7/8/9 = −$31,015 / −$16,642 / −$10,904 vs baseline +$5,307 |
| `build_shared_signal.py#_ladder_block` + `fleet_executor.py#_ladder_plan` | fleet raw-floor lane (bear-only) | **built, INERT** — `score_ladder_floor` DISARMED 2026-07-27 ~23:30 on the fullhist evidence (accounts.json + params docs) |
| `heartbeat_core.py#_apply_score_ladder` | core-arm raw-floor hook (bear-only) | built, INERT (same disarm) |
| guards `test_core_score_ladder.py`, `test_score_ladder_lane.py`, etc. | pin the inert v1 lane | passing, untouched |

**Why "verified NEVER implemented" (pk-2026-07-27) and "built but disarmed" are both true:**
the MECHANISM J keeps describing — a score admission with per-filter demerits — was never
built. What was built (and killed on evidence) admitted on RAW score with **blocker identity
ignored**: spread-blocked, entry-window-blocked and hard-VIX-blocked ticks all entered if
the number cleared the floor, bear-only. Entry in the binary engine remains pass/fail (any
single filter blocks regardless of score). Today's build is the third, different mechanism.

## 2. The mechanism (frozen in prereg `a780122e` BEFORE any run)

`analysis/recommendations/prereg-score-ladder-rung-2026-08-07.md` froze:

- **Demerit = 1 point per filter, derived from the scorer itself** (filters.py:1758
  `bear_score = 10 - len(blockers)`, :1273 `bull_score = 11 - len(blockers)`) — so the
  logged score IS the adjusted score, and admission = *(active blockers ⊆ demotable) AND
  (score ≥ rung)*.
- **Partition** — bull demotable {5 ribbon, 7 vol-div, 8 VIX-soft, 10 buyer-pressure};
  non-demotable {1 window, 6 spread, 9 VIX-hard, 11 trigger-count/level-tied, 12 sweep} +
  risk_gate + $0.30 premium floor. Bear mapped by MECHANISM not number (its VIX hard cap
  lives INSIDE blocker 8 — decomposed on the row's own vix vs 23.0; its pressure filter is
  9; its trigger-count gate is 10).
- Rungs: risky-3 = 7, risky-1 = 8; safe-3/safe-2/bold-2 binary control. Absent key =
  byte-identical (C14).
- Ship gates G-WEEK (primary, recency-first) / G-POP (guard) / G-HONEST (all cells).

## 3. Harness

`backtest/tools/ladder_rung_replay_2026_08_07.py` (NEW; commit `3b3072a9`):

- **Ledger mode** — replays the LIVE safe-account `core-decisions.jsonl` rows for any date;
  per-arm rungs at signal level; sequential one-position per arm; kill-switch (−50% SoD)
  and PDT-aware (counts always; enforces only where the arm's own ledger says
  `pdt_enforced` — live risky arms run `false`, mirrored+disclosed); paired BINARY-control
  vs LADDER walks so the ADDED cohort and DISPLACEMENT are both measured. Real 1-min OPRA
  (`_option_bars_1min_cache.fetch_1min_cached`) for prior days; TODAY priced off the
  engine's own per-tick spy/vix track through the repo BS lib — **every today cell labeled
  EST** (same-day OPRA 403s until ~16:21; `--no-est` re-prices after that).
- **Population mode** — 390 RTH days (2025-01-02..2026-07-27) through
  `run_backtest(**SAFE_BASE_LIVE)` with a full bull-side capture, rung admission, real-OPRA
  walks only, vs binary baseline + the killed floor lanes.
- Exits: `walk_exit_manager` → the REAL `exit_manager.plan_exit_actions` ONLY. RIBBON_RIDE
  shape, structure stop, raw level as trigger_level, entry+1 next-bar-OPEN.

**Today's facts reproduced from the ledger** (verification of the task brief): 100
sole-blocker score-10 HOLD ticks 10:14:03→12:12:04 — 80× filter-10, 10× filter-7, 10×
filter-11 (the f11 rows are non-demotable and correctly stay OUT). The 10:14 tick
(spy 770.495, score 10, sole blocker 10) IS admitted by the ladder.

## 4. Evidence — all cells

### Today 2026-08-07 (EST-priced, PARTIAL DAY — ledger through ~12:12 ET)

| Arm (rung) | Binary walk | Ladder walk | Added (n) | Takes 10:14? |
|---|---|---|---|---|
| risky-3 (7) | −$314 (3tr) | −$74 (9tr) | +$240 (6) | YES (−$177, then the 10:24 f7-rescue +$457) |
| risky-1 (8) | −$314 (3tr) | −$97 (7tr) | +$217 (4) | YES |

EST calibration vs the engine's 22 real-priced proposal ticks: mean err −$0.085, max |err|
$0.39 — EST cells never blended with real-OPRA cells. Final Friday cell requires the
post-16:21 re-run (`--no-est`).

### The week 08-03..08-07 (bull-only ship variant; Mon–Thu real 1-min OPRA, Fri EST)

| Day | Added P&L (n) — identical both rungs | Note |
|---|---|---|
| Mon 08-03 | +$1,307 (1) | real OPRA |
| Tue 08-04 | +$3,384 (1) | real OPRA — the monster |
| Wed 08-05 | −$1,555 (19) | **adversarial chop day** |
| Thu 08-06 | −$325 (30) | frequency exposure |
| Fri 08-07 | +$217 (4) | EST, partial day |
| **WEEK** | **+$3,028** | ex-best-day −$356; with 3-rescue/day cap **+$4,054** |

Both-sides variant: added +$2,184 (r7) / +$2,321 (r8) — bear rescues net −$719/−$597 on
real OPRA even this week. Delta (ladder-total − binary-total) +$1,696/arm bull-only.

### Population 2025-01-02..2026-07-27 (390 RTH days, real OPRA only, qty3)

| Lane | n | Total | Avg/tr | Held-out 25% | Drop-best | 2025 slice | 2026 slice |
|---|---|---|---|---|---|---|---|
| Binary baseline (07-27 ref) | 191 | +$5,307 | +$27.8 | +$1,548 | +$4,447 ✓ | — | — |
| KILLED floor=7 (ref) | 1538 | −$31,015 | −$20.2 | −$7,274 | ✗ | — | — |
| Rung 7 both-sides | 1276 | −$12,984 | −$10.2 | — | ✗ | — | — |
| Rung 7 bear-only slice | 843 | −$16,631 | −$19.7 | −$2,931 | ✗ | — | — |
| **Rung 7 BULL-ONLY (ship shape)** | 822 | **+$706** | +$0.86 | **+$660** | ✗ (−$231) | −$2,214 | **+$2,920** |
| **Rung 8 BULL-ONLY (ship shape)** | 755 | **−$644** | −$0.85 | −$760 | ✗ | −$2,442 | **+$1,799** |

**Artifact caught (/fable-too-good): the mixed-lane bull SLICE (+$3,647) was a selection
illusion** — bear positions occupying the book filtered which bull ticks got taken. The
true bull-only lane takes ~2× the bull trades and lands ~flat. The ship evidence quoted
everywhere is the bull-only LANE walk, not the slice.

Cohorts (bull-only, population): [8]-sole (VIX-soft) is the best cohort (+$3,605/46tr r7);
**[10]-sole — today's exact refusal shape — is −$361/118tr full-window but +$1,384/50tr in
the 2026 slice**; [7]-sole is thin and negative (n=15, −$721; 2026 n=2). [5,10] and [5,8]
are the bleeders (−$1,790/109, −$1,493/136).

### Bear side: two strikes, stays OUT

The rung semantics do NOT rescue the bear ladder: −$16,631/843tr (rung 7), held-out
negative — replicating the July kill under a strictly tighter mechanism. The production
patch is therefore **bull-only** (mirror-image of the v1 bear-only lane, evidence inverted),
and the guard `test_rung_lane_is_bull_only` pins it.

## 5. Ship gates as frozen — result

- **G-WEEK** (added net > 0 per shipped arm, recency-first): **PASS** — +$3,028 both arms
  (bull-only; Fri EST-labeled).
- **G-POP** (avg/added-trade > −$5 AND not the killed-lane shape): **PASS** — +$0.86 (r7)
  / −$0.85 (r8) per trade; killed-lane shape was ≈ −$20/tr.
- **G-HONEST**: all cells above; EST labeled; excluded counts in the JSONs; no NHST
  p-values computed anywhere in this study so no BH family exists (stated, not skipped).

Ship decision + runbook + the patch itself: the ADDENDUM. Safe arms stay binary — that IS
the ladder.

## 6. Guards + RED-proof (quoted)

`backtest/tests/test_score_ladder_rung_2026_08_07.py` — partition guards (6) enforce the
frozen prereg partition inside the harness from day one; production-lane guards pin the
dormant patch contract. RED run against HEAD (`--runxfail`, captured this session):

```
FAILED backtest\tests\test_score_ladder_rung_2026_08_07.py::test_rung_lane_admits_bull_f10_sole_blocker
FAILED backtest\tests\test_score_ladder_rung_2026_08_07.py::test_producer_emits_bull_block_with_vix
2 failed, 6 passed, 3 skipped in 1.30s
```

Normal mode (suite stays green until the patch lands): `6 passed, 3 skipped, 2 xfailed`.
`test_live_accounts_carry_no_rung_key_yet` additionally REDs on any accidental arming.

Patch applicability proven without touching the tree:
`git apply --check analysis/arm-ladder/score-ladder-rung-2026-08-07.patch` → rc 0.

## 7. Honest limitations

- **Friday is a partial day priced on EST** — re-run `--ledger 2026-08-07 --sides C
  --no-est` after ~16:21 ET before quoting a final Friday number.
- **Population is ~flat overall for the ship shape**; the positive story is the 2026
  regime slice + the week. That ordering (recency > aggregate) is J's standing doctrine
  (2026-07-31), applied here explicitly, not silently.
- **Drop-best fails everywhere** (week ex-Tuesday −$356; population ex-best-trade −$231
  r7). This lane's economics are a few large winners paying for many small stops
  (WR ~0.33-0.35) — same shape as the binary engine's own book, but thinner margins.
- **Chop-day frequency**: 19-31 rescue trades/day on Wed/Thu. A 3-rescue/day cap
  (probe-lane `daily_cap` precedent) turns the week from +$3,028 to +$4,054 and cuts the
  worst day from −$1,555 to ≈−$610. NOT in the minimal patch (untested as a live
  mechanism) — staged as the first fast-follow.
- Binary-control walk is a convention-normalized twin (ATM/PROBE tiers, next-bar-OPEN
  entries), not the broker ledger — the DELTA is the measurement, absolute levels differ
  from broker fills.
- risky arms run `pdt_enforced=false` live (mirrored in the walks; day-trade counts
  reported in the JSONs). Under a 3-in-5d enforcement the lane would cap hard — see the
  cap cell above.

Artifacts: `analysis/arm-ladder/LADDER-RUNG-2026-08-07-{week,population,week-bullonly,population-bullonly}.json`,
`analysis/arm-ladder/score-ladder-rung-2026-08-07.patch`, prereg `a780122e`, code `3b3072a9`.
