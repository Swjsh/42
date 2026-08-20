# LOSSES LANE — STOP LEVEL vs THE NOISE FLOOR

> **Full matrix over all 303 closed round trips** (5 arms, 35 trading days, 2026-06-26 → 2026-08-19).
> Engine: [`backtest/tools/stop_noise_matrix_2026_08_19.py`](../../backtest/tools/stop_noise_matrix_2026_08_19.py) ·
> raw cells: [`analysis/recommendations/losses-stop-level-matrix-2026-08-19.json`](../recommendations/losses-stop-level-matrix-2026-08-19.json) ·
> dataset: [`analysis/recommendations/trade-matrix.json`](../recommendations/trade-matrix.json)
> **ANALYSIS ONLY. Nothing armed, no params touched, no orders. $0 (cache-only).**

---

## 🎯 VERDICT — **NO EDGE on the stop-level axis**

- **The mechanism is real. The lever is not.** 104 of 302 trades (34%) run a hard stop *inside* one
  minute of their own contract's noise — but no stop setting, in any unit, produces a robust P&L
  improvement.
- **Tightening is definitively wrong** and this half needs no modelling at all: −8% costs
  **−$1,693**, −12% **−$1,481**, −15% **−$1,051** vs production. Every tighter cell loses money.
- **Widening looks spectacular and is a mirage.** The best raw cell (flat −20%) gains **+$1,558** —
  but **161% of that gain is one day, 2026-08-04**, the book's single best day (+$3,613 as traded,
  SPY +1.4%). Excluding it: **−$948**.
- **The single most robust cell** — a noise-normalised stop at a **0.050% adverse SPY move**,
  delta-scaled per contract — is worth **+$947 gross / +$573 after fees and exit slippage** over
  35 days, on a **16-improved / 15-worsened** day split with a median improving day of **+$9.12**.
  That is a coin flip worth $16/day. The book still loses **−$993 net / −$3,205 after full costs**.
- ⚠️ **The brief's premise needs one correction.** On 2026-08-19, four of five arms were cut by a
  **structure stop @ 770.85**, not a premium stop. And the premium stop that actually binds on 75%
  of the book is the **−50% catastrophe cap, which sits at 4.6× the noise band** — it is not the
  problem. The stops that sit inside the noise are the **−6% / −8% fixed stops on the satellite
  setups** (VWAP_CONTINUATION, vwap_reclaim_failed_break, vix_regime_dayside, bollinger_squeeze).

---

## 📏 THE NOISE FLOOR, MEASURED

Median 1-minute traded range of the contract, as a fraction of entry premium, over the held window.
A stop tighter than this fires on a single minute of ordinary print-to-print noise.

| | p10 | p25 | **median** | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| 1-min range ÷ entry premium (n=302) | 8.3% | 9.8% | **13.1%** | 16.7% | 23.5% |

| moneyness | n | median 1-min range ÷ premium |
|---|---:|---:|
| OTM+1 | 5 | 7.5% |
| ATM | 175 | **11.1%** |
| ITM-1 | 2 | 11.2% |
| OTM+2 | 38 | 14.7% |
| OTM+3 | 82 | **19.2%** |

Expressed in the underlying: one minute of this book's option noise is a **0.030% SPY move**
(p10 0.018%, p90 0.058%).

### Which production stops sit inside it

| production cohort | n | inside the noise band | median \|stop\| ÷ noise band |
|---|---:|---:|---:|
| `structure` mode, −50% catastrophe cap | 143 | **0 / 143** | **4.64×** |
| `premium` mode, −20% | 14 | 0 / 14 | 1.62× |
| −20% fallback (`stop_mode` unrecorded) | 71 | 35 / 71 | **1.00×** |
| `premium` mode, −8% | 22 | **21 / 22** | **0.60×** |
| −8% (unrecorded) | 7 | 7 / 7 | 0.50× |
| `premium` mode, −6% | 39 | **35 / 39** | **0.58×** |
| −6% (unrecorded) | 6 | 6 / 6 | 0.41× |
| **book** | **302** | **104 (34%)** | 1.73× |

**Post-stop recovery.** Of the **78** trades whose hard premium stop actually fired, **55 (70.5%)**
printed back at or above the entry premium before 15:50 ET, and **36 (46.2%)** printed **+30% or
better**. Median post-stop peak: **+22.6%**.
> This is a statement about the *tape*, not about realisable money — capturing it requires a rule,
> and [LOSER-SEPARABILITY-2026-08-19](LOSER-SEPARABILITY-2026-08-19.md) already established the
> losers are not selectable in advance. The counterfactual matrix below is what tests whether the
> recovery is *bankable*. It is not.

