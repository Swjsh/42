# FRIDAY 2026-08-07 — FULL SYNTHESIS

> Clock verified at write time: `2026-08-07 12:53:00 Friday EDT / market_hours=True` (setup/scripts/et_clock.py).
> Trading-path integrity: **all 5 lane verifiers report no_live_file_touched=true** — zero engine/config files modified during market hours. Every claim below was independently re-derived by a verifier before landing here.
> Dollar labels: **EST** = engine-tick premium track + BS surface (MAE ~$0.27/unit disclosed); real-OPRA re-price lands after ~16:21 ET and supersedes every EST cell. No ORACLE cells anywhere today.

---

## FOR J — 12 LINES MAX

1. Friday realized ≈ **−$1,821** (morning −$629.46, then a second entry at 12:06 gave back ≈ −$1,192; final number at EOD). The Wednesday spiral did **NOT** recur — one trade per arm, one stop, zero re-entries.
2. Both entries were the shape we PAY for — level-tied, historically **+$70.8/entry (40% WR)**. They lost anyway. That is variance, not process failure. No filter change would have avoided the morning loss ($0.00 counter-cell, proven twice independently).
3. 10:15–11:45 the engine refused a **2.7-point SPY run** (770.50 → 773.17): 182 straight HOLDs, bull score 10/11, blocked by exactly two filters.
4. **Filter 7 = "volume divergence"**: a red bar out-volumes a green bar within 2 bars → block. It is POLICY, working as coded — but a **+$0.06 green bar** armed it at 10:15 and killed the one tick everything else approved.
5. **Filter 10 = "buyer pressure"**: bar volume must be ≥0.7× the 20-bar average. It is a **DEFECT** — the 0.7 was calibrated on full-market (SIP) volume but runs live on IEX, which prints **~3.6% of the tape**. About **a third of its refusals flip to PASS** on the real feed, including the 11:05–11:20 breakout at 773.
6. Skipping today's refusals was worth ≈ **+$886 EST** one-trip — but the unconstrained version **churns to −$393**, and the 391-day battery (finally run tonight after being queued twice) says **every relax cell is negative and under the n≥20 floor. Nothing clears.**
7. So **no filter values change tonight**. What ships at 15:55 is one behavior-neutral wiring fix: bull filter 10 gets its **own knob** — today it secretly shares bear filter 9's key, so the frozen prereg was un-shippable as written.
8. Replay fidelity **GREEN 68/68** — the engine did exactly what its code says all day. The OTM-2 tier revert's first live fill (risky-3 774C ×12): correct strike, correct size, PASS.
9. Naive fix is unavailable: the live key's SIP feed is **15-minutes delayed** (verified). The real path is re-calibrating on the feed we actually trade — prereg frozen, weekend grind.
10. **bold-2 stays PDT-dark until Wed 08-12.** Monday brings **zero** PDT roll-off for every arm; first relief Tuesday.
11. Week ≈ **+$1,867 realized** — Tuesday carried it (ex-Tue ≈ −$1,757). Small-losses held every day but Wednesday.
12. Your Monday line — "make sure nothing is gated that actually works" — today violated it, and it's now **measured, named, and instrumented** (feed-divergence tracker live, 5 days of artifacts) instead of guessed at.

---

## 1. Why we lost this morning — and whether the entry was even wrong

**The loss:** entries 09:46–09:47 on the push above PDH 771.82; all four active arms long 772C/774C; structure-stopped 10:01–10:02 on the 5m close 771.30 < 771.53. Per-arm: safe-2 3× 772C 1.67→1.16 (−$153) · safe-3 8× 772C 1.33→1.11 (−$176) · risky-1 5× 772C 1.33→1.14 (−$95) · risky-3 12× 774C 0.62→0.45 (−$205). bold-2 dark (PDT). Book −$629.46, flat by 10:02.

