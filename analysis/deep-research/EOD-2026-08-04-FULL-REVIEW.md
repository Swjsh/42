# EOD 2026-08-04 — FULL REVIEW (canonical)

**Written:** 2026-08-04 17:33 ET, `market_hours=False` (verified `setup/scripts/et_clock.py`).
**Authority:** live broker reads on all 5 arms this session + real OPRA 1-min bars + engine decision
ledgers. Five adversarial lanes, each independently reviewed; every load-bearing number below was
re-derived by me from raw sources, not copied from a lane.
**Sources:** [REENTRY](EOD-2026-08-04-REENTRY.md) · [WINNERS](EOD-2026-08-04-WINNERS.md) ·
[ENGINE](EOD-2026-08-04-ENGINE.md) · [REPEATABILITY](EOD-2026-08-04-REPEATABILITY.md) ·
[TWIN-PROCESS](EOD-2026-08-04-TWIN-PROCESS.md)

---

## 1. THE ONE THING TODAY TAUGHT US

> ### 🚨 **+$3,617.85 is real money, and we could not legally have traded for it.** The fleet's PDT gate read `0` on **1,152 consecutive ticks** while three arms took **17 day-trades against a limit of 3** — and all five arms now sit at **ZERO headroom through Friday**.

The record was not produced by a machine that was working. It was produced by a machine with a
**silently dead safety gate** that manufactured the leg count the headline rests on. The dead gate
did not cost a dollar today — it *enabled* the day. That is a worse finding than a loss.

Verified live this session: `daytrade_count` is **absent** from the Alpaca payload on all 5 arms, so
`fleet_live.py:660`'s `int(acct.get('daytrade_count', 0) or 0)` evaluates `0` forever. `0 >= 3` is
never true. Meanwhile `multiplier=4` on every arm — **real PDT binds.**

---

## 2. THE DAY, VERIFIED

### 2.1 Per-arm (broker truth, re-read 17:33 ET)

| Arm | SOD equity | Close equity | Δ equity | Legs | Day trades (5d) | PDT headroom |
|---|---:|---:|---:|---:|---:|---:|
| safe-2 | 5,067.73 | 5,729.22 | **+661.49** | 9 | 4 | **−1** |
| bold-2 | 5,000.00 | 5,478.25 | **+478.25** | 15 | 3 | **0** |
| safe-3 | 5,144.73 | 5,780.83 | **+636.10** | 18 | 6 | **−3** |
| risky-1 | 5,144.55 | 6,184.30 | **+1,039.75** | 25 | 5 | **−2** |
| risky-3 | 5,175.55 | 5,977.81 | **+802.26** | 55 | 6 | **−3** |
| **TOTAL** | | | **+3,617.85** | 122 | **24** | **0 arms with room** |

✅ **All five arms flat at the close** — `npos=0` on every account, verified by direct broker read.
Day-trade counts computed with the repo's own `pdt_tracker.fetch_day_trades_used_5d`, so the number
matches the engine's own definition. Rolloff **2026-08-11** (bold-2 08-12).

> One lane reported risky-3 at 8 day-trades. I re-derived it: **6** under the FINRA symbol-date
> reading (9 under strict pairing). Corrected here. The broker field is absent, so nothing can
> arbitrate the definitions — that ambiguity is itself the instrument gap.

### 2.2 Reconciliation verdict — ✅ CLEAN, zero unexplained

| Measure | Value |
|---|---:|
| Broker equity delta (5 arms) | **+$3,617.85** |
| Option cash flow, FIFO over real fills | **+$3,624.00** |
| Residual | **−$6.15** |

The residual decomposes as **$0.05/contract regulatory fees on 122 contracts sold ($6.10)** plus a
few cents of accounting treatment; one lane's bucket also absorbed **$2.82 of crypto-twin P&L**,
which is why two lanes quote $6.12 vs $6.15. **No unexplained P&L on any arm.** The handoff's
+$3,617.19 is $0.66 light purely because its SOD equities ran $0.12–0.21/arm above broker
`last_equity`. All three figures are correct for what they measure. **Fix: pin SOD to broker
`last_equity` in the EOD roll-up.**

### 2.3 Scorecard — graded on process, not on P&L

Yesterday's +$533 graded **B** on a luck-audit. Today is **6.8× the P&L and a worse process day.**

| Dimension | Grade | Why |
|---|:---:|---|
| Signal quality | **B+** | Direction right repeatedly; all 82 core `ENTER_BULL` were ELITE + level_reclaim. |
| Execution & reconciliation | **A−** | Ties to the cent, all arms flat, zero unexplained, 122 contracts accounted. |
| Exit shape | **C** | 20.3% book capture; 4 of 5 arms gave the runner back to an *ordinary* retrace. |
| Risk management | **D** | PDT gate dead; −6% stop inside a 10.3% noise band; hard-day test **failed** (−$1,304). |
| Instrumentation honesty | **C+** | Nightly would have published a garbage 4.3% headline; a dead knob inflated a denominator; three lanes found real defects in their *own* work. |
| Repeatability | **D** | 5.1% archetype; ex-today the live record is **−$1,130 over 23 days**. |
| **My judgment** | **D** | Alarm wrong on three independent counts; retraction unearned; entry count never verified. |
| **COMPOSITE** | **C+** | **An A+ day delivered by a C+ machine.** |

