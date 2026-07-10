# Gate Provenance Sweep + block_elite_bull SS-B Revalidation — 2026-07-10

**Mission:** two parts. (1) Provenance-audit the 5 gates that blocked entries on 2026-07-10 while the bull side won ($7 trend day, 6 arms / 0 trades). (2) Relaunch the `block_elite_bull` SS-B revalidation a PC reboot killed on 2026-07-09, under a frozen pre-registration.

**Method:** static code read (`gates.py`, `engine_cli.py`, `heartbeat_core.py`) cross-checked against today's `automation/state/core-decisions.jsonl` (780 rows), `automation/state/fleet/*/decisions.jsonl`, params.json doc-strings, and every cited `analysis/recommendations/*.json` scorecard. All timestamps ET. Read-only for Part 1; Part 2 writes analysis-only artifacts, no params/heartbeat/gate code touched.

---

## PART 1 — participation-side gate provenance

### Headline: three of the five items are not what they look like

Two of today's "5 gates blocking a winning day" stories collapse under a same-second cross-account check: **the SAFE account independently proves the exact bar BOLD's gate fired on was a stale echo from yesterday's last 5m bar, not a live afternoon signal** (§1.1). A third item (§1.4) has no code to audit — the doctrine describing it as "active" cites a study that never contained the numbers attributed to it, and the real source of those numbers reached the opposite conclusion nine days earlier. Only two of the five (§1.2 `SKIP_BULL_1100_1200`, §1.3 the ELITE/SUPER split) are genuinely live, revalidation-worthy blockers today.

### 1.1 — `SKIP_CONF_LVL_REC_AFTERNOON` (5 blocks, Bold) — KILL-CANDIDATE

- **Enforcement:** `backtest/lib/engine/gates.py:365-375`, `GATE_ORDER` #12. Predicate: `bt.time() >= 14:00` AND `confluence`+`level_reclaim` in triggers. `bt` is the **trigger bar's own timestamp**, not "now" — the gate runs *inside* `engine_cli.decide_payload`, which executes *before* `heartbeat_core.py`'s post-verdict ladder (`_stale_trigger_bar` etc., lines 827-847) ever gets a chance to run.
- **Armed:** Bold only (`automation/state/aggressive/params.json:146`).
- **Provenance:** ratified 2026-06-17 (IS +$468 / OOS +$176); doc-string as of 2026-06-18 downgrades it to **"KEPT but DEAD (0 impact in all contexts)... fully superseded by `block_conf_lvl_rej_midday_afternoon`"** — but that superseding sibling was *removed* the same day (06-18), a self-contradiction the 2026-07-09 census already flagged.
- **Exit-contaminated:** yes, predates chart-stop-primary refresh and SS-B.
- **What it blocked today (quoted):** all 5 rows fired 09:31:04–09:35:04 ET — **morning**, not afternoon:
  ```
  2026-07-10T09:31:04 bold SKIP_CONF_LVL_REC_AFTERNOON spy=751.55 vix=15.73 triggers=[level_reclaim,ribbon_flip,confluence]
  ... (09:32-09:35, same spy/triggers)
  ```
  Cross-checked against SAFE at the **identical** timestamps:
  ```
  2026-07-10T09:31:03 safe SKIP_STALE_TRIGGER trigger_bar_et=2026-07-09T15:55:00-04:00 triggers=[level_reclaim,ribbon_flip,confluence]
  ```
  Same signal, same triggers, same spy=751.55. SAFE (which does *not* arm this gate) fell through to the stale-trigger-bar guard and got the bar's true provenance logged: **yesterday's 15:55 ET closing bar** — which, read as a raw clock value, legitimately is "afternoon" (`15:55 >= 14:00`), so gate #12 fired *correctly by its own logic* on a **36-hour-old phantom signal**. Zero of today's 5 fires are live.
- **Verdict: KILL-CANDIDATE** — two independent reasons: its own provenance doc already says "0 impact / superseded" (by a gate that no longer exists), and today's fires — the only evidence anyone has looked at since — are proven not to be live. **The real bug is upstream**: `evaluate_gates()` runs before `_stale_trigger_bar`, so *any* `GATE_ORDER` time-window gate can misfire on a carried-over prior-session bar and get logged under the gate's own name instead of `SKIP_STALE_TRIGGER`. This contaminates every gate's fire-count in every prior census too, not just this one.