**The entry was RIGHT by every measure we own:**
- **PAY-cohort shape**: level-tied + structure signature — the cohort that runs +$70.8/entry, 40% WR (n=55) vs −$103/entry (0% WR) for bare entries. Best time-of-day bucket (09:30–09:59 historically +$1,050).
- **V-d1 agree**; structure detectors correctly BLIND-abstain at 09:46 (~3 closed 5m bars — too early by design, not a miss).
- **Not enlargeable**: both Lane 2 and Lane 3 independently ran the morning counter-cell — relaxing filter 7, filter 10, or both changes the morning by **$0.00 exactly** (09:35–09:45 ticks were multi-blocked; the 09:46 entry had zero blockers and fires identically under every relax).
- **Neither frozen shadow rule** (V-d1 / V-e3) would have refused it.

**The one soft cell:** we bought a 0.77-premium contract 0.3–0.8 under a 1-minute-old session high — a failed-PDH-push entry. That is a texture observation, not a rule breach; it goes to the entry-quality ledger, not to a filter proposal.

**Verdict: variance.** A PAY-shape trade lost. The Wednesday spiral shape did **not** recur — one trade per arm, one mechanical stop, zero re-entries, no averaging down. Process held.

**Tier-revert first live verdict — PASS.** risky-3's 774C@0.62 ×12 was the first fill under last night's OTM-2 revert: `pick_strike(772.045, $4,946, C) = 774` recomputed = actual fill; qty 12 = elite tier $2–10K; SHIP-C boost correctly no-op. Loss per premium-dollar: risky-3 −27.4% vs ATM arms −30.5%/−16.5%/−14.3%.

---

## 2. The refusal — named, classified, priced

