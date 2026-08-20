# 🌙 NIGHT SYNTHESIS — 2026-08-19

**Written** `2026-08-20 01:44:36 Thursday EDT` (`setup/scripts/et_clock.py`, `market_hours=False`).

> ⛔ **NOTHING IS ARMED.** No `params*.json` touched, no order placed, no gate flipped, no engine
> file edited by this synthesis. Every proposal in §5 carries a named kill criterion. **J decides
> what ships.**

One surface for the whole night. Five lanes ran: the canonical trade matrix + day-summary tool,
the winners/losses matrix study, a data-custody build, a SPY-history backfill, and two root-cause
investigations — then **three independent adversarial refutation passes** over the findings.
Numbers marked ✅ were recomputed fresh in this session from the sources in §6.

---

## ⛔ VERDICT BOX — the three things that most changed the picture

> **1. 🚨 The book had ZERO backups, not weak ones — and that is now fixed.**
> `fills-ledger.jsonl`, the only surviving copy of **22 trading days Alpaca has already deleted**,
> was untracked **and** unignored — `git clean -fd` would have destroyed it permanently. It is now
> checksummed off-volume on `D:\GammaArchive`, and a restore drill rebuilds the 303-row matrix from
> the archive alone at **−$1,805.00 exactly**. ✅
>
> **2. 🚨 One of our own headline numbers did not reproduce — it sign-flipped.**
> The engine-stress swarm's **+$7,728.5** re-ran on identical inputs as **−$9,723.6**. Cause:
> `abs(hash(seed))` seeds numpy and `PYTHONHASHSEED` is unset anywhere in the repo ✅, so **150 of
> 1,200 cells are a fresh random draw every process.** Every stress-swarm P&L figure on record is
> unreproducible until that is pinned. The deterministic baseline matched to the cent — a *seeding*
> defect, not a broken harness.
>
> **3. 📉 Nothing new survived — and the one bull gate we actually run was armed on a
> walk-forward computed off a denominator of one.**
> Four matrix lanes → four candidates → **four refutations** (three died on the same fact: leave-
> best-two-days-out flips the sign). Meanwhile `block_bull_1100_1200` (armed 2026-06-18 on **IS
> n=11 / OOS n=1**) has blocked **17 live signals, 17 of 17 at maximum bull score** ✅, was flagged
> REVALIDATE **twice** and never actioned — and its purpose-built forward probe is already
> `"enabled": true` with an allowlist containing **this gate and nothing else** ✅.

---

## 1. 🔒 DATA CUSTODY — the direct answer

**J asked plainly. Answered plainly, no hedge:**

### **The irreplaceable history is now SAFE against everything that was realistically going to kill it. It is NOT safe against fire, theft, or ransomware.**

| threat | this morning | now |
|---|---|---|
| accidental `git clean -fd` | **would have deleted 22 trading days** | ✅ closed (`.gitignore:161` ✅) |
| `rm` / repo wipe / bad checkout on C: | only copy lived beside the repo | ✅ second copy on a different volume |
| single-disk failure | one disk | ✅ two disks (C: repo, D: archive) |
| silent bit-rot | undetectable | ✅ content-addressed sha256, re-read and re-verified every fire |
| **fire / theft / ransomware** | exposed | 🚨 **STILL EXPOSED — one machine, two disks** |

**Proof it works, not proof it exists:**

- Restore drill rebuilds **from the archive alone**: `303 round trips, gross $-1,805.00`,
  `rebuilt matrix: 303 rows … net $-1,939.90, 35 days, crosscheck=AGREE`, 4/4 PASS.
- A negative control proves the drill reads the **archive**, not the live file — making it secretly
  copy the live file makes the drill fail loudly.
- The scheduled task **actually fired**: `Gamma_LedgerCustody`, `State: Ready`,
  `LastTaskResult=0`, `LastRunTime 8/19/2026 10:52:22 PM`, `NextRunTime 8/20/2026 2:40 PM`
  (=16:40 ET) ✅ — verified as *fired with result 0*, not merely "registered".
- Archive is **4.6 MB on disk** ✅ for 89.5 MB of sources (content-addressed dedupe). Storage was
  never the constraint — **colocation was.**

### 🚨 Still at risk — the honest list

1. **No offsite copy.** D: and C: are two disks in **one machine**. The archive is 4.6 MB; it would
   fit anywhere. Needs a destination J chooses (external rotation or a cloud target) — no vendor was
   added without an OK.
