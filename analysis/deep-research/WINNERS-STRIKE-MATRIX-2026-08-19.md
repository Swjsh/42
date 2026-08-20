# WINNERS — STRIKE MATRIX (full ladder, every trade ever taken)

**Lane:** BIGGER WINNERS · **Lever:** strike selection · **Date:** 2026-08-19 (ET) · **Scope:** ANALYSIS ONLY — nothing armed, no params touched, no orders.

**Dataset:** `analysis/recommendations/trade-matrix.json` (303 closed round trips, 35 trading days, 5 arms).
**Cells:** `WINNERS-STRIKE-MATRIX-2026-08-19-cells.json` (per-trade, per-rung) · **Aggregates:** `WINNERS-STRIKE-MATRIX-2026-08-19.json`

---

## VERDICT

> **J's observation is real and it generalises — and it is still not a lever.**
>
> ✅ **Dollars DO fall monotonically as you go OTM, on every winner, on every winning day.** 18/18 winning days, 83.8% of individual winners monotonic. ITM-2 pays **$90.75/contract**, OTM+2 pays **$33.96/contract**. 2026-08-19 was not a one-day fluke.
>
> ❌ **At a fixed contract count that is not an edge, it is 3.23× the capital.** ITM-2 buys $359,592 of premium where production bought $111,438. Its +$2,697 gross advantage is **100.1% one day** (2026-07-17); leave that day out and the effect is **−$4**.
>
> ❌ **At a fixed RISK budget — the comparison that actually matters — the gross ranking is NOISE.** Across all five rungs the gross delta spans −$107 to +$681 on 292 trades. Cluster bootstrap on ITM-2: 95% CI **[−$3,440, +$4,705]**, P(>0) = 64%. **No strike has a gross edge.** The right tail pays the same dollars at fixed capital wherever you put the strike.
>
> ⚠️ **The only non-noise strike effect is FRICTION, and it runs ITM.** Fixed budget spans **410 contracts (ITM-2) to 2,866 (OTM+2)** — a 7× spread. Worth **+$1,709 net** for ITM-2 (LODO min +$451, sign-stable, 24/35 days positive). But **$681 of that is gross noise**; only **$1,028 is deterministic** = **$29/day book-wide ≈ $6/day/arm**.
>
> 🚨 **And the winning cell is not implementable.** ITM-2 at production's own budget buys **1 contract on 221 of 292 rows** and fewer than 3 on **91.1%** — a straight Rule 6 breach (min 3: 2 TP + 1 runner). A Rule-6-legal ITM-2 3-lot costs a median **$730** against production's median **$315** deployed. Making it legal means **+$115,621 more premium at risk** — that is a *sizing* change wearing a *strike* label.
>
> **Answer to the one-line test — does any cell beat production by more than its own concentration can explain?**
> **ITM-2 at fixed budget survives concentration (top day 73.6%, effect still +$451 without it) but not significance (P(>0) = 79.1%) and not Rule 6 (91% sub-minimum). Nothing else clears anything. VERDICT: WEAK.**
>
> 🎯 **The one usable finding is the opposite end of the ladder:** OTM+2 is *confidently worse* — LODO max **−$783** (never positive under any single-day removal), bootstrap P(>0) = **22.1%**. 117 rows (40% of the book) currently sit at OTM+2 or wider.

---

## 1. Method — pre-registered, and its own error measured

Every convention was frozen before any counterfactual result was inspected. Full text is embedded in `WINNERS-STRIKE-MATRIX-2026-08-19-cells.json#conventions`.