### The unit question, answered directly

What SPY move does one nominal premium-% stop correspond to, trade by trade?

| nominal stop | SPY move p10 | median | p90 | **p90 ÷ p10** |
|---|---:|---:|---:|---:|
| −8% | 0.0101% | 0.0199% | 0.0323% | **3.2×** |
| −20% | 0.0252% | 0.0497% | 0.0808% | **3.2×** |
| −50% | 0.0631% | 0.1242% | 0.2019% | **3.2×** |

**A single premium-% number means 3.2× different things across this book.** A −8% stop is a
0.010%–0.032% SPY move depending on the contract — i.e. between **0.33× and 1.07× of one minute's
noise**. So the *unit* criticism is correct on its face. It just does not convert into money.

---

## 🧮 THE MATRIX

Production baseline (as traded, replayed leg-by-leg and reconciled to the ledger):

| | |
|---|---:|
| n | 303 round trips / 35 days / ~60–90 independent decisions |
| gross | **−$1,804.99** |
| after real fees | **−$1,941.28** (ledger: −$1,939.90; $1.38 gap = per-execution fee ceiling, disclosed) |
| after fees + measured exit slippage | **−$3,777.72** |
| win rate | 23.1% (70 wins) |
| avg loss / worst loss | −$75.51 / −$664.69 |
| avg win / best win | $223.62 / $829.26 |
| book max drawdown | −$4,910.50 |

### Panel A — EXACT. No continuation is modelled anywhere.

Where the candidate stop is touched, the outcome is real tape. Where it is never touched, the row
keeps its **observed** outcome. ⚠️ **This panel is unbiased for tightening and structurally biased
against widening** (it books the downside of a wider stop and refuses to credit the upside), so
read only the top three rows as evidence.

| stop | net | net + slip | WR | avg loss | worst loss | max DD | n stopped | **Δ net** | Δ ex-08-04 | days +/− | winners→losers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **−8%** | −3,634.62 | −5,691.78 | 11.2% | **−33.85** | **−151.11** | **−4,029** | 239 | **−1,693.34** | +1,208.35 | 23/12 | **36** |
| **−12%** | −3,421.99 | −5,551.65 | 14.5% | −45.83 | −226.31 | −4,634 | 221 | **−1,480.71** | +280.86 | 21/13 | 26 |
| **−15%** | −2,992.28 | −5,129.29 | 16.8% | −53.53 | −282.71 | −4,636 | 208 | **−1,051.00** | −787.65 | 17/15 | 19 |
| −20% | −3,654.94 | −5,827.17 | 19.1% | −66.42 | −376.71 | −6,133 | 185 | −1,713.66 | −1,484.15 | — | 12 |
| −25% | −5,237.02 | −7,346.17 | 21.1% | −79.03 | −470.70 | −7,985 | 157 | −3,295.73 | −3,119.52 | — | 6 |
| −30% | −7,159.85 | −9,268.09 | 21.5% | −88.42 | −564.70 | −9,712 | 136 | −5,218.57 | −5,112.97 | — | 5 |
| −40% | −10,213.41 | −12,282.95 | 22.4% | −104.95 | −752.70 | −12,509 | 108 | −8,272.13 | −8,272.13 | — | 2 |
| −50% | −12,114.39 | −14,172.58 | 23.1% | −119.17 | −940.69 | −13,792 | 94 | −10,173.10 | −10,173.10 | — | 0 |

> 🚨 **THE TRAP, CAUGHT.** The −8% cell improves **average loss by 55%** (−$75.51 → −$33.85),
> **worst loss by 77%** (−$664.69 → −$151.11) and **book drawdown by 18%** — and makes the book
> **$1,693 worse**, while dropping win rate from 23.1% to 11.2%. It destroys **36 winners**,
> spending **$11,359 of winner dollars** to save **$10,207 of loser dollars**. Every loss metric
> improves; the only metric that matters gets worse. **That is a FAILURE, not a trade-off.**

### Panel B2 — widening, with the continuation bounded at production TP1

The one modelling assumption in the whole study: when a candidate stop is wider than the one that
actually fired, the trade continues on **real tape**, and is exited in full at the setup's own
configured TP1 (+100% ribbon / +40% VWAP_CONT / +30% others) if touched after the removed stop's
original minute. `n_terminal_modeled = 0` for every cell down to −65%, i.e. **no row needed a
modelled hold to 15:50.** Bias: production banks only 66.7–80% at TP1 and rides a runner, so this
panel is *conservative* on the upside of widening.

