# EOD FULL REVIEW — Wednesday 2026-08-05

**Synthesis of 5 adversarially-reviewed lenses + this session's own independent re-derivation.**
Answers J's question, in J's order: *"why do we get in trades and then get stopped out? were they going to
be good trades? do we need better entries? do we need larger stops? audit this fully."*

---

## ⏰ CLOCK CORRECTION — READ FIRST

The task brief that commissioned every lens said **"PRE-DAWN (~03:40 ET), market CLOSED."** That was
**FALSE at execution.** `python setup/scripts/et_clock.py` returns:

```
2026-08-06 12:20:30 Thursday EDT
market_hours=True
```

**Four of five lenses independently caught it and went read-only.** So did this synthesis. **No live
trading-path file was modified by any lens or by me.** Everything shipped is `analysis/`, `backtest/tests/`,
or already-executing-on-disk code that was merely committed.

Consequence: an interactive session ran inside J's 09:30–15:55 no-session window, on the shared Max pool.
Flagged, not hidden.

**Bonus: because it is Thursday midday and not Wednesday pre-dawn, I have a THIRD day of live evidence the
lenses could not see.** It changes one of their conclusions. See §7.

---

## LINE 1 — THE ONE SENTENCE

> ### **Wednesday cost −$1,943.66 because the engine bought the day's high ten times on one call contract for −$1,279 — and 84% of that was the RE-ENTRY COUNT, not the stop width — then let a +63% put round-trip to −50% on the two arms whose take-profit was configured at +100%, for another −$919.**

The whole day is three events and nothing else:

| Event | Contract | Arms | P&L | Share |
|---|---|---|---|---|
| **A — the spiral** | `SPY260805C00776000` ×10 round trips | risky-1, risky-3 | **−$1,279** | 66% |
| **A′ — the sixth call** | `SPY260805C00777000` | safe-2 | **−$84** | 4% |
| **B — the put divergence** | `SPY260805P00772000` | all three | **−$572 net** (+347 / −664 / −255) | 30% |
| SPY options total | | | **−$1,935.00** | |
| crypto twin residual | | | −$8.66 | |
| **DAY** | | | **−$1,943.66** | |

Broker-verified, per arm: safe-2 −339.76 · bold-2 −0.54 · safe-3 −0.68 · risky-1 −140.39 · risky-3 −1,462.29.

---

## 1. WHY DO WE GET IN TRADES AND THEN GET STOPPED OUT?

**VERDICT: because on 08-05 we entered a location that never paid, and then re-entered it four more times.
The stop did what it was told; the stop is not the defect.**

The mechanism, end to end, verified in code and in the live ledger:

1. **`vwap_continuation` fires once per day BY DESIGN** — `detect_vwap_continuation_setup` enforces it with
   the module-global `_fired_today`. Its validated cell (n=153, +$38.3/trade) was measured at **one entry
   per day**.
2. **The fleet producer runs in a FRESH PROCESS every 60 seconds.** `run-fleet-executor.ps1` relaunches
   `build_shared_signal.py` each tick, so the module global resets each tick. RED-proofed on 08-05's real
   bars: **1 fire same-process vs 3 fires with a reload per tick** (live saw 5 because the producer also
   reads the in-progress bar).
3. **The CORE lane has a churn guard; the FLEET lane does not.** Core persists a same-bar cooldown
   (`heartbeat_core._route_extra_setups → exit_actuator.same_bar_cooldown_active → <arm>/extra-setup-cooldown.json`).
   `same_bar_cooldown_active` appears in `fleet_live.py` **only inside a comment.** That is exactly why
   safe-2 took ONE extra-setup entry and risky-1/risky-3 took FIVE each.
4. **`vwap_continuation` declares NO `stop_mode`**, so `ExitShape.stop_mode` defaults to `"premium"` and the
   −6% premium stop is the **declared primary stop**, ported deliberately 2026-07-09 (commit `b1250556`,
   STOP-B ship 2) as the "full validated core cell" — 5/5 OP-22 gates PASS on n=149 real OPRA fills.

**⚠️ CORRECTION TO THE COMMISSIONING BRIEF (load-bearing).** The brief carried: *"Continuation setups have
`trigger_level=None` ALWAYS, so their `stop_mode='structure'` patch is a guaranteed NO-OP."* For
`vwap_continuation` that is **wrong in the way that matters** — there is no structure patch to be a no-op.
The −6% is not a silent fallback from a broken patch; it is a validated knob meeting an adversarial day.
LENS 1 caught an error in its own tasking. Two lenses independently confirmed it in `strategies.py:122` +
`exit_manager.py:178`.

So the answer to J's literal question: **we get stopped out because a signal that is authorised to speak
once got to speak five times, into a location with no demand under it.** The −6% stop converted one bad
idea into ten round trips. It did not create the bad idea.

---

## 2. WERE THEY GOING TO BE GOOD TRADES?

**VERDICT: NO. Not one of the eleven call entries was ever going to pay. The put was — and two arms
gave it back.**

### Event A — the 776C spiral: unambiguously NOT good trades

Real OPRA, independently pulled twice (two different sessions, two different price bases, 0.002% delta):

- **The contract never traded at ANY of the ten entry prices again after the last stop-out at 10:20.**
  Post-10:20 maximum was an intrabar **$2.00** print at 10:25 — **six cents below the cheapest of the five
  entries ($2.06)**. Then 0.88 @ 11:00 → 0.35 @ 11:30 → 0.07 @ 13:30 → **settled $0.01**
  (380,345 contracts / 50,969 prints).
- **MFE from fill to exit on all ten round trips:** 0.0% / 1.5% / 2.2% / 2.6% / 4.5% / 5.0% / 6.1% / 6.1% /
  10.5% / 11.5%. **The tightest take-profit configured anywhere in the live book is +30%.** Zero of ten ever
  printed a payable profit.
- **SPY's session high (776.81/776.85) printed in the FIRST MINUTE** (t_high = 0.013 of the session). The
  day gapped up 0.60%, topped immediately, closed on the low (close_loc 0.034). The bull signal fired
  **09:58–10:19 — 19 to 39 minutes AFTER the high was already in** — and every entry sat 0.23–0.88 below it.
- **776.85 was in the engine's own `levels_active` list.** It bought its own supply zone, five times.

Against **J's market philosophy**: zone identified ✅ · waited for the return ❌ · structure shift at the
zone ❌ (zero confirmed BOS/CHoCH on 5m AND 1m before any call entry) · never chase candles ❌ **VIOLATED**
(every entry was into a green 1-minute thrust).

### Event A′ — safe-2's 777C: also not a good trade

MFE 23.6%, below the +30% payable bar. Note it was **not** `vwap_continuation` — it was
`vwap_reclaim_failed_break`, and that detector **did** supply a real structure stop at 774.40. The position
still exited −17.4% with SPY at 776.23, i.e. **1.83 above its own structure stop.** The structure stop never
bound. The premium stop fired first, again.

### Event B — the put: a GOOD trade that two arms did not collect

`SPY260805P00772000`, bought by three arms within one minute at 11:48–11:49. Ask peaked
**2.68 / 2.69 / 2.76 at 12:09** (+58.6% / +63.0% / +69.3%). risky-1 took +$347. risky-3 took −$664. safe-2
took −$255. **Same contract, same minute, opposite outcomes.** Full root cause in §5.

**Summary of §2:** 11 of 14 entries were structurally dead on arrival. 3 were live. We collected on 1.

---

## 3. DO WE NEED LARGER STOPS?

> ### ❌ **NO. This is the cleanest verdict in the audit, and it is not close.** A wider stop loses more at every entry cap on 08-05's own archetype and on the 391-day population. **NO STOP-WIDTH CHANGE SHIPS — IN EITHER DIRECTION.**

### 3a. The day-level counterfactual

