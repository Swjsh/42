# Arm Participation and the Growth Path — 2026-08-03

**Written 2026-08-02, overnight into Monday 2026-08-03.** The weekend's other research
(FREQUENCY-CEILING / CAPITAL-EFFICIENCY / SIZING-SCALING-DECISION, all 2026-08-03)
exhaustively measured core Safe/Bold's SELECTION and SIZING axes on a 390-day *simulated*
population and found both near a ceiling. This document measures the axis nobody had
touched: PARTICIPATION — of the 5 live paper arms (safe-2, bold-2, safe-3, risky-1,
risky-3) trading off overlapping signal streams, how many of the signals each arm was
*configured* to take did it mechanically drop, and why. This is real, live decision-log
data (~5-6 weeks, 2026-06-21 → 2026-08-02), not a backtest replay. **Nothing is armed.
Nothing shipped.** Guards: 34 tests, RED-proofed live this session (§7).

**Scope discipline:** zero edits to any trading-path file. `heartbeat_core.py`,
`automation/state/fleet/*` code, `params.json`/`aggressive/params.json`, `exit_manager.py`,
`exit_actuator.py`, the option-pricing/exit-walk libs, and `journal/gex-archive/` were read
where cited, never modified. This document ships no trading change.

---

## Verdict first

- **The fleet's own real money, over the window this document actually has ledger data
  for, is NEGATIVE — not the ~$80/day the task's own hypothesis assumed.** Summed across
  each of the 5 arms' own live decision-ledger window (2026-06-21/25 → 2026-07-31/08-02,
  the ~5-6 weeks the current 5-arm architecture has existed): **-$1,187.00** real fills,
  combined. Only two of five arms (safe-2, risky-3) are net positive in that window; bold-2
  is the largest single drag (-$764.00 on just 4 real-fill days). Widening to each arm's
  own FULL real-fill history (safe-2's stretches back to 2026-04-29, well before the
  current fleet architecture existed) turns the total barely positive: **+$360.00** — the
  overwhelming majority of that is safe-2's older, pre-fleet track record, not the fleet
  as it exists today. **Five arms are not currently five independent sources of ~$16/day
  each — the honest current combined rate, this window, real fills, is close to zero or
  negative.** (§4)
- **Of 722 real signal-events that reached one of the 5 arms' own decision funnel this
  window, 108 (15.0%) became an order.** Of the other 614: **407 (56.4% of all signals)
  were refused by a DELIBERATE, already-validated mechanism** (a named production gate, an
  arm's own configured selectivity, Rule-4 one-position, PDT, quality-lock, the free-model
  veto) — working as designed, not a gap. **182 (25.2%) were refused by a mechanical
  friction that is plausibly fixable without touching the trading edge at all** — and 159
  of those 182 (87%, by far the largest single mechanism in this whole document) are ONE
  thing: the `$0.30` min-entry-premium floor colliding with the fleet's far-OTM/"bold"
  strike tables. **25 (3.5%) were lost to infrastructure noise.** (§1, §3)
- **The min-premium-floor collision is 89.5% concentrated on the CALL (bullish) side**
  across every arm that has it (221 of 247 blocked ticks), and core Safe (ATM strikes)
  shows ZERO min-premium-floor blocks in the same window — proving the mechanism is the
  STRIKE TABLE, not the floor itself (the floor is validated doctrine, ENTRY-1
  2026-07-09 — do not touch it). **The fix is already identified and PARTIALLY SHIPPED**
  (`strike_tier_table: bold_core`, ATM under $2K, landed for risky-1 and risky-3 on
  2026-08-01) — but 2026-08-01 was a Saturday and 2026-07-31 is the last real trading day
  in this dataset, so **there are zero live trading days of evidence on the fix yet.**
  safe-3 has NOT received the same fix and is still on the old OTM table. (§3.1)
- **A genuinely new finding this weekend's core-only sizing research missed:** the exact
  `$2,000`-tier deny-semantics deadlock `SIZING-SCALING-DECISION-2026-08-03.md` found for
  *hypothetical* core scaling is not hypothetical for the fleet arms — `fleet_executor.py`'s
  `position_sizing_tiers` wiring has been LIVE for safe-3/risky-1/risky-3 since inception.
  risky-3's own equity has round-tripped across the `$2,000` boundary at least twice this
  month (peaked `$2,352.43` on 07-29, currently `$2,121.61`). Raw dollar cost measured so
  far is small (12 risk_cap events fleet-wide), but the exposure is live, ongoing, and
  invisible until now. (§3.2)