| stop | net | net + slip | WR | avg loss | worst loss | **Δ net** | **Δ ex-08-04** | Δ drop-top-3-days | days +/− | winners→losers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| −8% | −3,634.62 | −5,691.78 | 11.2% | −33.85 | −151.11 | −1,693.34 | +1,208.35 | +887.62 | 23/12 | 36 |
| −12% | −3,072.56 | −5,208.41 | 14.9% | −45.62 | −226.31 | −1,131.28 | +630.29 | +590.03 | 22/12 | 26 |
| −15% | −1,605.11 | −3,763.79 | 17.8% | −53.18 | −282.71 | +336.17 | −413.26 | +1,850.31 | 19/13 | 19 |
| **−20%** | **−382.78** | −2,597.96 | 21.5% | −65.60 | −376.71 | **+1,558.50** | **−948.16** | **−434.70** | **16/14** | 12 |
| −25% | −1,911.26 | −4,076.78 | 23.4% | −78.34 | −470.70 | +30.02 | −2,529.93 | +1,394.12 | 14/13 | 6 |
| −30% | −3,753.19 | −5,916.52 | 24.1% | −88.13 | −564.70 | −1,811.91 | −4,442.48 | +429.81 | 12/14 | 5 |
| −40% | −4,819.40 | −6,988.27 | 27.1% | −106.17 | −752.70 | −2,878.12 | −5,614.29 | +612.52 | 10/15 | 2 |
| −50% | −6,030.69 | −8,193.24 | 29.0% | −122.13 | −940.69 | −4,089.41 | −6,825.57 | +943.19 | 6/16 | 0 |
| −65% | −10,198.96 | −12,191.50 | 29.4% | −142.89 | −1,222.69 | −8,257.68 | −10,993.85 | −530.30 | 4/17 | 0 |
| −80% | −9,606.43 | −11,492.80 | 32.3% | −154.33 | −1,504.68 | −7,665.15 | −10,401.32 | +2,558.59 | 8/13 | 0 |

> 🚨 **RULE 4, VIOLATED BY THE WHOLE COLUMN.** Win rate rises **monotonically** from 11.2% to 32.3%
> as the stop widens, while net P&L peaks at −20% and then collapses. The widest cells buy a
> **9-point win-rate improvement** for **−$8,258**. Any cell chosen on win rate here is a losing
> choice.

### Panel C2 — the noise-normalised grid (stop = a fixed SPY move, delta-scaled per contract)

Per trade: `stop% = −(|delta| × SPY_move × SPY_price) ÷ entry_premium`, with delta solved from the
contract's own entry price via [`option_iv_solve.py`](../../backtest/lib/option_iv_solve.py)
(all 303 solved, zero failures). Same TP1 bound as Panel B2.

| SPY move | implied stop p10 / med / p90 | net | net + slip | WR | avg loss | **Δ net** | **Δ net+slip** | Δ ex-08-04 | Δ drop-top-3 | days +/− |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **0.050%** | −39.6% / **−20.1%** / −12.4% | **−993.50** | **−3,204.69** | 20.1% | −57.41 | **+947.78** | **+573.03** | **+616.61** | **+2,836.30** | **16/15** |
| 0.075% | −59% / −30% / −19% | −2,170.46 | −4,360.49 | 24.1% | −77.33 | −229.18 | −582.80 | −2,296.84 | +1,372.05 | 14/14 |
| 0.100% | −79% / −40% / −25% | −2,626.16 | −4,833.99 | 26.7% | −91.49 | −684.88 | −1,056.30 | −3,309.89 | −201.70 | 8/18 |
| 0.150% | — | −3,688.11 | −5,826.54 | 29.4% | −108.66 | −1,746.83 | −2,048.80 | −4,483.00 | −140.69 | 7/16 |
| 0.200% | — | −3,784.38 | −5,809.81 | 31.0% | −119.16 | −1,843.10 | −2,032.10 | −4,579.27 | +1,171.43 | 8/14 |
| 0.250% | — | −4,465.89 | −6,440.23 | 32.3% | −129.26 | −2,524.61 | −2,662.50 | −5,260.78 | +2,474.97 | 8/13 |
| 0.350% | — | −7,778.12 | −9,773.75 | 32.3% | −145.41 | −5,836.84 | −5,996.00 | −8,573.01 | +2,386.65 | 8/13 |
| 0.500% | — | −11,686.02 | −13,575.87 | 32.3% | −164.48 | −9,744.74 | −9,798.10 | −12,480.91 | +2,308.78 | 8/13 |