2. **The clock is still running.** Alpaca's retention boundary is **2026-08-03** and slides forward
   daily. Today **22 of 35 trading days are ledger-only** (broker copy gone) — **137 of 303 round
   trips, 45.2%, −$1,664 gross = 92.2% of the book's loss**. Unattended it grows by **one day per
   trading day**. Nothing built tonight stops that; it only guarantees we keep *our* copy.
3. **`order-intents.jsonl` has the identical hole today** — untracked **and** unignored, the exact
   shape `fills-ledger.jsonl` had. It *is* archived now, but the deletion hole is open. It belongs to
   the concurrent order-intent lane; flagged, not edited.
4. **Attribution defect (content is safe).** All 5 custody files were swept into another lane's commit
   `df50f823 "feat(cockpit)"` during `commit_scoped.py`'s add→gate→commit window. Content verified
   identical at HEAD, 29/29 tests pass from the committed state. History was **not** rewritten — main
   is shared and other lanes are mid-flight.
5. **Unverified:** whether any pre-2026-07-20 copy of the fills ledger exists elsewhere. Belief: none.
   External drives were not exhaustively searched.

---

## 2. CONCLUDED vs REFUTED — with the numbers

Every finding went through an independent pass that tried to kill it. Three did not fully survive.

### 2.1 Stress swarm — root cause **CONFIRMED**, headline P&L **REFUTED**

| claim | verdict | number |
|---|---|---|
| Swarm silently collapsed to **1 seed day** | ✅ **CONFIRMED** | `sorted(glob)[-1]` picked `spy_5m_2026-07-23_supplement.csv` — **80 rows, one date**; ledger rows 112–187 all `n_seeds=1` |
| Removing the cause removes the symptom | ✅ **CONFIRMED** | cause present → `['2026-07-23']`; cause removed → 15 days, order-identical |
| No look-ahead in the perturbations | ✅ **CONFIRMED** | prefix-stable at k=10/20/40/60 on all 5 transforms (`np.allclose`, atol 1e-9) |
| Cache is **63** RTH days, not 35 | ✅ **CONFIRMED** | the "35-day cap" framing was wrong for *this* file |
| **Aggregate +$7,728.5 after the fix** | 🚨 **REFUTED** | identical re-run: **−$9,723.6**. Baseline subtotal **−$9,869.7 in both**, per-day to the cent |
| "the negatives were a single-day artifact" | 🚨 **REFUTED** | drop 2026-07-09 → **−$5,096.6**; drop 2026-06-12 → **−$3,531.0**; a 10-seed run 12 min earlier logged **−$5,123.3**. Of 3 large fixed-harness runs, **2 are negative** |
| The fix generalizes | ⚠️ **NO — patches the instance** | `_pick_broadest` takes freshest-end-date with **no minimum-breadth floor**; a supplement named with two real dates re-breaks it |

**Root cause, one sentence:** `_perturb_seed`'s `add_noise` branch seeds numpy with
`np.random.default_rng(abs(hash(seed)) % (2**32))` (`engine_stress_swarm.py:239` ✅) and CPython salts
string hashing per process, so **150 of 1,200 cells are non-deterministic across runs.**

**Also worth knowing:** `select_seed_days` hardcodes `picks[2] = df.loc[df["rng_pct"].idxmax()]` — the
worst day is **selected for by construction** (rank 1 of 63, 3.7× median range), not discovered.

### 2.2 `block_bull_1100_1200` — **CONFIRMED** thin, two sub-claims corrected

