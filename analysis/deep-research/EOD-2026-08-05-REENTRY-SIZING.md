# EOD 2026-08-05 — LENS 5: THE RE-ENTRY LOOP ON ITS ADVERSARIAL DAY, + SIZING

**Run:** 2026-08-06 pre-dawn (ET verified `03:39:34 EDT`, `market_hours=False` via `setup/scripts/et_clock.py`).
**Authority:** real broker fills (`automation/state/fills-ledger.jsonl`, `attribution=="engine"`, 25 trading
days, 204 entry events) + real OPRA 1-min bars fetched live from Alpaca (392/405/385 bars for the three
2026-08-05 contracts, 400/386/375/399 for 2026-08-04) + the live exit-state ledger (`exit_pass` rows in
the per-arm and core decision journals — the exact `best_premium`/`worst_premium` the production exit
manager saw each tick).
**Reconciliation:** FIFO over engine fills gives 2026-08-05 = **−$1,935.00** vs the brief's broker day
**−$1,943.66** (Δ $8.66, fee/accounting). Per-arm: safe-2 −339.00 / −339.76, risky-1 −138.00 / −140.39,
risky-3 −1,458.00 / −1,462.29. 2026-08-04 reproduces the prior audit's **+$3,624** exactly.

---

## VERDICT — a PER-CONTRACT ENTRY CAP OF 3 is the change that survives both days. The stop width is not the lever, and the cooldown is not the shape.

| | cost on 08-04 (trend) | effect on 08-05 (chop) | all 25 real-fill days |
|---|---|---|---|
| **Cap 3 entries per contract per arm per day** | **$0.00 — removes nothing** | **+$653** | **+$720**, 3 days affected, **3 win / 0 lose** |
| 30-min per-setup cooldown | **−$380** | +$1,058 | +$1,260, 11 days, 10 win / 1 lose |
| Widen the −6% stop | (n/a) | **worse at every width** | — |

Cap-3 removed **12 entries in 25 days. Exactly one was a winner (+$6).** On 2026-08-04 the winning
re-entry — risky-3's 763C at 09:57, +$524 — was the **3rd** entry on that contract, so cap-3 preserves
it by construction. This is the rare guard whose historical worst case is **zero**.

**Three things the brief asked that came back the other way, and I am reporting them against my own
draft thesis:**

1. **Widening the stop makes 08-05 WORSE, not better.** Every cell down every column of the stop-width
   grid degrades as the stop widens (risky-3: −$661 at −6% → −$960 at −50%). The 776C did not shake us
   out of a winner; it went down and stayed down.
2. **The TP1 knob that saved risky-1's put is a population NULL.** On the clean single-knob pair
   (risky-1 TP1 +50% vs safe-3 TP1 +100%, *every other exit field identical*), restricted to the 8
   trades where TP1 could bind: **mean −$3.11/contract, risky-1 wins 1 of 8.** The 08-05 put is n=1.
3. **ATM-TIER-EXTENSION: risky-3 has MET its pre-registered kill criterion** (n=14 ≥ 10 fills, cohort
   **−$653 < 0**). risky-1 has met the floor on the other side (n=11, **+$903**) and stays.

---

## 1. THE OPEN QUESTION, ANSWERED FROM THE LEDGER: WHY TP1 NEVER FIRED

The brief asked why risky-3 (entry 1.65, peak 2.62+) never fired a TP1 that "sits at ~2.31". **The
premise is wrong: there is no +40% TP1 on that trade.** The 11:48 entry was
`BEARISH_REJECTION_RIDE_THE_RIBBON` → the `ribbon_ride` strategy, whose registry exit shape carries
**`tp1_premium_pct=1.0` (+100%)**. +40% belongs to `vwap_continuation`, the morning call.

The live placement record says it in the arm's own words:

```
risky-3 11:48:04 ENTER_BEAR  placement: {"mid": 1.7, "tp": 3.4, "tp1_premium_pct": 1.0,
                                         "stop": 0.825, "stop_display": "STRUCTURE@772.33 (cat -50%)"}
```

