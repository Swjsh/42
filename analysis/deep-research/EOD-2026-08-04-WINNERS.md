# EOD 2026-08-04 — LENS 2: CRITICIZE THE WINNERS

_Generated after the close (16:07 ET verified via `et_clock.py`, `market_hours=False`). Real
broker fills + real 1-min OPRA only. n=1 trading day — **nothing here is armable on its own.**_

> **J's ask:** _"criticize the winners... make sure we are gonna trade like this on top days."_

---

## VERDICT — the three things that matter

1. 🚨 **PDT is not being enforced on the fleet, and it is not a rounding error.** `safe-3` and
   `risky-3` each used **6** day-trades today, `risky-1` **5** — against a limit of **3 per
   rolling 5 business days**. The fleet engine saw **0** for all three, every tick. Meanwhile
   the core `bold` account correctly counted its own and refused **21 ELITE setups** from
   12:26 ET. **A large share of today's record is not reproducible at a real broker.**
2. ⚠️ **The single biggest exit lever today was the chandelier trail, and it cost us.**
   `risky-1`'s runner survived to **$4.87 (+250%)** for exactly one reason: it is the only arm
   whose post-TP1 runner uses a **fixed BE floor** instead of a **trailing** lock. Every other
   arm's trail had ratcheted to ~2.54 and the ordinary 3.00→2.53 pullback at 10:18–10:21
   evicted all four. **Regime-conditional — PREREG only, not armed.**
3. ✅ **The late-fade 772C losses were NOT a missed standdown.** Every directional instrument
   said BULL and was *right* — SPY rose 771.13→772.34 through the whole window. The 772C still
   bled 1.22→0.90. That is theta, not direction. Hindsight, not a signal.

**Book capture: 20.3%** of the best single fixed policy (n=10 winners, one day). But read §1
before quoting that number — the denominator is a trend-day artifact.

---

## 0. Reconciliation (do this before believing any number)

| Source | Value |
|---|---:|
| Broker equity delta, 5 arms summed (`last_equity`→`equity`) | **+$3,617.85** |
| Task brief day total | +$3,617.19 |
| Fills-ledger position P&L (25 positions) | +$3,624.00 |
| **Difference (fills-ledger − broker)** | **$6.15 = fees/commissions** |

25 closed positions: **10 winners (+$4,735.00)**, **15 losers (−$1,111.00)**.
All 5 arms flat at the close. `$6.15` on 173 contracts ≈ $0.036/contract — consistent with
regulatory + exchange fees. **No unexplained P&L.**

---

## 1. (a) CAPTURE — what did we keep of what the winners offered?

### Book

| Metric | Value |
|---|---:|
| Realized (broker fills) | **$4,735.00** |
| Best single fixed policy — `hold_to_time_stop` | $23,380.00 |
| **CAPTURE (honest headline)** | **20.3%** |
| Hindsight per-trade shape-picking (NOT live-selectable) | 20.1% of $23,512 |
| 🔮 **ORACLE — sell 100% at the post-entry high. UNREACHABLE by any live rule.** | **17.7% of $26,766** |

**The 20.3% is real arithmetic and a misleading headline.** The only policy that beats us
materially is `hold_to_time_stop` — *never take profit, ride every position to the 15:50 time
stop*. On a day where SPY ripped ~762→772, every 0DTE call we touched finished deep ITM, so
"never sell" wins by 5x. That policy is the single most dangerous shape on the menu on a
reversal day: it has **no profit-taking at all**, only the −50% catastrophe cap.

It is also already in the **GRAVEYARD** — hold-longer book-wide is dead at −$451.50 across 21
winners. Today does not revive it; today is the counter-example that a trend day always
produces.

### 🐛 Instrument defect found and fixed (this changed the answer)

`EXIT_MENU` advertised 7 policies but delivered **6 distinct behaviours**. `trail_only_no_tp1`
set `tp1_premium_pct=999` (TP1 unreachable) while leaving `profit_lock_arm_scope="post_tp1"` —
so the profit lock could only arm on a TP1 fill **that never comes**, making `trail_pct=0.20`
a **dead knob**. It was a byte-identical copy of `hold_to_time_stop`: both returned exactly
**$23,380.00**, matching to the cent on all 10 winners.

