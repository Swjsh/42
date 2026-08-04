# EOD 2026-08-04 — LENS 5: the twin, the instruments, and process scrutiny on ourselves

_Written after the close (verified `16:07 ET Tuesday EDT, market_hours=False` via
`setup/scripts/et_clock.py`). Real broker fills / real twin journal only. Every small-n
figure is labelled. Hindsight columns are labelled ORACLE and never mixed into
live-executable ones._

**Scope note:** the SPY day itself (+$3,617.19, 5 arms) and the risky-3 7×-re-entry
counterfactual belong to other lenses and are NOT re-derived here. This lens covers the
**crypto twin (arm #6)**, **scheduled-instrument health**, **an audit of my own judgment**,
and **cost + git hygiene**.

---

## 0. Verdict

Three things matter out of everything below:

1. **The twin had a bad day and it is the most useful thing in this report.** 13 organic
   round trips, **0 winners**, -$2.66 — 11 of 13 knifed out by `structure_stop` inside
   minutes. The twin is the mechanism-validation ground, and today it ran the *same*
   rapid-re-entry-after-stop pattern that risky-3 ran on SPY. It bled. That is a
   mechanism signal the SPY lens should have on its desk.
2. **Of the two fixes I shipped this morning, one is organically proven and one has never
   run.** The ladder `time_stop_et` fix is proven on live data. The max-hold journaling fix
   has **not been exercised once** since it shipped — and the coverage battery that reports
   it GREEN cannot prove it, because that branch reaches its designed stage only 14% of the
   time.
3. **I found a third defect in my own work from this morning, and it is the worst of the
   three.** My "corrected" ladder A/B (+1.1044% / +0.5745%) is a survivorship-filtered
   reconstruction, not a clean baseline. On genuinely post-fix data both lanes flip
   negative. Small-n, but the number I shipped was overstated and is now labelled as such.

**Two more that deserve J's eye:**

- ✅ **The IEX tail worked.** `intraday_rth_high` level coverage went **28.6% → 75.0%** with
  median latency **9.1 min → 0.0 min** — the exact source it was built to fix. One session
  each side, so directional, not validated (§2.3).
- 🚩 **A second armed setup has never traded, for a completely different reason.**
  `double_bottom_base_quiet` — armed 34 days, 0 fills. Its detector is *alive* (10 fires in
  one session); **every fire was killed downstream** by the free-model veto (6) and the risk
  cap (4). That is not evidence against the setup — it is evidence nothing has ever let it
  try (§3.4).

**Two self-corrections inside this report, both caught before it shipped:** I nearly
reported WinnerAutopsy as broken (it is healthy — I had read its same-day probe, not its
population run, §2.2), and I first mis-described `double_bottom_base_quiet` as a dead
emitter (it is a blocked one, §3.4).

---

## 1. The twin (arm #6) — full day

### 1.1 The book

`Gamma_CryptoTwin` ran **1,200 ticks / 1,199 expected = 100.0% uptime**, 0 incidents,
breaker not tripped, sentinel **GREEN** (`automation/state/twin-sentinel.json`).

**Every one of today's 14 entries was ORGANIC** (`scenario=null` on all 14 `PLACED` rows).
Zero forced/scenario entries in the ET day — the coverage battery's forced sweep ran at
23:50–00:10 ET the previous evening.

| | today (ET) |
|---|---|
| PLACED / FILLED | 14 / 13 (+1 still open at write time) |
| CLOSED / EXIT_FILLED | 13 / 13 |
| ENTRY_MISSED / ENTRY_PARTIAL_FLATTENED | 1 / 1 |
| **Realized (organic)** | **-$2.6579** |
| **Wins** | **0 of 13** |

Exit-reason split: `structure_stop` ×12, `ribbon_flip_back` ×1. Losses ranged
-$0.11 to -$0.37 (-0.07% to -0.24%).

### 1.2 The corrected organic book

`crypto_twin_pnl.py` now reports the organic lane as:

> **36 round trips | 8.3% WR | total -3.011% | avg -0.0836%/trip | -$3.84**

Yesterday's post-backfill figure was n=25 / wins=3. Today added **11 organic round trips
and zero wins** (the count differs from the 13 ET-day closes because the module bins on
UTC day). The three lifetime winners are unchanged; the twin has not produced a winning
organic trade since the 2026-08-03 max-hold ride.

**The shape that matters — this is the finding.** Today's exits cluster like this
(UTC): 14:50, 15:10, 15:20, 15:25, 16:05, 16:30, 16:45, 17:15, 17:25, 17:50 — **ten round
trips in three hours, every one a `structure_stop`, every one a loss.** The twin entered,
got stopped on structure within minutes, and immediately re-entered the same idea. That is
rapid re-entry after a stop-out, and on this instrument it is a **pure bleed function**:
each cycle pays the round-trip spread (median **0.33%** round-trip, §1.5) to re-acquire a
position that the structure stop then removes again.

This is directly relevant to the SPY open question (risky-3, seven `ENTER_BULL` in eleven
minutes, no re-entry lock since the 2026-07-02 deletion). The twin cannot price the SPY
question — twin P&L is never SPY evidence — but it is the designated place to ask whether
a *mechanism* is sound, and today the mechanism "re-enter immediately after a structure
stop, with only flat-verify and risk_gate between fires" produced 10 consecutive losses on
a 24/7 instrument. **Recommend the SPY re-entry lens read this as corroborating mechanism
evidence, not as P&L evidence.**

### 1.3 Fix #1 — max-hold exit journaling (commit `1a55e410`): **NOT EXERCISED**

The fix is correct code. It has never run in production.

- The **only** `max_hold` `EXIT_FILLED` row that exists anywhere is
  `2026-08-03T19:55:15Z` — and that row was **written by the commit itself as a backfill**,
  not produced by the live path.
- **Zero** max-hold exits occurred today, organic or forced.
- The coverage battery's `ENTRY_MAX_HOLD` branch *did* fire today at 00:06→00:07Z — and
  **exited via `ribbon_flip_back` in 59 seconds**, never reaching max-hold at all. It also
  ran on pre-fix code (fix landed 13:55Z; branch fired 00:07Z).

**So: "does the P&L module now pair max-hold trips?" — yes for the backfilled row, and
that is all we know.** The live code path that writes it remains unproven.

**And the instrument that claims otherwise is wrong.** `path-coverage.json` reports
`ENTRY_MAX_HOLD: GREEN` today. It is GREEN because
`crypto_twin_scenarios._ALWAYS_ACCEPTABLE_STAGES = {"ribbon_flip", "time_stop"}` grades a
preemption as acceptable. Across all history:

| forced branch | n | reached its DESIGNED stage | actual stages |
|---|---:|---:|---|
| `ENTRY_TP1_TRAIL` | 22 | **2 (9%)** | trail 2, time_stop 11, ribbon_flip 8, max_hold 1 |
| `ENTRY_STRUCTURE_STOP` | 23 | 18 (78%) | structure_stop 18, time_stop 4, ribbon_flip 1 |
| `ENTRY_CAT_CAP` | 22 | **6 (27%)** | premium_stop 6, time_stop 11, ribbon_flip 5 |
| `ENTRY_MAX_HOLD` | 22 | **3 (14%)** | max_hold 3, time_stop 11, ribbon_flip 8 |
| `RESTART_OPEN_POSITION` | 21 | 21 (100%) — by design, any stage counts | ribbon_flip 10, time_stop 11 |

**"9/9 branches GREEN" mostly means "a position opened and something closed it."** Three of
five live branches reach their designed exit under 30% of the time. This is a C7-class
coverage illusion: the dashboard is green on a property it is not testing.

Second-order: `time_stop` sits in `_ALWAYS_ACCEPTABLE_STAGES`. `time_stop` was the exact
bug fixed in the ladder today. If the *live* twin ever regressed to the SPY-shaped
default, this battery would grade the regression GREEN. (The live twin is currently clean:
64 lifetime `time_stop` closes, **last on 2026-07-27**, 8 days ago.)

### 1.4 Fix #2 — ladder `time_stop_et` (commit `41753b9c`): **ORGANICALLY PROVEN**

Proven, and the bug was bigger than the commit message said.

**The real bug window.** `exit_manager` closes when *now ≥ 15:50 ET*. On a 24/7 instrument
that predicate is true from 15:50 ET **until midnight ET**. Empirically confirmed — UTC
hours that ever produced a ladder `time_stop`: `[19,20,21,22,23,0,1,2,3]`; hours
`[4…18]`: **never**. That is an **8h05m/day dead zone — 34% of every day** in which no
ladder position could survive. Not a "15:50 bleed"; a third of the clock.

**Discriminating evidence that the fix works.** Both lanes entered `18:05:15Z` and were
still open past `20:00Z` — they rode straight through the `19:50Z` (15:50 ET) boundary
that would previously have force-closed them.

| | pre-fix | post-fix (≥13:55Z) |
|---|---|---|
| `LADDER_CLOSED` stages | time_stop **394**, structure_stop 81, ribbon_flip 33, trail 1 | structure_stop **21**, time_stop **0** |
| last `time_stop` in file | `2026-08-04T03:30:16Z` (before the fix) | — |

### 1.5 The ladder A/B — and the correction to my own re-baseline

⚠ **The `+1.1044% / +0.5745%` figures I put in commit `41753b9c` and in
`EOD-2026-08-03-TWIN.md` are a SURVIVORSHIP-FILTERED RECONSTRUCTION, not a clean
baseline. Do not cite them as corrected totals.**

| slice | variant | baseline |
|---|---|---|
| **C.** Pre-fix, `time_stop` excluded — *what I reported* ⚠ filtered | n=74 WR 23.0% **+1.1044%** | n=43 WR 4.7% **+0.5745%** |
| **A.** All history, `time_stop` excluded (incl. today) ⚠ filtered | n=84 WR 20.2% +0.7125% | n=54 WR 3.7% +0.1609% |
| **B.** **True post-fix window only** ⚠ **SMALL-n (n=10/11)** | n=10 WR **0.0%** **-0.3919%** | n=11 WR **0.0%** **-0.4136%** |

**Why C is not a baseline.** Excluding `stage == time_stop` does not remove a random
contaminant. Because the dead zone is a *time window*, the excluded rows are exactly
(a) the trades that lived long enough to still be open when it opened — **the
longest-held trades** — and (b) every trade entered inside it. The survivors are
conditioned on *short duration*. For a ladder whose thesis is that winners need time,
that filter removes the population the strategy exists to capture. Full reasoning:
`strategy/candidates/_lesson-inbox/excluding-buggy-rows-is-a-conditioned-filter-2026-08-04.md`.

**What can honestly be said today:** n=10/11 is far too small for a verdict, and both
lanes being 0% WR is consistent with the whole instrument having a bad day (§1.1). The
variant-vs-baseline question is **UNRESOLVED pending clean forward data**. The right next
step is to **re-simulate** the affected span under fixed code (the ladder sim is
deterministic on stored bars) rather than keep filtering output.

### 1.6 Discarded bear signals — the standing perps question, quantified

`SKIP_NO_SHORT_CRYPTO`: **684 lifetime / 80 today**. Deduped at 10-minute spacing:
**83 lifetime episodes / 6 today.**

**⚠ ORACLE / HINDSIGHT — not live-executable (Alpaca crypto is long-only). Never mix into
a live column.** Short P&L proxy = −(forward return), gross and net of a round-trip spread
estimate. Median one-way spread at signal **0.1648%** → round-trip **0.3296%**.

| horizon | n | GROSS mean | GROSS WR | NET mean | NET WR |
|---|---:|---:|---:|---:|---:|
| 15 min | 83 | -0.0212% | 41.0% | -0.3753% | 4.8% |
| 30 min | 83 | -0.0260% | 38.6% | -0.3802% | 6.0% |
| 60 min | 83 | -0.0328% | 43.4% | -0.3869% | 6.0% |
| 180 min | 83 | -0.0176% | 42.2% | -0.3717% | 19.3% |
| 360 min | 83 | +0.0457% | 49.4% | -0.3084% | 27.7% |

**Answer: there is nothing being left on the table.** Gross mean is -0.03%…+0.05% with
WR 39–49% across every horizon — statistically indistinguishable from a coin flip *before
any cost*. The spread then makes it decisively negative.

This matters for the perps question specifically: **a tighter venue does not rescue it.**
The net column is bad because of spread, but the *gross* column shows no edge to recover
in the first place. On the evidence, "we can't short crypto" has cost the twin nothing,
and a perps venue would be solving a cost problem that sits underneath a non-existent
signal. **Recommend: close the standing perps question as NOT-WORTH-PURSUING on current
evidence, and re-open only if the bear detector's gross edge turns positive.**

---

## 2. Instrument health

**Framing that must not be skipped:** this audit began at **16:07 ET**. The EOD cascade
runs **16:15 → 17:35 ET**. Several instruments named in the brief had *not yet fired* at
first check — that is scheduling, not failure. Results below are re-checked; anything
still unfired at write time is labelled.

| instrument | fired today? | result | finding |
|---|---|---|---|
| `Gamma_CryptoTwin` | ✅ 1-min all day | rc=0, 1200/1199 ticks, 100.0% uptime | GREEN |
| `Gamma_TwinSentinel` | ✅ 15-min | rc=0, verdict GREEN, 0 incidents | GREEN |
| `Gamma_LiveWatch` | ✅ 16:06 ET | rc=0, `market_state=CLOSED`, idle marker, no per-minute churn | **Working as designed** |
| `Gamma_ThetaClock` | ✅ 16:00 ET | rc=0, 560 rows, 20 position-instances | ⚠ **greeks still 100% unavailable** — see below |
| `Gamma_TradeAutopsy` | ✅ 16:15 ET | rc=0 | GREEN |
| `Gamma_MondayVerify` | ✅ 16:15 ET | rc=0 | GREEN (registered daily, self-gates) |
| `Gamma_EodBrief` | ✅ 16:20 ET | rc=0 | GREEN |
| `Gamma_WinnerAutopsy` | ✅ 16:25 ET | creds fix **PROVEN**; population run 35/35 scored, `sufficient_n` TRUE; pain-ledger + fill-latency chained clean | GREEN — only the *same-day probe* is bar-starved; see below |
| `Gamma_GateExpiryCheck` | ✅ overnight 01:00 ET | rc=0, 23 gates scored | GREEN (findings are gate-level, not instrument-level) |
| `Gamma_ViolinMetric` | ❌ **not yet** — fires 17:35 ET | last scheduled fire 00:39 ET covered the **08-03** session | answered read-only instead: `intraday_rth_high` **28.6% → 75.0%**, latency **9.1 m → 0.0 m** — see below |
| `Gamma_RiskyDivergenceWeekly` | n/a — not due | **State=Ready**, next **Sun 2026-08-09 17:00 ET**, rc=267011 (*never run*) | ✅ **registered correctly** |

### 2.1 ThetaClock — greeks still 0%, and the denominator it prints is stale

Today was the test case the brief asked for: ~20 real positions. Result:

- 560 rows, **20 distinct (arm, symbol) position-instances**.
- `greeks_raw` non-null: **0**. `greeks_source`: `unavailable` on **560/560** rows.
- Every decomposition is `sqrt_time_decay_model_est`, self-labelled *"textbook ATM
  extrinsic~sqrt(T) heuristic, NOT fitted/validated"*.

So the Alpaca options-snapshots feed returned empty on a day with 20 real positions across
5 arms — the streak is unbroken. **But the module reports the streak as "29/29 real entries
to date", and that string is hardcoded in the docstring rather than counted.** With today's
20 the true figure is **≈49/49**. An instrument that under-reports its own failure count
will keep looking like a small known gap instead of a settled verdict.

**Recommend:** either make the counter live, or stop calling the feed and rename the
source honestly to `closed_form_est` — 49 consecutive empties is not a transient.

### 2.2 WinnerAutopsy — creds fix PROVEN, instrument HEALTHY; only the same-day probe is blind

⚠ *Self-correction: my first read of this instrument, taken at 16:21 ET, was of the
**same-day probe** and I was about to report the instrument as starved. The **16:25 ET
population fire then landed and contradicted that**. The corrected reading is below; the
premature version is not the finding.*

**Creds fix: PROVEN** — and proven twice over.

**The 16:25 ET population run is healthy on every axis:**

```
scope: "all winners to date"      generated_at: 2026-08-04T16:25:02
n_winners_found: 35 · n_winners_scored: 35 · n_no_bars: 0 · sufficient_n: TRUE
realized_total: $8,748.00 · best_policy: trail_only_no_tp1 → $27,848.50
capture_vs_best_policy: 31.4% · attribution_pct: 80.9% (68 legs, 13 unattributed)
pain_ledger: n_positions 190, n_scored 189, n_no_bars 0 (floor 148 ✅)
```

It also chained its folded-in dependents correctly: the pain-ledger rebuild
(`analysis/pain-ledger/mae-mfe.json`, 189/190 scored) and the fill-latency decomposition
(21 entry fills, 0 excluded) both ran clean.

**The real, narrower finding — today's winners are not in that population yet.** The
same-day probe at 16:21 ET (`scope: 2026-08-04`) returned:

```
n_winners_found: 10 · n_winners_scored: 1 · n_no_bars: 9 · sufficient_n: false
```

Today's OPRA 1-min bars are not cached at 16:2x ET, so **9 of the 10 winners from the
best P&L day on record are absent from the capture-rate population** until those bars
land. The instrument is not broken; its same-day view is structurally blind by
sequencing.

**Credit where due — the disclosure chain is correct end-to-end.** The probe report leads
with *"n=1 < 8 — ANECDOTE, not a statistic"* and *"9 winning position(s) had NO OPRA bars
available and are absent entirely (never zero-filled)"*; `sufficient_n:false` is written to
the JSON; and the consumer gates on it (`firm_brief.py:537` appends
`⚠ ANECDOTE (n below floor)`). **Coverage gap, not a false claim** — C7 discipline working.

**Recommend:** confirm tomorrow that today's 9 winners get absorbed once their bars cache.
If they do, this is self-healing and needs no fix. If they do not, the highest-P&L day of
the program never enters the population, and a next-day backfill pass is required.

**Worth passing to the exits lens** (from the same population run, n=35, `sufficient_n`
true — descriptive only, ratifies nothing): of **21 scaled-out winners, 13 had the runner
finish BELOW TP1**, 9 with material giveback, **median runner giveback 21.3%**. And the
best fixed policy over the winner population is `trail_only_no_tp1`. That is a direct,
population-level restatement of J's standing "stay in longer, or get better exits?"
question — with the standing caveat printed on the report itself that a winners-only
sample cannot support an exit change without a full-population pre-registered A/B.

**One observation flagged, not claimed** (fill-latency rows, today): `bar_close_ts →
core_verdict_ts` ran **427–604 s** and `core_verdict_ts → signal_written_ts` a further
**55–58 s**, giving ~**486–670 s total bar-close-to-fill**. Broker-side latency is
negligible (submit→fill ≈ 0.1–0.3 s) — essentially all of it is upstream of the broker. I
have **not** verified what the intended entry-bar convention is, so this is not being
called a defect; it is handed to whoever owns the fill pipeline as a number worth
explaining.

### 2.3 ViolinMetric — coverage DID move, and it moved exactly where the IEX tail aimed

**Fire status:** the scheduled organic fire is **17:35 ET and had NOT run at write time**
(last scheduled fire 00:39 ET, covering the 08-03 session, which ran mostly *before* the
IEX tail shipped on 08-03 evening). Rather than stall the report, I computed today's
session **read-only** (`violin_metric.py --dates 2026-08-04`, no `--write`, so tonight's
scheduled artifact is untouched). Tonight's fire should reproduce these numbers.

| source | 08-03 (pre-tail) | **08-04 (post-tail)** |
|---|---|---|
| **`intraday_rth_high`** | **28.6%** (2/7), median latency **9.1 m** | **75.0%** (6/8), median latency **0.0 m** |
| `intraday_swing_high` | 75.0% (3/4) | 83.3% (5/6) |
| `intraday_swing_low` | 100% (5/5) | 83.3% (5/6) |
| `intraday_rth_low` | — (not present) | 0.0% (0/1), latency 19.1 m |
| overall | 75.0% (21/28) | 76.2% (16/21) |

**Verdict: yes, on the metric that mattered.** `intraday_rth_high` was the worst source in
the pre-tail session (28.6%, 5 misses at 9–34 min latency) and is the one the IEX tail was
built to fix. It went **28.6% → 75.0% with median latency 9.1 m → 0.0 m** — misses now
land at the tick, not ten minutes late.

⚠ **Read the headline number with care, and do not quote the overall delta.** Overall
coverage barely moved (75.0% → 76.2%) and that comparison is **apples-to-oranges**: the
08-03 session included `premarket_high`, `premarket_low` and `daily_context_shelf` levels
that are absent today, so the source mix differs. The like-for-like per-source
`intraday_rth_high` row is the honest evidence. Both sides are **a single session each** —
this is one clean directional datapoint, not a validated improvement. `intraday_rth_low`
at 0/1 is n=1 noise, worth watching, not worth acting on.

### 2.4 Nothing failed silently

No instrument in scope returned a non-zero exit code today. The two disabled/never-run
codes seen (`267011` = *task has not yet run*, `267014` = *task terminated by user*) belong
to `Gamma_RiskyDivergenceWeekly` (correct — not due until Sunday) and to long-disabled
legacy tasks (`Gamma_Grind_all`, `Gamma_FuturesEod`, `Gamma_Grind_Vwap`,
`Gamma_FuturesPremarket`).

---

## 3. My own process, audited

Three lesson-inbox items written. Two were assigned; **the third I found by auditing my own
commit from this morning, and it is the most serious.**

### 3.1 The 09:57 defect call — and the retraction

→ `strategy/candidates/_lesson-inbox/intra-session-defect-call-evidence-threshold-2026-08-04.md`

I called a shipped setup "a defect losing money" on **11 minutes of intra-session realized
P&L** and said I would stage `RUN_VWAP=False`. The full day: `VWAP_CONTINUATION` finished
**10 legs, +$721.00**. The fifth fire of the very cluster I was alarmed about became the
trade of the day.

**Root cause of the bad call:** an 11-minute realized-P&L window is not a small sample, it
is a **censored** one — and the censoring correlates with sign, because losers resolve fast
and winners resolve slow. Four sub-2-minute losses plus one 7-minute-old open position is
what a *working* continuation setup looks like at minute 11.

**The retraction was also not a good process step:** I withdrew on judgment without stating
a threshold, so the next session inherits nothing.

**Proposed evidence bar for any mid-session revert proposal** — one of:
1. **a MECHANISM defect** (wrong side/instrument, gate ignored, entering while not flat,
   sizing past cap) — verifiable in one tick, needs no n. *Only same-day-actionable trigger.*
2. **a kill-switch / risk-cap breach** — already deterministic under Rules 5/6.
3. **otherwise: no mid-session action**; P&L-based disarm waits for the close and goes
   through the setup's own pre-registered kill criterion.

Corollary: censored-window P&L must never be quoted to J as a verdict during RTH; if
mentioned, label **PARTIAL/CENSORED** with the open-position count. Rule 9 already forbade
the *action* — the gap is that it did not stop me forming and voicing the *conclusion*.

### 3.2 "Validated" vs "live-exercised" — and a nuance that makes yesterday's claim worse

→ `strategy/candidates/_lesson-inbox/backtest-validated-is-not-live-exercised-2026-08-04.md`

Yesterday I called the vwap lane "a validated edge" when its emitter had been import-dead
since 2026-06-25 (zero rows in 3,865). **Auditing it today surfaced something I had not
known and did not report:**

`vwap_continuation` was **not** a setup with no live history. On the CORE lane it had
**7 real fills, 0% WR, -$204** (07-16, 07-21, 07-22) and was **DISARMED 2026-07-25**,
J-approved, for exactly that record (`params.json#_extra_setup_exec_armed_disarm_doc_2026_07_25`
— and the arithmetic reconciles exactly against `journal/trades.csv`).

So the honest framing is neither "first ever live" nor "validated edge". It is: *a setup
name disarmed on one lane for 0/7 and -$204 was re-activated on a different lane in a
different risk shell and had a good first day (+$721).* That may be entirely legitimate —
different arm, different strike tier, different exits, and C29 says cells do not transfer
across strike tiers — **but I omitted a directly relevant negative prior.**

Proposed rules:
- **(a) three-state vocabulary, never collapsed:** VALIDATED (backtest) / ARMED (config) /
  **EXERCISED (a real broker fill)**.
- **(b) first-live shadow session** for any never-exercised path — *flagged as a genuine
  trade-off, not a recommendation*: it costs a live learning day and cuts against J's
  standing "on paper, bias toward TAKING the trade". Decide explicitly.
- **(c) lane-blind provenance check — ship it, no trade-off:** before calling any setup
  new/first-live, grep the setup NAME across `journal/trades.csv` and every disarm doc, and
  quote any prior live record including a negative one. Cheap, mechanical, would have caught
  this outright.

### 3.3 (Self-found) My "corrected" ladder A/B was survivorship-filtered

→ `strategy/candidates/_lesson-inbox/excluding-buggy-rows-is-a-conditioned-filter-2026-08-04.md`

Covered in §1.5. The pattern to encode: **when a bug is found in a producer of historical
results, you may not silently drop the affected rows and call the remainder a baseline.**
Characterize the bug's *selection function* first; if it correlates with outcome, exclusion
is biased. Report reconstruction and true post-fix separately, always labelled. Prefer
**re-running** the producer to filtering its output. Never call a filtered reconstruction
"corrected."

Honest note on how this happened: I verified the *fix* to engineering standard (guard test
RED-proofed by live revert-and-rerun) and then treated the re-baseline as bookkeeping. It
was statistics. I also did not run `/fable-too-good` on a re-baseline that turned a bug
into two positive lanes — which is precisely the shape that protocol exists to catch.

### 3.4 Any OTHER armed setup that has never executed live? — **YES, one**

Swept every setup name in `journal/trades.csv` (276 legs, all history) against every
arming key in `automation/state/params.json`.

| armed setup | armed? | live fills, all history | verdict |
|---|---|---|---|
| `BEARISH_REJECTION_RIDE_THE_RIBBON` | ✅ | 62 legs | exercised |
| `BULLISH_RECLAIM_RIDE_THE_RIBBON` | ✅ | 161 legs | exercised |
| `bollinger_squeeze` | ✅ true | 8 legs, 5 dates, **+$104** | exercised |
| `vwap_reclaim_failed_break` | ✅ true | 2 legs (07-21, 07-28), -$15 | exercised (thin) |
| **`double_bottom_base_quiet`** | ✅ **true** | **0 legs** | 🚩 **NEVER EXECUTED LIVE** |
| `vwap_continuation` | ❌ false (core) | 12 legs | disarmed 07-25 |
| `vix_regime_dayside` | ❌ false | 5 legs, -$153 | disarmed 07-25 |

**`double_bottom_base_quiet` has been `exec_armed=true` since the 2026-07-01 trade-to-learn
batch — 34 days — and has produced zero live fills.**

⚠ *Second self-correction: my first pass called it "fired at most once and never converted."
That was wrong, and the true mechanism is more interesting.* Sweeping
`extra_setup_placed` across every `fill-funnel-*.json`:

| armed extra setup | dispatch outcomes | days fired | PLACED | why it died |
|---|---:|---:|---:|---|
| `bollinger_squeeze` | 60 | 9 | **20** | healthy — SKIP_LATE_ENTRY 22, VETOED_BY_MODELS 8 |
| `vwap_continuation` | 133 | 5 | 3 | WATCH_NOT_ARMED 93 (core disarmed 07-25) |
| `vwap_reclaim_failed_break` | 10 | 2 | 1 | STALE_SIGHT 4, COOLDOWN 4, veto 1 |
| **`double_bottom_base_quiet`** | **10** | **1** (07-30) | **0** | **VETOED_BY_MODELS 6 · RISK_DENY_RISK_CAP 4** |
| `gap_and_go` | 20 | 4 | 0 | WATCH_NOT_ARMED 20 ✅ *by design* |
| `level_break_first_strike` | 15 | 2 | 0 | WATCH_NOT_ARMED 15 ✅ *by design* |

**The corrected diagnosis: the detector is ALIVE, not import-dead.** It fired **10 times in
one session** (2026-07-30) and **every single fire was killed downstream** — 6 by the
free-model veto, 4 by the risk cap. It has not fired on any other funnel-covered day.

So this is *not* the vwap_continuation failure mode (dead emitter, zero signals). It is a
distinct one: **a rare detector whose only firing day was 100% blocked by gates.** Same
end-state (armed, never exercised), completely different fix. Two things are worth pulling
on, neither of which I can settle here:

- **The risk-cap half is probably the known sizing deadlock, not this setup's fault.** The
  same funnel is full of `safe: notional $XXX exceeds per-trade cap $348 (30% of $1,160)`
  on that date — the account was small enough that most things were sized out. All five
  arms are now $5K-class, so this half may already be resolved.
- **The model-veto half deserves a look on its own.** 6 of 10 fires vetoed on this setup,
  plus 8 of 60 on `bollinger_squeeze`. Per OP-32's free-model trust gate, a veto lane that
  is the sole reason a validated setup has never traded is exactly what
  `free_model_audit.py` exists to grade.

**Recommend:** re-classify `double_bottom_base_quiet` from "armed strategy" to
**ARMED-BUT-NEVER-EXERCISED**, and route it to the free-model audit rather than disarming
it — 0 fills across 34 days is not evidence against the setup, it is evidence that nothing
downstream has ever let it try.

Correctly handled by contrast, and worth stating so the sweep isn't misread: `gap_and_go`
(`gap_and_go_enabled=true`) and `level_break_first_strike` (`j_lbfs_enabled=true`) both have
their exec-arm key **deliberately ABSENT** → 100% `WATCH_NOT_ARMED` across 20 and 15
dispatches respectively, documented in `setup/scripts/setup_dispatch.py`. Those are
documented shadows behaving exactly as specified, not silent gaps.

---

## 4. Cost + git hygiene

### 4.1 Cost — and the number that must not be misread

**Today: `total=$275.97` notional** (Claude $275.92 · MiniMax $0.05 · Groq $0.00).

⚠ **This is NOT a bill.** `spend_summary.py` prices Claude Code token usage at Anthropic
public API rates as a **rate-limit-pressure proxy**; the work runs on the flat Max
subscription, so **actual marginal cost is $0**. The module says so itself: *"A high $-day
doesn't cost J extra (Max is flat), but it predicts the next rate-limit hit."*
(Stale-doc nit: that docstring still says `$100/mo`; CLAUDE.md records the 2026-06-24
upgrade to $200/mo Max 20x.)

| date | notional total | opus share |
|---|---:|---:|
| 07-31 | $125.97 | 50% |
| 08-01 | $266.03 | 76% |
| 08-02 | $277.25 | 80% |
| 08-03 | $187.37 | 46% |
| **08-04 (today, partial)** | **$275.97** | **86%** |

**Today is at the top of the recent band and the most opus-heavy day in it** — opus
$238.21 of $275.92 across 106 messages vs sonnet's 337. Against CLAUDE.md §1 (*top tier =
judgment only; Sonnet = the workhorse; big-model tokens are for JUDGMENT, never mechanical
execution*), **86% opus is a routing signal worth flagging**, even at $0 marginal cost,
because rate-limit pressure is shared with the heartbeat. Today's fan-out was large and
opus-tier; the doctrine-conforming shape is Opus writes the spec, Sonnet runs it.

