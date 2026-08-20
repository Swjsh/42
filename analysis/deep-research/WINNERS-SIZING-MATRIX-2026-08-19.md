# WINNERS lane — POSITION SIZING, full matrix on every trade ever taken

> **Scope: ANALYSIS AND PROPOSAL ONLY.** Nothing armed, no `params*.json` touched, no orders.
> Every recommendation below ships as a **pre-registered hypothesis with a kill criterion**.
>
> Dataset: `analysis/recommendations/trade-matrix.json` — 303 closed round trips, 5 arms,
> 35 trading days, 2026-06-26..2026-08-19.
> Instrument: [`setup/scripts/sizing_matrix_2026_08_19.py`](../../setup/scripts/sizing_matrix_2026_08_19.py)
> · machine output: [`analysis/recommendations/sizing-matrix-2026-08-19.json`](../recommendations/sizing-matrix-2026-08-19.json)

---

## 🎯 VERDICT

**The best sizing cell is `MINCON-FLAT` — every arm flat at its own `min_contracts` (3/3/5/5/5), which means DE-ARMING the fleet equity/elite ladder and risky-3's cheap-contract boost. Worth +$1,575 net-after-costs of forward-available money. Verdict: WEAK — two days carry 104% of it.**

- 📉 **Sizing is not a winner-amplifier here. It is a leak.** Every cell that "beats" production does so by taking size OFF, not by putting size ON. There is **no cell in the matrix where sizing UP made money at acceptable risk.**
- ⚠️ **The lane premise was wrong and the correction matters more than the matrix.** "Every arm uses a flat min_contracts" is true only for the two CORE arms. The three FLEET arms already run an **equity-tiered + conviction-scaled ladder**. Equity-scaled and conviction-scaled sizing are not hypotheses here — they are **armed, and they have cost money**.
- 🚨 **One live knob has already met its own pre-registered kill bar:** risky-3's `cheap_contract_qty_boost` — 20 boosted fills / 10 sessions / net **negative on both readings** (−$675 as traded, −$371 marginal), 8 of 10 sessions negative.
- ❌ **Win rate is identical (22.11%) in all 26 cells.** Sizing cannot change whether a trade wins. This lever moves dollars only. Any sizing claim that reports a win-rate change is a bug.
- 🧮 **No cell makes the book profitable.** The single cell with positive net (`RECENCY-UP`, +$362) is the C31 martingale, is 93% one day, and fails the day bootstrap. Killed on sight.

---

## ⚠️ PREMISE CORRECTION — production sizing is not flat, and it changed three times

The brief said "today every arm uses a flat `min_contracts` (3/5/10)". Measured against the code and the fills:

| Lane | Arms | Sizing mechanism today |
|---|---|---|
| **Core** | safe-2, bold-2 | `heartbeat_core` → **flat `min_contracts`** (3 / 5). Genuinely flat. |
| **Fleet** | safe-3, risky-1, risky-3 | `fleet_executor._qty_for` → **`params.json#position_sizing_tiers`**, an equity-tiered ladder with a conviction upsize. In the $2K–$10K tier: safe **base 5 / elite 8**, risky **base 8 / elite 12**. `min_contracts` is applied as a **CEILING only when `_apply_recency_min_sizing` reads a RED recency verdict** (ribbon_ride scope). |

That is why 52 of 303 rows filled **above** `min_contracts` (qty 6–12), and why `safe-3` — nominally a "qty 3" arm — traded **8 contracts three times on 2026-08-07**.

Three sizing configs were live at different points inside the same 35-day window, so **"PRODUCTION" is not one cell**:

| Config | Shipped | Status today | Rows it upsized | Net-after-costs effect |
|---|---|---|---|---|
| `cheap_contract_qty_boost` (risky-3, qty 10 under $0.50) | 2026-08-03 `966c48f1` | **LIVE** | 20 | **−$371** |
| `min_contracts_equity_scaled` (both core params files) | 2026-08-13 `7f354c19` | **REVERTED 2026-08-14 `636c5ba4`** | 4 | **−$837** |
| `position_sizing_tiers` ladder (fleet arms) | pre-window | **LIVE** | ~28 | the balance |