| arm | entry | TP1 level | peak `best_premium` (live ledger) | TP1 fired? | outcome |
|---|---|---|---|---|---|
| risky-1 | 1.69 | **2.535** (+50%, arm `exit_patch`) | 2.68 @ 12:09 | **YES** → sold 3, ratchet to BE, trail exit 12:17 | **+$347** |
| risky-3 | 1.65 | 3.300 (+100%, registry) | 2.69 @ 12:09 | no | −$664 |
| safe-2 | 1.63 | 3.260 (+100%, registry) | 2.76 @ 12:09 | no | −$255 |

**Consequence, and this is the structural finding:** `profit_lock_armed` is only set at/after TP1
(`profit_lock_arm_scope="post_tp1"`, the default). TP1 never firing means **the chandelier trail never
armed**, so the *only* live exit on risky-3 and safe-2 was the **−50% catastrophe cap** — which is
exactly what fired, at 14:05 and 14:12. `runner_stop` sat at 0.825 / 0.815 and **never moved for 133
consecutive ticks.** Both arms rode +63% / +69% to −50% with no intermediate exit of any kind.

### 1a. How reachable is +100%? — measured on the live ledger, no modeling

`best_premium` in `exit_pass` is what the production exit manager itself saw. Max over each position's
life = the best price the machine could possibly have sold into.

| cohort | n | median MFE | ≥+30% | ≥+40% | ≥+50% | **≥+100%** |
|---|---|---|---|---|---|---|
| all engine entries | 198 | +12.5% | 31% | 27% | 22% | 13% |
| **ribbon_ride (TP1 set to +100%)** | **124** | **+16.3%** | 35% | 31% | 23% | **14%** |
| vwap_continuation (TP1 +40%) | 17 | +1.5% | 12% | 12% | 12% | 12% |

**86% of ribbon_ride positions never reach their own TP1**, take no partial profit, never arm the
profit-lock, and are managed solely by the structure stop / −50% cap / time stop. Confirmed
independently: `tp1_filled=True` appears in the live ledger on **19 of 124** ribbon entries.

### 1b. A live display-vs-behaviour divergence in the core lane (correctness bug, ships free)

`setup/scripts/heartbeat_core.py` computes the logged TP from **params.json** but registers the exit
state from **strategies.py**:

```python
_tp1_pct = (_params_float(params, _xov["tp1"], 0.30) if _xov
            else float(params.get("tp1_premium_pct", 0.30)))   # params.json -> 0.5
tp = round(mid * (1 + _tp1_pct), 2)                            # logs "tp": 2.5
...
_s = _strat.by_name("ribbon_ride"); _shape = _s.exit.to_dict() # tp1_premium_pct = 1.0  <-- enforced
```

`ribbon_ride` is **not** in `_SETUP_EXIT_OVERRIDES`, so `_xov is None` on every ribbon entry — the
majority of the book. safe-2's 11:49 put logged `"tp": 2.5` and was managed at 3.26. **Every plan log
and journal row for a core-lane ribbon trade states a TP1 the machine will not honour.** C14/C7 class.
This is a labelling defect, not a P&L claim — see §4 for why the behaviour should *not* be changed yet.

---

## 2. THE DISCRIMINATING TEST — STOP TOO TIGHT, OR NO RE-ENTRY DISCIPLINE?

**Why the entry side needs zero modeling.** A wider stop can only *delay* an exit, never advance one, so
the counterfactual flat windows are a strict **subset** of the real flat windows. Every entry a
wider-stop counterfactual can take therefore lands on a minute when the arm was really flat **and** the
signal really fired — i.e. one of the 5 real ENTERs, at its **real broker fill price**.

This is verifiable, not assumed. The arms' own `reason` strings separate the two states:

```
09:59  HOLD  flat=False  risk_gate denied: PA3V7JT25H6Z: position already open   <- signal FIRED, blocked
10:07  HOLD  flat=False  no qualifying setup (no strategy fired)                 <- signal did NOT fire
10:02  HOLD  flat=True   no qualifying setup (no strategy fired)                 <- flat, no signal
```

Exactly **5 ENTER decisions per arm, all 5 placed, all while flat, zero refusals.** (Materially unlike
08-04, where 3 of 7 decision rows were `SKIP_DUPLICATE_CLAIM`.)

**Grid: stop width × cooldown, risky-3, real OPRA 1-min bars replayed through the production
`exit_manager.plan_exit_actions`. `(n)` = entries taken.**