### 4.2 Git hygiene

- **Stashes: ZERO** ✅ (`git stash list` empty — L238 respected).
- **Unpushed commits: 49** (16 of them today). Not pushed — per instruction, the
  orchestrator audits and pushes.
- **Working tree: 178 modified / 1,568 untracked.** Modified is dominated by
  `automation/state` (86) — expected operational churn.

🚩 **L242/L252-class recurrence found — `analysis/manager/`:**

```
tracked:   77 files
untracked: 550 files          (NOT gitignored)
oldest untracked: 2026-06-27  newest: 2026-08-01
last commit touching the dir: 621f1380  (2026-06-26)
```

The directory **is** tracked and **is not** ignored, yet nothing in it has been committed
in **39 days** while 550 files accumulated. This is precisely L242's shape (1,176
`strategy/candidates/` files sitting `git add`-less for weeks) — and precisely L252's
warning that *a detector without an automatic remediator re-violates on its own schedule*.
`auto_commit_candidates.py` was built as the remediator for `strategy/candidates/` **only**;
`analysis/manager/` is the same disease with no remediator pointed at it.

**Recommend:** extend `auto_commit_candidates.py`'s pathspec set (or clone the pattern) to
cover `analysis/manager/` and any other tracked-but-uncommitted analysis directory, then
re-run the L242 detector across *all* tracked dirs rather than the one it was born on.