**The shape of the day, stated plainly:** two signal clusters (09:50–09:58 763C and 12:28 769C)
produced **$3,942 of $4,372 gross-positive P&L = 90.2%**. The other **six clusters combined lost
−$318**. 10 winners (+$4,735) against **15 losers** (−$1,111). This was a two-trade day, not a
system firing on all cylinders.

---

## 3. THE RE-ENTRY VERDICT — decided

### 3.1 The verdict

> **The loop is a SYMPTOM. The defect is the STOP. Arm nothing tonight.**
>
> - ❌ **Do NOT arm a re-entry cooldown at any value.** Every honest cell loses money.
> - ❌ **Do NOT revert `RUN_VWAP`.** Its pre-registered kill criteria are not met.
> - ✅ **The real lever is stop width** — pre-registered, not armed.

All four lanes that touched this converge on the **action**. They disagreed on the **judgment**, and
that disagreement is resolved below.

### 3.2 The counterfactual numbers

**Cooldown grid, today's real broker fills (risky-1 + risky-3 vwap combined).** I hand-recomputed
all six cells; they reproduce to the dollar.

| Cooldown | P&L | vs live |
|---|---:|---:|
| **0 / live** | **+$721.00** | — |
| 5 min | −$403.00 | −$1,124 |
| 10 min | +$265.00 | −$456 |
| 15 min | −$259.00 | −$980 |
| 30 min | −$259.00 | −$980 |
| once/day | −$179.00 | −$900 |

**Every cell loses.** The best cooldown costs −$456; the worst −$1,124. The 10-min cell survives
*only* because 09:57 falls 11.05 min after 09:46 — **a 12-minute cooldown destroys it.** A
2-minute-wide winning window on one day is an artifact, not an effect.

**The behaviour the alarm targeted is the behaviour that paid:** risky-3's trade of the day came
**1 minute after a stop-out**, and risky-1 — the arm I called well-behaved — made **100% of its vwap
money on a 4-minute re-entry.**

### 3.3 Premise corrections (four load-bearing facts were wrong)

| Claim | Truth |
|---|---|
| risky-3 "entered 7 times" | **7 decision rows, 4 PLACED.** 09:48/09:49/09:53 were `SKIP_DUPLICATE_CLAIM`. |
| "the FIFTH became the trade of the day" | It was the **4th placed** entry. |
| risky-1 "took it 3× (tighter gate)" | **2×**, and its gate is `gate_override.full_send=true` — the **LOOSEST in the fleet**. |
| "risky-1's tighter gate made more" | risky-1 **was never flat** 09:50→11:25. Re-entry was structurally impossible, not declined. |

**The "control" was not a control.** Both arms bought the same 763C within 2 seconds at 09:50 —
risky-1 at 1.39, risky-3 at 1.46. The entire divergence (+$640 vs −$40) was **~7 cents of entry fill
luck.**

> **⚠️ CORRECTION to a lane headline.** The REENTRY lane called this "survived by 0.34 cents" and
> promoted it as its most important number. That was derived from a *modeled* bid (OPRA close − 3c)
> for a quantity the engine **already records**. I pulled the real values: the engine's actual stop
> operand (`worst_premium`) bottomed at **1.37 @ 09:56** against a stop of 1.3066 — **a true margin
> of +$0.0634, understated 18.6×.** The knife-edge is at an entry fill of **1.4574**; risky-3's 1.46
> missed survival by **0.26 cents**. The lane's middle table row ("filled 3c worse → stopped out")
> **inverts** — 1.37 > 1.3348, it survives. The *conclusion* (fill luck decided it) stands; the
> headline number did not. Same error class the lane itself indicted: **an OPRA bar records what
> TRADED, not what the engine QUOTED.**

### 3.4 Root cause — new, and nobody knew it this morning

`exit_manager.ExitState.from_entry`:

```python
resolved_structure = (shape_mode == 'structure' and bool(structure_stop_enabled)
                      and trigger_level is not None)
```

`vwap_continuation` is a **continuation** setup — its `trigger_level` is **always `None`**. So its
`stop_mode='structure'` patch is a **guaranteed no-op on every arm**, and every position silently
falls back to the raw **−6% premium stop**. Config says structure; the machine runs premium.
Confirmed in code *and* in the live ledger (every vwap `exit_pass` row carries
`"stop_mode": "premium"`, `"trigger_level": null`, with stops at exactly `entry × 0.94`).

That −6% stop is **1-minute sampled** and sits inside a **10.3% median 1-min noise band** (real
OPRA, 763C 09:45–10:30, n=46; p90 14.9%, max 23.4%). **Every re-entry today was preceded by a
stop-out.** Fix the stop and the loop dissolves; cap the loop and you keep paying the stop.

### 3.5 The honest audit of my 09:57 alarm and my retraction

**The alarm was wrong on three independent counts.**

1. **I counted a field I never read.** I said seven entries; four were placed. `placement.placed`
   sits in the *same JSON object* as `action`. **75% overstatement on a verification failure, not a
   judgment call.**
2. **My decision statistic was structurally biased.** Realized P&L at minute 11 is **censored, and
   the censoring correlates with sign** — losers resolve in under 2 minutes and print, winners are
   still open and contribute nothing. Four fast losses plus one 7-minute-old open position is
   **exactly what a working trend-continuation setup looks like at minute 11.**
3. **The proposed fix did not follow from the diagnosis even if the diagnosis had been right.**
   `RUN_VWAP=False` disarms the **entry producer** for a pathology whose mechanism is the **exit**.
   Killing the signal to fix a stop is a category error.