| stop | 0m (live) | 5m | 10m | 15m | 30m | once/day |
|---|---|---|---|---|---|---|
| **−6% (live)** | **−661 (n5)** | −403 (n3) | −271 (n2) | −267 (n2) | **−139 (n1)** | −139 (n1) |
| −10% | −764 (n4) | −588 (n3) | −384 (n2) | −404 (n2) | −208 (n1) | −208 (n1) |
| −12% | −706 (n3) | −706 (n3) | −489 (n2) | −482 (n2) | −252 (n1) | −252 (n1) |
| −15% | −587 (n2) | −587 (n2) | −577 (n2) | −569 (n2) | −288 (n1) | −288 (n1) |
| −20% | −770 (n2) | −770 (n2) | −779 (n2) | −768 (n2) | −402 (n1) | −402 (n1) |
| −25% | −928 (n2) | −928 (n2) | −920 (n2) | −922 (n2) | −472 (n1) | −472 (n1) |
| −50% | −960 (n1) | −960 (n1) | −960 (n1) | −960 (n1) | −960 (n1) | −960 (n1) |

(risky-1 same shape: −413/−252/−170/−168/−88/−88 across the −6% row; −609 at −50%.)

**Answer: the two mechanisms are coupled, and the coupling runs the wrong way for the stop.**
Widening the stop *does* mechanically dissolve the loop — n5 → n1 as the stop widens — but it costs
more than the loop did, because a wider stop simply holds a losing contract longer. **A wider stop alone
does not fix this; it converts five small losses into one large one, and the large one is bigger.**

**Parity + bias disclosure (L251).** All 5 modeled trades terminate at the **same stage**
(`premium_stop`) as the real fills — 5/5 stage parity. Modeled exits fire **1–3 minutes earlier** than
live, because the replay reads the full 1-min bar low while the live engine reads a once-a-minute
snapshot (the documented option-bar-resolution bias). Modeled control = −$661 vs real −$794 at 3.3c
slippage; at 10c the control is −$829 vs −$794, bracketing reality. **The grid ordering is identical at
both slippage settings.** The bias under-counts slippage on high-entry-count cells, so the measured
benefit of *fewer* entries is conservative. Second-order check: no wide-stop cell is still holding the
call at 11:48, so **no cell blocks the put entry** (latest exit across all cells = 10:30).

---

## 3. THE COOLDOWN, RE-ADJUDICATED — AND WHY THE ORDINAL CAP BEATS IT

### 3a. Cooldown grid, Tier 1 (a cooldown can only remove real entries), all scopes

Key = `(arm, date, symbol)`, anchor = prior kept entry. Setup-keyed and exit-anchored variants are in
the JSON; the sign pattern is identical across all four combinations.

| scope | 0 (live) | 5 min | 10 min | 15 min | 30 min | once/day |
|---|---|---|---|---|---|---|
| 2026-08-05 only | −1,935 (n14) | −1,224 | −1,137 | −1,079 | **−877** | −877 |
| 2026-08-04 only | +3,624 (n25) | +3,768 | +3,244 | +3,244 | +3,244 | +1,427 |
| COMBINED 04+05 | +1,689 (n39) | +2,544 | +2,107 | +2,165 | +2,367 | +550 |
| **ALL 25 days** | **+317 (n204)** | +1,346 | +1,041 | +1,099 | **+1,577** | −140 |
| EX-08-04 (24 days) | −3,307 | −2,422 | −2,203 | −2,145 | −1,667 | −1,567 |

**Does it clear its bar?** The 08-04 audit set: OOS positive **and** WF ≥ 0.70 **and** sub-window stable
**and** monotonic.

- **Sign: yes.** 30-min cell affects 11 of 25 days, **10 win / 1 lose**, total +$1,260 (sign test on
  10/11, p ≈ 0.006).
- **Sub-window: yes.** First half +$323, second half +$937 — both positive.
- **Monotonicity: NO.** +1,346 → +1,041 → +1,099 → +1,577 → −140. Still zig-zags, still the noise
  signature the prior audit named.
- **Magnitude concentration: FAILS C4.** +$1,058 of the +$1,260 (**84%**) is 08-05 alone. Ex-08-05 the
  30-min cooldown is +$202 over 10 affected days.
- **And it costs −$380 on the trend day.** That is the disqualifier the brief asked for.

### 3b. The threshold-free view — where the damage actually lives

No cutoff anywhere; just P&L by position in the same-contract sequence, all 25 days:

