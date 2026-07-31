# FULL-SEND learning arm — ship report (2026-07-31)

> ## ⛔ CORRECTED 2026-07-31 evening — READ THIS BEFORE ANY NUMBER BELOW
>
> Two adversarial verifiers found defects in this lane's own write-up. Both are now fixed in
> place; the **architecture finding stands**, the **P&L claim is retracted.**
>
> 1. **The min-size P&L was a biased ratio estimator and BOTH headline signs INVERT.**
>    `scale_factor = 5/mean_qty` applied to a SUM, over a qty range of 3–22. Correct estimator
>    is per-trade `5·Σ(pnlᵢ/qtyᵢ)`. **Full population +$1,951 → −$1,010. Recent +$63 → −$734.**
>    The arm hard-clamps every entry to min size, so **this column IS the forward expectation.**
>    The old `_disclosure` claiming the scaling "is exact" was an affirmatively false statement
>    of method and has been deleted.
> 2. **The ATM strike override was NEVER reverted on the shipped path.** The revert landed in
>    `_tiers_for_arm` only; `_full_send_plan` (`fleet_executor.py` ~L849) never calls it and
>    prices `PROBE_STRIKE_TIERS` — offset 0 at $2K. **Every trade this lane adds is ATM.**
>    **DECISION: keep ATM** (it is what clears the $0.30 floor that refused risky-1 all Friday
>    — the point of the arm) and label it honestly instead of repointing production to make a
>    stale number look valid.
> 3. **Consequently the headline cell does not apply.** It was measured at `strike_offset=2`
>    (OTM-2); production trades `offset=0`. **OP-16 sim-accuracy: the incremental trades this
>    arm adds are UNMEASURED AT THEIR ACTUAL STRIKE.**
> 4. **Pre-registered check F2 now FAILS on BOTH windows** (it only ever "passed" on the biased
>    numbers). So **two** of the pre-registered checks fail, not one.
>
> **STATUS: ARMED as an explicitly UNMEASURED forward-paper experiment. NOT a validated ship.**
> Paper account `PA3W17FD8G19`, min-size clamp, every risk guard proven binding by execution.

**Verdict: ARMED, UNMEASURED (paper, reversible in one line) — it does NOT fix risky-1's
zero-trade problem, and the honest reason is in §4. The arm's real binding constraint is the
`min_entry_premium` floor, not selection.**

- Pre-registration: [`prereg-full-send-arm-2026-07-31.json`](prereg-full-send-arm-2026-07-31.json)
  — frozen **2026-07-31T17:35:46-04:00 ET**, before any run.
- Results: [`full-send-arm-2026-07-31.json`](full-send-arm-2026-07-31.json) — real OPRA fills.
  Its `_corrections[]` block carries both defects above, machine-readable.
- Harness: `backtest/full_send_arm_ab.py` · Instrument: `setup/scripts/full_send_vs_gated.py`
- Guards: `automation/state/fleet/test_full_send_arm.py` — 26 tests. The strike guard was
  **rewritten and RED-proofed 2026-07-31 evening**; the original was **vacuous** (it ran a
  `bull_score=11` fixture that the pre-existing scoring-peak lane rescues, so `_full_send_plan`
  never executed in it and it compared two normal-lane plans). The other 4 RED-proofs claimed on
  2026-07-31 afternoon were **not** re-verified in the correction pass.

---

## 1. The crux: a truly ungated arm was NOT representable

J asked why one arm can't "just get in shit and see if it works." The answer is architectural.

An arm's `gate_override` can **only ever ADD selectivity** — `_gate_check` / `plan_entry` return
a HOLD reason or `None`; nothing there can rescue a tick the producer never emitted. Measured
over **all 3,479 ticks of fleet history per arm**:

| arm | ticks | blocked by its OWN `gate_override` | on 2026-07-31 |
|---|---|---|---|
| safe-3 (tight) | 3,479 | **45 (1.3%)** | **0 of 128** |
| risky-1 (tight) | 3,479 | **45 (1.3%)** | **0 of 128** |
| risky-3 (loose) | 3,479 | **0** | **0 of 128** |

**The entire "gate" axis of the 2×3 grid is inert.** Entry ADMISSION is decided upstream in
`build_shared_signal`, which emits ONE `strategies[]` list every arm shares. So "this arm
inherits fewer vetoes" was not expressible in `accounts.json` at any value.