### 1.2 — `SKIP_BULL_1100_1200` (6 blocks, Safe) — REVALIDATE

- **Enforcement:** `gates.py:284-291`, `GATE_ORDER` #5. Armed Safe only.
- **Provenance:** `params.json:189`, ratified 2026-06-18: IS n=11 WR=9.1% total=-$89 (worst TOD bucket), OOS n=1 blocked (+$42), WF=5.22, 5/5 OP-22 gates pass. Scorecard `analysis/recommendations/safe_bull_1100_1200_gate.json`.
- **Exit-contaminated:** yes — pre-SS-B; ratified the same day chart-stop-primary shipped, so IS evidence likely straddles the transition.
- **What it blocked today:** 6 rows, two 3-minute clusters — 11:21:03-11:23:03 (spy=752.67) and 11:31:04-11:33:03 (spy=753.23), SAFE, SUPER tier (`level_reclaim`+`ribbon_flip`+`confluence`, bull_score=11, the ceiling). **Confirmed live** (SPY genuinely moving tick-to-tick, nowhere near the at-open stale-bar risk window) — this is a real block of a maxed-quality SUPER signal mid-trend.
- **Verdict: REVALIDATE** — thin (n=11 IS / n=1 OOS), pre-SS-B, and today is the first genuinely-live test of it since ratification, on a higher-quality (SUPER, not just ELITE) signal than its original evidence base ever covered.

### 1.3 — ELITE-vs-SUPER tier system — REVALIDATE (partially-validated C23 shape)

- **File:line:** live derivation `backtest/lib/orchestrator.py:1178-1184`; stateless mirror `backtest/lib/engine/engine_cli.py:472-489` (`_derive_tier`). **Not VIX-based** — purely trigger-driven: `(confluence AND ribbon_flip) OR len(triggers)>=3` ⇒ SUPER (qty 15); `confluence OR sequence` ⇒ ELITE (qty 10). `block_elite_bull` (`gates.py:269-277`) checks `tier=='ELITE'` only — SUPER is structurally exempt.
- **Today, corrected:** 20 ELITE blocks (10 safe + 10 bold, same signal at 11:51 and 12:51) confirmed. The mission's "11 SUPER passes" does **not** describe 11 live entries — those 11 raw ticks are exactly **2 underlying moments**, both blocked by *unrelated* gates: 5× `SKIP_STALE_TRIGGER` (the same 07-09 phantom bar as §1.1) + 6× `SKIP_MIN_PREMIUM_FLOOR` (Bold, 11:21-11:33). **Zero SUPER-tier entries actually landed today.** "SUPER passes the ELITE-only gate" is true only in the trivial structural sense.
- **Validated or trap?** The tier *boundary* was studied once: `backtest/tools/elite_subtier_sweep.py` / `analysis/recommendations/elite_subtier_sweep.json` (committed 2026-06-26, same commit as chef-bull-scope-ab). SUPER (n=14, WR 42.9%, avg **+$650.8**/tr) beats ELITE (n=22, WR 36.4%, avg **+$147.4**/tr) in aggregate — but ELITE's own internal VIX-bucket breakdown shows its *weakest* sub-population is VIX<17 (n=13, WR 23.1%, avg +$55.2/tr) — and **every one of today's 20 ELITE blocks sat at VIX 15.3-15.6**, squarely in that bucket. That cuts both ways: it's consistent with a real VIX-conditional effect (a C23-flavored concern), but the sweep's *own* gate-candidate bar (WR<15% AND avg<-$20 AND n≥10) was never cleared even by that weakest bucket (WR 23.1% > 15%, avg +$55 > -$20) — so blocking specifically-at-low-VIX was never validated either. The file itself is exit-contaminated (hardcodes `premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08`, pre-dating both exit-shape changes).
- **Verdict: REVALIDATE** — same underlying question as `block_elite_bull` itself (is ELITE a real loser cohort under the *current* exit shape), not a separate lever. Folded into Part 2 below rather than re-litigated standalone.

### 1.4 — FLEET `ribbon_flip`-cohort block — KILL-CANDIDATE (the doctrine text, not any code)