**The 0.050% cell is the only cell in the entire matrix whose improvement survives both the
drop-top-day and the drop-top-3-days test with a positive sign.** Its concentration is genuinely
low — the top day is 17.2% of the gross daily movement, the top trade 7.0%. It is not concentrated;
it is simply **small**: +$573 after full costs over 35 days, on a **16/15** day split, median
improving day **+$9.12**. It converts **14 winners into losers**, spending $4,641 of winner dollars
to save $7,375 of loser dollars.

---

## 🔬 THE 2026-08-04 PROBLEM

Every large positive number in this study traces to one day.

- **2026-08-04 was the book's best day as traded: +$3,613 net.** SPY ran 762 → 772.68 (**+1.4%**),
  a clean one-way trend day. 25 trades: 18 ribbon, 7 VWAP_CONTINUATION; exits were 11 structure
  stops, 9 TP1s, 5 premium stops.
- The 5 premium stops were VWAP_CONTINUATION's **−6%** fixed stop cutting 762/763/765 calls that
  closed the day around **$10** against a **$1.33–$1.77** entry.
- Under a wider stop those 5 rows are worth **+$29,651** if held to 15:50, or **+$2,507** with the
  TP1 bound applied.

**Effect of that one day on each headline cell:**

| cell | Δ net | Δ net excluding 2026-08-04 | top day's signed share of Δ |
|---|---:|---:|---:|
| flat −20% (TP1-capped) | +1,558.50 | **−948.16** | **+161%** |
| flat −20% (held to 15:50) | +28,166.77 | **−1,484.15** | **+105%** |
| no hard stop at all (held to 15:50) | +17,246.67 | **−12,633.76** | **+173%** |
| −8% (exact) | −1,693.34 | **+1,208.35** | — |
| noise-normalised 0.050% | +947.78 | +616.61 | −191% (top day is 08-06, and it is *negative*) |

The −8% row makes the symmetry unmissable: **excluding 2026-08-04, tightening to −8% would have
made +$1,208.** Including it, it loses $1,693. The stop axis is not an edge — it is a **bet on
whether the next 35 days contain a 2026-08-04.** That is the right-tail book restated at the exit.

---

## 🔧 THE SURGICAL CELL — change only the stops that are inside the noise

Cohort: the **75 trades** whose configured hard stop is tighter than −10% (the −6% / −8% satellite
setups). 19 days, 34 date-symbol clusters, baseline **−$2,139.45**. Ribbon / structure-mode rows
are left completely untouched.

| satellite stop | book net | Δ net | Δ net+slip | Δ ex-08-04 | Δ drop-top-3 | days +/− | WR |
|---|---:|---:|---:|---:|---:|---:|---:|
| −10% | −2,033 | −92 | −246 | +45 | −109 | **10/5** | 23.1% |
| −12% | −2,198 | −257 | −358 | −12 | −510 | 9/6 | 23.4% |
| −15% | −1,761 | +180 | +108 | −631 | −132 | 6/7 | 24.1% |
| **−20%** | **−816** | **+1,125** | +1,029 | **−1,611** | +328 | **4/7** | 25.4% |
| −25% | −1,891 | +50 | −13 | −2,686 | +86 | 4/7 | 25.4% |
| −30% | −3,035 | −1,093 | −1,150 | −3,829 | −176 | 4/7 | 25.4% |
| −50% | −6,732 | −4,791 | −4,866 | −7,527 | −284 | 5/6 | 26.1% |
| none | −14,178 | −12,237 | −12,162 | −14,973 | +550 | 5/5 | 27.4% |

**This is the cleanest kill in the study.** The best-dollar cell (−20%) makes **more days worse
than better (4 vs 7)** and loses **−$1,611** once 2026-08-04 is removed. The cells that improve
*most days* (−10%: 10 improved vs 5 worsened) **lose money**. Nothing here is shippable.

---

## 📋 PRE-REGISTERED HYPOTHESIS (SHADOW ONLY — nothing armed)

**`PREREG-STOP-NOISE-UNIT-2026-08-19`**

> For the satellite setups only (VWAP_CONTINUATION, vwap_reclaim_failed_break, vix_regime_dayside,
> bollinger_squeeze), replacing the fixed −6% / −8% premium stop with a **delta-scaled stop equal
> to a 0.050% adverse SPY move**, floored at −10% and capped at −40%, improves net P&L after fees
> and exit slippage **without reducing the share of days that improve**.

**Instrument:** a shadow counter that, per satellite fill, logs the production stop level, the
noise-normalised level, and both counterfactual outcomes replayed from the same OPRA tape the next
evening. Zero live behaviour change. $0.