**The retraction was the right call by the wrong process.** I withdrew on the *same censored
11-minute window* that produced the alarm, having acquired **no new evidence**. Both draws came from
the same biased sample; the second happened to land on the right side. **A coin that lands heads is
not a decision procedure.** It also **stated no threshold**, so it left nothing behind — a future
session inherits neither the rule that would have justified the revert nor the reason it was
withdrawn.

**One thing was correct and I claim no more than it:** I did not act mid-session, so **Rule 9 held.**
The real gap is that **Rule 9 stopped the ACTION but not the CONCLUSION** — and a stated conclusion
is what a later session acts on.

### 3.6 Adjudicating the lane disagreement

The REPEATABILITY lane reached the opposite verdict — *"the alarm was RIGHT; the retraction was
WRONG"* — on a **different and better argument**: **displacement.** The ledgers show risky-1/risky-3
were offered the ELITE **ribbon** signal at 09:58–10:12 and refused it with one reason only,
*"position already open."* With FIX2 reverted they take the ribbon instead, and the day is
**+$247.50 better** (risky-3 +$368, risky-1 −$120.50).

**My adjudication:**

- **The displacement finding is the strongest live-money argument against the setup, and it
  survives.** It is *not* the argument I made at 09:57. I argued churn; this argues opportunity
  cost. **Reaching a similarly-signed conclusion by a mechanism I never considered does not make my
  reasoning right.** The alarm stays graded wrong.
- **It cannot carry an action tonight.** n = 1 day, 2 arms, and it **splits by arm** (+$368 /
  −$120.50). risky-1's counterfactual entry is **simulated** at 1.50 against risky-3's real 1.40,
  and the lane's own harness carries a measured **+29.4% optimism** on all-simulated rows. +$247.50
  is **6.8%** of the day, inside that error bar.
- **The twin corroborates the mechanism, never the P&L.** On the same calendar day the crypto twin
  ran **14 organic round trips, 0 winners, −$2.86**, with **12 of 13 knifed out by structure stop**
  and ten consecutive losing re-entries in a three-hour block. That is *mechanism* evidence that
  re-enter-after-stop is a bleed function on a tape with no trend to redeem it. **Twin P&L is never
  SPY evidence.**

**Net:** alarm wrong, retraction unearned, mechanism newly identified, **displacement promoted to a
pre-registration**, and **nothing armed.**

### 3.7 What the hard-day evidence actually says

Stripping today out of the 24-day real-fill history, **TIGHT (<15 min) re-entry sequences bled
−$846 across 12 sequences at a 0% rescue rate** — not one was saved by a later leg. That argues
**FOR** a cooldown. Today the same shape made **+$900**. Net across 24 days: **+$54 — a wash.** The
24-day cooldown sweep is **non-monotonic** (5min −$934, 10min −$9, 15min −$521, 30min +$149,
once/day −$2,356); a genuine effect would not zig-zag.

The payoff is **positively skewed**, and a cooldown truncates the **right** tail, not the left: it
saves ~$37/day over 23 ordinary days and forfeits ~$900 on the one day that pays. **You cannot
harvest a fat right tail with a rule that removes late entries.** The correct hard-day defence is a
stop wide enough that the position is not ejected into the chop in the first place.

**Verdict grade: (c) UNDERPOWERED.** Today and the 23-day population point opposite ways. I did not
resolve that; I quantified both and refused to pick.

---

## 4. WINNERS, CRITICIZED

### 4.1 Capture — and the policy that "beats" us is already in the graveyard

| Measure | Value |
|---|---:|
| Book capture (n=10 winners) | **20.3%** |
| Best single fixed policy — `hold_to_time_stop` | $23,380 |
| Hindsight per-trade shape-picking | 20.1% |
| **ORACLE** *(UNREACHABLE — never mixed into a live column)* | **17.7% of $26,766** |

`hold_to_time_stop` has **no profit-taking at all** — only the −50% catastrophe cap. Its 5× edge is
**pure 0DTE expiry mechanics on a one-directional day** (the 763C finished ~$9.26 intrinsic). It is
the single most dangerous shape on the menu on a reversal day, and **"hold longer" is already in the
graveyard at −$451.50 over 21 winners.** Today is the counter-example any trend day produces, not
new evidence.

### 4.2 🚨 Cross-lane collision neither lane caught — the exits recommendation is invalid

The TWIN lane handed the exits question a headline: *"best fixed policy over the winner population
is `trail_only_no_tp1`."* **I checked it against git and the artifact clock. It fails three ways:**

1. **It is the graveyard entry.** At `git show HEAD:analysis/winner-autopsies/all.md`,
   `trail_only_no_tp1` and `hold_to_time_stop` both sat at **exactly −$451.50 over n=21** — the
   literal graveyard item — described in the file's *own prose* as "usually the **WORST** column."
2. **It is a one-day sign flip.** Adding today's 10 winners moves both to **+$27,848.50** — a
   **+$19,100.50 swing** that makes the worst columns the best. Today is **28.6% of n and 54.1% of
   the population's realized dollars.**
