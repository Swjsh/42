# Two-week engine retro — 2026-07-28 → 2026-08-11

The step-back J asked for. Every number here is broker-realized P&L or the live decisions
ledger unless explicitly tagged HARNESS (calibrated v5, bias −$7.4/pos, disclosed).

---

## 1. The P&L truth, per day

| day | book | character |
|---|--:|---|
| 08-04 | **+$3,624** | trend up, 25 entries, every arm green — **still 100%+ of the config's net** |
| 08-05 | −$1,935 | reversal chop |
| 08-06 | +$1,465 | low-ER day that PAID — the ER false negative |
| 08-07 | **−$2,687** | chop, 3 re-entry waves, all calls, every arm red |
| 08-10 | −$758 | the give-back day (three +83/+91/+98% peaks closed red) |
| 08-11 | +$43 | first ladder-live day; no give-back; mid-day +$188 faded on one late put |

Two-week engine book ≈ **−$248** (08-04..08-11), current-config-era total +$1,638 over 14
days with **drop-best −$124** and 6/14 days positive. The book is one Tuesday.

## 2. What is PROVEN (real money, survives drop-best or reproduces per-arm)

| finding | evidence |
|---|---|
| **Wide structure/−50% beats tight %-stops by ~$62/trade** | n=126 real fills; reproduces independently on every arm (risky-1 +46.75 vs −72; risky-3 +66.38 vs −59.60) |
| Tight % stops read the SPREAD, not price | VWAP G4: 12/17 premium-stop deaths at <10% adverse, five at ≥0% adverse |
| 145 positions die pre-TP1 vs 44 reaching it | live ledger, all history |
| Median +75% was AVAILABLE from our entries (upper bound) | raw OPRA, 256 positions |
| The give-back chain (TP1-gated protection) is structurally fixed | 08-11 live: three +82..+153% positions all banked |

## 3. What was RETRACTED or KILLED this week (and why that's the real product)

| claim | fate | mechanism |
|---|---|---|
| Ladder = +$6,454 | **RETRACTED** | first-exit harness discarded 74 runner legs from the control |
| Harness calibration "+$384, near-perfect" | **superseded** | two errors cancelling: SPY feed ended 07-22 (optimistic) vs 2¢ slippage (pessimistic). v5 = extreme fills + 1¢ → −$7.4/pos, 95% sign |
| "+$22k best cell" (tp1 150%) | killed | 08-04 alone = 167% of it |
| VWAP tight stop | FAILED its frozen prereg | drop-best −$1,631, 2/4 days |
| K2 zone stop | CLOSED by its own G4 | +$1,633 when it binds, but binds on 3/29 — dead-frequency |
| ribbon_flip confirmation A/B | parked | 5 fires in ledger history; structural defect, not a tunable |

## 4. Engine changes actually LIVE (all committed, guard-tested, RED-proofed)

1. **Pre-TP1 ladder** (+50→+30, +75→+60, trail @+75) — all 5 arms. Status: **UNPROVEN,
   forward-evidence-only** (calibrated harness: −$1,662, p=0.28; helps chop days, cuts trend
   days). Nightly winner_autopsy adjudicates.
2. **Pending-fill prune guard** — a working buy order can never read as flat (the risky-1
   −$440 class). Proven against the live Alpaca API.
3. **Kill switch no longer freezes exits** (fleet gate bug; a 61%-underwater position placed
   0 sells while tripped). Entries stay blocked by two independent gates.
4. **Orphan-position adoption on fleet arms** — lost exit-state self-heals next tick;
   engine-placed orphans get the full ladder back, unknown provenance gets cap-only.
5. **Ladder-aware re-anchor refusal** — an armed floor can no longer be silently lowered
   (RED-proof showed 1.856 → 0.88 without it).
6. **Tomorrow's-exits brief section** — per-arm resolved shape, nightly, from the production
   code path.

## 5. Standing clocks (pre-registrations that BLOCKED action this week — working as designed)

| clock | state | fires when |
|---|---|---|
| risky-3 stop_mode revert | **2/20 days** | n≥20 days (evidence says revert; prereg says wait) |
| ER30 regime discriminator | **0/25 forward days** | G5 auto-kill if >30% of low-ER days green |
| VWAP stop widening | **4/8 fill days** | mechanism confirmed; widening licensed at 8 days |
| Ladder | forward-only | winner_autopsy nightly ladder-vs-actual |

## 6. Open defects, ranked

1. **Chop-day entries** — the single largest loss driver (08-07 −$2,687; 08-11 mid-day
   −$636). ER30 is the candidate discriminator; shadow only, 0/25.
2. **ribbon_flip single-tick liquidation** — killed 3 profitable trades in 11 min on 08-11
   (57-second holds). NOT FIXED — parked on n=5; needs the structural confirmation buffer.
3. **Trend-continuation blindness** — 113 consecutive no-setup ticks while SPY fell 1.6 pts.
4. **safe-3 took zero trades 08-11** — unexplained; a fifth of the book idle.
5. **Partial-fill prune gap** — bounded to one tick by adoption; real fix is a blast-radius
   change, deliberately deferred.
6. **safe-1 credential dead (401)**; pain-ledger producer stale since 08-01.

## 7. The meta-lesson the two weeks actually taught

Three separate multi-day research efforts (ladder, TP1 grid, zone stop) produced confident
wrong answers **from the same root cause: an unanchored simulator**. The fix that matters is
methodological and is now standing: **no exit study is admissible unless the harness first
reproduces broker truth on the config that actually traded** (`harness_fidelity_anchor.py`).
Findings from real money survived every audit; findings from unanchored simulation did not —
without exception.