| Item | Rule |
|---|---|
| **Ladder** | ITM-2 / ITM-1 / ATM / OTM+1 / OTM+2, defined against `round(spy_at_entry)` on the $1 SPY strike grid — the same definition `trade_matrix_build.moneyness_label` uses. |
| **Bars** | Real OPRA 1-minute bars, Alpaca `/v1beta1/options/bars`, cached to `backtest/data/opra_1m_cache/`. 209 new contract-days fetched, **0 empty**. |
| **Pricing** | Entry *and* exit take the acting minute's **bar OPEN**. Chosen by calibration against real fills, not by preference (see below). |
| **Exit E1** | **Production's actual exit schedule replayed** — each leg's minute and each leg's share of the position, applied to every alternate strike. TP1-plus-runner scale-outs are honoured, not collapsed. |
| **Exit E2** | Policy replay: −50% catastrophe cap vs the bar LOW, +100% TP1 vs the bar HIGH, **stop tested first inside a bar**, scanning from the bar *after* entry; else sell at production's exit minute. |
| **Sizing S1** | Fixed contract count = the qty production actually traded. |
| **Sizing S2** | Fixed premium budget = the dollars production actually deployed. `pct_of_equity` is premium-space, so **fixed-risk ≡ fixed-premium** here; there is no third axis hiding between them. |
| **Costs** | `cost_model.fee_breakdown` (OCC+ORF+TAF+SEC) + per-contract exit slippage, reported across a sensitivity ladder rather than at one assumed value. |
| **Row set** | A row counts only if **all six cells** (5 rungs + as-traded) price. **292 of 303 kept, 11 dropped**, all listed in the cells JSON. Identical row set in every cell — no cell-composition bias. |
| **Look-ahead (C6)** | Every price used is at or before the minute it is used in. Exit minutes are an input identical across all cells; no cell can see a bar another cannot. |

### Why bar OPEN

Measured against the real ledger, not assumed:

| Field | vs 301 real ENTRY fills | vs 224 real single-leg EXIT fills |
|---|---|---|
| open | **−0.0058** (\|mean\| 0.0308) | **+0.0042** (\|mean\| 0.0237) |
| close | −0.0076 (\|mean\| 0.0416) | +0.0038 (\|mean\| 0.0460) |
| high | +0.0432 | +0.0488 |
| low | −0.0565 | −0.0422 |

Real entry fills land at **0.620** of the minute's traded range (we pay up, as a buyer must); real exits at **0.433**. Round-trip, bar-OPEN pricing is optimistic by ≈ **$0.010/contract**. That is a *measurement of this study's own convention*, so removing it is a correction, not an assumption — and it is the central case used throughout. The repo's conservative constant (`EXIT_SLIPPAGE_CONSERVATIVE_PER_CONTRACT = $0.02`) is shown as the upper bound.

### Sim-accuracy gate

| Subset | n | real gross | sim as-traded | error | mean abs err | corr |
|---|---|---|---|---|---|---|
| all | 292 | −$1,078 | +$315 | **+$1,393** | $18.4 | **0.987** |
| single-leg exits | 215 | −$13,987 | −$12,994 | +$993 | $18.6 | 0.953 |
| multi-leg exits | 77 | +$12,909 | +$13,309 | +$400 | $17.7 | 0.994 |

Sign agreement 269/292 = **92.1%**. Residual error is **+$4.8/trade**, which is exactly the measured bar-vs-fill optimism above — structural, disclosed, and identical in every cell so it cancels in the deltas.

> **v1 of this study got this wrong and it inverted the answer.** Selling one block at the final exit timestamp overstated the as-traded replay by **$2,930**, and the overstatement landed hardest on the ITM cells (bigger dollar moves). Fixing the leg replay cut the error to $1,393. **Any strike study that collapses TP1-plus-runner into a single sell will manufacture an ITM edge.**

### Internal validation

`safe-2` traded **100% ATM** across all 70 of its priced rows. Its ATM cell reproduces its as-traded cell to the cent — **$−181.00 vs $−181.00, 0 symbol mismatches.** The ladder is wired correctly.

---

## 2. Q1 — does dollar-falls-as-you-go-OTM hold across ALL winners?

**Yes. Unambiguously.** 68 winners, 39 independent signal clusters, 18 days. Exit = production's own schedule replayed.

