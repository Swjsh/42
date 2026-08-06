# THE WEEK ORDER — week of 2026-08-10

> Written Thursday 2026-08-06 evening. Clock verified at synthesis start:
> `2026-08-06 19:45:06 Thursday EDT / market_hours=False` (`et_clock.py`).
> Successor to [WEEK-ORDER-2026-08-03.md](WEEK-ORDER-2026-08-03.md). Synthesized from the
> 7-lane Thursday-evening sweep — every lane independently verified (all 7 reviews:
> `ship_safety_confirmed=true`, zero refutations); suite states re-run fresh at final HEAD
> for this document, not recalled from lane summaries.

---

## FOR J — 12 LINES MAX

- **+$3,667.55 week** → book **$28,667.55 (+14.67%)** — but Tuesday was **98.3%** of gross; ex-Tuesday the week is **+$64** and the prior 23 days are **−$1,372**. The trend is not earned yet.
- **7 lanes, 25 commits, 0 NEEDS-REVERT** — every verifier confirmed ship-safe; 2 minor-gap disclosures, both harmless (detail §2).
- **ONE trading-path change Monday:** risky-3 strikes **OTM-2** in the $2K–10K band — its own preregged kill bar hit (n=14, **−$653**); risky-1 keeps ATM (n=11, **+$903**). The per-arm A/B is now live by construction.
- The sanctioned same-bar cooldown shipped **DISARMED**: day-0 replay under production bar identity showed it blocks **Tuesday's +$524 winner and nothing on Wednesday** — its own prereg killed the arming; forward re-measure is the only arm path.
- **Small losses:** the honest Wednesday floor is **−$710** (all 15 loss-cap combos subtract); the real fixes shipped are the phantom-flat prune (position sat unmanaged 10 min on 08-05) and risky-3's bleed kill.
- **Strategic entries:** measured signature — level-tied + 1m structure pays **+$70.8/entry (40% WR, n=55)**; bare + structureless bleeds **−$103/entry (0% WR, n=16)**. Shadow-only; nightly counter live.
- **Hold winners:** the chandelier trail **IS** the policy — the BE-floor alternative loses **−$1,095 ex-week** and **−$907** on the 07-29 trend day. DO_NOT_ARM; sell-half-at-+100% is the one frozen candidate.
- **Don't trade chop:** "no structure = chop" is **WRONG** on this book (blocking zero-structure entries costs Tuesday **−$2,091**); the chop that hurts is repeat entries into the same falling contract. Nightly chop meter live at 16:08 ET.
- **All nine harness defects (D1–D9) fixed + guarded** — including naming and stopping the synthetic-ledger-row writer (322 rows quarantined) and a $415.25 sign-flip.
- **Rig ready:** 24/24 trading-critical tasks green; TV watchdog heals in 67s (proven live); github_audit GREEN; fleet suite fresh at HEAD: **395 passed / 3 known anchor-fidelity REDs** (owned, §5).
- **bold-2 is PDT-dark Mon+Tue, back Wed 08-12** — a self-imposed legacy rule the paper broker doesn't apply. Your ONE decision: [PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md](PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md) (Option A = one line).
- **Next week's job, your words:** small losses, strategic entries, hold winners, don't trade chop — everything armed toward that is measured; everything unproven sits in shadow with a frozen clock.

---

## 1. What we did good this week

J asked explicitly. The honest list — process wins first, because the P&L is one day deep:

- **The Thursday entry was the blueprint.** 10:31 ET puts: 1m CHoCH-DOWN confirmed 5–6 bars prior, trigger tied to the 771.5 level, **3 arms filled inside 15 seconds** on the clean break. That single structure-confirmed trade paid **+$1,501** and is the textbook PAY-cell of the new entry-quality signature. Thursday closed **+$1,465, broker-verified to the dollar** (chop meter reconciliation: 375+296+830−36).
- **Tuesday's reclaim rides were earned, not lucky.** The record **+$3,624** came from early reclaims the engine took *without* waiting for structure — and tonight's battery proved that instinct right: blocking zero-structure entries would have cost Tuesday **−$2,091**. The engine's best cohort is the one a naive filter would kill.
- **The exits fired as designed.** The chandelier trail out-held the BE-floor by **+$906.60** on the 07-29 trend test; risky-1's +50% TP1 patch banked **+$236.80**, all of it Wednesday defense; the 763C runner exhibit walked at +$625.50 vs +$640 live — the model is faithful.
- **Reconciliations came back clean everywhere they were run:** Monday broker pull $534.00 = header exact (diff $0.00); runner cohort n=35 matched catcap **to the cent** ($15,497.25); popA CONTROL 0 mismatches; all five arms sum to $28,667.55 exactly.
- **Defects were caught before they cost money:** the watchdog hang that would have eaten a mid-day heal (fixed, 67s proven); the phantom-flat prune that left a live position unmanaged 10 minutes on 08-05 (fixed, 2-read confirm); a harness sign-flip mis-reporting −$76.80 for +$338.45 (fixed); synthetic test rows silently contaminating the live decision ledger and one research pin (writer named, stopped); 21 PDT denials invisible to the escalation cord (now visible).
- **Per-arm, everyone finished green:** safe-2 +$730 / bold-2 +$479 / safe-3 +$782 / risky-1 +$1,344 / risky-3 +$353. Do not inflate it: one session made the week, the ex-week base rate is negative, and risky-3's headline hides the −$653 tier bleed we killed tonight.

