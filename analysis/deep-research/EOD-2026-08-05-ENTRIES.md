# EOD 2026-08-05 — LENS 2: DID WE NEED BETTER **ENTRIES**?

**Run:** 2026-08-06 pre-dawn ET (`et_clock.py` → `market_hours=False`, verified before any edit).
**Authority:** Alpaca broker orders + `fills-ledger.jsonl` (attribution=engine) for P&L · Alpaca **SIP**
1m/5m SPY bars · **real OPRA** 1-minute option bars (1,182 bars, 3 contracts) · the arms' own
`decisions.jsonl` + `core-decisions.jsonl` rows.
**Pre-registration:** `analysis/recommendations/entry-improvement-variants-prereg-2026-08-05.json`,
frozen and committed as **b9cd7a6e** *before* the runner existed.
**Machine-readable twin:** `analysis/deep-research/EOD-2026-08-05-ENTRIES.json`.

---

## VERDICT (three sentences)

1. **70.4% of Wednesday's loss — $1,363 of $1,935 — was ENTRY-side.** Eleven round trips never once
   printed a payable profit on real OPRA. No exit rule in doctrine could have saved them.
2. **The direction was defensible; the LOCATION was not.** Every 776C entry bought within $0.87 of a
   19-to-39-minute-old session high that was *already on the engine's own `levels_active` list*, with
   **zero** confirmed structure events on 5m **or** 1m. We chased candles into supply, ten times.
3. **One pre-registered entry rule survives BOTH Tuesday and Wednesday: V-d1** — *do not enter when the
   last fully closed 5m bar closed against you.* +$179 on the trend day, +$145 on the chop day,
   +$1,242 over 25 live days, **1 winner blocked out of 33 (worth $15)**. Its within-day permutation
   p is 0.14, so the honest call is **SHADOW-AND-MEASURE, not arm.**

---

## 1. THE ENTRY-SIDE ROOT CAUSE — a provenance defect, not a missing knob

The 776C spiral was not five decisions. It was **one decision the engine could not remember making.**

`vwap_continuation`'s validated cell (`analysis/recommendations/j-daily-pattern-LIVE.json`, n=153,
+$38.3/trade) was measured at **one entry per day**. The detector says so:

> `detect_vwap_continuation_setup` — *"Fires at most ONCE per day … Per-day state (trend side, fired
> flag, VIX history) resets on date change."*

It enforces that with the **module-global `_fired_today`**. And the live fleet path is:

```
setup/scripts/run-fleet-executor.ps1        # Windows task, EVERY 1 MIN, 09:30-15:55 ET
  └─ Invoke-PythonHidden build_shared_signal.py     <-- A BRAND NEW PROCESS
       └─ fleet_market.vwap_strategy_block()
            └─ detect_vwap_continuation_setup()     <-- _fired_today = False again
```

**RED-proof, run on 08-05's real 5m bars** (`test_vwap_cont_once_per_day_process_scope_2026_08_05.py`):

| replay mode | fires | times |
|---|---|---|
| one long-lived process (the contract) | **1** | 09:55 |
| module reloaded each bar (= a new process each tick) | **3** | 09:55, 10:05, 10:10 |

Three on *closed* bars; the live producer also reads the **in-progress** bar, which is how it reached
five. Entries 2–5 are **outside the validated population entirely.**

### Why safe-2 took one and the fleet arms took five

| lane | persisted cooldown | 08-05 extra-setup entries |
|---|---|---|
| **CORE** (safe-2/bold-2) | `heartbeat_core._route_extra_setups` → `exit_actuator.same_bar_cooldown_active` → on-disk `<arm>/extra-setup-cooldown.json` | **1** |
| **FLEET** (risky-1/risky-3/safe-3) | **none** — the string appears only in a comment in `fleet_live.py` | **5 each** |

The churn guard built on 2026-07-20 for *exactly this shape* (three same-bar 748C entries) was wired
into the core lane only. The fleet lane never got the sibling.

