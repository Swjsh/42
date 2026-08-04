# EOD 2026-08-04 — LENS 3: CRITICIZE THE ENGINE

> Adversarial audit of the machinery on the best day on record. **This document is about
> what the engine did wrong, what it cannot see, and what is still unproven — not about
> the P&L.** Written after the close (verified `et_clock.py` → `2026-08-04 16:07 ET`,
> `market_hours=False`). All P&L from BROKER FILLS. All counterfactuals from real OPRA
> 1-min bars, explicitly labeled SIM and bounded.

**Companion JSON:** `analysis/deep-research/EOD-2026-08-04-ENGINE.json`

---

## VERDICT

The day was **real and correctly booked** — every dollar reconciles to the cent. But the
machinery produced it with **one structurally dead safety gate, one alarm that went deaf at
10:17, one shipped fix that is invisible, and one exit knob that decided a $680 swing on a
7-cent fill difference.**

Ranked, most severe first:

| # | Finding | Status |
|---|---|---|
| **1** | **Fleet PDT gate is structurally dead** — `day_trades` read `0` on all 384 ticks × 3 arms. Fleet arms took 6/5/8 day trades against a limit of 3. | 🚨 **DEFECT, unfixed** |
| **2** | **Every arm is now at or over the PDT limit.** Conservative headroom Wed/Thu/Fri = **ZERO on all five arms.** Rolloff 2026-08-11. | 🚨 **HARD CONSTRAINT** |
| **3** | **The −6% premium stop is a once-per-minute-sampled stop.** Intrabar range exceeded the stop band; a 7¢ fill difference decided a $680 swing between two arms on the *same contract, same minute*. Cost ≥ **$2,298** today (SIM lower bound). | 🚨 **DEFECT, quantified** |
| **4** | **Entry-block alarm hit its 3/day cap at 10:17 ET** and suppressed everything after — including all 21 PDT denials. | ⚠️ **INSTRUMENT BLIND** |
| **5** | **SHIP A fleet path emits no artifact.** Proven working *only* by arithmetic I derived. A fix that ran and a fix that never ran are indistinguishable in the logs. | ⚠️ **C7 violation** |
| **6** | **`safe` core PDT gate mode is justified by a stale account.** Doc cites `PA3DHPT7KIQE` / `multiplier=1`; live account is `PA3POKNV46VG` / `multiplier=4`. | ⚠️ **STALE PROVENANCE** |
| **7** | **L246 floor-rescue never fired** — the ATM extension eliminated its trigger condition. Two same-night ships; one made the other unreachable. | ℹ️ **UNPROVEN / now dead path** |

---

## §1 — FIRST-SESSION VERDICTS ON EVERY NEWLY-LIVE CHANGE

| Change | Verdict | Evidence |
|---|---|---|
| **SHIP A** exits anchor to real fill — **core** | ✅ **EVIDENCED** | 6/6 attempted. 5 applied, 1 conservatively refused. |
| **SHIP A** exits anchor to real fill — **fleet** | ✅ **EVIDENCED** (by arithmetic only) | **19/19** entries anchored to true fill. |
| **ATM-TIER-EXTENSION-2K-10K** | ✅ **EVIDENCED** | 6/6 core placements `strike == round(spot)`. |
| **SHIP B** `block_elite_bull` lift | ✅ **EVIDENCED — and load-bearing** | 6/6 placements would have been blocked pre-lift. |
| **IEX tail** on level refresh | ✅ **EVIDENCED** | `tail_used > 0` on 80 of 171 refreshes. |
| **SHIP C** risky-3 qty10 under $0.50 | ⬜ **UNPROVEN** | Never fired (no contract < $0.50). As handed off. |
| **L246 floor-rescue** (risky-1) | ⬜ **UNPROVEN — now unreachable** | 0 floor blocks to rescue (see §3). |
| **FIX2** vwap_continuation un-deadened | ✅ **FIRED** — ⚠️ **and is finding #3** | 7 entries, its first live session ever. |

### 1a. SHIP A — core path (`heartbeat_core._reanchor_after_reconcile`)

Every core `exec` row carries a `reanchor` marker, always written (loud, never silent).