> 🚨 **The −$837 from the dead equity-scaler is NOT available forward.** It was armed for one day, lost on the 2026-08-14 cluster (safe-2 qty 6, safe-3 qty 7, bold-2 qty 10, risky-1 qty 12 — all on the same signal, all losers), and was reverted the next day. Any counterfactual that "wins" it back is **double-counting a closed loop.** Every headline number below is quoted twice: **as-measured** (includes it) and **forward-available** (excludes it).

---

## 📊 THE FULL MATRIX — every cell, every trade

All figures net of **real fees** (OCC/ORF/TAF/SEC, `cost_model.py` empirical rates) **and measured exit slippage** (0.129 × exit-minute traded range × contracts × 100, `exit_fill_realism.py`). Rule 6 enforced in every cell. `$/ctr` is the **leverage-neutral shape metric** — the only fair way to compare cells that trade different contract counts.

**◀ = production.** `Δ vs MINCON` is the honest comparison (both are flat-reference cells); `Δ vs PROD` is shown because production is what actually happened.

| cell | ctrs | gross | **net after costs** | **$/ctr** | WR% | avg win | avg loss | max DD | worst day | Δ vs PROD | Δ vs MINCON | top-day share | boot +% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **PRODUCTION** ◀ | 1500 | −1804 | **−3768** | **−2.51** | 22.1 | 224 | −80 | −6135 | −2774 | 0 | −2434 | 0.43 | 2.5 |
| **MINCON-FLAT** | 1270 | +397 | **−1334** | **−1.05** | 22.1 | 211 | −65 | **−4458** | **−1722** | **+2434** | 0 | 0.43 | **96.7** |
| MINCON-FLAT-2X | 2427 | +1415 | −1763 | −0.73 | 22.1 | 405 | −123 | −8910 | −3443 | +2005 | −430 | −7.77 | 45.4 |
| FLAT-1 | 303 | +71 | −360 | −1.19 | 22.1 | 51 | −16 | −1028 | −451 | +3408 | +974 | −2.68 | 60.6 |
| FLAT-2 | 606 | −25 | −877 | −1.45 | 22.1 | 99 | −32 | −2218 | −901 | +2891 | +456 | −3.90 | 57.6 |
| FLAT-3 | 908 | +326 | −942 | −1.04 | 22.1 | 154 | −48 | −3244 | −1351 | +2827 | +392 | −1.91 | 62.2 |
| FLAT-5 | 1461 | +705 | −1280 | −0.88 | 22.1 | 249 | −76 | −5462 | −2251 | +2488 | +54 | 15.04 | 51.2 |
| FLAT-8 | 2236 | +1617 | −1325 | −0.59 | 22.1 | 387 | −115 | −8702 | −3602 | +2444 | +9 | 372.42 | 48.8 |
| FLAT-10 | 2727 | +2296 | −1259 | −0.46 | 22.1 | 476 | −140 | −10854 | −4502 | +2509 | +75 | 66.94 | 49.1 |
| EQUITY-2% | 560 | −138 | −647 | −1.16 | 22.1 | 56 | −19 | −1261 | −523 | +3121 | +687 | −3.80 | 58.0 |
| EQUITY-5% | 1245 | −287 | −1211 | −0.97 | 22.1 | 103 | −34 | −2309 | −1114 | +2557 | +123 | −21.76 | 52.0 |
| EQUITY-10% | 2422 | +845 | −1067 | −0.44 | 22.1 | 240 | −73 | −5107 | −2773 | +2701 | +266 | 4.09 | 53.7 |
| EQUITY-20% | 4266 | +1182 | −2654 | −0.62 | 21.9 | 506 | −153 | −12106 | −6838 | +1114 | −1320 | 3.87 | 44.5 |
| EQUITY-30% | 5707 | +440 | −5122 | −0.90 | 21.9 | 744 | −230 | −20000 | −11354 | −1354 | −3789 | 2.54 | 41.0 |
| EQUITY-50% | 7011 | −1175 | −8483 | −1.21 | 21.8 | 993 | −315 | **−27227** | **−15340** | −4715 | −7150 | 1.90 | 38.0 |
| VOL-INV-VIX | 1281 | +299 | −1428 | −1.11 | 22.1 | 211 | −66 | −4626 | −1869 | +2340 | −94 | 2.01 | 39.0 |
| VOL-DIR-VIX | 1278 | +140 | −1610 | −1.26 | 22.1 | 210 | −66 | −4458 | −1722 | +2158 | −276 | 0.89 | 22.9 |
| CONV-SCORE | 1835 | +1489 | −862 | −0.47 | 22.1 | 320 | −94 | −7568 | −3387 | +2906 | +472 | 5.37 | 53.2 |
| CONV-SCORE-INV | 1097 | −804 | −2335 | −2.13 | 22.1 | 157 | −55 | −4222 | −1489 | +1433 | −1001 | 1.17 | 34.0 |
| CONV-TIER | 1441 | +508 | −1250 | −0.87 | 22.1 | 237 | −73 | −5368 | −2636 | +2518 | +83 | −10.98 | 50.1 |
| CONV-TIER-INV | 1324 | −267 | −2243 | −1.69 | 22.1 | 209 | −69 | −4671 | −2753 | +1525 | −910 | 1.32 | 34.5 |
| CHEAP-BOOST | 1705 | +1179 | −850 | −0.50 | 22.1 | 248 | −74 | −4394 | −1903 | +2918 | +484 | 1.06 | 67.6 |
| RICH-BOOST | 1726 | +761 | −1955 | −1.13 | 22.1 | 349 | −107 | −9031 | −3153 | +1813 | −621 | −5.37 | 43.9 |
| EARLY-BOOST | 1714 | −338 | −2719 | −1.59 | 22.1 | 283 | −92 | −7828 | −2752 | +1049 | −1386 | −1.43 | 32.7 |
| LATE-BOOST | 1987 | +2173 | −362 | −0.18 | 22.1 | 335 | −97 | −5664 | −3022 | +3406 | +971 | 1.40 | 65.2 |
| RECENCY-DOWN | 774 | −1014 | −2135 | −2.76 | 22.1 | 128 | −46 | −4647 | −1722 | +1633 | −801 | 1.21 | 33.4 |
| RECENCY-UP | 1987 | +2866 | **+362** | +0.18 | 22.1 | 328 | −91 | −5497 | −1722 | +4130 | +1696 | 0.93 | 75.7 |