That inflated the "hold longer" end of the axis to look **twice as corroborated as it was**,
and handed the capture denominator a menu containing a duplicate.

**Fixed** (`profit_lock_arm_scope: "full"` — a real production value, so the shape stays
live-executable and is now what its name always claimed). Effect:

| Policy | Before fix | After fix |
|---|---:|---:|
| `trail_only_no_tp1` | $23,380.00 *(fake — duplicate)* | **$554.00 (worst on the menu)** |

A genuine 20% trailing ride is *terrible* on 0DTE — it gets shaken out by ordinary noise. The
corrected menu says the opposite of what the broken one said.

### Per wave — where the money actually leaked

| # | wave | ET | arms | n | realized | best fixed policy | that policy | capture | 🔮 ORACLE (unreachable) |
|---:|---|---|---:|---:|---:|---|---:|---:|---:|
| 1 | `763C` | 09:50–09:58 | 5 | 5 | $2,534.00 | `hold_to_time_stop` | $19,908.00 | **12.7%** | $21,492.00 |
| 2 | `769C` | 12:28 | 4 | 4 | $2,192.00 | `hold_to_time_stop` | $3,394.00 | **64.6%** | $4,914.00 |
| 3 | `771C` | 13:24 | 1 | 1 | $9.00 | `all_out_at_tp1_50` | $210.00 | **4.3%** | $360.00 |

Wave 1 is the whole story: it holds **97%** of the theoretical gap. That is entirely the 0DTE
expiry effect — the 763C finished ~$9.26 intrinsic. Wave 2, entered midday with less runway,
captured a healthy **64.6%**. **Our exits are not broadly broken; they are "broken" only
against a policy that exploits same-day expiry on a one-directional day.**

Note the 11:52 769C cohort (all 4 arms, all losers) and the 12:28 769C cohort (all 4 arms, all
winners) are the **same strike 36 minutes apart**. Wave grouping is by time, not strike —
collapsing them would have averaged a losing cohort into a winning one and hidden both.

---

## 2. (b) THE BIG ONE — why did ONE runner reach $4.87?

**Answer: `risky-1` is the only arm without a trailing stop on its runner.** Ground truth from
the engine's own `exit_pass` rows (not a reconstruction):

| arm | TP1 | post-TP1 lock | runner stop path | runner exit |
|---|---|---|---|---|
| **risky-1** | +50% @10:06 (4 of 5) | **`fixed`** | parks at **BE 1.39**, *never ratchets* (79 ticks) | **`runner_target` @4.87 (+250%)** |
| safe-2 | +100% @10:16 | `trailing` | BE 1.35 → 2.329 → **2.55** | `trail` @2.48 |
| bold-2 | +100% @10:16 | `trailing` | BE 1.38 → 2.346 → **2.5415** | `trail` @2.50 |
| safe-3 | +100% @10:16 | `trailing` | BE 1.38 → 2.346 → **2.5415** | `trail` @2.51 |
| risky-3 | +40% @10:04 | `trailing` | ratcheted 11× 1.624 → **2.328** | `trail` @2.25 |

All five held the **same contract**. The 3.00 → 2.53 pullback at 10:18–10:21 was an ordinary
retrace. It hit every ratcheted trail and could not touch risky-1's breakeven floor. risky-1
then rode the second leg to 4.92 and left on its **`runner_target` (+250%)** — a hard target,
not an unbounded hold.

**Worth stating plainly: risky-1 had the WORSE TP1.** It banked 4 contracts at 2.12 while the
others got 2.68. **100% of its outperformance came from the runner surviving**, not from entry
or TP1.

### Book-wide counterfactual (winners only, real OPRA)

Each arm keeps its own TP1; only the post-TP1 runner changes:

| Runner policy | Winners total |
|---|---:|
| BE floor only (`fixed`) — what risky-1 ran | **$5,724.20** |
| Chandelier trail (`trailing`) — what the other four ran | $3,812.20 |
| **Delta** | **+$1,912.00** |

### ⛔ Graveyard check + verdict