3. **The policy was a dead knob when that number was computed.** `trail_only_no_tp1` set
   `tp1_premium_pct=999` while leaving `profit_lock_arm_scope='post_tp1'`, so the lock could only
   arm on a TP1 fill that never comes — making it **byte-identical to `hold_to_time_stop`** (both
   still show $27,848.50 in the current artifact). The WINNERS lane fixed it at **16:45 ET, twenty
   minutes after the 16:25 population run**. Post-fix it collapses to **$554 — the WORST policy on
   the menu.**

**Ruling: `trail_only_no_tp1` is struck from the exits input.** `analysis/winner-autopsies/all.md`
currently carries **pre-fix numbers** and needs a full-population re-run before any exit claim is
sourced from it.

### 4.3 Per-wave capture — the gap is one wave, and it is expiry mechanics

| Wave | Capture | Realized |
|---|---:|---:|
| 763C 09:50–09:58 | **12.7%** | $2,534 |
| 769C 12:28 | **64.6%** | $2,192 |
| 771C 13:24 | 4.3% | $9 |

**Wave 1 holds 97% of the theoretical gap.** Wave 2 — entered midday with less runway, where the
expiry distortion is weakest — captured a healthy **64.6%**. Our exits are not broadly broken; they
are "broken" only against a policy that exploits same-day expiry on a one-way day.

### 4.4 The $4.87 runner — an exit-shape fact, not luck

All five arms held the **same contract**. risky-1 is **the only arm whose post-TP1 runner uses
`profit_lock_mode=fixed`**: its stop parked at breakeven 1.39 and **never ratcheted across 79
ticks**, then left on `runner_target` at **4.87 (+250%)**. The other four ratcheted trails to ~2.54,
and the **ordinary 3.00 → 2.53 pullback at 10:18–10:21 evicted every one of them.**

risky-1 actually had the **worse TP1** (2.12 vs 2.68). **100% of its outperformance came from the
runner surviving.** On the best trend day on record, the binding constraint was **the chandelier
trail — the v15.3 profit-lock itself** — not the runner target.

> **Caveat, load-bearing:** the lane's +$1,912 BE-floor-vs-chandelier delta is **hardcoded literals
> with no computing code path**, and depends on a shape-reconstructor the same lane declares broken
> for empty-`exit_patch` arms (all 8 arms have `exit_patch=None`). Independent re-derivation gives
> **+$2,229.70** — same sign, same magnitude, **but the stated number is not reproducible.**
> PREREG-only; never armed. Also: 4 of 10 winners carry **another trade's entry metadata**
> (`find_entry_decision` matches on symbol with no timestamp constraint), which stamps wave 2's
> window as 11:52–12:28 when all four members filled at 12:28. Capture and P&L are unaffected.

### 4.5 What sizing left on the table — and why it is not free money

| Scenario | Book | vs actual |
|---|---:|---:|
| Actual | $3,624 | — |
| qty10 (MODELLED) | $8,863 | 2.45× |
| Rule-6 ceiling (MODELLED) | $12,924.40 | 3.57× |
| Capital left unused | $38,420.12 | — |

**Do not read this as an argument to size up.** It scales the **losers identically** — today's
−$1,111 becomes ~−$4,000 — trips the Safe −30% / Bold −50% kill switches far faster on a bad day,
and **C31 is explicit that J's own 667 trades run +$4,576 at 1–2 lots and −$17,461 at 3+ lots.**
Sizing up is the documented killer. There is no market-impact model behind these figures.

### 4.6 The late fade — theta, not direction. No standdown existed.

Through 13:20–13:48 the ribbon was **BULL**, htf_15m **BULL**, bull_score 9–11, VIX 16.33→16.55, and
**SPY ROSE 771.135 → 772.34 with its high AFTER both entries.** The 772C still bled 1.22 → 0.90.
**Every directional instrument was right; the option lost anyway** — textbook C3 (SPY-price edge ≠
option edge).

**A late-afternoon standdown is REJECTED and deliberately not pre-registered.** It would be fitted
to two trades totalling **−$114** on the best day on record, against a tape where every instrument
was correct. That is curve-fitting noise.

---

## 5. ENGINE, CRITICIZED

### 5.1 First-session verdict per newly-live change

| Change | Verdict | Evidence |
|---|:---:|---|
| **SHIP A** exits anchor to real fill — **core** | ✅ **EVIDENCED** | 6 reanchor markers, 5 applied, 1 conservatively refused on unknown fill. |
| **SHIP A** — **fleet half** | ⚠️ **EVIDENCED BY ARITHMETIC ONLY** | 19/19 fill-anchored, discriminating on 16/19 — but the success branch **emits nothing**. Provable only by reconstructing stop arithmetic. **C7.** |
| **SHIP B** `block_elite_bull` lifted | ✅ **EVIDENCED, load-bearing** | **+$1,139.62** = exactly safe-2 + bold-2. All 82 `ENTER_BULL` were ELITE + level_reclaim — precisely what gate #3 refuses. Real control found: on 08-03 the core emitted `SKIP_ELITE_BULL_LEVEL_RECLAIM` while fleet arms **placed** at the same minute. |
| **ATM-TIER-EXTENSION-2K-10K** | ✅ **EVIDENCED** — ⚠️ **but it is leverage** | 6/6 strikes == `round(spot)`. See §6.3: **symmetric leverage in a strike-selection costume.** |
| **IEX tail** on level refresh | ✅ **EVIDENCED** | 80/171 refreshes used tail bars; `intraday_rth_high` freshness **28.6% → 75.0%**, median latency **9.1m → 0.0m**. |
| **FIX2** vwap emission un-deadened | ✅ **RUNS** — ⚠️ **net negative today** | First live fleet session ever (import-dead since 2026-06-25). +$721 gross, but **−$247.50 on displacement** (§3.6). |
| **SHIP C** risky-3 qty10 under $0.50 | ❌ **UNPROVEN — possibly UNREACHABLE** | **0 fires.** Cheapest contract all day $1.038 = **2.1× the threshold.** With ATM live, its `n>=10` kill criterion **can never resolve.** |
| **L246** floor-rescue (risky-1) | ❌ **UNPROVEN — structurally UNREACHABLE** | 0 fires. Its sibling ship killed its own precondition: `FLOOR_WALL` **103 → 0**. |

