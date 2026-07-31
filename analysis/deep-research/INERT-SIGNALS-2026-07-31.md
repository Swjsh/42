# INERT SIGNALS — 2026-07-31 synthesis

> **The looseness knob doesn't exist: arm-level `gate_override` blocked 45 of 3,479 ticks all-history (1.3%) and 0 of 128 on 2026-07-31.** Risky-1's real Friday was 106/128 HOLDs = `NO_SIGNAL_FROM_PRODUCER`, 18/128 = the $0.30 premium floor, **0/128 = its own gate.** Every future hour spent "loosening the arms" is aimed at a mechanism that was already off.

**Written:** 2026-07-31 18:34 ET (verified `setup/scripts/et_clock.py` → `2026-07-31 18:34:44 Friday EDT, market_hours=False`).
**Scope:** three lanes — the ribbon gate (filter 5), the shadow-wiring architecture, the full-send arm. Each ran a correctness verifier and a risk/blast-radius verifier.
**Status of the night: 2 measured NULLs, 1 armed-but-unmeasured experiment. Nothing about the live SPY entry path changed.**

---

## 1. Scoreboard

| Lane | Verdict | Reviewers | Reported as | Hot-path change |
|---|---|---|---|---|
| Filter 5 (ribbon MA-stack) | **NULL** — gate stays | MINOR_GAPS ×2, not refuted | **SHIPPED** (a measurement + a decision) | **ZERO** — `git diff HEAD -- backtest/lib/filters.py` empty ✅ |
| Shadow-signal inventory | **NULL** — arm nothing | MINOR_GAPS ×2, not refuted | **SHIPPED**; the held instrument defect + both disclosure corrections **LANDED 19:0x ET** (§3) | ZERO (no engine file touched) |
| FULL-SEND arm | **ARMED, EVIDENCE RETRACTED** | **MAJOR_GAPS ×2, one REFUTED** | **NOT shipped-as-validated** | Producer + fleet consumer lane, paper only |

---

## 2. Lane 1 — Filter 5 (ribbon MA-stack): measured, null, gate stays