**Kill criterion (pre-committed).** Evaluated after **≥40 new satellite fills across ≥15 trading
days**. KILL unless **all four** hold:
1. cumulative Δ net **after fees AND exit slippage** > $0;
2. `days_improved ≥ 1.5 × days_worsened`;
3. the top single day is **< 50%** of the gross \|daily\| movement;
4. Δ net after dropping the **best 3 days** > $0.

**Honest status: on the retrospective 2026-06-26 → 2026-08-19 sample this rule FAILS criterion 2**
(16 improved vs 15 worsened = 1.07×, median improving day +$9.12). It ships as a shadow counter
precisely *because* the retrospective sample does not clear its own bar. Nothing is armed, and
`per_band_stop.py` — the already-built, still-unwired band resolver this would consume — stays
shadow.

---

## 🧾 METHOD, LIMITS, AND WHAT IS REAL

**Real, not modelled.** The price path is full-day 1-minute OPRA tape from
`backtest/data/opra_1m_cache` — **all 109 (symbol, date) pairs cached, zero fetch misses, zero rows
skipped, 303/303 simulated.** Every non-hard-stop exit (TP1, structure stop, ribbon flip, time
stop, and the profit-lock trail rungs the ledger also labels `premium_stop`) is replayed at its
**observed minute and observed price**. Only the hard entry-referenced stop is swapped.

**Baseline self-check.** Replaying every observed leg reproduces the ledger's gross P&L on
**303/303 rows** (the run aborts otherwise). Net differs by **$1.38** because fees are charged
per execution here rather than per round trip.

**Leg classification.** 173 `premium_stop` legs split into **85 hard** entry-referenced stops and
**88 profit-lock trail rungs** (preserved, since deleting them would erase the winners from every
wide cell — the exact artifact this lane exists to catch). 49 trail legs are corroborated against
the contract's own running high-water mark at a known `trail_pct`; **39 legs matched neither shape
and are reported, not bucketed** — they were preserved as non-hard, which is the conservative
choice for the widening cells.

**The one modelling assumption.** In Panels B2/C2, a trade whose hard stop no longer fires is
exited **in full** at its setup's configured TP1 if touched. Production takes 66.7–80% there and
rides a runner, so this is **conservative on the upside of widening**. The unbounded variants
(Panels B/C in the JSON) hold to 15:50 instead and are **wildly optimistic** — every one of their
positive cells is >100% carried by 2026-08-04, which is why they are not quoted above.

**Costs, both directions.** Fees recomputed per execution at the empirical OCC/ORF/TAF/SEC rates
(CAT excluded, as in `trade-matrix.json`). Exit-side spread realism debits **0.129 × the exit
minute's traded range × 100 × qty** on the baseline *and* every counterfactual.
⚠️ **This gives $1,836 of exit slippage across 303 trips ($6.06/trip), not the ~$895 quoted in
[COST-REALISM-2026-08-18](COST-REALISM-2026-08-18.md).** The whole difference is that the earlier
figure extrapolated from *median* exit qty 3, while mean qty here is **4.96** (risky-3 trades 10
lots). Per-trade computation is the more careful number; reported, not reconciled away.

**No look-ahead (C6).** Every stop level is fixed at entry from information available at entry
(entry premium, spot, strike, time to 16:00 ET). Stops fire on the first minute whose *low* touches
the level; the counterfactual fill is `min(stop_level, bar_open)`, so a gap-through is never
credited a better price than the open. Primary results are **entry-bar-exclusive**; the inclusive
sensitivity moves the −20% cell by **$22 of $28,167** and the −50% cell by **$0**.

**Independence.** The 5 arms trade **one shared signal** (r = 0.846, 95.7% sign agreement). 303
rows are ~60–90 independent decisions. The nominated cell changes **83 date-symbol clusters across
31 days** — and the day-level sign test (16/15) is the statistic that matters, because the
day is the unit at which this book's P&L is actually concentrated.

**What this study cannot answer.** The 2026-08-19 exemplar in the brief was cut by a
**structure stop**, not a premium stop, on 4 of 5 arms. A premium-stop matrix cannot move that day
at all. If the tight-stop intuition is right, **the structure stop's buffer — not the premium stop
— is where it lives**, and that is a different lane's question.

---

## 🔗 See also

- [LOSER-SEPARABILITY-2026-08-19](LOSER-SEPARABILITY-2026-08-19.md) — losers are not selectable in advance
- [COST-REALISM-2026-08-18](COST-REALISM-2026-08-18.md) — the fee and exit-slippage model used here
- [WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19](WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19.md)
- `automation/state/fleet/per_band_stop.py` — the built-but-unwired premium-band stop resolver a shipped version of this would consume