| claim | verdict | number |
|---|---|---|
| Pure time+side gate, no score/tier/VIX term | ✅ CONFIRMED | `gates.py:284-291` ✅ — `side == "C"` and `11:00 ≤ t < 12:00`, nothing else |
| Armed on almost nothing | ✅ CONFIRMED | `params.json:212` ✅ — **IS n=11, WR 9.1%, −$89; OOS n=1, −$42; WF 5.219 = (42/1)/(89/11)** — a walk-forward off a denominator of **one** |
| Flagged REVALIDATE, never actioned | ✅ CONFIRMED | twice: 2026-07-22 `RETEST-INSUFFICIENT-N`, plus `"expiry_verdict":"YELLOW"` / `"revalidation":{"status":"NOT_FILED"}` |
| It blocks *good* signals | ✅ CONFIRMED | **17 live fires** ✅, `Counter({('C', 11, 'BULLISH_RECLAIM_RIDE_THE_RIBBON'): 17})` — 17/17 at max bull score, 100% safe arm |
| Removing the gate lets the trade through | ✅ CONFIRMED (mechanism, not correlation) | gates 6–15 enumerated against safe's real params: **nothing else can block a C-side entry**; bold logged `ENTER_BULL \| PLACED` on the same minutes |
| Blocked-cohort net effect | ⚠️ **too small and unstable to call** | 4 measurable episodes, 16 fills, **net −$360.35**; 4 defensible proxies span **−$67 … +$11 per trip**; **3 of 4 say the gate SAVED money** |
| "11:00 CALLs are reliably negative" | 🚨 **REFUTED** | drop-worst-**two**-days flips the gated hour to **+$185.3** — its negative expectancy does not survive leave-two-out |
| The *ungated* 10:00 hour is worse | ✅ **CONFIRMED, and stronger than the gated one** | n=36, **0 winners gross or net**, 9/9 days negative, drop-top-loss-day still **−$1,332.4**; setup-matched n=20, 0 wins, **−$54.0/trip** |

**Material discovery:** the revalidation instrument **already exists and is enabled** —
`accounts.json` `probe_arm: {"enabled": true, "arm_id": "risky-3", "daily_cap": 3}` ✅ and
`build_shared_signal.py:842` `PROBE_ALLOWED_VERDICTS = frozenset({"SKIP_BULL_1100_1200"})` ✅, an
allowlist of exactly this one gate, built 2026-07-10 to convert this cohort into forward evidence.
**The correct next action is "read/repair the probe's tagging", not "file a revalidation from scratch."**

🚨 **New defect, unresolved:** `gate-registry-status.json`'s replay reports the *same* episode set as
`"sign":"POSITIVE"`, n=3, **+$54**, best_day **+$147** — while every sibling arm lost on both days and
the real-fill proxies give **−$159 … −$196**. A sign contradiction on an identical episode set.

### 2.3 safe/bold structure asymmetry — mechanism **CONFIRMED**, cost **REFUTED to zero**

| claim | verdict | number |
|---|---|---|
| safe's structure classifier throws every tick | ✅ **CONFIRMED, reproduced 5/5** | `(None, "error:ModuleNotFoundError:No module named 'backtest'")` at the safe slot, real bars, 4 cutoffs + empty payload |
| Cause is sys.path ordering | ✅ **CONFIRMED + inoculated** | importing `setup_dispatch` (`heartbeat_core.py:1602`) is the **sole** inserter of the repo root; appending it first makes the error vanish 5/5 |
| Live ledger shows the split | ✅ CONFIRMED | 2026-08-19 `{('safe', True): 12, ('bold', False): 12}`; lifetime **safe 115/115 DEGRADED, 0 SCORED** vs bold 86/115 |
| **"up to 6 near-misses could have flipped"** | 🚨 **REFUTED — realistic cost is ZERO** | joining each near-miss to its **paired bold row** on `core_tick_id`: bold **SCORED 0 of 6**. On every near-miss tick the arm that *had* the path also had no structural opinion |
| Blast radius on live trading | ✅ **NONE, by construction** | the live structure veto runs the classifier in a **subprocess** (`subprocess.run([..., "-m", "backtest.lib.engine.engine_cli"], cwd=REPO)`) — the gate that actually blocks trades never sees the parent's path ordering. Conviction rows are `"shadow_only": true` with no consumer |
| Concentration | ⚠️ worse than first disclosed | byte-level proof exists on **one day** (12 ticks); attributable near-misses **n=3, 100% on 2026-08-19** |

**Net:** a real, deterministic defect that has cost **$0** so far — but **safe-2's structure instrument
has been dead since 2026-08-17**, so we have been reading a shadow signal that was never produced.

---

## 3. 🎯 WHAT IS NOW KNOWABLE THAT WAS NOT THIS MORNING

Capability, not activity. Each is a question we *can now ask*; none has been asked yet.