```
09:56:03 safe  reanchor={'applied': True, 'true_entry_premium': 1.35}  limit=1.39  broker fill 1.350
09:56:51 bold  reanchor={'applied': True, 'true_entry_premium': 1.38}  limit=1.40  broker fill 1.380
11:26:04 bold  reanchor={'applied': True, 'true_entry_premium': 1.11}  limit=1.14  broker fill 1.110
11:51:04 bold  reanchor={'applied': True, 'true_entry_premium': 1.19}  limit=1.22  broker fill 1.190
12:28:04 safe  reanchor={'applied': False, 'reason': 'fill_unknown_kept_limit_anchor'}  broker status='new'
13:41:03 safe  reanchor={'applied': True, 'true_entry_premium': 1.22}  broker status='partially_filled' filled_qty='2'
```

**Two day-one mechanism caveats, both real, neither harmful today:**

- **12:28 safe — the poll raced the fill.** `poll_fill` returned `status='new', filled_qty='0'`;
  the code correctly refused and kept the limit anchor. The limit (1.34) happened to equal
  the eventual fill (1.340), so no damage — **by luck, not by design.** This is a
  refuse-and-log path that will silently degrade to limit-anchoring on any slow fill.
- **13:41 safe — anchored off a PARTIAL fill.** `filled_qty='2'` of 3 at the moment of the
  poll. The 3rd contract also filled at 1.220, so the anchor was right. **If the remainder
  had filled at a different price, the anchor would be wrong and nothing would flag it.**

### 1b. SHIP A — fleet path: works, but is invisible

`fleet_live.py:548-590` prints **only** on FAILED / SKIPPED / fill-unknown. The success
branch writes nothing to stderr and nothing to `decisions.jsonl`. A repo-wide grep for
`reanchor` across every log touched today returns **zero lines** — which is equally
consistent with "all 19 succeeded silently" and "the code never executed."

I proved it independently: the exit manager's `runner_stop` must equal
`true_fill × (1 + premium_stop_pct)`. If reanchoring had not run it would equal
`limit × (1 + pct)`.

```
arm       sym        entry     limit    mid   FILL stop_pct runner_stop  fill*pct  limit*pct
risky-3   C00762000  09:46:06   1.79   1.77  1.750    -0.06      1.6450    1.6450     1.6826  FILL-ANCHORED
risky-3   C00765000  10:35:05   1.36   1.35  1.330    -0.06      1.2502    1.2502     1.2784  FILL-ANCHORED
risky-3   C00768000  11:27:05   1.12   1.08  1.038    -0.50      0.5190    0.5190     0.5600  FILL-ANCHORED
risky-1   C00763000  09:50:06   1.40   1.38  1.390    -0.06      1.3066    1.3066     1.3160  FILL-ANCHORED
safe-3    C00769000  12:28:07   1.38   1.35  1.330    -0.50      0.6650    0.6650     0.6900  FILL-ANCHORED
                                                        ... 19/19 FILL-ANCHORED
```

The test is **discriminating, not vacuous**: `limit*pct ≠ fill*pct` on 16 of the 19 rows.
Note `risky-3 11:27` — fill was a two-leg VWAP (4@1.04 + 1@1.03 = 1.038) and the anchor
tracked the blended price exactly.

**Verdict: EVIDENCED. But this is a C7 violation** — a fix shipped the night before,
carrying real money, whose success leaves no positive artifact. One `reanchor` key on the
fleet decision row closes it.

### 1c. ATM extension — 6/6 exact

```
09:56:03 safe  spy=763.43  → 763C ✓     11:51:04 bold  spy=768.640 → 769C ✓
09:56:51 bold  spy=763.43  → 763C ✓     12:28:04 safe  spy=769.225 → 769C ✓
11:26:04 bold  spy=767.745 → 768C ✓     13:41:03 safe  spy=771.875 → 772C ✓
```

Both bold-tier ($5K-class) arms received ATM strikes — that *is* the extension. EVIDENCED.

### 1d. SHIP B — the lift is responsible for 100% of core entries

`block_elite_bull = false` on both `params.json` and `aggressive/params.json`. All **82**
`ENTER_BULL` verdicts today carried triggers `('confluence', 'level_reclaim')` at tier
ELITE, VIX 15.85–16.48. Replaying the pre-lift gate bands:

