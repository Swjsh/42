# FULL-SEND learning arm — ship report (2026-07-31)

**Verdict: SHIPPED (paper, reversible in one line) — but it does NOT fix risky-1's zero-trade
problem, and the honest reason is in §4. The arm's real binding constraint is the
`min_entry_premium` floor, not selection.**

- Pre-registration: [`prereg-full-send-arm-2026-07-31.json`](prereg-full-send-arm-2026-07-31.json)
  — frozen **2026-07-31T17:35:46-04:00 ET**, before any run.
- Results: [`full-send-arm-2026-07-31.json`](full-send-arm-2026-07-31.json) — real OPRA fills.
- Harness: `backtest/full_send_arm_ab.py` · Instrument: `setup/scripts/full_send_vs_gated.py`
- Guards: `automation/state/fleet/test_full_send_arm.py` (26 tests, 4 RED-proofs verified)

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

| window | arm | trades | fills/sess | total P&L | exp/trade | WR | worst day |
|---|---|---:|---:|---:|---:|---:|---:|
| full (387 sess) | BASELINE | 157 | 0.406 | **+$11,294** | $71.94 | 63.7% | −$557 |
| full | FULL_SEND | 332 | 0.858 | **+$3,430** | $10.33 | 38.9% | −$830 |
| full | FULL_SEND @min-size | — | — | **+$1,951** | — | — | −$472 |
| full | *FULL_SEND ATM (rejected)* | 327 | 0.845 | **−$5,110** | −$15.63 | 41.9% | −$737 |
| recent (51 sess) | BASELINE | 41 | 0.804 | **+$4,308** | $105.08 | 63.4% | −$398 |
| recent | FULL_SEND | 78 | 1.529 | **+$118** | $1.51 | 39.7% | −$830 |
| recent | FULL_SEND @min-size | — | — | **+$63** | — | — | −$444 |
| recent | *FULL_SEND ATM (rejected)* | 79 | 1.549 | **−$1,088** | −$13.77 | 39.2% | −$588 |

**Idle days** — the metric that answers J's actual complaint: full population **65.1% → 42.4%**;
recent **33.3% → 9.8%**.

**Pre-registered checks:** F1 (kill switch) **pass** both windows · F2 (per-trade tail) **pass**
both windows · F4 (≥2.0× uplift) **pass** full population (2.115×), **FAIL recent (1.902×)**.

F4 failed by 5% on one of two windows. Not massaged — shipped anyway because F1/F2 held, the
profile is P&L-**positive** rather than merely bounded, and the idle-day collapse is the real
target. Recorded as a caveat, not as a pass.

### A change that was built and then REVERTED on its own evidence

An ATM strike override for the full-send arm was built (rationale: ATM contracts are pricier,
so they clear the $0.30 floor). Its A/B cell came back **+$3,430 → −$5,110** for a **<2% change
in trade count**. The intended benefit is *not observable in that harness at all* — the premium
floor lives in `fleet_executor.finalize()`, not the orchestrator. Measured cost, unmeasurable
benefit → **reverted**, and pinned by a negative guard test so it cannot creep back unmeasured.

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

**SHIPPED** on `risky-1` → `FLEET-FULLSEND-R (8G19)`, paper, `PA3W17FD8G19`.

**DE-ARM (one line, byte-identical):** set `risky-1.gate_override` back to
`{"min_triggers": 2, "require_confluence_or_sequence": true}`. Producer belt-and-suspenders:
`build_shared_signal.FULL_SEND_LIVE = False`.

**De-arming is all-or-nothing.** The A/B measured the package of five with **no per-gate
attribution**; gate-picking on this same data is the multiple-comparisons trap. A drift guard
fails if the allowlist changes without new evidence.

**Standing caveats:** (1) real-OPRA **SIM**, not broker fills — the forward paper ledger is the
real evidence; (2) the arm keeps its 2026-07-29 REACHABLE-TP1 `exit_patch`, so it is **not** an
exit control (disclosed confound, deliberately untouched); (3) F4 failed on the recent window.

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