| ordinal | n | total | mean | win% |
|---|---|---|---|---|
| #1 | 145 | −$140 | −$1.0 | 19% |
| **#2** | 30 | **+$1,070** | **+$35.7** | 13% |
| #3 | 17 | +$107 | +$6.3 | 24% |
| **#4** | 9 | **−$257** | −$28.6 | 11% |
| **#5** | 3 | **−$463** | −$154.3 | **0%** |

**The second entry is the most profitable ordinal in the book.** The damage is concentrated entirely at
**#4 and #5: n=12, −$720, one winner.** A blanket cooldown taxes #2 and #3 to reach #4 and #5 — that is
precisely why it costs money on trend days.

Dose–response by gap since prior entry confirms the same thing from the other axis: every bucket under
30 minutes is negative (0–3m −$174, 3–5m −$533, 5–10m −$277, 10–15m −$27, 15–30m −$261 → **−$1,272 over
32 attempts, 13% win rate**), while 30–60m is +$1,759. But ex-08-04/08-05 the 30–60m bucket is also
negative (−$58), so the sign flip at 30 minutes is **not** independent of the two anchor days. The
ordinal split is.

### 3c. THE SHIPPABLE SHAPE — cap 3 entries per contract, per arm, per day

| scope | live | cap 1 | cap 2 | **cap 3** | cap 4 |
|---|---|---|---|---|---|
| 2026-08-05 | −1,935 | −877 | −1,022 | **−1,282** | −1,484 |
| **2026-08-04** | **+3,624** | +1,427 | +3,100 | **+3,624** | +3,624 |
| COMBINED 04+05 | +1,689 | +550 | +2,078 | **+2,342** | +2,140 |
| **ALL 25 days** | **+317** | −140 | +930 | **+1,037** | +780 |
| EX 04+05 (23 days) | −1,372 | −690 | −1,148 | −1,305 | −1,360 |

Everything cap-3 removes, in 25 days of real fills:

| | date | arm | time | contract | P&L |
|---|---|---|---|---|---|
| #4 | 06-30 | risky-3 | 15:13 | C750 | −5 |
| #4 | 06-30 | risky-1 | 15:21 | C750 | −30 |
| #4 | 06-30 | safe-3 | 15:21 | C750 | −18 |
| #4 | 07-06 | safe-2 | 13:39 | P750 | **+6** ← the only winner |
| #5 | 07-06 | safe-2 | 13:40 | P750 | −12 |
| #4 | 07-06 | safe-3 | 14:22 | C754 | 0 |
| #4 | 07-06 | safe-1 | 14:22 | C753 | −8 |
| #4 | 07-06 | risky-1 | 14:22 | C754 | 0 |
| #4 | **08-05** | risky-1 | 10:14 | C776 | −80 |
| #4 | **08-05** | risky-3 | 10:14 | C776 | −122 |
| #5 | **08-05** | risky-1 | 10:18 | C776 | −155 |
| #5 | **08-05** | risky-3 | 10:18 | C776 | −296 |

**Total removed: −$720. Winners removed: 1 (+$6).** Days affected: 3 (06-30 +$53, 07-06 +$14,
08-05 +$653) — **3 wins, 0 losses, and $0 on 08-04.**

Why it is free on the trend day, stated as data rather than assertion — 08-04's multi-entry sequences:

```
risky-3 C763: #1 09:50 -40 | #2 09:54 -144 | #3 09:57 +524     <- the day's rescue is the 3rd
risky-1 C769: #1 11:52 -110 | #2 12:28 +651
risky-3 C769: #1 11:52 -110 | #2 12:28 +788
safe-3  C769: #1 11:52 -66  | #2 12:28 +378
```