**① Deeper history — 35 days → 657 ✅ (≈19×).**
`spy_sip_cache` now holds **657 SPY 5m days, 2024-01-02 → 2026-08-19** (622 new), plus matching 1m,
DST-verified on both sides of all 5 US transitions, guarded by a test that reds if any cached day loses
its 09:30 ET bar. **What it unlocks, measured fresh:** our 34 measurable live days have a median RTH
range of **0.882%** vs **0.864%** across all 656 — statistically the *same middle*. But our **worst**
live day (**2.737%**) sits at the **97.6th percentile**, and **15 days (2.3%) of the wider history were
more violent than anything we have ever traded**, topping out at **10.798% on 2025-04-09** ✅.
**The tail regimes are now on disk. They have never been tested.**

**② Per-leg exit truth is the default surface.**
**78 of 303** round trips are multi-leg (TP1 + runner) and hold **50 of 70 winners** and **93.1% of all
winner dollars** ✅. In the canonical table **0 rows carry a null `exit_premium`** ✅ — the naive filter
that reported the book as −$14,689 (matrix lane's figure; not re-derived here) now drops nothing. The
reconciling day-summary means a consumer that disagrees with **−$1,805.00 / −$1,939.90** fails loudly
instead of quietly.

**③ Exit-reason coverage is measurable, and the gap is exactly 5.**
**298 of 303** exits carry `decision-ledger:exit_pass.actions`; **5 carry
`UNLOGGED: fleet_eod.close_all_spy_options writes no decision row`** ✅ — four small 2026-06-30 stubs and
**risky-1 −$440.00 on 2026-08-10**, the second-largest loss in the book. We now know exactly which trades
we cannot explain, and why.

**④ A standing custody tripwire.** The daily drill reds the day the live ledger stops reconstructing to
**303 / −$1,805.00** — silent data loss becomes a loud failure.

**⑤ The forward test for the bull gate already exists** (§2.2). The open question is whether it is
firing, not whether to build it.

---

## 4. ❓ STILL UNKNOWN — stated, not buried

1. **Is the 2.14pp breakeven gap closeable? UNKNOWN.** ✅ Book: WR **23.10%**, avg win **$223.63**, avg
   loss **$75.51**, breakeven WR **25.24%** → short **2.14pp** = **−$1,940.98** = **−$55.46/session** =
   **−$6.41/round trip**. (The "1.6pp" framing is the same arithmetic on a smaller subset — **use
   2.14pp**.) It closes with **+12.4% more tail** *or* **−11.0% less bleed** — neither heroic, both
   plausibly inside one exit-side parameter. But **four lanes hunted that parameter tonight and produced
   four refutations**, and costs are provably not the villain (all fees **$135.98** = **7.0%** of the
   deficit). **We know the size of the gap and the exchange rate. We do not have a validated lever.**
2. **Is the safe/bold structure asymmetry resolved? NO — diagnosed, not fixed.** The one-line fix (append
   repo root before the first classifier call) is *not applied*: `heartbeat_core.py` is dirty from the
   concurrent order-intent lane and was left alone. Until it lands, safe-2 keeps producing **zero**
   structure reads. Cost so far measured **$0**; cost going forward unknown, because C5 has never been
   observable on that arm.
3. **35 days is ONE VIX regime and cannot tell us what a different one does.** ✅ All 303 trips sit in
   **VIX 14.41 → 19.86, median 15.88** — no stress, no crush, nothing 25+. Every gate, exit knob and win
   rate in this repo is conditioned on that single regime. The 657-day cache now *contains* other regimes
   (§3①) but **no engine result has been produced on them.** "This edge is real" currently means "real in
   a low-VIX, median-range summer."
4. **Are the other stress-swarm results contaminated?** UNKNOWN. The RNG defect is *class*-level — every
   historical swarm P&L in `_ledger.jsonl` predates any pin. Nothing has been re-run.
5. **Which replay is lying about the bull gate?** `gate-registry-status.json` says **+$54 POSITIVE** on
   episodes where real fills say **−$159 … −$196** (§2.2). Unreconciled.
6. **Did the probe arm ever actually fire?** Strike/qty signature *suggests* risky-3 probed on 2026-08-04
   (qty 5 ATM vs its normal qty 8) and did **not** on 08-13 / 08-19. **Unverified** — no `PROBE_ARM` tag
   was confirmed in the ledger.
7. **Why risky-1 lost $440 on 2026-08-10 is unrecoverable from logs** — `fleet_eod` force-flattened and
   only printed. Fixable forward, never backward.
8. **`_pick_broadest` will re-break** the first time a patch file is named with two real dates (§2.1).
9. **Independence, always:** 5 arms trade one signal at **r=0.846** — 303 trips are **~60–90 independent
   decisions**. Every per-trip statistic above is softer than its n suggests.

---

## 5. PROPOSALS — nothing armed, each with a kill criterion

Ranked by expected value. **None applied. J decides.**

| # | proposal | why now | **kill criterion** |
|---|---|---|---|
| 1 | **Pin `PYTHONHASHSEED`** (or seed from a stable hash) in the stress harness, then re-run the last 3 batches | a headline sign-flipped; every swarm P&L is currently unreproducible | **Kill if** two fresh processes still disagree on any cell after the pin — the non-determinism is elsewhere and the harness stays quarantined |
| 2 | **Offsite copy** of `D:\GammaArchive` (4.6 MB) to a destination J names | the last custody hole; fire/theft/ransomware still take everything | **Kill if** the copy cannot be verified by re-reading its blobs and re-running the restore drill at the destination |
| 3 | **Read the probe arm's `PROBE_ARM` tags** before filing any bull-gate revalidation | the forward test is already enabled and allowlisted to this one gate | **Kill if** zero `PROBE_ARM`-tagged fills exist since 2026-07-11 — the probe is dead-on-arrival again, and *that* is the bug |
| 4 | **Land the one-line sys.path fix** once the order-intent lane releases `heartbeat_core.py` | safe-2 has produced 0 structure reads since 08-17 | **Kill if** safe still logs `structure=DEGRADED` on ≥90% of ticks over 3 sessions after the fix — the cause is not path ordering |
| 5 | **Run the engine on the 622 new days**, stratified by range percentile, before trusting any gate | we now hold 15 days more violent than anything ever traded | **Kill if** replay fidelity against the 35 live days fails the existing sim-accuracy gate — an unfaithful replay on 622 days is worse than none |
| 6 | **Add a minimum-breadth floor to `_pick_broadest`** | the current fix patches the instance, not the class | **Kill if** the floor ever rejects the real cache — then it is mis-specified |
| 7 | **Make `fleet_eod` write a decision row** (concurrent lane's surface — flagged, not edited) | 5 exits are permanently unexplainable | **Kill if** the new order-intent ledger already captures it — then this is redundant |
| 8 | 🚨 **Close the `order-intents.jsonl` deletion hole** (one `.gitignore` line, that lane's call) | identical exposure to the one that nearly cost 22 days | none — this is the same fix that already proved out |

**Explicitly NOT proposed: flipping `block_bull_1100_1200`.** Its basis is thin **and** the evidence that
removing it helps is thinner — **3 of 4 proxies say it saved money**, and the sign flips under 2 of 3
leave-one-day-out variants. *Both* directions fail the bar. Measure it with the probe first.

---

## 6. Reproduce

- Canonical book — `analysis/recommendations/trade-matrix.json` (303 rows; the P&L keys are
  `real_pnl_gross` / `real_pnl_net` — `gross_pnl` does **not** exist and silently sums to 0).
- Gap arithmetic + the four refuted candidates — [[analysis/deep-research/WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19|WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19]]
- Dataset depth + the bottleneck this backfill removed — [[analysis/deep-research/DATASET-DEPTH-AUDIT-2026-08-19|DATASET-DEPTH-AUDIT-2026-08-19]]
- Entry side, settled separately — [[analysis/deep-research/LOSER-SEPARABILITY-2026-08-19|LOSER-SEPARABILITY-2026-08-19]]
- Custody — `setup/scripts/archive_ledgers.py`, `backtest/tests/test_archive_ledgers.py` (24 tests, 5
  RED-proofed), `D:\GammaArchive\integrity-report.json`, task `Gamma_LedgerCustody`.
- Backfill — `backtest/tools/backfill_spy_sip_cache_2024.py`,
  `backtest/tests/test_spy_sip_cache_dst_guard.py`.
- Gate — `backtest/lib/engine/gates.py:284-291`, `automation/state/params.json:211-212`,
  `analysis/recommendations/safe_bull_1100_1200_gate.json`.
- Structure asymmetry — `setup/scripts/heartbeat_core.py:546,571,1602`,
  `automation/state/core-decisions.jsonl`.
- Regime-breadth stat — recomputed from `backtest/data/spy_sip_cache/spy_5m_*.json`, RTH ≥60 bars,
  `100*(high−low)/open` per day.