- Graveyard kills *hold-longer book-wide*, *pre-TP1 trailing lock ×4*, *take-profit-earlier ×3*.
- **"Post-TP1 runner: BE floor only, no chandelier" is NOT in the graveyard.** It is a
  genuinely untested lever, distinct from the pre-TP1 lock that was killed.
- **But this is a WINNERS-ONLY sample on a TREND DAY.** Removing the trail lets losers run to
  the −50% cap instead of trailing out. The measurement says nothing about that side, and the
  losers outnumber the winners 15:10 today.

**→ PREREG ONLY. Not armed. Regime-conditional (trend-day).** Registered in §6.

---

## 3. (c) SIZING — headroom, PDT, and the honest ceiling

### SHIP C never fired, and it is not close

| | |
|---|---|
| SHIP C rule | `risky-3`, qty 10 when premium **< $0.50** |
| Fires today | **0** |
| **Lowest entry premium all day, any arm** | **$1.038** |

The cheapest contract we bought was **2.1× the threshold**. This is not "a quiet day for
SHIP C" — with ATM strike selection (ATM-TIER-EXTENSION-2K-10K, live today) a sub-$0.50 SPY
0DTE contract is structurally unlikely. **SHIP C may be unreachable by construction**, which
means its n≥10 kill-criterion will never resolve. Flagged, not changed.

### Sizing counterfactuals — MODELLED, not measured

> ⚠️ These scale the **realized per-contract** result. No market-impact model. Valid only if
> identical fills were available at the larger size.

| Scenario | Book P&L | vs actual |
|---|---:|---:|
| **Actual** (173 contracts, $16,465 notional) | **$3,624.00** | — |
| qty 10 on every entry (MODELLED) | $8,863.00 | 2.45× |
| Each arm's Rule-6 ceiling (MODELLED) | $12,924.40 | 3.57× |

| arm | realized | contracts | Rule 6 | capital left on table | qty10 (MOD) | Rule-6 ceiling (MOD) |
|---|---:|---:|---:|---:|---:|---:|
| safe-2 | $662 | 9 | 30% | $3,387.96 | $2,206.67 | $2,395.33 |
| bold-2 | $479 | 15 | 50% | $5,660.00 | $958.00 | $1,631.40 |
| safe-3 | $637 | 18 | 30% | $6,965.52 | $2,123.33 | $2,281.67 |
| risky-1 | $1,041 | 25 | 50% | $9,456.40 | $2,082.00 | $3,806.80 |
| risky-3 | $805 | 55 | 50% | $12,950.24 | $1,493.00 | $2,809.20 |
| **total** | **$3,624** | **173** | — | **$38,420.12** | **$8,863.00** | **$12,924.40** |

**Do not read 3.57× as free money.** Three reasons:
1. It scales the **losers** identically. Today's −$1,111 becomes ≈−$4,000 at the ceiling; a
   losing day of the same shape trips the Safe −30% / Bold −50% kill switches far faster.
2. **C31**: J's own 667 trades run **+$4,576 at 1–2 lots and −$17,461 at 3+ lots.** Sizing up
   is the documented killer, not the documented edge.
3. PDT — below — makes most of these entries illegal anyway.

### 🚨 PDT — the finding that outranks everything else here

The engine has **two different PDT paths and only one of them works.**

| arm | true 5-day count (`pdt_tracker`, broker fill history) | what the engine saw | limit | status |
|---|---:|---:|---:|---|
| safe-2 (core) | **4** | **4** | 3 | ⚠️ **counted, not enforced** — no PDT denial fired |
| bold-2 (core) | 3 | **3** | 3 | ✅ counted **and enforced** — denied 21 ELITE setups 12:26–13:48 |
| safe-3 (fleet) | **6** | **0** | 3 | ❌ **blind** |
| risky-1 (fleet) | **5** | **0** | 3 | ❌ **blind** |
| risky-3 (fleet) | **6** | **0** | 3 | ❌ **blind** |

Three distinct states, not two. All 21 `RISK_DENY_PDT` rows belong to the **`bold`** account;
**zero** belong to `safe`. So `safe-2` reached 4 day-trades with a *correct* count in hand and
was never stopped — consistent with the core Safe path gating on the **settled-cash** ledger
rather than margin PDT (`heartbeat_core.py:1918` describes exactly that split). Whether that is
still the right gate now that the account reads `multiplier=4` is **an open question I did not
resolve** — flagged, not answered.