| Rung | mean $/contract | median $/contract | mean % | median % | mean entry premium | win rate |
|---|---|---|---|---|---|---|
| **ITM-2** | **$90.75** | $87.90 | 35.9% | 37.1% | $2.49 | 94.1% |
| **ITM-1** | $80.85 | $80.67 | 45.6% | 50.9% | $1.74 | 92.6% |
| **ATM** | $66.37 | $63.67 | 58.4% | 63.8% | $1.16 | 91.2% |
| **OTM+1** | $49.53 | $42.20 | 71.2% | 78.6% | $0.74 | 89.7% |
| **OTM+2** | $33.96 | $24.50 | **75.1%** | **83.9%** | $0.48 | 83.8% |

- **Dollars fall, percent rises** — perfectly monotone in the means, both directions.
- **83.8%** of individual winners (57/68) are monotone in dollars; 51.5% in percent.
- **18/18 winning days** have ITM-2 richer in dollars than OTM+2 (range +$3.67 to +$111.16 per contract).

2026-08-19 was representative, not exceptional: it shows +$45.10/contract, below the 18-day mean of +$62.
The brief's live anchor (ITM-1 +$0.97 vs OTM+2 +$0.42 per contract) is reproduced independently here, on a rule-based exit rather than the peak.

⚠️ **This table cannot be used for a P&L claim.** The winners subset is conditioned on production having won *at its own strike*, which is not knowable at entry. Scored on all 292 rows the same cells collapse to **$4.97 / $4.10 / $3.01 / $2.11 / $1.22** per contract — a 15–28× drop. The shape is real; the magnitude is selection.

---

## 3. Q2 — the full matrix (all 292 priced round trips)

Production's live core (`safe-2`) runs **ATM**; the book's realised mix is `AS_TRADED`. Both are marked.

### 3a. Fixed contract count · production's exit schedule replayed

| cell | ctrs | gross | net (fees) | net (fees+$0.02) | WR | avg win | avg loss | max DD | days + | Δ gross | top-day share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **AS_TRADED ← PROD** | 1,442 | $315 | $185 | −$2,699 | 27.1% | $203.7 | −$82.2 | −$3,992 | 12/35 | — | — |
| ITM-2 | 1,442 | $3,012 | $2,877 | −$7 | 32.5% | $323.9 | −$146.1 | −$5,171 | 13/35 | **+$2,697** | **1.00** 🚨 |
| ITM-1 | 1,442 | $2,184 | $2,052 | −$832 | 30.1% | $306.9 | −$127.3 | −$4,511 | 13/35 | +$1,869 | 1.25 🚨 |
| ATM | 1,442 | $1,177 | $1,047 | −$1,837 | 27.7% | $269.5 | −$103.3 | −$4,383 | 12/35 | +$862 | 2.02 🚨 |
| OTM+1 | 1,442 | $854 | $724 | −$2,160 | 26.7% | $207.5 | −$78.2 | −$3,606 | 12/35 | +$539 | 1.88 🚨 |
| OTM+2 | 1,442 | $326 | $197 | −$2,687 | 24.7% | $153.1 | −$54.6 | −$2,928 | 11/35 | +$11 | 107 🚨 |

**Every cell in this block fails concentration.** Top-day share ≥ 1.00 means a single day carries the entire effect. And the block is not risk-comparable anyway — see 3c.

### 3b. Fixed premium budget · production's exit schedule replayed — **the comparison that matters**

| cell | ctrs | gross | net (fees) | net (fees+$0.02) | WR | avg win | avg loss | max DD | days + | Δ gross | Δ net (measured $0.010) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **AS_TRADED ← PROD** | 1,361 | $713 | $592 | −$2,130 | 27.1% | $189.2 | −$74.1 | −$3,830 | 12/35 | — | — |
| **ITM-2** | **410** | $1,394 | $1,350 | **+$530** | 32.5% | $100.3 | −$42.8 | **−$1,607** | 12/35 | +$681 | **+$1,709** |
| ITM-1 | 551 | $1,054 | $999 | −$103 | 30.1% | $127.2 | −$52.0 | −$2,246 | 11/35 | +$341 | +$1,218 |
| ATM | 874 | $733 | $651 | −$1,097 | 27.7% | $172.3 | −$66.1 | −$3,665 | 11/35 | +$20 | +$547 |
| OTM+1 | 1,518 | $672 | $537 | −$2,499 | 26.7% | $215.4 | −$82.3 | −$4,458 | 11/35 | −$41 | −$211 |
| OTM+2 | **2,866** | $606 | $359 | **−$5,373** | 24.7% | $271.4 | −$97.1 | **−$6,171** | 10/35 | −$107 | **−$1,737** |

