# COST-RECOVERY SIZING — J directive 2026-08-13

> **J, verbatim:** *"we're not a home run factory. we need to ensure we are buying the right
> amount and right size contracts 20-40% and make back the money we spent on the entire trade.
> thats where the runners come in. i dont care what the math says... its not going to happen.
> you need to re think this."*

**Status:** FINDING + DESIGN. Nothing shipped. Written during market hours; no trading-path edit.

---

## The law J stated, formalized

First tranche must **recover the entire cost of the trade**. Sell `n` of `Q` at gain `r`:

```
n * E(1+r) * 100  >=  Q * E * 100        ->        n = ceil(Q / (1+r))
free_runners(Q, r) = Q - ceil(Q / (1+r))
```

`E` cancels — **the required tranche fraction depends only on `r`, and viability only on `Q`.**

| Q | +20% | +25% | +30% | +40% | +50% |
|---|---|---|---|---|---|
| 3 | 0 | 0 | 0 | 0 | **1** |
| 4 | 0 | 0 | 0 | **1** | **1** |
| 5 | 0 | **1** | **1** | **1** | **1** |
| 6 | **1** | **1** | **1** | **1** | **2** |
| 8 | **1** | **1** | **1** | **2** | **2** |
| 16 | **2** | **3** | **3** | **4** | **5** |

(cells = free runners after full cost recovery)

**Minimum Q to cost-recover inside J's 20-40% band:** +40% -> Q>=4 · +30% -> Q>=5 · +20% -> Q>=6.

> **3 contracts cannot cost-recover below +50%.** This is arithmetic, not a tuning opinion.

---

## Root cause chain (every link evidence-quoted)

1. **Rule 6 sets `min_contracts = 3`** — "Min 3 contracts (2 TP + 1 runner)", authored at $1-2K equity.

2. **The recency clamp uses that FLOOR as a CEILING.**
   `automation/state/fleet/fleet_executor.py:343-346`
   ```python
   min_qty = int(params.get("min_contracts", 3))
   clamped = min(int(qty), min_qty)
   ```

3. **It fired today.** `automation/state/fleet/<arm>/decisions.jsonl`, 2026-08-13:
   - `safe-3 : qty clamped 8 -> 3  : recency RED`  (equity 4470.48)
   - `risky-1: qty clamped 12 -> 5 : recency RED`  (equity 4979.42)

4. **Equity has tripled; the floor did not.** safe-2 live equity **$5,500.84** (CLAUDE.md still
   claims $1,746.75). 30% risk cap = $1,650; at $1.03/contract that affords **16**. Took **3**.

5. **3 contracts force TP1 >= +50%**, so the +100% TP1 inherited from the SS-B whole-cell port
   (`strategies.py:131`, commit `933bd651`) was never challenged — it was *consistent* with a
   3-lot even though nobody derived it that way.

6. **Result: a strategy that only pays on home runs.** TP1 +100% fires **20.4%** of the time
   (`tp1-reachability-2026-08-06.json`, `popA_tp1_fire_rate`).

**The exit shape is a symptom. The sizing is the disease.**

---

## Why the earlier "the math says no" did not apply

`tp1-reachability-2026-08-06.json` swept `tp1_premium_pct` x `tp1_qty_fraction` as **independent
knobs on a fixed position**. It never anchored the tranche to cost recovery and **never varied Q**.
Every cell it rejected lowered TP1 *while leaving the position at 3-5 lots* — which, per the law
above, guarantees the tranche cannot recover cost and the runner is still carrying the trade.
**J's structure was never a cell in that study.** The REJECT verdict does not bind here.

---

## Proposed design (NOT shipped)

**Decouple two decisions that are currently fused.**

- **KEEP the recency clamp.** It is A/B validated (`recency-sizing-ab.json`,
  `policy_dominates=true`, -$1,274 improvement over 8 real fleet-fill days). Removing it re-opens
  a proven loss. It correctly answers *"how much capital do I risk on an unconfirmed edge?"*
- **DERIVE the exit from realized Q at fill time.** The bug is that the exit shape is static
  (+100%) no matter whether the engine ends up holding 3 or 16 contracts.

```
r_first   = min{ r in [0.20 .. 0.50] : Q - ceil(Q/(1+r)) >= 1 }
qty_first = ceil(Q / (1 + r_first))          # sells exactly enough to recover cost
runners   = Q - qty_first                    # free carry, zero cost basis
```