**The window:** 10:15–11:45, 182 verdicts, ALL HOLD, 70 ticks carrying live bull triggers (level_reclaim + confluence, score 10/11). SPY ran 770.50 → 773.17 underneath. Refusal actually extended to 12:05; the engine entered at 12:06:03 (a relaxed engine's latest entry = 11:46, 20 minutes earlier). Sole-blocker census per account: sole-[10] ×27 ticks, sole-[7] ×5, sole-[11] ×5 (f11 firewalled — Rule 2, never touched). **Caveat that reframes the launch brief:** filter 11 co-blocks 12 of 24 refusal bars — "one rotating sole blocker" holds on only 9 bars, so any f7/f10 unlock value must model f11's joint distribution or it overstates.

### Filter 7 — NAMED: `_bullish_volume_divergence_failed` (filters.py:1352, called :1182-1186) — **POLICY**
Green bar followed within 1–2 bars by a red bar with volume ≥ the green bar's → block; candidate pairs include the current bar. **No minimum body/volume on the breakout leg** — at 10:15 a +$0.06-body, 17,148-share green bar armed the invalidation (red bar 30,662) and killed the single tick filter 10 approved (f10 = 0.999 PASS there). Reproduces identically on SIP — design, not feed. Class: **POLICY as coded, with a named design gap** (breakout-leg-minimum qualifier → prereg, §5).

### Filter 10 — NAMED: `buyer_pressure_bar_v11` (filters.py:1343, :1206-1212) — **DEFECT (calibration infidelity)**
Green trigger bar AND volume ≥ 0.7 × prior-20-bar mean (also blocks on ribbon None — not today's case). The mechanism finding, three parts:
- **Suspected mixed-feed bias: REFUTED.** One IEX fetch (`heartbeat_core._fetch_spy_5m`, feed=iex since commit 667217a1, 2026-06-26) feeds BOTH bar volume and vol_baseline_20 — internally consistent; the 08-03 IEX tail (levels path) never touches f10 inputs; no 08-03 break in block rates.
- **Actual defect: CONFIRMED.** The 0.7 constant was ratified on SIP ratios but runs live on IEX (median **3.6% of SIP volume**). **34–35% of sole-[10]-elite refusals (62/176 ticks, 15/44 unique bars) flip to PASS on the ratified feed** — chronic since 06-26, steady across all 7 sessions with refusals. Today: 3 of 9 f10-refused unique bars are feed flips — **11:05 (IEX 0.477 vs SIP 1.714 — SIP printed a 987,522-share ~2× surge that IEX showed as 12,799), 11:10, 11:20 — exactly the >773 breakout leg.**
- **Naive fix unavailable:** SIP on the live key is **15-min delayed** (verified 16:11Z). Feed noise is **bidirectional** across the week (12–26% of bars/day flip) — a variance defect, not a one-way winner-suppressor; today it happened to be one-way against us.

### Priced (ALL EST — evening OPRA re-price supersedes)
| Lens | f10 relax | f7 relax | both |
|---|---|---|---|
| Lane 2 book walk, one-trip PDT-safe | **+$885.51** | +$792.79 | +$885.51 |
| Lane 2 extended (3rd+ trips, pdt_contingent) | **−$393.12** (churn) | +$336.22 | +$617.57 |
| Lane 3 completed-bar walk (3-lot safe-core; HEAD −$82.8) | **−$150.60** (worse than HEAD) | +$58.20 (OPEN at tape end) | +$58.20 |

The two EST lenses **disagree on f10's sign** (re-entry policy is the difference). That disagreement is exactly why nothing value-shaped ships on today's numbers — the adjudicators are the real-OPRA re-price (≥16:21) and the 391-day battery, and **the battery already answered: no.**

**Attribution correction that matters:** the launch exhibit "10:15 block=[10]" was a tick-vs-trigger-bar artifact — the 10:15 **trigger bar's** binding blocker was **filter 7**, not 10. Today's tape does NOT independently support the 08-03 gate table's "+$4,535/2d" f10 attribution; f10-relax-alone made today *worse* in the completed-bar lens. The frozen prereg was honored and its runner finally ran (below).

**Logging caveat:** `bull_blockers` has only existed since 07-28 — the block-rate history is 9 sessions, and today is the worst on record (f10 blocking 81.8% of ticks, f7 47.2% at snapshot). Pre-07-28 zeros are logging absence, not pass rates.

---

## 3. What the replay proved

- **Fidelity GREEN 68/68** verdict match (safe 34/34, bold 34/34; full-field 33/34 + 34/34) via `hc._build_payload → hc._engine_verdict` with live-recorded VIX/levels and the engine's own IEX feed. Both live entry bars reproduce field-for-field. Single field-diff bar (10:05, forming-bar trigger flip, HOLD either way). **Nothing quarantined. The engine did exactly what its code says.**
- **The 391-day population battery ran** (507s, baseline 215 trades/41 bulls) — the instrument queued twice and never run until today, honoring the frozen 08-04 prereg cells and gates verbatim: **f10_relax_50 n=9 −$1,049 · f10_relax_35 n=13 −$670 · f10_off n=15 −$762 · f7_off n=3 −$674 · joint_relax35 n=17 −$1,629 (anchor FAIL) · joint_off n=18 −$1,566 (anchor FAIL)**. Every cell below the n≥20 floor AND negative AND BH-insignificant; joints worse than singles. **Verdict: NOT_CLEARED, both preregs.**
- **Structural finding bigger than the verdicts:** the sim battery adds only 3–18 trades over 391 days because run_backtest's baseline rarely reaches f10/f7-as-sole-blocker — while the LIVE engine logged 27+5 sole-blocked elite ticks per account in 90 minutes today. **The frozen instrument cannot see the live-refusal population** that the +$4,535/2d origin claimed to measure — and this cuts both ways: the battery can't vindicate the origin number either. Successor instrument: §5.
- **Feed-divergence instrument** (new, standing): 5 daily artifacts committed; IEX-vs-SIP flips f10 on 12–26% of bars/day, f7 on 12–25%. Today: IEX f10 pass rate 14.3% vs SIP 29.6%; all 5 disagreement bars inside the refusal window.
- **Wave 2 (after lane snapshots):** 12:06–12:07 all four active arms re-entered on a clean blockers-[] level-tied trigger at 772.89 (773C ×3/×8/×5, 775C ×12) — a NEW confirmed trigger, not an averaging-down re-entry — and stopped 12:25–26 for ≈ −$1,192 further. Day realized ≈ −$1,821. Replay reproduces the ENTER_BULL.

---

## 4. THE CLOSE PACKAGE — applied at 15:55 ET, item by item

**Verdict up front: ONE behavior-neutral diff ships. Zero filter values change — the battery refused every cell, and that refusal is the honest result.** Package doc: `analysis/deep-research/CLOSE-PACKAGE-2026-08-07.md`.

**ADJUDICATION (resolved here — the one judgment call left, now made):** two variants of the same bull-f10 knob-split exist. Lane 1's inline heartbeat_core-only edit (FRIDAY-BLOCKERS sec 6, with regex guard `test_f10_knob_split_2026_08_07.py`) is **SUPERSEDED — do not apply it and do not create its guard file**. Apply ONLY the close-package superset (commit 0a45d396's staged diffs), which does the identical live-path change AND fixes the same shared-knob coupling in orchestrator.py. One diff, not two.

### A1 — UNCONDITIONAL: bull-f10 knob threading (DEFECT-class, byte-identical tonight)
Fixes: `heartbeat_core.py:647/654` and `orchestrator.py:1030/1075` hard-tie bull `f10_vol_mult` to `filter_9_vol_multiplier` — any future bull relax would silently relax bear f9 (a cell no battery ever ran). The frozen prereg was un-shippable as written.
1. `git apply --check` both diffs first — **STOP on conflict, never force** (other lanes committed after generation; both were CLEAN at freeze).
2. `git apply analysis/staged/f10-bull-knob-threading-2026-08-07.diff` (5,447B; threads dedicated key `filter_10_vol_multiplier_bull`, falls back to the shared value — **key absent from both params files ⇒ byte-identical live behavior**).
3. `git apply analysis/staged/f10-guard-activation-2026-08-07.diff` (un-gates the env-gated guard).
4. `pytest backtest/tests/test_f10_bull_knob_threading_2026_08_07.py backtest/tests/test_feed_divergence_tool_2026_08_07.py` → expect **8 + 46 passed** (RED-proofed: 7-failed pre-apply; GREEN 8/8 on patched sandbox). Then `backtest/tests/test_engine_gates_parity.py backtest/tests/test_audit_fix_heartbeat.py` → expect **41 passed, unchanged**.
5. `python setup/scripts/commit_scoped.py "fix(engine): thread dedicated bull f10 knob (filter_10_vol_multiplier_bull), byte-identical while key absent" <the 3 files>`.
- **REVERT:** `git revert <sha>`. **KILL (frozen, n=1):** any tick where bull f10_vol_mult ≠ filter_9_vol_multiplier while the key is absent → revert same evening. REVOKE line: package SA1.

### B1 — RESOLVED to ELSE-branch: f10 value flip does NOT ship
Battery landed (commit 1bdc1f12); **no cell cleared**. Orchestrator appends to `automation/overnight/STATUS.md` the exact line from Lane 2's package: *"f10 value flip NOT applied — no cell cleared (all 3 f10 cells below n>=20 floor AND negative aggregate; battery ran, 391d, analysis/recommendations/f10-f7-population-battery-2026-08-07.json); prereg stays frozen; BULL-F10-PREREG-RUNNER (queue.md:14) CLOSES — runner has now run."* Mark queue.md:14 done citing commit 1bdc1f12. Machine-readable verdicts the orchestrator reads before ever touching params: `analysis/recommendations/bull-f10-buyer-pressure-relax.json` (NOT_CLEARED).

### B2 — RESOLVED the same way: f7 does NOT ship
`bull-f7-volume-divergence-relax.json` = NOT_CLEARED (f7_off n=3 −$674). Prereg was git-provably frozen (94157aa6, 12:23 ET) BEFORE its runner existed. Nothing ships; filter 7 stays armed.

### C — Regime-attribution self-heal (NOT trading-path; Lane 4's APPLY.md, 3 mechanical steps)
1. ~16:30 ET (after the spy_5m cache lands ~16:16): `backtest/.venv/Scripts/python.exe backtest/tools/build_day_archetypes.py`; verify `'2026-08-07' in days == True`.
2. `git apply analysis/deep-research/staged/regime-selfheal-2026-08-07/regime_attribution_selfheal.patch` (apply-check pre-verified clean) + copy guard test to backtest/tests/ + pytest → **3 passed** (RED-proofed: 3-failed on original, replicated by the verifier in a sandbox).
3. `commit_scoped.py "fix(instruments): regime_attribution self-heals missing target day (rebuild-on-miss); guard test" <2 files>`. REVERT documented in APPLY.md. Fail-open preserved.

### D — MANDATORY evening re-price (≥16:21 ET, before quoting ANY of today's dollars as final)
One command, clock-gated (refusal path live-verified rc=3): `backtest/.venv/Scripts/python.exe backtest/tools/reprice_close_package_2026_08_07.py` — re-prices today's refusal cohorts + the 11:05/11:15/11:30 named events on real OPRA, re-runs full-day feed divergence, diffs both lanes' EST artifacts. Plus Lane 3's `friday_replay_2026_08_07.py variants` on real OPRA (loader seam documented) → `## OPRA addendum` in FRIDAY-REPLAY-2026-08-07.md. Contracts needed: SPY260807C00770000/772000/773000/774000/775000. **Real numbers supersede every EST cell; a sign flip turns the affected disclosure item OFF — no ship decision depends on it, because nothing value-shaped shipped.**

**Explicitly NOT in the package (honest statement):** no f10 value change, no f7 change, no f11 touch (Rule 2 firewall), no feed switch (SIP 15-min delayed), no stop/exit changes, nothing from the graveyard re-proposed. The morning loss produced zero fix candidates because the entry was right.

---

## 5. Stays prereg / shadow — with clocks

| Item | State | Clock |
|---|---|---|
| **bull-f10 buyer-pressure prereg** (08-04, frozen) | NOT_CLEARED verdict filed; stays frozen; queue item CLOSES (runner has run) | Superseded as an instrument by the live-refusal battery below |
| **bull-f7 volume-divergence prereg** (08-07, frozen pre-runner) | NOT_CLEARED; filter stays armed | Next discriminating cell = breakout-leg-minimum qualifier (Lane 1 supplies the cell family) — freeze prereg BEFORE running |
| **Live-refusal battery** (decision-log-mined, 07-28..08-07, real OPRA, same gates + f7 qualifier sibling cell) | Named follow-up — the successor to the sim battery that can't see the live population | **Freeze prereg first; run = weekend grind 08-08/09** |
| **feed-consolidated-volume prereg** | Frozen, forward-clock | Weekend grind; **auto-STALE 2026-08-14** |
| **Feed-divergence f10/f7 instrument** | STANDING (5 daily artifacts, drift guard 46 tests) | Daily; doubles as f10/f7's revalidation clock per the 07-31 recency directive |
| **IEX-sensitivity addendum** for any future SIP-fed battery | Recorded in scorecard — every added-cohort must re-screen on IEX ratios (post-06-26) or it is not cleared for the live path | Attached to L2-3 successor |
| **GATE-EXPIRY-SOLE-BLOCKER-MINER** | Still queued, still not built (build target outside market-hours writable set) — explicitly not silently dropped | After-hours queue |
| **V-d1 / V-e3 shadow rules** | Running; neither would have refused today's morning entry | Day-2 cells fill tonight (16:25 fold) |
| **A1 kill rule** | Frozen n=1: bull f10_vol_mult ≠ f9 value while key absent → same-evening revert | Live from 15:55 apply |

---

## 6. Instruments status for tonight's EOD

| Instrument | Fire (ET) | Status |
|---|---|---|
| ChopMeter | 16:08 | Ready, LastResult 0 |
| Participation | 16:10 | Ready, LastResult 0 |
| WinnerAutopsy + V-d1 fold | 16:25 | Ready; entry-quality ledger rebuilt incl. today (244 events), analysis/entry-quality/* left for the nightly fold to own |
| spy_5m cache same-day land | ~16:16 | 40-session cadence verified (5 consecutive days at exactly 16:16) — gates package item C step 1 |
| Evening OPRA re-price (item D) | ≥16:21 | Runner committed, clock-gate live-verified |
| Violin | 17:35 | Ready, LastResult 0 |
| RegimeAttribution | 17:45 | **Structurally UNTAGGED today without item C** (library rebuilt premarket only — root-caused, one sentence: the 17:45 fire reads a library rebuilt at 08:40 ET, so the target day is never present); fix staged + RED/GREEN-proofed |
| Auto-draw | fired 11:35:04 | 11/11 levels verified on chart |
| Fleet PDT log parity | live 12:04 | Exact parity with independent broker recompute |
| **Known broken list** | — | **EMPTY** (last night's 3 anchor-fidelity REDs fixed in 3d9228d4, re-verified fresh: 23 passed) |
| Week scoreboard skeleton | committed | EOD fills chop-meter + capture-rate + V-d1 day-2 cells; all four J-phrases currently PARTIAL with evidence pinned |
| Test gates (fresh, this session's lanes) | — | Safety gate 59/59 PASS; fleet suite 155/144/99/96-passed runs across four verifiers, 0 failed |

---

## 7. Monday PDT table

Counts = our pdt_tracker margin-style computation (Alpaca PAPER returns null PDT flags; log-only except bold-2, which the risk gate enforces). **Includes today's both round trips** (wave-2 closes added +1 to every trading arm, exactly as pre-declared).

| Arm | 5bd day-trades (thru Fri) | Mon 08-10 roll-off | Mon posture |
|---|---|---|---|
| safe-2 | 10 | 0 | trades (log-only) |
| safe-3 | 8 | 0 | trades (log-only) |
| risky-1 | 10 | 0 | trades (log-only) |
| risky-3 | 11 | 0 | trades (log-only) |
| bold-2 | 3 | 0 | **DARK — enforced until Wed 08-12** (all 3 pairs dated 08-04; confirmed two independent ways; risk gate correctly refused 8 ENTERs today) |

- **Monday = ZERO roll-off relief for every arm.** First relief Tue 08-11 (−1). Wed 08-12 big relief (08-04 exits roll off; bold-2 → 0, un-darks).
- Week book (broker fills, sell−buy per symbol per ET day — exact because everything flattens same-day): **Mon +534 / Tue +3,624 / Wed −1,935 / Thu +1,465 / Fri ≈ −1,821** → WTD ≈ **+$1,867** realized, ex-Tue ≈ −$1,757. Final Friday number lands at EOD; base rate before this week was −$1,372.

---

## 8. Gamma — spoken brief (10 lines)

1. Honest first: I'm down about eighteen hundred today, and both trades were the kind I'm built to take — level-tied, the pay shape. They lost. I was surprised too.
2. What I did NOT do matters more: one stop per arm, zero re-entries, no averaging down. Wednesday's spiral did not happen.
3. What I did wrong was in between: from ten-fifteen to noon I refused a two-point-seven SPY run, a hundred eighty-two straight holds.
4. Two filters did it, and I can finally name them. Filter seven punishes a green bar when a red bar out-volumes it — and today a six-cent green bar was enough to arm that. That's a design gap, not a broken part.
5. Filter ten demands volume ratios that were calibrated on the full market feed — but I watch a feed that prints four percent of the tape. A third of its refusals today pass on the real numbers. That's a defect, and it's mine since June.
6. I priced the refusals: maybe nine hundred dollars today — but the same relax churned to minus four hundred in the re-entry lens, and the three-ninety-one-day test says every relax loses. So I'm not un-gating anything on one angry day.
7. What changes tonight: filter ten gets its own bull knob — behavior-identical until something actually clears — plus the regime tagger gets fixed so tonight's day gets labeled.
8. What's queued: re-price today on real option prints after four-twenty, and this weekend, re-test both filters against my own live refusal log instead of a simulator that can't see it.
9. J — your Monday words were "nothing gated that actually works." Today broke that, and now it's measured instead of suspected. The instrument watching the feed gap runs daily from here.
10. Monday: no PDT relief for anyone, bold-two stays dark until Wednesday. I trade the same rules, with one more honest knob and one less blind spot.

---

## Provenance

| Lane | Verdict | Key artifacts |
|---|---|---|
| L1 name-the-blockers | MINOR_GAPS (adjudication resolved in §4) | FRIDAY-BLOCKERS-2026-08-07.md/.json, commit 5246d7f2 |
| L2 price-the-refusal | SOLID | F10-F7-AB-2026-08-07.md, f10-f7-population-battery-2026-08-07.json, both NOT_CLEARED scorecards, commits 94157aa6 + 1bdc1f12 |
| L3 replay-today | SOLID | FRIDAY-REPLAY-2026-08-07.md/.json, commit 0ff537fb |
| L4 week-context | SOLID | WEEK-FINAL-PREP-2026-08-07.md/.json, regime-selfheal staged pkg, commit 75cb3bf9 |
| L5 close-package | SOLID | CLOSE-PACKAGE-2026-08-07.md, staged diffs, reprice runner, commits 1d393907 + 0a45d396 |

Nothing pushed (market hours). All commits pathspec-scoped via commit_scoped.py.