> **This is NOT the graveyarded re-entry cooldown.** That was a tuned duration knob and every cell of
> it lost on 08-04. This is a **contract violation**: the live path does not implement the cell it
> claims to implement. Fixing it restores the validated population — it does not add a new parameter.
> Its forward P&L is still **not established**, and I am not claiming otherwise.

**Shipped tonight:** a 3-test characterization guard, RED-proofed both directions (disabling
`_fired_today` fails test 1; wiring the cooldown into the fleet fails test 3). It pins the defect so
it cannot be lost, and it tells the fixer which assertion to invert.

---

## 2. WHAT THE ENGINE SAW — real ledger rows

Core view at the moment of the first entry (`core-decisions.jsonl`, 09:58:03, account `safe`):

```
spy 775.87 | ribbon BULL | htf_15m BULL | vix 17.44 | bull_score 9 | bear_score 5
levels_active [772.33, 772.97, 773.41, 774.4, 775.84, 776.85]
bull_reclaim_level_raw 775.84 | shadow_triggers_fired ["wick_reclaim"]
verdict HOLD -- "no setup passed scoring (neither bear nor bull)"   <-- the CORE said no
context_bundle: daily uptrend 0.733 / hourly uptrend 0.80 / m15 uptrend 1.00, alignment_score 3
```

Fleet view, same minute (`risky-1/decisions.jsonl`):

```
09:58:04 ENTER_BULL C VWAP_CONTINUATION strike 776 qty 5 prem 2.36 BASE ALLOW
         trigger_level = None
         "vwap_continuation C (BASE); qty clamped 8->5: FULL_SEND min size"
```

`trigger_level = None` on every continuation entry — the known 08-04 mechanism: `stop_mode="structure"`
resolves to **False** without a trigger level, so the position silently falls back to the raw −6%
premium stop. Confirmed again here on all ten.

| entry (ET) | arms | SPY (last closed 1m) | session high | age of that high | 5m structure | 1m structure | last closed 5m |
|---|---|---|---|---|---|---|---|
| 09:58:05/07 | risky-1, risky-3 | 776.15 | **776.85** | 19.1 min | **none** (blind, 5 bars) | **none** | UP |
| 10:01:58 | safe-2 (777C) | 776.04 | 776.85 | 23.0 min | **none** (blind, 7 bars) | **none** | UP |
| 10:06:05/13 | risky-1, risky-3 | 775.98 | 776.85 | 27.1 min | **none** (blind) | **none** | **DOWN** |
| 10:10:06/07 | risky-1, risky-3 | 776.06 | 776.85 | 31.1 min | **none** (8 bars, trend unknown) | **none** | UP |
| 10:14:05/07 | risky-1, risky-3 | 776.17 | 776.85 | 35.1 min | **none** | **none** | UP |
| 10:18:06/07 | risky-1, risky-3 | 776.19 | 776.85 | 39.1 min | **none** | **none** | UP |
| **11:48/11:49** | all three | 771.59 | 776.85 | 129 min | **BOS DOWN, 5 bars ago** | **BOS DOWN, 34 bars ago** | DOWN |

**The only trades of the day with a confirmed structure event in their direction were the puts — and
the put was the only trade that paid.** Ten calls into a structureless tape: 0 winners.

The safe-2 10:01 entry is worth its own line. It was **not** `vwap_continuation`
(`params.extra_setup_exec_armed.vwap_continuation = false`); it was `vwap_reclaim_failed_break`, and
that detector handed the engine a **real structure stop at 774.40**. The position still exited at
−17.4% with SPY at **776.23** — 1.83 above the stop. The structure stop never bound.

---

## 3. THE ENTRY-TIMING QUESTION — did we chase?

**Yes.** Judged against J's own yardstick (`J-MARKET-PHILOSOPHY.md`: supply/demand zone → **wait for
the return** → **structure shift at the zone** → never chase candles):

