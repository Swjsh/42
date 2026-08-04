# EOD 2026-08-04 — LENS 4: MAKE SURE WE CAN DO IT AGAIN

**Generated:** 2026-08-04 after the close (`market_hours=False` verified via `setup/scripts/et_clock.py`).
**Data:** `analysis/deep-research/EOD-2026-08-04-REPEATABILITY.json` · broker FIFO round trips + real 1-min OPRA + the real `exit_manager` core. No LLM anywhere in the numbers.

---

## VERDICT (read this line if you read nothing else)

**+$3,624 was two trades on a 1-in-20 tape, on a config that is one day old — and the biggest single contributor to it is a leverage knob that lost $1,304 across the five hardest days we have.**

- **57% of today ($2,061) would have happened under yesterday's config.** 43% ($1,563) is what last night bought.
- **Two signal clusters produced 90.2% of gross-positive P&L.** The other six clusters combined **lost $318**.
- **Today's exact day-shape is 5.1% of 395 days.** Honest expected day: **$45–$137**, not $3,600.
- **Hard-day test: FAILED.** The ATM tier extension amplifies losses on chop/fade days by the same mechanism that paid today.
- 🚨 **Separate HIGH-severity defect found:** the three fleet arms have **no working PDT gate**.

---

## 1 — CLASSIFY: what kind of day was this?

**Archetype: `gap-go`** — the same as Monday. But the archetype alone hides how extreme it was:

| feature | value | reading |
|---|---|---|
| `gap_pct` | +0.39% | up-gap, never filled |
| `open_loc` | **0.008** | **opened AT the session low** |
| `t_low` | **0.0** | **the low printed on the first bar** |
| `body_pct` | +1.40% | huge up body |
| `close_loc` | 0.83 | closed near the high |
| `t_high` | 0.974 | high on the last bar |
| `range_pct` / VIX | 1.69% / 15.57→16.42 | wide range, calm vol |

One-way up from the opening bar to the closing bar. Nested frequency over **N=395** assignable days:

| tier | definition | n | share |
|---|---|---|---|
| T1 | `gap-go` | 89 | 22.5% |
| T2 | + bullish (gap up, up body) | 55 | 13.9% |
| **T3** | **+ one-way (open bottom 20%, close top 30%)** | **20** | **5.1% — 1 day in 20** |
| T4 | + body ≥ 1.0% | 7 | 1.8% |
| T5 | + range ≥ 1.5% | 4 | 1.0% |

> **Monday AND Tuesday are both T4 — 7 days in 395 ever.** Back-to-back is a **cluster, not a new regime.** Nothing in the population says this continues.

### The honest expected value

The live real-fill record (24 traded days, all five arms):

| | total |
|---|---|
| all 24 days | **+$2,494** |
| **excluding today (23 days)** | **−$1,130** (−$49.13/day) |

*The engine's entire live paper record before today was negative. Today is 145% of the all-time total.*
⚠️ Mixed sizing: arms were ~$1.7K until the 08-02/03 $5K rebuild. Cross-era dollars are labelled, not blended.

Per-archetype live record (n tiny — ANECDOTE):

| archetype | n | total | mean |
|---|---|---|---|
| gap-go | 7 | +3,300 | +471 — **ex-today: n=6, −$324** |
| gap-fade | 4 | −1,036 | −259 |
| range-chop | 7 | −186 | −27 |
| V-reversal | 3 | −492 | −164 |
| trend-down | 1 | +1,341 | +1,341 |
| trend-up | 1 | −325 | −325 |
| pin-day | 1 | −108 | −108 |

**EV/day at P(T3) = 5.06%:**

| scenario | EV/day |
|---|---|
| live baseline as-is, today's payoff repeats | **+$137** |
| baseline scaled 2.9× to $5K sizing | **+$48** |
| T3 payoff halved | **+$45** |
| both pessimistic | **−$44** |
| the nightly instrument's own `mix_ev` (population-weighted) | **+$74** |

> **$100–200/day is reachable but is NOT what today proved.** The whole spread is driven by n=1 on the T3 payoff term.

---

## 2 — DECOMPOSE: tape vs. what we shipped

**Method.** Entry population = the REAL live decision ledgers (not a re-derived signal stream). Exit layer = the real `exit_manager.plan_exit_actions` on real 1-min OPRA. Trades that actually happened take the **broker's own P&L and exit timestamp**; only genuinely counterfactual entries are simulated.

**Parity gate: PASS.** The `TODAY` lane reproduces the broker day to **$0.00**. The all-simulated probe lane runs **+29.4%** — that is the disclosed error bar on simulated rows, and the reason the hybrid design exists.

### Leave-one-out ladder (paired vs TODAY = $3,624.00)

| revert | Δ | basis |
|---|---|---|
| **SHIP B** — re-arm `block_elite_bull` | **−$1,141.00** | **EXACT, zero simulation** |
| **ATM-TIER-EXTENSION** → OTM-2 | **−$984.39** | SIM, 4 arms |
| **FIX2** vwap emission dead | **+$247.50** | SIM, 2 arms |
| **SHIP A** → limit-anchored exits | **+$147.26** | pure-sim paired lane only |
| **ALL FOUR = yesterday's config** | **−$1,562.75** → day = **$2,061.25** | |

