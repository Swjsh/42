# Churn teardown — 2026-08-12 (15-agent workflow, 4 lanes survived adversarial verification)

> Method: 7 independent forensic lanes, each adversarially refuted by a separate agent before
> counting, then adjudicated. 3 lanes refuted. ~2.8M subagent tokens, 498 tool calls, read-only.
> **This document OVERTURNS the same-day EOD writeup.** Where they disagree, this one wins —
> it is per-fill attributed and verified; the EOD was a first-pass estimate.

## The headline that changes everything

**The churn did not lose the money.**

| exit stage | n | broker P&L | median hold |
|---|---:|---:|---:|
| `ribbon_flip` (the 1-minute churn) | 18 | **+$60** | **1.0 min** |
| `structure_stop` | 11 | **−$579** | 24 min |
| `premium_stop` | 8 | **−$493** | 2.5 min |
| `tp1` / `trail` | 2 | +$122 | 29 min |

Reconciles to **−$890 fill-price vs −$900.14 broker** (the $10.14 is ~$0.025/contract fees).
**38 positions, not 40** — "40" counted buy FILL ROWS; two risky-1 orders partial-filled.
All 38 attributed, 0 unattributed, 0 duplicate sells, 0 error rows.

**There was no runaway and no orphan-order bug.** Every exit fired from a named configured
stage. The fast-churn cohort was P&L-neutral. The money left through slow, "correct-looking"
exits: 11 structure-stopped CALLS with **zero winners**, four arms long into a −$3.43 fade.

## The actual bug: entry and exit read the same ribbon and disagree

18 of 38 positions were **PUTs opened while the ribbon stack read BULL**, and the ribbon-flip
exit predicate reads that identical BULL as invalidation — so they were liquidated on their
**first management tick, by construction**. Not flicker. Verified tick series: **772 RTH ticks,
BULL 670 / MIXED 90 / BEAR 12, five transitions all day, ZERO transitions into BEAR after
09:36, and all 27 ENTER_BEAR verdicts carried `ribbon: BULL` (27/27).** Nothing flipped —
**the positions were born pre-invalidated.**

- Entry **waives** it: `backtest/lib/filters.py:1494` sets `ribbon_bear_ok = stack == "BEAR"`,
  then `:1662-1665` `if trendline_only_setup: blockers.remove(5)`.
- Exit **enforces** it: `exit_actuator.py:468` and `heartbeat_core.py:877`, both bare
  `ribbon_stack == ("BULL" if side == "P" else "BEAR")`.

Same tick, same value, opposite conclusions.

## Mechanism ranking (they overlap — do not sum)

| # | mechanism | positions | P&L | verdict |
|---|---|---:|---:|---|
| M1 | entry/exit ribbon contradiction | 18 (47%) | +$60 | 🚨 **BUG** |
| M2 | risky-1 selectivity gate deleted | 12 (32%) | −$70 | 🚨 **BUG — commit `e28d210c`** |
| M3 | concurrent opposite plans, arbitrated only by "am I flat" | 8 (21%) | **−$574** | ⚠️ works-as-configured, wrong |
| M4 | sub-spread −6%/−8% premium stops | 8 (21%) | **−$493** | ⚠️ execution-frame defect |
| M5 | correlated fleet structure_stop (all calls) | 11 (29%) | **−$579** | ✅ by-design — **signal problem** |

M3 detail: 8 direction-flip re-entries (opposite side within 1.0–2.1 min of the prior exit)
lost **−$574 = 64.5% of the book**. The same flipped ribbon that fires the exit immediately
authorizes the opposite-side entry; the only re-entry guard
(`exit_actuator.same_bar_cooldown_active:176-190`) is keyed per-(arm, **SETUP**, trigger-bar),
and a direction flip changes the setup name, so it never binds.

## Not a regression — the churn is not new

Lane B **disproved** its own premise: 2026-07-20 and 07-21 were **worse** (median hold 1.0 min,
67% and 80% of closes under 2 min). No commit changed the exit mechanism. What IS new is the
**firing rate** of the longstanding unbuffered `ribbon_flip` SELL_ALL: **0 → 1 → 4 → 21** across
08-10/11/12. `ENTER_BEAR @ ribbon=BULL` occurs on only **5 days in the entire core ledger**
(07-07, 07-14, 07-15, 07-21, 08-12). 08-12 is an out-of-population day for that exit.

## ⛔ What NOT to do — each of these looked right and the evidence kills it