| J's step | 08-05 |
|---|---|
| Identify the zone | ✅ 776.85 was in `levels_active` |
| Wait for the **return** to it | ❌ we bought **at** the supply zone, never at a demand zone |
| Require a **structure shift** at the zone | ❌ zero BOS/CHoCH on 5m **and** 1m |
| Never chase candles | ❌ every entry landed on a green 1m thrust into the ceiling |

The tape (SIP 1m): the day's high **776.85 printed at 09:39** and was never exceeded. Every rally
after topped lower — 776.70 (09:59), 776.55 (10:05), 776.39 (10:11), 776.46 (10:15), 776.28 (10:18).
SPY opened 775.84, **above** the prior-day RTH high of 773.41, so the whole session traded inside an
untested gap with no demand shelf below it. Close 769.76 — the low of the day's range.

**The direction had real support** (ribbon BULL, htf_15m BULL, 3/3 timeframe alignment uptrend, above
VWAP). This was not a wrong-way read. It was a **right-way read executed at the wrong price** — the
top of a 25-minute distribution range, five times.

> **Brief variant (c) cannot fire on this day.** The prior-day high (773.41) sat **2.56–2.78 BELOW**
> every entry. Reported as a null, not massaged.

---

## 4. PRE-REGISTERED VARIANTS — every cell, pass or fail

**Population LIVE-ENGINE-REAL-FILLS-v1:** 230 distinct entry events / 286 FIFO round trips /
25 trading days (2026-06-26 → 2026-08-05) / actual net **+$317** / winner rate 18.3%.
*(08-04 alone is +$3,624 of that +$317. Ex-08-04 the book is −$3,307. Everything below is reported
ex-08-04 as well.)*

Δ = dollars the variant would have added by refusing those entries. All 17 cells reported.

| cell | n blocked | **Δ full** | Δ ex-08-04 | Δ 08-05 | Δ ex-08-05 | Δ 08-04 | winner$ blocked | loser$ blocked | Δ h1 | Δ h2 | gates | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V-a1 structure any-age | 56 | +807 | +727 | +913 | −106 | +80 | 1495 | 2302 | −345 | +1152 | 123-56 | WATCH |
| V-a2 structure ≤30m | 91 | +296 | +1863 | +913 | −617 | −1567 | 3696 | 3992 | +131 | +165 | 12345- | WATCH |
| V-a3 structure ≤15m | 117 | −180 | +1387 | +1485 | −1665 | −1567 | 5562 | 5382 | +70 | −250 | --3-5- | REJECT |
| V-b1 band 0.15 /engine | 48 | −506 | +470 | +1790 | −2296 | −976 | 4011 | 3505 | 0 | −506 | --3-5- | REJECT |
| V-b1 band 0.15 /proxy | 157 | −1079 | +2204 | +1790 | −2869 | −3283 | 7916 | 6837 | +942 | −2021 | --3-5- | REJECT |
| V-b2 band 0.25 /engine | 32 | −190 | +1280 | +1446 | −1636 | −1470 | 2857 | 2667 | 0 | −190 | --3-5- | REJECT |
| V-b2 band 0.25 /proxy | 127 | −1984 | +1299 | +1446 | −3430 | −3283 | 7657 | 5673 | +555 | −2539 | --3-5- | REJECT |
| V-b3 band 0.40 /engine | 15 | −1763 | +60 | +572 | −2335 | −1823 | 2842 | 1079 | 0 | −1763 | --3-5- | REJECT |
| V-b3 band 0.40 /proxy | 77 | −780 | +311 | +572 | −1352 | −1091 | 4080 | 3300 | +71 | −851 | --3-5- | REJECT |
| V-c1 PDH 0.25 | 1 | +36 | +36 | 0 | +36 | 0 | 0 | 36 | 0 | +36 | 12-4-6 | WATCH |
| V-c2 PDH 0.50 | 5 | −140 | −140 | 0 | −140 | 0 | 290 | 150 | −221 | +81 | ----56 | REJECT |
| V-c3 PDH 1.00 | 16 | +1 | +1 | 0 | +1 | 0 | 290 | 291 | −122 | +123 | 12--56 | WATCH |
| V-cp1 sessHi 0.50/10m | 16 | +428 | +348 | 0 | +428 | +80 | 0 | 428 | +106 | +322 | 12-456 | WATCH |
| V-cp2 sessHi 1.00/10m | 54 | **+3262** | +3182 | +1935 | +1327 | +80 | 655 | 3917 | +246 | +3016 | 123456 | SHIP_CAND* |
| V-cp3 sessHi 1.00/20m | 41 | +2757 | +2757 | +1714 | +1043 | 0 | 365 | 3122 | +369 | +2388 | 123456 | SHIP_CAND* |
| **V-d1 closed-bar dir** | 33 | **+1242** | +1063 | +145 | **+1097** | **+179** | **15** | 1257 | **+579** | **+663** | 123456 | **SHIP_CAND** |
| V-d2 closed-bar + third | 64 | +2590 | +2420 | +1630 | +960 | +170 | 1272 | 3862 | +596 | +1994 | 123456 | SHIP_CAND* |