**Minimum change specified and shipped:** a producer-side `full_send` block +
a per-arm consumer lane — the exact grain the existing `probe` and `ladder` lanes already use.

### 1b. Dead knob found in passing (C14 class)

`fleet_executor._effective_passed` — the per-arm `gate_params.hard_skip_verdicts` override
shipped 2026-07-23 for risky-3 — **is unreachable on the live path.** It is only called from
`_chosen_side` → `plan_entry`, and `plan_entry` has exactly one caller:
`backtest/replay_fleet_arms.py`. Live ticks go `fleet_live` → `plan_all` →
`_plan_from_strategies`, which never consults it (`strategies` is always a list, so the
`is not None` branch always wins). risky-3's `hard_skip_verdicts: []` has never done anything
in production. **Not fixed here** — flagged, out of this lane's scope.

---

## 2. What the profile is (doctrine: arms are RISK PROFILES, not strategies)

Same validated setups (`ribbon_ride` entry setups only — the lane structurally cannot emit a
new strategy or setup name; guarded). What differs:

**Vetoes DROPPED** — cohort/tier only, an explicit allowlist, exactly the 5 that were measured:
`SKIP_ELITE_BULL_LEVEL_RECLAIM`, `SKIP_BULL_1100_1200`, `SKIP_CONF_LVL_REC_AFTERNOON`,
`SKIP_LEVEL_REJECTION_GATE`, `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`.

**Guards RETAINED** (each individually guard-tested to still BLOCK a full-send plan):
daily kill switch · per-trade risk cap (Rule 6) · PDT (Rule 7) · no-add/one-position
(Rule 4, `NOT_FLAT`) · `min_entry_premium` floor · entry-time floor/ceiling · EOD flatten ·
broker-flat verification · `SKIP_NO_LEVELS` sight-failure block · no-level-no-trade.
Plus a **min-size clamp on every entry** (`min_contracts`), so the arm trades *more often,
smaller* — never more often, same size.

**Deliberately NOT dropped:** sight failures, time gates, data-integrity, structure veto, and
the two cohort gates outside the measured package (`SKIP_RIBBON_MOMENTUM_GATE`,
`SKIP_DOJI_ENTRY_BAR`). Ship only what was tested.

---

## 3. Measured results — ALL cells, real OPRA fills

⚠️ **STRIKE PROVENANCE — the column that decides whether any of this applies.** Production
(`_full_send_plan` → `PROBE_STRIKE_TIERS`) trades **ATM (offset 0)**. The `FULL_SEND` rows were
measured at **OTM-2 (offset 2)**. Only the `FULL_SEND ATM` rows share production's strike.

| window | arm | strike | trades | fills/sess | total P&L | exp/trade | WR | worst day |
|---|---|---|---:|---:|---:|---:|---:|---:|
| full (387 sess) | BASELINE | OTM-2 | 157 | 0.406 | **+$11,294** | $71.94 | 63.7% | −$557 |
| full | FULL_SEND ⚠️*not prod strike* | OTM-2 | 332 | 0.858 | **+$3,430** | $10.33 | 38.9% | −$830 |
| full | FULL_SEND @min-size ⚠️*not prod strike* | OTM-2 | 332 | — | **−$1,010** | — | — | −$470 |
| full | **FULL_SEND ATM** *(production strike)* | **ATM** | 327 | 0.845 | **−$5,110** | −$15.63 | 41.9% | −$737 |
| full | **FULL_SEND ATM @min-size** *(production strike)* | **ATM** | 327 | — | **−$5,044** | — | — | −$753 |
| recent (51 sess) | BASELINE | OTM-2 | 41 | 0.804 | **+$4,308** | $105.08 | 63.4% | −$398 |
| recent | FULL_SEND ⚠️*not prod strike* | OTM-2 | 78 | 1.529 | **+$118** | $1.51 | 39.7% | −$830 |
| recent | FULL_SEND @min-size ⚠️*not prod strike* | OTM-2 | 78 | — | **−$734** | — | — | −$470 |
| recent | **FULL_SEND ATM** *(production strike)* | **ATM** | 79 | 1.549 | **−$1,088** | −$13.77 | 39.2% | −$588 |
| recent | **FULL_SEND ATM @min-size** *(production strike)* | **ATM** | 79 | — | **−$1,878** | — | — | −$733 |