```
safe gate: ELITE + level_reclaim, VIX ∈ [0.0, 25.0)
bold gate: ELITE + confluence,    VIX ∈ [15.0, 18.0)
→ all 6 PLACED entries: OLD gate would BLOCK = True
```

**Attribution: SHIP B alone accounts for safe-2 +$661.37 and bold-2 +$478.25 = +$1,139.62**
of the day. Pre-lift, both core arms trade zero. This is the single highest-value change
of the batch — and it validates the standing memory *"dynamic market: recency > aggregate"*
(the gate was blocking on stale 390-day evidence).

### 1e. IEX tail — fired

`automation/state/logs/level-refresh-2026-08-04.log`: 171 `iex_tail` records.
`tail_used: 0` ×91 · `1` ×2 · `2` ×2 · `3` ×76. **80/171 refreshes consumed tail bars.** EVIDENCED.

---

## §2 — WHAT THE ENGINE MISSED (refused cohort, priced on real OPRA)

**Method.** Core decision stream mined for rows where `verdict ∈ {ENTER_BULL, ENTER_BEAR}`
but no order resulted. Clustered into events (>15 min gap = new event). Priced on real OPRA
1-min bars at the arm's own live exit shape, sampled at the **bar open** — matching the
engine's true ~:05s/minute poll cadence, so there is **no oracle**. Upside credited **only
to TP1** (runner credited nothing) → every number is a **strict LOWER BOUND**.

> **First attempt was wrong and is disclosed.** v1 priced `NOT_FLAT` rows as missed money.
> They are not missed — the arm was *already in that move* via an open position; `NOT_FLAT`
> is the Rule-4 no-add guard working (C31). `VETOED_BY_MODELS` is also evaluated *before*
> the flat check, so vetoes logged while holding would have been `NOT_FLAT` anyway. v2
> prices a refusal only where the arm was **verifiably flat per broker fills**. v1 read
> +$3,335; v2 reads +$802. **The $2,533 delta was double-counting.**

| acct | mechanism | ticks | events | flat events | SIM (lower bd) | verdict |
|---|---|---:|---:|---:|---:|---|
| bold | `RISK_DENY_PDT` | 21 | 3 | 3 | **+$767.50** | **COST money** |
| bold | `VETOED_BY_MODELS` | 4 | 3 | 2 | +$52.50 | overlapping (see below) |
| safe | `VETOED_BY_MODELS` | 6 | 3 | 1 | +$198.00 | delay only (see below) |
| safe | `SKIP_LATE_ENTRY` | 11 | 2 | 2 | **−$216.00** | **SAVED money** |
| bold | `NOT_FLAT` | 10 | 3 | 0 | — | guard working, not a refusal |
| safe | `NOT_FLAT` | 24 | 4 | 0 | — | guard working, not a refusal |

Flat-verified event detail:

```
12:26:03 safe  VETOED_BY_MODELS  x2  769C q3   +198.00  in 1.32 -> TP1 1.98 13:01
12:26:55 bold  RISK_DENY_PDT     x7  769C q5   +495.00  in 1.32 -> TP1 2.31 13:04
12:38:18 bold  VETOED_BY_MODELS  x2  770C q5   +322.50  in 0.86 -> TP1 1.50 13:02
13:06:39 bold  RISK_DENY_PDT     x7  771C q5   +412.50  in 1.10 -> TP1 1.93 13:45
13:41:33 bold  RISK_DENY_PDT     x7  772C q5   -140.00  in 1.20 -> MARK 15:50 0.92
13:46:24 bold  VETOED_BY_MODELS  x1  772C q5   -270.00  in 1.46 -> MARK 15:50 0.92
15:06:03 safe  SKIP_LATE_ENTRY   x6  773C q3    -99.00  in 0.81 -> MARK 15:50 0.48
15:46:03 safe  SKIP_LATE_ENTRY   x5  773C q3   -117.00  in 0.87 -> MARK 15:50 0.48
```

**Two further corrections before anyone quotes the +$802:**

- **safe 12:26 veto (+$198) is not a loss.** safe-2 entered the *same* 769C 2 minutes later
  at 12:28:43 and booked **+$375 actual** — better than the sim's lower bound. The veto
  delayed entry; it did not cost money.