**Honest bounding.** Cap-3 is the argmax of a 4-cell grid, but cap-2 (+$613) and cap-4 (+$463) are also
positive — a smooth single peak, not the knife-edge the 08-04 cooldown grid produced. It fires on 12% of
sessions, so this is a **tail guard, not an edge**; the n=3 day-level sign test is p=0.125 and proves
nothing on its own. What carries it is the mechanism (n=12 attempts at ordinal ≥4, 1 winner, 0% win rate
at #5) plus the **provable $0 historical cost**. Verified no-look-ahead: the cap is a count of prior
entries on the same contract, fully known at entry time. Verified no substitution effect on 08-05: after
10:20 every tick logs `no qualifying setup` until 11:48, which the arms took anyway — blocking #4/#5
creates no alternative trade. PDT strictly improves.

---

## 4. THE TENSION THE BRIEF DEMANDED BE RESOLVED

Tuesday said *don't tighten*; Wednesday said *take profit early*. risky-1 won both days. The brief asked
which single change survives both, or an honest admission that none does.

**The answer is that risky-1's advantage was never one exit philosophy — it was two different things on
the two days, and only one of them generalises.**

- **08-04:** risky-1's edge on the 763C was **entry-fill luck, already adjudicated**. The prior audit
  proved it survived its stop by **0.34 cents**. Per-contract, risky-1 +$128.0 vs risky-3 −$5.0 on the
  same contract, same minute — that +$133 is fill price, not exit shape.
- **08-05:** risky-1's edge on the put **was** the exit knob (TP1 +50% vs +100%), n=1.

Test it properly, on the pair that differs in **exactly one exit field** — risky-1 (`tp1_premium_pct`
0.5) vs safe-3 (registry 1.0); both carry `stop_mode=structure`, `profit_lock_mode=trailing`,
`trail_pct=0.15`. Restricted to trades where TP1 could bind (live MFE ≥ +50%):

| date | contract | MFE | risky-1 (+50%) | safe-3 (+100%) | edge |
|---|---|---|---|---|---|
| 06-30 | C746 | +60% | −16.0/ct | −11.0/ct | −5.0 |
| 07-06 | C754 | +67% | −1.0 | −1.0 | 0.0 |
| 07-06 | C754 | +75% | 0.0 | 0.0 | 0.0 |
| 07-06 | C755 | +100% | −1.0 | −1.0 | 0.0 |
| 07-17 | P742 | +79% | 0.0 | 0.0 | 0.0 |
| 07-29 | C740 | +255% | +83.6 | +88.3 | −4.7 |
| 08-03 | C754 | +157% | +29.0 | +48.3 | −19.3 |
| 08-04 | C769 | +223% | +130.2 | +126.0 | +4.2 |
| | | **n=8** | | | **mean −$3.11/ct, 1 win** |

Unrestricted, n=26 paired: **−$0.26/contract.** **The +50% TP1 is a null.** It did not cost anything on
the trend day — and it has not earned anything anywhere else either. The 08-05 put is a single
observation on which safe-3 did not trade at all.

**So: the change that survives both days is the per-contract entry cap of 3, and nothing on the exit
axis.** The TP1 finding is a *correctness* result (§1b) and a *structural* result (§1a — 86% of ribbon
trades never take a partial and never arm a trail), not yet a P&L result.

---

## 5. SIZING — HOW MUCH OF risky-3's −$1,462 WAS SIZE?

risky-3 and risky-1 took the **identical six signals**. 2×2 factorial on risky-3's book using the real
per-contract outcomes of each arm:

| | qty 5 (risky-1 size) | qty 8 (risky-3 size) |
|---|---|---|
| TP1 +50% (risky-1 knobs) | −$138.00 | −$220.80 |
| TP1 +100% (risky-3 knobs) | −$911.25 | **−$1,458.00 ← actual** |

- **Size effect (qty8 → qty5): +$546.75 — 38% of the loss.**
- **Knob effect (at qty 8): +$1,237.20 — 85% of the loss.**
- They are not additive; the knob dominates because it is levered by the size.

Where the knob effect lives: **calls-only per-contract, risky-1 −$97.00 vs risky-3 −$99.25 — a $2.25
gap.** The morning loop was a size story and nothing else. **Put-only per-contract, +$69.40 vs −$83.00 —
a $152.40 gap.** All of risky-3's decision deficit is one trade.

**Rule-5 kill switch (Bold-class, −50% of start-of-day equity):**

| arm | SOD | EOD | day | kill level | budget used | headroom |
|---|---|---|---|---|---|---|
| **risky-3** | 5,977.81 | 4,515.52 | **−1,462.29 (−24.5%)** | −2,988.91 | **48.9%** | −1,526.62 |
| risky-1 | 6,184.30 | 6,043.91 | −140.39 (−2.3%) | −3,092.15 | 4.5% | −2,951.76 |
| safe-2 | 5,729.22 | 5,389.46 | −339.76 (−5.9%) | −1,718.77 (−30% Safe) | 19.8% | −1,379.01 |

risky-3 consumed **just under half its daily loss budget** and did not come close to halting. It would
have needed to roughly double the day's damage. The switch was never near firing — which is the point:
**a −50% daily kill is not a control that engages on a −24.5% day.** Nothing here argues for tightening
it; it argues that the position-level guard (cap-3) is the only thing operating at this scale.

**C31 — the brief asked whether qty8 sits on the wrong side of J's own evidence. The premise needs
correcting first.** The "1–2 lots +$4,576 / 3+ lots −$17,461" split is a **retired accounting artifact**
(per-sell-fill banding credited profit-taking clips out of 3+ lot positions into the small band). The
honest episode-level number is 1–2 lots = **−$4,420**; J was never net profitable at any size. Do not
re-quote the old split. **What survives** is (a) the monotonic per-contract gradient (−$7.1/ct small →
−$28.7/ct large) and (b) the real identified killer: **intra-position averaging-down plus refusing the
stop, which "are one behaviour."** By that corrected standard risky-3 *is* on the wrong side — not
because qty8 is 3+ lots, but because five successively cheaper entries into the same falling contract
(2.35 → 2.27 → 2.19 → 2.12 → 2.09) **is averaging down, executed by re-entry instead of by adding.**
The `fb.is_flat_spy_options` structural guard does not see it, because the arm really is flat between
legs. Cap-3 is the missing half of that guard.

---

## 6. ATM-TIER-EXTENSION — KILL CRITERION STATUS AFTER TWO LIVE SESSIONS

Pre-registration: `analysis/recommendations/atm-tier-extension-2k10k-prereg-2026-08-03.json`
(frozen 2026-08-04T00:25 ET). Sample floor **n ≥ 10 fills per arm OR 10 sessions, whichever first**;
kill = **per-arm net realized P&L on the new-tier cohort < 0 at the sample floor → revert that arm same
day.** All entries since arming verified ATM (strikes track spot: K776 at SPY≈776, K769 at SPY≈769).

| arm | n entries | net | by session | floor reached? | verdict |
|---|---|---|---|---|---|
| **risky-3** | **14** | **−$653** | 08-04 +805, 08-05 −1,458 | **YES (14 ≥ 10)** | **KILL CRITERION MET → revert due** |
| risky-1 | 11 | +$903 | 08-04 +1,041, 08-05 −138 | YES (11 ≥ 10) | **KEEP** |
| safe-3 | 6 | +$637 | 08-04 +637 | no | continue |
| bold-2 | 3 | +$479 | 08-04 +479 | no | continue |
| **cohort** | **34** | **+$1,366** | | | aggregate positive |

**`anchor_no_regression`: PASSES emphatically.** `SKIP_MIN_PREMIUM_FLOOR` refusals went from the
08-03 baseline of **33 / 35 / 35** (safe-3 / risky-1 / risky-3) to **0 / 0 / 0** on both 08-04 and
08-05. The extension did exactly the job it was built for.

**Reported as met, with the mechanism stated separately and not used to explain it away.** risky-3's
−$653 is −$794 (the 776C loop, a re-entry defect) plus −$664 (the put, a TP1 defect) against +$805 on
08-04. **Neither failure is a strike-tier failure**, and reverting to OTM-2 would reinstate ~35
refusals/day. `sub_window_stable` is un-evaluable on a two-session cohort of opposite signs. But the
pre-registration exists precisely to stop a post-hoc rescue, so the finding stands as written:
**risky-3 has met its kill criterion; either honour the revert or amend the prereg in writing with a
documented reason — not silently.** The 08-04 audit's framing of this change as "a ~2.2x size increase
in a strike-selection costume" that lost −$1,304 across 5 hostile days is **contradicted by the live
cohort, which is +$1,366 over 34 real fills.**

---

## 7. WHAT I RECOMMEND

**SHIP (paper, reversible, guard + RED-proof + one-line revert):**
**PER-CONTRACT-ENTRY-CAP-3** — refuse a 4th entry on the same `(arm, date, option symbol)`. Placement-
path guard, evaluated at entry, no look-ahead. Historical cost $0 on the trend day, +$720 across 25
days, 12 blocked entries with 1 winner. Kill: n ≥ 10 blocked entries or 10 sessions, net < 0 → delete.

**SHIP (correctness, no behaviour change):**
Fix the `heartbeat_core.py` logged-`tp` divergence so the plan log reports the `tp1_premium_pct`
actually registered with `exit_manager` (§1b), and assert it in a guard. This is a lying instrument,
not a strategy change.

**PRE-REGISTER, DO NOT SHIP:**
`ribbon_ride` TP1 reachability. The +100% tier is reached on 14% of entries and 86% of ribbon positions
never arm a profit-lock — but the clean paired live A/B says +50% is worth **−$3.11/contract** over 8
binding trades. The A/B is already running for free on risky-1; let it run to n ≥ 15 binding trades
before touching the registry.

**REVERT DUE (per its own prereg):** risky-3's ATM tier participation. See §6.

**NOT RECOMMENDED:** widening the `vwap_continuation` stop (§2 — worse at every width, on the exact day
the 08-04 audit predicted it would help); any time-based re-entry cooldown (§3a — costs $380 on the
trend day, non-monotonic, 84% of its benefit is one session).

**Scored prediction from the 08-04 audit — it came true.** That audit wrote: *"The −6% stop on a chop
day — that is the treadmill, and it is the day we have not seen yet."* 2026-08-05 delivered exactly that
day, and the −6% stop fired on 10 of 10 round trips. But the audit's proposed remedy (PREREG-A, widen
the stop) is **falsified** by the day it was waiting for: widening makes it worse. The treadmill was
real; the brake was the wrong one.