1. **Do NOT arm `pre_tp1_ribbon_confirm_ticks`.** Three lanes recommended it; the adjudicator
   killed it. The predicate was **permanently true** (zero BEAR transitions all day), so an
   N-tick buffer delays each dump by N minutes and liquidates all 18 anyway. It is the right
   instrument for **flicker**, and 08-12 was not flicker. (It may still be right for **08-11**,
   which WAS a genuine mid-hold BEAR→BULL flip — different day, different mechanism.)
2. **Do NOT ship a time-based re-entry cooldown/min-hold on this grid.** The apparent
   "+$594 at 10 min" fails a 20,000-draw permutation null: 5 min obs +246 vs null **+304
   (worse than random)**; 15 min +485 vs **+490 (exactly random)**; 10 min +676 vs null +468,
   p95 +711 — does not clear. On a day where 27 of 38 waves lost and mean wave was −$23.42,
   *any* rule deleting k waves earns +$23.42k for free. **Standing rule for this class: carry
   a matched suppress-k-at-random control, or you will re-derive the base rate and call it edge.**
3. **Do NOT arm `FLEET_SAME_BAR_COOLDOWN`.** Second independent tape meeting its own kill
   criterion: it covers 6 of 38 waves which netted **+$89** — arming it makes today worse, and
   worse than random (6 random waves = +$140 expected).
4. **Do NOT edit `j_vwap_cont_premium_stop_pct` in params.json.** Fleet arms never read
   params.json for exit shape — `strategies.py:161` hardcodes `premium_stop_pct=-0.06` on
   vwap_continuation. Editing that key changes nothing.
5. **Do NOT wire `ribbon_flip_back_min_spread_cents: 30`.** Genuinely dead on the live path
   (C14) — but wiring it would have changed **zero** trades: ribbon spread at every flip exit
   was 33.87–56.84c, all ≥30. Delete it or document it as dead.

## Open / unverified — ranked

1. 🚨 **A real safe-2 fill with NO decision row** — core ledger has 9 PLACED vs 10 core broker
   buys; bold-2 reconciles 5/5, **safe-2's 09:58 P773 buy has no producer** (rows 09:56–09:59
   all read `verdict: HOLD, side: null`). Strongest surviving candidate for a literal
   second execution path (L244 class). No lane owned it. Probe: trace its `client_order_id`.
2. **Why did the ribbon read BULL all day on a −2.33 close?** Every lane read ribbon
   *consumers*; **nobody read the producer** (`backtest/lib/ribbon.py`). If it mis-classifies
   an efficient fade, both M1 fixes mask an upstream defect.
3. **The hold-through counterfactual blocks the M1 fix.** `backtest/data/options/` has **zero**
   `SPY260812*` files; `/v1beta1/options/bars` returns 403 "OPRA agreement is not signed".
   Must backfill via `/v1beta1/options/trades` before pricing "what if we held the 18."
4. **Fleet arms can trade a signal the CORE vetoed** — risky-1's 13:24/13:32 entries came off
   core ticks whose own verdict was `SKIP_STRUCTURE_VETO`.
5. **Rule 7 (PDT) is inert on every fleet arm** — risky-1 logs `day_trades: 0,
   day_trades_true: 12, pdt_enforced: false`. Reads as armed in the ledger; is not.
6. **A BTC/USD round trip on the core Safe options account** at 20:45:04. Crypto is gym-only.
7. **Latent live spread $196–292/day at this entry rate.** Measured paper slip was −$1.98 with
   a 90% CI of −$531..+$499 (268× the point estimate) — **"we pay no spread" is a property of
   Alpaca's paper simulator, not a measurement.** Against a $100–200/day/arm target this is the
   figure that makes the book unviable at `GAMMA_CORE_ARMED=1`. Live-arming checklist item.

## Shipped tonight

**Restored risky-1's selectivity gate** (`accounts.json`: added `min_triggers: 2` +
`require_confluence_or_sequence: true` alongside the existing `full_send: true`). Reverts the
`e28d210c` accidental deletion; orthogonal key families so full-send stays armed. 3 new guards
in `test_full_send_arm.py`, RED-proofed by re-injecting the exact mutation (3 fail → restore →
29/29 green). **Not sold on paper dollars** (+$70, worse than random) — sold on reverting an
unintended deletion, removing 12 entries of real spread friction paper doesn't charge, and
making an experiment falsifiable whose lane has produced 0 of 66 lifetime placements.
