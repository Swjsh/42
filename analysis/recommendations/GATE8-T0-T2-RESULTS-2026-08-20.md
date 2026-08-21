# Gate-8 work package — T0 + T2 results (2026-08-20 evening)

> Executing `markdown/planning/OPUS-WORKER-HANDOFF-2026-08-20-GATE8.md`.
> **T2's pre-registered kill criterion FIRED. T3 is dead — the seven-arm matrix does not get built.**

---

## Verdict

**Gate 8 is not the thing standing between us and money. It is the most discriminating filter in the bear stack, and the setups it rejects are the worst in the book.**

Entries blocked by **gate 8 alone** lose **−$36.79/trade** — nearly **2× worse** than entries missing two or more filters (−$19.10), with a lower win rate (22.6% vs 30.4%). The pre-registered criterion was "missing-[8] must beat the pooled cohort." It lost to it by a factor of two.

---

## T2 — blocker-stratified re-cut (the analysis nobody had run)

Population: `LADDER-FULLHIST-2026-07-27.json` lane 7, **1,538 real-OPRA resolved trades**, synthetic excluded per the reporting rule. Every prior study relaxed by *score* or by *bypass scope*; none had ever asked **which blocker was missing**.

| Stratum | n | Total | Per trade | WR | Day majority |
|---|---:|---:|---:|---:|---:|
| **missing ONLY [8] — VIX gate** | **137** | **−$5,040** | **−$36.79** | **22.6%** | **24/92** |
| missing 2+ blockers | 1,338 | −$25,559 | −$19.10 | 30.4% | 115/342 |
| missing ONLY [9] — breakdown bar | 8 | +$742 | +$92.72 | 37.5% | 3/7 |
| missing ONLY [7] — vol divergence | 4 | −$348 | −$87.00 | 25.0% | 1/4 |

**⚠️ n=8 and n=4 are meaningless.** Ignore the +$92.72. The only comparison with power is missing-[8] (n=137) vs pooled (n=1,338), and it is decisive in the wrong direction.

### The uncomfortable detail

Trigger mix inside the missing-[8] cohort:

| Triggers | n |
|---|---:|
| `level_rejection` alone | 50 |
| `confluence` + `level_rejection` | 36 |
| `confluence` + `level_rejection` + `trendline_rejection` | 20 |
| `level_rejection` + `ribbon_flip` | 11 |

**These are the strongest-looking setups in the system.** Clean structure, named level, multiple corroborating triggers — and VIX not confirming. They look best and pay worst. That is exactly the edge-shaped illusion the gate exists to refuse.

---

## Level-quality stratum (J's addition) — REFUTED, and it re-discovers L142

J's hypothesis: *"768.60 isn't a random level — it's been respected for days. Condition on level strength."* Level strength proxied by how often the engine re-derives that same `rejection_level` price across the population.

**Within the missing-[8] cohort:**

| Level strength | n | Per trade | WR |
|---|---:|---:|---:|
| STRONG (≥10 recurrences) | 4 | −$86.25 | 50.0% |
| **medium (4–9)** | **34** | **−$102.71** | **11.8%** |
| weak (1–3) | 99 | −$12.15 | 25.3% |

**Full population, same cut:** STRONG n=28 −$15.37 · medium n=393 **−$42.78** · weak n=1,117 −$12.33.

**Stronger levels performed WORSE, not better** — the medium bucket is the worst in both cuts, and the pattern is not gate-8-specific. STRONG is n=4/n=28, too thin to read.

### This is L142 / C25, rediscovered from the other side

> **L142 (2026-06-17):** "Star-score formula produces INVERSE correlation with level respect — high touch_count drives ★★★ then those levels break more… Touch count is the WRONG input to a respect-predictor. A respected level is one that bounced price CLEANLY on the FIRST visit. High touch_count with zero net respect = exhausted levels."

**J's read of 768.60 is factually correct and its trading implication is inverted.** The shelf *was* touched by 77 of 432 bars across three sessions. That is precisely what an **exhausted** level looks like in L142's framing — and on 2026-08-20 it did what exhausted levels do: it broke, price flipped it, and the day ran 6 points the other way.

