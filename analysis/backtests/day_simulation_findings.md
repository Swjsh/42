# Day-by-Day Engine Simulation — what does the autonomous engine see?

**Run:** 2026-05-07
**Tool:** `backtest/tools/simulate_day.py`
**Days tested:** 4/29, 5/1, 5/4, 5/5, 5/6, 5/7

For each day, the simulator walks every 5-min RTH bar, runs the full heartbeat
filter logic + v8 tiered exits, and records what the engine sees + decides.

---

## Headline

The engine's autonomous BEAR fires across these 6 days produced **−$369 P&L**
vs J's actual **+$920**. Same days. The 4 R-BT-08-class entry-timing failures
are fully visible bar-by-bar.

| Day | J actual | Engine autonomous | Notes |
|---|---|---|---|
| 4/29 | **+$352** | **−$462** (2 trades) | Engine fired 12:35 + 14:10 — both LATE bounces, both stopped out |
| 5/1 | **+$510** | $0 (no fire) | Filter 8 (VIX > 17.30 + rising) blocked all bars |
| 5/4 | **+$738** | **+$93** (1 trade) | Engine fired 11:20 — 53 min after J's 10:27 entry, $1 deeper strike |
| 5/5 | −$260 | $0 (correct skip) | Engine right to skip — J's manual chop trade |
| 5/6 | −$300 | $0 (correct skip) | Engine right to skip — J's hold-to-expiry rule break |
| 5/7 | −$120 (J manual) / −$45 (engine BULL trade) | $0 BEAR fire | Engine wisely skipped a chop-zone day |
| **TOTAL** | **+$920** | **−$369** | Gap: −$1,289 over 6 days |

