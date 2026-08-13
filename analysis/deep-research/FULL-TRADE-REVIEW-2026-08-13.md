# FULL TRADE REVIEW — 2026-08-13

> J directive: *"full review on every single trade we did today from all angles. fix all issues
> like account sizing being wrong. analyze the winners, and figure out why we got into so many
> losers and how we could either sit out or lose less. and the winners figure out how we could
> manage them better, buy more contracts to maximize profit."*

**Method.** Every filled SPY option order from all 5 arms, FIFO-matched into discrete round trips.
Price paths rebuilt from ~500,000 real OPRA trade prints (the options *bars* endpoint returns
`403 OPRA agreement is not signed`; the *trades* endpoint works, but only if the `end` parameter
is omitted — see DATA ACCESS below). No replay engine, no simulator. Broker fills only.

---

---

## ⚠️ SUPERSEDED IN PART — read DEEP-REVIEW-2026-08-13-MULTIAGENT.md first

A 36-agent adversarial review (7 angles, every finding refuted-or-survived by an independent
reviewer) corrected this document's HEADLINE. The per-trade forensics below stand; the framing
and the significance claim do not.

**1. There were not 15 trades. There were 5 signal EVENTS**, mechanically fanned across arms —
proven by identical `core_tick_id` on all three fleet arms entering at 09:52:04. All five events
are sign-homogeneous, so **8W/7L is really 2W/3L.**

**2. The "+25% in 4-6 minutes, zero overlap" separator is NOT significant.** Fisher p = 0.000155
at n=15, but **p = 0.100 at n=5** — the honest unit. Worse, the winner half is near-tautological:
minimum winner *realized* return is +46.77%, and realized <= MFE by construction. The only
empirical content is the loser side (max loser MFE +23.71%), which rests on **3 events**. It is
also partly measuring ENTRY SLIPPAGE rather than signal quality — event C is one price path
peaking at 1.20, entered at 0.97 / 1.13 / 1.14, producing MFE +23.7% / +6.2% / +5.3% purely from
a 17.5% entry-price spread.

**3. Event A alone is +$1,985 = 114% of the day's net. Ex-A, 2026-08-13 is a -$237 LOSING day.**

**4. Section 5c's "worst-case ordering drawdown" is not an observed drawdown** — it is
sum(losses)/equity under a reordering that did not happen, i.e. a deterministic function of total
losses. On n=1 with known outcomes it cannot be distinguished from fitting to which trades lost.

**5. The actual #1 finding is different and was not in this document:** five arms run five
different entry-gate sets and no inventory exists of which gate is armed where. That moved $942
today in two opposite directions.

## 1. The ledger — 15 round trips, +$1,748

| # | in | out | arm | strike | Q | entry | exit | P&L | MFE | MAE | capture eff |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 09:51 | 10:42 | safe-2 | 777C | 3 | 1.03 | 2.14 | **+$332** | +162% | −6% | 66% |
| 2 | 09:51 | 10:42 | bold-2 | 777C | 5 | 1.01 | 2.08 | **+$534** | +167% | −4% | 63% |
| 3 | 09:52 | 10:42 | safe-3 | 777C | 3 | 1.09 | 2.25 | **+$348** | +148% | −11% | 72% |
| 4 | 09:52 | 10:42 | risky-1 | 777C | 5 | 1.08 | 1.89 | **+$405** | +150% | −10% | **50%** |
| 5 | 09:52 | 10:04 | risky-3 | 779C | 10 | 0.36 | 0.73 | **+$366** | +117% | −14% | 87% |
| 6 | 10:27 | 10:41 | risky-3 | 781C | 10 | 0.36 | 0.27 | −$90 | +11% | −31% | — |
| 7 | 11:41 | 11:56 | bold-2 | 776C | 5 | 0.97 | 0.80 | −$85 | +24% | −23% | — |
| 8 | 11:42 | 11:57 | safe-3 | 776C | 3 | 1.13 | 0.83 | −$90 | +6% | −34% | — |
| 9 | 11:42 | 11:45 | risky-3 | 778C | 10 | 0.32 | 0.24 | −$80 | +6% | −28% | — |
| 10 | 11:42 | 11:57 | risky-1 | 776C | 5 | 1.14 | 0.83 | −$155 | +5% | −34% | — |
| 11 | 12:41 | 12:56 | safe-2 | 776**P** | 3 | 0.63 | 0.40 | −$69 | +3% | −40% | — |
| 12 | 12:41 | 13:12 | bold-2 | 776**P** | 5 | 0.64 | 0.24 | −$200 | +2% | −66% | — |
| 13 | 14:36 | 15:13 | safe-2 | 777C | 3 | 0.66 | 1.26 | **+$181** | +127% | −9% | 72% |
| 14 | 14:37 | 15:14 | safe-3 | 777C | 3 | 0.65 | 1.31 | **+$199** | +131% | −6% | 78% |
| 15 | 14:37 | 14:59 | risky-1 | 777C | 5 | 0.65 | 0.95 | **+$152** | +69% | −6% | 68% |