**Min-size method:** `5 · Σ(pnlᵢ/qtyᵢ)`, per-trade, all 332 / 78 trades scaled, **0 missing a
qty** (no silent exclusion), observed qty range **3–22**. The superseded
`scale_factor = 5/mean_qty × Σpnl` gave +$1,951 / +$63 — see the correction banner at the top.

**Idle days** — the metric that answers J's actual complaint: full population **65.1% → 42.4%**;
recent **33.3% → 9.8%**. *(Measured on the OTM-2 cells; a strike change does not move selection,
so trade COUNTS carry across — only P&L does not.)*

**Pre-registered checks (recomputed on the corrected estimator):**

| check | full population | recent |
|---|---|---|
| F1 kill switch (worst day > −$1,000) | **pass** (−$470) | **pass** (−$470) |
| F2 per-trade tail ≥ baseline worst | **FAIL** (−$487.50 vs −$477) | **FAIL** (−$487.50 vs −$397.50) |
| F4 uplift ≥ 2.0× | **pass** (2.115×) | **FAIL** (1.902×) |

**TWO pre-registered checks now fail, not one.** F2 "passed" in the original write-up only
because the biased scaling shrank the worst trade; on the correct per-trade basis the full-send
book's worst min-size trade is worse than BASELINE's worst full-size trade in both windows.
A pre-registration you override on judgment is not a pre-registration — this is recorded as a
**failure carried**, not a pass.

### The ATM strike override was NOT reverted — and is deliberately KEPT

The original text of this section claimed ATM was built, measured at **+$3,430 → −$5,110**, and
**reverted**. **That claim was false on the shipped path.** The revert was applied to
`_tiers_for_arm` only, and `_full_send_plan` never calls it — it prices `PROBE_STRIKE_TIERS`
(offset 0) directly. Instrumented proof at spot 744.10, $2K equity:

```
bull_score=7  -> FULL_SEND cohort=elite_bull_level_reclaim   strike=744  (ATM)      <- ships
bull_score=11 -> ribbon_ride C (ELITE)  [normal lane]        strike=746  (OTM-2)
arm's own _tiers_for_arm table at this equity: 746 (OTM-2)
```

**DECISION: keep ATM.** ATM is precisely what lets the contract clear the UNTOUCHED $0.30
`min_entry_premium` floor that refused risky-1 on **15 of its 16** named-setup ticks on
2026-07-31 — the entire reason the arm exists. Repointing production at `_tiers_for_arm` to make
the OTM-2 measurement "honest" would be moving the trade to match a stale number; the honest fix
is to label the cell as **not applying**.

**What that costs us, stated plainly:** the `FULL_SEND ATM` rows are the only cells at
production's strike and they are **negative in every configuration** (−$5,110 raw / −$5,044
min-size full; −$1,088 / −$1,878 recent). They are *not* the live expectation either — they
apply ATM to all 327 trades, whereas live only ~17 marginal ticks per 28 days take this lane
(§4). **Net: the incremental trades this arm adds have NO valid measurement at their actual
strike. Its forward paper ledger is the evidence, and nothing else here is.**

---

## 4. The honest limitation — read this before believing the arm "fixes" anything

The A/B measured the **core engine**. But the **fleet already runs a looser perception** than
the core (`_score_peak_check` rescues cohort-vetoed ticks scoring ≥9 bull / ≥8 bear). Measured
over the 28-day bold ledger:

- **206** cohort-vetoed, named-setup ticks carrying a level
- **189 (92%)** were **already rescued** by the existing scoring-peak lane — this is exactly how
  safe-3 and risky-3 entered on 2026-07-31 at bull_score 11
- **17 (8%)** are marginal to the new lane — and **all 17** are `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`

**So the full-send lane's marginal selection effect is small**, and the A/B's 2.1× uplift is
uplift versus the CORE arms, not versus the fleet arms this arm sits beside.

And the instrument (`full_send_vs_gated.py`, run on today) names the true blocker outright:

```
  safe-3     NO_SIGNAL_FROM_PRODUCER=106, SKIP_MIN_PREMIUM_FLOOR=17, RISK_CAP=1, ENTERED=1
  risky-1    NO_SIGNAL_FROM_PRODUCER=106, SKIP_MIN_PREMIUM_FLOOR=18, RISK_CAP=1
  risky-3    NO_SIGNAL_FROM_PRODUCER=106, SKIP_MIN_PREMIUM_FLOOR=11, NOT_FLAT=5, ENTERED=2
```