- **The 2026-07-31 anecdote in the task brief is confirmed, precisely, against the raw
  ledger — with one correction.** safe-3 took 1, risky-3 took 2, both core arms took zero:
  exactly as stated. risky-1's "128 straight HOLDs" is also confirmed to the tick (128 raw
  ticks, verified) — but of those, 19 (not accounts.json's own prose estimate of 16) carried
  a real candidate, and every single one was on the call side, and every single one was
  refused by the risk gate (18 premium-floor, 1 risk-cap) — a clean, total, single-mechanism
  shutout, not a vague "no signal" day. **Both core arms ALSO took zero that day** despite
  10-11 signals reaching their own gates — 2026-07-31 was a fleet-wide low-participation
  day, not a risky-1-specific failure. (§2)
- **Growth model (§5): at the MEASURED rate, holding it flat (the proven regime below
  ~$5,000), the honest range to the $5,000 inflection is wide — roughly 40 to 500+ trading
  days depending on which arm and which window (risky-1's own thinnest positive cut implies
  512), and for bold-2 and several arms' other cuts, the model does not converge at all
  (rate ≤ 0).** Closing the participation gap (§3) is
  illustrated, not forecast, at +11 to +32 $/day per fleet arm — cutting the wide end of
  that range roughly in half, not transforming it. **There is no version of this model,
  honestly stated, that reaches $100-200/day on participation fixes alone before either
  equity compounds past the ~$5,000 sizing inflection or the underlying edge itself
  improves.** (§5, §8)

---

## 1. Method

**Instrument reused, not rebuilt** (repo's own C17 doctrine): `backtest/tools/
participation_cascade.py` — the existing, tested joint-gate-cascade tool built 2026-07-10
after J's "6 arms and nothing took a trade from over 700 signals" incident. It already
reconstructs every tick in `automation/state/core-decisions.jsonl` (safe-2/bold-2, keyed by
the row's `account` field) and `automation/state/fleet/<arm>/decisions.jsonl` (safe-3,
risky-1, risky-3) into terminal-classified, run-length-encoded SIGNAL EVENTS — consecutive
ticks sharing the same `(side, setup, stage, blocker)` identity collapse into one event, so
a 48-tick boring HOLD stretch is one event and a real, transient candidate is its own event.
This UNDER-counts rather than tick-inflates by design (see that tool's own docstring).

**What this document adds** (`backtest/tools/arm_participation_growth_2026_08_03.py`, new,
guard-tested):
1. Full-window aggregation — `participation_cascade`'s own CLI is per-day / trailing-N-day;
   this sums it across the ENTIRE available live-ledger history (33 calendar days
   discovered, 27 of them real RTH trading days with SPY 5-minute bar coverage).
2. A mapping from the tool's `(category, blocker, stage)` triples onto the task's own
   mechanism vocabulary: `gate` / `min_premium_floor` / `sizing_deadlock` / `not_flat` /
   `arm_disabled` / `no_signal_from_producer` / `risk_cap` / `pdt` (`mechanism_bucket()`,
   14 unit tests).
3. Real-$ aggregation from `journal/trades.csv`, summed **per calendar day, not per row** —
   the CSV logs partial TP1/runner legs as separate rows for one entry (verified: some
   `notes_short` fields explicitly describe multi-leg splits), so summing by row overstates
   distinct entries; summing by date is leg-count-safe regardless.
4. A day-count growth model (`days_to_target()`, order-of-operations, never a calendar
   date, per J's standing no-timeline-guesses rule) from today's LIVE-VERIFIED equity to
   the ~$5,000 flat-curve-to-scaling inflection `CAPITAL-EFFICIENCY-2026-08-03.md`
   identified.

**Window:** 2026-06-21 → 2026-08-02 (33 calendar days; 27 real RTH trading days — the
non-trading days that still appear are stray off-hours/weekend test ticks, disclosed not
hidden). This is the LONGEST window with real per-arm LIVE decision data — bounded by when
the current 6-account grid (`accounts.json` "GRID REBUILD 2026-06-25") and the fleet's own
ledgers (earliest row 2026-06-21) began, not an arbitrary cut. It is shorter than, and a
different KIND of evidence from, the 390-day *simulated* backtest population the weekend's
other three documents used — that distinction is preserved throughout, never blended.

**Verification performed this session (OP-33):**
- All 5 arms' current equity fetched LIVE via `fleet_broker.get_account()` (read-only
  `GET /v2/account`, the same tested primitive `heartbeat_core.py`/`fleet_executor.py` use)
  — not trusted from the task brief's own numbers. Matched to the penny on 4 of 5 (safe-2
  differed by $0.06, a timing artifact): safe-2 `$1,160.24`, bold-2 `$1,197.52`, safe-3
  `$1,967.81`, risky-1 `$1,756.87`, risky-3 `$2,121.61`.
- risky-1's 2026-07-31 "128 straight HOLDs" reconciled against the raw
  `automation/state/fleet/risky-1/decisions.jsonl` rows directly (not just the aggregated
  tool output) — see §2.
- `journal/trades.csv`'s `safe`-account total (`$1,228.00`, n=38) independently matches
  `CAPITAL-EFFICIENCY-2026-08-03.md`'s own citation of the same figure — a strong
  cross-document consistency check that the CSV parse (which has to route around ~26 of 223
  rows corrupted by unescaped quotes in the notes column, disclosed and skipped, not
  guessed at) is sound.

---

## 2. The five funnels

Each arm's own decision-log window, real RTH trading days only. "Passed scoring" = a real
candidate reached this arm's own decision funnel (cleared the shared/core scoring layer);
"orders" = PLACED or FILLED.

| Arm | Window | Signal-events reaching arm | Orders placed | Conversion | Days w/ ≥1 signal | Days w/ ≥1 order | Days: signal but ZERO orders |
|---|---|---:|---:|---:|---:|---:|---:|
| **safe-2** | 06-25 → 08-02 | 184 | 12 | 6.5% | 29 | 8 | **21** |
| **bold-2** | 06-25 → 07-31 | 173 | 7 | 4.0% | 25 | 6 | **19** |
| **safe-3** | 06-21 → 08-01 | 122 | 27 | 22.1% | 25 | 13 | **12** |
| **risky-1** | 06-21 → 08-01 | 119 | 24 | 20.2% | 25 | 11 | **14** |
| **risky-3** | 06-21 → 08-01 | 124 | 38 | 30.6% | 24 | 15 | **9** |
| **TOTAL** | — | **722** | **108** | **15.0%** | — | — | — |

**Fleet-wide, day-level (27 real RTH trading days, all 5 arms summed per day):**
- **7 of 27 real trading days (25.9%) saw ZERO entries from ANY of the 5 arms combined** —
  2026-06-22, 06-24, 06-25, 07-10, 07-14, 07-16, 07-22. Several of these were not quiet
  days: 06-24 (1.238% SPY range), 06-25 (1.322%), 07-10 (0.973%) all clear
  `participation_cascade.py`'s own 0.8% "tradeable day" threshold. **2026-07-10 is the
  exact incident that motivated `participation_cascade.py`'s original build** ("6 arms and
  nothing took a trade… on a $7 SPY trend") — this document's independent, wider-window
  measurement reproduces that known incident exactly, a real cross-check that the pipeline
  is faithful.
- 108 total order-events fleet-wide over 27 days = **4.0 entries/day, fleet-wide, split
  across 5 arms** — 0.8/arm/day on average, well below what "5 independent producers"
  implies.

**Per-arm mechanism breakdown (signal-events, EXCLUDING orders — i.e. of everything that
did NOT convert):**

| Mechanism | safe-2 | bold-2 | safe-3 | risky-1 | risky-3 | TOTAL |
|---|---:|---:|---:|---:|---:|---:|
| `gate_named` (production/cohort gates) | 91 | 131 | 2 | 2 | 3 | **229** |
| `min_premium_floor` | 0 | 5 | 48 | 50 | 56 | **159** |
| `not_flat` (Rule 4, one-position) | 14 | 9 | 11 | 11 | 22 | **67** |
| `gate_arm_selectivity` (this arm's own gate) | — | — | 29 | 28 | — | **57** |
| `other_block:vetoed_by_models` (free-model veto) | 14 | 8 | — | — | — | **22** |
| `execution_stale_trigger` | 18 | 3 | — | — | — | **21** |
| `gate_structure_veto` | 19 | — | — | — | — | **19** |
| `risk_cap` | 6 | 2 | 1 | 2 | 1 | **12** |
| `execution_place_fail` | 1 | 3 | 1 | 2 | 4 | **11** |
| `pdt` | 6 | 4 | — | — | — | **10** |
| `quality_lock` | 2 | 1 | — | — | — | **3** |
| other (log errors, one-offs) | 1 | — | 3 | — | — | **4** |
| **Blocked total** | **172** | **166** | **95** | **95** | **86** | **614** |

**Rolling this up into the task's own framing** (of 722 signals, not 614 — including the
108 that DID convert):

| Category | n signal-events | % of all 722 | What it means |
|---|---:|---:|---|
| **Converted to an order** | 108 | 15.0% | — |
| **By-design refusal** (named gates + arm's own configured selectivity + Rule-4 + PDT + quality-lock + model veto) | 407 | 56.4% | Working as intended — not a gap |
| **Mechanically fixable friction** (min-premium-floor/strike collision + risk-cap + broker place-fail) | 182 | 25.2% | **This is the actual, open gap** |
| **Infrastructure noise** (stale trigger, one-off log errors) | 25 | 3.5% | Small, not currently material |

**arm_disabled:** measured as zero ongoing impact. The only WATCH-mode (non-live)
placement rows found (~50-267 ticks per fleet arm) all date to the 2026-06-21 → 06-29
onboarding window, before the 2026-06-25 grid rebuild's arms went fully live, plus two
stray after-hours ticks on 2026-08-01 (a Saturday, both HOLD, zero missed entries). No
arm has sat disabled during a live RTH session in the measured window.

**sizing_deadlock (sub-classification of risk_cap):** `risk_gate.explain_block()`'s
`binding.deadlock` telemetry exists in the code (`backtest/lib/risk_gate.py`, added after
the 2026-07-30 incident) but was found **empty on every single row** of both
`core-decisions.jsonl` and all 3 fleet ledgers, this session — disclosed, not silently
assumed absent. §3.2 below establishes the mechanism is real and live for the fleet arms
specifically through a different, independently-verified route (the equity trajectory
itself), not through this telemetry field.

---

## 2.1. The 2026-07-31 spotlight, verified against the raw ledger

| Arm | Signals reaching arm | Orders | What blocked it |
|---|---:|---:|---|
| safe-2 | 10 | 0 | 9 named-gate blocks, 1 stale-trigger |
| bold-2 | 11 | 0 | 10 named-gate blocks, 1 stale-trigger |
| safe-3 | 11 | **1** | 10 risk-gate denies (mostly premium floor), 1 filled |
| risky-1 | 10 | **0** | 10 risk-gate denies, 0 filled |
| risky-3 | 12 | **2** | 10 risk-gate denies, 2 filled |

Matches the task's own citation exactly (safe-3=1, risky-3=2, both core=0). risky-1's raw
tick count for that day: **128, verified directly against
`automation/state/fleet/risky-1/decisions.jsonl`** (not just the aggregated tool). Of those
128: 106 were genuine no-signal ticks, 3 were a signal-feed read error (`signal_unreadable`,
infra), and **19 carried a real candidate — all 19 were side=C (calls) — and all 19 were
refused by the risk gate (18 by the $0.30 min-premium floor, 1 by the 50% risk cap).**
`accounts.json`'s own risky-1 doc estimates "15 of 16 named-setup ticks" for this same day
— close, not exact (19 vs 16); this document's count is a fresh, direct re-derivation and
should be preferred going forward, but the two readings agree on the qualitative point:
**the premium floor was the total, single-mechanism cause of risky-1's shutout that day.**
**Both core arms ALSO shut out entirely** despite 10-11 signals each reaching their own
(different, already-studied) gate cascade — 2026-07-31 was a fleet-wide quiet day, and
risky-1's zero was not a uniquely broken arm, it was the SAME mechanism (§3.1) other
studies have already flagged as the fleet's #1 friction, caught in the act on one specific
day.

---

## 3. The participation gap, ranked and priced

### 3.1. #1 — `min_premium_floor` × far-OTM strike selection (159 events, 87% of the fixable gap)

**Mechanism, fully traced:** the fleet's `safe-3`/`risky-1`/`risky-3` price entries off the
"bold"/OTM-2/OTM-3 strike tables (`_tiers_for_arm`), which routinely produce sub-`$0.30`
contracts — refused by the `min_entry_premium` floor BEFORE `risk_gate.check_order` ever
runs (`fleet_executor.py`'s `finalize()`, checked ahead of sizing). Core Safe (ATM strikes)
shows **zero** min-premium-floor blocks in the same window — the floor itself is not the
problem (it is validated doctrine, ENTRY-1 2026-07-09: sub-$0.20 fills are a documented
toxic cohort, ~2-tick stops reading spread noise not price — **do not weaken it**). The
problem is exclusively that the fleet's OTM strike tables collide with it. **89.5%
concentrated on the call side** (221 of 247 blocked ticks fleet-wide) — a real, new,
cross-arm-confirmed asymmetry: far-OTM 0DTE SPY calls at these specific offsets price
under $0.30 far more often than puts do at the same distance.

**Fix status:** already identified and PARTIALLY shipped. `params_patch.strike_tier_table:
"bold_core"` (resolves `V15_BOLD_CORE_TIERS`, ATM under $2K — the same table core Bold has
used since 2026-07-17/18) landed for **risky-1 and risky-3 on 2026-08-01**, pre-registered
(`analysis/recommendations/fleet-strike-tier-atm-extension-prereg-2026-08-01.json`).
**safe-3 has NOT received it** — still on the plain "bold" OTM table, and its 48
min-premium-floor events are the single largest unaddressed bucket in this whole document.

**Evidence status:** 2026-08-01 was a Saturday; 2026-07-31 is the last real trading day in
this dataset. **Zero live trading days of evidence exist yet for the risky-1/risky-3 fix.**
This document does not, and should not, claim a validated $ improvement. An illustrative
(not forecast) bound: if even half of a fleet arm's own blocked-by-floor events over this
~27-day window had cleared and traded near core Safe's own validated $33.35/trade rate (the
closest existing real analog to what an ATM-priced fleet entry would look like), that is
roughly **24 events × $33.35 ≈ $800 over 27 days ≈ $30/day, spread across the arm** — an
order-of-magnitude sanity check, not a prediction. **The correct next step is not another
backtest guess — it is watching the next 10-15 real trading days under the already-shipped
fix, and extending the same fix to safe-3**, which is a one-line `params_patch` change
mirroring risky-1/risky-3's own, already-precedented twice.

### 3.2. #2 (new this session) — the live `$2,000`-tier sizing deadlock, already active on the fleet

`SIZING-SCALING-DECISION-2026-08-03.md` (this same weekend) found that porting fleet's
own `position_sizing_tiers`/deny-semantics mechanism into CORE would be actively harmful
right at the `$2,000` boundary (qty jumps from `min_contracts` to a bigger tier, which
*tightens* the per-contract premium ceiling under a fixed dollar cap, and denies the
majority of the opportunity set) — but concluded core itself is *currently inert* below
`$2,000` because core never had this mechanism wired at all.

**That "currently inert" finding does not apply to the fleet arms — they have had this
exact mechanism live since inception** (`fleet_executor.plan_entry` → `_qty_for`, reading
the SAME `position_sizing_tiers` tables, gated by `lo <= equity < hi` on live, per-tick
equity). **risky-3's own equity has round-tripped across the `$2,000` line at least twice
this month** (crossed up 2026-07-02, back down through most of July, up again 2026-07-29
to a peak of `$2,352.43`, currently `$2,121.61`) — meaning its position size has been
silently flipping between the `[0,2000)` tier (qty 5) and the `[2000,10000)` tier (qty 8
base / 12 elite) tick to tick, exactly the mechanism that produced a 96% P&L collapse in
that document's own controlled test at Safe's equivalent boundary.

**Measured dollar cost so far: small** — only 12 `risk_cap` events fleet-wide this whole
window (safe-3 1, risky-1 2, risky-3 1, plus core's own 6+2). This is NOT yet the dominant
lever. It IS a live, ongoing, previously-invisible structural exposure that will bind
harder as any of these 3 arms compounds further past `$2,000` — exactly the band
`SIZING-SCALING-DECISION` calls "the first equity band either account will actually
reach," except for the fleet arms that band is not a future hypothetical, it is today.
**Recommendation: apply that document's own recommended fix (shrink semantics — clamp a
too-big tiered qty down to the largest affordable size, never deny outright — the SAME
clamp `heartbeat_core.py:1964-1967` already carries as dead code) to `fleet_executor.py`'s
`_qty_for` call site too, before any of the 3 fleet arms compounds meaningfully further.**
This is a measurement finding, not a shipped fix — flagged for the next building session.

### 3.3. Everything else, briefly

- **`not_flat` (67 events, Rule 4 one-position)** — not a bug. This is the rule doing its
  job. Excluded from "the gap."
- **`gate_named` (229) + `gate_structure_veto` (19) + `other_block:vetoed_by_models` (22) +
  `pdt` (10) + `quality_lock` (3)`** — core Safe/Bold's OWN production doctrine, already
  exhaustively re-examined THIS SAME WEEKEND at a 390-day sample
  (`FREQUENCY-CEILING-2026-08-03.md`), which found most gates independently load-bearing
  and net-positive-or-neutral to keep. Not re-litigated here.
- **`gate_arm_selectivity` (57, entirely safe-3 + risky-1's pre-2026-07-31 config)** — a
  DELIBERATE selectivity choice (the "safe x tight" grid cell), not a mechanical accident.
  safe-3's own real fills sit near breakeven (-$22 total) despite this extra filtering —
  worth a future A/B (does the tight gate earn its keep?) but not an obvious "fix."
- **`execution_place_fail` (11) + `execution_stale_trigger` (21)** — small, and the
  largest chunk of stale-trigger events (18 of 21, on safe-2) date to the
  2026-06-25 → 2026-07-10 GATE-PROVENANCE-SWEEP era, already fixed in the code (per that
  audit's own commit trail) — legacy noise, not an ongoing drag.
- **`arm_disabled`** — measured at zero ongoing cost (§2).

---

## 4. What the fleet actually made (real fills, leg-count-safe)

| Arm | Ledger-window real $ | Real-fill days in window | Full-history real $ | Full-history days | Full-history range |
|---|---:|---:|---:|---:|---|
| safe-2 | -$319.00 | 6 | **+$1,228.00** | 14 | 2026-04-29 → 07-28 |
| bold-2 | -$764.00 | 4 | -$764.00 | 4 | 2026-07-17 → 07-28 |
| safe-3 | -$22.00 | 13 | -$22.00 | 13 | 2026-06-29 → 07-31 |
| risky-1 | -$228.00 | 11 | -$228.00 | 11 | 2026-06-29 → 07-29 |
| risky-3 | +$146.00 | 15 | +$146.00 | 15 | 2026-06-29 → 07-31 |
| **TOTAL** | **-$1,187.00** | — | **+$360.00** | — | — |

**Reading this straight:** the "ledger-window" column is the fairest apples-to-apples
comparison (all 5 arms, the same ~5-6 week era the current architecture has existed) and it
is **negative**. safe-2's full-history column is positive only because it includes 7 real
days from 2026-04-29 → 05-14 that predate the current fleet architecture entirely (J's own
early, pre-rules, hand-picked trades — see §5's recency split). **The task's own
hypothesis — "five arms each producing ~$16/day would be ~$80/day" — does not hold up
against real fills.** Real, measured, fleet-wide output over the era that matters is closer
to flat-to-negative than to $80/day.

---

## 5. The growth-path model (Regime 1 — flat curve, below ~$5,000)

`CAPITAL-EFFICIENCY-2026-08-03.md` proved the $/trade rate is FLAT with equity below
~$5,000 for core (sizing never scales past `min_contracts` there) — so this regime is a
**linear runway** (`dollar_needed / measured_rate`), not compounding. Per J's standing
no-timeline-guesses rule: **trading days at the measured rate, never a calendar date.**
Every rate below is real, live-verified, and thin — presented as three cuts (full window /
early half / recent half of REAL fills only), never collapsed to one point estimate.

| Arm | Live equity (verified) | $ to $5,000 | Full-window rate | Early-half rate | Recent-half rate | Days @ full | Days @ recent |
|---|---:|---:|---:|---:|---:|---:|---:|
| safe-2 | $1,160.24 | $3,839.76 | +$87.71/day (n=14) | +$331.00/day (n=7) | **-$155.57/day (n=7)** | 44 | **never (rate < 0)** |
| bold-2 | $1,197.52 | $3,802.48 | **-$191.00/day (n=4)** | -$57.00/day (n=2) | -$325.00/day (n=2) | never | never |
| safe-3 | $1,967.81 | $3,032.19 | -$1.69/day (n=13) | -$34.33/day (n=6) | +$26.29/day (n=7) | never | 115 |
| risky-1 | $1,756.87 | $3,243.13 | -$20.73/day (n=11) | -$53.20/day (n=5) | +$6.33/day (n=6) | never | 512 |
| risky-3 | $2,121.61 | $2,878.39 | +$9.73/day (n=15) | -$24.86/day (n=7) | +$40.00/day (n=8) | 296 | 72 |

**Cross-referencing the LARGER-sample simulated rates** (`CAPITAL-EFFICIENCY-2026-08-03.md`
+ `SIZING-SCALING-DECISION-2026-08-03.md`, 390-day backtest, only exists for the two core
arms) — **tier-labeled, because the cap itself changes which trades clear it, and that
matters more here than a single "recent" number would suggest:**

| Arm | Full-391d, @ current-ish tier | Recent-25d, @ $2,000 cap | Recent-25d, @ $1,746.75 cap | Recent-25d, @ $5,000+ cap (cap fully loosened) |
|---|---:|---:|---:|---:|
| safe-2 | $34.36/trading-day (@ $2,000 tier) · $27.27 (@ $5,000+ tier) | +$46.72/day | +$64.41/day | **-$0.51/day** |
| bold-2 | $63.66/trading-day (flat, every tier) | +$80.50/day | not computed | **+$205.14/day** |

**This table needs its own correction flagged, because I initially read it too shallowly.**
`CAPITAL-EFFICIENCY-2026-08-03.md` §5 published the $64.41/day figure as "genuinely better,
not just noisier." `SIZING-SCALING-DECISION-2026-08-03.md` §3 already caught that this was
computed at ONE specific narrow cap ($1,746.75) that happens to filter OUT the recent
window's more expensive (and, on the fuller sample, worse) trades — at a fully-loosened
$5,000+ cap, the SAME 33-trade Safe population reads **-$0.51/day**, not +$64.41. **Which
of these is the right number for safe-2's OWN growth path is not a fixed fact — it depends
on where in the $1,160→$5,000 journey safe-2's cap actually sits at the time**, and that
shifts continuously as equity grows. Near today's equity (sub-$2,000), the $46.72-$64.41
readings are the closer analogs; as equity approaches $5,000 the -$0.51 reading becomes
more relevant — which is exactly the inflection this model is trying to reach, making the
sim-rate estimate partly circular for safe-2 specifically. **Bold shows the opposite shape**
on this same population: its recent-25 baseline gets BETTER at the looser cap ($80.50 →
$205.14/day, zero trades denied at $5K+) — but that reading is n=37 trades over 25 SIMULATED
days, sharply contradicted by bold-2's own 4 REAL paper fills over roughly the same recent
era (-$191.00/day, §5's real-fill table above). Both are real, sourced numbers; neither
is dismissed to make the story cleaner.

**Reading this honestly:** the real-fill rates and the simulated rates **disagree in both
magnitude and sometimes sign, for both core arms**, and the disagreement is itself the
finding, not noise to average away. safe-2's own recent 7 REAL days are negative
(-$155.57/day) — consistent in DIRECTION, if not magnitude, with the corrected -$0.51/day
loosened-cap sim reading, not with the original $64.41 headline. bold-2's own 4 REAL days
are also strongly negative (-$191.00/day) despite a strongly positive simulated recent
population. **The honest range for safe-2 is roughly 44 days (using the full-history
$1,746.75-baseline sim rate, the single most generous defensible number) to "not currently
on this trajectory" (both the corrected loosened-cap sim AND the freshest real fills agree
on the sign, even if not the exact magnitude) — lean toward the pessimistic end.** bold-2's
range is similarly wide and, on its only REAL evidence, currently pointed the wrong way. No
fleet arm has an equivalent large-sample simulated study — that is a disclosed, real gap in
the evidence base, not filled in here with a guess.

**With the participation gap illustratively closed** (§3.1's `+$30/day`-order-of-magnitude
bound applied to the 3 fleet arms' own recent-half rate; NOT a validated forecast):

| Arm | Recent-half rate + illustrative gap-closure | Days to $5,000 |
|---|---:|---:|
| safe-3 | ~$26.29 + $11-32 ≈ $37-58/day | 52-82 |
| risky-1 | ~$6.33 + $11-32 ≈ $17-38/day | 85-187 |
| risky-3 | ~$40.00 + $11-32 ≈ $51-72/day | 40-56 |

Closing the participation gap **roughly halves the pessimistic end of the range for the
two arms that are currently thinnest (safe-3, risky-1) — it does not transform the
picture, and it does nothing for bold-2** (bold-2's own gap is `gate_named`/production
doctrine, already studied and not re-opened here, not `min_premium_floor`).

### 5.1. Regime 2 — above ~$5,000, IF shrink-semantics scaling ships and is armed

`SIZING-SCALING-DECISION-2026-08-03.md`'s own table (core only; no fleet-arm equivalent
exists) — cited, not re-derived:

| Equity | Safe baseline (flat) | Safe scaled (shrink semantics, unbuilt) | Bold baseline (flat) | Bold scaled (shrink semantics, unbuilt) |
|---:|---:|---:|---:|---:|
| $5,000 | $27.11/day | $71.18/day | $96.40/day | $127.48/day |
| $10,000 | $27.11/day | $135.26/day | $96.40/day | $340.57/day (thin, n small — that doc's own caution) |
| $25,000 | $27.11/day | $165.92/day | $96.40/day | $353.41/day |

**This regime requires THREE things that have not happened, in order:** (1) ship the
shrink-semantics wiring (that document's own recommendation — inert today, zero risk); (2)
re-validate it with its own harness (specified, not yet measured); (3) J arms it — a
risk-posture call that document explicitly declines to make for him. Combined
$100-200/day is reachable in this regime for a SINGLE arm around the $5,000-10,000 mark
IF all three land and the flat-curve edge itself holds at scale (unverified — a scaled
population is a sizing-only counterfactual, not a re-priced one, per that document's own
caveats).

---

## 6. Stress test — what would invalidate this model

- **The measured rate is a THIN sample, not a forward guarantee.** Every fleet-arm rate in
  §5 is drawn from 11-15 real trading days; every early/recent half-split is drawn from
  5-8 days. A single large win or loss moves these rates by tens of dollars per day. Treat
  the RANGE, not any single number, as the finding.
- **Recent ≠ better, mechanically.** J's own standing rule is recency > aggregate, and this
  document follows it (leading with recent-half rates) — but "recent" here is also "smaller
  sample," and safe-2's own recent-half swing (from a strongly positive full/early rate to
  a strongly negative recent one) is a live demonstration that recency and reliability can
  point in opposite directions at this sample size.
- **The participation-gap-closure numbers in §5 are illustrative bounds, not measurements.**
  Zero live trading days exist under the shipped strike-tier fix. If the first 10-15 real
  sessions under that fix show a $/day rate outside the $11-32 illustrative band used here,
  this document's §5 "with gap closed" row should be recomputed from real data, not from
  this bound.
- **A losing stretch is not a broken model.** `SIZING-SCALING-DECISION-2026-08-03.md`'s own
  drawdown analysis found 40%-313%-of-equity peak-to-trough stretches in the FULL 18-month
  simulated history at low-to-mid equity. The daily kill switch bounds a single bad DAY; it
  does not bound a multi-week bleed. A model that assumes a smooth, monotonic climb to
  $5,000 is wrong by construction — the real path will have setbacks the linear-runway
  arithmetic in §5 does not show.
- **What would falsify the §3.1 fix specifically:** if, after 10-15 real sessions,
  risky-1/risky-3's `min_premium_floor` event count under the new ATM strike table has NOT
  materially dropped from its pre-fix historical rate (~1.85 events/day for risky-1), the
  fix did not work as diagnosed and the mechanism needs re-investigation before extending
  it to safe-3.
- **What would falsify §3.2:** if risky-3 (or safe-3/risky-1 as they approach $2,000) shows
  a cluster of `risk_cap` denials concentrated in the days immediately after crossing the
  boundary upward, that is direct, real-time confirmation of the deadlock actually biting —
  the standing recommendation (shrink semantics) becomes urgent, not precautionary.

---

## 7. Guards, RED-proofs, disclosures

- **34 tests**, `backtest/tests/test_arm_participation_growth_2026_08_03.py`, covering every
  pure function in the new tool (`mechanism_bucket` — 17 tests spanning every reachable
  bucket plus the fail-open "unrecognized input still counted, never dropped" contract;
  `days_to_target` — the at-target / zero-rate / negative-rate / none-rate boundary cases;
  `windowed_real_pnl`; `split_recent_vs_early` — including the odd-n tie-goes-to-recent
  rule). All pass:
  ```
  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_arm_participation_growth_2026_08_03.py -q
  34 passed
  ```
- **RED-proofed live, this session, two independent mutations:** (1) flipped
  `days_to_target`'s at-target boundary from `>=` to `>` — caught by a boundary test that
  was ITSELF found missing during the RED-proof (added
  `test_at_target_with_non_positive_rate_is_still_zero_not_none`, confirmed it fails against
  the mutation, then reverted); (2) flipped `not_flat_rule4`'s mapping to `risk_cap` —
  2 tests failed exactly as expected (`test_not_flat_blocker`,
  `test_full_task_mechanism_vocabulary_is_reachable`), both reverted, suite confirmed green
  again (34 passed). The existing `participation_cascade.py` suite (51 tests) was re-run
  unchanged alongside this one as a non-regression check — 85 total passed.
- **Live verification, not assumed:** all 5 arms' current equity fetched fresh this session
  via read-only `GET /v2/account` (`fleet_broker.get_account`) — matched the task brief's
  own figures to within a $0.06 timing artifact on 1 of 5, exact on 4 of 5. risky-1's
  "128 straight HOLDs" re-derived directly from the raw ledger, not just the aggregated
  tool, and found to differ slightly (19 vs. a prior doc's "16") from an existing narrative
  claim in `accounts.json` — reported as a correction, not silently adopted.
- **Known, disclosed limits:** (a) `sizing_deadlock` cannot be sub-classified from
  `binding.deadlock` telemetry — verified empty on every row checked, not assumed; §3.2's
  live-deadlock finding is established through the equity-trajectory route instead,
  independently. (b) No fleet-arm-specific large-sample backtest exists (unlike core
  Safe/Bold) — §5's fleet-arm growth rates rest on 11-15 real days each, explicitly flagged
  as thin throughout, not smoothed over. (c) `journal/trades.csv` has ~26 of 223 rows
  (11.7%) that fail to parse cleanly (unescaped quotes in the notes column shifting
  columns) — skipped and counted, not guessed at; the well-formed rows cross-validate
  exactly against `CAPITAL-EFFICIENCY-2026-08-03.md`'s independently-cited safe-account
  total. (d) The §3.1 "$30/day illustrative" bound is explicitly NOT a validated forecast —
  restated three times in this document on purpose, because it is the single number most
  likely to get quoted out of context.

---

## 8. The blunt paragraph

Given everything measured this weekend: per-trade quality is at a ceiling (13 nulled
selection attempts), frequency is gate-limited with one narrow lever pending validation,
size doesn't scale below ~$5,000 and actively backfires if scaled naively at $2,000, and
now — participation is real but smaller than hoped, with 87% of its fixable share
concentrated in ONE already-partially-shipped strike-selection fix. **The fastest honest
path from here to $100-200/day is not a single lever, it is patience plus one specific
follow-through: let the already-shipped risky-1/risky-3 ATM strike fix run 10-15 real
sessions, extend it to safe-3 the moment that evidence is positive (a one-line config
change, already precedented twice), and in parallel apply the shrink-semantics sizing fix
to the fleet's `_qty_for` before risky-3 (already past $2,000) or safe-3/risky-1 (both
approaching it) compound into the live deadlock §3.2 found. Both are cheap, both are
already half-built, and together they are worth low tens of dollars per day, not
hundreds.** Getting to $100-200/day from here is a compounding story, not a participation
story: it requires equity actually crossing the ~$5,000 inflection where
`SIZING-SCALING-DECISION`'s scaled numbers turn real, and that in turn requires the
current small, thin, sometimes-negative edge to survive enough trading days to get there —
roughly 40 to 500+ depending on which arm and which window, honestly ranged, not pointed.
**What the engine can do by itself, unprompted:** ship the safe-3 strike-tier extension, wire and
guard-test the shrink-semantics sizing fix, and keep measuring real fills as the fix runs —
all paper-only, all reversible, all within standing authorization. **What only J can do:**
decide whether to arm shrink-semantics scaling once it's validated (an explicit
risk-posture call `SIZING-SCALING-DECISION` already declined to make for him), and accept
that the realistic timeline is measured in trading-day counts in the dozens-to-low-hundreds,
not a number of days that fits comfortably before next week.

---

_Sources: `backtest/tools/participation_cascade.py` (reused, unmodified) ·
`backtest/tools/arm_participation_growth_2026_08_03.py` (new) ·
`backtest/tests/test_arm_participation_growth_2026_08_03.py` (new, 34 tests) ·
`analysis/deep-research/ARM-PARTICIPATION-AND-GROWTH-2026-08-03.json` (new, raw output) ·
`automation/state/core-decisions.jsonl` · `automation/state/fleet/{safe-3,risky-1,risky-3}/
decisions.jsonl` · `automation/state/fleet/accounts.json` · `journal/trades.csv` ·
`automation/state/fleet/fleet_broker.py` (imported, read-only, live equity check) ·
`analysis/deep-research/FREQUENCY-CEILING-2026-08-03.md` ·
`analysis/deep-research/CAPITAL-EFFICIENCY-2026-08-03.md` ·
`analysis/deep-research/SIZING-SCALING-DECISION-2026-08-03.md` ·
`setup/scripts/full_send_vs_gated.py` (referenced, not re-run — same-purpose standing
query for risky-1 specifically) · `markdown/doctrine/FOCUS-DOCTRINE.md`._