`boot +%` = share of 2,000 **day-block bootstrap** resamples (35 trading days drawn with replacement) in which the cell still beats `MINCON-FLAT`. Days, not trades, are the resampling unit — the five arms trade **one shared signal at r=0.846 / 95.7% sign agreement**, so trades inside a day are not independent draws.

### Reading the matrix in four lines

1. **Every "winning" cell wins by de-levering.** `FLAT-1` (303 contracts) improves on production by $3,408. So would trading nothing at all, by $3,768. **On a losing book, shrinking is arithmetic, not information** — and the limit case beats every cell in this table.
2. **`$/ctr` is where the real comparison lives.** Production sits at **−$2.51/contract**; `MINCON-FLAT` at **−$1.05**; every flat cell between −$0.46 and −$1.45. Production's shape is roughly **2.4× worse per contract than simply not deviating from `min_contracts`.**
3. **Sizing UP always widens the risk metrics faster than the P&L.** `EQUITY-30%` takes max DD to −$20,000 and a worst day of −$11,354 on ~$5K accounts — a Rule 5 kill-switch breach many times over. `EQUITY-50%` is worse on every axis *including* net.
4. **Top-day share ≥ 1.0 on almost every cell that beats `MINCON-FLAT`.** `FLAT-8` "gains" $9 with a single day worth $3,395 (372× the total). Those are noise cells wearing a positive sign.

---

## ✅ WHAT SURVIVES

Exactly one cell clears both the concentration test and the day bootstrap: **`MINCON-FLAT`**.

| | PRODUCTION | MINCON-FLAT | delta |
|---|---:|---:|---:|
| contracts | 1,500 | 1,270 | −230 |
| gross | −$1,804 | **+$397** | +$2,201 |
| fees | $135 | $117 | −$18 |
| exit slippage | $1,829 | $1,614 | −$215 |
| **net after costs** | **−$3,768** | **−$1,334** | **+$2,434** |
| net per contract | −$2.51 | −$1.05 | +$1.46 |
| win rate | 22.11% | 22.11% | **0.00** |
| avg win / avg loss | $224 / −$80 | $211 / −$65 | payoff ratio 2.81 → 3.22 |
| **max drawdown** | **−$6,135** | **−$4,458** | +$1,677 |
| **worst single day** | **−$2,774** | **−$1,722** | +$1,052 |
| max contracts, single trade | 12 | 5 | — |
| max notional % of equity | 46.2% | 46.2% | Rule 6 respected in both |