- **bold 12:38 veto (+$322.50) double-counts PDT.** bold was PDT-denied on the surrounding
  ticks (12:36:42, 12:38:20). PDT was the **binding** constraint; counting the veto
  separately prices the same missed 770C window twice.

### The honest bottom line on refusals

**Exactly one mechanism genuinely cost real money today: bold-2's PDT denial, ≈ +$767.50
(SIM, lower bound).** Every other refusal was neutral, a delay, or net-positive.
`SKIP_LATE_ENTRY` **saved $216** — both late events would have lost.

And the irony is the finding: **the one arm that obeyed PDT paid $767.50 for it. The three
arms that ignored PDT entirely (§4) were never charged — because paper does not enforce it.**

---

## §3 — ALARMS AND LIVENESS INSTRUMENTS

### 3a. FLOOR_WALL — collapsed exactly as the extension predicted ✅

`SKIP_MIN_PREMIUM_FLOOR` rows per fleet arm:

| arm | 2026-08-03 | 2026-08-04 |
|---|---:|---:|
| safe-3 | 33 | **0** |
| risky-1 | 35 | **0** |
| risky-3 | 35 | **0** |

**103 → 0.** `FLOOR_BLOCK_ALARM_MIN = 10`, so the alarm correctly stayed silent — a **true
negative, not a false negative.** This is the ATM-TIER-EXTENSION's own pre-registered
kill-criteria baseline and it is fully met. `fleet_liveness_check.py` returned
`2026-08-04 ALL_TICKED checked=['safe-3','risky-1','risky-3'] all 3/3 readable fleet arm(s) ticked today`.

### 3b. L246 floor-rescue — never fired, and is now structurally unreachable ⬜

`floor_rescue` mentions in fleet decisions today: **0**. `floor_rescue denied`: **0**.

The rescue path is contingent on a `SKIP_MIN_PREMIUM_FLOOR` kill. §3a shows there were
zero. **Two changes shipped the same night; the ATM extension removed the condition the
L246 rescue exists to handle.** L246 remains untested in production and, on the current
config, cannot be exercised. That is not a bug — but it must not be recorded as "shipped
and working," and its guard test is now the *only* thing exercising it.

### 3c. Entry-block watcher — went deaf at 10:17 ET 🚨

```
09:38:14 ALERT      safe/bull @ 09:37:03 score=10
09:38:14 ALERT      bold/bull @ 09:37:04 score=10
10:18:09 ALERT      safe/bull @ 10:17:04 score=10
10:18:09 SUPPRESSED bold/bull @ 10:17:05 -- daily cap (3) already reached
10:38:01 SUPPRESSED safe/bull ... 10:48:01 SUPPRESSED ... 11:04:01 SUPPRESSED ...
15:48:01 SUPPRESSED bold/bull @ 15:47:04 -- daily cap (3) already reached
```

`.entry-block-watch.json` → `"alerts_today": 3`. **The 3-alert daily cap was spent by
10:17 ET.** Every block for the remaining 5½ hours was suppressed — including **all 21
`RISK_DENY_PDT` events (12:26–13:48)**, which per §2 were the only refusals that cost money.

