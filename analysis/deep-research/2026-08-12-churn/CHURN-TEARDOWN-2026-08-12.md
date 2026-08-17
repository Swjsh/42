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

---

## POST-TEARDOWN CORRECTIONS (same night, after the data memo + hold counterfactual)

**1. Open item #3 (OPRA backfill blocked) is FALSE — we were never blocked.** A dedicated
research agent probed every option endpoint live on both keys: `/v1beta1/options/bars` returns
**200 at $0** — 1-min AND 5-min, same-day 0DTE included, history to Feb 2024, 200 req/min.
The recorded 403 "OPRA agreement is not signed" exists ONLY on `quotes/latest?feed=opra` (an
explicit feed override no repo script uses) and was misattributed to bars. Historical option
QUOTES don't exist at any Alpaca tier (the /quotes 404 is a product gap, not permissions) —
use /trades for spread work. Also: stock SIP is FREE for data >15 min old; the IEX premarket
fallback was sampling **3 bars where SIP has 274 (1% coverage)**. Fills-vs-bars validation:
85/85 of today's fills matched a 1-min bar, ~4c mean abs deviation, +1.2c buy-side skew (paper
fills at the ask vs trade prints). Queued fixes: unfreeze `fetch_option_data.py`'s hardcoded
19-contract list (frozen 2026-05-07 — the actual cache-gap bug), route its hardcoded UTC-4
offset through `lib/et_frame.py` (DST-artifact recurrence, also in `_option_bars_1min_cache.py`),
switch premarket level reads to SIP.

**2. The hold-vs-dump question is now PRICED (real 1-min/5-min bars, all 8 contracts, $0):**

| counterfactual | P&L | vs actual −$890 |
|---|---:|---:|
| every position held to 15:50 | **−$10,313** | −$9,423 worse |
| ONE trade per arm/direction (first entry, held to 15:50) | **−$2,845** | −$1,955 worse |

Caveat: both are full-hold bounds with no intraday management (a managed hold with TP1/trail
sits between), and 15:50 on 0DTE is near-intrinsic. But the direction is unambiguous.

**Consequences:**
- **R3 option (b) — exit-side "hold through the ribbon dump" — is KILLED for this tape.** The
  18 ribbon-dumped puts held to close get massacred (the 09:46 771P @0.82 held = −$632; SPY
  recovered to 772.40 and theta did the rest). The single-tick dump, wrong by construction,
  functioned as a cheap fast stop on a mean-reverting day. **R3 proceeds ENTRY-SIDE only:
  don't OPEN positions the exit predicate already rejects.**
- The teardown's own suggestive cell (+$60 dumped vs −$579 aligned-held) pointed the wrong
  way once priced — reinforcing the standing rule: no exit change ships on a suggestive cell
  without the hold counterfactual actually computed.
- **Entries were the loss mechanism in full**: morning entries mid-flush (not at range edges)
  lose under EVERY exit policy tested — dump fast (−$890), hold all (−$10.3k), trade once and
  hold (−$2.8k). The only winning line on 08-12 remains J's: one long at the 12:35 support
  touch at the RANGE EDGE. Entry location/conviction is the whole game — which is exactly what
  the conviction-ratchet design gates on (C1 named level, C4 range extreme).

---

## 2026-08-15 — this doc ANSWERS the handoff's "largest unexplained compositional shift"

The 2026-08-15 engine-review handoff flagged `ribbon_flip_back` going **4% → 22% of all closes**
as "the largest unexplained compositional shift in the book" and "an open lead nobody has
explained." It was explained here, the night it happened. Recording the join so the next
session routes here instead of re-deriving it.

**It is not a shift in exit behaviour. It is one out-of-population day.**

| window | closes | `ribbon_flip_back` | share |
|---|---:|---:|---:|
| PRE-stack (everything before 08-10) | 239 | 9 | 4% |
| POST 08-10..08-14 | 98 | 22 | **22%** |
| POST **excluding 08-12** | 59 | 4 | **7%** |