Concentration and robustness, **as measured** vs **forward-available** (dead 2026-08-13/14 config removed):

| | as measured | **forward-available** |
|---|---:|---:|
| gross delta | +$2,201 | **+$1,369** |
| net-of-fees delta | — | +$1,386 |
| **net-after-costs delta** | **+$2,434** | **+$1,575** |
| top-day share | 0.43 (2026-08-07) | **0.67 (2026-08-07, $1,052)** |
| **top-2-day share** | — | **1.04 (08-07 + 08-05)** |
| top-trade share | 0.13 | 0.20 (safe-3 08-07 qty 8) |
| days better / worse | 11 / 4 | 10 / 4 |
| **days on which anything changes** | 15 | **14 of 35** |
| bootstrap % positive | 96.7% | **92.2%** |
| bootstrap 5th percentile | **+$230** | **−$201** |

> ### 🚨 The one line that decides it
> **No cell beats production by more than its own concentration can explain.** The best cell's forward-available effect is +$1,575, and **two days — 2026-08-05 and 2026-08-07 — are worth $1,642 of it, i.e. 104%.** Remove those two days and the remaining 33 days are net *negative*. The bootstrap agrees: the 5th percentile of the forward-available effect is **−$201**, below zero.

**Verdict: WEAK.** Not NO EDGE — the direction is unanimous (all 5 arms, both cost treatments, every flat reference cell, 10 of 14 affected days) and one component carries a met pre-registered kill. Not STRONG — two days carry the whole thing and the bootstrap floor is negative.

---

## ❌ WHAT DOES NOT SURVIVE — and why each one is dead

| cell | looked like | why it's dead |
|---|---|---|
| **RECENCY-UP** (+$362, the only positive-net cell) | the winner | **C31's martingale** — double after a red day. 93% of its edge is **2026-08-13 alone** ($1,569 of $1,696). Day bootstrap only 75.7% positive. Doubling into a losing streak is refused on Rule 5/6 grounds regardless of the number. |
| **LATE-BOOST** (+$971 vs MINCON) | a clean clock tilt | top-day share **1.40** — 2026-08-04 alone exceeds the entire effect; 21 of 33 affected days are negative. Bootstrap 65.2%. |
| **CHEAP-BOOST** (+$484) | vindication of the live boost | **contradicted by the live arm.** Book-wide the cheap tilt looks positive; on risky-3, where it is actually armed, it has **lost $371** over 20 fills. Cell and reality disagree → the cell is the artifact. |
| **CONV-SCORE** (+$472) | conviction pays | requires score ≥ 10 to double, but 175 of 303 rows are score ≥ 10 — so it is mostly a 1.4× leverage cell. Its `$/ctr` (−$0.47) is no better than plain `FLAT-10` (−$0.46). Bootstrap 53.2%. |
| **EQUITY-*** family | the obvious "scale with the account" answer | monotonically **worse** past 10%: −$1,067 → −$2,654 → −$5,122 → −$8,483, with max DD −$5.1K → −$27.2K. Also structurally confounded: all five arms were re-funded from ~$1.4–2.2K to **$5,000 on 2026-08-03/04**, so any equity-scaled cell mechanically levers up the second half of the sample. That is a capital-injection artifact, not a sizing edge. |
| **VOL-INV-VIX / VOL-DIR-VIX** | volatility targeting | both *negative* vs MINCON (−$94, −$276). VIX carried no per-contract signal: `<16` → −$0.08/ctr, `16–20` → −$2.47/ctr, and nothing above 20 in the whole sample. |
| **CONV-TIER** (+$83) | quality tiers pay | top-day share **−10.98**; `SUPER` (the highest tier) is the **worst** bucket at −$25.75/contract on n=9. The tier labels do not order the money. |
| **RECENCY-DOWN** (−$801) | the prudent one | **the worst shape in the matrix at −$2.76/contract.** This is directionally the live recency clamp, and it sizes *down* into the trades that pay. Flagged, not concluded — see the confound note below. |

---

## 🔧 THE THREE LIVE SIZING KNOBS, AUDITED