The alarm that would have surfaced the day's single most expensive gate was structurally
incapable of firing by mid-morning. The cap is a reasonable anti-spam device, but it is
**flat across mechanisms** — a repeated bull-block at 09:37 and a novel PDT wall at 12:26
consume the same budget. A per-mechanism budget (or "always alert on a mechanism not yet
seen today") would have caught it.

---

## §4 — PDT AUDIT (first-class)

### 4a. The broker field is genuinely absent — Monday's flag is CONFIRMED

```
safe-2   daytrade_count=None  pattern_day_trader=None  multiplier='4'  dtbp=None  opts_lvl=3
bold-2   daytrade_count=None  pattern_day_trader=None  multiplier='4'  dtbp=None  opts_lvl=3
safe-3   daytrade_count=None  pattern_day_trader=None  multiplier='4'  dtbp=None  opts_lvl=3
risky-1  daytrade_count=None  pattern_day_trader=None  multiplier='4'  dtbp=None  opts_lvl=3
risky-3  daytrade_count=None  pattern_day_trader=None  multiplier='4'  dtbp=None  opts_lvl=3
```

`daytrade_count`, `pattern_day_trader` and `daytrading_buying_power` are **not present at
all** in the key set returned by `/v2/account`. All five arms read `multiplier='4'` →
**margin**, equity ~$5–6K → **well under $25,000** → real FINRA PDT applies: **3 day trades
per rolling 5 business days.**

### 4b. 🚨 THE DEFECT: the fleet PDT gate is fed a number that can never move

```python
# automation/state/fleet/fleet_live.py:660
day_trades = int(acct.get("daytrade_count", 0) or 0)
```

The field is absent → `None` → `int(None or 0)` → **0, forever.**

**Verified against the decision stream:** `day_trades` was `0` on **384/384 rows on every
one of the three fleet arms** — 1,152 consecutive ticks, zero variance, across a session in
which those arms executed 19 round trips.

The core lane does it correctly — `heartbeat_core.py:1909` calls
`pdt_tracker.fetch_day_trades_used_5d(creds)`, which **computes** the count from broker fill
history. That is why bold-2 stopped dead at 3 with a real reason string:

> `bold: 3 day-trades in 5d at equity $5,478 < $25,000 — PDT rule blocks a 4th day-trade`

…while safe-3, risky-1 and risky-3 sailed past it. `params.json`'s own doc string says the
fleet arms are *"EXPLICITLY pinned back to `margin_pdt` regardless of this key"* — **the mode
is correct; the input is dead.** This is textbook C14 (dead knob, vary-and-assert) sitting
on top of C7 (silent success). `pdt_tracker.py`'s header documents this exact failure class
from 2026-07-06 — *"a hardcoded 0 … the counter can literally never reach
PDT_DAY_TRADE_LIMIT=3 because it never moves off 0"* — and it has **re-emerged in the fleet
lane** (C34/L252: a detector without a remediator re-violates on its own schedule).

**The fix is one line** — route the fleet lane through the same computed count:

```python
# fleet_live.py:660  — replace the dead broker read
day_trades = _pdt.fetch_day_trades_used_5d(creds)   # was: int(acct.get("daytrade_count", 0) or 0)
```

### 4c. Day-trade counts — both readings

Limit = **3 / rolling 5 business days**. FINRA reading = `(symbol, date)` pairs, computed
with the repo's own `pdt_tracker.compute_day_trades_detail` (so the number is the engine's
own definition). Strict-pairing = each open→flat cycle.

| arm | mult | FINRA 5bd | strict 5bd | FINRA today | strict today | **headroom (FINRA)** | rolloff |
|---|---:|---:|---:|---:|---:|---:|---|
| safe-2 | 4 | 4 | 4 | 3 | 3 | **−1** | 2026-08-11 |
| bold-2 | 4 | 3 | 3 | 3 | 3 | **0** | 2026-08-12 |
| safe-3 | 4 | 6 | 7 | 5 | 6 | **−3** | 2026-08-11 |
| risky-1 | 4 | 5 | 6 | 4 | 5 | **−2** | 2026-08-11 |
| risky-3 | 4 | **6** | **9** | 5 | 8 | **−3** | 2026-08-11 |

risky-3's today cycles (strict), the shape that made the count:

```
C00762000 09:46:09 -> 09:47:07      C00765000 10:35:08 -> 10:37:06
C00763000 09:50:09 -> 09:52:07      C00768000 11:27:12 -> 11:32:08
C00763000 09:54:07 -> 09:56:07      C00769000 11:52:12 -> 11:57:08
C00763000 09:57:09 -> 10:23:06      C00769000 12:28:11 -> 13:51:08
```

### 4d. CONSERVATIVE HEADROOM FOR THE REST OF THIS WEEK

**ZERO on all five arms, Wednesday through Friday.**