**Root cause** — `automation/state/fleet/fleet_live.py:660`:

```python
day_trades = int(acct.get("daytrade_count", 0) or 0)
```

Alpaca returns `daytrade_count = None` on these accounts (verified live on all 5). `int(None or 0)`
is **0**, every tick, forever. The fleet PDT gate is structurally inert — `0 >= 3` is never true.

This is a **verbatim re-run of the bug fixed on 2026-07-06**, whose own code comment reads:
_"day_trades_used_5d was a hardcoded 0 that no component ever incremented (Rule 7 PDT was
structurally unenforceable — 0 >= 3 is never true)."_ That fix landed in `heartbeat_core.py`
(which now calls `pdt_tracker.fetch_day_trades_used_5d`) and **was never carried across to the
fleet path.** Same lesson, second location. C14/C34 shape.

A stale premise is embedded too: `heartbeat_core.py:1918` still asserts the core accounts are
**cash accounts, `multiplier=1`, PDT never applies**. All five arms read **`multiplier=4`**
today. The accounts were rebuilt 2026-08-02; that comment predates the rebuild.

**Cost, today, measured:** `bold-2` was PDT-denied from 12:26 and therefore **missed the 12:28
769C wave entirely** — the wave that paid the other four arms +$2,192. At bold-2's 5-lot sizing
and the wave's realized $125–158/contract, that is **≈ +$630 to +$790 of foregone P&L**, and it
is the *correct* gate doing its job.