776C never recovered (§2). There was nothing on the other side of a wider stop to wait for. **The five
stop-outs were the only thing limiting the damage.** The **−50% catastrophe-only cell is the single WORST
cell in both arms** — risky-1 −$643 vs −$535 live; risky-3 −$1,029 vs −$856 live, **$281 worse combined
than what actually happened.**

### 3b. The joint stop × entry-cap grid — the table that answers the question

Combined both arms, sequential one-position-at-a-time walk, real OPRA, re-entry minutes taken from the
engine's own NOT_FLAT ledger rows:

| stop \ entries | cap 1 | cap 2 | cap 3 | **cap 5 (LIVE)** |
|---|---|---|---|---|
| **−6% (LIVE)** | **−205** | −374 | −613 | **−1,196** |
| −10% | −395 | −733 | −1,162 | −1,162 |
| −15% | −616 | −1,240 | −1,240 | −1,240 |
| −25% | −839 | −839 | −839 | −839 |
| −50% | −1,643 | −1,643 | −1,643 | −1,643 |

*(Modelled. Broker truth at −6% × cap5 = −$1,279; the grid calibrates within +$25 / +$58 per arm.)*

**Axis decomposition — this is the whole finding:**
- Hold the stop at −6%, cap entries at 1 → **saves $991.**
- Hold entries at 5, widen to −15% → **costs $44.**
- **84% of the 776C loss was re-entry count** (precisely 82.9% = 991/1196; LENS 1's "84%" is rounded up).

**⚠️ HONEST CORRECTION TO LENS 1'S OWN PROSE.** LENS 1's headline says *"a wider stop loses MORE in every
cell"* and *"monotone in BOTH directions."* **Its own published grid contradicts that** — read the cap5
column: −25% (−839) beats −6% (−1,196) by $357, and −10% beats it by $34. **Monotonicity holds at cap1
only.** Its shipped guard `test_widening_the_stop_is_monotonically_worse_at_every_entry_cap` loops
`for cap in ("cap1",)` — a one-element tuple — so it passes only because cap1 is the sole monotone column,
while its name claims every cap.

**Does that overturn the verdict? No — and here is why, stated on the merits rather than by assertion:**
1. The −25% cell's apparent win is a **one-cent knife edge**. Monte-Carlo over the fitted quote noise gives
   p05 of −611 / −977 per arm (≈ −1,588 combined) — **worse than the −6% cell it appears to beat.** It wins
   only because the 10:20 bid landed a hair under its stop; nudge three cents and it holds into the collapse.
2. An **independent re-derivation on a different price basis** (intrabar OPRA low + fill-at-stop, vs minute-
   close bid + fill edge) puts −25% × cap5 at **−1,504 vs −6% × cap5 at −910** — decisively worse.
3. The archetype and population evidence below is monotone and does not depend on the n=1 grid at all.

**LENS 1's verdict survives; its prose overstates its own table. Both are now on the record.**

### 3c. The sequential-walk caveat (why the grid is honest and where it is not)

- ✅ `simulate()` is a **genuine sequential one-position-at-a-time walk** — no recombination. A wider stop
  correctly **suppresses** later re-entries rather than double-counting them. Verified by the reviewer.
- ✅ No look-ahead in the reconstructed VWAP invalidation (bar must close first).
- ⚠️ The **25-day book grid's** re-entry candidates are the wave's OWN observed entry timestamps, so a wide
  stop that exits after the last observed entry **loses** that re-entry rather than shifting it later. That
  **flatters wide stops.** This is why the single-entry sub-population (n=116, no re-entry interaction) is
  reported separately as the clean read.
- ⚠️ **An artifact was caught and killed before reporting** (recorded so it is not re-made): the first draft
  of the population tool hand-rolled the exit loop with no TP1 and no runner. Every winner rode to the 15:50
  flatten and the "−6% LIVE" cell printed **+$12,115 against broker truth +$317 — a 38× artifact.** Rebuilt
  on the live `plan_exit_actions` core. Disclosed in the tool docstring, the report, and the JSON.
- ⚠️ The chart/structure cell for 776C is a **RECONSTRUCTION**, labelled as one everywhere — the live setup
  carried `trigger_level=None`, so no such invalidation level existed in production.

### 3d. The 391-day check — the population says the same thing, harder

191 trades, 141 days, 2025-01-02 → 2026-07-22, re-walked through the **live** `exit_manager.plan_exit_actions`.
**Harness validated EXACTLY:** the −20% cell IS the live `ribbon_ride` `premium_stop_pct` and reproduces the
repo's frozen published baseline to the cent (**+4,808.75 on 191 trades**).

| stop | TOTAL | trend_like | chop_like | **gap-fade (08-05's own, n=30)** | gap-go (n=37) | WR |
|---|---|---|---|---|---|---|
| **−6%** | **+8,036** | +3,466 | **+4,504** | **−120** | +2,871 | .246 |
| −10% | +6,948 | +3,423 | +3,459 | −367 | +3,082 | .257 |
| −12% | +6,107 | +3,201 | +2,840 | −423 | +2,966 | .262 |
| −15% | +6,153 | +4,001 | +2,087 | −596 | +2,791 | .283 |
| **−20% (LIVE ribbon)** | +4,809 | +3,903 | +840 | −884 | +2,911 | .293 |
| −25% | +4,060 | +3,444 | +550 | −1,173 | +2,670 | .304 |
| **−50%** | **+2,176** | **+4,534** | **−2,423** | **−2,704** | **+3,686** | .356 |

Read the gap-fade column: **monotone, −$120 → −$2,704, 22× worse.** Read trend_like vs chop_like: they move
in **opposite directions.** That is the regime effect, clean, on 391 days.

### 3e. And I tested the OPPOSITE move, and rejected that too

Tightening globally from the live −20% to −6% is worth **+$3,227** aggregate, robust to drop-best-5
(+$2,543), 94 improved / 9 worsened, paired t = 2.72. **That looks shippable until you split by window:**

| window | delta |
|---|---|
| 2025 H1 | +$1,443 |
| 2025 H2 | +$1,641 |
| 2026 Q1 | +$128 |
| **2026 May onward (n=49)** | **+$15** |

The entire edge is pre-2026. Per J's standing **recency-over-aggregate** directive this fails the bar.
**Rejected on evidence, not deferred.**

**§3 bottom line: the stop is not the problem. Do not touch it. The one number J should keep is
−$205 vs −$1,279 — that is the gap between the best achievable outcome on that wave and what happened, and
the entire gap is entry count.**

---

## 4. DO WE NEED BETTER ENTRIES?

> ### ⚠️ **YES on location — 70.4% of the loss was entry-side and unsaveable by any exit rule. But NO on filters: every entry FILTER tested fails its discriminating test.** The fixable entry defect is a broken contract, not a missing knob.

### 4a. The split, as a number

Method: a trade is **ENTRY-side** if its real-OPRA MFE from fill to the arm's own exit **never reached a
payable profit** (bar = **+30%**, the tightest TP1 configured anywhere in the live book).

| bucket | n | actual | best executable | recoverable |
|---|---|---|---|---|
| **A — ENTRY-side: the tape never paid +30%** | 11 | **−$1,363** | −$1,363 | **$0** |
| **B — CONFIG-side: tape paid, but the arm's OWN TP1 was unreachable** | 1 | −$664 | +$163.50 | $827.50 |
| **C — EXIT-side: TP1 reachable and missed** | 2 | +$92 | +$470.30 | $378.30 |
| | | **−$1,935** | **−$729.20** | **$1,205.80** |

> ## **ENTRY-side = 70.4% of the day. EXIT + CONFIG = 29.6%.**
> Executable fixes were worth **$1,205.80 (62.3% of the day)** — which would have made Wednesday **−$729.20**
> instead of −$1,935.
> **ORACLE bound (LABEL ONLY, never executable): +$2,601.**

**⚠️ DISCLOSED DEVIATION.** The frozen prereg defined the split against *"that strategy's OWN TP1."* Under
that literal rule, risky-3's put is **ENTRY-side** and the headline becomes **104.8% entry-side, −4.8%
exit-side.** The report used a uniform +30% bar plus a post-hoc third bucket. **The deviation is
conservative on the headline** (it weakens the entry-side thesis) but it **inflates the companion
"$1,205.80 recoverable"** figure by folding a config counterfactual into an exit-execution total.
**Pure exit-EXECUTION recoverable is $378.30 (19.6% of the day).** Both framings on the record; the reviewer
found this and it was not fully disclosed in the source artifact.

### 4b. Every entry FILTER tested fails its discriminating test

17 pre-registered cells, frozen and committed **before** the runner existed (`b9cd7a6e`, git-provable).
Population: 230 live entry events / 286 FIFO round trips / 25 live days / net **+$317**
(**ex-08-04: −$3,307** — the record day is the book).

The killer test: a **within-day permutation** — hold each day's block COUNT fixed, randomise WHICH entries
inside that day get blocked, 20,000 draws. It asks *"did the rule pick the bad ENTRY?"* rather than *"did it
sit out a bad DAY?"*

| cell | delta (25d) | 08-04 | 08-05 | p (within-day) | verdict |
|---|---|---|---|---|---|
| **V-d1** last closed 5m bar closed AGAINST | **+$1,242** | +$179 | +$145 | **0.145** | shadow only |
| V-d2 | — | — | — | 0.102 | shadow only |
| V-cp2 | — | — | — | 0.255 | reject |
| V-e3 no 1m structure event (**POST-HOC**) | +$2,357 | +$179 | +$1,363 | **0.063** | forward prereg only |
| **V-b1/b2/b3 level proximity ×2 bases** | — | — | — | — | **ALL 6 REJECT** |

**Nothing clears p ≤ 0.10 except the post-hoc cell.** Most of the apparent entry-filter edge is *"sat out a
bad day,"* not *"picked the bad entry."* And "levels are zones" is right as a description of the market but
**loses money as an entry gate on this population.**

**Brief variant (c) is a NULL on this day** and is reported as one rather than reinterpreted: the prior-day
high (773.41) sat **2.56–2.78 BELOW every entry.** The binding supply was the **session** high.

**Brief variant (a) gates on the wrong property.** Bucketing all 230 entries by what
`market_structure.analyze_structure` saw on closed 5m bars strictly before the fill:

| structure bucket | n | P&L | WR |
|---|---|---|---|
| structure AGREES | 120 | +$344 | — |
| structure **DISAGREES** | 18 | **+$559** | 27.8% ← the best cohort in the book |
| **NO structure event at all** | 38 | **−$1,366** | 10.5% ← the killer |
| blind (<8 closed bars) | 54 | +$780 | — |

Requiring agreement throws away the best cohort. And a 5m structure gate is **blind for 23% of all entries**
(every fill 09:30–10:06, before 8 closed bars exist) — it **abstained on the first six 776C entries.**

### 4c. So what IS the entry fix?

**Not a filter. A contract.** The live path takes 5 entries where the validated cell authorises 1 (§1).
Restoring that **adds no parameter** — it restores the cell the engine claims to be running.

**But I will not oversell it: its forward P&L is NOT established, and it has a real chance of costing
money.** On 08-04 every re-entry-cooldown cell lost ($456–$1,124), and one of that day's late re-entries
became the trade of the day. **Restoring the contract is a provenance fix with an unmeasured cost.** That is
stated, not hedged around. See §7 for the narrower guard that IS measured.

---

## 5. THE PUT — ONE TRADE, THREE OUTCOMES

> ### ✅ **ROOT CAUSE: TP1 was armed and worked CORRECTLY on all three arms. It did not fire on risky-3 and safe-2 because their armed TP1 was +100% (3.30 / 3.26) and the put topped at +63% / +69%. The trade was decided by ONE CONFIG KEY.**

### 5a. The brief's premise was wrong, and the wrong premise came from a logging bug

The brief asked: *"risky-3 entered at 1.65 and the put reached 2.62 (+59%). A +40% TP1 sits at ~2.31. WHY
did risky-3 never fire TP1?"*

**There was no +40% TP1 on this trade.** Exit shapes are **per-STRATEGY, not per-arm.** +40% is
`vwap_continuation`'s cell (the 776C shape). risky-3's `BEARISH_REJECTION_RIDE_THE_RIBBON` cell is **+100%**,
and the 11:48 fleet placement row logs `tp1_premium_pct=1.0, tp=3.4` verbatim.

**Where the wrong number came from — NEW DEFECT A, `CORE-TP1-DISPLAY-DIVERGENCE`** (HIGH visibility, ZERO
money): safe-2's exec row **journaled `tp=2.50` while its armed TP1 was 3.26** — a 30% understatement.
`heartbeat_core.py:2049-2052` computes the displayed `tp` from `params.json` (0.5) while `:2224-2230` arms
from the `ribbon_ride` registry (1.0). Lines 2250-2257 already back-correct `stop` / `premium_stop_pct` /
`stop_display` / `stop_mode` / `trigger_level` from the resolved `ExitState` — **`tp` was left out.**
**This is the exact field you read to answer "why didn't TP1 fire."** Core-vs-fleet parity gap: the fleet
path logs it correctly.

### 5b. Proven, not theorised

Replaying the **real tick series** through the **unmodified production exit engine** reproduces the ledger
**action-for-action, tick-for-tick, stage-for-stage** on all three arms; replay P&L lands within $2 / $16 / $6
of broker actual.

| arm | armed TP1 | ask peak | ticks ask ≥ TP1 | fired? | actual | best live exit | miss |
|---|---|---|---|---|---|---|---|
| risky-1 | **2.535 (+50%)** — `exit_patch` | 2.68 (+58.6%) | **4** | ✅ sold 3/5 @2.62 | **+$347** | +$475 | $128 |
| risky-3 | 3.30 (+100%) — registry | 2.69 (+63.0%) | **0** | ❌ | −$664 | +$816 | $1,480 |
| safe-2 | 3.26 (+100%) — registry | 2.76 (+69.3%) | **0** | ❌ | −$255 | +$333 | $588 |
| | | | | | | | **$2,196** |

**The stale/wrong-side-quote hypothesis is EXCLUDED IN CODE, not by assertion.** `fleet_broker.py:222`
returns `(ask, bid)` and the actuator binds `best_premium = ASK` — TP1 tests the **optimistic** side, so a
wrong-side read would fire TP1 **earlier**, not later. Zero `no_quote` rows across 29/135/132 ticks.

**Secondary finding worth its own line: TP1 triggers on the ASK but fills on the BID.** Nominal TP1 is never
realised TP1 — systematic optimism that must be disclosed in any future TP1-threshold study. *(Confirmed
live again today: risky-3's +100% TP1 = 2.56 filled at 2.49 — seven cents of it.)*

### 5c. The kill chain — an unreachable TP1 does not just forgo a partial, it DISARMS EVERYTHING

```
tp1_filled stays False
  → profit_lock_arm_scope = "post_tp1"  → the trailing lock CANNOT arm
  → pre_tp1_be_floor_arm_pct = None     → no breakeven floor
  → structure stop never eligible        (max last-closed-5m close 772.125 vs trigger 772.33 — 20.5 cents short)
  → ribbon-flip exit needs BULL          (ribbon was BEAR from 12:01)
  ────────────────────────────────────────────────────────────────
  → ONLY the −50% catastrophe cap remained. A "chart-stop-primary" trade became a naked cap trade.
```

**This was PREDICTED VERBATIM, a week early.** `accounts.json`'s `exit_profile_doc`, dated **2026-07-29**,
states that an unreachable +100% TP1 means the partial never fires **AND** the post_tp1 lock never arms —
citing the 2026-07-28 Bold trade that peaked +56% and closed −42%. **08-05 replayed it exactly:**
risky-3 +63% → −50%; safe-2 +69% → −53%. That is not hindsight. It was written down and it happened.

### 5d. NEW DEFECT B — `SAFE2-PHANTOM-FLAT-PRUNE` (MEDIUM, state integrity, $0 this trade)

At **13:57:03** a transient broker `qty=0` read emitted `FLAT_PRUNED` and **DELETED safe-2's exit-state
record while it still held 3 contracts.** Unmanaged ~10 minutes, re-adopted at 14:07 as
`adopted_manual/cap_only` with `stop_mode` **downgraded to "premium"** and `trigger_level` **nulled.** It was
never actually flat (open_qty=3 at 14:08, sold 3 at 14:12). Classic C11/L237. Zero P&L impact verified three
ways — **but `exit_actuator.manage_tick` prunes on a SINGLE `qty<=0` read with no error and no STATUS entry.**
On a day where the 5m close *did* break the trigger, this is a real loss.

---

## 6. WHY TWO ARMS SAT OUT — AND DID IT SAVE MONEY?

> ### ⚠️ **THE HEADLINE OF LENS 4 WAS REFUTED ON REVIEW, AND I RE-DERIVED THE CORRECTION MYSELF. bold-2's silence was NOT a free-model coin flip. It was Rule 7, hard, all day — and it is a per-account params divergence nobody has looked at.**

### 6a. bold-2 — GATED silence, PDT-primary (corrected)

LENS 4 reported: 386 ticks, 0 PLACED, 16 ENTER verdicts, of which **13 `VETOED_BY_MODELS` + 3
`RISK_DENY_PDT`** — and concluded the veto was the cause because it was the verdict at the decisive 11:48
fork. **That measures which gate wrote the log line first, not causation.** The free-model veto runs
**UPSTREAM** of the risk gate (`heartbeat_core.py:1417-1419`) and short-circuits, writing its own label.

**My independent re-derivation, three ways:**

1. `pdt_tracker.fetch_day_trades_used_5d(bold-2)` = **3**. `risk_gate.PDT_DAY_TRADE_LIMIT` = **3**. Equity
   $5,477 < `PDT_EQUITY_THRESHOLD` $25,000. **3 ≥ 3 → DENY**, all day. bold-2's three day-trades came from
   08-04 (763C, 768C, 769C round-tripped), so **it entered Wednesday already at the cap.**
2. **13 veto + 3 PDT = 16 = every ENTER verdict it produced.** On every tick where the coin came up
   "no veto," **PDT denied 3-for-3, zero exceptions.**
3. **TODAY (08-06) proves it with the mask removed.** Core ledger through 12:20 ET:
   `bold: 170 HOLD, 6 SKIP_STALE_TRIGGER, 2 SKIP_BULLISH_FILL_BAR, 3 RISK_DENY_PDT, 0 VETOED_BY_MODELS, 0 PLACED.`
   **No veto rows at all today. bold-2's only blocker was PDT.**

**AND THE ROOT CAUSE IS A PARAMS DIVERGENCE NOBODY HAS FLAGGED:**

```
automation/state/params.json            -> pdt_gate_mode = "cash_settlement"   (core SAFE)
automation/state/aggressive/params.json -> pdt_gate_mode = "margin_pdt"        (core BOLD)  ← legacy
```

The core Safe account was migrated to cash-settlement on **2026-07-14** after a live verification that
*"both core accounts are CASH accounts (multiplier=1, `pattern_day_trader`/`daytrade_count` both null) —
PDT is structurally inapplicable."* **bold-2 was left behind on the legacy path.** That is why safe-2 can
take 7 day-trades in the window and trade freely while bold-2 is hard-blocked at 3.

**🚨 DO NOT "FIX" THIS BY FLIPPING THE KEY — I checked, and the 07-14 premise is now STALE.** Live right now:

| arm | account | multiplier | pattern_day_trader | daytrade_count |
|---|---|---|---|---|
| safe-2 | PA3POKNV46VG | **4** | null | null |
| bold-2 | PA3WEBXJU67N | **4** | null | null |

**Both report multiplier = 4 (RegT margin), not 1 (cash).** If that is real, then **bold-2's PDT block is
CORRECT and safe-2's PDT exemption is the defect** — and safe-2 has taken 7 day-trades in 5 business days on
a sub-$25K margin account. Harmless on paper; **it is a hard blocker for live money.**
**Highest-priority open question in this audit. Do not touch either key until the account type is
re-verified.**

### 6b. safe-3 — SIGNAL-ABSENT silence, a completely different mechanism

384 ticks, 383 HOLD + 1 ERROR, **`risk_code = None` on all 383** — the risk gate was never consulted, so a
structurally-dead PDT gate cannot explain a silence it never saw. Reasons: 351 "no qualifying setup" ·
16 "requires confluence/sequence" · 14 "1 triggers < 2" · 2 "no live signal". **Only 1 signal in 384 ticks,
vs 17 on Tuesday.** That is an upstream TAPE change, not gate intelligence — and those 30 ARM_GATE rows sit
**upstream of side/strike selection**, so there is no counterfactual contract to price.

### 6c. Did the silence save money?

**On Wednesday, YES, and unambiguously.** bold-2 **−$0.54** and safe-3 **−$0.68** against participants'
−$140.39 / −$339.76 / −$1,462.29. Not trading was the best available outcome and both silent arms got it.
ORACLE bound (**LABEL ONLY, never executable**): bold-2 taking the put at 3–8 lots = **−$249 to −$680**.

**But three cuts kill the flattering story:**
1. **Both silent arms TRADED on Tuesday's +$3,617 record day** (bold-2: 3 fills / 49 signals; safe-3: 5
   contracts / 17 signals). The gates are **selective, not statically restrictive.**
2. **TODAY they sat out AGAIN — and today the silence COST money.** The three participating arms are
   **+$1,500.15** through 12:20 ET. bold-2 and safe-3 are **$0.00.** bold-2's TP1 is +75% (= 2.24 on a 1.28
   entry) and the contract traded 2.57 — **it would have collected.** Three consecutive silent sessions on
   an arm blocked by a legacy params key is not a risk filter; **it is an arm that is effectively OFFLINE.**
3. At **n=2 days** I refuse to call abstention an edge, and the mechanism says not to: safe-3's silence is
   tape, and bold-2's is Rule 7 arithmetic. **/fable-too-good applies — this is exactly the shape to
   distrust.**

### 6d. Ledger blind spot found while doing this (L244 replayed)

A **second execution path, `extra_exec`, is invisible to the top-level `action` field.** Core row
`2026-08-05T10:01:02` reads `action=HOLD / setup=None / reason="no setup passed scoring"` yet carries
`extra_exec[1].action=PLACED` with real broker order `f9366c6f` → a real fill at 10:01:58 of
3× `SPY260805C00777000` @ 1.61. **Any tool answering "did this arm trade?" from `action` reports safe-2 = 1
trade when the broker shows 2.** `daily_brief.py` and `fill_funnel.py` were fixed;
**`participation_daily.py` is STILL `extra_exec`-blind** — OPEN.

### 6e. Structural asymmetry exposed in passing

**bold-2 has ZERO `extra_exec` rows all day** — it is never evaluated against the
`vwap_*`/`bollinger_squeeze` family that safe-2 sees. Part of "bold-2 trades less" is a **smaller strategy
surface**, not stricter gates. That quietly contradicts *arms = risk profiles, not strategies* and deserves
its own look.

---

## 7. 🎯 THE TUE-vs-WED TENSION — THE CRUX

J's instruction: *"Name the change that survives BOTH, or state honestly that no single static change does,
and then prove the regime is detectable LIVE at entry time."*

### 7a. On the STOP axis: NOTHING survives, and the two populations disagree with each other

No single static width improves both days. Worse, the two wide populations point in **opposite aggregate
directions** — the 25-day real-fill book says *widen* (+$815 at −6% → +$7,652 at −50%), the 391-day
population says *tighten* (+$8,036 → +$2,176) — because their trend/chop mix differs. **Both agree on chop**
(391-day chop +4,504 → −2,423; book chop −416 → −1,903; gap-fade monotone −120 → −2,704).

### 7b. On the EXIT-HEIGHT axis: NOTHING survives — **and TODAY flipped the sign**

This is **new evidence no lens could see**, and it is the most important thing in this document.

The seductive story after Tue+Wed was: *"risky-1 was best both days, and the common property is a
REACHABLE TP1 (+50% instead of +100%)."* LENS 3 had already disconfirmed the naive "trail vs fixed"
framing (risky-1 ran the trailing ribbon shape on Tuesday too), and reachable-TP1 looked like the survivor.

**Today, 2026-08-06, all three arms bought `SPY260806P00770000` within 15 seconds. Same trade. Third
head-to-head. Broker fills, all closed, all flat:**

| arm | TP1 | entry | fills | realised | **per contract** |
|---|---|---|---|---|---|
| risky-1 | **+50% = 1.845** (REACHABLE-TP1 challenger) | 1.23 ×5 | sell 3 @1.95 · 2 @1.63 | +$295.75 | **+$59.20** |
| risky-3 | +100% = 2.56 | 1.28 ×8 | sell 5 @2.49 · 3 @2.03 | +$829.61 | **+$103.75** |
| safe-2 | +100% = 2.56 | 1.28 ×3 | sell 2 @2.71 · 1 @2.17 | +$374.79 | **+$125.00** |

**The tape reached 2.57 — it cleared the +100% TP1 by ONE CENT. Both "unreachable" TP1s fired.** And the
reachable-TP1 arm came **LAST**, by 75–111% per contract, because +50% sold 60% of the position too early.
Had risky-1 run the +100% shape on its own 5 lots it would have earned **+$538 instead of +$296.**

**Scored, three consecutive days, same-contract head-to-heads:**

| day | reachable +50% | unreachable +100% | winner |
|---|---|---|---|
| 08-05 put | +$69.40/ct | −$83.00 / −$85.00 /ct | **reachable, by ~$153/ct** |
| 08-06 put | +$59.20/ct | +$103.75 / +$125.00 /ct | **unreachable, by ~$55/ct** |

> ### **The candidate that survived Tuesday and Wednesday died on Thursday. n=2 head-to-heads, sign already flipped once. There is no static exit height that survives.**

**LENS 5 recorded a prediction before the outcome was known** — *"if this resolves as a loss it is the 11th
consecutive orphan-band member (0-for-11)"* — and **it resolved as a WINNER.** Scored: **wrong.** The orphan
band stays 0-for-10 and the correct reading of it is now sharper: it is **not** "positions that peak ≥+50%
always lose." It is *"a position whose TP1 is unreachable has no intermediate protection, so its outcome is
a coin flip on whether the tape keeps going."* Wednesday it stopped. Thursday it kept going.

### 7c. Is the regime detectable LIVE at entry time? **NO — and this repo already proved it, four days ago**

The regime-conditional answer (widen on trend, tighten on chop) is **mechanistically real and consistent
across all three populations.** It is also **not executable**, and the evidence is pre-registered, not
hand-waved:

- The **early regime classifier was pre-registered on 2026-08-02 and FAILED every gate**: 8-way accuracy
  **20.9% vs a 39.1% majority baseline**; binary skip precision **26.8%**.
- **Its own confusion matrix:** of days it flagged **gap-fade** at 09:45 ET, **18 were truly gap-go** vs
  **16 truly gap-fade.** Worse than a coin flip on the one distinction that matters.
- **Tuesday was gap-go. Wednesday was gap-fade.** The two days J asked me to reconcile are *precisely* the
  pair the classifier provably cannot separate.
- The 776C entries landed **09:58–10:19 — squarely inside the blind window.**

**Calling the answer "regime-conditional" and stopping there would be hindsight wearing a plan's clothes.**

### 7d. There IS one live-detectable discriminator that is not a regime classifier — and the obvious action on it is already dead

`tp1_filled` is a **boolean known at every tick with zero look-ahead.** It cleanly separates the two branches
J framed as conflicting: on 08-04 TP1 fired at 09:57 and the live question was how tight to trail (post-TP1
behaviour is already correct); on 08-05 TP1 never fired and there is **no intermediate exit of any kind**
between entry and the −50% cap.

**The obvious action — arm the profit lock pre-TP1 (`profit_lock_arm_scope = "full"`) — is CELL E1 of an A/B
this repo already ran on the LIVE core, and it FAILED:**

| gate | E1 (arm_scope=full) | verdict |
|---|---|---|
| G1 aggregate | **−$482.10** | FAIL |
| G3 ex-best-1 | −$1,008.60 | FAIL |
| G4 runner cohort | **−$7,758.85**, 22 worse / 0 better | FAIL |
| n | 190 real-OPRA, `n_excluded_no_opra_cache = 0` | — |

**⛔ LENS 5's headline deliverable — `analysis/recommendations/profit-lock-arm-scope-prereg-2026-08-06.json` —
IS THIS CELL, AND MUST BE KILLED, NOT BUILT.** Its stated justification contains two factually false claims,
both caught on review and both verified by me:
1. *"That runner does not exist yet"* — **false.** `backtest/tools/exit_armscope_ab_2026_07_28.py` exists,
   with guard `backtest/tests/test_exit_armscope_ab.py` (among 102 tests I re-ran green).
2. *"Those four were SIMULATOR studies… this prereg IS the request for that live-machine scorecard"* —
   **false.** That runner's own docstring says exits are re-derived ONLY through `walk_exit_manager` driving
   the real live `exit_manager.plan_exit_actions`, **"NEVER `simulator_real.simulate_trade_real"`** — it
   routes around the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar by name. **It IS the live-machine scorecard.**

**Pre-TP1 arming has now died five times, the fifth on the live machine at n=190. Honest write-up: settled,
not pending. Graveyard, permanently.**

### 7e. So what IS left standing? ONE candidate, and it is a tail guard, not an edge

> ### 🎯 **MAX-3-ENTRIES-PER-WAVE, keyed `(arm, date, option_symbol)` — the only change measured to cost ZERO on every day we have and to save money on the day that hurt.**

| day | live | cap-3 | delta |
|---|---|---|---|
| **2026-08-04** (record +$3,624 day) | +3,624 | +3,624 | **$0.00 — literal no-op** |
| **2026-08-05** | −1,935 | −1,282 | **+$653** |
| **2026-08-06** (today) | +1,500 | +1,500 | **$0.00 — one entry per contract per arm** |
| 25-day book | +317 | +1,037 | **+$720** (9 waves, 12 trades) |

**Why the 08-04 no-op is provable and not a claim** — I re-derived the per-contract ordinals from broker
fills myself. The largest wave on 08-04 was **n=3** (risky-3's 763C at 09:50 / 09:54 / 09:57), and its
legs were **[−$40, −$144, +$524]** — **the +$524 winner IS the 3rd entry, and cap-3 preserves it.**
Cap-**2** would have destroyed it, which is exactly why the grid reads cap_2 = 3,100 vs cap_3 = 3,624.

**Why it does not cut a profitable cohort** — the broker-truth entry-ordinal decomposition puts the sign flip
exactly between the 3rd and 4th entry:

| ordinal | n | total | mean | win % |
|---|---|---|---|---|
| 1st | 145 | −$140 | −0.97 | 19% |
| **2nd** | 30 | **+$1,070** | +35.67 | 13% |
| **3rd** | 17 | **+$107** | +6.29 | 24% |
| 4th | 9 | **−$257** | −28.56 | 11% |
| 5th+ | 3 | **−$463** | −154.33 | **0%** |

This also **refutes the seductive cap=1 reading of the n=1 grid**: 2nd entries are the **best cohort in the
entire book.** Capping at one would have destroyed real money (−$1,193 in the reviewer's window).

**⚠️ AND THE HONEST DISCLOSURE THAT DECIDES IT: 91% of cap-3's measured benefit is the day that motivated it.
Excluding 08-05, it is +$67 across 7 waves on n=12 removed trades — noise. It clears a DOES-NO-HARM bar, not
an EVIDENCE bar.**

**⚖️ CROSS-LENS CONFLICT, ADJUDICATED.** LENS 5 says *"SHIP cap-3."* LENS 1 says *"PRE-REGISTER, DO NOT SHIP."*
Identical numbers, opposite verdicts. **I side with LENS 1** — and it is moot tonight anyway, because the
market is open and no trading-path file may change. **Both lens commits are docs-only; nothing is live
either way.** Cap-3 gets a frozen prereg with a forward clock and ships after 15:55 ET on an evening when it
has forward evidence, not on the strength of the day it was born on.

**Also note cap-3 (per-CONTRACT, count-based) is NOT the once-per-day contract restoration (per-STRATEGY,
§4c) and NOT the graveyarded per-setup TIME cooldown.** Three different guards, and only cap-3 has a
verified $0 cost on 08-04.

### 7f. And one entry rule survives all three days, in shadow only

**V-d1** — do not enter when the last fully closed 5m bar closed AGAINST the trade direction:
**+$179 Tue · +$145 Wed · no-op today** (the 10:25 bar closed 770.45 vs open 771.23 = DOWN, agreeing with the
put) · **+$1,242 over 25 days** · 14 days touched, 1 negative (−$15) · blocked-cohort WR **3.0%** vs
population **18.3%**. It survives because it is **not a regime bet**: on a trend day the last closed bar
usually already agrees so it rarely binds; in chop it binds precisely on the knife-catch re-entries (it
blocked the 10:06 776C re-entry on both arms).
**Its within-day permutation p is 0.145 across 17 uncorrected cells. SHADOW AND MEASURE for 10 sessions.
Do not arm.**

---

## 8. WHAT SHIPPED vs WHAT IS PREREG-ONLY

**Nothing arms on one day of evidence. No live trading-path file changed this session. Market open.**

### 8a. SHIPPED — behaviour-affecting (both were ALREADY EXECUTING on disk; committing changed no runtime behaviour)

| commit | what | guard | RED-proof | revert |
|---|---|---|---|---|
| `e3ec740b` | **FLEET-PDT-PARITY** — fleet day-trade count routed through `pdt_tracker` exactly as core already did. **LOG ALWAYS, ENFORCE NEVER by default.** Fail-open (C7): any fetch failure degrades to the broker field then 0 — pre-fix value exactly, so an outage can never invent a block. 90s per-arm TTL memo. | `test_fleet_pdt_parity.py` **11/11**, parametrized params×live matrix (C14 vary-and-assert) + source-mirror asserts | ⚠️ **OWED** — task #103, after 15:55 ET. Mutating a file that executes every 60s during RTH was correctly refused. **Green ≠ proven-to-go-red.** | delete params key `fleet_pdt_enforce` |
| `3ba20e09` | **Standing per-arm "why did this arm not trade" one-liner** in `fill_funnel.py` (OP-33(e) — so J never has to ask again). $0, pure ledger read, `extra_exec`-aware. | `test_fill_funnel_why.py` **23/23** | ✅ reproduced hand-derived tick counts EXACTLY and independently | revert commit |

**🚨 THE HIGHEST-RISK FINDING OF THE SESSION AND IT IS A PROCESS ONE:** both of the above were **already
running live but sat UNCOMMITTED.** One stray `git checkout` in another lane would have silently reverted
production mid-session. **C34/C35.** Now committed.

### 8b. SHIPPED — analysis + guards only (zero production surface)

- `dcf733b4` — LENS 1: 3 stop-width tools, `EOD-2026-08-05-STOPS.{md,json}` + charted 776C SVG,
  `test_stop_width_lens1_guards.py` **13 guards, RED-PROOFED TWICE** (flipped LOWEST_ENTRY → recovery guard
  went RED as predicted; flipped the monotonicity sort → proved the assert is discriminating, not vacuous).
  Clone-safe. Plus real 1-min OPRA cache for 08-05.
- `b9cd7a6e` — LENS 2 **prereg frozen BEFORE the runner existed** (git-provable: prereg 01:56:39, runner
  mtime 02:00, report 02:18:12).
- `b80f0deb` — LENS 2 report + runners + `test_vwap_cont_once_per_day_process_scope_2026_08_05.py`
  (**3/3, RED-proofed BOTH ways** — disabling `_fired_today` fails test 1; wiring
  `same_bar_cooldown_active` into `fleet_live` fails test 3; both mutations reverted and re-verified green).
- `2127a9fd` — LENS 3 put autopsy, post-commit verified with `git show --stat` (L247).
- `76d78f0c` — LENS 4 silent-arms report *(headline now superseded by §6a)*.
- `8214cac7` — LENS 5 verification addendum V1–V7.
- **This document.**

### 8c. READY TO SHIP, DELIBERATELY WITHHELD — queue for ≥15:55 ET

| item | exact change | why withheld |
|---|---|---|
| **CORE-TP1-DISPLAY-DIVERGENCE** (Defect A) | In the existing `ExitState` back-correction block, `heartbeat_core.py` ~L2250-2257: add `plan['tp1_premium_pct'] = _exit_state.tp1_premium_pct` and `plan['tp'] = round(_exit_state.entry_premium * (1.0 + _exit_state.tp1_premium_pct), 2)`. Guard: assert a core ribbon entry journals `tp == entry*2.0`. **Revert: delete the two lines.** | hot shared surface, sibling lanes in the same tree (L271), market open |
| **SAFE2-PHANTOM-FLAT-PRUNE** (Defect B) | Require **two consecutive** `qty<=0` reads before `FLAT_PRUNED` deletes a record + a loud log when re-adoption downgrades `stop_mode` structure→premium | `exit_actuator` is shared by core AND fleet — needs its own `/fable-blast-radius` |
| **RED-proof of `test_fleet_pdt_parity.py`** | source mutation, restore procedure written | task #103, after RTH |

### 8d. PRE-REGISTERED ONLY — nothing armed

- **MAX-3-ENTRIES-PER-WAVE** — needs a frozen prereg with a forward clock (§7e).
- `entry-structure-forward-prereg-2026-08-06.json` — shadow-measure **V-d1** (pre-registered) and **V-e3**
  (post-hoc, first legitimate registration) for 10 sessions; 5 forward gates including within-day-permutation
  **p ≤ 0.10** on the pooled population; **pre-committed KILL criterion** sending both to the graveyard if
  they still fail at 20 pooled sessions.

### 8e. ⛔ KILLED THIS SESSION

- **`profit-lock-arm-scope-prereg-2026-08-06.json`** — graveyard collision, §7d. **DO NOT BUILD THE RUNNER.**
- **Any stop-width change, in either direction** — rejected on evidence (§3), not deferred.
- **All 6 level-proximity entry cells** — REJECT on both engine-actual levels and a causal mechanical proxy.

### 8f. OPEN — flagged, not fixed, owner unassigned

1. 🚨 **The account-type contradiction** (§6a). Highest priority. Blocks live money.
2. `participation_daily.py` still `extra_exec`-blind — will under-report any `vwap_*`/`bollinger_squeeze` trade.
3. `fill_funnel` prints `[DEGRADED]` on **every** run, both days, unexplained. A banner that always says
   DEGRADED trains J to ignore the instrument. ~10 minutes.
4. `accounts.json` risky-1's `note` field still says *"deliberately NO exit_patch — the untouched control
   lane"* (dated 2026-07-20) while the same arm's `exit_profile_doc` (2026-07-29) correctly describes
   REACHABLE-TP1 with `tp1_premium_pct: 0.5`. **Internally contradictory record**, and that key is exactly
   what decided the put. Doc-only; another lane is in that file.
5. `accounts.json` lists **safe-1 and safe-2 on the SAME account number PA3POKNV46VG.** Noticed, not
   investigated.
6. `safe-1` credentials return HTTP 401 / equity 0.00. Zero 08-05 activity so no data is missing.
7. 6× `SKIP_STALE_TRIGGER` at 09:30–09:35 on bars stamped 15:50/15:55 — the previous session's closing bars
   leaking into the open. It skipped correctly, so cosmetic, but it is a staleness smell at the exact minute
   the engine is most eager. **Recurs today: 6 more, both core arms.**
8. **The free-model panel silently degrades to ONE voter.** At the 11:48 fork, safe got qwen3:14b(go=true) +
   qwen3:14b(**error: no_valid_json**); bold got qwen3:14b(**error: no_valid_json**) + nemotron-3-super-120b
   (go=false). **Both arms decided a live entry on a one-voter panel and neither logged a degradation.**
   That is a C7 silent-degradation defect and it is more actionable than "the veto is a coin flip."
   Also triggers **OP-32's free-model trust gate** — this touchpoint is due a `free_model_audit.py` grading.
9. **risky-3 ATM kill criterion is knife-edge and MUST NOT be silently cancelled.** Criterion met at the
   sample floor on 08-05 (n=14, −$653); revert was due **same day** by the prereg's own wording and was not
   executed; risky-3 took a fresh ATM position today and made **+$830**, which would take the cohort to
   ~+$177. **The criterion evaluates AT the floor, which was already reached.** Letting a later gain quietly
   cancel a triggered kill is exactly the post-hoc rescue the pre-registration exists to prevent.
   **Two honest options: honour the revert tonight, or amend the prereg IN WRITING before any further
   outcome is known.** Do not just let it lapse.

---

## 9. THURSDAY — LIVE STATUS (it is already 12:20 ET and the day is 2/3 done)

**Broker-verified this session, all arms FLAT:**

| arm | equity | day P&L | legs | notes |
|---|---|---|---|---|
| risky-1 | 6,338.46 | **+$295.75** | 3 | +50% TP1 fired 11:23 |
| risky-3 | 5,343.32 | **+$829.61** | 3 | +100% TP1 fired 12:04 @2.49 (7c of ask→bid slippage) |
| safe-2 | 5,764.06 | **+$374.79** | 3 | +100% TP1 fired 12:16 @2.71 |
| bold-2 | 5,477.71 | **$0.00** | 0 | 3× `RISK_DENY_PDT`, **no veto rows** |
| safe-3 | 5,780.15 | **$0.00** | 0 | 180 HOLD, zero signals |
| **TOTAL** | | **+$1,500.15** | | |

One clean trade, three arms, entered 10:32 ET after the session high (771.82 @ 10:20) — **puts bought into
supply, the mirror image of Wednesday's calls bought into supply.** That is the setup shape J's philosophy
asks for, and it paid. **Two-day net: −$443.51.**

### PDT / day-trade headroom — real numbers, from the repo's own `pdt_tracker` (my naive count agrees exactly)

| arm | lane | gate mode | day-trades (trailing 5 bd) | limit | status |
|---|---|---|---|---|---|
| safe-2 | core | `cash_settlement` | **7** | PDT N/A — gate is settled cash | free |
| **bold-2** | core | **`margin_pdt`** | **3** | **3** | 🚫 **HARD BLOCKED** — and stays blocked until 08-04 rolls out of the window |
| safe-3 | fleet | not enforced | 6 | (3) | logged, not enforced |
| risky-1 | fleet | not enforced | 8 | (3) | logged, not enforced |
| risky-3 | fleet | not enforced | 9 | (3) | logged, not enforced |

> ### 🚨 **LIVE FOOT-GUN: if anyone ever flips `fleet_pdt_enforce = true`, ALL THREE fleet arms go dark instantly (6, 8, 9 — every one over the limit of 3).** The flag ships OFF by default and must stay OFF until the account-type question (§6a) is resolved.

### What to watch for the rest of today

- **15:50 ET time-stop / 15:55 EOD flatten** — all arms are flat now, so this is only live if a new entry fires.
- **`SKIP_STALE_TRIGGER` at the open** recurred again today (6 rows, both core arms). Cosmetic, still unexplained.
- **safe-3 has now produced 1 signal in two full sessions.** If tomorrow is a third, that is a signal-supply
  problem, not a gate problem, and it needs its own lane.

### What needs J

**Under OP-0, nothing in this audit requires J's permission** — everything is paper, reversible, and reported
for REVOKE. Two things need his *judgment* rather than his approval:

1. 🚨 **The account-type contradiction (§6a).** Are these cash or margin accounts? The 2026-07-14 verification
   says multiplier=1; the live API says multiplier=4. Until that is settled, one of safe-2 or bold-2 is
   running the wrong PDT gate, and **it is a hard blocker for arming live money.** I will not guess and I
   will not flip either key.
2. ⚖️ **The risky-3 ATM kill (§8f#9)** — honour it, or amend the prereg in writing. Not "let it lapse."

---

## ⚖️ THE HARDER QUESTION: THE 08-04 AUDIT PREDICTED THIS. WAS TUESDAY NIGHT DISCIPLINE, OR A MISS?

**First, the scored prediction, stated plainly, because it was right.** The 2026-08-04 audit wrote:

> *"The −6% stop on a chop day — that is the treadmill, and it is the day we have not seen yet."*

**2026-08-05 classified gap-fade. The −6% stop fired ten times for −$1,279. Realized stop distances −7.2% /
−5.7% / −9.1% / −7.5% / −15%, against a 10.3% median 1-minute noise band. Prediction: CORRECT.** Four of the
five lenses confirmed it independently. That is a real forecast, made in writing, before the fact, and it
landed.

### VERDICT: **It was DISCIPLINE — and Wednesday's own data proves it was also CORRECT. But there is a real miss inside it, and it is not the stop.**

**Why the discipline was right, with the number:**

The 08-04 audit predicted the **SYMPTOM** correctly and prescribed the **WRONG REMEDY**. Its proposed action
(PREREG-A) was *widen the stop.* Wednesday's own evidence says:

- widening loses more in every cell at cap1 (−205 → −1,643),
- the −50% catastrophe-only cell is the **single worst cell in both arms**, $281 worse than what happened,
- and 08-05's own archetype degrades **monotonically** across 391 days, −$120 → −$2,704.

> **Had we shipped Tuesday night on one day of evidence, we would have made Wednesday WORSE.**
> The "one day is not enough" rule did exactly its job. **Keep it. It just paid for itself.**

**And Wednesday's night proves the same rule again from the other side.** The best-looking exit change out of
Tue+Wed was reachable-TP1. **Thursday killed it** (§7b). Two consecutive nights where the obvious one-day
inference was wrong. That is not caution — that is the rule being empirically correct twice in 48 hours.

### **But there IS a miss, and it is a VISIBILITY miss, not a discipline miss.**

We spent Tuesday night arguing about a knob we **could not validate**, while **three already-diagnosed
defects sat unsurfaced** — none of which needed a backtest, and all of which cost real money on Wednesday:

| already written down, before Wednesday | where | Wednesday cost |
|---|---|---|
| The **unreachable-TP1 kill chain**, described verbatim, citing the 07-28 incident that peaked +56% and closed −42% | `accounts.json` `exit_profile_doc`, **2026-07-29** | **−$919** (risky-3 −664 + safe-2 −255) |
| `vwap_continuation` **once-per-day** contract, enforced by a module-global inside a process that restarts every 60s | the detector's own docstring | enabled entries 2–5 = **$991 of the modelled −$1,196** (82.9% of the spiral) |
| **bold-2 stranded on `pdt_gate_mode = margin_pdt`** while core Safe was migrated to `cash_settlement` | `aggressive/params.json`, since **2026-07-14** | 3 sessions offline; today alone it missed a winning trade |

**In fairness to Tuesday night — the first of those WAS being handled correctly.** risky-1 was armed as the
REACHABLE-TP1 live challenger on 2026-07-29, *with an honest caveat in its own doc that the change tested
negative in isolation.* 08-05 and 08-06 are exactly the forward evidence it was armed to collect, and it has
now collected two data points with opposite signs. **That is the system working as designed.**

**So the honest, unflattering summary:**
- **The knob discipline was right and is vindicated twice.** ✅
- **The instrument discipline was not.** ❌ A defect written into a JSON `doc` field, a docstring, and a
  legacy params key is not on any surface a session or J reads at decision time. **Per OP-33(e) — a
  diagnosis without an instrument is not a finding, it is a note to nobody.**

**The correction that must stick:** the output of a diagnosis is a **surface**, not a paragraph. LENS 4's
per-arm "why this arm did/did not trade" one-liner (`3ba20e09`) is the right shape and it is the single most
valuable thing shipped in these five lenses — **not because it found anything, but because it means the next
bold-2-style silence announces itself instead of waiting for a −$1,900 day to be audited.**

---

## LENS ROSTER — WHAT WAS UPHELD, WHAT WAS REFUTED, WHAT I DISCARDED

| lens | verdict after adversarial review | status |
|---|---|---|
| **L1 stop-width** | **UPHELD.** Re-derived on a different price basis, same conclusion. **MINOR_GAPS:** monotonicity prose overstates its own table (§3b); guard loops `("cap1",)` while its name claims every cap; JSON field `benefit_excluding_the_motivating_day = −67.0` sign-conflicts with the prose's `+$67` (arithmetic says the prose is right); **the headline joint grid has no generating code in any committed tool** — a clean clone cannot regenerate it. | ✅ verdict stands |
| **L2 entries** | **NOT REFUTED. MINOR_GAPS:** undisclosed deviation from the frozen split definition (70.4% vs 104.8%, §4a); the counterfactual is additive with no sequential walk (tested empirically — V-d1's block persists continuously 10:05–10:09 so no replacement entry is possible; headline survives); **the decisive permutation p-values are hardcoded literals with no committed code path.** | ✅ findings stand |
| **L3 the put** | **SOLID.** Survived adversarial re-derivation intact **and corrected the brief that commissioned it.** No re-entry artifact possible (the put was the last trade of the day for both fleet arms). Only gap: it inherited the day P&L rather than re-deriving it, and disclosed that. | ✅ |
| **L4 silent arms** | 🚫 **REFUTED — headline causal inversion.** Data flawless (every tick count, every P&L reproduced exactly), safe-3's half perfect, and the L244 `extra_exec` blind spot is real and valuable. But **"PDT falsified as the dominant cause" is WRONG for bold-2** and **"a coin-flip decided bold-2's entire Wednesday" is directly refuted by observation.** §6a carries the corrected version, which I re-derived three independent ways. Also: "the veto is non-deterministic on identical input" is imprecise — the real mechanism (lane divergence + silent error-induced voter dropout to a one-voter panel) is **worse and more actionable.** | ⚠️ **corrected, do not cite the original headline** |
| **L5 re-entry + sizing** | **VERIFICATION HALF UPHELD** (nothing shipped ✅, live Event B ✅, orphan band ✅, naive TP1 fix net-negative ✅ — a third independent route to the same answer). 🚫 **FORWARD HALF REFUTED:** its prereg is a graveyard collision justified by two false statements (§7d) and **must be killed, not built.** Its novelty was also overstated — `accounts.json` documented the orphan-band mechanism verbatim on 2026-07-29, and the 07-28 incident it "discovered" is literally row 5 of its own n=10 table. And **its recorded prediction resolved WRONG today** (§7b). | ⚠️ **keep the verification, kill the prereg** |

**Discarded, not reported as fact:** LENS 4's veto-primary causal story · LENS 5's arm-scope prereg and its
"unmeasured candidate" framing · LENS 1's "monotone in every cell" phrasing · LENS 3's trend-alignment entry
lead (already KILLED with the **opposite sign**: frozen prereg n=250/90 OOS, fully-aligned mean −$148.43 vs
fully-fighting +$200.40, Spearman −0.150 p=0.157, beats-null False — LENS 3 correctly declared the re-pick
hazard rather than proposing the variant).

---

## 10. 🎙️ SPOKEN BRIEF — GAMMA, FIRST PERSON

> Wednesday was a losing day. Minus nineteen hundred forty-four dollars, and most of it was our fault, not the tape's.
>
> Here's the honest version. One bullish signal is licensed to speak once a day. Because our producer restarts every sixty seconds, it spoke five times, and each time we bought the same call — into a high that had already printed in the first minute of the session. That contract never traded back to any of our ten entry prices. It settled at a penny.
>
> So no, they were not going to be good trades. And no, we do not need bigger stops. I tested it every way I know how, on the day, on the archetype, and on three hundred ninety-one days, and a wider stop loses more every time. Eighty-four percent of that loss was the number of times we entered, not how far we let it run.
>
> Seventy percent of the day was entry-side — trades no exit rule could have saved. The other thirty was one config key. Three arms bought the same put. The one with a fifty-percent target took three hundred forty-seven dollars. The two with a hundred-percent target had a target the tape never reached, which quietly disarmed every protection they had, and they gave it all back.
>
> Tuesday's audit predicted this exact day, in writing, and it was right. It also prescribed the wrong fix — widen the stop — and if I had shipped that Tuesday night, Wednesday would have been worse. So the discipline held, and it held correctly.
>
> The real miss is different, and I'll own it. Three of the things that cost us money on Wednesday were already written down in this repo before Wednesday. They just weren't on any surface anyone reads. A diagnosis nobody can see isn't a finding.
>
> One change survives all three days: never take more than three entries on the same contract. Zero cost on Tuesday, saves six hundred fifty-three on Wednesday, no-op today. But ninety-one percent of its benefit is the day that inspired it, so it gets pre-registered, not armed.
>
> Today we're up fifteen hundred. Same setup shape, mirrored — we sold into supply instead of buying it, and it paid. Two-day net is minus four hundred forty-four.
>
> Two things I need your judgment on, not your permission. Bold-two has been offline three sessions on a stale pattern-day-trader setting, and the account-type record contradicts itself — I won't guess at that one. And the ATM kill criterion on risky-three triggered Tuesday; today's win would quietly cancel it if we let it, and that's exactly what pre-registration exists to prevent.
>
> Nothing armed tonight. Nothing arms on one day.

---

*Sources: broker `/v2/orders` + `/v2/positions` (all six arms, live this session) · `automation/state/fills-ledger.jsonl`
(26 days, 498 engine option fills; matches broker EXACTLY on all 3 overlapping days: 08-03 15/15, 08-04 68/68, 08-05 30/30)
· real OPRA 1-min bars (Alpaca `v1beta1/options/bars`) · `core-decisions.jsonl` + per-arm `fleet/*/decisions.jsonl`
· `setup/scripts/pdt_tracker.py` · `automation/state/params.json` + `aggressive/params.json` ·
`analysis/deep-research/EOD-2026-08-05-{STOPS,ENTRIES,PUT,SILENT-ARMS,REENTRY-SIZING}.{md,json}`.
Clock: `setup/scripts/et_clock.py` → 2026-08-06 12:20:30 EDT, `market_hours=True`. Read-only throughout.*