### Two harder cuts added after the prereg (disclosed — both can only DEMOTE)

`drop-top-2-days` (the repo's standard concentration cut) and a **within-day permutation** that holds
each day's *number* of blocks fixed and randomises *which* entries inside that day get blocked. The
second is the one that matters: it separates **"picked the bad entry"** from **"sat out a bad day."**

| cell | Δ | Δ after dropping its 2 best days | blocked WR | p(random-k) | **p(within-day)** |
|---|---|---|---|---|---|
| **V-d1** | +1242 | **+726 (58% survives)** | **3.0%** | 0.043 | **0.145** |
| V-d2 | +2590 | +655 (25%) | 17.2% | 0.002 | 0.102 |
| V-cp2 | +3262 | +553 (17%) | 7.4% | 0.000 | 0.255 |
| V-cp3 | +2757 | +431 (16%) | 4.9% | — | — |

**\* V-cp2 / V-cp3 / V-d2 pass the letter of the pre-registered gates but do not survive the
concentration cut.** V-cp2's Δ is 83% two days — $1,935 from 08-05 (**the day it was designed on**,
where it simply blocks *every* entry) plus $774 from 07-27. Per the prereg's own meta-gate, that is
noise. V-d2 blocks risky-1's +$347 put on 08-05 and $1,272 of winners overall.

**Every level-proximity cell is REJECT.** Six of six, engine-actual levels and mechanical proxy alike.
*Levels are zones* is right as a description of the market; as an **entry gate on this population** it
loses money.

### Variant (a) as briefed tests the wrong property

Bucketing all 230 entries by what the 5m structure read actually was:

| context at entry | n | P&L | WR |
|---|---|---|---|
| structure event **AGREES** with the trade | 120 | +$344 | 18.3% |
| structure event **DISAGREES** | 18 | **+$559** | **27.8%** |
| **NO structure event at all** | 38 | **−$1,366** | **10.5%** |
| structure-blind (<8 closed 5m bars) | 54 | +$780 | 20.4% |

The disagree bucket is the **most profitable in the book.** The killer is **absence**, not conflict.
A gate that requires *agreement* (variant (a) as written) throws away the best cohort and keeps the
worst-adjacent one.

And the 5m structure gate is **blind exactly when it is needed**: 54 of 230 entries (23%) — every
entry between 09:30 and 10:06 ET — happen before eight closed 5m bars exist. On 08-05 it abstained on
the first six 776C entries.

**Post-hoc exploratory (cannot ship — pre-registration fodder only):**

| cell | n | Δ | Δ ex-08-05 | drop-top-2 | blocked WR | p(within-day) |
|---|---|---|---|---|---|---|
| V-e1 no 5m structure event | 38 | +1366 | +453 | −159 | 10.5% | 0.372 |
| V-e2 no 5m structure incl. blind | 92 | +586 | −777 | −1389 | 16.3% | 0.475 |
| **V-e3 no *1m* structure event** | 41 | **+2357** | **+994** | **+637** | **7.3%** | **0.063** |
| V-f  V-d1 ∪ V-e1 | 65 | +2371 | +1313 | +647 | 7.7% | 0.227 |