Self-correcting: whatever the clamp does to Q, cost recovery stays achievable and runners are
always free. At Q=3 it reproduces today's +50% floor; at Q=8 it lands at +20%.

**Second lever (separate prereg):** `min_contracts` is pinned to $2K-era equity. The recency
config block itself still declares `equity: {safe: 2000.0, bold: 1648.0}` and `qty: {safe: 3,
bold: 5}` at `run_date 2026-08-12`. That is the L288-L290 class — *a cap mis-sized at birth fails
silently forever*. Scaling the floor with equity is a **separate** change and must not be bundled
with the exit-derivation change.

---

## The hard fact that constrains all of this

`tp1-reachability-2026-08-06.json`:
- `in_trade_under_control_walk_bar_open.median_mfe` = **+15.2%**
- `unconditional_session_max_bar_high.median_mfe` = **+83.8%**

**The median trade never reaches +20%.** No exit structure rescues a position that never moves in
your favor. Cost-recovery sizing fixes *how we get paid when we're right*; it does not fix *how
often we're right*. Both are live problems and they must not be conflated — a cost-recovery ladder
validated on entries with +15% median MFE would look like a losing change even if the structure is
correct.

**Therefore the study must report entry-conditional results**, not one pooled number.

---

## Validity gates (pre-registration, before any runner)

- **G1** — control arm reproduces today's live config exactly (Q=3/5, TP1 +100%) per arm.
- **G2** — vary-and-assert: the derivation must change `r_first` when Q changes, or it did not bind (C14).
- **G3** — report ALL cells including NOT-RUN; never report only movers.
- **G4** — stratify by whether the trade reached +20% at all. Pooling a +15%-median population
  hides the mechanism.
- **G5** — `automation/state/*` is READ-ONLY for the study.
- **G6** — a sign flip is not a resurrection. No cell is armed by this document.

## Provenance

- Root cause found 2026-08-13 ~10:50 ET from live decision ledgers + `fleet_executor.py`.
- Live equity read from broker `/v2/account` per arm, not from any cached state file.
- Directive is J's, unprompted, and overrides the earlier REJECT reading — correctly, because
  that study's population did not contain this structure.


---

## EXHIBIT — 2026-08-13 live fills (added post-close of the trade, same day)