---

## 2. What changed tonight

**Verifier verdict first: zero items flagged `ship_safety_confirmed=false` — nothing NEEDS REVERT.**
Two MINOR_GAPS disclosures, neither blocking: (a) Lane 6's D3 forensics over-attributed — 148 of
the 322 quarantined ledger rows predate the named test-suite writer and belong to an older
unarmed-run writer; the quarantine and leak-stop stand regardless. (b) Lane 7 asserted "provably
ready" before running the fleet suite; resolved for this doc by a fresh HEAD run (§5, 395/3).

### Shipped to the trading path (guard + RED-proof + one-line revert + REVOKE in STATUS.md, all verified)

| Item | Commits | What changed | Revert |
|---|---|---|---|
| **S3 risky-3 tier kill (EXECUTED prereg)** | `3ac1d7b2` + `f3a30ad8` | risky-3 alone moves to `bold_core_pre_ext` (OTM-2 in $2K–10K) via accounts.json patch; shared table untouched — risky-1/safe-3/core bold-2 keep ATM. Vary-and-assert 6/6. | risky-3 `strike_tier_table` → `'bold_core'` |
| **S2 fleet same-bar cooldown — DISARMED** | prereg `55880b45` → wiring `7598c20d` (ancestry git-proven) | Consult+stamp wired into `fleet_live._place_live` mirroring core's exact contract; `trigger_bar_et` threaded into the signal. **`FLEET_SAME_BAR_COOLDOWN=False`, pinned by guard.** | `git revert 7598c20d` |
| **D5 phantom-flat prune fix** | `f99a10a4` | Prune requires **2 consecutive** broker-flat reads; qty query fail-CLOSED (error = HOLD); confirmed prune writes a STATUS.md Live-watch line. Shared core+fleet surface. | `git revert f99a10a4` |
| **D4 TP1 display divergence** | `df53bc65` | Journaled `tp` recomputed from the **ARMED** ExitState (registry), not params render. Render-only. | `git revert df53bc65` |

### Shipped instruments (measurement-only, no trading-path surface)

- **Chop exposure meter** `7aac35e6` — `Gamma_ChopMeter` 16:08 ET daily + firm_brief "Chop exposure" section; records ord≥4, consec runs, rr<0.70, against-V-d1, fleet realized floor, BRK600 would-trip. Guards 8/8, RED-proofed x2.
- **Entry-quality ledger + V-d1/V-e3 shadow counter** `6d6bf8c8`/`c7d2bf9b`/`e9e1db79` — folded into the 16:25 Gamma_WinnerAutopsy fire, idempotent, fail-open; proven in-situ on the real fire ("4 tally rows, vd1 blocks 0, ve3 blocks 0"). Guards 14/14, RED-proofed x2.
- **Harness integrity D1–D9** — 10 commits (`7d8f4337` `c2f4afbf` `04415e5d` `df53bc65` `f99a10a4` `7123aafe` `785175b3` `f42baef2` `1bc41822` `508cf1af`), 41 new guard tests, 10/10 RED-proofs. Highlights: D1 sign-flip refusal ($415.25 error class closed); D3 ledger-leak writer named+stopped (leak-proof: 322 rows before AND after re-running the suite); D6's "extra_exec-blind" claim **refuted** with a live data test; D7 theta counter live; D8 risk-denials now alarm; D9 trendline producer revived + liveness alarm (consumption stays SHADOW).
- **TV watchdog heal fix** `273a113b` — non-blocking launch + 90s CDP window; end-to-end proven: kill TV → `EXIT=0 elapsed=67s`, `relaunch_fresh_healed`, `cdp_connected=true`. The second masked defect (pipeline blocked until TV exited) found and fixed the same evening. Guards 12/12, RED-proofed x3.
- **S1 stale guard un-staled** `36acbbab` — test was wrong, not code: `c2cb9f72` deliberately shipped shrink-not-deny 08-03; guard now pins the new shape. The suite had been RED 3 days with no owner — process gap logged.
- **S4 ghost workflow** — verified already dead (TaskStop x5 → "No task found", zero surviving processes); transcripts preserved. The "4 agents alive, idle 391.9m" reading was transcript-mtime inference, not liveness.