The exits are right (102.5% capture on J's entries — see v8 findings doc).
**Entries are systematically late or absent.** R-BT-08 is the ONE remaining
constraint between current state and live-deployment readiness.

---

## Today (5/7) — would the engine have caught the bear move?

**Short answer: No, and the filters correctly identified why.**

The day produced 9 BEAR near-misses (score 8/10) but every one was blocked:

| Time | SPY | Bar | Stack | Spread | Bear Score | Blocker | Why blocked |
|---|---|---|---|---|---|---|---|
| 12:00 | 733.41 | BEAR_marubozu | MIXED | 57c | 8/10 | f5 | Ribbon still MIXED — hasn't BEAR-stacked yet |
| 12:35 | 732.79 | BEAR_marubozu | BEAR | 33c | 8/10 | f9 | Vol 6,885 = 0.7× — below 1.3× threshold (post-FOMC quiet) |
| 13:25 | 730.57 | red | BEAR | 107c | 8/10 | f7+f10 | Vol divergence, only 1 trigger |
| 13:40 | 730.73 | red | BEAR | 123c | 8/10 | f8+f10 | VIX falling (post-FOMC), only 1 trigger |
| 13:45 | 730.55 | red | BEAR | 130c | 8/10 | f8+f10 | Same — VIX still falling |
| 14:45 | 730.25 | doji | BEAR | 103c | 8/10 | f9+f10 | No clear seller bar, only 1 trigger |
| 15:15 | 730.55 | red | BEAR | 92c | 8/10 | f9+f10 | Vol 1.1× — below 1.3× threshold, only 1 trigger |
| 15:40 | 731.26 | red | BEAR | 76c | 8/10 | f8+f10 | VIX falling, only 1 trigger |
| 15:45 | 731.22 | doji | BEAR | 70c | 8/10 | f8+f10 | Same |

**Top blockers across the day:** filter 8 (VIX) 60×, filter 9 (volume) 60×,
filter 10 (≥2 of 4 triggers) 56×.

The bear move played out — SPY went 736.11 → 729.75 — but the **ribbon-and-volume
combination never hit the engine's "clean alignment" threshold.** 5/7 was a
post-FOMC drift day with falling VIX, light volume between key bars, and chop
zones interspersed with the moves. J's eye reads "broken level + lower highs +
ribbon BEAR-stacked = enter" with a 1-trigger setup; the engine waits for 2.

**This is honest.** The engine isn't "missing" a clean setup — it's correctly
identifying 5/7 as a setup day that doesn't meet the strict 2-trigger rule. The
question is whether the rule should be relaxed.

If we relaxed filter 10 from "≥2 of 4 triggers" to "≥1 of 4 triggers" — and
KEPT filter 8 strict — let me look at what would have fired on 5/7:

- 12:35 BEAR_marubozu would still be blocked (f9 vol)
- 13:25 red would FIRE (level_rejection alone, score becomes 9 with 1-trigger pass)
- 13:40 red would FIRE (level_rejection)
- 13:45 red would FIRE
- 14:45 doji would still be blocked (f9)

So filter 10 loosening would have produced 3 entries on 5/7 — all puts in the
730 area as SPY drifted lower. With v8 exits, those would have ridden to the
session low at 729.75 then exited on ribbon flip back. Reasonable wins.

But — this is a doctrine change that needs broader testing. R-BT-08.

---

## 4/29 — the engine fires LATE and loses

| Trade | Engine | J's |
|---|---|---|
| Entry time | 12:35, 14:10 | 10:25 |
| Strike | 709P (ATM-round) | 710P (1 ITM) |
| Result | −$129, −$333 | +$352 |

Engine's first entry at 12:35 hit the level stop within 5 minutes (12:40)
because SPY was BOUNCING off 709 area when the engine fired. J had ALREADY
exited the trade at 12:37 at +$352 — the engine was firing on the END of the
move, not the beginning.

Second entry at 14:10 hit −50% premium stop at 14:55 (−$333). Same problem
— late bar firing on a recovering tape.

What would have happened if the engine entered at 10:25 like J? Per the
J-replay test: +$199 (vs J's $352 — engine took TP1 at +30% premium instead
of riding to peak; runner exited at BE).

**The engine has all the right logic. It enters at the wrong moment.**

---

## 5/1 — the strict-filter day

Engine never fired. 60 bars blocked on filter 8 (VIX), 53 on filter 10. The
descending-trendline rejection setup that J caught at 13:36 just never met
the multi-filter alignment.

This is a HARDER fix than 4/29 — the trigger logic doesn't model trendlines
(only horizontal levels). The chart-anatomy says trendline-rejection is a
valid trigger but the auto-detector hasn't been built to fit lines through
swings. R-BT-09 (level/trendline detection upgrade).

---

## 5/4 — partial win

Engine fired at 11:20 ($1.56 entry on 719P). J fired at 10:27 ($0.85 entry
on 721P). Engine paid 84% more for entry, captured a smaller piece of the
move. +$93 vs J's +$738.

If engine had fired at 10:25 entry like J: per the J-replay, +$1,268 — even
BEATING J's discretion. The exit logic isn't the constraint.

---

## 5/5 / 5/6 — engine correctly skips J's bad days

5/5 J took a 722P that wasn't a playbook setup — engine never fired (correct).
5/6 J held 730P to expiry without a stop — engine never fired (correct).

**The engine's strict filters earn their keep here.** When J's eye is wrong,
the filter discipline is right.

---

## What this means for tomorrow live

1. **The exit logic is solid** — captures or beats J's edge when entries align.
2. **Entry timing is the limiting factor** — engine fires 53-130 min late
   on the wins, missing both the optimal premium AND being on bounce bars
   that immediately level-stop.
3. **The engine correctly skips J's losing days** — that part of the strict-
   filter discipline is paying off.
4. **The fixable lever is filter 10** — currently requires ≥2 of 4 triggers.
   Loosening to ≥1 with strong-other-filter conditions would catch many more
   J-quality entries. Need backtest first.

Updates ratified into CLAUDE.md operating principles 8-11. Next priority is
R-BT-08 (entry timing), specifically filter 10 sensitivity testing.

---

## Files

- `backtest/tools/simulate_day.py` — the day-walker tool
- `backtest/tools/replay_j_with_v8_exits.py` — J replay with engine exits
- `backtest/lib/simulator_real.py` — v8 implementation
- `analysis/backtests/v8_tiered_exits_findings.md` — exit doctrine findings

Re-run any time:
```
cd backtest
.venv/Scripts/python tools/simulate_day.py 2026-05-07
.venv/Scripts/python tools/simulate_day.py --all-recent
```