**Two ships went out the same night and one removed the condition the other exists to handle.**
Neither may be logged as "shipped and working."

### 5.2 What the engine refused, and what it cost

**+$802 net** — after removing a **$2,533 double-count** in the first pass. `NOT_FLAT` rows are **not
missed money**; they are the **Rule-4 no-add guard working as designed** (C31), and
`VETOED_BY_MODELS` is evaluated *before* the flat check, so those vetoes would have been `NOT_FLAT`
anyway. Priced on broker-verified-flat refusals only.

**Of that, bold-2's PDT compliance is +$767.50.** bold-2 was denied **21 ELITE setups** between
12:26:55 and 13:48:26 — including the **12:28 769C wave that paid the other four arms +$2,192**.

> **The refusal irony, stated plainly: the one arm that OBEYED PDT paid $767.50 for it. The three
> arms that ignored it entirely were never charged, because paper does not enforce it.**

### 5.3 The operator was blind, and worse than one lane claimed

The ENGINE lane reported that all 21 `RISK_DENY_PDT` events were suppressed by the entry-block
watcher's 3-alert daily cap (spent by 10:17 ET). **I re-ran the watcher's predicate against all 21
rows: 0/21 qualify.** `entry_block_watch._qualifies()` returns `False` whenever
`row["verdict"] == "ENTER_BULL"` — those rows were **never alarm candidates at all**, so the cap is
irrelevant to them.

**The real defect is broader than claimed:** the watcher is **structurally blind to every risk-gate
denial, on any day, at any alert budget.** The lane's proposed fix (per-mechanism budget) **would
not have fixed this case** — `_qualifies` runs before the cap check. Corrected here; the follow-up
is re-scoped.

### 5.4 Other machinery defects found today

- **Safe core's PDT gate mode rests on a stale account.** `params.json` justifies `cash_settlement`
  by naming `PA3DHPT7KIQE` / `multiplier=1`; the live account is `PA3POKNV46VG` / **`multiplier=4`**.
  The 08-01 reset minted margin accounts and safe's provenance was never re-checked. safe-2 took
  exactly 3 day trades and logged **zero** `RISK_DENY_*` rows all session — **luck, not design.**
- **The nightly would have lied tonight.** `Gamma_WinnerAutopsy` fires 16:25 ET; Alpaca does not
  serve same-day-expiry OPRA until ~16:21. Nine of ten winners returned **HTTP 403** through the
  full retry ladder; every symbol then fetched in **0.17s** from ~16:30. The old code counted the
  loss, warned, and **still headlined capture = 4.3% built from a single $9 trade** while $4,726 of
  winners sat unfetched. Pure C7 — **fixed** (§8.2).
- **New, unreported until now:** fleet placement rows log `tp1_premium_pct: 0.5` / `tp: 2.07` while
  `strategies.py` defines `0.40` and live exits prove **+40%** (risky-3 entry 1.40 → TP1 fired at
  2.01; +50% would need 2.10). **Stale log-only field** — same C7 family.
- **A dead knob inflated a denominator.** `EXIT_MENU` advertised 7 policies and delivered 6 (§4.2),
  making the "hold longer" end look twice as corroborated as it was.

### 5.5 PDT headroom for the rest of the week

| Arm | Used (5d) | Limit | Headroom Wed–Fri | Rolls off |
|---|---:|---:|---:|---|
| safe-2 | 4 | 3 | **−1** | 2026-08-11 |
| bold-2 | 3 | 3 | **0** | 2026-08-12 |
| safe-3 | 6 | 3 | **−3** | 2026-08-11 |
| risky-1 | 5 | 3 | **−2** | 2026-08-11 |
| risky-3 | 6 | 3 | **−3** | 2026-08-11 |

**Zero headroom on all five arms Wednesday, Thursday and Friday.** The trailing window contains both
08-03 and 08-04 until 2026-08-11. Unenforced on paper (the field is absent); on live money safe-3
and risky-3 are at **double the limit** and would be **closing-only for 90 days**.

> **"Trade like this again" is not available at these account sizes this week.**

---

## 6. CAN WE DO IT AGAIN?

### 6.1 Archetype frequency — this was a 1-in-20 tape

Today was **gap-go**, same as Monday: opened at the low (`open_loc` 0.008), low on bar 1, high on the
**last** bar, body **+1.40%**, range 1.69%, VIX 15.6→16.4. One-way up from first bar to last.

| Slice | Count | Share |
|---|---:|---:|
| That exact one-way character | 20 / 395 | **5.1%** |
| The `+body ≥ 1.0` variant (Mon **and** Tue are both this) | 7 / 395 | **1.8%** |
| **Hostile archetypes** (range-chop + gap-fade + pin-day + inverted-V) | **251 / 395** | **63.5%** |