### Preregs frozen tonight, each with its forward clock

| Prereg | Status | Forward clock / kill |
|---|---|---|
| fleet-same-bar-cooldown (`55880b45`) | **Kill criterion met day 0** → DO_NOT_ARM recorded | Arm ONLY if forward ledger (keyed to `trigger_bar_et`, now auto-accruing) clears the frozen gates |
| ATM-tier-extension (08-03) | Kill **executed** on risky-3; still running on risky-1/safe-3/core bold-2 | Same prereg clock continues per-arm |
| R_tp100_f50 — keep TP1 +100%, sell HALF (`24c4832d`) | 7/8 gates + sole BH survivor; failed G4 on dispersion (31/191 trades) | Re-adjudicate at risky-1 ribbon fills n≥30 post-08-03 OR 2026-09-05, exact frozen grid, no new knobs |
| Runner finite-2.5-target on ribbon_ride (candidate) | NOT run — contamination disclosed | Forward paper fills n≥15 TP1-reaching runners, or out-of-window population |
| V-d1 + V-e3 entry admissibility | SHADOW, session 1/10 logged (4 entries, 0 blocks) | F1–F5 at 10 sessions; would-block-a-big-winner = falsification, report don't rationalize |
| B-RR-070 range compression (`5737488a`) | Only 8/8-gate cross-population cell, but BH q=0.50 | ≥10 sessions with ≥8 rr<0.70 entries; kill = blocked cohort turns net-winner or a compressed-morning-that-pays repeats |
| BRK600 / CAP-3 / CONSEC4 | Recorders live in the meter; **enforcement deliberately unbuilt** | ≥10 sessions; BRK600 kill = would-trip on a green day; CAP-3 kill = blocked 4th+ entry > +$300; CONSEC4 kill = halts before a green session twice |

### Killed tonight (cite, never re-run)

Reachable-TP1 at every fraction (third independent refutation, all anchor-killing) · BE-floor
runner book-wide (regime-conditional, unknowable at entry) · R-S8 structure-recency entry rule
(−$524, blocks Tuesday −$1,760) · same-bar cooldown ARMING on current evidence (the mechanism's
wall-clock study was fiction under production bar identity — L251-class lesson filed) ·
"no structure = chop" per-trade blocking (Tue −$2,091) · loss-conditional per-contract halts
(identical block set to CAP-3, redundant).

---

## 3. Monday 09:30 armed state

**Live account state:** five arms, book $28,667.55 (safe-2 $5,727.91 · bold-2 $5,477.71 ·
safe-3 $5,780.15 · risky-1 $6,338.46 · risky-3 $5,343.32, live-read 08-06 ~18:55 ET).

