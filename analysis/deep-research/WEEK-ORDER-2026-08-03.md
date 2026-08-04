# THE WEEK ORDER — week of 2026-08-04

> Written Tuesday 2026-08-04 ~09:00 ET, market closed, live state verified this session.
> Completes the 5-lane Fable sweep of 2026-08-03: 4 lanes landed and shipped, lane 5 (orphan
> hygiene) and 2 verifiers died on a usage limit and are re-running now. Everything below is
> re-derived from live config + broker reads, not from lane summaries.

---

## 1. The mission

**Every wall that stopped us trading a real signal in the post-fix era is now down or measured:
the elite-bull gate is lifted on both cores (it refused +$3,577 across 26 events), the OTM-2
floor-wall that killed 4 of 5 arms all Monday afternoon is dead (bold_core is ATM through $10K),
and the one remaining door — the bear VIX floor — was priced at $0 sole-blocked and exonerated.
The week is measured in real fills, not in what we shipped.**

---

## 2. Tuesday 09:30 state — what is armed

| Change | Scope | Live value | Kill criterion | First-tick check |
|---|---|---|---|---|
| **SHIP A** exit anchors → real fill | all arms | `reanchor_entry` wired | guard suite REDs → `git revert` | entry row logs a reanchor line; TP1 computed off fill, not limit |
| **SHIP B** `block_elite_bull` lifted | safe-2 + bold-2 | `false` / `false` (verified) | per arm n≥10 elite fills OR 10 sessions, net<0 → re-block same day | zero `SKIP_ELITE_BULL_LEVEL_RECLAIM` rows on cores |
| **SHIP C** cheap-contract boost | risky-3 only | qty 10 when premium < $0.50 | n≥10 boosted fills or 10 sessions, net<0 → delete 2 patch keys | first sub-$0.50 plan shows qty 10, legs 6/4 |
| **ATM-TIER-EXTENSION-2K-10K** | bold-2, safe-3, risky-1, risky-3 | `V15_BOLD_CORE_TIERS` $2K–10K = **ATM** (verified) | FLOOR_WALL alarm count must collapse toward 0 | bold-tier plans show `strike == round(spot)` |
| **L246 floor-rescue** | risky-1 (full-send) | `floor_rescue_plan` + rescue branch | denied rescues tallied in fleet_liveness | first `floor_rescue after SKIP_MIN_PREMIUM_FLOOR` row |
| **Fleet vwap_reclaim_failed_break** | risky-3 enters / safe-3 holds | `RUN_VWAP_RECLAIM_FB` | n≥10 fills or 10 sessions, net<0 → flag False | divergence: risky-3 ENTER while safe-3 HOLDs same signal |
| **FIX2 vwap emission un-deadened** | fleet | lazy imports repaired | `RUN_VWAP=False` | first-ever fleet `vwap_continuation` rows |
| **IEX tail on level refresh** | all | `_merge_iex_tail` | fail-open: degrades to old behavior | 09:33 log shows `iex_tail.tail_used > 0` |

**Live account state, verified 08:57 ET:** all five arms FLAT, zero open orders.
safe-2 $5,067.67 · bold-2 $5,000.00 · safe-3 $5,144.73 · risky-1 $5,144.55 · risky-3 $5,175.55.

**Unchanged and deliberately so:** entry window 09:35–15:00 · `min_entry_premium` $0.30 ·
`structure_veto_enabled` true (safe) · `require_bearish_fill_bar` true (bold) · bear VIX floor 17.3.

---

## 3. Pipeline: what is alarmed, what can still kill a trade