The trailing window on Wed 08-05 is 07-30…08-05 — it still contains **both** 08-03 and
08-04. Nothing rolls off until **Mon 2026-08-10 at the earliest, and the 08-03 pairs do not
clear until Tue 2026-08-11** (08-04's own pairs clear 08-12).

**Does today put any arm at risk of a PDT block Wed/Thu?** On **paper: no** — Alpaca does
not enforce it, which is precisely why the dead gate cost nothing today. On **live money:
four of five arms are already flagged.** safe-3 and risky-3 are at **double** the limit;
under a real broker they would be restricted to closing-only for 90 days.

**"Trade like this again" is not available at these account sizes.** Today's leg counts are
only reachable because the constraint is unenforced in the sandbox. Any live-money arming
conversation must start here, and the fleet gate must be fixed *before* it, not after.

### 4e. ⚠️ safe core's gate mode rests on a stale account

`automation/state/params.json` → `pdt_gate_mode = cash_settlement`, justified by a doc
string reading *"Gamma-Safe-2 (PA3DHPT7KIQE) is a CASH account — verified live:
multiplier=1."*

**Live today: account `PA3POKNV46VG`, `multiplier='4'`.** Different account number,
different account type. The 2026-08-01 reset minted new margin accounts and the safe lane's
gate-mode provenance was never re-checked — the identical drift that was caught and fixed on
the bold lane 2026-07-20.

safe-2 happened to take exactly 3 day trades today, but **not because a gate stopped it** —
safe-2 logged **zero** `RISK_DENY_*` rows all session. Its 3 came from
`SKIP_BULL_1100_1200`, `NOT_FLAT`, `VETOED_BY_MODELS` and `SKIP_LATE_ENTRY`. **Luck, not
design** — the same sentence `levels_blind_check.py` already carries about a prior session.

---

## §5 — RECONCILIATION (zero tolerance, all 5 arms)

```
arm          last_eq     equity      delta   opt_flow  cry_flow  sells    resid   $/sold
safe-2       5067.73    5729.22    +661.49    +662.00   -0.0282      9  -0.4818  -0.0535
bold-2       5000.00    5478.25    +478.25    +479.00   +0.0000     15  -0.7500  -0.0500
safe-3       5144.73    5780.83    +636.10    +637.00   +0.0000     18  -0.9000  -0.0500
risky-1      5144.55    6184.30   +1039.75   +1041.00   +0.0000     25  -1.2500  -0.0500
risky-3      5175.55    5977.81    +802.26    +805.00   +0.0000     55  -2.7400  -0.0498
TOTAL                             +3617.85   +3624.00   -0.0282    122  -6.1218  -0.0502
```

**Zero unexplained equity delta on any arm.** The residual is a flat **$0.05 per contract
sold** on all five arms (122 contracts, −$6.12) — option regulatory fees (ORF/OCC/SEC/TAF)
applied at fill. `accrued_fees` and `pending_reg_taf_fees` both read `'0'` everywhere, so
they are netted into cash rather than accrued. Fills → decisions → exit-state → broker all
tie out; the per-trade FIFO ledger is in the companion JSON.

**All five arms flat at the close** (`broker_positions = 0`, `exit-state.json = {}` on all five).

Two small provenance notes:

- **The handoff's day total is $0.66 light.** Broker truth is **+$3,617.85**; the handoff's
  **+$3,617.19** used start-of-day equities $0.12–$0.21/arm *above* broker `last_equity`
  (e.g. risky-3 5175.76 vs 5175.55 — and 5175.55 is what the arm's own 09:31 decision row
  recorded). Immaterial in dollars, but **SOD should be pinned to broker `last_equity`**,
  which is also what the first tick reads.
- **Two BTC/USD fills appear in a `date=2026-08-04` activities query** but belong to
  2026-08-03 20:45 ET. Alpaca's activities `date` parameter filters on **UTC**. The repo's
  own `fills-ledger.jsonl` correctly stamps them `date_et: 2026-08-03`, and `pdt_tracker`
  documents this exact trap — but any *new* ad-hoc broker query is exposed to it.
- **`entry-claim.json` is stale on all 5 arms** (last claim of the day, never cleared).
  **Checked, not a defect**: 180 s TTL plus date-specific 0DTE symbols means tomorrow can
  never match.

---

## §6 — THE OPEN QUESTION: adjudicating the 7× ENTER_BULL alarm *and* the retraction

**Both the alarm and the retraction were aimed at the wrong object. The re-entry count was
the symptom. The mechanism is a −6% premium stop evaluated once per minute.**

### 6a. What actually happened

All seven 09:46–09:57 `ENTER_BULL` ticks were `vwap_continuation` (BASE), which carries
`ExitShape(premium_stop_pct=-0.06, ...)` — a **−6% premium stop**, not the −50% catastrophe
cap that CLAUDE.md's chart-stop-primary doctrine describes for the core path. The first
four round trips were not "the engine re-entering because a lock is missing." They were
**the engine being stopped out at −6% and then legitimately re-triggering on a signal that
was still live.**

```
09:46 b8@1.75 → stop 1.6450 → 09:47 SELL_ALL "premium_stop @ 1.65"   −$104
09:50 b8@1.46 → stop 1.3724 → 09:52 SELL_ALL "premium_stop @ 1.37"   −$40
09:54 b8@1.52 → stop 1.4288 → 09:56 SELL_ALL "premium_stop @ 1.43"   −$144
09:57 b8@1.40 → stop 1.3160 → not hit → TP1 6@1.99, runner 2@2.25    +$524
```

Deleting the re-entries would have deleted **trade #4 as well**, because it is the same
signal on the same tick cadence. The retraction was right to refuse the standdown. But it
stopped at "it made money" and never named the mechanism — so the actual defect survived
the whole adjudication.

### 6b. The natural experiment — a 7¢ fill decided a $680 swing

risky-1 and risky-3 bought **the same contract within 2 seconds of each other**:

| arm | fill | −6% stop | outcome | P&L |
|---|---:|---:|---|---:|
| risky-1 | 09:50:07 @ **1.390** ×5 | **1.3066** | held to 11:25 | **+$640** |
| risky-3 | 09:50:09 @ **1.460** ×8 | **1.3724** | stopped 09:52 | **−$40** |

Same signal, same contract, same minute. The **only** difference was a 7-cent worse fill on
the larger order, which placed a percentage stop 5 cents higher — inside the noise.

### 6c. Worse: the stop is not actually enforced at its stated level

risky-1's stop was 1.3066. The real OPRA 09:56 bar printed a **low of 1.26** — decisively
through it. It was never triggered, because the exit manager samples once per minute:

```
09:55:05  best=1.65 worst=1.64  runner_stop=1.3066  actions=[]
09:56:05  best=1.39 worst=1.37  runner_stop=1.3066  actions=[]      ← bar low that minute: 1.26
09:57:07  best=1.41 worst=1.40  runner_stop=1.3066  actions=[]
```

**risky-1's +$640 winner survived on poll timing, not on stop design.** Twenty seconds later
and the same code sells at ~1.26–1.30 and books ≈ −$450.

At −6% on a ~$1.40 premium the stop band is ~8¢, while the observed 1-minute intrabar range
was routinely 8–14¢. **The sampling interval dominates the stop band, so the stop is
effectively random at this tightness.** This is C3/C2 territory and matches the standing
noise-floor memory (*10-min MAE −36% vs a −20% stop = winners stopped by noise*).

### 6d. What the −6% stop cost today — bounded, calibrated, non-oracle

> **My first counterfactual was fiction and I killed it.** Riding runners to the 15:50 close
> on a trend day produced **+$12,105**. Its own artifact hunt rejected it: mean |error|
> reproducing the *actual* −6% outcomes was **$291.86**, driven entirely by the two runner
> trades, because the engine's real runner machinery (chandelier / ribbon-flip / structure /
> time stops) is not modelled. **That number is not in this report except as the lesson.**