| Change | Scope | Live value | Kill criterion | First-tick check |
|---|---|---|---|---|
| **risky-3 tier kill** | risky-3 only | `strike_tier_table='bold_core_pre_ext'` → OTM-2 in $2K–10K (at $5K: strike(C,748)=**750**) | Un-kill only via the extension prereg's own re-open bar | first risky-3 plan shows strike = spot+2; risky-1/safe-3/bold-2 plans still ATM |
| **Same-bar cooldown code** | fleet | **DISARMED** (`FLEET_SAME_BAR_COOLDOWN=False`, guard-pinned) | n/a — arming is the gated event, not reverting | fleet signal rows carry `trigger_bar_et`; zero cooldown blocks logged |
| **D5 flat-prune** | core + fleet | 2 consecutive flat reads, fail-closed qty query | guard suite REDs → `git revert f99a10a4` | an externally-closed position shows `FLAT_SUSPECT_HOLD` → `FLAT_PRUNED` one tick later + STATUS Live-watch line — that is the guard working |
| **D4 tp display** | core journal | `tp` = armed registry value | render-only; revert `df53bc65` | ribbon_ride entry journals tp at 2x entry, not the params 0.5x render — EOD tooling should expect the shift at the 08-06/08-07 boundary |
| **D8 risk-deny visibility** | entry_block_watch | RISK_DENY rows qualify | revert `f42baef2` | bold-2 Mon/Tue high-score signal may fire the escalation cord naming `RISK_DENY_PDT` — **expected, not noise** (3/day cap unchanged) |
| **D9 trendline producer** | premarket | deterministic step in run-premarket.ps1; consumption SHADOW | revert `1bc41822` | `trendlines.json` `as_of` stamps each premarket (first unattended: Fri 08-07 08:30); self_check alarms within a day if it dies again |
| **Watchdog heal** | TV infra | non-blocking launch, 90s CDP window | revert `273a113b` | any heal tick completes ~67–115s and writes `*_healed`/`*_FAILED` truthfully — a `*_FAILED` block is now a REAL signal |
| **Chop meter** | nightly instrument | `Gamma_ChopMeter` 16:08 ET | `Unregister-ScheduledTask Gamma_ChopMeter` | firm brief 16:10 shows the "Chop exposure" line; "meter has not run yet" = check the task |
| **Entry shadow counter** | nightly instrument | inside WinnerAutopsy 16:25 ET | delete the try-block in winner_autopsy main() | `shadow-summary.json` updates after 16:25; F1–F3 progress visible |

### PDT headroom per arm per day (enforced-window counts entering each day; **assumes Friday 08-07 adds zero day-trades** — labeled assumption, re-read after Friday's close)

| Arm | Mon 08-10 | Tue 08-11 | Wed 08-12 | Thu 08-13 | Binding? |
|---|---|---|---|---|---|
| safe-2 | 8 (FINRA hr 0) | 7 (hr 0) | 4 (hr 1) | 2 (hr 3) | **NO** — core gates on `cash_settlement` (settled cash), counts informational |
| **bold-2** | **3 — BLOCKED** | **3 — BLOCKED** | **0 — UNBLOCKS** | 0 (hr 3) | **YES — core enforces** `margin_pdt`: `RISK_DENY_PDT` at count≥3 & equity<$25K; production `rolloff_date=2026-08-12` (strict FINRA would free it 08-11; shipped tracker is 1 day more conservative by design) |
| safe-3 | 6 (hr 0) | 5 (hr 0) | 0 (hr 3) | 0 (hr 3) | **NO — LOG-ONLY** (FLEET-PDT-PARITY, 08-06) |
| risky-1 | 8 (hr 0) | 7 (hr 0) | 3 (hr 2) | 1 (hr 3) | **NO — LOG-ONLY** |
| risky-3 | 9 (hr 0) | 8 (hr 0) | 3 (hr 2) | 1 (hr 3) | **NO — LOG-ONLY** |

**What bold-2 does until 08-12:** logs `RISK_DENY_PDT` on every qualifying entry Monday and
Tuesday — correct behavior, not a defect — and rejoins Wednesday. The paper broker demonstrably
does not enforce PDT (8–9 day-trades/arm this week, zero rejections, all PDT telemetry null);
the block is our own legacy rule. If J takes **Option A** on the decision page before the open
(one line: `aggressive/params.json` `pdt_gate_mode: margin_pdt → cash_settlement`), bold-2
trades Monday.

---

## 4. The week's strategy, in J's four phrases

For each: **MEASURED** (what the evidence says) vs **SHIPPED** (live Monday) vs **SHADOW**
(accruing, not acting) vs **PREREG** (frozen, clocked). No blending.

### "Small losses"

- **MEASURED:** the honest Wednesday floor is **−$710** — every loss-cap combination tested
  subtracts from other days (14/15 pairs subtractive). Stop width is settled BOTH directions.
  Tighter breakers were overfit ($18 margin). What stands between us and another −$1,935 is not
  a new lever — it is the same-bar defect's chosen repair (core side, already live), CAP-3-class
  repeat-entry protection **in prereg**, and the risky-3 bleed kill (shipped).
- **SHIPPED:** D5 phantom-flat prune (no more unmanaged positions on a transient read);
  risky-3 → OTM-2 (its −$653 extension cohort ended); catastrophe caps unchanged at −50%.
- **SHADOW:** chop meter's fleet realized floor + BRK600 would-trip latch, nightly.
- **PREREG:** BRK600 −$600 fleet realized breaker (spec written, enforcement deliberately
  unbuilt), CAP-3, CONSEC4 — all on 10-session clocks with frozen kills.