The level mattered. It just wasn't a *reason to enter earlier* — it was a reason the eventual break ran so far.

---

## T0 — data authority: RESOLVED, and my earlier claim RETRACTED

**There is no feed disagreement.** Lag test across all 78 RTH bars:

| Lag | mean abs error | exact-cent matches |
|---|---:|---:|
| 0 bars | $0.3430 | 1/78 |
| **1 bar (5 min)** | **$0.0285** | **24/77** |
| 2 bars | $0.3119 | 1/76 |

The engine reads the **last CLOSED 5m bar** — correct, and required by the closed-bar rule (C6). My earlier "engine says open 768.74 / CSV says 765.95" finding compared **closed-bar closes against intrabar extremes** — two different statistics. **Retracted.**

**Authoritative for replays: the CSV** (it carries true OHLC). The engine's `spy` field is a decision-time closed-bar close and must never be read as session OHLC. The EOD audit's session numbers are relabelled accordingly.

### But T0 surfaced a real defect

| Tick | Engine `spy` | Last closed bar | Drift | `blind` |
|---|---:|---:|---:|---|
| 09:30 | 768.74 | 765.94 | **+2.80** | False |
| 09:31–09:34 | 769.09 | 765.94 | **+3.15** | False |
| 09:35 | 769.09 | 767.05 | +2.04 | False |
| 09:36 onward | 767.05 | 767.05 | **0.00** | False |

**`768.74` is the 06:35 premarket bar's close** — the engine opened the session on a quote **~3 hours stale**, reading **$3.15 too high** for six ticks, with **`blind=False` throughout.** The never-blind beacon did not detect it; it believed it had good data.

Bull score read **9/6** during the stale window and dropped to **8/6** the tick it corrected. No trade resulted today — but 09:30–09:35 is exactly when a gap-and-go fires, and there is a **−$1,569 stale-level scar on record (2026-08-14)**. Silent staleness is worse than a detected outage.

---

## Package status

| Task | Status |
|---|---|
| **T0** data authority | ✅ **DONE** — no disagreement; closed-bar lag is correct; CSV is authoritative. Retracted my own claim. Found the open-tick staleness defect. |
| **T2** blocker-stratified re-cut | ✅ **DONE** — kill criterion FIRED. Gate 8 vindicated. |
| **T3** gate-8 isolation matrix | ⛔ **DEAD** — killed by T2's pre-registered criterion. Do not build. |
| Level-quality stratum | ✅ **DONE** — refuted; rediscovers L142/C25. |
| **T1** gate-8 provenance | ⬇️ **DEMOTED** to documentation-only. The gate is empirically vindicated; provenance is now about recording *why*, not deciding whether. |
| **T4** bypass `trendline_present` | 🟢 **STILL OPEN** — genuinely untested, and the 12:51→12:56 scar (corroboration BLOCKED entry) is a real pathology independent of gate 8. |
| **T5** exit-survival counterfactual | ⬇️ **DEMOTED** — T2 already answers the economic question. Only worth running if T4 needs it. |
| **T6** ladder-ledger dedupe | 🟢 **STILL OPEN** — real bookkeeping bug, cheap fix. |

**Net: the package shrank from 6 tasks to 2.** That is the pre-registration doing its job — one cheap re-cut of data we already had killed a seven-arm matrix before a single night was spent on it.

---

## What did NOT change

Gate 8 being vindicated does **not** vindicate the *architecture* around it:

- **Entry is still binary** — a 9/10 and a 2/10 are identical at the order gate.
- **One shared signal across five arms** (r=0.846) — arms cannot diversify a gated signal.
- **One relief valve** — ~89% of bear ENTERs come through the trendline-only bypass; on 08-20 it was 100%.
- **Corroboration still blocks entry** — 12:51–12:55 two triggers → HOLD; 12:56 one trigger → ENTER. **T4.**
- **Gate 8 still has no revalidation clock**, and now it has a fresh scorecard worth clocking against.

_Sources: `analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json` lane 7 · `automation/state/core-decisions.jsonl` · `backtest/data/spy_5m_2026-05-19_2026-08-20.csv` · `markdown/doctrine/LESSONS-LEARNED.md` L142._