Mon + Tue being the same rare variant is **a cluster, not a regime.**

### 6.2 What last night's work bought vs what the tape gave

Yesterday's config replayed on today's tape yields **$2,061.25**.

> **Config bought $1,563–$2,031 (43–56%). The tape would have paid $1,593–$2,061 (44–57%)
> regardless.** Stated as a range, not a point — the counterfactual's fleet rows are simulated and
> carry the harness's measured **+29.4%** optimism.

**Leave-one-out attribution:**

| Change removed | Effect on today |
|---|---:|
| SHIP B elite-gate lift | **−$1,141.00** *(EXACT — zero simulation)* |
| ATM-TIER-EXTENSION | −$984.39 |
| SHIP A exit re-anchor | **+$147.26** *(it cost money today)* |
| FIX2 vwap emission | **+$247.50** *(reverting IMPROVES the day)* |

Sum of LOO −$1,730.63 vs joint −$1,562.75 → **$168 of non-additive overlap.** The IEX-tail ship is
**unmodelled** — its contribution sits silently inside the "tape" bucket, so **57% is an upper bound
on the tape's true share.**

### 6.3 The hard-day replay — ❌ FAILED, and the culprit is named

Across the **five most hostile-character days** in the live window (selected on regime-library
**features, not on P&L**), the ATM tier lost **−$1,303.60** more than OTM-2 would have: real
**−$1,690.00** vs **−$386.40**. Mechanism splits cleanly:

- **−$737.00** from trades OTM-2's **$0.30 min_entry_premium floor would have refused outright** —
  every one a loser. *The participation the extension was shipped to buy is negative on hostile
  tape.*
- **−$566.60** from **~1.7×–3.1× premium per contract at unchanged contract count.**

On 08-04 the mirror image holds exactly: **zero** contracts floor-blocked, and the entire
**+$2,235.87** came from notional.

> **ATM-TIER-EXTENSION is not a strike edge. It is a ~2.2× size increase wearing a strike-selection
> costume.** Net over six days **+$932.27** — one trend day paying for five hostile ones.

**I did not revert it.** n = 5 days / 28 round trips is an **anecdote**, and its own pre-registered
kill criterion (n≥10 elite fills/arm **or** 10 sessions net<0) is the authority and is **not met**.
Reverting on five hand-selected days is the same recency-overfit in the opposite direction.

### 6.4 The honest expectancy

| Basis | EV/day |
|---|---:|
| Live record, 24 days | +$104 |
| **Live record EXCLUDING today (23 days)** | **−$49.13** |
| Population-weighted archetype mix (`mix_ev`) | **+$73.71** |
| Optimistic | +$137 |
| Sizing-scaled baseline | +$48 |
| Payoff halved | +$45 |
| Both pessimistic | **−$44** |

**Today is 145% of the all-time live total.** The 24-day record spans two sizing eras (~$1.7K arms
until the 08-02/03 $5K rebuild), so the −$49.13/day is an honest **floor**, not a like-for-like
rate. `mix_ev` weights a thin per-archetype record by population share — right *shape* of estimate,
weak point estimate (several archetypes have n=1).

**Answer: not this week, and not on this archetype mix.** PDT alone forecloses it (§5.5).

---

## 7. TWIN + PROCESS

### 7.1 Instrument health

| Instrument | Status | Evidence |
|---|:---:|---|
| Crypto twin — uptime | ✅ **GREEN** | 1,200/1,199 ticks = **100.0%**, 0 incidents, sentinel GREEN. |
| Crypto twin — **P&L** | 🚨 **BLED** | **14 organic round trips, 0 winners, −$2.86.** 12 of 13 knifed by structure stop; ten consecutive losing re-entries in one 3-hour block. Organic book now **n=37, 8.1% WR, −$4.04**. |
| Ladder `time_stop_et` fix | ✅ **ORGANICALLY PROVEN** | Both lanes entered 18:05Z and rode **through** the 19:50Z boundary still open; post-fix `time_stop` count **0**. Bug was an **8h10m/day (34% of the clock)** dead zone, not a "15:50 bleed". |
| Max-hold journaling fix | ⚠️ **NEVER EXERCISED** | The only `max_hold` EXIT_FILLED row in existence is **the backfill the commit itself wrote.** |
| Path-coverage battery | 🚨 **COVERAGE ILLUSION** | Reports **9/9 GREEN**; true designed-stage hit rates are `TP1_TRAIL` **2/22 (9%)**, `CAT_CAP` **6/22 (27%)**, `MAX_HOLD` **3/22 (14%)**. `time_stop` is in the *acceptable* set — **so a regression to the SPY default would grade GREEN.** |
| WinnerAutopsy | ✅ **HEALTHY** | 16:25 population run scored **35/35, 0 no-bars**, `sufficient_n` TRUE, capture 31.4%. Chained pain-ledger (189/190) + fill-latency (21) clean. |
| Violin (post-IEX tail) | ✅ **IMPROVED** | `intraday_rth_high` **28.6% → 75.0%**, latency **9.1m → 0.0m**. One session each side — directional, not validated. |
| Theta clock | ❌ **DEAD** | `greeks_raw` non-null **0/560** rows over 20 real position-instances. Worse: it reports its failure streak as **"29/29" from a hardcoded docstring**, not a live counter. True figure ~49/49. |
| `double_bottom_base_quiet` | ⚠️ **ARMED, NEVER TRIED** | Armed 34 days; fired **10 times in one session**, **PLACED=0** (6 `VETOED_BY_MODELS` + 4 `RISK_DENY_RISK_CAP`). Zero fills is evidence nothing **let** it try. |
| Git hygiene | ⚠️ **L242/L252 RECURRENCE** | 0 stashes ✅, 56 unpushed. `analysis/manager/` is tracked and not gitignored: **77 tracked vs 550 untracked, nothing committed in 39 days.** `auto_commit_candidates.py` remediates `strategy/candidates/` **only** — same disease, no remediator. |
| Safety gate | ✅ **59 passed** | Re-run by me this session, 8.68s. |
| `Gamma_RegimeAttribution` | ✅ **Ready** | Registered, `State=Ready`, 17:45 ET daily; artifact reads archetype `gap-go`, `mix_ev` 73.71, `day_pnl` 3624. |