### 1. `cheap_contract_qty_boost` — risky-3, LIVE — **its own kill bar is MET**

Armed 2026-08-03 (`966c48f1`) in `automation/state/fleet/accounts.json`. Its pre-registered kill, verbatim from the config: *"n>=10 boosted fills or 10 sessions, net<0 -> delete these two keys (one-line revert, byte-identical)."*

| bar | required | measured | met? |
|---|---|---:|---|
| boosted fills | ≥ 10 | **20** | ✅ |
| sessions | ≥ 10 | **10** | ✅ |
| net — as traded | < 0 | **−$675** | ✅ |
| net — marginal vs qty 5 | < 0 | **−$371** | ✅ |
| sessions negative | — | **8 of 10** | — |

**KILL BAR TRIGGERED on every reading.** Honest caveat: the marginal −$371 is itself concentrated — 2026-08-07 is 68% of it, and the day bootstrap is only 84.8% positive with a 5th percentile of −$192. **But a pre-registered kill does not need fresh significance; it needs its stated bar met, and this one is met four ways out of four.** This is the single cleanest action in the lane.

### 2. `position_sizing_tiers` ladder — fleet arms, LIVE — direction is bad, mechanism is confounded

Per-contract net-after-costs, split by whether the ladder passed through or the recency clamp cut size to `min_contracts` (equity in the $2K–$10K tier):

| arm | tier base qty | ladder passed | $/ctr | clamped to min | $/ctr |
|---|---:|---:|---:|---:|---:|
| safe-3 | 5 | n=5 | **−$34.44** | n=19 | +$20.47 |
| risky-1 | 8 | n=2 | **−$21.50** | n=46 | +$2.84 |
| risky-3 | 8 | n=43 | **−$3.68** | n=9 | +$11.47 |

Same sign on all three arms. **But this is NOT a clean size A/B and must not be sold as one:** the clamp fires on RED recency days and the ladder-passed population skews to expensive `VWAP_CONTINUATION` entries, so **day-regime, setup and premium are all confounded with size**. Two of the three arms have n≤5 on the passed side. Direction only — which is exactly what a pre-registered forward test is for.

### 3. `min_contracts_equity_scaled` — **already dead, do not count it**

Shipped 2026-08-13 (`7f354c19`), reverted 2026-08-14 (`636c5ba4`); both params files read `false` today. It was live for one day, upsized 4 rows across four arms on the same 2026-08-14 signal, and cost **−$837**. Already banked as a lesson. Excluded from every forward-available number above.

---

## 🧪 WHERE THE PER-CONTRACT MONEY ACTUALLY IS

Net-after-costs **per contract**, bucketed by information available at entry. This is the whole basis on which any sizing rule could work — and it is why almost nothing does.

| bucket | n | mean $/ctr | median $/ctr |
|---|---:|---:|---:|
| score ≥ 10 | 175 | −0.35 | −6.90 |
| score 8–9 | 74 | **+1.16** | −10.11 |
| score < 8 | 54 | −7.06 | −3.49 |
| tier ELITE | 161 | +2.39 | −4.61 |
| tier BASE | 71 | −3.16 | −8.86 |
| tier SUPER | 9 | **−25.75** | −16.25 |
| VIX < 16 | 164 | −0.08 | −6.88 |
| VIX 16–20 | 139 | −2.47 | −7.74 |
| premium < $0.50 | 98 | **+1.22** | −2.35 |
| premium $0.50–0.99 | 93 | −3.22 | −8.87 |
| premium ≥ $1.00 | 112 | −1.58 | −15.90 |
| first 60 min | 118 | −3.89 | −11.56 |
| after 60 min | 185 | **+0.55** | −3.61 |

**Every median is negative and every positive mean is a right-tail artifact.** The mean/median gap is the whole story of this book: money arrives in a tail, and *no at-entry variable in the matrix locates that tail reliably enough to bet size on it.* `score 8–9` has the best mean and the **worst** median. `SUPER` — the label that literally means highest conviction — has the worst mean of any tier.

---

## 📌 PRE-REGISTERED HYPOTHESIS — frozen before any change

> **H-SIZE-1 (2026-08-19).** Production's *deviations above* `min_contracts` — the fleet
> `position_sizing_tiers` ladder and risky-3's `cheap_contract_qty_boost` — carry **negative**
> marginal net-after-costs. Flattening every arm to its own `min_contracts` improves the book.