**risky-1 reached the SAME `ribbon_ride C (ELITE)` ENTER plan safe-3 and risky-3 traded, and
died at `finalize()` 18 times on `premium < 0.30`.** That is a **strike-tier / premium-floor**
problem, owned by the `min_entry_premium` provenance-audit lane — not by selection. Shipping
full-send does not, on its own, make this arm trade. Said plainly rather than claimed otherwise.

---

## 5. Disposition + REVOKE

**ARMED — as an explicitly UNMEASURED forward-paper experiment, NOT a validated ship** — on
`risky-1` → `FLEET-FULLSEND-R (8G19)`, paper, `PA3W17FD8G19`, **ATM strike, min-size clamp.**

**DE-ARM (one line, byte-identical):** set `risky-1.gate_override` back to
`{"min_triggers": 2, "require_confluence_or_sequence": true}`. Producer belt-and-suspenders:
`build_shared_signal.FULL_SEND_LIVE = False`.

**Why it stays armed anyway** (the case for J to revoke or keep): paper account; every entry
min-size clamped; all six risk guards proven binding *by execution* through the real
`finalize()`; worst min-size day −$470 against a −$1,000 kill switch; one-line revert. And ATM
is the strike that clears the floor that produced 128 straight HOLDs — which is exactly what J
asked for ("get in shit and see if it works"). The measurement that settles it is the forward
paper ledger, not another SIM cell.

**KILL CRITERION (pre-committed):** de-arm if, over the first **n ≥ 10 forward sessions**, the
arm's realized paper P&L is negative *and* its fill count is not materially above the gated
arms — i.e. it is paying the cost without buying the learning rate. Re-check via
`setup/scripts/full_send_vs_gated.py --since`.

**De-arming is all-or-nothing.** The A/B measured the package of five with **no per-gate
attribution**; gate-picking on this same data is the multiple-comparisons trap. A drift guard
fails if the allowlist changes without new evidence.

**Standing caveats:** (1) the min-size expectation is **NEGATIVE** in backtest (−$1,010 full /
−$734 recent at OTM-2; −$5,044 / −$1,878 at ATM) — the "P&L-positive" leg of the original ship
rationale is **retracted**; (2) production trades **ATM** and has **no valid measurement at that
strike** (OP-16); (3) real-OPRA **SIM**, not broker fills — the forward paper ledger is the real
evidence; (4) the arm keeps its 2026-07-29 REACHABLE-TP1 `exit_patch`, so it is **not** an exit
control (disclosed confound, deliberately untouched); (5) **F2 and F4 both failed**
pre-registration; (6) at $2K equity the 50% per-trade cap **refuses any full-send entry above
$2.00 premium**, and ATM 0DTE SPY midday frequently prices above that — so the arm fires **less
often** than the 2.115× uplift figure suggests.

**Hand-off to the premium-floor lane:** risky-1's 18 daily `SKIP_MIN_PREMIUM_FLOOR` deaths are
the highest-value single fix for fleet participation — higher than anything in this lane.

---

## 6. Blast radius (mapped, not recalled)

| consumer | effect |
|---|---|
| `fleet_live.py` → `plan_all` | new lane appended **after** probe/ladder; fires only when no other lane produced an ENTER, only for an arm with `gate_override.full_send`. Every other arm byte-identical. |
| `build_shared_signal.build()` / `build_from_rows()` | `full_send` key added — **purely additive**; every existing reader ignores unknown keys (same contract as `probe`/`ladder`). Verified live: producer runs, emits the block. |
| DOJO `engine_step.py`, `test_dojo_engine_step.py`, `test_core_score_ladder.py`, `test_blind_no_levels` | **57 tests pass** |
| fleet suite | **310 pass** (was 281 pass / **3 pre-existing failures**, all stale risky-1 "control arm" assertions RED since 2026-07-29 — re-pointed at the real controls `safe-2`/`bold-2`, invariants unchanged, not weakened) |
| `backtest/replay_fleet_arms.py` | ⚠️ **reads `accounts.json` LIVE** (line 76) and keys off `gate_override.min_triggers` (line 127). risky-1 no longer sets `min_triggers`, so this historical-parity fixture now replays risky-1 without the tight override. Behaviourally correct (the arm *is* no longer tight) and it does not crash — but anyone comparing to a pre-2026-07-31 run of that harness must know risky-1's cell changed meaning. Not a guard test; not in the pytest suite. |
| live orders | none — market closed, paper only, no order placed by this work |