---

## APPENDIX — 2026-08-05 engine round trips, real broker fills

| arm | in | out | contract | qty | entry | P&L | setup / live exit config |
|---|---|---|---|---|---|---|---|
| risky-1 | 09:58:05 | 10:01:06 | C776 | 5 | 2.37 | −85 | VWAP_CONTINUATION stop −6% premium |
| risky-3 | 09:58:07 | 10:01:07 | C776 | 8 | 2.35 | −136 | " |
| safe-2 | 10:01:58 | 10:20:04 | C777 | 3 | 1.61 | −84 | vwap_reclaim_failed_break, stop −8% premium |
| risky-1 | 10:06:05 | 10:08:05 | C776 | 5 | 2.27 | −65 | " |
| risky-3 | 10:06:13 | 10:09:05 | C776 | 8 | 2.27 | −80 | " |
| risky-1 | 10:10:06 | 10:13:05 | C776 | 5 | 2.20 | −100 | " |
| risky-3 | 10:10:07 | 10:13:06 | C776 | 8 | 2.19 | −160 | " |
| risky-1 | 10:14:05 | 10:17:05 | C776 | 5 | 2.12 | −80 | ← cap-3 blocks |
| risky-3 | 10:14:07 | 10:17:06 | C776 | 8 | 2.12 | −122 | ← cap-3 blocks |
| risky-1 | 10:18:06 | 10:20:06 | C776 | 5 | 2.06 | −155 | ← cap-3 blocks |
| risky-3 | 10:18:07 | 10:20:07 | C776 | 8 | 2.09 | −296 | ← cap-3 blocks |
| risky-1 | 11:48:05 | 12:17:05 | P772 | 5 | 1.69 | **+347** | ribbon_ride, TP1 **+50%** (arm patch), structure/−50% cap |
| risky-3 | 11:48:07 | 14:05:07 | P772 | 8 | 1.65 | −664 | ribbon_ride, TP1 **+100%** (registry) |
| safe-2 | 11:49:07 | 14:12:04 | P772 | 3 | 1.63 | −255 | ribbon_ride, TP1 **+100%** (logged as 2.50) |

**Day total −$1,935.00** (engine round trips) vs broker **−$1,943.66**.

Realized stop slippage, 13 losing exits: median **3.3c** below the configured stop, max **24.5c**
(risky-3 10:18, filled 1.72 against a 1.9646 stop = −17.7% realized on a −6% stop). The −6% stop did not
cost 6% on the fast bars; it cost 15–18%.

**PDT — still UNVERIFIED, still a missing instrument.** risky-3 closed 6 round trips on 08-05 and 8 on
08-04 on a `multiplier=4` account. The Alpaca payload returns no `daytrade_count` / `pattern_day_trader`
field, so headroom could not be confirmed from the broker this session. Named, not asserted — same gap
the 08-04 audit flagged, still open.