**V-e3 is the strongest discriminator found anywhere in this study** (+$1,101 h1 / +$1,256 h2,
one negative day, p=0.063) and it fixes V-a's blindness by reading structure on 1m instead of 5m.
It is **post-hoc**. It ships nothing. It is the obvious thing to pre-register for forward measurement.

---

## 5. THE NUMBER J ASKED FOR — entry-side vs exit-side

Method (pre-registered): a trade is **ENTRY-side** if its real-OPRA MFE from fill to the arm's own
exit never reached a payable profit. The payable bar is **+30%** — the tightest TP1 configured
anywhere in the live book. The pre-registered binary was subdivided into three buckets after
discovering that one arm's *own* TP1 sat above anything the tape offered.

| bucket | n | actual | best **executable** | recoverable |
|---|---|---|---|---|
| **A — ENTRY-side.** Tape never printed +30% | 11 | **−$1,363** | −$1,363 | **$0** |
| **B — CONFIG-side.** Tape paid, the arm's own TP1 was unreachable | 1 | −$664 | +$163.50 | **+$827.50** |
| **C — EXIT-side.** TP1 reachable and missed | 2 | +$92 | +$470.30 | **+$378.30** |
| **TOTAL** | **14** | **−$1,935.00** | **−$729.20** | **+$1,205.80** |

> **ENTRY-side = 70.4% of the loss ($1,363 of $1,935).** Unsaveable by any exit rule in doctrine.
> **EXIT + CONFIG = 29.6% of the loss**, but worth **$1,205.80** in recoverable dollars (62.3% of the
> day) because the exit-side trades also handed back profit that was on the table.
> *(ORACLE bound — LABEL ONLY, never executable: +$2,601.)*

**Bucket A** is the ten 776C round trips (MFE 0.0% / 1.5% / 2.2% / 2.6% / 4.5% / 5.0% / 6.1% / 6.1% /
10.5% / 11.5%) plus safe-2's 777C (23.6%). Not one of them ever offered a payable exit.

**Bucket B answers the brief's open question.** risky-3's put topped at 2.62 = **+66.7%**;
`ribbon_ride`'s registry TP1 is **+100% (3.30)**. TP1 was not "missed" — it was **structurally
unreachable**. risky-1 held the identical contract with `params_patch.exit_patch.tp1_premium_pct = 0.5`,
crossed +50% at 2.535, and sold 3 of 5 (`tp1_qty_fraction` 0.667 × 5 = 3) at 2.62 at 12:09. **Same
trade, opposite outcome, decided by one config key.** safe-2's TP1 (+50%, reachable at 2.445) *was*
reachable and did not fire — that root cause belongs to the L5-0 lane; only its number is used here.

---

## 6. WHAT SURVIVES BOTH DAYS

The brief rejects anything that only works on one of the two days. **One pre-registered entry rule
clears it:**

> **V-d1 — do not enter when the LAST FULLY CLOSED 5m bar closed AGAINST the trade direction.**

| | |
|---|---|
| 2026-08-04 (trend day) | **+$179** |
| 2026-08-05 (chop day) | **+$145** |
| Full population, 25 days | **+$1,242** |
| Days touched / days negative | 14 / **1** (worst −$15) |
| Winner dollars blocked | **$15** (one trade) |
| Loser dollars blocked | $1,257 |
| Blocked-cohort win rate | **3.0%** vs 18.3% population |

**Why it survives both regimes:** it is not a regime bet. On a trend day the last closed bar usually
already agrees, so it rarely binds and blocks no winners. In chop it binds precisely on the
knife-catch re-entries — the 10:06 776C re-entry on both arms, which is exactly the shape that killed
Wednesday.