**Read the gross column.** $606 → $1,394 across a 7× swing in contract count and a 5-strike spread. On 292 trades that is nothing. **The ladder does not change how many dollars the right tail pays at fixed capital — it only changes how many contracts you must buy and therefore how much friction you pay.**

Note the *drawdown* column, which is not noise: ITM-2 −$1,607 vs OTM+2 −$6,171. Same capital, 3.8× the drawdown at the OTM end.

### 3c. The leverage illusion — why block 3a is not a comparison

| cell | premium deployed @ fixed contracts | × production | premium deployed @ fixed budget |
|---|---|---|---|
| PROD | $111,438 | 1.00 | $102,495 |
| ITM-2 | **$359,592** | **3.23×** | $104,873 |
| ITM-1 | $253,405 | 2.27× | $100,547 |
| ATM | $167,692 | 1.50× | $102,425 |
| OTM+1 | $106,277 | 0.95× | $102,436 |
| OTM+2 | $66,983 | 0.60× | $105,517 |

At fixed contracts "ITM-2 wins" reduces to *"spending 3.23× more money makes 3.23× bigger numbers."* J's framing of the question — fixed risk budget, not fixed contract count — is exactly the correction that dissolves it.

### 3d. Policy-replay exit (−50% / +100%), fixed contracts — robustness on the exit clock

| cell | gross | net (fees) | net (fees+$0.02) | WR |
|---|---|---|---|---|
| AS_TRADED | $690 | $560 | −$2,324 | 28.4% |
| ITM-2 | $4,532 | $4,397 | +$1,513 | 32.5% |
| ITM-1 | $4,506 | $4,374 | +$1,490 | 30.5% |
| ATM | $2,532 | $2,402 | −$482 | 28.1% |
| OTM+1 | $1,308 | $1,178 | −$1,706 | 27.4% |
| OTM+2 | $799 | $670 | −$2,214 | 26.4% |

The rung ordering is identical under a mechanical policy exit, so it is **not** an artefact of inheriting production's exit clock. (ITM-2 and ITM-1 converge here — a fixed −50% cap is further outside the noise band on a $2.49 premium than on a $0.48 one, which is the same effect the stops lane is measuring from the other side.) Same leverage caveat as 3a applies: this block is still 3.23× the capital.

---

## 4. Where the fixed-budget advantage actually comes from

| cell | Δ gross | Δ fees | Δ spread @ $0.010 | **Δ net (measured)** | Δ net @ $0.020 | contracts |
|---|---|---|---|---|---|---|
| ITM-2 | +$681 | +$77 | +$951 | **+$1,709** | +$2,660 | 410 |
| ITM-1 | +$341 | +$67 | +$810 | +$1,218 | +$2,028 | 551 |
| ATM | +$20 | +$40 | +$487 | +$547 | +$1,034 | 874 |
| OTM+1 | −$41 | −$13 | −$157 | −$211 | −$368 | 1,518 |
| OTM+2 | −$107 | −$125 | −$1,505 | −$1,737 | −$3,242 | 2,866 |

**$1,028 of ITM-2's $1,709 is deterministic** (fees + per-contract spread on 951 fewer contracts). **$681 is gross noise.** The reliable component is **$29/day book-wide ≈ $6/day/arm** — 3–6% of the $100–200/day/account target. Real, and immaterial.

### Slippage sensitivity (Δ net vs production, fixed budget)

