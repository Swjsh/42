# Gate revalidation filing — 2026-08-21

> Filed after the 2026-08-21 book day (−$585 / 20 fills / 5 arms). Every number below is
> read from `automation/state/gate-registry-status.json` (run_date 2026-08-21, window
> 2026-07-17..2026-08-20), produced by `Gamma_GateExpiryCheck` via `walk_exit_manager`
> (`replay_soundness: sound`). Nothing here changes live behaviour.

## Why this filing exists

`gate_recency_report.py` has carried `recommendation: "REVALIDATE"` with
`revalidation.status: "NOT_FILED"` for weeks. The machinery was working; the filing step
was the gap. This is that step.

**It also redirected the investigation.** I came to revalidate `block_bull_1100_1200` —
the gate that blocked Safe through the winning 11:37 wave and released it into the worst
one. The instrument says that gate is the *least* actionable of the three, and named two
bigger problems.

---

## 1. `core_strategy_bear` — **RED**. This outranks every gate below.

> real-fills expectancy **−$16.71/trade, n=31** on the freshest window — *the core
> strategy itself is losing*, not a gate costing money.

This is the honest headline for 2026-08-21, and it is not a gate problem, a wiring
problem, or a theta problem. **The bear side is unprofitable on recent real fills.**
Today's wave 1 (trendline-only BEAR, −$449 book-wide) is one draw from that distribution,
not an aberration.

Note the divergence disclosed in the same record: the replay supplement (Safe shape,
engine-sim) reads **+$116.89/tr on n=21** over a comparable window. Real fills say
−$16.71; the simulator says +$116.89. **That gap is itself a finding** — it is the
sim-accuracy question OP-16 exists for, and it means no bear-side decision should rest on
replay evidence until the two are reconciled.

**Action:** no flip, no disarm. Strategy-level verdict; needs the full recency battery,
not a gate tweak. Escalated to STATUS.md automatically. Queued, not executed tonight.

## 2. `require_bearish_fill_bar` — **RED**, and it is the most expensive gate in the book

| | |
|---|---|
| refused cohort | **n=37 events over 16 days**, WR 45.9% |
| expectancy | **+$60.28/trade**, total **+$2,230** |
| concentration | best day **$1,405** → **drop-best-day $825** (≈ +$24/tr over 15 days) |
| day split | **9 win days / 7 loss days** |
| scope | **bold only** (all 37 events) |
| evidence age | **65 days** against a 21-day interval |

It fired 3× today (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`), including on Bold at 09:52.

Unlike most RED findings, this one **survives its own best day**: +$24/trade drop-best
with 9 of 16 days positive is a real signal, not one session.

**But the counterfactual is naive and must be labelled as such.** The checker replays
*refused* signals through the exit core. It does **not** model what else would have
changed had those trades been taken — most importantly `NOT_FLAT`, which would have
blocked later entries in the same wave. On a day like today, where wave 3 was the only
winner, a gate that let Bold into wave 1 might have blocked it out of wave 3.
**A refused-cohort P&L is an upper bound on a gate's cost, never its true cost.**

**Action:** pre-register an A/B that replays the **whole book path**, not the refused
cohort in isolation, scored on OP-11 gates (OOS positive, WF ≥ 0.70, sub-window stable,
anchor no-regression). Do not flip on the refused-cohort number alone.

## 3. `block_bull_1100_1200` — **YELLOW**, not yet actionable

| | |
|---|---|
| refused cohort | n=4 events over 3 days, WR 75% |
| expectancy | +$64.35/trade, total +$257.40 |
| concentration | best day **$203.40 of $257.40 = 79%** → drop-best ≈ +$18/tr on 3 events |
| evidence age | **64 days** against a 21-day interval |
| original ratification | **IS n=11 / OOS n=1** (2026-06-18) |

Today it blocked Safe 18 raw fires (11:06–11:50), spanning the 11:37 wave that paid every
other arm, then released Safe into the 12:26 wave that lost $494 book-wide. That reads
damning — and at **n=4 events with 79% of the P&L in one day it remains below the n=10
confirm floor**, exactly as the checker says. One session is not evidence, and the fact
that the session was today does not change that.

**Action:** leave armed. Re-read at n ≥ 10. Staleness filed, not a verdict.

### The Safe/Bold asymmetry is an accident, and should be a decision

`heartbeat_core.py:953` builds gate params as
`{k: account_params[k] for k in GATE_KEYS if k in account_params}` — a **membership**
filter, not `.get(k, default)`. `automation/state/aggressive/params.json` simply has no
`block_bull_1100_1200` key, so the gate is structurally dead on Bold. The gate code is
account-agnostic; nothing ever decided Bold should be exempt.

`automation/state/gate-arm-matrix.json` already flags the class: *"2026-08-13: $942 moved
by gates armed on some arms and not others, in two opposite directions."*

**Action:** decide deliberately and record it. An accidental scope is not a scope. Not
changed tonight — arming a gate on a new arm is a live behaviour change.

---

## Filing status

| gate | verdict | age | actionable now? |
|---|---|---|---|
| `core_strategy_bear` | **RED** | 20d | Escalated to STATUS.md; strategy-level, queued |
| `require_bearish_fill_bar` | **RED** | 65d | **Yes — pre-register whole-book A/B** |
| `block_bull_1100_1200` | YELLOW | 64d | No (n=4 < floor 10); staleness filed |
| `free_model_veto` | STALE_UNVERIFIED | 43d | Inert since 2026-08-12; no action |
| `fleet_score_ladder_floor` | STALE_UNVERIFIED | 25d | Not measured; queued |
| `fleet_hard_skip_verdicts_override` | STALE_UNVERIFIED | 29d | Not measured; queued |

**Nothing in this filing changes live behaviour.** Every candidate is gated on OP-11, and
the `core_strategy_bear` RED means bear-side changes specifically need the
real-fills-vs-replay divergence reconciled first.

## Withdrawn from the 2026-08-21 autopsy

The autopsy ranked the trendline-only bypass as cause #1. Measured on **real fills** that
night (`Gamma_TrendlineTierRail`, commit `97af7375`) the ordering inverts: trendline-only
−$1.88/tr drop-best-day vs rest-of-book −$36.29. The bypass was bad on 08-21 (n=1); it is
not the book's villain. Three populations now disagree in sign on that cohort, which is
why it now has a standing rail rather than another one-off study.