**The twin's day is the most useful thing in this report.** On the same calendar day SPY had its best
session on record, the twin ran the *same mechanism* — re-enter after a structure stop with only
flat-verify and `risk_gate` between fires — and **lost every single trade.** That is mechanism
corroboration for §3, and it is exactly what a hard day looks like.

> One lane's twin numbers are one trade stale (13 trips / −$2.6579); the true full day is **14 /
> −$2.8621**. All differences are conservative. Its quantified "0.33% round-trip spread" driver is
> **not established** — that figure came from a *different* (bear-skip) population, and the twin's
> organic trips lose a mean of −0.1335%/trip, which is impossible if every cycle paid 0.33%. **The
> bleed is real; its price tag is not.**

### 7.2 My two process lessons, stated plainly

> **1. Count what was EXECUTED, not what was LOGGED.**
> I raised a defect alarm on "seven entries" when only four were placed, and `placement.placed` was
> sitting in the same JSON object as the field I did read. **A decision row records what was
> DECIDED, not what was EXECUTED.** That was not a judgment failure — it was a field I never opened.
> Encoded as lesson clause **1a**.

> **2. An intra-session P&L window is CENSORED, not merely small — and the censoring correlates with
> sign.**
> Losers resolve in under two minutes and print; winners are still open and contribute nothing. Four
> fast losses plus one 7-minute-old open position is what a **working** trend-continuation setup
> looks like at minute 11. Both my alarm and my retraction drew from that same biased sample, and
> only the second one landed right — **by luck, not by method.** Encoded as the **mid-session revert
> evidence bar**: mechanism defect or kill-switch breach only, **never intra-session P&L**.

**And a third, earned the hard way today:** **name the mechanism before naming the fix.** `RUN_VWAP=False`
attacks an entry producer for an exit pathology. Encoded as clause **1b**.