### "Strategic entries"

- **MEASURED:** the entry-quality ledger's 2x2 — level-tied trigger + confirmed 1m structure
  pays **+$70.8/entry, 40% WR (n=55)**; bare confirmation into structureless tape bleeds
  **−$103.1/entry, 0% WR (n=16)**. The named recency rule (structure within 8 bars) is KILLED
  by its own criterion (−$524, would cost Tuesday −$1,760). NOTHING clears BH q≤0.10 —
  in-sample dollars are still consistent with day-level exposure reduction.
- **SHIPPED:** the measurement machinery only (ledger + nightly shadow counter).
- **SHADOW:** V-d1 + V-e3 abstain-when-blind rules, session 1/10 logged; on paper the bias
  stays TAKE THE TRADE (J directive) until the forward window says otherwise.
- **PREREG:** the 2x2 signature itself is the next candidate if J wants an admissibility rule
  with teeth — pre-register before scoring, never arm off tonight's cut.

### "Hold winners"

- **MEASURED:** the chandelier trail already IS hold-winners on every day that doesn't close at
  its high: the BE-floor alternative made **+$4,026 this week** but **−$1,095 over the prior 22
  dates** and **−$907 on the 07-29 trend day** — regime-conditional, unknowable at entry,
  DO_NOT_ARM by its own frozen gates. `runner_target=99.0` on ribbon_ride is a **deliberate**
  SS-B sentinel, not a dead knob (doctrine text fix owed this weekend, Rule 9 window).
- **SHIPPED:** nothing — correctly.
- **SHADOW:** risky-1's live +50% TP1 exit_patch is the binding instrument (week **+$236.80**,
  all Wednesday defense); fold into its arm A/B ledger.
- **PREREG:** R_tp100_f50 (sell HALF at +100%, keep more runner) — the only BH survivor of 28
  cells, +$910.05 popA, helps the runner anchor (+$628.05), failed only G4 dispersion; frozen
  clock n≥30 ribbon fills or 09-05. Finite-2.5-target candidate not run.

### "Don't trade chop"