Minor untracked junk worth clearing (reported, not deleted): a literal file named `NUL` at
repo root (a Windows artifact from a bash `> NUL` redirect — on Windows that creates a real
file instead of discarding), `_pytest_guards2.txt`, and editor dirs `.claudian/` /
`.obsidian/` which should probably be gitignored.

---

## 5. Open items handed forward

| # | item | owner |
|---|---|---|
| 1 | Twin rapid-re-entry bleed (10 straight `structure_stop` losses) as **mechanism** corroboration for the SPY 7×-re-entry adjudication | SPY re-entry lens |
| 2 | `ENTRY_MAX_HOLD` live path still unexercised — next natural exercise is tonight's forced sweep (~20:07 ET); verify a `max_hold` `EXIT_FILLED` with `entry_price` appears | next session |
| 3 | Coverage battery grades preemption as GREEN — tighten `_ALWAYS_ACCEPTABLE_STAGES`, or report designed-stage-hit-rate alongside GREEN | build |
| 4 | Re-simulate the ladder's affected span under fixed code instead of filtering `time_stop` rows out | build |
| 5 | `double_bottom_base_quiet`: armed 34 days, 0 fills — detector ALIVE (10 fires, 1 day), 100% killed downstream (6 model-veto + 4 risk-cap). Re-classify ARMED-BUT-NEVER-EXERCISED; route the veto half to `free_model_audit.py`, re-check the risk-cap half now arms are $5K-class | build |
| 6 | ThetaClock: 49/49 empty greeks; make the counter live or rename source to `closed_form_est` | build |
| 7 | Confirm tomorrow that today's 9 unscored winners get absorbed once OPRA bars cache; if not, add a next-day backfill pass | next session |
| 7b | Runner cohort (n=35 population): 13 of 21 runners finished BELOW TP1, median giveback 21.3%, best fixed policy `trail_only_no_tp1` — feed to the exits lens as population-level input to J's "longer vs better exits" question | exits lens |
| 7c | Explain ~486–670 s bar-close→fill latency (all upstream of broker); verify against intended entry-bar convention | fill-pipeline owner |
| 8 | Confirm tonight's 17:35 ET ViolinMetric fire reproduces the read-only numbers (`intraday_rth_high` 75.0%, latency 0.0 m); accumulate more sessions before calling the IEX tail validated | tonight / next session |
| 9 | Extend L242 remediator to `analysis/manager/` (550 files, 39 days) | build |
| 10 | Perps question: recommend CLOSED as not-worth-pursuing (no gross edge in discarded bear signals) | J / doctrine |

**Nothing in this report changed a trading-path param, placed an order, or armed anything.**
Read-only analysis plus three lesson-inbox markdown files.