> **`evidence_n = 1`** (stamped 2026-08-14 per deep-review tonight-item #3, C4 disclosure).
> The four rows below are **one signal event fanned across four arms** — identical
> `core_tick_id`, same strike, same minute. They are four *executions* of one observation, not
> four observations. Nothing in this exhibit is a sample size; it is a worked example of the
> algebra in §1, which is what carries the argument. The day's own honest unit is **5 events**
> (not 15 round trips), and this is one of them.

`BULLISH_RECLAIM_RIDE_THE_RIBBON`, SPY260813C00777000, entered 09:51 ET, fully flat 10:42 ET.
These four arms **+$1,619**; the full event including risky-3's 779C leg is **+$1,985**.
All figures below are broker fills, not replay.

| arm | Q | cost | tranche 1 | runner | total | **cost recovered at** |
|---|---|---|---|---|---|---|
| safe-2 | 3 | $309 | 10:19 2@2.10 | 10:42 1@2.21 | $332 | **+104%** |
| safe-3 | 3 | $327 | 10:22 2@2.27 | 10:42 1@2.21 | $348 | **+108%** |
| bold-2 | 5 | $505 | 10:12 3@1.99 | 10:42 2@2.21 | $534 | **+97%** |
| risky-1 | 5 | $540 | 10:01 3@1.68 | 10:42 2@2.21 | $405 | **+105%** (NOT at TP1) |

### The decisive row is risky-1

It has the *low* TP1 (+50%) — the "safe" config. It fired at +56%, sold 3 of 5 for **$504
against a $540 cost**, and **still had not paid for the trade.** It needed the runner to reach
break-even on capital.

Cause: `tp1_qty_fraction 0.667 x 5 = 3.33 -> floors to 3`. The law requires
`ceil(5 / 1.56) = 4`. **Off by one contract**, and a fixed fraction cannot know that.

> A fixed `tp1_qty_fraction` does not recover cost. Only `ceil(Q/(1+r))` does, by construction.

### Every arm needed ~+100% to get paid back

Not one arm recovered its cost below +97%. **Today worked only because the contract doubled.**
On a day topping at +50%, safe-2 (3 lots, TP1 +100%) banks nothing at tranche 1 and is entirely
dependent on the ladder floor. That is the home-run dependency J named, demonstrated on a day
the engine WON.

### Honest counter-evidence

On today's tape the current config **made more money** than cost-recovery sizing would have.
Re-running risky-1 selling 4 at 1.68 instead of 3: cost recovered ($672 > $540), but total
falls to **$353 vs the actual $405** — the extra contract sold at 1.68 instead of riding to 2.21.

**This does not weaken the case; it defines the study.** Cost recovery is insurance, and today
was a day insurance was not needed. Its value is on the **79.6% of trades that never reach
+100%** (`popA_tp1_fire_rate` = 0.2042). Evaluating it on the full pooled population — where a
handful of doublers dominate the sum — measures the wrong thing.

### Study design this forces

1. **Stratify on outcome reached**: trades topping <+20%, +20-50%, +50-100%, >+100%. Report all four.
2. **Primary metric is not total P&L** — it is *fraction of trades that returned their own cost*,
   with total P&L reported alongside as the cost of the insurance.
3. **Control arm must reproduce the table above exactly** (G1), including risky-1's shortfall.


---

## EXHIBIT 2 -- the OTHER half of the distribution, same day (trade #4, 14:36 ET)

Exhibit 1 (the 09:51 777C) DOUBLED, and the +100% TP1 beat every alternative on it. That is the
20.4% case. This is the other 79.6%, and it landed four hours later on the same setup.

`BULLISH_RECLAIM_RIDE_THE_RIBBON`, SPY260813C00777000, entered 14:36-14:37 ET.
Recorded while the position was STILL OPEN; the counterfactual is conditional on a floor exit.

| arm | entry | Q | cost | HWM | live TP1 | banked at peak |
|---|---|---|---|---|---|---|
| safe-2 | 0.66 | 3 | $198 | 1.11 (**+68%**) | +100% = 1.32 | **$0** |
| safe-3 | 0.65 | 3 | $195 | 1.10 (**+69%**) | +100% = 1.30 | **$0** |

The trade ran +68% and **banked nothing**, because the first tranche is priced at a double.
It then faded to 0.91 with the ladder floor locked at 0.858 (+30%) -- five cents away.

### Counterfactual under the cost-recovery law

For Q=3 the law returns r=+50% (the lowest band leaving a runner), sell `ceil(3/1.5)=2`:

| arm | LIVE (exit 3 at floor) | LAW (sell 2 @ +50%, 1 runner to floor) | delta |
|---|---|---|---|
| safe-2 | +$59.40 | **+$85.80** | **+$26.40 (+44%)** |
| safe-3 | +$58.50 | **+$84.50** | **+$26.00 (+44%)** |

Cost recovery is EXACT, not approximate: 2 x 0.99 x 100 = $198 against a $198 outlay. The
identity 2 x 1.5 = 3 is why -- at Q=3 and r=+50% the law consumes the position to the cent and
leaves precisely one free contract.

### Why this pair of exhibits is the whole argument

Same setup, same instrument, same day, four hours apart:

| | move | +100% TP1 verdict |
|---|---|---|
| trade #1 (09:51) | +124% | **won** -- holding beat every lower TP1 |
| trade #4 (14:36) | +68% peak | **banked $0**; cost-recovery +44% better |

The live config is not wrong, it is **conditional**: it wins on doublers and forfeits the peak on
everything else. `popA_tp1_fire_rate = 0.2042` says doublers are ~1 trade in 5.

This is precisely why the tp1-reachability study's REJECT does not settle it. That sweep lowered
TP1 on a FIXED position and measured the pooled sum -- where the doublers dominate. It never
asked the question these two exhibits pose: *what does the OTHER 79.6% give up?*

**Study design implication (already in the gates above, now with a live anchor): stratify on the
peak the trade actually reached. Reporting one pooled number across both exhibits would average a
+124% winner against a +68% non-winner and conclude nothing.**

Status: trade #4 was OPEN at time of writing. If it recovers to +100% or exits above the floor,
these deltas change -- the EXHIBIT stands (it banked $0 at a +68% peak) but the dollar figures
must be re-derived from the actual fills, not from this projection.