**Measured on history (forward-available, dead config excluded):** gross **+$1,369**, net-of-fees **+$1,386**, net-after-costs **+$1,575**; max DD −$6,135 → −$4,458; worst day −$2,774 → −$1,722; win rate unchanged at 22.11%. Concentration: top day 0.67, **top two days 1.04**, top trade 0.20, 14 of 35 days affected. Day bootstrap 92.2% positive, 5th percentile **−$201**.

**Two-stage proposal — stage 1 is the only one that should move now.**

| stage | action | why now | revert |
|---|---|---|---|
| **1** | Execute the **already-met, already-pre-registered kill** on risky-3's `cheap_contract_qty_boost` (delete the two keys — the config itself documents this as a one-line, byte-identical revert). | Its bar was written before the data and is met four ways out of four. This needs no new statistics. | restore the two keys |
| **2** | **Shadow-only** clock on `MINCON-FLAT` for the fleet arms: log what qty the ladder proposes vs `min_contracts` on every fill, price both, and accumulate. **Do not clamp live.** | +$1,575 with two days carrying 104% of it is not enough to change armed sizing. The ladder/clamp comparison is confounded by day-regime, setup and premium. | n/a — shadow writes nothing |

### 🛑 KILL CRITERIA (frozen)

- **Kills stage 1's premise (un-kill the boost):** over the next ≥ 10 risky-3 boosted fills, the boost's marginal net-after-costs vs qty 5 is **positive** AND positive in ≥ 6 of ≥ 10 sessions.
- **Kills stage 2 / H-SIZE-1 outright:** after **≥ 20 additional fleet fills on ≥ 15 fresh trading days**, the shadow `MINCON-FLAT` delta is **≤ $0**, OR its top-2-day share stays **≥ 0.80**, OR the day-block bootstrap 5th percentile remains **< $0**. Any one of the three → H-SIZE-1 is dead, the ladder stands, and this document is closed NO-SHIP.
- **Promotes stage 2 to a live proposal:** delta **> $0** with **top-2-day share < 0.50** and **bootstrap 5th percentile > $0** on the fresh window — evaluated on the fresh window alone, never pooled with the 35 days above.
- **Immediate abort on either stage:** any Rule 5 kill-switch breach or Rule 6 clamp-to-zero attributable to the change.

---

## 🔬 METHOD, ASSUMPTIONS, AND THE ARTIFACT HUNT

**Reconciliation.** The production cell re-priced from scratch reproduces the ledger: gross −$1,803.66 vs −$1,805.00 (**$1.34**, one ledger row rounding −36.99 → −37.00) and fees $135.39 vs $134.90 (**$0.49**, model charges OCC/ORF once per side, ledger charges per execution). The same formula prices every cell, so both cancel out of every delta. Exit-leg P&L reconstructs to the cent on **303/303** rows.

**Costs are recomputed at every size, never scaled.** Fees from `cost_model.py`'s empirical rates; exit slippage at 0.129 × exit-minute traded range × contracts × 100. **389 of 390 exit legs** have their exit-minute bar; the one that does not is reported, never imputed. Slippage is the dominant cost — $1,829 vs $135 of fees at production size — and it scales linearly with contracts, which is why the sizing-up cells are punished so hard.

**No look-ahead (C6).** Every sizing input is known at the entry timestamp: equity, VIX, bull/bear score, quality tier, entry premium, minutes-since-open, and prior-day realized P&L. `VOL-*` uses an **expanding** median of VIX over prior trades only, with an 18.0 fallback until n≥10. Nothing reads the outcome, the future high, or the exit.

**Equity is path-simulated, and the re-funding is handled explicitly.** `equity_cf = equity_actual + (cum_cf_net − cum_prod_net)` since the last capital injection. All five arms were re-funded to exactly **$5,000 on 2026-08-03/04** (safe-2 $1,146→$5,000, risky-1 $1,339→$5,000, safe-3 $1,893→$5,000, risky-3 $2,202→$5,000, bold-2 $1,493→$5,000). That is exogenous capital, so the counterfactual delta resets to zero there — otherwise an equity-scaled cell would inherit money it was never given.