**Why I did not ship the fix tonight.** Enforcing PDT correctly on the fleet **halts safe-3,
risky-1 and risky-3 immediately** — they are already at 5–6 against a limit of 3, so they would
take zero trades until the counts roll off. That is a fleet-wide trading halt, not a bug fix,
and it is a genuine fork (OP-0 #4): correct-and-drastic vs incorrect-and-productive. It needs
J. **Registered as PREREG-PDT-FLEET-PARITY in §6, top of the list.**

---

## 4. (d) THE LATE FADE — was there a live standdown signal after 13:30?

**No. This is hindsight, and I will not prereg it.**

The two losers: `safe-2` 772C 13:41 @1.22 → 14:01 @0.90 (−$96); `safe-3` 772C 13:42 @1.22 →
14:02 @1.16 (−$18).

Engine state through the window (core ledger, `safe` account, every 2 min):

| ET | SPY | VIX | ribbon | htf_15m | bull_score |
|---|---:|---:|---|---|---:|
| 13:20 | 771.135 | 16.33 | **BULL** | **BULL** | 10 |
| 13:30 | 771.22 | 16.42 | **BULL** | **BULL** | 9 |
| 13:40 | 771.37 | 16.48 | **BULL** | **BULL** | 10 |
| 13:46 | **772.34** | 16.54 | **BULL** | **BULL** | 11 |

Every directional instrument said BULL, held BULL, and **was correct** — SPY rose ~+1.2 points
across the window and made its high *after* both entries. There was no trendline break, no
ribbon flip, no HTF divergence, no VIX spike (16.33→16.55).

**The loss was not directional.** A near-ATM 772C bought at 13:41 with SPY at 771.87 bled
1.22→0.90 *while the underlying went up*. That is **theta + IV decay in the last two hours of
0DTE** — textbook **C3: SPY-price edge ≠ option edge.**

A "stand down after 13:30" rule would be fitted to two trades totalling −$114 on the single
best day on record. The correct lever, if any, is a **time-of-day / theta gate**, not a trend
gate — and `SKIP_LATE_ENTRY` (11 fires) and `SKIP_CONF_LVL_REC_AFTERNOON` (11 fires) already
exist on the core path. **No new prereg. Logged as an observation only.**

---

## 5. (e) ADJUDICATION — the 7× ENTER_BULL alarm, and its retraction

**Both the alarm and the retraction were wrong. They were wrong in the same way: each was a
conclusion drawn from outcome, on ~11 minutes of evidence, without reading the mechanism.**

What actually happened on `risky-3`'s open sequence:

| # | entry | exit | P&L | closed by |
|---|---|---|---:|---|
| 1 | 09:46 762C @1.75 ×8 | 09:47 @1.62 | −$104 | premium_stop |
| 2 | 09:50 763C @1.46 ×8 | 09:52 @1.41 | −$40 | **`premium_stop` @1.3724** |
| 3 | 09:54 763C @1.52 ×8 | 09:56 @1.34 | −$144 | **`premium_stop` @1.4288** |
| 4 | 09:57 763C @1.40 ×8 | 10:04 ×6 @1.99 / 10:23 ×2 @2.25 | **+$524** | tp1 / trail |
| | | **net** | **+$236** | |

**The re-entries were not the defect.** The three losses were all closed by a **−6% premium
stop** (`rstop` 1.3724, 1.4288 — visible in the engine's own exit_pass rows), firing within two
minutes each. That is a stop **inside the instrument's noise floor** — the same failure already
documented in memory (*10-min MAE −36% vs a −20% stop = winners stopped by noise*) and in
**C2/C3**. The signal was right the whole time; the stop kept chopping it.

The decisive comparison the alarm missed: **`risky-1` took the identical 09:50 763C signal two
seconds later and was never stopped out at all.**

| arm | 09:50 763C fill | stop | outcome |
|---|---:|---:|---|
| risky-1 | **1.39** | 1.3066 | survived → +$640 |
| risky-3 | **1.46** | 1.3724 | stopped 09:52 → −$40 |

The 09:50 signal bar ranged **1.17–1.50**. risky-3 paid 1.46 (near the bar high), risky-1 paid
1.39. **A 5% worse entry fill put risky-3's −6% stop inside the noise band and risky-1's
outside it.** Survival was decided by fill quality, not by re-entry policy and not by exit shape.

**Verdict on the two judgments:**

- **The 09:57 alarm ("a defect losing money", stage `RUN_VWAP=False`) — WRONG, and dangerous.**
  It would have disabled `vwap_continuation` 30 seconds before that strategy produced the
  single best trade of the day (+$524 on risky-3, and it is the same strategy behind risky-1's
  +$640). Diagnosis was "re-entry spam"; the mechanism was a too-tight stop. Acting on it would
  have cost ~$1,164 on this day alone.
- **The retraction — RIGHT CONCLUSION, WRONG BASIS.** It was ratified by the 5th trade paying,
  i.e. by outcome. Had the 5th also lost, the same reasoning would have "confirmed" the defect.
  A conclusion that flips on the next trade's P&L is not a finding.
- **What both should have been:** *"Three consecutive stop-outs in 8 minutes on an unchanged
  signal is a STOP-WIDTH question, not an entry-frequency question. Instrument it; change
  nothing mid-session (Rule 9)."* That is the reading the exit_pass rows supported in real time.

**Standing correction:** mid-session, the engine's *own* `exit_pass` stage labels are available
and decisive. Neither judgment consulted them. **No knob change is proposed from n=1** — the
stop-width question goes to prereg (§6), where it belongs.

---

## 6. PREREG REGISTER — nothing below is armed

| ID | Hypothesis | Bar to arm | Status |
|---|---|---|---|
| **PREREG-PDT-FLEET-PARITY** | Route fleet `day_trades` through `pdt_tracker.fetch_day_trades_used_5d` (as `heartbeat_core` already does) instead of the always-`None` `acct["daytrade_count"]`. | **Needs J** — correct enforcement halts 3 of 5 arms immediately (already 5–6 vs limit 3). Fork, OP-0 #4. | 🔴 **BLOCKED ON J — #1 item** |
| **PREREG-RUNNER-BE-FLOOR** | Post-TP1 runner uses a fixed BE floor instead of the chandelier trail. +$1,912 on today's winners. | Full-population A/B **including losers**, stratified by day archetype (trend vs chop). Trend-day-only effect must be shown to survive on chop. | 🟡 preregistered, not run |
| **PREREG-STOP-WIDTH-NOISE** | The −6% premium stop sits inside the 0DTE noise floor; widen or replace with structure-only on first-strike entries. Cost today: 3 stop-outs, −$288, on a signal that then paid +$524. | Full-population A/B vs the existing MAE/MFE pain ledger. Must not degrade the −50% catastrophe cap. | 🟡 preregistered, not run |
| — | *Late-afternoon standdown* | **Rejected as hindsight** — every instrument said BULL and was right; the loss was theta. | ⚫ not registered |

---

## 7. Shipped this session (all paper-path, guarded, RED-proofed, one-line revert)

| Change | File | Revert |
|---|---|---|
| **Data-integrity rail** — a run that loses any filled position to a bar-fetch fault is `DEGRADED` and publishes **no** capture ratio | `setup/scripts/winner_autopsy.py` | delete the `if degraded:` block |
| **Dead-knob fix** — `trail_only_no_tp1` arms its lock (`arm_scope: "full"`) so `trail_pct` is live | `setup/scripts/winner_autopsy.py` | restore `"post_tp1"` |
| **Wave grouping** — `assign_waves` / `wave_capture` + per-wave table | `setup/scripts/winner_autopsy.py` | drop the two functions + table block |
| **9 new guards** (33/33 green, each RED-proofed) | `backtest/tests/test_winner_autopsy.py` | — |

### 🐛 Why the nightly would have lied tonight

`Gamma_WinnerAutopsy` fires at **16:25 ET**. Alpaca does **not serve same-day-expiry OPRA bars
until ≈16:21 ET** — verified: 9 of 10 winners returned **HTTP 403** across the full 20/40/80/160s
retry ladder at 16:07–16:21, then every symbol fetched cleanly in 0.17s from ~16:30.

The old code counted the loss, printed a warning, and **still headlined
`capture_vs_best_policy=4.3%` computed from a single $9 trade** while $4,726 of winners sat
unfetched. That is C7 exactly: audit the OUTPUT, not the exit code. The rail now withholds the
ratio instead. **Follow-up (not done): move the task to ≥16:35 ET** — left for J since it
touches the schedule.

**Known instrument gap (not fixed):** `resolve_shipped_shape` mis-reconstructs the exit shape
for arms with an empty `accounts.json` `exit_patch` — it reported `safe-2`/`bold-2` as
`profit_lock_mode: fixed` and `tp1: 0.30`, while their own `exit_pass` rows show **trailing**
locks and TP1 firing at **+100%**. Every claim in §2 is taken from the `exit_pass` rows, not
from that reconstruction. Logged, not repaired.

---

## 8. Caveats — read before quoting anything here

1. **n = 1 trading day**, and the single best on record (~6.8× the prior best). Maximum
   selection pressure. Nothing here is armable on today.
2. **Winners-only conditioning.** §1 and §2 are computed over trades that *already won*.
   A policy's column answers "what would this shape have made on the trades our current exits
   happened to win" — **not** "what would this shape make". Switching changes which trades win.
3. **`hold_to_time_stop`'s 5× is a 0DTE-expiry artifact** on a one-directional day. It is the
   graveyard's already-killed hold-longer policy wearing a good day.
4. **All sizing counterfactuals are MODELLED** by scaling realized per-contract P&L. No
   market-impact model; they also scale the losers.
5. 🔮 **ORACLE columns are unreachable** by any live rule and are never mixed into a
   live-executable column. They bound the universe; they are not targets.
6. **Replay bias runs against us**: variants fill at their target price intrabar while real
   fills cross the spread, so true capture is likely *higher* than 20.3%.
7. **Structure stops are not modelled** in any replay (`last_closed_5m_close` is never
   supplied), so the three arms running `stop_mode: structure` diverge most from their grids.
8. **PDT** means a material share of today's fleet P&L is not reproducible at a real broker.

---

### Artifacts

- `analysis/deep-research/EOD-2026-08-04-WINNERS.md` (this file) · `…-WINNERS.json`
- `analysis/winner-autopsies/2026-08-04.md` · `.jsonl` (per-winner anatomy + wave table)
- `setup/scripts/winner_autopsy.py` (extended) · `backtest/tests/test_winner_autopsy.py` (33 guards)
- `setup/scripts/_eod_2026_08_04_winners.py` (sizing/PDT runner)