- **Exhaustive search result: this filter does not exist anywhere in the executing system.** `block_bull_ribbon_flip` (`gates.py:279-282`, the only ribbon_flip-named *entry* gate in the codebase) is **absent from both `params.json` and `aggressive/params.json`** — confirmed by direct grep (zero hits for the literal key) and independently by two prior audits (`GATE-PROVENANCE-AUDIT-2026-07-02.md:37`: "dormant — ignore"; the 2026-07-09 census: "KEEP (inert/unarmed)"). On the fleet lane specifically, every `ribbon_flip` reference in `automation/state/fleet/*.py` is about **exit** (`ribbon_flip_back`, an unrelated invalidation mechanism) — zero entry-side ribbon_flip filtering anywhere.
- **Provenance chase:** `markdown/doctrine/BULL-DIRECTION-ACTIVATION.md` lists `block_bull_ribbon_flip` under "Active per-block filters (A/B-validated)," citing **"chef-bull-scope-ab, 2026-06-26"** with n21 WR10% −$2,222 (loser, blocked) vs n24 WR29% +$6,901 (winner, kept). **Verified this session: false.** `analysis/recommendations/chef-bull-scope-ab-2026-06-26.json` (read in full) contains only a top-level 25-trade `enable_bullish` A/B — no ribbon_flip sub-split anywhere. The n21/n24/WR10%/WR29% numbers instead trace to `markdown/doctrine/LESSONS-LEARNED.md` **L126** (dated **2026-06-17**, nine days earlier, n=45=21+24, WR "9-11%" vs "29%" — near-exact match) — whose own verdict is the **opposite**: *"Fix: Do NOT implement `block_bull_ribbon_flip`... WF=-23.984... regime-conditional... no static filter can solve this."* (OOS delta was **-$3,123**, SW_hurt=3/5 — ribbon_flip is a *lagging-bad* tell in range-bound markets but a *momentum-confirming-good* tell in trending markets, exactly the regime running right now.)
- **Today:** N/A — nothing to block; nothing in the executing code reads this key. Fleet's actual near-zero participation today (1 raw signal across all 4 arms, at 09:34:02, the SAME ELITE-tier `BULLISH_RECLAIM` core saw) was blocked by `SKIP_EARLY_ENTRY` — it missed the 09:35:00 floor by **58 seconds** and never re-fired all session. A mundane timing-gate story, not a cohort-block story.
- **Verdict: KILL-CANDIDATE on the doctrine text.** Delete or correct the `BULL-DIRECTION-ACTIVATION.md` "Active per-block filters" row for `block_bull_ribbon_flip` — it is not armed anywhere, and its cited evidence is a misattributed, reversed-verdict lesson. Left as-is, a future session will treat this as "already validated and active" and skip re-testing a filter that (a) doesn't exist and (b) the one real study of it says should never exist.

### 1.5 — `structure_veto` (4 blocks) — FOLD INTO F2, no duplication

- F2 (`automation/overnight/queue.md:14`) already flags thin, non-OOS provenance for `structure_veto` — not re-litigated here.
- Today's increment: 4 fires, **all** at 00:54:59-01:01:29 ET (after midnight), **all** `armed: false`, spy pinned flat at 751.0, spread_cents a suspiciously round 10, vix pinned flat at 16.0 — a diagnostic/gym-harness signature identical in shape to the two the 2026-07-09 census already found ("armed=false... looks like a diagnostic/gym harness call"). Zero live RTH fires, second session running.
- **New for F2's scope note:** these 4 fires blocked an **extra-setup** signal (`bollinger_squeeze`, `extra_exec_blocked_by: "structure_veto"`), proving `structure_veto` also gates the extra-setup dispatch path, not only the core ribbon path its `structure-veto-ab-2026-06-26.json` evidence was measured on. Worth folding into F2's scope before it's closed.

### Part 1 verdict table