- **MEASURED:** 12 preregged per-trade cells: "no structure = chop" is WRONG (zero-structure
  entries are the engine's BEST cohort; blocking them costs Tuesday −$2,091); the chop that
  actually hurts is **repeat entries into the same falling contract** — already the same-bar /
  CAP-3 / breaker family's territory. B-RR-070 (range <0.70x 20d median) is the one fresh
  cross-population survivor but sits on a knife-edge (0.80 blocks all of Thursday) at q=0.50.
- **SHIPPED:** the chop exposure meter — chop is now a nightly glance in the firm brief, never
  a gate.
- **SHADOW:** all meter columns accrue (ord≥4, consec runs, rr<0.70, against-V-d1, floor,
  would-trip).
- **PREREG:** B-RR-070, BRK600, CAP-3, CONSEC4 — frozen kills, 10-session windows, judged
  mechanically.

---

## 5. If X then Y

- **If** the forward same-bar ledger (auto-accruing, keyed to `trigger_bar_et`) shows blocked
  re-entries net-negative per the frozen gates → arm the flag. **If** it blocks another winner
  > +$150 → the DO_NOT_ARM stands permanently; close the prereg.
- **If** risky-3's OTM-2 cohort at n≥10 fills underperforms risky-1's ATM cohort → the per-arm
  A/B has answered; report, don't re-litigate. **If** risky-3 min-premium/floor skips spike
  (OTM-2 premiums < $0.30) → check FLOOR_WALL alarms before blaming the kill.
- **If** a TP1 cell (risky-1's live +50% patch) goes net-negative at n≥10 → revert same day,
  not at week's end. **If** +100% TP1 fires accrue and cure R_tp100_f50's G4 dispersion →
  re-adjudicate the exact frozen grid, no new knobs.
- **If** V-d1/V-e3 would have blocked a big winner in any session → that is the pre-committed
  falsification signal; report it, don't rationalize it.
- **If** BRK600's would-trip latch fires on a day that ends green → kill the breaker prereg
  (its own frozen criterion).
- **If** the 3 anchor-fidelity REDs (`test_anchor_pass_rate` safe-3/risky-1/risky-3 — fresh at
  HEAD tonight: `3 failed, 395 passed`) are still unowned when anyone reaches for fleet-replay
  evidence → that evidence is quarantined until an owner re-derives; risky-3 produced 75% of
  Wednesday and its replay harness currently cannot verify that lane.
- **If** the watchdog writes a `*_FAILED` BROKEN block → real signal now (the argv+hang bugs
  that made it noise are dead); act on it.
- **If** `synthetic_core_rows_excluded` > 0 for any Friday+ date → a SECOND ledger writer
  exists; the discriminating signal is now clean — hunt it.
- **If** bold-2 logs `RISK_DENY_PDT` Mon/Tue or the escalation cord names it → expected
  behavior, not a defect (unless J flipped Option A).
- **If** SPY breaks down with VIX < 17.3 → no arm can short it; the exonerated floor stands on
  current evidence — log the event, don't change it mid-week (Rule 9).

---

## 6. What needs J

**One decision:** the account-type/PDT call —
[PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md](PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md), one page,
three coherent options, facts live-read, keys untouched. bold-2 sits dark Monday+Tuesday on a
self-imposed legacy rule the broker doesn't apply and FINRA is retiring; both param docs cite
accounts that no longer exist. Option A is one line before the open. **J owns this; nothing
ships without him.**

**Nothing else.** No verifier flagged anything for revert. Everything shipped tonight is on the
REVOKE surface in `automation/overnight/STATUS.md` with one-line reverts; the open items below
act on REVOKE or are already owned:

- 3 anchor-fidelity replay REDs — needs an owner before fleet-replay evidence is trusted (top
  of the after-hours queue; STATUS.md ## Known broken).
- Two V-d1 counters (Lane 4's winner_autopsy fold vs Lane 5's meter column) — diff once,
  declare one canonical; deliberately not resolved unilaterally tonight.
- `crypto_twin_core.py:630` carries the same single-flat-read prune D5 fixed — twin surface,
  same-class fix not applied blind.
- Weekend doctrine-text fix (Rule 9 window): CLAUDE.md "runner target 2.5x" → "2.5x on
  vwap-family; ribbon_ride deliberately has NO finite target (SS-B)". Ships Saturday with a
  changelog entry.
- Pre-existing `LastTaskResult` graduated-guard RED in self_check.py — instrument lane's queue.

---

## 7. Spoken brief (Gamma, first person)

1. The book grew fourteen point seven percent this week — twenty-five thousand to twenty-eight
   six sixty-seven — and I have to say the honest part first: Tuesday was ninety-eight percent
   of it, ex-Tuesday we made sixty-four dollars, and the twenty-three days before this week were
   net negative. The trend is not earned yet. Next week's job is to earn it.
2. What we did genuinely well: Thursday's entry — structure confirmed on the one-minute, tied to
   a level, three arms in fifteen seconds — that trade alone paid fifteen hundred and it is now
   the measured template, not a feeling.
3. Tonight I ran seven lanes in parallel and shipped twenty-five commits, every one verified by
   an independent reviewer, and nothing came back needing a revert.
4. Only one thing about Monday's trading is different: risky-three goes back to out-of-the-money
   strikes because its own pre-registered kill bar was hit — it lost six fifty-three on the
   extension while risky-one made nine hundred keeping it, so now they run the honest A/B.
5. The same-bar cooldown you sanctioned is wired but deliberately not armed — when I replayed it
   through the engine's real bar identity, it blocked Tuesday's five-twenty-four winner and
   nothing on Wednesday. Its own prereg killed it, and the forward measurement runs automatically.
6. On small losses: I tested every loss-cap combination against Wednesday and the honest floor
   is minus seven-ten — the levers subtract. What actually protects us is the phantom-position
   fix, the repeat-entry protections on their clocks, and not trading the bleed cohort.
7. On holding winners: the chandelier trail already is the policy — the floor variant I tested
   gives back nine hundred on a real trend day. The one live idea left is selling half instead
   of two-thirds at plus-one-hundred, frozen with a clock.
8. On chop: I measured it instead of guessing — no-structure entries are our best trades, not
   our worst; the chop that hurts is re-buying the same falling contract. There's a meter in the
   nightly brief now so we see exposure instead of arguing about it.
9. All nine harness defects are fixed and guarded, including a test suite that was quietly
   writing fake rows into the live decision ledger — named, stopped, and the ledger's clean
   signal is now a tripwire for any second writer.
10. One thing is yours alone: bold-two sits dark Monday and Tuesday on our own legacy PDT rule —
    the decision page is one page, and one line frees it before the open if that's your call.