| cell | $0.000 | $0.005 | **$0.010 (measured)** | **$0.020 (repo)** | $0.030 |
|---|---|---|---|---|---|
| ITM-2 | +$758 | +$1,234 | **+$1,709** | **+$2,660** | +$3,611 |
| ITM-1 | +$408 | +$813 | +$1,218 | +$2,028 | +$2,838 |
| ATM | +$60 | +$303 | +$547 | +$1,034 | +$1,521 |
| OTM+1 | −$54 | −$133 | −$211 | −$368 | −$525 |
| OTM+2 | −$232 | −$985 | −$1,737 | −$3,242 | −$4,747 |

At **zero** per-contract execution cost the entire ladder is inside ±$760 — i.e. **the strike lever is a friction lever or it is nothing.**

---

## 5. Concentration, LODO, and significance

### Leave-one-day-out (35 refits, one day dropped each)

| | fixed contracts, gross | | | fixed budget, net (measured) | | |
|---|---|---|---|---|---|---|
| cell | full | LODO min | sign-stable | full | LODO min | sign-stable |
| ITM-2 | +$2,697 | **−$4** | ❌ | +$1,709 | **+$451** | ✅ |
| ITM-1 | +$1,869 | −$463 | ❌ | +$1,218 | +$301 | ✅ |
| ATM | +$862 | −$882 | ❌ | +$547 | +$287 | ✅ |
| OTM+1 | +$539 | −$473 | ❌ | −$211 | −$890 | ❌ |
| OTM+2 | +$11 | −$1,168 | ❌ | **−$1,737** | max **−$783** | ✅ (negative) |

Every fixed-contract cell dies on **2026-07-17**. Every fixed-budget ITM cell survives every single-day removal.

### Concentration of the fixed-budget net effect

| cell | total | largest **positive** day | share | largest positive trade | share | days + |
|---|---|---|---|---|---|---|
| ITM-2 | +$1,709 | $1,258 | **73.6%** | $294 (2026-08-05 risky-3) | 17.2% | 24/35 |
| ITM-1 | +$1,218 | $917 | 75.3% | $195 | 16.0% | 22/35 |
| ATM | +$547 | $260 | **47.5%** | $104 | 19.1% | 19/35 |

The single *largest* day for ITM-2 is **−$1,670 (2026-08-04) — it works against the cell.** Removing it grows the effect to $4,330. That is the opposite of concentration risk, and it is what a friction effect should look like: broad, small, everywhere.

### Cluster bootstrap (143 independent signal clusters, 4,000 draws)

The 5 arms trade one shared signal at r = 0.846 / 95.7% sign agreement. **The cluster, not the row, is the unit.** 292 rows → **143 clusters** (68 winners → 39 clusters).

| cell | metric | point | 2.5% | 97.5% | P(>0) |
|---|---|---|---|---|---|
| ITM-2 | S2 gross Δ | +$681 | −$3,440 | +$4,705 | 64.1% |
| ITM-2 | S2 net Δ (measured) | +$1,709 | −$2,667 | +$5,741 | **79.1%** |
| ITM-2 | S1 gross Δ | +$2,697 | −$5,823 | +$11,491 | 71.9% |
| ATM | S2 net Δ | +$547 | −$538 | +$1,630 | 84.1% |
| OTM+1 | S2 net Δ | −$211 | −$2,286 | +$2,027 | 41.9% |
| **OTM+2** | **S2 net Δ** | **−$1,737** | −$5,754 | +$2,843 | **22.1%** |

**Nothing clears.** The deterministic friction term is real but it is an order of magnitude smaller than the gross P&L noise it is embedded in.

---

## 6. The feasibility kill — Rule 6

Rule 6 requires a **minimum 3 contracts (2 TP + 1 runner)**. At production's own deployed premium:

| cell | median contracts | rows < 3 | share | rows = 1 | median 3-lot cost | × prod median deployed ($315) |
|---|---|---|---|---|---|---|
| AS_TRADED | 4.0 | 45 | 15.4% | 0 | $225 | 0.71× |
| **ITM-2** | **1.0** | **266** | **91.1%** | **221** | **$730** | **2.32×** |
| ITM-1 | 1.0 | 228 | 78.1% | 148 | $504 | 1.60× |
| ATM | 3.0 | 133 | 45.5% | 84 | $329 | 1.04× |
| OTM+1 | 5.0 | 85 | 29.1% | 63 | $195 | 0.62× |
| OTM+2 | 8.0 | 58 | 19.9% | 22 | $108 | 0.34× |