**Two more self-inflicted findings worth recording:** three lanes shipped headline numbers that were
wrong and **caught themselves** — a survivorship-filtered ladder re-baseline (excluding a *time*-window
bug's rows is a **duration-conditioned filter**, not cleaning), a $2,533 refusal double-count, and an
exit model that booked **profit on stop-outs**. Each was disclosed rather than quietly fixed. That is
the standard. It is also a warning: **the first number a harness produces has been wrong more often
than it has been right this session.**

---

## 8. TOMORROW

### 8.1 What is armed — nothing new

**No change was armed by any lane tonight.** Every one of the five newly-live changes stays exactly
as it ran today. Explicitly **NOT** shipped: any re-entry cooldown at any value, any `RUN_VWAP`
change, any exit-shape edit, any `params.json` change, any ATM-tier revert, any late-day standdown.

### 8.2 What DID ship (docs, tooling, guards — no trading path)

| Commit | Content |
|---|---|
| `ece23fdd` | LENS 1 re-entry adjudication + lesson clauses 1a/1b |
| `b4ec1575` | LENS 3 engine audit |
| `50efba6e` | **winner_autopsy data-integrity rail** (any OPRA fetch loss → run marked DEGRADED, **capture ratios withheld**; a missing number makes a human look, a plausible wrong one does not) + **EXIT_MENU dead-knob fix** + wave grouping + 9 RED-proofed guards |
| `eef059be`, `0c388f08` | LENS 4 decomposition tooling + **`Gamma_RegimeAttribution`** nightly (17:45 ET, $0, stdlib-only, fail-open, places nothing) — answers *"was that us or the tape?"* automatically, every night |
| `631619de`, `043af746`, `17457b2a` | LENS 5 twin/process audit + 3 lesson-inbox items |

**56 commits unpushed — the orchestrator audits and pushes. I did not push.**

### 8.3 Kill-criteria status after ONE live session

| Change | Kill criterion | Status |
|---|---|---|
| SHIP B elite-bull lift | n≥10 elite fills/arm **or** 10 sessions net<0 | **3/10 fills** (safe-2, bold-2), **1/10 sessions, net +$1,139.74.** ✅ not killed |
| ATM-TIER-EXTENSION | same | **1/10 sessions, net +$2,236.** ✅ not killed — ⚠️ but see §6.3 |
| SHIP C qty10 <$0.50 | n≥10 fills | **0 fires. CANNOT RESOLVE** — flag as possibly unreachable by construction |
| L246 floor-rescue | — | **0 fires. Structurally unreachable** while ATM is live |
| FIX2 vwap emission | — | Ran; **+$721 gross, −$247.50 on displacement.** Under observation, not killed |

### 8.4 Priority queue for tomorrow's after-4pm block

1. **🚨 FLEET-PDT-PARITY (#1).** Route `fleet_live.py:660` through
   `pdt_tracker.fetch_day_trades_used_5d`, as `heartbeat_core.py` already does. **Design: read the
   true count, log it always, enforce only when `live:true`** — halting three paper arms teaches us
   nothing, but a gate that reads `0` forever teaches us nothing *and* hides a breach. Add a
   **vary-and-assert** guard (C14): the count must **change** across a session. Ships under standing
   paper autonomy with prereg + guard + RED-proof + one-line revert. **No J gate.**
2. **PREREG-A — vwap stop width.** A/B over `{−0.06 control, −0.12, −0.20, −0.25, catastrophe-only}`
   on real OPRA, with **entries-per-day and re-entry-sequence-count as OUTCOME variables**, not
   covariates. Scored prediction recorded in advance: **widening the stop materially reduces
   re-entry count**, because every re-entry today followed a stop-out.
3. **PREREG-B — `trigger_level=None` silently disables the structure stop** on every
   `stop_mode='structure'` shape for every trigger-level-free setup. Needs an explicit assertion,
   plus a decision on what continuation setups use as chart invalidation (**VWAP itself** is the
   obvious candidate — it is in the setup's name).
4. **PREREG — displacement.** Does `vwap_continuation` systematically crowd out higher-quality ribbon
   entries by occupying the arm? Today says +$247.50, n=1, split by arm. Needs the full population.
5. **PREREG — runner BE-floor vs chandelier trail.** +$1,912–$2,230 on today's winners. Bar to arm:
   full-population A/B **including losers**, stratified by day archetype; the trend-day-only effect
   **must survive on chop.**
6. **Re-run `winner_autopsy` over the full population** under the corrected EXIT_MENU —
   `all.md`/`all.jsonl` still carry pre-fix numbers, and §4.2 shows the policy ranking is wrong until
   they do.
7. **Fixes, ranked:** move `Gamma_WinnerAutopsy` to ≥16:35 ET · repair `find_entry_decision` to match
   on symbol **+ timestamp** · emit a fleet reanchor marker (closes the §5.1 C7 gap) · make
   `entry_block_watch` see risk-gate denials at all · re-check `params.json` `pdt_gate_mode` against
   the **live** multiplier · point a remediator at `analysis/manager/` · pin SOD to broker
   `last_equity` · fix theta-clock's hardcoded failure counter.

### 8.5 What to watch

- **PDT (§5.5)** — zero headroom on all five arms Wed–Fri. Paper won't stop it; the ledger will.
- **The −6% stop on a chop day** — that is the treadmill, and it is the day we have not seen yet.
- **Whether wave-2-style capture (64.6%) repeats** once the expiry-mechanics distortion is absent.
  That is the honest read on whether our exits are actually fine.
- **`Gamma_RegimeAttribution`'s first organic fire tonight at 17:45 ET.**

### 8.6 What needs J

> **Nothing.** No live-money arming, no secret, no irreversible external action, and no genuine fork
> — the fleet-PDT design question has an obvious right answer (§8.4 #1) and I took it rather than
> handing over a menu. Everything above is **for REVOKE, not for approval.**
>
> The one thing I want J to *carry*, not decide: **the ATM tier is leverage, not a strike edge**
> (§6.3). That is a risk-posture fact about the current stack, and it is his to disagree with.

---

## 9. SPOKEN BRIEF

> 1. Best day on record — **plus three thousand six hundred seventeen dollars and eighty-five cents**, all five arms flat at the close, and it reconciles to the cent.
> 2. But I have to lead with the bad part: **we could not legally have traded it.** Three arms took seventeen day-trades against a limit of three, because the fleet's PDT gate read zero on eleven hundred fifty-two straight ticks.
> 3. All five arms now have **zero headroom Wednesday, Thursday and Friday.** Whatever else happens this week, we cannot trade like today.
> 4. Ninety percent of the money came from **two trades.** Six of eight signal clusters lost. This was not the system firing on all cylinders.
> 5. The tape did about half of it. Last night's work bought roughly forty-three to fifty-six percent — and today's exact shape is **one day in twenty.**
> 6. Take today out and our live record is **minus eleven hundred thirty dollars over twenty-three days.** I'm not going to pretend one day changes that.
> 7. The best runner survived because one arm doesn't ratchet its trail. The other four gave theirs back to an ordinary pullback — **our profit-lock was the binding constraint on the best trend day we've had.**
> 8. I got the mid-session call wrong. I flagged a defect on seven entries when only four were placed, using an eleven-minute P&L window that structurally hides winners. Then I took it back for no better reason. **Both calls were unearned.**
> 9. The real defect was underneath all of it: a continuation setup has no trigger level, so its structure stop was silently a no-op and it ran a **six percent stop inside a ten percent noise band.** That's the fix — not a cooldown.
> 10. Nothing new is armed, nothing needs your approval, and everything is on the revoke surface. **Great day, honestly audited: some of it was ours, a lot of it was the tape, and the machine that made it needs work.**

---

*No trading-path code, params, or producer flags were changed by this review. ORACLE figures are
labelled UNREACHABLE and never mixed into a live-executable column. All n-small results are labelled.
Where two lanes disagreed, the disagreement is stated and adjudicated rather than averaged.*