Per day: 08-10 **1**, 08-11 **3**, 08-12 **18**, 08-13 **0**, 08-14 **0**. Eighteen of the
twenty-two POST firings — and 58% of every `ribbon_flip_back` that has EVER fired (31 all-time)
— are 2026-08-12. Strip that one day and the "shift" is 7% vs 4% on n=4.

(Counting note: this table counts logged exit ACTIONS keyed on `reason`; the teardown above
counts broker POSITIONS and reports 1/4/21 for the same three days. Different units, same
mechanism, same magnitude. Neither was silently adopted for the other.)

**Two framing corrections for whoever inherits the handoff:**

1. **C28 ("ribbon flip is a LAGGING exit") does not explain this — it is the opposite.** These
   exits fired at a **1.0-minute median hold**, on the position's FIRST management tick. Not
   late: immediate, and immediate *by construction*, per M1 above — entry waives the ribbon
   check and the exit enforces it, so the position is born pre-invalidated. Reaching for C28
   here points at exit width, which is precisely the lever the same handoff concluded not to
   pull.
2. **The denominator moved too.** Only 98 closes POST vs 239 PRE-stack, so any surviving reason
   gains share mechanically as `premium_stop` collapsed 62% → 19%. Absolute count is the honest
   axis; share alone overstates every non-premium_stop row in that table.

**Still live as of 2026-08-15** — re-verified in code today, not recalled from this doc:
- Entry still waives it: `backtest/lib/filters.py` `if trendline_only_setup: blockers.remove(5)`
  — and filter 5 IS the ribbon check (`:1172` BULL-stacked, `:1487` BEAR-stacked, confirmed by
  reading the numbering rather than trusting the label).
- Exit still enforces it bare: `exit_actuator.py` `ribbon_stack == ("BULL" if side == "P" else
  "BEAR")`, whose own docstring says it is "Shared by heartbeat_core (core accounts) AND
  fleet_live (fleet arms) so the two exit paths cannot drift". The `heartbeat_core.py:877`
  reference above has since drifted to a different function — the shared predicate in
  `exit_actuator.py` is now the single authority, which is an improvement, but M1 is UNFIXED.

So **M1 remains the open bug**, and it is an ENTRY-side bug — consistent with this teardown's own
conclusion (R3 proceeds entry-side only) and with the handoff's verdict that the next lever is
entry selectivity, not exit width. Nothing about the 4% → 22% number argues for re-tuning exits.

---

## 2026-08-17 — CORRECTION to POST-TEARDOWN CORRECTION #1 (same-day bars)

Correction #1 above records: *"`/v1beta1/options/bars` returns **200 at $0** — 1-min AND 5-min,
**same-day 0DTE included**"*. The bolded clause is **wrong for the CURRENT session**.

Measured 2026-08-17 after the close, same endpoint, same key, same code path:

| contract | day | result |
|---|---|---|
| `SPY260814C00778000` | 2026-08-14 (past) | **200 — 81 bars** |
| `SPY260813C00777000` | 2026-08-13 (past) | **200 — 81 bars** |
| `SPY260817P00775000` | **2026-08-17 (today)** | **403 Forbidden** |

**The discriminator is the DAY, not the endpoint, the feed override, or the entitlement.** A
past 0DTE expiry is free and complete; the current session is 403 until it becomes a past day.

Consequences, both now handled in `fetch_option_data.topup_from_fills_ledger`:
- The nightly 16:25 fold **cannot** price the session it just finished. It picks those
  contracts up on the NEXT night — a one-day lag that is expected and self-healing.
- That lag must not be logged as a failure. Same-day contracts are now **deferred**
  (`deferred_same_day`) rather than attempted, and genuine failures now record their reason
  instead of incrementing an anonymous `failed` counter — the first version turned a
  diagnosable 403 into "failed=2" with no cause, which is how this nearly went unexplained.

Practical limit worth stating plainly: **a same-day hold-through counterfactual is not
computable on the day.** Any "should we have held?" question about today's fills has to wait
until tomorrow, or use a different data source.