**The friction gradient and the feasibility gradient run in opposite directions.** ITM strikes are cheaper to *execute* and unaffordable to *structure*. On 91% of rows an ITM-2 3-lot costs more than production actually deployed on that trade.

Forcing the floor to 3 makes the ITM cells look spectacular — and the reason is written in the last column:

| cell | Δ gross @ 3-lot floor | Δ net (measured) | **extra premium deployed** |
|---|---|---|---|
| ITM-2 | +$3,599 | +$4,148 | **+$115,621** (+113%) |
| ITM-1 | +$2,457 | +$2,974 | +$56,290 |
| ATM | +$846 | +$1,187 | +$21,012 |
| OTM+1 | +$660 | +$379 | +$6,506 |
| OTM+2 | −$393 | −$2,061 | +$1,940 |

That is section 3c's leverage illusion returning in disguise. **Reporting +$4,148 as a strike finding would be a lie by omission** — it doubles capital at risk on a book that is already down.

---

## 7. Per-arm — where the ladder actually bites

Δ net (measured, fixed budget) from moving that arm's actual strike to each rung:

| arm | n | real gross | median moneyness | ITM-2 | ITM-1 | ATM | OTM+1 | OTM+2 |
|---|---|---|---|---|---|---|---|---|
| safe-2 | 70 | −$685 | ATM | +$102 | +$60 | — | −$448 | −$952 |
| bold-2 | 29 | −$402 | ATM | +$302 | +$43 | −$171 | −$184 | −$457 |
| risky-1 | 67 | +$422 | ATM | +$356 | +$126 | +$180 | +$233 | −$272 |
| **risky-3** | 77 | −$238 | **OTM+2** | **+$687** | **+$706** | **+$343** | +$203 | +$68 |
| **safe-3** | 49 | −$175 | **OTM+3** | +$262 | +$282 | +$194 | −$15 | −$124 |

The arms with something to gain are exactly the two that sit **far OTM**. The arms already at ATM gain almost nothing from going further ITM and lose materially from going further OTM. **safe-2's current ATM setting is already at or near the flat part of the curve — production is not the thing that is broken.**

### The clean sub-finding

Restricting to the **117 rows (40% of the book) currently at OTM+2 or wider** and clamping them, at the same premium budget:

| clamp to | Δ gross | Δ net (measured) | days + | top-day share |
|---|---|---|---|---|
| **ATM** | +$219 | **+$737** | 19/26 | **35.3%** ✅ |
| OTM+1 | +$107 | +$539 | 19/26 | 26.8% ✅ |

This is the only cell in the entire study that is **positive, broad (19/26 days), un-concentrated (top day 35%), Rule-6-feasible (median 5–8 contracts), and requires no extra capital.** It is worth ~$21/day book-wide. Small — but honest, and it is a *de-risking* move, not a bet.

---

## 8. PRE-REGISTERED HYPOTHESIS — H-STRIKE-1

> **Not a fix. A pre-registration.** Nothing here is armed. `params*.json` untouched.

**Claim.** For arms whose strike selection currently lands at **OTM+2 or wider** (`risky-3`, `safe-3` — 40% of book rows), **clamping strike selection to no further OTM than OTM+1** at the *same premium budget* raises net P&L. The mechanism is **friction, not direction**: the clamp cuts contract count ~2× and therefore cuts per-contract fees and half-spread, while the gross dollar outcome at fixed capital is statistically unchanged (5-rung gross spread −$107…+$681, all CIs straddling zero).

**Explicitly NOT claimed:** that ITM strikes beat ATM. That claim fails Rule 6 on 91% of rows and fails significance at P(>0)=79%.

**Expected effect size.** +$737 net over the 35-day window (26 of which carried a clamped row) = **+$21/day book-wide**, **+$28 per active day**, ~$10/day on `risky-3`. If the shadow shows materially more than this, suspect the artefact before believing the number.