`PIPELINE-CHAIN-MAP-2026-08-03.md` maps 18 core + 10 fleet links with each link's fail
open/closed/**SILENT** verdict. Silent links now alarmed:

- `FEED_DEAD_INSIDE_RUNNING_ENGINE` — 772 ticks all `SKIP_NO_DATA` used to read RAN
- `BLIND` — key-levels dead while the engine ticks happily
- `VIX_FEED_DEAD` — vix=0.0 makes the bear floor unreachable **and the bull cap wide open**
- `BROKER_INFRA_FAILURES` — entry attempts dying on creds/equity/place errors
- `SIGNAL_STALE_WALL` / `FLOOR_WALL` / `ARM_ERRORS` (fleet) — the FLOOR_WALL alarm caught
  Monday's real 33/35/35 wall on its first run

**Still unaccounted — the honest list:**
1. **Fail-open flat read (O1).** `is_flat_spy_options` fails OPEN; a broker read error could in
   principle permit a stacked entry. Spec written (map §6), needs its own RED-proof pass. **Top
   of the after-hours queue.**
2. **VIX-feed failure changes gate BEHAVIOR**, not just visibility — alarmed, not fixed; fixing
   it is edge-affecting and needs a prereg.
3. **Content-alarm thresholds** (30% dominance, ≥10 floor, ≥3 errors) are judgment constants,
   not A/B-derived. Tune only on observed false pos/neg.
4. **extra_exec counter blindness** — 3 counters can't see a real trade (safe-2's +$67.85 was
   invisible Monday). Lane 5 is fixing it now.
5. **Premarket frame** — the 09:25-class bounce remains structurally untradeable (premarket bars
   are outside the RTH trigger frame; filter 7 would refuse it anyway). A/B pre-registered,
   runner unbuilt. **Not** a Tuesday change.

---

## 4. Gates — the post-fix verdict

Priced on real OPRA over 07-31 + 08-03 (n-small, both trend-recovery days — labeled):

| Gate | Post-fix refusal value | Verdict |
|---|---|---|
| `block_elite_bull` | **+$3,577 / 26 ev** (ex-stale: +$1,861 / 24 ev) | **LIFTED** — trial 2 live |
| OTM-2 tier → floor collision | 28–35 floor rows/arm on Monday's afternoon cluster | **FIXED** — ATM through $10K |
| `structure_veto` | +$38.97/tr, n=11 | prereg frozen, **not armed** |
| `require_bearish_fill_bar` | +$20.61/tr, n=33 | prereg frozen, **not armed** (blast radius: `_HARD_SKIP_VERDICTS` propagates a Bold lift to safe-3/risky-1) |
| filter 10 buyer-pressure | +$4,535 / 2d | prereg frozen, runner queued |
| **bear VIX floor 17.3** | **$0 sole-blocked** | **EXONERATED** — Friday's real breakdown opened the floor itself at VIX 17.35+. No prereg filed. |
| PDT / kill-switch / NOT_FLAT / risk-cap | fire counts only | doctrine-class — never P&L-verdicted |

---

## 5. Risky-3 — the differentiation J demanded

**Measured first, honestly: the complaint was correct.** Over 5 sessions risky-3's marginal
cohort — trades the safes did NOT take — was **4 trades, −$229**, and both rescue lanes had
fired **zero times ever**.

**Now differentiated by three mechanisms, all from the validated menu:**
1. `vwap_reclaim_failed_break` emits fleet-wide; **safe-3 holds it on its own gate, risky-3
   enters** (guard-proven divergence on a real-shaped signal)
2. SHIP C qty-10 on sub-$0.50 contracts (3 of last week's 7 entries would have qualified)
3. The L246 floor-rescue lane, which exists precisely for the speculative participation J named

**Standing measurement:** `Gamma_RiskyDivergenceWeekly`, Sundays 17:00 ET — *"risky-3 took N
trades the safes did not; that cohort paid $X."* Registered and verified. **J never has to ask.**

---

## 6. The violin metric

Coverage — levels the tape respected vs levels the engine had active *at that moment* — over
the last 5 sessions: **66.7% / 44.8% / 0.0% / 84.1% / 75.0%**. (The 0.0% is the known
blindness day; 44.8% on 07-29 is unexplained and owed a forensic once the trend has 2–3 more
nights.)

Root cause of the lag was the **delayed-SIP plan tier** — the level file's eye was ~15 minutes
behind the tape (Monday's 749.33 case). Fixed with a real-time IEX tail; final premarket levels
now land by ~09:34, ahead of the 09:35 window-open. **Unit-proven, not yet live-proven** — the
market was closed. Tuesday's 09:33 log is the first live evidence.

Reports nightly at 17:35 ET via `Gamma_ViolinMetric`.

---

## 7. The week, ordered

**Tuesday**
- 09:00 — premarket readiness now leads with carried trendlines (Monday's TESTING wick support)
- 09:33 — **first live proof of the IEX tail**: `tail_used > 0` in the refresh log
- 09:35+ — watch, in priority order: (a) zero elite-bull skips on cores, (b) bold-tier arms
  planning ATM strikes, (c) first floor-rescue row on risky-1, (d) first fleet vwap fills
- 16:25 — WinnerAutopsy fires organically (first proof of the creds fix)
- 17:35 — violin metric; expect premarket_low + intraday_rth_high/low rows to rise
- EOD — content alarms surface through daily_brief for the first time on a scheduled run

**If X then Y**
- If an elite-bull fill loses and the arm reaches n≥10 or 10 sessions net<0 → **re-block that arm
  same day**, don't wait for the week to end
- If FLOOR_WALL alarms persist on bold-tier arms → the ATM extension didn't take; check
  `_tiers_for_arm` resolution before touching anything else
- If SPY breaks down with VIX < 17.3 → **no arm can short it.** That's the exonerated floor doing
  its job on current evidence; log the event, don't change it mid-week
- If the floor-rescue never fires all week → post-SHIP-B, elite no longer produces the veto it
  keys on; it only proves out on the other 4 cohorts (expected, not a defect)

**After-hours queue, in order:** O1 fail-open flat read → PRIOR-DAY-HLC-LEVELS → BULL-F10 runner
→ GATE-EXPIRY-SOLE-BLOCKER-MINER → structure-veto lift adjudication (never stacked on elite
trial 2's live kill window).

**Standing asks that are J's alone — and the list is this short:**
1. Restart Claude Code when convenient (restores TradingView chart-drawing; trading unaffected)
2. Alpaca OPRA data-agreement re-sign, *if still unsigned* — backfills run on disclosed fallbacks

---

## 8. What didn't survive / what's still open

- **Lane 5 (orphan hygiene) never ran** last night — re-running now: two dead lanes' work, the
  2 git stashes (dated 07-15/07-18, not from the sweep), counter blindness, twin staged fixes.
- **Lane 1's verifier died** — its ATM ship went live unverified. Independent verification
  running now, including a plain yes/no on whether the extension is safe to have live today.
- One stale display-name pin (`test_arm_display.py`) fixed this morning — my own regression from
  Sunday's account rebuild.
- 37 commits unpushed pending audit.

---

## 9. Spoken brief

1. Five arms, all flat, all funded around five thousand — and for the first time every wall we
   measured is either down or priced.
2. The elite-bull gate is lifted on both cores; it refused three and a half thousand dollars
   across twenty-six events in the post-fix era, and that is now a live trial with a hard kill.
3. The strike regression that floor-walled four of five arms all Monday afternoon is dead —
   bold-tier arms are ATM through ten thousand.
4. Risky-three is finally speculative on purpose: it takes a validated setup the safe arms
   refuse, it buys ten when contracts are cheap, and it has a rescue lane for floor-blocked plans.
5. I measured its old divergence first and it was four trades and minus two twenty-nine — the
   complaint was right, so I fixed it rather than argued.
6. The level pipeline was fifteen minutes behind the tape; that was a delayed-data plan tier, and
   the real-time tail lands premarket levels before the window opens.
7. Coverage is now a nightly number, so "playing levels like a violin" is measured, not asserted.
8. Four silent failure classes now alarm — a dead feed, dead levels, a dead VIX read, broker
   infra errors — and the floor-wall alarm caught Monday's real wall on its first run.
9. What I am watching today: zero elite skips on the cores, ATM strikes on bold-tier arms, and
   the first rescue fire on risky-one.
10. What would make me pull a trigger back: any armed trial going net-negative at its frozen n —
    and I re-block same day, not at week's end.