| # | Gate | Enforcement | Today's fires | Verdict |
|---|---|---|---|---|
| 1 | `SKIP_CONF_LVL_REC_AFTERNOON` | `gates.py:365-375` (Bold) | 5 — **all a stale 07-09 15:55 phantom bar**, proven via SAFE's cross-account `SKIP_STALE_TRIGGER` at the same instant | **KILL-CANDIDATE** |
| 2 | `SKIP_BULL_1100_1200` | `gates.py:284-291` (Safe) | 6 — confirmed live, SUPER-tier maxed signal | **REVALIDATE** |
| 3 | ELITE-vs-SUPER tier | `orchestrator.py:1178-1184` / `engine_cli.py:472-489` | 20 ELITE blocks; "11 SUPER" = 2 real moments, 0 entries | **REVALIDATE** (folded into Part 2) |
| 4 | FLEET `ribbon_flip` block | *none — not armed anywhere* | 0 (doesn't exist); fleet's real 09:34 block was `SKIP_EARLY_ENTRY` | **KILL-CANDIDATE** (doctrine text) |
| 5 | `structure_veto` | `engine_cli.py:567-589` (Safe) | 4 — off-hours, `armed:false`, diagnostic | **FOLD INTO F2** |

---

## PART 2 — `block_elite_bull` SS-B revalidation (relaunched)

### Pre-registration

Frozen **before** any replay ran: `analysis/recommendations/block-elite-bull-ssb-preregistration.json` (`content_sha256_16: e9933be0e0ed453e`, verified by the runner's `preflight()` on every execution — hash-pinned by `test_block_elite_bull_ssb_revalidation.py`).

- **Cohort:** (a) the original `bull_unblock_replay_probe.py` n=7 cohort, 2026-05-21..2026-06-30, reproduced by **re-running its exact A/B** (not trusting the saved JSON) so the Trade objects' entry time/strike/premium/reclaim-level are available for SS-B replay; (b) extended through 2026-07-10 by mining `core-decisions.jsonl` (`account=='safe'`) for `SKIP_ELITE_BULL_LEVEL_RECLAIM` since 07-01, **deduped** (stated rule: gap ≤5 min = same event, matching this engine's native 5m bar granularity; sensitivity checked at 2-min and 15-min too — n stays ≥17 at every threshold), with a **stale-echo exclusion** (cross-account `SKIP_STALE_TRIGGER` corroboration within ±90s — the exact mechanism proven live in §1.1).
- **Comparison cohort (disclosure only, not pass-bar-gated):** the SUPER-tier population over the same window — thin by construction (n=4 after excluding 2 mechanically-untradeable events).
- **Strike convention:** `simulator_real.py:372-376`'s production rule (`strike = round(spot) - 2` for calls, **ITM by $2**) — explicitly **not** `t4_exit_matrix.py`'s OTM-2 convention (the two tools use opposite signs under the same "-2" label; documented in the prereg's `sim_accuracy_check_OP16` as a real, previously-undocumented convention mismatch in this codebase).
- **Exit shapes:** OLD = the shipped `-20%/+150%/sell80%/fixed` CONTROL shape (`t4_exit_matrix.CONTROL`, the codebase-wide "OLD" reference used by every prior SS-B-family study); SS-B = `structure_stop_study.SS_B_SHAPE` (cat -50%, tp1 100%/sell66.7%, trail 15%) reused verbatim, unmodified.
- **Pass bar (frozen):** unblock proposed only if ALL FOUR hold — SS-B total positive, SS-B total positive after drop-top-1, old-exit parity reproduces -$241.26 within $1.00, n≥12 events.

### An important correction found and disclosed mid-study

The mission (and the pre-registration's initial framing) assumed the original -$241.26 was produced under the "-20/+150" CONTROL shape. **It was not.** `bull_unblock_replay_probe.py`'s `_bull_cfg()` never overrides `premium_stop_pct_bull`/`tp1_premium_pct`/`tp1_qty_fraction`, so it silently inherited `run_backtest`'s bare defaults (`-8%` stop / `+30%` TP1 / sell 66.7%) — a much tighter shape than CONTROL. This does **not** invalidate the parity check (which re-runs the *original code* verbatim and reproduces -$241.26 exactly, independent of what shape that implies) — but it means the "OLD" column in the headline comparison below is the codebase's standard CONTROL reference shape (used by every other SS-B study for consistency), not literally the exact shape that produced -$241.26. Both readings agree on the conclusion; disclosed here rather than silently smoothed over.

### Results

**Parity check:** re-running the original A/B **exactly** reproduced n=7, **-$241.26**, byte-for-byte (0-cent divergence) — including all 7 individual strikes matching the recorded artifact exactly. Condition 3: **PASS**.

**Elite cohort (n=28 = 7 original + 21 extension, all mined/replayed with 0 missing-bars drops):**

| | n | WR | Total P&L | Expectancy/tr | Drop-top-1 remainder |
|---|---|---|---|---|---|
| OLD (CONTROL) | 28 | 25.0% | **-$560.00** | -$20.00 | -$3,960.00 (still negative) |
| SS-B | 28 | 28.6% | **-$3,873.60** | -$138.34 | -$6,810.00 (still negative) |

SS-B does not merely fail to flip this cohort — it makes an already-negative population **~7× worse**. Mechanism (verified, not assumed): only 10/28 trades ever triggered the structure-stop layer at all; the rest ground down through the wider **-50% catastrophe cap** (vs CONTROL's tighter -20%), so losers that CONTROL cut early run much further under SS-B before capping out. Two days — 2026-07-09 and 2026-07-10, the two most recent — are the *only* net-positive days in the 14-day cohort (+$7,098 combined under OLD); every other one of the 12 days is a loser under both shapes. This is the textbook shape of the recency-bias trap the mission's own framing ("today 6 arms/0 trades on a $7 trend day") was at risk of falling into: zoomed out to 7 weeks, today's frustration is the outlier, not the norm.

**Comparison cohort (n=4, disclosure only — SUPER-tier, never touched by this gate):** OLD total -$2,349 (0% WR), SS-B total -$1,920 (0% WR, but structure-stop fired on all 4 and softened the loss by ~$429). Notably, per-trade this thin sample is **worse** than the ELITE cohort (avg -$587/-$480 vs ELITE's -$20/-$138) — a live-data hint (n=4, not actionable alone) against the assumption that "3+ triggers = automatically better" baked into the tier system; queued as a note for whoever picks up item 1.3 above, not acted on here.

### Pass bar

| Condition | Result |
|---|---|
| 1. SS-B total positive | **FAIL** (-$3,873.60) |
| 2. SS-B drop-top-1 positive | **FAIL** (-$6,810.00) |
| 3. Old-exit parity reproduces -$241.26 (±$1) | **PASS** (exact) |
| 4. n ≥ 12 events | **PASS** (n=28) |
| **All four** | **FAIL** |

**VERDICT: KEEP.** No proposal staged (`block-elite-bull-ssb-unblock-proposal.json` correctly not written — verified absent on disk). `fable-too-good` discipline: not triggered — this is not an extraordinary win requiring an artifact hunt; if anything it's the opposite (a validated-KEEP getting *more* validated), and the mechanism (wider catastrophe cap costing more on a structurally-losing cohort) was independently verified against the per-trade `structure_fired` flags before reporting, not assumed.

### Outputs

- `analysis/recommendations/block-elite-bull-ssb-preregistration.json` (frozen spec, hash-pinned)
- `analysis/recommendations/block-elite-bull-ssb-revalidation.json` (full result, all 28+4 trade-level rows)
- `backtest/tools/block_elite_bull_ssb_revalidation.py` (runner, reuses `structure_stop_study.py`/`tw8_level_context.py`/`exit_shape_parity_study.py` machinery unmodified)
- `backtest/tests/test_block_elite_bull_ssb_revalidation.py` (19 tests: prereg hash pin + bite, parity-tolerance bite, dedupe rule incl. boundary/unsorted-input cases, stale-echo cross-account corroboration, strike convention, drop-top-1, golden-finding pin against the committed result) — **19/19 pass**.

---

## Single highest-leverage gate action for Monday

**Fix the stale-trigger-bar guard's ordering, not any single gate.** `evaluate_gates()` (the 15-gate `GATE_ORDER` battery, including every time-window gate: `block_conf_lvl_rec_afternoon`, `block_bull_1100_1200`, `block_conf_lvl_rej_midday_afternoon`, `midday_trendline_gate`) runs *inside* `engine_cli.decide_payload`, which executes **before** `heartbeat_core.py`'s `_stale_trigger_bar` check (which only runs on a raw `ENTER_BEAR`/`ENTER_BULL` verdict, lines 827-847). This session **proved** the consequence directly: `SKIP_CONF_LVL_REC_AFTERNOON` fired at 09:31 ET on a bar timestamped 15:55 ET the *prior day* — every one of today's 5 "afternoon" blocks was actually the same stale-bar echo SAFE correctly caught as `SKIP_STALE_TRIGGER` one field over. This is a **confirmed code-ordering bug**, not a P&L judgment call — it means every `GATE_ORDER` fire-count in every gate census run to date (including this one, including the 2026-07-09 census) is contaminated by an unknown number of phantom stale-bar fires mislabeled under whichever gate happened to check first, and it is a small, mechanically-testable, contained fix (move the stale-trigger-bar check to the top of `_engine_verdict`, before `decide_payload` is even called, with a guard asserting no `GATE_ORDER` gate can fire on a bar whose date != today).