v2 models only the defensible branch: 1-min sampled bar opens (the engine's true cadence),
exit 100% at TP1 (+40%) — the runner credited **nothing** past TP1, a strict lower bound.

Calibration against reality: **stop-branch mean |error| = $21.60 (n=5)** — the branch the
counterfactual turns on. Runner branch under-reads by $219 **by design**.

| arm | sym | in | ACTUAL | CF ≥ (−50% cap) | delta ≥ |
|---|---|---|---:|---:|---:|
| risky-3 | 762C | 09:46 | −104.00 | +560.00 | +664.00 |
| risky-1 | 762C | 09:46 | −75.00 | +354.00 | +429.00 |
| risky-3 | 763C | 09:50 | −40.00 | +467.20 | +507.20 |
| risky-1 | 763C | 09:50 | +640.00 | +278.00 | −362.00 |
| risky-3 | 763C | 09:54 | −144.00 | +486.40 | +630.40 |
| risky-3 | 763C | 09:57 | +524.00 | +448.00 | −76.00 |
| risky-3 | 765C | 10:35 | −80.00 | +425.60 | +505.60 |
| **TOTAL** | | | **+721.00** | **+3019.20** | **+2298.20** |

**The −6% stop cost the vwap_continuation cohort at least $2,298 today** — with both real
winners deliberately penalised (−$362, −$76) inside that figure.

### 6e. What is *not* established — the honest limits

- **The −6% cell is not an unvalidated knob.** It passed all 5 OP-22 gates on n=149 real
  OPRA fills (`vwapcont-exit-ab-ship-gate.json`, OOS $75.47 vs $66.83/tr, WF 1.62).
- Its C29 strike-tier caveat is **recorded and now moot** — it was validated at ATM, and
  post-ATM-extension the fleet arms trade ATM too. I am **not** claiming a tier mismatch.
- **n = 7 trades, ONE session, ONE strategy, on its first live day ever** (import-dead since
  2026-06-25). This is not remotely a ratification.
- **The real open question this raises** — and the right next experiment — is whether the
  n=149 validation evaluated the stop **continuously (bar lows)** or **1-min sampled**. If
  continuously, the backtest systematically *over*-counted stop-outs and the live edge is
  mis-estimated in an unknown direction. §6c proves live enforcement is sampled. **Answer
  that before touching the knob.** A stop whose realised level depends on poll jitter is not
  the same instrument the A/B measured.

---

## FOLLOW-UPS — stated, not silently dropped

I shipped **no code**. That is a deliberate call, not an omission:

1. **The PDT one-liner (§4b) collides with an in-flight lane.** Task **L2-c ("Sizing
   counterfactual — qty10 + Rule-6 ceilings + PDT")** is active in a parallel agent. Editing
   `fleet_live.py`'s PDT feed while another lane reasons about PDT sizing would clobber it
   (`/fable-blast-radius`). **Route it through the orchestrator with L2-c.**
2. **The −6% stop must not be re-tuned on n=7 from a single green day.** That is the exact
   shape of the graveyard entries ("take-profit-earlier ×3", "pre-TP1 trailing lock ×4").
   The pre-registered question is §6e's sampling-fidelity check, not a knob change.

| # | Action | Owner | Gate |
|---|---|---|---|
| F1 | Route fleet PDT feed to `pdt_tracker.fetch_day_trades_used_5d` + guard asserting `day_trades` varies | orchestrator w/ L2-c | prereg + RED-proof |
| F2 | Re-check `params.json` `pdt_gate_mode` against **live** `multiplier`; add a premarket assert that gate mode matches account type | after-hours | guard test |
| F3 | Per-mechanism alert budget in entry-block-watch (or "always alert an unseen mechanism") | after-hours | guard test |
| F4 | Emit a `reanchor` marker on the fleet decision row (close the C7 gap) | after-hours | guard test |
| F5 | Determine whether the vwap_continuation A/B evaluated stops continuously or 1-min sampled | research | prereg before any knob change |
| F6 | Pin SOD equity to broker `last_equity` in the EOD roll-up | after-hours | — |
| F7 | Record L246 floor-rescue as **untested in production and currently unreachable** | doctrine | — |

**Candidate lesson (for `lesson-author`, not written by me):** *a shipped fix whose success
path emits no artifact is indistinguishable from a fix that never ran — SHIP A's fleet half
had to be proved by reconstructing stop arithmetic from an unrelated ledger.* (C7/C35.)

---

## Provenance

- Broker truth: `fleet_broker.load_creds()` → `/v2/account`, `/v2/orders`,
  `/v2/account/activities/FILL`, `/v2/positions`, all 5 arms, pulled 2026-08-04 ~16:10 ET.
- Decisions: `automation/state/core-decisions.jsonl` (776 rows today),
  `automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl` (384 rows each).
- OPRA: Alpaca `v1beta1/options/bars`, 1-min, 26 SPY 260804 call contracts (755C–780C).
- PDT counts computed with the repo's own `setup/scripts/pdt_tracker.py`.
- **Every counterfactual in this document is SIM, lower-bounded, and calibrated against the
  real outcomes it claims to model. No oracle figure appears in any live-executable column.**