**8 winners +$2,517 · 7 losers −$769 · net +$1,748.**

---

## 2. THE DISCRIMINATOR — the single most important finding

**Time from entry to the first +25% tick:**

| | result |
|---|---|
| trades 1, 2, 3, 4, 5 | **+25% in 5–6 minutes** |
| trades 13, 14, 15 | **+25% in 4–5 minutes** |
| trades 6, 7, 8, 9, 10, 11, 12 | **NEVER** |

**8 of 8 winners cleared +25% inside six minutes. 0 of 7 losers ever cleared it at all.**
Zero overlap. The MFE distributions do not touch: every winner ≥ +69%, every loser ≤ +24%.

### What this does and does not buy

Applying it as an EXIT rule ("flatten anything not +25% by entry+10min") is worth **+$117** on
today's tape — small, because the existing structure stop was already exiting at similar prices.
**I initially over-read this as a windfall; it is not.**

Its real value is as a **signal-quality readout, not an exit**: within six minutes of the first
fill the engine knows whether the signal it just acted on is live. That is the input a
"should I take the NEXT signal today" decision needs, and nothing currently consumes it.

---

## 3. WINNERS — how they were managed

**Capture efficiency (realised move / MFE) ranged 50%–87%, mean ~70%.** We keep roughly two
thirds of the maximum move. That is not bad, and it is not the problem.

### 3a. The lower TP1 captured LESS, not more

Trade 4 (risky-1) has the **+50%** TP1; trades 1–3 have **+100%**. On the same contract, same
minute, same direction:

| arm | TP1 | capture eff | P&L per contract |
|---|---|---|---|
| safe-2 | +100% | 66% | $110.67 |
| bold-2 | +100% | 63% | $106.80 |
| safe-3 | +100% | 72% | $116.00 |
| **risky-1** | **+50%** | **50%** | **$81.00** |

On a +150% move the low TP1 is a **handicap** — it sells the majority of the position into the
first third of the run. This is the exact mirror of the 14:36 trade where the high TP1 banked
nothing on a +68% move. **Neither fixed level is right; the level has to be derived.** That is
the cost-recovery finding (COST-RECOVERY-SIZING-2026-08-13.md), independently confirmed here
from the winner side.

### 3b. What the winners left behind

- Trade 5 (risky-3 779C) exited 10:04 at +102%. The contract peaked **1.23 (+242%) at 10:32**.
- Trade 15 (risky-1 777C) exited 14:59 at +47%. The contract reached **1.50 (+131%)** after.
- Trades 1–4 exited 10:42 at ~+106%. The contract peaked **2.26 (+119%)** shortly after.

The 09:51 cohort captured near the peak. The two early exits (5 and 15) each left more than they
took. Both were **runner exits on a trailing stop** while the underlying was still trending.

---

## 4. LOSERS — why we entered, why we exited, and what happened next

### 4a. They never worked. Not one.

Every losing trade's MFE was **≤ +24%**, five of seven were **≤ +11%**. These were not trades that
went well and then reversed. They were dead from the first minute.

### 4b. The 11:42 cluster was stopped by a STRUCTURAL signal, not the premium cap

Three arms, three different entries, all exiting within 60 seconds at effectively the same price:

```
bold-2   entry 0.97 -> exit 0.80 @11:56  = -17.5%
safe-3   entry 1.13 -> exit 0.83 @11:57  = -26.5%
risky-1  entry 1.14 -> exit 0.83 @11:57  = -27.2%
```

A per-position premium stop would have exited each at `entry x 0.5` = 0.485 / 0.565 / 0.570.
**A common exit price across different entries is a shared structural signal.** The −50%
catastrophe cap never came close to firing.

### 4c. And then the 776C ran +154%

Path of SPY 776C after the 11:42 entry (blocks, ET):

```
11:45  low 0.66  <- we were stopped here, at 0.80-0.83
12:30  high 1.17
13:00  high 1.60
13:15  high 1.65  (+70%)
14:30  high 1.80
14:45  high 2.00
15:00  high 2.46  (+154%)
```

Held to 15:45 those four trades are **+$1,433 instead of −$410** — a $1,843 swing, larger than
the entire day.

### 4d. But "hold longer" is NOT the lesson — the puts prove it

Trades 11 and 12 were **puts**. Held to the close they go to **0.03** (P776 day low, 15:13) —
a total loss, far worse than the −$269 actually taken.