**Honest limit:** within-day permutation **p = 0.14**, across 17 cells, uncorrected. The dollar edge
is real in-sample but is **not statistically separated from "sat out days that were bad anyway."**
The permutation table above is the discriminating test and none of the leading cells clear it.

**Recommendation: SHADOW-AND-MEASURE V-d1 for 10 sessions. Do not arm it.**
J's standing correction applies — *on paper, bias toward TAKING the trade* — and the graveyard is full
of entry filters that looked like this.

**What does NOT survive:** all six level-proximity cells (REJECT), V-c2 (REJECT), and V-cp2/V-cp3/V-d2
(gate-passing but 75–85% two-day concentrated, one of those days being the one they were designed on).

---

## 7. THE HONEST SHAPE OF THE ANSWER

The 08-04 audit said the loop was downstream of the exit. It was right about the *mechanism* and
incomplete about the *provenance*. Both are true at once:

- The re-entries **exist** because the −6% stop fired inside the noise band (08-04's finding, and its
  scored prediction that a chop day would be the treadmill **came true on 08-05** — say so plainly).
- The re-entries **were permitted** because the validated one-per-day contract dies with the process
  (this study's finding).
- And the entries themselves were **located wrong**: 70.4% of the damage sits on trades that never
  once printed a payable profit, taken into a structureless tape, under a ceiling the engine already
  had on its own list.

Fix the stop and the loop shrinks. Fix the process-scoped flag and the loop cannot repeat at all.
Neither one makes a bad location good.

---

## ARTIFACTS

| path | what |
|---|---|
| `analysis/recommendations/entry-improvement-variants-prereg-2026-08-05.json` | frozen prereg, commit **b9cd7a6e**, before the runner |
| `analysis/deep-research/EOD-2026-08-05-ENTRIES.md` | this report |
| `analysis/deep-research/EOD-2026-08-05-ENTRIES.json` | machine-readable twin, all cells + all cuts |
| `analysis/deep-research/_entry_variants_0805.py` | the scorer (17 cells, causal features) |
| `analysis/deep-research/_entry_json_0805.py` | the JSON assembler |
| `backtest/tests/test_vwap_cont_once_per_day_process_scope_2026_08_05.py` | 3-test characterization guard, RED-proofed both ways |

## CAVEATS

- **n=230 entries / 25 live days is small.** 08-04 alone is +$3,624 of the +$317 net; every headline is
  also reported ex-08-04.
- `levels_active` is only logged from **2026-07-28**, so V-b/engine covers 7 days (169 of 230 abstain).
  The V-b/proxy row rebuilds a causal mechanical level set for the full window — a **proxy**, not the
  engine's own levels.
- The ten 776C entries are **one clustered decision**, not ten independent ones. `n_blocked` overstates
  independence; the within-day permutation is the honest correction and is reported for every leader.
- V-c-prime and V-e1/e2/e3/V-f were designed **after** seeing the 08-05 tape and cannot ship off this
  population.
- The 3¢ half-spread haircut on the OPRA high is a fill proxy for a resting TP1 limit, not a guarantee.
- Bucket B's counterfactual harmonises risky-3's TP1 to +50%. That is a **config** change, not exit
  execution, and is labelled separately for that reason.
- **Doc defect found:** `accounts.json` still calls risky-1 *"deliberately NO exit_patch — the untouched
  control lane."* Stale — the arm has carried `params_patch.exit_patch {tp1_premium_pct: 0.5,
  stop_mode: structure}` since 2026-07-29, and that key is exactly what made it the only winner on the
  put. Documentation, not code.
- **Process miss, self-reported:** the RED-proof briefly wrote to `automation/state/fleet/fleet_live.py`
  while another lane (L4-5 FLEET-PDT-PARITY) was editing it. Verified afterwards that their change is
  intact (868 lines, `_true_day_trades_5d` present, parses clean, their guard
  `backtest/tests/test_fleet_pdt_parity.py` exists). No damage — but the RED-proof should have used a
  temp copy, and will next time.