**Kill criteria — any one fires, the hypothesis dies:**

1. **≥ 25 forward trading days and ≥ 40 clamped signals** logged, and cumulative net delta (after `cost_model` fees + $0.010/contract) **≤ $0**.
2. Fewer than **55%** of shadow days show a non-negative delta.
3. The **top single day carries > 50%** of a positive cumulative delta (this study's baseline is 35.3% — a shadow that concentrates worse is measuring something else).
4. Median contract count on clamped rows falls **below 3** (Rule 6 breach — the clamp must never create the ITM-2 problem it exists to avoid).
5. Realised entry premium on clamped rows lands **> 1.25×** the pre-clamp premium budget — that would mean the clamp is buying leverage, not saving friction.

**Falsifier in one sentence:** if per-contract execution cost is truly below **$0.005**, the whole hypothesis is worth < $400 over 35 days and should be dropped without further work — so **measure the realised half-spread first**, from `exit_fill_realism.py`, before spending a shadow window on it.

---

## 9. Limitations — stated, not buried

1. **The winners table (§2) is outcome-conditioned.** It answers "what shape does the ladder have on signals that paid" and nothing else. All P&L claims come from the 292-row full matrix.
2. **n is 143 clusters, not 292 trades, and not 303.** Every CI here uses the cluster.
3. **Bar-OPEN pricing is optimistic by ~$0.010/contract round trip** (measured). The convention is identical in every cell so it cancels in the *deltas*, but it inflates any *absolute* cell total in proportion to contract count. Absolute cell totals in §3 should not be quoted on their own.
4. **11 of 303 rows dropped** (one or more ladder rungs printed no OPRA trade in the entry minute), 10 of them on 2026-08-10/11. Listed individually in the cells JSON. Not imputed.
5. **4 of 1,752 cells** used a stale-minute substitution (latest bar at or before the acting minute; never after). Negligible, disclosed.
6. **E2's policy replay sells the whole block at target**, where production scales 0.8/0.667 at TP1. E2 is a *policy counterfactual*, not a production replay; E1 is the faithful one and carries every headline number.
7. **A chart-stop / delta-normalised sizing axis was NOT measured.** Production is chart-stop-primary, so a fixed *SPY-point* stop would size by delta, not by premium — ITM's higher delta would mean fewer contracts than S2 gives it. That axis needs implied greeks this dataset does not carry, and it could move the ITM cells in either direction. **Unmeasured, not assumed away.**
8. **Alternate-strike liquidity is assumed adequate.** OPRA printed in every entry minute for 292/303 rows, but a print is not a fillable size. ITM-2 quotes on 0DTE SPY are wider in *percentage* terms than ATM; the flat $/contract cost model does not capture that, and it biases *in favour of* the ITM cells.

---

## 10. What this lane concluded

| Question | Answer |
|---|---|
| Does the dollar-falls-OTM pattern hold across all winners? | **Yes — 18/18 days, 83.8% of winners. Not a one-day artefact.** |
| Is that a lever at fixed contracts? | **No — 3.23× the capital, and 100% of the effect is 2026-07-17.** |
| At a fixed risk budget, which strike maximises dollars? | **Gross: none, it is noise (−$107…+$681). Net: ITM-2, by friction only (+$1,709, of which $1,028 is deterministic).** |
| Does any cell beat production by more than its concentration can explain? | **ITM-2 passes concentration and fails significance (P=79%) and Rule 6 (91% sub-3-lot). Nothing else passes anything.** |
| What survives? | **The far-OTM tail is confidently worse. Clamping OTM+2-or-wider rows to ATM/OTM+1 is +$737 net, 19/26 days, top day 35%, no extra capital.** |
| What should be built next? | **Measure the realised per-contract half-spread. The entire strike lever is worth what that number says it is worth, and nothing more.** |

---

*Generated 2026-08-19 ET · scope: analysis only · nothing armed · no params edited · no orders placed.*
*Builders: `scratchpad/fetch_alt_strikes.py` → `strike_matrix2.py` → `strike_report.py` / `artifact_hunt.py` / `robustness.py`.*