LOO deltas sum to −$1,730.63 vs a joint −$1,562.75 → **$168 of overlap**. The ships are **not additive**; the ATM tier and the vwap fix act on the same morning cluster.

Deflating the simulated YESTERDAY lane by the measured +29.4% optimism bounds it at **$1,593–$2,061**, so config bought **$1,563–$2,031**.

### Two findings that matter more than the split

**① SHIP B is the cleanest win on the board — and it needs no simulation to prove.**
All **82 of 82** core `ENTER_BULL` verdicts today were `ELITE` + `level_reclaim` — precisely what `gates.py` gate #3 refuses, inside its VIX band. With the gate armed, **safe-2 and bold-2 take zero trades**. Fleet arms are untouched (`fleet_rest` never enforced `GATE_ORDER`). $1,141 = exactly safe-2 $662 + bold-2 $479.

**② The vwap fix was NET NEGATIVE. The 09:57 alarm was right; the retraction was wrong.**

Reverting FIX2 **improves** the day by **+$247.50**. The mechanism is visible in the ledgers: while risky-1/risky-3 held vwap positions from 09:46, both were **offered the ELITE ribbon signal at 09:58–10:12 and refused it with one reason only — "position already open."** With vwap dead they take that ribbon entry instead.

- risky-3: $805 → **$1,173** (+$368) — it skips four churns and just takes the winner
- risky-1: $1,041 → **$916** (−$125) — the counter-example

> The 5th vwap entry becoming the trade of the day is **survivorship**. The arm was getting that move anyway, via a higher-quality ELITE signal, without the four churns that cost −$288. **n=2 arms, one day — directional, not ratified.**

### Concentration — this was a two-trade day

| cluster | n | net |
|---|---|---|
| 09:46–09:50 vwap | 4 | +$421 |
| **09:54–09:58 763C ribbon** | 5 | **+$1,750** |
| 10:35 vwap | 1 | −$80 |
| 11:26–11:27 768C | 4 | −$193 |
| 11:51–11:52 769C | 4 | −$361 |
| **12:28 769C ribbon** | 4 | **+$2,192** |
| 13:23–13:24 771C | 1 | +$9 |
| 13:41–13:42 772C | 2 | −$114 |

**Top 2 clusters = $3,942 of $4,372 gross-positive (90.2%). All other clusters combined: −$318.**

---

## 3 — THE HARD-DAY TEST: does this config bleed on chop?

**Answer: YES. The responsible change is ATM-TIER-EXTENSION-2K-10K.**