Same session, same "hold longer" rule, opposite outcomes. The variable that separates them is
**whether the directional call was right**, which is not knowable at the stop. **Today's tape
does not support a hold-longer rule, and claiming otherwise would be hindsight.**

What it DOES support is narrower and mechanical:

> The structure stop fired at **−18% to −27%**, inside the −50% cap and inside this repo's own
> measured **−36% 10-minute MAE noise floor** (`project_noise_floor_entry_exit_matrix_2026_07_08`).
> We are exiting inside the noise band. That is a documented lesson **re-occurring**, and today
> it is attached to a $1,843 counterfactual on the call side.

### 4e. Why so many losers: three waves, one cause each

| wave | trades | cause |
|---|---|---|
| 10:27 | 6 | re-entry 45 min after the winner, chasing a higher strike (781C) into a fading move |
| 11:42 | 7, 8, 9, 10 | **4 arms took the same signal simultaneously** — one bad signal became four losses |
| 12:41 | 11, 12 | direction flip to puts while the underlying was building the afternoon rally |

**The 11:42 wave is the structural problem: correlated arms.** Five arms are RISK PROFILES, not
strategies (per doctrine) — so a single bad signal is taken by all of them at once. There is no
diversification in the book; there is leverage on signal quality.

---

## 5. SIZING — the fix J called for, and its real risk

### 5a. The defect (already root-caused, COST-RECOVERY-SIZING-2026-08-13.md)

`min_contracts = 3` was authored when an account held ~$2,000. It is the only sizing knob in
`params.json` that is an ABSOLUTE COUNT — every sibling (`per_trade_risk_cap_pct`,
`daily_loss_kill_switch_pct`) is a PERCENTAGE and rescales itself. Equity is now $5,501.
`fleet_executor._apply_recency_min_sizing` then uses that floor as a **CEILING**
(`clamped = min(qty, min_contracts)`), so a risk gate that computed 8 was overridden back to 3.

### 5b. What equity-proportional sizing would have produced — on EVERY trade, winners and losers

| | |
|---|---|
| Actual day | **+$1,748** |
| At the risk cap each arm already permits | **+$9,734 (5.6x)** |

That is not cherry-picked: the losers scale up too (trade 12 becomes −$1,720).

### 5c. The honest risk statement

Today's cumulative P&L never went negative on any arm — **but that is ORDERING LUCK.** The 09:51
winners landed before every loser. Reverse the order:

| arm | all losses at proportional size | as % equity | kill switch |
|---|---|---|---|
| bold-2 | −$2,196 | **−39.8%** | limit −50% |
| risky-3 | −$1,245 | −24.8% | limit −50% |
| risky-1 | −$713 | −13.2% | limit −50% |
| safe-2 | −$598 | −10.9% | limit −30% |
| safe-3 | −$360 | −7.5% | limit −30% |

No kill switch trips, but bold-2 sits at **−40% of equity** on a day it finished green.
And the standing counter-evidence must be stated: **C31 — J's 667 real trades: 1–2 lots
+$4,576, 3+ lots −$17,461.** Sizing UP is the documented historical killer.

### 5d. Therefore the fix is a RESTORATION, not an increase

The clamp's *intent* was "trade small while the edge is unconfirmed." At $2,000 equity, 3
contracts at ~$1.03 was **15.4% of equity**. At $5,501 the same 3 contracts is **5.6%** — the
clamp is now 2.75x tighter than designed. The fix expresses the floor as the equity FRACTION it
originally encoded, so the policy means today what it meant when it was validated.

**This is deliberately NOT the 5.6x number.** It restores 3 -> 8 contracts (the risk gate's own
answer), not 3 -> 16.

---

## 6. DATA ACCESS defect found during this review

`https://data.alpaca.markets/v1beta1/options/bars` returns **`403 {"message":"OPRA agreement is
not signed"}`** on this key. The `trades` endpoint works — but ONLY if the `end` parameter is
omitted; including `end` returns the same 403.

Any fetcher that catches broadly and returns `None`/`[]` here reports **"no data"** for what is
actually **"access denied"** — precisely L241. Worth an audit of every options-bars consumer.

---

## 7. What NOT to conclude from today

- **Not** that we should hold losers longer. The puts refute it inside the same session.
- **Not** that TP1 should simply be lower. Trade 4 had the low TP1 and captured the LEAST.
- **Not** that 5.6x sizing is free. It is ordering luck away from a −40% arm day.
- **Not** that the +25% rule is worth money as an exit. It is worth **$117** today; its value is
  as a signal-quality readout.
- n = 1 day, 15 trades. Everything here is a hypothesis with a live anchor, not a validated edge.