**Verdict: NULL. Filter 5 stays. Net hot-path change is zero and I verified it three ways** (`git diff HEAD` empty; `git status --porcelain backtest/lib/` empty; `filters.py`'s last commit is `459342c8`, 07-28, predating this lane entirely).

### The honest number

The headline "+$738.60 from deleting filter 5" **is 86% position-sequencing.** Decomposed:

| Component | n | P&L |
|---|---|---|
| Trades the deletion **ADDS** (the actual block-set) | 21 | **+$103.60** (+$4.93/tr, WR 52.4%) |
| …same cohort **ex-best** | 20 | **−$437.00** |
| Trades the deletion **PRE-EMPTS** out of the control book | 8 | +$635.00 |
| Full-window total | | +$738.60 |
| **Recent 25 days (the primary gate)** | 3 added | **−$68.00** |

Gates: **2 of 5 pass.** G1 (recent-positive, PRIMARY) fails, G2 fails (1 up / 1 down), G3 fails (drop-best −$122), G4 passes (runner anchor 39/39, $18,330 → $18,488), G5 passes (fires reported: 21 full / 3 recent).

### What survived verification, what didn't

- **Pre-registration is genuinely frozen first** (prereg mtime 17:34 ET, runner 17:58, output 18:03), `"primary": true` is inside the frozen file, and the ship rule pre-commits verbatim to the exact case that occurred — "including the case where deletion looks good on the aggregate but fails the recent window." Cherry-picking is structurally foreclosed.
- **Independently re-derived and confirmed:** all P&L figures, zero duplicate trade keys, zero `BS_FALLBACK` rows (synthetic genuinely excluded, not merely disclosed), entry+1 structurally enforced.
- ✅ **CORRECTION LANDED — cohort-A bar counts were exactly 2× inflated.** The capture monkeypatch patches both `lib.orchestrator` and `lib.engine.score`, and the per-bar parity cross-check runs every bar through both. **"346 bull / 152 bear" was really 173 / 76; "56 / 48 recent" was really 28 / 24** — re-measured, not divided: the corrected re-run reports exactly those figures. Day counts unaffected. Fixed at source by `Blockers5Capture` (dedupe keyed on timestamp, so a third patched module could not re-inflate it either), guarded by `backtest/tests/test_filter5_capture_no_double_count.py`, RED-proofed both ways — the mechanism test fails against restored `list.append` semantics, and the artifact test failed against the pre-correction committed JSON (all 16 sampled rows were exact adjacent duplicates). Corrected in the scorecard JSON, MD and STATUS.md.
- ✅ **CORRECTION LANDED — G1 now reads UNDETERMINED, not FAIL.** OPRA coverage collapses after 2026-07-22 (~22–30 cached contracts/day through 07-22, then **3 / 0 / 0 / 2 / 3 / 0 / 4**, with **three recent-window days — 07-24, 07-27, 07-30 — at ZERO coverage**). Measured from the corrected re-run: ARM_A adds **7** raw entries in the decisive recent window (the verifier's estimate of 6 was one low) and **only 3 are measurable**; all 4 unpriceable ones sit in the newest week. G1 is a strict sign test on that sum — the missing four would need to average only **+$17.00** each to flip it. A window-stratified OPRA-exclusion table now ships in the JSON + MD so the collapse is visible rather than buried under a lump `no_opra: 25`. **The verdict is unchanged either way** — UNDETERMINED is not a PASS, G2/G3 fail on measured data, no arm passes, gate stays. This is a **gap, not a refutation**; an OPRA backfill is the one input that would settle it.
- ✅ **CORRECTION LANDED — "zero trades on 07-31 in any arm" was true only of the walked book.** ARM_A *did* produce a 07-31 09:50 `SPY260731P00742000` entry (level_rejection + confluence @ 742.45); it was dropped for a **missing OPRA contract**, not by a gate — "excluded for missing data" reported as "blocked by gating" (C7 shape). **The conclusion survives on better evidence, now re-derived from the run itself:** under ARM_A the 10:20 bar fires `BULLISH_RECLAIM_RIDE_THE_RIBBON` with `["level_reclaim","confluence"]` at level 738.85 and is refused with blockers `["BLOCK_ELITE_BULL"]`, action `SKIP_ELITE_BULL_LEVEL_RECLAIM` — one of **8** such refusals that day (11 named gate refusals total). `day_forensics_2026_07_31` now separates walked / excluded-for-missing-data / gate-refused **by construction**, so the three can never be collapsed again.

> **Re-run reproduced the finding exactly** — full delta **+$738.60**, recent **−$68.00**, 21 added, verdict **NULL** — confirming these were reporting defects only. The verdict never moved.

### ⭐ The by-product worth more than the null — the single most reusable thing this lane produced

**Filter 5 is largely redundant with the ribbon-flip EXIT.** **76.2% of the unlocked trades exit on `ribbon_flip_back` (n=16) vs 9.9% of the control book (n=19)**; the control book's own dominant exit is `premium_stop` at 48.7%. The entry veto and the exit both read the same lagging ribbon, so the block-set dies within minutes of being let in — it never gets a chance to be right or wrong, it gets round-tripped.

**Any future "loosen the ribbon" that moves only the entry gate is PRE-REFUTED.** It will null the same way this arm did, for this mechanism, regardless of how the entry gate is scoped — that covers ARM_A (outright deletion), ARM_B (level-anchored bypass), and any not-yet-imagined entry-side variant. The only version worth a run is the **PAIRED** one: relax the entry gate **and** suppress `ribbon_flip_back` for the same cohort, in ONE pre-registered change. **That paired arm has never been measured** — it is item 7 on the ship list and the only live door left on this axis. (L243's shape, on the exit side.)

Second by-product: `attribution_block()` in the runner decomposes any gate A/B delta into added-cohort vs pre-empted-cohort, so the artifact that fooled this headline is now structurally impossible to omit.

### Shipped vs queued

- **SHIPPED** — commit `abb1f42d`, 6 files, +8,521 lines, not pushed, pre-commit gate 59/59 green: frozen pre-reg, scorecard JSON+MD, reusable runner `backtest/tools/filter5_ribbon_fate_2026_07_31.py`, STATUS.md signal block, lesson-inbox item. Standing suites re-run green after revert (83 passed / 4 skipped).
- **HELD** — the ARM_B scoped-bypass flag and its 8-test guard were deliberately reverted out of `filters.py` after ARM_B measured byte-identical to ARM_A. Trade accepted: hot-path cleanliness over ARM_B's re-derivability. **ARM_B's cell in the scorecard is a transcribed constant, not reproducible from the committed tree.**
- **CORRECTIONS LANDED** — all three of the above, in a follow-up commit: source fix + RED-proofed guard (`Blockers5Capture`, `test_filter5_capture_no_double_count.py`), corrected scorecard JSON + MD regenerated by a full re-run (which reproduced +$738.60 / −$68.00 / 21 added / NULL exactly), window-stratified OPRA-exclusion table, `day_forensics_2026_07_31`, and a corrected STATUS.md block. **The verdict did not move.**

---

## 3. Lane 2 — Shadow signals: the wiring gap is real, the signals are not worth wiring

**Verdict: NULL. Armed nothing. The 2026-07-15 logged-only quarantine is vindicated by measurement, not by assumption.**

### The honest numbers (corrected by the verifier)

| Signal | n | Total | Per-trade | Per-trade p | **Day-level test** | Honest verdict |
|---|---|---|---|---|---|---|
| `trendline_reclaim` | 27 | **−$1,097** | −$40.64 | 1.9e-08 | **t=−3.401, p=0.0007, 3/3 days negative** | **Significant NEGATIVE — stands unqualified** |
| `wick_reclaim` | 133 | **−$2,556** | −$19.22 | 0.059 | **t=−0.649, p=0.516, 2/3 days neg (one day +$1,737)** | **Negative point estimate, NOT significant** ⬅ downgraded |
| `pullback_hold` | 0 resolvable | — | — | — | — | **UNDERPOWERED, no verdict issued** |

- ✅ **CORRECTION LANDED (2026-07-31 19:0x ET) — `wick_reclaim`'s "BH-SIG NEGATIVE" was n-inflation.** 133 firings are not 133 independent draws: on 07-20 alone, 52 trades ran across only **8 distinct contracts** (the detector fires on 57% of bars, so positions overlap near-continuously). The harness's own docstring promised day-level block aggregation; sums were printed, **no day-level test was ever computed.** It is computed now, in the harness (`day_level_test()`), so a re-run reproduces it — and the label is **"negative point estimate, NOT significant at day level"** on every surface. `trendline_reclaim` keeps its significant-negative unqualified.
- ✅ **CORRECTION LANDED — the validated exit cell was never applied to 90% of trades.** `ExitState.from_entry` needs `trigger_level`, which was missing on **144/160** shadow trades (90.0%, re-derived this session), so it silently fell back to premium mode at **−20%** — which `RIBBON_RIDE`'s own source note calls "the flag-OFF emergency fallback, NOT the validated cell." Proof, re-derived: **87 premium stops, all firing between −20.9% and −19.0%, zero near −50%**; the only 16 `structure_stop` legs are exactly the 16 trades that carried a `trigger_level`. Textbook C14/L248 dead-knob-by-omission.
  **Direction of bias: CONSERVATIVE.** Re-walked at the true −50% cap: wick −$2,556 → **−$6,462**; trendline −$1,097 → **−$1,588** (both reproduced to the cent). Negative in every configuration, so **the null survives and strengthens.** Now first-class fields in the committed JSON (`exit_fallback_correction`, `counterfactual_true_cap`), not prose.

### What this lane did right, and it is the best work of the night

It ran `/fable-too-good` on its own negative before reporting. The naive run said `wick_reclaim` **+$603**; the unbiased-day slice said **−$2,556** — a sign flip. Cause: OPRA cache selection is non-random (on 07-31 only strikes 744–748 were cached against an SPY range of 738.61–748.47, i.e. only the day's upper third could resolve — exactly where a bullish signal wins). The unbiased-day set is computed **in code** from cache + observed range, never hand-listed.

Other verified findings:
- **1 true orphan:** `detect_candlestick_pattern_bullish` (`backtest/lib/filters.py:334`), zero callsites tree-wide including tests. Its bearish twin **is** called at `filters.py:1572`.
- `wick_reclaim` fires on **57.2%** of RTH 5-min bars on its active days (17.9% over the full ledger window — denominator disclosed here, it was not there). That is ambient, not a trigger.
- Payoff ratio is healthy (2.6:1, mean win +$144.74 vs mean loss −$55.35). **The 16.3% hit rate is what kills it**, not the exits.

### Shipped vs held

- **SHIPPED** — commit `bc1263e4`, 9 files: nightly orphan/drift detector `setup/scripts/shadow_signal_audit.py`, the standing inventory, the reusable real-OPRA edge harness (auto-widens when the OPRA backfill lands). Task `Gamma_ShadowSignalAudit` registered and **fired for real** (LastTaskResult=0, State=Ready, NextRun 08/01 15:25 MT = 17:25 ET). Guard 9/9, four mechanics RED-proofed by reverting each fix. Risk suites re-run: 124 passed.
- ✅ **FIXED (was HELD BROKEN) — the new instrument's timestamps were wrong.** Line 422 was `generated_at_et=dt.datetime.now()` — **bare local Mountain time**, rendered with an " ET" suffix. Proof at the time: the autogen block read `2026-07-31T16:10:10 ET` while the task's actual run was 18:09 ET. Now routed through a single `stamp_et()` helper backed by `et_clock.py`; the identical bug in `shadow_signal_edge_2026_07_31.py:338` was fixed in the same pass. **Guarded** by `test_generated_stamp_is_real_ET` (+2 companions, suite 12/12), **RED-proofed** by reverting to `dt.datetime.now()` → `is 7201s from et_clock ET`. Artifacts restamped by firing the REAL task (`LastTaskResult=0`, empty stderr, header now `2026-07-31T19:03:23 ET`), and the mislabeled `## Known broken` line restamped 16:00 → 18:00 ET with the reason inline.
- ✅ **FIXED (was HELD) — the revert is two steps and is now documented.** `git revert bc1263e4` deletes the script but leaves `Gamma_ShadowSignalAudit` registered against a missing absolute path, firing nightly into silent failure. Fail-open (a dead task cannot block trading) but it is the exact C7 shape this lane was built to detect. The **two-step procedure — `Unregister-ScheduledTask Gamma_ShadowSignalAudit -Confirm:$false` FIRST, then `git revert bc1263e4`** — plus current task state and the leftovers list is written into both `SHADOW-SIGNAL-INVENTORY-2026-07-31.md` ("REVERT PROCEDURE") and `automation/overnight/STATUS.md`.
- Minor: "fail-open by construction (always exits 0)" is overstated — the guard is a source-string assertion and `main()` has no try/except. Nothing consumes its exit code, so risk is nil.

---

## 4. Lane 3 — FULL-SEND arm: architecture finding SHIPPED, P&L evidence REFUTED

**Verdict: the architecture finding is solid and is the most valuable thing produced tonight. The A/B evidence used to justify the ship does not survive verification, so this is NOT reported as a validated ship — it is an ARMED, UNMEASURED forward-paper experiment.**

### What survived, exactly as claimed (both verifiers re-derived it independently)

- **A truly ungated arm was not representable.** `gate_override` can only ADD selectivity. All-history blocks: safe-3 **45/3,479 (1.3%)**, risky-1 **45/3,479**, risky-3 **0/3,479**. On 2026-07-31: **0/128.** The grid's entire "looseness" axis was inert.
- **Risky-1's Friday cascade** (exact re-derivation): **106 `NO_SIGNAL_FROM_PRODUCER` (83%), 18 `SKIP_MIN_PREMIUM_FLOOR`, 1 `RISK_CAP`, 3 `NO_LIVE_SIGNAL`, 0 `ARM_GATE`.** Its binding constraint is the $0.30 floor and an upstream producer that emits nothing — **not any gate anyone measured tonight.**
- **Briefing correction:** there were **3** fleet entries on 07-31, not 1 — risky-3 at 12:19 and 13:25, safe-3 at 12:31, all via the normal `ribbon_ride` lane rescued by scoring-peak, none via the probe lane.
- **The safety half is proven by execution, not asserted.** A real full-send plan swept through the real `finalize()`: premium 0.29 → `SKIP_MIN_PREMIUM_FLOOR`; 0.31/1.99 → ALLOW; ≥2.01 → `RISK_CAP` (binds at exactly 50% of equity); equity 500 → `RISK_CAP`; kill-switch → `KILL_SWITCH`; open position → `NOT_FLAT`; day_trades=3 → `PDT`. Fleet suite **310 pass**, full-send guards **26 pass**, downstream consumers **57 pass**. Runner cohort untouched — no exit or params file in the diff.
- **Paper only.** risky-1 = `PA3W17FD8G19`, an Alpaca paper account (verified against `accounts.json`). No live money anywhere in this lane.

### What was REFUTED

1. **The min-size P&L is a biased ratio estimator, and both headlines invert.** `scale_factor = 5 / mean_qty` (I verified 0.5688 = 5/8.79 in the committed JSON) applied to a SUM, over qty spanning 3–22. Correct is `5 · Σ(pnl_i/qty_i)`:
   - full population: reported **+$1,951 → actual −$1,010**
   - recent window: reported **+$63 → actual −$734**

   The JSON's `_disclosure` claims the scaling "is exact." That is an affirmatively false statement of method. **The shipped arm hard-clamps every entry to min size, so this column IS the forward expectation.** `accounts.json` justifies overriding a failed pre-registered check partly because "the profile is P&L-POSITIVE not merely bounded" — **that leg of the rationale is gone.**

2. **The ATM strike override was NOT reverted on the shipped path.** I verified this directly: `_full_send_plan` (`fleet_executor.py:849`) prices `PROBE_STRIKE_TIERS`, whose first two tiers are `StrikeTier(…, 0, "ATM")` — offset 0 at $2K equity. Only `_tiers_for_arm` was reverted, and **the full-send lane never calls it.** At spot 744.10 the arm's own table gives strike **746** (OTM-2); the shipped full-send plan prices **744** (ATM). **Every trade this ship adds is ATM.**

3. **The negative guard pinning that revert is VACUOUS.** `test_full_send_does_NOT_override_the_arms_strike_tier` uses a `bull_score=11` fixture, which the pre-existing scoring-peak lane already rescues — so the full-send lane never fires in it. Instrumented proof: score 11 → `ribbon_ride C (ELITE)`, strike 746; score 7 → `FULL_SEND cohort=elite_bull_level_reclaim`, strike 744. **The guard compares two normal-lane plans and stays green while the override is live.** Second vacuous guard in this lane; the first was self-caught, this one was not.

4. **OP-16 sim-accuracy gate breach.** The headline cell (+$3,430 / 387 sessions) was measured at `strike_offset=2`. Production trades `strike_offset=0`. The harness's own comment labels the offset-0 cell "the LIVE arm's strike" — **and that cell measured −$5,110 raw / −$4,036 min-size**, tabled as "(rejected)." In fairness the −$5,110 cell applied ATM to all 327 trades whereas live only ~17 marginal ticks per 28 days take the new lane, so it is *not* the live expectation. **The honest statement: the incremental trades this ship adds have NO valid measurement at their actual strike, and J was told the opposite.**

5. **Pre-registered check F4 (≥2.0× uplift) FAILED recent at 1.902× and was shipped anyway.** Self-disclosed, not massaged — but a pre-registration you override on judgment is not a pre-registration.

6. **Two live surfaces describe the same behavior in opposite terms.** `accounts.json` `full_send_doc` correctly says entries price `PROBE_STRIKE_TIERS` (ATM-class); the scorecard JSON and commit message say ATM was reverted.

### DECISION (mine, for REVOKE)

**The arm stays armed as an explicitly UNMEASURED forward-paper experiment; the "validated / P&L-positive" claim is retracted.** Rationale, stated plainly: paper account, min-size clamp, all six risk guards proven binding by execution, worst day −$470 against a −$1,000 kill switch, one-line revert documented — and ATM is precisely the strike that clears the $0.30 floor that killed risky-1 all day, which is what J asked for ("get in shit and see if it works"). The measurement that matters for this arm is its forward paper ledger, not another SIM cell.
**But it is labeled UNMEASURED, not validated, and if the corrections in §7 items 1–2 do not land by Sunday night, de-arm it** (`risky-1.gate_override` → `{"min_triggers": 2, "require_confluence_or_sequence": true}`; belt-and-suspenders `build_shared_signal.FULL_SEND_LIVE = False`).

Note found while stressing `finalize()`: at $2K equity the 50% per-trade cap refuses any full-send entry above $2.00 premium, and ATM 0DTE SPY midday frequently prices above that — **so the arm will fire even less often than claimed.**

---

## 5. THE ARCHITECTURE ANSWER — why none of the arms got in

You called three good longs on Friday and the fleet took one of them. Here is the honest order of blame, counted in cells. **The ribbon MA-stack (filter 5) cost the most — 5 of 15 live cells**, all five arms at once on your 10:15 low, because the ribbon flipped BULL→MIXED at 10:16 and never restacked through the entire +4.82 bounce; it is a lagging indicator vetoing a leading entry. **Next, plain no-trigger — another 5 of 15**, on your 11:30 long: the level was tracked at that exact tick, but the reclaim detector demands a *closed* bar back above the line, and that bar landed at 11:36, by which time the ribbon had re-flipped and re-blocked. **Third, `block_elite_bull` — 2 of 15**, and it is the ugliest one, because on your 12:15 long the engine had a perfect read: bull score 11 of 11, blockers empty, setup and reclaim level correct — and a cohort gate killed both core arms anyway. **Fourth, the $0.30 minimum-premium floor — 2 of 15**, refusing safe-3 and risky-1 on a contract priced at $0.15. **One arm got in** (risky-3 at 12:19) and it won. Underneath all of that sits the finding I did not expect: **the arm-level "looseness" knob everyone reaches for blocked zero of 128 ticks on Friday and 1.3% of ticks in all history** — so the reason risky-1 logged 128 straight HOLDs is not that its gates are tight; it is that for 106 of those 128 ticks *the producer upstream sent it nothing at all*, and on most of the rest the premium floor refused the contract. **Loosening arms cannot make arms trade. The two levers that can are the ribbon's grip on the entry cascade — which must move together with the ribbon-based exit, since 76% of ribbon-blocked trades die on that exit within minutes — and the strike/premium-floor pairing that decides whether a legitimate signal ever becomes an order.**

---

## 6. Graveyard additions

**Do NOT retest these:**

1. **Deleting filter 5 as a standalone entry-gate change** (both directions). Full-window +$738.60 is 86% pre-emption; the block-set itself is +$4.93/tr and **−$437 ex-best**; recent window −$68. Measured, pre-registered, null.
2. **`trendline_reclaim` as a standalone entry trigger.** n=27, −$40.64/tr, **day-level p=0.0007, 3/3 days negative**, and worse (−$1,588) under the correct −50% cap.
3. **`wick_reclaim` as a standalone entry trigger.** −$19.22/tr, fires on 57.2% of bars — ambient, not a trigger. Worse (−$6,462) under the correct −50% cap. **Caveat on the strength of this one:** it is **not** significant at day level (stat −0.649, p=0.516, 2/3 days negative). Graveyarded as *not shown to be good*, not *proven bad* — do not quote it as a significant negative.
4. **Arm-level `gate_override` looseness as a lever for "make the arms trade."** 1.3% of ticks all-history, 0% on 07-31. The axis is inert.
5. **ATM applied to the whole full-send book.** −$5,110 raw / −$4,036 min-size over 387 sessions. The all-trades-ATM cell is dead; only the marginal-lane version is open.

**Explicitly NOT graveyarded** (do not let these get swept in):
- **`pullback_hold`** — n=0 resolvable, UNDERPOWERED, **no verdict was issued.** It is untested, not dead.
- **Shadow signals as SCORE CONTRIBUTORS / tiebreakers / vetoes.** Only the standalone-trigger form was tested. Gate interactions are multiplicative (C15); `wick_reclaim` at 57% of bars is useless as a trigger and could still be a legitimate score input.
- **Filter 5 relaxed *together with* the ribbon-flip exit.** The paired change has never been measured.

---

## 7. Ordered ship list for the weekend

Each item names its gate. Nothing here needs J to start.

| # | Item | Gate | Deadline |
|---|---|---|---|
| 1 | **Resolve the full-send strike mismatch.** Either point `_full_send_plan` at `_tiers_for_arm` (making the measured +$3,430 cell honest) or keep ATM and correct every surface to say ATM+UNMEASURED. | Rewrite `test_full_send_does_NOT_override_the_arms_strike_tier` at `bull_score=7` and RED-proof it; `accounts.json` + scorecard JSON + MD all state the same strike. | **Before Monday 09:30 ET** |
| 2 | **Recompute min-size P&L per-trade** (`5·Σ pnl_i/qty_i`) in `backtest/full_send_arm_ab.py`; correct −$1,010 / −$734 into the JSON, MD and `accounts.json`; delete the false "this is exact" disclosure and the "P&L-POSITIVE" clause from the F4-override rationale. | Recomputed figures reproduce −$1,010 / −$734 within rounding. | **Before Monday 09:30 ET** |
| 3 | ✅ **DONE** — **Fixed the TZ bug** at `setup/scripts/shadow_signal_audit.py` (+ the same bug at `shadow_signal_edge_2026_07_31.py:338`): single `stamp_et()` helper on `et_clock`. Inventory + machine state + the STATUS.md line **restamped**. | ✅ `test_generated_stamp_is_real_ET` +2 companions, suite 12/12; RED-proofed by reverting → `is 7201s from et_clock ET`. | ~~Tonight~~ **landed 19:03 ET** |
| 4 | ~~**Correct lane-1 reporting:** dedupe cohort-A bar counts, relabel G1 **FAIL → UNDETERMINED**, add a window-stratified OPRA-exclusion table.~~ **✅ DONE** — deduped at source + RED-proofed guard; counts re-measured at 173/76 full and 28/24 recent; G1 → UNDETERMINED with the flip-threshold arithmetic; stratified exclusion table + `day_forensics_2026_07_31` shipped; 07-31 misattribution corrected. Full re-run reproduced the verdict exactly. | Recomputed counts + exclusion table in the committed JSON. | ✅ Landed |
| 5 | ✅ **DONE** — **lane-2 reporting corrected:** the 90% / −20%-fallback disclosure and the −$6,462 / −$1,588 counterfactual are now first-class fields in the committed JSON and stated inline in the inventory doc; `wick_reclaim` downgraded to "not significant at day level" everywhere; `trendline_reclaim`'s significant-negative kept; `pullback_hold` explicitly **no verdict**; standalone-trigger-only scope stated. | ✅ Counterfactual **re-run and reproduced** (−$6,462.16 / −$1,587.83); baseline block diffed byte-identical against `git show bc1263e4:…json`. | ~~Tonight~~ **landed 18:57 ET** |
| 6 | ✅ **DONE** — **`bc1263e4` revert procedure written**, `Unregister-ScheduledTask Gamma_ShadowSignalAudit -Confirm:$false` FIRST, then `git revert`. | ✅ In the inventory doc ("REVERT PROCEDURE") **and** STATUS.md, with task state quoted from `Get-ScheduledTask`/`Get-ScheduledTaskInfo` (State=Ready, LastTaskResult=0, NextRun 08-01 17:25 ET). | ~~Tonight~~ **landed 19:05 ET** |
| 7 | **PAIRED A/B: relax filter 5 AND suppress `ribbon_flip_back` for level-anchored entries.** This is the only version of "loosen the ribbon" that can work. | Pre-registered; **fire count reported alongside P&L (L243)**; recent-window-positive as primary; runner-cohort no-regression. | Weekend |
| 8 | **Delete-or-wire `detect_candlestick_pattern_bullish`** (`filters.py:334`) — hand the call to the directional-gate lane; it is the natural building block for a bull candlestick trigger. | A callsite + guard, or deletion + `git grep` proof of zero references. | Weekend |
| 9 | **Fix the dead knob `fleet_executor._effective_passed`** — risky-3's `hard_skip_verdicts` override has silently done nothing on the live path since 2026-07-23 (only reachable from `backtest/replay_fleet_arms.py`). | Vary-and-assert test proving the override changes live-path behavior. | Weekend |
| 10 | **Re-run `backtest/tools/shadow_signal_edge_2026_07_31.py`** once the in-flight OPRA backfill lands (it auto-widens its unbiased-day set). | `pullback_hold` reaches n≥15 resolvable → first real verdict. | On backfill |
| 11 | **Re-run `setup/scripts/full_send_vs_gated.py --since`** and decide REVOKE-or-keep on forward broker fills, not SIM. | n ≥ 10 forward sessions. | ~2 weeks |

---

## 8. NEEDS J — explicit, nothing hidden

**No live-money arming is requested. No secret rotation is needed. Every account touched tonight is paper.** Three items are genuinely yours:

1. **REVOKE call on the full-send arm.** I left risky-1 armed at ATM as an unmeasured paper experiment against your "just get in shit and see if it works." That is my call to make and yours to kill: one line in `accounts.json`, documented in §4. If you want it dark until it is measured at its real strike, say so and it goes dark in one edit.
2. **If the $0.30 `min_entry_premium` floor fix ends up *loosening the floor* rather than *moving the strike*, that is a risk-rule change and it is yours** — not mine, and not the audit lane's. Moving the strike so contracts clear the floor on their own merits is engineering; lowering the floor is a rules edit.
3. **26 commits sit unpushed on `main` against a PUBLIC repo.** I did not push (instructed not to, and this session did not run the secrets audit). Your call on when — and it should follow a `github-audit` GREEN.

---

## 9. Morning brief — spoken, 6 lines

> Friday gave us three fleet entries and one clean winner on risky-3. I'm not calling that a good day — n is one.
> You asked why none of the arms got in on your ten-fifteen long: the ribbon stack blocked five of five arms, and it never restacked through the whole bounce.
> So I measured that ribbon gate over three hundred and ninety days of real fills. Deleting it earns nothing — the headline gain was eighty-six percent position sequencing, not the gate. It stays.
> I also measured the three signals the engine sees but can't act on. Both testable ones lose money; the third is underpowered and I'm not calling it either way. I armed nothing.
> The real finding is smaller and worse: the arm-looseness knob you'd reach for blocked one-point-three percent of ticks in all history, and zero on Friday. Loosening arms cannot make arms trade — the producer sent risky-one nothing on a hundred and six of a hundred and twenty-eight ticks.
> The full-send arm is armed on risky-one, but its evidence was measured at the wrong strike, so I'm calling it unmeasured, not validated — one line de-arms it, and I'll have it corrected before Monday's open.

---

## Appendix — commits (all local, none pushed; `main` ahead 26)

| Commit | Lane | Files | Hot path |
|---|---|---|---|
| `abb1f42d` | Filter 5 | 6 (+8,521) | none — `filters.py` byte-identical to HEAD |
| `bc1263e4` | Shadow inventory | 9 (+1,722/−1) | none — instrument + docs only |
| `e28d210c` | Full-send arm | 11 (+2,238/−14) | producer `build_shared_signal.py` + consumer `fleet_executor.py`, paper only |