*Method — deliberately narrower and exactly parity-clean.* The decomposition harness **fails its parity gate on the older days** (3-min tick cadence; 2026-07-22's safe-2 fill has no matching core ENTER row at all — the L244 second-path blind spot), so nothing it says about them is quotable. Instead: hold the trade fixed — same arm, entry, qty, exit contract — and change **only the strike**. Lane A is the real broker round trip; Lane B re-prices the identical trade OTM-2.

Days selected on regime-library **features**, not P&L, one per hostile mode.

| date | archetype | n | ATM (real) | OTM-2 (sim) | ATM − OTM2 |
|---|---|---|---|---|---|
| 2026-07-20 | gap-fade | 5 | −141.00 | −21.60 | **−119.40** |
| 2026-07-22 | pin-day | 3 | −108.00 | −99.00 | −9.00 |
| 2026-07-27 | gap-fade | 6 | −828.00 | −123.00 | **−705.00** |
| 2026-07-08 | V-reversal | 10 | −304.00 | −142.80 | −161.20 |
| 2026-07-15 | V-reversal | 4 | −309.00 | 0.00 | −309.00 |
| **5 hard days** | | 28 | **−1,690.00** | **−386.40** | **−1,303.60** |
| 2026-08-04 | gap-go | 25 | +3,624.00 | +1,388.13 | **+2,235.87** |

**Mechanism split of the −$1,303.60:**

- **−$737.00** — trades OTM-2's $0.30 `min_entry_premium` floor would have **refused outright**. Every one a loser on those days. *This is exactly the participation the ATM extension was shipped to buy.*
- **−$566.60** — the same trades at **~2.1–3.1× premium per contract at unchanged qty**.

On 08-04, **zero** contracts were floor-blocked and the entire +$2,236 came from notional.

> **ATM-TIER-EXTENSION is not a strike-selection edge. It is symmetric leverage wearing a strike-selection costume** — ~2.2× notional at fixed contract count. It made $2,236 on one trend day and lost $1,304 across five hostile ones (net +$932 over the six). Hostile archetypes (range-chop, gap-fade, pin-day, inverted-V) are **63.5%** of the population; today's shape is 5.1%.
>
> ⚠️ n = 5 days / 28 round trips. Directionally clear, statistically an **ANECDOTE**. Not a kill recommendation — its own pre-registered kill criterion (n≥10 fills/arm or 10 sessions, net<0) is the authority and is **not yet met**.

---

## 4 — THE REPEATABILITY SCORECARD

| bucket | $ | share |
|---|---|---|
| **Tape** (would have paid anyway) | **$2,061** | **57%** |
| **Controllable** (config shipped 08-03 evening) | **$1,563** | **43%** |

Controllable, broken out:

| ship | $ | note |
|---|---|---|
| SHIP B elite-gate lift | **+$1,141** | EXACT. 73% of the controllable slice. |
| ATM tier extension | **+$984** | ⚠️ symmetric leverage; −$1,304 across 5 hard days |
| FIX2 vwap emission | **−$248** | ⚠️ negative contribution |
| SHIP A anchor-to-fill | **−$147** | cost money today **by design** — its own commit predicted it ("SHIP A buys the other tail") |

**Unmodelled (named, not hidden):** IEX-tail level-refresher fix (the counterfactual reuses the live trigger levels); SHIP C qty10-under-$0.50 (never fired); equity-driven re-sizing under a cheaper OTM-2 contract.

### Shipped so this answers itself

`setup/scripts/regime_attribution.py` → **`Gamma_RegimeAttribution`**, daily 15:45 MT = 17:45 ET. Stdlib-only, $0, no LLM, no network, fail-open, places nothing. Writes `automation/state/regime-attribution.json` + upserts `analysis/regime-library/attribution-history.jsonl`.

Every night it reports: archetype · population share · **strictly-prior** archetype mean (a day never helps set the bar it is graded against) · `regime_lift` · `mix_ev` · top-1/top-2 concentration.

First run, verified through the real scheduled-task chain (`LastTaskResult=0`):

```
REGIME-ATTRIBUTION 2026-08-04  archetype=gap-go (22.5% of population)
  day P&L $3,624.00   bold-2=$479  risky-1=$1,041  risky-3=$805  safe-2=$662  safe-3=$637
  prior days of this archetype: n=6 mean=$-54.00   regime_lift=$3,678.00
  concentration: 25 round trips, gross+ $4,735.00 gross- $-1,111.00, top2 share=30%
  mix_ev=$73.71/day (archetype coverage 98% of population mass)
  live record: 24 days $2,494.00 total ($-1,130.00 excluding this day)
```

---

## 🚨 OPEN — HIGH severity, found while checking PDT headroom, NOT fixed here

**`FLEET-PDT-GATE-READS-ZERO` — the three fleet arms have no working PDT gate.**

- `automation/state/fleet/fleet_live.py:660` — `day_trades = int(acct.get("daytrade_count", 0) or 0)`
- `fb.get_account()` on all five arms returns **no `daytrade_count` and no `pattern_day_trader` key** (37 keys verified live after the close) → the gate is **permanently fed 0**.
- Every one of today's 384 ticks/arm on safe-3 / risky-1 / risky-3 logged `day_trades: 0` **while those arms took 6 / 5 / 8 day trades**.
- Core bold-2 runs a *different* path (`heartbeat_core`) whose counter **did** move: 3/3 by 11:26 ET, 21 ENTERs correctly refused.

All five arms are $5K-class at multiplier 4 → **real PDT (3 day-trades / 5 business days) binds.**
Shape: **C7/C14 — a fail-open default masking an absent field** (same family as L241).

**Not fixed in this lens on purpose:** it is a trading-path guard, and making it fail-CLOSED could block every fleet entry tomorrow. Needs its own blast-radius pass + prereg.

---

## Caveats

- The YESTERDAY lane's fleet-arm rows are **SIMULATED** (different strikes have no broker answer). Pure-walk error measured at +29.4%; the config range [$1,563, $2,031] carries it.
- Hard-day n is **tiny**: 5 days, 28 round trips, 1–2 days per archetype. **ANECDOTE.**
- The vwap verdict rests on **n=2 arms on one day** and splits by arm. Directional, not ratified.
- The live record spans two sizing eras. Every cross-era dollar comparison is labelled.
- Archetype labels are **post-hoc** (whole-session) by construction — slicing and attribution only, never a same-day live entry.
- Ground truth here is **$3,624.00** (FIFO premium math). The brief's $3,617.19 is the equity delta; the $6.81 gap is per-contract regulatory fees. Both correct for what they measure.

---

## Artifacts

| what | path |
|---|---|
| This report | `analysis/deep-research/EOD-2026-08-04-REPEATABILITY.md` |
| Full data | `analysis/deep-research/EOD-2026-08-04-REPEATABILITY.json` |
| Decomposition harness | `backtest/tools/repeatability_decompose_2026_08_04.py` |
| Hard-day strike axis | `backtest/tools/hard_day_strike_axis_2026_08_04.py` |
| Nightly instrument | `setup/scripts/regime_attribution.py` + `setup/scripts/install-regime-attribution.ps1` |
| Guards (47/47 green, RED-proofed) | `backtest/tests/test_repeatability_decompose_2026_08_04.py` · `backtest/tests/test_regime_attribution_2026_08_04.py` |

**Revert (one line):** `Unregister-ScheduledTask -TaskName Gamma_RegimeAttribution -Confirm:$false`
Everything else in this lens is read-only research tooling — no trading-path file was touched.