**Rule 6 enforced in every cell**, and it turns out to matter more than expected: the cap acts as an implicit expensive-premium filter. At `FLAT-10` it clamps 59 trades and lifts gross/contract from $0.231 (unclamped) to $0.842. **Any credit `FLAT-8`/`FLAT-10`/`EQUITY-*` appear to earn is substantially the Rule 6 cap doing the work, not the sizing rule.** `EQUITY-50%` clamps 125 times and skips 10 trades entirely (qty would round to 0).

### Artifacts hunted and their measured size

| suspected artifact | test | result |
|---|---|---|
| Exit-leg re-allocation (largest remainder) distorts the TP1/runner split at small qty | gross/contract across flat sizes 1→20, split single-leg vs multi-leg | **Single-leg is exactly invariant** (−$12.956/ctr at every size). Multi-leg moves only $37.21–$38.66. Artifact ≤ ~$1.5/contract at qty 1–2, ~$0 from qty 3 up. **Not the driver.** 78 rows drop a leg at `FLAT-1`, 1 row at `FLAT-5`, 0 from `FLAT-8` up. |
| Over-sized rows are really **adds** (C31's real killer), not bigger single orders | `n_entry_legs` on the 52 over-base rows | **49 of 52 are single-leg entries.** These are genuinely larger orders, not averaging in. |
| Production's advantage-losing shape is a bug in the counterfactual | per-arm production vs base-flat at matched contract counts | Cost of deviation is **negative on all 5 arms**: safe-3 −$925, risky-3 −$846, risky-1 −$311, bold-2 −$224, safe-2 −$131. Consistent, not a single-arm artifact. |
| The best cell is just leverage | permutation null — shuffle the rule's own multipliers within each arm, 1,000 trials | `RECENCY-UP` 0.1%, `LATE-BOOST` 0.7%, `EQUITY-10%` 23.3% of random reweightings do as well. **But this null shuffles multipliers across days, which a day-level rule would never do — it is too weak for `RECENCY-UP`/`LATE-BOOST`.** The day-block bootstrap is the governing test, and it disagrees (75.7% / 65.2%). Where two instruments disagree, the one that respects the correlation structure wins. |
| The effect is a capital-regime break | pre- vs post-refund per-contract split, and equity-cell monotonicity | Confirmed as a confound for the whole `EQUITY-*` family; disclosed rather than adjusted away. |

### Honest limits

- **The 5 arms are not 5 samples.** r=0.846, 95.7% sign agreement. 303 rows ≈ **151 distinct signal-level decisions**, and for a *day-level* effect the binding number is **35 trading days** — of which only **14** are touched by the best cell.
- **Linear-fill assumption.** Resizing assumes the same fill prices. Fine at 1–12 contracts on SPY 0DTE; the `EQUITY-20/30/50%` cells reach the 60-contract sanity ceiling (8/15/49 times) and their fills would **not** be linear in reality. Those cells lose on every axis anyway, so the assumption never carries a conclusion.
- **The ladder-vs-clamp comparison is confounded** by day regime, setup mix and premium. It shows a direction, not a mechanism.
- **`RECENCY-DOWN` scoring worst in the matrix is suggestive but not a verdict on the live recency clamp** — the modelled rule (half `min_contracts` after a red day) is not the live one (clamp the *ladder* to `min_contracts` on a RED recency verdict, ribbon_ride scope only). Flagged for a dedicated test, not concluded here.
- **Nothing here makes the book profitable.** `MINCON-FLAT` turns a −$3,768 book into a −$1,334 book. It is a smaller loss, and the win rate does not move at all.

---

## ▶ Reproduce

```bash
backtest/.venv/Scripts/python.exe setup/scripts/sizing_matrix_2026_08_19.py
```

Machine-readable: `analysis/recommendations/sizing-matrix-2026-08-19.json` — every cell, per-day
delta series, live-knob audits, permutation nulls, bootstraps, and the per-contract bucket table.

Related: [`LOSER-SEPARABILITY-2026-08-19.md`](LOSER-SEPARABILITY-2026-08-19.md) (the lever is not
fewer losers) · [`COST-REALISM-2026-08-18.md`](COST-REALISM-2026-08-18.md) (where the fee and
slippage rates come from) · [`LIVE-READINESS-FIRST-READING-2026-08-18.md`](LIVE-READINESS-FIRST-READING-2026-08-18.md)
(the breakeven-margin framing).
