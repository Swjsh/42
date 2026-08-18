# GOING LIVE ON ONE ACCOUNT — what the 5-arm experiment is actually teaching us

> J, 2026-08-18: *"when we go live, we're only gonna have one account. So we need to keep that
> in mind as we do this day to day on what is winning and what's making money and make sure we
> have all the gates and everything documented… instead of safe-2 and bold-2 buying three and
> five respectively, we would probably just buy like fifteen."*
>
> Status: **PLANNING / DOCUMENTATION ONLY.** Nothing here is armed, scheduled, or ratified.
> Live arming needs J (OP-0 #1).

---

## 1. The reframe that matters

Today read as "+$162 across two arms." On one account it is simply:

> **one signal → 8 contracts of 768P → +$162**

The five arms are **not a portfolio**. `LEVER-CORRELATION-2026-08-06` measured them at
**r = 0.846 with 95.7% sign agreement** — "one bet in five sizes" — and the 2026-08-16 forward
check confirmed the correlation persists. So the arms are a **measurement instrument**, not
diversification. Consolidating loses nothing real; it just makes the size explicit.

**The consequence to internalise:** every per-arm P&L we quote is one decision sampled five
times. Book-level numbers overstate `n` by roughly 2.3–3.5x (measured). The live account will
feel *exactly like* one arm — same win rate, same drawdowns — just scaled.

## 2. Can one account hold multiple positions? YES — and this is the real design question

J: *"we could buy five 768 puts, and then we could also potentially buy one lottery ticket."*

Nothing structural prevents it. What currently prevents it is **policy**, and that policy is
worth keeping deliberate rather than inheriting by accident:

| guard | what it does today | one-account implication |
|---|---|---|
| `fb.is_flat_spy_options` (C11/L237) | refuses an entry unless the account is FLAT | **This is the blocker.** A second concurrent position is impossible while this holds. |
| `min_entry_premium` = 0.30 | refuses sub-$0.20-toxic fills | **This is what blocked the lottery ticket today** (risky-3's 766P @ $0.06). |
| `min_contracts` flat 3/5 | fixed size, no equity scaling | becomes "how many on the one account" |
| Rule 6 per-trade risk cap | 30% Safe / 50% Bold of equity | must be enforced across the SUM of concurrent legs, not per-leg |

**The flat-check is load-bearing, not incidental.** It exists because a manual fill once
NOT-FLAT'd the engine and blocked entries (C11), and because the 08-12 churn day showed
*concurrent opposite plans arbitrated only by "am I flat"* losing **−$574 (64.5% of that
book)**. Relaxing it without a replacement arbiter re-opens that exact wound.

**If we want a core + lottery structure, the honest design is:**

1. **Named legs, not a free-for-all.** A position carries `{leg_role: "core" | "lottery"}` with
   its OWN size cap and its OWN exit shape. The flat-check becomes "am I flat *in this role*."
2. **The lottery leg needs a different premium floor, not an exemption.** The $0.30 floor is
   correct for a *managed* position — a −8% stop on a $0.06 contract is half a cent, which is
   noise, not risk. A lottery leg is explicitly **unmanaged**: no stop, max loss = premium paid,
   hold to target or zero. That is a different instrument and deserves its own rule.
3. **Rule 6 applies to the SUM.** Core notional + lottery notional ≤ the per-trade cap. The
   lottery leg is carved *out of* the risk budget, never added *on top of* it.
4. **It must be earned by evidence.** Today's lottery ticket would have been a 766P at $0.06 on
   a day SPY moved under a point — it expires worthless. One appealing story is not a mandate;
   the strike matrix is the first real evidence and it is still running.

## 3. One account or two? — recommendation: ONE live, the rest stay paper

J: *"I prefer to do one, but just thinking out loud."* Agreed, and here is the argument:

- **Two LIVE accounts buy no information.** At r = 0.846 they produce near-identical results;
  you would pay two spreads and two fee schedules for a duplicate sample.
- **Two live accounts DO double the operational surface** — two kill switches, two breakers,
  two settlement ledgers, two day-trade counters, two reconciliations.
- **The experiment does not need real money to continue.** Keep the paper fleet running beside
  the one live account: same shared signal, different gates, zero capital at risk. That
  preserves exactly the isolation J wanted "for data and documentation purposes."

> **Proposed shape: ONE live account (the product) + the paper fleet (the laboratory).**
> The laboratory keeps answering "which gate set wins." The product trades only the gate set
> that has already won.

## 4. The gate map the live account must inherit

Every gate that fired this week, what it did, and whether the live account should carry it.
**This is the table to keep current** — it is what "make sure we have all the gates documented"
means in practice.

| gate | fired | effect observed | carry live? |
|---|---|---|---|
| `min_triggers >= 2` (risky-1, safe-3) | 17x on 08-18 | blocked the winner (1 trigger only) | ⚠️ **open** — blocked a winner two days running |
| `min_entry_premium` 0.30 (risky-3) | 10x on 08-18 | blocked a $0.06 lottery ticket | ✅ yes for the core leg; a lottery leg needs its own rule |
| filter 8 (VIX > 17.30 and rising) | dominant blocker both days | kept us out of most mid-VIX setups | ✅ yes — the matrix says mid-VIX loses at every spread threshold |
| filter 6 (ribbon spread ≥ 30c) | sole blocker 4x on 08-17 | admitted the trade that paid once spread opened | ✅ yes, pending the regime study |
| structure veto (safe) | 17x on 08-17 | blocked safe from the +$360 winner | ⚠️ lagging classifier — exhibit filed |
| `is_flat` (C11) | continuous | prevented 22 duplicate entries on 08-18 | ✅ **yes — load-bearing** |
| conviction | shadow, 100% would-block | would have vetoed every winner | ❌ **stays disarmed** |

## 5. ⚠️ Honest finding on conviction v2 — it fixes blindness, NOT discrimination

The v2 trendline anchor shipped today (shadow) because v0 scored both live winners 0/8 by
construction. **But measured against every closed round trip on the 12 days that have trendline
history:**

| group | n | had a quality-agnostic trendline within $0.60 of the strike | median gap |
|---|---:|---:|---:|
| winners | 28 | **27 (96%)** | $0.01 |
| losers | 75 | **64 (85%)** | $0.01 |

**Trendlines sit next to almost every entry we take, winner or loser.** Proximity alone is not
an edge. So v2 makes conviction *able to see* the lane that pays — a necessary fix — but on this
evidence it would credit the losers just as readily.

All of v2's discriminating power therefore has to come from the **quality bar** (respects ≥ 20,
violations ≤ 6), and that bar **could not be tested here**: the historical
`trendline-log.jsonl` carries anchors and projected values but no `respect_count` /
`violations`, and this test used the strike as a spot proxy. **The quality bar is unproven and
must earn its keep forward**, in shadow, on the paired v0/v2 join.

Stated plainly because it cuts against a change made an hour earlier: **do not read v2 as
"conviction fixed."** Read it as *"conviction can now score the right lane; whether it can rank
that lane is an open question with a measurement plan."*

## 6. What would have to be true before the live account sizes up

1. Conviction (v0 or v2) demonstrates **separation** — blocked trades measurably worse than
   allowed trades — over enough post-fix paired rows to mean something.
2. `min_contracts_equity_scaled` re-arms **only** on that validated gate (standing rule from
   the 08-15 handoff).
3. The strike question is settled by the matrix, not by intuition.
4. The regulatory picture is confirmed — see `REGULATORY-BROKER-LANDSCAPE-2026-08-18.md`.
   Day-trade counting and settlement mechanics constrain re-entry, which constrains everything
   above.

Until then the live account trades the **current, boring, working** configuration: one signal,
flat size, tight stops, one position at a time. That configuration made money two days running.
