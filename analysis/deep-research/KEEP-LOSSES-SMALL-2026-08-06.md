# KEEP LOSSES SMALL — the joint optimisation

**2026-08-06, after the close.** Clock verified this session by me, first action:
`python setup/scripts/et_clock.py` → **`2026-08-06 18:03:30 Thursday EDT, market_hours=False`**.
Analysis-only. No trading-path file touched, nothing armed, nothing pushed.

> J's ask: *"we gotta KEEP OUR LOSSES SMALL so that way our wins can stack."*
> This document answers the **joint** question: what package of the surviving levers caps a
> Wednesday-shaped day without costing Tuesday (+$3,624) or Thursday (+$1,465)?

---

## FOR J — 12 LINES MAX

- **No package caps Wednesday near −$500. The honest floor is −$710** (from −$1,935). It is a **wall**, not a tuning choice.
- **Why:** the breaker trips at **10:13**. Everything after is already stopped. What's LEFT is the first three 776C legs per arm + one safe-2 trade, all entered **09:58–10:10** — **−$710 of trades that happen before any loss-cap can know anything.**
- **The levers do NOT add.** Breaker +$1,225, CAP-3 +$653, same-bar +$202 on Wednesday. Run together: **still exactly −$710.** They block the *same trades*; the breaker just gets there first. **Never bank two.**
- **Recommended package: same-bar cooldown + CAP-3 + 4-loss halt + fleet −$600 breaker** → Wed **−$710**, Tue **+$144**, Thu **$0.00**, book **+$1,676**, **0 of 26 days harmed**.
- **What the extras buy is EVIDENCE, not Wednesday dollars.** Breaker alone = 100% one-day. Package = 73% — **+$451 outside Wednesday**, +$307 outside the whole week.
- **Premium: $0.18 of winners per $1.00 of losses removed**, binds 7 of 26 days. $347 of the $362 surrendered is **one trade** (risky-1's Wednesday put).
- 🎯 **SHIP-ELIGIBLE (1):** the **same-bar cooldown** — a **wiring gap, not a new edge**. `same_bar_cooldown_active` already lives in the fleet's own folder; only the CORE lane calls it. No knob to overfit. Tue **+$144**, 0 harmed.
- ⚠️ **BLOCKED TONIGHT:** the fleet suite is **RED** (7 tests, incl. risky-3 entry-fidelity 0/16) and not in STATUS.md. **Do not ship into a lane whose harness can't verify you.** Fix that first.
- **PREREG, do NOT ship (2):** the −$600 breaker (100% single-day — **and it does not exist**: no fleet-pooled realized surface anywhere, this is a build) and CAP-3 (91% single-day).
- **SHADOW (1):** V-d1 — best ex-week money (+$918) but BH q = 0.75, and its forward window's first session blocked nothing.
- ❌ **Dead, don't re-propose:** vwap once-per-day costs Tuesday **−$900** (same-bar fixes the same bug for **+$144**); tighter breakers (−$400) reach Wed −$565 but on an **$18 margin** — overfit.
- 📉 **The uncomfortable one:** strip this week and the 23-day book is **−$1,372**. Capping losses is right, but it is stacking on a **negative base rate**.

---

## 1. Provenance and the trust gate

Everything below is a **sequential re-walk of 208 real broker fills** over 26 ET dates
(2026-06-26 … 2026-08-06, `attribution == "engine"`, SPY options only). No exit is re-walked,
no fill re-priced, no ORACLE column anywhere.

**Base reconciles to broker truth before any joint cell was believed** — asserted in-code, and
the runner refuses to print joint results if it fails:

| check | got | want |
|---|---|---|
| book total | **+$1,782.01** | +$1,782.01 ✅ |
| positions / dates | **208 / 26** | 208 / 26 ✅ |
| Tue 2026-08-04 | **+$3,624.00** | +$3,624.00 ✅ |
| Wed 2026-08-05 | **−$1,935.00** | −$1,935.00 ✅ |
| Thu 2026-08-06 | **+$1,465.00** | +$1,465.00 ✅ |

**Then the harness reproduced all six solo cells to the dollar, across four independent lanes
that never shared code with this runner:**

| lever | total | Tue | Wed | Thu | ex-Wed | blocked | harmed | matches lane |
|---|---|---|---|---|---|---|---|---|
| `VWAP1` once/day (defect fix) | +$158 | **−$900** | +$1,058 | $0 | −$900 | 13 | 1 | Lane 4 ✅ |
| `VD1` last-5m-agrees | +$1,242 | +$179 | +$145 | $0 | +$1,097 | 32 | 1 | Lane 4 ✅ |
| `SAMEBAR` cooldown | +$497 | +$144 | +$202 | $0 | +$295 | 13 | 0 | Lane 4 ✅ |
| `CAP3` ≤3/contract | +$720 | $0 | +$653 | $0 | +$67 | 12 | 0 | Lane 4 ✅ |
| `CONSEC4` 4-loss halt | +$974 | $0 | +$768 | $0 | +$206 | 13 | 0 | Lane 1 ✅ |
| `BRK600` fleet breaker | +$1,225 | $0 | +$1,225 | $0 | $0 | 7 | 0 | Lane 1 ✅ |

Six for six. **The harness is trusted for joint cells because it is exact on solo cells.**

**Semantics (live-faithful, "taken-counted").** One chronological event stream per ET date with
**both legs on the same clock** — exits book before entries at equal timestamps, because a
broker realizes cash at the sell. A blocked position contributes $0, **never increments any
lever's counter, and never feeds the breaker**. That last clause is the entire interaction
channel and it is why summation is wrong.

---

## 2. The interaction matrix — every pair is subtractive

Wednesday dollars saved. **`interaction = joint − (solo A + solo B)`.**

| pair | joint | naive sum | **interaction** | Tue |
|---|---|---|---|---|
| VWAP1+BRK600 | +1,058 | +2,283 | **−1,225** | −900 |
| VWAP1+CONSEC4 | +1,058 | +1,826 | **−768** | −900 |
| CAP3+CONSEC4 | +653 | +1,421 | **−768** | $0 |
| CONSEC4+BRK600 | +1,225 | +1,993 | **−768** | $0 |
| VWAP1+CAP3 | +1,058 | +1,711 | **−653** | −900 |
| **CAP3+BRK600** | **+1,225** | +1,878 | **−653** | **$0** |
| VD1+CONSEC4 | +462 | +913 | **−451** | +179 |
| SAMEBAR+CONSEC4 | +519 | +970 | **−451** | +144 |
| VWAP1+SAMEBAR | +1,058 | +1,260 | **−202** | −900 |
| VD1+CAP3 | +596 | +798 | **−202** | +179 |
| **VD1+BRK600** | **+1,168** | +1,370 | **−202** | +179 |
| **SAMEBAR+CAP3** | +653 | +855 | **−202** | +144 |
| **SAMEBAR+BRK600** | **+1,225** | +1,427 | **−202** | +144 |
| VWAP1+VD1 | +1,058 | +1,203 | **−145** | −121 |
| VD1+SAMEBAR | +347 | +347 | **0** | +323 |

**14 of 15 pairs are strictly subtractive. The 15th is exactly zero. Not one pair in the entire
matrix is super-additive on Wednesday.**

Three readings that matter:

1. **`CAP3+BRK600` and `SAMEBAR+BRK600` both give exactly +$1,225 — identical to the breaker
   alone.** The entry levers contribute **literally nothing** on Wednesday once the breaker is
   present. Banking $1,225 + $653 as "$1,878 of Wednesday protection" would overstate the
   package by **53%**.
2. **`VD1+BRK600` is ANTI-additive: +$1,168, which is $57 WORSE than the breaker alone.**
   V-d1 removes losers early, the breaker's running total stays shallower, it trips later, and
   trades it would have blocked get taken. This is the mechanism, demonstrated, not theorised.
3. **The only zero-interaction pair (`VD1+SAMEBAR`) is the only pair that touches disjoint
   trades.** Disjointness is the *sole* condition under which two loss levers add.

---

## 3. Why Wednesday has a −$710 floor

The recommended package blocks 8 of Wednesday's 14 positions. Here is **everything that
survives**, and it is the whole answer:

```
09:58:05  risky-1  SPY260805C00776000  ord1   −85.00
09:58:07  risky-3  SPY260805C00776000  ord1  −136.00
10:01:58  safe-2   SPY260805C00777000  ord1   −84.00
10:06:05  risky-1  SPY260805C00776000  ord2   −65.00
10:06:13  risky-3  SPY260805C00776000  ord2   −80.00
10:10:06  risky-1  SPY260805C00776000  ord3  −100.00
10:10:07  risky-3  SPY260805C00776000  ord3  −160.00
                                      TOTAL  −710.00
```

**Every survivor is an ordinal-1/2/3 entry taken between 09:58 and 10:10 — before the breaker
latches at 10:13:06.** A loss-magnitude control is *reactive by construction*: it needs booked
losses before it can act. Wednesday's residual is precisely the losses it must eat to learn.

This also settles the attribution question cleanly. Under the full package the 10:14 entries
are charged to `SAMEBAR` and the 10:18 entries to `CAP3` — **but the breaker latched at
10:13:06 and would have blocked all four anyway.** The lever ordering changes *who gets
credit*, never the book. Reported as attribution, not as causation.

**Consequence: J's "near −$500" is unreachable from the loss-cap axis.** The remaining $210
is not in any cap. Lane 0 (Shapley, exact) and Lane 3 (walk through the live
`exit_manager.plan_exit_actions`) independently price Wednesday's exit-config lever at
**+$1,682.40 and +$1,683.25 — $0.85 apart**. That is where the rest of Wednesday lives, and
it is an exit-reachability problem, not a loss-cap problem.

---

## 4. The package search — 64 subsets + an 88-cell threshold sweep

Exhaustive over all 2⁶ subsets, plus a breaker-threshold × entry-package sweep built to test
the one genuinely new joint hypothesis: **an entry lever that blocks a Tuesday loser makes
Tuesday's drawdown shallower, which might unlock a tighter breaker.** No isolated lane could
ask this.

**Result: 32 Tue/Thu-free subsets. Zero reach Wed > −$700 with 0 days harmed.**

### 4a. The Tue/Thu-free, zero-harm frontier

| package | Wed after | total | ex-Wed | ex-week | ratio | bind |
|---|---|---|---|---|---|---|
| `BRK600` | −$710 | +$1,225 | $0 | $0 | 0.221 | 3.8% |
| `CAP3+BRK600` | −$710 | +$1,292 | +$67 | +$67 | 0.215 | 11.5% |
| `CONSEC4+BRK600` | −$710 | +$1,431 | +$206 | +$206 | 0.195 | 15.4% |
| `SAMEBAR+BRK600` | −$710 | +$1,520 | +$295 | +$151 | 0.192 | 26.9% |
| `SAMEBAR+CAP3+BRK600` | −$710 | +$1,565 | +$340 | +$196 | 0.188 | 26.9% |
| **`SAMEBAR+CAP3+CONSEC4+BRK600`** | **−$710** | **+$1,676** | **+$451** | **+$307** | **0.178** | 26.9% |

**Wednesday is pinned at −$710 in all six.** The column that moves is `ex-Wed`.

### 4b. The hypothesis was RIGHT — and it still loses

The interaction is real and large. Tuesday's fleet realized floor is **−$363**; under
`VD1+SAMEBAR` it rises to **−$40**. That genuinely unlocks tighter breakers:

| cell | Tue | Wed after | Thu | total | ex-week | harmed |
|---|---|---|---|---|---|---|
| `BRK350` alone | **−$3,347** | −$450 | $0 | −$2,478 | −$3,963 | 3 |
| `SAMEBAR+BRK350` | **+$144** | −$450 | $0 | +$1,015 | −$614 | 2 |
| `VD1+SAMEBAR+BRK400` | **+$323** | **−$565** | $0 | **+$2,707** | +$1,014 | 1 (−$15) |
| `VD1+SAMEBAR+BRK200` | +$323 | **−$221** | $0 | +$2,339 | +$302 | 2 |

`SAMEBAR` converts a Tuesday-destroying −$350 breaker (−$3,347) into a Tuesday-*positive* one
(+$144). Confirmed super-additivity on the Tuesday gate.

**And it must still be rejected, because the safety margin collapses.** Deepest fleet realized
drawdown per date, base vs `VD1+SAMEBAR`:

| date | base floor | under VD1+SAMEBAR | margin vs −$400 |
|---|---|---|---|
| 2026-07-02 (recovered +$771) | −$526.99 | −$361.00 | $39 |
| **2026-07-08** | **−$382.00** | **−$382.00** | **$18** ⚠️ |
| 2026-07-28 | −$361.00 | −$361.00 | $39 |
| 2026-06-30 | −$388.00 | −$306.00 | $94 |

**The entry levers move the binding constraint off 07-02 and onto 07-08 — a day they do not
touch at all — and the margin gets WORSE, $73 → $18.** An $18 margin on a 26-date sample,
selected from 88 swept cells, is the textbook overfit shape. Tightening from −$600 to −$400
buys $145 of Wednesday and pays for it with a 4× thinner safety margin.

**The −$600 operating point survives because its margin is $73 and its safe band is $800 wide
(−$550 … −$1,350, 33 contiguous cells, per Lane 1). That robustness — not its dollars — is why
it is the recommended threshold.**

### 4c. Answering the brief's target directly

> *"Find the MINIMAL PACKAGE that gets Wednesday better than −$700 while costing $0.00 on
> Tuesday and Thursday. If no package achieves that, say so plainly."*

**No package achieves it.** The best Tue/Thu-free, zero-harm Wednesday in 64 subsets × 11
thresholds is **−$710** — $10 short, and the shortfall is structural, not a rounding accident.
The achievable frontier, honestly:

- **−$710** at Tue $0 / Thu $0 / **0 days harmed** ← recommended
- **−$565** at Tue +$323 / Thu $0 / **1 day harmed (−$15)** — but on an $18 breaker margin and
  leaning on V-d1, the weakest-evidence lever in the set
- **−$221** at Tue +$323 / Thu $0 / **2 days harmed (−$495, −$15)**

---

## 5. Evidence-quality ranking — defect fix vs new constraint

Ranked by **evidence quality, not dollars**, exactly as the brief demands.

### 🥇 1. `SAMEBAR` — same-bar cooldown. **WIRING GAP.** Highest confidence.

Verified by me this session, not inherited:

```
automation/state/fleet/exit_actuator.py:114   def same_bar_cooldown_active(...)
callers:  setup/scripts/heartbeat_core.py:2375, :2410     ← CORE lane only
          automation/state/fleet/fleet_live.py:227        ← a COMMENT, not a call
```

**The function already lives in the fleet's own module and the fleet's placement path never
calls it.** That is not a new edge requiring a new bar — it is an unwired guard. It has **no
tunable knob** (the trigger bar must simply advance), so it cannot be overfit by threshold
choice. Tue **+$144**, Wed +$202, Thu $0, 0 of 26 days harmed, and at 40.6% Wednesday-
concentration it is the **least motivating-day-dependent** positive cell measured anywhere.

**Honest debit:** Lane 4 discloses it is **POST-HOC** — written after the pre-registered
once-per-day cell failed. Its own lane capped it at PREREG for that reason and **I am not
overriding that cap to manufacture a ship.** Lane 5's reviewer also found its "0 days harmed"
is join-dependent (under a coarser `(arm,date)` key it harms 2026-07-21 by −$18). Tue +$144 and
Wed +$202 hold under both keyings.

### 🥈 2. `VWAP1` — once-per-day. **THE ONLY TRUE DEFECT FIX. And it fails as a loss lever.**

This is the genuine restoration of a validated contract (`_fired_today` in
`vwap_continuation_watcher.py:266` resets every 60s because the fleet producer relaunches in a
fresh process; validated at 1 entry/day, n=153, +$38.3/trade). The brief called it the
strongest candidate in the workflow.

**It costs Tuesday −$900** — 9× the −$100 hard gate — and the family loses money live in *both*
configurations (−$558 as-run, −$400 restored) across 17 fills on 2 dates.

**The synthesis point:** `SAMEBAR` and `VWAP1` are **two remedies for the same underlying
defect** — the fleet lane has no re-entry guard at all. One costs $900 of Tuesday; the other
*makes* $144. **Ship the narrow one.** Keep the provenance argument alive as hygiene (the engine
should not trade outside its validated population), but the number any provenance case must now
beat is **−$900**, and same-bar beats it by $1,044.

### 🥉 3. `BRK600` — fleet realized day breaker. **NEW CONSTRAINT.** Best mechanism, worst concentration.

Two independent supports: a **mechanical boundary argument** ($73 margin over the deepest
recovering-day drawdown; $800-wide safe band) and an **independent 141-traded-day replay** where
the same rule is net-positive at every cap −$200…−$575 and harms **zero** days.

**Three debits, all load-bearing:**
- **Leave-one-day-out = 100.0%.** Remove 2026-08-05 and the book benefit is exactly **$0.00**
  across 25 dates. Worse concentration than CAP-3's disclosed 91%.
- **At its own threshold the OOS population contains zero events** — the 391-day replay blocks
  **0 trades at −$600**. It validates a *mechanism* at −$200 on a single arm; it cannot validate
  a fleet threshold, and it structurally contains no re-entry-spiral shape.
- **It does not exist.** My grep for `fleet_realized|pooled_pnl|fleet_pnl|realized_today|
  fleet_day_loss` across `automation/state/fleet/` and `setup/scripts/` returns **nothing**, and
  live `daily_loss_guard.py` is **per-account and EQUITY-based** (`--account safe|bold`). This
  is a **new cross-account realized-P&L aggregator polling 5 broker accounts every tick plus a
  shared latch** — a build with its own failure modes (partial read → false trip), not a config
  flip. Anyone costing this as "re-parameterise Rule 5" is costing it wrong.

**And the basis must change.** Lane 1's most important disclosure argues against its own
candidate: priced on 27,927 real OPRA marks, the same −$600 breaker on an **equity** basis was
**ARMED on Thursday**, the +$1,465 day, from 10:57 ET (worst mark −$711). It cost $0 only
because all three winners were already open. **Whatever Rule 5 becomes, this instrument must
read REALIZED P&L.** An equity basis punishes exactly the chandelier profit-lock the engine is
built around.

### 4. `CONSEC4` — 4-consecutive-loser halt. **NEW CONSTRAINT.** Thin but clean.

+$206 ex-Wednesday across three independent dates (06-30 +$44, 07-02 +$132, 07-20 +$30), 3-for-3
positive. **Total evidence: 4 dates.** Fires **0 times in 141 replay days** (one arm averaging
1.35 trades/day essentially never takes 4 losers), so it is single-population forever. N=3 is
separately **rejected** — it costs Tuesday −$1,093 by halting risky-3 immediately before +$524
and +$788.

### 5. `CAP3` — ≤3 per (arm, date, contract). **NEW CONSTRAINT.** Does-no-harm only.

8/8 gates, 12 blocked of which exactly one winner worth +$6, 0 days harmed — reproduced here
from a fourth independent code path (+$720 / Tue $0 / Wed +$653 / ex-Wed +$67). But **90.7% of
the benefit is the motivating day**, BH q = 0.796, and the 391-day population **structurally
cannot test it** (never more than 2 entries per contract per day → NO-OP on all 141 days).
Ordinal ladder sign-flips between 3rd (+$107) and 4th (−$257), which is why 3 and not 2.

### 6. `VD1` — last closed 5m bar must agree. **SHADOW.** Best money, weakest evidence.

Best ex-week number in the whole set (+$918) and blocked-cohort WR 3.0% vs 18.3% population.
But: raw within-day permutation p = 0.116, **Bonferroni ×17 = 1.000, BH q = 0.746** against a
q ≤ 0.10 bar; **harms a day** (2026-07-28, −$15); near-inert on population B (2 of 191 blocked,
p = 0.497); and **session 1 of its own frozen 10-session forward window blocked zero entries**.
Its window is uninformative after one day. **EXTEND, do not judge, do not arm.**

---

## 6. The premium — what this insurance costs

J is buying left-tail insurance and is entitled to the price.

**Recommended package `SAMEBAR+CAP3+CONSEC4+BRK600`:**

| metric | value |
|---|---|
| Winners surrendered | **$362** |
| Losses removed | **$2,038** |
| **Exchange rate** | **$0.178 of upside per $1.00 of loss prevented** |
| Net | **+$1,676** over 26 dates |
| **Bind frequency** | **7 of 26 dates (26.9%)**; breaker itself latches on only **2** (07-27, 08-05), **both losing days, never once on a green day** |
| Concentration | 73.1% of benefit from 2026-08-05 |
| Ex-Wednesday | **+$451** over 25 dates (≈ $18/day) |
| Ex-week | **+$307** over 23 dates |

**The single most useful number here: $347 of the $362 surrendered is ONE trade** — risky-1's
Wednesday 772P winner, which the breaker forfeits. **Outside Wednesday the entire package
surrenders $15 of winners.** At $0.18 on the dollar this is cheap insurance by any standard;
what it is *not* is well-evidenced, because 73% of the measured payoff is the event that
motivated buying it.

**Comparator premiums, for calibration:** breaker alone $0.221 · CAP-3 alone $0.008 · same-bar
alone $0.029 · and from the rejected pile, fleet −$250 at **$1.88** and per-arm retrace-20% at
**$11.63** — those are strategy changes in a guard's costume, not insurance.

---

## 7. SHIP / PREREG / SHADOW — with kill criteria and one-line reverts

### ⚠️ Blocker that gates all of it

**The fleet test suite is RED and unowned.** Re-run by me this session:

```
backtest/tests/run_safety_gate.py            → 59 passed, "PASS -- curated safety gate green"
pytest backtest/tests/test_sizing_deadlock_wiring.py
  → FAILED test_fleet_sizing_miss_is_distinguishable_from_deadlock  (- RISK_CAP / + ALLOW)
     1 failed, 6 passed
```

Two prior reviewers independently counted **7 fleet failures** (this one, `test_replay_fleet_arms`
×3 — including **risky-3 entry-fidelity matched 0/16** — and `test_fleet_arm_replay` anchor-pass-rate
×3). **risky-3 is the arm that produced 75% of Wednesday.** None of these appears in STATUS.md
`## Known broken`, which is itself an OP-25/C7 silent-failure gap.

**Shipping a fleet placement-path change while the fleet replay harness cannot verify that lane
is the exact C7 shape this repo keeps getting burned by. Triage the 7 REDs first.** That is the
highest-value next action in this whole document, and it is bounded.

### The ladder

| # | Item | Verdict | Gate to clear | Kill criterion | One-line revert |
|---|---|---|---|---|---|
| 1 | **`SAMEBAR`** fleet same-bar cooldown | **SHIP-ELIGIBLE** (after the RED triage) | frozen forward prereg committed **before** the wiring commit (`git merge-base --is-ancestor`) + guard test + **RED-proof** (mutate source, prove RED, restore byte-identical, prove green) + REVOKE log | any single session where it blocks an entry that would have been a **winner > +$150**, or 2 consecutive weeks net-negative attributable | remove the `same_bar_cooldown_active` call from the fleet placement path (1 call site) |
| 2 | **`BRK600`** fleet realized breaker | **PREREG ONLY — do not build yet** | forward prereg with the threshold **frozen before** the confirming run; must read **REALIZED**, never equity; latching; blocks **new entries only**, never force-liquidates | trips on any day that then ends **green**; or fleet realized dips past −$600 and recovers (never seen in 26 dates, nearest miss $73) | `fleet_breaker_enabled: false` in params (the flag must exist before the logic does) |
| 3 | **`CAP3`** ≤3/(arm,date,contract) | **PREREG** | forward clock, ≥ 10 sessions with ≥ 8 blocked entries before judging | any blocked 4th entry that would have returned > +$300; or ex-motivating-day total goes negative | `max_entries_per_contract: 99` |
| 4 | **`CONSEC4`** 4-loss arm halt | **PREREG** (optional leg) | same forward clock; label post-hoc where composed with the breaker | halts an arm before a session it would have finished green, twice | `consec_loss_halt_n: 99` |
| 5 | **`VD1`** last-5m-agrees | **SHADOW — EXTEND** | its frozen 10-session window; **session 1 blocked zero entries**, so F3 (n_blocked ≥ 8) is untouched | BH q stays > 0.10 at window close | already shadow — nothing to revert |
| 6 | **`VWAP1`** once-per-day | **DO NOT SHIP as a loss lever** | — | — | superseded by #1 for the same defect |

**Nothing in this document was armed, and no trading-path file was touched.** Item 1 is the
only thing that should move tonight, and only behind the RED triage.

---

## 8. What I did NOT test — and what would settle it

1. **Any exit-side lever, jointly.** Every cell here changes *whether an entry is taken*, never
   how a position exits. The **$210 between −$710 and J's −$500 target lives entirely in the
   exit config** (Lane 0 Shapley 68.9%; two independent methods agree to $0.85 on +$1,682/+$1,683).
   **Settle it with:** a pre-registered TP1-reachability A/B routed through
   `exit_manager.plan_exit_actions` — specifically whether the ribbon_ride registry's +100% TP1
   is reachable at all (on Wednesday's put, TP1 sat at 3.30/3.26 while the ask peaked 2.69/2.76;
   risky-1's `exit_patch` at +50% was the **only** one that fired). **This is the single highest-
   value untested lane and it is where the rest of Wednesday is.**
2. **Joint effects on the 391-day population.** Impossible, not skipped: the replay is one arm at
   qty 3, so CAP-3, same-bar, once-per-day and CONSEC4 are all structural NO-OPs, and it has no
   fleet to pool. **Settle it with:** a genuine multi-arm replay, which does not exist today.
3. **Capital redeployment.** A blocked entry frees buying power the counterfactual never
   redeploys. Every number here is therefore a **lower bound on cost** and a fair bound on benefit.
4. **The breaker's live failure modes.** A 5-account polling aggregator can partial-read → false
   trip, or fail-open → no trip. Not modelled. **Settle it with:** a shadow build that logs the
   trip decision for 10 sessions without acting.
5. **Interaction with the equity-based Rule 5 that actually exists.** I modelled the realized
   breaker as if it were the only day-level control; live, `daily_loss_guard.py` is still running
   per-account on equity. Two day-level controls on different bases is its own blast radius.
6. **Anything about sizing, stop width, catastrophe-cap width, or fleet concentration.** Lanes 2,
   3 and 5 returned NULL / GRAVEYARD_COLLISION and I did not re-litigate them. Notably Lane 2's
   hard result stands: **even the Rule-6 floor (qty 3 everywhere) leaves Wednesday at −$968.55
   while costing $1,602 across Tue+Thu.** Sizing cannot do this job.

---

## 9. Caveats — read before quoting any number

- **The single-day concentration is the dominant weakness of the entire package.** Breaker
  LODO = 100.0%; package = 73.1%. This clears a **does-no-harm** bar on two populations. It
  clears an **evidence** bar on neither. That is why nothing here is a SHIP except the wiring fix.
- **88 sweep cells + 64 subsets were scored against a 26-date book containing exactly ONE
  Wednesday.** The best-looking cell is selected in-sample by construction. Only the *mechanical
  margin argument* (§4b) and the independent 141-day replay carry weight — never the ranking.
- **The −$710 floor and the $18-margin result are the two most robust findings here**, because
  both are constraints rather than optima: they are arithmetic on real fills with no free
  parameters, and they get *stronger*, not weaker, under adversarial re-derivation.
- **Lever ordering affects attribution, not results.** The runner evaluates in a fixed order;
  every "blocked_by" label is attribution over a chosen basis, stated, not hidden.
- **All P&L here is SPY-options-only** (Wed −$1,935.00, Tue +$3,624.00, Thu +$1,465.00). The
  brief's all-in figures (−$1,943.66 / +$3,617.19 / +$1,460.80) include crypto-twin residual.
  Both correct, different scopes — **never mix them in one column.**
- **The book includes safe-1, a retired arm** (last fill 2026-07-09). Dollars were real; its
  share is not live exposure.
- **Lane 5's reviewer found `SAMEBAR`'s 0-days-harmed is join-dependent** (coarser key → harms
  2026-07-21 by −$18, +$479/14 blocked vs +$497/13). Tue +$144 / Wed +$202 hold under both.
- **Inherited defects not fixed here, still open for the next caller:**
  `backtest/tools/_option_bars_1min_cache.py:48` raises `KeyError` on three 2026-08-05 highres
  files carrying a UTC `timestamp` column (Lane 2); `exit_shape_parity_study.replay_position`'s
  structure-stop degradation plus core-row `trigger_level_exact = null` (Lane 5); and Lane 0's
  claimed "$294 unmatched position" artifact, which Lane 1's reviewer showed is itself an
  artifact of dropping manual-attribution fills.
- **Graveyard check run before any number was computed — no collision.** Nothing here is stop
  width in either direction, stopped-then-paid, pre-TP1 profit-lock arming
  (`profit_lock_arm_scope="full"`), hold-longer, take-profit-earlier, level-target exits,
  min-contracts, a per-setup TIME cooldown, or a regime standdown. **No cell in this document
  alters any exit**; every lever decides only whether an entry is taken, and every counterfactual
  is deletion arithmetic on real broker fills. The breaker is reactive to already-booked realized
  loss and **requires no forecast** — which is what separates it from the regime standdown whose
  classifier failed at 20.9% accuracy on 2026-08-02.
- **`SAMEBAR` is POST-HOC** and its lane capped it at PREREG. I report it as the best candidate
  and as ship-*eligible* on the strength of being an unwired existing guard — **not** as
  pre-registered evidence.

---

## Artifacts

| path | what |
|---|---|
| `analysis/deep-research/KEEP-LOSSES-SMALL-2026-08-06.md` | this document |
| `analysis/deep-research/KEEP-LOSSES-SMALL-2026-08-06.json` | all 64 subsets, 88 sweep cells, pairwise matrix, frontier, LODO |
| `backtest/tools/joint_optimiser_2026_08_06.py` | the sequential joint walker (trust gate refuses to print if base ≠ broker truth) |

**Upstream lanes:** `LOSS-ANATOMY-2026-08-06.md` · `LEVER-DAILY-CAP-2026-08-06.md` ·
`LEVER-SIZING-2026-08-06.md` · `LEVER-CATCAP-2026-08-06.md` ·
`LEVER-ENTRY-COUNT-2026-08-06.md` · `LEVER-CORRELATION-2026-08-06.md`

**Checks run fresh this session:** `et_clock.py` → 18:03:30 EDT market_hours=False ·
base reconciliation 6/6 · solo-cell reproduction 6/6 across four lanes ·
`run_safety_gate.py` → 59 passed PASS · `test_sizing_deadlock_wiring.py` → **1 failed**, 6 passed ·
greps confirming no fleet-pooled realized surface and `same_bar_cooldown_active` called only by
the core lane.
